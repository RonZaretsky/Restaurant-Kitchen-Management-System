---
baseline_commit: 33e4aa36b45317a1cfc185106fabf2155e478623
---

# Story 1.1: User Login

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a staff member,
I want to log in with a username and password,
so that I can access the parts of the system my role permits.

**Scope note.** This story is backend-only. The Login *screen* (React form, redirect-after-login,
generic-error display in the UI) is built in Story 1.4 against [key-login.html](../planning-artifacts/ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/mockups/key-login.html).
This story's job is the `POST /api/auth/login` endpoint, the JWT-cookie session it issues, the
CORS policy that lets the frontend call it, and the shared auth dependency every later protected
route will use. Do not build any frontend code here.

## Acceptance Criteria

**AC1 — Successful login**
Given a User with valid active credentials,
When they submit username and password to the login endpoint,
Then they receive a JWT set as an httpOnly cookie identifying their Role, and the response body
identifies their Role (the frontend, in Story 1.4, uses this to redirect to the role's home
surface — this story does not redirect anything itself).

**AC2 — Wrong credentials**
Given a wrong username or a wrong password,
When login is attempted,
Then it is rejected with a generic "Invalid username or password" error that does not reveal which
part was wrong (FR-1).

**AC3 — Deactivated user**
Given a deactivated User's credentials,
When they attempt to log in,
Then login is rejected with the same generic error as AC2 (FR-1/FR-3).

**AC4 — Password verification**
Given a User created by an Admin (Story 1.3) with a bcrypt-hashed password,
When they submit their credentials,
Then authentication verifies the submitted password against the stored bcrypt hash; the plaintext
password is never stored, never logged, and never included in any response or error payload (FR-1,
PRD Privacy guardrail).

**AC5 — Token expiry**
Given a successful login,
When the JWT is issued,
Then it carries an 8-hour expiry, matching a work shift so no one is logged out mid-service; on
expiry the user is returned to Login and re-authenticates, with no refresh-token flow in v1 (AD-3,
resolves PRD Open Question 1).

**AC6 — Protected-by-default**
Given no valid session cookie,
When any non-login, non-health route is requested,
Then the request is rejected as unauthorized (NFR-2, AD-3).

**AC7 — CORS and DI wiring**
Given the login route is hit from the frontend origin,
When the request is made,
Then CORS is enforced via an explicit allow-list of that origin, never a wildcard (AD-3), and
`container.wire()` is activated for the `auth` module, the first entry in the `modules=[...]` list
(AD-1).

**AC8 — Stray scaffold cleanup**
Given the stray empty `backend/data_models/exceptions/` package left over from scaffolding,
When this story touches the backend,
Then it is removed, leaving top-level `backend/exceptions/` as the single designated location for
custom exceptions (architecture spine, Deferred).

## Tasks / Subtasks

- [x] **Task 1: Exceptions package** (AC: 8, 2, 3)
  - [x] Delete `backend/data_models/exceptions/` (the file is empty; confirmed nothing imports
    `data_models.exceptions` anywhere in the codebase)
  - [x] Create `backend/exceptions/__init__.py` with `InvalidCredentialsError(Exception)` — raised
    for wrong username, wrong password, and deactivated user alike, so the caller cannot
    distinguish the three cases (AC2, AC3)
  - [x] Register a FastAPI exception handler in `main.py` mapping `InvalidCredentialsError` to a
    `401` response body `{"detail": "Invalid username or password"}` — one handler, so the generic
    message can never drift between call sites

- [x] **Task 2: Add auth dependencies** (AC: 4, 5)
  - [x] Add `bcrypt>=5.0.0` and `pyjwt>=2.13.0` to `backend/pyproject.toml`'s main `dependencies`
    (not the dev group; these run in production) and run `uv sync` from inside `backend/`,
    committing the regenerated `uv.lock`
  - [x] Do not add `passlib` — it is unmaintained and its bcrypt backend has known compatibility
    breaks with bcrypt 4.x+; call `bcrypt.hashpw`/`bcrypt.checkpw` directly instead

