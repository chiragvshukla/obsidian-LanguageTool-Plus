from pathlib import Path

import pytest

from ltplus.lexicon import (
    LexiconConfigError,
    load_lexicon,
    synthetic_matches,
    validate_modes,
)

LEXICON = r"""
terms:
  - id: email_hyphen
    languages: [de]
    pattern: '(?<!\w)Email(?!\w)'
    message: 'Schreibe E-Mail mit Bindestrich.'
    replacement: E-Mail
    modes: [formal]
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "lexicon.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_terms(tmp_path: Path) -> None:
    terms = load_lexicon(write(tmp_path, LEXICON))

    assert terms[0].id == "email_hyphen"
    assert terms[0]._compiled.pattern == r"(?<!\w)Email(?!\w)"


def test_missing_file_means_no_terms(tmp_path: Path) -> None:
    assert load_lexicon(tmp_path / "missing.yaml") == []


def test_rejects_invalid_regex(tmp_path: Path) -> None:
    broken = """
terms:
  - id: broken
    pattern: '(unclosed'
    message: 'x'
"""
    with pytest.raises(LexiconConfigError, match="invalid pattern"):
        load_lexicon(write(tmp_path, broken))


def test_rejects_duplicate_id(tmp_path: Path) -> None:
    duplicate = """
terms:
  - id: same
    pattern: 'a'
    message: 'x'
  - id: same
    pattern: 'b'
    message: 'y'
"""
    with pytest.raises(LexiconConfigError, match="duplicate term id"):
        load_lexicon(write(tmp_path, duplicate))


def test_rejects_unknown_mode(tmp_path: Path) -> None:
    terms = load_lexicon(write(tmp_path, LEXICON))

    with pytest.raises(LexiconConfigError, match="unknown mode"):
        validate_modes(terms, {"neutral"})


def test_match_shape_and_mode(tmp_path: Path) -> None:
    terms = load_lexicon(write(tmp_path, LEXICON))

    matches = synthetic_matches(terms, "Ein Email hier", "de-DE", "formal")

    assert len(matches) == 1
    match = matches[0]
    assert match["offset"] == 4
    assert match["length"] == 5
    assert match["replacements"] == [{"value": "E-Mail"}]
    assert match["rule"] == {
        "id": "EMAIL_HYPHEN",
        "description": "Schreibe E-Mail mit Bindestrich.",
        "issueType": "style",
        "category": {"id": "LT_PLUS", "name": "LanguageToolPlus"},
    }


def test_mode_and_language_gate(tmp_path: Path) -> None:
    terms = load_lexicon(write(tmp_path, LEXICON))

    assert synthetic_matches(terms, "Ein Email hier", "de-DE", "casual") == []
    assert synthetic_matches(terms, "Ein Email hier", "en-US", "formal") == []


def test_offsets_use_utf16_code_units(tmp_path: Path) -> None:
    terms = load_lexicon(write(tmp_path, LEXICON))

    matches = synthetic_matches(terms, "😀 Email", "de-DE", "formal")

    assert matches[0]["offset"] == 3
    assert matches[0]["length"] == 5
