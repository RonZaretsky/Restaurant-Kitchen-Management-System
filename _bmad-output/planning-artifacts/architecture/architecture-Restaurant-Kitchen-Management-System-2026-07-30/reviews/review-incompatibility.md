# Adversarial Incompatibility Review — ARCHITECTURE-SPINE.md

**Method:** for every AD (and the Consistency Conventions table), assume two developers/agents each build a different epic/story, each obeying the letter of every AD, in isolation from each other. Try to construct a concrete scenario where their outputs still don't interoperate. Only findings with a genuine constructed scenario are reported; things that "feel underspecified" but don't produce an actual clash are excluded.

**Verdict:** The spine is tight on structural/layering concerns (AD-1, AD-3, AD-5, AD-9 wording, AD-12, AD-13) — those hold up under attack. It has real, concrete holes in four places: (1) a transaction-ordering race between AD-6 and AD-11 that can silently lose stock, (2) AD-2's event contract (name choice, payload shape, audience) is unfixed, so two features can legitimately diverge, (3) the `{"detail": string}` error envelope is contradicted by FastAPI's own default validation-error handler unless explicitly overridden, and (4) "ISO 8601 UTC" doesn't force timezone-aware serialization, which breaks JS date parsing inconsistently across features. Three more secondary gaps (AD-7 total-with-cancelled-items, AD-8 asymmetric enforcement, AD-9/AD-10 boundary under pagination) are real but lower-severity.

---

## Findings by severity

### F1 [HIGH] — AD-6 × AD-11: uncoordinated transactions can lose stock silently

**Binds attacked:** AD-6 (atomic stock deduction on `in_preparation`) and AD-11 (cancel/void compensating transaction), mediated by AD-5 (last-write-wins, no version column, on `OrderItem`).

