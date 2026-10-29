"""Model providers.

The default provider replays recorded strings. It does not sample. When the
router passes a JSON schema, the replay returns the ``constrained`` string;
after a validation-error prompt, it returns the next ``retry`` string. The
Ollama provider is optional and is used only when ``HL_PROVIDER=ollama``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Protocol

from toolrouter.prompting import feedback_count


class ProviderError(RuntimeError):
    pass


class Provider(Protocol):
    name: str

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        schema: dict[str, Any] | None,
        task_id: str,
    ) -> str: ...


class MockProvider:
    """Deterministic replay of scripted small-model outputs."""

    name = "mock"

    def __init__(self, recordings: dict[str, dict[str, Any]]):
        self.recordings = recordings
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        schema: dict[str, Any] | None,
        task_id: str,
    ) -> str:
        self.calls.append({"task_id": task_id, "schema": schema, "messages": messages})
        try:
            recording = self.recordings[task_id]
        except KeyError as exc:
            raise KeyError(f"no recording for {task_id}") from exc
        seen = feedback_count(messages)
        if schema is None:
            sequence = recording["raw"]
            return sequence[min(seen, len(sequence) - 1)]
        if seen == 0:
            return recording["constrained"]
        sequence = recording["retry"]
        return sequence[min(seen - 1, len(sequence) - 1)]


class OllamaProvider:
    """Ollama ``/api/chat``. ``format`` is the JSON schema when the router is on."""

    def __init__(self, model: str, host: str, seed: int, timeout: float = 120.0):
        self.model = model
        self.name = f"ollama:{model}"
        self.host = host.rstrip("/")
        self.seed = seed
        self.timeout = timeout

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        schema: dict[str, Any] | None,
        task_id: str,
    ) -> str:
        del task_id
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0, "seed": self.seed},
        }
        if schema is not None:
            payload["format"] = schema
        request = urllib.request.Request(
            self.host + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Ollama returned non-JSON: {exc}") from exc
        try:
            content = body["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise ProviderError("Ollama response missing message.content") from exc
        if not isinstance(content, str) or content == "":
            raise ProviderError("Ollama response missing message.content")
        return content


def provider_from_env(recordings: dict[str, dict[str, Any]]) -> Provider:
    kind = os.environ.get("HL_PROVIDER", "mock").strip().lower()
    if kind == "mock":
        return MockProvider(recordings)
    if kind == "ollama":
        model = os.environ.get("OLLAMA_MODEL", "").strip()
        if not model:
            raise SystemExit("OLLAMA_MODEL is required when HL_PROVIDER=ollama")
        host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        seed = int(os.environ.get("HL_SEED", "42"))
        return OllamaProvider(model=model, host=host, seed=seed)
    raise SystemExit(f"Unknown HL_PROVIDER: {kind}")


def provider_label(provider: Provider) -> str:
    if provider.name == "mock":
        return "mock (scripted small-model errors; not a live model sample)"
    return provider.name
