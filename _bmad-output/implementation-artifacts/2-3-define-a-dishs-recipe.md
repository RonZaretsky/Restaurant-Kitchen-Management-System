---
baseline_commit: 6ed78e2a0889f7d272f2384642722094726f258c
epic: 2
story: 3
---

# Story 2.3: Define a Dish's Recipe

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Admin,
I want to define and edit the Recipe Ingredient lines that compose a Dish,
so that stock deduction and availability gating both work correctly.

## Scope note (read first)

**This story is full-stack, unlike Stories 1.1-1.3, 2.1 and 2.2, which were all backend-only.**
Story 2.2's own AC3 explicitly deferred the frontend disabled-toggle behavior "to Story 2.3's
concern, once a menu-management screen exists," and this story's own AC4 (below) names UX-DR13's
frontend behavior ("re-enables instantly, with no page reload") as its own acceptance criterion.
There is no separate "build the Menu Management screen" story anywhere in `sprint-status.yaml`, so
this is where it happens.

**Frontend scope is deliberately narrow**, matching what the 4 ACs below actually test, not the
full mockup:

- **In scope:** a dish list (read), each dish row expandable into a recipe-ingredient editor
  (add/edit/remove lines), and an availability toggle whose enabled/disabled state and click
  behavior are wired to real backend state. This is enough to exercise all 4 ACs end-to-end.
- **Out of scope:** Category creation UI and Dish creation UI. No AC in this story or in Story
  2.2 tests either, and building them would be scope beyond what's asked (see project-context.md's
  Academic context note: "Don't add scope beyond the epics to look more impressive"). Admin test
  data for this story's own tests is seeded directly via `db_session`, the same way
  `test_menu.py`'s AD-8 success-path test already does. A later story can add create-forms if the
  epics ever call for them; none currently does.

**Backend scope includes two small pieces of enabling infrastructure**, both justified below, not
scope creep:

1. `GET /api/menu/categories` and `GET /api/menu/dishes` (list endpoints) — the frontend dish list
   needs data to render before an Admin can drill into a recipe. Neither exists yet; only the
   `POST`/`PATCH` writes from Story 2.2 do.
2. `GET /api/inventory/ingredients` (list endpoint) — the recipe-ingredient-add form needs a real
   Ingredient picker, not a free-typed id. This naturally belongs to Epic 4's Story 4.3 ("View
   Ingredient Stock Levels"), which is still `backlog` and epic-sequenced after Epic 2. Build the
   minimal list endpoint here, gated to `(admin, warehouse_manager)` matching
   `InventoryWriteDep`'s existing two-Role shape (not a new one-off Role combination), so Story 4.3
   extends this same endpoint (stock levels, low-stock highlighting) rather than duplicating it.

## Acceptance Criteria

**AC1 — Save Recipe Ingredient lines**
Given an existing Dish and a set of Ingredient + quantity + unit lines, when an Admin saves the
Dish's recipe, then those Recipe Ingredient lines are persisted (FR-23).

**AC2 — Cannot remove the last line while available**
Given a Dish is currently available, when an Admin attempts to remove its last Recipe Ingredient
line, then the removal is rejected until the Dish is marked unavailable first (AD-8).

**AC3 — Recipe reads are always live**
Given a Dish's Recipe is edited, when the Recipe is read back for any purpose, then the
currently-defined lines are returned, never a snapshot taken at an earlier time; this is what lets
Epic 5's deduction read live Recipe state rather than a stale copy (FR-23, verified end-to-end in
Story 5.2).

**AC4 — Availability gate re-enables instantly**
Given a Dish with zero Recipe Ingredient lines and a disabled availability toggle, when an Admin
adds its first ingredient line, then the availability gate control re-enables instantly, with no
page reload (UX-DR13).

## Tasks / Subtasks

