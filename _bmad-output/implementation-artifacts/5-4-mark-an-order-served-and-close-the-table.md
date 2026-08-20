---
baseline_commit: 51cf1309d1159af068978b99e66171c32ff7e3d9
epic: 5
story: 4
---

# Story 5.4: Mark an Order Served and Close the Table

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Waiter,
I want to mark a ready order as served and then close the table,
so that I can finish the table and free it up for the next guests.

## Scope note (read first)

**This story is the first to write `served` and `closed` onto `Order.status`.** Story 5.3 built
`_recompute_order_status` and explicitly guarded it to no-op on an Order already `served`/`closed`
— those two values have sat unreachable since Story 3.1 created the column. This story makes them
reachable, via two new, explicit, Waiter-triggered actions that are **not** derived recomputes:

- **Mark served** (`POST /api/orders/{order_id}/serve`, FR-11): a guarded transition,
  `Order.status` moves from `ready` **or** `pending` to `served`. The "or `pending`" half of the
  epic AC ("ready, or it has zero non-cancelled Order Items") is not a second condition to check
  separately — per FR-12/Story 5.3's own three-bucket rule, `Order.status` is `pending` **if and
  only if** the Order currently has zero non-cancelled Order Items (any non-cancelled item at all
  forces `in_preparation` or `ready`, never `pending`). So the guard is simply `status IN (ready,
  pending)`, one `UPDATE ... WHERE status IN (...)` — do not re-count items separately, the status
  column already encodes that fact.
