---
baseline_commit: 6802144cf07e2a0ed80d89c0078405597bbb07d6
epic: 2
story: 1
---

# Story 2.1: Create and Manage Ingredients

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Warehouse Manager or Admin,
I want to create ingredient records,
so that they can be referenced by recipes and tracked in inventory.

**Scope note.** Backend-only, same pattern as Stories 1.1-1.3: this story adds the first real
`inventory` domain router and its own service, with no frontend screen. The Ingredients *list*
screen (the mockup at `key-ingredients.html`) belongs to **FR-17 / Epic 4**, not this story — do
not build a GET/list endpoint or any frontend page here. AC3 ("immediately selectable") is
satisfied once the row exists in the database; nothing in this story's ACs asks for a way to
browse ingredients yet.

## Acceptance Criteria

**AC1 — Create an Ingredient**
Given a name, unit of measure, minimum stock threshold, and optional initial stock, when a
Warehouse Manager or Admin submits the create-ingredient request, then a new Ingredient is
created, defaulting current stock to zero if unspecified (FR-16).

**AC2 — Reject a duplicate name**
Given an Ingredient name that already exists, when creation is attempted, then it is rejected as
a duplicate, with the inline rejection copy pattern UX-DR17 already established for
username/table-number duplicates ("...already exists") (FR-16, UX-DR17).

**AC3 — Immediately usable**
Given a newly created Ingredient, when a Recipe or Stock Movement is being defined (in a later
story), then that Ingredient is immediately selectable, i.e. it exists as a committed row the
moment the create request returns (FR-16).

**AC4 — Wire the new router into the container**
Given the `inventory` domain router does not yet exist, when this story adds it, then
`"api.inventory"` is appended to `container.wire(modules=[...])` in `main.py`, alongside the
existing entries, never replacing them (AD-1).

## Tasks / Subtasks

- [x] **Task 1: Ingredient name uniqueness is case-insensitive** (AC: 2)
  - [x] `backend/data_models/recipe.py`'s `Ingredient.name` already has `unique=True` (case-sensitive,
    from the baseline migration). That alone lets "Tomato" and "tomato" coexist as two rows, which
    silently defeats AC2 and lets a recipe author pick the wrong one. Story 1.3 hit exactly this gap
    for `User.username` and fixed it with a **functional case-insensitive unique index** layered on
    top of the plain column constraint, not replacing it. Do the same here:
    ```python
    from sqlalchemy import Index, text
    # ... inside Ingredient:
    __table_args__ = (
        Index("uq_ingredients_name_lower", text("lower(name)"), unique=True),
    )
    ```
    Model this on `backend/data_models/user.py`'s `User.__table_args__` exactly (same import
    shape, same reasoning comment if you add one).
  - [x] Generate the Alembic revision: `uv run alembic revision --autogenerate -m "Add
    case-insensitive unique index on ingredient name"`. Current head is `f1743862f1b1`; the new
    revision's `down_revision` must be that. **Inspect the generated script before committing** —
    autogenerate sometimes emits unrelated noise; the diff should be exactly one `CREATE UNIQUE
    INDEX` (and its `downgrade` drop).
  - [x] `tests/test_migrations.py::test_migrations_match_the_models` fails if the model and the
    migration ever disagree — run it after generating the revision, not just at the end of the
    story, so any drift is caught immediately.
