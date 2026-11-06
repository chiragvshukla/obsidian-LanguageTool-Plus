import { EditorView, ViewPlugin, ViewUpdate } from "@codemirror/view";
import { editorInfoField, MarkdownView } from "obsidian";
import LanguageToolPlugin from "src";
import { getDocumentAutoCheck } from "../helpers";

// The model is much slower than LanguageTool, so the automatic pass waits
// longer and checks only the sentence around the cursor.
const AI_AUTO_CHECK_DELAY_MS = 4_000;

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

    return {
      update(update: ViewUpdate) {
        // A cursor move is a selection-only update. It must still arm the AI
        // pass, so a sentence the user did not just type can be checked.
        const cursorSettled =
          update.selectionSet && update.state.selection.main.empty;
        if (!update.docChanged && !update.selectionSet) {
          return;
        }

        if (plugin.scoringOpen) {
          window.clearTimeout(debounceTimer);
          window.clearTimeout(aiTimer);
          return;
        }

        // A non-empty selection has no single sentence to check. Drop a pending
        // pass so selecting text does not fire one.
        if (!update.docChanged && !cursorSettled) {
          window.clearTimeout(aiTimer);
          aiTimer = -1;
          return;
        }

        if (update.docChanged && shouldAutoCheck(plugin, view)) {
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
            if (plugin.scoringOpen) {
              return;
            }
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

        if (plugin.isAiReady() && plugin.settings.aiAutoCheck) {
          window.clearTimeout(aiTimer);
          aiTimer = window.setTimeout(() => {
            aiTimer = -1;
            if (plugin.scoringOpen) {
              return;
            }
            // Read the cursor when the pause ends: Obsidian emits
            // selection-only updates while typing, and they must not cancel
            // the check.
            plugin.checkParagraphWithAI(view).catch(e => {
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