# Frontend Architecture - Restaurant-Kitchen-Management-System

**Date:** 2026-07-24
**Part:** frontend (`frontend/`)

## Executive Summary

The frontend is a minimal Vite + React 19 + TypeScript (strict) single-page application scaffold. Only one component exists (`App.tsx`, a static placeholder heading) and the folder structure for future growth (`components/`, `pages/`, `services/`, `types/`) is in place but empty. No routing, state management, component library, or API client code has been written yet.

## Technology Stack

| Category | Technology | Version | Justification |
|---|---|---|---|
| Language | TypeScript | ~5.7.2 | Strict mode enforced (`tsconfig.app.json`) |
| Framework | React | 19.0.0 | `createRoot` + `StrictMode` in `main.tsx` |
| Build tool | Vite | ^6.0.5 | Dev server on port 3000 (`vite.config.ts`) |
| React plugin | @vitejs/plugin-react | ^4.3.4 | Fast Refresh support |
| Package manager | pnpm | 9.15.0 (pinned via `packageManager` field) | Never use npm/yarn commands in this project |

## Architecture Pattern

Component-based SPA (React functional components). The intended folder convention — visible from the scaffolded empty directories — is:

- `pages/` — route-level components
- `components/` — reusable UI components
- `services/` — API call layer
- `types/` — shared TypeScript types

No router (e.g., React Router), state management library (Redux/Context/MobX/Zustand), or UI component library has been chosen yet. Per project conventions, the first PR that needs one of these should raise it as an explicit decision rather than silently picking one.

## Component Overview

- **`main.tsx`** — application entry point; mounts `<App />` (wrapped in `<StrictMode>`) into `#root` via `createRoot`
- **`App.tsx`** — currently a single static placeholder: `<h1>Restaurant Kitchen Management System</h1>`
- **`config/config.ts`** — the only "service-like" module today: reads `import.meta.env.VITE_API_BASE_URL` / `VITE_API_TIMEOUT_MS` with fallback defaults (`http://localhost:8000`, `5000`). **Convention: never read `import.meta.env` directly in components — always go through this module.**
- **`vite-env.d.ts`** — Vite client type reference
- **`components/`, `pages/`, `services/`, `types/`** — empty except `.gitkeep`; no components, routes, API clients, or shared types exist yet

## State Management

None implemented. No Redux/Context/MobX/Zustand present. To be decided when the first feature requiring shared state is built.

## UI Component Inventory

See [component-inventory-frontend.md](./component-inventory-frontend.md) — effectively empty; only the root `<App />` placeholder exists.

## Source Tree

See [source-tree-analysis.md](./source-tree-analysis.md) for the full annotated tree.

## Development Workflow

See [development-guide-frontend.md](./development-guide-frontend.md).

## Deployment Architecture

See [deployment-guide.md](./deployment-guide.md). Multi-stage `frontend/Dockerfile`: `node:20-alpine` build stage (`pnpm install && pnpm build`, with `VITE_API_BASE_URL`/`VITE_API_TIMEOUT_MS` as build `ARG`s baked into the static bundle) → `nginx:alpine` serving `/dist` on port 80, exposed as host port 3000 via Docker Compose.

## Testing Strategy

No test framework installed (no `vitest`, no `@testing-library/react`, no test files). The standard Vite/React pairing (`vitest` + `@testing-library/react`) is the natural choice when tests are introduced, but neither is installed — don't import them speculatively.

## Critical Architectural Notes

- **Build-time env baking:** `VITE_API_BASE_URL` is injected as a Docker build `ARG`, meaning it's fixed at image-build time, not runtime. Changing the backend URL for an already-built frontend image requires a rebuild, not just an environment variable change at container start.
- **No CORS-aware error handling exists** — since no HTTP calls are implemented yet, there's no precedent for how API errors (including the current lack of CORS on the backend) should be surfaced to the UI.
- **Strict TypeScript config** — `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`, and `isolatedModules: true` are all enforced at `pnpm build` time (not just lint), and each file must be independently transpilable (no `const enum`).

---

_Generated using BMAD Method `document-project` workflow_
