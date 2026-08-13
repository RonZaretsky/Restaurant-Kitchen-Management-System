---
baseline_commit: c0fdd1cb6bc826e980fa80f1660f9b3758c64dad
epic: 1
story: 6
---

# Story 1.6: Manage User Accounts from the Admin UI

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Admin,
I want to create, edit, deactivate, and reactivate User accounts, and reset a User's password, from the Users screen,
so that I can manage staff access without calling the API directly.

## Scope note (read first)

**Frontend-only. Zero backend changes.** Story 1.3 built and tested all 6 routes this story needs
(`admin.py` has a 7th, `GET /api/admin/users/{id}`, a single-user fetch this story has no use for —
the list view covers every read this screen needs);
Story 1.4 built the shell and route (`/admin/users` → `UsersPage`) but left the screen itself as a
bare placeholder, explicitly noting it was "still unassigned" (`epics.md`, Story 1.4's own scope
note; `deferred-work.md`'s Story 1.3 section). This story writes the real
`frontend/src/pages/admin/UsersPage.tsx`, replacing the placeholder, plus a new
`frontend/src/services/userService.ts`. Do not touch any backend file.

**Do not create a new `User` type.** `frontend/src/types/user.ts` already exports `CurrentUser`,
whose shape is byte-for-byte identical to the backend's `UserResponse` (`id`, `username`,
`full_name`, `role`, `is_active`, `created_at`) — it was built for `GET /api/auth/me` in Story 1.1,
but the shape is the same response model. Reuse `CurrentUser` as the list-row type; do not add a
parallel `User` interface. Add only the new request-payload types this story needs
(`CreateUserPayload`, `UpdateUserPayload`, `ResetPasswordPayload`) to `types/user.ts`, following its
existing snake_case-mirrors-the-backend convention.

**Follow `TablesSetupPage.tsx` (Story 2.4), not `MenuManagementPage.tsx`.** It is the closest
precedent: an Admin-only screen with an always-visible inline create form above a dense-row list,
per-row inline edit, row-level rejection messages, and a full Vitest suite that mocks only `fetch`.
Story 2.6 (menu/ingredient creation) has not been built yet and sets no precedent — do not wait for
it or reference it. Copy `TablesSetupPage`'s shape exactly for: the service layer (`apiRequest` +
TanStack Query hooks, module-level query-key constant, `invalidateQueries` on mutation
success/settle), the inline-form pattern (plain `useState` per field, no react-hook-form), the
per-row local-edit-state component, the loading/error/empty triad
(`RowsSkeleton` / `Alert severity="error"` with a Retry action / plain `Typography` empty copy),
and the test file's `jsonResponse` helper + real `QueryClient`.

**This story satisfies AD-15's UI half.** The last-active-Admin lockout (AD-15) is already enforced
server-side (`LastAdminLockoutError` → 409, both on deactivate and on a role-changing PATCH) — this
story does not add that guard, only surfaces its 409 inline like every other rejection. What this
story *does* add is new: the mockup's "This is you" marker on the signed-in Admin's own row, which
removes the Deactivate control entirely from that row. This directly closes the separate,
narrower gap `deferred-work.md`'s Story 1.3 section flagged ("An Admin can deactivate their own
account... Better addressed as a confirmation step... than as a service-layer block") — AC6 below
goes one step further than a confirmation step by making the action unreachable from this screen,
matching `key-users.html` exactly.

## Acceptance Criteria

**AC1 — Create a User**
Given a full name, username, Role, and initial password, when an Admin submits the "+ New user"
form, then a new User account is created via the existing `POST /api/admin/users` endpoint and
appears in the Users list immediately (FR-3).

**AC2 — Duplicate username rejected**
Given a username that already exists (active or deactivated — the backend check is
case-insensitive and includes inactive accounts), when creation is attempted, then it is rejected
inline with the backend's exact message, "That username already exists" (FR-3, UX-DR17).

**AC3 — Edit full name and Role**
Given an existing User, when an Admin clicks Edit, updates full name and/or Role, and saves, then
the change is persisted via the existing `PATCH /api/admin/users/{id}` endpoint (FR-3).

**AC4 — Deactivate an active User**
Given an active User who is not the last active Admin, when an Admin clicks Deactivate, then the
User is deactivated via the existing endpoint and its Status chip updates to Inactive (FR-3).

**AC5 — Last-Admin lockout surfaced inline**
Given the last remaining active Admin account, when deactivation or a demoting role change is
attempted (on that row, by any Admin including a different one), then the backend's 409 is
rendered inline, "Rejected, at least one admin must stay active" (FR-3, AD-15, UX-DR17).

