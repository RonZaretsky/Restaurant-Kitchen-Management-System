---
baseline_commit: 9128c8a32b72aab24fdb00253780842aac1ddc4c
epic: 4
story: 3
---

# Story 4.3: View Ingredient Stock Levels

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Warehouse Manager,
I want to see all ingredients with their current stock, threshold, and shortage status,
so that I can spot problems at a glance.

## Scope note (read first)

**This is the smallest story in Epic 4 so far, and the first with zero backend changes.** Both
capabilities the ACs ask for already have a working backend source of truth:

- `GET /api/inventory/ingredients` (Story 2.3) already returns every Ingredient's `current_stock`
  and `min_stock_threshold` — AC1's "current stock, threshold" half is already fully shown on
  `IngredientsPage.tsx` today. The only missing dimension is **shortage status**.
- `GET /api/inventory/alerts` (Story 4.2) already computes exactly "which Ingredients are currently
  in shortage" (`current_stock < min_stock_threshold`), as the derived, always-fresh source of
  truth. **This story reuses it as-is via the existing `useAlerts()` hook** rather than
  reimplementing the same comparison a second time client-side. Two consequences:
  1. No new endpoint, no new Pydantic schema, no backend file touched at all in this story.
  2. **Live updates for the shortage highlighting/sorting come for free**, with zero new
     subscription code. `AppShell.tsx` (Story 4.2) already holds a permanent
     `inventory.alerts_changed` subscription for every `warehouse_manager` session that invalidates
     the shared `ALERTS_QUERY_KEY` the moment any shortage crosses. Since TanStack Query's cache is
     keyed and shared across every component calling `useAlerts()`, `IngredientsPage.tsx` calling
     the same hook automatically picks up that same invalidation and refetches — **do not add a
     second `inventory.alerts_changed` subscription inside `IngredientsPage.tsx`, it would be pure
     duplication of work `AppShell.tsx` already does globally for this Role.**

**Two of the four ACs are already fully satisfied by earlier stories and need zero new code:**

- **AC3** ("no ingredients exist yet" → "No ingredients recorded yet") — already implemented,
  `IngredientsPage.tsx:210-212`, shipped with Story 2.6.
- **AC4** ("Ingredient's detail is opened... movement history is shown, or 'No stock movements yet'
  if empty") — already implemented, `IngredientDetailPage.tsx:274-276`, shipped with Story 4.1.
  **Do not touch `IngredientDetailPage.tsx` in this story** — nothing in Story 4.3's ACs asks for
  stat-card danger styling or a shortage banner there (that phrase in Story 4.1's own docstring was
  this codebase's own deferred-scope note, not sourced from any AC; re-checked against
  `EXPERIENCE.md`/`DESIGN.md` directly, neither mentions a detail-page shortage treatment at all —
  only the Ingredients *list* row and the Alerts row get the red-plus-icon treatment).

**What actually changes**: `IngredientsPage.tsx` only. Add `useAlerts()` alongside the existing
`useIngredients()`, build a `Set<number>` of in-shortage ingredient ids, and:
1. Sort the rendered list: in-shortage rows first, then alphabetical by name — **within** each
   group also alphabetical (`DESIGN.md`'s literal wording: "in-shortage rows pinned to top, then
   alphabetical").
2. Give an in-shortage row the same red token as a cancelled OrderItem
   (`{components.status-badge.cancelled.color}`, i.e. MUI's `"error"` semantic color) plus a
   `WarningAmberIcon` (`DESIGN.md` line 64-68, `components.ingredient-row.in-shortage`) — this is
   row-level styling, not a new "Status" text column; nothing in the AC or the design tokens asks
   for a separate column, only that the row be "visually distinguished."
3. Combine `isLoading`/`isError` across **both** queries (`useIngredients()` and `useAlerts()`),
   and make Retry refetch both — the standing project rule from Story 2.5's review ("a page driven
   by more than one independent query must combine loading/error across all of them, not just the
   'main' one"), applied here for the first time to two *read* queries on the same page rather than
   a form-plus-picker shape.

**Test-file impact you must not miss**: `IngredientsPage.test.tsx`'s existing 8 tests each stub
`fetch` for `/api/inventory/ingredients` only. Adding `useAlerts()` means every existing test's
mock now also receives a `GET /api/inventory/alerts` call; **every existing test's `fetch` stub
must be updated to also answer that URL** (typically `[]`, i.e. "nothing in shortage," unless the
test is specifically about shortage styling/sorting) or the mock's catch-all
`Promise.reject(new Error("unexpected request..."))` branch will fail every single existing test,
not just the new ones.

## Acceptance Criteria

1. **Given** the Ingredients screen loads, **when** a Warehouse Manager views it, **then** every
   Ingredient's current stock, threshold, and shortage status are shown (FR-17). *(Current
   stock/threshold: already shown, Story 2.3. Shortage status: new in this story, via the
   icon+color treatment below — not a new column.)*
2. **Given** an Ingredient is currently below threshold, **when** the list renders, **then** it is
   visually distinguished (red plus warning icon) and sorted to the top of the list, not just
   flagged in place (UX-DR9).
3. **Given** no ingredients exist yet, **when** the screen loads, **then** it shows "No ingredients
   recorded yet" (UX-DR15). *(Already implemented, Story 2.6 — verify with a test, do not
   reimplement.)*
4. **Given** an Ingredient's detail is opened, **when** it loads, **then** its movement history is
   shown, or "No stock movements yet" if empty (UX-DR15). *(Already implemented, Story 4.1 — verify
   with a test if one doesn't already exist for the empty-history case, do not touch
   `IngredientDetailPage.tsx`.)*

## Tasks / Subtasks

- [x] **Task 1: Verify AC3/AC4 are genuinely already satisfied, not just claimed** (AC3, AC4)
  - [x] Confirm `IngredientsPage.tsx`'s empty-state branch (`ingredients?.length === 0`) reads
    exactly `"No ingredients recorded yet"` — it does (line 211), add a test if
    `IngredientsPage.test.tsx` doesn't already have one asserting the exact copy (it has
    `"shows the empty state instead of the old placeholder"` — check it asserts the literal string,
    not just presence of *a* message).
  - [x] Confirm `IngredientDetailPage.tsx`'s empty-state branch (`movements?.length === 0`) reads
    exactly `"No stock movements yet"` — it does (line 274). Check
    `IngredientDetailPage.test.tsx` for an existing test covering this exact empty-history case; add
    one only if genuinely missing (do not duplicate if it already exists under a different name).
  - [x] Do not modify `IngredientDetailPage.tsx` itself in this task or any other in this story.
