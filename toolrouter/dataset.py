"""Load the synthetic dataset named by ``HL_DATASET_URI``."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "toolrouter").is_dir():
            return candidate
    return here.parents[1]


class TaskModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    suite: str
    title: str
    failure_class: str
    blurb: str
    user: str
    expect_tool: str
    expect_args: dict[str, Any]


class RecordingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw: list[str] = Field(min_length=1)
    constrained: str = Field(min_length=1)
    retry: list[str] = Field(min_length=1)


class FixtureEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    title: str
    start: str
    end: str
    location: str | None = None


class FixtureTicket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_id: str
    project: str
    title: str
    status: str


class FixtureContact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    role: str
    desk: str


class FixtureDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc_id: str
    title: str
    summary: str


class FixturesModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calendar: list[FixtureEvent]
    tickets: list[FixtureTicket]
    contacts: list[FixtureContact]
    docs: list[FixtureDoc]


@dataclass(frozen=True)
class Task:
    id: str
    suite: str
    title: str
    failure_class: str
    blurb: str
    user: str
    expect_tool: str
    expect_args: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "suite": self.suite,
            "title": self.title,
            "failure_class": self.failure_class,
            "blurb": self.blurb,
            "user": self.user,
            "expect_tool": self.expect_tool,
            "expect_args": self.expect_args,
        }


@dataclass
class Dataset:
    uri: str
    display: str
    tasks: list[Task]
    recordings: dict[str, dict[str, Any]]
    fixtures: dict[str, Any]


def resolve_dataset_path(uri: str | None = None) -> tuple[Path, str]:
    raw = uri if uri is not None else os.environ.get("HL_DATASET_URI")
    if raw is None or raw.strip() == "":
        path = repo_root() / "demo" / "data"
        return path, "demo/data"
    raw = raw.strip()
    if raw.startswith(("http://", "https://")):
        raise ValueError(
            "HL_DATASET_URI does not accept http(s). Use a local directory or a file:// URI."
        )
    if raw.startswith("file://"):
        parsed = urlparse(raw)
        path = Path(unquote(parsed.path))
        return path, _display(path)
    path = Path(raw)
    if not path.is_absolute():
        from_cwd = Path.cwd() / path
        path = from_cwd if from_cwd.exists() else repo_root() / path
    return path, _display(path)


def _display(path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root()).as_posix()
    except ValueError:
        return "custom"


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"missing dataset file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_dataset(uri: str | None = None) -> Dataset:
    path, display = resolve_dataset_path(uri)
    if path.is_dir():
        tasks_raw = _read_json(path / "tasks.json")
        recordings_raw = _read_json(path / "recordings.json")
        fixtures_raw = _read_json(path / "fixtures.json")
        shown = str(path)
    elif path.is_file():
        bundle = _read_json(path)
        if not isinstance(bundle, dict):
            raise ValueError("dataset file must be a JSON object")
        tasks_raw = bundle["tasks"]
        recordings_raw = bundle["recordings"]
        fixtures_raw = bundle["fixtures"]
        shown = str(path)
    else:
        raise FileNotFoundError(f"dataset not found: {path}")

    tasks = [Task(**TaskModel.model_validate(item).model_dump()) for item in tasks_raw]
    if not tasks:
        raise ValueError("dataset has no tasks")
    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate task id")

    if not isinstance(recordings_raw, dict):
        raise ValueError("recordings must be an object keyed by task id")
    recordings: dict[str, dict[str, Any]] = {}
    for key, value in recordings_raw.items():
        recordings[key] = RecordingModel.model_validate(value).model_dump()
    missing = [task.id for task in tasks if task.id not in recordings]
    extra = sorted(set(recordings) - set(ids))
    if missing or extra:
        raise ValueError(f"recordings do not match tasks (missing={missing}, extra={extra})")

    fixtures = FixturesModel.model_validate(fixtures_raw).model_dump()
    return Dataset(
        uri=shown,
        display=display,
        tasks=tasks,
        recordings=recordings,
        fixtures=fixtures,
    )
