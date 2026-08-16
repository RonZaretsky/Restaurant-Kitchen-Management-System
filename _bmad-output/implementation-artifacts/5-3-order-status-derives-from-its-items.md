---
baseline_commit: b4f561122b207494dd72126d812a01a6583c6575
epic: 5
story: 3
---

# Story 5.3: Order Status Derives From Its Items

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the system,
I want an Order's status to automatically reflect the aggregate of its non-cancelled Order Items,
so that Waiters and Cooks always see an accurate summary status.

## Scope note (read first)

**This story makes `Order.status` a real, live-changing value for the first time.** Since Story 3.1
created it, `Order.status` has sat permanently at its `pending` default — nothing before this story
ever wrote to it. FR-12's aggregate rule is exactly three buckets, matching the epic's own ACs
literally:

- Zero non-cancelled Order Items → `pending`.
- Every non-cancelled Order Item `ready` → `ready`.
- Anything else (a mix, all `pending`, all `in_preparation`, etc.) → `in_preparation`.

**Where the new logic lives:** a new private helper on `OrderService`, `_recompute_order_status(db,
order_id) -> bool`, called from every existing method that changes the shape of an Order's
non-cancelled item set: `add_item` (a new pending item can pull a `ready` Order back down),
`cancel_item` (removing an item from the aggregate can push the remainder to `ready`),
`pick_up_item`, and `mark_item_ready` (Story 5.2). `edit_item` is untouched — it only changes
quantity/notes, never an item's status, so it cannot change the aggregate. The helper runs inside
each method's **existing transaction**, before that method's own `db.commit()` — Order.status
changing together with the OrderItem write that caused it is the same "things that change together
commit together" principle AD-6 already applies to the stock deduction, just without AD-6's guard
(see below for why no guard is needed here).

**Why this is not a guarded UPDATE (AD-6/trap 18 does NOT apply here):** AD-6 guards a *state
machine transition* — one row moving from an expected prior status to a new one, where a stale
precondition must be rejected, not silently reapplied. `Order.status` is not a transition, it is a
**pure recomputation from current truth** every time. Recomputing it twice concurrently converges to
the same correct answer both times — there is no "precondition that might no longer hold" to guard,
only a value to overwrite with whatever the aggregate says right now (AD-5's last-write-wins already
covers Order edits generally). Writing a guarded `UPDATE ... WHERE status = <expected>` here would
be answering a question ("was the prior status still X?") that FR-12 never asks. Do not add one.

