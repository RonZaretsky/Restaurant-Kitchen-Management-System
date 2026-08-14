---
baseline_commit: d7da24ef82dc2f4799e540e8814f746d9c9b71b2
epic: 1
story: 7
---

# Story 1.7: User Logout

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a staff member,
I want to end my session,
so that I can sign out from a shared terminal when I'm done, or when handing it to the next person.

## Scope note (read first)

**Added by `correct-course` on 2026-08-14, not part of the original PRD/epics pass.** Logout was
never captured anywhere: not in the PRD's FR set (FR-1 through FR-25 was "deliberately the entire
v1"), not in Epic 1's original scope, not in any UX mockup. Discovered during manual testing after
Story 3.1, when there turned out to be no way to sign out of the running app at all — confirmed via
grep across `backend/` and `frontend/src/` for `logout`/`Logout`, zero matches. FR-26 and this story
were added retroactively; see `_bmad-output/planning-artifacts/sprint-change-proposal-2026-08-14.md`
for the full impact analysis.

**Backend and frontend, both small.** One new route on the existing, already-wired `api/auth.py`
router (no `container.wire()` change needed, `"api.auth"` is already in `main.py`'s module list from
Story 1.1). One new control in the existing `AppShell` nav, next to `ThemeToggle`.

**Scope limitation, stated up front, not to be "fixed" by this story.** v1's JWT is stateless with no
server-side revocation store (AD-3: httpOnly cookie, no refresh-token flow). Logout clears the
*client's* cookie only. A token copied out of the browser before logout remains cryptographically
valid until its natural 8-hour expiry if replayed from that copy. This is an accepted v1 limitation
given the closed-staff, physical-terminal threat model (PRD FR-26's own `[ASSUMPTION]` tag) — do not
attempt to add a token blacklist/revocation table, that is a real architectural change out of this
story's scope.

## Acceptance Criteria

**AC1 — Logging out clears the session cookie**
Given an authenticated User, when they trigger logout, then the httpOnly session cookie is cleared
so the browser can no longer present it (FR-26).

**AC2 — Session is genuinely gone afterward**
Given a User has just logged out, when any subsequent non-login, non-health request is made from
that browser, then it is rejected as unauthorized, the same behavior Story 1.2/AD-3 already define
for "no valid session cookie" (FR-26, NFR-2).

**AC3 — Sign Out is visible for every Role**
Given the application shell (`AppShell`, Story 1.4), when it renders for any authenticated Role,
then a "Sign Out" control is visible in the shared nav area, available uniformly to all four Roles
(FR-26, FR-2's Role-level model).

**AC4 — Clicking Sign Out returns the User to Login**
Given a User clicks Sign Out, when the logout request completes, then the frontend's cached current-user
state is invalidated and the User lands on `/login` (no residual access to any protected route).

**AC5 — Logout works even against an already-invalid session**
Given a User whose cookie is missing, expired, or otherwise already invalid, when they trigger
logout (e.g. a stale tab, or a double-click), then the request still succeeds rather than 401ing —
logout is idempotent, not gated behind a valid session.

## Tasks / Subtasks

- [x] **Task 1: Backend `POST /api/auth/logout`** (AC: 1, 2, 5)
  - [x] Add to `backend/api/auth.py`, right after the existing `login`/`get_own_profile` routes.
    **Deliberately does not depend on `CurrentUserDep`** (unlike `get_own_profile`) — logout must
    succeed even when the presented cookie is missing, expired, or otherwise invalid, so a User
    whose session already lapsed can still click Sign Out and land cleanly on Login rather than
    getting a confusing 401 from the very control meant to end their session (AC5).
    ```python
    @router.post("/logout", status_code=204)
    async def logout(response: Response) -> None:
        """End the caller's session by clearing the session cookie (FR-26).

        Always succeeds, regardless of whether the presented cookie (if any)
        is still valid — logout is idempotent by design (AC5). v1 has no
        server-side token revocation store (AD-3), so this clears the
        client's cookie only; a token copied out beforehand stays valid
        until its natural expiry if replayed elsewhere.

        Args:
            response: Used to clear the session cookie.

        Returns:
            Nothing (204 No Content).
        """
        response.delete_cookie(
            key=COOKIE_NAME,
            httponly=True,
            samesite="lax",
            secure=True,
        )
    ```
    `delete_cookie`'s `httponly`/`samesite`/`secure` must match `login`'s `set_cookie` call exactly
    (same file, a few lines up) — a browser only overwrites/clears a cookie when the clearing
    `Set-Cookie` matches the original's attributes closely enough; mismatched `SameSite` or
    `Secure` can silently leave the original cookie in place. No `path` override needed (both
    default to `/`).
  - [x] No new error responses to declare (`error_responses(...)` is unnecessary here, this route
    cannot fail) and no `@inject`/container wiring needed, it touches no service.

- [x] **Task 2: Frontend `useLogout()`** (AC: 1, 4)
  - [x] Add to `frontend/src/services/authService.ts`, next to `useLogin()`:
    ```typescript
    /**
     * Logs the current User out.
     *
     * Invalidates the current-user query on success, the mirror image of
     * useLogin's invalidation. RequireAuth already redirects to /login the
     * moment useCurrentUser() re-reads as a rejected (401) session, so no
     * separate navigate() call is needed here (AC4) — this reuses the exact
     * redirect path an expired session already takes, rather than a second,
     * parallel one.
     *
     * @returns The TanStack Query mutation for logging out.
     */
    export function useLogout(): UseMutationResult<void, Error, void> {
      const queryClient = useQueryClient();

      return useMutation({
        mutationFn: () => apiRequest<void>("/api/auth/logout", { method: "POST" }),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: CURRENT_USER_QUERY_KEY }),
      });
    }
    ```
  - [x] Do not add a manual `useNavigate()`/redirect in the component that calls this. `RequireAuth`
    (`components/shell/RequireAuth.tsx`) already redirects to `/login` whenever `useCurrentUser()`
    resolves to a 401 (`isSessionRejected`); invalidating the query is what triggers that refetch.
    Adding a second redirect path risks the two racing or diverging later.

- [x] **Task 3: "Sign Out" control in `AppShell`** (AC: 3, 4)
  - [x] Edit `frontend/src/components/shell/AppShell.tsx`. Add a control in the `Toolbar`, after the
    user-identity `Typography` and before (or after) `ThemeToggle` — exact position is a small call,
    match `key-users.html`/the other mockups' general nav conventions if they show one, otherwise
    place it last. Use a plain MUI `IconButton` (`LogoutIcon` from `@mui/icons-material`, matching
    `ThemeToggle`'s icon-button shape) with a visible `aria-label="Sign out"` (matches project-context.md's
    rule that a disabled/icon-only control still needs a visible-to-assistive-tech label; `ThemeToggle`
    is the precedent to copy, not invent a new shape).
    ```tsx
    import LogoutIcon from "@mui/icons-material/Logout";
    import IconButton from "@mui/material/IconButton";
    import { useLogout } from "../../services/authService";
    // ...
    const logoutMutation = useLogout();
    // ...
    <IconButton
      color="inherit"
      onClick={() => logoutMutation.mutate()}
      disabled={logoutMutation.isPending}
      aria-label="Sign out"
    >
      <LogoutIcon />
    </IconButton>
    ```
  - [x] No error UI needed for a failed logout request (AC5 makes the backend route effectively
    unfailable; a network-layer failure just leaves the User signed in, which is an acceptable
    failure mode — they can simply click again). Do not add an `Alert` for this.

- [x] **Task 4: Tests** (AC: all)
  - [x] `backend/tests/test_auth.py` — mirror the existing login test style (`# Arrange`/`# Act`/`# Assert`,
    no docstrings). Add:
    - Logging out after a real login returns 204 and the `Set-Cookie` header clears `access_token`
      (assert `Max-Age=0` or an expiry in the past — check `response.cookies.get("access_token")` is
      falsy/empty after the client processes it, or inspect the raw `set-cookie` header directly,
      matching `test_login_cookie_carries_every_required_attribute`'s approach of reading the header).
    - After logout, a subsequent `GET /api/auth/me` with the same client (same cookie jar) is
      rejected 401 (AC2) — this is the test that actually proves the session is gone, not just that
      *a* response came back.
    - Logging out with **no session cookie at all** still returns 204, not 401 (AC5).
    - Logging out with an **expired** session cookie (same pattern as
      `test_me_rejects_an_expired_session_cookie`: hand-craft an expired JWT via `jwt.encode` and
      `client.cookies.set(COOKIE_NAME, expired_token)`) still returns 204, not 401 (AC5) — this is
      the sharpest test in the set, since it is the one case a naive `CurrentUserDep`-gated
      implementation would get wrong.
  - [x] `frontend/src/appIntegration.test.tsx` — this file is explicitly "the one test file that does
    NOT mock authService," the correct place for the logout counterpart to its existing login test.
    Add one test: sign in (reuse the existing login flow), then click the Sign Out control, and
    assert the User lands back on the Login screen (`screen.findByRole("heading", { name: "Sign in" })`
    or equivalent) with no further protected content visible. Stub `POST /api/auth/logout` in the
    same `vi.stubGlobal("fetch", ...)` block already used for login/`/me`, returning a 204, and make
    the stubbed `/api/auth/me` swap back to a 401 once logout has been "called" (mirror the existing
    `signedIn` boolean flag the login test already uses, just flip it the other way).
  - [x] Full regression: `uv run pytest` from `backend/`, `pnpm test` from `frontend/`.

### Review Findings

- [x] [Review][Patch] New test hardcodes the literal `"access_token="` instead of the already-imported
  `COOKIE_NAME` constant, so a future rename would silently stop being verified
  [backend/tests/test_auth.py]
- [x] [Review][Patch] `test_logout_clears_the_session_cookie` only checks `Max-Age=0`, not the full
  `HttpOnly`/`Secure`/`SameSite` attribute set `test_login_cookie_carries_every_required_attribute`
  already checks for login's cookie [backend/tests/test_auth.py]
- [x] [Review][Patch] `useLogout()` has no `onError` handling and the Sign Out button shows no error
  state on failure, violating project-context.md's "every mutation renders its own isError" rule
  [frontend/src/services/authService.ts, frontend/src/components/shell/AppShell.tsx]
- [x] [Review][Patch] Stray double blank line between the new `logout` route and `get_own_profile`
  [backend/api/auth.py]
- [x] [Review][Defer] The logout route logs nothing (no INFO entry, no identifying context) —
  deferred, every other route in `api/auth.py` delegates logging to its service, `logout` has none
  and never decodes the cookie, so there is no user identity available to log without adding a
  service/logger dependency solely for this; revisit if an audit-trail requirement emerges.
- [x] [Review][Defer] Logout is unauthenticated by design (AC5), so a cross-site top-level form
  navigation could theoretically force a signed-in User's session to clear — deferred, `SameSite=lax`
  already blocks the practical cross-site `fetch`/XHR case, and the worst realistic consequence is a
  forced sign-out nuisance, not data exposure or privilege escalation; not worth an Origin check for
  this severity.
- [x] [Review][Defer] No cross-tab session sync — logging out in one tab doesn't signal other open
  tabs, which keep rendering the authenticated shell until their own next request 401s — deferred, no
  AC requires it and NFR-5's "concurrent terminals" is about separate devices, not same-browser tabs.

## Dev Notes

### Architecture compliance

- **AD-3** (JWT in an httpOnly cookie, no refresh-token flow, no server-side session store): this
  story operates entirely within AD-3, it does not change it. Logout is a plain consumer of the
  existing cookie mechanism — clear the cookie, nothing more. Do not introduce a token
  blacklist/revocation table; that would be a new architectural decision this story is not scoped for.
- **NFR-2** (authorization is universal, no mutating action without a permitted session): logout is
  the one deliberate exception in spirit — it doesn't mutate any domain resource, and per AC5 it must
  succeed even without a currently-valid session. Do not gate it behind `CurrentUserDep`.
- No new Alembic migration, no new `data_models/` change, no new container provider. This story
  touches nothing behind DI beyond a plain `Response` object, the same shape `login` already uses.

### Backend contract (existing routes this story sits next to, unchanged)

| Method | Path | Body | Success | Errors |
|---|---|---|---|---|
| POST | `/api/auth/login` | `LoginRequest` | 200 `LoginResponse`, sets cookie | 401 |
| GET | `/api/auth/me` | — | 200 `UserResponse` | 401 |
| POST | `/api/auth/logout` (**new**) | — | 204, clears cookie | — (never fails) |

`COOKIE_NAME = "access_token"` (`services/auth_service.py`). Login's `set_cookie` call
(`api/auth.py`, `httponly=True, samesite="lax", secure=True, max_age=token_expiry_hours*3600`) is the
exact attribute set `delete_cookie` must match on the clearing side (Task 1).

### Project Structure Notes

Files touched:
- `backend/api/auth.py` — **UPDATE**, add the `logout` route. No new imports beyond `Response`
  (already imported) — `COOKIE_NAME` is already imported from `services.auth_service`.
- `frontend/src/services/authService.ts` — **UPDATE**, add `useLogout()` next to `useLogin()`.
  `CURRENT_USER_QUERY_KEY` already exists and is exported.
- `frontend/src/components/shell/AppShell.tsx` — **UPDATE**, add the Sign Out `IconButton` to the
  `Toolbar`.
- `backend/tests/test_auth.py` — **UPDATE**, add the four logout tests.
- `frontend/src/appIntegration.test.tsx` — **UPDATE**, add the one logout integration test.

No backend route file is new (extends `api/auth.py`), no `container.py`/`main.py` change (`"api.auth"`
already wired), no new frontend file, no router change (`AppShell` is not itself a route).

### References

- [Source: `_bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md#FR-26`] —
  this story's AC source, added by `correct-course`
- [Source: `_bmad-output/planning-artifacts/epics.md#Story 1.7`] — the epics-level version of these ACs
- [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-08-14.md`] — the full impact
  analysis behind adding this story
- [Source: `backend/api/auth.py`, `backend/services/auth_service.py`] — the existing login/`/me`
  routes and `COOKIE_NAME`/cookie-attribute precedent this story must match
- [Source: `backend/tests/test_auth.py`] — the existing test style and the expired-cookie-crafting
  pattern (`test_me_rejects_an_expired_session_cookie`) to reuse for AC5's sharpest case
- [Source: `frontend/src/services/authService.ts`] — `useLogin()`/`CURRENT_USER_QUERY_KEY`, the
  pattern `useLogout()` mirrors
- [Source: `frontend/src/components/shell/AppShell.tsx`, `ThemeToggle.tsx`] — the nav bar this story
  adds a control to, and the icon-button-with-visible-`aria-label` shape to copy
- [Source: `frontend/src/components/shell/RequireAuth.tsx`] — the existing 401-redirect logic Task 2
  relies on rather than duplicating
- [Source: `frontend/src/appIntegration.test.tsx`] — the real-`authService` integration test file,
  and the `signedIn` boolean/`delayed()` stubbing pattern the new logout test should mirror

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (claude-sonnet-5)

### Debug Log References

None. No HALT conditions were hit; implementation proceeded task-by-task without needing debug-log
capture.

### Completion Notes List

- `POST /api/auth/logout` added to the existing `api/auth.py` router, deliberately not gated behind
  `CurrentUserDep`: it must succeed even when the presented cookie is missing, expired, or otherwise
  invalid (AC5), so a User on a lapsed tab can still click Sign Out and land cleanly on Login. Clears
  the cookie via `response.delete_cookie` with the exact `httponly`/`samesite`/`secure` attributes
  `login`'s `set_cookie` call uses, since a mismatch would leave the original cookie in place.
- `useLogout()` added to `authService.ts`, mirroring `useLogin()`'s shape (invalidates
  `CURRENT_USER_QUERY_KEY` on success). Deliberately does not call `useNavigate()` itself:
  `RequireAuth` already redirects to `/login` whenever `useCurrentUser()` resolves to a 401, so
  invalidating the query after logout reuses that exact same path rather than adding a second,
  potentially-racing redirect.
- `AppShell.tsx` gained a Sign Out `IconButton` (MUI `LogoutIcon`, `aria-label="Sign out"`) next to
  the existing `ThemeToggle`, following its established icon-button shape rather than inventing a new
  control pattern. Disabled while the mutation is pending.
- Backend tests (4 new, `test_auth.py`): cookie actually clears (`Max-Age=0` in the `Set-Cookie`
  header), a subsequent `/me` genuinely 401s afterward (not just "a response came back"), logout with
  no cookie at all still 204s, and logout with an already-expired cookie still 204s, the sharpest
  case, the one a naive `CurrentUserDep`-gated implementation would get wrong.
- Frontend test (1 new, `appIntegration.test.tsx`, the file that deliberately does not mock
  `authService`): signs in through the real router, clicks Sign Out, and asserts the User lands back
  on the Login screen. Extended the file's shared `signedIn` fetch-stub flag to also handle
  `POST /api/auth/logout`, flipping it back to false, the mirror image of what login already does.
- Full regression: `uv run pytest` — 229 passed (up from 225, +4 in `test_auth.py`). `pnpm test` —
  118 passed (up from 117, +1 in `appIntegration.test.tsx`). `npx tsc -b` clean.
- **Code review (Blind Hunter, Edge Case Hunter, Acceptance Auditor):** 4 patches applied, 3 deferred,
  7 dismissed as false positives (verified against actual code, e.g. `login`'s own `set_cookie` also
  omits `path` and hardcodes `secure=True`, so the "attribute mismatch" claims didn't hold; `logout`
  never reads the cookie's contents at all, so a malformed-cookie test would exercise nothing;
  `ThemeToggle` also has no `Tooltip`, so the "inconsistency" claim was false). Patches: strengthened
  `test_logout_clears_the_session_cookie` to assert the full `HttpOnly`/`Secure`/`SameSite` attribute
  set (matching `test_login_cookie_carries_every_required_attribute`'s own precedent) and to use the
  `COOKIE_NAME` constant instead of a hardcoded literal; added `logoutMutation.isError` handling to
  `AppShell.tsx` (an `Alert` rendering the backend's own message, per UX-DR17) plus a new integration
  test covering the failure path, closing a real violation of project-context.md's "every mutation
  renders its own isError" rule; removed a stray extra blank line in `auth.py`. Full regression after
  patches: 229 backend (unchanged, assertions strengthened not counts), 119 frontend (+1), `tsc -b`
  clean.

### File List

**Modified**

- `backend/api/auth.py` (added the `logout` route)
- `backend/tests/test_auth.py` (added 4 logout tests)
- `frontend/src/services/authService.ts` (added `useLogout()`)
- `frontend/src/components/shell/AppShell.tsx` (added the Sign Out `IconButton`)
- `frontend/src/appIntegration.test.tsx` (added the logout integration test; extended the shared
  fetch stub to handle `POST /api/auth/logout`)

**Confirmed unchanged**: `backend/services/auth_service.py`, `backend/container.py`, `backend/main.py`
(`"api.auth"` was already wired from Story 1.1), `frontend/src/router.tsx` (no route change,
`AppShell` is not itself a route), no Alembic migration, no new package in either manifest.

## Change Log

| Date | Change |
|---|---|
| 2026-08-14 | Added `POST /api/auth/logout` to `backend/api/auth.py`, clearing the session cookie via `response.delete_cookie` with attributes matching `login`'s `set_cookie` exactly. Deliberately not gated behind `CurrentUserDep`, so logout succeeds even against a missing or expired cookie (AC5). |
| 2026-08-14 | Added `useLogout()` to `frontend/src/services/authService.ts`, mirroring `useLogin()`'s invalidation shape. No manual redirect: `RequireAuth`'s existing 401-driven redirect to `/login` handles navigation once the current-user query is invalidated and refetches as unauthorized. |
| 2026-08-14 | Added a Sign Out `IconButton` to `frontend/src/components/shell/AppShell.tsx`, next to `ThemeToggle`, following its icon-button-with-visible-`aria-label` shape. |
| 2026-08-14 | Added 4 backend tests (`test_auth.py`) and 1 frontend integration test (`appIntegration.test.tsx`, the file that drives the real `authService` rather than mocking it). Full regression: 229 backend (+4), 118 frontend (+1), `tsc -b` clean. |
| 2026-08-14 | Code review (Blind Hunter, Edge Case Hunter, Acceptance Auditor). 4 patches applied: strengthened the logout cookie test to assert the full attribute set and use `COOKIE_NAME` instead of a literal; added `isError` handling to `AppShell`'s Sign Out control (an inline `Alert`) plus a covering test, closing a real "every mutation renders its own isError" violation; removed a stray blank line. 3 items deferred (no router-level logging, unauthenticated-logout CSRF nuisance, no cross-tab sync), 7 dismissed as false positives after verifying against the actual code. Full regression: 229 backend, 119 frontend (+1), `tsc -b` clean. |
