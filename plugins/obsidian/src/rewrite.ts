import { App, Modal, requestUrl, Setting } from "obsidian";
import { LanguageToolPluginSettings } from "./SettingsTab";

interface RewriteErrorBody {
  error?: { message?: string };
}

interface RewriteResponseBody {
  rewritten: string;
}

/**
 * Ask the gateway for a rewrite. Only call this when AI features are enabled.
 * The gateway returns {original, rewritten, changes}; the plugin uses
 * `rewritten` and leaves review of individual changes to a later phase.
 */
export async function requestRewrite(
  settings: LanguageToolPluginSettings,
  text: string,
  language?: string
): Promise<string> {
  const body: Record<string, string> = {
    text,
    mode: settings.writingMode ?? "neutral"
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

  return (res.json as RewriteResponseBody).rewritten;
}

/** Show the original and the rewrite side by side before replacing. */
export class RewriteModal extends Modal {
  constructor(
    app: App,
    private readonly original: string,
    private readonly rewritten: string,
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