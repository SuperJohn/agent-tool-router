import json

from toolrouter.schema import reduce_schema
from toolrouter.tools import TOOLS, Catalog, CreateEvent, LogTime, Store


def _nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nodes(child)


def test_reduce_schema_drops_pattern_and_keeps_bounds():
    reduced = reduce_schema(CreateEvent.model_json_schema())
    assert "pattern" not in json.dumps(reduced)
    assert reduced["properties"]["title"]["minLength"] == 1
    assert reduced["properties"]["title"]["maxLength"] == 80
    assert "location" not in reduced["required"]
    assert reduced["additionalProperties"] is False
    assert reduced["properties"]["start"]["type"] == "string"
    assert "pattern" not in reduced["properties"]["start"]


def test_optional_null_branch_collapses_to_string():
    reduced = reduce_schema(CreateEvent.model_json_schema())
    location = reduced["properties"]["location"]
    assert location["type"] == "string"
    assert "anyOf" not in location
    assert location["maxLength"] == 40


def test_catalog_grammar_is_anyof_without_patterns():
    schema = Catalog(Store.from_fixtures(_fixtures())).grammar_schema()
    assert len(schema["anyOf"]) == len(TOOLS)
    for node in _nodes(schema):
        assert "pattern" not in node
        assert "format" not in node
    branches = {branch["properties"]["tool"]["enum"][0]: branch for branch in schema["anyOf"]}
    minutes = branches["log_time"]["properties"]["arguments"]["properties"]["minutes"]
    assert minutes["type"] == "integer"
    assert minutes["minimum"] == 1
    assert minutes["maximum"] == 480
    assert branches["log_time"]["properties"]["arguments"]["properties"]["project"]["enum"] == [
        "atlas",
        "beacon",
        "cedar",
    ]
    assert branches["set_status"]["properties"]["arguments"]["properties"]["status"]["enum"] == [
        "open",
        "in_progress",
        "blocked",
        "done",
    ]
    create_required = branches["create_event"]["properties"]["arguments"]["required"]
    assert "location" not in create_required
    assert "start" in create_required


def test_narrowed_schema_names_one_tool():
    catalog = Catalog(Store.from_fixtures(_fixtures()))
    narrowed = catalog.narrowed_schema("cancel_event")
    assert "anyOf" not in narrowed
    assert narrowed["properties"]["tool"]["enum"] == ["cancel_event"]
    assert "event_id" in narrowed["properties"]["arguments"]["properties"]
    assert "pattern" not in json.dumps(narrowed)


def test_log_time_literal_survives_reduction():
    reduced = LogTime.model_json_schema()
    assert "atlas" in json.dumps(reduce_schema(reduced))


def _fixtures():
    return {
        "calendar": [],
        "tickets": [],
        "contacts": [],
        "docs": [],
    }
