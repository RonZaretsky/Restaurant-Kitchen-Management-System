from pydantic import BaseModel, Field

from .user import UserRole

# bcrypt refuses anything longer, so a longer submission can never be a real
# credential: no account could have been created with one either.
MAX_PASSWORD_BYTES = 72


class LoginRequest(BaseModel):
    """Body of a login request."""

    # Bounded to keep an oversized body from reaching the hashing path at all.
    # The username bound matches the users.username column width.
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_BYTES)


class LoginResponse(BaseModel):
    """Body of a successful login response."""

    role: UserRole
