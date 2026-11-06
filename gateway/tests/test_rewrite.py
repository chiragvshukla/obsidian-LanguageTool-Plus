import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from openai import APIConnectionError
from pydantic import ValidationError

from ltplus.config import Settings
from ltplus.main import create_app
from ltplus.models import Mode
from ltplus.rewrite import PromptError, load_prompts

MODES_DIR = Path(__file__).resolve().parents[2] / "modes"
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
LLM_URL = "http://llm.test/v1/chat/completions"
CHECK_URL = "http://lt.test/v2/check"


class FakeLLM:
    """Stand-in for AsyncOpenAI: the real SDK uses its own HTTP stack."""

    def __init__(self) -> None:
        self.replies: list[str | Exception] = [json.dumps({"changes": []})]
        self.calls = 0
        self.last_messages: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kwargs: Any) -> Any:
        self.calls += 1
        self.last_messages = kwargs.get("messages", [])
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])

    async def close(self) -> None:
        return None


def completion(*pairs: tuple[str, str]) -> str:
    return json.dumps(
        {
            "changes": [
                {
                    "original": original,
                    "replacement": replacement,
                    "category": "style",
                    "explanation": "test",
                }
                for original, replacement in pairs
            ]
        }
    )


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def client(llm: FakeLLM) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        lt_url="http://lt.test",
        llm_base_url="http://llm.test/v1",
        modes_dir=MODES_DIR,
        prompts_dir=PROMPTS_DIR,
        default_mode="neutral",
        default_language="de-DE",
    )
    with TestClient(create_app(settings)) as test_client:
        test_client.app.state.llm = llm
        yield test_client


def post(client: TestClient, **body: object) -> httpx.Response:
    payload = {"text": "Das ist ein Test.", "language": "de-DE"}
    payload.update(body)
    return client.post("/rewrite", json=payload)


@respx.mock
def test_rewrite_applies_changes(client: TestClient, llm: FakeLLM) -> None:
    llm.replies = [completion(("ist", "war"))]
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    response = post(client)

    assert response.status_code == 200
    assert response.json() == {
        "original": "Das ist ein Test.",
        "rewritten": "Das war ein Test.",
        "changes": [
            {
                "original": "ist",
                "replacement": "war",
                "category": "style",
                "explanation": "test",
                "offset": 4,
                "length": 3,
            }
        ],
    }


@respx.mock
def test_rewrite_reports_source_offsets_for_repeated_spans(
    client: TestClient, llm: FakeLLM
) -> None:
    llm.replies = [completion(("ist", "war"), ("ist", "bleibt"))]
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    response = post(client, text="Das ist gut, das ist schlecht.")

    assert response.status_code == 200
    changes = response.json()["changes"]
    assert [(change["offset"], change["length"]) for change in changes] == [(4, 3), (17, 3)]
    assert response.json()["rewritten"] == "Das war gut, das bleibt schlecht."


@respx.mock
def test_rewrite_retries_invalid_json_once(client: TestClient, llm: FakeLLM) -> None:
    llm.replies = ["not json", completion(("ist", "war"))]
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    response = post(client)

    assert response.status_code == 200
    assert llm.calls == 2


@respx.mock
def test_rewrite_rejects_two_invalid_replies(client: TestClient, llm: FakeLLM) -> None:
    llm.replies = ["not json"]

    response = post(client)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "llm_validation_failed"


@respx.mock
def test_rewrite_rejects_changed_numbers(client: TestClient, llm: FakeLLM) -> None:
    llm.replies = [completion(("3", "4"))]

    response = post(client, text="Es sind 3 Stück.")

    assert response.status_code == 502
    assert "numbers, links, or code changed" in response.json()["error"]["message"]


