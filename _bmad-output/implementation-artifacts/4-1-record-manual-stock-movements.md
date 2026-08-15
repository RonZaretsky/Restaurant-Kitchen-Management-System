---
baseline_commit: d854f63ce210359db305b2fbe7ee45e787423c18
epic: 4
story: 1
---

# Story 4.1: Record Manual Stock Movements

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Warehouse Manager,
I want to log purchase, waste, or adjustment stock movements,
so that inventory stays accurate as things happen outside the kitchen's automatic path.

## Scope note (read first)

**Epic 4's first story, and the first time `Ingredient.current_stock` is ever written to after
creation.** Story 2.1 built `Ingredient` and `POST /api/inventory/ingredients`; nothing since has
touched `current_stock` again. `StockMovement`/`MovementType` (ORM only, no Pydantic schemas) have
existed unused since Story 2.1 too (`backend/data_models/inventory.py`), and the table has existed
in the database since the Story 1.0 baseline migration (`8c7084cec0ff_baseline_schema.py`, lines
103-115) — **no new Alembic migration is needed for this story.**

**This story's frontend targets are two placeholder pages that already exist and are already
routed**, `frontend/src/pages/warehouse/IngredientDetailPage.tsx` and the route
`/warehouse/ingredients/:ingredientId` in `frontend/src/router.tsx` (both wired ahead of content,
the same "route/placeholder before the story that fills it" shape `AlertsPage`/`/warehouse/alerts`
also already has for Story 4.2). This story replaces `IngredientDetailPage.tsx`'s one-line
placeholder with real content. Do **not** touch `router.tsx` or create a new route, both already
exist. Do **not** build the Alerts screen or the shortage banner/red-styling on the stat cards —
those are Story 4.2/4.3, out of scope here (see below).

**`consumption` is a `MovementType` enum member but is never a valid *manual* input.** It is Epic
5's automatic-deduction path (FR-13), not built yet. This story's create-movement request accepts
only `purchase`/`waste`/`adjustment`; a submitted `consumption` is rejected with a 422 (see Task 2).
The movement-history *read* path still returns every `MovementType`, including `consumption`,
unfiltered — no code writes a `consumption` row yet, but the schema/rendering must not assume it
never will (Epic 5 will insert rows through this same table later).

**Explicitly out of scope (Stories 4.2/4.3, not this one):**
- The shortage banner at the top of the mockup ("Stock low: Tomato...").
- Red/"danger" styling on the Current stock stat card when below threshold.
- The Low-Stock Alert derived state, the Alerts nav badge, and the Alerts screen itself.
- Shortage sorting/highlighting on the Ingredients list screen (`IngredientsPage.tsx` stays
  unchanged).
The stat cards themselves (Current stock, Minimum threshold, plain styling) **are** this story's
scope, since the log-movement form needs them and AC1/AC2 need somewhere to observe the result.

**Sign convention (from FR-15/AD-16, not stated explicitly in the epics AC text — read this
before implementing `record_movement`):** the submitted `quantity` is a plain magnitude for
`purchase` (always applied as `+quantity`) and `waste` (always applied as `-quantity`); for
`adjustment` the caller submits the already-signed delta directly (`+2.5` or `-2.5`), since an
adjustment is the one type where the direction itself is the fact being recorded. `current_stock`
is **never floor-capped at zero** on any of the three paths (AD-16): `waste` or a negative
`adjustment` can drive it negative, and the write must not clamp, reject on that basis, or silently
no-op.

## Acceptance Criteria

**AC1 — Purchase increases stock, recorded in the audit trail**
Given a quantity and optional note, when a Warehouse Manager logs a `purchase` movement, then the
Ingredient's current stock increases accordingly and the movement is recorded in the append-only
audit trail (FR-15, NFR-4).

**AC2 — Waste or negative adjustment decreases stock, never floor-capped**
Given a quantity and optional note, when a Warehouse Manager logs a `waste` movement or a negative
`adjustment`, then the Ingredient's current stock decreases accordingly, even if it drives stock
negative, never floor-capped at zero (FR-15, AD-16).

**AC3 — Movement type chip uses a neutral color scheme**
Given a Stock Movement shown on Ingredient detail, when its type is rendered, then the movement
type chip uses a neutral color scheme, deliberately distinct from the status traffic-light
convention (UX-DR14).

## Tasks / Subtasks

- [x] **Task 1: Pydantic schemas for `StockMovement`** (AC: 1, 2)
  - [x] `backend/data_models/inventory.py`, colocated below `StockMovement` (matches
    `recipe.py`'s `Ingredient` → `CreateIngredientRequest`/`IngredientResponse` placement
    convention). Needs `from decimal import Decimal` and
    `from pydantic import BaseModel, Field, model_validator` added to the file's imports (neither
    exists there yet).
    ```python
    class CreateStockMovementRequest(BaseModel):
        """Body of a Warehouse Manager's or Admin's request to log a Stock Movement (FR-15).

        movement_type accepts the full MovementType enum at the field level (no Literal-based
        subset type exists anywhere in this codebase to follow as precedent), but the validator
        below rejects `consumption`: it is Epic 5's automatic path only, never a manually
        submitted value here, mirroring `UpdateRecipeIngredientRequest.at_least_one_field`'s
        validator-rejects-the-disallowed-case shape.

        Sign convention (AD-16, FR-15): quantity is a plain positive magnitude for purchase/waste
        (the direction is implied by movement_type); for adjustment it is the already-signed
        delta the caller wants applied (positive or negative, never zero).
        """

        movement_type: MovementType
        # max_digits/decimal_places match StockMovement.quantity_change's Numeric(10, 3) column
        # exactly (trap 16). No ge/gt bound at the field level: validity depends on
        # movement_type, enforced below.
        quantity: Decimal = Field(max_digits=10, decimal_places=3)
        notes: str | None = None

        @model_validator(mode="after")
        def validate_type_and_quantity(self) -> "CreateStockMovementRequest":
            """Reject consumption, and enforce the sign convention for the other three types.

            Returns:
                This instance, unchanged, if movement_type/quantity are a valid combination.

            Raises:
                ValueError: If movement_type is consumption, if quantity is <= 0 for a
                    purchase/waste movement, or if quantity is exactly 0 for an adjustment.
            """
            if self.movement_type == MovementType.consumption:
                raise ValueError("consumption is recorded automatically and cannot be logged manually")
            if self.movement_type in (MovementType.purchase, MovementType.waste) and self.quantity <= 0:
                raise ValueError("quantity must be greater than zero for a purchase or waste movement")
            if self.movement_type == MovementType.adjustment and self.quantity == 0:
                raise ValueError("quantity must not be zero for an adjustment movement")
            return self


    class StockMovementResponse(BaseModel):
        """Body of any inventory endpoint response describing a Stock Movement.

        Maps 1:1 to StockMovement's own columns (no joined/enriched data), matching
        OrderItemResponse's precedent of returning raw ids (`performed_by`, like `cook_id`)
        rather than a resolved display name — see Dev Notes for why the frontend renders
        `performed_by` as a plain id rather than a name, and why that's a known,
        deliberate gap in this story rather than an oversight.
        """

        model_config = {"from_attributes": True}

        id: int
        ingredient_id: int
        movement_type: MovementType
        quantity_change: Decimal
        reference_id: int | None
        performed_by: int
        timestamp: datetime
        notes: str | None
    ```
    (`datetime` is already imported in this file.)

