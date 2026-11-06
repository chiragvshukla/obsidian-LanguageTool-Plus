# Adding words and rules

Four places extend what LanguageTool finds. None of them requires rebuilding
the container.

## Personal dictionary

`data/dictionary/<language>.txt` holds accepted words, one per line.

- Use the primary language code (`de.txt`) or the full code (`de-DE.txt`).
  Both are loaded; `de.txt` covers `de-DE`, `de-AT`, and `de-CH`.
- Case-insensitive. `Straße` also matches `STRASSE` (Unicode case folding).
- Lines starting with `#` and blank lines are ignored.
- Read on every check, so an edit applies immediately. No restart.

Example:

```text
# Project names
LanguageToolPlus
Obsidian
```

A LanguageTool match is dropped when its whole span is a dictionary entry. This
is for names and accepted spellings, not for suppressing grammar rules.

## Terminology rules (`rules/lexicon.yaml`)

Each term is a Python regular expression. A match becomes a synthetic
LanguageTool-shaped match, so the Obsidian plugin displays it like any other.

```yaml
terms:
  - id: email_hyphen          # becomes rule id EMAIL_HYPHEN
    languages: [de]           # empty or omitted = all languages
    pattern: '(?<!\w)Email(?!\w)'
    message: 'Schreibe „E-Mail“ mit Bindestrich.'
    replacement: E-Mail       # optional
    modes: [formal, business] # empty or omitted = all modes
```

- `id` must be unique. It is uppercased in the response.
- `pattern` is a Python regex; invalid patterns fail at startup.
- `languages` matches the full code or the primary subtag.
- `modes` must name modes defined in `modes/`; an unknown mode fails at startup.
- Loaded once at startup. Restart the gateway after editing.
- The client can turn a term off with `disabledRules=EMAIL_HYPHEN` or all
  gateway terms off with `disabledCategories=LT_PLUS`.

## Document consistency

The gateway also reads the whole checked text and adds at most one match per
issue type. This catches patterns a sentence-level checker cannot see.

| Rule id | What it reports |
|---|---|
| `CONSISTENCY_DU_SIE` | German text mixes `Sie` and `du`. |
| `CONSISTENCY_DATE_FORMAT` | Two date formats (`12.03.2024`, `03/12/2024`, `2024-03-12`) appear in one document. |
| `CONSISTENCY_NUMBER_FORMAT` | German (`1.234,56`) and English (`1,234.56`) numbers appear together. |
| term id, e.g. `EMAIL_HYPHEN` | A lexicon term and its `replacement` both appear, placed at the canonical form. |

- Each rule fires once per document, not once per occurrence.
- `CONSISTENCY_*` rules can be turned off with `disabledRules` or the whole
  `LT_PLUS` category with `disabledCategories`, exactly like lexicon terms.
- The address check is a pronoun heuristic: a lone `Sie` is also third-person
  plural. It only fires when informal forms are present too.
- The terminology notice reuses the term's id, so disabling the term disables
  both its per-occurrence matches and its consistency notice.

## Grammar rules (`rules/grammar_custom.xml`)

The file is bind-mounted into the container at
`/LanguageTool/org/languagetool/rules/de/grammar_custom.xml`. LanguageTool loads
it at startup.

- Add a rule in the `LT_PLUS` category.
- Give it an `<example correction="…">` and a negative example if possible.
- Restart LanguageTool to apply: `docker compose restart languagetool`.
- Modes can disable the whole category; `casual` already does.

Check that a rule does not fire on correct text before relying on it. The
`rules/grammar_custom.xml` file ships with one working rule as a template.

## Dormant LanguageTool rules (`modes/*.yaml`)

Some German rules ship in LanguageTool but are disabled by default. Modes turn
them on with `enabled_rules`; the gateway forwards them as `enabledRules`.

```yaml
enabled_rules:
  - DAS_DASS
  - LG
disabled_rules:      # optional; turns a default-on rule off
  - PASSIVE_VOICE
```

- Rule IDs are LanguageTool IDs, uppercase, group IDs included.
- A rule both enabled and disabled in one mode is a startup error.
- Rules come from the `default="off"` nodes in LanguageTool's German
  `grammar.xml` and `style.xml`. Rules marked `temp_off` are intentionally
  skipped: upstream disabled them for known false alarms.
- `neutral` and `casual` get correctness rules only. `formal` and `business`
  add correspondence, style, and recommended-spelling rules. `academic` adds
  correctness and recommended spelling but no colloquialisms or letter
  formulas.
- The client still wins: `disabledRules` removes a mode rule, and
  `enabledOnly=true` uses only the client's lists.
- Restart the gateway after editing a mode.

Not enabled, on purpose: `TEST_*` rules, rules whose examples no longer fire
(`IMP_AUX_SPELLING_RULE`, `ZWEI_UND_VIERZIG`, `AUSGESCHRIEBENE_ZAHLEN`,
`TYPOGRAFISCHES_ZOLLZEICHEN`), the optional-comma hints, and the ambiguous
`SIE_ANREDE`/`SIE_KEINE_ANREDE` pair.

## Quick verification

```powershell
Invoke-RestMethod http://127.0.0.1:8077/v2/check `
  -Method Post `
  -ContentType "application/x-www-form-urlencoded" `
  -Body "data={%22annotation%22:[{%22text%22:%22Ein Email hier%22}]}&language=de-DE&writing_mode=formal"
```

The response should contain `EMAIL_HYPHEN` with replacement `E-Mail`.