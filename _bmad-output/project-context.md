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

**Backend, layered and wired. Epic 2's authoring domain is complete: auth, users, real-time push, inventory, menu (including Recipe Ingredient CRUD), and Restaurant Tables. Epic 3 (Table Service & Order Taking) is now open: Story 3.1 landed the first `orders` route, opening a Table into a new Order.**

```
backend/
  main.py            app factory + lifespan; calls exceptions/handlers.py's register_exception_handlers(app)
  container.py       DeclarativeContainer: config, logging, database, connection_registry, auth_service,
                     user_service, inventory_service, menu_service, table_service, order_service,
                     realtime_service
  constants.py       SETTINGS (app name, version, config path)
  config.yaml        ${ENV_VAR: default} interpolation, parsed by utils.load_config
  utils.py           config loader
  entrypoint.sh       Docker CMD: alembic upgrade head, then the app. Never in the lifespan.
  alembic/            async-template migration environment; alembic/versions/ still has 3 revisions.
                     Neither Story 2.3 nor 2.4 needed one, both ORM schemas already fit
  tests/              conftest.py + one test file per module below
  api/router.py      aggregator; include_router()s auth, admin, inventory, menu, tables, orders, websocket
  api/auth.py        POST /auth/login (sets the JWT httpOnly cookie), GET /auth/me (Story 1.4, the
                     frontend's only way to learn who is logged in across a page reload)
  api/admin.py        Story 1.3's User-management routes, the reference implementation for
                     role-gated routes with declared error responses (see trap 8)
  api/inventory.py    Story 2.1: POST /api/inventory/ingredients, the first route to permit more
                     than one Role (admin, warehouse_manager). Story 2.3 added GET on the same two
                     Roles (InventoryReadDep); Story 2.5 widened InventoryReadDep to admin,
                     warehouse_manager, cook (a Cook needs Ingredient names to render a Dish's
                     recipe); Story 4.3 should extend it further, not duplicate it
  api/menu.py         Story 2.2: POST /categories, POST /dishes, PATCH /dishes/{id}, admin-only.
                     Story 2.3 added GET /categories, GET /dishes, and Recipe Ingredient CRUD at
                     /dishes/{dish_id}/recipe-ingredients (GET/POST/PATCH/DELETE). Story 2.5 split
                     a new MenuReadDep (admin, cook) off the three GET routes; every write route
                     stays on the original MenuDep (admin-only), unchanged
  api/tables.py       Story 2.4: GET /api/tables, POST /api/tables, PATCH /api/tables/{id},
                     admin-only. Note the collection paths have NO trailing slash, matching the
                     sibling routers; a trailing slash shipped first and was corrected in review.
                     Story 3.1 split GET onto a new TablesReadDep (admin, waiter); POST/PATCH stay
                     on the original admin-only TablesDep, unchanged
  api/orders.py       Story 3.1: POST /api/orders/tables/{table_id}/open, waiter-only (the first
                     route in the project gated to exactly one non-admin Role, no admin fallback)
  api/websocket.py    Story 1.5: the single /api/ws endpoint, Role-scoped, cookie-authenticated,
                     periodic session re-verification while the connection stays open
  api/dependencies.py CurrentUserDep (get_current_user) and require_role(*roles) — the shared auth/authz seams;
                     also CurrentUserWsDep/verify_ws_origin, the WebSocket-route counterparts (Story 1.5)
  api/responses.py    error_responses(), shared OpenAPI responses-dict builder
  clients/database.py  SessionDep, session_scope() — a short-lived-session context manager any non-request
                     caller (a WebSocket handshake, a periodic re-verification tick) uses directly (see trap 15)
  clients/websocket.py ConnectionRegistry (Story 1.5): tracks open sockets keyed by user id (not just Role),
                     closing a User's prior socket on a new one; broadcast_to_roles() targets several Roles
                     in one emission
  data_models/       7 ORM modules + base.py + auth.py + errors.py, the full schema, already written.
                     recipe.py, menu.py and order.py also hold their own Pydantic request/response
                     schemas colocated with their ORM class, matching user.py's shape. menu.py owns
                     _INT4_MAX; recipe.py and order.py import it from there rather than redeclaring
  services/auth_service.py  login, token issuance/verification, password hashing
  services/user_service.py  Story 1.3's User CRUD, the last-admin lock guard, denial logging
  services/inventory_service.py  Story 2.1: Ingredient creation, case-insensitive duplicate check.
                     Story 2.3 added list_ingredients
  services/menu_service.py  Story 2.2: Category/Dish creation and edits, AD-8's availability gate.
                     Story 2.3 added list_categories/list_dishes, Recipe Ingredient CRUD, AD-8's
                     second half, a unit-mismatch guard, and _lock_dish (see trap 9)
  services/table_service.py  Story 2.4: Table creation/listing and the guarded-UPDATE edit path
                     (see trap 18)
  services/order_service.py  Story 3.1: open_table, the second guarded-UPDATE application (AD-6),
                     with its read step factored into a private _get_table seam so a race test can
                     monkeypatch it, mirroring TableService.get_table's role in trap 18's own test
  services/realtime_service.py  Story 1.5: thin wrapper over ConnectionRegistry so api/ only ever
                     calls into services/ (AD-1); broadcast(roles, event, payload). Still has NO
                     producers: no service emits anything yet (see Domain rules)
  exceptions/__init__.py    AuthError family (401), ForbiddenError (403), ConflictError family (409),
                     NotFoundError family (404, one shared base since Story 2.3, see trap 17)
  exceptions/handlers.py    register_exception_handlers(app); exactly four handlers, one per family
```

