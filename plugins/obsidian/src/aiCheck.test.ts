import { Text } from "@codemirror/state";
import { changesToMatches, isAIUnderline, paragraphAt } from "./aiCheck";

function equal(actual: unknown, expected: unknown) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

const source = "Der Mädchen geht. Das Mann ist groß.";
const changes = [
  { original: "Der", replacement: "Das", offset: 0, length: 3, explanation: "sächlich" },
  { original: "geht", replacement: "", offset: source.indexOf("geht"), length: 4 },
  { original: "Das", replacement: "Der", offset: source.indexOf("Das"), length: 3 },
  { original: "nope", replacement: "x", offset: 0, length: 4 }
];

const matches = changesToMatches(100, source, changes);
equal(matches.length, 2);
equal([matches[0].offset, matches[0].length], [100, 3]);
equal(matches[1].offset, 100 + source.indexOf("Das"));
equal(matches[0].rule.id, "AI_GRAMMAR");

const withEmoji = "😀 Der Mädchen geht.";
const emojiMatches = changesToMatches(0, withEmoji, [
  // Python counts code points, JS counts UTF-16 units, so this offset is off.
  { original: "Der", replacement: "Das", offset: 2, length: 3 }
]);
equal(emojiMatches.length, 1);
equal(emojiMatches[0].offset, withEmoji.indexOf("Der"));

const doc = Text.of(["first", "", "second para", "continues", "", "third"]);
const paragraph = paragraphAt(doc, doc.line(3).from);
equal(paragraph, {
  from: doc.line(3).from,
  to: doc.line(4).to,
  text: "second para\ncontinues"
});
equal(paragraphAt(doc, doc.line(2).from), null);

const aiDecoration = { spec: { match: { rule: { id: "AI_GRAMMAR" } } } };
const ltDecoration = { spec: { match: { rule: { id: "MORFOLOGIK_RULE_DE_DE" } } } };
equal(isAIUnderline(aiDecoration), true);
equal(isAIUnderline(ltDecoration), false);
equal(isAIUnderline({}), false);