---
baseline_commit: 01b85e53e61a95304f3ab6e0bf5e6fa9155fd1ab
epic: 2
story: 6
---

# Story 2.6: Create Menu Categories, Dishes, and Ingredients from the Admin UI

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Admin (and Warehouse Manager for Ingredients),
I want to create Menu Categories, Dishes, and Ingredients from their own screens,
so that menu and inventory setup doesn't require calling the API directly.

## Scope note (read first)

**Frontend-only for both halves. Zero backend changes.** Stories 2.2 and 2.1 built and tested every
endpoint this story needs (`POST /api/menu/categories`, `POST /api/menu/dishes`,
`POST /api/inventory/ingredients`); each shipped backend-only, deliberately deferring its create
form. `MenuManagementPage.tsx`'s own code comment ("Category/Dish creation forms are deliberately
out of scope... ships in a later story") and `IngredientsPage.tsx`'s bare placeholder are the two
gaps this story closes. Do not touch any backend file.

**Dish half extends an existing screen; Ingredient half replaces a placeholder.**
`frontend/src/pages/admin/MenuManagementPage.tsx` (Story 2.3) already lists Dishes with a per-dish
recipe editor — this story adds the create form on top, it does not rebuild the page.
`frontend/src/pages/warehouse/IngredientsPage.tsx` is still the one-line placeholder from Story 1.4
— this story writes its real content for the first time (list + create form).

**`useIngredients()` and the `Ingredient` type already exist** (`frontend/src/services/
inventoryService.ts`, `frontend/src/types/inventory.ts`) — added in Story 2.5 for the Cook's recipe
view. Only a create mutation and its payload type are new. Do not duplicate the query hook or the
type.

**No dialog. Follow the inline-form convention this codebase's shipped creation flow uses**
(`TablesSetupPage`'s Add-table form, Story 2.4 — the only merged creation-form precedent as of
this story's baseline commit; Story 1.6 also builds a Users screen along similar lines but is not
yet merged and must not be relied on as a present pattern): an always-visible form above the list,
plain `useState` per field, no `react-hook-form`. The UX mock (`key-menu-management.html`) shows
"+ New dish" as a button, which could be read as "opens a dialog" — it is not. This codebase has
never introduced a modal, and this story should not be the first to invent one just because a
static mockup shows a button; render the same button, but have it submit an always-visible form.

**Category creation is nested inside the dish form, not a second top-level button.** The mock has
no "+ New category" control anywhere — Categories only appear as section labels grouping the dish
table. Since a Dish requires a valid `category_id` and there is no AC or mockup element proposing a
standalone category screen, the dish form's Category `Select` gets a small "+ New category"
in-place reveal (a text field + Confirm/Cancel appearing where the Select is). Model this on
`TablesSetupPage`'s `TableListRow`: a local boolean (`isEditing` there; call it e.g.
`isCreatingCategory` here) swaps a control for an editable field in place, resyncing/collapsing on
success or cancel — the same component-local reveal shape, just triggered by a button instead of
by clicking existing data.

