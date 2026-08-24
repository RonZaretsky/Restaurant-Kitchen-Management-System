---
baseline_commit: 8eef9c84e3efee959eee2cc96aa2ecb772dd6eb1
epic: 6
story: 2
---

# Story 6.2: Confirm a Recipe Suggestion into a Live Dish

Status: done

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

**"Confirm into Dish" is an in-place dialog on `RecipeSuggestionsPage.tsx`, not a hand-off to
Menu Management (revised post-manual-test-feedback — see Change Log).** The original design
navigated to `/admin/menu` with `name`/`description` pre-filled via router state, leaving the
Admin to separately re-add every Recipe Ingredient line by hand afterward; manual testing found
this an unacceptable extra step. The AI's `generated_recipe` JSON still has no `category_id` or
`price` (Dish's two required-but-AI-unknowable fields), and its `ingredients` are still free-text
names/quantities, not validated `Ingredient` ids + `Unit`s the way `RecipeIngredient` requires
(`UnitMismatchError` still guards this) — there remains no safe way to blindly auto-create a
complete, valid Dish+Recipe from AI output alone. Instead, `ConfirmSuggestionDialog.tsx` opens in
place and asks the Admin for exactly the fields AI output can't supply (category, price, prep
time), while **best-effort prefilling** each suggested ingredient's row via a case-insensitive
name match against the real Ingredient list (for the id + its fixed `unit`) and a parsed leading
numeric amount off the AI's free-text quantity string — every field stays editable, and an
unmatched/unparseable row is left blank rather than guessed. Confirming composes the two existing
endpoints already used everywhere else in this codebase: `POST /api/menu/dishes` (carrying
`source_suggestion_id`), then `POST /api/menu/dishes/{id}/recipe-ingredients` once per row — no
new backend action, `MenuService.create_dish`/`add_recipe_ingredient` remain the only paths for
either (AC2). A per-row `add_recipe_ingredient` failure (e.g. a genuine `UnitMismatchError`) does
not roll back the already-created Dish; it is reported inline, and the Admin can still finish that
line from Menu Management's existing recipe editor, matching how a Recipe Ingredient edit failure
is already surfaced everywhere else in this app.

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

- [x] **Task 1: Backend — `Dish.source_suggestion_id` + `AIRecipeSuggestion.dismissed` (AC1, AC3,
  AC4, AC7)**
  - [x] `backend/data_models/menu.py`: add `source_suggestion_id: Mapped[int | None] =
    mapped_column(Integer, ForeignKey("ai_recipe_suggestions.id"), nullable=True)` to `Dish`.
    Nullable, no default needed beyond `None` (AC3: a manually-defined Dish's reference is null by
    construction, nothing to enforce).
  - [x] `backend/data_models/ai.py`: add `dismissed: Mapped[bool] = mapped_column(Boolean,
    nullable=False, default=False)` to `AIRecipeSuggestion`.
  - [x] Generate the Alembic revision: `uv run alembic revision --autogenerate -m "add dish
    source_suggestion_id and ai_recipe_suggestions dismissed"` (AC7, AD-4). **Inspect the
    generated script before committing** — confirm it only adds the one column + one FK per table,
    no unrelated autogenerate noise, matching trap 22's "a nullable-with-no-default column add
    doesn't break existing rows" lesson (both new columns here are nullable or have a plain
    default, so no backfill step is needed, but verify the generated script doesn't add a
    server-side default that would).
  - [x] `DishResponse` (`data_models/menu.py`) gains `source_suggestion_id: int | None`.
  - [x] `AIRecipeSuggestionResponse` (`data_models/ai.py`) gains `dismissed: bool` and
    `confirmed_dish_id: int | None` (the derived-confirmation signal the frontend filters on — see
    Task 3).

