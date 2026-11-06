import { App, Modal, Notice, Setting, requestUrl } from "obsidian";
import { LanguageToolPluginSettings } from "./SettingsTab";
import {
  formatFacts,
  formatIssueBreakdown,
  ScoreResult,
  TopicResult
} from "./practiceHelpers";

interface PracticeErrorBody {
  error?: { message?: string };
}

async function post<T>(
  settings: LanguageToolPluginSettings,
  path: string,
  body: Record<string, unknown>
): Promise<T> {
  const res = await requestUrl({
    url: `${settings.serverUrl}${path}`,
    method: "POST",
    contentType: "application/json",
    body: JSON.stringify(body),
    throw: false
  });

  if (res.status < 200 || res.status >= 300) {
    let message = `AI request failed (${res.status})`;
    try {
      const payload = res.json as PracticeErrorBody;
      if (payload?.error?.message) {
        message = payload.error.message;
      }
    } catch {
      // Keep the status message when the body is not JSON.
    }
    throw new Error(message);
  }
  return res.json as T;
}

export function requestScore(
  settings: LanguageToolPluginSettings,
  text: string,
  language: string | undefined,
  mode: string
): Promise<ScoreResult> {
  return post<ScoreResult>(settings, "/score", { text, language, mode });
}

export function requestTopic(
  settings: LanguageToolPluginSettings,
  language: string | undefined,
  mode: string
): Promise<TopicResult> {
  return post<TopicResult>(settings, "/topic", { language, mode });
}

const GRADE_LABELS: { key: keyof ScoreResult["grades"]; label: string }[] = [
  { key: "clarity", label: "Clarity" },
  { key: "tone", label: "Tone / mode" },
  { key: "vocabulary", label: "Vocabulary" },
  { key: "structure", label: "Structure" }
];

/** Read-only score report. Nothing is applied to the note. */
export class ScoreModal extends Modal {
  constructor(
    app: App,
    private readonly result: ScoreResult,
    private readonly modeLabel: string,
    private readonly onCloseReport: () => void
  ) {
    super(app);
  }

  onOpen() {
    const { contentEl } = this;
    contentEl.addClass("lt-score-modal");
    contentEl.createEl("h2", { text: "Writing score" });
    contentEl.createDiv({
      cls: "lt-score-mode",
      text: `Mode: ${this.modeLabel}`
    });
    if ((this.result.chunks ?? 1) > 1) {
      contentEl.createDiv({
        cls: "lt-score-mode",
        text: `Scored in ${this.result.chunks} sections; final grades combine the sections.`
      });
    }
    contentEl.createDiv({
      cls: "lt-score-facts",
      text: formatFacts(this.result.facts)
    });

    const breakdown = formatIssueBreakdown(this.result.facts);
    if (breakdown) {
      contentEl.createDiv({ cls: "lt-score-breakdown", text: breakdown });
    }

    const grades = contentEl.createDiv({ cls: "lt-score-grades" });
    for (const { key, label } of GRADE_LABELS) {
      const row = grades.createDiv({ cls: "lt-score-row" });
      row.createSpan({ cls: "lt-score-label", text: label });
      row.createSpan({
        cls: "lt-score-value",
        text: `${this.result.grades[key]} / 5`
      });
    }

    contentEl.createEl("h3", { text: "Recommendations" });
    if (this.result.recommendations.length === 0) {
      contentEl.createDiv({
        cls: "lt-score-recs",
        text: "No specific recommendations."
      });
    } else {
      const list = contentEl.createEl("ul", { cls: "lt-score-recs" });
      for (const recommendation of this.result.recommendations) {
        list.createEl("li", { text: recommendation });
      }
    }

    contentEl.createDiv({
      cls: "lt-score-note",
      text: "LanguageTool counts are exact; grades are the model's judgement."
    });

    new Setting(contentEl).addButton(button =>
      button
        .setButtonText("Close")
        .setCta()
        .onClick(() => this.close())
    );

    new Notice("Writing score ready", 2000);
  }

  onClose() {
    this.contentEl.empty();
    this.onCloseReport();
  }
}