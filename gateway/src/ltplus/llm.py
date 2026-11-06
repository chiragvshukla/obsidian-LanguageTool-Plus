"""One place for OpenAI-compatible chat calls.

The rewrite and practice endpoints use the same request shape, schema
fallback, and error mapping. Keeping that here means a change lands once.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from openai import APIConnectionError, AsyncOpenAI, BadRequestError
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONObject, ResponseFormatJSONSchema
from pydantic import BaseModel

from ltplus.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMAnswer:
    """One reply, with the metadata needed to explain a bad answer."""

    content: str
    finish_reason: str | None
    has_reasoning: bool


def _answer(response: Any) -> LLMAnswer:
    choice = response.choices[0]
    message = choice.message
    return LLMAnswer(
        content=message.content or "",
        finish_reason=getattr(choice, "finish_reason", None),
        has_reasoning=bool(getattr(message, "reasoning_content", None)),
    )


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
    model_id: str,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
) -> LLMAnswer:
    """Call the endpoint, shedding fields the server rejects.

    Servers vary: some know only `json_object`, and some reject the optional
    `reasoning_effort`. Each fallback is tried once, so a normal call is still
    a single request.
    """
    limit = max_tokens or settings.llm_max_tokens
    schema = _schema(name, model)
    fallback: ResponseFormatJSONObject = {"type": "json_object"}

    attempts: list[tuple[ResponseFormatJSONSchema | ResponseFormatJSONObject, str | None]] = [
        (schema, reasoning_effort)
    ]
    if reasoning_effort:
        attempts.append((schema, None))
    attempts.append((fallback, None))

    last: BadRequestError | None = None
    for response_format, effort in attempts:
        extra = {"reasoning_effort": effort} if effort else None
        try:
            response = await client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=temperature,
                max_tokens=limit,
                response_format=response_format,
                extra_body=extra,
            )
        except BadRequestError as exc:
            last = exc
            continue
        return _answer(response)

    assert last is not None
    raise last


def llm_status(exc: Exception) -> tuple[int, str, str]:
    """Map an OpenAI SDK error to the gateway's status, code, and message."""
    if isinstance(exc, BadRequestError):
        logger.warning("LLM rejected the request: %s", exc.status_code)
        return 502, "llm_invalid_request", "The LLM rejected the request"
    if isinstance(exc, APIConnectionError):
        return 503, "llm_unavailable", "The LLM is not reachable"
    logger.warning("LLM status %s", getattr(exc, "status_code", "unknown"))
    return 502, "llm_error", "The LLM returned an error"
