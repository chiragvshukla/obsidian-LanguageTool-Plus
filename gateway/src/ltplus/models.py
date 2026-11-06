"""Typed models for declarative writing modes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

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
    prompt: str = ""
    temperature: float = 0.2

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not value or not all(char.isalnum() or char in "-_" for char in value):
            raise ValueError("mode id must contain only letters, digits, '-' and '_'")
        return value
