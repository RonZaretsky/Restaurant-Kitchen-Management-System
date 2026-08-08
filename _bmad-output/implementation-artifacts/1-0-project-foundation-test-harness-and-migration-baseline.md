---
baseline_commit: 56c69cbf242117001b5b39a006349204d6964fef
---

# Story 1.0: Project Foundation, Test Harness and Migration Baseline

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the development team,
I want an executable test harness and a schema-migration baseline in place,
so that every story's acceptance criteria can actually be verified and every schema change from here has a migration path.

**Why this story exists and why it is first.** This is the only story in the plan (alongside 1.5) with no direct end-user value. It was created by the implementation-readiness gate, which found that all 25 stories are written as Given/When/Then assertions with nothing in the repo able to execute them, and that `Base.metadata.create_all` cannot evolve a schema while silently reporting success. Both problems compound with every story built on top of them, so they are cleared before Story 1.1 writes a line of feature code.

**Do not expand this story.** No auth, no routers, no models, no frontend screens. Story 1.1 owns all of that.

## Acceptance Criteria

**AC1 — Backend test harness**
Given no test framework exists on the backend,
When this story is built,
Then `pytest`, `pytest-asyncio` and `httpx` are added to `backend/pyproject.toml`, a `conftest.py` provides an async test client and a throwaway-database session fixture, and `uv sync` regenerates `backend/uv.lock`.

**AC2 — Frontend test harness**
Given no frontend test framework exists,
When this story is built,
Then `vitest`, `@testing-library/react` and `@testing-library/jest-dom` are added to `frontend/package.json` via `pnpm` (never npm or yarn), a `pnpm test` script is wired, and `pnpm-lock.yaml` is regenerated.

**AC3 — Both suites run green**
Given a trivial passing test on each side,
When the suites are run from a clean checkout,
Then both execute green, so every later story's acceptance criteria have something to run in.

**AC4 — Alembic baseline**
Given `Base.metadata.create_all` is still the schema mechanism and cannot evolve a schema,
When this story is built,
Then Alembic is adopted using the async template, a baseline revision is generated against the current `data_models/` schema, and `create_all` is removed from `backend/container.py`'s startup path.

**AC5 — Every later schema change has a path**
Given any later story needs a schema change,
When it ships,
Then it adds its own revision on top of this baseline, so no story in any epic is left without a migration path.

**AC6 — Migrations actually run (derived, see Dev Notes: Migration Execution Gap)**
Given `create_all` no longer runs at startup,
When the stack is brought up with `docker compose up` against an empty volume,
Then the schema is created by an explicit `alembic upgrade head` step before the API serves traffic, and the app starts against a correctly migrated database.

> AC6 is not in `epics.md`. It is required for the system to keep working after AC4 removes `create_all`, and a story must leave the system working end to end, not merely satisfy its written ACs. Do not skip it.

## Tasks / Subtasks

- [x] **Task 1: Backend test dependencies** (AC: 1)
  - [x] Add `pytest`, `pytest-asyncio`, `httpx` to a **dev dependency group** in `backend/pyproject.toml`, not the main `dependencies` list (see Dev Notes: Dockerfile Constraint)
  - [x] Run `uv sync` from inside `backend/` and commit the regenerated `backend/uv.lock`
  - [x] Configure `asyncio_mode` in `pyproject.toml` under `[tool.pytest.ini_options]`

- [x] **Task 2: Backend conftest and fixtures** (AC: 1, 3)
  - [x] Create `backend/tests/conftest.py` with an async test client fixture over the FastAPI app
  - [x] Add a throwaway-database session fixture (see Dev Notes: Test Database Strategy)
  - [x] Use `@pytest_asyncio.fixture` for every async fixture, never `@pytest.fixture` (see Dev Notes: pytest-asyncio 1.x)
  - [x] Do **not** define an `event_loop` fixture, it was removed in pytest-asyncio 1.0

