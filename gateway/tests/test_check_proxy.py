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
        data={"data": "{}", "language": "de-DE", "level": "default", "mode": "formal"},
    )

    assert sent_form(route)["level"] == ["picky"]


@respx.mock
def test_client_picky_wins_over_neutral_mode(client: TestClient) -> None:
    route = respx.post(CHECK_URL).mock(return_value=httpx.Response(200, json={"matches": []}))

    client.post(
        "/v2/check",
        data={"data": "{}", "language": "de-DE", "level": "picky", "mode": "neutral"},
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
            "mode": "casual",
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
            "mode": "academic",
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
            "mode": "formal",
            "enabledCategories": "STYLE",
            "disabledCategories": "STYLE",
        },
    )

    assert "enabledCategories" not in sent_form(route)


def test_unknown_mode_is_rejected(client: TestClient) -> None:
    response = client.post("/v2/check", data={"data": "{}", "language": "de-DE", "mode": "nope"})

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
