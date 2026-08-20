---
baseline_commit: 411363ea0bbde8c7d9608e88964b34769ed1ec53
epic: 5
story: 5
---

# Story 5.5: Live-Update the Kitchen Display and Waiter Screen on Cancel/Edit

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Cook or Waiter,
I want a cancelled or edited Order Item to update my screen live,
so that I never act on a stale item after someone else has already changed it.

## Scope note (read first)

**This story exists because of a Sprint Change Proposal** (`_bmad-output/planning-artifacts/
sprint-change-proposal-2026-08-16.md`), not a fresh PRD requirement. Manual testing of Story 5.2
found that cancelling an Order Item never updated an already-open Kitchen Display — root cause,
confirmed by reading the code: `OrderService.cancel_item` (Story 3.4) and `OrderService.edit_item`
(Story 3.4) never call `realtime_service.broadcast(...)`. That was correct **at the time** — no
live-consuming screen existed yet for either method to reach. Story 5.1/5.2 then made the Kitchen
Display a live, always-foregrounded second consumer of Order Item state, and added the
`order.item_status_changed` broadcast for pick-up/mark-ready — but nobody revisited cancel/edit's
silence once that second live consumer existed. **This closes a gap against already-approved
NFR-1** ("An Order Item status change... is visible on the relevant other Role's screen... within
2 seconds, with no manual refresh required"), it is not new scope.

**This is the smallest story in the project so far, by design.** The fix is two `broadcast()`
calls added to two already-existing, already-guarded, already-tested methods — reusing the exact
event name, payload shape, and recipient list `pick_up_item`/`mark_item_ready` (Story 5.2)
already established for `order.item_status_changed`. **No new event name. No new endpoint. No
schema change. No migration. No frontend code changes at all** — confirmed by reading both
consumers: `KitchenDisplayPage.tsx` (`~line 121`) and `TableOrderDetailPage.tsx` (`~line 462`)
already subscribe to `order.item_status_changed` generically and just invalidate-and-refetch on
receipt, regardless of which backend transition triggered it. Do not add anything beyond the two
broadcast calls and their tests — there is no hidden frontend gap here, the Sprint Change
Proposal's own Impact Analysis confirmed this by reading the actual subscriber code, not by
assumption.

**Where exactly the two calls go, mirroring `mark_item_ready`'s own placement (`order_service.py`,
current lines ~571-584) exactly:**

- `edit_item` (current lines ~326-352): after `await db.refresh(item)`, add
  `await self._realtime_service.broadcast([UserRole.waiter, UserRole.cook],
  "order.item_status_changed", OrderItemResponse.model_validate(item).model_dump(mode="json"))`.
  Unconditional — `edit_item` never changes `.status` (only `quantity`/`notes`), so there is no
  `order_status_changed` branch to add here, unlike `cancel_item`/`pick_up_item`/`mark_item_ready`.
  Do not call `_recompute_order_status` from `edit_item` — Story 5.3's own Scope note already
  established `edit_item` is the one item-mutating method that never touches the aggregate,
  because it never changes an item's status; that reasoning is unchanged by this story.
