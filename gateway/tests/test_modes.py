from pathlib import Path

import pytest

from ltplus.modes import ModeConfigError, load_modes

VALID = """\
id: formal
label: Formal
level: picky
enabled_categories: [STYLE]
disabled_categories: []
"""


def test_loads_valid_modes(tmp_path: Path) -> None:
    (tmp_path / "formal.yaml").write_text(VALID, encoding="utf-8")

    modes = load_modes(tmp_path)

    assert modes["formal"].level == "picky"
    assert modes["formal"].enabled_categories == ["STYLE"]


def test_rejects_id_mismatch(tmp_path: Path) -> None:
    (tmp_path / "other.yaml").write_text(VALID, encoding="utf-8")

    with pytest.raises(ModeConfigError, match="must match the file name"):
        load_modes(tmp_path)


def test_rejects_invalid_yaml(tmp_path: Path) -> None:
    (tmp_path / "broken.yaml").write_text("id: [unclosed", encoding="utf-8")

    with pytest.raises(ModeConfigError, match="cannot read"):
        load_modes(tmp_path)


def test_rejects_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(ModeConfigError, match="no modes found"):
        load_modes(tmp_path)


def test_rejects_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(ModeConfigError, match="not found"):
        load_modes(tmp_path / "missing")