- [x] **Task 2: Export the new schemas** (AC: 1, 2)
  - [x] `backend/data_models/__init__.py`: extend the existing `from .inventory import
    StockMovement, MovementType` line to also import `CreateStockMovementRequest`,
    `StockMovementResponse`, and add both to `__all__` next to `"StockMovement", "MovementType"`.

- [x] **Task 3: `InventoryService` additions** (AC: 1, 2)
  - [x] `backend/services/inventory_service.py`, three new methods (imports needed:
    `from data_models import CreateStockMovementRequest, MovementType, StockMovement` alongside
    the existing `Ingredient`/`User` import; `from exceptions import IngredientNotFoundError` added
    to the existing `DuplicateIngredientNameError` import).
    ```python
    async def get_ingredient(self, db: AsyncSession, ingredient_id: int) -> Ingredient:
        """Fetch one Ingredient by id, for the Ingredient detail screen's stat cards.

        Args:
            db: The active database session.
            ingredient_id: The id of the Ingredient to fetch.

        Returns:
            The matching Ingredient.

        Raises:
            IngredientNotFoundError: If no Ingredient matches ingredient_id.
        """
        ingredient = await db.get(Ingredient, ingredient_id)
        if ingredient is None:
            raise IngredientNotFoundError()
        return ingredient

    async def list_movements(self, db: AsyncSession, ingredient_id: int) -> Sequence[StockMovement]:
        """List every Stock Movement recorded for an Ingredient, newest first.

        Args:
            db: The active database session.
            ingredient_id: The id of the Ingredient whose history is being read.

        Returns:
            Every Stock Movement for this Ingredient, most recent first.

        Raises:
            IngredientNotFoundError: If no Ingredient matches ingredient_id.
        """
        ingredient = await db.get(Ingredient, ingredient_id)
        if ingredient is None:
            raise IngredientNotFoundError()
        result = await db.execute(
            select(StockMovement)
            .where(StockMovement.ingredient_id == ingredient_id)
            .order_by(StockMovement.timestamp.desc())
        )
        return result.scalars().all()

    async def record_movement(
        self, db: AsyncSession, actor: User, ingredient_id: int, payload: CreateStockMovementRequest
    ) -> StockMovement:
        """Log a manual Stock Movement and update the Ingredient's current stock (AC1/AC2).

        Not a guarded UPDATE (trap 18 does not apply here): nothing about the Ingredient's own
        state blocks a movement the way an OrderItem's status blocks an edit, this is a plain
        read-modify-write plus an append-only insert, both committed in one transaction (AD-16,
        NFR-4). purchase/waste apply as +/-quantity; adjustment applies payload.quantity as
        already signed. current_stock is never floor-capped at zero (AD-16): a waste or negative
        adjustment is applied in full even past zero.

        Args:
            db: The active database session.
            actor: The Warehouse Manager or Admin logging the movement.
            ingredient_id: The id of the Ingredient the movement applies to.
            payload: The submitted movement type, quantity, and optional note.

        Returns:
            The newly recorded Stock Movement.

        Raises:
            IngredientNotFoundError: If no Ingredient matches ingredient_id.
        """
        ingredient = await db.get(Ingredient, ingredient_id)
        if ingredient is None:
            self._logger.warning(
                "Stock movement rejected by user_id={}: ingredient_id={} not found",
                actor.id,
                ingredient_id,
            )
            raise IngredientNotFoundError()

        delta = -payload.quantity if payload.movement_type == MovementType.waste else payload.quantity
        ingredient.current_stock = ingredient.current_stock + delta

        movement = StockMovement(
            ingredient_id=ingredient_id,
            movement_type=payload.movement_type,
            quantity_change=delta,
            performed_by=actor.id,
            notes=payload.notes,
        )
        db.add(movement)
        await db.commit()
        await db.refresh(movement)
        await db.refresh(ingredient)
        self._logger.info(
            "Stock movement recorded by user_id={}: ingredient_id={} type={} quantity_change={} new_stock={}",
            actor.id,
            ingredient_id,
            payload.movement_type.value,
            delta,
            ingredient.current_stock,
        )
        return movement
    ```
    No `IntegrityError`/rollback handling needed here (unlike `create_ingredient`): nothing this
    method inserts or updates has a unique constraint to violate. `Sequence` is already imported
    at the top of this file (used by `list_ingredients`'s return type).
  - [x] **Known accepted risk, not a task to build:** `ingredient.current_stock + delta` is not
    itself bounded against `Ingredient.current_stock`'s own `Numeric(10, 3)` ceiling (only the
    individual `quantity` field is bounded, per Task 1). A value that pushes an already
    near-the-ceiling `current_stock` over it would surface as a raw `asyncpg.NumericValueOutOfRangeError`
    (an unhandled 500) rather than a clean 422, the same class of gap trap 16's Story 3.2 extension
    describes for `Order.total_amount`. Not fixed here: no AC asks for it, and
    `CreateIngredientRequest.current_stock` already carries the same unbounded-arithmetic gap
    today. Leaving this documented rather than silently reintroducing an unflagged instance of a
    known trap.

