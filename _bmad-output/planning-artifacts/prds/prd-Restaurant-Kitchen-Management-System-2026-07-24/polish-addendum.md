# Editorial Polish — `addendum.md`

Two-pass review (structure, then prose) of the PRD addendum. Recommendations only — nothing has been applied to `addendum.md` yet.

---

## Pass 1 — Structural Review

## Document Summary
- **Purpose:** Help whoever writes the downstream OOA/OOD deliverables (and future reviewers of PRD decisions) quickly locate crosswalk, grading-rubric, and decision-rationale content by jumping to the relevant section — not by reading start to finish.
- **Audience:** The two students authoring the OOA/OOD documents next; secondarily, reviewers auditing why a PRD decision was made.
- **Reader type:** humans (default)
- **Structure model:** Reference/Database (random access, MECE topics)
- **Current length:** ~1,732 words across 8 top-level sections (12 including subsections)

## Recommendations

### 1. MOVE - OOA/OOD document-requirements subsections, out from under "Grading Structure"
**Rationale:** "Grading Structure" is about point weights (70%/35%/35%, Maman 12 vs. 13 percentages), but its two nested subsections — "OOA (Analysis) document requirements" and "OOD (Design) document requirements" — describe deliverable *content*, not weight. That's a MECE violation: a reader scanning headers for "what must the OOA contain" has to know to look inside the percentages section to find it, and it sits topically closer to the UML-Crosswalk section right after it (which maps PRD content directly onto these same required elements).
**Impact:** ~0 words (reorganization, not a length change)
**Comprehension note:** Moving these subsections to sit adjacent to (or merge with) UML-Crosswalk would let a reader who only cares about "what OOA/OOD need" find everything in one place, without wading through grading percentages first.

### 2. MERGE - Duplicate `.memlog.md` pointer (intro paragraph + footer)
**Rationale:** Line 3 ("Audit and override information is not here — that lives in `.memlog.md`") and the footer ("Audit/decision history is in `.memlog.md`") state the same fact in near-identical words. True redundancy, not reinforcement — the doc is short enough that a reader who saw it at the top doesn't need it repeated at the bottom.
**Impact:** ~15 words
**Comprehension note:** None — keep the pointer in the footer (conventional closing-metadata position) and trim it from the intro.

### 3. CONDENSE - UML-Crosswalk self-correction parenthetical
**Rationale:** "(Course guideline reconciliation flagged that the original version of this table only covered diagrams, not the other two required OOA elements — problem description and system-component description — so those are included here too.)" narrates the table's *revision history*, not something the reader needs to use the table today.
**Impact:** ~35 words
**Comprehension note:** None — this is process narration, not reference content.

### 4. QUESTION - Source Documents item 1's watermark/redistribution note vs. the doc's own audit-scope rule
**Rationale:** The addendum's intro states audit/override information doesn't belong here ("that lives in `.memlog.md`"), but the course-guidelines source entry carries what reads like exactly that category of caution note (file watermark, "do not distribute"). Worth an author call on whether this is intentional provenance metadata (kept) or audit-adjacent content that's technically misplaced per the doc's own stated scope.
**Impact:** 0 words if kept as-is; ~25 words if relocated to `.memlog.md`
**Comprehension note:** Low stakes either way — flagging for consistency, not clarity.

### 5. QUESTION - Intro paragraph's section list is incomplete
**Rationale:** Line 3 enumerates the addendum's contents as "source-document crosswalk, the grading-rubric breakdown, rejected/deferred technical-how decisions, and a UML-mapping crosswalk" — but omits two sections that exist in the document: Per-Role Action Table and Dual-Voice Worked Examples. For a random-access reference doc, an inaccurate scope list undersells what's actually jumpable-to.
**Impact:** ~+15 words if the list is completed (a cost, not a saving)
**Comprehension note:** A complete list (or a short heading-based TOC) would meaningfully help readers who are scanning to find a section, which is exactly how this document is meant to be used.

