---
title: Rubric Review — Architecture Spine (Restaurant Kitchen Management System)
reviewed_artifact: ../ARCHITECTURE-SPINE.md
date: 2026-07-30
method: checklist-driven read of the spine, cross-checked against docker-compose.yml, backend/container.py, backend/pyproject.toml, backend/data_models/*, docs/architecture-backend.md, frontend/package.json, frontend/src/config/config.ts, and the finalized PRD (prd.md). Corroborated where overlapping against the two existing reconciliation reviews (review-reconcile-brownfield.md, review-reconcile-prd.md) rather than re-deriving their findings from scratch.
gate_verdict: HAS-GAPS — one Critical (AD-11 implements the opposite of FR-7's confirmed rule) plus one High-severity brownfield-contradiction blocks a clean pass; fix both before epics/stories consume this spine.
---

# Rubric Review — Architecture Spine

## Checklist Item 1 — Does it fix the real divergence points for the level below, missing none?

Mostly yes for the "obvious" divergence points (layering, DI, WebSocket-vs-polling, auth scheme, migrations, concurrency policy, stock-transaction atomicity for the automatic path, price lock, availability gating, role-only auth, AI provenance/client abstraction, cancel-as-status). Confirmed gaps, all corroborating and cross-checked against `review-reconcile-prd.md`:

- **Low-stock alert / manual stock-movement atomicity is not fixed anywhere.** AD-6 binds only the automatic `OrderItem → in_preparation` path (deduction + `StockMovement(consumption)`). FR-14's "check-and-create-alert is atomic per Ingredient" and FR-15's manual `purchase`/`waste`/`adjustment` movements are a second, independently-implementable code path (Warehouse feature vs. Kitchen feature) with no equivalent invariant. Two teams building these independently could reasonably pick different transaction/dedup strategies. See Finding H-1 below.
- **AD-2's WebSocket binding list omits Low-Stock Alerts.** "Binds: kitchen board and order/table status updates" — FR-14/UJ-3 is explicitly push-style ("Noa gets an alert" while away from the screen), yet inventory isn't named. This is exactly the ambiguity AD-2 exists to close out, left open for the one other push-worthy feature in the PRD.
- **FR-21's AI-failure integrity rule ("no orphaned Recipe Suggestion row, no dangling Chat Message") has no architectural analog**, despite AD-6/AD-11 setting a clear precedent (state a write-ordering/transaction invariant) for structurally identical problems elsewhere.
- **FR-18's "one generation in flight per Cook" guard** has no stated mechanism or owner (in-memory lock vs. DB flag vs. status column) — smaller blast radius than the above since it's confined to one service, but still an unstated invariant of exactly the kind AD-6/AD-12 pattern after.
- **Two comparably-explicit PRD guards were not elevated to AD status even though sibling rules of the same shape were**: FR-3's last-active-Admin guard (parallel to AD-8's dish-availability gate) and FR-15's "never floor-cap at zero" (parallel to AD-6/AD-7, and split across the automatic vs. manual stock paths the same way the alert-atomicity gap above is).

## Checklist Item 2 — Is every AD's Rule enforceable, and does it actually prevent its own stated "Prevents"?

12 of 13 ADs pass this test cleanly — each Rule is a concrete, checkable statement (single container, single WS endpoint, single JWT dependency, migration-per-schema-change, no version column, one transaction, stored `price_at_add`, service-layer gate, role-only checks, provenance FK, terminal-status-not-delete, client-behind-interface, single routing/UI/query library) that would visibly fail code review if violated, and each does close its stated gap.

- **AD-11 is the exception, and it's a Critical defect, not a nuance.** AD-11's Rule ("cancellation inserts a compensating `StockMovement` in the same transaction") is tagged `[ADOPTED — PRD FR-7]` but implements the *opposite* of FR-7's testable consequence: *"Cancelling an `in_preparation` Order Item does **not** automatically reverse its stock deduction... the ingredients are treated as already used/opened."* The PRD's own §9 Assumptions Index records this as a deliberate, reasoned decision ("no-auto-reversal is the simpler, safer default"). AD-11's "Prevents" line ("a cancel... that leaves already-deducted stock unreturned") is internally consistent with its own Rule, which is precisely the problem — the AD is self-consistent but encodes the rejected alternative. If built as written, every mid-prep cancellation would silently re-inflate stock relative to what was actually pulled. This needs a correction pass before it reaches epics/stories: keep "terminal status, never delete the row," drop the compensating-movement clause. (Corroborates `review-reconcile-prd.md` Finding 1, independently re-derived here directly from `prd.md` FR-7 and §9.)

## Checklist Item 3 — Does anything in Deferred actually risk incompatible divergence (i.e., something should have been an AD)?

The six Deferred items themselves are correctly scoped (UX, fuller OOD doc, production deployment, rate limiting, WS handshake mechanics, exact enum literals, table delete/renumber, JWT duration) — none of those, as stated, would let two independently-built units diverge incompatibly; they're either genuinely UI/product-level, single-service internal detail, or a shared config value.

The actual problem is the inverse of what this item asks: the gaps in Item 1 (low-stock/manual-movement atomicity, AD-2's alert binding, FR-21 AI-integrity, FR-18 in-flight guard, FR-3/FR-15 guards) are **not deferred at all** — they're silently absent, which is worse than an explicit deferral, since nothing signals to the epics/stories author that a decision is still needed there.

## Checklist Item 4 — Is named tech internally consistent?

All versions in the Stack table are copied verbatim into their consuming ADs/conventions with no drift (e.g. React 19.0.0 matches AD-13's "React Router v7 owns routing" framing and `frontend/package.json`'s already-pinned `^19.0.0`; PostgreSQL 16-alpine matches both the Stack table and the Structural Seed's deployment diagram and the real `docker-compose.yml`). No internal contradictions found.

One minor style inconsistency (Low, not a correctness issue): every other backend dependency is pinned as a floor (`≥x.y.z`), but Alembic is pinned to an exact patch (`1.18.5 (async template)`). Harmless, but worth normalizing if the table gets revised — a reader could mistake the asymmetry for "this one is version-locked for a reason" when none is stated.

## Checklist Item 5 — Does it ratify rather than contradict the brownfield codebase?

Verified directly against the live tree (`backend/api/`, `backend/clients/`, `backend/data_models/`, `backend/services/`, `backend/container.py`, `backend/pyproject.toml`, `frontend/src/`, `docker-compose.yml`): the Design Paradigm, dependency-direction rule, DI/Resource pattern (AD-1), the `clients/database.py` precedent cited by AD-12, the Stack table, and the deployment diagram all match the real scaffold exactly.

- **One confirmed contradiction: `exceptions/`.** The spine's Design Paradigm, Consistency Conventions table, and Structural Seed source tree all place `exceptions/` as a top-level `backend/` sibling of `api/`/`services/`/`clients/`/`data_models/`. The real scaffold nests it at `backend/data_models/exceptions/` (confirmed via `find`), and — notably — **`docs/architecture-backend.md`, which is cited in the spine's own `sources:` frontmatter**, states this explicitly and correctly at line 51 ("`data_models/` — 6 model files + `base.py` + empty `exceptions/` subpackage"). The spine appears to have followed `project-context.md`'s imprecise phrasing over its own more-authoritative cited source. This is a High-severity finding for a spine whose entire job is to be the single source of truth implementers check first: as written, whoever implements AD-1's "exceptions/ is a leaf" will either relocate the existing package without that being a recorded decision, or add new exceptions to the correct existing location and quietly diverge from the spine's own tree/table. (Corroborates `review-reconcile-brownfield.md` Finding 1 — independently reproduced here via direct `find`/`Read` rather than taken on trust.)

## Checklist Item 6 — Is every structural dimension this altitude owns decided, deferred, or open — especially deployment/environments/infra/ops, auth, data consistency/concurrency, and AI integration?

- **Deployment & environments / infra strategy:** Decided. Single-environment Docker Compose (postgres:16-alpine + backend:8000 + frontend:3000→80), verified to match the real `docker-compose.yml` exactly; production deployment explicitly and correctly Deferred (cloud/autoscale/CI-CD/TLS out of scope, consistent with the course-defense delivery model).
- **Operations (monitoring/backups/error-tracking):** Not mentioned at all — not decided, not explicitly deferred. Given the single-environment academic-demo framing this is a reasonable implicit non-goal, but strictly it's a silent gap rather than a stated one. Low severity given the project context, but noting per the checklist's explicit instruction to check this isn't silently skipped.
- **Auth:** Fully covered — AD-3 (JWT httpOnly cookie, explicit CORS allow-list, one shared verification dependency) plus the Consistency Conventions table's auth row plus an explicitly flagged `[ASSUMPTION]` for the one still-open sub-question (8-hour session duration). This is the model for how a "flagged, not silent" deferral should look — contrast with Item 3's findings.
- **Data consistency/concurrency:** Partially covered, with a real gap. AD-5 (last-write-wins for Table/Order/OrderItem field edits) and AD-6 (atomic transaction for the automatic stock-deduction path) are both clear and correctly scoped relative to each other ("AD-6 is stricter than AD-5 and never weakened by it" is a good explicit precedence rule). But as detailed in Items 1/2/3 above, this dimension is incomplete: the manual-stock-movement path (FR-15) and the low-stock alert check (FR-14) have no atomicity/dedup invariant, and AD-11 actively states the wrong rule for cancel-time stock reversal. "Covered" is true only for the automatic-deduction slice of this dimension, not the whole of it.
- **AI integration:** Partially covered. AD-10 (provenance FK + role-level sharing) and AD-12 (client-behind-interface abstraction) are both precise and correctly scoped. Missing: FR-21's write-ordering/no-orphan-row guarantee on API failure, and FR-18's in-flight-request guard — both cross-cutting invariants of the same kind AD-6/AD-8 exist to fix elsewhere in the spine, absent here.

---

## Findings Summary (severity-ordered)

### CRITICAL

**C-1 — AD-11 implements the opposite of FR-7's confirmed rule.** AD-11's compensating-`StockMovement`-on-cancel clause contradicts FR-7's explicit, PRD-§9-confirmed "no automatic reversal" decision. Self-consistent within the AD (Rule matches its own Prevents), but wrong against the PRD it claims to encode `[ADOPTED — PRD FR-7]`. Must be corrected before downstream epics/stories are written against it, or every mid-prep cancellation will silently re-inflate stock. See Checklist Item 2.

### HIGH

**H-1 — Data-consistency/concurrency coverage is incomplete: manual stock movements (FR-15) and low-stock alerting (FR-14) have no atomicity/dedup invariant**, unlike the automatic deduction path (AD-6). AD-2 also doesn't name inventory alerts in its WebSocket "Binds" list, leaving push-vs-poll ambiguous for FR-14 specifically. Two independently-built features (Kitchen's automatic path vs. Warehouse's manual path) could diverge on transaction boundaries and on whether/how alert-dedup is enforced. See Checklist Items 1 and 6.

**H-2 — `exceptions/` folder location contradicts the brownfield scaffold and the spine's own cited source** (`docs/architecture-backend.md`, listed in `sources:`). Spine places it top-level (`backend/exceptions/`); the real scaffold and the cited doc place it at `backend/data_models/exceptions/`. Low blast radius (one empty package) but a clear, confirmed defect in a document whose entire purpose is to be trusted at face value. See Checklist Item 5.

### MEDIUM — plus 2 more in the file (FR-21 AI-failure orphaned-record integrity has no AD analog; FR-18's "one generation in flight per Cook" guard has no stated mechanism/owner)

### LOW — plus 4 more in the file (FR-3 last-Admin guard and FR-15 floor-at-zero rule not elevated to AD despite sibling rules of the same shape getting one; AD-6's transaction boundary doesn't state the concurrency-safety mechanism NFR-3 actually needs, e.g. row lock / conditional update; WebSocket event payload shape isn't fixed beyond the naming convention; Operations/monitoring/backups dimension is silently unaddressed rather than explicitly deferred; Alembic is pinned to an exact patch version while every sibling dependency uses a floor, a stylistic asymmetry only)
