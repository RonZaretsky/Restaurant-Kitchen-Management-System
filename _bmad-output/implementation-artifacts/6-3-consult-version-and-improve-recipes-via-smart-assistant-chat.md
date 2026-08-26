---
baseline_commit: df9bd8171515d174d52e87c847335f8fd74214cf
epic: 6
story: 3
---

# Story 6.3: Consult, Version, and Improve Recipes via Smart Assistant Chat

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Cook,
I want to open a chat session with the Smart Assistant to discuss and iterate on a Recipe or Recipe Suggestion,
so that I can refine an idea through conversation instead of guessing.

## Scope note (read first)

**This is the last story in Epic 6 and the last story in the sprint plan.** It extends the same
AI infrastructure Stories 6.1/6.2 built (`clients/llm.py::LLMClient`, `services/ai_service.py::AIService`,
`api/smart_chef.py`, the `smart_chef` container Singletons) rather than building anything parallel
to it. Read Stories 6.1 and 6.2 in full before touching any file here — this story's Dev Notes
assume that context.

**There is no separate "Recipe" entity in this schema** (established by Story 6.2's own Scope
note, still true): a Dish's recipe is its set of `RecipeIngredient` rows keyed by `dish_id`. FR-20's
"a Recipe or a prior Recipe Suggestion" therefore means a Chat Session is tied to **either a `Dish`
or an `AIRecipeSuggestion`** — the two things in this schema a Cook could plausibly want to
discuss. This story adds that targeting to `AIChatSession`, which currently has no way to express
it (`id`, `user_id`, `title`, `created_at` only, unchanged since the Story 1.0 baseline).

**Schema change needed:** `AIChatSession` gains two new nullable FK columns, `dish_id` (→
`dishes.id`) and `suggestion_id` (→ `ai_recipe_suggestions.id`). **Exactly one must be set per
session** — enforced by a Pydantic `model_validator` on `CreateChatSessionRequest` (422 on
neither/both), mirroring `UpdateUserRequest.at_least_one_field`'s exact shape, not a DB `CHECK`
constraint (this codebase's established pattern for a business-rule invariant is application-level,
see `SuggestionAlreadyConfirmedError`/`SuggestionAlreadyDismissedError`'s mutual-exclusivity guard
in `AIService`, not a schema constraint). This needs its own Alembic migration (AD-4), the third
in Epic 6 after `f9cbd3ff5b87`.

**`title` is server-computed at creation, not a Cook-supplied field.** No mockup or AC asks the
Cook to name a session. Derive it from the target at creation time: `f"Chat about {dish.name}"` or
`f"Chat about {suggestion.generated_recipe['name']}"`. This is a captured-at-creation-time value
(same "snapshot, not a live join" precedent as `OrderItem.price_at_add`/`AIRecipeSuggestion.prompt_used`),
so it stays stable even if the underlying Dish is later renamed.

**Message-pair atomicity is this story's own application of AD-14.** The architecture spine's AD-14
explicitly binds `AIChatMessage` writes, not just `AIRecipeSuggestion`: *"The `AIRecipeSuggestion`/
`AIChatMessage` row is written only after the OpenAI call succeeds; a failed or timed-out call
persists nothing."* Read literally and applied here: when a Cook sends a message, **neither the
user's own `AIChatMessage` row nor the assistant's reply is inserted until the OpenAI call
succeeds** — both are inserted together, in one transaction, only on success. This is a deliberate
design decision, not the only defensible one (a looser reading would persist the user's message
immediately and only skip the assistant reply on failure), but it is the one that keeps every
session free of an unanswered dangling turn and matches `generate_suggestion`'s own
insert-only-after-success shape exactly, rather than inventing a second failure semantics for this
domain. State this reasoning in code (a docstring on `send_message`), don't just implement it
silently.

**Concurrency guard, scoped to the session, not the Cook.** `AIService._in_flight` (Story 6.1)
guards recipe-suggestion generation per-Cook. This story adds a second, independent in-process set,
`_chat_in_flight: set[int]` keyed by **session id**, guarding a chat send. A Cook may legitimately
have two different sessions open in two tabs (no AC forbids that), but two concurrent sends into
the *same* session would race the message-ordering guarantee AC2 relies on ("access to that
session's prior messages as conversational context") and could produce two assistant replies
answering the same prior state. Reject the second with a new `ChatMessageInProgressError` (409),
mirroring `SuggestionGenerationInProgressError`'s exact shape. `AIService` is already a
`providers.Singleton` (Story 6.1's own deliberate deviation from this container's Factory
pattern, for exactly this reason), so a second in-process set on the same instance works the same
way `_in_flight` already does — **no container.py change is needed**, both sets live on the one
existing Singleton.

**`LLMClient` gains a second method, not a second client (AD-12).** Story 6.1 already said this
story would "extend this same class rather than introducing a second OpenAI client" — do exactly
that. Add `async def send_chat_message(self, messages: list[dict[str, str]]) -> str`, reusing the
same `self._client.chat.completions.create(...)` call shape as `generate_recipe` but **without**
`response_format={"type": "json_object"}` (a chat reply is free text, not a structured suggestion)
and returning the plain string content instead of a parsed dict. Same `_REQUEST_TIMEOUT_SECONDS`
constant, same "let any exception propagate, the caller translates it" contract.

**The chat's system context is a live read of the target, not a snapshot.** Every recipe-domain
read elsewhere in this codebase is deliberately live, never stale (FR-23's "the currently-defined
lines, never a snapshot taken at an earlier time," verified end-to-end by Story 5.2's deduction
path). Building the system message from the target's *current* state on every send (not a value
captured once at session-creation) follows that same established convention — if a Dish's recipe
changes mid-conversation, the next message the assistant answers reflects the current recipe, not
a stale one.

