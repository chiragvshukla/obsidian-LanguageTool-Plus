import gzip
import io
import json
from pathlib import Path

from fastapi.testclient import TestClient

from ltplus.wordbook import Wordbook
from ltplus.wordbook_build import (
    BuildError,
    _build_kaikki,
    iter_freedict,
    kaikki_aliases,
    kaikki_entry,
)

TEI = b"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text><body>
    <entry xml:id="Haus.1">
      <form><orth>Haus</orth></form>
      <gramGrp><gen>neut</gen><pos>n</pos></gramGrp>
      <sense><cit type="trans"><quote xml:lang="en">house</quote></cit>
        <cit type="trans"><quote xml:lang="en">home</quote></cit></sense>
    </entry>
    <entry xml:id="gehen.1">
      <form><orth>gehen</orth></form>
      <gramGrp><pos>v</pos></gramGrp>
      <sense><cit type="trans"><quote xml:lang="en">to go</quote></cit></sense>
    </entry>
    <entry xml:id="empty.1">
      <form><orth>leer</orth></form>
      <sense><cit type="trans"><quote xml:lang="fr">vide</quote></cit></sense>
    </entry>
  </body></text>
</TEI>
"""

KAIKKI = [
    {
        "lang_code": "de",
        "word": "Haus",
        "pos": "noun",
        "head_templates": [{"args": {"1": "n"}}],
        "senses": [{"glosses": ["building for living"]}],
        "forms": [
            {"form": "Haus", "tags": ["nominative", "singular"]},
            {"form": "Häuser", "tags": ["nominative", "plural"]},
            {"form": "Häusern", "tags": ["dative", "plural"]},
        ],
    },
    {
        "lang_code": "de",
        "word": "gehen",
        "pos": "verb",
        "senses": [{"glosses": ["to go"]}],
        "forms": [{"form": "ging", "tags": ["past"]}, {"form": "gegangen"}],
    },
    {
        "lang_code": "de",
        "word": "laufen",
        "pos": "verb",
        "senses": [{"glosses": ["to run"]}],
    },
    {"lang_code": "en", "word": "house", "pos": "noun", "senses": [{"glosses": ["x"]}]},
]


def write_gzip(path: Path, rows: list[dict[str, object]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def make_book(directory: Path) -> Wordbook:
    write_gzip(
        directory / "de-de.entries.jsonl.gz",
        [
            {"w": "Haus", "p": "noun", "g": "n", "s": ["building"]},
            {"w": "gehen", "p": "verb", "g": "", "s": ["to go"]},
            {"w": "Bank", "p": "noun", "g": "f", "s": ["bench"]},
            {"w": "Bank", "p": "noun", "g": "f", "s": ["bank"]},
            {"a": "Häuser", "l": "Haus"},
            {"a": "ging", "l": "gehen"},
        ],
    )
    write_gzip(
        directory / "de-en.entries.jsonl.gz",
        [{"w": "Haus", "p": "noun", "g": "n", "s": ["house"]}],
    )
    write_gzip(
        directory / "en-de.entries.jsonl.gz",
        [{"w": "house", "p": "noun", "g": "", "s": ["Haus"]}],
    )
    return Wordbook(directory)


def test_freedict_parses_translations_and_skips_empty() -> None:
    rows = list(iter_freedict(io.BytesIO(TEI), "en"))

    assert rows == [
        {"w": "Haus", "p": "noun", "g": "n", "s": ["house", "home"]},
        {"w": "gehen", "p": "verb", "g": "", "s": ["to go"]},
    ]


def test_kaikki_entry_and_alias_shape() -> None:
    entry = kaikki_entry(KAIKKI[0])
    assert entry == {
        "w": "Haus",
        "p": "noun",
        "g": "n",
        "s": ["building for living"],
    }
    assert list(kaikki_aliases(KAIKKI[0])) == [
        {"a": "Häuser", "l": "Haus"},
        {"a": "Häusern", "l": "Haus"},
    ]
    assert kaikki_entry(KAIKKI[3]) is None


def test_kaikki_build_writes_entries_and_aliases(tmp_path: Path) -> None:
    source = tmp_path / "kaikki.jsonl.gz"
    write_gzip(source, KAIKKI)

    _build_kaikki(source, tmp_path)

    with gzip.open(tmp_path / "de-de.entries.jsonl.gz", "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]

    entries = [row for row in rows if "w" in row]
    aliases = [row for row in rows if "a" in row]
    assert [entry["w"] for entry in entries] == ["Haus", "gehen", "laufen"]
    assert {"a": "ging", "l": "gehen"} in aliases
    assert all(alias["a"] != "gegangen" or alias["l"] == "gehen" for alias in aliases)
    assert not (tmp_path / "de.aliases.jsonl.gz").exists()


def test_lookup_reads_legacy_alias_file(tmp_path: Path) -> None:
    write_gzip(
        tmp_path / "de-de.entries.jsonl.gz",
        [{"w": "Haus", "p": "noun", "g": "n", "s": ["building"]}],
    )
    write_gzip(tmp_path / "de.aliases.jsonl.gz", [{"a": "Häuser", "l": "Haus"}])

    assert Wordbook(tmp_path).lookup("de-de", "Häuser")["lemma"] == "Haus"


def test_lookup_resolves_alias_and_keeps_ambiguity(tmp_path: Path) -> None:
    book = make_book(tmp_path)

    assert book.lookup("de-de", "Häuser")["lemma"] == "Haus"
    assert book.lookup("de-de", "ging")["lemma"] == "gehen"
    assert len(book.lookup("de-de", "Bank")["entries"]) == 2
    assert book.lookup("de-en", "Haus")["entries"][0]["s"] == ["house"]
    assert book.lookup("en-de", "house")["entries"][0]["s"] == ["Haus"]


def test_lookup_normalizes_punctuation_and_case(tmp_path: Path) -> None:
    book = make_book(tmp_path)

    assert book.lookup("de-de", "  HÄUSER!")["lemma"] == "Haus"
    assert book.lookup("de-de", "  Háusern!")["entries"] == []


def test_status_reports_missing_pairs(tmp_path: Path) -> None:
    status = Wordbook(tmp_path).status()

    assert status["pairs"]["de-de"]["installed"] is False
    assert status["building"] is False


def test_endpoints_lookup_status_and_missing_data(
    client: TestClient, settings, tmp_path: Path
) -> None:
    client.app.state.wordbook = make_book(tmp_path)

    response = client.get("/dictionary/lookup", params={"word": "Häuser", "pair": "de-de"})
    assert response.status_code == 200
    assert response.json()["lemma"] == "Haus"

    assert client.get("/dictionary/status").json()["pairs"]["de-de"]["installed"] is True

    missing = client.get("/dictionary/lookup", params={"word": "Haus", "pair": "de-de"})
    assert missing.status_code == 200

    client.app.state.wordbook = Wordbook(tmp_path / "missing")
    response = client.get("/dictionary/lookup", params={"word": "Haus", "pair": "de-de"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dictionary_not_installed"


def test_lookup_rejects_unknown_pair_and_long_word(client: TestClient) -> None:
    unknown = client.get("/dictionary/lookup", params={"word": "Haus", "pair": "xx-xx"})
    long_word = client.get("/dictionary/lookup", params={"word": "x" * 81, "pair": "de-de"})

    assert unknown.status_code == 400
    assert long_word.status_code == 400


def test_install_deduplicates_running_build(monkeypatch) -> None:
    book = Wordbook(Path("unused"))
    calls: list[int] = []

    class FakeThread:
        def __init__(self, target, name, daemon):
            calls.append(1)

        def start(self) -> None:
            return None

    monkeypatch.setattr("ltplus.wordbook.threading.Thread", FakeThread)
    book.start_install()
    book.start_install()

    assert len(calls) == 1
    assert book.status()["building"] is True


def test_checksum_mismatch_is_reported(tmp_path: Path, monkeypatch) -> None:
    from ltplus import wordbook_build

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            yield b"not the pinned bytes"

    class FakeStream:
        def __enter__(self):
            return FakeResponse()

        def __exit__(self, *exc) -> None:
            return None

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> None:
            return None

        def stream(self, method, url):
            return FakeStream()

    monkeypatch.setattr(wordbook_build.httpx, "Client", FakeClient)

    try:
        wordbook_build._download("http://x", tmp_path / "a", "00", "sha256")
    except BuildError:
        pass
    else:
        raise AssertionError("expected a checksum failure")

    assert not (tmp_path / "a").exists()
