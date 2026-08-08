---
project_name: 'Restaurant-Kitchen-Management-System'
user_name: 'Ron'
date: '2026-08-02'
supersedes: 'project-context.md dated 2026-07-24 (stale: predated the Postgres/SQLAlchemy merge, the architecture spine, the UX spines, and the epic breakdown)'
sources:
  - 'backend/ and frontend/ as they exist on disk, verified 2026-08-02'
  - '_bmad-output/planning-artifacts/architecture/architecture-Restaurant-Kitchen-Management-System-2026-07-30/ARCHITECTURE-SPINE.md'
  - '_bmad-output/planning-artifacts/epics.md'
status: 'complete'
optimized_for_llm: true
---

# Project Context for AI Agents

_Critical rules and current-state facts for anyone implementing code here. Focus is on the
unobvious: what exists vs. what is only decided, and the traps that fail silently._

---

## The single most important distinction: installed vs. decided

Many technologies are **ratified in the architecture spine but not yet in any manifest.** Do not
`import` them until the story that adopts them has run — and when you do adopt one, add it to the
manifest in that same change.

| | Installed and usable **now** | Decided, **not yet installed** (adopting story) |
|---|---|---|
| **Backend** | fastapi, uvicorn[standard], dependency-injector, pyyaml, loguru, sqlalchemy[asyncio], asyncpg | alembic (Story 1.0) · pytest + pytest-asyncio + httpx (Story 1.0) · a bcrypt/password-hashing lib (Story 1.1) · a JWT lib (Story 1.1) · openai (Story 6.1) |
| **Frontend** | react 19, react-dom, typescript ~5.7.2, vite ^6, @vitejs/plugin-react | react-router v7 (Story 1.4) · MUI v9 (Story 1.4) · @tanstack/react-query v5 (Story 1.4) · vitest + @testing-library/react (Story 1.0) |

Authoritative manifests: `backend/pyproject.toml` + `backend/uv.lock`, `frontend/package.json` +
`frontend/pnpm-lock.yaml`. Lockfiles are authoritative — regenerate via `uv sync` / `pnpm install`
after editing a manifest; never hand-edit a lockfile.

- Backend runs on Python >=3.12, managed by `uv`. Run from inside `backend/`: `uv run python main.py`.
- Frontend is pinned to `pnpm@9.15.0` via `packageManager`. **Never use npm or yarn.**
- Orchestration: Docker Compose — Postgres 16-alpine, backend :8000, frontend :3000 host → :80 container.

---

## Current state of the code

**Backend — layered, wired, and almost entirely empty of domain logic.**

```
backend/
  main.py            app factory + lifespan (init/shutdown container resources)
  container.py       DeclarativeContainer: config, logging, database — all providers.Resource
  constants.py       SETTINGS (app name, version, config path)
  config.yaml        ${ENV_VAR: default} interpolation, parsed by utils.load_config
  utils.py           config loader
  api/router.py      ONE router, ONE route: GET /health
  clients/database.py  SessionDep — AsyncSession from the container's session factory
  data_models/       7 ORM modules + base.py — the full schema, already written
  services/          EMPTY (only __init__.py) — no business logic exists yet
```

- `data_models/` is complete and mirrors `docs/database-schema.md`: `user.py`, `menu.py`,
  `recipe.py`, `order.py`, `inventory.py`, `ai.py`, `base.py`. **Do not treat the schema as unwritten.**
- `services/` is empty. Every domain rule in the epics still has to be written.
- `api/` has exactly one health route. Every domain router is still to be created.

**Frontend — scaffold only.** `src/App.tsx`, `src/main.tsx`, `src/config/config.ts`, and four
intentionally empty folders (`pages/`, `components/`, `services/`, `types/`, each holding a
`.gitkeep`). No routing, no component library, no state management, no screens.

---

## Traps that fail silently

These are the ones that cost hours because nothing errors:

1. **`container.wire()` is never called.** Not in `main.py`, not anywhere. Until it is, every
   `@inject` / `Depends(Provide[...])` resolves to an unconfigured provider — and it fails at
   *request* time, not import time, so the app starts fine and breaks on first call. Story 1.1
   activates it for `auth`. Every later story **appends** its module to `modules=[...]` — never
   replaces the list. A silently truncated list is the classic version of this bug.

2. **`Base.metadata.create_all` still runs on startup** (`container.py`, inside `_init_database`).
   It only creates *missing* tables. It will not add a column, will not alter a constraint, will not
   drop anything — and it reports success either way. **Story 1.0 adopts Alembic (async template,
   `alembic init -t async` — the sync template does not work with asyncpg), generates a baseline,
   and removes `create_all` from the startup path.** After Story 1.0, every schema change ships its
   own revision. Before Story 1.0, assume any schema edit you make is not actually applied.

