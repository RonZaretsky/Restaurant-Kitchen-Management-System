# Addendum — Restaurant Kitchen Management System PRD

Content that belongs to this project but not to the PRD's main narrative: source-document crosswalk, the grading-rubric breakdown, the OOA/OOD requirements and UML-mapping crosswalk, a per-role action table, dual-voice worked examples, and rejected/deferred technical-how decisions for the downstream course deliverables.

## Source Documents

1. **Course guidelines** — "פרק 11: פרויקט הגמר" (Final Project chapter), Open University of Israel OOP workshop coursebook, pages 64–66. Provided as a pasted PDF during PRD Discovery (2026-07-24). **Restricted course material — verbatim extract kept out of version control in `secrets/source-course-guidelines.md` (gitignored), not reproduced here.**
2. **Approved project proposal** — email from Ofek Rotem & Ron Zaretsky to instructor "Danny," pasted during PRD Discovery (2026-07-24). Pre-approved by the instructor per the user's statement. **Verbatim copy kept out of version control in `secrets/source-proposal.md` (gitignored), not reproduced here.**
3. **Brownfield code scan** — `docs/index.md` and its linked documents, generated 2026-07-24 via `bmad-document-project` (exhaustive scan).

## Grading Structure (from course guidelines, for reference)

- The project (all stages combined) = **70%** of the overall workshop grade.
- **Maman 12** ("planning" submission) = topic/background doc (2%) + OOA/Analysis document (~38–40%) + OOD/Design document (60%) — percentages are of Maman 12's own weight; Maman 12 as a whole = 35% of the *overall* workshop grade.
- **Maman 13** (final submission: implementation + install/user guide + code + live defense) = **35% of the overall workshop grade**, independently of Maman 12.
- Net effect: **design and analysis documentation (Maman 12) carries roughly the same overall weight as the working implementation (Maman 13)** — this is the basis for Success Metrics counter-metric SM-C1 in the PRD (don't over-invest in feature breadth at the expense of design/documentation quality).

## OOA/OOD Document Requirements & UML-Crosswalk

### OOA (Analysis) document requirements — must inform how this PRD's §2–§5 get extracted
- Must be **100% client-facing** — zero design or implementation detail (no classes, no inheritance, no tech choices). The reader is explicitly "a client who understands nothing about programming."
- Must include: problem description; description of system components; **detailed description of each user type and every action each can perform**; Use Case diagrams and Activity diagrams for the system's main processes.
- Explicitly requires the author to represent *both* sides: the client stating requirements, and the analyst inferring additional requirements the client didn't state explicitly. This PRD's `[ASSUMPTION]` tags and §8 Open Questions are the direct mechanism for surfacing that second voice — don't strip them out when extracting into the OOA — they're evidence of exactly the analytical work being graded.

### OOD (Design) document requirements — downstream of this PRD, produced by `bmad-architecture`
- Class Diagram, Activity Diagram, Use Case Diagram, Sequence Diagram (at minimum).
- Full description of every class: inheritance hierarchy, members (fields/methods), relationships to other classes.
- Naming conventions used, explicit working assumptions, a section on possible future changes and how the design accommodates them.
- Design must be **independent of a specific DB or presentation implementation** — directly echoed in this PRD as the "capabilities not implementation" discipline and in NFR framing that avoids naming specific tech (e.g. NFR-1 states a latency/push bound, not "use WebSockets").

### UML-Crosswalk (PRD → required OOA/OOD content)

For whoever writes the OOA/OOD documents next, a quick map of what in this PRD feeds which required element (extended beyond the original diagrams-only version to also cover the problem-description and system-component-description requirements above).

| Required OOA/OOD element | Primary PRD source |
|---|---|
| Problem description | PRD §1 Vision, paragraph 1 (the "handoffs are informal today" framing) |
| System-component description | PRD §4 Features section headers (4.1–4.6) — each is one system component/module; §4's per-feature "Description" prose is the component description, stripped of the nested FRs |
| Use Case Diagram | §4 Features — each FR is close to one use case; actors = the four Roles in §3 Glossary (see per-Role action table below) |
| Activity Diagram (main processes) | §2.3 User Journeys — each UJ's "Path" beats are close to an activity-diagram flow already; UJ-1→UJ-2 chain is the order-to-kitchen main process, UJ-2→UJ-3 is the consumption-to-alert process |
| Class Diagram | The existing `backend/data_models/*.py` (already implemented) plus §3 Glossary for any concept not yet a table (Role permissions, Chat Session/Message already modeled as `AIChatSession`/`AIChatMessage`) |
| Sequence Diagram | UJ-2's climax (order-item-picked-up → stock deduction → waiter view update) and UJ-5's climax (suggestion request → OpenAI call → persisted suggestion) are the two richest multi-actor sequences in the PRD |

## Per-Role Action Table (OOA "user types and their actions" requirement)

The PRD is organized by feature, not by actor, so this table re-derives the OOA's required "detailed description of each user type and the actions they can perform" view directly from the FRs.

| Role | Actions (FR references) |
|---|---|
| **Waiter** | Open a table and start an order (FR-4); add items to an order (FR-5); view live order/table status (FR-6); edit or cancel an order item (FR-7); mark an order served (FR-11); close a table (FR-8) |
| **Cook** | View incoming orders in real time (FR-9); update an order item's status / pick up and mark ready (FR-10); cancel an in-preparation order item (FR-7, shared with Waiter/Admin); browse the dish catalog read-only for prep context (FR-25); generate a recipe suggestion from stock (FR-18); consult/version/improve recipes via Smart Assistant chat (FR-20) |
| **Warehouse Manager** | Record manual stock movements — purchase/waste/adjustment (FR-15); create a new ingredient (FR-16, shared with Admin); view ingredient stock levels and shortage status (FR-17); receive Low-Stock Alerts (FR-14, passive) |
| **Admin** | Create/deactivate/edit/reactivate user accounts (FR-3); manage menu dishes and categories (FR-22); define a dish's recipe (FR-23); add and edit restaurant tables, edit gated on the table being available (FR-24); create a new ingredient (FR-16, shared with Warehouse Manager); turn a Recipe Suggestion into a live Dish (FR-19, shared trigger with FR-22/23) |

**Cross-role note:** every Role also performs FR-1 (login) and is subject to FR-2 (role-based authorization) — these are foundational rather than Role-specific and are listed once here rather than repeated in each row.

## Dual-Voice Worked Examples (client-stated vs. analyst-inferred)

The course guidelines require the OOA to represent *both* what the client stated *and* what the analyst inferred as necessary but unstated. This PRD's `[ASSUMPTION]` tags mostly mark unconfirmed *policy* decisions rather than analyst-added requirements — the following are the clearest examples of genuine analyst inference (requirements the proposal never stated but that follow necessarily from what it did state), worth citing explicitly when writing the OOA's own dual-voice narrative:

- **UJ-3 single-alert-per-shortage rule** (PRD §2.3, FR-14 consequence): the proposal says "alert the warehouse manager on shortages" but never addresses repeat/duplicate alerts for an already-known shortage. The analyst-added requirement (one active alert per ingredient-in-shortage, not one per consumption event) follows from basic usability, not from anything the client wrote.
- **UJ-4 no-orphan-user rule** (FR-3 consequence): the proposal says admins manage "users and permissions" but never addresses what happens to a deactivated user's historical order-item assignments. The analyst-added requirement (history preserved, account just can't log in) follows from the existing audit-trail design of Stock Movements, extended by inference to users.
- **FR-7 order-item cancel/void path** (surfaced during Reviewer Gate edge-case review, added 2026-07-24): the proposal never mentions correcting or cancelling a submitted order item. Without it, a Waiter's FR-8 close would hard-block indefinitely on any item that can never reach `ready` (e.g. a dish 86'd — pulled from the menu — mid-service). The analyst-added requirement follows necessarily from combining the proposal's own "close a table" requirement with the reality that kitchens run out of things mid-shift.
- **NFR-3 stock/order atomicity**: nowhere stated in the proposal, but necessarily implied by combining "automatic stock deduction" with "multiple staff using the system simultaneously" (also proposal-implied via the multi-role hierarchy).
- **FR-24 restaurant table management** (see §9 Assumptions Index in `prd.md`): the proposal's Administration section never mentions tables, but `RestaurantTable` must be configurable by someone for the rest of the system to function.

