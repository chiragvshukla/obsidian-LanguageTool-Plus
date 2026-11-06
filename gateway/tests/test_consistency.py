from ltplus.consistency import document_matches
from ltplus.lexicon import LexiconTerm

EMAIL = LexiconTerm(
    id="email_hyphen",
    languages=["de"],
    pattern=r"(?<!\w)Email(?!\w)",
    message="Schreibe E-Mail mit Bindestrich.",
    replacement="E-Mail",
    modes=["formal"],
)


def rule_ids(matches: list[dict[str, object]]) -> list[str]:
    return [match["rule"]["id"] for match in matches]  # type: ignore[index]


def test_mixed_address_reports_one_match() -> None:
    matches = document_matches([], "Wir danken Ihnen. Kannst du helfen?", "de-DE", "neutral")

    assert rule_ids(matches) == ["CONSISTENCY_DU_SIE"]
    assert matches[0]["message"] == "Anrede wechselt zwischen „Sie“ und „du“. Wähle eine Form."


def test_single_address_style_is_fine() -> None:
    assert document_matches([], "Wir danken Ihnen für die Hilfe.", "de-DE", "neutral") == []
    assert document_matches([], "Danke, dass du hilfst.", "de-DE", "neutral") == []


def test_address_check_is_german_only() -> None:
    text = "Wir danken Ihnen. Can you help?"

    assert document_matches([], text, "en-US", "neutral") == []


def test_mixed_date_formats_report_one_match() -> None:
    text = "Termin am 12.03.2024, danach am 2024-04-01."

    matches = document_matches([], text, "de-DE", "neutral")

    assert rule_ids(matches) == ["CONSISTENCY_DATE_FORMAT"]
    assert text[matches[0]["offset"] :].startswith("2024-04-01")  # type: ignore[index]


def test_one_date_format_is_fine() -> None:
    text = "Am 12.03.2024 und am 13.03.2024."

    assert document_matches([], text, "de-DE", "neutral") == []


def test_mixed_number_formats_report_one_match() -> None:
    matches = document_matches([], "Einmal 1.234,56 und einmal 1,234.56.", "de-DE", "neutral")

    assert rule_ids(matches) == ["CONSISTENCY_NUMBER_FORMAT"]


def test_one_number_format_is_fine() -> None:
    assert document_matches([], "Einmal 1.234,56.", "de-DE", "neutral") == []


def test_inconsistent_term_is_reported_once_at_canonical_form() -> None:
    text = "Eine E-Mail und ein Email."

    matches = document_matches([EMAIL], text, "de-DE", "formal")

    assert rule_ids(matches) == ["EMAIL_HYPHEN"]
    assert text[matches[0]["offset"] :].startswith("E-Mail")  # type: ignore[index]


def test_term_respects_mode_and_language() -> None:
    text = "Eine E-Mail und ein Email."

    assert document_matches([EMAIL], text, "de-DE", "casual") == []
    assert document_matches([EMAIL], text, "en-US", "formal") == []


def test_term_used_consistently_is_fine() -> None:
    assert document_matches([EMAIL], "Zwei Emails.", "de-DE", "formal") == []


def test_offsets_use_utf16_code_units() -> None:
    matches = document_matches([], "😀 Ihnen und du", "de-DE", "neutral")

    assert matches[0]["offset"] == 13  # type: ignore[index]
