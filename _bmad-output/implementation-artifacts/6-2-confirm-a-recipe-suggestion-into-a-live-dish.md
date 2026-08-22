---
baseline_commit: 8eef9c84e3efee959eee2cc96aa2ecb772dd6eb1
epic: 6
story: 2
---

# Story 6.2: Confirm a Recipe Suggestion into a Live Dish

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Admin,
I want to confirm a promising Recipe Suggestion into a real, orderable Dish,
so that Smart Chef's ideas can actually reach the menu under human review.

## Scope note (read first)

**There is no separate "Recipe" entity in this schema** — a Dish's recipe is the set of
`RecipeIngredient` rows keyed by `dish_id` (a composite-primary-key bridge table with no `id`
column of its own, see `backend/data_models/recipe.py`). The epics AC's "the resulting Recipe
stores a nullable back-reference" therefore cannot mean a `RecipeIngredient` row — there is no
single row representing "the recipe" as a whole. **The nullable provenance link belongs on
`Dish`** (`Dish.source_suggestion_id`, nullable FK to `ai_recipe_suggestions.id`): one Dish has at
most one originating suggestion, which is exactly the cardinality FR-19 describes.

**"Confirmed" is a derived state, not a stored one — matching this codebase's own established
pattern** (Low-Stock Alerts, Story 5.3's `Order.status`). A Recipe Suggestion is confirmed **if
and only if** some `Dish` row has `source_suggestion_id` equal to its id. There is no
`confirmed`/`status` column to add, and no separate "mark confirmed" mutation to build — the only
way a suggestion becomes confirmed is a real Dish actually being created (or updated) with that
back-reference, via the **existing, unchanged** `create_dish`/`update_dish` flow. This is also
exactly how AC2 ("no code path allows it to write directly to Dish/Recipe tables outside that
Admin-driven flow") gets satisfied structurally: there is no second write path to satisfy or
bypass, because confirming *is* calling the same `POST /api/menu/dishes` (or `PATCH .../{id}`)
every other Dish creation/edit already uses, now optionally carrying one more field.

**`dismissed` is the one genuinely new, stored column** (epics' own last AC is explicit that it
needs its own Alembic migration on top of the Story 1.0 baseline, AD-4) — a simple, independent
boolean on `AIRecipeSuggestion`, defaulting to `False`. Dismissing and confirming are mutually
exclusive but not enforced against each other at the DB level beyond normal application logic: a
dismissed suggestion should not also be confirmable (guard it), and a confirmed one should not
also be dismissible (guard it) — both are plain business-rule checks in `AIService`, not schema
constraints.

**"Confirm into Dish" is a hand-off to the existing Menu Management page, not a new one-shot
backend action.** The AI's `generated_recipe` JSON has no `category_id` or `price` (Dish's two
required-but-AI-unknowable fields), and its `ingredients` are free-text names/quantities, not
validated `Ingredient` ids + `Unit`s the way `RecipeIngredient` requires (`UnitMismatchError`
already guards this elsewhere) — there is no safe way to auto-create a complete, valid Dish+Recipe
from AI output alone. The Admin must still choose a category and price, and must still map each
suggested ingredient to a real `Ingredient` record with a real quantity/unit, **exactly the same
manual steps every other new Dish already requires**. "Confirm into Dish" therefore means: clicking
it navigates to `/admin/menu` with the suggestion's `name` and a description built from its
`plating` text pre-filled into the **existing** create-Dish form (via React Router's
`navigate(path, { state })`, read once on mount — ephemeral hand-off data, not a URL param meant to
be bookmarked or shared), plus the `source_suggestion_id` carried invisibly so the eventual
`POST /api/menu/dishes` call includes it. The Admin still fills in category/price and still adds
Recipe Ingredient lines afterward exactly as they already do today — **no change to
`add_recipe_ingredient`/`MenuManagementPage.tsx`'s recipe-ingredient UI at all.**

**What this story does NOT include:** no chat UI (`AIChatSession`/`AIChatMessage`, Story 6.3's
scope, still untouched). No change to `SmartChefPage.tsx`'s own generation flow (Story 6.1) beyond
whatever the shared `AIRecipeSuggestionResponse` shape gains (see Task 3) — a Cook's own page must
still show no Confirm/Dismiss actions, those remain Admin-only, rendered only on
`RecipeSuggestionsPage.tsx`.

## Acceptance Criteria

1. **Given** a Recipe Suggestion, **when** an Admin confirms it, **then** a Dish and Recipe are
   created or updated via Epic 2's normal Menu Management flow, and the resulting Dish stores a
   nullable back-reference to the originating Recipe Suggestion (FR-19).
2. **Given** a Recipe Suggestion is confirmed, **when** the confirmation happens, **then** no code
   path allows it to write directly to the Dish/Recipe tables outside that Admin-driven flow
   (FR-19).
3. **Given** a manually-defined Recipe not sourced from a suggestion, **when** its provenance is
   checked, **then** the reference is null (FR-19).
4. **Given** a Recipe Suggestion, **when** an Admin dismisses it instead of confirming, **then** it
   is marked with a persisted `dismissed` status, leaving the active Recipe Suggestions list but
   retained for audit (UX-DR20).
5. **Given** a Recipe Suggestion card on the Admin's review surface, **when** it renders, **then**
   it offers exactly two actions, Confirm into Dish (accent primary button) and Dismiss (outlined/
   text button).
6. **Given** no suggestions awaiting review, **when** the surface loads, **then** it shows "No
   suggestions awaiting review" (UX-DR15).
7. **Given** `dismissed` does not yet exist as a column on `AIRecipeSuggestion`, **when** this
   story adds it, **then** it ships with its own Alembic migration on top of the baseline
   established in Story 1.0, per AD-4.

## Tasks / Subtasks

- [ ] **Task 1: Backend — `Dish.source_suggestion_id` + `AIRecipeSuggestion.dismissed` (AC1, AC3,
  AC4, AC7)**
  - [ ] `backend/data_models/menu.py`: add `source_suggestion_id: Mapped[int | None] =
    mapped_column(Integer, ForeignKey("ai_recipe_suggestions.id"), nullable=True)` to `Dish`.
    Nullable, no default needed beyond `None` (AC3: a manually-defined Dish's reference is null by
    construction, nothing to enforce).
  - [ ] `backend/data_models/ai.py`: add `dismissed: Mapped[bool] = mapped_column(Boolean,
    nullable=False, default=False)` to `AIRecipeSuggestion`.
  - [ ] Generate the Alembic revision: `uv run alembic revision --autogenerate -m "add dish
    source_suggestion_id and ai_recipe_suggestions dismissed"` (AC7, AD-4). **Inspect the
    generated script before committing** — confirm it only adds the one column + one FK per table,
    no unrelated autogenerate noise, matching trap 22's "a nullable-with-no-default column add
    doesn't break existing rows" lesson (both new columns here are nullable or have a plain
    default, so no backfill step is needed, but verify the generated script doesn't add a
    server-side default that would).
  - [ ] `DishResponse` (`data_models/menu.py`) gains `source_suggestion_id: int | None`.
  - [ ] `AIRecipeSuggestionResponse` (`data_models/ai.py`) gains `dismissed: bool` and
    `confirmed_dish_id: int | None` (the derived-confirmation signal the frontend filters on — see
    Task 3).

