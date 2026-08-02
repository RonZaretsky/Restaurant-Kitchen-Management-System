# PRD Editorial Polish — prd.md (2026-07-24)

Two independent passes per `bmad-editorial-review-structure` and `bmad-editorial-review-prose`. Recommendations only — nothing in `prd.md` has been changed. Content (including all `[ASSUMPTION: ...]` tags, the Assumptions Index, and the Open Questions section) was treated as sacrosanct per both skills' governing principle and per this task's explicit brief.

---

# Pass 1 — Structural Review

## Document Summary
- **Purpose:** Serve as the primary requirements reference for Ofek & Ron and for downstream BMad workflows (`bmad-ux`, `bmad-architecture`, `bmad-create-epics-and-stories`), while doubling as source material for the course-required OOA document.
- **Audience:** Ofek & Ron (builders/analysts), downstream BMad skills, and indirectly the course instructor (via the OOA/OOD documents this PRD feeds).
- **Reader type:** humans (default — not specified by caller)
- **Structure model:** Strategic/Context (Pyramid) as the primary model, with the caveat (per task brief) that §4 Features functions as a Reference/Database section within it — readers jump to a specific FR rather than reading linearly. Both models were weighed throughout.
- **Current length:** 7,224 words across 13 top-level sections (§0–§9 plus three unnumbered closing sections), with §4 further subdivided into 6 feature groups and 24 individually-numbered FRs.

## Recommendations

### 1. MOVE - Glossary (§3) relative to Key User Journeys (§2.3)
**Rationale:** The document states its own policy that "every FR, UJ, and feature description uses [Glossary] terms verbatim" (§0), yet §2.3's five journeys (UJ-1–UJ-5) make heavy use of formally-defined vocabulary — Table/Order statuses, Order Item, Stock Movement — a full section before the Glossary that defines them. A linear first-time reader hits the jargon before the definitions. Relocating §3 Glossary to precede §2.3 (e.g., directly after §1 Vision, or as the first subsection of §2) fixes the dependency order without touching content.
**Impact:** ~0 words (reorder only)
**Comprehension note:** Improves first-read comprehension for linear readers; no cost to readers who already jump straight to the Glossary as a reference.

### 2. MOVE - Cross-Cutting NFRs section relative to §4 Features
**Rationale:** FR-6 and FR-9 (early in §4) explicitly cite "the bound defined in NFR-1" by name, but NFR-1 isn't actually defined until the "Cross-Cutting NFRs" section near the very end of the document — roughly 2,000+ words later. This is a forward reference / missing-scaffolding gap (Step 4) for anyone reading top-to-bottom. Relocating "Cross-Cutting NFRs" to directly before §4 Features (e.g., right after the relocated Glossary) means NFR-1 is defined before it's first cited.
**Impact:** ~0 words (reorder only)
**Comprehension note:** Meaningful for linear readers; negligible cost to reference-style readers who navigate by search/section number regardless.

### 3. MOVE - Italic aside in §2.1 Jobs To Be Done
**Rationale:** The italic paragraph explaining that "the four roles above... are the system's actual user types" and that the builders' own JTBD is a meta-entry currently sits *between* the 4th bullet (Admin) and the 5th bullet (Ofek & Ron), interrupting a five-item bulleted list with a full paragraph. Moving it to after the 5th (final) bullet lets the list read as one continuous list, with the clarifying note appended as a trailing caveat instead of a mid-list interruption. While there, the 5th bullet's parenthetical "(meta, non-system-user)" can drop — it's now redundant with the aside that immediately precedes it.
**Impact:** ~4 words (dropping the redundant parenthetical); reordering itself is free.
**Comprehension note:** Restores list scannability; no information is lost.

