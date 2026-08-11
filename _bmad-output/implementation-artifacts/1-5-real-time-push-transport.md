---
baseline_commit: 7de497542b94669bf6b9ad858bee46bc54148ea8
epic: 1
story: 5
---

# Story 1.5: Real-Time Push Transport

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the system,
I want one authenticated WebSocket channel with a fixed event-naming convention,
so that every later feature pushes state changes the same way instead of each inventing its own.

**Scope note.** Like Story 1.0, this is enabling infrastructure with no directly visible feature.
It is split out from its first real consumer (Story 3.3) because Stories 3.3, 4.2, 5.1 and 5.2 all
emit over this channel and the naming convention has to exist before any of them are written
against it. This story:

- adds the transport (backend WS endpoint, connection registry, a `broadcast` seam every later
  service will call) and
- **discharges the exact obligation Story 1.4's review deferred here**: "wire the live WebSocket
  to drive `status`, and implement AC7's 'automatic retry'"
  (`_bmad-output/implementation-artifacts/deferred-work.md`, "AC7's connection producer and
  automatic retry ship with Story 1.5").

It does **not** add any real domain event. `order.item_status_changed` and friends belong to the
stories that own those mutations (3.3, 4.2, 5.1, 5.2). This story's own NFR-1 smoke test uses one
synthetic, throwaway event name to prove the pipe works end to end; do not invent or half-build a
real domain event to test with.

Two mechanics the architecture spine explicitly leaves to this story to decide, because it says so
in as many words ("left to implementation" / "left to implementation"):

1. **WebSocket auth-token transport.** Decision: **cookie-on-upgrade.** The browser's native
   `WebSocket` constructor sends cookies for the target origin automatically on the handshake
   request, exactly like a normal `fetch`, with no JS-level opt-in needed (unlike `fetch`, which
   needed `credentials: "include"`, per `httpClient.ts`). This reuses the exact same httpOnly
   session cookie AD-3 already established, adds no token-in-URL/logs exposure a query-param
   token would create, and needs no new frontend code to attach it. The backend reads it via
   `websocket.cookies.get(COOKIE_NAME)`, the WebSocket-route equivalent of
   `request.cookies.get(...)` in `get_current_user`.
2. **`CORSMiddleware` does not apply to WebSocket connections.** This is an ASGI fact, not a
   project choice: Starlette's CORS middleware only inspects `http` scope, and a WebSocket
   handshake is a `websocket` scope. AD-3's "explicit allow-list, never wildcard" is a real
   security requirement that would otherwise silently not apply to this transport. Task 2 checks
   the handshake's `Origin` header against `config.cors.allow_origin` by hand.

## Acceptance Criteria

**AC1 — Single endpoint, one connection per session, Role-scoped**
Given no WebSocket endpoint exists in the codebase, when this story is built, then a single
WebSocket endpoint is added, one connection per authenticated session, scoped to the connecting
User's Role (AD-2).

**AC2 — Gated by the same JWT**
Given a connection attempt, when it is opened, then it is gated by the same JWT verified for REST
routes, through the same shared verification logic, and rejected if absent or expired (AD-3,
NFR-2).

**AC3 — No new dependency**
Given the `websockets` package is already present transitively via `uvicorn[standard]`, when the
transport is implemented, then no new backend dependency is added for it. (Verified:
`uv run python -c "import websockets; print(websockets.__version__)"` succeeds today, on
`main`, with zero `pyproject.toml` changes.)

**AC4 — Fixed `{domain}.{event}` emission seam**
Given any state change that other Roles must see, when the owning service layer commits it, then
it emits exactly once, from the service that owns the mutation, under the past-tense
`{domain}.{event}` naming convention (e.g. `order.item_status_changed`) (AD-2). This story builds
the seam (a `broadcast` method every future service calls); it does not call it from any real
domain service, since none exist yet in Epic 1.

**AC5 — Delivery within 2 seconds, smoke-tested**
Given a client is connected and an event is emitted, when the emission commits, then the connected
client receives it within 2 seconds, verified by a smoke test that emits one event and asserts
receipt (NFR-1).

**AC6 — Drives Story 1.4's Reconnecting state, with automatic retry**
Given the connection drops, when the client detects it, then it drives Story 1.4's shared
"Reconnecting..." state and retries automatically, with no local-first write queue (UX-DR16). This
is the exact deferred obligation from Story 1.4's review (see Scope note).

## Tasks / Subtasks

- [x] **Task 1: `ConnectionRegistry` (backend, `clients/`)** (AC: 1, 5)
  - [x] New file `backend/clients/websocket.py`. Tracks open connections by Role so a broadcast can
    target a subset, matching `clients/database.py`'s existing shape (a plain class/dataclass, no
    business logic, the "network/driver" layer per `CLAUDE.md`). AD-1 names this exact component
    ("WebSocket connection registry") as one of its three examples of a lifecycle-managed
    `providers.Resource`, alongside the DB engine — follow that literally, do not make it a bare
    `providers.Singleton` even though nothing here strictly needs async init:
    ```python
    from collections import defaultdict

    from fastapi import WebSocket

    from data_models import UserRole


    class ConnectionRegistry:
        """Tracks open WebSocket connections, grouped by the connecting User's Role."""

        def __init__(self) -> None:
            self._connections: dict[UserRole, set[WebSocket]] = defaultdict(set)

        def register(self, role: UserRole, websocket: WebSocket) -> None:
            """Record a newly accepted connection under its Role."""
            self._connections[role].add(websocket)

        def unregister(self, role: UserRole, websocket: WebSocket) -> None:
            """Drop a connection, e.g. once it disconnects. No-op if already removed."""
            self._connections[role].discard(websocket)

        async def broadcast_to_role(self, role: UserRole, event: str, payload: dict) -> None:
            """Send one `{domain}.{event}` message to every connection for that Role.

            A send failing on one dead socket (e.g. a client that vanished
            without a clean close) must not stop delivery to the rest.
            """
            envelope = {"event": event, "payload": payload}
            for websocket in list(self._connections[role]):
                try:
                    await websocket.send_json(envelope)
                except Exception:
                    self.unregister(role, websocket)

        async def close_all(self) -> None:
            """Close every open connection. Called on app shutdown."""
            for role_connections in self._connections.values():
                for websocket in list(role_connections):
                    await websocket.close()
            self._connections.clear()
    ```
  - [x] Register in `backend/container.py` as a `providers.Resource`, no config dependencies:
    ```python
    def _init_connection_registry() -> Generator[ConnectionRegistry, None, None]:
        registry = ConnectionRegistry()
        yield registry
        # Nothing left running past this point on shutdown.
    ```
    Wire `await registry.close_all()` into that generator's teardown (after the `yield`), not into
    `main.py`'s lifespan — matching how `_init_database` owns its own `engine.dispose()`.
  - [x] The envelope shape is `{"event": "<domain>.<event>", "payload": {...}}`. No AC or spine
    text fixes this exact field naming (it is a "left to implementation" the spine does not even
    flag) — this story is what fixes it for every later consumer. Do not use a different shape
    (e.g. `type`/`data`) without updating this note; whichever shape ships here is what 3.3, 4.2,
    5.1 and 5.2 will consume.

