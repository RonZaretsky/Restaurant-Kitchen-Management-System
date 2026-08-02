# PRD Quality Review — Restaurant Kitchen Management System (2026-07-24)

## Overall verdict

This is an unusually rigorous PRD for its stakes: nearly every FR carries testable consequences, NFRs carry numeric/behavioral bounds instead of adjectives, and the assumption/open-question mechanism is used honestly rather than decoratively — including a genuine deliberate deviation from the client's literal proposal wording (FR-9/FR-11 deduction timing), which is exactly the kind of trade-off PRDs usually bury. The risk surface is narrow: one unsupported competitive-novelty claim in the Vision, no internal fallback/priority order across FR-1…FR-21 despite an explicit 3-week build window, and a handful of Assumption-Index/inline-tag roundtrip gaps that matter more than usual here because the addendum flags those tags as graded OOA evidence. None of these threaten the PRD's core usability as OOA/OOD source material.

## Decision-readiness — strong

Trade-offs are named with what was given up, not smoothed over. The clearest example: §9's Assumptions Index entry for FR-9/FR-11 states plainly that automatic stock deduction was deliberately placed at "transition-to-`in_preparation`" rather than at order placement, *despite* the proposal's literal Hebrew wording ("בעת הזמנת מנות" / "upon ordering") — and gives the engineering reason (avoid deducting stock for a cancelled order) rather than hiding the deviation. FR-17's "manage versions" is handled the same way: §4.5 states outright that there is "no separate version-entity, save/revert/compare mechanism, or dedicated diffing UI in v1," with the trade-off pushed to a `[NOTE FOR PM: revisit if the 3-week sprint has slack]` in §6.2 rather than silently narrowed.

§8 Open Questions are genuinely open — e.g. OQ-4 (concurrent-edit conflict handling) and OQ-6 (provenance link from published Dish back to its Recipe Suggestion) have no answer baked into the following sentence; OQ-1 and OQ-2 state a current working assumption but flag it as reversible, not settled.

### Findings
No findings — this dimension is not at risk.

## Substance over theater — adequate

### Findings
- **medium** Unsupported competitive-novelty claim (§1, paragraph 2) — "Competitive research into commercial Kitchen Display Systems (Toast, Square, TouchBistro, Lightspeed) found none that combine live B2B kitchen inventory with generative recipe suggestions" is asserted with no method, date, or source, immediately followed by a strong differentiation claim ("never joined together the way this system joins them"). For a PRD that otherwise earns its claims (deviation-with-reasoning, tagged assumptions), this is the one place a claim outruns its evidence — it reads as the kind of "innovation theater" the rubric warns about even though the rest of the Vision is domain-specific and not swappable. *Fix:* either cite what the "competitive research" consisted of (a paragraph, a search, a prior BMad research step) or soften to "a survey suggests" / mark it `[ASSUMPTION]`.

Personas avoid theater: four system roles (Waiter, Cook, Warehouse Manager, Admin) each map to a distinct UJ and a distinct FR cluster (§4.1–§4.6), and the PRD explicitly excludes the builders' own meta-JTBD from the OOA-relevant persona list (§2.1, closing parenthetical) rather than padding the persona count. NFRs (§ Cross-Cutting NFRs) all carry concrete bounds — "within 2 seconds," "at least four distinct terminals," "atomic... must not both apply" — none of the generic "must be scalable/secure/reliable" boilerplate the rubric flags appears anywhere in the document (verified by search).

## Strategic coherence — strong

