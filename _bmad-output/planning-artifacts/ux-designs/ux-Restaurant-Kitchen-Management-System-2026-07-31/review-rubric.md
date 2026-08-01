# Spine Pair Review, Restaurant Kitchen Management System

## Overall verdict

The spine pair is well-built and mostly source-extractable cleanly: five UJs map to five Key Flows with correct protagonists, all 13 IA surfaces get cold-load/empty/error coverage, and FR/AD citations throughout are accurate rather than decorative. Two critical gaps keep it from a clean pass: Table status (available/occupied/reserved) is referenced via `{components.status-badge}` in EXPERIENCE.md but has no corresponding entry in DESIGN.md's status-badge token, and FR-8 (close a table, the total-amount computation) has zero coverage anywhere in either file despite being a named Waiter action in the addendum's per-role table and part of PRD Success Metric SM-1. A citation-integrity issue also surfaced: both files cite "Drift" as an external reference product, but Drift is the fictional example product from this skill's own asset files, not a real product.

## 1. Flow coverage, strong

Checked: PRD section 2.3 lists UJ-1 through UJ-5 (Maya, Amir, Noa, David, Amir again), no other named journeys or requirements to cover. EXPERIENCE.md's Key Flows section has Flow 1 through Flow 5, one per UJ, each with a named protagonist matching the PRD verbatim, numbered steps, a bolded **Climax** beat, and a **Failure path** or **Edge case** (matching the PRD's own edge-case framing for UJ-2/UJ-3) where the source UJ names one.

### Findings
- **low** Flow 2 and Flow 3 label their failure beat "Edge case" rather than "Failure path," matching the PRD's own wording for those two UJs but diverging from Flow 1/4/5's "Failure path" label (EXPERIENCE.md lines 149, 162, 176 vs 187, 199). *Fix:* none needed, this is intentional verbatim inheritance from the PRD's own terminology, just note it as a naming asymmetry a downstream reader should expect.

## 2. Token completeness, adequate

Checked every token in DESIGN.md's YAML frontmatter (colors, typography, rounded, spacing, components) and every `{path.to.token}` reference in both files' prose. Nearly all resolve cleanly; the accent color pair has hex values and measured contrast ratios for both light and dark mode.

### Findings
- **critical** EXPERIENCE.md's Component Patterns table states the Table tile's status (available/occupied/reserved) "shown via `{components.status-badge}`," but DESIGN.md's `status-badge` frontmatter object only defines children for `pending`, `in_preparation`, `ready`, `served`, `closed`, `cancelled`, i.e. OrderItem/Order statuses only. No color, icon, or hex exists anywhere in DESIGN.md for `available`, `occupied`, or `reserved` (grep confirms "reserved" and Table-status "available" do not appear in DESIGN.md at all). This is the Tables grid, Maya's home surface, and it has no defined visual treatment for its primary status dimension. (DESIGN.md components.status-badge, lines 33-51; EXPERIENCE.md Component Patterns, line 70). *Fix:* add `available`/`occupied`/`reserved` entries to `status-badge` (or a separate `table-status-badge` token) with color/icon per state, matching the traffic-light discipline already used for Order/OrderItem status.
- **medium** DESIGN.md gives measured contrast ratios only for `{colors.accent}`/`{colors.accent-dark}` (5.76:1 and 9.05:1). The traffic-light status colors (`status-badge.pending/in_preparation/ready/served/closed/cancelled`), explicitly called out as carrying "real operational weight (colorblind legibility at the kitchen display)," are stated only as inherited MUI token names (`warning.main`, `success.main`, etc.) with no contrast number given, even though this is named as the one place the system invents real visual vocabulary (DESIGN.md Brand & Style, line 98; Colors, lines 108-119). *Fix:* state measured or MUI-documented contrast ratios for at least the Kitchen Display's dark-background rendering of these tokens, since that is the specific surface named as the hard accessibility requirement.

## 3. Component coverage, adequate

Extracted every component name from DESIGN.md.Components and EXPERIENCE.md.Component Patterns and cross-checked both directions.

