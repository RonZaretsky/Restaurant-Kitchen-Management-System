---
title: Restaurant Kitchen Management System
status: final
created: 2026-07-24
updated: 2026-07-31
---

# PRD: Restaurant Kitchen Management System
*Working title — confirm.*

## 0. Document Purpose

This PRD is for Ofek and Ron (builders and analysts of this project) and for the BMad workflows that consume it next (`bmad-ux`, `bmad-architecture`, `bmad-create-epics-and-stories`). It is also, deliberately, the primary *source material* for the course-required **OOA** (Analysis) document — but it is not a drop-in substitute for it: §2–§5 here are written capability-first and cover the OOA's required content (problem description in §1, system components in §4's feature groupings, user types and their actions — see the per-Role action table in `addendum.md` — and the flows behind the required Use Case/Activity diagrams in §2.3 and §4). Writing the actual OOA still requires a pass that strips the implementation-adjacent details this PRD intentionally keeps for engineering's benefit (real field names like `password_hash`/`cook_id`, model names like `AIRecipeSuggestion`, and named technology like OpenAI/React) — the OOA must be zero-implementation-detail and readable by a client who "understands nothing about programming," a stricter bar than this PRD holds itself to. The course-required **OOD** (Design) document — Class/Sequence diagrams, layering, design patterns — is downstream of this PRD, produced by `bmad-architecture`; this PRD deliberately stays in capability language and defers technology/pattern choices to `addendum.md` or to that later stage.

Structure: vocabulary is Glossary-anchored (§3) — every FR, UJ, and feature description uses those terms verbatim. Functional Requirements are grouped by feature and numbered globally (FR-1…FR-24) so they stay stable references even if features are reorganized later. Inline `[ASSUMPTION: …]` tags mark places drafted without direct confirmation; all are indexed in §9. Grounding inputs: the existing brownfield codebase scan (`docs/index.md`), the official course final-project guidelines, and the instructor-approved project proposal — the crosswalk between this PRD and those source documents lives in `addendum.md`, not here.

## 1. Vision

A restaurant kitchen runs on handoffs — a waiter's order has to reach the cook instantly, the cook's prep has to draw down the right ingredients automatically, and a warehouse manager has to know about a shortage before it becomes a table's problem. Today those handoffs are informal: shouted tickets, paper pads, a whiteboard for stock. This system replaces that with one shared, role-aware application that carries an order from the moment a waiter opens a table through kitchen prep, automatic inventory deduction, and checkout — with every staff member seeing exactly the slice of that flow their role needs, live, without refreshing a page or walking to the pass.

Layered on top of that operational core is a genuinely differentiated capability: a **Smart Chef** module that turns the system's own live inventory data into usable creativity — generating recipe or special-of-the-day suggestions from *what's actually in stock right now* (reducing food waste instead of just tracking it), and giving the kitchen a conversational assistant to consult on, version, and improve recipes. Competitive research into commercial Kitchen Display Systems (Toast, Square, TouchBistro, Lightspeed) found none that combine live B2B kitchen inventory with generative recipe suggestions — that pairing exists separately in consumer food-waste apps and in enterprise waste-*analytics* tools, never joined together the way this system joins them. `[ASSUMPTION: this novelty claim reflects a research pass at PRD-drafting time (2026-07-24), not an exhaustive or ongoing competitive audit — see §9.]`

Underneath the product goal is a second, equally real one: this system is the vehicle for demonstrating rigorous object-oriented design — a clean layered architecture, relevant design patterns, and a domain model expressive enough that the requirements captured here translate cleanly into the UML diagrams (Use Case, Activity, Class, Sequence) the course requires.

## 2. Target User

### 2.1 Jobs To Be Done

- **Waiter** — needs to open a table, get an order into the kitchen without walking there, see when it's ready, and close out the bill — fast, during a live service rush.
- **Cook** — needs to see new orders the instant they're placed, work through them without missing or double-handling an item, and mark items done in a way that automatically reflects everywhere else.
- **Warehouse Manager** — needs to trust that stock levels reflect reality without manual recount, and to be told *before* an ingredient runs out, not after a cook can't make a dish.
- **Admin** (restaurant owner/manager) — needs to control what's on the menu and at what price, and control who on staff can do what, without touching a database directly.
- **Cook, acting as chef, using Smart Chef** — needs a way to turn "I have a surplus of X about to spoil" into a servable dish idea in minutes, and a sounding board to iterate on it, instead of guessing or letting the ingredient go to waste.
- **Ofek & Ron, as builders** — need the requirements captured here to map cleanly onto graded OOA/OOD deliverables (Use Case, Activity, Class, Sequence diagrams) without having to reverse-engineer intent from code later.

*(The four roles above — Waiter, Cook, Warehouse Manager, Admin — are the system's actual user types, and the only ones that belong in a course OOA user-type list. The builders' own need, above, is a meta-JTBD about this PRD, not a system user — kept here for completeness but out of scope if this section is lifted into the OOA.)*

### 2.2 Non-Users (v1)

- **Restaurant customers / diners** — no customer-facing app, kiosk, or online ordering surface exists in v1; all input into the system comes from staff.
- **Multi-location restaurant groups** — the system models a single restaurant's tables, menu, and inventory; no cross-location or franchise concept.
- **Delivery/takeout platforms** — no integration with third-party delivery aggregators.

### 2.3 Key User Journeys