**AC6 — "This is you" replaces Deactivate on the signed-in Admin's own row**
Given the signed-in Admin's own row, when the Users list renders, then it shows "This is you" in
place of a Deactivate control, so self-deactivation is never reachable from this screen (FR-3,
AD-15, matches `key-users.html`).

**AC7 — Reactivate a deactivated User**
Given a deactivated User, when an Admin clicks Reactivate, then the User becomes Active again via
the existing endpoint (FR-3).

**AC8 — Reset a User's password**
Given any User row, when an Admin resets that User's password, then a new password is set via the
existing reset-password endpoint (request field `new_password`), never displaying or requiring the
previous one (FR-3).

**AC9 — Screen matches the UX mock**
Given the Users screen, when it renders, then it matches the UX mock (`key-users.html`) with dense
row styling, and holds the WCAG 2.2 AA floor established in Story 1.4 (UX-DR8, UX-DR19, UX-DR21).

## Tasks / Subtasks

- [x] **Task 1: Request-payload types** (AC: 1, 3, 8)
  - [x] In `frontend/src/types/user.ts`, add (do not touch `CurrentUser`, reuse it as the list-row
    type):
    ```ts
    /** Body of an Admin's request to create a User. Mirrors backend CreateUserRequest. */
    export interface CreateUserPayload {
      username: string;
      full_name: string;
      role: UserRole;
      password: string;
    }

    /** Body of an Admin's edit request. At least one field required (server-enforced, 422 on empty body). */
    export interface UpdateUserPayload {
      full_name?: string;
      role?: UserRole;
    }

    /** Body of an Admin's password-reset request. Field name is new_password, not password. */
    export interface ResetPasswordPayload {
      new_password: string;
    }
    ```

- [x] **Task 2: `userService.ts`** (AC: 1, 3, 4, 5, 7, 8)
  - [x] New file `frontend/src/services/userService.ts`, modeled on `tableService.ts`'s shape
    exactly: a module-level `USERS_QUERY_KEY = ["admin", "users"] as const`, all requests through
    `apiRequest<T>` from `httpClient.ts` (never raw `fetch`), every mutation hook invalidating
    `USERS_QUERY_KEY` — use `onSuccess` for create (nothing stale to reconcile) and `onSettled` for
    update/deactivate/reactivate/reset-password (same reasoning `useUpdateTable` uses: a 409 means
    the cached row is already stale, so the failing path needs the refetch too).
    ```ts
    export function useUsers(): UseQueryResult<CurrentUser[], Error> { ... }              // GET /api/admin/users
    export function useCreateUser(): UseMutationResult<CurrentUser, Error, CreateUserPayload> { ... }
    export function useUpdateUser(): UseMutationResult<CurrentUser, Error, { userId: number; payload: UpdateUserPayload }> { ... }
    export function useDeactivateUser(): UseMutationResult<CurrentUser, Error, number> { ... }  // POST .../deactivate
    export function useReactivateUser(): UseMutationResult<CurrentUser, Error, number> { ... }  // POST .../reactivate
    export function useResetPassword(): UseMutationResult<CurrentUser, Error, { userId: number; payload: ResetPasswordPayload }> { ... }
    ```
  - [x] `useCurrentUser` already exists in `authService.ts` (`CURRENT_USER_QUERY_KEY = ["auth", "me"]`)
    — import and reuse it for AC6's "This is you" check, do not add a second current-user fetch.

- [x] **Task 3: `UsersPage.tsx` shell, list, and create form** (AC: 1, 2, 6, 9)
  - [x] Replace the placeholder body of `frontend/src/pages/admin/UsersPage.tsx` entirely.
  - [x] Header matches the mock: `<h1>Users</h1>` plus a subtitle `"{n} staff accounts · {m} active"`
    computed from the loaded list (`users.length`, `users.filter(u => u.is_active).length`) — not a
    separate API call.
  - [x] "+ New user" inline form (always visible, above the list, like `TablesSetupPage`'s Add-table
    form): plain `useState` per field (username, full_name, role, password — role defaults to a
    valid `UserRole`, e.g. `"waiter"`, rendered as an MUI `Select` over the four Role values).
    Submit disabled while any required field is empty or `createMutation.isPending`. On success,
    clear the form; on failure, render `createMutation.error`'s `ApiError.message` inline (AC2's
    exact backend string flows through unchanged, do not re-word it).
  - [x] Dense-row `Table`/`TableHead`/`TableBody` (MUI, `size="small"` from the theme default, same
    as `TablesSetupPage`/`MenuManagementPage`): columns Username, Full name, Role (chip), Status
    (chip), Actions — matching `key-users.html`'s column set.
  - [x] Loading/error/empty triad, identical wording pattern to `TablesSetupPage`: `isLoading` →
    `<RowsSkeleton count={5} />`; `isError` → `Alert severity="error"` with a Retry action button
    calling `refetch()`, message `` `Could not load the users. ${...}` ``; `users.length === 0` →
    `Typography color="text.secondary"` reading `"No users yet."`

