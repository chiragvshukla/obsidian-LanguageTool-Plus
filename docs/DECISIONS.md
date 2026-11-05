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