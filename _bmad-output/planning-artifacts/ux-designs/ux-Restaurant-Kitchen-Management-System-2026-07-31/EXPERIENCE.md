---
name: 'Restaurant-Kitchen-Management-System'
status: draft
sources:
  - '_bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md'
  - '_bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/addendum.md'
  - '_bmad-output/planning-artifacts/architecture/architecture-Restaurant-Kitchen-Management-System-2026-07-30/ARCHITECTURE-SPINE.md'
updated: '2026-07-31'
---

# Restaurant Kitchen Management System, Experience Spine

> Single-surface responsive web, desktop/PC browser only, four roles (Waiter, Cook, Warehouse Manager, Admin). Paired with `DESIGN.md`. Built on MUI per architecture AD-13; this spine specifies the behavioral delta on top of MUI's defaults, not a from-scratch interaction model.

## Foundation

Single-surface responsive web, desktop/PC browser only, for all four roles. No native mobile, no tablet, no touch input, no separate physical controller for the Kitchen Display, this is a shared-terminal, mouse-and-keyboard tool used on the restaurant's own machines during service. There is no separate Responsive & Platform section in this spine because there are no breakpoints to define: one layout, one input model, across every role.

MUI is the UI system (React Router v7 for routing, TanStack Query for server state, WebSockets for push updates, per the architecture spine). `DESIGN.md` is the visual identity reference; this spine covers information architecture, behavior, states, and interaction. Where a component is named here, its visual spec lives in `DESIGN.md.Components` under the same name.

Every screen is theme-aware: a real light/dark toggle, not a per-role hardcoded look. The Kitchen Display initializes in dark mode (glare and distance legibility at the pass); every other role's home surface initializes in light mode. Any user can flip either way at any time from the app bar (`{components.theme-toggle}` in `DESIGN.md`). The choice persists per browser/terminal, not per user account, matching the shared-terminal reality of this system (multiple staff use the same machine per shift); no user-preference storage is needed for it.

No offline mode: the system runs on the restaurant's local network during service and assumes continuous connectivity (matches the PRD's explicit No Offline Mode non-goal). A dropped connection shows a plain "Reconnecting..." state and retries automatically; there is no local-first write queue.

Content density is dense throughout: tables and lists over cards-with-whitespace, per the Discovery decision. Row height and text size follow `{spacing.dense-row-height}` and `{typography.dense-row}` in `DESIGN.md`.

## Information Architecture

13 surfaces across four roles, confirmed with Ofek during Discovery.

| Surface | Reached from | Purpose |
|---|---|---|
| Login | App open | JWT auth, redirects to the role's home surface |
| **Waiter:** Tables | Login / nav | Grid of all tables (available/occupied/reserved), Maya's home |
| **Waiter:** Table / Order detail | Tap a table | Open table, add dishes (qty + notes), edit/cancel pending items, mark served |
| **Cook:** Kitchen Display | Login / nav | The board, items grouped by table, pick up to in-prep to ready, Amir's home |
| **Cook:** Dishes (view-only) | Nav | Browse dish catalog + recipe/plating notes for context, no write access |
| **Cook:** Smart Chef | Nav | Request a recipe suggestion, chat to iterate |
| **Warehouse Manager:** Ingredients | Login / nav | List of all ingredients vs. threshold, Noa's home |
| **Warehouse Manager:** Ingredient detail | Tap an ingredient | Stock, threshold, movement history, log purchase/waste/adjustment |
| **Warehouse Manager:** Alerts | Persistent nav badge | Standing list of active shortages |
| **Admin:** Menu Management | Login / nav | Dishes + categories + recipes, availability, price |
| **Admin:** Recipe Suggestions | Nav | Review Cook-requested AI suggestions, confirm into a live Dish |
| **Admin:** Users | Nav | Create/edit role/deactivate/reactivate staff |
| **Admin:** Tables setup | Nav | Add/configure physical tables |

Every Waiter sees every Table and every Order (no per-waiter filtering, per FR-6/AD-9); every Cook sees every Chat Session and Recipe Suggestion, with the current Cook's own items sorted first as a display default, not an access boundary (AD-10). There is no cross-role navigation: each role's nav only lists that role's own surfaces, plus the shared Login entry point.

