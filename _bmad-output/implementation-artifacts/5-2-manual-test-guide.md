# Story 5.2 — Pick Up and Progress an Order Item, with Atomic Stock Deduction: Manual Test Guide

The stack is rebuilt and running via `docker compose up -d --build`.

- Frontend: http://localhost:3000
- Backend docs: http://localhost:8000/docs

## Login credentials

| Role | Username | Password | Notes |
|---|---|---|---|
| Cook | `amir_test` | `cook12345` | Lands on Kitchen Display by default. Use this account to pick up and mark items ready. |
| Waiter | `maya_test` | `waiter12345` | Used to open a table and add items to test the live push to the Waiter's own screen. |
| Warehouse Manager | `noa_test` | `warehouse12345` | Use this to watch stock levels and the Alerts page while a Cook picks items up. |
| Admin | `ron` | `admin12345` | Optional — for inspecting Dish recipes/ingredient thresholds if you want to engineer a specific low-stock crossing. |

## What to check

1. **Pick up a pending item, atomic deduction (AC1).** As `maya_test`, open a table and add an item
   for a Dish that has a recipe with ingredients (e.g. Margherita, which uses an ingredient
   Story 4.x already seeded). Switch to `amir_test`'s Kitchen Display tab — the new item appears
   as a `pending` row with a **"Pick up"** button. Click it. Confirm:
   - The row's status badge flips to **"In preparation"** within ~2 seconds.
   - The button changes to **"Mark ready"**.
   - As `noa_test`, open the Ingredients page and confirm that Dish's ingredient's `current_stock`
     dropped by exactly `recipe quantity × item quantity`.

2. **No double-deduction on a re-click (AC2).** Try clicking "Pick up" again on the same item (if
   the button is still visible momentarily) or refresh and confirm the item stays `in_preparation`
   and stock does not drop a second time.

3. **Mark ready, no further stock movement (AC3).** Click **"Mark ready"** on the now
   `in_preparation` item. Confirm the badge flips to **"Ready"**, the button disappears (no action
   on a `ready` row), and the ingredient's stock is unchanged from step 1's post-pick-up value.

4. **Live push to the Waiter's screen too (AC8).** With the Waiter's Table/Order detail page for
   this same table open in another tab, confirm its status badge for this item also updates live
   (to "In preparation" then "Ready") without a page refresh, matching what the Cook did — and
   confirm no pick-up/mark-ready buttons ever appear on the Waiter's page (Cook-only feature).

5. **Cannot skip ahead or reverse (AC4/AC5).** Add a second item and, from the Cook's tab, confirm
   there's no way to "Mark ready" a still-`pending` item (no button shows until it's picked up
   first), and once an item reaches `ready`, no button remains to undo it.

6. **Attribution, not an access lock (AC6).** Pick up an item as `amir_test`, then log in as a
   second Cook account (create one via Admin if needed, e.g. `cook2`/`cook212345`, role `cook`) and
   confirm that second Cook **can** mark the first Cook's picked-up item ready from their own
   Kitchen Display.

7. **Below-stock pick-up still succeeds, and triggers a Low-Stock Alert (AC7).** As `ron` or
   `noa_test`, find or adjust an Ingredient so its `current_stock` is just above its
   `min_stock_threshold` (or use the Warehouse Manager's manual stock-movement form to bring one
   down close to threshold). As `maya_test`, add an item for a Dish using that ingredient, then as
   `amir_test`, pick it up. Confirm:
   - The pick-up succeeds even if it pushes stock below zero or below threshold (no error, no
     capping).
   - As `noa_test`, the **Alerts** page picks up the new shortage within a couple of seconds
     (live push), reading `"Stock low: {name} (...)"`.

8. **Single large click target (AC8, UX-DR19).** Visually confirm the "Pick up"/"Mark ready"
   buttons are full-width, large, easy to hit at a glance from a few feet away — not small icon
   buttons.

9. **Inline error, not a silent failure.** With two browser tabs both logged in as different Cooks
   watching the same pending item, click "Pick up" in both tabs at nearly the same moment. One
   should succeed; the other should show a small inline error message under that row (not a blank
   failure, not a crash), and its button should not stay stuck disabled.

## Known, deliberately out-of-scope items (do not report as bugs)

- The Order itself never changes status here — an Order can have every one of its items reach
  `ready` while the Order's own `status` field stays `pending`. That's explicitly Story 5.3's job
  ("Order Status Derives From Its Items"), not this one.
- A `ready` item still shows on the Kitchen Display indefinitely — there's still no way for an
  Order to reach `served`/`closed` (Stories 5.3/5.4), so nothing removes a finished item from the
  board yet.
