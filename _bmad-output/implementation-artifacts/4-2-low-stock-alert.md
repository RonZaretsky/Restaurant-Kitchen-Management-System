---
baseline_commit: 5f8dd27ebef9e9f0825a0c167d9e069e2a6570dd
epic: 4
story: 2
---

# Story 4.2: Low-Stock Alert

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Warehouse Manager,
I want to be alerted the instant any stock movement drops an ingredient below its threshold,
so that I can react before it becomes a problem.

## Scope note (read first)

**Low-Stock Alert is explicitly a *derived* state, not a stored entity** (PRD glossary: "an
Ingredient is 'in shortage' whenever its current stock is below its minimum threshold, computed at
read time... rather than persisted as its own entity"). This is the single most important design
decision in this story and it collapses most of the FR-14 acceptance criteria to "satisfied by
construction" rather than something requiring new state-machine code:

- **"At most one active alert per Ingredient-in-shortage"** — trivially true. There is exactly one
  `Ingredient` row per ingredient; a shortage query returns at most one row per ingredient no matter
  how many Stock Movements landed. There is no alert *entity* to duplicate.
- **"Two movements crossing the threshold at nearly the same instant still produce exactly one
  alert, not two"** — also satisfied by construction, for the same reason, *and* independently
  covered by Story 4.1's existing `_lock_ingredient` (`SELECT ... FOR UPDATE`) already serializing
  any two concurrent movements against the same Ingredient row. **No new locking, no new race test
  harness is needed here** — do not build a check-then-insert alert table or any "atomic
  check-and-create" logic; there is nothing to make atomic that isn't already atomic by having no
  alert row to create at all.
- **"The alert clears once a Stock Movement brings the Ingredient back at/above threshold"** — also
  free: the next read of the derived query simply no longer includes that Ingredient. No clear/
  dismiss code path exists or is needed.

**What this story actually builds**, then, is narrower than FR-14's prose might suggest:

1. A backend read endpoint that computes the derived shortage list (`GET /api/inventory/alerts`),
   reusing `IngredientResponse` — no new Pydantic schema, no new ORM entity, no new Alembic
   migration.
2. A **live push** so the Warehouse Manager's nav badge and Alerts screen update within the
   established real-time window without a manual refresh (this is why `sprint-status.yaml`'s
   sequencing note requires Story 1.5 before this one, same as 3.3/5.1/5.2). Broadcasting is
   **crossing-triggered, not every-movement-triggered**: `InventoryService.record_movement` already
   holds the Ingredient's pre-mutation `current_stock` in memory (from `_lock_ingredient`'s read)
   before applying `delta`; broadcast `inventory.alerts_changed` to `UserRole.warehouse_manager`
   only if the shortage boolean (`current_stock < min_stock_threshold`) actually flips in either
   direction across that one movement. A `waste` that keeps an already-in-shortage Ingredient
   further below threshold does **not** re-broadcast — FR-14's own wording is "crosses... below
   threshold" (a transition), not "any decreasing movement while already in shortage." This mirrors
   `table.status_changed`'s existing shape exactly: a plain refetch-signal dict, not a full state
   transfer, so the frontend re-fetches the authoritative list rather than trusting anything in the
   payload.
3. Frontend: replace `AlertsPage.tsx`'s placeholder with real content (loading/error/empty/loaded,
   the empty state reading exactly `"No active shortages"`, UX-DR15), and add a persistent count
   `Badge` on the "Alerts" nav item in `AppShell.tsx`, visible from anywhere in the Warehouse
   Manager's UI, not just the Alerts screen itself (UX-DR5). Both subscribe to the new
   `inventory.alerts_changed` event and invalidate the alerts query on receipt.

