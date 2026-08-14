---
baseline_commit: 7c830b893485f72613bd5270117d11a35ba49936
epic: 3
story: 1
---

# Story 3.1: Open a Table and Start an Order

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Waiter,
I want to mark an available table as occupied and start a new order,
so that I can begin taking a table's order.

**Scope note.** This is Epic 3's first story, opening the `orders` domain. Backend **and**
frontend: the frontend piece is narrow, `pages/waiter/TablesPage.tsx` (currently a Story 1.0/1.4
placeholder) becomes the real Tables grid. `pages/waiter/TableOrderDetailPage.tsx` (the
`/waiter/tables/:tableId` route, also currently a placeholder) is explicitly **out of scope** —
its real content (add-dish form, Order Item list) is Story 3.2/3.3+ territory; the UX mockup for
that page (`key-table-order-detail.html`) only depicts an *already-opened* table with an existing
Order, it shows no "open"/"start order" affordance of its own. **The open action lives on the
grid, triggered by clicking an available tile**, not on the detail page. After a successful open,
navigate to `/waiter/tables/:tableId` (the route already exists and resolves to the still-placeholder
detail page, that's fine, later stories fill it in).

`Order`/`OrderItem` ORM models already exist (`data_models/order.py`, built in the original schema
pass) with no Pydantic request/response schemas yet, mirroring how `menu.py`/`recipe.py` started.
This story adds the first ones: just enough to represent "a table was opened, an Order now exists
tied to it." `OrderItem.price_at_add` does not exist as a column yet, that's Story 3.2's own
Alembic revision (see epics.md Story 3.2's own AC) — **do not add it here**, and do not add any
Order Item creation in this story at all, a newly-opened Order always starts with zero items.

## Acceptance Criteria

**AC1 — Opening an available Table starts a new Order**
Given an available Table, when a Waiter opens it, then the Table becomes `occupied` and a new
Order starts with status `pending` and no items (FR-4).

**AC2 — Occupied or reserved is rejected**
Given a Table that is already `occupied` or `reserved`, when a Waiter attempts to open it into a
new Order, then the action is rejected (FR-4). `reserved` is treated identically to `occupied` for
this purpose, v1 has no reservation-arrival workflow that would let a Waiter override a
reservation by opening it (PRD FR-4's own assumption note).

**AC3 — The Waiter's Tables grid**
Given the Waiter's Tables grid, when it renders, then each tile shows the table-status badge for
`available`/`occupied`/`reserved` (UX-DR2), and "No tables configured yet" is shown when none
exist (UX-DR15, the exact copy `TablesSetupPage.tsx` already uses for the identical empty Table
list).

**AC4 — Wire the new router into the container**
Given the `orders` domain router does not yet exist, when this story adds it, then `"api.orders"`
is appended to `container.wire(modules=[...])` in `main.py`, alongside the existing entries, never
replacing them (AD-1).

## Tasks / Subtasks

- [x] **Task 1: Request/response schemas** (AC: 1)
  - [x] Add to `backend/data_models/order.py` (colocated with the ORM classes, matching
    `menu.py`/`recipe.py`'s established shape):
    ```python
    class OrderResponse(BaseModel):
        """Body of any orders endpoint response describing an Order."""

        model_config = {"from_attributes": True}

        id: int
        table_id: int
        waiter_id: int
        status: OrderStatus
        created_at: datetime
        closed_at: datetime | None
        total_amount: Decimal | None
    ```
    No `CreateOrderRequest`: opening a table takes no body, `table_id` comes from the path
    (`POST /api/orders/tables/{table_id}/open` or equivalent, see Task 3), and `waiter_id` is
    always the authenticated actor, never client-submitted (a Waiter cannot open an Order on
    another Waiter's behalf).
- [x] **Task 2: Exceptions** (AC: 2)
  - [x] Add to `backend/exceptions/__init__.py`:
    ```python
    class TableNotAvailableError(ConflictError):
        """Raised when opening a Table that is not currently available (AC2).

        Distinct from TableInUseError (Story 2.4), which is specifically about
        an Admin's edit attempt; this is about a Waiter's open attempt. Covers
        both an already-occupied/reserved Table and the race where a second
        Waiter opens the same Table between this request's read and write, the
        guarded UPDATE (Task 3) cannot tell those apart, and both use the same
        detail, mirroring TableInUseError's own precedent.
        """

        detail = "Rejected, table not available"
    ```
    Reuse `TableNotFoundError` (already exists, `exceptions/__init__.py`, Story 2.4) for an
    unknown `table_id`, do not add a second one.
- [x] **Task 3: `OrderService`** (AC: 1, 2)
  - [x] New file `backend/services/order_service.py`, modeled on `TableService`'s shape
    (config-free, logger-only Factory) and `TableService.update_table`'s **guarded-UPDATE**
    pattern (trap 18) for the Table-status half of this action:
    ```python
    class OrderService:
        """Opens Tables into new Orders.

        Config-free, registered as a container-level Factory with only the
        logger injected, matching TableService's shape.
        """

        def __init__(self, logger: Any) -> None:
            self._logger = logger

        async def open_table(self, db: AsyncSession, actor: User, table_id: int) -> Order:
            """Mark an available Table occupied and start a new Order on it (AC1).

            The Table-status check and the write happen in one guarded UPDATE
            (WHERE status = 'available'), never a separate read-then-write, so
            two Waiters opening the same Table at once cannot both succeed
            (AD-6 pattern, the same shape TableService.update_table already
            uses). A zero-rowcount result means the Table was already
            occupied/reserved, or lost exactly that race (AC2); the guarded
            UPDATE cannot distinguish the two, and both raise the same error.

            Args:
                db: The active database session.
                actor: The Waiter opening the Table.
                table_id: The id of the Table to open.

            Returns:
                The newly created, pending Order.

            Raises:
                TableNotFoundError: If no Table matches table_id.
                TableNotAvailableError: If the Table's status is not
                    available at the moment of the write.
            """
    ```
  - [x] Implementation shape: `await db.get(RestaurantTable, table_id)`, raise
    `TableNotFoundError` if `None` (mirrors `TableService.get_table`). Then one guarded
    `UPDATE restaurant_tables SET status = 'occupied' WHERE id = :id AND status = 'available'`;
    `rowcount == 0` raises `TableNotAvailableError`. **Only after that UPDATE succeeds**, insert the
    `Order` row (`table_id=table_id, waiter_id=actor.id`, `status` defaults to `pending` at the
    column level, no need to set it explicitly) and commit **both** the Table status change and the
    Order insert in the same transaction/commit — a Table left `occupied` with no Order to show
    for it (or vice versa) is a state no later story can recover from cleanly. Log the rejection at
    `WARNING` and the success at `INFO` with `actor.id`/`table_id`/the new `order_id`, matching
    every existing service's convention.
- [x] **Task 4: Register in the container** (AC: 1)
  - [x] `backend/container.py`: add
    ```python
    order_service = providers.Factory(
        OrderService,
        logger=logging,
    )
    ```
    next to `table_service`, same shape.
- [x] **Task 5: `api/orders.py` router** (AC: 1, 2, 4)
  - [x] New file `backend/api/orders.py`, modeled on `api/tables.py`. Waiter-only (**not**
    Admin, unlike every prior domain router which was Admin-only or Admin-plus-one-Role, this is
    the first route gated to `UserRole.waiter` alone; see NFR-2/trap 8, `require_role` already
    supports any single Role with no change needed):
    ```python
    router = APIRouter(prefix="/api/orders", tags=["orders"])

    OrdersDep = Annotated[User, Depends(require_role(UserRole.waiter))]

    _ERROR_DESCRIPTIONS = {
        401: "No valid session cookie was supplied",
        403: "Authenticated, but the caller's Role is not waiter",
        404: "No matching Table was found",
        409: "The Table is not currently available",
    }

    @router.post(
        "/tables/{table_id}/open",
        response_model=OrderResponse,
        status_code=201,
        responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 404, 409),
    )
    @inject
    async def open_table(
        table_id: TableIdPath,
        actor: OrdersDep,
        db: SessionDep,
        order_service: OrderService = Depends(Provide[Container.order_service]),
    ) -> Order:
        return await order_service.open_table(db, actor, table_id)
    ```
    Reuse `TableIdPath` (`data_models.menu._INT4_MAX` bound, trap 16) from `api/tables.py`'s
    existing pattern rather than redeclaring it, either import it or redefine identically, this
    project has both precedents (menu.py/recipe.py share `_INT4_MAX` by import; each router so far
    has defined its own `*IdPath` alias). Prefer importing if it does not create an import-cycle;
    otherwise redeclare identically, matching `api/tables.py`'s own comment about trap 16.
  - [x] `backend/api/router.py`: add `from api.orders import router as orders_router` and
    `router.include_router(orders_router)`.
  - [x] `backend/main.py`: append `"api.orders"` to `container.wire(modules=[...])` (AC4) —
    **append, never replace**.
- [x] **Task 6: `TablesPage.tsx`, the real Waiter screen** (AC: 1, 2, 3)
  - [x] Replace the placeholder body of `frontend/src/pages/waiter/TablesPage.tsx` entirely. No
    routing change needed, `/waiter/tables` already points here.
  - [x] New `frontend/src/services/orderService.ts`: `useTables()` reusing the **existing**
    `GET /api/tables` endpoint (Story 2.4, already Admin-only today — **this story must widen it**,
    see Task 5's note below; do not add a second tables-list endpoint), and `useOpenTable()`, a
    mutation posting to `/api/orders/tables/{tableId}/open`, invalidating the tables list query on
    success so the grid reflects the new `occupied` status without a manual refresh.
  - [x] **`GET /api/tables` is currently Admin-only** (`TablesDep = require_role(UserRole.admin)`
    in `api/tables.py`). `project-context.md`'s own Domain rules note this is a known, deliberate
    Story 2.4 scoping gap explicitly earmarked for Epic 3 to widen ("`GET /api/tables` is currently
    Admin-only... Epic 3 widens it when Waiters need table reads. No test asserts a Waiter is
    refused, so widening breaks nothing"). **This story is that widening.** Add a `TablesReadDep`
    permitting `admin, waiter` (mirrors `MenuReadDep`/`InventoryReadDep`'s established split
    between a read-only dependency and a write-only one), change only `list_tables` to depend on
    it, leave `create_table`/`update_table` on the existing Admin-only `TablesDep` untouched.
  - [x] Grid layout: one tile per Table, each showing its status badge (`available`/`occupied`/
    `reserved`, per `key-tables.html`'s three badge colors/labels). Only an **available** tile is
    clickable to open; clicking it calls `useOpenTable()` and, on success, navigates to
    `/waiter/tables/${tableId}` (the existing placeholder route). An occupied/reserved tile is not
    an open target, per FR-4/AC2, do not wire a click handler on it that could even attempt the
    open call.
  - [x] Loading/error/empty states: mirror `TablesSetupPage.tsx`'s existing pattern exactly
    (`RowsSkeleton` while loading, an `Alert` with Retry on failure, "No tables configured yet" —
    reuse this exact string, it is `TablesSetupPage.tsx`'s own copy for the identical empty case,
    per AC3 — when the list loads empty). Combine loading/error across every query the page
    depends on (just `useTables()` here, so this is trivially satisfied, but do not regress the
    "combine every query" rule Story 2.5's review established for a future multi-query version of
    this page).
- [x] **Task 7: Tests**
  - [x] New file `backend/tests/test_orders.py`, mirroring `test_tables.py`'s style
    (`# Arrange`/`# Act`/`# Assert`, no docstrings). Cover:
    - A Waiter can open an available Table: 201, the Table's status is `occupied` (verify via a
      direct read, not just the response body), the returned Order has `status: "pending"`,
      `waiter_id` equal to the acting Waiter's id, and `table_id` matching.
    - Opening an already-`occupied` Table is rejected 409.
    - Opening a `reserved` Table is rejected 409 (AC2's explicit "treated the same as occupied").
    - Opening a nonexistent `table_id` is rejected 404.
    - An Admin, Cook, or Warehouse Manager cannot open a table, 403 (Role gate, NFR-2). An
      unauthenticated request gets 401.
    - **The race**: two "simultaneous" opens of the same Table only one succeeds. Use the
      established pattern from `test_tables.py`'s
      `test_race_between_form_load_and_save_is_rejected` (`monkeypatch` the service's own read
      step so a second open commits from the test's own session on its way out, landing strictly
      between the first request's read and write), not a test that merely sets the Table to
      `occupied` before the request starts (that proves only the ordinary AC2 rejection, not the
      race, per `project-context.md`'s "a test that pins the wrong thing" lesson).
    - `GET /api/tables` (widened in Task 6) is now reachable by a Waiter: 200. Still 403 for a
      Cook or Warehouse Manager (no AC grants either Role table reads yet).
  - [x] New file `frontend/src/pages/waiter/TablesPage.test.tsx`, mocking only `fetch`, matching
    `TablesSetupPage.test.tsx`'s established pattern. Cover: every table renders with its correct
    status badge; clicking an available tile opens it and navigates on success; an
    occupied/reserved tile has no click affordance; the empty-state copy; a failed table-list fetch
    renders a retry-capable error, not a silent blank page (Story 2.5's "combine loading/error"
    lesson, verify it actually applies here even though there is only one query).
  - [x] Full regression: `uv run pytest` from `backend/`, `pnpm test` from `frontend/`.

### Review Findings

- [x] [Review][Patch] `useOpenTable` invalidates the Tables query only on `onSuccess`, not on
  failure — a Waiter who loses the open race still sees a stale `available` tile that stays
  clickable, contradicting `tableService.ts`'s own established `onSettled` precedent
  [frontend/src/services/orderService.ts:24]
- [x] [Review][Patch] `TableTile`'s JSDoc claims `disabled` reflects whether *this* tile's open
  request is in flight, but `TablesPage` passes the same page-level `openMutation.isPending` to
  every tile — the doc is inaccurate about actual behavior
  [frontend/src/pages/waiter/TablesPage.tsx:40]
- [x] [Review][Patch] No frontend test exercises the `openMutation.isError` Alert path (a failed
  `/open` POST, e.g. losing the race with a 409, is never simulated)
  [frontend/src/pages/waiter/TablesPage.test.tsx]
- [x] [Review][Defer] `test_orders.py`'s race test runs both writes through the same
  `db_session`/connection, proving the guarded-UPDATE predicate is logically correct but not
  exercising true cross-connection concurrency [backend/tests/test_orders.py:710] — deferred,
  mirrors `test_tables.py`'s own established race-test pattern verbatim (this story's own spec
  mandated reusing it); a real multi-connection harness is a test-infrastructure investment
  beyond this story's scope.
- [x] [Review][Defer] No synchronous click-lock on `TableTile`/`handleOpen` — `openMutation.isPending`
  updates asynchronously, leaving a narrow window for a double-click to fire two concurrent open
  requests [frontend/src/pages/waiter/TablesPage.tsx:69] — deferred, the backend's guarded UPDATE
  already prevents any data-integrity consequence; worst case is a flashed extra 409, pure UX
  polish for a later pass.
- [x] [Review][Defer] `TableTile`'s `badgeColor` ternary has no exhaustive/default guard for a
  `TableStatus` value outside `available`/`occupied`/`reserved`
  [frontend/src/pages/waiter/TablesPage.tsx:53] — deferred, `TableStatus` is a closed 3-member
  enum shared with the backend; no current code path can produce a fourth value.
- [x] [Review][Defer] `OrderResponse` exposes bare `table_id`/`waiter_id` integers with no
  denormalized context (table number, waiter name) [backend/data_models/order.py:126] —
  deferred, explicitly out of scope per this story's own scope note; resolving Order ids into
  displayable context is the detail page's job in a later story.

## Dev Notes

### Architecture compliance

- **AD-6** (guarded conditional updates, extended to `RestaurantTable` by Story 2.4): this story is
  the *second* application of that same pattern to the same table, now for a Waiter's open action
  instead of an Admin's edit. Reuse the shape exactly (`UPDATE ... WHERE status = 'available'`,
  rowcount-checked), do not read-then-write.
- **AD-6, first application to `Order`**: unlike `RestaurantTable`'s single-column guard, opening a
  table is two writes (Table status + new Order row) that must succeed or fail together. Do the
  Table's guarded UPDATE first; only insert the Order and commit if that UPDATE's rowcount is 1.
  If a later story ever needs to roll back the Table status when the Order insert itself fails
  (it should not, a plain insert with no unique/FK conflict on valid input has no real failure
  mode here), that is out of this story's scope to defend against speculatively.
- **NFR-2**: enforced via `require_role(UserRole.waiter)`. First domain router scoped to exactly
  one non-Admin Role with no Admin fallback, do not default to including `UserRole.admin` the way
  every prior router did, FR-4 names only the Waiter.
- **Design pattern to name**: `OrderService.open_table` is a fourth independent instance of the
  Repository-style service pattern (`UserService` → `InventoryService`/`MenuService`/`TableService`
  → `OrderService`), and its guarded UPDATE is the second instance of AD-6's State-transition-guard
  pattern (`TableService.update_table` → `OrderService.open_table`). Name both in the PR
  description per this project's pattern-traceability convention.

### Existing files this story modifies

- `backend/data_models/order.py` — read fully before editing (135 lines). Add `OrderResponse` only;
  `RestaurantTable`, `TableStatus`, `Order`, `OrderStatus`, `OrderItem`, `OrderItemStatus` are all
  unchanged, this story neither adds nor edits any ORM column.
- `backend/api/tables.py` — read fully (131 lines) before adding `TablesReadDep` and switching only
  `list_tables` to it. `create_table`/`update_table` keep `TablesDep` (admin-only), untouched.
- `backend/exceptions/__init__.py` — add `TableNotAvailableError(ConflictError)`. No handler
  changes needed, `ConflictError`'s existing handler covers it.
- `backend/container.py` — add `order_service` as a `providers.Factory`.
- `backend/main.py` — append `"api.orders"` to `container.wire(modules=[...])`.
- `backend/api/router.py` — add and mount the new `orders_router`.
- `frontend/src/pages/waiter/TablesPage.tsx` — currently a Story 1.0/1.4 placeholder (an `<h1>`
  only). Full read is trivial but do read it, don't assume its current shape.

### New files

- `backend/api/orders.py`
- `backend/services/order_service.py`
- `backend/tests/test_orders.py`
- `frontend/src/services/orderService.ts`
- `frontend/src/pages/waiter/TablesPage.test.tsx`

No new backend types file, no new Alembic migration (no schema change this story, `Order`'s
columns already match what AC1 needs).

### Project Structure Notes

No deviation from the established five-folder backend layout or the frontend's `pages/{role}/`
convention. `services/orderService.ts` follows the existing per-domain frontend service pattern
(`menuService.ts`, `inventoryService.ts`, `tableService.ts`, `userService.ts`).

### Testing

- Both backend and frontend suites are touched, matching Story 2.5's shape (the last story that
  combined a Role-gate widening with a new real screen).
- Backend: `uv run pytest` from `backend/`. The race test is the one genuinely new technique
  needed here beyond what `test_tables.py` already demonstrates for the identical guarded-UPDATE
  shape, follow that file's `test_race_between_form_load_and_save_is_rejected` verbatim in
  structure, adapted to `OrderService.open_table`.
- Frontend: `pnpm test` from `frontend/`. Mock only `fetch`, never the service module wholesale.
- Before trusting the race test, reintroduce a read-then-write version of `open_table` locally,
  confirm the test goes red, then restore the guarded UPDATE. This is the same
  "if I implement the wrong thing, does this test notice?" check `project-context.md`'s Testing
  section requires for any test guarding a concurrency rule.

### References

- Story source: [Source: _bmad-output/planning-artifacts/epics.md#Story 3.1]
- FR-4 (full text, including the `reserved`-treated-as-`occupied` assumption note): [Source:
  _bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md#FR-4]
- AD-6 (guarded conditional updates) and its first application (`TableService.update_table`,
  Story 2.4): [Source: backend/services/table_service.py], [Source: _bmad-output/project-context.md,
  trap 18]
- The Admin-only `GET /api/tables` gap this story closes, already flagged and earmarked for Epic 3:
  [Source: _bmad-output/project-context.md, Domain rules section]
- UX mockups: the Waiter Tables grid (badges, empty state) [Source:
  _bmad-output/planning-artifacts/ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/mockups/key-tables.html];
  the order-detail page, confirmed out of scope for this story [Source:
  _bmad-output/planning-artifacts/ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/mockups/key-table-order-detail.html]
- Precedent this story copies: `api/tables.py`/`TableService`/`test_tables.py` (the guarded-UPDATE
  shape and its race-test pattern), `MenuReadDep`/`InventoryReadDep` (the read-dep-split shape):
  [Source: backend/api/tables.py], [Source: backend/api/menu.py], [Source: backend/api/inventory.py]
- Project-wide conventions and traps: [Source: _bmad-output/project-context.md]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (claude-sonnet-5)

### Debug Log References

None. No HALT conditions were hit; implementation proceeded task-by-task without needing
debug-log capture.

### Completion Notes List

- `OrderResponse` added to `data_models/order.py` and exported from `data_models/__init__.py`,
  matching `menu.py`/`recipe.py`'s established shape.
- `TableNotAvailableError(ConflictError)` added to `exceptions/__init__.py`, kept distinct from
  the existing `TableInUseError` since that exception's docstring explicitly scopes it to an
  Admin's edit attempt (Story 2.4 semantics).
- `OrderService.open_table` implements the AD-6 guarded-UPDATE pattern
  (`UPDATE ... WHERE status = 'available'`, rowcount check), mirroring
  `TableService.update_table`. The read step was factored into a private `_get_table` method
  (not inlined) specifically so the race test could monkeypatch just that seam, the same shape
  `test_tables.py`'s existing race test uses against `TableService.get_table`.
- `api/orders.py` added, Waiter-only (`require_role(UserRole.waiter)`) with no Admin fallback,
  the first router in the project scoped to exactly one non-Admin Role.
- `api/tables.py`'s `list_tables` widened from Admin-only to `TablesReadDep`
  (`admin, waiter`), closing the gap `project-context.md` had pre-flagged as deliberately
  deferred to Epic 3. `create_table`/`update_table` remain Admin-only, unchanged.
- Frontend: reused the existing `useTables()` hook (`tableService.ts`, Story 2.4) rather than
  duplicating it in `orderService.ts` as the story's Task 6 text suggested, exporting
  `TABLES_QUERY_KEY` so the new `useOpenTable()` mutation invalidates the same cache key. This
  is a deliberate deviation from the task's literal wording in favor of the established
  no-duplicate-hooks precedent.
- `TablesPage.tsx` rewritten: only `available` tiles are wrapped in a clickable
  `CardActionArea`; occupied/reserved tiles render the same content inside a plain, non-interactive
  `Card` with no click handler at all, per AC2.
- Full regression run clean: `uv run pytest` — 225 passed (backend, including the 12 new
  `test_orders.py` cases). `pnpm test` — 116 passed (frontend, including the 5 new
  `TablesPage.test.tsx` cases). `npx tsc -b` shows exactly one error,
  `IngredientsPage.tsx(97,23)`, a pre-existing bug in Story 2.6's code unrelated to this story
  (confirmed against the raw, unmerged `feature/story-2-6-...` branch).

### File List

- `backend/data_models/order.py` (modified — added `OrderResponse`)
- `backend/data_models/__init__.py` (modified — exported `OrderResponse`)
- `backend/exceptions/__init__.py` (modified — added `TableNotAvailableError`)
- `backend/services/order_service.py` (new)
- `backend/container.py` (modified — registered `order_service` provider)
- `backend/api/tables.py` (modified — added `TablesReadDep`, widened `list_tables`)
- `backend/api/orders.py` (new)
- `backend/api/router.py` (modified — included `orders_router`)
- `backend/main.py` (modified — appended `"api.orders"` to `container.wire`)
- `backend/tests/test_orders.py` (new)
- `frontend/src/services/tableService.ts` (modified — exported `TABLES_QUERY_KEY`)
- `frontend/src/services/orderService.ts` (new)
- `frontend/src/types/order.ts` (new)
- `frontend/src/pages/waiter/TablesPage.tsx` (modified — full implementation, was a placeholder)
- `frontend/src/pages/waiter/TablesPage.test.tsx` (new)

## Change Log

| Date | Change |
|---|---|
| 2026-08-14 | Story 3.1 implemented end-to-end (backend `OrderService`/`api/orders.py`, widened `GET /api/tables`, frontend `TablesPage.tsx`), all 7 tasks complete, full regression green. |
