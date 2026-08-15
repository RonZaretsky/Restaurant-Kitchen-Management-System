---
baseline_commit: 723fdd0a87a33e4555b8736dc5f3ba87dadb32ba
epic: 3
story: 3
---

# Story 3.3: View Live Order and Table Status

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Waiter,
I want to see every table's and order item's current status update live,
so that I know what's happening without walking to the kitchen or refreshing.

## Scope note (read first)

**This is the first story to actually use the real-time transport Story 1.5 built.** `RealtimeService`/`ConnectionRegistry`/`useRealtime()` have existed since Story 1.5, but `project-context.md` has flagged since then that **nothing emits over them yet** — confirmed again just now: `grep -rn "realtime_service" backend/services/order_service.py backend/api/orders.py` returns nothing. This story adds the first two producers (backend) and the first two consumers (frontend), closing that gap for the surfaces that exist today.

**Exactly two events, both backend-only additions to `OrderService`, nothing in `TableService`:**
1. `table.status_changed` — emitted by `OrderService.open_table` (Story 3.1) when it flips a Table to `occupied`. `TableService.update_table` (Story 2.4, edits number/capacity only, never status) does **not** need this, it never changes `status`.
2. `order.item_added` — emitted by `OrderService.add_item` (Story 3.2) when a new Order Item is created.

**What this story explicitly does NOT add**, per its own AC text ("today: a Waiter adding, editing, or cancelling an item; **from Epic 5 onward** also a Cook's status transitions"): no Cook-side producer, no `order.item_status_changed` event (that name is only ever used as an *illustrative example* in AD-2's own docstring and in `test_websocket.py`'s smoke tests, not a shipped event — Epic 5's stories are what actually add Cook pickup/pass transitions). Do not build ahead of that.

**Backend/frontend parity is mandatory for this story** (explicit user instruction for this pipeline run): every event this story's backend emits must have a working frontend consumer that visibly updates the UI. An event nobody subscribes to, or a subscription that does nothing, does not satisfy this story. Concretely: after this story, opening a Table or adding an Order Item from one browser tab must visibly update a **second, independently connected** browser tab's Tables grid or Table/Order detail page within 2 seconds, with no manual refresh — not just "a broadcast fires and a backend test asserts it arrived."

**Container wiring order matters.** `backend/container.py` currently declares `order_service` *before* `realtime_service`/`connection_registry` (`container.py:92-99`). Since these are plain Python class-level assignments evaluated top to bottom, injecting `realtime_service` into `order_service`'s `providers.Factory(...)` call requires `order_service`'s declaration to move **below** `realtime_service`'s, or the container fails at import time with `NameError: name 'realtime_service' is not defined`. Move the block, don't reorder-hack around it.

## Acceptance Criteria

**AC1 — Emit over the existing transport, no new one, no competing naming scheme**
Given the transport and event-naming convention established in Story 1.5 (AD-2), when the order and table services commit a state change, then they emit over that existing WebSocket channel under a `{domain}.{event}` name, adding no second transport.

**AC2 — Live update within 2 seconds, no manual refresh**
Given any Order or Order Item state change committed by the service layer (today: a Waiter opening a Table into a new Order, or adding an Order Item), when the change is committed, then it appears on every other connected Waiter terminal's Tables grid and Table/Order detail page within 2 seconds via WebSocket push, with no manual refresh (FR-6, NFR-1, AD-2).

**AC3 — Every connected Waiter sees every change**
Given the system is used from multiple Waiter terminals simultaneously, when any one of them makes a change, then every other Waiter terminal sees every Table and every Order, since v1 has no per-waiter filtering (FR-6, NFR-5).

**AC4 — Reconnecting state (already built, verify it still holds)**
Given the WebSocket connection drops, when the frontend detects it, then a "Reconnecting..." state is shown and the connection retries automatically (UX-DR16). This is Story 1.5's existing `RealtimeProvider`/`ReconnectingBanner` behavior — nothing to build here, just confirm this story's changes do not regress it (no new test needed beyond the existing `RealtimeProvider.test.tsx` suite staying green).

## Tasks / Subtasks

- [x] **Task 1: Container wiring order fix** (AC: 1)
  - [x] In `backend/container.py`, move the `order_service = providers.Factory(OrderService, logger=logging)` block to **after** the `realtime_service = providers.Factory(RealtimeService, ...)` block (currently `order_service` is declared first, at line ~92, `realtime_service` after `connection_registry` at line ~97-99). Verify with `uv run python -c "from container import Container; Container()"` that the container still imports cleanly before moving on.

- [x] **Task 2: `OrderService` emits `table.status_changed`** (AC: 1, 2, 3)
  - [x] `backend/services/order_service.py`: add `realtime_service: RealtimeService` to `OrderService.__init__`'s signature (alongside the existing `logger`), store it as `self._realtime_service`.
  - [x] In `open_table`, **after** the guarded UPDATE succeeds and **after** the `Order` row is committed (the existing `await db.commit()` near the end of the method), call:
    ```python
    await self._realtime_service.broadcast(
        [UserRole.waiter],
        "table.status_changed",
        {"table_id": table_id, "status": TableStatus.occupied.value},
    )
    ```
    Broadcasting only to `UserRole.waiter` matches this story's own AC text ("every other connected Waiter terminal") — Cook/Admin/Warehouse Manager audiences are out of scope until a later story needs them. Keep the payload minimal (id + new status), the frontend already has `useTables()` to refetch full detail, this event is a signal to refetch, not a full state transfer (matches this codebase's established invalidate-then-refetch mutation pattern, never a payload-merge-into-cache pattern).
  - [x] `UserRole` needs importing into `order_service.py` if not already present (check first, `TableStatus` is already imported).