### 4. MERGE - Platform section into Constraints and Guardrails
**Rationale:** "Platform" is 54 words — too short to justify its own top-level heading — and is topically continuous with the other system-wide-quality sections it already sits beside (Cross-Cutting NFRs, Constraints and Guardrails). Folding it in as a final subsection (or bullet) of Constraints and Guardrails reduces section-list clutter without losing content.
**Impact:** ~0 words saved (heading overhead only); mainly a ToC/scannability cleanup.
**Comprehension note:** None — same content, one fewer top-level heading to scan past.

### 5. QUESTION - Inconsistent top-level section numbering
**Rationale:** §0 through §9 are numbered, but "Cross-Cutting NFRs," "Constraints and Guardrails," and "Platform" are not. This inconsistency already produced a real defect: §4.5's Feature-specific NFRs text cites "the Constraints & Guardrails Cost note in §7," but §7 is Success Metrics — Constraints and Guardrails has no number to correctly cite (see Pass 2, item 4). Recommend numbering all top-level sections consistently (e.g., continuing §10, §11, §12) so future cross-references stay valid.
**Impact:** ~0 words; prevents recurrence of broken references.
**Comprehension note:** N/A — pure consistency fix, author decision on final numbering scheme.

### 6. QUESTION - Consider a brief top-of-document status banner
**Rationale:** Under the Pyramid model, "conclusion/status/recommendation starts the document." §0 Document Purpose partially serves this role (explains what the document is and how it's used) but doesn't state the document's current state — draft, pending review, counts of open items — which would orient a time-pressured reviewer (relevant given this PRD's mid-Reviewer-Gate status). This is optional and low-priority since §0 already does real orientation work; flagging for author decision rather than recommending outright.
**Impact:** +20–30 words if added (cost)
**Comprehension note:** Would help reviewers scanning the doc for state; not adding it is also defensible since §0 exists.

### 7. PRESERVE - Assumptions Index (§9)
**Rationale:** §9 restates information already present inline via `[ASSUMPTION: ...]` tags scattered through §1–§4, which could read as true redundancy by the letter of the structural principles. It is preserved explicitly because it serves a distinct use case — a single scannable audit list for reviewer-gate triage — that in-context tags don't serve, and per this task's brief it is deliberate and load-bearing for the grading rubric.
**Impact:** ~564 words retained (would be the cost of removing it)
**Comprehension note:** Keeping it aids reviewers; a "might seem cuttable" flag, not a genuine cut candidate.

