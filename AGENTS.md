# AGENTS.md — LanguageToolPlus

Guidance for AI agents and humans working in this repository. Read this file,
`docs/ARCHITECTURE.md`, and `docs/PLAN.md` before changing anything.

## 1. What this project is

A personal, self-hosted German/English writing assistant for Obsidian:

- **LanguageTool OSS** (LGPL-2.1) runs unmodified as a separate service. We do
  not fork or patch its Java code.
- **This gateway** (Python/FastAPI) is API-compatible with LanguageTool's
  `/v2/check`, so the Obsidian plugin can talk to it.
- **An OpenAI-compatible LLM** provides style suggestions, rewrites, and
  document-level consistency checks.
- **A forked Obsidian plugin** (AGPL-3.0, vendored under `plugins/obsidian/`)
  adds per-note modes and a rewrite command.

No database. State lives in config files, rule files, a flat dictionary, and an
in-memory cache.

## 2. Hard rules

### Secrets

- Never read, search, list, open, or copy `.env`, `.env.*` (except
  `.env.example`), credential files, keychains, `~/.ssh`, browser profiles, or
  token stores.
- Never write a secret, token, API key, or password into any file, test
  fixture, log, or commit.
- Configuration is read from environment variables at runtime. `.env.example`
  contains placeholders only.
- If a task appears to require a secret, stop and ask.

### Licensing and provenance

- Do not copy code, rules, prose, or data unless its license allows it. Record
  every borrowed item in `docs/PROVENANCE.md` with source URL, license, and
  commit/version.
- Explicitly forbidden: the third-party browser extension,
  LanguageTool Closed rules, and non-open content from the LanguageTool
  website.
- Preserve all license headers and NOTICE files. Do not relicense third-party
  code.
- Any new dependency must have a compatible license and a one-line
  justification.

### Portability

- No absolute paths, hostnames, ports, usernames, GPU IDs, or model names
  hard-coded in source. Use `gateway/src/ltplus/config.py` and `.env.example`.
- Code must run on a clean machine from `docker compose up -d languagetool`,
  `uv sync`, and any OpenAI-compatible endpoint the user configures.
- Do not assume Windows, Linux, or macOS specifics unless isolated behind a
  documented boundary.

### Honesty and scope

- Do not invent APIs, libraries, flags, or endpoints. Verify against upstream
  docs or source before use.
- Ask before adding a dependency, changing a public interface, altering the
  data model, or expanding scope.
- Do not silently implement multiple phases at once.
- Report what you changed, what you tested, and what you did not verify.

## 3. Architecture invariants

- `/v2/check` must stay compatible with the request shape the Obsidian plugin
  sends: `data` (annotated JSON), `language`, `enabledOnly`, `level`,
  `enabledCategories`, `disabledCategories`, `enabledRules`, `disabledRules`,
  `preferredVariants`, `motherTongue`.
- `/v2/languages` must return the same shape as LanguageTool.
- Inline matches come from LanguageTool. LLM output is for explicit rewrites
  and later inline style matches; it never overrides a deterministic grammar
  match.
- Modes are declarative (`modes/*.yaml`), not code branches.
- The LLM interface is OpenAI-compatible `/v1/chat/completions` only. No
  provider-specific fields.
- No database. If persistence becomes necessary, ask first; SQLite would be the
  default, never Postgres for a single user.

## 4. Coding standards

- Python 3.12, managed with `uv`. Run commands from `gateway/`.
- `ruff` for lint/format, `mypy --strict` for types, `pytest` for tests.
- FastAPI + pydantic v2. Settings via `pydantic-settings`.
- Public functions are fully typed. No untyped `dict` blobs at boundaries; use
  models.
- No bare `except`; no swallowed exceptions. Every network call has a timeout
  and a bounded retry policy.
- Structured logging. Never log document text, prompts, or completions by
  default.
- Validate at trust boundaries: request bodies, LLM JSON, YAML/XML rules.
- Treat model output as untrusted input.
- Keep functions small and pure where possible; isolate I/O.

## 5. Repository map

```
AGENTS.md                 this file
docs/                     architecture, plan, standards, security, licensing
docker-compose.yml        LanguageTool only (rules bind-mounted, no custom image)
gateway/                  FastAPI gateway (Python 3.12, uv, runs natively)
  src/ltplus/             application package
  tests/                  unit and integration tests
modes/                    declarative writing-mode profiles
rules/                    grammar_custom.xml and lexicon rules
prompts/                  per-mode German prompts
data/dictionary/          flat word lists (no database)
plugins/obsidian/         vendored AGPL Obsidian plugin fork (later phase)
scripts/                  developer scripts
```

## 6. Commands

```powershell
cd gateway
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

```powershell
# from repository root
docker compose up -d languagetool

cd gateway
uv run uvicorn ltplus.main:app --host 127.0.0.1 --port 8077

# Ollama is external; it is addressed only through LLM_BASE_URL.
```

## 7. Definition of done

- Tests cover the change (unit and, where relevant, integration).
- `scripts/check.ps1` passes.
- Docs updated; non-trivial choices recorded in `docs/DECISIONS.md`.
- No secrets, no machine-specific assumptions, no new unlicensed code.
- The change is small enough to review in one sitting.

## 8. Workflow

1. Read `docs/PLAN.md`; pick one phase task.
2. Confirm ambiguity with the user before coding.
3. Write a failing test.
4. Implement the smallest change that passes.
5. Run the full check suite.
6. Update docs and provenance.

## 9. Out of scope

Team features, multi-user auth, rule parity, per-paragraph
mixed-language checking, mobile apps, and redistributing the third-party
browser extension.