- [x] **Task 2: Wire `useAlerts()` into `IngredientsPage.tsx` and combine loading/error** (AC1, AC2)
  - [x] Import `useAlerts` from `../../services/inventoryService` (already exported, Story 4.2 —
    no new export needed).
  - [x] Call both `useIngredients()` and `useAlerts()`. Combine: `isLoading = ingredientsQuery.isLoading
    || alertsQuery.isLoading`; `isError = ingredientsQuery.isError || alertsQuery.isError`; Retry
    calls both queries' `refetch()`.
  - [x] Build `const shortageIds = new Set(alerts?.map((a) => a.id) ?? [])` (empty set while
    `alerts` is undefined, so nothing renders as in-shortage before the alerts query settles —
    acceptable since `isLoading` already gates the whole table render until both queries resolve).
- [x] **Task 3: Sort in-shortage rows to the top, alphabetical within each group** (AC2)
  - [x] Before rendering, sort a copy of `ingredients` (do not mutate the query's cached array):
    primary key `shortageIds.has(id) ? 0 : 1` ascending, secondary key `name.localeCompare(other.name)`.
  - [x] Do this with plain array sort in the render body (or a `useMemo` keyed on `ingredients`/
    `alerts`) — no new state needed, this is a pure derivation.
- [x] **Task 4: Row-level shortage styling** (AC1, AC2)
  - [x] For a row whose id is in `shortageIds`: render a `WarningAmberIcon` (from
    `@mui/icons-material/WarningAmber`, matching `DESIGN.md`'s named icon exactly) next to the
    Name cell's text, and color that row's text `"error"` (MUI's semantic error color, matching
    `{components.status-badge.cancelled.color}` per `DESIGN.md` line 66 — reuse the same
    `"error"` MUI palette key `OrderItemStatusBadge.tsx`'s `cancelled` entry already uses, do not
    invent a new hex value).
  - [x] A non-shortage row renders with no icon and default (unstyled) text color, unchanged from
    today.
- [x] **Task 5: Update `IngredientsPage.test.tsx`'s existing 8 tests for the new `/alerts` call**
  (regression safety, no new AC)
  - [x] Every existing test's `fetch` mock must also answer `GET /api/inventory/alerts` (stub `[]`
    unless the test is specifically about shortage rows) — see Scope note. Follow the same
    `if (path.includes(...))` branching shape these tests' mocks already use for
    `/api/inventory/ingredients`.
- [x] **Task 6: New tests for shortage styling/sorting/combined-error behavior** (AC1, AC2)
  - [x] An ingredient below threshold renders with the warning icon and error-colored text; one at
    or above threshold does not (boundary: exactly-at-threshold is NOT in shortage, matches
    `list_alerts`'s strict `<`, Story 4.2).
  - [x] Given a mixed list (some in shortage, some not, deliberately out of alphabetical order in
    the raw fetch response), the rendered row order is: all in-shortage rows first (alphabetical
    among themselves), then all others (alphabetical among themselves).
  - [x] The page combines loading/error across both `useIngredients()`/`useAlerts()`: a failing
    `/alerts` request alone (while `/ingredients` succeeds) still shows the retry-capable error
    state, not a table with no shortage styling silently applied.
  - [x] Retry re-fires both requests, not just the one that originally failed.
- [x] **Task 7: Full regression pass**
  - [x] `pnpm test` (frontend) — zero regressions across every existing suite, not just this file.
  - [x] `npx tsc -b` — clean.
  - [x] No backend changes in this story, so no backend test run is strictly required, but running
    `uv run pytest -q` once at the end costs little and confirms nothing on that side drifted.

## Dev Notes

### Architecture compliance

- **FR-17 / UX-DR9**: see Scope note — the shortage signal is reused from Story 4.2's derived
  `GET /api/inventory/alerts`, not recomputed. Do not add a second `current_stock <
  min_stock_threshold` comparison anywhere in the frontend; there is exactly one place that
  computation should live (the backend), consistent with this codebase's stated preference for one
  source of truth over duplicated client-side business logic.
- **No new Observer/Pub-Sub subscription**: `AppShell.tsx`'s existing global
  `inventory.alerts_changed` subscription (Story 4.2) already keeps `ALERTS_QUERY_KEY` fresh for
  every mounted consumer via TanStack Query's shared cache. Adding a second subscription in
  `IngredientsPage.tsx` would be redundant, not incorrect, but avoid it — it's dead code the moment
  it's written, since the cache invalidation already happens globally.
- **Role-level-only permissions**: unaffected. `IngredientsPage.tsx` is already reachable only by
  `warehouse_manager`/`admin` (`ROLE_NAV_ITEMS`); no new Role scoping question here.
- **AD-16 boundary**: the shortage comparison this story visualizes is `list_alerts`'s own strict
  `<`, already correct and tested in Story 4.2 — this story only needs to trust that boundary, not
  re-derive or re-test it independently (no `<=` ambiguity to worry about here).

### Current state of the files this story touches (read before editing)

- **`frontend/src/pages/warehouse/IngredientsPage.tsx`**: currently calls only `useIngredients()`
  and `useCreateIngredient()`. Its own docstring (lines 62-71) explicitly defers "shortage sorting,
  highlighting... to Epic 4's Story 4.3" — this story is that promised follow-up, update the
  docstring to reflect it's now built, not still deferred.
- **`frontend/src/services/inventoryService.ts`**: `useAlerts(enabled = true)` already exists
  (Story 4.2), exported alongside `ALERTS_QUERY_KEY`. No change needed here at all.
- **`frontend/src/pages/warehouse/IngredientDetailPage.tsx`**: read-only reference for this story
  (confirming AC4 is already satisfied) — **not modified**.
- **`frontend/src/pages/warehouse/IngredientsPage.test.tsx`**: 8 existing tests, each with its own
  `fetch` mock stubbing only `/api/inventory/ingredients` — see Scope note, all 8 need a second
  URL branch added or they will fail once `useAlerts()` is wired in, independent of anything new
  this story adds.

### Project Structure Notes

Files touched:
- `frontend/src/pages/warehouse/IngredientsPage.tsx` — **UPDATE**, `useAlerts()` wired in, sort +
  row styling added, docstring updated.
- `frontend/src/pages/warehouse/IngredientsPage.test.tsx` — **UPDATE**, all 8 existing tests'
  mocks extended for the new `/alerts` call, new tests added per Task 6.

No backend files touched. No new Alembic migration. No new frontend route. No change to
`IngredientDetailPage.tsx`, `AppShell.tsx`, `AlertsPage.tsx`, or `inventoryService.ts` — every
dependency this story needs already exists from Stories 2.3/2.6/4.1/4.2.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 4.3`, lines 812-834] — this story's AC
  source, read alongside Story 4.2 (780-810) to confirm the shortage-derivation boundary between
  the two stories (4.2 owns the Alerts screen/nav badge/broadcast; 4.3 owns the Ingredients list's
  own visual treatment of the same underlying derived state).
- [Source: `_bmad-output/planning-artifacts/prds/prd-.../prd.md#FR-17`, lines 282-287] — "visibly
  distinguishable... not just present in an undifferentiated list," the literal AC1/AC2 source.
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../DESIGN.md`, lines 64-68, 129, 163] —
  `components.ingredient-row.in-shortage` token (`WarningAmberIcon`, the same red as
  `status-badge.cancelled`, "pinned to top, then alphabetical" sort), the literal spec Tasks 3/4
  implement.
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../EXPERIENCE.md`, Component Patterns line
  75] — "Ingredient row... Below-threshold rows are visually distinct... and sorted to the top of
  the list, not just flagged in place. Click opens Ingredient detail." (the click-through already
  exists, Story 4.1, unchanged by this story.)
