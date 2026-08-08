# Development Guide - Backend

**Date:** 2026-07-24
**Part:** backend (`backend/`)

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## Environment Setup

Configuration lives in `backend/config.yaml`, with values overridable by environment variables using the `${VAR: default}` syntax parsed by `backend/utils.py::load_config`:

```yaml
app:
  debug: ${APP_DEBUG: false}
server:
  host: ${SERVER_HOST: "0.0.0.0"}
  port: ${SERVER_PORT: 8000}
database:
  host: ${DB_HOST: "localhost"}
  port: ${DB_PORT: 5432}
  user: ${DB_USER: "kitchen"}
  password: ${DB_PASSWORD: "kitchen"}
  name: ${DB_NAME: "kitchen"}
logging:
  level: ${LOG_LEVEL: "INFO"}
  colorize: ${LOG_COLORIZE: true}
auth:
  secret_key: ${JWT_SECRET_KEY: "dev-only-insecure-secret-change-me"}
  token_expiry_hours: ${JWT_EXPIRY_HOURS: 8}
cors:
  allow_origin: ${FRONTEND_ORIGIN: "http://localhost:3000"}
```

Overrides come from real process environment variables (`APP_DEBUG`, `SERVER_HOST`, `SERVER_PORT`, `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `LOG_LEVEL`, `LOG_COLORIZE`, `JWT_SECRET_KEY`, `JWT_EXPIRY_HOURS`, `FRONTEND_ORIGIN`), and from an optional `backend/.env` file loaded at import by `utils.load_config`. A real environment variable always beats the file, so docker-compose and your shell both still win.

### Secrets: set up `backend/.env` before the first run

```bash
cd backend
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into JWT_SECRET_KEY
```

`backend/.env` is gitignored and is excluded from the Docker build context, so the secret is injected at runtime and never baked into an image. `docker-compose.yml` picks it up via `env_file` (marked optional, so a fresh clone still starts).

**If you skip this**, the app falls back to the default `JWT_SECRET_KEY` published in `config.yaml` and logs a warning at startup. That default is in the public repository, so anyone can forge a session token against it. Fine for a throwaway local run, never for anything shared.

A PostgreSQL instance must be reachable at the configured host/port — locally this means either running `docker compose up postgres` from the repo root, or your own Postgres install matching the `database.*` config values.

## Installation

```bash
cd backend
uv sync
```

This installs dependencies from `pyproject.toml` per `uv.lock` (authoritative — never hand-edit; regenerate with `uv sync` after any manual `pyproject.toml` edit).

## Running Locally

```bash
cd backend
uv run python main.py
```

- API: `http://localhost:8000`
- Interactive docs (Swagger UI): `http://localhost:8000/docs`

`reload` is tied to `app.debug` in config — set `APP_DEBUG=true` for auto-reload during development.

## Build

No build step — Python is interpreted. For containerized runs, see [deployment-guide.md](./deployment-guide.md).

## Testing

**No test framework is currently installed** — no `pytest`, no `conftest.py`, no test files exist anywhere in the backend. When tests are introduced, `pytest` + `httpx.AsyncClient` is the standard FastAPI pairing, but this should be raised as an explicit decision first rather than added speculatively.

## Common Development Tasks

- **Add a new endpoint:** create/extend a router under `backend/api/`, following the existing pattern of `async def` handlers with an explicit Pydantic `response_model`. Prefer a dedicated sub-router per domain over growing `router.py` indefinitely.
- **Add a new table:** add a `Mapped`/`mapped_column` class to the relevant file under `backend/data_models/` (or a new file for a new domain), inheriting `Base`. Remember there is no migration tool — `create_all` only adds new tables/won't alter existing ones.
- **Add a new long-lived resource** (e.g., an external API client): register it as a `providers.Resource` in `backend/container.py`, following the same init/teardown generator pattern as `logging` and `database`.
- **Add custom exceptions:** place them in `backend/data_models/exceptions/` (currently empty but designated) rather than inlining generic `raise Exception(...)`.

---

_Generated using BMAD Method `document-project` workflow_
