---
baseline_commit: 9c36de02c84d02877d7b73e60daedfcb6245a4e8
epic: 2
story: 5
---

# Story 2.5: Cook Browses the Dish Catalog

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Cook,
I want to browse the dish catalog with each dish's recipe and plating notes,
so that I can see how to prepare something without asking an Admin or leaving the kitchen.

**Scope note.** This is the first Cook-facing screen with real content (`pages/cook/DishesPage.tsx`
is currently a title-only placeholder from Story 1.0/1.4). Unlike Stories 1.1-2.2, this story is
**not** backend-only: it needs both a backend Role-gate change and a real frontend page. It adds
**zero new backend endpoints and zero new schemas** — Story 2.3 already built
`GET /api/menu/categories`, `GET /api/menu/dishes`, and `GET /api/menu/dishes/{id}/recipe-ingredients`,
and Story 2.1 already built `GET /api/inventory/ingredients`. All four already return exactly the
data this story needs; they are simply Admin-only (or Admin/Warehouse-Manager-only) today. The only
backend change is widening two `require_role(...)` dependencies to also permit `UserRole.cook` on
**read paths only** — every write path (create/update/delete on any of these resources) stays
exactly as restricted as it is today. Do not add a new route, a new response schema, or a
combined/nested "dish with recipe" endpoint; reuse the four existing ones exactly as the frontend's
`services/menuService.ts` and `services/inventoryService.ts` already call them.

**This story flips two existing tests, it does not just add new ones.** `test_menu.py` currently has
`test_cook_cannot_list_categories_or_read_a_recipe` (asserting 403 on reads that must become 200
after this story) and `test_inventory.py` has `test_cook_cannot_list_ingredients` (same). Both must
be corrected, not left in place contradicting the new behavior, and not merely duplicated alongside
a new passing test.

## Acceptance Criteria

**AC1 — Full catalog, read-only fields**
Given a Cook opens the Dishes surface, when it loads, then every Dish is listed with its name,
description, price, prep time, category, availability, and its Recipe Ingredient lines (FR-25).
Recipe Ingredient lines must show the **Ingredient's name**, not its bare id (`RecipeIngredientResponse`
has only `ingredient_id`; join it against `GET /api/inventory/ingredients`, the same way
`DishRecipeEditor.tsx` already does for the Admin screen).

**AC2 — Strictly read-only**
Given a Cook is viewing the Dishes surface, when they look for a way to change anything, then no
create, edit, availability-toggle, or delete control exists; this surface is strictly read-only and
menu authoring stays Admin-only via Stories 2.2/2.3 (FR-25, FR-2).

**AC3 — Empty state**
Given no dishes exist on the menu yet, when the surface loads, then it shows "No dishes on the menu
yet" (UX-DR15, the exact copy `MenuManagementPage.tsx` already uses for the same empty state).

**AC4 — Always current, never stale**
Given an Admin changes a Dish's recipe or availability (Stories 2.2/2.3), when a Cook next loads the
Dishes surface, then they see the current definition, never a stale copy (FR-25, FR-23). Satisfied
by reusing `useDishes`/`useCategories`/`useRecipeIngredients`/`useIngredients` as-is: none of them
set a non-zero `staleTime`, so React Query refetches on every mount, matching the guarantee Story
2.3 already established and tested for the Admin screen.

## Tasks / Subtasks