@respx.mock
def test_rewrite_rejects_new_language_errors(client: TestClient, llm: FakeLLM) -> None:
    llm.replies = [completion(("ist", "war"))]
    new_error = httpx.Response(200, json={"matches": [{"rule": {"id": "NEW_ERROR"}}]})
    clean = httpx.Response(200, json={"matches": []})
    route = respx.post(CHECK_URL).mock(side_effect=[clean, new_error, clean, new_error])

    response = post(client)

    assert response.status_code == 502
    assert "NEW_ERROR" in response.json()["error"]["message"]
    assert route.call_count == 4


@respx.mock
def test_rewrite_reports_unreachable_llm(client: TestClient, llm: FakeLLM) -> None:
    llm.replies = [APIConnectionError(request=httpx.Request("POST", LLM_URL))]

    response = post(client)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_unavailable"


@respx.mock
def test_rewrite_reports_unreachable_languagetool(client: TestClient, llm: FakeLLM) -> None:
    llm.replies = [completion(("ist", "war"))]
    respx.post(CHECK_URL).mock(side_effect=httpx.ConnectError("refused"))

    response = post(client)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "languagetool_unavailable"


@respx.mock
def test_rewrite_is_cached(client: TestClient, llm: FakeLLM) -> None:
    llm.replies = [completion(("ist", "war"))]
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    first = post(client)
    second = post(client)

    assert first.status_code == second.status_code == 200
    assert llm.calls == 1


def test_rewrite_rejects_unknown_mode(client: TestClient) -> None:
    response = post(client, mode="nope")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_mode"


def test_rewrite_rejects_unknown_language(client: TestClient) -> None:
    response = post(client, language="fr-FR")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_language"


def test_rewrite_rejects_missing_text(client: TestClient) -> None:
    response = client.post("/rewrite", json={"language": "de-DE"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_rewrite_rejects_long_text(client: TestClient) -> None:
    response = post(client, text="x" * 12001)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "text_too_long"


def test_prompt_must_be_a_file_name() -> None:
    with pytest.raises(ValidationError, match="prompt must be a file name"):
        Mode(id="test", label="Test", prompt="../evil.md")


def categorized(*items: tuple[str, str, str]) -> str:
    return json.dumps(
        {
            "changes": [
                {
                    "original": original,
                    "replacement": replacement,
                    "category": category,
                    "explanation": "test",
                }
                for original, replacement, category in items
            ]
        }
    )


@respx.mock
def test_rewrite_drops_disabled_categories(client: TestClient, llm: FakeLLM) -> None:
    llm.replies = [
        categorized(("ist", "war", "style"), ("Test", "Versuch", "grammar"))
    ]
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    response = post(client, categories=["grammar"])

    assert response.status_code == 200
    assert response.json()["rewritten"] == "Das ist ein Versuch."
    assert [change["category"] for change in response.json()["changes"]] == ["grammar"]


@respx.mock
def test_rewrite_tells_the_model_which_categories_are_allowed(
    client: TestClient, llm: FakeLLM
) -> None:
    llm.replies = [completion(("ist", "war"))]
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    post(client, categories=["grammar"])

    user_message = llm.last_messages[-1]["content"]
    assert "Change only these categories:" in user_message
    assert "grammar (spelling, grammar, punctuation)" in user_message
    assert "vocabulary (" not in user_message


@respx.mock
def test_rewrite_cache_key_includes_categories(
    client: TestClient, llm: FakeLLM
) -> None:
    llm.replies = [completion(("ist", "war"))]
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    post(client, categories=["grammar"])
    post(client, categories=["grammar", "style"])

    assert llm.calls == 2


def test_rewrite_without_categories_skips_the_model(
    client: TestClient, llm: FakeLLM
) -> None:
    response = post(client, categories=[])

    assert response.status_code == 200
    assert response.json()["changes"] == []
    assert llm.calls == 0


def test_missing_prompt_fails_startup(tmp_path: Path) -> None:
    mode = Mode(id="formal", label="Formal", prompt="formal.md")
    (tmp_path / "de").mkdir()

    with pytest.raises(PromptError, match="cannot read"):
        load_prompts(tmp_path, {"formal": mode})
