import type { Text } from "@codemirror/state";
import type { MatchesEntity } from "./LanguageToolTypings";
import type { RewriteChange } from "./rewrite";

export const AI_RULE_ID = "AI_GRAMMAR";

/** Longest paragraph the automatic pass sends to the model. */
export const AI_AUTO_MAX_CHARS = 2000;

/** Whether a CodeMirror decoration holds one of our AI matches. */
export function isAIUnderline(value: { spec?: unknown }): boolean {
  const spec = value.spec as
    | { match?: { rule?: { id?: string } } }
    | undefined;
  return spec?.match?.rule?.id === AI_RULE_ID;
}

/** Turn validated rewrite changes into matches the existing UI can render. */
export function changesToMatches(
  baseOffset: number,
  source: string,
  changes: RewriteChange[]
): MatchesEntity[] {
  const matches: MatchesEntity[] = [];
  let cursor = 0;
  for (const change of changes) {
    // The popover renders no button for an empty replacement.
    if (!change.replacement.trim()) {
      continue;
    }
    let offset = change.offset;
    let length = change.length;
    if (
      typeof offset !== "number" ||
      typeof length !== "number" ||
      source.slice(offset, offset + length) !== change.original
    ) {
      offset = source.indexOf(change.original, cursor);
      length = change.original.length;
    }
    if (
      offset < cursor ||
      offset + length > source.length ||
      source.slice(offset, offset + length) !== change.original
    ) {
      continue;
    }
    cursor = offset + length;
    matches.push({
      message:
        change.explanation || `${change.original} → ${change.replacement}`,
      shortMessage: "AI grammar",
      replacements: [{ value: change.replacement }],
      offset: baseOffset + offset,
      length,
      context: { text: source, offset, length },
      sentence: source,
      type: { typeName: "Other" },
      rule: {
        id: AI_RULE_ID,
        description: "AI grammar suggestion",
        issueType: "grammar",
        category: { id: "GRAMMAR", name: "Grammar" }
      },
      ignoreForIncompleteSentence: false,
      contextForSureMatch: 0
    });
  }
  return matches;
}

/** The block between blank lines around `pos`, or null on an empty line. */
export function paragraphAt(
  doc: Text,
  pos: number
): { from: number; to: number; text: string } | null {
  const bounded = Math.max(0, Math.min(pos, doc.length));
  const line = doc.lineAt(bounded);
  if (!line.text.trim()) {
    return null;
  }
  let start = line;
  let end = start;

  while (start.number > 1 && doc.line(start.number - 1).text.trim()) {
    start = doc.line(start.number - 1);
  }
  while (end.number < doc.lines && doc.line(end.number + 1).text.trim()) {
    end = doc.line(end.number + 1);
  }

  const text = doc.sliceString(start.from, end.to);
  return text.trim() ? { from: start.from, to: end.to, text } : null;
}