- [x] **Task 1: Widen the two read dependencies to permit Cook** (AC: 1)
  - [x] `backend/api/menu.py`: add a `MenuReadDep`, separate from the existing (write-only) `MenuDep`:
    ```python
    MenuReadDep = Annotated[User, Depends(require_role(UserRole.admin, UserRole.cook))]
    ```
    Change **only** `list_categories`, `list_dishes`, and `list_recipe_ingredients` to depend on
    `MenuReadDep` instead of `MenuDep`. Every other route in this file (`create_category`,
    `create_dish`, `update_dish`, `add_recipe_ingredient`, `update_recipe_ingredient`,
    `remove_recipe_ingredient`) **must keep using `MenuDep`** (admin-only), unchanged.
  - [x] `backend/api/inventory.py`: `InventoryReadDep` currently permits `admin, warehouse_manager`.
    Add `UserRole.cook` to that same tuple (`list_ingredients` is the only route using
    `InventoryReadDep`; `InventoryWriteDep`, used by `create_ingredient`, stays untouched at
    `admin, warehouse_manager`). Update `InventoryReadDep`'s own comment, it currently says "Reads
    permit the same two Roles as writes here", which stops being true once Cook is added; rewrite it
    to explain Cook needs ingredient *names* to render a recipe's ingredient list (Story 2.5), not
    stock levels.
  - [x] Update both routers' `_ERROR_DESCRIPTIONS[403]` wording if it names the specific permitted
    Roles (check both files; `api/menu.py`'s currently says "not admin", `api/inventory.py`'s says
    "neither admin nor warehouse_manager" — both are now inaccurate for the read paths and should
    read something like "Authenticated, but the caller's Role is not permitted for this action" or
    otherwise not enumerate a stale Role list for an error shared across a write and a read route).
- [x] **Task 2: Fix the two now-incorrect existing tests** (AC: 1)
  - [x] `backend/tests/test_menu.py`: `test_cook_cannot_list_categories_or_read_a_recipe` currently
    asserts 403 on `GET /api/menu/categories` and `GET /api/menu/dishes/{id}/recipe-ingredients` for
    a Cook. Split it: rename/rewrite so the two `GET`s now assert 200, and keep only the `PATCH`
    assertion (still 403) — either in the same test renamed to reflect what it now actually checks,
    or split into two clearly-named tests. Do not just add a new passing test alongside the old
    failing one; the old assertion must be corrected because it currently contradicts Task 1's change.
  - [x] `backend/tests/test_inventory.py`: `test_cook_cannot_list_ingredients` currently asserts 403.
    Rewrite it (rename to `test_cook_can_list_ingredients` or similar) to assert 200.
  - [x] Run both files immediately after Task 1, before writing anything else, to confirm the fix
    lands cleanly: `uv run pytest tests/test_menu.py tests/test_inventory.py -q`.
- [x] **Task 3: Backend tests for the new Cook read access** (AC: 1, 2)
  - [x] `backend/tests/test_menu.py`: a Cook can `GET /api/menu/dishes` (200) and
    `GET /api/menu/dishes/{id}/recipe-ingredients` (200, with content matching what an Admin created).
    A Cook still gets 403 on `POST /api/menu/categories`, `POST /api/menu/dishes`,
    `PATCH /api/menu/dishes/{id}`, `POST/PATCH/DELETE .../recipe-ingredients` (some of these already
    exist as passing tests from Stories 2.2/2.3, verify they still pass rather than assuming; do not
    duplicate them).
  - [x] `backend/tests/test_inventory.py`: a Cook can `GET /api/inventory/ingredients` (200). A Cook
    still gets 403 on `POST /api/inventory/ingredients` (already covered by
    `test_cook_cannot_create_an_ingredient`, verify it still passes).
  - [x] A Warehouse Manager or a Waiter attempting any of the newly Cook-permitted `GET`s: not
    specified by any AC, no test needed either way, `require_role`'s existing behavior (permitted
    Roles only) already covers it structurally.
