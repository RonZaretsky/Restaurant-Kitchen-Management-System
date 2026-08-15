# Deferred Work

## Deferred from: code review of story-1-0 (2026-08-08)

- **`get_session` missing `await` on `container.database()`** — `backend/clients/database.py:9`
  raises `AttributeError` on the first real DB-backed request, since the async resource
  provider returns a Future, not the `Database` instance. Pre-existing bug on a file Story 1.0
  was not allowed to touch. Fix is a single `await`. Story 1.1 should fix this when it wires the
  first real route through `SessionDep`.
- **`db_session` fixture has no per-test transaction isolation** — `backend/tests/conftest.py:88-97`
  opens a plain session against the session-scoped `migrated_database` with no rollback or
  truncation between tests. Unreachable today because only read-only tests exist; the first
  story that adds a write-test needs to wrap this in a savepoint/rollback or truncate strategy,
  or state changes will leak across tests in the same run.
- **`migrated_database` fixture has no per-worker uniqueness** — `backend/tests/conftest.py:72-84`
  hardcodes one database name. Fine today since there is no `pytest-xdist` dependency and no CI
  pipeline. Revisit if parallel test execution or CI is introduced, since concurrent runs would
  race on the same `DROP DATABASE` / `CREATE DATABASE` calls.
- **DSN-building duplicated three times** — the `postgresql+asyncpg://...` f-string appears in
  `backend/container.py`, `backend/alembic/env.py:51-54`, and `backend/tests/conftest.py:32-34`.
  A shared helper is the honest fix, but `container.py`'s function signature was on Story 1.0's
  must-not-change list, so consolidating now would mean touching that file anyway or adding a
  new shared module for a one-line string. Revisit if a fourth consumer appears.
- **No clear-error guard when Postgres is unreachable** — `backend/tests/conftest.py`'s DB
  fixtures raise a raw `ConnectionRefusedError` deep in setup if Postgres isn't running, rather
  than one message pointing at "start Postgres first" (`docker compose up`). DX polish only, not
  a correctness bug.

## Deferred from: code review of story-1-1 (2026-08-08)

- ~~**The JWT `role` claim is written but never read**~~ — **RESOLVED during the same review's
  patch pass, not deferred.** The claim was dropped from `create_access_token` entirely; the
  token now carries only `sub` and `exp`. `get_current_user` re-loads the `User` row, so role is
  always read live from the database. **The rule this leaves for Story 1.2:** derive
  authorization from the loaded `User`, never from a token claim. Putting `role` back in the
  token would mean an Admin demoting or deactivating someone has no effect until that user's
  token expires up to 8 hours later.
- ~~**Layering: `api/` imports `data_models`**~~ — **RESOLVED 2026-08-08, not deferred.**
  `backend/api/auth.py` originally defined `LoginRequest`/`LoginResponse` inline and pulled the
  bare `UserRole` enum from `data_models` to type the response, the crossing this item
  originally flagged. `LoginRequest` and `LoginResponse` now live in the new
  `backend/data_models/auth.py`, alongside `MAX_PASSWORD_BYTES` (moved there too, since the
  request schema's `Field(max_length=...)` needs it and `data_models/` must not import from
  `services/`). `api/auth.py` now imports only Pydantic schemas from `data_models`, never a raw
  domain enum, matching the architecture spine's own description of that package: "SQLAlchemy
  models & Pydantic schemas." `services/auth_service.py` imports `MAX_PASSWORD_BYTES` back from
  `data_models`, which is the allowed direction (`services/` may depend on `data_models/`). The
  opposite-direction violation (`services/` importing `fastapi.Request`) was already resolved in
  the prior patch pass. **The pattern for Story 1.2 and beyond:** request/response schemas for a
  domain live in `data_models/{domain}.py` next to that domain's ORM models, not inline in the
  router file.

## Deferred from: code review of story-1-3 (2026-08-10)

