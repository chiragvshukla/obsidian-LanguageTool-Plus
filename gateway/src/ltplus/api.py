"""LanguageTool-compatible endpoints.

The request shape mirrors LanguageTool's own `/v2/check`: a form-encoded body
whose `data` field carries the plugin's annotated JSON. That field is forwarded
untouched; only the mode-derived parameters are adjusted.
"""

from __future__ import annotations

import json
import logging
from urllib.parse import parse_qs

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from ltplus.config import Settings
from ltplus.consistency import document_matches
from ltplus.dictionary import load_words
from ltplus.lexicon import LexiconTerm, synthetic_matches
from ltplus.models import Mode

logger = logging.getLogger(__name__)

router = APIRouter()
_LEVELS = ("default", "picky")


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status,
    )


def _relay(upstream: httpx.Response) -> Response:
    """Return LanguageTool's body and status unchanged."""
    return Response(
        upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _request_text(params: dict[str, str]) -> str | None:
    """Recover the checked text from `text` or the plugin's `data` JSON."""
    if "text" in params:
        return params["text"]

    raw = params.get("data")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    text = data.get("text")
    if isinstance(text, str):
        return text

    annotation = data.get("annotation")
    if not isinstance(annotation, list):
        return None

    parts: list[str] = []
    for item in annotation:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
        else:
            return None
    return "".join(parts)


def _is_known_word(match: object, utf16: bytes, words: set[str]) -> bool:
    """True when the match covers a word from the personal dictionary."""
    if not words or not isinstance(match, dict):
        return False
    offset = match.get("offset")
    length = match.get("length")
    if not isinstance(offset, int) or not isinstance(length, int):
        return False
    span = utf16[offset * 2 : (offset + length) * 2].decode("utf-16-le", "ignore")
    return span.strip().casefold() in words


def _offset(match: object) -> int:
    if isinstance(match, dict):
        offset = match.get("offset")
        if isinstance(offset, int):
            return offset
    return 0


def _allowed_terms(terms: list[LexiconTerm], params: dict[str, str]) -> list[LexiconTerm]:
    """Drop terms the client disabled or did not enable under `enabledOnly`."""
    return [term for term in terms if _client_allows(term.id.upper(), params)]


def _client_allows(rule_id: str, params: dict[str, str]) -> bool:
    disabled_categories = set(_csv(params.get("disabledCategories")))
    disabled_rules = set(_csv(params.get("disabledRules")))
    enabled_categories = set(_csv(params.get("enabledCategories")))
    enabled_rules = set(_csv(params.get("enabledRules")))
    enabled_only = params.get("enabledOnly", "").lower() == "true"

    if "LT_PLUS" in disabled_categories or rule_id in disabled_rules:
        return False
    return not (
        enabled_only and "LT_PLUS" not in enabled_categories and rule_id not in enabled_rules
    )


def merge_categories(
    client_enabled: list[str], client_disabled: list[str], mode: Mode
) -> tuple[list[str], list[str]]:
    """Combine client and mode settings: the most restrictive wins."""
    if client_enabled and mode.enabled_categories:
        enabled = sorted(set(client_enabled) & set(mode.enabled_categories))
    else:
        enabled = sorted(set(client_enabled) | set(mode.enabled_categories))

    disabled = sorted(set(client_disabled) | set(mode.disabled_categories))
    # A category explicitly disabled on either side must never be re-enabled.
    enabled = [item for item in enabled if item not in set(disabled)]
    return enabled, disabled


def merge_level(client_level: str, mode: Mode) -> str:
    """`picky` wins if either side asks for it."""
    if client_level not in _LEVELS:
        client_level = "default"
    return "picky" if "picky" in (client_level, mode.level) else "default"


def merge_rules(
    client_enabled: list[str], client_disabled: list[str], mode: Mode
) -> tuple[list[str], list[str]]:
    """Rules a mode adds are enabled; any client disable still wins."""
    enabled = sorted(set(client_enabled) | set(mode.enabled_rules))
    disabled = sorted(set(client_disabled) | set(mode.disabled_rules))
    enabled = [item for item in enabled if item not in set(disabled)]
    return enabled, disabled


def _apply_mode(params: dict[str, str], mode: Mode) -> None:
    params["level"] = merge_level(params.get("level", "default"), mode)

    if params.get("enabledOnly", "").lower() == "true":
        # LanguageTool rejects disabled lists here, and an explicit client
        # subset must not be widened or narrowed by the mode (ADR-011).
        params.pop("disabledCategories", None)
        params.pop("disabledRules", None)
        return

    enabled, disabled = merge_categories(
        _csv(params.get("enabledCategories")),
        _csv(params.get("disabledCategories")),
        mode,
    )
    if enabled:
        params["enabledCategories"] = ",".join(enabled)
    else:
        params.pop("enabledCategories", None)
    if disabled:
        params["disabledCategories"] = ",".join(disabled)
    else:
        params.pop("disabledCategories", None)

    enabled_rules, disabled_rules = merge_rules(
        _csv(params.get("enabledRules")),
        _csv(params.get("disabledRules")),
        mode,
    )
    if enabled_rules:
        params["enabledRules"] = ",".join(enabled_rules)
    else:
        params.pop("enabledRules", None)
    if disabled_rules:
        params["disabledRules"] = ",".join(disabled_rules)
    else:
        params.pop("disabledRules", None)


def _upstream_error(exc: httpx.HTTPError) -> JSONResponse:
    if isinstance(exc, httpx.TimeoutException):
        return _error(504, "languagetool_timeout", "LanguageTool did not answer in time")
    return _error(503, "languagetool_unavailable", "LanguageTool is not reachable")


@router.get("/v2/languages")
async def languages(request: Request) -> Response:
    """Proxy the language list so settings dropdowns work unchanged."""
    try:
        upstream = await request.app.state.lt.get("/v2/languages")
    except httpx.HTTPError as exc:
        logger.warning("languages request failed: %s", type(exc).__name__)
        return _upstream_error(exc)

    if upstream.status_code >= 500:
        logger.warning("languages upstream status %s", upstream.status_code)
        return _error(502, "languagetool_error", "LanguageTool failed")
    return _relay(upstream)


@router.post("/v2/check")
async def check(request: Request) -> Response:
    """Check text through LanguageTool, with the writing mode applied."""
    settings: Settings = request.app.state.settings
    modes: dict[str, Mode] = request.app.state.modes

    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("application/x-www-form-urlencoded"):
        return _error(415, "unsupported_media_type", "Expected a form-urlencoded request body")

    try:
        body = (await request.body()).decode("utf-8")
    except UnicodeDecodeError:
        return _error(400, "invalid_body", "Request body must be UTF-8")
    parsed = parse_qs(body, keep_blank_values=True)
    params = {key: values[-1] for key, values in parsed.items()}

    mode_id = params.pop("writing_mode", "") or settings.default_mode
    mode = modes.get(mode_id)
    if mode is None:
        return _error(400, "unknown_mode", f"Unknown mode: {mode_id}")

    params.setdefault("language", settings.default_language)
    _apply_mode(params, mode)

    try:
        upstream = await request.app.state.lt.post("/v2/check", data=params)
    except httpx.HTTPError as exc:
        logger.warning("check request failed: %s", type(exc).__name__)
        return _upstream_error(exc)

    if upstream.status_code >= 500:
        logger.warning("check upstream status %s", upstream.status_code)
        return _error(502, "languagetool_error", "LanguageTool failed")

    text = _request_text(params)
    if text is None:
        return _relay(upstream)

    try:
        payload = upstream.json()
    except ValueError:
        return _relay(upstream)
    if not isinstance(payload, dict) or not isinstance(payload.get("matches"), list):
        return _relay(upstream)

    language = params["language"]
    words = load_words(settings.dictionary_dir, language)
    utf16 = text.encode("utf-16-le")
    payload["matches"] = [
        match for match in payload["matches"] if not _is_known_word(match, utf16, words)
    ]
    terms = _allowed_terms(request.app.state.lexicon, params)
    payload["matches"].extend(synthetic_matches(terms, text, language, mode.id))
    for match in document_matches(terms, text, language, mode.id):
        rule = match["rule"]
        if isinstance(rule, dict) and _client_allows(str(rule.get("id", "")), params):
            payload["matches"].append(match)
    payload["matches"].sort(key=_offset)
    return JSONResponse(payload)
