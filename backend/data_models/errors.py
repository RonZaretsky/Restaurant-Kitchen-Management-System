from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Body of any error response the app returns.

    Every exception handler in main.py emits this shape, so declaring it as
    the response model for a route's error statuses makes the OpenAPI schema
    match what a caller actually receives.
    """

    detail: str
