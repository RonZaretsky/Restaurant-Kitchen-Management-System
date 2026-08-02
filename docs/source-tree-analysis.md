# Restaurant-Kitchen-Management-System - Source Tree Analysis

**Date:** 2026-07-24

## Overview

The repository is a two-part client/server layout at the root: `backend/` (FastAPI/Python) and `frontend/` (React/Vite/TypeScript), orchestrated together by a root-level `docker-compose.yml`. Supporting documentation lives in `docs/`, and BMad Method tooling/artifacts live in `_bmad/` and `_bmad-output/`.

## Multi-Part Structure

This project is organized into 2 distinct parts:

- **Backend** (`backend/`): FastAPI REST API, SQLAlchemy async data layer, DI-managed resources
- **Frontend** (`frontend/`): React/Vite SPA scaffold

## Complete Directory Structure

```
.
├── README.md
├── docker-compose.yml
├── .gitignore
├── docs/
│   ├── database-schema.md
│   ├── diagrams/
│   │   └── database-schema.puml
│   └── generate_pdf.py
├── _bmad/                          # BMad Method installation (skills, config, scripts)
├── _bmad-output/                   # BMad-generated planning/context artifacts
│   └── project-context.md
├── backend/
│   ├── main.py                     # FastAPI app factory + entrypoint
│   ├── container.py                # dependency-injector container (logging, database resources)
│   ├── constants.py                 # SETTINGS: app name/version/config path
│   ├── utils.py                     # load_config(): YAML + ${VAR:default} env substitution
│   ├── config.yaml                  # app/server/database/logging config with env overrides
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── Dockerfile
│   ├── api/
│   │   ├── __init__.py
│   │   └── router.py                # single APIRouter; only GET /health today
│   ├── clients/
│   │   ├── __init__.py
│   │   └── database.py              # get_session() FastAPI dependency, SessionDep type alias
│   ├── data_models/
│   │   ├── __init__.py
│   │   ├── base.py                  # SQLAlchemy DeclarativeBase
│   │   ├── user.py                  # User, UserRole
│   │   ├── menu.py                  # Category, Dish
│   │   ├── recipe.py                # Ingredient, RecipeIngredient, Unit
│   │   ├── order.py                 # RestaurantTable, Order, OrderItem, TableStatus/OrderStatus/OrderItemStatus
│   │   ├── inventory.py             # StockMovement, MovementType
│   │   ├── ai.py                    # AIRecipeSuggestion, AIChatSession, AIChatMessage, ChatRole
│   │   └── exceptions/
│   │       └── __init__.py          # empty — designated location for custom exceptions
│   └── services/
│       └── __init__.py              # empty — designated location for business logic
└── frontend/
    ├── index.html
    ├── package.json
    ├── pnpm-lock.yaml
    ├── vite.config.ts                # dev server pinned to port 3000
    ├── tsconfig.json / tsconfig.app.json / tsconfig.node.json
    ├── Dockerfile                    # multi-stage: pnpm build → nginx:alpine serving /dist
    └── src/
        ├── main.tsx                  # ReactDOM root, StrictMode
        ├── App.tsx                   # single placeholder component (<h1>...</h1>)
        ├── vite-env.d.ts
        ├── config/
        │   └── config.ts             # reads import.meta.env.VITE_API_BASE_URL / VITE_API_TIMEOUT_MS
        ├── components/.gitkeep       # empty — reusable UI components (none yet)
        ├── pages/.gitkeep            # empty — route-level components (none yet)
        ├── services/.gitkeep         # empty — API client layer (none yet)
        └── types/.gitkeep            # empty — shared TypeScript types (none yet)
```

## Critical Directories

### `backend/api/`

Houses the single `APIRouter` (`router.py`) that `main.py` includes into the FastAPI app.

**Purpose:** HTTP route definitions
**Contains:** 1 file, 1 route (`GET /health`)
**Entry Points:** `router` object imported by `backend/main.py`

### `backend/data_models/`

SQLAlchemy ORM models, one file per functional domain, all inheriting from `data_models/base.py::Base`.