- [x] **Task 2: Backend — `CreateDishRequest` gains `source_suggestion_id` (AC1, AC2)**
  - [x] `backend/data_models/menu.py`: add `source_suggestion_id: int | None = Field(default=None,
    gt=0, le=_INT4_MAX)` to `CreateDishRequest`. Optional, defaults to `None` — every existing
    manual Dish-creation call site is unaffected (AC3).
  - [x] `backend/services/menu_service.py::create_dish`: when `payload.source_suggestion_id` is
    provided, validate before inserting: the suggestion exists (`SuggestionNotFoundError`, 404, new
    exception type mirroring `DishNotFoundError`'s shape); it is not `dismissed`
    (`SuggestionAlreadyDismissedError`, 409, new); and no other Dish already references it
    (`SuggestionAlreadyConfirmedError`, 409, new — query `select(Dish).where(Dish.
    source_suggestion_id == payload.source_suggestion_id)`, reject if any row exists). Only after
    all three checks pass, set `dish.source_suggestion_id = payload.source_suggestion_id` on the
    same insert already in progress — **do not** add a second commit or a second code path; this
    is one more field on the existing insert, not a new method.
  - [x] No change to `update_dish` for this story — epics AC1 says "created or updated," but
    nothing in this story's own UX flow ever confirms into an *existing* Dish (Confirm into Dish
    always creates a new one via the create form); leave `update_dish` unable to set
    `source_suggestion_id` for now, there is no caller that would use it and no AC that requires it
    — do not speculatively add an unused parameter.

