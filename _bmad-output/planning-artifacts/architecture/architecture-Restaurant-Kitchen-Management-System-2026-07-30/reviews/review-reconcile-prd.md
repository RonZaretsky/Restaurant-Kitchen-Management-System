---
title: Architecture Spine Reconciliation — Restaurant Kitchen Management System
reviews: '_bmad-output/planning-artifacts/architecture/architecture-Restaurant-Kitchen-Management-System-2026-07-30/ARCHITECTURE-SPINE.md'
against:
  - '_bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md'
  - '_bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/addendum.md'
date: 2026-07-30
verdict: has-gaps
---

# Reconciliation Review: Architecture Spine vs. PRD + Addendum

## Scope note

Per instructions, UX/screen design is out of scope for this review — the spine explicitly defers it and that's correct. This review focuses on FR/NFR-level business rules, invariants, and edge cases the spine's ADs should bind but silently dropped, contradicted, or subtly narrowed.

---

## Finding 1 (CRITICAL — direct contradiction) — AD-11 reverses FR-7's explicit no-auto-reversal rule

**Spine (AD-11):**
> "...if that item had already reached `in_preparation` (stock deducted per AD-6), cancellation inserts a compensating `StockMovement` in the same transaction."

**PRD (FR-7 consequence, verbatim):**
> "Cancelling an `in_preparation` Order Item does **not** automatically reverse its stock deduction (FR-13) — the ingredients are treated as already used/opened. A Warehouse Manager can log a manual `waste` movement separately if physically applicable."

This is not a nuance — it's the opposite rule. The PRD's own Assumptions Index (§9) records this as a deliberate decision, with explicit reasoning: *"no-auto-reversal is the simpler, safer default (no invented 'undo consumption' movement semantics)."* AD-11 is tagged `[ADOPTED — PRD FR-7]`, i.e. it claims to encode FR-7, but instead encodes the alternative the PRD considered and rejected (auto-compensating reversal). If built as written, AD-11 would silently restore stock on every mid-prep cancellation — inflating on-hand stock relative to what was actually pulled/opened, which is exactly the "invented undo-consumption semantics" the PRD chose to avoid.

**Recommendation:** AD-11 should read: cancelling a `pending` item has no stock impact (nothing was deducted); cancelling an `in_preparation` item leaves its prior deduction as-is (no compensating movement) — a WM may separately log a manual `waste` movement if applicable. The "terminal status, never delete the row" half of AD-11 is correct and should stay.

---

## Finding 2 — AD-2's WebSocket binding list silently excludes Low-Stock Alerts / inventory

**Spine (AD-2):**
> **Binds:** kitchen board and order/table status updates

Only two update classes are named. UJ-3 (Noa) is explicit that the low-stock alert is a live, push-style event — "Noa gets an alert" while she's away from the screen doing physical stock work, mirroring the same "no manual refresh" framing FR-6/FR-9 get under NFR-1. FR-14 is a first-class FR with its own atomicity/dedup consequences, not a side effect of order/table flow.

As written, AD-2 leaves it genuinely ambiguous whether a Low-Stock Alert rides the same WebSocket channel as kitchen/order updates or is left to polling/on-view computation — which would be inconsistent with the "push, not poll" spirit the PRD explicitly confirmed for NFR-1 (only the *2-second bound* was left unconfirmed, not the push-vs-poll choice itself). Since AD-2's stated purpose is precisely to prevent "different features independently choosing polling vs. push," omitting inventory from its own binding list undercuts that purpose for the one feature (FR-14) most explicitly framed as real-time in the PRD.

**Recommendation:** Either broaden AD-2's "Binds" line to explicitly include low-stock/inventory alerts, or add an explicit note if inventory alerts are intentionally poll-based (e.g. "computed at read time" per the Glossary's Low-Stock Alert definition) — right now it reads as an omission, not a decision.

---

## Finding 3 — No architectural mechanism for FR-18's "one generation in flight per Cook" guard

FR-18 has an explicit, testable consequence: *"A second FR-18 request from the same Cook while an earlier one for them is still in flight is rejected rather than queued."* This requires some stateful tracking (in-memory registry, a DB flag/status column, a short-lived lock) scoped per-Cook. AD-12 covers only the OpenAI client abstraction (interface, single configured model) — it says nothing about where/how in-flight-request state is tracked. Given the single-process Docker Compose deployment this is a small decision, but it's exactly the kind of thing that, left unstated, two people could implement two different (and differently buggy) ways — which is the stated purpose of writing ADs at all. Worth at least a one-line rule (e.g., "tracked via a status column on the in-flight request row, checked-and-set in the same transaction that creates it") alongside AD-12 or AD-6-style atomicity language.

