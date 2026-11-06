import { App } from "obsidian";
import { EditorView, Decoration, DecorationSet } from "@codemirror/view";
import { StateField, StateEffect } from "@codemirror/state";
import { syntaxTree, tokenClassNodeProp } from "@codemirror/language";
import {
  getIssueTypeClassName,
  getSpellcheckDictionary,
  ignoreListRegEx
} from "../helpers";
import { MatchesEntity } from "../LanguageToolTypings";
import { AI_RULE_ID, isAIUnderline } from "../aiCheck";

export interface UnderlineEffect {
  from: number;
  to: number;
  match: MatchesEntity;
}

export const addUnderline = StateEffect.define<UnderlineEffect>();
export const clearUnderlines = StateEffect.define();
export const clearUnderlinesInRange = StateEffect.define<{
  from: number;
  to: number;
}>();
export const clearAIUnderlinesInRange = StateEffect.define<{
  from: number;
  to: number;
}>();
export const clearLTUnderlines = StateEffect.define();
export const clearLTUnderlinesInRange = StateEffect.define<{
  from: number;
  to: number;
}>();
export const ignoreUnderline = StateEffect.define<{
  from: number;
  to: number;
}>();

function filterUnderlines(
  decorationStart: number,
  decorationEnd: number,
  rangeStart: number,
  rangeEnd: number
) {
  // Decoration begins in defined range
  if (decorationStart >= rangeStart && decorationStart <= rangeEnd) {
    return false;
  }

  // Decoration ends in defined range
  if (decorationEnd >= rangeStart && decorationEnd <= rangeEnd) {
    return false;
  }

  // Defined range begins within decoration
  if (rangeStart >= decorationStart && rangeStart <= decorationEnd) {
    return false;
  }

  // Defined range ends within decoration
  if (rangeEnd >= decorationStart && rangeEnd <= decorationEnd) {
    return false;
  }

  return true;
}

export const ignoredUnderlineField = StateField.define<{
  marks: DecorationSet;
  ignoredRanges: Set<string>;
}>({
  create() {
    return {
      // Using a decoration set allows us to update ignored ranges
      // when the document around them is changed
      marks: Decoration.none,

      // But we use this set to check if a range is ignored. See
      // underlineField below
      ignoredRanges: new Set()
    };
  },
  update(state, tr) {
    let marks = state.marks.map(tr.changes);

    // Clear out any decorations when their contents are edited
    if (tr.docChanged && tr.selection && marks.size) {
      marks = marks.update({
        filter: (from, to) =>
          filterUnderlines(
            from,
            to,
            tr.selection!.main.from,
            tr.selection!.main.to
          )
      });
    }

    for (const e of tr.effects) {
      if (e.is(ignoreUnderline)) {
        const { from, to } = e.value;
        marks = marks.update({
          add: [Decoration.mark({}).range(from, to)]
        });
      }
    }

    // Rebuild after every change so the set matches the final decorations.
    // State values are immutable; never touch `state` in place.
    const ignoredRanges = new Set<string>();
    marks.between(0, tr.newDoc.length, (from, to) => {
      ignoredRanges.add(`${from},${to}`);
    });

    return { marks, ignoredRanges };
  }
});

export const underlineField = StateField.define<DecorationSet>({
  create() {
    return Decoration.none;
  },
  update(underlines, tr) {
    const { ignoredRanges } = tr.state.field(ignoredUnderlineField);
    const seenRanges = new Set<string>();

    // Memoize any positions we check so we can avoid some work
    const seenPositions: Record<number, boolean> = {};
    // syntaxTree() only returns the parse work that already happened, so
    // reading it once up front costs nothing extra
    const tree = syntaxTree(tr.state);

    underlines = underlines.map(tr.changes);

    // Prevent decorations in codeblocks, etc...
    const canDecorate = (pos: number) => {
      if (seenPositions[pos] !== undefined) {
        return seenPositions[pos];
      }

      const nodeProps = tree.resolveInner(pos, 1).type.prop(tokenClassNodeProp);

      if (nodeProps && ignoreListRegEx.test(nodeProps)) {
        seenPositions[pos] = false;
      } else {
        seenPositions[pos] = true;
      }

      return seenPositions[pos];
    };

    // Ignore certain rules in special cases
    const isRuleAllowed = (match: MatchesEntity, from: number, to: number) => {
      // Don't show spelling errors for entries in the user dictionary
      if (match.rule.category.id === "TYPOS") {
        // This state field is a module-level singleton without access to the
        // plugin instance, so the app comes from Obsidian's global
        const { app } = (window as unknown) as { app: App };
        const str = tr.state.sliceDoc(from, to);

        if (getSpellcheckDictionary(app.vault).includes(str)) {
          return false;
        }
      }

      // Don't display whitespace rules in tables
      const lineNodeProp = tree
        .resolve(tr.newDoc.lineAt(from).from, 1)
        .type.prop(tokenClassNodeProp);

      if (lineNodeProp?.includes("table")) {
        if (match.rule.id === "WHITESPACE_RULE") {
          return false;
        }
      }

      return true;
    };

    // Clear out any decorations when their contents are edited
    if (tr.docChanged && tr.selection && underlines.size) {
      underlines = underlines.update({
        filter: (from, to) => {
          return filterUnderlines(
            from,
            to,
            tr.selection!.main.from,
            tr.selection!.main.to
          );
        }
      });
    }

    for (const e of tr.effects) {
      if (e.is(addUnderline)) {
        const { from, to, match } = e.value;
        const key = `${from},${to}`;

        if (
          !ignoredRanges.has(key) &&
          !seenRanges.has(key) &&
          canDecorate(from) &&
          canDecorate(to) &&
          isRuleAllowed(match, from, to)
        ) {
          seenRanges.add(key);
          underlines = underlines.update({
            add: [
              Decoration.mark({
                class: `lt-underline ${getIssueTypeClassName(
                  match.rule.category.id
                )}${match.rule.id === AI_RULE_ID ? " lt-ai" : ""}`,
                match
              }).range(from, to)
            ]
          });
        }
      } else if (e.is(clearUnderlines)) {
        underlines = Decoration.none;
      } else if (e.is(clearAIUnderlinesInRange)) {
        underlines = underlines.update({
          filter: (from, to, value) => {
            if (!isAIUnderline(value)) {
              return true;
            }
            return filterUnderlines(from, to, e.value.from, e.value.to);
          }
        });
      } else if (e.is(clearLTUnderlines)) {
        // LT checks must not erase AI hints they cannot reproduce.
        underlines = underlines.update({
          filter: (_from, _to, value) => isAIUnderline(value)
        });
      } else if (e.is(clearLTUnderlinesInRange)) {
        underlines = underlines.update({
          filter: (from, to, value) =>
            isAIUnderline(value) ||
            filterUnderlines(from, to, e.value.from, e.value.to)
        });
      } else if (e.is(clearUnderlinesInRange) || e.is(ignoreUnderline)) {
        underlines = underlines.update({
          filter: (from, to) =>
            filterUnderlines(from, to, e.value.from, e.value.to)
        });
      }
    }

    return underlines;
  },
  provide: f => EditorView.decorations.from(f)
});
