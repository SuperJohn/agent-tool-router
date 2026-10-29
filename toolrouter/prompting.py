"""Prompt text shared by the router and the mock replay provider."""

from __future__ import annotations

import json
from typing import Any

# The mock provider counts retries by this marker. Keep it stable.
VALIDATION_MARKER = "Validation error:\n"


def retry_prompt(raw: str, error_message: str) -> str:
    return (
        "Your previous tool call failed validation and was not executed.\n\n"
        f"{VALIDATION_MARKER}"
        f"{error_message}\n\n"
        "Raw output:\n"
        f"{raw}\n\n"
        'Return one JSON object with keys "tool" and "arguments". '
        "Change the fields named in the error. Do not add fields."
    )


def feedback_count(messages: list[dict[str, Any]]) -> int:
    return sum(
        1
        for message in messages
        if message.get("role") == "user" and VALIDATION_MARKER in str(message.get("content", ""))
    )


def system_prompt(specs: list[dict[str, Any]]) -> str:
    """``specs`` entries: name, description, constraints, reduced schema."""
    lines = [
        'Return one JSON object with keys "tool" and "arguments".',
        "Do not wrap it in markdown. Use only a listed tool.",
        "A grammar may enforce types, enums, required keys, and bounds.",
        "Patterns and cross-field rules are checked after decoding.",
        "",
        "Tools:",
    ]
    for spec in specs:
        lines.append(f"- {spec['name']}: {spec['description']} {spec['constraints']}")
        lines.append(
            "  arguments: "
            + json.dumps(spec["reduced"], separators=(",", ":"), ensure_ascii=True)
        )
    return "\n".join(lines)