---

## Finding 4 — FR-21's "no orphaned records on AI failure" integrity rule has no AD analog

FR-21 requires: *"A failed generation leaves no orphaned Recipe Suggestion row and no dangling Chat Message with an empty/null `content`."* This is a transactional-integrity requirement in the same spirit as AD-6 (atomic stock deduction) and AD-11 (no broken rows on cancel) — but nothing in the spine states the equivalent invariant for the Smart Chef write path (e.g., "the suggestion/message row is only inserted after a successful OpenAI response; a failed call writes nothing"). Since AD-12 already establishes that all OpenAI calls go through a dedicated client, this would be a natural, low-cost addition (write-after-success, or wrap create+call+persist and roll back the row on failure) but it isn't stated anywhere, so it's easy to implement as "create row, then fill in result" — which is precisely the ordering that produces the orphaned/dangling rows FR-21 forbids.

---

## Finding 5 (minor, paired) — Two explicit business rules with no AD-level analog, unlike similarly-scoped rules that did get one

The spine elevated several single-rule business constraints to AD status (AD-7 price lock, AD-8 dish-availability gate, AD-11 cancel/void). Two comparably explicit, testable PRD rules did not get the same treatment and have no mention anywhere in the spine:

- **FR-3**: "Deactivating or demoting the last remaining active Admin account is rejected — the system always keeps at least one Admin able to log in and manage users." A single missed guard here breaks the whole system's admin-recovery path; it's exactly the class of rule AD-8 exists to protect against for dishes (a live-but-broken state).
- **FR-15**: "...stock is never floor-capped at zero, since the audit trail should reflect what actually happened even when it exceeds what was recorded as on-hand." This applies to *both* the automatic consumption path (FR-13, under AD-6) and the manual movement path (FR-15, not covered by any AD) — if only one of the two paths gets a floor-at-zero guard added later (a very natural "safety" instinct for a reviewer/implementer to add), the two paths silently diverge.

These are lower severity than Findings 1–4 (no contradiction, just omission of rules the spine's own pattern suggests should be ADs), but worth a one-line mention each if the spine gets a revision pass.

---

## Secondary / lower-priority technical note (not a top finding)

**NFR-3 vs. AD-6's locking mechanism:** NFR-3 requires "two near-simultaneous transitions on the same Order Item must not both apply." AD-6 wraps the status update + stock decrement + StockMovement insert in "one DB transaction," but a bare transaction at default isolation doesn't by itself prevent two concurrent transactions from both reading `status = pending` and both proceeding — that needs an explicit guard (row lock / `SELECT ... FOR UPDATE`, or a conditional `UPDATE ... WHERE status = 'pending'` with a rowcount check). The addendum's own "Deferred Technical-How" section correctly flags "concurrency control for NFR-3" as architecture's job to design, but AD-6 as written doesn't fully close that loop — it states the transaction boundary but not the concurrency-safety mechanism inside it. This is more implementation-level than the other findings (the spine intentionally defers comparably fine-grained items elsewhere, e.g. WebSocket handshake mechanics), so it's flagged here for awareness rather than as a top-5 finding.

---

## What the spine got right (for contrast, not exhaustive)

- AD-9's role-level-only permission model, including the explicit UI-default-vs-access-filter carve-out for AD-10, correctly mirrors FR-2/FR-6/FR-20's "no per-resource filtering" rule and its Cook-list-ordering exception.
- AD-7 (price lock) and AD-8 (dish-availability gate) are faithful, precise encodings of FR-5/FR-8 and FR-22 respectively.
- The Structural Seed's core-entities ERD correctly omits a "Low-Stock Alert" entity, matching the Glossary's explicit "derived state, not a stored record" definition — a good instance of *not* over-modeling.
- AD-10's provenance FK and its "UI default, not access filter" framing correctly track FR-19/FR-20, including the addendum's confirmed (not merely assumed) status of the shared-visibility decision.
- The Deferred section's handling of session duration, table delete/renumber, and the status-enum literals correctly identifies genuine open PRD questions rather than silently picking an answer.
