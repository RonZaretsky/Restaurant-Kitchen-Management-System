---
baseline_commit: 3131f9af633603375b8656985fca11b1e2eb0205
epic: 5
story: 1
---

# Story 5.1: View Incoming Orders in Real Time (Kitchen Display)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Cook,
I want to see new and updated order items on the kitchen display instantly,
so that I never miss or double-handle an item.

## Scope note (read first)

**Epic 5 opens. This is a read-only display story — no pick-up/mark-ready actions.** Story 5.2 adds
the one-click pending→in_preparation→ready transitions; this story only makes the Kitchen Display
show live data. Do not add any action button, click handler, or state-transition endpoint here.

**Two of this story's ACs are already fully built and need zero new code — verify, don't
reimplement:**

- **Dark-theme initialization (UX-DR7).** `ThemeModeProvider.tsx`'s own docstring: "With no stored
  preference yet, defaults to dark for a Cook (Kitchen Display's home surface) and light for every
  other Role, per AC4." This was built ahead of this story, forward-looking. Confirmed correct by
  reading the code directly — no change needed.
- **"Reconnecting..." on a dropped WebSocket (UX-DR16).** `ReconnectingBanner` (Story 1.5) already
  renders globally inside `AppShell.tsx` for every Role, including Cook. No Kitchen-Display-specific
  reconnect UI is needed.

**What actually needs building:**

1. **A new `kitchen` domain, backend and frontend, from scratch** — `api/kitchen.py`,
   `services/kitchen_service.py`, `services/kitchenService.ts`, all new. The story's own last AC
   states this explicitly: "the `kitchen` domain router does not yet exist... `kitchen` is appended
   to `container.wire(modules=[...])`, alongside the existing entries, not replacing them" (AD-1).
   Same for `main.py`'s `container.wire(modules=[...])` list (currently 8 entries, all `api.*`
   modules) and `api/router.py` (currently 7 `include_router()` calls).

