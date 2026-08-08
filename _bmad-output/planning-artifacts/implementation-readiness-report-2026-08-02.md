---
stepsCompleted: [1, 2, 3, 4, 5, 6]
status: complete
verdict: READY (all 10 findings resolved 2026-08-02)
documentsUnderAssessment:
  prd:
    - _bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md
    - _bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/addendum.md
    - _bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/polish-prd.md
    - _bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/polish-addendum.md
  architecture:
    - _bmad-output/planning-artifacts/architecture/architecture-Restaurant-Kitchen-Management-System-2026-07-30/ARCHITECTURE-SPINE.md
  ux:
    - _bmad-output/planning-artifacts/ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/DESIGN.md
    - _bmad-output/planning-artifacts/ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/EXPERIENCE.md
  epics:
    - _bmad-output/planning-artifacts/epics.md
  supportingContext:
    - _bmad-output/project-context.md
    - docs/database-schema.md
    - docs/application-flow.md
---

# Implementation Readiness Assessment Report

**Date:** 2026-08-02
**Project:** Restaurant-Kitchen-Management-System

---

## Step 1: Document Discovery

### PRD Files Found

**Whole Documents:** none at `{planning_artifacts}` top level

**Folder-based Documents:**

- Folder: `prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/`
  - `prd.md` (48.4 KB) — **PRIMARY**
  - `addendum.md` (11.8 KB) — **PRIMARY** (decisions supplement)
  - `polish-prd.md` (12.7 KB) — polish pass
  - `polish-addendum.md` (8.6 KB) — polish pass
  - `reconcile-brownfield.md` (5.8 KB) — review artifact
  - `reconcile-course-guidelines.md` (5.6 KB) — review artifact
  - `reconcile-proposal.md` (8.3 KB) — review artifact
  - `review-edge-case-hunter.md` (13.9 KB) — review artifact
  - `review-rubric.md` (12.3 KB) — review artifact
  - `.memlog.md` (14.9 KB) — workflow memory log

### Architecture Files Found

**Whole Documents:** none at `{planning_artifacts}` top level

**Folder-based Documents:**

- Folder: `architecture/architecture-Restaurant-Kitchen-Management-System-2026-07-30/`
  - `ARCHITECTURE-SPINE.md` (20.1 KB) — **PRIMARY**
  - `reviews/review-incompatibility.md` (15.8 KB) — review artifact
  - `reviews/review-rubric.md` (13.1 KB) — review artifact
  - `reviews/review-version-check.md` (11.3 KB) — review artifact
  - `reviews/review-reconcile-prd.md` (9.5 KB) — review artifact
  - `reviews/review-reconcile-brownfield.md` (8.4 KB) — review artifact
  - `.memlog.md` (10.7 KB) — workflow memory log

### Epics & Stories Files Found

**Whole Documents:**

- `epics.md` (42.1 KB, modified 2026-08-02) — **PRIMARY**

**Folder-based Documents:** none

### UX Design Files Found

**Whole Documents:** none at `{planning_artifacts}` top level

**Folder-based Documents:**

- Folder: `ux-designs/ux-Restaurant-Kitchen-Management-System-2026-07-31/`
  - `DESIGN.md` (17.8 KB) — **PRIMARY**
  - `EXPERIENCE.md` (28.0 KB) — **PRIMARY**
  - `review-rubric.md` (14.1 KB) — review artifact
  - `.memlog.md` (7.7 KB) — workflow memory log
  - `mockups/` — 13 key-screen HTML mockups
  - `.working/` — 13 working-copy HTML mockups (superseded by `mockups/`)

### Issues Found

**Duplicates:** ✅ None. Each document type exists in exactly one canonical form. The BMad workflow folders contain one primary artifact plus supporting review/memlog files — this is the expected output shape, not a whole-vs-sharded conflict. No `index.md` shard sets exist.

**Missing Documents:** ✅ None. All four required document types (PRD, Architecture, UX, Epics & Stories) are present.

**Notes carried into assessment:**

- `.working/` mockups duplicate `mockups/` by filename but are the pre-finalization working copies; `mockups/` is authoritative.
- `_bmad-output/project-context.md` is dated 2026-07-24 and predates the Postgres/SQLAlchemy integration and the architecture spine. It is loaded as workflow context but the ARCHITECTURE-SPINE is the newer authority where the two conflict — flagged for validation in later steps.

**Status:** Document Discovery complete, no blocking issues.

---

## Step 2: PRD Analysis

**Source read in full:** `prd.md` (452 lines, 48 KB) + `addendum.md` (85 lines). Both polish files
(`polish-prd.md`, `polish-addendum.md`) confirmed to be **recommendations-only** — each states
explicitly that nothing was applied to the source document. They introduce no requirements and are
correctly excluded from the epics' `inputDocuments`.

### Functional Requirements

Extracted verbatim from `prd.md` §4 (`#### FR-n` headings). Grouped by feature area.

**§4.1 Authentication & Access Control**

- **FR-1 — User login:** A User can authenticate with a username and password and receive a session identifying their Role.
- **FR-2 — Role-based authorization:** The system restricts every state-changing action to the Roles permitted to perform it, and the UI only surfaces actions the current User's Role is permitted to take. *Out of scope: per-resource permissions beyond the four fixed Roles — v1 is Role-level only.*
- **FR-3 — Admin manages user accounts:** An Admin can create a User account (username, full name, Role), edit an existing User's Role or full name, deactivate an active User, and reactivate a previously deactivated User. *Binding rule: deactivating/demoting the last active Admin is rejected.*

**§4.2 Table & Order Management (Waiter)**

- **FR-4 — Open a table and start an order:** A Waiter can mark an available Table as occupied and start a new Order tied to it. *`reserved` treated as `occupied` (cannot be opened).*
- **FR-5 — Add items to an order:** A Waiter can add one or more Order Items (Dish + quantity + optional note) to an open Order. *Unavailable Dish rejected; `price_at_add` stored at add time.*
- **FR-6 — View live order and table status:** A Waiter can see the current status of every Table and every Order Item in the system, reflecting kitchen-side updates without manual refresh. *No per-waiter filtering in v1.*
- **FR-7 — Edit or cancel an order item:** A Waiter can edit quantity/note or cancel while `pending`; once `in_preparation`, a Waiter, Cook, or Admin can cancel but not edit. *Cancelled items excluded from FR-12 derivation and FR-8 close check. Cancelling `in_preparation` does **not** auto-reverse stock deduction.*
- **FR-8 — Close a table:** A Waiter can close an Order once it is `served`, computing total from non-cancelled items' stored `price_at_add`, setting Order to `closed`, returning Table to `available`. *Hard-blocked before `served`, no override.*

**§4.3 Kitchen Display & Prep Workflow (Cook)**

- **FR-9 — View incoming orders in real time:** A Cook sees new and updated Order Items on the kitchen display as submitted, without manual refresh.
- **FR-10 — Update an order item's status:** A Cook can move an Order Item `pending` → `in_preparation` (recording the acting Cook, triggering FR-13 deduction) and `in_preparation` → `ready`. *No skip `pending`→`ready`; no reverse transitions; recorded Cook is attribution, not an access lock.*
- **FR-11 — Mark an order served:** A Waiter can mark an Order `served` once its status is `ready`. *An Order with zero non-cancelled items may be marked `served` directly.*
- **FR-12 — Order status derives from its items:** An Order's `pending`/`in_preparation`/`ready` status reflects the aggregate of its non-cancelled Order Items' statuses. *`served` and `closed` are set explicitly, not derived. Zero non-cancelled items ⇒ `pending`.*