3. **No CORS middleware exists.** Frontend `:3000` and backend `:8000` are different origins.
   Requests fail in-browser until `CORSMiddleware` is added with an explicit allow-list (never a
   wildcard). Story 1.1 adds it.

4. **No auth layer exists.** `User.role` is defined in the schema, but every route today is
   effectively public. Do not assume a request carries an authenticated user until Story 1.1 ships.

5. **`backend/data_models/exceptions/` is stray scaffold debris.** The designated location is
   top-level `backend/exceptions/`. Story 1.1 removes the stray package. Don't treat it as a
   competing convention.

---

## Where code goes

**Backend** — five top-level folders by responsibility. Don't add a sixth for something that fits one:

- `api/` — routers, one file per resource, each with its own `APIRouter` + prefix + tags.
  `api/router.py` is the aggregator only: it `include_router()`s the rest and holds nothing else.
  Handlers stay thin — validate, call a service, return the response model. **No SQLAlchemy queries
  and no business rules in a route handler.**
- `services/` — all business logic, one service per domain area. Registered as providers in
  `container.py` with dependencies injected. Design patterns (Repository, Strategy, State, Observer)
  live here.
- `clients/` — anything reached over a network or driver (`database.py` today; `llm.py` for OpenAI
  later). Constructed by the container, never instantiated ad hoc inside a service.
- `data_models/` — ORM schema only. No business logic.
- `exceptions/` — custom exceptions (top-level; currently absent, create it when first needed).

**Frontend** — respect the existing empty-but-intentional folders: `pages/` (route-level),
`components/` (reusable UI), `services/` (API calls), `types/` (shared types), `config/`.

---

## Language and framework rules

**Python**
- Imports are relative to `backend/` as root (the app runs from inside it). Never `from backend.X import ...`.
- Type hints on every signature, including generators and DI provider functions.
- Route handlers are `async def` with an explicit Pydantic `response_model` — never a bare dict.
- Custom exceptions go in `backend/exceptions/`; no inline `raise Exception(...)`.
- Log through the **injected loguru logger** from the container at every layer — never `print`, never
  a module-level logger built outside DI. Carry identifying context (order id, dish id, ingredient
  name, user id) so a flow can be traced end to end.

**TypeScript**
- `strict`, `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch` are enforced at
  build time — unused vars and non-exhaustive switches fail `pnpm build`, not just lint.
- `isolatedModules: true` — every file independently transpilable; no `const enum`.
- Never read `import.meta.env` in a component; always go through `src/config/config.ts`.

**Config** — `config.yaml` with `${ENV_VAR: default}` placeholders via `utils.load_config`. Not a
`.env`-only setup, not hardcoded values.

---

## Comments and docstrings

Docstrings are the documentation. Inline comments are the exception, not the habit.

**Required:**

- Every method and every function gets a docstring saying what it does, what each argument is, and what it returns. If it returns nothing, say so. If it raises, say what and when.
- Every class gets a docstring at the top of the class saying what it is and what it is for.
- Every module gets a short docstring at the top of the file when the filename alone does not make its purpose obvious.

**Style:**

- **Never use an em dash (—) in a docstring or comment.** Use a comma, a period, or a new sentence.
- Simple English. Short sentences. No long words where a short one works.
- Say what the code does, not how clever it is. No filler, no restating the function name.

**Inline comments:**

- Do not comment between the lines of a method by default. If the docstring says what the method does, the body should be readable without narration.
- Add an inline comment only when the code is genuinely hard to follow: a non-obvious algorithm, a workaround, an ordering that matters, a rule that looks wrong but is correct.
- When you do add one, explain **why**, not what. `# guard against a second cook picking this up mid-transaction` is useful. `# increment the counter` is not.
- Naming a design pattern in a comment is expected and encouraged here, since pattern usage is graded (see Academic context below).

**Python format** (standard triple-quoted docstring):

```python
class OrderService:
    """Handles order creation, item changes, and status transitions."""

    async def cancel_item(self, item_id: int, actor: User) -> OrderItem:
        """Cancel a single order item.

        Args:
            item_id: The order item to cancel.
            actor: The user performing the cancellation. Must be a waiter, cook, or admin.

        Returns:
            The updated order item, now cancelled.

        Raises:
            NotFoundError: If no order item matches item_id.
            InvalidTransitionError: If the item is already cancelled or served.
        """
```

**TypeScript format** (TSDoc, same rules):

```typescript
/**
 * Formats a price for display in the order total.
 *
 * @param cents - The price in whole cents.
 * @returns The price as a string with a currency symbol.
 */
```

---

## Binding architecture invariants

From the architecture spine — these are contracts, not suggestions. Cited by AD number in story ACs.