- [x] **Task 2: Request/response schemas** (AC: 1, 2)
  - [x] Add to `backend/data_models/recipe.py` (Pydantic schemas live alongside the ORM model they
    describe, matching `user.py`'s and `auth.py`'s existing shape, not a separate schemas file):
    ```python
    from decimal import Decimal
    from pydantic import BaseModel, Field, field_validator

    class CreateIngredientRequest(BaseModel):
        """Body of a Warehouse Manager's or Admin's request to create an Ingredient."""

        name: str = Field(min_length=1, max_length=100)
        unit: Unit
        min_stock_threshold: Decimal = Field(ge=0)
        current_stock: Decimal = Field(default=Decimal("0"), ge=0)

        _strip_name = field_validator("name")(_strip_and_require_content)

    class IngredientResponse(BaseModel):
        """Body of any inventory endpoint response describing an Ingredient."""

        model_config = {"from_attributes": True}

        id: int
        name: str
        unit: Unit
        current_stock: Decimal
        min_stock_threshold: Decimal
        created_at: datetime
        updated_at: datetime
    ```
  - [x] `_strip_and_require_content` (blank-after-strip rejection) already exists in
    `backend/data_models/user.py`. It is not underscore-private in the Python sense, just
    module-scoped by convention; importing it (`from .user import _strip_and_require_content`) is
    cheaper than duplicating it a second time and keeps the "blank name is rejected" rule defined
    once. Do not copy-paste the function body.
  - [x] Export `CreateIngredientRequest` and `IngredientResponse` from
    `backend/data_models/__init__.py`'s import list and `__all__`, next to the existing
    `Ingredient, RecipeIngredient, Unit` line.
  - [x] `min_stock_threshold` and `current_stock` are `Numeric(10, 3)` columns; `ge=0` on both
    matches AD-16's stock-can-go-negative rule being about *consumption/waste*, not about a
    Warehouse Manager typing a negative number when first registering an Ingredient. Reject
    negative input here rather than letting Postgres silently accept it.
- [x] **Task 3: `DuplicateIngredientNameError`** (AC: 2)
  - [x] Add to `backend/exceptions/__init__.py`, as a `ConflictError` subclass (not a new base, the
    existing `_conflict_error_handler` in `exceptions/handlers.py` already maps any `ConflictError`
    to a 409 and needs no new registration):
    ```python
    class DuplicateIngredientNameError(ConflictError):
        """Raised when creating an Ingredient with a name that already exists.

        Compared case-insensitively (see the functional index on ingredients.name).
        """

        detail = "That ingredient name already exists"
    ```
- [x] **Task 4: `InventoryService`** (AC: 1, 2, 3)
  - [x] New file `backend/services/inventory_service.py`, modeled directly on
    `backend/services/user_service.py`'s `create_user` (case-insensitive duplicate check, then
    insert, then a race-losing `IntegrityError` fallback caught and translated to the same 409):
    ```python
    class InventoryService:
        """Creates and manages Ingredient records.

        Config-free, registered as a container-level Factory with only the
        logger injected, matching UserService's shape.
        """

        def __init__(self, logger: Any) -> None:
            self._logger = logger

        async def create_ingredient(
            self, db: AsyncSession, actor: User, payload: CreateIngredientRequest
        ) -> Ingredient:
            """Create a new Ingredient record.

            Args:
                db: The active database session.
                actor: The Warehouse Manager or Admin performing the creation,
                    used only for logging.
                payload: The submitted name, unit, threshold, and initial stock.

            Returns:
                The newly created Ingredient.

            Raises:
                DuplicateIngredientNameError: If the name already exists,
                    compared without regard to case.
            """
            existing = await db.execute(
                select(Ingredient).where(func.lower(Ingredient.name) == payload.name.lower())
            )
            if existing.scalar_one_or_none() is not None:
                self._logger.warning(
                    "Ingredient creation rejected by user_id={}: name={} already exists",
                    actor.id, payload.name,
                )
                raise DuplicateIngredientNameError()

            ingredient = Ingredient(
                name=payload.name,
                unit=payload.unit,
                current_stock=payload.current_stock,
                min_stock_threshold=payload.min_stock_threshold,
            )
            db.add(ingredient)
            try:
                await db.commit()
            except IntegrityError as exc:
                await db.rollback()
                self._logger.warning(
                    "Ingredient creation rejected by user_id={}: name={} already exists "
                    "(lost the race)",
                    actor.id, payload.name,
                )
                raise DuplicateIngredientNameError() from exc
            await db.refresh(ingredient)
            self._logger.info(
                "Ingredient created by user_id={}: ingredient_id={} name={} unit={}",
                actor.id, ingredient.id, ingredient.name, ingredient.unit.value,
            )
            return ingredient
    ```
  - [x] `actor` here is a Warehouse Manager *or* Admin, unlike `UserService`'s Admin-only actor.
    Keep the parameter named `actor` and typed `User` for consistency, the log line just prints
    whichever Role it turns out to be (`actor.role.value`, matching the pattern, not hardcoded
    "admin_id=").
- [x] **Task 5: Register in the container** (AC: 1)
  - [x] `backend/container.py`: add
    ```python
    inventory_service = providers.Factory(
        InventoryService,
        logger=logging,
    )
    ```
    next to `user_service`, same shape (config-free, logger-only).