- `data_models/` is complete and mirrors `docs/database-schema.md`: `user.py`, `menu.py`,
  `recipe.py`, `order.py`, `inventory.py`, `ai.py`, `base.py`, plus `auth.py`/`errors.py` for
  request/response schemas. **Do not treat the schema as unwritten.**
- `services/` has `auth_service.py`, `user_service.py`, `inventory_service.py`, `menu_service.py`,
  `table_service.py`, and `realtime_service.py`. Every other domain rule in the epics still has to
  be written.
- `api/` has `router.py` (health, mounted inline), `auth.py`, `admin.py` (Story 1.3, the reference
  implementation for role-gated routes, see trap 8), `inventory.py` (2.1/2.3), `menu.py` (2.2/2.3),
  `tables.py` (2.4), and `websocket.py` (Story 1.5).
- `alembic/versions/` still holds three revisions: the baseline, `f1743862f1b1` (case-insensitive
  unique index on username, Story 1.3), and `daca523f69f5` (the same fix applied to
  `Ingredient.name`, Story 2.1, see trap 11). Stories 2.2, 2.3 and 2.4 all needed none.
- **Every `ConflictError`/`NotFoundError` subclass now lives in one family with one handler each.**
  Adding a new 404 means subclassing `NotFoundError` and nothing else; forgetting to subclass it
  makes the error a silent 500, which `tests/test_migrations.py` now guards against.

**Frontend, shell/routing plus a live real-time transport, and the first five real domain screens (Menu Management with dish/category creation, Tables setup, Cook's read-only Dishes catalog, Ingredients, and the Waiter's Tables grid). The other 8 IA surfaces are still placeholders.**

```
frontend/src/
  App.tsx              provider composition root: QueryClientProvider, ThemeModeProvider,
                        RouterProvider (react-router core export, not "/dom", see Testing).
                        ConnectionStatusProvider no longer sits here (Story 1.5): RealtimeProvider
                        renders it internally, further down the tree, see below
  main.tsx              mounts <App/>, unchanged since Story 1.0
  router.tsx             the route tree (13 IA-surface routes + /login), exported as `routes` so
                        tests build their own createMemoryRouter from the same config
  config/config.ts       import.meta.env access (unchanged)
  config/theme.ts         lightTheme/darkTheme (accent-color override only, everything else stock
                        MUI) + DENSE_ROW_HEIGHT
  types/user.ts           UserRole, CurrentUser (mirrors UserResponse's JSON shape, snake_case)
  types/menu.ts           Unit, Category, Dish, RecipeIngredient (Story 2.3)
  types/inventory.ts      Ingredient (Story 2.3)
  types/table.ts          TableStatus, Table (Story 2.4)
  types/order.ts          OrderStatus, Order (Story 3.1)
  services/httpClient.ts   fetch wrapper: credentials "include", ApiError, detail-envelope parsing.
                        Every failure leaves as an ApiError, including an unreachable backend and a
                        timeout, which carry status 0 (see trap 12)
  services/authService.ts  useCurrentUser / useLogin
  services/menuService.ts  Story 2.3: categories/dishes/recipe-ingredient hooks; Story 2.6:
                        useCreateCategory / useCreateDish (payload types private to this file,
                        matching tableService.ts's precedent)
  services/inventoryService.ts  Story 2.3: useIngredients; Story 2.6: useCreateIngredient
                        (INGREDIENTS_QUERY_KEY promoted to a module constant)
  services/tableService.ts  Story 2.4: useTables / useCreateTable / useUpdateTable. TABLES_QUERY_KEY
                        exported (Story 3.1) so orderService.ts's mutation can invalidate the same
                        cache key without a second copy of ["tables"]
  services/orderService.ts  Story 3.1: useOpenTable, invalidates onSettled (not onSuccess only),
                        matching useUpdateTable's own precedent, a lost race needs the same refresh
                        a rejected edit does
  components/menu/DishRecipeEditor.tsx  Story 2.3: the per-dish recipe editor (first domain
                        component folder outside components/shell/)
  components/shell/        RequireAuth (route guard, now wraps AppShell in RealtimeProvider),
                        AppShell (app bar + nav + Outlet), AppShellSkeleton (the cold-load
                        stand-in: app bar shape, not a blank page), ThemeModeProvider/ThemeToggle,
                        ConnectionStatusContext/ReconnectingBanner, RealtimeProvider (Story 1.5:
                        owns the single WebSocket connection, drives ConnectionStatusContext with
                        real state, capped exponential backoff reconnect, exposes useRealtime()'s
                        subscribe(event, handler) for later stories to consume push events),
                        RowsSkeleton, navigationConfig.ts (ROLE_HOME_PATH/ROLE_NAV_ITEMS/
                        ROLE_PATH_PREFIX + canRoleVisit(), the single source of truth the nav and
                        the guard both read; Story 2.6 made reachability derive from ROLE_NAV_ITEMS
                        so Admin's cross-prefix Ingredients grant cannot drift from its nav entry)
  pages/{role}/           placeholder components for the 8 IA surfaces that have not shipped yet
                        (just the surface's own title as the page's h1). Five are now real:
                        admin/MenuManagementPage.tsx (Story 2.3; Story 2.6 added the always-visible
                        "+ New dish" form and an inline "+ New category" reveal on its Category
                        picker, no dialog), admin/TablesSetupPage.tsx (Story 2.4), cook/DishesPage.tsx
                        (Story 2.5, strictly read-only, groups every Dish by Category, resolves
                        Recipe Ingredient lines to names via useIngredients()),
                        warehouse/IngredientsPage.tsx (Story 2.6, replacing Story 1.4's placeholder:
                        an "Add ingredient" form plus a dense-row list, deliberately no shortage
                        sorting/highlighting/detail-drill-down, that scope belongs to Epic 4's Story
                        4.3), and waiter/TablesPage.tsx (Story 3.1: the Tables grid, one tile per
                        Table with its status badge, only an `available` tile is clickable, opens
                        the Table into a new Order and navigates to its still-placeholder detail
                        page), each with its own *.test.tsx alongside.
                        waiter/TableOrderDetailPage.tsx (`/waiter/tables/:tableId`) is still a
                        placeholder, deliberately: Story 3.1's scope note ruled it out, its real
                        content (add-dish form, Order Item list) is Story 3.2/3.3+ territory
frontend/
  nginx.conf            the production image's site config (see trap 13)
```

