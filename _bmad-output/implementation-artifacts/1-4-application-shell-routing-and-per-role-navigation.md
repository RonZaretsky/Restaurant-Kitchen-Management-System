---
baseline_commit: 4cb0879ea56f06094e024637ada2270d885dfb42
epic: 1
story: 4
---

# Story 1.4: Application Shell, Routing and Per-Role Navigation

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a staff member of any role,
I want the app to open on a working shell that shows me only my own surfaces,
so that every screen built in later epics has somewhere to live and I never see another role's tools.

## Acceptance Criteria

1. React Router v7 is wired with a route per IA surface, and an authenticated-route guard redirects any unauthenticated visit to Login. (AD-3, UX-DR19)
2. The nav lists only the current Role's own surfaces, with no cross-role navigation anywhere, and login lands the User on their Role's home surface: Waiter -> Tables, Cook -> Kitchen Display, Warehouse Manager -> Ingredients, Admin -> Menu Management. (FR-2, UX-DR19)
3. The Login screen is built per [key-login.html](../planning-artifacts/ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/mockups/key-login.html), showing the generic "Invalid username or password" copy inline on failure. (FR-1, UX-DR17, UX-DR19)
4. The theme toggle in the app bar flips light/dark and persists per browser/terminal (not per user account); Kitchen Display initializes dark, every other role's home initializes light. (UX-DR7)
5. The MUI theme overrides `primary` with `{colors.accent}` (light) / `{colors.accent-dark}` (dark); every other Button variant stays stock MUI; dense-row styling (`size="small"`, 36px rows) is available as the shared list/table convention. (UX-DR6, UX-DR8)
6. Any surface loading data for the first time renders MUI `Skeleton` rows/cards matching its expected layout, the shared cold-load pattern every later screen reuses. (UX-DR15)
7. One app-wide "Reconnecting..." state exists with automatic retry and no local-first write queue, driven by a transport-agnostic connection signal; Story 1.5 wires it to the live WebSocket. (UX-DR16)
8. The shell and its shared components meet the WCAG 2.2 AA contrast baseline in both themes, render a visible focus ring on every interactive element, and follow a logical tab order matching reading order. (UX-DR21)

## Scope note

**This story builds the shell, not the screens.** AC1 requires a route for all 13 IA surfaces, but 12 of
them (everything except Login) render a minimal placeholder for this story, matching the surface's own
mockup only for the chrome (app bar, nav) around it, not the mockup's body content. Each surface's real
content, data-fetching, and interactions ship in its own later epic/story (e.g. Tables in Epic 3,
Kitchen Display in Epic 5, Ingredients in Epic 4, Users/Menu Management/Recipe Suggestions/Tables setup
scattered across Epic 2/6 and one still-unassigned follow-up for the Admin Users screen specifically,
see `deferred-work.md`). Building any of that content now would be thrown away or diverge from the
domain story that actually owns it. **Do not build Tables, Kitchen Display, Ingredients, Menu
Management, or any other domain screen's real content in this story.**

No FR or AC in this epic covers logout. Do not add a logout button or action, there is nowhere in the
PRD, epics, or UX spine that calls for one; the session simply expires after 8 hours (AD-3).

## Tasks / Subtasks

- [x] **Task 1: Backend — `GET /api/auth/me`** (AC: 1, 2)
  - [x] The frontend's route guard and per-role nav need to know who is logged in and what Role they
    hold **after a page reload**, when all that exists client-side is an httpOnly cookie JavaScript
    cannot read. No endpoint for this exists yet (verified: `grep` across `backend/api/` finds no
    `/me` route). Add one to `backend/api/auth.py`, reusing `UserResponse` (already in
    `data_models/user.py`, already excludes `password_hash`) rather than inventing a new schema:
    ```python
    from api.dependencies import CurrentUserDep
    from api.responses import error_responses
    from data_models import LoginRequest, LoginResponse, User, UserResponse

    _ERROR_DESCRIPTIONS = {401: "No valid session cookie was supplied"}

    @router.get("/me", response_model=UserResponse, responses=error_responses(_ERROR_DESCRIPTIONS, 401))
    async def get_own_profile(user: CurrentUserDep) -> User:
        """Return the authenticated User's own profile.

        The frontend's only way to learn who is logged in and what Role they
        hold after a page reload, since the session cookie is httpOnly and
        unreadable by JavaScript (AD-3).

        Args:
            user: The authenticated User, resolved by the shared CurrentUserDep
                seam.

        Returns:
            The caller's own User record.

        Raises:
            NotAuthenticatedError: Propagated from get_current_user, handled
                globally as a 401, if no valid session cookie is present.
            SessionExpiredError: Same handling, if the cookie's token has
                expired.
        """
        return user
    ```
  - [x] Use `CurrentUserDep`, not `require_role(...)`. Every authenticated Role must be able to call
    this, it is not Admin-only.
  - [x] No change to `container.wire(modules=[...])`. `api.auth` is already in that list (Story 1.1);
    this route needs no new `@inject`/DI wiring since it takes no service dependency.
  - [x] Add a test to `backend/tests/test_auth.py` (reuse the file's existing `_create_user` helper,
    do not duplicate it): authenticated caller gets 200 with the full `UserResponse` shape
    (`id`, `username`, `full_name`, `role`, `is_active`, `created_at`), unauthenticated caller gets
    401 with the existing `NotAuthenticatedError` detail.

