# Operations

Day-to-day running, health checks, and backup for a single-user install.

## Health

```powershell
docker compose ps                      # languagetool should be Up (healthy)
Invoke-RestMethod http://127.0.0.1:8077/healthz
Invoke-RestMethod http://127.0.0.1:8010/v2/languages
```

The LanguageTool image ships its own healthcheck (`/v2/check`); Compose
reports `(healthy)` without extra configuration. The gateway has `/healthz`.
Ollama is optional and only affects `POST /rewrite`.

If `/v2/check` works but `/rewrite` returns `503 llm_unavailable`, Ollama is
not running or `LLM_BASE_URL` is wrong. Check `http://127.0.0.1:11434/v1/models`.

## Start and restart

```powershell
docker compose up -d languagetool

cd gateway
uv sync
uv run uvicorn ltplus.main:app --host 127.0.0.1 --port 8077
```

LanguageTool uses `restart: unless-stopped`. The gateway and Ollama run
natively and are restarted by whatever supervises them on the host; this repo
does not install a service manager. Mode, prompt, rule, and dictionary edits
need a gateway restart; personal dictionary edits apply on the next check.
Downloaded wordbook data applies immediately and needs no restart.

For plugin development, `cd plugins/obsidian; npm run dev` rebuilds `main.js` in
watch mode. Copy it to the vault after a successful build; the unit tests run
with `npm run test:ai` and in CI.

## What to back up

| Item | Where | Notes |
|---|---|---|
| Gateway config | `.env` | Contains no secrets by default, but may hold an API key. Back it up securely, never commit it. |
| Modes, prompts, rules, lexicon | `modes/`, `prompts/`, `rules/` | Tracked in git. |
| Personal dictionary | `data/dictionary/*.txt` | Tracked in git; edit freely. |
| Wordbook (hover dictionary) | `data/wordbook/` | Git-ignored and safe to delete; rebuild from the plugin settings or `scripts/build_dictionary.py`. German entries and aliases share one gzip per pair, so a rebuild replaces both atomically. |
| Obsidian notes | Your vault | Back up separately; not part of this repo. |
| LLM cache | Gateway memory | Volatile. Nothing to back up. |
| LanguageTool data | Docker volume/image | None. The image is pull-only; no state. |

There is no database. The repository is the source of truth for everything
except `.env` and the vault.

## Restore

1. Clone the repository at the commit you want.
2. Restore `.env` from its secure backup (or copy `.env.example`).
3. `docker compose up -d languagetool`.
4. `cd gateway; uv sync`.
5. Start the gateway and verify `/healthz`.
6. Start Ollama and pull the configured model if rewrites are wanted.

## Logs

- LanguageTool: `docker compose logs -f languagetool`
- Gateway: stdout of the uvicorn process. Do not log document text; the
  gateway does not.
- Ollama: its own service logs.