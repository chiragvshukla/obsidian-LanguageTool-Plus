# Engineering standards

## Language and tooling

- Python 3.12, managed with `uv`.
- `ruff` for lint and formatting, line length 100.
- `mypy --strict` for the `ltplus` package.
- `pytest` with `pytest-asyncio`; `respx` for HTTP mocking.
- FastAPI + pydantic v2; settings via `pydantic-settings`.

## Code

- Public functions and methods are fully typed. Avoid `Any`; if unavoidable,
  comment why.
- Prefer small, pure functions. Isolate I/O at the edges.
- No mutable module-level state except a settings singleton and the cache.
- No bare `except`. Catch specific exceptions and preserve context with
  `raise ... from exc`.
- Every external call has a timeout.
- Validate at trust boundaries: request bodies, LLM output, YAML, XML.
- Do not log document text, prompts, completions, or secrets. Log IDs, counts,
  durations, and error classes.
- Keep dependencies minimal. Every addition needs a one-line justification and
  a compatible license.

## Configuration

- All configuration comes from environment variables.
- No absolute paths, hostnames, ports, usernames, or model names in source.
- Defaults must be safe and documented in `.env.example`.
- The app must start with an empty environment and fail with a clear message if
  a required dependency is unavailable.

## HTTP and errors

- Return structured JSON errors: `{ "error": { "code", "message" } }`.
- Map LanguageTool failures to 502/503, never to a silent empty result.
- Never expose stack traces or upstream response bodies to clients.
- Timeouts are explicit and configurable.

## Testing

- Every behaviour change has a test.
- Prefer deterministic tests. Mock external HTTP with `respx`.
- Keep a golden corpus for LanguageTool results and an eval set for LLM output.
- No test may depend on a live LLM, the public LanguageTool API, or the user's
  machine.

## Documentation

- Update `docs/` with code changes.
- Record non-trivial choices in `docs/DECISIONS.md`.
- Record borrowed code or data in `docs/PROVENANCE.md`.

## Commits

- Small, focused commits. One concern each.
- Message format: `type(scope): summary` (Conventional Commits).
- Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `build`, `ci`.
- Do not commit generated files, secrets, or local paths.

## Performance budgets

- Inline check p95 < 100 ms steady state on localhost; gateway overhead p95 < 50 ms.
- Rewrite p95 < 5 s locally with the configured model.
- Cache lookups O(1); bounded memory.

## Definition of done

Tests pass, `scripts/check.ps1` passes, docs updated, no secrets, no
machine-specific assumptions, diff reviewable.