- [x] **Task 3: Backend smoke test** (AC: 3)
  - [x] Add a test hitting the existing `GET /health` route through the async client, asserting `200` and `{"status": "ok"}`
  - [x] Verify `uv run pytest` passes from inside `backend/`

- [x] **Task 4: Alembic adoption** (AC: 4, 5)
  - [x] Add `alembic` to the **main** dependencies, not the dev group (migrations run in the deployed container)
  - [x] Run `alembic init -t async alembic` from inside `backend/`. The async template is mandatory, the default sync template does not work with the asyncpg driver
  - [x] Wire `alembic/env.py`: import `Base` from `data_models`, set `target_metadata = Base.metadata`, and resolve the database URL through `utils.load_config` rather than hardcoding it in `alembic.ini` (see Dev Notes: Alembic Config Wiring)
  - [x] Generate the baseline: `alembic revision --autogenerate -m "baseline schema"`
  - [x] **Inspect the generated revision before committing it.** Autogenerate must reproduce the 7 existing model modules exactly. If it emits an empty migration, `target_metadata` is wired wrong. If it emits drops, it is pointed at the wrong database

- [x] **Task 5: Remove `create_all`** (AC: 4)
  - [x] Delete the `async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)` block from `_init_database` in `backend/container.py`
  - [x] Remove the now-unused `from data_models import Base` import from `container.py` if nothing else needs it
  - [x] Confirm the container still initialises and disposes the engine correctly

- [x] **Task 6: Migration execution step** (AC: 6)
  - [x] Add an explicit `alembic upgrade head` step before the API starts (entrypoint script or a compose command), never inside FastAPI's lifespan
  - [x] Verify `docker compose down -v && docker compose up` produces a fully migrated database and a working `/health`

- [x] **Task 7: Frontend test harness** (AC: 2, 3)
  - [x] `pnpm add -D vitest @testing-library/react @testing-library/jest-dom jsdom`
  - [x] Add `"test": "vitest run"` and optionally `"test:watch": "vitest"` to `frontend/package.json` scripts
  - [x] Configure vitest in `vite.config.ts` with `environment: "jsdom"` and a setup file importing `@testing-library/jest-dom`
  - [x] Add a trivial passing component test
  - [x] Verify `pnpm test` passes and `pnpm build` still succeeds (strict TS flags are enforced at build time)
  - [x] Commit the regenerated `pnpm-lock.yaml`

### Review Findings

Reviewed 2026-08-08 by three parallel reviewers (Blind Hunter, Edge Case Hunter, Acceptance
Auditor) against a diff scoped to this story's File List (lockfiles excluded from line-by-line
review as machine-generated; independently confirmed in sync by two reviewers out-of-band).

**Decision needed** — resolved

- [x] [Review][Decision] `backend/.dockerignore` excludes `uv.lock`, so `alembic` (now a main
  dependency this story adds, running live migrations from the container entrypoint) resolves
  fresh at image-build time instead of from the committed lock. **Resolved: fix now** — moved to
  Patch below.

**Patch** — all 6 applied 2026-08-08

- [x] [Review][Patch] `backend/.dockerignore` excludes `uv.lock`, so the image build resolves
  dependencies (including `alembic`) fresh instead of from the committed lock
  [backend/.dockerignore:7] — fixed: removed the `uv.lock` line; verified it's now copied into
  the built image and `docker compose down -v && up` still migrates and serves `/health`
- [x] [Review][Patch] No guard against `DROP DATABASE` targeting a real database name if
  `TEST_DB_NAME` is misconfigured to match `config.yaml`'s `DB_NAME` default (`"kitchen"`, the
  same name the dev database uses) [backend/tests/conftest.py:62-84] — fixed: added
  `guard_test_database_name`, called before every `DROP`/`CREATE DATABASE` in both
  `empty_database` and `migrated_database`; verified it raises for `"kitchen"` and passes for
  `"kitchen_test"` / `"kitchen_empty"`
- [x] [Review][Patch] `run_async_migrations` disposes the engine after the `async with` block
  instead of in a `finally`, leaking a connection if a migration raises
  [backend/alembic/env.py:92-103] — fixed: wrapped in `try/finally`