- **Close** (`POST /api/orders/{order_id}/close`, FR-8): a guarded transition, `Order.status`
  moves from `served` to `closed`, `Order.total_amount` is computed and stored (sum of
  `price_at_add × quantity` over non-cancelled Order Items, AD-7), `Order.closed_at` is stamped,
  and the owning `RestaurantTable.status` moves back to `available` — three writes that must commit
  together in one transaction (the same "things that change together commit together" principle
  AD-6 already applies to pick-up's stock deduction): a `closed` Order whose Table never reopened,
  or a Table freed with an Order still `served`, is a state nothing later can recover from cleanly.

**Why both are guarded UPDATEs, unlike Story 5.3's `_recompute_order_status` (AD-6, not AD-5):**
these two are genuine state-machine transitions with a real expected prior status to check — the
exact opposite of Story 5.3's Scope note, which explained why *that* recompute was **not** a
guarded transition. Do not reuse or extend `_recompute_order_status` for either of these; they are
new, separate guarded UPDATEs (trap 18's idiom: `UPDATE ... WHERE id = ? AND status IN (...)`,
checked via rowcount), each getting its own new exception type in `backend/exceptions/`
(`OrderNotServableError` for mark-served, `OrderNotClosableError` for close) mirroring
`OrderItemNotPendingError`'s existing shape.

**No row lock needed for close's total computation.** Trap 27 (Story 5.3) established "aggregating
sibling rows onto a parent needs a lock on the parent" — but by the time an Order reaches `served`,
every one of its non-cancelled Order Items is already `ready` (mark-served's own guard, above,
only accepts `ready`/`pending`, and `ready` per FR-12 means *every* non-cancelled item is already
`ready`). No later action can change any Order Item's status once its Order is `served`:
`cancel_item` only accepts `pending`/`in_preparation` items (none exist once `served`), and
`pick_up_item`/`mark_item_ready` only accept `pending`/`in_preparation` items respectively (same).
So the Order Item set is frozen the instant `served` is reached — reading it inside close's own
transaction (after close's own guarded UPDATE succeeds) sees a value nothing else can be mutating
concurrently. This is a narrower situation than trap 27's, not a contradiction of it.

**No new `order.status_changed` broadcast shape.** Both mark-served and close call the **same**
`_broadcast_order_status_changed(db, order)` helper Story 5.3 already built (refresh, then
broadcast `OrderResponse` to `[UserRole.waiter]`) — these are just two more call sites for it,
alongside `add_item`/`cancel_item`/`pick_up_item`/`mark_item_ready`. Do not build a second
broadcast helper or a new event name; `order.status_changed` already means "this Order's status
field changed, for any reason," and both of these new actions are exactly that.

**Close also broadcasts `table.status_changed`**, reusing `open_table`'s existing broadcast shape
exactly (plain dict, `{table_id, status}`, to `[UserRole.waiter]`) — the Tables grid's tile needs
to flip back to `available` live, the same way it already flips to `occupied` live when a Table
opens.

**`GET /api/orders` (`list_open_orders`, Story 5.3) already excludes `closed` Orders** by its
existing `status != closed` filter — once close writes `closed`, that Order silently drops out of
the Tables grid's attention-lookup on its next refetch, no change needed there.

**A gap Story 5.3 explicitly deferred to this story, now genuinely in scope:**
`KitchenService.list_active_items` (`backend/services/kitchen_service.py`) filters only on
`OrderItem.status != cancelled`, with no filter on the *owning* Order's status — its own docstring
already says "once those \[5.3/5.4] ship, this query will need `Order.status not in (served,
closed)` added too, since a served Order's items keep their own `ready` status and would otherwise
leak onto this board forever." This story is what first makes a `served`/`closed` Order reachable,
so this is not optional polish, it is required for the Kitchen Display to keep working correctly
once this story ships (a story must leave the system working end-to-end, not just satisfy its own
literal ACs). Add the join-and-filter: `.join(Order, ...).where(OrderItem.status !=
OrderItemStatus.cancelled, Order.status.not_in([OrderStatus.served, OrderStatus.closed]))`.

**The "N tables need attention" nav counter (UX-DR4/EXPERIENCE.md) does not exist in the codebase
yet** — confirmed by inspection, only the Warehouse Manager's Alerts nav badge
(`AppShell.tsx:110`) exists today. This story adds it for the first time, for the Waiter role
only, reusing infrastructure Story 5.3 already built: `useOpenOrders()` (already fetched by
`TablesPage.tsx`, not yet by `AppShell.tsx`) filtered to `status === "ready"`, counted (not just
turned into a boolean Set the way `TablesPage.tsx`'s `readyTableIds` does — the badge needs the
*count*, `TablesPage.tsx`'s existing computation only needs Set membership, so this is a second,
parallel derivation in `AppShell.tsx`, not a shared extraction; the two components already fetch
`useOpenOrders()` independently via TanStack Query's own cache, so this is not a duplicate
network request). Same `Badge`/`badgeContent`/`invisible={count === 0}` shape
`AppShell.tsx:108-112` already established for the Alerts badge, but with the `ready`-green color
token (`DESIGN.md`'s `nav-badge-attention`), not the Alerts badge's red — a deliberate difference,
not an inconsistency to "fix." "Clears automatically" (FR-11, no dismiss action) falls out for
free: the moment mark-served's `order.status_changed` broadcast lands, `AppShell.tsx`'s own
`useOpenOrders()` invalidates and refetches, and that Order (now `served`, not `ready`) drops out
of the count on its own — no explicit "clear" code needed, matching the "counter reflects live
truth" pattern this whole feature area already uses. `AppShell.tsx` needs a new
`order.status_changed` subscription (Waiter-scoped, mirroring the existing
`inventory.alerts_changed` subscription's warehouse_manager-scoped shape at lines 91-98) to keep it
live.

## Acceptance Criteria

1. **Given** an Order's status is `ready` (or it has zero non-cancelled Order Items), **when** a
   Waiter marks it `served`, **then** the Order moves to `served` as a pure status change (FR-11).
2. **Given** any non-cancelled Order Item is not yet `ready`, **when** a Waiter attempts to mark
   the Order `served`, **then** the action is rejected (FR-11).
3. **Given** an Order is `served`, **when** a Waiter closes it, **then** the total is computed as
   the sum of each non-cancelled Order Item's stored `price_at_add x quantity` (AD-7), the Order
   moves to `closed`, and the Table returns to `available` (FR-8).
4. **Given** an Order has not yet reached `served`, **when** a Waiter attempts to close it, **then**
   the action is hard-blocked with no override, a stuck item must be cancelled first via Epic 3's
   FR-7 (FR-8).
5. **Given** an Order is closed, **when** its total_amount is checked afterward, **then** it is
   populated and immutable (FR-8).
6. **Given** an Order eligible to be closed, **when** the Waiter clicks Close, **then** it applies
   with no separate confirm step, unlike the cancel path which does confirm, since closing is not
   a data-loss risk (UX-DR12 contrast).
7. **Given** a table whose Order is marked `served`, **when** that happens, **then** the Waiter's
   "tables need attention" counter clears for that table automatically, with no dismiss action
   (UX-DR4).

## Tasks / Subtasks

- [x] **Task 1: Backend — new exception types** (AC2, AC4)
  - [x] `backend/exceptions/__init__.py`: add `OrderNotServableError(ConflictError)`, detail
    `"Rejected, order is not ready to be served"`, mirroring `OrderItemNotPendingError`'s
    docstring shape (covers both "wrong status" and "lost the race between read and write," same
    detail for both, the guarded UPDATE cannot distinguish them).
  - [x] Add `OrderNotClosableError(ConflictError)`, detail `"Rejected, order is not served yet"`,
    same shape.

- [x] **Task 2: Backend — `OrderService.mark_served`** (AC1, AC2)
  - [x] `backend/services/order_service.py`: new `async def mark_served(self, db: AsyncSession,
    actor: User, order_id: int) -> Order`.
    - `await self._get_order(db, actor, order_id)` first (404 if the Order does not exist, same
      pattern every other item/order-scoped method in this file already uses).
    - Guarded UPDATE: `update(Order).where(Order.id == order_id, Order.status.in_([OrderStatus.
      ready, OrderStatus.pending])).values(status=OrderStatus.served)`. `rowcount == 0` →
      `await db.rollback()`, raise `OrderNotServableError` (AC2), logged at `WARNING` with
      `order_id`.
    - On success: `await db.commit()`, `await db.refresh(order)`, log at `INFO` (`order_id`, old
      status if convenient, `served`), then call the existing
      `self._broadcast_order_status_changed(db, order)` (Story 5.3's helper, unchanged) — **do
      not** write a second broadcast helper.
    - Returns the now-`served` Order.

- [x] **Task 3: Backend — `OrderService.close_order`** (AC3, AC4, AC5)
  - [x] Same file, new `async def close_order(self, db: AsyncSession, actor: User, order_id: int)
    -> Order`.
    - `await self._get_order(db, actor, order_id)` first (404).
    - Guarded UPDATE #1: `update(Order).where(Order.id == order_id, Order.status ==
      OrderStatus.served).values(status=OrderStatus.closed, closed_at=func.now())`. `rowcount ==
      0` → `await db.rollback()`, raise `OrderNotClosableError` (AC4), logged at `WARNING`.
    - On success, still inside the same transaction (no commit yet): read every non-cancelled
      Order Item's `price_at_add` and `quantity` (`select(OrderItem.price_at_add,
      OrderItem.quantity).where(OrderItem.order_id == order_id, OrderItem.status !=
      OrderItemStatus.cancelled)`), sum `price_at_add * quantity` in Python (`Decimal`
      arithmetic, matching `price_at_add`'s existing `Numeric(8, 2)` type — do not round through
      `float`), and set `order.total_amount = computed_total` as a plain ORM attribute assignment
      (same "already-tracked-object, included in the pending commit" shape
      `_recompute_order_status` already established for `order.status`).
    - Guarded UPDATE #2, same transaction: `update(RestaurantTable).where(RestaurantTable.id ==
      order.table_id, RestaurantTable.status == TableStatus.occupied).values(status=TableStatus.
      available)`. This one should not realistically fail (a Table backing a `served` Order can
      only be `occupied`, opened by this same Order and never touched again in v1), but check
      `rowcount` anyway and log at `ERROR` (not silently ignore) if it is ever 0 — do not raise
      past this point, the Order-side writes already succeeded and must still commit; log loudly
      instead so a genuine data inconsistency is visible rather than silently swallowed.
    - `await db.commit()`, `await db.refresh(order)`, log at `INFO` (`order_id`, `total_amount`,
      `table_id`).
    - Broadcast `self._broadcast_order_status_changed(db, order)` (reused, AD-2/Story 5.3), then
      broadcast `table.status_changed` to `[UserRole.waiter]` with the same plain-dict payload
      shape `open_table` already uses: `{"table_id": order.table_id, "status": TableStatus.
      available.value}`.
    - Returns the now-`closed` Order.

- [x] **Task 4: Backend — `POST /api/orders/{order_id}/serve` and `/close` routes** (AC1-AC5)
  - [x] `backend/api/orders.py`: two new routes, both on the existing Waiter-only `OrdersDep`
    (mark-served/close are Waiter actions per FR-11/FR-8, no Cook/Admin fallback — matches every
    other Waiter-scoped route in this file, do not widen).
    - `@router.post("/{order_id}/serve", response_model=OrderResponse, responses=error_responses(
      _SERVE_ERROR_DESCRIPTIONS, 401, 403, 404, 409))`, calling `order_service.mark_served(db,
      actor, order_id)`. New `_SERVE_ERROR_DESCRIPTIONS` dict (401/403 shared from
      `_ERROR_DESCRIPTIONS`, 404 `"No matching Order was found"`, 409 `"The order is not ready to
      be served"`), following this file's existing per-route dict convention exactly.
    - `@router.post("/{order_id}/close", response_model=OrderResponse, responses=error_responses(
      _CLOSE_ERROR_DESCRIPTIONS, 401, 403, 404, 409))`, calling `order_service.close_order(db,
      actor, order_id)`. New `_CLOSE_ERROR_DESCRIPTIONS` dict, 409 `"The order is not served
      yet"`.
    - No route-ordering concern: neither new suffix (`/serve`, `/close`) collides with
      `/{order_id}/items` or `/{order_id}/items/{item_id}/...`, same reasoning Story 5.3's `GET
      /api/orders` route already documented for its own bare-prefix route.

- [x] **Task 5: Backend — fix the Kitchen Display's served/closed leak** (required for the system
  to keep working correctly, per Scope note; not covered by this story's own ACs but a direct
  consequence of them)
  - [x] `backend/services/kitchen_service.py`: `list_active_items`'s query gains `Order.status.
    not_in([OrderStatus.served, OrderStatus.closed])`, alongside the existing `OrderItem.status !=
    cancelled` filter, joined via the `Order` already joined in for `table_id`. Update the
    method's own docstring to remove the now-resolved "not a gap today" note.
  - [x] `backend/tests/test_kitchen.py`: extend with a case — an Order Item at `ready` whose Order
    has been marked `served` (via the full serve flow, not a direct DB write) no longer appears in
    `GET /api/kitchen/items`.

- [x] **Task 6: Backend tests** (`backend/tests/test_orders.py`, extend existing file — reuse the
  existing `_open_table`/`_add_item` helpers, follow this file's established `test_*` naming and
  role-coverage conventions)
  - [x] Mark-served from `ready` succeeds (AC1): an Order with one item, picked up and marked
    ready → `POST .../serve` returns 200, `status == "served"`.
  - [x] Mark-served from `pending`-with-zero-items succeeds (AC1, the "or zero items" branch): a
    freshly opened Order, no items added → `POST .../serve` returns 200, `status == "served"`.
  - [x] Mark-served rejected when a non-cancelled item is not `ready` (AC2): one item still
    `pending` (or `in_preparation`) → `POST .../serve` returns 409, Order status unchanged.
  - [x] Mark-served rejected on an already-`served` Order (idempotency/re-trigger case, mirrors
    this file's existing `test_ready_item_pick_up_and_mark_ready_are_both_rejected` pattern).
  - [x] Close succeeds from `served`, computes the total correctly (AC3): two items at different
    price_at_add/quantity, one of them cancelled before serving (assert the cancelled item is
    excluded from the sum — the epic's own literal wording), assert `total_amount` equals the
    exact expected `Decimal`, `status == "closed"`, `closed_at` is populated, and a `GET
    /api/tables` (or the Order's own table) shows `available` again.
  - [x] Close rejected when the Order is not yet `served` (AC4): a `ready` Order (not yet marked
    served) → `POST .../close` returns 409, no Table status change, `total_amount` still null.
  - [x] Close rejected on an already-`closed` Order (re-trigger case).
  - [x] `total_amount` is immutable after close (AC5): fetch the Order again after closing,
    confirm the same value persists (a second read, not a second write attempt — there is no
    endpoint that could mutate it, so this is a straightforward persistence check, not a
    rejection test).
  - [x] Role coverage for both new routes, matching every existing route's own coverage in this
    file: cook, admin, warehouse_manager all 403; unauthenticated 401.
  - [x] `order.status_changed` broadcast fires for both mark-served and close (extend
    `test_websocket.py` or wherever Story 5.3's own `order.status_changed` broadcast test lives),
    waiter-only recipients, matching Story 5.3's existing coverage shape.
  - [x] `table.status_changed` broadcast fires on close, with `status: "available"` (a second
    assertion alongside the above, or its own test — dev agent's call, matching whichever this
    file's existing `table.status_changed` coverage already does for `open_table`).
  - [x] Kitchen Display exclusion (Task 5's own test, listed here for completeness — same file or
    `test_kitchen.py`, whichever `list_active_items`'s existing tests already live in).

- [x] **Task 7: Frontend — `orderService.ts`** (AC1, AC3, AC6)
  - [x] New `useMarkOrderServed(orderId: number | undefined): UseMutationResult<Order, Error,
    void>`, `POST /api/orders/${orderId}/serve`, invalidating `orderForTableQueryKey(tableId)` on
    settle — mirrors `useCancelOrderItem`'s shape/invalidation reasoning, but this hook needs the
    Order's own query key (not the items key), since it is the Order object itself that changes.
    Note: this hook needs the `tableId`, not just `orderId`, to invalidate the correct key (the
    Table/Order detail page already has both in scope — pass whichever the calling page already
    holds, following `useOrderForTable`'s own `tableId`-keyed precedent rather than introducing a
    second `orderId`-keyed variant of the same cache).
  - [x] New `useCloseOrder(orderId: number | undefined, tableId: number | null):
    UseMutationResult<Order, Error, void>`, `POST /api/orders/${orderId}/close`, invalidating both
    `orderForTableQueryKey(tableId)` **and** `TABLES_QUERY_KEY` on settle (the Table's own status
    changed too, the same "invalidate every affected key" rule `useOpenTable` already follows for
    its own Table-list invalidation).

- [x] **Task 8: Frontend — `TableOrderDetailPage.tsx`, the Order total / Mark served / Close bar**
  (AC1, AC3, AC4, AC6, per `EXPERIENCE.md`'s "Order total / Close action" row: visible **at all
  times**, not just once closeable)
  - [x] A new bar/section below the Order Item table (matching the mockup's `.total-bar`
    placement, `mockups/key-table-order-detail.html`), always rendered once `order` is loaded
    (regardless of status), showing the Order total. Since the backend only computes/stores
    `total_amount` at close time (AC3/AC5 — it is null before then), the **pre-close** displayed
    total must be computed client-side from the already-fetched `items` list (sum of
    `price_at_add × quantity` over non-cancelled items, mirroring AD-7's rule exactly, computed in
    the frontend the same way `formatPrice` already exists for a single line) — once `order.status
    === "closed"`, prefer the server's own stored `order.total_amount` instead (the authoritative,
    immutable value per AC5), not a re-derived client sum.
  - [x] A "Mark served" button, enabled only when `order.status === "ready"` or (`order.status ===
    "pending"` and the item list is empty/all-cancelled) — mirroring the backend guard exactly,
    do not just check `"ready"` alone or the "zero items" branch silently never enables the
    button. No confirm step (this AC list does not ask for one, and the epic's own contrast is
    specifically about Close, not Mark served — but mark-served is also not a data-loss action,
    so treat it the same "no confirm" way, consistent with UX-DR12's stated rule that only
    data-loss actions get a confirm step).
  - [x] A "Close order" button, enabled only when `order.status === "served"` (AC4), disabled
    otherwise with no separate error state needed (a disabled control needs no explanation beyond
    its own disabled state here, unlike the add-item form's existing "state your own reason"
    pattern, since there is no ambiguity about why: the order simply isn't ready). **No confirm
    dialog** (AC6, UX-DR12 contrast — closing is not a data-loss risk, unlike the cancel path's
    existing confirm-behind-reveal).
  - [x] Both buttons follow this file's existing inline-error convention (`errorMessage`,
    `Alert severity="error"`) on mutation failure, matching `addItemMutation`'s existing error
    Alert shape.
  - [x] After a successful close, the page's own Order query key still resolves this exact Order
    (now `closed`) rather than 404ing — `useOrderForTable`'s `GET /api/orders/tables/{table_id}`
    filters on `status != closed` (`get_open_order_for_table`'s own existing behavior, unchanged
    by this story) — **a closed Order is no longer "the Table's open Order,"** so a refetch after
    close will 404 through `hasNoOpenOrder`'s already-existing branch (this page already renders
    "This table has no open order" for that case, Story 3.2's original UI) — do not build a new
    "closed" state banner, the existing 404-branch message already covers this outcome correctly
    once the Table's Order genuinely has nothing open on it anymore. Verify this by hand during
    manual testing (Task 10) rather than assuming.

- [x] **Task 9: Frontend — `AppShell.tsx`, the Waiter's "tables need attention" nav badge** (AC7)
  - [x] Fetch `useOpenOrders()` (Story 5.3's existing hook, `orderService.ts`), scoped to `user.
    role === "waiter"` only (mirroring the existing `isWarehouseManager`-scoped
    `useAlerts(isWarehouseManager)` call directly above it), and derive `readyOrderCount` (a plain
    count, not a Set — this badge shows a number, unlike `TablesPage.tsx`'s Set-for-membership
    use of the same data).
  - [x] Locate the Waiter's own "Tables" nav item the same way `ALERTS_NAV_PATH` locates the
    Alerts one (a new `const TABLES_NAV_PATH = "/waiter/tables"` constant, check
    `navigationConfig.ts` for the exact path string rather than guessing it), and wrap it in the
    same `Badge` pattern (`badgeContent={readyOrderCount}`, `invisible={readyOrderCount === 0}`),
    but `color` must use the `ready`-green token (check `theme`/`OrderItemStatusBadge.tsx`'s
    existing `success` color mapping for the exact token to reuse — **not** `color="error"`,
    which is the Alerts badge's own distinct token per `DESIGN.md`'s explicit "reuse the
    `ready`-green and cancelled/shortage-red tokens for the two attention-cue badges" rule).
  - [x] New `useEffect` subscribing to `order.status_changed`, invalidating
    `OPEN_ORDERS_QUERY_KEY` (Story 5.3's exported key), scoped to `user.role === "waiter"` the
    same way the existing `inventory.alerts_changed` subscription is scoped to
    `isWarehouseManager` (lines 91-98) — mirror that `useEffect`'s exact shape, do not merge the
    two into one generic subscription, they are conditioned on different Roles.

- [x] **Task 10: Frontend tests**
  - [x] `TableOrderDetailPage.test.tsx`: Mark served button renders/enables only when eligible
    (both the `ready` case and the zero-non-cancelled-items case); clicking it calls the new
    mutation and the page reflects the resulting `served` status once refetched. Close button
    renders/enables only when `served`; clicking it calls the new mutation with no confirm
    dialog appearing first (assert the request fires immediately on click, unlike the existing
    in-row cancel-confirm test's two-click assertion). The client-computed pre-close total matches
    a hand-checked sum over a stubbed item list, excluding a stubbed cancelled item from that sum.
    Post-close, the page falls back to the existing "no open order" branch once the Order query
    refetches and 404s.
  - [x] `AppShell.test.tsx`: a waiter user with one `ready` Order in a stubbed `useOpenOrders()`
    response renders the Tables nav badge with count 1, in the green token, not the Alerts badge's
    red; zero `ready` Orders renders no visible badge (`invisible`); a non-waiter role never
    fetches `useOpenOrders()` or renders this badge at all (mirroring this file's existing
    warehouse_manager-only Alerts-badge test shape). A stubbed `order.status_changed` message
    triggers a refetch of the open-orders list, mirroring this file's existing
    `inventory.alerts_changed` refetch test.

- [x] **Task 11: Full regression pass**
  - [x] `uv run pytest -q` (backend) — zero regressions.
  - [x] `pnpm test` (frontend) — zero regressions.
  - [x] `npx tsc -b` — clean.

## Dev Notes

### Architecture compliance

- **AD-6** (guarded, atomic transitions) governs both new actions here, unlike Story 5.3's
  `_recompute_order_status` (which is explicitly AD-5/pure-recompute territory, not AD-6) — see
  the Scope note's explicit contrast. Both `mark_served` and `close_order` are conditional
  `UPDATE ... WHERE status IN/== <expected>` checked via rowcount (trap 18's idiom), never a
  read-then-write.
- **AD-7** (price lock at add-time): close's total is always `sum(price_at_add × quantity)` over
  non-cancelled Order Items, never a live `Dish.price` join — the exact rule Story 3.x already
  established for `price_at_add` itself, this story is the first to actually sum it into a total.
- **AD-2** (one event per actual mutation, Role-scoped, emitted once by the owning service): both
  new actions reuse Story 5.3's existing `_broadcast_order_status_changed` helper for
  `order.status_changed` — do not add a new event name for "served" or "closed" specifically,
  `order.status_changed` already means exactly this. Close additionally reuses `open_table`'s
  existing `table.status_changed` broadcast shape (plain dict), the same event that already fires
  when a Table opens, now also firing when one frees up.
- **Trap 9 / trap 27's row-lock lesson does not apply to close's total computation** — see the
  Scope note's explicit reasoning for why the Order Item set is already frozen by the time
  `served` is reached, unlike Story 5.3's own aggregate-read case.
- **Trap 26's lesson (re-read after a guarded UPDATE, never reuse a pre-UPDATE value) applies to
  close's Order Items too**, in spirit: read the Order Items for the total sum only *after*
  close's own guarded UPDATE has succeeded (inside the same transaction), not before — though in
  this specific case no other concurrent write can touch those rows post-`served` (see above), so
  this is about not reading them prematurely/out of order within the method, not a live
  concurrency hazard the way trap 26's original case was.

### Current state of the files this story touches (read before editing)

- **`backend/services/order_service.py`**: `_recompute_order_status`
  (~587-653) already no-ops on `served`/`closed` — this story is what finally exercises that
  branch for the first time. `_broadcast_order_status_changed` (~655-676) takes an already-loaded
  `Order` and is reused as-is by both new methods, no signature change needed.
  `open_table` (~70-135) is the exact precedent for close's `table.status_changed` broadcast
  payload shape (plain dict, not a `TableResponse`).
- **`backend/api/orders.py`**: `OrdersDep` (~29) is what both new routes reuse, unchanged.
  `_ERROR_DESCRIPTIONS`/`_GET_ORDER_ERROR_DESCRIPTIONS`/etc. (~50-103) are the existing
  per-route dict convention; two more dicts follow the same shape.
- **`backend/services/kitchen_service.py`**: `list_active_items` (~28-57), its own docstring
  (~37-42) already documents the exact gap this story closes — read it before editing, the fix is
  described there almost verbatim.
- **`backend/data_models/order.py`**: `Order` (~121-130) already has `total_amount` (nullable
  `Numeric(10, 2)`) and `closed_at` (nullable `DateTime`) columns — both already exist from
  whatever migration originally created the table, no new Alembic revision needed for either.
  `OrderResponse` (~146-157) already serializes both fields.
- **`frontend/src/pages/waiter/TableOrderDetailPage.tsx`**: `OrderItemRow` (~123-298) is untouched
  by this story (item-level actions, not Order-level). The page component itself (~319-587) gains
  the new total/serve/close bar below the existing `<Table>` (~564-582), following the same
  inline-`Alert`-on-mutation-error convention `addItemMutation.isError` already uses (~556-560).
  `formatPrice` (~99-101) is the existing per-line formatting precedent to match for the new total
  display.
- **`frontend/src/components/shell/AppShell.tsx`**: the Alerts badge (~84-98, ~108-112) is the
  exact structural precedent for the new Waiter badge — a second, independently-scoped
  query+subscription pair, and a second `item.path === <NAV_PATH>` branch in the same `navItems.
  map(...)`, not a generalized "any nav item can have a badge" abstraction (this codebase's own
  comment at line ~25 explicitly says a per-path badge-lookup map would be premature until a
  second badge exists — this story is what makes that true, but the two badges still don't need
  to be unified into one map by this story alone; a plain second conditional branch, matching the
  first one's own shape, is consistent with "no premature abstraction").
- **`frontend/src/services/orderService.ts`**: `orderForTableQueryKey` (~70-72),
  `OPEN_ORDERS_QUERY_KEY`/`useOpenOrders` (~103-120) are Story 5.3's existing exports this story's
  two new hooks reuse for invalidation, not rebuilt.

### Project Structure Notes

Files touched:
- `backend/exceptions/__init__.py` — **UPDATE**, two new exception types.
- `backend/services/order_service.py` — **UPDATE**, `mark_served`/`close_order` added.
- `backend/api/orders.py` — **UPDATE**, two new routes.
- `backend/services/kitchen_service.py` — **UPDATE**, `list_active_items`'s filter gains the
  Order-status exclusion.
- `backend/tests/test_orders.py` — **UPDATE**, new coverage (Task 6).
- `backend/tests/test_kitchen.py` — **UPDATE**, new coverage (Task 5).
- `backend/tests/test_websocket.py` — **UPDATE** (or wherever Story 5.3's own
  `order.status_changed`/`table.status_changed` broadcast tests already live).
- `frontend/src/services/orderService.ts` — **UPDATE**, `useMarkOrderServed`/`useCloseOrder`
  added.
- `frontend/src/pages/waiter/TableOrderDetailPage.tsx` — **UPDATE**, total bar + Mark
  served/Close buttons.
- `frontend/src/pages/waiter/TableOrderDetailPage.test.tsx` — **UPDATE**, new coverage.
- `frontend/src/components/shell/AppShell.tsx` — **UPDATE**, Waiter attention-count nav badge.
- `frontend/src/components/shell/AppShell.test.tsx` — **UPDATE**, new coverage.

No new Alembic migration — `total_amount`/`closed_at` already exist as columns (see above). No
new frontend route (both buttons live on the existing `/waiter/tables/:tableId` page).

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 5.4`] — this story's AC source,
  verbatim.
