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
features" switch (off by default), a rewrite command, and a selection-scoped AI
check that reuses the existing underlines. The upstream plugin also works
against the gateway in pass-through mode.

What you can do in Obsidian:

- Check the note or selection with LanguageTool; underlines and the popover
  work as before, with writing modes applied on the gateway.
- Rewrite a selection, review changed spans, then replace or cancel.
- Check a selection, the paragraph around the cursor, or the whole document
  with AI, with hints drawn as normal (dashed) underlines.
- Let the optional auto-check follow the cursor: after 4 seconds it checks the
  sentence you are on, including an older sentence you clicked into.
- Score a note (exact counts plus 1–5 grades and up to three recommendations)
  or insert a writing topic as a blockquote.
- Hover a word for a local dictionary entry, independent of the AI switch.

See [`USAGE.md`](USAGE.md) for the full walkthrough.

> **Built with AI (open-weight models).** This is a personal project, developed
> largely with AI coding assistants running open-weight models. Changes are
> reviewed and tested before use, but expect rough edges and verify anything
> you depend on.
>
> **AI features.** Rewrites, AI checks, and the optional paragraph auto-check
> send text to the OpenAI-compatible endpoint you configure in the plugin
> settings, together with the model and (optionally) an API key stored in
> Obsidian's SecretStorage. The plugin's "Enable AI features" switch is off by
> default, and no AI request is made while it is off or while no endpoint and
> model are configured. LanguageTool checks are unaffected. If you point the
> plugin at a hosted API, that provider's terms and privacy policy apply.

> [!WARNING]
> **AI features are slow and hardware-dependent.** A local model can take
> seconds to tens of seconds per rewrite or AI check, versus milliseconds for a
> LanguageTool check. Speed depends on your CPU, GPU, and available memory; the
> first request is slower while the model loads. Start with a small model.

## Requirements

- Docker Desktop (or Docker Engine + Compose) for LanguageTool
- [uv](https://docs.astral.sh/uv/) for the gateway
- Obsidian
- *Optional:* an OpenAI-compatible LLM endpoint for `POST /rewrite`. Ollama is
  the local default but is not part of this repository: it runs natively and is
  addressed by URL. Without it, checking still works and `/rewrite` returns
  `503 llm_unavailable`.

## Quick start

For the full install, plugin build, update, and troubleshooting walkthrough,
see [`USAGE.md`](USAGE.md).

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

In Obsidian, install the plugin from `plugins/obsidian/` into
`.obsidian/plugins/languagetool-plus/` (see `plugins/obsidian/UPSTREAM.md` for
the build) and set its endpoint to
`http://127.0.0.1:8077` (the plugin appends `/v2` itself). Port `8010` is
LanguageTool directly and does not apply writing modes. Enable "AI features"
in the plugin settings to unlock "Rewrite selection with AI" and "Check
selection with AI"; the latter shows model changes as inline suggestions. An
optional "AI auto-check current sentence" setting checks after a 4-second pause
without typing or moving the cursor. The "Writing mode" setting applies to
checks and rewrites; a note can override it with `lt-mode` frontmatter.

For plugin development, `cd plugins/obsidian; npm install; npm run dev` watches
and rebuilds `main.js`. `npm run build` type-checks, `npm run test:ai` runs the
pure unit tests (also run in CI), and `npm run lint` checks the source.

## Configuration

All runtime configuration is environment-based. See `.env.example`. There are
no committed secrets. The gateway never logs document text by default.

Only LanguageTool is containerized. The gateway and the LLM are plain host
processes addressed by `LT_URL` and `LLM_BASE_URL`.

## Repository layout

See `AGENTS.md` §5 and `docs/ARCHITECTURE.md`.

## Documentation

- [`USAGE.md`](USAGE.md) — install, run, build, update, troubleshoot
- `docs/ARCHITECTURE.md` — components and request flow
- `docs/OPERATIONS.md` — health checks, restart, backup, restore
- `docs/RULES.md` — add dictionary words, term rules, and German grammar rules
- `docs/STANDARDS.md` — engineering standards
- `docs/SECURITY.md` — secrets, privacy, threat model
- `docs/LICENSING.md` — AGPL/LGPL obligations
- `docs/PROVENANCE.md` — what was borrowed and from where
- `docs/DECISIONS.md` — architecture decision records
- `docs/LLM.md` — OpenAI-compatible contract and validation
- `docs/TESTING.md` — test strategy

## Credits

Built on other people's work:

- **LanguageTool** and its German rules, by the LanguageTool team
  (LGPL-2.1-or-later).
- **LanguageTool server image**, maintained by Erikvl87
  (`Erikvl87/docker-languagetool`, LGPL-2.1).
- **Obsidian LanguageTool Integration**, by Clemens Ertle and contributors,
  including Matthew Meyers (AGPL-3.0). The fork lives in `plugins/obsidian/`.
- The MIT-licensed JavaScript libraries bundled into the plugin build.

Full attribution, copyright notices, and license texts are in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## License

AGPL-3.0-or-later. See `LICENSE`.

LanguageTool is used unmodified as a separate service under LGPL-2.1. The
Obsidian plugin fork remains AGPL-3.0. See `docs/LICENSING.md`.