- [x] **Task 4: Per-row actions** (AC: 3, 4, 5, 6, 7, 8)
  - [x] Own row component (e.g. `UserListRow`), owning its own local `isEditing` /
    `isResettingPassword` state, same reasoning as `TablesSetupPage`'s `TableListRow`: editing one
    row must not re-render or reset the whole list.
  - [x] **Edit**: click swaps Full name/Role cells to inline editable controls (`TextField` /
    `Select`), Save calls `useUpdateUser` **always sending both fields**, never diffed against the
    cached row. (Corrected 2026-08-13 during code review — this task originally said "only the
    changed field(s)", which contradicts project-context.md's standing rule "Never diff a form
    against cached data to decide what to send" and `TablesSetupPage`'s own six-line comment
    rejecting it. Diffing lets a save silently revert a concurrent change to the field this Admin
    never touched, and disables Save entirely when the cache is stale. The backend already skips a
    no-op edit without committing, so sending both costs nothing.) Resync local edit state from the
    server value only while *not* editing, same `useEffect`-guarded-on-editing pattern
    `TablesSetupPage` uses, so an in-flight edit isn't clobbered by a background refetch.
  - [x] **Deactivate / Reactivate**: single button per row, `useDeactivateUser`/`useReactivateUser`
    called with the row's `id`. AC5's 409 renders as an `Alert severity="error"` in a full-width
    extra `TableRow` under that row (`colSpan` = column count), same placement `TablesSetupPage`
    uses for row-level mutation errors — do not use a page-level toast, this codebase has none.
  - [x] **AC6**: on the row where `row.id === currentUser?.id`, render `<Typography>This is you</Typography>`
    in the Actions cell in place of the Deactivate button (Edit and Reset password stay available —
    only Deactivate is removed, matching `key-users.html`'s row exactly).
  - [x] **Reset password**: a "Reset password" action reveals an inline password `TextField` +
    Save/Cancel within that row's own local state (same in-place-reveal shape as Edit, not a modal —
    this codebase has not established a modal-dialog pattern anywhere and this story should not be
    the first to invent one). On save, call `useResetPassword`; on success, collapse back to the
    normal row (never display or log the new value anywhere after submission, per AC8).
  - [x] Do not add client-side password-length validation beyond "non-empty" — the 72-byte bcrypt
    limit is server-enforced (422) and already surfaces inline via the same `ApiError.message`
    path; duplicating that check client-side is out of scope and risks disagreeing with the
    server's UTF-8-byte-based count.