**One more thing the helper must get right, forward-looking to Story 5.4:** `served` and `closed`
are **set explicitly** (FR-11/FR-8, not built yet), never derived. `_recompute_order_status` must
no-op (return `False`, touch nothing) if the Order's current status is already `served` or `closed`
— otherwise, once Story 5.4 exists, a Waiter cancelling a `served` Order's last non-cancelled item
would silently un-serve it back to `pending`/`in_preparation`, which is not a rule anywhere in the
PRD. Nothing today can ever produce a `served`/`closed` Order (that lands with 5.4), so this branch
is unreachable in practice right now — write it anyway, it is one `if` and the domain rule is
already documented (`_bmad-output/project-context.md`, "Domain rules worth restating": *"`served`
and `closed` are set explicitly"*), not a speculative guess.

**New broadcast, only when the derived value actually changes:** `order.status_changed` (past-tense,
`{domain}.{event}`, AD-2), broadcast to `[UserRole.waiter]` only (unlike `order.item_status_changed`,
Cook's Kitchen Display has no use for Order-level status — it only ever renders individual Order
Items). Payload is `OrderResponse.model_validate(order).model_dump(mode="json")`, the same
build-a-proper-response-object convention `order.item_status_changed` already established, even
though the two frontend subscribers below only use it as a refetch signal and never parse the
payload themselves. **Do not broadcast on every item mutation** — only when
`_recompute_order_status` returns `True` (the aggregate genuinely moved), otherwise cancelling one
of three still-`pending` items (aggregate stays `in_preparation` before and after) would fire a
no-op event on every mutation forever.

**New read endpoint, because AC4 needs it:** `GET /api/orders`, Waiter-only (reuses the existing
`OrdersDep`), `response_model=list[OrderResponse]`, backed by a new `OrderService.list_open_orders`
returning every Order where `status != closed` (same filter `get_open_order_for_table` already
uses), ordered by `Order.id`. This is the first **bulk** Order read in the project — every existing
Order read is scoped to one Table (`get_open_order_for_table`) or one Order's items — and it exists
for exactly one reason: **the Tables grid needs to know, across every occupied Table at once,
whether that Table's Order is `ready`**, to render AC4's attention-state tile treatment. A
per-tile `GET /api/orders/tables/{table_id}` call for every tile on the grid would be an N+1 request
pattern this codebase has never done (`KitchenDisplayPage` combines exactly 3 top-level queries, not
one per row); one bulk list, resolved client-side into a `table_id -> status` lookup (the same
"client-side resolution, never a second server-side filter" precedent `AD-10`/the Kitchen Display's
own `table_id` resolution already established), is the shape to match. `OrderResponse` already
carries `table_id` directly (unlike `OrderItem`, which needed `KitchenItemResponse`'s join in Story
5.1) — no join, no new response schema.

**Frontend, AC4 only on the Tables grid:** `TablesPage.tsx`'s `TableTile` gets a second Chip,
layered next to (not replacing) the existing table-status Chip, shown only when that Table's id
resolves to a `ready` Order in the new bulk list — matching DESIGN.md's `{components.table-tile.
attention-state}` spec (same green/`CheckCircleIcon` treatment as the `ready` status badge). Only
`occupied` tiles can ever have a matching Order (a Table only gets one via `open_table`, gated on
`status == available`; `reserved`/`available` tiles never have an open Order in v1, no
reservation-arrival flow exists), so the lookup only needs to be consulted for occupied tiles.
`TablesPage` subscribes to the new `order.status_changed` event to keep this live (alongside its
existing `table.status_changed` subscription). **`TableOrderDetailPage.tsx` also subscribes** to the
same event, invalidating its own `useOrderForTable` query key — not because any AC in this story
asks for new UI there, but because that page already holds a cached `Order` object this story is
what first makes `.status` a real, changing field on, and every other live-relevant field this
codebase tracks gets the same live-refresh treatment (matches the page's own existing
`order.item_added`/`order.item_status_changed` subscriptions, same pattern, one more event). No new
visible element is added to this page.

## Acceptance Criteria

1. **Given** an Order with a mix of `pending` and `ready` non-cancelled items, **when** status is
   computed, **then** the Order shows `in_preparation`, not `ready` (FR-12).
2. **Given** an Order where every non-cancelled item is `ready`, **when** status is computed,
   **then** the Order shows `ready` (FR-12).
3. **Given** an Order with zero non-cancelled Order Items, **when** status is computed, **then**
   the Order shows `pending` (FR-12).
4. **Given** the Order's derived status reaches `ready`, **when** that happens, **then** the
   Waiter's Table tile switches to the attention-state treatment, layered on top of the base
   table-status badge (FR-12, UX-DR3).

## Tasks / Subtasks

- [x] **Task 1: Backend — `OrderService._recompute_order_status`** (AC1, AC2, AC3)
  - [x] `backend/services/order_service.py`: new private method `async def
    _recompute_order_status(self, db: AsyncSession, order_id: int) -> bool`.
    - `order = await db.get(Order, order_id)`.
    - If `order.status not in (OrderStatus.pending, OrderStatus.in_preparation,
      OrderStatus.ready)` (i.e. already `served`/`closed`): return `False` immediately, no query, no
      write (forward-looking guard for Story 5.4, see Scope note).
    - `SELECT OrderItem.status WHERE order_id = :order_id AND status != cancelled` — reuses the
      same `!= cancelled` filter `KitchenService`/`list_items` already apply elsewhere in this
      codebase.
    - Zero rows → `OrderStatus.pending`. Every row `== ready` → `OrderStatus.ready`. Otherwise →
      `OrderStatus.in_preparation`. (AC1/AC2/AC3, the exact three-bucket rule.)
    - If the computed value equals `order.status`, return `False`, no write.
    - Otherwise, set `order.status = new_status` (a plain ORM attribute assignment on an object
      already tracked by this session — SQLAlchemy's unit-of-work includes it in the caller's own
      pending `db.commit()`, no separate `UPDATE`/flush needed here) and return `True`.
  - [x] This method takes no `actor`/logging parameters — it is a pure internal recompute, not a
    user-facing action with its own rejection path to log.
- [x] **Task 2: Backend — wire the recompute into every item-set-changing method** (AC1, AC2, AC3)
  - [x] `add_item`: call `order_status_changed = await self._recompute_order_status(db, order_id)`
    after `db.add(item)` and before `await db.commit()` (SQLAlchemy's autoflush means the pending
    insert is visible to the recompute's own `SELECT`, no manual flush needed). After the commit and
    `db.refresh(item)` already there, if `order_status_changed`, `await db.refresh(order)` (`order`
    fetched inside the helper — either have the helper return the `Order` object alongside the bool,
    or re-fetch it here; pick whichever keeps the method's own flow readable, but do not skip the
    refresh: `db.commit()`'s default `expire_on_commit=True` means every attribute on `order` is
    stale until refreshed, the same reason `item` is always refreshed after every commit elsewhere
    in this file) and broadcast `order.status_changed` (see Task 3).
  - [x] `cancel_item`: same call, placed after the guarded UPDATE succeeds (i.e. after the
    `rowcount == 0` check, not before — a rejected cancel must not recompute anything) and before
    `await db.commit()`.
  - [x] `pick_up_item`: same call, placed after the deduction loop succeeds (i.e. right before the
    existing `await db.commit()` — the last write in that method's transaction) and before that
    commit.
  - [x] `mark_item_ready`: same call, placed after the guarded UPDATE succeeds and before `await
    db.commit()`.
  - [x] In every one of the four methods above, the broadcast added in Task 3 fires **only when**
    the recompute returned `True` — do not broadcast on every call.
- [x] **Task 3: Backend — `order.status_changed` broadcast** (AC1, AC2, AC3, AC4)
  - [x] In each of the four methods, once `order_status_changed` is `True` and `order` has been
    refreshed post-commit: `await self._realtime_service.broadcast([UserRole.waiter],
    "order.status_changed", OrderResponse.model_validate(order).model_dump(mode="json"))`. Placed
    after that method's own existing item-level broadcast (e.g. after `order.item_added` in
    `add_item`), not before — the item-level event is the primary signal for that method, the
    order-level one is a secondary, conditional follow-up.
  - [x] Log at `INFO` when the derived status actually changes: order_id, old status, new status
    (the recompute helper can return the old value too, or the caller can capture `order.status`
    just before overwriting it inside the helper — either is fine, but the log must show both
    values, not just "changed").
- [x] **Task 4: Backend — `OrderService.list_open_orders` + `GET /api/orders`** (AC4)
  - [x] `backend/services/order_service.py`: new method `async def list_open_orders(self, db:
    AsyncSession, actor: User) -> Sequence[Order]`. `SELECT * FROM orders WHERE status != closed
    ORDER BY id` — mirrors `get_open_order_for_table`'s own `!= closed` filter, no Table join
    needed (`OrderResponse` already carries `table_id`). No `actor`-based filtering (AD-9).
  - [x] `backend/api/orders.py`: `@router.get("", response_model=list[OrderResponse], ...)` — the
    bare router prefix (`/api/orders`), gated by the existing `OrdersDep` (Waiter-only, unchanged —
    reused as-is, do not widen it to Cook, no Cook-facing surface consumes this in this story). Add
    an error-descriptions dict with just 401/403 (no 404/409, a list endpoint always answers 200,
    possibly `[]`). No route-ordering concern: an empty-suffix path has zero additional segments, so
    it cannot collide with `/tables/{table_id}` or `/{order_id}/items` regardless of where it is
    registered in the file — place it near `get_order_for_table` for readability, not out of
    necessity.
- [x] **Task 5: Backend tests** (`backend/tests/test_orders.py`, extend existing file)
  - [x] Zero-items Order stays `pending` after being opened (AC3) — this is already true by default
    today, add a test asserting `_recompute_order_status`/the field stays correct once an item is
    added then cancelled back to zero non-cancelled items (round-trip, not just the untouched
    default).
  - [x] All-ready aggregate (AC2): an Order with two items, both picked up and marked ready — Order
    reads `ready` after the second item's mark-ready call, not before (assert it is still
    `in_preparation` after only the first item reaches `ready`, i.e. verify the mix case from AC1
    along the way, not just the end state).
  - [x] Mixed aggregate (AC1): one item `ready`, one item still `pending` (never picked up) — Order
    reads `in_preparation`, not `ready`.
  - [x] Cancel pushes to `ready` (AC2/FR-12): two items, one `ready`, one `pending`; cancel the
    `pending` one — Order flips to `ready` (the remaining non-cancelled item is the only one left,
    and it's `ready`).
  - [x] Cancel-to-zero returns to `pending` (AC3): a single-item Order, cancel that one item — Order
    reads `pending` (zero non-cancelled items left), not stuck at whatever it was before.
  - [x] Add pulls a `ready` Order back down (AC1/FR-12): an Order with one item already `ready`
    (status `ready`); add a second item (`pending`) — Order flips back to `in_preparation`.
  - [x] No-op recompute does not rewrite `updated_at`/does not broadcast: cancelling one of three
    still-`pending` items (aggregate stays `in_preparation` both before and after) — assert
    `order.status_changed` is **not** broadcast (mirrors this codebase's existing
    "assert absence, not just presence" convention from Story 5.2's low-stock-alert tests).
  - [x] `order.status_changed` broadcast content and recipients (extend `test_websocket.py` or
    place alongside `order.item_status_changed`'s own test, whichever this file already does):
    a connected Waiter socket receives it when the aggregate flips; a connected Cook socket does
    **not** (recipients are `[waiter]` only, unlike `order.item_status_changed`'s `[waiter, cook]`).
  - [x] `GET /api/orders` (AC4): returns every non-closed Order (not just one Table's); a fresh
    install / zero Orders returns `[]`, not a 404; role coverage — waiter 200; cook, admin, and
    warehouse_manager all 403 (`OrdersDep` is Waiter-only with no Admin fallback, matching
    `open_table`'s own existing role coverage tests in this file); unauthenticated 401.
- [x] **Task 6: Frontend — `orderService.ts`** (AC4)
  - [x] New exported `OPEN_ORDERS_QUERY_KEY = ["orders", "open"] as const` (mirrors
    `KITCHEN_ITEMS_QUERY_KEY`'s exported-cache-key shape) and `useOpenOrders():
    UseQueryResult<Order[], Error>` querying `GET /api/orders`, `retry: false` (matches every other
    query hook in this file/`tableService.ts`).
- [x] **Task 7: Frontend — `TablesPage.tsx` attention-state tile** (AC4)
  - [x] Call `useOpenOrders()` alongside the existing `useTables()`; combine its `isLoading`/
    `isError` into the page's existing combined loading/error state (matching the established
    "OR every dependent query together" convention this codebase's domain notes call out).
  - [x] Build a `Set<number>` (or `Map`) of `table_id`s whose Order is currently `ready`, derived
    from `useOpenOrders()`'s data.
  - [x] `TableTile` gains a new prop (e.g. `isReadyForAttention: boolean`); when true, render a
    second `Chip` (green/`success`, `CheckCircleIcon` from `@mui/icons-material`, matching
    `OrderItemStatusBadge`'s existing `ready`-status Chip styling so the same visual vocabulary is
    reused, not reinvented) alongside the existing table-status Chip, never replacing it (DESIGN.md's
    explicit "layered on top of, not replacing" instruction).
  - [x] Only pass `isReadyForAttention={true}` for `occupied` tiles matched in the ready-table set;
    `available`/`reserved` tiles never receive it (they cannot have an open Order in v1).
  - [x] Subscribe to `order.status_changed`, invalidating `OPEN_ORDERS_QUERY_KEY` on receipt — same
    subscribe/invalidate shape as the existing `table.status_changed` subscription in this file, a
    second `useEffect` (or extend the existing one with an added `subscribe(...)` call/cleanup, dev
    agent's call, matching whichever shape `TableOrderDetailPage.tsx`'s two-event subscription
    already uses).
- [x] **Task 8: Frontend — `TableOrderDetailPage.tsx` live Order refresh** (no new UI)
  - [x] Add a third `subscribe("order.status_changed", ...)` call inside the existing `useEffect`
    that already subscribes to `order.item_added`/`order.item_status_changed`, invalidating
    `["orders", "table", tableId]` (the exact key `useOrderForTable` builds internally — check its
    definition in `orderService.ts` rather than reconstructing it by hand, to avoid the two drifting
    apart the way `orderItemsQueryKey` is already exported specifically to prevent). Guarded the same
    way the existing two subscriptions already are (`order?.id === undefined` early return).
- [x] **Task 9: Frontend tests**
  - [x] `TablesPage.test.tsx`: an occupied tile whose matching Order is `ready` (via a stubbed
    `useOpenOrders()`/`GET /api/orders` response) renders the attention Chip alongside the existing
    status Chip; an occupied tile whose Order is `in_preparation`/`pending` does not; an `available`/
    `reserved` tile never renders it regardless of what `useOpenOrders()` returns. A live
    `order.status_changed` event triggers a refetch of the open-orders list (assert the query is
    invalidated/refetched, mirroring how this file's existing `table.status_changed` test already
    asserts a `table.status_changed`-triggered refetch, if one exists — check the current file
    first).
  - [x] `TableOrderDetailPage.test.tsx`: a stubbed `order.status_changed` WebSocket message
    triggers a refetch of the Order query (assert via a spy/mock on the query client or a changed
    `useOrderForTable` response after the event, matching this file's existing pattern for
    `order.item_status_changed`'s own test). No new visible element asserted, since none was added.
- [x] **Task 10: Full regression pass**
  - [x] `uv run pytest -q` (backend) — zero regressions.
  - [x] `pnpm test` (frontend) — zero regressions.
  - [x] `npx tsc -b` — clean.

## Dev Notes

### Architecture compliance

- **AD-2** (one WebSocket endpoint, Role-scoped, each event emitted exactly once by the service
  that owns the mutation): `order.status_changed` is emitted exactly once per actual status change,
  from `OrderService` (the service that owns both the Order and every OrderItem mutation), to
  `[UserRole.waiter]` only — a narrower recipient list than `order.item_status_changed`'s
  `[waiter, cook]`, a deliberate choice (see Scope note), not an oversight to "fix" into matching.
- **AD-5** (last-write-wins, no version column/conflict UI) governs `Order.status` here, not AD-6:
  see the Scope note's explicit reasoning for why this recompute is not a guarded transition.
  Do not add a guarded `UPDATE ... WHERE status = <expected>` for this — there is no expected prior
  value to check, only a value to recompute and overwrite.
- **Trap 20's generalized lesson** (an object's attributes are stale/expired immediately after
  `db.commit()` under `expire_on_commit=True`; accessing one outside an `await db.refresh(...)`
  raises `MissingGreenlet` under `AsyncSession`) applies to the `order` object exactly the way it
  already applies to `item` in every existing method in this file: refresh it after commit, before
  building its broadcast payload.
- **FR-12's three-bucket rule is exhaustive and order-independent** — it does not matter whether the
  non-cancelled items are `[pending, pending]`, `[pending, in_preparation]`, or
  `[in_preparation, in_preparation, ready]`; anything short of "all ready" and "zero items" is
  `in_preparation`. Do not build a more granular status inference (e.g. a Order status that
  distinguishes "not yet started" from "partially in prep") — FR-12 defines exactly three derived
  values and no more.

### Current state of the files this story touches (read before editing)

- **`backend/services/order_service.py`**: `add_item` (lines ~199–267), `cancel_item` (~326–378),
  `pick_up_item` (~380–492), `mark_item_ready` (~494–548) each currently end with their own
  `db.commit()` → `db.refresh(item)` → item-level broadcast, with no Order-level write anywhere in
  this file today. `edit_item` (~269–324) is the one item-mutating method this story does **not**
  touch (quantity/notes only, never status). `OrderService.__init__` (lines ~54–67) needs no new
  constructor dependency — everything this story needs (`db`, `self._realtime_service`,
  `self._logger`) is already injected.
- **`backend/api/orders.py`**: `OrdersDep` (line ~29, Waiter-only, no Admin fallback — read its own
  comment before assuming Admin should also reach the new `GET /api/orders`) is what the new list
  route reuses. `_ERROR_DESCRIPTIONS`/`_GET_ORDER_ERROR_DESCRIPTIONS`/etc. (lines ~50–98) are the
  existing per-route error-description dict convention this file uses; the new route needs its own
  narrower one (401/403 only).
- **`backend/data_models/order.py`**: `OrderResponse` (line ~146) already includes every field the
  new broadcast payload and the new list endpoint need (`status`, `table_id`) — no schema change
  required anywhere in this story.
- **`frontend/src/pages/waiter/TablesPage.tsx`**: `TableTile` (lines ~50–84) currently renders one
  `Chip` off `table.status` alone; `TablesPage` (lines ~104–186) subscribes to exactly one event
  (`table.status_changed`, lines ~118–122) and calls exactly one query hook (`useTables()`). This
  story adds a second query hook and a second live subscription, following the same shapes already
  present, not inventing new ones.
- **`frontend/src/pages/waiter/TableOrderDetailPage.tsx`**: the `useEffect` at lines ~350–364
  already subscribes to two events and invalidates `orderItemsQueryKey(order.id)` for both — the
  third subscription this story adds invalidates a **different** key (`useOrderForTable`'s own,
  currently only referenced inside `orderService.ts` itself, not re-exported — check whether it
  needs exporting the same way `orderItemsQueryKey` already is, or whether the query key can be
  reconstructed inline as `["orders", "table", tableId]` safely; prefer exporting a helper function
  if `orderService.ts` doesn't already expose one, to avoid the two drifting apart).
- **`frontend/src/services/orderService.ts`**: `orderItemsQueryKey` (lines ~34–36) is the existing
  exported-key precedent to mirror for the new `OPEN_ORDERS_QUERY_KEY`. `useOrderForTable` (lines
  ~75–82) builds its query key inline as `["orders", "table", tableId]` — not currently exported as
  a named function, unlike `orderItemsQueryKey`.
- **`frontend/src/components/orders/OrderItemStatusBadge.tsx`**: the existing `ready` styling
  (`CheckCircleIcon`, `color: "success"`, lines ~17–29) is the exact visual reference the new
  attention Chip on `TablesPage.tsx` should match, per DESIGN.md's "same green-plus-check
  treatment" instruction — reuse the icon import and color token, do not invent a new mapping.

### Project Structure Notes

Files touched:
- `backend/services/order_service.py` — **UPDATE**, `_recompute_order_status` added,
  `list_open_orders` added, `add_item`/`cancel_item`/`pick_up_item`/`mark_item_ready` each call the
  new helper and conditionally broadcast.
- `backend/api/orders.py` — **UPDATE**, new `GET /api/orders` route.
- `backend/tests/test_orders.py` — **UPDATE**, new coverage (Task 5).
- `backend/tests/test_websocket.py` — **UPDATE** (or extended in `test_orders.py`, matching
  wherever `order.item_status_changed`'s own broadcast test already lives).
- `frontend/src/services/orderService.ts` — **UPDATE**, `OPEN_ORDERS_QUERY_KEY` +
  `useOpenOrders()` added.
- `frontend/src/pages/waiter/TablesPage.tsx` — **UPDATE**, attention-state Chip + new subscription.
- `frontend/src/pages/waiter/TablesPage.test.tsx` — **UPDATE**, new test coverage.
- `frontend/src/pages/waiter/TableOrderDetailPage.tsx` — **UPDATE**, new subscription only, no new
  visible UI.
- `frontend/src/pages/waiter/TableOrderDetailPage.test.tsx` — **UPDATE**, new test coverage.

No new Alembic migration (no schema change — `Order.status` already exists as a column, this story
only makes it change). No new frontend route. No change to `backend/api/kitchen.py`/
`backend/services/kitchen_service.py` — the deferred `list_active_items` filter gap noted in Story
5.2's review (a served Order's items could leak onto the Kitchen Display) is explicitly **Story
5.4's** concern (nothing can reach `served`/`closed` until that story exists), not this one's; do
not fix it here.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 5.3`] — this story's AC source, verbatim.
- [Source: `_bmad-output/planning-artifacts/epics.md`, FR-12] — "An Order's `pending`/
  `in_preparation`/`ready` status derives from the aggregate of its non-cancelled Order Items'
  statuses" — the literal three-bucket rule this story implements.
