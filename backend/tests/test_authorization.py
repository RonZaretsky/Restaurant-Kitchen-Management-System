import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_current_user, require_role
from data_models import User, UserRole
from exceptions import AuthError, ForbiddenError, NotAuthenticatedError
from exceptions.handlers import _auth_error_handler, _forbidden_error_handler
from main import app as production_app

FORBIDDEN_DETAIL = "You do not have permission to perform this action"


def _build_user(role: UserRole) -> User:
    # Arrange helper: a plain in-memory User, no DB needed for role checks
    return User(
        id=1,
        username="someone",
        password_hash="irrelevant",
        full_name="Someone",
        role=role,
        is_active=True,
    )


def _build_guarded_app(*allowed: UserRole) -> tuple[FastAPI, dict[str, bool]]:
    # Arrange helper: a throwaway app carrying one route actually gated by
    # require_role, plus a flag the test reads to prove whether the route body ran.
    # Mounting the guard on a real route is the point: it forces FastAPI to resolve
    # require_role through its dependency graph, which is the only way the
    # CurrentUserDep composition and the ordering against get_current_user get
    # exercised. Calling the returned closure directly proves neither.
    test_app = FastAPI()
    test_app.add_exception_handler(ForbiddenError, _forbidden_error_handler)
    test_app.add_exception_handler(AuthError, _auth_error_handler)
    body_ran = {"value": False}

    @test_app.get("/guarded")
    async def _guarded(user: User = Depends(require_role(*allowed))) -> dict[str, str]:
        body_ran["value"] = True
        return {"role": user.role.value}

    return test_app, body_ran


async def _get(test_app: FastAPI) -> tuple[int, dict]:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/guarded")
    return response.status_code, response.json()


def test_forbidden_error_detail_survives_a_raise_and_catch() -> None:
    # Act
    with pytest.raises(ForbiddenError) as caught:
        raise ForbiddenError()

    # Assert
    assert caught.value.detail == FORBIDDEN_DETAIL


def test_require_role_rejects_arguments_that_are_not_roles() -> None:
    # Arrange
    # UserRole is a plain Enum, so UserRole.admin == "admin" is False. Without this
    # guard, require_role("admin") builds a dependency that denies real admins with
    # no error anywhere, and no linter or CI exists in this project to catch it.
    cases = ["admin", [UserRole.admin], None, 1]

    # Act / Assert
    for bad in cases:
        with pytest.raises(TypeError):
            require_role(bad)


@pytest.mark.parametrize("role", list(UserRole))
@pytest.mark.asyncio
async def test_require_role_permits_the_role_it_allows(role: UserRole) -> None:
    # Arrange
    checker = require_role(role)
    user = _build_user(role)

    # Act
    result = await checker(user)

    # Assert
    assert result is user


@pytest.mark.parametrize("role", list(UserRole))
@pytest.mark.asyncio
async def test_require_role_rejects_every_other_role(role: UserRole) -> None:
    # Arrange
    others = [other for other in UserRole if other is not role]
    checker = require_role(role)

    # Act / Assert
    for other in others:
        with pytest.raises(ForbiddenError):
            await checker(_build_user(other))


@pytest.mark.asyncio
async def test_require_role_permits_any_of_multiple_allowed_roles() -> None:
    # Arrange
    checker = require_role(UserRole.waiter, UserRole.cook, UserRole.admin)

    # Act / Assert
    for role in (UserRole.waiter, UserRole.cook, UserRole.admin):
        assert (await checker(_build_user(role))).role is role


@pytest.mark.parametrize("role", list(UserRole))
@pytest.mark.asyncio
async def test_require_role_with_no_roles_rejects_every_role(role: UserRole) -> None:
    # Arrange
    checker = require_role()

    # Act / Assert
    with pytest.raises(ForbiddenError):
        await checker(_build_user(role))


@pytest.mark.asyncio
async def test_guarded_route_admits_a_permitted_role() -> None:
    # Arrange
    test_app, body_ran = _build_guarded_app(UserRole.admin)
    test_app.dependency_overrides[get_current_user] = lambda: _build_user(UserRole.admin)

    # Act
    status, body = await _get(test_app)

    # Assert
    assert status == 200
    assert body == {"role": "admin"}
    assert body_ran["value"] is True


@pytest.mark.parametrize("role", [UserRole.waiter, UserRole.cook, UserRole.warehouse_manager])
@pytest.mark.asyncio
async def test_guarded_route_returns_403_and_never_runs_the_body(role: UserRole) -> None:
    # Arrange
    test_app, body_ran = _build_guarded_app(UserRole.admin)
    test_app.dependency_overrides[get_current_user] = lambda: _build_user(role)

    # Act
    status, body = await _get(test_app)

    # Assert
    assert status == 403
    assert body == {"detail": FORBIDDEN_DETAIL}
    # AC1's second half: the action must not execute, not merely report 403.
    assert body_ran["value"] is False


@pytest.mark.asyncio
async def test_guarded_route_returns_401_before_the_role_check_runs() -> None:
    # Arrange
    # An unauthenticated caller must be rejected by get_current_user, one layer
    # above the role check, and must never be told 403 (which would imply a
    # verified identity). This also pins the ordering AC2 rests on.
    test_app, body_ran = _build_guarded_app(UserRole.admin)

    async def _unauthenticated() -> User:
        raise NotAuthenticatedError()

    test_app.dependency_overrides[get_current_user] = _unauthenticated

    # Act
    status, body = await _get(test_app)

    # Assert
    assert status == 401
    assert body == {"detail": "Not authenticated"}
    assert body_ran["value"] is False


@pytest.mark.asyncio
async def test_role_guard_resolves_through_the_shared_get_current_user_seam() -> None:
    # Arrange
    # AD-3/AC4: require_role must layer on the one shared dependency, never
    # re-derive a user. Overriding get_current_user can only take effect if it is
    # genuinely a sub-dependency of the guarded route, so an override that fires
    # is proof of the composition. Annotating _check_role's parameter as a plain
    # User instead of CurrentUserDep makes route registration raise FastAPIError.
    test_app, _ = _build_guarded_app(UserRole.admin)
    calls: list[str] = []

    def _tracked_user() -> User:
        calls.append("resolved")
        return _build_user(UserRole.admin)

    test_app.dependency_overrides[get_current_user] = _tracked_user

    # Act
    status, _body = await _get(test_app)

    # Assert
    assert status == 200
    assert calls == ["resolved"]


def test_production_app_registers_the_forbidden_handler() -> None:
    # Arrange / Act
    # Without this, deleting the register_exception_handlers(app) call in main.py's
    # create_app() turns every role denial into a 500 while the rest of this file
    # stays green, since every other test here builds its own throwaway app.
    handler = production_app.exception_handlers.get(ForbiddenError)

    # Assert
    assert handler is _forbidden_error_handler
