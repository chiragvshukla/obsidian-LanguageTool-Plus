import { App, Modal, requestUrl, Setting } from "obsidian";
import { LanguageToolPluginSettings } from "./SettingsTab";

interface RewriteErrorBody {
  error?: { message?: string };
}

interface RewriteChange {
  original: string;
  replacement: string;
  category?: string;
  explanation?: string;
}

interface RewriteResponseBody {
  rewritten: string;
  changes?: RewriteChange[];
}

export interface RewriteResult {
  rewritten: string;
  changes: RewriteChange[];
}

/**
 * Ask the gateway for a rewrite. Only call this when AI features are enabled.
 * The gateway returns {original, rewritten, changes}; the modal shows the
 * rewritten text and the short explanation for each change.
 */
export async function requestRewrite(
  settings: LanguageToolPluginSettings,
  text: string,
  language?: string,
  mode?: string
): Promise<RewriteResult> {
  const body: Record<string, string> = {
    text,
    mode: mode ?? settings.writingMode ?? "neutral"
  };
  if (language) {
    body.language = language;
  }

  const res = await requestUrl({
    url: `${settings.serverUrl}/rewrite`,
    method: "POST",
    contentType: "application/json",
    body: JSON.stringify(body),
    throw: false
  });

  if (res.status < 200 || res.status >= 300) {
    let message = `AI rewrite failed (${res.status})`;
    try {
      const payload = res.json as RewriteErrorBody;
      if (payload?.error?.message) {
        message = payload.error.message;
      }
    } catch {
      // Keep the status message when the body is not JSON.
    }
    throw new Error(message);
  }

  const payload = res.json as RewriteResponseBody;
  return { rewritten: payload.rewritten, changes: payload.changes ?? [] };
}

/** Show the original and the rewrite side by side before replacing. */
export class RewriteModal extends Modal {
  constructor(
    app: App,
    private readonly original: string,
    private readonly rewritten: string,
    private readonly changes: RewriteChange[],
    private readonly onReplace: (value: string) => void
  ) {
    super(app);
  }

  onOpen() {
    const { contentEl } = this;
    contentEl.createEl("h2", { text: "AI rewrite" });
    contentEl.createEl("h3", { text: "Original" });
    contentEl.createEl("pre", { text: this.original });
    contentEl.createEl("h3", { text: "Rewritten" });
    contentEl.createEl("pre", { text: this.rewritten });

    if (this.changes.length > 0) {
      contentEl.createEl("h3", { text: "Changes" });
      const list = contentEl.createEl("ul");
      for (const change of this.changes) {
        list.createEl("li", {
          text:
            change.explanation ||
            `${change.original} → ${change.replacement}`
        });
      }
    }

    new Setting(contentEl)
      .addButton(button =>
        button
          .setButtonText("Replace")
          .setCta()
          .onClick(() => {
            this.onReplace(this.rewritten);
            this.close();
          })
      )
      .addButton(button =>
        button.setButtonText("Cancel").onClick(() => this.close())
      );
  }

  onClose() {
    this.contentEl.empty();
  }
}