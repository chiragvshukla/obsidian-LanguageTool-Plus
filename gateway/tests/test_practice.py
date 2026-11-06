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

from ltplus.config import Settings
from ltplus.main import create_app
from ltplus.practice import PromptError, load_practice_prompts

MODES_DIR = Path(__file__).resolve().parents[2] / "modes"
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
CHECK_URL = "http://lt.test/v2/check"

SCORE = {
    "grades": {"clarity": 4, "tone": 3, "vocabulary": 5, "structure": 4},
    "recommendations": ["Shorten the second sentence.", "Name the actor."],
}
TOPIC = {"topic": "Ein Tag im Homeoffice", "angle": "Beschreibe einen typischen Morgen."}


class FakeLLM:
    def __init__(self) -> None:
        self.replies: list[str | Exception] = [json.dumps(SCORE)]
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


def matches(*categories: str) -> dict[str, Any]:
    return {
        "matches": [
            {"rule": {"id": f"RULE_{index}", "category": {"id": category}}}
            for index, category in enumerate(categories)
        ]
    }


@respx.mock
def test_score_combines_facts_with_model_grades(client: TestClient, llm: FakeLLM) -> None:
    respx.post(CHECK_URL).mock(
        return_value=httpx.Response(200, json=matches("GRAMMAR", "GRAMMAR", "STYLE"))
    )

    response = client.post(
        "/score",
        json={"text": "Das ist ein Test. Es fehlt etwas.", "language": "de-DE", "mode": "formal"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["facts"] == {
        "words": 7,
        "sentences": 2,
        "averageSentenceWords": 3.5,
        "ltIssues": [
            {"category": "GRAMMAR", "count": 2},
            {"category": "STYLE", "count": 1},
        ],
    }
    assert body["grades"] == SCORE["grades"]
    assert body["recommendations"] == SCORE["recommendations"]
    assert llm.calls == 1
    assert "formal" in llm.last_messages[1]["content"]


@respx.mock
def test_score_trims_extra_recommendations(client: TestClient, llm: FakeLLM) -> None:
    llm.replies = [
        json.dumps(
            {
                "grades": SCORE["grades"],
                "recommendations": ["one", "two", "three", "four"],
            }
        )
    ]
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    response = client.post("/score", json={"text": "Ein Text.", "language": "de-DE"})

    assert response.status_code == 200
    assert response.json()["recommendations"] == ["one", "two", "three"]


@respx.mock
def test_topic_returns_blockquote_fields(client: TestClient, llm: FakeLLM) -> None:
    llm.replies = [json.dumps(TOPIC)]

    response = client.post("/topic", json={"language": "de-DE", "mode": "casual"})

    assert response.status_code == 200
    assert response.json() == TOPIC
    assert "casual" in llm.last_messages[1]["content"]


def test_score_rejects_unknown_mode(client: TestClient) -> None:
    response = client.post("/score", json={"text": "Text", "mode": "nope"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_mode"


def test_score_rejects_long_text(client: TestClient) -> None:
    response = client.post("/score", json={"text": "x" * 20000})

    assert response.status_code == 413


def test_topic_rejects_unsupported_language(client: TestClient) -> None:
    response = client.post("/topic", json={"language": "fr-FR"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_language"


@respx.mock
def test_score_reports_languagetool_down(client: TestClient) -> None:
    respx.post(CHECK_URL).mock(side_effect=httpx.ConnectError("down"))

    response = client.post("/score", json={"text": "Ein Text."})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "languagetool_unavailable"


@respx.mock
def test_score_reports_llm_down(client: TestClient, llm: FakeLLM) -> None:
    llm.replies = [APIConnectionError(request=httpx.Request("POST", "http://llm.test"))]
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    response = client.post("/score", json={"text": "Ein Text."})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_unavailable"


@respx.mock
def test_score_rejects_invalid_model_output(client: TestClient, llm: FakeLLM) -> None:
    llm.replies = ["not json"]
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    response = client.post("/score", json={"text": "Ein Text."})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "llm_validation_failed"


def test_missing_practice_prompt_fails_loudly(tmp_path: Path) -> None:
    (tmp_path / "de").mkdir()
    (tmp_path / "de" / "score.md").write_text("score", encoding="utf-8")

    with pytest.raises(PromptError):
        load_practice_prompts(tmp_path)