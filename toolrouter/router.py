"""Validate a tool call, retry with the error trace, or fail safe.

``use_schema=False`` and ``max_retries=0`` is the baseline arm: one sample,
no grammar, no retry. The parser and the Pydantic models are the same.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from toolrouter.dataset import Task
from toolrouter.prompting import retry_prompt
from toolrouter.provider import Provider, ProviderError
from toolrouter.tools import Catalog


@dataclass
class Attempt:
    index: int
    raw: str
    schema_kind: str
    narrowed_to: str | None
    valid: bool
    parsed: dict[str, Any] | None
    error: dict[str, Any] | None
    retry_prompt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "raw": self.raw,
            "schema_kind": self.schema_kind,
            "narrowed_to": self.narrowed_to,
            "valid": self.valid,
            "parsed": self.parsed,
            "error": self.error,
            "retry_prompt": self.retry_prompt,
        }


@dataclass
class Outcome:
    validated: bool
    retries: int
    tool: str | None
    arguments: dict[str, Any] | None
    execution: dict[str, Any] | None
    failure: dict[str, Any] | None
    attempts: list[Attempt]

    def to_dict(self) -> dict[str, Any]:
        return {
            "validated": self.validated,
            "retries": self.retries,
            "tool": self.tool,
            "arguments": self.arguments,
            "execution": self.execution,
            "failure": self.failure,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }


class ToolRouter:
    def __init__(
        self,
        catalog: Catalog,
        provider: Provider,
        *,
        max_retries: int = 2,
        use_schema: bool = True,
    ):
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self.catalog = catalog
        self.provider = provider
        self.max_retries = max_retries
        self.use_schema = use_schema

    def run(self, task: Task) -> Outcome:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.catalog.system_prompt()},
            {"role": "user", "content": task.user},
        ]
        attempts: list[Attempt] = []
        narrowed: str | None = None
        full_schema = self.catalog.grammar_schema() if self.use_schema else None

        for index in range(self.max_retries + 1):
            schema: dict[str, Any] | None = None
            schema_kind = "none"
            narrowed_to: str | None = None
            if self.use_schema:
                if narrowed is not None:
                    schema = self.catalog.narrowed_schema(narrowed)
                    schema_kind = "narrowed"
                    narrowed_to = narrowed
                else:
                    schema = full_schema
                    schema_kind = "catalog"

            try:
                raw = self.provider.complete(messages=messages, schema=schema, task_id=task.id)
            except ProviderError as exc:
                message = str(exc)
                attempts.append(
                    Attempt(
                        index=index,
                        raw="",
                        schema_kind=schema_kind,
                        narrowed_to=narrowed_to,
                        valid=False,
                        parsed=None,
                        error={
                            "message": message,
                            "details": [
                                {
                                    "loc": [],
                                    "msg": message,
                                    "type": "provider_error",
                                    "input": None,
                                }
                            ],
                        },
                    )
                )
                return self._failure(attempts, code="provider_error")

            parsed, model, error = self.catalog.validate_raw(raw)
            attempt = Attempt(
                index=index,
                raw=raw,
                schema_kind=schema_kind,
                narrowed_to=narrowed_to,
                valid=error is None,
                parsed=parsed,
                error=error,
            )
            attempts.append(attempt)
            if error is None and model is not None and parsed is not None:
                execution = self.catalog.execute(parsed["tool"], model)
                return Outcome(
                    validated=True,
                    retries=len(attempts) - 1,
                    tool=parsed["tool"],
                    arguments=parsed["arguments"],
                    execution=execution,
                    failure=None,
                    attempts=attempts,
                )

            if isinstance(parsed, dict) and parsed.get("tool") in self.catalog.by_name:
                narrowed = str(parsed["tool"])

            if index < self.max_retries:
                prompt = retry_prompt(raw, error["message"] if error else "validation failed")
                attempt.retry_prompt = prompt
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": prompt})

        return self._failure(attempts, code="unrecoverable")

    def _failure(self, attempts: list[Attempt], *, code: str) -> Outcome:
        last = attempts[-1] if attempts else None
        tool = None
        if last and isinstance(last.parsed, dict) and isinstance(last.parsed.get("tool"), str):
            tool = last.parsed["tool"]
        errors = [attempt.error["message"] for attempt in attempts if attempt.error]
        details: list[dict[str, Any]] = []
        if last and last.error:
            details = list(last.error.get("details") or [])
        failure = {
            "ok": False,
            "code": code,
            "attempts": len(attempts),
            "retries": max(0, len(attempts) - 1),
            "tool": tool,
            "errors": errors,
            "details": details,
            "last_raw": last.raw if last else "",
        }
        return Outcome(
            validated=False,
            retries=max(0, len(attempts) - 1),
            tool=tool,
            arguments=None,
            execution=None,
            failure=failure,
            attempts=attempts,
        )