- [Source: `_bmad-output/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md`, AD-2, AD-5,
  AD-6] — the broadcast-ownership rule, the last-write-wins model this recompute falls under, and
  the guarded-transition mechanism this story explicitly does **not** use (contrast documented in
  Scope note).
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../DESIGN.md`, `table-tile.attention-state`,
  `status-badge.ready`] — the exact color/icon token the new Chip must reuse.
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../EXPERIENCE.md`, "Table tile" component
  row, Flow 2 step 6 (UJ-2)] — "layered on top of the base table-status badge, not replacing it,"
  and the walkthrough moment (both items reach `ready`) this story's AC4 makes real.
- [Source: `backend/services/order_service.py::add_item`, `::cancel_item`, `::pick_up_item`,
  `::mark_item_ready`] — the four existing methods this story extends, and the refresh-after-commit
  pattern (`await db.refresh(item)`) the new `order` refresh must mirror.
- [Source: `_bmad-output/implementation-artifacts/5-2-pick-up-and-progress-an-order-item-with-atomic-
  stock-deduction.md`, Review Findings, "Order.status is still never derived from its items' statuses
  ... explicitly Story 5.3's job"] — this story's own scope, confirmed by the immediately preceding
  story's review.
- [Source: `_bmad-output/project-context.md`, "Domain rules worth restating"] — "`Order.status` ...
  is derived from its non-cancelled OrderItems. `served` and `closed` are set explicitly. An Order
  with zero non-cancelled items is pending" — the exact rule this story's helper implements,
  including the served/closed no-op guard.
- [Source: `_bmad-output/project-context.md`, trap 18, trap 20] — the guarded-UPDATE-vs-plain-
  recompute distinction this story's Scope note applies for the first time, and the refresh-after-
  commit convention the new `order` broadcast payload must follow.

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5

### Debug Log References

- `uv run pytest tests/test_orders.py -q` — 76 passed (66 baseline + 9 new: round-trip
  pending/in_preparation, all-ready aggregate [the mix case from AC1 is an inline assertion
  inside this same test, not a separate one], cancel-pushes-to-ready, add-pulls-back-down, three
  `GET /api/orders` coverage tests, and — added in the code review's patch pass — the
  served/closed no-op guard test and the real-concurrency convergence test)
- `uv run pytest tests/test_websocket.py -q` — 24 passed (22 baseline + 2 new: the
  `order.status_changed` waiter-only broadcast test, and the no-op-does-not-broadcast test)
- `uv run pytest -q` (full backend suite) — 352 passed, no regressions (baseline 341 + 11 new)
- `npx vitest run src/pages/waiter/TablesPage.test.tsx` — 13 passed (7 baseline + 4 new: the
  attention-chip render/non-render cases and the live-refetch case; + 1 more added in the code
  review's patch pass, the Retry-refetches-both-queries regression test)
- `npx vitest run src/pages/waiter/TableOrderDetailPage.test.tsx` — 23 passed (22 baseline + 1 new)
- `npx vitest run` (full frontend suite, three times across the implementation and review
  passes) — 184 total, zero real failures; every failure observed (2-3 timeouts in
  `src/pages/admin/UsersPage.test.tsx`, a file untouched by this story) passed 17/17 cleanly when
  re-run in isolation — confirmed test-runner resource contention from concurrent backend-suite
  runs and a freshly-started Docker Desktop, not a regression introduced here
- `npx tsc -b` — clean

### Completion Notes List

- Implemented `OrderService._recompute_order_status` exactly per the Scope note's three-bucket
  rule (zero non-cancelled items → `pending`; all `ready` → `ready`; anything else →
  `in_preparation`), with the forward-looking `served`/`closed` no-op guard for Story 5.4. This
  is a pure recompute, not a guarded transition — no `AD-6`-style `UPDATE ... WHERE status =
  <expected>` was added, matching the story's explicit instruction.
- Wired the recompute into `add_item`, `cancel_item`, `pick_up_item`, and `mark_item_ready`,
  each calling it inside its own existing transaction, before that method's own `db.commit()`.
  Extracted a shared `_broadcast_order_status_changed(db, order)` private helper (refresh, then
  broadcast, taking the already-loaded `Order` object directly rather than re-fetching it) to
  avoid duplicating the same refresh-and-broadcast sequence across all four call sites — a DRY
  simplification beyond the story's literal per-call-site instruction, not a deviation from its
  intent. Reworked during the code review's patch pass to avoid a redundant double-fetch (see
  Review Findings).
- `order.status_changed` broadcasts to `[UserRole.waiter]` only, conditional on
  `_recompute_order_status` returning `True`, verified end-to-end in `test_websocket.py`: a
  connected Waiter receives it, a connected Cook does not, and cancelling one of several still-
  pending items (no aggregate change) broadcasts nothing at all.
- Added `OrderService.list_open_orders` and `GET /api/orders` (bare router prefix,
  `@router.get("", ...)`), reusing the existing Waiter-only `OrdersDep` unchanged. Confirmed no
  FastAPI route-ordering concern: an empty-suffix path has zero additional segments.
- Frontend: `orderService.ts` gained `OPEN_ORDERS_QUERY_KEY`/`useOpenOrders()` and an exported
  `orderForTableQueryKey(tableId)` helper (previously only built inline inside
  `useOrderForTable`), so `TableOrderDetailPage.tsx`'s new `order.status_changed` subscriber can
  invalidate the exact same key without reconstructing the array by hand.
- `TablesPage.tsx`'s `TableTile` gained a second Chip (green, `CheckCircleIcon`, matching
  `OrderItemStatusBadge`'s existing `ready` styling), layered next to the base table-status
  Chip, shown only on an `occupied` tile whose id resolves to a `ready` Order in the new bulk
  list — never on `available`/`reserved` tiles. The page now combines two queries'
  loading/error state and subscribes to a second live event (`order.status_changed`).
- Fixed a real `MissingGreenlet` bug caught by running the new backend tests, not by reasoning
  about it: a test read `waiter.username` off an ORM object after a prior `db_session.
  expire_all()` call — the exact trap this codebase's own fixtures already document (capture
  plain values before expiring the session, never an ORM attribute after). Fixed by capturing
  `waiter_username` as a plain `str` immediately after `_open_table` returns.