- **UJ-1. Maya opens a table and gets an order into the kitchen.**
  - **Persona + context:** Maya is a waiter mid-shift during dinner service, working the floor from a shared terminal near the host stand.
  - **Entry state:** Already logged in as `waiter` from the start of her shift; standing at Table 12, which just sat down.
  - **Path:** She opens Table 12 (status → occupied), starts a new order, adds two dishes with quantities and one note ("no onions" on the second), and submits.
  - **Climax:** The moment she submits, the order items appear — instantly, with no page refresh — on the kitchen display Amir is watching. Maya sees each item's status still say "pending" on her own screen, confirming it's in the queue.
  - **Resolution:** Maya moves to her next table; Table 12's order now exists with two pending items, visible to both her and the kitchen — and to every other Waiter, since v1 has no per-waiter table filtering (FR-6).
  - **Edge case:** If Maya tries to add an item for a dish currently marked unavailable, the system blocks the add and tells her why, rather than silently accepting an order the kitchen can't fulfill.

- **UJ-2. Amir works the pass in real time.**
  - **Persona + context:** Amir is the cook on the line, watching the kitchen display instead of a paper ticket rail.
  - **Entry state:** Logged in as `cook`, kitchen display open, mid-service.
  - **Path:** Table 12's two items (continuing from UJ-1) appear on his screen the instant Maya submits them. He picks up the first item — his name attaches to it, status moves to in-preparation. He preps it, marks it ready ("passed").
  - **Climax:** The moment he picks the item up (marks it in-preparation), two things happen invisibly to him but critically to the system: the recipe's ingredient quantities are deducted from stock right then — because that's when the ingredients actually start getting used — and Maya's screen updates to show the item in progress. Marking it ready afterward is a pure status change; no further stock movement happens at that point.
  - **Resolution:** He repeats for the second item; once both are ready, Table 12's order status reflects "ready" for Maya to see. Maya marks it `served` once she delivers it (FR-11).
  - **Edge case:** If picking up an item would deduct more of an ingredient than is currently in stock, the system still allows it (food gets made regardless) but the resulting negative/below-threshold stock immediately triggers the low-stock alert path (UJ-3), so the shortage surfaces rather than being silently absorbed.

- **UJ-3. Noa catches a shortage before it stalls the kitchen.**
  - **Persona + context:** Noa is the warehouse manager, primarily monitoring from a back-office terminal but responsible for reacting fast during service.
  - **Entry state:** Logged in as `warehouse_manager`, not actively watching the screen — she's doing physical stock work.
  - **Path:** Amir's consumption movement (from UJ-2) drops an ingredient below its minimum threshold. Noa gets an alert. She opens the ingredient's detail, sees current stock, threshold, and the movement history that got it there.
  - **Climax:** She confirms this needs a purchase, logs a `purchase` stock movement once new stock arrives, and the ingredient clears the shortage state.
  - **Resolution:** The kitchen can keep making the affected dish without Noa having to physically walk the line to check.
  - **Edge case:** If two consumption movements land in quick succession (two cooks finishing similar items at once), the alert must not fire twice for the same still-unresolved shortage — Noa should see one active alert per ingredient, not a flood. The same one-alert-per-shortage guarantee holds for a shortage caused by a logged `waste` or `adjustment` movement, not only `consumption` (FR-14).

- **UJ-4. David sets up a new hire and adjusts the menu.**
  - **Persona + context:** David is the admin (owner/manager), doing back-of-house administration between services.
  - **Entry state:** Logged in as `admin`.
  - **Path:** He creates a login for a newly hired cook, assigning the `cook` role. Separately, he opens the menu, marks a dish unavailable (out of season) and adjusts another dish's price.
  - **Climax:** The new cook can log in and see exactly the kitchen display, nothing else; the unavailable dish immediately stops being orderable by any waiter, though any of its items already in the kitchen queue are unaffected and get prepared normally (FR-22).
  - **Resolution:** Staff roster and menu both reflect reality without David touching data directly.
  - **Edge case:** Deactivating a user who has in-progress order items assigned to them (`cook_id`) must not orphan or break those items — the items keep their history and remain visible on the kitchen display, and any other active Cook can pick up where the deactivated Cook left off (FR-10) since the recorded `cook_id` is attribution, not an access lock. The deactivated user just can no longer log in.