- [ ] **Task 2: Backend — `CreateDishRequest` gains `source_suggestion_id` (AC1, AC2)**
  - [ ] `backend/data_models/menu.py`: add `source_suggestion_id: int | None = Field(default=None,
    gt=0, le=_INT4_MAX)` to `CreateDishRequest`. Optional, defaults to `None` — every existing
    manual Dish-creation call site is unaffected (AC3).
  - [ ] `backend/services/menu_service.py::create_dish`: when `payload.source_suggestion_id` is
    provided, validate before inserting: the suggestion exists (`SuggestionNotFoundError`, 404, new
    exception type mirroring `DishNotFoundError`'s shape); it is not `dismissed`
    (`SuggestionAlreadyDismissedError`, 409, new); and no other Dish already references it
    (`SuggestionAlreadyConfirmedError`, 409, new — query `select(Dish).where(Dish.
    source_suggestion_id == payload.source_suggestion_id)`, reject if any row exists). Only after
    all three checks pass, set `dish.source_suggestion_id = payload.source_suggestion_id` on the
    same insert already in progress — **do not** add a second commit or a second code path; this
    is one more field on the existing insert, not a new method.
  - [ ] No change to `update_dish` for this story — epics AC1 says "created or updated," but
    nothing in this story's own UX flow ever confirms into an *existing* Dish (Confirm into Dish
    always creates a new one via the create form); leave `update_dish` unable to set
    `source_suggestion_id` for now, there is no caller that would use it and no AC that requires it
    — do not speculatively add an unused parameter.