- [x] **Task 6: `api/inventory.py` router** (AC: 1, 2, 4)
  - [x] New file `backend/api/inventory.py`, modeled on `api/admin.py`'s structure exactly: its own
    `APIRouter(prefix="/api/inventory", tags=["inventory"])`, a module-level `Dep` alias, its own
    `_ERROR_DESCRIPTIONS` dict, `error_responses()` from `api/responses.py` (do not write a new
    `_errors()` helper, that was Story 1.3's review finding and `error_responses()` is the fix):
    ```python
    InventoryWriteDep = Annotated[
        User, Depends(require_role(UserRole.admin, UserRole.warehouse_manager))
    ]

    _ERROR_DESCRIPTIONS = {
        401: "No valid session cookie was supplied",
        403: "Authenticated, but the caller's Role is neither admin nor warehouse_manager",
        409: "An ingredient with this name already exists",
    }

    @router.post(
        "/ingredients",
        response_model=IngredientResponse,
        status_code=201,
        responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 409),
    )
    @inject
    async def create_ingredient(
        payload: CreateIngredientRequest,
        actor: InventoryWriteDep,
        db: SessionDep,
        inventory_service: InventoryService = Depends(Provide[Container.inventory_service]),
    ) -> Ingredient:
        return await inventory_service.create_ingredient(db, actor, payload)
    ```
    `require_role(UserRole.admin, UserRole.warehouse_manager)` is the existing `*roles` signature
    (`api/dependencies.py`), no changes needed there, this is the first route to pass it more than
    one Role.
  - [x] `backend/api/router.py`: add `from api.inventory import router as inventory_router` and
    `router.include_router(inventory_router)`, next to the existing `include_router` calls.
  - [x] `backend/main.py`: append `"api.inventory"` to `container.wire(modules=[...])` — **append,
    never replace the list** (AD-1, AC4).
- [x] **Task 7: Tests**
  - [x] New file `backend/tests/test_inventory.py`, mirroring `tests/test_admin.py`'s style
    (`# Arrange`/`# Act`/`# Assert`, no docstrings, per the Testing convention). Cover:
    - A Warehouse Manager can create an Ingredient; the response is 201 with the submitted fields.
    - An Admin can also create an Ingredient (both Roles permitted, AC1).
    - Omitting `current_stock` defaults it to `0` (AC1).
    - Creating with a name that already exists (same case) is rejected 409.
    - Creating with a name that differs only in case (`"Tomato"` vs `"tomato"`) is also rejected
      409 — this is the one case a naive case-sensitive check would miss, and the whole reason
      Task 1 exists.
    - A Cook or Waiter attempting to create an Ingredient gets 403 (Role gate, NFR-2).
    - An unauthenticated request gets 401.
    - A negative `min_stock_threshold` or `current_stock` is rejected 422.
    - A blank (or whitespace-only) name is rejected 422.
  - [x] Full regression: `uv run pytest` from `backend/`. This story touches `container.py`,
    `main.py`, `api/router.py`, `data_models/__init__.py`, `exceptions/__init__.py`, all shared by
    every existing backend test; the migration change is also covered by
    `tests/test_migrations.py`, which already runs as part of the full suite.

### Review Findings

Code review 2026-08-11 (three parallel adversarial layers on sonnet: Blind Hunter, Edge Case
Hunter, Acceptance Auditor). The Decimal-bound claim below was reproduced empirically (a real
request against a live Postgres) before being patched, not accepted from the reviewer's reasoning
alone.

- [x] [Review][Patch] CONFIRMED: a `min_stock_threshold`/`current_stock` value with more digits than the `Numeric(10, 3)` column allows 500s instead of 422 [backend/data_models/recipe.py] — Neither `Decimal` field had `max_digits`/`decimal_places`, so Pydantic accepted `"12345678901.123"` and the request reached the database, where it raised an unhandled `asyncpg.NumericValueOutOfRangeError` (a raw `DBAPIError`, not an `IntegrityError`, so the existing duplicate-name fallback never caught it). Reproduced directly against Postgres before fixing. Fixed by adding `max_digits=10, decimal_places=3` to both fields, matching the column exactly. Regression test added: `test_min_stock_threshold_exceeding_the_column_precision_is_rejected`.
- [x] [Review][Patch] The new Alembic migration had no docstring explaining that it fails on pre-existing case-duplicate rows [backend/alembic/versions/daca523f69f5_...py] — The identical precedent migration (`f1743862f1b1`, Story 1.3's username fix) documents this tradeoff explicitly in its own docstring ("this fails if two existing rows already differ only by ... case. That is correct... reconciled by hand before upgrading"). This migration was missing the equivalent note, which reviewers read as an unacknowledged deploy risk even though the behavior itself is the same accepted tradeoff. Fixed by adding the matching docstring, no behavior change.
- [x] [Review][Patch] The cross-module import of `_strip_and_require_content` had no comment explaining the leading underscore is a convention, not enforcement [backend/data_models/recipe.py] — a reader of `recipe.py` alone (without this story file) would reasonably flag importing an underscore-prefixed name from another module as a real API violation. This was already a deliberate, documented decision in this story's own Task 2 notes; the code itself just didn't say so. Fixed with a short comment at the import.
- [x] [Review][Dismiss] Blanket `except IntegrityError` treats any integrity violation as a duplicate name — matches `UserService.create_user`'s identical, already-accepted pattern verbatim; not a new risk this story introduces.
- [x] [Review][Dismiss] `func.lower()` (Postgres) vs. Python's `str.lower()` can disagree for some non-ASCII casing (e.g. Turkish dotless i) — matches `User.username`'s identical existing design (same app-side pre-check + DB-side functional index shape); not a new risk this story introduces.
- [x] [Review][Dismiss] The pre-check `SELECT` before insert costs an extra round trip on every request — matches `UserService.create_user`'s identical, already-accepted shape.
- [x] [Review][Dismiss] `_ERROR_DESCRIPTIONS[403]`'s wording has to be hand-kept in sync with the `require_role(...)` call — matches `api/admin.py`'s identical existing pattern.
- [x] [Review][Dismiss] The success log line dereferences `ingredient.unit.value` with no guard — `unit` is a required, Pydantic-validated `Unit` enum member by the time this line runs; there is no reachable path where `.value` is unsafe here.
- [x] [Review][Dismiss] No test asserts the DB-level index (vs. the ORM-level `Index` declaration) is what actually enforces uniqueness — matches the existing test suite's practice for `User.username`'s identical index; not a new gap.
- [x] [Review][Dismiss] No test for `name` exceeding its 100-character `max_length` — pure framework-guaranteed Pydantic validation with no custom logic behind it, consistent with the existing suite not testing this for `username`'s identical bound either.

## Dev Notes

### Architecture compliance

- **AD-1** (composition root, `providers.Resource`/`providers.Factory` via the container): followed
  exactly, `InventoryService` is config-free like `UserService`, so a plain `providers.Factory` with
  only the logger, no `providers.Resource` needed.
- **NFR-2** ("no mutating action executes without an authenticated session carrying a Role permitted
  for that action"): enforced via `require_role(UserRole.admin, UserRole.warehouse_manager)`, the
  same seam every other protected route uses, layered on `CurrentUserDep` (`api/dependencies.py`).
  Nothing new to build here, this is the first *caller* to pass `require_role` more than one Role,
  which its existing `*roles: UserRole` signature already supports untouched.
- **Design pattern to name** (per this project's academic-context grading convention): this story
  is a second, independent instance of the exact Repository-behind-a-service shape `UserService`
  established in Story 1.3 (service methods do the querying, the router stays thin). Naming it in
  the PR description ("InventoryService follows the same Repository-style service pattern as
  UserService") is the traceable move, not a new pattern.

### Existing files this story modifies

- `backend/data_models/recipe.py` — currently ORM-only (`Unit`, `Ingredient`, `RecipeIngredient`),
  no Pydantic schemas yet. This story adds `CreateIngredientRequest`/`IngredientResponse` here and
  a `__table_args__` index to `Ingredient`, following `user.py`'s precedent of colocating a model's
  ORM class with its own request/response schemas in the same file.
- `backend/data_models/__init__.py` — add the two new schema names to both the import block and
  `__all__`.
- `backend/exceptions/__init__.py` — add `DuplicateIngredientNameError(ConflictError)`. No change
  needed in `exceptions/handlers.py`: the existing `_conflict_error_handler` already maps the whole
  `ConflictError` family to 409.
- `backend/container.py` — add `inventory_service` as a `providers.Factory`, same shape as
  `user_service`.
- `backend/main.py` — append `"api.inventory"` to the `container.wire(modules=[...])` list (currently
  `["api.auth", "api.dependencies", "api.admin", "api.websocket"]`).
- `backend/api/router.py` — add and mount the new `inventory_router`.
- `backend/api/dependencies.py` — **read, not modified.** `require_role(*roles: UserRole)` already
  accepts multiple Roles; this story is the first caller to actually pass more than one.

### New files

- `backend/api/inventory.py`
- `backend/services/inventory_service.py`
- `backend/tests/test_inventory.py`
- `backend/alembic/versions/<hash>_add_case_insensitive_unique_index_on_ingredient_name.py`
  (generated by `alembic revision --autogenerate`, not hand-written)

### Project Structure Notes

No deviation from the established five-folder backend layout (`api/`, `services/`, `clients/`,
`data_models/`, `exceptions/`). No new top-level folder, no `clients/` changes (nothing here talks
to an external service).

### Testing

- Backend only, `uv run pytest` from `backend/`. No frontend changes in this story.
- Use the existing `client` and `db_session` fixtures from `tests/conftest.py`; no new fixtures
  needed. Create test Users the same way `test_admin.py`/`test_websocket.py` do (`AuthService.hash_password`
  for the password, never `bcrypt.hashpw` directly).
- Run `tests/test_migrations.py` explicitly right after generating the Alembic revision (Task 1),
  not only at the end, so a schema/model mismatch is caught while the migration is still fresh in
  context.

### References

- Story source: [Source: _bmad-output/planning-artifacts/epics.md#Story 2.1]
- FR: [Source: _bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md#FR-16]
- UX-DR17 (inline rejection microcopy convention): [Source: _bmad-output/planning-artifacts/epics.md,
  Design Requirements list] — "duplicate username/table-number/ingredient-name... rejected inline"
- AD-1 (composition root / container wiring): [Source: ARCHITECTURE-SPINE.md#AD-1]
- AD-16 (stock never clamped at zero, consumption/waste path only): [Source: ARCHITECTURE-SPINE.md#AD-16]
- FR-17 (Ingredients list/view) is explicitly **out of scope**, it belongs to Epic 4: [Source:
  _bmad-output/planning-artifacts/epics.md#Epic 4: Warehouse Inventory Operations & Low-Stock Alerts]
- Precedent this story copies: Story 1.3's case-insensitive-username fix and its three-places-must-
  agree lesson (trap 11): [Source: _bmad-output/project-context.md, trap 11] — apply the same
  functional-index + service-side `func.lower()` shape to `Ingredient.name`.
- Precedent for the service/router shape: [Source: backend/services/user_service.py],
  [Source: backend/api/admin.py]
- `require_role`'s existing multi-Role support (`*roles: UserRole`), unused until now: [Source:
  backend/api/dependencies.py]

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (Claude Code, bmad-dev-story workflow)

### Debug Log References

- Followed the story's own snippets as written; each matched the installed code on the first try
  (`require_role`'s `*roles: UserRole` signature already accepted two Roles with no change,
  `error_responses()` needed no new wording beyond a fresh `_ERROR_DESCRIPTIONS` dict, and
  `_strip_and_require_content` imported cleanly from `data_models/user.py` with no circular-import
  issue).
- `uv run alembic revision --autogenerate -m "..."` produced exactly one operation
  (`CREATE UNIQUE INDEX uq_ingredients_name_lower ON ingredients (lower(name))`, plus its symmetric
  `downgrade`), no unrelated autogenerate noise. `down_revision` correctly picked up the existing
  head (`f1743862f1b1`) automatically.
- Ran `tests/test_migrations.py` immediately after generating the revision, per the story's own
  instruction, before writing any other code: passed on the first try, confirming the model and the
  migration agreed from the start.

### Completion Notes List

- All 4 acceptance criteria satisfied: AC1 (create, defaulting `current_stock` to zero), AC2
  (duplicate rejection, verified both same-case and cross-case via the new functional index), AC3
  (the created row is committed and fetchable by the time the response returns, no separate
  mechanism needed), AC4 (`"api.inventory"` appended, not substituted, in `main.py`'s
  `container.wire(modules=[...])`).
- `InventoryService.create_ingredient` and `api/inventory.py`'s `create_ingredient` route are a
  second, independent instance of the Repository-style service pattern `UserService`/`api/admin.py`
  established in Story 1.3 (service does the querying and the duplicate check, the router stays
  thin) - named here per this project's pattern-traceability convention, not a new pattern.
- 11 new tests in `test_inventory.py`, covering both Roles permitted to create (warehouse_manager,
  admin), both Roles rejected (cook, waiter), unauthenticated rejection, the default-to-zero case,
  same-case and cross-case duplicate rejection, and 422 on a negative threshold, negative stock, and
  a blank name.
- Full regression: 134 passed (up from 123), zero regressions, on the first full run after
  implementation.

### File List

**Added**

- `backend/api/inventory.py`
- `backend/services/inventory_service.py`
- `backend/tests/test_inventory.py`
- `backend/alembic/versions/daca523f69f5_add_case_insensitive_unique_index_on_.py`

**Modified**

- `backend/data_models/recipe.py` (added `Ingredient.__table_args__`'s case-insensitive unique
  index; added `CreateIngredientRequest`/`IngredientResponse`)
- `backend/data_models/__init__.py` (exported the two new schemas)
- `backend/exceptions/__init__.py` (added `DuplicateIngredientNameError(ConflictError)`)
- `backend/container.py` (added `inventory_service` Factory)
- `backend/main.py` (appended `"api.inventory"` to `container.wire(modules=[...])`)
- `backend/api/router.py` (included the new inventory router)

**Confirmed unchanged**: `backend/api/dependencies.py` (`require_role`'s existing `*roles` signature
needed no change), `backend/exceptions/handlers.py` (the existing `_conflict_error_handler` already
covers the whole `ConflictError` family), `backend/api/responses.py`, `pyproject.toml`/`uv.lock`
(no new dependency).

## Change Log

| Date | Change |
|---|---|
| 2026-08-11 | Added the case-insensitive unique index on `Ingredient.name` (`uq_ingredients_name_lower`), mirroring Story 1.3's fix for `User.username`, plus its Alembic revision (`daca523f69f5`, down_revision `f1743862f1b1`). |
| 2026-08-11 | Added `CreateIngredientRequest`/`IngredientResponse` to `backend/data_models/recipe.py`, reusing `data_models/user.py`'s `_strip_and_require_content` validator rather than duplicating it. |
| 2026-08-11 | Added `DuplicateIngredientNameError(ConflictError)` to `backend/exceptions/__init__.py`; no new handler needed, the existing `_conflict_error_handler` covers the whole family. |
| 2026-08-11 | Added `InventoryService.create_ingredient` (`backend/services/inventory_service.py`), modeled on `UserService.create_user`'s case-insensitive duplicate check plus race-losing `IntegrityError` fallback. Registered as a `providers.Factory` in `container.py`. |
| 2026-08-11 | Added the `POST /api/inventory/ingredients` route (`backend/api/inventory.py`), the first route to pass `require_role` more than one Role (`admin`, `warehouse_manager`). Mounted in `api/router.py`; appended `"api.inventory"` to `main.py`'s `container.wire(modules=[...])`. |
| 2026-08-11 | Added `backend/tests/test_inventory.py`: 11 tests covering both permitted Roles, both rejected Roles, unauthenticated rejection, the zero-default, same-case and cross-case duplicate rejection, and validation (negative threshold/stock, blank name). |
| 2026-08-11 | Full regression: 134 passed (up from 123), reproducible on a fresh database. |
| 2026-08-11 | Code review (sonnet, three parallel layers): confirmed and fixed a real bug where a `min_stock_threshold`/`current_stock` value exceeding the `Numeric(10, 3)` column's precision reached the database and 500'd instead of 422'ing, via `max_digits=10, decimal_places=3` on both Pydantic fields, reproduced against a live Postgres before and after the fix. Added a matching docstring to the new Alembic migration (parity with its Story 1.3 precedent) and a clarifying comment on the cross-module validator import. 7 findings dismissed as matching existing, already-accepted codebase patterns (`UserService`/`api/admin.py`/`User.username`'s identical shapes). Full regression after patching: 135 passed (up from 134). |