2. **A genuine backend join — the first one in `backend/services/`.** Every prior story in this
   codebase avoided joins by returning raw ids and letting the frontend resolve names from
   already-fetched reference data (confirmed repeatedly: `OrderItemResponse.dish_id`/`cook_id`,
   `StockMovementResponse.performed_by`, all bare ids, no `join`/`selectinload`/`joinedload`
   anywhere in `services/` as of this story's baseline). That precedent holds here too for dish
   names (frontend resolves via the already-cook-permitted `useDishes()`) — **but not for grouping
   by table**. The Kitchen Display's whole point is "items grouped under its Table's card," and
   `OrderItem` has no `table_id` of its own (only `order_id`); `Order` has `table_id` but there is
   no existing endpoint that maps an arbitrary `order_id` to its `table_id` for an unrelated Cook
   session (unlike the Waiter path, which always starts from a known `table_id` via `GET
   /api/orders/tables/{table_id}`). A one-table join (`OrderItem` joined to `Order` for its
   `table_id` column only) is the honest fix, not a second frontend round trip per unique
   `order_id` on the page. This is a deliberate, first-of-its-kind exception to the
   raw-ids-only precedent — call it out by name in the PR/commit, not silently.

3. **Widen two existing Role grants, don't duplicate them:**
   - `OrderService.add_item`'s existing `order.item_added` broadcast
     (`backend/services/order_service.py` line ~250) currently targets `[UserRole.waiter]` only.
     Widen to `[UserRole.waiter, UserRole.cook]` — the Kitchen Display's whole live-push
     requirement (AC1) rides on this one event, there is no second "kitchen-scoped" event to
     invent. **This breaks an existing regression test on purpose**:
     `backend/tests/test_websocket.py::test_adding_an_order_item_broadcasts_order_item_added`
     currently asserts "the event is Waiter-scoped, a Cook receives nothing" — that assertion must
     flip to "a connected Cook also receives it," not be deleted. Finding and fixing this
     is itself a task below, not an incidental side effect to discover during code review.
   - `TablesReadDep` (`backend/api/tables.py`) currently permits `admin, waiter`. Widen to also
     permit `UserRole.cook` — the Kitchen Display's frontend needs `table_number` for each card's
     header, and the established pattern for resolving that (client-side, via the already-cached
     `useTables()`, exactly like `TableOrderDetailPage.tsx`'s own heading) requires Cook to be able
     to call `GET /api/tables` at all. This is the same incremental-widening pattern
     `InventoryReadDep`/`DishCatalogReadDep`/`MenuReadDep` have each gone through story by story —
     reuse the dependency object, do not create a second one.

4. **Filter scope, honestly stated for what exists today, not over-engineered for what doesn't
   yet.** The Kitchen Display should show every non-cancelled Order Item currently in play
   (`OrderItem.status != cancelled`) — no additional filter on the *Order's* own status is needed
   **yet**, because nothing in this codebase can currently move an Order to `served`/`closed`
   (Stories 5.3/5.4, not built). Once those ship, an Order reaching `served` does **not** reset its
   items' own `ready` status, so a naive `OrderItem.status != cancelled` filter would then start
   leaking already-served orders' `ready` items onto the Kitchen Display forever. **This is a
   known, explicitly-flagged forward-compatibility gap for whichever of Stories 5.3/5.4 ships
   next** (they should add `Order.status not in (served, closed)` to this query's join condition) —
   not something to solve speculatively now with no way to test it honestly (mirrors this
   codebase's own established precedent for exactly this situation, e.g. `add_item`'s
   "no guard exists yet against adding to a non-pending Order" note from Story 3.2).

## Acceptance Criteria

1. **Given** a new Order Item is added by a Waiter (Epic 3), **when** it's submitted, **then** it
   appears on the Kitchen Display grouped under its Table's card within 2 seconds via WebSocket
   push, with no manual refresh (FR-9, NFR-1, AD-2).
2. **Given** the Kitchen Display has no orders in the queue, **when** it loads, **then** it shows
   "No orders in the queue" (UX-DR15).
3. **Given** the WebSocket connection drops, **when** detected, **then** "Reconnecting..." is shown
   and retried automatically (UX-DR16), most critical on this surface. *(Already implemented,
   `ReconnectingBanner`/Story 1.5 — verify, do not touch `ReconnectingBanner.tsx`.)*
4. **Given** a Cook opens the Kitchen Display, **when** it renders, **then** it initializes in dark
   theme (UX-DR7), cards render at elevation 1, and each Order Item row within a card shows its
   status badge (UX-DR1). *(Dark-theme init: already implemented, `ThemeModeProvider.tsx` — verify,
   do not touch. Elevation 1: MUI `Card`'s own default, no override needed. Status badge: reuse
   `OrderItemStatusBadge` verbatim.)*
5. **Given** the `kitchen` domain router does not yet exist, **when** this story adds it, **then**
   `kitchen` is appended to `container.wire(modules=[...])`, alongside the existing entries, not
   replacing them (AD-1).

## Tasks / Subtasks

- [x] **Task 1: Backend — `KitchenItemResponse` schema** (AC1)
  - [x] Add to `backend/data_models/order.py` (same file as `OrderItemResponse`, this is still the
    `orders` domain's own data, just a cross-table read shape): `KitchenItemResponse(BaseModel)`
    with `id`, `order_id`, `table_id`, `dish_id`, `quantity`, `status`, `notes`, `cook_id`,
    `price_at_add` — `OrderItemResponse`'s exact field set plus `table_id`. `model_config =
    {"from_attributes": True}` won't work directly since `table_id` isn't a column on `OrderItem`
    itself (see Task 2's join) — construct instances explicitly rather than relying on
    `from_attributes`, or use a `@classmethod` constructor taking `(item: OrderItem, table_id:
    int)`. Export it from `data_models/__init__.py` alongside `OrderItemResponse`.
- [x] **Task 2: Backend — `KitchenService.list_active_items`** (AC1, AC2)
  - [x] New `backend/services/kitchen_service.py`, `KitchenService` class, config-free (`logger`
    only, no `realtime_service` — this service only reads, `OrderService` owns the one broadcast it
    needs, see Task 3).
  - [x] `list_active_items(self, db: AsyncSession) -> Sequence[KitchenItemResponse]`:
    `select(OrderItem, Order.table_id).join(Order, OrderItem.order_id == Order.id).where(
    OrderItem.status != OrderItemStatus.cancelled).order_by(Order.table_id, OrderItem.id)` — the
    one join this story explicitly justifies (see Scope note). No actor argument: a plain read with
    nothing to reject or audit, matching `list_ingredients`/`list_items`'s own precedent.
  - [x] Build `KitchenItemResponse` instances from each `(OrderItem, table_id)` row pair.
- [x] **Task 3: Backend — `GET /api/kitchen/items` route** (AC1, AC2, AC5)
  - [x] New `backend/api/kitchen.py`: `router = APIRouter(prefix="/api/kitchen", tags=["kitchen"])`.
    `KitchenReadDep = Annotated[User, Depends(require_role(UserRole.cook, UserRole.admin))]`
    (mirrors every other read-dep's "primary Role + admin" shape).
    `GET /items`, `response_model=list[KitchenItemResponse]`, calls
    `kitchen_service.list_active_items(db)`. Empty list is a valid response (AC2), not a 404.
  - [x] Register in `backend/api/router.py`: import and `include_router(kitchen_router)`, alongside
    the existing 7.
  - [x] Register in `backend/container.py`: `kitchen_service = providers.Factory(KitchenService,
    logger=logging)` — no ordering constraint (trap 23 does not apply, this service takes no other
    provider as a dependency).
  - [x] Register in `backend/main.py`'s `container.wire(modules=[...])`: append `"api.kitchen"`
    (AC5, this story's own explicitly-named requirement — do not forget it, the route will 500 with
    a DI resolution error at request time, not at import time, if this is skipped).
- [x] **Task 4: Backend — widen `order.item_added`'s broadcast to include Cook** (AC1)
  - [x] In `backend/services/order_service.py`'s `add_item`, change
    `self._realtime_service.broadcast([UserRole.waiter], "order.item_added", ...)` to
    `self._realtime_service.broadcast([UserRole.waiter, UserRole.cook], "order.item_added", ...)`.
  - [x] **Fix the now-outdated regression test**:
    `backend/tests/test_websocket.py::test_adding_an_order_item_broadcasts_order_item_added`
    currently connects a Cook socket and asserts `pytest.raises(asyncio.TimeoutError)` on it (i.e.
    "Cook receives nothing"). Flip that assertion: the Cook socket should now receive the same
    `order.item_added` message the Waiter socket does. Do not delete or weaken the test — the
    Waiter-still-receives-it half must stay exactly as strict as before.
- [x] **Task 5: Backend — widen `TablesReadDep` to include Cook** (AC1)
  - [x] `backend/api/tables.py`: `TablesReadDep = Annotated[User, Depends(require_role(UserRole.admin,
    UserRole.waiter, UserRole.cook))]`. `TablesDep` (write, admin-only) stays unchanged.
- [x] **Task 6: Backend tests** (`backend/tests/test_kitchen.py`, new file)
  - [x] `GET /api/kitchen/items` returns an empty list when nothing is active.
  - [x] A `pending` Order Item on an open Order appears in the response with the correct `table_id`.
  - [x] Items across two different Tables' Orders both appear, each with their own correct
    `table_id` (proves the join, not a hardcoded/first-row value).
  - [x] A cancelled Order Item is excluded.
  - [x] `in_preparation`/`ready` items are included (nothing in this story can produce them yet via
    the API — insert directly via `db_session` in the test, matching this codebase's existing
    shortcut for fixture setup that has no API path yet).
  - [x] Role coverage: cook and admin can each read `/items`; waiter and warehouse_manager are
    rejected 403; unauthenticated is rejected 401.
  - [x] `GET /api/tables` (existing endpoint, widened dep): cook can now read it; add this as a
    `test_tables.py` addition, not a new file, mirroring how Story 3.1 tested `TablesReadDep`'s
    waiter-widening in the same existing file.
  - [x] Broadcast test in `test_websocket.py` (edit the existing test per Task 4, plus optionally a
    dedicated new test if the edit reads awkwardly): a connected Cook now receives `order.item_added`
    within the 2-second window, same payload shape the Waiter receives.
- [x] **Task 7: Frontend — types and service hook** (AC1, AC2)
  - [x] `frontend/src/types/kitchen.ts` (new): `KitchenItem` interface mirroring
    `KitchenItemResponse` exactly (snake_case, matching every other type in this codebase's own
    convention) — `id`, `order_id`, `table_id`, `dish_id`, `quantity`, `status` (reuse
    `OrderItemStatus` from `types/order.ts`, do not redeclare it), `notes`, `cook_id`,
    `price_at_add`.
  - [x] `frontend/src/services/kitchenService.ts` (new): `useKitchenItems(): UseQueryResult<KitchenItem[],
    Error>` (`GET /api/kitchen/items`, `retry: false`, matches every other query hook). Export
    `KITCHEN_ITEMS_QUERY_KEY` as a module constant (mirrors `ALERTS_QUERY_KEY`'s cross-file-export
    precedent) so the page's own `order.item_added` subscriber can invalidate it.
- [x] **Task 8: Frontend — `KitchenDisplayPage.tsx` real content** (AC1, AC2, AC4)
  - [x] Replace the placeholder. Loading (`RowsSkeleton`, matching `TablesPage.tsx`'s own
    card-grid-loading precedent), error+Retry, empty (`"No orders in the queue"`, exact copy,
    UX-DR15), loaded.
  - [x] Loaded state: group `useKitchenItems()`'s flat list by `table_id` client-side (the backend
    already sorts by `table_id, id`, so a single pass building a `Map<table_id, KitchenItem[]>`
    preserves that order — do not re-sort). One MUI `Card` per table (default elevation 1, no
    override, AC4), header reads the Table's `table_number` (resolved via the now-cook-permitted
    `useTables()`, never the raw `table_id`, matching `TableOrderDetailPage.tsx`'s own established
    "never show the raw id" rule). Each row inside a card: dish name (resolved via `useDishes()`,
    same client-side-resolution convention `TableOrderDetailPage.tsx` already uses for its own Order
    Item list), quantity, note if present, and `OrderItemStatusBadge` (reused verbatim, AC4) — no
    action buttons of any kind, this story is read-only (Scope note).
  - [x] Combine loading/error across all three queries this page depends on
    (`useKitchenItems()`, `useTables()`, `useDishes()`) — the established "a page driven by more
    than one independent query must combine loading/error across all of them" rule (Story 2.5's
    review, most recently reapplied in Story 4.3), now for the first time across *three* queries,
    not two.
  - [x] Subscribe to `order.item_added` (`useRealtime().subscribe`, matching every prior live-update
    subscriber's shape) and invalidate `KITCHEN_ITEMS_QUERY_KEY` on receipt — a plain
    refetch-signal use of the pushed payload, not a direct cache merge (matches every other
    subscriber in this codebase, none of them merge the WebSocket payload directly into the query
    cache).
- [x] **Task 9: Frontend tests** (`KitchenDisplayPage.test.tsx`, new)
  - [x] Empty state exact copy.
  - [x] Loading skeleton, then loaded state, groups items correctly under the right Table's card
    (use at least two Tables with items to prove grouping, not just rendering a flat list).
  - [x] Each row shows dish name (resolved, not a raw id), quantity, note when present, and the
    correct `OrderItemStatusBadge` per item.
  - [x] No action controls render anywhere on the page (a `getByRole("button")` query should find
    nothing card-related — only whatever global chrome buttons `AppShell.tsx` itself renders).
  - [x] Combined error state: any one of the three underlying queries failing shows the
    retry-capable error, not a partially-rendered board.
  - [x] Live update: a stubbed `order.item_added` WebSocket message (mirrors
    `TableOrderDetailPage.test.tsx`'s `FakeWebSocket` pattern, continuing the existing
    per-test-file-copy precedent) triggers a refetch that adds the new item to its Table's card
    without a page reload.
- [x] **Task 10: Full regression pass**
  - [x] `uv run pytest -q` (backend) — zero regressions, including the intentionally-flipped
    broadcast test from Task 4.
  - [x] `pnpm test` (frontend) — zero regressions.
  - [x] `npx tsc -b` — clean.

## Dev Notes

### Architecture compliance

- **AD-1** (DI container is the composition root; every `@inject`-using module gets wired, never
  reached for directly): Task 3's `main.py` append and Task 3's `container.py` provider are both
  this AC's literal requirement (AC5).
- **AD-2** (one WebSocket endpoint, Role-scoped, each event emitted exactly once by the service that
  owns the mutation): `order.item_added` is still emitted exactly once, from `OrderService.add_item`
  — widening its Role list (Task 4) is not a second emission, still AD-2-compliant.
- **First real join in `backend/services/`**: see Scope note point 2. This is a deliberate,
  explicitly-justified exception, not a precedent to casually extend — the next story that's
  tempted to add a join for convenience (rather than because no client-side resolution path exists
  at all) should not point to this one as cover.
- **Role-level-only permissions, unaffected**: `GET /api/kitchen/items` returns the same list to
  every Cook/Admin, no per-Cook filtering (e.g. "only items I've picked up") — that's not even a
  concept yet, Story 5.2 introduces `cook_id` attribution, this story only reads whatever the
  column already holds (always `NULL` today, since nothing sets it yet).

### Current state of the files this story touches (read before editing)

- **`backend/api/router.py`**: currently 7 `include_router()` calls, no `kitchen` router exists.
- **`backend/main.py`**: `container.wire(modules=[...])` currently lists exactly 8 `api.*` modules,
  `"api.kitchen"` is not among them.
- **`backend/container.py`**: `order_service`, `inventory_service` (both `realtime_service`-
  dependent, declared below it per trap 23) are the two most recent providers. `kitchen_service`
  needs no such ordering, since it takes no cross-provider dependency — it can be declared anywhere,
  but for readability, group it near `order_service` (same domain).
- **`backend/services/order_service.py`**: `add_item`'s broadcast (line ~250) is the one line this
  story changes; nothing else in this file is touched (Story 5.2 is what adds pick-up/mark-ready
  service methods here, not this story).
- **`backend/api/tables.py`**: `TablesReadDep` (line ~33) is the one line this story changes.
- **`frontend/src/pages/cook/KitchenDisplayPage.tsx`**: currently a bare one-line `Typography`
  placeholder, already imported and routed in `router.tsx` at `/cook/kitchen-display` (confirmed;
  do not touch `router.tsx`, the route already exists — same "route/placeholder before the story
  that fills it" shape every prior placeholder-replacement story has used).
- **`frontend/src/services/menuService.ts`**: already exports `useDishes()` (Story 2.3), already
  permits Cook (`DishCatalogReadDep` widened in Story 3.2 to admin/cook/waiter) — reused as-is, no
  change needed.
- **`frontend/src/services/tableService.ts`**: already exports `useTables()` (Story 2.4) — reused
  as-is once the backend's `TablesReadDep` widening (Task 5) lands; no frontend change needed to
  this file itself.

### Project Structure Notes

Files touched:
- `backend/data_models/order.py` — **UPDATE**, `KitchenItemResponse` added.
- `backend/data_models/__init__.py` — **UPDATE**, new export.
- `backend/services/kitchen_service.py` — **NEW**.
- `backend/services/order_service.py` — **UPDATE**, one broadcast line.
- `backend/api/kitchen.py` — **NEW**.
- `backend/api/router.py` — **UPDATE**, `kitchen_router` registered.
- `backend/api/tables.py` — **UPDATE**, `TablesReadDep` widened.
- `backend/container.py` — **UPDATE**, `kitchen_service` provider added.
- `backend/main.py` — **UPDATE**, `"api.kitchen"` appended to `wire(modules=[...])`.
- `backend/tests/test_kitchen.py` — **NEW**.
- `backend/tests/test_tables.py` — **UPDATE**, cook-can-read coverage.
- `backend/tests/test_websocket.py` — **UPDATE**, existing broadcast test flipped.
- `frontend/src/types/kitchen.ts` — **NEW**.
- `frontend/src/services/kitchenService.ts` — **NEW**.
- `frontend/src/pages/cook/KitchenDisplayPage.tsx` — **UPDATE**, placeholder replaced.
- `frontend/src/pages/cook/KitchenDisplayPage.test.tsx` — **NEW**.

No new Alembic migration (no schema change — `KitchenItemResponse` is a read shape over existing
columns). No new frontend route (`router.tsx` already has `/cook/kitchen-display`). No change to
`ThemeModeProvider.tsx`/`ReconnectingBanner.tsx` (both already satisfy their ACs).

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 5.1`] — this story's AC source, read
  alongside Story 5.2 (immediately following) to confirm the read-only/no-actions scope boundary.
- [Source: `_bmad-output/planning-artifacts/prds/prd-.../prd.md#FR-9`] — the live-push-within-2-
  seconds requirement this story's `order.item_added` widening satisfies.
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../EXPERIENCE.md`, Component Patterns
  ("Kitchen Display card"), Key Flows Flow 2 (UJ-2)] — "one card per table," the exact grouping
  requirement Task 8 implements; State Patterns table for the exact empty-state copy (UX-DR15).
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../DESIGN.md`, "kitchen-display-card"
  component entry] — MUI `Card`/`Paper` at elevation 1, dark-theme-by-default rendering.
- [Source: `frontend/src/components/shell/ThemeModeProvider.tsx`] — confirms AC4's dark-theme-init
  half is already built; read in full before assuming any work is needed here.
- [Source: `frontend/src/pages/waiter/TableOrderDetailPage.tsx`] — the client-side dish-name/
  table-number resolution convention (never show a raw id), the "combine loading/error across every
  dependent query" pattern, and the `useRealtime().subscribe` + `invalidateQueries` live-update
  shape Task 8 mirrors for a third consumer.
- [Source: `frontend/src/pages/waiter/TablesPage.tsx`, `TablesPage.test.tsx`] — the card-grid
  `RowsSkeleton` loading precedent, and the `FakeWebSocket` test-double pattern (continue the
  existing per-file-copy convention, see `deferred-work.md`'s note that this was already flagged
  for extraction once a fourth consumer appeared — Story 4.2 became that fourth consumer; this
  story would be a fifth, worth raising again in this story's own review whether the threshold has
  now clearly been crossed).
- [Source: `backend/services/order_service.py::add_item`, `backend/tests/test_websocket.py::
  test_adding_an_order_item_broadcasts_order_item_added`] — the exact broadcast call and the exact
  existing test whose Cook-exclusion assertion Task 4 must flip, not merely notice.
- [Source: `_bmad-output/project-context.md`, trap 9, trap 20, trap 23, "Domain rules worth
  restating" (Role-level-only permissions), Testing section] — the row-lock-shape precedent (not
  applicable here, no write in this story, cited only for contrast), the rollback-before-lazy-read
  ordering (not applicable, no write), the container-ordering trap (not triggered by
  `kitchen_service`, cited so the dev agent explicitly confirms it doesn't apply rather than assumes
  so), and the incremental-read-dep-widening precedent (`InventoryReadDep`/`DishCatalogReadDep`/
  `MenuReadDep`'s own histories) Task 5 follows for `TablesReadDep`.

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5

### Debug Log References

- `uv run pytest tests/test_kitchen.py -q` — 9 passed
- `uv run pytest tests/test_tables.py -q` — 22 passed
- `uv run pytest tests/test_websocket.py -q -k "adding_an_order_item"` — 1 passed
- `uv run pytest -q` (full backend suite, first run) — 1 failed (`test_orders.py::
  test_cook_cannot_list_tables`, a second existing instance of the same test name/assertion
  already fixed once in `test_tables.py`, missed on the first pass), 320 passed
- `uv run pytest -q` (full backend suite, after fixing the second instance) — 321 passed, 23
  warnings, no regressions
- `pnpm vitest run src/pages/cook/KitchenDisplayPage.test.tsx` — 5 passed
- `pnpm test` (full frontend suite) — 172 passed
- `npx tsc -b` — clean

### Completion Notes List

- New `kitchen` domain end to end: `KitchenItemResponse` (`data_models/order.py`),
  `KitchenService.list_active_items` (the first genuine join in `backend/services/` — `OrderItem`
  joined to `Order` for `table_id`, explicitly justified in the story's own Scope note as a
  deliberate, named exception to the raw-ids-only precedent every prior story followed), `GET
  /api/kitchen/items` (`api/kitchen.py`, `KitchenReadDep` = cook + admin), wired into
  `container.py`, `api/router.py`, and `main.py`'s `container.wire(modules=[...])` list (AC5,
  `"api.kitchen"` appended, not replacing any existing entry).
- Filter is `OrderItem.status != cancelled` only, no filter on the owning Order's own status —
  correct today since nothing in this codebase can move an Order to `served`/`closed` yet
  (Stories 5.3/5.4 unbuilt). Explicitly flagged in both the story and the service's own docstring
  as a forward-compatibility gap for whichever of those stories ships next.
- Widened two existing Role grants rather than duplicating them: `OrderService.add_item`'s
  `order.item_added` broadcast now targets `[UserRole.waiter, UserRole.cook]` (was waiter-only);
  `TablesReadDep` now permits `admin, waiter, cook` (was admin/waiter-only).
- **Caught and fixed two now-outdated regression tests, not just the one anticipated in the
  story's own Scope note.** `test_websocket.py::test_adding_an_order_item_broadcasts_
  order_item_added`'s "Cook receives nothing" assertion was flipped to "Cook receives the
  identical payload" as planned, and a `warehouse_manager` role-exclusion check was added in its
  place to keep the "prove the negative too" pattern alive for this broadcast. What the story did
  *not* anticipate: **two separate pre-existing tests named `test_cook_cannot_list_tables`**
  (one in `test_tables.py`, one in `test_orders.py`, both asserting 403) both broke once
  `TablesReadDep` was widened. The first full backend suite run caught only the `test_tables.py`
  one having been fixed already; the `test_orders.py` duplicate was missed until the full-suite
  run surfaced it as a failure. Both are now flipped to `test_cook_can_list_tables` (asserting
  200), and a new `test_cook_cannot_create_a_table` was added alongside the `test_tables.py` fix
  to keep write-access-stays-admin-only coverage from silently disappearing.
- Frontend: `KitchenDisplayPage.tsx` combines loading/error across three independent queries
  (`useKitchenItems`, `useTables`, `useDishes`) for the first time in this codebase (prior
  multi-query pages combined two). Groups the flat item list into a `Map<table_id, KitchenItem[]>`
  client-side, preserving the backend's own `table_id, id` sort order rather than re-sorting.
  Dish name and table number are both resolved client-side from already-fetched reference data
  (never a raw id shown), matching `TableOrderDetailPage.tsx`'s established convention.
  Subscribes to the widened `order.item_added` event and invalidates `KITCHEN_ITEMS_QUERY_KEY` on
  receipt — a plain refetch signal, matching every other live subscriber in this codebase.
- Dark-theme initialization (UX-DR7) and the "Reconnecting..." banner (UX-DR16) required zero new
  code — both were already built ahead of this story (`ThemeModeProvider.tsx`, `ReconnectingBanner`/
  Story 1.5) and are covered by this story only via direct-reading verification, not new tests.
- MUI `Stack`'s `alignItems`/`justifyContent` props hit a TypeScript overload resolution error in
  this project's MUI version when used as direct props; worked around by moving them into the
  `sx` prop instead (`sx={{ alignItems: ..., justifyContent: ... }}`), which resolves cleanly.
  Purely a typing quirk, no behavioral difference.

### File List

- `backend/data_models/order.py`
- `backend/data_models/__init__.py`
- `backend/services/kitchen_service.py`
- `backend/services/order_service.py`
- `backend/api/kitchen.py`
- `backend/api/router.py`
- `backend/api/tables.py`
- `backend/container.py`
- `backend/main.py`
- `backend/tests/test_kitchen.py`
- `backend/tests/test_tables.py`
- `backend/tests/test_orders.py`
- `backend/tests/test_websocket.py`
- `frontend/src/types/kitchen.ts`
- `frontend/src/services/kitchenService.ts`
- `frontend/src/pages/cook/KitchenDisplayPage.tsx`
- `frontend/src/pages/cook/KitchenDisplayPage.test.tsx`

## Review Findings

Reviewed by three parallel agents (Blind Hunter, Edge Case Hunter, Acceptance Auditor) against this
story's 5 ACs and `_bmad-output/project-context.md`. All three independently re-ran the backend/
frontend suites and `tsc -b` against the actual working tree rather than trusting the Dev Agent
Record's numbers, and all confirmed them exactly (321 backend, 172 frontend, clean typecheck).

**Fixed during this review:**

- **Stale `tables`/`dishes` reference data with no self-correcting refetch, and a raw-id fallback
  that's indistinguishable from a real table number** (Edge Case Hunter, echoed by Blind Hunter) —
  `KitchenDisplayPage.tsx` only invalidated `KITCHEN_ITEMS_QUERY_KEY` on the live `order.item_added`
  event, never `TABLES_QUERY_KEY`/`DISHES_QUERY_KEY`. A Table or Dish created after this
  long-lived, always-foregrounded page's initial load would never resolve correctly while the page
  stayed mounted, and the `table_id` fallback (`?? tableId`) rendered the raw internal id with no
  visual distinction from a genuine `table_number` — violating this codebase's own "never show a
  raw id" convention. Fixed: the `order.item_added` handler now also invalidates
  `TABLES_QUERY_KEY`/`DISHES_QUERY_KEY` (harmless over-invalidation the rest of the time, matching
  `useAddOrderItem`'s existing precedent), and the fallbacks now render `"?"` / `"Unknown dish"`
  instead of echoing a raw id. New regression test:
  `resolves a table created after the initial load once a live event refetches the tables list`.
- **Container/router placement drift from the story's own stated intent** (Blind Hunter) —
  `kitchen_service` was declared away from `order_service` despite the Dev Notes explicitly saying
  to group them; `"api.kitchen"`/`kitchen_router` were inserted mid-list rather than literally
  appended at the end, which AC5's own wording ("appended... not replacing") implies literally even
  though list order has no functional effect on `container.wire()`/`include_router()`. Both fixed:
  `kitchen_service` moved next to `order_service` in `container.py`; `"api.kitchen"` and
  `kitchen_router` both moved to the physical end of their respective lists.
- **Stray blank line in `KitchenDisplayPage.tsx`'s row JSX** (Blind Hunter) — cosmetic, removed.

**Verified as non-issues:**

- **The widened `order.item_added` broadcast** (Blind Hunter, Acceptance Auditor) — confirmed
  end-to-end as genuinely safe, not just assumed: the payload is identical for every recipient
  regardless of Role, and this codebase's Role-level-only permission model means there's no
  per-order Cook scoping to have been skipped. The new test correctly flips the Cook assertion to
  "receives it" *and* adds a fresh `warehouse_manager` negative case, a stronger test than what it
  replaced.
- **Both `test_cook_cannot_list_tables` instances** (all three agents independently) — confirmed
  genuinely found and fixed (`test_tables.py` and `test_orders.py`), not just claimed; a repo-wide
  grep for the old name/assertion turned up zero remaining instances, and the one other "Cook
  receives nothing"-style comment in `test_websocket.py` belongs to the unrelated, correctly
  untouched `table.status_changed` test.
- **AC3/AC4's "already implemented, zero new code" claims** (Acceptance Auditor) — independently
  re-verified by reading `ThemeModeProvider.tsx`/`ReconnectingBanner.tsx`/`AppShell.tsx` directly;
  both files are genuinely untouched by this story's diff.
- **AC5's `container.wire(modules=[...])` requirement and trap-23 non-applicability** (Acceptance
  Auditor) — confirmed `"api.kitchen"` was added without removing or reordering any pre-existing
  entry, and confirmed `KitchenService.__init__` takes only `logger`, so trap 23 genuinely does not
  apply to its container placement.
- **The backend join's correctness** (all three agents) — `test_items_across_two_tables_each_
  carry_their_own_table_id` specifically guards against a hardcoded/first-row `table_id` bug, and
  the join cannot silently drop or duplicate rows given `OrderItem.order_id`/`Order.table_id` are
  both non-nullable FKs with no delete endpoint for either `Order` or `RestaurantTable`.

**Deferred (non-blocking, see `deferred-work.md`):** `list_active_items` has no pagination/bound
(matches this codebase's other accepted-at-current-scale gaps); `KitchenItemResponse` carries
`price_at_add`/`order_id` the frontend never renders (a reuse-over-narrowing tradeoff, not a
security issue given Role-level-only permissions); no automated tripwire forces revisiting the
already-well-documented `Order.status` filter gap once Stories 5.3/5.4 ship.

## Change Log

| Date | Change |
|---|---|
| 2026-08-16 | Implemented Story 5.1: View Incoming Orders in Real Time (Kitchen Display). New `kitchen` domain end to end (backend join, `GET /api/kitchen/items`, frontend board). Widened `order.item_added`'s broadcast and `TablesReadDep` to include Cook. Fixed two now-outdated regression tests asserting Cook could not list tables. 10 new backend tests (321 total), 5 new frontend tests (172 total). |
| 2026-08-16 | Code review patch pass: fixed stale `tables`/`dishes` reference data on the Kitchen Display (now invalidated on every live `order.item_added` event, not just the kitchen items list) and a raw-id fallback that was indistinguishable from a real table number; moved `kitchen_service`/`"api.kitchen"`/`kitchen_router` to match the story's own stated placement intent and AC5's literal "appended" wording. 1 new regression test added (173 frontend total). |