**Fix required alongside this story's own work, not optional polish:** `MenuManagementPage.tsx`
currently destructures only `useDishes()`'s `isLoading`/`isError` (line 33) and reads
`useCategories()` for data only (line 34), never checking its own loading/error state. This is the
exact "silent blank page" bug Story 2.5's review found and fixed in `DishesPage` — `project-context.
md`'s own checklist states it as a hard rule ("A page driven by more than one independent query
must combine loading/error across all of them"). It was never backported to this page. This story's
new dish-creation form needs Categories loaded to populate its picker, so shipping the create form
without fixing this leaves a real, newly-relevant gap: a Categories fetch failure would silently
leave the "+ New dish" form's Category `Select` empty with no explanation anywhere on the page. Fix
it as part of Task 1 below — this is required for the feature to work end-to-end, not a
nice-to-have.

## Acceptance Criteria

**AC1 — Create a Dish**
Given the Menu Management screen, when an Admin submits the "+ New dish" form (name, description,
price, category, prep time), then a form collects those fields and creates the Dish via the
existing `POST /api/menu/dishes` endpoint, starting unavailable per AD-8 (FR-22).

**AC2 — Create a Menu Category inline**
Given an Admin creating a Dish needs a Menu Category that doesn't exist yet, when they use the
form's category control, then they can create a new Menu Category via the existing
`POST /api/menu/categories` endpoint without leaving the flow (FR-22).

**AC3 — Duplicate/invalid data rejected inline**
Given a duplicate category name, or a dish submitted with invalid data, when the form is submitted,
then it is rejected inline, matching the existing 409/422 contract (FR-22, UX-DR17).

**AC4 — Create an Ingredient**
Given the Ingredients screen, when a Warehouse Manager or Admin clicks "Add ingredient", then a
form collects name, unit of measure, minimum stock threshold, and optional initial stock, and
creates the Ingredient via the existing `POST /api/inventory/ingredients` endpoint (FR-16).

**AC5 — Duplicate ingredient name rejected**
Given a duplicate ingredient name, when creation is attempted, then it is rejected inline (FR-16,
UX-DR17).

**AC6 — Empty state replaces the placeholder**
Given no ingredients exist yet, when the Ingredients screen loads, then it shows "No ingredients
recorded yet" instead of the current blank placeholder (UX-DR15).

## Tasks / Subtasks

- [x] **Task 1: `menuService.ts` additions + the pre-existing loading/error fix** (AC: 1, 2, 3)
  - [x] In `frontend/src/services/menuService.ts`, add two payload types **locally in the service
    file**, matching `tableService.ts`'s established precedent (`CreateTablePayload`/
    `UpdateTablePayload` are private interfaces in that file, not exported from `types/table.ts`) —
    do not add these to `types/menu.ts`, which holds only response-shaped types mirroring backend
    Pydantic *response* models, a distinction this codebase has kept consistently so far:
    ```ts
    export interface CreateCategoryPayload {
      name: string;
    }
    export interface CreateDishPayload {
      name: string;
      description?: string | null;
      price: string;              // Decimal-as-string, matching Dish.price's existing convention
      category_id: number;
      prep_time_minutes?: number | null;
    }
    ```
  - [x] Add `useCreateCategory()` and `useCreateDish()`, copying `useUpdateDishAvailability`'s
    shape exactly: `apiRequest` only, `onSuccess` invalidates `CATEGORIES_QUERY_KEY` /
    `DISHES_QUERY_KEY` respectively (both already-defined module constants — reuse them, do not
    redeclare). Nothing here can be rejected because of stale client data (no concurrent-edit race
    on a *create*), so `onSuccess` is correct, not `onSettled` (that distinction is for mutations
    that can 409 against a caller's stale copy, per `project-context.md`).
  - [x] Fix `MenuManagementPage.tsx`'s pre-existing gap (see Scope note): destructure
    `isLoading`/`isError` from `useCategories()` too, OR both queries' `isLoading`/`isError`
    together (`isLoading = dishesLoading || categoriesLoading`, same for `isError`), and make
    Retry refetch both. Matches `DishesPage`'s fix from Story 2.5 exactly — that file is the
    precedent to copy, not a hypothetical.

- [x] **Task 2: Dish/Category creation UI on `MenuManagementPage.tsx`** (AC: 1, 2, 3)
  - [x] Add an always-visible "+ New dish" form above the existing dish list (`Typography
    variant="h5"` heading stays; form goes below it, list below that — same vertical order
    `TablesSetupPage` uses). Fields: name (`TextField`), description (`TextField`, optional),
    price (`TextField`, numeric — parse explicitly with a helper mirroring
    `TablesSetupPage.tsx`'s `parsePositiveInteger`, adapted for a decimal: reject non-numeric,
    reject `<= 0`, never let `Number("")`/`Number("abc")` reach `JSON.stringify` as `null`/`NaN`),
    category (`Select`, populated from `useCategories()`, plus the inline "+ New category" reveal
    described below), prep time (`TextField`, optional, numeric, `>= 0`).
  - [x] **Inline category creation**: next to/inside the category `Select`, a small link/button
    "+ New category" reveals a `TextField` + Confirm/Cancel in place (component-local boolean
    state, same reveal shape as `TablesSetupPage`'s `TableListRow` uses for `isEditing`). On
    Confirm, call `useCreateCategory()`;
    on success, close the reveal and set the dish form's `category_id` to the newly created
    Category's `id` so the Admin doesn't have to reselect it. On failure (409 duplicate name),
    show `ApiError.message` inline in the reveal, do not close it.
  - [x] Submitting "+ New dish" calls `useCreateDish()`. On success, clear the form. On failure
    (404 nonexistent category — unreachable via the UI's own picker but still a valid server
    response; 422 validation), render `ApiError.message` inline via an `Alert`, matching
    `TablesSetupPage`'s `createMutation.isError` pattern exactly. Do not re-word any backend
    string (UX-DR17).
  - [x] Update the file's own top-of-component doc comment, which currently states creation forms
    are "deliberately out of scope" — that sentence describes Story 2.3's scope, not this file's
    current state, and must not survive unedited.

- [x] **Task 3: `inventoryService.ts` — add the create mutation** (AC: 4, 5)
  - [x] Promote the inline `["inventory", "ingredients"]` array literal in `useIngredients()`'s
    `queryKey` to a module-level `INGREDIENTS_QUERY_KEY` constant (matching every other service
    file's convention — `menuService.ts`/`tableService.ts` both do this; `inventoryService.ts` is
    currently the only one that doesn't, because it has only ever had one hook). Reuse the constant
    in both the existing query and the new mutation's invalidation.
  - [x] Add the payload type **locally in `inventoryService.ts`**, same rule as Task 1
    (`tableService.ts`'s precedent: request-payload types are private to the service file, only
    response-shaped types live in `types/`) — do not add this to `types/inventory.ts`:
    ```ts
    interface CreateIngredientPayload {
      name: string;
      unit: Unit;
      min_stock_threshold: string;   // Decimal-as-string, matching current_stock's existing convention
      current_stock?: string;        // optional; server defaults to "0" if omitted (FR-16)
    }
    ```
  - [x] Add `useCreateIngredient()` to `inventoryService.ts`: `POST /api/inventory/ingredients`,
    `onSuccess` invalidates `INGREDIENTS_QUERY_KEY`.

- [x] **Task 4: `IngredientsPage.tsx` — real content, replacing the placeholder** (AC: 4, 5, 6)
  - [x] Header: `<h1>Ingredients</h1>` plus a subtitle `"{n} ingredients"` (no threshold/shortage
    count — that needs the comparison logic Story 4.3 owns, do not invent it here).
  - [x] Always-visible "Add ingredient" form: name (`TextField`), unit (`Select` over the three
    `Unit` values `kg`/`liter`/`piece`), minimum stock threshold (`TextField`, numeric, `>= 0`,
    parsed explicitly per the same non-null-on-`NaN` reasoning as Task 2's price field), current
    stock (`TextField`, numeric, optional, `>= 0` — omit from the payload entirely if left blank,
    do not send `0` or `null` for "not specified", the backend already defaults it).
  - [x] Dense-row list (`Table`/`size="small"` theme default) with columns Name / Unit / Current
    stock / Threshold, populated via the existing `useIngredients()`. **Do not add** shortage
    sorting, red highlighting, a Status column, or click-to-detail — `key-ingredients.html` has
    all of these, but they need the below-threshold comparison Story 4.3 owns; this list proves
    creation worked, nothing more (see Scope note in `epics.md`).
  - [x] Loading/error/empty triad, same wording pattern as every other domain screen: `isLoading`
    → `RowsSkeleton`; `isError` → `Alert` + Retry calling `refetch()`; `ingredients?.length === 0`
    → `Typography` reading **"No ingredients recorded yet"** (AC6's exact required copy — note
    this differs from `TablesSetupPage`'s "No tables configured yet.", each screen has its own
    copy per its own AC, do not genericize).
  - [x] Submitting "Add ingredient" calls `useCreateIngredient()`. On success, clear the form. On
    failure (409 duplicate name, exact string `"That ingredient name already exists"`; 422), render
    inline via `Alert`, same pattern as Task 2.

- [x] **Task 5: Tests** (AC: all)
  - [x] `MenuManagementPage.test.tsx` (extend the existing file, do not replace it — its current
    recipe-editor tests must keep passing): add tests for dish creation success, the exact 409
    string on duplicate category name, the inline "+ New category" flow (create, then the new
    category is selected in the dish form), and a categories-fetch-failure test proving the fixed
    isLoading/isError-combining actually renders an error (this is the regression test for Task
    1's fix — write it, then temporarily revert the fix and confirm it fails, before trusting it;
    this is the exact verification step Story 2.5's own review lesson calls for).
  - [x] `IngredientsPage.test.tsx` (new file, mirrors `TablesSetupPage.test.tsx`'s conventions:
    mock only `fetch`, real `QueryClient`, `jsonResponse` helper). Required coverage: list renders;
    create succeeds and clears the form; duplicate-name 409 renders the exact backend string and
    preserves the form; empty state shows "No ingredients recorded yet"; error+Retry.
  - [x] Mutation-test the new tests before trusting them (Story 1.6's review lesson, now a standing
    practice, not optional): pick at least the duplicate-name and empty-state assertions, delete
    the behavior they claim to pin, confirm the test actually fails, then restore.

- [x] **Task 6: Docs** (AC: n/a — required for story completion, not dev-story)
  - [x] Update `_bmad-output/project-context.md`: `IngredientsPage` moves from placeholder to real
    (fifth domain screen); `MenuManagementPage` gains create forms; suite counts; a dated patch
    entry noting the retroactive `isLoading`/`isError` fix and why it was in this story's scope.
  - [x] `sprint-status.yaml` and `epics.md` need no further edits — already registered as Story 2.6.

### Review Findings

- [x] [Review][Decision] **RESOLVED (Ofek's call, 2026-08-13): widen Admin's nav/routing.** AC4 promises Admin access to the Ingredients screen, but Admin could not reach it at all — `_bmad-output/implementation-artifacts/2-6-create-menu-categories-dishes-and-ingredients-from-the-admin-ui.md` AC4 says "when a Warehouse Manager **or Admin** clicks 'Add ingredient'", and the backend's `InventoryWriteDep` permits both roles, but `frontend/src/components/shell/RequireAuth.tsx` gates every route on `ROLE_PATH_PREFIX[user.role]` (admin → `/admin`), and `ROLE_NAV_ITEMS.admin` has no Ingredients entry — an Admin navigating to `/warehouse/ingredients` is redirected away. This routing restriction predates this story (Story 1.4) and this story's own Dev Notes said "do not touch the router." The AC's wording and the pre-existing routing architecture conflict; fixing it means widening Admin's nav/routing, which needs a decision on intent, not a code guess. **Fix applied:** `navigationConfig.ts` gained an `Ingredients` entry under `admin` plus a new `canRoleVisit(role, pathname)` helper (own prefix OR any surface that Role's own nav links to), and `RequireAuth.tsx` now calls it instead of comparing prefixes directly. Deriving reachability from the nav config means a nav entry a Role cannot open, and a reachable surface with no nav link, are both unrepresentable. Two `router.test.tsx` tests pin it (Admin reaches Ingredients; a Waiter is still bounced), and the helper was mutation-tested.
- [x] [Review][Patch] canSubmitDish doesn't account for the open "+ New category" reveal, and pressing Enter in that field submits the dish form instead of confirming the category [frontend/src/pages/admin/MenuManagementPage.tsx:130,137,228]
- [x] [Review][Patch] IngredientsPage's handleCreate guard is weaker than canSubmit (missing name/isPending checks), same class of latent bug as MenuManagementPage's [frontend/src/pages/warehouse/IngredientsPage.tsx:96]
- [x] [Review][Patch] Inline category auto-select can put the Category picker into an out-of-range MUI state before the invalidated query refetches [frontend/src/services/menuService.ts, useCreateCategory]
- [x] [Review][Patch] CreateCategoryPayload/CreateDishPayload are exported, contradicting Task 1's "private interfaces" instruction and this story's own Completion Notes [frontend/src/services/menuService.ts:31,35]
- [x] [Review][Patch] The dish creation form renders unconditionally during a categories loading/error state, leaving the Category picker empty with no visible reason [frontend/src/pages/admin/MenuManagementPage.tsx:199]
- [x] [Review][Patch] No maxLength on the three new name fields (Dish 100, Category 50, Ingredient 100), though every backend column is bounded [frontend/src/pages/admin/MenuManagementPage.tsx, frontend/src/pages/warehouse/IngredientsPage.tsx]
- [x] [Review][Patch] IngredientsPage's subtitle reads "0 ingredients" during loading/error and "1 ingredients" for a single row [frontend/src/pages/warehouse/IngredientsPage.tsx:120]
- [x] [Review][Patch] The "clears the form" tests only assert one field resets, not all of them [frontend/src/pages/admin/MenuManagementPage.test.tsx, frontend/src/pages/warehouse/IngredientsPage.test.tsx]
- [x] [Review][Patch] AC3's dish-submission-rejection path (createDishMutation.isError Alert) has zero test coverage [frontend/src/pages/admin/MenuManagementPage.test.tsx]
- [x] [Review][Defer] Client-side numeric parsers only enforce sign, not the backend's digit/decimal-place/int4 bounds (price, prep_time_minutes, threshold, current_stock) — deferred, low risk: UX-DR17's inline Alert already surfaces the backend's own 422 message verbatim [frontend/src/pages/admin/MenuManagementPage.tsx, frontend/src/pages/warehouse/IngredientsPage.tsx] — deferred, pre-existing class of gap, self-mitigated by the existing error-surfacing contract
- [x] [Review][Defer] createDishMutation/createMutation errors are never reset while the user edits fields after a failed submit, only on the next submit attempt — deferred, pre-existing UX rough edge, self-heals on resubmit [frontend/src/pages/admin/MenuManagementPage.tsx, frontend/src/pages/warehouse/IngredientsPage.tsx] — deferred, low severity, self-heals
- [x] [Review][Defer] errorMessage()/GENERIC_ERROR_MESSAGE is now duplicated across four page files, and UNIT_OPTIONS duplicates DishRecipeEditor's UNITS constant — deferred, matches this codebase's existing per-screen duplication precedent, extraction is out of this story's scope [frontend/src/pages/admin/MenuManagementPage.tsx, frontend/src/pages/warehouse/IngredientsPage.tsx] — deferred, matches existing precedent

## Dev Notes

### Architecture compliance

- **AD-8** (Dish availability gated on non-empty recipe): `CreateDishRequest` has no
  `is_available` field at all — the backend forces it `false` unconditionally. Nothing for this
  story to enforce client-side; do not add an availability toggle to the create form, one does not
  exist in the create flow by design (Story 2.3's `DishRecipeEditor`, reached after creation, owns
  toggling availability once a recipe exists).
- **UX-DR17** (inline rejection copy): every error this story surfaces must be the backend's
  literal `detail` string via `ApiError.message`, never re-worded. This is what makes AC3/AC5's
  "matching the existing 409/422 contract" wording testable.
- **UX-DR15** (empty-state copy): AC6's string is exact — "No ingredients recorded yet" — verified
  against `epics.md`'s own wording, not paraphrased.
- The checklist item this story must not violate a second time: **"Never diff a form against
  cached data to decide what to send."** Not directly at risk here (these are all *creates*, not
  edits — there is no cached row to diff against), but if the "+ New category" reveal's
  auto-select-after-create logic is ever extended to also patch the dish form's other fields,
  do not derive that patch by comparing to a cached Category list; use the mutation's own response.

### Backend contract (existing, unchanged)

| Method | Path | Role | Body | Success | Errors |
|---|---|---|---|---|---|
| POST | `/api/menu/categories` | admin only (`MenuDep`) | `CreateCategoryRequest` | 201 `CategoryResponse` | 409 `"That category name already exists"` |
| POST | `/api/menu/dishes` | admin only (`MenuDep`) | `CreateDishRequest` | 201 `DishResponse` | 404 `"Category not found"`; 422 validation |
| POST | `/api/inventory/ingredients` | admin, warehouse_manager (`InventoryWriteDep`) | `CreateIngredientRequest` | 201 `IngredientResponse` | 409 `"That ingredient name already exists"`; 422 validation |

Field bounds (`backend/data_models/menu.py`, `backend/data_models/recipe.py`):
```python
# CreateCategoryRequest
name: str = Field(min_length=1, max_length=50)        # stripped, non-blank