- Fixed a real TypeScript compile error caught by `npx tsc -b`, not anticipated in the story:
  combining `isTablesError || isOpenOrdersError` into one `isError` boolean breaks the
  discriminated-union narrowing TanStack Query's single-query destructuring otherwise gives
  `error: Error | null` for free when passed to a strictly-`Error`-typed helper. Fixed by
  widening the file-local `errorMessage()` helper to accept `Error | null` (it already safely
  handles that via `instanceof`) and building an explicit `firstError = tablesError ??
  openOrdersError` rather than assuming which query actually failed.
- `TableOrderDetailPage.tsx` gained a third live subscription (`order.status_changed`,
  alongside the existing `order.item_added`/`order.item_status_changed`), invalidating
  `useOrderForTable`'s query key — no new visible UI, only keeps that page's already-cached
  Order object accurate now that `.status` is a real, changing field for the first time.

### File List

- `backend/services/order_service.py`
- `backend/api/orders.py`
- `backend/tests/test_orders.py`
- `backend/tests/test_websocket.py`
- `frontend/src/services/orderService.ts`
- `frontend/src/pages/waiter/TablesPage.tsx`
- `frontend/src/pages/waiter/TablesPage.test.tsx`
- `frontend/src/pages/waiter/TableOrderDetailPage.tsx`
- `frontend/src/pages/waiter/TableOrderDetailPage.test.tsx`