- [x] **Task 2: Frontend dependencies** (AC: all)
  - [x] pnpm is not on this machine's `PATH` yet. Enable it first, matching `frontend/Dockerfile`'s
    pin exactly: `corepack enable && corepack prepare pnpm@9.15.0 --activate`.
  - [x] From `frontend/`, add the three architecture-decided-not-yet-installed packages
    (`_bmad-output/project-context.md`'s installed-vs-decided table):
    `pnpm add react-router @mui/material @mui/icons-material @emotion/react @emotion/styled @tanstack/react-query`.
    Note the package is `react-router` (v7 merged what used to be `react-router-dom`), not
    `react-router-dom`. `@emotion/react`/`@emotion/styled` are MUI's default styling engine, both
    required peers, not optional. `@mui/icons-material` is needed now for the theme-toggle's
    sun/moon icons even though the status-badge icon set (`RadioButtonUncheckedIcon` etc.) isn't
    used until later stories.
  - [x] Commit the regenerated `pnpm-lock.yaml`. The Dockerfile's `pnpm install` will otherwise
    resolve different versions than whatever was used locally.
  - [x] No devDependency changes needed for testing, `vitest` + `@testing-library/react` +
    `jest-dom` already cover component testing. **Deviation, corrected during Task 12:** this was
    wrong, `@testing-library/user-event` was not installed and is needed for realistic tab-order and
    click interaction testing. Added as a devDependency; see Completion Notes.

- [x] **Task 3: Types and the auth service** (AC: 1, 2, 3)
  - [x] `frontend/src/types/user.ts`. Field names stay snake_case, matching the API's JSON keys
    exactly, there is no camelCase conversion anywhere in this backend (verified: no
    `alias_generator` in any Pydantic model). Do not invent a mapping layer.
    ```typescript
    export type UserRole = "admin" | "waiter" | "cook" | "warehouse_manager";

    export interface CurrentUser {
      id: number;
      username: string;
      full_name: string;
      role: UserRole;
      is_active: boolean;
      created_at: string;
    }
    ```
  - [x] `frontend/src/services/httpClient.ts`. A thin `fetch` wrapper, not axios (not an installed or
    decided dependency, and only two endpoints exist so far). Reads `config.api.baseUrl` /
    `config.api.timeoutMs` from `src/config/config.ts` (never `import.meta.env` directly, that rule
    is already established). Always sends `credentials: "include"`, the frontend (`:3000`) and
    backend (`:8000`) are different origins even in local dev, so the session cookie is not sent
    without it. Parse the error envelope per the architecture spine's Consistency Conventions: a
    failed response's `detail` is either a `string` (app-raised exceptions, `ErrorResponse`) or
    FastAPI's structured validation array (422s), check the type rather than assuming a string.
  - [x] `frontend/src/services/authService.ts`, exposed as TanStack Query hooks per the architecture
    spine's stated `services/` convention (server data lives only in the Query cache, AD-13, never
    duplicated into a parallel Context/store):
    ```typescript
    export function useLogin(): UseMutationResult<{ role: UserRole }, Error, { username: string; password: string }>
    export function useCurrentUser(): UseQueryResult<CurrentUser, Error>
    ```
    `useCurrentUser` calls `GET /api/auth/me` (Task 1). Set `retry: false` on it, a 401 there means
    "not logged in," not a transient failure, retrying just delays the redirect to Login.
    `useLogin` posts to `/api/auth/login`; on success, call
    `queryClient.invalidateQueries({ queryKey: ["auth", "me"] })` so the shell picks up the full
    profile, but navigate to the Role's home surface immediately using the `role` already in the
    login response, do not wait for the refetch.

- [x] **Task 4: MUI theme** (AC: 4, 5, 8)
  - [x] `frontend/src/config/theme.ts`. Two themes built with `createTheme`, everything inherited
    from MUI defaults except the one documented delta (`_bmad-output/planning-artifacts/ux-designs/.../DESIGN.md` Colors/Components):
    ```typescript
    export const lightTheme = createTheme({
      palette: { mode: "light", primary: { main: "#0B6E8F", contrastText: "#FFFFFF" } },
      components: { MuiTable: { defaultProps: { size: "small" } }, MuiList: { defaultProps: { dense: true } } },
    });
    export const darkTheme = createTheme({
      palette: { mode: "dark", primary: { main: "#4FC3D9", contrastText: "#08171B" } },
      components: { MuiTable: { defaultProps: { size: "small" } }, MuiList: { defaultProps: { dense: true } } },
    });
    export const DENSE_ROW_HEIGHT = 36;
    ```
    Do not override `shape.borderRadius` or `spacing`, both already match MUI's defaults (DESIGN.md
    states this explicitly, "No override"). `DENSE_ROW_HEIGHT` is exported for later stories to apply
    directly to row containers where the theme's component-default `size="small"` alone doesn't hit
    the exact 36px (e.g. a custom `<TableRow sx={{ height: DENSE_ROW_HEIGHT }}>`).
  - [x] Mount `<CssBaseline />` once, at the app root (Task 8). It resets focus-ring suppression
    along with everything else, do not add `outline: none` anywhere in this story's CSS, that is
    exactly the thing AC8 forbids.

