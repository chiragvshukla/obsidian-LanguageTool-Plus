/** Pure helpers for the hover dictionary; no Obsidian imports so they test easily. */

export interface DictionaryStatus {
  pairs: Record<string, { installed: boolean; bytes: number }>;
  building: boolean;
  message: string;
  error: string;
}

// Words may contain letters, combining marks, and internal hyphens or
// apostrophes (Häuser, E-Mail, geht's).
const WORD = /[\p{L}\p{M}]+(?:['’-][\p{L}\p{M}]+)*/gu;

// Markdown and code nodes where a dictionary hint would be noise.
const SKIP_NODES = new Set([
  "code",
  "comment",
  "fenced-code",
  "frontmatter",
  "hmd-frontmatter",
  "html",
  "image",
  "inline-code",
  "link",
  "url"
]);

export function wordAt(
  lineText: string,
  position: number
): { word: string; from: number; to: number } | null {
  for (const match of lineText.matchAll(WORD)) {
    const from = match.index ?? 0;
    const to = from + match[0].length;
    if (position >= from && position <= to) {
      return { word: match[0], from, to };
    }
  }
  return null;
}

/** End offset of the leading YAML block, or 0 when there is none. */
export function frontmatterEnd(doc: string): number {
  if (!doc.startsWith("---\n") && !doc.startsWith("---\r\n")) {
    return 0;
  }
  const closing = doc.slice(4).search(/^---[ \t]*\r?$/m);
  if (closing === -1) {
    return 0;
  }
  return 4 + closing + doc.slice(4 + closing).indexOf("\n") + 1;
}

export function isSkippedNode(name: string): boolean {
  return SKIP_NODES.has(name);
}

export function isUrl(word: string): boolean {
  return /^(?:https?:\/\/|www\.)/i.test(word);
}

/** Human-readable install state for the settings tab. */
export function describeDictionaryStatus(
  status: DictionaryStatus | null,
  pair: string
): string {
  if (!status) {
    return "Gateway unreachable.";
  }
  const current = status.pairs[pair];
  if (!current?.installed) {
    return status.building ? "Downloading…" : "Not installed.";
  }
  const megabytes = current.bytes / (1024 * 1024);
  const installed = `Installed (${megabytes.toFixed(1)} MB).`;
  if (!status.building) {
    return installed;
  }
  return `${installed} ${status.message || "Updating…"}`;
}