- [Source: `frontend/src/components/orders/OrderItemStatusBadge.tsx`] — the `"error"` MUI color key
  precedent this story's row styling reuses verbatim, matching `DESIGN.md`'s explicit instruction to
  reuse the same red token as a cancelled OrderItem rather than inventing a new one.
- [Source: `frontend/src/pages/warehouse/AlertsPage.tsx`, Story 4.2] — the existing, already-tested
  `useAlerts()` consumer this story's `IngredientsPage.tsx` becomes the second independent consumer
  of (matching the "two independent components sharing one query key" shape `AlertsPage.tsx`/
  `AppShell.tsx` already established for each other).
- [Source: `_bmad-output/project-context.md`, "A page driven by more than one independent query
  must combine loading/error across all of them" (Story 2.5's review), Testing section] — the
  combined-query-state rule Task 2 applies, and the "mock only fetch, not the service" test
  convention Task 5/6 must follow.

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5

### Debug Log References

- `pnpm vitest run src/pages/warehouse/IngredientsPage.test.tsx` — 12 passed
- `pnpm test` (full frontend suite) — 166 passed
- `npx tsc -b` — clean
- `uv run pytest -q` (full backend suite, no backend files touched by this story) — 311 passed, 22
  warnings, no regressions

### Completion Notes List

- AC3 and AC4 required zero new production code — both were already fully implemented (Story 2.6
  and Story 4.1 respectively) and already had a test asserting their exact required copy. Verified
  by reading the code and the existing test suite directly rather than trusting the story's own
  claim; added no duplicate tests.
- No backend files touched at all. Both capabilities this story surfaces (`current_stock`/
  `min_stock_threshold` and the derived shortage list) already existed as backend endpoints
  (`GET /api/inventory/ingredients`, Story 2.3; `GET /api/inventory/alerts`, Story 4.2) before this
  story began.
- `IngredientsPage.tsx` now calls `useAlerts()` alongside `useIngredients()`, builds a
  `Set<number>` of in-shortage ingredient ids from the alerts response, and combines
  `isLoading`/`isError` across both queries per the established multi-query-page rule (Story 2.5's
  review). Retry re-fires both.
- Sort: in-shortage rows first, alphabetical within each group (`DESIGN.md`'s literal "pinned to
  top, then alphabetical" wording) — implemented as a `useMemo`'d stable sort over a copy of the
  fetched array, never mutating the TanStack Query cache's own array reference.
- Row styling: `WarningAmberIcon` next to the Name cell plus `color: "error.main"` on every cell in
  an in-shortage row, reusing the exact same `"error"` MUI semantic key `OrderItemStatusBadge.tsx`'s
  `cancelled` entry already uses (per `DESIGN.md`'s explicit "same red token as a cancelled
  OrderItem" instruction) — no new hex value introduced anywhere.
- Live updates for the shortage highlighting/sorting require zero new subscription code:
  `AppShell.tsx`'s existing global `inventory.alerts_changed` subscription (Story 4.2) already
  invalidates the shared `ALERTS_QUERY_KEY` for every mounted `useAlerts()` consumer, including this
  page's own call, via TanStack Query's keyed cache.
- All 8 pre-existing `IngredientsPage.test.tsx` tests needed their `fetch` mocks extended to also
  answer `GET /api/inventory/alerts` (5 of the 8 had URL-branching mocks that would otherwise reject
  the new call as "unexpected request"; 3 had unconditional mocks that already covered any URL and
  needed no change). Added 4 new tests for shortage styling, sort order, a combined-error case where
  only the alerts request fails, and that Retry re-fires both requests.

### File List

- `frontend/src/pages/warehouse/IngredientsPage.tsx`
- `frontend/src/pages/warehouse/IngredientsPage.test.tsx`
- `frontend/src/services/inventoryService.ts` (added during code review, see Review Findings)
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Review Findings

Reviewed by three parallel agents (Blind Hunter, Edge Case Hunter, Acceptance Auditor) against this
story's 4 ACs and `_bmad-output/project-context.md`. All 4 ACs independently confirmed satisfied by
the code, including the "AC3/AC4 already satisfied, zero new code" and "zero backend files touched"
claims, both re-verified directly rather than trusted from the story's own prose.

**Fixed during this review:**

- **A newly-created Ingredient already below its own threshold showed no shortage styling until an
  unrelated event refetched the alerts cache** (Edge Case Hunter) — `useCreateIngredient`
  (`frontend/src/services/inventoryService.ts`) only invalidated `INGREDIENTS_QUERY_KEY`, not
  `ALERTS_QUERY_KEY`. Creating an ingredient never goes through `record_movement`, so Story 4.2's
  crossing-triggered broadcast never fires for it either — nothing else would have refreshed the
  alerts list. Fixed: `useCreateIngredient` now invalidates both keys on success. New regression
  test: `shows shortage styling immediately for a newly-created ingredient already below its own
  threshold`.
- **AC2's warning-icon half had no direct test assertion** (Blind Hunter) — the existing shortage
  test asserted row color but never that `WarningAmberIcon` itself renders; a regression dropping
  just the icon while keeping the color would have passed undetected. Added explicit
  `querySelector('[data-testid="WarningAmberIcon"]')` assertions for both the in-shortage and
  not-in-shortage cases.
- **The non-shortage group's own alphabetical ordering was never actually exercised** (Blind
  Hunter) — the existing sort test used only one non-shortage ingredient (Flour), so a regression
  breaking ordering within that group specifically would not have been caught. Added a second
  non-shortage ingredient ("Eggs", alphabetically before "Flour" but listed after it in the raw
  fetch response) to the same test.
- **A garbled `baseline_commit` hash in the story's own frontmatter** (Blind Hunter) — the 40-char
  hash didn't correspond to any object in the repository (only its 7-char prefix, copied from a
  `git log --oneline` line, was real). Corrected to the actual full hash
  (`9128c8a32b72aab24fdb00253780842aac1ddc4c`).
- **A stale, pre-existing test comment referencing the wrong AC number** (`IngredientsPage.test.tsx`,
  "AC6" where "AC3" was meant) — not introduced by this story, but directly adjacent to code this
  story already touches; fixed as a drive-by while in the file.

**Verified as non-issues:**

- **DESIGN.md-sourced implementation details** (Acceptance Auditor) — `WarningAmberIcon`, the
  reused `"error"` MUI color token (matching `OrderItemStatusBadge.tsx`'s `cancelled` entry, no new
  hex introduced), and the "pinned to top, then alphabetical" sort were all independently confirmed
  implemented exactly as `DESIGN.md` specifies, not merely gestured at.
- **No accessibility label on the shortage icon** (Blind Hunter) — re-checked against `DESIGN.md`
  line 163 directly: the `ingredient-row.in-shortage` token specifies color-plus-icon only, unlike
  `status-badge`'s explicit "plus the text label spelled out" requirement. The implementation
  matches its actual design spec; this is not a spec violation.
- **Test-count claims** (Acceptance Auditor) — independently re-run live: 12 (now 13 post-patch)
  file-level, 166 (now 167) suite-wide, `tsc -b` clean. No repeat of a prior story's
  count-inaccuracy mistake.
- **The branch had no commits yet at review time** (Blind Hunter) — expected: this session's
  established pattern commits once at PR time, after code review completes, not before.

**Deferred (non-blocking, see `deferred-work.md`):** Admin gets correct shortage highlighting on
initial load but no live re-highlighting while the backend only broadcasts
`inventory.alerts_changed` to `warehouse_manager` (no AC asks for Admin live updates, out of this
story's scope); the combined error message always prefers `ingredientsError` over `alertsError`
when both queries fail simultaneously.

## Change Log

| Date | Change |
|---|---|
| 2026-08-16 | Implemented Story 4.3: View Ingredient Stock Levels. `IngredientsPage.tsx` now shows shortage status (WarningAmberIcon + error-colored row, reusing Story 4.2's `useAlerts()`) and sorts in-shortage rows to the top, alphabetical within each group. No backend changes — AC3/AC4 were already satisfied by Stories 2.6/4.1. 4 new frontend tests (166 total), 8 existing tests updated for the new `/alerts` call. |
| 2026-08-16 | Code review patch pass: fixed a newly-created in-shortage ingredient not showing shortage styling until an unrelated refetch (`useCreateIngredient` now also invalidates `ALERTS_QUERY_KEY`); added icon-presence and non-shortage-group sort-order test coverage; corrected a garbled `baseline_commit` hash. 1 new regression test added (167 frontend total). |

