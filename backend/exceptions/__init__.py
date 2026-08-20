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


class OrderNotFoundError(NotFoundError):
    """Raised when a request targets an order_id with no matching row, or a table_id with no
    currently open Order.

    Both cases return the same 404: whether the id is simply wrong, or the Table exists but has
    no Order open on it right now (available, or its Order already closed), the caller has
    nothing to act on either way.
    """

    detail = "Order not found"


class TableNotAvailableError(ConflictError):
    """Raised when opening a Table that is not currently available (AC2).

    Distinct from TableInUseError (Story 2.4), which is specifically about an
    Admin's edit attempt; this is about a Waiter's open attempt. Covers both
    an already-occupied/reserved Table and the race where a second Waiter
    opens the same Table between this request's read and write, the guarded
    UPDATE cannot tell those apart, and both use the same detail, mirroring
    TableInUseError's own precedent.
    """

    detail = "Rejected, table not available"


class DishNotAvailableError(ConflictError):
    """Raised when adding an Order Item for a Dish currently marked unavailable (AC2).

    Distinct from EmptyRecipeError (Story 2.2), which blocks an Admin from making a Dish
    available; this blocks a Waiter from ordering one that already isn't.
    """

    detail = "Rejected, dish unavailable"


class OrderItemNotFoundError(NotFoundError):
    """Raised when no Order Item matches the given id, or it belongs to a different Order."""

    detail = "Order item not found"


class OrderItemNotPendingError(ConflictError):
    """Raised when editing an Order Item that is not currently pending (AC4, Story 3.4).

    The guarded UPDATE cannot distinguish "already in_preparation" from "lost the race between
    this request's read and write", and both use the same detail, mirroring
    TableNotAvailableError's own precedent.
    """

    detail = "Rejected, item not pending"


class OrderItemNotCancellableError(ConflictError):
    """Raised when cancelling an Order Item that is not pending or in_preparation (AC2/AC3, Story 3.4).

    Covers an item already ready or already cancelled, and the race where a second cancel/edit
    lands between this request's read and its guarded UPDATE.
    """

    detail = "Rejected, item not cancellable"


class OrderItemNotInPreparationError(ConflictError):
    """Raised when marking an Order Item ready that is not currently in_preparation (AC4/AC5, Story 5.2).

    Covers a pending item skipping straight to ready, an already-ready item re-triggering the
    transition, and a cancelled item, plus the race where a second transition lands between this
    request's read and its guarded UPDATE.
    """

    detail = "Rejected, item not in preparation"


class OrderNotServableError(ConflictError):
    """Raised when marking an Order served that is not currently ready or pending-with-zero-items
    (AC2, Story 5.4).

    Covers an Order with a non-cancelled item still short of ready, an already-served/closed
    Order re-triggering the transition, and the race where a second transition lands between this
    request's read and its guarded UPDATE. `pending` is included in the guard because, per FR-12,
    an Order is `pending` if and only if it currently has zero non-cancelled Order Items — the
    status column already encodes the "zero items" case, no separate count is needed.
    """

    detail = "Rejected, order is not ready to be served"


class OrderNotClosableError(ConflictError):
    """Raised when closing an Order that is not currently served (AC4, Story 5.4).

    Covers an Order not yet served and an already-closed Order re-triggering the transition, plus
    the race where a second transition lands between this request's read and its guarded UPDATE.
    """

    detail = "Rejected, order is not served yet"


class UnitMismatchError(ConflictError):
    """Raised when a Recipe Ingredient line's unit differs from its Ingredient's own unit.

    Nothing in this system converts between units, so a line recorded in
    liters against an ingredient stocked in kilograms would make Epic 5's
    automatic stock deduction subtract the wrong amount silently. The line
    must be recorded in the unit the ingredient is stocked in.
    """

    detail = "The line's unit must match the ingredient's own unit"
