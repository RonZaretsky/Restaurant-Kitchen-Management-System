---
title: Design Gaps & Decisions — Restaurant Kitchen Management System
status: draft
created: 2026-07-29
source_artifacts:
  - _bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md
  - _bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/addendum.md
  - docs/architecture-backend.md
  - docs/architecture-frontend.md
  - docs/data-models-backend.md
---

# Design Gaps & Decisions

## How to read this document

**Important framing before you read further:** in BMad terms, only the **PRD** is finalized (2026-07-24, 24 FRs). **Architecture, UX design, and epics/stories have not been run yet** — the `docs/` folder you already have is a scan of the *existing brownfield scaffold* (what's literally in the repo today), not a forward-looking design. Concretely, the codebase today is:

- **Backend**: FastAPI app with a `dependency-injector` container, an async SQLAlchemy schema (11 tables, matches the PRD's Glossary), and exactly one route (`GET /health`). No auth, no CORS, no business logic, no tests.
- **Frontend**: Vite + React 19 scaffold with one placeholder component. No routing, no state management, no UI library, no API client, no tests.

So "concluding design and specification" is accurate for the *requirements* (PRD is genuinely done and solid), but **not yet** for the *technical design* (OOD) or the *UX*. A meaningful chunk of what's below isn't a gap in your thinking — it's work that BMad's later phases (`bmad-architecture`, `bmad-ux`, `bmad-create-epics-and-stories`) exist specifically to resolve. I've flagged which items are "decide it yourselves now" vs. "this is what architecture/UX will produce" so you don't try to hand-roll a full OOD in this conversation.

**Status tags:**
- `[RESOLVED]` — a gap or open question from earlier work that's already been decided — listed for the record, not for re-discussion.
- `[GAP]` — something missing from the design/spec that will bite you during implementation if unaddressed.
- `[OPEN]` — a question the PRD itself already flagged as unconfirmed, or one I'm surfacing now, needing your input.
- `[NEEDS DECISION]` — a concrete choice (stack, mechanism, process) blocking forward progress, where the option space is known and you just need to pick.

**A note on sourcing §1 (Resolved / Closed Gaps):** I don't have the raw back-and-forth transcript of the earlier PRD-drafting conversation — that was a separate session. What I do have is that PRD run's own decision log (`.memlog.md`, 38 timestamped entries) and the PRD's `§9 Assumptions Index`, which explicitly marks certain items `"confirmed decision"` vs. still-unconfirmed. §1 below is reconstructed from those artifacts, not from memory — each item traces to a specific memlog entry or PRD section, cited inline.

---

## 1. Resolved / Closed Gaps

These were open questions, gaps, or contradictions surfaced during the PRD's own drafting and Reviewer Gate (edge-case-hunter + rubric) passes — all already decided. Listed here so nothing gets silently re-opened, not because they need your attention again.

- `[RESOLVED]` **Table close: hard-block or allow an override for unready items?** Kept the hard-block (no override) — the safer default for a graded demo with no silent data-integrity workaround to explain — paired with a *new* cancel/void path (FR-7) so a stuck item can't deadlock a table close indefinitely. *(Former Open Question 1; `addendum.md` Rejected Alternatives)*
- `[RESOLVED]` **Smart Chef OpenAI cost cap — enforce a per-user/per-day spending limit?** No cap in v1. A small team's academic usage volume is inherently low and self-contained; a cap mechanism wasn't judged worth the sprint time. *(Former Open Question 2; PRD §4.5 feature NFR)*
- `[RESOLVED]` **Concurrent edits to the same Table/Order — need locking or a conflict UI?** Last-write-wins in v1, no optimistic locking or conflict UI (new NFR-6) — appropriate for a single small kitchen's low real-world contention. Explicitly scoped separately from NFR-3's stricter atomicity guarantee for the stock-deduction path, which still applies in full. *(Former Open Question 4)*
- `[RESOLVED]` **Should a published Dish keep traceable provenance back to the AI Recipe Suggestion it came from?** Yes — a confirmed Recipe Suggestion leaves a nullable provenance link on the resulting Recipe once an Admin turns it into a live Dish, so "this started as an AI suggestion" can be shown, not just claimed. *(Former Open Question 6; FR-19)*
- `[RESOLVED]` **Does "manage versions of dishes" (proposal wording) require a dedicated version-entity/diff UI?** No — satisfied conversationally: each Smart Assistant chat turn is itself a retrievable version/iteration of the recipe being discussed. You confirmed this directly; it's no longer an assumption tag in the PRD. *(FR-20)*
- `[RESOLVED]` **Do all Waiters see all tables, or is there per-waiter table assignment?** All Waiters see all Tables and Orders — no per-resource filtering in v1. *(FR-6, consistent with FR-2's Role-level-only permission model)*
- `[RESOLVED]` **Can a Dish be marked available without a defined recipe?** No — a Dish cannot go live while its Recipe has zero ingredient lines, closing a risk where stock deduction would silently be a no-op for a live menu item. *(FR-22)*
- `[RESOLVED]` **Scope of Admin user-management — create only, or also edit/reactivate?** Expanded to include Role/name edit and reactivation of a previously deactivated User, plus a last-admin-lockout guard (deactivating/demoting the last active Admin is rejected). *(FR-3)*
- `[RESOLVED]` **What happens to an Order's total if a Dish's price changes while the Order is still open?** Price locks at add-time — each Order Item stores `price_at_add`, and the Order total is always computed from these stored prices, never the Dish's live price. *(FR-5/FR-8)*
- `[RESOLVED]` **What happens to already-queued kitchen items when a Dish is 86'd (marked unavailable) mid-service?** Marking unavailable only blocks new adds going forward — items already `pending`/`in_preparation`/`ready` for that Dish proceed to completion normally, not auto-voided. *(FR-22)*
- `[RESOLVED]` **Are a Cook's Smart Chef chat sessions/suggestions private, or shared?** Shared — no per-Cook access restriction (matching FR-2's Role-level-only model) — but the default list view filters to the current Cook's own sessions/suggestions first, as a personalization default rather than a permission boundary. Your own framing, given directly during triage. *(FR-20)*
- `[RESOLVED]` **Does deactivating a Cook mid-shift strand their in-progress order items?** No — the recorded `cook_id` is attribution/audit only, not an access lock; any other active Cook can already progress an `in_preparation` item to `ready`. *(FR-10 consequence)*
- `[RESOLVED]` **Is there a way to mark an Order "served," distinct from the kitchen finishing it?** Yes — added FR-11 (Waiter marks an Order served once ready), closing a gap where the lifecycle previously jumped straight from ready to closed.
- `[RESOLVED]` **What creates the master Ingredient record that Stock Movements and Recipes reference?** Added FR-16 (Warehouse Manager or Admin can create an Ingredient) — no FR previously covered this at all.
- `[RESOLVED]` **Stock-deduction timing contradiction — does deduction happen when an item is marked "ready," or when prep starts ("in_preparation")?** Resolved to `in_preparation` (deduction happens when prep starts), matching the pre-existing `database-schema.md` business logic and avoiding deducting stock for items that are cancelled or never started. *(FR-10/FR-13; this was a genuine drafting contradiction between two FRs, caught during input reconciliation)*
- `[RESOLVED]` **Scope of the Smart Assistant chat — recipe-generator follow-up only, or the full consult/version/improve proposal?** Full scope, matching the instructor-approved proposal — a narrower cut was considered and rejected. *(FR-20; `addendum.md` Rejected Alternatives)*
- `[RESOLVED]` **Terminology correction: are the course deliverables "COA" or "OOA/OOD"?** Corrected to OOA (Analysis) / OOD (Design) early in drafting, before it could propagate through the rest of the PRD.

---

## 2. Identified Gaps

### 1.1 Architecture / infrastructure gaps (nothing built yet)

- `[GAP]` **No authentication or authorization layer exists in code.** Every current route is effectively public (`docs/architecture-backend.md`). FR-1/FR-2/NFR-2 require this built from zero — there's no partial implementation to extend.
- `[GAP]` **No CORS middleware on the backend.** The frontend cannot successfully call the API from a browser yet (`:3000`/`:80` vs `:8000`). Blocks *any* end-to-end feature work, not just auth — worth fixing first regardless of what else is prioritized.
- `[GAP]` **No real-time push mechanism implemented.** NFR-1 requires push-not-poll propagation within ~2s (Waiter ↔ Cook), but no WebSocket/SSE library is present anywhere in the stack today. This is arguably the single riskiest piece of unbuilt infrastructure relative to the demo's centerpiece (UJ-1 → UJ-2).
- `[GAP]` **No migration tool.** Schema is created via `Base.metadata.create_all()` on every startup — additive only, won't alter or drop existing tables. Any schema change after your first real deployment/demo data load requires a full DB reset. Given the PRD's FRs will require schema additions (e.g. any RBAC/session table, cancel/void state), decide now whether Alembic goes in or whether you accept "wipe the DB on schema change" for the whole project lifetime.
- `[GAP]` **No concurrency-control mechanism for NFR-3.** The PRD requires atomic stock deduction (no double-deduct, no partial deduction across a Recipe's ingredients), but no locking strategy, transaction isolation level, or DB-transaction boundary has been chosen. This is explicitly deferred to architecture in the addendum, but it's worth naming here as unimplemented, not just undesigned.
- `[GAP]` **OpenAI integration is entirely unbuilt.** No client wiring, no model choice, no prompt template, no cost-attribution mechanism exists. FR-18/FR-20/FR-21 (the whole Smart Chef feature, one of your two Success Metrics) depend entirely on this being designed and built from scratch.
- `[GAP]` **No test framework installed on either side** (no `pytest`/`httpx` on backend, no `vitest`/`@testing-library/react` on frontend). Given a fixed defense date, deciding your testing bar *now* (even "smoke tests only for the demo path") avoids either scrambling late or silently skipping tests entirely.
- `[GAP]` **No frontend state-management, routing, or UI-component-library choice.** Four distinct role-based screens (Waiter, Kitchen Display, Warehouse, Admin) plus a chat UI (Smart Chef) all need to share/receive real-time state, and none of the plumbing for that exists yet — not even a chosen approach.

### 1.2 Functional / edge-case gaps not covered by any FR

- `[GAP]` **`reserved` Table status has no lifecycle at all.** The schema supports `TableStatus.reserved`, and FR-4 says a `reserved` table is treated like `occupied` (blocked from a new Order) — but **no FR ever sets a table to `reserved` or clears it back to `available`.** As written, if a table is ever set to `reserved` by any means, it becomes permanently unusable in v1 (no FR to un-reserve it). This is a step beyond the PRD's own "no reservation *workflow*" non-goal (§5) — that non-goal covers the booking-ahead feature; this gap is about the enum value having no in/out transition *at all*, which risks a self-inflicted dead table.
- `[GAP]` **Lost-credential lockout for the last Admin.** FR-3 correctly blocks deactivating/demoting the last active Admin, but there's no password-reset flow anywhere in FR-1/FR-3. If that Admin's password is lost, there is no in-system recovery path in v1 — likely fine as an explicit non-goal (matches your project's existing pattern of naming simplifications rather than leaving them silent), but it should be *named*, not discovered live during the defense.
- `[GAP]` **No FR addresses demo/seed data.** SM-1–SM-4 require a live defense demo with tables, dishes, recipes, and stock already populated. Nothing currently specifies whether that's manual setup via the FRs themselves during a rehearsal, or a seed script/fixture. Worth deciding now since a seed script is itself a small piece of extra work to schedule into the 3-week sprint.
- `[GAP]` **FR-18's "only in-stock ingredients used" has no validation gap.** The PRD already flags this as enforced by prompt construction only, "not independently validated post-generation" (§9). Concretely: if the LLM hallucinates an ingredient not in current stock, or misspells one, nothing catches it before the Cook sees the suggestion. Worth deciding whether a lightweight post-generation check (suggested ingredient names must match existing `Ingredient` rows) is in scope, given it's cheap to add and directly protects FR-18's stated purpose (waste reduction from *real* stock).

### 1.3 Documentation gaps (relative to what the course grades)

- `[GAP]` **No OOD content exists yet** — Class/Sequence/Activity/Use-Case diagrams, design patterns, layering, naming conventions, and future-extensibility notes are all still to be produced. This is the single largest remaining piece of *graded* work (60% of Maman 12's weight) and it's produced by `bmad-architecture`, not by hand-writing UML directly from the PRD.
- `[GAP]` **No OOA extraction has been done yet** — the PRD is deliberately written to feed the OOA (per its own §0), but the actual client-facing, zero-implementation-detail OOA document doesn't exist as a separate deliverable yet.

---

## 3. Clarifications Needed

These are points the PRD itself already flagged as unconfirmed (`§8 Open Questions`, `§9 Assumptions Index`) that are still genuinely open, plus a couple I'm surfacing now. Items the PRD already marked "confirmed decision" are **not** repeated here — see `prd.md` §9 if you want the full list of what's already settled.

- `[OPEN]` **Session survival across refresh.** Should a login session survive a browser refresh mid-shift, and for how long? (PRD §8, Open Question 1). The *mechanism* (JWT vs. server session) is architecture's call, but this behavioral expectation is yours to set first, since it constrains the mechanism choice.
- `[OPEN]` **Table delete/renumber.** Does `table_number` uniqueness (FR-24) need to survive a deleted/deactivated table being renumbered, or are tables add-only forever in v1? (PRD §8, Open Question 2 — no FR currently covers removing or renumbering a table.)
- `[OPEN]` **NFR-1's exact 2-second bound.** The PRD confirms *push, not poll* is a hard requirement, but the specific "2 seconds" figure itself was never directly confirmed with you — it's a placeholder that felt reasonable at drafting time. Worth a quick gut-check: is 2s the right number for a kitchen-pass replacement, or should it be tighter/looser?
- `[OPEN]` **`reserved` Table treatment.** FR-4 assumes a `reserved` table can't be opened into a new Order (same as `occupied`), for lack of a reservation-arrival workflow that would say otherwise. Combined with the 1.2 gap above (no way to set/clear `reserved` at all), it may be simplest to just confirm: should `reserved` be reachable by *any* FR in v1, or should it be treated as dead code in the enum for now?
- `[OPEN]` **No stock-reversal on cancelling an in-preparation item.** FR-7 assumes cancelling an `in_preparation` Order Item does *not* auto-reverse its stock deduction (ingredients treated as already used/opened) — a Warehouse Manager would need to log a manual `waste` movement separately if that's not true in practice. Confirm this matches how your kitchen scenario actually works.
- `[OPEN]` **No undo on status transitions.** FR-10 assumes `in_preparation → pending` and `ready → in_preparation` are never needed — a mis-pick or mis-mark-ready is corrected via cancel, not undo. Confirm this is acceptable, since it means a Cook's mistake becomes a cancelled item (lost from the Order) rather than a corrected one.
- `[OPEN]` **Reject vs. queue for concurrent Smart Chef requests.** FR-18 rejects a second suggestion-generation request from the same Cook while one is in flight, rather than queuing it. Low-stakes, but confirm the UX expectation (an error toast vs. a disabled button vs. a queued spinner) since it affects both backend and frontend behavior.

---

## 4. Pending Decisions

These are choices where the *option space* is basically known and it's a matter of picking, not open-ended discovery. Several are explicitly named in the PRD's addendum as "belongs to `bmad-architecture`, not this PRD" — I've kept those grouped separately from process decisions that are actually yours to make right now, independent of any BMad skill.

### 4.1 Technical stack / mechanism (→ resolved by `bmad-architecture`)

- `[NEEDS DECISION]` **Real-time push mechanism** for NFR-1 — WebSockets vs. Server-Sent Events vs. long-polling.
- `[NEEDS DECISION]` **Session/auth implementation** for FR-1/FR-2 — JWT vs. server-side session store, expiry policy, refresh strategy. Also needs `container.wire()` activated for any DI-based auth dependency (currently inert).
- `[NEEDS DECISION]` **Concurrency control** for NFR-3 — optimistic locking, DB transaction isolation level, or row-level locking specifically for the stock-deduction path (narrower than NFR-6's already-decided last-write-wins policy for ordinary field edits).
- `[NEEDS DECISION]` **OpenAI integration specifics** for FR-18/FR-20 — which model, prompt template design, per-call cost-attribution mechanism (the *policy* — no cap — is already decided; the *mechanism* to track cost per call isn't).
- `[NEEDS DECISION]` **Migration strategy** — adopt Alembic now vs. accept full-reset-on-schema-change for the project's lifetime (leans on the `[GAP]` above).
- `[NEEDS DECISION]` **Frontend routing/state-management/UI-library choice** — nothing chosen yet; blocks starting any real screen.
- `[NEEDS DECISION]` **Testing strategy** for both sides — framework choice is easy (`pytest`+`httpx`, `vitest`+`@testing-library/react` are the natural defaults per the brownfield scan), but *scope* (what gets tested given the timeline) is a real decision.

### 4.2 Process decision (yours to make now, not architecture's)

- `[NEEDS DECISION]` **Whether to run the remaining BMad design phases before coding, or start coding now.** You've finalized the PRD; the natural next steps per BMad are `bmad-architecture` (produces the OOD content — Class/Sequence/Activity diagrams, resolves every 3.1 item above, and is the graded-heaviest remaining artifact) and `bmad-ux` (produces the four role-based screen layouts + the Smart Chef chat UI, none of which have any design yet), optionally followed by `bmad-create-epics-and-stories` to slice the 24 FRs into a sprint-sized backlog. Given your 3-week coding-sprint pressure, the real decision is sequencing: architecture first (recommended — it directly produces graded OOD content and de-risks the technical unknowns in 3.1), then UX for the four screens, then epics/stories to structure the sprint — or some compressed/parallel variant if time is tighter than expected.

---

## Recommended Path Forward

1. **`bmad-architecture`** — highest priority. Resolves every item in §4.1, produces the OOD's required Class/Sequence/Activity/Use-Case diagrams, and is worth roughly 60% of Maman 12's weight — the single highest-leverage next step.
2. **`bmad-ux`** — four role-based screens (Waiter, Kitchen Display, Warehouse, Admin) plus the Smart Chef chat UI currently have zero design; can run in parallel with or right after architecture.
3. **`bmad-create-epics-and-stories`** — once architecture (and ideally UX) exist, slice the 24 FRs into a sprint-sized backlog for the 3-week coding push.

Each runs best in a fresh context window. Use `bmad-help` if you want routing help deciding which to start with, or just start `bmad-architecture` directly since the sequencing question above already points there.

_This document is a working checklist, not a BMad-generated artifact — update or delete items as you resolve them._
