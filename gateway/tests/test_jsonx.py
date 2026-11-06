import json

from ltplus.jsonx import describe, extract_candidates

VALUE = {"changes": [{"original": "ist", "replacement": "war"}]}


def test_plain_json() -> None:
    assert extract_candidates(json.dumps(VALUE)) == [VALUE]


def test_fenced_json() -> None:
    assert extract_candidates(f"```json\n{json.dumps(VALUE)}\n```") == [VALUE]


def test_unclosed_fence() -> None:
    assert extract_candidates(f"```json\n{json.dumps(VALUE)}") == [VALUE]


def test_think_block() -> None:
    text = f"<think>Beispiel: {json.dumps(VALUE)}</think>\n{json.dumps(VALUE)}"
    assert extract_candidates(text) == [VALUE]


def test_prose_before_and_after() -> None:
    text = f"Here is the rewrite: {json.dumps(VALUE)} Hope it helps."
    assert extract_candidates(text) == [VALUE]


def test_last_object_wins_over_an_example_in_the_reasoning() -> None:
    example = {"changes": []}
    text = f"Example {json.dumps(example)}. Final:\n{json.dumps(VALUE)}"
    assert extract_candidates(text)[0] == VALUE


def test_braces_inside_strings_do_not_split_the_object() -> None:
    value = {"text": "a { b } c"}
    assert extract_candidates(f"before {json.dumps(value)} after") == [value]


def test_double_encoded_json() -> None:
    assert extract_candidates(json.dumps(json.dumps(VALUE))) == [VALUE]


def test_empty_and_garbage() -> None:
    assert extract_candidates("") == []
    assert extract_candidates("not json") == []


def test_describe_never_includes_the_text() -> None:
    report = describe("secret prompt text {")
    assert "secret" not in report
    assert "len=20" in report
    assert "braces=1/0" in report
