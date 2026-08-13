---
baseline_commit: 9b16f6103587e284df39417dca0b153e5ab7d503
epic: 2
story: 4
---

# Story 2.4: Manage Restaurant Tables

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Admin,
I want to add and configure Restaurant Tables,
so that Waiters have tables to open orders against.

## Scope note (read first)

**Full-stack, same shape as Story 2.3.** AC7 requires the Tables setup screen itself to match the
UX mock (UX-DR8, UX-DR19), so this story builds both the backend and `TablesSetupPage`, currently
a placeholder. There is no separate "build the screen" story.

**Backend is greenfield**: no `RestaurantTable` service, router, or Pydantic schema exists yet.
`data_models/order.py`'s `RestaurantTable` ORM class already has everything needed (`table_number`
unique, `capacity`, `status` defaulting to `available`), no Alembic migration required.

**This is the third instance of the AD-6 guarded-conditional-update pattern** (OrderItem
transitions were the first; Story 2.3's AD-8 dish-row lock was the second, though that one used
`SELECT ... FOR UPDATE` rather than a conditional `UPDATE`). AC6's race (a Waiter opens the table
between an Admin loading the edit form and saving) is closed the same way OrderItem transitions
are: `UPDATE ... WHERE id = ? AND status = 'available'`, checked by rowcount, not a separate
read-then-write. Do not add a row lock here; a guarded UPDATE is the established pattern for this
exact shape of race and needs no extra round trip.

**Out of scope**: table deletion (PRD Non-Goals: "Restaurant Tables are added and edited, never
removed"). No delete route, no delete affordance anywhere in the UI. Waiter-facing table reads
(Epic 3) are a later story's concern; this story's `GET /api/tables` is Admin-only, matching how
Story 2.1's `GET /api/inventory/ingredients` started scoped to its own story's needs.

## Acceptance Criteria

**AC1 — Create, starting available**
Given a table number and capacity, when an Admin adds a new Restaurant Table, then it is created
with status `available` (FR-24).

**AC2 — Duplicate table number rejected on create**
Given a table number that already exists, when creation is attempted, then it is rejected as a
duplicate (FR-24, UX-DR17).

**AC3 — Edit while available succeeds**
Given a Restaurant Table whose status is `available`, when an Admin edits its table number or
capacity, then the change is saved (FR-24).

**AC4 — Edit rejected while occupied/reserved, control disabled**
Given a Restaurant Table whose status is `occupied` or `reserved`, when an Admin attempts to edit
it, then the edit is rejected and the Edit control is disabled with the inline reason "Rejected,
table in use", re-enabling the moment the table returns to `available` (FR-24, UX-DR13 pattern,
UX-DR17).

**AC5 — Rename-to-duplicate rejected**
Given an Admin renames a table to a number another table already uses, when the edit is submitted,
then it is rejected as a duplicate with the same inline copy as the create path, table numbers stay
unique across all tables (FR-24, UX-DR17).

**AC6 — Race between load and save is rejected, not silently applied**
Given a Waiter opens the table between the Admin loading the edit form and saving it, when the save
commits, then it is rejected rather than silently applied, via a guarded conditional update on the
expected `available` status with a rowcount check (AD-6 pattern extended to RestaurantTable, NFR-3).

**AC7 — No delete affordance**
Given Restaurant Tables cannot be deleted in v1, when an Admin views the Tables setup screen, then
no delete affordance exists anywhere on it, tables are only ever added and edited (FR-24, PRD
Non-Goals).

**AC8 — Screen matches the UX mock**
Given the Tables setup screen, when it renders, then it matches the UX mock with dense-row list
styling (UX-DR8, UX-DR19).

## Tasks / Subtasks

