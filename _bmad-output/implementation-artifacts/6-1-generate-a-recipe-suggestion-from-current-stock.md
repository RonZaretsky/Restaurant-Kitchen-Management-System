---
baseline_commit: 479e0e401713a6c94b3013faf30930704f14961a
epic: 6
story: 1
---

# Story 6.1: Generate a Recipe Suggestion from Current Stock

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Cook,
I want to request an AI-generated recipe suggestion based on what's actually in stock,
so that I can turn surplus into a usable dish idea instead of letting it go to waste.

## Scope note (read first)

**This is the first story in Epic 6 and the first external-API integration in the project.**
Nothing in `backend/clients/` talks to a third-party service today (`database.py` and
`websocket.py` are both internal). This story is what establishes the pattern (AD-12) every later
Smart Chef story (6.2, 6.3) builds on — get the client seam, the config, and the failure handling
right here, since 6.2/6.3 will reuse this story's client and config, not rebuild them.

**The ORM models already exist** — `backend/data_models/ai.py` (`AIRecipeSuggestion`,
`AIChatSession`, `AIChatMessage`, `ChatRole`) was scaffolded into the Alembic baseline back in
Story 1.0 and is already exported from `data_models/__init__.py`. **No new migration is needed for
this story's own schema** — the columns this story writes to (`requested_by`, `prompt_used`,
`generated_recipe`, `ingredients_snapshot`, `created_at`) all already exist. (Story 6.2 adds its
own `dismissed` column later, via its own migration — not this story's concern.)

**The frontend route and nav entry already exist too** — `frontend/src/pages/cook/
SmartChefPage.tsx` is a placeholder (`<Typography>Smart Chef</Typography>`), already wired at
`/cook/smart-chef` in `router.tsx` and already in `ROLE_NAV_ITEMS.cook` in `navigationConfig.ts`.
This story replaces the placeholder's body, not the routing/nav (already correct, don't touch
`router.tsx`/`navigationConfig.ts`).

**What this story does NOT include, even though the UX mockup (`mockups/key-smart-chef.html`)
shows it on the same screen:** the mockup is one **key-screen composite** illustrating the whole
Smart Chef feature area across three stories, not this story's own scope. Specifically:
- **No Confirm/Dismiss buttons anywhere in this story.** The mockup's suggestion card shows both,
  but confirming/dismissing a suggestion is explicitly **Story 6.2's** Admin-only action (FR-19,
  "As an Admin, I want to confirm...") — a Cook's own Smart Chef page must not offer either
  action. If a suggestion card renders on `SmartChefPage.tsx` in this story, it shows the
  suggestion's content only (name, ingredients drawn on, plating), no action buttons.
- **No chat panel.** The mockup's "Iterate on this suggestion" panel is Story 6.3's
  (`AIChatSession`/`AIChatMessage`, FR-20) — do not build any chat UI, endpoint, or
  `AIChatSession`/`AIChatMessage` write in this story.
- **Do not add a `dismissed` filter or column** — that column doesn't exist until Story 6.2's own
  migration adds it. This story's list endpoint (below) returns every `AIRecipeSuggestion` row,
  unfiltered.

**What this story DOES need beyond the epics.md AC text, to leave the system working
end-to-end:** the epics ACs describe generating and displaying one suggestion, but
`EXPERIENCE.md`'s own State Patterns table lists an empty state for this exact page ("No recipe
suggestions yet.") and the mockup's own subtitle ("1 recipe suggestion") implies the page shows a
Cook's **persisted history** of suggestions, not just the one just generated in the current
browser session. A Cook who navigates away and back must still see their prior suggestions. This
means a **`GET` list endpoint is required, not optional**, even though no epics AC spells it out
literally — matching this project's own "a story must leave the system working end-to-end, not
just satisfy its literal ACs" rule. Scope the read broadly (Cook and Admin both, matching the
Chat-Session/Recipe-Suggestion "shared, Role-level, sort current-user-first as a personalization
default, not an access boundary" pattern FR-20/AD-9/AD-10 already establish for this exact domain)
so Story 6.2's own Admin review page can reuse this same list endpoint rather than rebuilding it.