**§4.4 Inventory & Stock Automation (Warehouse Manager)**

- **FR-13 — Automatic stock deduction on preparation:** On transition to `in_preparation`, deduct each Recipe Ingredient's quantity × item quantity and record a `consumption` Stock Movement referencing the Order. *Exactly once per transition; no double-deduct.*
- **FR-14 — Low-stock alert:** After any stock-decreasing Stock Movement (`consumption`, `waste`, negative `adjustment`), check whether the Ingredient is below threshold and surface a Low-Stock Alert. *At most one active alert per Ingredient-in-shortage; check-and-create is atomic; alert clears when back at/above threshold.*
- **FR-15 — Record manual stock movements:** A Warehouse Manager can log a `purchase`, `waste`, or `adjustment` movement with quantity and optional note. *Stock is never floor-capped at zero.*
- **FR-16 — Create an ingredient:** A Warehouse Manager or Admin can create an Ingredient (name, unit, min threshold, initial stock defaulting to zero). *Ingredient names are unique.*
- **FR-17 — View ingredient stock levels:** A Warehouse Manager can view all Ingredients with current stock, threshold, and shortage status, visibly distinguishing in-shortage ingredients.

**§4.5 Smart Chef (AI-Powered)**

- **FR-18 — Generate a recipe suggestion from current stock:** A Cook can request an AI-generated suggestion from a snapshot of currently-available stock (prioritizing at-risk ingredients), optionally steered by free-text direction; request, suggestion, and snapshot persist as a Recipe Suggestion. *At most one generation in flight per Cook (reject, not queue); direction folds into `prompt_used`.*
- **FR-19 — Recipe Suggestion requires admin confirmation to become a menu item:** A Recipe Suggestion never itself creates/modifies a live Dish; promotion is a separate Admin action. *Resulting Recipe stores a nullable back-reference to the originating Suggestion; manual Recipes leave it null.*
- **FR-20 — Consult, version, and improve recipes via Smart Assistant chat:** A Cook can open a Chat Session to discuss, revise, and iterate on a Recipe or Recipe Suggestion; messages/sessions persist. *"Manage versions" is satisfied conversationally — ordered chat history IS the version record, no separate version entity or diff UI. Sessions are shared (Role-level), current-Cook-first is a display default only.*
- **FR-21 — Graceful AI degradation:** If the OpenAI call for FR-18 or FR-20 fails/times out, surface a clear failure state and persist no partial or corrupt record. *No orphaned Suggestion row, no dangling Message with empty/null content; error state distinguishable from "still generating."*

**§4.6 Menu & Administration**

- **FR-22 — Manage menu dishes and categories:** An Admin can create, update, and mark a Dish available/unavailable, and manage Menu Categories. *Unavailable blocks new adds only — in-flight items proceed. A Dish cannot be marked `available` with zero Recipe Ingredient lines.*
- **FR-23 — Define a dish's recipe:** An Admin can define/edit the set of Recipe Ingredient lines (Ingredient + quantity + unit) composing a Dish. *FR-13 always uses the currently-defined Recipe, not a stale copy.*
- **FR-24 — Manage restaurant tables:** An Admin can **add and configure** Restaurant Tables (table number, capacity). *Table numbers are unique.*

**Total FRs: 24** (FR-1 … FR-24, contiguous, no gaps)

### Non-Functional Requirements

Extracted from `prd.md` "Cross-Cutting NFRs" section.

- **NFR-1 (Real-time propagation):** An Order Item status change (creation or transition) is visible on the relevant other Role's screen (Waiter ↔ Cook) within **2 seconds**, with no manual refresh. Explicitly a **push** requirement, not short-interval polling. *The 2-second figure itself is an unconfirmed assumption; push-not-poll was confirmed.*
- **NFR-2 (Authorization is universal):** No mutating action executes without an authenticated session carrying a permitted Role. No "trusted internal" bypass.
- **NFR-3 (Stock/order consistency):** FR-13 deduction and FR-10/FR-12 status transitions must be atomic w.r.t. concurrent requests — two near-simultaneous transitions on the same Order Item must not both apply; a deduction must never be partially applied across a Recipe's Ingredients.
- **NFR-4 (Auditability):** Every change to an Ingredient's stock is traceable to exactly one Stock Movement — no code path mutates `current_stock` without a corresponding movement.
- **NFR-5 (Concurrent multi-terminal use):** At least four distinct simultaneous terminals/sessions against one shared backend is baseline expected load, not a stress-test edge case.
- **NFR-6 (Concurrent-edit resolution):** Simultaneous edits to the same Table/Order/Order Item outside NFR-3's atomic paths resolve **last-write-wins** in v1 — no optimistic locking, no conflict UI.

**Total cross-cutting NFRs: 6** (NFR-1 … NFR-6)

**Plus one feature-specific NFR (§4.5, unnumbered):**

- **Cost attribution:** Every OpenAI API call is attributable to a specific User and Chat Session/Suggestion for later cost auditing. No hard per-user or per-day cost cap is enforced in v1 (confirmed policy decision).

### Additional Requirements

**Constraints and Guardrails (unnumbered, binding):**

- **Safety:** AI-generated Recipe Suggestions are drafts until a human Admin promotes them — the system never auto-publishes AI output as sellable/servable.
- **Privacy:** Only staff data is held (username, hashed password, full name, Role) — no diner PII anywhere in v1. Passwords hashed, never stored or logged in plaintext.
- **Cost:** Smart Chef makes real billed OpenAI calls; v1 ships with no enforced ceiling (deliberate).
- **Platform:** Single responsive React web application, multi-terminal, no mobile-native or desktop-native build.

**MVP Scope (§6):** FR-1 through FR-24 in full — deliberately the entire v1, no trimmed subset.

**Success Metrics (§7):** SM-1 (full vertical slice runs live in defense demo, no manual DB intervention), SM-2 (live Smart Chef suggestion + ≥1 chat iteration), SM-3 (Low-Stock Alert fires as a real consequence of the SM-1 flow, not staged), SM-4 (every Role has ≥1 distinct demo-able action). Counter-metrics SM-C1 (do not optimize feature breadth) and SM-C2 (do not optimize AI novelty over stock-constraint fidelity).

**Non-Goals (§5, 11 items):** no customer-facing surface; no payment/POS; no delivery integration; no multi-location; no native mobile; no kitchen printer; no offline mode; no analytics/BI dashboards; no staff scheduling; no table reservation *workflow* (the `reserved` enum value exists but is settable-state-only); no automated nutritional/allergen checking; no optimistic locking/conflict UI.

**Open Questions still carried by the PRD (§8) — 2 items, both material to implementation:**

1. Session/auth *behavioral* question — should a session survive a browser refresh mid-shift, and for how long? PRD explicitly says this "is a product decision this PRD should eventually pin down."
2. Does `table_number` uniqueness (FR-24) need to survive a deleted/deactivated table being renumbered, or is table deletion out of scope entirely? **"No FR currently covers removing or renumbering a table."**

**Assumptions Index (§9):** 18 entries, of which 7 are marked *confirmed decisions* (FR-8 hard-block, FR-20 conversational versioning, FR-20 shared sessions, §4.5 no cost cap, FR-19 provenance link, NFR-6 last-write-wins, FR-13 deduction timing) and the remainder remain unconfirmed policy assumptions (novelty claim, UJ-5 human gate, §4.1 session mechanism, FR-4 `reserved` handling, FR-7 no auto-reversal, FR-10 no reverse transitions, FR-18 prompt-enforced stock constraint, FR-18 reject-not-queue, FR-22 soft-delete, FR-24 analyst-inferred).

