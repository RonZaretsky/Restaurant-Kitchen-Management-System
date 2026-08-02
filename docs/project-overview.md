# Restaurant-Kitchen-Management-System - Project Overview

**Date:** 2026-07-24
**Type:** Multi-part (backend + frontend)
**Architecture:** Layered/DI-container backend API + component-based SPA frontend

## Executive Summary

A full-stack restaurant kitchen management system, currently in early scaffolding stage. The backend is a FastAPI service wired through a `dependency-injector` container, with a complete SQLAlchemy async data model (11 tables across 6 functional modules: users, menu, recipes/ingredients, tables/orders, inventory, AI features) but only a single `/health` route implemented — no business endpoints exist yet. The frontend is a bare Vite/React/TypeScript scaffold (single placeholder `<App />`) with folder structure in place (`components/`, `pages/`, `services/`, `types/`) but no implemented UI. The two parts do not yet call each other in code; integration is presently limited to Docker networking and documented environment variables.

## Project Classification

- **Repository Type:** Multi-part (client/server layout in a single repository, not a workspace-tooled monorepo)
- **Project Type(s):** `backend` (Python/FastAPI), `web` (React/TypeScript)
- **Primary Language(s):** Python 3.12+, TypeScript 5.7 (strict)
- **Architecture Pattern:** Backend — service/API-centric with dependency-injection container managing resource lifecycle (logging, DB engine). Frontend — component-based SPA (currently unstructured, single component).

## Multi-Part Structure

This project consists of 2 distinct parts:

### Backend

- **Type:** backend (Python/FastAPI)
- **Location:** `backend/`
- **Purpose:** REST API serving kitchen/restaurant operations data (menu, orders, inventory, users) backed by PostgreSQL
- **Tech Stack:** FastAPI ≥0.115.0, uvicorn[standard] ≥0.30.0, dependency-injector ≥4.41.0, SQLAlchemy[asyncio] ≥2.0.0, asyncpg ≥0.29.0, loguru ≥0.7.0, PyYAML ≥6.0 — managed by `uv`

### Frontend

- **Type:** web (React SPA)
- **Location:** `frontend/`
- **Purpose:** Browser client for restaurant staff (waiters, cooks, warehouse managers, admins) to interact with the kitchen management system
- **Tech Stack:** React 19.0.0, TypeScript ~5.7.2 (strict mode), Vite ^6.0.5 — managed by `pnpm`

### How Parts Integrate

Intended integration is REST-over-HTTP: the frontend reads `VITE_API_BASE_URL` (default `http://localhost:8000`) via `src/config/config.ts` and would call the backend's REST API. **No actual HTTP calls exist in the frontend code yet** — `services/` is empty. In Docker Compose, the frontend container is built with `VITE_API_BASE_URL=http://localhost:8000` baked in at build time (not the internal Docker service name `backend`), and the backend has no CORS middleware configured, so browser-based calls from the frontend origin (`:3000`/`:80`) to the backend (`:8000`) will currently fail silently until CORS is added.

## Technology Stack Summary

### Backend Stack

| Category | Technology | Version | Notes |
|---|---|---|---|
| Language | Python | ≥3.12 | |
| Web framework | FastAPI | ≥0.115.0 | |
| ASGI server | uvicorn[standard] | ≥0.30.0 | |
| Dependency Injection | dependency-injector | ≥4.41.0 (v4 API) | `Container.wire()` not yet called anywhere |
| ORM | SQLAlchemy[asyncio] | ≥2.0.0 | Async engine/session via `providers.Resource` |
| DB driver | asyncpg | ≥0.29.0 | PostgreSQL |
| Logging | loguru | ≥0.7.0 | Wired as a DI `Resource` alongside DB |
| Config | PyYAML | ≥6.0 | `backend/config.yaml` with `${VAR: default}` env-override syntax |
| Package manager | uv | — | `backend/uv.lock` authoritative |

