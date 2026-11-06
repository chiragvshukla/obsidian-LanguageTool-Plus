import { frontmatterEnd } from "./dictionaryHelpers";

/** Largest slice sent to the model by the whole-document check. */
export const AI_DOC_CHUNK_CHARS = 8000;

/** Largest slice sent to LanguageTool by one whole-document check. */
export const LT_DOC_CHUNK_CHARS = 30_000;

/** Refuse to fire more calls than this for one explicit document check. */
export const AI_DOC_MAX_CHUNKS = 20;

const FENCE = /^\s{0,3}(```|~~~)/;

export interface DocumentChunk {
  from: number;
  to: number;
  text: string;
}

interface Range {
  from: number;
  to: number;
}

function splitLongBlock(block: Range, doc: string, limit: number): DocumentChunk[] {
  const text = doc.slice(block.from, block.to);
  const pieces: DocumentChunk[] = [];
  const boundary = /[.!?]+\s+/g;
  const parts: Range[] = [];
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = boundary.exec(text)) !== null) {
    const end = match.index + match[0].trimEnd().length;
    parts.push({ from: last, to: end });
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    parts.push({ from: last, to: text.length });
  }

  for (const part of parts) {
    const partText = text.slice(part.from, part.to);
    for (let index = 0; index < partText.length; index += limit) {
      const slice = partText.slice(index, index + limit);
      if (!slice.trim()) {
        continue;
      }
      const from = block.from + part.from + index;
      pieces.push({ from, to: from + slice.length, text: slice });
    }
  }
  return pieces;
}

/**
 * Split a note into sections the gateway will accept. Paragraph boundaries
 * come first, then sentence boundaries. Frontmatter and fenced code blocks are
 * skipped. The gateway uses the same rules for long-note scoring; keep the two
 * in sync.
 */
export function chunkDocument(
  doc: string,
  limit = AI_DOC_CHUNK_CHARS,
  skipFrontmatter = true
): DocumentChunk[] {
  const start = skipFrontmatter ? frontmatterEnd(doc) : 0;
  const body = doc.slice(start);

  const blocks: Range[] = [];
  const separator = /\n[ \t]*\n+/g;
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = separator.exec(body)) !== null) {
    blocks.push({ from: cursor, to: match.index });
    cursor = match.index + match[0].length;
  }
  blocks.push({ from: cursor, to: body.length });

  const pieces: DocumentChunk[] = [];
  for (const block of blocks) {
    const text = body.slice(block.from, block.to);
    if (!text.trim()) {
      continue;
    }
    // shortcut: a block that merely touches a fence is dropped whole. Code
    // fences usually stand alone; revisit if prose next to fences gets skipped.
    if (text.split("\n").some(line => FENCE.test(line))) {
      continue;
    }
    const absolute = {
      from: start + block.from,
      to: start + block.to,
      text
    };
    if (text.length <= limit) {
      pieces.push(absolute);
    } else {
      pieces.push(...splitLongBlock(absolute, doc, limit));
    }
  }

  const chunks: DocumentChunk[] = [];
  let current: DocumentChunk | null = null;
  for (const piece of pieces) {
    if (!current) {
      current = piece;
      continue;
    }
    if (
      doc.slice(current.to, piece.from).trim() === "" &&
      piece.to - current.from <= limit
    ) {
      current = {
        from: current.from,
        to: piece.to,
        text: doc.slice(current.from, piece.to)
      };
    } else {
      chunks.push(current);
      current = piece;
    }
  }
  if (current) {
    chunks.push(current);
  }
  return chunks;
}