### PRD Completeness Assessment

**Overall: strong.** The PRD is unusually rigorous for this stage — requirements are globally numbered and stable, every FR carries explicit testable consequences, assumptions are tagged inline *and* indexed, and non-goals are stated affirmatively rather than left implicit. It has already survived a rubric review and an edge-case-hunter pass. Vocabulary is Glossary-anchored and used consistently across FRs, UJs, and feature prose.

**Transcription fidelity into `epics.md`: verified clean.** The epics file's own Requirements Inventory reproduces all 24 FRs and all 6 NFRs with faithful (compressed but non-distorting) wording. The circularity risk that motivated this step did not materialize — no requirement was dropped or reworded in transit.

**Three gaps identified, carried into Step 3 for coverage validation:**

1. **[MEDIUM] PRD Open Question 2 (table delete/renumber) fell through the crack between architecture and epics.** The architecture memlog explicitly deferred it: *"Table delete/renumber (PRD's other open question) stays out of scope for this architecture pass — it's a product/FR-level decision, not an architectural one; **deferred to epics/stories**."* `epics.md` contains **zero** occurrences of delete/remove/renumber for tables. It was formally handed to this stage and never picked up. Compounding this: FR-24 reads "add **and configure**," but Story 2.4's acceptance criteria cover only *add* + duplicate rejection — there is no AC for editing a table's number or capacity at all.

2. **[LOW-MEDIUM] PRD Open Question 1 (session duration) resolved only as an unratified architecture assumption, absent from story ACs.** The architecture memlog records `[ASSUMPTION] JWT session duration: 8-hour access token … silent re-login on expiry rather than a refresh-token flow — resolves the PRD's open 'session-survives-refresh duration' question; **flag for Ofek's review**.` That review flag was never closed, and Story 1.1 specifies the JWT httpOnly cookie mechanism but states no expiry. A developer implementing Story 1.1 has no AC telling them what to set.

3. **[LOW] §4.5 cost-attribution feature-NFR has no explicit story coverage.** Because it is unnumbered, it was not swept up by the FR/NFR transcription. Epic 6's stories persist `prompt_used`, the stock snapshot, and the requesting Cook, so per-User/per-Suggestion attribution is *structurally* satisfied by the existing `user_id` FKs on `AIRecipeSuggestion`/`AIChatSession` — but no acceptance criterion states the requirement, so nothing prevents it being lost.

**Status:** PRD Analysis complete. Proceeding to Epic Coverage Validation.

---

## Step 3: Epic Coverage Validation

**Source read in full:** `epics.md` (706 lines) — Requirements Inventory, Additional Requirements
(13 architecture ADs), UX Design Requirements (UX-DR1…UX-DR21), Epic List, FR Coverage Map, and all
21 stories across 6 epics.

### Epic FR Coverage Extracted

The epics document carries its own explicit FR Coverage Map (line 124) plus per-epic `**FRs covered:**` claims:

- **Epic 1** — Staff Accounts & Access Control: FR-1, FR-2, FR-3 (Stories 1.1–1.3)
- **Epic 2** — Menu, Recipes, Ingredients & Table Setup: FR-16, FR-22, FR-23, FR-24 (Stories 2.1–2.4)
- **Epic 3** — Table Service & Order Taking: FR-4, FR-5, FR-6, FR-7 (Stories 3.1–3.4)
- **Epic 4** — Warehouse Inventory Operations & Low-Stock Alerts: FR-14, FR-15, FR-17 (Stories 4.1–4.3)
- **Epic 5** — Kitchen Fulfillment, Stock Deduction & Close-Out: FR-8, FR-9, FR-10, FR-11, FR-12, FR-13 (Stories 5.1–5.4)
- **Epic 6** — Smart Chef, Recipe Suggestions & Assistant Chat: FR-18, FR-19, FR-20, FR-21 (Stories 6.1–6.3)

**Total FRs claimed in epics: 24.** Every claim was verified against the actual story acceptance
criteria rather than accepted at face value.

### Coverage Matrix

| FR | Requirement | Epic Coverage | Status |
|---|---|---|---|
| FR-1 | User login | Epic 1 / Story 1.1 | ✓ Covered *(hashing consequence has no AC — see L-2)* |
| FR-2 | Role-based authorization | Epic 1 / Story 1.2 | ✓ Covered |
| FR-3 | Admin manages user accounts | Epic 1 / Story 1.3 | ⚠️ **Covered but not implementable — see B-1** |
| FR-4 | Open a table and start an order | Epic 3 / Story 3.1 | ✓ Covered |
| FR-5 | Add items to an order | Epic 3 / Story 3.2 | ✓ Covered |
| FR-6 | View live order and table status | Epic 3 / Story 3.3 | ✓ Covered |
| FR-7 | Edit or cancel an order item | Epic 3 / Story 3.4 | ✓ Covered |
| FR-8 | Close a table | Epic 5 / Story 5.4 | ✓ Covered |
| FR-9 | View incoming orders in real time | Epic 5 / Story 5.1 | ✓ Covered |
| FR-10 | Update an order item's status | Epic 5 / Story 5.2 | ✓ Covered |
| FR-11 | Mark an order served | Epic 5 / Story 5.4 | ✓ Covered |
| FR-12 | Order status derives from its items | Epic 5 / Story 5.3 | ✓ Covered |
| FR-13 | Automatic stock deduction on preparation | Epic 5 / Story 5.2 | ✓ Covered |
| FR-14 | Low-stock alert | Epic 4 / Story 4.2 | ✓ Covered |
| FR-15 | Record manual stock movements | Epic 4 / Story 4.1 | ✓ Covered |
| FR-16 | Create an ingredient | Epic 2 / Story 2.1 | ✓ Covered |
| FR-17 | View ingredient stock levels | Epic 4 / Story 4.3 | ✓ Covered |
| FR-18 | Generate a recipe suggestion from stock | Epic 6 / Story 6.1 | ✓ Covered |
| FR-19 | Suggestion requires admin confirmation | Epic 6 / Story 6.2 | ✓ Covered |
| FR-20 | Smart Assistant chat | Epic 6 / Story 6.3 | ✓ Covered |
| FR-21 | Graceful AI degradation | Epic 6 / Stories 6.1 + 6.3 | ✓ Covered |
| FR-22 | Manage menu dishes and categories | Epic 2 / Story 2.2 | ✓ Covered |
| FR-23 | Define a dish's recipe | Epic 2 / Story 2.3 | ✓ Covered |
| FR-24 | Manage restaurant tables (**add and configure**) | Epic 2 / Story 2.4 | ⚠️ **PARTIAL — add only, no configure — see H-1** |

**NFR coverage (checked separately — NFRs are not in the FR Coverage Map):**

| NFR | Covered by | Status |
|---|---|---|
| NFR-1 (2s push propagation) | Story 3.3, Story 5.1 | ✓ Covered |
| NFR-2 (universal authorization) | Story 1.1, Story 1.2 | ✓ Covered |
| NFR-3 (stock/order atomicity) | Story 5.2 | ✓ Covered |
| NFR-4 (auditability) | Story 4.1, Story 5.2 | ✓ Covered |
| NFR-5 (concurrent multi-terminal) | Story 3.3 | ✓ Covered |
| NFR-6 (last-write-wins) | Story 3.4 | ✓ Covered |
| §4.5 cost attribution (unnumbered) | — | ❌ **No AC — see L-1** |

