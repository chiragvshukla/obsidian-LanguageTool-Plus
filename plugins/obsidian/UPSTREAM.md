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

1. **AI switch and rewrite command**
   - `src/SettingsTab.ts`: added `enableAIFeatures` (default `false`) and
     `rewriteMode` (default `neutral`) to the settings, plus an "AI features"
     settings section.
   - `src/rewrite.ts`: new. Calls `POST {serverUrl}/rewrite` on the gateway and
     shows the result in a review modal.
   - `src/index.ts`: added the "Rewrite selection with AI" command. It is
     hidden unless `enableAIFeatures` is on and the editor has a non-empty
     selection.

The gateway URL is the existing `serverUrl` setting (bare origin, no `/v2`
suffix). The rewrite language is the static language setting when it is set
and not `auto`; otherwise the gateway default applies.

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

Copy the new upstream tree over this directory, then re-apply the three
changes above. Keep the format of this file: update the commit and date. Never
add the plugin as a git submodule.