from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import CreateUserRequest, UpdateUserRequest, User, UserRole
from exceptions import DuplicateUsernameError, LastAdminLockoutError, UserNotFoundError
from services.auth_service import AuthService


class UserService:
    """Creates, edits, deactivates, and reactivates staff User accounts.

    Config-free, so it is registered as a container-level Factory with only
    the logger injected. Per-request state such as the DB session is passed
    into each method as an argument, never held on the instance, matching
    AuthService's shape.
    """

    def __init__(self, logger: Any) -> None:
        """Initialize the service.

        Args:
            logger: The loguru logger injected from the container.
        """
        self._logger = logger

    async def create_user(self, db: AsyncSession, actor: User, payload: CreateUserRequest) -> User:
        """Create a new User account with an Admin-assigned initial password.

        Args:
            db: The active database session.
            actor: The Admin performing the creation, used only for logging.
            payload: The submitted username, full name, role, and password.

        Returns:
            The newly created, active User.

        Raises:
            DuplicateUsernameError: If the username already exists, active or
                deactivated, compared without regard to case.
        """
        existing = await db.execute(
            select(User).where(func.lower(User.username) == payload.username.lower())
        )
        if existing.scalar_one_or_none() is not None:
            self._logger.warning(
                "User creation rejected by admin_id={}: username={} already exists",
                actor.id,
                payload.username,
            )
            raise DuplicateUsernameError()

        user = User(
            username=payload.username,
            password_hash=AuthService.hash_password(payload.password),
            full_name=payload.full_name,
            role=payload.role,
            is_active=True,
        )
        db.add(user)
        try:
            await db.commit()
        except IntegrityError as exc:
            # The check above loses to a concurrent create of the same username.
            # The unique index is the real arbiter, so translate its violation
            # into the same 409 rather than letting it surface as a 500.
            await db.rollback()
            self._logger.warning(
                "User creation rejected by admin_id={}: username={} already exists (lost the race)",
                actor.id,
                payload.username,
            )
            raise DuplicateUsernameError() from exc
        await db.refresh(user)
        self._logger.info(
            "User created by admin_id={}: user_id={} username={} role={}",
            actor.id,
            user.id,
            user.username,
            user.role.value,
        )
        return user

    async def list_users(self, db: AsyncSession) -> Sequence[User]:
        """List every User account, active and deactivated alike.

        Args:
            db: The active database session.

        Returns:
            Every User row, in id order.
        """
        result = await db.execute(select(User).order_by(User.id))
        return result.scalars().all()

    async def get_user(self, db: AsyncSession, actor: User, user_id: int) -> User:
        """Fetch a single User by id.

        Every by-id admin route funnels its 404 through here, so this is the
        most-travelled rejection path in the service and logs like the others.

        Args:
            db: The active database session.
            actor: The Admin performing the lookup, used only for logging.
            user_id: The id of the User to fetch.

        Returns:
            The matching User.

        Raises:
            UserNotFoundError: If no User matches user_id.
        """
        user = await db.get(User, user_id)
        if user is None:
            self._logger.warning(
                "Admin action rejected for admin_id={}: no user with user_id={}",
                actor.id,
                user_id,
            )
            raise UserNotFoundError()
        return user

    async def update_user(
        self, db: AsyncSession, actor: User, user_id: int, payload: UpdateUserRequest
    ) -> User:
        """Edit a User's full name and/or Role.

        Args:
            db: The active database session.
            actor: The Admin performing the edit, used only for logging.
            user_id: The id of the User to edit.
            payload: The fields to change. At least one is always set,
                enforced by UpdateUserRequest's own validation.

        Returns:
            The updated User.

        Raises:
            UserNotFoundError: If no User matches user_id.
            LastAdminLockoutError: If the edit would demote the last active
                Admin to a different Role.
        """
        user = await self.get_user(db, actor, user_id)

        changed = False

        if payload.role is not None and payload.role != user.role:
            if user.role == UserRole.admin and user.is_active:
                await self._reject_if_last_active_admin(db, user, actor, action="demoted")
            user.role = payload.role
            changed = True

        if payload.full_name is not None and payload.full_name != user.full_name:
            user.full_name = payload.full_name
            changed = True

        # An edit submitting the values already stored is not a state change, and
        # the audit log must not claim one. The log line is the only record this
        # service produces of who changed what.
        if not changed:
            return user

        await db.commit()
        await db.refresh(user)
        self._logger.info(
            "User updated by admin_id={}: user_id={} full_name={} role={}",
            actor.id,
            user.id,
            user.full_name,
            user.role.value,
        )
        return user

    async def deactivate_user(self, db: AsyncSession, actor: User, user_id: int) -> User:
        """Deactivate an active User, blocking further logins.

        Historical records referencing this User are untouched: deactivation
        only flips is_active, it never deletes or reassigns the row.

        Args:
            db: The active database session.
            actor: The Admin performing the deactivation, used only for
                logging.
            user_id: The id of the User to deactivate.

        Returns:
            The deactivated User.

        Raises:
            UserNotFoundError: If no User matches user_id.
            LastAdminLockoutError: If this User is the last active Admin.
        """
        user = await self.get_user(db, actor, user_id)

        if not user.is_active:
            return user

        if user.role == UserRole.admin:
            await self._reject_if_last_active_admin(db, user, actor, action="deactivated")

        user.is_active = False
        await db.commit()
        await db.refresh(user)
        self._logger.info("User deactivated by admin_id={}: user_id={}", actor.id, user.id)
        return user

    async def reactivate_user(self, db: AsyncSession, actor: User, user_id: int) -> User:
        """Reactivate a previously deactivated User, restoring their login.

        Args:
            db: The active database session.
            actor: The Admin performing the reactivation, used only for
                logging.
            user_id: The id of the User to reactivate.

        Returns:
            The reactivated User.

        Raises:
            UserNotFoundError: If no User matches user_id.
        """
        user = await self.get_user(db, actor, user_id)

        if user.is_active:
            return user

        user.is_active = True
        await db.commit()
        await db.refresh(user)
        self._logger.info("User reactivated by admin_id={}: user_id={}", actor.id, user.id)
        return user

    async def reset_password(
        self, db: AsyncSession, actor: User, user_id: int, new_password: str
    ) -> User:
        """Set a new password on an existing User, overwriting the old hash.

        Never reads or requires the account's previous password. The
        old password stops working immediately since password_hash is
        overwritten, not appended to.

        Args:
            db: The active database session.
            actor: The Admin performing the reset, used only for logging.
            user_id: The id of the User whose password is being reset.
            new_password: The new plaintext password. Never logged.

        Returns:
            The updated User.

        Raises:
            UserNotFoundError: If no User matches user_id.
        """
        user = await self.get_user(db, actor, user_id)
        user.password_hash = AuthService.hash_password(new_password)
        await db.commit()
        await db.refresh(user)
        self._logger.info("Password reset by admin_id={}: user_id={}", actor.id, user.id)
        return user

    async def _reject_if_last_active_admin(
        self, db: AsyncSession, user: User, actor: User, action: str
    ) -> None:
        """Raise LastAdminLockoutError if user is the sole active Admin.

        Args:
            db: The active database session.
            user: The active Admin User about to be deactivated or demoted.
            actor: The Admin attempting the action, used only for logging.
            action: A short past-tense description of the attempted action,
                used only in the log line ("deactivated" or "demoted").

        Returns:
            Nothing, if at least one other active Admin exists.

        Raises:
            LastAdminLockoutError: If user is the only active Admin left.
        """
        # FOR UPDATE, not a bare count. Two admins deactivating each other at the
        # same time would otherwise both read a count of 1, both pass, and both
        # commit, leaving zero active admins and locking everyone out of user
        # management for good. Locking the rows makes the second transaction wait
        # for the first to commit and then re-evaluate against the new state.
        # Ordering by id gives both transactions the same lock order, so they
        # serialize instead of deadlocking.
        locked_admins = await db.execute(
            select(User.id)
            .where(User.role == UserRole.admin, User.is_active.is_(True))
            .order_by(User.id)
            .with_for_update()
        )
        other_active_admin_ids = [
            admin_id for admin_id in locked_admins.scalars().all() if admin_id != user.id
        ]
        if not other_active_admin_ids:
            self._logger.warning(
                "Last-admin lockout: admin_id={} attempted to have user_id={} {} "
                "(the last active Admin)",
                actor.id,
                user.id,
                action,
            )
            raise LastAdminLockoutError()