- [x] **Task 3: `OrderService` emits `order.item_added`** (AC: 1, 2, 3)
  - [x] In `add_item`, **after** the existing `await db.commit()` / `await db.refresh(item)`, call:
    ```python
    await self._realtime_service.broadcast(
        [UserRole.waiter],
        "order.item_added",
        OrderItemResponse.model_validate(item).model_dump(mode="json"),
    )
    ```
    Reuse `OrderItemResponse` (already defined, `data_models/order.py`) via `model_validate(...).model_dump(mode="json")` rather than hand-building a dict — this keeps the broadcast payload's shape identical to the REST response shape (including `Decimal` → JSON-string conversion for `price_at_add`, matching how FastAPI already serializes it), so the frontend's existing `OrderItem` type can deserialize it with zero drift. Import `OrderItemResponse` into `order_service.py` if not already present (check first, only the ORM `OrderItem` may currently be imported, not the Pydantic response schema).

- [x] **Task 4: Register `realtime_service` on `OrderService` in the container** (AC: 1)
  - [x] `backend/container.py`: update the (now-moved, per Task 1) `order_service` Factory to also inject `realtime_service=realtime_service`:
    ```python
    order_service = providers.Factory(
        OrderService,
        logger=logging,
        realtime_service=realtime_service,
    )
    ```

