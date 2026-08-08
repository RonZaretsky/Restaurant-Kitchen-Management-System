from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import User
from exceptions import InvalidCredentialsError

_JWT_ALGORITHM = "HS256"
_COOKIE_NAME = "access_token"


class AuthService:
    """Authenticates staff logins and issues/verifies JWT session cookies.

    Config-driven only (secret key, token expiry), so it is registered as a
    container-level Factory. Per-request state such as the DB session is
    passed into each method as an argument, never held on the instance.
    """

    def __init__(self, secret_key: str, token_expiry_hours: int) -> None:
        """Initialize the service.

        Args:
            secret_key: The symmetric key used to sign and verify JWTs.
            token_expiry_hours: How many hours a token remains valid.
        """
        self._secret_key = secret_key
        self.token_expiry_hours = token_expiry_hours

    async def authenticate(self, db: AsyncSession, username: str, password: str) -> User:
        """Verify a username/password pair against the stored User record.

        Args:
            db: The active database session.
            username: The submitted username.
            password: The submitted plaintext password. Never logged.

        Returns:
            The matching, active User.

        Raises:
            InvalidCredentialsError: If no User matches the username, the
                User is deactivated, or the password does not match the
                stored bcrypt hash. All three cases raise identically so the
                caller cannot distinguish which one occurred.
        """
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            raise InvalidCredentialsError()

        if not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
            raise InvalidCredentialsError()

        return user

    def create_access_token(self, user: User) -> str:
        """Build a signed JWT identifying the given User's session.

        Args:
            user: The authenticated User to encode a session for.

        Returns:
            A JWT string carrying the user's id and role, expiring after
            the configured number of hours.
        """
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self.token_expiry_hours)
        payload = {
            "sub": str(user.id),
            "role": user.role.value,
            "exp": expires_at,
        }
        return jwt.encode(payload, self._secret_key, algorithm=_JWT_ALGORITHM)

    async def get_current_user(self, request: Request, db: AsyncSession) -> User:
        """Resolve the authenticated User from the request's session cookie.

        This is the one shared dependency every protected route depends on,
        per AD-3. It must never be reimplemented per-route.

        Args:
            request: The incoming request, read for its session cookie.
            db: The active database session.

        Returns:
            The User identified by the cookie's JWT.

        Raises:
            InvalidCredentialsError: If the cookie is missing, the token is
                malformed, expired, or signed with the wrong key, or the
                User it names no longer exists or is deactivated.
        """
        token = request.cookies.get(_COOKIE_NAME)
        if token is None:
            raise InvalidCredentialsError()

        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[_JWT_ALGORITHM])
        except jwt.PyJWTError as exc:
            raise InvalidCredentialsError() from exc

        result = await db.execute(select(User).where(User.id == int(payload["sub"])))
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            raise InvalidCredentialsError()

        return user
