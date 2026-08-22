import json
from typing import Any

from openai import AsyncOpenAI


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
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def generate_recipe(self, prompt: str) -> dict[str, Any]:
        """Request a structured recipe suggestion from the configured model.

        Uses Chat Completions' JSON mode (`response_format={"type": "json_object"}`) rather than
        manually extracting JSON from free-form text, the reliable, well-supported way to get a
        parseable structured response. Any failure (network error, API error, unparseable
        content) propagates to the caller as-is — this method's job is the API call and parsing,
        not deciding what a failure means to the rest of the app; `AIService` (its only caller)
        translates any exception here into FR-21's graceful-degradation path.

        Args:
            prompt: The full prompt to send, already including the stock snapshot and any
                Cook-supplied direction.

        Returns:
            The parsed JSON response as a dict, expected to have "name", "ingredients", and
            "plating" keys (not validated here — the caller validates shape).

        Raises:
            Exception: Any exception raised by the OpenAI SDK (rate limit, auth, timeout, etc.),
                or `json.JSONDecodeError` if the response content is not valid JSON.
        """
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        return json.loads(content)