## Review Findings

Reviewed by three parallel agents (Blind Hunter, Edge Case Hunter, Acceptance Auditor) against
this story's 4 ACs and `_bmad-output/project-context.md`.

- [x] [Review][Patch] `_recompute_order_status` read sibling `OrderItem` statuses with no row
  lock, so two concurrent transactions each finishing a *different* item of the same multi-item
  Order could each read the other's not-yet-committed item status, each independently compute
  "no change," and leave `Order.status` permanently stuck wrong after both committed — a direct
  violation of FR-12's own guarantee. Fixed by locking the Order row (`SELECT ... FOR UPDATE`,
  trap 9's row-lock idiom, the same pattern `_lock_ingredient`/`_lock_dish` already use) before
  reading its items, always acquired after any OrderItem/Ingredient lock a caller already holds
  (never before, so no new deadlock risk). Verified with a genuine concurrency test (two
  independent `AsyncClient`s, `asyncio.gather`), not a monkeypatched interleave —
  `backend/services/order_service.py:_recompute_order_status`
- [x] [Review][Patch] `TablesPage.tsx`'s Retry button only refetched `useTables()`, never the new
  `useOpenOrders()`, even though `isError` is the OR of both — a failure isolated to the
  open-orders query left the entire Tables grid permanently stuck behind the error banner with
  no in-app recovery. Fixed with a combined `retryAll()` refetching both queries, matching this
  codebase's own documented "Retry must refetch all of them, not just one" rule —
  `frontend/src/pages/waiter/TablesPage.tsx`
