# Data Models - Backend

**Date:** 2026-07-24
**Source:** `backend/data_models/` (6 files + `base.py`)

## Overview

The full column-level schema (types, constraints, business logic, relationship diagram) is already documented in [database-schema.md](./database-schema.md) and [diagrams/database-schema.puml](./diagrams/database-schema.puml) — verified against the code and accurate as of this scan. This document adds the **implementation-level** details that a database design doc doesn't cover: file locations, SQLAlchemy patterns, and migration status.

**11 tables** are modeled across 6 files, all inheriting from `data_models/base.py::Base` (`sqlalchemy.orm.DeclarativeBase`):

| File | Tables | Enums |
|---|---|---|
| `user.py` | `User` | `UserRole` (admin/waiter/cook/warehouse_manager) |
| `menu.py` | `Category`, `Dish` | — |
| `recipe.py` | `Ingredient`, `RecipeIngredient` | `Unit` (kg/liter/piece) |
| `order.py` | `RestaurantTable`, `Order`, `OrderItem` | `TableStatus`, `OrderStatus`, `OrderItemStatus` |
| `inventory.py` | `StockMovement` | `MovementType` (purchase/consumption/waste/adjustment) |
| `ai.py` | `AIRecipeSuggestion`, `AIChatSession`, `AIChatMessage` | `ChatRole` (user/assistant) |

## Implementation Notes

- **Style:** SQLAlchemy 2.0 typed declarative style throughout — `Mapped[T]` + `mapped_column(...)`, no legacy `Column(...)` usage.
- **Enums** are native Python `enum.Enum` classes mapped via SQLAlchemy's `Enum` type — one enum class per file, colocated with the table(s) that use it (not centralized).
- **Timestamps** use `server_default=func.now()` (DB-side default), not Python-side `datetime.utcnow()`.
- **No migration tool** — there is no Alembic (or equivalent) setup. Schema is created via `Base.metadata.create_all(...)` inside `backend/container.py::_init_database`, executed automatically on every app startup (see `backend/clients/database.py` is a different file — the engine init lives in `container.py`). This means:
  - New tables/columns require a fresh database or manual DDL against existing environments — `create_all` will not alter existing tables.
  - Any schema evolution strategy (Alembic or otherwise) is an open decision, not yet made.
- **Async only** — the engine is `create_async_engine` with the `asyncpg` driver; there is no sync engine/session anywhere in the codebase.
- **Session access pattern:** routes obtain a session via `SessionDep` (`backend/clients/database.py`), which pulls `request.app.container.database().session_factory` — not via `dependency-injector`'s `@inject`/`Provide[...]` (that wiring path is not yet activated; see [architecture-backend.md](./architecture-backend.md)).

## Full Schema Reference

See [database-schema.md](./database-schema.md) for:

- Complete column listing (types, constraints, defaults) for all 11 tables
- Business logic notes (e.g., stock deduction on order-item preparation, low-stock alert trigger)
- Full relationship summary table
- Status lifecycle diagram for `Order`/`OrderItem`

See [diagrams/database-schema.puml](./diagrams/database-schema.puml) for the PlantUML ER diagram.

## Cross-check: Schema Doc vs. Code

The existing `database-schema.md` was checked line-by-line against the SQLAlchemy model files during this scan — no discrepancies were found. The two documents can be considered in sync as of 2026-07-24.

---

_Generated using BMAD Method `document-project` workflow_
