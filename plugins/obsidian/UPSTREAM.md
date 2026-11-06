# Obsidian plugin fork

Vendored from
[Clemens-E/obsidian-languagetool-plugin](https://github.com/Clemens-E/obsidian-languagetool-plugin).

| Item | Value |
|---|---|
| Upstream URL | https://github.com/Clemens-E/obsidian-languagetool-plugin |
| Copyright | Clemens Ertle and contributors, including Matthew Meyers |
| Commit | `f1817704bc0700b0313e474207762af5ab422750` (2026-09-05, "Release 0.4.3") |
| License | AGPL-3.0, `LICENSE.md` |
| Copied | 2026-11-06 |
| Method | Plain copy, no git submodule (ADR-003) |

`src/`, the build config, `styles.css`, `manifest.json`, `package.json`,
`yarn.lock`, `versions.json`, `LICENSE.md`, and the upstream `README.md` are
unmodified upstream files except where listed below. The upstream `test/` and
`demos/` directories were not copied.

## Local modifications

1. **AI switch, rewrite, and AI checking**
   - `src/SettingsTab.ts`: added `enableAIFeatures` (default `false`),
     `aiAutoCheck` (default `false`), `aiGrammar`/`aiStyle`/`aiVocabulary`
     (default `true`), and `writingMode` (default `neutral`) to
     the settings, plus a "Writing" section and an "AI features" section.
     `WRITING_MODES`/`isWritingMode` are exported for validation.
   - `src/rewrite.ts`: new. Calls `POST {serverUrl}/rewrite` on the gateway,
     sending the enabled AI categories when one is switched off, and
     shows the result in a review modal, with changed spans highlighted.
   - `src/aiCheck.ts`: new. Converts validated rewrite changes into
     LanguageTool-shaped matches, finds the paragraph around the cursor,
     extracts the sentence inside it for the automatic pass, and sends the
     rest of the paragraph as bounded read-only context.
     `style` changes get the `STYLE` category (purple), `vocabulary` gets
     `VOCABULARY` (blue), others `GRAMMAR`.
   - `src/index.ts`: added "Rewrite selection with AI", "Check selection with
     AI", "Check current paragraph with AI", "Check whole document with AI",
     "Score current note with AI", and "Insert writing topic with AI". All are
     hidden unless `enableAIFeatures` is on; the checks use the note's resolved
     writing mode. The status-bar menu and the ribbon icon open one shared menu
     with the checks, AI actions, writing-mode picker, and dictionary-pair
     picker.
   - `src/documentChunk.ts`: new. Splits the note body into sections of at most
     8,000 characters on paragraph then sentence boundaries, skipping
     frontmatter and fenced code, so the whole-document check stays within the
     gateway's context budget.
   - `src/practice.ts` and `src/practiceHelpers.ts`: new. Read-only score modal
     over `POST /score`, topic insertion over `POST /topic`, and the pure
     formatting helpers for both.
   - `src/modePicker.ts`: new. `FuzzySuggestModal` over `WRITING_MODES` and
     `DICTIONARY_PAIRS` for the shared menu; each writes its setting.
   - `src/cm6/buildAutoCheckHandler.ts`: optional 4-second sentence check
     when `aiAutoCheck` is on. Cursor-only updates do not cancel it; the cursor
     is read when the pause ends, and edits invalidate the result.
   - `src/cm6/underlineStateField.ts`: `clearAIUnderlinesInRange` replaces only
     AI underlines; `clearLTUnderlines`/`clearLTUnderlinesInRange` let an LT
     check clear only its own underlines, so AI hints survive a re-check. AI
     decorations also carry `lt-ai`, which draws a dashed underline.
   - `src/cm6/tooltipField.ts`: one popover can now list several overlapping
     suggestions, each with its own replacement buttons and Ignore. A
     non-breaking-rule hint (a deletion) carries its explanation without a
     replacement button.

2. **Writing modes on checks**
   - `src/api.ts`: sends `writing_mode` on `/v2/check` when `urlMode` is
     `custom`; the official API never receives the parameter.
   - `src/helpers.ts`: new `getDocumentMode`, reading the `lt-mode`
     frontmatter key and rejecting unknown values.
   - `src/index.ts`: resolves the per-note mode, includes it in the detection
     cache key, and passes it to the request.

The gateway URL is the existing `serverUrl` setting (bare origin, no `/v2`
suffix). A rewrite resolves the language like a check does: the note's
frontmatter language first, then a static language setting, then a short
LanguageTool detection probe (the first 500 characters with `language=auto`).
A failed probe leaves the language unset so the gateway default applies.

A rewrite also uses the note's `lt-mode` frontmatter when present and falls
back to the same `writingMode` setting used by checks.

## Building

```powershell
cd plugins/obsidian
yarn install          # or: npm install
yarn build            # or: npm run build
```

`main.js` is a build artifact and is ignored by git. It bundles 40
MIT-licensed npm packages; their notices are in the repository-root
`THIRD_PARTY_NOTICES.md`. Copy `main.js`, `manifest.json`, and `styles.css` into
`<vault>/.obsidian/plugins/obsidian-languagetool-plugin/` and keep the notices
with any build you share.

## Upstream updates

Copy the new upstream tree over this directory, then re-apply the changes
above. Keep the format of this file: update the commit and date. Never
add the plugin as a git submodule.