**No orphans:** every story traces to at least one FR/NFR/AD/UX-DR. No epic invents scope absent
from the PRD. UX-DR20 (`dismissed` field on `AIRecipeSuggestion`) is the one story element sourced
from UX rather than an FR, and it is correctly labelled as such.

### Missing Requirements

#### BLOCKER

**B-1 — No path exists to set a User's password; Story 1.3 as written cannot be implemented.**

- `password_hash` is `NOT NULL` in `docs/database-schema.md` (line 18, "Bcrypt-hashed password") and in the ORM at `backend/data_models/user.py:22` (`nullable=False`).
- FR-3 defines account creation as *"username, full name, Role"* — **no password**. Story 1.3's AC mirrors it exactly: *"Given valid new-user details (username, full name, role)."*
- FR-3's own consequence asserts *"A newly created User can log in immediately with the Role assigned at creation"* — which FR-1 (username + password auth) makes impossible with no password.
- `grep -i password` across `epics.md` returns only Login-screen references (lines 21, 158, 164, 166). The word never appears in Story 1.3, in any admin surface, or in any UX mock outside the Login screen.
- **Nothing anywhere specifies:** an admin-set initial password, a temporary/generated password, a first-login password change, a password reset/recovery path, or a self-service password change.
- **Impact:** A developer implementing Story 1.3 hits a `NOT NULL` violation on the first INSERT and must invent a policy on the spot — precisely the kind of unowned decision this gate exists to catch. It also silently blocks SM-4 (every Role demonstrably demo-able), since seeding the four demo accounts depends on it.
- **Recommendation:** Add an AC to **Story 1.3** covering initial-password provisioning (simplest v1: Admin sets the password at creation; bcrypt-hash it in the service layer) and a matching AC to **Story 1.1** asserting passwords are bcrypt-hashed at rest and never logged. Decide explicitly whether password *reset* is in or out of v1 scope — if out, add it to §5 Non-Goals rather than leaving it absent.

#### HIGH

**H-1 — FR-24's "configure" half is uncovered, and PRD Open Question 2 was dropped in transit.**

- FR-24 reads *"An Admin can **add and configure** Restaurant Tables (table number, capacity)."* Story 2.4's ACs cover only creation and duplicate-number rejection. There is **no AC for editing** a table's number or capacity — the "configure" verb has no implementation path.
- Separately, PRD §8 Open Question 2 asks whether table deletion/renumbering is in scope, noting *"No FR currently covers removing or renumbering a table."* The architecture memlog explicitly punted it downstream: *"deferred to epics/stories."* `epics.md` contains zero occurrences of delete/remove/renumber for tables — the handoff was never received.
- **Impact:** A mis-numbered or mis-capacity table is uncorrectable without direct DB access, which contradicts UJ-4's premise (*"without David touching data directly"*).
- **Recommendation:** Add an edit AC to **Story 2.4**, and record an explicit decision on delete/renumber — either a story or a line in §5 Non-Goals. Do not leave it as a third silent pass.

#### MEDIUM

**M-1 — Session expiry is unspecified at story level (PRD Open Question 1 still open).**
Story 1.1 specifies the JWT httpOnly cookie mechanism but no expiry. The architecture's 8-hour
assumption is tagged *"flag for Ofek's review"* and that flag was never closed. A developer has no
AC to implement against. **Recommendation:** ratify the 8-hour token explicitly and add it to Story 1.1's ACs.

#### LOW

**L-1 — §4.5 cost-attribution NFR has no acceptance criterion.** Structurally satisfied by the
existing `user_id` FKs on `AIRecipeSuggestion`/`AIChatSession`, but unstated, so nothing protects it.
**Recommendation:** one AC on Story 6.1/6.3, or accept as implicitly covered and note it.

**L-2 — FR-1's password-hashing consequence has no AC.** The schema documents bcrypt; no story
asserts it. Folds naturally into B-1's fix.

**L-3 — Duplicate/stale heading in `epics.md`.** Two `### FR Coverage Map` headings exist: line 94
still contains the unreplaced placeholder *"Populated in Step 2 once epics are designed,"* while the
real map sits at line 124. Cosmetic, but it makes the document look half-generated.
**Recommendation:** delete the line-94 stub.

### Coverage Statistics

- **Total PRD FRs:** 24
- **FRs claimed covered in epics:** 24 (100%)
- **FRs fully covered on verification:** 23 (95.8%)
- **FRs partially covered:** 1 — FR-24 (add ✓ / configure ✗)
- **FRs blocked by an unresolvable gap:** 1 — FR-3 (see B-1; formally covered, not implementable)
- **Cross-cutting NFRs covered:** 6 of 6 (100%)
- **Unnumbered feature-NFRs covered:** 0 of 1 (§4.5 cost attribution)
- **Orphan stories (no PRD trace):** 0

**Assessment:** Traceability is strong — this is a well-constructed epic breakdown with genuine
per-story architecture (AD) and UX (UX-DR) anchoring, and no invented scope. The gaps are narrow and
concentrated at the seams: one blocker (B-1) that stops Epic 1 dead, one uncovered requirement half
(H-1) compounded by a dropped open question, and three minor items. None require replanning — all are
additive fixes to existing stories.

**Status:** Epic Coverage Validation complete. Proceeding to UX Alignment.

---

## Step 4: UX Alignment Assessment

### UX Document Status

**Found.** `DESIGN.md` (179 lines, visual spine) and `EXPERIENCE.md` (224 lines, experience spine),
plus 13 key-screen HTML mockups in `mockups/`. Both spines declare `status: final` and both list the
PRD, addendum, and ARCHITECTURE-SPINE in their `sources:` frontmatter — the correct upstream set.

### UX ↔ PRD Alignment

**Strong.** Verified point by point:

- **User journeys:** `EXPERIENCE.md` Key Flows 1–5 map 1:1 onto PRD UJ-1…UJ-5, with protagonists and beats carried verbatim and every PRD-named edge case retold at screen level (unavailable-dish inline rejection, negative-stock pick-up still succeeding, one-alert-per-shortage, deactivated-Cook items not stranded, AI failure and double-request rejection).
- **Roles and permissions:** the no-per-waiter-filtering rule (FR-6/AD-9) and the current-Cook-first-as-display-default rule (FR-20/AD-10) are both stated correctly as *display* behavior, not access boundaries — matching FR-2's Role-level-only model rather than drifting toward per-resource permissions.
- **Non-goals respected:** desktop-only, no touch, no offline/local-first queue, no drag interactions, no customer-facing surface — each traced to an explicit PRD non-goal, and each stated as a deliberate scope line rather than left silent.
- **Status vocabulary:** the status-color table correctly encodes that OrderItem has no `served` state and Order has no `cancelled` state, matching the PRD Glossary and FR-11/FR-12.

**Two deltas found:**

- **UX-introduced surface with no FR:** *Cook: Dishes (view-only)* — "Browse dish catalog + recipe/plating notes for context, no write access." No FR in the PRD covers a Cook reading the menu/recipe catalog (FR-22/FR-23 are Admin-side authoring). This is legitimate inferred scope, but it is untraced: it appears only inside the UX-DR15/UX-DR19 definition text and has **no dedicated story**.
- **UX-introduced schema change:** the persisted `dismissed` field on `AIRecipeSuggestion`. This one is handled correctly — `EXPERIENCE.md` flags it explicitly as "a minor data-model note for whoever builds FR-18/FR-19's stories, not a new FR," it became UX-DR20, and Story 6.2 carries it with its own Alembic migration AC. Model behavior for the other delta to follow.