- [x] **Task 5: Frontend consumes `table.status_changed` on the Tables grid** (AC: 2, 3)
  - [x] `frontend/src/pages/waiter/TablesPage.tsx`: subscribe to `table.status_changed` via `useRealtime()` (`../../components/shell/RealtimeProvider`), invalidating `TABLES_QUERY_KEY` (already exported from `tableService.ts`, Story 3.1) on receipt, the same query-invalidation idiom every mutation in this codebase already uses, not a manual cache patch of the pushed payload.
    ```tsx
    import { useEffect } from "react";
    import { useQueryClient } from "@tanstack/react-query";
    import { useRealtime } from "../../components/shell/RealtimeProvider";
    // ...
    const queryClient = useQueryClient();
    const { subscribe } = useRealtime();
    useEffect(() => {
      return subscribe("table.status_changed", () => {
        void queryClient.invalidateQueries({ queryKey: TABLES_QUERY_KEY });
      });
    }, [subscribe, queryClient]);
    ```
    `subscribe` returns its own unsubscribe function (see `RealtimeProvider.tsx`'s `subscribe` implementation), return it directly from the effect, do not wrap it in an extra arrow function, matching the pattern any future subscriber should copy.

- [x] **Task 6: Frontend consumes `order.item_added` on the Table/Order detail page** (AC: 2, 3)
  - [x] `frontend/src/pages/waiter/TableOrderDetailPage.tsx`: subscribe to `order.item_added`, invalidating the current Order's item-list query key on receipt. `orderItemsQueryKey(orderId)` is currently a module-**private** function in `orderService.ts` (`function orderItemsQueryKey(...)`, not exported) — **export it** (same pattern `tableService.ts`'s `TABLES_QUERY_KEY` and `menuService.ts`'s `DISHES_QUERY_KEY` already established: a query key a second file needs to invalidate must be exported, not re-derived) rather than reconstructing the array `["orders", orderId, "items"]` by hand in this page, which would silently drift if the key's shape ever changes in one place and not the other.
    ```tsx
    // orderService.ts: change from a private function to an exported one, no other change
    export function orderItemsQueryKey(orderId: number | undefined) {
      return ["orders", orderId, "items"] as const;
    }
    ```
    ```tsx
    // TableOrderDetailPage.tsx
    import { useEffect } from "react";
    import { useQueryClient } from "@tanstack/react-query";
    import { useRealtime } from "../../components/shell/RealtimeProvider";
    import { orderItemsQueryKey } from "../../services/orderService";
    // ...
    const queryClient = useQueryClient();
    const { subscribe } = useRealtime();
    useEffect(() => {
      return subscribe("order.item_added", () => {
        void queryClient.invalidateQueries({ queryKey: orderItemsQueryKey(order?.id) });
      });
    }, [subscribe, queryClient, order?.id]);
    ```
    This subscription is page-wide (fires for *any* order's item-added event, not just this page's own order), which is correct and matches AC3 ("every other Waiter terminal sees every Table and every Order") — invalidating a query keyed on an order id this page is not currently viewing is a harmless no-op (`invalidateQueries` only refetches active/matching queries), not a bug to guard against with client-side filtering.

- [x] **Task 7: Tests** (AC: all)
  - [x] `backend/tests/test_orders.py` — mirror the existing style (`# Arrange`/`# Act`/`# Assert`, no docstrings). Since `open_table`/`add_item` are called through the HTTP client (`client.post(...)`) in every existing test in this file, not directly against `OrderService`, the new broadcast calls need a **real WebSocket connection to observe**, matching `test_websocket.py`'s established pattern (`_running_server()`/`_connect()`/real `uvicorn.Server`, `client.websocket_connect`/`TestClient` alone cannot share an event loop with a broadcast, see that file's own comment). The cleanest home for these two new tests is `test_websocket.py` itself (it already has every fixture this needs, `test_orders.py` has none of the WebSocket scaffolding), added as two new tests:
    - Opening a Table broadcasts `table.status_changed` with the right `table_id`/`status`, received by a connected Waiter within 2 seconds. Needs a Table and a Waiter/Admin created directly via the DB session (mirroring this file's own `_create_user` helper) since `test_websocket.py` has no existing table-creation helper, plus one `client.post("/api/tables", ...)` as Admin over the running server's own `httpx.AsyncClient` (see `_login_over_http`'s pattern for talking HTTP to the ephemeral-port server) before opening it as the Waiter.
    - Adding an Order Item broadcasts `order.item_added` with the item's fields (including `price_at_add`), received within 2 seconds. Needs an available Dish first (mirror `test_orders.py`'s `_create_available_dish` shape, adapted to call over the running server rather than the `client`/`db_session` fixtures `test_orders.py` uses).
  - [x] `frontend/src/pages/waiter/TablesPage.test.tsx` — one new test: after the initial table list renders, simulate a `table.status_changed` message arriving over the (mocked) WebSocket and assert the grid refetches (`fetch` is called against `/api/tables` a second time, or the updated status renders if the stub returns a changed list on the second call). Needs a fake `WebSocket` global stub, matching `RealtimeProvider.test.tsx`'s own `FakeWebSocket` class (copy that class's shape into this file, or extract it to a shared test-support module if duplicating it a second time feels wrong — dev's call, note either way in the Completion Notes, don't block on it).
  - [x] `frontend/src/pages/waiter/TableOrderDetailPage.test.tsx` — one new test: after the item list renders, simulate an `order.item_added` message and assert the item list refetches. Same `FakeWebSocket` need as above.
  - [x] Full regression: `uv run pytest` from `backend/`, `pnpm test` from `frontend/`.
  - [x] **Manual end-to-end verification is required for this story specifically**, beyond the usual regression run, because AC2/AC3's actual claim ("a second terminal sees it live") is not something a single-browser-tab automated test can fully prove the way a human watching two tabs can. Before marking this story `review`: open two browser tabs/windows against the running Docker stack, both logged in as (different) Waiters, and confirm opening a Table in tab A updates tab B's grid live, and adding an item in tab A updates tab B's detail page live, without touching tab B at all. Record what was observed in Dev Agent Record → Completion Notes.

