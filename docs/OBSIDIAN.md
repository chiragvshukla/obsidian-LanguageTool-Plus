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

## Writing modes

The plugin's "Writing mode" setting is sent as `writing_mode` on every check
and as `mode` on `POST /rewrite`. Only a custom endpoint receives the
parameter, so the official LanguageTool API never sees it.

A note can override the mode with frontmatter:

```yaml
lt-mode: formal
```

Unknown values are ignored (the setting applies), so the gateway never returns
`400 unknown_mode`. The resolved mode is part of the detection cache key.

## Fork changes (Phase 6)

Implemented:

1. `lt-mode` frontmatter, mirroring `getDocumentLanguage`.
2. `writing_mode` in the `/v2/check` body for custom endpoints.
3. A "Writing mode" dropdown in settings.
4. A "Rewrite selection with AI" command behind the "Enable AI features"
   switch, calling `POST /rewrite`.

Do not modify the upstream request shape otherwise. Record the upstream commit
in `plugins/obsidian/UPSTREAM.md` and keep the AGPL-3.0 license.

## Configuration

- Endpoint: `http://127.0.0.1:8077` (the plugin appends `/v2`).
- `http://127.0.0.1:8010` is LanguageTool directly; modes do not apply.

## Out of scope

Mixed-language checking, mobile apps, and redistributing the third-party
browser extension.