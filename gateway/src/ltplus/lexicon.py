"""Terminology rules loaded from `rules/lexicon.yaml`.

Every match is emitted as a LanguageTool-shaped match, so the Obsidian plugin
needs no changes. Rules are read once at startup.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, PrivateAttr, ValidationError, model_validator


class LexiconConfigError(RuntimeError):
    """Raised when lexicon configuration cannot be loaded."""


class LexiconTerm(BaseModel):
    """One term rule. Empty `languages` or `modes` means all of them."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1)
    languages: list[str] = Field(default_factory=list)
    pattern: str = Field(min_length=1)
    message: str
    replacement: str | None = None
    modes: list[str] = Field(default_factory=list)

    _compiled: re.Pattern[str] = PrivateAttr()

    @model_validator(mode="after")
    def _compile(self) -> LexiconTerm:
        try:
            self._compiled = re.compile(self.pattern)
        except re.error as exc:
            raise ValueError(f"invalid pattern: {exc}") from exc
        return self


def load_lexicon(path: Path) -> list[LexiconTerm]:
    """Return the configured terms. A missing file means no terms."""
    if not path.is_file():
        return []

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise LexiconConfigError(f"cannot read {path}: {exc}") from exc

    if raw is None:
        return []
    if not isinstance(raw, dict):
        raise LexiconConfigError(f"{path}: expected a mapping")

    items = raw.get("terms", [])
    if not isinstance(items, list):
        raise LexiconConfigError(f"{path}: 'terms' must be a list")

    terms: list[LexiconTerm] = []
    seen: set[str] = set()
    for item in items:
        try:
            term = LexiconTerm.model_validate(item)
        except ValidationError as exc:
            raise LexiconConfigError(f"invalid term in {path}: {exc}") from exc
        if term.id in seen:
            raise LexiconConfigError(f"duplicate term id '{term.id}' in {path}")
        seen.add(term.id)
        terms.append(term)
    return terms


def validate_modes(terms: list[LexiconTerm], mode_ids: set[str]) -> None:
    """Fail on a term that names a mode the gateway does not define."""
    for term in terms:
        for mode_id in term.modes:
            if mode_id not in mode_ids:
                raise LexiconConfigError(f"term '{term.id}' uses unknown mode '{mode_id}'")


def synthetic_matches(
    terms: list[LexiconTerm], text: str, language: str, mode_id: str
) -> list[dict[str, object]]:
    """Build LanguageTool-shaped matches for every rule that applies."""
    primary = language.split("-")[0]
    matches: list[dict[str, object]] = []
    for term in terms:
        if term.modes and mode_id not in term.modes:
            continue
        if term.languages and language not in term.languages and primary not in term.languages:
            continue
        for found in term._compiled.finditer(text):
            start, end = found.span()
            before = max(0, start - 30)
            after = min(len(text), end + 30)
            context = text[before:after]
            matches.append(
                {
                    "message": term.message,
                    "shortMessage": "",
                    "replacements": [{"value": term.replacement}] if term.replacement else [],
                    "offset": _utf16_len(text[:start]),
                    "length": _utf16_len(text[start:end]),
                    "context": {
                        "text": context,
                        "offset": _utf16_len(text[before:start]),
                        "length": _utf16_len(text[start:end]),
                    },
                    "sentence": context,
                    "type": {"typeName": "Other"},
                    "rule": {
                        "id": term.id.upper(),
                        "description": term.message,
                        "issueType": "style",
                        "category": {"id": "LT_PLUS", "name": "LanguageToolPlus"},
                    },
                    "ignoreForIncompleteSentence": False,
                }
            )
    return matches


def _utf16_len(value: str) -> int:
    """LanguageTool and JavaScript measure offsets in UTF-16 code units."""
    return len(value.encode("utf-16-le")) // 2