- **AD-1** DI container is the composition root; every lifecycle-managed resource is a `providers.Resource`.
- **AD-2** One WebSocket endpoint per authenticated session, role-scoped. Every state change emitted
  exactly once, by the service that owns the mutation, under a fixed past-tense `{domain}.{event}` name
  (e.g. `order.item_status_changed`).
- **AD-3** JWT at login as an httpOnly cookie, **8-hour expiry** (a work shift; no refresh-token flow —
  on expiry the user re-logs in). Every route except login/health verified via one shared FastAPI
  dependency. CORS allow-list, never wildcard.
- **AD-4** Alembic owns the schema; every `data_models/` change ships a migration; avoid multi-head
  across parallel branches.
- **AD-6** OrderItem status transitions are **guarded conditional updates** (`WHERE status = <expected>`,
  rowcount-checked). The `in_preparation` transition does status update + stock decrement +
  `StockMovement` insert in **one transaction**. Extended to `RestaurantTable` edits (must be `available`).
- **AD-7** `OrderItem.price_at_add` is stored; Order totals always computed from it over non-cancelled
  items — never a live Dish-price lookup.
- **AD-8** Reject marking a Dish available with zero `RecipeIngredient` rows; reject removing the last
  row while available.
- **AD-11** Cancelling an `in_preparation` OrderItem does **not** reverse its stock deduction. Ingredients
  are treated as already used. No compensating movement is created automatically.
- **AD-12** All OpenAI calls go through a `clients/` adapter behind an interface — never called from `services/`.
- **AD-14** One recipe-suggestion generation in flight per Cook: reject, don't queue. Write only after
  success — no orphaned rows on failure.
- **AD-15** Reject any User update that would leave zero active Admins.
- **AD-16** `Ingredient.current_stock` is **never clamped at zero**, on either the automatic or manual path.

---

## Domain rules worth restating

- `Order.status` (`pending`/`in_preparation`/`ready`) is **derived** from its non-cancelled OrderItems.
  `served` and `closed` are set explicitly. An Order with zero non-cancelled items is `pending`.
- Stock deducts at **transition to `in_preparation`** (prep start), not at order placement.
- `StockMovement` is **append-only** — the audit trail. Never mutate a past row. No code path changes
  `current_stock` without a corresponding movement.
- Low-Stock Alert is a **derived state, not a stored entity** — an Ingredient is in shortage whenever
  stock < threshold. At most one active alert per ingredient; it clears when a movement restores it.
- Permissions are **Role-level only.** No per-resource filtering anywhere: every Waiter sees every
  Table; every Cook sees every chat session. "Current user's items first" is a *sort*, never a filter.
- An Admin sets a new User's **initial password** at creation and can **reset** it later. No
  self-service signup, no email recovery. Passwords are bcrypt-hashed, never logged or returned.
- Tables are **added and edited, never deleted.** Editing is gated on the table being `available`.
- A Recipe Suggestion never writes to a live Dish — Admin confirmation is the only path to the menu.

---

## Testing

**Story 1.0 establishes both harnesses.** Until it lands there is nothing to run.

- Backend: `pytest` + `pytest-asyncio` + `httpx.AsyncClient`, with `conftest.py` providing an async
  client and a throwaway-database session fixture.
- Frontend: `vitest` + `@testing-library/react`, exposed as `pnpm test`.

Every story in `epics.md` is written as Given/When/Then acceptance criteria — those are the tests.

---

## Workflow

- Branches: `feature/<name>` or `fix/<name>`.
- Commits: imperative-mood summary line, no conventional-commit prefixes (`feat:`/`fix:`). A substantive change gets a short wrapped body explaining what and why; trivial ones stay summary-only.
- Everything lands via GitHub PR into `main`; no direct pushes.
- **No CI/CD** (`.github/workflows` absent) and **no linter/formatter configured** on either side —
  nothing gates a merge but review. Don't add lint-suppression comments for rules that don't exist.
- Local dev: `docker compose up`. A native Postgres on this machine also binds 5432 — stop it first
  (`sudo launchctl unload /Library/LaunchDaemons/postgresql-16.plist`) if the port is taken.

---

## Academic context (shapes what "good" means here)

This is the final project for an OOP workshop. **Design and analysis documentation carries roughly
the same weight as the working implementation.** Prefer an explicit, recognizable design pattern over
the shortest path to a feature, and name the pattern in a comment or PR description — that
traceability is graded. Don't add scope beyond the epics to look more impressive; that time is
better spent on design depth.

---

## Maintaining this file

Regenerate when the installed-vs-decided table stops matching the manifests, or when a story lands
that removes one of the silent traps above (Story 1.0 kills traps 2; Story 1.1 kills 1, 3, 4, 5).
Keep it lean — facts an agent can't infer from the code in front of it.

Last Updated: 2026-08-02
