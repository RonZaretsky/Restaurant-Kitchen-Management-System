# Restaurant-Kitchen-Management-System Documentation Index

**Type:** multi-part with 2 parts
**Primary Language:** Python (backend), TypeScript (frontend)
**Architecture:** DI-container-based FastAPI backend + React/Vite SPA frontend
**Last Updated:** 2026-07-24

## Project Overview

A full-stack restaurant kitchen management system. The backend (FastAPI + SQLAlchemy async + PostgreSQL) has a complete 11-table data model but only a `GET /health` endpoint implemented. The frontend (React 19 + TypeScript + Vite) is a bare scaffold with one placeholder component. The two parts don't yet call each other in code, and the backend has no CORS middleware or auth layer. See [project-overview.md](./project-overview.md) for the full executive summary.

## Project Structure

This project consists of 2 parts:

### Backend (backend)

- **Type:** backend (Python/FastAPI)
- **Location:** `backend/`
- **Tech Stack:** FastAPI, dependency-injector, SQLAlchemy(asyncio), asyncpg, loguru, uv
- **Entry Point:** `backend/main.py`

### Frontend (frontend)

- **Type:** web (React/TypeScript)
- **Location:** `frontend/`
- **Tech Stack:** React 19, Vite 6, pnpm
- **Entry Point:** `frontend/src/main.tsx`

## Cross-Part Integration

Intended as REST-over-HTTP (frontend → backend), but not yet implemented on either side, and currently blocked by missing CORS middleware on the backend. See [integration-architecture.md](./integration-architecture.md) for full details.

## Quick Reference

### Backend Quick Ref

- **Stack:** FastAPI ≥0.115.0, dependency-injector ≥4.41.0, SQLAlchemy[asyncio] ≥2.0.0, asyncpg ≥0.29.0, loguru ≥0.7.0
- **Entry:** `backend/main.py`
- **Pattern:** Service/API-centric, DI-managed resource lifecycle (logging + database as `providers.Resource`)

### Frontend Quick Ref

- **Stack:** React 19.0.0, TypeScript ~5.7.2 (strict), Vite ^6.0.5
- **Entry:** `frontend/src/main.tsx`
- **Pattern:** Component-based SPA (currently a single static component)

## Generated Documentation

### Core Documentation

- [Project Overview](./project-overview.md) — Executive summary and high-level architecture
- [Source Tree Analysis](./source-tree-analysis.md) — Annotated directory structure

### Part-Specific Documentation

#### Backend (backend)

- [Architecture](./architecture-backend.md) — Technical architecture for the backend
- [Development Guide](./development-guide-backend.md) — Setup and dev workflow
- [API Contracts](./api-contracts-backend.md) — API documentation (`GET /health` only, today)
- [Data Models](./data-models-backend.md) — Data architecture (links to the existing `database-schema.md`)

#### Frontend (frontend)

- [Architecture](./architecture-frontend.md) — Technical architecture for the frontend
- [Components](./component-inventory-frontend.md) — Component catalog
- [Development Guide](./development-guide-frontend.md) — Setup and dev workflow

### Integration

- [Integration Architecture](./integration-architecture.md) — How the parts communicate (and why they don't yet)
- [Project Parts Metadata](./project-parts.json) — Machine-readable structure

### Optional Documentation

- [Deployment Guide](./deployment-guide.md) — Docker Compose deployment process and known gaps

## Existing Documentation

- [database-schema.md](./database-schema.md) — Full column-level database schema, business logic, and relationship summary (pre-existing, verified against code during this scan — no discrepancies found)
- [diagrams/database-schema.puml](./diagrams/database-schema.puml) — PlantUML ER diagram (pre-existing)
- [README.md](../README.md) — Top-level run instructions (repo root)
- [_bmad-output/project-context.md](../_bmad-output/project-context.md) — AI-agent-facing rules/conventions (BMad-generated, not end-user documentation, but a useful companion to this index for AI-assisted development)

## Getting Started

### Backend Setup

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/)

**Install & Run:**

```bash
cd backend
uv sync
uv run python main.py
```

### Frontend Setup

**Prerequisites:** Node.js 20+, [pnpm](https://pnpm.io/installation) 9.15.0

**Install & Run:**

```bash
cd frontend
pnpm install
pnpm dev
```

### Full Stack (Docker Compose)

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

## For AI-Assisted Development

This documentation was generated specifically to enable AI agents to understand and extend this codebase. See also [_bmad-output/project-context.md](../_bmad-output/project-context.md) for condensed, rule-form conventions.

### When Planning New Features:

**UI-only features:**
→ Reference: `architecture-frontend.md`, `component-inventory-frontend.md`

**API/Backend features:**
→ Reference: `architecture-backend.md`, `api-contracts-backend.md`, `data-models-backend.md`

**Full-stack features:**
→ Reference: both architecture docs + `integration-architecture.md` (and note the CORS gap — it must be resolved before any real frontend→backend call will work)

**Deployment changes:**
→ Reference: `deployment-guide.md`

---

_Documentation generated by BMAD Method `document-project` workflow_
