"""Load and validate declarative writing modes.

Invalid YAML, a mismatched id, or an empty directory is a startup error. Modes
are read once; editing them requires a restart, which keeps request handling
free of file I/O and surprises.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from ltplus.models import Mode


class ModeConfigError(RuntimeError):
    """Raised when mode configuration cannot be loaded."""


def load_modes(directory: Path) -> dict[str, Mode]:
    """Return modes keyed by id. Raises ModeConfigError on any problem."""
    if not directory.is_dir():
        raise ModeConfigError(f"modes directory not found: {directory}")

    modes: dict[str, Mode] = {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            raise ModeConfigError(f"cannot read {path}: {exc}") from exc

        try:
            mode = Mode.model_validate(raw)
        except ValidationError as exc:
            raise ModeConfigError(f"invalid mode {path.name}: {exc}") from exc

        if mode.id != path.stem:
            raise ModeConfigError(
                f"{path.name}: id '{mode.id}' must match the file name '{path.stem}'"
            )
        modes[mode.id] = mode

    if not modes:
        raise ModeConfigError(f"no modes found in {directory}")
    return modes
