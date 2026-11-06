"""Document-level consistency checks.

Each check reports at most one match, because the useful signal is a single
document-wide warning, not one per occurrence. The matches are synthetic
LanguageTool matches, so the Obsidian plugin needs no changes.
"""

from __future__ import annotations

import re

from ltplus.lexicon import LexiconTerm, applies, make_match

# German address. `Sie` is also third-person plural, so a lone `Sie` can be a
# false positive; the check only fires when informal forms appear as well.
# shortcut: pronoun heuristics only, upgrade to a tagger if false alarms matter.
_INFORMAL = re.compile(
    r"\b(?:du|dich|dir|dein(?:e|em|en|er|es)?|euch|euer|eure|eurem|euren|eurer|eures)\b",
    re.IGNORECASE,
)
_FORMAL = re.compile(r"\b(?:Sie|Ihnen|Ihr(?:e|em|en|er|es)?)\b")

_DATE_FORMATS = (
    re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
)
_NUMBER_DE = re.compile(r"\b\d{1,3}(?:\.\d{3})+(?:,\d+)?\b")
_NUMBER_EN = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b")

_MESSAGES = {
    "du_sie": (
        "Anrede wechselt zwischen „Sie“ und „du“. Wähle eine Form.",
        "Address changes between formal and informal. Pick one form.",
    ),
    "date": (
        "Datumsformate sind gemischt. Verwende ein Format im ganzen Dokument.",
        "Date formats are mixed. Use one format throughout the document.",
    ),
    "number": (
        "Zahlenformate sind gemischt (1.234,56 und 1,234.56).",
        "Number formats are mixed (1.234,56 and 1,234.56).",
    ),
    "term": (
        "Der Begriff wird im Dokument uneinheitlich verwendet.",
        "The term is spelled inconsistently in this document.",
    ),
}


def _message(key: str, language: str) -> str:
    german, english = _MESSAGES[key]
    return german if language.split("-")[0] == "de" else english


def _second_format_span(text: str, patterns: tuple[re.Pattern[str], ...]) -> re.Match[str] | None:
    """Return the first match of the second date format that appears."""
    found = [match for pattern in patterns if (match := pattern.search(text))]
    if len(found) < 2:
        return None
    return sorted(found, key=lambda match: match.start())[1]


def document_matches(
    terms: list[LexiconTerm], text: str, language: str, mode_id: str
) -> list[dict[str, object]]:
    """Return at most one match per consistency issue type."""
    primary = language.split("-")[0]
    matches: list[dict[str, object]] = []

    informal = _INFORMAL.search(text)
    formal = _FORMAL.search(text)
    if primary == "de" and informal and formal:
        later = max(informal, formal, key=lambda match: match.start())
        matches.append(
            make_match(
                text,
                later.start(),
                later.end(),
                "CONSISTENCY_DU_SIE",
                _message("du_sie", language),
            )
        )

    switch = _second_format_span(text, _DATE_FORMATS)
    if switch:
        matches.append(
            make_match(
                text,
                switch.start(),
                switch.end(),
                "CONSISTENCY_DATE_FORMAT",
                _message("date", language),
            )
        )

    german_number = _NUMBER_DE.search(text)
    english_number = _NUMBER_EN.search(text)
    if german_number and english_number:
        later = max(german_number, english_number, key=lambda match: match.start())
        matches.append(
            make_match(
                text,
                later.start(),
                later.end(),
                "CONSISTENCY_NUMBER_FORMAT",
                _message("number", language),
            )
        )

    for term in terms:
        if not term.replacement or not applies(term, language, mode_id):
            continue
        non_canonical = term._compiled.search(text)
        if not non_canonical:
            continue
        if non_canonical.group(0).casefold() == term.replacement.casefold():
            continue
        canonical = re.search(rf"(?<!\w){re.escape(term.replacement)}(?!\w)", text)
        if canonical:
            matches.append(
                make_match(
                    text,
                    canonical.start(),
                    canonical.end(),
                    term.id,
                    _message("term", language),
                )
            )

    return matches
