---
title: Sprint Change Proposal — User Logout
date: '2026-08-14'
status: proposed
---

# Sprint Change Proposal: User Logout (backend + frontend)

## 1. Issue Summary

**Trigger:** No specific story. Discovered during manual testing of the running Docker stack after
Story 3.1 landed, when Ron asked "how to logout?" and the answer turned out to be "there is no way."

**Problem statement:** User logout was never captured as a requirement anywhere in this project's
planning chain. Verified directly, not assumed:

- **PRD**: §6.1 states "FR-1 through FR-25, in full — this is deliberately the entire v1." FR-1
  (`4.1 Authentication & Access Control`) covers login only. §8 Open Question 1's resolution
  covers JWT's 8-hour *expiry*-driven return to Login, never a user-initiated sign-out action.
- **Epics**: Epic 1 (Staff Accounts & Access Control) is scoped to FR-1, FR-2, FR-3 only. Story
  1.1's (User Login) acceptance criteria cover login and the expiry-redirect behavior, nothing else.
- **UX**: Zero mentions of "logout" or "sign out" in `EXPERIENCE.md`, `DESIGN.md`, or any of the 13
  mockups. No nav-bar mockup shows a sign-out control. Confirmed empirically in the running app: the
  `AppShell` nav bar shows the user's name, role, and a theme toggle — no sign-out affordance.
- **Architecture**: No mention in `ARCHITECTURE-SPINE.md`. AD-3 (JWT in an httpOnly cookie, no
  refresh-token flow, no server-side session store) already governs the session shape a logout would
  operate within, but never anticipated a logout action itself.
- **Code**: Confirmed via grep across `backend/` and `frontend/src/`, zero matches for
  `logout`/`Logout` anywhere.

**Category:** Misunderstanding/omission of original requirements — a genuine planning gap of the same
class the Story 2.5 review found for the Category/Dish creation forms (logged in `deferred-work.md`
at the time), not a technical limitation or a stakeholder-driven pivot.

## 2. Impact Analysis

**Epic impact:** Epic 1 (Staff Accounts & Access Control) can still be completed exactly as planned;
this is a pure addition, not a break. One new story slots in after Story 1.6. No other epic is
affected — Epic 3 (in progress) and Epics 4–6 (backlog) are orthogonal to session lifecycle. No epic
becomes obsolete; no new epic is needed; no resequencing is needed. Story 1.7 has no dependency on
anything built after Story 1.4 (the `AppShell`/nav it extends already exists), so it can land whenever
convenient without blocking or being blocked by Epic 3's in-flight work.

**Artifact conflicts:**
- **PRD**: needs a new FR (FR-26, next available number) under §4.1, and §6.1's "FR-1 through FR-25"
  line needs to become "FR-1 through FR-26."
- **Architecture**: no new AD needed — AD-3 already covers the session mechanism; a logout is
  documented as operating within it (clearing the cookie), not changing it. Worth stating explicitly
  as a scope limitation: since v1 has no server-side token revocation store, logout clears the
  browser's cookie only — a token copied out before logout stays cryptographically valid until its
  natural 8-hour expiry if replayed. This is an accepted v1 limitation given the closed-staff,
  physical-terminal threat model (no diner-facing exposure), not a gap this story needs to close.
- **UX**: additive only — a "Sign Out" control needs to appear in `AppShell`'s shared nav area,
  available uniformly to all four Roles (no mockup redesign, no new screen).
- **Other artifacts** (deployment, IaC, CI, testing strategy): no impact. The existing backend
  pytest / frontend vitest pattern covers this story the same way it covered every prior one.

**Technical impact:** Small and isolated. Backend: one new route (session cookie clear) alongside the
existing `api/auth.py`. Frontend: one new control wired into the already-existing `AppShell`/nav and
`authService.ts`. No schema change, no migration.

## 3. Recommended Approach

**Selected: Option 1 — Direct Adjustment.** Add one new story (1.7) within Epic 1's existing
structure, plus the corresponding FR in the PRD. No rollback (nothing built needs to be reverted —
this is a pure omission, not a defect in shipped work) and no MVP redefinition (this doesn't shrink,
reduce, or reshuffle scope, it fills a gap).

- **Effort:** Low. One backend route, one frontend control, both extending existing, well-understood
  patterns (`api/auth.py`, `AppShell`, `authService.ts`).
- **Risk:** Low. No existing behavior changes; nothing else depends on logout's absence.
- **Rollback (Option 2) and MVP Review (Option 3):** both evaluated, both not viable/not applicable —
  there is nothing to roll back and no scope trade-off to make.

## 4. Detailed Change Proposals

### 4.1 PRD (`_bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md`)

**Section: 4.1 Authentication & Access Control — new FR, appended after FR-3**

