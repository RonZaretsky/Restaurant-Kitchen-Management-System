---
baseline_commit: 7c361ad457d7f6d286ca676f0cb34464a068e92f
---

# Story 1.3: Admin Manages User Accounts

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Admin,
I want to create, edit, deactivate, and reactivate User accounts,
so that I control who can access the system and with what role.

**Scope note.** Backend-only, same pattern as Stories 1.1 and 1.2. This story adds the first real
domain router (`api/admin.py`) and the first real caller of `require_role` (Story 1.2's guard,
built and tested but never mounted on a live route). It also owns two obligations Story 1.2's
code review deferred specifically to this story:

1. **OpenAPI must document the 403** every admin route can return (`ForbiddenError` is a bare
   `Exception`, so FastAPI cannot infer it; declare `responses={403: {...}}` per route).
2. **Service-layer denial logging.** `require_role` deliberately logs nothing (decided
   2026-08-08: `api/` stays thin, non-logging). The standing rule from that decision is
   "every service that rejects an action logs it through its injected loguru logger with the
   acting user id, starting with Story 1.3's user-management service." `UserService` must log
   every rejection (duplicate username, last-admin lockout) this way.

The AC below about the Users screen matching the UX mock is **not** implemented by this story,
same carve-out Story 1.2 used for its frontend AC. There is no MUI, no routing, and no frontend
auth context yet (Story 1.4 builds those); building a screen now would be thrown away. Do not
build any frontend code for this story.

No FR/AC explicitly asks for a "list users" endpoint, but there is no way to identify a User to
edit/deactivate/reactivate/reset without one, and no later story is positioned to add it
retroactively (unlike Epic 2's split between "manage" and "browse" stories, Users have no second
role that reads them). This story therefore adds `GET /api/admin/users` and
`GET /api/admin/users/{user_id}` as necessary supporting infrastructure, flagged here rather than
silently invented, so it stays visible as a scope decision.

## Acceptance Criteria

**AC1 — Create with initial password**
Given valid new-user details (username, full name, role, initial password), when an Admin submits
the create-user request, then a new User is created and can log in immediately with the assigned
Role and that initial password (FR-3).

**AC2 — Password never stored, logged, or returned in plaintext**
Given an Admin sets a new User's initial password, when the account is persisted, then the
password is stored only as a bcrypt hash in `password_hash`, never in plaintext, never logged, and
never returned by any read endpoint (FR-1, FR-3, PRD Privacy guardrail).

**AC3 — Missing password rejected**
Given the create-user request has a missing or blank password, when validation runs, then it is
rejected inline (422) and an account is never created without a password (FR-3, UX-DR17).

**AC4 — Duplicate username rejected**
Given a username that already exists (active or deactivated), when an Admin tries to create it,
then the request is rejected as a duplicate (FR-3, UX-DR17).

**AC5 — Deactivate blocks login, preserves history**
Given an active User, when an Admin deactivates them, then they can no longer log in, but their
historical records remain intact and attributed to them (FR-3).

**AC6 — Reactivate restores login**
Given a deactivated User, when an Admin reactivates them, then they can log in again (FR-3).

**AC7 — Admin-initiated password reset**
Given a User who has forgotten their password, when an Admin sets a new password on that account,
then the new password is hashed on the same path as an initial password, the previous hash is
overwritten, the old password stops working immediately, and the User can log in with the new one
(FR-3, FR-1).

**AC8 — Reset never needs or reveals the old password**
Given any Admin-initiated password reset, when it is performed, then it never reveals or requires
the account's previous password, and there is no self-service or email-based reset path anywhere
in v1 (FR-3).

**AC9 — Last-Admin lockout guard**
Given the last remaining active Admin account, when an Admin attempts to deactivate or demote it,
then the action is rejected inline with **"Rejected, at least one admin must stay active"**
(AD-15, UX-DR17). Applies to both the deactivate action and a role-edit that would change the
Admin's role away from `admin`.