### UX ↔ Architecture Alignment

**Strong — no architectural gaps.** Every UX mechanism has a supporting architecture decision, and
the UX cites them by ID rather than assuming:

| UX need | Architecture support | Status |
|---|---|---|
| MUI as the only component library, one accent on `primary` slot | AD-13 | ✓ |
| Live status updates with no refresh, ≤2s | AD-2 (single WebSocket, `{domain}.{event}`), NFR-1 | ✓ |
| Login → role home redirect | AD-3 (JWT httpOnly cookie) | ✓ |
| Order total from stored prices, never live lookup | AD-7 | ✓ |
| Availability toggle disabled with inline reason | AD-8 | ✓ |
| Cancel-confirm dialog stating stock is not reversed | AD-11 | ✓ |
| Last-admin lockout inline rejection | AD-15 | ✓ |
| Pick-up succeeds even into negative stock | AD-16 | ✓ |
| Inline error copy sourced from a shared envelope | Spine's error-envelope convention (string `detail` **or** FastAPI's structured validation list) | ✓ |
| Reconnecting state, auto-retry, no local write queue | AD-2 + PRD no-offline non-goal | ✓ |

No UI component in the UX requires capability the architecture does not provide. Performance needs
(2-second push) are architecturally satisfied by AD-2 rather than left as an aspiration.

### Alignment Issues

**The weak seam is UX ↔ Epics, not UX ↔ PRD or UX ↔ Architecture.** The UX requirements were
faithfully *transcribed* into `epics.md` as UX-DR1…UX-DR21, but several carry far broader scope than
the single story reference that claims them. Reference counts across all 21 story-level ACs:

| UX-DR | Stated scope | Story refs | Gap |
|---|---|---|---|
| **UX-DR19** | Build **all 13 IA surfaces** per mockups, **plus per-role nav** | 3 | Only Users, Tables setup, and one Kitchen Display detail. **11 surfaces have no build story; per-role nav and routing have none at all.** |
| **UX-DR21** | WCAG 2.2 AA, focus rings, tab order — **on every surface** | 1 | Users screen only. 12 surfaces uncovered. |
| **UX-DR7** | Real light/dark toggle in app bar on every surface, persisted per browser/terminal | 1 | The single ref covers only "Kitchen Display defaults to dark." **The toggle component and its persistence have no story.** |
| **UX-DR15** | Cold-load **`Skeleton` states** *and* empty-state copy, all 13 surfaces | 8 | Empty-state copy is well covered. **`Skeleton`/cold-load is never mentioned in any story** — `grep -i skeleton` matches only the UX-DR definition line. |

Consequential specifics:

- **No story builds the frontend application shell.** Nothing covers React Router v7 wiring, the app-bar/nav chrome, role-based route guarding on the client, or the Login *screen* (Story 1.1 covers the login *endpoint*, JWT, and CORS — not the UI). The architecture picked React Router v7, but `grep -i "react router\|routing\|navigation"` across `epics.md` matches only the UX-DR19 definition line.
- **The *Cook: Dishes (view-only)* surface has neither an FR nor a story** — it exists only inside two UX-DR definition strings.
- **Impact on the next step:** sprint planning derives its work queue from stories. Scope that lives only in a UX-DR definition line, with no owning story, will not appear in that queue — so the app shell, navigation, theming, skeletons, and 11 of 13 screens are at real risk of being treated as invisible work absorbed ad hoc into backend-shaped stories.

### Warnings

- **⚠️ Corroborates B-1 (blocker) independently.** `EXPERIENCE.md` Flow 4 step 1 reads: *"David opens Users. He creates a new account: username, full name, role `cook`"* — no password — and step 3 has that cook logging in. `grep -i password` against `mockups/key-users.html` returns **nothing**: the Users mockup has Edit controls but **no password field anywhere**. The omission is now confirmed across all four artifacts (PRD FR-3, epics Story 1.3, UX spine, UX mockup) against a `NOT NULL password_hash` column. This is systemic, not a transcription slip.
- **⚠️ Upgrades H-1.** The UX explicitly promises table configuration: the IA table describes Tables setup as *"Add/**configure** physical tables,"* and `mockups/key-tables-setup.html` renders a Capacity field plus **11 `Edit` buttons**. Story 2.4 has no edit AC at all, yet its closing line instructs the developer that the screen *"renders per the UX mocks."* The story therefore tells a developer to build controls whose behavior no acceptance criterion defines — an internal contradiction, not merely an omission.
- **⚠️ No accessibility verification story.** UX-DR21 sets a WCAG 2.2 AA floor across every surface and both themes, but only one story references it. There is no story or AC covering the contrast/focus/tab-order pass as testable work, so the floor is asserted but never checked.

**Status:** UX Alignment complete. Proceeding to Epic Quality Review.

---

## Step 5: Epic Quality Review

Validated all 6 epics and 21 stories against `create-epics-and-stories` standards.

### Epic Structure Validation

**A. User Value Focus — PASS (6/6).** No technical-milestone epics found. Every epic title and goal
is phrased as what a *role* can do, not what a *layer* gets built:

| Epic | Goal framing | Verdict |
|---|---|---|
| 1. Staff Accounts & Access Control | "Every role can log in securely and see only what their role permits; Admin can manage the staff roster" | ✓ User value (not "Auth System") |
| 2. Menu, Recipes, Ingredients & Table Setup | "Admin can build a sellable menu … and configure the restaurant's physical tables" | ✓ User value |
| 3. Table Service & Order Taking | "A Waiter can open a table, build and adjust an order … and see live status" | ✓ User value |
| 4. Warehouse Inventory Operations & Low-Stock Alerts | "A Warehouse Manager can log manual stock movements … and get alerted" | ✓ User value |
| 5. Kitchen Fulfillment, Stock Deduction & Close-Out | "A Cook works orders to ready in real time … the Waiter marks served and closes the table" | ✓ User value |
| 6. Smart Chef, Recipe Suggestions & Assistant Chat | "A Cook can generate an AI recipe suggestion … an Admin can confirm a suggestion into a real menu Dish" | ✓ User value |

There is no "Set up database," no "API development," no "Infrastructure" epic. Epic 1 is
authentication but is correctly framed around what each role gains rather than the subsystem —
this clears the standard's "borderline" test.

**B. Epic Independence — PASS.** Epic N never *requires* Epic N+1 to function. Dependency direction
is uniformly backward: Epic 2 → 1; Epic 3 → 1,2; Epic 4 → 1,2; Epic 5 → 1,2,3,4; Epic 6 → 1,2,4.
Epic 4 is deliberately designed to stand alone ("fully standalone, independent of the kitchen's
automatic path"), and Epic 5 correctly *reuses* Epic 4's alert logic rather than rebuilding it
("reuses FR-14, no new alert logic built here"). This is well-sequenced work.

### 🟠 Major Issues

**Q-1 — Three acceptance criteria carry forward dependencies on Epic 5 and cannot be verified at their own epic's completion.**

| Location | AC text | Problem |
|---|---|---|
| `epics.md:387` (Story 3.3) | *"**Given** any Order Item's status changes (**from Epic 5's Cook actions**)"* | Story 3.3's headline AC — the 2-second push guarantee (FR-6/NFR-1) — is untestable until Epic 5 ships a Cook action to trigger it. This is the story's whole point. |
| `epics.md:422` (Story 3.4) | *"a cancelled Order Item is excluded from **Epic 5's** status-derivation (FR-12) and readiness-for-close checks (FR-8)"* | Asserts behavior implemented two epics later. |
| `epics.md:308` (Story 2.3) | *"**When** a future Order Item for that Dish is later prepared (**Epic 5**)"* | Asserts Epic 5 deduction behavior from an Epic 2 story. |

**Contrast — the correct pattern already exists in this document.** Story 4.2 (`epics.md:457`) handles
the identical situation properly: *"(`waste` or a negative `adjustment` today; automatic `consumption`
once Epic 5 exists)"* — it scopes what is verifiable now and names the deferred case explicitly,
leaving the story independently completable.

