---
baseline_commit: c7ebf222e1e612efab2e1d6fa975252922e879b7
---

# Story 1.2: Role-Based Authorization Enforcement

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the system,
I want to restrict every state-changing action to the Roles permitted to perform it,
so that no User can perform actions outside their Role.

**Scope note.** This story is backend-only, same pattern as Story 1.1. It builds the reusable
`require_role(...)` FastAPI dependency that every future domain router (`admin` in Story 1.3,
`orders`/`kitchen`/`inventory`/`smart_chef` from Epic 2 onward) will depend on to gate its
mutating routes. **No domain router except `auth` (public) exists yet**, so there is nothing to
attach `require_role` to in this story, the same situation Story 1.1 was in with `CurrentUserDep`.
Do not add a placeholder protected route just to exercise it; prove the dependency directly with
tests, matching Story 1.1's precedent for `AuthService.get_current_user`.

The AC below about the frontend only surfacing permitted actions (FR-2's UI clause) is **not**
implemented by this story. There is no frontend routing, shell, or auth context yet (Story 1.4
builds those), and v1's information architecture has no shared multi-role screen where the same
page needs to conditionally hide one role's actions from another, every IA surface already belongs
to exactly one role. That AC is satisfied structurally once Story 1.4 ships per-role navigation
and each later story builds only its own role's screen; nothing further needs to be added on top
for it. Do not build a frontend permissions utility or component here, it would be speculative
scope this story's ACs don't actually require yet.

## Acceptance Criteria

**AC1 — Forbidden role rejected**
Given an authenticated User whose Role is not permitted for a given action,
When they attempt it,
Then the system returns an explicit unauthorized (403) response and the action does not execute
(FR-2).

**AC2 — Unauthenticated request rejected**
Given an unauthenticated request to any non-public action,
When it is made,
Then it is rejected, not silently allowed (FR-2, NFR-2).

**AC3 — Frontend surfaces only permitted actions**
Given the current User's Role,
When the frontend renders any screen,
Then only actions permitted to that Role are shown as available (FR-2).
_Deferred by design, see Scope note above. No frontend code ships in this story; tracked as
satisfied structurally by Story 1.4's per-role navigation and each later story's role-scoped
screens._

**AC4 — One shared dependency, never re-derived**
Given any protected route in any domain router,
When its authorization is enforced,
Then it goes through one shared FastAPI dependency, never re-derived per route (AD-3).

## Tasks / Subtasks

- [x] **Task 1: ForbiddenError exception** (AC: 1)
  - [x] Add `ForbiddenError(Exception)` to `backend/exceptions/__init__.py`, as its own class, **not**
    a subclass of `AuthError` (that family is reserved for 401s per its docstring: "every
    authentication failure"). A role mismatch is an *authorization* failure on an already-verified
    identity, a distinct case (401 vs 403) that must stay visibly distinct in the exception
    hierarchy.
    ```python
    class ForbiddenError(Exception):
        """Raised when an authenticated User's Role is not permitted for the attempted action.

        Distinct from AuthError: the caller's identity is already verified,
        only their Role lacks permission. Maps to 403, never 401.
        """

        detail = "You do not have permission to perform this action"
    ```
  - [x] Register a FastAPI exception handler in `main.py` mapping `ForbiddenError` to a `403`
    response body `{"detail": exc.detail}` (mirror `_auth_error_handler`'s shape exactly, a second
    small handler function, e.g. `_forbidden_error_handler`, registered via
    `app.add_exception_handler(ForbiddenError, _forbidden_error_handler)` alongside the existing
    `AuthError` registration). Do not fold this into the existing `AuthError` handler, the status
    code differs (403 vs 401) and the two failure modes must stay independently testable.

- [x] **Task 2: `require_role` dependency factory** (AC: 1, 2, 4)
  - [x] Add to `backend/api/dependencies.py`, directly below the existing `CurrentUserDep`:
    ```python
    def require_role(*roles: UserRole) -> Callable[[User], Coroutine[Any, Any, User]]:
        async def _check_role(user: CurrentUserDep) -> User:
            if user.role not in roles:
                raise ForbiddenError()
            return user

        return _check_role
    ```
    (adjust the typing imports as needed; the exact return-type annotation is not load-bearing,
    keep it precise but do not over-engineer it)
  - [x] Import `UserRole` from `data_models` and `ForbiddenError` from `exceptions` at the top of
    the file
  - [x] Usage from a future router: `Depends(require_role(UserRole.admin))`, or
    `Depends(require_role(UserRole.waiter, UserRole.cook, UserRole.admin))` for a multi-role action
    like FR-7's cancel. This story does not add any such usage, no domain router exists yet to add
    it to (Task 3 covers why AC2 needs no new code).
  - [x] **Why this satisfies AD-4/AC4 without re-deriving anything:** `_check_role`'s parameter is
    typed `CurrentUserDep` (`Annotated[User, Depends(get_current_user)]`), the exact same shared
    seam Story 1.1 built. FastAPI resolves that inner dependency first, `require_role` only adds a
    role check on top of an already-authenticated `User`, it never re-reads the cookie or re-verifies
    the token itself.
  - [x] **Why AC2 needs no new code:** because `require_role`'s returned function requires
    `CurrentUserDep` to resolve first, FastAPI's dependency graph rejects an unauthenticated request
    with `NotAuthenticatedError` (existing 401, Story 1.1) before `_check_role`'s body ever runs. An
    unauthenticated caller never reaches the role check, it is rejected one layer earlier by
    machinery this story reuses rather than duplicates.

- [x] **Task 3: Tests** (AC: all)
  - [x] Create `backend/tests/test_authorization.py`. No domain router exists yet to hit over HTTP
    (same situation Story 1.1 was in for `get_current_user`), so test `require_role`'s returned
    callable directly, constructing plain `User` instances in memory (no DB needed, `require_role`
    never touches the database):
    - A User whose role is in the allowed set is returned unchanged, no exception raised (AC1
      happy path)
    - A User whose role is not in the allowed set raises `ForbiddenError` (AC1)
    - `require_role` accepts multiple roles and permits any one of them (needed for FR-7's
      Waiter-or-Cook-or-Admin cancel pattern later)
    - `require_role()` with zero roles passed rejects every role, an explicit test pinning this
      edge case so a future caller cannot accidentally build an all-permitting guard by forgetting
      arguments
  - [x] Add one test asserting `ForbiddenError.detail` round-trips through a raised-and-caught
    exception (cheap regression pin, mirrors how `test_auth.py` pins `InvalidCredentialsError`'s
    message)
  - [x] Add an app-level test for the exception handler itself: construct a `Request`-free direct
    call is not possible for a registered FastAPI handler, so instead register a **test-local**
    throwaway route on a **separate `FastAPI()` test app instance** (not `main.app`) that
    unconditionally raises `ForbiddenError`, mount the same handler function, and assert the
    response is `403` with the expected `detail` body. This proves the handler wiring without
    adding a placeholder route to the real application (mirrors the spirit of Story 1.1's
    "test the dependency directly" rule, applied to the handler instead of a live protected route).
  - [x] Regression check: run the full existing suite (`uv run pytest`) to confirm nothing in
    `test_auth.py`, `test_health.py`, `test_container.py`, `test_migrations.py` regresses, this
    story touches shared files (`exceptions/__init__.py`, `main.py`) that those tests also exercise

### Review Findings

Reviewed 2026-08-08 by three parallel Opus reviewers (Blind Hunter, Edge Case Hunter, Acceptance
Auditor) against `c7ebf22..working tree` scoped to `backend/`. Every finding below was
independently re-verified against the code before being rated; subagent severities were discarded.

**All three reviewers independently confirmed the mechanism itself is correct.** Mounted on a real
route against the real `create_app()`, with a real login cookie and all four `UserRole` members:
403 for a disallowed role, 200 for a permitted one, 401 (not 403) for an unauthenticated caller,
route body never executed, and `get_current_user` resolved exactly once per request even when a
route uses both `CurrentUserDep` and two `require_role(...)` dependencies. AD-3/AC4's "never
re-derived" claim holds in fact. Every finding below is about what the tests do not prove, what
the code does not say, and how the factory can be misused later.

**Decision needed** — 2, both resolved 2026-08-08 by Ofek

- [x] [Review][Decision] Authorization denials produce no log line, while every sibling auth
  rejection path logs one. `project-context.md` mandates logging "at every layer... carry
  identifying context (user id) so a flow can be traced end to end", and `AuthService` complies at
  `services/auth_service.py:109,113,116,205`. `api/dependencies.py:74-75` raises `ForbiddenError()`
  silently, so a user probing admin-only routes leaves no server-side trace while a single mistyped
  password leaves one. The ambiguity is where authorization denials belong: nothing under
  `backend/api/` logs today, and the project rule also says route handlers stay thin. Options: (a)
  `@inject` the container logger into `_check_role` the way `get_current_user` injects
  `auth_service`, (b) leave `api/` non-logging and make each service log its own denials from
  Story 1.3 onward, (c) accept the gap for v1. [backend/api/dependencies.py:74] — **Resolved:
  option (b), the service layer owns denial logging.** No code change in this story. `api/` stays
  thin and non-logging, consistent with every file under it today and with the project rule that
  route handlers validate, call a service, and return. `require_role` is a coarse pre-filter; the
  meaningful audit record is the one the service writes when it rejects or performs a domain
  action, with the domain context (order id, ingredient name) that makes a log line worth reading.
  A bare "role X was denied" from a dependency has none of that. **Standing rule from here:** every
  service that rejects an action logs it through its injected loguru logger with the acting user
  id, starting with Story 1.3's user-management service. Carried into `deferred-work.md` so 1.3
  picks it up.
- [x] [Review][Decision] `api/dependencies.py` now imports the raw `UserRole` enum from
  `data_models`, reversing a resolution Story 1.1's review explicitly recorded as closed. The
  architecture spine states "`api/` may depend on `services/` only"; Story 1.1 adjudicated exactly
  this and moved `LoginRequest`/`LoginResponse` into `data_models/auth.py` so that "`api/auth.py`
  imports only Pydantic schemas from `data_models` now", setting the stated pattern for Story 1.2
  onward. This story's spec instructed the import (Task 2) and its Architecture-compliance section
  asserts AD-1/AD-3/AD-9 compliance without acknowledging the reversal. Partially mitigated:
  `dependencies.py` already imported `User` from `data_models` before this story. Options: (a)
  accept it and amend the spine's wording, since a role guard fundamentally needs the role enum and
  the spine itself describes `data_models` as "SQLAlchemy models & Pydantic schemas", (b) re-export
  `UserRole` through a schema module so `api/` imports a schema not an ORM enum, (c) relocate
  `require_role`. [backend/api/dependencies.py:9] — **Resolved: option (a), accept the import and
  amend the spine.** An authorization guard's whole job is comparing against the role enum, so
  routing that through a re-exported alias would add indirection purely to satisfy a rule the
  spine's own wording does not actually impose: it describes `data_models/` as "SQLAlchemy models &
  Pydantic schemas" and the dependency-direction rule was written to stop business logic and
  queries leaking upward, not to ban a type import. `dependencies.py` already imported `User` from
  `data_models` before this story. Converted to a Patch below: amend the spine to say plainly what
  `api/` may take from `data_models`, so the next story does not relitigate this a third time.

**Patch** — 8 (7 from review, 1 converted from the resolved decision above)

- [x] [Review][Patch] Amend the architecture spine's dependency-direction rule to state explicitly
  that `api/` may import Pydantic schemas and type-level declarations (enums like `UserRole`, ORM
  classes used purely as type annotations) from `data_models`, while business logic and all
  querying stay in `services/`. Story 1.1's review and now Story 1.2's have each spent a decision
  cycle on this same ambiguity; the fix is to write the rule down, not to re-adjudicate it a third
  time (converted from Decision 2).
  [ARCHITECTURE-SPINE.md#Design Paradigm, the "Rule (dependency direction)" paragraph]

- [x] [Review][Patch] Every `require_role` test bypasses FastAPI's dependency graph, so the story's
  central invariant has zero executing coverage. All four tests call `await checker(user)` with a
  positional `User`, which never reads the `CurrentUserDep` annotation. Verified by mutation:
  replacing the parameter annotation with a plain `User`, destroying the "layered on the one shared
  seam, never re-derived" property that is the entire point of the story, leaves all four tests
  passing. AC4 is unprotected against regression, AC1's "and the action does not execute" clause is
  never asserted, and AC2 has no test at all (it is closed by prose argument in the story). The
  story already blessed the pattern that fixes this: a throwaway `FastAPI()` instance plus
  `app.dependency_overrides[get_current_user]`, needing no DB and no placeholder route in
  `main.app`. [backend/tests/test_authorization.py:55-99]
- [x] [Review][Patch] `create_app()`'s `ForbiddenError` handler registration is untested; deleting
  it turns every role denial into a 500 with a fully green suite. The handler test builds its own
  `test_app = FastAPI()` and registers the handler by hand, so it structurally cannot observe the
  real app losing its registration. Verified by mutation: removing the registration yields
  `500 Internal Server Error` on a raised `ForbiddenError` while `pytest tests/test_authorization.py`
  still reports 6 passed. Story 1.3's first `require_role` route would ship 500s on every forbidden
  action with a green suite. [backend/main.py:103, backend/tests/test_authorization.py:36]
- [x] [Review][Patch] `require_role(*roles)` never validates that its arguments are `UserRole`
  members, and a non-member argument silently produces a permanent deny-all. `UserRole` is a plain
  `enum.Enum`, not `(str, Enum)`, so `UserRole.admin == "admin"` is `False` (re-verified in the
  project venv). `require_role("admin")` (the natural typo, since the enum's values are exactly
  those strings) therefore denies a real admin, and `require_role([UserRole.admin])` (brackets
  instead of varargs) denies everyone. Nothing surfaces either: no error at import, at route
  registration, or at request time, just a 403 reading "you do not have permission". There is no
  static gate to catch it either, no CI and no mypy/ruff config anywhere, so the `*roles: UserRole`
  annotation is documentation only. Guard at factory time with an `isinstance` check raising
  `TypeError`. [backend/api/dependencies.py:44,74]
- [x] [Review][Patch] The Change Log overclaims test coverage, the same class of finding raised
  against Story 1.1. It states the tests cover "unauthenticated-by-construction" and "the
  shared-dependency composition"; neither has an executing test. Correct the wording (the claim
  becomes true once the first patch above lands).
  [_bmad-output/implementation-artifacts/1-2-role-based-authorization-enforcement.md, Change Log]
- [x] [Review][Patch] `Depends(require_role)` with the factory left uncalled registers successfully
  and silently becomes a required query parameter instead of an authorization check. FastAPI reads
  the `*roles: UserRole` var-positional as a query param and publishes it in the OpenAPI schema:
  verified `422 {"loc":["query","roles"]}` with no query string, and `500 TypeError: require_role()
  got an unexpected keyword argument 'roles'` with `?roles=admin`. It fails closed, so this is not
  a bypass, but it is the one misuse the factory shape makes easy and startup cannot catch (by
  contrast, dropping the `CurrentUserDep` annotation does fail loudly at startup). Cheapest
  mitigation is an explicit call-me-do-not-pass-me line in the docstring.
  [backend/api/dependencies.py:44]
- [x] [Review][Patch] Task 3's "raised-and-caught" subtask was checked off but delivered as a plain
  attribute read: `error = ForbiddenError()` then `assert error.detail == ...`, never raised, never
  caught. Intent is covered elsewhere by the handler test asserting the string in a real 403 body,
  but the subtask as written was not performed. [backend/tests/test_authorization.py:23-28]
- [x] [Review][Patch] `warehouse_manager`, the fourth `UserRole` member, is never exercised. Tests
  cover `admin`, `waiter` and `cook` only. [backend/tests/test_authorization.py]

**Defer** — 2

- [x] [Review][Defer] 403 is invisible in the OpenAPI schema. Because `ForbiddenError` is a bare
  `Exception` rather than an `HTTPException`, FastAPI cannot infer it and no `responses={403: ...}`
  is declared; a `require_role`-protected route documents only `200`. The frontend from Story 1.4
  onward, reading `/docs` or generating a client, sees no 403 contract for routes whose purpose is
  returning one. [backend/exceptions/__init__.py:47] — deferred, nothing to annotate until the
  first real protected route exists (Story 1.3).
- [x] [Review][Defer] `ForbiddenError("some specific reason")` silently discards the message and
  `str(ForbiddenError())` is `''`, so an escaped traceback shows a bare class name. `detail` is a
  class attribute with no `__init__` override. [backend/exceptions/__init__.py:54] — deferred,
  pre-existing: the entire `AuthError` family added by Story 1.1 has exactly this shape, so fixing
  it properly means changing that family too, not just this story's addition.

**Dismissed as noise (4):** `sprint-status.yaml` missing from the File List (Story 1.1's File List
omits it too, it is workflow tracking mutated by the workflow itself, not a story deliverable);
AC3's deferred obligation being untracked (the auditor verified Story 1.4's AC in `epics.md`
genuinely carries FR-2's UI clause, and `EXPERIENCE.md` confirms every non-Login surface belongs to
exactly one role); two byte-identical handlers in `main.py` wanting a shared base (the split was a
deliberate, reasoned design decision and a shared abstraction over two cases is premature); the
test helper building a session-less ORM `User` (harmless by design, since AD-9 fixes the guard to
reading one plain column).

## Dev Notes

### Architecture compliance

- **AD-3 (Auth).** `require_role` is layered strictly on top of `CurrentUserDep`
  (`AuthService.get_current_user` via `api/dependencies.py::get_current_user`), the one shared
  dependency Story 1.1 built. This story adds a second composable dependency on top of it, it does
  not add a second way to verify a session. "Role is checked in that same dependency layer, never
  re-derived per route" (architecture spine, Consistency Conventions) is satisfied because
  `require_role`'s check happens inside the dependency graph, not inside a route handler body.
- **AD-9 (Role-level-only permissions).** `require_role`'s check is `user.role not in roles`, a
  pure Role comparison with no per-resource/per-user filtering. Do not parameterize it with
  anything beyond `UserRole` values, per-resource scoping is explicitly out of scope for the whole
  system (PRD §5 Non-Goals, AD-9).
- **AD-1 (DI composition root).** No new `container.py` provider is needed, `require_role` has no
  constructor dependencies (no config, no logger, no DB), it is a plain function factory, not a
  container-managed service. No change to `container.wire(modules=[...])` either, this story adds
  no new `@inject`-decorated route, `api.dependencies` is already in that list from Story 1.1's
  patch pass.
- **NFR-2 (universal authorization).** As with Story 1.1's AD-3 compliance note: this story wires
  the *mechanism* only. There are still no protected domain routes to apply it to. Story 1.3 (Admin
  manages user accounts) is the first story that will actually call `Depends(require_role(...))`
  on a real route.

### Existing files this story modifies

| File | Current state | What changes |
|---|---|---|
| `backend/exceptions/__init__.py` | `AuthError` base + `InvalidCredentialsError`, `SessionExpiredError`, `NotAuthenticatedError`, all 401 | Add `ForbiddenError`, a sibling class (not an `AuthError` subclass), for 403 |
| `backend/api/dependencies.py` | `get_current_user` + `CurrentUserDep` only | Add `require_role(*roles)` factory below the existing code, new imports for `UserRole` and `ForbiddenError` |
| `backend/main.py` | One `AuthError` handler registered via `app.add_exception_handler` | Add a second handler for `ForbiddenError` mapping to 403, registered the same way |

Files that must **not** change: `backend/services/auth_service.py` (role-checking is an
authorization concern, layered above authentication; `AuthService` stays scoped to identity
verification only), `backend/container.py` (no new provider needed), `backend/data_models/**` (no
schema change, `User.role` already exists), `backend/api/router.py` (no new router to include yet).

### New files

- `backend/tests/test_authorization.py`

### Project Structure Notes

- Imports relative to `backend/` as root, same as every prior story.
- `require_role` lives in `api/dependencies.py` next to `CurrentUserDep`, not in `services/`, it is
  pure request-authorization glue with no business logic and no DB access, matching
  `dependencies.py`'s existing single-purpose role in the source tree (architecture spine:
  `api/` → `services/`, `dependencies.py` is the `api/`-layer seam, not a service).
