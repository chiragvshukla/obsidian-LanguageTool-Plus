import { App, FuzzySuggestModal } from "obsidian";
import { WRITING_MODES, WritingMode } from "./SettingsTab";

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