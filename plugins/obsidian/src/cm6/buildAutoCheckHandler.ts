import { EditorView, ViewPlugin, ViewUpdate } from "@codemirror/view";
import { editorInfoField, MarkdownView } from "obsidian";
import LanguageToolPlugin from "src";
import { getDocumentAutoCheck } from "../helpers";

// The model is much slower than LanguageTool, so the automatic pass waits
// longer and checks only the paragraph around the cursor.
const AI_AUTO_CHECK_DELAY_MS = 10_000;

function shouldAutoCheck(
  plugin: LanguageToolPlugin,
  view: EditorView
): boolean {
  const { file } = view.state.field(editorInfoField);
  return (
    getDocumentAutoCheck(plugin.app, file) ?? plugin.settings.shouldAutoCheck
  );
}

export function buildAutoCheckHandler(plugin: LanguageToolPlugin) {
  // A ViewPlugin gets one instance per editor, so the debounce timer and the
  // accumulated range are isolated per pane and cleaned up with the editor.
  return ViewPlugin.define(view => {
    let debounceTimer = -1;
    let minRange = Infinity;
    let maxRange = -Infinity;
    let aiTimer = -1;
    let aiPosition = 0;

    return {
      update(update: ViewUpdate) {
        // Moving the cursor abandons a pending check of the old paragraph.
        if (update.selectionSet && aiTimer !== -1) {
          window.clearTimeout(aiTimer);
          aiTimer = -1;
        }

        if (!update.docChanged) {
          return;
        }

        if (shouldAutoCheck(plugin, view)) {
          // Keep positions accumulated from earlier edits valid in the new doc
          if (minRange !== Infinity) {
            minRange = update.changes.mapPos(minRange, -1);
            maxRange = update.changes.mapPos(maxRange, 1);
          }

          update.changes.iterChangedRanges((_fromA, _toA, fromB, toB) => {
            minRange = Math.min(minRange, fromB);
            maxRange = Math.max(maxRange, toB);
          });

          window.clearTimeout(debounceTimer);

          debounceTimer = window.setTimeout(() => {
            const docLength = view.state.doc.length;
            const from = Math.min(minRange, docLength);
            const to = Math.min(maxRange, docLength);

            minRange = Infinity;
            maxRange = -Infinity;

            const startLine = view.lineBlockAt(from);
            const endLine = view.lineBlockAt(to);

            const markdownView = view.state.field(editorInfoField);

            plugin
              .runDetection(
                view,
                markdownView as MarkdownView,
                startLine.from,
                endLine.to
              )
              .catch(e => {
                console.error(e);
              });
          }, plugin.settings.autoCheckDelay);
        }

        if (plugin.settings.enableAIFeatures && plugin.settings.aiAutoCheck) {
          window.clearTimeout(aiTimer);
          aiPosition = update.state.selection.main.head;
          aiTimer = window.setTimeout(() => {
            aiTimer = -1;
            plugin.checkParagraphWithAI(view, aiPosition).catch(e => {
              console.error(e);
            });
          }, AI_AUTO_CHECK_DELAY_MS);
        }
      },
      destroy() {
        window.clearTimeout(debounceTimer);
        window.clearTimeout(aiTimer);
      }
    };
  });
}