- [x] **Task 2: `RealtimeService` (backend, `services/`)** (AC: 1, 4)
  - [x] New file `backend/services/realtime_service.py`. Thin wrapper over `ConnectionRegistry`,
    existing purely so `api/websocket.py` calls `services/` and not `clients/` directly (AD-1: "routes
    in `api/` call only `services/`"). This is also the seam Epic 3-5's services (`order_service`,
    `kitchen_service`, `inventory_service`) will inject to emit real events later — keep its method
    names generic (`broadcast`, not `broadcast_order_event`), it is not this story's job to guess
    those services' shapes.
    ```python
    class RealtimeService:
        """Emits `{domain}.{event}` push notifications to connected clients, by Role."""

        def __init__(self, registry: ConnectionRegistry, logger: Any) -> None:
            self._registry = registry
            self._logger = logger

        def register(self, role: UserRole, websocket: WebSocket) -> None: ...
        def unregister(self, role: UserRole, websocket: WebSocket) -> None: ...
        async def broadcast(self, role: UserRole, event: str, payload: dict) -> None:
            self._logger.info("Broadcasting {} to role={}", event, role.value)
            await self._registry.broadcast_to_role(role, event, payload)
    ```
  - [x] Register as a `providers.Factory` in `container.py`, `registry=connection_registry,
    logger=logging`, same pattern as `user_service`.

- [x] **Task 3: WebSocket auth dependency** (AC: 2)
  - [x] Add `get_current_user_ws` to `backend/api/dependencies.py`, next to `get_current_user`. It
    must reuse `AuthService.get_current_user` (the same verification method the REST path uses,
    satisfying "through the same shared verification logic") — the only new code is extracting the
    token from a `WebSocket` instead of a `Request`, since FastAPI's DI needs a distinct parameter
    type for a websocket route's dependencies:
    ```python
    from starlette.websockets import WebSocketException

    @inject
    async def get_current_user_ws(
        websocket: WebSocket,
        db: SessionDep,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
    ) -> User:
        """Resolve the authenticated User for a WebSocket handshake.

        The WebSocket-route counterpart to get_current_user. Extracts the
        session token from the handshake's cookies (browsers send cookies on
        a WebSocket upgrade automatically, same as any same-origin request)
        and verifies it through the identical AuthService method the REST
        path uses.

        Raises:
            WebSocketException: code 1008 (policy violation), if the token is
                absent, invalid, or expired. Raising before websocket.accept()
                is what makes FastAPI close the handshake cleanly instead of
                accepting then immediately dropping the connection.
        """
        token = websocket.cookies.get(COOKIE_NAME)
        try:
            return await auth_service.get_current_user(token, db)
        except AuthError as exc:
            raise WebSocketException(code=1008, reason=exc.detail) from exc
    ```
  - [x] **Do not** try to reuse `CurrentUserDep`'s `Annotated[User, Depends(get_current_user)]`
    alias for the websocket route — build a parallel `CurrentUserWsDep` alias over
    `get_current_user_ws`. `Request` and `WebSocket` are different Starlette types; FastAPI
    resolves a route's dependency graph against the route's own connection type, so the two are not
    interchangeable, even though the resolved return type (`User`) is identical.

- [x] **Task 4: The WebSocket route + manual Origin check** (AC: 1, 2, 3)
  - [x] New file `backend/api/websocket.py`:
    ```python
    router = APIRouter()

    @router.websocket("/api/ws")
    async def websocket_endpoint(
        websocket: WebSocket,
        user: CurrentUserWsDep,
        realtime_service: RealtimeService = Depends(Provide[Container.realtime_service]),
        allow_origin: str = Depends(Provide[Container.config.cors.allow_origin]),
    ) -> None:
        """The single push channel every authenticated session connects to.

        Scoped to the connecting User's Role (AD-2): registered under
        user.role, so a broadcast can target that Role specifically. Read-only
        from the client's perspective — inbound frames are received only to
        detect disconnect, never acted on (AD-2: "Clients never treat the
        WebSocket as a write channel").
        """
        origin = websocket.headers.get("origin")
        if origin != allow_origin:
            raise WebSocketException(code=1008, reason="Origin not allowed")

        await websocket.accept()
        realtime_service.register(user.role, websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            realtime_service.unregister(user.role, websocket)
    ```
  - [x] **The manual Origin check is required, not optional polish.** `CORSMiddleware` only
    inspects the ASGI `http` scope; a WebSocket handshake is a `websocket` scope, so
    `app.add_middleware(CORSMiddleware, ...)` in `main.py` silently does not apply here. Without
    this check, AD-3's "explicit allow-list, never wildcard" has a real, silent gap on this one
    transport. Verify by testing a handshake with a mismatched `Origin` header is rejected before
    accept.
  - [x] Include the router in `backend/api/router.py`, alongside the existing includes.
  - [x] In `backend/main.py`, append `"api.websocket"` and `"api.dependencies"` is already present
    — `get_current_user_ws` lives in the already-wired `api.dependencies` module, so no change
    needed there, but `api.websocket` itself uses `@inject`-free `Depends(Provide[...])` at the
    route function directly, which still requires the *module* to be wired. Append, do not
    replace: `container.wire(modules=["api.auth", "api.dependencies", "api.admin",
    "api.websocket"])` (AD-1, the trap every prior story has hit or avoided).

