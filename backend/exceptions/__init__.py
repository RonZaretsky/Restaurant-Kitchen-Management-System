class InvalidCredentialsError(Exception):
    """Raised when a login attempt fails for any reason.

    Covers an unknown username, a wrong password, and a deactivated user
    alike, so callers can never distinguish which case occurred and no
    endpoint can leak which part of a login attempt was wrong.
    """
