---
baseline_commit: 4593f1370e310696917fb1836cac3645ef13a76f
epic: 2
story: 2
---

# Story 2.2: Manage Menu Categories and Dishes

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Admin,
I want to create, update, and mark dishes available or unavailable, and manage menu categories,
so that I control what's sellable.

**Scope note.** Backend-only, same pattern as Stories 1.1-1.3 and 2.1. Category management is
scoped strictly to **create** in this story: the epics ACs only test category creation (no
update/delete AC exists, no duplicate-rejection AC exists for categories either, unlike
User/Table/Ingredient names). Do not add a category list/update/delete endpoint here, that would
be scope beyond what's asked. AC4 below ("a Dish marked unavailable is rejected by future
add-to-order attempts") requires **no new code in this story**: there is no add-to-order endpoint
yet (that is Epic 3), so this AC is satisfied by construction, once `is_available` is correctly
maintained by AC2/AC3, and the enforcement point belongs to whichever Epic 3 story adds
add-to-order. Do not build a placeholder order endpoint to "satisfy" this AC.

Menu authoring (both category creation and dish create/update/availability) is **Admin-only**
(FR-22), unlike Story 2.1's Ingredient creation which permitted two Roles. Do not reuse
`InventoryWriteDep`'s multi-Role shape here.

## Acceptance Criteria

**AC1 — Create a Menu Category**
Given valid category details, when an Admin creates a Menu Category, then it is available for
grouping Dishes (FR-22).

**AC2 — Create a Dish, starting unavailable**
Given valid dish details (name, description, price, prep time, category), when an Admin creates a
Dish, then it is created, starting unavailable until it has a recipe (FR-22, AD-8). The submitted
request never includes `is_available`, a newly created Dish is unconditionally unavailable
regardless of what a caller sends.

**AC3 — Cannot mark available with zero Recipe Ingredient lines**
Given a Dish with zero Recipe Ingredient lines, when an Admin attempts to mark it available, then
the attempt is rejected with "Cannot mark available, recipe has no ingredients" (FR-22, AD-8).
(The *frontend* disabled-toggle behavior UX-DR13 describes is Story 2.3's concern, once a
menu-management screen exists; this story only owns the backend rejection.)

**AC4 — Unavailable blocks future orders, not in-progress ones**
Given a Dish is marked unavailable, when the change is saved, then it is immediately rejected by
future add-to-order attempts, but Order Items already in progress on already-open Orders are
unaffected (FR-22). No implementation task in this story, `is_available` being correctly
maintained is what a later Epic 3 story reads.

## Tasks / Subtasks

- [x] **Task 1: Request/response schemas** (AC: 1, 2, 3)
  - [x] Add to `backend/data_models/menu.py` (Pydantic schemas colocated with their ORM class,
    matching `user.py`/`recipe.py`'s existing shape):
    ```python
    from decimal import Decimal
    from pydantic import BaseModel, Field, field_validator, model_validator
    from .user import _strip_and_require_content

    class CreateCategoryRequest(BaseModel):
        name: str = Field(min_length=1, max_length=50)
        _strip_name = field_validator("name")(_strip_and_require_content)

    class CategoryResponse(BaseModel):
        model_config = {"from_attributes": True}
        id: int
        name: str

    class CreateDishRequest(BaseModel):
        """Never carries is_available: AC2 forces every new Dish unavailable."""
        name: str = Field(min_length=1, max_length=100)
        description: str | None = None
        price: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
        category_id: int
        prep_time_minutes: int | None = Field(default=None, ge=0)
        _strip_name = field_validator("name")(_strip_and_require_content)

    class UpdateDishRequest(BaseModel):
        """At least one field required, mirroring UpdateUserRequest's shape."""
        name: str | None = Field(default=None, min_length=1, max_length=100)
        description: str | None = None
        price: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=2)
        category_id: int | None = None
        prep_time_minutes: int | None = Field(default=None, ge=0)
        is_available: bool | None = None
        _strip_name = field_validator("name")(_strip_and_require_content)

        @model_validator(mode="after")
        def at_least_one_field(self) -> "UpdateDishRequest":
            if all(v is None for v in (self.name, self.description, self.price,
                                        self.category_id, self.prep_time_minutes,
                                        self.is_available)):
                raise ValueError("at least one field must be provided")
            return self

    class DishResponse(BaseModel):
        model_config = {"from_attributes": True}
        id: int
        name: str
        description: str | None
        price: Decimal
        category_id: int
        is_available: bool
        prep_time_minutes: int | None
        created_at: datetime
    ```
  - [x] `price`'s `Field(gt=0, ...)`, not `ge=0`: a free Dish is not a modeled concept anywhere in
    the schema or the ACs; `gt=0` also matches this story's own Story 2.1 review finding (a
    Decimal without `max_digits`/`decimal_places` lets an out-of-range value reach the database
    and 500 instead of cleanly 422ing) — apply that bound here from the start rather than waiting
    for a review to catch it a second time.
  - [x] Export `CreateCategoryRequest`, `CategoryResponse`, `CreateDishRequest`,
    `UpdateDishRequest`, `DishResponse` from `backend/data_models/__init__.py`.
