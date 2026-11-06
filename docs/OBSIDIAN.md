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

Both AI actions require "Enable AI features" and call `POST /rewrite`. They also
require an **AI base URL** and an **AI model** in the plugin settings; with
either empty, AI stays off and only LanguageTool runs. The model list comes from
`POST /llm/models`, and the API key is read from Obsidian's SecretStorage and
sent to the gateway as headers. The optional **AI max response tokens** and
**Reasoning effort** settings are sent the same way. Results are validated by
the gateway before the plugin sees them.

- **Rewrite selection with AI** uses the note's mode. The review modal shows
  the original, the rewritten text with changed spans highlighted, and one
  short explanation per change. A deletion is shown as a small "removed"
  marker. "Replace" applies the whole rewrite; "Cancel" leaves the note alone.
- **Check selection with AI** uses the note's resolved writing mode (frontmatter
  `lt-mode`, else the plugin setting), so a formal note gets tone-aware phrasing
  suggestions while `neutral` stays a correctness pass. Each change becomes a
  LanguageTool-shaped underline (`rule.id` = `AI_GRAMMAR`) with the model's
  replacement and explanation, so the existing popover, jump, ignore, and
  accept-suggestion commands work unchanged. The category picks the colour:
  `style` is purple, grammar is amber, and a vocabulary suggestion (a word in
  the text's language) is blue; AI underlines are dashed while LT underlines
  stay solid. AI spans are drawn even when they overlap deterministic
  LT underlines; clicking the shared text shows one popover with a section per
  suggestion, each with its own buttons and Ignore. A deletion has no
  replacement button, but still shows its explanation.
- **Check current paragraph with AI** runs the same pass on the paragraph around
  the cursor, without needing a selection. It reports its result or error in a
  notice and works even when automatic checking is off.
- **Check whole document with AI** splits the note body on paragraph, then
  sentence boundaries into sections of at most 8,000 characters, skips
  frontmatter and fenced code, and calls `POST /rewrite` once per section. It
  shows the section count before the first call and progress while it runs.
  Underlines are drawn only after every section succeeds and the note is
  unchanged. A note that needs more than 20 sections is refused; check a
  selection instead. Rewrite stays selection-only.
- **AI auto-check current sentence** is a separate, default-off toggle. After
  4 seconds without typing it checks the sentence around the cursor (at most
  2,000 characters). The rest of the paragraph is sent as `context_before` /
  `context_after` (up to 1,000 characters per side) so pronouns and references
  resolve; the model may not change or return the context, and only sentence
  changes become underlines. The cursor is read when the pause ends, so
  cursor-only
  updates and clicks do not cancel a pending check; any edit invalidates it.
  Failed or stale checks are dropped silently. An empty result does not erase
  existing AI underlines; only an explicit check replaces them. LT checking
  stays instant and independent, and an LT check now clears only its own
  underlines, so an automatic LT pass cannot wipe visible AI hints.
- The status-bar **Aa** icon and the ribbon icon open the same menu: check the
  document, switch writing mode, switch the dictionary pair, run the AI
  actions, toggle automatic checking, and clear suggestions. AI entries are
  hidden while AI features are off or no model is configured; selection actions stay disabled without a
  selection.
- The three AI category toggles (grammar, style, vocabulary) are sent as
  `categories` on every `/rewrite` call. All on is the default and sends no
  list. Switching one off is enforced by the gateway, not only hidden by the
  plugin.

- **Score current note with AI** calls `POST /score` once with the note body
  (frontmatter removed). The gateway makes one `/v2/check` call for exact word,
  sentence, and category counts. A note within `LLM_CONTEXT_CHARS` uses one
  model call; a longer note is graded section by section and one reduce call
  produces the final 1–5 grades (clarity, tone fit, vocabulary, structure) and
  up to three recommendations. The modal is read-only, states how many
  sections were used, and nothing is cached. While it is open, automatic LT
  and AI checks are suppressed so the note cannot change underneath the report.
  Notes over `LLM_SCORE_MAX_CHUNKS × LLM_CONTEXT_CHARS` return
  `413 text_too_long`.
- **Insert writing topic with AI** calls `POST /topic` and inserts the result
  at the cursor as a blockquote. The labels follow the note language:
  `Schreibthema`/`Fokus` in German and `Writing prompt`/`Angle` in English.
  Topics may repeat across sessions; nothing is stored.

The model is slower than LanguageTool (seconds, not milliseconds), so AI
auto-check is opt-in and scoped to one sentence. Explicit commands state their
call count; a long note costs one call per section (plus one reduce call when
scoring).

## Hover dictionary

Independent of the AI switch and off by default. Settings → Dictionary holds
the toggle, the pair (German – German, English → German, German → English),
per-pair status, and one Download button. The gateway builds the data on
request; nothing is bundled with the plugin and no model is involved.

The CodeMirror `hoverTooltip` waits 500 ms, extracts the word around the
cursor, and skips frontmatter, code, links, and URLs using the Markdown syntax
tree. It asks `GET /dictionary/lookup?word=…&pair=…` and stays silent on a miss
or when the gateway is down. Results render the headword with the article from
the source entry and its part of speech (`das Haus`, noun), plus up to three
senses. German inflected forms are resolved by the gateway's alias
index, so hovering `Häuser` shows `Haus`. Lookups are cached in memory for the
session.

The three data pairs live under `data/wordbook/` and are git-ignored. See
ADR-018 and `THIRD_PARTY_NOTICES.md`.

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
7. Per-category AI toggles (grammar, style, vocabulary), enforced by the
   gateway and sent on every `/rewrite` call.
8. The local hover dictionary: settings, download status, and a CM6 hover
   tooltip backed by the gateway.
9. Writing practice: a read-only score report (`POST /score`) and blockquote
   topic insertion (`POST /topic`). Long notes score with map + reduce.
10. Whole-document AI checking with paragraph/sentence chunking, progress, and
    a call-count notice. Rewrite stays selection-only.
11. Dictionary pair selection in the shared ribbon/status menu, and a readable
    hover tooltip in both themes.

Do not modify the upstream request shape otherwise. Record the upstream commit
in `plugins/obsidian/UPSTREAM.md` and keep the AGPL-3.0 license.

## Configuration

- Endpoint: `http://127.0.0.1:8077` (the plugin appends `/v2`).
- `http://127.0.0.1:8010` is LanguageTool directly; modes do not apply.

## Out of scope

Mixed-language checking and mobile apps.