**Frontend scope decision: the Dish-target creation path is backend-complete, but this story does
not add a new "discuss this dish" entry point to `DishesPage.tsx`.** No mockup shows one (the
Smart Chef IA row only describes "request a recipe suggestion... chat to iterate" — the Suggestion
side), and adding it would mean touching a file no story since 2.5 has needed to change for an
unbudgeted UI surface. This mirrors an established pattern in this codebase: a backend permission
or capability shipping ahead of its own frontend screen (`InventoryWriteDep` permitting Admin for
several stories before Story 2.6 built the UI for it; `OrderItemCancelDep` granting Cook/Admin
cancel with no matching frontend screen at the time). `POST /api/smart-chef/chat-sessions` fully
supports `dish_id`, tested directly against the API; the Cook-facing entry point this story
actually builds lives entirely on `SmartChefPage.tsx`, tied to a Recipe **Suggestion** (matching
the one UX mockup that exists, `key-smart-chef.html`). If time allows, a small "Discuss this dish"
affordance on `DishesPage.tsx` is welcome polish, not a blocker — no AC requires it.

**Frontend scope decision: "Discuss via chat" always starts a new session, it does not
find-or-resume an existing one for the same suggestion.** The mockup shows exactly one chat panel
tied to "the suggestion above," with no session-picker UI. Always-create is the simpler, mockup-
consistent behavior; **reopening any existing session (yours or another Cook's) is what the new
Chat Sessions list is for** — clicking a row there loads that exact session's history and lets the
Cook continue it. This is also what satisfies AC3 concretely: the Sessions list is the one place a
different Cook's session becomes reachable.

**AC3's "current Cook's own items first" sort applies to the Suggestions list too, not just the
new Sessions list — closing a gap Stories 6.1/6.2 explicitly left deferred.** Story 6.1's own Dev
Notes say this sort "if ever added... belongs client-side," and it was never built; 6.2 didn't
touch it either. This story's own AC3 restates the rule for "a session **or suggestion**"
verbatim, so build the client-side sort for both lists now rather than leaving the suggestion side
as further debt — a small, directly-AC-justified inclusion, not scope creep.

## Acceptance Criteria

1. **Given** a Cook opens a Chat Session tied to a Recipe or Recipe Suggestion, **when** they send
   a message, **then** it is persisted with its role (`user`/`assistant`) in order, retrievable as
   a full conversation (FR-20).
2. **Given** an existing session with prior messages, **when** a Cook sends a follow-up, **then**
   the assistant's response has access to that session's prior messages as conversational context
   (FR-20).
3. **Given** any Cook (not just the session's creator), **when** they open a session or suggestion
   created by a different Cook, **then** they can do so without special permission — the default
   list view just sorts the current Cook's own items first, as a personalization default, not an
   access boundary (FR-20, AD-9, AD-10).
4. **Given** the OpenAI call for a chat message fails or times out, **when** that happens, **then**
   the system surfaces a clear failure state and persists no dangling Chat Message with empty or
   null content (FR-21).
5. **Given** a Cook scrolls back through a session's history, **when** they do, **then** they can
   see an earlier iteration of the recipe under discussion — this ordered history IS the version
   record, no separate version-entity or diff UI in v1 (FR-20).
6. **Given** a Cook has no chat sessions, **when** the Smart Chef surface loads, **then** it shows
   "No chat sessions yet" (UX-DR15).

## Tasks / Subtasks

- [x] **Task 1: Backend — `AIChatSession.dish_id`/`suggestion_id` + migration (AC1, AC5)**
  - [x] `backend/data_models/ai.py`: add `dish_id: Mapped[int | None] = mapped_column(Integer,
    ForeignKey("dishes.id"), nullable=True)` and `suggestion_id: Mapped[int | None] =
    mapped_column(Integer, ForeignKey("ai_recipe_suggestions.id"), nullable=True)` to
    `AIChatSession`. Both nullable, no default — a session created before this story never existed
    (fresh feature), so there is no backfill concern.
  - [x] Generate the Alembic revision: `uv run alembic revision --autogenerate -m "add dish_id and
    suggestion_id to ai_chat_sessions"`, `down_revision` chaining onto `f9cbd3ff5b87` (Story 6.2's
    head). **Inspect the generated script** — confirm it only adds the two nullable columns + two
    FKs, no unrelated autogenerate noise, and that the downgrade correctly names both new FK
    constraints (Story 6.2's own review caught an unnamed-constraint downgrade bug on this exact
    shape — verify with `alembic downgrade --sql` before considering this done, trap the codebase
    has already hit once).

- [x] **Task 2: Backend — request/response schemas (`backend/data_models/ai.py`)** (AC1, AC3, AC5)
  - [x] `CreateChatSessionRequest(BaseModel)`: `dish_id: int | None = Field(default=None, gt=0,
    le=_INT4_MAX)`, `suggestion_id: int | None = Field(default=None, gt=0, le=_INT4_MAX)` (import
    `_INT4_MAX` from `data_models.menu`, the existing cross-module convention — see
    `api/smart_chef.py`'s own `SuggestionIdPath` for the precedent). `@model_validator(mode="after")`
    rejecting neither-set and both-set (mirrors `UpdateUserRequest.at_least_one_field`'s shape,
    inverted to "exactly one" instead of "at least one").
  - [x] `AIChatSessionResponse(BaseModel)`: `model_config = {"from_attributes": True}`; `id`,
    `user_id`, `dish_id: int | None`, `suggestion_id: int | None`, `title`, `created_at`. Plain
    `model_validate(session)` is sufficient here (unlike `AIRecipeSuggestionResponse`, nothing
    about a session is derived from a join).
  - [x] `CreateChatMessageRequest(BaseModel)`: `content: str = Field(min_length=1)`, `_strip_content
    = field_validator("content")(_strip_and_require_content)` (import from `data_models.user`, the
    existing shared helper — see `CreateCategoryRequest.name`'s precedent in `data_models/menu.py`
    for the exact import/wiring shape). No `max_length` bound — matches
    `CreateOrderItemRequest.notes`'s already-accepted unbounded-free-text precedent (see
    `deferred-work.md`'s Story 3.2 entry), a conscious match, not an oversight.
  - [x] `AIChatMessageResponse(BaseModel)`: `model_config = {"from_attributes": True}`; `id`,
    `session_id`, `role: ChatRole`, `content`, `created_at`.
  - [x] Export all four from `data_models/__init__.py` alongside the existing `ai.py` exports.

- [x] **Task 3: Backend — new exception types** (AC1, AC4)
  - [x] `backend/exceptions/__init__.py`: `ChatSessionNotFoundError(NotFoundError)`, detail `"Chat
    session not found"`. `ChatMessageInProgressError(ConflictError)`, detail `"Rejected, a reply is
    already generating for this session"`. `AIChatReplyFailedError(ExternalServiceError)`, detail
    `"Couldn't get a response right now"`. All three subclass an existing family — no new handler
    needed, same as every exception Stories 6.1/6.2 added.

- [x] **Task 4: Backend — `clients/llm.py` gains `send_chat_message`** (AD-12)
  - [x] Add `async def send_chat_message(self, messages: list[dict[str, str]]) -> str` to the
    existing `LLMClient` class (no new file, no second client — the class's own Story 6.1 docstring
    already commits to this). Same `self._client.chat.completions.create(model=self._model,
    messages=messages, timeout=_REQUEST_TIMEOUT_SECONDS)` call shape as `generate_recipe`, but no
    `response_format` (free-text reply, not JSON mode) and returns `response.choices[0].message.content`
    directly (a `str`, not `json.loads`'d). Reuses the module-level `_REQUEST_TIMEOUT_SECONDS`
    constant unchanged. Same `RuntimeError` if `self._client is None` (no API key configured) as
    `generate_recipe` already raises — no new no-key handling needed, one shared `if self._client
    is None` check per method, matching the existing shape.

- [x] **Task 5: Backend — `AIService` chat session + message methods** (AC1, AC2, AC3, AC4, AC5)
  - [x] `__init__`: add `self._chat_in_flight: set[int] = set()` alongside the existing
    `self._in_flight` (Story 6.1) — a second, independent in-process guard, keyed by session id not
    user id (see Scope note). No container.py change: `AIService` is already a `providers.Singleton`.
  - [x] `async def create_chat_session(self, db: AsyncSession, actor: User, dish_id: int | None,
    suggestion_id: int | None) -> AIChatSessionResponse`:
    - Exactly one of `dish_id`/`suggestion_id` is guaranteed non-None by the request schema's own
      validator — this method still only receives whichever the caller resolved, no re-validation
      of the XOR here (that's the schema's job, not the service's).
    - If `dish_id`: `db.get(Dish, dish_id)`, `DishNotFoundError` if missing (reuse the existing
      exception, imported from `exceptions`, don't add a duplicate). Title:
      `f"Chat about {dish.name}"`.
    - If `suggestion_id`: `db.get(AIRecipeSuggestion, suggestion_id)`, `SuggestionNotFoundError` if
      missing (reuse Story 6.2's exception). Title: `f"Chat about {suggestion.generated_recipe['name']}"`.
    - Insert the new `AIChatSession(user_id=actor.id, dish_id=..., suggestion_id=..., title=...)`,
      commit, refresh, log at `INFO`, return `AIChatSessionResponse.model_validate(session)`.
  - [x] `async def list_chat_sessions(self, db: AsyncSession, actor: User) ->
    Sequence[AIChatSessionResponse]`: `select(AIChatSession).order_by(AIChatSession.id.desc())`, no
    actor-based filtering (AD-9) — mirrors `list_suggestions`'s exact shape, `actor` accepted for
    signature symmetry only.
  - [x] `async def list_chat_messages(self, db: AsyncSession, actor: User, session_id: int) ->
    Sequence[AIChatMessageResponse]`: `db.get(AIChatSession, session_id)` first,
    `ChatSessionNotFoundError` if missing (AC1's "retrievable as a full conversation" implies a
    404 for a session that doesn't exist, not an empty list). Then
    `select(AIChatMessage).where(AIChatMessage.session_id == session_id).order_by(AIChatMessage.id.asc())`
    — **ascending**, chronological conversation order (AC5's "scroll back through history"),
    unlike `list_suggestions`'/`list_chat_sessions`' own newest-first descending order.
  - [x] `async def send_message(self, db: AsyncSession, actor: User, session_id: int, content: str)
    -> Sequence[AIChatMessageResponse]`:
    - `db.get(AIChatSession, session_id)`, `ChatSessionNotFoundError` if missing.
    - If `session_id in self._chat_in_flight`: raise `ChatMessageInProgressError` immediately, no
      DB read beyond the session lookup, no OpenAI call (mirrors `generate_suggestion`'s AC3 guard
      shape exactly, just keyed differently).
    - Add `session_id` to `self._chat_in_flight` before proceeding; remove it in a `finally` block
      wrapping everything below (same guarantee-of-removal shape as `_in_flight`).
    - Resolve the session's target (fetch the `Dish` or `AIRecipeSuggestion` it references — a
      live read, per this story's own Scope-note reasoning, not a value cached anywhere) and build
      a system message describing it (name, ingredients/recipe lines, plating/description as
      applicable) via a private `_build_chat_system_message` helper.
    - Load every existing `AIChatMessage` for this session, ordered ascending (reuse
      `list_chat_messages`'s query shape or factor a shared private helper — dev agent's call).
    - Build the full OpenAI `messages` list: `[system_message, *prior_messages_as_role_content,
      {"role": "user", "content": content}]`.
    - Call `self._llm_client.send_chat_message(messages)` inside a `try`; on any exception, log at
      `ERROR` with `actor.id`/`session_id`, raise `AIChatReplyFailedError` — **no `AIChatMessage`
      row is inserted on this path, neither the user's nor a reply's** (AC4, this story's own
      Scope-note reasoning on message-pair atomicity).
    - On success: insert **both** `AIChatMessage(session_id=session_id, role=ChatRole.user,
      content=content)` and `AIChatMessage(session_id=session_id, role=ChatRole.assistant,
      content=<the reply>)` in the same transaction, one `db.commit()`, refresh both, log at
      `INFO`, return `[AIChatMessageResponse.model_validate(user_msg),
      AIChatMessageResponse.model_validate(assistant_msg)]` (user then assistant, matching insertion
      order).
  - [x] `_build_chat_system_message(self, dish: Dish | None, suggestion: AIRecipeSuggestion | None,
    recipe_lines: Sequence[RecipeIngredient] | None) -> dict[str, str]` (private helper, exact
    signature/shape is the dev agent's call): instructs the model it is a chef assistant discussing
    a specific recipe (naming it), states the recipe's current ingredients/plating so the assistant
    can reason about it, and asks for plain conversational replies (no JSON mode this time — a
    system-message instruction, not `response_format`).

- [x] **Task 6: Backend — `api/smart_chef.py` routes** (AC1, AC2, AC3, AC4, AC5)
  - [x] `SessionIdPath = Annotated[int, Path(gt=0, le=_INT4_MAX)]` (mirrors `SuggestionIdPath`).
  - [x] `POST /api/smart-chef/chat-sessions` (`SmartChefWriteDep`, Cook-only — matches FR-20's own
    "As a Cook" framing and `generate_suggestion`'s existing precedent), body
    `CreateChatSessionRequest`, `response_model=AIChatSessionResponse`, `status_code=201`. Calls
    `ai_service.create_chat_session(db, actor, payload.dish_id, payload.suggestion_id)`.
  - [x] `GET /api/smart-chef/chat-sessions` (`SmartChefReadDep`, Cook + Admin — matches
    `list_suggestions`'s shared-read precedent), `response_model=list[AIChatSessionResponse]`.
  - [x] `GET /api/smart-chef/chat-sessions/{session_id}/messages` (`SmartChefReadDep`),
    `response_model=list[AIChatMessageResponse]`.
  - [x] `POST /api/smart-chef/chat-sessions/{session_id}/messages` (`SmartChefWriteDep`, Cook-only),
    body `CreateChatMessageRequest`, `response_model=list[AIChatMessageResponse]`,
    `status_code=201`. Calls `ai_service.send_message(db, actor, session_id, payload.content)`.
  - [x] New `_ERROR_DESCRIPTIONS`-style dicts per route, following this file's existing convention
    (`_GENERATE_ERROR_DESCRIPTIONS`/`_LIST_ERROR_DESCRIPTIONS`/`_DISMISS_ERROR_DESCRIPTIONS`) —
    404 "no matching Chat Session", 409 "a reply is already generating for this session", 502 "the
    OpenAI call failed, timed out, or returned unparseable content" (reworded per-route as those
    three existing dicts already do).
  - [x] No `container.py` change, no `container.wire(modules=[...])` change — `api.smart_chef` is
    already wired (Story 6.1), and no new provider is added this story.

- [x] **Task 7: Backend tests** (`backend/tests/test_ai.py`, extend)
  - [x] Extend `FakeLLMClient` with `chat_response: str | None`, `chat_error: Exception | None`, a
    `send_chat_message` method mirroring `generate_recipe`'s own configurable-behavior shape (reuse
    the same fixture, don't build a second fake).
  - [x] AC1: creating a session tied to a Dish, and separately to a Suggestion, then sending a
    message persists exactly two `AIChatMessage` rows (user, assistant) in that order, retrievable
    via the messages endpoint.
  - [x] Creating a session with neither `dish_id` nor `suggestion_id`, and with both, both 422.
  - [x] Creating a session against a nonexistent `dish_id`/`suggestion_id` is 404.
  - [x] AC2: a second message in an existing session — assert the `messages` list passed to the
    fake client's `send_chat_message` includes the prior turns' content, not just the new message
    (a real test of "has access to prior messages as context," not just an assumption).
  - [x] AC3: a session/suggestion created by Cook A is fully readable (session detail + messages)
    by Cook B with no special grant — a positive cross-Cook test, the same class of gap
    Story 3.4's review flagged as missing for cross-Waiter cancel (don't repeat that gap here).
  - [x] AC4: a mocked client that raises on `send_chat_message` — the endpoint answers 502, and
    **zero** `AIChatMessage` rows exist afterward for that session (query the table directly, not
    just the response).
  - [x] Chat concurrency guard: two sends into the *same* session, the second rejected 409 while
    the first is still in flight (deterministic via a controlled `asyncio.Event`, mirroring the
    existing suggestion-generation concurrency test's technique, not a timing sleep).
  - [x] A different session's send is NOT blocked by another session's in-flight send (mirrors the
    existing "a different Cook can generate concurrently" test's reasoning, applied per-session
    instead of per-Cook).
  - [x] AC5: three sequential messages in one session, `GET .../messages` returns all of them in
    ascending chronological order.
  - [x] AC6 is a frontend-only concern (empty-state copy) — no backend test needed beyond `GET
    /api/smart-chef/chat-sessions` returning `[]` on a fresh install (mirrors Story 6.1's own `GET
    .../suggestions` empty-list test).
  - [x] Role coverage: waiter/warehouse_manager 403 on both POST routes; unauthenticated 401;
    Admin can list sessions/messages via `SmartChefReadDep` but cannot create a session or send a
    message (403 on both POST routes, mirroring `SmartChefWriteDep`'s existing Cook-only coverage).

- [x] **Task 8: Frontend — `types/ai.ts`** (AC1, AC3, AC5)
  - [x] `AIChatSession` interface: `id`, `user_id`, `dish_id: number | null`,
    `suggestion_id: number | null`, `title`, `created_at`.
  - [x] `AIChatMessage` interface: `id`, `session_id`, `role: "user" | "assistant"`, `content`,
    `created_at`.

- [x] **Task 9: Frontend — `smartChefService.ts` gains chat hooks** (AC1, AC2, AC3, AC4, AC6)
  - [x] `CHAT_SESSIONS_QUERY_KEY = ["smart-chef", "chat-sessions"] as const` and
    `chatMessagesQueryKey(sessionId: number) = ["smart-chef", "chat-sessions", sessionId,
    "messages"] as const` (exported, matching `SUGGESTIONS_QUERY_KEY`'s own exported-constant
    precedent).
  - [x] `useChatSessions(): UseQueryResult<AIChatSession[], Error>` — `GET
    /api/smart-chef/chat-sessions`, `retry: false` (matches every other query hook in this file).
  - [x] `useChatMessages(sessionId: number | null): UseQueryResult<AIChatMessage[], Error>` — `GET
    /api/smart-chef/chat-sessions/${sessionId}/messages`, `enabled: sessionId !== null` (the
    established `number | null` + `enabled` gating shape, see `useOrderForTable`'s precedent —
    don't fire the request with a literal `null` in the URL).
  - [x] `useCreateChatSession(): UseMutationResult<AIChatSession, Error, { dish_id?: number;
    suggestion_id?: number }>` — `POST /api/smart-chef/chat-sessions`, invalidates
    `CHAT_SESSIONS_QUERY_KEY` `onSettled`.
  - [x] `useSendChatMessage(): UseMutationResult<AIChatMessage[], Error, { sessionId: number;
    content: string }>` — `POST /api/smart-chef/chat-sessions/${sessionId}/messages`, using the
    same `GENERATE_SUGGESTION_TIMEOUT_MS`-shaped override (50s; rename or share the constant, dev
    agent's call, but do not leave a chat send on the 5s default the way `useGenerateSuggestion`'s
    own manual-test finding proves would falsely time out a real OpenAI-backed call). Invalidates
    `chatMessagesQueryKey(sessionId)` `onSettled` (a 409/502 both mean the client's view of "what
    just happened" may be stale, matching every other mutation in this file).

- [x] **Task 10: Frontend — `components/ai/ChatPanel.tsx`** (new) (AC1, AC2, AC4, AC5)
  - [x] A self-contained chat panel: renders `useChatMessages(sessionId)`'s messages (user/assistant
    styled distinctly, per `key-smart-chef.html`'s `.msg.user`/`.msg.assistant` visual reference —
    `DESIGN.md` has no formal `{components.chat-*}` token for this, the mockup's own inline styles
    are the closest available reference, translate to MUI primitives rather than inventing a new
    design-system entry), a text input + Send button wired to `useSendChatMessage`, an in-flight
    indicator while pending (matching the mockup's `generating-pill` treatment, reused conceptually
    not literally — this codebase already has `CircularProgress` + text for this exact pattern in
    `SmartChefPage.tsx`'s own generating state, follow that precedent instead of a new spinner
    shape), and an inline `Alert` on `isError` (AC4 — a failed send must render a clear failure
    state, not a silently-stuck "sending").
  - [x] Loading/empty state for the message list itself: while `useChatMessages` is loading, a
    skeleton or spinner (dev agent's call on exact treatment, `RowsSkeleton` is available); an
    empty message list (a freshly created session with zero messages yet) renders no special copy,
    it is just a blank panel ready for the first message — no AC names an empty-messages state
    distinct from "No chat sessions yet" (AC6, which is about the *sessions list*, not one open
    session's own message history).

- [x] **Task 11: Frontend — `SmartChefPage.tsx` gains chat** (AC1, AC2, AC3, AC4, AC6)
  - [x] Add a "Discuss via chat" button to `SuggestionCard` (alongside the existing card content,
    still with no Confirm/Dismiss — those stay out of scope here exactly as Stories 6.1/6.2 already
    established). Clicking it calls `useCreateChatSession().mutate({ suggestion_id: suggestion.id
    })`, and on success sets that new session as the page's "active session" (local `useState`),
    rendering `<ChatPanel sessionId={activeSessionId} />` inline next to/below the card — mirrors
    the mockup's card+chat-panel side-by-side layout as closely as this page's existing single-
    column card list allows (dev agent's call on exact layout; the mockup's two-column grid is not
    mandatory to replicate pixel-for-pixel, matching this codebase's own "mocks illustrate, the
    spine and epics govern" rule from `EXPERIENCE.md`).
  - [x] Add a "Chat Sessions" section: `useChatSessions()`, sorted client-side with the current
    Cook's own sessions first (`user_id === currentUser.id`, via the existing `useCurrentUser()`
    hook from `authService.ts`) while preserving each group's own newest-first order — the AD-10
    sort this story's own Scope note commits to building for real. Empty state: **"No chat sessions
    yet."** (AC6, exact copy per `EXPERIENCE.md`'s State Patterns table — note the trailing period,
    matching `SmartChefPage.tsx`'s existing "No recipe suggestions yet." precedent). Clicking a
    session row sets it as the active session and renders `<ChatPanel sessionId={session.id} />`
    the same way the suggestion-card path does.
  - [x] Also add the same current-Cook-first client-side sort to the existing Suggestions list
    (Scope note's own justification — AC3 names both nouns). Do not add a second server-side query
    parameter for this (AD-9/AD-10 forbid it) — a plain client-side sort over the already-fetched
    list.

- [x] **Task 12: Frontend tests**
  - [x] `SmartChefPage.test.tsx`: "No chat sessions yet." empty state renders (AC6); a session
    created by a different user still appears in the Sessions list (AC3, positive test — mirrors
    Task 7's backend cross-Cook test); clicking "Discuss via chat" on a suggestion creates a
    session and renders the chat panel; sending a message in the panel shows both the new user and
    assistant messages after success; a failed send shows an inline error, not a stuck sending
    state (AC4); current-Cook's-own items render first in both the Sessions list and the
    Suggestions list, given a fixture with items from two different users.
  - [x] `ChatPanel.test.tsx` (new, if extracted as its own file — dev agent's call, matching Story
    6.2's own "extract a shared component, dev agent's call" precedent) or folded into
    `SmartChefPage.test.tsx`: covers the panel's own loading/error/generating states directly.

- [x] **Task 13: Full regression pass**
  - [x] `uv run pytest -q` (backend) — zero regressions.
  - [x] `pnpm test` (frontend) — zero regressions.
  - [x] `npx tsc -b` — clean.

## Dev Notes

### Architecture compliance

- **AD-4** (every schema change ships its own Alembic revision): Task 1's migration, chained onto
  `f9cbd3ff5b87` (Story 6.2's head), inspected before committing per the trap this exact migration
  shape already tripped once (Story 6.2's own unnamed-FK-constraint downgrade bug).
- **AD-9/AD-10** (Role-level-only permissions, sort-not-filter personalization): `list_chat_sessions`/
  `list_chat_messages` take no actor-based filter, matching `list_suggestions`'s own precedent
  exactly. "Current Cook's own first" is a client-side sort for both the new Sessions list and the
  pre-existing Suggestions list, never a second server-side query parameter.
- **AD-12** (Smart Chef client behind an interface): `send_chat_message` is added to the *existing*
  `LLMClient` class, not a new client — `services/` still only ever imports `clients.llm.LLMClient`,
  never `openai` directly.
- **AD-14** (request lifecycle integrity, explicitly binding `AIChatMessage` writes per its own
  spine text): this story's two concrete implementations are the per-session `_chat_in_flight`
  reject-not-queue guard, and the strict "both messages inserted only after the OpenAI call
  succeeds" ordering — no dangling/partial `AIChatMessage` on failure (AC4).
- **AD-1** (append-only `container.wire(modules=[...])`): unchanged this story — `api.smart_chef`
  is already wired, no new module added.
- **PRD §4.5 feature NFR** ("every OpenAI API call is attributable to a specific User and Chat
  Session/Suggestion for later cost auditing," Story 6.1's own AC7 for the suggestion side): no
  new column is needed for the chat side — every `AIChatMessage` belongs to an `AIChatSession`,
  and `AIChatSession.user_id` already carries the requesting Cook, so the same attributability
  holds structurally. No hard per-user/per-day cost cap is in scope here either (confirmed policy
  decision, PRD §8/§9), unchanged from Story 6.1.

### Current state of the files this story touches (read before editing)

- **`backend/data_models/ai.py`**: `AIChatSession` currently has `id`, `user_id`, `title`,
  `created_at` only — no `dish_id`/`suggestion_id` (this story's own schema addition). `ChatRole`
  enum (`user`/`assistant`) already exists and is reused unchanged. `AIRecipeSuggestion`/
  `AIRecipeSuggestionResponse` (Stories 6.1/6.2) are read-only reference material here, not
  modified by this story except where noted.
- **`backend/services/ai_service.py`**: `generate_suggestion`/`list_suggestions`/
  `dismiss_suggestion` (Stories 6.1/6.2) are the literal templates for this story's four new
  methods — same insert-only-after-success shape, same private-`_get_*`-seam style, same
  logger-before-raise convention. `self._in_flight` (Story 6.1) is untouched; this story adds a
  sibling `self._chat_in_flight`, not a modification to the existing one.
- **`backend/clients/llm.py`**: `LLMClient.generate_recipe` (Story 6.1) is the exact template for
  the new `send_chat_message` method — same class, same `_REQUEST_TIMEOUT_SECONDS` constant, same
  `self._client is None` guard, different `response_format` (none) and return type (`str`, not
  `dict`).
- **`backend/api/smart_chef.py`**: `SmartChefWriteDep`/`SmartChefReadDep`/`SmartChefAdminDep`
  (Stories 6.1/6.2) are reused unchanged — no new dependency needed, session-create/message-send
  are Cook-only via the existing `SmartChefWriteDep`, session/message reads are Cook+Admin via the
  existing `SmartChefReadDep`. `SuggestionIdPath` is the literal template for the new
  `SessionIdPath`.
- **`backend/container.py`**: **not touched by this story.** `llm_client`/`ai_service` are already
  registered as `providers.Singleton` (Story 6.1's own deliberate deviation, still the correct
  shape here — see this story's own Scope note on why the chat concurrency guard needs the same
  Singleton).
- **`frontend/src/types/ai.ts`**: `AIRecipeSuggestion` (Stories 6.1/6.2) is the existing content;
  this story adds two new interfaces alongside it, no changes to the existing one.
- **`frontend/src/services/smartChefService.ts`**: `useSuggestions`/`useGenerateSuggestion`/
  `useDismissSuggestion` (Stories 6.1/6.2) are the literal hook-shape templates — same
  `retry: false`, same invalidate-`onSettled` convention, same per-call-`timeoutMs`-override
  pattern `GENERATE_SUGGESTION_TIMEOUT_MS` already established for exactly this "OpenAI call takes
  longer than an ordinary CRUD request" reason.
- **`frontend/src/pages/cook/SmartChefPage.tsx`**: `SuggestionCard`/`SuggestionSummary` (Stories
  6.1/6.2) are read for their exact card layout before adding the "Discuss via chat" action to
  `SuggestionCard`. The page's existing request-bar/generating/error/empty-state code for
  suggestions is unchanged except for the new current-Cook-first sort.
- **`frontend/src/components/ai/`**: currently holds `SuggestionSummary.tsx` (Story 6.2) and
  `ConfirmSuggestionDialog.tsx` (Story 6.2). This story adds `ChatPanel.tsx` alongside them, the
  same folder, no new top-level `components/` subfolder.

### Project Structure Notes

Files touched:
- `backend/data_models/ai.py` — **UPDATE**, `AIChatSession.dish_id`/`.suggestion_id`,
  `CreateChatSessionRequest`, `AIChatSessionResponse`, `CreateChatMessageRequest`,
  `AIChatMessageResponse`.
- `backend/data_models/__init__.py` — **UPDATE**, export the four new models.
- `backend/alembic/versions/` — **NEW** migration file (autogenerated, inspected before commit,
  chained onto `f9cbd3ff5b87`).
- `backend/services/ai_service.py` — **UPDATE**, four new methods
  (`create_chat_session`/`list_chat_sessions`/`list_chat_messages`/`send_message`) plus
  `_build_chat_system_message` and `self._chat_in_flight`.
- `backend/clients/llm.py` — **UPDATE**, `send_chat_message` added to the existing `LLMClient`.
- `backend/exceptions/__init__.py` — **UPDATE**, three new exception types (no new handlers).
- `backend/api/smart_chef.py` — **UPDATE**, four new routes + `SessionIdPath`.
- `backend/container.py` — **NOT TOUCHED**.
- `backend/tests/test_ai.py` — **UPDATE**, new coverage, extended `FakeLLMClient`.
- `frontend/src/types/ai.ts` — **UPDATE**, `AIChatSession`/`AIChatMessage` interfaces added.
- `frontend/src/services/smartChefService.ts` — **UPDATE**, four new hooks + two new query keys.
- `frontend/src/components/ai/ChatPanel.tsx` — **NEW**.
- `frontend/src/pages/cook/SmartChefPage.tsx` — **UPDATE**, chat sessions section, "Discuss via
  chat" action, current-Cook-first sort on both lists.
- `frontend/src/pages/cook/SmartChefPage.test.tsx` — **UPDATE**, new coverage.
- `frontend/src/components/ai/ChatPanel.test.tsx` — **NEW** (if extracted separately; otherwise
  folded into `SmartChefPage.test.tsx`, dev agent's call).

**Deliberately NOT touched**: `frontend/src/pages/cook/DishesPage.tsx` (no Dish-triggered chat
entry point this story, see Scope note), `router.tsx`/`navigationConfig.ts` (Smart Chef is already
routed and navigable, Story 6.1), `frontend/src/pages/admin/RecipeSuggestionsPage.tsx` (chat is a
Cook-only surface per FR-20's own framing, the Admin review page's own scope from Story 6.2 is
unaffected).

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 6.3`] — this story's AC source,
  verbatim.
- [Source: `_bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md`,
  FR-20, FR-21, §4.5 feature NFR] — the full requirement text, including the confirmed "manage
  versions conversationally, no separate version-entity/diff UI" interpretation (AC5) and the
  shared-access/personalization-sort decision (AC3).
- [Source: `_bmad-output/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md`, AD-9, AD-10,
  AD-12, AD-14] — the client-interface rule, the role-level-permissions/sort-not-filter rule, and
  the request-lifecycle-integrity rule (explicitly binding `AIChatMessage` writes) this story
  implements for the chat domain.
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../EXPERIENCE.md`, "Cook: Smart Chef" IA
  row, State Patterns table ("No chat sessions yet."), Component Patterns ("Recipe request bar")] —
  the exact empty-state copy and the confirmation that the mocks/spine govern over any mockup
  detail this story's chat layout can't replicate pixel-for-pixel.
- [Source: `_bmad-output/planning-artifacts/ux-designs/.../mockups/key-smart-chef.html`] — the
  visual reference for the chat panel (`.chat-panel`/`.msg.user`/`.msg.assistant`), the closest
  available reference since `DESIGN.md` defines no formal chat component tokens.
- [Source: `_bmad-output/implementation-artifacts/6-2-confirm-a-recipe-suggestion-into-a-live-dish.md`]
  — the previous story's Scope note establishing "no separate Recipe entity, a Dish's recipe is its
  `RecipeIngredient` rows," directly reused here to justify targeting `AIChatSession` at `Dish`
  rather than inventing a Recipe entity; also its Alembic-migration review finding (unnamed FK
  constraint breaking downgrade) this story's own migration must not repeat.
- [Source: `_bmad-output/implementation-artifacts/6-1-generate-a-recipe-suggestion-from-current-stock.md`]
  — the original AD-12/AD-14 implementation patterns (`LLMClient`, `_in_flight`,
  insert-only-after-success) this story extends rather than reinvents; its own stated intent that
  "future OpenAI calls (Story 6.3's chat) extend this same class."
- [Source: `backend/data_models/ai.py`, `backend/services/ai_service.py`, `backend/clients/llm.py`,
  `backend/api/smart_chef.py`] — read in full during this story's creation; current state
  documented above under "Current state of the files this story touches."
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md`, Story 3.2 entry] — the
  accepted unbounded-free-text precedent (`CreateOrderItemRequest.notes`) this story's
  `CreateChatMessageRequest.content` deliberately matches rather than diverges from.

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5

### Debug Log References

- Alembic autogenerate for the new `ai_chat_sessions.dish_id`/`suggestion_id` columns emitted the
  same unnamed-FK-constraint shape Story 6.2's own review already caught once
  (`create_foreign_key(None, ...)`, whose downgrade cannot target it). Renamed both constraints to
  match Postgres's own default naming (`ai_chat_sessions_dish_id_fkey`,
  `ai_chat_sessions_suggestion_id_fkey`) before ever running it, then verified both directions
  against the real dev database: `alembic downgrade --sql` renders valid, named `DROP CONSTRAINT`
  statements, and a live `alembic downgrade f9cbd3ff5b87` followed by `alembic upgrade head`
  round-trips cleanly.
- The first draft of the new backend tests created Dish fixtures via `POST /api/menu/dishes`
  while logged in as the Cook under test, which is admin-only and returned 403. Switched
  `_create_dish` to insert the Category/Dish rows directly against `db_session`, the same
  direct-insert precedent `_create_ingredient` already established in this file, rather than
  juggling a login switch just to seed a fixture.

### Completion Notes List

- `AIChatSession` gained two new nullable FK columns, `dish_id` and `suggestion_id`; exactly one
  is enforced by `CreateChatSessionRequest`'s `model_validator` (422 on neither/both), not a DB
  constraint, matching `UpdateUserRequest.at_least_one_field`'s established shape. Migration
  chained onto `f9cbd3ff5b87` as `ai_chat_sessions_dish_id_fkey`/`_suggestion_id_fkey`.
- `AIService` gained `create_chat_session`/`list_chat_sessions`/`list_chat_messages`/`send_message`
  plus a private `_build_chat_system_message` helper and a second in-process guard,
  `_chat_in_flight: set[int]`, keyed by session id (independent of the existing per-Cook
  `_in_flight`). `send_message` builds the system message from a *live* read of the session's
  target (Dish + its current Recipe Ingredient lines, or a Recipe Suggestion's stored
  `generated_recipe`) on every send, never a value cached at session creation.
- Message-pair atomicity (AD-14): both the user's and the assistant's `AIChatMessage` rows are
  inserted together in one transaction, only after `LLMClient.send_chat_message` succeeds; any
  failure raises `AIChatReplyFailedError` (502) with zero rows persisted, verified directly against
  the `ai_chat_messages` table, not just the response.
- `LLMClient.send_chat_message` was added to the existing class (AD-12) — same call shape as
  `generate_recipe`, no `response_format`, returns the plain string reply. `services/` still only
  ever imports `clients.llm.LLMClient`.
- `api/smart_chef.py` gained four routes (`POST`/`GET /chat-sessions`,
  `GET`/`POST /chat-sessions/{id}/messages`) on the existing `SmartChefWriteDep`/`SmartChefReadDep`
  — no `container.py` change, `api.smart_chef` was already wired in Story 6.1.
- Frontend: `smartChefService.ts` gained `useChatSessions`/`useChatMessages`/
  `useCreateChatSession`/`useSendChatMessage` (the send mutation uses a 50s timeout override,
  matching `useGenerateSuggestion`'s own OpenAI-call reasoning). New `components/ai/ChatPanel.tsx`
  renders a session's message history, a "Ask a follow-up" input, a generating indicator, and an
  inline error Alert on a failed send. `SmartChefPage.tsx` gained a "Discuss via chat" action per
  suggestion card (always creates a new session, per the Scope note) and a new Chat Sessions
  section with the "No chat sessions yet." empty state (AC6); both the Suggestions and Sessions
  lists now sort the current Cook's own items first client-side (AC3/AD-10), never a second
  server-side query parameter. `DishesPage.tsx` was deliberately not touched, per the story's own
  scope decision.
- Full regression pass: 414 backend tests pass (`uv run pytest -q`), 220 frontend tests pass
  (`pnpm test` / vitest), `tsc -b` clean. No ruff/mypy or eslint configuration exists in this repo
  to run.

### File List

- `backend/data_models/ai.py` (modified)
- `backend/data_models/__init__.py` (modified)
- `backend/alembic/versions/ff8b89322b7c_add_dish_id_and_suggestion_id_to_ai_.py` (new)
- `backend/services/ai_service.py` (modified)
- `backend/clients/llm.py` (modified)
- `backend/exceptions/__init__.py` (modified)
- `backend/api/smart_chef.py` (modified)
- `backend/tests/test_ai.py` (modified)
- `frontend/src/types/ai.ts` (modified)
- `frontend/src/services/smartChefService.ts` (modified)
- `frontend/src/components/ai/ChatPanel.tsx` (new)
- `frontend/src/components/ai/ChatPanel.test.tsx` (new)
- `frontend/src/pages/cook/SmartChefPage.tsx` (modified)
- `frontend/src/pages/cook/SmartChefPage.test.tsx` (modified)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified)
- `_bmad-output/implementation-artifacts/6-3-consult-version-and-improve-recipes-via-smart-assistant-chat.md` (modified)

## Change Log

- **Implementation pass (2026-08-26)**: implemented all 13 tasks per the story's own sequencing —
  schema + migration (Task 1), request/response schemas (Task 2), new exception types (Task 3),
  `LLMClient.send_chat_message` (Task 4), `AIService`'s four chat methods plus the
  `_chat_in_flight` guard (Task 5), the four new `api/smart_chef.py` routes (Task 6), backend test
  coverage (Task 7), frontend types/hooks/`ChatPanel`/`SmartChefPage` wiring (Tasks 8-11), frontend
  test coverage (Task 12), and a full regression pass (Task 13). No deviations from the story's
  Dev Notes guardrails; the two implementation notes worth recording (the FK-constraint-naming
  trap and the admin-only Dish-fixture 403) are captured under Debug Log References above. The
  optional "Discuss via chat" entry point on `DishesPage.tsx` was deliberately not added, per the
  story's own explicit scope decision.
