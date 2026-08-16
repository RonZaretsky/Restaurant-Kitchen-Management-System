# Sprint Change Proposal — 2026-08-16

## 1. Issue Summary

Manual testing of Story 5.2 (Pick Up and Progress an Order Item) surfaced a gap: a Waiter cancelling
an Order Item does not update a Cook's already-open Kitchen Display. The item lingers, apparently
still active, until something else happens to trigger a refetch (in practice, the browser tab losing
and regaining focus, which silently re-triggers TanStack Query's default `refetchOnWindowFocus`).

Root cause, confirmed by reading the code: `OrderService.cancel_item` and `OrderService.edit_item`
(Story 3.4) never call `realtime_service.broadcast(...)`. This was a deliberate, correct decision at
the time — no live-consuming screen existed yet for either method to reach. Stories 5.1 and 5.2 then
made the Kitchen Display a live, always-foregrounded second consumer of Order Item state (explicitly
described in Story 5.1's own docs as "a screen meant to stay foregrounded for a whole shift"), and
Story 5.2 added the `order.item_status_changed` broadcast for pick-up/mark-ready — but nobody revisited
cancel/edit's silence once that second live consumer existed.

This is **not new scope**. NFR-1 (already approved) reads: *"An Order Item status change (creation or
transition) is visible on the relevant other Role's screen... within 2 seconds, with no manual
refresh required."* Cancelling and editing are both transitions on the Order Item; the code currently
does not satisfy NFR-1 for either.

## 2. Impact Analysis

- **Epic impact**: Epic 5 (Kitchen Fulfillment) gains one additional story to close this gap. No
  change to Epic 5's existing stories (5.1–5.4) or their acceptance criteria. Epic 3 (Table Service &
  Order Taking), which owns `edit_item`/`cancel_item`, is unaffected structurally — only its
  underlying service methods gain a broadcast call, no new Epic 3 story, no AC change there either.
- **Story impact**: None of the already-`done` stories need their own ACs amended — this is a gap the
  code review process at the time correctly scoped out (no AC asked for live update on cancel/edit),
  not a defect against any existing AC. No future story (5.3/5.4) depends on or conflicts with this
  fix.
- **Artifact conflicts**: None. No PRD text needs to change — NFR-1 already covers this case, it was
  simply not yet implemented for these two transitions. No architecture/UX document conflict: the fix
  reuses the existing WebSocket transport (AD-2) and the existing `order.item_status_changed` event
  name/payload shape/recipients Story 5.2 already established.
- **Technical impact**: Backend-only change (two `broadcast()` calls added to already-existing guarded
  methods). No new endpoint, no new event name, no schema change, no migration. Frontend needs no
  changes at all — `KitchenDisplayPage.tsx` and `TableOrderDetailPage.tsx` already subscribe to
  `order.item_status_changed` and just invalidate-and-refetch on receipt, regardless of which
  transition triggered it.

## 3. Recommended Approach

**Option 1: Direct Adjustment.** Add a new story to Epic 5 (Story 5.5) that widens `cancel_item` and
`edit_item` to broadcast the existing `order.item_status_changed` event, the same one `pick_up_item`/
`mark_item_ready` already use.

- Effort: **Low** — two broadcast calls added to already-existing, already-guarded methods; the event
  shape, recipients, and every consumer already exist.
- Risk: **Low** — purely additive (a new broadcast call, no behavior change to the guarded transition
  logic itself); the two consumer pages already handle this event generically.

Options 2 (rollback) and 3 (MVP review) were not seriously in play — there is nothing to roll back
(the gap predates all of Epic 5, going back to Story 3.4) and no MVP scope question (NFR-1 already
covers this, so closing the gap is completing already-approved scope, not adding new scope).

## 4. Detailed Change Proposal

### Epic 5 (`epics.md`)

```
### Story 5.5: Live-Update the Kitchen Display and Waiter Screen on Cancel/Edit

As a Cook or Waiter,
I want a cancelled or edited Order Item to update my screen live,
So that I never act on a stale item after someone else has already changed it.

**Acceptance Criteria:**

**Given** a pending or in_preparation Order Item is cancelled
**When** the cancellation commits
**Then** the same `order.item_status_changed` event Story 5.2 introduced is broadcast to
[waiter, cook], and both the Kitchen Display and the Waiter's own Table/Order Detail page reflect
the cancellation within 2 seconds, with no manual refresh (NFR-1)

**Given** a pending Order Item's quantity or note is edited
**When** the edit commits
**Then** the same event is broadcast, and both screens reflect the change within 2 seconds, with no
manual refresh (NFR-1)

**Given** a Kitchen Display that has stayed foregrounded for an extended period
**When** another Role cancels or edits an item shown on it
**Then** the display updates without requiring a tab switch, window refocus, or manual reload
```

Placed after Story 5.4 (numbered 5.5) since it is not on the critical path of the core
pick-up→ready→served→close loop 5.1–5.4 build; it is a live-consistency fix that became necessary
once that loop's live screens existed. No renumbering of 5.1–5.4 needed.

### PRD

No change. NFR-1 already states the requirement this story implements; no new FR is introduced.

## 5. Implementation Handoff

**Scope: Minor.** Route directly to the Developer agent via the existing `create-story` →
`dev-story` → `code-review` pipeline, the same flow every other story in this project has used.
No PO/Architect/PM involvement needed — this is a same-shape extension of Story 5.2's own, already
-built broadcast pattern, not a new pattern or a scope negotiation.

**Success criteria**: `cancel_item` and `edit_item` broadcast `order.item_status_changed` after their
own commit succeeds (matching `pick_up_item`/`mark_item_ready`'s existing placement and recipients);
both `KitchenDisplayPage.tsx` and `TableOrderDetailPage.tsx` reflect a cancel/edit from another
session within 2 seconds with no manual refresh; regression tests confirm `edit_item`/`cancel_item`
now broadcast (flipping the standing negative test noted in `deferred-work.md`'s story-3-4 entry,
which explicitly anticipated this).
