"""JSON Schema reduction for grammar-constrained decoding.

Pydantic is the source of truth for a tool call. The grammar engines behind
Ollama's ``format`` field reliably express a smaller subset: types, enums,
required keys, string and numeric bounds, and ``additionalProperties``.
Regex patterns, string formats, and cross-field checks stay on the Pydantic
model. The retry loop feeds those validation errors back to the model.
"""

from __future__ import annotations

from typing import Any

_BOUND_KEYS = (
    "enum",
    "const",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
)


def reduce_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a grammar-oriented copy of a Pydantic JSON schema.

    Drops ``pattern``, ``format``, titles, defaults, and descriptions.
    Collapses ``anyOf: [string, null]`` to ``string`` so optional fields
    stay optional without a null branch the grammar may reject.
    """
    if not isinstance(schema, dict):
        raise TypeError("schema must be an object")

    if "$ref" in schema:
        raise ValueError(f"unsupported $ref in tool schema: {schema['$ref']}")

    union_key = "anyOf" if "anyOf" in schema else "oneOf" if "oneOf" in schema else None
    if union_key is not None:
        branches = schema[union_key]
        non_null = [
            branch
            for branch in branches
            if not (isinstance(branch, dict) and branch.get("type") == "null")
        ]
        if len(non_null) == 1 and len(non_null) != len(branches):
            return reduce_schema(non_null[0])
        return {union_key: [reduce_schema(branch) for branch in branches]}

    out: dict[str, Any] = {}
    if "type" in schema:
        out["type"] = schema["type"]
    for key in _BOUND_KEYS:
        if key in schema:
            out[key] = schema[key]
    if "properties" in schema:
        out["type"] = out.get("type", "object")
        out["properties"] = {
            name: reduce_schema(child) for name, child in schema["properties"].items()
        }
        out["additionalProperties"] = False
        if "required" in schema:
            out["required"] = list(schema["required"])
    elif "items" in schema and isinstance(schema["items"], dict):
        out["items"] = reduce_schema(schema["items"])
    return out


def tool_call_schema(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """One grammar branch: a single tool name plus its reduced argument schema."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["tool", "arguments"],
        "properties": {
            "tool": {"type": "string", "enum": [tool_name]},
            "arguments": arguments,
        },
    }


def catalog_schema(branches: list[dict[str, Any]]) -> dict[str, Any]:
    if not branches:
        raise ValueError("catalog schema needs at least one tool")
    if len(branches) == 1:
        return branches[0]
    return {"anyOf": branches}