### Findings
- **medium** `status-badge` is DESIGN.md's first and most-referenced component ("the shared atom behind every status rendering in the system") but has no corresponding row in EXPERIENCE.md's Component Patterns table. Its behavior is only inferable secondhand from the Order Item row, Kitchen Display card, and Table tile rows that reference it (DESIGN.md Components, line 143; EXPERIENCE.md Component Patterns, lines 68-78). *Fix:* add a Status badge row to Component Patterns stating the behavioral rule directly (e.g., updates automatically on status transition, never manually toggled, always paired with icon + label per the Accessibility Floor).
- **low** `button-primary` is a defined frontmatter token and is referenced from `recipe-suggestion-card.confirm-action`, but has no standalone bullet in DESIGN.md's prose Components section; the section's opening line ("`Button`... used as MUI ships it") reads as if Button has no delta at all, when in fact its primary-color slot is the accent override described in Colors. (DESIGN.md Components, lines 139-141; Colors, line 106). *Fix:* add a one-line Button bullet noting the primary variant resolves through the overridden theme `primary` slot, to remove the apparent tension with the Colors section.

## 4. State coverage, strong

Walked all 13 IA surfaces against the State Patterns table. Every surface has at minimum cold-load and error coverage (both stated as blanket rows covering "All 13 surfaces"), and each surface's domain-specific states (empty, generating, rejected, reconnecting) are present where the PRD's consequences call for them.

### Findings
- **low** The "Reconnecting" row is scoped to "Kitchen Display (and globally)" in a single table row (EXPERIENCE.md State Patterns, line 94). The parenthetical is the only signal that this state applies to all 13 surfaces, not just Kitchen Display; a downstream reader skimming the table could reasonably read it as Kitchen-Display-only. *Fix:* either add "(all 13 surfaces)" explicitly or give it its own row alongside the Cold load / Error blanket rows.
- **low** Ingredient detail's movement-logging action (record a purchase/waste/adjustment) has a listed empty state for its history list but no explicit row for a submission-validation state (e.g. a negative quantity or malformed input), relying entirely on the generic "Error (generic)" blanket row. Given FR-15/NFR-4's emphasis on audit correctness, this is a candidate for its own line, though not a hard gap given the blanket row's coverage. *Fix:* optional, add a named "Rejected (invalid movement)" row if stories need explicit inline-error microcopy for this action.

## 5. Visual reference coverage, strong

Confirmed: `mockups/` and `wireframes/` folders do not exist in the workspace; `imports/` and `.working/` exist but are empty. This matches the expected state for this run (no key-screen mocks rendered yet), and both spine files avoid making promises to composition references that don't exist (unlike the shape examples, which point to `mockups/*.html` files that presumably do exist in their illustrative context). No dangling references to check.

## 6. Bloat and overspecification, strong

Checked for pixel specs duplicating tokens, verbatim source restatement, prose where a table would serve better, and decorative narrative untied to a decision.

### Findings
- **low** A handful of Key Flow sentences carry vivid narrative color beyond flat behavioral description (e.g. "while the food is still on the pan," "without Noa having to walk the line to check"). This matches the register of the reference example files' own Key Flows sections (Drift's "she picks up her coffee and starts writing"), so it is within the established shape, but EXPERIENCE.md's own stated discipline ("EXPERIENCE.md prose should not carry editorial voice") is written for the rest of the file, not clearly exempting Key Flows. *Fix:* none required, flagged for awareness only since it sits right at the boundary the shape allows.

## 7. Inheritance discipline, adequate

Checked frontmatter `sources` resolution, verbatim UJ/protagonist naming, glossary consistency, component-name consistency, EXPERIENCE-to-DESIGN token resolution, and contradiction-checking against the 16 architecture ADs.

