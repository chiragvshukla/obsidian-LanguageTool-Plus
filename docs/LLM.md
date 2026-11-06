# LLM contract

The LLM is optional at runtime. `POST /v2/check` never calls it; only an
explicit `POST /rewrite` does. If the endpoint is down, inline checking keeps
working.

## Endpoint

Any OpenAI-compatible server:

```
POST {LLM_BASE_URL}/chat/completions
```

Ollama exposes this at `http://127.0.0.1:11434/v1`. The gateway uses the
official `openai` SDK, so no provider-specific fields are sent.

## Configuration

| Variable | Meaning | Default |
|---|---|---|
| `LLM_BASE_URL` | OpenAI-compatible base URL | `http://127.0.0.1:11434/v1` |
| `LLM_API_KEY` | API key; `ollama` for local | `ollama` |
| `LLM_MODEL` | Model identifier | `gemma4:e4b-it-q4_K_M` |
| `LLM_TIMEOUT_SECONDS` | Per-request timeout | `60` |
| `LLM_MAX_TOKENS` | Response cap | `4096` |
| `LLM_CONTEXT_CHARS` | Maximum rewrite input, in characters | `12000` |
| `LLM_CACHE_SIZE` | Successful rewrites kept in memory | `128` |

No model name is hard-coded in source. Model choice belongs to configuration.

## Per-request overrides

A client may override the endpoint, key, and model for one request:

| Header | Overrides |
|---|---|
| `X-LLM-Base-URL` | `LLM_BASE_URL` |
| `X-LLM-API-Key` | `LLM_API_KEY` |
| `X-LLM-Model` | `LLM_MODEL` |

The Obsidian plugin uses these headers so its settings win over `.env`. Missing
headers keep the gateway defaults, so the HTTP API stays usable on its own.
Clients are cached by base URL and a hash of the key; the rewrite cache key also
includes the model, so switching models never returns another model's result.

`POST /llm/models` lists the endpoint's models for the plugin picker:

```json
{ "base_url": "https://example.test/v1", "api_key": "secret" }
```

Response: `{"models": ["model-a", "model-b"]}`. The key is optional. The gateway
requests `{base_url}/models` and returns `502`/`503`/`504` on upstream failures.
Only `http://` and `https://` URLs are accepted.

## `POST /rewrite`

Request (JSON):

```json
{
  "text": "Das ist ein Tset.",
  "language": "de-DE",
  "mode": "formal",
  "instruction": "Kürzer, bitte."
}
```

- `text` is required and must not exceed `LLM_CONTEXT_CHARS`.
- `language` defaults to `DEFAULT_LANGUAGE`. Prompts exist for `de` and `en`.
- `mode` defaults to `DEFAULT_MODE`.
- `instruction` is optional.

Response:

```json
{
  "original": "Das ist ein Tset.",
  "rewritten": "Das ist ein Test.",
  "changes": [
    {
      "original": "Tset",
      "replacement": "Test",
      "category": "grammar",
      "explanation": "Tippfehler",
      "offset": 12,
      "length": 4
    }
  ]
}
```

`offset` and `length` locate the change in the original text. They let the
plugin highlight changed spans and turn a change into an inline suggestion
without searching for the string again.

Changes are applied by the gateway, in order, to produce `rewritten`. The
plugin uses `rewritten` for the rewrite modal and `changes` for review,
highlighting, and inline AI suggestions.

## Prompts

`prompts/<language>/<mode>.md`, where the mode file names only the file
(`prompt: formal.md`). All modes must have a prompt for every language
directory; a missing file is a startup error. Editing a prompt needs a gateway
restart.

## Request shape

Standard fields only: `model`, `messages`, `temperature`, `max_tokens`,
`response_format`. No `stream`.

Always set `response_format` (ADR-010). The gateway asks for `json_schema`
derived from the output model; if the server rejects it with a 400, the call is
retried once with `json_object`.

## Output and validation

The model must answer:

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

Every response is validated before it is returned:

- JSON parses and matches the schema.
- Changes are applied in text order. Out-of-order changes are reordered; a
  change that overlaps one already applied is dropped. A change whose
  `original` is nowhere in the source still fails validation.
- Length ratio is within 0.5–2.0.
- Numbers, URLs, emails, inline code, and fenced code are unchanged.
- Re-checking `rewritten` with LanguageTool uses the mode's parameters
  (`level`, categories, enabled/disabled rules) and compares correctness
  findings per rule ID. A new rule, or one that now occurs more often, fails
  validation. Findings with `issueType: style` never do.
- If the whole set adds a correctness finding, each of up to 12 changes is
  checked alone; the unsafe ones are dropped and the rest is returned with
  `dropped: N` (ADR-021). If every change is unsafe, the request fails.

Replies are parsed tolerantly before failing: think blocks, code fences, and
prose around the object are stripped, and the last complete JSON object is
used. If the reply was cut off at the token cap, one retry runs with twice the
budget (capped at 16384). If no JSON object matches the schema, one repair call
asks the model to reformat its own answer. Only then does the request fail with
`llm_invalid_json`, `llm_truncated`, or `llm_empty_answer`. Each failure logs
structure only — length, finish reason, and the presence of fences or a think
block — never the text. Unvalidated model text is never returned.

Names are not checked by a tokenizer. They rely on the LanguageTool re-check
and on the user reviewing the diff before accepting.

## Caching

Successful rewrites are cached in process memory, keyed by text, language,
mode, instruction, allowed categories, context, and the endpoint/model pair.
The cache is an LRU bounded by `LLM_CACHE_SIZE` and is lost on restart. Errors
and rejected responses are not cached.

## Errors

| Status | Code | Cause |
|---|---|---|
| 400 | `invalid_body` | Body is not JSON |
| 400 | `invalid_request` | Missing or invalid field |
| 400 | `unknown_mode` | Mode is not defined |
| 400 | `unsupported_language` | No prompt for the language |
| 413 | `text_too_long` | Input exceeds `LLM_CONTEXT_CHARS` |
| 502 | `llm_invalid_request` | Endpoint rejected the request |
| 502 | `llm_error` | Other upstream error |
| 502 | `llm_invalid_json` | No reply matched the expected JSON shape |
| 502 | `llm_truncated` | Reply hit the token cap before finishing |
| 502 | `llm_empty_answer` | Reply had no content (reasoning-only or empty) |
| 502 | `llm_validation_failed` | JSON was valid but failed the source checks |
| 503 | `llm_unavailable` | Timeout or connection failure |
| 503 | `languagetool_unavailable` | Re-check could not run |

## Privacy

- Local Ollama is the default; no text leaves the machine.
- Hosted endpoints are opt-in and are the user's responsibility.
- Prompts and completions are never logged.

## Chunking

Not implemented. A selection longer than `LLM_CONTEXT_CHARS` is rejected with
`text_too_long`; select a shorter passage. Chunking can be added without
changing the response shape.

The practical limit is the response budget, not the input cap: the model must
emit every original span, replacement, and explanation. Prompts therefore ask
for changed spans only and one short explanation per change, and the default
response cap is `4096` tokens. With `gemma4:e4b-it-q4_K_M`, a 2,200-character
German paragraph passed in about 37 s at that cap.

`shortcut: rewrites are single-chunk, add paragraph chunking if whole-document rewrites become a use case.`

A repository `.env` overrides the defaults above. If rewrites still truncate,
check that it does not pin `LLM_MAX_TOKENS` or `LLM_TIMEOUT_SECONDS` to older
values; do not commit that file.