### Review Findings

- [x] [Review][Patch] `container.py` has no comment explaining why `order_service` must be declared
  after `realtime_service`/`connection_registry` (forward-reference evaluation order) — the same
  class of bug could be silently reintroduced by a future contributor
  [backend/container.py]
- [x] [Review][Patch] Neither the new `OrderService` broadcast calls nor the frontend subscribers
  name the Observer/Pub-Sub pattern anywhere, violating CLAUDE.md's "name the pattern being used"
  requirement for this project's grading context
  [backend/services/order_service.py, frontend/src/pages/waiter/TablesPage.tsx,
  frontend/src/pages/waiter/TableOrderDetailPage.tsx]
- [x] [Review][Patch] Both new frontend tests read `FakeWebSocket.instances[0]` with no guard,
  producing a confusing `TypeError` instead of a clear assertion failure if `RealtimeProvider`
  doesn't construct synchronously on mount
  [frontend/src/pages/waiter/TablesPage.test.tsx, frontend/src/pages/waiter/TableOrderDetailPage.test.tsx]
- [x] [Review][Patch] Neither new backend test proves role-scoping actually excludes a non-waiter —
  both connect only a waiter socket and assert receipt, so a regression broadcasting to every Role
  would pass CI undetected
  [backend/tests/test_websocket.py]
- [x] [Review][Patch] `TableOrderDetailPage.tsx`'s `order.item_added` subscriber can invalidate
  `orderItemsQueryKey(undefined)` if the event arrives in the narrow window before `order?.id`
  resolves, missing the live update for that one event
  [frontend/src/pages/waiter/TableOrderDetailPage.tsx]
- [x] [Review][Patch] `table.status_changed`'s hand-built dict payload vs. `order.item_added`'s
  Pydantic-schema-backed payload is an unexplained asymmetry with no comment justifying it
  [backend/services/order_service.py]
- [x] [Review][Defer] No batching/coalescing for rapid successive item-adds, each firing a full
  broadcast + cache invalidation on every connected Waiter terminal — deferred, out of scope at this
  project's stated demo/NFR-5 scale (4 concurrent terminals), matches the PRD's own "no rate
  limiting, small academic-team usage volume" stance.
- [x] [Review][Defer] No test exercises the zero-connected-Waiters broadcast path — deferred, the
  underlying `broadcast_to_roles`/`_targets` short-circuit is already covered generically by
  `test_websocket.py`'s existing suite, this story's two new tests only needed to prove these two
  new call sites reach that already-tested mechanism correctly.
