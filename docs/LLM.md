# LLM contract

## Endpoint

Any OpenAI-compatible server:

```
POST {LLM_BASE_URL}/chat/completions
GET  {LLM_BASE_URL}/models
```

Ollama exposes this at `http://127.0.0.1:11434/v1`. Use the official `openai`
SDK pointed at `LLM_BASE_URL`; do not hand-roll HTTP.

## Configuration

| Variable | Meaning | Default |
|---|---|---|
| `LLM_BASE_URL` | OpenAI-compatible base URL | `http://127.0.0.1:11434/v1` |
| `LLM_API_KEY` | API key; `ollama` for local | `ollama` |
| `LLM_MODEL` | Model identifier | `qwen2.5:14b-instruct` |
| `LLM_TIMEOUT_SECONDS` | Per-request timeout | `30` |
| `LLM_MAX_TOKENS` | Response cap | `1024` |
| `LLM_CONTEXT_CHARS` | Conservative chunk budget | `12000` |

No model name is hard-coded in source. Model choice belongs to configuration.

## Request shape

Standard fields only: `model`, `messages`, `temperature`, `max_tokens`,
`response_format`, `stream`. No provider-specific parameters.

## Output

Require JSON:

```json
{
  "changes": [
    {
      "original": "…",
      "replacement": "…",
      "category": "style",
      "explanation": "…"
    }
  ]
}
```

Use `response_format={"type": "json_object"}`. Probe for `json_schema` and use
it only if the endpoint accepts it. Always validate; never trust the flag.

## Validators

Reject or retry when:

- output is not valid JSON or does not match the schema,
- a replacement is empty where text is required,
- length ratio is outside 0.5–2.0,
- numbers, names, URLs, or code blocks changed,
- re-checking the replacement with LanguageTool adds new errors,
- the model echoes the input unchanged (for rewrite requests).

## Chunking

- Chunk by paragraph against `LLM_CONTEXT_CHARS`, with margin.
- Do not assume a tokenizer. `tiktoken` is OpenAI-specific and misleading for
  other models.
- Preserve paragraph boundaries so offsets remain mappable.

## Determinism

`temperature` 0.1–0.3 for corrections, 0 for consistency checks. `seed` is
best-effort. The eval set, not the seed, catches drift.

## Failure handling

- Timeout or connection error → 503 with a stable error code.
- Invalid JSON → one retry with a stricter instruction, then 502.
- Never fall back to unvalidated text.

## Privacy

- Local Ollama is the default; no text leaves the machine.
- Hosted endpoints are opt-in and are the user's responsibility.
- Do not log prompts or completions by default.