- [Source: `_bmad-output/planning-artifacts/epics.md`, FR-8, FR-11] — the literal close/serve
  rules this story implements.
- [Source: `_bmad-output/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md`, AD-2, AD-6,
  AD-7] — broadcast ownership, the guarded-transition mechanism both new actions use (contrast
  with Story 5.3's own AD-5 recompute), and the price-lock/total rule.
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../EXPERIENCE.md`, "Order total / Close
  action" row, "Nav badge / counter, tables needing attention" row] — the total-always-visible
  rule, the close-enablement rule, and the attention-counter's live-clearing behavior (UX-DR4).
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../DESIGN.md`, `nav-badge-attention`,
  `table-tile.attention-state`] — the green-token reuse rule for the new nav badge, distinct from
  the Alerts badge's red.
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../mockups/key-table-order-detail.html`]
  — the total-bar's visual placement/labels (`Order total`, `Close order`).
- [Source: `backend/services/order_service.py::_recompute_order_status`,
  `::_broadcast_order_status_changed`, `::open_table`] — the served/closed no-op guard this story
  finally exercises, the broadcast helper this story reuses twice, and the
  `table.status_changed` payload shape close's second broadcast mirrors.
- [Source: `backend/services/kitchen_service.py::list_active_items`, its own docstring] — the
  exact gap this story is required to close (Task 5), documented in the code itself since Story
  5.1.
- [Source: `_bmad-output/implementation-artifacts/5-3-order-status-derives-from-its-items.md`,
  Scope note, "One more thing the helper must get right, forward-looking to Story 5.4"] — the
  served/closed no-op guard's own stated forward dependency on this story.
- [Source: `_bmad-output/project-context.md`, trap 9, trap 18, trap 26, trap 27] — the row-lock
  and guarded-UPDATE idioms this story's two new transitions apply, and the specific reasoning for
  why trap 27's lock is not needed for close's total computation.

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5

### Debug Log References

- `uv run pytest tests/test_orders.py -q` — 94 passed (85 baseline + 9 new: mark-served from
  ready, mark-served from zero-item pending, mark-served rejected on a not-yet-ready item,
  mark-served rejected on an already-served Order, close computes the total correctly excluding
  a cancelled item and frees the Table, close rejected before served, close rejected on an
  already-closed Order, total_amount persistence, and role coverage for both new routes)
- `uv run pytest tests/test_kitchen.py -q` — 10 passed (9 baseline + 1 new: a served Order's
  ready item no longer appears on the Kitchen Display, via the real serve flow)
- `uv run pytest tests/test_websocket.py -q` (implicit in the full run) — 2 new tests: mark-served
  broadcasts `order.status_changed` to Waiter only (Cook receives nothing), close broadcasts both
  `order.status_changed` and `table.status_changed` in that order
- `uv run pytest -q` (full backend suite) — 364 passed, no regressions (baseline 352 + 12 new)
- `npx vitest run src/pages/waiter/TableOrderDetailPage.test.tsx` — new coverage: pre-close total
  computed client-side excluding a cancelled item, Mark served enabled only when `ready` or
  `pending` with zero non-cancelled items (checked against the actual item list, not
  `order.status` alone), Close enabled only once `served`, both apply with no confirm dialog, and
  a post-close refetch falls back to the existing "no open order" state via the Order query's own
  404 once `get_open_order_for_table`'s `status != closed` filter excludes it
- `npx vitest run src/components/shell/AppShell.test.tsx` — new coverage: the Waiter's Tables nav
  badge shows the ready-Order count (green, distinct from the Alerts badge's red), hides when
  zero, refetches live on `order.status_changed`, and a non-Waiter Role never queries
  `useOpenOrders()` or renders it at all
- `npx vitest run` (full frontend suite) — 195 total, 1 failure (`router.test.tsx`, a 5s test
  timeout on an admin-navigation test untouched by this story) that passed cleanly in isolation
  (16/16) — confirmed test-runner resource contention under load, not a regression, the same
  flakiness pattern Story 5.3's own Dev Agent Record already documented
- `npx tsc -b` — clean

### Completion Notes List

- Implemented `OrderService.mark_served` and `OrderService.close_order` as two new guarded
  transitions (AD-6, trap 18), contrasting explicitly with Story 5.3's `_recompute_order_status`
  (a pure AD-5 recompute, not a guarded transition). `mark_served` guards on `status IN (ready,
  pending)` — a single condition, since FR-12 already guarantees `pending` means zero
  non-cancelled items, no separate item count needed server-side. `close_order` guards on `status
  == served`, computes `total_amount` as the exact `Decimal` sum of `price_at_add * quantity`
  over non-cancelled items (AD-7), stamps `closed_at`, and frees the Table — all three writes in
  one transaction. No row lock was added for the total's aggregate read (contrast trap 27): the
  Scope note's reasoning holds — every non-cancelled item is already `ready` by the time an Order
  reaches `served`, and no later action can change any item's status once `served`, so the set is
  frozen by construction, not by an explicit lock.
- Both new exception types (`OrderNotServableError`, `OrderNotClosableError`) mirror
  `OrderItemNotPendingError`'s existing shape and are handled by the same generic `ConflictError`
  → 409 handler already registered in `main.py`, no new handler needed.
- Reused Story 5.3's `_broadcast_order_status_changed` helper unchanged for both new actions —
  no new event name or broadcast helper was introduced. `close_order` additionally broadcasts
  `table.status_changed` with the same plain-dict payload shape `open_table` already established.
- Fixed the Kitchen Display's served/closed leak (`KitchenService.list_active_items`), a gap
  Story 5.3's own docstring had explicitly deferred to this story: added `Order.status.not_in([
  served, closed])` alongside the existing `!= cancelled` item filter.
- Frontend: `useMarkOrderServed`/`useCloseOrder` added to `orderService.ts`, matching
  `useOrderForTable`'s `tableId`-keyed invalidation precedent. `TableOrderDetailPage.tsx` gained
  an always-visible total bar (client-computed pre-close, the server's stored `total_amount`
  once `closed`) plus Mark served/Close buttons, both applying with no confirm step (AC6). Mark
  served's enablement check was written against the actual fetched `items` list, not
  `order.status === "pending"` alone, deliberately more defensive than the backend's own single-
  condition guard: the Order and item-list queries are independent TanStack Query caches that can
  momentarily disagree (refreshed by different live events), so relying on `order.status` alone
  client-side could transiently show the button enabled for an Order that still has a pending
  item in the currently-rendered list. Caught by a test written against exactly that scenario
  (`items` stubbed non-empty while `order.status` was stubbed `"pending"`), not by inspection —
  the first draft used `order.status` alone and the test correctly failed against it.
- `AppShell.tsx` gained the Waiter's first-ever "tables need attention" nav badge, reusing Story
  5.3's `useOpenOrders()` (now gated by a new `enabled` parameter, defaulting to `true` so
  `TablesPage.tsx`'s own existing unconditional call site is unchanged) filtered to a live ready-
  Order count, mirroring the Alerts badge's structure exactly but with the green `success` token
  per `DESIGN.md`'s explicit red/green distinction between the two attention-cue badges.
- Two pre-existing tests needed updates as a direct, expected consequence of the new UI, not
  scope creep: `TableOrderDetailPage.test.tsx`'s single-item render test now finds the same price
  text twice (the item row and the new total bar, which happen to match for a single qty-1 item)
  and `AppShell.test.tsx`'s "no Alerts nav item" test needed its fetch mock extended to answer
  `/api/orders` too, since a Waiter now legitimately queries it.

### File List

- `backend/exceptions/__init__.py`
- `backend/services/order_service.py`
- `backend/api/orders.py`
- `backend/services/kitchen_service.py`
- `backend/tests/test_orders.py`
- `backend/tests/test_kitchen.py`
- `backend/tests/test_websocket.py`
- `frontend/src/services/orderService.ts`
- `frontend/src/pages/waiter/TableOrderDetailPage.tsx`
- `frontend/src/pages/waiter/TableOrderDetailPage.test.tsx`
- `frontend/src/components/shell/AppShell.tsx`
- `frontend/src/components/shell/AppShell.test.tsx`

## Review Findings

Reviewed by three parallel agents (Blind Hunter, Edge Case Hunter, Acceptance Auditor) against
this story's 7 ACs and `_bmad-output/project-context.md`.

- [x] [Review][Patch] `close_order` broadcasts `table.status_changed` with `status: "available"`
  unconditionally, even on the branch where the Table's own guarded UPDATE returned `rowcount ==
  0` (logged at `ERROR`, table left unchanged) — waiter clients would be told the table freed up
  when it did not. Currently unreachable in production (a Table backing a `served` Order can only
  be `occupied`, and no other code path can change a Table's status while its Order is open), but
  cheap and unambiguous to fix: only broadcast when the write actually succeeded —
  `backend/services/order_service.py:close_order`
- [x] [Review][Patch] No concurrency test exists for two simultaneous `/close` calls on the same
  Order, unlike Story 5.3's own precedent of empirically verifying a similar "no lock needed"
  argument with a genuine two-client concurrent test rather than reasoning alone. Add one —
  `backend/tests/test_orders.py`
- [x] [Review][Defer] `computeClientSideTotal` (`TableOrderDetailPage.tsx`) sums currency with
  native JS `Number` arithmetic while the backend uses `Decimal` (AD-7) for the same computation
  — theoretical floating-point drift for the pre-close preview total. Deferred: this is the
  story's own explicit design choice (Dev Notes: "computed... the same way `formatPrice` already
  exists for a single line"), the backend's stored `total_amount` remains authoritative post-close
  (AC5), and `price_at_add` is always exactly 2 decimal places (`Numeric(8,2)`), bounding realistic
  drift to well below display precision.
- [x] [Review][Defer] `useMarkOrderServed`/`useCloseOrder` invalidate only the mutating page's own
  query key, relying on the WebSocket broadcast round-trip to refresh the Tables grid/nav badge on
  other pages — a brief self-observed staleness window if the actor's own socket is mid-reconnect
  at the moment of their own action. Deferred: matches this codebase's own established, documented
  precedent ("the live event is what refreshes other pages, not the mutating page's own success
  handler," `usePickUpItem`'s docstring), not a gap introduced by this story; the existing
  `ReconnectingBanner` already surfaces degraded connectivity to the user.
- [x] [Review][Defer] Mark served's eligibility check is implemented independently on both sides —
  backend trusts `Order.status` alone (FR-12's invariant), frontend re-derives from the raw item
  list (deliberately, to guard against the two independent TanStack Query caches momentarily
  disagreeing) — with no shared/contract test asserting the two conditions never diverge. Deferred:
  both directions fail safe (worst case is a disabled button requiring a manual refresh, never an
  incorrectly-enabled one that reaches a 409), and this codebase has no existing precedent for
  cross-stack contract tests to extend.

**Verified as non-issues:**

- **`close_order` mixes a raw Core `update()` (for `status`/`closed_at`) with a plain ORM
  attribute assignment (`order.total_amount = total`) on the same identity-mapped object in one
  transaction** — flagged as a "known SQLAlchemy footgun," but `synchronize_session="auto"`'s
  evaluator strategy only refreshes the in-memory attribute values from the bulk statement, it
  does not mark them dirty for re-flush; only the explicitly-assigned `total_amount` enters the
  pending flush. Verified correct by every passing test that asserts `total_amount`/`closed_at`
  post-close, not just by reasoning.
- **`mark_served`'s guard has no independent item-count check, trusting `Order.status` alone** —
  by design (Scope note): FR-12/`_recompute_order_status` already guarantees `pending` means zero
  non-cancelled items; a second count would duplicate an invariant this codebase already enforces
  centrally, not add real safety.
- **`OrderNotServableError` reuses one `detail` string for three distinct rejection causes** (item
  not ready, already served, already closed) — matches this exact file's own established
  precedent (`OrderItemNotPendingError`, `TableNotAvailableError`, `OrderItemNotCancellableError`
  all document the identical "guard cannot distinguish these cases, same detail" reasoning), not
  an oversight specific to this story.
- **No ownership check ties the acting Waiter to the Order's `waiter_id`** — matches AD-9
  (Role-level-only permissions) exactly, an explicit, already-documented architecture decision
  applied consistently across every method in this file, not a gap.
- **The in-memory computed `Decimal` total might not match the value later reloaded from the
  `Numeric(10,2)` column** — factually inapplicable: `price_at_add` is always exactly 2 decimal
  places, and multiplying a 2-decimal `Decimal` by an integer quantity can never produce more than
  2 decimal places, so no column-level rounding can ever apply.
- **Test-style nitpick (blank-line spacing, login-helper choice) in the new `test_kitchen.py`
  case** — both parts are false positives: the spacing matches this file's standard two-blank-line
  convention, and `_login_as(...)` is this exact file's own established helper (used by every
  sibling test), not an inconsistency with a different file's `_login_as_cook`.

## Change Log

| Date | Change |
|---|---|
| 2026-08-20 | Story 5.4 created via bmad-create-story: two new guarded transitions on Order.status (mark_served, close_order), the required Kitchen Display served/closed filter fix Story 5.3 deferred here, and the first-time Waiter "tables need attention" nav badge. |
| 2026-08-20 | Implemented Story 5.4: `OrderService.mark_served`/`close_order` (guarded transitions, AD-6, contrasting with Story 5.3's pure-recompute `_recompute_order_status`), two new exception types, two new `POST /api/orders/{order_id}/serve`\|`/close` routes, the Kitchen Display served/closed exclusion fix, and frontend: `useMarkOrderServed`/`useCloseOrder`, `TableOrderDetailPage.tsx`'s always-visible total bar with Mark served/Close actions (no confirm step), and `AppShell.tsx`'s new Waiter attention-count nav badge. 12 new backend tests (364 total), 2 pre-existing frontend tests updated for the new UI. Full backend suite: 364/364 passed. Full frontend suite: 195/195 passed (1 unrelated, isolation-confirmed flaky timeout in `router.test.tsx`). `npx tsc -b` clean. |
| 2026-08-21 | Code review patch pass (three parallel agents): fixed `close_order` broadcasting `table.status_changed` as "available" even when the Table's own guarded UPDATE failed to free it (now conditional on the write actually succeeding). Added a genuine concurrent double-close test (two independent `AsyncClient`s, `asyncio.gather`), confirming the guarded Order-status UPDATE alone — not a row lock — correctly serializes two simultaneous `/close` calls. Deferred: client-side JS-float total computation vs. the backend's `Decimal` (bounded, display-only, matches the story's own stated approach); cross-page query invalidation relying on the WebSocket round-trip (matches an existing, documented codebase precedent); no contract test between the backend's and frontend's independently-derived mark-served eligibility checks (both fail safe). 1 new backend test (365 total). |
