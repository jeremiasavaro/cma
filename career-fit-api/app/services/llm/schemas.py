"""
LLM Schemas - Internal request/response shapes used by LLMClient.

These models are not exposed via the API; they exist to give the LLM
client typed, validated structures instead of passing raw dicts around.
"""

from typing import Any

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    """A single chat message sent to the LLM.

    Mirrors the OpenAI-compatible chat message shape: {"role": ..., "content": ...}.
    """

    role: str = Field(..., description="Message role, e.g. 'system', 'user', 'assistant'")
    content: str = Field(..., description="Message text content")


class CompletionRequest(BaseModel):
    """Internal representation of a chat completion request.

    TODO: confirm which fields the Groq / OpenAI-compatible endpoint actually
    requires vs. optional (e.g. top_p, stop sequences) once the client is implemented.
    """

    messages: list[LLMMessage]
    model: str | None = None
    response_format: dict[str, Any] | None = None
    temperature: float | None = None  # TODO: confirm default comes from app.config settings
    max_tokens: int | None = None  # TODO: confirm default comes from app.config settings


class TokenUsage(BaseModel):
    """Token accounting for a single LLM call, used for cost monitoring."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class CompletionResponse(BaseModel):
    """Internal representation of a chat completion response.

    TODO: extend with provider-specific metadata (finish_reason, latency, etc.)
    once real error handling and retries are implemented.
    """

    content: str
    model: str | None = None
    usage: TokenUsage | None = None


class StructuredOutputRequest(BaseModel):
    """Internal representation of a structured-output request.

    Used by LLMClient.structured_output() to bundle the messages with the
    JSON schema the response must conform to.
    """

    messages: list[LLMMessage]
    schema_: dict[str, Any] = Field(
        ..., alias="schema", description="JSON schema the response must match"
    )
    model: str | None = None