### Frontend Stack

| Category | Technology | Version | Notes |
|---|---|---|---|
| Language | TypeScript | ~5.7.2 | `strict`, `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch` enforced at build |
| Framework | React | 19.0.0 | |
| Build tool | Vite | ^6.0.5 | Dev server on port 3000 |
| Package manager | pnpm | 9.15.0 (pinned via `packageManager`) | |

## Key Features

Based on the designed (but largely unimplemented) data model, the system is scoped to cover:

- **User management** with role-based access (`admin`, `waiter`, `cook`, `warehouse_manager`)
- **Menu management** (categories, dishes, pricing, availability)
- **Recipes & ingredients** (bill-of-materials linking dishes to ingredients)
- **Table & order management** with an order/order-item status lifecycle (`pending → in_preparation → ready → served → closed`)
- **Inventory tracking** via an append-only `StockMovement` audit log, with low-stock alerting logic
- **AI features** — recipe suggestions and chat sessions (schema references "OpenAI" in the prompt field comment; no AI client integration exists in code yet)

None of the above are implemented as API endpoints yet — only the data model exists.

## Architecture Highlights

- **DI-managed resource lifecycle:** `backend/container.py` defines `logging` and `database` as `providers.Resource`, initialized/torn down in `main.py`'s FastAPI `lifespan` context — this is the established pattern any future resource (e.g., an AI/OpenAI client) should follow.
- **Config loading with env override:** `backend/utils.py::load_config` parses `config.yaml` and substitutes `${VAR: default}` placeholders from environment variables before YAML parsing — a custom mechanism, not a standard library (e.g., not `pydantic-settings`).
- **Single router today:** all routes live in `backend/api/router.py`; only `GET /health` exists.
- **No auth/authorization layer:** despite `User.role` being modeled, every route is effectively public today.
- **No CORS middleware:** cross-origin browser calls from the frontend will fail until added.
- **Frontend has no state management or component library chosen** — folders (`components/`, `pages/`, `services/`, `types/`) are scaffolded intentionally but empty.

## Development Overview

### Prerequisites

- **Backend:** Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/)
- **Frontend:** Node.js 20+, [pnpm](https://pnpm.io/installation) 9.15.0
- **Full stack:** Docker + Docker Compose (for the bundled `postgres` service and containerized run)

### Getting Started

Fastest path is `docker compose up --build` from the repo root, which starts `postgres`, `backend` (:8000), and `frontend` (:3000→:80). For local (non-Docker) development, run backend and frontend separately — see part-specific development guides.

### Key Commands

#### Backend

- **Install:** `uv sync` (run from `backend/`)
- **Dev:** `uv run python main.py`
- **Build:** N/A (interpreted; Docker image via `backend/Dockerfile`)
- **Test:** No test framework configured yet

#### Frontend

- **Install:** `pnpm install` (run from `frontend/`)
- **Dev:** `pnpm dev`
- **Build:** `pnpm build` (runs `tsc -b && vite build`)
- **Test:** No test framework configured yet

## Repository Structure

```
.
├── backend/          # FastAPI service (Python, uv-managed)
├── frontend/          # React/Vite SPA (TypeScript, pnpm-managed)
├── docs/              # Project documentation (this folder)
├── _bmad/, _bmad-output/  # BMad Method tooling and generated planning/context artifacts
└── docker-compose.yml # postgres + backend + frontend orchestration
```

## Documentation Map

For detailed information, see:

- [index.md](./index.md) — Master documentation index
- [architecture-backend.md](./architecture-backend.md) / [architecture-frontend.md](./architecture-frontend.md) — Detailed architecture per part
- [source-tree-analysis.md](./source-tree-analysis.md) — Directory structure
- [development-guide-backend.md](./development-guide-backend.md) / [development-guide-frontend.md](./development-guide-frontend.md) — Development workflow

---

_Generated using BMAD Method `document-project` workflow_