- [x] **Task 4: `DishesPage.tsx`, the real Cook screen** (AC: 1, 2, 3, 4)
  - [x] Replace the placeholder body of `frontend/src/pages/cook/DishesPage.tsx` entirely (it
    currently only renders an `<h1>`). No routing change needed, `/cook/dishes` already points here
    (`navigationConfig.ts`).
  - [x] Reuse existing hooks only, do not add new ones: `useDishes()`, `useCategories()` (both from
    `services/menuService.ts`), `useIngredients()` (from `services/inventoryService.ts`, already used
    by `DishRecipeEditor.tsx` for the identical id-to-name join this story needs). A per-dish recipe
    needs `useRecipeIngredients(dishId)` called once per Dish, structure this the same way
    `DishRecipeEditor.tsx`/`MenuManagementPage.tsx` structure per-row state: a small `DishRow`
    (or similarly named) sub-component that takes one `Dish` and calls `useRecipeIngredients` itself,
    never call a hook inside a `.map()` callback directly (violates the Rules of Hooks).
  - [x] Group by Category (mirrors `key-cook-dishes.html`'s layout: a heading per Category, dishes
    listed underneath). Use `categories` the same way `MenuManagementPage.tsx`'s `categoryName()`
    helper does, falling back to `#{id}` if a Category can't be resolved (defensive, matches existing
    precedent, should not be reachable in practice since Dishes always reference a real Category).
  - [x] Show, per Dish: name, description, price, prep time, category, availability, and its Recipe
    Ingredient lines by name (join against `useIngredients()`'s result on `ingredient_id`). The
    mockup (`key-cook-dishes.html`) only visually shows name + inline ingredient list + prep time in
    its table, it does not show price or description as separate columns; AC1 requires all of them
    to be present, so add price/description somewhere sensible (e.g. a secondary line under the dish
    name, matching Material Design's list-item secondary-text convention already used elsewhere in
    this codebase) rather than dropping them because the mockup's table doesn't have a column for
    them. Mark an unavailable Dish distinctly (the mockup uses an inline "Unavailable" tag next to
    the name; an MUI `Chip` is the existing precedent for a similar tag, see `MenuManagementPage.tsx`).
  - [x] No create, edit, toggle, or delete control anywhere on this page (AC2). This is the one hard
    rule to double check, since `DishRecipeEditor.tsx` (the Admin equivalent this page borrows
    layout/data-fetching ideas from) is full of exactly those controls, do not copy any of its
    mutation hooks (`useAddRecipeIngredient`, `useUpdateRecipeIngredient`, `useRemoveRecipeIngredient`,
    `useUpdateDishAvailability`) or its editable inputs.
  - [x] Empty state: "No dishes on the menu yet" when `dishes` loads to an empty array (AC3, exact
    copy already used by `MenuManagementPage.tsx` for the identical case, do not invent new wording).
  - [x] Loading/error states: mirror `MenuManagementPage.tsx`'s existing pattern exactly
    (`RowsSkeleton` while loading, an `Alert` with a Retry button using `ApiError`'s message on
    failure). Do not invent a new loading/error UI shape for this screen.
- [x] **Task 5: Frontend tests**
  - [x] New file `frontend/src/pages/cook/DishesPage.test.tsx`, mocking only `fetch` (not the service
    module), matching `MenuManagementPage.test.tsx`'s established pattern (the Story 1.4
    service-mocking lesson: mocking a whole service hides real wiring bugs). Cover:
    - Every Dish renders with its name, description, price, prep time, category name (not a raw
      id), availability, and its Recipe Ingredient lines shown by ingredient **name** (not id).
    - No button, toggle, input, or any other control that could mutate anything is rendered anywhere
      on the page (AC2) — assert on the *absence* of write affordances, not just the presence of
      read-only text.
    - Zero dishes renders "No dishes on the menu yet".
    - A failed dish/category/ingredient fetch renders a retry-capable error state, not a silent blank
      page or a false-empty state (the same silent-failure class Story 2.3's own review caught and
      fixed for the Admin screens, do not reintroduce it here).
  - [x] Full regression: `pnpm test` from `frontend/`, `uv run pytest` from `backend/`.

### Review Findings

Code review 2026-08-13 (three parallel adversarial layers on sonnet: Blind Hunter, Edge Case
Hunter, Acceptance Auditor). The "silent blank page" claim below was reproduced empirically (a
real render against a real query-failure state) before being fixed, not accepted from the
reviewer's reasoning alone.