# CreateDishRequest — never carries is_available
name: str = Field(min_length=1, max_length=100)        # stripped, non-blank
description: str | None = None
price: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
category_id: int = Field(gt=0, le=2_147_483_647)
prep_time_minutes: int | None = Field(default=None, ge=0, le=2_147_483_647)

# CreateIngredientRequest
name: str = Field(min_length=1, max_length=100)         # stripped, non-blank
unit: Unit                                              # "kg" | "liter" | "piece"
min_stock_threshold: Decimal = Field(ge=0, max_digits=10, decimal_places=3)
current_stock: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=3)
```
**Do not assume both names are checked the same way.** Ingredient name uniqueness is
case-insensitive (functional `lower()` index, same pattern as Story 1.3's username check), but
Category name uniqueness is **case-sensitive only** — `MenuService.create_category`'s own
docstring states this explicitly as a deliberate choice, and no AC or UX doc asks for
case-insensitive category matching. A test asserting "Pizza" and "pizza" both get rejected as
duplicates would be correct for Ingredients and wrong for Categories.

### Project Structure Notes

Files touched, all frontend:
- `frontend/src/pages/admin/MenuManagementPage.tsx` — **UPDATE**, adds the create forms and fixes
  the pre-existing loading/error gap; the existing list + recipe-editor behavior must not regress.
- `frontend/src/pages/admin/MenuManagementPage.test.tsx` — **UPDATE**, extend, do not replace.
- `frontend/src/services/menuService.ts` — **UPDATE**, additive (`useCreateCategory`,
  `useCreateDish`, plus their locally-scoped payload interfaces).
- `frontend/src/types/menu.ts` — **untouched**. It holds only response-shaped types; the two new
  request payloads live in `menuService.ts` itself, per `tableService.ts`'s precedent.
- `frontend/src/pages/warehouse/IngredientsPage.tsx` — **UPDATE**, replaces the entire placeholder
  body. Route (`/warehouse/ingredients` or equivalent) already exists from Story 1.4; do not touch
  the router.
- `frontend/src/pages/warehouse/IngredientsPage.test.tsx` — **NEW**.
- `frontend/src/services/inventoryService.ts` — **UPDATE**, additive (`useCreateIngredient` plus
  its locally-scoped payload interface, promotes the query key to a named constant).
- `frontend/src/types/inventory.ts` — **untouched**, same reasoning as `types/menu.ts` above.

No backend file, no Alembic migration, no `container.py`/`main.py` wiring change — everything on
that side already shipped in Stories 2.1 and 2.2.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 2.6`] — this story's AC source
- [Source: `_bmad-output/implementation-artifacts/2-1-create-and-manage-ingredients.md`,
  `2-2-manage-menu-categories-and-dishes.md`] — the backend both halves wire up; each explicitly
  deferred this UI
