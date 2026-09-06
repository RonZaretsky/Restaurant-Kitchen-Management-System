import enum
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import Boolean, DateTime, Enum, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# bcrypt refuses anything longer, so a longer submission can never be a real
# credential: no account could have been created with one either. Defined here
# rather than in auth.py because auth.py imports UserRole from this module, and
# the schemas below need the constant. Keeping it here makes that dependency
# one-directional.
MAX_PASSWORD_BYTES = 72


class UserRole(enum.Enum):
    admin = "admin"
    waiter = "waiter"
    cook = "cook"
    warehouse_manager = "warehouse_manager"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Declared here as well as in the migration so the drift check in
        # tests/test_migrations.py sees the model and the schema agree.
        Index("uq_users_username_lower", text("lower(username)"), unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _strip_and_require_content(value: str) -> str:
    """Trim surrounding whitespace and reject a value that is blank once trimmed.

    Without this, min_length=1 accepts "   ", which produces an account whose
    username nobody can type and whose display name is empty everywhere.

    Args:
        value: The raw submitted string.

    Returns:
        The trimmed string.

    Raises:
        ValueError: If the string holds nothing but whitespace.
    """
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("must not be blank")
    return trimmed


def _require_hashable_password(value: str) -> str:
    """Reject a password that bcrypt could not hash.

    Pydantic's max_length counts characters while bcrypt's limit is a byte
    budget, so a password of 72 accented or Hebrew characters passes a
    character bound and then raises inside hash_password. Checking bytes here
    turns that into the same 422 every other validation failure produces,
    instead of an unhandled 500.

    Args:
        value: The submitted plaintext password. Never logged.

    Returns:
        The password unchanged.

    Raises:
        ValueError: If the password exceeds MAX_PASSWORD_BYTES when encoded.
    """
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password cannot be longer than {MAX_PASSWORD_BYTES} bytes")
    return value


# Deliberately not bounded by max_length: the byte check below is the real
# limit, and a character bound would reject valid short multi-byte passwords
# while still admitting oversized ones.
PasswordStr = Annotated[str, Field(min_length=1)]


class CreateUserRequest(BaseModel):
    """Body of an Admin's request to create a new User account."""

    username: str = Field(min_length=1, max_length=50)
    full_name: str = Field(min_length=1, max_length=100)
    role: UserRole
    password: PasswordStr

    _strip_username = field_validator("username", "full_name")(_strip_and_require_content)
    _check_password = field_validator("password")(_require_hashable_password)


class UpdateUserRequest(BaseModel):
    """Body of an Admin's request to edit a User's full name and/or Role.

    At least one field must be provided, a request editing nothing is
    rejected rather than silently accepted as a no-op.
    """

    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: UserRole | None = None

    _strip_full_name = field_validator("full_name")(_strip_and_require_content)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UpdateUserRequest":
        """Reject an update that changes neither field.

        Returns:
            This instance, unchanged, if at least one field is set.

        Raises:
            ValueError: If both full_name and role are None.
        """
        if self.full_name is None and self.role is None:
            raise ValueError("at least one of full_name or role must be provided")
        return self


class ResetPasswordRequest(BaseModel):
    """Body of an Admin's request to set a new password on an existing User."""

    new_password: PasswordStr

    _check_password = field_validator("new_password")(_require_hashable_password)


class UserResponse(BaseModel):
    """Body of any admin endpoint response describing a User.

    Never includes password_hash, so a plaintext or hashed password can
    never leak through a read endpoint.
    """

    model_config = {"from_attributes": True}

    id: int
    username: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
