import type { Text } from "@codemirror/state";
import type { MatchesEntity } from "./LanguageToolTypings";
import type { RewriteChange } from "./rewrite";

export const AI_RULE_ID = "AI_GRAMMAR";

/** Longest paragraph the automatic pass sends to the model. */
export const AI_AUTO_MAX_CHARS = 2000;

/** Most context characters sent on each side of an automatic check. */
export const AI_CONTEXT_MAX_CHARS = 1000;

/**
 * The paragraph text before and after `range`, trimmed to the nearest
 * `limit` characters. The gateway treats it as read-only context.
 */
export function contextAround(
  paragraph: { from: number; text: string },
  range: { from: number; text: string },
  limit = AI_CONTEXT_MAX_CHARS
): { before: string; after: string } {
  const start = Math.max(0, range.from - paragraph.from);
  const end = Math.min(paragraph.text.length, start + range.text.length);
  return {
    before: paragraph.text.slice(Math.max(0, start - limit), start),
    after: paragraph.text.slice(end, end + limit)
  };
}

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
    // The gateway prompt asks for `vocabulary` when it suggests a word in the
    // text's language, so those hints get their own colour.
    const kind =
      change.category === "vocabulary"
        ? { short: "AI word", issue: "vocabulary", id: "VOCABULARY", name: "Vocabulary" }
        : change.category === "style"
        ? { short: "AI style", issue: "style", id: "STYLE", name: "Style" }
        : { short: "AI grammar", issue: "grammar", id: "GRAMMAR", name: "Grammar" };
    matches.push({
      message:
        change.explanation ||
        (change.replacement
          ? `${change.original} → ${change.replacement}`
          : `Remove "${change.original}"`),
      shortMessage: kind.short,
      // An empty replacement is a removal hint: the popover shows the
      // explanation and Ignore, but no button it cannot apply.
      replacements: change.replacement
        ? [{ value: change.replacement }]
        : [],
      offset: baseOffset + offset,
      length,
      context: { text: source, offset, length },
      sentence: source,
      type: { typeName: "Other" },
      rule: {
        id: AI_RULE_ID,
        description: `${kind.short} suggestion`,
        issueType: kind.issue,
        category: { id: kind.id, name: kind.name }
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

/**
 * The sentence around `pos`, bounded by the paragraph. The automatic check
 * uses this so one request covers a sentence, not a whole paragraph.
 * shortcut: the regex split treats "z. B." as a sentence end; use
 * Intl.Segmenter or LanguageTool sentenceRanges if that misleads in practice.
 */
export function sentenceAt(
  doc: Text,
  pos: number
): { from: number; to: number; text: string } | null {
  const paragraph = paragraphAt(doc, pos);
  if (!paragraph) {
    return null;
  }

  const local = pos - paragraph.from;
  const text = paragraph.text;
  const boundary = /[.!?…]+(?=\s|$)/g;
  let start = 0;
  let end = text.length;
  // Start and end of the segment before `start`, used when the caret sits in
  // the whitespace after a sentence end.
  let previousStart = 0;
  let previousEnd = 0;
  let match: RegExpExecArray | null;
  while ((match = boundary.exec(text)) !== null) {
    const after = match.index + match[0].length;
    // `<` keeps a period exactly at the caret in the sentence it ends; `<=`
    // would start an empty sentence after it.
    if (after < local) {
      previousStart = start;
      previousEnd = after;
      start = after;
      continue;
    }
    end = after;
    break;
  }

  // A caret right after the last period, or in the space behind it, still
  // belongs to that sentence.
  if (!text.slice(start, end).trim() && start > 0) {
    start = previousStart;
    end = previousEnd;
  }

  const raw = text.slice(start, end);
  const trimmed = raw.trim();
  if (!trimmed) {
    return null;
  }
  const leading = raw.length - raw.trimStart().length;
  const from = paragraph.from + start + leading;
  return { from, to: from + trimmed.length, text: trimmed };
}