- [x] [Review][Patch] `os.environ.setdefault("TEST_DB_NAME", ...)` doesn't catch an
  already-present empty string, so `TEST_DB_NAME=""` silently produces `DB_NAME=""`
  [backend/tests/conftest.py:7-8] — fixed: replaced with
  `os.environ.get("TEST_DB_NAME") or "kitchen_test"`
- [x] [Review][Patch] `alembic.ini`'s `prepend_sys_path = .` is dead/misleading now that
  `env.py` sets `sys.path` explicitly; add a comment noting it's superseded
  [backend/alembic.ini] — fixed: added a comment above the line
- [x] [Review][Patch] README's "Run locally" section documents `uv run python main.py` as the
  non-Docker dev path, but after `create_all` removal this now hits missing-table errors with
  no mention of `alembic upgrade head` [README.md:41-54] — fixed: added
  `uv run alembic upgrade head` as a required step before starting the server

All 6 fixes verified: backend 6/6 pytest still green, frontend 1/1 vitest still green, `pnpm
build` still succeeds, and a full `docker compose down -v && docker compose up --build` from an
empty volume still migrates the schema and returns a healthy `/health`.

**Defer**

- [x] [Review][Defer] `get_session` calls `container.database()` without `await`, raising
  `AttributeError` on first real DB-backed request (the async resource returns a Future)
  [backend/clients/database.py:9] — deferred, pre-existing bug on a must-not-change file,
  already flagged in Completion Notes for Story 1.1 to fix (single `await`)
- [x] [Review][Defer] `db_session` fixture has no per-test transaction isolation on the
  session-scoped database [backend/tests/conftest.py:88-97] — deferred, unreachable until a
  future story adds write-tests; only read-only tests exist today
- [x] [Review][Defer] `migrated_database` fixture has no per-worker uniqueness for parallel
  test execution [backend/tests/conftest.py:72-84] — deferred, unreachable today: no
  `pytest-xdist` dependency and no CI pipeline exists yet
- [x] [Review][Defer] DSN-building string is duplicated across `container.py`, `alembic/env.py`,
  and `conftest.py` [backend/container.py, backend/alembic/env.py:51-54,
  backend/tests/conftest.py:32-34] — deferred, centralizing further touches the must-not-change
  `container.py` signature; revisit if a 4th consumer appears
- [x] [Review][Defer] No clear-error guard when Postgres is unreachable; fixtures raise a raw
  `ConnectionRefusedError` deep in setup [backend/tests/conftest.py] — deferred, DX polish only,
  not a correctness bug

**Dismissed as noise (4):** docstrings intentionally stripped from test files per this session's
Arrange/Act/Assert convention (not a defect, see Debug Log); diff-under-review omitted lockfiles
(a review-scoping choice, both lockfiles independently confirmed in sync); `test_container.py`
building a fresh `Container()` instead of the `main.py` singleton (the only viable approach given
must-not-change constraints); `Dockerfile`'s explicit `chmod +x entrypoint.sh` (defensible
defensive practice, git file mode isn't reliably preserved across all environments).

## Dev Notes

### Migration Execution Gap (read before Task 5)

`backend/Dockerfile` ends with `CMD ["uv", "run", "python", "main.py"]` and `docker-compose.yml` has no migration step. Today the schema exists only because `container.py` calls `create_all` at startup. **The moment Task 5 removes that call, nothing creates the schema**, and a fresh `docker compose up` yields an app talking to an empty database. This fails at first query, not at boot, so it is easy to miss.

Fix it in the same story. `CLAUDE.md` is explicit: run migrations as an explicit step (entrypoint or compose command) rather than implicitly on app startup. Do not put `alembic upgrade head` inside the FastAPI lifespan, that reintroduces implicit schema management under a new name.

### Dockerfile Constraint (read before Task 1 and Task 4)

`backend/Dockerfile` runs `uv sync --no-dev`. Consequences:

