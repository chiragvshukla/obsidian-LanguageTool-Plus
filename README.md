# LanguageToolPlus

A self-hosted German/English writing assistant for Obsidian. It runs a local
gateway in front of [LanguageTool](https://github.com/languagetool-org/languagetool)
and, if you want, an OpenAI-compatible LLM for rewriting and style advice.

No account, no telemetry, no database. One person, one vault, one machine.

## What it does

- Check a note or a selection for grammar, spelling, and style.
- Pick a writing mode: `neutral`, `formal`, `casual`, `academic`, or `business`.
  A note can override it with `lt-mode` frontmatter.
- Rewrite a selection and review the changed spans before applying them.
- Check a selection, the current paragraph, or the whole document with an LLM.
- Score a note: exact LanguageTool counts plus 1–5 grades and up to three
  recommendations.
- Insert a writing topic as a blockquote, for practice.
- Hover any word for a local German/English dictionary entry.

AI features are off by default. Everything except the AI commands works with
LanguageTool alone.

## How it works

```
Obsidian plugin  ->  gateway (127.0.0.1:8077)  ->  LanguageTool (127.0.0.1:8010)
                                             \->  optional LLM (Ollama or hosted)
```

The gateway speaks LanguageTool's `/v2/check` and `/v2/languages`, so the
upstream plugin works against it unchanged. It adds writing modes, a personal
dictionary, style rules, and the `/rewrite`, `/score`, `/topic`, and
`/dictionary` endpoints. Only LanguageTool runs in a container; the gateway and
the LLM are ordinary host processes reached by URL.

## Requirements

- Docker Desktop (or Docker Engine + Compose). On Windows, use the WSL2 backend
  (`wsl --install` if WSL2 is missing); the image is Linux-only and does not run
  on WSL1.
- [uv](https://docs.astral.sh/uv/) and Python 3.12 (uv installs the interpreter).
- Node.js 18+ and npm, to build the plugin.
- Obsidian desktop 1.8.10 or newer.
- *Optional:* an OpenAI-compatible LLM endpoint. Ollama is the local default but
  is not part of this repository. Without one, checking still works and
  `/rewrite` returns `503 llm_unavailable`.

## Install

Run these from the repository root. PowerShell is shown; any shell works.

1. **Configure.**

   ```powershell
   Copy-Item .env.example .env    # defaults fit a local install
   ```

2. **Start LanguageTool.** It is the only container.

   ```powershell
   docker compose up -d languagetool
   ```

3. **Start the gateway.** Leave it running; use a second terminal for the rest.

   ```powershell
   cd gateway
   uv sync
   uv run uvicorn ltplus.main:app --host 127.0.0.1 --port 8077
   Invoke-RestMethod http://127.0.0.1:8077/healthz
   ```

4. **Build and install the plugin.** From the repository root:

   ```powershell
   cd plugins/obsidian
   npm install
   npm run build
   ```

   Copy `main.js`, `manifest.json`, and `styles.css` into
   `<vault>/.obsidian/plugins/languagetool-plus/`, then enable
   **LanguageTool Plus** in Obsidian's community plugins.

5. **Point the plugin at the gateway.** In the plugin settings choose a custom
   endpoint and enter `http://127.0.0.1:8077` — the plugin appends `/v2`
   itself, so do not add it. Port `8010` is LanguageTool directly and does not
   apply writing modes.

The full walkthrough — update procedure, troubleshooting, uninstall — is in
[`USAGE.md`](USAGE.md).

## Optional AI

Set an endpoint and model under *Settings → LanguageTool Plus → AI features*.
Ollama works at `http://127.0.0.1:11434/v1`; any OpenAI-compatible server works
too. The API key, if you need one, is stored in Obsidian's SecretStorage. With
no endpoint configured, AI stays off.

See [`docs/LLM.md`](docs/LLM.md) for the request contract and validation.

## Privacy and limits

Your text goes to the LanguageTool instance and, only when you use an AI
command, to the LLM endpoint you configured. Nothing else is sent. Hosted
providers apply their own terms and privacy policy.

AI is slow and hardware-dependent: the LanguageTool check takes milliseconds, a
local model takes seconds to tens of seconds, and the first request is slower
while it loads. Start with a small model.

This is a personal project, developed largely with AI coding assistants running
open-weight models. Changes are reviewed and tested before use, but expect rough
edges and verify anything you depend on.

## Configuration

Runtime configuration is environment-based; see `.env.example`. There are no
committed secrets, and the gateway does not log document text by default. See
[`docs/SECURITY.md`](docs/SECURITY.md) for the threat model.

## Development

```powershell
# Gateway: lint, types, and tests
cd gateway
uv run pytest                 # or: pwsh ../scripts/check.ps1 for the full check

# Plugin
cd ../plugins/obsidian
npm run dev                   # rebuild main.js on change
npm run test:ai               # pure unit tests, also run in CI
npm run lint
```

CI runs the same checks on every push. See
[`docs/TESTING.md`](docs/TESTING.md) for the test layers.

## Documentation

- [`USAGE.md`](USAGE.md) — install, run, build, update, troubleshoot
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — components and request flow
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md) — health checks, restart, backup, restore
- [`docs/RULES.md`](docs/RULES.md) — dictionary words, term rules, German grammar rules
- [`docs/SECURITY.md`](docs/SECURITY.md) — secrets, privacy, threat model
- [`docs/LICENSING.md`](docs/LICENSING.md) — AGPL/LGPL obligations
- [`docs/PROVENANCE.md`](docs/PROVENANCE.md) — what was borrowed and from where
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — architecture decision records
- [`docs/LLM.md`](docs/LLM.md) — OpenAI-compatible contract and validation
- [`docs/STANDARDS.md`](docs/STANDARDS.md) — engineering standards
- [`docs/TESTING.md`](docs/TESTING.md) — test strategy

## Credits

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
Obsidian plugin fork remains AGPL-3.0. See [`docs/LICENSING.md`](docs/LICENSING.md).