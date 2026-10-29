"""Shared, minimal normalization before JSON parsing.

Fence stripping is preprocessing for both arms of the benchmark. It is not
a retry and it does not repair trailing commas, types, or wrong fields.
"""

from __future__ import annotations

import re

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


def strip_fences(raw: str) -> str:
    text = raw.strip()
    match = _FENCE.match(text)
    if match:
        return match.group(1).strip()
    return text