**Explicitly out of scope** (Story 4.3's job, not this one — confirmed by reading
`IngredientsPage.tsx`'s own comment, which already reserves this): the shortage badge/red styling
and sort-to-top on the Ingredients list itself, and any shortage banner on `IngredientDetailPage`'s
stat cards. This story touches only the Alerts screen, the nav badge, and the backend endpoint/
broadcast that feed them. Do not add shortage styling to `IngredientsPage.tsx` or
`IngredientDetailPage.tsx`.

**Container wiring trap (trap 23, hit for real in Story 3.3, and it will bite again here exactly
the same way if not handled up front):** `InventoryService` currently takes only `logger` and is
declared **above** `realtime_service` in `backend/container.py` (line ~77 vs ~94). This story adds
a `realtime_service` dependency to `InventoryService`'s constructor, which means
`inventory_service`'s provider declaration **must move below** `realtime_service`'s, exactly the
ordering constraint `order_service` already documents inline in `container.py`. Forgetting this
raises a `NameError` at import time, not a subtle runtime bug — it will fail loudly and immediately,
but do it right the first time rather than rediscovering the trap.

## Acceptance Criteria

1. **Given** a Stock Movement that decreases an Ingredient's current stock (`waste` or a negative
   `adjustment` today; automatic `consumption` once Epic 5 exists) crosses it below its minimum
   threshold, **when** the movement commits, **then** a Low-Stock Alert becomes active for that
   Ingredient (FR-14). *(Implemented as: the Ingredient now appears in `GET /api/inventory/alerts`,
   and `inventory.alerts_changed` is broadcast to `warehouse_manager` connections.)*
