from pathlib import Path

from ltplus.dictionary import load_words


def test_loads_words_comments_and_primary_language(tmp_path: Path) -> None:
    (tmp_path / "de.txt").write_text("# comment\nLanguageToolPlus\nStraße\n\n", encoding="utf-8")

    words = load_words(tmp_path, "de-DE")

    assert "languagetoolplus" in words
    assert "strasse" in words


def test_missing_language_returns_empty(tmp_path: Path) -> None:
    assert load_words(tmp_path, "de-DE") == set()


def test_reloads_after_edit(tmp_path: Path) -> None:
    path = tmp_path / "de.txt"
    path.write_text("LanguageToolPlus\n", encoding="utf-8")
    assert "obsidian" not in load_words(tmp_path, "de-DE")

    path.write_text("LanguageToolPlus\nObsidian\n", encoding="utf-8")

    assert "obsidian" in load_words(tmp_path, "de-DE")
