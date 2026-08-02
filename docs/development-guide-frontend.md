# Development Guide - Frontend

**Date:** 2026-07-24
**Part:** frontend (`frontend/`)

## Prerequisites

- Node.js 20+
- [pnpm](https://pnpm.io/installation) — version pinned to `9.15.0` via the `packageManager` field in `package.json`; never use `npm`/`yarn` commands in this project

## Environment Setup

The README documents a `.env.example` → `.env` copy step, but **no `.env.example` file currently exists in the repository** (verified during this scan — only `.env`/`.env.*` are gitignored). Until one is added, set the variables manually if you need non-default values:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_API_TIMEOUT_MS=5000
```

Both have safe defaults hardcoded in `src/config/config.ts`, so a `.env` file is only needed to override them.

## Installation

```bash
cd frontend
pnpm install
```

## Running Locally

```bash
cd frontend
pnpm dev
```

App available at `http://localhost:3000` (port pinned in `vite.config.ts`).

## Build

```bash
pnpm build
```

Runs `tsc -b && vite build` — a full TypeScript project build (strict mode) followed by the Vite production build. Type errors (including unused locals/params and non-exhaustive switches) will fail this command, not just linting.

## Testing

**No test framework is currently installed** — no `vitest`, no `@testing-library/react`, no test files exist. The standard Vite/React pairing (`vitest` + `@testing-library/react`) is the natural choice when tests are introduced, but neither is installed yet.

## Common Development Tasks

- **Add a new page/route:** place it in `src/pages/` (currently empty). No router is installed yet — introducing one (e.g., React Router) should be raised as an explicit decision.
- **Add a reusable component:** place it in `src/components/` (currently empty).
- **Add an API call:** place it in `src/services/` (currently empty) — none exist yet, and the backend has no CORS middleware configured, so browser-based calls will fail until that's added on the backend side.
- **Add a shared type:** place it in `src/types/` (currently empty).
- **Read a build-time env var:** always go through `src/config/config.ts` — never read `import.meta.env` directly in a component.

---

_Generated using BMAD Method `document-project` workflow_