- [x] **Task 3: Config for auth and CORS** (AC: 5, 7)
  - [x] Add to `backend/config.yaml`:
    ```yaml
    auth:
      secret_key: ${JWT_SECRET_KEY: "dev-only-insecure-secret-change-me"}
      token_expiry_hours: 8

    cors:
      allow_origin: ${FRONTEND_ORIGIN: "http://localhost:3000"}
    ```
  - [x] Wire both into `container.config` the same way `database`/`logging` already are (config is
    loaded once in `main.py` via `container.config.from_dict(load_config(...))`, nothing extra
    needed there)

- [x] **Task 4: AuthService** (AC: 1, 2, 3, 4, 5, 6)
  - [x] Create `backend/services/auth_service.py` with a class `AuthService`:
    - Constructor takes `secret_key: str`, `token_expiry_hours: int` (config-driven, no per-request
      state, so it can be a container-level provider — see Task 5)
    - `async def authenticate(self, db: AsyncSession, username: str, password: str) -> User`:
      looks up the User by username, raises `InvalidCredentialsError` if not found, if
      `is_active` is `False`, or if `bcrypt.checkpw` fails against `password_hash` — all three
      paths raise the identical exception so the caller cannot distinguish them (AC2, AC3, AC4)
    - `def create_access_token(self, user: User) -> str`: builds a JWT with `sub=str(user.id)`,
      `role=user.role.value`, `exp` = now + `token_expiry_hours` (AC5), signed with `secret_key`,
      `HS256`
    - `async def get_current_user(self, request: Request, db: AsyncSession) -> User`: reads the
      cookie, decodes/validates the JWT (raises `InvalidCredentialsError` — mapped to 401 by the
      Task 1 handler — on missing cookie, bad signature, or expiry), loads the `User` by the `sub`
      claim, raises if the user no longer exists or is now deactivated. **This is the one shared
      dependency AD-3 requires** — every future protected route depends on this method, never a
      per-route reimplementation
  - [x] Never log the plaintext password anywhere in this file, including in exception messages
    (AC4)

- [x] **Task 5: Register AuthService in the container** (AC: 7)
  - [x] Add to `backend/container.py`:
    ```python
    auth_service = providers.Factory(
        AuthService,
        secret_key=config.auth.secret_key,
        token_expiry_hours=config.auth.token_expiry_hours,
    )
    ```
  - [x] `AuthService` takes no DB session in its constructor — the session is per-request
    (`SessionDep`) and is passed as a method argument at call time, not injected via the container
    (the container's providers are app-lifetime; a request-scoped `AsyncSession` cannot live on
    one)

- [x] **Task 6: Auth router** (AC: 1, 2, 3, 6, 7)
  - [x] Create `backend/api/auth.py`: `APIRouter(prefix="/api/auth", tags=["auth"])`
  - [x] `POST /api/auth/login`, `@inject`-decorated, taking a `LoginRequest` Pydantic body
    (`username: str`, `password: str`), the `SessionDep`, a `Response` param, and
    `auth_service: AuthService = Depends(Provide[Container.auth_service])`
  - [x] On success: call `auth_service.authenticate(...)`, then `create_access_token(...)`, set it
    via `response.set_cookie(key="access_token", value=token, httponly=True, samesite="lax",
    secure=not container.config.app.debug(), max_age=token_expiry_hours * 3600)`, return a
    `LoginResponse` with the User's role (do not return the token in the body — it only ever
    travels as the httpOnly cookie)
  - [x] `InvalidCredentialsError` from `authenticate` propagates to the Task 1 handler; do not
    catch it in the route
  - [x] Include the new router in `backend/api/router.py`'s aggregator via `include_router()` —
    that file stays the aggregator-only, no route logic added there

- [x] **Task 7: CORS middleware and DI wiring** (AC: 7)
  - [x] In `backend/main.py`, register `CORSMiddleware` on the `FastAPI` app with
    `allow_origins=[container.config.cors.allow_origin()]` (a one-item explicit list, never `"*"`),
    `allow_credentials=True` (required for the cookie to be sent cross-port), and the standard
    methods/headers
  - [x] Call `container.wire(modules=["api.auth"])` after the container is constructed — this is
    the first entry in the wire list; every later story that adds `@inject` to a new router
    **appends** its module name to this same list, never replaces it (AC7, AD-1)

