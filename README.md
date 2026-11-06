# LanguageToolPlus

A personal, self-hosted German/English writing assistant for Obsidian.

It combines three open parts:

- [LanguageTool](https://github.com/languagetool-org/languagetool) (LGPL-2.1)
  as the deterministic grammar, spelling, and style engine.
- A small FastAPI **gateway** that is API-compatible with LanguageTool's
  `/v2/check`, adds writing modes, a personal dictionary, style-guide rules,
  rewrites, and document-level consistency checks.
- An OpenAI-compatible **LLM** for style and fluency work. Ollama is the local
  default; any compatible endpoint works.

The Obsidian plugin is vendored under `plugins/obsidian/` with an "Enable AI
features" switch (off by default) and a rewrite command. The upstream plugin
also works against the gateway in pass-through mode.

> **Status:** Phase 3 plus the plugin fork's AI switch and rewrite command. The
> gateway proxies `/v2/check` and `/v2/languages`, applies writing modes, and
> serves `POST /rewrite`. Inline AI suggestions follow `docs/PLAN.md`.

## Requirements

- Docker Desktop (or Docker Engine + Compose) for LanguageTool
- [uv](https://docs.astral.sh/uv/) for the gateway
- Obsidian
- *Optional:* an OpenAI-compatible LLM endpoint for `POST /rewrite`. Ollama is
  the local default but is not part of this repository: it runs natively and is
  addressed by URL. Without it, checking still works and `/rewrite` returns
  `503 llm_unavailable`.

## Quick start

```powershell
Copy-Item .env.example .env
# edit .env if needed; never commit it

# LanguageTool (the only container)
docker compose up -d languagetool

# Gateway, natively
cd gateway
uv sync
uv run uvicorn ltplus.main:app --host 127.0.0.1 --port 8077

Invoke-RestMethod http://127.0.0.1:8077/healthz
```

Ollama is expected to be running already, at the URL in `LLM_BASE_URL`
(`http://127.0.0.1:11434/v1` by default). It is only used by `POST /rewrite`.
Any compatible server works; the gateway knows nothing about which one.

Try a rewrite:

```powershell
Invoke-RestMethod http://127.0.0.1:8077/rewrite `
  -Method Post -ContentType "application/json" `
  -Body '{"text":"Das ist ein Tset.","language":"de-DE","mode":"formal"}'
```

In Obsidian, install the plugin from `plugins/obsidian/` (see
`plugins/obsidian/UPSTREAM.md` for the build) and set its endpoint to
`http://127.0.0.1:8077` (the plugin appends `/v2` itself). Port `8010` is
LanguageTool directly and does not apply writing modes. Enable "AI features"
in the plugin settings to unlock "Rewrite selection with AI".

## Configuration

All runtime configuration is environment-based. See `.env.example`. There are
no committed secrets. The gateway never logs document text by default.

Only LanguageTool is containerized. The gateway and the LLM are plain host
processes addressed by `LT_URL` and `LLM_BASE_URL`.

## Repository layout

See `AGENTS.md` §5 and `docs/ARCHITECTURE.md`.

## Documentation

- `docs/PLAN.md` — phases and acceptance criteria
- `docs/ARCHITECTURE.md` — components and request flow
- `docs/RULES.md` — add dictionary words, term rules, and German grammar rules
- `docs/STANDARDS.md` — engineering standards
- `docs/SECURITY.md` — secrets, privacy, threat model
- `docs/LICENSING.md` — AGPL/LGPL obligations
- `docs/PROVENANCE.md` — what was borrowed and from where
- `docs/DECISIONS.md` — architecture decision records
- `docs/LLM.md` — OpenAI-compatible contract and validation
- `docs/TESTING.md` — test strategy

## License

AGPL-3.0-or-later. See `LICENSE`.

LanguageTool is used unmodified as a separate service under LGPL-2.1. The
Obsidian plugin fork remains AGPL-3.0. See `docs/LICENSING.md`.