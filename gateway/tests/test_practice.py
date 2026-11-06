import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from openai import APIConnectionError

from ltplus.config import Settings
from ltplus.main import create_app
from ltplus.practice import (
    PromptError,
    _facts,
    _strip_markdown,
    chunk_text,
    load_practice_prompts,
)

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
    assert body["chunks"] == 1
    assert body["method"] == "direct"
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


def test_score_rejects_text_beyond_the_chunk_limit(client: TestClient) -> None:
    response = client.post("/score", json={"text": "x" * 100000})

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "text_too_long"


@respx.mock
def test_score_uses_map_reduce_for_long_text(client: TestClient, llm: FakeLLM) -> None:
    text = "Ein Satz. " * 1300
    chunks = chunk_text(text, 12000)
    assert len(chunks) > 1
    section = {
        "grades": {"clarity": 1, "tone": 1, "vocabulary": 1, "structure": 1},
        "recommendations": ["section note"],
    }
    final = {
        "grades": {"clarity": 5, "tone": 4, "vocabulary": 3, "structure": 2},
        "recommendations": ["final one", "final two", "final three", "ignored"],
    }
    llm.replies = [json.dumps(section)] * len(chunks) + [json.dumps(final)]
    route = respx.post(CHECK_URL).mock(
        return_value=httpx.Response(200, json={"matches": []})
    )

    response = client.post("/score", json={"text": text, "language": "de-DE"})

    assert response.status_code == 200
    body = response.json()
    assert body["chunks"] == len(chunks)
    assert body["method"] == "map_reduce"
    assert body["grades"] == final["grades"]
    assert body["recommendations"] == ["final one", "final two", "final three"]
    assert body["facts"]["words"] == len(text.split())
    assert route.call_count == 1
    assert llm.calls == len(chunks) + 1


def test_chunk_text_splits_on_boundaries_within_limit() -> None:
    text = "Erster Satz. Zweiter Satz.\n\nDritter Absatz."

    chunks = chunk_text(text, 25)

    assert chunks
    assert all(chunk.strip() and len(chunk) <= 25 for chunk in chunks)
    assert " ".join(chunks).split() == text.split()


def test_chunk_text_hard_splits_unbroken_text() -> None:
    chunks = chunk_text("x" * 50, 20)

    assert [len(chunk) for chunk in chunks] == [20, 20, 10]


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


@respx.mock
def test_score_applies_writing_mode_to_language_tool(
    client: TestClient, llm: FakeLLM
) -> None:
    route = respx.post(CHECK_URL).mock(
        return_value=httpx.Response(200, json={"matches": []})
    )

    response = client.post(
        "/score", json={"text": "Ein Text.", "language": "de-DE", "mode": "academic"}
    )

    assert response.status_code == 200
    params = parse_qs(route.calls.last.request.content.decode())
    assert params["level"] == ["picky"]
    assert "STYLE" in params["enabledCategories"][0]
    assert "COLLOQUIALISMS" in params["disabledCategories"][0]

    route.reset()
    response = client.post(
        "/score", json={"text": "Ein Text.", "language": "de-DE", "mode": "neutral"}
    )

    assert response.status_code == 200
    params = parse_qs(route.calls.last.request.content.decode())
    assert params["level"] == ["default"]
    assert "STYLE" in params["disabledCategories"][0]


@respx.mock
def test_score_chunks_long_text_for_language_tool(
    client: TestClient, llm: FakeLLM
) -> None:
    text = "Ein Satz. " * 5000
    chunks = chunk_text(text, 12000)
    section = {
        "grades": {"clarity": 1, "tone": 1, "vocabulary": 1, "structure": 1},
        "recommendations": [],
    }
    llm.replies = [json.dumps(section)] * len(chunks) + [json.dumps(SCORE)]
    route = respx.post(CHECK_URL).mock(
        return_value=httpx.Response(200, json={"matches": []})
    )

    response = client.post("/score", json={"text": text, "language": "de-DE"})

    assert response.status_code == 200
    assert route.call_count == 2
    assert all(
        len(parse_qs(call.request.content.decode())["text"][0]) <= 30_000
        for call in route.calls
    )


@respx.mock
def test_score_reports_languagetool_timeout(client: TestClient) -> None:
    respx.post(CHECK_URL).mock(side_effect=httpx.ReadTimeout("slow"))

    response = client.post("/score", json={"text": "Ein Text."})

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "languagetool_timeout"


def test_facts_ignore_markup_and_abbreviations() -> None:
    text = "## Titel\n\nDas ist z. B. ein Test. Noch ein Satz."

    prose = _strip_markdown(text)

    assert "##" not in prose
    assert _facts(prose) == {
        "words": 10,
        "sentences": 2,
        "averageSentenceWords": 5.0,
    }