- [x] **Task 5: Backend NFR-1 smoke test** (AC: 5)
  - [x] New file `backend/tests/test_websocket.py`. **Do not** use
    `starlette.testclient.TestClient(app).websocket_connect(...)` for this specific test — it runs
    the ASGI app in a background thread with its own event loop, and this test needs to call
    `realtime_service.broadcast(...)` from *outside* the connection while the connection is open,
    on the *same* event loop the connection's registry lives on (the registry is not built to be
    thread-safe across event loops). Instead, run a real `uvicorn.Server` in an `asyncio.create_task`
    inside the test's own event loop, bound to `127.0.0.1` on an ephemeral port
    (`uvicorn.Config(app, host="127.0.0.1", port=0, ...)`, then read the bound port back), so the
    server, the test's `broadcast` call, and the WebSocket client all share one loop:
    ```python
    @pytest.mark.asyncio
    async def test_broadcast_delivered_within_two_seconds(db_session: AsyncSession) -> None:
        # Arrange: seed a User, log in via HTTP to get a real session cookie,
        # start a real uvicorn.Server bound to an ephemeral port as a background task.
        # Act: open a websockets.connect(..., <cookie header>) to it, then call
        # `main.container.realtime_service().broadcast(role, "test.smoke", {...})`
        # directly (bypassing REST, this story owns no domain route that would trigger one).
        # Assert: the client receives {"event": "test.smoke", "payload": {...}} within 2s
        # (asyncio.wait_for(websocket.recv(), timeout=2)).
        ...
    ```
    Check the installed `websockets` v16 API (`import websockets; websockets.__version__`) for the
    exact keyword to attach a custom `Cookie` header on `connect()` before writing this — it has
    changed name across major versions, do not guess from an older tutorial.
  - [x] Separately (can use the simpler `TestClient.websocket_connect`, since these do not need an
    external broadcast mid-connection): a valid session connects and `websocket.accept()` succeeds;
    a missing/expired/invalid cookie is rejected before accept (AC2); a mismatched `Origin` header
    is rejected before accept (Task 4's manual check).

- [x] **Task 6: Frontend `RealtimeProvider`** (AC: 6)
  - [x] New file `frontend/src/components/shell/RealtimeProvider.tsx`. This is the "producer" Story
    1.4's review deferred here verbatim: `App.tsx` currently mounts
    `<ConnectionStatusProvider>` with no `status` prop, so the value is permanently `"connected"`
    and nothing can ever set `"reconnecting"`. Do not add a second, competing connection-status
    mechanism — this component's whole job is to become the one thing that sets `status`.
    - Owns a native `WebSocket` connecting to `wss://`/`ws://` + `/api/ws`, derived from
      `config.api.baseUrl` (swap the scheme; do not hardcode a second base URL — reuse
      `src/config/config.ts`, the same single source `httpClient.ts` already uses).
    - Tracks `status: "connected" | "reconnecting"` in state; renders
      `<ConnectionStatusProvider status={status}>{children}</ConnectionStatusProvider>` internally
      — `ConnectionStatusContext`'s public shape (`{ status }`) is Story 1.4's contract and must
      not change.
    - On close/error: sets `status="reconnecting"` and retries with capped exponential backoff
      (e.g. 1s, 2s, 4s, 8s, capped at 30s; reset to the initial delay on a successful reconnect).
      This is what satisfies AC6's "retries automatically" — Story 1.4's review explicitly rejected
      building this early because "a retry loop with no transport to retry against would be
      speculative"; the transport now exists.
    - Exposes a second, separate context (e.g. `RealtimeContext` with a `subscribe(event, handler)`
      returning an unsubscribe function) for future consumers to receive parsed
      `{event, payload}` messages by event name. **Build only this generic subscribe mechanism, no
      per-domain handler.** Stories 3.3/4.2/5.1/5.2 are this context's actual consumers; inventing
      what they call `subscribe` with is out of scope here.
  - [x] Mount `RealtimeProvider` in `frontend/src/components/shell/RequireAuth.tsx`, wrapping only
    the final `<AppShell user={user} />` return — **not** at `App.tsx`'s top level. The connection
    must not exist before a User is authenticated (the backend would reject it per AC2 anyway, and
    an unauthenticated retry loop hammering `/api/ws` on the Login screen is pure waste). Remove
    `<ConnectionStatusProvider>` from `App.tsx` entirely; it is superseded by the one
    `RealtimeProvider` now renders internally. `ReconnectingBanner` (rendered inside `AppShell`,
    inside `RequireAuth`) needs no code change, it already reads `useConnectionStatus()`.

- [x] **Task 7: Frontend tests** (AC: 6)
  - [x] `jsdom` (this project's test environment) has no real `WebSocket` implementation. Do not
    add a new dependency (e.g. `mock-socket`) for this — the surface `RealtimeProvider` actually
    uses is small (construct, `onopen`/`onclose`/`onerror`/`onmessage`, `close()`; the client never
    sends, per AD-2) and is cheap to hand-write. In the test file, define a minimal fake class and
    install it with `vi.stubGlobal("WebSocket", FakeWebSocket)`, matching this project's existing
    preference for hand-rolled test doubles over new test-only dependencies (mirrors the backend's
    choice of `starlette.testclient`/a real `uvicorn.Server` over a mocking library).
  - [x] Cover: connecting renders `status: "connected"` once the fake's `onopen` fires; the fake
    firing `onclose` flips `status` to `"reconnecting"`; a second `onopen` (simulating the retry
    succeeding) flips it back to `"connected"`; the backoff delay grows between successive retries
    and resets after a successful reconnect (use `vi.useFakeTimers()`).

### Review Findings

Code review 2026-08-11 (three parallel adversarial layers on opus: Blind Hunter, Edge Case Hunter,
Acceptance Auditor). Claims marked CONFIRMED were reproduced empirically against a live Postgres,
not accepted from the reviewer's reasoning alone.

Three findings were routed as decisions and resolved by Ron on 2026-08-11; each is recorded below
as a patch carrying the chosen approach.

- [x] [Review][Patch] Re-verify authorization periodically so a socket cannot outlive its JWT [backend/api/websocket.py:56-62] — **Decision: periodic re-verification.** A connection opened one minute before token expiry currently keeps receiving Role-scoped pushes for as long as the tab stays open (days), and deactivating an account (`is_active=False`) or changing a User's Role has no effect on the live socket, because AC2 gates only the upgrade. Wrap the receive loop in `asyncio.wait_for` with a tick, re-run the same `AuthService.get_current_user` verification on each tick, and close with 1008 once the token no longer validates. Note this compounds the DB-session finding below: the re-verification query needs a short-lived session per tick, not a session pinned for the connection's life.
- [x] [Review][Patch] Enforce one connection per User by closing the prior socket [backend/clients/websocket.py:19-29] — **Decision: enforce per-user.** `ConnectionRegistry` is keyed only by `UserRole` with no user or session identity, and `register()` adds unconditionally, so one User with three tabs holds three sockets and receives every event three times, and an authenticated client can open sockets in a loop. Key the registry by user id as well as Role and, on register, close any socket already held by that user. This makes AC1 literally true and bounds memory; the accepted trade-off is that opening a second tab closes the first tab's connection.
- [x] [Review][Patch] Widen the broadcast seam to accept multiple Roles [backend/services/realtime_service.py:1] — **Decision: multiple Roles only, no per-User targeting yet.** `broadcast(role, ...)` takes exactly one Role, so `order.item_status_changed` (needed by both cooks and waiters) requires two calls, contradicting AC4's "emitted exactly once". Change to `broadcast(roles: Iterable[UserRole], ...)` so one emission reaches several Roles. Per-User targeting ("the waiter who owns this table") is deliberately left for whichever story first genuinely needs it, even though the per-user keying above makes it cheap to add later.
- [x] [Review][Patch] CONFIRMED: every open WebSocket pins a PostgreSQL connection for the life of the connection [backend/clients/database.py:17-30] — `SessionWsDep` is a `yield` dependency on a websocket route, so FastAPI holds the session open until the connection closes. Measured: 6 open sockets = 6 checked-out pool connections, released only on disconnect. With `create_async_engine` defaults (`pool_size=5`, `max_overflow=10`), the 16th concurrent device exhausts the pool and every REST request then blocks 30s and fails. Fix: acquire a short-lived session inside `get_current_user_ws` and release it before `accept()`.
- [x] [Review][Patch] The WebSocket transport logs nothing, violating the project's own logging convention [backend/api/websocket.py:11] — CLAUDE.md requires routers to log request received/rejected and clients to log external-call failures. An accepted connection, a rejected Origin, an auth rejection, a disconnect, and a failed broadcast send are all invisible. `RealtimeService.broadcast`'s line fires before delivery is attempted and proves nothing. Every other router (`api/auth.py`, `api/admin.py`) logs its accept/reject paths.
- [x] [Review][Patch] A serialization error silently and permanently unsubscribes a healthy client [backend/clients/websocket.py:62-66] — `send_json` calls `json.dumps`, so the first payload carrying a `datetime`, `Decimal`, or ORM object raises `TypeError` (a sender-side bug) and the bare `except Exception` responds by evicting the socket. The socket is still open and still parked in `receive_text`, so the client never sees a close, never reconnects, and stops receiving events forever, with nothing logged. Fix: serialize once outside the loop, distinguish transport failure from serialization failure, log both.
- [x] [Review][Patch] One slow client delays delivery to every other client of the same Role [backend/clients/websocket.py:62-66] — Sends are awaited sequentially with no timeout. A client with a full send buffer blocks the loop until it drains, which is exactly how NFR-1's 2-second budget gets violated. The smoke test has one connected client and is structurally incapable of catching it. Fix: `asyncio.gather` with a per-send `wait_for`.
- [x] [Review][Patch] CONFIRMED: a binary frame kills the connection with an unhandled exception [backend/api/websocket.py:57-60] — `receive_text()` returns `message["text"]`, raising `KeyError` for a bytes frame; `except WebSocketDisconnect` does not cover it. Reproduced: the client gets `ConnectionClosedError: no close frame received or sent` and the server logs a traceback. The `finally` does still unregister, so there is no registry leak. Since the loop exists only to detect disconnect, use `receive()` and discard, or close with a policy code on any inbound data frame.
- [x] [Review][Patch] The three "rejected before accept" tests assert only `pytest.raises(Exception)` [backend/tests/test_websocket.py:59-102] — That passes for a `NameError`, a typo in the URL, a failed login, or a DB error, so a genuine auth regression goes through. None asserts the close code, and none distinguishes "rejected at handshake" from "accepted then dropped" — the exact property the test names claim. CONFIRMED the correct assertion is available: a missing cookie raises `WebSocketDisconnect` with `code == 1008`.
- [x] [Review][Patch] `test_valid_session_connects` contains no assertion at all [backend/tests/test_websocket.py:44-55] — Only a comment saying "connecting does not raise". It never checks that `client.cookies.get(COOKIE_NAME)` returned a token, so if login silently broke, the header becomes `access_token=None` — failing this test for the wrong reason, and passing the sibling rejection tests for the wrong reason.
- [x] [Review][Patch] Role scoping — the central claim of AC1 — has no test [backend/tests/test_websocket.py:106] — No test broadcasts to one Role and asserts a connection held by another Role does not receive it. The smoke test connects one cook and broadcasts to cooks. Replacing `broadcast_to_role`'s body with a broadcast to every open socket would leave the entire suite green. Also untested: `close_all`, the dead-socket eviction path, `RealtimeService` in isolation, and two connections of the same Role both receiving one event.
- [x] [Review][Patch] Task 5's "invalid" (wrong-signature) token case is not covered [backend/tests/test_websocket.py:59-83] — Only missing and expired are tested. A token signed with the wrong key takes the `NotAuthenticatedError` branch, distinct from `SessionExpiredError`.
- [x] [Review][Patch] The smoke test can hang forever and mutates shared container state [backend/tests/test_websocket.py:114-142] — `while not server.started` and `await server_task` are both unbounded, so a server that fails to bind hangs the suite instead of failing it. More seriously, `lifespan="on"` runs the app lifespan against the module-global `container`, so on exit it calls `shutdown_resources()`: the `logging` Resource removes the loguru sink and `database` disposes the engine for every test that runs afterwards. The suite passes today only because of ordering.
- [x] [Review][Patch] Every authenticated page load flashes the amber "Reconnecting..." warning [frontend/src/components/shell/RealtimeProvider.tsx:83] — Initial state is `"reconnecting"` and `ReconnectingBanner` renders a MUI warning `Alert` for any non-connected status. The socket cannot open synchronously, so every login and every reload shows a scary banner (and a layout shift) before flipping to connected. `ConnectionStatusContext`'s own default is `"connected"` precisely to avoid this. Fix: start at `"connected"` and only degrade on a close after a successful open, or add a distinct initial state.
- [x] [Review][Patch] The client retries forever against a server deliberately rejecting it [frontend/src/components/shell/RealtimeProvider.tsx:117-127] — Every close is treated identically. A 1008 policy close (expired token, wrong Origin, deactivated account) is permanent, but the provider reschedules on it like a transient drop, capping at one attempt per 30s for as long as the tab is open. It never inspects `CloseEvent.code`, never gives up, and never signals the app to re-authenticate, so an expired session yields an eternal banner instead of a redirect to login. There is also no jitter, so every device retries in lockstep after a backend restart.
- [x] [Review][Patch] A superseded socket's `onclose` can fire after a replacement exists [frontend/src/components/shell/RealtimeProvider.tsx:117-127] — `scheduleRetry` overwrites `retryTimerRef.current` unconditionally, so a late close from an abandoned socket schedules an extra `connect()`, producing duplicate timers and duplicate sockets. Guard with `if (socketRef.current !== socket) return;` and null the old handlers before reconnecting.
- [x] [Review][Patch] A throwing subscriber takes down its siblings [frontend/src/components/shell/RealtimeProvider.tsx:113-115] — `handlers?.forEach((handler) => handler(message.payload))` runs consumer callbacks with no `try/catch`, so one subscriber throwing stops delivery to every other subscriber of that event and escapes into the WebSocket handler. Relatedly, an unparseable frame is swallowed by `catch { return; }` and an unknown `event` name is dropped, both with no log — invisible during exactly the debugging session where you would want them visible.
- [x] [Review][Patch] The frontend tests leave the risky paths uncovered [frontend/src/components/shell/RealtimeProvider.test.tsx:18-35] — `FakeWebSocket` never exposes `readyState` or fires `onerror`, so `socket.onerror = () => socket.close()` is never exercised. Nothing tests the `unmountedRef` guard against a reconnect after unmount, and nothing tests `MAX_RETRY_DELAY_MS` — deleting the `Math.min` cap breaks no test.
- [x] [Review][Patch] A non-object JSON frame throws inside `onmessage` [frontend/src/components/shell/RealtimeProvider.tsx:107-113] — `JSON.parse("null")` or `JSON.parse("3")` parses fine, then `message.event` throws a `TypeError`. Guard the shape before reading `event`.
- [x] [Review][Patch] `websocketUrl()` produces a malformed URL for any non-`http` base [frontend/src/components/shell/RealtimeProvider.tsx:62-64] — `config.api.baseUrl.replace(/^http/, "ws")` silently yields `/api/api/ws` for a relative base like `/api`, a common deployment choice. Not reachable today (the default and `.env.example` are both absolute `http://`), so this is cheap hardening rather than a live bug. Fix: build with `new URL(base, window.location.origin)` and swap the protocol.
- [x] [Review][Patch] `close_all` has no defensive guards [backend/clients/websocket.py:68-80] — `await websocket.close()` is unguarded, and `unregister` on a `defaultdict` can insert a new key while `close_all` iterates `.values()` ("dictionary changed size during iteration"). NOT reproduced: shutdown with an open socket was clean, because uvicorn closes websocket connections before lifespan shutdown, so the registry is already empty. Filed as low-cost robustness, not a live defect.
- [x] [Review][Patch] `frontend/.env.example` is undocumented and `ConnectionStatusContext`'s docstring is now stale — The new file appears nowhere in the story's File List or Change Log, which are otherwise presented as exhaustive (its `VITE_*` keys are Story 1.2-era `config.ts` variables, unrelated to this transport). Separately, `ConnectionStatusContext.tsx` still reads "Defaults to 'connected', there is no real transport to observe yet. Story 1.5 replaces this default..." — the story chose not to edit that file, but the comment now actively misleads.
- [x] [Review][Patch] The route uses `@inject`, contradicting Task 4's stated design — Task 4 specifies "`api.websocket` itself uses `@inject`-free `Depends(Provide[...])` at the route function directly". The implementation is arguably more correct, but the deviation is unrecorded in the Debug Log / Completion Notes, which document every other deviation (the `WebSocketException` import, `get_session_ws`).
- [x] [Review][Patch] Test-only consistency nits [backend/tests/test_websocket.py:20] — `_ALLOWED_ORIGIN` is hardcoded while the same file correctly reads `secret_key` from `load_config(SETTINGS.CONFIG_PATH)`, so setting `FRONTEND_ORIGIN` in CI breaks three tests for no reason. Separately, the route's Origin check runs after the auth dependency, so a cross-origin handshake still costs a JWT decode and a DB query before being refused, and it compares against a single string while `main.py`'s `CORSMiddleware` takes a list.
- [x] [Review][Defer] The `Secure` + `SameSite=Lax` session cookie limits this transport to same-site/localhost, and it fails silently [backend/api/auth.py] — deferred, pre-existing. The cookie-on-upgrade design holds only because `localhost` gets the potentially-trustworthy exemption for `Secure` and `:3000`/`:8000` are same-site. Any cross-site deployment, or `ws://` over a LAN address, drops the cookie; the symptom is a permanent silent "Reconnecting..." banner with no server-side log. `api/auth.py` already carries a review note that LAN access silently drops this cookie — this story inherits that constraint rather than introducing it.
- [x] [Review][Defer] Removing the app-wide `ConnectionStatusProvider` lets any future consumer outside `RequireAuth` silently read a fake "connected" [frontend/src/App.tsx] — deferred, pre-existing shape. `ConnectionStatusContext`'s default is `"connected"` by design, and the only consumer today (`ReconnectingBanner`, inside `AppShell`) is within the provider, so nothing is wrong now. A login-screen or error-boundary consumer added later would read the default with no warning.

## Dev Notes

### Architecture compliance

- **AD-1 (DI composition root).** `ConnectionRegistry` is a `providers.Resource` (explicitly named
  by AD-1's own text as an example, alongside the DB engine); `RealtimeService` is a
  `providers.Factory`, same shape as `user_service`. `api/websocket.py` calls only
  `services/realtime_service.py`, never `clients/websocket.py` directly, keeping the same
  api-to-services-to-clients direction as every REST router.
- **AD-2 (Real-time updates via WebSockets).** This story's entire subject. One endpoint, one
  connection per session, Role-scoped registration, `{domain}.{event}` naming fixed here for every
  later emitter, read-only from the client.
- **AD-3 (Auth).** The WS handshake is gated by the identical `AuthService.get_current_user`
  verification the REST path uses — `get_current_user_ws` is a thin adapter over the same method,
  not a second implementation. The manual `Origin` check (Task 4) is this story's addition to
  AD-3's CORS guarantee, needed because `CORSMiddleware` structurally cannot see a `websocket`
  scope.
- **NFR-2 (universal authorization).** No mutating action is added by this story — the channel is
  push-only from the server, so there is no "trusted internal bypass" surface to create.

### Existing files this story modifies

| File | Current state | What changes |
|---|---|---|
| `backend/container.py` | `logging`, `database` Resources; `auth_service`, `user_service` Factories | Add `connection_registry` (Resource) and `realtime_service` (Factory) |
| `backend/main.py` | `container.wire(modules=["api.auth", "api.dependencies", "api.admin"])` | Append `"api.websocket"` |
| `backend/api/dependencies.py` | `get_current_user`/`CurrentUserDep`, `require_role` | Add `get_current_user_ws`/`CurrentUserWsDep` |
| `backend/api/router.py` | Includes `auth_router`, `admin_router` | Also include the new websocket router |
| `frontend/src/App.tsx` | Wraps everything in `<ConnectionStatusProvider>` (static, no `status` prop) | Remove that wrapper; `RealtimeProvider` (mounted lower, in `RequireAuth`) now owns it |
| `frontend/src/components/shell/RequireAuth.tsx` | Returns `<AppShell user={user} />` directly | Wrap that return in `<RealtimeProvider>` |

Files that must **not** change: `frontend/src/components/shell/ConnectionStatusContext.tsx` (its
`{ status }` contract is exactly what Story 1.4 fixed for this story to match — read it, do not
edit it), `backend/services/auth_service.py` (its `get_current_user` method is reused as-is, not
duplicated or modified), `backend/services/user_service.py`, `backend/api/admin.py`,
`backend/api/auth.py` (no change needed to any of Story 1.3/1.4's routes).

### New files

- `backend/clients/websocket.py`
- `backend/services/realtime_service.py`
- `backend/api/websocket.py`
- `backend/tests/test_websocket.py`
- `frontend/src/components/shell/RealtimeProvider.tsx`
- `frontend/src/components/shell/RealtimeProvider.test.tsx`

### Project Structure Notes

- Imports relative to `backend/` as root, same as every prior story.
- No new backend dependency (AC3) and no new frontend dependency (Task 7's fake `WebSocket` is
  hand-written, not a package). `pyproject.toml`/`uv.lock` and `package.json`/`pnpm-lock.yaml`
  unchanged.
- Type hints and docstrings per `project-context.md`'s conventions; no em dash. Test files skip
  docstrings, `# Arrange`/`# Act`/`# Assert` on the backend, whatever this project's existing
  frontend test files already use as their equivalent structuring comments (check
  `ThemeModeProvider.test.tsx`/`RowsSkeleton.test.tsx` for the current convention before writing
  new ones).

### Testing

- Backend: `uv run pytest` from `backend/`. The NFR-1 smoke test (Task 5) is the one test in this
  project that starts a real `uvicorn.Server` rather than using the `client`/`db_session` fixtures
  or `starlette.testclient` — justified because it is the one test needing a broadcast triggered
  from outside an open connection on the same event loop. Every other new backend test in this
  story can and should use the existing fixtures/`TestClient` pattern; do not default to the heavy
  real-server pattern for tests that do not need it.
- Frontend: `pnpm test` from `frontend/`. `vi.stubGlobal("WebSocket", ...)` per Task 7; restore the
  real global (or let Vitest's environment reset handle it) between tests so one test's fake socket
  cannot leak into another.
- Full regression: run both suites. This story touches `container.py`, `main.py`,
  `api/dependencies.py`, `api/router.py`, `App.tsx`, and `RequireAuth.tsx`, all shared by every
  existing backend and frontend test.

### References

- Story source: [Source: _bmad-output/planning-artifacts/epics.md#Story 1.5]
- Transport invariant: [Source: ARCHITECTURE-SPINE.md#AD-2] — single endpoint, Role-scoped, exactly
  one emission per state change, `{domain}.{event}` naming, read-only from the client
- Auth invariant: [Source: ARCHITECTURE-SPINE.md#AD-3] — one shared verification path, explicit
  CORS allow-list
- Naming convention: [Source: ARCHITECTURE-SPINE.md#Consistency Conventions] — "WebSocket events:
  `{domain}.{event}`, past-tense (e.g. `order.item_status_changed`)"
- Left-to-implementation flags this story resolves: [Source: ARCHITECTURE-SPINE.md, "Open
  Questions" section] — "WebSocket handshake mechanics (exact auth-token transport: query param vs.
  subprotocol vs. cookie-on-upgrade) — left to implementation; AD-3 only fixes that it must be
  gated by the same JWT"
- Prior-story handoff (the exact deferred obligation this story closes): [Source:
  _bmad-output/implementation-artifacts/deferred-work.md#Deferred from: code review of story-1-4] —
  "AC7's connection producer and automatic retry ship with Story 1.5... wire the live WebSocket to
  drive `status`, and implement AC7's 'automatic retry' there. The context's shape is the contract
  1.5 must match, so it should not be changed without revisiting `ReconnectingBanner`."
- Contract this story must match exactly: [Source:
  frontend/src/components/shell/ConnectionStatusContext.tsx] — `{ status: "connected" |
  "reconnecting" }`, `useConnectionStatus()`, `ConnectionStatusProvider`
- Downstream consumers depending on this story's naming/envelope decisions:
  [Source: _bmad-output/planning-artifacts/epics.md#Story 3.3, #Story 4.2, #Story 5.1, #Story 5.2]
- Conventions: [Source: _bmad-output/project-context.md] — "Where code goes" (`clients/` vs.
  `services/` vs. `api/`), comment/docstring rules, Testing section

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (Claude Code, bmad-dev-story workflow)

### Debug Log References

Followed the story's tasks in written order, verifying each design decision empirically before
committing to it in code (several of the story's own suggested snippets turned out to need
correction once actually run):

- **`WebSocketException` import.** The story suggested `from starlette.websockets import
  WebSocketException`. That name lives at `starlette.exceptions`, not `starlette.websockets`, in
  the installed starlette 1.0. Used `from fastapi import WebSocketException` instead (FastAPI
  re-exports it), which is what `api/dependencies.py` and `api/websocket.py` both already import
  `Depends`/`WebSocket` from, so no new import source.
- **`Request`-typed dependencies do not resolve inside a `@websocket` route at all.** Verified with
  a throwaway probe: a sub-dependency typed `request: Request` raises `TypeError: missing 1
  required positional argument` when reached from a websocket route, it is not a graceful
  fallback. `clients/database.py`'s existing `get_session(request: Request)` (used by `SessionDep`,
  which `get_current_user_ws` would naturally want to depend on) hits exactly this. Added
  `get_session_ws(websocket: WebSocket)` / `SessionWsDep` as the parallel dependency, identical
  lookup logic, only the connection-type parameter differs. This is the same shape the story's
  own Task 3 already used for `get_current_user` vs `get_current_user_ws`; it was missing one layer
  down at the session-dependency level and would have failed at runtime if left as `SessionDep`.
- **`Depends(Provide[Container.config.cors.allow_origin])` does resolve correctly**, once actually
  exercised end-to-end (route + `TestClient`), despite the story flagging it as a novel,
  unverified-elsewhere pattern in this codebase. Confirmed with a throwaway FastAPI app before
  using it in the real route.
- **`starlette.testclient.TestClient.websocket_connect` does not reuse the client's HTTP cookie
  jar.** A cookie set by a prior `client.post("/api/auth/login", ...)` is invisible to
  `websocket_connect` unless passed explicitly via a `Cookie` header (or the deprecated per-call
  `cookies=` kwarg, avoided here). Verified by a probe that failed identically for an authenticated
  and an unauthenticated client until the header was added explicitly.
- **`websockets` v16's `connect()` uses `additional_headers`** (not `extra_headers`, the name used
  in older tutorials/major versions) and a top-level `origin=` kwarg. Confirmed via
  `inspect.signature` against the installed version before writing the NFR-1 test.
- **`container.<factory>()` returns an awaitable, not the instance, once any dependency in its
  chain is an async Resource.** `realtime_service` depends on `connection_registry` (an async
  `providers.Resource`), so `container.realtime_service()` from the NFR-1 test needed an explicit
  `await`, exactly like `clients/database.py`'s `get_session` already does for
  `request.app.container.database()`.
- **jsdom 30 (this project's version) defines a real `WebSocket` global** that attempts an actual,
  slow, eventually-failing network connection, rather than being absent entirely as in older jsdom.
  This is why the pre-existing `router.test.tsx` (which renders an authenticated route, and so now
  also mounts `RealtimeProvider`) did not throw when this story landed: the real WebSocket fails
  silently in the background after the test has already finished, never synchronously. Confirmed
  the frontend test plan's hand-rolled `FakeWebSocket` (Task 7) was the right call, not optional
  polish, since relying on jsdom's real implementation would make status/backoff assertions
  non-deterministic.
- React 19 (`@types/react` ^19) requires `useRef` to be called with an explicit initial value; the
  story's sketch (`useRef<ReturnType<typeof setTimeout>>()`, no argument) does not compile under
  this project's strict TypeScript config. Used `useRef<... | undefined>(undefined)`.

Verified full end-to-end operation beyond the test suite: `docker compose up -d --build`, logged in
against the live container via a real `websockets` client (confirmed the `/api/ws` handshake
succeeds against the deployed app, not just the test app), and drove a real headless browser
through login, confirming the WebSocket opens (`ws://localhost:8000/api/ws`) and stays open with no
close/error events for the session's duration.

**Post-review (2026-08-11), applying the code review's patch findings:**

- **The route keeps `@inject`, deviating from Task 4's "`@inject`-free `Depends(Provide[...])`
  directly."** Verified (again) that this is necessary, not optional: `Provide[...]` markers do not
  resolve at all without `@inject` on the function that declares them, confirmed the same way as the
  `Depends(Provide[Container.config.cors.allow_origin])` check above. Task 4's suggested shape does
  not work; the deviation was real but unrecorded until now.
- **Registry keying changed from `dict[UserRole, set[WebSocket]]` to `dict[int, _Connection]`,
  keyed by user id**, to enforce AC1's "one connection per authenticated session" (closing a User's
  prior socket on a new one) and to let a broadcast target several Roles in one call. Doing so
  surfaced and fixed a real race: the first version closed the old socket *before* installing the
  new one, so a broadcast landing in that window would find the stale, already-closing connection
  and drop it — the new connection would simply miss that event. Fixed by swapping the dict entry
  in before awaiting the old socket's close. Caught by
  `test_second_connection_for_a_user_replaces_the_first`, which failed against the first ordering.
- **`get_session_ws`/`SessionWsDep` (added earlier in this story, see the Debug Log entry above)
  were removed**, not merely renamed. Reproduced the pool-exhaustion finding directly: opening 6
  concurrent sockets checked out 6 pooled connections that were only released on disconnect, against
  a default `pool_size=5` + `max_overflow=10`. Both `get_current_user_ws` and the new periodic
  re-verifier now open a session through `session_scope()` only for the duration of one query.
- **Smoke-test infrastructure fix, found while adding the new Role-scoping tests**: the original
  `test_broadcast_delivered_within_two_seconds` ran its `uvicorn.Server` with `lifespan="on"` but
  never paired it with an explicit shutdown, and other tests in the same module called
  `container.<factory>()` outside any server context at all. Once more tests needed their own
  server, this surfaced as `asyncpg.exceptions.InterfaceError: another operation is in progress` in
  whichever test ran after the first: the app's lifespan disposes the database engine on shutdown,
  which stranded the engine against a pytest-asyncio event loop a later test's own loop had already
  replaced. Fixed by making every test's server symmetric (`lifespan="on"`, bounded `should_exit` +
  `await server_task`), so init and shutdown always pair within one test.

### Completion Notes List

**What was built.** The full real-time push transport: `ConnectionRegistry`
(`backend/clients/websocket.py`, a `providers.Resource` per AD-1's own example), `RealtimeService`
(`backend/services/realtime_service.py`, the `broadcast(role, event, payload)` seam every future
domain service will call), the WebSocket-specific auth dependency (`get_current_user_ws` /
`CurrentUserWsDep`, reusing `AuthService.get_current_user` verbatim) and its session-dependency
counterpart (`get_session_ws` / `SessionWsDep`, needed because `Request`-typed dependencies cannot
resolve inside a `@websocket` route at all), the single `/api/ws` endpoint with a manual `Origin`
check (`CORSMiddleware` does not inspect the websocket ASGI scope), and the frontend
`RealtimeProvider` that owns the connection lifecycle, drives Story 1.4's
`ConnectionStatusContext` with real state, and retries with capped exponential backoff.

**Both of Story 1.4's exact deferred obligations are closed.** `ConnectionStatusProvider` no
longer sits statically at `App.tsx`'s top with no `status` prop; `RealtimeProvider` (mounted inside
`RequireAuth`, wrapping only the authenticated `AppShell`) now renders it internally with the real
WebSocket state, and `ReconnectingBanner` (unchanged) is exercised end-to-end for the first time.
AC6's "retries automatically" is implemented as capped exponential backoff (1s doubling to a 30s
ceiling, reset to 1s on a successful reconnect).

**Design decisions worth knowing:**

1. **Envelope shape fixed as `{"event": "<domain>.<event>", "payload": {...}}`.** No AC or spine
   text pinned this; it is fixed here because every future emitter (3.3, 4.2, 5.1, 5.2) needs one
   shape to agree on, and this story is the one place that gets to decide it before anyone depends
   on it.
2. **The NFR-1 smoke test runs a real `uvicorn.Server`** bound to an ephemeral port inside the
   test's own event loop, rather than `starlette.testclient.TestClient`. `TestClient` runs the ASGI
   app in a separate thread with its own event loop; this test needs to call
   `realtime_service.broadcast(...)` from outside an already-open connection, on the same loop the
   connection registry lives on, which only a real, shared-loop server makes safe. Every other new
   backend test in this story uses the ordinary `TestClient`/fixture pattern; the heavier pattern is
   scoped to the one test that actually needs it.
3. **No new dependency, either side (AC3).** `websockets` was already present transitively; the
   frontend fake WebSocket (Task 7) is hand-written rather than adding `mock-socket`, matching this
   project's existing preference for test doubles over new test-only packages.
4. **`RealtimeProvider` mounts inside `RequireAuth`, not at `App.tsx`'s top.** The backend rejects
   an unauthenticated handshake anyway (AC2); mounting earlier would mean a retry loop hammering
   `/api/ws` from the Login screen for no reason. `ConnectionStatusProvider` (Story 1.4) is removed
   from `App.tsx` entirely, since `RealtimeProvider` now renders it internally wherever it mounts.
5. **`get_session_ws`/`SessionWsDep` were not in the story's own task list**, discovered only by
   running the code: `get_current_user_ws` naturally wants `SessionDep` (matching the REST
   `get_current_user`), but a `Request`-typed dependency cannot resolve at all inside a
   `@websocket` route. Added as the same kind of parallel dependency Task 3 already specified one
   layer up.

### File List

**Added**

- `backend/clients/websocket.py`
- `backend/services/realtime_service.py`
- `backend/api/websocket.py`
- `backend/tests/test_websocket.py`
- `frontend/src/components/shell/RealtimeProvider.tsx`
- `frontend/src/components/shell/RealtimeProvider.test.tsx`
- `frontend/.env.example` (documents the pre-existing Story 1.2 `VITE_API_BASE_URL`/
  `VITE_API_TIMEOUT_MS` variables `config.ts` already read; not a new variable this story
  introduces, added because local dev otherwise had no example env file at all)

**Modified**

- `backend/container.py` (added `connection_registry` Resource, `realtime_service` Factory; after
  code review, `connection_registry` also takes the injected `logger`)
- `backend/main.py` (appended `"api.websocket"` to `container.wire(modules=[...])`)
- `backend/api/dependencies.py` (added `get_current_user_ws`/`CurrentUserWsDep`; after code review,
  also `verify_ws_session` (extracted, reused by periodic re-verification) and `verify_ws_origin`
  (moved from an inline check in the route to a route-level dependency, so it runs before the
  session cookie is read))
- `backend/clients/database.py` (originally added `get_session_ws`/`SessionWsDep`, not in the
  original task list, see Debug Log References; after code review, replaced by a `session_scope`
  context manager both `get_session`/`get_current_user_ws`/the periodic re-verifier share, since the
  `yield`-dependency shape pinned one pooled database connection per open socket for the
  connection's entire lifetime)
- `backend/api/router.py` (included the new websocket router)
- `frontend/src/App.tsx` (removed the static `ConnectionStatusProvider` wrapper)
- `frontend/src/components/shell/RequireAuth.tsx` (wrapped `AppShell` in `RealtimeProvider`)
- `frontend/src/components/shell/ConnectionStatusContext.tsx` (docstring only, after code review:
  it referred to this story's default as forthcoming, which was stale once this story shipped; the
  `{ status }` contract itself is still unmodified)

**Confirmed unchanged**: `backend/services/auth_service.py`, `backend/services/user_service.py`,
`backend/api/admin.py`, `backend/api/auth.py`, `pyproject.toml`/`uv.lock`, `package.json`/
`pnpm-lock.yaml` (no new dependency on either side, per AC3 and Task 7).

## Change Log

| Date | Change |
|---|---|
| 2026-08-11 | Added `ConnectionRegistry` (`backend/clients/websocket.py`) and `RealtimeService` (`backend/services/realtime_service.py`): the connection registry is a `providers.Resource` per AD-1's own text, wired in `container.py`. |
| 2026-08-11 | Added `get_current_user_ws`/`CurrentUserWsDep` (`backend/api/dependencies.py`), reusing `AuthService.get_current_user` verbatim, gated by the httpOnly session cookie sent automatically on the WebSocket handshake. |
| 2026-08-11 | Added `get_session_ws`/`SessionWsDep` (`backend/clients/database.py`), not originally scoped: `Request`-typed dependencies (`SessionDep`) do not resolve at all inside a `@websocket` route, verified by a failing probe before this was added. |
| 2026-08-11 | Added the single `/api/ws` endpoint (`backend/api/websocket.py`), Role-scoped registration, and a manual `Origin` check standing in for `CORSMiddleware`, which does not inspect the websocket ASGI scope. Appended `"api.websocket"` to `container.wire(modules=[...])`. |
| 2026-08-11 | Added `backend/tests/test_websocket.py`: valid-session connect, missing-cookie and expired-token rejection before accept, mismatched-Origin rejection before accept, and the NFR-1 smoke test (real `uvicorn.Server` on an ephemeral port, broadcast-and-receive within 2 seconds). |
| 2026-08-11 | Added `frontend/src/components/shell/RealtimeProvider.tsx`: owns the WebSocket lifecycle, drives `ConnectionStatusContext` with real state, retries with capped exponential backoff (1s doubling to 30s, reset on success). Removed `App.tsx`'s static `ConnectionStatusProvider`; mounted `RealtimeProvider` inside `RequireAuth` instead, wrapping only the authenticated `AppShell`. This closes Story 1.4's review-deferred AC7 obligation exactly as specified there. |
| 2026-08-11 | Added `frontend/src/components/shell/RealtimeProvider.test.tsx` with a hand-rolled `FakeWebSocket` (jsdom 30's real `WebSocket` attempts actual, non-deterministic network connections). Verified by mutation that the backoff-growth assertion actually fails when backoff is removed. |
| 2026-08-11 | Full regression: backend 116 passed (up from 107), frontend 40 passed (up from 34), both reproducible on a fresh database. Verified beyond the test suite via `docker compose up -d --build`: a real `websockets` client and a real headless browser both connect to the live deployed `/api/ws` successfully. |
| 2026-08-11 | Code review (opus, three parallel layers): 3 decisions resolved (periodic re-verification of the session; enforce one connection per User by closing the prior socket; widen `broadcast` to accept multiple Roles), 24 patches applied, 2 deferred (documented in `deferred-work.md`). Confirmed empirically against a live Postgres: 6 open sockets pinned 6 pooled DB connections (fixed by scoping the session to one query instead of the connection's lifetime); a binary frame killed the connection with an unhandled `KeyError` (fixed by discarding non-text frames instead of assuming text). Applying the per-user registry keying surfaced and fixed a real race: swapping in a new connection had to happen before awaiting the old one's close, not after, or a concurrent broadcast could hit the stale, already-closing socket and be silently dropped — caught by `test_second_connection_for_a_user_replaces_the_first`. Full regression after patching: backend 123 passed (up from 116), frontend 47 passed (up from 40). |
