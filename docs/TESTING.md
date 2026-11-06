# Testing

## Layers

| Layer | What | Tools |
|---|---|---|
| Unit | Pure logic: mode mapping, validators, dictionary filter, offset map | pytest |
| Integration | Gateway ↔ mocked LanguageTool / LLM | respx, httpx |
| Golden | Deterministic LanguageTool results per mode | pytest + fixtures |
| Eval | LLM quality on a fixed German corpus | pytest marker `eval` |
| End-to-end | Obsidian plugin ↔ gateway | plugin's wdio harness, later |
| Smoke | `docker compose up`, healthchecks | script |

## Rules

- No test depends on a live LLM, the public LanguageTool API, or the user's
  machine.
- Mock HTTP with `respx`. Keep fixtures small and readable.
- Every bug fix gets a regression test.
- Golden fixtures record the exact LanguageTool version that produced them.
- Eval tests are marked and excluded from the default run:

```powershell
uv run pytest -m "not eval"
```

## Stub LLM

Add a tiny FastAPI app under `tests/stubs/` that implements:

- `GET /v1/models`
- `POST /v1/chat/completions`

It returns canned JSON per scenario. This keeps CI fast and deterministic.

## What to test first

1. Mode → LanguageTool params, including the intersection rule.
2. Dictionary filtering by word and language.
3. Lexicon rule compilation and offsets.
4. LLM validator chain (reject bad length, changed numbers, invalid JSON).
5. Annotated-JSON round-trip once Phase 4 starts.

## Plugin units

The plugin's pure helpers have no Obsidian dependency and run under `tsx`:
match mapping, paragraph/sentence bounds, context trimming, dictionary word
extraction, frontmatter bounds, document chunking, rewrite guards, and the
auto-check trigger decision. CI runs them after build and lint.

```powershell
cd plugins/obsidian
npm run test:ai
```

A behaviour change in `aiCheck.ts`, `dictionaryHelpers.ts`, `documentChunk.ts`,
`practiceHelpers.ts`, or `rewriteGuard.ts` needs a case there. The trigger is a
pure function (`shouldAutoCheckAfterUpdate`) precisely so it can be tested
without a live CodeMirror view.

## Commands

```powershell
cd gateway
uv run pytest
uv run pytest -m eval
```

## Quality bar

- Core logic: high coverage, including edge cases.
- No flaky tests. If a test is timing-dependent, fix the design.
- Evals compare against a stored baseline; a prompt change must show the delta.