**Construction:** Developer A builds "start preparation" (AD-6): reads `OrderItem.status`, and inside one DB transaction sets `status='in_preparation'`, decrements `Ingredient.current_stock`, inserts `StockMovement(consumption)`. Developer B builds "cancel/void" (AD-11): reads `OrderItem.status`; if it is *not yet* `in_preparation`, it just sets the terminal status (no compensating movement needed by AD-11's own rule — compensation only applies "if that item had already reached `in_preparation`"). Both transactions are individually atomic, and each developer followed their AD to the letter.

Now interleave them (no AD anywhere mandates row-level locking — `SELECT ... FOR UPDATE` — and AD-5 explicitly rules out a version column for `OrderItem`, i.e. explicitly sanctions "no conflict detection" for exactly this field):

1. T2 (cancel) reads `status = 'pending'` → concludes no compensating movement is needed.
2. T1 (start-prep) begins, sets `status='in_preparation'`, decrements stock, inserts `StockMovement(consumption)`, commits.
3. T2 finishes its transaction and commits: `status='cancelled'` (last-write-wins per AD-5 — no check against T1's write).

Result: the item ends up `cancelled`, stock was decremented, and no compensating `StockMovement` was ever inserted, because T2's compensation check ran against a pre-T1 snapshot. This is exactly the state AD-11 says it "prevents" ("one that leaves already-deducted stock unreturned") — reached even though both developers implemented their own AD correctly. AD-6 and AD-11 each guarantee atomicity *within* their own transaction; neither AD (nor AD-5) says anything about serializing the two transactions *against each other* for the same `OrderItem` row.

**Why AD-5 doesn't cover this:** AD-5 legitimizes "last write wins" for `OrderItem` edits in general (UI convenience for concurrent editing), but AD-6 says its stock guarantee is "stricter than AD-5 and is never weakened by it" — yet nothing operationalizes that strictness against a *concurrent, different* transaction touching the same row. The spine asserts precedence without a locking mechanism to enforce it.

---

### F2 [HIGH] — AD-2 fixes transport but not the event contract

**Binds attacked:** AD-2, cross-checked against the Consistency Conventions naming row and AD-13's `setQueryData`/`invalidateQueries`.

**Construction:** Two features both need to notify clients that an `OrderItem`'s status changed: the "kitchen board" feature (Cook-facing) and the "order/table status" feature (Waiter-facing). AD-2 only fixes *how* the push happens (one WS endpoint) and the naming convention fixes *lexical shape* (`{domain}.{event}`, past-tense). Nothing fixes:

- **Which domain owns the event.** Developer A (kitchen board) emits `kitchen.item_status_changed`; Developer B (order status) emits `order.item_status_changed` — for the *same* underlying `OrderItem` transition. Both strings are individually valid under the naming convention. A frontend subscriber built against one name never sees updates driven by the other feature, so the kitchen board and the waiter's order view can silently drift out of sync with each other after a single write.
- **Payload shape.** Nothing says whether the event carries just an ID (client refetches), the changed `OrderItem`, or the whole parent `Order` with nested items. Two `setQueryData` handlers built against different payload assumptions either crash on `undefined` fields or silently write partial/stale data into the TanStack Query cache.
- **Audience/scoping.** AD-2 says "one WebSocket endpoint per authenticated session" but not whether the backend filters by role/subscription before pushing, or broadcasts everything and expects client-side filtering. A Cook's browser may receive Waiter-only events (or vice versa); whether that's harmless or breaks something depends entirely on whichever developer's handler logic runs on whatever it receives.

This is a real gap, not a stylistic nit: the naming convention constrains spelling, not ownership, shape, or audience, and two compliant developers can produce events that don't compose.

---

### F3 [HIGH] — `{"detail": string}` envelope is contradicted by FastAPI's own default behavior

**Binds attacked:** Consistency Conventions → "Data & formats" row: *"Errors: FastAPI `HTTPException` / registered exception handlers, always shaped `{"detail": string}` — one error shape, handled once on the frontend."*

**Construction:** Developer A builds a route whose only error paths are custom domain exceptions from `backend/exceptions/`, mapped by an app-level handler to `{"detail": "<message>"}` — fully compliant. Developer B builds a different route relying on FastAPI's default request-body validation (a Pydantic model on the request, no manual check) — also fully compliant with every AD, since nothing in the spine says validation must be hand-rolled instead of relying on FastAPI/Pydantic.

FastAPI's *default* handler for `RequestValidationError` (422s from Pydantic parsing a malformed/missing field) does **not** produce `{"detail": string}`. It produces:
```json
{"detail": [{"loc": ["body", "quantity"], "msg": "field required", "type": "missing"}]}
```
i.e. `detail` is a **list of objects**, not a string. Unless someone explicitly overrides `RequestValidationError`'s handler app-wide (which no AD mandates — AD-1/table only requires *custom* exception types be mapped by handlers), Developer B's route emits a shape that violates the stated single envelope. The frontend's "one error shape, handled once" (AD-13's error handling implicitly assumes this) then either renders `[object Object]`/crashes on validation errors from Developer B's route while working fine on Developer A's, or someone downstream has to special-case it — precisely the divergence the convention claims to prevent. The spine never states "override FastAPI's default validation exception handler to conform," so this isn't a matter of someone breaking a rule; it's a rule with a known counterexample baked into the framework's defaults.

---

### F4 [MEDIUM-HIGH] — "ISO 8601 UTC" doesn't force timezone-aware datetimes

**Binds attacked:** Consistency Conventions → "Data & formats" row: *"Timestamps: ISO 8601 UTC."*

**Construction:** Developer A writes `created_at = datetime.utcnow()` (naive, no tzinfo) for `OrderItem` timestamps. Developer B writes `created_at = datetime.now(timezone.utc)` (aware) for `StockMovement` timestamps. Both are "UTC," both serialize via Pydantic to ISO-8601-looking strings, and both developers can honestly claim compliance with "Timestamps: ISO 8601 UTC." But Pydantic's default JSON encoding differs:

- Naive: `"2026-07-30T12:00:00"` — no offset.
- Aware: `"2026-07-30T12:00:00+00:00"` — explicit UTC offset.

On the frontend, `new Date("2026-07-30T12:00:00")` is parsed as **local browser time**, while `new Date("2026-07-30T12:00:00+00:00")` is parsed as **UTC**. A shared "relative time" or "elapsed since" component consuming both fields (e.g. showing "started 4 min ago" on the kitchen board using `OrderItem.created_at`, and a stock-movement audit log using `StockMovement.created_at`) will be silently wrong by the user's UTC offset for one of the two, with no error raised anywhere. The convention names a format family ("ISO 8601") broad enough to admit both the broken and correct serializations.

---

### F5 [MEDIUM] — AD-7 doesn't say whether cancelled/void `OrderItem`s count toward `Order.total_amount`

**Binds attacked:** AD-7 ("Order totals are always computed by summing stored `price_at_add × quantity`") vs AD-11 (cancel/void as a terminal status, row never deleted).

**Construction:** Developer A builds the order-total computation per AD-7's literal text — sum `price_at_add × quantity` over an Order's `OrderItem`s. AD-7 says nothing about excluding any status, so summing over *all* rows (including `cancelled`/`void`) is a literal, compliant reading. Developer B, building the checkout/receipt view, assumes — reasonably, since AD-11 preserves cancelled rows only for audit/stock-integrity reasons — that a cancelled item shouldn't be billed, and filters `status != 'cancelled'` before summing. Both are defensible readings of AD-7 in light of AD-11, and they produce two different totals for the same Order (one includes voided items in the bill, one doesn't) depending on which component/route computed it. AD-7 fixes *what price* to use, not *which rows* to include post-cancellation.

---

### F6 [MEDIUM] — AD-8 only binds the "turn availability on" transition, not "recipe shrinks to zero while already on"

