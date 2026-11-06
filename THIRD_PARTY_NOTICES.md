# Third-party notices

LanguageToolPlus is AGPL-3.0-or-later (see `LICENSE`). It uses and vendors
code from the projects below. This file is the single record of attribution;
`docs/PROVENANCE.md` tracks where each item came from.

If you distribute the built Obsidian plugin (`main.js`, `manifest.json`,
`styles.css`), include this file and `plugins/obsidian/LICENSE.md` alongside it.

## Vendored source

### Obsidian LanguageTool Integration

- Upstream: https://github.com/Clemens-E/obsidian-languagetool-plugin
- Copyright © Clemens Ertle and contributors, including Matthew Meyers.
- License: GNU Affero General Public License v3.0 (`plugins/obsidian/LICENSE.md`).
- Vendored at commit `f1817704bc0700b0313e474207762af5ab422750`
  (2026-09-05, "Release 0.4.3").
- Local modifications are listed in `plugins/obsidian/UPSTREAM.md`.

This fork is also AGPL-3.0. Its full source is this repository.

## Bundled in the plugin build

`plugins/obsidian/main.js` is bundled by esbuild from `plugins/obsidian/src`.
It includes the following MIT-licensed packages. Each copyright notice is
reproduced below; one copy of the MIT license text follows the list.

### Copyright © Titus Wormer <tituswormer@gmail.com>

- `bail` — Copyright (c) 2015 Titus Wormer
- `decode-named-character-reference` — Copyright (c) Titus Wormer
- `devlop` — Copyright (c) 2023 Titus Wormer
- `fault` — Copyright (c) 2015 Titus Wormer
- `mdast-util-from-markdown` — Copyright (c) Titus Wormer
- `mdast-util-frontmatter` — Copyright (c) 2020 Titus Wormer
- `mdast-util-to-string` — Copyright (c) 2015 Titus Wormer
- `micromark` — Copyright (c) Titus Wormer
- `micromark-core-commonmark` — Copyright (c) Titus Wormer
- `micromark-extension-frontmatter` — Copyright (c) 2020 Titus Wormer
- `micromark-factory-destination` — Copyright (c) Titus Wormer
- `micromark-factory-label` — Copyright (c) Titus Wormer
- `micromark-factory-space` — Copyright (c) Titus Wormer
- `micromark-factory-title` — Copyright (c) Titus Wormer
- `micromark-factory-whitespace` — Copyright (c) Titus Wormer
- `micromark-util-character` — Copyright (c) Titus Wormer
- `micromark-util-chunked` — Copyright (c) Titus Wormer
- `micromark-util-classify-character` — Copyright (c) Titus Wormer
- `micromark-util-combine-extensions` — Copyright (c) Titus Wormer
- `micromark-util-decode-numeric-character-reference` — Copyright (c) Titus Wormer
- `micromark-util-decode-string` — Copyright (c) Titus Wormer
- `micromark-util-html-tag-name` — Copyright (c) Titus Wormer
- `micromark-util-normalize-identifier` — Copyright (c) Titus Wormer
- `micromark-util-resolve-all` — Copyright (c) Titus Wormer
- `micromark-util-subtokenize` — Copyright (c) Titus Wormer
- `remark-frontmatter` — Copyright (c) 2017 Titus Wormer
- `remark-parse` — Copyright (c) 2014-2020 Titus Wormer
- `trough` — Copyright (c) 2016 Titus Wormer
- `unified` — Copyright (c) 2015 Titus Wormer
- `unist-util-stringify-position` — Copyright (c) 2016 Titus Wormer
- `vfile` — Copyright (c) 2015 Titus Wormer
- `vfile-message` — Copyright (c) 2017 Titus Wormer

### Other copyright holders

- `annotatedtext` — Copyright (c) 2018 David L. Day
- `annotatedtext-remark` — Copyright (c) 2018 David L. Day
- `escape-string-regexp` — Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com)
- `is-plain-obj` — Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com)
- `is-buffer` — Copyright (c) Feross Aboukhadijeh
- `extend` — Copyright (c) 2014 Stefan Thomas
- `format` — Copyright Sami Samhuri. The package ships no license file and
  declares MIT in `package.json` (`http://sjs.mit-license.org`).

### MIT License

The following text applies to every package listed in this section.

```text
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Dictionary data, downloaded but not redistributed

The gateway downloads these sources at the user's request and writes compact
indexes under `data/wordbook/` (git-ignored). The original data is never
committed to this repository.

- **FreeDict German–English / English–German** —
  https://freedict.org/ — Copyright Frank Richter, Einhard Leichtfuß, and
  contributors. License: GNU GPL v2.0. Pinned to release `1.9-fd1` and
  verified with the publisher's SHA-512 checksums.
- **German Wiktionary extract (kaikki.org)** —
  https://kaikki.org/dewiktionary/ — derived from
  https://de.wiktionary.org/ by Tatu Ylonen's wiktextract. License:
  CC BY-SA 3.0 and GFDL. The URL is unversioned and rotates weekly, so the
  builder records the SHA-256 of the downloaded file in `SOURCES.json`.
  The derived indexes keep the same license and attribution.

The images in `plugins/obsidian/` are not affected.

## Services used, not redistributed

These run as separate processes or images. No source is copied into this
repository.

- **LanguageTool** — https://github.com/languagetool-org/languagetool —
  LGPL-2.1-or-later for the core. Used unmodified over HTTP. German grammar
  and style rules are read at runtime from LanguageTool; rule IDs in
  `modes/*.yaml` are public identifiers.
- **LanguageTool Docker image** —
  https://github.com/Erikvl87/docker-languagetool — LGPL-2.1. Published as
  `erikvl87/languagetool` and pinned in `docker-compose.yml`.
- **LLM models** — any OpenAI-compatible endpoint. Ollama is the local default,
  but model weights are downloaded by the user and are not part of this
  repository. Each model carries its own license; check it before
  redistributing weights or outputs.

## Gateway runtime dependencies

Installed by `uv` from `gateway/pyproject.toml`; not copied into this
repository. Direct dependencies and their licenses:

| Package | License |
|---|---|
| `fastapi` | MIT |
| `uvicorn` | BSD-3-Clause |
| `pydantic` | MIT |
| `pydantic-settings` | MIT |
| `httpx` | BSD-3-Clause |
| `openai` | Apache-2.0 |
| `pyyaml` | MIT |
| `pytest` | MIT |
| `respx` | BSD-3-Clause |
| `ruff` | MIT |
| `mypy` | MIT |
| `types-pyyaml` | Apache-2.0 |

Transitive dependency versions are pinned in `gateway/uv.lock`; each package
carries its own license metadata.