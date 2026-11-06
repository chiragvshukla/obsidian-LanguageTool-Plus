/** True when the editor still holds exactly the text that was rewritten. */
export function selectionUnchanged(current: string, original: string): boolean {
  return current === original;
}

/** Note shown when the gateway discarded model changes that added errors. */
export function droppedChangesNotice(dropped: number): string | null {
  if (dropped <= 0) {
    return null;
  }
  return `${dropped} suggested change${dropped === 1 ? "" : "s"} dropped to avoid new errors`;
}