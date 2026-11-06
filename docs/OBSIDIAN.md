# Obsidian integration

## Upstream plugin

- https://github.com/Clemens-E/obsidian-languagetool-plugin
- License: AGPL-3.0.
- Works against any LanguageTool-compatible endpoint.

## What the plugin sends

`POST /v2/check` with:

- `data` — annotated JSON built with `annotatedtext-remark` (not plain text)
- `language`
- `enabledOnly`
- `level` — `default` or `picky`
- `enabledCategories`, `disabledCategories`
- `enabledRules`, `disabledRules`
- `preferredVariants`
- `motherTongue`
- `writing_mode` — gateway fork only, sent to a custom endpoint (`neutral`,
  `formal`, `casual`, `academic`, `business`)

`GET /v2/languages` populates the settings dropdowns.

The plugin uses Obsidian's `requestUrl`, which bypasses CORS.

## Per-note language

Frontmatter keys, in precedence order: `lt-language`, `language`, `lang`.
`lt-language: auto` re-enables detection. Varieties (`de-DE`, `de-AT`,
`de-CH`, `en-US`, `en-GB`, …) apply only while auto-detecting.

Checks and rewrites resolve the language the same way: frontmatter first, then
the static setting, then detection. For a rewrite the detection probe checks
the first 500 characters of the selection with `language=auto`, so an English
selection does not fall back to the gateway's German default. If the probe
fails, the language is omitted and the gateway default applies.

## Writing modes

The plugin's "Writing mode" setting is sent as `writing_mode` on every check
and as `mode` on `POST /rewrite`. Only a custom endpoint receives the
parameter, so the official LanguageTool API never sees it.

A note can override the mode for both checks and rewrites with frontmatter:

```yaml
lt-mode: formal
```

Unknown values are ignored (the setting applies), so the gateway never returns
`400 unknown_mode`. The resolved mode is part of the detection cache key.

## AI checking and rewriting

Both AI actions require "Enable AI features" and call `POST /rewrite`. Results
are validated by the gateway before the plugin sees them.

- **Rewrite selection with AI** uses the note's mode. The review modal shows
  the original, the rewritten text with changed spans highlighted, and one
  short explanation per change. A deletion is shown as a small "removed"
  marker. "Replace" applies the whole rewrite; "Cancel" leaves the note alone.
- **Check selection with AI** always uses `neutral`, because it is a
  correctness pass rather than a style rewrite. Each change becomes a normal
  LanguageTool-shaped underline (`rule.id` = `AI_GRAMMAR`) with the model's
  replacement and explanation, so the existing popover, jump, ignore, and
  accept-suggestion commands work unchanged. Spans that overlap deterministic
  LT underlines are skipped.
- **AI auto-check current paragraph** is a separate, default-off toggle. After
  10 seconds without typing it checks the paragraph around the cursor (at most
  2,000 characters), then clears and redraws only its own AI underlines.
  Moving the cursor or typing again discards the pending check. Failed or stale
  checks are dropped silently. LT checking stays instant and independent.

The model is slower than LanguageTool (seconds, not milliseconds), so AI
auto-check is opt-in and scoped to one paragraph. Explicit commands have no
such cap beyond the gateway's `LLM_CONTEXT_CHARS`.

## Fork changes (Phase 6)

Implemented:

1. `lt-mode` frontmatter, mirroring `getDocumentLanguage`.
2. `writing_mode` in the `/v2/check` body for custom endpoints.
3. A "Writing mode" dropdown in settings.
4. A "Rewrite selection with AI" command behind the "Enable AI features"
   switch, calling `POST /rewrite`.
5. Changed-span highlighting in the rewrite review modal.
6. A "Check selection with AI" command that renders model changes as normal
   underlines, plus a default-off paragraph auto-check.

Do not modify the upstream request shape otherwise. Record the upstream commit
in `plugins/obsidian/UPSTREAM.md` and keep the AGPL-3.0 license.

## Configuration

- Endpoint: `http://127.0.0.1:8077` (the plugin appends `/v2`).
- `http://127.0.0.1:8010` is LanguageTool directly; modes do not apply.

## Out of scope

Mixed-language checking, mobile apps, and redistributing the third-party
browser extension.