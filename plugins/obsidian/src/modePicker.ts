import { App, FuzzySuggestModal } from "obsidian";
import {
  DICTIONARY_PAIRS,
  DictionaryPair,
  WRITING_MODES,
  WritingMode
} from "./SettingsTab";

/** One fuzzy picker shared by the writing-mode and dictionary menus. */
class PickerModal<T> extends FuzzySuggestModal<T> {
  constructor(
    app: App,
    placeholder: string,
    private readonly items: T[],
    private readonly current: T | undefined,
    private readonly label: (item: T) => string,
    private readonly choose: (item: T) => void
  ) {
    super(app);
    this.setPlaceholder(placeholder);
  }

  getItems(): T[] {
    return this.items;
  }

  getItemText(item: T): string {
    const label = this.label(item);
    return item === this.current ? `${label} (current)` : label;
  }

  onChooseItem(item: T): void {
    this.choose(item);
  }
}

/** Quick mode switch from the status bar and ribbon menus. */
export class WritingModeModal extends PickerModal<WritingMode> {
  constructor(
    app: App,
    current: WritingMode | undefined,
    choose: (mode: WritingMode) => void
  ) {
    super(
      app,
      "Writing mode",
      Object.keys(WRITING_MODES) as WritingMode[],
      current,
      mode => WRITING_MODES[mode],
      choose
    );
  }
}

/** Quick dictionary pair switch from the status bar and ribbon menus. */
export class DictionaryPairModal extends PickerModal<DictionaryPair> {
  constructor(
    app: App,
    current: DictionaryPair | undefined,
    choose: (pair: DictionaryPair) => void
  ) {
    super(
      app,
      "Dictionary pair",
      Object.keys(DICTIONARY_PAIRS) as DictionaryPair[],
      current,
      pair => DICTIONARY_PAIRS[pair],
      choose
    );
  }
}