- [x] [Review][Patch] CONFIRMED: a `useCategories()` or `useIngredients()` failure was completely silent — only `useDishes()`'s loading/error state drove the page [frontend/src/pages/cook/DishesPage.tsx] — Reproduced directly: with `dishes` succeeding and `categories` failing, the page rendered only the "Dishes" heading, no error, no empty-state text, nothing. This directly contradicts AC1/Task 5's explicit "a failed dish/category/ingredient fetch renders a retry-capable error state, not a silent blank page". Fixed by combining `isLoading`/`isError` across all three top-level queries and having Retry refetch all three. Regression test added: `test_cook_can_list_categories_and_read_a_recipe_but_not_edit_it`'s sibling `surfaces a categories-fetch failure as an error, not a silent blank page`.
- [x] [Review][Patch] A Dish whose `category_id` didn't match any loaded Category was silently dropped from the page entirely [frontend/src/pages/cook/DishesPage.tsx] — Grouping only ever iterated the fetched `categories` array and filtered dishes into each; a Dish referencing an unresolvable category never appeared anywhere, with no error and no fallback. This directly contradicted this story's own Task 4 instruction to fall back to `#{id}`, which the first implementation pass didn't actually do despite saying it would. Fixed by grouping off each Dish's own `category_id` instead (a `Set` of ids present in `dishes`), resolving each group's label via `categoryName()` with a `#{id}` fallback. Regression test added.
- [x] [Review][Patch] A failed Ingredient-list fetch silently fell back to raw ingredient ids (`#100`) in a Dish's recipe line, with no indication anything had failed [frontend/src/pages/cook/DishesPage.tsx] — contradicts AC1's "must show the Ingredient's name, not its bare id". Fixed by passing `ingredientsFailed` down to `DishRow` and rendering an explicit warning when it's true, instead of silently degrading to ids. Regression test added.
- [x] [Review][Patch] `InventoryReadDep`'s comment overclaimed field-level scoping that doesn't exist [backend/api/inventory.py] — the comment said Cook access was "not to view stock levels", but the endpoint returns the full `IngredientResponse` including `current_stock`/`min_stock_threshold`; there is no field-level restriction anywhere in this codebase's permission model (Role-level only, per `project-context.md`). Fixed the comment to state this accurately rather than imply a scoping guarantee the code doesn't provide. No behavior change, this project's Role-level-only model already makes the actual behavior correct.
- [x] [Review][Patch] Task 3's "content matching what an Admin created" check for the Cook recipe-read test was missing [backend/tests/test_menu.py] — the test asserted only `status_code == 200` with no recipe ingredient ever added, so the "matches what an Admin created" comparison Task 3 explicitly asked for was never exercised. Fixed by adding a real Recipe Ingredient line via the existing `_add_recipe_ingredient` helper and asserting the Cook's response equals it exactly.
- [x] [Review][Patch] No test confirmed a Category with zero Dishes is actually hidden, despite the render code explicitly filtering for it — Added `hides a Category with zero Dishes rather than showing an empty group`.
- [x] [Review][Dismiss] The shared `_ERROR_DESCRIPTIONS[403]` wording was genericized from naming exact Roles to a generic "not permitted for this action" message — deliberate, and correct: the same dict is now shared across routes with different permitted-Role sets (`MenuReadDep`'s admin+cook vs. `MenuDep`'s admin-only, `InventoryReadDep`'s three Roles vs. `InventoryWriteDep`'s two), so naming one route's specific Roles in a description shared by routes with a different permitted set would be actively misleading, not merely imprecise.
- [x] [Review][Dismiss] One HTTP request per Dish for its recipe lines (unbatched, refetched every mount) scales poorly for a "browse the full catalog" screen — this is an explicit, already-documented scope decision in this story's own spec ("It adds zero new backend endpoints... Do not add... a combined/nested 'dish with recipe' endpoint; reuse the four existing ones exactly as the frontend's `services/menuService.ts` already calls them"). Not a defect this story introduced by omission, a deliberate tradeoff traded for zero new backend surface area.

## Dev Notes

### Architecture compliance

