"""Synthetic calendar, tracker, and lookup tools.

Every tool is a Pydantic v2 model. ``strict=True`` and ``extra='forbid'``
are the contract: the string ``"90"`` is not an integer, and a field the
schema does not name is rejected. Cross-field rules and id patterns live
here. The reduced grammar schema does not include them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from toolrouter.parse import strip_fences
from toolrouter.prompting import system_prompt
from toolrouter.schema import catalog_schema, reduce_schema, tool_call_schema

_ISO_DATETIME = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$"
_ISO_DAY = r"^\d{4}-\d{2}-\d{2}$"
_EVENT_ID = r"^evt_[0-9]{3}$"
_TICKET_ID = r"^tkt_[0-9]{3}$"
_DOC_ID = r"^doc_[a-z0-9]+$"


class CreateEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=1, max_length=80)
    start: str = Field(pattern=_ISO_DATETIME)
    end: str = Field(pattern=_ISO_DATETIME)
    location: str | None = Field(default=None, max_length=40)

    @field_validator("end")
    @classmethod
    def end_after_start(cls, value: str, info: Any) -> str:
        start = info.data.get("start")
        # Zero-padded ISO-8601 without a timezone sorts lexicographically.
        # The pattern rejects offsets so this comparison stays well-defined.
        if (
            isinstance(start, str)
            and isinstance(value, str)
            and re.fullmatch(_ISO_DATETIME, start)
            and re.fullmatch(_ISO_DATETIME, value)
            and value <= start
        ):
            raise ValueError("end must be after start")
        return value


class ListEvents(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    day: str = Field(pattern=_ISO_DAY)


class CancelEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    event_id: str = Field(pattern=_EVENT_ID)


class LogTime(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project: Literal["atlas", "beacon", "cedar"]
    minutes: int = Field(ge=1, le=480)
    note: str = Field(min_length=1, max_length=160)


class SetStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ticket_id: str = Field(pattern=_TICKET_ID)
    status: Literal["open", "in_progress", "blocked", "done"]


class LookupContact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=60)


class LookupDoc(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    doc_id: str = Field(pattern=_DOC_ID)


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tool: str
    arguments: dict[str, Any]


@dataclass
class Store:
    calendar: list[dict[str, Any]]
    tickets: list[dict[str, Any]]
    contacts: list[dict[str, Any]]
    docs: list[dict[str, Any]]
    logs: list[dict[str, Any]]
    executions: int = 0

    @classmethod
    def from_fixtures(cls, fixtures: dict[str, Any]) -> Store:
        return cls(
            calendar=[dict(item) for item in fixtures["calendar"]],
            tickets=[dict(item) for item in fixtures["tickets"]],
            contacts=[dict(item) for item in fixtures["contacts"]],
            docs=[dict(item) for item in fixtures["docs"]],
            logs=[],
            executions=0,
        )

    def copy(self) -> Store:
        return Store.from_fixtures(
            {
                "calendar": self.calendar,
                "tickets": self.tickets,
                "contacts": self.contacts,
                "docs": self.docs,
            }
        )

    def next_event_id(self) -> str:
        nums: list[int] = []
        for event in self.calendar:
            match = re.fullmatch(r"evt_(\d{3})", str(event.get("event_id", "")))
            if match:
                nums.append(int(match.group(1)))
        return f"evt_{(max(nums) if nums else 0) + 1:03d}"


def _create_event(args: CreateEvent, store: Store) -> dict[str, Any]:
    event = {
        "event_id": store.next_event_id(),
        "title": args.title,
        "start": args.start,
        "end": args.end,
        "location": args.location,
    }
    store.calendar.append(event)
    return {"ok": True, "event": event}


def _list_events(args: ListEvents, store: Store) -> dict[str, Any]:
    events = [dict(event) for event in store.calendar if str(event["start"]).startswith(args.day)]
    return {"ok": True, "day": args.day, "events": events}


def _cancel_event(args: CancelEvent, store: Store) -> dict[str, Any]:
    for index, event in enumerate(store.calendar):
        if event["event_id"] == args.event_id:
            removed = store.calendar.pop(index)
            return {"ok": True, "event": dict(removed)}
    return {"ok": False, "error": "unknown event_id", "event_id": args.event_id}


def _log_time(args: LogTime, store: Store) -> dict[str, Any]:
    entry = {"project": args.project, "minutes": args.minutes, "note": args.note}
    store.logs.append(entry)
    return {"ok": True, "entry": entry}


def _set_status(args: SetStatus, store: Store) -> dict[str, Any]:
    for ticket in store.tickets:
        if ticket["ticket_id"] == args.ticket_id:
            ticket["status"] = args.status
            return {"ok": True, "ticket": dict(ticket)}
    return {"ok": False, "error": "unknown ticket_id", "ticket_id": args.ticket_id}


def _lookup_contact(args: LookupContact, store: Store) -> dict[str, Any]:
    for contact in store.contacts:
        if contact["name"] == args.name:
            return {"ok": True, "found": True, "contact": dict(contact)}
    return {"ok": True, "found": False, "contact": None}


def _lookup_doc(args: LookupDoc, store: Store) -> dict[str, Any]:
    for doc in store.docs:
        if doc["doc_id"] == args.doc_id:
            return {"ok": True, "found": True, "doc": dict(doc)}
    return {"ok": True, "found": False, "doc": None}


Executor = Callable[[Any, Store], dict[str, Any]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    constraints: str
    args_model: type[BaseModel]
    execute: Executor

    def reduced_arguments(self) -> dict[str, Any]:
        return reduce_schema(self.args_model.model_json_schema())


TOOLS: tuple[Tool, ...] = (
    Tool(
        "create_event",
        "Add one calendar event.",
        "start and end are YYYY-MM-DDTHH:MM:SS with no timezone. end must be after start.",
        CreateEvent,
        _create_event,
    ),
    Tool(
        "list_events",
        "List calendar events on one day.",
        "day is YYYY-MM-DD.",
        ListEvents,
        _list_events,
    ),
    Tool(
        "cancel_event",
        "Cancel one calendar event.",
        "event_id matches evt_### (lowercase, underscore, three digits).",
        CancelEvent,
        _cancel_event,
    ),
    Tool(
        "log_time",
        "Log minutes on a project.",
        "project is atlas, beacon, or cedar. minutes is an integer from 1 to 480.",
        LogTime,
        _log_time,
    ),
    Tool(
        "set_status",
        "Set a ticket status.",
        "ticket_id matches tkt_###. status is open, in_progress, blocked, or done.",
        SetStatus,
        _set_status,
    ),
    Tool(
        "lookup_contact",
        "Look up a contact by exact name.",
        "name is the full name, matched exactly.",
        LookupContact,
        _lookup_contact,
    ),
    Tool(
        "lookup_doc",
        "Look up a document by id.",
        "doc_id matches doc_ plus lowercase letters or digits.",
        LookupDoc,
        _lookup_doc,
    ),
)


def error_payload(exc: ValidationError, prefix: tuple[str, ...] = ()) -> dict[str, Any]:
    details = []
    for err in exc.errors():
        loc = [*prefix, *[str(part) for part in err["loc"]]]
        raw_input = err.get("input")
        try:
            json.dumps(raw_input)
            shown: Any = raw_input
        except TypeError:
            shown = repr(raw_input)
        details.append(
            {
                "loc": loc,
                "msg": err["msg"],
                "type": err["type"],
                "input": shown,
            }
        )
    return {"message": str(exc), "details": details}


class Catalog:
    def __init__(self, store: Store):
        self.store = store
        self.tools = TOOLS
        self.by_name = {tool.name: tool for tool in TOOLS}

    def grammar_schema(self) -> dict[str, Any]:
        branches = [tool_call_schema(tool.name, tool.reduced_arguments()) for tool in self.tools]
        return catalog_schema(branches)

    def narrowed_schema(self, tool_name: str) -> dict[str, Any]:
        tool = self.by_name[tool_name]
        return tool_call_schema(tool.name, tool.reduced_arguments())

    def system_prompt(self) -> str:
        specs = [
            {
                "name": tool.name,
                "description": tool.description,
                "constraints": tool.constraints,
                "reduced": tool.reduced_arguments(),
            }
            for tool in self.tools
        ]
        return system_prompt(specs)

    def validate_raw(
        self, raw: str
    ) -> tuple[dict[str, Any] | None, BaseModel | None, dict[str, Any] | None]:
        text = strip_fences(raw)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            message = f"JSON decode error: {exc.msg} (line {exc.lineno}, column {exc.colno})"
            return (
                None,
                None,
                {
                    "message": message,
                    "details": [
                        {
                            "loc": [],
                            "msg": message,
                            "type": "json_invalid",
                            "input": text[:500],
                        }
                    ],
                },
            )

        parsed = data if isinstance(data, dict) else None
        try:
            envelope = Envelope.model_validate(data)
        except ValidationError as exc:
            return parsed, None, error_payload(exc)

        envelope_dict = {"tool": envelope.tool, "arguments": envelope.arguments}
        tool = self.by_name.get(envelope.tool)
        if tool is None:
            known = ", ".join(self.by_name)
            return (
                envelope_dict,
                None,
                {
                    "message": f"Unknown tool {envelope.tool!r}. Known tools: {known}.",
                    "details": [
                        {
                            "loc": ["tool"],
                            "msg": f"unknown tool {envelope.tool!r}",
                            "type": "unknown_tool",
                            "input": envelope.tool,
                        }
                    ],
                },
            )
        try:
            model = tool.args_model.model_validate(envelope.arguments)
        except ValidationError as exc:
            return envelope_dict, None, error_payload(exc, prefix=("arguments",))
        return {"tool": tool.name, "arguments": model.model_dump()}, model, None

    def execute(self, tool_name: str, model: BaseModel) -> dict[str, Any]:
        self.store.executions += 1
        return self.by_name[tool_name].execute(model, self.store)
