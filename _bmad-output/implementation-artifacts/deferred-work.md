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
  cursor later is a breaking response-shape change. Best decided when Story 1.4 builds the Users
  screen and the actual pagination need is known.
- **An Admin can deactivate their own account** — `backend/services/user_service.py:162-171` never
  compares `user_id` to `actor.id`. Verified: with a second admin present, self-deactivation
  returns 200 and the very next request on that session returns 401. AD-15 still holds (it only
  permits this when another active Admin remains) and no AC forbids it, so this is arguably correct
  behavior rather than a defect. But a misclick on the wrong row is unrecoverable for that Admin,
  and it is only truly safe if someone actually holds the other Admin account's password. Better
  addressed as a confirmation step in Story 1.4's Users screen than as a service-layer block.
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
