import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import MAX_PASSWORD_BYTES, User
from exceptions import InvalidCredentialsError, NotAuthenticatedError, SessionExpiredError

JWT_ALGORITHM = "HS256"
COOKIE_NAME = "access_token"

# A fixed valid hash compared against on the user-miss path so a failed login
# costs the same time whether or not the username exists. Without this the
# response time alone tells an attacker which usernames are real.
_TIMING_EQUALIZATION_HASH = b"$2b$12$YrC4qD.0tLAyEhEzp45ONOrODu5fJI1ATtwA46vrUtwGSINNcsMV6"


class AuthService:
    """Authenticates staff logins and issues/verifies JWT session cookies.

    Config-driven only (secret key, token expiry, logger), so it is
    registered as a container-level Factory. Per-request state such as the
    DB session is passed into each method as an argument, never held on the
    instance.
    """

    def __init__(self, secret_key: str, token_expiry_hours: Any, logger: Any) -> None:
        """Initialize the service.

        Args:
            secret_key: The symmetric key used to sign and verify JWTs.
            token_expiry_hours: How many hours a token remains valid. Coerced
                to int here because config values arrive as raw strings from
                environment substitution.
            logger: The loguru logger injected from the container.

        Raises:
            ValueError: If token_expiry_hours is not a positive whole number.
        """
        self._secret_key = secret_key
        self._logger = logger

        try:
            self.token_expiry_hours = int(token_expiry_hours)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"token_expiry_hours must be a whole number of hours, got {token_expiry_hours!r}"
            ) from exc

        if self.token_expiry_hours <= 0:
            raise ValueError(
                f"token_expiry_hours must be positive, got {self.token_expiry_hours}"
            )

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a plaintext password for storage.

        The single hashing seam for the whole system. Story 1.3 creates and
        resets passwords through this, so cost and salt settings can never
        diverge between account creation and login.

        Args:
            password: The plaintext password to hash. Never logged.

        Returns:
            The bcrypt hash, ready to store in User.password_hash.

        Raises:
            ValueError: If the password is longer than MAX_PASSWORD_BYTES.
        """
        encoded = password.encode("utf-8")
        if len(encoded) > MAX_PASSWORD_BYTES:
            raise ValueError(f"password cannot be longer than {MAX_PASSWORD_BYTES} bytes")
        return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")

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
                User is deactivated, the password is unusably long, the
                stored hash is corrupt, or the password does not match. All
                cases raise identically and take comparable time, so the
                caller cannot distinguish which one occurred.
        """
        # Case-insensitive, matching the uniqueness rule UserService enforces on
        # creation. If login stayed case-sensitive, an account created as "Casey"
        # could never be signed into as "casey" while also blocking "casey" from
        # being created, which is the worst of both.
        result = await db.execute(
            select(User).where(func.lower(User.username) == username.strip().lower())
        )
        user = result.scalar_one_or_none()

        encoded = password.encode("utf-8")
        if len(encoded) > MAX_PASSWORD_BYTES:
            encoded = b""

        if user is None or not user.is_active:
            # Burn the same time a real comparison would, then fail identically.
            await self._verify_password(encoded, _TIMING_EQUALIZATION_HASH)
            self._logger.info("Login rejected for username={}: no active matching account", username)
            raise InvalidCredentialsError()

        if not await self._verify_password(encoded, user.password_hash.encode("utf-8")):
            self._logger.info("Login rejected for user_id={}: password mismatch", user.id)
            raise InvalidCredentialsError()

        self._logger.info("Login succeeded for user_id={} role={}", user.id, user.role.value)
        return user

    @staticmethod
    async def _verify_password(encoded_password: bytes, encoded_hash: bytes) -> bool:
        """Compare a password against a bcrypt hash without blocking the event loop.

        bcrypt is deliberately slow and CPU-bound, so running it inline in an
        async handler would stall every other request on the worker for the
        duration.

        Args:
            encoded_password: The UTF-8 encoded plaintext password.
            encoded_hash: The UTF-8 encoded stored bcrypt hash.

        Returns:
            True if the password matches, False if it does not or if the
            stored hash is not a usable bcrypt hash.
        """
        try:
            return await asyncio.to_thread(bcrypt.checkpw, encoded_password, encoded_hash)
        except ValueError:
            # A corrupt or empty stored hash must fail closed, not 500.
            return False

    def create_access_token(self, user: User) -> str:
        """Build a signed JWT identifying the given User's session.

        Args:
            user: The authenticated User to encode a session for.

        Returns:
            A JWT string carrying the user's id, expiring after the
            configured number of hours.
        """
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self.token_expiry_hours)
        payload = {
            "sub": str(user.id),
            "exp": expires_at,
        }
        return jwt.encode(payload, self._secret_key, algorithm=JWT_ALGORITHM)

    async def get_current_user(self, token: str | None, db: AsyncSession) -> User:
        """Resolve the authenticated User from a session token.

        This is the one shared verification path every protected route
        reaches through api/dependencies.py, per AD-3. It must never be
        reimplemented per-route.

        Args:
            token: The raw JWT from the session cookie, or None if absent.
            db: The active database session.

        Returns:
            The User identified by the token.

        Raises:
            SessionExpiredError: If the token was valid but has expired.
            NotAuthenticatedError: If the token is absent, malformed, signed
                with the wrong key, missing required claims, or names a User
                who no longer exists or has been deactivated.
        """
        if not token:
            raise NotAuthenticatedError()

        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[JWT_ALGORITHM],
                # Without an explicit requirement PyJWT happily accepts a token
                # carrying no exp at all, which would never expire.
                options={"require": ["exp", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise SessionExpiredError() from exc
        except jwt.PyJWTError as exc:
            raise NotAuthenticatedError() from exc

        try:
            user_id = int(payload["sub"])
        except (KeyError, TypeError, ValueError) as exc:
            # A validly signed token can still carry a nonsense sub claim.
            raise NotAuthenticatedError() from exc

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            self._logger.info("Session rejected for user_id={}: account missing or inactive", user_id)
            raise NotAuthenticatedError()

        return user