- [x] **Task 4: `api/inventory.py` routes** (AC: 1, 2, 3)
  - [x] New imports: `Path` from `fastapi`; `_INT4_MAX` from `data_models.menu` (same import
    orders.py/menu.py already use); `CreateStockMovementRequest`, `StockMovement`,
    `StockMovementResponse` added to the existing `data_models` import line.
  - [x] New path type, same shape as `api/menu.py`'s `IngredientIdPath`/`api/orders.py`'s
    `ItemIdPath` (each router file defines its own copy, no shared cross-router import exists in
    this codebase for these):
    ```python
    IngredientIdPath = Annotated[int, Path(gt=0, le=_INT4_MAX)]
    ```
  - [x] Three new routes, full docstrings (Args/Returns/Raises) matching every existing route in
    this file:
    ```python
    @router.get(
        "/ingredients/{ingredient_id}",
        response_model=IngredientResponse,
        responses=error_responses(_DETAIL_ERROR_DESCRIPTIONS, 401, 403, 404),
    )
    @inject
    async def get_ingredient(
        ingredient_id: IngredientIdPath,
        actor: InventoryReadDep,
        db: SessionDep,
        inventory_service: InventoryService = Depends(Provide[Container.inventory_service]),
    ) -> Ingredient:
        return await inventory_service.get_ingredient(db, ingredient_id)


    @router.get(
        "/ingredients/{ingredient_id}/movements",
        response_model=list[StockMovementResponse],
        responses=error_responses(_DETAIL_ERROR_DESCRIPTIONS, 401, 403, 404),
    )
    @inject
    async def list_movements(
        ingredient_id: IngredientIdPath,
        actor: InventoryReadDep,
        db: SessionDep,
        inventory_service: InventoryService = Depends(Provide[Container.inventory_service]),
    ) -> list[StockMovement]:
        return await inventory_service.list_movements(db, ingredient_id)


    @router.post(
        "/ingredients/{ingredient_id}/movements",
        response_model=StockMovementResponse,
        status_code=201,
        responses=error_responses(_MOVEMENT_ERROR_DESCRIPTIONS, 401, 403, 404, 422),
    )
    @inject
    async def record_movement(
        ingredient_id: IngredientIdPath,
        payload: CreateStockMovementRequest,
        actor: InventoryWriteDep,
        db: SessionDep,
        inventory_service: InventoryService = Depends(Provide[Container.inventory_service]),
    ) -> StockMovement:
        return await inventory_service.record_movement(db, actor, ingredient_id, payload)
    ```
    (Write out full docstrings per this project's convention; omitted above for brevity, mirror
    `create_ingredient`'s Args/Returns/Raises shape exactly, `Raises: IngredientNotFoundError:
    Propagated from inventory_service, handled globally as a 404, ...`.)
    `_DETAIL_ERROR_DESCRIPTIONS` and `_MOVEMENT_ERROR_DESCRIPTIONS`: new local dicts extending the
    existing `_ERROR_DESCRIPTIONS`' shape, e.g.
    `_DETAIL_ERROR_DESCRIPTIONS = {**_ERROR_DESCRIPTIONS, 404: "No ingredient matches the given id"}`
    with `409` dropped (not applicable here) — or two fresh dicts if that reads cleaner, dev's
    call, just keep every declared status documented per trap 8(a).
  - [x] No `container.py` or `main.py` change: `inventory_service` and `"api.inventory"` are
    already registered/wired.

- [x] **Task 5: Backend tests** (AC: 1, 2, 3 — read `backend/tests/test_inventory.py` in full
  first, extend it, do not create a second file)
  - [x] Purchase increases `current_stock`, response reflects it (AC1).
  - [x] Admin can also log a purchase (mirrors `test_admin_can_also_create_an_ingredient`).
  - [x] Waste decreases `current_stock` (AC2).
  - [x] Negative adjustment decreases `current_stock` (AC2).
  - [x] Positive adjustment increases `current_stock`.
  - [x] **Waste can drive `current_stock` negative, not floor-capped** — start an Ingredient at a
    small `current_stock` (e.g. `"2.000"`), log `waste` with `quantity="5.000"`, assert the
    response's `current_stock` (via a follow-up `GET .../ingredients/{id}`) is `"-3.000"`, not
    `"0.000"` (AC2/AD-16, this is the one test in this story that would pass under a wrong,
    floor-capped implementation if not written carefully — assert the exact negative value, not
    just "did not error").
  - [x] A negative adjustment can drive `current_stock` negative too, same assertion shape
    (AD-16's second path).
  - [x] The movement is recorded in the audit trail: after a purchase, `GET
    .../ingredients/{id}/movements` includes a row with `movement_type: "purchase"`,
    `quantity_change` matching the applied delta, `notes` matching what was submitted, and
    `performed_by` matching the acting user's id (AC1/NFR-4).
  - [x] `waste`'s `quantity_change` in the audit trail is stored **negative** (not the positive
    magnitude submitted) — the append-only row must reflect the actual signed delta applied
    (NFR-4: "traceable to exactly one Stock Movement record").
  - [x] Submitting `movement_type: "consumption"` is rejected 422.
  - [x] Submitting `quantity: "0"` for `adjustment` is rejected 422.
  - [x] Submitting a non-positive `quantity` for `purchase` is rejected 422; same for `waste`.
  - [x] A `quantity` exceeding the column's precision (mirrors
    `test_min_stock_threshold_exceeding_the_column_precision_is_rejected`'s exact shape, verify
    against a live Postgres per the Testing section's own standing rule, don't just reason about
    the Pydantic bound) is rejected 422.
  - [x] Logging a movement against a nonexistent `ingredient_id` is rejected 404.
  - [x] Cook cannot log a movement (403) — read-only role for this write.
  - [x] Waiter cannot log a movement (403).
  - [x] Unauthenticated request to log a movement is rejected 401.
  - [x] `GET /api/inventory/ingredients/{id}` returns 200 for an existing Ingredient, 404 for a
    nonexistent one.
  - [x] `GET .../movements` returns `[]` for an Ingredient with no movements yet, and returns rows
    newest-first when more than one exists (create two movements, assert order in the response).
  - [x] Cook can read a single Ingredient and its movement history (200) — same read tier as
    `list_ingredients` already grants Cook.
  - [x] Waiter cannot read a single Ingredient or its movement history (403).
  - [x] Unauthenticated requests to both new GET routes are rejected 401.
  - [x] Omitting `notes` on a create-movement request stores it as `null` (mirrors
    `test_omitting_current_stock_defaults_to_zero`'s "omitted optional field" shape).
  - [x] Full regression: `uv run pytest` from `backend/`.

- [x] **Task 6: Frontend — `types/inventory.ts`** (AC: 1, 2, 3)
  - [x] Add:
    ```typescript
    export type MovementType = "purchase" | "consumption" | "waste" | "adjustment";

    /**
     * Mirrors backend/data_models/inventory.py's StockMovementResponse.
     * `quantity_change` stays a string (Decimal-as-string, matching
     * Ingredient.current_stock's own precedent), already signed by the backend
     * (e.g. "-0.800" for a waste movement).
     */
    export interface StockMovement {
      id: number;
      ingredient_id: number;
      movement_type: MovementType;
      quantity_change: string;
      reference_id: number | null;
      performed_by: number;
      timestamp: string;
      notes: string | null;
    }
    ```

- [x] **Task 7: Frontend — `services/inventoryService.ts`** (AC: 1, 2, 3)
  - [x] Three new exports, following `useOrderForTable`/`useOrderItems`/`useAddOrderItem`'s exact
    shapes (nullable/optional id param, `enabled` gate, `retry: false` on queries,
    `onSettled`-based invalidation on the mutation):
    ```typescript
    interface CreateStockMovementPayload {
      movement_type: "purchase" | "waste" | "adjustment";
      quantity: string;
      notes?: string | null;
    }

    const ingredientQueryKey = (id: number | null) => ["inventory", "ingredients", id] as const;
    const movementsQueryKey = (id: number | null) => ["inventory", "ingredients", id, "movements"] as const;

    export function useIngredient(ingredientId: number | null): UseQueryResult<Ingredient, Error> {
      return useQuery({
        queryKey: ingredientQueryKey(ingredientId),
        queryFn: () => apiRequest<Ingredient>(`/api/inventory/ingredients/${ingredientId}`),
        enabled: ingredientId !== null,
        retry: false,
      });
    }

    export function useStockMovements(ingredientId: number | null): UseQueryResult<StockMovement[], Error> {
      return useQuery({
        queryKey: movementsQueryKey(ingredientId),
        queryFn: () => apiRequest<StockMovement[]>(`/api/inventory/ingredients/${ingredientId}/movements`),
        enabled: ingredientId !== null,
        retry: false,
      });
    }

    export function useRecordStockMovement(
      ingredientId: number | null,
    ): UseMutationResult<StockMovement, Error, CreateStockMovementPayload> {
      const queryClient = useQueryClient();
      return useMutation({
        mutationFn: (payload: CreateStockMovementPayload) =>
          apiRequest<StockMovement>(`/api/inventory/ingredients/${ingredientId}/movements`, {
            method: "POST",
            body: JSON.stringify(payload),
          }),
        onSettled: () => {
          void queryClient.invalidateQueries({ queryKey: ingredientQueryKey(ingredientId) });
          void queryClient.invalidateQueries({ queryKey: movementsQueryKey(ingredientId) });
          void queryClient.invalidateQueries({ queryKey: ["inventory", "ingredients"] });
        },
      });
    }
    ```
    Three invalidations on settle, not just one: `current_stock` changed, which is cached under
    the single-ingredient key, the movements-list key, *and* the plain ingredients-list key
    `IngredientsPage.tsx` already reads (`INGREDIENTS_QUERY_KEY` in this same file) — a Warehouse
    Manager who logs a movement and then navigates back to the list must not see stale stock.
    `onSettled`, not `onSuccess`, matching `useEditOrderItem`'s documented reasoning: a rejected
    submission (422) means nothing changed here, so the extra invalidation is a harmless no-op,
    but the *pattern* stays consistent across this codebase's mutations.

- [x] **Task 8: Frontend — `components/inventory/MovementTypeChip.tsx`** (AC: 3, new file/folder)
  - [x] New folder `components/inventory/`, mirroring `components/orders/`. Shape mirrors
    `OrderItemStatusBadge` (`size="small"`, `label`, `color`), no icon (EXPERIENCE.md's Movement
    type chip pattern: "No icon required").
    ```tsx
    import Chip from "@mui/material/Chip";
    import type { MovementType } from "../../types/inventory";

    const LABELS: Record<MovementType, string> = {
      purchase: "Purchase",
      consumption: "Consumption",
      waste: "Waste",
      adjustment: "Adjustment",
    };

    // Deliberately none of "success"/"warning"/"error": those three are
    // OrderItemStatusBadge's traffic-light trio (ready/in_preparation/cancelled).
    // A movement type is a category, not an urgency signal (AC3/UX-DR14), so this
    // reuses MUI's three remaining semantic Chip colors plus "default" instead —
    // also keeps this theme-aware in dark mode, unlike the mockup's raw light-mode
    // hex swatches, which this deliberately does not copy verbatim (see Dev Notes).
    const COLORS: Record<MovementType, "primary" | "info" | "default" | "secondary"> = {
      purchase: "primary",
      consumption: "info",
      waste: "default",
      adjustment: "secondary",
    };

    /**
     * The Stock Movement type chip (AC3, UX-DR14): a neutral-palette MUI Chip, deliberately
     * distinct from OrderItemStatusBadge's traffic-light convention, since a movement's type is a
     * category, not an urgency signal.
     *
     * @param type - The Stock Movement's type.
     * @returns The type Chip.
     */
    export function MovementTypeChip({ type }: { type: MovementType }) {
      return <Chip size="small" label={LABELS[type]} color={COLORS[type]} />;
    }
    ```

- [x] **Task 9: Frontend — `IngredientDetailPage.tsx`** (AC: 1, 2, 3 — replace the placeholder)
  - [x] Read the current one-line placeholder in full before editing (it is a `Typography` only,
    nothing to preserve).
  - [x] Route param handling mirrors `TableOrderDetailPage.tsx`'s exact `parseRouteId` shape (a
    private, unexported copy in this file too — this codebase duplicates this helper per page
    rather than sharing it, see `IngredientsPage.tsx`'s own `parseNonNegativeAmount` for the same
    duplication precedent):
    ```typescript
    const { ingredientId } = useParams<{ ingredientId: string }>();
    const parsedIngredientId = parseRouteId(ingredientId);
    ```
    An invalid/missing route param and a genuine backend 404 (valid numeric id, no matching row)
    both render the same inline "not found" message — do not fetch at all when
    `parsedIngredientId === null` (`enabled` gate already handles this via
    `useIngredient`/`useStockMovements`'s own `enabled: ingredientId !== null`).
  - [x] Two parsing helpers, page-local (not shared/exported), following
    `IngredientsPage.tsx`'s `parseNonNegativeAmount` shape:
    ```typescript
    /** A positive decimal amount, for purchase/waste (magnitude only, direction is implied). */
    function parsePositiveAmount(raw: string): string | null {
      const trimmed = raw.trim();
      if (!/^\d+(\.\d+)?$/.test(trimmed) || Number(trimmed) === 0) {
        return null;
      }
      return trimmed;
    }

    /** An optionally-signed, non-zero decimal amount, for adjustment. */
    function parseAdjustmentAmount(raw: string): string | null {
      const trimmed = raw.trim();
      if (!/^-?\d+(\.\d+)?$/.test(trimmed) || Number(trimmed) === 0) {
        return null;
      }
      return trimmed;
    }
    ```
    Both regexes fully constrain the string to digits (plus an optional leading `-` on the second)
    before any `Number()` call, so the `Number(trimmed) === 0` check never runs against an
    unvalidated string (trap 19's own pattern: never call bare `Number()` on unvalidated input).
  - [x] Type select offers exactly **Purchase / Waste / Adjustment** (three `MenuItem`s, matching
    the mockup) — Consumption is never an option, matching Task 1's server-side rejection.
    Quantity `TextField` label includes the ingredient's unit once loaded (`` `Quantity
    (${ingredient.unit})` ``, matching the mockup's "Quantity (kg)"). Note `TextField` is
    `multiline`, optional. Submit button disabled until: type selected, quantity parses per the
    type's own parser (`parsePositiveAmount` for purchase/waste, `parseAdjustmentAmount` for
    adjustment), and the mutation is not already pending — re-check the full predicate in the
    submit handler itself, not just the button's `disabled`, per this codebase's standing rule
    (`IngredientsPage.tsx`'s `handleCreate` is the precedent for this exact re-check).
  - [x] On successful submit: clear the form (type/quantity/note reset), matching
    `IngredientsPage.tsx`'s `onSuccess` clear-the-form precedent.
  - [x] Stat cards: Current stock, Minimum threshold, plain MUI `Card`/`Paper` (no danger/red
    styling — that's Story 4.3's job on the *list* screen and Story 4.2/4.3's job on this stat
    card, see Scope note). Render the raw `current_stock`/`min_stock_threshold` strings plus
    `ingredient.unit`, same as `IngredientsPage.tsx`'s table cells already do (no numeric
    reformatting).
  - [x] Movement history: a `Table` with columns Type (`MovementTypeChip`) / Quantity / Recorded
    by / Note / When, newest first (the backend already orders this way, no client-side re-sort
    needed). Quantity cell: `` `${movement.quantity_change.startsWith("-") ? "" : "+"}${movement.quantity_change} ${ingredient.unit}` ``,
    colored via MUI `Typography` `color="success.main"` (non-negative) /
    `color="error.main"` (negative) — this sign-coloring is a separate, ordinary
    increase/decrease convention from the type chip's own color and AC3 does not restrict it (AC3
    is scoped to "its type is rendered", the chip, not the quantity cell). Recorded by: render
    `` `User #${movement.performed_by}` `` (see Dev Notes for why this does not resolve to a name
    like the mockup's "Noa (Warehouse Manager)"). When: `new Date(movement.timestamp).toLocaleString()`
    (first timestamp rendered anywhere in this codebase, no existing shared formatter to reuse or
    match).
  - [x] Empty movement history: exact copy **"No stock movements yet"** (UX-DR15,
    `_bmad-output/planning-artifacts/ux-designs/.../EXPERIENCE.md` State Patterns table — this
    string is load-bearing, copy it exactly, do not paraphrase).
  - [x] Loading/error state: combine `ingredientQuery`/`movementsQuery` per
    `TableOrderDetailPage.tsx`'s "OR loading/error across multiple queries" convention
    (`isLoading = ingredientQuery.isLoading || movementsQuery.isLoading`, etc.), `RowsSkeleton`
    for cold load, an `Alert` with Retry for a genuine transport error, distinct from the
    "not found" message (mirror `hasNoOpenOrder`'s split-out-of-isError shape: a 404 from
    `useIngredient` is not a transport failure needing Retry, it means this id has nothing to
    show).
  - [x] `createMutation.isError` (i.e. the record-movement mutation) renders inline via an `Alert`,
    same shape as `IngredientsPage.tsx`'s `createMutation.isError` block, and does not clear the
    typed form values on failure (matches the duplicate-name precedent: "the typed values stay").

- [x] **Task 10: Frontend tests** (AC: 1, 2, 3, new file
  `frontend/src/pages/warehouse/IngredientDetailPage.test.tsx`, mirror `IngredientsPage.test.tsx`'s
  "mock only `fetch`, drive the real hooks" pattern — do not `vi.mock` `inventoryService`)
  - [x] Renders the stat cards (current stock, threshold, unit) from the two GET responses.
  - [x] Renders a movement history row: type label text (via `MovementTypeChip`), signed quantity
    with the correct `+`/`-` prefix, note text, "When" text.
  - [x] Shows **"No stock movements yet"** when the movements GET returns `[]` (exact copy, AC per
    UX-DR15).
  - [x] Type select offers Purchase/Waste/Adjustment and does **not** offer Consumption as an
    option (query the select's options, assert Consumption's absence, not just the other three's
    presence — mirrors this codebase's own "assert absence, not just presence" habit, e.g.
    `IngredientsPage.test.tsx`'s unit-select-reset assertion).
  - [x] Submitting a Purchase movement calls `POST .../movements` with the exact body
    `{ movement_type: "purchase", quantity: "<n>", notes: null }` (or the typed note), and the
    form clears on success (mirrors `IngredientsPage.test.tsx`'s "creates an ingredient..." test
    shape: mock state tracks the POST, GETs after invalidation reflect it).
  - [x] Submitting an Adjustment with a leading `-` in the quantity field is accepted and sent as
    typed (proves `parseAdjustmentAmount` allows the sign the Purchase/Waste parser must reject).
  - [x] An invalid/zero quantity keeps the submit button disabled (client-side, before any
    request) — mirrors `IngredientsPage.test.tsx`'s inline validation-error assertions
    (`INVALID_AMOUNT_MESSAGE`-style, dev picks the exact message text and asserts it).
  - [x] A 422 from the backend on submit renders inline, and the typed form values are preserved
    (mirrors `IngredientsPage.test.tsx`'s "surfaces the exact duplicate-name message..." test).
  - [x] An invalid route param (e.g. non-numeric `:ingredientId`) or a 404 from `useIngredient`
    both render the same "not found" message, with no fetch attempted for the first case (assert
    the mock `fetch` was never called with the movements endpoint when the param itself is
    invalid).
  - [x] Full regression: `pnpm test` from `frontend/`, `npx tsc -b` (this codebase's own trap 21:
    `pnpm test` alone has shipped a build-breaking type error before, `tsc -b` is mandatory before
    calling a frontend story done).

### Review Findings

- [x] [Review][Patch] Lost-update race on `Ingredient.current_stock` in `record_movement` [backend/services/inventory_service.py:171] — a plain `db.get(Ingredient, ingredient_id)` read with no row lock means two concurrent movements on the same ingredient (e.g. a Warehouse Manager and an Admin both logging at once) both read the same starting `current_stock`, and the later commit silently overwrites the earlier delta. Both `StockMovement` audit rows still get inserted correctly, so the audit trail and `current_stock` end up disagreeing, exactly the failure NFR-4/AD-16 exist to prevent. This codebase already has the fix pattern for this exact class of bug (trap 9 / `MenuService._lock_dish`'s `SELECT ... FOR UPDATE`), just not applied here since this story's Dev Notes correctly ruled out a *guarded* UPDATE (no state to gate) but didn't separately consider the *lock* needed for a concurrent read-modify-write accumulate.
- [x] [Review][Patch] Simultaneous "not found" and "could not load" banners on `IngredientDetailPage` [frontend/src/pages/warehouse/IngredientDetailPage.tsx:114] — `isError` excludes `ingredientQuery`'s own 404 via `!isNotFound`, but not `movementsQuery`'s: `list_movements` also raises `IngredientNotFoundError` for a missing ingredient, so both queries 404 together on every nonexistent-id visit, and `isError` still evaluates true from `movementsQuery.isError` alone. Both the warning Alert ("not valid") and the error Alert ("Could not load... Retry") render at once on what is the page's primary not-found path, not a rare race. Fix: `const isError = (ingredientQuery.isError && !isNotFound) || (movementsQuery.isError && !isNotFound);`
- [x] [Review][Patch] No secondary sort key on movement history ordering [backend/services/inventory_service.py:143] — `list_movements` orders by `StockMovement.timestamp.desc()` alone; two movements inserted with the same DB-clock timestamp sort in an undefined order. Add `.order_by(StockMovement.timestamp.desc(), StockMovement.id.desc())`.
- [x] [Review][Patch] Duplicated "fetch ingredient or 404" logic across three methods [backend/services/inventory_service.py:106-178] — the same four-line existence check is copy-pasted in `get_ingredient`, `list_movements`, and `record_movement`, and has already drifted (only `record_movement` logs the rejection). Consolidate into a private `_get_ingredient` seam, mirroring `OrderService._get_order`/`_get_table`/`_get_item`'s established shape.
- [x] [Review][Patch] Dev Agent Record overstates backend test count [_bmad-output/implementation-artifacts/4-1-record-manual-stock-movements.md, Dev Agent Record] — Completion Notes and File List both say "42 new tests"; the diff adds exactly 26 (`grep -c "^+async def test_"` on `backend/tests/test_inventory.py`'s diff hunk). Coverage itself is complete against Task 5's checklist, only the recorded count is wrong. Correct "42" to "26" in both places.
- [x] [Review][Defer] `current_stock + delta` not bounded against its own `Numeric(10,3)` ceiling [backend/services/inventory_service.py:181] — deferred, pre-existing. A value pushing an already-near-ceiling `current_stock` over it raises a raw 500 instead of a 422. Already flagged and consciously accepted in this story's own Dev Notes as matching `CreateIngredientRequest.current_stock`'s identical existing gap; no AC requires a fix.
- [x] [Review][Defer] Untested decimal_places-only precision overflow (e.g. `"1.2345"`, valid digit count but too many decimal places) [backend/tests/test_inventory.py] — deferred, pre-existing test-coverage gap pattern. The Pydantic `decimal_places=3` bound is declarative and already exercised by the total-digit-count overflow test; this is a coverage completeness gap, not a suspected implementation defect.
- [x] [Review][Defer] Non-404 frontend error path untested on `IngredientDetailPage` [frontend/src/pages/warehouse/IngredientDetailPage.test.tsx] — deferred, pre-existing test-coverage gap pattern. No test simulates a 500/network failure on the GET requests to exercise the "Could not load... Retry" Alert; code inspection shows the branch itself is correctly implemented.
- [x] [Review][Defer] "Preserves typed form values" test checks only the quantity field [frontend/src/pages/warehouse/IngredientDetailPage.test.tsx] — deferred, minor test-coverage gap. Does not also assert movement-type and notes survive a rejected submission, despite the test name's broader claim.
- [x] [Review][Defer] Generic error-fallback branch (`errorMessage`'s non-`ApiError` case) unverified [frontend/src/pages/warehouse/IngredientDetailPage.test.tsx] — deferred, test-coverage gap. No test throws a raw non-`ApiError` failure to confirm `GENERIC_ERROR_MESSAGE` renders.
- [x] [Review][Defer] `StockMovementResponse.ingredient_id`/`reference_id` not asserted in backend tests [backend/tests/test_inventory.py] — deferred, test-coverage gap. Existing tests check `movement_type`/`quantity_change`/`notes`/`performed_by` but not that `ingredient_id` matches the URL param or that `reference_id` comes back `null`.
- [x] [Review][Defer] Admin role not explicitly tested against the two new GET endpoints [backend/tests/test_inventory.py] — deferred, test-coverage gap. Write path has `test_admin_can_also_log_a_purchase`; no equivalent exists for `GET /ingredients/{id}` or `GET .../movements`.
- [x] [Review][Defer] No client-side precision guard on the quantity field [frontend/src/pages/warehouse/IngredientDetailPage.tsx:68] — deferred, minor UX gap. An over-precision value passes `parsePositiveAmount`/`parseAdjustmentAmount`'s regex and only fails server-side with a 422 (still shown inline, form values preserved), rather than being caught before submit.
- [x] [Review][Defer] `isQuantityInvalid` shows no visible reason when quantity is typed before a movement type is selected [frontend/src/pages/warehouse/IngredientDetailPage.tsx:128] — deferred, minor UX gap. Submit stays disabled with no inline text explaining why until a type is also chosen; project-context.md's "disabled control needs visible text" rule applies loosely here but the missing-type case is generally self-evident from the form's own layout.

Dismissed as noise or consistent with established precedent (6): cross-module import of `_INT4_MAX` from `data_models.menu` (identical to `api/menu.py`/`api/orders.py`/`api/tables.py`'s own existing convention); unbounded `notes` `Text` field (matches `OrderItem.notes`'s identical existing precedent); stale rejection message not auto-cleared on field edit (matches `IngredientsPage.tsx`'s own established "typed values stay, error stays until next submit" behavior); `useRecordStockMovement`'s mutation function tolerating a null id (unreachable — the page returns its "not valid" state before rendering the form whenever `parsedIngredientId` is null); double-submit guard relying on `isPending`'s render timing (matches every other mutation in this codebase, e.g. `useAddOrderItem`/`useEditOrderItem`, not novel to this diff); whitespace-padded quantity strings (false positive — Python's `Decimal` constructor strips surrounding whitespace per spec, no parse failure).

## Dev Notes

### Architecture compliance

- **AD-16** (`Ingredient.current_stock` never floor-capped at zero, on either path): `record_movement`
  applies `delta` unconditionally, no `max(0, ...)`/clamp anywhere. AC2's test explicitly asserts
  the exact negative resulting value, not merely "no error", since a floor-capped implementation
  would also return 200 and could otherwise pass a weaker test.
- **NFR-4** (auditability, every stock change traceable to exactly one Stock Movement): `record_movement`
  commits the Ingredient's row update and the new StockMovement insert together in one transaction
  (Task 3) — never update `current_stock` from any other code path without a corresponding
  movement row.
- This story is **not** an application of AD-6/trap 18's guarded-UPDATE shape. Nothing about the
  Ingredient's own current state gates whether a movement is allowed (unlike a Table needing to be
  `available` or an OrderItem needing to be `pending`) — this is a plain read-modify-write plus an
  append-only insert. Do not add a `WHERE`-guarded conditional UPDATE here, there is no invariant
  of the form "only while X" for this story to guard.
- **AD-9-style Role-level-only permissions**: `InventoryWriteDep`/`InventoryReadDep` are reused
  as-is (no new dependency object needed), both already grant exactly the roles this story's ACs
  need (write: warehouse_manager + admin; read: warehouse_manager + admin + cook, same tier
  `list_ingredients` already uses).

### The "Recorded by" gap (read before building the frontend table)

The Ingredient detail mockup shows "Noa (Warehouse Manager)" / "Amir (Cook)" in the Recorded By
column. This story's `StockMovementResponse` does **not** enrich the response with a resolved
name, staying consistent with this codebase's one existing precedent for this exact situation:
`OrderItemResponse.cook_id`/`dish_id` are also plain ids, never a joined `cook_name`/`dish_name`
(confirmed: no `join`/`selectinload`/`joinedload` exists anywhere in `backend/services/` today).
Unlike `dish_id` (resolvable client-side via `useDishes()`, a menu-read endpoint every relevant
role can already call), there is **no endpoint any non-Admin role can call to resolve a user id to
a name** — `GET /api/admin/users` is Admin-only, and a Warehouse Manager/Cook has no other path to
it. Building one is out of this story's AC scope (no FR/AC asks for it). The frontend therefore
renders `User #{performed_by}` as an honest, non-crashing fallback rather than a resolved name.
**This is a known, flagged product-fidelity gap versus the mockup, not an oversight** — worth a
line in `deferred-work.md` if the reviewing session agrees it should be tracked for Story 4.2/4.3
or a later polish pass (e.g. a lightweight `GET /api/users/me`-adjacent "resolve ids to names" read
open to more roles). Left as a call for whoever reviews this story to confirm or override.

### The movement-type-chip color palette (a deliberate deviation from the mockup's literal hex)

The mockup (`key-ingredient-detail.html`) hardcodes 4 light-mode-only hex pairs for `.type-*`
chips, and `.type-waste` happens to reuse the exact same red (`#d32f2f`) as the shortage banner and
as this codebase's `OrderItemStatusBadge` `color="error"` chip. Copying those hex values verbatim
would (a) not adapt to dark mode (`frontend/src/config/theme.ts` has a real `darkTheme`, toggled
live via `ThemeToggle`/`ThemeModeProvider`, unlike the mockup which only illustrates light mode),
and (b) risk undercutting AC3/UX-DR14's explicit "distinct from the traffic-light convention" text
by reusing traffic-light red for `waste`. Task 8 instead maps the four types onto MUI's
`primary`/`info`/`default`/`secondary` Chip colors — the three semantic colors
`OrderItemStatusBadge` does **not** use (`success`/`warning`/`error` are that badge's own trio),
plus `default` — which is both theme-aware for free and unambiguously not the traffic-light set.
**This is a judgment call, not something explicitly specified by any AC or the EXPERIENCE.md
component-pattern text** (which only says "neutral color scheme... no icon required", not which
specific colors) — flagged here in case the reviewing session wants closer literal fidelity to the
mockup's exact hues instead.

### Current state of the files this story touches (read before editing)

- **`backend/data_models/inventory.py`**: currently ORM-only (`MovementType`, `StockMovement`),
  no Pydantic imports at all. Task 1 is this file's first Pydantic schema.
- **`backend/services/inventory_service.py`**: currently exactly two methods
  (`list_ingredients`, `create_ingredient`). `Sequence`/`select`/`AsyncSession` are already
  imported; `IngredientNotFoundError` is not yet imported here (it exists in
  `backend/exceptions/__init__.py`, unused anywhere in the codebase today per a repo-wide grep —
  this story is its first real caller).
- **`backend/api/inventory.py`**: currently exactly two routes (`GET`/`POST /ingredients`).
  `InventoryWriteDep`/`InventoryReadDep` are both already correctly scoped for this story's three
  new routes, reuse them unchanged. `"api.inventory"` is already in `main.py`'s `container.wire(modules=[...])`
  list (line 27) — do not add it again.
- **`frontend/src/pages/warehouse/IngredientDetailPage.tsx`**: currently a bare one-line
  `Typography` placeholder, already imported and routed in `router.tsx` at
  `/warehouse/ingredients/:ingredientId`. This story is what gives it real content for the first
  time.
- **`frontend/src/services/inventoryService.ts`**: currently exports `useIngredients` (list) and
  `useCreateIngredient` (Story 2.6). Both stay unchanged; this story only adds three new exports.
- **`frontend/src/pages/warehouse/IngredientsPage.tsx`**: read for its established
  parse-helper/form/error-handling conventions (Task 9 mirrors several of its shapes directly) but
  is **not modified** by this story — no shortage sorting/highlighting, that's Story 4.3.

### Project Structure Notes

Files touched:
- `backend/data_models/inventory.py` — **UPDATE**, `CreateStockMovementRequest`,
  `StockMovementResponse` added.
- `backend/data_models/__init__.py` — **UPDATE**, new exports.
- `backend/services/inventory_service.py` — **UPDATE**, `get_ingredient`, `list_movements`,
  `record_movement` added.
- `backend/api/inventory.py` — **UPDATE**, 3 new routes, `IngredientIdPath`.
- `backend/tests/test_inventory.py` — **UPDATE**, new tests per Task 5.
- `frontend/src/types/inventory.ts` — **UPDATE**, `MovementType`, `StockMovement` added.
- `frontend/src/services/inventoryService.ts` — **UPDATE**, `useIngredient`,
  `useStockMovements`, `useRecordStockMovement` added.
- `frontend/src/components/inventory/MovementTypeChip.tsx` — **NEW** (new folder
  `components/inventory/`).
- `frontend/src/pages/warehouse/IngredientDetailPage.tsx` — **UPDATE**, placeholder replaced.
- `frontend/src/pages/warehouse/IngredientDetailPage.test.tsx` — **NEW**.

No new backend route *file* (extends `api/inventory.py`), no Alembic migration, no
`container.py`/`main.py` change, no new frontend route (`router.tsx` already has it), no change to
`IngredientsPage.tsx`/`AlertsPage.tsx`.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 4.1`] — this story's AC source (lines
  760-778); Stories 4.2 (lines 780-810) and 4.3 (812-834) read alongside it to confirm this
  story's own scope boundary.
- [Source: `_bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md#FR-15,#NFR-4`]
  — FR-15's exact sign-convention wording ("purchase increases... waste and negative adjustment
  decrease... never floor-capped") this story's Scope note paraphrases.
- [Source: `_bmad-output/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md#AD-16`] —
  binding invariant, restated verbatim in `_bmad-output/project-context.md`'s own "Binding
  architecture invariants" section.
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../mockups/key-ingredient-detail.html`] —
  the concrete layout Task 9 implements (stat cards, log-movement form, movement history table);
  shortage banner and stat-card danger styling explicitly excluded per this story's Scope note.
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../EXPERIENCE.md`] — Component Patterns
  table ("Movement type chip" row, the AC3/UX-DR14 source) and State Patterns table (the exact
  "No stock movements yet" empty-state copy, UX-DR15).
- [Source: `backend/data_models/recipe.py`] — `CreateIngredientRequest`/`IngredientResponse`'s
  colocation-with-ORM-class convention and trap-16 `max_digits`/`decimal_places` shape, both
  followed by Task 1's new schemas.
- [Source: `backend/services/inventory_service.py::create_ingredient`] — the existing
  logging-before-any-lazy-read shape (trap 20) `record_movement` follows, though this story's
  method has no `IntegrityError` branch to protect (see Task 3's own note on why).
- [Source: `frontend/src/pages/waiter/TableOrderDetailPage.tsx`] — `parseRouteId`'s exact shape
  (Task 9), the "OR loading/error across multiple queries" convention, and the
  split-404-out-of-isError pattern (`hasNoOpenOrder`) this story's "not found" handling mirrors.
- [Source: `frontend/src/pages/warehouse/IngredientsPage.tsx`,
  `IngredientsPage.test.tsx`] — the parse-helper, "re-check the full predicate in the submit
  handler" (trap-adjacent standing rule), form-clear-on-success, and
  preserve-typed-values-on-error shapes Task 9/10 both mirror; also the "mock only fetch" test
  pattern Task 10 must follow, not `vi.mock("../../services/inventoryService")`.
- [Source: `frontend/src/components/orders/OrderItemStatusBadge.tsx`] — the Chip-component shape
  `MovementTypeChip` mirrors (`size="small"`, `label`, `color`, no icon), and the exact
  `success`/`warning`/`error` trio Task 8's color mapping deliberately avoids reusing.
- [Source: `_bmad-output/project-context.md`, trap 16, trap 19, trap 21, "Testing" section] — the
  Numeric-bound-matching rule (Task 1), the never-bare-`Number()`-on-unvalidated-input rule (Task
  9's two parsers), the `npx tsc -b`-before-done rule (Task 10), and the "verify a numeric claim
  against a live Postgres" rule (Task 5's precision-overflow test).

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (claude-sonnet-5), via Claude Code.

### Debug Log References

None. Backend and frontend suites passed on the first full run after implementation, aside from
two pre-existing issues fixed along the way (both cross-file, neither in this story's own new
code, see Completion Notes below):
- `frontend/src/router.test.tsx`'s two `/warehouse/ingredients/1` assertions hardcoded the old
  placeholder's static "Ingredient detail" heading text; updated to "Ingredient", the new page's
  own unconditional heading fallback (`{ingredient ? ingredient.name : "Ingredient"}`), since
  that router test never stubs `fetch` and so the Ingredient never actually loads.
- `frontend/src/pages/admin/UsersPage.test.tsx`'s "creates a user..." test intermittently timed
  out at the default 5000ms only when the *full* suite ran under parallel CPU contention; it
  passed cleanly every time in isolation and on a second full-suite run. Confirmed pre-existing
  flakiness unrelated to this story (that file is untouched by Story 4.1), not a regression.

### Completion Notes List

- Implemented all 10 tasks per the story's own near-complete code: Pydantic schemas
  (`CreateStockMovementRequest`/`StockMovementResponse`) with the AD-16 sign-convention
  validator, `InventoryService.get_ingredient`/`list_movements`/`record_movement`, three new
  `api/inventory.py` routes (`GET /ingredients/{id}`, `GET .../movements`,
  `POST .../movements`), full backend test coverage (26 new tests, Task 5's entire list),
  frontend types/hooks/`MovementTypeChip`/`IngredientDetailPage`, and 10 new frontend tests
  (Task 10's entire list).
- Deviation 1 (backend, cosmetic): Task 4's suggested `_DETAIL_ERROR_DESCRIPTIONS` spread-and-drop
  shape (`{**_ERROR_DESCRIPTIONS, 404: "..."}` with 409 manually excluded) was replaced with two
  fresh, self-contained dicts (`_DETAIL_ERROR_DESCRIPTIONS`, `_MOVEMENT_ERROR_DESCRIPTIONS`), per
  the story's own "or two fresh dicts if that reads cleaner, dev's call" allowance. Avoids
  spreading in a 409 key that these three routes never return.
- Deviation 2 (frontend, required to satisfy `tsc -b`, trap 21 in practice): the story's Task 9
  sketch re-checks `movementType === ""` inside `handleSubmit`. Because `canSubmit`'s own
  `movementType !== ""` clause is evaluated first in the same `||` chain, TypeScript's
  control-flow analysis of aliased conditions narrows `movementType`'s type to exclude `""` by
  that point, so a literal `===` comparison against `""` is flagged TS2367 ("no overlap") and
  fails the build. Changed to `!movementType`, matching `IngredientsPage.tsx`'s own
  `handleCreate` precedent (`!unit`, not `unit === ""`), which sidesteps the same issue.
  `pnpm test` alone passed with the literal comparison still in place; only `tsc -b` caught it,
  the exact trap 21 scenario the story's Dev Notes flagged.
- Deviation 3 (frontend test file): the story's Task 9/10 sketches don't show a `stubReads`
  helper signature; mine originally took `(url: string)` only (no `init` param), which made
  `fetchMock.mock.calls.every(([, init]) => ...)` fail to type-check under `tsc -b` (a
  one-element tuple has no index 1). Fixed by giving `stubReads` a second, unused `_init`
  parameter, matching `TableOrderDetailPage.test.tsx`'s own `stubReads` shape.
- Fixed two pre-existing `router.test.tsx` assertions that hardcoded the placeholder's old
  "Ingredient detail" heading text (see Debug Log References) so the full frontend suite passes;
  no other file outside this story's own File List was modified.
- All ACs verified by test: AC1 (purchase increases stock + audit trail) via
  `test_purchase_increases_current_stock`/`test_purchase_is_recorded_in_the_audit_trail`; AC2
  (waste/negative-adjustment decrease, never floor-capped) via
  `test_waste_can_drive_current_stock_negative_not_floor_capped`/
  `test_negative_adjustment_can_drive_current_stock_negative_not_floor_capped`, asserting the
  exact negative value per the story's own "don't just check no error" instruction; AC3 (neutral
  movement-type chip) via `MovementTypeChip`'s `primary`/`info`/`default`/`secondary` mapping and
  its frontend test asserting Consumption is never offered as a loggable type.
- Final regression: backend `uv run pytest` from `backend/` — 296 passed (0 failed). Frontend
  `pnpm test` from `frontend/` — 152 passed (0 failed) on two consecutive full runs. `npx tsc -b`
  from `frontend/` — clean, exit code 0.
- **Found and fixed during manual testing against the live Docker stack (2026-08-15), after the
  automated code review had already closed the story as `done`:**
  1. **`IngredientsPage.tsx` had no way to reach `IngredientDetailPage.tsx` at all.** The page's own
     docstring (written in Story 2.6) deliberately deferred "click-to-detail" to Story 4.3 on the
     reasoning that it "needs the below-threshold comparison logic" — but that reasoning was wrong:
     plain row-click navigation needs no comparison logic, only sorting/highlighting does. With Story
     4.1 now shipping a real destination page, the Ingredients list had a dead end: the only way to
     reach it was typing the URL by hand. Fixed by adding `useNavigate()` + an `onClick`/`hover`/
     `cursor: pointer` `TableRow`, mirroring `TablesPage.tsx`'s own tile-click-to-detail precedent,
     plus a new test (`navigates to the Ingredient detail page when a row is clicked`) and the
     `MemoryRouter`/`useNavigate` mock scaffolding `IngredientsPage.test.tsx` needed to support it
     (mirrors `TablesPage.test.tsx`'s exact setup, since none of that file's existing tests rendered
     inside a Router before this fix). None of the three review layers caught this, since a diff-only
     review has no way to notice a page that exists and works but is unreachable through the UI it
     ships alongside.
  2. **The movement-history quantity color never rendered.** `Typography`'s `color` prop was passed
     `"error.main"`/`"success.main"` — valid syntax inside `sx`, but not a value `TypographyPropsColorOverrides`
     recognizes on the bare `color` prop, so it silently fell back to no color at all (correct text,
     wrong/no styling, exactly what manual testing surfaced and no automated test caught, since none
     of `IngredientDetailPage.test.tsx`'s assertions checked color). Fixed by changing both to the
     bare palette keys `"error"`/`"success"`, which **are** valid `color` prop values.
  - Backend was not touched by this pass; the three Review Findings patches above cover it fully.

- `backend/data_models/inventory.py` — UPDATE, `CreateStockMovementRequest`,
  `StockMovementResponse` added.
- `backend/data_models/__init__.py` — UPDATE, new exports.
- `backend/services/inventory_service.py` — UPDATE, `get_ingredient`, `list_movements`,
  `record_movement` added.
- `backend/api/inventory.py` — UPDATE, 3 new routes, `IngredientIdPath`,
  `_DETAIL_ERROR_DESCRIPTIONS`/`_MOVEMENT_ERROR_DESCRIPTIONS`.
- `backend/tests/test_inventory.py` — UPDATE, 26 new tests per Task 5.
- `frontend/src/types/inventory.ts` — UPDATE, `MovementType`, `StockMovement` added.
- `frontend/src/services/inventoryService.ts` — UPDATE, `useIngredient`, `useStockMovements`,
  `useRecordStockMovement` added.
- `frontend/src/components/inventory/MovementTypeChip.tsx` — NEW (new folder
  `components/inventory/`).
- `frontend/src/pages/warehouse/IngredientDetailPage.tsx` — UPDATE, placeholder replaced with
  full detail page.
- `frontend/src/pages/warehouse/IngredientDetailPage.test.tsx` — NEW, 10 tests per Task 10.
- `frontend/src/router.test.tsx` — UPDATE (not in the story's own Project Structure Notes list;
  fixed as an incidental cross-file regression, see Completion Notes), two assertions updated
  from the old placeholder's literal "Ingredient detail" heading text to the new page's
  "Ingredient" fallback heading.
- `frontend/src/pages/warehouse/IngredientsPage.tsx` — UPDATE (not in the story's own Project
  Structure Notes list; found and fixed during manual testing, see Completion Notes), row
  click-through to the Ingredient detail page added.
- `frontend/src/pages/warehouse/IngredientsPage.test.tsx` — UPDATE, one new test plus
  `MemoryRouter`/`useNavigate` mock scaffolding (see Completion Notes).
