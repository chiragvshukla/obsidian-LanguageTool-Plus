import {
  formatFacts,
  formatIssueBreakdown,
  formatTopic
} from "./practiceHelpers";

function equal(actual: unknown, expected: unknown) {
  if (actual !== expected) {
    throw new Error(`expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

const facts = {
  words: 312,
  sentences: 18,
  averageSentenceWords: 17.3,
  ltIssues: [
    { category: "GRAMMAR", count: 3 },
    { category: "STYLE", count: 2 }
  ]
};

equal(
  formatFacts(facts),
  "312 words · 18 sentences · 17.3 words/sentence · 5 LanguageTool findings"
);
equal(formatIssueBreakdown(facts), "GRAMMAR 3 · STYLE 2");
equal(formatIssueBreakdown({ ...facts, ltIssues: [] }), "");
equal(
  formatFacts({ ...facts, words: 1, sentences: 1, averageSentenceWords: 1, ltIssues: [] }),
  "1 words · 1 sentences · 1 words/sentence · 0 LanguageTool findings"
);

equal(
  formatTopic(
    { topic: "Ein Tag im Homeoffice", angle: "Fokus auf den Morgen." },
    "de-DE"
  ),
  "> **Schreibthema:** Ein Tag im Homeoffice\n> **Fokus:** Fokus auf den Morgen."
);
equal(
  formatTopic(
    { topic: "A short walk", angle: "Focus on the morning." },
    "en-US"
  ),
  "> **Writing prompt:** A short walk\n> **Angle:** Focus on the morning."
);
equal(
  formatTopic({ topic: "  Ein Tag im Homeoffice  ", angle: "   " }),
  "> **Schreibthema:** Ein Tag im Homeoffice"
);