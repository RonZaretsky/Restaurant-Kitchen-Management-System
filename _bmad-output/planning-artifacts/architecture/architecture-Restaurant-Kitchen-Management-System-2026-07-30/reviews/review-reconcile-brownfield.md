---
title: Review — Reconcile Architecture Spine Against Brownfield Reality
reviewed_artifact: ../ARCHITECTURE-SPINE.md
date: 2026-07-30
method: manual cross-check of spine vs. docs/architecture-*.md, docs/data-models-backend.md, project-context.md, and live code (pyproject.toml, container.py, clients/database.py, package.json, actual folder tree, docker-compose.yml, .memlog.md)
---

# Review — Reconcile Architecture Spine Against Brownfield Reality

## Overall Verdict

**Mostly sound, one confirmed real divergence.** The spine's Design Paradigm, most ADs, the Stack table, and the Structural Seed genuinely ratify what's in the code today rather than inventing a new shape. The SQLAlchemy/asyncpg fact was correctly handled (spine reflects the real, already-installed state; `project-context.md` is the stale document, not the spine). The one confirmed bug is a folder-location mismatch for `exceptions/`, traceable to the spine trusting `project-context.md`'s imprecise wording over the actual scaffold and over `architecture-backend.md`'s more accurate description.

## Findings

### 1. [CONFIRMED BUG] `exceptions/` is nested under `data_models/` in the real scaffold, not top-level — the spine says top-level

**Actual code** (`backend/` tree, verified via `ls`):
```
backend/
  api/
  clients/
  data_models/
    exceptions/      <- empty subpackage, only __init__.py, dated same as rest of scaffold (2026-07-24)
    __init__.py, base.py, user.py, menu.py, recipe.py, order.py, inventory.py, ai.py
  services/
```
There is **no** `backend/exceptions/` directory at all — `ls backend/` confirms only `api/`, `clients/`, `data_models/`, `services/` at the top level.

**`docs/architecture-backend.md` (accurate)**, line 51:
> `data_models/` — 6 model files + `base.py` + empty `exceptions/` subpackage (designated location for custom exceptions...)

This correctly places it *inside* `data_models/`.

**`_bmad-output/project-context.md` (imprecise)**, line 35:
> Custom exceptions belong in `backend/exceptions/` (currently empty, but it's the designated location)

This states it as top-level — inconsistent with the actual nested location and with `architecture-backend.md`'s own description.

**The spine followed the imprecise source, not the code or the more accurate doc:**
- `ARCHITECTURE-SPINE.md` Design Paradigm: "`exceptions/` is a cross-cutting leaf usable from any layer" — diagrammed as an independent top-level box.
- Consistency Conventions table: "custom exception types live in `backend/exceptions/`".
- Structural Seed minimal source tree: lists `exceptions/` as a sibling of `api/`, `services/`, `clients/`, `data_models/`.
- `.memlog.md` line 22 makes this explicit and labels it `[RATIFIED, brownfield]`: "Backend layered folders (api/, clients/, data_models/, exceptions/, services/) are the only top-level organizing unit" — this is asserted as already-true brownfield fact, but it isn't; the real scaffold nests `exceptions/` one level deeper.

**Impact:** minor in isolation (one empty package, trivial to `git mv`), but it's exactly the kind of thing this reconciliation pass exists to catch — a spine claim labeled "ratified from brownfield" that doesn't match the brownfield. Whoever implements AD-1 will either (a) silently relocate `data_models/exceptions/` → `backend/exceptions/` without that being a stated decision anywhere, or (b) put new exception types in the existing nested location and quietly diverge from the spine's own tree/table. Worth an explicit one-line decision (relocate vs. amend the spine to `data_models/exceptions/`) rather than leaving it implicit.

### 2. [CONFIRMED CORRECT] SQLAlchemy/asyncpg discrepancy already handled correctly by the spine

Per the task's known-stale-fact check: `project-context.md` line 22 claims "Planned but NOT yet installed: PostgreSQL + SQLAlchemy... do not assume SQLAlchemy is available." This is stale. Actual `backend/pyproject.toml` lists `sqlalchemy[asyncio]>=2.0.0` and `asyncpg>=0.29.0` as real dependencies, and `backend/container.py` already wires a working async engine/session/`Base.metadata.create_all` via `providers.Resource` (`_init_database`). The spine's Stack table lists both as `[ADOPTED]`-tier entries with exact version floors matching `pyproject.toml` verbatim, and AD-4/AD-12 correctly describe the current `create_all`-based state as the thing Alembic will replace, not as already replaced. `docs/architecture-backend.md` and `docs/data-models-backend.md` (both 2026-07-24) already had this right too — only `project-context.md` is stale here. The spine correctly sided with the code, not the stale doc.

### 3. [NOT A BUG, WORTH NAMING] Frontend Stack entries (React Router, MUI, TanStack Query) are net-new decisions, correctly not yet reflected in `package.json`

`frontend/package.json` today has only `react`/`react-dom` plus build tooling — no router, UI library, or query library installed. The spine's AD-13 and Stack table pin React Router 7.8.0, MUI (current major), and TanStack Query v5. This is **not** a ratify-vs-invent violation: both `docs/architecture-frontend.md` and `project-context.md` explicitly flag routing/state/UI-library as unchosen ("the first PR that needs one of these should raise it as an explicit decision") — the spine is that decision, made once, which is the correct place for it to happen (frontend is explicitly scoped "near-greenfield" in the spine's own frontmatter). No action needed; noting only so the reconciliation record shows this was checked, not missed.