- [x] **Task 1: Backend request/response schemas** (AC: 1, 2, 3)
  - [x] New Pydantic schemas colocated with the ORM class in `backend/data_models/order.py`
    (matching `recipe.py`/`menu.py`'s existing shape, ORM-only file today, this is its first
    schema addition). Apply trap 16's bound proactively (both fields are plain `Integer`), do not
    wait for review to catch it a third time:
    ```python
    from pydantic import BaseModel, Field, model_validator

    _INT4_MAX = 2_147_483_647

    class CreateTableRequest(BaseModel):
        """Body of an Admin's request to create a Restaurant Table."""
        table_number: int = Field(gt=0, le=_INT4_MAX)
        capacity: int = Field(gt=0, le=_INT4_MAX)

    class UpdateTableRequest(BaseModel):
        """Body of an Admin's request to edit a Table's number and/or capacity.
        At least one field required, mirroring UpdateDishRequest's shape."""
        table_number: int | None = Field(default=None, gt=0, le=_INT4_MAX)
        capacity: int | None = Field(default=None, gt=0, le=_INT4_MAX)

        @model_validator(mode="after")
        def at_least_one_field(self) -> "UpdateTableRequest":
            if self.table_number is None and self.capacity is None:
                raise ValueError("at least one field must be provided")
            return self

    class TableResponse(BaseModel):
        model_config = {"from_attributes": True}
        id: int
        table_number: int
        capacity: int
        status: TableStatus
    ```
  - [x] `capacity: gt=0`, not `ge=0`: a zero-seat table is not a modeled concept (same reasoning
    `Dish.price`'s `gt=0` used).
  - [x] Export `CreateTableRequest`, `UpdateTableRequest`, `TableResponse` from
    `backend/data_models/__init__.py`.

- [x] **Task 2: Exceptions** (AC: 2, 3, 4, 5, 6)
  - [x] Add to `backend/exceptions/__init__.py`. `TableNotFoundError` extends the shared
    `NotFoundError` base Story 2.3 introduced (trap 17), no new near-duplicate handler needed:
    ```python
    class DuplicateTableNumberError(ConflictError):
        """Raised when creating or renaming a Table to a table_number that already exists."""
        detail = "Rejected, table number already exists"

    class TableInUseError(ConflictError):
        """Raised when editing a Table whose status is not available (AD-6 pattern, AC4/AC6).
        Covers both an edit attempted while already occupied/reserved, and the race
        where the Table stopped being available between the Admin loading the form
        and saving it; the guarded UPDATE cannot tell those two apart, and AC4's
        wording is the one both cases use."""
        detail = "Rejected, table in use"

    class TableNotFoundError(NotFoundError):
        """Raised when an admin action targets a table_id that does not exist."""
        detail = "Table not found"
    ```
  - [x] Both `ConflictError` subclasses need no handler changes, the existing family handler
    covers them (409). `TableNotFoundError` needs no handler changes either, `NotFoundError`'s
    single handler already covers it (404).

- [x] **Task 3: `TableService`** (AC: 1, 2, 3, 4, 5, 6)
  - [x] New file `backend/services/table_service.py`, modeled on `MenuService`'s shape:
    ```python
    class TableService:
        def __init__(self, logger: Any) -> None:
            self._logger = logger

        async def list_tables(self, db: AsyncSession) -> Sequence[RestaurantTable]:
            """No actor argument, plain unfiltered read, order_by(RestaurantTable.id)."""

        async def get_table(self, db, actor, table_id) -> RestaurantTable:
            """Raise TableNotFoundError if missing. Every by-id lookup funnels through here."""

        async def create_table(self, db, actor, payload: CreateTableRequest) -> RestaurantTable:
            """Duplicate check on table_number, insert with status defaulting to
            TableStatus.available (the column default already does this; do not
            pass a payload-derived status, CreateTableRequest has no status field
            at all, so there is nothing to override), IntegrityError race fallback,
            same shape as InventoryService.create_ingredient minus the func.lower()
            wrapper (table numbers are integers, no case question applies)."""

        async def update_table(
            self, db, actor, table_id: int, payload: UpdateTableRequest
        ) -> RestaurantTable:
            """1. get_table (404 if missing). 2. If table_number is changing,
            check for a duplicate among OTHER tables (id != table_id), raise
            DuplicateTableNumberError if found (AC5). 3. Build the guarded
            UPDATE: `update(RestaurantTable).where(RestaurantTable.id == table_id,
            RestaurantTable.status == TableStatus.available).values(**changed_fields)`.
            4. Execute, check rowcount: 0 means either the table was already
            occupied/reserved (AC4) or became so in the race window (AC6), raise
            TableInUseError either way, log at WARNING. 5. Catch IntegrityError as
            a race-losing duplicate (AC5's own race variant), same
            rollback-and-re-raise shape as create_category's fallback. 6. Commit,
            refresh, return, log at INFO with changed_fields."""
    ```
  - [x] The guarded UPDATE is a single statement, not a read-then-write: do not `SELECT` the
    table's current row and then decide whether to update in application code, that reopens the
    exact race AC6 exists to close. `WHERE ... AND status = 'available'` is the only correct
    shape, matching AD-6's own OrderItem precedent.
  - [x] A no-op update (submitted values equal to what is already stored) still goes through the
    guarded UPDATE in this story, unlike `MenuService.update_dish`'s early-return: the Table's
    `status` still has to be `available` for *any* save to succeed per AC3/AC4, so short-circuiting
    on "nothing changed" would incorrectly let a no-op edit through against an occupied table. If
    `changed_fields` is empty after step 2, skip the UPDATE and return the table unchanged with no
    log line, the same reasoning as `update_dish`, but only when nothing was actually submitted to
    change (`UpdateTableRequest`'s own validator already guarantees at least one field is present,
    so "nothing changed" only happens when the submitted values equal the stored ones).

- [x] **Task 4: Register in the container** (AC: 1, 2, 3, 4, 5, 6)
  - [x] `backend/container.py`: add `table_service = providers.Factory(TableService, logger=logging)`
    next to `menu_service`.

- [x] **Task 5: `api/tables.py` router** (AC: 1, 2, 3, 4, 5, 6, 7)
  - [x] New file `backend/api/tables.py`, modeled on `api/menu.py` exactly: `APIRouter(prefix="/api/tables",
    tags=["tables"])`, its own `_ERROR_DESCRIPTIONS`, `error_responses()` reused. `TablesDep = Annotated[User,
    Depends(require_role(UserRole.admin))]`, admin-only (FR-24 names only the Admin), same shape as
    `MenuDep`, not `InventoryWriteDep`'s two-Role form.
    ```python
    @router.get("/", response_model=list[TableResponse],
                responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403))
    async def list_tables(actor: TablesDep, db: SessionDep,
                           table_service: TableService = Depends(Provide[Container.table_service])) -> list[RestaurantTable]:
        return await table_service.list_tables(db)

    @router.post("/", response_model=TableResponse, status_code=201,
                 responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 409))
    async def create_table(payload: CreateTableRequest, actor: TablesDep, db: SessionDep,
                            table_service: TableService = Depends(Provide[Container.table_service])) -> RestaurantTable:
        return await table_service.create_table(db, actor, payload)

    @router.patch("/{table_id}", response_model=TableResponse,
                  responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 404, 409))
    async def update_table(table_id: Annotated[int, Path(gt=0, le=_INT4_MAX)], payload: UpdateTableRequest,
                            actor: TablesDep, db: SessionDep,
                            table_service: TableService = Depends(Provide[Container.table_service])) -> RestaurantTable:
        return await table_service.update_table(db, actor, table_id, payload)
    ```
    Bound `table_id`'s path parameter with `Path(gt=0, le=_INT4_MAX)` from the start (Story 2.3's
    review caught this same gap after the fact on four routes, apply it proactively here).
  - [x] No route below `/{table_id}` for delete. There is nothing to build, not even a stub that
    returns 405, the absence itself is AC7.
  - [x] `backend/api/router.py`: add and mount `tables_router`.
  - [x] `backend/main.py`: append `"api.tables"` to `container.wire(modules=[...])`, append-only.