- **An Admin password reset does not revoke the target's existing sessions** —
  `backend/services/user_service.py:216-221` overwrites `password_hash` only. Verified by
  execution: the victim's pre-reset session cookie still authenticates afterwards, because the JWT
  carries only `sub`/`exp` and nothing password-derived. Since the canonical reason to reset a
  password is a compromised account, the attacker keeps access for the remaining token lifetime
  (8h default) while everyone believes the account was secured. AC7's "the old password stops
  working immediately" is satisfied for *login*, and no Story 1.3 AC covers session revocation.
  The honest fix is a `token_version` column on `users`, bumped on reset, included in the JWT and
  verified in `get_current_user` — an Alembic migration plus an AD-3 amendment, both outside Story
  1.3's stated no-schema-change scope. The revocation seam already exists (`get_current_user`
  rejects inactive users, proven by the deactivate path returning 401 on the same cookie), so the
  wiring is small once the column exists. **Worth doing before any real deployment**; it is a
  genuine security gap, not just polish.
- **`GET /api/admin/users` is unbounded** — `backend/services/user_service.py:92` is
  `select(User).order_by(User.id)` with no limit, offset, or `is_active` filter. Fine for a
  restaurant's staff list. Flagged because this endpoint is on the critical path for every admin
  screen (per Story 1.3's scope note it is the only way the UI discovers user ids), and adding a
  cursor later is a breaking response-shape change. **Still open**: Story 1.6 (not 1.4, which only
  built the shell/placeholder) is the one that actually built the Users screen against this
  endpoint, and deliberately added no pagination — same call this item already made ("fine for a
  restaurant's staff list"). Revisit if the roster ever grows past what one page can show.
- ~~**An Admin can deactivate their own account**~~ — **RESOLVED by Story 1.6 (2026-08-13),
  which built the Users screen this item was waiting on.** The signed-in Admin's own row shows
  "This is you" in place of a Deactivate control (matching `key-users.html`), and the control is
  withheld from *every* row while the signed-in identity is unknown, so the guard fails closed.
  Deactivating *another* User is additionally gated behind an in-row "Deactivate {name}?"
  confirmation, which is the confirmation step this item originally asked for. The backend is
  untouched (AD-15's last-Admin guard was always the real backstop); this closes the UX gap on top
  of it. **Scope note, corrected during Story 1.6's code review:** this covers self-*deactivation*
  only. Self-*demotion* (an Admin changing their own Role away from `admin` via Edit) is still
  reachable and is not blocked, by design — AD-15 permits it whenever another active Admin remains,
  and the backend rejects it otherwise. Story 1.6 does make it non-silent: every mutation now
  invalidates `CURRENT_USER_QUERY_KEY`, so the app shell re-reads the demoted Role immediately
  instead of continuing to render Admin nav against a stale profile.
- **The test suite has no isolation against concurrent runs, and this review proved it empirically**
  — during this review three Opus subagents ran `uv run pytest` simultaneously; one observed a
  251-second run with 3 spurious failures (`InvalidRequestError: Could not refresh instance`) in
  tests unrelated to the change. Three subsequent fresh-database runs by the reviewer were green in
  ~24s each, confirming the story's own code is not flaky. This is live confirmation of the
  pre-existing `migrated_database` per-worker-isolation item already deferred from Story 1.0, and it
  will become a real problem the moment CI or `pytest-xdist` is introduced. Not caused by Story 1.3.

## Deferred from: code review of story-1-2 (2026-08-08)

- **403 is invisible in the OpenAPI schema** — `ForbiddenError` is a bare `Exception` rather than
  an `HTTPException` (`backend/exceptions/__init__.py:47`), so FastAPI cannot infer it and a
  `require_role`-protected route declares only `200` in its `responses`. Verified against a real
  mounted route. The frontend from Story 1.4 onward, reading `/docs` or generating a typed client,
  sees no 403 contract for exactly the routes whose purpose is returning one. Deferred because
  there is no protected route to annotate yet. **Story 1.3 should settle this** when it adds the
  first one: either declare `responses={403: ...}` per route, or give `require_role` a shape that
  contributes the response to the schema automatically.
- **Authorization denials are not logged, by decision, and the obligation moves to `services/`** —
  `require_role` raises `ForbiddenError` silently at `backend/api/dependencies.py:74`, while every
  auth rejection inside `AuthService` logs one. Reviewed and **decided 2026-08-08 (Ofek): the
  service layer owns denial logging, `api/` stays thin and non-logging.** A bare "role X denied"
  from a shared dependency carries no domain context; the log line worth having is the one the
  service writes, with the order id, ingredient name, or target user id attached. **Action for
  Story 1.3 and every domain story after it:** when a service rejects an action, log it through the
  injected loguru logger with the acting user id. This is the only remaining coverage for
  `project-context.md`'s "log at every layer, carry identifying context" rule on the authorization
  path, so if 1.3 does not do it, nothing does.
- **The `AuthError`/`ForbiddenError` families silently discard a constructor message** — `detail`
  is a class attribute with no `__init__` override, so `ForbiddenError("only admins may do this")`
  keeps the generic default and `str(ForbiddenError())` is `''`, leaving an escaped traceback as a
  bare class name. Verified. Pre-existing rather than introduced here: every member of the
  `AuthError` family Story 1.1 added has the same shape, so the honest fix changes that family
  too. Worth doing the first time a call site genuinely needs a specific message; harmless while
  every raise site uses the default.

## Deferred from: code review of story-1.4 (2026-08-11)

- **The frontend image bakes `http://localhost:8000` as the API origin** — `docker-compose.yml`
  passes it as a build arg into `frontend/Dockerfile:12`, so the built image only works when the
  browser runs on the same machine as the stack; from any other device `localhost` resolves to the
  client. Matches `project-context.md` trap 7's accepted localhost-only scope for v1, so deferred
  rather than fixed. The new `frontend/nginx.conf` is the natural place to terminate this if the app
  ever needs to be reached off-box: an `/api` proxy makes requests same-origin, which removes the
  baked host and the CORS allow-list at the same time.
- **Session expiry discards the attempted deep link** — `RequireAuth` at
  `frontend/src/components/shell/RequireAuth.tsx:38` redirects to `/login` without carrying the path
  the user was trying to reach, so a Waiter whose 8-hour session lapses on `/waiter/tables/12` lands
  back on their home surface after logging in. `useLocation()` is already read in that component, so
  the fix is `state={{ from: location }}` plus a `LoginPage` handler that honours it. No AC requires
  it; worth doing when deep links start being shared between staff.
- **The catch-all route is unreachable and there is no real 404 surface** —
  `frontend/src/router.tsx:49` places `{ path: "*", element: <Navigate to="/" replace /> }` inside
  the guarded layout, but `RequireAuth` returns its own redirect before `Outlet` ever renders, so
  that element is dead code. The practical effect is that any mistyped or stale URL silently lands
  on the Role home instead of saying anything, which will hide broken links in later stories.
  Benign today; revisit if a real 404 surface is ever wanted.
- **`frontend/src/types/user.ts` is not pinned to the backend's `UserResponse`** — the two are kept
  in agreement by hand, so a backend field rename fails only at runtime, in the route guard, as a
  redirect to Login. No contract-testing tooling exists on this project and adding it is new scope,
  so this is deferred rather than solved. Same class as the item below.
- **An unknown Role at runtime would crash the shell** — `ROLE_HOME_PATH[user.role]`,
  `ROLE_PATH_PREFIX[user.role]` and `ROLE_NAV_ITEMS[user.role]` are exhaustive `Record<UserRole, ...>`
  maps, so TypeScript covers this at build time; it can only bite if the backend's `UserRole` enum
  grows without a matching frontend change, at which point `navItems.map` throws and blanks the
  entire app bar. A `?? []` / `?? homePath` fallback would degrade instead of crashing.
- **A Cook's dark default flashes light on every cold load** — `ThemeModeProvider.tsx:60` derives
  `mode` from `user?.role`, which is `undefined` while `GET /api/auth/me` is still in flight, so the
  first paint is light and then flips. Cosmetic, and deliberately left alone: the obvious fix
  (persisting the Role-derived default to `localStorage` once known) conflicts with AC4's
  per-browser-not-per-account semantics on a shared kitchen terminal, where it would leave the next
  Waiter to sign in stuck in dark mode.
- **AC7's connection producer and automatic retry ship with Story 1.5** — reviewed and **decided
  2026-08-11 (Ofek): the scaffold is accepted as satisfying Story 1.4's half of AC7.**
  `frontend/src/components/shell/ConnectionStatusContext.tsx` defines the transport-agnostic
  `{ status }` contract and `ReconnectingBanner` consumes it, but `App.tsx` mounts the provider with
  no `status` prop and nothing anywhere can ever set `"reconnecting"`, so the banner is unreachable
  in the running app and no retry exists. Building a producer now (polling a health endpoint, say)
  would invent a transport that 1.5 immediately replaces. **Action for Story 1.5:** wire the live
  WebSocket to drive `status`, and implement AC7's "automatic retry" there. The context's shape is
  the contract 1.5 must match, so it should not be changed without revisiting `ReconnectingBanner`.
  Until 1.5 lands, AC7 is only half met and the banner has no runtime coverage.

## Deferred from: code review of story-1.5 (2026-08-11)

- **The `Secure` + `SameSite=Lax` session cookie limits the WebSocket transport to same-site /
  localhost, and it fails silently.** Story 1.5's cookie-on-upgrade design works only because
  `localhost` gets the potentially-trustworthy exemption for `Secure` and because `:3000`/`:8000`
  are same-site. Any deployment where the frontend and API are cross-site, or reached over `ws://`
  on a LAN address, drops the cookie on the upgrade. The observable symptom is a permanent
  "Reconnecting..." banner with a 30s retry loop, no server-side log, and no client-side
  distinction between "rejected" and "network down". `api/auth.py` already carries a review note
  that LAN access silently drops this cookie, so Story 1.5 inherits this constraint rather than
  introducing it. **Action:** revisit when the app is first deployed anywhere other than
  localhost — likely a token-in-subprotocol handshake, or serving both origins behind one host.

- **Removing the app-wide `ConnectionStatusProvider` lets a future consumer outside `RequireAuth`
  silently read a fake "connected".** Story 1.5 moved the provider from `App.tsx` down into
  `RequireAuth`, so it now wraps only the authenticated subtree. `ConnectionStatusContext`'s
  default value is `"connected"`, so a consumer mounted outside that subtree (login screen, 404,
  error boundary) would read a status that reflects nothing, with no warning. Nothing is wrong
  today: the only consumer is `ReconnectingBanner` inside `AppShell`, which is inside the provider.
  **Action:** if connection status is ever needed outside the authenticated shell, make the
  context default `undefined` and have `useConnectionStatus()` throw outside a provider.

## Deferred from: code review of story-2.4 (2026-08-12)

- **AC4's "re-enabling the moment the table returns to `available`" is not implemented, deferred to
  Epic 3 by decision 2026-08-12 (Ofek).** `TablesSetupPage` derives the Edit control's disabled
  state from `useTables()`, but nothing refreshes it when a *different* session frees or seats a
  table: no `refetchInterval`, no `useRealtime()` subscription, and the query is invalidated only by
  that page's own mutations. A Waiter releasing a table leaves Edit disabled until a manual reload.
  AD-2 requires the owning service to broadcast every state change, and `RealtimeProvider`'s
  `subscribe(event, handler)` has been unused since Story 1.5. **Rationale for deferring rather than
  building it now:** Epic 3 needs live table status for Waiters to satisfy its own ACs, so the
  `table.*` event contract should be designed there against its real consumers, instead of being
  invented here for a single one and reworked two stories later. **Action for the Epic 3 story that
  first needs live table state:** emit `table.created`/`table.updated` from `TableService` (the
  first real producer on the Story 1.5 transport) and subscribe on both the Waiter surface and
  `TablesSetupPage`, which closes this AC4 clause retroactively.

- **`TablesSetupPage` diverges from the UX mock's panel layout.** The mock
  (`mockups/key-tables-setup.html`) has two bordered panels with an "Add table" panel head, a
  "N tables configured" subtitle, right-aligned row actions, and values rendered as `Table 1` /
  `2 seats`; the page ships a bare form and a bare table with raw numeric values. Dense-row styling
  (UX-DR8) itself **is** satisfied, via the theme's `MuiTable: { defaultProps: { size: "small" } }`
  default. Cosmetic only, no AC-visible behavior depends on it. Worth folding into whichever story
  next touches an Admin setup screen.
- **`GET /api/tables/` is Admin-only and Epic 3 will have to widen it.** project-context.md's domain
  rules state "every Waiter sees every Table", and `router.tsx` already routes `waiter/tables` to a
  `TablesPage`. Story 2.4 deliberately scoped table reads to Admin (its Scope note says Waiter-facing
  reads are Epic 3's concern). Nothing blocks the change: no test asserts a Waiter is refused on the
  list route, only that a Cook is. **Action for the Epic 3 story that needs Waiter table reads:**
  widen `TablesDep` on the list route to `require_role(UserRole.admin, UserRole.waiter)` (the
  two-Role precedent `api/inventory.py` already set) rather than adding a second near-duplicate
  endpoint.
- **An offline (paused) query renders a blank page and a paused mutation disables its button
  forever.** With TanStack v5's default `networkMode: "online"`, an offline query is
  `isPending: true, isFetching: false`, so `isLoading` is false, `isError` is false, and `data` is
  undefined, leaving all four render branches false. `createMutation.isPending` likewise stays true
  while paused, disabling Add table with no explanation. Pre-existing codebase-wide shape
  (`MenuManagementPage` has the identical gap), not introduced by Story 2.4. Fix once, in a shared
  pattern, rather than per page.
- **The test-support fake `Response` diverges from the real one.** `jsonResponse` in both
  `TablesSetupPage.test.tsx` and `MenuManagementPage.test.tsx` supplies only `ok`, `status`, `text`
  and `json`, with no `headers`, `statusText` or `body`. It works against today's `httpClient`, but a
  future 204 path, header read, or `response.clone()` will fail with an obscure "not a function"
  rather than a meaningful assertion. There are now three hand-rolled copies (counting
  `appIntegration.test.tsx`); lift one shared helper.

## Deferred from: dev-story of story-2.4 (2026-08-12)

- ~~**Logging `actor.id` after `db.rollback()` raises an unhandled `MissingGreenlet`, latent in three
  existing `IntegrityError` handlers.**~~ **RESOLVED 2026-08-12 during Story 2.4's code review, not
  deferred.** The review found a fourth instance, freshly introduced in `TableService.create_table`
  by this very story, and all four call sites were fixed together in that pass (log before rollback,
  never after). Original finding retained below for the reasoning.

- **(resolved, kept for the why)** Found and fixed live in `TableService.update_table` while
  writing Story 2.4's AC6 race test (the first test in this codebase to actually trigger a
  rollback-then-log path, since every prior duplicate-name check wins on its existence check before
  ever reaching an `IntegrityError`). `AsyncSession.rollback()` expires every object bound to the
  session, `actor` included; reading `actor.id` afterward triggers an implicit lazy-load with no
  greenlet context to run it in. The same ordering (rollback, then `actor.id` in the warning log)
  exists in `MenuService.create_category` (`backend/services/menu_service.py:83`),
  `MenuService.add_recipe_ingredient` (`:341`), and `InventoryService.create_ingredient`
  (`backend/services/inventory_service.py:86`) — none currently reachable by any test, so all three
  are a real 500 waiting for a genuine concurrent-duplicate race in production, not a hypothetical.
  **Fix is mechanical**: swap the two lines so the log call reads `actor.id` before `await
  db.rollback()`, matching what Story 2.4's own `TableService.update_table` now does. Worth a
  dedicated pass across all four call sites (three existing plus the new one) the next time any of
  those files is touched, rather than three more stories each rediscovering it independently.

## Deferred from: code review of story-2.2 (2026-08-11)

- **`UpdateDishRequest` has no way to clear `description` or `prep_time_minutes` back to null
  once set.** `MenuService.update_dish` guards every field with `if payload.X is not None`, which
  cannot distinguish "the caller explicitly sent `null`" from "the caller omitted this field
  entirely" — both look identical once Pydantic parses the request. A caller can never blank out a
  previously-set description or prep time via `PATCH /api/menu/dishes/{id}`; the value is
  permanent once set to anything non-null. No acceptance criterion in Story 2.2 asks for this
  capability, so it was not built. **Action:** if a later story needs to support clearing an
  optional field via this endpoint, adopt an explicit "unset" sentinel (e.g. a distinct sentinel
  object as the field default, checked with `is` rather than `==`, so an explicit `null` can be
  told apart from an omitted field) rather than plain `Optional[str] = None`.

## Deferred from: dev-story of story-2.5 (2026-08-13)

- **RESOLVED by Story 2.6 (2026-08-13), for the creation-form gap this entry describes.**
  `MenuManagementPage.tsx` now has an always-visible "+ New dish" form with an inline "+ New
  category" reveal on its Category picker, and `IngredientsPage.tsx` (previously a bare placeholder)
  now has its own "Add ingredient" form. No backend change was needed, exactly as this entry
  predicted. This story's code review also surfaced a separate, pre-existing gap the original entry
  never mentioned — an Admin could not navigate to the Ingredients screen at all, despite
  `InventoryWriteDep` having permitted Admin since Story 2.1 — and that **was** fixed here too, by
  deriving route reachability from `ROLE_NAV_ITEMS` via `canRoleVisit()`. Original entry kept below
  for context.
- **No story anywhere in the plan builds the Category/Dish creation forms the UX mockup shows.**
  `key-menu-management.html` (the UX designer's mockup for `MenuManagementPage`) explicitly shows a
  "+ New dish" button, and an equivalent affordance for creating a Menu Category. Neither exists in
  the shipped UI. Traced through both stories that touch this screen: Story 2.2 (which built the
  backend `POST /api/menu/categories`/`POST /api/menu/dishes`) was scoped backend-only by its own
  ACs, no UI was ever required of it. Story 2.3 (which built `MenuManagementPage.tsx`, the list +
  per-dish recipe editor) explicitly deferred the creation forms in its own code comment ("Category/
  Dish creation forms are deliberately out of scope... this screen's remaining CRUD ships in a later
  story"). Checked every story title across all 6 epics: no later story ever picks this up. This is
  a genuine planning gap, not a bug, each story correctly assumed the form wasn't its job on the
  assumption a later story would build it, and none did. Found while manually testing Story 2.5
  against the running stack (Ron asked "is there an API for creating dishes" after not finding a
  create button anywhere in the UI).
  **Action:** the backend endpoints already exist and need no changes
  (`POST /api/menu/categories`, `POST /api/menu/dishes`); a new story is needed to add the create
  forms to `MenuManagementPage.tsx`, matching `key-menu-management.html`'s "+ New dish" affordance
  and its Category-creation equivalent. Until that story exists, an Admin can only create a Category
  or Dish via a direct API call.

## Deferred from: code review of story-1.6 (2026-08-13)

- **`errorMessage` is now copy-pasted verbatim into a fifth file, and its fallback branch is dead
  code.** `frontend/src/pages/admin/UsersPage.tsx:48-53` is byte-identical to
  `TablesSetupPage.tsx:29-34`, with near-identical twins in `DishesPage.tsx`, `DishRecipeEditor.tsx`
  and the same literal in `LoginPage.tsx`. Separately, its `error instanceof ApiError` fallback
  ("Something went wrong. Try again.") is **unreachable**: `httpClient.apiRequest` throws `ApiError`
  on every failure path including network failure and timeout, so the non-ApiError branch can never
  execute. **Action:** lift one shared `errorMessage` next to `ApiError` in `httpClient.ts` and
  delete the five copies. Worth doing on whichever story next touches two or more of those files;
  doing it here would have put five unrelated screens in this story's diff.
- **A sixth hand-rolled `jsonResponse` test helper copy.** `UsersPage.test.tsx:54-62` joins the
  copies in `TablesSetupPage.test.tsx`, `MenuManagementPage.test.tsx`, `appIntegration.test.tsx`,
  and `cook/DishesPage.test.tsx`. Same item Story 2.4's review already recorded (then at three);
  Story 1.6's own spec explicitly marked lifting it non-blocking for this story. All copies still
  supply only `ok`/`status`/`text`/`json`, so a future 204 path, header read, or `response.clone()`
  fails with an obscure "not a function" rather than a meaningful assertion. **Action:** lift one
  shared test helper; the count now justifies it more than it did at three.
- **Inline row editors do not submit on Enter.** `UsersPage.tsx`'s edit and password panels are
  plain `Box`es, not `<form>`s, so Enter does nothing after typing, while the create form on the
  same screen does submit on Enter. Pre-existing shape inherited from `TablesSetupPage`'s
  `TableListRow`, but Story 1.6 is the first screen where both behaviors are visible side by side,
  which is what makes the inconsistency noticeable. **Action:** wrap both inline panels in
  `<Box component="form" onSubmit=...>` when either file is next touched; fix both screens together
  so they do not diverge further.
- **No client-side guard on the password's 72-byte bcrypt limit.** `backend/data_models/user.py`
  enforces the limit in **UTF-8 bytes**, not characters, so a Hebrew or otherwise multibyte password
  is rejected at roughly 36 characters with a raw Pydantic message. Story 1.6's spec explicitly
  scoped this out ("do not add client-side password-length validation beyond non-empty... risks
  disagreeing with the server's UTF-8-byte-based count"), and that reasoning still holds for a naive
  character-count check. **Action:** if this ever bites a real user, the correct fix is
  `new TextEncoder().encode(password).length <= 72`, which agrees with the server exactly rather
  than approximating it. Relevant to this project specifically, since the team and likely users are
  Hebrew-speaking.
- **No seed script or bootstrap command for a first Admin account.** A fresh `docker compose up`
  produces an empty `users` table, and every route on the Users screen requires an authenticated
  Admin, so there is no way to reach the running app at all without hand-inserting a row. Verifying
  Story 1.6 manually meant hashing a password with `uv run python -c "...AuthService.hash_password"`
  inside the backend container, then `INSERT`ing via `psql`. This is why Story 1.6's first pass
  shipped with no live browser check. **Action:** add a small idempotent bootstrap (an Alembic data
  migration, a `python -m scripts.seed_admin` command, or a first-run "create the first Admin" path)
  so a fresh clone is reachable. Worth doing before the project is demonstrated or handed in, since
  a grader cloning the repo currently cannot log in.

## Deferred from: code review of story-2.6 (2026-08-13)

- **FIXED, not deferred: `appIntegration.test.tsx`'s "lands on Kitchen Display" test was
  load-sensitive.** It failed with `Test timed out in 5000ms` in two of three full-suite runs while
  passing every time in isolation, with no code change in between. The test types two fields through
  `userEvent`, waits on a deliberately `delayed()` `/api/auth/me`, and drives the whole router, all
  inside Vitest's default 5s budget. Story 2.6's route-guard change is not the cause (this test's
  Cook path is granted by the prefix clause, which kept its subtree semantics), but the story grew
  the suite by 18 tests, and the extra parallel contention is what brought it over the line — which
  makes it this story's to fix rather than log. Given an explicit 20s timeout; assertions unchanged.
  Recorded here because the underlying fragility is general: any integration test that drives real
  user interaction plus a delayed network stub needs a budget set from that, not the unit-test
  default, and a suite that is red for timing reasons is worse than one that is slow.

- **Client-side numeric parsers only enforce sign, not the backend's exact digit/decimal-place/int4
  bounds.** `parsePositivePrice`/`parseNonNegativeInteger` (`MenuManagementPage.tsx`) and
  `parseNonNegativeAmount` (`IngredientsPage.tsx`) reject non-numeric and negative input but do not
  cap decimal places or digit count against `CreateDishRequest.price` (`max_digits=8,
  decimal_places=2`), `prep_time_minutes` (`le=2_147_483_647`), or
  `CreateIngredientRequest.min_stock_threshold`/`current_stock` (`max_digits=10, decimal_places=3`).
  An out-of-bounds value still round-trips to a 422, surfaced inline via `ApiError.message` per
  UX-DR17, so this is a wasted round trip, not a silent failure. **Action:** if a future story
  touches these forms again, consider tightening the regexes to the exact bounds.
- **createDishMutation/createMutation (Ingredients) errors are never reset while the user edits
  fields after a failed submit, only on the next `mutate()` call.** The stale error `Alert` can
  outlive a field edit that would have fixed it, for the few seconds before the user resubmits.
  Self-heals on the very next submit attempt (TanStack Query resets `isError` as soon as a new
  `mutate()` starts), so no submission is ever blocked or corrupted by this. **Action:** if this
  becomes a recurring complaint, wire `.reset()` into each form's field `onChange` handlers,
  matching Story 1.6's fix for the same class of issue on longer-lived row state.
- **`errorMessage()`/`GENERIC_ERROR_MESSAGE` is now duplicated across four page files
  (`TablesSetupPage.tsx`, `DishesPage.tsx`, `MenuManagementPage.tsx`, `IngredientsPage.tsx`), and
  `IngredientsPage.tsx`'s `UNIT_OPTIONS` duplicates `DishRecipeEditor.tsx`'s `UNITS` constant.**
  Matches this codebase's existing per-screen duplication precedent (no shared `components`/`utils`
  module exists yet for either), so not a new deviation, but the fifth screen will copy it again.
  **Action:** if a sixth screen needs either, extract `errorMessage`/`GENERIC_ERROR_MESSAGE` next to
  `ApiError` in `httpClient.ts`, and the `Unit` enum's UI options next to its `types/menu.ts`
  definition.

## Deferred from: code review of story-3-1 (2026-08-14)

- **`test_orders.py`'s race test runs both writes through the same `db_session`/connection**
  (`backend/tests/test_orders.py:710`), proving the guarded-UPDATE predicate is logically correct
  but not exercising true cross-connection concurrency. Mirrors `test_tables.py`'s own established
  race-test pattern verbatim, which this story's own spec mandated reusing. A real multi-connection
  test harness is a test-infrastructure investment beyond any single story's scope. **Action:** if
  a future story needs to prove real cross-transaction behavior (e.g. actual isolation-level
  interaction), build a shared two-connection test fixture then.
- **No synchronous click-lock on `TableTile`/`handleOpen`** (`frontend/src/pages/waiter/TablesPage.tsx:69`)
  — `openMutation.isPending` updates asynchronously, leaving a narrow window for a double-click to
  fire two concurrent open requests. The backend's guarded UPDATE already prevents any
  data-integrity consequence; worst case is a flashed extra 409. **Action:** if this proves
  annoying in manual testing, add a `useRef` synchronous guard on the click handler.
- **`TableTile`'s `badgeColor` ternary has no exhaustive/default guard** for a `TableStatus` value
  outside `available`/`occupied`/`reserved` (`frontend/src/pages/waiter/TablesPage.tsx:53`).
  `TableStatus` is a closed 3-member enum shared with the backend; no current code path can produce
  a fourth value. **Action:** if a future story adds a new Table status, switch this to an
  exhaustive lookup map so a missing color mapping fails loudly instead of rendering an unlabeled
  default badge.
- **`OrderResponse` exposes bare `table_id`/`waiter_id` integers with no denormalized context**
  (table number, waiter name) (`backend/data_models/order.py:126`). Explicitly out of scope per
  Story 3.1's own scope note. **Action:** the table detail page (Story 3.2/3.3+) will need to
  resolve these ids into something displayable — decide there whether that's a join in the
  response or a separate lookup.