**Recommendation:** rewrite the three ACs on the Story 4.2 model. Story 3.3's especially should assert
propagation using a **Waiter-side** change (add/edit/cancel an item, visible on a second Waiter
terminal), which is fully within Epic 3 — then note Cook-side propagation as verified in Epic 5.

**Q-2 — No story establishes a test framework, yet every story is written in testable BDD form.**
`grep -i "pytest\|vitest\|test framework\|testing"` across `epics.md` returns **zero matches**.
Meanwhile `project-context.md` states plainly: *"No test framework is set up on either side yet …
Do not assume a framework or write tests against one without first raising the choice as a decision."*
All 21 stories carry Given/When/Then criteria whose verification is undefined, and the downstream
`bmad-dev-story` workflow runs a test-first (red/green/refactor) loop with nothing to run.
**Recommendation:** add an explicit story (or an AC on Story 1.1) adopting `pytest` + `httpx.AsyncClient`
on the backend and `vitest` + `@testing-library/react` on the frontend, before Story 1.1's ACs need verifying.

**Q-3 — 11 of 13 UI surfaces have no owning story** (carried from Step 4). Because sprint planning
derives its queue from stories, the app shell, React Router wiring, per-role nav, theme toggle,
cold-load skeletons, and most screens will not appear as planned work. See Step 4 for the full table.

### 🟡 Minor Concerns

**Q-4 — Alembic adoption is deferred to Story 3.2 (Epic 3), leaving Epics 1–2 on `create_all`.**
Two schema-management regimes run across the project's first third. This is workable *only if* no
Epic 1–2 story needs a schema change — but **B-1's fix may well require one** (e.g. a
`must_change_password` flag or any password-provisioning column), and at that point there is no
migration mechanism in place. **Recommendation:** move the Alembic baseline into Epic 1 (Story 1.1 or
a dedicated story) so every subsequent schema delta has a home, and resolve B-1 before deciding.

**Q-5 — Trailing `**And**` clauses carry orphaned requirements with no Given/When scenario.**
Several stories close with a floating `**And** …` appended after the final `Then`, bundling unrelated
requirements into one sentence — e.g. `epics.md:233` (Users screen styling + WCAG floor),
`epics.md:562` (click-target sizing + WebSocket push), `epics.md:644` (client adapter + card contents).
These are not anchored to any scenario, making them the least testable and most skippable ACs in the
document. Notably, **this is exactly where the thinnest UX coverage lives** — UX-DR19 and UX-DR21
appear *only* in such trailers. **Recommendation:** promote each to its own Given/When/Then.

**Q-6 — Story sizing: two stories bundle infrastructure adoption with feature delivery.**
Story 3.3 introduces the entire WebSocket transport (endpoint, JWT gating, role scoping, the
`{domain}.{event}` naming convention that all later stories depend on) *and* the Waiter live-status
feature. Story 3.2 similarly adopts Alembic wholesale alongside adding one column. Both are coherent,
but each front-loads a foundational decision inside a feature story — worth splitting if either slips.
Story 1.1 also carries unrelated housekeeping (removing the stray `backend/data_models/exceptions/`
folder) that belongs in its own cleanup task.

### Best Practices Compliance Checklist

| Check | Result |
|---|---|
| Epic delivers user value | ✅ 6/6 |
| Epic can function independently | ✅ 6/6 (backward-only dependency graph) |
| Stories appropriately sized | ⚠️ 19/21 — Stories 3.2, 3.3 bundle infrastructure with feature |
| No forward dependencies | ❌ **3 violations** (Q-1: stories 2.3, 3.3, 3.4) |
| Database tables created when needed | ✅ Migrations are incremental and per-story (3.2 baseline, 3.4 enum, 6.2 column) — ⚠️ but adoption starts late (Q-4) |
| Clear acceptance criteria | ✅ Consistent Given/When/Then throughout; specific, testable, error paths covered — ⚠️ except floating `And` trailers (Q-5) |
| Traceability to FRs maintained | ✅ Every story cites FR / AD / UX-DR IDs; zero orphan stories |

**Brownfield handling — strong.** No starter-template story is required (the architecture ratifies the
existing scaffold rather than specifying a template), and the stories correctly integrate with what
exists: incremental `container.wire(modules=[...])` appends with an explicit "never replacing" rule
repeated in five stories, reuse of the `clients/database.py` pattern, and removal of scaffold debris.

### Assessment

**This is a well-constructed epic breakdown.** Epic decomposition, value framing, sequencing, AC
discipline, and traceability are all above the bar — the authors clearly worked from the architecture
and UX rather than paraphrasing the PRD. The defects are narrow and mechanical: three mis-scoped ACs,
one missing test-infrastructure decision, and frontend scope that was captured as requirements but
never converted into stories. None require re-planning; all are additive edits.

**Status:** Epic Quality Review complete. Proceeding to Final Assessment.

---

## Summary and Recommendations

### Overall Readiness Status

## ⚠️ NEEDS WORK

**One blocker, three major issues, and six lesser findings — all fixable in a single focused editing
pass. No re-planning required; every fix is additive to existing artifacts.**

This verdict is not a criticism of the planning work. The PRD, UX spines, and Architecture spine are
each unusually rigorous, and the epic breakdown is well-decomposed with strictly backward dependencies
and zero orphan stories. **The failures are concentrated at the seams between documents** — decisions
formally handed from one stage to the next and never received, and requirements captured in a list but
never converted into stories. That is precisely the failure mode this gate exists to catch, and it is
why "the individual documents are good" does not by itself mean "ready to build."

### Critical Issues Requiring Immediate Action

#### 🔴 BLOCKER — B-1: No path exists to set a User's password

`password_hash` is `NOT NULL` (`docs/database-schema.md:18`, `backend/data_models/user.py:22`), but
account creation is specified as *username + full name + Role* in **all four artifacts**:

- PRD FR-3 (§4.1) — no password in the creation tuple
- `epics.md` Story 1.3 — *"Given valid new-user details (username, full name, role)"*
- `EXPERIENCE.md` Flow 4 step 1 — *"He creates a new account: username, full name, role `cook`"* — and step 3 has that cook logging in
- `mockups/key-users.html` — Edit controls present, **no password field anywhere**

Nothing anywhere defines an admin-set initial password, a temporary/generated one, a first-login
change, or any reset path. FR-3's own consequence — *"a newly created User can log in immediately"* —
is unachievable under FR-1's username+password auth.

**Consequence if unaddressed:** Story 1.3 cannot be implemented as written (first INSERT violates
`NOT NULL`), Story 1.1 cannot authenticate anyone Story 1.3 creates, and SM-4 — *every Role has a
demo-able action* — is blocked, because seeding the four demo accounts depends on it. Epic 1 gates
every other epic, so this stops the entire build at story one.

#### 🟠 MAJOR — H-1: FR-24's "configure" is unimplemented, and the story contradicts its own mockup