- [x] **Task 6: Backend tests** (AC: 1, 2, 3, 4, 5, 6, 7)
  - [x] New file `backend/tests/test_tables.py`, mirroring `test_menu.py`'s style
    (`# Arrange`/`# Act`/`# Assert`, no docstrings). Cover:
    - Admin creates a Table (201), status is `available`.
    - Duplicate `table_number` on create is rejected 409 with "Rejected, table number already
      exists".
    - Admin edits an `available` Table's number/capacity (200), change persists.
    - Editing an `occupied` Table (seed directly via `db_session`, `status=TableStatus.occupied`)
      is rejected 409 with "Rejected, table in use". Same for `reserved`.
    - Renaming a Table to another existing Table's number is rejected 409 (AC5), including when
      the Table being edited is itself `available` (the number collision fires before the status
      guard even matters for this case, but assert the 409 regardless of which guard produced it,
      the response detail should be the duplicate message not the in-use message when
      table_number is the actual conflict).
    - **AC6, the story's core rule**: seed two Tables. In one test connection/transaction shape,
      change the target Table's status to `occupied` *between* reading it once (simulating "the
      Admin loaded the form") and calling `PATCH` (simulating "the save"). Since this project's
      test harness runs everything through one `db_session` per test, simulate the race directly:
      update the row's status out from under the guarded UPDATE (e.g. issue a raw status change via
      `db_session` and commit it) immediately before calling the PATCH endpoint, then assert 409
      "Rejected, table in use". This proves the guard reads live state, not a value read earlier in
      the request.
    - `PATCH` with an empty body is rejected 422.
    - `PATCH`/edit on a nonexistent `table_id` is rejected 404.
    - A negative or zero `capacity`/`table_number` is rejected 422; a value beyond int4 range is
      rejected 422 (both the request body and the `table_id` path parameter, matching Story 2.3's
      review lesson about path parameters needing the same bound as body fields).
    - A non-Admin (waiter, cook, warehouse_manager) cannot create/edit/list, 403. Unauthenticated,
      401.
    - `GET /api/tables` returns every table created.
  - [x] Verify the int4-boundary and precision claims against the live test database before
    trusting the assertion, not from reasoning alone (project-context.md's Story 2.1 review lesson).
  - [x] Full regression: `uv run pytest` from `backend/`.

- [x] **Task 7: Frontend `tableService.ts`** (AC: 1, 2, 3, 4, 5, 6, 7)
  - [x] New file `frontend/src/services/tableService.ts`, following `menuService.ts`'s exact shape
    (query key arrays, `apiRequest<T>`, `retry: false` on every query per Story 2.3's review
    lesson, applied proactively here):
    - `useTables()` — `useQuery`, key `["tables"]`.
    - `useCreateTable()` — `useMutation`, invalidates `["tables"]` on success.
    - `useUpdateTable()` — `useMutation` taking `{ tableId, payload }`, invalidates `["tables"]` on
      success.
  - [x] New file `frontend/src/types/table.ts`: `TableStatus` union type mirroring
    `backend/data_models/order.py`'s enum (`"available" | "occupied" | "reserved"`), and a `Table`
    interface mirroring `TableResponse`'s JSON shape (snake_case field names), same pattern as
    `types/menu.ts`.

- [x] **Task 8: Frontend `TablesSetupPage`** (AC: 1, 2, 3, 4, 5, 6, 7, 8)
  - [x] Replace the placeholder in `frontend/src/pages/admin/TablesSetupPage.tsx`. Per the mockup
    (`mockups/key-tables-setup.html`): a page header, an "Add table" panel (`table_number` and
    `capacity` fields plus a submit button), and a list below it (`MuiTable`, `size="small"`
    per UX-DR8's dense-row spec, already the theme default per `config/theme.ts`, do not override
    it). Each row: table number, capacity, a status Chip, and an Edit action. **No delete action
    anywhere in this component or any child of it** (AC7).
  - [x] Clicking Edit on an `available` row switches that row into two editable `TextField`s (both
    controlled, resynced from server state the same way Story 2.3's `RecipeLineRow` resyncs its
    quantity field, do not repeat the uncontrolled-`defaultValue` mistake that story's review
    caught) plus Save/Cancel. On any other status, the Edit control is disabled with an inline
    reason "Rejected, table in use" shown via `Tooltip` **and** visible text (a `Tooltip` alone is
    Story 2.3's review's own finding: tooltips do not appear on touch or keyboard-primary
    interaction, do not repeat that gap here).
  - [x] The Add-table form and the inline row-edit form must each surface their own mutation's
    `isError` as a visible `Alert`, not silently swallow a 409/422 the way Story 2.3's first draft
    did before its review. Show the backend `detail` string verbatim (`ApiError.message` already
    carries it), do not hand-write a second copy of "Rejected, table number already exists"/
    "Rejected, table in use" that could drift from the backend's wording.
  - [x] Handle `useTables()`'s `isError` with a retry affordance, and the empty-list case with "No
    tables configured yet." (from the mockup's documented empty state), matching the pattern
    Story 2.3's review established for `MenuManagementPage`'s dish-list failure/empty states. Do
    not ship the blank-page-on-failure gap that story's first draft had.

- [x] **Task 9: Frontend tests** (AC: 1, 2, 3, 4, 5, 6, 7, 8)
  - [x] New file `frontend/src/pages/admin/TablesSetupPage.test.tsx`, mocking only `fetch` (Story
    1.4's lesson, reapplied by Story 2.3's review to this exact page shape). Cover:
    - The table list renders from a mocked `GET /api/tables` response.
    - Creating a table (mocked `POST` success + updated `GET` on refetch) adds it to the list.
    - A duplicate-number rejection (mocked 409) surfaces inline, verbatim.
    - An `occupied` table's Edit control is disabled and shows "Rejected, table in use" (as visible
      text, assert it with `getByText`, not only via a `Tooltip` that a text-based query might miss
      if implemented as `title`-only).
    - Editing an `available` table (mocked `PATCH` success) updates the row and exits edit mode.
    - A failed `GET /api/tables` (network error) shows an error with Retry, not a blank page.
    - No `DELETE` request is ever issued anywhere, and no delete affordance renders (`queryByRole("button", { name: /delete/i })` is null), directly asserting AC7 rather than only asserting its absence by omission.
  - [x] Before trusting a new regression test, reintroduce the bug it targets and confirm it goes
    red first (Story 1.4's lesson, reapplied throughout Story 2.3's own review pass).
  - [x] `pnpm test` from `frontend/`.

### Review Findings

