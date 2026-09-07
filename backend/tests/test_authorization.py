import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_current_user, require_role
from data_models import User, UserRole
from exceptions import AuthError, ForbiddenError, NotAuthenticatedError
from exceptions.handlers import _auth_error_handler, _forbidden_error_handler

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
    # The action must not execute, not merely report 403.
    assert body_ran["value"] is False


@pytest.mark.asyncio
async def test_guarded_route_returns_401_before_the_role_check_runs() -> None:
    # Arrange
    # An unauthenticated caller must be rejected by get_current_user, one layer
    # above the role check, and must never be told 403 (which would imply a
    # verified identity). This also pins that ordering.
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

