import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from ltplus.config import Settings
from ltplus.llm_config import LLMConfigError, resolve_target
from ltplus.main import create_app

MODES_DIR = Path(__file__).resolve().parents[2] / "modes"
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
CHECK_URL = "http://lt.test/v2/check"
MODELS_URL = "http://llm.test/v1/models"


class FakeLLM:
    def __init__(self) -> None:
        self.models: list[str] = []
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kwargs: Any) -> Any:
        self.models.append(kwargs["model"])
        content = json.dumps({"changes": []})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    async def close(self) -> None:
        return None


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        lt_url="http://lt.test",
        llm_base_url="http://llm.test/v1",
        llm_api_key="ollama",
        llm_model="default-model",
        modes_dir=MODES_DIR,
        prompts_dir=PROMPTS_DIR,
        default_mode="neutral",
        default_language="de-DE",
    )


@pytest.fixture
def app_client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


def cache_key(base_url: str, api_key: str) -> tuple[str, str]:
    return (base_url, hashlib.sha256(api_key.encode()).hexdigest())


def test_target_falls_back_to_settings(settings: Settings) -> None:
    request = SimpleNamespace(headers={})
    target = resolve_target(request, settings)  # type: ignore[arg-type]
    assert target.base_url == "http://llm.test/v1"
    assert target.model == "default-model"
    assert target.api_key == "ollama"


def test_target_uses_headers(settings: Settings) -> None:
    request = SimpleNamespace(
        headers={
            "X-LLM-Base-URL": "https://sparta.test/v1",
            "X-LLM-API-Key": "secret",
            "X-LLM-Model": "sparta-large",
        }
    )
    target = resolve_target(request, settings)  # type: ignore[arg-type]
    assert target.base_url == "https://sparta.test/v1"
    assert target.api_key == "secret"
    assert target.model == "sparta-large"


def test_target_does_not_leak_env_key_to_a_custom_endpoint(settings: Settings) -> None:
    request = SimpleNamespace(
        headers={"X-LLM-Base-URL": "https://sparta.test/v1", "X-LLM-Model": "m"}
    )
    target = resolve_target(request, settings)  # type: ignore[arg-type]
    assert target.api_key == ""


def test_target_rejects_non_http_url(settings: Settings) -> None:
    request = SimpleNamespace(headers={"X-LLM-Base-URL": "file:///etc/passwd"})
    with pytest.raises(LLMConfigError):
        resolve_target(request, settings)  # type: ignore[arg-type]


def test_target_reads_token_budget_and_effort(settings: Settings) -> None:
    request = SimpleNamespace(
        headers={"X-LLM-Max-Tokens": "8000", "X-LLM-Reasoning-Effort": "HIGH"}
    )
    target = resolve_target(request, settings)  # type: ignore[arg-type]
    assert target.max_tokens == 8000
    assert target.reasoning_effort == "high"


def test_target_clamps_token_budget(settings: Settings) -> None:
    high = resolve_target(  # type: ignore[arg-type]
        SimpleNamespace(headers={"X-LLM-Max-Tokens": "999999"}), settings
    )
    low = resolve_target(  # type: ignore[arg-type]
        SimpleNamespace(headers={"X-LLM-Max-Tokens": "1"}), settings
    )
    assert high.max_tokens == 65536
    assert low.max_tokens == 256


def test_target_rejects_invalid_token_budget(settings: Settings) -> None:
    request = SimpleNamespace(headers={"X-LLM-Max-Tokens": "many"})
    with pytest.raises(LLMConfigError):
        resolve_target(request, settings)  # type: ignore[arg-type]


def test_target_rejects_unknown_effort(settings: Settings) -> None:
    request = SimpleNamespace(headers={"X-LLM-Reasoning-Effort": "extreme"})
    with pytest.raises(LLMConfigError):
        resolve_target(request, settings)  # type: ignore[arg-type]


@respx.mock
def test_model_header_does_not_reuse_cached_rewrite(
    app_client: TestClient, fake_llm: FakeLLM
) -> None:
    app_client.app.state.llm_clients[cache_key("http://llm.test/v1", "secret")] = fake_llm
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))
    body = {"text": "Das ist ein Test.", "language": "de-DE"}
    headers = {"X-LLM-API-Key": "secret"}

    first = app_client.post("/rewrite", json=body, headers={**headers, "X-LLM-Model": "model-a"})
    second = app_client.post("/rewrite", json=body, headers={**headers, "X-LLM-Model": "model-b"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert fake_llm.models == ["model-a", "model-b"]


def test_invalid_base_url_returns_400(app_client: TestClient) -> None:
    response = app_client.post(
        "/rewrite",
        json={"text": "Hallo.", "language": "de-DE"},
        headers={"X-LLM-Base-URL": "ftp://nope"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "llm_not_configured"


@respx.mock
def test_models_listing(app_client: TestClient) -> None:
    route = respx.get(MODELS_URL).mock(
        return_value=httpx.Response(200, json={"data": [{"id": "model-a"}, {"id": "model-b"}]})
    )

    response = app_client.post(
        "/llm/models", json={"base_url": "http://llm.test/v1", "api_key": "secret"}
    )

    assert response.status_code == 200
    assert response.json() == {"models": ["model-a", "model-b"]}
    assert route.calls.last.request.headers["Authorization"] == "Bearer secret"


@respx.mock
def test_models_listing_reports_upstream_error(app_client: TestClient) -> None:
    respx.get(MODELS_URL).mock(return_value=httpx.Response(401))

    response = app_client.post(
        "/llm/models", json={"base_url": "http://llm.test/v1", "api_key": "bad"}
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "llm_error"