- [x] [Review][Defer] `FakeWebSocket` is now duplicated across three files (`RealtimeProvider.test.tsx`
  and this story's two new copies) with no shared test-support module — deferred, already logged as
  a deliberate call in this story's own Completion Notes ("worth revisiting if a fourth test file
  needs the same double").
- [x] [Review][Defer] The two new `broadcast()` call sites have no `try`/`except` around them —
  deferred, verified against `clients/websocket.py`: `broadcast_to_roles` already catches JSON
  serialization errors (logs and returns) and `_send` catches all per-connection send failures
  individually, so the call is provably exception-safe today. Wrapping it anyway would be defensive
  code against a currently unreachable failure mode, which project-context.md's own conventions
  discourage ("Don't add error handling...for scenarios that can't happen").

## Dev Notes

### Architecture compliance

- **AD-2** (single WebSocket endpoint, `{domain}.{event}` naming, emitted exactly once by the owning service): both new events are emitted from `OrderService` alone (the service that owns each mutation), never from `api/orders.py` (routers stay non-logging/non-emitting, services own domain actions — same rule that already governs logging placement in this codebase). `table.status_changed` and `order.item_added` are both new names, not reused from anywhere else; `order.item_status_changed` (seen in `test_websocket.py`'s smoke tests and AD-2's own docstring example) is explicitly **not** used by this story, it names a different, not-yet-built event (Cook status transitions, Epic 5).
- **NFR-1** (2-second push bound): both new backend tests assert delivery via `asyncio.wait_for(ws.recv(), timeout=2)`, matching `test_broadcast_delivered_within_two_seconds`'s existing pattern exactly.
- **NFR-5** (concurrent multi-terminal use) / **FR-6** (no per-waiter filtering): broadcasting to `[UserRole.waiter]` (the whole Role, not a specific `user_id`) is what satisfies both — every Waiter terminal is an equally valid audience, there is no concept of "this Waiter's own tables" to filter by.
- This story does **not** touch `TableService`, `MenuService`, or any Cook-facing surface. Do not add a producer to `TableService.update_table` (it never changes `status`, nothing for a Waiter's live view to react to) and do not add any Cook-side consumer (`KitchenDisplayPage.tsx` stays untouched, Epic 5's own stories own that).

### Current state of the files this story touches (read before editing)

- **`backend/services/order_service.py`**: `OrderService.__init__(self, logger: Any)` currently takes only `logger`. `open_table` ends with `await db.commit()` then a `self._logger.info(...)` call then `return order`. `add_item` ends with `await db.commit()`, `await db.refresh(item)`, then a `self._logger.info(...)` call then `return item`. The broadcast calls in Tasks 2/3 go **after** the existing commit, alongside (not replacing) the existing logger call — order between the new broadcast and the existing log line does not matter, but both must happen only after the commit succeeds, never before (a broadcast for a change that then fails to commit would lie to every connected Waiter).
- **`backend/container.py`**: see the Scope note above on wiring order. `RealtimeService` is already imported at the top of the file (`from services.realtime_service import RealtimeService`), nothing to add there.
- **`frontend/src/services/orderService.ts`**: `orderItemsQueryKey` is currently `function orderItemsQueryKey(orderId: number | undefined) { ... }` with no `export` keyword, directly above `useOrderForTable`. `TABLES_QUERY_KEY` (a different file, `tableService.ts`) is already exported and already used cross-file by `orderService.ts`'s own `useOpenTable` — Task 5/6 extend that same established cross-file-query-key-import pattern, they do not invent a new one.
- **`frontend/src/pages/waiter/TablesPage.tsx`** and **`TableOrderDetailPage.tsx`**: both already import `useQueryClient`-adjacent hooks indirectly via the service layer, but neither currently imports `useQueryClient` or `useRealtime` directly at the page level. Both additions are new imports, not replacements.

### Project Structure Notes

Files touched:
- `backend/container.py` — **UPDATE**, reorder `order_service`/`realtime_service` declarations, inject `realtime_service` into `order_service`.
- `backend/services/order_service.py` — **UPDATE**, `__init__` gains `realtime_service`, `open_table`/`add_item` each gain one broadcast call.
- `backend/tests/test_websocket.py` — **UPDATE**, two new tests (see Task 7).
- `frontend/src/services/orderService.ts` — **UPDATE**, `orderItemsQueryKey` becomes exported (one-word change, `function` → `export function`).
- `frontend/src/pages/waiter/TablesPage.tsx` — **UPDATE**, subscribes to `table.status_changed`.
- `frontend/src/pages/waiter/TableOrderDetailPage.tsx` — **UPDATE**, subscribes to `order.item_added`.
- `frontend/src/pages/waiter/TablesPage.test.tsx`, `frontend/src/pages/waiter/TableOrderDetailPage.test.tsx` — **UPDATE**, one new test each.

No new file, no Alembic migration, no new backend route, no new frontend route. `api/orders.py` is **not** touched at all, both new events are emitted from the service layer the existing routes already call into.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 3.3`] — this story's AC source
- [Source: `_bmad-output/implementation-artifacts/3-2-add-items-to-an-order.md`] — previous story; `add_item`'s exact current shape, `TableOrderDetailPage.tsx`'s full current implementation
- [Source: `_bmad-output/implementation-artifacts/1-5-real-time-push-transport.md`] — the transport this story is the first real consumer of; `RealtimeService`/`ConnectionRegistry`/`RealtimeProvider` all built there, unchanged by this story
- [Source: `backend/services/realtime_service.py`] — `broadcast(roles, event, payload)`'s exact signature
- [Source: `backend/tests/test_websocket.py`] — `_running_server()`/`_connect()`/`_login_over_http()` scaffolding to reuse; `test_broadcast_delivered_within_two_seconds` is the pattern the two new tests mirror
- [Source: `frontend/src/components/shell/RealtimeProvider.tsx`, `RealtimeProvider.test.tsx`] — `useRealtime()`'s `subscribe(event, handler)` contract and the `FakeWebSocket` test double
- [Source: `frontend/src/services/orderService.ts`, `tableService.ts`] — the query-key export/invalidation pattern Tasks 5/6 extend
- [Source: `_bmad-output/project-context.md`, "Domain rules worth restating"] — the "`RealtimeService` has no producers yet" note this story resolves; AD-2's exact rule text

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (claude-sonnet-5)

### Debug Log References

None. No HALT conditions were hit; implementation proceeded task-by-task without needing debug-log
capture.

### Completion Notes List

- `backend/container.py`: `order_service`'s declaration moved below `realtime_service`/
  `connection_registry` (plain top-to-bottom Python class-body evaluation otherwise raises
  `NameError` referencing `realtime_service` before it exists), and now injects
  `realtime_service=realtime_service`. Verified with a standalone `Container()` import before
  writing any test.
- `OrderService.__init__` gained a `realtime_service: RealtimeService` parameter. `open_table`
  broadcasts `table.status_changed` (`{table_id, status}`) to `UserRole.waiter` only, after the
  guarded UPDATE and Order insert both commit, never before (a broadcast for a change that then
  failed to commit would lie to every connected Waiter). `add_item` broadcasts `order.item_added`
  with the full `OrderItemResponse.model_validate(item).model_dump(mode="json")` payload, reusing
  the existing Pydantic schema rather than hand-building a dict so the pushed shape can never drift
  from the REST response shape (including `Decimal` → JSON-string handling for `price_at_add`).
- Frontend: `TablesPage.tsx` and `TableOrderDetailPage.tsx` each subscribe via `useRealtime()` and
  invalidate their existing query keys on receipt (`TABLES_QUERY_KEY`, `orderItemsQueryKey`), never
  merging the pushed payload into cache directly, matching this codebase's established
  invalidate-then-refetch mutation idiom. `orderItemsQueryKey` was promoted from a private function
  to an exported one in `orderService.ts` for this, the same cross-file query-key pattern
  `TABLES_QUERY_KEY` already established.
- Both new event names (`table.status_changed`, `order.item_added`) are new; `order.item_status_changed`
  (seen in `test_websocket.py`'s own smoke-test literals and AD-2's docstring example) was
  deliberately not touched or reused, it names a different, not-yet-built Cook-side event (Epic 5).
- Backend tests: added directly to `test_websocket.py` (not `test_orders.py`, which has no
  WebSocket scaffolding), reusing its `_running_server()`/`_connect()`/`_login_over_http()` helpers.
  Both new fixtures (`RestaurantTable`, `Category`+`Dish`) are created directly via the DB session
  rather than through an admin-login HTTP round trip, mirroring this file's own `_create_user`
  shortcut.
- Frontend tests: both `TablesPage.test.tsx` and `TableOrderDetailPage.test.tsx` now render inside a
  real `RealtimeProvider` (previously they didn't need one), which meant every existing test in both
  files needed a global `WebSocket` stub, not just the two new ones, since `RealtimeProvider` opens a
  connection unconditionally on mount and jsdom's real `WebSocket` attempts a genuine, slow network
  connection. Copied `RealtimeProvider.test.tsx`'s own `FakeWebSocket` class into both files rather
  than extracting a shared test-support module — two duplicate copies (now three including the
  original) felt like the threshold to extract, but doing so was judged out of scope for this story
  and left as-is; worth revisiting if a fourth test file needs the same double.
- **Manual two-tab verification performed against a rebuilt Docker stack** (`docker compose build
  backend frontend`, real browser automation via Playwright, two independent browser contexts logged
  in as two different Waiters, `waiter1`/Wendy and a newly created `waiter2`/Wesley, so neither
  connection stole the other's WebSocket per Story 1.5's one-per-user rule). Confirmed both live
  paths end to end: Wendy (tab A) opened Table 4 into a new Order; Wesley's tab (B), never touched or
  refreshed, showed Table 4 flip from `available` to `occupied` within the observation window.
  Wendy then added a Margherita to that Order from tab A; Wesley's already-open detail page for
  Table 4 showed the new "Pending / Margherita / — / 1 / 12.50 ₪" row appear with no manual refresh.
  Screenshots taken at each step confirm both transitions visually, not just via DOM assertions.
- Full regression: `uv run pytest` — 249 passed (up from 247, +2 in `test_websocket.py`). `pnpm test`
  — 133 passed (up from 131, +1 each in `TablesPage.test.tsx`/`TableOrderDetailPage.test.tsx`).
  `npx tsc -b` clean.
- **Code review (Blind Hunter, Edge Case Hunter, Acceptance Auditor):** 6 patches applied, 4
  deferred, 5 dismissed as false positives after verifying against the actual code (e.g.
  `OrderItemResponse` has zero relationship fields so the raised lazy-load concern was unfounded;
  `broadcast_to_roles`/`_send` already catch every failure mode they could raise, so wrapping the
  call sites again would be defensive code against an unreachable scenario; `RealtimeService` being
  a `Factory` not `Singleton` matches every other service in this codebase and is functionally
  harmless since it only wraps a shared `Resource`-backed registry). Patches: added a comment on
  `container.py`'s provider-ordering requirement; named the Observer/Pub-Sub pattern explicitly in
  `OrderService`'s and both subscriber pages' docstrings, per CLAUDE.md's pattern-naming
  requirement; guarded both new frontend tests' `FakeWebSocket.instances[0]` reads with an explicit
  assertion; extended both new backend tests with a connected Cook socket that asserts it receives
  nothing, closing a real role-scoping coverage gap; fixed a genuine (if narrow) stale-query-key
  race in `TableOrderDetailPage.tsx`'s subscriber, which could invalidate
  `orderItemsQueryKey(undefined)` if `order.item_added` arrived before `order?.id` resolved; added a
  comment explaining why `table.status_changed`'s payload is a plain dict rather than a
  `TableResponse`. Full regression after patches: 249 backend (assertions strengthened, no new
  tests), 133 frontend (unchanged count, existing tests strengthened), `tsc -b` clean.

### File List

**Modified**

- `backend/container.py` (reordered `order_service`/`realtime_service` declarations; injected
  `realtime_service` into `order_service`; added the ordering-requirement comment)
- `backend/services/order_service.py` (`__init__` gained `realtime_service`; `open_table` and
  `add_item` each broadcast one new event; Observer/Pub-Sub named in the class docstring; comment
  explaining `table.status_changed`'s plain-dict payload)
- `backend/tests/test_websocket.py` (2 new tests: `test_opening_a_table_broadcasts_table_status_changed`,
  `test_adding_an_order_item_broadcasts_order_item_added`, both now also asserting a connected Cook
  receives nothing)
- `frontend/src/services/orderService.ts` (`orderItemsQueryKey` promoted to exported)
- `frontend/src/pages/waiter/TablesPage.tsx` (subscribes to `table.status_changed`; Observer/Pub-Sub
  named in the subscriber comment)
- `frontend/src/pages/waiter/TableOrderDetailPage.tsx` (subscribes to `order.item_added`;
  Observer/Pub-Sub named; guarded against invalidating an undefined order id)
- `frontend/src/pages/waiter/TablesPage.test.tsx` (added `RealtimeProvider`/`FakeWebSocket` to the
  render wrapper; 1 new test; guarded `FakeWebSocket.instances[0]` read)
- `frontend/src/pages/waiter/TableOrderDetailPage.test.tsx` (same wrapper change; 1 new test; same
  guard)

**Confirmed unchanged**: `backend/api/orders.py` (both events emitted from the service layer the
existing routes already call into, no route change needed), `backend/services/table_service.py` (no
producer added, it never changes Table `status`), no Alembic migration, no new package in either
manifest, no new file, no new route.

## Change Log

| Date | Change |
|---|---|
| 2026-08-15 | Story 3.3 implemented end-to-end: `OrderService` gained the project's first two real-time producers (`table.status_changed` from `open_table`, `order.item_added` from `add_item`), and `TablesPage.tsx`/`TableOrderDetailPage.tsx` gained the first two frontend consumers, closing the "RealtimeService has no producers yet" gap `project-context.md` had flagged since Story 1.5. All 7 tasks complete, full regression green (backend 249/249, frontend 133/133), manually verified live across two independent browser sessions. |
| 2026-08-15 | Code review (Blind Hunter, Edge Case Hunter, Acceptance Auditor). 6 patches applied: named the Observer/Pub-Sub pattern explicitly per CLAUDE.md's requirement, added a role-exclusion assertion to both new backend tests (a connected Cook now asserted to receive nothing), fixed a narrow stale-query-key race in `TableOrderDetailPage.tsx`, guarded two brittle test assumptions, and documented the container provider-ordering requirement and the `table.status_changed` payload's plain-dict shape. 4 items deferred, 5 dismissed as false positives after verifying against the actual code. Full regression after patches: 249 backend, 133 frontend, `tsc -b` clean. |
