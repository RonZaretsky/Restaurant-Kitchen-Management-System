# Story 4.2 — Low-Stock Alert: Manual Test Guide

The stack is already rebuilt and running via `docker compose up -d --build`.

- Frontend: http://localhost:3000
- Backend docs: http://localhost:8000/docs

## Login credentials

| Role | Username | Password | Notes |
|---|---|---|---|
| Warehouse Manager | `noa_test` | `warehouse12345` | Freshly created for this test round (`warehouse1` also exists but its password isn't known). |
| Admin | `ron` | `admin12345` | Existing account, useful for the "no Alerts nav item" negative check. |
| Cook | `chef` | (unknown — use Admin to reset if needed) | Only needed for the backend-permitted-but-no-UI check below (optional, API only). |

Seeded ingredients relevant to this test (via `noa_test`'s Ingredients screen): **Potatos** — current stock `12.000 kg`, threshold `10.000 kg`. Closest to shortage, best demo candidate. Everything else is comfortably above its own threshold.

## What to check

1. **Empty state (AC6).** Log in as `noa_test`. Open **Alerts** from the nav. Confirm it reads exactly **"No active shortages"** and the Alerts nav item shows no badge/number next to it.

2. **Crossing into shortage, live (AC1, AC5).** Go to **Ingredients → Potatos**. Log a **waste** movement of `3.000 kg` (12.000 → 9.000, crosses below the 10.000 threshold). Within ~2 seconds, without refreshing:
   - The **Alerts nav badge** should appear showing **1**.
   - If you navigate to **Alerts**, you should see one row: **"Stock low: Potatos (9.000kg left)"**.
   - Clicking that row should navigate to Potatos' own Ingredient detail page.

3. **Live push across two tabs (AC1/AC5, the real-time requirement).** Open two browser tabs/windows both logged in as `noa_test` (or a second warehouse_manager). Put one tab on the **Alerts** screen. From the other tab, log another stock-decreasing movement on a *different* ingredient (e.g. **waste** `2.000 kg` on **Sugar**, threshold `1.000 kg`, current `2.000 kg` → crosses to `0.000`). The first tab's Alerts list and nav badge should update on their own, no manual refresh, within a couple of seconds.

4. **No duplicate alert (AC2/AC3).** With Potatos still below threshold, log a second small **waste** (e.g. `0.500 kg`). Confirm the Alerts list still shows **exactly one row** for Potatos (not two), just with the lower stock number the next time the list is fetched (a non-crossing movement doesn't push live by design — a manual refresh or navigating away and back will show the updated number).

5. **Clearing an alert (AC4).** On Potatos (currently below threshold), log a **purchase** large enough to bring it back to or above `10.000 kg` (e.g. `+2.000 kg`). Within ~2 seconds, confirm the nav badge count decrements and the Alerts row for Potatos disappears — no manual dismiss anywhere.

6. **Boundary check (strict `<`, not `<=`).** Bring an ingredient to land **exactly** at its threshold (e.g. adjust Sugar back to exactly `1.000 kg`, its own threshold). Confirm it does **not** appear as an alert — only strictly-below counts.

7. **Role scoping.** Log in as `ron` (Admin). Confirm there is **no "Alerts" nav item at all** for Admin (Admin's nav is Menu Management / Recipe Suggestions / Users / Tables setup / Ingredients only) — so there's nothing to badge for that role, by design (only warehouse_manager has this screen).

8. **Empty state returns.** After clearing every alert you created, revisit Alerts and confirm it goes back to **"No active shortages"** and the badge disappears again.

## Optional / API-only checks (no dedicated UI, backend-only per this story's scope)

- `GET /api/inventory/alerts` also succeeds (200) for `cook` and `admin` sessions, even though neither role has an Alerts screen to view it from — this is an intentional backend-ahead-of-UI grant, not a bug (see the story's Scope note).

## Known, deliberately out-of-scope items (do not report as bugs)

- The Ingredients list (`/warehouse/ingredients`) and an Ingredient's own detail page do **not** show any shortage styling/badge/sort-to-top — that's Story 4.3, not this one.
- A movement that changes an already-in-shortage ingredient's stock *without* crossing the threshold does not push live — the Alerts row will show a stale number until your next natural refetch (page revisit, window focus, or the next crossing event on any ingredient). This is a deliberate, documented design choice (see check #4 above).
