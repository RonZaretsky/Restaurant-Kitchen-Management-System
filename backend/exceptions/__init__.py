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


class DuplicateCategoryNameError(ConflictError):
    """Raised when creating a Menu Category with a name that already exists."""

    detail = "That category name already exists"


class EmptyRecipeError(ConflictError):
    """Raised when attempting to mark a Dish available with zero Recipe Ingredient lines.

    AD-8: a Dish must have a defined recipe before it can be ordered, so
    automatic stock deduction is never silently a no-op for a live menu item.
    """

    detail = "Cannot mark available, recipe has no ingredients"


class NotFoundError(Exception):
    """Base for a request that references an id with no matching row.

    One handler in main.py turns any subclass into a 404 carrying that
    subclass's detail, mirroring AuthError/ConflictError's shape.
    """

    detail = "Not found"


class UserNotFoundError(NotFoundError):
    """Raised when an admin action targets a User id that does not exist."""

    detail = "User not found"


class CategoryNotFoundError(NotFoundError):
    """Raised when a request references a category_id that does not exist."""

    detail = "Category not found"


class DishNotFoundError(NotFoundError):
    """Raised when an admin action targets a Dish id that does not exist."""

    detail = "Dish not found"


class IngredientNotFoundError(NotFoundError):
    """Raised when a request references an ingredient_id that does not exist."""

    detail = "Ingredient not found"


class RecipeIngredientNotFoundError(NotFoundError):
    """Raised when a request targets a Dish/Ingredient pair with no existing Recipe Ingredient line."""

    detail = "Recipe ingredient not found"


class DuplicateRecipeIngredientError(ConflictError):
    """Raised when adding a Recipe Ingredient line for an ingredient already on this Dish's recipe.

    The composite primary key (dish_id, ingredient_id) is the real arbiter;
    this turns that constraint violation into a clean 409 instead of a 500.
    """

    detail = "That ingredient is already on this dish's recipe"


class CannotRemoveLastRecipeIngredientError(ConflictError):
    """Raised when removing a Dish's last Recipe Ingredient line while it is available (AD-8, second half)."""

    detail = "Cannot remove the last recipe ingredient while the dish is available"


class DuplicateTableNumberError(ConflictError):
    """Raised when creating or renaming a Table to a table_number that already exists."""

    detail = "Rejected, table number already exists"


class TableInUseError(ConflictError):
    """Raised when editing a Table whose status is not available (AD-6 pattern).

    Covers both an edit attempted while already occupied/reserved, and the race
    where the Table stopped being available between the Admin loading the form
    and saving it. The guarded UPDATE cannot tell those two cases apart, and
    both use the same detail wording.
    """

    detail = "Rejected, table in use"


class TableNotFoundError(NotFoundError):
    """Raised when an admin action targets a table_id that does not exist."""

    detail = "Table not found"


class UnitMismatchError(ConflictError):
    """Raised when a Recipe Ingredient line's unit differs from its Ingredient's own unit.

    Nothing in this system converts between units, so a line recorded in
    liters against an ingredient stocked in kilograms would make Epic 5's
    automatic stock deduction subtract the wrong amount silently. The line
    must be recorded in the unit the ingredient is stocked in.
    """

    detail = "The line's unit must match the ingredient's own unit"
