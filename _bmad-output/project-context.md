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
| **Backend** | fastapi, uvicorn[standard], dependency-injector, pyyaml, loguru, sqlalchemy[asyncio], asyncpg, alembic, bcrypt, pyjwt, python-dotenv, pytest + pytest-asyncio + httpx | openai (Story 6.1) |
| **Frontend** | react 19, react-dom, typescript ~5.7.2, vite ^6, @vitejs/plugin-react, vitest + @testing-library/react + @testing-library/user-event, react-router 7.8.0 (Story 1.4), MUI v9 + @mui/icons-material + @emotion/react + @emotion/styled (Story 1.4), @tanstack/react-query v5 (Story 1.4) | none |

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
  main.py            app factory + lifespan; calls exceptions/handlers.py's register_exception_handlers(app)
  container.py       DeclarativeContainer: config, logging, database, auth_service, user_service — all providers
  constants.py       SETTINGS (app name, version, config path)
  config.yaml        ${ENV_VAR: default} interpolation, parsed by utils.load_config
  utils.py           config loader
  entrypoint.sh       Docker CMD: alembic upgrade head, then the app. Never in the lifespan.
  alembic/            async-template migration environment; alembic/versions/ has 2 revisions
  tests/              conftest.py + one test file per module below
  api/router.py      aggregator; include_router()s auth and admin
  api/auth.py        POST /auth/login (sets the JWT httpOnly cookie), GET /auth/me (Story 1.4, the
                     frontend's only way to learn who is logged in across a page reload)
  api/admin.py        Story 1.3's User-management routes, the reference implementation for
                     role-gated routes with declared error responses (see trap 8)
  api/dependencies.py CurrentUserDep (get_current_user) and require_role(*roles) — the shared auth/authz seams
  api/responses.py    error_responses(), shared OpenAPI responses-dict builder
  clients/database.py  SessionDep — AsyncSession from the container's session factory
  data_models/       7 ORM modules + base.py + auth.py + errors.py, the full schema, already written
  services/auth_service.py  login, token issuance/verification, password hashing
  services/user_service.py  Story 1.3's User CRUD, the last-admin lock guard, denial logging
  exceptions/__init__.py    AuthError family (401), ForbiddenError (403), ConflictError family (409), UserNotFoundError (404)
  exceptions/handlers.py    register_exception_handlers(app), the one place new exception families get wired
```

- `data_models/` is complete and mirrors `docs/database-schema.md`: `user.py`, `menu.py`,
  `recipe.py`, `order.py`, `inventory.py`, `ai.py`, `base.py`, plus `auth.py`/`errors.py` for
  request/response schemas. **Do not treat the schema as unwritten.**
- `services/` has `auth_service.py` and `user_service.py`. Every other domain rule in the epics
  still has to be written.
- `api/` has `router.py` (health, mounted inline), `auth.py`, and `admin.py` (Story 1.3, the first
  real domain router and the reference implementation for role-gated routes, see trap 8).
- `alembic/versions/` now holds two revisions: the baseline, and `f1743862f1b1` (case-insensitive
  unique index on username, Story 1.3).

**Frontend, shell and routing skeleton, no domain screens yet (Story 1.4).**

```
frontend/src/
  App.tsx              provider composition root: QueryClientProvider, ConnectionStatusProvider,
                        ThemeModeProvider, RouterProvider (react-router core export, not "/dom",
                        see Testing)
  main.tsx              mounts <App/>, unchanged since Story 1.0
  router.tsx             the route tree (13 IA-surface routes + /login), exported as `routes` so
                        tests build their own createMemoryRouter from the same config
  config/config.ts       import.meta.env access (unchanged)
  config/theme.ts         lightTheme/darkTheme (accent-color override only, everything else stock
                        MUI) + DENSE_ROW_HEIGHT
  types/user.ts           UserRole, CurrentUser (mirrors UserResponse's JSON shape, snake_case)
  services/httpClient.ts   fetch wrapper: credentials "include", ApiError, detail-envelope parsing.
                        Every failure leaves as an ApiError, including an unreachable backend and a
                        timeout, which carry status 0 (see trap 12)
  services/authService.ts  useCurrentUser / useLogin, the only TanStack Query hooks so far
  components/shell/        RequireAuth (route guard), AppShell (app bar + nav + Outlet),
                        AppShellSkeleton (the cold-load stand-in: app bar shape, not a blank page),
                        ThemeModeProvider/ThemeToggle, ConnectionStatusContext/ReconnectingBanner,
                        RowsSkeleton, navigationConfig.ts (ROLE_HOME_PATH/ROLE_NAV_ITEMS/
                        ROLE_PATH_PREFIX, the single source of truth the nav and the guard both read)
  pages/{role}/           one placeholder component per IA surface (just the surface's own title,
                        as the page's h1), real content ships per-surface in its own later story
frontend/
  nginx.conf            the production image's site config (see trap 13)
```

No state management library beyond TanStack Query for server state and React Context/`useState` for
local UI state (theme mode, connection status), matching AD-13. `services/` is not yet organized
per-domain (only `authService.ts` exists); later stories add one file per domain the same way
`user_service.py` did on the backend.

---

## Traps that fail silently

These are the ones that cost hours because nothing errors:

1. **RESOLVED by Story 1.1.** `container.wire()` is now called in `main.py` with
   `modules=["api.auth", "api.dependencies"]`. The live rule from here: every later story
   **appends** its module to that list, **never replaces it**. A silently truncated list is the
   classic version of this bug, and it fails at *request* time rather than import time, so the
   app still starts fine and breaks on first call.

2. **RESOLVED by Story 1.0.** `create_all` is gone from `container.py`. Alembic (async template)
   now owns the schema: `backend/alembic/env.py` resolves the connection URL through
   `utils.load_config` (never hardcoded in `alembic.ini`), and `backend/entrypoint.sh` runs
   `alembic upgrade head` before the API starts in Docker. **Every schema change from here ships
   its own revision** (`alembic revision --autogenerate -m "..."`, inspect it before committing).
   Running the app outside Docker (`uv run python main.py` directly) does **not** run migrations
   for you; run `uv run alembic upgrade head` first, per the README.

3. **RESOLVED by Story 1.1.** `CORSMiddleware` is registered in `main.py` with an explicit
   one-item allow-list from `config.cors.allow_origin` and `allow_credentials=True` (needed for
   the session cookie across ports). **Never widen this to a wildcard** (AD-3).

4. **RESOLVED by Story 1.1, with a sharp edge.** Auth exists, but it is *opt-in per route*.
   `api/dependencies.py` provides `CurrentUserDep`, the one shared seam AD-3 requires. A route
   without it is still fully public, and nothing warns you. Every protected route must declare
   `user: CurrentUserDep`, and it must never re-derive a user from the cookie itself. Story 1.2
   built role enforcement on top of this (see trap 8).

5. **RESOLVED by Story 1.1.** The stray `backend/data_models/exceptions/` package is gone.
   Top-level `backend/exceptions/` is the single designated location, and it now holds the
   `AuthError` family (`InvalidCredentialsError`, `SessionExpiredError`,
   `NotAuthenticatedError`). Each carries its own `detail`; one handler in `main.py` maps any of
   them to a 401. Add new exception types the same way rather than raising inline or building a
   second handler.

6. **Secrets come from `backend/.env`, which is untracked.** `utils.load_config` loads it at
   import (real environment variables still win), and docker-compose passes it through
   `env_file` as optional. A fresh clone with no `.env` still boots, silently falling back to
   `config.yaml`'s published default JWT key, which makes every session forgeable. The app logs a
   startup warning when that happens. Copy `backend/.env.example` to `backend/.env` before the
   first run. **Never commit `.env`, and never put a real secret in `.env.example`.**

7. **The session cookie is `Secure` unconditionally, and v1 is localhost-only.** Browsers exempt
   `http://localhost` from the Secure requirement, so the Docker demo works. Reaching the app
   over a LAN IP or hostname instead returns a 200 on login and then silently drops the cookie,
   with no error anywhere. Accepted scope for v1 (review 2026-08-08); revisit with a real
   cookie-transport setting if the app ever needs to be reached off-box.

8. **RESOLVED by Story 1.3, and now the live pattern every domain router copies.**
   `api/dependencies.py` exports `require_role(*roles)`, layered on `CurrentUserDep` so a request
   is authenticated before it is role-checked. Call it, never pass it bare:
   `Depends(require_role(UserRole.admin))` is correct; `Depends(require_role)` registers without
   error but makes FastAPI read the roles as a query param, silently running zero authorization.
   `ForbiddenError` (a sibling of `AuthError`, not a subclass) maps to 403 via its own handler in
   `main.py`. `api/admin.py` is the reference implementation: one module-level
   `AdminDep = Annotated[User, Depends(require_role(UserRole.admin))]` reused by every route.
   The two obligations Story 1.2 deferred here are both discharged, and both are now standing
   rules: (a) **every route declares the error statuses it can return**, each with a body schema
   (`_errors()` in `api/admin.py`, `ErrorResponse` in `data_models/errors.py`) — these exceptions
   are plain `Exception` subclasses, so FastAPI infers nothing and an undeclared status is simply
   absent from the contract Story 1.4's client builds against; (b) **`api/` stays non-logging and
   services log their own rejections** through the injected loguru logger with the acting user id
   (`actor` is threaded into every `UserService` method for exactly this).

9. **A business rule enforced by a read-then-write in a service is not enforced at all under
   concurrency.** Story 1.3's AD-15 last-admin guard counted active admins in an unlocked
   `SELECT`, so two admins deactivating each other simultaneously both passed and both committed,
   leaving zero active admins and locking user management permanently. Fixed with an id-ordered
   `SELECT ... FOR UPDATE` over the active-admin rows before counting (consistent lock order, so
   concurrent callers serialize instead of deadlocking). **Apply the same shape to every
   invariant of the form "reject if this would leave zero/too few X"** — AD-6's guarded status
   transitions and AD-8's last-recipe-row rule are the same class of problem. AD-5's
   last-write-wins covers ordinary field edits, never an invariant check.

10. **Pydantic's `max_length` counts characters; bcrypt's limit is bytes.** A 72-character
    password of Hebrew or accented text is 144 bytes, passes a `max_length=72` field, and then
    raises `ValueError` out of `hash_password` as an unhandled 500. Password fields use a
    byte-length validator (`_require_hashable_password` in `data_models/user.py`), never a
    character bound. Any future field whose real limit is a byte budget needs the same treatment.

11. **Usernames are case-insensitive and trimmed, enforced in three places that must stay in
    agreement.** `data_models/user.py` strips whitespace and rejects blank-after-strip;
    `UserService.create_user` compares with `func.lower(...)`; `AuthService.authenticate` looks up
    the same way; and a functional `UNIQUE INDEX ON users (lower(username))` (revision
    `f1743862f1b1`) is the final arbiter. Changing any one of these without the others either
    makes an account unreachable at login or lets two confusable accounts exist. Decided
    2026-08-10 during Story 1.3's review, after establishing that nothing in the PRD, epics,
    schema doc, or spine had ever specified username case at all.

12. **A single-page app needs a history fallback in the image, and no test can see that it is
    missing.** Every route below `/` exists only in React Router. Nginx serves literal files, so
    `frontend/nginx.conf` has to answer unmatched paths with `index.html` or a refresh, a bookmark,
    or a pasted link on any surface returns 404 while the app itself looks perfect in dev and green
    in every test. Found by manually opening the Docker stack, not by the 24-test suite that shipped
    with Story 1.4. Two neighbouring rules in that same file: `/assets/` must `try_files $uri =404`
    ahead of the catch-all (otherwise a stale asset request is answered with HTML and a 200), and
    `index.html` must be sent `no-cache` (otherwise a redeploy serves a cached shell pointing at
    asset hashes that no longer exist). **Anything else served by that image, and any future route
    prefix, has to be reconciled with these three blocks.**

13. **Only a 401 means "signed out". Every other failure is a transport problem.** `httpClient`
    turns every failure into an `ApiError`, using **status 0 for "no response ever arrived"**
    (dead network, CORS, or its own `AbortController` timeout), precisely so callers can tell that
    apart from a rejected session. `RequireAuth` redirects to Login only when
    `error instanceof ApiError && error.status === 401`, and offers a Retry for anything else.
    Treating a bare `isError` as "not logged in", which is what shipped first, silently ejects a
    working session to the Login screen on a momentary blip, and `retry: false` on `useCurrentUser`
    means there is not even one retry to hide it. **Any future query whose failure drives navigation
    or an auth decision needs the same discrimination**, not a bare `isError`.

14. **`RequireAuth`'s Role-prefix check is a navigation affordance, not a security boundary.**
    `location.pathname.startsWith(ROLE_PATH_PREFIX[user.role])` keeps a Waiter from landing on an
    Admin URL, but it is plain prefix matching (so `/adminfoo` also matches `/admin`) and it runs
    entirely in the browser, where anyone can edit it. **The backend's `require_role` is the only
    real enforcement** (trap 8). As later stories put real data behind these surfaces, every one of
    them still needs its own role-gated endpoint; never treat "the nav does not show it" or "the
    guard redirected" as protection.

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
- `data_models/` — ORM schema only. No business logic. **Clarified 2026-08-08:** `api/` may import
  type-level names from here (Pydantic schemas, an enum like `UserRole`, an ORM class used only as
  a type annotation) for declaration purposes; querying, mutation, and domain rules still must stay
  in `services/`.
- `exceptions/` — top-level, holds the `AuthError` family plus `ForbiddenError` (a sibling, not a
  subclass, since it maps to 403 on an already-verified identity vs. 401). Add new exception types
  the same way rather than raising inline or building a second handler.

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

**Exception: test files.** Everything below applies to application code. Inside `tests/`
(backend) and `*.test.tsx` / test-support files (frontend), skip docstrings entirely and
structure each test with `# Arrange` / `# Act` / `# Assert` comments instead. See Testing below.

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

**Both harnesses are live as of Story 1.0.** Run `uv run pytest` from `backend/` and `pnpm test`
from `frontend/`.

- Backend: `pytest` + `pytest-asyncio` + `httpx.AsyncClient`, declared as a PEP 735
  `[dependency-groups] dev` group (never main `dependencies` — the Dockerfile runs
  `uv sync --no-dev`). `backend/tests/conftest.py` provides `client` (async HTTP client over the
  app, entering the real lifespan) and `db_session` (bound to a throwaway database migrated by
  `alembic upgrade head`, not `create_all`, so the suite continuously proves the migration chain
  works). Fixture names: `client`, `db_session`, `migrated_database` (session-scoped),
  `empty_database`. Async fixtures use `@pytest_asyncio.fixture`, never plain `@pytest.fixture`
  (pytest-asyncio 1.x removed the `event_loop` fixture, don't define one).
- Frontend: `vitest` + `@testing-library/react` + `jest-dom`, exposed as `pnpm test`. Configure
  vitest via `defineConfig` from `"vitest/config"` (not `"vite"` — that import doesn't type the
  `test` key and fails the strict build).
- **Test files do not use docstrings.** Every test method is organized with plain
  `# Arrange` / `# Act` / `# Assert` comments instead (omit a section with nothing in it). This is
  a deliberate carve-out from the "Comments and docstrings" rule below, scoped to `tests/` and
  `*.test.tsx` files only — everything else still requires docstrings.
- **`db_session` truncates every model table after each test** (Story 1.1). Rows must be
  committed for the app under test to see them over its own connection, so isolation is
  truncation afterwards, not a rollback. Write tests freely; they will not leak into the next
  test. `alembic_version` is untouched, so the migration state survives.
- Hash passwords in tests through `AuthService.hash_password`, never `bcrypt.hashpw` directly, so
  account creation and login can never diverge on cost or salt settings.
- No `pytest-xdist` and no CI pipeline exist yet, so the session-scoped test database fixture has
  no per-worker isolation. Fine today; revisit if parallel test execution is introduced.
- **`frontend/src/setupTests.ts` calls `@testing-library/react`'s `cleanup()` in an explicit
  `afterEach` (Story 1.4).** RTL's own auto-cleanup only registers itself if it detects a global
  `afterEach`, and `vite.config.ts`'s `globals: false` deliberately does not provide one (every test
  file imports `describe`/`it`/`expect` itself). Without the explicit call, a second `it()` in the
  same file that renders another component leaves the first render's DOM in place, so queries like
  `getByRole` start matching more than one element. Any new test file with more than one `render()`
  call across its `it()` blocks needs nothing extra, `setupTests.ts` already covers it.
- **Import `RouterProvider` from `"react-router"`, never `"react-router/dom"` (Story 1.4).** The
  `/dom` subpath's `RouterProvider` is a thin wrapper that also passes `flushSync: ReactDOM.flushSync`
  to the real one; under this project's React 19.2.6 + react-router 7.8.0 + jsdom/Vitest combination,
  that wrapper reproducibly breaks the Router context, `useLocation`/`useNavigate`/`NavLink` anywhere
  in the tree then throw "may be used only in the context of a `<Router>` component," even outside
  tests (verified with a two-line repro, not a testing-only quirk). Everything else routing-related
  (`createBrowserRouter`, `createMemoryRouter`, `NavLink`, `Navigate`, `Outlet`, `useLocation`,
  `useNavigate`) already lives on the core `"react-router"` export, so there is no reason to reach for
  `/dom` at all in this codebase.

- **Mocking a service in every test hides the wiring between that service and its callers
  (Story 1.4 review).** Story 1.4 shipped with `authService` `vi.mock`ed in all four component test
  files, so `retry: false`, the login invalidation, and the query-to-guard handover never actually
  ran anywhere. `frontend/src/appIntegration.test.tsx` is the counterweight and the pattern to copy:
  **one file per feature that mocks only `fetch`** and drives the real hooks, real router and real
  guard end to end. Component tests may keep mocking the service; at least one test must not.
- **A regression test that cannot fail is worse than none, so make it fail first.** Two traps hit
  during the same review. A stubbed `fetch` that resolves in a microtask lands before React
  re-renders, so any ordering bug it is meant to catch is invisible, use a real `setTimeout` delay
  when the timing *is* the thing under test. And an assertion derived from the DOM (reading tab
  order out of `getAllByRole("link")` and then asserting tab order) is a tautology, derive expected
  values from the config the code reads, e.g. `ROLE_NAV_ITEMS`. **Before trusting a new regression
  test, reintroduce the bug and watch it go red.** Doing exactly that is what proved one of the
  review's own "high severity" findings was a false positive.

Every story in `epics.md` is written as Given/When/Then acceptance criteria, those are the tests.

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
that removes one of the silent traps above (Story 1.0 killed trap 2; Story 1.1 kills 1, 3, 4, 5).
Keep it lean — facts an agent can't infer from the code in front of it.

**2026-08-08 patch (Story 1.0 landed, PR #121 merged to main):** installed-vs-decided table,
current-state tree, trap 2, and Testing updated in place rather than a full regenerate. Everything
else in this file is still as of 2026-08-02 and should be checked against the code before being
trusted for later stories.

**2026-08-08 patch (Story 1.1 code review):** traps 1, 3, 4 and 5 marked resolved and rewritten as
the live rules they became; traps 6 and 7 added for the new `.env` secret mechanism and the
localhost-only cookie scope; installed-vs-decided table updated (bcrypt, pyjwt and python-dotenv
are installed, only openai is still pending); Testing updated for the new per-test truncation and
the `AuthService.hash_password` seam.

**2026-08-08 patch (Story 1.2, PR #124 merged to main):** current-state tree brought up to date
(`api/auth.py`, `api/dependencies.py`, `services/auth_service.py`, `exceptions/` now listed; no
more "predates Story 1.1" warning). Trap 8 added for `require_role`/`ForbiddenError`: built, wired
to a 403 handler, but not yet used by any route, with two review-deferred obligations
(OpenAPI 403 documentation, service-layer denial logging) that land on the story that adds the
first protected route. "Where code goes" updated for the architecture spine's same-day
type-vs-behaviour clarification on `api/` importing from `data_models/`, and for `exceptions/`
now existing rather than being a placeholder. No new packages landed in Story 1.2; the
installed-vs-decided table is unchanged. Next story per sprint-status.yaml: **1.3, Admin Manages
User Accounts** (backend-only scope expected, matching 1.0-1.3's pattern; the Users screen UI
depends on Story 1.4's shell/routing/MUI setup, which has not landed).

**2026-08-10 patch (Story 1.3 + its code review):** trap 8 rewritten as resolved, since Story 1.3
mounted the first `require_role` route and discharged both of Story 1.2's deferred obligations;
`api/admin.py` named as the reference implementation. Traps 9, 10 and 11 added from the review,
all three generalizable beyond this story: read-then-write invariant checks need row locks,
byte-vs-character bounds on password fields, and the three-places-must-agree username
normalization rule. Current-state tree updated for `services/user_service.py`, `api/admin.py`, and
the second Alembic revision. Testing note: the suite is 107 tests; `tests/conftest.py`'s `client`
fixture uses an `https` base URL because the session cookie is `Secure` and httpx, unlike a
browser, has no localhost exemption.

**2026-08-10 patch (Story 1.4, application shell/routing/nav):** installed-vs-decided table updated,
react-router, MUI (+icons +emotion), and @tanstack/react-query all landed, nothing left pending on
the frontend side. `GET /api/auth/me` added to `api/auth.py`, not named by any FR/AC but required
infrastructure: the frontend's only way to learn who is logged in and what Role they hold across a
page reload, since the session cookie is httpOnly. Backend and frontend current-state trees both
rewritten (frontend was "scaffold only," now has the full shell: routing, per-role nav, theme,
Skeleton/Reconnecting scaffolds; backend tree also caught up to Story 1.3's `admin.py`/
`user_service.py`/`exceptions/handlers.py`, which the prior patch missed). Two new Testing entries:
`setupTests.ts` needs an explicit `afterEach(cleanup)` because `globals: false` defeats
`@testing-library/react`'s own auto-cleanup detection; `RouterProvider` must come from `"react-router"`
core, never `"react-router/dom"` (its `flushSync` wrapper reproducibly breaks Router context under
this project's React 19.2.6 + react-router 7.8.0 combination). Backend suite is 109 tests.

**2026-08-11 patch (Story 1.4 code review):** three traps added, all generalizable beyond this
story. Trap 12: a single-page app needs an nginx history fallback in the image, plus an `/assets/`
404 guard and a `no-cache` on `index.html`, and no test in the suite can see when it is missing.
Trap 13: only a 401 means "signed out", so `httpClient` now reports an unreachable backend as
`ApiError` with **status 0** and `RequireAuth` discriminates on it instead of redirecting on any
error. Trap 14: the guard's Role-prefix check is a navigation affordance, not a security boundary,
the backend's `require_role` remains the only enforcement. Two Testing entries added, on the
service-mocking blind spot (with `appIntegration.test.tsx` as the pattern to copy) and on proving a
regression test can actually fail before trusting it. Frontend current-state tree updated for
`AppShellSkeleton` and `nginx.conf`. AC4's wording was amended to key the dark default off the Cook
Role rather than the Kitchen Display surface, matching the implementation. Suites are now **111
backend and 34 frontend tests**.

Last Updated: 2026-08-11
