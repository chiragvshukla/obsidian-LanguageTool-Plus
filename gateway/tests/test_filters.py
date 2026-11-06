import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import respx
from fastapi.testclient import TestClient

from ltplus.config import Settings
from ltplus.main import create_app

MODES_DIR = Path(__file__).resolve().parents[2] / "modes"
CHECK_URL = "http://lt.test/v2/check"

LEXICON = r"""
terms:
  - id: email_hyphen
    languages: [de]
    pattern: '(?<!\w)Email(?!\w)'
    message: 'Schreibe E-Mail mit Bindestrich.'
    replacement: E-Mail
    modes: [formal]
"""


@contextmanager
def make_client(directory: Path) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        lt_url="http://lt.test",
        modes_dir=MODES_DIR,
        rules_dir=directory,
        dictionary_dir=directory,
        default_mode="neutral",
        default_language="de-DE",
    )
    with TestClient(create_app(settings)) as client:
        yield client


def annotated(text: str) -> str:
    return json.dumps({"annotation": [{"text": text}]})


@respx.mock
def test_dictionary_word_is_filtered(tmp_path: Path) -> None:
    (tmp_path / "de.txt").write_text("LanguageToolPlus\n", encoding="utf-8")
    respx.post(CHECK_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "matches": [{"rule": {"id": "MORFOLOGIK_RULE_DE_DE"}, "offset": 0, "length": 16}]
            },
        )
    )

    with make_client(tmp_path) as client:
        response = client.post(
            "/v2/check",
            data={"data": annotated("LanguageToolPlus"), "language": "de-DE"},
        )

    assert response.json()["matches"] == []


@respx.mock
def test_dictionary_offsets_are_utf16(tmp_path: Path) -> None:
    (tmp_path / "de.txt").write_text("LanguageToolPlus\n", encoding="utf-8")
    respx.post(CHECK_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "matches": [{"rule": {"id": "MORFOLOGIK_RULE_DE_DE"}, "offset": 3, "length": 16}]
            },
        )
    )

    with make_client(tmp_path) as client:
        response = client.post(
            "/v2/check",
            data={"data": annotated("😀 LanguageToolPlus"), "language": "de-DE"},
        )

    assert response.json()["matches"] == []


@respx.mock
def test_term_rule_fires_in_its_mode(tmp_path: Path) -> None:
    (tmp_path / "lexicon.yaml").write_text(LEXICON, encoding="utf-8")
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    with make_client(tmp_path) as client:
        response = client.post(
            "/v2/check",
            data={
                "data": annotated("Ein Email hier"),
                "language": "de-DE",
                "writing_mode": "formal",
            },
        )

    matches = response.json()["matches"]
    assert [(match["rule"]["id"], match["replacements"]) for match in matches] == [
        ("EMAIL_HYPHEN", [{"value": "E-Mail"}])
    ]


@respx.mock
def test_term_rule_is_off_in_other_modes(tmp_path: Path) -> None:
    (tmp_path / "lexicon.yaml").write_text(LEXICON, encoding="utf-8")
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    with make_client(tmp_path) as client:
        response = client.post(
            "/v2/check",
            data={
                "data": annotated("Ein Email hier"),
                "language": "de-DE",
                "writing_mode": "casual",
            },
        )

    assert response.json()["matches"] == []


@respx.mock
def test_term_rule_respects_enabled_only(tmp_path: Path) -> None:
    (tmp_path / "lexicon.yaml").write_text(LEXICON, encoding="utf-8")
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    with make_client(tmp_path) as client:
        off = client.post(
            "/v2/check",
            data={
                "data": annotated("Ein Email hier"),
                "language": "de-DE",
                "writing_mode": "formal",
                "enabledOnly": "true",
                "enabledCategories": "STYLE",
            },
        )
        on = client.post(
            "/v2/check",
            data={
                "data": annotated("Ein Email hier"),
                "language": "de-DE",
                "writing_mode": "formal",
                "enabledOnly": "true",
                "enabledCategories": "LT_PLUS",
            },
        )

    assert off.json()["matches"] == []
    assert [match["rule"]["id"] for match in on.json()["matches"]] == ["EMAIL_HYPHEN"]


@respx.mock
def test_term_rule_respects_disabled_rules(tmp_path: Path) -> None:
    (tmp_path / "lexicon.yaml").write_text(LEXICON, encoding="utf-8")
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    with make_client(tmp_path) as client:
        response = client.post(
            "/v2/check",
            data={
                "data": annotated("Ein Email hier"),
                "language": "de-DE",
                "writing_mode": "formal",
                "disabledRules": "EMAIL_HYPHEN",
            },
        )

    assert response.json()["matches"] == []


@respx.mock
def test_consistency_check_adds_one_document_match(tmp_path: Path) -> None:
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    with make_client(tmp_path) as client:
        response = client.post(
            "/v2/check",
            data={
                "data": annotated("Wir danken Ihnen. Kannst du helfen?"),
                "language": "de-DE",
                "writing_mode": "neutral",
            },
        )

    matches = response.json()["matches"]
    assert [match["rule"]["id"] for match in matches] == ["CONSISTENCY_DU_SIE"]


@respx.mock
def test_consistency_check_respects_disabled_rules(tmp_path: Path) -> None:
    respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    with make_client(tmp_path) as client:
        response = client.post(
            "/v2/check",
            data={
                "data": annotated("Wir danken Ihnen. Kannst du helfen?"),
                "language": "de-DE",
                "writing_mode": "neutral",
                "disabledRules": "CONSISTENCY_DU_SIE",
            },
        )

    assert response.json()["matches"] == []
