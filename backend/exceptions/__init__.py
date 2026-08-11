class AuthError(Exception):
    """Base for every authentication failure.

    One handler in main.py turns any subclass into a 401 carrying that
    subclass's `detail`. Keeping the wording on the class means each
    message is defined in exactly one place and cannot drift between call
    sites.
    """

    detail = "Not authenticated"


class InvalidCredentialsError(AuthError):
    """Raised when a login attempt fails for any reason.

    Covers an unknown username, a wrong password, and a deactivated user
    alike, so callers can never distinguish which case occurred and no
    endpoint can leak which part of a login attempt was wrong.
    """

    detail = "Invalid username or password"


class SessionExpiredError(AuthError):
    """Raised when a session token was valid but has passed its expiry.

    Kept separate from InvalidCredentialsError so the frontend can tell a
    user whose shift ended to sign in again, instead of wrongly telling
    them they typed a bad password. This leaks nothing, since only an
    already-authenticated user can reach it.
    """

    detail = "Your session has expired. Please sign in again."


class NotAuthenticatedError(AuthError):
    """Raised when a request carries no usable session token.

    Covers a missing cookie, a malformed or unsigned token, a bad
    signature, and a token naming a user who no longer exists or has been
    deactivated. All of these are indistinguishable to the caller.
    """

    detail = "Not authenticated"


class ForbiddenError(Exception):
    """Raised when an authenticated User's Role is not permitted for the attempted action.

    Distinct from AuthError: the caller's identity is already verified,
    only their Role lacks permission. Maps to 403, never 401.
    """

    detail = "You do not have permission to perform this action"


class ConflictError(Exception):
    """Base for a well-formed request that conflicts with existing state.

    One handler in main.py turns any subclass into a 409 carrying that
    subclass's `detail`.
    """

    detail = "Request conflicts with existing state"


class DuplicateUsernameError(ConflictError):
    """Raised when creating a User with a username that already exists.

    Applies whether the existing account is active or deactivated.
    """

    detail = "That username already exists"


class LastAdminLockoutError(ConflictError):
    """Raised when a mutation would leave zero active Admins in the system.

    Covers both deactivating the last active Admin and demoting them to a
    different Role (AD-15).
    """

    detail = "Rejected, at least one admin must stay active"


class DuplicateIngredientNameError(ConflictError):
    """Raised when creating an Ingredient with a name that already exists.

    Compared case-insensitively (see the functional index on ingredients.name).
    """

    detail = "That ingredient name already exists"


class UserNotFoundError(Exception):
    """Raised when an admin action targets a User id that does not exist."""

    detail = "User not found"
