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

from ltplus.api import _apply_mode
from ltplus.config import Settings
from ltplus.models import Mode

logger = logging.getLogger(__name__)
router = APIRouter()

# Changes should stay in order and must not overlap. The model gets this right
# most of the time; the applier tolerates the rest instead of failing a check.
MIN_LENGTH_RATIO = 0.5
MAX_LENGTH_RATIO = 2.0

# Above this many changes, validating each one is not worth the LanguageTool
# calls; the whole set is checked once instead.
MAX_SAFE_CHECKS = 12

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
    # Allowed change categories. None means all; an empty list means none.
    categories: list[str] | None = None
    # Read-only surrounding text. Changes must stay inside `text`.
    context_before: str = ""
    context_after: str = ""


# Categories the plugin can show. Anything else is ignored in `categories`.
KNOWN_CATEGORIES = ("grammar", "style", "vocabulary")

# Short definition per category, so the model classifies changes as intended.
CATEGORY_LABELS = {
    "grammar": "spelling, grammar, punctuation",
    "style": "wording, tone, register",
    "vocabulary": "a word written in another language",
}

# (language, mode, instruction, text, categories, context before, context after)
CacheKey = tuple[str, str, str, str, str, str, str]


class RewriteCache:
    """Small in-memory LRU. Nothing is written to disk."""

    def __init__(self, size: int) -> None:
        self._size = max(1, size)
        self._items: OrderedDict[CacheKey, dict[str, Any]] = OrderedDict()

    def get(self, key: CacheKey) -> dict[str, Any] | None:
        value = self._items.get(key)
        if value is not None:
            self._items.move_to_end(key)
        return value

    def put(self, key: CacheKey, value: dict[str, Any]) -> None:
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


def _user_message(
    text: str,
    instruction: str,
    categories: list[str] | None = None,
    context_before: str = "",
    context_after: str = "",
) -> str:
    message = f"Text to revise:\n<<<\n{text}\n>>>"
    if context_before:
        message += f"\n\nContext before (do not revise):\n<<<\n{context_before}\n>>>"
    if context_after:
        message += f"\n\nContext after (do not revise):\n<<<\n{context_after}\n>>>"
    if context_before or context_after:
        message += (
            "\n\nUse the context only to understand the text. Return changes "
            "only for the text to revise."
        )
    if categories is not None:
        allowed = [
            f"{category} ({CATEGORY_LABELS[category]})"
            for category in categories
            if category in KNOWN_CATEGORIES
        ]
        message += (
            "\n\nChange only these categories: "
            f"{'; '.join(allowed)}. Leave everything else as it is, and "
            "keep each change to one category instead of bundling several."
        )
    if instruction:
        message += f"\n\nAdditional instruction: {instruction}"
    return message


def _categories_key(categories: list[str] | None) -> str:
    """Cache key part: requests with different allowed sets must not collide."""
    if categories is None:
        return "*"
    return ",".join(sorted(set(categories) & set(KNOWN_CATEGORIES)))


def _filter_changes(
    changes: list[LLMChange], categories: list[str] | None
) -> list[LLMChange]:
    """Drop changes the client has switched off."""
    if categories is None:
        return changes
    allowed = set(categories) & set(KNOWN_CATEGORIES)
    return [change for change in changes if change.category in allowed]


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
    categories: list[str] | None = None,
    context_before: str = "",
    context_after: str = "",
) -> str:
    """Call the endpoint once. Returns the raw message content."""
    system = prompt
    if strict:
        system += "\n\nReturn only valid JSON. No prose, no code fences."
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": _user_message(
                text, instruction, categories, context_before, context_after
            ),
        },
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


def _apply_changes(
    text: str, changes: list[LLMChange]
) -> tuple[str, list[LLMChange], list[tuple[int, int]]]:
    """Apply non-overlapping changes in text order and report their spans.

    The model sometimes reports a change that contains another change, or lists
    changes out of order. Those are skipped rather than failing the whole
    rewrite. A change whose text is nowhere in the source still fails.
    """
    located: list[tuple[int, int, LLMChange]] = []
    cursor = 0
    for order, change in enumerate(changes):
        index = text.find(change.original, cursor)
        if index < 0:
            index = text.find(change.original)
        if index < 0:
            raise ValidationFailure("a reported change does not match the source text")
        located.append((index, order, change))
        if index >= cursor:
            cursor = index + len(change.original)

    located.sort(key=lambda item: (item[0], item[1]))
    parts: list[str] = []
    spans: list[tuple[int, int]] = []
    kept: list[LLMChange] = []
    cursor = 0
    for index, _, change in located:
        if index < cursor:
            continue  # overlaps a change already applied
        parts.append(text[cursor:index])
        parts.append(change.replacement)
        spans.append((index, len(change.original)))
        kept.append(change)
        cursor = index + len(change.original)
    parts.append(text[cursor:])
    return "".join(parts), kept, spans


def _protected_spans(text: str) -> Counter[str]:
    return Counter(_PROTECTED.findall(text))


def _validate_output(
    text: str, payload: LLMOutput
) -> tuple[str, list[LLMChange], list[tuple[int, int]]]:
    rewritten, changes, spans = _apply_changes(text, payload.changes)

    ratio = len(rewritten) / len(text)
    if not MIN_LENGTH_RATIO <= ratio <= MAX_LENGTH_RATIO:
        raise ValidationFailure("rewritten length is out of range")

    if _protected_spans(text) != _protected_spans(rewritten):
        raise ValidationFailure("numbers, links, or code changed")

    return rewritten, changes, spans


