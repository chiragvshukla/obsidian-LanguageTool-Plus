export interface ScoreIssue {
  category: string;
  count: number;
}

export interface ScoreFacts {
  words: number;
  sentences: number;
  averageSentenceWords: number;
  ltIssues: ScoreIssue[];
}

export interface ScoreGrades {
  clarity: number;
  tone: number;
  vocabulary: number;
  structure: number;
}

export interface ScoreResult {
  facts: ScoreFacts;
  grades: ScoreGrades;
  recommendations: string[];
}

export interface TopicResult {
  topic: string;
  angle: string;
}

export function formatFacts(facts: ScoreFacts): string {
  const base = `${facts.words} words · ${facts.sentences} sentences · ${facts.averageSentenceWords} words/sentence`;
  const issues = facts.ltIssues.reduce((sum, issue) => sum + issue.count, 0);
  return `${base} · ${issues} LanguageTool ${issues === 1 ? "finding" : "findings"}`;
}

export function formatIssueBreakdown(facts: ScoreFacts): string {
  return facts.ltIssues.map(issue => `${issue.category} ${issue.count}`).join(" · ");
}

/** The topic is inserted as a blockquote, with its angle on a second line. */
export function formatTopic(result: TopicResult): string {
  const lines = [`> **Writing prompt:** ${result.topic.trim()}`];
  const angle = result.angle.trim();
  if (angle) {
    lines.push(`> **Angle:** ${angle}`);
  }
  return lines.join("\n");
}