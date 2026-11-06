import { droppedChangesNotice, selectionUnchanged } from "./rewriteGuard";

function equal(actual: unknown, expected: unknown) {
  if (actual !== expected) {
    throw new Error(`expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

equal(selectionUnchanged("same text", "same text"), true);
equal(selectionUnchanged("edited text", "same text"), false);

equal(droppedChangesNotice(0), null);
equal(
  droppedChangesNotice(1),
  "1 suggested change dropped to avoid new errors"
);
equal(
  droppedChangesNotice(3),
  "3 suggested changes dropped to avoid new errors"
);