Code review 2026-08-12 (three parallel adversarial layers: Blind Hunter, Edge Case Hunter,
Acceptance Auditor). Blind Hunter's verdict on the story's central design: the guarded conditional
UPDATE **does** hold. One request-scoped session, READ COMMITTED, and the `UPDATE`'s row lock
re-evaluates its `WHERE` against the latest committed row, so a Waiter committing `occupied` at any
point before the write yields `rowcount == 0`. AD-6's pattern is correctly applied. The defects are
around it. Three findings were reproduced against a live database before being filed, not accepted
from reasoning: the no-op bypass, the `MissingGreenlet` mechanism, and the explicit-null partial
write.

- [x] [Review][Decision] **Resolved 2026-08-12 (Ofek): option (c), defer to Epic 3.** Epic 3 must build live table status for Waiters to satisfy its own ACs, so the event contract is better designed there with its real consumers in mind than invented here for one. Recorded in `deferred-work.md`. AC4's disabled-control and inline-reason halves are met; only the live re-enable is outstanding. Original finding: AC4's "re-enabling the moment the table returns to `available`" is not implemented — `disabled={!isAvailable}` derives from `useTables()` data, but nothing refreshes it when a *different* session frees the table: no `refetchInterval`, no `useRealtime()` subscription, and the query is invalidated only by this page's own mutations. A Waiter releasing a table leaves the Edit button disabled indefinitely until a manual reload, and the Admin never sees a table become occupied either (so they keep opening edit forms already doomed to 409). AD-2 requires every state change to be emitted by the service that owns the mutation, and `RealtimeProvider`'s `subscribe(event, handler)` has existed unused since Story 1.5. No service in the codebase broadcasts yet, so this is a project-wide first rather than a regression, but this is the first AC to explicitly demand live re-enablement. Options: (a) emit `table.created`/`table.updated` from `TableService` and subscribe on this page, the AD-2-correct fix and the first real use of the Story 1.5 transport; (b) add a `refetchInterval` to `useTables`, cheap but polling; (c) accept the gap, record it in `deferred-work.md`, and let Epic 3 (which needs live table status for Waiters anyway) build the broadcast.
- [x] [Review][Patch] HIGH: the AC6 race test is byte-for-byte identical to the AC4 occupied test and cannot fail [backend/tests/test_tables.py] — both create a table, set `status = occupied` via `db_session`, commit, PATCH, expect 409. The status is already occupied *before the request starts*, so the request never observes an `available` row and no interleaving occurs. Replacing the guarded UPDATE with the naive read-then-write this story exists to forbid leaves **both tests green**. The story's one novel requirement therefore has zero real coverage, and the test's own comment overclaims ("so the guarded UPDATE reads live, already-changed state"). Task 6 also specified seeding two tables and flipping status *between* the read and the write; neither happened. Fix: flip the status from a second connection after the service's `get_table` read and before its `UPDATE` (patch `TableService.get_table` to commit the flip on its way out), so removing the guard turns the test red. Third instance of the "test that cannot fail" pattern in this project.
- [x] [Review][Patch] HIGH: `create_table` reads `actor.id` after `db.rollback()`, so a genuine duplicate-create race 500s instead of 409ing [backend/services/table_service.py] — `rollback()` expires every object bound to the session including `actor`, so reading `actor.id` afterward triggers a lazy load with no greenlet context. Reproduced directly: `actor.id` after `await db.rollback()` raises `MissingGreenlet`. This is the exact bug this story found and fixed in `update_table` forty lines below, complete with a five-line comment explaining it, while leaving the identical ordering in `create_table` untouched. The branch is unreachable in a single-threaded test (the pre-check always wins), which is why the suite is green. `MenuService.create_category`, `MenuService.add_recipe_ingredient` and `InventoryService.create_ingredient` have the same ordering and are already recorded in `deferred-work.md`; fix all four together.
- [x] [Review][Patch] HIGH: non-numeric input becomes JSON `null` and produces a silent partial write [frontend/src/pages/admin/TablesSetupPage.tsx, backend/data_models/order.py] — `Number("abc")` is `NaN`, and `JSON.stringify` serializes `NaN` to `null` (verified). `UpdateTableRequest.table_number` is `int | None`, so an explicit `null` is indistinguishable from an omitted field and is silently skipped. Reproduced end to end: `PATCH {"table_number": null, "capacity": 8}` returns **200** with `table_number` unchanged and `capacity` applied. Scenario: an Admin types `abc` into the number field *and* changes capacity, clicks Save, the row exits edit mode showing success, and they believe the table was renumbered when it was not. Related coercions on the same inputs: `Number("")` and `Number(" ")` are both `0` (so a single space passes `canSubmit` and sends `0`), and `"4.5"` reaches the server as a float. Fix both halves: validate client-side before sending (reject non-integer input rather than coercing), and reject an explicit `null` server-side instead of treating it as omitted.
- [x] [Review][Patch] HIGH: an edit matching a stale cached value is silently discarded with no request [frontend/src/pages/admin/TablesSetupPage.tsx] — `save()` diffs the drafts against `table`, the object from the TanStack Query cache, and returns early with `setIsEditing(false)` when the payload is empty. If the cache holds `capacity: 4` while the server holds `8` (another Admin changed it), an Admin who types `4` gets no request, no message, edit mode exits, and the row renders `4` as though it saved. `useTables` sets no `staleTime` and `App.tsx` uses a bare `new QueryClient()`, so the stale window is real. No test asserts the PATCH body or the no-request path.
- [x] [Review][Patch] MEDIUM: a no-op PATCH on an occupied table returns 200, bypassing the status guard [backend/services/table_service.py] — `if not changed_fields: return table` short-circuits *before* the guarded UPDATE. Reproduced: `PATCH {"capacity": 4}` against an occupied table whose capacity is already 4 returns **200** with a body reading `'status': 'occupied'`. AC4 says an edit attempted on an occupied table is rejected. The code comment claims the opposite of what the code does ("never as a way to skip the status guard"), and the story spec contradicts itself on this point, first stating the no-op must still go through the guarded UPDATE and then authorizing the early return. AC4's wording favors rejection. Untested in either direction.
- [x] [Review][Patch] MEDIUM: a rejected save never refreshes the row, leaving a permanently contradictory UI [frontend/src/services/tableService.ts] — `useUpdateTable` invalidates only `onSuccess`. When a save loses the race and returns 409 "Rejected, table in use", nothing refetches: the row keeps showing a green `available` Chip and an enabled Save button beside a red Alert saying the table is in use, and the Admin can retry forever. Invalidate on error too (`onSettled`), so the row flips to `occupied` and disables itself.
- [x] [Review][Patch] MEDIUM: a row stays in edit mode after its table becomes unavailable, and the in-use reason is suppressed [frontend/src/pages/admin/TablesSetupPage.tsx] — nothing watches `table.status` (the resync effect's deps exclude it), and the caption is gated on `!isEditing`. A table seated while the Admin has the row open keeps rendering editable fields and Save/Cancel, with the only signal being a 409 after clicking Save, while the Chip beside it already says occupied.
- [x] [Review][Patch] MEDIUM: the resync `useEffect` clobbers in-progress typing [frontend/src/pages/admin/TablesSetupPage.tsx] — the effect overwrites both drafts from server values unconditionally, including while `isEditing` is true. With no `staleTime` and TanStack's default `refetchOnWindowFocus`, alt-tabbing away and back during an edit silently replaces typed text, and the Admin may then Save a value they never chose. Gate on `!isEditing` (or surface a conflict notice). Inherited from Story 2.3's `RecipeLineRow`, which the spec told this story to copy, so fix the precedent too.
- [x] [Review][Patch] MEDIUM: a failed save leaves a stale error Alert after Cancel, and Cancel during an in-flight save orphans it [frontend/src/pages/admin/TablesSetupPage.tsx] — `updateMutation.reset()` is called in `startEdit` but not `cancelEdit`, and the Alert renders on `isError` regardless of `isEditing`, so a 409 followed by Cancel pins a red error under a row that is no longer being edited. Cancel is also not disabled while `isPending`, so a cancelled-but-in-flight save can land silently or error into a row showing no edit UI.
- [x] [Review][Patch] MEDIUM: the row-edit 409 path is never tested [frontend/src/pages/admin/TablesSetupPage.test.tsx] — the seven tests cover create-duplicate inline messaging but no test makes a `PATCH` return 409, so the row-level `Alert` never renders in any test. AC5 requires the rename-to-duplicate rejection to reach the Admin "with the same inline copy as the create path", and only the create half is proven. Same shape as the gap Story 2.3's review filed against silent edit failures.
- [x] [Review][Patch] LOW: `db.commit()` sits outside the `IntegrityError` try on the update path [backend/services/table_service.py] — the try wraps only the `UPDATE`. If a unique violation surfaces at commit rather than at execution, the `IntegrityError` escapes uncaught as a 500 instead of the intended 409. `create_table` gets this right (its try wraps the commit).
- [x] [Review][Patch] LOW: the update path's `IntegrityError` handler logs `table_number=None` when only capacity changed [backend/services/table_service.py] — the handler unconditionally attributes any integrity violation to a duplicate table number and logs `changed_fields.get("table_number")`, producing a warning that names no cause on a capacity-only edit. Guard the branch on `"table_number" in changed_fields` at minimum.
- [x] [Review][Patch] LOW: `_INT4_MAX` is now defined twice and reached by a private cross-package import [backend/data_models/order.py, backend/api/tables.py] — `recipe.py` established importing it from `menu.py`; `order.py` redeclares it with a near-copy of the comment, and `api/tables.py` reaches past `data_models/__init__.py`'s `__all__` to grab the underscore name. Same "third near-identical copy is the signal" reasoning trap 17 applies to `NotFoundError`. Promote it to one shared public constant.
- [x] [Review][Patch] LOW: `/api/tables/` uses a trailing-slash collection route, unlike every sibling router [backend/api/tables.py] — `menu.py` and `inventory.py` mount `"/categories"`, `"/ingredients"` under their prefix; this uses `"/"`, producing `/api/tables/` while `PATCH /api/tables/{id}` has no slash, so the URL space is internally inconsistent. Works today because the frontend matches it, but anything hitting `/api/tables` gets a 307 redirect, which for a credentialed cross-origin POST means re-preflighting the target.
- [x] [Review][Patch] LOW: the test's PATCH mock matches `/api/tables/1` by prefix [frontend/src/pages/admin/TablesSetupPage.test.tsx] — `path.includes("/api/tables/1")` also matches `/api/tables/12` and `/api/tables/199`. Harmless with the current single-table fixture, silently mis-routes the moment a fixture uses a two-digit id.
- [x] [Review][Defer] LOW: the page diverges from the UX mock's panel layout [frontend/src/pages/admin/TablesSetupPage.tsx] — the mock has two bordered panels with a "Add table" panel head, a "N tables configured" subtitle, right-aligned row actions, and values formatted as `Table 1` / `2 seats`; the page renders a bare form and bare table with raw values. Dense-row styling itself (UX-DR8) **is** correctly satisfied via the theme's `MuiTable` default. Deferred, cosmetic and no AC-visible behavior depends on it.
- [x] [Review][Defer] LOW: `GET /api/tables/` is Admin-only, which Epic 3 will have to widen [backend/api/tables.py] — project-context.md states "every Waiter sees every Table", and `router.tsx` already routes `waiter/tables`. This story deliberately scoped reads to Admin. No test asserts a Waiter is refused on the list route, so widening later breaks nothing. Deferred to whichever Epic 3 story needs Waiter table reads.
- [x] [Review][Defer] LOW: an offline (paused) query renders a blank page and a paused mutation disables its button forever [frontend/src/pages/admin/TablesSetupPage.tsx] — with TanStack v5's default `networkMode: "online"`, an offline query is `isPending` but not `isFetching`, so all four render branches are false. Pre-existing codebase-wide shape (`MenuManagementPage` has it too), not introduced here.
- [x] [Review][Defer] LOW: the test-support fake `Response` diverges from the real one [frontend/src/pages/admin/TablesSetupPage.test.tsx] — supplies only `ok`/`status`/`text`/`json`, with no `headers`, `statusText`, or `body`. Fine against today's `httpClient`; a future 204 path or header read fails obscurely. Worth lifting into one shared test helper alongside `appIntegration.test.tsx`'s copy.
- [x] [Review][Dismiss] AC8's dense-row styling is missing because the `<Table>` has no `size="small"` — **false positive**, verified: `frontend/src/config/theme.ts` sets `MuiTable: { defaultProps: { size: "small" } }` on both themes, and Task 8 explicitly instructed not to override it. Dense rows are satisfied. (The two reviewers disagreed on this; the Acceptance Auditor was correct.)
- [x] [Review][Dismiss] `create_table`'s duplicate check and the rename check are read-then-write (trap 9) — the DB's own `unique=True` on `table_number` is the real arbiter and both paths carry an `IntegrityError` fallback translating to the same 409. Correct as shipped, and the same shape Stories 2.1/2.2 already accepted.
- [x] [Review][Dismiss] `create_table` labels every `IntegrityError` a duplicate table number — `restaurant_tables` has exactly one constraint today, so it is unreachable, and this matches the precedent Story 2.2 explicitly accepted for `create_category`. (The update-path log-noise variant is filed separately as a patch above.)
- [x] [Review][Dismiss] Error precedence: renaming an occupied table to a taken number reports the duplicate before the in-use rule, costing two round trips — both messages are accurate for their own condition, and Task 6 explicitly required the duplicate check to run first so AC5's wording wins on a genuine number collision.
- [x] [Review][Dismiss] `list_tables` is unpaginated and `capacity`/`table_number` have no ceiling below int4 — bounded in practice by a restaurant's table count, same accepted reasoning as `GET /api/admin/users`; the int4 bound already prevents the 500 that trap 16 is about.
- [x] [Review][Dismiss] `db.refresh()` after commit re-reads live state, so a 200 body could carry a status the write did not produce — accurate but harmless: the response reports current committed truth, which is what the frontend should render, and the alternative (returning a stale in-transaction snapshot) is worse.

## Dev Notes

### Architecture compliance

- **AD-6, extended** (this story's core rule, AC6): project-context.md documents this extension
  explicitly ("Extended to `RestaurantTable` edits (must be `available`)"), the architecture
  spine's own AD-6 text is scoped to OrderItem only; the extension is this project's own decision,
  not a spine quote to cite verbatim. Implement as a single guarded `UPDATE`, not a `SELECT` then
  conditional `UPDATE` in application code.
  - **Do not reuse Story 2.3's `_lock_dish`-style `SELECT ... FOR UPDATE` pattern here.** That
    shape existed because Story 2.3's invariant needed to synchronize *two different write paths*
    (deleting a recipe line, toggling availability) against each other around a *count* that
    changes across multiple rows. This story's invariant is a single row's own `status` column
    checked at the moment of its own write, which is exactly what a guarded conditional `UPDATE`
    is for, matching every existing OrderItem transition. Introducing a row lock here would be
    solving an already-solved problem with the wrong tool.
- **FR-24 / NFR-3** cited directly by the epics ACs.
- **Design pattern to name**: `TableService` is a fourth independent instance of the Repository-style
  service pattern (`UserService` → `InventoryService` → `MenuService` → `TableService`), name it
  the same way in the PR description.

### Existing files this story modifies

- `backend/data_models/order.py` — currently ORM-only (`TableStatus`, `RestaurantTable`, `Order`,
  `OrderItem`), no Pydantic schemas anywhere in this file yet. This story's three schemas are its
  first. Do not touch `Order`/`OrderItem`, out of scope.
- `backend/data_models/__init__.py` — export the three new schema names.
- `backend/exceptions/__init__.py` — add three new exception types. `TableNotFoundError` inherits
  the `NotFoundError` base Story 2.3 introduced; do not create a fourth near-duplicate handler.
- `backend/container.py` — add `table_service` as a `providers.Factory`.
- `backend/main.py` — append `"api.tables"` to `container.wire(modules=[...])`.
- `backend/api/router.py` — add and mount the new `tables_router`.
- `frontend/src/pages/admin/TablesSetupPage.tsx` — currently a placeholder, becomes real content.
- `frontend/src/router.tsx` — no change needed, `admin/tables` already routes to
  `TablesSetupPage`, only its contents change.

### New files

- `backend/api/tables.py`
- `backend/services/table_service.py`
- `backend/tests/test_tables.py`
- `frontend/src/services/tableService.ts`
- `frontend/src/types/table.ts`
- `frontend/src/pages/admin/TablesSetupPage.test.tsx`

### Project Structure Notes

No new top-level backend or frontend folder. No Alembic migration: `RestaurantTable`'s columns are
unchanged, only Pydantic schemas are added. Confirm with `tests/test_migrations.py`'s existing
checks, no new revision expected.

### Testing

- Backend: `uv run pytest` from `backend/`. Frontend: `pnpm test` from `frontend/`. Both harnesses
  unchanged since Story 1.0/1.4.
- Reuse `test_menu.py`'s helper shape (`_create_user`, `_login`, `_login_as_admin`) rather than
  reinventing it in `test_tables.py`; these are file-local helpers today (not shared across test
  files), so copy the pattern, do not attempt a cross-file import.
- Frontend: mock only `fetch` for at least one test file covering this page (Task 9), matching the
  standing rule Story 1.4 established and Story 2.3's review reinforced.
- Verify any new numeric-boundary test value is actually rejected by running it, not by reasoning
  about the Pydantic bound in the abstract (Story 2.1's review lesson, repeated in Story 2.3's own
  int4 path-parameter fix, which was reproduced against a live Postgres before being trusted).

### References

- Story source: [Source: _bmad-output/planning-artifacts/epics.md#Story 2.4]
- FR-24 (full text) and the table-deletion Non-Goal: [Source:
  _bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md#FR-24]
- AD-6 (spine text, OrderItem-scoped) and its project-specific extension to RestaurantTable:
  [Source: ARCHITECTURE-SPINE.md#AD-6], [Source: _bmad-output/project-context.md] (binding
  architecture invariants section, "Extended to RestaurantTable edits")
- UX-DR8 (dense-row styling), UX-DR13 (disabled-control-plus-inline-reason pattern, reused by
  analogy from Menu Management), UX-DR17 (inline rejection microcopy), UX-DR19 (build all 13 IA
  surfaces per the mockups): [Source: _bmad-output/planning-artifacts/epics.md]
- Mockup reference (structure only, not literal markup; everything not a documented delta
  component uses stock MUI): [Source:
  _bmad-output/planning-artifacts/ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/mockups/key-tables-setup.html]
- Precedent this story extends: `MenuService`/`api/menu.py`'s shape (Story 2.2/2.3), and Story
  2.3's own code-review findings this story applies proactively (trap 16 on path parameters,
  controlled-not-uncontrolled inputs that resync, visible error states for every mutation, an
  error-vs-empty distinction on every list query, `retry: false` on every new query hook):
  [Source: _bmad-output/implementation-artifacts/2-3-define-a-dishs-recipe.md#Review Findings]
- `NotFoundError` shared base, reused rather than duplicated a sixth time: [Source:
  backend/exceptions/__init__.py]
- The existing `RestaurantTable` ORM shape, unchanged by this story: [Source:
  backend/data_models/order.py]

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (Claude Code, bmad-dev-story workflow)

### Debug Log References

- Found a real bug while writing the AC6 race test, not from the story's own snippet: logging
  `actor.id` **after** `await db.rollback()` in `update_table`'s rejection branches raised an
  unhandled `sqlalchemy.exc.MissingGreenlet`. `rollback()` expires every object bound to the
  session, including `actor`, so reading `actor.id` afterward triggers an implicit lazy-load with
  no greenlet context to run it in. Fixed by logging before rolling back. The same ordering
  (rollback, then `actor.id` in the log line) already exists in `MenuService.create_category`,
  `MenuService.add_recipe_ingredient`, and `InventoryService.create_ingredient`'s `IntegrityError`
  handlers, but none of their tests actually trigger a real constraint race (the existence check
  before insert always wins first in a single-threaded test), so the bug is latent there too,
  never exercised. Not fixed in those files, out of this story's scope; recorded in
  `deferred-work.md`.
- Backend and frontend suites verified independently before combining: backend first (209 passed,
  up from 191), then frontend (62 passed, up from 55), then `pnpm build` clean.

### Completion Notes List

- All 8 acceptance criteria satisfied. AC1/AC2 (create, starting available, duplicate rejected):
  `TableService.create_table`, same check-then-insert-with-IntegrityError-fallback shape as
  `MenuService.create_category`. AC3/AC4/AC6 (edit only while available, including the race): a
  single guarded `UPDATE ... WHERE id = ? AND status = 'available'` in `update_table`, checked by
  rowcount, never a read-then-write; the AC6 test simulates the race by committing a status change
  via the test's own `db_session` (a separate connection) immediately before the `PATCH`, proving
  the guard reads live state. AC5 (rename-to-duplicate): a duplicate check against other tables
  runs before the guarded UPDATE, plus an `IntegrityError` fallback for the race variant. AC7 (no
  delete): no `DELETE` route exists anywhere in `api/tables.py`, and a frontend test asserts no
  delete affordance renders and no `DELETE` request is ever issued. AC8 (screen matches the mock):
  `TablesSetupPage` built per `key-tables-setup.html`'s structure using stock MUI `Table`
  (`size="small"`, the theme default, UX-DR8).
- `TableService` is a fourth independent instance of the Repository-style service pattern
  (`UserService` → `InventoryService` → `MenuService` → `TableService`).
- Applied three of Story 2.3's own review lessons proactively rather than waiting for a second
  review to catch them again: `Path(gt=0, le=_INT4_MAX)` on `table_id` from the start; every new
  query hook (`useTables`) sets `retry: false`; every mutation's `isError` renders a visible
  `Alert` (create, update), and the list query's `isError`/empty/loaded states are each handled
  distinctly with a Retry action, never collapsed into a blank page.
- The per-row edit fields (`TableListRow`) are controlled and resync via `useEffect` off the
  server's own value, the same pattern `DishRecipeEditor`'s `RecipeLineRow` established, not the
  uncontrolled `defaultValue` shape that story's review had to fix after the fact.
- The "Rejected, table in use" reason is rendered as both a `Tooltip` and visible `Typography`
  text, per Story 2.3's review finding that a tooltip alone is invisible to touch and
  keyboard-primary interaction. Confirmed a regression test can catch its removal: temporarily
  deleted the visible-text render, watched `TablesSetupPage.test.tsx`'s "disables Edit and shows
  the in-use reason" test go red, then restored it.
- Backend suite: 209 passed (up from 191, +18 in `test_tables.py`). Frontend suite: 62 passed (up
  from 55, +7 in `TablesSetupPage.test.tsx`). Both green on the final full run; production build
  clean. No new Alembic migration, `RestaurantTable`'s columns were already exactly what this
  story needed.

### File List

**Added**

- `backend/api/tables.py`
- `backend/services/table_service.py`
- `backend/tests/test_tables.py`
- `frontend/src/services/tableService.ts`
- `frontend/src/types/table.ts`
- `frontend/src/pages/admin/TablesSetupPage.test.tsx`

**Modified**

- `backend/data_models/order.py` (added `CreateTableRequest`, `UpdateTableRequest`,
  `TableResponse`, and the module-local `_INT4_MAX` constant, this file's first Pydantic schemas)
- `backend/data_models/__init__.py` (exported the three new schemas)
- `backend/exceptions/__init__.py` (added `DuplicateTableNumberError`, `TableInUseError`,
  `TableNotFoundError`; the latter inherits the shared `NotFoundError` base from Story 2.3)
- `backend/container.py` (added `table_service` as a `providers.Factory`)
- `backend/main.py` (appended `"api.tables"` to `container.wire(modules=[...])`)
- `backend/api/router.py` (included the new `tables_router`)
- `frontend/src/pages/admin/TablesSetupPage.tsx` (placeholder replaced with the real Add-table
  form, list, and per-row inline editor)

**Confirmed unchanged**: `backend/data_models/order.py`'s `RestaurantTable`/`Order`/`OrderItem`
ORM classes (no column changes, only new Pydantic schemas added alongside them), no new Alembic
revision, no new package in either manifest, `frontend/src/router.tsx` (the `admin/tables` route
already pointed at `TablesSetupPage`, only its contents changed).

## Change Log

| Date | Change |
|---|---|
| 2026-08-12 | Added `CreateTableRequest`/`UpdateTableRequest`/`TableResponse` to `backend/data_models/order.py`, its first Pydantic schemas, with `_INT4_MAX` bounds applied proactively (Story 2.3's review lesson). |
| 2026-08-12 | Added `DuplicateTableNumberError`/`TableInUseError`/`TableNotFoundError` to `backend/exceptions/__init__.py`; `TableNotFoundError` reuses the shared `NotFoundError` base rather than adding a new near-duplicate handler. |
| 2026-08-12 | Added `TableService` (`backend/services/table_service.py`): `list_tables`, `create_table`, `update_table`. AD-6's guarded-conditional-update pattern extended to `RestaurantTable`, a single `UPDATE ... WHERE status = 'available'` closing both the occupied/reserved rejection (AC4) and the load-then-save race (AC6). Registered as a `providers.Factory` in `container.py`. |
| 2026-08-12 | Found and fixed a real bug while testing the race path: logging `actor.id` after `db.rollback()` raises an unhandled `MissingGreenlet`, since rollback expires the session's objects. Fixed by logging before rolling back. The same latent ordering exists in three other services' `IntegrityError` handlers, never exercised by their tests; recorded in `deferred-work.md` rather than fixed out of scope. |
| 2026-08-12 | Added `GET/POST /api/tables/` and `PATCH /api/tables/{table_id}` (`backend/api/tables.py`), admin-only, with `Path(gt=0, le=_INT4_MAX)` on the id from the start. Mounted in `api/router.py`; appended `"api.tables"` to `main.py`'s `container.wire(modules=[...])`. |
| 2026-08-12 | Added `backend/tests/test_tables.py`: 18 tests covering create/duplicate rejection, edit while available, the occupied/reserved rejection, the AC6 race, rename-to-duplicate, empty-body/nonexistent/int4-boundary validation, and Role gating. Full regression: 209 passed (up from 191). |
| 2026-08-12 | Added `frontend/src/services/tableService.ts` (`useTables`/`useCreateTable`/`useUpdateTable`, `retry: false` from the start) and `frontend/src/types/table.ts`. |
| 2026-08-12 | Replaced `TablesSetupPage`'s placeholder with a real Add-table form and dense-row list (`size="small"`, UX-DR8), each row editable only while available via a controlled, server-resyncing `TableListRow`. The in-use reason renders as both a Tooltip and visible text. No delete affordance anywhere (AC7). |
| 2026-08-12 | Added `frontend/src/pages/admin/TablesSetupPage.test.tsx`: 7 tests, mocking only `fetch`. Confirmed the in-use-reason test fails when its visible-text render is removed, before trusting it. Full frontend regression: 62 passed (up from 55). Production build clean. |
| 2026-08-12 | Code review (three parallel adversarial layers). Blind Hunter confirmed the guarded conditional UPDATE design itself is sound (one request-scoped session, READ COMMITTED, the UPDATE's row lock re-evaluates its WHERE against the latest committed row). 15 patches applied, 1 decision resolved (AC4's live re-enable deferred to Epic 3), 4 deferred, 6 dismissed including one verified false positive (dense-row styling *is* satisfied, via the theme's `MuiTable` `size="small"` default). |
| 2026-08-12 | Review patch: **rewrote the AC6 race test, which previously could not fail.** It was byte-for-byte identical to the AC4 occupied test, so a naive read-then-write passed it. It now patches `TableService.get_table` to seat the table from a second connection *after* the service's read and *before* its write, and additionally asserts the write did not land. Proven: reverting the guard to a read-then-write turns exactly this test red and leaves the other 20 green. |
| 2026-08-12 | Review patch: fixed `create_table` reading `actor.id` after `db.rollback()`, which would 500 instead of 409 on a genuine duplicate-create race, the same bug this story had already fixed in `update_table` forty lines below. Reproduced the mechanism directly (`actor.id` after rollback raises `MissingGreenlet`). Fixed the identical ordering in `MenuService.create_category`, `MenuService.add_recipe_ingredient` and `InventoryService.create_ingredient` in the same pass, clearing the `deferred-work.md` item that recorded them. |
| 2026-08-12 | Review patch: closed the silent partial write. `Number("abc")` is `NaN` and `JSON.stringify` serializes that as `null`, which `UpdateTableRequest` treated as "field omitted", so a typo in one field returned 200 having applied only the other (reproduced: `{"table_number": null, "capacity": 8}` → 200, capacity applied). Both halves fixed: `UpdateTableRequest` now rejects an explicit null, and the frontend validates each field as a positive whole number before sending, disabling Save and showing inline helper text otherwise. |
| 2026-08-12 | Review patch: a no-op edit on an occupied table returned 200, bypassing the status guard (reproduced: body read `'status': 'occupied'`). The early return now re-checks availability under the same filter the guarded UPDATE uses, and rejects with 409. |
| 2026-08-12 | Review patch: `update_table`'s `commit()` moved inside the `IntegrityError` block (a violation surfacing at commit would have escaped as a 500), and its handler no longer logs `table_number=None` on a capacity-only edit. |
| 2026-08-12 | Review patch (frontend): `useUpdateTable` invalidates `onSettled` rather than `onSuccess`, so a 409 refreshes the now-stale row instead of leaving an enabled Save button beside a permanent error; `save()` sends both fields instead of diffing against possibly-stale cache (diffing meant typing the cached value produced no request at all while the row looked saved); the resync effect no longer overwrites text mid-edit; a row leaves edit mode when its table is seated elsewhere; Cancel resets the mutation and is disabled while a save is in flight. |
| 2026-08-12 | Review patch: applied the same mid-edit resync fix to Story 2.3's `RecipeLineRow`, the precedent this story copied, so the shared pattern is correct in both places. |
| 2026-08-12 | Review patch: collection routes moved from `/api/tables/` to `/api/tables`, matching every sibling router and removing the 307 redirect; `_INT4_MAX` imported from `menu.py` instead of being redeclared in `order.py`; the test mock's `/api/tables/1` prefix match tightened to an exact match. |
| 2026-08-12 | Review patch (tests): +3 backend tests (no-op rejected on an occupied table, no-op accepted on an available one, explicit null rejected) and +4 frontend tests (the AC5 row-edit 409 message, invalid input blocking the save, both fields always sent, and leaving edit mode when the table is seated). Final regression: **212 backend, 66 frontend**, production build clean. |
