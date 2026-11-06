import urllib.parse

import httpx
import respx
from fastapi.testclient import TestClient

CHECK_URL = "http://lt.test/v2/check"
LANGUAGES_URL = "http://lt.test/v2/languages"


def sent_form(route: respx.Route) -> dict[str, list[str]]:
    request = route.calls.last.request
    parsed = urllib.parse.parse_qs(request.content.decode("utf-8"))
    assert isinstance(parsed, dict)
    return parsed


@respx.mock
def test_data_is_forwarded_unchanged(client: TestClient) -> None:
    route = respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))
    annotated = '{"annotation":["Test ",{"text":"x"}]}'

    response = client.post("/v2/check", data={"data": annotated, "language": "de-DE"})

    assert response.status_code == 200
    assert response.json() == {"matches": []}
    assert sent_form(route)["data"] == [annotated]


@respx.mock
def test_mode_picky_wins_over_client_default(client: TestClient) -> None:
    route = respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    client.post(
        "/v2/check",
        data={"data": "{}", "language": "de-DE", "level": "default", "writing_mode": "formal"},
    )

    assert sent_form(route)["level"] == ["picky"]


@respx.mock
def test_client_picky_wins_over_neutral_mode(client: TestClient) -> None:
    route = respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    client.post(
        "/v2/check",
        data={"data": "{}", "language": "de-DE", "level": "picky", "writing_mode": "neutral"},
    )

    assert sent_form(route)["level"] == ["picky"]


@respx.mock
def test_disabled_categories_are_unioned(client: TestClient) -> None:
    route = respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    client.post(
        "/v2/check",
        data={
            "data": "{}",
            "language": "de-DE",
            "writing_mode": "casual",
            "disabledCategories": "CASING",
        },
    )

    disabled = sent_form(route)["disabledCategories"][0].split(",")
    assert "CASING" in disabled
    assert "STYLE" in disabled
    assert "COLLOQUIALISMS" in disabled


@respx.mock
def test_enabled_categories_are_intersected(client: TestClient) -> None:
    route = respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    client.post(
        "/v2/check",
        data={
            "data": "{}",
            "language": "de-DE",
            "writing_mode": "academic",
            "enabledCategories": "STYLE,CASING",
        },
    )

    enabled = sent_form(route)["enabledCategories"][0].split(",")
    assert enabled == ["STYLE"]


@respx.mock
def test_category_disabled_on_either_side_stays_disabled(client: TestClient) -> None:
    route = respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    client.post(
        "/v2/check",
        data={
            "data": "{}",
            "language": "de-DE",
            "writing_mode": "formal",
            "enabledCategories": "STYLE",
            "disabledCategories": "STYLE",
        },
    )

    assert "enabledCategories" not in sent_form(route)


def test_unknown_mode_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/v2/check", data={"data": "{}", "language": "de-DE", "writing_mode": "nope"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_mode"


@respx.mock
def test_unreachable_languagetool_returns_503(client: TestClient) -> None:
    respx.post(CHECK_URL).mock(side_effect=httpx.ConnectError("refused"))

    response = client.post("/v2/check", data={"data": "{}", "language": "de-DE"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "languagetool_unavailable"


@respx.mock
def test_languagetool_timeout_returns_504(client: TestClient) -> None:
    respx.post(CHECK_URL).mock(side_effect=httpx.ReadTimeout("slow"))

    response = client.post("/v2/check", data={"data": "{}", "language": "de-DE"})

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "languagetool_timeout"


@respx.mock
def test_languages_are_proxied(client: TestClient) -> None:
    payload = [{"name": "German (Germany)", "longCode": "de-DE"}]
    respx.get(LANGUAGES_URL).mock(return_value=httpx.Response(200, json=payload))

    response = client.get("/v2/languages")

    assert response.status_code == 200
    assert response.json() == payload


@respx.mock
def test_languagetool_mode_is_forwarded(client: TestClient) -> None:
    route = respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    response = client.post("/v2/check", data={"data": "{}", "language": "de-DE", "mode": "all"})

    assert response.status_code == 200
    assert sent_form(route)["mode"] == ["all"]


@respx.mock
def test_enabled_categories_are_unioned_when_client_sends_none(client: TestClient) -> None:
    route = respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    client.post("/v2/check", data={"data": "{}", "language": "de-DE", "writing_mode": "academic"})

    enabled = set(sent_form(route)["enabledCategories"][0].split(","))
    assert {"STYLE", "REDUNDANCY", "TYPOGRAPHY", "GENDER_NEUTRALITY"} <= enabled


@respx.mock
def test_enabled_only_drops_disabled_categories(client: TestClient) -> None:
    route = respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    response = client.post(
        "/v2/check",
        data={
            "data": "{}",
            "language": "de-DE",
            "writing_mode": "neutral",
            "enabledOnly": "true",
            "enabledCategories": "GRAMMAR",
        },
    )

    assert response.status_code == 200
    assert "disabledCategories" not in sent_form(route)
    assert sent_form(route)["enabledCategories"] == ["GRAMMAR"]


@respx.mock
def test_missing_language_uses_default(client: TestClient) -> None:
    route = respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    client.post("/v2/check", data={"data": "{}"})

    assert sent_form(route)["language"] == ["de-DE"]


def test_non_utf8_body_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/v2/check",
        content=b"\xff\xfe",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_body"


@respx.mock
def test_upstream_4xx_is_passed_through(client: TestClient) -> None:
    respx.post(CHECK_URL).mock(return_value=httpx.Response(400, text="Error: bad language"))

    response = client.post("/v2/check", data={"data": "{}", "language": "xx-XX"})

    assert response.status_code == 400
    assert response.text == "Error: bad language"