## Voice and Tone

Microcopy only. Brand posture lives in `DESIGN.md.Brand & Style`. Every role gets the same plain, factual voice, nobody is spoken to more warmly than anyone else, and there is no customer-facing surface anywhere to write for.

| Do | Don't |
|---|---|
| "Table 12, occupied" | "Table 12 is currently occupied!" |
| "2 items ready" | "You have 2 items ready for pickup" |
| "Stock low: Tomato (3.2kg left)" | "Uh oh! Running low on tomatoes." |
| "Rejected, dish unavailable" | "Oops, something went wrong!" |
| "Reconnecting..." | "Oops! We lost connection, hang tight!" |
| "No active shortages" | "You're all caught up! Great job!" |
| "Order closed" | "Success! Your order has been closed." |
| State the fact, then (if needed) the reason. | Apologize, celebrate, or editorialize. |

## Component Patterns

Behavioral rules. Visual specs live in `DESIGN.md.Components` under the matching name.

| Component | Use | Behavioral rules |
|---|---|---|
| Table tile | Tables | Click opens Table/Order detail. Status shown via `{components.status-badge}` (available/occupied/reserved has its own neutral rendering, distinct from OrderItem status). Once the table's open Order has an item at `ready`, the tile switches to `{components.table-tile.attention-state}` regardless of which table Maya is currently viewing, this is the Waiter attention cue (see below). |
| Order Item row | Table/Order detail, Kitchen Display card | Status via `{components.status-badge}`. Edit (quantity/note) and pick-up/mark-ready are each one click while the precondition holds (edit only while `pending`; pick-up only while `pending`; mark-ready only while `in_preparation`). Cancel is available while `pending` or `in_preparation` (Waiter, Cook, or Admin) but is gated behind a confirm step: for an `in_preparation` item, the confirm dialog states plainly that stock already deducted for it will not be reversed (AD-11), so the acting user isn't surprised later. |
| Kitchen Display card | Kitchen Display | One card per table, grouping that table's Order Items. One click advances a card's item from `pending` to `in_preparation` (pick-up, records the acting Cook) or from `in_preparation` to `ready`. No drag, no multi-select, no reverse transition, a mis-pick is corrected via the Order Item row's cancel path, not an undo (matches AD-6/FR-10). |
| Ingredient row | Ingredients | Below-threshold rows are visually distinct (`{components.ingredient-row.in-shortage}`) *and* sorted to the top of the list, not just flagged in place. Click opens Ingredient detail. |
| Alert row | Alerts | One row per Ingredient currently in shortage (never more than one active alert per ingredient, per FR-14). Never auto-dismisses and carries no dismiss control of its own; it drops off the list only when a Stock Movement brings that Ingredient back at or above threshold. Click opens Ingredient detail to log the resolving movement. |
| Recipe Suggestion card | Recipe Suggestions | Shows the requesting Cook and the ingredients the suggestion drew on. Exactly two actions: Confirm into Dish (routes into Menu Management to complete the Dish/Recipe, per FR-19) or Dismiss. |
| Nav badge, Alerts | Warehouse Manager nav (Noa) | Persistent count of active alerts, visible from anywhere in her role's UI. No toast, she's frequently not looking at the screen when a shortage occurs (UJ-3). Clears only as individual alerts resolve, never a manual "mark read." |
| Nav badge / counter, tables needing attention | Waiter nav + Table/Order detail (Maya) | Persistent "N tables need attention" counter, visible from the Tables grid and from inside any Table/Order detail screen, not just the grid. Clears automatically, one at a time, as each Order is marked `served` (FR-11). No separate dismiss action. |
| Theme toggle | App bar, every surface | One click toggles light/dark. Persists per browser/terminal (see Foundation). |

**Resolved:** Dismissing a Recipe Suggestion sets a persisted dismissed status on it (a small addition to `AIRecipeSuggestion`, not defined by FR-18/FR-19 as written), so it leaves the active Recipe Suggestions list but is retained for audit, consistent with this system's audit-everything ethos elsewhere (Stock Movements, cancelled Order Items). Not a UI-only, unpersisted dismiss. This is a minor data-model note for whoever builds FR-18/FR-19's stories, not a new FR.