- [ ] **Task 3: Backend — `AIService` dismiss + confirmed-status derivation (AC4, AC6)**
  - [ ] `backend/services/ai_service.py`: new `async def dismiss_suggestion(self, db: AsyncSession,
    actor: User, suggestion_id: int) -> AIRecipeSuggestion`. Fetch the suggestion
    (`SuggestionNotFoundError` if missing, reusing Task 2's new exception type). Reject if already
    `dismissed` (`SuggestionAlreadyDismissedError`) or already confirmed (has a referencing Dish,
    `SuggestionAlreadyConfirmedError`) — the same two guards Task 2's `create_dish` path checks,
    now checked here in the opposite direction. Set `dismissed = True`, commit, refresh, log at
    `INFO`, return it.
  - [ ] `list_suggestions`: extend the query to a `LEFT JOIN Dish ON Dish.source_suggestion_id ==
    AIRecipeSuggestion.id`, selecting `Dish.id` alongside each suggestion row (`select(
    AIRecipeSuggestion, Dish.id).outerjoin(...)`), so the response can carry `confirmed_dish_id`
    without a second per-row query (N+1). No `dismissed` filter here — same as Story 6.1's own
    reasoning, this method still returns every suggestion; filtering "awaiting review" (not
    dismissed, not confirmed) happens client-side (AC6), matching AD-9's established
    client-side-filter convention and Story 6.1's own "no dismissed filter, that's this story's job"
    note.

- [ ] **Task 4: Backend — new exception types** (AC1, AC2, AC4)
  - [ ] `backend/exceptions/__init__.py`: `SuggestionNotFoundError(NotFoundError)`, detail
    `"Recipe suggestion not found"`. `SuggestionAlreadyDismissedError(ConflictError)`, detail
    `"Rejected, suggestion is already dismissed"`. `SuggestionAlreadyConfirmedError(ConflictError)`,
    detail `"Rejected, suggestion is already confirmed"`. No new handler needed — all three
    subclass an existing family (`NotFoundError`/`ConflictError`), already handled.

- [ ] **Task 5: Backend — `POST /api/smart-chef/suggestions/{id}/dismiss`** (AC4)
  - [ ] `backend/api/smart_chef.py`: new `SmartChefAdminDep = Annotated[User,
    Depends(require_role(UserRole.admin))]` (dismissing is Admin-only, distinct from the existing
    Cook-only `SmartChefWriteDep` and the Cook+Admin `SmartChefReadDep`).
  - [ ] `@router.post("/suggestions/{suggestion_id}/dismiss", response_model=
    AIRecipeSuggestionResponse)`, calling `ai_service.dismiss_suggestion(db, actor,
    suggestion_id)`. New `_DISMISS_ERROR_DESCRIPTIONS` dict (401/403, 404 "no matching suggestion",
    409 "already dismissed or already confirmed"), following this file's existing per-route dict
    convention.

- [ ] **Task 6: Backend tests** (`backend/tests/test_ai.py`, extend; `backend/tests/test_menu.py`,
  extend if it exists — check the file list first)
  - [ ] AC1/AC3: creating a Dish with `source_suggestion_id` persists the back-reference; creating
    a Dish without it (every existing call site) leaves it `None`.
  - [ ] AC1/AC2: confirming a suggestion (`POST /api/menu/dishes` with `source_suggestion_id` set)
    is the *only* path exercised — no new endpoint bypasses `create_dish`'s own validation
    (category existence, price bounds, etc. all still apply unchanged).
  - [ ] Confirming an already-confirmed suggestion (a second Dish citing the same
    `source_suggestion_id`) is rejected with 409.
  - [ ] Confirming a dismissed suggestion is rejected with 409.
  - [ ] Confirming a nonexistent `source_suggestion_id` is rejected with 404.
  - [ ] AC4: dismissing a suggestion sets `dismissed = True`; dismissing an already-dismissed one
    is rejected with 409; dismissing an already-confirmed one is rejected with 409; dismissing a
    nonexistent id is rejected with 404.
  - [ ] `GET /api/smart-chef/suggestions` includes `dismissed` and `confirmed_dish_id` (null when
    neither, the real Dish id once confirmed) in every row.
  - [ ] Role coverage for `POST .../dismiss`: cook, waiter, warehouse_manager all 403 (Admin-only,
    no Cook fallback — unlike the existing `SmartChefReadDep`); unauthenticated 401.

- [ ] **Task 7: Frontend — `smartChefService.ts` gains dismiss** (AC4)
  - [ ] New `useDismissSuggestion(): UseMutationResult<AIRecipeSuggestion, Error, number>`, `POST
    /api/smart-chef/suggestions/${id}/dismiss`, invalidating `SUGGESTIONS_QUERY_KEY` on settle
    (matches `useGenerateSuggestion`'s own "invalidate on settle" reasoning — a 409 means the
    client's view of this suggestion's state is already stale).
  - [ ] `frontend/src/types/ai.ts`: `AIRecipeSuggestion` gains `dismissed: boolean` and
    `confirmed_dish_id: number | null`.

- [ ] **Task 8: Frontend — `menuService.ts`/`types/menu.ts`** (AC1)
  - [ ] `CreateDishPayload` (or wherever the create-Dish request type lives) gains
    `source_suggestion_id?: number` — optional, every existing call site unaffected.

- [ ] **Task 9: Frontend — `RecipeSuggestionsPage.tsx`** (AC4, AC5, AC6)
  - [ ] Replace the placeholder. Fetch `useSuggestions()` (Story 6.1's existing hook, already
    Admin-accessible via `SmartChefReadDep`), filter client-side to "awaiting review": `!dismissed
    && confirmed_dish_id === null` (AD-9's client-side-filter convention — no new backend query
    param).
  - [ ] Each card (reusing the same content layout `SmartChefPage.tsx`'s `SuggestionCard`
    establishes — name, ingredients drawn on, plating; consider extracting a shared component if
    the dev agent judges the duplication significant, dev agent's call) additionally renders two
    actions this story adds: **Confirm into Dish** (`variant="contained"`, the accent-primary
    button) and **Dismiss** (`variant="outlined"`).
  - [ ] Confirm into Dish: `navigate("/admin/menu", { state: { prefillName:
    suggestion.generated_recipe.name, prefillDescription: suggestion.generated_recipe.plating,
    sourceSuggestionId: suggestion.id } })`.
  - [ ] Dismiss: calls `useDismissSuggestion().mutate(suggestion.id)` directly, no confirm step (no
    AC asks for one here, and losing a suggestion to dismissal is reversible in spirit — the row is
    retained for audit per AC4 itself, matching the "no confirm unless it's a data-loss risk"
    convention `close_order`/`mark_served` already established, though dev agent should re-check
    this against `UX-DR11`'s referenced wording if more specific guidance is found there).
  - [ ] Empty state: "No suggestions awaiting review." (AC6, exact copy) when the filtered list is
    empty — even if `useSuggestions()`'s raw list is not (i.e. every suggestion is
    dismissed/confirmed already).

- [ ] **Task 10: Frontend — `MenuManagementPage.tsx` prefill** (AC1)
  - [ ] Read `useLocation().state` once on mount (a `useEffect` with an empty-ish dependency guard,
    or a `useState` lazy initializer reading `history.state`/`location.state` directly — dev
    agent's call on the exact React idiom, but it must only apply once, not re-prefill if the
    Admin clears the field and the component re-renders). If present, prefill `name`/`description`
    from `prefillName`/`prefillDescription`, and hold `sourceSuggestionId` in a new piece of state
    threaded into the existing `handleCreateDish`'s `createDishMutation.mutate({...,
    source_suggestion_id: sourceSuggestionId ?? undefined})` call.
  - [ ] No visible UI change beyond the pre-filled fields — the Admin still manually picks a
    category and confirms/edits the price exactly as they already do for any new Dish.

- [ ] **Task 11: Frontend tests**
  - [ ] `RecipeSuggestionsPage.test.tsx` (new): empty-state copy; a card renders Confirm/Dismiss
    (contrast with `SmartChefPage.test.tsx`'s own assertion that those buttons are *absent* there);
    clicking Confirm navigates to `/admin/menu` with the expected state payload; clicking Dismiss
    calls the dismiss endpoint; a dismissed or already-confirmed suggestion is excluded from the
    rendered list even though `useSuggestions()`'s raw response still includes it.
  - [ ] `MenuManagementPage.test.tsx` (extend): arriving with navigation state pre-fills
    name/description; submitting the create form in that state includes `source_suggestion_id` in
    the request body; arriving with no state behaves exactly as today (regression check).

- [ ] **Task 12: Full regression pass**
  - [ ] `uv run pytest -q` (backend) — zero regressions.
  - [ ] `pnpm test` (frontend) — zero regressions.
  - [ ] `npx tsc -b` — clean.

## Dev Notes

### Architecture compliance

- **AD-4** (every schema change ships its own Alembic revision): Task 1's migration, inspected
  before committing, per trap 22's lesson about nullable/no-default column adds being safe against
  existing rows.
- **FR-19** ("no code path allows it to write directly to Dish/Recipe tables outside that
  Admin-driven flow"): satisfied structurally, not by a runtime guard — there is only one Dish
  creation path (`MenuService.create_dish`), and this story adds one optional field to it rather
  than a second path.
- **AD-9** (Role-level-only permissions, client-side filtering over server-side query params):
  "awaiting review" filtering happens in `RecipeSuggestionsPage.tsx`, not as a new backend query
  parameter — matches `list_suggestions`'s own existing "no dismissed filter, returns everything"
  design from Story 6.1.

### Current state of the files this story touches (read before editing)

- **`backend/data_models/menu.py`**: `Dish` (no `source_suggestion_id` yet), `CreateDishRequest`/
  `DishResponse` (no `source_suggestion_id` field yet). `_INT4_MAX` already defined here, reused
  for the new field's bound, matching every other id-typed field in this file.
- **`backend/data_models/ai.py`**: `AIRecipeSuggestion` (no `dismissed` yet, Story 6.1's four
  original columns only). `AIRecipeSuggestionResponse` (Story 6.1) has no `dismissed`/
  `confirmed_dish_id` yet.
- **`backend/services/menu_service.py::create_dish`** (current, ~lines 117-152): a plain
  check-then-insert (category existence, then insert with `is_available=False` unconditionally,
  AD-8) — no guarded UPDATE, no row lock, matching `MenuService.add_recipe_ingredient`'s own
  established shape. This story adds one more validation branch (the three suggestion checks) and
  one more field on the same insert, no structural change to the method's shape.
  `update_dish` (~195-...) is read but NOT modified this story (see Task 2's own note).
- **`backend/services/ai_service.py`**: `generate_suggestion`/`list_suggestions` (Story 6.1) —
  `list_suggestions`'s current query is a bare `select(AIRecipeSuggestion).order_by(...)`, no join;
  this story adds the join. The in-process `_in_flight` concurrency guard (AD-14) is unrelated to
  and untouched by this story — dismiss/confirm have no concurrency-guard requirement of their
  own, nothing in the epics ACs asks for one.
- **`backend/api/smart_chef.py`**: `SmartChefWriteDep`/`SmartChefReadDep` (Story 6.1) — this story
  adds a third, `SmartChefAdminDep`, narrower than `SmartChefReadDep` (admin only, no cook).
- **`frontend/src/pages/admin/RecipeSuggestionsPage.tsx`**: currently a two-line placeholder
  (`<Typography>Recipe Suggestions</Typography>`), already correctly routed at
  `/admin/recipe-suggestions` and already in `ROLE_NAV_ITEMS.admin` — do not touch
  `router.tsx`/`navigationConfig.ts`.
- **`frontend/src/pages/admin/MenuManagementPage.tsx`**: the create-Dish form (~lines 96-169) uses
  plain `useState` fields (`name`, `description`, `price`, `categoryId`, `prepTime`) and
  `handleCreateDish`'s `createDishMutation.mutate({...})` call — this story adds a prefill read and
  one more field to that same mutate call, no change to the form's own validation
  (`canSubmitDish`) or its Category-creation reveal.
- **`frontend/src/pages/cook/SmartChefPage.tsx`**: `SuggestionCard` (Story 6.1) — read for its
  exact card-content layout (name, ingredients-drawn-on chips, plating) before deciding whether to
  extract a shared component for `RecipeSuggestionsPage.tsx`'s own cards (dev agent's call, Task
  9's own note).

### Project Structure Notes

Files touched:
- `backend/data_models/menu.py` — **UPDATE**, `Dish.source_suggestion_id`,
  `CreateDishRequest.source_suggestion_id`, `DishResponse.source_suggestion_id`.
- `backend/data_models/ai.py` — **UPDATE**, `AIRecipeSuggestion.dismissed`,
  `AIRecipeSuggestionResponse.dismissed`/`.confirmed_dish_id`.
- `backend/alembic/versions/` — **NEW** migration file (autogenerated, inspected before commit).
- `backend/services/menu_service.py` — **UPDATE**, `create_dish`'s new validation branch.
- `backend/services/ai_service.py` — **UPDATE**, `dismiss_suggestion` added,
  `list_suggestions`'s join.
- `backend/exceptions/__init__.py` — **UPDATE**, three new exception types (no new handlers).
- `backend/api/smart_chef.py` — **UPDATE**, new dismiss route + `SmartChefAdminDep`.
- `backend/tests/test_ai.py` (and/or `test_menu.py`) — **UPDATE**, new coverage.
- `frontend/src/services/smartChefService.ts` — **UPDATE**, `useDismissSuggestion` added.
- `frontend/src/services/menuService.ts` — **UPDATE**, `CreateDishPayload` gains the optional
  field.
- `frontend/src/types/ai.ts` — **UPDATE**, new response fields.
- `frontend/src/pages/admin/RecipeSuggestionsPage.tsx` — **UPDATE**, placeholder replaced.
- `frontend/src/pages/admin/RecipeSuggestionsPage.test.tsx` — **NEW**.
- `frontend/src/pages/admin/MenuManagementPage.tsx` — **UPDATE**, prefill-from-navigation-state.
- `frontend/src/pages/admin/MenuManagementPage.test.tsx` — **UPDATE**, new coverage.

No change to `router.tsx`/`navigationConfig.ts` (already correctly wired). No chat
endpoints/models (Story 6.3's scope).

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 6.2`] — this story's AC source,
  verbatim.