No state management library beyond TanStack Query for server state and React Context/`useState` for
local UI state (theme mode, connection status), matching AD-13. `services/` is now organized
per-domain (`authService`, `menuService`, `inventoryService`, `tableService`, `userService`), the
same way the backend's `services/` is; later stories add one file per domain.

**The shape every new domain screen should copy** (established by 2.3, corrected by 2.4's review):

- Every query hook sets `retry: false`. The app-level `QueryClient` sets no default, so TanStack's
  3 retries otherwise turn a 401/403/404 into four requests and a multi-second wait.
- A list query handles **four distinct states**: loading, error (with a Retry action), empty, and
  loaded. Collapsing error into empty makes a failed fetch render as an authoritative "there is
  nothing here", which is trap 13's reasoning applied to data rather than auth.
- **Every mutation renders its own `isError`.** A mutation whose failure is never displayed is the
  single most repeated defect in this codebase's reviews.
- Mutations that can be rejected because the caller's copy is stale invalidate `onSettled`, not
  `onSuccess`: a 409 is exactly when the row most needs refreshing.
- Inline editors use **controlled** inputs that resync from the server, but **never while the field
  is dirty**, or a background refetch silently overwrites what the user is typing.
- **Never diff a form against cached data to decide what to send.** Send the fields; let the server
  decide what changed. Diffing against a stale cache produces an empty payload, so no request is
  sent and the row looks saved while the server still holds something else (Story 2.4 review).
- Parse numeric inputs explicitly. `Number("abc")` is `NaN`, which `JSON.stringify` serializes as
  `null`, and a nullable backend field reads that as "not provided" and half-applies the update
  (see trap 19).
- A disabled control's reason must be **visible text**, not only a `Tooltip`: tooltips never appear
  on touch or keyboard-primary interaction.
- **A page driven by more than one independent query must combine loading/error across all of
  them, not just the "main" one.** Story 2.5's `DishesPage` originally wired up only `useDishes()`'s
  `isLoading`/`isError`, leaving `useCategories()`/`useIngredients()` silent. Reproduced directly:
  with dishes succeeding and categories failing, the page rendered only its heading, no error, no
  empty state, nothing. `isLoading`/`isError` must be OR'd across every query the page depends on
  to render anything meaningful, and Retry must refetch all of them, not just one.
- **A form whose picker is populated by a query must not render until that query settles.** Rendering
  it anyway gives an empty picker and a permanently disabled submit with no visible reason — the
  same silent-failure class as the bullet above, one layer in (Story 2.6 review).
- **A submit handler re-checks its full submit predicate, never a subset of it.** The disabled button
  is not authoritative: Enter submits a form regardless. Every check the handler omits is a request
  that can ship with a blank required field or duplicate one already in flight (Story 2.6 review).
- **An inline reveal nested inside another form needs its own Enter handling**, or the outer form's
  implicit submit steals the keypress and discards what the user typed in the reveal (Story 2.6).
- **A mutation whose caller immediately selects the created row seeds the cache in `onSuccess`
  before invalidating.** Invalidation only *schedules* a refetch, so selecting the new id first
  leaves a picker holding a value with no matching option until the refetch lands (Story 2.6).
- **If a story's AC names a Role, verify that Role can actually reach the screen.** Backend
  permission and UI reachability are separate systems: `InventoryWriteDep` permitted Admin from
  Story 2.1, but the route guard redirected Admin away until Story 2.6's review caught it. Route
  reachability is derived from `ROLE_NAV_ITEMS` via `canRoleVisit`, so granting a Role a
  cross-prefix surface means adding the nav entry, never maintaining a second list.
- **Path authorization matches on segment boundaries, and a nav-derived grant is exact.**
  `startsWith(prefix)` alone lets `/admin` match a future `/administration`, and
  `startsWith(navPath)` hands out the whole subtree — that is how Story 2.6's first fix silently
  gave Admin `/warehouse/ingredients/:ingredientId`. Compare `=== p || startsWith(p + "/")` for a
  subtree, and `=== p` for a single surface. Both bugs were invisible: no route matched the widened
  patterns *yet*, so nothing failed, and the next route named as a textual extension of an existing
  one would have been granted with no code change and no test failure (Story 2.6 second review).
- **When a fix contradicts a shipped AC, amend the AC in the same story rather than leaving the
  contradiction.** Story 2.6's Admin nav entry violated Story 1.4's AC2 as literally worded; the AC
  was reworded by correct-course in `epics.md` and `EXPERIENCE.md`, with the reasoning recorded
  inline. Leaving it would have left a later reader reconciling the epics against the code with no
  audit trail on the epics side.

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
    **Reused verbatim by Story 2.1 for `Ingredient.name`** (revision `daca523f69f5`), so this is
    now a two-instance precedent, not a username-only quirk. `Category.name` (Story 2.2)
    deliberately does **not** get this treatment: no epics AC or UX doc pairs category names into
    the case-insensitive-duplicate convention, so it stays plain case-sensitive `unique=True`. Do
    not assume every future `unique` string column needs the functional-index treatment, check the
    epics/UX docs for that field specifically first.

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

15. **A `yield` dependency on a `@websocket` route stays open for the connection's entire
    lifetime, not just one request.** `get_session_ws` (Story 1.5's first draft) was shaped like
    the REST `get_session`, so a session opened per-connection instead of per-query, pinning one
    pooled database connection for as long as the socket stayed open. Confirmed empirically: 6
    open sockets checked out 6 pooled connections, released only on disconnect, against a default
    `pool_size=5` + `max_overflow=10`, so the 16th concurrent device would exhaust the pool and
    block every REST request. Fixed with `clients/database.py`'s `session_scope()`, a context
    manager any non-request caller (a WebSocket handshake, `api/websocket.py`'s periodic
    re-verification tick) opens and closes around one query, never around the connection's
    lifetime. **Any future long-lived connection (a background task, a second WebSocket route)
    must use `session_scope()`, never a `yield` dependency shaped for a request/response cycle.**

16. **A `Numeric`/`Integer` column needs a matching Pydantic bound, or an out-of-range value
    500s instead of 422ing.** Hit twice, both from code review, not from writing the story fresh.
    Story 2.1: `Ingredient.min_stock_threshold`/`current_stock` (`Numeric(10, 3)`) had no
    `max_digits`/`decimal_places`, so a value with more digits than the column allowed reached
    Postgres and raised an unhandled `asyncpg.NumericValueOutOfRangeError`. Story 2.2: `Dish.price`
    got the `Numeric(8, 2)` bound applied proactively from that lesson, but `category_id`/
    `prep_time_minutes` (plain `Integer`, i.e. int4) had no upper bound at all, and a value beyond
    Postgres's int4 range raised `asyncpg.DataError: value out of int32 range` the same way.
    **Every `Decimal` field needs `Field(max_digits=..., decimal_places=...)` matching its
    `Numeric(p, s)` column exactly; every plain-`Integer`-backed `int` field needs `Field(le=2_147_483_647)`
    unless the column is `BigInteger`.** Check this for every new request schema, do not wait for
    review to catch it a third time.

17. **RESOLVED by Story 2.3.** The `*NotFoundError` types now share one `NotFoundError(Exception)`
    base with a single handler, the same way `ConflictError` covers every 409. Story 2.3 crossed
    the fourth-instance threshold this trap named and did the refactor. The live rule from here:
    **a new 404 type subclasses `NotFoundError` and nothing else**, no new handler, no
    registration. Forgetting to subclass it does not fail loudly, it makes that error an
    unhandled 500, so `tests/test_migrations.py` carries an assertion that every class whose name
    ends in `NotFoundError` inherits the base.

18. **A rule of the form "only allow this while the row is in state X" must be one guarded
    `UPDATE`, never a read-then-write.** Story 2.4's Table edit is the reference implementation:
    `UPDATE ... WHERE id = ? AND status = 'available'`, with `rowcount == 0` meaning "rejected"
    (`TableService.update_table`). Reading the row, checking `.status` in Python, and then writing
    is the version that looks correct and silently permits the edit when someone changes the row in
    between. Two related sharp edges found in the same review:
    (a) **an early return for "nothing actually changed" skips the guard.** Story 2.4 shipped
    `if not changed_fields: return table`, which answered 200 for a no-op edit against an *occupied*
    table, reproduced against a live database. Any short-circuit before the guarded write has to
    re-check the state condition itself.
    (b) **a test that sets the row to the blocking state before the request starts proves nothing.**
    That is the plain "already in state X" case, and a naive read-then-write passes it identically.
    A real test has to change the state *between* the service's read and its write (patch the
    read method to commit the change from a second connection on its way out). See Testing.
    This generalizes AD-6's OrderItem transitions and is distinct from trap 9: use a guarded
    `UPDATE` when one row's own column gates its own write, and `SELECT ... FOR UPDATE` when the
    invariant spans multiple rows or multiple write paths (AD-8's `_lock_dish`).

19. **`Number()` on a form field, plus a nullable backend field, equals a silent partial write.**
    `Number("abc")` is `NaN`, and `JSON.stringify` serializes `NaN` as `null`. A Pydantic
    `int | None` field guarded by `if payload.x is not None` cannot tell an explicit `null` from an
    omitted field, so the null is skipped and the *other* fields in the same request are applied,
    returning 200. Reproduced in Story 2.4: `{"table_number": null, "capacity": 8}` answered 200
    having changed only the capacity, so the Admin believed both saved. Also note `Number("")` and
    `Number(" ")` are both `0`, so a non-empty check is not a validity check. **Fix both ends:**
    parse and validate the field in the browser before sending (never coerce with bare `Number()`),
    and reject an explicit `null` server-side rather than treating it as absent.

20. **`await db.rollback()` expires every object in the session, including `actor`.** Reading
    `actor.id` in a log line *after* the rollback triggers an implicit lazy load with no greenlet
    context to run it in, raising an unhandled `MissingGreenlet`, so the 409 the handler meant to
    return becomes a 500. Always log **before** rolling back. This bit four `IntegrityError`
    handlers across `TableService`, `MenuService` (twice) and `InventoryService`; all four are
    fixed, but the shape is easy to reintroduce because **no test reaches these branches**: a
    duplicate-check-before-insert always wins in a single-threaded test, so the handler only runs
    under a genuine concurrent race in production.

21. **Neither `pnpm test` nor a routine `npx tsc -b` run gets exercised against a fresh Docker
    image, so a build-breaking TypeScript error can sit in the tree for stories at a time.**
    `IngredientsPage.tsx`'s `handleCreate` guard (`unit === ""`) had been narrowed unreachable by
    the `canSubmit` expression a few lines above (a `const`-binding control-flow narrowing quirk:
    comparing `unit !== ""` once in an `&&` chain persists the narrowed type for the rest of the
    function, so the later `unit === ""` compares `Unit` against a literal it can no longer be).
    `npx tsc -b` reports it correctly whenever run, but Story 2.6 never ran a `docker compose build`
    after landing it, and no CI exists to run one automatically (see Workflow). It broke
    `docker compose build frontend` outright (`pnpm build` runs `tsc -b && vite build`, so a type
    error there fails the whole image, not a warning), and only surfaced when Story 3.1 needed a
    fresh image built. Fixed with `!unit` instead of the literal comparison (no narrowing
    ambiguity, `Unit` is always a non-empty string when set). **Run `npx tsc -b` as a matter of
    course before considering a frontend story done, not only `pnpm test`, since vitest never
    typechecks.**

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
  row while available. **Both halves are now built** (first in Story 2.2's
  `MenuService.update_dish`/`_reject_if_recipe_empty`, second in Story 2.3's
  `remove_recipe_ingredient`). The two halves guard the same invariant from opposite directions and
  would otherwise interleave, so both take the same `_lock_dish` row lock (trap 9). Story 2.3 also
  added a rule AD-8 does not state but Epic 5 depends on: **a Recipe Ingredient line's unit must
  match its Ingredient's own unit**, since nothing in this system converts between units and a
  mismatch would make automatic deduction subtract the wrong amount silently.
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
- Tables are **added and edited, never deleted.** Editing is gated on the table being `available`,
  enforced by a guarded conditional `UPDATE` (trap 18), and the Tables setup screen has no delete
  affordance anywhere by design (PRD Non-Goals). **RESOLVED by Story 3.1.** `GET /api/tables` now
  also permits `UserRole.waiter` via a new `TablesReadDep` (mirrors `MenuReadDep`/`InventoryReadDep`'s
  split), closing the gap this bullet used to flag as deferred to Epic 3. `POST`/`PATCH` stay on the
  original admin-only `TablesDep`, unchanged.
- **Opening a Table into an Order is the second guarded-UPDATE application (Story 3.1, AD-6),
  and the first route in the project scoped to exactly one non-admin Role with no admin
  fallback.** `OrderService.open_table` follows `TableService.update_table`'s exact shape:
  `UPDATE restaurant_tables SET status = 'occupied' WHERE id = :id AND status = 'available'`,
  rowcount-checked, only inserting the new `Order` (status `pending`, zero items) once that
  UPDATE succeeds, both writes committed together. `reserved` is treated identically to
  `occupied`, the guarded UPDATE cannot and does not need to tell them apart.
- **`RealtimeService` has no producers yet.** The transport is live (Story 1.5) and
  `useRealtime()`'s `subscribe(event, handler)` exists on the frontend, but no service emits any
  event, so nothing in the UI updates from another user's action, only from its own mutations or a
  window-focus refetch. AD-2 governs the naming when the first producer lands. Story 2.4's AC4
  ("re-enable the moment the table returns to available") is the first AC this shortfall leaves
  partially unmet, deferred to Epic 3 by decision (see `deferred-work.md`). **Any story whose AC
  says "live", "instantly", or "the moment" needs to check whether a producer exists yet.**
- A Recipe Suggestion never writes to a live Dish — Admin confirmation is the only path to the menu.
- A newly created Dish is **unconditionally unavailable**, regardless of anything a caller submits
  (`CreateDishRequest` has no `is_available` field at all). Menu Categories are **create-only** in
  v1 so far (no update/delete endpoint exists, Story 2.2's explicit scope), and their name
  uniqueness is plain case-sensitive, unlike User/Ingredient names (trap 11).
- **A Cook can read the menu catalog (Categories, Dishes, Recipe Ingredient lines) and the
  Ingredient list, but has zero write access to any of it** (Story 2.5, FR-25). This is the first
  Role granted read access to a resource it cannot write to at all; `MenuReadDep`/`InventoryReadDep`
  are the pattern (a dedicated read-only dependency alongside the write-only one), the same shape
  `InventoryReadDep`/`InventoryWriteDep` already established in Story 2.1.
- **RESOLVED by Story 2.6.** The Category/Dish creation forms the UX mockup (`key-menu-management.html`)
  shows, and the Ingredients screen's own create form, now exist on `MenuManagementPage.tsx` and
  `IngredientsPage.tsx` respectively. Zero backend changes, both endpoints (`POST /api/menu/categories`,
  `POST /api/menu/dishes`, `POST /api/inventory/ingredients`) had existed unused since Stories 2.1/2.2.
  No dialog anywhere: both forms are always-visible inline forms, and the dish form's Category picker
  gets a small "+ New category" in-place reveal (a text field + Confirm/Cancel swapping in where the
  picker is), the same component-local-boolean-reveal shape `TablesSetupPage`'s `TableListRow`
  established for row editing.
- The single WebSocket connection (`/api/ws`, Story 1.5) is **one per authenticated session**: a
  second connection from the same User closes the first. A connection's session is re-verified
  periodically while it stays open, so a socket cannot outlive its JWT or survive a Role change/
  deactivation indefinitely (bounded by the re-verification interval, not instant).

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

- **A WebSocket broadcast test needs a real `uvicorn.Server`, not `TestClient` (Story 1.5).**
  `TestClient.websocket_connect` runs the ASGI app in a separate thread with its own event loop, so
  a broadcast call from the test would race the connection registry across two loops.
  `tests/test_websocket.py` instead runs a real `uvicorn.Server` on an ephemeral port, sharing the
  test's own event loop, `lifespan="on"` so the server's own startup/shutdown pairs with
  `container.init_resources()`/`shutdown_resources()` symmetrically. Do **not** call
  `container.init_resources()` manually alongside `lifespan="off"`, that leaves the database engine
  bound to a pytest-asyncio event loop a later test's own loop has already replaced, surfacing as
  `asyncpg.InterfaceError: another operation is in progress` in whichever test runs next.
  `TestClient.websocket_connect` also does not reuse the client's HTTP cookie jar, pass the session
  cookie explicitly via a `Cookie` header.
- **Verify a numeric claim against a live Postgres before writing the assertion.** Two review
  findings (trap 16) were confirmed by actually sending the oversized value against a running
  database and reading the real exception, not by reasoning about Pydantic's field constraints in
  the abstract. A first attempt at the Story 2.1 precision test used a value that turned out to be
  exactly at the boundary (accepted, not rejected); caught only by running it.

- **"Make it fail first" has a specific failure mode: a test that pins the wrong thing.** This rule
  has now been broken three times, twice by tests whose *shape* made them unfalsifiable rather than
  by a missing red run. Story 2.4's AC6 test is the sharpest example: it was byte-for-byte identical
  to the AC4 "already occupied" test, so it passed under both the guarded `UPDATE` it was meant to
  pin **and** the naive read-then-write that AC exists to forbid. The check that catches this is not
  "did I watch it go red once", it is **"if I implement the wrong thing, does this test notice?"**
  For any test guarding a concurrency rule, write the wrong implementation, run the test, and
  confirm it fails. Two related shapes already documented above: an assertion derived from the DOM
  it is asserting on, and a stubbed `fetch` that resolves before React re-renders.
- **Testing a race needs the state change to land mid-request.** Setting the row to its blocking
  state before calling the endpoint tests the ordinary rejection, not the race. `test_tables.py`'s
  `test_race_between_form_load_and_save_is_rejected` is the pattern: `monkeypatch` the service's
  read method so it commits the conflicting change from the test's own session on its way out,
  which puts the change strictly between the read and the write. Assert both the 409 **and** that
  the write did not land.
- **A backend `IntegrityError`/rollback branch is usually unreachable from the suite.** Any handler
  that only runs when a pre-check loses a race will never execute in a single-threaded test, so it
  can carry a crashing bug (trap 20) while the suite stays green. When writing one, verify its
  mechanism directly (a focused probe) rather than assuming coverage.

Every story in `epics.md` is written as Given/When/Then acceptance criteria, those are the tests.
Backend suite is now **225 tests**, frontend **117 tests** (as of Story 3.1).

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

**2026-08-11 patch (Story 1.5, Real-Time Push Transport, plus its code review):** first WebSocket
transport landed: `api/websocket.py` (the single `/api/ws` endpoint), `clients/websocket.py`
(`ConnectionRegistry`, keyed by user id so one connection per session is enforceable and a
broadcast can target several Roles in one call), `services/realtime_service.py`, and the frontend's
`RealtimeProvider.tsx` (replacing the static `ConnectionStatusProvider` in `App.tsx`, now mounted
inside `RequireAuth`). Trap 15 added (a WebSocket `yield` dependency pins a pooled DB connection for
the connection's whole lifetime, confirmed by reproducing pool exhaustion directly); `clients/database.py`
gained `session_scope()` as the fix. `api/dependencies.py` gained the WebSocket-route counterparts
`CurrentUserWsDep`/`verify_ws_origin`. A new Testing entry documents the real-`uvicorn.Server`
pattern needed for broadcast tests, since `TestClient` cannot share an event loop with the app.

**2026-08-11 patch (Story 2.1, Create and Manage Ingredients, plus its code review):** first
`inventory` domain router: `api/inventory.py` (`POST /api/inventory/ingredients`, the first route to
permit two Roles via `require_role`), `services/inventory_service.py`. Trap 11 extended: the
username case-insensitive-uniqueness fix was reused verbatim for `Ingredient.name` (revision
`daca523f69f5`), now a two-instance precedent rather than a username-only quirk. Trap 16 added
(first occurrence): a `Numeric` column needs a matching `max_digits`/`decimal_places` bound or an
oversized value 500s instead of 422ing, confirmed by reproducing the raw `asyncpg` error against a
live database.

**2026-08-12 patch (Story 2.2, Manage Menu Categories and Dishes, plus its code review):** first
`menu` domain router: `api/menu.py` (category create, dish create/update, admin-only),
`services/menu_service.py`, and AD-8's first half (the availability-toggle gate). Two new
`ConflictError` subclasses (`DuplicateCategoryNameError`, `EmptyRecipeError`) and two new bare-404
types (`CategoryNotFoundError`, `DishNotFoundError`) added to `exceptions/`. Trap 16 extended
(second occurrence, this time on plain `Integer` columns rather than `Numeric`): `category_id`/
`prep_time_minutes` had no upper bound, so a value beyond Postgres's int4 range also 500'd, fixed
with `Field(le=2_147_483_647)`. Trap 17 added: `CategoryNotFoundError`/`DishNotFoundError` duplicate
`UserNotFoundError`'s shape by deliberate choice rather than sharing a base, revisit if a fourth
`*NotFoundError` ever appears. `Dish.is_available`'s column-level default corrected from `True` to
`False` to align with AD-8 (no migration needed, it was never a `server_default`). Domain rules
section gained notes on Dish's unconditional-unavailable-at-creation rule, Category's create-only/
case-sensitive scope, and the WebSocket one-connection-per-session/periodic-re-verification
behavior (the latter carried over from Story 1.5, missed by that patch). Suites are now **158
backend and 47 frontend tests**.

**2026-08-12 patch (Story 2.3, Define a Dish's Recipe, plus its code review):** Recipe Ingredient
CRUD landed on `api/menu.py`/`MenuService`, closing AD-8's second half, alongside three enabling
reads (`GET /menu/categories`, `GET /menu/dishes`, `GET /inventory/ingredients`). Trap 17 marked
**resolved**: this story crossed the fourth-`*NotFoundError` threshold it named, so the shared
`NotFoundError` base plus one handler now exists and three near-duplicate handlers were collapsed
into one; `tests/test_migrations.py` gained an assertion pinning the inheritance, since forgetting
it yields a silent 500. AD-8's entry rewritten (both halves built) and extended with the
unit-must-match-the-Ingredient rule, which no AD states but Epic 5's deduction depends on. Trap 9's
prescription was applied to AD-8 for the first time (`MenuService._lock_dish`), after the review
found that this story's own spec had wrongly told the developer to skip the lock: two concurrent
deletes could leave an available Dish with an empty recipe. **First real domain screens** on the
frontend (`MenuManagementPage` + `components/menu/DishRecipeEditor`), plus the first per-domain
service files beyond `authService`. The frontend current-state tree and a new "shape every domain
screen should copy" list capture the review's UI findings, all of which were silent-failure states.

**2026-08-12 patch (Story 2.4, Manage Restaurant Tables, plus its code review):** `api/tables.py` +
`services/table_service.py` + `TablesSetupPage`, completing Epic 2's authoring surfaces. Three new
traps, all generalizable. **Trap 18**: a "only while the row is in state X" rule must be one guarded
`UPDATE`, not a read-then-write, with two sharp edges the review found in this story's own code (a
no-op early return that skipped the guard and answered 200 on an occupied table, and a race test
that could not fail because it set the blocking state before the request started). It also draws the
line between trap 18's guarded `UPDATE` and trap 9's `SELECT ... FOR UPDATE`. **Trap 19**:
`Number()` on a form field plus a nullable backend field equals a silent partial write, reproduced
end to end. **Trap 20**: `db.rollback()` expires `actor`, so logging `actor.id` afterward raises
`MissingGreenlet` and turns an intended 409 into a 500; four handlers carried this, all now fixed,
and none of them is reachable from the test suite. Domain rules gained the note that
`RealtimeService` still has **no producers**, which is what leaves Story 2.4's AC4 partially unmet
(deferred to Epic 3 by decision). Testing section gained the "a test that pins the wrong thing"
lesson, the mid-request race-testing pattern, and the warning that rollback branches are unreachable
from the suite. Suites are now **212 backend and 66 frontend tests**.

**2026-08-13 patch (Story 2.5, Cook Browses the Dish Catalog, plus its code review):** Zero new
backend endpoints or schemas, deliberately: `MenuReadDep` (new, `api/menu.py`) and `InventoryReadDep`
(widened, `api/inventory.py`) now also permit `UserRole.cook` on the existing list/read routes only,
every write route unchanged. First Role granted read access with zero write access to the same
resource. Real frontend screen `cook/DishesPage.tsx` replaces its placeholder, the third real domain
screen after `MenuManagementPage`/`TablesSetupPage`. The review reproduced and fixed a real "silent
blank page" bug: only `useDishes()`'s loading/error state drove the page, so a `useCategories()`/
`useIngredients()` failure was completely invisible, no error, no empty state, nothing rendered but
the heading. Added to "the shape every new domain screen should copy": a page driven by more than
one independent query must OR every query's `isLoading`/`isError` together, not just the "main"
one's. Also fixed, in the same review: a Dish whose Category couldn't be resolved was silently
dropped instead of falling back to `#{id}` (this story's own spec had said to do this and the first
implementation pass hadn't actually done it), and a failed Ingredient-list fetch silently degraded
Recipe Ingredient lines to raw ids with no warning. **Separately, found while manually testing the
running stack (not a code defect): no story anywhere in the plan builds the Category/Dish creation
forms the UX mockup shows.** Traced through Stories 2.2 and 2.3, confirmed via every story title
across all 6 epics, logged as a genuine planning gap in `deferred-work.md` and in Domain rules
above, not fixed here (out of this story's scope). Suites are now **213 backend and 76 frontend
tests**.

**2026-08-13 patch (Story 1.6, Manage User Accounts from the Admin UI):** Zero backend changes —
Story 1.3 already built and tested every endpoint this story needed; only `admin/UsersPage.tsx`
(the fourth real domain screen, replacing its placeholder) and the new `services/userService.ts`
landed. `types/user.ts`'s existing `CurrentUser` (built for `GET /api/auth/me` in Story 1.1) was
reused as the list-row type rather than duplicated, since its shape already matched
`UserResponse` byte for byte — worth checking `types/` for an existing match before adding a new
type on any future story that wires a screen to an already-shipped endpoint. Resolves the
`deferred-work.md` item on self-deactivation (Story 1.3's review): the signed-in Admin's own row
now shows "This is you" in place of Deactivate, matching `key-users.html` exactly, going one step
further than the confirmation-step fix that item suggested. AD-15's last-Admin lockout was already
enforced server-side; this story only renders its existing 409 inline. Suites are now **213
backend and 93 frontend tests**.

**2026-08-13 patch (Story 2.6, Create Menu Categories, Dishes, and Ingredients from the Admin UI):**
Frontend-only, zero backend changes: the two gaps Story 2.5's review logged (no Category/Dish
creation UI, `IngredientsPage.tsx` still a bare placeholder) are both closed. `menuService.ts` gained
`useCreateCategory`/`useCreateDish` (payload types private to the file, per `tableService.ts`'s
precedent); `inventoryService.ts` gained `useCreateIngredient` and promoted its query key to a named
`INGREDIENTS_QUERY_KEY` constant, matching every other service file. `MenuManagementPage.tsx` gained
an always-visible "+ New dish" form with an inline "+ New category" reveal on its Category picker (a
component-local boolean swap, the same shape `TablesSetupPage`'s `TableListRow` uses for row editing;
no dialog, this codebase has never introduced one). `IngredientsPage.tsx` went from a one-line
placeholder to a real screen: an "Add ingredient" form plus a dense-row list, deliberately without
shortage sorting/highlighting/a Status column/click-to-detail, that scope stays with Epic 4's Story
4.3. Alongside this story's own work (not optional polish, required for the new dish-creation form
to fail loudly rather than silently): `MenuManagementPage.tsx` had the same "silent blank page" bug
Story 2.5's review found and fixed in `DishesPage` — only `useDishes()`'s `isLoading`/`isError` drove
the page, `useCategories()`'s own state was read for data only, never checked. It was never
backported to this file; fixed here the same way, `isLoading`/`isError` now OR'd across both queries
and Retry refetches both. The Task 1 regression test for this fix, and the two duplicate-name/empty-
state assertions in the new `IngredientsPage.test.tsx`, were each mutation-tested (behavior
temporarily reverted, confirmed the test actually fails, then restored) before being trusted.

**The review's most consequential finding was an AC that the routing architecture made unreachable.**
AC4 names both Warehouse Manager and Admin as able to create Ingredients, and
`InventoryWriteDep` has permitted both since Story 2.1 — but `RequireAuth` gated every route on a
single `ROLE_PATH_PREFIX[role]` string, and `/warehouse/ingredients` is outside `/admin`, so an Admin
was redirected away from a screen the backend explicitly authorized them for. Fixed by adding an
`Ingredients` entry to `ROLE_NAV_ITEMS.admin` and replacing the prefix comparison with a new
`canRoleVisit(role, pathname)` in `navigationConfig.ts` (anything under the Role's own prefix, **or**
an exact match on a surface that Role's own nav links to). **The generalizable rule: derive
cross-prefix route reachability from the nav config rather than keeping a second hand-maintained
list** — that makes a nav entry a Role cannot open unrepresentable. Note the converse does *not*
hold and deliberately so: the prefix clause grants a Role's own subtree whether or not the nav links
to it, which is what lets detail routes like `/waiter/tables/:tableId` work without their own entry.
A second review round caught two bugs in the first version of this fix: prefix matching that ignored
segment boundaries (so `/admin` would also match a future `/administration`), and a `startsWith` on
nav paths that silently handed Admin `/warehouse/ingredients/:ingredientId`, Story 4.3's surface. The
nav clause is now an exact match and the prefix clause is segment-aware. The check remains a
navigation affordance, never a security boundary (trap 14). **Story 1.4's AC2 was amended by
correct-course in the same story** (`epics.md`, `EXPERIENCE.md`): it had read "no cross-role
navigation anywhere", keying the rule to URL shape, when the intent was always authorization —
a Waiter must never see Admin tools. Other review patches: a submit handler must
re-check its *full* predicate rather than trusting the disabled button (Enter submits a form
regardless, and the checks both handlers had omitted were exactly the ones guarding a blank name and
a duplicate in-flight request); an inline reveal nested inside another form needs its own Enter
handling or the outer form's implicit submit steals it; and a mutation whose caller immediately
selects the created row should seed the cache in `onSuccess` before invalidating, since invalidation
only *schedules* a refetch. Suites are now **213 backend and 90 frontend tests**.

**2026-08-14 patch (Story 3.1, Open a Table and Start an Order, plus its code review):** First
`orders` domain route: `api/orders.py` (`POST /api/orders/tables/{table_id}/open`), `OrderResponse`
(`data_models/order.py`), `TableNotAvailableError` (`exceptions/__init__.py`, distinct from
`TableInUseError` since that one's docstring scopes it specifically to an Admin's edit attempt),
and `services/order_service.py`. `OrderService.open_table` is the second application of AD-6's
guarded-UPDATE pattern (`table_service.py`'s `update_table` was the first), with its read step
factored into a private `_get_table` seam purely so the race test could monkeypatch it, mirroring
`TableService.get_table`'s own role in trap 18's test. `GET /api/tables` widened onto a new
`TablesReadDep` (admin, waiter), closing the gap this file had flagged as deferred to Epic 3 since
Story 2.4; `POST`/`PATCH` stay admin-only, unchanged. First route in the project gated to exactly
one non-admin Role with no admin fallback (`require_role(UserRole.waiter)`).

Frontend: `waiter/TablesPage.tsx` replaces its Story 1.4 placeholder, the fifth real domain screen.
Reused the existing `useTables()` hook rather than duplicating it in the new `orderService.ts`
(a deliberate deviation from the story's literal task text, exporting `TABLES_QUERY_KEY` from
`tableService.ts` instead); `useOpenTable()` invalidates `onSettled`, not `onSuccess` only, per the
review (a lost race means the cached `available` status is already stale, same reasoning
`useUpdateTable` documented first). `TableOrderDetailPage.tsx` remains a placeholder by design,
Story 3.2/3.3+ territory.

**Trap 21 added**, found while standing up a fresh Docker image for manual testing, not by any
test suite: a pre-existing Story 2.6 TypeScript error in `IngredientsPage.tsx` (a `const`-narrowing
quirk making one branch of a submit guard unreachable) had sat in the tree undetected because
neither `pnpm test` nor routine development ever ran a full `docker compose build`, and `pnpm
build`'s `tsc -b` step fails the whole image on a type error. Fixed as an incidental one-line
change, unrelated to this story's own scope. Domain rules gained the note that opening a Table is
the second guarded-UPDATE application. Suites are now **225 backend and 117 frontend tests**.

Last Updated: 2026-08-14
