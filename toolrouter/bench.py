"""Run the fixed task set with the router and without it."""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from toolrouter.dataset import Dataset, Task, load_dataset, repo_root
from toolrouter.metrics import DEFINITIONS, format_report, summarize, task_correct
from toolrouter.provider import Provider, provider_from_env, provider_label
from toolrouter.router import Outcome, ToolRouter
from toolrouter.tools import Catalog, Store


def _arm(
    dataset: Dataset,
    provider: Provider,
    *,
    use_schema: bool,
    max_retries: int,
) -> list[tuple[Task, Outcome]]:
    rows: list[tuple[Task, Outcome]] = []
    for task in dataset.tasks:
        catalog = Catalog(Store.from_fixtures(dataset.fixtures))
        router = ToolRouter(
            catalog,
            provider,
            max_retries=max_retries,
            use_schema=use_schema,
        )
        rows.append((task, router.run(task)))
    return rows


def pack_outcome(task: Task, outcome: Outcome) -> dict[str, Any]:
    payload = outcome.to_dict()
    payload["task_correct"] = task_correct(task, outcome)
    return payload


def run_task(
    dataset: Dataset,
    provider: Provider,
    task_id: str,
    *,
    arm: str,
    max_retries: int,
) -> dict[str, Any]:
    if arm not in {"with_router", "without_router"}:
        raise ValueError("arm must be with_router or without_router")
    task = next((item for item in dataset.tasks if item.id == task_id), None)
    if task is None:
        raise KeyError(task_id)
    use_schema = arm == "with_router"
    rows = _arm(
        Dataset(
            uri=dataset.uri,
            display=dataset.display,
            tasks=[task],
            recordings=dataset.recordings,
            fixtures=dataset.fixtures,
        ),
        provider,
        use_schema=use_schema,
        max_retries=max_retries if use_schema else 0,
    )
    return {
        "task": task.to_dict(),
        "arm": arm,
        "provider": provider.name,
        "outcome": pack_outcome(rows[0][0], rows[0][1]),
    }


def run_benchmark(
    dataset: Dataset | None = None,
    provider: Provider | None = None,
    *,
    max_retries: int | None = None,
    seed: int | None = None,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    dataset = dataset or load_dataset()
    if provider is None:
        provider = provider_from_env(dataset.recordings)
    if max_retries is None:
        max_retries = int(os.environ.get("HL_MAX_RETRIES", "2"))
    if seed is None:
        seed = int(os.environ.get("HL_SEED", "42"))
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")

    with_rows = _arm(dataset, provider, use_schema=True, max_retries=max_retries)
    without_rows = _arm(dataset, provider, use_schema=False, max_retries=0)
    catalog = Catalog(Store.from_fixtures(dataset.fixtures))
    report = {
        "provider": provider.name,
        "provider_label": provider_label(provider),
        "seed": seed,
        "max_retries": max_retries,
        "task_count": len(dataset.tasks),
        "recorded_at": recorded_at or date.today().isoformat(),
        "dataset": dataset.display,
        "definitions": dict(DEFINITIONS),
        "with_router": summarize(with_rows),
        "without_router": summarize(without_rows),
        "system_prompt": catalog.system_prompt(),
        "tasks": [
            {
                **task.to_dict(),
                "with_router": pack_outcome(task, with_outcome),
                "without_router": pack_outcome(task, without_outcome),
            }
            for (task, with_outcome), (_, without_outcome) in zip(with_rows, without_rows, strict=True)
        ],
    }
    return report


def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def split_site(report: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    scoreboard = {
        key: value
        for key, value in report.items()
        if key not in {"tasks", "system_prompt"}
    }
    traces = {
        "provider": report["provider"],
        "provider_label": report["provider_label"],
        "recorded_at": report["recorded_at"],
        "seed": report["seed"],
        "max_retries": report["max_retries"],
        "dataset": report["dataset"],
        "system_prompt": report["system_prompt"],
        "tasks": report["tasks"],
    }
    return scoreboard, traces


def results_dir() -> Path:
    override = os.environ.get("HL_RESULTS_DIR")
    if override:
        return Path(override)
    return repo_root() / "results" / "runs"


def site_data_dir() -> Path:
    override = os.environ.get("HL_SITE_DATA")
    if override:
        return Path(override)
    return repo_root() / "site" / "data"


def run_filename(provider_name: str, seed: int) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", provider_name).strip("-")
    return f"{safe}-seed{seed}.json"


def write_results(report: dict[str, Any], directory: Path | None = None) -> Path:
    directory = directory or results_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / run_filename(report["provider"], int(report["seed"]))
    path.write_text(dumps(report), encoding="utf-8")
    return path


def write_site(report: dict[str, Any], directory: Path | None = None) -> tuple[Path, Path]:
    directory = directory or site_data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    scoreboard, traces = split_site(report)
    scoreboard_path = directory / "scoreboard.json"
    traces_path = directory / "traces.json"
    scoreboard_path.write_text(dumps(scoreboard), encoding="utf-8")
    traces_path.write_text(dumps(traces), encoding="utf-8")
    return scoreboard_path, traces_path
