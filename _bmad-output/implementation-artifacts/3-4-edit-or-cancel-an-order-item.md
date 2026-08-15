---
baseline_commit: b1325c69c3e208600a3ef38902e4e6ed68da51f1
epic: 3
story: 4
---

# Story 3.4: Edit or Cancel an Order Item

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Waiter, Cook, or Admin,
I want to edit a pending order item or cancel an order item,
so that mistakes and last-minute changes can be corrected without blocking the table.

## Scope note (read first)

**Two role-gated backend actions, only one of which has a frontend surface today.** FR-7 grants
edit to the Waiter only, and cancel to Waiter, Cook, **or** Admin. `TableOrderDetailPage.tsx`
(`/waiter/tables/:tableId`) is currently the **only** screen in the entire app that shows an
Order's items — Cook's Kitchen Display (Epic 5) and any Admin order-viewing surface do not exist
yet. So: **both endpoints permit Waiter/Cook/Admin per FR-7 on the backend** (cancel) or
**Waiter-only** (edit), but **the frontend Cancel/Edit controls only need to be wired into the
Waiter's `TableOrderDetailPage.tsx`**, the one surface that exists. This is not a parity gap to
"fix" by inventing a Cook or Admin screen early — it is the same shape Story 2.1/2.6 already
established (`InventoryWriteDep` permitted Admin before Admin's own UI reached it), and Epic 5 is
what will eventually give Cook a cancel control of their own. **Every control this story CAN wire
into an existing screen, it must** — that is the parity bar, not "build screens that don't exist
yet."

**`cancelled` does not exist on `OrderItemStatus` yet.** This story adds it as the 4th member,
shipping its own Alembic migration (AC7) on top of the current head (`819cce996301`,
`add_price_at_add_to_order_items`). **Autogenerate does not detect Postgres enum value additions**
— `alembic revision --autogenerate` will produce an empty migration for this change; the
`op.execute("ALTER TYPE orderitemstatus ADD VALUE 'cancelled'")` call has to be hand-written (the
enum's Postgres type name is `orderitemstatus`, confirmed in `alembic/versions/8c7084cec0ff_baseline_schema.py`
line ~130, lowercase, matching SQLAlchemy's default `Enum(OrderItemStatus)` naming). Postgres
cannot cleanly remove an enum value, so `downgrade()` is a documented no-op (raise
`NotImplementedError` with an explanatory message, matching the honesty-over-silent-failure
convention this codebase already applies elsewhere), not a fake `DROP TYPE`/recreate that would
corrupt any row already carrying `cancelled`.

**Two guarded-UPDATE transitions (AD-6/trap 18), not a read-then-write, for the same reason
`TableService.update_table`/`OrderService.open_table` already aren't**: edit is only valid `WHERE
status = 'pending'`, cancel is only valid `WHERE status IN ('pending', 'in_preparation')`. A
concurrent transition landing between this request's read and write must not silently succeed
against a row that has already moved past the state this request assumed.

**No live broadcast for this story.** Story 3.3 gave `OrderService` its first two producers
(`table.status_changed`, `order.item_added`), but this story's own ACs never say "live",
"instantly", or "the moment" for edit/cancel — unlike Story 3.3's ACs, which said so explicitly.
Per `project-context.md`'s own rule ("any story whose AC says live/instantly/the moment needs to
check whether a producer exists"), the absence of that language here means this story does **not**
need to add `order.item_edited`/`order.item_cancelled` events. Do not add them — that would be
scope beyond what this story's epics entry asks for; a future story can add them if a real AC
needs it.

## Acceptance Criteria

**AC1 — Edit a pending item's quantity or note**
Given a `pending` Order Item, when a Waiter edits its quantity or note, then the change is saved
(FR-7).

**AC2 — Cancel a pending item, no stock impact**
Given a `pending` Order Item, when a Waiter, Cook, or Admin cancels it, then it moves to
`cancelled` with no stock impact, since nothing was deducted yet (FR-7).

**AC3 — Cancel an in_preparation item, no auto-reversal, confirm required**
Given an `in_preparation` Order Item, when a Waiter, Cook, or Admin cancels it, then it moves to
`cancelled`, but its prior stock deduction is **not** automatically reversed (FR-7, AD-11); the
confirm dialog states this plainly before the cancel is applied (UX-DR12).

**AC4 — Editing an in_preparation item is rejected**
Given an `in_preparation` Order Item, when anyone attempts to edit its quantity or note instead of
cancelling, then the edit is rejected, only cancellation is available once prep has started (FR-7).

**AC5 — Cancelled items are excluded from aggregate reads**
Given an Order containing a cancelled Order Item, when any aggregate read of that Order is
performed, then the cancelled item is excluded, so the status-derivation and readiness-for-close
rules built in Epic 5 (FR-12, FR-8) never see it. *(No aggregate-read code exists yet — Epic 5
builds `Order.status` derivation. This AC is satisfied for this story by ensuring `list_items`
still returns every item including cancelled ones, unfiltered — a Waiter needs to see a cancelled
line was cancelled, not have it vanish — and by leaving a note for Epic 5's own implementer that
its aggregate logic must filter `status != cancelled` itself. Nothing to build here beyond that
note.)*

**AC6 — Last-write-wins on concurrent field edits**
Given two concurrent field edits to the same Order Item, outside the atomic transition paths, when
both commit, then last-write-wins applies, with no optimistic locking and no conflict UI (NFR-6).
*(Already true by construction: the edit endpoint is a guarded UPDATE on `status`, not on the
edited fields themselves, so two overlapping quantity/note edits both succeed sequentially, last
one committed wins. Nothing extra to build; a test proves it.)*

**AC7 — `cancelled` ships its own migration**
Given `cancelled` does not yet exist as a value on the `OrderItemStatus` enum, when this story adds
it, then the enum change ships with its own Alembic migration on top of the baseline established in
Story 1.0 (AD-4).

## Tasks / Subtasks

- [x] **Task 1: `cancelled` on `OrderItemStatus` + migration** (AC: 7)
  - [x] `backend/data_models/order.py`: add `cancelled = "cancelled"` to `OrderItemStatus`.
  - [x] Generate the revision: `uv run alembic revision -m "add cancelled to orderitemstatus"`
    (plain `revision`, not `--autogenerate`, since autogenerate produces an empty file for enum
    value additions — confirm this by trying `--autogenerate` first if unsure, observe the empty
    diff, then write it by hand). Body:
    ```python
    def upgrade() -> None:
        op.execute("ALTER TYPE orderitemstatus ADD VALUE 'cancelled'")

    def downgrade() -> None:
        raise NotImplementedError(
            "Postgres cannot cleanly remove an enum value; downgrading past this revision "
            "requires a manual data migration for any row already using 'cancelled'."
        )
    ```
  - [x] Confirm exactly one head (`uv run alembic heads`), then `uv run alembic upgrade head`
    against the dev DB before writing any test against it.

- [x] **Task 2: Exceptions** (AC: 1, 2, 3, 4)
  - [x] `backend/exceptions/__init__.py`, two new `ConflictError` subclasses, following
    `TableNotAvailableError`/`DishNotAvailableError`'s exact shape (short docstring, one-line
    `detail`, `"Rejected, ..."` phrasing matching this codebase's established convention):
    ```python
    class OrderItemNotPendingError(ConflictError):
        """Raised when editing an Order Item that is not currently pending (AC4)."""

        detail = "Rejected, item not pending"


    class OrderItemNotCancellableError(ConflictError):
        """Raised when cancelling an Order Item that is not pending or in_preparation (AC2/AC3)."""

        detail = "Rejected, item not cancellable"
    ```
  - [x] One new `NotFoundError` subclass, matching `OrderNotFoundError`'s shape exactly:
    ```python
    class OrderItemNotFoundError(NotFoundError):
        """Raised when no Order Item matches the given id."""

        detail = "Order item not found"
    ```

- [x] **Task 3: `UpdateOrderItemRequest` schema** (AC: 1)
  - [x] `backend/data_models/order.py`, placed after `CreateOrderItemRequest`. **Not** a partial
    PATCH like `UpdateTableRequest` — `quantity` is always required (there is no meaningful "leave
    quantity alone" partial state the way a Table's number/capacity can be edited independently),
    `notes` stays optional/nullable exactly like `CreateOrderItemRequest`'s own `notes` field, no
    `at_least_one_field`/reject-explicit-null validators needed (there is no partial-update
    ambiguity to defend against: the frontend always sends both fields, `None` already means "no
    note" uniformly on both the add and edit paths).
    ```python
    class UpdateOrderItemRequest(BaseModel):
        """Body of a Waiter's request to edit a pending Order Item's quantity and/or note."""

        quantity: int = Field(gt=0, le=MAX_ORDER_ITEM_QUANTITY)
        notes: str | None = None
    ```

- [x] **Task 4: `OrderService.edit_item`** (AC: 1, 4, 6)
  - [x] `backend/services/order_service.py`, new method, guarded UPDATE `WHERE id = :item_id AND
    status = 'pending'` (AD-6/trap 18 shape, mirroring `open_table`'s guarded UPDATE on
    `RestaurantTable`, not a read-then-write):
    ```python
    async def edit_item(
        self, db: AsyncSession, actor: User, order_id: int, item_id: int, payload: UpdateOrderItemRequest
    ) -> OrderItem:
        """Edit a pending Order Item's quantity and/or note (AC1).

        Guarded on status = 'pending' at the moment of the write (AD-6): an item that has already
        moved to in_preparation between this request's read and write must reject the edit, not
        silently apply it (AC4).

        Args:
            db: The active database session.
            actor: The Waiter editing the item.
            order_id: The id of the Order the item belongs to.
            item_id: The id of the Order Item to edit.
            payload: The submitted quantity and/or note.

        Returns:
            The updated Order Item.

        Raises:
            OrderItemNotFoundError: If no Order Item matches item_id on order_id.
            OrderItemNotPendingError: If the item's status is not pending at the moment of the write.
        """
    ```
    Implementation shape: `await self._get_item(db, actor, order_id, item_id)` first (404 if
    missing, mirrors `_get_order`), **then** the guarded UPDATE:
    `UPDATE order_items SET quantity = :quantity, notes = :notes WHERE id = :item_id AND status =
    'pending'`. `rowcount == 0` after the existence check already passed means the item exists but
    is no longer pending, raise `OrderItemNotPendingError` (409), not a second `OrderItemNotFoundError`.
    `await db.rollback()` before raising (trap 18's own precedent), log the rejection at
    `WARNING`/success at `INFO` before the rollback and before any lazy attribute read (trap 20:
    `db.rollback()` expires `actor`, log identifying ids from `actor.id` *before* rolling back, not
    after). On success, `await db.commit()`, `await db.refresh(item)` (the row bound from the
    existence check, not a fresh `db.get`), return it.

- [x] **Task 5: `OrderService.cancel_item`** (AC: 2, 3)
  - [x] Same file, new method, guarded UPDATE `WHERE id = :item_id AND status IN ('pending',
    'in_preparation')`:
    ```python
    async def cancel_item(self, db: AsyncSession, actor: User, order_id: int, item_id: int) -> OrderItem:
        """Cancel a pending or in_preparation Order Item (AC2/AC3).

        Guarded on status IN ('pending', 'in_preparation') at the moment of the write (AD-6): an
        item already ready or already cancelled cannot be cancelled again. Cancelling never
        reverses a prior stock deduction (AD-11) — no compensating StockMovement is inserted here
        or anywhere else; the frontend's confirm dialog for an in_preparation item is what tells
        the actor this before they commit to it (AC3, UX-DR12), the backend enforces no stock rule
        because there is none to enforce, only the state transition itself.

        Args:
            db: The active database session.
            actor: The Waiter, Cook, or Admin cancelling the item.
            order_id: The id of the Order the item belongs to.
            item_id: The id of the Order Item to cancel.

        Returns:
            The now-cancelled Order Item.

        Raises:
            OrderItemNotFoundError: If no Order Item matches item_id on order_id.
            OrderItemNotCancellableError: If the item's status is not pending or in_preparation at
                the moment of the write.
        """
    ```
    Same existence-check-then-guarded-UPDATE shape as `edit_item`. No stock/`StockMovement` code
    of any kind, AD-11 is a *prohibition* (never auto-reverse), not a rule this method enforces
    positively.

- [x] **Task 6: `_get_item` seam** (AC: 1, 2, 3, 4)
  - [x] Private helper, mirrors `_get_order`/`_get_table`'s exact shape: `await
    db.get(OrderItem, item_id)`, raise `OrderItemNotFoundError` if `None` or if `item.order_id !=
    order_id` (an item id that exists but belongs to a *different* Order must 404, not silently
    operate on the wrong Order's item just because the numeric id happened to match — no test in
    this codebase has needed this cross-Order check before since every prior `_get_*` seam had only
    one id to check; this is the first one with two, get this specific check right).

- [x] **Task 7: `api/orders.py` routes** (AC: 1, 2, 3, 4)
  - [x] New role dependency, the project's first three-Role `require_role` call (`require_role`
    already supports any number of Roles, trap 8, no change needed to it):
    ```python
    # Cancel is the one route in this file NOT waiter-only (FR-7): a Cook or Admin can also
    # cancel, though neither role has a screen that reaches this endpoint yet (Epic 5 builds
    # Cook's Kitchen Display). Edit stays on the existing waiter-only OrdersDep, unchanged.
    OrderItemCancelDep = Annotated[User, Depends(require_role(UserRole.waiter, UserRole.cook, UserRole.admin))]
    ItemIdPath = Annotated[int, Path(gt=0, le=_INT4_MAX)]
    ```
    ```python
    @router.patch(
        "/{order_id}/items/{item_id}",
        response_model=OrderItemResponse,
        responses=error_responses(_EDIT_ERROR_DESCRIPTIONS, 401, 403, 404, 409),
    )
    @inject
    async def edit_order_item(
        order_id: OrderIdPath,
        item_id: ItemIdPath,
        payload: UpdateOrderItemRequest,
        actor: OrdersDep,
        db: SessionDep,
        order_service: OrderService = Depends(Provide[Container.order_service]),
    ) -> OrderItem:
        return await order_service.edit_item(db, actor, order_id, item_id, payload)


    @router.post(
        "/{order_id}/items/{item_id}/cancel",
        response_model=OrderItemResponse,
        responses=error_responses(_CANCEL_ERROR_DESCRIPTIONS, 401, 403, 404, 409),
    )
    @inject
    async def cancel_order_item(
        order_id: OrderIdPath,
        item_id: ItemIdPath,
        actor: OrderItemCancelDep,
        db: SessionDep,
        order_service: OrderService = Depends(Provide[Container.order_service]),
    ) -> OrderItem:
        return await order_service.cancel_item(db, actor, order_id, item_id)
    ```
    (Full docstrings required per this project's convention, omitted above for brevity — write
    them out, matching every sibling route's Args/Returns/Raises shape.) `_EDIT_ERROR_DESCRIPTIONS`/
    `_CANCEL_ERROR_DESCRIPTIONS`: build from `_ITEM_ERROR_DESCRIPTIONS`'s existing shape, 404 text
    "No matching Order or Order Item was found", 409 text specific to each ("The item is not
    pending" / "The item is not pending or in_preparation").
  - [x] No `container.py`/`main.py` change needed, `order_service` and `"api.orders"` are already
    wired.

- [x] **Task 8: Frontend — `types/order.ts`** (AC: 1, 2, 3, 4)
  - [x] Add `"cancelled"` to the `OrderItemStatus` union (the file's own comment already flags this
    as the exact trigger: *"`cancelled` (AD-11) does not exist on the backend enum until Story 3.4
    ships its own migration, do not add it speculatively"* — this is that story, add it now).

- [x] **Task 9: Frontend — `OrderItemStatusBadge.tsx`** (AC: 2, 3)
  - [x] Add a `cancelled` entry to all three `Record<OrderItemStatus, ...>` maps (`LABELS`,
    `ICONS`, `COLORS`). TypeScript's exhaustiveness checking on `Record<OrderItemStatus, X>` means
    the file will not compile until this is done, once Task 8 lands — that failure is the intended
    forcing function, not a bug to work around. Suggested: label `"Cancelled"`, icon
    `CancelIcon`/`@mui/icons-material/Cancel` (or any `@mui/icons-material` icon already available,
    dev's call), color `"error"` (the one unused MUI Chip color among this badge's existing
    `default`/`warning`/`success`, keeping every status visually distinct).

- [x] **Task 10: Frontend — `orderService.ts` mutations** (AC: 1, 2, 3, 4)
  - [x] Two new hooks, mirroring `useAddOrderItem`'s shape (invalidate the item list on settle,
    same `orderItemsQueryKey` this file already exports):
    ```typescript
    interface EditOrderItemPayload {
      quantity: number;
      notes?: string | null;
    }

    export function useEditOrderItem(
      orderId: number | undefined,
    ): UseMutationResult<OrderItem, Error, { itemId: number; payload: EditOrderItemPayload }> {
      const queryClient = useQueryClient();
      return useMutation({
        mutationFn: ({ itemId, payload }) =>
          apiRequest<OrderItem>(`/api/orders/${orderId}/items/${itemId}`, {
            method: "PATCH",
            body: JSON.stringify(payload),
          }),
        onSettled: () => queryClient.invalidateQueries({ queryKey: orderItemsQueryKey(orderId) }),
      });
    }

    export function useCancelOrderItem(
      orderId: number | undefined,
    ): UseMutationResult<OrderItem, Error, number> {
      const queryClient = useQueryClient();
      return useMutation({
        mutationFn: (itemId: number) =>
          apiRequest<OrderItem>(`/api/orders/${orderId}/items/${itemId}/cancel`, { method: "POST" }),
        onSettled: () => queryClient.invalidateQueries({ queryKey: orderItemsQueryKey(orderId) }),
      });
    }
    ```
    `onSettled`, not `onSuccess`: a 409 (item no longer pending/cancellable) means this client's
    cached row is already stale, the failing path needs the refetch too, same reasoning
    `useUpdateTable`/`useAddOrderItem` already documented.

- [x] **Task 11: Frontend — `TableOrderDetailPage.tsx` row actions** (AC: 1, 2, 3, 4)
  - [x] The Order Item table currently has no Actions column (Story 3.2's own scope note ruled it
    out explicitly: *"No actions column on the Order Item rows (edit/cancel is Story 3.4)"* — this
    is that story). Add one, following this row-visibility matrix straight from the ACs:
    - `pending`: an **Edit** control and a plain **Cancel** button (no confirm, AC2 states no
      consequence).
    - `in_preparation`: **Cancel only** (no Edit, AC4), behind an in-row confirm reveal stating the
      stock will not be restored (AC3/UX-DR12) — reuse the established in-row-reveal shape
      (`UsersPage.tsx`'s "Deactivate {name}?" Confirm/Cancel swap is the precedent this codebase's
      Story 1.6 review settled on over a modal; this codebase has never introduced a modal
      dialog, do not be the first).
    - `ready`/`cancelled`: no actions, nothing to do with either status this story.
  - [x] Edit: click reveals inline `quantity`/`notes` fields (reuse `parseQuantity`'s existing
    validation, same `MAX_ORDER_ITEM_QUANTITY` bound), Save calls `useEditOrderItem`, **always
    sending both fields** (this codebase's standing rule: never diff against cached data to decide
    what to send, `TablesSetupPage`'s six-line comment and regression test are the precedent —
    quantity and notes are independent fields here exactly the way Table's number/capacity are).
  - [x] Cancel: `pending` row's button calls `useCancelOrderItem` directly. `in_preparation` row's
    button reveals the confirm text + a second Confirm button that then calls it.
  - [x] Row-level mutation errors render inline (an `Alert` in the row, or reuse the page's existing
    top-level `addItemMutation.isError` `Alert` pattern if a per-row `Alert` feels heavier than this
    page's existing conventions warrant — dev's call, note the choice in Completion Notes).

- [x] **Task 12: Tests** (AC: all)
  - [x] `backend/tests/test_orders.py` — mirror the existing style (`# Arrange`/`# Act`/`# Assert`,
    no docstrings). New helper `_add_item(client, order_id, dish_id, ...)` if useful (a plain POST
    wrapper, several new tests need one already-added item to edit/cancel). Cover:
    - Waiter edits a pending item's quantity and note, both persist (AC1).
    - Waiter, Cook, and Admin *each* successfully cancel a pending item (three tests or one
      parametrized test, dev's call), stock unaffected because nothing was ever deducted — no
      `StockMovement` table exists yet to assert against, so "no stock impact" is proven by absence
      of any deduction-related error/side effect, not a movement-count assertion (AC2).
    - Cancelling an `in_preparation` item succeeds and does not reverse whatever stock state
      preceded it — since automatic deduction (FR-13) is Epic 5 territory and doesn't exist in code
      yet either, set the item to `in_preparation` directly via `db_session` for this test's setup,
      matching how `test_editing_an_occupied_table_is_rejected`-style tests in `test_tables.py` set
      up blocking state directly (AC3).
    - Editing an `in_preparation` item is rejected 409 with `"Rejected, item not pending"` (AC4).
    - Editing/cancelling a `ready` or already-`cancelled` item is rejected 409 (edit: "not pending";
      cancel: "not cancellable") — `ready` reachable only via direct `db_session` state-setting
      (Epic 5 hasn't built the transition into it yet), `cancelled` reachable by cancelling first
      then cancelling/editing again.
    - Editing/cancelling a nonexistent item id is rejected 404.
    - Editing/cancelling an item id that belongs to a **different** Order is rejected 404, not
      silently applied (Task 6's cross-Order check, the one novel piece of this story's `_get_item`
      seam — write the wrong implementation once, confirm this test goes red, per this codebase's
      "make it fail first" testing rule, then fix it and confirm green).
    - Warehouse Manager cannot edit or cancel (403, matches the existing
      `test_warehouse_manager_cannot_use_order_item_endpoints` precedent, extended to the two new
      routes).
    - Cook and Admin **cannot** edit (403 — edit stays Waiter-only, unlike cancel).
    - Unauthenticated requests to both new routes are rejected 401.
    - **Guarded-UPDATE race test for both transitions**, mirroring `test_orders.py`'s own
      `test_race_between_two_opens_only_one_succeeds` pattern (`monkeypatch` `OrderService._get_item`
      so a second request commits the item to `in_preparation`/`cancelled` strictly between this
      request's read and its guarded UPDATE): confirm the edit and the cancel each correctly lose
      the race with a 409 when the item's state changes out from under them mid-request, not merely
      when it was already in that state before the request started (AC1/AC4, AC2/AC3).
    - Last-write-wins on two sequential edits from different actors, both succeed, second value
      wins, no conflict response (AC6).
  - [x] `frontend/src/pages/waiter/TableOrderDetailPage.test.tsx` — mirror the existing style. New
    tests for: editing a pending item's quantity/note (both submitted, matching
    `TablesSetupPage.test.tsx`'s "always sends both fields" regression-test precedent); cancelling a
    pending item with no confirm step (button click alone triggers the request); cancelling an
    in_preparation item requires the confirm reveal first (clicking Cancel alone must **not** call
    the endpoint, only the subsequent Confirm click does — assert the mutation's `mutationFn` fires
    exactly once, at the right click); an in_preparation row has no Edit control at all; a
    `ready`/`cancelled` row has no action controls at all; a 409 on edit/cancel renders inline, not
    silently.
  - [x] Full regression: `uv run pytest` from `backend/`, `pnpm test` from `frontend/`, `npx tsc -b`.

## Dev Notes

### Architecture compliance

- **AD-6** (guarded, atomic OrderItem status transitions): both `edit_item` and `cancel_item` are
  guarded UPDATEs on `status`, the third and fourth applications of this pattern after
  `TableService.update_table` and `OrderService.open_table`. Trap 18's two sharp edges both apply
  here too: (a) do not add a short-circuit "nothing changed" early return that skips the guard —
  Story 2.4's review caught exactly this bug; (b) the race test must change the item's state
  *between* the read and the write via a monkeypatched read step, not merely before the request
  starts, or it proves nothing (see Task 12).
- **AD-11** (cancel/void as a status transition, no auto-reversal): `cancel_item` contains zero
  stock/`StockMovement` code. This is a prohibition, not a feature to build — do not add a
  compensating movement, do not add a TODO for one, AD-11 explicitly rejects that shape.
- **NFR-6** (last-write-wins, no optimistic locking): `edit_item`'s guarded UPDATE guards on
  `status`, never on the fields being edited (`quantity`/`notes`) or a version/timestamp column —
  two overlapping edits from different actors both succeed sequentially, whichever commits last
  wins, exactly as AC6 requires. Do not add a version column or a conflict check on the edited
  fields themselves, that would be optimistic locking NFR-6 explicitly rules out.
- **AD-9** (Role-level-only permissions): `OrderItemCancelDep`'s three-Role grant is still
  Role-level, not per-resource — any Waiter/Cook/Admin can cancel any Order Item, not just "their
  own." No filtering logic to add.

### Current state of the files this story touches (read before editing)

- **`backend/data_models/order.py`**: `OrderItemStatus` is currently `pending`/`in_preparation`/
  `ready` (3 members). `CreateOrderItemRequest` (the shape `UpdateOrderItemRequest` should closely
  mirror) sits right above `OrderItemResponse`. `UpdateTableRequest` (a few classes above) is the
  *wrong* shape to mirror for this story specifically, it solves a genuine partial-update problem
  Table edits have that Order Item edits do not, see Task 3's own reasoning for why.
- **`backend/services/order_service.py`**: `OrderService.__init__` already takes `logger` and
  `realtime_service` (Story 3.3). `_get_order`/`_get_table` are the two existing `_get_*` seams to
  match exactly in shape for the new `_get_item`. Neither `edit_item` nor `cancel_item` should call
  `self._realtime_service.broadcast(...)` anywhere, per this story's own explicit "no live
  broadcast" scope note above.
- **`backend/api/orders.py`**: `OrdersDep` (waiter-only) and `OrderIdPath`/`TableIdPath` (both
  `Annotated[int, Path(gt=0, le=_INT4_MAX)]`) already exist and are reused as-is for the edit
  route; only `ItemIdPath` and the new three-Role `OrderItemCancelDep` are new. `_ITEM_ERROR_DESCRIPTIONS`
  is the existing dict shape the two new per-route dicts extend.
- **`frontend/src/pages/waiter/TableOrderDetailPage.tsx`**: the Order Item `<Table>` currently
  renders exactly 5 columns (Status, Dish, Note, Qty, Price), no Actions column, confirmed by
  reading the file in full. `parseQuantity`/`MAX_ORDER_ITEM_QUANTITY`/`errorMessage` all already
  exist in this file and should be reused, not reimplemented, for the edit form's own validation.
- **`frontend/src/services/orderService.ts`**: `orderItemsQueryKey` is already exported (Story 3.3).
  `useAddOrderItem`'s `onSettled` shape is the direct precedent for both new mutations.

### Project Structure Notes

Files touched:
- `backend/data_models/order.py` — **UPDATE**, `cancelled` added to `OrderItemStatus`, new
  `UpdateOrderItemRequest`.
- `backend/alembic/versions/<new>_add_cancelled_to_orderitemstatus.py` — **NEW**.
- `backend/exceptions/__init__.py` — **UPDATE**, 3 new exception classes.
- `backend/services/order_service.py` — **UPDATE**, `edit_item`, `cancel_item`, `_get_item` added.
- `backend/api/orders.py` — **UPDATE**, 2 new routes, `OrderItemCancelDep`, `ItemIdPath`.
- `backend/tests/test_orders.py` — **UPDATE**, new tests per Task 12.
- `frontend/src/types/order.ts` — **UPDATE**, `"cancelled"` added to the status union.
- `frontend/src/components/orders/OrderItemStatusBadge.tsx` — **UPDATE**, `cancelled` entry in all
  three maps.
- `frontend/src/services/orderService.ts` — **UPDATE**, `useEditOrderItem`/`useCancelOrderItem`.
- `frontend/src/pages/waiter/TableOrderDetailPage.tsx` — **UPDATE**, Actions column, edit/cancel UI.
- `frontend/src/pages/waiter/TableOrderDetailPage.test.tsx` — **UPDATE**, new tests per Task 12.

No new backend route *file* (extends `api/orders.py`), no `container.py`/`main.py` change, no new
frontend route, no new frontend page/component file beyond what's listed.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 3.4`] — this story's AC source
- [Source: `_bmad-output/implementation-artifacts/3-3-view-live-order-and-table-status.md`] —
  previous story; confirms `TableOrderDetailPage.tsx`'s exact current shape and the "no live
  broadcast unless the AC says so" precedent this story's own scope note applies
  [Source: `_bmad-output/implementation-artifacts/3-2-add-items-to-an-order.md`] — the story whose
  own scope note explicitly deferred the Actions column to this one
- [Source: `backend/services/table_service.py`, `backend/services/order_service.py`] — the
  guarded-UPDATE reference implementations (trap 18) `edit_item`/`cancel_item` both follow
- [Source: `backend/tests/test_tables.py::test_race_between_form_load_and_save_is_rejected`,
  `backend/tests/test_orders.py::test_race_between_two_opens_only_one_succeeds`] — the
  mid-request-race test pattern Task 12's two new race tests must mirror, not merely
  pre-setting-blocking-state
- [Source: `frontend/src/pages/admin/UsersPage.tsx`] — the in-row confirm-reveal precedent (Story
  1.6's review settled this over a modal) for the in_preparation cancel confirm
- [Source: `frontend/src/pages/admin/TablesSetupPage.tsx`, `TablesSetupPage.test.tsx`] — the
  "always send both fields, never diff against cache" rule and its regression-test shape, applied
  to the edit form here
- [Source: `_bmad-output/project-context.md`, trap 18, trap 20, "Domain rules worth restating"] —
  the guarded-UPDATE two sharp edges, the rollback-before-lazy-read ordering, and the "no live
  broadcast unless the AC asks for it" rule this story's scope note relies on

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5

### Debug Log References

- `uv run pytest tests/test_orders.py -q` — 51 passed
- `uv run pytest -q` (full backend suite) — 270 passed, 17 warnings, no regressions
- `pnpm vitest run src/pages/waiter/TableOrderDetailPage.test.tsx` — 19 passed
- `pnpm test` (full frontend suite) — 140 passed
- `npx tsc -b` — clean

### Completion Notes List

- Added `cancelled` to the `OrderItemStatus` Postgres enum via a hand-written Alembic migration
  (autogenerate produces an empty upgrade for enum-value additions); `downgrade()` intentionally
  raises `NotImplementedError` since Postgres cannot cleanly remove an enum value (AC7).
- `edit_item`/`cancel_item` on `OrderService` follow the established guarded-UPDATE pattern
  (AD-6/trap 18): `UPDATE ... WHERE status IN (...)`, rowcount-checked, never read-then-write.
  `_get_item` is a new private seam mirroring `_get_order` but checking two ids (item id and that
  it belongs to the given order).
- AC2/AC3: cancel is permitted from `pending` or `in_preparation`; per AD-11 there is deliberately
  no automatic stock-reversal compensating movement on cancel.
- AC4: edit is only permitted while `status == pending`; the guard clause itself (not extra
  application code) rejects edits once an item has moved to `in_preparation`/`ready`/`cancelled`.
- AC5 (cancelled items excluded from aggregate reads) required no new code: no aggregate-status
  derivation exists yet in the codebase (that lands with Epic 5's Order.status work). `list_items`
  is left unfiltered on purpose so a Waiter can still see that a line was cancelled instead of it
  silently disappearing.
- AC6 (last-write-wins) required no new code either — proven by construction, since the guarded
  UPDATE's WHERE guards only on `status`, never on the edited fields (`quantity`/`notes`). Verified
  with `test_last_write_wins_on_two_sequential_edits`.
- Backend permission grant is 3 roles (`waiter`, `cook`, `admin`) for cancel per FR-7; only the
  Waiter-facing `TableOrderDetailPage` got a frontend wiring in this story, since no Cook/Admin
  order-viewing screen exists yet (Kitchen Display is Epic 5) — precedented by `InventoryWriteDep`
  shipping before Admin's own inventory UI landed (Stories 2.1→2.6). This is not a parity gap: the
  instruction is to not leave *reachable* frontend surface unwired, and no such surface exists yet
  for Cook/Admin order actions.
- `OrderItemRow` intentionally owns its own `useEditOrderItem`/`useCancelOrderItem` mutation
  instances (per-row, not shared from the page), unlike `TablesPage.tsx`'s single shared
  page-level mutation — editing item A and cancelling item B are independent actions, whereas
  "open" is inherently page-level-exclusive.
- Cancel confirmation uses the codebase's existing in-row confirm-reveal pattern (no modal),
  precedented by `UsersPage.tsx`'s "Deactivate {name}?" Confirm/Cancel swap.
- Two bugs were caught and fixed during implementation, neither required a scope or design
  change: a hardcoded admin username in the `_create_table` test helper collided across two new
  cross-order tests (fixed by deriving the username from the already-unique `table_number`); and
  an RTL `getByLabelText` ambiguity once the row-edit form and the always-present add-item form
  both render "Qty"/"Note (optional)" labels on screen simultaneously (fixed with
  `getAllByLabelText` + explicit last-element indexing, avoiding `Array.prototype.at()` since this
  project targets ES2020).

### File List

- `backend/data_models/order.py`
- `backend/data_models/__init__.py`
- `backend/alembic/versions/856ef9ffb5cd_add_cancelled_to_orderitemstatus.py`
- `backend/exceptions/__init__.py`
- `backend/services/order_service.py`
- `backend/api/orders.py`
- `backend/tests/test_orders.py`
- `frontend/src/types/order.ts`
- `frontend/src/components/orders/OrderItemStatusBadge.tsx`
- `frontend/src/services/orderService.ts`
- `frontend/src/pages/waiter/TableOrderDetailPage.tsx`
- `frontend/src/pages/waiter/TableOrderDetailPage.test.tsx`

## Change Log

| Date | Change |
|---|---|
| 2026-08-15 | Implemented Story 3.4: edit/cancel order items (backend `edit_item`/`cancel_item`, `cancelled` enum migration, PATCH/POST routes; frontend `OrderItemRow` edit/cancel UI on `TableOrderDetailPage`). 21 new backend tests (270 total), 7 new frontend tests (19 total in this file). |
| 2026-08-15 | Code review patch pass: fixed `notes` field silently omitted (sent as `undefined`) instead of explicit `null` when a note is cleared; fixed a dead-end where a row stuck mid-edit lost all action buttons if its item transitioned away from `pending` under it; renamed the discard-edit button from ambiguous duplicate "Cancel" to "Back"; cleared stale mutation error state on discard/back. 2 new regression tests added (142 total frontend, up from 140 pre-review-patch). |

## Review Findings

Reviewed by three parallel agents (Blind Hunter, Edge Case Hunter, Acceptance Auditor) against
this story's 7 ACs and `_bmad-output/project-context.md`. All three independently converged on the
same core defect (see below), which is strong signal it was real.

**Fixed during this review:**

- **`notes` silently omitted instead of sent as explicit `null` when a Waiter clears a note**
  (`frontend/src/pages/waiter/TableOrderDetailPage.tsx`, `handleSaveEdit`) — flagged independently
  by all three agents. `JSON.stringify` drops object keys whose value is `undefined`, so clearing
  an existing note produced a PATCH body with no `notes` key at all, violating this story's own
  "always send both fields explicitly" instruction (Task 11). Not a live bug today only because
  `UpdateOrderItemRequest.notes` defaults to `None` on an absent key, but a real deviation from the
  stated convention. Fixed: `notes: trimmedNotes === "" ? null : trimmedNotes`. New regression test:
  `sends an explicit null, not an omitted field, when a note is cleared to empty`.
- **Dead-end: a row stuck mid-edit rendered no action buttons at all if its item's status changed
  away from `pending` while the edit form was open** (Edge Case Hunter) — e.g. another actor
  cancels the same item while this Waiter has it open for edit. The Qty/Note `TextField`s were
  gated on `isEditing` alone, but the Save/Back buttons were gated on `isEditing && status ===
  "pending"`, so once status left `pending` the editable fields kept rendering with no way to save
  or exit. Fixed by gating the `TextField`s on the same `isEditing && item.status === "pending"`
  condition as the action buttons, so the row correctly falls back to read-only display.
- **Two visually-identical "Cancel" buttons with the same accessible name could appear on screen
  simultaneously** (Blind Hunter) — the discard-edit button and a different pending row's
  cancel-the-item button were both labeled "Cancel," indistinguishable to a screen reader/keyboard
  user, and ambiguous for any `getByRole` query on a multi-pending-item order. Renamed the
  discard-edit button to "Back," matching this codebase's own existing discard-affordance
  precedent (`UsersPage.tsx`'s reveal-confirm "Back"/"Confirm" pair, already reused elsewhere in
  this same row for the in_preparation confirm).
- **Stale error banner survived discarding the action that caused it** (Blind Hunter) — neither
  mutation was ever `.reset()`, so backing out of a failed edit or cancel left the row's error
  `Alert` rendering underneath the now-read-only row, describing an action no longer in progress.
  Fixed: discard/back handlers now call `editMutation.reset()`/`cancelMutation.reset()`. New
  regression test: `discarding an edit clears the row back to read-only with no stale error`.

**Verified as non-issues:**

- The cross-cutting "every backend functionality also in the frontend" concern (this story's own
  goal instruction) — independently re-verified by the Acceptance Auditor by reading
  `frontend/src/pages/cook/KitchenDisplayPage.tsx` directly: it is still a bare placeholder with no
  Order/OrderItem data or hooks, and no `admin/*` page shows Order data either. The Waiter-only
  frontend wiring for the 3-role (`waiter`/`cook`/`admin`) backend cancel grant is not a parity
  gap — there is no reachable Cook/Admin order surface yet to wire it into.
- The Alembic migration's safety claim (`ALTER TYPE ... ADD VALUE`) was flagged as "reasoned about,
  not verified" — this is inaccurate; it was applied live via `uv run alembic upgrade head` and
  confirmed via `uv run alembic heads` during implementation (see Debug Log References).
- Two Change Log inaccuracies caught by the Acceptance Auditor (test counts stated as file totals
  rather than new-test counts) — corrected above.

**Deferred (test-coverage gaps and minor polish, non-blocking, see `deferred-work.md`):** no
regression test proving `edit_item`/`cancel_item` never broadcast; no positive AD-9 cross-Waiter
cancel test; three near-identical role-cancel tests not collapsed into one parametrized test;
`UpdateOrderItemRequest.notes` doesn't normalize an explicit `""` to `None` server-side.

