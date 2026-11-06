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
"Check selection with AI" command that sends the note's resolved writing mode,
converts each validated change into an `AI_GRAMMAR` match, and draws it even
where a deterministic LT underline already exists. The change category sets the
underline colour (`style` purple, grammar amber, `vocabulary` blue) and AI
underlines are dashed,
so a phrasing suggestion is distinguishable from a grammar catch and from LT.
Overlapping hints share one popover with a section per suggestion, so neither is
hidden. Add a separate, default-off "AI auto-check current sentence" setting:
after 4 seconds without typing it checks one sentence (at most 2,000
characters) around the cursor, discards stale results, and redraws only its own
underlines. Rewrite changes carry source `offset`/`length`, which also drive
changed-span highlighting in the review modal.

**Consequences:** AI hints look and behave like normal LT suggestions, including
accept, ignore, and jump. Because the check follows the note's mode, formal,
business, and academic notes receive phrasing suggestions as well as correctness
fixes; the category keeps their colours apart. Where both underline the same
words, one popover lists both suggestions instead of hiding one. Auto-check can
spend a request on a sentence the user has left, and the model can flag correct
text; that is why it is opt-in and scoped. Cursor-only updates do not cancel the
debounce; the cursor is read when the pause ends. LT checks clear only their own
underlines so they cannot erase AI hints, and an empty automatic AI result leaves
existing hints in place. Whole-document checking and paragraph chunking remain
deferred.
`shortcut: auto-check is one sentence and 2,000 characters, add chunking if
whole-note AI checking becomes a use case.`

## ADR-016 — AI categories are filtered in the gateway

**Status:** accepted

**Context:** users want correctness help without unsolicited phrasing advice,
or want only the foreign-word hint. Skipping suggestions in the plugin would
still pay for the model and could drop a grammar fix that a style rewrite
absorbed.

**Decision:** `POST /rewrite` accepts `categories`, a list drawn from `grammar`,
`style`, and `vocabulary`. The gateway adds a policy line to the user message,
drops returned changes outside the list before validation, and includes the
sorted set in the cache key. `None` means all categories; an empty list returns
no changes without calling the model. The plugin sends the list only when a
category is switched off, so the default path is unchanged. Three settings
under "Enable AI features" default to on; the master switch stays the only
off switch.

**Consequences:** the model is told to keep each change in one category rather
than bundle a rewrite, but a small model can still mislabel a change; the
gateway filter trusts the label it returns. With only `grammar` enabled, wording
suggestions are dropped rather than partially applied, and a span needing both
kinds of fix gets only the enabled part.

## ADR-017 — Automatic checks send paragraph context

**Status:** accepted

**Context:** a sentence checked alone loses the references that decide German
case, gender, and register: a pronoun's antecedent, whether the note addresses
a landlord or a friend, and the tense already established. Sending the whole
paragraph as the rewrite target would make every sentence pay for a paragraph
rewrite and would return changes the auto-check cannot safely place.

**Decision:** `POST /rewrite` accepts optional `context_before` and
`context_after`. They are rendered as separate, marked read-only blocks. The
model may use them but changes are validated against `text` only, so a change
that falls in the context fails validation and is retried. The cache key
includes both strings, and text plus context must fit `LLM_CONTEXT_CHARS`. The
plugin's automatic pass sends the rest of the paragraph capped at 1,000
characters per side; the manual paragraph command and selection actions send no
context. A test pins the context slicing.

**Consequences:** the prompt grows by the surrounding paragraph, and a sentence
repeated in different paragraphs no longer shares a cache entry. On the local
model the measured difference was under 0.2 s for a ~90-character sentence with
two context sentences, so the change is effectively free. Only the checked
sentence receives underlines; clicking one still accepts a change within that
sentence.

## ADR-018 — The hover dictionary is built locally, never by the LLM

**Status:** accepted

**Context:** the plugin already has an AI vocabulary hint, but a reader also
wants to look up an arbitrary word without leaving the note. Sending every
hover to a model would be slow, non-deterministic, costly, and would fail
offline. The two existing FreeDict German/English dictionaries and the German
Wiktionary extract cover the needed directions.

**Decision:** the gateway downloads and parses the sources once, on request,
and serves compact gzip JSONL indexes under `data/wordbook/`. FreeDict archives
are pinned by SHA-512 from the publisher's API. The Wiktionary extract rotates
weekly with no published checksum, so the builder records the SHA-256 it
computed in `SOURCES.json` and validates the gzip stream while parsing. German
inflected forms become an alias list pointing at their source form; lookup
tries the direct index first, then aliases, and returns at most two entries so
homographs stay visible. The plugin asks the gateway only after a 500 ms hover
and stays silent on any miss. The feature has its own default-off setting and
does not depend on the AI master switch.

