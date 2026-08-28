import json
from typing import Any

from openai import AsyncOpenAI

# Bounds how long a single generation can occupy AIService's in-process "in flight" slot for a
# Cook (AD-14) — without this, a hung or very slow OpenAI call would lock that Cook out of ever
# generating again until the process restarts, since nothing else clears the slot (review
# finding). 45s comfortably covers a normal completion while still failing well inside any
# reasonable request timeout on the caller's side.
_REQUEST_TIMEOUT_SECONDS = 45.0


class LLMClient:
    """The only place `openai` is imported in this codebase (AD-12, Story 6.1).

    The first external-service client in the project — `clients/database.py`/`clients/
    websocket.py` are both internal. `services/` depends only on this class's method signatures,
    never on the `openai` package directly, so the integration stays swappable/mockable in tests
    without touching any service. Future Smart Chef calls (Story 6.3's chat) extend this same
    class rather than introducing a second OpenAI client.
    """

    def __init__(self, api_key: str, model: str) -> None:
        """Initialize the client.

        Args:
            api_key: The OpenAI API key, injected from config (never read from
                os.environ directly here — the container is the one place
                config is resolved).
            model: The model name to use for every call this client makes.
        """
        # `AsyncOpenAI(api_key="")` raises immediately at construction (confirmed empirically
        # against the installed SDK) — if that ran eagerly here, a never-configured key would
        # surface as a raw, unhandled error the first time this Singleton is constructed, not
        # FR-21's intended graceful 502 (review finding). Deferring construction until a real
        # call is made means the failure instead happens inside generate_recipe, which
        # AIService already wraps and translates.
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None
        self._model = model

    async def generate_recipe(self, prompt: str) -> dict[str, Any]:
        """Request a structured recipe suggestion from the configured model.

        Uses Chat Completions' JSON mode (`response_format={"type": "json_object"}`) rather than
        manually extracting JSON from free-form text, the reliable, well-supported way to get a
        parseable structured response. Any failure (network error, API error, unparseable
        content) propagates to the caller as-is — this method's job is the API call and parsing,
        not deciding what a failure means to the rest of the app; `AIService` (its only caller)
        translates any exception here into FR-21's graceful-degradation path, and also validates
        the parsed content's shape (this method only guarantees valid JSON, not the expected
        keys).

        Args:
            prompt: The full prompt to send, already including the stock snapshot and any
                Cook-supplied direction.

        Returns:
            The parsed JSON response as a dict, expected to have "name", "ingredients", and
            "plating" keys (not validated here — the caller validates shape).

        Raises:
            RuntimeError: If no API key was configured at construction.
            Exception: Any exception raised by the OpenAI SDK (rate limit, auth, timeout, etc.),
                or `json.JSONDecodeError` if the response content is not valid JSON.
        """
        if self._client is None:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        content = response.choices[0].message.content
        return json.loads(content)

    async def send_chat_message(self, messages: list[dict[str, str]]) -> str:
        """Send a chat conversation to the configured model and return its free-text reply.

        Story 6.3's own extension of this class (per its own docstring above, "future Smart Chef
        calls extend this same class rather than introducing a second OpenAI client", AD-12).
        Same call shape as `generate_recipe`, but no `response_format` (a chat reply is free
        text, not a structured suggestion) and returns the plain string content directly instead
        of parsing it as JSON. Any failure propagates to the caller as-is, same contract as
        `generate_recipe` — this method's job is the API call, not deciding what a failure means;
        `AIService` (its only caller) translates any exception here into FR-21's
        graceful-degradation path.

        Args:
            messages: The full conversation to send, in OpenAI Chat Completions message shape
                (a system message plus the prior turns and the new user message, in order).

        Returns:
            The assistant's free-text reply.

        Raises:
            RuntimeError: If no API key was configured at construction.
            Exception: Any exception raised by the OpenAI SDK (rate limit, auth, timeout, etc.).
        """
        if self._client is None:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        return response.choices[0].message.content

    async def send_chat_message_with_recipe_update(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """Send a chat conversation to the configured model and return a structured envelope
        carrying both a conversational reply and an optional updated recipe.

        Used only for Chat Sessions tied to a Recipe Suggestion (a Dish-tied session stays on
        `send_chat_message`'s free-text contract, unchanged) — a separate method rather than a
        branch inside `send_chat_message`, matching how `generate_recipe`/`send_chat_message` are
        already two separate methods for two different response shapes, keeping each method's
        contract to exactly one shape.

        Same call shape as `send_chat_message`, but with `response_format={"type": "json_object"}`
        added (JSON mode, same mechanism `generate_recipe` already uses) and returning the parsed
        JSON dict directly (`json.loads`, same as `generate_recipe`) rather than a plain string.

        Args:
            messages: The full conversation to send, in OpenAI Chat Completions message shape (a
                system message instructing the JSON envelope shape, plus the prior turns and the
                new user message, in order).

        Returns:
            The parsed JSON response as a dict, expected to have a "reply" string and an
            "updated_recipe" key that is either null or a dict (not validated here — the caller,
            `AIService`, validates shape).

        Raises:
            RuntimeError: If no API key was configured at construction.
            Exception: Any exception raised by the OpenAI SDK (rate limit, auth, timeout, etc.),
                or `json.JSONDecodeError` if the response content is not valid JSON.
        """
        if self._client is None:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            response_format={"type": "json_object"},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        content = response.choices[0].message.content
        return json.loads(content)