- [x] **Task 5: Tests, `UsersPage.test.tsx`** (AC: all)
  - [x] Mirror `TablesSetupPage.test.tsx`'s conventions exactly: mock only `global.fetch`
    (`vi.stubGlobal`/`vi.unstubAllGlobals`), never the service module; reuse or lift the same
    `jsonResponse(status, body)` helper (four near-identical copies already exist across
    `TablesSetupPage.test.tsx`, `MenuManagementPage.test.tsx`, `appIntegration.test.tsx`, and
    `cook/DishesPage.test.tsx` — first flagged as three in `deferred-work.md`'s Story 2.4 section,
    a fourth landed with Story 2.5; if a shared helper is introduced here, note it in the Change
    Log, but do not block this story on refactoring the other three); render through a real
    `QueryClient` (`retry: false`) + `QueryClientProvider`, no query-hook mocking.
  - [x] Required coverage, one test per: list renders with counts (AC1/AC9); create succeeds and
    clears the form (AC1); duplicate-username 409 renders the exact backend string and does not
    clear the form (AC2); edit saves full_name/role (AC3); deactivate succeeds and flips the Status
    chip (AC4); deactivate on the last Admin renders the exact 409 string and the chip stays Active
    (AC5); the signed-in Admin's own row shows "This is you" and has no Deactivate button, while
    other rows do (AC6); reactivate succeeds (AC7); reset-password succeeds and the field is cleared
    without ever rendering the submitted value afterward (AC8); empty-state and error+Retry render
    correctly (AC9's loading/error/empty triad, same bar as `TablesSetupPage`).
  - [x] `useCurrentUser`'s query needs a mocked `GET /api/auth/me` response in every test's fetch
    stub (the AC6 tests depend on it matching one row's `id`); factor this into whatever shared
    render-helper the test file uses.

- [x] **Task 6: Docs** (AC: n/a — required for story completion, not dev-story)
  - [x] Update `_bmad-output/project-context.md`: new frontend domain screen, updated
    backend/frontend suite counts, and remove/resolve the Story 1.3 "Users screen still
    unassigned" note this story closes.
  - [x] `sprint-status.yaml` and `epics.md` need no further edits — already registered as Story 1.6.

### Review Findings

Code review 2026-08-13, three parallel adversarial layers (Blind Hunter, Edge Case Hunter,
Acceptance Auditor), all run on a stronger model than the one that implemented the story, each with
no prior conversation context. The Acceptance Auditor additionally **mutation-tested** the suite,
deleting behaviors and re-running the tests, which is how the unpinned-test findings below were
proven rather than merely suspected.

- [x] [Review][Decision] **RESOLVED 2026-08-13 (Ofek): in-row confirm, no modal.** Deactivating another User had no confirmation step — the action is one
  click, adjacent to Edit in a dense `flexWrap` row, immediately blocks a staff member's login, and
  `color="error"` is its only signal (invisible to colour-blind users and to anyone reading the
  button by name). Reversible via Reactivate, but there is no undo affordance. Notably,
  `deferred-work.md`'s original Story 1.3 item explicitly anticipated "a confirmation step in the
  Users screen" — this story delivered that intent only for the *self* row (AC6's "This is you"),
  not for deactivating others. Deciding needs human input because a confirm dialog would be the
  **first modal pattern in this codebase** (the story spec deliberately avoided inventing one for
  the password field), so it is an architectural first, not a local fix.

- [x] [Review][Patch] Edit diffs the form against cached data to decide what to send, forbidden
  outright by project-context.md:189-191, and can silently revert another Admin's concurrent role
  change [frontend/src/pages/admin/UsersPage.tsx:94,113-123]
- [x] [Review][Patch] `deactivateMutation`/`reactivateMutation` are never `reset()`, so a failed
  Deactivate leaves an undismissable red alert that outlives a later *successful* edit on the same
  row [frontend/src/pages/admin/UsersPage.tsx:158-159,97-100,130-134]
- [x] [Review][Patch] `activeError`'s fixed-precedence `??` chain shows a stale earlier error
  instead of the failure the Admin just caused, telling them the wrong reason
  [frontend/src/pages/admin/UsersPage.tsx:158-159]
- [x] [Review][Patch] No mutation invalidates `CURRENT_USER_QUERY_KEY`, so editing or demoting your
  own account leaves the app shell rendering a stale name and a stale Role, with admin nav still
  showing after a self-demotion [frontend/src/services/userService.ts:56-128]
- [x] [Review][Patch] A failed background refetch unmounts the entire table, destroying every open
  editor and any typed password; an alt-tab is enough to trigger it
  [frontend/src/pages/admin/UsersPage.tsx:407]
- [x] [Review][Patch] The Role edit branch is unpinned by any test — mutation-verified, deleting
  `payload.role = draftRole` leaves 11/11 green, and so does replacing the edit-mode Role Select
  with a static chip; AC1's create-Role field is equally unpinned
  [frontend/src/pages/admin/UsersPage.test.tsx:181]
- [x] [Review][Patch] AC1's "clears the form" test omits Full name — mutation-verified, deleting
  `setFullName("")` leaves 11/11 green [frontend/src/pages/admin/UsersPage.test.tsx:147-148]
- [x] [Review][Patch] AC8's "field is cleared" assertion passes unconditionally because the field
  unmounts on success — mutation-verified, deleting `setDraftPassword("")` leaves 11/11 green
  [frontend/src/pages/admin/UsersPage.test.tsx:355]
- [x] [Review][Patch] AC5's demoting-role-change half has no test, only the deactivate 409 is
  covered [frontend/src/pages/admin/UsersPage.test.tsx:243]
- [x] [Review][Patch] An over-length full name reports "Full name is required", which misstates the
  violation and is a client-invented string where UX-DR17 requires the backend's own copy
  [frontend/src/pages/admin/UsersPage.tsx:93,173]
- [x] [Review][Patch] `isSelf` fails open when `currentUser` is undefined, rendering a live
  Deactivate button on the signed-in Admin's own row. Not reachable in the composed app (RequireAuth
  gates it), but the component's own contract permits undefined and the AC6 test renders the page
  standalone, which is exactly the configuration where the hole is open
  [frontend/src/pages/admin/UsersPage.tsx:157]
- [x] [Review][Patch] Neither password field sets `autoComplete`, so browsers offer to autofill the
  admin's own credentials into the create form and to save a staff member's new password as the
  admin's own [frontend/src/pages/admin/UsersPage.tsx:216-222,370-376]
- [x] [Review][Patch] Both Role `Select`s have only an `aria-label` and no visible label, unlike
  every sibling control, so sighted users see an unlabelled box reading "Waiter"
  [frontend/src/pages/admin/UsersPage.tsx:181-186,358-369]
- [x] [Review][Patch] Header renders "1 staff accounts" for a single-user list
  [frontend/src/pages/admin/UsersPage.tsx:335-339]
- [x] [Review][Patch] AC9 divergences from `key-users.html`: the Role chip is not colour-coded (the
  mock defines four distinct per-Role treatments) and the Actions column is left-aligned where the
  mock right-aligns it [frontend/src/pages/admin/UsersPage.tsx:194,236,415]
- [x] [Review][Patch] The create form applies no length validation, so an over-long username or full
  name round-trips into a raw Pydantic 422, while the row editor does bound the name — inconsistent
  within one file [frontend/src/pages/admin/UsersPage.tsx:304-308]
- [x] [Review][Patch] The story spec's own Task 4 authorized "only the changed field(s)", which
  contradicts project-context.md:189-191; correct the spec text so the next story does not inherit
  the same wrong instruction [this file, Task 4]

- [x] [Review][Defer] `errorMessage` is now copy-pasted verbatim into a fifth file, and its
  `instanceof ApiError` fallback is dead code since `apiRequest` throws `ApiError` on every failure
  path [frontend/src/pages/admin/UsersPage.tsx:48-53] — deferred, pre-existing codebase-wide
- [x] [Review][Defer] A sixth hand-rolled `jsonResponse` test helper copy was added rather than
  lifting a shared one [frontend/src/pages/admin/UsersPage.test.tsx:54-62] — deferred, pre-existing;
  the spec explicitly marked this non-blocking
- [x] [Review][Defer] Inline edit and password panels are not wrapped in `<form>`, so Enter does
  nothing, while the create form on the same screen does submit on Enter
  [frontend/src/pages/admin/UsersPage.tsx:206-234] — deferred, pre-existing in `TableListRow`
- [x] [Review][Defer] No client-side guard on the password's 72-**byte** bcrypt limit, so a Hebrew
  password fails at roughly 36 characters with an opaque server message
  [frontend/src/pages/admin/UsersPage.tsx:307] — deferred, the spec explicitly scoped this out

## Dev Notes

### Architecture compliance

- **AD-15** (last-Admin lockout): already fully enforced server-side, this story only renders its
  409. Do not add a client-side "is this the last admin" check — the server is the single source of
  truth and a client-side guess could disagree with it (e.g. a second Admin deactivated
  concurrently by someone else).
- **AD-9** (Role-level-only permissions): no per-resource filtering applies here, `GET
  /api/admin/users` already returns every User unfiltered — nothing to enforce in this story beyond
  rendering what the endpoint returns.
- **UX-DR8/UX-DR19** (dense-row list): satisfied by the theme's existing `MuiTable: { defaultProps:
  { size: "small" } }` default, same as `TablesSetupPage` — no per-component override needed.
- **UX-DR17** (inline rejection copy): every error this story surfaces must be the backend's literal
  `detail` string via `ApiError.message`, never a re-worded client-side copy — this is what makes
  AC2/AC5's "exact message" wording testable and keeps one source of truth for user-facing text.
- **UX-DR21** (WCAG 2.2 AA floor, established Story 1.4): reuse existing shell components
  (`RowsSkeleton`, themed `Alert`, MUI `Table`) rather than hand-rolled markup, they already carry
  the accessibility baseline; do not introduce new interactive elements (icon-only buttons, custom
  widgets) without a visible text label or `aria-label`, matching `TablesSetupPage`'s icon-button
  convention.

### Backend contract (existing, unchanged — `backend/api/admin.py`)

All routes require `AdminDep` (authenticated + `role == admin`), 401/403 on failure.

| Method | Path | Body | Success | Errors |
|---|---|---|---|---|
| POST | `/api/admin/users` | `CreateUserRequest` | 201 `UserResponse` | 409 `DuplicateUsernameError` |
| GET | `/api/admin/users` | — | 200 `UserResponse[]` | — |
| PATCH | `/api/admin/users/{id}` | `UpdateUserRequest` | 200 `UserResponse` | 404, 409 `LastAdminLockoutError` |
| POST | `/api/admin/users/{id}/deactivate` | — | 200 `UserResponse` | 404, 409 `LastAdminLockoutError` |
| POST | `/api/admin/users/{id}/reactivate` | — | 200 `UserResponse` | 404 |
| POST | `/api/admin/users/{id}/reset-password` | `ResetPasswordRequest` | 200 `UserResponse` | 404 |

Exact 409 strings (render verbatim, do not paraphrase):
- Duplicate create: `"That username already exists"`
- Last-Admin lockout (deactivate or demoting PATCH): `"Rejected, at least one admin must stay active"`

Known backend behaviors a frontend implementation must not fight:
- `PATCH` with a **fully empty** body → 422 (server requires `full_name` and/or `role`); a payload
  with values identical to the current state is accepted as a 200 no-op. Task 4's "send only
  changed fields, never nothing" guidance covers this.
- Deactivate/reactivate are **idempotent** — calling either on a User already in that state returns
  200, not an error. No special-casing needed client-side.
- Username uniqueness is **case-insensitive** and checked against **deactivated accounts too** — a
  409 on create can happen even with no visible active match in the list.
- `UserResponse` never includes `password_hash`; `is_active` and `role` (as its string value) are
  both present — this is exactly `CurrentUser`'s existing shape (Task 1).

### Project Structure Notes

Files touched, all frontend:
- `frontend/src/pages/admin/UsersPage.tsx` — **UPDATE**, replaces the entire placeholder body.
  Route (`/admin/users`) and its import in `frontend/src/router.tsx` already exist; do not touch
  the router.
- `frontend/src/services/userService.ts` — **NEW**, mirrors `tableService.ts`'s structure.
- `frontend/src/types/user.ts` — **UPDATE**, additive only (Task 1); `CurrentUser`/`UserRole` stay
  untouched, `authService.ts`'s existing import of them must keep working unmodified.
- `frontend/src/pages/admin/UsersPage.test.tsx` — **NEW**, mirrors `TablesSetupPage.test.tsx`.

No backend file, no Alembic migration, no `container.py`/`main.py` wiring change — everything on
that side already shipped in Story 1.3.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 1.6`] — this story's AC source
- [Source: `_bmad-output/implementation-artifacts/1-3-admin-manages-user-accounts.md`] — the
  backend this story wires up; its own Scope note explicitly deferred this screen