### Findings
- **medium** Both files cite "Drift" as if it were a real external reference product: DESIGN.md's Brand & Style section invokes "the same discipline Drift-style shadcn products use," and EXPERIENCE.md's Interaction Primitives section rejects "a Drift-style vim-nav layer" as out of scope. Drift is not a real product, it is the fictional illustrative example used in this skill's own asset files (`design-example-shadcn.md` / `experience-example-shadcn.md`), which this review was pointed to as shape references. Citing it as market inspiration is citing the teaching scaffold as if it were prior art. (DESIGN.md line 98; EXPERIENCE.md line 121). *Fix:* replace with a real reference product if inspiration-citation is intended, or rephrase both sentences to state the principle directly without a product name (e.g. "the same discipline of inheriting a component library's defaults wholesale," "a vim-style keyboard-nav layer is out of scope for v1").
- **high** FR-8 (close a table, which computes `total_amount` from non-cancelled Order Items' stored `price_at_add` and returns the table to `available`) is named explicitly in the addendum's Per-Role Action Table as a Waiter action and is part of PRD Success Metric SM-1's demo-critical vertical slice. It appears nowhere in EXPERIENCE.md: not in the Table/Order detail surface's Purpose column (which lists "Open table, add dishes... edit/cancel pending items, mark served" but not close), not in any Key Flow (Flow 1 ends at "Maya moves to her next table" without reaching a close), not in Component Patterns, and not in State Patterns beyond the `closed` status-badge color definition in DESIGN.md. No price or total_amount display is specified anywhere in either file (grep confirms "total"/"price" do not appear in EXPERIENCE.md outside the Menu Management IA row and Flow 4's dish-price edit). (EXPERIENCE.md IA, line 35; Key Flows, Flow 1). *Fix:* add a beat to Flow 1 (or a new short flow) covering close-table: where the close action lives on Table/Order detail, what total is shown, and confirm this ties to the `closed` status badge already defined in DESIGN.md.
- No other issues found: `sources` frontmatter in both files resolves to the three files this review also read; protagonist names (Maya, Amir, Noa, David) are verbatim from PRD §2.3; Order/OrderItem/Table glossary terms and status vocabularies match the PRD Glossary exactly; FR and AD citations spot-checked throughout (FR-6/AD-9, AD-6/FR-10, AD-11, AD-14, AD-15, AD-16, FR-14, FR-19) are all accurate, not decorative.

## 8. Shape fit, strong

Checked DESIGN.md section order against the design-md-spec's canonical order, and EXPERIENCE.md's required-default sections against the shape examples.

### Findings
- DESIGN.md sections appear in exact canonical order: Brand & Style, Colors, Typography, Layout & Spacing, Elevation & Depth, Shapes, Components, Do's and Don'ts. No misordering, no unlisted sections.
- EXPERIENCE.md carries all required defaults in order: Foundation, Information Architecture, Voice and Tone, Component Patterns, State Patterns, Interaction Primitives, Accessibility Floor, Key Flows.
- **Responsive & Platform omission is defensible and explicitly justified**: Foundation states directly "there is no separate Responsive & Platform section in this spine because there are no breakpoints to define," consistent with the PRD's desktop-only, single-layout non-goal.
- **medium** **Inspiration & Anti-patterns omission is only partly defensible.** The stated premise for omitting it would be "no named reference products," but the file does informally invoke a named product twice (see the Drift finding under section 7), and the file does contain real rejected-alternative content that the shape examples would normally home under this section: DESIGN.md's rejection of "fire, wood, harvest tones... in favor of a cool blue/teal" (Colors, line 121), and EXPERIENCE.md's rejection of a drag-based Kitchen Display ticket rail and of custom keyboard shortcuts (Interaction Primitives, lines 120-121). These are scattered inline rather than gathered where a downstream reader would expect to find "what we rejected and why" in one place. *Fix:* either add a short Inspiration & Anti-patterns section consolidating these (and dropping the Drift references per the section 7 fix), or add one line to Foundation explicitly stating why it's omitted, mirroring the Responsive & Platform section's self-justifying sentence.

## Mechanical notes

- Frontmatter is complete on both files: `name`, `status`, `sources`, `updated` on EXPERIENCE.md (matches the shape examples' minimal frontmatter, no `description` expected there); `name`, `description`, `status`, `sources`, `colors`, `typography`, `rounded`, `spacing`, `components`, `updated` on DESIGN.md.
- No Mermaid diagrams in either file, nothing to validate there.
- No broken cross-references found: `DESIGN.md` and `EXPERIENCE.md` refer to each other by bare filename consistently (matching the paired-file convention in the shape examples), and every `{components.x}` / `{colors.x}` / `{typography.x}` / `{rounded.x}` / `{spacing.x}` reference checked resolves to a real frontmatter path except the Table-status gap noted in section 2.
- Component naming is consistent between files with one exception already noted (status-badge has no EXPERIENCE.md row) and one cosmetic split (DESIGN.md's single "Nav badges" bullet covers what EXPERIENCE.md splits into two Component Patterns rows, "Nav badge, Alerts" and "Nav badge / counter, tables needing attention"; both resolve to the correct distinct tokens, `nav-badge-alerts` and `nav-badge-attention`, so this is a non-issue, just noted for completeness).
