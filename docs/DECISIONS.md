# Architecture decision records

Short records of choices that are expensive to reverse.

## ADR-001 — No database

**Status:** accepted

**Context:** single user, one gateway, local Obsidian.

**Decision:** no SQLite or Postgres. Config lives in YAML/env, the dictionary in
flat files, and the LLM cache in memory.

**Consequences:** zero migrations and zero backup tooling. Cache is lost on
restart. If concurrent writers or queryable history appear, add SQLite first.

## ADR-002 — OpenAI-compatible LLM interface only

**Status:** accepted

**Context:** local Ollama and hosted providers should be interchangeable.

**Decision:** use `/v1/chat/completions` through the official `openai` SDK.
No provider-specific fields. Ollama is the local default.

**Consequences:** some providers differ in JSON-mode support; validators are
mandatory.

## ADR-003 — Vendor the Obsidian plugin

**Status:** accepted

**Context:** the fork will change substantially; the user is a solo developer.

**Decision:** copy the upstream plugin under `plugins/obsidian/` and record the
upstream commit in `UPSTREAM.md`. No git submodule.

**Consequences:** one clone and normal CI. Upstream updates require manual
merges, which is acceptable for a personal tool.

## ADR-004 — AGPL-3.0 for the repository

**Status:** accepted

**Context:** the plugin fork must be AGPL; the user wants OSS.

**Decision:** license the whole repository AGPL-3.0-or-later.

**Consequences:** network use requires source availability. If a permissive
gateway is ever needed, split it into a separate repository.

## ADR-005 — Gateway is API-compatible with LanguageTool

**Status:** accepted

**Context:** the upstream plugin already speaks `/v2/check`.

**Decision:** keep the LanguageTool request/response shape so the upstream
plugin works unmodified in pass-through mode.

**Consequences:** the gateway inherits the annotated-JSON complexity. LLM
features must fit that shape or use separate endpoints.

## ADR-006 — No per-paragraph mixed-language checking

**Status:** accepted

**Context:** LanguageTool checks one language per request; the plugin sends one
request per note.

**Decision:** do not implement mixed-language fan-out.

**Consequences:** pin one language per note. Mixed notes are out of scope.

## ADR-007 — Modes are declarative

**Status:** accepted

**Decision:** modes live in `modes/*.yaml` and map to LanguageTool parameters
plus a prompt file. No code branches per mode.

**Consequences:** adding a mode is a config change; invalid YAML fails startup.

## ADR-008 — External services are endpoints, not containers

**Status:** accepted

**Context:** Ollama and the gateway were initially placed in
`docker-compose.yml`. Both already run natively, and bundling them duplicated
models and created port and networking problems without benefit.

**Decision:** only LanguageTool is containerized. Ollama and the gateway run as
host processes. Every external service is addressed by a URL
(`LT_URL`, `LLM_BASE_URL`), never assumed to be in the same compose project.

**Consequences:** one container, no `host.docker.internal` special cases for
the default setup, no duplication of models. A clean-machine deployment can
later add an optional compose profile, but it must stay opt-in.

## ADR-009 — Mount custom rules instead of building a custom image

**Status:** accepted

**Context:** the custom German rules are a single XML file. Building a custom
LanguageTool image requires Maven and a 10–20 minute compile for every change.

**Decision:** use the prebuilt `erikvl87/languagetool` image and bind-mount
`rules/grammar_custom.xml` into the German rules directory. Verified against
upstream source: `Language.getRuleFileNames()` loads
`JLanguageTool.CUSTOM_PATTERN_FILE` (`grammar_custom.xml`) when the file exists.

**Consequences:** rule changes need only a container restart. We cannot add
Java-implemented rules this way, which is already out of scope.

## ADR-010 — Always send `response_format` to the LLM

**Status:** accepted

**Context:** the local default model is a reasoning model. Without
`response_format` it spends ~700 tokens on hidden reasoning, answers in 6.9 s,
and wraps JSON in a Markdown code fence. With `response_format` it emits clean
JSON in 1.2–1.8 s. Ollama accepts both `json_object` and `json_schema`.

**Decision:** every structured call sets `response_format`. Prefer
`json_schema`; fall back to `json_object` if the endpoint rejects it. Validate
the parsed object regardless of what the server accepts.

**Consequences:** faster rewrites and no fence-stripping. Providers without
JSON mode still work, but their output goes through the full validator chain.

## ADR-011 — Mode and client settings combine as "most restrictive"

**Status:** accepted

**Context:** the upstream plugin sends `level` and its own category lists. A
mode must influence checks without silently discarding the user's settings.

**Decision:** `picky` wins if either side asks for it. Disabled categories are
unioned; enabled categories are intersected when both sides provide a list.
A category disabled on either side is never re-enabled.

**Consequences:** modes can tighten checks or remove noise, but cannot override
an explicit client restriction. The rule is visible in `merge_categories` and
covered by tests.

## ADR-012 — Enable LanguageTool pipeline caching

**Status:** accepted

**Context:** German checks took ~600 ms each, independent of text length; even a
text with no words cost ~400 ms. `HTTPServerConfig` defaults to
`pipelineCaching=false`, so every request rebuilt `JLanguageTool` and reloaded
the German speller dictionary. The image's default `-Xmx512m` also crashed the
JVM under four parallel German checks.

**Decision:** set `langtool_pipelineCaching=true`,
`langtool_maxPipelinePoolSize=4`, `Java_Xms=1g`, `Java_Xmx=2g` in
`docker-compose.yml`. Do not enable `pipelinePrewarming`: it fills the pool with
picky/query settings that never match our requests and adds ~8 s of startup.

**Consequences:** steady-state German checks drop to 50-70 ms and four parallel
checks no longer crash. The first request after a container start still costs
~4 s. Misspelled words remain slow (~0.9-1.4 s) because Hunspell generates
suggestions; that path is unaffected by caching.

## Phase 0 findings

- LanguageTool: prebuilt image + bind-mounted `grammar_custom.xml` works; the
  custom Maven image is unnecessary.
- Locale: the image runs without `LANG`, but Java 17 on Alpine still decodes
  UTF-8 resources correctly. No locale override is needed.
- Plugin request shape: taken from upstream source; a live capture lands with
  Phase 1.
- LLM: see ADR-010. Model quality on one sample was imperfect, so validators
  are load-bearing.