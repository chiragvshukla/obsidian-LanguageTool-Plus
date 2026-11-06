"""Extract JSON from a model reply that may not be only JSON.

Providers vary: some wrap the object in a code fence, some leave the Qwen
think block in `content`, some add a sentence before or after. Parsing the
content verbatim turns all of those into "not valid JSON".
"""

from __future__ import annotations

import json
import re
from typing import Any

_THINK = re.compile(r"<think\b[^>]*>.*?(?:</think\s*>|$)", re.IGNORECASE | re.DOTALL)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)(?:```|$)", re.IGNORECASE | re.DOTALL)
_DECODER = json.JSONDecoder()


def _decode(text: str) -> Any | None:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _unwrap(value: Any) -> Any:
    """Turn a JSON value encoded as a string back into the value."""
    for _ in range(2):
        if not isinstance(value, str):
            break
        nested = _decode(value)
        if nested is None:
            break
        value = nested
    return value


def _scan(text: str) -> list[Any]:
    """Outermost objects in the text, in document order."""
    found: list[Any] = []
    index = 0
    while index < len(text):
        start = text.find("{", index)
        if start < 0:
            break
        try:
            value, end = _DECODER.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(value, dict):
            found.append(_unwrap(value))
            index = end
        else:
            index = start + 1
    return found


def extract_candidates(text: str) -> list[Any]:
    """Parsed JSON values from a reply, most likely answer first.

    The last complete object in the text is usually the answer; earlier ones
    are examples in the reasoning. The caller validates each with pydantic, so
    a wrong candidate is skipped rather than used.
    """
    if not text:
        return []

    direct = _decode(text.strip())
    if direct is not None:
        return [_unwrap(direct)]

    cleaned = _THINK.sub("", text)
    if "```" in cleaned:
        cleaned = _FENCE.sub(lambda match: f"\n{match.group(1)}\n", cleaned)

    direct = _decode(cleaned.strip())
    if direct is not None:
        return [_unwrap(direct)]

    return list(reversed(_scan(cleaned)))


def describe(text: str) -> str:
    """Structure-only diagnosis. Never includes the reply text."""
    stripped = text.strip()
    return (
        f"len={len(text)} first={stripped[:1]!r} last={stripped[-1:]!r} "
        f"think={bool(_THINK.search(text))} fence={'```' in text} "
        f"braces={text.count('{')}/{text.count('}')}"
    )