- [x] **Task 3: Backend — `AIService` dismiss + confirmed-status derivation (AC4, AC6)**
  - [x] `backend/services/ai_service.py`: new `async def dismiss_suggestion(self, db: AsyncSession,
    actor: User, suggestion_id: int) -> AIRecipeSuggestion`. Fetch the suggestion
    (`SuggestionNotFoundError` if missing, reusing Task 2's new exception type). Reject if already
    `dismissed` (`SuggestionAlreadyDismissedError`) or already confirmed (has a referencing Dish,
    `SuggestionAlreadyConfirmedError`) — the same two guards Task 2's `create_dish` path checks,
    now checked here in the opposite direction. Set `dismissed = True`, commit, refresh, log at
    `INFO`, return it.
  - [x] `list_suggestions`: extend the query to a `LEFT JOIN Dish ON Dish.source_suggestion_id ==
    AIRecipeSuggestion.id`, selecting `Dish.id` alongside each suggestion row (`select(
    AIRecipeSuggestion, Dish.id).outerjoin(...)`), so the response can carry `confirmed_dish_id`
    without a second per-row query (N+1). No `dismissed` filter here — same as Story 6.1's own
    reasoning, this method still returns every suggestion; filtering "awaiting review" (not
    dismissed, not confirmed) happens client-side (AC6), matching AD-9's established
    client-side-filter convention and Story 6.1's own "no dismissed filter, that's this story's job"
    note.

- [x] **Task 4: Backend — new exception types** (AC1, AC2, AC4)
  - [x] `backend/exceptions/__init__.py`: `SuggestionNotFoundError(NotFoundError)`, detail
    `"Recipe suggestion not found"`. `SuggestionAlreadyDismissedError(ConflictError)`, detail
    `"Rejected, suggestion is already dismissed"`. `SuggestionAlreadyConfirmedError(ConflictError)`,
    detail `"Rejected, suggestion is already confirmed"`. No new handler needed — all three
    subclass an existing family (`NotFoundError`/`ConflictError`), already handled.

- [x] **Task 5: Backend — `POST /api/smart-chef/suggestions/{id}/dismiss`** (AC4)
  - [x] `backend/api/smart_chef.py`: new `SmartChefAdminDep = Annotated[User,
    Depends(require_role(UserRole.admin))]` (dismissing is Admin-only, distinct from the existing
    Cook-only `SmartChefWriteDep` and the Cook+Admin `SmartChefReadDep`).
  - [x] `@router.post("/suggestions/{suggestion_id}/dismiss", response_model=
    AIRecipeSuggestionResponse)`, calling `ai_service.dismiss_suggestion(db, actor,
    suggestion_id)`. New `_DISMISS_ERROR_DESCRIPTIONS` dict (401/403, 404 "no matching suggestion",
    409 "already dismissed or already confirmed"), following this file's existing per-route dict
    convention.

- [x] **Task 6: Backend tests** (`backend/tests/test_ai.py`, extend; `backend/tests/test_menu.py`,
  extend if it exists — check the file list first)
  - [x] AC1/AC3: creating a Dish with `source_suggestion_id` persists the back-reference; creating
    a Dish without it (every existing call site) leaves it `None`.
  - [x] AC1/AC2: confirming a suggestion (`POST /api/menu/dishes` with `source_suggestion_id` set)
    is the *only* path exercised — no new endpoint bypasses `create_dish`'s own validation
    (category existence, price bounds, etc. all still apply unchanged).
  - [x] Confirming an already-confirmed suggestion (a second Dish citing the same
    `source_suggestion_id`) is rejected with 409.
  - [x] Confirming a dismissed suggestion is rejected with 409.
  - [x] Confirming a nonexistent `source_suggestion_id` is rejected with 404.
  - [x] AC4: dismissing a suggestion sets `dismissed = True`; dismissing an already-dismissed one
    is rejected with 409; dismissing an already-confirmed one is rejected with 409; dismissing a
    nonexistent id is rejected with 404.
  - [x] `GET /api/smart-chef/suggestions` includes `dismissed` and `confirmed_dish_id` (null when
    neither, the real Dish id once confirmed) in every row.
  - [x] Role coverage for `POST .../dismiss`: cook, waiter, warehouse_manager all 403 (Admin-only,
    no Cook fallback — unlike the existing `SmartChefReadDep`); unauthenticated 401.

- [x] **Task 7: Frontend — `smartChefService.ts` gains dismiss** (AC4)
  - [x] New `useDismissSuggestion(): UseMutationResult<AIRecipeSuggestion, Error, number>`, `POST
    /api/smart-chef/suggestions/${id}/dismiss`, invalidating `SUGGESTIONS_QUERY_KEY` on settle
    (matches `useGenerateSuggestion`'s own "invalidate on settle" reasoning — a 409 means the
    client's view of this suggestion's state is already stale).
  - [x] `frontend/src/types/ai.ts`: `AIRecipeSuggestion` gains `dismissed: boolean` and
    `confirmed_dish_id: number | null`.

- [x] **Task 8: Frontend — `menuService.ts`/`types/menu.ts`** (AC1)
  - [x] `CreateDishPayload` (or wherever the create-Dish request type lives) gains
    `source_suggestion_id?: number` — optional, every existing call site unaffected.

- [x] **Task 9 (revised): Frontend — `RecipeSuggestionsPage.tsx` + `ConfirmSuggestionDialog.tsx`**
  (AC1, AC4, AC5, AC6)
  - [x] `RecipeSuggestionsPage.tsx`: fetch `useSuggestions()`, filter client-side to "awaiting
    review": `!dismissed && confirmed_dish_id === null` (AD-9's client-side-filter convention).
    Each card (`SuggestionSummary`, extracted from `SmartChefPage.tsx`'s original card so both
    pages share the read-only content) renders **Confirm into Dish** (`variant="contained"`) and
    **Dismiss** (`variant="outlined"`).
  - [x] Confirm into Dish opens `ConfirmSuggestionDialog` in place (no navigation) — revised from
    the original navigate-to-Menu-Management design per manual-test feedback: the Admin wanted
    Confirm to also add the Recipe Ingredient lines, not just create a bare Dish. The dialog asks
    for Category, Price, Prep time (the fields AI output can't supply), with `name`/`description`
    prefilled and editable, and one row per suggested ingredient — each row best-effort matched
    (case-insensitive name match against the real Ingredient list for its id + fixed `unit`) and
    best-effort quantity-parsed, but always editable, since an unmatched/unparseable row is left
    blank rather than guessed. Confirm composes `POST /api/menu/dishes` (with
    `source_suggestion_id`) then one `POST /api/menu/dishes/{id}/recipe-ingredients` per row — no
    new backend endpoint, both remain the sole paths for either action (AC2).
  - [x] Dismiss: calls `useDismissSuggestion().mutate(suggestion.id)` directly, no confirm step
    (unchanged from the original design).
  - [x] Empty state: "No suggestions awaiting review." (AC6, exact copy).

- [x] ~~Task 10: Frontend — `MenuManagementPage.tsx` prefill~~ (superseded — removed, see Change
  Log). The navigation-state prefill this task added was reverted entirely once Task 9 was
  revised to confirm in-place; `MenuManagementPage.tsx` has no Story 6.2 involvement at all in the
  final design.

- [x] **Task 11: Frontend tests**
  - [x] `RecipeSuggestionsPage.test.tsx`: empty-state copy; a card renders Confirm/Dismiss
    (contrast with `SmartChefPage.test.tsx`'s own assertion that those buttons are *absent*
    there); a dismissed or already-confirmed suggestion is excluded from the rendered list even
    though `useSuggestions()`'s raw response still includes it; clicking Confirm opens the dialog
    with name/description prefilled and an ingredient row matched to a real Ingredient; confirming
    the dialog creates the Dish (carrying `source_suggestion_id`) and its Recipe Ingredient line
    together, using the matched Ingredient's real id/unit rather than the AI's free-text name/unit.

- [x] **Task 12: Full regression pass**
  - [x] `uv run pytest -q` (backend) — zero regressions.
  - [x] `pnpm test` (frontend) — zero regressions.
  - [x] `npx tsc -b` — clean.

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

## Review Findings

Reviewed by three parallel agents (Blind Hunter, Edge Case Hunter, Acceptance Auditor) against
this story's ACs and `_bmad-output/project-context.md`. Several findings from all three agents
converged on the same underlying issues; consolidated below.

- [x] [Review][Patch] The generated Alembic downgrade for `f9cbd3ff5b87` was broken:
  `op.create_foreign_key(None, ...)` leaves the FK constraint unnamed, and
  `op.drop_constraint(None, 'dishes', type_='foreignkey')` cannot target an unnamed constraint —
  confirmed via `alembic downgrade --sql`, which raised `CompileError: Can't emit DROP CONSTRAINT
  ... it has no name`. Named the constraint explicitly (matching the name Postgres itself had
  already assigned, so no live database needed a rename) —
  `backend/alembic/versions/f9cbd3ff5b87_add_dish_source_suggestion_id_and_ai_.py`
- [x] [Review][Patch] No DB-level uniqueness on `Dish.source_suggestion_id` — a plain,
  unlocked `SELECT` in `MenuService._validate_source_suggestion` let two concurrent
  `POST /api/menu/dishes` requests citing the same suggestion both pass the "not already
  confirmed" check before either committed, giving one suggestion two confirming Dishes (FR-19's
  "at most one" cardinality). Added a `UNIQUE` constraint on `dishes.source_suggestion_id`
  (Postgres permits multiple NULLs under a plain unique constraint, so ordinary Dishes are
  unaffected), added `unique=True` to the ORM column to keep the model/migration in sync, and
  caught the resulting `IntegrityError` in `create_dish` to translate the losing request's 409
  rather than letting it surface as a 500. Added
  `test_two_concurrent_confirms_of_the_same_suggestion_only_one_succeeds` (two real concurrent
  requests via `asyncio.gather`, not sequential) to prove it —
  `backend/data_models/menu.py`, `backend/services/menu_service.py`,
  `backend/alembic/versions/f9cbd3ff5b87_add_dish_source_suggestion_id_and_ai_.py`,
  `backend/tests/test_ai.py`
- [x] [Review][Patch] `AIService.dismiss_suggestion` hardcoded `confirmed_dish_id=None` on its
  response instead of reusing the `confirmed_dish_id` its own guard already computed — correct
  only by proximity to that guard, so a future reorder/relaxation of it would silently start
  returning a wrong `null`. Reused the already-computed value — `backend/services/ai_service.py`
- [x] [Review][Patch] No test proved `confirmed_dish_id` is populated with the real Dish id once
  a suggestion is actually confirmed — only the null (awaiting/dismissed) cases were covered,
  leaving the headline behavior this story adds unverified. Added
  `test_list_suggestions_reports_the_real_dish_id_once_confirmed` — `backend/tests/test_ai.py`
- [x] [Review][Patch] The Confirm button read "Confirm into dish"; AC5/Task 9 specify "Confirm
  into Dish". Corrected the label and its two test assertions —
  `frontend/src/pages/admin/RecipeSuggestionsPage.tsx`,
  `frontend/src/pages/admin/RecipeSuggestionsPage.test.tsx`
- [x] [Review][Defer] Concurrent dismiss-vs-dismiss race (two simultaneous dismiss requests for
  the same suggestion could both read `dismissed=False` before either commits, both succeeding
  with 200 instead of the second getting 409) — deferred, pre-existing class of race this story's
  design doesn't newly introduce risk from: the end state is still correctly `dismissed=True`
  either way, no data corruption, just a lost 409 in an already-narrow window.
- [x] [Review][Dismiss] Concurrent dismiss-vs-confirm race (a suggestion ending up both
  `dismissed=True` and referenced by a confirmed Dish) — the story's own Scope note explicitly
  accepts this: "not enforced against each other at the DB level beyond normal application
  logic," a documented tradeoff, not a gap.
- [x] [Review][Dismiss] Cross-module import of `_INT4_MAX` (a leading-underscore name) in
  `api/smart_chef.py` — verified this is the codebase's own pre-existing, documented convention
  (`order.py`/`recipe.py`/`api/tables.py`/`api/inventory.py`/`api/orders.py` all already import it
  the same way), not something this story diverges from.
- [x] [Review][Dismiss] `MultipleResultsFound` risk in `scalar_one_or_none()` call sites if
  duplicate confirming Dishes ever existed — moot once the unique constraint above makes that
  state unreachable.
- [x] [Review][Dismiss] Duplicated "does a Dish cite this suggestion" query logic between
  `AIService._get_confirmed_dish_id` and `MenuService._validate_source_suggestion` — two lines
  each, and consolidating would require a new cross-service dependency for a trivial query;
  not worth the coupling.
- [x] [Review][Dismiss] "Dismiss is reversible in spirit" framing (no undo path exists) —
  matches the story's own stated Task 9 intent (audit retention, not actual reversibility), a
  rationale critique rather than a code defect.
- [x] [Review][Dismiss] Error alert on a failed Dismiss can unmount with the card on refetch —
  matches this codebase's established "invalidate onSettled" convention used everywhere else;
  not a regression specific to this story.
- [x] [Review][Dismiss] Brittle exact `toEqual` assertion on the create-Dish request body in the
  new frontend tests — matches the same pattern already used by this file's pre-existing "creates
  a dish and clears the form" test.
- [x] [Review][Dismiss] `useState` lazy-initializer prefill assumes `MenuManagementPage` remounts
  on navigation — verified against `router.tsx`: each path maps to a distinct element with no
  keep-alive mechanism, so the assumption holds.
- [x] [Review][Dismiss] Missing regression test asserting `update_dish` never accepts
  `source_suggestion_id` — verified `UpdateDishRequest` has no such field at all (Pydantic
  silently ignores unknown fields by default), so this is structurally impossible, not merely
  untested.

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5

### Debug Log References

- Alembic autogenerate for `f9cbd3ff5b87` omitted `server_default` on the new NOT NULL
  `ai_recipe_suggestions.dismissed` column — trap 22 (nullable/no-default NOT NULL add against a
  table with existing rows). Verified 6 pre-existing rows via `psql` against the running dev
  container, added `server_default=sa.text('false')` manually, re-ran `alembic upgrade head`, and
  confirmed all 6 rows backfilled to `dismissed = f`.
- A backend test (`test_dismissing_a_suggestion_sets_dismissed_true`) initially failed with
  `sqlalchemy.exc.MissingGreenlet`: `db_session.expire_all()` expired the `suggestion` ORM object
  itself, so the later `suggestion.id` access (evaluated synchronously as a call argument) tried a
  lazy DB reload outside the awaited call. Fixed by capturing `suggestion.id` into a local before
  calling `expire_all()`.

### Completion Notes List

- `Dish.source_suggestion_id` is the nullable provenance FK (no separate "Recipe" entity exists in
  this schema); `AIRecipeSuggestion.dismissed` is the one new stored column. "Confirmed" remains
  derived — a suggestion is confirmed iff some `Dish.source_suggestion_id` matches its id, resolved
  via an outerjoin in `AIService.list_suggestions`, never a stored flag.
- `MenuService.create_dish` is still the only Dish-creation path; Story 6.2 adds one optional,
  validated field to it (`_validate_source_suggestion`) rather than a second path, satisfying AC2
  structurally.
- `POST /api/smart-chef/suggestions/{id}/dismiss` is Admin-only (`SmartChefAdminDep`), rejecting an
  already-dismissed or already-confirmed suggestion with a 409, and a nonexistent one with a 404.
- Frontend: extracted `SuggestionSummary` (in `components/ai/`) out of `SmartChefPage.tsx`'s
  original `SuggestionCard` so `RecipeSuggestionsPage.tsx` could reuse the same read-only content
  without duplicating it, wrapping it with this story's own Confirm/Dismiss actions.
  `RecipeSuggestionsPage.tsx` filters `useSuggestions()` client-side to "awaiting review"
  (`!dismissed && confirmed_dish_id === null`), per AD-9. "Confirm into dish" hands off to
  `MenuManagementPage.tsx` via `navigate(path, { state })`, read once via a lazy `useState`
  initializer so it only prefills on the initial mount.
- Full regression pass: 394 backend tests pass (`uv run pytest -q`), 209 frontend tests pass
  (`pnpm test` / vitest), `npx tsc -b` clean.

### File List

- `backend/data_models/menu.py` (modified)
- `backend/data_models/ai.py` (modified)
- `backend/exceptions/__init__.py` (modified)
- `backend/services/ai_service.py` (modified)
- `backend/services/menu_service.py` (modified)
- `backend/api/smart_chef.py` (modified)
- `backend/alembic/versions/f9cbd3ff5b87_add_dish_source_suggestion_id_and_ai_.py` (new)
- `backend/tests/test_ai.py` (modified)
- `backend/tests/test_menu.py` (modified)
- `frontend/src/types/ai.ts` (modified)
- `frontend/src/types/menu.ts` (modified)
- `frontend/src/services/smartChefService.ts` (modified)
- `frontend/src/services/menuService.ts` (modified)
- `frontend/src/components/ai/SuggestionSummary.tsx` (new)
- `frontend/src/pages/cook/SmartChefPage.tsx` (modified)
- `frontend/src/pages/admin/RecipeSuggestionsPage.tsx` (modified)
- `frontend/src/pages/admin/RecipeSuggestionsPage.test.tsx` (new)
- `frontend/src/components/ai/ConfirmSuggestionDialog.tsx` (new)
- `frontend/src/pages/admin/MenuManagementPage.tsx` (modified, then reverted to its pre-Story-6.2
  state — see Change Log)
- `frontend/src/pages/admin/MenuManagementPage.test.tsx` (modified, then reverted alongside it)

## Change Log

- **Post-code-review, during manual testing**: the Admin found the original "Confirm into Dish"
  design (navigate to Menu Management with `name`/`description` pre-filled, Admin re-adds every
  Recipe Ingredient line by hand) an unacceptable extra step — Confirm should create the Dish
  *and* its Recipe Ingredient lines together, in one place. Reworked Task 9 into an in-place
  `ConfirmSuggestionDialog.tsx` on `RecipeSuggestionsPage.tsx` (Category/Price/Prep-time fields
  plus one best-effort-prefilled, always-editable row per suggested ingredient) and fully removed
  Task 10's `MenuManagementPage.tsx` navigation-state prefill, since nothing routes through it
  anymore. No backend change was needed for this rework: the dialog composes the same two
  existing endpoints (`POST /api/menu/dishes`, `POST .../recipe-ingredients`) already used
  everywhere else. See the Scope note and Task 9/10 above for the full reasoning.
- **Follow-up manual-test finding**: the confirmed Dish stayed `is_available: false`, requiring a
  separate manual toggle even though its recipe was just attached in the same flow. Since
  `ConfirmSuggestionDialog` already knows at least one Recipe Ingredient line succeeded, it now
  also sends `PATCH /api/menu/dishes/{id}` with `{is_available: true}` right after — reusing
  `MenuService.update_dish`'s own existing `EmptyRecipeError` guard (AD-8) as the safety net, not
  a new rule. If zero lines succeeded, or the availability PATCH itself fails, the Dish is left as
  created and the Admin finishes it from Menu Management, same as any other partial failure here.