- **UJ-5. Amir turns a surplus ingredient into tonight's special via Smart Chef.**
  - **Persona + context:** Amir, acting in a chef capacity, notices (via Noa's stock view or his own kitchen display) that an ingredient is high in stock and close to needing to move.
  - **Entry state:** Logged in as `cook`, opens the Smart Chef module.
  - **Path:** He requests a recipe suggestion; the system generates one from currently-available stock and shows it with the ingredients it drew on. He doesn't love the plating description, so he opens a chat with the Smart Assistant and asks it to suggest a simpler plating and adjust portion size.
  - **Climax:** The assistant responds with a revised version of the same suggestion, referencing the original — a usable draft special, arrived at through conversation rather than a single one-shot generation.
  - **Resolution:** Amir has a recipe draft. Realizing it as an actual orderable menu item still requires an admin (David) to add it via the menu-management flow (UJ-4) — Smart Chef proposes, it doesn't publish. `[ASSUMPTION: this human-confirmation gate before a suggestion becomes a live menu item is a food-safety and quality guardrail, not confirmed with Ofek/Ron directly — see §9.]` Once David confirms it, the resulting Dish's recipe keeps a traceable link back to this Recipe Suggestion (FR-19), so the AI origin of tonight's special can be shown, not just claimed.
  - **Edge case:** If the OpenAI API call fails or times out, Amir sees a clear "couldn't generate a suggestion right now" state — no half-written suggestion, no stuck chat message. If Amir fires a second request before the first finishes (e.g. a double-click), the second is rejected rather than queued — only one generation in flight per Cook at a time.

## 3. Glossary

- **User** — Any authenticated staff account. Has exactly one **Role**.
- **Role** — One of `admin`, `waiter`, `cook`, `warehouse_manager`. Determines which actions a User can perform.
- **Table** — A physical restaurant table. Has a status: `available`, `occupied`, or `reserved`.
- **Order** — A single dining session at a Table, opened by a Waiter and closed at checkout. Has a status lifecycle: `pending` → `in_preparation` → `ready` (these three derived automatically from its Order Items' statuses, FR-12) → `served` (set explicitly by a Waiter once delivered, FR-11) → `closed` (set by a Waiter at checkout, FR-8).
- **Order Item** — One dish-and-quantity line within an Order. Has its own status: `pending` → `in_preparation` → `ready` → `cancelled` (Order Items do not have their own `served` state — see Order, above, and FR-11). Optionally carries a note (e.g. "no onions") and, once picked up, the Cook who is preparing it (attribution only — see FR-10).
- **Dish** — A menu item: name, description, price, prep time, availability, and a Menu Category. Composed of a Recipe. Cannot be marked available without a non-empty Recipe (FR-22).
- **Menu Category** — A grouping of Dishes (e.g. Starters, Mains, Desserts).
- **Recipe** — The set of Ingredients and quantities required to prepare one serving of a Dish (modeled as Recipe Ingredient lines). Optionally carries a nullable reference back to the Recipe Suggestion it originated from, if any (FR-19).
- **Ingredient** — A raw material tracked in inventory: unit of measure, current stock, and a minimum stock threshold.
- **Stock Movement** — An append-only, auditable log entry of a change to an Ingredient's stock: `purchase`, `consumption`, `waste`, or `adjustment`.
- **Low-Stock Alert** — A *derived* state, not a stored record: an Ingredient is "in shortage" whenever its current stock is below its minimum threshold, computed at read time or on each Stock Movement that can decrease stock, rather than persisted as its own entity. Surfaced to the Warehouse Manager whenever such a Stock Movement causes an Ingredient to newly cross below threshold, with at most one active alert per Ingredient-in-shortage at a time (FR-14).
- **Smart Chef** — The AI-powered module comprising Recipe Suggestion generation and the Smart Assistant chat.
- **Recipe Suggestion** — An AI-generated recipe/special proposal, generated from a snapshot of current Ingredient stock, that a Cook can act on but that requires Admin action via menu management to become an orderable Dish.
- **Smart Assistant** — The conversational (chat) interface a Cook uses to consult on, version, and improve Recipes and Recipe Suggestions.
- **Chat Session** — A persisted, titled conversation between a User and the Smart Assistant, made up of Chat Messages.

## 4. Features

### 4.1 Authentication & Access Control

**Description:** Every action in the system is gated by an authenticated User's Role. This is foundational — every other feature below assumes it. Realizes the entry state of UJ-1 through UJ-5. `[ASSUMPTION: session mechanism (e.g. token expiry duration) is a technology decision deferred to architecture — see addendum.md.]`

**Functional Requirements:**

#### FR-1: User login

A User can authenticate with a username and password and receive a session identifying their Role.

**Consequences (testable):**
- Invalid credentials are rejected with a generic error that does not reveal whether the username exists.
- A successful login returns/establishes a session that subsequent requests can be authorized against.
- Passwords are never stored or transmitted in plaintext at rest (hashed, matching the existing `password_hash` field).

#### FR-2: Role-based authorization

The system restricts every state-changing action to the Roles permitted to perform it, and the UI only surfaces actions the current User's Role is permitted to take.

**Consequences (testable):**
- An authenticated User attempting an action outside their Role's permissions receives an explicit unauthorized response; the action does not execute.
- An unauthenticated request to any non-public action is rejected, not silently allowed.

**Out of Scope:**
- Fine-grained per-resource permissions beyond the four fixed Roles (e.g. "this waiter can only see their own tables," "this cook can only see their own chat sessions") — v1 permissions are Role-level only. FR-6, FR-10, and FR-20 each spell out what this means concretely in their own area.

#### FR-3: Admin manages user accounts

An Admin can create a User account (username, full name, Role), edit an existing User's Role or full name, deactivate an active User, and reactivate a previously deactivated User.

**Consequences (testable):**
- A deactivated User cannot log in (FR-1 rejects their credentials) but their historical records (e.g. Order Items they prepared) remain intact and attributed to them.
- A newly created User can log in immediately with the Role assigned at creation.
- Creating a User with a username that already exists (active or deactivated) is rejected as a duplicate.
- Editing a User's Role or name does not alter the attribution of that User's historical records — past Order Items, Stock Movements, etc. stay attributed to the account as it existed at the time.
- Deactivating or demoting the last remaining active Admin account is rejected — the system always keeps at least one Admin able to log in and manage users.

**Notes:** No self-service signup exists — Admin is the only path to a new account, matching the closed-staff nature of the system.

### 4.2 Table & Order Management (Waiter)

**Description:** The waiter-facing flow of opening a table, building an order against it, watching it progress, correcting or closing it out. Realizes UJ-1.

**Functional Requirements:**

#### FR-4: Open a table and start an order

A Waiter can mark an available Table as occupied and start a new Order tied to it.

**Consequences (testable):**
- A Table already `occupied` cannot have a second Order opened against it.
- A Table currently `reserved` is treated the same as `occupied` for this purpose — it cannot be opened into a new Order either, since v1 has no reservation-arrival workflow to intentionally override it. `[ASSUMPTION: not directly confirmed — see §9.]`
- The new Order starts with status `pending` and no Order Items.

#### FR-5: Add items to an order

A Waiter can add one or more Order Items (Dish + quantity + optional note) to an open Order.

**Consequences (testable):**
- Adding an Order Item for a Dish currently marked unavailable is rejected with a clear reason (realizes the UJ-1 edge case).
- Each added Order Item starts at status `pending` and stores the Dish's price at that moment (`price_at_add`) — the Order's total (FR-8) is always computed from these stored prices, so a later Dish price change (FR-22) never retroactively changes an already-open Order's total.

#### FR-6: View live order and table status

A Waiter can see the current status of every Table and every Order Item in the system, reflecting kitchen-side updates (FR-9/FR-10) without a manual page refresh. There is no per-waiter table assignment or filtering in v1 (FR-2 Out of Scope) — every Waiter sees every Table and Order.

**Consequences (testable):**
- An Order Item's status change made by a Cook is visible on the Waiter's screen within the bound defined in NFR-1.

#### FR-7: Edit or cancel an order item

A Waiter can edit an Order Item's quantity or note, or cancel it outright, while it is still `pending`. Once an Order Item is `in_preparation`, a Waiter, Cook, or Admin can still cancel it (e.g. the dish had to be pulled mid-shift) but can no longer edit its quantity or note.

**Consequences (testable):**
- A cancelled Order Item is excluded from FR-12's Order-status derivation and from FR-8's readiness check for closing the table — this is what keeps a stuck item (one that can never reach `ready`) from permanently blocking a table close.
- Cancelling a `pending` Order Item has no stock impact, since nothing was deducted for it yet.
- Cancelling an `in_preparation` Order Item does **not** automatically reverse its stock deduction (FR-13) — the ingredients are treated as already used/opened. A Warehouse Manager can log a manual `waste` movement separately if physically applicable. `[ASSUMPTION: no-auto-reversal is the simpler, safer default (no invented "undo consumption" movement semantics) — not directly confirmed with Ofek/Ron — see §9.]`

#### FR-8: Close a table

A Waiter can close an Order once it is `served` (FR-11), which computes the total amount as the sum of each non-cancelled Order Item's stored `price_at_add` (FR-5), sets the Order to `closed`, and returns the Table to `available`.

**Consequences (testable):**
- Closing an Order that has not yet reached `served` is hard-blocked, with no override in v1 — a stuck Order Item is resolved via FR-7's cancel path instead of forcing the close.
- Once closed, an Order's total_amount is populated and immutable.

### 4.3 Kitchen Display & Prep Workflow (Cook)

**Description:** The cook-facing real-time queue and prep-status workflow that mirrors a physical pass, plus the explicit hand-off back to the Waiter once food is delivered. Realizes UJ-2.

**Functional Requirements:**

#### FR-9: View incoming orders in real time

A Cook sees new and updated Order Items on the kitchen display as they're submitted by Waiters, without manually refreshing.

**Consequences (testable):**
- A new Order Item (FR-5) appears on the kitchen display within the bound defined in NFR-1.

#### FR-10: Update an order item's status

A Cook can move an Order Item from `pending` to `in_preparation` (picking it up, recording themselves as the preparing Cook) and from `in_preparation` to `ready` ("passed").

**Consequences (testable):**
- Transitioning to `in_preparation` records the acting Cook against the Order Item and triggers automatic stock deduction (FR-13) for that item's Recipe — deduction happens when prep starts, not when the item is marked ready, since that's when the ingredients are actually consumed.
- Transitioning to `ready` is a pure status change — it does not itself move any stock.
- An Order Item cannot skip directly from `pending` to `ready`.
- Reverse transitions (`in_preparation` → `pending`, `ready` → `in_preparation`) are not supported — a mis-pick or mis-mark-ready is corrected via FR-7's cancel path, not an undo. `[ASSUMPTION: intentionally no undo, to avoid inventing stock-reversal semantics for a reverted transition — not directly confirmed — see §9.]`
- The Cook recorded against an Order Item is for attribution/audit, not an access restriction — any active Cook can transition an `in_preparation` Order Item to `ready`, including one different from whoever picked it up (matches FR-2's Role-level-only permission model). A Cook being deactivated mid-shift (FR-3) therefore does not strand their in-progress items; any other active Cook can finish them.

#### FR-11: Mark an order served

A Waiter can mark an Order `served` once its status is `ready` (FR-12), recording that all items have been delivered to the table.

**Consequences (testable):**
- An Order cannot be marked `served` while any non-cancelled Order Item is not yet `ready`, except an Order with zero non-cancelled Order Items (nothing was ever added, or everything added was later cancelled via FR-7), which may be marked `served` directly.
- Marking an Order `served` is a pure status change — no stock or item-level effect.

#### FR-12: Order status derives from its items

An Order's `pending`/`in_preparation`/`ready` status reflects the aggregate of its non-cancelled Order Items' statuses (e.g. moves to `in_preparation` once any item does; to `ready` once all non-cancelled items are). `served` and `closed` are set explicitly (FR-11, FR-8), not derived.

**Consequences (testable):**
- An Order with a mix of `pending` and `ready` items shows as `in_preparation`, not `ready`.
- An Order with zero non-cancelled Order Items has status `pending`.

### 4.4 Inventory & Stock Automation (Warehouse Manager)

**Description:** Keeps Ingredient stock levels accurate automatically as orders move through the kitchen, and surfaces shortages before they block service. Realizes UJ-3 and the automatic-deduction half of UJ-2.

**Functional Requirements:**

#### FR-13: Automatic stock deduction on preparation

When an Order Item transitions to `in_preparation` (FR-10), the system deducts each Recipe Ingredient's quantity (× the item's quantity) from the corresponding Ingredient's current stock and records a `consumption` Stock Movement referencing the triggering Order.

**Consequences (testable):**
- The resulting Stock Movement's `reference_id` links back to the Order that caused it.
- Deduction happens exactly once per Order Item transition — re-triggering the same transition does not double-deduct.

#### FR-14: Low-stock alert

After any Stock Movement that can decrease an Ingredient's current stock (`consumption`, `waste`, or a negative `adjustment`), the system checks whether the affected Ingredient's current stock is now below its minimum threshold, and if so, surfaces a Low-Stock Alert to the Warehouse Manager. Realizes UJ-3.

**Consequences (testable):**
- An Ingredient already below threshold does not generate a duplicate alert on every subsequent stock-decreasing movement — one active alert per Ingredient-in-shortage (realizes the UJ-3 edge case).
- The check-and-create-alert step is atomic per Ingredient: two stock-decreasing movements crossing the threshold at nearly the same instant still produce exactly one active alert, not two.
- An alert clears once a Stock Movement brings the Ingredient back at/above threshold.

#### FR-15: Record manual stock movements

A Warehouse Manager can log a `purchase`, `waste`, or `adjustment` Stock Movement with a quantity and optional note, updating the Ingredient's current stock accordingly.

**Consequences (testable):**
- A `purchase` movement increases current stock; `waste` and negative `adjustment` decrease it; the Stock Movement audit trail (append-only) is preserved regardless of movement type.
- A `waste` or negative `adjustment` movement may drive current stock negative, consistent with the automatic consumption path (FR-13) — stock is never floor-capped at zero, since the audit trail should reflect what actually happened even when it exceeds what was recorded as on-hand.

#### FR-16: Create an ingredient

A Warehouse Manager or Admin can create a new Ingredient record: name, unit of measure, minimum stock threshold, and an initial current stock (defaulting to zero if not specified).

**Consequences (testable):**
- A newly created Ingredient is immediately available to reference in a Recipe (FR-23) or a Stock Movement (FR-15).
- Ingredient names are unique — a duplicate name is rejected (mirrors FR-24's table-number uniqueness and FR-3's username uniqueness).

#### FR-17: View ingredient stock levels

A Warehouse Manager can view all Ingredients with their current stock, threshold, and shortage status, distinguishing ingredients currently in shortage from those that are not.

**Consequences (testable):**
- Ingredients currently below threshold are visibly distinguishable from those that are not (not just present in an undifferentiated list).

### 4.5 Smart Chef (AI-Powered)

**Description:** Generates recipe/special suggestions from live inventory to reduce waste, and gives the kitchen a conversational assistant to iterate on recipes. Realizes UJ-5. Both capabilities are OpenAI-API-backed per the approved proposal.

**Functional Requirements:**

#### FR-18: Generate a recipe suggestion from current stock

A Cook can request an AI-generated recipe/special suggestion, generated using a snapshot of currently-available Ingredient stock (prioritizing ingredients at risk of waste), optionally steered by a short free-text direction the Cook supplies (e.g. "something for dessert," "want it spicy"). The request, the resulting suggestion, and the stock snapshot it was based on are persisted as a Recipe Suggestion.

**Consequences (testable):**
- A stored Recipe Suggestion retains the exact prompt used and the stock snapshot at generation time, so it can be audited/reproduced later (matches the existing `AIRecipeSuggestion` schema).
- The generated suggestion references only ingredients that were in stock at generation time. `[ASSUMPTION: enforced by prompt construction, not independently validated post-generation, see §9.]`
- A second FR-18 request from the same Cook while an earlier one for them is still in flight is rejected rather than queued, at most one generation in flight per Cook at a time. `[ASSUMPTION: reject-not-queue is the simpler default, not directly confirmed, see §9.]`
- When a Cook supplies a free-text direction, it is folded into the generation prompt alongside the stock snapshot and steers the suggestion, but never overrides the stock-availability constraint above, a direction toward a dessert or a specific flavor profile still only draws on ingredients that were actually in stock at generation time. The direction text itself is not a separate persisted field, it becomes part of the already-persisted `prompt_used`.

#### FR-19: Recipe Suggestion requires admin confirmation to become a menu item

A Recipe Suggestion, however promising, does not itself create or modify a live Dish. Turning it into an orderable menu item is a separate Admin action via menu management (FR-22/FR-23).

**Consequences (testable):**
- No code path exists where a Recipe Suggestion writes directly to the Dish/Recipe tables — it always lands in a Cook-facing draft state first.
- When an Admin confirms a Recipe Suggestion into a live Dish's Recipe (FR-23), the resulting Recipe stores a nullable reference back to the originating Recipe Suggestion. A manually-defined Recipe leaves this reference null. This is what lets the system later show which live Dishes started as an AI suggestion.

**Out of Scope:**
- Automated nutritional or allergen validation of AI-generated suggestions — human review is the only safety gate in v1.

#### FR-20: Consult, version, and improve recipes via Smart Assistant chat

A Cook can open a Chat Session with the Smart Assistant to discuss, request revisions to, and iteratively improve a Recipe or a prior Recipe Suggestion. Messages and sessions persist. Realizes UJ-5. **"Manage versions" (per the approved proposal) is satisfied conversationally**: each assistant turn in a session is itself a retrievable version of the recipe being discussed — there is no separate version-entity, save/revert/compare mechanism, or dedicated diffing UI in v1 (deferred, §6.2). This interpretation is confirmed, not an open assumption.

Chat Sessions and Recipe Suggestions are not access-restricted by Cook (matching FR-2's Role-level-only permission model — any Cook can open any other Cook's session or suggestion), but the default list view is filtered to the current Cook's own sessions/suggestions first — a personalization default, not an access boundary — with an option to browse everyone's.

**Consequences (testable):**
- A Chat Session's messages are stored in order with their role (`user`/`assistant`) and are retrievable as a full conversation, not just the latest exchange — this ordered history *is* the version record.
- A follow-up message in an existing session has access to that session's prior messages as conversational context (not treated as a fresh, context-free request).
- A Cook can scroll back through a session's history to see an earlier iteration of the recipe under discussion.
- A Cook can, without any special permission, open a session or suggestion created by a different Cook; the default view simply doesn't lead with it.

#### FR-21: Graceful AI degradation

If the OpenAI API call for a suggestion (FR-18) or a chat message (FR-20) fails or times out, the system surfaces a clear failure state to the Cook and does not persist a partial or corrupt record.

**Consequences (testable):**
- A failed generation leaves no orphaned Recipe Suggestion row and no dangling Chat Message with an empty/null `content`.
- The Cook sees an explicit error state distinguishable from "still generating."

**Feature-specific NFRs:**
- Cost: every OpenAI API call is attributable to a specific User and Chat Session/Suggestion for later cost auditing. No hard per-user or per-day cost cap is enforced in v1 — a confirmed policy decision (was Open Question 2), not merely an unaddressed gap; see the Cost note under Constraints and Guardrails below for the rationale.

### 4.6 Menu & Administration

**Description:** Admin-facing control over what's sellable and how the physical restaurant is modeled. Realizes UJ-4.

**Functional Requirements:**

#### FR-22: Manage menu dishes and categories

An Admin can create, update, and mark a Dish available/unavailable, and manage Menu Categories.

**Consequences (testable):**
- A Dish marked unavailable is immediately rejected by FR-5 (a Waiter cannot add it to a new Order) — but any of its Order Items already `pending`/`in_preparation`/`ready` on already-open Orders are unaffected and proceed through the kitchen normally; marking unavailable only blocks new adds going forward.
- A Dish cannot be marked `available` while its Recipe (FR-23) has zero Recipe Ingredient lines — a Dish must have a defined recipe before it can be ordered, so FR-13's automatic stock deduction is never silently a no-op for a live menu item.

#### FR-23: Define a dish's recipe

An Admin can define/edit the set of Recipe Ingredient lines (Ingredient + quantity + unit) that compose a Dish.

**Consequences (testable):**
- FR-13's stock deduction always reflects the Dish's currently-defined Recipe at the time an Order Item is prepared — not a stale copy from when the Order was placed.

#### FR-24: Manage restaurant tables

An Admin can add and configure Restaurant Tables (table number, capacity).

**Consequences (testable):**
- Table numbers are unique; a duplicate table number is rejected.

## 5. Non-Goals (Explicit)

- **No customer-facing surface** — no diner-facing app, kiosk, QR-code ordering, or online reservation system. All input is staff-entered (ties to §2.2).
- **No payment processing / POS integration** — closing a table computes a total; it does not process a card payment or integrate with a payment terminal.
- **No delivery/takeout or third-party aggregator integration.**
- **No multi-location / multi-tenant support** — one restaurant, one deployment.
- **No native mobile apps** — web-only (responsive), consistent with the existing React/Vite frontend already scaffolded in the repo.
- **No kitchen printer / paper-ticket integration** — the kitchen display screen is the only ticket surface.
- **No offline mode** — the system assumes continuous connectivity between staff terminals and the backend; no local-first or offline-sync behavior.
- **No analytics/BI/reporting dashboards** beyond the stock-level view in FR-17 (e.g. no sales trend reports, no staff performance dashboards).
- **No staff scheduling/shift management.**
- **No table reservation system** — Table status (`available`/`occupied`/`reserved`) exists in the schema, but a reservation *workflow* (booking ahead, holding a table) is not a v1 feature; `reserved` is a settable state only. `[NOTE FOR PM: this is a real gap between the modeled enum and the built feature set — worth a one-line mention in the OOA problem description so the instructor doesn't read it as an oversight.]`
- **No automated nutritional/allergen checking of AI-generated recipes** (see FR-19 Out of Scope).
- **No optimistic locking or conflict UI for simultaneous edits to the same Table/Order** — see NFR-6; a known, explicitly-chosen v1 simplification, not a silent gap.

## 6. MVP Scope

### 6.1 In Scope

- FR-1 through FR-24, in full — this is deliberately the entire v1, matching the proposal's "vertical slice" framing rather than a further-trimmed subset. Auth/RBAC (4.1), Table & Order (4.2), Kitchen Display (4.3), Inventory Automation (4.4), Smart Chef (4.5), and Menu & Administration (4.6) are all required for the core order-to-close flow and the AI differentiator to both work end-to-end for the defense demo.

### 6.2 Out of Scope for MVP

- A **dedicated version-comparison UI** (structured save/list/revert/diff of recipe versions side-by-side) — FR-20 already satisfies "manage versions" conversationally via the persisted chat history itself (see FR-20); what's deferred is a *purpose-built screen* on top of that history. `[NOTE FOR PM: revisit if the 3-week sprint has slack — it would strengthen the Smart Chef demo.]`
- Any of the items listed in §5 Non-Goals.
- Per-resource permission granularity beyond Role-level (FR-2 Out of Scope).

## 7. Success Metrics

*Given the academic context, "success" is grading- and demo-readiness-oriented rather than business-metric-oriented.*

**Primary**
- **SM-1**: The full vertical slice — Maya opens a table, adds items, Amir progresses them to ready (triggering stock deduction), Maya marks it served and closes the table — completes live in the defense demo with no manual database intervention. Validates FR-4, FR-5, FR-8, FR-9, FR-10, FR-11, FR-12, FR-13.
- **SM-2**: A Smart Chef Recipe Suggestion is generated live during the demo, referencing real current stock, followed by at least one Smart Assistant chat iteration on it. Validates FR-18, FR-20.

**Secondary**
- **SM-3**: A Low-Stock Alert fires live during the demo as a direct, visible consequence of the SM-1 order flow (not a separately staged/faked event). Validates FR-14.
- **SM-4**: Every Role (waiter, cook, warehouse_manager, admin) has at least one demo-able action distinct from the others, so the RBAC model (FR-2) is visibly demonstrated, not just implemented.

**Counter-metrics (do not optimize)**
- **SM-C1**: Feature count / breadth. The course grading weights OOA+OOD (design/analysis depth) at roughly double the weight of raw implementation (per the grading breakdown in `addendum.md`) — do not add scope beyond §6.1 in pursuit of a more impressive feature list; that time is better spent on design-pattern depth and documentation quality. Counterbalances SM-1/SM-2.
- **SM-C2**: AI suggestion novelty/cleverness. Optimizing Smart Chef prompts purely for "impressive-sounding" output risks suggestions that ignore real stock constraints (undermining FR-18's actual purpose — waste reduction) or that read as gimmicky rather than usable. Counterbalances SM-2.

## 8. Open Questions

1. Session/auth mechanism (JWT vs. server-side session, expiry duration) is a technology decision for `bmad-architecture`, but the *behavioral* question — should a session survive a browser refresh mid-shift, and for how long — is a product decision this PRD should eventually pin down.
2. Does "table_number" uniqueness (FR-24) need to survive a deleted/deactivated table being renumbered, or is table deletion out of scope entirely (tables only ever added, never removed)? No FR currently covers removing or renumbering a table.

## 9. Assumptions Index

- §1 Vision — the competitive-novelty claim (no mainstream KDS combines live inventory with AI recipe suggestion) reflects a single research pass at drafting time, not an ongoing or exhaustive audit.
- §2.3 UJ-5 — Recipe Suggestion → live menu item requires a human (Admin) confirmation gate; framed as a food-safety/quality guardrail, not directly confirmed.
- §4.1 — Session mechanism (token type, expiry) is deferred to architecture as a technology choice.
- §4.2 FR-4 — A `reserved` Table is treated the same as `occupied` (cannot be opened into a new Order) for lack of a reservation-arrival workflow to say otherwise. Not directly confirmed.
- §4.2 FR-7 — Cancelling an `in_preparation` Order Item does not automatically reverse its stock deduction; treated as already-consumed. Not directly confirmed.
- §4.2/§4.3 FR-8 — Closing a table with a non-`served` Order is hard-blocked, with no override, in v1 — a confirmed decision (was Open Question 1), resolved together with FR-7's cancel/void path so a stuck item cannot deadlock the table indefinitely.
- §4.3 FR-10 — Reverse status transitions are intentionally unsupported, to avoid inventing stock-reversal semantics for a reverted transition. Not directly confirmed.
- §4.3/§4.4 FR-10/FR-13 — Automatic stock deduction is deliberately triggered at transition-to-`in_preparation` (prep start), not at order placement, despite the original proposal's literal "בעת הזמנת מנות" (upon ordering) wording — chosen to match the pre-existing `docs/database-schema.md` business-logic note and to avoid deducting stock for items that are ordered but never started (e.g. a cancelled order). Flagged as a deliberate, not silent, deviation from the proposal's literal phrasing.
- §4.5 FR-18 — "Only in-stock ingredients used" is assumed enforced via prompt construction, not independently validated post-generation.
- §4.5 FR-18 — A second concurrent generation request from the same Cook is rejected, not queued. Not directly confirmed.
- §4.5 FR-20 — "Manage versions of dishes" (proposal wording) is interpreted as satisfied by the persisted chat conversation itself (each turn = a retrievable iteration), not a dedicated version-entity/diff UI — a confirmed decision (was drafted as an assumption; confirmed during Reviewer Gate triage), not merely inferred.
- §4.5 FR-20 — Chat Sessions/Recipe Suggestions are shared (no per-Cook access restriction, matching FR-2), with the default list view filtered to the current Cook's own items as a personalization default rather than a permission boundary. A confirmed decision.
- §4.5 feature NFR — No hard per-user/per-day OpenAI cost cap enforced in v1 — a confirmed policy decision (was Open Question 2), not merely an unaddressed gap.
- §4.6 FR-19 — A confirmed Recipe Suggestion keeps a nullable provenance link on the resulting Recipe back to the originating Recipe Suggestion — a confirmed decision (was Open Question 6).
- §4.6 FR-22 — "Remove" a dish (proposal wording) is implemented as soft-delete (mark unavailable), not a hard delete — narrower than the proposal's literal "add/remove," chosen to preserve historical Order/Order Item references to that Dish.
- §4.6 FR-24 — Restaurant Table management has no explicit counterpart in the proposal's Administration bullets; included as an analyst-inferred requirement (tables must be configurable somehow, and `RestaurantTable` already exists in the schema) rather than a client-stated one — exactly the kind of implicit-requirement addition the course's OOA guidelines ask analysts to surface.
- NFR-6 — Simultaneous edits to the same Table/Order resolve last-write-wins in v1 — a confirmed decision (was Open Question 4), chosen for a single small kitchen's low real-world contention rather than left silently unhandled.

---

## Cross-Cutting NFRs

- **NFR-1 (Real-time propagation):** An Order Item status change (creation or transition) is visible on the relevant other Role's screen (Waiter ↔ Cook, per FR-6/FR-9) within **2 seconds**, with no manual refresh required. This is a push requirement, not a polling-with-short-interval requirement — chosen because the whole point of digitizing the pass is that staff react to the screen the way they'd react to a shouted ticket. `[ASSUMPTION: the 2-second figure itself is not confirmed with Ofek/Ron — the *push, not poll* requirement was confirmed; the exact bound was not.]`
- **NFR-2 (Authorization is universal):** No mutating action (order creation, status change, stock movement, menu edit, user management) executes without an authenticated session carrying a Role permitted for that action (FR-2). There is no "trusted internal" bypass.
- **NFR-3 (Stock/order consistency):** Automatic stock deduction (FR-13) and Order/Order Item status transitions (FR-10, FR-12) must be atomic with respect to concurrent requests — two near-simultaneous transitions on the same Order Item must not both apply, and a deduction must never be partially applied (some Ingredients deducted, others not, from the same Recipe). This is a strict data-integrity guarantee, distinct from NFR-6's general last-write-wins policy for non-transactional field edits (e.g. a Table note) — the two do not conflict because they cover different kinds of concurrent access.
- **NFR-4 (Auditability):** Every change to an Ingredient's stock is traceable to exactly one Stock Movement record — there is no code path that mutates `current_stock` without a corresponding movement (already implied by the existing schema's audit-log design; stated here as a requirement so it survives into the OOD).
- **NFR-5 (Concurrent multi-terminal use):** The system is used simultaneously from at least four distinct terminals/sessions in normal operation (one or more Waiters, a kitchen display, a warehouse terminal, an Admin terminal) against one shared backend — this is baseline expected load, not a stress-test edge case.
- **NFR-6 (Concurrent-edit resolution):** Simultaneous edits to the same Table/Order/Order Item by two Waiters, or a Waiter and a Cook (outside the atomic paths already covered by NFR-3), resolve last-write-wins in v1 — no optimistic locking or conflict UI. A deliberate v1 simplification appropriate to a single small kitchen's low real-world contention, stated explicitly rather than left as a silent gap (resolves former Open Question 4).

## Constraints and Guardrails

**Safety**
- An AI-generated Recipe Suggestion is a *draft* until a human (Admin, via FR-19/FR-22/FR-23) turns it into a real menu item — the system never auto-publishes AI output as sellable/servable. This exists because an LLM can hallucinate an implausible or unsafe ingredient combination, and food served to real people is the one place in this project where a mistake has a consequence beyond a bad grade.

**Privacy**
- The system holds only staff data (username, hashed password, full name, Role) — no customer/diner PII is collected anywhere in v1 (consistent with §5's no-customer-facing-surface non-goal). Passwords are hashed, never stored or logged in plaintext (FR-1).

**Cost**
- Smart Chef (§4.5) makes real, billed OpenAI API calls. v1 ships without an enforced cost ceiling — a deliberate choice (former Open Question 2, now resolved), because a small team's academic-project usage volume is inherently low and self-contained, and adding a cap mechanism was judged not worth the implementation time it would take from a compressed 3-week sprint.

**Platform**
- **Web, responsive** — a single React web application (matching the already-scaffolded `frontend/`), used across multiple simultaneous roles/terminals (NFR-5) rather than a per-role native app. No mobile-native or desktop-native build in v1.

---

_Generated with BMad Method `bmad-prd` — Fast path, finalized 2026-07-24. See `addendum.md` for source-document crosswalk, grading-rubric breakdown, and technical-how deferrals._
