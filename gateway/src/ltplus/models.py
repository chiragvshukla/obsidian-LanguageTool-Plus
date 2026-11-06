"""Typed models for declarative writing modes."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Level = Literal["default", "picky"]


class Mode(BaseModel):
    """One writing mode, loaded from `modes/<id>.yaml`."""

    model_config = {"extra": "forbid"}

    id: str
    label: str
    description: str = ""
    level: Level = "default"
    enabled_categories: list[str] = Field(default_factory=list)
    disabled_categories: list[str] = Field(default_factory=list)
    enabled_rules: list[str] = Field(default_factory=list)
    disabled_rules: list[str] = Field(default_factory=list)
    prompt: str = ""
    temperature: float = 0.2

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not value or not all(char.isalnum() or char in "-_" for char in value):
            raise ValueError("mode id must contain only letters, digits, '-' and '_'")
        return value

    @field_validator("prompt")
    @classmethod
    def _valid_prompt(cls, value: str) -> str:
        if value and (Path(value).name != value or value in {".", ".."}):
            raise ValueError("prompt must be a file name resolved under prompts/<language>/")
        return value

    @model_validator(mode="after")
    def _rules_disjoint(self) -> Mode:
        overlap = set(self.enabled_rules) & set(self.disabled_rules)
        if overlap:
            raise ValueError(f"rules both enabled and disabled: {sorted(overlap)}")
        return self
