import { App, Modal, requestUrl, Setting } from "obsidian";
import { droppedChangesNotice } from "./rewriteGuard";
import { LanguageToolPluginSettings } from "./SettingsTab";

interface RewriteErrorBody {
  error?: { message?: string };
}

export interface RewriteChange {
  original: string;
  replacement: string;
  category?: string;
  explanation?: string;
  offset?: number;
  length?: number;
}

interface RewriteResponseBody {
  rewritten: string;
  changes?: RewriteChange[];
  dropped?: number;
}

export interface RewriteResult {
  rewritten: string;
  changes: RewriteChange[];
  dropped: number;
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
  mode?: string,
  categories?: string[],
  context?: { before?: string; after?: string },
  headers: Record<string, string> = {}
): Promise<RewriteResult> {
  const body: Record<string, string | string[]> = {
    text,
    mode: mode ?? settings.writingMode ?? "neutral"
  };
  if (language) {
    body.language = language;
  }
  if (categories) {
    body.categories = categories;
  }
  if (context?.before) {
    body.context_before = context.before;
  }
  if (context?.after) {
    body.context_after = context.after;
  }

  const res = await requestUrl({
    url: `${settings.serverUrl}/rewrite`,
    method: "POST",
    contentType: "application/json",
    body: JSON.stringify(body),
    headers,
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
  return {
    rewritten: payload.rewritten,
    changes: payload.changes ?? [],
    dropped: payload.dropped ?? 0
  };
}

/** Show the original and the rewrite side by side before replacing. */
export class RewriteModal extends Modal {
  constructor(
    app: App,
    private readonly original: string,
    private readonly rewritten: string,
    private readonly changes: RewriteChange[],
    private readonly dropped: number,
    private readonly onReplace: (value: string) => boolean
  ) {
    super(app);
  }

  onOpen() {
    const { contentEl } = this;
    this.modalEl.addClass("lt-rewrite-modal");
    contentEl.createEl("h2", { text: "AI rewrite" });
    contentEl.createEl("h3", { text: "Original" });
    contentEl.createEl("pre", { cls: "lt-rewrite-text", text: this.original });
    contentEl.createEl("h3", { text: "Rewritten" });
    this.renderRewritten(contentEl);

    const dropped = droppedChangesNotice(this.dropped);
    if (dropped) {
      contentEl.createEl("p", { text: dropped });
    }

    if (this.changes.length > 0) {
      contentEl.createEl("h3", { text: "Changes" });
      const list = contentEl.createEl("ul", { cls: "lt-rewrite-changes" });
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
            if (this.onReplace(this.rewritten)) {
              this.close();
            }
          })
      )
      .addButton(button =>
        button.setButtonText("Cancel").onClick(() => this.close())
      );
  }

  /**
   * Rebuild the rewritten text with changed spans marked. The gateway sends
   * source offsets; if they are missing or do not line up, show plain text
   * rather than a misleading highlight.
   */
  private renderRewritten(container: HTMLElement) {
    const pre = container.createEl("pre", { cls: "lt-rewrite-text" });
    const spans: { offset: number; length: number; change: RewriteChange }[] = [];

    let cursor = 0;
    for (const change of this.changes) {
      let offset = change.offset;
      let length = change.length;
      if (
        typeof offset !== "number" ||
        typeof length !== "number" ||
        this.original.slice(offset, offset + length) !== change.original
      ) {
        offset = this.original.indexOf(change.original, cursor);
        length = change.original.length;
      }
      if (
        offset < cursor ||
        length <= 0 ||
        offset + length > this.original.length ||
        this.original.slice(offset, offset + length) !== change.original
      ) {
        pre.setText(this.rewritten);
        return;
      }
      spans.push({ offset, length, change });
      cursor = offset + length;
    }

    let rebuilt = "";
    cursor = 0;
    for (const { offset, length, change } of spans) {
      rebuilt += this.original.slice(cursor, offset) + change.replacement;
      cursor = offset + length;
    }
    rebuilt += this.original.slice(cursor);

    if (rebuilt !== this.rewritten) {
      pre.setText(this.rewritten);
      return;
    }

    cursor = 0;
    for (const { offset, length, change } of spans) {
      if (offset > cursor) {
        pre.appendText(this.original.slice(cursor, offset));
      }
      if (change.replacement) {
        const mark = pre.createEl("mark", {
          cls: "lt-rewrite-change",
          text: change.replacement
        });
        if (change.explanation) {
          mark.setAttribute("title", change.explanation);
        }
      } else {
        // Nothing remains to mark, so show a small display-only marker.
        const marker = pre.createSpan({
          cls: "lt-rewrite-deletion",
          text: "removed"
        });
        if (change.explanation) {
          marker.setAttribute("title", change.explanation);
        }
      }
      cursor = offset + length;
    }
    pre.appendText(this.original.slice(cursor));
  }

  onClose() {
    this.contentEl.empty();
  }
}