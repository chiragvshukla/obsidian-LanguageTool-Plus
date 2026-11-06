"""LLM rewrite endpoint.

This is the only module that talks to an OpenAI-compatible server. Inline
checks never import an LLM path: if this module fails or the server is down,
`/v2/check` keeps working.

Every rewrite is validated before it is returned. Unvalidated model text is
never sent to the client.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from openai import APIConnectionError, APIStatusError, AsyncOpenAI, BadRequestError
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONObject, ResponseFormatJSONSchema
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ltplus.config import Settings
from ltplus.models import Mode

logger = logging.getLogger(__name__)
router = APIRouter()

# Changes must stay in order and must not overlap.
MIN_LENGTH_RATIO = 0.5
MAX_LENGTH_RATIO = 2.0

# Spans the model must not alter. Keep this list short and mechanical; names
# are left to the LanguageTool re-check rather than guessed by a tokenizer.
_PROTECTED = re.compile(
    r"```.*?```|`[^`\n]+`|https?://[^\s<>\"']+|[\w.+-]+@[\w-]+\.[\w.-]+|-?\d+(?:[.,]\d+)*%?"
)


class PromptError(RuntimeError):
    """Raised when prompt files are missing or unreadable."""


class ValidationFailure(Exception):
    """The model answered, but its answer did not pass validation."""


class LLMChange(BaseModel):
    model_config = ConfigDict(extra="ignore")

    original: str = Field(min_length=1)
    replacement: str
    category: str = "style"
    explanation: str = ""


class LLMOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    changes: list[LLMChange]


class RewriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    language: str = "de-DE"
    mode: str | None = None
    instruction: str = ""


class RewriteCache:
    """Small in-memory LRU. Nothing is written to disk."""

    def __init__(self, size: int) -> None:
        self._size = max(1, size)
        self._items: OrderedDict[tuple[str, str, str, str], dict[str, Any]] = OrderedDict()

    def get(self, key: tuple[str, str, str, str]) -> dict[str, Any] | None:
        value = self._items.get(key)
        if value is not None:
            self._items.move_to_end(key)
        return value

    def put(self, key: tuple[str, str, str, str], value: dict[str, Any]) -> None:
        self._items[key] = value
        self._items.move_to_end(key)
        while len(self._items) > self._size:
            self._items.popitem(last=False)


def load_prompts(directory: Path, modes: dict[str, Mode]) -> dict[tuple[str, str], str]:
    """Load `prompts/<language>/<mode.prompt>` once. Fail loudly on gaps."""
    if not directory.is_dir():
        raise PromptError(f"prompts directory not found: {directory}")

    languages = sorted(path.name for path in directory.iterdir() if path.is_dir())
    if not languages:
        raise PromptError(f"no language directories in {directory}")

    prompts: dict[tuple[str, str], str] = {}
    for language in languages:
        for mode in modes.values():
            if not mode.prompt:
                continue
            path = directory / language / mode.prompt
            try:
                prompts[(language, mode.id)] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise PromptError(f"cannot read {path}: {exc}") from exc
    return prompts


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _user_message(text: str, instruction: str) -> str:
    message = f"Text to revise:\n<<<\n{text}\n>>>"
    if instruction:
        message += f"\n\nAdditional instruction: {instruction}"
    return message


def _schema() -> ResponseFormatJSONSchema:
    return {
        "type": "json_schema",
        "json_schema": {"name": "rewrite", "schema": LLMOutput.model_json_schema()},
    }


async def _generate(
    client: AsyncOpenAI,
    settings: Settings,
    prompt: str,
    text: str,
    instruction: str,
    temperature: float,
    strict: bool,
) -> str:
    """Call the endpoint once. Returns the raw message content."""
    system = prompt
    if strict:
        system += "\n\nReturn only valid JSON. No prose, no code fences."
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system},
        {"role": "user", "content": _user_message(text, instruction)},
    ]

    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=temperature,
            max_tokens=settings.llm_max_tokens,
            response_format=_schema(),
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


def _apply_changes(text: str, changes: list[LLMChange]) -> tuple[str, list[tuple[int, int]]]:
    """Apply ordered, non-overlapping changes and report their source spans."""
    parts: list[str] = []
    spans: list[tuple[int, int]] = []
    cursor = 0
    for change in changes:
        index = text.find(change.original, cursor)
        if index < 0:
            raise ValidationFailure("a reported change does not match the source text")
        parts.append(text[cursor:index])
        parts.append(change.replacement)
        spans.append((index, len(change.original)))
        cursor = index + len(change.original)
    parts.append(text[cursor:])
    return "".join(parts), spans


def _protected_spans(text: str) -> Counter[str]:
    return Counter(_PROTECTED.findall(text))


def _validate_output(
    text: str, payload: LLMOutput
) -> tuple[str, list[LLMChange], list[tuple[int, int]]]:
    rewritten, spans = _apply_changes(text, payload.changes)

    ratio = len(rewritten) / len(text)
    if not MIN_LENGTH_RATIO <= ratio <= MAX_LENGTH_RATIO:
        raise ValidationFailure("rewritten length is out of range")

    if _protected_spans(text) != _protected_spans(rewritten):
        raise ValidationFailure("numbers, links, or code changed")

    return rewritten, payload.changes, spans


async def _match_ids(lt: httpx.AsyncClient, language: str, text: str) -> set[str]:
    response = await lt.post(
        "/v2/check", data={"text": text, "language": language, "level": "default"}
    )
    response.raise_for_status()
    payload = response.json()
    matches = payload.get("matches", []) if isinstance(payload, dict) else []
    ids = {str(item.get("rule", {}).get("id")) for item in matches if isinstance(item, dict)}
    return ids


async def _new_rule_ids(
    lt: httpx.AsyncClient, language: str, original: str, rewritten: str
) -> set[str]:
    before = await _match_ids(lt, language, original)
    after = await _match_ids(lt, language, rewritten)
    return after - before


@router.post("/rewrite")
async def rewrite(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    modes: dict[str, Mode] = request.app.state.modes

    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error(400, "invalid_body", "Request body must be JSON")
    try:
        payload = RewriteRequest.model_validate(body)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = first["loc"]
        field = location[-1] if location else "body"
        return _error(400, "invalid_request", f"{field}: {first['msg']}")

    mode_id = payload.mode or settings.default_mode
    mode = modes.get(mode_id)
    if mode is None:
        return _error(400, "unknown_mode", f"Unknown mode: {mode_id}")

    language = payload.language
    prompt = request.app.state.prompts.get((language.split("-")[0], mode.id))
    if prompt is None:
        return _error(400, "unsupported_language", f"No rewrite prompt for {language}")

    if len(payload.text) > settings.llm_context_chars:
        return _error(
            413,
            "text_too_long",
            f"Text exceeds {settings.llm_context_chars} characters; select a shorter passage",
        )

    key = (language, mode.id, payload.instruction, payload.text)
    cache: RewriteCache = request.app.state.rewrite_cache
    cached = cache.get(key)
    if cached is not None:
        return JSONResponse(cached)

    client: AsyncOpenAI = request.app.state.llm
    accepted: tuple[str, list[LLMChange], list[tuple[int, int]]] | None = None
    last_problem = ""
    for strict in (False, True):
        try:
            content = await _generate(
                client,
                settings,
                prompt,
                payload.text,
                payload.instruction,
                mode.temperature,
                strict,
            )
        except BadRequestError as exc:
            logger.warning("LLM rejected the request: %s", exc.status_code)
            return _error(502, "llm_invalid_request", "The LLM rejected the request")
        except APIConnectionError:
            return _error(503, "llm_unavailable", "The LLM is not reachable")
        except APIStatusError as exc:
            logger.warning("LLM status %s", exc.status_code)
            return _error(502, "llm_error", "The LLM returned an error")

        try:
            parsed = LLMOutput.model_validate(json.loads(content))
            rewritten, changes, spans = _validate_output(payload.text, parsed)
        except (json.JSONDecodeError, ValidationError):
            last_problem = "the response was not valid JSON"
            continue
        except ValidationFailure as exc:
            last_problem = str(exc)
            continue

        try:
            new_rules = await _new_rule_ids(request.app.state.lt, language, payload.text, rewritten)
        except httpx.HTTPError:
            return _error(503, "languagetool_unavailable", "LanguageTool is not reachable")
        if new_rules:
            last_problem = "the rewrite added LanguageTool errors: " + ", ".join(sorted(new_rules))
            continue
        accepted = (rewritten, changes, spans)
        break

    if accepted is None:
        logger.warning("rewrite rejected: %s", last_problem)
        return _error(502, "llm_validation_failed", last_problem)

    rewritten, changes, spans = accepted

    result = {
        "original": payload.text,
        "rewritten": rewritten,
        "changes": [
            {**change.model_dump(), "offset": offset, "length": length}
            for change, (offset, length) in zip(changes, spans, strict=True)
        ],
    }
    cache.put(key, result)
    return JSONResponse(result)