- [x] **Task 5: Theme mode state and toggle** (AC: 4)
  - [x] `frontend/src/components/shell/ThemeModeProvider.tsx`. Local UI state, not server data
    (AD-13's Query-only rule is about server-derived data; light/dark mode is neither, plain React
    Context plus `localStorage` is correct here, same as the architecture spine's own "local
    component state covers the rest"). Persist under one fixed key (e.g. `"rkms-theme-mode"`) so it
    survives per browser/terminal, not per user account, per AC4's own wording.
  - [x] Initial-default rule (read `localStorage` first; only if nothing is stored yet does the
    following apply): light, unless the user's Role is `cook`, in which case dark. This can only be
    known once `useCurrentUser` resolves, so it is safe to apply once, on the shell's first real
    render after the auth-resolving load state (Task 7) clears, not before. Every role besides cook
    already defaults to light, so the only surface where this matters is Kitchen Display, and Login
    itself (pre-auth) is always light per its own mockup.
  - [x] `frontend/src/components/shell/ThemeToggle.tsx`. One `IconButton` (MUI default styling, no
    override, per DESIGN.md's `{components.theme-toggle}`) using MUI's own sun/moon icons from
    `@mui/icons-material`, flips the mode and writes it to `localStorage` immediately.

- [x] **Task 6: Connection-status scaffold** (AC: 7)
  - [x] `frontend/src/components/shell/ConnectionStatusContext.tsx`. A context typed
    `{ status: "connected" | "reconnecting" }`, provider defaulting to `{ status: "connected" }`
    (hardcoded, there is no real transport to observe yet, Story 1.5 replaces this default with a
    live WebSocket signal, the context's shape is the contract that story must match, do not change
    it casually there).
  - [x] `frontend/src/components/shell/ReconnectingBanner.tsx`. Reads the context, renders nothing
    when `"connected"`, renders a plain MUI `Alert` reading "Reconnecting..." (exact copy, per
    EXPERIENCE.md Voice and Tone) when `"reconnecting"`. Mount once in the shell (Task 8), not once
    per page, so it is genuinely the one app-wide instance AC7 requires.

- [x] **Task 7: Shared cold-load Skeleton pattern** (AC: 6)
  - [x] `frontend/src/components/shell/RowsSkeleton.tsx` (and a card variant if the shell needs one;
    the shell itself only needs the rows variant, see below). Reusable: `count` prop, each row an
    MUI `Skeleton` sized to `DENSE_ROW_HEIGHT` (Task 4). This is the pattern every later story reuses
    for its own cold-load state (UX-DR15), building it once here is the point of AC6, not full
    coverage of all 13 surfaces' real loading states, those don't exist until each surface's own data
    fetching is built.
  - [x] The one real loading state this story has: `useCurrentUser` resolving on first app load.
    While it is `isLoading`, the shell renders the app bar's shape with `RowsSkeleton` standing in
    for the nav links and user chip, not a blank screen and not a spinner (a spinner would not
    satisfy AC6's "renders MUI Skeleton rows/cards").

- [x] **Task 8: Navigation config and the AppShell chrome** (AC: 2, 8)
  - [x] `frontend/src/components/shell/navigationConfig.ts`. One static map, the single source of
    truth for both the nav (this task) and the route guard/redirects (Task 9), derived directly from
    the mockups' own address bars (see Dev Notes' route table):
    ```typescript
    export const ROLE_HOME_PATH: Record<UserRole, string> = {
      admin: "/admin/menu",
      waiter: "/waiter/tables",
      cook: "/cook/kitchen-display",
      warehouse_manager: "/warehouse/ingredients",
    };
    export const ROLE_NAV_ITEMS: Record<UserRole, { label: string; path: string }[]> = {
      admin: [
        { label: "Menu Management", path: "/admin/menu" },
        { label: "Recipe Suggestions", path: "/admin/recipe-suggestions" },
        { label: "Users", path: "/admin/users" },
        { label: "Tables setup", path: "/admin/tables" },
      ],
      waiter: [{ label: "Tables", path: "/waiter/tables" }],
      cook: [
        { label: "Kitchen Display", path: "/cook/kitchen-display" },
        { label: "Dishes", path: "/cook/dishes" },
        { label: "Smart Chef", path: "/cook/smart-chef" },
      ],
      warehouse_manager: [
        { label: "Ingredients", path: "/warehouse/ingredients" },
        { label: "Alerts", path: "/warehouse/alerts" },
      ],
    };
    ```
  - [x] `frontend/src/components/shell/AppShell.tsx`. MUI `AppBar` (title "RKMS", matching
    `key-login.html`'s `brandmark`) + nav links from `ROLE_NAV_ITEMS[user.role]` in DOM order left to
    right (matches the mockup's visual order, needed for AC8's tab-order requirement) + a user chip
    (`"{full_name} · {role}"`, title-cased for display) + `ThemeToggle` (Task 5) + `<Outlet />` for
    the active route's page. Mount `ReconnectingBanner` (Task 6) here too, once, above the `Outlet`.
    Nav links render only the current Role's own entries, this is the literal mechanism behind AC2's
    "no cross-role navigation anywhere."

- [x] **Task 9: Route guard and redirects** (AC: 1, 2)
  - [x] `frontend/src/components/shell/RequireAuth.tsx`. Calls `useCurrentUser()` directly (Task 3),
    does not duplicate it into a separate Context, that would be exactly the "server data duplicated
    into ad-hoc local/global state" AD-13 prohibits. Three states:
    - `isLoading`: render the Task 7 skeleton shell.
    - error (401, "not logged in"): `<Navigate to="/login" replace />`. This is AC1's guard.
    - success: render `<AppShell />` (Task 8), which renders `<Outlet />` for the matched child
      route.
  - [x] Role-scoped redirect (a reasonable extension of AC2's "I never see another role's tools" from
    the story's own goal statement, not literally spelled out as a separate AC bullet, flagging this
    as a judgment call): inside `RequireAuth`, once the user is known, if the current path does not
    start with that Role's own prefix (`/admin`, `/waiter`, `/cook`, `/warehouse`) and is not `/`,
    redirect to `ROLE_HOME_PATH[user.role]` instead of rendering another Role's page. A direct URL
    edit to another Role's surface should not render that Role's UI even though nothing in the AC
    text names this scenario explicitly.
  - [x] Root path `/`: redirect to `ROLE_HOME_PATH[user.role]` once authenticated (this is what
    "login lands them on their Role's home surface" means at the routing layer, AC2).

- [x] **Task 10: Router wiring, 13 routes** (AC: 1, 2)
  - [x] `frontend/src/main.tsx` (or a new `frontend/src/router.tsx` if that keeps `main.tsx` thin,
    either is fine): `createBrowserRouter` + `RouterProvider` from `"react-router/dom"` (declarative
    mode, not framework mode, this project has no `@react-router/dev` Vite plugin and Vite is already
    the bundler; framework mode would require restructuring around a different dev server plugin
    that is not a decided dependency). One layout route wrapping `RequireAuth`, thirteen leaf routes
    underneath it (see Dev Notes' route table for exact paths, taken directly from the mockups'
    address bars), plus a public `/login` route outside the guard. **Deviation:** `RouterProvider`
    is imported from `"react-router"` core instead, not `"react-router/dom"`. That subpath's wrapper
    reproducibly breaks the Router context under this project's React 19.2.6 + react-router 7.8.0 +
    jsdom combination (verified with a minimal repro outside this app's own code, not a mocking
    artifact); everything routing-related this story needs is already on the core export. Documented
    in `project-context.md`'s Testing section. Built `router.tsx` separate from `App.tsx`, exporting
    `routes` (the plain config array) alongside the `router` instance, so tests build their own
    `createMemoryRouter` from the exact same route tree.
  - [x] Twelve of the thirteen non-Login routes render a placeholder page (one file per surface,
    under `pages/{role}/`, see Dev Notes' File Structure) whose entire content is the surface's own
    title, e.g. `<Typography variant="h5">Kitchen Display</Typography>`, nothing else. Do not add
    empty-state copy, mock data, or partial layouts, per the Scope note above, that belongs to each
    surface's own future story.
  - [x] Wrap the router in `QueryClientProvider` (new `QueryClient()`, defaults are fine, no custom
    `staleTime`/`gcTime` tuning needed for this story) and `ThemeModeProvider` (Task 5) plus
    `ConnectionStatusContext.Provider` (Task 6), in `frontend/src/App.tsx`. Retire `App.tsx`'s
    current placeholder body (the bare `<h1>`), it becomes this provider composition root instead.

- [x] **Task 11: Login page** (AC: 3)
  - [x] `frontend/src/pages/login/LoginPage.tsx`, built to
    [key-login.html](../planning-artifacts/ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/mockups/key-login.html):
    username/password `TextField`s, primary `Button` ("Sign in"), on failure show the error inline
    per-field plus the line "Invalid username or password." (exact copy, generic on purpose per
    FR-1's no-enumeration requirement, EXPERIENCE.md State Patterns). On success, `useLogin`'s
    mutation already redirects (Task 3); this component only needs to call it and render its
    pending/error state. **Judgment call:** the error line renders `loginMutation.error.message`
    (the live text `httpClient` extracted from the backend's `detail`, "Invalid username or
    password" with no trailing period, `exceptions/__init__.py`'s actual string) rather than a
    hardcoded copy of EXPERIENCE.md's mockup text (which has a period). This follows the same
    spine's own "Error (generic)" state-pattern rule elsewhere: "sourced from the architecture
    spine's error envelope," never a UI-owned copy that can drift from what the backend actually
    sends.
  - [x] If a Login visit happens while already authenticated (e.g. the User manually navigates back
    to `/login`), redirect to `ROLE_HOME_PATH[user.role]` instead of showing the form again.

- [x] **Task 12: Tests** (AC: all)
  - [x] Backend: Task 1's two tests in `test_auth.py`, plus `uv run pytest` full regression (this
    story touches `api/auth.py`, shared by every existing `test_auth.py`/`test_authorization.py`
    test). **109 tests pass** (107 pre-existing + 2 new).
  - [x] Frontend, `pnpm test`. **Deviation:** mocked `services/authService.ts`'s exported hooks
    (`useCurrentUser`/`useLogin`) via `vi.mock` for the routing/nav/theme/login integration tests,
    rather than mocking `global.fetch` directly, this is the more natural boundary for testing
    component behavior against query state (loading/error/success), and avoids re-deriving TanStack
    Query's own request lifecycle in every test. To close the resulting gap (nothing was exercising
    `httpClient.ts` itself), added a dedicated `httpClient.test.ts` that mocks `global.fetch`
    directly and covers `credentials: "include"`, successful JSON parsing, and both `detail` shapes
    (string and FastAPI's validation array). At minimum:
    - AC1: an unauthenticated visit to any protected path (mock `useCurrentUser` returning a 401/
      error state) renders `/login`, not the requested page.
    - AC2: an authenticated Cook sees only Kitchen Display/Dishes/Smart Chef in the nav; each of the
      four roles visiting `/` lands on its documented home path; a successful login (mocked
      `mutate` invoking its own `onSuccess`) navigates to the role's home surface; a direct
      cross-role URL visit redirects to the caller's own home instead of rendering the other role's
      page.
    - AC3: submitting bad credentials renders the live error message inline (see Task 11's judgment
      call on exact copy) and does not navigate away from `/login`; submitting valid-looking
      credentials calls the mutation with exactly the entered values.
    - AC4: clicking the theme toggle flips the mode and the value written to `localStorage`; a fresh
      mount with no stored preference and a `cook` role defaults dark, `admin` defaults light.
    - AC6: the shell renders the loading skeleton (`role="status"`) while the current-user query is
      still loading; a direct `RowsSkeleton` unit test covers row count.
    - AC7: `ReconnectingBanner` renders nothing under the default `"connected"` context value, and
      renders "Reconnecting..." when the context is overridden to `"reconnecting"`.
    - AC8: `userEvent.tab()` through the app bar's nav links, asserting focus lands on them in the
      same order they appear in the DOM. **Scope note:** covers the nav links specifically (the
      part of the app bar whose visual order most plausibly diverges from DOM order); does not also
      assert the theme toggle's position in the same sequence.
  - [x] Discovered and fixed two real infrastructure gaps, both documented in
    `project-context.md`'s Testing section for future stories:
    1. `@testing-library/react`'s auto-cleanup never registered (this project's `globals: false`
       defeats its detection), so a second `render()` in the same test file leaked DOM from the
       first. Fixed with an explicit `afterEach(cleanup)` in `setupTests.ts`. No test in this story
       needed the `matchMedia` polyfill the story anticipated; none of MUI's components used here
       call it.
    2. `RouterProvider` from `"react-router/dom"` reproducibly breaks Router context under this
       project's React 19.2.6 + react-router 7.8.0 combination (verified with a minimal repro, not
       a testing artifact). Switched to the core `"react-router"` export everywhere, including in
       `App.tsx` itself, not just tests (see Task 10's deviation note).
  - [x] Rewrote `frontend/src/App.test.tsx`: the old literal-`<h1>` assertion no longer applies once
    `App.tsx` became the provider composition root. Replaced with an integration smoke test
    asserting an unauthenticated render of `App` ends up on the Login screen.

## Dev Notes

### Architecture compliance

- **AD-13** (binding on all frontend code): React Router v7 owns routing, MUI is the only UI
  component library, TanStack Query is the only cache for server-derived data. This story is the
  first to touch any of the three; get the pattern right here since every later frontend story
  copies it. [Source: architecture spine AD-13]
- **AD-3**: the session cookie is httpOnly, `Secure`, `SameSite=lax`, 8-hour expiry, no refresh flow.
  The frontend cannot read it and cannot renew it silently, `useCurrentUser` failing means "log in
  again," not "retry." [Source: architecture spine AD-3, `_bmad-output/project-context.md` trap 7]
- **Dependency direction** (frontend mirrors the backend's): `pages/` may depend on `components/` and
  `services/`; `components/` may depend on `services/` and `types/`; `services/` may depend on
  `types/`; nothing imports `pages/`. The placeholder pages (Task 10) depend on nothing but MUI, the
  `AppShell`/`RequireAuth`/`ThemeToggle`/etc. components (Task 5-9) depend on `services/authService.ts`
  and `types/user.ts`, never the other way. [Source: architecture spine, "Rule (dependency
  direction)"]
- No backend file this story touches is on any prior story's must-not-change list. `api/auth.py` was
  last touched in Story 1.1; nothing since has claimed ownership of it.

### Route table (source of truth: the mockups' own address bars, not invented)

| Path | Surface | Role | Home? |
|---|---|---|---|
| `/login` | Login | (unauthenticated) | - |
| `/waiter/tables` | Tables | waiter | yes |
| `/waiter/tables/:tableId` | Table/Order detail | waiter | |
| `/cook/kitchen-display` | Kitchen Display | cook | yes |
| `/cook/dishes` | Dishes (view-only) | cook | |
| `/cook/smart-chef` | Smart Chef | cook | |
| `/warehouse/ingredients` | Ingredients | warehouse_manager | yes |
| `/warehouse/ingredients/:ingredientId` | Ingredient detail | warehouse_manager | |
| `/warehouse/alerts` | Alerts | warehouse_manager | |
| `/admin/menu` | Menu Management | admin | yes |
| `/admin/recipe-suggestions` | Recipe Suggestions | admin | |
| `/admin/users` | Users | admin | |
| `/admin/tables` | Tables setup | admin | |

Verified against every `key-*.html` mockup's `.address-bar` text (e.g. `key-tables.html` ->
`rkms.local/waiter/tables`, `key-table-order-detail.html` -> `rkms.local/waiter/tables/12`). 13 rows,
matching EXPERIENCE.md's "13 surfaces" count including Login. `:tableId`/`:ingredientId` are route
params for later stories to read, not used by this story's placeholder pages.

### File structure (new files)

```
backend/api/auth.py                              # + GET /me (Task 1)
backend/tests/test_auth.py                        # + 2 tests (Task 1)

frontend/src/types/user.ts                        # UserRole, CurrentUser (Task 3)
frontend/src/services/httpClient.ts                # fetch wrapper (Task 3)
frontend/src/services/authService.ts               # useLogin, useCurrentUser (Task 3)
frontend/src/config/theme.ts                       # lightTheme, darkTheme, DENSE_ROW_HEIGHT (Task 4)
frontend/src/components/shell/ThemeModeProvider.tsx
frontend/src/components/shell/ThemeToggle.tsx
frontend/src/components/shell/ConnectionStatusContext.tsx
frontend/src/components/shell/ReconnectingBanner.tsx
frontend/src/components/shell/RowsSkeleton.tsx
frontend/src/components/shell/navigationConfig.ts
frontend/src/components/shell/AppShell.tsx
frontend/src/components/shell/RequireAuth.tsx
frontend/src/pages/login/LoginPage.tsx
frontend/src/pages/waiter/TablesPage.tsx
frontend/src/pages/waiter/TableOrderDetailPage.tsx
frontend/src/pages/cook/KitchenDisplayPage.tsx
frontend/src/pages/cook/DishesPage.tsx
frontend/src/pages/cook/SmartChefPage.tsx
frontend/src/pages/warehouse/IngredientsPage.tsx
frontend/src/pages/warehouse/IngredientDetailPage.tsx
frontend/src/pages/warehouse/AlertsPage.tsx
frontend/src/pages/admin/MenuManagementPage.tsx
frontend/src/pages/admin/RecipeSuggestionsPage.tsx
frontend/src/pages/admin/UsersPage.tsx
frontend/src/pages/admin/TablesSetupPage.tsx
```

**Modified**: `frontend/src/App.tsx` (becomes the provider composition root), `frontend/src/App.test.tsx`
(rewritten, Task 12), `frontend/src/main.tsx` (mounts `App`, likely unchanged if `App.tsx` absorbs the
router/providers, verify), `frontend/package.json` + `frontend/pnpm-lock.yaml` (Task 2).

No file under `backend/services/`, `backend/data_models/`, `backend/exceptions/`, or
`backend/container.py` needs to change. `UserResponse` (already exists) is reused as-is for `/me`.

### Judgment calls this story makes (flagging for review, not hiding them)

- **Adding `GET /api/auth/me`.** Not named by any FR/AC/AD, but AC1/AC2 are unbuildable across a page
  reload without it (see Task 1's reasoning). The alternative, storing role client-side in
  non-httpOnly storage after login, would mean a User whose Role an Admin changes mid-session keeps
  acting on stale permissions until they manually reload, worse than one extra GET.
- **The role-scoped route guard** (Task 9). AC2's literal text is about nav *contents*, not URL
  access. Redirecting a direct cross-role URL visit instead of rendering it is inferred from the
  story's own "I never see another role's tools" line. If this is unwanted, the fix is a one-line
  removal in `RequireAuth`, everything else (nav, home redirect) stands on its own.
- **`config/theme.ts` for the MUI theme, not a new `theme/` folder.** `config/` is already documented
  as this project's home for app-wide static configuration (today just `config.ts`); a new top-level
  frontend folder for one file would repeat the "don't add a sixth for something that fits one" trap
  the backend already learned. Same reasoning put `navigationConfig.ts` under `components/shell/`
  rather than `config/`, it is UI-only data consumed exclusively by shell components, not env/app
  config.
- **No `matchMedia`-based system-preference detection for the initial theme.** AC4 specifies a
  role-based default (Kitchen Display dark, everything else light), which is a deliberate design
  decision (glare/distance legibility at the pass), not a stand-in for "respect the OS setting." Do
  not add `prefers-color-scheme` detection, it would silently override the documented rule.

### Testing

- Backend: existing `client`/`db_session` fixtures, `AuthService.hash_password` for seeding, no new
  fixtures needed. [Source: `_bmad-output/project-context.md` Testing]
- Frontend: `pnpm test` runs `vitest run`. `globals: false` in `vite.config.ts`, every test file
  imports `describe`/`it`/`expect` from `"vitest"` explicitly (see `App.test.tsx`, the only existing
  example). Test files skip docstrings, `# Arrange`/`# Act`/`# Assert` comments instead, per
  `_bmad-output/project-context.md`'s test-file carve-out, same rule as the backend suite.
- No dependency for mocking network calls exists yet; use a plain `vi.spyOn(global, "fetch")` or
  equivalent rather than adding MSW for this story alone.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 1.4: Application Shell, Routing and
  Per-Role Navigation`] - acceptance criteria, FR-1/FR-2, AD-3, UX-DR6/7/8/15/16/17/19/21
- [Source: `_bmad-output/planning-artifacts/architecture/architecture-Restaurant-Kitchen-Management-System-2026-07-30/ARCHITECTURE-SPINE.md#AD-13`]
  - React Router v7 / MUI / TanStack Query ownership rule, frontend dependency direction, Stack
  versions (React Router 7.8.0, MUI v9, TanStack Query v5)
- [Source: `_bmad-output/planning-artifacts/ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/DESIGN.md`]
  - accent color tokens, dense-row convention, theme-toggle spec, Do's and Don'ts
- [Source: `_bmad-output/planning-artifacts/ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/EXPERIENCE.md`]
  - Information Architecture table (13 surfaces), State Patterns (Skeleton/Reconnecting/Invalid
  credentials copy), Accessibility Floor, Voice and Tone
- [Source: mockups `key-login.html`, `key-tables.html`, and every other `key-*.html`'s
  `.address-bar`] - Login screen layout, app bar/nav chrome, the route table above
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md#code review of story-1-3`] -
  the Admin Users screen's real content (pagination need, self-deactivation confirm step) is
  explicitly deferred past this story; do not build it here
- [Source: `backend/data_models/user.py`, `backend/api/admin.py`] - `UserResponse` shape, the
  `error_responses()`/`AdminDep`-style pattern Task 1 follows for `/me`

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (Claude Sonnet 5)

### Debug Log References

- `uv run pytest -q` (backend): 107 passed before this story's changes, 109 passed after (2 new
  `/me` tests). No regressions.
- `pnpm test` (frontend): 24 tests across 7 files, all passing after two infrastructure fixes (see
  Completion Notes).
- `tsc -b` (frontend): clean, no errors, after every change.
- `vite build` (frontend): clean production build, one pre-existing "chunk larger than 500kB"
  advisory warning (MUI + react-router + tanstack-query in a single bundle), not a new regression
  and not addressed here, code-splitting is out of scope for this story.
- Repro used to isolate the `react-router/dom` bug: a two-component test file rendering
  `RouterProvider` (from `"react-router/dom"`) around a component calling `useLocation()` (from
  `"react-router"`), created and deleted during investigation, not part of the final test suite.

### Completion Notes List

- Implemented `GET /api/auth/me` (Task 1) before any frontend work, since the route guard and
  per-role redirect are structurally impossible to build against a page reload without it.
- Built the full shell: MUI theme (accent-only override, dense-row component defaults), theme mode
  Context with role-based initial default and `localStorage` persistence, a connection-status
  scaffold Story 1.5 will wire to a real transport, a shared row-skeleton pattern, per-role
  nav/home-path config, the app bar shell, the route guard, the 13-route tree, and the Login screen.
- Two deviations from the story text, both verified necessary rather than stylistic:
  1. **`RouterProvider` from `"react-router"` core, not `"react-router/dom"`.** The `/dom` subpath's
     wrapper (adds `flushSync: ReactDOM.flushSync`) reproducibly breaks Router context under this
     project's exact React 19.2.6 + react-router 7.8.0 combination, `useLocation`/`useNavigate`/
     `NavLink` all throw "may be used only in the context of a `<Router>` component." Confirmed with
     a minimal two-component repro outside any of this story's own code before changing anything, so
     this is not a mocking or test-harness artifact. Applied everywhere, not just in tests.
  2. **Added `@testing-library/user-event` as a devDependency.** The story's Task 2 assumed no new
     devDependencies were needed; that was wrong once AC8's tab-order test needed realistic
     Tab-key-driven focus traversal, which `fireEvent` cannot simulate well.
- One test-infrastructure bug fixed that was latent since Story 1.0 and only surfaced once a test
  file had more than one `it()` block that called `render()`: `@testing-library/react`'s automatic
  cleanup detects a global `afterEach`, and `vite.config.ts`'s `globals: false` never provides one.
  Added an explicit `afterEach(cleanup)` to `setupTests.ts`. `App.test.tsx` never hit this before
  because it only ever had one test.
- `project-context.md` updated: installed-vs-decided table (nothing left pending on the frontend),
  both current-state trees (frontend was "scaffold only," backend's tree had also drifted since
  Story 1.3), two new Testing entries for the bugs above, and a dated patch note.
- **Not verified in this session:** an actual browser render of the app. Automated coverage is
  thorough (tsc, production build, 24 frontend tests exercising the real component tree through
  `RouterProvider`/`QueryClientProvider` with only the network boundary mocked, 109 backend tests
  including 2 new ones hitting a real Postgres-backed app via `httpx.AsyncClient`), but no headless
  browser or manual click-through was available in this environment. Recommend a manual
  `docker compose up` + browser check before considering this story fully done, particularly for
  visual/contrast claims (AC5, AC8's contrast half) that automated tests cannot verify.
- AC5 (accent color override, dense-row convention) and AC8's WCAG contrast-ratio claim are
  satisfied by configuration (the theme's `primary.main`/`contrastText` values are DESIGN.md's own
  pre-verified hex codes) rather than by a dedicated automated test; no accessibility-testing
  library (e.g. `axe-core`) was added, consistent with EXPERIENCE.md's explicit "no dedicated
  screen-reader/a11y tooling beyond the stated baseline" scope line.

### File List

**Backend**
- `backend/api/auth.py` (modified) - added `GET /api/auth/me`
- `backend/tests/test_auth.py` (modified) - added `test_me_returns_the_authenticated_users_profile`, `test_me_without_a_session_is_rejected`

**Frontend — new**
- `frontend/src/types/user.ts`
- `frontend/src/services/httpClient.ts`
- `frontend/src/services/httpClient.test.ts`
- `frontend/src/services/authService.ts`
- `frontend/src/config/theme.ts`
- `frontend/src/router.tsx`
- `frontend/src/router.test.tsx`
- `frontend/src/components/shell/ThemeModeProvider.tsx`
- `frontend/src/components/shell/ThemeModeProvider.test.tsx`
- `frontend/src/components/shell/ThemeToggle.tsx`
- `frontend/src/components/shell/ConnectionStatusContext.tsx`
- `frontend/src/components/shell/ReconnectingBanner.tsx`
- `frontend/src/components/shell/ReconnectingBanner.test.tsx`
- `frontend/src/components/shell/RowsSkeleton.tsx`
- `frontend/src/components/shell/RowsSkeleton.test.tsx`
- `frontend/src/components/shell/navigationConfig.ts`
- `frontend/src/components/shell/AppShell.tsx`
- `frontend/src/components/shell/RequireAuth.tsx`
- `frontend/src/pages/login/LoginPage.tsx`
- `frontend/src/pages/login/LoginPage.test.tsx`
- `frontend/src/pages/waiter/TablesPage.tsx`
- `frontend/src/pages/waiter/TableOrderDetailPage.tsx`
- `frontend/src/pages/cook/KitchenDisplayPage.tsx`
- `frontend/src/pages/cook/DishesPage.tsx`
- `frontend/src/pages/cook/SmartChefPage.tsx`
- `frontend/src/pages/warehouse/IngredientsPage.tsx`
- `frontend/src/pages/warehouse/IngredientDetailPage.tsx`
- `frontend/src/pages/warehouse/AlertsPage.tsx`
- `frontend/src/pages/admin/MenuManagementPage.tsx`
- `frontend/src/pages/admin/RecipeSuggestionsPage.tsx`
- `frontend/src/pages/admin/UsersPage.tsx`
- `frontend/src/pages/admin/TablesSetupPage.tsx`

**Frontend — modified**
- `frontend/src/App.tsx` (provider composition root, replacing the placeholder `<h1>`)
- `frontend/src/App.test.tsx` (rewritten smoke test)
- `frontend/src/setupTests.ts` (added explicit `afterEach(cleanup)`)
- `frontend/package.json` (react-router, @mui/material, @mui/icons-material, @emotion/react,
  @emotion/styled, @tanstack/react-query added; @testing-library/user-event added as a devDependency)
- `frontend/pnpm-lock.yaml` (regenerated)
- `frontend/Dockerfile` (copies the new `nginx.conf` over nginx's stock default site config)

**Frontend — new (deployment)**
- `frontend/nginx.conf` - SPA history fallback (`try_files $uri $uri/ /index.html`), without which a
  refresh or direct hit on any client-side route (`/login`, `/admin/users`, ...) 404s

**Planning artifacts**
- `_bmad-output/project-context.md` (installed-vs-decided table, both current-state trees, two new
  Testing entries, dated patch note)

## Change Log

| Date | Change |
|---|---|
| 2026-08-10 | Story drafted from `epics.md` Story 1.4, the UX spine (`DESIGN.md`/`EXPERIENCE.md`), and the architecture spine's AD-13. Route table sourced from the mockups' own address bars rather than invented. Flagged one backend addition (`GET /api/auth/me`) as necessary infrastructure not named by any FR/AC. |
| 2026-08-10 | Implemented: `GET /api/auth/me`; the full frontend shell (routing, per-role nav, MUI theme, theme toggle, connection-status and Skeleton scaffolds, route guard, Login screen, 12 placeholder pages). Fixed two test-infrastructure gaps found during implementation (RTL auto-cleanup, `react-router/dom`'s broken `RouterProvider`) and documented both in `project-context.md`. 109 backend tests and 24 frontend tests passing; `tsc -b` and `vite build` both clean. |
| 2026-08-11 | Manual verification against a real Docker Compose stack surfaced a deployment-side routing defect the mocked tests could not see: the frontend image shipped nginx's stock config, so refreshing or directly opening any client-side route returned 404. Added `frontend/nginx.conf` with the SPA history fallback and wired it into the image. `/login` and `/admin/users` now return 200 on a direct request. |
