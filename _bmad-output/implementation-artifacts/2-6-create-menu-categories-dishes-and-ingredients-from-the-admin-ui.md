---
baseline_commit: 01b85e53e61a95304f3ab6e0bf5e6fa9155fd1ab
epic: 2
story: 6
---

# Story 2.6: Create Menu Categories, Dishes, and Ingredients from the Admin UI

Status: ready-for-dev

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

- [ ] **Task 1: `menuService.ts` additions + the pre-existing loading/error fix** (AC: 1, 2, 3)
  - [ ] In `frontend/src/services/menuService.ts`, add two payload types **locally in the service
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
  - [ ] Add `useCreateCategory()` and `useCreateDish()`, copying `useUpdateDishAvailability`'s
    shape exactly: `apiRequest` only, `onSuccess` invalidates `CATEGORIES_QUERY_KEY` /
    `DISHES_QUERY_KEY` respectively (both already-defined module constants — reuse them, do not
    redeclare). Nothing here can be rejected because of stale client data (no concurrent-edit race
    on a *create*), so `onSuccess` is correct, not `onSettled` (that distinction is for mutations
    that can 409 against a caller's stale copy, per `project-context.md`).
  - [ ] Fix `MenuManagementPage.tsx`'s pre-existing gap (see Scope note): destructure
    `isLoading`/`isError` from `useCategories()` too, OR both queries' `isLoading`/`isError`
    together (`isLoading = dishesLoading || categoriesLoading`, same for `isError`), and make
    Retry refetch both. Matches `DishesPage`'s fix from Story 2.5 exactly — that file is the
    precedent to copy, not a hypothetical.

- [ ] **Task 2: Dish/Category creation UI on `MenuManagementPage.tsx`** (AC: 1, 2, 3)
  - [ ] Add an always-visible "+ New dish" form above the existing dish list (`Typography
    variant="h5"` heading stays; form goes below it, list below that — same vertical order
    `TablesSetupPage` uses). Fields: name (`TextField`), description (`TextField`, optional),
    price (`TextField`, numeric — parse explicitly with a helper mirroring
    `TablesSetupPage.tsx`'s `parsePositiveInteger`, adapted for a decimal: reject non-numeric,
    reject `<= 0`, never let `Number("")`/`Number("abc")` reach `JSON.stringify` as `null`/`NaN`),
    category (`Select`, populated from `useCategories()`, plus the inline "+ New category" reveal
    described below), prep time (`TextField`, optional, numeric, `>= 0`).
  - [ ] **Inline category creation**: next to/inside the category `Select`, a small link/button
    "+ New category" reveals a `TextField` + Confirm/Cancel in place (component-local boolean
    state, same reveal shape as `TablesSetupPage`'s `TableListRow` uses for `isEditing`). On
    Confirm, call `useCreateCategory()`;
    on success, close the reveal and set the dish form's `category_id` to the newly created
    Category's `id` so the Admin doesn't have to reselect it. On failure (409 duplicate name),
    show `ApiError.message` inline in the reveal, do not close it.
  - [ ] Submitting "+ New dish" calls `useCreateDish()`. On success, clear the form. On failure
    (404 nonexistent category — unreachable via the UI's own picker but still a valid server
    response; 422 validation), render `ApiError.message` inline via an `Alert`, matching
    `TablesSetupPage`'s `createMutation.isError` pattern exactly. Do not re-word any backend
    string (UX-DR17).
  - [ ] Update the file's own top-of-component doc comment, which currently states creation forms
    are "deliberately out of scope" — that sentence describes Story 2.3's scope, not this file's
    current state, and must not survive unedited.

- [ ] **Task 3: `inventoryService.ts` — add the create mutation** (AC: 4, 5)
  - [ ] Promote the inline `["inventory", "ingredients"]` array literal in `useIngredients()`'s
    `queryKey` to a module-level `INGREDIENTS_QUERY_KEY` constant (matching every other service
    file's convention — `menuService.ts`/`tableService.ts` both do this; `inventoryService.ts` is
    currently the only one that doesn't, because it has only ever had one hook). Reuse the constant
    in both the existing query and the new mutation's invalidation.
  - [ ] Add the payload type **locally in `inventoryService.ts`**, same rule as Task 1
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
  - [ ] Add `useCreateIngredient()` to `inventoryService.ts`: `POST /api/inventory/ingredients`,
    `onSuccess` invalidates `INGREDIENTS_QUERY_KEY`.

- [ ] **Task 4: `IngredientsPage.tsx` — real content, replacing the placeholder** (AC: 4, 5, 6)
  - [ ] Header: `<h1>Ingredients</h1>` plus a subtitle `"{n} ingredients"` (no threshold/shortage
    count — that needs the comparison logic Story 4.3 owns, do not invent it here).
  - [ ] Always-visible "Add ingredient" form: name (`TextField`), unit (`Select` over the three
    `Unit` values `kg`/`liter`/`piece`), minimum stock threshold (`TextField`, numeric, `>= 0`,
    parsed explicitly per the same non-null-on-`NaN` reasoning as Task 2's price field), current
    stock (`TextField`, numeric, optional, `>= 0` — omit from the payload entirely if left blank,
    do not send `0` or `null` for "not specified", the backend already defaults it).
  - [ ] Dense-row list (`Table`/`size="small"` theme default) with columns Name / Unit / Current
    stock / Threshold, populated via the existing `useIngredients()`. **Do not add** shortage
    sorting, red highlighting, a Status column, or click-to-detail — `key-ingredients.html` has
    all of these, but they need the below-threshold comparison Story 4.3 owns; this list proves
    creation worked, nothing more (see Scope note in `epics.md`).
  - [ ] Loading/error/empty triad, same wording pattern as every other domain screen: `isLoading`
    → `RowsSkeleton`; `isError` → `Alert` + Retry calling `refetch()`; `ingredients?.length === 0`
    → `Typography` reading **"No ingredients recorded yet"** (AC6's exact required copy — note
    this differs from `TablesSetupPage`'s "No tables configured yet.", each screen has its own
    copy per its own AC, do not genericize).
  - [ ] Submitting "Add ingredient" calls `useCreateIngredient()`. On success, clear the form. On
    failure (409 duplicate name, exact string `"That ingredient name already exists"`; 422), render
    inline via `Alert`, same pattern as Task 2.

- [ ] **Task 5: Tests** (AC: all)
  - [ ] `MenuManagementPage.test.tsx` (extend the existing file, do not replace it — its current
    recipe-editor tests must keep passing): add tests for dish creation success, the exact 409
    string on duplicate category name, the inline "+ New category" flow (create, then the new
    category is selected in the dish form), and a categories-fetch-failure test proving the fixed
    isLoading/isError-combining actually renders an error (this is the regression test for Task
    1's fix — write it, then temporarily revert the fix and confirm it fails, before trusting it;
    this is the exact verification step Story 2.5's own review lesson calls for).
  - [ ] `IngredientsPage.test.tsx` (new file, mirrors `TablesSetupPage.test.tsx`'s conventions:
    mock only `fetch`, real `QueryClient`, `jsonResponse` helper). Required coverage: list renders;
    create succeeds and clears the form; duplicate-name 409 renders the exact backend string and
    preserves the form; empty state shows "No ingredients recorded yet"; error+Retry.
  - [ ] Mutation-test the new tests before trusting them (Story 1.6's review lesson, now a standing
    practice, not optional): pick at least the duplicate-name and empty-state assertions, delete
    the behavior they claim to pin, confirm the test actually fails, then restore.

- [ ] **Task 6: Docs** (AC: n/a — required for story completion, not dev-story)
  - [ ] Update `_bmad-output/project-context.md`: `IngredientsPage` moves from placeholder to real
    (fifth domain screen); `MenuManagementPage` gains create forms; suite counts; a dated patch
    entry noting the retroactive `isLoading`/`isError` fix and why it was in this story's scope.
  - [ ] `sprint-status.yaml` and `epics.md` need no further edits — already registered as Story 2.6.

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

### Debug Log References

### Completion Notes List

### File List
