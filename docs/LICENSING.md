# Licensing

## This repository

AGPL-3.0-or-later. See `LICENSE`. Network use counts as distribution: if you
run a modified version as a service, users must be able to obtain the source.

## LanguageTool

- Repository: https://github.com/languagetool-org/languagetool
- License: LGPL-2.1-or-later for the core.
- How we use it: as an **unmodified separate service** over HTTP. We do not
  link against it or modify its Java.
- If that ever changes, LGPL obligations apply: publish modifications and allow
  relinking.
- Closed-source rule sets are not copied, scraped, or redistributed.
- The container comes from https://github.com/Erikvl87/docker-languagetool
  (LGPL-2.1), published as `erikvl87/languagetool`.

## Obsidian plugin fork

- Upstream: https://github.com/Clemens-E/obsidian-languagetool-plugin
- Copyright © Clemens Ertle and contributors, including Matthew Meyers.
- License: AGPL-3.0. Upstream license text is kept at
  `plugins/obsidian/LICENSE.md`.
- The vendored fork remains AGPL-3.0. Keep the license and attribution.
- Modifications are published in this repository, satisfying AGPL. If the built
  plugin is shared, include `THIRD_PARTY_NOTICES.md` and
  `plugins/obsidian/LICENSE.md`, and offer the corresponding source (this
  repository).
- `plugins/obsidian/main.js` bundles MIT-licensed JavaScript packages. Their
  copyright notices and license text are in `THIRD_PARTY_NOTICES.md`; keep that
  file with any distributed build.

## Models and data

- Each model has its own license (for example Llama's community license,
  Qwen's Apache-2.0, Mistral's terms). Check before redistributing weights or
  outputs.
- Do not commit model weights. Pull them at runtime.
- German rule data comes from LanguageTool's LGPL resources; do not import
  non-open rule sets.

## Rules of thumb

- If a source has no license file, assume all rights reserved.
- If you cannot name the license, you cannot copy it.
- When in doubt, ask before adding code or data.