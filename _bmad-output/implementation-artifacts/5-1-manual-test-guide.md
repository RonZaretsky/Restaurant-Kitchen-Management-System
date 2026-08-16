# Story 5.1 — View Incoming Orders in Real Time (Kitchen Display): Manual Test Guide

The stack is already rebuilt and running via `docker compose up -d --build`.

- Frontend: http://localhost:3000
- Backend docs: http://localhost:8000/docs

## Login credentials

| Role | Username | Password | Notes |
|---|---|---|---|
| Cook | `amir_test` | `cook12345` | Freshly created for this test round. Lands on Kitchen Display by default (its home surface), and should load in **dark theme** automatically. |
| Waiter | `maya_test` | `waiter12345` | Freshly created, used to open Table 50 and add items live. |
| Admin | `ron` | `admin12345` | Optional, for the "Cook can't create tables" negative check. |

A fresh **Table 50** (`available`) was created for this test round, since every other seeded table
is already occupied. Available dishes: Margherita, Tiramisu, Fries.

## What to check

1. **Empty state + dark theme on load (AC2, AC4).** Log in as `amir_test`. You should land directly
   on **Kitchen Display**. Confirm:
   - The page renders in **dark mode** automatically (no manual toggle needed) — this should already
     be true even on a fresh browser profile with no stored theme preference.
   - It reads **"No orders in the queue"** (assuming Table 50 has no order yet — if you've already
     run through this guide once, open a different fresh table, or check Table 50 for existing items
     first).

2. **Live push within ~2 seconds, grouped by table (AC1).** Open a second tab/window, log in as
   `maya_test`. Go to **Tables**, click **Table 50** to open it into an order, then add **2×
   Margherita** and **1× Fries**. Switch back to the Cook's tab — **without refreshing** — and
   confirm within a couple of seconds:
   - A new card appears reading **"Table 50"**.
   - It lists **Margherita × 2** and **Fries × 1**, each with a **"Pending"** status badge
     (colorblind-safe: icon + color + spelled label, not color alone).

3. **Status badge rendering (AC4).** Confirm each row's status badge matches the same visual
   language used elsewhere in the app (e.g. the Waiter's own Table/Order detail screen) — grey/
   neutral for Pending.

4. **No action controls anywhere (this story is read-only, Story 5.2 adds actions).** Confirm there
   is **no button** on any Kitchen Display card — no pick-up, no mark-ready, nothing clickable on
   the items themselves. This is intentional, not a missing feature.

5. **Multiple tables, correct grouping.** From the Waiter tab, open a **second** table (any other
   `available` one, or create a new one via Admin) and add an item to it too. Confirm the Kitchen
   Display now shows **two separate cards**, each correctly grouping only its own table's items —
   not merged, not cross-contaminated.

6. **Elevation / dark-theme card rendering (AC4).** Visually confirm the cards have a subtle
   elevation/shadow (MUI's default `Card` elevation) and render legibly against the dark background
   — this matters specifically because the Kitchen Display is meant to be read at a glance, at a
   distance, on a shared kitchen terminal.

7. **Reconnect banner (AC3) — optional, harder to trigger manually.** If you want to verify this:
   stop the backend container (`docker stop restaurant-kitchen-management-system-backend-1`) while
   the Cook tab is open, and confirm a **"Reconnecting..."** banner appears within a few seconds.
   Restart it (`docker start ...`) and confirm the banner disappears and the board still works. This
   banner is shared global chrome (built in Story 1.5), not new in this story, so this check is
   optional/lower priority.

8. **Cook can now see Tables data, but still can't manage it.** While logged in as `amir_test`,
   confirm there's still no way to create/edit tables from the Cook's UI (no such nav item) — the
   backend permission widening in this story is read-only and only feeds the Kitchen Display's own
   table-number resolution, not a new UI capability for Cook.

## Known, deliberately out-of-scope items (do not report as bugs)

- No pick-up / mark-ready buttons anywhere — that's Story 5.2, not this one.
- An item that reaches `ready` status will **still show on the Kitchen Display indefinitely** —
  there's no way yet for an Order to be marked `served`/`closed` (Stories 5.3/5.4), so nothing
  removes a finished item from the board yet. This is a known, documented forward-compatibility gap,
  not a bug in this story.
- If a new Table or Dish is created by an Admin *while* a Cook is already on the Kitchen Display, and
  a Waiter then immediately uses it, the new item should resolve correctly within a couple of seconds
  once the live event refetches the reference data (this was a real bug found and fixed during this
  story's code review) — but this is a narrow, unlikely-to-hit-manually scenario, not something the
  guide above specifically walks through.