## State Patterns

Every one of the 13 IA surfaces, minimum cold-load / empty / error coverage.

| State | Surface(s) | Treatment |
|---|---|---|
| Cold load | All 13 surfaces | Skeleton rows/cards matching the expected layout (MUI `Skeleton`). Resolves on data. |
| Invalid credentials | Login | "Invalid username or password." Generic on purpose, matches FR-1's no-enumeration requirement, never reveals whether the username exists. |
| Empty | Tables | "No tables configured yet." (Admin hasn't run Tables setup.) |
| Empty | Table/Order detail | "No items added yet." |
| Unavailable-dish block | Table/Order detail | "Rejected, dish unavailable." Inline at the add-item control, not a toast (realizes UJ-1's edge case). |
| Empty | Kitchen Display | "No orders in the queue." |
| Reconnecting | Kitchen Display (and globally) | "Reconnecting..." Retries automatically. Most time-critical here, since this is the surface furthest from a keyboard/mouse to manually refresh. |
| Empty | Dishes (view-only) | "No dishes on the menu yet." |
| Empty | Smart Chef | "No recipe suggestions yet." / "No chat sessions yet." |
| Generating | Smart Chef | Explicit in-flight indicator, distinguishable from both the empty state and the error state (FR-21). A second request while one is in flight for the same Cook is rejected inline, not queued. |
| Generation failed | Smart Chef | "Couldn't generate a suggestion right now." No half-written suggestion, no stuck chat message (FR-21, AD-14). |
| Empty | Ingredients | "No ingredients recorded yet." |
| Empty | Ingredient detail (movement history) | "No stock movements yet." |
| Empty (desired state) | Alerts | "No active shortages." Plain line, this is the good outcome, not an error. |
| Empty | Menu Management | "No dishes yet." |
| Empty | Recipe Suggestions | "No suggestions awaiting review." |
| Empty | Users | "No staff accounts yet." (Should not occur in practice, at least one Admin always exists per AD-15, listed for completeness.) |
| Rejected (last-admin lockout) | Users | "Rejected, at least one admin must stay active." Inline on the deactivate/demote action (AD-15). |
| Rejected (duplicate) | Users, Tables setup, Ingredients | "Rejected, username/table number/ingredient name already exists." Inline on the create action (FR-3/FR-24/FR-16). |
| Empty | Tables setup | "No tables configured yet." |
| Error (generic) | All 13 surfaces | The actual reason, inline, sourced from the architecture spine's error envelope (`detail` as a string or FastAPI's structured validation list). Never a generic "something went wrong." |

**Two attention-cue mechanisms** (both real, product-important, and easy to under-build if treated as generic notifications):

1. **Noa's shortage alerts.** A persistent count badge on the Alerts nav item (`{components.nav-badge-alerts}` in `DESIGN.md`), visible from anywhere in her role's UI, plus the standing Alerts list itself. Deliberately no toast, she is frequently doing physical stock work and not watching the screen when a shortage first appears (UJ-3's framing). The badge and the list both clear only when the underlying shortage resolves via a Stock Movement, never a manual dismiss.
2. **Maya's tables-needing-attention.** A Table tile gets the traffic-light "ready" treatment (`{components.table-tile.attention-state}` in `DESIGN.md`) the moment that table's order has an item at `ready`, visible even while she's viewing a different table. A persistent "N tables need attention" counter mirrors this from both the Tables grid and the Table/Order detail screen. Clears automatically, per table, the moment she marks that Order `served` (FR-11), no separate dismiss action exists or should exist.

## Interaction Primitives

Mouse and keyboard only, no touch surface anywhere in this system.

- Standard click-to-act everywhere: open a tile, pick up an item, confirm a dialog.
- No drag, no multi-select, anywhere, most notably on the Kitchen Display where a drag-based ticket rail would be the obvious pattern to reach for and is deliberately rejected (keeps the one-click-per-transition model simple and matches AD-6's guarded, single-step transitions).
- No custom keyboard shortcuts beyond what the browser already provides (Tab, Enter, Esc on dialogs, browser back). This was an explicit scope cut for a three-week build, not an oversight, a Drift-style vim-nav layer is out of scope for v1.
- Standard MUI focus and hover behavior; no custom hover-reveal affordances given there's no touch fallback to design around.

## Accessibility Floor

Behavioral. Visual contrast values live in `DESIGN.md.Colors`.

- WCAG 2.2 AA contrast baseline across every surface, in both light and dark mode. `{colors.accent}` and `{colors.accent-dark}` are each verified above 4.5:1 against their mode's background (see `DESIGN.md`).
- Colorblind-safe status everywhere: every status (Order/OrderItem, Ingredient shortage, Alert) pairs its color with a distinct icon and a spelled-out text label, per `{components.status-badge}`. This is a hard requirement on the Kitchen Display specifically, where a cook working fast, at a glance, and potentially colorblind must be able to tell `in_preparation` from `ready` without relying on hue alone.
- Visible focus rings on every interactive element (inherits MUI's default focus ring, kept at its default contrast against both light and dark backgrounds).
- Logical tab order matching visual/reading order on every surface.
- No screen-reader-specific work beyond this baseline. This is a stated scope line, not a silent gap: given the three-week academic build window and desktop-only staff usage, dedicated screen-reader optimization (live-region announcements, custom ARIA beyond framework defaults) is out of scope for v1.

## Key Flows

Retold from the PRD's UJ-1 through UJ-5 at screen-level detail. Protagonists and beats are verbatim from PRD §2.3; the steps below are new, translating each into clicks against the surfaces and components named above.

### Flow 1, UJ-1: Maya opens a table and gets an order into the kitchen

Maya is a waiter mid-shift during dinner service, working from a shared terminal near the host stand. Table 12 just sat down.

1. Maya is on the Tables grid (her home surface). Table 12's tile shows `available`.
2. She clicks the tile. Table/Order detail opens; the table flips to `occupied` and a new Order starts, `pending`, with no items.
3. She adds two Order Item rows: a dish with quantity, and a second with quantity plus a note ("no onions"). Each row shows `pending` via `{components.status-badge}`.
4. She submits.
5. **Climax:** The instant she submits, those two Order Item rows appear on Amir's Kitchen Display, grouped under a Table 12 card, no page refresh on either screen. On Maya's own screen, both rows still read `pending`, confirming the order is in the queue rather than lost.
6. Maya returns to the Tables grid and moves to her next table. Table 12's tile now shows `occupied`; the order and its two `pending` items are visible to her, to Amir, and to every other Waiter (no per-waiter filtering, FR-6).

**Failure path:** if Maya tries to add a dish currently marked unavailable, the add is rejected inline at the Order Item entry control with "Rejected, dish unavailable," no silent acceptance of an order the kitchen can't fulfill (realizes UJ-1's named edge case, FR-5).

### Flow 2, UJ-2: Amir works the pass in real time

Amir is the cook on the line, watching the Kitchen Display instead of a paper ticket rail.

1. Amir is on the Kitchen Display. Table 12's card appears the instant Maya submits (continuing Flow 1), showing two `pending` Order Item rows.
2. He clicks the first row's pick-up control. It moves to `in_preparation`; his name attaches to it as the preparing Cook.
3. Invisibly to him, two things happen atomically in that same click: the recipe's ingredient quantities are deducted from stock (a `consumption` Stock Movement referencing this Order), and Maya's Table/Order detail updates that same row to `in_preparation`.
4. He preps it, then clicks mark-ready. The row moves to `ready`, a pure status change, no further stock movement.
5. **Climax:** the deduction happened the moment he picked the item up, not when he passed it, so the system's inventory already reflects reality while the food is still on the pan.
6. He repeats for the second item. Once both are `ready`, the Order's derived status (FR-12) reads `ready` on Maya's screen; her Table 12 tile switches to the attention-state treatment (green plus check). She marks it `served` once delivered (FR-11), clearing the attention cue.

**Edge case named by the PRD (not a hard failure):** if picking up an item would deduct more of an ingredient than is currently in stock, the pick-up still succeeds (food gets made regardless, per AD-16, stock is never floor-capped at zero), but the resulting below-threshold stock immediately surfaces a Low-Stock Alert, Flow 3 picks up from exactly this point.

### Flow 3, UJ-3: Noa catches a shortage before it stalls the kitchen

Noa is the warehouse manager, primarily doing physical stock work, not watching a screen.

1. Amir's consumption movement (end of Flow 2) drops an ingredient below its minimum threshold.
2. Noa's Alerts nav badge increments (`{components.nav-badge-alerts}`), visible the next time she glances at any screen in her role, no toast was fired to interrupt her physical work.
3. She opens Alerts. One Alert row for the affected ingredient, reading "Stock low: {ingredient} ({current stock}{unit} left)."
4. She clicks the row, opening Ingredient detail: current stock, threshold, and the movement history that produced this state.
5. She confirms a purchase is needed and logs a `purchase` Stock Movement once new stock arrives.
6. **Climax:** the moment that movement brings stock back at or above threshold, the Alert row disappears from her list and the nav badge count drops, no manual dismiss anywhere in this path.
7. The kitchen keeps making the affected dish without Noa having to walk the line to check.

**Edge case named by the PRD:** if two consumption movements land in quick succession (two cooks finishing similar items near-simultaneously), the Alert row must not double up, Noa sees exactly one active alert per ingredient-in-shortage, never a flood (FR-14). The same guarantee holds whether the shortage was caused by `consumption`, `waste`, or a negative `adjustment`.

### Flow 4, UJ-4: David sets up a new hire and adjusts the menu

David is the admin, doing back-of-house administration between services.

1. David opens Users. He creates a new account: username, full name, role `cook`.
2. Separately, he opens Menu Management. He marks one dish unavailable (out of season) and edits another dish's price.
3. **Climax:** the new cook logs in and lands on exactly the Kitchen Display, nothing else, per their role. At the same moment, the now-unavailable dish stops appearing as addable in every Waiter's Table/Order detail (the same "Rejected, dish unavailable" path from Flow 1), while any of its Order Items already queued on open Orders are unaffected and keep moving through the Kitchen Display normally.
4. Staff roster and menu both now reflect reality, without David touching data directly.

**Failure path named by the PRD:** if David later deactivates a Cook who has `in_preparation` Order Items assigned to them, those items are not orphaned or blocked, they keep their history and stay visible on the Kitchen Display, and any other active Cook can pick up where the deactivated Cook left off, since the recorded Cook is attribution, not an access lock (FR-10). The deactivated user simply can no longer log in. Separately, if David tries to deactivate or demote the last remaining active Admin, that action is rejected inline ("Rejected, at least one admin must stay active," AD-15), the system never allows itself to lock every user out of user management.

### Flow 5, UJ-5: Amir turns a surplus ingredient into tonight's special via Smart Chef

Amir, still acting as cook, notices via his Kitchen Display or Noa's stock view that an ingredient is high in stock and close to needing to move.

1. He opens Smart Chef and requests a recipe suggestion.
2. A Recipe Suggestion card appears, generated from a snapshot of currently-available stock, showing the ingredients it drew on.
3. He doesn't love the plating description, so he opens a Chat Session tied to that suggestion and asks the Smart Assistant for a simpler plating and an adjusted portion size.
4. **Climax:** the assistant responds with a revised version of the same suggestion, explicitly referencing the original, a usable draft special arrived at through conversation rather than a single one-shot generation.
5. Amir now has a recipe draft. Turning it into an actual orderable menu item still requires David to confirm it via Menu Management (Flow 4's surface), Smart Chef proposes, it doesn't publish. Once confirmed, the resulting Dish's recipe keeps a traceable link back to this Recipe Suggestion (FR-19), so the AI origin of tonight's special can be shown, not just claimed.

**Failure path:** if the OpenAI call fails or times out, Amir sees an explicit "Couldn't generate a suggestion right now" state, distinguishable from "still generating," with no half-written suggestion and no stuck chat message (FR-21). If Amir fires a second request before the first finishes (a double-click, say), the second is rejected outright rather than queued, only one generation in flight per Cook at a time (FR-18, AD-14).
