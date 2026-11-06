# Adding words and rules

Three places extend what LanguageTool finds. None of them requires rebuilding
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

Rules must be written from scratch. Do not copy LanguageTool closed rule text.

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

## Quick verification

```powershell
Invoke-RestMethod http://127.0.0.1:8077/v2/check `
  -Method Post `
  -ContentType "application/x-www-form-urlencoded" `
  -Body "data={%22annotation%22:[{%22text%22:%22Ein Email hier%22}]}&language=de-DE&writing_mode=formal"
```

The response should contain `EMAIL_HYPHEN` with replacement `E-Mail`.