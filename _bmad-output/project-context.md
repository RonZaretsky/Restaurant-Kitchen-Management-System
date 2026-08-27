---
project_name: 'Restaurant-Kitchen-Management-System'
user_name: 'Ron'
date: '2026-08-02'
supersedes: 'project-context.md dated 2026-07-24 (stale: predated the Postgres/SQLAlchemy merge, the architecture spine, the UX spines, and the epic breakdown)'
sources:
  - 'backend/ and frontend/ as they exist on disk, verified 2026-08-02'
  - '_bmad-output/planning-artifacts/architecture/architecture-Restaurant-Kitchen-Management-System-2026-07-30/ARCHITECTURE-SPINE.md'
  - '_bmad-output/planning-artifacts/epics.md'
status: 'complete'
optimized_for_llm: true
---

# Project Context for AI Agents

_Critical rules and current-state facts for anyone implementing code here. Focus is on the
unobvious: what exists vs. what is only decided, and the traps that fail silently._

---

## The single most important distinction: installed vs. decided

Many technologies are **ratified in the architecture spine but not yet in any manifest.** Do not
`import` them until the story that adopts them has run — and when you do adopt one, add it to the
manifest in that same change.

| | Installed and usable **now** | Decided, **not yet installed** (adopting story) |
|---|---|---|
| **Backend** | fastapi, uvicorn[standard], dependency-injector, pyyaml, loguru, sqlalchemy[asyncio], asyncpg, alembic, bcrypt, pyjwt, python-dotenv, pytest + pytest-asyncio + httpx | openai (Story 6.1) |
| **Frontend** | react 19, react-dom, typescript ~5.7.2, vite ^6, @vitejs/plugin-react, vitest + @testing-library/react + @testing-library/user-event, react-router 7.8.0 (Story 1.4), MUI v9 + @mui/icons-material + @emotion/react + @emotion/styled (Story 1.4), @tanstack/react-query v5 (Story 1.4) | none |

Authoritative manifests: `backend/pyproject.toml` + `backend/uv.lock`, `frontend/package.json` +
`frontend/pnpm-lock.yaml`. Lockfiles are authoritative — regenerate via `uv sync` / `pnpm install`
after editing a manifest; never hand-edit a lockfile.

- Backend runs on Python >=3.12, managed by `uv`. Run from inside `backend/`: `uv run python main.py`.
- Frontend is pinned to `pnpm@9.15.0` via `packageManager`. **Never use npm or yarn.**
- Orchestration: Docker Compose — Postgres 16-alpine, backend :8000, frontend :3000 host → :80 container.

---

## Current state of the code

