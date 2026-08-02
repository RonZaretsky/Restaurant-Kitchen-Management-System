# Backend Architecture - Restaurant-Kitchen-Management-System

**Date:** 2026-07-24
**Part:** backend (`backend/`)

## Executive Summary

The backend is a FastAPI service whose lifecycle-sensitive resources (structured logging, async database engine/session) are wired through a `dependency-injector` `DeclarativeContainer`, initialized and torn down via FastAPI's `lifespan` context manager. The data layer is fully modeled in SQLAlchemy 2.0 (async, 11 tables), but the API surface currently exposes only a single health-check endpoint — no business logic, authentication, or CORS handling exists yet.

## Technology Stack

| Category | Technology | Version | Justification |
|---|---|---|---|
| Language | Python | ≥3.12 | `pyproject.toml requires-python` |
| Web framework | FastAPI | ≥0.115.0 | Async-native, OpenAPI docs at `/docs` |
| ASGI server | uvicorn[standard] | ≥0.30.0 | Runs via `uvicorn.run("main:app", ...)` in `main.py` |
| DI container | dependency-injector | ≥4.41.0 | v4 declarative API (`containers.DeclarativeContainer`, `providers.Resource`) |
| ORM | SQLAlchemy | ≥2.0.0 (asyncio extras) | `Mapped`/`mapped_column` typed model style |
| DB driver | asyncpg | ≥0.29.0 | Used in the `postgresql+asyncpg://` connection URL |
| Logging | loguru | ≥0.7.0 | Wired as a `providers.Resource`, same pattern as DB |
| Config parsing | PyYAML | ≥6.0 | Custom `${VAR: default}` substitution in `utils.py` |
| Package manager | uv | — | `backend/uv.lock` authoritative; never hand-edit |

## Architecture Pattern

Service/API-centric backend with an explicit **resource-lifecycle DI container**. Two resources are currently registered:

1. `logging` — configures `loguru` sinks (`_init_logging`)
2. `database` — creates the async SQLAlchemy engine, runs `Base.metadata.create_all`, and yields a `Database` dataclass wrapping the engine + `async_sessionmaker` (`_init_database`)

Both are `providers.Resource`, meaning they run generator-based init/teardown hooks triggered by `container.init_resources()` / `container.shutdown_resources()` in `main.py`'s `lifespan`. **Any future long-lived resource (e.g., an OpenAI client for the AI features) must follow this same pattern** — never instantiate long-lived clients directly inside route handlers or services.

`container.wire(modules=[...])` is **not called anywhere yet** — so `@inject` / `Depends(Provide[...])` DI-style injection is not currently functional; the codebase instead uses a plain FastAPI dependency (`SessionDep = Annotated[AsyncSession, Depends(get_session)]` in `clients/database.py`) that reaches into `request.app.container.database()` directly.

## Data Architecture

See [data-models-backend.md](./data-models-backend.md) for the full schema. Summary: 11 tables across 6 domains (users, menu, recipes/ingredients, tables/orders, inventory, AI). All models inherit `data_models/base.py::Base` (`DeclarativeBase`). No migration tool is configured — schema is created via `Base.metadata.create_all` on every startup, which is destructive-safe only because it's additive (won't drop/alter existing tables, but also won't apply schema changes to existing deployed databases).

## API Design

See [api-contracts-backend.md](./api-contracts-backend.md). Only `GET /health` exists today, defined directly in `backend/api/router.py` as a single flat `APIRouter`. Convention going forward (per project rules): introduce a dedicated sub-router per domain (menu, orders, inventory, etc.) and `include_router()` it into the main router, rather than growing one file indefinitely.

## Component Overview

- **`main.py`** — FastAPI app factory (`create_app`), `lifespan` context manager, `uvicorn.run` entrypoint
- **`container.py`** — DI container: `config`, `logging` (Resource), `database` (Resource)
- **`constants.py`** — `SETTINGS` class: app name/version, config file path
- **`utils.py`** — `load_config()`: reads YAML, substitutes `${VAR: default}` from environment before parsing
- **`api/router.py`** — single `APIRouter`, currently just `/health`
- **`clients/database.py`** — `get_session()` FastAPI dependency + `SessionDep` type alias, used to obtain an `AsyncSession` per-request from `request.app.container.database()`
- **`data_models/`** — 6 model files + `base.py` + empty `exceptions/` subpackage (designated location for custom exceptions, currently unused — code should not `raise Exception(...)` inline nor create a parallel error-handling location)
- **`services/`** — empty, designated location for business logic

## Source Tree

See [source-tree-analysis.md](./source-tree-analysis.md) for the full annotated tree.

## Development Workflow

See [development-guide-backend.md](./development-guide-backend.md).

## Deployment Architecture

See [deployment-guide.md](./deployment-guide.md). Containerized via `backend/Dockerfile` (python:3.12-slim + `uv sync --no-dev`), orchestrated alongside `postgres` and `frontend` in the root `docker-compose.yml`.

## Testing Strategy

No test framework is installed (no `pytest`, no `conftest.py`, no test files exist). The standard FastAPI pairing (`pytest` + `httpx.AsyncClient`) is the natural choice when tests are introduced, but should be raised as an explicit decision rather than added speculatively.

## Critical Architectural Notes

- **No CORS middleware** — must be added before the frontend can successfully call this API from a browser (different origins: `:3000`/`:80` vs `:8000`).
- **No auth/authorization layer** — despite `User.role` being modeled (`admin`/`waiter`/`cook`/`warehouse_manager`), every route is effectively public today. Do not assume any endpoint is protected.
- **DI wiring incomplete** — `container.wire(modules=[...])` is never called; `@inject`-style injection will silently resolve to unconfigured providers if introduced without also adding the module to the wire list.
- **Imports are relative to `backend/` as root** — the app runs via `uv run python main.py` from inside `backend/`; never use `from backend.X import ...` package-style imports.

---

_Generated using BMAD Method `document-project` workflow_