**Consequences:** the first build downloads roughly 350 MB and takes minutes;
afterwards lookup is local and instant, and the generated data never enters
git. Without a lemma tagger the alias index can be patchy for unusual forms;
the cap of five aliases per form keeps homograph groups bounded. The indexes
load lazily per pair, so a cold first hover can pause briefly.

## ADR-021 — A rewrite is blocked by new errors, not by new style hints

**Status:** accepted

**Context:** `/rewrite` re-checked every model rewrite with LanguageTool and
rejected it when any new rule ID appeared. Model suggestions are often small
grammar fixes, and a corrected sentence can legitimately trigger a style rule
(e.g. three sentences now start with the same word). Inline paragraph and
whole-document checks then failed with `502` and showed nothing, even though
the rewrite was fine. Two other model habits also killed a check: a change that
contains another change, and changes listed out of order.

**Decision:** the re-check uses the same mode-derived LanguageTool parameters
as `/v2/check` (`level`, categories, enabled/disabled rules) and compares
occurrence counts per rule ID, not sets. Only correctness findings count;
matches whose `issueType` is `style` never block a rewrite. The applier
tolerates out-of-order changes and drops a change that overlaps one already
applied; a change whose text is nowhere in the source is still a validation
failure. If the whole set adds a correctness finding, each change is tested
alone (up to 12) and the unsafe ones are dropped, so the remaining hints are
still returned with `dropped: N`. When every change is unsafe, the request
fails as before. This keeps the guarantee that the plugin never receives
unvalidated text while making partial results usable.

**Consequences:** a check can show fewer hints than the model proposed. A new
style hint may appear as a normal LanguageTool underline after accepting an AI
suggestion; that is visible, not silent. The guard costs up to `N + 2`
LanguageTool calls only when the combined set fails validation.

## ADR-020 - Chunk long text on paragraph boundaries; score with map + reduce

**Status:** accepted

**Context:** the local model has a character budget (`LLM_CONTEXT_CHARS`,
12,000), while notes can be much longer. Two features now need long text:
whole-document AI checking and scoring a whole note. Blindly slicing on
characters breaks sentences and offsets; grading a long note in one call
exceeds the budget, and averaging independent section grades would hide how
the sections interact.

**Decision:** split text on blank-line paragraph boundaries, then sentence
ends, then a hard slice, so every section fits the budget. The plugin does this
for whole-document checks (`documentChunk.ts`) because it needs progress and
local offsets. The gateway does the same for `/score` (`chunk_text`) because
the report is aggregated there. `/score` computes facts and LanguageTool
findings once over the whole text, then grades each section and makes one
reduce call that receives the facts and the section results. Notes within the
budget keep the single-call path. Scoring is capped at
`LLM_SCORE_MAX_CHUNKS` (default 8); whole-document checking at 20 sections.
Rewriting remains selection-only.

**Consequences:** a long note costs N + 1 model calls to score and one call per
section to check, so both commands state the count before starting. Facts stay
exact and are never split. The two chunkers must stay in sync; both carry a
comment saying so. If the model handles long context better later, the chunk
size can rise without changing either endpoint.

## ADR-019 — The score separates measured facts from model judgement

**Status:** accepted

**Context:** a writing score is useful only if the reader knows what is exact
and what is an opinion. LanguageTool findings, word counts, and sentence
lengths are deterministic. Clarity, tone fit, vocabulary, and structure are
judgements, and a small local model can grade the same text differently on
repeated runs. A single authoritative number would hide that difference.

**Decision:** `POST /score` returns `facts` from the deterministic pass
(`words`, `sentences`, `averageSentenceWords`, `ltIssues` by category) and 1–5
grades only for `clarity`, `tone`, `vocabulary`, and `structure`, plus at most
three recommendations. There is no overall score and no grammar grade, because
grammar is already measured exactly. The plugin renders both parts in one
read-only modal and labels the grades as model judgement. Requests are explicit
commands; they never create underlines, are never automatic, and are not cached.
No second LanguageTool call is made: the same `/v2/check` input that
`Check Text` uses feeds the facts.

**Consequences:** the report is less tidy than a single number but cannot
contradict the deterministic findings. If the model proves too noisy, the
grades can be dropped without changing the endpoint shape. While the modal is
open, automatic LT and AI checks are suppressed so the note does not change
underneath the report; manual commands still work.

## Phase 0 findings

- LanguageTool: prebuilt image + bind-mounted `grammar_custom.xml` works; the
  custom Maven image is unnecessary.
- Locale: the image runs without `LANG`, but Java 17 on Alpine still decodes
  UTF-8 resources correctly. No locale override is needed.
- Plugin request shape: taken from upstream source; a live capture lands with
  Phase 1.
- LLM: see ADR-010. Model quality on one sample was imperfect, so validators
  are load-bearing.