- `cancel_item` (current lines ~354-410): the method already calls `_recompute_order_status` and
  conditionally broadcasts `order.status_changed` (Story 5.3). Add the new
  `order.item_status_changed` broadcast **unconditionally**, placed after `await db.refresh(item)`
  and **before** the existing `if order_status_changed:` block — matching every other method's
  established ordering (the item-level event is the primary signal, the order-level one is a
  secondary, conditional follow-up, per Story 5.3's own Task 3 note).

**The event's own "reflects within 2 seconds" AC is already proven generically** — Story 1.5 has a
dedicated `test_broadcast_delivered_within_two_seconds` covering the transport itself, and Story
5.2's own broadcast tests already prove the same event/payload/recipients round-trips correctly
for pick-up/mark-ready. This story's own tests only need to prove the **two new call sites** fire
it, not re-prove the transport or the timing.

**One existing test must be updated, not just extended** — flagged by name in `deferred-work.md`'s
own story-3-4 entry as anticipating exactly this: `test_websocket.py::
test_cancelling_one_of_several_pending_items_broadcasts_nothing` currently asserts a connected
Waiter receives **nothing at all** after a cancel that leaves the Order's aggregate status
unchanged (two pending items, cancel one, aggregate stays `in_preparation` both before and after —
the no-op-recompute case Story 5.3 added this test for). Once `cancel_item` broadcasts
`order.item_status_changed` unconditionally, that assertion becomes **false**: the Waiter now
correctly receives `order.item_status_changed` (the item was cancelled, that is a real event) but
still correctly does **not** receive `order.status_changed` (the aggregate genuinely did not
change). Rewrite this test's assertions to match — receive-then-timeout, not
timeout-immediately — following `test_marking_the_only_item_ready_broadcasts_order_status_changed_
to_waiter_only`'s own two-events-then-nothing-more shape. Do not delete this test or its
No-op-order-status-changed coverage; only its top-level "broadcasts nothing" claim is now wrong.

## Acceptance Criteria

1. **Given** a pending or in_preparation Order Item is cancelled, **when** the cancellation
   commits, **then** the same `order.item_status_changed` event Story 5.2 introduced is broadcast
   to [waiter, cook], and both the Kitchen Display and the Waiter's own Table/Order Detail page
   reflect the cancellation within 2 seconds, with no manual refresh (NFR-1).
2. **Given** a pending Order Item's quantity or note is edited, **when** the edit commits, **then**
   the same event is broadcast, and both screens reflect the change within 2 seconds, with no
   manual refresh (NFR-1).
3. **Given** a Kitchen Display that has stayed foregrounded for an extended period, **when**
   another Role cancels or edits an item shown on it, **then** the display updates without
   requiring a tab switch, window refocus, or manual reload.

## Tasks / Subtasks

- [x] **Task 1: Backend — `edit_item` broadcasts `order.item_status_changed`** (AC2)
  - [x] `backend/services/order_service.py`: after `await db.refresh(item)`, add
    `await self._realtime_service.broadcast([UserRole.waiter, UserRole.cook],
    "order.item_status_changed", OrderItemResponse.model_validate(item).model_dump(mode="json"))`
    — unconditional, no `order_status_changed` branch (edit never changes `.status`).
  - [x] Update the method's own docstring: remove "No live broadcast, this story's own ACs never
    say 'live' for edit/cancel..." (that was Story 3.4's own accurate note at the time; this story
    is exactly the one that changes it) and state the new broadcast instead, matching
    `mark_item_ready`'s own docstring style.

- [x] **Task 2: Backend — `cancel_item` broadcasts `order.item_status_changed`** (AC1)
  - [x] Same file: after `await db.refresh(item)` and before the existing
    `if order_status_changed:` block, add the identical broadcast call (unconditional), matching
    `mark_item_ready`'s exact ordering (item-level event first, order-level conditional follow-up
    second).
  - [x] Update the method's docstring the same way as Task 1.

