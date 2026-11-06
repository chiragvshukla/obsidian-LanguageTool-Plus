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
A category disabled on either side is never re-enabled. Mode `enabled_rules`
are unioned with the client's, while a client `disabledRules` entry always
wins. When the client sends `enabledOnly=true`, the mode adds nothing and
disabled lists are dropped: LanguageTool rejects them, and an explicit client
subset must not be widened.

**Consequences:** modes can tighten checks or remove noise, but cannot override
an explicit client restriction. The rules are visible in `merge_categories`
and `merge_rules` and covered by tests.

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

## ADR-013 — Rewrite is explicit, validated, and gated in the plugin

**Status:** accepted

**Context:** an LLM can change meaning, invent facts, or return malformed text.
Inline checking must remain deterministic and usable without any model running.

**Decision:** the LLM is reachable only through `POST /rewrite`, called by an
explicit user action. `/v2/check` never calls the model. Every rewrite is
validated (schema, ordered non-overlapping changes, length ratio, protected
numbers/URLs/emails/code, LanguageTool re-check) and one stricter retry is made
before returning `502 llm_validation_failed`; unvalidated text is never sent.
Prompts are `prompts/<language>/<mode>.md` and a missing prompt fails startup.
The plugin exposes a single "Enable AI features" switch, default off, that
gates every AI command and inline suggestion. The gateway has no master switch:
the plugin decides.

**Consequences:** the stack works fully without an LLM, and a hosted endpoint
cannot be reached by accident. The validator chain is the quality boundary, so
it must run on every rewrite. `shortcut: rewrites are single-chunk; selections
over `LLM_CONTEXT_CHARS` return `413 text_too_long` until chunking is added.`

## ADR-014 — Consistency checks emit one match per issue type

**Status:** accepted

**Context:** a document can mix `Sie` and `du`, date formats, or terminology.
Reporting every occurrence would drown the user and duplicate deterministic
rules that already mark each wrong spelling.

**Decision:** the gateway runs a document-level pass after LanguageTool and the
lexicon. It returns at most one synthetic match per issue type
(`CONSISTENCY_DU_SIE`, `CONSISTENCY_DATE_FORMAT`,
`CONSISTENCY_NUMBER_FORMAT`, plus one terminology notice per lexicon term),
placed at the point where the style changes or at the canonical term. Matches
are LanguageTool-shaped and gated by `disabledRules`, `disabledCategories`, and
`enabledOnly` like the other gateway rules.

**Consequences:** the plugin needs no new UI. The address check is a pronoun
heuristic; `shortcut: a lone Sie is ambiguous, upgrade to a tagger if false
alarms matter.` Terminology notices reuse the term's rule id, so disabling the
term disables both its per-occurrence and its consistency match.

## ADR-015 — AI checks are explicit, with opt-in paragraph auto-check

**Status:** accepted

**Context:** LanguageTool misses German gender and case agreement in ambiguous
forms (`Der Mädchen`, `Der Frau`, `Der Bundeskanzlerin`). The local model fixes
these, but a rewrite replaces the whole selection and gives no inline review.
Running the model from `/v2/check` would make deterministic, millisecond checks
depend on a slow, stochastic service.

**Decision:** keep `/v2/check` LLM-free. Reuse `POST /rewrite` for an explicit
"Check selection with AI" command that always sends `neutral`, converts each
validated change into an `AI_GRAMMAR` match, and skips spans that overlap a
deterministic LT underline. Add a separate, default-off "AI auto-check current
paragraph" setting: after 10 seconds without typing it checks at most 2,000
characters around the cursor, discards stale results, and redraws only its own
underlines. Rewrite changes carry source `offset`/`length`, which also drive
changed-span highlighting in the review modal.

**Consequences:** AI hints look and behave like normal LT suggestions, including
accept, ignore, and jump. Auto-check can spend a request on a paragraph the
user has left, and the model can flag correct text; that is why it is opt-in
and scoped. Whole-document checking and paragraph chunking remain deferred.
`shortcut: auto-check is one paragraph and 2,000 characters, add chunking if
whole-note AI checking becomes a use case.`

## Phase 0 findings

- LanguageTool: prebuilt image + bind-mounted `grammar_custom.xml` works; the
  custom Maven image is unnecessary.
- Locale: the image runs without `LANG`, but Java 17 on Alpine still decodes
  UTF-8 resources correctly. No locale override is needed.
- Plugin request shape: taken from upstream source; a live capture lands with
  Phase 1.
- LLM: see ADR-010. Model quality on one sample was imperfect, so validators
  are load-bearing.