### 8. PRESERVE - Key User Journeys (§2.3)
**Rationale:** At ~1,108 words for five journeys, this is the single densest subsection in the front half of the document — a plausible CONDENSE target under a pure brevity mandate. It is preserved because it is explicitly the source material for the required Use Case/Activity diagrams (§0) and because the "Edge case" beat in each journey carries requirement-level detail (e.g., UJ-3's one-alert-per-shortage rule) that downstream FRs depend on.
**Impact:** ~1,108 words retained
**Comprehension note:** Length is justified by its dual role as narrative and requirements source; not a comprehension burden given the document's reference-jump usage pattern.

### 9. PRESERVE - Per-FR "Consequences (testable)" sub-bullets (§4)
**Rationale:** These sub-bullets roughly double the length of each FR entry and could look like elaboration-for-its-own-sake. They're preserved because they are the testable acceptance criteria that make each FR unambiguous for `bmad-architecture` and `bmad-create-epics-and-stories` — cutting them would reintroduce the ambiguity this PRD exists to remove.
**Impact:** Majority of §4's 2,850 words retained
**Comprehension note:** Verbose by design; consistent with the document's stated purpose as an engineering-facing spec, not a marketing brief.

## Summary
- **Total recommendations:** 9 (3 MOVE, 1 MERGE, 2 QUESTION, 3 PRESERVE; 0 CUT, 0 CONDENSE)
- **Estimated reduction:** ~4 words (0.06% of original) — this pass is almost entirely reordering/consistency, not trimming, because the document's issues are sequencing (Glossary/NFR forward references) and formatting (inconsistent numbering), not bloat.
- **Meets length target:** No target specified
- **Comprehension trade-offs:** None of the MOVE/MERGE recommendations cost any comprehension aid. The two QUESTION items are pure author-decision points. All three PRESERVE calls exist because the document's length in those spots is load-bearing for its dual role as engineering spec and OOA source material, per the task brief — not because brevity was deprioritized elsewhere.

---

# Pass 2 — Prose Review

Reviewed all prose sections; skipped frontmatter, headings, and structural markup (FR numbering, bullet/table scaffolding). `[ASSUMPTION: ...]`, `[NOTE FOR PM: ...]` tags, and their content were left untouched per CONTENT IS SACROSANCT — only genuine communication issues below, no preference-driven rewrites.

| Original Text | Revised Text | Changes |
|---|---|---|
| "...and giving the kitchen a conversational assistant to consult on, version, and **refine** recipes." (§1 Vision) | "...and giving the kitchen a conversational assistant to consult on, version, and **improve** recipes." | Terminology consistency: the Glossary's Smart Assistant entry and FR-20's title both say "consult on, version, and **improve**." The document commits itself (§0) to using Glossary terms verbatim; "refine" is a stray synonym for the same concept. |
| "- **Warehouse manager** — needs to trust that stock levels reflect reality..." (§2.1 Jobs To Be Done) | "- **Warehouse Manager** — needs to trust that stock levels reflect reality..." | Capitalization consistency: the three sibling JTBD bullets in the same list — Waiter, Cook, Admin — fully capitalize the role name; "Warehouse manager" breaks that parallel pattern within one list. |
| "...Automatic stock deduction (FR-13) and Order/**Order-Item** status transitions (FR-10, FR-12) must be atomic..." (Cross-Cutting NFRs, NFR-3) | "...Automatic stock deduction (FR-13) and Order/**Order Item** status transitions (FR-10, FR-12) must be atomic..." | Removed a stray hyphen. The Glossary defines the term as "Order Item" (no hyphen), and it's written that way everywhere else in the document, including the very next NFR (NFR-6: "Table/Order/Order Item"). |
| "...see the Constraints & Guardrails Cost note in **§7** for the rationale." (§4.5, Feature-specific NFRs) | "...see the Constraints and Guardrails section's Cost note below for the rationale." | Fixed an incorrect cross-reference: §7 is Success Metrics, not Constraints and Guardrails (which is an unnumbered section near the end of the document — see Pass 1, item 5, for the underlying numbering-consistency issue). |
| "...computed at read time **/** on each Stock Movement that can decrease stock, rather than persisted..." (§3 Glossary, Low-Stock Alert) | "Consider: 'computed at read time, **or** on each Stock Movement that can decrease stock,'?" | Query — the "/" shorthand is ambiguous between "and/or" and strictly "or." Flagged as a query rather than a definitive change since the intended logic (read-time computation OR movement-triggered computation, not both required) should be confirmed by the author. |
| "...but it is not a drop-in substitute for it: §2–§5 here are written capability-first and cover the OOA's required content (problem description in §1, system components in §4's feature groupings, user types and their actions — see the per-Role action table in `addendum.md` — and the flows behind the required Use Case/Activity diagrams in §2.3 and §4)." (§0 Document Purpose) | Consider: splitting into two sentences — one stating what §2–§5 cover, a second mapping each OOA requirement to its location — given three nested levels of punctuation (colon, em-dash, parentheses) in the current single sentence? | Query — flagged rather than rewritten, since a definitive split risks subtly changing which claims are scoped together; author should confirm the intended grouping before it's split. |

**No issues found in:** §1 Vision (remainder), §2.2 Non-Users, §2.3 Key User Journeys (UJ-1 through UJ-5 narrative text), the majority of §3 Glossary, §4's FR statements and Consequences bullets, §5 Non-Goals, §6 MVP Scope, §7 Success Metrics, §8 Open Questions, §9 Assumptions Index, remaining Cross-Cutting NFRs, Constraints and Guardrails, and Platform. These sections are dense by design (per the task brief) but internally clear, grammatically sound, and consistent in terminology.
