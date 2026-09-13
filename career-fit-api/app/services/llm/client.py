"""
LLM Client - Provider-agnostic abstraction for all LLM calls.

Decouples business logic (CV extraction, skill normalization, etc.) from the
specific LLM provider, so the provider can be swapped later without touching
callers.
"""


class LLMClient:
    """Provider-agnostic LLM abstraction.

    MVP: targets Groq's OpenAI-compatible chat completions API
    (base URL, API key and model come from app.config.Settings —
    see LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE,
    LLM_MAX_TOKENS, LLM_TIMEOUT).
    Later: swap providers (OpenAI, Anthropic, local models) without touching
    business code.
    """

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        response_format: dict | None = None,
    ) -> str:
        """Send a chat completion request and return the text response.

        Args:
            messages: Chat messages in OpenAI format, e.g. [{"role": "user", "content": "..."}].
            model: Optional model override; defaults to settings.LLM_MODEL.
            response_format: Optional response format hint (e.g. JSON mode).

        Returns:
            The text content of the completion.
        """
        # TODO: implement with httpx + OpenAI-compatible endpoint (settings.LLM_BASE_URL).
        # TODO: add LiteLLM integration as fallback provider.
        # TODO: add retry logic with exponential backoff (see tenacity, already a dependency).
        # TODO: add token usage tracking for cost monitoring (see llm.schemas.TokenUsage).
        # TODO: support streaming responses for long CV parsing.
        ...

    async def structured_output(
        self,
        messages: list[dict],
        schema: dict,
        model: str | None = None,
    ) -> dict:
        """Send a request and parse the response into a dict matching the given JSON schema.

        Args:
            messages: Chat messages in OpenAI format.
            schema: JSON schema the response must conform to.
            model: Optional model override; defaults to settings.LLM_MODEL.

        Returns:
            Parsed response as a dict matching the given schema.
        """
        # TODO: implement with httpx + OpenAI-compatible endpoint, using JSON mode
        # or function calling to enforce the schema.
        # TODO: add LiteLLM integration as fallback provider.
        # TODO: add retry logic with exponential backoff.
        # TODO: add token usage tracking for cost monitoring.
        # TODO: validate the parsed dict against `schema` before returning.
        ...
