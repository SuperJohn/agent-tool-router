"""Router metrics.

Definitions, also stored on every recorded run:

- first-try valid: attempt 0 parsed and passed Pydantic
- valid after retry: some attempt inside the budget passed, including first-try
- mean retries: average of (attempts - 1) over every task
- unrecoverable: no attempt validated, so the tool was not executed
- task correct: validated and the tool plus arguments match the task

Task correct is not what the retry loop optimizes. A schema-valid wrong day
counts as valid and incorrect.
"""

from __future__ import annotations

from typing import Any

from toolrouter.dataset import Task
from toolrouter.router import Outcome

DEFINITIONS = {
    "first_try_valid": "Passed JSON parse and Pydantic on attempt 0.",
    "valid_after_retry": "Passed within the retry budget, including first-try successes.",
    "mean_retries": "Average of (attempts - 1) over every task. A first-try success is 0.",
    "unrecoverable": "Never validated. The tool was not executed.",
    "task_correct": "Validated, and the tool plus arguments match the task. Not what the retry loop targets.",
}


def _pct(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(100.0 * count / total, 1)


def _display(count: int, total: int) -> str:
    return f"{_pct(count, total):.1f}% ({count}/{total})"


def arguments_match(actual: dict[str, Any] | None, expect: dict[str, Any]) -> bool:
    if actual is None:
        return False
    cleaned = {
        key: value
        for key, value in actual.items()
        if value is not None or key in expect
    }
    return cleaned == expect


def task_correct(task: Task, outcome: Outcome) -> bool:
    if not outcome.validated:
        return False
    if outcome.tool != task.expect_tool:
        return False
    return arguments_match(outcome.arguments, task.expect_args)


def summarize(rows: list[tuple[Task, Outcome]]) -> dict[str, Any]:
    total = len(rows)
    first = sum(1 for _, outcome in rows if outcome.attempts and outcome.attempts[0].valid)
    valid = sum(1 for _, outcome in rows if outcome.validated)
    retry_total = sum(outcome.retries for _, outcome in rows)
    correct = sum(1 for task, outcome in rows if task_correct(task, outcome))
    unrecoverable = total - valid
    mean = round(retry_total / total, 2) if total else 0.0
    return {
        "tasks": total,
        "first_try_valid": first,
        "first_try_valid_pct": _pct(first, total),
        "first_try_valid_display": _display(first, total),
        "valid_after_retry": valid,
        "valid_after_retry_pct": _pct(valid, total),
        "valid_after_retry_display": _display(valid, total),
        "retry_total": retry_total,
        "mean_retries": mean,
        "mean_retries_display": f"{mean:.2f}",
        "unrecoverable": unrecoverable,
        "unrecoverable_pct": _pct(unrecoverable, total),
        "unrecoverable_display": _display(unrecoverable, total),
        "task_correct": correct,
        "task_correct_pct": _pct(correct, total),
        "task_correct_display": _display(correct, total),
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"provider: {report['provider_label']}",
        (
            f"tasks: {report['task_count']}  max_retries: {report['max_retries']}  "
            f"seed: {report['seed']}  recorded_at: {report['recorded_at']}  "
            f"dataset: {report['dataset']}"
        ),
        "",
        f"{'arm':<16} {'first-try valid':<18} {'valid after retry':<20} "
        f"{'mean retries':<14} {'unrecoverable':<18} {'task correct':<18}",
    ]
    for arm, label in (("with_router", "with_router"), ("without_router", "without_router")):
        metrics = report[arm]
        lines.append(
            f"{label:<16} {metrics['first_try_valid_display']:<18} "
            f"{metrics['valid_after_retry_display']:<20} "
            f"{metrics['mean_retries_display']:<14} "
            f"{metrics['unrecoverable_display']:<18} "
            f"{metrics['task_correct_display']:<18}"
        )
    return "\n".join(lines)
