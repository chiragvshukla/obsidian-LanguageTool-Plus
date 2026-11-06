# Architecture

## Context

LanguageToolPlus is a personal writing assistant for Obsidian, split into four
parts that can fail independently:

```
┌───────────────────────┐
│  Obsidian + plugin    │  upstream plugin, later a small fork
└───────────┬───────────┘
            │ HTTP  POST /v2/check, GET /v2/languages
            ▼
┌───────────────────────┐        ┌──────────────────────────┐
│  Gateway (FastAPI)    │───────▶│  LanguageTool (Docker)   │
│  stateless per request│  HTTP  │  unmodified, port 8010   │
│                       │        └──────────────────────────┘
│  modes / rules / dict │
│  in-memory LLM cache  │        ┌──────────────────────────┐
│                       │───────▶│  OpenAI-compatible LLM   │
└───────────────────────┘  HTTP  │  Ollama or hosted API    │
                                 └──────────────────────────┘
```

There is no database.

## Components

### LanguageTool

- Prebuilt upstream image `erikvl87/languagetool`, unmodified. No custom build.
- The only container in the stack.
- Port `8010`, bound to `127.0.0.1` on the host.
- Customisation is a single read-only bind mount:
  `rules/grammar_custom.xml` →
  `/LanguageTool/org/languagetool/rules/de/grammar_custom.xml`.
  `Language.getRuleFileNames()` loads that file automatically when it exists,
  so a rule change means restarting the container, not rebuilding an image.
- Personal spelling words are handled by the gateway dictionary
  (`data/dictionary/`), not by editing Hunspell data.

### Ollama / LLM

- Not containerized and not part of this repository.
- Runs as a host process, addressed only through `LLM_BASE_URL`.
- Any OpenAI-compatible server can replace it.

### Gateway

- Python 3.12, FastAPI, pydantic v2.
- Stateless per request. Reads config from environment.
- Responsibilities, in build order:
  1. Pass-through `/v2/check` and `/v2/languages`.
  2. Resolve a writing mode into LanguageTool parameters.
  3. Filter results against the personal dictionary.
  4. Apply gateway-level lexicon rules.
  5. Call the LLM for rewrites and, later, inline style matches.
  6. Run document-level consistency checks.

### Obsidian plugin

- Upstream plugin works unmodified against the gateway.
- Vendored fork (later phase) adds `lt-mode` frontmatter and a rewrite command.
- The plugin sends **annotated JSON** in `data`, not plain text. The gateway
  must forward it unchanged in pass-through mode.

## Request flow (inline check)

1. Plugin sends `POST /v2/check`.
2. Gateway resolves the mode:
   - from an optional `writing_mode` form field (ignored by the upstream plugin), or
   - `DEFAULT_MODE`.
3. Gateway maps the mode to `level` and `enabledCategories` /
   `disabledCategories`, intersected with what the client sent.
4. Gateway forwards the request to LanguageTool.
5. Gateway filters matches:
   - drop words in `data/dictionary/<language>.txt` (read per request),
   - apply `rules/lexicon.yaml` term rules (loaded at startup).
6. Gateway returns LanguageTool-shaped JSON.

LLM suggestions are never merged into the inline path in the first
implementation. They are explicit rewrite actions.

## Request flow (rewrite)

1. Plugin sends `POST /rewrite` with `{text, language, mode, instruction}`.
2. Gateway resolves the mode and loads `prompts/<language>/<mode.prompt>`.
3. Gateway calls the OpenAI-compatible endpoint with `response_format`.
4. Response is validated (JSON shape, ordered changes, length ratio,
   numbers/links/code preserved, re-checked by LanguageTool).
5. Gateway returns `{original, rewritten, changes}`.

A failed validation gets one stricter retry; nothing unvalidated is returned.
Successful rewrites are cached in memory. Inline checks never call the LLM.

## State

| State | Location | Persistence |
|---|---|---|
| Mode profiles | `modes/*.yaml` | repo |
| Style rules | `rules/grammar_custom.xml`, `rules/lexicon.yaml` | repo |
| Personal dictionary | `data/dictionary/<lang>.txt` | repo working tree |
| LLM cache | process memory (LRU) | lost on restart |
| Logs | stdout / files | optional |

A database is intentionally absent. Revisit only if concurrent writers,
queryable history, or durable cache become requirements.

## Configuration

Environment variables, documented in `.env.example` and validated in
`gateway/src/ltplus/config.py`. No absolute paths or machine-specific defaults
in source.

## Failure modes

| Failure | Expected behaviour |
|---|---|
| LanguageTool down | Return 503 with a clear message; do not invent results |
| LLM down | Inline checks still work; rewrite returns 503 |
| LLM returns invalid JSON | Validate, retry once, then return a structured error |
| Rule file malformed | Refuse to start; fail loudly |
| Cache full | Evict least recently used |

## Non-goals

Multi-user auth, team features, rule parity, per-paragraph
mixed-language checking, and forking the third-party browser extension.