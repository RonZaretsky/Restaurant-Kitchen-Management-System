# Reconciliation: PRD (+ addendum) vs. Course Guidelines

This document checks whether `prd.md` and `addendum.md`, as written, give their authors what
they need to satisfy the *structural* requirements of `source-course-guidelines.md` (Open
University OOP Workshop, Final Project chapter, pp. 64–66) — specifically the OOA (Analysis)
document's required content and prohibitions, what OOD will need downstream, the "client vs.
analyst" dual-voice requirement, and general project requirements (GUI, DB, OOP/patterns/layers,
future-change consideration). This is not a general PRD quality review.

Overall the PRD/addendum pairing is unusually well-aligned with the guidelines — the addendum
explicitly quotes the four required OOA content elements, the OOD requirement list, and provides
a UML crosswalk. The gaps below are the places where the mapping is incomplete, or where the
PRD's own "this can be lifted almost directly into the OOA" claim (§0) doesn't fully hold up.

## Gaps

- **Implementation/schema leakage inside the sections the PRD claims are OOA-ready.** §0 states
  §2–§5 are "written capability-first with zero design/implementation detail so they can be
  lifted almost directly into the client-facing OOA." The guidelines are explicit that the OOA
  "must not contain any design or implementation details (classes, inheritance, etc.)" and must
  be readable by "a client who understands nothing about programming." In practice several FR
  "Consequences" blocks and one User Journey edge case name actual DB fields, a specific ORM
  model, and a specific vendor API:
  - FR-1: "matching the existing `password_hash` field"
  - FR-15: "matches the existing `AIRecipeSuggestion` schema"
  - FR-11: "the resulting Stock Movement's `reference_id` links back to..."
  - UJ-4 edge case: "...in-progress order items assigned to them (`cook_id`)"
  - NFR-4: "already implied by the existing schema's audit-log design"
  - §1, §4.5, FR-15/17/18, Constraints: repeated explicit naming of "OpenAI API" as the AI
    provider, and §5/Platform naming "React/Vite" as the frontend stack
  A non-programmer client, or a grader checking OOA purity, would flag every one of these as
  implementation detail. If §2–§5 are extracted "almost directly" as §0 proposes, these need to
  be stripped or paraphrased first (e.g. "the system does not store passwords in readable form"
  instead of naming the field; "an AI service" instead of "OpenAI API").

- **The addendum's UML-crosswalk covers only the diagram requirements, not the two textual OOA
  requirements.** The addendum correctly quotes all four required OOA elements (problem
  description; system-components description; detailed user-type/action breakdown; Use Case +
  Activity diagrams), but its "UML-Crosswalk" table maps PRD content to only the diagram types
  (Use Case, Activity, Class, Sequence). It never states where in the PRD the "problem
  description" or "system components description" live. In practice they exist (§1 Vision for
  the former; §4's six feature-group headers for the latter) but this isn't made explicit
  anywhere, so whoever drafts the OOA has to infer it rather than being pointed at it.

- **No consolidated per-actor action list, despite the guideline asking for one.** The guideline
  wants "a detailed description of each user type, and the actions each is able to perform."
  The PRD's information exists (role tags on section headers in §4.2–§4.4/4.6, "A Cook can..."
  phrasing throughout FRs) but is organized by *feature*, not by *actor* — there is no single
  place listing, e.g., "Waiter: FR-4, FR-5, FR-6, FR-7" end to end. Building that view requires
  re-deriving it from FR text. This is a real but minor gap since the underlying content is all
  present; it's a reorganization task the addendum doesn't flag as needed.

- **The "client-stated vs. analyst-inferred requirements" dual-voice is real but not clearly
  labeled as such.** The guideline requires representing *both* what the client explicitly asked
  for and what the analyst inferred as necessary without the client stating it. The addendum
  asserts the PRD's `[ASSUMPTION: ...]` tags and §8 Open Questions are "the direct mechanism"
  for this. On inspection, most `[ASSUMPTION]` tags mark *unconfirmed policy decisions*
  (session-expiry duration, OpenAI cost cap, hard-block vs. override on table close) rather than
  *analyst-added requirements the client never stated*. Meanwhile, genuine examples of the
  latter — e.g. the UJ-3 rule that a shortage must produce exactly one active alert, not a flood;
  the UJ-4 rule that deactivating a user must not orphan their historical order items; NFR-3's
  atomicity requirement — are written as ordinary requirements/edge cases with no tag or label
  marking them as "this wasn't asked for, the analyst added it." The substance the guideline
  wants is present, but nothing distinguishes the two voices, so a grader looking specifically
  for that dual representation may not find it obviously called out.

- **A non-system actor is mixed into the user-type list.** §2.1 Jobs To Be Done lists "Ofek &
  Ron, as builders" alongside the four real system roles (Waiter, Cook, Warehouse Manager,
  Admin). That's reasonable in a PRD (it's a legitimate JTBD for the document's own authors), but
  if §2.1 is used as a source list for the OOA's required "description of user types," this fifth
  entry needs to be filtered out — the guidelines' user-type section is about actors of the
  *system*, not the students building it.