FR-24 specifies *"add **and configure**"*; `EXPERIENCE.md` describes the surface as *"Add/configure
physical tables"*; `mockups/key-tables-setup.html` renders a Capacity field and **11 `Edit` buttons**.
Story 2.4 has **no edit AC** — yet instructs the developer that the screen *"renders per the UX mocks."*
The story directs building controls whose behavior no criterion defines.

Compounding this, PRD §8 Open Question 2 (table delete/renumber) was explicitly deferred downstream by
the architecture memlog — *"deferred to epics/stories"* — and `epics.md` contains zero occurrences of
delete, remove, or renumber for tables. The handoff was never received.

#### 🟠 MAJOR — Q-2: No test framework is established anywhere

Zero matches for `pytest`/`vitest`/`test framework`/`testing` across all 706 lines of `epics.md`, while
all 21 stories are written in verifiable Given/When/Then form and `project-context.md` states the
choice must be raised as an explicit decision. The downstream `bmad-dev-story` workflow runs a
test-first loop with nothing to run.

#### 🟠 MAJOR — Q-3 / Step 4: The frontend has no owning stories

11 of 13 UI surfaces, the React Router wiring, the app shell and per-role nav, the theme toggle and its
persistence, and every cold-load `Skeleton` state exist **only** as UX-DR definition lines — never as
story acceptance criteria. Sprint planning derives its queue from stories, so this scope will be
invisible in the plan and absorbed ad hoc into backend-shaped work.

#### 🟠 MAJOR — Q-1: Three acceptance criteria have forward dependencies

`epics.md:387` (Story 3.3), `:422` (Story 3.4), and `:308` (Story 2.3) each assert behavior delivered in
Epic 5, making them unverifiable at their own epic's completion. Story 3.3's is the most damaging — the
2-second push guarantee is that story's entire purpose. Story 4.2 (`:457`) already models the correct
fix in this same document.

### Lesser Findings

| ID | Severity | Finding |
|---|---|---|
| M-1 | Medium | Session expiry unspecified in Story 1.1; architecture's 8-hour JWT is tagged *"flag for Ofek's review"* and that flag was never closed |
| Q-4 | Minor | Alembic adoption deferred to Story 3.2, leaving Epics 1–2 on `create_all` with no migration mechanism — collides with B-1's fix if it needs a column |
| Q-5 | Minor | Floating `**And**` trailers carry orphaned, scenario-less requirements — and are exactly where UX-DR19/UX-DR21 coverage hides |
| Q-6 | Minor | Stories 3.2 and 3.3 bundle infrastructure adoption (Alembic, WebSockets) with feature delivery; Story 1.1 carries unrelated cleanup |
| L-1 | Low | §4.5 cost-attribution NFR has no AC (structurally satisfied by existing `user_id` FKs, but unstated) |
| L-2 | Low | FR-1's bcrypt-hashing consequence has no AC — folds into B-1's fix |
| L-3 | Low | `epics.md:94` holds a stale duplicate *"FR Coverage Map"* heading still reading *"Populated in Step 2…"* |
| — | Note | `_bmad-output/project-context.md` (2026-07-24) is stale: it claims *"no models exist in code yet"* when `backend/data_models/` has 7 ORM files, and predates the architecture spine entirely. It is loaded as persistent context by BMad skills and will mislead implementation agents. |

### Recommended Next Steps

1. **Resolve B-1 first — it is a product decision, not an editing task.** Decide how a new user gets a
   password (simplest v1: Admin sets it at creation, bcrypt-hashed in the service layer) and whether
   password *reset* is in scope. Then propagate to PRD FR-3, Story 1.3, `EXPERIENCE.md` Flow 4, and
   `key-users.html`. If reset is out of scope, add it to PRD §5 Non-Goals rather than leaving it absent.
2. **Close the two open questions the PRD is still carrying.** Ratify the 8-hour session (M-1) into
   Story 1.1's ACs, and make an explicit call on table delete/renumber (H-1) — a story or a Non-Goals
   line, not a third silent pass.
3. **Add the missing stories.** A test-infrastructure story (Q-2), a frontend-shell story covering
   routing/nav/theme/skeletons (Q-3), and a *Cook: Dishes (view-only)* story. Add an edit AC to
   Story 2.4 (H-1).
4. **Fix the three forward-dependency ACs** (Q-1) on the Story 4.2 model — scope each to what is
   verifiable within its own epic and name the deferred half explicitly.
5. **Consider moving the Alembic baseline into Epic 1** (Q-4), so B-1's fix and any Epic 1–2 schema
   delta have a migration path.
6. **Regenerate or retire `project-context.md`** before implementation agents consume it.
7. **Re-run this check** after the edits, then proceed to **Sprint Planning** (`bmad-sprint-planning`).

### Final Note

This assessment identified **10 issues across 5 categories** (traceability, UX↔epic alignment, story
quality, dependency structure, and document hygiene), from a review of 4 primary artifacts totaling
~1,900 lines plus 13 mockups, validated against the live codebase.

Coverage itself is excellent: **24/24 FRs and 6/6 NFRs traced to stories, zero orphan stories, 6/6
epics delivering genuine user value, and a strictly backward dependency graph.** One requirement is
partially covered (FR-24), one unnumbered feature-NFR is uncovered (§4.5 cost attribution), and one
formally-covered requirement is not implementable as written (FR-3, per B-1).

Address B-1 before writing any code — it stops Epic 1 at its first story, and Epic 1 gates everything
else. The remaining items are best fixed in the same pass, since they touch the same four documents.

---

**Assessed:** 2026-08-02
**Assessor:** `bmad-check-implementation-readiness` (Implementation Readiness gate, Phase 3 → Phase 4)
**Artifacts reviewed:** `prd.md`, `addendum.md`, `ARCHITECTURE-SPINE.md`, `DESIGN.md`, `EXPERIENCE.md`, `epics.md`, 13 key-screen mockups, plus live-codebase verification against `backend/data_models/`, `docs/database-schema.md`, and `_bmad-output/project-context.md`.

---

## Post-Assessment Resolutions

### ✅ B-1 RESOLVED — 2026-08-02

**Decision (Ron):** *The Admin sets the password on user creation.*

No self-service signup, no emailed invite, no auto-generated password. Propagated to every artifact
that carried the gap:

| Artifact | Change |
|---|---|
| `prd.md` FR-3 | Creation tuple now reads *"username, full name, Role, **initial password**"*; added a consequence covering hash-only storage, no plaintext, no retrieval-after-the-fact; the "can log in immediately" consequence now names the initial password. `updated:` bumped to 2026-08-02. |
| `epics.md` Requirements Inventory | FR-3 transcription updated to match. |
| `epics.md` Story 1.3 | Create-user AC now takes an initial password; **+2 new ACs** — bcrypt-hash-only persistence (never logged, never returned by a read endpoint), and inline rejection of a blank/missing password. |
| `epics.md` Story 1.1 | **+1 new AC** — authentication verifies against the stored bcrypt hash; plaintext never stored, logged, or included in any response or error payload. *(This also closes **L-2**.)* |
| `epics.md` UX-DR17 | Added missing-initial-password to the named inline-rejection list. |
| `EXPERIENCE.md` Flow 4 | Step 1 now has David setting an initial password and handing it to the new hire. |
| `EXPERIENCE.md` State Patterns | New row: *Rejected (missing password) → "Rejected, password required."* |

**Correction to the Step 4 finding:** `mockups/key-users.html` was described as having "no password
field anywhere." Accurate but misleading — the mockup renders only the roster table and a `+ New user`
button; **no create form is mocked at all**. The mockup was silent on the question rather than
contradicting it, and needs no change. The gap was confined to the three text artifacts, all now fixed.