- **Test dependencies belong in a dev group.** `pytest`, `pytest-asyncio`, `httpx` must not reach the production image.
- **`alembic` must be a main dependency.** Task 6 runs `alembic upgrade head` inside the container, so it has to survive `--no-dev`.

Getting this backwards produces an image that either bloats or crashes on entrypoint.

### Two syntax traps

**Where the dev group goes.** `backend/pyproject.toml` has `[tool.uv] package = false`. Declare test dependencies as a PEP 735 group so `uv sync --no-dev` actually excludes them:

```toml
[dependency-groups]
dev = ["pytest>=8.4.0", "pytest-asyncio>=1.4.0", "httpx>=0.27.0"]
```

`alembic` goes in the main `dependencies` array instead, for the reason in Dockerfile Constraint above.

**Typing the vitest config.** `frontend/vite.config.ts` currently imports `defineConfig` from `"vite"`, which does **not** type the `test` key, so adding one fails the strict build. Either import from `"vitest/config"` instead, or add `/// <reference types="vitest" />` at the top of the file. This is a build-time failure, not a lint warning.

### pytest-asyncio 1.x (read before Task 2)

The 0.x to 1.x jump changed how async fixtures are written. Anything remembered from older tutorials is wrong:

- **The `event_loop` fixture was removed in 1.0.** Do not define or override it.
- **Async fixtures must use `@pytest_asyncio.fixture`.** Decorating an async fixture with plain `@pytest.fixture` raises a DeprecationWarning in strict mode and does not behave as expected.
- `pytest-asyncio` 1.4.0 requires **pytest >= 8.4.0**.
- Set `asyncio_mode` explicitly in `[tool.pytest.ini_options]`. `strict` is the safer default; `auto` removes per-test decorators but hides intent.

### Test Database Strategy (read before Task 2)

The session fixture must not touch the development database. Two workable approaches:

1. **Separate test database, migrated (recommended).** Point tests at a distinct database name (for example `kitchen_test`, overridable by env var), run `alembic upgrade head` against it during session setup, and drop or truncate afterward. This continuously verifies the migration chain, which is exactly what this story exists to protect.
2. **Transaction rollback per test.** Open a connection, begin an outer transaction, bind the session to it, roll back after each test. Faster, but it never exercises migrations.

Whichever you pick, the fixture must yield an `AsyncSession` built the same way production builds one, via `async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)`. Do not construct sessions a second, divergent way. Note that using `create_all` inside a test fixture is acceptable if you choose approach 2, since AD-4 forbids it in the **startup path**, not in tests, but approach 1 is preferred precisely because it tests migrations.

### Alembic Config Wiring (read before Task 4)

The database URL is assembled in `container.py` as
`f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"`
from `config.yaml`, which uses `${ENV_VAR: default}` placeholders resolved by `utils.load_config`.

`alembic/env.py` must resolve the URL the same way rather than hardcoding `sqlalchemy.url` in `alembic.ini`. Otherwise migrations work locally and fail in Docker, where `DB_HOST` is `postgres` rather than `localhost`. Import `load_config` and `SETTINGS.CONFIG_PATH` and build the URL from the same values the app uses. There must be exactly one source of connection truth.

### Existing files this story modifies

| File | Current state | What changes |
|---|---|---|
| `backend/container.py` | `Container` with `config`, `logging`, `database` providers. `_init_database` builds the async engine, calls `create_all`, yields a `Database` dataclass, disposes the engine | Remove only the `create_all` block. Leave the provider structure, the `Database` dataclass, and the dispose path untouched |
| `backend/pyproject.toml` | 7 main dependencies, `[tool.uv] package = false` | Add `alembic` to main; add a dev group with the test dependencies; add `[tool.pytest.ini_options]` |
| `backend/Dockerfile` | `uv sync --no-dev`, `CMD uv run python main.py` | Add the migration step before the app starts |
| `docker-compose.yml` | 3 services, postgres healthcheck gating backend | Possibly a `command` override for the migration step |
| `frontend/package.json` | react 19, vite ^6, no test tooling, `packageManager: pnpm@9.15.0` | Add dev dependencies and the `test` script |
| `frontend/vite.config.ts` | plugins `[react()]`, `server.port 3000` | Add the `test` block |