**Binds attacked:** AD-8 ("the service layer rejects setting `Dish.is_available = true` while that Dish has zero `RecipeIngredient` rows").

**Construction:** Developer A builds the dish-availability toggle exactly as AD-8 specifies: blocks `is_available = true` when `RecipeIngredient` count is 0. Developer B, working a completely different epic (recipe/inventory management), builds "delete recipe ingredient line." AD-8's rule text binds only the availability-toggle transition; it imposes no obligation on the recipe-editing endpoint to check or cascade `is_available` when a deletion drops the ingredient count to zero. If a Waiter/Admin deletes the last `RecipeIngredient` row of a Dish that is *already* `is_available = true`, the system reaches exactly the state AD-8's "Prevents" clause names — "a live, orderable Dish whose stock deduction is silently a no-op" — via a code path AD-8 never touches, with both developers fully compliant with what their respective AD literally says.

---

### F7 [MEDIUM] — AD-9/AD-10 boundary ("ordering, not filtering") has no enforcement mechanism and no defined data contract

**Binds attacked:** AD-9 (role-level-only, no ownership filtering) vs AD-10 ("current-Cook-first ordering... is a UI default, not a query-level access filter").

**Construction:** AD-10 requires the frontend to show "current-Cook-first" ordering for `AIChatSession`/`AIRecipeSuggestion` lists. There are exactly two ways to implement "ordering" honestly: (a) the backend returns the full unfiltered list (AD-9-compliant) and the frontend sorts client-side, which requires the list response to actually carry an owner/`cook_id` field to sort by — nothing in the spine guarantees that field is present on the list endpoint's schema; or (b) the backend accepts a "current user" hint and does the ordering server-side (e.g. for pagination efficiency at scale), which requires the query to branch on `user.id` — the exact shape of logic AD-9 forbids as "per-resource/per-user filtering." Developer A (backend), reading AD-9 conservatively, builds a plain list endpoint with no user-aware parameter of any kind and no guaranteed owner field in the response (nothing requires it — AD-9 says results aren't filtered by ownership, which a minimal schema also satisfies). Developer B (frontend), needing to satisfy AD-10's UI-default requirement, has no way to fulfill it against Developer A's endpoint: no per-item owner field to sort on client-side, and no server-side "mine-first" parameter available because AD-9 was read as forbidding any user-aware branching in the query at all. Both developers are individually AD-compliant; together they cannot build AD-10's required behavior. The spine states the *legal* distinction ("ordering, not filtering") but never anchors it to a concrete API contract (e.g. "list responses include the owner id; ordering happens client-side"), so nothing stops it collapsing into either under-implementation (B above) or over-implementation (a dev builds `order_by=mine_first&user_id=` server-side and later someone turns it into pagination that only ever surfaces the first page — de facto filtering by ownership, in spirit if not in the letter of AD-9).

---

### F8 [LOW-MEDIUM] — AD-4 doesn't prevent Alembic multi-head conflicts across parallel stories

**Binds attacked:** AD-4 ("every `data_models/` change ships with an Alembic migration generated against the async template").

**Construction:** This is the textbook Alembic failure mode, and the spine's own premise (independently-built epics, "potentially built by different people or agents") makes it likely rather than hypothetical. Developer A and Developer B both branch off the same merged head, each adds a `data_models/` change, each dutifully runs `alembic revision --autogenerate` per AD-4 — each producing a migration whose `down_revision` points at the same prior head. Both individually satisfy AD-4 ("every change ships with a migration"). Whichever branch merges second now has two migrations claiming the same parent — two heads — and `alembic upgrade head` fails (or is ambiguous) until someone manually inserts a merge migration. AD-4 mandates *that* a migration exists per change; it says nothing about generating against the latest integrated head or a rebase/merge-migration convention, so nothing in the spine prevents two AD-4-compliant developers from producing a broken combined migration history.

---

## Findings judged NOT to hold up (attacked and rejected)

For completeness — these were attacked and did not produce a genuine incompatibility, only surface-level "feels vague":

- **AD-1's DI wiring rule** ("routes call only `services/`; lifecycle resources are `providers.Resource`") is tight enough that a route bypassing `services/` to inject a `clients/`/DB resource directly would violate AD-1's own text, not slip through a gap between two compliant readings.
- **AD-3's auth dependency** is safe from two-developer divergence because there is exactly one shared FastAPI dependency and (per AD-2) exactly one WebSocket endpoint — subsequent features consume, not redefine, either.
- **AD-12's client interface** — two features needing different AI operations (chat vs. recipe generation) naturally add different methods to the same interface; this is additive, not a clash.
- **IDs (auto-increment integers) and Config (`config.yaml`/`config.ts`)** rows in the Consistency Conventions table are concrete enough (single mechanism named) that no two compliant implementations diverge.
