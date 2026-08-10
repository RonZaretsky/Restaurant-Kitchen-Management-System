from typing import Any

from data_models import ErrorResponse


def error_responses(descriptions: dict[int, str], *statuses: int) -> dict[int | str, dict[str, Any]]:
    """Build the OpenAPI `responses` entries for the given error statuses.

    Shared across every domain router. FastAPI's exceptions here are plain
    Exception subclasses rather than HTTPException, so it cannot infer any of
    them and a route would otherwise document only its success case. Each
    entry carries ErrorResponse as its body schema, so a generated client sees
    the `detail` contract and not just a status number.

    Args:
        descriptions: Maps each status code this router can return to the
            human-readable description shown in the OpenAPI docs. Callers own
            their own wording, since it is resource-specific ("no User
            matches" vs. "no Dish matches").
        statuses: The subset of descriptions' keys this particular route can
            return.

    Returns:
        A responses mapping ready to pass to a route decorator.
    """
    return {
        status: {"description": descriptions[status], "model": ErrorResponse}
        for status in statuses
    }