```
#### FR-26: User logout

A User can end their own session, returning to the Login screen with no further access until they
authenticate again.

**Consequences (testable):**
- The session cookie is cleared so the browser can no longer present it; any subsequent
  non-login, non-health request behaves exactly as an unauthenticated one (FR-1, NFR-2).
- Logout is available uniformly to every authenticated Role — the same action regardless of Role
  (FR-2's Role-level model).
- v1 has no server-side token revocation store (no refresh-token flow, §8 Open Question 1):
  logout clears the browser's cookie only. A token copied out before logout remains
  cryptographically valid until its natural 8-hour expiry if replayed from that copy.
  `[ASSUMPTION: an accepted v1 limitation given the closed-staff, physical-terminal threat model —
  not directly confirmed with Ofek/Ron — see §9.]`
```

**Section: 6.1 MVP Scope**

```
OLD: FR-1 through FR-25, in full — this is deliberately the entire v1. [...]
NEW: FR-1 through FR-26, in full — this is deliberately the entire v1. [...]
```

**Section: 9. Assumptions Index — new entry**

```
- §4.1 FR-26 — Logout clears the client-side session cookie only; v1's stateless-JWT/no-revocation-
  store design (AD-3) means a copied token stays valid until natural expiry. Accepted given the
  closed-staff threat model. Not directly confirmed.
```

**Rationale:** FR-26 fills a genuine gap using the PRD's existing FR-numbering/consequences
convention (next sequential number, same testable-consequences shape as every other FR). The MVP
scope line and Assumptions Index are updated in the same pass so the document stays internally
consistent, matching the precedent Story 2.6's `correct-course` amendment set for Story 1.4's AC2.

### 4.2 Epics (`_bmad-output/planning-artifacts/epics.md`)

**FR Coverage Map — append**

```
FR-26: Epic 1 - User logout
```

**Epic 1 summary line**

```
OLD: **FRs covered:** FR-1, FR-2, FR-3
NEW: **FRs covered:** FR-1, FR-2, FR-3, FR-26
```

**New story, inserted after Story 1.6 (before the `## Epic 2` heading)**

```
### Story 1.7: User Logout

As a staff member,
I want to end my session,
So that I can sign out from a shared terminal when I'm done, or when handing it to the next person.

**Acceptance Criteria:**

**Given** an authenticated User
**When** they trigger logout
**Then** the httpOnly session cookie is cleared so the browser can no longer present it (FR-26)

**Given** a User has just logged out
**When** any subsequent non-login, non-health request is made from that browser
**Then** it is rejected as unauthorized, the same behavior Story 1.2/AD-3 already define for "no
valid session cookie" (FR-26, NFR-2)

**Given** the application shell (`AppShell`, Story 1.4)
**When** it renders for any authenticated Role
**Then** a "Sign Out" control is visible in the shared nav area, available uniformly to all four
Roles (FR-26, FR-2's Role-level model)

**Given** a User clicks Sign Out
**When** the logout request completes
**Then** the frontend clears its cached auth state (`useCurrentUser`) and redirects to `/login`

**Given** v1's stateless-JWT design has no server-side revocation store (AD-3, no refresh-token flow)
**When** a User logs out
**Then** only the client-side cookie is cleared; a token copied out before logout remains valid
until its natural 8-hour expiry if replayed, an accepted v1 limitation this story does not need to
close (FR-26)
```

**Rationale:** Mirrors Story 1.1's Given/When/Then shape and FR/AD citation style exactly. Placed in
Epic 1 alongside the other auth-lifecycle stories (1.1 login, 1.2 role auth) since it's the same
domain and the same `api/auth.py`/`AppShell` surfaces, even though Epic 1's other stories are already
`done` — this is additive, not a reopening of finished work.

### 4.3 Architecture

No AD changes. Adding a short implementation note is optional and can be left to the story's own Dev
Notes rather than amending `ARCHITECTURE-SPINE.md` — AD-3 already fully governs this (JWT in an
httpOnly cookie); a logout route is a normal consumer of that existing rule, not a new architectural
decision.

### 4.4 UI/UX

No mockup file changes needed (none of the 13 `.html` mockups model the nav bar's exact contents down
to individual controls). The story's own Dev Notes should state: "Sign Out" control lives in
`AppShell`'s existing nav area, next to the current user-identity/theme-toggle cluster, rendered
identically for all four Roles — consistent with every other shared-shell element in this codebase.

## 5. Implementation Handoff

**Scope classification: Minor.** One new backend route extending an existing router
(`api/auth.py`), one new frontend control extending an existing component (`AppShell`) and service
(`authService.ts`). No schema change, no new pattern, no cross-cutting architectural decision.

**Routed to:** Developer agent, via the normal `bmad-create-story` → `bmad-dev-story` →
`bmad-code-review` cycle, same as every story this session.

**Deliverables of this proposal:**
- PRD updated with FR-26 (§4.1, §6.1, §9)
- `epics.md` updated with Story 1.7 and Epic 1's FR-coverage line
- `sprint-status.yaml` updated with `1-7-user-logout: backlog`

**Success criteria:** `bmad-create-story` can discover Story 1.7 from `sprint-status.yaml` exactly
the way it discovers any other backlog story, with no special-casing.
