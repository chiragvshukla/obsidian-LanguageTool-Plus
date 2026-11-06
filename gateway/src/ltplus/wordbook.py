"""Local wordbook for the hover dictionary.

Data is built by `wordbook_build.py` and stored as gzip JSONL. Nothing here
calls an LLM or the network. The indexes load on first lookup and stay in
memory.
"""

from __future__ import annotations

import gzip
import json
import logging
import string
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()

PAIRS = ("de-de", "en-de", "de-en")
_DE_PAIRS = ("de-de", "de-en")
_MAX_ENTRIES = 2
_MAX_ALIASES = 5

_TRIM = string.punctuation + "„“”‚‘’…"  # noqa: RUF001 - typographic quotes are intentional


def normalize(word: str) -> str:
    """Case-fold and strip surrounding punctuation; German ß folds to ss."""
    return word.strip().strip(_TRIM).casefold()


def _entries_path(directory: Path, pair: str) -> Path:
    return directory / f"{pair}.entries.jsonl.gz"


def _aliases_path(directory: Path) -> Path:
    return directory / "de.aliases.jsonl.gz"


class Wordbook:
    """Lazy lookup over the generated indexes, plus install bookkeeping."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._index: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self._aliases: dict[str, list[str]] | None = None
        self._lock = threading.RLock()
        self._building = False
        self._message = ""
        self._error = ""

    def status(self) -> dict[str, Any]:
        with self._lock:
            pairs = {}
            for pair in PAIRS:
                path = _entries_path(self.directory, pair)
                pairs[pair] = {
                    "installed": path.is_file(),
                    "bytes": path.stat().st_size if path.is_file() else 0,
                }
            return {
                "pairs": pairs,
                "building": self._building,
                "message": self._message,
                "error": self._error,
            }

    def start_install(self) -> None:
        with self._lock:
            if self._building:
                return
            self._building = True
            self._error = ""
            self._message = "starting"
        threading.Thread(target=self._install, name="wordbook-install", daemon=True).start()

    def _install(self) -> None:
        from ltplus.wordbook_build import build_all

        try:
            build_all(self.directory, self._progress)
        except Exception as exc:  # surfaced through /dictionary/status
            logger.warning("wordbook install failed: %s", exc)
            with self._lock:
                self._error = str(exc)
                self._message = "failed"
        else:
            with self._lock:
                self._message = "installed"
        finally:
            # A failed build may still have replaced some pairs, so always
            # drop cached indexes rather than serve stale entries.
            with self._lock:
                self._index.clear()
                self._aliases = None
                self._building = False

    def _progress(self, pair: str, message: str) -> None:
        self._message = f"{pair}: {message}"

    def _load(self, pair: str) -> dict[str, list[dict[str, Any]]]:
        index = self._index.get(pair)
        if index is not None:
            return index
        path = _entries_path(self.directory, pair)
        if not path.is_file():
            raise FileNotFoundError(path)
        loaded: dict[str, list[dict[str, Any]]] = {}
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                loaded.setdefault(normalize(row["w"]), []).append(row)
        self._index[pair] = loaded
        return loaded

    def _load_aliases(self) -> dict[str, list[str]]:
        if self._aliases is not None:
            return self._aliases
        aliases: dict[str, list[str]] = {}
        path = _aliases_path(self.directory)
        if path.is_file():
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    row = json.loads(line)
                    targets = aliases.setdefault(normalize(row["a"]), [])
                    if row["l"] not in targets:
                        targets.append(row["l"])
                    if len(targets) > _MAX_ALIASES:
                        targets.pop()
        self._aliases = aliases
        return aliases

    def lookup(self, pair: str, word: str) -> dict[str, Any]:
        if pair not in PAIRS:
            raise ValueError("unknown pair")
        key = normalize(word)
        if not key:
            return {"word": word, "lemma": None, "entries": []}

        with self._lock:
            index = self._load(pair)
            targets = [key] if key in index else []
            if not targets and pair in _DE_PAIRS:
                targets = [normalize(item) for item in self._load_aliases().get(key, [])]

            entries: list[dict[str, Any]] = []
            seen: set[tuple[str, str, tuple[str, ...]]] = set()
            for target in targets:
                for entry in index.get(target, []):
                    marker = (entry["w"], entry["p"], tuple(entry["s"]))
                    if marker in seen:
                        continue
                    seen.add(marker)
                    entries.append(entry)
                    if len(entries) >= _MAX_ENTRIES:
                        break
                if len(entries) >= _MAX_ENTRIES:
                    break

        return {
            "word": word,
            "lemma": entries[0]["w"] if entries else None,
            "entries": entries,
        }


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


@router.get("/dictionary/status")
def dictionary_status(request: Request) -> JSONResponse:
    book: Wordbook = request.app.state.wordbook
    return JSONResponse(book.status())


@router.post("/dictionary/install")
def dictionary_install(request: Request) -> JSONResponse:
    book: Wordbook = request.app.state.wordbook
    book.start_install()
    return JSONResponse(book.status(), status_code=202)


@router.get("/dictionary/lookup")
def dictionary_lookup(request: Request, word: str, pair: str = "de-de") -> JSONResponse:
    if pair not in PAIRS:
        return _error(400, "unknown_pair", f"Unknown pair: {pair}")
    if not word.strip() or len(word) > 80:
        return _error(400, "invalid_word", "Word must be 1-80 characters")
    book: Wordbook = request.app.state.wordbook
    try:
        result = book.lookup(pair, word)
    except FileNotFoundError:
        return _error(503, "dictionary_not_installed", "Download the dictionary data first")
    return JSONResponse(result)