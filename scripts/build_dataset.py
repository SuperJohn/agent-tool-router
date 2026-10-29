"""Write the synthetic dataset under demo/data/.

The JSON files are what the router loads. This module is the readable source.
Nothing here is a real person, account, or message.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo" / "data"


def pretty(tool: str, arguments: dict) -> str:
    return json.dumps({"tool": tool, "arguments": arguments}, indent=2)


def fenced(tool: str, arguments: dict) -> str:
    return "```json\n" + pretty(tool, arguments) + "\n```"


TRAILING_COMMA = """{
  "tool": "create_event",
  "arguments": {
    "title": "Vendor hold",
    "start": "2026-11-04T10:00:00",
    "end": "2026-11-04T10:30:00",
  }
}"""


def build() -> dict:
    tasks: list[dict] = []
    recordings: dict[str, dict] = {}

    def add(
        *,
        id: str,
        suite: str,
        title: str,
        failure_class: str,
        blurb: str,
        user: str,
        expect_tool: str,
        expect_args: dict,
        raw: str,
        constrained: str,
        retry: list[str],
    ) -> None:
        tasks.append(
            {
                "id": id,
                "suite": suite,
                "title": title,
                "failure_class": failure_class,
                "blurb": blurb,
                "user": user,
                "expect_tool": expect_tool,
                "expect_args": expect_args,
            }
        )
        recordings[id] = {"raw": [raw], "constrained": constrained, "retry": retry}

    review = {
        "title": "Schema review",
        "start": "2026-11-03T15:00:00",
        "end": "2026-11-03T15:45:00",
        "location": "Lab Room B",
    }
    review_call = pretty("create_event", review)
    add(
        id="cal-01",
        suite="calendar",
        title="Schema review",
        failure_class="clean",
        blurb="Well-formed call. Both arms accept it on the first try.",
        user='Book a schema review titled "Schema review" on 2026-11-03 from 15:00 to 15:45 in Lab Room B.',
        expect_tool="create_event",
        expect_args=review,
        raw=review_call,
        constrained=review_call,
        retry=[review_call],
    )

    day = {"day": "2026-11-03"}
    listed = pretty("list_events", day)
    add(
        id="cal-02",
        suite="calendar",
        title="Fenced list_events",
        failure_class="fenced_json",
        blurb="Markdown fence around valid JSON. Fence stripping is shared, so the baseline also passes.",
        user="What is on the calendar on 2026-11-03?",
        expect_tool="list_events",
        expect_args=day,
        raw=fenced("list_events", day),
        constrained=listed,
        retry=[listed],
    )

    hold = {
        "title": "Vendor hold",
        "start": "2026-11-04T10:00:00",
        "end": "2026-11-04T10:30:00",
    }
    hold_call = pretty("create_event", hold)
    add(
        id="cal-03",
        suite="calendar",
        title="Trailing comma",
        failure_class="trailing_comma",
        blurb="Trailing comma. The baseline cannot parse it. The schema-constrained string is valid JSON.",
        user='Add a vendor hold titled "Vendor hold" on 2026-11-04 from 10:00 to 10:30. No location.',
        expect_tool="create_event",
        expect_args=hold,
        raw=TRAILING_COMMA,
        constrained=hold_call,
        retry=[hold_call],
    )

    grammar = {
        "title": "Grammar pass",
        "start": "2026-11-05T13:00:00",
        "end": "2026-11-05T14:00:00",
        "location": "Lab Room B",
    }
    grammar_bad = {
        "title": "Grammar pass",
        "start": "2026-11-05T14:00:00",
        "end": "2026-11-05T13:00:00",
        "location": "Lab Room B",
    }
    grammar_fixed = pretty("create_event", grammar)
    add(
        id="cal-04",
        suite="calendar",
        title="End before start",
        failure_class="end_before_start",
        blurb="end is before start. The grammar allows both timestamps. Pydantic rejects them, and the retry swaps them.",
        user='Schedule "Grammar pass" on 2026-11-05 from 13:00 to 14:00 in Lab Room B.',
        expect_tool="create_event",
        expect_args=grammar,
        raw=pretty("create_event", grammar_bad),
        constrained=pretty("create_event", grammar_bad),
        retry=[grammar_fixed],
    )

    cancel = {"event_id": "evt_002"}
    add(
        id="cal-05",
        suite="calendar",
        title="Event id never matches",
        failure_class="id_pattern_stuck",
        blurb="event_id never matches evt_###. Each retry changes the spelling and still fails the pattern.",
        user="Cancel event evt_002.",
        expect_tool="cancel_event",
        expect_args=cancel,
        raw=pretty("cancel_event", {"event_id": "EVT-002"}),
        constrained=pretty("cancel_event", {"event_id": "EVT-002"}),
        retry=[
            pretty("cancel_event", {"event_id": "evt-002"}),
            pretty("cancel_event", {"event_id": "EVT_002"}),
        ],
    )

    hours = {
        "title": "Office hours",
        "start": "2026-11-06T16:00:00",
        "end": "2026-11-06T16:30:00",
        "location": "Lab Room B",
    }
    add(
        id="cal-06",
        suite="calendar",
        title="Datetime, two retries",
        failure_class="natural_language_datetime",
        blurb="Prose on the baseline. The constrained call uses natural language, the first retry drops the T, and the second retry is ISO-8601.",
        user='Book "Office hours" on 2026-11-06 from 16:00 to 16:30 in Lab Room B.',
        expect_tool="create_event",
        expect_args=hours,
        raw="I'll book office hours tomorrow afternoon.",
        constrained=pretty(
            "create_event",
            {
                "title": "Office hours",
                "start": "Nov 6 4pm",
                "end": "Nov 6 4:30pm",
                "location": "Lab Room B",
            },
        ),
        retry=[
            pretty(
                "create_event",
                {
                    "title": "Office hours",
                    "start": "2026-11-06 16:00",
                    "end": "2026-11-06 16:30",
                    "location": "Lab Room B",
                },
            ),
            pretty("create_event", hours),
        ],
    )

    budget = {
        "title": "Budget sync",
        "start": "2026-11-06T09:00:00",
        "end": "2026-11-06T09:20:00",
        "location": "Lab Room B",
    }
    add(
        id="cal-07",
        suite="calendar",
        title="Extra attendees field",
        failure_class="extra_field",
        blurb="An extra attendees field. additionalProperties is false, so the constrained call omits it.",
        user='Book "Budget sync" on 2026-11-06 from 09:00 to 09:20 in Lab Room B.',
        expect_tool="create_event",
        expect_args=budget,
        raw=pretty("create_event", {**budget, "attendees": ["Avery Chen"]}),
        constrained=pretty("create_event", budget),
        retry=[pretty("create_event", budget)],
    )

    retro = {
        "title": "Retro",
        "start": "2026-11-07T15:00:00",
        "end": "2026-11-07T16:00:00",
        "location": "Lab Room B",
    }
    add(
        id="cal-08",
        suite="calendar",
        title="End order never fixed",
        failure_class="end_order_stuck",
        blurb="Three schema-valid calls, each with end earlier than or equal to start. The retry budget runs out and the tool is not executed.",
        user='Schedule "Retro" on 2026-11-07 from 15:00 to 16:00 in Lab Room B.',
        expect_tool="create_event",
        expect_args=retro,
        raw=pretty(
            "create_event",
            {
                "title": "Retro",
                "start": "2026-11-07T16:00:00",
                "end": "2026-11-07T15:00:00",
                "location": "Lab Room B",
            },
        ),
        constrained=pretty(
            "create_event",
            {
                "title": "Retro",
                "start": "2026-11-07T16:00:00",
                "end": "2026-11-07T15:00:00",
                "location": "Lab Room B",
            },
        ),
        retry=[
            pretty(
                "create_event",
                {
                    "title": "Retro",
                    "start": "2026-11-07T15:00:00",
                    "end": "2026-11-07T15:00:00",
                    "location": "Lab Room B",
                },
            ),
            pretty(
                "create_event",
                {
                    "title": "Retro",
                    "start": "2026-11-07T16:00:00",
                    "end": "2026-11-07T15:30:00",
                    "location": "Lab Room B",
                },
            ),
        ],
    )

    walk = {
        "title": "Lab walkthrough",
        "start": "2026-11-12T10:00:00",
        "end": "2026-11-12T11:00:00",
        "location": "Lab Room B",
    }
    wrong_day = pretty(
        "create_event",
        {
            "title": "Lab walkthrough",
            "start": "2026-11-13T10:00:00",
            "end": "2026-11-13T11:00:00",
            "location": "Lab Room B",
        },
    )
    add(
        id="cal-09",
        suite="calendar",
        title="Valid, wrong day",
        failure_class="wrong_but_valid_day",
        blurb="Valid ISO timestamps on the wrong day. Validation passes, so there is no retry.",
        user='Book "Lab walkthrough" on 2026-11-12 from 10:00 to 11:00 in Lab Room B.',
        expect_tool="create_event",
        expect_args=walk,
        raw=wrong_day,
        constrained=wrong_day,
        retry=[wrong_day],
    )

    export = {"project": "atlas", "minutes": 45, "note": "export reduced schema"}
    export_call = pretty("log_time", export)
    add(
        id="trk-01",
        suite="tracker",
        title="Clean time log",
        failure_class="clean",
        blurb="Well-formed time log. Both arms accept it.",
        user='Log 45 minutes on atlas with note "export reduced schema".',
        expect_tool="log_time",
        expect_args=export,
        raw=export_call,
        constrained=export_call,
        retry=[export_call],
    )

    replay = {"project": "beacon", "minutes": 90, "note": "replay harness"}
    add(
        id="trk-02",
        suite="tracker",
        title="Minutes as a string",
        failure_class="string_integer",
        blurb='minutes is the string "90". Strict mode does not coerce it. The grammar asks for an integer.',
        user='Log 90 minutes on beacon with note "replay harness".',
        expect_tool="log_time",
        expect_args=replay,
        raw=pretty("log_time", {**replay, "minutes": "90"}),
        constrained=pretty("log_time", replay),
        retry=[pretty("log_time", replay)],
    )

    cedar = {"project": "cedar", "minutes": 90, "note": "grammar notes"}
    add(
        id="trk-03",
        suite="tracker",
        title="Minutes over the maximum",
        failure_class="above_maximum",
        blurb="minutes is 900, over the 480 maximum encoded in the grammar. The constrained call uses 90.",
        user='Log 90 minutes on cedar with note "grammar notes".',
        expect_tool="log_time",
        expect_args=cedar,
        raw=pretty("log_time", {**cedar, "minutes": 900}),
        constrained=pretty("log_time", cedar),
        retry=[pretty("log_time", cedar)],
    )

    enum_note = {"project": "atlas", "minutes": 30, "note": "enum check"}
    add(
        id="trk-04",
        suite="tracker",
        title="Project enum case",
        failure_class="bad_enum",
        blurb='project is "Atlas". The grammar enum is lowercase.',
        user='Log 30 minutes on atlas with note "enum check".',
        expect_tool="log_time",
        expect_args=enum_note,
        raw=pretty("log_time", {**enum_note, "project": "Atlas"}),
        constrained=pretty("log_time", enum_note),
        retry=[pretty("log_time", enum_note)],
    )

    status = {"ticket_id": "tkt_012", "status": "in_progress"}
    add(
        id="trk-05",
        suite="tracker",
        title="Status synonym",
        failure_class="status_synonym",
        blurb='status is "In Progress". The grammar enum is in_progress.',
        user="Set ticket tkt_012 to in_progress.",
        expect_tool="set_status",
        expect_args=status,
        raw=pretty("set_status", {"ticket_id": "tkt_012", "status": "In Progress"}),
        constrained=pretty("set_status", status),
        retry=[pretty("set_status", status)],
    )

    blocked = {"ticket_id": "tkt_018", "status": "blocked"}
    add(
        id="trk-06",
        suite="tracker",
        title="Ticket id hyphen",
        failure_class="id_pattern",
        blurb="ticket_id uses a hyphen. That pattern is not in the grammar. The retry uses tkt_018.",
        user="Set ticket tkt_018 to blocked.",
        expect_tool="set_status",
        expect_args=blocked,
        raw=pretty("set_status", {"ticket_id": "tkt-018", "status": "blocked"}),
        constrained=pretty("set_status", {"ticket_id": "tkt-018", "status": "blocked"}),
        retry=[pretty("set_status", blocked)],
    )

    noted = {"project": "cedar", "minutes": 15, "note": "empty note rejected"}
    add(
        id="trk-07",
        suite="tracker",
        title="Empty note",
        failure_class="empty_string",
        blurb="note is empty. minLength is in the grammar, so the constrained call includes the note.",
        user='Log 15 minutes on cedar with note "empty note rejected".',
        expect_tool="log_time",
        expect_args=noted,
        raw=pretty("log_time", {**noted, "note": ""}),
        constrained=pretty("log_time", noted),
        retry=[pretty("log_time", noted)],
    )

    done = {"ticket_id": "tkt_012", "status": "done"}
    add(
        id="trk-08",
        suite="tracker",
        title="Unknown tool name",
        failure_class="unknown_tool",
        blurb="The unconstrained call names update_ticket, which is not in the tool enum.",
        user="Mark ticket tkt_012 done.",
        expect_tool="set_status",
        expect_args=done,
        raw=pretty("update_ticket", done),
        constrained=pretty("set_status", done),
        retry=[pretty("set_status", done)],
    )

    floats = {"project": "beacon", "minutes": 25, "note": "strict floats"}
    add(
        id="trk-09",
        suite="tracker",
        title="Float minutes",
        failure_class="float_not_int",
        blurb="minutes is 1.5. Strict integers reject floats. The grammar type is integer.",
        user='Log 25 minutes on beacon with note "strict floats".',
        expect_tool="log_time",
        expect_args=floats,
        raw=pretty("log_time", {**floats, "minutes": 1.5}),
        constrained=pretty("log_time", floats),
        retry=[pretty("log_time", floats)],
    )

    avery = {"name": "Avery Chen"}
    avery_call = pretty("lookup_contact", avery)
    add(
        id="look-01",
        suite="lookup",
        title="Contact lookup",
        failure_class="clean",
        blurb="Exact contact name. Both arms accept it.",
        user="Look up Avery Chen.",
        expect_tool="lookup_contact",
        expect_args=avery,
        raw=avery_call,
        constrained=avery_call,
        retry=[avery_call],
    )

    doc = {"doc_id": "doc_schema"}
    add(
        id="look-02",
        suite="lookup",
        title="Document id case",
        failure_class="doc_id_pattern",
        blurb="doc_id is uppercase. The pattern is not in the grammar. The retry lowercases it to doc_schema.",
        user="Open document doc_schema.",
        expect_tool="lookup_doc",
        expect_args=doc,
        raw=pretty("lookup_doc", {"doc_id": "DOC_SCHEMA"}),
        constrained=pretty("lookup_doc", {"doc_id": "DOC_SCHEMA"}),
        retry=[pretty("lookup_doc", doc)],
    )

    priya = {"name": "Priya Nair"}
    add(
        id="look-03",
        suite="lookup",
        title="Arguments are a string",
        failure_class="arguments_stringified",
        blurb="arguments is a JSON string instead of an object. The grammar requires an object.",
        user="Find Priya Nair in the directory.",
        expect_tool="lookup_contact",
        expect_args=priya,
        raw=pretty("lookup_contact", json.dumps(priya)),
        constrained=pretty("lookup_contact", priya),
        retry=[pretty("lookup_contact", priya)],
    )

    short = {"name": "Priya N."}
    short_call = pretty("lookup_contact", short)
    add(
        id="look-04",
        suite="lookup",
        title="Valid, wrong person",
        failure_class="wrong_but_valid_name",
        blurb="Valid call, shortened name. Validation passes, so there is no retry, and the lookup misses.",
        user="Who is Priya Nair?",
        expect_tool="lookup_contact",
        expect_args=priya,
        raw=short_call,
        constrained=short_call,
        retry=[short_call],
    )

    fixtures = {
        "calendar": [
            {
                "event_id": "evt_001",
                "title": "Standup",
                "start": "2026-11-03T09:00:00",
                "end": "2026-11-03T09:15:00",
                "location": "Lab Room B",
            },
            {
                "event_id": "evt_002",
                "title": "Vendor sync",
                "start": "2026-11-03T11:00:00",
                "end": "2026-11-03T11:30:00",
                "location": None,
            },
        ],
        "tickets": [
            {
                "ticket_id": "tkt_012",
                "project": "atlas",
                "title": "Schema export drops bounds",
                "status": "open",
            },
            {
                "ticket_id": "tkt_018",
                "project": "beacon",
                "title": "Retry prompt exceeds context",
                "status": "in_progress",
            },
        ],
        "contacts": [
            {"name": "Avery Chen", "role": "lab coordinator", "desk": "B2"},
            {"name": "Priya Nair", "role": "data engineer", "desk": "C1"},
        ],
        "docs": [
            {
                "doc_id": "doc_schema",
                "title": "Tool schema notes",
                "summary": "The reduced JSON schema drops pattern and cross-field checks.",
            },
            {
                "doc_id": "doc_retry",
                "title": "Retry loop",
                "summary": "Feed the validation trace back, then stop at N and do not execute.",
            },
        ],
    }
    return {"tasks": tasks, "recordings": recordings, "fixtures": fixtures}


def main() -> None:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("tasks", "recordings", "fixtures"):
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(payload[name], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