**"Prioritizing at-risk-of-waste ingredients" (FR-18) needs a concrete, honest heuristic** — the
schema has no expiry date, no usage-rate history, nothing that directly measures "about to go to
waste." The most defensible proxy available today is **surplus relative to normal operating
level**: `current_stock / min_stock_threshold`, descending — an Ingredient sitting at many times
its own minimum threshold is the one most plausibly overstocked/at risk of aging out, not
necessarily the one with the largest raw quantity (a staple with a naturally huge `min_stock_
threshold` isn't "at risk" just because its raw `current_stock` number is big). Sort the stock
snapshot this way before building the prompt, and instruct the model (in the prompt text itself)
to prioritize the ingredients listed first. Document this as a stated simplification in the
service's own docstring — it is a genuine, reasoned interpretation of an underspecified
requirement, not an oversight to flag as a gap later.

**AD-14's "reject, don't queue" concurrency guard needs an in-memory seam, not a DB column.** This
is a single-process demo app (no distributed workers), so tracking "which Cooks currently have a
generation in flight" as a plain in-process `set[int]` (user ids) on the new service instance is
sufficient and simplest — add the user id before the OpenAI call, remove it in a `finally` block
regardless of success/failure, and reject with a 409 if already present when a request arrives.
Do not reach for Redis, a DB lock, or a Celery-style queue — none of that infrastructure exists in
this project and none is warranted for a single-process app.

**FR-21's graceful degradation is the other half of AD-14.** If the OpenAI call fails, times out,
or returns unparseable content: log the failure, persist **no** `AIRecipeSuggestion` row (not even
a partial one), and surface a clear, distinct error to the Cook — never silently succeed with
empty/null content, and never leave the frontend's "Generating..." state stuck. This needs a new
exception type, the **first of a new family** (`ExternalServiceError`, base for
`AIGenerationFailedError`), mapped to a new 502 handler — mirroring the existing `AuthError`/
`ConflictError`/`NotFoundError` family-plus-one-handler pattern in `backend/exceptions/
handlers.py` exactly, since nothing in that file currently handles an upstream-service failure.

## Acceptance Criteria

1. **Given** a Cook requests a suggestion, optionally with a free-text direction, **when** the
   request is submitted, **then** the system generates one using a snapshot of currently-available
   Ingredient stock, prioritizing at-risk-of-waste ingredients, and persists the prompt used, the
   stock snapshot, and the resulting suggestion as a Recipe Suggestion (FR-18).
2. **Given** a free-text direction is supplied, **when** the prompt is constructed, **then** the
   direction steers the suggestion but never overrides the stock-availability constraint, and
   becomes part of the persisted `prompt_used` rather than a separate field (FR-18).
3. **Given** a Cook already has a generation in flight, **when** they submit a second request
   before the first finishes, **then** the second is rejected inline, not queued (FR-18, AD-14).
4. **Given** the OpenAI call fails or times out, **when** that happens, **then** the system
   surfaces "Couldn't generate a suggestion right now," persists no partial or orphaned Recipe
   Suggestion row, and shows a state distinguishable from "still generating" (FR-21, AD-14,
   UX-DR18).
5. **Given** any OpenAI call issued by this story, **when** it is made, **then** it goes through a
   `backend/clients/` adapter behind an interface, never called directly from `services/` (AD-12).
6. **Given** a generated Recipe Suggestion, **when** its card renders, **then** it shows the
   requesting Cook and the ingredients the suggestion drew on (UX-DR11).
7. **Given** any OpenAI call is issued for a suggestion, **when** it is made, **then** the
   resulting record carries the requesting User's id and its owning Recipe Suggestion, so every
   billed call is attributable for later cost auditing; no hard per-user or per-day cost cap is
   enforced in v1 (PRD 4.5 feature NFR).
8. **Given** the `smart_chef` domain router does not yet exist, **when** this story adds it,
   **then** `smart_chef` is appended to `container.wire(modules=[...])`, alongside the existing
   entries, not replacing them (AD-1).

## Tasks / Subtasks

- [x] **Task 1: Dependency + config** (AC5)
  - [x] `backend/pyproject.toml`: add `"openai>=1.0.0"` to `dependencies` (the official Python SDK,
    exposes `openai.AsyncOpenAI`). Run `uv sync` (or `uv add openai`) to update `uv.lock`.
  - [x] `backend/config.yaml`: add a `smart_chef` section: `api_key: ${OPENAI_API_KEY:}` (no
    committed default — unlike `auth.secret_key`'s insecure-but-functional fallback, a fake API
    key would just fail every call, so there is nothing useful to default to) and `model:
    ${OPENAI_MODEL: gpt-4o-mini}` (a real, cheap, capable default so a contributor who sets the
    key but not the model still gets a working model name).
  - [x] `backend/.env.example`: add `OPENAI_API_KEY=` and `OPENAI_MODEL=gpt-4o-mini` with a short
    comment, matching the file's existing per-var comment convention. **HALT and ask the user for
    a real API key and model name to put in their own `backend/.env`** before attempting to run
    the app against a live OpenAI call — `.env.example`'s own values are placeholders, never a
    real key.
  - [x] `main.py`: add a startup warning if `OPENAI_API_KEY` is unset, mirroring
    `_warn_if_default_secret_key`'s exact shape (a `_warn_if_no_openai_key` sibling function),
    since an unset key means every Smart Chef call will fail at request time with no earlier
    signal otherwise.

- [x] **Task 2: Backend — `backend/clients/llm.py`** (AC5, AD-12)
  - [x] New file, mirroring `clients/database.py`'s "the client, not `services/`, owns the
    third-party SDK" role. Define an `LLMClient` class wrapping `openai.AsyncOpenAI(api_key=...)`,
    constructed with `api_key`/`model` from config (injected via the container, not read from
    `os.environ` directly — matches `AuthService`'s own config-injected-at-construction shape).
  - [x] One public method, e.g. `async def generate_recipe(self, prompt: str) -> dict`: calls
    `self._client.chat.completions.create(model=self._model, messages=[{"role": "user", "content":
    prompt}], response_format={"type": "json_object"})` (JSON mode — reliable, widely-supported,
    avoids fragile manual JSON-extraction from free text), parses the response content as JSON,
    and returns the parsed dict. Let `json.JSONDecodeError` and any `openai` SDK exception
    propagate to the caller (`AIService`, Task 3) — the client's job is the API call and parsing,
    not deciding what a failure means to the rest of the app.
  - [x] Include a short module docstring stating this is the first external-service client in the
    project and the seam AD-12 requires — future OpenAI calls (Story 6.3's chat) extend this same
    class, they do not create a second one.

- [x] **Task 3: Backend — `backend/services/ai_service.py`** (AC1, AC2, AC3, AC4, AC6, AC7)
  - [x] New `AIService`, config-free aside from its `llm_client`/`logger` collaborators
    (`inventory_service` is NOT a dependency — read Ingredients directly via the session, the same
    plain-`select()` shape every other read-only service method in this codebase uses, no need to
    route through `InventoryService` for a simple stock read).
  - [x] `__init__(self, logger, llm_client)`.
  - [x] A private, in-process `self._in_flight: set[int] = set()` (Cook user ids currently
    generating) — see Scope note. Not persisted, not shared across processes; acceptable for a
    single-process app.
  - [x] `async def generate_suggestion(self, db: AsyncSession, actor: User, direction: str | None)
    -> AIRecipeSuggestion`:
    - If `actor.id in self._in_flight`: raise a new `SuggestionGenerationInProgressError`
      (`ConflictError` subclass, 409) immediately, no DB read, no OpenAI call (AC3).
    - Otherwise add `actor.id` to `self._in_flight` before proceeding, and remove it in a `finally`
      block wrapping everything below (guarantees removal on success, failure, or an unexpected
      exception).
    - Read every Ingredient (`select(Ingredient)`), sort by `current_stock / min_stock_threshold`
      descending (Scope note's heuristic) — build the stock snapshot as a JSON-serializable list
      of `{name, unit, current_stock}` (no threshold in the snapshot itself, that's an internal
      sort key, not something the model needs to see).
    - Build the prompt: instructs the model to propose one recipe using only the listed
      ingredients (in the given priority order), incorporating `direction` if provided as a
      steering hint that never overrides the stock constraint (AC2), and to respond as JSON with
      exactly the shape `{"name": str, "ingredients": [{"name": str, "quantity": str}], "plating":
      str}` (matching the mockup's card sections: title, "Ingredients drawn on", "Suggested
      plating").
    - Call `self._llm_client.generate_recipe(prompt)` inside a `try` — on any exception
      (`openai`'s own exception types, `json.JSONDecodeError`, or a response missing expected
      keys), log at `ERROR` with `actor.id`/truncated prompt, and raise a new
      `AIGenerationFailedError` (`ExternalServiceError` subclass, 502). No `AIRecipeSuggestion` row
      is created on this path (AC4) — the insert happens strictly after the call succeeds.
    - On success: insert a new `AIRecipeSuggestion(requested_by=actor.id, prompt_used=prompt,
      generated_recipe=<parsed dict>, ingredients_snapshot=<the snapshot list built above>)`,
      commit, refresh, log at `INFO` (`actor.id`, `suggestion.id`), return it.
  - [x] `async def list_suggestions(self, db: AsyncSession, actor: User) -> Sequence[
    AIRecipeSuggestion]`: `select(AIRecipeSuggestion).order_by(AIRecipeSuggestion.id.desc())` — no
    actor-based filtering (AD-9), `actor` accepted for signature symmetry only, matching
    `OrderService.list_open_orders`'s own established shape and docstring wording. No `dismissed`
    filter (doesn't exist yet, Story 6.2's job).

- [x] **Task 4: Backend — new exception types** (AC3, AC4)
  - [x] `backend/exceptions/__init__.py`: add `SuggestionGenerationInProgressError(ConflictError)`,
    detail `"Rejected, a suggestion is already generating for this Cook"`.
  - [x] Add a new base `class ExternalServiceError(Exception): detail = "An external service call
    failed"` (mirrors `AuthError`/`ConflictError`/`NotFoundError`'s own base-class shape, one
    handler for the whole family), and `AIGenerationFailedError(ExternalServiceError)`, detail
    `"Couldn't generate a suggestion right now"` (the exact copy `EXPERIENCE.md`'s State Patterns
    table specifies).
  - [x] `backend/exceptions/handlers.py`: add `_external_service_error_handler` (502, mirrors
    `_not_found_error_handler`'s exact structure/docstring shape) and register it in
    `register_exception_handlers` alongside the other three.

- [x] **Task 5: Backend — `backend/api/smart_chef.py` + container wiring** (AC5, AC8)
  - [x] New router, `prefix="/api/smart-chef"`, `tags=["smart-chef"]`, following every other
    domain router's file shape (`OrdersDep`-style role-scoped `Annotated` deps, an
    `_ERROR_DESCRIPTIONS` dict, `error_responses(...)` on each route).
  - [x] `SmartChefWriteDep = Annotated[User, Depends(require_role(UserRole.cook))]` (generating is
    Cook-only, no Admin fallback — matches the epics AC's literal "As a Cook").
  - [x] `SmartChefReadDep = Annotated[User, Depends(require_role(UserRole.cook, UserRole.admin))]`
    (the list read, per the Scope note's "shared with Story 6.2's Admin review page" reasoning).
  - [x] `@router.post("/suggestions", response_model=AIRecipeSuggestionResponse, status_code=201)`
    — body `{"direction": str | None}` (a small inline Pydantic model or reuse a request schema
    defined in `data_models/ai.py`, matching every other domain's `Create*Request` convention),
    calls `ai_service.generate_suggestion(db, actor, payload.direction)`.
  - [x] `@router.get("/suggestions", response_model=list[AIRecipeSuggestionResponse])` — calls
    `ai_service.list_suggestions(db, actor)`.
  - [x] `backend/api/router.py`: `include_router(smart_chef_router)`, alongside the existing list
    (never replacing it).
  - [x] `backend/main.py`: append `"api.smart_chef"` to `container.wire(modules=[...])` (AC8) —
    the exact append-only rule AD-1/trap 1 already established, do not reorder or replace existing
    entries.
  - [x] `backend/container.py`: add `llm_client = providers.Factory(LLMClient, api_key=config.
    smart_chef.api_key, model=config.smart_chef.model)` and `ai_service = providers.Factory(
    AIService, logger=logging, llm_client=llm_client)`. No provider-ordering constraint beyond the
    Python-class-body top-to-bottom rule already documented (trap 23) — `llm_client` must be
    declared above `ai_service` since `ai_service` references it.

- [x] **Task 6: Backend — `data_models/ai.py` response/request models** (AC1, AC6)
  - [x] Add `CreateRecipeSuggestionRequest` (`direction: str | None = None`) and
    `AIRecipeSuggestionResponse` (`model_config = {"from_attributes": True}`; `id`, `requested_by`,
    `prompt_used`, `generated_recipe: dict`, `ingredients_snapshot: list | dict`, `created_at`),
    matching every other domain's `Response`-suffix/`from_attributes` convention.
  - [x] Export both from `data_models/__init__.py`, alongside the existing `ai.py` exports.

- [x] **Task 7: Backend tests** (`backend/tests/test_ai.py`, new file)
  - [x] Mock `LLMClient.generate_recipe` (e.g. via a test double injected through the container
    override, or monkeypatching the method — check `conftest.py` for this project's established
    container-override convention for injecting test doubles before picking an approach) so no
    test makes a real network call to OpenAI.
  - [x] AC1/AC2: a successful generation persists `prompt_used` containing the supplied
    `direction` text, `ingredients_snapshot` matching current stock, `generated_recipe` matching
    the mocked client's returned dict, `requested_by` the acting Cook's id.
  - [x] AC3: two rapid requests from the same Cook — the second is rejected with 409 while the
    first is still "in flight" (use a mocked client whose `generate_recipe` blocks on an
    `asyncio.Event` the test controls, so the first call's in-flight window is deterministic, not
    timing-dependent).
  - [x] AC4: a mocked client that raises — response is 502 with the exact `"Couldn't generate a
    suggestion right now"` detail, and no `AIRecipeSuggestion` row exists afterward (query the
    table directly).
  - [x] AC7: after a successful generation, `AIRecipeSuggestion.requested_by` is populated (cost
    attribution) — a simple persistence assertion, not a new mechanism.
  - [x] Role coverage for both routes: waiter, warehouse_manager 403 on `POST`; unauthenticated
    401; `GET` permits both cook and admin, 403 for waiter/warehouse_manager.
  - [x] `GET /api/smart-chef/suggestions` returns `[]` on a fresh install, not a 404.

- [x] **Task 8: Frontend — `smartChefService.ts`** (AC1, AC2, AC3, AC4, AC6)
  - [x] New file (this domain's first frontend service file), mirroring `orderService.ts`'s
    hook-per-endpoint shape: `useGenerateSuggestion(): UseMutationResult<AIRecipeSuggestion, Error,
    { direction?: string }>` (`POST /api/smart-chef/suggestions`) and `useSuggestions():
    UseQueryResult<AIRecipeSuggestion[], Error>` (`GET /api/smart-chef/suggestions`).
  - [x] `useGenerateSuggestion` invalidates the suggestions list query key on settle (matching
    `useAddOrderItem`'s own "invalidate on settle, not just success" reasoning — a 409 in-flight
    rejection or a 502 generation failure both mean the client's view of "what's currently
    happening" may be stale).
  - [x] New `frontend/src/types/ai.ts`: `AIRecipeSuggestion` interface mirroring
    `AIRecipeSuggestionResponse` field-for-field (matching every other domain's frontend-type
    mirrors-backend-response convention, e.g. `types/order.ts`).

- [x] **Task 9: Frontend — `SmartChefPage.tsx`** (AC1, AC2, AC3, AC4, AC6)
  - [x] Replace the placeholder body. A request bar (optional free-text "direction" field +
    "Request suggestion" button, matching the mockup's copy/placeholder text exactly) and a list
    of suggestion cards below it (newest first, matching `list_suggestions`'s own `id.desc()`
    order).
  - [x] Each card shows: the suggestion's dish name, "Requested by {Cook}" (resolve the id via
    the existing Users list the same way `OrderItemResponse.cook_id` is resolved elsewhere, or via
    a plain `#id` fallback if no per-suggestion user-name resolution exists yet — check whether a
    `GET /api/admin/users` (or similar) response is already fetched anywhere reusable before
    building a new lookup), the ingredients drawn on (name + quantity chips, per the mockup), and
    the plating description. **No Confirm/Dismiss buttons, no chat panel** (Scope note).
  - [x] Generating state: while the mutation is pending, an explicit "Generating suggestion..."
    indicator (matching the mockup's `generating-pill`), distinguishable from both the empty list
    state and an error state (AC4). The Request button (and, per AC3, submitting again) is
    disabled while pending — this is the primary UI mechanism preventing a second in-flight
    request, the backend's 409 is the defense-in-depth backstop, not the primary UX.
  - [x] Error state: on a 502 (or any mutation error), an inline `Alert` showing the server's own
    message (`"Couldn't generate a suggestion right now"` for the 502 case, matching this
    codebase's established `error instanceof ApiError ? error.message : "Something went wrong.
    Try again."` pattern everywhere else).
  - [x] Empty state: `!isLoading && !isError && suggestions?.length === 0` → "No recipe
    suggestions yet." (`EXPERIENCE.md`'s exact copy).

- [x] **Task 10: Frontend tests** (`frontend/src/pages/cook/SmartChefPage.test.tsx`, new file)
  - [x] Empty state renders the exact copy.
  - [x] A successful generation renders the new card (name, ingredients, plating) with no
    Confirm/Dismiss buttons anywhere on the page.
  - [x] While the mutation is pending, the generating indicator shows and the Request button is
    disabled.
  - [x] A 502 mutation error shows the inline error message, not a stuck "Generating..." state.
  - [x] The optional direction field's text is included in the submitted request body.

- [x] **Task 11: Full regression pass**
  - [x] `uv run pytest -q` (backend) — zero regressions.
  - [x] `pnpm test` (frontend) — zero regressions.
  - [x] `npx tsc -b` — clean.

## Dev Notes

### Architecture compliance

- **AD-12** (Smart Chef client behind an interface): `backend/clients/llm.py`'s `LLMClient` is the
  only place `openai` is imported anywhere in `backend/`; `services/ai_service.py` depends only on
  `LLMClient`'s method signature.
- **AD-14** (request lifecycle integrity): the in-process `_in_flight` set (reject, AC3) and the
  strict "insert only after the OpenAI call succeeds" ordering (no orphaned rows, AC4) are this
  story's two concrete implementations of it.
- **AD-9/AD-10** (Role-level-only permissions, sort-not-filter personalization): `list_suggestions`
  takes no actor-based filter — if/when a "current Cook's own items first" sort is added to the
  frontend later, it is a client-side sort over the same unfiltered list, never a second
  server-side query parameter.
- **AD-1** (append-only `container.wire(modules=[...])`): `"api.smart_chef"` appended, existing
  entries untouched (AC8).
- **Trap 23** (a `providers.Factory` that injects another provider must be declared *after* it):
  `llm_client` must be declared above `ai_service` in `container.py`, the same ordering constraint
  `inventory_service`/`order_service` already established.

### Current state of the files this story touches (read before editing)

- **`backend/data_models/ai.py`**: `AIRecipeSuggestion`/`AIChatSession`/`AIChatMessage`/`ChatRole`
  ORM classes already exist (Story 1.0 baseline) — this story only adds Pydantic request/response
  models to this same file, no ORM column changes.
- **`backend/container.py`**: read the existing `inventory_service`/`order_service` block's own
  comment about provider-declaration ordering (trap 23) before adding `llm_client`/`ai_service`.
- **`backend/main.py`**: `container.wire(modules=[...])` (~lines 21-31) and
  `_warn_if_default_secret_key` (the exact sibling-function shape `_warn_if_no_openai_key`
  mirrors) both live here.
- **`backend/exceptions/__init__.py`** and **`backend/exceptions/handlers.py`**: read
  `NotFoundError`'s base-class-plus-handler shape as the literal template for the new
  `ExternalServiceError` family — one new handler function, one new registration line, nothing
  else in `main.py` or elsewhere needs to change.
- **`frontend/src/pages/cook/SmartChefPage.tsx`**: currently a two-line placeholder. Already
  correctly routed and navigable — do not touch `router.tsx` or `navigationConfig.ts`.
- **`frontend/src/services/orderService.ts`**: the exact hook-shape template (`useMutation`/
  `useQuery`, invalidate-on-settle) `smartChefService.ts` should mirror.

### Project Structure Notes

Files touched:
- `backend/pyproject.toml`, `backend/uv.lock` — **UPDATE**, `openai` dependency added.
- `backend/config.yaml`, `backend/.env.example` — **UPDATE**, new `smart_chef` config section.
- `backend/main.py` — **UPDATE**, `container.wire` gains `"api.smart_chef"`, new
  `_warn_if_no_openai_key`.
- `backend/clients/llm.py` — **NEW**.
- `backend/services/ai_service.py` — **NEW**.
- `backend/exceptions/__init__.py`, `backend/exceptions/handlers.py` — **UPDATE**, new
  `ExternalServiceError` family.
- `backend/api/smart_chef.py` — **NEW**.
- `backend/api/router.py` — **UPDATE**, `include_router(smart_chef_router)`.
- `backend/container.py` — **UPDATE**, `llm_client`/`ai_service` providers.
- `backend/data_models/ai.py`, `backend/data_models/__init__.py` — **UPDATE**, new request/
  response models.
- `backend/tests/test_ai.py` — **NEW**.
- `frontend/src/services/smartChefService.ts` — **NEW**.
- `frontend/src/types/ai.ts` — **NEW**.
- `frontend/src/pages/cook/SmartChefPage.tsx` — **UPDATE**, placeholder replaced.
- `frontend/src/pages/cook/SmartChefPage.test.tsx` — **NEW**.

No changes to `router.tsx`/`navigationConfig.ts` (already correctly wired). No `dismissed` column,
no chat endpoints/models — both are later stories' scope (see Scope note).

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 6.1`] — this story's AC source,
  verbatim.
- [Source: `_bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md`,
  FR-18, FR-21, §4.5 feature NFR] — the full requirement text and the confirmed "no hard cost cap"
  policy decision.
- [Source: `_bmad-output/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md`, AD-1, AD-9,
  AD-12, AD-14] — the client-interface rule, the append-only wiring rule, and the request-lifecycle
  integrity rule this story implements for the first time.
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../EXPERIENCE.md`, "Smart Chef" nav row,
  "Recipe request bar" row, State Patterns table (Empty/Generating/Generation failed)] — the exact
  UI copy and state shapes this story's frontend must match.
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../mockups/key-smart-chef.html`] — the
  visual reference for the request bar and suggestion card; the chat panel and Confirm/Dismiss
  buttons on this same mockup are explicitly out of this story's scope (see Scope note).
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../DESIGN.md`, `recipe-suggestion-card`
  component token] — confirm/dismiss button styling, relevant to Story 6.2, not this one (no
  buttons render here).
- [Source: `docs/database-schema.md`, `AIRecipeSuggestion`] — the exact column set this story
  writes to, confirming no migration is needed.
- [Source: `backend/data_models/recipe.py::Ingredient`] — `current_stock`/`min_stock_threshold`
  fields the stock-snapshot heuristic sorts on.
- [Source: `backend/exceptions/handlers.py`] — the base-class-plus-handler pattern the new
  `ExternalServiceError` family mirrors.
- [Source: `backend/container.py`, trap 23] — the provider-declaration-ordering constraint
  `llm_client`/`ai_service` must follow.

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5

### Debug Log References

- `uv run pytest tests/test_ai.py -q` — 9 passed: successful generation persists prompt/snapshot/
  recipe, direction is folded into the prompt with an explicit never-override-stock instruction,
  a second concurrent request from the same Cook is rejected (deterministic via a
  test-controlled `asyncio.Event`, not timing-dependent), a failed generation persists no row and
  returns 502, the in-flight guard clears on failure too (a Cook can retry immediately), `GET`
  returns `[]` not a 404, Admin can also list, and role coverage for both routes.
- `uv run pytest -q` (full backend suite) — 378 passed, no regressions (baseline 369 + 9 new).
- `npx vitest run src/pages/cook/SmartChefPage.test.tsx` — 5 passed: empty state, a rendered
  suggestion card with no Confirm/Dismiss buttons and no chat panel present anywhere, the
  generating indicator/disabled button while pending, the inline error on a 502 (not a stuck
  generating state), and the direction field's text reaching the request body.
- `npx vitest run` (full frontend suite) — 201 passed, no regressions (baseline 196 + 5 new).
- `npx tsc -b` — clean.

### Completion Notes List

- Added `openai>=3.3.1` as a new dependency. Its actual installed API surface (`openai.
  AsyncOpenAI`, `client.chat.completions.create(model=, messages=, response_format=)`) was
  verified by direct introspection before writing any code against it, not assumed from prior
  knowledge — this release (and its `httpx2` dependency) postdates my training data, so I
  confirmed the constructor and method signatures still matched the plan before relying on them.
- `backend/clients/llm.py`'s `LLMClient` is the only place `openai` is imported anywhere in
  `backend/` (AD-12) — `AIService` depends only on its `generate_recipe(prompt) -> dict` method.
- **Caught and fixed a real concurrency bug before it shipped, not after**: the story's own plan
  called for `ai_service` to be a `providers.Factory`, matching every other service in
  `container.py`. Working through it, a Factory would hand each injected request its own fresh
  `AIService` instance with an empty `_in_flight` set, silently defeating AC3's "reject a second
  concurrent request" guard the moment two different requests happened to get two different
  instances. Registered both `llm_client` and `ai_service` as `providers.Singleton` instead — a
  deliberate, documented deviation from this container's otherwise-universal Factory pattern,
  verified by the deterministic concurrency test in `test_ai.py` (a test-controlled
  `asyncio.Event`, not a timing-dependent sleep).
- `AIService.generate_suggestion`'s stock-snapshot sort (`current_stock / min_stock_threshold`
  descending) implements the story's own "at-risk-of-waste" heuristic exactly, with the sort
  order itself communicated to the model as a prioritization instruction in the prompt text.
- The new `ExternalServiceError`/`AIGenerationFailedError` pair mirrors `AuthError`/
  `ConflictError`/`NotFoundError`'s existing base-class-plus-one-handler shape in
  `exceptions/handlers.py` exactly — one new handler function, one new registration line.
- Frontend: `SmartChefPage.tsx` replaces the Story 1.4-era placeholder with the request bar,
  generating/error/empty states, and a suggestion-card list — deliberately with no Confirm/
  Dismiss actions and no chat panel, both out of this story's scope (Stories 6.2/6.3), confirmed
  absent by an explicit negative assertion in the new test file, not just by omission.
  `requested_by` renders as a raw `User #{id}`, matching `StockMovement`'s own existing
  "Recorded by" precedent — no endpoint a Cook can call resolves a user id to a name.
- `OPENAI_MODEL` was configured to `gpt-5.6-sol`, a model name outside my training data (dated
  after my knowledge cutoff). The implementation makes no assumptions about which model is
  configured beyond the standard Chat Completions call shape; if that specific model name
  doesn't behave as expected against the real OpenAI API, it's a one-line config change, not a
  code change.

### File List

- `backend/pyproject.toml`, `backend/uv.lock`
- `backend/config.yaml`, `backend/.env.example`
- `backend/main.py`
- `backend/clients/llm.py`
- `backend/services/ai_service.py`
- `backend/exceptions/__init__.py`, `backend/exceptions/handlers.py`
- `backend/api/smart_chef.py`, `backend/api/router.py`
- `backend/container.py`
- `backend/data_models/ai.py`, `backend/data_models/__init__.py`
- `backend/tests/test_ai.py`
- `frontend/src/services/smartChefService.ts`
- `frontend/src/types/ai.ts`
- `frontend/src/pages/cook/SmartChefPage.tsx`
- `frontend/src/pages/cook/SmartChefPage.test.tsx`

## Review Findings

Reviewed by three parallel agents (Blind Hunter, Edge Case Hunter, Acceptance Auditor) against
this story's 8 ACs and `_bmad-output/project-context.md`. Several findings from all three agents
converged on the same underlying issues; consolidated below.

- [x] [Review][Patch] `LLMClient.generate_recipe` had no timeout — a hung or very slow OpenAI
  call would leave the calling Cook's `_in_flight` slot occupied indefinitely, since nothing else
  clears it (AD-14's guard has no recovery path of its own). Added a 45s timeout on the
  `chat.completions.create` call — `backend/clients/llm.py`
- [x] [Review][Patch] The stock-snapshot sort mixed scales inconsistently: `current_stock /
  min_stock_threshold` for a normal Ingredient, falling back to raw `current_stock` for a
  zero-threshold one — comparing a small dimensionless ratio against a raw quantity in the same
  `sorted()` call produces a meaningless order once both kinds of Ingredient are present.
  Extracted a `_waste_risk_rank` method that ranks a zero-threshold Ingredient with any stock as
  maximally at-risk instead — `backend/services/ai_service.py`
- [x] [Review][Patch] The parsed OpenAI response's shape was never validated — a syntactically
  valid JSON object missing `name`/`ingredients`/`plating` (or with the wrong types) would be
  persisted as a "successful" suggestion and only break later at render time on the frontend
  (`.ingredients.map(...)` on `undefined`). Added a shape check before persisting, raising
  `AIGenerationFailedError` on a mismatch, plus a new test
  (`test_a_malformed_llm_response_is_rejected_and_persists_nothing`) —
  `backend/services/ai_service.py`
- [x] [Review][Patch] No test proved the `_in_flight` guard is scoped per-Cook rather than
  global — every existing concurrency test used a single Cook. Added
  `test_a_different_cook_can_generate_concurrently`, which also caught and fixed a genuine
  deadlock in the test double itself (see Completion Notes) —
  `backend/tests/test_ai.py`
- [x] [Review][Patch] The one concurrency test used `await asyncio.sleep(0.1)` to "let the first
  request reach the in-flight set" — reintroducing exactly the timing-dependent flakiness the
  story's own Task 7 said to avoid via a controlled `asyncio.Event`. Replaced with a `started`
  event the fake client sets deterministically once its call has genuinely begun —
  `backend/tests/test_ai.py`
- [x] [Review][Patch] An empty ingredient list (no stock at all) was still sent to the model,
  risking a hallucinated, unusable suggestion. Added an explicit rejection before ever calling
  the LLM client, plus `test_no_ingredients_in_stock_is_rejected` —
  `backend/services/ai_service.py`
- [x] [Review][Patch] AC1 says "currently-available Ingredient stock," but the snapshot included
  out-of-stock (`current_stock == 0`) Ingredients. Added a `current_stock > 0` filter, plus
  `test_out_of_stock_ingredients_are_excluded_from_the_snapshot` —
  `backend/services/ai_service.py`
- [x] [Review][Patch] `SuggestionCard`'s ingredient `Chip` list used `key={ingredient.name}`,
  which collides if a generated recipe names the same ingredient twice. Added the array index to
  the key — `frontend/src/pages/cook/SmartChefPage.tsx`
- [x] [Review][Patch] `AsyncOpenAI(api_key="")` raises immediately at construction (confirmed
  empirically against the installed SDK) — since `llm_client` is a lazily-constructed Singleton,
  a never-configured key would have surfaced as a raw, unhandled error on the first real request
  rather than FR-21's intended graceful 502. `LLMClient` now defers construction until a real
  call is made, raising a plain `RuntimeError` `AIService` already catches and converts. New test:
  `test_llm_client_raises_a_plain_error_when_no_api_key_is_configured` —
  `backend/clients/llm.py`
- [x] [Review][Defer] `AIService`/`llm_client` are registered as `providers.Singleton`, which
  assumes a single-process deployment forever — if this app were ever scaled to multiple Uvicorn
  workers, each worker would get its own empty `_in_flight` set, silently defeating AC3's
  guarantee. Deferred: this matches the story's own explicit, stated scope ("a single-process
  demo app... none is warranted"); logged in `deferred-work.md` as a forward-looking note for if
  that assumption ever changes.
- [x] [Review][Defer] `list_suggestions` has no pagination or bound. Deferred: matches the
  already-accepted, already-logged unpaginated-growth pattern `GET /api/orders`/`KitchenService.
  list_active_items` established (see `deferred-work.md`'s existing entries) — not a new gap this
  story introduces.

**Verified as non-issues:**

- **`openai>=3.3.1` "looks fabricated/unverifiable"** — confirmed genuinely real by direct
  introspection of the installed package in this environment (`uv add openai` resolved and
  installed it from PyPI; `openai.__version__` prints `3.3.1`; `AsyncOpenAI`/`chat.completions.
  create`'s signatures were inspected directly, not assumed). This release postdates the
  reviewing model's training data the same way it postdates mine — the verification was done
  empirically, not from memory, precisely to guard against this.
- **The Completion Notes' `OPENAI_MODEL=gpt-5.6-sol` mention "contradicts" `config.yaml`'s
  `gpt-4o-mini` default** — no contradiction: `gpt-4o-mini` is the fallback used only when
  `OPENAI_MODEL` is unset (`${OPENAI_MODEL: "gpt-4o-mini"}`), and this environment's own
  `backend/.env` sets it explicitly, overriding the default as designed.
- **No cross-check of the model's returned ingredients against the actual stock snapshot, no
  prompt-injection defense on `direction`** — matches the PRD's own explicit, already-recorded
  assumption (§9, FR-18): *"enforced by prompt construction, not independently validated
  post-generation."* Not a gap introduced by this story.
- **AC7's "cost auditing" only stores `requested_by`, not token counts or dollar cost** — matches
  AC7's own literal definition of "attributable": *"carries the requesting User's id and its
  owning Recipe Suggestion."* The AC does not ask for token/cost tracking.
- **`llm_client`/`ai_service` registered as `Singleton` instead of the story's own literal `Task
  5` instruction to use `Factory`** — a deliberate, necessary, already-documented deviation
  (Completion Notes): a `Factory` would give every injected request its own empty `_in_flight`
  set, silently defeating AC3 the first time two different requests happened to get two
  different instances.
- **`openai>=3.3.1` deviates from Task 1's literal `>=1.0.0`** — the task text was written before
  implementation, without knowing the real current package version; using the actual, verified
  installed version instead of a guessed one is correct execution, not a defect.
- **`ingredient.unit.value` could raise if `unit` were null** — factually inapplicable:
  `Ingredient.unit` is a `NOT NULL` column (`backend/data_models/recipe.py`), so this state cannot
  occur.
- **Broad `except Exception` around the OpenAI call** — a standard, defensible pattern at exactly
  one already-isolated external-boundary call site, converting any SDK-internal exception
  hierarchy into one well-defined domain exception; does not wrap `_build_prompt` or any other
  internal logic.
- **`backend/uv.lock` "not updated" despite Task 1 claiming it was** — false positive from the
  diff scope given to reviewers (the lockfile was deliberately excluded from the reviewed diff
  as a low-signal generated file); confirmed actually committed via `git diff --stat` against the
  full repository history.
- **`config.yaml`'s `${OPENAI_API_KEY: ""}` differs from Task 1's literal `${OPENAI_API_KEY:}`**
  — functionally identical for the `_warn_if_no_openai_key()` falsy check; cosmetic only.

## Change Log

| Date | Change |
|---|---|
| 2026-08-22 | Story 6.1 created via bmad-create-story: the first external-API integration in the project. Establishes `backend/clients/`'s LLM adapter pattern (AD-12), the in-process reject-not-queue concurrency guard (AD-14), and graceful degradation (FR-21) that Stories 6.2/6.3 will reuse. Scoped tightly against the shared Smart Chef mockup: explicitly excludes Confirm/Dismiss (6.2) and chat (6.3). |
| 2026-08-22 | Implemented Story 6.1: `backend/clients/llm.py` (`LLMClient`, AD-12), `AIService.generate_suggestion`/`list_suggestions` (the in-process `_in_flight` set for AD-14, the surplus-ratio "at-risk-of-waste" sort heuristic), two new exception types (`SuggestionGenerationInProgressError`, `AIGenerationFailedError`/`ExternalServiceError`), `POST`/`GET /api/smart-chef/suggestions`, and container wiring — caught and fixed a real bug during implementation (both new providers needed to be `Singleton`, not `Factory`, or the concurrency guard would never actually trigger). Frontend: `SmartChefPage.tsx` replaces its placeholder with the request bar and suggestion-card list, no Confirm/Dismiss or chat (out of scope). 9 new backend tests (378 total), 5 new frontend tests (201 total). Full backend suite: 378/378 passed. Full frontend suite: 201/201 passed. `npx tsc -b` clean. |
| 2026-08-22 | Code review patch pass (three parallel agents): added a 45s timeout on the OpenAI call (an unbounded hang would lock a Cook out of the in-flight guard indefinitely); fixed a scale-mixing bug in the stock-snapshot sort for zero-threshold Ingredients; added response-shape validation before persisting a suggestion; filtered out-of-stock Ingredients from the snapshot (AC1's "currently-available" wording) and rejected the request cleanly when nothing is in stock at all; fixed a real deadlock caught while adding a new per-Cook-scoping concurrency test (two concurrent calls sharing one blocking test double); replaced a timing-dependent `asyncio.sleep` in the existing concurrency test with a deterministic event; made a never-configured API key fail gracefully (502) instead of raising raw at first use; fixed a React key-collision risk in the ingredient chip list. Deferred: the Singleton-based in-flight guard assumes single-process deployment forever (logged for revisit if that assumption changes). 5 new backend tests (383 total). Full backend suite: 383/383 passed. Full frontend suite: unaffected (key fix only), `tsc -b` clean. |
| 2026-08-22 | Manual testing (against a real OpenAI call) found a real bug: `httpClient.ts`'s global 5s fetch timeout is far shorter than a genuine generation call (observed ~9s, up to the backend's own 45s budget), producing a false "The server took too long to respond" even though the request had actually succeeded and persisted. Fixed by adding an optional per-call `timeoutMs` override to `apiRequest` (defaulting to the existing 5s for every other call site) and using a 50s override specifically for `useGenerateSuggestion`. Caught and fixed a second bug while testing the fix itself: the new test's mock `fetch` didn't respect the abort signal, so it hung for real rather than simulating a timeout — fixed the mock to reject with an `AbortError` on `signal`'s `abort` event, matching real `fetch` behavior. 1 new frontend test (202 total). `npx tsc -b` clean, full frontend suite 202/202 passed. |
