---
baseline_commit: f1b7cd7eb2a48fb9db0437027f86a34c72a76c5a
epic: 5
story: 2
---

# Story 5.2: Pick Up and Progress an Order Item, with Atomic Stock Deduction

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Cook,
I want to pick up a pending item and later mark it ready,
so that the kitchen's prep state is accurate and stock reflects real consumption the moment it starts.

## Scope note (read first)

**This story adds the two write transitions the Kitchen Display has been missing since 5.1: `pending`
→ `in_preparation` (pick up) and `in_preparation` → `ready` (mark ready/"passed").** 5.1 built a
read-only board; this story is what makes its cards clickable. Do not touch `KitchenService` or
`GET /api/kitchen/items` — that route stays exactly as 5.1 left it, this story only adds new write
endpoints.

**Where the new logic lives — a deliberate decision, not left to be discovered mid-implementation:**

- The two transitions belong on **`OrderService`**, not `KitchenService`. `OrderService` already owns
  every other `OrderItem` transition (`add_item`, `edit_item`, `cancel_item`); `KitchenService` is
  explicitly config-free/read-only (5.1's own docstring: *"holds no `realtime_service` collaborator,
  since it never broadcasts anything itself"*). Adding a `realtime_service` dependency to
  `KitchenService` now just to broadcast a status change would fight that story's own stated design,
  not extend it.
- **`OrderService` gains a new constructor dependency: `InventoryService`.** The stock deduction this
  story requires (FR-13) needs the exact same row-lock-then-decrement-then-insert-`StockMovement`
  shape `InventoryService.record_movement` already implements (trap 9) — reuse it, don't duplicate it.
  But `record_movement` commits its own transaction and its `CreateStockMovementRequest` payload
  explicitly rejects `movement_type=consumption` (*"consumption is recorded automatically and cannot
  be logged manually"*) — it cannot be called as-is from inside a pick-up that must also atomically
  update `OrderItem.status` and `cook_id` in the **same** transaction (AD-6, NFR-3). So:
  **add a new `InventoryService.apply_consumption(db, ingredient_id, quantity, actor_id, order_id) ->
  bool` method** — same row lock (`_lock_ingredient`), same `was_low`/`is_low` crossing computation,
  same never-floor-capped-at-zero decrement (AD-16), inserts a `StockMovement(movement_type=consumption,
  reference_id=order_id, performed_by=actor_id)` — but **does not commit** (the caller's transaction
  owns the commit) and **does not broadcast** the low-stock alert itself (a broadcast fired before the
  encompassing transaction commits would tell a Warehouse Manager's browser to refetch data that isn't
  visible yet). It returns `True` if this movement crossed the shortage threshold in either direction,
  so the caller can broadcast `inventory.alerts_changed` **after** its own commit succeeds — this is
  the same event `record_movement` already broadcasts (Story 4.2), reused verbatim, not a second event
  invented for this path.
- **Container ordering (trap 23 applies for real this time):** `order_service` currently sits
  **above** `inventory_service` in `backend/container.py` (declared first, since neither previously
  depended on the other). Once `OrderService.__init__` takes `inventory_service` as a parameter,
  `order_service`'s provider **must move below** `inventory_service`'s — the existing comment above
  `order_service` in `container.py` ("order_service and inventory_service must stay below
  realtime_service... any future provider that depends on another must be declared after it, the same
  way") is telling you exactly this rule now applies to `order_service` itself, not just
  `realtime_service`.
- **New endpoints, not new routes on `api/kitchen.py`.** Both transitions act on an `OrderItem`
  identified by `(order_id, item_id)`, exactly like `edit_item`/`cancel_item` already do — add them to
  the **existing** `backend/api/orders.py` router (mirroring `PATCH .../items/{item_id}` and `DELETE
  .../items/{item_id}` shape), not a new file. The Kitchen Display's own frontend service
  (`kitchenService.ts`) can still be the thing that calls them, but the backend route itself belongs
  to the `orders` domain, matching where the underlying mutation actually happens.
- **New event name:** broadcast `order.item_status_changed` (past-tense, `{domain}.{event}`, AD-2 —
  this is the literal example event name Story 1.5's own architecture spec uses) to
  `[UserRole.waiter, UserRole.cook]`, same recipients as `order.item_added`, so both the Waiter's
  Table Order Detail page and every Cook's Kitchen Display update from one broadcast (AC8's own
  wording: *"the status badge updates on both the Kitchen Display and the Waiter's screen via the same
  WebSocket push"*).

## Acceptance Criteria

1. **Given** a `pending` Order Item, **when** a Cook picks it up, **then** in one atomic DB
   transaction: the item moves to `in_preparation`, the acting Cook is recorded against it, each
   Recipe Ingredient's quantity (times the item's quantity) is deducted from stock, and a
   `consumption` Stock Movement referencing the Order is recorded (FR-10, FR-13, AD-6, NFR-3, NFR-4).
2. **Given** that same transition is not re-triggered, **when** a Cook picks up an item once, **then**
   deduction happens exactly once, re-triggering does not double-deduct (FR-13, AD-6).
3. **Given** an `in_preparation` Order Item, **when** a Cook marks it ready ("passed"), **then** it
   moves to `ready` as a pure status change with no further stock movement (FR-10).
4. **Given** an Order Item is `pending`, **when** any attempt is made to move it directly to `ready`,
   **then** it is rejected, it cannot skip `in_preparation` (FR-10).
5. **Given** an Order Item is `in_preparation` or `ready`, **when** any attempt is made to reverse its
   transition, **then** it is rejected, no undo; correction goes through Epic 3's cancel path (FR-10).
6. **Given** a deactivated Cook has an `in_preparation` item, **when** any other active Cook views the
   Kitchen Display, **then** they can transition that item to `ready` themselves (FR-10, attribution
   not access lock).
7. **Given** a pick-up would deduct more of an Ingredient than currently in stock, **when** the
   transition commits, **then** it still succeeds (stock is never floor-capped at zero, AD-16), and
   the resulting `consumption` movement triggers Epic 4's existing Low-Stock Alert check exactly as a
   manual movement would (FR-13, reuses FR-14, no new alert logic built here).
8. **Given** an Order Item on a Kitchen Display card, **when** a Cook advances its status, **then**
   the advance control is a single large click target sized for reading at a distance (UX-DR19), and
   the status badge updates on both the Kitchen Display and the Waiter's screen via the same WebSocket
   push (AD-2).

## Tasks / Subtasks

- [x] **Task 1: Backend — new exception for the mark-ready guard**
  - [x] Add `OrderItemNotInPreparationError(ConflictError)` to `backend/exceptions/__init__.py`
    (mirrors `OrderItemNotPendingError`'s shape, wording adjusted: *"Order Item is not in
    preparation"*). `OrderItemNotPendingError` is reused as-is for the pick-up guard (AC4) — its
    existing wording already fits ("item is not pending"), no new class needed there.
- [x] **Task 2: Backend — `InventoryService.apply_consumption`** (AC1, AC2, AC7)
  - [x] `backend/services/inventory_service.py`: new method `async def apply_consumption(self, db:
    AsyncSession, ingredient_id: int, quantity: Decimal, actor_id: int, order_id: int) -> bool`.
    Reuses `self._lock_ingredient(db, ingredient_id)` (trap 9, same row lock `record_movement`
    already uses). Computes `was_low = ingredient.current_stock < ingredient.min_stock_threshold`
    *before* applying the delta. Decrements `ingredient.current_stock -= quantity` (never
    floor-capped, AD-16 — matches `record_movement`'s own unclamped delta application). Inserts
    `StockMovement(ingredient_id=ingredient_id, movement_type=MovementType.consumption,
    quantity_change=-quantity, reference_id=order_id, performed_by=actor_id)` via `db.add(...)`.
    **Does not call `db.commit()`** — the caller (`OrderService.pick_up_item`) owns the single
    transaction this participates in. Returns `was_low != is_low` computed off the in-memory,
    not-yet-committed `ingredient.current_stock` (safe: this is the same object `_lock_ingredient`
    already returned, mutated in place, no extra read needed) so the caller can decide whether to
    broadcast after its own commit.
  - [x] `IngredientNotFoundError` propagates uncaught if `ingredient_id` doesn't exist — a
    `RecipeIngredient` row pointing at a deleted `Ingredient` should not be possible today (no
    Ingredient-delete endpoint exists anywhere in this codebase), but the caller does not need to
    catch this defensively; let it surface as-is, consistent with every other `_get_*`-style helper
    in this codebase.
- [x] **Task 3: Backend — `OrderService.pick_up_item`** (AC1, AC2, AC4, AC7, AC8)
  - [x] `backend/services/order_service.py`: `OrderService.__init__` gains
    `inventory_service: InventoryService` as a new constructor parameter, stored as
    `self._inventory_service`. Update its class docstring to mention the new collaborator (mirrors
    how the class docstring already documents `realtime_service`'s role).
  - [x] New method `async def pick_up_item(self, db: AsyncSession, actor: User, order_id: int,
    item_id: int) -> OrderItem`:
    - `item = await self._get_item(db, actor, order_id, item_id)` (existing helper, unchanged).
    - Guarded UPDATE (AD-6, same shape as `edit_item`): `update(OrderItem).where(OrderItem.id ==
      item_id, OrderItem.status == OrderItemStatus.pending).values(status=
      OrderItemStatus.in_preparation, cook_id=actor.id)`. `rowcount == 0` →
      `await db.rollback()`, raise `OrderItemNotPendingError()` (AC4 — this single guard is also
      what rejects a re-trigger on an already-`in_preparation`/`ready`/`cancelled` item, AC2/AC5,
      since the guard's precondition is `status == pending` regardless of what the current status
      actually is).
    - Fetch this item's Recipe Ingredients: `select(RecipeIngredient).where(RecipeIngredient.dish_id
      == item.dish_id)` (same query `MenuService.list_recipe_ingredients` runs, inlined here rather
      than adding a `MenuService` dependency purely for one read — `OrderService` already imports
      `Dish` directly in `add_item` without going through `MenuService`, same precedent).
    - For each `RecipeIngredient` row: `crossed = await self._inventory_service.apply_consumption(db,
      ri.ingredient_id, ri.quantity * item.quantity, actor.id, order_id)` — collect
      `(ri.ingredient_id, crossed)` pairs for the post-commit broadcast step. `ri.quantity *
      item.quantity` is a per-serving `Decimal` times an integer `quantity` column — confirm the
      multiplication's result type matches what `apply_consumption`/`StockMovement.quantity_change`
      expects (`Numeric(10,3)`).
    - `await db.commit()` — the guarded `OrderItem` UPDATE and every `apply_consumption` call's
      `Ingredient` decrement + `StockMovement` insert land in this single commit (AC1's "one atomic
      DB transaction").
    - `await db.refresh(item)`.
    - Log at `INFO`: order_id, item_id, cook (actor.id), dish_id, ingredient count deducted.
    - Broadcast `order.item_status_changed` to `[UserRole.waiter, UserRole.cook]` with
      `OrderItemResponse.model_validate(item).model_dump(mode="json")` (AC8 — same payload shape
      `add_item`'s `order.item_added` already uses, reused verbatim).
    - For each `(ingredient_id, crossed)` pair where `crossed` is `True`, broadcast
      `inventory.alerts_changed` to `[UserRole.warehouse_manager]` with `{"ingredient_id":
      ingredient_id}` — same event/payload shape `InventoryService.record_movement` already
      broadcasts (AC7, reuses FR-14, "no new alert logic built here" per this story's own AC
      wording). Loop, not a single call, since a multi-ingredient Dish's pick-up could cross the
      threshold for more than one Ingredient in the same transaction.
    - Return `item`.
- [x] **Task 4: Backend — `OrderService.mark_item_ready`** (AC3, AC5, AC6, AC8)
  - [x] New method `async def mark_item_ready(self, db: AsyncSession, actor: User, order_id: int,
    item_id: int) -> OrderItem`:
    - `item = await self._get_item(db, actor, order_id, item_id)`.
    - Guarded UPDATE: `update(OrderItem).where(OrderItem.id == item_id, OrderItem.status ==
      OrderItemStatus.in_preparation).values(status=OrderItemStatus.ready)` — **no `cook_id`
      reassignment**: the Cook recorded is whoever picked the item up, marking it ready does not
      overwrite that attribution even when a different Cook performs this step (AC6 — "attribution
      not access lock", any active Cook can call this regardless of whose `cook_id` is already set;
      the route's own role dependency, not this method, is what decides who may call it at all).
      `rowcount == 0` → `await db.rollback()`, raise `OrderItemNotInPreparationError()` (AC4's
      pending→ready-skip case and AC5's reverse-transition case both hit this same guard: neither
      `pending` nor `ready` nor `cancelled` satisfies `status == in_preparation`).
    - `await db.commit()`, `await db.refresh(item)`.
    - Log at `INFO`: order_id, item_id, actor.id (the Cook marking it ready, which may differ from
      `item.cook_id`).
    - Broadcast `order.item_status_changed` (same event/payload/recipients as Task 3) — **no**
      `inventory.alerts_changed` broadcast here, this transition never touches stock (AC3).
    - Return `item`.
- [x] **Task 5: Backend — routes** (AC1–AC8)
  - [x] `backend/api/orders.py`: two new routes alongside the existing `PATCH
    /{order_id}/items/{item_id}` (edit) and `DELETE /{order_id}/items/{item_id}` (cancel):
    - `POST /{order_id}/items/{item_id}/pick-up`, `response_model=OrderItemResponse`, calls
      `order_service.pick_up_item(db, actor, order_id, item_id)`.
    - `POST /{order_id}/items/{item_id}/mark-ready`, `response_model=OrderItemResponse`, calls
      `order_service.mark_item_ready(db, actor, order_id, item_id)`.
    - Both gated by a Cook-or-Admin dependency — check whether an existing dependency in this file
      already grants exactly `(cook, admin)` (unlikely, `orders.py`'s existing deps are
      Waiter-oriented) or whether a new one is needed here, matching `KitchenReadDep`'s shape from
      `api/kitchen.py` (`Depends(require_role(UserRole.cook, UserRole.admin))`) but as a
      write-capable dependency name distinct from any existing `OrdersDep`/`OrdersReadDep` in this
      file — do not widen an existing Waiter-scoped dependency to include Cook just to avoid adding
      one.
  - [x] Router-level logging: request received/rejected at INFO/WARNING per CLAUDE.md's logging
    convention, matching the existing edit/cancel routes' own log lines in this file.
- [x] **Task 6: Backend — container wiring** (AC1)
  - [x] `backend/container.py`: move `order_service`'s provider declaration to **below**
    `inventory_service`'s (trap 23 — `order_service` now depends on `inventory_service`, so it must
    be declared after it, the same rule the file's own existing comment already states for
    `realtime_service`). Add `inventory_service=inventory_service` to `order_service`'s
    `providers.Factory(...)` call. Update the file's own ordering comment to mention this new
    dependency explicitly, not just describe the old `realtime_service`-only constraint.
- [x] **Task 7: Backend tests** (`backend/tests/test_orders.py`, extend existing file — this is
  still the `orders` domain, not a new test file)
  - [x] Pick-up (AC1): a `pending` item picked up by a Cook moves to `in_preparation`, `cook_id` is
    set to the acting Cook, each Recipe Ingredient's `current_stock` decreases by `quantity ×
    item.quantity`, and a `consumption` StockMovement is recorded with `reference_id == order_id`.
  - [x] Pick-up, multi-ingredient Dish: a Dish with two+ Recipe Ingredients, picked up once, deducts
    from both Ingredients and inserts one StockMovement per Ingredient (not one combined row).
  - [x] No double-deduction (AC2): picking up the same item twice — second attempt is rejected
    (409), `current_stock` reflects only one deduction, only one `consumption` StockMovement exists
    for that item/Ingredient pair.
  - [x] Mark-ready (AC3): an `in_preparation` item marked ready moves to `ready`, no new
    StockMovement row is created, `current_stock` is unchanged by this call.
  - [x] Skip-ahead rejected (AC4): a `pending` item's mark-ready attempt is rejected 409, status
    stays `pending`.
  - [x] Reverse transitions rejected (AC5): an `in_preparation` item's pick-up attempt (already past
    pending) is rejected 409; a `ready` item's mark-ready attempt is rejected 409; a `ready` item's
    pick-up attempt is rejected 409.
  - [x] Attribution not access lock (AC6): Cook A picks up an item (`cook_id == A`); Cook B (a
    different active Cook) successfully marks it ready; `cook_id` remains `A` after the mark-ready
    call, not overwritten to `B`.
  - [x] Deactivated Cook's item (AC6): an item picked up by a Cook who is then deactivated (`user.
    is_active = False`, matching however this codebase already models deactivation, check
    `UserService`) can still be marked ready by a different active Cook — the deactivated Cook's own
    session/token being rejected on other endpoints is out of scope here, only this specific
    transition's own guard matters.
  - [x] Below-stock pick-up still succeeds (AC7): an Ingredient with `current_stock` less than the
    Dish's Recipe requirement, picked up anyway, succeeds; resulting `current_stock` goes negative
    (or below zero-floor, whichever this Ingredient's starting value implies) and is not clamped.
  - [x] Low-stock alert crossing on pick-up (AC7): an Ingredient starting **above**
    `min_stock_threshold`, deducted below it by a pick-up, triggers `inventory.alerts_changed`
    broadcast to a connected `warehouse_manager` (mirror `test_inventory.py`'s existing crossing
    test for `record_movement`, same assertion shape, different trigger). A pick-up that does
    **not** cross the threshold (already low before, still low after, or stays comfortably above)
    broadcasts nothing — assert absence, not just presence, matching `record_movement`'s own
    non-crossing test.
  - [x] Role coverage: cook and admin can each call pick-up/mark-ready; waiter and warehouse_manager
    are rejected 403 on both routes; unauthenticated is rejected 401.
  - [x] Not-found coverage: pick-up/mark-ready on a nonexistent `item_id`, or an `item_id` that
    exists but belongs to a different `order_id`, is rejected 404 (reuses `_get_item`'s existing
    behavior — a lower-cost test than exhaustively re-testing `_get_item` itself, just confirm
    these two new routes wire it in).
  - [x] `order.item_status_changed` broadcast (extend `test_websocket.py` or add here, matching
    however `order.item_added`'s own test is organized): both a Waiter and a Cook socket receive
    the broadcast on pick-up and on mark-ready; a `warehouse_manager` socket does not receive
    `order.item_status_changed` (it's not in the recipient list).
  - [x] Concurrency guard (trap 18's "a real concurrency test must change the state *between* the
    service's read and its write"): two concurrent pick-up calls on the same `pending` item — only
    one succeeds, the other gets 409, `current_stock` reflects exactly one deduction (mirrors
    whatever pattern this codebase's existing race tests already use for `open_table`/`edit_item`,
    e.g. monkeypatching the read step to interleave a second write).
- [x] **Task 8: Frontend — types and service hooks** (AC1, AC3, AC8)
  - [x] `frontend/src/services/orderService.ts` (existing file — extend, do not create a new
    service file for this): add `usePickUpItem(orderId: number): UseMutationResult<OrderItem, Error,
    number>` and `useMarkItemReady(orderId: number): UseMutationResult<OrderItem, Error, number>` (or
    a single parameterized hook if this file already has a precedent for that shape — check
    `useEditOrderItem`/`useCancelOrderItem`'s existing signatures first and match them exactly, do
    not invent a new hook-shape convention). Both `POST` to the new routes from Task 5. Invalidate
    whatever query keys the Kitchen Display and Table Order Detail page both read from on success —
    check how `useCancelOrderItem` already invalidates across both surfaces, if it does, and mirror
    that; if it doesn't yet (cancel might only affect the Waiter's own page), this is the first
    mutation whose effect must be visible on **two** independently-query-cached pages, so lean on
    the live WebSocket invalidation (Task 9) rather than an aggressive multi-key `invalidateQueries`
    call from the mutation itself — the pattern this codebase uses elsewhere is "the live event is
    what refreshes other pages, not the mutating page's own success handler."
- [x] **Task 9: Frontend — `KitchenDisplayPage.tsx` action buttons** (AC8)
  - [x] Each `pending` row gets a "Pick up" button; each `in_preparation` row gets a "Mark ready"
    button; `ready` rows get no button (matches the mockup, `mockups/key-kitchen-display.html`'s
    `.action-btn` labels). Button is a single large MUI `Button` (UX-DR19 — "single large click
    target sized for reading at a distance"), primary/accent variant per DESIGN.md's "MUI defaults
    plus one accent color" rule (the only place this codebase uses a non-stock `Button` variant).
  - [x] Wire each button to `usePickUpItem`/`useMarkItemReady`; disable the button (not hide it)
    while its own mutation is pending, matching whatever loading-state convention
    `TableOrderDetailPage.tsx`'s existing edit/cancel buttons already use.
  - [x] Subscribe to `order.item_status_changed` (new subscription, alongside the existing
    `order.item_added` one) and invalidate `KITCHEN_ITEMS_QUERY_KEY` on receipt — same
    refetch-signal pattern as every other subscriber in this codebase, not a direct cache merge.
  - [x] Inline error on a failed pick-up/mark-ready call (UX-DR17's "inline, non-toast" convention)
    — do not add a toast/snackbar system that doesn't exist elsewhere in this codebase.
- [x] **Task 10: Frontend — `TableOrderDetailPage.tsx`** (AC8)
  - [x] This page must also reflect a Cook's pick-up/mark-ready action live, since AC8 requires
    "the status badge updates on both the Kitchen Display and the Waiter's screen via the same
    WebSocket push." Read this file's current `order.item_added`/other subscriptions first (it
    already listens for at least one event, per 5.1's Dev Notes reference to its own
    `useRealtime().subscribe` shape) — add a subscription to `order.item_status_changed` here too,
    invalidating whatever query key drives this page's own Order Item list, so a Waiter sees a
    status badge change without a manual refresh. This page does **not** get pick-up/mark-ready
    buttons itself (those are Cook-only, Kitchen-Display-only, per this story's own user statement
    "As a Cook") — read-only badge update here, same as how the Kitchen Display was read-only for
    everything in 5.1.
- [x] **Task 11: Frontend tests**
  - [x] `KitchenDisplayPage.test.tsx`: a `pending` row shows a "Pick up" button; clicking it calls
    the mutation and (via the subsequent live event or direct query invalidation, whichever Task 8
    implements) the row's badge updates to `in_preparation`, the button changes to "Mark ready".
    Clicking "Mark ready" on an `in_preparation` row updates it to `ready` with no button remaining.
    A failed pick-up call shows an inline error, does not silently do nothing. No button renders on
    a `ready` row.
  - [x] `TableOrderDetailPage.test.tsx`: a stubbed `order.item_status_changed` WebSocket message
    updates that page's own status badge without a page reload, no button appears anywhere on this
    page as a result.
- [x] **Task 12: Full regression pass**
  - [x] `uv run pytest -q` (backend) — zero regressions.
  - [x] `pnpm test` (frontend) — zero regressions.
  - [x] `npx tsc -b` — clean.

## Dev Notes

### Architecture compliance

- **AD-6** (guarded, atomic OrderItem status transitions): both `pick_up_item` and
  `mark_item_ready` are single guarded `UPDATE ... WHERE status = <expected>` statements, checked
  via `rowcount`, exactly like `edit_item`/`cancel_item` already do — this story's central mechanism
  for AC1/AC2/AC4/AC5. `pick_up_item` additionally wraps the `Ingredient` decrement(s) and
  `StockMovement` insert(s) in the **same** transaction as the guarded UPDATE (one `db.commit()` for
  all of it), which is the literal text of AD-6's own extended description quoted in the
  architecture spine: *"For the `in_preparation` transition specifically, the status update, the
  `Ingredient.current_stock` decrement, and the `StockMovement(consumption)` insert happen in one DB
  transaction."*
- **Trap 9** (lock the one row every caller contends on): `apply_consumption` reuses
  `InventoryService._lock_ingredient`'s existing `SELECT ... FOR UPDATE`, composed inside
  `pick_up_item`'s own transaction — a pick-up touching two Ingredients locks both, in whatever
  order the Recipe Ingredients query returns them (no explicit ordering guarantee beyond
  `RecipeIngredient.ingredient_id` ascending, matching `MenuService.list_recipe_ingredients`'s own
  `order_by`) — consistent lock ordering across all callers avoids a deadlock between two
  simultaneous multi-ingredient pick-ups that would otherwise lock the same two Ingredients in
  opposite orders.
- **Trap 18** ("only allow this while the row is in state X" must be one guarded UPDATE, never
  read-then-write): both new methods follow this exactly, matching `edit_item`. The "early return
  must not skip the guard" half of this trap doesn't arise here (neither method has an early-exit
  branch before the guarded UPDATE beyond the existing `_get_item` 404 check, which is a distinct
  concern — item exists at all — not a state check).
- **Trap 20** (log `actor.id` before `rollback()`, not after — `rollback()` expires every session
  object): both new methods' `WARNING`-level rejection logs must read `actor.id` **before** calling
  `await db.rollback()`, matching `edit_item`'s/`cancel_item`'s existing order exactly (log line
  first, `rollback()` second — do not reorder).
- **Trap 23** (container provider ordering): this story is the first time `order_service` itself
  gains a same-container dependency beyond `realtime_service` — `inventory_service` must be
  declared above `order_service` in `container.py` (Task 6). Get this wrong and the app fails at
  **import time** with a `NameError`, not at request time — this is the one place a mistake here is
  loud rather than silent.
- **AD-16** (stock never floor-capped at zero): `apply_consumption`'s decrement must not clamp,
  matching `record_movement`'s existing unclamped delta application — AC7 is explicitly testing
  this.
- **AD-2** (one WebSocket endpoint, Role-scoped, each event emitted exactly once by the service
  that owns the mutation): `order.item_status_changed` is emitted exactly once per transition, from
  `OrderService` (the service that owns the mutation), to `[UserRole.waiter, UserRole.cook]` —
  matches `order.item_added`'s own recipient list and reasoning.
- **Reused, not duplicated, from Story 4.2:** the `was_low`/`is_low` threshold-crossing check and
  the `inventory.alerts_changed` event/payload shape are identical to `record_movement`'s own — this
  story's AC7 wording ("reuses FR-14, no new alert logic built here") is a direct instruction, not
  just a description.

### Current state of the files this story touches (read before editing)

- **`backend/services/order_service.py`**: `OrderService.__init__` currently takes `(logger,
  realtime_service)` only. `_get_item` (used by `edit_item`/`cancel_item`) is directly reusable
  as-is for both new methods, no change needed to it. `edit_item`'s guarded-UPDATE-then-rollback
  shape (lines ~257–312) is the template to copy for both new methods' guard logic.
- **`backend/services/inventory_service.py`**: `InventoryService.__init__` currently takes `(logger,
  realtime_service)`. `_lock_ingredient` (lines ~279–303) and `record_movement`'s `was_low`/`is_low`
  computation (lines ~219, ~244) are what `apply_consumption` must mirror, minus the commit and
  minus the broadcast (both deferred to the caller).
- **`backend/container.py`**: `order_service` (line ~101) is currently declared **above**
  `inventory_service` (line ~115) — this ordering must flip (Task 6), the file's own existing
  comment already states the general rule this specific case now triggers.
- **`backend/api/orders.py`**: not read in full during story creation — the dev agent must read this
  file's existing `PATCH`/`DELETE` item routes (edit/cancel) before adding the two new `POST` routes,
  to match its existing dependency-injection and response-model conventions exactly, and to
  determine whether a Cook-permitted write dependency already exists in this file or must be added.
- **`backend/data_models/order.py`**: `OrderItem.cook_id` (line 142) already exists, nullable,
  currently always `NULL` in production data since nothing sets it yet — this story is what first
  writes to it. `OrderItemResponse` (line 191) already includes `cook_id` — no schema change needed
  for the broadcast payload.
- **`frontend/src/pages/cook/KitchenDisplayPage.tsx`**: read-only as of 5.1, no button/click-handler
  code exists anywhere in it yet — Task 9 is pure addition, not a rewrite of the existing
  loading/error/grouping logic (leave that as-is).
- **`frontend/src/pages/waiter/TableOrderDetailPage.tsx`**: not read in full during story creation —
  the dev agent must read this file's existing `order.item_added`-or-similar subscription (referenced
  by 5.1's own Dev Notes as the source of the "client-side resolution, never a raw id" and "combine
  loading/error across every dependent query" conventions) before adding the new
  `order.item_status_changed` subscription in Task 10.
- **`frontend/src/services/orderService.ts`**: not read in full during story creation — the dev
  agent must read `useEditOrderItem`/`useCancelOrderItem`'s exact hook signatures and
  invalidation behavior before adding the two new hooks in Task 8, to match the established
  convention rather than inventing a new one.

### Project Structure Notes

Files touched:
- `backend/exceptions/__init__.py` — **UPDATE**, `OrderItemNotInPreparationError` added.
- `backend/services/inventory_service.py` — **UPDATE**, `apply_consumption` added.
- `backend/services/order_service.py` — **UPDATE**, `inventory_service` dependency added,
  `pick_up_item`/`mark_item_ready` added.
- `backend/api/orders.py` — **UPDATE**, two new routes.
- `backend/container.py` — **UPDATE**, `order_service` moved below `inventory_service`,
  `inventory_service=inventory_service` added to its Factory call.
- `backend/tests/test_orders.py` — **UPDATE**, extensive new coverage (Task 7).
- `backend/tests/test_websocket.py` — **UPDATE** (or extended in `test_orders.py`, dev agent's
  call, matching whichever file `order.item_added`'s own broadcast test already lives in).
- `frontend/src/services/orderService.ts` — **UPDATE**, two new mutation hooks.
- `frontend/src/pages/cook/KitchenDisplayPage.tsx` — **UPDATE**, action buttons + new subscription.
- `frontend/src/pages/cook/KitchenDisplayPage.test.tsx` — **UPDATE**, new test coverage.
- `frontend/src/pages/waiter/TableOrderDetailPage.tsx` — **UPDATE**, new subscription only, no new
  buttons.
- `frontend/src/pages/waiter/TableOrderDetailPage.test.tsx` — **UPDATE**, new test coverage.

No new Alembic migration (no schema change — `OrderItem.cook_id` already exists). No new frontend
route. No change to `backend/api/kitchen.py`/`backend/services/kitchen_service.py` (5.1's read-only
route is untouched by this story).

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 5.2`] — this story's AC source, verbatim.
- [Source: `_bmad-output/planning-artifacts/prds/prd-.../prd.md#FR-10, FR-13, NFR-1, NFR-3, NFR-4`]
  — the transition rules, the atomicity requirement, and the traceability requirement this story's
  AC1/AC2 implement.
- [Source: `_bmad-output/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md`, AD-6, AD-2,
  AD-16] — the guarded-atomic-transition mechanism, the broadcast-ownership rule, and the
  never-floor-capped rule this story's core logic must satisfy.
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../EXPERIENCE.md`, "Kitchen Display card",
  Flow 2 (UJ-2)] — the one-click-per-transition interaction model, the exact "deduction happens at
  pick-up, not pass" sequencing, and the below-stock-still-succeeds edge case.
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../DESIGN.md`, "kitchen-display-card"] —
  the single-large-click-target button requirement (UX-DR19).
- [Source: `backend/services/order_service.py::edit_item`, `::cancel_item`] — the exact
  guarded-UPDATE-then-rollback shape both new methods copy.
- [Source: `backend/services/inventory_service.py::record_movement`, `::_lock_ingredient`] — the
  exact row-lock and threshold-crossing logic `apply_consumption` reuses, minus commit/broadcast.
- [Source: `backend/container.py`, existing ordering comment above `order_service`] — states the
  general rule this story's Task 6 is the first concrete case of applying to `order_service` itself.
- [Source: `_bmad-output/implementation-artifacts/5-1-view-incoming-orders-in-real-time-kitchen-
  display.md`, Scope note and Dev Agent Record] — confirms `KitchenService` is deliberately
  read-only/config-free, and that this story (5.2) is the one explicitly deferred to for
  pick-up/mark-ready.
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md`, story-3-4 review entry] — the
  standing instruction that whichever story adds live updates for order-item transitions (this one)
  should also add a negative test proving `edit_item`/`cancel_item` stay silent unless this story
  explicitly changes that (it does not — neither method is touched here).
- [Source: `_bmad-output/project-context.md`, trap 9, trap 18, trap 20, trap 23] — the row-lock
  ordering, guarded-UPDATE, log-before-rollback, and container-declaration-order rules this story's
  implementation must follow exactly, the last of which (trap 23) is directly triggered by this
  story for the first time on `order_service` itself.

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5

### Debug Log References

- `uv run pytest tests/test_orders.py -q` — 66 passed
- `uv run pytest tests/test_websocket.py -q -k "pick_up or picking or marking_an_item_ready"` — 3 passed
- `uv run pytest -q` (full backend suite) — 339 passed, no regressions (baseline 321 + 18 new)
- `npx vitest run src/pages/cook/KitchenDisplayPage.test.tsx` — 9 passed
- `npx vitest run src/pages/waiter/TableOrderDetailPage.test.tsx` — 22 passed
- `npx vitest run` (full frontend suite) — 178 passed, no regressions (baseline 173 + 5 new)
- `npx tsc -b` — clean

### Completion Notes List

- Implemented both transitions on `OrderService` (not `KitchenService`, per the story's own Scope
  note): `pick_up_item` (pending → in_preparation, guarded UPDATE + `cook_id` attribution, AD-6)
  and `mark_item_ready` (in_preparation → ready, pure status change, no `cook_id` reassignment —
  attribution is audit-only, not an access lock, AC6).
- Added `InventoryService.apply_consumption`, reusing `_lock_ingredient`'s row lock (trap 9) and
  `record_movement`'s `was_low`/`is_low` threshold-crossing shape, but deliberately not committing
  or broadcasting itself — `pick_up_item` composes it inside its own single transaction so the
  `OrderItem` status update, every `Ingredient` decrement, and every `StockMovement` insert commit
  together (AD-6, NFR-3), then broadcasts `inventory.alerts_changed` only after that commit
  succeeds, once per Ingredient that actually crossed threshold.
- `OrderService` gained a new `inventory_service: InventoryService` constructor dependency. This
  required moving `order_service`'s provider below `inventory_service`'s in `container.py` (trap
  23, applied to `order_service` itself for the first time) — done, with the file's own ordering
  comment updated to state the new rule explicitly.
- New exception `OrderItemNotInPreparationError` (409) added for the mark-ready guard, distinct
  from `OrderItemNotPendingError` (reused as-is for the pick-up guard, its existing wording already
  fit).
- Two new `POST` routes added to the existing `backend/api/orders.py` (not a new router file),
  gated by a new `OrderItemProgressDep` (cook + admin, mirroring `KitchenReadDep`'s shape).
- New `order.item_status_changed` event broadcast to `[UserRole.waiter, UserRole.cook]` from both
  transitions — same recipients and payload shape as `order.item_added`, verified via three new
  `test_websocket.py` end-to-end tests (pick-up delivers to Waiter+Cook, not warehouse_manager
  unless threshold crosses; a crossing pick-up also delivers `inventory.alerts_changed`; mark-ready
  delivers the status change with no alert).
- Frontend: `KitchenDisplayPage.tsx` gained "Pick up"/"Mark ready" buttons (single large MUI
  `Button`, UX-DR19), wired to two new hooks (`usePickUpItem`/`useMarkItemReady` in
  `orderService.ts`) that are deliberately *not* bound to one fixed `orderId` the way
  `useEditOrderItem`/`useCancelOrderItem` are — the Kitchen Display renders items from many
  different Orders on one screen, so `orderId` travels with each mutation call instead. Per-row
  inline error display (UX-DR17, no toast system exists in this codebase). New
  `order.item_status_changed` subscription added alongside the existing `order.item_added` one,
  invalidating `KITCHEN_ITEMS_QUERY_KEY`.
- `TableOrderDetailPage.tsx` also subscribes to `order.item_status_changed` now (a Waiter's screen
  must reflect a Cook's action live, AC8), but gets no new buttons — pick-up/mark-ready stay
  Cook-only, Kitchen-Display-only, per the story's "As a Cook" user statement.
- One pre-existing frontend test needed updating, not just new tests added: 5.1's
  `KitchenDisplayPage.test.tsx::"renders no action controls anywhere on the board"` asserted zero
  buttons ever render — genuinely true in 5.1 (read-only), genuinely false now that this story adds
  pick-up/mark-ready. Replaced with a test asserting exactly one "Pick up" and one "Mark ready"
  button render, scoped correctly to `pending`/`in_preparation` rows, none on a `ready` row.
- Caught and fixed a `MissingGreenlet` bug in the test suite itself (not application code) while
  writing Task 7's new backend tests: accessing an ORM object's attribute (e.g. `ingredient.id`)
  *after* calling `db_session.expire_all()` triggers a synchronous lazy-load that an `AsyncSession`
  cannot perform outside an explicit `await`. Every pre-existing test in this file avoids this by
  only ever holding plain ids (e.g. `item["id"]` from a JSON response) across an `expire_all()`
  call, never an ORM attribute access — the new `_create_available_dish_with_ingredient` helper was
  changed to return a plain `int` ingredient id rather than the ORM `Ingredient` instance, matching
  that existing convention, and every new test was audited for the same mistake.
- The concurrency test (`test_race_between_two_pick_ups_only_one_succeeds_and_deducts_once`)
  initially asserted the wrong post-race stock value — AD-6's guard runs *before* any deduction is
  attempted, so a losing request's guarded UPDATE hits 0 rowcount and rolls back before touching
  stock at all; the correct assertion is that stock is completely untouched (still at its starting
  value, zero StockMovement rows), not that exactly one deduction landed. Caught and fixed by
  running the test and reading its actual failure, not just reasoning about it in the abstract.

### File List

- `backend/exceptions/__init__.py`
- `backend/services/inventory_service.py`
- `backend/services/order_service.py`
- `backend/api/orders.py`
- `backend/container.py`
- `backend/tests/test_orders.py`
- `backend/tests/test_websocket.py`
- `frontend/src/services/orderService.ts`
- `frontend/src/pages/cook/KitchenDisplayPage.tsx`
- `frontend/src/pages/cook/KitchenDisplayPage.test.tsx`
- `frontend/src/pages/waiter/TableOrderDetailPage.tsx`
- `frontend/src/pages/waiter/TableOrderDetailPage.test.tsx`

## Change Log

| Date | Change |
|---|---|
| 2026-08-16 | Story 5.2 created via bmad-create-story: pick-up/mark-ready transitions, atomic stock deduction via a new `InventoryService.apply_consumption` reused from `OrderService`, `order.item_status_changed` broadcast, container reordering (trap 23) required for `order_service`'s new `inventory_service` dependency. |
| 2026-08-16 | Implemented Story 5.2: pick-up (pending → in_preparation, atomic stock deduction, cook attribution) and mark-ready (in_preparation → ready, pure status change) transitions, both on `OrderService`. New `InventoryService.apply_consumption` reused inside the same transaction, `order.item_status_changed` broadcast, container reordering for the new `order_service` → `inventory_service` dependency (trap 23). 18 new backend tests (339 total), 5 new frontend tests + 1 updated (178 total). |
