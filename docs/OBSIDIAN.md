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

`GET /v2/languages` populates the settings dropdowns.

The plugin uses Obsidian's `requestUrl`, which bypasses CORS.

## Per-note language

Frontmatter keys, in precedence order: `lt-language`, `language`, `lang`.
`lt-language: auto` re-enables detection. Varieties (`de-DE`, `de-AT`,
`de-CH`, `en-US`, `en-GB`, …) apply only while auto-detecting.

## Fork changes (Phase 6)

Keep the patch small and upstream-friendly:

1. Read `lt-mode` frontmatter (mirror `getDocumentLanguage`).
2. Send it as a `mode` parameter.
3. Add a mode selector to the settings/status UI.
4. Add a "Rewrite selection" command that calls `POST /rewrite`.
5. Do not modify the upstream request shape otherwise.

Record the upstream commit in `plugins/obsidian/UPSTREAM.md` and keep the
AGPL-3.0 license.

## Configuration

- Endpoint: `http://127.0.0.1:8077` (the plugin appends `/v2`).
- During Phase 0/1 before the gateway exists: `http://127.0.0.1:8010`.

## Out of scope

Mixed-language checking, mobile apps, and redistributing the third-party
browser extension.