- Type hints on every signature. Docstrings on every function/class per `project-context.md`'s
  "Comments and docstrings" section, no em dash in any docstring or comment. `test_authorization.py`
  skips docstrings and uses `# Arrange` / `# Act` / `# Assert` per the test-file carve-out.
- No new dependency, no `pyproject.toml`/`uv.lock` change expected.

### Testing

Backend harness is live: `uv run pytest` from `backend/`. `require_role`'s tests need no database
fixture (`db_session`/`client`/`migrated_database` are all unnecessary here, plain in-memory `User`
objects are enough since the function only reads `.role`), keep them fast and fixture-free except
for the one handler-wiring test in Task 3, which needs its own throwaway `FastAPI()` instance (not
`db_session` or `client`, those bind to `main.app`).

### References

- Story source: [Source: _bmad-output/planning-artifacts/epics.md#Story 1.2]
- Auth invariant: [Source: ARCHITECTURE-SPINE.md#AD-3] — one shared dependency, role checked in
  that same layer, never re-derived per route
- Permissions model: [Source: ARCHITECTURE-SPINE.md#AD-9] — Role-level-only, no per-resource
  filtering
- FR/NFR text: [Source: prd.md#FR-2, #NFR-2] — "the UI only surfaces actions the current User's
  Role is permitted to take"; "no mutating action executes without an authenticated session
  carrying a Role permitted for that action... no trusted internal bypass"
- Prior-story handoff: [Source: _bmad-output/implementation-artifacts/1-1-user-login.md#Review
  Findings] — "Standing rule for Story 1.2: derive authorization from the loaded User, never from a
  token claim" (the `role` JWT claim was deliberately dropped; `require_role` reads `user.role` off
  the DB-loaded `User`, never a token payload)
- Prior-story precedent: [Source: _bmad-output/implementation-artifacts/1-1-user-login.md#Dev
  Notes] — "Do not add a placeholder protected route just to exercise this — test the dependency
  directly," the same rule this story follows for `require_role`
- Conventions: [Source: _bmad-output/project-context.md] — trap 4 ("Auth exists, but it is opt-in
  per route... Story 1.2 builds role enforcement on top of this"), comment/docstring rules, domain
  rule "Permissions are Role-level only... 'Current user's items first' is a sort, never a filter"
- Sequencing: [Source: _bmad-output/implementation-artifacts/sprint-status.yaml] — Story 1.1 gates
  this story; this story gates every future domain router's authorization (1.3 onward)

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (Claude Code, bmad-dev-story workflow)

### Debug Log References

Followed the story's tasks in written order (1: exception, 2: dependency factory, 3: tests),
red-green cycle per task: wrote failing tests importing the not-yet-existing symbol
(`ForbiddenError`, then `require_role`), confirmed the collection error, implemented, reran to
green. `uv run pytest tests/test_authorization.py -v` after Task 1 (2 passed), after Task 2 (6
passed). Full regression suite (`uv run pytest -v` from `backend/`, against Postgres started via
`docker compose up -d postgres`) run once at the end: 35 passed (29 pre-existing from Story 1.1, 6
new), no regressions.

One test needed a fix mid-flight: the app-level handler test (`test_forbidden_error_handler_returns_403`)
is `async def` and the project's `pytest.ini_options` pins `asyncio_mode = "strict"`, so it needed
an explicit `@pytest.mark.asyncio` marker (matching every async test in `test_auth.py`) rather than
running bare.

### Completion Notes List

**What was built.** A `ForbiddenError` exception (`backend/exceptions/__init__.py`), sibling to
the existing `AuthError` family rather than a subclass of it, since it maps to 403 (an
authorization failure on an already-verified identity) and `AuthError` is reserved for 401s. A
matching `_forbidden_error_handler` registered in `main.py` alongside the existing `AuthError`
handler. A `require_role(*roles: UserRole)` dependency factory in `backend/api/dependencies.py`,
layered directly on `CurrentUserDep` (Story 1.1's shared seam): its returned dependency resolves
the current User via `CurrentUserDep` first (so an unauthenticated caller 401s before the role
check ever runs, satisfying AC2 with no new code) and then raises `ForbiddenError` if
`user.role not in roles` (AC1), otherwise returns the User unchanged.

**Design decisions worth knowing:**

1. **`ForbiddenError` is not an `AuthError` subclass.** `AuthError`'s own docstring scopes it to
   "every authentication failure," and its one registered handler always returns 401. A role
   mismatch is a different failure mode entirely (the identity is already verified), so it gets
   its own exception type and its own handler, registered separately in `main.py` rather than
   folded into the existing one. This keeps the two failure modes independently testable and
   prevents a future edit to the `AuthError` handler from accidentally changing the 403 behavior
   too.
2. **No placeholder protected route was added.** Exactly as Story 1.1 declined to add a
   placeholder route to prove `CurrentUserDep`, this story proves `require_role` by calling its
   returned coroutine directly with hand-built `User` instances, no DB, no HTTP round trip needed.
   The one exception is the handler-wiring test, which needs a real ASGI app to prove FastAPI's
   exception-handler registration actually returns a 403 JSON body; that test builds its own
   throwaway `FastAPI()` instance rather than adding a route to `main.app`.
3. **`require_role()` called with zero roles rejects everything.** This was made an explicit test
   case rather than left as an accidental consequence of `not in ()` always being `True`, so a
   future caller who forgets to pass roles gets a documented, tested failure mode instead of a
   silent all-permitting or all-denying guard discovered by surprise.
4. **No container or wiring changes.** `require_role` has no constructor and no dependencies of
   its own beyond `CurrentUserDep`, so it needed no `container.py` provider and no addition to
   `container.wire(modules=[...])`. `api.dependencies` was already in that list from Story 1.1's
   patch pass.

**Deferred, as scoped.** AC3 (frontend surfaces only permitted actions) ships no code in this
story, per the story's Scope note: no frontend routing or auth context exists yet (Story 1.4), and
v1 has no shared multi-role screen needing conditional action visibility within a single page.

### File List

**Added**

- `backend/tests/test_authorization.py`

**Modified**

- `backend/exceptions/__init__.py` (added `ForbiddenError`)
- `backend/api/dependencies.py` (added `require_role(*roles)`, new imports for `UserRole` and
  `ForbiddenError`)
- `backend/main.py` (added `_forbidden_error_handler`, registered it via
  `app.add_exception_handler(ForbiddenError, _forbidden_error_handler)`)

**Confirmed unchanged**: `backend/services/auth_service.py`, `backend/container.py`,
`backend/data_models/**`, `backend/api/router.py`, all frontend files, `pyproject.toml`/`uv.lock`
(no new dependency was needed).

### Files changed by the code-review patch pass (2026-08-08)

**Modified**

- `backend/tests/test_authorization.py` (rewritten: 6 tests to 22, now exercising the guard through
  real routes and FastAPI's dependency graph rather than as a bare coroutine)
- `backend/api/dependencies.py` (`TypeError` guard on non-`UserRole` arguments, docstring warning
  about the uncalled-factory trap)
- `_bmad-output/planning-artifacts/architecture/architecture-Restaurant-Kitchen-Management-System-2026-07-30/ARCHITECTURE-SPINE.md`
  (Decision 2: clarified the dependency-direction rule for `api/` to `data_models/` type imports)
- `_bmad-output/implementation-artifacts/deferred-work.md` (two deferred findings, plus the
  Decision 1 rule handing denial logging to the service layer from Story 1.3 onward)

**Confirmed unchanged by the patch pass**: `backend/main.py` and `backend/exceptions/__init__.py`
(both were mutation-tested during review and restored byte-identical; no patch needed either file).

## Change Log

| Date | Change |
|---|---|
| 2026-08-08 | Added `ForbiddenError` (`backend/exceptions/__init__.py`), a sibling to the `AuthError` family for 403 role-authorization failures, and its own handler in `main.py`. |
| 2026-08-08 | Added `require_role(*roles: UserRole)` (`backend/api/dependencies.py`), a dependency factory layered on `CurrentUserDep` that rejects any User whose Role is not in the permitted set. No domain router yet calls it; Story 1.3 is the first to. |
| 2026-08-08 | Added `tests/test_authorization.py`, 6 tests exercising the guard as a plain coroutine: forbidden-role rejection, multi-role permission, and the zero-roles edge case. ~~Covering all 4 ACs.~~ **Corrected 2026-08-08 during code review, this claim was wrong.** The original wording credited coverage of "unauthenticated-by-construction" and "the shared-dependency composition"; neither had an executing test, because every test called the returned closure directly and so never entered FastAPI's dependency graph. AC2 and AC4 were argued in prose, not tested. See the review Change Log entries below for what actually closed them. |
| 2026-08-08 | Applied bmad-code-review findings (3-layer parallel Opus review: 2 decisions resolved, 8 patches, 2 deferred, 4 dismissed). All three layers independently confirmed the guard behaves correctly end to end against the real app; every finding concerned what the tests failed to prove rather than a live defect. |
| 2026-08-08 | Rebuilt `tests/test_authorization.py` around routes actually gated by `Depends(require_role(...))` on a throwaway `FastAPI()` app, with `dependency_overrides[get_current_user]` standing in for the session. This is what finally tests AC1's "the action does not execute" (asserted via a flag the route body sets), AC2's 401-before-403 ordering, and AC4's composition on the shared seam. Verified by mutation: destroying the `CurrentUserDep` annotation now fails 6 tests where it previously left all of them green. Test count 6 to 22, suite 35 to 51. |
| 2026-08-08 | Added a test asserting the real `main.app` registers the `ForbiddenError` handler. Deleting that registration turned every role denial into a 500 while the suite stayed green, because every other test builds its own throwaway app; it now fails. |
| 2026-08-08 | `require_role` now raises `TypeError` at import time for any argument that is not a `UserRole` member. `UserRole` is a plain `Enum`, so `UserRole.admin == "admin"` is `False`, and `require_role("admin")`, the natural typo since the enum's values are exactly those strings, previously built a guard that silently denied real admins with no error anywhere and no linter or CI to catch it. |
| 2026-08-08 | Documented the call-me-do-not-pass-me trap in `require_role`'s docstring: `Depends(require_role)` without the call registers fine and silently becomes a required query parameter, so the route answers 422 and no authorization runs. |
| 2026-08-08 | Extended role coverage to all four `UserRole` members (`warehouse_manager` was untested) and made the `ForbiddenError.detail` test actually raise and catch, as its subtask specified, rather than reading the class attribute. |
| 2026-08-08 | Amended the architecture spine's dependency-direction rule (Decision 2) to state that `api/` may import Pydantic schemas and type-level names such as `UserRole` from `data_models`, while all querying and domain rules stay in `services/`. Stories 1.1 and 1.2 each burned a review cycle relitigating this ambiguity; the rule is now written down. |
