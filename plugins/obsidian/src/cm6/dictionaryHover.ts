import { EditorView, hoverTooltip, Tooltip } from "@codemirror/view";
import { syntaxTree } from "@codemirror/language";
import { editorInfoField, requestUrl } from "obsidian";
import LanguageToolPlugin from "src";
import {
  DictionaryStatus,
  isSkippedNode,
  isUrl,
  wordAt
} from "../dictionaryHelpers";

const HOVER_DELAY_MS = 500;
const CACHE_SIZE = 300;

export interface DictionaryEntry {
  w: string;
  p: string;
  g: string;
  s: string[];
}

export interface DictionaryResult {
  word: string;
  lemma: string | null;
  entries: DictionaryEntry[];
}

const cache = new Map<string, DictionaryResult | null>();

function cachePut(key: string, value: DictionaryResult | null): void {
  if (cache.size >= CACHE_SIZE) {
    for (const oldest of cache.keys()) {
      cache.delete(oldest);
      break;
    }
  }
  cache.set(key, value);
}

async function lookup(
  plugin: LanguageToolPlugin,
  word: string
): Promise<DictionaryResult | null> {
  const pair = plugin.settings.dictionaryPair ?? "de-de";
  const key = `${pair}:${word.toLocaleLowerCase("de-DE")}`;
  if (cache.has(key)) {
    return cache.get(key) ?? null;
  }

  try {
    const response = await requestUrl({
      url: `${plugin.settings.serverUrl}/dictionary/lookup?word=${encodeURIComponent(
        word
      )}&pair=${pair}`,
      method: "GET",
      throw: false
    });
    if (response.status !== 200) {
      // Do not remember an outage as "this word has no entry".
      return null;
    }
    const result = response.json as DictionaryResult;
    const value = result.entries?.length ? result : null;
    cachePut(key, value);
    return value;
  } catch {
    // A miss or an offline gateway stays silent; LLM errors are not useful
    // while merely hovering.
    return null;
  }
}

function article(gender: string): string {
  return gender === "m" ? "der" : gender === "f" ? "die" : gender === "n" ? "das" : "";
}

function render(root: HTMLElement, result: DictionaryResult): void {
  for (const entry of result.entries) {
    const headword = root.createDiv({ cls: "lt-dict-headword" });
    if (entry.g) {
      headword.createSpan({ cls: "lt-dict-article", text: article(entry.g) + " " });
    }
    headword.createSpan({ text: entry.w });
    if (entry.p) {
      headword.createSpan({ cls: "lt-dict-pos", text: entry.p });
    }

    if (entry.s.length) {
      const senses = root.createEl("ul", { cls: "lt-dict-senses" });
      for (const sense of entry.s.slice(0, 3)) {
        senses.createEl("li", { text: sense });
      }
    }
  }
}

export function buildDictionaryHover(plugin: LanguageToolPlugin) {
  return hoverTooltip(
    async (view: EditorView, position: number): Promise<Tooltip | null> => {
      if (!plugin.settings.dictionaryHover) {
        return null;
      }
      // Read the frontmatter end from Obsidian's cache instead of copying the
      // whole document on every hover.
      const file = view.state.field(editorInfoField).file;
      const bodyStart = file
        ? plugin.app.metadataCache.getFileCache(file)?.frontmatterPosition?.end
            .offset
        : undefined;
      if (bodyStart !== undefined && position < bodyStart) {
        return null;
      }

      const line = view.state.doc.lineAt(position);
      const hit = wordAt(line.text, position - line.from);
      if (!hit || hit.word.length < 2 || isUrl(hit.word)) {
        return null;
      }

      const tree = syntaxTree(view.state);
      let node: ReturnType<typeof tree.resolveInner> | null = tree.resolveInner(
        position,
        -1
      );
      while (node) {
        if (isSkippedNode(node.name)) {
          return null;
        }
        node = node.parent;
      }

      const result = await lookup(plugin, hit.word);
      if (!result) {
        return null;
      }

      return {
        pos: line.from + hit.from,
        end: line.from + hit.to,
        above: true,
        create: () => {
          const dom = createDiv({ cls: "lt-dict-tooltip" });
          render(dom, result);
          return { dom };
        }
      };
    },
    { hoverTime: HOVER_DELAY_MS }
  );
}

export async function fetchDictionaryStatus(
  serverUrl: string
): Promise<DictionaryStatus | null> {
  try {
    const response = await requestUrl({
      url: `${serverUrl}/dictionary/status`,
      method: "GET",
      throw: false
    });
    return response.status === 200 ? (response.json as DictionaryStatus) : null;
  } catch {
    return null;
  }
}