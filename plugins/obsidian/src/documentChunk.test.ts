import { chunkDocument } from "./documentChunk";

function equal(actual: unknown, expected: unknown) {
  if (actual !== expected) {
    throw new Error(`expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

const note = [
  "---",
  "tags: [test]",
  "---",
  "",
  "Erster Absatz. Zweiter Satz.",
  "",
  "Zweiter Absatz mit etwas mehr Text.",
  "",
  "```",
  "const ignored = true;",
  "```",
  "",
  "Dritter Absatz."
].join("\n");

const chunks = chunkDocument(note, 40);

equal(chunks.length > 0, true);
equal(
  chunks.every(chunk => chunk.text.length <= 40 && chunk.text.trim().length > 0),
  true
);
equal(
  chunks.every(chunk => note.slice(chunk.from, chunk.to) === chunk.text),
  true
);
equal(chunks.some(chunk => chunk.text.includes("tags:")), false);
equal(chunks.some(chunk => chunk.text.includes("const ignored")), false);
equal(
  chunks.map(chunk => chunk.text).join(" ").includes("Dritter Absatz."),
  true
);

const contiguous = chunkDocument("aa bb cc dd ee ff gg hh", 12);
equal(
  contiguous.every((chunk, index) => {
    const next = contiguous[index + 1];
    return !next || chunk.to <= next.from;
  }),
  true
);
equal(
  contiguous.every(chunk => chunk.text === "aa bb cc dd ee ff gg hh".slice(chunk.from, chunk.to)),
  true
);

const unbroken = chunkDocument("x".repeat(50), 20);
equal(unbroken.map(chunk => chunk.text.length).join(","), "20,20,10");

const allCode = chunkDocument("```\ncode\n```", 100);
equal(allCode.length, 0);

const aroundCode = chunkDocument("aa\n\n```\ncode\n```\n\nbb", 100);
equal(aroundCode.length, 2);
equal(aroundCode.some(chunk => chunk.text.includes("code")), false);