**Still open on this thread:** password **reset/recovery** is undefined. FR-3 lets an Admin edit Role
and full name, not reset a password, so a staff member who forgets theirs currently has no recovery
path. Requires an explicit in-scope story or a §5 Non-Goals line — see recommendation 1.

**L-2 also resolved** by the Story 1.1 AC above.

**Revised blocker count: 0.** Remaining: 3 major (H-1, Q-2, Q-3), 1 major (Q-1), plus M-1 and the
minor/low items. Status moves from **NEEDS WORK (blocked)** to **NEEDS WORK (unblocked)** — Epic 1
Story 1.3 is now implementable.

### ✅ B-1 follow-up RESOLVED — password reset — 2026-08-02

**Decision (Ron):** *An Admin can reset an existing User's password.* No self-service reset, no
email-based recovery — consistent with the closed-staff, no-diner-PII design and requiring no mail
infrastructure. Reuses the hashing path Story 1.3 already builds.

| Artifact | Change |
|---|---|
| `prd.md` FR-3 | Capability list now includes *"reset an existing User's password"*; new consequence covering same-path hashing, old hash overwritten, previous password stops working immediately, and the explicit no-self-service/no-email statement. |
| `epics.md` Requirements Inventory | FR-3 transcription updated to match. |
| `epics.md` Story 1.3 | **+2 new ACs** — Admin-initiated reset (new hash, old one dead immediately, User logs in with the new password) and the negative case (never reveals or requires the old password; no self-service or email path in v1). |
| `EXPERIENCE.md` IA table | Admin Users surface purpose now reads *"Create (incl. initial password) / edit role / reset password / deactivate / reactivate staff."* |

The forgotten-password recovery path is now closed. Story 1.3 gained 4 ACs total across both
decisions (initial password, hash-only storage, blank-password rejection, reset ×2 — 5 with the
negative case), and Story 1.1 gained 1.

---

## Full Resolution Record — 2026-08-02

All ten findings closed in a single editing pass following a decision round with Ron. No re-planning
was required; every fix was additive to existing artifacts.

### Decisions taken

| # | Question | Ron's decision |
|---|---|---|
| 1 | How does a User get a password? | Admin sets the **initial password at creation**; Admin can also **reset** an existing User's password. No self-service signup, no email recovery. |
| 2 | Table configure/delete scope | Admin can **add and edit** tables (number, capacity), gated on the table being `available`. **No deletion in v1.** |
| 3 | Test framework | **pytest + pytest-asyncio + httpx** (backend), **vitest + @testing-library/react** (frontend). |
| 4 | How does the frontend enter the plan? | **App-shell story + screens attached to their existing epics** — not a separate frontend epic, preserving vertical slices. |
| 5 | Session expiry | **8-hour JWT** ratified, silent re-login on expiry, no refresh-token flow. |
| 6 | Cook: Dishes (view-only) | **Kept as a real feature** — promoted to a new **FR-25** with its own story. |
| 7 | `project-context.md` | **Regenerated** against the live codebase. |
| 8 | Floating `And` trailers | **Promoted** to full Given/When/Then criteria. |
| 9 | Story 3.3's bundled WebSocket adoption | **Split** into its own foundation story. |

### Findings, closed

| ID | Severity | Resolution |
|---|---|---|
| **B-1** | 🔴 Blocker | Password provisioning specified across PRD FR-3, epics Story 1.3 (+5 ACs incl. reset and blank-password rejection), Story 1.1 (+1 bcrypt AC), UX-DR17, `EXPERIENCE.md` Flow 4 and State Patterns. |
| **H-1** | 🟠 Major | FR-24 rewritten with an edit path gated on `available`; Story 2.4 gained 5 ACs (edit, in-use rejection, duplicate-on-rename, guarded conditional update, no-delete affordance). Table deletion added to PRD §5 Non-Goals. **PRD Open Question 2 closed.** |
| **Q-2** | 🟠 Major | New **Story 1.0 — Project Foundation**: both test harnesses adopted with a green smoke test on each side, before any story's ACs need verifying. |
| **Q-3** | 🟠 Major | New **Story 1.4 — Application Shell**: React Router v7, per-role nav, route guarding, Login screen, theme toggle + persistence, shared `Skeleton` pattern, shared Reconnecting state, and the WCAG 2.2 AA floor as its own criterion. Screens remain attached to their owning epics. |
| **Q-1** | 🟠 Major | All three forward-dependency ACs (Stories 2.3, 3.3, 3.4) rewritten on the Story 4.2 model — each now scoped to what is verifiable within its own epic, with the deferred half named explicitly. |
| **M-1** | 🟡 Medium | 8-hour expiry written into Story 1.1's ACs. **PRD Open Question 1 closed.** |
| **Q-4** | 🟡 Minor | Alembic baseline moved from Story 3.2 to **Story 1.0**, so Epics 1–2 are no longer stranded on `create_all`. Stories 3.2, 3.4 and 6.2 now each ship a revision on top of that baseline. |
| **Q-5** | 🟡 Minor | **All 17** floating `**And**` trailers promoted to full Given/When/Then scenarios. Zero remain. |
| **Q-6** | 🟡 Minor | Story 3.2 no longer bundles Alembic adoption. Story 3.3's WebSocket adoption split into new **Story 1.5 — Real-Time Push Transport**, which fixes the `{domain}.{event}` convention before Stories 3.3, 4.2, 5.1 and 5.2 are written against it. |
| **L-1** | 🔵 Low | Cost-attribution AC added to Story 6.1. |
| **L-2** | 🔵 Low | Closed by Story 1.1's bcrypt AC. |
| **L-3** | 🔵 Low | Stale duplicate "FR Coverage Map" placeholder deleted. |
| **Note** | — | `project-context.md` regenerated. Its central defect was structural, not staleness: it could not distinguish *installed* from *merely decided*. It now leads with an installed-vs-decided table naming the adopting story for each pending dependency, plus a four-item silent-failure list (`container.wire()` never called, `create_all` reporting success while doing nothing, no CORS, no auth), all 16 ADs, and the grading-weight context. |

### Artifact state after the pass

| Artifact | Before | After |
|---|---|---|
| `epics.md` | 21 stories, 24 FRs | **25 stories, 25 FRs**, 144 Given/When/Then criteria, 0 floating trailers |
| `prd.md` | 24 FRs, 2 open questions | **25 FRs, 0 open questions**, table deletion in Non-Goals |
| `addendum.md` | — | Per-role action table updated (Cook +FR-25, Admin table verbs) |
| `EXPERIENCE.md` | — | Two IA rows corrected, new table-in-use state row |
| `project-context.md` | Stale (2026-07-24) | Rewritten against the live codebase |

**New stories:** 1.0 Project Foundation · 1.4 Application Shell · 1.5 Real-Time Push Transport · 2.5 Cook Browses the Dish Catalog.

### Revised Status

## ✅ READY

Blockers: 0. Majors: 0. Minors: 0. Every FR and NFR traces to a story; no orphan stories; no forward
dependencies; every epic delivers user value; every schema change has a migration path; every
acceptance criterion has an executable harness to run in.

**Recommended sequencing note for sprint planning:** Story 1.0 must complete before Story 1.1, and
Story 1.5 before Stories 3.3 / 4.2 / 5.1 / 5.2. Both are enabling stories with no direct user value —
the only two in the plan, each marked as such in the document.

**Next step:** `bmad-sprint-planning`.