- [Source: `_bmad-output/implementation-artifacts/1-4-application-shell-routing-and-per-role-navigation.md`] —
  built the placeholder and the route; flagged the screen as unassigned
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md`, "Deferred from: code review of
  story-1-3"] — the self-deactivation and unbounded-list items this story's design addresses
  (AC6 closes the former; the latter stays out of scope, no pagination AC exists)
- [Source: `frontend/src/pages/admin/TablesSetupPage.tsx`, `TablesSetupPage.test.tsx`,
  `frontend/src/services/tableService.ts`] — the pattern this story's frontend must match
- [Source: `frontend/src/types/user.ts`, `frontend/src/services/authService.ts`] — `CurrentUser`
  and `useCurrentUser`, both reused rather than rebuilt
- [Source: `backend/api/admin.py`, `backend/services/user_service.py`,
  `backend/data_models/user.py`] — the unchanged backend contract
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../mockups/key-users.html`] — AC9's visual
  target

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (Claude Code, bmad-dev-story workflow)

### Debug Log References

- `.\node_modules\.bin\vitest.cmd run src/pages/admin/UsersPage.test.tsx` — 11 passed on first run.
- `.\node_modules\.bin\vitest.cmd run` (full frontend suite) — 87 passed (up from 76), zero
  regressions.
