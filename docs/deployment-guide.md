# Deployment Guide

**Date:** 2026-07-24
**Source:** `docker-compose.yml` (root), `backend/Dockerfile`, `frontend/Dockerfile`

## Overview

The whole stack is orchestrated with a single root-level `docker-compose.yml` defining three services: `postgres`, `backend`, `frontend`. There is no CI/CD pipeline (no `.github/workflows/`) and no Kubernetes/Terraform/infra-as-code — deployment today is Docker Compose only.

## Infrastructure Requirements

- Docker + Docker Compose
- No external managed services required — Postgres runs as a container with a named volume (`postgres_data`) for persistence

## Services

### `postgres`

- **Image:** `postgres:16-alpine`
- **Port:** `5432:5432`
- **Env:** `POSTGRES_USER=kitchen`, `POSTGRES_PASSWORD=kitchen`, `POSTGRES_DB=kitchen` (hardcoded in compose, not parameterized)
- **Healthcheck:** `pg_isready -U kitchen -d kitchen`, 5s interval, 5 retries
- **Volume:** `postgres_data:/var/lib/postgresql/data`
- **Restart policy:** `unless-stopped`

### `backend`

- **Build context:** `./backend` (`backend/Dockerfile`: `python:3.12-slim`, installs `uv`, runs `uv sync --no-dev`, `CMD ["uv", "run", "python", "main.py"]`)
- **Port:** `8000:8000`
- **Env:** `DB_HOST=postgres`, `DB_PORT=5432`, `DB_USER=kitchen`, `DB_PASSWORD=kitchen`, `DB_NAME=kitchen` — note these match the `postgres` service's hardcoded credentials
- **Depends on:** `postgres` with `condition: service_healthy` — backend won't start until Postgres passes its healthcheck
- **Restart policy:** `unless-stopped`

### `frontend`

- **Build context:** `./frontend` (`frontend/Dockerfile`: multi-stage — `node:20-alpine` build stage running `pnpm install && pnpm build`, output copied into an `nginx:alpine` runtime stage serving `/dist` on port 80)
- **Build arg:** `VITE_API_BASE_URL=http://localhost:8000` — baked into the static JS bundle at **build time**, not overridable at container start
- **Port:** `3000:80` (host 3000 → container 80)
- **Depends on:** `backend` (no health-check condition, just start-order)
- **Restart policy:** `unless-stopped`

## Deployment Process

```bash
docker compose up --build
```

Brings up all three services in dependency order (`postgres` healthy → `backend` → `frontend`).

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

## Environment Configuration

- Postgres and backend DB credentials are **hardcoded** in `docker-compose.yml` (`kitchen`/`kitchen`/`kitchen`) — fine for local dev, not suitable as-is for a production deployment without externalizing secrets.
- `frontend`'s `VITE_API_BASE_URL` build arg points at `http://localhost:8000`, i.e., the **host machine's** view of the backend, not the Docker-internal service name `backend`. This works because the frontend is a static bundle served to a browser on the host, not calling the backend from inside the Docker network.

## CI/CD Pipeline

**None configured.** No `.github/workflows/`, no `.gitlab-ci.yml`, no other CI config exists. Nothing currently gates a merge besides manual review — tests/lint are not automatically run on PRs (and no test/lint tooling is installed yet regardless).

## Known Gaps for Production Readiness

- No CORS middleware on the backend (browser calls from the frontend origin will fail until added)
- No authentication/authorization layer
- Hardcoded DB credentials in compose (should move to secrets/env injection for real deployments)
- No migration tooling — schema changes to an already-deployed Postgres instance require manual intervention (`create_all` is additive-only)
- No CI/CD — no automated test/build gate on PRs

---

_Generated using BMAD Method `document-project` workflow_
