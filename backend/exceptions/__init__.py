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
