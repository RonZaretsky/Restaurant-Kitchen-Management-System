# Integration Architecture

**Date:** 2026-07-24

## Overview

The frontend and backend are designed to integrate over REST/HTTP, but **no integration code exists yet** on either side — this document describes the intended wiring (visible in config) and the concrete gaps that block it from working today.

## Integration Points

### Frontend → Backend

- **Type:** REST API (planned; not yet implemented)
- **Location:** `frontend/src/config/config.ts` defines `VITE_API_BASE_URL` (default `http://localhost:8000`) and `VITE_API_TIMEOUT_MS` (default `5000`), but `frontend/src/services/` — where API-calling code would live — is empty.
- **Details:** No `fetch`/`axios`/HTTP client code exists anywhere in the frontend. No endpoints beyond `GET /health` exist on the backend to call.

## Data Flow

None implemented yet. Once built, the expected flow is: browser → frontend (React) → REST call to backend (`VITE_API_BASE_URL`) → FastAPI route → SQLAlchemy session (`SessionDep`) → PostgreSQL.

## Authentication Flow

Not implemented on either side. No login endpoint, no token/session handling in the frontend, no auth middleware in the backend.

## Blocking Gaps (must be resolved before real frontend↔backend calls work)

1. **No CORS middleware on the backend** — the frontend (`:3000` in dev, `:80` behind the Docker `frontend` service) and backend (`:8000`) are different origins. Browser requests will fail silently until `CORSMiddleware` is added to the FastAPI app in `backend/main.py`.
2. **No API client layer on the frontend** — `services/` is empty; nothing calls the backend yet.
3. **No business endpoints on the backend** — only `GET /health` exists; there's nothing meaningful to call yet beyond that.

## Deployment-Time Networking Note

In Docker Compose, the frontend's `VITE_API_BASE_URL` build arg is set to `http://localhost:8000` (the *host* machine's address), not the Docker-internal service name `backend`. This is correct for the current setup because the frontend serves a static bundle to the browser (which runs on the host, not inside the Docker network) — but it means the frontend container itself cannot reach the backend container via that URL from server-side code (there is none today).

---

_Generated using BMAD Method `document-project` workflow_
