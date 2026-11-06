"""Resolve the LLM endpoint per request, with `.env` as the fallback.

The plugin may send its own OpenAI-compatible endpoint, key, and model as
headers. Requests without those headers keep using the gateway's `.env`
settings, so the HTTP API stays usable on its own.
"""

from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict
from dataclasses import dataclass

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from ltplus.config import Settings

logger = logging.getLogger(__name__)
router = APIRouter()

BASE_URL_HEADER = "X-LLM-Base-URL"
API_KEY_HEADER = "X-LLM-API-Key"
MODEL_HEADER = "X-LLM-Model"
MAX_TOKENS_HEADER = "X-LLM-Max-Tokens"
EFFORT_HEADER = "X-LLM-Reasoning-Effort"

# A typo in the plugin must not ask the model for a million tokens.
MIN_MAX_TOKENS = 256
MAX_MAX_TOKENS = 65536

EFFORT_LEVELS = ("low", "medium", "high")

# Keep a few clients around when the user switches models. Keys include a hash
# of the API key, so changing the key creates a fresh client.
MAX_CACHED_CLIENTS = 8

MODELS_TIMEOUT_SECONDS = 10.0


class LLMConfigError(ValueError):
    """The caller supplied an endpoint the gateway cannot use."""


@dataclass(frozen=True)
class LLMTarget:
    base_url: str
    api_key: str
    model: str
    max_tokens: int | None = None
    reasoning_effort: str | None = None


class ModelsRequest(BaseModel):
    base_url: str
    api_key: str = ""


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def resolve_target(request: Request, settings: Settings) -> LLMTarget:
    """Read the per-request headers, falling back to the gateway settings."""
    base_url = (request.headers.get(BASE_URL_HEADER, "").strip() or settings.llm_base_url).rstrip(
        "/"
    )
    if not base_url.startswith(("http://", "https://")):
        raise LLMConfigError("LLM base URL must start with http:// or https://")

    model = request.headers.get(MODEL_HEADER, "").strip() or settings.llm_model
    if not model:
        raise LLMConfigError("No LLM model configured")

    # A caller that overrides the endpoint owns the key too: an absent key
    # header means "no key", not "use the gateway's .env key".
    api_key = request.headers.get(API_KEY_HEADER, "").strip()
    if not request.headers.get(BASE_URL_HEADER, "").strip():
        api_key = api_key or settings.llm_api_key

    max_tokens: int | None = None
    raw_tokens = request.headers.get(MAX_TOKENS_HEADER, "").strip()
    if raw_tokens:
        try:
            max_tokens = int(raw_tokens)
        except ValueError as exc:
            raise LLMConfigError("LLM max tokens must be a whole number") from exc
        max_tokens = max(MIN_MAX_TOKENS, min(max_tokens, MAX_MAX_TOKENS))

    reasoning_effort = request.headers.get(EFFORT_HEADER, "").strip().lower() or None
    if reasoning_effort is not None and reasoning_effort not in EFFORT_LEVELS:
        raise LLMConfigError("LLM reasoning effort must be low, medium, or high")

    return LLMTarget(
        base_url=base_url,
        api_key=api_key,
        model=model,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
    )


async def resolve_llm(request: Request, settings: Settings) -> tuple[AsyncOpenAI, LLMTarget]:
    """Return a client for this endpoint and the target it belongs to."""
    target = resolve_target(request, settings)

    # The `.env` client is created at startup (and tests replace it). Reuse it
    # whenever the request did not override the endpoint.
    if (
        target.base_url == settings.llm_base_url.rstrip("/")
        and target.api_key == settings.llm_api_key
        and target.model == settings.llm_model
    ):
        return request.app.state.llm, target

    cache: OrderedDict[tuple[str, str], AsyncOpenAI] = request.app.state.llm_clients
    key = (
        target.base_url,
        hashlib.sha256(target.api_key.encode("utf-8")).hexdigest(),
    )
    client = cache.get(key)
    if client is None:
        client = AsyncOpenAI(
            base_url=target.base_url,
            api_key=target.api_key or "none",
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
        cache[key] = client
        while len(cache) > MAX_CACHED_CLIENTS:
            _, oldest = cache.popitem(last=False)
            await oldest.close()
    return client, target


async def close_clients(clients: OrderedDict[tuple[str, str], AsyncOpenAI]) -> None:
    """Close every cached client at shutdown."""
    for client in clients.values():
        await client.close()


@router.post("/llm/models")
async def list_models(request: Request) -> Response:
    """List the models the configured endpoint offers, for the plugin picker."""
    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError):
        return _error(400, "invalid_body", "Request body must be JSON")
    try:
        payload = ModelsRequest.model_validate(body)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = first["loc"][-1] if first["loc"] else "body"
        return _error(400, "invalid_request", f"{field}: {first['msg']}")

    base_url = payload.base_url.strip().rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        return _error(
            400,
            "invalid_base_url",
            "LLM base URL must start with http:// or https://",
        )

    headers = {}
    if payload.api_key:
        headers["Authorization"] = f"Bearer {payload.api_key}"

    try:
        async with httpx.AsyncClient(timeout=MODELS_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{base_url}/models", headers=headers)
    except httpx.TimeoutException:
        return _error(504, "llm_timeout", "The LLM endpoint did not answer in time")
    except httpx.HTTPError:
        return _error(503, "llm_unavailable", "The LLM endpoint is not reachable")

    if response.status_code >= 400:
        logger.warning("model list failed: %s", response.status_code)
        return _error(
            502,
            "llm_error",
            f"The LLM endpoint returned {response.status_code}",
        )

    try:
        payload_json = response.json()
    except ValueError:
        return _error(502, "llm_error", "The LLM endpoint returned invalid JSON")

    data = payload_json.get("data") if isinstance(payload_json, dict) else None
    if not isinstance(data, list):
        return _error(502, "llm_error", "The LLM endpoint returned no model list")

    models = [
        item["id"]
        for item in data
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]
    ]
    return JSONResponse({"models": models})
