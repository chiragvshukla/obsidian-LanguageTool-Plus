import {
  describeDictionaryStatus,
  frontmatterEnd,
  isSkippedNode,
  isUrl,
  wordAt
} from "./dictionaryHelpers";

function equal(actual: unknown, expected: unknown) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

// Word extraction keeps umlauts, internal hyphens, and apostrophes but stops
// at surrounding punctuation.
equal(wordAt("Die Häuser sind groß.", 5), { word: "Häuser", from: 4, to: 10 });
equal(wordAt("Eine E-Mail kommt.", 7), { word: "E-Mail", from: 5, to: 11 });
equal(wordAt("Wie geht's?", 5), { word: "geht's", from: 4, to: 10 });
equal(wordAt("...", 1), null);
// A position at the end of a word still belongs to it.
equal(wordAt("Haus", 4), { word: "Haus", from: 0, to: 4 });

// YAML frontmatter is skipped before its closing line.
const withFrontmatter = "---\ntags: [a]\n---\nDer Text.";
equal(frontmatterEnd(withFrontmatter), withFrontmatter.indexOf("Der"));
equal(frontmatterEnd("Der Text."), 0);
equal(frontmatterEnd("---\nunclosed"), 0);
// A note that ends exactly on the closing fence has no trailing newline.
const noTrailingNewline = "---\ntags: [a]\n---";
equal(frontmatterEnd(noTrailingNewline), noTrailingNewline.length);

// Code, links, and URLs are skipped.
equal(isSkippedNode("inline-code"), true);
equal(isSkippedNode("paragraph"), false);
equal(isUrl("https://example.com"), true);
equal(isUrl("Haus"), false);

const status = {
  pairs: {
    "de-de": { installed: true, bytes: 5 * 1024 * 1024 },
    "en-de": { installed: false, bytes: 0 },
    "de-en": { installed: false, bytes: 0 }
  },
  building: false,
  message: "",
  error: ""
};
equal(describeDictionaryStatus(status, "de-de"), "Installed (5.0 MB).");
equal(describeDictionaryStatus(status, "en-de"), "Not installed.");
equal(describeDictionaryStatus(null, "de-de"), "Gateway unreachable.");

const building = { ...status, building: true, message: "de-de: indexing" };
equal(describeDictionaryStatus(building, "de-de"), "Installed (5.0 MB). de-de: indexing");
equal(describeDictionaryStatus(building, "en-de"), "Downloading…");