**Purpose:** Database schema definition (11 tables across 6 files)
**Contains:** `base.py`, `user.py`, `menu.py`, `recipe.py`, `order.py`, `inventory.py`, `ai.py`, plus an empty `exceptions/` subpackage
**Integration:** `Base.metadata.create_all` is run automatically at startup by `container.py::_init_database` — tables are created on every app boot, there is no migration tool (e.g. Alembic) in use

### `backend/clients/`

Infrastructure-facing helpers — currently just the DB session dependency.

**Purpose:** External resource access (DB session provisioning today)
**Contains:** `database.py` (`get_session`, `SessionDep`)

### `backend/services/`

Empty but intentional — designated location for business logic per project conventions.

**Purpose:** Business logic layer (not yet populated)

### `frontend/src/`

All frontend application code.

**Purpose:** React application source
**Contains:** Entry point (`main.tsx`), root component (`App.tsx`), config module, and four scaffolded-but-empty folders (`components/`, `pages/`, `services/`, `types/`)
**Entry Points:** `index.html` → `src/main.tsx` → `src/App.tsx`

## Entry Points

### Backend

- **Entry Point:** `backend/main.py`
- **Bootstrap:** Module-level `container = Container()` is created and configured from `config.yaml` at import time; `create_app()` builds the FastAPI instance with a `lifespan` context manager that calls `container.init_resources()` / `container.shutdown_resources()`. Run via `uv run python main.py` from inside `backend/` (imports are relative to `backend/` as root, not package-style).

### Frontend

- **Entry Point:** `frontend/src/main.tsx`
- **Bootstrap:** `index.html` loads `/src/main.tsx` as an ES module, which mounts `<App />` (wrapped in `<StrictMode>`) into `#root` via `createRoot`.

## File Organization Patterns

- **Backend:** role-based top-level folders (`api`, `clients`, `data_models`, `exceptions` [nested under `data_models`], `services`) — new backend code should be placed into the existing folder matching its responsibility rather than creating new top-level modules.
- **Frontend:** route/reuse-based folders (`pages/` for route-level components, `components/` for reusable UI, `services/` for API calls, `types/` for shared types) — currently all empty placeholders (`.gitkeep`), but the convention is established and should be followed when code is added.

## Key File Types

### SQLAlchemy Model Files

- **Pattern:** `backend/data_models/*.py`
- **Purpose:** Define ORM-mapped tables using SQLAlchemy 2.0 `Mapped`/`mapped_column` syntax
- **Examples:** `user.py`, `menu.py`, `order.py`, `inventory.py`, `recipe.py`, `ai.py`

### FastAPI Route Files

- **Pattern:** `backend/api/router.py` (currently one file; convention calls for sub-routers as domains grow)
- **Purpose:** HTTP endpoint definitions with Pydantic `response_model`s
- **Examples:** `router.py` (`GET /health`)

### React Component Files

- **Pattern:** `frontend/src/**/*.tsx`
- **Purpose:** UI components
- **Examples:** `App.tsx` (only one exists today)

## Asset Locations

No significant assets detected — no `public/`, `static/`, or `assets/` directories with content in either part.

## Configuration Files

- **`backend/config.yaml`**: App/server/database/logging config, with `${VAR: default}` placeholders resolved against environment variables by `backend/utils.py::load_config`
- **`backend/pyproject.toml`**: Python dependencies (uv-managed), `requires-python = ">=3.12"`
- **`frontend/package.json`**: Frontend dependencies and scripts (`dev`, `build`, `preview`), `packageManager` pinned to `pnpm@9.15.0`
- **`frontend/vite.config.ts`**: Vite dev server config (port 3000, React plugin)
- **`frontend/tsconfig.app.json`**: Strict TypeScript compiler options (`strict`, `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`, `isolatedModules`)
- **`docker-compose.yml`** (root): Orchestrates `postgres` (5432), `backend` (8000), `frontend` (3000→80) with health-check-gated startup ordering

## Notes for Development

- Both `backend/services/` and `backend/data_models/exceptions/` are empty on purpose — they are the designated locations for business logic and custom exceptions respectively, not dead code to be removed.
- Frontend's four empty `src/` subfolders (`components/`, `pages/`, `services/`, `types/`) are likewise intentional scaffolding — place new files in the matching folder rather than flat in `src/`.
- No test framework is installed on either side; no CI/CD (`.github/workflows/`) exists.

---

_Generated using BMAD Method `document-project` workflow_