- **NFR-2** / trap 8 (`require_role`'s Role-level-only permission model): this story is the first to
  give a Role read access to a resource it has no write access to at all (`Cook` can `GET` Dishes/
  Categories/Ingredients but has zero mutating permission on any of the three). `require_role`'s
  existing `*roles: UserRole` signature and the by-now-established pattern of a dedicated `*ReadDep`
  separate from a `*WriteDep`/`*Dep` (see `InventoryReadDep`/`InventoryWriteDep` from Story 2.1)
  already supports this with no change to `api/dependencies.py` itself.
- **Design pattern to name**: no new pattern, this story is purely a Role-list widening on two
  already-existing Strategy-style `require_role(...)` guards, plus a read-only frontend view over
  already-existing TanStack Query hooks. Nothing here is a new architectural component.
- **AC1's "never a stale copy" (AD-4-adjacent)**: already satisfied by every hook this story reuses;
  no caching configuration change needed or wanted. Do not add `staleTime`/`gcTime` to make the page
  "feel faster", that would directly violate AC4.

### Existing files this story modifies

- `backend/api/menu.py` — read the whole file before editing (334 lines, all 7 routes). Only
  `list_categories`, `list_dishes`, `list_recipe_ingredients` change their dependency from `MenuDep`
  to a new `MenuReadDep`. The four write routes are untouched.
- `backend/api/inventory.py` — read fully (90 lines). Only `InventoryReadDep`'s Role tuple changes
  (add `UserRole.cook`); `InventoryWriteDep` and `create_ingredient` are untouched.
- `backend/tests/test_menu.py` — contains `test_cook_cannot_list_categories_or_read_a_recipe`
  (currently asserts 403 on two `GET`s that must become 200). Read this specific test before editing
  anything else in the file.
- `backend/tests/test_inventory.py` — contains `test_cook_cannot_list_ingredients` (currently asserts
  403, must become 200).
- `frontend/src/pages/cook/DishesPage.tsx` — currently a 9-line placeholder
  (`<Typography variant="h5" component="h1">Dishes</Typography>`, nothing else). Full read is trivial,
  but do read it, don't assume its current shape.

### New files

- `frontend/src/pages/cook/DishesPage.test.tsx`

No new backend files. No new Alembic migration (no schema change at all this story).

### Project Structure Notes

No deviation from the established five-folder backend layout or the frontend's `pages/{role}/`
convention. This story's frontend work stays inside `pages/cook/`; if a per-dish sub-component is
extracted, prefer keeping it inline in `DishesPage.tsx` or, if it grows large enough to warrant its
own file, place it under `components/menu/` alongside `DishRecipeEditor.tsx` (the existing
convention for menu-domain components), not under `pages/cook/`.

### Testing

- Both backend and frontend suites are touched this story, unlike most of Epic 2 so far (2.1/2.2
  were backend-only).
- Backend: `uv run pytest` from `backend/`. Fix the two existing tests (Task 2) *before* writing any
  new ones, and re-run just those two files to confirm before moving on, per Task 2's own note.
- Frontend: `pnpm test` from `frontend/`. Mock only `fetch`, never the service module wholesale
  (Story 1.4's established lesson, `project-context.md`'s Testing section). `setupTests.ts` already
  provides the explicit `afterEach(cleanup)` this file needs with no extra setup.
- Before trusting the "no write controls exist" assertion in Task 5, verify it can actually fail:
  temporarily add a stray button to the page locally, confirm the test goes red, then remove it.
  This mirrors the project's established "prove a regression test can fail before trusting it" rule
  (Story 1.4's review, restated in Story 2.3's own review for a UI-state test).

### References

- Story source: [Source: _bmad-output/planning-artifacts/epics.md#Story 2.5]
- FR-25 (full text, including the "no authoring controls" consequence and the "always live, never
  stale" guarantee): [Source: _bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md#FR-25]
- UX-DR15 (empty-state copy convention): [Source: _bmad-output/planning-artifacts/epics.md]
- Mockup (layout reference, not a literal field list, see AC1's price/description note above):
  [Source: _bmad-output/planning-artifacts/ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/mockups/key-cook-dishes.html]
- Existing endpoints this story reuses unmodified in shape (only their Role gate changes):
  [Source: backend/api/menu.py], [Source: backend/api/inventory.py]
- Existing frontend hooks this story reuses unmodified: [Source: frontend/src/services/menuService.ts],
  [Source: frontend/src/services/inventoryService.ts]
- The id-to-name join pattern for Recipe Ingredient lines, already solved once for the Admin screen:
  [Source: frontend/src/components/menu/DishRecipeEditor.tsx]
- Loading/error/empty-state precedent to mirror exactly: [Source: frontend/src/pages/admin/MenuManagementPage.tsx]
- `InventoryReadDep`/`InventoryWriteDep` split precedent (Story 2.1), the shape `MenuReadDep` copies:
  [Source: backend/api/inventory.py]
- Project-wide conventions and traps: [Source: _bmad-output/project-context.md]

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (Claude Code, bmad-dev-story workflow)

### Debug Log References

- Caught and corrected a factual error in this story's own AC3 note while implementing it: the
  spec claimed `MenuManagementPage.tsx` already uses "No dishes on the menu yet" verbatim as its
  own empty-state copy. Checked the actual file: it says "No dishes yet." instead (Story 2.3 was
  never required to use UX-DR15's exact wording, only Story 2.5's own AC3 is). Used the correct,
  AC3-mandated string ("No dishes on the menu yet") in `DishesPage.tsx`, not the different string
  actually present in `MenuManagementPage.tsx`.
- Verified the "no write controls" frontend test could actually fail before trusting it, per the
  story's own Testing note: temporarily added a stray `<Button>` to `DishesPage.tsx`, reran the
  test, confirmed it failed (`expected [...] to have a length of +0 but got 1`), then reverted.
- Ran `tests/test_menu.py tests/test_inventory.py` immediately after Task 1's Role-gate widening,
  before writing any new tests, per Task 2's own instruction: both fixed tests passed on the first
  try alongside the full existing suite in those two files (67 passed).

### Completion Notes List

- All 4 acceptance criteria satisfied: AC1 (every Dish shown with name, description, price, prep
  time, category, availability, and recipe lines resolved to Ingredient names, not bare ids), AC2
  (verified by a dedicated test asserting zero buttons/switches/checkboxes/textboxes/comboboxes
  exist anywhere on the page), AC3 (the AC-mandated exact copy, corrected from what the story
  itself had misattributed to `MenuManagementPage.tsx`), AC4 (satisfied by construction, reusing
  the existing hooks' default no-`staleTime` behavior unchanged).
- Zero new backend endpoints or schemas, exactly as scoped: the only backend change is widening
  `MenuReadDep` (new, read-only, `api/menu.py`) and `InventoryReadDep` (existing, `api/inventory.py`)
  to permit `UserRole.cook`, with every write-path dependency (`MenuDep`, `InventoryWriteDep`)
  left untouched.
- Two pre-existing tests were flipped, not just supplemented: `test_menu.py`'s
  `test_cook_cannot_list_categories_or_read_a_recipe` became
  `test_cook_can_list_categories_and_read_a_recipe_but_not_edit_it` (GETs now 200, PATCH still
  403), and `test_inventory.py`'s `test_cook_cannot_list_ingredients` became
  `test_cook_can_list_ingredients`.
- `DishesPage.tsx` follows `MenuManagementPage.tsx`'s established loading/error/empty-state shapes
  exactly, and reuses `DishRecipeEditor.tsx`'s id-to-name join pattern for Recipe Ingredient lines.
  A new `DishRow` sub-component (mirroring `RecipeLineRow`'s per-item shape) calls
  `useRecipeIngredients(dish.id)` once per Dish, since a hook cannot be called inside a parent's
  `.map()` callback directly.
- 4 new backend tests (2 fixed + 2 added) and 6 new frontend tests. Full regression: backend 213
  passed (up from 191), frontend 72 passed (up from 66), `tsc -b` clean.

### File List

**Added**

- `frontend/src/pages/cook/DishesPage.test.tsx`

**Modified**

- `backend/api/menu.py` (added `MenuReadDep`; `list_categories`/`list_dishes`/
  `list_recipe_ingredients` now depend on it instead of `MenuDep`; generalized the shared
  `_ERROR_DESCRIPTIONS[403]` wording)
- `backend/api/inventory.py` (`InventoryReadDep` now also permits `UserRole.cook`; updated its
  comment and the `list_ingredients` docstring; generalized `_ERROR_DESCRIPTIONS[403]` wording)
- `backend/tests/test_menu.py` (flipped `test_cook_cannot_list_categories_or_read_a_recipe`;
  added `test_cook_can_list_dishes_but_not_create_one`)
- `backend/tests/test_inventory.py` (flipped `test_cook_cannot_list_ingredients`)
- `frontend/src/pages/cook/DishesPage.tsx` (full implementation, replacing the Story 1.0/1.4
  placeholder)

**Confirmed unchanged**: `backend/api/dependencies.py` (`require_role`'s existing `*roles`
signature needed no change), `backend/services/menu_service.py`, `backend/services/inventory_service.py`
(both already return exactly the data this story needs), `backend/data_models/` (no schema
change), `frontend/src/services/menuService.ts`, `frontend/src/services/inventoryService.ts`
(both reused as-is), `frontend/src/router.tsx`, `frontend/src/components/shell/navigationConfig.ts`
(`/cook/dishes` was already wired to `DishesPage`), no new Alembic revision, no new dependency on
either side.

## Change Log

| Date | Change |
|---|---|
| 2026-08-13 | Added `MenuReadDep` (`backend/api/menu.py`) permitting `admin, cook` on the three menu list/read routes; every write route stays on the existing `MenuDep` (admin-only), unchanged. |
| 2026-08-13 | Widened `InventoryReadDep` (`backend/api/inventory.py`) to also permit `UserRole.cook`, so a Cook can resolve Ingredient names when rendering a Dish's recipe; `InventoryWriteDep` untouched. |
| 2026-08-13 | Flipped two pre-existing tests that had asserted 403 for a Cook on routes this story makes 200: `test_menu.py`'s categories/recipe-read test and `test_inventory.py`'s ingredient-list test. Added one new test confirming a Cook can list Dishes but not create one. |
| 2026-08-13 | Implemented `frontend/src/pages/cook/DishesPage.tsx`, replacing its Story 1.0/1.4 placeholder: every Dish grouped by Category, showing name/description/price/prep time/availability and its recipe by Ingredient name (joined via `useIngredients()`), strictly read-only, matching `MenuManagementPage.tsx`'s loading/error/empty-state shapes. Corrected the story's own AC3 note along the way: `MenuManagementPage.tsx` does not actually use the UX-DR15 exact copy, this page uses the AC-mandated string directly instead. |
| 2026-08-13 | Added `frontend/src/pages/cook/DishesPage.test.tsx`: 6 tests covering full-field rendering, ingredient-name resolution, the unavailable-dish marker, the empty state, a failed dish-list fetch, and a failed per-dish recipe fetch. The "no write controls" assertion was verified to actually fail before being trusted (a stray button was added, the test went red, then it was reverted). |
| 2026-08-13 | Full regression: backend 213 passed (up from 191), frontend 72 passed (up from 66), `tsc -b` clean, reproducible on a fresh database. |
| 2026-08-13 | Code review (sonnet, three parallel layers): confirmed and fixed a real "silent blank page" bug where a `useCategories()`/`useIngredients()` failure was invisible (only `useDishes()`'s error state drove the page), reproduced by rendering the page against a real query-failure state before and after the fix. Fixed a Dish whose Category couldn't be resolved being silently dropped instead of falling back to `#{id}` as this story's own Task 4 had specified but the first pass hadn't actually implemented. Fixed a failed Ingredient-list fetch silently degrading to raw ids with no warning. Corrected an overclaiming comment on `InventoryReadDep`. Closed two test-coverage gaps (recipe content-matching, empty-category hiding). 2 findings dismissed as deliberate, already-documented tradeoffs. Full regression after patching: backend 213 passed, frontend 76 passed (up from 72). |
