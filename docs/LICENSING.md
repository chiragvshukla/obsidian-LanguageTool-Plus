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
- LanguageTool Closed rules are closed source. We do not copy, scrape, or
  redistribute them.

## Obsidian plugin fork

- Upstream: https://github.com/Clemens-E/obsidian-languagetool-plugin
- License: AGPL-3.0.
- The vendored fork remains AGPL-3.0. Keep the license and attribution.
- Modifications are published in this repository, satisfying AGPL.

## Third-party browser extension

The current official LanguageTool browser extension is **All Rights Reserved**.
Do not copy, decompile, or redistribute its code. The old LGPL-2.1 add-on is
archived and not a drop-in base.

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