**Backend, layered and wired. Epic 2's authoring domain is complete: auth, users, real-time push, inventory, menu (including Recipe Ingredient CRUD), and Restaurant Tables. Epic 3 (Table Service & Order Taking) is complete: Story 3.1 opened a Table into a new Order, Story 3.2 added Order Items (list/add) and the table_id → Order read the detail page needs, Story 3.3 gave `RealtimeService` its first two producers so both of those now push live, Story 3.4 added edit/cancel for a pending or in_preparation Order Item (no live push for either, by design at the time — both gained one later, Story 5.5). Epic 4 (Warehouse Inventory Operations & Low-Stock Alerts) is **complete**: Story 4.1 added manual Stock Movement recording (purchase/waste/adjustment), `InventoryService`'s first write to `Ingredient.current_stock` since Story 2.1 created the column. Story 4.2 added the Low-Stock Alert as a derived (not stored) state — `GET /api/inventory/alerts`, plus `InventoryService`'s first `RealtimeService` producer, a crossing-triggered `inventory.alerts_changed` push to `warehouse_manager` connections only. Story 4.3 added shortage visualization to the Ingredients list (warning icon + red row, sort-to-top) by reusing Story 4.2's `useAlerts()` as-is — the first Epic 4 story with zero backend changes. Epic 5 (Kitchen Fulfillment, Automatic Stock Deduction & Close-Out) is **complete**: Story 5.1 opened it with a read-only Kitchen Display — a brand-new `kitchen` domain (first genuine join in `backend/services/`), `order.item_added` and `TablesReadDep` both widened to include Cook. Story 5.2 made the Kitchen Display's cards clickable: `OrderService` gained `pick_up_item`/`mark_item_ready` (its first cross-service collaborator, `InventoryService`, reusing rather than duplicating the row-lock/threshold-crossing stock-deduction machinery), and a new `order.item_status_changed` event. Story 5.3 made `Order.status` derive live from its items. Story 5.4 added the guarded `mark_served`/`close_order` transitions and Order total computation. Story 5.5 closed the live-update gap on cancel/edit. Epic 6 (Smart Chef, Recipe Suggestions & Assistant Chat) is under way: Story 6.1 added the project's first external-API integration — `backend/clients/llm.py` (the only place `openai` is imported, AD-12), `AIService` (a deliberate `Singleton`, not `Factory`, for its in-process concurrency guard), and `POST`/`GET /api/smart-chef/suggestions`, letting a Cook generate an AI recipe suggestion from current stock. Story 6.2 let an Admin confirm a Recipe Suggestion into a live Dish (or dismiss it): `Dish.source_suggestion_id` is a nullable, **unique** FK (closes a double-confirm race — two concurrent creates citing the same suggestion, one loses to an `IntegrityError` translated to a 409) and `AIRecipeSuggestion.dismissed` is the one new stored column; "confirmed" stays derived (a suggestion is confirmed iff some `Dish.source_suggestion_id` matches it, resolved via `AIService.list_suggestions`'s outerjoin), never a stored flag. `POST /api/smart-chef/suggestions/{id}/dismiss` is Admin-only. The frontend design changed twice during this story's own manual testing: the original "navigate to Menu Management with prefilled fields" hand-off was reworked into an in-place `ConfirmSuggestionDialog` (creates the Dish AND its Recipe Ingredient lines together, composing the same two existing endpoints, no new backend action), and a follow-up fix made the dialog PATCH the Dish available immediately once a recipe line lands, reusing `update_dish`'s existing `EmptyRecipeError`/AD-8 guard as the safety net rather than leaving the Admin to flip it by hand.**

```
backend/
  main.py            app factory + lifespan; calls exceptions/handlers.py's register_exception_handlers(app)
  container.py       DeclarativeContainer: config, logging, database, connection_registry, auth_service,
                     user_service, inventory_service, menu_service, table_service, order_service,
                     realtime_service
  constants.py       SETTINGS (app name, version, config path)
  config.yaml        ${ENV_VAR: default} interpolation, parsed by utils.load_config
  utils.py           config loader
  entrypoint.sh       Docker CMD: alembic upgrade head, then the app. Never in the lifespan.
  alembic/            async-template migration environment; alembic/versions/ now has 5 revisions
                     (baseline, two case-insensitive-index fixes, Story 3.2's price_at_add column
                     add, Story 3.4's cancelled OrderItemStatus enum value). Neither Story 2.3 nor
                     2.4 needed one, both ORM schemas already fit. Adding a Postgres enum value is
                     the one migration shape autogenerate cannot produce (empty upgrade); it must be
                     hand-written as `op.execute("ALTER TYPE ... ADD VALUE '...'")`, and its
                     downgrade() must raise rather than fake a DROP TYPE, since Postgres cannot
                     cleanly remove an enum value
  tests/              conftest.py + one test file per module below
  api/router.py      aggregator; include_router()s auth, admin, inventory, menu, tables, orders, websocket
  api/auth.py        POST /auth/login (sets the JWT httpOnly cookie), GET /auth/me (Story 1.4, the
                     frontend's only way to learn who is logged in across a page reload), POST
                     /auth/logout (Story 1.7: clears the cookie, deliberately NOT gated behind
                     CurrentUserDep so it succeeds even against a missing/expired cookie)
  api/admin.py        Story 1.3's User-management routes, the reference implementation for
                     role-gated routes with declared error responses (see trap 8)
  api/inventory.py    Story 2.1: POST /api/inventory/ingredients, the first route to permit more
                     than one Role (admin, warehouse_manager). Story 2.3 added GET on the same two
                     Roles (InventoryReadDep); Story 2.5 widened InventoryReadDep to admin,
                     warehouse_manager, cook (a Cook needs Ingredient names to render a Dish's
                     recipe); Story 4.3 should extend it further, not duplicate it. Story 4.1 added
                     GET /ingredients/{id}, GET /ingredients/{id}/movements, and POST
                     /ingredients/{id}/movements, all reusing InventoryReadDep/InventoryWriteDep
                     unchanged, no new Role scoping needed. A module-level IngredientIdPath
                     (Path(gt=0, le=_INT4_MAX), _INT4_MAX imported from data_models.menu) bounds
                     the new path ids the same way trap 16 already requires of request bodies,
                     matching api/orders.py's TableIdPath/OrderIdPath/ItemIdPath shape; api/menu.py
                     already declares its own same-named IngredientIdPath independently for its
                     recipe-ingredient routes, the two are unrelated module-level constants that
                     happen to share a name, not one shared definition. Story 4.2 added
                     GET /alerts, also on InventoryReadDep (admin, warehouse_manager, cook can all
                     read it, though only warehouse_manager has a frontend screen for it — an
                     intentional backend-ahead-of-UI grant, not a gap)
  api/menu.py         Story 2.2: POST /categories, POST /dishes, PATCH /dishes/{id}, admin-only.
                     Story 2.3 added GET /categories, GET /dishes, and Recipe Ingredient CRUD at
                     /dishes/{dish_id}/recipe-ingredients (GET/POST/PATCH/DELETE). Story 2.5 split
                     a new MenuReadDep (admin, cook) off the three GET routes; every write route
                     stays on the original MenuDep (admin-only), unchanged. Story 3.2 split GET
                     /dishes alone onto a narrower DishCatalogReadDep (admin, cook, waiter): a
                     Waiter needs the dish list to add Order Items but never a Dish's recipe, so
                     /categories and /recipe-ingredients stay on MenuReadDep, unwidened
  api/tables.py       Story 2.4: GET /api/tables, POST /api/tables, PATCH /api/tables/{id},
                     admin-only. Note the collection paths have NO trailing slash, matching the
                     sibling routers; a trailing slash shipped first and was corrected in review.
                     Story 3.1 split GET onto a new TablesReadDep (admin, waiter); POST/PATCH stay
                     on the original admin-only TablesDep, unchanged. Story 5.1 widened
                     TablesReadDep again to admin/waiter/cook, so the Kitchen Display can resolve
                     table_number client-side (same incremental-widening pattern as
                     InventoryReadDep/DishCatalogReadDep/MenuReadDep)
  api/kitchen.py      Story 5.1 (new domain): GET /api/kitchen/items, KitchenReadDep = cook +
                     admin (mirrors every other read-dep's "primary Role + admin" shape). Still
                     read-only — Story 5.2's pick-up/mark-ready routes live on api/orders.py
                     instead, since the mutation they trigger belongs to the orders domain
  api/orders.py       Story 3.1: POST /api/orders/tables/{table_id}/open, waiter-only (the first
                     route in the project gated to exactly one non-admin Role, no admin fallback).
                     Story 3.2 added GET /api/orders/tables/{table_id} (resolves table_id -> its
                     currently open Order, the read nothing before this could do), and GET/POST
                     /api/orders/{order_id}/items, all on the same waiter-only OrdersDep. Story 3.4
                     added PATCH /api/orders/{order_id}/items/{item_id} (edit, stays on OrdersDep,
                     waiter-only) and POST /api/orders/{order_id}/items/{item_id}/cancel (cancel,
                     new OrderItemCancelDep = waiter, cook, admin — the project's first 3-role
                     require_role() usage). Story 5.2 added POST .../pick-up and POST
                     .../mark-ready, both on a new OrderItemProgressDep = cook, admin (the first
                     route pair in this file with no waiter access at all). Story 5.3 added
                     GET /api/orders (bare router prefix, @router.get("", ...)) on the existing
                     waiter-only OrdersDep, unwidened — the first bulk (not Table/Order-scoped)
                     read in this file
  api/smart_chef.py   Story 6.1 (new domain, Epic 6): POST /api/smart-chef/suggestions
                     (SmartChefWriteDep = cook only, no admin fallback) and GET (SmartChefReadDep =
                     cook + admin, shared with Story 6.2's Admin review page). First router
                     to reach an external service indirectly (via ai_service -> llm_client).
                     Story 6.2 added POST /suggestions/{id}/dismiss on a new SmartChefAdminDep
                     (admin only, narrower than SmartChefReadDep)
  api/websocket.py    Story 1.5: the single /api/ws endpoint, Role-scoped, cookie-authenticated,
                     periodic session re-verification while the connection stays open
  api/dependencies.py CurrentUserDep (get_current_user) and require_role(*roles) — the shared auth/authz seams;
                     also CurrentUserWsDep/verify_ws_origin, the WebSocket-route counterparts (Story 1.5)
  api/responses.py    error_responses(), shared OpenAPI responses-dict builder
  clients/database.py  SessionDep, session_scope() — a short-lived-session context manager any non-request
                     caller (a WebSocket handshake, a periodic re-verification tick) uses directly (see trap 15)
  clients/websocket.py ConnectionRegistry (Story 1.5): tracks open sockets keyed by user id (not just Role),
                     closing a User's prior socket on a new one; broadcast_to_roles() targets several Roles
                     in one emission. Fix (2026-08-26): that takeover close now sends its own code,
                     CONNECTION_REPLACED_CLOSE_CODE = 4409 (RFC 6455's private-use range), instead of a
                     generic one - the superseded tab's RealtimeProvider was treating it as a plain drop
                     and auto-retrying, which stole the connection right back and made two tabs of the
                     same account flap between connected/reconnecting roughly every second, forever.
                     _close_quietly(websocket, code=1000) now takes the code explicitly; close_all()
                     (app shutdown) still uses the 1000 default, only register()'s takeover path passes
                     4409
  clients/llm.py       Story 6.1 (new, Epic 6): LLMClient, the ONLY place `openai` is imported
                     anywhere in backend/ (AD-12). Wraps AsyncOpenAI, one method
                     (generate_recipe(prompt) -> dict), JSON mode
                     (response_format={"type": "json_object"}), a 45s per-call timeout. Defers
                     constructing the SDK client until first real use if no API key is configured,
                     so a missing key fails inside the call (which AIService already catches),
                     never raw at container-Singleton construction time
  data_models/       7 ORM modules + base.py + auth.py + errors.py, the full schema, already written.
                     recipe.py, menu.py and order.py also hold their own Pydantic request/response
                     schemas colocated with their ORM class, matching user.py's shape. menu.py owns
                     _INT4_MAX; recipe.py and order.py import it from there rather than redeclaring.
                     inventory.py was ORM-only (StockMovement, MovementType) until Story 4.1 added
                     its first Pydantic schemas, CreateStockMovementRequest (a model_validator
                     rejects consumption as a manual input and enforces AD-16's sign convention) and
                     StockMovementResponse
  services/auth_service.py  login, token issuance/verification, password hashing
  services/user_service.py  Story 1.3's User CRUD, the last-admin lock guard, denial logging
  services/inventory_service.py  Story 2.1: Ingredient creation, case-insensitive duplicate check.
                     Story 2.3 added list_ingredients. Story 4.1 added get_ingredient,
                     list_movements, and record_movement (this service's first write to
                     Ingredient.current_stock since Story 2.1 created the column), plus two private
                     seams: _get_ingredient (plain read, no lock, used by the two read methods) and
                     _lock_ingredient (SELECT ... FOR UPDATE, record_movement only) — the third
                     instance of trap 9's "lock the one row every caller contends on" shape, after
                     MenuService._lock_dish (AD-8) and UserService's AD-15 last-admin guard. Unlike
                     those two, the lock here guards no reject-condition, it exists purely so two
                     concurrent movements on the same Ingredient serialize instead of the later
                     commit silently discarding the earlier delta (both StockMovement rows would
                     still insert correctly either way). Sign convention (AD-16): purchase/waste
                     submit a positive magnitude and the service applies +/-; adjustment submits the
                     already-signed delta directly. current_stock is never floor-capped at zero,
                     verified by tests asserting the exact negative resulting value. Story 4.2 added
                     list_alerts (a plain derived-state SELECT, current_stock < min_stock_threshold,
                     no stored entity — see "Domain rules worth restating") and extended
                     record_movement to capture was_low from the row _lock_ingredient already holds,
                     compare against is_low after commit, and broadcast inventory.alerts_changed to
                     warehouse_manager only when that boolean flips (crossing-triggered, not
                     every-movement). This is the service's first RealtimeService producer, which
                     meant moving its container.py provider below realtime_service's (trap 23,
                     second application after order_service). Story 5.2 added apply_consumption,
                     called from OrderService.pick_up_item rather than a route on this service's
                     own router — reuses _lock_ingredient and the was_low/is_low crossing check,
                     but deliberately does not commit or broadcast itself, since it must
                     participate in the caller's own transaction (AD-6/NFR-3); record_movement's
                     CreateStockMovementRequest already rejects a manually-submitted consumption
                     type, which is why this is a separate method rather than a call to it
  services/menu_service.py  Story 2.2: Category/Dish creation and edits, AD-8's availability gate.
                     Story 2.3 added list_categories/list_dishes, Recipe Ingredient CRUD, AD-8's
                     second half, a unit-mismatch guard, and _lock_dish (see trap 9, now joined by
                     InventoryService._lock_ingredient, Story 4.1, as the pattern's third instance).
                     Story 6.2 added an optional source_suggestion_id to create_dish (validated by
                     a new _validate_source_suggestion: 404 if the suggestion doesn't exist, 409 if
                     already dismissed or already confirmed by another Dish) — still the only Dish
                     creation path (FR-19), no second "confirm" mutation. The pre-check's own
                     SELECT loses a TOCTOU race to a genuinely concurrent create_dish citing the
                     same suggestion; dishes.source_suggestion_id carries a DB-level UNIQUE
                     constraint (ORM: unique=True) as the real arbiter, with the resulting
                     IntegrityError caught and translated into the same 409 rather than a 500 —
                     a genuine double-confirm race, caught by code review, not by either of the
                     two sequential-only tests that shipped with the first draft
  services/table_service.py  Story 2.4: Table creation/listing and the guarded-UPDATE edit path
                     (see trap 18)
  services/order_service.py  Story 3.1: open_table, the second guarded-UPDATE application (AD-6),
                     with its read step factored into a private _get_table seam so a race test can
                     monkeypatch it, mirroring TableService.get_table's role in trap 18's own test.
                     Story 3.2 added get_open_order_for_table, list_items, add_item, and a private
                     _get_order seam (mirrors MenuService's list+add shape); add_item is a plain
                     check-then-insert, no guard/lock, AD-6 governs transitioning an existing
                     OrderItem's status, not creating a new one at pending. Story 3.3 made this the
                     project's first Observer/Pub-Sub publisher: open_table broadcasts
                     table.status_changed (a plain dict, table_id+status only, a refetch signal not
                     a state transfer) and add_item broadcasts order.item_added
                     (OrderItemResponse.model_validate(item).model_dump(mode="json"), so the pushed
                     shape can never drift from the REST response shape), both to UserRole.waiter
                     only, both only after their db.commit() succeeds. Story 5.1 widened
                     add_item's order.item_added broadcast to [UserRole.waiter, UserRole.cook], so
                     the Kitchen Display also receives it live; table.status_changed stays
                     waiter-only, unaffected. Story 3.4 added edit_item
                     (guarded UPDATE, WHERE status == pending) and cancel_item (guarded UPDATE,
                     WHERE status IN (pending, in_preparation)), the 5th/6th guarded-UPDATE
                     application; a private _get_item seam (mirrors _get_order/_get_table) is the
                     first _get_* seam in this service checking two ids (item id, and that it
                     belongs to the given order). Deliberately NOT added at the time: no
                     compensating StockMovement on cancel (AD-11 is a prohibition, not a feature,
                     still true), and no realtime_service.broadcast() call from either method (no
                     AC asked for live at the time — Story 5.5 later added one to each,
                     unconditional order.item_status_changed, [waiter, cook], reusing pick_up_item/
                     mark_item_ready's exact event/payload shape, placed after db.refresh(item)
                     and, in cancel_item's case, before the existing order_status_changed
                     conditional). Story 5.2 added pick_up_item (7th/8th
                     guarded-UPDATE application counting mark_item_ready below; WHERE status ==
                     pending, sets cook_id, then loops each RecipeIngredient calling the new
                     InventoryService.apply_consumption inside the same transaction, one
                     db.commit() for the status change and every Ingredient decrement together,
                     AD-6/NFR-3) and mark_item_ready (WHERE status == in_preparation, pure status
                     change, no cook_id reassignment). OrderService's first cross-service
                     collaborator: __init__ now also takes inventory_service, which meant
                     container.py's order_service provider had to move below inventory_service's
                     (trap 23, third application, first time on order_service itself). Both new
                     methods broadcast order.item_status_changed (a new event, same
                     [waiter, cook] recipients as order.item_added) after their own commit;
                     pick_up_item additionally broadcasts inventory.alerts_changed per Ingredient
                     that actually crosses threshold, after commit, reusing record_movement's
                     was_low/is_low pattern rather than duplicating it (see trap 26 for the
                     stale-quantity-read bug found and fixed in this story's own code review).
                     Story 5.3 added _recompute_order_status (private, called from add_item/
                     cancel_item/pick_up_item/mark_item_ready, never edit_item) and
                     list_open_orders (the first bulk Order read — GET /api/orders). The
                     recompute is deliberately NOT a guarded UPDATE (see AD-6 vs AD-5 note above
                     trap 27) but does lock the Order row (SELECT ... FOR UPDATE) before reading
                     sibling Items — trap 27, added this story after the code review caught a
                     real concurrency bug here. Broadcasts order.status_changed
                     ([UserRole.waiter] only, unlike order.item_status_changed's [waiter, cook])
                     via a shared _broadcast_order_status_changed(db, order) helper, only when
                     the aggregate actually changed. Story 5.4 added mark_served (guarded UPDATE,
                     WHERE status IN (ready, pending) — pending already means zero non-cancelled
                     items per FR-12, no separate item count) and close_order (guarded UPDATE,
                     WHERE status == served, then computes total_amount as a Decimal sum of
                     price_at_add * quantity over non-cancelled items, stamps closed_at, and
                     guarded-UPDATEs the owning RestaurantTable back to available, all one
                     transaction). Both reuse _broadcast_order_status_changed unchanged; close_order
                     also broadcasts table.status_changed (open_table's own plain-dict shape),
                     conditional on the Table UPDATE's own rowcount actually succeeding (review
                     finding — a client must never be told the table freed up when it didn't).
                     These are the project's first guarded UPDATEs against Order.status itself
                     (contrast _recompute_order_status above, which deliberately is not one)
  services/kitchen_service.py  Story 5.1 (new): list_active_items — the FIRST genuine join in
                     backend/services/ (every prior story returned raw ids and resolved names
                     client-side instead). Joins OrderItem to Order to resolve table_id, since
                     OrderItem has no table_id of its own, only order_id. Filter:
                     OrderItem.status != cancelled only; no filter on the owning Order's own
                     status yet, since nothing can move an Order to served/closed until Stories
                     5.3/5.4 — flagged explicitly in the method's own docstring as a
                     forward-compatibility gap for whichever of those ships next. **RESOLVED by
                     Story 5.4**: the filter now also excludes Order.status IN (served, closed),
                     since this story is what first makes those reachable
  services/realtime_service.py  Story 1.5: thin wrapper over ConnectionRegistry so api/ only ever
                     calls into services/ (AD-1); broadcast(roles, event, payload).
                     **RESOLVED by Story 3.3**: OrderService is now its first producer (see above).
                     Story 4.2 made InventoryService its second: inventory.alerts_changed, to
                     UserRole.warehouse_manager only
  services/ai_service.py  Story 6.1 (new, Epic 6): AIService.generate_suggestion/list_suggestions.
                     Config-free aside from llm_client/logger, but registered as a
                     providers.Singleton in container.py — the ONE deliberate exception to this
                     container's otherwise-universal Factory pattern, since AD-14's
                     "reject a second concurrent generation for the same Cook" guard lives in an
                     in-process set (_in_flight) on the service instance itself; a Factory would
                     hand each injected request its own empty set, silently defeating the guard.
                     Reads Ingredient directly (current_stock > 0 only), no InventoryService
                     dependency needed for a plain read. Stock snapshot sorted by
                     _waste_risk_rank (current_stock / min_stock_threshold descending, a
                     zero-threshold Ingredient with stock ranks maximally at-risk instead of
                     falling back to a raw, differently-scaled quantity) — the "prioritize
                     at-risk-of-waste ingredients" heuristic (FR-18), since nothing in this schema
                     tracks expiry/usage-rate. Validates the parsed OpenAI response's shape
                     (name/ingredients/plating present) before persisting. Story 6.2 changed
                     generate_suggestion/list_suggestions to return AIRecipeSuggestionResponse
                     (not the raw ORM row): list_suggestions now does an outerjoin against Dish on
                     Dish.source_suggestion_id to resolve confirmed_dish_id per row (null if
                     unconfirmed), the derived-state read side of "confirmed." Added
                     dismiss_suggestion (404 if missing, 409 if already dismissed or already
                     confirmed, via a private _get_confirmed_dish_id helper reused by both the
                     guard and the response so the two can never drift apart)
  exceptions/__init__.py    AuthError family (401), ForbiddenError (403), ConflictError family (409),
                     NotFoundError family (404, one shared base since Story 2.3, see trap 17).
                     Story 6.1 added a fifth family, ExternalServiceError (502) — the first
                     handler added since the original four, for a third-party service call
                     failure (AIGenerationFailedError). Story 6.2 added three NotFoundError/
                     ConflictError subclasses (SuggestionNotFoundError,
                     SuggestionAlreadyDismissedError, SuggestionAlreadyConfirmedError), no new
                     handler needed since both families already have one
  exceptions/handlers.py    register_exception_handlers(app); five handlers as of Story 6.1, one
                     per family
```

- `data_models/` is complete and mirrors `docs/database-schema.md`: `user.py`, `menu.py`,
  `recipe.py`, `order.py`, `inventory.py`, `ai.py`, `base.py`, plus `auth.py`/`errors.py` for
  request/response schemas. **Do not treat the schema as unwritten.**
- `services/` has `auth_service.py`, `user_service.py`, `inventory_service.py`, `menu_service.py`,
  `table_service.py`, and `realtime_service.py`. Every other domain rule in the epics still has to
  be written.
- `api/` has `router.py` (health, mounted inline), `auth.py`, `admin.py` (Story 1.3, the reference
  implementation for role-gated routes, see trap 8), `inventory.py` (2.1/2.3), `menu.py` (2.2/2.3),
  `tables.py` (2.4), and `websocket.py` (Story 1.5).
- `alembic/versions/` still holds three revisions: the baseline, `f1743862f1b1` (case-insensitive
  unique index on username, Story 1.3), and `daca523f69f5` (the same fix applied to
  `Ingredient.name`, Story 2.1, see trap 11). Stories 2.2, 2.3 and 2.4 all needed none.
- **Every `ConflictError`/`NotFoundError` subclass now lives in one family with one handler each.**
  Adding a new 404 means subclassing `NotFoundError` and nothing else; forgetting to subclass it
  makes the error a silent 500, which `tests/test_migrations.py` now guards against.

**Frontend, shell/routing plus a live real-time transport, and eleven real domain screens (Menu Management with dish/category creation, Tables setup, Cook's read-only Dishes catalog, Ingredients, the Waiter's Tables grid, the Waiter's Table/Order detail, the Warehouse Ingredient detail page, the Warehouse Alerts page, the Cook's Kitchen Display, the Cook's Smart Chef page (Story 6.1), and the Admin's Recipe Suggestions review page (Story 6.2)). The remaining IA surfaces are still placeholders.**

```
frontend/src/
  App.tsx              provider composition root: QueryClientProvider, ThemeModeProvider,
                        RouterProvider (react-router core export, not "/dom", see Testing).
                        ConnectionStatusProvider no longer sits here (Story 1.5): RealtimeProvider
                        renders it internally, further down the tree, see below
  main.tsx              mounts <App/>, unchanged since Story 1.0
  router.tsx             the route tree (13 IA-surface routes + /login), exported as `routes` so
                        tests build their own createMemoryRouter from the same config
  config/config.ts       import.meta.env access (unchanged)
  config/theme.ts         lightTheme/darkTheme (accent-color override only, everything else stock
                        MUI) + DENSE_ROW_HEIGHT
  types/user.ts           UserRole, CurrentUser (mirrors UserResponse's JSON shape, snake_case)
  types/menu.ts           Unit, Category, Dish, RecipeIngredient (Story 2.3)
  types/inventory.ts      Ingredient (Story 2.3). Story 4.1 added MovementType and StockMovement
                        (quantity_change stays a string, mirroring current_stock's
                        Decimal-as-string precedent, already signed by the backend, e.g. "-0.800"
                        for a waste movement)
  types/table.ts          TableStatus, Table (Story 2.4)
  types/order.ts          OrderStatus, Order (Story 3.1); OrderItemStatus, OrderItem,
                        MAX_ORDER_ITEM_QUANTITY (Story 3.2, mirrors the backend's own cap by hand).
                        Story 3.4 added "cancelled" to the OrderItemStatus union, mirroring the
                        backend's new enum value by hand, same as MAX_ORDER_ITEM_QUANTITY above
  services/httpClient.ts   fetch wrapper: credentials "include", ApiError, detail-envelope parsing.
                        Every failure leaves as an ApiError, including an unreachable backend and a
                        timeout, which carry status 0 (see trap 12). `apiRequest`'s global timeout
                        (`config.api.timeoutMs`, 5s) is now overridable per call (Story 6.1,
                        manual-test finding) — a genuine OpenAI-backed request routinely takes
                        longer than any ordinary CRUD call; only `useGenerateSuggestion` overrides
                        it (50s), every other call site keeps the 5s default
  services/smartChefService.ts  Story 6.1 (new, Epic 6): useSuggestions/useGenerateSuggestion.
                        The first call site to pass a non-default timeout to apiRequest (50s,
                        matching LLMClient's own 45s server-side budget plus margin). Story 6.2
                        added useDismissSuggestion (POST .../dismiss, invalidates
                        SUGGESTIONS_QUERY_KEY on settle, same reasoning as useGenerateSuggestion's
                        own settle-not-success invalidation)
  services/authService.ts  useCurrentUser / useLogin / useLogout (Story 1.7: invalidates
                        CURRENT_USER_QUERY_KEY on success, the mirror of useLogin's own
                        invalidation; no manual navigate(), RequireAuth's existing 401-redirect
                        handles it once the refetch reports the session gone)
  services/menuService.ts  Story 2.3: categories/dishes/recipe-ingredient hooks; Story 2.6:
                        useCreateCategory / useCreateDish (payload types private to this file,
                        matching tableService.ts's precedent). Story 3.2 exports DISHES_QUERY_KEY
                        (was module-private) so orderService.ts's add-item mutation can invalidate
                        it on a stale-dish 409, the same TABLES_QUERY_KEY cross-service export
                        tableService.ts already set the precedent for. Story 6.2 added an optional
                        source_suggestion_id to CreateDishPayload (the only wiring this file needed
                        for Story 6.2 in its final design — the create-Dish request itself is still
                        the one path a suggestion gets confirmed through)
  services/inventoryService.ts  Story 2.3: useIngredients; Story 2.6: useCreateIngredient
                        (INGREDIENTS_QUERY_KEY promoted to a module constant). Story 4.1 added
                        useIngredient, useStockMovements, and useRecordStockMovement, the last of
                        which invalidates three keys onSettled (the single-ingredient key, the
                        movements-list key, and INGREDIENTS_QUERY_KEY), since a logged movement
                        changes current_stock and IngredientsPage.tsx's own list must not show
                        stale stock after a Warehouse Manager navigates back to it. Story 4.2 added
                        useAlerts(enabled = true) (GET /api/inventory/alerts) and exported
                        ALERTS_QUERY_KEY, so both AppShell.tsx's nav badge and AlertsPage.tsx's list
                        can invalidate the same key from their own independent
                        inventory.alerts_changed subscriptions; the enabled param exists so
                        AppShell.tsx (rendered for every Role) can gate the query to
                        warehouse_manager only, since hooks cannot themselves be called
                        conditionally. Story 4.3's review fixed useCreateIngredient to also
                        invalidate ALERTS_QUERY_KEY (not just INGREDIENTS_QUERY_KEY): creating an
                        Ingredient never goes through record_movement, so nothing else would ever
                        refresh the alerts list for one created already below its own threshold
  services/tableService.ts  Story 2.4: useTables / useCreateTable / useUpdateTable. TABLES_QUERY_KEY
                        exported (Story 3.1) so orderService.ts's mutation can invalidate the same
                        cache key without a second copy of ["tables"]
  services/orderService.ts  Story 3.1: useOpenTable, invalidates onSettled (not onSuccess only),
                        matching useUpdateTable's own precedent, a lost race needs the same refresh
                        a rejected edit does. Story 3.2 added useOrderForTable (accepts
                        `number | null`, enabled: tableId !== null, so a malformed route param
                        never reaches the server), useOrderItems (accepts `number | undefined`,
                        same enabled-gating shape), and useAddOrderItem (invalidates the item list
                        AND menuService's DISHES_QUERY_KEY on settle, a 409 means the cached dish is
                        stale too). Story 3.3 exported orderItemsQueryKey (was module-private) so
                        TableOrderDetailPage.tsx's live order.item_added subscriber can invalidate
                        the same key this file's own query/mutation already use. Story 3.4 added
                        useEditOrderItem (PATCH, itemId + payload) and useCancelOrderItem (POST,
                        itemId), both invalidating orderItemsQueryKey(orderId) onSettled, same
                        rejected-mutation-needs-a-refresh rule as this file's other mutations.
                        Story 5.2 added usePickUpItem/useMarkItemReady, deliberately NOT bound to a
                        fixed orderId the way every other mutation in this file is: their only
                        caller, the Kitchen Display, renders items from many different Orders on
                        one screen, so { orderId, itemId } travels with each mutate() call instead.
                        Invalidate KITCHEN_ITEMS_QUERY_KEY only (imported from kitchenService.ts) —
                        the Waiter's own orderItemsQueryKey refreshes from the live
                        order.item_status_changed push instead, not from this mutation reaching
                        into a cache key it doesn't otherwise know about. Story 5.3 exported
                        orderForTableQueryKey(tableId) (previously only built inline inside
                        useOrderForTable, needed once TableOrderDetailPage.tsx's new
                        order.status_changed subscriber had to invalidate it without
                        reconstructing the array by hand) and added OPEN_ORDERS_QUERY_KEY /
                        useOpenOrders() (GET /api/orders, the first bulk Order read), which
                        TablesPage.tsx resolves client-side into a table_id -> status lookup to
                        drive the attention-state tile treatment
  components/menu/DishRecipeEditor.tsx  Story 2.3: the per-dish recipe editor (first domain
                        component folder outside components/shell/)
  components/ai/SuggestionSummary.tsx  Story 6.2 (new folder): the read-only Recipe Suggestion
                        card content (name, ingredients drawn on, plating), extracted out of
                        SmartChefPage.tsx's original SuggestionCard so RecipeSuggestionsPage.tsx
                        could wrap the same content with its own Confirm/Dismiss actions instead
                        of duplicating the markup
  components/ai/ConfirmSuggestionDialog.tsx  Story 6.2: opened from RecipeSuggestionsPage.tsx's
                        "Confirm into Dish" button (revised mid-story from an original
                        navigate-to-Menu-Management design per manual-test feedback — see that
                        story's own Change Log). Asks only for Category/Price/Prep-time, with one
                        best-effort-prefilled, always-editable row per suggested ingredient
                        (case-insensitive name match against the real Ingredient list for id+unit,
                        parsed leading numeric amount for quantity). Composes
                        POST /api/menu/dishes (carrying source_suggestion_id) then one
                        POST .../recipe-ingredients per row — no new backend endpoint — and, once
                        at least one line succeeds, PATCHes is_available: true so the Admin never
                        has to flip it manually for a Dish whose recipe was just attached in the
                        same flow. A per-row add failure (or the availability PATCH itself failing)
                        does not roll back the created Dish; it is reported inline for the Admin to
                        finish from Menu Management's existing recipe editor
  components/orders/OrderItemStatusBadge.tsx  Story 3.2: the shared Order Item status badge
                        (UX-DR1, MUI Chip + icon + spelled label), built as its own file rather
                        than inlined so Story 3.4's edit/cancel UI and Epic 5's Kitchen Display can
                        import it verbatim. Scoped to today's 3-member OrderItemStatus, no fallback
                        case for a value outside it (deferred, same call Story 3.1's review made
                        for TableTile.badgeColor). Story 3.4 added the 4th member: "Cancelled"
                        label, Cancel icon, "error" MUI color (COLORS' type widened to include it)
  components/inventory/MovementTypeChip.tsx  Story 4.1: the Stock Movement type chip (AC3/UX-DR14),
                        first file in a new components/inventory/ folder. A neutral-palette MUI Chip
                        (primary/info/default/secondary), deliberately not reusing
                        OrderItemStatusBadge's success/warning/error traffic-light trio: a movement
                        type is a category, not an urgency signal, and reusing "error" for waste
                        would collide with that trio's meaning
  components/shell/        RequireAuth (route guard, now wraps AppShell in RealtimeProvider),
                        AppShell (app bar + nav + Outlet; Story 1.7 added a Sign Out IconButton
                        next to ThemeToggle, same icon-button-with-visible-aria-label shape,
                        rendering its own isError Alert on a failed logout; Story 4.2 added a MUI
                        Badge on the "Alerts" NavItem specifically, matched by a literal path
                        comparison rather than a generic per-path badge map since no second nav
                        badge exists yet, driven by useAlerts(isWarehouseManager) and a live
                        inventory.alerts_changed subscription, both scoped to
                        user.role === "warehouse_manager" since that's the only Role with an Alerts
                        nav entry at all), AppShellSkeleton (the
                        cold-load stand-in: app bar shape, not a blank page), ThemeModeProvider/ThemeToggle,
                        ConnectionStatusContext/ReconnectingBanner, RealtimeProvider (Story 1.5:
                        owns the single WebSocket connection, drives ConnectionStatusContext with
                        real state, capped exponential backoff reconnect, exposes useRealtime()'s
                        subscribe(event, handler) for later stories to consume push events.
                        Fix (2026-08-26): ConnectionStatus gained a third value, "replaced", read
                        off a new CONNECTION_REPLACED_CLOSE_CODE = 4409 the backend's
                        ConnectionRegistry now sends when a second tab of the same session takes the
                        socket over - onclose no longer treats that close as a plain drop and
                        auto-retries into it, which is what was making two tabs of the same account
                        flap between connected/reconnecting roughly every second, forever.
                        ReconnectingBanner shows a distinct "connected in another tab" info message
                        for it, not the "Reconnecting..." warning; a superseded tab needs a manual
                        reload to go live again, deliberately not automatic),
                        RowsSkeleton, navigationConfig.ts (ROLE_HOME_PATH/ROLE_NAV_ITEMS/
                        ROLE_PATH_PREFIX + canRoleVisit(), the single source of truth the nav and
                        the guard both read; Story 2.6 made reachability derive from ROLE_NAV_ITEMS
                        so Admin's cross-prefix Ingredients grant cannot drift from its nav entry)
  pages/{role}/           placeholder components for the 4 IA surfaces that have not shipped yet
                        (just the surface's own title as the page's h1). Nine are now real:
                        admin/MenuManagementPage.tsx (Story 2.3; Story 2.6 added the always-visible
                        "+ New dish" form and an inline "+ New category" reveal on its Category
                        picker, no dialog), admin/TablesSetupPage.tsx (Story 2.4), cook/DishesPage.tsx
                        (Story 2.5, strictly read-only, groups every Dish by Category, resolves
                        Recipe Ingredient lines to names via useIngredients()),
                        warehouse/IngredientsPage.tsx (Story 2.6, replacing Story 1.4's placeholder:
                        an "Add ingredient" form plus a dense-row list; Story
                        4.1 added row click-through to warehouse/IngredientDetailPage.tsx, found
                        missing during Story 4.1's own manual testing, not by any of the three
                        automated review layers, see trap 24: plain navigation needs none of the
                        deferred comparison logic, only sorting/highlighting does. Story 4.3 added
                        the shortage sorting/highlighting this docstring used to defer: reuses
                        useAlerts() (Story 4.2) rather than recomputing current_stock <
                        min_stock_threshold a second time client-side, sorts in-shortage rows to
                        the top (alphabetical within each group), and renders WarningAmberIcon +
                        error-colored text on those rows — zero backend changes, the first Epic 4
                        story to need none. Live re-highlighting works for every warehouse_manager
                        session for free, via AppShell.tsx's existing global
                        inventory.alerts_changed subscription sharing the same ALERTS_QUERY_KEY
                        cache; Admin (who can also reach this screen) gets correct data on load but
                        no live re-highlighting, since the backend only broadcasts to
                        warehouse_manager — a known, deferred gap, not a regression, since no AC
                        asks for Admin live updates),
                        warehouse/IngredientDetailPage.tsx (Story 4.1, replacing Story 1.4's
                        placeholder: stat cards for current stock and minimum threshold, a
                        log-movement form restricted to Purchase/Waste/Adjustment (Consumption is
                        never offered, it is Epic 5's automatic path), and a movement history table
                        with MovementTypeChip per row; a 404 on the Ingredient lookup and an invalid
                        route param both render the same "not found" message, mirroring
                        TableOrderDetailPage.tsx's split-404-out-of-isError/parseRouteId
                        conventions; the quantity cell's color is the bare token "error"/"success",
                        not the dot-path "error.main"/"success.main" that shipped first and
                        silently rendered no color at all, see trap 25), waiter/TablesPage.tsx
                        (Story 3.1: the Tables grid, one tile per
                        Table with its status badge, only an `available` tile is clickable, opens
                        the Table into a new Order and navigates to its detail page; Story 3.3
                        subscribes to the live table.status_changed push and invalidates
                        TABLES_QUERY_KEY on receipt, so another Waiter opening a Table updates this
                        grid with no manual refresh), and
                        waiter/TableOrderDetailPage.tsx (Story 3.2, `/waiter/tables/:tableId`,
                        replacing its Story 1.4 placeholder: resolves the route param to its open
                        Order via useOrderForTable, an add-dish form with the inline "Rejected,
                        dish unavailable" 409, and a read-only Order Item list with
                        OrderItemStatusBadge per row and "No items added yet" empty state; a 404
                        "no open order" is presented as its own state with a link back to Tables,
                        Story 3.3 subscribes to the live order.item_added push and invalidates
                        orderItemsQueryKey(order.id), guarded against order?.id still being
                        undefined in the narrow window before the Order lookup resolves,
                        not a Retry that could never succeed; the heading resolves the Table's
                        table_number via the already-cached useTables(), never the route param's
                        raw id), each with its own *.test.tsx alongside. Story 3.4 added the
                        Actions column: a per-row OrderItemRow subcomponent owning its own
                        useEditOrderItem/useCancelOrderItem instances (per-row, not shared from the
                        page — editing item A and cancelling item B are independent actions, unlike
                        TablesPage.tsx's page-level-exclusive "open" mutation). pending gets Edit +
                        a plain Cancel; in_preparation gets Cancel behind an in-row confirm-reveal
                        (no modal, matching UsersPage.tsx's "Deactivate {name}?" precedent);
                        ready/cancelled get no actions. The edit/cancel-discard "Back" and confirm
                        "Confirm cancel" buttons are deliberately not both labeled "Cancel" (a
                        review finding: two same-named "Cancel" buttons could render on screen at
                        once with 2+ pending items). The editable Qty/Note fields are gated on
                        `isEditing && item.status === "pending"`, not `isEditing` alone, so a row
                        stuck mid-edit falls back to read-only if its item transitions away from
                        pending under it. Deliberately NOT in this story: live updates for edit/
                        cancel (Story 3.3 added live push for open/add only), the Close-order
                        bar/total (FR-8, a later story), and
                        warehouse/AlertsPage.tsx (Story 4.2, replacing Story 4.1's placeholder:
                        useAlerts()-driven loading/error/empty("No active shortages")/loaded states,
                        one row per Ingredient in shortage reading "Stock low: {name}
                        ({current_stock}{unit} left)" per UX-DR10, no dismiss control anywhere, a
                        row click navigates to that Ingredient's own detail page; subscribes to the
                        live inventory.alerts_changed push independently of AppShell.tsx's own
                        subscription for the nav badge, both invalidating the same
                        ALERTS_QUERY_KEY), and
                        cook/KitchenDisplayPage.tsx (Story 5.1, replacing Epic 1's placeholder:
                        read-only, one MUI Card per Table grouping that Table's active
                        (non-cancelled) Order Items, each row showing dish name/quantity/note/
                        OrderItemStatusBadge. Combines loading/error across three independent
                        queries for the first time in this codebase (kitchen items, tables,
                        dishes). Subscribes to the widened order.item_added push and invalidates
                        KITCHEN_ITEMS_QUERY_KEY, TABLES_QUERY_KEY, and DISHES_QUERY_KEY together on
                        receipt (review fix: originally only invalidated the kitchen items key,
                        leaving a newly-created Table/Dish unresolved — client-side table/dish name
                        resolution falls back to "?"/"Unknown dish", never a raw id, matching
                        TableOrderDetailPage.tsx's convention). Dark-theme-on-Cook-login (UX-DR7)
                        and the "Reconnecting..." banner (UX-DR16) needed zero new code, both
                        already built ahead of this story (ThemeModeProvider.tsx/
                        ReconnectingBanner, Stories 1.4/1.5). Story 5.2 added "Pick up"/"Mark
                        ready" buttons per row (single large click target, UX-DR19), wired to
                        usePickUpItem/useMarkItemReady; a second live subscription
                        (order.item_status_changed) also invalidates KITCHEN_ITEMS_QUERY_KEY and
                        clears any stale per-row inline error for the item it names. Per-row
                        pending state is tracked via an explicit Set of in-flight item ids, not
                        derived from the shared mutation's own .variables field (review fix: that
                        field only ever reflects the most recent call, so two rapid clicks on
                        different rows could leave an earlier row's button incorrectly re-enabled
                        mid-flight)),
                        cook/SmartChefPage.tsx (Story 6.1: a request bar (optional free-text
                        direction) plus the Cook's own persisted Recipe Suggestions, newest first,
                        each card via the shared SuggestionSummary component. Deliberately no
                        Confirm/Dismiss and no chat panel here, both out of scope for that story),
                        and
                        admin/RecipeSuggestionsPage.tsx (Story 6.2, replacing the placeholder:
                        useSuggestions() filtered client-side to "awaiting review"
                        (!dismissed && confirmed_dish_id === null, AD-9's convention), each card
                        wrapping SuggestionSummary with Confirm into Dish/Dismiss actions. Confirm
                        opens ConfirmSuggestionDialog in place (see components/ai/ above for the
                        full design and its mid-story revision); Dismiss calls
                        useDismissSuggestion().mutate() directly, no confirm step. Empty state:
                        "No suggestions awaiting review.")
frontend/
  nginx.conf            the production image's site config (see trap 13)
```

No state management library beyond TanStack Query for server state and React Context/`useState` for
local UI state (theme mode, connection status), matching AD-13. `services/` is now organized
per-domain (`authService`, `menuService`, `inventoryService`, `tableService`, `userService`), the
same way the backend's `services/` is; later stories add one file per domain.

**The shape every new domain screen should copy** (established by 2.3, corrected by 2.4's review):

- Every query hook sets `retry: false`. The app-level `QueryClient` sets no default, so TanStack's
  3 retries otherwise turn a 401/403/404 into four requests and a multi-second wait.
- A list query handles **four distinct states**: loading, error (with a Retry action), empty, and
  loaded. Collapsing error into empty makes a failed fetch render as an authoritative "there is
  nothing here", which is trap 13's reasoning applied to data rather than auth.
- **Every mutation renders its own `isError`.** A mutation whose failure is never displayed is the
  single most repeated defect in this codebase's reviews.
- Mutations that can be rejected because the caller's copy is stale invalidate `onSettled`, not
  `onSuccess`: a 409 is exactly when the row most needs refreshing.
- Inline editors use **controlled** inputs that resync from the server, but **never while the field
  is dirty**, or a background refetch silently overwrites what the user is typing.
- **Never diff a form against cached data to decide what to send.** Send the fields; let the server
  decide what changed. Diffing against a stale cache produces an empty payload, so no request is
  sent and the row looks saved while the server still holds something else (Story 2.4 review).
- Parse numeric inputs explicitly. `Number("abc")` is `NaN`, which `JSON.stringify` serializes as
  `null`, and a nullable backend field reads that as "not provided" and half-applies the update
  (see trap 19).
- A disabled control's reason must be **visible text**, not only a `Tooltip`: tooltips never appear
  on touch or keyboard-primary interaction.
- **A page driven by more than one independent query must combine loading/error across all of
  them, not just the "main" one.** Story 2.5's `DishesPage` originally wired up only `useDishes()`'s
  `isLoading`/`isError`, leaving `useCategories()`/`useIngredients()` silent. Reproduced directly:
  with dishes succeeding and categories failing, the page rendered only its heading, no error, no
  empty state, nothing. `isLoading`/`isError` must be OR'd across every query the page depends on
  to render anything meaningful, and Retry must refetch all of them, not just one.
- **A form whose picker is populated by a query must not render until that query settles.** Rendering
  it anyway gives an empty picker and a permanently disabled submit with no visible reason — the
  same silent-failure class as the bullet above, one layer in (Story 2.6 review).
- **A submit handler re-checks its full submit predicate, never a subset of it.** The disabled button
  is not authoritative: Enter submits a form regardless. Every check the handler omits is a request
  that can ship with a blank required field or duplicate one already in flight (Story 2.6 review).
- **An inline reveal nested inside another form needs its own Enter handling**, or the outer form's
  implicit submit steals the keypress and discards what the user typed in the reveal (Story 2.6).
- **A mutation whose caller immediately selects the created row seeds the cache in `onSuccess`
  before invalidating.** Invalidation only *schedules* a refetch, so selecting the new id first
  leaves a picker holding a value with no matching option until the refetch lands (Story 2.6).
- **If a story's AC names a Role, verify that Role can actually reach the screen.** Backend
  permission and UI reachability are separate systems: `InventoryWriteDep` permitted Admin from
  Story 2.1, but the route guard redirected Admin away until Story 2.6's review caught it. Route
  reachability is derived from `ROLE_NAV_ITEMS` via `canRoleVisit`, so granting a Role a
  cross-prefix surface means adding the nav entry, never maintaining a second list.
  **This check has to trace every endpoint the page's queries call, not only the page's own
  route.** Story 3.2's `TableOrderDetailPage` correctly gated `GET /api/orders/tables/{table_id}`
  to Waiter, but its `useDishes()` call hit `GET /api/menu/dishes`, still admin+cook-only from
  Story 2.5, so the Waiter got a 403 and the whole page rendered as an error. All three review
  layers caught it independently; nothing in either test suite could, since the frontend test
  stubbed that endpoint 200 and `test_menu.py` had zero Waiter cases. **When a page composes more
  than one query, check every one of them against the Role the AC names, not just the one the
  story's own new route added.**
- **TanStack Query's `refetch()` bypasses that query's own `enabled` gate.** A dependent query kept
  `enabled: false` until its id is known is still fired if something calls `refetch()` on it
  directly, so a page-level "Retry all" handler must check the same condition `enabled` used before
  calling `refetch()`, not call it unconditionally (Story 3.2 review: the Retry button could fire
  `/api/orders/undefined/items` before an Order was known, and its 422 then became the user-visible
  reason the page said it had failed).
- **A 404 from a read can be a legitimate domain state, not a transport failure, and the two need
  different UI.** `TableOrderDetailPage`'s order-lookup 404 means "this Table has nothing open on
  it right now," reachable by a direct URL to an `available` table, not a dropped connection.
  Folding it into the generic error/Retry path offers a Retry that can never succeed. Discriminate
  on `error instanceof ApiError && error.status === 404` (the same shape trap 13 already uses for
  401) and show the domain-appropriate message instead.
- **Path authorization matches on segment boundaries, and a nav-derived grant is exact.**
  `startsWith(prefix)` alone lets `/admin` match a future `/administration`, and
  `startsWith(navPath)` hands out the whole subtree — that is how Story 2.6's first fix silently
  gave Admin `/warehouse/ingredients/:ingredientId`. Compare `=== p || startsWith(p + "/")` for a
  subtree, and `=== p` for a single surface. Both bugs were invisible: no route matched the widened
  patterns *yet*, so nothing failed, and the next route named as a textual extension of an existing
  one would have been granted with no code change and no test failure (Story 2.6 second review).
- **When a fix contradicts a shipped AC, amend the AC in the same story rather than leaving the
  contradiction.** Story 2.6's Admin nav entry violated Story 1.4's AC2 as literally worded; the AC
  was reworded by correct-course in `epics.md` and `EXPERIENCE.md`, with the reasoning recorded
  inline. Leaving it would have left a later reader reconciling the epics against the code with no
  audit trail on the epics side.

---

## Traps that fail silently

These are the ones that cost hours because nothing errors:

1. **RESOLVED by Story 1.1.** `container.wire()` is now called in `main.py` with
   `modules=["api.auth", "api.dependencies"]`. The live rule from here: every later story
   **appends** its module to that list, **never replaces it**. A silently truncated list is the
   classic version of this bug, and it fails at *request* time rather than import time, so the
   app still starts fine and breaks on first call.

2. **RESOLVED by Story 1.0.** `create_all` is gone from `container.py`. Alembic (async template)
   now owns the schema: `backend/alembic/env.py` resolves the connection URL through
   `utils.load_config` (never hardcoded in `alembic.ini`), and `backend/entrypoint.sh` runs
   `alembic upgrade head` before the API starts in Docker. **Every schema change from here ships
   its own revision** (`alembic revision --autogenerate -m "..."`, inspect it before committing).
   Running the app outside Docker (`uv run python main.py` directly) does **not** run migrations
   for you; run `uv run alembic upgrade head` first, per the README.

3. **RESOLVED by Story 1.1.** `CORSMiddleware` is registered in `main.py` with an explicit
   one-item allow-list from `config.cors.allow_origin` and `allow_credentials=True` (needed for
   the session cookie across ports). **Never widen this to a wildcard** (AD-3).

4. **RESOLVED by Story 1.1, with a sharp edge.** Auth exists, but it is *opt-in per route*.
   `api/dependencies.py` provides `CurrentUserDep`, the one shared seam AD-3 requires. A route
   without it is still fully public, and nothing warns you. Every protected route must declare
   `user: CurrentUserDep`, and it must never re-derive a user from the cookie itself. Story 1.2
   built role enforcement on top of this (see trap 8).

5. **RESOLVED by Story 1.1.** The stray `backend/data_models/exceptions/` package is gone.
   Top-level `backend/exceptions/` is the single designated location, and it now holds the
   `AuthError` family (`InvalidCredentialsError`, `SessionExpiredError`,
   `NotAuthenticatedError`). Each carries its own `detail`; one handler in `main.py` maps any of
   them to a 401. Add new exception types the same way rather than raising inline or building a
   second handler.

6. **Secrets come from `backend/.env`, which is untracked.** `utils.load_config` loads it at
   import (real environment variables still win), and docker-compose passes it through
   `env_file` as optional. A fresh clone with no `.env` still boots, silently falling back to
   `config.yaml`'s published default JWT key, which makes every session forgeable. The app logs a
   startup warning when that happens. Copy `backend/.env.example` to `backend/.env` before the
   first run. **Never commit `.env`, and never put a real secret in `.env.example`.**

7. **The session cookie is `Secure` unconditionally, and v1 is localhost-only.** Browsers exempt
   `http://localhost` from the Secure requirement, so the Docker demo works. Reaching the app
   over a LAN IP or hostname instead returns a 200 on login and then silently drops the cookie,
   with no error anywhere. Accepted scope for v1 (review 2026-08-08); revisit with a real
   cookie-transport setting if the app ever needs to be reached off-box.

8. **RESOLVED by Story 1.3, and now the live pattern every domain router copies.**
   `api/dependencies.py` exports `require_role(*roles)`, layered on `CurrentUserDep` so a request
   is authenticated before it is role-checked. Call it, never pass it bare:
   `Depends(require_role(UserRole.admin))` is correct; `Depends(require_role)` registers without
   error but makes FastAPI read the roles as a query param, silently running zero authorization.
   `ForbiddenError` (a sibling of `AuthError`, not a subclass) maps to 403 via its own handler in
   `main.py`. `api/admin.py` is the reference implementation: one module-level
   `AdminDep = Annotated[User, Depends(require_role(UserRole.admin))]` reused by every route.
   The two obligations Story 1.2 deferred here are both discharged, and both are now standing
   rules: (a) **every route declares the error statuses it can return**, each with a body schema
   (`_errors()` in `api/admin.py`, `ErrorResponse` in `data_models/errors.py`) — these exceptions
   are plain `Exception` subclasses, so FastAPI infers nothing and an undeclared status is simply
   absent from the contract Story 1.4's client builds against; (b) **`api/` stays non-logging and
   services log their own rejections** through the injected loguru logger with the acting user id
   (`actor` is threaded into every `UserService` method for exactly this).

9. **A business rule enforced by a read-then-write in a service is not enforced at all under
   concurrency.** Story 1.3's AD-15 last-admin guard counted active admins in an unlocked
   `SELECT`, so two admins deactivating each other simultaneously both passed and both committed,
   leaving zero active admins and locking user management permanently. Fixed with an id-ordered
   `SELECT ... FOR UPDATE` over the active-admin rows before counting (consistent lock order, so
   concurrent callers serialize instead of deadlocking). **Apply the same shape to every
   invariant of the form "reject if this would leave zero/too few X"** — AD-6's guarded status
   transitions and AD-8's last-recipe-row rule are the same class of problem. AD-5's
   last-write-wins covers ordinary field edits, never an invariant check.

10. **Pydantic's `max_length` counts characters; bcrypt's limit is bytes.** A 72-character
    password of Hebrew or accented text is 144 bytes, passes a `max_length=72` field, and then
    raises `ValueError` out of `hash_password` as an unhandled 500. Password fields use a
    byte-length validator (`_require_hashable_password` in `data_models/user.py`), never a
    character bound. Any future field whose real limit is a byte budget needs the same treatment.

11. **Usernames are case-insensitive and trimmed, enforced in three places that must stay in
    agreement.** `data_models/user.py` strips whitespace and rejects blank-after-strip;
    `UserService.create_user` compares with `func.lower(...)`; `AuthService.authenticate` looks up
    the same way; and a functional `UNIQUE INDEX ON users (lower(username))` (revision
    `f1743862f1b1`) is the final arbiter. Changing any one of these without the others either
    makes an account unreachable at login or lets two confusable accounts exist. Decided
    2026-08-10 during Story 1.3's review, after establishing that nothing in the PRD, epics,
    schema doc, or spine had ever specified username case at all.
    **Reused verbatim by Story 2.1 for `Ingredient.name`** (revision `daca523f69f5`), so this is
    now a two-instance precedent, not a username-only quirk. `Category.name` (Story 2.2)
    deliberately does **not** get this treatment: no epics AC or UX doc pairs category names into
    the case-insensitive-duplicate convention, so it stays plain case-sensitive `unique=True`. Do
    not assume every future `unique` string column needs the functional-index treatment, check the
    epics/UX docs for that field specifically first.

12. **A single-page app needs a history fallback in the image, and no test can see that it is
    missing.** Every route below `/` exists only in React Router. Nginx serves literal files, so
    `frontend/nginx.conf` has to answer unmatched paths with `index.html` or a refresh, a bookmark,
    or a pasted link on any surface returns 404 while the app itself looks perfect in dev and green
    in every test. Found by manually opening the Docker stack, not by the 24-test suite that shipped
    with Story 1.4. Two neighbouring rules in that same file: `/assets/` must `try_files $uri =404`
    ahead of the catch-all (otherwise a stale asset request is answered with HTML and a 200), and
    `index.html` must be sent `no-cache` (otherwise a redeploy serves a cached shell pointing at
    asset hashes that no longer exist). **Anything else served by that image, and any future route
    prefix, has to be reconciled with these three blocks.**

13. **Only a 401 means "signed out". Every other failure is a transport problem.** `httpClient`
    turns every failure into an `ApiError`, using **status 0 for "no response ever arrived"**
    (dead network, CORS, or its own `AbortController` timeout), precisely so callers can tell that
    apart from a rejected session. `RequireAuth` redirects to Login only when
    `error instanceof ApiError && error.status === 401`, and offers a Retry for anything else.
    Treating a bare `isError` as "not logged in", which is what shipped first, silently ejects a
    working session to the Login screen on a momentary blip, and `retry: false` on `useCurrentUser`
    means there is not even one retry to hide it. **Any future query whose failure drives navigation
    or an auth decision needs the same discrimination**, not a bare `isError`.

14. **`RequireAuth`'s Role-prefix check is a navigation affordance, not a security boundary.**
    `location.pathname.startsWith(ROLE_PATH_PREFIX[user.role])` keeps a Waiter from landing on an
    Admin URL, but it is plain prefix matching (so `/adminfoo` also matches `/admin`) and it runs
    entirely in the browser, where anyone can edit it. **The backend's `require_role` is the only
    real enforcement** (trap 8). As later stories put real data behind these surfaces, every one of
    them still needs its own role-gated endpoint; never treat "the nav does not show it" or "the
    guard redirected" as protection.

15. **A `yield` dependency on a `@websocket` route stays open for the connection's entire
    lifetime, not just one request.** `get_session_ws` (Story 1.5's first draft) was shaped like
    the REST `get_session`, so a session opened per-connection instead of per-query, pinning one
    pooled database connection for as long as the socket stayed open. Confirmed empirically: 6
    open sockets checked out 6 pooled connections, released only on disconnect, against a default
    `pool_size=5` + `max_overflow=10`, so the 16th concurrent device would exhaust the pool and
    block every REST request. Fixed with `clients/database.py`'s `session_scope()`, a context
    manager any non-request caller (a WebSocket handshake, `api/websocket.py`'s periodic
    re-verification tick) opens and closes around one query, never around the connection's
    lifetime. **Any future long-lived connection (a background task, a second WebSocket route)
    must use `session_scope()`, never a `yield` dependency shaped for a request/response cycle.**

16. **A `Numeric`/`Integer` column needs a matching Pydantic bound, or an out-of-range value
    500s instead of 422ing.** Hit twice, both from code review, not from writing the story fresh.
    Story 2.1: `Ingredient.min_stock_threshold`/`current_stock` (`Numeric(10, 3)`) had no
    `max_digits`/`decimal_places`, so a value with more digits than the column allowed reached
    Postgres and raised an unhandled `asyncpg.NumericValueOutOfRangeError`. Story 2.2: `Dish.price`
    got the `Numeric(8, 2)` bound applied proactively from that lesson, but `category_id`/
    `prep_time_minutes` (plain `Integer`, i.e. int4) had no upper bound at all, and a value beyond
    Postgres's int4 range raised `asyncpg.DataError: value out of int32 range` the same way.
    **Every `Decimal` field needs `Field(max_digits=..., decimal_places=...)` matching its
    `Numeric(p, s)` column exactly; every plain-`Integer`-backed `int` field needs `Field(le=2_147_483_647)`
    unless the column is `BigInteger`.** Check this for every new request schema, do not wait for
    review to catch it a third time.
    **Extended by Story 3.2's review: a numeric field's real bound is not always its own column's
    range.** `OrderItem.quantity` was correctly int4-bounded on its own `Integer` column, but
    `price_at_add * quantity` feeds `Order.total_amount`, a `Numeric(10, 2)`, so an int4-sized
    quantity overflows that ceiling and raises the same unhandled `NumericValueOutOfRangeError` one
    write later, on an Order nobody could then close. Capped at 99 per line
    (`MAX_ORDER_ITEM_QUANTITY`, `data_models/order.py`, a product decision not implied by any
    column). **Check every numeric field against what it is later multiplied, summed, or joined
    into, not only the column it is stored in.**

17. **RESOLVED by Story 2.3.** The `*NotFoundError` types now share one `NotFoundError(Exception)`
    base with a single handler, the same way `ConflictError` covers every 409. Story 2.3 crossed
    the fourth-instance threshold this trap named and did the refactor. The live rule from here:
    **a new 404 type subclasses `NotFoundError` and nothing else**, no new handler, no
    registration. Forgetting to subclass it does not fail loudly, it makes that error an
    unhandled 500, so `tests/test_migrations.py` carries an assertion that every class whose name
    ends in `NotFoundError` inherits the base.

18. **A rule of the form "only allow this while the row is in state X" must be one guarded
    `UPDATE`, never a read-then-write.** Story 2.4's Table edit is the reference implementation:
    `UPDATE ... WHERE id = ? AND status = 'available'`, with `rowcount == 0` meaning "rejected"
    (`TableService.update_table`). Reading the row, checking `.status` in Python, and then writing
    is the version that looks correct and silently permits the edit when someone changes the row in
    between. Two related sharp edges found in the same review:
    (a) **an early return for "nothing actually changed" skips the guard.** Story 2.4 shipped
    `if not changed_fields: return table`, which answered 200 for a no-op edit against an *occupied*
    table, reproduced against a live database. Any short-circuit before the guarded write has to
    re-check the state condition itself.
    (b) **a test that sets the row to the blocking state before the request starts proves nothing.**
    That is the plain "already in state X" case, and a naive read-then-write passes it identically.
    A real test has to change the state *between* the service's read and its write (patch the
    read method to commit the change from a second connection on its way out). See Testing.
    This generalizes AD-6's OrderItem transitions and is distinct from trap 9: use a guarded
    `UPDATE` when one row's own column gates its own write, and `SELECT ... FOR UPDATE` when the
    invariant spans multiple rows or multiple write paths (AD-8's `_lock_dish`).

19. **`Number()` on a form field, plus a nullable backend field, equals a silent partial write.**
    `Number("abc")` is `NaN`, and `JSON.stringify` serializes `NaN` as `null`. A Pydantic
    `int | None` field guarded by `if payload.x is not None` cannot tell an explicit `null` from an
    omitted field, so the null is skipped and the *other* fields in the same request are applied,
    returning 200. Reproduced in Story 2.4: `{"table_number": null, "capacity": 8}` answered 200
    having changed only the capacity, so the Admin believed both saved. Also note `Number("")` and
    `Number(" ")` are both `0`, so a non-empty check is not a validity check. **Fix both ends:**
    parse and validate the field in the browser before sending (never coerce with bare `Number()`),
    and reject an explicit `null` server-side rather than treating it as absent.

20. **`await db.rollback()` expires every object in the session, including `actor`.** Reading
    `actor.id` in a log line *after* the rollback triggers an implicit lazy load with no greenlet
    context to run it in, raising an unhandled `MissingGreenlet`, so the 409 the handler meant to
    return becomes a 500. Always log **before** rolling back. This bit four `IntegrityError`
    handlers across `TableService`, `MenuService` (twice) and `InventoryService`; all four are
    fixed, but the shape is easy to reintroduce because **no test reaches these branches**: a
    duplicate-check-before-insert always wins in a single-threaded test, so the handler only runs
    under a genuine concurrent race in production.

21. **Neither `pnpm test` nor a routine `npx tsc -b` run gets exercised against a fresh Docker
    image, so a build-breaking TypeScript error can sit in the tree for stories at a time.**
    `IngredientsPage.tsx`'s `handleCreate` guard (`unit === ""`) had been narrowed unreachable by
    the `canSubmit` expression a few lines above (a `const`-binding control-flow narrowing quirk:
    comparing `unit !== ""` once in an `&&` chain persists the narrowed type for the rest of the
    function, so the later `unit === ""` compares `Unit` against a literal it can no longer be).
    `npx tsc -b` reports it correctly whenever run, but Story 2.6 never ran a `docker compose build`
    after landing it, and no CI exists to run one automatically (see Workflow). It broke
    `docker compose build frontend` outright (`pnpm build` runs `tsc -b && vite build`, so a type
    error there fails the whole image, not a warning), and only surfaced when Story 3.1 needed a
    fresh image built. Fixed with `!unit` instead of the literal comparison (no narrowing
    ambiguity, `Unit` is always a non-empty string when set). **Run `npx tsc -b` as a matter of
    course before considering a frontend story done, not only `pnpm test`, since vitest never
    typechecks.**

22. **An Alembic column add with `nullable=False` and no `server_default` breaks its own
    downgrade/upgrade cycle the moment any row exists.** `downgrade()` drops the column; the
    re-`upgrade()` then violates NOT NULL on whatever rows survived the downgrade, and
    `entrypoint.sh` runs `alembic upgrade head` on every container start, so this is not a
    hypothetical, it is what a rollback-then-redeploy actually hits. The autogenerated shape for
    `OrderItem.price_at_add` (Story 3.2, `819cce996301`) was bare `nullable=False`, justified at
    write time by "the table is empty right now" — true for the very first `upgrade`, false for
    every run after. Fixed by adding with a temporary `server_default`, then dropping the default
    in the same revision (`op.add_column(..., server_default='0')` then
    `op.alter_column(..., server_default=None)`), so the ORM stays the only thing that decides a
    real value while the migration itself stays reversible. **Verify this by hand, not by
    reasoning about it**: downgrade a live database, insert a row through the now-missing column,
    re-upgrade, confirm it succeeds and the column ends `NOT NULL` with no lingering default. Any
    future `nullable=False` column add on a table a shipped story might already have inserted into
    needs the same treatment.

23. **A `providers.Factory` in `container.py` that injects another provider must be declared
    *after* it.** `DeclarativeContainer`'s provider declarations are plain Python class-body
    assignments, evaluated top to bottom, not resolved lazily by name. Story 3.3 needed
    `order_service` to receive `realtime_service`, but `order_service` was declared first (right
    after `table_service`), so the container raised `NameError: name 'realtime_service' is not
    defined` at import time the moment the injection was added. Fixed by moving `order_service`'s
    declaration below `realtime_service`'s (and `connection_registry`'s, which `realtime_service`
    itself depends on). **Any new cross-service dependency added to an existing provider needs the
    same check**: verify the provider it now references is declared earlier in the file, not just
    that it exists somewhere in it. **Hit a second time in Story 4.2**: `inventory_service` needed
    `realtime_service` injected (its first producer role, for `inventory.alerts_changed`) but was
    declared above it (right after `user_service`); moved below `order_service`'s own declaration,
    same fix shape, caught before it could raise rather than rediscovered.

24. **A page that exists, works, and is fully wired into the router is not necessarily reachable
    from anywhere a user can click, and a diff-only review cannot see that it isn't.** Story 2.6
    shipped `IngredientsPage.tsx` with a docstring deferring "click-to-detail" to Story 4.3, on the
    stated reason that it "needs the below-threshold comparison logic." That reason was wrong the
    moment it was written: plain row-click navigation needs zero comparison logic, only shortage
    *sorting/highlighting* does. Nobody re-examined it when Story 4.1 built the actual destination
    page (`IngredientDetailPage.tsx`), so the Ingredients list shipped a real, working screen with no
    way to reach it short of typing the URL by hand. None of the three automated review layers
    (Blind Hunter, Edge Case Hunter, Acceptance Auditor) caught it, since "no new code references
    this route" is not a gap a diff review checks, a route with a fully working page behind it looks
    identical, from a diff, to one nothing points at. Found only by manually clicking through the
    live Docker stack. Fixed by adding `useNavigate()` plus an `onClick`/`hover`/`cursor: pointer`
    `TableRow`, mirroring `TablesPage.tsx`'s own Story 3.1 tile-click-to-detail precedent. **Two
    standing rules**: a comment recording *why* something was deliberately deferred can itself be
    wrong, and the only way to catch that is to re-examine the stated reason at the moment the
    "later" story actually ships, not to trust it at face value forever; and when a story's scope
    note says "screen X stays unchanged," check first whether X is the only entry point to a page
    that story is building, if so the navigation link itself is in scope even though nothing else on
    X is.

25. **MUI's `Typography` `color` prop silently drops a dot-path theme value; only `sx` resolves
    one.** `"error.main"`/`"success.main"` are valid inside the `sx` prop, which resolves theme
    palette paths, but `Typography`'s bare `color` prop only accepts the literal tokens
    `TypographyPropsColorOverrides` declares (`"error"`, `"success"`, `"primary"`, etc.), never a
    dotted path. Passing one does not throw, warn, or fail a type check in any way that is visible
    without reading MUI's own types closely, it just matches none of MUI's internal
    `MuiTypography-color*` classes, so the text renders with correct content and **no color applied
    at all**. `IngredientDetailPage.tsx`'s movement-quantity cell shipped exactly this
    (`color={negative ? "error.main" : "success.main"}`), invisible to a `getByText`-only assertion
    and to all three code-review layers, since nothing in this codebase's test suite anywhere
    asserts a MUI color prop or CSS class (confirmed by grepping for `toHaveClass`/color assertions
    before writing this trap: zero hits, on any MUI component, in any test file). Fixed by switching
    to the bare tokens `"error"`/`"success"`. **This class of bug sits outside what this project's
    test suite can prove**: it is only ever going to be caught by a human looking at the running
    app, not by `getByText`, `toHaveClass`, or `tsc -b`. Worth remembering the next time a component
    passes a theme-path-shaped string to a prop that looks like it should accept one.

26. **A guarded UPDATE (trap 18) only closes the race for the column it guards on — a value read
    before that UPDATE and reused afterward is still stale.** Story 5.2's `pick_up_item` read
    `item.quantity` once, before its own `status == pending`-guarded UPDATE, then used that same
    in-memory value afterward to compute the stock deduction. The guard correctly serializes two
    concurrent pick-ups against each other, but says nothing about a concurrent `edit_item` call
    (also legally guarded on `status == pending`) changing `quantity` in the window between the
    read and the UPDATE — both writes can commit successfully, with the deduction silently using
    the pre-edit quantity. Found only by the code review's adversarial layer, not by any test: the
    only concurrency test in the story covered double-pick-up idempotency, not a stale-column-read-
    across-an-unrelated-concurrent-write. Fixed by re-reading (`await db.refresh(item)`)
    immediately after the guarded UPDATE succeeds, before using any of that row's other columns —
    at that point the row is no longer `pending`, so no further `edit_item` can land, making that
    refresh the last point the value could still change. Generalizes: after a guarded UPDATE
    succeeds, any other column on that row you're about to read for downstream logic needs a fresh
    read, not the one from before the guard ran.

27. **A value derived by aggregating several sibling rows needs a row lock too, even though no
    single row is being "written" the way trap 9's canonical cases are.** Story 5.3's
    `_recompute_order_status` reads every non-cancelled `OrderItem.status` for an Order and
    writes the aggregate onto `Order.status` — no guarded UPDATE applies (there is no expected
    prior value to check, FR-12's rule is a pure recompute, not a state-machine transition, see
    AD-6 vs. AD-5 distinction below), so it looked lock-free by construction. It wasn't: two
    concurrent transactions each finishing a *different* sibling Item (e.g. two Cooks marking two
    Items of the same Order ready within the same overlapping window) each read the other's
    not-yet-committed Item status under READ COMMITTED, each independently compute "no change"
    from their own narrow view, and both commit — leaving the aggregate stuck wrong with nothing
    left to re-trigger a correct recompute. Fixed by locking the *owning* row (`SELECT Order ...
    FOR UPDATE`, before reading the children), which is trap 9's mechanism applied to a case
    trap 9's own framing doesn't obviously cover: the row being locked is not itself one of the
    rows in conflict, it's the aggregate's anchor, and taking its lock is what serializes the two
    transactions' reads of the *set* of children. **Generalize: whenever a value is computed by
    reading N sibling/child rows and writing the result onto a parent, lock the parent before the
    read, regardless of whether any single row's own write looks unguarded in isolation.** Caught
    only by the code review's adversarial layer, reproduced with a genuine two-connection
    concurrency test (`asyncio.gather` across two independent `AsyncClient`s), not a monkeypatched
    interleave — trap 18's usual technique doesn't apply here, since the mechanism under test is a
    real DB-level lock, not a guarded UPDATE's rowcount.

28. **Invalidating a query key that belongs to the page you are about to navigate away from can
    race the navigation, flashing the wrong UI first.** Story 5.4's Close button called
    `closeMutation.mutate(undefined, { onSuccess: () => navigate("/waiter/tables") })`, and
    `useCloseOrder`'s own `onSettled` invalidated the just-closed Order's query key
    (`orderForTableQueryKey`). Hook-level mutation callbacks fire before call-level ones (trap:
    not obvious from either callback in isolation), so the invalidation's background refetch was
    already in flight before `navigate()` ran — and on localhost's near-zero latency, that
    refetch could resolve and re-render `TableOrderDetailPage.tsx` with its `hasNoOpenOrder`
    banner **before** the route change fully committed, a flash a human tester caught that no
    test (including this story's own) had covered. A first fix (gating the order-content block on
    `!hasNoOpenOrder` so the two states couldn't co-render) removed the *simultaneous* rendering
    but not the flash itself, since the banner could still legitimately render for one frame
    before navigation won the race. The real fix: stop invalidating that query key at all — once
    a mutation's own success handler is about to navigate away from the page a key belongs to,
    that page has nothing left to refresh, and refreshing it anyway only creates a race with the
    navigation for no benefit. **Generalize: before invalidating a query key inside a mutation
    hook, check whether every real caller of that mutation immediately navigates away on success —
    if so, the invalidation is very likely pure risk, not a safety net.**

---

## Where code goes

**Backend** — five top-level folders by responsibility. Don't add a sixth for something that fits one:

- `api/` — routers, one file per resource, each with its own `APIRouter` + prefix + tags.
  `api/router.py` is the aggregator only: it `include_router()`s the rest and holds nothing else.
  Handlers stay thin — validate, call a service, return the response model. **No SQLAlchemy queries
  and no business rules in a route handler.**
- `services/` — all business logic, one service per domain area. Registered as providers in
  `container.py` with dependencies injected. Design patterns (Repository, Strategy, State, Observer)
  live here.
- `clients/` — anything reached over a network or driver (`database.py` today; `llm.py` for OpenAI
  later). Constructed by the container, never instantiated ad hoc inside a service.
- `data_models/` — ORM schema only. No business logic. **Clarified 2026-08-08:** `api/` may import
  type-level names from here (Pydantic schemas, an enum like `UserRole`, an ORM class used only as
  a type annotation) for declaration purposes; querying, mutation, and domain rules still must stay
  in `services/`.
- `exceptions/` — top-level, holds the `AuthError` family plus `ForbiddenError` (a sibling, not a
  subclass, since it maps to 403 on an already-verified identity vs. 401). Add new exception types
  the same way rather than raising inline or building a second handler.

**Frontend** — respect the existing empty-but-intentional folders: `pages/` (route-level),
`components/` (reusable UI), `services/` (API calls), `types/` (shared types), `config/`.

---

## Language and framework rules

**Python**
- Imports are relative to `backend/` as root (the app runs from inside it). Never `from backend.X import ...`.
- Type hints on every signature, including generators and DI provider functions.
- Route handlers are `async def` with an explicit Pydantic `response_model` — never a bare dict.
- Custom exceptions go in `backend/exceptions/`; no inline `raise Exception(...)`.
- Log through the **injected loguru logger** from the container at every layer — never `print`, never
  a module-level logger built outside DI. Carry identifying context (order id, dish id, ingredient
  name, user id) so a flow can be traced end to end.

**TypeScript**
- `strict`, `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch` are enforced at
  build time — unused vars and non-exhaustive switches fail `pnpm build`, not just lint.
- `isolatedModules: true` — every file independently transpilable; no `const enum`.
- Never read `import.meta.env` in a component; always go through `src/config/config.ts`.

**Config** — `config.yaml` with `${ENV_VAR: default}` placeholders via `utils.load_config`. Not a
`.env`-only setup, not hardcoded values.

---

## Comments and docstrings

Docstrings are the documentation. Inline comments are the exception, not the habit.

**Exception: test files.** Everything below applies to application code. Inside `tests/`
(backend) and `*.test.tsx` / test-support files (frontend), skip docstrings entirely and
structure each test with `# Arrange` / `# Act` / `# Assert` comments instead. See Testing below.

**Required:**

- Every method and every function gets a docstring saying what it does, what each argument is, and what it returns. If it returns nothing, say so. If it raises, say what and when.
- Every class gets a docstring at the top of the class saying what it is and what it is for.
- Every module gets a short docstring at the top of the file when the filename alone does not make its purpose obvious.

**Style:**

- **Never use an em dash (—) in a docstring or comment.** Use a comma, a period, or a new sentence.
- Simple English. Short sentences. No long words where a short one works.
- Say what the code does, not how clever it is. No filler, no restating the function name.

**Inline comments:**

- Do not comment between the lines of a method by default. If the docstring says what the method does, the body should be readable without narration.
- Add an inline comment only when the code is genuinely hard to follow: a non-obvious algorithm, a workaround, an ordering that matters, a rule that looks wrong but is correct.
- When you do add one, explain **why**, not what. `# guard against a second cook picking this up mid-transaction` is useful. `# increment the counter` is not.
- Naming a design pattern in a comment is expected and encouraged here, since pattern usage is graded (see Academic context below).

**Python format** (standard triple-quoted docstring):

```python
class OrderService:
    """Handles order creation, item changes, and status transitions."""

    async def cancel_item(self, item_id: int, actor: User) -> OrderItem:
        """Cancel a single order item.

        Args:
            item_id: The order item to cancel.
            actor: The user performing the cancellation. Must be a waiter, cook, or admin.

        Returns:
            The updated order item, now cancelled.

        Raises:
            NotFoundError: If no order item matches item_id.
            InvalidTransitionError: If the item is already cancelled or served.
        """
```

**TypeScript format** (TSDoc, same rules):

```typescript
/**
 * Formats a price for display in the order total.
 *
 * @param cents - The price in whole cents.
 * @returns The price as a string with a currency symbol.
 */
```

---

## Binding architecture invariants

From the architecture spine — these are contracts, not suggestions. Cited by AD number in story ACs.

- **AD-1** DI container is the composition root; every lifecycle-managed resource is a `providers.Resource`.
- **AD-2** One WebSocket endpoint per authenticated session, role-scoped. Every state change emitted
  exactly once, by the service that owns the mutation, under a fixed past-tense `{domain}.{event}` name
  (e.g. `order.item_status_changed`).
- **AD-3** JWT at login as an httpOnly cookie, **8-hour expiry** (a work shift; no refresh-token flow —
  on expiry the user re-logs in). Every route except login/health verified via one shared FastAPI
  dependency. CORS allow-list, never wildcard.
- **AD-4** Alembic owns the schema; every `data_models/` change ships a migration; avoid multi-head
  across parallel branches.
- **AD-6** OrderItem status transitions are **guarded conditional updates** (`WHERE status = <expected>`,
  rowcount-checked). The `in_preparation` transition does status update + stock decrement +
  `StockMovement` insert in **one transaction**. Extended to `RestaurantTable` edits (must be `available`).
- **AD-7** `OrderItem.price_at_add` is stored; Order totals always computed from it over non-cancelled
  items — never a live Dish-price lookup. **First real application: Story 3.2.** Captured from
  `Dish.price` at insert time in `OrderService.add_item`, never rewritten by any later code path.
  `Order.total_amount` computation itself is still FR-8's job, unbuilt, so it stays `None` on every
  Order so far.
- **AD-8** Reject marking a Dish available with zero `RecipeIngredient` rows; reject removing the last
  row while available. **Both halves are now built** (first in Story 2.2's
  `MenuService.update_dish`/`_reject_if_recipe_empty`, second in Story 2.3's
  `remove_recipe_ingredient`). The two halves guard the same invariant from opposite directions and
  would otherwise interleave, so both take the same `_lock_dish` row lock (trap 9). Story 2.3 also
  added a rule AD-8 does not state but Epic 5 depends on: **a Recipe Ingredient line's unit must
  match its Ingredient's own unit**, since nothing in this system converts between units and a
  mismatch would make automatic deduction subtract the wrong amount silently.
- **AD-11** Cancelling an `in_preparation` OrderItem does **not** reverse its stock deduction. Ingredients
  are treated as already used. No compensating movement is created automatically.
- **AD-12** All OpenAI calls go through a `clients/` adapter behind an interface — never called from `services/`.
- **AD-14** One recipe-suggestion generation in flight per Cook: reject, don't queue. Write only after
  success — no orphaned rows on failure.
- **AD-15** Reject any User update that would leave zero active Admins.
- **AD-16** `Ingredient.current_stock` is **never clamped at zero**, on either the automatic or
  manual path. **First real application: Story 4.1.** `InventoryService.record_movement` applies a
  waste or negative-adjustment delta unconditionally, with tests asserting the exact negative
  resulting value, not merely "no error". The automatic path (consumption, at an OrderItem's
  transition to `in_preparation`) is still unbuilt, Epic 5's job.

---

## Domain rules worth restating

- `Order.status` (`pending`/`in_preparation`/`ready`) is **derived** from its non-cancelled OrderItems.
  `served` and `closed` are set explicitly. An Order with zero non-cancelled items is `pending`.
  **RESOLVED (both transitions built) by Story 5.4.** `OrderService.mark_served`/`close_order` are
  guarded UPDATEs (AD-6), not recomputes — `ready`/`pending` → `served`, `served` → `closed`.
  Closing also computes `Order.total_amount` (sum of `price_at_add × quantity` over non-cancelled
  items, AD-7) and returns the owning `RestaurantTable` to `available`, all three writes in one
  transaction.
- Stock deducts at **transition to `in_preparation`** (prep start), not at order placement.
- `StockMovement` is **append-only** — the audit trail. Never mutate a past row. No code path changes
  `current_stock` without a corresponding movement.
- Low-Stock Alert is a **derived state, not a stored entity** — an Ingredient is in shortage whenever
  stock < threshold. At most one active alert per ingredient; it clears when a movement restores it.
  **RESOLVED (built) by Story 4.2.** `InventoryService.list_alerts`/`GET /api/inventory/alerts` is
  the derived query (strictly `<`, not `<=`); no `LowStockAlert` table exists or is needed, since
  "at most one active alert per ingredient" and "clears automatically" both hold structurally (one
  `Ingredient` row, no alert entity to duplicate or dismiss). The live push
  (`inventory.alerts_changed`, to `warehouse_manager` only) is crossing-triggered from
  `record_movement`, not fired on every stock-decreasing movement — see `record_movement`'s own
  docstring and Story 4.2's Scope note for the exact reasoning. **Story 4.3 gave the derived state
  its second frontend consumer**: `IngredientsPage.tsx` reuses the same `useAlerts()` hook (not a
  second `current_stock < min_stock_threshold` comparison) to sort in-shortage Ingredients to the
  top and render them with a warning icon, entirely frontend, zero backend changes.
- Permissions are **Role-level only.** No per-resource filtering anywhere: every Waiter sees every
  Table; every Cook sees every chat session. "Current user's items first" is a *sort*, never a filter.
- An Admin sets a new User's **initial password** at creation and can **reset** it later. No
  self-service signup, no email recovery. Passwords are bcrypt-hashed, never logged or returned.
- Tables are **added and edited, never deleted.** Editing is gated on the table being `available`,
  enforced by a guarded conditional `UPDATE` (trap 18), and the Tables setup screen has no delete
  affordance anywhere by design (PRD Non-Goals). **RESOLVED by Story 3.1.** `GET /api/tables` now
  also permits `UserRole.waiter` via a new `TablesReadDep` (mirrors `MenuReadDep`/`InventoryReadDep`'s
  split), closing the gap this bullet used to flag as deferred to Epic 3. `POST`/`PATCH` stay on the
  original admin-only `TablesDep`, unchanged.
- **Opening a Table into an Order is the second guarded-UPDATE application (Story 3.1, AD-6),
  and the first route in the project scoped to exactly one non-admin Role with no admin
  fallback.** `OrderService.open_table` follows `TableService.update_table`'s exact shape:
  `UPDATE restaurant_tables SET status = 'occupied' WHERE id = :id AND status = 'available'`,
  rowcount-checked, only inserting the new `Order` (status `pending`, zero items) once that
  UPDATE succeeds, both writes committed together. `reserved` is treated identically to
  `occupied`, the guarded UPDATE cannot and does not need to tell them apart.
- **RESOLVED by Story 3.2.** `GET /api/menu/dishes` now also permits `UserRole.waiter`, via a new
  `DishCatalogReadDep` split off `list_dishes` alone (`MenuReadDep` itself, and every other menu
  read, stays admin+cook). A Waiter needs the dish catalog to add Order Items but has no FR-backed
  reason to read a Dish's recipe, so this is deliberately narrower than the `TablesReadDep`/
  `InventoryReadDep` precedent of widening a whole shared read-dep at once.
- **Order Item reads and writes are order-scoped (`/api/orders/{order_id}/items`), not
  table-scoped, and `OrderService.list_items`/`add_item` are a second application of
  `MenuService`'s list+add shape** (`list_recipe_ingredients`/`add_recipe_ingredient` →
  `list_items`/`add_item`). The frontend always has `order_id` in hand by the time it lists or adds
  items, via `GET /api/orders/tables/{table_id}` first, so no item route needs to carry both a
  `table_id` and an `order_id`. `add_item` is a plain check-then-insert (Dish exists, Dish is
  available, then insert at `pending`), no row lock, no guarded UPDATE. **Order Item quantity is
  capped at 99 per line** (`MAX_ORDER_ITEM_QUANTITY`, `data_models/order.py`), so
  `price_at_add * quantity` cannot overflow `Order.total_amount`'s `Numeric(10, 2)` once FR-8
  computes it (trap 16's extension). No guard exists yet against adding an item to a non-`pending`
  Order: no story so far can produce an Order in any other status (FR-8/close and `Order.status`
  derivation are FR-8/Story 3.3 territory), so that guard would be dead code no test could exercise
  honestly today, a deliberate omission, not an oversight.
- **Two screens currently disagree on the currency symbol.** `TableOrderDetailPage`'s Order Item
  rows render `42.00 ₪`, following that surface's own mockup; `cook/DishesPage.tsx` renders
  `$42.00`. Neither is wrong per its own story's scope, but only one should survive. Logged in
  `deferred-work.md`, not fixed by Story 3.2 since no AC there covers the Cook's screen. **Any
  story that touches price display should resolve this rather than adding a third convention.**
- **RESOLVED (partially) by Story 3.3.** `RealtimeService` now has its first two producers:
  `OrderService.open_table` broadcasts `table.status_changed`, `OrderService.add_item` broadcasts
  `order.item_added`, both to `UserRole.waiter`, both consumed live by `TablesPage.tsx`/
  `TableOrderDetailPage.tsx`. This is still not blanket coverage: `TableService.update_table` (Table
  edits) and any future Table-close path still push nothing, so Story 2.4's AC4 ("re-enable the
  moment the table returns to available") remains partially unmet, still deferred (see
  `deferred-work.md`). **Any story whose AC says "live", "instantly", or "the moment" for a mutation
  other than opening a Table or adding an Order Item still needs to check whether a producer exists
  for it.**
- **Story 3.4 added the `cancelled` OrderItemStatus and its edit/cancel rules.** An OrderItem can be
  edited (quantity/notes) only while `pending` (waiter-only); it can be cancelled from `pending` or
  `in_preparation` (waiter, cook, **and** admin — the first 3-role `require_role()` grant in the
  project). Cancelling never reverses stock (AD-11 applied for the first time in code, not just
  stated). `list_items` stays deliberately unfiltered — a cancelled line still shows, it just carries
  the `cancelled` badge — since no `Order.status` aggregate-derivation code exists yet to need
  filtering (that lands with Epic 5). Neither `edit_item` nor `cancel_item` broadcasts over the
  WebSocket; no AC in this story asked for "live", unlike Story 3.3's two producers. Backend grants
  Cook/Admin cancel permission with **no matching frontend screen yet** (Kitchen Display is still a
  placeholder, no admin/* screen shows Order data) — this is not a parity gap, it's the same
  ahead-of-UI pattern `InventoryWriteDep` set for Admin between Stories 2.1 and 2.6; the Waiter's
  `TableOrderDetailPage` is the only frontend consumer this story wires up.
- **Story 4.1 gave `InventoryService` its first write to `Ingredient.current_stock`** (AD-16), via
  three new routes reusing `InventoryReadDep`/`InventoryWriteDep` unchanged: `GET
  /ingredients/{id}`, `GET /ingredients/{id}/movements`, `POST /ingredients/{id}/movements`. Sign
  convention (FR-15): `purchase`/`waste` submit a positive magnitude and the service applies
  `+`/`-`; `adjustment` submits the already-signed delta directly; `consumption` is rejected at the
  schema level (`CreateStockMovementRequest`'s `model_validator`), it is Epic 5's automatic path
  only, never a manual input. `current_stock` is never floor-capped at zero on this path either, a
  `waste` or negative `adjustment` can drive it negative. The movement history's "Recorded by"
  column shows a raw `User #{id}`, never a resolved name, a conscious, reviewed decision: no
  endpoint any non-Admin role can call resolves a user id to a name, matching
  `OrderItemResponse.cook_id`'s existing no-join precedent (logged in `deferred-work.md`, not a
  gap this story needed to close).
- A Recipe Suggestion never writes to a live Dish — Admin confirmation is the only path to the menu.
- A newly created Dish is **unconditionally unavailable**, regardless of anything a caller submits
  (`CreateDishRequest` has no `is_available` field at all). Menu Categories are **create-only** in
  v1 so far (no update/delete endpoint exists, Story 2.2's explicit scope), and their name
  uniqueness is plain case-sensitive, unlike User/Ingredient names (trap 11).
- **A Cook can read the menu catalog (Categories, Dishes, Recipe Ingredient lines) and the
  Ingredient list, but has zero write access to any of it** (Story 2.5, FR-25). This is the first
  Role granted read access to a resource it cannot write to at all; `MenuReadDep`/`InventoryReadDep`
  are the pattern (a dedicated read-only dependency alongside the write-only one), the same shape
  `InventoryReadDep`/`InventoryWriteDep` already established in Story 2.1.
- **RESOLVED by Story 2.6.** The Category/Dish creation forms the UX mockup (`key-menu-management.html`)
  shows, and the Ingredients screen's own create form, now exist on `MenuManagementPage.tsx` and
  `IngredientsPage.tsx` respectively. Zero backend changes, both endpoints (`POST /api/menu/categories`,
  `POST /api/menu/dishes`, `POST /api/inventory/ingredients`) had existed unused since Stories 2.1/2.2.
  No dialog anywhere: both forms are always-visible inline forms, and the dish form's Category picker
  gets a small "+ New category" in-place reveal (a text field + Confirm/Cancel swapping in where the
  picker is), the same component-local-boolean-reveal shape `TablesSetupPage`'s `TableListRow`
  established for row editing.
- The single WebSocket connection (`/api/ws`, Story 1.5) is **one per authenticated session**: a
  second connection from the same User closes the first. A connection's session is re-verified
  periodically while it stays open, so a socket cannot outlive its JWT or survive a Role change/
  deactivation indefinitely (bounded by the re-verification interval, not instant).
- **RESOLVED by Story 1.7.** User logout was missing from the PRD/epics entirely until a
  `correct-course` pass added FR-26. `POST /api/auth/logout` clears the client's cookie only, it
  does **not** revoke the underlying JWT server-side (v1 has no revocation store, AD-3), so a token
  copied out before logout stays valid until its natural 8-hour expiry if replayed. An accepted v1
  scope limitation (closed-staff, physical-terminal threat model), not a bug. The route is
  deliberately unauthenticated (no `CurrentUserDep`), so it succeeds even against a missing or
  expired cookie, logout must never itself 401 the person trying to end their session.

---

## Testing

**Both harnesses are live as of Story 1.0.** Run `uv run pytest` from `backend/` and `pnpm test`
from `frontend/`.

- Backend: `pytest` + `pytest-asyncio` + `httpx.AsyncClient`, declared as a PEP 735
  `[dependency-groups] dev` group (never main `dependencies` — the Dockerfile runs
  `uv sync --no-dev`). `backend/tests/conftest.py` provides `client` (async HTTP client over the
  app, entering the real lifespan) and `db_session` (bound to a throwaway database migrated by
  `alembic upgrade head`, not `create_all`, so the suite continuously proves the migration chain
  works). Fixture names: `client`, `db_session`, `migrated_database` (session-scoped),
  `empty_database`. Async fixtures use `@pytest_asyncio.fixture`, never plain `@pytest.fixture`
  (pytest-asyncio 1.x removed the `event_loop` fixture, don't define one).
- Frontend: `vitest` + `@testing-library/react` + `jest-dom`, exposed as `pnpm test`. Configure
  vitest via `defineConfig` from `"vitest/config"` (not `"vite"` — that import doesn't type the
  `test` key and fails the strict build).
- **Test files do not use docstrings.** Every test method is organized with plain
  `# Arrange` / `# Act` / `# Assert` comments instead (omit a section with nothing in it). This is
  a deliberate carve-out from the "Comments and docstrings" rule below, scoped to `tests/` and
  `*.test.tsx` files only — everything else still requires docstrings.
- **`db_session` truncates every model table after each test** (Story 1.1). Rows must be
  committed for the app under test to see them over its own connection, so isolation is
  truncation afterwards, not a rollback. Write tests freely; they will not leak into the next
  test. `alembic_version` is untouched, so the migration state survives.
- Hash passwords in tests through `AuthService.hash_password`, never `bcrypt.hashpw` directly, so
  account creation and login can never diverge on cost or salt settings.
- No `pytest-xdist` and no CI pipeline exist yet, so the session-scoped test database fixture has
  no per-worker isolation. Fine today; revisit if parallel test execution is introduced.
- **`frontend/src/setupTests.ts` calls `@testing-library/react`'s `cleanup()` in an explicit
  `afterEach` (Story 1.4).** RTL's own auto-cleanup only registers itself if it detects a global
  `afterEach`, and `vite.config.ts`'s `globals: false` deliberately does not provide one (every test
  file imports `describe`/`it`/`expect` itself). Without the explicit call, a second `it()` in the
  same file that renders another component leaves the first render's DOM in place, so queries like
  `getByRole` start matching more than one element. Any new test file with more than one `render()`
  call across its `it()` blocks needs nothing extra, `setupTests.ts` already covers it.
- **Import `RouterProvider` from `"react-router"`, never `"react-router/dom"` (Story 1.4).** The
  `/dom` subpath's `RouterProvider` is a thin wrapper that also passes `flushSync: ReactDOM.flushSync`
  to the real one; under this project's React 19.2.6 + react-router 7.8.0 + jsdom/Vitest combination,
  that wrapper reproducibly breaks the Router context, `useLocation`/`useNavigate`/`NavLink` anywhere
  in the tree then throw "may be used only in the context of a `<Router>` component," even outside
  tests (verified with a two-line repro, not a testing-only quirk). Everything else routing-related
  (`createBrowserRouter`, `createMemoryRouter`, `NavLink`, `Navigate`, `Outlet`, `useLocation`,
  `useNavigate`) already lives on the core `"react-router"` export, so there is no reason to reach for
  `/dom` at all in this codebase.

- **Mocking a service in every test hides the wiring between that service and its callers
  (Story 1.4 review).** Story 1.4 shipped with `authService` `vi.mock`ed in all four component test
  files, so `retry: false`, the login invalidation, and the query-to-guard handover never actually
  ran anywhere. `frontend/src/appIntegration.test.tsx` is the counterweight and the pattern to copy:
  **one file per feature that mocks only `fetch`** and drives the real hooks, real router and real
  guard end to end. Component tests may keep mocking the service; at least one test must not.
- **A regression test that cannot fail is worse than none, so make it fail first.** Two traps hit
  during the same review. A stubbed `fetch` that resolves in a microtask lands before React
  re-renders, so any ordering bug it is meant to catch is invisible, use a real `setTimeout` delay
  when the timing *is* the thing under test. And an assertion derived from the DOM (reading tab
  order out of `getAllByRole("link")` and then asserting tab order) is a tautology, derive expected
  values from the config the code reads, e.g. `ROLE_NAV_ITEMS`. **Before trusting a new regression
  test, reintroduce the bug and watch it go red.** Doing exactly that is what proved one of the
  review's own "high severity" findings was a false positive.

- **A WebSocket broadcast test needs a real `uvicorn.Server`, not `TestClient` (Story 1.5).**
  `TestClient.websocket_connect` runs the ASGI app in a separate thread with its own event loop, so
  a broadcast call from the test would race the connection registry across two loops.
  `tests/test_websocket.py` instead runs a real `uvicorn.Server` on an ephemeral port, sharing the
  test's own event loop, `lifespan="on"` so the server's own startup/shutdown pairs with
  `container.init_resources()`/`shutdown_resources()` symmetrically. Do **not** call
  `container.init_resources()` manually alongside `lifespan="off"`, that leaves the database engine
  bound to a pytest-asyncio event loop a later test's own loop has already replaced, surfacing as
  `asyncpg.InterfaceError: another operation is in progress` in whichever test runs next.
  `TestClient.websocket_connect` also does not reuse the client's HTTP cookie jar, pass the session
  cookie explicitly via a `Cookie` header.
- **Verify a numeric claim against a live Postgres before writing the assertion.** Two review
  findings (trap 16) were confirmed by actually sending the oversized value against a running
  database and reading the real exception, not by reasoning about Pydantic's field constraints in
  the abstract. A first attempt at the Story 2.1 precision test used a value that turned out to be
  exactly at the boundary (accepted, not rejected); caught only by running it.

- **"Make it fail first" has a specific failure mode: a test that pins the wrong thing.** This rule
  has now been broken three times, twice by tests whose *shape* made them unfalsifiable rather than
  by a missing red run. Story 2.4's AC6 test is the sharpest example: it was byte-for-byte identical
  to the AC4 "already occupied" test, so it passed under both the guarded `UPDATE` it was meant to
  pin **and** the naive read-then-write that AC exists to forbid. The check that catches this is not
  "did I watch it go red once", it is **"if I implement the wrong thing, does this test notice?"**
  For any test guarding a concurrency rule, write the wrong implementation, run the test, and
  confirm it fails. Two related shapes already documented above: an assertion derived from the DOM
  it is asserting on, and a stubbed `fetch` that resolves before React re-renders.
- **Testing a race needs the state change to land mid-request.** Setting the row to its blocking
  state before calling the endpoint tests the ordinary rejection, not the race. `test_tables.py`'s
  `test_race_between_form_load_and_save_is_rejected` is the pattern: `monkeypatch` the service's
  read method so it commits the conflicting change from the test's own session on its way out,
  which puts the change strictly between the read and the write. Assert both the 409 **and** that
  the write did not land.
- **A backend `IntegrityError`/rollback branch is usually unreachable from the suite.** Any handler
  that only runs when a pre-check loses a race will never execute in a single-threaded test, so it
  can carry a crashing bug (trap 20) while the suite stays green. When writing one, verify its
  mechanism directly (a focused probe) rather than assuming coverage.

Every story in `epics.md` is written as Given/When/Then acceptance criteria, those are the tests.
Backend suite is now **249 tests**, frontend **133 tests** (as of Story 3.3).

---

## Workflow

- Branches: `feature/<name>` or `fix/<name>`.
- Commits: imperative-mood summary line, no conventional-commit prefixes (`feat:`/`fix:`). A substantive change gets a short wrapped body explaining what and why; trivial ones stay summary-only.
- Everything lands via GitHub PR into `main`; no direct pushes.
- **No CI/CD** (`.github/workflows` absent) and **no linter/formatter configured** on either side —
  nothing gates a merge but review. Don't add lint-suppression comments for rules that don't exist.
- Local dev: `docker compose up`. A native Postgres on this machine also binds 5432 — stop it first
  (`sudo launchctl unload /Library/LaunchDaemons/postgresql-16.plist`) if the port is taken.

---

## Academic context (shapes what "good" means here)

This is the final project for an OOP workshop. **Design and analysis documentation carries roughly
the same weight as the working implementation.** Prefer an explicit, recognizable design pattern over
the shortest path to a feature, and name the pattern in a comment or PR description — that
traceability is graded. Don't add scope beyond the epics to look more impressive; that time is
better spent on design depth.

---

## Maintaining this file

Regenerate when the installed-vs-decided table stops matching the manifests, or when a story lands
that removes one of the silent traps above (Story 1.0 killed trap 2; Story 1.1 kills 1, 3, 4, 5).
Keep it lean — facts an agent can't infer from the code in front of it.

**2026-08-08 patch (Story 1.0 landed, PR #121 merged to main):** installed-vs-decided table,
current-state tree, trap 2, and Testing updated in place rather than a full regenerate. Everything
else in this file is still as of 2026-08-02 and should be checked against the code before being
trusted for later stories.

**2026-08-08 patch (Story 1.1 code review):** traps 1, 3, 4 and 5 marked resolved and rewritten as
the live rules they became; traps 6 and 7 added for the new `.env` secret mechanism and the
localhost-only cookie scope; installed-vs-decided table updated (bcrypt, pyjwt and python-dotenv
are installed, only openai is still pending); Testing updated for the new per-test truncation and
the `AuthService.hash_password` seam.

**2026-08-08 patch (Story 1.2, PR #124 merged to main):** current-state tree brought up to date
(`api/auth.py`, `api/dependencies.py`, `services/auth_service.py`, `exceptions/` now listed; no
more "predates Story 1.1" warning). Trap 8 added for `require_role`/`ForbiddenError`: built, wired
to a 403 handler, but not yet used by any route, with two review-deferred obligations
(OpenAPI 403 documentation, service-layer denial logging) that land on the story that adds the
first protected route. "Where code goes" updated for the architecture spine's same-day
type-vs-behaviour clarification on `api/` importing from `data_models/`, and for `exceptions/`
now existing rather than being a placeholder. No new packages landed in Story 1.2; the
installed-vs-decided table is unchanged. Next story per sprint-status.yaml: **1.3, Admin Manages
User Accounts** (backend-only scope expected, matching 1.0-1.3's pattern; the Users screen UI
depends on Story 1.4's shell/routing/MUI setup, which has not landed).

**2026-08-10 patch (Story 1.3 + its code review):** trap 8 rewritten as resolved, since Story 1.3
mounted the first `require_role` route and discharged both of Story 1.2's deferred obligations;
`api/admin.py` named as the reference implementation. Traps 9, 10 and 11 added from the review,
all three generalizable beyond this story: read-then-write invariant checks need row locks,
byte-vs-character bounds on password fields, and the three-places-must-agree username
normalization rule. Current-state tree updated for `services/user_service.py`, `api/admin.py`, and
the second Alembic revision. Testing note: the suite is 107 tests; `tests/conftest.py`'s `client`
fixture uses an `https` base URL because the session cookie is `Secure` and httpx, unlike a
browser, has no localhost exemption.

**2026-08-10 patch (Story 1.4, application shell/routing/nav):** installed-vs-decided table updated,
react-router, MUI (+icons +emotion), and @tanstack/react-query all landed, nothing left pending on
the frontend side. `GET /api/auth/me` added to `api/auth.py`, not named by any FR/AC but required
infrastructure: the frontend's only way to learn who is logged in and what Role they hold across a
page reload, since the session cookie is httpOnly. Backend and frontend current-state trees both
rewritten (frontend was "scaffold only," now has the full shell: routing, per-role nav, theme,
Skeleton/Reconnecting scaffolds; backend tree also caught up to Story 1.3's `admin.py`/
`user_service.py`/`exceptions/handlers.py`, which the prior patch missed). Two new Testing entries:
`setupTests.ts` needs an explicit `afterEach(cleanup)` because `globals: false` defeats
`@testing-library/react`'s own auto-cleanup detection; `RouterProvider` must come from `"react-router"`
core, never `"react-router/dom"` (its `flushSync` wrapper reproducibly breaks Router context under
this project's React 19.2.6 + react-router 7.8.0 combination). Backend suite is 109 tests.

**2026-08-11 patch (Story 1.4 code review):** three traps added, all generalizable beyond this
story. Trap 12: a single-page app needs an nginx history fallback in the image, plus an `/assets/`
404 guard and a `no-cache` on `index.html`, and no test in the suite can see when it is missing.
Trap 13: only a 401 means "signed out", so `httpClient` now reports an unreachable backend as
`ApiError` with **status 0** and `RequireAuth` discriminates on it instead of redirecting on any
error. Trap 14: the guard's Role-prefix check is a navigation affordance, not a security boundary,
the backend's `require_role` remains the only enforcement. Two Testing entries added, on the
service-mocking blind spot (with `appIntegration.test.tsx` as the pattern to copy) and on proving a
regression test can actually fail before trusting it. Frontend current-state tree updated for
`AppShellSkeleton` and `nginx.conf`. AC4's wording was amended to key the dark default off the Cook
Role rather than the Kitchen Display surface, matching the implementation. Suites are now **111
backend and 34 frontend tests**.

**2026-08-11 patch (Story 1.5, Real-Time Push Transport, plus its code review):** first WebSocket
transport landed: `api/websocket.py` (the single `/api/ws` endpoint), `clients/websocket.py`
(`ConnectionRegistry`, keyed by user id so one connection per session is enforceable and a
broadcast can target several Roles in one call), `services/realtime_service.py`, and the frontend's
`RealtimeProvider.tsx` (replacing the static `ConnectionStatusProvider` in `App.tsx`, now mounted
inside `RequireAuth`). Trap 15 added (a WebSocket `yield` dependency pins a pooled DB connection for
the connection's whole lifetime, confirmed by reproducing pool exhaustion directly); `clients/database.py`
gained `session_scope()` as the fix. `api/dependencies.py` gained the WebSocket-route counterparts
`CurrentUserWsDep`/`verify_ws_origin`. A new Testing entry documents the real-`uvicorn.Server`
pattern needed for broadcast tests, since `TestClient` cannot share an event loop with the app.

**2026-08-11 patch (Story 2.1, Create and Manage Ingredients, plus its code review):** first
`inventory` domain router: `api/inventory.py` (`POST /api/inventory/ingredients`, the first route to
permit two Roles via `require_role`), `services/inventory_service.py`. Trap 11 extended: the
username case-insensitive-uniqueness fix was reused verbatim for `Ingredient.name` (revision
`daca523f69f5`), now a two-instance precedent rather than a username-only quirk. Trap 16 added
(first occurrence): a `Numeric` column needs a matching `max_digits`/`decimal_places` bound or an
oversized value 500s instead of 422ing, confirmed by reproducing the raw `asyncpg` error against a
live database.

**2026-08-12 patch (Story 2.2, Manage Menu Categories and Dishes, plus its code review):** first
`menu` domain router: `api/menu.py` (category create, dish create/update, admin-only),
`services/menu_service.py`, and AD-8's first half (the availability-toggle gate). Two new
`ConflictError` subclasses (`DuplicateCategoryNameError`, `EmptyRecipeError`) and two new bare-404
types (`CategoryNotFoundError`, `DishNotFoundError`) added to `exceptions/`. Trap 16 extended
(second occurrence, this time on plain `Integer` columns rather than `Numeric`): `category_id`/
`prep_time_minutes` had no upper bound, so a value beyond Postgres's int4 range also 500'd, fixed
with `Field(le=2_147_483_647)`. Trap 17 added: `CategoryNotFoundError`/`DishNotFoundError` duplicate
`UserNotFoundError`'s shape by deliberate choice rather than sharing a base, revisit if a fourth
`*NotFoundError` ever appears. `Dish.is_available`'s column-level default corrected from `True` to
`False` to align with AD-8 (no migration needed, it was never a `server_default`). Domain rules
section gained notes on Dish's unconditional-unavailable-at-creation rule, Category's create-only/
case-sensitive scope, and the WebSocket one-connection-per-session/periodic-re-verification
behavior (the latter carried over from Story 1.5, missed by that patch). Suites are now **158
backend and 47 frontend tests**.

**2026-08-12 patch (Story 2.3, Define a Dish's Recipe, plus its code review):** Recipe Ingredient
CRUD landed on `api/menu.py`/`MenuService`, closing AD-8's second half, alongside three enabling
reads (`GET /menu/categories`, `GET /menu/dishes`, `GET /inventory/ingredients`). Trap 17 marked
**resolved**: this story crossed the fourth-`*NotFoundError` threshold it named, so the shared
`NotFoundError` base plus one handler now exists and three near-duplicate handlers were collapsed
into one; `tests/test_migrations.py` gained an assertion pinning the inheritance, since forgetting
it yields a silent 500. AD-8's entry rewritten (both halves built) and extended with the
unit-must-match-the-Ingredient rule, which no AD states but Epic 5's deduction depends on. Trap 9's
prescription was applied to AD-8 for the first time (`MenuService._lock_dish`), after the review
found that this story's own spec had wrongly told the developer to skip the lock: two concurrent
deletes could leave an available Dish with an empty recipe. **First real domain screens** on the
frontend (`MenuManagementPage` + `components/menu/DishRecipeEditor`), plus the first per-domain
service files beyond `authService`. The frontend current-state tree and a new "shape every domain
screen should copy" list capture the review's UI findings, all of which were silent-failure states.

**2026-08-12 patch (Story 2.4, Manage Restaurant Tables, plus its code review):** `api/tables.py` +
`services/table_service.py` + `TablesSetupPage`, completing Epic 2's authoring surfaces. Three new
traps, all generalizable. **Trap 18**: a "only while the row is in state X" rule must be one guarded
`UPDATE`, not a read-then-write, with two sharp edges the review found in this story's own code (a
no-op early return that skipped the guard and answered 200 on an occupied table, and a race test
that could not fail because it set the blocking state before the request started). It also draws the
line between trap 18's guarded `UPDATE` and trap 9's `SELECT ... FOR UPDATE`. **Trap 19**:
`Number()` on a form field plus a nullable backend field equals a silent partial write, reproduced
end to end. **Trap 20**: `db.rollback()` expires `actor`, so logging `actor.id` afterward raises
`MissingGreenlet` and turns an intended 409 into a 500; four handlers carried this, all now fixed,
and none of them is reachable from the test suite. Domain rules gained the note that
`RealtimeService` still has **no producers**, which is what leaves Story 2.4's AC4 partially unmet
(deferred to Epic 3 by decision). Testing section gained the "a test that pins the wrong thing"
lesson, the mid-request race-testing pattern, and the warning that rollback branches are unreachable
from the suite. Suites are now **212 backend and 66 frontend tests**.

**2026-08-13 patch (Story 2.5, Cook Browses the Dish Catalog, plus its code review):** Zero new
backend endpoints or schemas, deliberately: `MenuReadDep` (new, `api/menu.py`) and `InventoryReadDep`
(widened, `api/inventory.py`) now also permit `UserRole.cook` on the existing list/read routes only,
every write route unchanged. First Role granted read access with zero write access to the same
resource. Real frontend screen `cook/DishesPage.tsx` replaces its placeholder, the third real domain
screen after `MenuManagementPage`/`TablesSetupPage`. The review reproduced and fixed a real "silent
blank page" bug: only `useDishes()`'s loading/error state drove the page, so a `useCategories()`/
`useIngredients()` failure was completely invisible, no error, no empty state, nothing rendered but
the heading. Added to "the shape every new domain screen should copy": a page driven by more than
one independent query must OR every query's `isLoading`/`isError` together, not just the "main"
one's. Also fixed, in the same review: a Dish whose Category couldn't be resolved was silently
dropped instead of falling back to `#{id}` (this story's own spec had said to do this and the first
implementation pass hadn't actually done it), and a failed Ingredient-list fetch silently degraded
Recipe Ingredient lines to raw ids with no warning. **Separately, found while manually testing the
running stack (not a code defect): no story anywhere in the plan builds the Category/Dish creation
forms the UX mockup shows.** Traced through Stories 2.2 and 2.3, confirmed via every story title
across all 6 epics, logged as a genuine planning gap in `deferred-work.md` and in Domain rules
above, not fixed here (out of this story's scope). Suites are now **213 backend and 76 frontend
tests**.

**2026-08-13 patch (Story 1.6, Manage User Accounts from the Admin UI):** Zero backend changes —
Story 1.3 already built and tested every endpoint this story needed; only `admin/UsersPage.tsx`
(the fourth real domain screen, replacing its placeholder) and the new `services/userService.ts`
landed. `types/user.ts`'s existing `CurrentUser` (built for `GET /api/auth/me` in Story 1.1) was
reused as the list-row type rather than duplicated, since its shape already matched
`UserResponse` byte for byte — worth checking `types/` for an existing match before adding a new
type on any future story that wires a screen to an already-shipped endpoint. Resolves the
`deferred-work.md` item on self-deactivation (Story 1.3's review): the signed-in Admin's own row
now shows "This is you" in place of Deactivate, matching `key-users.html` exactly, going one step
further than the confirmation-step fix that item suggested. AD-15's last-Admin lockout was already
enforced server-side; this story only renders its existing 409 inline. Suites are now **213
backend and 93 frontend tests**.

**2026-08-13 patch (Story 2.6, Create Menu Categories, Dishes, and Ingredients from the Admin UI):**
Frontend-only, zero backend changes: the two gaps Story 2.5's review logged (no Category/Dish
creation UI, `IngredientsPage.tsx` still a bare placeholder) are both closed. `menuService.ts` gained
`useCreateCategory`/`useCreateDish` (payload types private to the file, per `tableService.ts`'s
precedent); `inventoryService.ts` gained `useCreateIngredient` and promoted its query key to a named
`INGREDIENTS_QUERY_KEY` constant, matching every other service file. `MenuManagementPage.tsx` gained
an always-visible "+ New dish" form with an inline "+ New category" reveal on its Category picker (a
component-local boolean swap, the same shape `TablesSetupPage`'s `TableListRow` uses for row editing;
no dialog, this codebase has never introduced one). `IngredientsPage.tsx` went from a one-line
placeholder to a real screen: an "Add ingredient" form plus a dense-row list, deliberately without
shortage sorting/highlighting/a Status column/click-to-detail, that scope stays with Epic 4's Story
4.3. Alongside this story's own work (not optional polish, required for the new dish-creation form
to fail loudly rather than silently): `MenuManagementPage.tsx` had the same "silent blank page" bug
Story 2.5's review found and fixed in `DishesPage` — only `useDishes()`'s `isLoading`/`isError` drove
the page, `useCategories()`'s own state was read for data only, never checked. It was never
backported to this file; fixed here the same way, `isLoading`/`isError` now OR'd across both queries
and Retry refetches both. The Task 1 regression test for this fix, and the two duplicate-name/empty-
state assertions in the new `IngredientsPage.test.tsx`, were each mutation-tested (behavior
temporarily reverted, confirmed the test actually fails, then restored) before being trusted.

**The review's most consequential finding was an AC that the routing architecture made unreachable.**
AC4 names both Warehouse Manager and Admin as able to create Ingredients, and
`InventoryWriteDep` has permitted both since Story 2.1 — but `RequireAuth` gated every route on a
single `ROLE_PATH_PREFIX[role]` string, and `/warehouse/ingredients` is outside `/admin`, so an Admin
was redirected away from a screen the backend explicitly authorized them for. Fixed by adding an
`Ingredients` entry to `ROLE_NAV_ITEMS.admin` and replacing the prefix comparison with a new
`canRoleVisit(role, pathname)` in `navigationConfig.ts` (anything under the Role's own prefix, **or**
an exact match on a surface that Role's own nav links to). **The generalizable rule: derive
cross-prefix route reachability from the nav config rather than keeping a second hand-maintained
list** — that makes a nav entry a Role cannot open unrepresentable. Note the converse does *not*
hold and deliberately so: the prefix clause grants a Role's own subtree whether or not the nav links
to it, which is what lets detail routes like `/waiter/tables/:tableId` work without their own entry.
A second review round caught two bugs in the first version of this fix: prefix matching that ignored
segment boundaries (so `/admin` would also match a future `/administration`), and a `startsWith` on
nav paths that silently handed Admin `/warehouse/ingredients/:ingredientId`, Story 4.3's surface. The
nav clause is now an exact match and the prefix clause is segment-aware. The check remains a
navigation affordance, never a security boundary (trap 14). **Story 1.4's AC2 was amended by
correct-course in the same story** (`epics.md`, `EXPERIENCE.md`): it had read "no cross-role
navigation anywhere", keying the rule to URL shape, when the intent was always authorization —
a Waiter must never see Admin tools. Other review patches: a submit handler must
re-check its *full* predicate rather than trusting the disabled button (Enter submits a form
regardless, and the checks both handlers had omitted were exactly the ones guarding a blank name and
a duplicate in-flight request); an inline reveal nested inside another form needs its own Enter
handling or the outer form's implicit submit steals it; and a mutation whose caller immediately
selects the created row should seed the cache in `onSuccess` before invalidating, since invalidation
only *schedules* a refetch. Suites are now **213 backend and 90 frontend tests**.

**2026-08-14 patch (Story 3.1, Open a Table and Start an Order, plus its code review):** First
`orders` domain route: `api/orders.py` (`POST /api/orders/tables/{table_id}/open`), `OrderResponse`
(`data_models/order.py`), `TableNotAvailableError` (`exceptions/__init__.py`, distinct from
`TableInUseError` since that one's docstring scopes it specifically to an Admin's edit attempt),
and `services/order_service.py`. `OrderService.open_table` is the second application of AD-6's
guarded-UPDATE pattern (`table_service.py`'s `update_table` was the first), with its read step
factored into a private `_get_table` seam purely so the race test could monkeypatch it, mirroring
`TableService.get_table`'s own role in trap 18's test. `GET /api/tables` widened onto a new
`TablesReadDep` (admin, waiter), closing the gap this file had flagged as deferred to Epic 3 since
Story 2.4; `POST`/`PATCH` stay admin-only, unchanged. First route in the project gated to exactly
one non-admin Role with no admin fallback (`require_role(UserRole.waiter)`).

Frontend: `waiter/TablesPage.tsx` replaces its Story 1.4 placeholder, the fifth real domain screen.
Reused the existing `useTables()` hook rather than duplicating it in the new `orderService.ts`
(a deliberate deviation from the story's literal task text, exporting `TABLES_QUERY_KEY` from
`tableService.ts` instead); `useOpenTable()` invalidates `onSettled`, not `onSuccess` only, per the
review (a lost race means the cached `available` status is already stale, same reasoning
`useUpdateTable` documented first). `TableOrderDetailPage.tsx` remains a placeholder by design,
Story 3.2/3.3+ territory.

**Trap 21 added**, found while standing up a fresh Docker image for manual testing, not by any
test suite: a pre-existing Story 2.6 TypeScript error in `IngredientsPage.tsx` (a `const`-narrowing
quirk making one branch of a submit guard unreachable) had sat in the tree undetected because
neither `pnpm test` nor routine development ever ran a full `docker compose build`, and `pnpm
build`'s `tsc -b` step fails the whole image on a type error. Fixed as an incidental one-line
change, unrelated to this story's own scope. Domain rules gained the note that opening a Table is
the second guarded-UPDATE application. Suites are now **225 backend and 117 frontend tests**.

**2026-08-14 patch (Story 1.7, User Logout, plus its code review):** Added retroactively via
`correct-course` after discovering, during manual testing, that logout did not exist anywhere in the
PRD, epics, UX mockups, or code (confirmed by grep across `backend/`/`frontend/src/`, zero matches).
FR-26 added to the PRD; Story 1.7 added to Epic 1 alongside the other auth-lifecycle stories, even
though Epic 1's other 6 stories were already `done`.

`POST /api/auth/logout` (`api/auth.py`) clears the session cookie via `response.delete_cookie` with
attributes matching `login`'s own `set_cookie` call exactly (a mismatch would leave the browser's
cookie in place). Deliberately **not** gated behind `CurrentUserDep`, unlike every other protected
route: logout must succeed even when the presented cookie is missing, expired, or otherwise invalid,
so a User on a lapsed tab can still click Sign Out and land cleanly on Login. This is a one-route
exception to the "every mutating action requires an authenticated session" posture (NFR-2), justified
because logout mutates no domain resource, only the client's own cookie. `useLogout()` (`authService.ts`)
mirrors `useLogin()`'s invalidation shape and deliberately adds **no** manual `navigate()`, it relies
on `RequireAuth`'s existing 401-redirect firing once the invalidated `useCurrentUser()` query refetches
as unauthorized, reusing the exact same path an expired session already takes rather than adding a
second, parallel one. `AppShell.tsx` gained a Sign Out `IconButton` next to `ThemeToggle`.

The review's most substantive finding, after 7 others were dismissed as false positives on inspection
(the "cookie attribute mismatch" and "CSRF" claims didn't survive checking `login`'s own `set_cookie`
call and `SameSite=lax`'s actual semantics; a "malformed cookie" test would have exercised nothing
since `logout` never reads the cookie's contents at all): `useLogout()` had no `onError` handling and
`AppShell` showed no failure state, violating this file's own "every mutation renders its own isError"
rule (see "the shape every new domain screen should copy" above) — the first place that rule was
checked against shell-level chrome rather than a page-level form. Fixed with an inline `Alert`
rendering the backend's own error message, per UX-DR17, plus a covering integration test. Domain rules
gained the note that logout clears the client's cookie only, v1 has no server-side JWT revocation
(AD-3), a token copied out beforehand stays valid until natural expiry, an accepted v1 limitation, not
a gap this story could or should close. Suites are now **229 backend and 119 frontend tests**.

**2026-08-15 patch (Story 3.2, Add Items to an Order, plus its code review):** Second `orders`-domain
slice. `api/orders.py` gained `GET /api/orders/tables/{table_id}` (resolves a Table to its
currently open Order, since nothing before this story could fetch an *existing* one, only the
transient POST-open response) and `GET`/`POST /api/orders/{order_id}/items`, mirroring
`MenuService`'s list+add shape. `OrderItem.price_at_add` (AD-7's first real application) landed via
the project's fourth Alembic revision, `819cce996301`; `Order.total_amount` still stays `None`
everywhere, FR-8's job. Two new exceptions (`OrderNotFoundError`, `DishNotAvailableError`);
`OrderService` gained `get_open_order_for_table`, `list_items`, `add_item`, `_get_order`.

Frontend: `waiter/TableOrderDetailPage.tsx` replaces its Story 1.4 placeholder, the sixth real
domain screen (7 IA surfaces remain). New shared `components/orders/OrderItemStatusBadge.tsx`
(UX-DR1), scoped to today's 3-member `OrderItemStatus`, built for Story 3.4/Kitchen Display to
reuse. `orderService.ts` gained `useOrderForTable`/`useOrderItems`/`useAddOrderItem`;
`menuService.ts` now exports `DISHES_QUERY_KEY` so the add-item mutation can invalidate it on a
409, a stale-dish rejection needing the same refresh a stale-table one already gets.

**The review's headline finding, caught independently by all three review layers**: `GET
/api/menu/dishes` was gated to admin+cook, so a Waiter, the only Role that can reach this page, got
a 403 on the dish picker, and the page's combined `isError` rendered nothing but an error message.
AC1/AC2/AC3 were unreachable in a running system while every test passed, because the frontend test
stubbed that endpoint 200 and `test_menu.py` had zero Waiter cases. This is the Role-reachability
rule Story 2.6 already established, one hop removed: checking the page's own new route is not
enough, every endpoint any of its queries call transitively needs the same check (now stated
explicitly above). Fixed with a new `DishCatalogReadDep` scoped to `list_dishes` only, a Waiter
never gets a Dish's recipe.

**Trap 22 added**: an Alembic column add with `nullable=False` and no `server_default` breaks
`downgrade`/`upgrade` the moment any row exists; fixed with a temporary default dropped in the same
revision, verified by hand against a live Postgres (downgrade, insert a row through the missing
column, re-upgrade, confirm success). Trap 16 extended: a numeric field's bound must also cover
arithmetic performed on it downstream, not just its own column, `OrderItem.quantity` was correctly
int4-bounded but unbounded against `price_at_add * quantity` overflowing `Order.total_amount`'s
`Numeric(10, 2)`; capped at 99 per line. "The shape every new domain screen should copy" gained two
more entries: `refetch()` bypasses a query's own `enabled` gate, and a 404 that is a legitimate
domain state (not a transport failure) needs the same `status`-based discrimination trap 13 already
uses for 401.

Also patched: the page heading rendered the Table's primary key labelled as a table number (tiles
show `table_number`, navigation uses `id`; now resolved through the already-cached `useTables()`);
and a frontend add-item test hardcoded the value it asserted and never read the request body, so it
could not have failed if the page posted the wrong dish or quantity (caught while writing up
findings, not by any review subagent). Two screens now disagree on the currency symbol
(`TableOrderDetailPage` renders `₪`, `cook/DishesPage` renders `$`), logged in `deferred-work.md`
rather than fixed silently on a screen this story's AC doesn't cover. Suites are now **247 backend
and 130 frontend tests**.

**2026-08-15 patch (Story 3.3, View Live Order and Table Status, plus its code review):** First
real producers on `RealtimeService` (Story 1.5 built the transport, nothing emitted over it until
now, confirmed by grep before starting). `OrderService.open_table` broadcasts `table.status_changed`
(`{table_id, status}`, a plain dict since the only consumer treats it as a refetch signal, not a
state transfer), `OrderService.add_item` broadcasts `order.item_added`
(`OrderItemResponse.model_validate(item).model_dump(mode="json")`, so the pushed shape can never
drift from the REST response shape), both to `UserRole.waiter` only, both only after their
`db.commit()` succeeds. First real frontend consumers: `TablesPage.tsx` subscribes to
`table.status_changed` and invalidates `TABLES_QUERY_KEY`; `TableOrderDetailPage.tsx` subscribes to
`order.item_added` and invalidates `orderItemsQueryKey(order.id)`. Both are page-wide subscriptions
(not filtered to "this page's own table/order" before invalidating), matching FR-6/NFR-5's "every
Waiter sees every Table and every Order" rule; `invalidateQueries` on a non-matching key is a
harmless no-op, not something to guard against.

**Trap 23 added**: a `providers.Factory` in `container.py` that injects another provider must be
declared after it, plain top-to-bottom class-body evaluation, not lazy name resolution. Discovered
when `order_service` needed `realtime_service` injected but was declared above it, raising
`NameError` at import time; fixed by reordering, not by any lazy-reference trick.

**Backend/frontend parity was an explicit requirement for this story** (not just an AC, a
session-level instruction): every emitted event needed a working, visibly-updating frontend
consumer, verified two ways, by automated tests and by manually driving two independent browser
sessions (two different Waiters) against a rebuilt Docker stack, confirming both live paths with
screenshots at each step, not just DOM assertions in a single-tab test.

Code review: 6 patches (named the Observer/Pub-Sub pattern per CLAUDE.md's requirement, since
neither the backend publisher nor the frontend subscribers named it initially; added a role-exclusion
assertion to both new backend tests, a connected Cook now asserted to receive nothing, closing a real
gap where a regression broadcasting to every Role would have passed CI; fixed a narrow but genuine
stale-query-key race in `TableOrderDetailPage.tsx`'s subscriber, which could invalidate
`orderItemsQueryKey(undefined)` if `order.item_added` arrived before the page's own Order lookup
resolved; guarded two brittle `FakeWebSocket.instances[0]` test reads; documented the container
ordering requirement and the `table.status_changed` payload's plain-dict shape). 5 findings dismissed
as false positives after verifying against the actual code: `OrderItemResponse` has zero relationship
fields so a raised lazy-load concern was unfounded, `ConnectionRegistry.broadcast_to_roles`/`_send`
already catch every failure mode they could raise so wrapping the call sites again would be
defensive code against an unreachable scenario, and `RealtimeService` being a `Factory` not
`Singleton` is harmless since it only wraps a shared `Resource`-backed registry, matching every
other service in this codebase. Suites are now **249 backend and 133 frontend tests**.

**2026-08-15 patch (Story 3.4, Edit or Cancel an Order Item, plus its code review):** Third
`orders`-domain endpoint pair. `OrderService.edit_item` (guarded UPDATE, `WHERE status = 'pending'`)
and `cancel_item` (guarded UPDATE, `WHERE status IN ('pending', 'in_preparation')`) are the 5th/6th
guarded-UPDATE applications in this codebase (AD-6/trap 18); a new private `_get_item` seam is the
first `_get_*` seam checking two ids (item id, and that it belongs to the given order). `cancelled`
added to `OrderItemStatus` via a hand-written Alembic migration (`ALTER TYPE ... ADD VALUE`,
autogenerate cannot produce this; `downgrade()` raises rather than fake a `DROP TYPE`), applied and
confirmed live against Postgres. `OrderItemCancelDep` (waiter, cook, admin) is the project's first
3-role `require_role()` grant; `require_role(*roles)` already supported any number of roles (trap
8), this was just the first call site to actually use three. Frontend: `TableOrderDetailPage.tsx`
gained an Actions column via a new per-row `OrderItemRow` subcomponent, owning its own
`useEditOrderItem`/`useCancelOrderItem` mutation instances (per-row, not shared — editing item A and
cancelling item B are independent actions, unlike `TablesPage.tsx`'s page-level-exclusive "open"
mutation). In-row confirm-reveal for the `in_preparation` cancel path (no modal, this codebase has
never introduced one), reusing `UsersPage.tsx`'s "Deactivate {name}?" precedent.

Backend/frontend parity was again an explicit session-level requirement; verified by inspecting
`frontend/src/pages/cook/KitchenDisplayPage.tsx` and every `admin/*` page directly (not just
trusting the story's own claim) to confirm no reachable Cook/Admin order-viewing surface exists yet
— the Cook/Admin cancel grant shipping backend-only is the same ahead-of-UI pattern
`InventoryWriteDep` set between Stories 2.1 and 2.6, not a gap.

Code review: three parallel agents (Blind Hunter, Edge Case Hunter, Acceptance Auditor)
independently converged on the same core defect — `notes: undefined` (dropped by `JSON.stringify`)
sent instead of an explicit `null` when a Waiter cleared a note, violating this project's "always
send both fields explicitly" rule. Also fixed: a dead-end where a row stuck mid-edit lost all action
buttons if its item's status changed away from `pending` under it (the Qty/Note `TextField`s were
gated on `isEditing` alone, not `isEditing && status === "pending"` like the action buttons were);
two visually-identical "Cancel" buttons (discard-edit vs. cancel-item) that could render
simultaneously with the same accessible name on a multi-pending-item order, the discard button
renamed to "Back"; and a stale error `Alert` that survived discarding the failed action that caused
it (mutations weren't `.reset()` on discard/back). Several findings verified as non-issues and
dismissed: the migration-safety concern (it was verified live, not just reasoned about, per the
story's own Debug Log), and two Change Log test-count inaccuracies (file totals mislabeled as
new-test counts, corrected). Deferred (test-coverage gaps, non-blocking, see `deferred-work.md`): no
regression test pinning that `edit_item`/`cancel_item` never broadcast; no positive AD-9 cross-Waiter
cancel test; three near-identical role-cancel tests not collapsed into one parametrized test;
`UpdateOrderItemRequest.notes` doesn't normalize an explicit `""` to `None` server-side. Suites are
now **270 backend and 142 frontend tests**.

**2026-08-15 patch (Story 4.1, Record Manual Stock Movements, plus its code review and manual
testing pass):** Epic 4 opens. First write to `Ingredient.current_stock` since Story 2.1 created
the column. `backend/data_models/inventory.py` gained its first Pydantic schemas
(`CreateStockMovementRequest`, whose `model_validator` rejects `consumption` as a manual input and
enforces AD-16's sign convention; `StockMovementResponse`), previously ORM-only.
`InventoryService` gained `get_ingredient`, `list_movements`, `record_movement`, plus two private
seams: `_get_ingredient` (plain read, no lock) and `_lock_ingredient` (`SELECT ... FOR UPDATE`,
`record_movement` only) — a code-review-driven fix. The first implementation pass did a plain
`db.get()` read-modify-write on `current_stock` with no lock, a genuine lost-update race (two
concurrent movements on the same Ingredient could silently overwrite each other's effect on
`current_stock`, even though both `StockMovement` audit rows would still insert correctly).
`_lock_ingredient` is the **third instance** of trap 9's "lock the one row every caller contends
on" shape, after `MenuService._lock_dish` (AD-8) and `UserService`'s AD-15 last-admin guard, and the
current-state tree's mention of `_lock_dish` now cross-references it. `api/inventory.py` gained
`GET /ingredients/{id}`, `GET /ingredients/{id}/movements`, `POST /ingredients/{id}/movements`, all
reusing `InventoryReadDep`/`InventoryWriteDep` unchanged, no new Role scoping needed. No Alembic
migration: `StockMovement`/`MovementType` already existed in the Story 1.0 baseline. 26 new backend
tests.

Frontend: `IngredientDetailPage.tsx` replaces its Story 1.4 placeholder, the seventh real domain
screen (6 IA surfaces remain placeholders) — stat cards, a log-movement form (Purchase/Waste/
Adjustment only, Consumption never offered), and a movement history table using the new
`components/inventory/MovementTypeChip.tsx` (first file in that folder, a neutral-palette Chip
deliberately not reusing `OrderItemStatusBadge`'s traffic-light trio, AC3/UX-DR14). `inventoryService.ts`
gained `useIngredient`/`useStockMovements`/`useRecordStockMovement`; the last invalidates the
single-ingredient key, the movements key, and `INGREDIENTS_QUERY_KEY` together on settle.

Code review (3 patches, both named above; the rest were deferred test-coverage gaps, see
`deferred-work.md`): the `_lock_ingredient` race; a duplicated "fetch ingredient or 404" check
across three service methods, consolidated into `_get_ingredient`; a missing secondary sort key on
movement-history ordering (`.order_by(timestamp.desc(), id.desc())`, ties by DB-clock timestamp
otherwise sort undefined).

**Two bugs found only by manually testing the live Docker stack, after the automated review had
already closed the story, neither caught by any of the three review layers or the test suite:**
**Trap 24 added** — `IngredientsPage.tsx` had no click-through to the destination page this story
just built; its Story 2.6 docstring had deferred that link to Story 4.3 on a reason (needs
comparison logic) that was wrong for plain navigation from the start, and nobody re-examined it
when the destination page actually shipped. Fixed with `useNavigate()` on the row, mirroring
`TablesPage.tsx`'s tile-click precedent. **Trap 25 added** — the movement-history quantity
`Typography` used `color="error.main"`/`"success.main"`, a dot-path that `sx` resolves but the bare
`color` prop silently ignores, so the text rendered with no color at all; fixed with the bare tokens
`"error"`/`"success"`. Neither bug is the kind an automated diff review or this codebase's own test
conventions (no test anywhere asserts a MUI color prop) can catch; both are recorded as durable
lessons about the limits of what "green tests, clean review" actually proves. Domain rules gained a
note on the sign convention and the deliberate "Recorded by" no-join gap (also logged in
`deferred-work.md`). AD-16 marked with its first real application. Suites are now **296 backend and
153 frontend tests**.

**2026-08-16 patch (Story 4.2, Low-Stock Alert, plus its code review):** Low-Stock Alert built as a
**derived state, not a stored entity** (PRD glossary), which collapsed most of FR-14's own
acceptance criteria to "satisfied by construction" rather than new state-machine code: one
`Ingredient` row per ingredient means there is structurally nothing for "at most one active alert"
to duplicate, and Story 4.1's pre-existing `_lock_ingredient` (`SELECT ... FOR UPDATE`) already
serializes any two concurrent movements on the same row, so "exactly one alert results" needed no
new locking either. `InventoryService.list_alerts` is a plain `SELECT ... WHERE current_stock <
min_stock_threshold` (strict `<`), exposed at `GET /api/inventory/alerts`, reusing
`IngredientResponse` — no new Pydantic schema, no new ORM entity, no Alembic migration.

`InventoryService` became `RealtimeService`'s **second producer** (after `OrderService`, Story
3.3): `record_movement` now captures `was_low` from the Ingredient row `_lock_ingredient` already
holds (free, no extra query), computes `is_low` after commit, and broadcasts
`inventory.alerts_changed` to `warehouse_manager` only when that boolean actually flips —
crossing-triggered, not fired on every stock-decreasing movement, matching FR-14's own literal
"crosses... below threshold" wording. **Trap 23 hit a second time**, exactly as the story's own
Scope note predicted in advance: `inventory_service`'s `container.py` provider had to move below
`realtime_service`'s once it needed that dependency injected, same fix shape as Story 3.3's
original discovery.

Frontend: `AlertsPage.tsx` replaces its Story 4.1-era placeholder (the eighth real domain screen, 5
IA surfaces remain placeholders) — loading/error/empty("No active shortages")/loaded states, one
row per shortage reading `"Stock low: {name} ({current_stock}{unit} left)"` (UX-DR10), no dismiss
control, click-through to that Ingredient's detail page. `AppShell.tsx` gained a persistent MUI
`Badge` on the "Alerts" `NavItem` (warehouse_manager only, matched by a direct path comparison
rather than a new generic badge-lookup abstraction), hidden entirely at zero rather than showing a
visible "0" (UX-DR5's "no toast" framing). Both `AppShell.tsx` and `AlertsPage.tsx` independently
subscribe to `inventory.alerts_changed`, each invalidating the newly-exported
`ALERTS_QUERY_KEY` on receipt — two independent subscriptions to one event, matching
`TablesPage.tsx`/`TableOrderDetailPage.tsx`'s existing precedent for overlapping event relevance,
not a shared subscription object. `useAlerts(enabled)` takes a boolean so `AppShell.tsx` (rendered
for every Role) can gate the query to `warehouse_manager` only — hooks cannot themselves be called
conditionally, so the query's own `enabled` flag does the gating instead. 14 new backend tests, 9
new frontend tests.

Code review (three parallel agents): fixed one real gap — a missing symmetric negative-broadcast
test (the suite covered "already-in-shortage, another decreasing movement, no re-broadcast" but not
the mirror "already-in-shortage, a purchase that reduces without clearing, no re-broadcast") — plus
one docstring precision tightening. Several findings verified as false positives after direct
checking rather than trusted from prose: the "badge hidden at zero" frontend test was confirmed via
an ad hoc render to test genuine DOM absence, not an MUI implementation-detail artifact; the
broadcast payload's `ingredient_id` field name was checked against `table.status_changed`'s own
`table_id` precedent (the correct comparison) rather than `order.item_added`'s unrelated
full-state-transfer shape; and AC2/AC3's "satisfied by construction" claim was independently
re-verified by reading the schema and lock code directly. Test-count claims in the story file were
independently re-run and matched exactly — no repeat of a prior story's count-inaccuracy mistake.
Four items deferred as non-blocking (see `deferred-work.md`): `FakeWebSocket` duplicated a fourth
time, past Story 3.3's own "extract at four" threshold; no visible fallback on the Alerts nav badge
if its own query fails; no index backing the shortage comparison (accepted at this project's
current scale, same call made for other O(n) reads elsewhere); no test proving the two independent
`inventory.alerts_changed` subscribers de-dupe into one network request. Suites are now **311
backend and 162 frontend tests**.

**2026-08-16 patch (Story 4.3, View Ingredient Stock Levels, plus its code review):** Closes Epic 4.
The first story in the epic with **zero backend changes** — both capabilities it needed
(`current_stock`/`min_stock_threshold`, already returned by `GET /api/inventory/ingredients` since
Story 2.3; the derived shortage list, already computed by `GET /api/inventory/alerts` since Story
4.2) already existed. `IngredientsPage.tsx` now calls `useAlerts()` alongside `useIngredients()`,
sorts in-shortage rows to the top (alphabetical within each group, per `DESIGN.md`'s literal
"pinned to top, then alphabetical"), and renders `WarningAmberIcon` plus `error.main`-colored text
on those rows — reusing the exact `"error"` MUI key `OrderItemStatusBadge.tsx`'s `cancelled` entry
already uses, no new hex value anywhere. Live re-highlighting for `warehouse_manager` sessions costs
zero new subscription code: `AppShell.tsx`'s existing global `inventory.alerts_changed` subscription
(Story 4.2) already keeps the shared `ALERTS_QUERY_KEY` fresh for every mounted `useAlerts()`
consumer via TanStack Query's keyed cache.

Two of the story's four ACs (empty-state copy, movement-history empty state) turned out to already
be fully implemented by Stories 2.6 and 4.1 respectively, each already covered by an existing test
asserting the exact required copy — verified directly rather than trusted from the story's own
claim, confirmed true, zero new code needed for either.

Code review (three parallel agents): fixed a real gap — `useCreateIngredient` only invalidated
`INGREDIENTS_QUERY_KEY`, not `ALERTS_QUERY_KEY`, so a newly-created Ingredient already below its own
threshold showed no shortage styling until an unrelated event happened to refresh the alerts cache
(creating an Ingredient never goes through `record_movement`, so Story 4.2's crossing-triggered
broadcast never fires for it). Also added missing icon-presence and non-shortage-group sort-order
test coverage, and corrected a garbled `baseline_commit` hash in the story file's own frontmatter.
One finding verified as a non-issue: the shortage icon has no `aria-label`, initially flagged as an
accessibility gap, but `DESIGN.md`'s own `ingredient-row.in-shortage` token specifies color-plus-icon
only (unlike `status-badge`'s explicit "plus spelled-out label" requirement) — the implementation
matches its actual design spec. One item deferred as non-blocking, out of this story's stated scope
(see `deferred-work.md`): Admin (who can also reach this screen) gets correct shortage data on
initial load but no live re-highlighting while parked on the page, since the backend only ever
broadcasts `inventory.alerts_changed` to `warehouse_manager` — no AC anywhere asks for Admin live
updates. Suites are now **311 backend and 167 frontend tests**.

**2026-08-16 patch (Story 5.1, View Incoming Orders in Real Time — Kitchen Display, plus its code
review):** Epic 5 opens, read-only. New `kitchen` domain end to end: `KitchenItemResponse`
(`data_models/order.py`), `KitchenService.list_active_items` — **the first genuine join in
`backend/services/`** (every prior story returned raw ids and resolved names client-side instead;
this one joins `OrderItem` to `Order` to resolve `table_id`, since `OrderItem` has no `table_id` of
its own and the Kitchen Display's whole point is grouping by Table). `GET /api/kitchen/items`
(`api/kitchen.py`, `KitchenReadDep` = cook + admin), wired into `container.py`, `api/router.py`,
and `main.py`'s `container.wire(modules=[...])` list (AC5's own explicit requirement, `"api.kitchen"`
appended at the physical end of the list, not just inserted anywhere in it, after a code-review
finding that the first pass inserted it mid-list).

Widened two existing grants rather than duplicating them: `OrderService.add_item`'s
`order.item_added` broadcast now targets `[UserRole.waiter, UserRole.cook]` (was waiter-only);
`TablesReadDep` now permits `admin, waiter, cook` (was admin/waiter-only), so the Kitchen Display
can resolve `table_number` client-side the same way `TableOrderDetailPage.tsx` already does.
**Widening `TablesReadDep` broke two separate pre-existing tests, both literally named
`test_cook_cannot_list_tables`** (one in `test_tables.py`, one in `test_orders.py`) — the first was
caught on a task-scoped test run, the second only surfaced on the full-suite rerun. Both flipped to
`test_cook_can_list_tables` (asserting 200), with a new `test_cook_cannot_create_a_table` added
alongside the fix to keep write-access-stays-admin-only coverage from silently disappearing. A
repo-wide grep after the fact confirmed zero remaining instances of the old name/assertion.

Frontend: `KitchenDisplayPage.tsx` replaces its Epic-1 placeholder — one Card per Table, combining
loading/error across **three** independent queries for the first time in this codebase (kitchen
items, tables, dishes; prior multi-query pages combined two). Dark-theme-on-Cook-login (UX-DR7) and
the "Reconnecting..." banner (UX-DR16) needed zero new code, both already built ahead of this story
(confirmed by direct read, not assumed).

Code review (three parallel agents): fixed a real gap — the live `order.item_added` handler only
invalidated the kitchen-items cache, so a Table or Dish created after the page's initial load would
never resolve while the (deliberately long-lived, always-foregrounded) page stayed mounted, and the
unresolved-`table_id` fallback echoed the raw internal id with no visual distinction from a genuine
`table_number` — violating this codebase's own "never show a raw id" convention. Fixed: the handler
now also invalidates `TABLES_QUERY_KEY`/`DISHES_QUERY_KEY` (harmless over-invalidation the rest of
the time), and the fallbacks now render `"?"`/`"Unknown dish"` instead of the raw id. Also fixed:
`kitchen_service`'s container placement (moved next to `order_service`, matching the story's own
stated intent) and the mid-list-vs-appended wiring nitpick above. Verified as safe, not just
assumed: the widened broadcast's payload is identical for every recipient regardless of Role, and
this codebase's Role-level-only permission model means there's no per-order Cook scoping that could
have been skipped. Deferred (see `deferred-work.md`): `list_active_items` has no pagination/bound;
`KitchenItemResponse` carries `price_at_add`/`order_id` the frontend never renders; no automated
tripwire forces revisiting the already-documented `Order.status` filter gap once Stories 5.3/5.4
ship (today's filter is `OrderItem.status != cancelled` only — correct today since nothing can move
an Order to `served`/`closed` yet, but a served Order's `ready` items would otherwise leak onto this
board forever once that changes). Suites are now **321 backend and 173 frontend tests**.

**2026-08-16 patch (Story 5.2, Pick Up and Progress an Order Item with Atomic Stock Deduction, plus
its code review):** the Kitchen Display's cards become clickable — `OrderService` gains
`pick_up_item` (`pending` → `in_preparation`, guarded UPDATE per trap 18, records the acting Cook)
and `mark_item_ready` (`in_preparation` → `ready`, pure status change, no `cook_id` reassignment —
attribution is audit-only, any active Cook may finish another's item). Both live in `OrderService`,
not `KitchenService`: `KitchenService` was deliberately left config-free/read-only by Story 5.1, and
every other `OrderItem` transition already lives in `OrderService`.

Stock deduction reuses, rather than duplicates, Story 4.x's row-lock/threshold-crossing machinery:
`InventoryService` gained `apply_consumption(db, ingredient_id, quantity, actor_id, order_id) ->
bool`, the same `_lock_ingredient` row lock and `was_low`/`is_low` crossing check `record_movement`
already used, but deliberately **does not commit or broadcast itself** — `pick_up_item` composes it
inside its own single transaction (the `OrderItem` status UPDATE, every `Ingredient` decrement, and
every `StockMovement` insert all land in one `db.commit()`, AD-6/NFR-3's literal requirement), then
broadcasts `inventory.alerts_changed` only after that commit succeeds, once per Ingredient that
actually crossed threshold. `CreateStockMovementRequest`'s existing rejection of a manually-submitted
`consumption` type (Story 4.1) is what forced this to be a new method rather than a call to
`record_movement`.

**Trap 23 hit a third time, applied to `order_service` itself for the first time**: `OrderService`
gaining `inventory_service` as a new constructor dependency required flipping `order_service`'s and
`inventory_service`'s declaration order in `container.py` — previously neither depended on the
other, so their order didn't matter; now it does, and the file's own long-standing ordering comment
was updated to say so explicitly rather than only covering `realtime_service`.

New event `order.item_status_changed` (past-tense, `{domain}.{event}`, the literal example name
Story 1.5's own architecture spec used) broadcasts to `[waiter, cook]`, the same recipients
`order.item_added` already uses — both `KitchenDisplayPage.tsx` (new "Pick up"/"Mark ready" buttons,
UX-DR19's single-large-click-target) and `TableOrderDetailPage.tsx` (badge-only, no new buttons —
pick-up/mark-ready stay Cook-only) subscribe to it.

**A genuine correctness bug found only by the code review's Blind Hunter layer, not by any test in
the suite**: `pick_up_item` originally computed each Recipe Ingredient's deduction using
`item.quantity` read *before* its own guarded UPDATE ran, so a concurrent `edit_item` call (also
legally guarded on `status == pending`) changing the item's quantity in that narrow window would
commit successfully while the deduction silently used the stale, pre-edit quantity — a real
inventory-accuracy bug, not just a benign race. Fixed by adding `await db.refresh(item)`
immediately after the guarded UPDATE succeeds and before the deduction loop: at that point the
item's status is already `in_preparation`, so no further `edit_item` can land (its own guard
requires `pending`), making that refresh the last point a quantity change could still be pending.
Generalizes into a new rule worth restating: **a value read before a guarded UPDATE must be
re-read after that UPDATE succeeds, not reused from before it, if downstream logic depends on its
current value** — the guard closes the race for the *status* column, but says nothing about any
other column the pre-UPDATE read touched.

Also fixed in the same review pass: an explicit `db.rollback()` added on `apply_consumption`'s
`IngredientNotFoundError` mid-loop (matching trap 20's convention, previously relied on implicit
session-close rollback instead, the only branch in this file that did); two frontend bugs in
`KitchenDisplayPage.tsx` — a stale inline error never cleared by a live status-change event from a
different session, and a shared page-level `useMutation()`'s `.variables` field only ever
reflecting the *most recent* call, which could let two rapid clicks on different rows leave an
earlier row's button incorrectly re-enabled mid-flight (fixed by tracking an explicit `Set` of
in-flight item ids instead); and two test gaps against the story's own Task 7 text (a missing
"already low, stays low" non-crossing alert case, and a missing different-order 404 case for
mark-ready). Deferred as pre-existing, not introduced by this story (see `deferred-work.md`):
`Order.status` still never derives from its items' statuses (explicitly Story 5.3's own scope), and
a Dish can reach zero `RecipeIngredient` rows while a still-`pending` Order Item references it
(`CannotRemoveLastRecipeIngredientError`'s guard only fires while the Dish `is_available`). Suites
are now **341 backend and 178 frontend tests**.

**2026-08-16 patch (Story 5.3, Order Status Derives From Its Items, plus its code review):**
`Order.status` is now genuinely live — resolves the gap Stories 5.1/5.2's own reviews flagged and
explicitly deferred to this story. FR-12's rule is exactly three buckets (zero non-cancelled
Items → `pending`; every non-cancelled Item `ready` → `ready`; anything else → `in_preparation`),
implemented as a new private `OrderService._recompute_order_status`, called from all four methods
that can change an Order's non-cancelled item set (`add_item`, `cancel_item`, `pick_up_item`,
`mark_item_ready`) — deliberately **not** `edit_item`, which only touches quantity/notes, never
status.

**A new, generalizable distinction from AD-6's guarded-UPDATE idiom:** this recompute is a pure
overwrite-with-current-truth, not a state-machine transition — there is no expected prior value
to guard against, so no `UPDATE ... WHERE status = <expected>` was written for it (AD-5's
last-write-wins already covers Order edits generally). Writing a guarded UPDATE here would be
answering a question ("was the prior status still X?") FR-12 never asks. A `served`/`closed`
Order is left untouched by the recompute (a one-`if` forward-looking guard for Story 5.4, since
`served`/`closed` are set explicitly, never derived) — unreachable today since nothing can produce
one yet, but now has a dedicated test forcing the state directly, so the guard isn't shipping
blind.

**A genuine concurrency bug, caught only by the code review's adversarial layer** (see trap 27,
added this story): the recompute's own read of sibling `OrderItem` statuses had no row lock, so
two concurrent transactions each finishing a different Item of the same Order could each converge
on "no change" from their own stale view and leave the aggregate stuck wrong after both committed
— reproduced with a real two-connection concurrency test, not a monkeypatch, and fixed by locking
the Order row before reading its children.

New broadcast `order.status_changed`, waiter-only (unlike `order.item_status_changed`'s
`[waiter, cook]` — Cook's Kitchen Display has no use for Order-level status), fired only when the
aggregate actually changes, not on every item mutation. New bulk read `GET /api/orders`
(`OrderService.list_open_orders`, reusing the existing Waiter-only `OrdersDep` unchanged) — the
first bulk Order read in the project, existing for exactly one reason: the Tables grid needs to
know, across every occupied Table at once, whether its Order is `ready`, to render the
attention-state tile treatment (UX-DR3). Resolved client-side into a `table_id -> status` lookup,
matching the established "client-side resolution, never a second server-side filter" precedent,
rather than an N+1 per-tile request.

**A second review-caught bug, this time frontend:** `TablesPage.tsx`'s Retry button only refetched
`useTables()`, not the new `useOpenOrders()`, even though `isError` was already the OR of both —
a failure isolated to the open-orders query left the grid permanently stuck behind the error
banner with no in-app recovery. Fixed by refetching both queries together, matching this
codebase's own "Retry must refetch all of them, not just one" rule (already stated earlier in
this file) more literally than the first implementation pass did. Combining two queries' error
state also broke TypeScript's discriminated-union narrowing on TanStack Query's nullable `error`
field (a `Error | null` no longer type-checked against a strictly-`Error`-typed helper once
`isError` became a synthesized OR of two independent flags) — caught by `npx tsc -b`, not
anticipated in the story, fixed by widening the file-local `errorMessage()` helper to accept
`Error | null` and building an explicit `firstError = tablesError ?? openOrdersError`.

Deferred, not fixed (see `deferred-work.md`): `GET /api/orders` has no pagination, the same
unbounded-growth shape already deferred for `KitchenService.list_active_items`; and that Kitchen
Display filter gap itself is still open too, since this story deliberately left
`api/kitchen.py`/`kitchen_service.py` untouched (nothing can reach `served`/`closed` until Story
5.4 exists). Suites are now **352 backend and 184 frontend tests**.

**2026-08-21 patch (Story 5.4, Mark an Order Served and Close the Table, plus its code review and
manual-testing fixes):** `Order.status` can finally reach `served` and `closed` — the two values
Story 3.1 created and Story 5.3's `_recompute_order_status` explicitly no-op'd on, unreachable
until now. Two new guarded UPDATEs on `OrderService` (`mark_served`, `close_order`), a real
contrast with Story 5.3's own recompute: these are genuine state-machine transitions with an
expected prior status to check (AD-6), not a pure overwrite-with-current-truth (AD-5). `mark_served`
guards on `status IN (ready, pending)` — FR-12 already guarantees `pending` means zero
non-cancelled items, so no separate item count is needed server-side. `close_order` guards on
`status == served`, computes `total_amount` (`Decimal` sum of `price_at_add × quantity` over
non-cancelled items, AD-7) and frees the owning Table, all three writes in one transaction. No row
lock was needed for the total's aggregate read (contrast trap 27): every non-cancelled item is
already `ready` by the time an Order reaches `served`, and nothing can change any item's status
once it is, so the set is frozen by construction.

**Required, not optional: fixed the Kitchen Display's served/closed leak**, a gap Story 5.3's own
`list_active_items` docstring had explicitly deferred here — a served Order's items would
otherwise linger on the Kitchen Display forever. This story is what first makes `served`/`closed`
reachable, so leaving that filter unfixed would have left the system broken end-to-end, not merely
incomplete against its own literal ACs.

**Two review-caught issues, both fixed:** `close_order` broadcast `table.status_changed` as
"available" even on the (currently unreachable) branch where the Table's own guarded UPDATE
failed — fixed to broadcast only when that write actually succeeded. And unlike Story 5.3's own
concurrent-mark-ready test validating a similar "no lock needed" argument empirically, this
story initially shipped with no concurrent-close test — added one (two independent `AsyncClient`s,
`asyncio.gather`), confirming the guarded Order-status UPDATE alone correctly serializes two
simultaneous `/close` calls with no row lock required.

**Frontend: the first Waiter-facing "tables need attention" nav badge** (`AppShell.tsx`), reusing
Story 5.3's `useOpenOrders()` (now gated by a new `enabled` param so a non-waiter Role never fires
the request) filtered to a live ready-Order count, green (`success`) unlike the Alerts badge's red
— DESIGN.md's own explicit two-token distinction. `TableOrderDetailPage.tsx` gained an
always-visible Order total bar (client-computed pre-close, the server's own stored value once
`closed`) with Mark served/Close buttons, both applying with no confirm step (AC6, UX-DR12
contrast).

**A two-round manual-testing bug, not caught by any automated test:** closing an Order left the
Waiter on that Order's own now-nonexistent page, showing the "no open order" banner layered over
the stale, just-closed Order's own content simultaneously — and even after gating those two states
to be mutually exclusive, the banner could still flash for one frame before a since-added
`navigate("/waiter/tables")` call won its race against the mutation's own query invalidation (see
trap 28, added this story). Fixed in two passes: first, mutual exclusion plus the navigation
itself; then, dropping the invalidation of the closed Order's own query key entirely, since a
caller that navigates away on success has nothing left on that page to refresh anyway. Suites are
now **365 backend and 196 frontend tests**.

**2026-08-21 patch (Story 5.5, Live-Update the Kitchen Display and Waiter Screen on Cancel/Edit,
plus its code review):** Closes a gap against already-approved NFR-1, surfaced by a Sprint Change
Proposal (2026-08-16) after manual testing of Story 5.2 found that cancelling an Order Item never
updated an already-open Kitchen Display. Root cause: `edit_item`/`cancel_item` (Story 3.4) never
called `realtime_service.broadcast(...)` — correct at the time (no live consumer existed for
either yet), stale once Story 5.1/5.2 made the Kitchen Display a live, always-foregrounded second
consumer. **The smallest-blast-radius story so far**: two `broadcast()` calls added to two
already-existing, already-guarded methods, reusing `order.item_status_changed` verbatim (same
event name, payload shape via `OrderItemResponse.model_validate(item).model_dump(mode="json")`,
same `[UserRole.waiter, UserRole.cook]` recipients Story 5.2 already established for
`pick_up_item`/`mark_item_ready`) — no new event, no new endpoint, no schema change, no migration,
**and no frontend code changes at all**, confirmed by reading both consumers
(`KitchenDisplayPage.tsx`, `TableOrderDetailPage.tsx`) before writing the story: both already
subscribe to `order.item_status_changed` generically and just invalidate-and-refetch, regardless
of which backend transition triggered it.

`edit_item`'s broadcast is unconditional (edit never changes `.status`, so there is no
`order_status_changed` branch to gate it around, unlike the other three item-mutating methods).
`cancel_item`'s broadcast is also unconditional, placed after `db.refresh(item)` and before the
existing `order_status_changed` conditional — item-level event first, order-level conditional
follow-up second, matching every other method's established ordering.

**One existing test had to be rewritten, not just extended** — `test_websocket.py::
test_cancelling_one_of_several_pending_items_broadcasts_nothing` (added by Story 5.3) asserted a
connected Waiter receives nothing after a cancel that leaves the Order's aggregate unchanged. Once
`cancel_item` broadcasts unconditionally, that top-level claim became false: the Waiter now
correctly receives `order.item_status_changed` (a real event) but still correctly does not receive
`order.status_changed` (the aggregate genuinely didn't change) — renamed to
`..._broadcasts_no_order_status_changed` and rewritten to assert receive-then-timeout instead of
timeout-immediately, preserving its original no-op-recompute coverage. This is exactly the
rewrite `deferred-work.md`'s own story-3-4 entry anticipated, in spirit if not by name (that test
didn't exist yet when the entry was written).

**Code review, all cheap test-coverage strengthening, no production-code changes needed beyond
the original two broadcast calls**: the two new broadcast-content tests were missing the
`warehouse_manager`-negative-recipient check their own claimed template has (added); the cancel
test's `order.status_changed` follow-up only checked the event name, not payload content (added
`id`/`status` assertions); the edit test only checked the Waiter's channel goes idle afterward, not
Cook's or a warehouse_manager's (added both); and nothing pinned that the existing status guards
still run *before* the new broadcast calls, so two new negative tests
(`test_rejected_edit_broadcasts_nothing`/`test_rejected_cancel_broadcasts_nothing`) assert a
rejected edit/cancel broadcasts nothing at all. Deferred, not fixed: both new broadcast calls run
post-commit with no try/except (matches every other broadcasting method in this file — fixing it
here alone would be inconsistent, fixing it project-wide is a separate change); `edit_item`
broadcasts even on a genuine no-op edit (harmless, a wasted refetch, not incorrect data). Suites
are now **369 backend and 196 frontend tests**.

**2026-08-22 patch (Story 6.1, Generate a Recipe Suggestion from Current Stock, plus its code
review and a manual-testing timeout fix):** Epic 6's opening story, and the project's **first
external-API integration**. `backend/clients/llm.py`'s `LLMClient` is the only place `openai` is
imported anywhere in `backend/` (AD-12) — one method, `generate_recipe(prompt) -> dict`, using
Chat Completions' JSON mode, a 45s timeout, and deferred SDK-client construction so a
never-configured API key fails inside the call (caught and converted to a 502) rather than
raising raw at container-Singleton construction time. `AIService.generate_suggestion` reads
Ingredient stock directly (no `InventoryService` dependency needed for a plain read, `current_
stock > 0` only), sorts it by a `_waste_risk_rank` heuristic (surplus relative to each
Ingredient's own minimum threshold, since nothing in this schema tracks expiry/usage-rate), and
validates the parsed OpenAI response's shape before persisting.

**A real concurrency bug caught and fixed during implementation, not after:** `AIService`/
`LLMClient` are registered as `providers.Singleton` in `container.py`, the **one deliberate
exception** to this container's otherwise-universal Factory pattern. AD-14's "reject a second
concurrent generation for the same Cook" guard lives in an in-process `set` on the service
instance itself; a `Factory` would hand each injected request its own empty set, silently
defeating the guard the moment two different requests happened to land on two different
instances — caught while implementing, before it ever shipped, and verified with a genuine
concurrency test (a controlled `asyncio.Event`, not a timing sleep).

**Code review found and fixed six further robustness gaps**, all before merge: a scale-mixing bug
in the stock-sort for zero-threshold Ingredients; no response-shape validation (a malformed OpenAI
reply would have been persisted as a "successful" suggestion); out-of-stock Ingredients still
included in the snapshot (AC1 says "currently-available"); no rejection when nothing is in stock
at all; a genuinely timing-dependent `asyncio.sleep` in the one existing concurrency test
(replaced with a deterministic event); and a never-configured API key raising raw instead of a
graceful 502. Adding a new per-Cook-scoping concurrency test also caught a real deadlock in the
test double itself (two concurrent calls sharing one blocking mock, with nothing to unblock the
second until the first — already-awaited — call returned).

**Manual testing (against a real, live OpenAI call) found one more real bug**, after everything
else was already verified: `httpClient.ts`'s global 5s fetch timeout is far shorter than a
genuine generation call (observed ~9s, up to `LLMClient`'s own 45s server-side budget), producing
a false "The server took too long to respond" even though the request had already succeeded and
persisted. Fixed by adding an optional per-call `timeoutMs` override to `apiRequest` (`services/
smartChefService.ts`'s `useGenerateSuggestion` is the first and only call site to use it, 50s;
every other call site keeps the 5s default) — while writing the test for this fix, caught a
second bug in the test's own mock `fetch`, which didn't respect the abort signal and hung for
real rather than simulating a timeout.

Deferred, not fixed (see `deferred-work.md`): the Singleton-based in-flight guard assumes
single-process deployment forever — if this app is ever scaled to multiple worker processes, each
would get its own empty `_in_flight` set. `list_suggestions` has no pagination, matching the
already-accepted unbounded-growth pattern `GET /api/orders`/`KitchenService.list_active_items`
already established. Suites are now **383 backend and 202 frontend tests**.

Last Updated: 2026-08-22