Files that must **not** change: anything in `backend/data_models/` (the baseline is generated against the schema exactly as it stands), `backend/api/router.py`, `backend/main.py`, `backend/clients/database.py`.

### Do not do these here

- **Do not remove the stray `backend/data_models/exceptions/` folder.** That is an explicit acceptance criterion of Story 1.1. Removing it here creates a merge conflict and steals another story's scope.
- **Do not add CORS**, that is Story 1.1.
- **Do not call `container.wire()`**, that is Story 1.1. It is currently never called anywhere, and adding it without an `@inject` consumer does nothing.
- **Do not upgrade pnpm or TypeScript.** Both are flagged as known housekeeping in the architecture spine's Deferred section and were deliberately ratified as-is for this sprint.

### Verified library versions (checked 2026-08-08)

| Package | Latest | Notes |
|---|---|---|
| pytest | 9.1.1 | Requires Python >= 3.10, project is >= 3.12 |
| pytest-asyncio | 1.4.0 | Requires pytest >= 8.4.0. Major behaviour change from 0.x, see above |
| alembic | 1.19.0 | The architecture spine recorded 1.18.5 on 2026-07-30; it has since moved |
| vitest | 4.1.10 | Peer-depends on Vite `^6 \|\| ^7 \|\| ^8`. Project is on `^6.0.5`, so **no Vite upgrade is needed** |
| @testing-library/react | 16.3.2 | Peer-depends on React `^18 \|\| ^19`. Project is on React 19, compatible |

Prefer version floors (`>=`) for the backend to match the existing style in `pyproject.toml`, and let `uv` resolve. Re-verify at install time rather than pinning these exact numbers from memory.

### Project Structure Notes

- **Imports are relative to `backend/` as root.** The app runs as `uv run python main.py` from inside `backend/`. Never write `from backend.X import ...`. `conftest.py` and `alembic/env.py` must both respect this; `alembic/env.py` in particular needs `backend/` on `sys.path` to import `data_models`.
- Alembic lives at `backend/alembic/` with `versions/` inside it, matching the architecture spine's source tree.
- Tests go in `backend/tests/`. This is a new directory and does not conflict with the five existing role-based folders (`api`, `clients`, `data_models`, `exceptions`, `services`), which are for application code.
- **Type hints on every function signature**, including fixtures and generators.
- **Docstrings are required** on every function, method and class, including test fixtures. Comments between lines only where the code is genuinely hard to follow. **Never use an em dash in a docstring or comment.** See `_bmad-output/project-context.md`, "Comments and docstrings".

### Definition of Done

1. `uv run pytest` passes from inside `backend/`
2. `pnpm test` passes from inside `frontend/`
3. `pnpm build` still succeeds
4. `docker compose down -v && docker compose up` produces a migrated database and a healthy `/health`
5. `backend/uv.lock` and `frontend/pnpm-lock.yaml` are both committed and regenerated by their tools, never hand-edited
6. `grep -rn "create_all" backend/` returns nothing in the startup path

### References

