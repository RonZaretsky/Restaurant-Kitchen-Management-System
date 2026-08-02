---
project_name: 'Restaurant-Kitchen-Management-System'
user_name: 'Ofek'
date: '2026-07-24'
sections_completed: ['technology_stack', 'language_rules', 'framework_rules', 'testing_rules', 'quality_rules', 'workflow_rules', 'anti_patterns']
status: 'complete'
rule_count: 29
optimized_for_llm: true
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

- Backend: Python 3.12+, FastAPI ≥0.115.0, uvicorn[standard] ≥0.30.0, dependency-injector ≥4.41.0 (v4 API), loguru ≥0.7.0, PyYAML ≥6.0 — managed via `uv` (backend/uv.lock is authoritative)
- Frontend: React 19.0.0, TypeScript ~5.7.2 (strict mode), Vite ^6.0.5, pnpm 9.15.0 (packageManager pinned — never use npm/yarn commands)
- Orchestration: Docker Compose (backend :8000, frontend :3000 host → :80 container)
- Planned but NOT yet installed: PostgreSQL + SQLAlchemy (schema is designed in docs/database-schema.md, no models exist in code yet — do not assume SQLAlchemy is available until it's added to backend/pyproject.toml)
- Future DB layer: when PostgreSQL/SQLAlchemy are added, the engine/session MUST be wired as a `providers.Resource` in `backend/container.py`, following the same init/teardown pattern as `logging` — never instantiate `create_engine`/`Session` directly in route handlers or services
- Lockfiles (`backend/uv.lock`, `frontend/pnpm-lock.yaml`) are authoritative — regenerate via `uv sync` / `pnpm install` after any manual `pyproject.toml`/`package.json` edit, never hand-edit the lockfile
- Dependency floors (`fastapi>=0.115.0`, `dependency-injector>=4.41.0`, etc.) are currently unbounded — acceptable for now, but revisit with upper bounds before this stabilizes toward production

## Critical Implementation Rules

### Language-Specific Rules

**Python:**
- Imports are relative to `backend/` as the root (app runs via `uv run python main.py` from inside `backend/`) — never use `from backend.X import ...` package-style imports
- Every function signature must have type hints, including generators and DI provider functions
- FastAPI route handlers must be `async def` with an explicit Pydantic `response_model` — never return bare dicts
- Custom exceptions belong in `backend/exceptions/` (currently empty, but it's the designated location) — don't inline generic `raise Exception(...)` or create a parallel error-handling location

**TypeScript:**
- `strict`, `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch` are enforced at build time (`tsconfig.app.json`) — unused vars/params and non-exhaustive switches will fail `pnpm build`, not just lint
- `isolatedModules: true` — write each file as independently transpilable; no `const enum`, no type-only patterns that require whole-program knowledge
- Never read `import.meta.env` directly in components — always go through `src/config/config.ts`

### Framework-Specific Rules

**FastAPI:**
- `container.wire(modules=[...])` is not yet called anywhere — required before any `@inject`/`Depends(Provide[...])` usage works. The `modules` list must be updated (appended to, never silently replaced) every time a new router/module starts using `@inject`, wherever that call ends up living — a partial list means DI resolves to unconfigured providers at request time, not import time, so it fails silently until something is actually called
- Routes currently live in a single `APIRouter` (`backend/api/router.py`). When adding a new domain's endpoints (menu, orders, inventory, etc.), prefer a dedicated sub-router included into the main one over growing one file indefinitely

**React:**
- Respect the existing empty-but-intentional folder structure: `pages/` for route-level components, `components/` for reusable UI, `services/` for API calls, `types/` for shared TypeScript types — do not add flat files to `src/` when a matching folder exists
- No state management library or component library is chosen yet — the first PR that needs one should raise it as a decision, not silently pick one

### Testing Rules

- No test framework is set up on either side yet — no `pytest`/`conftest.py` on the backend, no `vitest`/testing-library on the frontend, no test files exist at all. Do not assume a framework or write tests against one without first raising the choice as a decision (backend: `pytest` + `httpx.AsyncClient` is the standard FastAPI pairing; frontend: `vitest` + `@testing-library/react` is the standard Vite/React pairing) — but neither is installed yet, so don't import them speculatively

### Code Quality & Style Rules

- No linter/formatter is configured on either side (no `.eslintrc`/`eslint.config.*`/`.prettierrc`, no `ruff`/`black`/`flake8` config) — don't assume enforcement exists; don't add lint-suppression comments for rules that aren't configured
- Naming: Python snake_case files/modules, PascalCase classes; TypeScript PascalCase components, camelCase everything else
- Backend code must be placed into the existing role-based folders (`api`, `clients`, `data_models`, `exceptions`, `services`) by responsibility — don't create new top-level backend modules for something that fits an existing one
- No docstring/comment convention exists yet — every existing file is comment-free; don't introduce a new documentation style unilaterally

### Development Workflow Rules

- Branch naming: `feature/<name>` or `fix/<name>` — matches existing history (`feature/docker-compose`, `fix/frontend-docker-build`, etc.)
- Commit messages: short, imperative-mood, single-line summaries — no conventional-commit prefixes (`feat:`/`fix:`) in use
- All changes land via GitHub PR, merged into `main` — no direct-to-main pushes observed in history
- No CI/CD is configured (no `.github/workflows`) — don't assume tests/lint run automatically on PRs; nothing currently gates a merge besides review

### Critical Don't-Miss Rules

- No CORS middleware is configured — frontend (`:3000`) and backend (`:8000`) are different origins. Add `CORSMiddleware` to the FastAPI app before wiring any real frontend→backend API call, or requests will fail silently in-browser
- No authentication/authorization layer exists in code yet, despite the `User.role` enum (admin/waiter/cook/warehouse_manager) being defined in the schema doc. Do not assume any endpoint is protected or that a request carries an authenticated user — every route today is effectively public until an auth layer is added

---

## Usage Guidelines

**For AI Agents:**

- Read this file before implementing any code
- Follow ALL rules exactly as documented
- When in doubt, prefer the more restrictive option
- Update this file if new patterns emerge

**For Humans:**

- Keep this file lean and focused on agent needs
- Update when technology stack changes
- Review quarterly for outdated rules
- Remove rules that become obvious over time
- Revisit once `feature/postgres-integration` merges — it already touches the DB-layer, exceptions location, and config-loading rules documented above

Last Updated: 2026-07-24
