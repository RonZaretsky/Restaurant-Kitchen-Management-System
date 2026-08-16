# Story 5.3 — Order Status Derives From Its Items: Manual Test Guide

The stack is rebuilt and running via `docker compose up -d --build`.

- Frontend: http://localhost:3000
- Backend docs: http://localhost:8000/docs

## Login credentials

Existing accounts from prior manual-testing sessions, reset to a shared known password so this
guide is self-contained.

| Role | Username | Password | Notes |
|---|---|---|---|
| Waiter | `waiter1` | `test12345` | Use this to open/add items and watch the Tables grid. |
| Cook | `demo_cook` | `test12345` | Lands on Kitchen Display. Use this to pick up and mark items ready. |
| Admin | `demo_admin` | `test12345` | Optional — only needed if you want to create a second Table or a second Cook account. |
| Warehouse Manager | `demo_warehouse` | `test12345` | Not needed for this story's checks. |

There is already one Table (**Table 1**, occupied) with an open Order on it (its two original
items are both cancelled from earlier testing, so it currently has zero non-cancelled items — a
live example of AC3's "zero items → `pending`" case, already sitting there before you do
anything). There is one Dish, **"test"** (100.00), with a Recipe Ingredient, so pick-up will
genuinely deduct stock. Add all new items in this guide to **Table 1**'s existing Order.

## What to check

1. **Starting point — zero items reads `pending` (AC3).** As `waiter1`, open the **Tables** page.
   Table 1 shows the `occupied` badge only, no green "Ready" chip next to it. Click into Table 1
   → Table/Order detail. Both existing rows show **"Cancelled"**, matching the empty-non-cancelled
   state.

2. **A single pending item flips the Order off `pending` (AC1).** Still on Table 1's detail page,
   add one item for **"test"** (quantity 1). Nothing in the UI shows the Order's own status
   directly, but keep the Tables grid open in a second tab — no attention chip should appear yet
   (the Order is now `in_preparation` internally, one bucket short of `pending` and two short of
   `ready`, neither of which shows a chip).

3. **Mix of statuses still reads `in_preparation`, not `ready` (AC1).** Add a **second** item for
   "test" (quantity 1) to the same Order, so there are two pending items. Switch to `demo_cook`'s
   Kitchen Display (a third tab). Pick up the first item, then mark it ready. Refresh the Tables
   grid tab — Table 1 still shows **no** attention chip (one item ready, one still pending — the
   mix case).

4. **All non-cancelled items ready flips the tile to attention-state (AC2/AC4, the main new
   behavior).** Back on Kitchen Display, pick up the second item and mark it ready too. Within a
   couple of seconds, **without reloading**, the Tables grid tab should show Table 1's tile
   switch to the attention-state treatment — a green **"Ready"** chip (with a check icon) layered
   *next to* the existing "occupied" badge, not replacing it. This is the live
   `order.status_changed` push, not a manual refresh.

5. **Adding a new item pulls a `ready` Order back down (AC1, re-derivation on every change).** As
   `waiter1`, back on Table 1's detail page, add a **third** item for "test". Watch the Tables
   grid tab again — the green "Ready" chip should disappear within a couple of seconds (the Order
   is back to `in_preparation`, one fresh pending item among two ready ones).

6. **Cancelling that item pushes it back to `ready` (AC2, re-derivation via cancel too).** Cancel
   the third item you just added (Cancel button on its row, no confirm needed since it's still
   `pending`). The Tables grid's "Ready" chip should reappear live.

7. **Only occupied tiles are ever eligible.** Confirm no other Table tile in the grid ever shows
   the green chip (there's only one Table today, but worth a glance) — `available`/`reserved`
   tiles never render it regardless of backend data, by construction.

8. **Retry recovers if a request briefly fails (code-review fix).** Not easily reproducible by
   hand without simulating a network failure — skip unless you want to open DevTools, throttle to
   "Offline" briefly on the Tables page, then restore the connection and click **Retry**: the grid
   should recover fully (both the table list and the ready-chip data), not just partially.

## Known, deliberately out-of-scope items (do not report as bugs)

- Nothing anywhere in the UI shows the Order's own `pending`/`in_preparation`/`ready` value as
  text — only its *effect* (the attention-state chip when `ready`). That's exactly what AC4 asks
  for; a visible Order-status badge on the Waiter's screen isn't part of this story.
- The Order can never reach `served`/`closed` yet, and there's no "mark served"/"close" button
  anywhere — that's Story 5.4. The "tables need attention" nav counter that's supposed to clear
  automatically on serve is also Story 5.4's, not this one's.
- A `ready` item still shows on the Kitchen Display indefinitely, and a served/closed Order's
  items would still show there too once 5.4 exists — the Kitchen Display's own filter gap is
  explicitly still deferred (see `deferred-work.md`).