- [x] **Task 1: Backend request/response schemas** (AC: 1, 3)
  - [x] Add to `backend/data_models/recipe.py`. Import `_INT4_MAX` from `.menu` (already defined
    there for the identical reason: `ingredient_id` is a plain-`Integer` FK, needs the same int4
    upper bound Story 2.2's review caught for `category_id`, per trap 16):
    ```python
    from .menu import _INT4_MAX

    class CreateRecipeIngredientRequest(BaseModel):
        """Body of an Admin's request to add a Recipe Ingredient line to a Dish."""
        ingredient_id: int = Field(gt=0, le=_INT4_MAX)
        # max_digits/decimal_places match RecipeIngredient.quantity's Numeric(10, 3)
        # column exactly, same reasoning as CreateIngredientRequest's bounds (trap 16).
        quantity: Decimal = Field(gt=0, max_digits=10, decimal_places=3)
        unit: Unit

    class UpdateRecipeIngredientRequest(BaseModel):
        """Body of an Admin's request to edit a line's quantity and/or unit.
        At least one field required, mirroring UpdateDishRequest's shape."""
        quantity: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
        unit: Unit | None = None

        @model_validator(mode="after")
        def at_least_one_field(self) -> "UpdateRecipeIngredientRequest":
            if self.quantity is None and self.unit is None:
                raise ValueError("at least one field must be provided")
            return self

    class RecipeIngredientResponse(BaseModel):
        """Body of any menu endpoint response describing a Recipe Ingredient line.

        Deliberately maps 1:1 to RecipeIngredient's own columns (no joined
        Ingredient.name), matching CategoryResponse/DishResponse's precedent of
        not enriching responses with joined data. A name-enriched read is a
        frontend-list-rendering concern; the frontend already holds the
        Ingredient list from GET /api/inventory/ingredients (Task 6) and can
        join client-side, so no backend join is needed for this story's ACs.
        """
        model_config = {"from_attributes": True}
        dish_id: int
        ingredient_id: int
        quantity: Decimal
        unit: Unit
    ```
  - [x] Add `IngredientResponse`-style list support to `backend/data_models/menu.py`: no new
    schema needed there, `CategoryResponse`/`DishResponse` already exist and are reused as-is for
    the new list endpoints (`list[CategoryResponse]`, `list[DishResponse]`).
  - [x] Export `CreateRecipeIngredientRequest`, `UpdateRecipeIngredientRequest`,
    `RecipeIngredientResponse` from `backend/data_models/__init__.py`.

- [x] **Task 2: Exceptions, and the NotFoundError base refactor** (AC: 1, 2, 3)
  - [x] project-context.md's trap 17 pre-authorizes this: "If a fourth `*NotFoundError` is ever
    added, that is the signal to stop duplicating and introduce a shared `NotFoundError` base."
    This story adds a **fourth and fifth** (`IngredientNotFoundError`, `RecipeIngredientNotFoundError`),
    so do the refactor now rather than adding a sixth near-duplicate handler.
  - [x] In `backend/exceptions/__init__.py`, add a base and re-parent the three existing types
    (content unchanged, only the base class changes):
    ```python
    class NotFoundError(Exception):
        """Base for a request that references an id with no matching row.
        One handler in main.py turns any subclass into a 404 carrying that
        subclass's detail, mirroring AuthError/ConflictError's shape."""
        detail = "Not found"

    class UserNotFoundError(NotFoundError):
        """Raised when an admin action targets a User id that does not exist."""
        detail = "User not found"

    class CategoryNotFoundError(NotFoundError):
        """Raised when a request references a category_id that does not exist."""
        detail = "Category not found"

    class DishNotFoundError(NotFoundError):
        """Raised when an admin action targets a Dish id that does not exist."""
        detail = "Dish not found"

    class IngredientNotFoundError(NotFoundError):
        """Raised when a request references an ingredient_id that does not exist."""
        detail = "Ingredient not found"

    class RecipeIngredientNotFoundError(NotFoundError):
        """Raised when a request targets a Dish/Ingredient pair with no existing Recipe Ingredient line."""
        detail = "Recipe ingredient not found"

    class DuplicateRecipeIngredientError(ConflictError):
        """Raised when adding a Recipe Ingredient line for an ingredient already on this Dish's recipe.
        The composite primary key (dish_id, ingredient_id) is the real arbiter; this
        turns that constraint violation into a clean 409 instead of a 500."""
        detail = "That ingredient is already on this dish's recipe"

    class CannotRemoveLastRecipeIngredientError(ConflictError):
        """Raised when removing a Dish's last Recipe Ingredient line while it is available (AD-8, second half)."""
        detail = "Cannot remove the last recipe ingredient while the dish is available"
    ```
  - [x] In `backend/exceptions/handlers.py`: delete `_user_not_found_error_handler`,
    `_category_not_found_error_handler`, `_dish_not_found_error_handler` and their three
    registrations. Replace with **one** handler and **one** registration:
    ```python
    async def _not_found_error_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        """Turn any missing-resource lookup into a 404 carrying its message."""
        return JSONResponse(status_code=404, content={"detail": exc.detail})
    ```
    `app.add_exception_handler(NotFoundError, _not_found_error_handler)`. Update the `from
    exceptions import (...)` line accordingly (drop the three specific names, add `NotFoundError`
    if referenced directly, though FastAPI dispatches by the raised subclass so importing the base
    is enough for registration).
  - [x] `DuplicateRecipeIngredientError`/`CannotRemoveLastRecipeIngredientError` need **no new
    handler**, both are `ConflictError` subclasses and the existing `_conflict_error_handler`
    already covers the whole family (409), same as `EmptyRecipeError`/`DuplicateCategoryNameError`.
  - [x] This refactor changes **zero observable behavior** (status codes and `detail` strings are
    identical), so no existing test in `test_auth.py`/`test_menu.py` should need updating. Run the
    full suite after the refactor alone, before adding any new code, to confirm.

- [x] **Task 3: Extend `MenuService`** (AC: 1, 2, 3)
  - [x] Add to `backend/services/menu_service.py` (same file, same class, this is a continuation
    of Dish/Category authoring, not a new domain — see Dev Notes):
    ```python
    async def list_categories(self, db: AsyncSession) -> Sequence[Category]:
        """No actor/logging needed, a plain read has nothing to reject or audit."""

    async def list_dishes(self, db: AsyncSession) -> Sequence[Dish]:
        """Same shape as list_categories."""

    async def list_recipe_ingredients(
        self, db: AsyncSession, actor: User, dish_id: int
    ) -> Sequence[RecipeIngredient]:
        """Verify the Dish exists (DishNotFoundError), then return every
        RecipeIngredient row for it. This is AC3's 'read back' path: a plain
        SELECT against current state every call, never cached, so it can
        never return a stale snapshot."""

    async def add_recipe_ingredient(
        self, db: AsyncSession, actor: User, dish_id: int, payload: CreateRecipeIngredientRequest
    ) -> RecipeIngredient:
        """Verify the Dish exists (DishNotFoundError) and the Ingredient exists
        (IngredientNotFoundError). Check for an existing (dish_id, ingredient_id)
        row first (DuplicateRecipeIngredientError if found, same
        check-then-insert-with-IntegrityError-fallback shape as
        create_category's duplicate-name race handling, since the composite PK
        is the real arbiter). Insert, commit, refresh, log at INFO."""

    async def update_recipe_ingredient(
        self, db: AsyncSession, actor: User, dish_id: int, ingredient_id: int,
        payload: UpdateRecipeIngredientRequest,
    ) -> RecipeIngredient:
        """db.get(RecipeIngredient, (dish_id, ingredient_id)); raise
        RecipeIngredientNotFoundError if None (this call also implicitly
        confirms the Dish exists, a separate DishNotFoundError lookup is
        redundant here). Apply changed fields only, no-op-if-nothing-changed,
        matching update_dish's exact reasoning. Log at INFO."""

    async def remove_recipe_ingredient(
        self, db: AsyncSession, actor: User, dish_id: int, ingredient_id: int
    ) -> None:
        """db.get both the Dish (DishNotFoundError) and the RecipeIngredient
        row (RecipeIngredientNotFoundError). If dish.is_available is True,
        count this Dish's RecipeIngredient rows; if the count is 1 (this row
        is the last one), raise CannotRemoveLastRecipeIngredientError before
        deleting anything (AC2, AD-8 second half). Otherwise delete and
        commit. Log the rejection at WARNING, the deletion at INFO."""
    ```
  - [x] `list_categories`/`list_dishes` intentionally take no `actor` argument: unlike every
    mutating method in this file, a plain unfiltered read has nothing to reject and nothing worth
    auditing (permissions are Role-level only per project-context.md's Domain rules, "every Admin
    sees every Dish," there is no per-Admin filtering to apply). Do not thread `actor` through
    unused, that would be dead code the next reader has to explain.
  - [x] The last-line count check in `remove_recipe_ingredient` is a read-then-delete without a
    row lock, the same accepted shape as `_reject_if_recipe_empty`'s existing check
    (`update_dish`'s AD-8 gate), which project-context.md's trap 9 discussion already scoped: only
    invariants of the form "reject if this would leave zero/too few X" under *concurrent writers to
    the same row* need `SELECT ... FOR UPDATE` (that trap's own example was two Admins
    deactivating each other). Two Admins concurrently editing the same Dish's recipe is the same
    accepted-risk class NFR-6 already covers for Story 2.2's identical check; do not add locking
    here that Story 2.2 didn't add for the mirror-image case.
  - [x] Add `from typing import Sequence` (or `collections.abc.Sequence`, matching this codebase's
    existing import style, check `user_service.py` for the precedent) and the five new imports
    from `data_models`/`exceptions` to the top of the file.

- [x] **Task 4: New `api/menu.py` routes** (AC: 1, 2, 3, 4)
  - [x] Add to `backend/api/menu.py`, same `router`, same `MenuDep` (admin-only, unchanged):
    ```python
    @router.get("/categories", response_model=list[CategoryResponse])
    @inject
    async def list_categories(actor: MenuDep, db: SessionDep,
                               menu_service: MenuService = Depends(Provide[Container.menu_service])) -> list[Category]:
        return await menu_service.list_categories(db)

    @router.get("/dishes", response_model=list[DishResponse])
    @inject
    async def list_dishes(actor: MenuDep, db: SessionDep,
                           menu_service: MenuService = Depends(Provide[Container.menu_service])) -> list[Dish]:
        return await menu_service.list_dishes(db)

    @router.get("/dishes/{dish_id}/recipe-ingredients", response_model=list[RecipeIngredientResponse],
                responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 404))
    @inject
    async def list_recipe_ingredients(dish_id: int, actor: MenuDep, db: SessionDep,
                                       menu_service: MenuService = Depends(Provide[Container.menu_service])) -> list[RecipeIngredient]:
        return await menu_service.list_recipe_ingredients(db, actor, dish_id)

    @router.post("/dishes/{dish_id}/recipe-ingredients", response_model=RecipeIngredientResponse,
                 status_code=201, responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 404, 409))
    @inject
    async def add_recipe_ingredient(dish_id: int, payload: CreateRecipeIngredientRequest, actor: MenuDep, db: SessionDep,
                                     menu_service: MenuService = Depends(Provide[Container.menu_service])) -> RecipeIngredient:
        return await menu_service.add_recipe_ingredient(db, actor, dish_id, payload)

    @router.patch("/dishes/{dish_id}/recipe-ingredients/{ingredient_id}", response_model=RecipeIngredientResponse,
                  responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 404))
    @inject
    async def update_recipe_ingredient(dish_id: int, ingredient_id: int, payload: UpdateRecipeIngredientRequest,
                                        actor: MenuDep, db: SessionDep,
                                        menu_service: MenuService = Depends(Provide[Container.menu_service])) -> RecipeIngredient:
        return await menu_service.update_recipe_ingredient(db, actor, dish_id, ingredient_id, payload)

    @router.delete("/dishes/{dish_id}/recipe-ingredients/{ingredient_id}", status_code=204,
                   responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 404, 409))
    @inject
    async def remove_recipe_ingredient(dish_id: int, ingredient_id: int, actor: MenuDep, db: SessionDep,
                                        menu_service: MenuService = Depends(Provide[Container.menu_service])) -> None:
        await menu_service.remove_recipe_ingredient(db, actor, dish_id, ingredient_id)
    ```
  - [x] Extend `_ERROR_DESCRIPTIONS` with a 409 line covering both new conflict cases (duplicate
    line, last-line-while-available), matching the dict's existing style of one prose line per
    status, not per exception type.
  - [x] Add the new type imports (`CreateRecipeIngredientRequest`, `RecipeIngredientResponse`,
    `UpdateRecipeIngredientRequest`, `RecipeIngredient`) to `api/menu.py`'s `from data_models
    import (...)` block.
  - [x] No `container.py` or `main.py` changes needed, `menu_service`/`"api.menu"` are already
    wired from Story 2.2.

- [x] **Task 5: New `api/inventory.py` route** (enabling infrastructure, see Scope note)
  - [x] Add to `backend/api/inventory.py`, reusing the existing `InventoryWriteDep`-adjacent
    pattern but for reads. Add a sibling dep (reads permit the same two Roles as writes here,
    unlike Menu's admin-only split): `InventoryReadDep = Annotated[User,
    Depends(require_role(UserRole.admin, UserRole.warehouse_manager))]` (or reuse
    `InventoryWriteDep` directly under a read-oriented local alias if you prefer one fewer name;
    either is fine, name it for what Story 4.3 will also need).
    ```python
    @router.get("/ingredients", response_model=list[IngredientResponse])
    @inject
    async def list_ingredients(actor: InventoryReadDep, db: SessionDep,
                                inventory_service: InventoryService = Depends(Provide[Container.inventory_service])) -> list[Ingredient]:
        return await inventory_service.list_ingredients(db)
    ```
  - [x] Add `list_ingredients(self, db: AsyncSession) -> Sequence[Ingredient]` to
    `InventoryService` (plain unfiltered read, no `actor`, same reasoning as
    `MenuService.list_dishes`).

- [x] **Task 6: Backend tests** (AC: 1, 2, 3)
  - [x] Extend `backend/tests/test_menu.py` (same file, same router). Cover:
    - `GET /api/menu/categories` and `GET /api/menu/dishes` return everything present, 401/403
      gated the same as the existing routes.
    - An Admin can add a Recipe Ingredient line to a Dish (201), and `GET
      /dishes/{id}/recipe-ingredients` reflects it immediately (AC1, AC3 read-back).
    - Adding a line for an `ingredient_id` that does not exist is rejected 404
      (`IngredientNotFoundError`).
    - Adding a line for an `ingredient_id` already on that Dish's recipe is rejected 409
      (`DuplicateRecipeIngredientError`).
    - An Admin can update a line's `quantity`/`unit` (200), and the read-back reflects the new
      value, not the old one (AC3).
    - **AC2, the story's core rule:** mark a Dish available (seed one `RecipeIngredient` row
      directly via `db_session`, then `PATCH is_available=true`, mirroring `test_menu.py`'s
      existing AD-8 success-path test), then attempt to `DELETE` its only recipe line: rejected
      409 with the exact "Cannot remove the last recipe ingredient while the dish is available"
      detail. Then mark the Dish unavailable and retry the same delete: succeeds (204).
    - Deleting one of *two* lines on an available Dish succeeds (the "last line" guard only fires
      at count 1, not on every delete while available).
    - `PATCH`/`DELETE` on a `(dish_id, ingredient_id)` pair with no existing line is rejected 404
      (`RecipeIngredientNotFoundError`).
    - `PATCH` with an empty body is rejected 422 (mirrors `UpdateDishRequest`'s existing test).
    - A non-Admin (warehouse_manager or cook) cannot reach any of the five new `/menu/` routes,
      403. Unauthenticated, 401.
    - A negative or oversized-precision `quantity`, and an `ingredient_id` beyond int4 range, are
      each rejected 422 (same regression class as trap 16, prove it up front here too).
  - [x] Add to `backend/tests/test_inventory.py`: `GET /api/inventory/ingredients` returns
    everything present; both permitted Roles (admin, warehouse_manager) succeed; cook is 403;
    unauthenticated is 401.
  - [x] After Task 2's `NotFoundError` refactor, confirm the pre-existing `test_admin.py`
    (`UserNotFoundError`) and `test_menu.py` (`CategoryNotFoundError`/`DishNotFoundError`) tests
    still pass unmodified, their status codes and detail strings are unchanged by the refactor.
  - [x] Full regression: `uv run pytest` from `backend/`.

- [x] **Task 7: Frontend `menuService.ts` and `inventoryService.ts`** (AC: 1, 2, 3, 4)
  - [x] New file `frontend/src/services/menuService.ts`, first per-domain service file to follow
    `authService.ts`'s exact TanStack Query hook shape (query key arrays, `apiRequest<T>`
    wrapper, no direct `fetch`). Hooks needed:
    - `useCategories()` — `useQuery`, key `["menu", "categories"]`.
    - `useDishes()` — `useQuery`, key `["menu", "dishes"]`.
    - `useRecipeIngredients(dishId: number)` — `useQuery`, key `["menu", "dishes", dishId,
      "recipe-ingredients"]`, `enabled` only while a valid `dishId` is present if the panel can
      render before a dish is picked.
    - `useAddRecipeIngredient(dishId: number)` — `useMutation`, invalidates the
      `recipe-ingredients` key for that `dishId` on success (AC3/AC4 depend on the list
      refetching without a page reload).
    - `useUpdateRecipeIngredient(dishId: number)` — same invalidation.
    - `useRemoveRecipeIngredient(dishId: number)` — same invalidation, **also** invalidate
      `["menu", "dishes"]` if the dish list itself shows availability (so a rejected/succeeded
      delete near the AD-8 boundary is reflected without a manual refresh).
    - `useUpdateDishAvailability(dishId: number)` — `useMutation` calling the existing `PATCH
      /api/menu/dishes/{dishId}` with `{ is_available }`, invalidates `["menu", "dishes"]`. This
      reuses Story 2.2's backend endpoint, no new backend route for this one.
  - [x] New file `frontend/src/services/inventoryService.ts`: `useIngredients()`, same shape,
    wrapping the new `GET /api/inventory/ingredients`. Keep it to this one hook, an
    ingredient-detail/stock-levels UI is Epic 4's Story 4.3, not this story.

- [x] **Task 8: Frontend `MenuManagementPage` and recipe editor** (AC: 1, 2, 3, 4)
  - [x] Replace the placeholder in `frontend/src/pages/admin/MenuManagementPage.tsx`. Render the
    dish list from `useDishes()` (a MUI `List` or `Table`, per DESIGN.md's "everything not listed
    [as a delta component] is used as MUI ships it" rule, do not hand-roll custom row styling).
    Each row: name, category, an availability indicator/toggle, and an expand control.
  - [x] New component `frontend/src/components/menu/DishRecipeEditor.tsx`, rendered inside each
    expanded dish row. Owns: the current recipe-line table (`useRecipeIngredients(dishId)`), an
    "Add ingredient" row (an Ingredient `Select` sourced from `useIngredients()`, a quantity
    `TextField`, a unit `Select`, submit calling `useAddRecipeIngredient`), and a delete action per
    row calling `useRemoveRecipeIngredient`. Surface a 409 from either mutation as an inline
    message (not a toast/snackbar unless one is already established elsewhere in this codebase,
    none is yet), matching the mockup's `.gate-note` intent: "Cannot remove the last recipe
    ingredient while the dish is available" and "That ingredient is already on this dish's recipe"
    should reach the Admin verbatim from the backend `detail`, `ApiError.message` already carries
    it (see `httpClient.ts`), do not write a second, different copy of the same message client-side.
  - [x] The availability toggle's **disabled state is a pure derived value**: `recipeLines.length
    === 0` from the same `useRecipeIngredients` data already fetched for the editor panel, not a
    second API call or a stored flag. This is what makes AC4's "re-enables instantly, no page
    reload" work for free: adding the first line invalidates the query, the list refetches, the
    derived boolean flips, React re-renders. Do not implement this as a manually-toggled local
    `useState` that has to be kept in sync by hand, that is exactly the kind of stale-derived-state
    bug this AC exists to prevent.
  - [x] When disabled, show a tooltip/inline note with the same "Cannot mark available, recipe has
    no ingredients" wording `EmptyRecipeError` already uses server-side (`data_models`'s
    `EmptyRecipeError.detail` from Story 2.2), so the two surfaces (a disabled control here, a 409
    if somehow reached anyway) never say two different things.
  - [x] Clicking the toggle when enabled calls `useUpdateDishAvailability`. No backend change
    needed here, the AD-8 rejection at 0-lines is already enforced server-side by Story 2.2's
    `_reject_if_recipe_empty`, this is only the frontend now having a UI in front of it.

- [x] **Task 9: Frontend tests** (AC: 1, 2, 3, 4)
  - [x] New file `frontend/src/pages/admin/MenuManagementPage.test.tsx`. Per project-context.md's
    Story 1.4 lesson ("mocking a service in every test hides the wiring between that service and
    its callers"), **mock only `fetch`**, drive the real `menuService`/`inventoryService` hooks,
    matching `appIntegration.test.tsx`'s pattern, not the narrower per-component `vi.mock`
    approach. Cover:
    - The dish list renders from a mocked `GET /api/menu/dishes` response.
    - Expanding a dish with zero recipe lines shows the empty state and a **disabled** toggle.
    - Adding a line (mocked `POST` success + updated `GET` on refetch) causes the toggle to become
      **enabled**, asserted from the rendered DOM state, not by re-deriving the expected value from
      the same boolean the component computes (project-context.md's tautology warning from Story
      1.4's review: derive the expected assertion from the mocked response data, not from the
      component's own logic).
    - Attempting to remove the last line of an available dish surfaces the backend's exact 409
      message inline (mocked 409 response body).
    - A non-2xx/non-409 failure (mocked network error, status 0) is handled without crashing the
      page (reuse the `ApiError` discrimination pattern already established, do not add a second
      "is this an auth failure" check here, this page is already behind `RequireAuth`).
  - [x] Before trusting any new regression assertion, reintroduce the bug it is meant to catch and
    confirm it goes red first (project-context.md's Story 1.4 lesson: "a regression test that
    cannot fail is worse than none").
  - [x] `pnpm test` from `frontend/`.

### Review Findings

Code review 2026-08-12 (three parallel adversarial layers: Blind Hunter, Edge Case Hunter,
Acceptance Auditor). All four acceptance criteria were confirmed satisfied and no scope creep was
found; the findings below are defects and convention violations underneath a correct feature. The
int4 path-parameter claim was reproduced empirically against a live Postgres before being filed,
not accepted from reasoning alone.

- [x] [Review][Patch] HIGH: a Recipe Ingredient line's `unit` is never validated against the Ingredient's own `unit` [backend/services/menu_service.py] — `Ingredient` carries its own `unit` (`data_models/recipe.py`), and a line can legally be saved as `piece` for an ingredient stocked in `kg`. No conversion table exists anywhere in the codebase, so Epic 5's automatic stock deduction (Story 5.2) will either subtract mismatched units as if they agreed, or crash. No AC in this story or the PRD covers it either way, which is itself the problem. **Resolved by decision 2026-08-12 (Ofek): reject a line whose unit differs from its Ingredient's unit**, rather than dropping the column (needs a migration) or deferring to Story 5.2. Applies to both `add_recipe_ingredient` and `update_recipe_ingredient`'s unit change; needs a new `ConflictError` subclass and its own tests.
- [x] [Review][Patch] HIGH: AD-8's last-line invariant is an unlocked read-then-write, the exact case trap 9 names [backend/services/menu_service.py:434-449] — project-context.md trap 9 explicitly lists "AD-8's last-recipe-row rule" as needing an id-ordered `SELECT ... FOR UPDATE`. Two concurrent deletes of the last two lines on an available Dish both count 2, both pass the `== 1` guard, both commit, leaving an available Dish with an empty recipe. A second variant crosses methods: a `PATCH is_available=true` (counting 1 line) racing a `DELETE` of that line (reading `is_available=False`) reaches the same state. This story's own spec wrongly pre-authorized skipping the lock; trap 9 is the binding rule and takes precedence. Fix requires locking the Dish row in both `remove_recipe_ingredient` and `_reject_if_recipe_empty`.
- [x] [Review][Patch] HIGH: every failed quantity/unit edit is silently swallowed [frontend/src/components/menu/DishRecipeEditor.tsx] — `updateMutation.isError` is never rendered, unlike `addMutation` and `removeMutation` which both have `<Alert>` blocks. A 422 (bad precision) or 404 (line removed elsewhere) produces no feedback, and because the field is uncontrolled it keeps displaying the rejected value, so the Admin believes it saved.
- [x] [Review][Patch] HIGH: a failed recipe fetch is rendered as the authoritative claim "this dish has no recipe" [frontend/src/components/menu/DishRecipeEditor.tsx] — `hasRecipe = Boolean(lines && lines.length > 0)` collapses "loaded, empty" and "query errored" into the same `false`; `useRecipeIngredients`'s `isError` is never consulted. On a 500 the panel asserts "No recipe ingredients yet." and disables the toggle while the dish row's own Chip may say Available. This is trap 13's "only a 401 means signed out" reasoning applied to state rather than auth.
- [x] [Review][Patch] HIGH: a failed availability toggle is silent and the switch is not disabled in flight [frontend/src/components/menu/DishRecipeEditor.tsx] — `availabilityMutation.isError` is never rendered and `disabled` only checks `!hasRecipe`, never `isPending`. A 409/401/network failure reads as a dead click, and rapid clicking fires N concurrent PATCHes.
- [x] [Review][Patch] MEDIUM: `dish_id`/`ingredient_id` path parameters have no int4 bound, producing an unhandled 500 [backend/api/menu.py] — confirmed empirically: `GET /api/menu/dishes/99999999999999/recipe-ingredients` raises `asyncpg.DataError: value out of int32 range`, unhandled (no `DataError` handler is registered). This is trap 16, which the story guarded on the request *body* and even wrote a regression test for, while leaving the path variant open. Fix with `Path(gt=0, le=2_147_483_647)`.
- [x] [Review][Patch] MEDIUM: the per-row quantity input is uncontrolled and under-validated [frontend/src/components/menu/DishRecipeEditor.tsx] — `defaultValue={line.quantity}` is read once and the row `key` never changes, so a refetch never resyncs it: the server normalizes `0.3` to `0.300`, the field still shows `0.3`, and every subsequent blur re-fires an identical PATCH. Clearing the field silently does nothing while leaving it visibly blank. It also has no accessible label (unlike the unit select and delete button in the same row) and no numeric input constraints.
- [x] [Review][Patch] MEDIUM: a dish-list fetch failure renders a blank page, and the test blesses it [frontend/src/pages/admin/MenuManagementPage.tsx, frontend/src/pages/admin/MenuManagementPage.test.tsx] — `useDishes().isError` is never consulted, so a failure renders the heading over an empty list with no message and no retry, unlike `RequireAuth`'s Retry affordance. The "does not crash when the backend is unreachable" test asserts only that the `Menu Management` heading exists, which is true in the loading, empty, error and success branches alike, so it cannot fail.
- [x] [Review][Patch] MEDIUM: `list_recipe_ingredients` has no `ORDER BY` [backend/services/menu_service.py] — both sibling methods added in the same change (`list_categories`, `list_dishes`) order by id and say so in their docstrings. Postgres may return rows in any order and reorder them after an UPDATE rewrites a row, so the recipe table visibly reshuffles after an edit.
- [x] [Review][Patch] MEDIUM: the three new GET routes declare no error responses, breaking trap 8's standing rule [backend/api/menu.py, backend/api/inventory.py] — `GET /categories`, `GET /dishes` and `GET /ingredients` omit `responses=error_responses(...)` while every other route in both files carries it. All three can return 401 and 403, and this story's own tests assert exactly that, so the statuses are real and undocumented.
- [x] [Review][Patch] MEDIUM: test coverage is narrower than the checked-off subtasks claim — no test ever clicks the availability toggle, so `useUpdateDishAvailability`'s URL, payload, invalidation and error path are entirely unverified; no frontend test covers the PATCH quantity/unit path (where the silent-failure defect above lives); no role/auth test exists for `GET /categories`, `GET /dishes/{id}/recipe-ingredients`, or `PATCH .../{ingredient_id}` despite Task 6 claiming all five routes; and no backend test covers `update_recipe_ingredient`'s no-op branch. Separately, the AC4 assertion uses `findByRole` followed by a synchronous `.not.toBeDisabled()`, which resolves as soon as a switch exists rather than waiting on the state under test, and should be a `waitFor`.
- [x] [Review][Patch] LOW: `MenuManagementPage` renders invalid nested `<li>` elements [frontend/src/pages/admin/MenuManagementPage.tsx] — a hand-written `<li>` wraps MUI's `<ListItem>`, which itself renders an `<li>`. The parser auto-closes the outer one, so the `<Collapse>` panel lands outside the intended list item in the real DOM. MUI's pattern is `<ListItem component="div">`.
- [x] [Review][Patch] LOW: `_ERROR_DESCRIPTIONS[404]` does not mention the recipe-ingredient case it now returns [backend/api/menu.py] — three of the four new routes can raise `RecipeIngredientNotFoundError`, a distinct resource from Ingredient. The 409 line in the same dict was expanded for both new conflict cases; the 404 line was not.
- [x] [Review][Patch] LOW: `PATCH` on a nonexistent dish reports the wrong resource [backend/services/menu_service.py] — `update_recipe_ingredient` goes straight to `_get_recipe_ingredient` without `get_dish`, so `PATCH /dishes/999999/recipe-ingredients/5` returns "Recipe ingredient not found" where the other three verbs on the same URL space return "Dish not found".
- [x] [Review][Patch] LOW: the new query hooks do not opt out of retry [frontend/src/services/menuService.ts, frontend/src/services/inventoryService.ts] — the app-level `QueryClient` sets no `retry`, so TanStack's default of 3 attempts applies and a 404/403 is retried three times with backoff. `authService.ts` deliberately sets `retry: false`; the new hooks silently diverge from that precedent.
- [x] [Review][Patch] LOW: `EMPTY_RECIPE_MESSAGE` hand-copies `EmptyRecipeError.detail` with nothing enforcing agreement [frontend/src/components/menu/DishRecipeEditor.tsx] — the comment claims the two are kept in sync, but no test pins it, so changing the backend wording leaves the frontend hint quietly stale. Same shape as trap 11's three-places-must-agree rule.
- [x] [Review][Patch] LOW: `useRemoveRecipeIngredient`'s docstring justifies its dish-list invalidation with a false premise [frontend/src/services/menuService.ts] — the backend never mutates `Dish.is_available` on removal, so neither a rejected nor an accepted delete changes the dish. The extra invalidation is harmless but the recorded reasoning is wrong and will mislead the next reader. (Note it also prefix-matches every open recipe panel's key.)
- [x] [Review][Patch] LOW: nothing pins the new `NotFoundError` inheritance [backend/exceptions/] — the refactor is correct and Starlette walks the MRO, but a future `*NotFoundError` that forgets to inherit the base becomes a silent 500 rather than failing loudly. One assertion would close it.
- [x] [Review][Dismiss] `add_recipe_ingredient`'s blanket `except IntegrityError` reports any violation as a duplicate, so a concurrently-deleted Ingredient would surface an FK violation as a wrong 409 — unreachable: no DELETE endpoint exists for Ingredients or Dishes anywhere in the codebase (the only `@router.delete` is this story's own recipe-ingredient route), so the FK can never vanish mid-request. Identical to the reasoning Story 2.2 used to dismiss the same claim about `create_category`.

## Dev Notes

### Architecture compliance

- **AD-8, second half** (this story's core rule): "reject deleting a Dish's last `RecipeIngredient`
  row while that Dish is currently available." The first half (reject marking available with zero
  rows) shipped in Story 2.2's `MenuService._reject_if_recipe_empty`. The two halves are enforced
  by two different exception types with different wording (`EmptyRecipeError` vs
  `CannotRemoveLastRecipeIngredientError`) even though they protect the same invariant from two
  directions, matching this codebase's existing convention of one exception per specific failure
  message (see `DuplicateCategoryNameError` vs `DuplicateIngredientNameError`), not a shared
  generic exception reused with different call-site strings.
- **NFR-2**: every new route reuses the existing `MenuDep` (admin-only) or the two-Role inventory
  read dep, no new Role combination invented.
- **Design pattern to name**: `MenuService` remains the same Repository-style service instance,
  now covering a fourth resource (Recipe Ingredient lines) alongside Category/Dish. Name this
  continuation, not a new pattern, in the PR description.
- **Permissions are Role-level only** (project-context.md Domain rules): `list_categories`/
  `list_dishes`/`list_ingredients` return everything unfiltered to any caller who passes the Role
  gate, there is no per-Admin or per-Warehouse-Manager scoping to add.

### Existing files this story modifies

- `backend/data_models/recipe.py` — currently ORM-only (`Unit`, `Ingredient`,
  `RecipeIngredient`) plus `Ingredient`'s own request/response schemas. `RecipeIngredient` has
  **no ORM `relationship()`** to `Dish` or `Ingredient`, just raw FK columns (composite PK:
  `dish_id`, `ingredient_id`, in that order) — matching `Dish.category_id`'s same
  no-relationship style. Do not add a `relationship()` here to "simplify" a join; every other
  model in this codebase already made that same choice, stay consistent, use explicit `db.get`/
  `select` in the service instead.
- `backend/data_models/menu.py` — read `_INT4_MAX`'s existing definition and reuse it, do not
  redefine a second copy of the same magic number in `recipe.py`.
- `backend/data_models/__init__.py` — export the three new recipe schema names.
- `backend/exceptions/__init__.py` — the `NotFoundError` base refactor (Task 2) touches three
  pre-existing classes' base, not their content. Read the whole file before editing, `ConflictError`
  and `AuthError`'s existing shape is the template `NotFoundError` should match exactly (one base,
  one handler, subclasses only override `detail`).
- `backend/exceptions/handlers.py` — collapses three near-identical handler functions into one.
  Read `_conflict_error_handler`/`_auth_error_handler` first, `_not_found_error_handler` should be
  a one-line body identical in shape to those two.
- `backend/services/menu_service.py` — read fully before editing (274 lines). `_get_category` and
  `_reject_if_recipe_empty` are existing private helpers; the new `add_recipe_ingredient`/
  `remove_recipe_ingredient` methods should call `self.get_dish(...)` the same way `update_dish`
  already does, not re-implement the Dish lookup inline.
- `backend/api/menu.py` — read fully before editing (135 lines). Reuse `MenuDep`,
  `_ERROR_DESCRIPTIONS`, `error_responses()` exactly as the three existing routes do, do not
  introduce a second router or a second error-description dict for the new routes.
- `backend/api/inventory.py` — read fully before editing (57 lines, one route today). Reuse the
  two-Role pattern `InventoryWriteDep` already established, this is its read-side sibling.
- `backend/services/inventory_service.py` — read fully before editing. `create_ingredient`'s
  logging/duplicate-check shape is precedent for style, `list_ingredients` itself is much simpler
  (no actor, no rejection path).

### New files

- `frontend/src/services/menuService.ts`
- `frontend/src/services/inventoryService.ts`
- `frontend/src/components/menu/DishRecipeEditor.tsx`
- `frontend/src/pages/admin/MenuManagementPage.test.tsx`

### Project Structure Notes

No new top-level backend folder. `frontend/src/components/menu/` is a new subfolder under the
existing `components/` (currently only `components/shell/` exists) — this is the first
domain-specific component folder, matching the plan project-context.md already lays out
("`components/` (reusable UI)"), not a deviation. No Alembic migration this story:
`RecipeIngredient`'s columns (`dish_id`, `ingredient_id`, `unit`, `quantity`) already exist exactly
as needed, nothing in `data_models/recipe.py`'s ORM classes changes, only Pydantic schemas are
added. Confirm with `tests/test_migrations.py`'s existing single-head check, no new revision
expected.

### Testing

- Backend: `uv run pytest` from `backend/`. Frontend: `pnpm test` from `frontend/`. Both harnesses
  unchanged since Story 1.0/1.4.
- Seed a Dish's first Recipe Ingredient row directly via `db_session` for the AD-8 success-path
  setup, the same pattern `test_menu.py`'s existing
  `test_marking_a_dish_available_succeeds_once_it_has_a_recipe_ingredient` already uses (that test
  is effectively this story's own AC2 setup, written a story early because 2.2's review wanted the
  success path covered before 2.3 existed to build the endpoint).
- Frontend: mock only `fetch`, not the service module, for at least one test file covering this
  page (Task 9). Component-level tests may still mock the service for narrower cases, but at least
  one full-wiring test is required, per the Story 1.4 lesson already codified in
  project-context.md's Testing section.
- Verify any new numeric-boundary test value (oversized `quantity` precision, out-of-range
  `ingredient_id`) is actually rejected, not accepted at the boundary, by running it, not by
  reasoning about the Pydantic bound in the abstract (Story 2.1's own review lesson, project-context.md
  trap 16/Testing section: a first attempt at exactly the boundary value was wrongly accepted).

### References

- Story source: [Source: _bmad-output/planning-artifacts/epics.md#Story 2.3]
- FR-23 (full text): [Source: _bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md#FR-23]
- AD-8 (both halves, this story owns the second): [Source: ARCHITECTURE-SPINE.md#AD-8]
- UX-DR13 (canonical wording, availability gate re-enable behavior): [Source:
  _bmad-output/planning-artifacts/ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/EXPERIENCE.md]
- Mockup reference (illustrative structure only, not literal markup, per DESIGN.md's "everything
  not listed [as a delta component] is used as MUI ships it"): [Source:
  _bmad-output/planning-artifacts/ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/mockups/key-menu-management.html]
- Precedent this story extends: Story 2.2's `MenuService`/`api/menu.py`/`_reject_if_recipe_empty`
  (the first AD-8 half), and its own explicit deferral of UX-DR13 to this story: [Source:
  _bmad-output/implementation-artifacts/2-2-manage-menu-categories-and-dishes.md#Acceptance Criteria],
  [Source: backend/services/menu_service.py], [Source: backend/api/menu.py]
- `NotFoundError` refactor trigger (trap 17, pre-authorized): [Source: _bmad-output/project-context.md]
- `RecipeIngredient`'s existing ORM shape (composite PK, no relationships): [Source:
  backend/data_models/recipe.py]
- `authService.ts`'s TanStack Query hook shape, the template for `menuService.ts`/
  `inventoryService.ts`: [Source: frontend/src/services/authService.ts]
- `httpClient.ts`'s `ApiError`/204-handling, already built for this story's DELETE route and for
  surfacing a 409 `detail` string verbatim: [Source: frontend/src/services/httpClient.ts]
- Existing route for this page, unchanged: [Source: frontend/src/router.tsx] (`admin/menu` →
  `MenuManagementPage`)

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (Claude Code, bmad-dev-story workflow)

### Debug Log References

- Backend tasks (1-6) implemented and verified first: `uv run pytest` from `backend/` passed
  181/181 (up from 158) with zero regressions, including an intermediate full-suite run right
  after the `NotFoundError` refactor alone (Task 2), before any new recipe-ingredient code was
  added, confirming the refactor changed no observable behavior.
- Docker Desktop and the `postgres` container were not running at the start of this session;
  started both before the first test run (`docker compose up -d postgres`).
- `pnpm` was not directly on PATH in this shell; used `corepack pnpm` for all frontend commands
  (`corepack pnpm build`, `corepack pnpm test`), same effective `pnpm@9.15.0` per `packageManager`.
- Frontend type-check gap found while wiring `DishRecipeEditor`: a bare MUI `<Select>` with no
  paired `<InputLabel>` has no accessible name, so it could not be queried by label in tests (and
  was not properly labelled for a screen reader either). Switched all three Selects (the per-row
  unit picker, the add-form's ingredient and unit pickers) to `<TextField select label="...">`,
  MUI's shortcut that wires the `FormControl`/`InputLabel`/`aria-labelledby` chain automatically.
- AC4's regression test (`MenuManagementPage.test.tsx`, "adding a dish's first recipe ingredient
  re-enables its availability toggle") was proven capable of failing before being trusted: the
  `useAddRecipeIngredient` mutation's `onSuccess` invalidation was temporarily removed, the test
  went red, then the invalidation was restored and the suite re-run green.

### Completion Notes List

- All 4 acceptance criteria satisfied. AC1 (save lines): `POST
  /dishes/{id}/recipe-ingredients` persists a line, proven by an immediate read-back in the same
  test. AC2 (this story's core rule): `DELETE` on an available Dish's last line is rejected 409
  with the exact "Cannot remove the last recipe ingredient while the dish is available" detail;
  marking the Dish unavailable first lets the identical delete succeed, both halves covered by one
  backend test and surfaced inline in the frontend by a dedicated component test. AC3 (live reads):
  every read (`GET .../recipe-ingredients`) is a plain uncached `SELECT`, proven by a test that
  updates a line's quantity and asserts the very next read reflects the new value. AC4 (instant
  re-enable): the frontend toggle's disabled state is a pure derived value off the same
  `useRecipeIngredients` query the table renders, no local flag; a dedicated test adds a line
  through the real UI flow and asserts the toggle re-enables with no reload, and was confirmed
  capable of catching a regression before being trusted (see Debug Log).
- The `NotFoundError` base refactor (Task 2, project-context.md's trap 17) was done as a
  behavior-preserving step first, verified against the full 158-test baseline before any new
  recipe-ingredient code was added, so a status-code or `detail`-string regression could not hide
  inside the larger diff.
- `MenuService` gained six new methods, all following the file's existing shape (no `actor` on
  plain reads, `_get_*` private lookup helpers, check-then-insert with an `IntegrityError` fallback
  for the composite-PK race, changed-fields-only logging on updates).
- Frontend: first per-domain service files beyond `authService.ts` (`menuService.ts`,
  `inventoryService.ts`), following its exact TanStack Query hook shape. First domain component
  folder (`components/menu/`). `MenuManagementPage`'s placeholder is now real content; Category/Dish
  creation forms are deliberately still out of scope per the story's own Scope note, no AC tests
  them.
- Backend suite: 181 passed (up from 158, +23). Frontend suite: 52 passed (up from 47, +5, one new
  test file). Both suites green with zero regressions on the final full run.
- No new Alembic revision: `RecipeIngredient`'s columns already matched what this story needed, and
  `tests/test_migrations.py`'s single-head/no-drift checks passed as part of the full backend run.
  No new package added to either manifest.

### File List

**Added**

- `frontend/src/types/menu.ts`
- `frontend/src/types/inventory.ts`
- `frontend/src/services/menuService.ts`
- `frontend/src/services/inventoryService.ts`
- `frontend/src/components/menu/DishRecipeEditor.tsx`
- `frontend/src/pages/admin/MenuManagementPage.test.tsx`

**Modified**

- `backend/data_models/recipe.py` (added `CreateRecipeIngredientRequest`,
  `UpdateRecipeIngredientRequest`, `RecipeIngredientResponse`; imports `_INT4_MAX` from `.menu`)
- `backend/data_models/__init__.py` (exported the three new schemas)
- `backend/exceptions/__init__.py` (added `NotFoundError` base; re-parented `UserNotFoundError`/
  `CategoryNotFoundError`/`DishNotFoundError`; added `IngredientNotFoundError`/
  `RecipeIngredientNotFoundError`/`DuplicateRecipeIngredientError`/
  `CannotRemoveLastRecipeIngredientError`)
- `backend/exceptions/handlers.py` (collapsed three near-duplicate 404 handlers into one
  `_not_found_error_handler` registered against `NotFoundError`)
- `backend/services/menu_service.py` (added `list_categories`, `list_dishes`,
  `list_recipe_ingredients`, `add_recipe_ingredient`, `update_recipe_ingredient`,
  `remove_recipe_ingredient`, `_get_ingredient`, `_get_recipe_ingredient`)
- `backend/services/inventory_service.py` (added `list_ingredients`)
- `backend/api/menu.py` (added `GET /categories`, `GET /dishes`, `GET/POST/PATCH/DELETE
  /dishes/{dish_id}/recipe-ingredients[/{ingredient_id}]`)
- `backend/api/inventory.py` (added `InventoryReadDep`, `GET /ingredients`)
- `backend/tests/test_menu.py` (23 new tests: list endpoints, add/update/remove recipe-ingredient
  lines, the AC2 last-line-while-available rule, 404/409/422/403/401 coverage)
- `backend/tests/test_inventory.py` (4 new tests for `GET /api/inventory/ingredients`)
- `frontend/src/pages/admin/MenuManagementPage.tsx` (placeholder replaced with the real dish list
  and expand-to-recipe-editor screen)

**Confirmed unchanged**: `backend/container.py`/`backend/main.py` (no new provider or wired
module needed, `menu_service`/`inventory_service`/`"api.menu"`/`"api.inventory"` already wired
from Stories 2.1/2.2), no new Alembic revision, no new package in either manifest
(`pyproject.toml`/`uv.lock`, `package.json`/`pnpm-lock.yaml`), `frontend/src/router.tsx` (the
`admin/menu` route already pointed at `MenuManagementPage`, only its contents changed).

## Change Log

| Date | Change |
|---|---|
| 2026-08-12 | Added `CreateRecipeIngredientRequest`/`UpdateRecipeIngredientRequest`/`RecipeIngredientResponse` to `backend/data_models/recipe.py`, reusing `menu.py`'s `_INT4_MAX` bound for `ingredient_id`. |
| 2026-08-12 | Refactored `UserNotFoundError`/`CategoryNotFoundError`/`DishNotFoundError` onto a new shared `NotFoundError` base and added `IngredientNotFoundError`/`RecipeIngredientNotFoundError` (project-context.md trap 17's fourth-instance trigger); collapsed three near-duplicate 404 handlers into one. Verified behavior-preserving against the full pre-existing suite before adding new code. |
| 2026-08-12 | Added `DuplicateRecipeIngredientError`/`CannotRemoveLastRecipeIngredientError` (`ConflictError` subclasses, no new handler needed). |
| 2026-08-12 | Extended `MenuService` with `list_categories`/`list_dishes`/`list_recipe_ingredients`/`add_recipe_ingredient`/`update_recipe_ingredient`/`remove_recipe_ingredient`, enforcing AD-8's second half (reject removing a Dish's last Recipe Ingredient line while it is available). Added `InventoryService.list_ingredients`. |
| 2026-08-12 | Added `GET /api/menu/categories`, `GET /api/menu/dishes`, and `GET/POST/PATCH/DELETE /api/menu/dishes/{dish_id}/recipe-ingredients[/{ingredient_id}]` to `backend/api/menu.py`; added `GET /api/inventory/ingredients` (`InventoryReadDep`, admin + warehouse_manager) to `backend/api/inventory.py`. |
| 2026-08-12 | Added 23 backend tests to `test_menu.py` and 4 to `test_inventory.py`. Full backend regression: 181 passed (up from 158). |
| 2026-08-12 | Added `frontend/src/services/menuService.ts`/`inventoryService.ts` (TanStack Query hooks) and `frontend/src/types/menu.ts`/`inventory.ts`. |
| 2026-08-12 | Replaced `MenuManagementPage`'s placeholder with a real dish list + expand-to-recipe-editor screen (`frontend/src/components/menu/DishRecipeEditor.tsx`); the availability toggle's disabled state derives from the same recipe-ingredients query the table renders, no separate local flag. |
| 2026-08-12 | Refactored the recipe/unit `<Select>` fields to `<TextField select>` for a proper accessible name (MUI's bare `Select` has none without a paired `InputLabel`). |
| 2026-08-12 | Added `frontend/src/pages/admin/MenuManagementPage.test.tsx` (5 tests, mocking only `fetch` per the Story 1.4 lesson). Confirmed the AC4 regression test fails without its underlying fix before trusting it. Full frontend regression: 52 passed (up from 47). |
| 2026-08-12 | Code review (three parallel adversarial layers: Blind Hunter, Edge Case Hunter, Acceptance Auditor). All 4 ACs confirmed satisfied and no scope creep found; 17 findings filed underneath, 1 dismissed as unreachable. **Closed AD-8's concurrency hole**, the review's most important catch: trap 9 explicitly names "AD-8's last-recipe-row rule" as needing a row lock, and this story's own spec had wrongly pre-authorized skipping it. Added `MenuService._lock_dish`, called from both `remove_recipe_ingredient` and `_reject_if_recipe_empty`, so the removal half and the availability-toggle half of AD-8 serialize on the same row instead of interleaving into an available dish with an empty recipe. |
| 2026-08-12 | Review patch: added `UnitMismatchError` and rejected any Recipe Ingredient line whose unit differs from its Ingredient's own unit (decision by Ofek: reject rather than drop the column or defer to Story 5.2). Nothing converts between units, so a liter line on a kg ingredient would have made Epic 5's deduction silently wrong. |
| 2026-08-12 | Review patch: bounded every `dish_id`/`ingredient_id` path parameter with `Path(gt=0, le=_INT4_MAX)` (trap 16). Reproduced the unhandled `asyncpg.DataError` 500 against a live Postgres before and after the fix; the story had guarded the request body but left the path open. |
| 2026-08-12 | Review patch: `list_recipe_ingredients` now orders by `ingredient_id` (matching its two sibling list methods); `update_recipe_ingredient` now checks the Dish first so a bad `dish_id` reports "Dish not found" like the other three verbs; the three new GET routes declare their 401/403 responses (trap 8); `_ERROR_DESCRIPTIONS` updated for the new 404 and 409 cases. |
| 2026-08-12 | Review patch (frontend): surfaced previously-silent failures for the quantity/unit edit and the availability toggle; a failed recipe fetch is now an error with a Retry instead of being rendered as "no recipe ingredients yet" (which also wrongly disabled the toggle); the dish list shows an error with a Retry instead of a blank page; per-row quantity is now a controlled input that resyncs with the server and restores itself when cleared; the availability switch is disabled in flight; the ingredient picker is disabled until the recipe is known; fixed invalid nested `<li>`; new hooks opt out of retry matching `authService`'s precedent; corrected the false premise in `useRemoveRecipeIngredient`'s docstring and dropped its unnecessary dish-list invalidation. |
| 2026-08-12 | Review patch (tests): +10 backend tests (unit mismatch on add and update, matching-unit success, no-op PATCH, wrong-resource 404, stable ordering, both path-param overflows, role gates on the three previously-untested routes, and a guard pinning every `*NotFoundError` to the shared base) and +3 frontend tests (the availability toggle's PATCH is now actually exercised, a rejected quantity edit surfaces, a failed recipe fetch is distinguished from an empty one). Replaced the tautological "backend unreachable" assertion, which passed in every state, and switched AC4's assertion to `waitFor` so it polls the condition under test. Both new error-path tests were confirmed red with their bugs injected before being trusted. Final regression: **191 backend, 55 frontend**, production build clean. |
