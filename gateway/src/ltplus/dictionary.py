"""Personal dictionary: one word per line, `#` for comments.

The file is read on every request so edits apply without a restart.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_words(directory: Path, language: str) -> set[str]:
    """Return case-folded words for a language, or an empty set."""
    words: set[str] = set()
    for name in dict.fromkeys((language, language.split("-")[0])):
        path = directory / f"{name}.txt"
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("cannot read dictionary %s: %s", path, exc)
            continue
        for line in lines:
            word = line.strip()
            if word and not word.startswith("#"):
                words.add(word.casefold())
    return words