- [Source: `_bmad-output/implementation-artifacts/2-5-cook-browses-the-dish-catalog.md`] — where
  `useIngredients()`/`Ingredient` were added, and where the isLoading/isError-combining rule this
  story must also apply to `MenuManagementPage` was established
- [Source: `frontend/src/pages/admin/TablesSetupPage.tsx`,
  `frontend/src/services/tableService.ts`] — the always-visible inline-create-form pattern and the
  `TableListRow`-shaped local-boolean reveal this story's "+ New category" control copies
- [Source: `_bmad-output/project-context.md`, "The shape every new domain screen should copy"] —
  the standing rules this story must follow: never diff a form against cached data (create flows
  have no cached row to diff against, but the "+ New category" auto-select-after-create must still
  use the mutation's own response, not a re-derived comparison), every mutation renders its own
  `isError`, and a page driven by more than one query must combine loading/error across all of
  them (the rule Task 1's `MenuManagementPage` fix applies)
- [Source: `backend/api/menu.py`, `backend/api/inventory.py`,
  `backend/data_models/menu.py`, `backend/data_models/recipe.py`] — the unchanged backend contract
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../mockups/key-menu-management.html`,
  `key-ingredients.html`] — AC1/AC4's visual targets; confirmed no dedicated "+ New category"
  control exists in either mock

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5

### Debug Log References

- `frontend`: `tsc --noEmit` clean, `vite build` clean, full `vitest run` — 13 files, 85 tests passed
  (76 pre-existing + 9 new: 4 in `MenuManagementPage.test.tsx`, 5 in the new `IngredientsPage.test.tsx`)
- No backend changes; backend suite untouched at 213 tests

### Completion Notes List

- Zero backend changes, as scoped: all three endpoints (`POST /api/menu/categories`,
  `POST /api/menu/dishes`, `POST /api/inventory/ingredients`) already existed from Stories 2.1/2.2.
- `CreateCategoryPayload`/`CreateDishPayload`/`CreateIngredientPayload` all live as private interfaces
  inside their service files, matching `tableService.ts`'s established precedent, not in `types/`.
- No dialog anywhere: the dish form's Category picker swaps to an inline text field + Confirm/Cancel
  on "+ New category" (component-local boolean, the same reveal shape `TablesSetupPage`'s
  `TableListRow` uses for row editing). On success it selects the new Category using the mutation's
  own response, never a re-derived comparison against cached data.
- Fixed `MenuManagementPage.tsx`'s pre-existing gap alongside Task 1 (required for the new
  dish-creation form to fail loudly, not optional polish): `isLoading`/`isError` are now OR'd across
  `useDishes()` and `useCategories()`, and Retry refetches both, mirroring `DishesPage`'s Story 2.5 fix.
- `IngredientsPage.tsx` replaced entirely: header + subtitle, "Add ingredient" form, dense-row list
  (Name/Unit/Current stock/Threshold), and the loading/error/empty triad with AC6's exact copy "No
  ingredients recorded yet". Deliberately no shortage sorting/highlighting/Status column/detail-drill,
  that scope stays with Epic 4's Story 4.3.
- Mutation-tested the Task 1 regression test (reverted the OR-fix, confirmed the combined-query test
  fails, restored) and the `IngredientsPage.test.tsx` duplicate-name/empty-state assertions (each
  behavior temporarily broken, confirmed the corresponding test fails, restored), per Story 1.6's
  now-standing practice.
- Updated `_bmad-output/project-context.md` (current-state tree, "the shape every new domain screen
  should copy" context, the resolved Domain-rules gap note, a new dated patch entry, suite counts) and
  `_bmad-output/implementation-artifacts/deferred-work.md` (marked the Story 2.5 deferred entry
  RESOLVED). No `sprint-status.yaml`/`epics.md` edits needed, already registered.

### File List

- `frontend/src/services/menuService.ts` — UPDATE (additive: `CreateCategoryPayload`,
  `CreateDishPayload`, `useCreateCategory`, `useCreateDish`)
- `frontend/src/services/inventoryService.ts` — UPDATE (additive: `CreateIngredientPayload`,
  `useCreateIngredient`; promoted `INGREDIENTS_QUERY_KEY` to a module constant)
- `frontend/src/pages/admin/MenuManagementPage.tsx` — UPDATE (dish/category creation forms, the
  combined loading/error fix, updated top-of-component doc comment)
- `frontend/src/pages/admin/MenuManagementPage.test.tsx` — UPDATE (4 new tests, existing tests
  untouched)
- `frontend/src/pages/warehouse/IngredientsPage.tsx` — UPDATE (placeholder replaced with real content)
- `frontend/src/pages/warehouse/IngredientsPage.test.tsx` — NEW (7 tests after review patches)
- `frontend/src/components/shell/navigationConfig.ts` — UPDATE (review patch: Admin gains an
  Ingredients nav entry; new `canRoleVisit` helper derives reachability from the nav config)
- `frontend/src/components/shell/RequireAuth.tsx` — UPDATE (review patch: calls `canRoleVisit`
  instead of comparing `ROLE_PATH_PREFIX` directly)
- `frontend/src/router.test.tsx` — UPDATE (review patch: 2 tests pinning the Admin cross-prefix grant)
- `_bmad-output/project-context.md` — UPDATE (docs)
- `_bmad-output/implementation-artifacts/deferred-work.md` — UPDATE (docs)

## Change Log

| Date | Change |
|---|---|
| 2026-08-13 | Added `useCreateCategory`/`useCreateDish` to `menuService.ts` and `useCreateIngredient` to `inventoryService.ts`, all three reusing the existing backend endpoints unchanged. |
| 2026-08-13 | Built the always-visible "+ New dish" form on `MenuManagementPage.tsx` with an inline "+ New category" reveal on its Category picker; no dialog, matching `TablesSetupPage`'s inline-form/local-boolean-reveal precedent. |
| 2026-08-13 | Fixed `MenuManagementPage.tsx`'s pre-existing gap alongside Task 1: `isLoading`/`isError` are now OR'd across `useDishes()` and `useCategories()`, matching `DishesPage`'s Story 2.5 fix; required for the new create form to fail loudly on a Categories-fetch failure rather than silently. |
| 2026-08-13 | Replaced `IngredientsPage.tsx`'s one-line placeholder with real content: an "Add ingredient" form and a dense-row list, deliberately without shortage sorting/highlighting/a Status column/detail-drill (Epic 4's Story 4.3 scope). |
| 2026-08-13 | Added 4 tests to `MenuManagementPage.test.tsx` (dish creation, duplicate-category 409, inline category creation and auto-select, the combined-query regression test) and a new `IngredientsPage.test.tsx` (5 tests: list, empty state, create, duplicate-name 409, error+retry). The combined-query regression test and the duplicate-name/empty-state assertions were each mutation-tested (temporarily broken, confirmed red, restored) before being trusted. |
| 2026-08-13 | Updated `project-context.md` (current-state tree, resolved the Story 2.5 Domain-rules gap note, new dated patch entry, suite counts) and marked the corresponding `deferred-work.md` entry RESOLVED. |
| 2026-08-13 | Full regression: backend 213 passed (unchanged, zero backend changes), frontend 85 passed (up from 76), `tsc --noEmit` clean, `vite build` clean. |
| 2026-08-13 | **Code review** (3 parallel adversarial layers): 1 decision-needed, 9 patches, 3 deferred. Decision resolved by Ofek — widen Admin's nav/routing so AC4's "or Admin" half is actually reachable. |
| 2026-08-13 | Review patch: `navigationConfig.ts` gained an Admin `Ingredients` nav entry and a `canRoleVisit(role, pathname)` helper (own prefix OR any surface that Role's nav links to); `RequireAuth.tsx` now calls it. Reachability is derived from the nav config, so a nav entry a Role cannot open, and a reachable surface with no nav link, are both unrepresentable. Mutation-tested. |
| 2026-08-13 | Review patch: `canSubmitDish` now also requires the "+ New category" reveal to be closed, and the category field's Enter key confirms the category instead of falling through to the dish form's implicit submit (which would have created the Dish and discarded the typed category). Mutation-tested. |
| 2026-08-13 | Review patch: both submit handlers now re-check their full submit predicate rather than a subset — a disabled button is not authoritative, Enter submits regardless, and the omitted checks were exactly the ones guarding a blank name and a duplicate in-flight request. |
| 2026-08-13 | Review patch: `useCreateCategory` seeds the created Category into the cached list before invalidating, so the caller that immediately selects it never holds an id with no matching option (blank picker + MUI out-of-range warning) while the refetch is in flight. |
| 2026-08-13 | Review patch: un-exported `CreateCategoryPayload`/`CreateDishPayload`, matching `tableService.ts`'s precedent and this story's own Task 1 instruction. |
| 2026-08-13 | Review patch: the dish create form is withheld until both queries settle, so a categories failure no longer renders an empty Category picker and a permanently disabled submit with no visible reason. |
| 2026-08-13 | Review patch: `maxLength` added to all three new name fields (Dish 100, Category 50, Ingredient 100), matching the backend's column bounds. |
| 2026-08-13 | Review patch: `IngredientsPage`'s subtitle renders only once the list is known (no more "0 ingredients" beside a load error) and pluralizes correctly. |
| 2026-08-13 | Review patch: both "clears the form" tests now assert every field resets, not just the first; added an AC3 dish-rejection test and an Enter-confirms-category test; `IngredientsPage`'s Retry test now clicks Retry and asserts a refetch rather than only asserting the button exists. |
| 2026-08-13 | Post-review regression: frontend 90 passed (up from 85), `tsc --noEmit` clean, `vite build` clean. Backend untouched at 213. |