2. **Given** an Ingredient already below threshold, **when** another stock-decreasing movement
   lands, **then** no duplicate alert is generated — at most one active alert per
   Ingredient-in-shortage (FR-14). *(Satisfied by construction, see Scope note; still worth an
   explicit test proving the list stays at one row and that no second broadcast fires for a
   movement that doesn't cross.)*
3. **Given** two stock-decreasing movements cross the threshold at nearly the same instant, **when**
   both commit, **then** exactly one active alert results, not two (FR-14, atomic
   check-and-create). *(Satisfied by construction + Story 4.1's existing row lock, see Scope note.)*
4. **Given** a Stock Movement brings the Ingredient back at or above threshold, **when** it commits,
   **then** the alert clears automatically, with no manual dismiss (FR-14).
5. **Given** one or more active Low-Stock Alerts, **when** the Warehouse Manager's UI renders,
   **then** the Alerts nav badge shows a persistent count with no toast (UX-DR5), and the Alerts
   screen lists one Alert row per Ingredient-in-shortage reading `"Stock low: {ingredient}
   ({current stock}{unit} left)"` (UX-DR10).
6. **Given** no active shortages, **when** the Alerts screen loads, **then** it shows `"No active
   shortages"` (UX-DR15).

## Tasks / Subtasks

- [x] **Task 1: Backend — `list_alerts` on `InventoryService`** (AC1-4)
  - [x] Add `async def list_alerts(self, db: AsyncSession) -> Sequence[Ingredient]` to
    `backend/services/inventory_service.py`: `select(Ingredient).where(Ingredient.current_stock <
    Ingredient.min_stock_threshold).order_by(Ingredient.name)`. No actor argument (matches
    `list_ingredients`'s existing precedent — a plain unfiltered-by-user read has nothing to reject
    or audit).
  - [x] Strictly `<`, not `<=`: an Ingredient exactly at threshold is **not** in shortage (matches
    FR-14's "below its minimum threshold" wording literally).
- [x] **Task 2: Backend — `GET /api/inventory/alerts` route** (AC1, AC5, AC6)
  - [x] Add to `backend/api/inventory.py`: `response_model=list[IngredientResponse]`, gated on the
    existing `InventoryReadDep` (admin, warehouse_manager, cook — reuse as-is, no new dependency
    object; matches Story 4.1's own precedent of reusing existing deps whenever they already cover
    the need). Route path `/alerts`, no path params, no new error responses beyond 401/403 (no 404
    possible — an empty list is a valid, successful response, not a not-found).
  - [x] Route ordering: place before or after `/ingredients/{ingredient_id}` freely — no path
    collision (`alerts` vs `ingredients` are different first segments), but keep it visually grouped
    near `list_ingredients` since it's the same read shape.
- [x] **Task 3: Backend — crossing-triggered broadcast in `record_movement`** (AC1, AC4)
  - [x] Inject `realtime_service: RealtimeService` into `InventoryService.__init__`, alongside the
    existing `logger` (mirrors `OrderService`'s constructor shape exactly).
  - [x] In `container.py`: move the `inventory_service` provider declaration to **below**
    `realtime_service`'s (see Scope note's trap-23 warning), and add `realtime_service=realtime_service`
    to its provider args, matching `order_service`'s existing shape verbatim.
  - [x] In `record_movement`, capture `was_low = ingredient.current_stock < ingredient.min_stock_threshold`
    **before** applying `delta` (the row is already locked and loaded via `_lock_ingredient`, no
    extra query needed). After applying `delta` and committing, compute
    `is_low = ingredient.current_stock < ingredient.min_stock_threshold` on the refreshed value. If
    `was_low != is_low`, broadcast `inventory.alerts_changed` to `[UserRole.warehouse_manager]` with
    payload `{"ingredient_id": ingredient_id}` (a refetch signal, not a state transfer — matches
    `table.status_changed`'s established shape exactly, see Scope note). Broadcast only after
    `db.commit()` succeeds, same ordering `open_table`/`add_item` already established.
  - [x] Log the crossing at `INFO` when it fires in either direction (e.g. "Low-stock alert
    activated" / "Low-stock alert cleared"), giving `ingredient_id`, `current_stock`, and
    `min_stock_threshold` — matches this codebase's "identifying context in every log line" rule.
- [x] **Task 4: Backend tests** (`backend/tests/test_inventory.py`)
  - [x] `GET /api/inventory/alerts` returns an empty list when nothing is in shortage.
  - [x] A `waste` movement that crosses an Ingredient below threshold makes it appear in `/alerts`.
  - [x] A negative `adjustment` that crosses below threshold makes it appear in `/alerts`.
  - [x] An Ingredient exactly at threshold (not below) is excluded from `/alerts` (the strict-`<`
    boundary, AC1's literal wording).
  - [x] A second `waste` movement on an Ingredient already below threshold: `/alerts` still returns
    exactly one row for that Ingredient (AC2/AC3, "satisfied by construction" made concrete).
  - [x] A `purchase` that brings an in-shortage Ingredient back to or above threshold removes it from
    `/alerts` (AC4). Also test the boundary: landing exactly *at* threshold clears it (since AC1's
    shortage condition is strict `<`).
  - [x] Role coverage on `GET /alerts`: warehouse_manager, admin, and cook can each read it; waiter
    is rejected 403; unauthenticated is rejected 401 (mirrors 4.1's own `InventoryReadDep` test
    shape).
  - [x] Broadcast test in `backend/tests/test_websocket.py` (new, mirrors
    `test_opening_a_table_broadcasts_table_status_changed`'s exact shape): a `waste` movement that
    crosses an Ingredient below threshold broadcasts `inventory.alerts_changed` with
    `{"ingredient_id": ...}` to a connected `warehouse_manager` socket; a connected `cook` socket
    (also permitted to read `/alerts` via `InventoryReadDep`, but not a UI consumer of it, see Scope
    note) receives nothing — the role-exclusion assertion Story 3.3's review made standard for every
    new broadcast.
  - [x] Negative broadcast test: a `purchase` movement that does **not** cross the threshold (an
    Ingredient nowhere near shortage) sends nothing over the socket within the test's timeout window.
  - [x] Negative broadcast test: a second `waste` movement on an Ingredient already below threshold
    (no crossing, already in shortage) sends nothing — proving the crossing-only design from Task 3,
    not "every decreasing movement."
- [x] **Task 5: Frontend — types and service hook** (AC1, AC4-6)
  - [x] `frontend/src/services/inventoryService.ts`: add `useAlerts(): UseQueryResult<Ingredient[],
    Error>` (`GET /api/inventory/alerts`, `retry: false`, matches every other query hook's shape).
    Export `ALERTS_QUERY_KEY` as a module constant (mirrors `DISHES_QUERY_KEY`/`TABLES_QUERY_KEY`'s
    cross-file-export precedent), since both `AppShell.tsx` (badge) and `AlertsPage.tsx` (list) need
    to invalidate the same key from their own WebSocket subscriptions.
  - [x] No new frontend type needed: `Ingredient` (already in `frontend/src/types/inventory.ts`)
    is reused as-is.
- [x] **Task 6: Frontend — live subscription and nav badge** (AC5)
  - [x] In `AppShell.tsx`, when `user.role === "warehouse_manager"`, call `useAlerts()` and
    subscribe (via `useRealtime().subscribe`) to `inventory.alerts_changed`, invalidating
    `ALERTS_QUERY_KEY` on receipt (mirrors `TablesPage.tsx`'s existing `table.status_changed`
    subscriber shape). Wrap the "Alerts" `NavItem` specifically in a MUI `Badge` showing
    `alerts.length`; hide the badge entirely at zero (`invisible` prop or conditional render,
    matching the mockup comment's "nav badge hidden/zeroed" empty-state note) rather than rendering
    a visible "0".
  - [x] Keep this narrowly scoped to the one nav item that needs a badge today (`"/warehouse/alerts"`)
    rather than building a generic per-path badge-lookup map — no second nav badge exists yet in this
    codebase to justify the abstraction (the Waiter "tables needing attention" counter mentioned in
    the UX spec is not part of this story and is not built anywhere yet).
- [x] **Task 7: Frontend — `AlertsPage.tsx` real content** (AC5, AC6)
  - [x] Replace the placeholder with `useAlerts()`-driven content: loading, error (with Retry, `isError`
    excluding nothing since there's no legitimate 404 state here), empty (`"No active shortages"`,
    exact copy per UX-DR15), and loaded (one row per Ingredient, reading `"Stock low: {name}
    ({current_stock}{unit} left)"`, per UX-DR10's literal template).
  - [x] Also subscribe to `inventory.alerts_changed` here (same as Task 6's AppShell subscription;
    two independent subscribers to the same event is fine and matches this codebase's established
    "invalidate on receipt, not a shared subscription object" pattern — `TablesPage.tsx` and
    `TableOrderDetailPage.tsx` already both subscribe to their own overlapping-relevance events
    independently).
  - [x] Each Alert row is clickable and navigates to `/warehouse/ingredients/{ingredient_id}`
    (`useNavigate`, matches EXPERIENCE.md's "Click opens Ingredient detail to log the resolving
    movement").
  - [x] No dismiss control anywhere on the row (EXPERIENCE.md: "carries no dismiss control of its
    own; it drops off the list only when a Stock Movement brings that Ingredient back at or above
    threshold").
- [x] **Task 8: Frontend tests**
  - [x] `AlertsPage.test.tsx` (new): loading, error+Retry, empty state exact copy, loaded state row
    text exact format, row click navigates to the right Ingredient detail route, live update on a
    stubbed `inventory.alerts_changed` message (mirrors `TablesPage.test.tsx`'s `FakeWebSocket`
    pattern — reuse the existing copy-per-test-file precedent, do not extract a shared module per
    this codebase's own deferred-work note on that).
  - [x] Nav badge coverage (extend or create `AppShell.test.tsx`, none exists yet): badge shows the
    correct count for a warehouse_manager with active alerts, is hidden/absent at zero, is absent
    entirely for every other Role (no Alerts nav item exists for admin/waiter/cook at all, so there's
    nothing to badge — confirm via `navigationConfig.ts`, not a new rule).
- [x] **Task 9: Full regression pass**
  - [x] `uv run pytest -q` (backend) — zero regressions.
  - [x] `pnpm test` (frontend) — zero regressions.
  - [x] `npx tsc -b` — clean.

## Dev Notes

### Architecture compliance

- **AD-2** (`{domain}.{event}` naming, emitted exactly once by the service owning the mutation):
  `inventory.alerts_changed`, emitted from `InventoryService.record_movement` only — the one place
  `current_stock` is mutated today (Epic 5's future automatic `consumption` path will need to repeat
  this same crossing-check when it lands in `OrderService`, since that's a different service/method
  entirely; this story does not and cannot build that half yet, no `in_preparation` transition exists
  to trigger it).
- **FR-14 / "derived state, not stored"**: see Scope note. This is the load-bearing design decision
  for the whole story — do not introduce a `LowStockAlert` ORM model or table.
- **NFR-4** (auditability): unaffected — this story reads `current_stock`/`min_stock_threshold`,
  never writes them; the audit trail obligation was already fully satisfied by Story 4.1's
  `record_movement`.
- **AD-16** (`current_stock` never floor-capped at zero): unaffected — the shortage comparison
  (`current_stock < min_stock_threshold`) works identically whether `current_stock` is positive,
  zero, or negative; a deeply negative `current_stock` is still (correctly) "in shortage."
- **Role-level-only permissions** (no per-resource filtering anywhere in this codebase):
  `GET /api/inventory/alerts` returns the same list to every Role permitted to call it — no
  per-Warehouse-Manager scoping exists or is needed, there is exactly one shared inventory, matching
  every other list endpoint in this project.
- **Trap 23** (container provider declaration order): see Scope note — `inventory_service` must move
  below `realtime_service` in `container.py`.

### Current state of the files this story touches (read before editing)

- **`backend/services/inventory_service.py`**: currently `list_ingredients`, `create_ingredient`,
  `get_ingredient`, `list_movements`, `record_movement`, `_get_ingredient`, `_lock_ingredient`
  (Story 4.1). Constructor currently takes only `logger`. This story adds `list_alerts` and a
  `realtime_service` constructor argument, and extends `record_movement`'s body (crossing check +
  broadcast) — everything else in the file is unchanged.
- **`backend/api/inventory.py`**: currently 5 routes (`GET`/`POST /ingredients`,
  `GET /ingredients/{id}`, `GET /ingredients/{id}/movements`, `POST /ingredients/{id}/movements`).
  This story adds one more: `GET /alerts`. `InventoryReadDep` is reused unchanged.
- **`backend/container.py`**: `inventory_service` provider currently declared above
  `realtime_service` (must move below, see Scope note); `order_service`'s existing inline comment at
  that spot already documents the exact constraint this story must also follow.
- **`frontend/src/pages/warehouse/AlertsPage.tsx`**: currently a bare one-line `Typography`
  placeholder, already imported and routed in `router.tsx` at `/warehouse/alerts` (confirmed:
  `router.tsx:14,44`; do not touch `router.tsx`, the route already exists). This story gives it real
  content for the first time, the same "route/placeholder before the story that fills it" shape
  Story 4.1 used for `IngredientDetailPage.tsx`.
- **`frontend/src/components/shell/AppShell.tsx`**: currently renders `ROLE_NAV_ITEMS[user.role]` as
  a flat list of `NavItem`s with no badges anywhere. No `useRealtime()`/`useAlerts()` calls exist
  here yet. This story adds both, scoped to `warehouse_manager` only.
  `frontend/src/components/shell/navigationConfig.ts` already has the "Alerts" nav entry
  (`warehouse_manager` only, confirmed via direct read) — do not add a new nav entry, only badge the
  existing one.
- **`frontend/src/services/inventoryService.ts`**: currently exports `useIngredients`,
  `useCreateIngredient`, `useIngredient`, `useStockMovements`, `useRecordStockMovement`. This story
  adds `useAlerts` and exports `ALERTS_QUERY_KEY`.
- **`frontend/src/types/inventory.ts`**: unchanged — `Ingredient` already has every field
  `useAlerts()`'s consumers need (`name`, `current_stock`, `min_stock_threshold`, `unit`).

### Project Structure Notes

Files touched:
- `backend/services/inventory_service.py` — **UPDATE**, `list_alerts` added, `record_movement`
  extended, constructor gains `realtime_service`.
- `backend/api/inventory.py` — **UPDATE**, `GET /alerts` route added.
- `backend/container.py` — **UPDATE**, `inventory_service` provider moved below `realtime_service`,
  `realtime_service` arg added.
- `backend/tests/test_inventory.py` — **UPDATE**, new tests per Task 4.
- `backend/tests/test_websocket.py` — **UPDATE**, new broadcast tests per Task 4.
- `frontend/src/services/inventoryService.ts` — **UPDATE**, `useAlerts`, `ALERTS_QUERY_KEY` added.
- `frontend/src/components/shell/AppShell.tsx` — **UPDATE**, nav badge + live subscription.
- `frontend/src/components/shell/AppShell.test.tsx` — **NEW** (none exists today).
- `frontend/src/pages/warehouse/AlertsPage.tsx` — **UPDATE**, placeholder replaced.
- `frontend/src/pages/warehouse/AlertsPage.test.tsx` — **NEW**.

No new Alembic migration (no schema change — the alert is derived from existing `Ingredient`
columns), no new frontend route (`router.tsx` already has `/warehouse/alerts`), no change to
`IngredientsPage.tsx`/`IngredientDetailPage.tsx` (Story 4.3's job), no new Pydantic response schema
(`IngredientResponse` reused as-is).

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 4.2`, lines 780-810] — this story's AC
  source, read alongside Story 4.1 (760-778) and 4.3 (812-834) to confirm scope boundaries on both
  sides.
- [Source: `_bmad-output/planning-artifacts/prds/prd-.../prd.md#FR-14`, lines 257-263, and the
  glossary's "Low-Stock Alert" entry, line 98] — the "derived state, not a stored record" framing
  this story's whole design rests on, and FR-14's exact testable consequences.
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../EXPERIENCE.md`, Component Patterns
  ("Alert row", "Nav badge, Alerts") and `.memlog.md` line 14] — the exact row copy template
  (UX-DR10), the "persistent count, no toast, visible from anywhere in her role's UI" nav badge
  behavior (UX-DR5), and the empty-state copy (UX-DR15).
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../mockups/key-alerts.html`] — confirms the
  empty-state treatment (plain line, no celebratory copy, badge hidden/zeroed) and the alert-row
  visual token (reuses the same red as `status-badge.cancelled`, per DESIGN.md line 129).
  `key-alerts.html`'s address bar is the source for `/warehouse/alerts` already existing.
- [Source: `backend/services/inventory_service.py::record_movement`/`_lock_ingredient`, Story 4.1]
  — the existing `SELECT ... FOR UPDATE` row lock this story's crossing-detection reuses at zero
  extra query cost (the pre-mutation `current_stock` is already in memory from that lock's read).
- [Source: `backend/services/order_service.py::open_table`, `backend/container.py` lines ~94-110] —
  the exact `RealtimeService` injection shape (constructor arg, broadcast-after-commit ordering,
  plain-refetch-signal payload) this story's `record_movement` extension mirrors, and the container
  provider-ordering constraint (trap 23) that must be repeated here.
- [Source: `backend/tests/test_websocket.py::test_opening_a_table_broadcasts_table_status_changed`]
  — the exact test shape (two connected sockets, one in-role one out-of-role, `asyncio.wait_for`
  with a 2s timeout for the positive assertion and a short timeout + `pytest.raises(TimeoutError)`
  for the negative/role-exclusion assertion) Task 4's new broadcast tests must mirror.
- [Source: `frontend/src/pages/waiter/TablesPage.tsx`, `TablesPage.test.tsx`] — the
  `useRealtime().subscribe(event, handler)` + `invalidateQueries` shape Task 6/7 both mirror, and
  the `FakeWebSocket` test-double pattern (already duplicated across three test files per
  `deferred-work.md`; continue the existing per-file-copy precedent rather than extracting a shared
  module now, unless this becomes the fourth consumer and someone wants to revisit that call).
  `TABLES_QUERY_KEY`'s cross-service export precedent is what `ALERTS_QUERY_KEY` follows.
  `frontend/src/pages/warehouse/IngredientsPage.tsx`'s own in-file comment ("that scope belongs to
  Epic 4's Story 4.3") is independent confirmation that shortage styling on that screen is out of
  this story's scope.
  `frontend/src/pages/warehouse/IngredientDetailPage.tsx`'s docstring similarly confirms it
  "deliberately excludes the shortage banner" as Story 4.2/4.3 territory — the "banner on stat
  cards" half is 4.3's, not this story's; this story's own surface is the dedicated Alerts screen,
  not a banner embedded elsewhere.
- [Source: `_bmad-output/project-context.md`, trap 23, "Domain rules worth restating" (Low-Stock
  Alert bullet), Testing section] — the container-ordering trap this story repeats, the pre-existing
  restatement of FR-14's derived-state rule, and the "role-exclusion assertion is now standard for
  every new broadcast" rule (Story 3.3's review).

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5

### Debug Log References

- `uv run pytest tests/test_inventory.py -q -k "alert"` — 10 passed
- `uv run pytest tests/test_inventory.py -q` — 53 passed
- `uv run pytest tests/test_websocket.py -q -k "inventory_alerts_changed or shortage or threshold"` — 3 passed
- `uv run pytest tests/test_websocket.py -q` — 17 passed
- `uv run pytest -q` (full backend suite) — 310 passed, 21 warnings, no regressions; re-run after
  the review patch pass — 311 passed, 22 warnings, no regressions
- `pnpm vitest run src/pages/warehouse/AlertsPage.test.tsx` — 5 passed
- `pnpm vitest run src/components/shell/AppShell.test.tsx` — 4 passed
- `pnpm test` (full frontend suite) — 162 passed
- `npx tsc -b` — clean

### Completion Notes List

- Low-Stock Alert is a derived state, not a stored entity (PRD glossary). `InventoryService.list_alerts`
  is a plain `SELECT ... WHERE current_stock < min_stock_threshold`, strictly `<`. AC2/AC3
  ("no duplicate alert", "atomic check-and-create") required no new code: there is exactly one
  `Ingredient` row per ingredient, so there is structurally nothing to duplicate, and Story 4.1's
  pre-existing `_lock_ingredient` (`SELECT ... FOR UPDATE`) already serializes any two concurrent
  movements on the same Ingredient. No `LowStockAlert` table, no check-then-insert race, no new lock.
- Broadcast is crossing-triggered, not every-movement-triggered: `record_movement` captures
  `was_low` from the already-locked, already-in-memory `current_stock` before applying `delta`, and
  compares against `is_low` after commit. Only broadcasts `inventory.alerts_changed` to
  `warehouse_manager` when the boolean flips, matching FR-14's literal "crosses... below threshold"
  wording rather than firing on every decreasing movement while already in shortage. Verified with
  two dedicated negative-broadcast tests (no crossing; already-in-shortage, still below).
  Payload is a plain `{"ingredient_id": ...}` refetch signal, not a state transfer, mirroring
  `table.status_changed`'s established shape.
- Hit the exact trap-23 container-ordering issue the story's own Scope note called out in advance:
  `InventoryService` now takes `realtime_service`, so its provider had to move below
  `realtime_service`'s declaration in `container.py` (previously it sat above, needing only
  `logger`). Caught before it could fail, not rediscovered at import time.
- `GET /api/inventory/alerts` reuses `IngredientResponse` as-is — no new Pydantic schema, no new
  ORM entity, no new Alembic migration (confirmed no schema change was needed).
- Frontend: `AppShell.tsx`'s `useAlerts()` call is gated with an `enabled` param
  (`useAlerts(isWarehouseManager)`) so every non-warehouse_manager Role's shell render does not
  fire a doomed 403 request — hooks can't be called conditionally, so the query itself is
  conditionally enabled instead. `AlertsPage.tsx` (reachable only by a warehouse_manager via the
  route guard) omits the param and always fetches.
- Nav badge scoped narrowly to the one path that needs it (`/warehouse/alerts`) via a direct
  string comparison in the nav-items map, rather than a generic per-path badge-lookup — no second
  nav badge exists anywhere in this codebase yet to justify that abstraction.
- Two independent WebSocket subscriptions to the same `inventory.alerts_changed` event
  (`AppShell.tsx` for the badge, `AlertsPage.tsx` for the list), matching this codebase's
  established "invalidate on receipt per-consumer" pattern rather than a shared subscription
  object — `TablesPage.tsx`/`TableOrderDetailPage.tsx` already set this precedent for overlapping
  event relevance.
- `FakeWebSocket` copied into a third and fourth test file (`AlertsPage.test.tsx`,
  `AppShell.test.tsx`), continuing the existing per-file-copy precedent rather than extracting a
  shared module now (already flagged in `deferred-work.md` from Story 3.3's review as a "revisit
  if a fourth consumer appears" item — it just did; left as a call for the reviewing session).

### File List

- `backend/services/inventory_service.py`
- `backend/api/inventory.py`
- `backend/container.py`
- `backend/tests/test_inventory.py`
- `backend/tests/test_websocket.py`
- `frontend/src/services/inventoryService.ts`
- `frontend/src/components/shell/AppShell.tsx`
- `frontend/src/components/shell/AppShell.test.tsx`
- `frontend/src/pages/warehouse/AlertsPage.tsx`
- `frontend/src/pages/warehouse/AlertsPage.test.tsx`

## Review Findings

Reviewed by three parallel agents (Blind Hunter, Edge Case Hunter, Acceptance Auditor) against this
story's 6 ACs and `_bmad-output/project-context.md`. The Acceptance Auditor independently re-ran the
full test suite live and confirmed every test-count claim in this file numerically — no repeat of
the count-inaccuracy mistake a prior story's review caught.

**Fixed during this review:**

- **Missing symmetric negative-broadcast test** (Blind Hunter) — the suite covered "already in
  shortage, another *decreasing* movement, no re-broadcast" but not the mirror case, "already in
  shortage, a *purchase* that reduces the shortage without crossing back above threshold, no
  re-broadcast." Added `test_a_purchase_that_reduces_but_does_not_clear_a_shortage_broadcasts_nothing`
  to `backend/tests/test_websocket.py`.
- **Docstring imprecision on the crossing check's cost** (Blind Hunter) — `record_movement`'s
  docstring claimed the whole crossing check "costs no extra query," true only for `was_low`
  (read for free from the already-locked row); `is_low` still requires the `db.refresh()` this
  method already performs for its own return value. Tightened to say so explicitly.

**Verified as non-issues:**

- **"Badge hidden at zero" test rides on an MUI implementation detail"** (Blind Hunter) — checked
  directly: a minimal `Badge badgeContent={0} invisible={true}` render genuinely removes "0" from
  what `screen.queryByText` can find (confirmed via an ad hoc render), so `AppShell.test.tsx`'s
  assertion is testing real, queryable DOM absence, not a fragile internal.
- **Broadcast payload field name `ingredient_id` vs. the domain's plain `id` convention**
  (Blind Hunter) — checked against the actual precedent: `table.status_changed`'s payload (Story
  3.3) uses `table_id`, not `id`, for exactly this "plain refetch-signal dict" shape.
  `ingredient_id` matches that established convention exactly; the finding compared against the
  wrong precedent (`order.item_added`'s full-state-transfer payload, which legitimately does use
  bare `id`).
- **"Cook can read `/alerts` but isn't a UI consumer" framing implies false protection**
  (Blind Hunter) — re-read: the story never claims this is enforcement, only that no Cook-facing
  screen exists yet to wire the read into (the same ahead-of-UI framing used for the Cook/Admin
  cancel grant in Story 3.4, already an established, precedented pattern in this codebase).
- **AC2/AC3 "satisfied by construction" claim** (Acceptance Auditor) — independently re-verified by
  reading the schema and lock code directly, not just trusting the story's prose: one `Ingredient`
  row per ingredient means there is structurally nothing to duplicate, and `_lock_ingredient`'s
  pre-existing `SELECT ... FOR UPDATE` (Story 4.1) genuinely serializes concurrent movements on the
  same row.
- **Container wiring (trap 23)** (Acceptance Auditor) — confirmed `inventory_service` is correctly
  declared after `realtime_service`, with `realtime_service` passed as a constructor arg.
- A mid-review anomaly where `git stash list` briefly showed an unexpected WIP entry (Blind Hunter)
  was investigated immediately and confirmed to be a sandbox artifact of a concurrently-running
  backgrounded test command, not data loss — `git status`/`git diff` were unaffected and matched
  what was reviewed.

**Deferred (non-blocking, see `deferred-work.md`):** `FakeWebSocket` duplicated a 4th time (past
Story 3.3's own "extract at 4" threshold); no visible fallback on the Alerts nav badge if `useAlerts`
itself fails; no index backing the shortage comparison (matches this codebase's other
accepted-at-current-scale gaps); no test proving `AppShell`'s and `AlertsPage`'s independent
`inventory.alerts_changed` subscriptions actually de-dupe into one network request.

## Change Log

| Date | Change |
|---|---|
| 2026-08-16 | Implemented Story 4.2: Low-Stock Alert as a derived state (no new entity/migration). Backend: `InventoryService.list_alerts`, `GET /api/inventory/alerts`, crossing-triggered `inventory.alerts_changed` broadcast from `record_movement`. Frontend: real `AlertsPage.tsx` content, persistent Alerts nav badge + live subscription in `AppShell.tsx`. 14 new backend tests (310 total), 9 new frontend tests (162 total). |
| 2026-08-16 | Code review patch pass: added the missing symmetric negative-broadcast test (a purchase that reduces but doesn't clear an existing shortage); tightened `record_movement`'s docstring on exactly which part of the crossing check is and isn't a free read. 1 new regression test added (311 backend total). |