## Deferred Technical-How (belongs to `bmad-architecture`, not this PRD)

- **Real-time push mechanism** for NFR-1 — candidates: WebSockets, Server-Sent Events, or long-polling. The PRD only commits to "push, not poll, within ~2s"; picking the mechanism is an architecture decision.
- **Session/auth implementation** for FR-1/FR-2 — JWT vs. server-side session store, expiry policy, refresh strategy. `dependency-injector` wiring (`container.wire()`) is not yet activated anywhere in the codebase (see `docs/architecture-backend.md`) and will need to be activated for any DI-based auth dependency.
- **OpenAI integration specifics** for FR-18/FR-20 — which model, prompt template design, token/cost budgeting mechanism. The PRD has already resolved the *policy* question (no v1 cap, see §4.5 feature NFR); the *mechanism* for per-call cost attribution is architecture's to design.
- **Concurrency control** for NFR-3 — optimistic locking, DB transaction isolation level, or row-level locking for the stock-deduction path specifically. Note this is narrower than NFR-6's general last-write-wins policy for ordinary Table/Order edits (PRD's former Open Question 4, now resolved) — NFR-3's atomicity requirement still applies in full to the stock-deduction path regardless of that general policy.

## Rejected/Considered Alternatives

- **AI chat scope**: considered narrowing the Smart Assistant to recipe-generator follow-up only (smaller build surface for the 3-week sprint) but rejected in favor of matching the instructor-approved proposal (consult/version/improve) — see `.memlog.md` decision log, entry re: "AI chat assistant scope resolved."
- **Hard-block vs. override on closing a table with unready items** (was PRD Open Question 1, resolved 2026-07-24 during Reviewer Gate triage): an explicit Admin override was considered and rejected in favor of keeping the hard-block, which is the safer default for a graded demo (no silent data-integrity workaround to explain to a reviewer). That choice is paired with a new FR-7 cancel/void path, which resolves the "walked-out customer" / stuck-item scenario without needing an override mechanism at all.

## Raw Proposal Text

Not reproduced here — the verbatim Hebrew proposal email lives in `secrets/source-proposal.md` (gitignored, kept out of version control since it's private correspondence with the instructor). Treat the PRD's §1–§4 as the authoritative English restatement of its content.

---
_This addendum is a companion to `prd.md` — not a substitute. Audit/decision history is in `.memlog.md`._