**AC10 — Edits preserve historical attribution**
Given a User's Role or name is edited, when the edit is saved, then their historical records
(Order Items prepared, Stock Movements logged, etc.) stay attributed to the account as it existed
at the time (FR-3). _No code required this story: no domain service yet writes rows with a User FK
(Order/StockMovement services don't exist until Epic 3-5), so this is structurally guaranteed by
the schema (FK to `users.id`, never a copied name/role snapshot) and re-verified when those
services land. Do not add speculative code for it now._

**AC11 — Users screen UI**
Given the Users screen, when it renders, then it matches the UX mock with dense-row list styling
(UX-DR8, UX-DR19) and holds the WCAG 2.2 AA accessibility floor established in Story 1.4
(UX-DR21). _Deferred by design, see Scope note above. No frontend code ships in this story._

**AC12 — Router wired without truncating the module list**
Given the `admin` domain router does not yet exist, when this story adds it, then `admin` is
appended to `container.wire(modules=[...])`, never replacing the `auth`/`dependencies` entries
Stories 1.1/1.2 added (AD-1).

## Tasks / Subtasks

- [x] **Task 1: New exceptions** (AC: 4, 9)
  - [x] Add to `backend/exceptions/__init__.py`, following the existing `AuthError`-family shape
    (one base, siblings carry the message, one handler per family in `main.py`):
    ```python
    class ConflictError(Exception):
        """Base for a well-formed request that conflicts with existing state.

        One handler in main.py turns any subclass into a 409 carrying that
        subclass's `detail`.
        """

        detail = "Request conflicts with existing state"


    class DuplicateUsernameError(ConflictError):
        """Raised when creating a User with a username that already exists,
        active or deactivated."""

        detail = "That username already exists"


    class LastAdminLockoutError(ConflictError):
        """Raised when a mutation would leave zero active Admins (AD-15)."""

        detail = "Rejected, at least one admin must stay active"


    class UserNotFoundError(Exception):
        """Raised when an admin action targets a User id that does not exist."""

        detail = "User not found"
    ```
  - [x] Register two new handlers in `main.py`, mirroring `_auth_error_handler`/
    `_forbidden_error_handler` exactly in shape: `ConflictError` -> 409, `UserNotFoundError` ->
    404. Do not fold either into an existing handler; each status code stays independently
    testable, same reasoning Story 1.2 gave for keeping `ForbiddenError` separate from
    `AuthError`.
  - [x] Do not give these exceptions a constructor message. The whole `AuthError` family has the
    same class-attribute-only shape and fixing that is an explicitly deferred, separate concern
    from Story 1.2's review (see `deferred-work.md`). Match the existing pattern, don't fix it
    opportunistically here.

- [x] **Task 2: Request/response schemas** (AC: 1, 2, 3, 7)
  - [x] Add to `backend/data_models/user.py` (same file as `User`/`UserRole`, matching the
    "schemas live next to their domain's ORM models" pattern Story 1.1 established for
    `data_models/auth.py`):
    ```python
    from pydantic import BaseModel, Field, model_validator

    from .auth import MAX_PASSWORD_BYTES

    class CreateUserRequest(BaseModel):
        username: str = Field(min_length=1, max_length=50)
        full_name: str = Field(min_length=1, max_length=100)
        role: UserRole
        password: str = Field(min_length=1, max_length=MAX_PASSWORD_BYTES)

    class UpdateUserRequest(BaseModel):
        full_name: str | None = Field(default=None, min_length=1, max_length=100)
        role: UserRole | None = None

        @model_validator(mode="after")
        def at_least_one_field(self) -> "UpdateUserRequest":
            if self.full_name is None and self.role is None:
                raise ValueError("at least one of full_name or role must be provided")
            return self

    class ResetPasswordRequest(BaseModel):
        new_password: str = Field(min_length=1, max_length=MAX_PASSWORD_BYTES)

    class UserResponse(BaseModel):
        model_config = {"from_attributes": True}

        id: int
        username: str
        full_name: str
        role: UserRole
        is_active: bool
        created_at: datetime
    ```
    Note the reversed import direction from `data_models/auth.py` (auth.py has no dependency on
    user.py's new schemas; only `MAX_PASSWORD_BYTES` flows from auth.py into user.py). Confirm
    this doesn't create a circular import; if `data_models/__init__.py`'s import order causes one,
    move `MAX_PASSWORD_BYTES` instead of importing it, but try the straightforward import first.
  - [x] Export `CreateUserRequest`, `UpdateUserRequest`, `ResetPasswordRequest`, `UserResponse`
    from `data_models/__init__.py` (`__all__` too), same as every existing schema.
  - [x] `UserResponse` never includes `password_hash`. This is what makes AC2's "never returned by
    any read endpoint" true structurally, not by convention.

- [x] **Task 3: `UserService`** (AC: 1, 2, 4, 5, 6, 7, 9)
  - [x] Add `backend/services/user_service.py`. Follow `AuthService`'s established shape exactly:
    a plain class taking `logger` in `__init__`, no state held on the instance, `db: AsyncSession`
    passed into every method as an argument (never stored). No separate Repository class exists
    anywhere in this codebase yet (`AuthService` queries directly via `db.execute`); do not
    introduce one here either, that would be a new abstraction this story doesn't need.
    ```python
    class UserService:
        """Creates, edits, deactivates, and reactivates staff User accounts."""

        def __init__(self, logger: Any) -> None:
            self._logger = logger

        async def create_user(self, db: AsyncSession, payload: CreateUserRequest) -> User: ...
        async def list_users(self, db: AsyncSession) -> Sequence[User]: ...
        async def get_user(self, db: AsyncSession, user_id: int) -> User: ...
        async def update_user(self, db: AsyncSession, user_id: int, payload: UpdateUserRequest) -> User: ...
        async def deactivate_user(self, db: AsyncSession, user_id: int) -> User: ...
        async def reactivate_user(self, db: AsyncSession, user_id: int) -> User: ...
        async def reset_password(self, db: AsyncSession, user_id: int, new_password: str) -> User: ...
    ```
  - [x] **`create_user`**: hash the password through `AuthService.hash_password` (the single
    hashing seam, per its own docstring: "Story 1.3 creates and resets passwords through this").
    `UserService` does not need `AuthService` injected as a dependency for this, since
    `hash_password` is a `@staticmethod`; import and call it directly
    (`AuthService.hash_password(payload.password)`). Check for an existing username first
    (`select(User).where(User.username == payload.username)`, active or deactivated, no filter on
    `is_active`) and raise `DuplicateUsernameError` before insert if found — log the rejection
    (`self._logger.warning(...)`, no acting-admin id available at this layer unless threaded
    through, see the note on logging below) rather than relying solely on the DB's unique
    constraint, so the caller gets a clean 409 instead of a raw `IntegrityError`/500. A
    concurrent double-create race is out of scope for v1 (same tier of concern as the rest of this
    project's stated concurrency scope: AD-6/NFR-3 only cover Order/OrderItem/stock).
  - [x] **`update_user`**: load the target User (404 via `UserNotFoundError` if missing). If
    `payload.role` is provided and differs from the current role, and the current role is
    `UserRole.admin` and the new role is not, this is a demotion — run the same last-admin check
    as deactivation (see below) before applying it.
  - [x] **`deactivate_user`** and the demotion branch of `update_user` both need the AD-15 check:
    "the service layer rejects any User update (deactivation, role change) that would leave zero
    active Admins in the system." Implement as: if the target User is currently `role == admin`
    and `is_active == True`, count other active Admins (`select(func.count()).where(User.role ==
    UserRole.admin, User.is_active == True, User.id != user_id)`); if zero, raise
    `LastAdminLockoutError` before making any change. Log the rejection.
  - [x] **`reset_password`**: hash via `AuthService.hash_password`, overwrite `password_hash`,
    commit. No check of the old password anywhere in this path (AC8).
  - [x] **Denial logging (the obligation this story owns).** Every rejection
    (`DuplicateUsernameError`, `LastAdminLockoutError`) logs through `self._logger` before raising,
    with identifying context: target user id/username, and the acting admin's user id if it is
    available to the method. Decide whether to thread the acting `User` into these methods
    (e.g. `create_user(self, db, actor: User, payload: ...)`) purely to get that id into the log
    line — recommended, since the router already has `actor` from `require_role`'s return value
    and passing it through costs nothing. This is the log coverage Story 1.2's review explicitly
    left for this story; if it's skipped, nothing in the system logs an authorization/business-rule
    denial anywhere.
  - [x] Register `UserService` in `backend/container.py` as a `providers.Factory`, `logger=logging`
    injected, same shape as `auth_service`. No config values needed (unlike `AuthService`, which
    needs `secret_key`/`token_expiry_hours`).

- [x] **Task 4: `api/admin.py` router** (AC: 1, 2, 3, 4, 5, 6, 7, 9, 12)
  - [x] New file, `APIRouter(prefix="/api/admin", tags=["admin"])`. Every route gated by
    `Depends(require_role(UserRole.admin))` (call it, do not pass it bare — Story 1.2's docstring
    warns this exact misuse silently turns into an unchecked query parameter). Define once at
    module level for reuse across every route in the file:
    ```python
    AdminDep = Annotated[User, Depends(require_role(UserRole.admin))]
    ```
  - [x] Routes (all thin: validate via Pydantic, call `UserService`, return `UserResponse`; no
    SQLAlchemy in this file):
    - `POST /users` (201) — `create_user`
    - `GET /users` — `list_users` (supporting infra, see Scope note)
    - `GET /users/{user_id}` — `get_user` (404 via `UserNotFoundError` if missing)
    - `PATCH /users/{user_id}` — `update_user`
    - `POST /users/{user_id}/deactivate` — `deactivate_user`
    - `POST /users/{user_id}/reactivate` — `reactivate_user`
    - `POST /users/{user_id}/reset-password`, body `ResetPasswordRequest` — `reset_password`
  - [x] **Settle Story 1.2's deferred OpenAPI gap.** Every route above declares
    `responses={403: {"description": "..."}}` in its `@router.<method>(...)` decorator (mirroring
    how `response_model=UserResponse` is declared) so a guarded route's schema actually documents
    the 403 `ForbiddenError`/`require_role` can return. This is the concrete action Story 1.2's
    review flagged as "Story 1.3 should settle this."
  - [x] Include the router in `backend/api/router.py`: `router.include_router(admin_router)`,
    alongside the existing `auth_router` include. Do not touch the existing `/health` route or the
    `auth` include.

- [x] **Task 5: Wire the container module list** (AC: 12)
  - [x] In `backend/main.py`, change `container.wire(modules=["api.auth", "api.dependencies"])`
    to `container.wire(modules=["api.auth", "api.dependencies", "api.admin"])`. **Append, never
    replace** — this is AD-1's binding trap, called out in `project-context.md` trap 1 and in
    every prior story's Dev Notes.

- [x] **Task 6: Tests** (AC: all)
  - [x] New file `backend/tests/test_admin.py`, using the real `client`/`db_session` fixtures
    (unlike `test_authorization.py`, a real router now exists to hit over HTTP). Follow
    `test_auth.py`'s `_create_user` helper pattern (hash via `AuthService.hash_password`, commit,
    refresh) to seed users directly in `db_session`, and its login-then-reuse-the-client pattern
    (`httpx.AsyncClient` persists cookies across calls) to get an authenticated admin session
    before hitting `/api/admin/...`.
  - [x] Cover, at minimum, one test per AC:
    - AC1: create as admin -> 201, then log in as the new user with the submitted password -> 200.
    - AC2: create, then assert the raw DB row's `password_hash` is bcrypt (`$2b$` prefix) and
      differs from the plaintext; assert no admin response body ever contains `password_hash` or
      the plaintext password (list, get, create response bodies).
    - AC3: create with `password=""` or field omitted -> 422.
    - AC4: create the same username twice -> second call 409 with `DuplicateUsernameError`'s
      detail; also test the "already exists but deactivated" branch (create, deactivate, attempt
      to recreate the same username -> still 409).
    - AC5: deactivate an active user, then that user's `POST /api/auth/login` -> 401
      (`InvalidCredentialsError`, existing behavior from Story 1.1 since `authenticate` already
      checks `is_active`); assert the row still exists (not deleted).
    - AC6: deactivate then reactivate -> login succeeds again.
    - AC7: reset password for an existing user, old password now fails login, new password
      succeeds; assert `password_hash` changed.
    - AC9: seed exactly one active admin, attempt `POST /users/{id}/deactivate` on them -> 409
      with detail exactly `"Rejected, at least one admin must stay active"`; separately, attempt
      `PATCH /users/{id}` changing that same sole admin's role to `waiter` -> same 409. Also test
      the guard does NOT trip when a second active admin exists (deactivating one of two admins
      succeeds).
    - AC12: assert every route in `api/admin.py` returns 403 (not 500, not 200) for a
      non-admin authenticated caller of each of the four roles other than admin, and 401 for an
      unauthenticated caller — reusing `require_role`'s already-proven behavior, this just proves
      it is actually attached to these routes.
  - [x] One test asserting the OpenAPI schema: `app.openapi()["paths"]["/api/admin/users"]["post"]
    ["responses"]` (or equivalent for one representative route) contains `"403"`. This is what
    makes Task 4's OpenAPI-documentation subtask verifiable rather than a claim.
  - [x] Full regression: `uv run pytest` from `backend/` — this story touches `main.py`,
    `container.py`, `exceptions/__init__.py`, `data_models/__init__.py`, and
    `data_models/user.py`/`auth.py`, all shared by `test_auth.py`, `test_authorization.py`,
    `test_health.py`, and `test_container.py`.

### Review Findings

Reviewed 2026-08-10 by three parallel Opus reviewers (Blind Hunter, Edge Case Hunter, Acceptance
Auditor) against `7c361ad..working tree` scoped to `backend/`. Every finding below was
independently re-verified against the code before being rated; subagent severities were discarded.

All three layers independently converged on the multi-byte-password 500 and on the incomplete
OpenAPI error contract. The two most serious findings (the AD-15 race and the vacuous AC9
assertions) were each reproduced by direct execution, the race by running two interleaved
deactivations to completion, and the vacuous assertions by mutating the service so the last admin
really is deactivated while the test still passes.

**Decision needed** — 2, both resolved 2026-08-10 by Ron

- [x] [Review][Decision] **AD-15's last-admin guard is check-then-act and can be raced to zero
  active admins.** `_reject_if_last_active_admin` counts other active admins in a separate
  statement with no row lock, no serializable isolation, and no DB constraint behind it. Verified
  by execution: two concurrent deactivations (each admin deactivating the other) both pass the
  guard, both commit, and the database is left with **zero active admins**, permanently locking
  every `/api/admin/*` route with no in-app recovery. This is the single invariant the story
  exists to enforce. The story deliberately scoped out the *duplicate-username* race, but gave
  AD-15 no such carve-out, and AD-15's wording is absolute ("rejects any User update that would
  leave zero active Admins"). Options: (a) lock the active-admin rows before counting
  (`select(User.id).where(role==admin, is_active).order_by(User.id).with_for_update()`, then count
  excluding self, consistent lock order avoids deadlock), (b) add a DB-level constraint/trigger
  guaranteeing at least one active admin, (c) accept for v1 and document it as a known
  concurrency limit alongside AD-5. [backend/services/user_service.py:241-256] — **Resolved:
  option (a), lock the rows before counting.** The count now runs against an id-ordered
  `SELECT ... FOR UPDATE` over the active-admin rows, so a second concurrent transaction blocks
  until the first commits and then re-evaluates against the committed state. Consistent lock
  ordering by id means two admins deactivating each other serialize rather than deadlock. Chosen
  over the DB-constraint option because AD-1 puts business logic in `services/`, and over accepting
  the risk because the failure mode is an unrecoverable full lockout of user management, which is
  categorically worse than the last-write-wins races AD-5 knowingly tolerates for Order/Table edits.
- [x] [Review][Decision] **Usernames are neither trimmed nor case-normalized, so visually identical
  accounts can coexist and some are unusable.** Verified: with `chef` existing, `"CHEF"`, `"chef "`,
  `" chef"`, `"  "` and `"\t"` all return 201. Login is exact-match (`auth_service.py`), so
  `"chef "` is an account nobody can ever sign into, and a whitespace-only username is
  untypeable. Trimming is unambiguous and can be patched immediately; **case-insensitivity is the
  real decision**, because making creation case-insensitive without also folding case on the login
  path would let an Admin create `Casey` and leave that user unable to log in as `casey` — and the
  login path lives in `auth_service.py`, which this story listed as must-not-change. Options: (a)
  trim only (patch now), leave case-sensitivity as documented behavior, (b) trim + case-insensitive
  uniqueness, which requires touching the login query and a `lower(username)` unique index (schema
  change + migration), (c) trim now and raise case-folding as its own story.
  [backend/data_models/user.py:39-40, backend/services/user_service.py:44] — **Resolved: option
  (b), trim and case-insensitive, done in this story.**

  **Correction recorded, because the original framing of this finding was wrong.** The option
  presented to Ron claimed case-sensitivity was "documented, deliberate behavior." It is not.
  Searching `epics.md`, `docs/database-schema.md`, `project-context.md`, `ARCHITECTURE-SPINE.md`
  and `CLAUDE.md` turns up no statement about username case anywhere. The schema says only
  `username VARCHAR(50) NOT NULL UNIQUE` (`docs/database-schema.md:17`), and AC4 says only "a
  username that already exists" without defining equality. Case-sensitivity was therefore never a
  decision, just an emergent property of Postgres's default collation on a plain `UNIQUE` column.
  Ron challenged the claim, it did not survive checking, and the decision was made on the actual
  (silent) state of the spec.

  Consequences accepted with this choice: `auth_service.py`'s login lookup changes despite the
  story's original must-not-change list, and the story now ships an Alembic revision (a functional
  `UNIQUE INDEX ON users (lower(username))`) despite originally declaring no schema change. Both
  are recorded in the Change Log and File List. AD-4 is satisfied: the schema change ships its own
  revision. Note for any existing deployment: the migration will fail if two rows already differ
  only by username case, which is correct, those rows are exactly the ambiguity being closed.

**Patch** — 10

- [x] [Review][Patch] A well-formed password of >72 **bytes** but <=72 **characters** crashes the
  route with an unhandled `ValueError` (500, no `detail` body). Pydantic's `max_length` counts
  characters; `AuthService.hash_password` rejects on bytes. Verified: `"é" * 72` (72 chars, 144
  bytes) passes validation then raises out of the handler. Reachable with ~37 Hebrew or accented
  characters, which is an entirely ordinary password for this project's users. Both new hashing
  call sites are affected; `/api/auth/login` is immune only because `authenticate` neutralizes the
  oversize case explicitly. Fix with a byte-length `field_validator` on both password fields so it
  becomes the 422 AC3 already specifies. [backend/data_models/user.py:42, :73]
- [x] [Review][Patch] Both AC9 state assertions are vacuous and cannot fail. `db_session` is built
  with `expire_on_commit=False`, so the seeded `User` stays live in that session's identity map and
  a later `select(User)` returns the stale in-memory object rather than re-reading. Verified by
  mutation: moving `user.is_active = False; await db.commit()` *before* the guard, so the last
  admin genuinely is deactivated and the 409 is a lie, leaves
  `test_last_admin_lockout_on_deactivate` passing. The status code is the only thing actually
  pinning AC9. Fix by expiring/refreshing (or querying on a fresh connection) before asserting.
  [backend/tests/test_admin.py:238, :254]
- [x] [Review][Patch] Concurrent creation of the same username raises `IntegrityError` out of the
  handler as a 500 instead of the documented 409. The pre-insert existence check is not backed by a
  caught unique-constraint violation. The *race* was deliberately scoped out; returning a 500
  rather than the documented status was not. Wrap the commit and translate `IntegrityError` into
  `DuplicateUsernameError`. [backend/services/user_service.py:44-62]
- [x] [Review][Patch] The OpenAPI obligation inherited from Story 1.2 is only half-delivered. The
  403 is declared with a description but **no body schema** (`content` absent), and 401, 404 and
  409 are undocumented on every route. Verified against the live schema: all seven routes expose
  only `200/201`, `403`, `422`. Story 1.4's typed client therefore has no contract for the 409
  carrying `"Rejected, at least one admin must stay active"`, the one string an AC pins verbatim.
  Declare a shared error-body model and attach 401/404/409 per route.
  [backend/api/admin.py:27]
- [x] [Review][Patch] AC12's authorization tests cover 1 of 7 routes. Both the 403 and 401 tests hit
  only `GET /api/admin/users`, though Task 6 requires every route. All seven are correctly gated
  today (verified), so there is no live hole, but deleting `actor: AdminDep` from `deactivate_user`
  or `reset_password` would open every admin mutation to any authenticated waiter and leave the
  suite green. Parametrize over all seven. [backend/tests/test_admin.py:334-354]
- [x] [Review][Patch] `get_user` is the one rejection path that logs nothing, and the only service
  method not taking `actor`. All five by-id routes funnel their 404 through it, so id enumeration
  via `GET /api/admin/users/{n}` produces zero log lines. This directly violates the logging rule
  this story owns ("every service that rejects an action logs it through its injected loguru logger
  with the acting user id, starting with Story 1.3"). Thread `actor` through and log the rejection.
  [backend/services/user_service.py:86-99]
- [x] [Review][Patch] Move `MAX_PASSWORD_BYTES` instead of importing it mid-file. The current
  `from .auth import MAX_PASSWORD_BYTES  # noqa: E402` at line 33 sits between the ORM class and
  the schemas, load-bearing on `auth.py`'s `from .user import UserRole` resolving against a
  half-initialized module. Task 2 prescribed exactly this alternative ("if it causes one, move
  `MAX_PASSWORD_BYTES` instead"), and `project-context.md`'s Workflow section forbids
  lint-suppression comments for rules nothing enforces (there is no linter in this project). The
  constant is a bare `72`; moving it to `user.py` and having `auth.py` import it back makes the
  dependency one-directional. [backend/data_models/user.py:33]
- [x] [Review][Patch] `full_name` accepts whitespace-only values on both create and update
  (`min_length=1` is satisfied by `"   "`). Verified: `PATCH` with `{"full_name": "   "}` returns
  200 and persists it, and `UpdateUserRequest.at_least_one_field` treats it as a meaningful edit.
  Fold into the same strip-validator as the username trim. [backend/data_models/user.py:40, :52]
- [x] [Review][Patch] Deactivate/reactivate are silently idempotent and write an audit line for a
  state change that never happened. Verified: deactivating an already-deactivated user returns 200
  and logs `"User deactivated by admin_id=..."`. `update_user` likewise commits, refreshes and logs
  when the submitted values already equal the stored ones. Since the audit log is the only record
  this story produces of who did what, it should not claim transitions that did not occur.
  [backend/services/user_service.py:124-133, :167, :188-193]
- [x] [Review][Patch] `select(func.count()).where(User...)` relies on SQLAlchemy inferring the FROM
  clause from the WHERE columns. It is correct today, but the moment a predicate referencing a
  second table is added the statement silently becomes a cartesian product and the guard stops
  counting what it claims to. `select(func.count()).select_from(User)` costs nothing.
  [backend/services/user_service.py:242]

**Defer** — 3

- [x] [Review][Defer] An Admin password reset does not revoke the target's existing sessions
  [backend/services/user_service.py:216-221] — deferred, requires a schema change. Verified: the
  victim's pre-reset cookie still authenticates afterwards, because the JWT carries only `sub`/`exp`
  and nothing password-derived. The canonical reason to reset a password is a compromised account,
  so the attacker retains access for the remaining token lifetime (8h). AC7's "the old password
  stops working immediately" is satisfied for *login*, and no AC covers session revocation. The
  honest fix is a `token_version` column bumped on reset and checked in `get_current_user`, which
  means an Alembic migration and an AD-3 amendment, both outside this story's stated no-schema-change
  scope. The revocation seam already exists (`get_current_user` rejects inactive users), so the
  wiring is small once the column lands.
- [x] [Review][Defer] `GET /api/admin/users` is unbounded, with no limit, offset, or `is_active`
  filter [backend/services/user_service.py:92] — deferred, not a v1 problem. A restaurant's staff
  list is tens of rows. Worth noting that this endpoint is on the critical path for every admin
  screen (it is the only way the UI discovers user ids), and adding a cursor later is a breaking
  response-shape change, so it is better decided when Story 1.4 builds the actual Users screen.
- [x] [Review][Defer] An Admin can deactivate their own account and instantly destroy their own
  session [backend/services/user_service.py:162-171] — deferred, arguably correct behavior. AD-15
  still holds (it only permits this when another active Admin exists) and no AC forbids it, but a
  misclick on the wrong row is unrecoverable for that Admin, and it is only safe if someone
  actually holds the other Admin account's password. Worth a confirmation step in the Story 1.4 UI
  rather than a service-layer block.

## Dev Notes

### Architecture compliance

- **AD-1 (DI composition root).** `UserService` is a new `providers.Factory` in `container.py`,
  same shape as `auth_service`. `container.wire(modules=[...])` gains `"api.admin"`, appended not
  replacing (Task 5).
- **AD-3 (Auth).** Every admin route depends on `require_role(UserRole.admin)`, which itself
  depends on `CurrentUserDep` — no route in this story re-derives a user from the cookie or adds a
  second verification path.
- **AD-9 (Role-level-only permissions).** The guard is a pure role check
  (`Depends(require_role(UserRole.admin))`); nothing in this story filters by resource ownership.
- **AD-15 (Last-Admin lockout).** Implemented in `UserService`, not in the router or in
  `require_role` — it's a business rule on `User.role`/`User.is_active` mutations, which belongs
  in the service layer per AD-1's "services/ holds all business logic."
- **Dependency direction (architecture spine, 2026-08-08 clarification).** `api/admin.py` may
  import `UserRole`, `User` (type-only), and the Pydantic schemas from `data_models`; it must not
  query or mutate directly. All `db.execute`/`db.add`/`db.commit` calls live in `UserService`.

### Existing files this story modifies

| File | Current state | What changes |
|---|---|---|
| `backend/exceptions/__init__.py` | `AuthError` family (401) + `ForbiddenError` (403) | Add `ConflictError` + `DuplicateUsernameError` + `LastAdminLockoutError` (409), and `UserNotFoundError` (404) |
| `backend/main.py` | Two handlers registered (`AuthError`, `ForbiddenError`); `container.wire(modules=["api.auth", "api.dependencies"])` | Add `ConflictError` and `UserNotFoundError` handlers; append `"api.admin"` to the wire list |
| `backend/container.py` | `auth_service` Factory only | Add `user_service` Factory (`UserService`, `logger=logging`) |
| `backend/api/router.py` | Includes only `auth_router` | Also `include_router(admin_router)` |
| `backend/data_models/user.py` | `UserRole` enum + `User` ORM class only | Add `CreateUserRequest`, `UpdateUserRequest`, `ResetPasswordRequest`, `UserResponse` |
| `backend/data_models/__init__.py` | Exports through `auth.py`'s schemas | Also export the four new `user.py` schemas |

Files that must **not** change: `backend/services/auth_service.py` (identity verification stays
scoped there; password hashing is reused via its static method, not duplicated), `backend/api/
dependencies.py` (no new dependency needed, `require_role` already does everything this story
needs), `backend/alembic/**` (no schema change — `User`/`UserRole` already exist).

### New files

- `backend/services/user_service.py`
- `backend/api/admin.py`
- `backend/tests/test_admin.py`

### Project Structure Notes

- Imports relative to `backend/` as root, same as every prior story.
- `api/admin.py` is scoped to user-account administration specifically (the resource this story's
  AC12 names it for), not a generic admin catch-all for unrelated future features — menu
  management (Epic 2) gets its own `api/menu.py` per `CLAUDE.md`'s "one file per resource" rule,
  even though both are conceptually "Admin" work in the PRD's domain-module sense.
- Type hints on every signature. Docstrings on every function/class per `project-context.md`'s
  "Comments and docstrings" section, no em dash. `test_admin.py` skips docstrings and uses
  `# Arrange` / `# Act` / `# Assert` per the test-file carve-out.
- No new dependency, no `pyproject.toml`/`uv.lock` change expected.

### Testing

Backend harness is live: `uv run pytest` from `backend/`. Unlike `test_authorization.py` (which
tested `require_role` as a bare coroutine because no router existed yet), `test_admin.py` tests
through the real `client`/`db_session` fixtures and real HTTP calls, since `api/admin.py` is now a
real mounted router — follow `test_auth.py`'s conventions (the `_create_user` seeding helper,
hashing through `AuthService.hash_password`, reusing one `AsyncClient` across a login call and
subsequent authenticated calls since cookies persist automatically).

### References

- Story source: [Source: _bmad-output/planning-artifacts/epics.md#Story 1.3]
- Last-Admin rule: [Source: ARCHITECTURE-SPINE.md#AD-15] — "the service layer rejects any User
  update (deactivation, role change) that would leave zero active Admins in the system"
- Permissions model: [Source: ARCHITECTURE-SPINE.md#AD-9] — Role-level-only, no per-resource
  filtering
- Dependency-direction clarification: [Source: ARCHITECTURE-SPINE.md, "Rule (dependency
  direction)", 2026-08-08 addition] — `api/` may import type-level names from `data_models/`, not
  query or mutate
- FR text: [Source: epics.md#FR-3] — full create/edit/reset/deactivate/reactivate scope
- UX copy for the lockout rejection: [Source: epics.md#UX-DR17] — exact string "Rejected, at least
  one admin must stay active"
- Prior-story handoff (guard + exception, ready to consume): [Source:
  _bmad-output/implementation-artifacts/1-2-role-based-authorization-enforcement.md#Dev Notes] —
  `require_role(*roles)` usage (`Depends(require_role(UserRole.admin))`), `ForbiddenError` shape
- Prior-story handoff (deferred obligations owned by this story): [Source:
  _bmad-output/implementation-artifacts/deferred-work.md#code review of story-1-2] — OpenAPI 403
  documentation gap; "every service that rejects an action logs it through its injected loguru
  logger with the acting user id, starting with Story 1.3's user-management service"
- Password hashing seam: [Source: backend/services/auth_service.py#hash_password] — "the single
  hashing seam for the whole system. Story 1.3 creates and resets passwords through this"
- Conventions: [Source: _bmad-output/project-context.md] — trap 8 (require_role built, not yet
  used; two obligations land on the first protected route), "Where code goes" (api/ may import
  types from data_models/), comment/docstring rules, Testing section

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (Claude Code, bmad-dev-story workflow)

### Debug Log References

Followed the story's tasks in written order. Verified the circular-import risk flagged in Task
2 (`data_models/user.py` importing `MAX_PASSWORD_BYTES` from `data_models/auth.py`, which itself
imports `UserRole` from `user.py`) actually occurs when the import sits at module top; fixed by
moving that one import to just above the new schema classes, after `User`/`UserRole` are already
defined, so `auth.py`'s `from .user import UserRole` resolves against the partially-initialized
`user` module in `sys.modules`. Confirmed via `uv run python -c "import data_models"`.

`uv run pytest tests/test_admin.py -v` failed 18/20 on the first run, all with 401 instead of the
expected status. Root cause: `tests/conftest.py`'s `client` fixture used `base_url="http://test"`.
The login cookie is `Secure`-flagged (AD-3); httpx enforces `Secure` literally against the request
scheme with no browser-style localhost exemption, so it silently dropped the cookie on every
request after login. Story 1.1 never hit this (it only asserted the `Set-Cookie` header on the
login response itself) and Story 1.2 never hit it either (its tests used
`dependency_overrides` instead of a real login). Story 1.3 is the first to log in and then make a
second authenticated call through the real `client` fixture, so it's the first to expose this.
Fixed by changing the fixture's `base_url` to `https://test` (the ASGI transport does not perform
real TLS, so this only affects how httpx's cookie jar reasons about the `Secure` attribute).
Re-ran the full suite after the fix: 71 passed, no regressions.

### Completion Notes List

**What was built.** The first real domain router (`backend/api/admin.py`) and the first live use
of Story 1.2's `require_role` guard. A `UserService` (`backend/services/user_service.py`) handling
create/list/get/update/deactivate/reactivate/reset-password, registered in `container.py` as a
`providers.Factory` alongside `auth_service`. Four new exceptions
(`ConflictError`/`DuplicateUsernameError`/`LastAdminLockoutError` -> 409,
`UserNotFoundError` -> 404) with their own handlers in `main.py`, matching the existing
`AuthError`/`ForbiddenError` shape. Four new Pydantic schemas in `data_models/user.py`
(`CreateUserRequest`, `UpdateUserRequest`, `ResetPasswordRequest`, `UserResponse`).
`container.wire(modules=[...])` gained `"api.admin"`, appended not replacing.

**Both obligations this story owed from Story 1.2's review are done.** Every route in
`api/admin.py` declares `responses={403: {...}}`, verified by asserting `"403"` is a key in
`app.openapi()["paths"]["/api/admin/users"]["post"]["responses"]`. `UserService` logs every
rejection (duplicate username, last-admin lockout) through its injected logger with the acting
admin's id, threaded through every method as an `actor: User` parameter.

**Design decisions worth knowing:**

1. **No Repository class.** `UserService` queries the database directly via `db.execute`/`db.get`,
   matching `AuthService`'s existing, real precedent rather than introducing a new abstraction the
   story doesn't need.
2. **AD-15 last-admin check is one shared private method** (`_reject_if_last_active_admin`),
   called from both `deactivate_user` and the demotion branch of `update_user`, so the exact same
   "count other active Admins" query and rejection message back both code paths rather than being
   duplicated.
3. **List/get endpoints were added as scoped-and-flagged supporting infrastructure**, not a hidden
   scope expansion: no AC states them, but there is no other way for an Admin to discover a
   User's id to edit/deactivate/reactivate/reset. Called out explicitly in the story's Scope note
   before implementation, not decided ad hoc mid-task.
4. **AC10 (historical attribution) shipped no code.** No domain service yet writes a row carrying
   a User foreign key (Order/StockMovement don't exist until Epic 3-5), so there is nothing to
   attribute yet; the schema's plain FK-by-id (never a copied name/role snapshot) already
   guarantees it structurally.
5. **Test-harness fix included:** `tests/conftest.py`'s `client` fixture `base_url` changed from
   `http://test` to `https://test` so the `Secure` session cookie survives a second request on the
   same client. See Debug Log References for why this was necessary and out of this story's
   original file list, but required for the story's own tests (and any future story that logs in
   and then makes a further authenticated call) to work at all.

**Deferred, as scoped.** AC11 (Users screen UI) ships no code, per the story's Scope note: no MUI,
routing, or frontend auth context exists yet (Story 1.4).

### File List

**Added**

- `backend/services/user_service.py`
- `backend/api/admin.py`
- `backend/tests/test_admin.py`

**Modified**

- `backend/exceptions/__init__.py` (added `ConflictError`, `DuplicateUsernameError`,
  `LastAdminLockoutError`, `UserNotFoundError`)
- `backend/main.py` (added `_conflict_error_handler` and `_user_not_found_error_handler`,
  registered both; appended `"api.admin"` to `container.wire(modules=[...])`)
- `backend/container.py` (added `user_service` Factory provider)
- `backend/api/router.py` (added `include_router(admin_router)`)
- `backend/data_models/user.py` (added `CreateUserRequest`, `UpdateUserRequest`,
  `ResetPasswordRequest`, `UserResponse`)
- `backend/data_models/__init__.py` (exported the four new schemas)
- `backend/tests/conftest.py` (`client` fixture `base_url` changed from `http://test` to
  `https://test`; see Debug Log References)

**Confirmed unchanged**: `backend/services/auth_service.py`, `backend/api/dependencies.py`,
`backend/alembic/**`, all frontend files, `pyproject.toml`/`uv.lock` (no new dependency was
needed).

### Files changed by the code-review patch pass (2026-08-10)

**Added**

- `backend/alembic/versions/f1743862f1b1_add_case_insensitive_unique_index_on_.py` (functional
  `UNIQUE INDEX ON users (lower(username))`, from Decision 2; the story originally declared no
  schema change, AD-4 satisfied by shipping the revision)
- `backend/data_models/errors.py` (`ErrorResponse`, the body schema every documented error status
  now carries)

**Modified**

- `backend/services/user_service.py` (row-locking last-admin guard, case-insensitive duplicate
  check, `IntegrityError` to 409, `actor` threaded into `get_user` plus its rejection log,
  no-op idempotency on deactivate/reactivate/update)
- `backend/data_models/user.py` (`MAX_PASSWORD_BYTES` moved here from `auth.py`, removing the
  mid-file import and its `# noqa`; byte-length password validator; strip-and-reject-blank
  validators on `username`/`full_name`; functional index declared in `__table_args__`)
- `backend/data_models/auth.py` (imports `MAX_PASSWORD_BYTES` from `user.py` instead of defining it)
- `backend/data_models/__init__.py` (re-exports moved constant and new `ErrorResponse`)
- `backend/services/auth_service.py` (case-insensitive, whitespace-trimmed login lookup, the
  must-not-change exception Decision 2 explicitly accepted)
- `backend/api/admin.py` (`_errors()` helper replacing `_FORBIDDEN_RESPONSE`; every route now
  declares 401/403/404/409 as applicable, each with `ErrorResponse` as its body schema)
- `backend/tests/test_admin.py` (20 tests to 56: vacuous AC9 assertions replaced with raw-SQL reads
  past the identity map, authorization parametrized across all seven routes and three non-admin
  roles, plus new coverage for the race, multi-byte passwords, trimming, blank rejection,
  case-insensitive create and login, hash rotation, idempotency, and read-endpoint leakage)

## Change Log

| Date | Change |
|---|---|
| 2026-08-10 | Added `ConflictError`/`DuplicateUsernameError`/`LastAdminLockoutError` (409) and `UserNotFoundError` (404) to `backend/exceptions/__init__.py`, with matching handlers in `main.py`, following the existing `AuthError`/`ForbiddenError` shape. |
| 2026-08-10 | Added `CreateUserRequest`, `UpdateUserRequest`, `ResetPasswordRequest`, `UserResponse` to `backend/data_models/user.py`, exported from `data_models/__init__.py`. |
| 2026-08-10 | Added `backend/services/user_service.py` (`UserService`): create/list/get/update/deactivate/reactivate/reset-password, with AD-15's last-admin lockout guard shared between deactivation and role-demotion, and denial logging with the acting admin's id (the obligation Story 1.2's review deferred here). Registered as a `providers.Factory` in `container.py`. |
| 2026-08-10 | Added `backend/api/admin.py`, the first real domain router and the first live use of `require_role`. Every route declares `responses={403: {...}}` (the other obligation deferred from Story 1.2). Included into `api/router.py`; `"api.admin"` appended to `container.wire(modules=[...])`. |
| 2026-08-10 | Added `backend/tests/test_admin.py`, 20 tests covering every AC through real HTTP calls against the mounted router (create/duplicate/missing-password, deactivate/reactivate, password reset, last-admin lockout on both deactivate and demote, non-admin 403, unauthenticated 401, OpenAPI 403 documentation). |
| 2026-08-10 | Fixed `backend/tests/conftest.py`'s `client` fixture (`base_url` `http://test` -> `https://test`): the `Secure`-flagged session cookie was being silently dropped by httpx on any request after login, since httpx (unlike a browser) has no localhost exemption for `Secure` cookies over plain http. Latent since Story 1.1; first exposed by this story's tests, the first to log in and then make a further authenticated call on the same client. |
| 2026-08-10 | Full regression suite: 71 passed, 0 failed, no regressions in `test_auth.py`, `test_authorization.py`, `test_health.py`, `test_container.py`, `test_migrations.py`. |
| 2026-08-10 | Applied bmad-code-review findings (3-layer parallel Opus review: 2 decisions resolved, 10 patches, 3 deferred, 5 dismissed). Two findings were severe and both were reproduced by direct execution before being accepted. |
| 2026-08-10 | **AD-15 was breachable and is now closed (Decision 1).** `_reject_if_last_active_admin` counted other active admins with an unlocked `SELECT`, so two admins deactivating each other concurrently both passed the guard and both committed, leaving **zero active admins** and permanently locking every `/api/admin/*` route. Reproduced by running two interleaved deactivations to completion. The guard now locks the active-admin rows with an id-ordered `SELECT ... FOR UPDATE` before counting, so the second transaction waits and then re-evaluates. `tests/test_admin.py::test_concurrent_deactivations_cannot_remove_the_last_admin` runs the real race and asserts exactly one rejection; verified by mutation that reverting to the bare count fails it. |
| 2026-08-10 | **Both AC9 state assertions were vacuous and could never fail.** `db_session` uses `expire_on_commit=False`, so the seeded `User` stayed live in the identity map and `select(User)` returned the stale object rather than re-reading. Proven by mutating `deactivate_user` to commit *before* the guard: the last admin really was deactivated, the 409 was a lie, and the test still passed. Assertions now read through raw SQL past the identity map, and that same mutation now fails. |
| 2026-08-10 | A password of ≤72 characters but >72 bytes (any ~37 Hebrew or accented characters) passed Pydantic's character-counting `max_length` and then raised `ValueError` out of `hash_password` as an unhandled 500. Replaced the character bound with a byte-length `field_validator` on both password fields, so it is now the 422 AC3 specifies. All three review layers found this independently. |
| 2026-08-10 | **Usernames are now trimmed and case-insensitive (Decision 2).** Previously `"CHEF"`, `"chef "`, `" chef"` and `"   "` all created separate accounts alongside `"chef"`, and since login was exact-match, `"chef "` was an account nobody could ever sign into. Added strip-and-reject-blank validators on `username`/`full_name`, a case-insensitive duplicate check, a matching case-insensitive login lookup in `auth_service.py`, and a functional `UNIQUE INDEX ON users (lower(username))` so the database is the final arbiter. **The original review write-up claimed case-sensitivity was documented, deliberate behavior; that was wrong.** Ron challenged it, and a search of `epics.md`, `docs/database-schema.md`, `project-context.md`, `ARCHITECTURE-SPINE.md` and `CLAUDE.md` found no statement about username case anywhere. It was an emergent property of Postgres's default collation, never a decision. |
| 2026-08-10 | Concurrent creation of the same username surfaced `IntegrityError` as a 500 instead of the documented 409. The unique index is now treated as the real arbiter and its violation translated into `DuplicateUsernameError`. |
| 2026-08-10 | Completed the OpenAPI obligation inherited from Story 1.2, which had only been half-delivered: the 403 carried a description but no body schema, and 401/404/409 were undocumented everywhere. Added `ErrorResponse` and an `_errors()` helper; all seven routes now declare every error status they can return, each with a body schema. The test asserts body schemas exist rather than just checking that `"403"` is a key. |
| 2026-08-10 | Authorization coverage went from 1 route to all 7, parametrized across all three non-admin roles plus the unauthenticated case (21 + 7 cases). Verified by mutation: replacing `AdminDep` with `CurrentUserDep` on `reset_password` alone, which would let any waiter reset any user's password, now fails 3 tests where the old single-route test stayed green. |
| 2026-08-10 | `get_user` was the only rejection path that logged nothing and the only service method without `actor`, despite all five by-id routes funnelling their 404 through it. Threaded `actor` through and logged the rejection, closing the last gap in the logging obligation this story owns. |
| 2026-08-10 | Deactivate/reactivate/update no longer commit and write an audit line for a state change that did not happen. Since the log is the only record this service produces of who did what, it must not claim transitions that never occurred. |
| 2026-08-10 | Moved `MAX_PASSWORD_BYTES` from `auth.py` to `user.py`, removing the mid-file import and its `# noqa: E402`. This is what Task 2 originally prescribed, and `project-context.md` forbids lint-suppression comments for rules no configured linter enforces. The dependency between the two modules is now one-directional. |
| 2026-08-10 | Full regression suite after the patch pass: **107 passed** (71 to 107), reproducibly green across repeated fresh-database runs. |
