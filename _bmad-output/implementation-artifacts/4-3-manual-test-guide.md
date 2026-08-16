# Story 4.3 — View Ingredient Stock Levels: Manual Test Guide

The stack is already rebuilt and running via `docker compose up -d --build`.

- Frontend: http://localhost:3000
- Backend docs: http://localhost:8000/docs

## Login credentials

| Role | Username | Password | Notes |
|---|---|---|---|
| Warehouse Manager | `noa_test` | `warehouse12345` | Same account created for Story 4.2's manual round — still active. |
| Admin | `ron` | `admin12345` | Useful for the "shortage still shown but no live re-highlight" check below. |

Seeded ingredients (via `noa_test`'s Ingredients screen): **Potatos** — current stock `12.000 kg`,
threshold `10.000 kg`. Closest to shortage, best demo candidate. Everything else is comfortably
above its own threshold.

## What to check

1. **Baseline — no shortage styling yet (AC1, AC2).** Log in as `noa_test`, open **Ingredients**.
   Every row shows Name / Unit / Current stock / Threshold as before. None should show a warning
   icon or red text yet.

2. **Crossing into shortage — visual treatment (AC1, AC2).** Go to **Potatos**' row (click through
   to its detail page), log a **waste** movement of `3.000 kg` (12.000 → 9.000, crosses below the
   10.000 threshold). Navigate back to **Ingredients**. Confirm:
   - **Potatos now shows a warning icon next to its name, and its whole row's text is red.**
   - **Potatos has moved to the top of the list** (or top of the in-shortage group if you create
     more shortages below).
   - Every other ingredient is unaffected (no icon, default text color, unchanged position).

3. **Live re-sort/re-highlight without a manual refresh (AC2).** Stay on the **Ingredients** screen
   in one tab. From a second tab (same or a different `warehouse_manager` login), log a **waste**
   movement on **Sugar** (current `2.000`, threshold `1.000`) large enough to cross below threshold
   (e.g. `1.500 kg` → lands at `0.500`, below `1.000`). Within ~2 seconds, the first tab's
   Ingredients list should update on its own — Sugar gains the warning icon/red text and moves up
   into the shortage group, sorted alphabetically against Potatos (Potatos before Sugar).

4. **Alphabetical ordering within each group.** With at least two ingredients in shortage (Potatos,
   Sugar) and several not, confirm: shortage rows come first, alphabetical among themselves
   (Potatos before Sugar); non-shortage rows follow, alphabetical among themselves.

5. **New ingredient created already in shortage shows styling immediately (this story's own review
   fix — worth double-checking manually, not just by the automated test).** Using the "Add
   ingredient" form on the Ingredients screen, create a new ingredient with a **current stock lower
   than its threshold** (e.g. name "Truffle Oil", unit `liter`, threshold `5`, current stock `0`).
   Confirm it appears **immediately** with the warning icon and red text — no page reload needed.

6. **Clearing a shortage (derived-state behavior carried over from Story 4.2).** Go to Potatos'
   detail page, log a **purchase** bringing it back to or above `10.000 kg`. Return to Ingredients:
   Potatos should no longer show the warning icon/red text, and should sort back into its normal
   alphabetical position among the non-shortage rows.

7. **Admin sees shortage state on load, but not necessarily live (known, documented limitation —
   not a bug to report).** Log in as `ron` (Admin) and open **Ingredients** (reachable via the
   "Ingredients" nav entry). Any ingredient currently in shortage should show correctly on this
   initial load. If you then trigger a *new* crossing from another tab while staying on this screen
   as Admin, it is expected (not a bug) that Admin's view does **not** live-update — only
   `warehouse_manager` sessions get the live push today. A manual refresh will show the current
   state correctly.

8. **Empty state (AC3, unaffected by this story, quick sanity check only).** Not practical to fully
   test without deleting all ingredients (no delete UI exists) — skip unless you want to verify
   against a fresh database.

9. **Ingredient detail page unaffected (AC4, unaffected by this story).** Open any Ingredient's
   detail page — stat cards, log-movement form, and movement history should look exactly as before
   this story (no shortage banner or red styling was added there; that's explicitly out of scope).

## Known, deliberately out-of-scope items (do not report as bugs)

- No shortage banner or red "danger" stat-card styling on the Ingredient **detail** page — only the
  Ingredients **list** row and the existing Alerts screen row get the red-plus-icon treatment.
- Admin does not receive live re-highlighting while parked on the Ingredients screen (see check #7)
  — this is a known, documented limitation (see `deferred-work.md`), not a defect. Admin still sees
  correct data on every fresh page load.
- No delete/archive UI for Ingredients — out of scope for this project entirely.
