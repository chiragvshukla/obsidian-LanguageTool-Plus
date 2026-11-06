"""One place for OpenAI-compatible chat calls.

The rewrite and practice endpoints use the same request shape, schema
fallback, and error mapping. Keeping that here means a change lands once.
"""

from __future__ import annotations

import logging

from openai import APIConnectionError, AsyncOpenAI, BadRequestError
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONObject, ResponseFormatJSONSchema
from pydantic import BaseModel

from ltplus.config import Settings

logger = logging.getLogger(__name__)


def _schema(name: str, model: type[BaseModel]) -> ResponseFormatJSONSchema:
    return {
        "type": "json_schema",
        "json_schema": {"name": name, "schema": model.model_json_schema()},
    }


async def chat_json(
    client: AsyncOpenAI,
    settings: Settings,
    messages: list[ChatCompletionMessageParam],
    name: str,
    model: type[BaseModel],
    temperature: float,
) -> str:
    """Call the endpoint once, falling back to `json_object` when needed."""
    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=temperature,
            max_tokens=settings.llm_max_tokens,
            response_format=_schema(name, model),
        )
    except BadRequestError:
        # Some compatible servers know only json_object (ADR-010).
        fallback: ResponseFormatJSONObject = {"type": "json_object"}
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=temperature,
            max_tokens=settings.llm_max_tokens,
            response_format=fallback,
        )
    return response.choices[0].message.content or ""


def llm_status(exc: Exception) -> tuple[int, str, str]:
    """Map an OpenAI SDK error to the gateway's status, code, and message."""
    if isinstance(exc, BadRequestError):
        logger.warning("LLM rejected the request: %s", exc.status_code)
        return 502, "llm_invalid_request", "The LLM rejected the request"
    if isinstance(exc, APIConnectionError):
        return 503, "llm_unavailable", "The LLM is not reachable"
    logger.warning("LLM status %s", getattr(exc, "status_code", "unknown"))
    return 502, "llm_error", "The LLM returned an error"