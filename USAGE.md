# Usage

How to install, run, and build LanguageToolPlus on one machine. The examples
use PowerShell; the equivalent commands work in any shell.

## What runs where

| Component | Runs as | Default address |
|---|---|---|
| LanguageTool | Docker container | `http://127.0.0.1:8010` |
| Gateway | Native Python process | `http://127.0.0.1:8077` |
| LLM (optional) | Native process, e.g. Ollama | `http://127.0.0.1:11434/v1` |
| Obsidian plugin | Obsidian desktop | Vault settings |

Only LanguageTool is containerized. The gateway and the LLM are host processes
addressed by URL, so either can be replaced without touching the other.

## Prerequisites

- Docker Desktop (or Docker Engine + Compose)
- [uv](https://docs.astral.sh/uv/) and Python 3.12 (uv installs the interpreter)
- Node.js 18+ and npm, to build the plugin
- Obsidian desktop 1.8.10 or newer
- *Optional:* Ollama or any OpenAI-compatible endpoint for AI features

## 1. Configure

From the repository root:

```powershell
Copy-Item .env.example .env
```

Edit `.env` only if the defaults do not fit. The file holds no secrets by
default; if you add an API key, keep `.env` out of version control. The gateway
reads `.env` from the repository root.

## 2. Start LanguageTool

```powershell
docker compose up -d languagetool
docker compose ps
```

Wait until the container reports `(healthy)`. The first start pulls the image
and takes a few minutes. Verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8010/v2/languages
```

Custom German rules come from `rules/grammar_custom.xml` through a read-only
bind mount. Editing that file needs `docker compose restart languagetool`, not
an image rebuild.

## 3. Start the gateway

In its own terminal:

```powershell
cd gateway
uv sync
uv run uvicorn ltplus.main:app --host 127.0.0.1 --port 8077
```

Verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8077/healthz
```

A check through the gateway:

```powershell
Invoke-RestMethod http://127.0.0.1:8077/v2/check `
  -Method Post `
  -Body @{ text = "Das ist ein Tset."; language = "de-DE" }
```

Port `8010` talks to LanguageTool directly and does not apply writing modes,
the personal dictionary, style rules, or consistency checks. Use `8077` for
everything.

## 4. Optional: start an LLM

AI rewrites and AI checks need an OpenAI-compatible `/v1/chat/completions`
endpoint. Ollama is the local default:

```powershell
ollama serve
ollama pull gemma4:e4b-it-q4_K_M
```

The model name above is only `.env`'s default. Pull whatever you set in
`LLM_MODEL`, or point `LLM_BASE_URL` at a hosted provider and set
`LLM_API_KEY`. Verify:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/v1/models
```

Smoke-test a rewrite through the gateway:

```powershell
Invoke-RestMethod http://127.0.0.1:8077/rewrite `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"text":"Der Mädchen geht zur Schule.","language":"de-DE","mode":"neutral"}'
```

Without a reachable LLM, `/v2/check` still works and `/rewrite` returns
`503 llm_unavailable`.

## 5. Build the Obsidian plugin

```powershell
cd plugins/obsidian
npm install
npm run build
```

`npm run build` type-checks and writes `main.js`. The file is a gitignored
build artifact. Optional checks:

```powershell
npm run test:ai     # self-check for AI match mapping and paragraph bounds
npm run lint
```

## 6. Install the plugin in Obsidian

Create the plugin folder in your vault and copy the three runtime files:

```powershell
$vault = "C:\path\to\YourVault"
$dst = Join-Path $vault ".obsidian\plugins\obsidian-languagetool-plugin"
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item main.js, manifest.json, styles.css $dst -Force
```

Then in Obsidian:

1. Turn off Restricted Mode under **Settings → Community plugins**.
2. Reload the app or use the command palette's **Reload app without saving**.
3. Enable **LanguageTool Integration**.

Configure the plugin under **Settings → LanguageTool Integration**:

- **Endpoint:** custom, `http://127.0.0.1:8077` — the plugin appends `/v2/check`
  itself, so do not add `/v2`.
- **Language:** German, English, or automatic detection.
- **Writing mode:** `neutral`, `formal`, `casual`, `academic`, or `business`.
- **Enable AI features:** off by default. Required for rewrites and AI checks.
- **AI auto-check current paragraph:** optional, off by default. Waits 10
  seconds after typing, then checks the paragraph around the cursor.

Do not overwrite `data.json` when updating; it holds the plugin's settings and
possibly credentials.

## 7. Use it

- **Check Text** checks the document, or only the selection when there is one.
  **Toggle Automatic Checking** checks as you type.
- Click an underline for replacements, ignore, and the rule/category details.
- Per-note frontmatter overrides:

  ```yaml
  lt-language: en-GB
  lt-mode: formal
  lt-autocheck: true
  ```

- AI commands (require **Enable AI features**):
  - **Rewrite selection with AI** — rewrites and highlights changed spans for
    review.
  - **Check selection with AI** — correctness pass using `neutral`, shown as
    normal underlines.
  - **Check current paragraph with AI** — same pass on the paragraph around the
    cursor.

AI output is validated by the gateway before it reaches the plugin. Numbers,
links, and code blocks are protected.

## 8. Update

From the repository root:

```powershell
docker compose up -d languagetool   # applies image/compose changes
```

Restart the gateway process after gateway, mode, prompt, or rule changes.
Rebuild and copy the plugin after plugin changes:

```powershell
cd plugins/obsidian
npm install
npm run build
Copy-Item main.js, manifest.json, styles.css $dst -Force
```

Personal dictionary edits in `data/dictionary/*.txt` apply on the next check.
Mode, prompt, rule, and lexicon edits apply after a gateway restart.

## 9. Run the checks

```powershell
# Gateway: lint, format, types, tests
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check.ps1

# Plugin
cd plugins/obsidian
npm run build
npm run test:ai
npm run lint
```

The gateway suite mocks LanguageTool and the LLM; it needs neither running.
`npm run test:e2e` is the optional Obsidian harness.

## 10. Troubleshooting

| Symptom | Likely cause |
|---|---|
| `/rewrite` returns `503 llm_unavailable` | Ollama or the configured endpoint is down, or `LLM_BASE_URL` is wrong. |
| `/rewrite` returns `502 llm_validation_failed` | The model returned invalid JSON, changed protected text, or added new LanguageTool errors. Try again or use a stronger model. |
| Plugin says it cannot fetch languages | Endpoint is not the gateway, or it includes `/v2`. Use `http://127.0.0.1:8077`. |
| No underlines in code, math, or frontmatter | By design; those regions are skipped. |
| LT checks work but AI does nothing | AI features are off, no LLM is reachable, or the paragraph is too long for one automatic pass (2,000 characters). |
| AI auto-check seems idle | It runs 10 seconds after the last edit and only while the editor has focus. Use **Check current paragraph with AI** to test immediately. |
| Port already in use | Stop the old gateway/container. The defaults are `8010` for LanguageTool and `8077` for the gateway. |
| Container is unhealthy | `docker compose logs languagetool`; wait for the first start, then check memory limits. |

## 11. Stop and uninstall

```powershell
docker compose down            # stop and remove the LanguageTool container
```

Stop the gateway with `Ctrl+C` in its terminal. Disable or remove the plugin
from **Settings → Community plugins**. Your vault notes are never touched by
the gateway; only the plugin changes text, and only when you accept a
suggestion or a rewrite.

## Security notes

- LanguageTool and the gateway bind to `127.0.0.1` only.
- The gateway does not log document text.
- AI features are opt-in. When enabled, rewritten or checked text is sent to
  the configured LLM endpoint. With a hosted provider, that provider's terms
  and privacy policy apply.
- Never commit `.env`. See `docs/SECURITY.md` and `docs/OPERATIONS.md`.