import { App, FuzzySuggestModal } from "obsidian";
import {
  DICTIONARY_PAIRS,
  DictionaryPair,
  WRITING_MODES,
  WritingMode
} from "./SettingsTab";

/** Quick mode switch from the status bar and ribbon menus. */
export class WritingModeModal extends FuzzySuggestModal<WritingMode> {
  constructor(
    app: App,
    private readonly current: WritingMode | undefined,
    private readonly choose: (mode: WritingMode) => void
  ) {
    super(app);
    this.setPlaceholder("Writing mode");
  }

  getItems(): WritingMode[] {
    return Object.keys(WRITING_MODES) as WritingMode[];
  }

  getItemText(mode: WritingMode): string {
    const label = WRITING_MODES[mode];
    return mode === this.current ? `${label} (current)` : label;
  }

  onChooseItem(mode: WritingMode): void {
    this.choose(mode);
  }
}

/** Quick dictionary pair switch from the status bar and ribbon menus. */
export class DictionaryPairModal extends FuzzySuggestModal<DictionaryPair> {
  constructor(
    app: App,
    private readonly current: DictionaryPair | undefined,
    private readonly choose: (pair: DictionaryPair) => void
  ) {
    super(app);
    this.setPlaceholder("Dictionary pair");
  }

  getItems(): DictionaryPair[] {
    return Object.keys(DICTIONARY_PAIRS) as DictionaryPair[];
  }

  getItemText(pair: DictionaryPair): string {
    const label = DICTIONARY_PAIRS[pair];
    return pair === this.current ? `${label} (current)` : label;
  }

  onChooseItem(pair: DictionaryPair): void {
    this.choose(pair);
  }
}