- [x] **Task 8: Fix the pre-existing `clients/database.py` bug** (AC: 1 — needed for the login
  route's DB query to work at all)
  - [x] `get_session` currently does `db = request.app.container.database()` without `await`. The
    `database` provider is a `providers.Resource` built from an async generator, so the call
    returns an unawaited `Future`, and `db.session_factory` raises `AttributeError`. Fix: `db =
    await request.app.container.database()`. This was flagged in Story 1.0's Completion Notes as
    deferred to this story, since 1.0 had nothing that actually queried the DB through `SessionDep`
  - [x] Verify with a test that actually round-trips a query through `SessionDep` (the login test
    in Task 9 covers this — Story 1.0's tests never exercised this path)

- [x] **Task 9: Tests** (AC: all)
  - [x] `test_auth.py`: seed a User directly via the DB session fixture (bcrypt-hash a known
    password with the same helper `AuthService` uses, so the test doesn't duplicate hashing logic)
    covering: successful login sets the cookie and returns the role (AC1); wrong password rejected
    with the generic message (AC2); wrong username rejected with the identical message (AC2);
    deactivated user rejected with the identical message (AC3); the JWT's `exp` claim is
    `now + 8h` within a small tolerance (AC5)
  - [x] Assert the response never contains the plaintext password anywhere, including on a failed
    login (AC4)
  - [x] `get_current_user` unit-level coverage (AC6): no cookie raises `InvalidCredentialsError`;
    an expired token raises it; a token signed with the wrong secret raises it; a valid token
    resolves the correct User. **No protected domain route exists yet to exercise this
    end-to-end** (Stories 1.2/1.3 add the first ones) — proving the dependency directly is the
    correct scope for this story, matching the guard-test precedent set by Story 1.0's
    `test_migrations_match_the_models`
  - [x] CORS: assert `CORSMiddleware` is registered with `allow_origins == [<configured origin>]`
    and not `["*"]`
  - [x] `GET /health` still returns `200` with no cookie (stays public)

## Dev Notes

### Architecture compliance

- **AD-1 (DI composition root).** `AuthService` is a `providers.Factory` on `Container`, config-driven only. `container.wire(modules=["api.auth"])` is the first wire call in the codebase — every later story appends its router module to this list; a silently truncated list (replacing instead of appending) is the exact failure mode `project-context.md` calls out.
- **AD-3 (Auth).** httpOnly cookie, 8-hour expiry, one shared dependency (`AuthService.get_current_user`), explicit CORS allow-list. `Secure` is conditional on `not debug` per the spine's "Secure outside local dev" — reuses the existing `app.debug` config flag rather than inventing a second one.
- **NFR-2 (universal authorization).** This story only wires the *mechanism*; there are no protected domain routes yet to apply it to (Story 1.2 formalizes enforcement across all future routers). Do not add a placeholder protected route just to exercise this — test the dependency directly (Task 9).

### Traps this story resolves (from `project-context.md`)

Story 1.1 was flagged as killing traps 1, 3, 4, 5 from `_bmad-output/project-context.md`:
1. `container.wire()` was never called anywhere — Task 7 activates it for `auth`.
3. No CORS middleware existed — Task 7 adds it.
4. No auth layer existed, every route was effectively public — Tasks 4-6 add it.
5. `backend/data_models/exceptions/` was stray scaffold debris — Task 1 removes it.

**Update `_bmad-output/project-context.md`'s "Traps that fail silently" section after this story lands** — traps 1, 3, 4, 5 should be marked resolved the same way Story 1.0 marked trap 2 resolved, so the next story's context isn't reading stale warnings.

### Library/framework requirements (verified 2026-08-08)

| Package | Version to add | Notes |
|---|---|---|
| `bcrypt` | `>=5.0.0` | Direct API (`bcrypt.hashpw`/`bcrypt.checkpw`), not via `passlib` — `passlib` is unmaintained and has known breaks against bcrypt 4.x+ |
| `pyjwt` | `>=2.13.0` | Import name is `jwt`. Use `jwt.encode`/`jwt.decode` with `algorithms=["HS256"]` explicitly on decode (PyJWT requires the allowed algorithm list on decode as a security measure — omitting it raises) |

Both go in `pyproject.toml`'s main `dependencies` array (not `[dependency-groups] dev`) — they run inside the production container, same reasoning as `alembic` in Story 1.0.

### Existing files this story modifies

| File | Current state | What changes |
|---|---|---|
| `backend/container.py` | `Container` with `config`, `logging`, `database` providers (Story 1.0 removed `create_all`) | Add `auth_service = providers.Factory(AuthService, ...)` |
| `backend/main.py` | App factory, `lifespan`, includes `router` only | Add `CORSMiddleware`, add `InvalidCredentialsError` exception handler, call `container.wire(modules=["api.auth"])` |
| `backend/api/router.py` | Single flat router, only `/health` | `include_router()` the new `auth` router — stays aggregator-only |
| `backend/clients/database.py` | `get_session` calls `container.database()` without `await` (pre-existing bug, deferred here by Story 1.0) | Add the missing `await` — this is the fix, not a rewrite |
| `backend/config.yaml` | `app`, `server`, `database`, `logging` sections | Add `auth` and `cors` sections |
| `backend/pyproject.toml` | 8 main deps (Story 1.0 added `alembic`) | Add `bcrypt`, `pyjwt` |

Files that must **not** change beyond what's listed: `backend/data_models/**` (schema is untouched by this story — no migration needed, `User` already has every column this story reads), `backend/alembic/**`.

### New files

- `backend/exceptions/__init__.py` — `InvalidCredentialsError`
- `backend/services/auth_service.py` — `AuthService`
- `backend/api/auth.py` — login router
- `backend/tests/test_auth.py`

### Project Structure Notes

- Imports relative to `backend/` as root, same as every prior story — `from services.auth_service import AuthService`, never `from backend.services...`.
- `services/` is the only layer that writes to the DB or calls an outbound client (architecture spine, Design Paradigm) — `AuthService.authenticate` is where the User lookup happens, not in `api/auth.py`. Route handlers stay thin: validate, call the service, return the response model.
- Type hints on every signature. Docstrings on every function/method/class per `project-context.md`'s "Comments and docstrings" section — no em dash in any docstring or comment. Test files (`test_auth.py`) skip docstrings and use `# Arrange` / `# Act` / `# Assert` instead.
- REST route naming: `/api/{domain}/{resource}` per the architecture spine's Consistency Conventions table — `/api/auth/login` fits (`auth` domain, `login` action-resource).

### Testing

Backend harness is live as of Story 1.0: `uv run pytest` from `backend/`, fixtures `client`, `db_session`, `migrated_database`, `empty_database` in `conftest.py`. This story's tests are the first to actually write/read a `User` row through `db_session` — Story 1.0's suite was read-only. Use `bcrypt.hashpw` directly in the test setup (matching what `AuthService` does) rather than inserting a fake hash string, so a real `checkpw` round-trip is exercised.

### References

- Story source: [Source: _bmad-output/planning-artifacts/epics.md#Story 1.1]
- Auth invariant: [Source: ARCHITECTURE-SPINE.md#AD-3] — JWT httpOnly cookie, explicit CORS, one shared dependency
- DI invariant: [Source: ARCHITECTURE-SPINE.md#AD-1] — composition root, `providers.Resource`/`providers.Factory`
- Permissions model: [Source: ARCHITECTURE-SPINE.md#AD-9] — role-level only, relevant background for `get_current_user`'s shape even though enforcement itself is Story 1.2
- Exceptions convention: [Source: ARCHITECTURE-SPINE.md#Deferred] — stray `data_models/exceptions/` to be removed, top-level `backend/exceptions/` is canonical
- FR/NFR text: [Source: prd.md#FR-1, #FR-3, #NFR-2, #Privacy]
- Prior-story bug handoff: [Source: _bmad-output/implementation-artifacts/1-0-project-foundation-test-harness-and-migration-baseline.md#Completion Notes List] — `clients/database.py` missing `await`, explicitly assigned to this story
- Conventions: [Source: _bmad-output/project-context.md] — installed-vs-decided table (bcrypt/JWT libs "decided, not yet installed" for this story), traps 1/3/4/5, comment/docstring rules
- Sequencing: [Source: _bmad-output/implementation-artifacts/sprint-status.yaml] — Story 1.0 gates this story; this story gates 1.2 and 1.3

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (Claude Code, bmad-dev-story workflow)

### Debug Log References

**Task order changed from the written sequence.** Task 8 (fixing the pre-existing missing
`await` in `clients/database.py`) was implemented right after Task 6 (the auth router) rather
than after Task 7, since the login endpoint needed a working `SessionDep` to be testable at
all. Task 7 (CORS + `container.wire()`) was done last among the implementation tasks, right
before Task 9 (tests), since it is main.py's final piece and the tests assert on both the
wiring-enabled `@inject` route and the registered CORS middleware. Scope and content of every
task are unchanged; only the order was adapted, same as Story 1.0's precedent.

**Full regression pass:** `uv run pytest -v` from `backend/` (against a local Postgres started
via `docker compose up -d postgres`) — 18 passed (6 pre-existing from Story 1.0, 12 new). No
frontend files were touched by this story, so `pnpm test`/`pnpm build` were not re-run.

**Docker Compose end-to-end verification could not be completed on this machine.** A
`docker compose down -v && docker compose up --build` produced a crash-looping `backend`
container: `exec ./entrypoint.sh: no such file or directory`. Root-caused to this Windows
checkout's `core.autocrlf=true` converting `entrypoint.sh`'s committed LF line endings to CRLF
on checkout, breaking the `#!/bin/sh` shebang inside the Linux container. Confirmed with
`git show HEAD:backend/entrypoint.sh | cat -A` that the committed blob has correct LF endings
and `git log` that the file was added by Story 1.0, unmodified by this story. This is a
per-machine git-config artifact, not a repository defect or a regression introduced here, so it
was not fixed as part of this story (out of this story's file list and unrelated to any of its
ACs). The login flow, DI wiring, and CORS registration were instead verified through
`tests/test_auth.py`, which exercises the real `FastAPI` app (including its `lifespan`,
`container.wire()` call, and `CORSMiddleware` registration) via `httpx.AsyncClient` over
`ASGITransport` — equivalent coverage to a live HTTP call, without the container layer.
Flagging this CRLF issue for the team; a `.gitattributes` pinning `*.sh text eol=lf` would
prevent it recurring for any Windows contributor, but that is a repo-wide decision outside this
story's scope.

### Completion Notes List

**What was built.** The backend now has a working login endpoint (`POST /api/auth/login`)
issuing an httpOnly, 8-hour JWT cookie; a shared `AuthService.get_current_user` dependency
ready for every future protected route; CORS restricted to an explicit configured origin; and
`container.wire()` activated for the first time, with `api.auth` as its first module. The stray
`backend/data_models/exceptions/` scaffold folder is gone; `backend/exceptions/` is now the one
designated location for custom exceptions, starting with `InvalidCredentialsError`.

**Design decisions worth knowing:**

1. **One exception, three causes.** `AuthService.authenticate` raises the identical
   `InvalidCredentialsError` whether the username does not exist, the user is deactivated, or
   the password is wrong. A single FastAPI exception handler in `main.py` maps it to the fixed
   `401 {"detail": "Invalid username or password"}` body, so the generic message cannot drift
   between call sites and no code path can accidentally leak which part of a login attempt
   failed.
2. **bcrypt and PyJWT used directly, not `passlib`.** `passlib`'s bcrypt backend has known
   compatibility breaks against bcrypt 4.x+ and the project is unmaintained; `bcrypt.hashpw` /
   `bcrypt.checkpw` and `jwt.encode` / `jwt.decode` are called directly instead.
3. **`AuthService` is a container `Factory`, not a `Singleton` or a per-request object.** It
   holds only config values (`secret_key`, `token_expiry_hours`), no request-scoped state, so it
   can be constructed once and injected via `@inject` into route handlers. The database session
   it needs is passed as a method argument at call time, since a request-scoped `AsyncSession`
   cannot live on an app-lifetime container provider.
4. **AC6 (protected-by-default) is proven at the dependency level, not through a live protected
   route.** No domain router besides `auth` (public) and `health` (public) exists yet, so
   `tests/test_auth.py` calls `AuthService.get_current_user` directly with a hand-built
   `starlette.requests.Request` to prove it rejects a missing cookie, an expired token, and a
   token signed with the wrong secret, and accepts a valid one. This mirrors Story 1.0's
   `test_migrations_match_the_models` precedent: the executable proof for an invariant that has
   no consumer yet.
5. **The `clients/database.py` bug fix was a single line.** `get_session` now `await`s
   `request.app.container.database()` before calling `.session_factory()`. This was the only
   change to that file; the rest, including the fixture's shape, was left untouched.
6. **Cookie `Secure` attribute is tied to the existing `app.debug` config flag**, not a new
   setting: `secure=not debug`, injected via `Depends(Provide[Container.config.app.debug])`,
   matching the architecture spine's "Secure outside local dev" rule without inventing a second
   environment flag.

**Findings deliberately NOT fixed here (out of this story's stated scope):**

- **`backend/entrypoint.sh` breaks under Windows `core.autocrlf=true` checkouts.** See Debug Log
  above. Not in this story's file list; a `.gitattributes` fix is a repo-wide decision for the
  team, not this story's call.
- **NFR-2 ("no mutating action executes without an authenticated session") is not yet enforced
  on any concrete route**, because no mutating domain route exists yet besides login itself
  (which is intentionally public). Story 1.2 formalizes enforcement as new routers are added;
  this story only builds and proves the mechanism they will depend on.

### File List

**Added**

- `backend/exceptions/__init__.py`
- `backend/services/auth_service.py`
- `backend/api/auth.py`
- `backend/tests/test_auth.py`

**Modified**

- `backend/pyproject.toml` (added `bcrypt>=5.0.0`, `pyjwt>=2.13.0` to main dependencies)
- `backend/uv.lock` (regenerated by `uv sync`)
- `backend/config.yaml` (added `auth` and `cors` sections)
- `backend/container.py` (added `auth_service` provider, imports `AuthService`)
- `backend/main.py` (added `InvalidCredentialsError` exception handler, `CORSMiddleware`
  registration, `container.wire(modules=["api.auth"])`)
- `backend/api/router.py` (includes the new `auth` router)
- `backend/clients/database.py` (added the missing `await` on `container.database()`)

**Deleted**

- `backend/data_models/exceptions/__init__.py` (and the now-empty `backend/data_models/exceptions/` directory)

**Confirmed unchanged**: `backend/data_models/**` (other than the `exceptions/` removal above),
`backend/alembic/**`, all frontend files.

## Change Log

| Date | Change |
|---|---|
| 2026-08-08 | Removed the stray `backend/data_models/exceptions/` scaffold package; added `backend/exceptions/__init__.py` with `InvalidCredentialsError` and a global FastAPI handler mapping it to a generic 401. |
| 2026-08-08 | Added `bcrypt` and `pyjwt` as main backend dependencies. |
| 2026-08-08 | Added `auth` and `cors` config sections to `backend/config.yaml`. |
| 2026-08-08 | Added `AuthService` (`services/auth_service.py`): bcrypt password verification, JWT issuance with an 8-hour expiry, and the shared `get_current_user` session dependency. Registered it as a `providers.Factory` on the container. |
| 2026-08-08 | Added `POST /api/auth/login` (`api/auth.py`), setting the session JWT as an httpOnly, SameSite=Lax cookie; included it into the router aggregator. |
| 2026-08-08 | Registered `CORSMiddleware` with an explicit configured allow-list and activated `container.wire(modules=["api.auth"])`, the first entry in the wire list. |
| 2026-08-08 | Fixed the pre-existing missing `await` on `container.database()` in `clients/database.py`, deferred to this story by Story 1.0. |
| 2026-08-08 | Added `tests/test_auth.py` covering all 8 acceptance criteria: successful login, wrong username/password, deactivated user, no plaintext leakage, 8-hour token expiry, the `get_current_user` dependency's four cases, explicit CORS, and that `/health` stays public. |
