"""Writing practice: quality score and topic prompts.

Both endpoints need the LLM; the deterministic part of `/score` is one
LanguageTool check, so the plugin needs no second request.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from openai import APIConnectionError, APIStatusError, AsyncOpenAI, BadRequestError
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ltplus.api import _apply_mode
from ltplus.config import Settings
from ltplus.llm import chat_json, llm_status
from ltplus.llm_config import LLMConfigError, resolve_llm
from ltplus.models import Mode
from ltplus.rewrite import PromptError

logger = logging.getLogger(__name__)
router = APIRouter()

PRACTICE_PROMPTS = ("score", "score-reduce", "topic")

# One LanguageTool request per 30k characters keeps a long note under the
# default 10s timeout instead of failing the whole score.
LT_CHUNK_CHARS = 30_000


class ScoreGrades(BaseModel):
    model_config = ConfigDict(extra="ignore")

    clarity: int = Field(ge=1, le=5)
    tone: int = Field(ge=1, le=5)
    vocabulary: int = Field(ge=1, le=5)
    structure: int = Field(ge=1, le=5)


class ScoreOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    grades: ScoreGrades
    recommendations: list[str] = Field(default_factory=list)


class TopicOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    topic: str = Field(min_length=1)
    angle: str = ""


class TextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    language: str = "de-DE"
    mode: str | None = None


class PracticeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str = "de-DE"
    mode: str | None = None


def load_practice_prompts(directory: Path) -> dict[tuple[str, str], str]:
    """Load `prompts/<language>/<name>.md`; fail loudly on gaps."""
    if not directory.is_dir():
        raise PromptError(f"prompts directory not found: {directory}")

    prompts: dict[tuple[str, str], str] = {}
    for language_dir in sorted(path for path in directory.iterdir() if path.is_dir()):
        for name in PRACTICE_PROMPTS:
            path = language_dir / f"{name}.md"
            try:
                prompts[(language_dir.name, name)] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise PromptError(f"cannot read {path}: {exc}") from exc
    return prompts


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _mode(request: Request, mode_id: str | None) -> Mode | JSONResponse:
    settings: Settings = request.app.state.settings
    modes: dict[str, Mode] = request.app.state.modes
    selected = mode_id or settings.default_mode
    mode = modes.get(selected)
    if mode is None:
        return _error(400, "unknown_mode", f"Unknown mode: {selected}")
    return mode


def _split_block(block: str, limit: int) -> list[str]:
    """Split an oversized paragraph on sentence ends, then hard at `limit`."""
    pieces: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", block):
        if len(sentence) > limit:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(
                sentence[index : index + limit] for index in range(0, len(sentence), limit)
            )
        elif not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= limit:
            current = f"{current} {sentence}"
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return pieces


def chunk_text(text: str, limit: int) -> list[str]:
    """Split text into sections that never exceed `limit`.

    Paragraph boundaries come first, then sentence boundaries, then a hard
    split so a single unbroken run still fits. The plugin uses the same rules
    in TypeScript for whole-document checks; keep the two in sync.
    """
    if len(text) <= limit:
        return [text]

    pieces: list[str] = []
    for block in (part.strip() for part in re.split(r"\n\s*\n", text)):
        if not block:
            continue
        if len(block) <= limit:
            pieces.append(block)
        else:
            pieces.extend(_split_block(block, limit))

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n\n{piece}" if current else piece
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks or [text]


def _strip_markdown(text: str) -> str:
    """Turn note markup into prose so counts reflect what the reader sees."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"(?m)^\s{0,3}(?:#{1,6}|>|[-*+]\s|\d+\.\s)\s*", "", text)
    text = re.sub(r"[*_~]{1,3}", "", text)
    return text.strip()


def _facts(text: str) -> dict[str, Any]:
    words = len(
        re.findall(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*|\d+(?:[.,]\d+)*", text)  # noqa: RUF001
    )
    # Count a terminator only when a new sentence follows, and remove chains
    # like "z. B." / "i. d. R." first so they do not add sentences.
    without_abbreviations = re.sub(r"(?:\b[A-Za-z]\.\s*){2,}", " ", text)
    sentences = len(re.findall(r"[.!?]+(?=\s+[A-ZÄÖÜ]|\s*$)", without_abbreviations)) or 1
    return {
        "words": words,
        "sentences": sentences,
        "averageSentenceWords": round(words / sentences, 1),
    }


async def _lt_issues(
    lt: httpx.AsyncClient, language: str, mode: Mode, text: str
) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for chunk in chunk_text(text, LT_CHUNK_CHARS):
        params = {"text": chunk, "language": language}
        _apply_mode(params, mode)
        response = await lt.post("/v2/check", data=params)
        response.raise_for_status()
        payload = response.json()
        matches = payload.get("matches", []) if isinstance(payload, dict) else []
        for match in matches:
            if not isinstance(match, dict):
                continue
            category = str(match.get("rule", {}).get("category", {}).get("id", "OTHER"))
            counts[category] = counts.get(category, 0) + 1
    return [
        {"category": category, "count": count}
        for category, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _score_message(
    text: str, language: str, mode: Mode, facts: dict[str, Any], issues: list[dict[str, Any]]
) -> str:
    issue_text = ", ".join(f"{item['category']}: {item['count']}" for item in issues) or "none"
    return (
        f"Text to evaluate:\n<<<\n{text}\n>>>\n\n"
        f"Language: {language}\n"
        f"Writing mode: {mode.id} - {mode.description or mode.label}\n"
        f"Measured facts: {facts['words']} words, {facts['sentences']} sentences, "
        f"{facts['averageSentenceWords']} words per sentence.\n"
        f"LanguageTool findings: {issue_text}.\n\n"
        "Grade clarity, tone fit to the mode, vocabulary, and structure from 1 to 5, "
        "where 5 is best. Base the grades on the text. Use the measured facts and "
        "LanguageTool findings as context but do not invent numbers. Give at most "
        "three concrete recommendations in the text's language. Do not rewrite the text."
    )


def _section_message(text: str, language: str, mode: Mode, index: int, total: int) -> str:
    return (
        f"Text section:\n<<<\n{text}\n>>>\n\n"
        f"Language: {language}\n"
        f"Writing mode: {mode.id} - {mode.description or mode.label}\n"
        f"This is section {index} of {total} of one longer text. Grade this "
        "section on its own: clarity, tone fit to the mode, vocabulary, and "
        "structure from 1 to 5, where 5 is best. Give at most three concrete "
        "recommendations for this section in the text's language. Do not "
        "rewrite the text."
    )


def _reduce_message(
    language: str,
    mode: Mode,
    facts: dict[str, Any],
    issues: list[dict[str, Any]],
    sections: list[ScoreOutput],
) -> str:
    issue_text = ", ".join(f"{item['category']}: {item['count']}" for item in issues) or "none"
    lines = [
        f"Language: {language}",
        f"Writing mode: {mode.id} - {mode.description or mode.label}",
        f"Measured facts for the whole text: {facts['words']} words, "
        f"{facts['sentences']} sentences, {facts['averageSentenceWords']} words per sentence.",
        f"LanguageTool findings: {issue_text}.",
        "Section results:",
    ]
    for index, section in enumerate(sections, start=1):
        grades = ", ".join(f"{key}={value}" for key, value in section.grades.model_dump().items())
        notes = " | ".join(section.recommendations) or "none"
        lines.append(f"{index}. grades: {grades}; notes: {notes}")
    lines.append(
        "Combine these section results into final grades for the whole text and at most "
        "three concrete recommendations in the text's language. Use the measured facts "
        "and LanguageTool findings as context but do not invent numbers. Do not rewrite "
        "the text."
    )
    return "\n".join(lines)


def _topic_message(language: str, mode: Mode) -> str:
    return (
        f"Language: {language}\n"
        f"Writing mode: {mode.id} - {mode.description or mode.label}\n\n"
        "Propose one short everyday practice topic suitable for this mode, plus a "
        "one-sentence angle that says what to focus on. Write both in the text's "
        "language. Keep the topic under 120 characters."
    )


def _parse_score(content: str, label: str) -> ScoreOutput | JSONResponse:
    try:
        return ScoreOutput.model_validate(json.loads(content))
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("%s rejected: %s", label, exc)
        return _error(502, "llm_validation_failed", "The model returned an invalid score")


async def _llm_error(
    client: AsyncOpenAI,
    settings: Settings,
    model_id: str,
    prompt: str,
    user_message: str,
    name: str,
    model: type[BaseModel],
) -> str | JSONResponse:
    messages: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": prompt + "\n\nReturn only valid JSON. No prose, no code fences.",
        },
        {"role": "user", "content": user_message},
    ]
    try:
        return await chat_json(
            client, settings, messages, name, model, temperature=0.2, model_id=model_id
        )
    except (BadRequestError, APIConnectionError, APIStatusError) as exc:
        status, code, message = llm_status(exc)
        return _error(status, code, message)


@router.post("/score")
async def score(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    prompts: dict[tuple[str, str], str] = request.app.state.practice_prompts

    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error(400, "invalid_body", "Request body must be JSON")
    try:
        payload = TextRequest.model_validate(body)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = first["loc"][-1] if first["loc"] else "body"
        return _error(400, "invalid_request", f"{field}: {first['msg']}")

    mode = _mode(request, payload.mode)
    if isinstance(mode, JSONResponse):
        return mode
    language = payload.language.split("-")[0]
    prompt = prompts.get((language, "score"))
    reduce_prompt = prompts.get((language, "score-reduce"))
    if prompt is None or reduce_prompt is None:
        return _error(400, "unsupported_language", f"No score prompt for {payload.language}")

    chunks = chunk_text(payload.text, settings.llm_context_chars)
    if len(chunks) > settings.llm_score_max_chunks:
        return _error(
            413,
            "text_too_long",
            f"Text needs {len(chunks)} sections; the limit is {settings.llm_score_max_chunks}",
        )

    prose = _strip_markdown(payload.text)

    try:
        issues = await _lt_issues(request.app.state.lt, payload.language, mode, prose)
    except httpx.TimeoutException:
        return _error(504, "languagetool_timeout", "LanguageTool did not answer in time")
    except httpx.HTTPError:
        return _error(503, "languagetool_unavailable", "LanguageTool is not reachable")

    facts = _facts(prose)

    try:
        client, target = await resolve_llm(request, settings)
    except LLMConfigError as exc:
        return _error(400, "llm_not_configured", str(exc))

    if len(chunks) == 1:
        content = await _llm_error(
            client,
            settings,
            target.model,
            prompt,
            _score_message(payload.text, payload.language, mode, facts, issues),
            "score",
            ScoreOutput,
        )
        if isinstance(content, JSONResponse):
            return content
        parsed = _parse_score(content, "score")
        if isinstance(parsed, JSONResponse):
            return parsed
    else:
        sections: list[ScoreOutput] = []
        for index, chunk in enumerate(chunks, start=1):
            content = await _llm_error(
                client,
                settings,
                target.model,
                prompt,
                _section_message(chunk, payload.language, mode, index, len(chunks)),
                "score",
                ScoreOutput,
            )
            if isinstance(content, JSONResponse):
                return content
            section = _parse_score(content, f"score section {index}/{len(chunks)}")
            if isinstance(section, JSONResponse):
                return section
            sections.append(section)

        content = await _llm_error(
            client,
            settings,
            target.model,
            reduce_prompt,
            _reduce_message(payload.language, mode, facts, issues, sections),
            "score-reduce",
            ScoreOutput,
        )
        if isinstance(content, JSONResponse):
            return content
        parsed = _parse_score(content, "score reduce")
        if isinstance(parsed, JSONResponse):
            return parsed

    recommendations = [item.strip() for item in parsed.recommendations if item.strip()][:3]
    return JSONResponse(
        {
            "facts": {**facts, "ltIssues": issues},
            "grades": parsed.grades.model_dump(),
            "recommendations": recommendations,
            "chunks": len(chunks),
            "method": "direct" if len(chunks) == 1 else "map_reduce",
        }
    )


@router.post("/topic")
async def topic(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    prompts: dict[tuple[str, str], str] = request.app.state.practice_prompts

    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error(400, "invalid_body", "Request body must be JSON")
    try:
        payload = PracticeRequest.model_validate(body)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = first["loc"][-1] if first["loc"] else "body"
        return _error(400, "invalid_request", f"{field}: {first['msg']}")

    mode = _mode(request, payload.mode)
    if isinstance(mode, JSONResponse):
        return mode
    prompt = prompts.get((payload.language.split("-")[0], "topic"))
    if prompt is None:
        return _error(400, "unsupported_language", f"No topic prompt for {payload.language}")

    try:
        client, target = await resolve_llm(request, settings)
    except LLMConfigError as exc:
        return _error(400, "llm_not_configured", str(exc))

    content = await _llm_error(
        client,
        settings,
        target.model,
        prompt,
        _topic_message(payload.language, mode),
        "topic",
        TopicOutput,
    )
    if isinstance(content, JSONResponse):
        return content

    try:
        parsed = TopicOutput.model_validate(json.loads(content))
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("topic rejected: %s", exc)
        return _error(502, "llm_validation_failed", "The model returned an invalid topic")

    return JSONResponse({"topic": parsed.topic.strip(), "angle": parsed.angle.strip()})
