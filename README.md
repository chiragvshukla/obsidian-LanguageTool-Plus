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

The optional Obsidian plugin fork adds per-note modes and a rewrite command.
The upstream plugin already works against the gateway in pass-through mode.

> **Status:** scaffold. The gateway currently exposes `/healthz` only. Feature
> work follows `docs/PLAN.md`.

## Requirements

- Docker Desktop (or Docker Engine + Compose)
- [uv](https://docs.astral.sh/uv/) for local development
- Obsidian
- Optional: a local LLM served by Ollama, or any OpenAI-compatible API

## Quick start

```powershell
Copy-Item .env.example .env
# edit .env if needed; never commit it

docker compose up -d languagetool ollama
ollama pull qwen2.5:14b-instruct
docker compose up -d gateway

Invoke-RestMethod http://127.0.0.1:8077/healthz
```

In Obsidian, install the LanguageTool plugin and set its endpoint to
`http://127.0.0.1:8077` (the plugin appends `/v2` itself). Until Phase 1 is
implemented, point it at `http://127.0.0.1:8010` for plain LanguageTool.

## Configuration

All runtime configuration is environment-based. See `.env.example`. There are
no committed secrets. The gateway never logs document text by default.

## Repository layout

See `AGENTS.md` §5 and `docs/ARCHITECTURE.md`.

## Documentation

- `docs/PLAN.md` — phases and acceptance criteria
- `docs/ARCHITECTURE.md` — components and request flow
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