async def _finding_counts(
    lt: httpx.AsyncClient, language: str, mode: Mode, text: str
) -> Counter[str]:
    """Correctness findings per rule id, with the mode's LanguageTool settings.

    Style findings are left out on purpose: a rewrite that reads differently
    may trigger a style hint, but that is not an error the user needs to be
    protected from.
    """
    params = {"text": text, "language": language, "level": mode.level}
    _apply_mode(params, mode)
    response = await lt.post("/v2/check", data=params)
    response.raise_for_status()
    payload = response.json()
    matches = payload.get("matches", []) if isinstance(payload, dict) else []
    counts: Counter[str] = Counter()
    for item in matches:
        if not isinstance(item, dict):
            continue
        rule = item.get("rule")
        if not isinstance(rule, dict) or rule.get("issueType") == "style":
            continue
        counts[str(rule.get("id"))] += 1
    return counts


def _added_findings(before: Counter[str], after: Counter[str]) -> dict[str, int]:
    return {
        rule: count - before.get(rule, 0)
        for rule, count in after.items()
        if count > before.get(rule, 0)
    }


def _added_message(added: dict[str, int]) -> str:
    detail = ", ".join(
        f"{rule} (+{count})" if count > 1 else rule
        for rule, count in sorted(added.items())
    )
    return (
        f"the rewrite would add LanguageTool findings: {detail}. "
        "Nothing was applied."
    )


async def _drop_unsafe_changes(
    lt: httpx.AsyncClient,
    language: str,
    mode: Mode,
    text: str,
    before: Counter[str],
    changes: list[LLMChange],
) -> list[LLMChange] | None:
    """Keep only changes that add no correctness finding on their own.

    Returns None when there are too many changes to test one by one, or when
    every change is safe alone (the failure then comes from their interaction).
    """
    if len(changes) > MAX_SAFE_CHECKS:
        return None
    kept: list[LLMChange] = []
    for change in changes:
        try:
            rewritten, _, _ = _apply_changes(text, [change])
        except ValidationFailure:
            continue
        after = await _finding_counts(lt, language, mode, rewritten)
        if not _added_findings(before, after):
            kept.append(change)
    if len(kept) == len(changes):
        return None
    return kept


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
    if (
        len(payload.text) + len(payload.context_before) + len(payload.context_after)
        > settings.llm_context_chars
    ):
        return _error(
            413,
            "text_too_long",
            f"Text and context exceed {settings.llm_context_chars} characters",
        )

    # Nothing to ask when the client switched every category off.
    if payload.categories is not None and not payload.categories:
        return JSONResponse(
            {"original": payload.text, "rewritten": payload.text, "changes": []}
        )

    key = (
        language,
        mode.id,
        payload.instruction,
        payload.text,
        _categories_key(payload.categories),
        payload.context_before,
        payload.context_after,
    )
    cache: RewriteCache = request.app.state.rewrite_cache
    cached = cache.get(key)
    if cached is not None:
        return JSONResponse(cached)

    client: AsyncOpenAI = request.app.state.llm
    accepted: tuple[str, list[LLMChange], list[tuple[int, int]], int] | None = None
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
                payload.categories,
                payload.context_before,
                payload.context_after,
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
            parsed = LLMOutput(
                changes=_filter_changes(parsed.changes, payload.categories)
            )
            rewritten, changes, spans = _validate_output(payload.text, parsed)
        except (json.JSONDecodeError, ValidationError):
            last_problem = "the response was not valid JSON"
            continue
        except ValidationFailure as exc:
            last_problem = str(exc)
            continue

        lt = request.app.state.lt
        try:
            before = await _finding_counts(lt, language, mode, payload.text)
            after = await _finding_counts(lt, language, mode, rewritten)
            added = _added_findings(before, after)
            if added:
                # Drop the changes that introduce a finding on their own. The
                # rest stays useful instead of failing the whole check.
                safe = await _drop_unsafe_changes(
                    lt, language, mode, payload.text, before, changes
                )
                if safe is None or not safe:
                    last_problem = _added_message(added)
                    continue
                try:
                    rewritten, changes, spans = _validate_output(
                        payload.text, LLMOutput(changes=safe)
                    )
                except ValidationFailure as exc:
                    last_problem = str(exc)
                    continue
                after = await _finding_counts(lt, language, mode, rewritten)
                added = _added_findings(before, after)
                if added:
                    last_problem = _added_message(added)
                    continue
        except httpx.HTTPError:
            return _error(503, "languagetool_unavailable", "LanguageTool is not reachable")
        accepted = (rewritten, changes, spans, len(parsed.changes) - len(changes))
        break

    if accepted is None:
        logger.warning("rewrite rejected: %s", last_problem)
        return _error(502, "llm_validation_failed", last_problem)

    rewritten, changes, spans, dropped = accepted

    result: dict[str, Any] = {
        "original": payload.text,
        "rewritten": rewritten,
        "changes": [
            {**change.model_dump(), "offset": offset, "length": length}
            for change, (offset, length) in zip(changes, spans, strict=True)
        ],
    }
    if dropped:
        result["dropped"] = dropped
    cache.put(key, result)
    return JSONResponse(result)
