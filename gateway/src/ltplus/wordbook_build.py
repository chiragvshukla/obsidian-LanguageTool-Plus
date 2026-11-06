"""Download and build the local wordbook indexes.

Only this module talks to dictionary sources. Downloads are pinned where the
source publishes a checksum; the rotating Wiktionary extract has none, so its
computed hash is recorded in `SOURCES.json` and its gzip structure is verified
while parsing.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import re
import shutil
import tarfile
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

import httpx

logger = logging.getLogger(__name__)

TEI_NS = "{http://www.tei-c.org/ns/1.0}"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

# FreeDict publishes SHA-512 sums in its API; these are the 1.9-fd1 sources.
FREEDICT: dict[str, dict[str, str]] = {
    "de-en": {
        "url": "https://download.freedict.org/dictionaries/deu-eng/1.9-fd1/"
        "freedict-deu-eng-1.9-fd1.src.tar.xz",
        "sha512": "31c7143ae53074a5f357b80f4a6ccce8fa26f77a237476edca1353d5783293a0a"
        "8aef3a47f087de3e0c38f5aa7064196b7347886e1049116dc2964c6532397bc",
        "member": "deu-eng/deu-eng.tei",
        "language": "en",
    },
    "en-de": {
        "url": "https://download.freedict.org/dictionaries/eng-deu/1.9-fd1/"
        "freedict-eng-deu-1.9-fd1.src.tar.xz",
        "sha512": "e44d3a3697d2bfe93cadef70284355bdd9d41cae818722d26e9eda8e4268ce63c"
        "37cee4d623c4be8028467fc212d49b388fdb395c0a253d285aed1bd424f80a9",
        "member": "eng-deu/eng-deu.tei",
        "language": "de",
    },
}

# Rotating weekly; no checksum is published. See module docstring.
KAIKKI_URL = "https://kaikki.org/dewiktionary/raw-wiktextract-data.jsonl.gz"

KAIKKI_POS = {
    "noun",
    "verb",
    "adj",
    "adv",
    "pron",
    "prep",
    "conj",
    "det",
    "num",
    "intj",
    "phrase",
    "name",
    "article",
    "part",
    "postp",
    "contraction",
}

POS_NAMES = {
    "n": "noun",
    "v": "verb",
    "adj": "adjective",
    "adv": "adverb",
    "pron": "pronoun",
    "prep": "preposition",
    "conj": "conjunction",
    "det": "determiner",
    "num": "numeral",
    "intj": "interjection",
    "phrase": "phrase",
    "name": "proper noun",
    "article": "article",
    "part": "particle",
    "postp": "postposition",
    "contraction": "contraction",
}

GENDERS = {
    "m": "m",
    "masc": "m",
    "f": "f",
    "fem": "f",
    "n": "n",
    "neut": "n",
}

_FORM_JUNK = {"table-tags", "inflection-template", "class"}
_MAX_SENSES = 3
_OUT_OF_SCOPE_FORM = re.compile(r"[\s\d]")


class BuildError(RuntimeError):
    """Download or parse failure that leaves the previous data in place."""


def _download(url: str, target: Path, checksum: str | None, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    try:
        with (
            httpx.Client(follow_redirects=True, timeout=300.0) as client,
            client.stream("GET", url) as response,
            target.open("wb") as handle,
        ):
            response.raise_for_status()
            for chunk in response.iter_bytes():
                digest.update(chunk)
                handle.write(chunk)
    except (httpx.HTTPError, OSError) as exc:
        raise BuildError(f"cannot download {url}: {exc}") from exc

    actual = digest.hexdigest()
    if checksum is not None and actual != checksum:
        target.unlink(missing_ok=True)
        raise BuildError(f"checksum mismatch for {url}")
    return actual


def _write_jsonl(path: Path, rows: Iterator[dict[str, Any]]) -> None:
    temp = path.with_name(path.name + ".tmp")
    with gzip.open(temp, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temp, path)


def _sense_text(element: ET.Element) -> str:
    return " ".join("".join(element.itertext()).split())


def iter_freedict(tei: IO[bytes], target_language: str) -> Iterator[dict[str, Any]]:
    for _, element in ET.iterparse(tei, events=("end",)):
        if element.tag != TEI_NS + "entry":
            continue
        # Only the entry's own grammar: translation grammars belong to the
        # target word, not to the headword.
        word = (element.findtext(f"{TEI_NS}form/{TEI_NS}orth") or "").strip()
        if not word:
            element.clear()
            continue
        pos = (element.findtext(f"{TEI_NS}gramGrp/{TEI_NS}pos") or "").strip()
        gender = GENDERS.get(
            (element.findtext(f"{TEI_NS}gramGrp/{TEI_NS}gen") or "").strip().lower(), ""
        )
        senses: list[str] = []
        for sense in element.findall(f"{TEI_NS}sense"):
            for cit in sense.findall(f"{TEI_NS}cit"):
                if cit.get("type") != "trans":
                    continue
                quote = cit.find(f"{TEI_NS}quote")
                if quote is None or quote.get(XML_LANG) != target_language:
                    continue
                text = _sense_text(quote)
                if text and text not in senses:
                    senses.append(text)
                if len(senses) >= _MAX_SENSES:
                    break
            if len(senses) >= _MAX_SENSES:
                break
        if senses:
            yield {"w": word, "p": POS_NAMES.get(pos, pos), "g": gender, "s": senses}
        element.clear()


def _gender_of(entry: dict[str, Any]) -> str:
    for template in entry.get("head_templates") or []:
        args = template.get("args") or {}
        for key in ("1", "2", "3", "g"):
            value = str(args.get(key, "")).strip().lower()
            if value in GENDERS:
                return GENDERS[value]
    return ""


def _senses_of(entry: dict[str, Any]) -> list[str]:
    senses: list[str] = []
    for sense in entry.get("senses") or []:
        tags = sense.get("tags") or []
        if "form-of" in tags or "alt-of" in tags:
            continue
        for gloss in sense.get("glosses") or []:
            text = " ".join(str(gloss).split())
            if text and text not in senses:
                senses.append(text)
                break
        if len(senses) >= _MAX_SENSES:
            break
    return senses


def kaikki_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    """One compact entry, or None for entries the wordbook does not show."""
    if entry.get("lang_code") != "de":
        return None
    pos = entry.get("pos")
    if pos not in KAIKKI_POS:
        return None
    word = str(entry.get("word") or "").strip()
    senses = _senses_of(entry)
    if not word or not senses:
        return None
    return {
        "w": word,
        "p": POS_NAMES.get(pos, pos),
        "g": _gender_of(entry),
        "s": senses,
    }


def kaikki_aliases(entry: dict[str, Any]) -> Iterator[dict[str, str]]:
    if entry.get("lang_code") != "de":
        return
    word = str(entry.get("word") or "").strip()
    if not word:
        return
    for form in entry.get("forms") or []:
        text = str(form.get("form") or "").strip()
        tags = set(form.get("tags") or [])
        if not text or text == word or tags & _FORM_JUNK or _OUT_OF_SCOPE_FORM.search(text):
            continue
        yield {"a": text, "l": word}
    for sense in entry.get("senses") or []:
        for alt in sense.get("alt_of") or []:
            text = str(alt.get("word") or "").strip()
            if text and text != word and not _OUT_OF_SCOPE_FORM.search(text):
                yield {"a": text, "l": word}


def _build_kaikki(source: Path, directory: Path) -> None:
    # Entries and German aliases share one file, so one atomic replace switches
    # both at once. A crash can never leave them from different builds.
    entries = directory / "de-de.entries.jsonl.gz"
    entries_tmp = entries.with_name(entries.name + ".tmp")
    with (
        gzip.open(source, "rt", encoding="utf-8") as handle,
        gzip.open(entries_tmp, "wt", encoding="utf-8") as out,
    ):
        for line in handle:
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = kaikki_entry(raw)
            if item is not None:
                out.write(json.dumps(item, ensure_ascii=False) + "\n")
            for alias in kaikki_aliases(raw):
                out.write(json.dumps(alias, ensure_ascii=False) + "\n")
    os.replace(entries_tmp, entries)
    # Older installs kept aliases in a separate file; drop it after the swap.
    (directory / "de.aliases.jsonl.gz").unlink(missing_ok=True)


def _write_sources(directory: Path, sources: dict[str, Any]) -> None:
    """Replace SOURCES.json in one step so a crash never leaves half of it."""
    target = directory / "SOURCES.json"
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(sources, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, target)


def build_all(
    directory: Path,
    progress: Callable[[str, str], None] | None = None,
) -> None:
    """Download and build all three pairs. Partial success is kept."""
    directory.mkdir(parents=True, exist_ok=True)
    work = directory / ".work"
    work.mkdir(exist_ok=True)
    sources: dict[str, Any] = {
        "built": datetime.now(UTC).isoformat(timespec="seconds"),
        "sources": {},
    }
    report = progress or (lambda pair, message: None)

    for pair in ("en-de", "de-en"):
        source = FREEDICT[pair]
        report(pair, "downloading")
        archive = work / f"{pair}.tar.xz"
        digest = _download(source["url"], archive, source["sha512"], "sha512")
        report(pair, "parsing")
        with tarfile.open(archive, "r:xz") as tar:
            member = tar.extractfile(source["member"])
            if member is None:
                raise BuildError(f"{pair}: {source['member']} missing from archive")
            rows = iter_freedict(member, source["language"])
            _write_jsonl(directory / f"{pair}.entries.jsonl.gz", rows)
        sources["sources"][pair] = {
            "url": source["url"],
            "sha512": digest,
            "license": "GPL-2.0",
        }
        archive.unlink(missing_ok=True)
        _write_sources(directory, sources)
        report(pair, "installed")

    report("de-de", "downloading")
    extract = work / "kaikki.jsonl.gz"
    digest = _download(KAIKKI_URL, extract, None, "sha256")
    report("de-de", "indexing")
    _build_kaikki(extract, directory)
    extract.unlink(missing_ok=True)
    sources["sources"]["de-de"] = {
        "url": KAIKKI_URL,
        "sha256": digest,
        "license": "CC-BY-SA-3.0 / GFDL",
    }
    report("de-de", "installed")
    _write_sources(directory, sources)
    shutil.rmtree(work, ignore_errors=True)
