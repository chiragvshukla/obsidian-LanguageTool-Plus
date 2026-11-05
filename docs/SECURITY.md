# Security and privacy

## Secrets

- Secrets never live in this repository. `.env` is gitignored; `.env.example`
  contains placeholders only.
- Agents and contributors must not read, search, list, or copy `.env`,
  credential files, keychains, `~/.ssh`, browser profiles, or token stores.
- The gateway reads configuration from environment variables. It does not
  parse files for credentials.
- If a secret is committed accidentally: rotate it first, then remove it from
  history. Do not just delete the file.

## Deployment posture

- Every service binds to `127.0.0.1` on the host by default.
- No authentication is implemented because this is a single-user local tool.
  Do not expose the gateway or LanguageTool to a network without adding auth
  and TLS.
- CORS is not enabled. Obsidian's `requestUrl` bypasses browser CORS.
- Containers run as non-root where the upstream image allows it.

## Privacy

- Document text is sensitive. It is sent only to the configured LanguageTool
  and LLM endpoints.
- Nothing is persisted by default. The LLM cache is in memory.
- Logs must not contain document text, prompts, completions, or personal names.
- If a hosted LLM is configured, the user is responsible for its data policy.
  The default is a local Ollama endpoint.

## Model trust boundary

- Treat LLM output as untrusted input.
- The model has no tools, file access, or network access.
- Prompt injection from document text is expected. The gateway only accepts
  structured JSON, validates it, and re-checks the result with LanguageTool.
- Reject output that changes numbers, names, URLs, or code blocks.

## Dependencies

- Pin versions with `uv.lock`.
- Prefer maintained packages with compatible licenses.
- CI should run a dependency audit before release.
- Do not add a dependency for a few lines of code that the standard library
  covers.

## Backups

Only these are worth backing up: `data/dictionary/`, `rules/`, `modes/`, and
`prompts/`. Everything else is reproducible.