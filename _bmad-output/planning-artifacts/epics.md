---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md
  - _bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/addendum.md
  - _bmad-output/planning-artifacts/architecture/architecture-Restaurant-Kitchen-Management-System-2026-07-30/ARCHITECTURE-SPINE.md
  - _bmad-output/planning-artifacts/ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/DESIGN.md
  - _bmad-output/planning-artifacts/ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/EXPERIENCE.md
---

# Restaurant-Kitchen-Management-System - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for Restaurant-Kitchen-Management-System, decomposing the requirements from the PRD, UX Design, and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

FR-1: A User can authenticate with a username and password and receive a session identifying their Role (login).
FR-2: The system restricts every state-changing action to the Roles permitted to perform it, and the UI only surfaces permitted actions (role-based authorization).
FR-3: An Admin can create a User account (username, full name, Role, initial password set by the Admin), edit an existing User's Role or full name, reset an existing User's password, deactivate an active User, and reactivate a previously deactivated User.
FR-4: A Waiter can mark an available Table as occupied and start a new Order tied to it.
FR-5: A Waiter can add one or more Order Items (Dish + quantity + optional note) to an open Order.
FR-6: A Waiter can see the current status of every Table and every Order Item, reflecting kitchen-side updates without a manual page refresh (no per-waiter filtering).
FR-7: A Waiter can edit an Order Item's quantity/note or cancel it while `pending`; once `in_preparation`, a Waiter, Cook, or Admin can still cancel it but not edit it.
FR-8: A Waiter can close a table once its Order is `served`, computing the total from stored `price_at_add`, setting the Order to `closed`, and returning the Table to `available`.
FR-9: A Cook sees new and updated Order Items on the kitchen display as they're submitted, without manually refreshing.
FR-10: A Cook can move an Order Item from `pending` to `in_preparation` (recording the acting Cook, triggering stock deduction) and from `in_preparation` to `ready`.
FR-11: A Waiter can mark an Order `served` once its status is `ready`.
FR-12: An Order's `pending`/`in_preparation`/`ready` status derives from the aggregate of its non-cancelled Order Items' statuses.
FR-13: When an Order Item transitions to `in_preparation`, the system deducts each Recipe Ingredient's quantity from stock and records a `consumption` Stock Movement referencing the Order.
FR-14: After any stock-decreasing Stock Movement, the system checks whether the Ingredient is now below its minimum threshold and surfaces a Low-Stock Alert (at most one active alert per Ingredient-in-shortage).
FR-15: A Warehouse Manager can log a `purchase`, `waste`, or `adjustment` Stock Movement with a quantity and optional note.
FR-16: A Warehouse Manager or Admin can create a new Ingredient record (name, unit, min threshold, initial stock).
FR-17: A Warehouse Manager can view all Ingredients with current stock, threshold, and shortage status, visibly distinguishing in-shortage ingredients.
FR-18: A Cook can request an AI-generated recipe/special suggestion from a snapshot of currently-available stock, optionally steered by free-text direction; the request, suggestion, and stock snapshot persist as a Recipe Suggestion.
FR-19: A Recipe Suggestion never writes directly to a live Dish/Recipe; turning it into an orderable menu item is a separate Admin action (menu management), and the resulting Recipe stores a nullable back-reference to the originating Recipe Suggestion.
FR-20: A Cook can open a Chat Session with the Smart Assistant to discuss/revise/iterate on a Recipe or Recipe Suggestion; sessions/messages persist and are visible to any Cook (current Cook's own items sorted first as a display default).
FR-21: If the OpenAI call for a suggestion or chat message fails/times out, the system surfaces a clear failure state and persists no partial/corrupt record.
FR-22: An Admin can create, update, and mark a Dish available/unavailable, and manage Menu Categories; a Dish cannot be marked available with zero Recipe Ingredient lines.
FR-23: An Admin can define/edit the set of Recipe Ingredient lines (Ingredient + quantity + unit) that compose a Dish.
FR-24: An Admin can add Restaurant Tables (table number, capacity) and edit an existing table's number or capacity while it is `available`; table numbers are unique. Tables are never deleted in v1.
FR-25: A Cook can browse the Dish catalog read-only, seeing each Dish's details and Recipe Ingredient lines for preparation context, with no authoring controls.

### NonFunctional Requirements

NFR-1: An Order Item status change is visible on the relevant other Role's screen (Waiter <-> Cook) within 2 seconds, via push (not polling), with no manual refresh.
NFR-2: No mutating action executes without an authenticated session carrying a Role permitted for that action; no "trusted internal" bypass.
NFR-3: Automatic stock deduction and Order/Order Item status transitions must be atomic with respect to concurrent requests (no double-apply, no partial deduction).
NFR-4: Every change to an Ingredient's stock is traceable to exactly one Stock Movement record.
NFR-5: The system is used simultaneously from at least four distinct terminals/sessions against one shared backend (baseline expected load).
NFR-6: Simultaneous edits to the same Table/Order/Order Item (outside NFR-3's atomic paths) resolve last-write-wins in v1, no optimistic locking or conflict UI.

### Additional Requirements

- Layered backend (`api/` -> `services/` -> `clients/`+`data_models/`) with a single DI composition root (`dependency_injector`); every lifecycle-managed resource wired as a `providers.Resource` on `backend/container.py` (AD-1).
- Real-time updates delivered over a single WebSocket endpoint per authenticated session, scoped to role; every state change emitted exactly once under a fixed `{domain}.{event}` name (AD-2).
- Auth via JWT issued at login, set as an httpOnly cookie; every route except login/health requires a valid JWT verified via one shared FastAPI dependency; explicit CORS allow-list, never a wildcard (AD-3).
- DB schema managed via Alembic (async template); every `data_models/` change ships with a migration; `Base.metadata.create_all` removed from the startup path (AD-4).
- Guarded, atomic OrderItem status transitions: conditional update on expected prior status; the `in_preparation` transition's status update + stock decrement + `StockMovement` insert happen in one DB transaction (AD-6).
- OrderItem stores `price_at_add`; Order totals always computed from stored `price_at_add x quantity` over non-cancelled items (AD-7).
- Service layer rejects setting a Dish available with zero `RecipeIngredient` rows, and rejects deleting a Dish's last `RecipeIngredient` row while available (AD-8).
- All OpenAI calls routed through a `backend/clients/` adapter behind an interface, never called directly from `services/` (AD-12).
- A recipe-suggestion generation request is rejected (not queued) if that Cook already has one in flight, tracked via a status flag checked-and-set in the same transaction (AD-14).
- Service layer rejects any User update that would leave zero active Admins in the system (AD-15).
- No code path clamps `Ingredient.current_stock` at zero, for either the automatic consumption path or manual Stock Movements (AD-16).
- Deployment via the existing Docker Compose topology (Postgres 16, backend :8000, frontend :3000 -> :80); single environment, no cloud hosting/CI-CD in scope for this phase.

### UX Design Requirements

UX-DR1: Implement the shared status-badge component (MUI `Chip` + icon + spelled-out label) for OrderItem/Order status (`pending`/`in_preparation`/`ready`/`served`/`closed`/`cancelled`), reused across Order Item row, Kitchen Display card, and Order/table detail.
UX-DR2: Implement the separate table-status-badge component (`available`/`occupied`/`reserved`), a distinct dimension from OrderItem/Order status, same color+icon+label construction.
UX-DR3: Implement the Table tile attention-state treatment: once a table's open Order has an item at `ready`, the tile layers on the ready-green attention treatment on top of the base table-status badge.
UX-DR4: Implement the Waiter "N tables need attention" persistent counter (Tables grid + Table/Order detail), clearing automatically per table as each Order is marked `served`.
UX-DR5: Implement the Warehouse Manager Alerts nav badge (persistent count, no toast), clearing only as individual alerts resolve via a Stock Movement.
UX-DR6: Implement the primary-action button using the accent color override (`{colors.accent}`/`{colors.accent-dark}`) on MUI's `primary` theme slot; every other Button variant stays default MUI.
UX-DR7: Implement the real light/dark theme toggle (MUI IconButton in the app bar), Kitchen Display defaulting to dark, every other role's home defaulting to light, persisted per browser/terminal (not per user).
UX-DR8: Implement dense-row list/table styling (`size="small"`, `{spacing.dense-row-height}` = 36px, body2/caption text) across Tables, Ingredients, Order Item rows, Alert rows.
UX-DR9: Implement the Ingredient row in-shortage treatment: red token + warning icon, sorted to the top of the list (not just flagged in place).
UX-DR10: Implement the Alert row (red + warning icon, no dismiss control; resolves only via an Ingredient movement).
UX-DR11: Implement the Recipe Suggestion card with exactly two actions (Confirm into Dish via the primary button; Dismiss via outlined/text button), showing the requesting Cook and the ingredients drawn on.
UX-DR12: Implement the Order Item row's cancel action behind a confirm step; for an `in_preparation` item, the confirm dialog states that already-deducted stock will not be reversed (AD-11).
UX-DR13: Implement the Availability gate control on Menu Management: a Dish's availability toggle disabled with an inline reason while its Recipe has zero lines, re-enabling instantly (no reload) once a line is added.
UX-DR14: Implement the Movement type chip on Ingredient detail (neutral color scheme, distinct from the status traffic-light convention) for `purchase`/`consumption`/`waste`/`adjustment`.
UX-DR15: Implement cold-load skeleton states (MUI `Skeleton`) and the named empty-state copy for all 13 IA surfaces (Tables, Table/Order detail, Kitchen Display, Dishes view-only, Smart Chef, Ingredients, Ingredient detail, Alerts, Menu Management, Recipe Suggestions, Users, Tables setup, Login).
UX-DR16: Implement the generic "Reconnecting..." state (auto-retry, no local-first write queue) surfaced on all 13 surfaces when the WebSocket/connection drops.
UX-DR17: Implement inline (non-toast) rejection microcopy for the named validation failures: unavailable-dish add (FR-5), duplicate username/table-number/ingredient-name (FR-3/FR-24/FR-16), missing initial password on user creation (FR-3), last-admin lockout (AD-15), invalid login credentials (generic, no enumeration).
UX-DR18: Implement the Smart Chef "Generating..." in-flight state (distinguishable from empty/error) and the "Couldn't generate a suggestion right now" failure state, with inline rejection of a second concurrent request for the same Cook.
UX-DR19: Build all 13 IA surfaces (Login; Waiter Tables + Table/Order detail; Cook Kitchen Display + Dishes view-only + Smart Chef; Warehouse Manager Ingredients + Ingredient detail + Alerts; Admin Menu Management + Recipe Suggestions + Users + Tables setup) per the mockups in `mockups/`, with per-role nav showing only that role's own surfaces.
UX-DR20: Add a persisted `dismissed` status field on `AIRecipeSuggestion` (schema note surfaced by UX, not originally in an FR) so a dismissed suggestion leaves the active Recipe Suggestions list but is retained for audit.
UX-DR21: Meet the WCAG 2.2 AA contrast baseline in both light and dark mode, visible focus rings on every interactive element, and logical tab order matching visual/reading order, on every surface.

## Epic List

### Epic 1: Staff Accounts & Access Control
Every role can log in securely and see only what their role permits; Admin can manage the staff roster. Also establishes the test harness, migration baseline, application shell, and real-time transport everything later builds on.
**FRs covered:** FR-1, FR-2, FR-3

### Epic 2: Menu, Recipes, Ingredients & Table Setup
Admin can build a sellable menu (dishes, categories, recipes) with the ingredients they reference, and configure the restaurant's physical tables, the master data every later epic builds on.
**FRs covered:** FR-16, FR-22, FR-23, FR-24, FR-25

### Epic 3: Table Service & Order Taking
A Waiter can open a table, build and adjust an order against the menu, and see live status, the front-of-house half of the core flow.
**FRs covered:** FR-4, FR-5, FR-6, FR-7

### Epic 4: Warehouse Inventory Operations & Low-Stock Alerts
A Warehouse Manager can log manual stock movements (purchase/waste/adjustment), view stock levels/shortage status, and get alerted the instant any movement crosses an ingredient below threshold, fully standalone, independent of the kitchen's automatic path.
**FRs covered:** FR-14, FR-15, FR-17

### Epic 5: Kitchen Fulfillment, Automatic Stock Deduction & Close-Out
A Cook works orders to ready in real time (triggering the same automatic stock deduction and low-stock alert logic Epic 4 built), and the Waiter marks served and closes the table, the full order-to-close loop.
**FRs covered:** FR-8, FR-9, FR-10, FR-11, FR-12, FR-13

### Epic 6: Smart Chef, Recipe Suggestions & Assistant Chat
A Cook can generate an AI recipe suggestion from live stock and iterate on it via chat; an Admin can confirm a suggestion into a real menu Dish.
**FRs covered:** FR-18, FR-19, FR-20, FR-21

### FR Coverage Map

FR-1: Epic 1 - User login
FR-2: Epic 1 - Role-based authorization
FR-3: Epic 1 - Admin manages user accounts
FR-4: Epic 3 - Open a table and start an order
FR-5: Epic 3 - Add items to an order
FR-6: Epic 3 - View live order and table status
FR-7: Epic 3 - Edit or cancel an order item
FR-8: Epic 5 - Close a table
FR-9: Epic 5 - View incoming orders in real time
FR-10: Epic 5 - Update an order item's status
FR-11: Epic 5 - Mark an order served
FR-12: Epic 5 - Order status derives from its items
FR-13: Epic 5 - Automatic stock deduction on preparation
FR-14: Epic 4 - Low-stock alert
FR-15: Epic 4 - Record manual stock movements
FR-16: Epic 2 - Create an ingredient
FR-17: Epic 4 - View ingredient stock levels
FR-18: Epic 6 - Generate a recipe suggestion from current stock
FR-19: Epic 6 - Recipe Suggestion requires admin confirmation
FR-20: Epic 6 - Consult/version/improve recipes via Smart Assistant chat
FR-21: Epic 6 - Graceful AI degradation
FR-22: Epic 2 - Manage menu dishes and categories
FR-23: Epic 2 - Define a dish's recipe
FR-24: Epic 2 - Manage restaurant tables (add + edit while available; no delete)
FR-25: Epic 2 - Cook browses the dish catalog (read-only)

## Epic 1: Staff Accounts & Access Control

Every role can log in securely and see only what their role permits; Admin can manage the staff roster. Establishes the project's verification and schema-migration foundation, and the application shell every later surface renders inside.

### Story 1.0: Project Foundation, Test Harness and Migration Baseline

As the development team,
I want an executable test harness and a schema-migration baseline in place,
So that every story's acceptance criteria can actually be verified and every schema change from here has a migration path.

_Note: this is the one story in the plan with no direct end-user value. It is enabling work that Stories 1.1 onward depend on, kept separate rather than folded into Story 1.1 so that story does not grow a fourth unrelated concern._

**Acceptance Criteria:**

**Given** no test framework exists on either side of the repo
**When** this story is built
**Then** `pytest` + `pytest-asyncio` + `httpx.AsyncClient` are added to `backend/pyproject.toml` with a `conftest.py` providing an async test client and a throwaway-database session fixture, and `uv sync` regenerates `backend/uv.lock`

**Given** no frontend test framework exists
**When** this story is built
**Then** `vitest` + `@testing-library/react` + `@testing-library/jest-dom` are added to `frontend/package.json` via `pnpm` (never npm/yarn), with a `pnpm test` script wired and `pnpm-lock.yaml` regenerated

**Given** a trivial passing test on each side
**When** the suites are run
**Then** both execute green from a clean checkout, so every later story's Given/When/Then criteria have something to run in

**Given** `Base.metadata.create_all` is still the schema mechanism and cannot evolve a schema
**When** this story is built
**Then** Alembic is adopted here (async template per AD-4, `alembic init -t async` since the engine is asyncpg-based), a baseline revision is generated against the current `data_models/` schema, and `create_all` is removed from `backend/container.py`'s startup path (AD-4)

**Given** any later story needs a schema change
**When** it ships
**Then** it adds its own revision on top of this baseline, so no story in any epic is ever left without a migration path (AD-4)

### Story 1.1: User Login

As a staff member,
I want to log in with a username and password,
So that I can access the parts of the system my role permits.

**Acceptance Criteria:**

**Given** a User with valid active credentials
**When** they submit username and password to the login endpoint
**Then** they receive a JWT set as an httpOnly cookie identifying their Role and are redirected to their role's home surface

**Given** a wrong username or a wrong password
**When** login is attempted
**Then** it is rejected with a generic "Invalid username or password" error that does not reveal which part was wrong (FR-1)

**Given** a deactivated User's credentials
**When** they attempt to log in
**Then** login is rejected with the same generic error (FR-1/FR-3)

**Given** a User created by an Admin (Story 1.3) with a bcrypt-hashed password
**When** they submit their credentials
**Then** authentication verifies the submitted password against the stored bcrypt hash; the plaintext password is never stored, never logged, and never included in any response or error payload (FR-1, PRD Privacy guardrail)

**Given** a successful login
**When** the JWT is issued
**Then** it carries an 8-hour expiry, matching a work shift so no one is logged out mid-service; on expiry the user is returned to Login and re-authenticates, with no refresh-token flow in v1 (AD-3, resolves PRD Open Question 1)

**Given** no valid session cookie
**When** any non-login, non-health route is requested
**Then** the request is rejected as unauthorized (NFR-2, AD-3)

**Given** the login route is hit from the frontend origin
**When** the request is made
**Then** CORS is enforced via an explicit allow-list of that origin, never a wildcard (AD-3), and `container.wire()` is activated for the `auth` module, the first entry in the `modules=[...]` list (AD-1)

**Given** the stray empty `backend/data_models/exceptions/` package left over from scaffolding
**When** this story touches the backend
**Then** it is removed, leaving top-level `backend/exceptions/` as the single designated location for custom exceptions (architecture spine, Deferred)

### Story 1.2: Role-Based Authorization Enforcement

As the system,
I want to restrict every state-changing action to the Roles permitted to perform it,
So that no User can perform actions outside their Role.

**Acceptance Criteria:**

**Given** an authenticated User whose Role is not permitted for a given action
**When** they attempt it
**Then** the system returns an explicit unauthorized (403) response and the action does not execute (FR-2)

**Given** an unauthenticated request to any non-public action
**When** it is made
**Then** it is rejected, not silently allowed (FR-2, NFR-2)

**Given** the current User's Role
**When** the frontend renders any screen
**Then** only actions permitted to that Role are shown as available (FR-2)

**Given** any protected route in any domain router
**When** its authorization is enforced
**Then** it goes through one shared FastAPI dependency, never re-derived per route (AD-3)

### Story 1.3: Admin Manages User Accounts

As an Admin,
I want to create, edit, deactivate, and reactivate User accounts,
So that I control who can access the system and with what role.

**Acceptance Criteria:**

**Given** valid new-user details (username, full name, role, initial password)
**When** an Admin submits the create-user form
**Then** a new User is created and can log in immediately with the assigned Role and that initial password (FR-3)

**Given** an Admin sets a new User's initial password
**When** the account is persisted
**Then** the password is stored only as a bcrypt hash in `password_hash`, never in plaintext, never logged, and never returned by any read endpoint (FR-1, FR-3, PRD Privacy guardrail)

**Given** the create-user form is submitted with a missing or blank password
**When** validation runs
**Then** it is rejected inline, an account is never created without a password (FR-3, UX-DR17)

**Given** a username that already exists (active or deactivated)
**When** an Admin tries to create it
**Then** the request is rejected as a duplicate (FR-3, UX-DR17)

**Given** an active User
**When** an Admin deactivates them
**Then** they can no longer log in, but their historical records remain intact and attributed to them (FR-3)

**Given** a deactivated User
**When** an Admin reactivates them
**Then** they can log in again (FR-3)

**Given** a User who has forgotten their password
**When** an Admin sets a new password on that account
**Then** the new password is hashed on the same path as an initial password, the previous hash is overwritten, the old password stops working immediately, and the User can log in with the new one (FR-3, FR-1)

**Given** any Admin-initiated password reset
**When** it is performed
**Then** it never reveals or requires the account's previous password, and there is no self-service or email-based reset path anywhere in v1 (FR-3)

**Given** the last remaining active Admin account
**When** an Admin attempts to deactivate or demote it
**Then** the action is rejected inline with "Rejected, at least one admin must stay active" (AD-15, UX-DR17)

**Given** a User's Role or name is edited
**When** the edit is saved
**Then** their historical records (Order Items prepared, Stock Movements logged, etc.) stay attributed to the account as it existed at the time (FR-3)

**Given** the Users screen
**When** it renders
**Then** it matches the UX mock with dense-row list styling (UX-DR8, UX-DR19) and holds the WCAG 2.2 AA accessibility floor established in Story 1.4 (UX-DR21)

**Given** the `admin` domain router does not yet exist
**When** this story adds it
**Then** `admin` is appended to `container.wire(modules=[...])`, never replacing the `auth` entry Story 1.1 added (AD-1)

### Story 1.4: Application Shell, Routing and Per-Role Navigation

As a staff member of any role,
I want the app to open on a working shell that shows me only my own surfaces,
So that every screen built in later epics has somewhere to live and I never see another role's tools.

**Acceptance Criteria:**

**Given** no routing exists in the frontend yet
**When** this story is built
**Then** React Router v7 is wired with a route per IA surface, and an authenticated-route guard redirects any unauthenticated visit to Login (AD-3, UX-DR19)

**Given** a logged-in User of any Role
**When** the shell renders
**Then** the nav lists only that Role's own surfaces, with no cross-role navigation anywhere, and login lands them on their Role's home surface — Waiter→Tables, Cook→Kitchen Display, Warehouse Manager→Ingredients, Admin→Menu Management (FR-2, UX-DR19)

**Given** the Login screen
**When** it renders
**Then** it is built per [key-login.html](../ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/mockups/key-login.html), showing the generic "Invalid username or password" copy inline on failure (FR-1, UX-DR17, UX-DR19)

**Given** any surface in the app
**When** a User clicks the theme toggle in the app bar
**Then** the theme flips light/dark and persists per browser/terminal (not per user account); Kitchen Display initializes dark, every other role's home initializes light (UX-DR7)

**Given** the MUI theme is being configured
**When** it is set up
**Then** `{colors.accent}`/`{colors.accent-dark}` override MUI's `primary` slot and every other Button variant stays stock MUI (UX-DR6), with dense-row styling (`size="small"`, 36px rows) available as the shared list/table convention (UX-DR8)

**Given** any surface is loading data for the first time
**When** it has not resolved yet
**Then** it renders MUI `Skeleton` rows/cards matching its expected layout — the shared cold-load pattern every later screen reuses (UX-DR15)

**Given** the shared connection-status UI
**When** it is built
**Then** one app-wide "Reconnecting..." state exists with automatic retry and no local-first write queue, driven by a transport-agnostic connection signal; Story 1.5 wires it to the live WebSocket (UX-DR16)

**Given** the shell and its shared components
**When** they are built
**Then** they meet the WCAG 2.2 AA contrast baseline in both themes, render a visible focus ring on every interactive element, and follow a logical tab order matching reading order — the accessibility floor every later surface inherits and must not regress (UX-DR21)

### Story 1.5: Real-Time Push Transport

As the system,
I want one authenticated WebSocket channel with a fixed event-naming convention,
So that every later feature pushes state changes the same way instead of each inventing its own.

_Note: like Story 1.0, this is enabling work rather than a user-visible feature. It is separated from
its first consumer (Story 3.3) because Stories 3.3, 4.2, 5.1 and 5.2 all emit over this channel, and
the naming convention it fixes has to exist before any of them are written against it._

**Acceptance Criteria:**

**Given** no WebSocket endpoint exists in the codebase
**When** this story is built
**Then** a single WebSocket endpoint is added, one connection per authenticated session, scoped to the connecting User's Role (AD-2)

**Given** a connection attempt
**When** it is opened
**Then** it is gated by the same JWT verified for REST routes, through the same shared dependency, and rejected if absent or expired (AD-3, NFR-2)

**Given** the `websockets` package is already present transitively via `uvicorn[standard]`
**When** the transport is implemented
**Then** no new backend dependency is added for it

**Given** any state change that other Roles must see
**When** the owning service layer commits it
**Then** it emits exactly once, from the service that owns the mutation, under the past-tense `{domain}.{event}` naming convention (e.g. `order.item_status_changed`) — fixed here so no later story reinvents the naming (AD-2)

**Given** a client is connected and an event is emitted
**When** the emission commits
**Then** the connected client receives it within 2 seconds, verified by a smoke test that emits one event and asserts receipt (NFR-1)

**Given** the connection drops
**When** the client detects it
**Then** it drives Story 1.4's shared "Reconnecting..." state and retries automatically, with no local-first write queue (UX-DR16)

## Epic 2: Menu, Recipes, Ingredients & Table Setup

Admin can build a sellable menu (dishes, categories, recipes) with the ingredients they reference, and configure the restaurant's physical tables, the master data every later epic builds on.

### Story 2.1: Create and Manage Ingredients

As a Warehouse Manager or Admin,
I want to create ingredient records,
So that they can be referenced by recipes and tracked in inventory.

**Acceptance Criteria:**

**Given** a name, unit of measure, minimum stock threshold, and optional initial stock
**When** a Warehouse Manager or Admin submits the create-ingredient form
**Then** a new Ingredient is created, defaulting current stock to zero if unspecified (FR-16)

**Given** an Ingredient name that already exists
**When** creation is attempted
**Then** it is rejected as a duplicate (FR-16, UX-DR17)

**Given** a newly created Ingredient
**When** a Recipe or Stock Movement is being defined
**Then** that Ingredient is immediately selectable (FR-16)

**Given** the `inventory` domain router does not yet exist
**When** this story adds it
**Then** `inventory` is appended to `container.wire(modules=[...])`, alongside the existing entries, not replacing them (AD-1)

### Story 2.2: Manage Menu Categories and Dishes

As an Admin,
I want to create, update, and mark dishes available or unavailable, and manage menu categories,
So that I control what's sellable.

**Acceptance Criteria:**

**Given** valid category details
**When** an Admin creates a Menu Category
**Then** it is available for grouping Dishes (FR-22)

**Given** valid dish details (name, description, price, prep time, category)
**When** an Admin creates a Dish
**Then** it is created, starting unavailable until it has a recipe (FR-22, AD-8)

**Given** a Dish with zero Recipe Ingredient lines
**When** an Admin attempts to mark it available
**Then** the toggle is disabled with an inline reason, "Cannot mark available, recipe has no ingredients" (FR-22, AD-8, UX-DR13)

**Given** a Dish is marked unavailable
**When** the change is saved
**Then** it is immediately rejected by future add-to-order attempts, but Order Items already in progress on already-open Orders are unaffected (FR-22)

### Story 2.3: Define a Dish's Recipe

As an Admin,
I want to define and edit the Recipe Ingredient lines that compose a Dish,
So that stock deduction and availability gating both work correctly.

**Acceptance Criteria:**

**Given** an existing Dish and a set of Ingredient + quantity + unit lines
**When** an Admin saves the Dish's recipe
**Then** those Recipe Ingredient lines are persisted (FR-23)

**Given** a Dish is currently available
**When** an Admin attempts to remove its last Recipe Ingredient line
**Then** the removal is rejected until the Dish is marked unavailable first (AD-8)

**Given** a Dish's Recipe is edited
**When** the Recipe is read back for any purpose
**Then** the currently-defined lines are returned, never a snapshot taken at an earlier time; this is what lets Epic 5's deduction read live Recipe state rather than a stale copy (FR-23, verified end-to-end in Story 5.2)

**Given** a Dish with zero Recipe Ingredient lines and a disabled availability toggle
**When** an Admin adds its first ingredient line
**Then** the availability gate control re-enables instantly, with no page reload (UX-DR13)

### Story 2.4: Manage Restaurant Tables

As an Admin,
I want to add and configure Restaurant Tables,
So that Waiters have tables to open orders against.

**Acceptance Criteria:**

**Given** a table number and capacity
**When** an Admin adds a new Restaurant Table
**Then** it is created with status `available` (FR-24)

**Given** a table number that already exists
**When** creation is attempted
**Then** it is rejected as a duplicate (FR-24, UX-DR17)

**Given** a Restaurant Table whose status is `available`
**When** an Admin edits its table number or capacity
**Then** the change is saved (FR-24)

**Given** a Restaurant Table whose status is `occupied` or `reserved`
**When** an Admin attempts to edit it
**Then** the edit is rejected and the Edit control is disabled with the inline reason "Rejected, table in use", re-enabling the moment the table returns to `available` (FR-24, UX-DR13, UX-DR17)

**Given** an Admin renames a table to a number another table already uses
**When** the edit is submitted
**Then** it is rejected as a duplicate with the same inline copy as the create path, table numbers stay unique across all tables (FR-24, UX-DR17)

**Given** a Waiter opens the table between the Admin loading the edit form and saving it
**When** the save commits
**Then** it is rejected rather than silently applied, via a guarded conditional update on the expected `available` status with a rowcount check (AD-6 extended to RestaurantTable, NFR-3)

**Given** Restaurant Tables cannot be deleted in v1
**When** an Admin views the Tables setup screen
**Then** no delete affordance exists anywhere on it, tables are only ever added and edited (FR-24, PRD Non-Goals)

**Given** the Tables setup screen
**When** it renders
**Then** it matches the UX mock with dense-row list styling (UX-DR8, UX-DR19)

### Story 2.5: Cook Browses the Dish Catalog

As a Cook,
I want to browse the dish catalog with each dish's recipe and plating notes,
So that I can see how to prepare something without asking an Admin or leaving the kitchen.

**Acceptance Criteria:**

**Given** a Cook opens the Dishes surface
**When** it loads
**Then** every Dish is listed with its name, description, price, prep time, category, availability, and its Recipe Ingredient lines (FR-25)

**Given** a Cook is viewing the Dishes surface
**When** they look for a way to change anything
**Then** no create, edit, availability-toggle, or delete control exists, this surface is strictly read-only and menu authoring stays Admin-only via Stories 2.2/2.3 (FR-25, FR-2)

**Given** no dishes exist on the menu yet
**When** the surface loads
**Then** it shows "No dishes on the menu yet" (UX-DR15)

**Given** an Admin changes a Dish's recipe or availability (Stories 2.2/2.3)
**When** a Cook next loads the Dishes surface
**Then** they see the current definition, never a stale copy (FR-25, FR-23)

## Epic 3: Table Service & Order Taking

A Waiter can open a table, build and adjust an order against the menu, and see live status, the front-of-house half of the core flow.

### Story 3.1: Open a Table and Start an Order

As a Waiter,
I want to mark an available table as occupied and start a new order,
So that I can begin taking a table's order.

**Acceptance Criteria:**

**Given** an available Table
**When** a Waiter opens it
**Then** the Table becomes `occupied` and a new Order starts with status `pending` and no items (FR-4)

**Given** a Table that is already `occupied` or `reserved`
**When** a Waiter attempts to open it into a new Order
**Then** the action is rejected (FR-4)

**Given** the Waiter's Tables grid
**When** it renders
**Then** each tile shows the table-status badge for `available`/`occupied`/`reserved` (UX-DR2), and "No tables configured yet" is shown when none exist (UX-DR15)

**Given** the `orders` domain router does not yet exist
**When** this story adds it
**Then** `orders` is appended to `container.wire(modules=[...])`, alongside the existing entries, not replacing them (AD-1)

### Story 3.2: Add Items to an Order

As a Waiter,
I want to add dishes with quantity and an optional note to an open order,
So that the kitchen knows what to prepare.

**Acceptance Criteria:**

**Given** an open Order and an available Dish
**When** a Waiter adds it with a quantity and optional note
**Then** a new Order Item is created at status `pending`, storing the Dish's current price as `price_at_add` (FR-5, AD-7)

**Given** a Dish currently marked unavailable
**When** a Waiter attempts to add it
**Then** the add is rejected inline with "Rejected, dish unavailable" (FR-5, UX-DR17)

**Given** an Order's item list
**When** it renders
**Then** each Order Item row shows its status badge (UX-DR1), and "No items added yet" is shown on a fresh Order (UX-DR15)

**Given** `price_at_add` does not yet exist as a column on `OrderItem`
**When** this story adds it
**Then** this story ships its own Alembic revision adding `price_at_add`, on top of the baseline established in Story 1.0 (AD-4)

### Story 3.3: View Live Order and Table Status

As a Waiter,
I want to see every table's and order item's current status update live,
So that I know what's happening without walking to the kitchen or refreshing.

**Acceptance Criteria:**

**Given** the transport and event-naming convention established in Story 1.5
**When** the order and table services commit a state change
**Then** they emit over that existing channel under the agreed `{domain}.{event}` names, adding no second transport and no competing naming scheme (AD-2)

**Given** any Order or Order Item state change committed by the service layer (today: a Waiter adding, editing, or cancelling an item; from Epic 5 onward also a Cook's status transitions)
**When** the change is committed
**Then** it appears on every other connected Waiter terminal's Tables grid and Table/Order detail within 2 seconds via WebSocket push, with no manual refresh (FR-6, NFR-1, AD-2)

**Given** the system is used from multiple Waiter terminals simultaneously
**When** any one of them makes a change
**Then** every other Waiter terminal sees every Table and every Order, since v1 has no per-waiter filtering (FR-6, NFR-5)

**Given** the WebSocket connection drops
**When** the frontend detects it
**Then** a "Reconnecting..." state is shown and the connection retries automatically (UX-DR16)

### Story 3.4: Edit or Cancel an Order Item

As a Waiter, Cook, or Admin,
I want to edit a pending order item or cancel an order item,
So that mistakes and last-minute changes can be corrected without blocking the table.

**Acceptance Criteria:**

**Given** a `pending` Order Item
**When** a Waiter edits its quantity or note
**Then** the change is saved (FR-7)

**Given** a `pending` Order Item
**When** a Waiter, Cook, or Admin cancels it
**Then** it moves to `cancelled` with no stock impact, since nothing was deducted yet (FR-7)

**Given** an `in_preparation` Order Item
**When** a Waiter, Cook, or Admin cancels it
**Then** it moves to `cancelled`, but its prior stock deduction is NOT automatically reversed (FR-7, AD-11); the confirm dialog states this plainly before the cancel is applied (UX-DR12)

**Given** an `in_preparation` Order Item
**When** anyone attempts to edit its quantity or note instead of cancelling
**Then** the edit is rejected, only cancellation is available once prep has started (FR-7)

**Given** an Order containing a cancelled Order Item
**When** any aggregate read of that Order is performed
**Then** the cancelled item is excluded, so the status-derivation and readiness-for-close rules built in Epic 5 (FR-12, FR-8) never see it

**Given** two concurrent field edits to the same Order Item, outside the atomic transition paths
**When** both commit
**Then** last-write-wins applies, with no optimistic locking and no conflict UI (NFR-6)

**Given** `cancelled` does not yet exist as a value on the `OrderItemStatus` enum
**When** this story adds it
**Then** the enum change ships with its own Alembic migration on top of the baseline established in Story 1.0, per AD-4 (exact literal name left to this migration, per the architecture spine's Deferred section)

## Epic 4: Warehouse Inventory Operations & Low-Stock Alerts

A Warehouse Manager can log manual stock movements (purchase/waste/adjustment), view stock levels/shortage status, and get alerted the instant any movement crosses an ingredient below threshold, fully standalone, independent of the kitchen's automatic path.

### Story 4.1: Record Manual Stock Movements

As a Warehouse Manager,
I want to log purchase, waste, or adjustment stock movements,
So that inventory stays accurate as things happen outside the kitchen's automatic path.

**Acceptance Criteria:**

**Given** a quantity and optional note
**When** a Warehouse Manager logs a `purchase` movement
**Then** the Ingredient's current stock increases accordingly and the movement is recorded in the append-only audit trail (FR-15, NFR-4)

**Given** a quantity and optional note
**When** a Warehouse Manager logs a `waste` movement or a negative `adjustment`
**Then** the Ingredient's current stock decreases accordingly, even if it drives stock negative, never floor-capped at zero (FR-15, AD-16)

**Given** a Stock Movement shown on Ingredient detail
**When** its type is rendered
**Then** the movement type chip uses a neutral color scheme, deliberately distinct from the status traffic-light convention (UX-DR14)

### Story 4.2: Low-Stock Alert

As a Warehouse Manager,
I want to be alerted the instant any stock movement drops an ingredient below its threshold,
So that I can react before it becomes a problem.

**Acceptance Criteria:**

**Given** a Stock Movement that decreases an Ingredient's current stock (`waste` or a negative `adjustment` today; automatic `consumption` once Epic 5 exists) crosses it below its minimum threshold
**When** the movement commits
**Then** a Low-Stock Alert becomes active for that Ingredient (FR-14)

**Given** an Ingredient already below threshold
**When** another stock-decreasing movement lands
**Then** no duplicate alert is generated, at most one active alert per Ingredient-in-shortage (FR-14)

**Given** two stock-decreasing movements cross the threshold at nearly the same instant
**When** both commit
**Then** exactly one active alert results, not two (FR-14, atomic check-and-create)

**Given** a Stock Movement brings the Ingredient back at or above threshold
**When** it commits
**Then** the alert clears automatically, with no manual dismiss (FR-14)

**Given** one or more active Low-Stock Alerts
**When** the Warehouse Manager's UI renders
**Then** the Alerts nav badge shows a persistent count with no toast (UX-DR5), and the Alerts screen lists one Alert row per Ingredient-in-shortage reading "Stock low: {ingredient} ({current stock}{unit} left)" (UX-DR10)

**Given** no active shortages
**When** the Alerts screen loads
**Then** it shows "No active shortages" (UX-DR15)

### Story 4.3: View Ingredient Stock Levels

As a Warehouse Manager,
I want to see all ingredients with their current stock, threshold, and shortage status,
So that I can spot problems at a glance.

**Acceptance Criteria:**

**Given** the Ingredients screen loads
**When** a Warehouse Manager views it
**Then** every Ingredient's current stock, threshold, and shortage status are shown (FR-17)

**Given** an Ingredient is currently below threshold
**When** the list renders
**Then** it is visually distinguished (red plus warning icon) and sorted to the top of the list, not just flagged in place (UX-DR9)

**Given** no ingredients exist yet
**When** the screen loads
**Then** it shows "No ingredients recorded yet" (UX-DR15)

**Given** an Ingredient's detail is opened
**When** it loads
**Then** its movement history is shown, or "No stock movements yet" if empty (UX-DR15)

## Epic 5: Kitchen Fulfillment, Automatic Stock Deduction & Close-Out

A Cook works orders to ready in real time, triggering the same automatic stock deduction and low-stock alert logic Epic 4 built, and the Waiter marks served and closes the table, the full order-to-close loop.

### Story 5.1: View Incoming Orders in Real Time (Kitchen Display)

As a Cook,
I want to see new and updated order items on the kitchen display instantly,
So that I never miss or double-handle an item.

**Acceptance Criteria:**

**Given** a new Order Item is added by a Waiter (Epic 3)
**When** it's submitted
**Then** it appears on the Kitchen Display grouped under its Table's card within 2 seconds via WebSocket push, with no manual refresh (FR-9, NFR-1, AD-2)

**Given** the Kitchen Display has no orders in the queue
**When** it loads
**Then** it shows "No orders in the queue" (UX-DR15)

**Given** the WebSocket connection drops
**When** detected
**Then** "Reconnecting..." is shown and retried automatically (UX-DR16), most critical on this surface

**Given** a Cook opens the Kitchen Display
**When** it renders
**Then** it initializes in dark theme (UX-DR7), cards render at elevation 1, and each Order Item row within a card shows its status badge (UX-DR1)

**Given** the `kitchen` domain router does not yet exist
**When** this story adds it
**Then** `kitchen` is appended to `container.wire(modules=[...])`, alongside the existing entries, not replacing them (AD-1)

### Story 5.2: Pick Up and Progress an Order Item, with Atomic Stock Deduction

As a Cook,
I want to pick up a pending item and later mark it ready,
So that the kitchen's prep state is accurate and stock reflects real consumption the moment it starts.

**Acceptance Criteria:**

**Given** a `pending` Order Item
**When** a Cook picks it up
**Then** in one atomic DB transaction: the item moves to `in_preparation`, the acting Cook is recorded against it, each Recipe Ingredient's quantity (times the item's quantity) is deducted from stock, and a `consumption` Stock Movement referencing the Order is recorded (FR-10, FR-13, AD-6, NFR-3, NFR-4)

**Given** that same transition is not re-triggered
**When** a Cook picks up an item once
**Then** deduction happens exactly once, re-triggering does not double-deduct (FR-13, AD-6)

**Given** an `in_preparation` Order Item
**When** a Cook marks it ready ("passed")
**Then** it moves to `ready` as a pure status change with no further stock movement (FR-10)

**Given** an Order Item is `pending`
**When** any attempt is made to move it directly to `ready`
**Then** it is rejected, it cannot skip `in_preparation` (FR-10)

**Given** an Order Item is `in_preparation` or `ready`
**When** any attempt is made to reverse its transition
**Then** it is rejected, no undo; correction goes through Epic 3's cancel path (FR-10)

**Given** a deactivated Cook has an `in_preparation` item
**When** any other active Cook views the Kitchen Display
**Then** they can transition that item to `ready` themselves (FR-10, attribution not access lock)

**Given** a pick-up would deduct more of an Ingredient than currently in stock
**When** the transition commits
**Then** it still succeeds (stock is never floor-capped at zero, AD-16), and the resulting `consumption` movement triggers Epic 4's existing Low-Stock Alert check exactly as a manual movement would (FR-13, reuses FR-14, no new alert logic built here)

**Given** an Order Item on a Kitchen Display card
**When** a Cook advances its status
**Then** the advance control is a single large click target sized for reading at a distance (UX-DR19), and the status badge updates on both the Kitchen Display and the Waiter's screen via the same WebSocket push (AD-2)

### Story 5.3: Order Status Derives From Its Items

As the system,
I want an Order's status to automatically reflect the aggregate of its non-cancelled Order Items,
So that Waiters and Cooks always see an accurate summary status.

**Acceptance Criteria:**

**Given** an Order with a mix of `pending` and `ready` non-cancelled items
**When** status is computed
**Then** the Order shows `in_preparation`, not `ready` (FR-12)

**Given** an Order where every non-cancelled item is `ready`
**When** status is computed
**Then** the Order shows `ready` (FR-12)

**Given** an Order with zero non-cancelled Order Items
**When** status is computed
**Then** the Order shows `pending` (FR-12)

**Given** the Order's derived status reaches `ready`
**When** that happens
**Then** the Waiter's Table tile switches to the attention-state treatment, layered on top of the base table-status badge (FR-12, UX-DR3)

### Story 5.4: Mark an Order Served and Close the Table

As a Waiter,
I want to mark a ready order as served and then close the table,
So that I can finish the table and free it up for the next guests.

**Acceptance Criteria:**

**Given** an Order's status is `ready` (or it has zero non-cancelled Order Items)
**When** a Waiter marks it `served`
**Then** the Order moves to `served` as a pure status change (FR-11)

**Given** any non-cancelled Order Item is not yet `ready`
**When** a Waiter attempts to mark the Order `served`
**Then** the action is rejected (FR-11)

**Given** an Order is `served`
**When** a Waiter closes it
**Then** the total is computed as the sum of each non-cancelled Order Item's stored `price_at_add x quantity` (AD-7), the Order moves to `closed`, and the Table returns to `available` (FR-8)

**Given** an Order has not yet reached `served`
**When** a Waiter attempts to close it
**Then** the action is hard-blocked with no override, a stuck item must be cancelled first via Epic 3's FR-7 (FR-8)

**Given** an Order is closed
**When** its total_amount is checked afterward
**Then** it is populated and immutable (FR-8)

**Given** an Order eligible to be closed
**When** the Waiter clicks Close
**Then** it applies with no separate confirm step, unlike the cancel path which does confirm, since closing is not a data-loss risk (UX-DR12 contrast)

**Given** a table whose Order is marked `served`
**When** that happens
**Then** the Waiter's "tables need attention" counter clears for that table automatically, with no dismiss action (UX-DR4)

## Epic 6: Smart Chef, Recipe Suggestions & Assistant Chat

A Cook can generate an AI recipe suggestion from live stock and iterate on it via chat; an Admin can confirm a suggestion into a real menu Dish.

### Story 6.1: Generate a Recipe Suggestion from Current Stock

As a Cook,
I want to request an AI-generated recipe suggestion based on what's actually in stock,
So that I can turn surplus into a usable dish idea instead of letting it go to waste.

**Acceptance Criteria:**

**Given** a Cook requests a suggestion, optionally with a free-text direction
**When** the request is submitted
**Then** the system generates one using a snapshot of currently-available Ingredient stock, prioritizing at-risk-of-waste ingredients, and persists the prompt used, the stock snapshot, and the resulting suggestion as a Recipe Suggestion (FR-18)

**Given** a free-text direction is supplied
**When** the prompt is constructed
**Then** the direction steers the suggestion but never overrides the stock-availability constraint, and becomes part of the persisted `prompt_used` rather than a separate field (FR-18)

**Given** a Cook already has a generation in flight
**When** they submit a second request before the first finishes
**Then** the second is rejected inline, not queued (FR-18, AD-14)

**Given** the OpenAI call fails or times out
**When** that happens
**Then** the system surfaces "Couldn't generate a suggestion right now," persists no partial or orphaned Recipe Suggestion row, and shows a state distinguishable from "still generating" (FR-21, AD-14, UX-DR18)

**Given** any OpenAI call issued by this story
**When** it is made
**Then** it goes through a `backend/clients/` adapter behind an interface, never called directly from `services/` (AD-12)

**Given** a generated Recipe Suggestion
**When** its card renders
**Then** it shows the requesting Cook and the ingredients the suggestion drew on (UX-DR11)

**Given** any OpenAI call is issued for a suggestion or a chat message
**When** it is made
**Then** the resulting record carries the requesting User's id and its owning Chat Session or Recipe Suggestion, so every billed call is attributable for later cost auditing; no hard per-user or per-day cost cap is enforced in v1 (PRD 4.5 feature NFR)

**Given** the `smart_chef` domain router does not yet exist
**When** this story adds it
**Then** `smart_chef` is appended to `container.wire(modules=[...])`, alongside the existing entries, not replacing them (AD-1)

### Story 6.2: Confirm a Recipe Suggestion into a Live Dish

As an Admin,
I want to confirm a promising Recipe Suggestion into a real, orderable Dish,
So that Smart Chef's ideas can actually reach the menu under human review.

**Acceptance Criteria:**

**Given** a Recipe Suggestion
**When** an Admin confirms it
**Then** a Dish and Recipe are created or updated via Epic 2's normal Menu Management flow, and the resulting Recipe stores a nullable back-reference to the originating Recipe Suggestion (FR-19)

**Given** a Recipe Suggestion is confirmed
**When** the confirmation happens
**Then** no code path allows it to write directly to the Dish/Recipe tables outside that Admin-driven flow (FR-19)

**Given** a manually-defined Recipe not sourced from a suggestion
**When** its provenance is checked
**Then** the reference is null (FR-19)

**Given** a Recipe Suggestion
**When** an Admin dismisses it instead of confirming
**Then** it is marked with a persisted `dismissed` status, leaving the active Recipe Suggestions list but retained for audit (UX-DR20)

**Given** a Recipe Suggestion card on the Admin's review surface
**When** it renders
**Then** it offers exactly two actions, Confirm into Dish (accent primary button, UX-DR6) and Dismiss (outlined/text button, UX-DR11)

**Given** no suggestions awaiting review
**When** the surface loads
**Then** it shows "No suggestions awaiting review" (UX-DR15)

**Given** `dismissed` does not yet exist as a column on `AIRecipeSuggestion`
**When** this story adds it
**Then** it ships with its own Alembic migration on top of the baseline established in Story 1.0, per AD-4

### Story 6.3: Consult, Version, and Improve Recipes via Smart Assistant Chat

As a Cook,
I want to open a chat session with the Smart Assistant to discuss and iterate on a Recipe or Recipe Suggestion,
So that I can refine an idea through conversation instead of guessing.

**Acceptance Criteria:**

**Given** a Cook opens a Chat Session tied to a Recipe or Recipe Suggestion
**When** they send a message
**Then** it is persisted with its role (`user`/`assistant`) in order, retrievable as a full conversation (FR-20)

**Given** an existing session with prior messages
**When** a Cook sends a follow-up
**Then** the assistant's response has access to that session's prior messages as conversational context (FR-20)

**Given** any Cook, not just the session's creator
**When** they open a session or suggestion created by a different Cook
**Then** they can do so without special permission, the default list view just sorts the current Cook's own items first, as a personalization default, not an access boundary (FR-20, AD-9, AD-10)

**Given** the OpenAI call for a chat message fails or times out
**When** that happens
**Then** the system surfaces a clear failure state and persists no dangling Chat Message with empty or null content (FR-21)

**Given** a Cook scrolls back through a session's history
**When** they do
**Then** they can see an earlier iteration of the recipe under discussion, this ordered history is the version record, with no separate version-entity or diff UI in v1 (FR-20)

**Given** a Cook has no chat sessions
**When** the Smart Chef surface loads
**Then** it shows "No chat sessions yet" (UX-DR15)