The PRD states a real thesis in §1: the operational core (order→prep→checkout handoffs) plus a differentiated Smart Chef layer, explicitly justified against named competitors rather than asserted as self-evidently valuable. Success Metrics follow the thesis rather than measuring activity — SM-1/SM-2 validate the vertical slice and the AI differentiator actually working live, and SM-C1/SM-C2 are genuine counter-metrics (don't chase feature breadth; don't chase "impressive-sounding" AI output at the expense of FR-15's waste-reduction purpose) rather than token gestures at the "counter-metric" template slot.

### Findings
- **medium** No internal prioritization within the "entire v1" scope (§6.1) — §6.1 states "FR-1 through FR-21, in full... this is deliberately the entire v1," and the addendum (Deferred Technical-How, Rejected/Considered Alternatives) confirms a 3-week sprint window. Outside of the one `[NOTE FOR PM]` on the version-comparison UI (§6.2) and the AI-chat-scope note in the addendum's Rejected Alternatives, there is no stated fallback order if the 21-FR set doesn't fit the window — no MoSCoW-style ranking of which FRs could slip first without breaking SM-1/SM-2 (the demo-critical path). Given the PRD itself frames this as a defense-demo deliverable under a hard deadline, an explicit "if behind schedule, cut X before Y" ordering would materially help the builders more than most other single addition. *Fix:* add a short "if compressed" ordering — e.g. FR-13 (manual stock movements) or FR-21 (table config UI) are plausible earlier candidates to trim than anything on the SM-1/SM-2 critical path.

## Done-ness clarity — strong

This is the PRD's strongest dimension. All 21 FRs carry an explicit "Consequences (testable)" block, and a search for the usual vague-adjective tells ("gracefully," "reasonable," "user-friendly," "robust," "scalable," "intuitive," "seamless," "efficient") returned zero matches across the document — including in FR-18 ("Graceful AI degradation"), whose title uses the word but whose consequences are concrete ("no orphaned Recipe Suggestion row," "no dangling Chat Message with an empty/null `content`," "distinguishable from 'still generating'"). Cross-Cutting NFRs give bounds, not adjectives: NFR-1 is "within 2 seconds," NFR-5 is "at least four distinct terminals," NFR-3 and NFR-4 are stated as invariants a test suite could assert directly ("a deduction must never be partially applied," "no code path that mutates `current_stock` without a corresponding movement").

### Findings
- **low** FR-16's consequence ("No code path exists where a Recipe Suggestion writes directly to the Dish/Recipe tables") is a design invariant rather than an externally observable test — fine for OOD purposes but not directly black-box-testable the way the rest of FR-16's neighbors are. *Fix:* none needed for PRD purposes; worth a note to whoever writes the OOD that this maps to a code-review/architecture check rather than a functional test case.

## Scope honesty — adequate

§5 Non-Goals is doing real work — ten explicit bullets, including one `[NOTE FOR PM]` flagging a genuine model/feature gap (the `reserved` Table status exists in the schema but has no booking workflow) rather than letting a reviewer discover the mismatch unassisted. De-scoping is proposed honestly: §6.2's version-comparison UI cut is explained, not silently dropped.

### Findings
- **medium** Assumption-Index roundtrip gaps (§9 vs. inline tags) — three §9 entries have no corresponding inline `[ASSUMPTION: …]` tag at their cited location: **§4.3/§4.4 FR-9/FR-11** (deduction-timing deviation from the proposal's literal wording), **§4.6 FR-19** (soft-delete interpretation of "remove"), and **§4.6 FR-21** (table management as analyst-inferred). All three are stated as fact in the FR body text with no inline flag; a reader of §4 alone (without cross-referencing §9) would not know these are unconfirmed/inferred rather than client-stated. Conversely, the inline tag on **NFR-1** ("the 2-second figure itself is not confirmed... the exact bound was not") has no corresponding entry in §9's index at all. This matters more than a typical mechanical nit here: the addendum explicitly instructs whoever writes the OOA that "this PRD's `[ASSUMPTION]` tags... are the direct mechanism for surfacing that second voice [analyst-inferred vs. client-stated]... don't strip them out" — a roundtrip gap risks the OOA either missing genuine analyst-inference examples or fabricating unflagged ones. *Fix:* add inline `[ASSUMPTION: ...]` tags at FR-9/FR-11, FR-19, and FR-21 pointing to §9; add an NFR-1 entry to §9.

Open-items density (6 Open Questions, 9 Assumption-Index entries, 3 `[NOTE FOR PM]` callouts) is high in absolute terms but proportionate to the stakes as framed: this PRD is deliberately serving as OOA analyst-inference evidence for a graded deliverable, not a green-light-to-build spec for a live product, so the rubric's "high count on green-light PRD is a blocker" red flag does not apply.

## Downstream usability — strong

Glossary (§3) terms are used consistently in FR/UJ text (spot-checked: "Order Item," "Stock Movement," "Recipe Suggestion," "Chat Session" all match their glossary form verbatim across §2.3 and §4). FR IDs (FR-1…FR-21), UJ IDs (UJ-1…UJ-5), SM IDs (SM-1…SM-4, SM-C1/C2), and NFR IDs (NFR-1…NFR-5) are contiguous with no gaps or duplicates. Cross-references resolve: SM-1's "Validates FR-4 through FR-11" and SM-2/SM-3's FR citations all point to real, matching FRs; FR-6/FR-8 both correctly cite NFR-1 for their real-time bound instead of restating it. Every UJ has a named, recurring protagonist (Maya, Amir, Noa, David) reused consistently across UJ-1→UJ-2's shared Table-12 scenario, which is a stronger continuity signal than most PRDs bother with.

### Findings
- **low** Minor capitalization drift on "Low-Stock Alert" — Glossary (§3) and body prose use "Low-Stock Alert" (title case), but FR-12's own heading is "Low-stock alert" (sentence case). Cosmetic only; noted in Mechanical notes as well.

## Shape fit — strong

This is a multi-role internal operational tool with real per-role UX divergence (four roles see materially different screens/actions), so UJ-with-named-protagonist treatment is load-bearing rather than over-formalized — five UJs for four roles plus one AI-augmented variant (UJ-5, Cook-as-chef) is proportionate, not persona-padding. The PRD also correctly identifies and manages its unusual dual-audience shape (§0): it stays implementation-flavored (`password_hash`, `cook_id`, `AIRecipeSuggestion`) for engineering's benefit while explicitly flagging what must be stripped for the zero-implementation-detail OOA, rather than picking one register and forcing the other document to fight it.

Brownfield-accuracy spot check against the actual codebase confirmed the PRD's existing-schema references are correct, not aspirational: `password_hash`, `cook_id`, `reference_id`, `RestaurantTable` (with `available`/`occupied`/`reserved` enum values matching §3's Glossary exactly), and the `purchase`/`consumption`/`waste`/`adjustment` Stock Movement types all exist as named in `backend/data_models/*.py`; `container.wire()` is indeed present only in `backend/container.py` with no evidence of being invoked elsewhere, matching the addendum's claim that DI wiring "is not yet activated anywhere in the codebase."

### Findings
No findings — this dimension is not at risk.

## Mechanical notes

- **Assumption-Index roundtrip** (see Scope honesty above for full detail): §9 entries for FR-9/FR-11, FR-19, and FR-21 lack inline `[ASSUMPTION: …]` anchors in §4; the inline `[ASSUMPTION: …]` on NFR-1 (2-second bound) is not indexed in §9.
- **Glossary drift**: "Low-Stock Alert" (§3 Glossary, title case) vs. FR-12's heading "Low-stock alert" (sentence case) — cosmetic, does not affect meaning.
- **ID continuity**: FR-1…FR-21, UJ-1…UJ-5, SM-1…SM-4 + SM-C1/C2, NFR-1…NFR-5, OQ-1…OQ-6 all contiguous with no gaps, duplicates, or dangling cross-references found.
- **Required sections**: all sections the rubric and the PRD's own §0 commitments call for are present (Vision, Target User with JTBD/Non-Users/UJs, Glossary, Features with per-FR consequences, Non-Goals, MVP Scope, Success Metrics with counter-metrics, Open Questions, Assumptions Index, Cross-Cutting NFRs, Constraints & Guardrails, Platform) — no missing section for the agreed launch-tier/OOA-source stakes.
