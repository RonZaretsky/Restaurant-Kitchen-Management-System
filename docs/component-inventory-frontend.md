# Component Inventory - Frontend

**Date:** 2026-07-24
**Source:** `frontend/src/`

## Overview

The frontend has **one** implemented component. The folders intended to house future components, pages, services, and types exist but are empty (`.gitkeep` only). No design system or component library is chosen.

## Implemented Components

### `App` (`frontend/src/App.tsx`)

- **Category:** Root / Layout
- **Description:** Static placeholder — renders `<h1>Restaurant Kitchen Management System</h1>` with no props, state, or children.
- **Used by:** `main.tsx` (mounted directly into `#root`)

## Scaffolded, Empty Locations

| Folder | Intended Purpose | Current Contents |
|---|---|---|
| `src/components/` | Reusable UI components | Empty (`.gitkeep` only) |
| `src/pages/` | Route-level page components | Empty (`.gitkeep` only) |
| `src/services/` | API client / data-fetching layer | Empty (`.gitkeep` only) |
| `src/types/` | Shared TypeScript types/interfaces | Empty (`.gitkeep` only) |

## Design System

None chosen. No UI component library (e.g., MUI, Chakra, shadcn/ui) is installed. No design tokens, theme, or shared CSS/styling approach exists yet.

## Reusable vs. Feature-Specific

Not yet applicable — with a single static component, there is no established pattern to classify against. When the first real components are added, they should be sorted into `components/` (reusable) vs. `pages/` (feature/route-specific) per the existing folder convention.

---

_Generated using BMAD Method `document-project` workflow_