- [Source: `_bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md`,
  FR-19] — the full requirement text, including the confirmed decision that the provenance link is
  nullable and lives on the resulting Recipe/Dish.
- [Source: `_bmad-output/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md`, AD-4, AD-9] —
  the migration-per-schema-change rule and the client-side-filtering precedent this story reuses.
- [Source: `docs/database-schema.md`, `AIRecipeSuggestion`] — confirms no `status`/`dismissed`
  column exists yet, matching AC7's own premise.
- [Source: `backend/data_models/recipe.py::RecipeIngredient`] — confirms there is no singular
  "Recipe" row, the basis for this story's Scope note placing the provenance FK on `Dish` instead.
- [Source: `backend/services/menu_service.py::create_dish`, `::update_dish`] — the existing,
  unchanged (aside from one new optional field) Dish-creation flow this story's Confirm action
  reuses rather than bypasses (AC2).
- [Source: `_bmad-output/implementation-artifacts/6-1-generate-a-recipe-suggestion-from-current-stock.md`]
  — the previous story's `AIService`/`SmartChefWriteDep`/`SmartChefReadDep`/`_in_flight` guard
  this story extends without modifying its concurrency behavior.
- [Source: `_bmad-output/project-context.md`, trap 22, trap 23] — the nullable-column-add-is-safe
  lesson this story's migration follows, and the provider-declaration-ordering rule (not directly
  applicable here, no new container provider, noted for completeness).

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