- [x] **Task 2: Exceptions** (AC: 1, 2, 3)
  - [x] Add to `backend/exceptions/__init__.py`:
    ```python
    class DuplicateCategoryNameError(ConflictError):
        """Raised when creating a Menu Category with a name that already exists."""
        detail = "That category name already exists"

    class EmptyRecipeError(ConflictError):
        """Raised when attempting to mark a Dish available with zero Recipe Ingredient lines (AD-8)."""
        detail = "Cannot mark available, recipe has no ingredients"

    class CategoryNotFoundError(Exception):
        """Raised when a request references a category_id that does not exist."""
        detail = "Category not found"

    class DishNotFoundError(Exception):
        """Raised when an admin action targets a Dish id that does not exist."""
        detail = "Dish not found"
    ```
  - [x] `DuplicateCategoryNameError` and `EmptyRecipeError` need **no new handler**, both are
    `ConflictError` subclasses and the existing `_conflict_error_handler` already covers the whole
    family (409).
  - [x] `CategoryNotFoundError` and `DishNotFoundError` are each a bare `Exception`, mirroring
    `UserNotFoundError`'s exact shape (not a shared "NotFoundError" base). Add one handler function
    per type in `backend/exceptions/handlers.py`, each a near-copy of
    `_user_not_found_error_handler`, and register both in `register_exception_handlers`.
    A shared `NotFoundError` base covering all three would be the more idiomatic move now that
    there are three, but that means touching `UserNotFoundError` (Story 1.3's code) which is out of
    this story's scope, note it as worth revisiting later rather than doing it here.
  - [x] Category name uniqueness is **case-sensitive** (matches the column's existing `unique=True`
    only). Unlike `Ingredient.name`/`User.username`, no epics AC or UX doc pairs category names
    into the case-insensitive-duplicate convention (see this story's Scope note). Do not add a
    functional lower() index or migration for categories.
- [x] **Task 3: `MenuService`** (AC: 1, 2, 3)
  - [x] New file `backend/services/menu_service.py`, modeled on `InventoryService`'s shape
    (config-free, only the logger injected):
    ```python
    class MenuService:
        def __init__(self, logger: Any) -> None:
            self._logger = logger

        async def create_category(
            self, db: AsyncSession, actor: User, payload: CreateCategoryRequest
        ) -> Category:
            """Duplicate check (case-sensitive), insert, IntegrityError race fallback.
            Same shape as InventoryService.create_ingredient, minus the func.lower() wrapper.
            """

        async def create_dish(
            self, db: AsyncSession, actor: User, payload: CreateDishRequest
        ) -> Dish:
            """Verify category_id exists (raise CategoryNotFoundError if not), then insert
            with is_available=False unconditionally, regardless of anything in payload.
            """

        async def get_dish(self, db: AsyncSession, actor: User, dish_id: int) -> Dish:
            """Raise DishNotFoundError if no Dish matches dish_id. Every by-id lookup below
            funnels through here, mirroring UserService.get_user.
            """

        async def update_dish(
            self, db: AsyncSession, actor: User, dish_id: int, payload: UpdateDishRequest
        ) -> Dish:
            """Apply each provided field. If is_available is being set True, count
            RecipeIngredient rows where dish_id == this dish's id; raise EmptyRecipeError if
            zero. If category_id is changing, verify the new category exists first
            (CategoryNotFoundError if not). A no-op update (nothing actually changes) returns
            unchanged without a log line, mirroring UserService.update_user's exact reasoning
            ("an edit submitting the values already stored is not a state change").
            """
    ```
  - [x] The `RecipeIngredient` count check: `select(func.count()).where(RecipeIngredient.dish_id ==
    dish_id)`, both `RecipeIngredient` and `func` are already available from `data_models`/
    `sqlalchemy` respectively, no new import surface. No Recipe-management story has shipped yet
    (that is Story 2.3), so this count will always be 0 today, every dish stays permanently
    unavailable until 2.3 ships, that is expected sequencing, not a bug to work around.
  - [x] Log every rejection at `WARNING` with the acting Admin's id, every successful
    create/update at `INFO`, matching `UserService`'s/`InventoryService`'s exact logging
    convention (never a bare `print`, always through the injected logger).
- [x] **Task 4: Register in the container** (AC: 1, 2, 3)
  - [x] `backend/container.py`: add
    ```python
    menu_service = providers.Factory(
        MenuService,
        logger=logging,
    )
    ```
    next to `inventory_service`, same shape.
- [x] **Task 5: `api/menu.py` router** (AC: 1, 2, 3)
  - [x] New file `backend/api/menu.py`, modeled on `api/admin.py` exactly: its own
    `APIRouter(prefix="/api/menu", tags=["menu"])`, its own `_ERROR_DESCRIPTIONS` dict,
    `error_responses()` reused (never a new `_errors()` helper):
    ```python
    MenuDep = Annotated[User, Depends(require_role(UserRole.admin))]

    @router.post("/categories", response_model=CategoryResponse, status_code=201,
                 responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 409))
    async def create_category(payload: CreateCategoryRequest, actor: MenuDep, db: SessionDep,
                               menu_service: MenuService = Depends(Provide[Container.menu_service])) -> Category:
        return await menu_service.create_category(db, actor, payload)

    @router.post("/dishes", response_model=DishResponse, status_code=201,
                 responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 404))
    async def create_dish(payload: CreateDishRequest, actor: MenuDep, db: SessionDep,
                           menu_service: MenuService = Depends(Provide[Container.menu_service])) -> Dish:
        return await menu_service.create_dish(db, actor, payload)

    @router.patch("/dishes/{dish_id}", response_model=DishResponse,
                  responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 404, 409))
    async def update_dish(dish_id: int, payload: UpdateDishRequest, actor: MenuDep, db: SessionDep,
                           menu_service: MenuService = Depends(Provide[Container.menu_service])) -> Dish:
        return await menu_service.update_dish(db, actor, dish_id, payload)
    ```
    `MenuDep` permits **only** `UserRole.admin`, unlike Story 2.1's `InventoryWriteDep`. Do not
    copy the two-Role shape, FR-22 is Admin-only.
  - [x] `backend/api/router.py`: add `from api.menu import router as menu_router` and
    `router.include_router(menu_router)`.
  - [x] `backend/main.py`: append `"api.menu"` to `container.wire(modules=[...])` (currently
    `[..., "api.inventory"]` after Story 2.1) — **append, never replace**.
- [x] **Task 6: Tests**
  - [x] New file `backend/tests/test_menu.py`, mirroring `test_inventory.py`'s style
    (`# Arrange`/`# Act`/`# Assert`, no docstrings). Cover:
    - An Admin can create a Category (201).
    - A duplicate Category name (same case) is rejected 409. (No cross-case test needed, category
      names are case-sensitive per this story's Scope note; do not write a test asserting
      case-insensitive rejection for categories, that would test behavior this story deliberately
      does not build.)
    - A non-Admin (e.g. warehouse_manager, cook, waiter) cannot create a Category, 403. An
      unauthenticated request gets 401.
    - An Admin can create a Dish; the response's `is_available` is `false` even if the request
      tried to influence it (submit an unexpected extra field or just confirm the default).
    - Creating a Dish with a `category_id` that does not exist is rejected 404.
    - Attempting to `PATCH` a Dish's `is_available` to `true` while it has zero Recipe Ingredient
      lines is rejected 409 with the exact "Cannot mark available, recipe has no ingredients"
      detail.
    - Updating a Dish's price/name/description/prep_time succeeds and persists (no availability
      change involved).
    - `PATCH` with an empty body (no fields at all) is rejected 422.
    - `PATCH` on a non-existent `dish_id` is rejected 404.
    - A negative `price` or a `price` with more than 2 decimal places (or exceeding 8 total
      digits) is rejected 422 — this is the regression class Story 2.1's review caught, prove it
      cannot recur here.
    - A negative `prep_time_minutes` is rejected 422.
  - [x] Full regression: `uv run pytest` from `backend/`.

### Review Findings

Code review 2026-08-11 (three parallel adversarial layers on sonnet: Blind Hunter, Edge Case
Hunter, Acceptance Auditor). The two integer-overflow claims below were reproduced empirically (a
real request against a live Postgres) before being patched, not accepted from the reviewer's
reasoning alone.

- [x] [Review][Patch] CONFIRMED: `category_id`/`prep_time_minutes` had no upper bound, so an out-of-range value 500s instead of 422ing [backend/data_models/menu.py] — Both are plain `Integer` (int4) columns, but neither Pydantic field had a `le` bound. `category_id=99999999999999` reached `db.get(Category, category_id)` and `prep_time_minutes=99999999999999` reached the insert, both raising an unhandled `asyncpg.DataError: value out of int32 range`. Reproduced directly against Postgres before fixing. Fixed by adding `le=2_147_483_647` (int4 max) to both fields on both `CreateDishRequest` and `UpdateDishRequest`. Regression tests added: `test_category_id_exceeding_int4_range_is_rejected`, `test_prep_time_exceeding_int4_range_is_rejected`.
- [x] [Review][Patch] `Dish.is_available`'s column-level default was `True`, contradicting AD-8's "starts unavailable until it has a recipe" [backend/data_models/menu.py] — `MenuService.create_dish` always overrides this by passing `is_available=False` explicitly, so nothing was broken today, but any future insert path that bypasses the service (a fixture, a seed script, a different service) would silently get `is_available=True` with zero recipe ingredients, the exact state this story exists to prevent. Fixed by changing the column default to `False`, matching what the service already does. No migration needed, this was a Python-side `default=`, never a `server_default=`; `tests/test_migrations.py` confirms no drift.
- [x] [Review][Patch] `update_dish`'s success log line only ever reported `is_available`, even when the actual change was to `price`, `name`, `category_id`, or `prep_time_minutes` [backend/services/menu_service.py] — CLAUDE.md's logging convention calls for identifying context that lets a flow be traced end to end; a price-only edit logged a line that looked like an availability action and said nothing about what actually changed. Fixed by collecting a `changed_fields` list and logging that instead of a single hardcoded field.
- [x] [Review][Patch] The AD-8 success path (marking a Dish available once it *does* have a recipe ingredient) was never tested, only the rejection path was [backend/tests/test_menu.py] — the one behavior this story exists to gate was proven blocked but never proven to work. Added `test_marking_a_dish_available_succeeds_once_it_has_a_recipe_ingredient`, inserting a real `Ingredient`/`RecipeIngredient` row directly via `db_session` (Story 2.3, which will build the endpoint for this, hasn't shipped yet).
- [x] [Review][Patch] No test covered `CategoryNotFoundError` via the `update_dish` path (only `create_dish`'s case was tested), no test proved `CreateDishRequest` actually ignores a submitted `is_available`, no test proved category names differing only by case are *both* accepted (the deliberate case-sensitive-only design), no test asserted the Role gate directly on the dish-create/dish-update routes (only the category route was tested, though all three share `MenuDep`), and no test covered a price with more decimal places than `decimal_places=2` allows (only the `max_digits` boundary was tested) — six coverage gaps, all cheap. Added `test_updating_to_a_nonexistent_category_is_rejected`, `test_create_dish_request_ignores_a_submitted_is_available_field`, `test_category_names_differing_only_by_case_are_both_accepted`, `test_warehouse_manager_cannot_create_a_dish`, `test_cook_cannot_update_a_dish`, `test_price_with_too_many_decimal_places_is_rejected`.
- [x] [Review][Defer] `UpdateDishRequest` has no way to clear `description` or `prep_time_minutes` back to null once set [backend/services/menu_service.py] — deferred, real but not currently needed. An explicit `"description": null` is indistinguishable from the field being omitted (`payload.description is not None` guards both), so a caller can never blank out a previously-set description or prep time via this endpoint. No AC in this story asks for that capability. Fixing it properly needs a sentinel-value pattern (distinguishing "not provided" from "provided as null"), which is more machinery than this story's scope justifies. Revisit if a later story needs to clear either field.
- [x] [Review][Dismiss] `update_dish`'s recipe-emptiness check is a check-then-act race (read the count, then commit several lines later) with no lock — matches NFR-6's explicitly accepted v1 simplification (last-write-wins for concurrent edits outside NFR-3's atomic paths); not a new risk this story introduces.
- [x] [Review][Dismiss] `create_dish`/`update_dish` don't guard against a concurrently-deleted `category_id` with an `IntegrityError` catch, unlike `create_category`'s duplicate-name race handling — no delete endpoint exists anywhere for Categories (this story is explicitly create-only, per its own Scope note), so a Category can never vanish between the existence check and the insert; the race is unreachable in the current system.
- [x] [Review][Dismiss] `CategoryNotFoundError`/`DishNotFoundError` duplicate `UserNotFoundError`'s handler shape instead of sharing a common `NotFoundError` base — already an explicit, documented decision in this story's own Task 2 (a shared base would touch Story 1.3's `UserNotFoundError`, out of scope here).
- [x] [Review][Dismiss] The blanket `except IntegrityError` in `create_category` assumes any integrity violation means a duplicate name — matches `UserService.create_user`'s/`InventoryService.create_ingredient`'s identical, already-accepted pattern; not a new risk this story introduces.
- [x] [Review][Dismiss] `UpdateDishRequest.description` has no strip/blank-content validator, unlike `name` — not a defect, `description` is genuinely optional free text with no modeled business rule requiring non-blank content, unlike `name`, which a dish cannot meaningfully lack.

## Dev Notes

### Architecture compliance

- **AD-8** ("reject setting `Dish.is_available = true` while zero `RecipeIngredient` rows, and
  reject removing the last row while available"): this story owns only the first half (the
  availability-toggle gate). The second half (rejecting removing the last Recipe Ingredient line
  while available) belongs to Story 2.3, which owns Recipe Ingredient CRUD, do not implement it
  here, there is nothing to remove yet.
- **NFR-2**: enforced via `require_role(UserRole.admin)`, layered on `CurrentUserDep`. This story
  is the first to use `require_role` with exactly one Role again (Story 2.1 was the first to use
  more than one); do not default to copying 2.1's `InventoryWriteDep` shape.
- **Design pattern to name**: `MenuService` is a third independent instance of the same
  Repository-style service pattern (`UserService` → `InventoryService` → `MenuService`), name it
  the same way in the PR description.

### Existing files this story modifies

- `backend/data_models/menu.py` — currently ORM-only (`Category`, `Dish`), no Pydantic schemas.
  Read fully before editing: `Dish.is_available` defaults to `True` at the column level
  (`default=True`), which this story's `create_dish` must override in application code (always
  insert `is_available=False`), the column default is not itself AD-8 enforcement.
- `backend/data_models/__init__.py` — export the five new schema names.
- `backend/exceptions/__init__.py` — add the four new exception types (Task 2).
- `backend/exceptions/handlers.py` — add two new handler functions
  (`_category_not_found_error_handler`, `_dish_not_found_error_handler`) and register both;
  `DuplicateCategoryNameError`/`EmptyRecipeError` need no handler changes (`ConflictError` family).
- `backend/container.py` — add `menu_service` as a `providers.Factory`.
- `backend/main.py` — append `"api.menu"` to `container.wire(modules=[...])`.
- `backend/api/router.py` — add and mount the new `menu_router`.

### New files

- `backend/api/menu.py`
- `backend/services/menu_service.py`
- `backend/tests/test_menu.py`

### Project Structure Notes

No deviation from the established five-folder backend layout. No new top-level folder, no Alembic
migration this time (no schema change, `menu.py`'s `Category`/`Dish` columns are unchanged, only
Pydantic schemas are added).

### Testing

- Backend only, `uv run pytest` from `backend/`. No frontend changes in this story.
- Use the existing `client` and `db_session` fixtures from `tests/conftest.py`. Create test Users
  the same way `test_inventory.py` does (`AuthService.hash_password`, never `bcrypt.hashpw`
  directly).
- No new Alembic revision to verify this time, `tests/test_migrations.py`'s existing drift check
  still runs as part of the full suite regardless.

### References

- Story source: [Source: _bmad-output/planning-artifacts/epics.md#Story 2.2]
- FR-22 (full text, including the "remove is soft-delete via unavailable" decision, and the
  AD-8 cross-reference): [Source: _bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md#FR-22]
- AD-8 (recipe-emptiness gate, both halves): [Source: ARCHITECTURE-SPINE.md#AD-8]
- UX-DR13 (frontend disabled-toggle behavior, explicitly Story 2.3's concern per its own final AC):
  [Source: _bmad-output/planning-artifacts/epics.md#Story 2.3]
- Precedent this story copies: Story 2.1's `InventoryService`/`api/inventory.py` shape, and Story
  2.1's own code-review finding about `Decimal` fields needing `max_digits`/`decimal_places`
  applied proactively here: [Source: _bmad-output/implementation-artifacts/2-1-create-and-manage-ingredients.md#Review Findings]
  and [Source: backend/services/inventory_service.py], [Source: backend/api/inventory.py]
- `UserNotFoundError`'s exact shape, copied twice for `CategoryNotFoundError`/`DishNotFoundError`:
  [Source: backend/exceptions/__init__.py], [Source: backend/exceptions/handlers.py]
- `require_role`'s single- and multi-Role support, this story uses the single-Role form: [Source:
  backend/api/dependencies.py]

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (Claude Code, bmad-dev-story workflow)

### Debug Log References

- Discovered a real bug while writing `UpdateDishRequest`, not from the story's own snippet:
  reusing `_strip_and_require_content` directly on an `Optional[str]` field crashes with an
  unhandled `AttributeError` (not a clean `ValidationError`) the moment a caller explicitly submits
  `"name": null`, because the helper assumes a `str` and calls `.strip()` unconditionally.
  Reproduced this exact crash against the pre-existing `UpdateUserRequest` first (same helper, same
  shape, same bug) to confirm it wasn't specific to new code. Fixed locally for `UpdateDishRequest`
  with a small wrapper that passes `None` straight through before delegating to the shared helper;
  did **not** touch `UpdateUserRequest`, that is Story 1.3's code and out of this story's scope,
  noted as worth a future fix.
- Verified the `price` Decimal-precision test value before trusting it: a first attempt
  (`"123456.78"`) turned out to be exactly 8 significant digits, the same as the column's own
  bound, so it was accepted rather than rejected. Confirmed with a quick script before writing the
  final test, replaced with `"1234567.89"` (9 digits), which does exceed `max_digits=8`.

### Completion Notes List

- All 4 acceptance criteria satisfied: AC1 (category creation), AC2 (dish creation,
  unconditionally unavailable regardless of any submitted value), AC3 (availability-toggle gate,
  rejecting with the exact "Cannot mark available, recipe has no ingredients" message), AC4
  (satisfied by construction, no new code needed since no add-to-order endpoint exists yet).
- `MenuService` is a third independent instance of the Repository-style service pattern
  (`UserService` → `InventoryService` → `MenuService`), named per this project's
  pattern-traceability convention.
- Applied Story 2.1's own review finding proactively this time: both `price` fields
  (`CreateDishRequest`/`UpdateDishRequest`) carry `max_digits=8, decimal_places=2` matching the
  `Numeric(8, 2)` column from the start, with a regression test proving it, rather than waiting for
  a review to catch the same class of bug a second time.
- `CategoryNotFoundError`/`DishNotFoundError` are additive, `UserNotFoundError`-shaped exception
  types rather than a shared `NotFoundError` base, per the story's own scoping decision (a
  refactor of `UserNotFoundError` would touch Story 1.3's code, out of scope here).
- 14 new tests in `test_menu.py`: category creation and its duplicate rejection, Role gating (only
  admin permitted; warehouse_manager and cook both rejected, matching FR-22's Admin-only scope,
  unlike Story 2.1's two-Role Ingredient creation), dish creation defaulting to unavailable,
  nonexistent-category rejection, the AD-8 availability gate, a successful field update, an
  empty-body update rejection, a nonexistent-dish update rejection, and validation (negative
  price, oversized price precision, negative prep time).
- Full regression: 149 passed (up from 135), zero regressions, on the first full run after
  implementation. No new Alembic migration this story, `menu.py`'s ORM columns are unchanged.

### File List

**Added**

- `backend/api/menu.py`
- `backend/services/menu_service.py`
- `backend/tests/test_menu.py`

**Modified**

- `backend/data_models/menu.py` (added `CreateCategoryRequest`/`CategoryResponse`/
  `CreateDishRequest`/`UpdateDishRequest`/`DishResponse`)
- `backend/data_models/__init__.py` (exported the five new schemas)
- `backend/exceptions/__init__.py` (added `DuplicateCategoryNameError(ConflictError)`,
  `EmptyRecipeError(ConflictError)`, `CategoryNotFoundError`, `DishNotFoundError`)
- `backend/exceptions/handlers.py` (added `_category_not_found_error_handler`,
  `_dish_not_found_error_handler`, registered both; `ConflictError` subclasses needed no handler
  changes)
- `backend/container.py` (added `menu_service` Factory)
- `backend/main.py` (appended `"api.menu"` to `container.wire(modules=[...])`)
- `backend/api/router.py` (included the new menu router)

**Confirmed unchanged**: `backend/api/dependencies.py` (`require_role`'s existing single-Role
usage needed no change), `backend/data_models/recipe.py` (`RecipeIngredient` read, not modified),
`pyproject.toml`/`uv.lock` (no new dependency), no new Alembic revision (no ORM column changes).

## Change Log

| Date | Change |
|---|---|
| 2026-08-11 | Added `CreateCategoryRequest`/`CategoryResponse`/`CreateDishRequest`/`UpdateDishRequest`/`DishResponse` to `backend/data_models/menu.py`, reusing `data_models/user.py`'s `_strip_and_require_content` validator. Applied Story 2.1's own review finding proactively: `price` carries `max_digits=8, decimal_places=2` matching the `Numeric(8, 2)` column from the start. |
| 2026-08-11 | Fixed a real bug found while writing `UpdateDishRequest`: an explicit `"name": null` crashed with an unhandled `AttributeError` rather than a clean 422 (the same shape of bug exists in the pre-existing `UpdateUserRequest`, left untouched as out of scope). Guarded with a small `None`-passthrough wrapper before delegating to the shared strip-and-validate helper. |
| 2026-08-11 | Added `DuplicateCategoryNameError`/`EmptyRecipeError` (`ConflictError` subclasses, no new handler needed) and `CategoryNotFoundError`/`DishNotFoundError` (each with its own handler, mirroring `UserNotFoundError`'s exact shape) to `backend/exceptions/`. |
| 2026-08-11 | Added `MenuService.create_category`/`create_dish`/`update_dish` (`backend/services/menu_service.py`), enforcing AD-8's availability gate via a `RecipeIngredient` count check. Registered as a `providers.Factory` in `container.py`. |
| 2026-08-11 | Added `POST /api/menu/categories`, `POST /api/menu/dishes`, and `PATCH /api/menu/dishes/{dish_id}` (`backend/api/menu.py`), gated to `admin` only via `require_role`'s single-Role form. Mounted in `api/router.py`; appended `"api.menu"` to `main.py`'s `container.wire(modules=[...])`. |
| 2026-08-11 | Added `backend/tests/test_menu.py`: 14 tests covering category creation/duplicate rejection, Role gating, dish creation defaulting to unavailable, nonexistent-category rejection, the AD-8 availability gate, field updates, and validation. |
| 2026-08-11 | Full regression: 149 passed (up from 135), reproducible on a fresh database. |
| 2026-08-11 | Code review (sonnet, three parallel layers): confirmed and fixed a real bug where `category_id`/`prep_time_minutes` had no upper bound, letting an out-of-int4-range value reach the database and 500 instead of 422ing, reproduced against a live Postgres before and after the fix. Changed `Dish.is_available`'s column-level default from `True` to `False` for defense-in-depth alignment with AD-8 (no migration needed, it was never a `server_default`). Fixed `update_dish`'s log line to report every changed field instead of hardcoding `is_available`. Added 9 tests closing coverage gaps (the AD-8 success path, cross-case category names, direct Role-gate checks on the dish routes, the decimal-places boundary, both int4-overflow cases). One item deferred to `deferred-work.md` (no way to clear `description`/`prep_time_minutes` to null via PATCH); 5 findings dismissed as matching existing, already-accepted codebase patterns. Full regression after patching: 158 passed (up from 149). |
