# Reconciliation: PRD vs. Approved Proposal

**Purpose:** The instructor approved `source-proposal.md` (the original Hebrew email), not `prd.md`. This document checks the PRD against that proposal specifically, since any silent drift, narrowing, or contradiction is a real grading risk — the students could be judged against what they promised the instructor, not against the PRD's own framing of itself.

**Method:** Walked each of the proposal's 5 modules + tech stack + roles against the PRD's Features (§4) and FRs, then checked the PRD for capabilities that go beyond the proposal's literal text.

**Overall verdict:** 4 of 5 modules map cleanly. One real, PRD-self-acknowledged gap exists in the Smart Chef module (versioning). One unflagged reinterpretation exists in inventory-deduction timing. Two minor unflagged scope narrowings/additions exist in Administration. Tech stack and roles are faithful.

---

## Real gaps (proposal capability missing or weakened in PRD)

- **Smart Chef "manage versions of dishes" (לנהל גרסאות של מנות) is not actually implemented — only named.** The proposal lists three distinct chat-assistant capabilities: consult, **manage versions of dishes**, and improve existing recipes. PRD's FR-17 is titled "Consult, version, and improve recipes via Smart Assistant chat," but its actual mechanism is only a persisted `Chat Session` of ordered messages — there is no entity, field, or FR for a saved/named/numbered recipe version, no ability to list, compare, or revert versions, and FR-20 ("An Admin can define/edit... a Dish['s Recipe]") implies each Dish has exactly one current Recipe with edits overwriting it, not a version history. Worse, §6.2 MVP Out-of-Scope explicitly defers "Recipe-version *history/diffing UI*" and says "the Smart Assistant chat (FR-17) captures iteration conversationally" — i.e., the PRD itself concedes that "iteration via chat" is being substituted for "managing versions," while §6.1 simultaneously claims FR-17 is fully in scope and satisfies the proposal. This is the exact substitution the task flagged as the likely gap, and it is real: conversational chat history is not dish-version management (no way to name a version, return to a prior one, or compare two side by side). The PRD's own `[NOTE FOR PM]` at §6.2 shows the authors sensed this but didn't resolve it. **Action needed:** either build a minimal version-save/list/revert capability into FR-17/FR-20, or get explicit instructor/proposal-owner sign-off that "chat iteration" satisfies "ניהול גרסאות" before the OOA is written — right now the PRD would let the OOA get written against a capability the system won't actually have.

## Unflagged reinterpretations (proposal wording bent without a PRD assumption tag)

- **Stock-deduction trigger point.** Proposal: "עדכון מלאי אוטומטי בעת הזמנת מנות" — automatic inventory update **when dishes are ordered**. PRD's actual behavior deducts stock only when a Cook starts/finishes preparing the item (FR-9/FR-11), not when the Waiter places the order (FR-5) — a defensible design choice (avoids drift from cancelled orders) but a real reinterpretation of "בעת הזמנת" that is never entered into §9 Assumptions Index alongside the PRD's other reinterpretations.
- **Internal PRD inconsistency compounds this**: FR-9's consequences say "Transitioning to `ready` triggers automatic stock deduction (FR-11)," while FR-11's own body text says "When an Order Item transitions to `in_preparation` (FR-9), the system deducts..." — these two FRs disagree with each other about which transition fires the deduction (`in_preparation` vs. `ready`). UJ-2's narrative sides with `ready`. This should be resolved before OOD/Class-diagram work, since it affects the Sequence diagram the addendum earmarks for this exact flow.

## Minor scope narrowing (proposal capability softened, not flagged)

- **Dish removal.** Proposal: "הוספה/**הסרה** של מנות" — add/**remove** dishes. PRD's FR-19 only supports create/update/mark-unavailable; there is no actual delete/removal path. Soft-delete-via-unavailable is a reasonable and probably correct call (preserves order history integrity), but it silently narrows "remove" to "hide," and isn't logged as a deviation anywhere in §9.

## Minor scope addition (reasonable elaboration, but beyond the proposal's literal list — worth confirming, not necessarily a problem)

- **FR-21 (Admin manages restaurant tables)** has no counterpart in the proposal's Administration bullet list, which names only menu management and user/permissions management. Tables have to be configured by someone, so adding this to Admin is sensible engineering judgment — but since the proposal enumerated Administration's scope explicitly (two items) and the PRD adds a third capability under the same feature area, it's the kind of addition the task asked to surface for conscious confirmation rather than silent inheritance.
- Various other elaborations (NFR-1's 2-second latency bound, FR-12's alert-dedup logic, FR-13's purchase/waste/adjustment movement types, FR-16's human-confirmation gate before a suggestion becomes a menu item, FR-18's AI-failure handling) are all reasonable fleshing-out of things the proposal only gestured at ("בזמן אמת," "התראות... על חוסרים," "מלאי חומרי גלם"). These are the kind of inferred requirements the course's OOA explicitly wants captured (per `addendum.md`'s note that the analyst must "represent... the analyst inferring additional requirements the client didn't state explicitly") — not scope creep to worry about, and several are already self-tagged `[ASSUMPTION]` in the PRD.

## Tech stack — no gap

Proposal approved: Python, FastAPI (server); SQLAlchemy + Pydantic (data/validation); React (client). The PRD deliberately stays capability-first and defers all technology choices to `addendum.md`/architecture, and the addendum's "Deferred Technical-How" section only discusses mechanism *categories* (WebSockets/SSE/long-polling for real-time; JWT vs. server-session for auth) without committing to anything outside the approved stack. The one concrete technology named in the addendum — `dependency-injector` (`container.wire()`) — is described as an existing brownfield codebase dependency already present in `docs/architecture-backend.md`, not a new PRD-introduced stack choice, and it sits inside the approved Python/FastAPI boundary. No contradiction found.

## Roles — no meaningful gap

| Proposal (Hebrew) | PRD Glossary/Role | Assessment |
|---|---|---|
| מלצרים (waiters) | `waiter` | Exact match |
| טבחים (cooks) | `cook` | Exact match |
| מנהל מחסן (warehouse manager) | `warehouse_manager` | Exact match |
| מנהל ראשי (chief/main manager) | `admin` — "restaurant owner/manager" | Close match; PRD's JTBD gloss adds "owner" which the proposal's "מנהל ראשי" doesn't literally say (it says *manager*, not *owner*), a small semantic broadening. Low risk — the role's permissions (menu + user/permission management) match what the proposal assigns to מנהל ראשי either way. |

The PRD's role-based-permissions design (FR-2, four fixed roles, no fine-grained per-resource permissions in v1) matches the proposal's own framing — the proposal frames "ניהול הרשאות" as flowing from the user-type hierarchy itself ("מבנה זה יאפשר ניהול הרשאות... עבור המשתמשים השונים"), which is exactly what FR-2 implements. Not a gap.

## Modules fully covered, no issues

- **Order management** (proposal §1) → PRD §4.2, FR-4–FR-7: full match (open table, real-time status, close/checkout).
- **Kitchen management** (proposal §2) → PRD §4.3, FR-8–FR-10: full match (real-time incoming orders, prep workflow, "passed" reporting).
- **Inventory/logistics tracking & shortage alerts** (proposal §3, minus the deduction-timing point above) → PRD §4.4, FR-12–FR-14: full match.
- **Recipe generator** (proposal §4a) → PRD FR-15: full match, including the waste-reduction framing and OpenAI-API basis.
- **User/permission management** (proposal §5b) → PRD FR-2/FR-3: full match.