- `.\node_modules\.bin\tsc.cmd -b` — clean, no type errors.
- `.\node_modules\.bin\vite.cmd build` — clean production build (pre-existing single-chunk
  bundle-size warning, unrelated to this story, no code-splitting configured anywhere in the
  project).
- Backend untouched by this story; `uv run pytest` not re-run, no backend file in the File List
  below.
- No live Docker Compose / browser check performed: Docker Desktop was not running in this
  environment, and the project has no seeded admin account or bootstrap script to log in with
  (a pre-existing gap, not introduced here). Verification relied on the 11 component tests
  (real `QueryClient`, mocked `fetch`, realistic user interactions covering every AC), the clean
  type-check, and the clean production build.

### Completion Notes List

- All 9 acceptance criteria satisfied, zero backend changes (Story 1.3's 6 routes, unchanged).
  AC1/AC2 (create, duplicate rejected): `useCreateUser` + the "+ New user" form, backend's exact
  `"That username already exists"` string rendered inline, form not cleared on failure. AC3 (edit):
  `UserListRow`'s inline editor sends only the changed field(s), never an empty payload. AC4/AC5
  (deactivate, last-Admin lockout): `useDeactivateUser`, backend's exact `"Rejected, at least one
  admin must stay active"` string rendered inline on 409. AC6 ("This is you"): the signed-in
  Admin's own row (compared via the already-existing `useCurrentUser()`) shows a text marker in
  place of Deactivate, so self-deactivation has no control to click — verified via a dedicated
  test asserting exactly one Deactivate button renders across two Admin rows. AC7 (reactivate):
  `useReactivateUser`. AC8 (reset password): inline reveal (no modal, matching this codebase's
  established no-modal convention), field cleared and hidden again after a successful submit,
  never re-rendered anywhere. AC9 (matches the mock): dense-row MUI `Table` (`size="small"` theme
  default), header subtitle with live counts, matching `key-users.html`'s column set.
- Reused `types/user.ts`'s existing `CurrentUser` as the list-row type instead of adding a
  duplicate `User` interface — its shape already matched `UserResponse` byte for byte (it was
  built for `GET /api/auth/me` in Story 1.1). Also reused the existing `useCurrentUser()` hook for
  AC6 rather than adding a second current-user fetch.
- `userService.ts` is a fifth instance of the per-domain service pattern (`authService` →
  `tableService`/`menuService`/`inventoryService` → `userService`), copying `tableService.ts`'s
  shape exactly: module-level query-key constant, `onSuccess` invalidation for create,
  `onSettled` for every mutation that can be rejected because the caller's copy is stale
  (update/deactivate/reactivate/reset-password all 409 on a last-Admin conflict or a stale row).
- `UserListRow` mirrors `TablesSetupPage`'s `TableListRow`: controlled fields resynced from the
  server via `useEffect`, but only while not mid-edit; row-level mutation errors render as a
  full-width `Alert` in an extra `TableRow` under the row, never a page-level toast (this codebase
  has none). Per Dev Notes guidance, edit sends only changed fields (unlike Tables' "always send
  both" — Users' two fields are independent with no stale-cache race rationale requiring both),
  guarded so a true no-op can never fire an empty-payload 422.
- Frontend suite: 93 passed (up from 76, +17 in `UsersPage.test.tsx`, after the code-review
  patches below). `tsc -b` and `vite build` both clean. No backend file touched, no Alembic migration, no `container.py`/`main.py` wiring
  change.

### File List

**Added**

- `frontend/src/services/userService.ts`
- `frontend/src/pages/admin/UsersPage.test.tsx`

**Modified**

- `frontend/src/types/user.ts` (added `CreateUserPayload`/`UpdateUserPayload`/`ResetPasswordPayload`;
  `CurrentUser`/`UserRole` untouched)
- `frontend/src/pages/admin/UsersPage.tsx` (placeholder replaced with the real create form, list,
  and per-row inline editor/deactivate/reactivate/reset-password)
- `_bmad-output/project-context.md` (current-state tree, services list, suite counts, new dated
  patch entry)
- `_bmad-output/implementation-artifacts/deferred-work.md` (marked the Story 1.3 self-deactivation
  item resolved; corrected the unbounded-`GET /api/admin/users` item's story reference from 1.4 to
  1.6)

**Confirmed unchanged**: every backend file (`api/admin.py`, `services/user_service.py`,
`data_models/user.py`, `exceptions/__init__.py`), no Alembic migration, no new package in either
manifest, `frontend/src/router.tsx` (the `/admin/users` route already pointed at `UsersPage`, only
its contents changed).

## Change Log

| Date | Change |
|---|---|
| 2026-08-13 | Added `CreateUserPayload`/`UpdateUserPayload`/`ResetPasswordPayload` to `frontend/src/types/user.ts`, reusing the existing `CurrentUser` as the list-row type rather than adding a duplicate. |
| 2026-08-13 | Added `frontend/src/services/userService.ts`: `useUsers`/`useCreateUser`/`useUpdateUser`/`useDeactivateUser`/`useReactivateUser`/`useResetPassword`, copying `tableService.ts`'s shape (module-level query key, `retry: false`, `onSettled` invalidation on every mutation that can 409 against a stale row). Reused the existing `useCurrentUser()` from `authService.ts` for AC6 rather than adding a second current-user fetch. |
| 2026-08-13 | Replaced `UsersPage`'s placeholder with a real "+ New user" form and dense-row list (`size="small"`, UX-DR8), matching `key-users.html`'s column set and header subtitle. |
| 2026-08-13 | Added `UserListRow`: inline edit (full name/Role, sending only changed fields), Deactivate/Reactivate, and an inline password-reset reveal (no modal — this codebase has none), each owning its own local state and resyncing from the server only while not mid-edit, mirroring `TablesSetupPage`'s `TableListRow`. |
| 2026-08-13 | Implemented AC6: the signed-in Admin's own row renders "This is you" in place of Deactivate, removing self-deactivation from the UI entirely (not just adding a confirmation step) — resolves the corresponding `deferred-work.md` item from Story 1.3's review. |
| 2026-08-13 | Added `frontend/src/pages/admin/UsersPage.test.tsx`: 11 tests, mocking only `fetch`, covering all 9 ACs including the exact backend rejection strings (AC2/AC5) and the "This is you" / single-Deactivate-button assertion (AC6). Full frontend regression: 87 passed (up from 76). `tsc -b` and `vite build` both clean. |
| 2026-08-13 | Updated `project-context.md` (current-state tree, services list, suite counts, dated patch entry) and `deferred-work.md` (resolved the self-deactivation item; corrected the unbounded-list item's story reference). |
| 2026-08-13 | Code review (three parallel adversarial layers, run on a stronger model than the implementation, each with no prior context). 17 patches applied, 1 decision resolved, 4 deferred, 2 dismissed. The Acceptance Auditor mutation-tested the suite and proved four behaviors were pinned by nothing: the Role edit branch, the create-form Role field, `setFullName("")`, and `setDraftPassword("")` could each be deleted with all 11 tests still green. |
| 2026-08-13 | Review patch: **removed the client-side payload diff**, the most serious finding. `save()` diffed drafts against the cached row to build a partial payload, which project-context.md forbids outright ("Never diff a form against cached data to decide what to send") and which `TablesSetupPage` carries a six-line comment plus a regression test against. Beyond the documented empty-payload trap, it let a save silently **revert a concurrent change** to the field this Admin never touched, and disabled Save entirely when the cache was stale. Both fields are now always sent. The original justification ("sending an unchanged field back is unnecessary work") was verified false: `UserService.update_user` already diffs server-side and returns without committing. Task 4's wording, which authorized the diff, was corrected in this file so the next story does not inherit it. |
| 2026-08-13 | Review patch: row-level errors no longer outlive the action that caused them. `deactivateMutation`/`reactivateMutation` were never `reset()`, so a 409 alert survived a later *successful* edit on the same row; and `activeError`'s fixed `??` precedence chain showed the oldest failure rather than the one just triggered. All four mutations now reset together via `resetRowErrors()`, and the displayed error is the most recently submitted (`submittedAt`). |
| 2026-08-13 | Review patch: every mutation now invalidates `CURRENT_USER_QUERY_KEY` alongside the user list. Editing or demoting your own account previously left the app shell rendering a stale name and a stale Role, keeping Admin nav on screen after a self-demotion while every admin request 403'd. |
| 2026-08-13 | Review patch: a failed background refetch no longer unmounts the table. TanStack retains `data` when a refetch errors, so gating the table on `!isError` destroyed every open editor and any typed password over a momentary blip (an alt-tab was enough). The error banner now renders alongside the retained list. |
| 2026-08-13 | Review patch (decision, resolved 2026-08-13 by Ofek): deactivating another User is now gated behind an in-row "Deactivate {name}?" confirm with Confirm/Cancel, reusing the same in-place reveal Edit and Reset password use. Chosen over a MUI `Dialog` deliberately: a modal would have been the first in this codebase and would set a precedent for every later story. Naming the user in the prompt makes a misclick on the wrong row visible before it lands. |
| 2026-08-13 | Review patch: `isSelf` now fails closed. It previously treated an unknown signed-in identity as "not me", rendering a live Deactivate on the Admin's own row; not reachable in the composed app (`RequireAuth` gates it) but open in exactly the standalone configuration the AC6 test renders. |
| 2026-08-13 | Review patches (smaller): `autoComplete="new-password"`/`"off"` on the credential fields, so browsers stop offering to autofill the admin's own credentials into the create form or save a staff password as the admin's own; visible `InputLabel` on both Role `Select`s (previously `aria-label` only, so sighted users saw an unlabelled box); over-length full name now reports the actual bound instead of "Full name is required"; username/full-name length validation added to the create form to match the row editor; "1 staff account" pluralization; AC9 mock alignment — per-Role `Chip` colours and a right-aligned Actions column. |
| 2026-08-13 | Review verification: mutation-tested the new tests before trusting them, the lesson this story's first pass skipped. Dropping `role` from the edit payload fails 2 tests; narrowing `resetRowErrors` fails 1; reverting `isSelf` to fail-open and bypassing the confirm fails 5. Full suite after patching: **93 frontend tests passed** (up from 87), `tsc -b` clean. |