### 4. [LOW CONFIDENCE, INFORMATIONAL] Two pinned versions for not-yet-installed backend deps are precise enough to be worth a second look before implementation

Stack table pins `openai (Python SDK) 2.48.0` and `Alembic 1.18.5 (async template)`. Neither package is in `backend/pyproject.toml` yet (both are net-new, same category as Finding 3 — this is expected). `.memlog.md` lines 31–32 mark both "verified 2026-07-30" via what was presumably a live lookup at spine-authoring time. I have no way to independently verify current PyPI state from here, and my own knowledge cutoff predates 2026-07-30, so I can't confirm or refute the specific patch versions — flagging only so that whoever runs `uv add` first checks these resolve, rather than assuming the pin is load-bearing. Not a reconciliation failure since both are appropriately net-new (matching Finding 3's category), just a "verify at implementation time" note.

### 5. Everything else checked out clean

- Backend folder structure (`api/`, `clients/`, `data_models/`, `services/`) — spine's Design Paradigm, dependency-direction rule, and Structural Seed source tree all match the real tree exactly (aside from Finding 1).
- `container.py`'s `DeclarativeContainer` + `providers.Resource` pattern (logging, database) — spine's AD-1 and AD-12 describe this pattern accurately and extend it consistently (new OpenAI client, WS registry) rather than contradicting it.
- `clients/database.py`'s `SessionDep`/`get_session()` pattern — consistent with AD-12's "matching the existing `clients/database.py` pattern" framing.
- `docker-compose.yml`'s `postgres:16-alpine` — matches the Stack table and Structural Seed's deployment diagram exactly.
- `api/router.py`'s single flat `APIRouter` with only `/health` — spine correctly frames the "one sub-router per domain" convention as forward-looking ("Convention going forward"), not a claim that it already exists.
- `docs/data-models-backend.md`'s cross-check note ("no discrepancies were found... in sync as of 2026-07-24") — nothing in this pass contradicts that; the 11-table schema, enum-per-file convention, and `price_at_add`/cancel-void deltas (AD-7/AD-11) all line up with the data-models doc and code.

## Other Stale-Doc Notes (beyond the one asked about)

- `_bmad-output/project-context.md` line 35 (exceptions location) is the second stale claim found in that file this pass, beyond the already-known SQLAlchemy one — see Finding 1. `project-context.md` itself even flags at the bottom (line 92) "Revisit once `feature/postgres-integration` merges — it already touches the DB-layer, exceptions location, and config-loading rules documented above," suggesting the document's own author was aware it might be out of date on exactly this point. Worth a project-context.md refresh pass independent of the spine.
