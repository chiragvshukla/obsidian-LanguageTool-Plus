"""LanguageTool-compatible endpoints.

The request shape mirrors LanguageTool's own `/v2/check`: a form-encoded body
whose `data` field carries the plugin's annotated JSON. That field is forwarded
untouched; only the mode-derived parameters are adjusted.
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qs

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from ltplus.config import Settings
from ltplus.models import Mode

logger = logging.getLogger(__name__)

router = APIRouter()
_LEVELS = ("default", "picky")


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status,
    )


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


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


def _apply_mode(params: dict[str, str], mode: Mode) -> None:
    params["level"] = merge_level(params.get("level", "default"), mode)

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

    if upstream.status_code >= 400:
        logger.warning("languages upstream status %s", upstream.status_code)
        return _error(502, "languagetool_error", "LanguageTool rejected the request")
    return Response(upstream.content, media_type="application/json")


@router.post("/v2/check")
async def check(request: Request) -> Response:
    """Check text through LanguageTool, with the writing mode applied."""
    settings: Settings = request.app.state.settings
    modes: dict[str, Mode] = request.app.state.modes

    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("application/x-www-form-urlencoded"):
        return _error(415, "unsupported_media_type", "Expected a form-urlencoded request body")

    parsed = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    params = {key: values[-1] for key, values in parsed.items()}

    mode_id = params.pop("mode", "") or settings.default_mode
    mode = modes.get(mode_id)
    if mode is None:
        return _error(400, "unknown_mode", f"Unknown mode: {mode_id}")

    _apply_mode(params, mode)

    try:
        upstream = await request.app.state.lt.post("/v2/check", data=params)
    except httpx.HTTPError as exc:
        logger.warning("check request failed: %s", type(exc).__name__)
        return _upstream_error(exc)

    if upstream.status_code >= 400:
        logger.warning("check upstream status %s", upstream.status_code)
        return _error(502, "languagetool_error", "LanguageTool rejected the request")
    return Response(upstream.content, media_type="application/json")