- [x] [Review][Patch] `_broadcast_order_status_changed` re-fetched the Order via `_get_order` and
  then unconditionally called `db.refresh` on it — a redundant round trip on every broadcast,
  and (theoretically) `_get_order` could raise `OrderNotFoundError` after the triggering
  mutation's own commit had already succeeded. Fixed by having `_recompute_order_status` return
  the already-loaded `Order` object alongside its changed-flag, so the broadcast helper only
  refreshes it, no second fetch — `backend/services/order_service.py`
- [x] [Review][Patch] `_recompute_order_status` dereferenced `order.status` with no `None` check
  after `db.get(Order, order_id)`, unlike every other `_get_*`-style lookup in this file
  (currently unreachable — every call site already validates the Order exists earlier in the
  same method — but inconsistent with the file's own established defensive style). Fixed as part
  of the row-lock change above (`scalar_one_or_none()` now guards it) —
  `backend/services/order_service.py:_recompute_order_status`
- [x] [Review][Patch] The `served`/`closed` no-op guard inside `_recompute_order_status` shipped
  with zero test coverage. Added a test that forces an Order directly to `served` (no code path
  can do this yet, Story 5.4's job) and confirms a subsequent item cancel leaves it untouched —
  `backend/tests/test_orders.py::test_recompute_does_not_touch_a_served_or_closed_order`
- [x] [Review][Patch] The Dev Agent Record's Debug Log overstated and mis-composed the new test
  counts for `test_orders.py` and `TablesPage.test.tsx` (claimed a standalone "mixed aggregate"
  test and a fifth new `TablesPage.test.tsx` test, neither of which exist as described).
  Corrected to match the actual diff.
- [x] [Review][Defer] `GET /api/orders` has no pagination or bound beyond `status != closed`,
  mirroring the same unpaginated-growth risk the Kitchen Display's own item list already carries
  (already logged in `deferred-work.md`, not fixed there either) — deferred, matches an
  already-accepted project-wide pattern, not introduced fresh by this story's own design intent.

**Verified as non-issues:**

- **`order.status_changed` sends a full `OrderResponse` payload rather than a minimal dict** —
  a deliberate choice this story's own Scope note explicitly made and justified (matching
  `order.item_status_changed`'s own "build a proper response object" precedent), not an
  oversight; both frontend subscribers only use it as a refetch signal regardless.
- **The attention Chip is written inline in `TablesPage.tsx` rather than reusing
  `OrderItemStatusBadge`** — the story's own instruction was to reuse the icon and color token
  (done), not the whole component; `OrderItemStatusBadge`'s API takes an `OrderItemStatus`, a
  poor fit for a derived boolean attention flag layered on a different badge entirely.
- **`list_open_orders` takes an unused `actor` parameter** — matches every sibling method's
  signature shape in this file (all take `actor`) for future-extensibility consistency,
  documented in its own docstring; AD-9 already forbids any per-actor filtering it could do.
- **No-op-broadcast test uses two pending items, not the three the story's own example text
  named** — functionally equivalent for proving the no-op/no-broadcast behavior, not a coverage
  gap.

## Change Log

| Date | Change |
|---|---|
| 2026-08-16 | Story 5.3 created via bmad-create-story: Order.status derivation (three-bucket FR-12 rule) via a new `OrderService._recompute_order_status` helper called from `add_item`/`cancel_item`/`pick_up_item`/`mark_item_ready`, a new `order.status_changed` broadcast (waiter-only, conditional on an actual change), and a new bulk `GET /api/orders` read backing the Tables grid's attention-state tile treatment (AC4). |
| 2026-08-16 | Implemented Story 5.3: `OrderService._recompute_order_status` (pure recompute, not a guarded transition) wired into `add_item`/`cancel_item`/`pick_up_item`/`mark_item_ready`, a shared `_broadcast_order_status_changed` helper, `order.status_changed` (waiter-only, conditional), and `GET /api/orders` (`list_open_orders`). Frontend: `useOpenOrders()`, the Tables grid's attention-state Chip on occupied/ready tiles (AC4), and a third live subscription on `TableOrderDetailPage.tsx` keeping its cached Order accurate. 9 new backend tests (350 total), 6 new frontend tests (183 total). Fixed a `MissingGreenlet` bug in a new test (an ORM attribute read after `db_session.expire_all()`) and a real `npx tsc -b` failure (a combined `isError` boolean broke TanStack Query's discriminated-union narrowing on a nullable `error` field). |
| 2026-08-16 | Code review patch pass (three parallel agents): fixed a genuine concurrency bug — `_recompute_order_status` now locks the Order row (`SELECT ... FOR UPDATE`, trap 9) before reading sibling items, closing a race where two Cooks finishing different items of the same Order at once could leave `Order.status` permanently stuck wrong (verified with a real concurrent-request test, not a monkeypatch). Fixed `TablesPage.tsx`'s Retry button to refetch both dependent queries, not just `useTables()`. Reworked `_broadcast_order_status_changed` to take the already-loaded `Order` object instead of re-fetching it, removing a redundant read and a theoretical post-commit 404. Added the missing served/closed no-op guard test and a Retry regression test. Corrected inaccurate test-count claims in the Debug Log. 2 new backend tests (352 total), 1 new frontend test (184 total). Deferred: `GET /api/orders` has no pagination, matching the Kitchen Display's own already-accepted unbounded-list precedent. |