- Story source: [Source: _bmad-output/planning-artifacts/epics.md#Story 1.0]
- Alembic invariant: [Source: ARCHITECTURE-SPINE.md#AD-4] — async template mandatory, `create_all` removed once wired, rebase rather than leave multiple heads
- DI invariant: [Source: ARCHITECTURE-SPINE.md#AD-1] — every lifecycle-managed resource is a `providers.Resource` on the container
- Source tree: [Source: ARCHITECTURE-SPINE.md#Structural Seed] — `backend/alembic/` is the sanctioned location
- Deferred items: [Source: ARCHITECTURE-SPINE.md#Deferred] — pnpm and TypeScript bumps explicitly out of scope
- Migration execution: [Source: CLAUDE.md#Database initialization / migrations] — explicit step, not implicit on app startup
- Conventions: [Source: _bmad-output/project-context.md] — installed vs. decided table, silent-failure list, comment and docstring rules
- Sequencing: [Source: _bmad-output/implementation-artifacts/sprint-status.yaml] — this story gates Story 1.1

## Dev Agent Record

### Agent Model Used

claude-opus-5 (Claude Code, bmad-dev-story workflow)

### Debug Log References

**Task order changed: Task 4 was implemented before Tasks 2 and 3.** The Test Database
Strategy note marks "separate test database, migrated" as the recommended approach, and it
runs `alembic upgrade head` during session setup. Alembic does not exist until Task 4, so
building the conftest first would have meant checking Task 2 and Task 3 complete against
code that could not run. Scope and content of every task are unchanged. Final order was
1, 4, 2, 3, 5, 6, 7.

**The baseline was generated against a scratch empty database, not the dev database.** The
`kitchen` database already held all 12 tables from the old `create_all` startup path, so
autogenerating against it would have produced an empty migration for the reason the story
warns about, but with a different cause than a mis-wired `target_metadata`. A throwaway
`kitchen_baseline_gen` database was created empty, the revision generated against it, then
verified with `alembic upgrade head` followed by `alembic check` (which reported
"No new upgrade operations detected"), and finally dropped.

**The drift guard was proved non-vacuous.** A throwaway `drift_probe` column was added to
`Dish`, `test_migrations_match_the_models` was confirmed to fail with
"Detected added column 'dishes.drift_probe'", and the probe was reverted.
`git status backend/data_models/` is clean, so the schema is byte-identical to the baseline
the migration was generated from.

**RED was observed before GREEN on each behavioural change.** `tests/test_health.py` failed
with "fixture 'client' not found" before `conftest.py` existed;
`test_startup_does_not_create_the_schema` failed with `assert 12 == 0` before `create_all`
was removed from `container.py`.

**First `vitest run` appeared to hang.** It was a cold start, not a failure. The first run
took 66 seconds, dominated by environment and setup; subsequent runs finish in about 1
second.

### Completion Notes List

**What was built.** Both test harnesses now exist and run green, and Alembic owns the
schema end to end. Backend: 6 tests over 3 files. Frontend: 1 test. A clean
`docker compose down -v && docker compose up` migrates the database before the API serves
traffic and returns a healthy `/health`.

**Design decisions worth knowing:**

1. **One source of connection truth.** `alembic/env.py` never reads `sqlalchemy.url` from
   `alembic.ini`; that line was deleted and replaced with a comment. `get_database_url()`
   rebuilds the URL from `utils.load_config(SETTINGS.CONFIG_PATH)`, so migrations resolve
   `${DB_HOST}` to `postgres` inside Docker and `localhost` outside it, with no second set
   of connection settings to keep in sync.
2. **`env.py` puts `backend/` on `sys.path` itself.** `alembic.ini` only ships
   `prepend_sys_path = .`, which is the current working directory and therefore wrong
   whenever Alembic runs from anywhere but `backend/`. The explicit insert is what lets the
   container entrypoint run the upgrade from `/app`.
3. **Tests select the throwaway database by setting `DB_NAME` before importing the app.**
   `main.py` reads the config at import time, so `conftest.py` sets the environment variable
   at module top before any application import. This reuses the existing
   `${ENV_VAR: default}` mechanism instead of adding a parallel test-config path. The name
   is overridable with `TEST_DB_NAME` and defaults to `kitchen_test`.
4. **The test database is built by `alembic upgrade head`, never `create_all`.** This is
   the recommended strategy from Dev Notes, chosen so every test run re-proves the migration
   chain can raise the schema from nothing.
5. **Migrations run in an entrypoint script, not the FastAPI lifespan.** `backend/entrypoint.sh`
   runs `alembic upgrade head` and then `exec`s the app. Compose already gates the backend on
   the Postgres healthcheck, so no wait loop was added.
6. **The entrypoint uses `uv run --no-dev`.** Plain `uv run` re-syncs the project environment
   at container start and would pull the dev group back into the running container, undoing
   the `uv sync --no-dev` in the image build. Verified: `pytest` and `httpx` are absent from
   the running container's site-packages, `alembic` is present.

**Verified against the Dockerfile constraint.** `uv export --no-dev` excludes
pytest/pytest-asyncio/httpx and includes alembic, and the same was confirmed inside the
built image.

**Findings deliberately NOT fixed here (out of this story's stated scope):**

- **`clients/database.py` is broken at request time.** `get_session` does
  `db = request.app.container.database()` without awaiting. The database resource is async,
  so the provider returns an `_asyncio.Future`, and `db.session_factory` raises
  `AttributeError: '_asyncio.Future' object has no attribute 'session_factory'`. Confirmed
  empirically while writing `tests/test_container.py`, which is why that test uses
  `await container.database()`. Nothing exercises `SessionDep` today, so nothing fails yet.
  This file is on the story's must-not-change list. **Story 1.1 should fix this** when it
  wires the first real route, and the fix is a single `await`.
- **`backend/.dockerignore` excludes `uv.lock`.** The Dockerfile's `COPY pyproject.toml uv.lock* ./`
  therefore copies no lockfile and `uv sync --no-dev` resolves fresh at build time, so the
  image is not reproducible from the committed lock. Pre-existing, does not block any AC
  here, and `.dockerignore` is not in this story's change list.
- **`backend/tests/` is copied into the production image** by `COPY . .`. Harmless bloat
  only, since the test dependencies are not installed.
- **An existing dev database created by `create_all` has no `alembic_version` row.** After
  this story, `alembic upgrade head` against such a database will fail on
  "table already exists". Fix it with `alembic stamp head`, or just
  `docker compose down -v`. Fresh volumes are unaffected.

**Beyond the literal subtasks, three guard tests were added** (`tests/test_migrations.py`,
`tests/test_container.py`). They are not scope expansion: they are the executable form of
AC4 and AC5. Without them "every later schema change has a migration path" is an assertion
nobody checks. `test_migrations_match_the_models` fails the build the moment a model changes
without a revision.

**One small hygiene change outside the listed files:** `*.tsbuildinfo` was added to the root
`.gitignore`. `tsc -b` writes those two files on every `pnpm build`, and they were not
ignored. `.pytest_cache/` needed nothing, pytest writes its own self-ignoring `.gitignore`.

### File List

**Added**

- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/README`
- `backend/alembic/script.py.mako`
- `backend/alembic/versions/8c7084cec0ff_baseline_schema.py`
- `backend/entrypoint.sh`
- `backend/tests/conftest.py`
- `backend/tests/test_health.py`
- `backend/tests/test_migrations.py`
- `backend/tests/test_container.py`
- `frontend/src/App.test.tsx`
- `frontend/src/setupTests.ts`

**Modified**

- `backend/pyproject.toml` (alembic in main deps, `[dependency-groups] dev`, `[tool.pytest.ini_options]`)
- `backend/uv.lock` (regenerated by `uv sync`)
- `backend/container.py` (removed the `create_all` block and the now-unused `Base` import)
- `backend/Dockerfile` (`chmod +x entrypoint.sh`, `CMD ["./entrypoint.sh"]`)
- `frontend/package.json` (test dev dependencies, `test` and `test:watch` scripts)
- `frontend/pnpm-lock.yaml` (regenerated by `pnpm add -D`)
- `frontend/vite.config.ts` (`defineConfig` from `vitest/config`, jsdom `test` block)
- `.gitignore` (`*.tsbuildinfo`)
- `backend/.dockerignore` (removed `uv.lock` exclusion, review patch)
- `backend/tests/conftest.py` (added `guard_test_database_name`, fixed empty `TEST_DB_NAME` handling, review patches)
- `backend/alembic/env.py` (`try/finally` around engine dispose, review patch)
- `backend/alembic.ini` (clarifying comment on `prepend_sys_path`, review patch)
- `README.md` (added `alembic upgrade head` to the local run instructions, review patch)

**Deleted**

- None

**Confirmed unchanged** (on the story's must-not-change list): `backend/data_models/**`,
`backend/api/router.py`, `backend/main.py`, `backend/clients/database.py`,
`backend/data_models/exceptions/` (left in place for Story 1.1), `docker-compose.yml`.

### Definition of Done Verification

| # | Requirement | Result |
|---|---|---|
| 1 | `uv run pytest` passes from inside `backend/` | ✅ 6 passed |
| 2 | `pnpm test` passes from inside `frontend/` | ✅ 1 passed |
| 3 | `pnpm build` still succeeds | ✅ `tsc -b && vite build`, built in 7.29s |
| 4 | `docker compose down -v && docker compose up` gives a migrated DB and healthy `/health` | ✅ all 3 services up, 13 tables, `/health` 200, frontend 200 |
| 5 | `uv.lock` and `pnpm-lock.yaml` regenerated by their tools, never hand-edited | ✅ `uv sync` and `pnpm add -D` |
| 6 | `grep -rn "create_all" backend/` returns nothing in the startup path | ✅ zero hits in application code; remaining hits are test prose explaining why it must stay gone |

### Acceptance Criteria Verification

| AC | Result |
|---|---|
| AC1 backend harness | ✅ pytest 9.1.1, pytest-asyncio 1.4.0, httpx 0.28.1 in `[dependency-groups] dev`; `conftest.py` provides `client`, `db_session`, `migrated_database`, `empty_database`; `uv.lock` regenerated |
| AC2 frontend harness | ✅ vitest 4.1.10, @testing-library/react 16.3.2, @testing-library/jest-dom 7.0.0, jsdom 30.0.1 added via `pnpm` only; `pnpm test` wired; `pnpm-lock.yaml` regenerated |
| AC3 both suites green | ✅ backend 6 passed, frontend 1 passed |
| AC4 Alembic baseline | ✅ async template, revision `8c7084cec0ff` covering all 12 tables, `create_all` removed from `container.py` |
| AC5 later changes have a path | ✅ baseline is the single root revision; `test_migrations_match_the_models` fails any model change shipped without a revision |
| AC6 migrations actually run | ✅ `entrypoint.sh` runs `alembic upgrade head` before `exec`ing the app; verified from an empty volume |

## Change Log

| Date | Change |
|---|---|
| 2026-08-08 | Added the backend pytest harness (pytest, pytest-asyncio, httpx as a PEP 735 dev group) with an async client fixture and a migrated throwaway-database fixture. |
| 2026-08-08 | Adopted Alembic on the async template, wired `env.py` to resolve the database URL through `utils.load_config`, and generated baseline revision `8c7084cec0ff` against an empty database. |
| 2026-08-08 | Removed `Base.metadata.create_all` and the unused `Base` import from `backend/container.py`, leaving the provider structure and dispose path untouched. |
| 2026-08-08 | Added `backend/entrypoint.sh` running `alembic upgrade head` before the API starts, and pointed the Dockerfile `CMD` at it. Migrations never run inside the FastAPI lifespan. |
| 2026-08-08 | Added the frontend vitest harness (vitest, @testing-library/react, jest-dom, jsdom) with a jsdom `test` block typed via `vitest/config`, a setup file, and a `pnpm test` script. |
| 2026-08-08 | Added migration and container guard tests covering AC4 and AC5, and ignored `*.tsbuildinfo`. |
| 2026-08-08 | Applied bmad-code-review findings (3-layer parallel review): stopped `uv.lock` being excluded from the Docker build context, guarded the test-database fixtures against dropping a non-test database, fixed a connection leak on migration failure, fixed an empty `TEST_DB_NAME` edge case, clarified dead `alembic.ini` config, and documented the manual `alembic upgrade head` step in the README's local-run instructions. |