### 6. PRESERVE - Per-Role Action Table
**Rationale:** On first read this looks like it duplicates PRD §4's FR list, but it's explicitly a re-derived by-actor view that the OOA grading criteria require ("detailed description of each user type and every action each can perform") and that the PRD's feature-first organization doesn't provide directly. Not true redundancy.
**Impact:** ~248 words (cost of keeping)

## Summary
- **Total recommendations:** 6 (1 MOVE, 1 MERGE, 1 CONDENSE, 2 QUESTION, 1 PRESERVE — 0 CUT)
- **Estimated reduction:** ~50 words (~3% of original) if the MERGE and CONDENSE items are accepted; QUESTION items are net-neutral-to-additive pending author decision
- **Meets length target:** No target specified
- **Comprehension trade-offs:** None of the proposed cuts touch comprehension aids — the one PRESERVE item is flagged specifically because it might look cuttable but isn't.

---

## Pass 2 — Prose Review

| Original Text | Revised Text | Changes |
|---|---|---|
| "percentages are of Maman 12's own weight, which together = 35% of the *overall* workshop grade." | "percentages are of Maman 12's own weight; Maman 12 as a whole = 35% of the *overall* workshop grade." | Clarified ambiguous antecedent of "which together" (unclear whether it referred to the three listed percentages or to Maman 12 itself) by naming the subject explicitly. |
| "don't strip them out when extracting into the OOA, they're evidence of exactly the analytical work being graded." | "don't strip them out when extracting into the OOA — they're evidence of exactly the analytical work being graded." | Fixed comma splice (two independent clauses joined by a comma); replaced with an em dash, matching the document's existing dash usage elsewhere. |
| "Open a table & start an order (FR-4)" ... "manage menu dishes & categories (FR-22)" (Per-Role Action Table, 2 locations) | "Open a table and start an order (FR-4)" ... "manage menu dishes and categories (FR-22)" | Standardized "&" to "and" for consistency — the rest of the document spells out "and" in running prose; ampersand appears elsewhere only inside the proper noun "Ofek Rotem & Ron Zaretsky," which should stay as-is. |
| "...is not yet activated anywhere in the codebase (see `docs/architecture-backend.md`) and will need to be for any DI-based auth dependency." | "...is not yet activated anywhere in the codebase (see `docs/architecture-backend.md`) and will need to be activated for any DI-based auth dependency." | Restored the elided verb ("activated") — the ellipsis makes the second clause's verb unclear on first read. |
| "...token/cost budgeting mechanism (the PRD has already resolved the *policy* question — no v1 cap, see §4.5 feature NFR — but the *mechanism* for per-call cost attribution is architecture's to design)." | Consider: "...token/cost budgeting mechanism. The PRD has already resolved the *policy* question (no v1 cap, see §4.5 feature NFR); the *mechanism* for per-call cost attribution is architecture's to design."? | Query — the parenthetical nests two more em dashes inside an already dash-separated list item; three dash levels deep may slow parsing on first read. Splitting into two sentences would flatten it. |
| "...rejected in favor of keeping the hard-block — it's the safer default for a graded demo (no silent data-integrity workaround to explain to a reviewer) — paired instead with a new FR-7 cancel/void path, which resolves..." | Consider: "...rejected in favor of keeping the hard-block, which is the safer default for a graded demo (no silent data-integrity workaround to explain to a reviewer). That choice is paired with a new FR-7 cancel/void path, which resolves..."? | Query — "paired instead with..." sits three clauses away from its antecedent ("keeping the hard-block"), separated by a parenthetical aside, making the connection hard to track on first read. |
| "a dish 86'd mid-service" | Consider: "a dish 86'd (pulled from the menu) mid-service"? | Query — "86'd" is restaurant-industry slang for "sold out / removed from service"; a brief gloss would help readers unfamiliar with the term. Not a correctness issue — flagging as optional since the informal register looks intentional. |

**Total prose fixes:** 7 (4 definitive fixes, 3 flagged as queries for author judgment)
