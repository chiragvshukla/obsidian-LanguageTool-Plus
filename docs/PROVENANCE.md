# Provenance

Record every borrowed code fragment, rule, prompt, or dataset here before it
lands in the repository.

| Item | Source | License | Use | Notes |
|---|---|---|---|---|
| LanguageTool core | https://github.com/languagetool-org/languagetool | LGPL-2.1-or-later | Separate, unmodified service | Not vendored |
| LanguageTool German rules | same repository | LGPL-2.1-or-later | Read at runtime | Not copied into our source |
| German rule category IDs | `community.languagetool.org/rule/list` | LGPL-2.1-or-later | Referenced in `modes/*.yaml` | Public identifiers |
| Obsidian LanguageTool plugin | https://github.com/Clemens-E/obsidian-languagetool-plugin | AGPL-3.0 | Vendored fork under `plugins/obsidian/` | Commit `f1817704bc0700b0313e474207762af5ab422750`; see `plugins/obsidian/UPSTREAM.md` |
| LanguageTool Docker image | https://github.com/Erikvl87/docker-languagetool | LGPL-2.1 | Prebuilt image `erikvl87/languagetool:6.8` in `docker-compose.yml` | Not vendored; source is upstream |
| Bundled plugin libraries | npm, see `THIRD_PARTY_NOTICES.md` | MIT | Bundled into `plugins/obsidian/main.js` by esbuild | 40 packages; notices and MIT text recorded |

## Explicitly not used

- The third-party browser extension (All Rights Reserved).
- LanguageTool Closed rule packs.
- Any rule text copied from the LanguageTool website.

## How to add an entry

1. Add a row with the exact URL, license, and version/commit.
2. Confirm the license permits the intended use.
3. If the license is missing or unclear, do not copy; ask first.