- [x] **Task 3: Backend tests** (`backend/tests/test_orders.py`, extend existing file — reuse
  existing helpers, follow this file's established `test_*` naming)
  - [x] `edit_item` broadcast content/recipients (AC2): a connected Waiter and a connected Cook
    both receive `order.item_status_changed` after an edit, payload matches the edited item
    (quantity/notes reflect the submitted values), matching `test_marking_an_in_preparation_item_
    ready_is_a_pure_status_change`'s own "assert payload content" shape but for the WebSocket
    event rather than the HTTP response (extend `test_websocket.py` if that is where this file's
    sibling broadcast-content tests already live — check `pick_up_item`'s own broadcast-content
    test's location first, mirror it exactly rather than picking a new location).
  - [x] `cancel_item` broadcast content/recipients (AC1): a connected Waiter and a connected Cook
    both receive `order.item_status_changed` after a cancel, payload status is `cancelled`.
  - [x] **Rewrite** `test_websocket.py::test_cancelling_one_of_several_pending_items_broadcasts_
    nothing` per the Scope note above: assert the Waiter now receives `order.item_status_changed`
    first (payload status `cancelled`), then times out waiting for anything further (no
    `order.status_changed`, since the aggregate is unchanged) — do not just delete or weaken this
    test, its no-op-order-status-changed coverage is still real and still needed.
  - [x] Role coverage: confirm this story adds no new route/permission surface (cancel/edit's
    existing role gates — waiter-only for edit, waiter/cook/admin for cancel — are unchanged), so
    no new role-coverage tests are needed beyond what Tasks above already assert for waiter/cook
    recipients.

- [x] **Task 4: Full regression pass**
  - [x] `uv run pytest -q` (backend) — zero regressions.
  - [x] `pnpm test` (frontend) — zero regressions (no frontend files are touched by this story;
    this run is to confirm that remains true, not because any change is expected).
  - [x] `npx tsc -b` — clean.

## Dev Notes

### Architecture compliance

- **AD-2** (one WebSocket endpoint, Role-scoped, each event emitted exactly once by the service
  that owns the mutation): both new broadcasts are `order.item_status_changed`, already owned by
  `OrderService`, emitted from the same service method that performs the mutation — no new event
  name, no second producer for an existing event.
- **NFR-1** (live visibility within 2 seconds, no manual refresh) is the literal requirement this
  story completes for the `cancel`/`edit` transitions specifically; `pick_up`/`mark_item_ready`
  already satisfied it (Story 5.2), `add_item`/`open_table` already satisfied it (Story 3.3).

### Current state of the files this story touches (read before editing)

- **`backend/services/order_service.py`**: `edit_item` (~297-352) and `cancel_item` (~354-410)
  are the two methods this story changes — both already exist, already guarded (AD-6), already
  tested for their HTTP-level behavior; this story only adds a broadcast call to each, no change
  to either method's guard logic, status transition, or response shape. `pick_up_item` (~412-...)
  and `mark_item_ready` (~530-588) are the two existing call sites already broadcasting
  `order.item_status_changed` — read `mark_item_ready`'s exact placement (after
  `db.refresh(item)`, before its own `order_status_changed` conditional) as the literal template
  for `cancel_item`'s new call; `edit_item` has no `order_status_changed` branch to place around.
- **`frontend/src/pages/cook/KitchenDisplayPage.tsx`** (~line 121) and **`frontend/src/pages/
  waiter/TableOrderDetailPage.tsx`** (~line 462): both already subscribe to
  `order.item_status_changed` generically (invalidate-and-refetch, no payload inspection beyond
  triggering a refetch) — confirmed by reading both files for this story's Scope note. **No
  frontend file needs to change.** If a dev agent finds itself editing either of these two files,
  stop and re-read this Scope note — that is a sign of scope creep, not a requirement.
- **`backend/tests/test_websocket.py`**: `test_marking_an_order_served_broadcasts_order_status_
  changed_to_waiter_only` (or wherever `mark_item_ready`'s own `order.item_status_changed`
  broadcast-content test lives, check via a search for `OrderItemResponse.model_validate` near a
  `pick-up`/`mark-ready` WebSocket test) is the exact template for the two new tests Task 3 asks
  for. `test_cancelling_one_of_several_pending_items_broadcasts_nothing` (current, ~line 757) is
  the one existing test whose assertion this story makes false — see the Scope note for the exact
  rewrite needed.

### Project Structure Notes

Files touched:
- `backend/services/order_service.py` — **UPDATE**, two new broadcast calls (`edit_item`,
  `cancel_item`), no new methods, no new imports needed (`OrderItemResponse`, `UserRole` already
  imported).
- `backend/tests/test_orders.py` and/or `backend/tests/test_websocket.py` — **UPDATE**, new
  broadcast-content coverage for both methods (place wherever this file's existing
  `pick_up_item`/`mark_item_ready` broadcast-content tests already live, to keep sibling coverage
  together), plus the required rewrite of the now-false no-broadcast test.

No new Alembic migration. No new frontend route or component. No new exception type. No new API
route. This is the smallest-blast-radius story in the project: two `broadcast()` calls, reusing an
already-proven event/payload/transport, closing a gap the code correctly deferred at the time it
was written.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 5.5`] — this story's AC source,
  verbatim.
- [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-08-16.md`] — the full
  root-cause analysis, impact analysis, and the explicit confirmation (Section 2, "Technical
  impact") that no frontend change is needed, this story's own Scope note is drawn directly from
  it.
- [Source: `_bmad-output/planning-artifacts/epics.md`, NFR-1] — the already-approved requirement
  this story completes, not a new one.
- [Source: `backend/services/order_service.py::pick_up_item`, `::mark_item_ready`] — the existing,
  already-tested `order.item_status_changed` broadcast pattern this story copies verbatim to two
  more call sites.
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md`, "Deferred from: code review
  of story-3-4"] — the entry that explicitly anticipated this story and named the exact test
  (`test_cancelling_one_of_several_pending_items_broadcasts_nothing`, added later by Story 5.3)
  that would need rewriting once it landed.
- [Source: `frontend/src/pages/cook/KitchenDisplayPage.tsx`, `frontend/src/pages/waiter/
  TableOrderDetailPage.tsx`] — both already-existing, already-generic `order.item_status_changed`
  subscribers this story's broadcasts reach with zero frontend code changes.

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5

### Debug Log References

- `uv run pytest tests/test_websocket.py -q` — 28 passed (25 baseline + 3 new: `cancel_item`'s
  `order.item_status_changed` broadcast content/recipients, `edit_item`'s same, and the rewritten
  no-op test now asserting `order.item_status_changed` arrives while `order.status_changed` still
  does not)
- `uv run pytest -q` (full backend suite) — 367 passed, no regressions (baseline 365 + 2 net new
  test functions)
- `npx vitest run` (full frontend suite, sanity check per Task 4 — no frontend file was touched)
  — 196/196 passed
- `npx tsc -b` — clean

### Completion Notes List

- Added exactly two `broadcast()` calls, both reusing `order.item_status_changed` verbatim
  (`pick_up_item`/`mark_item_ready`'s existing event name, payload shape via
  `OrderItemResponse.model_validate(item).model_dump(mode="json")`, and `[UserRole.waiter,
  UserRole.cook]` recipients) — no new event, no new payload shape.
- `edit_item`: broadcast is unconditional (no `.status` change possible, so no
  `order_status_changed` branch exists to gate it), placed after `db.refresh(item)`, matching the
  story's exact placement instruction.
- `cancel_item`: broadcast is unconditional too, placed after `db.refresh(item)` and before the
  existing `if order_status_changed:` block, matching `mark_item_ready`'s item-first/order-second
  ordering exactly.
- Updated both methods' docstrings to state the new broadcast, removing `edit_item`'s now-stale
  "No live broadcast" note.
- Rewrote `test_cancelling_one_of_several_pending_items_broadcasts_nothing` (renamed to
  `..._broadcasts_no_order_status_changed`) per the story's own Scope note: it now asserts the
  Waiter receives `order.item_status_changed` (a real event — the item was genuinely cancelled),
  then times out waiting for anything further, rather than timing out immediately. The no-op
  `order.status_changed` coverage this test exists for is unchanged and still passes.
- Added two new positive broadcast-content tests (`test_cancelling_an_order_item_broadcasts_
  order_item_status_changed`, `test_editing_an_order_item_broadcasts_order_item_status_changed`),
  matching `test_picking_up_an_order_item_broadcasts_order_item_status_changed`'s exact structure
  and assertion style. The cancel test's single-item Order also genuinely drops the aggregate to
  zero non-cancelled items (`in_preparation` → `pending`), so it additionally asserts the expected
  follow-up `order.status_changed` broadcast — not a second, separate no-op case, a real one.
- Confirmed by direct inspection, not just by trusting the story's own claim: `KitchenDisplayPage.
  tsx` and `TableOrderDetailPage.tsx` both already subscribe to `order.item_status_changed`
  generically. Zero frontend files were touched.

### File List

- `backend/services/order_service.py`
- `backend/tests/test_websocket.py`

## Change Log

| Date | Change |
|---|---|
| 2026-08-21 | Story 5.5 created via bmad-create-story: closes a gap against already-approved NFR-1 (Sprint Change Proposal 2026-08-16) — `cancel_item`/`edit_item` never broadcast `order.item_status_changed`, so an already-open Kitchen Display never reflected a cancellation or edit live. Smallest-blast-radius story in the project: two `broadcast()` calls reusing Story 5.2's existing event, no frontend changes. |
| 2026-08-21 | Implemented Story 5.5: added the two broadcast calls to `edit_item`/`cancel_item`, updated both docstrings, added two new broadcast-content tests, and rewrote the one existing test whose "broadcasts nothing" claim this story made false (`deferred-work.md`'s story-3-4 entry had explicitly anticipated this rewrite). 2 net new backend tests (367 total). Full backend suite: 367/367 passed. Full frontend suite: 196/196 passed (sanity check, no frontend file touched). `npx tsc -b` clean. |
