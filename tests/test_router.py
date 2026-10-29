import json

from toolrouter.dataset import Task, load_dataset
from toolrouter.parse import strip_fences
from toolrouter.prompting import VALIDATION_MARKER
from toolrouter.provider import MockProvider, ProviderError
from toolrouter.router import ToolRouter
from toolrouter.tools import Catalog, Store


def _task(dataset, task_id):
    return next(task for task in dataset.tasks if task.id == task_id)


def test_strip_fences_and_leave_prose():
    fenced = "```json\n{\"tool\": \"list_events\"}\n```"
    assert strip_fences(fenced) == '{"tool": "list_events"}'
    assert strip_fences("not json") == "not json"


def test_router_retries_with_trace_then_executes():
    dataset = load_dataset()
    task = _task(dataset, "cal-04")
    provider = MockProvider(dataset.recordings)
    store = Store.from_fixtures(dataset.fixtures)
    outcome = ToolRouter(Catalog(store), provider, max_retries=2, use_schema=True).run(task)

    assert outcome.validated is True
    assert outcome.retries == 1
    assert outcome.tool == "create_event"
    assert outcome.arguments["start"] == "2026-11-05T13:00:00"
    assert outcome.arguments["end"] == "2026-11-05T14:00:00"
    assert outcome.execution["ok"] is True
    assert outcome.execution["event"]["event_id"] == "evt_003"
    assert store.executions == 1
    assert len(store.calendar) == 3

    assert provider.calls[0]["schema"]["anyOf"]
    narrowed = provider.calls[1]["schema"]
    assert "anyOf" not in narrowed
    assert narrowed["properties"]["tool"]["enum"] == ["create_event"]
    assert outcome.attempts[0].valid is False
    assert outcome.attempts[0].retry_prompt is not None
    assert VALIDATION_MARKER in outcome.attempts[0].retry_prompt
    assert "end must be after start" in outcome.attempts[0].retry_prompt
    assert outcome.attempts[0].raw in outcome.attempts[0].retry_prompt
    assert outcome.attempts[1].schema_kind == "narrowed"
    assert outcome.attempts[1].valid is True


def test_failsafe_does_not_execute():
    dataset = load_dataset()
    task = _task(dataset, "cal-08")
    provider = MockProvider(dataset.recordings)
    store = Store.from_fixtures(dataset.fixtures)
    before = json.dumps(store.calendar)
    outcome = ToolRouter(Catalog(store), provider, max_retries=2, use_schema=True).run(task)

    assert outcome.validated is False
    assert outcome.retries == 2
    assert outcome.execution is None
    assert outcome.failure["ok"] is False
    assert outcome.failure["code"] == "unrecoverable"
    assert outcome.failure["tool"] == "create_event"
    assert store.executions == 0
    assert json.dumps(store.calendar) == before
    assert all(attempt.retry_prompt for attempt in outcome.attempts[:-1])
    assert outcome.attempts[-1].retry_prompt is None


def test_baseline_is_one_shot_without_schema():
    dataset = load_dataset()
    task = _task(dataset, "cal-03")
    provider = MockProvider(dataset.recordings)
    store = Store.from_fixtures(dataset.fixtures)
    outcome = ToolRouter(Catalog(store), provider, max_retries=0, use_schema=False).run(task)

    assert provider.calls[0]["schema"] is None
    assert len(provider.calls) == 1
    assert outcome.validated is False
    assert outcome.retries == 0
    assert outcome.failure["code"] == "unrecoverable"
    assert "JSON decode error" in outcome.failure["errors"][0]
    assert store.executions == 0


def test_fenced_baseline_still_validates():
    dataset = load_dataset()
    task = _task(dataset, "cal-02")
    provider = MockProvider(dataset.recordings)
    store = Store.from_fixtures(dataset.fixtures)
    outcome = ToolRouter(Catalog(store), provider, max_retries=0, use_schema=False).run(task)
    assert outcome.validated is True
    assert outcome.execution["day"] == "2026-11-03"
    assert len(outcome.execution["events"]) == 2


def test_provider_error_fails_safe():
    dataset = load_dataset()
    task = _task(dataset, "cal-01")

    class Boom:
        name = "boom"

        def complete(self, **kwargs):
            raise ProviderError("connection refused")

    store = Store.from_fixtures(dataset.fixtures)
    outcome = ToolRouter(Catalog(store), Boom(), max_retries=2, use_schema=True).run(task)
    assert outcome.validated is False
    assert outcome.failure["code"] == "provider_error"
    assert outcome.retries == 0
    assert store.executions == 0


def test_strict_models_reject_coercion_and_extras():
    dataset = load_dataset()
    catalog = Catalog(Store.from_fixtures(dataset.fixtures))
    _, _, string_minutes = catalog.validate_raw(
        '{"tool":"log_time","arguments":{"project":"atlas","minutes":"90","note":"x"}}'
    )
    assert string_minutes["details"][0]["type"] == "int_type"
    _, _, extra = catalog.validate_raw(
        '{"tool":"create_event","arguments":{"title":"A","start":"2026-11-03T15:00:00","end":"2026-11-03T16:00:00","attendees":["Avery Chen"]}}'
    )
    assert extra["details"][0]["type"] == "extra_forbidden"
    _, _, floated = catalog.validate_raw(
        '{"tool":"log_time","arguments":{"project":"atlas","minutes":1.5,"note":"x"}}'
    )
    assert floated["details"][0]["type"] == "int_type"


def test_mock_is_deterministic():
    dataset = load_dataset()
    task = Task(**{**_task(dataset, "trk-06").to_dict()})
    first = MockProvider(dataset.recordings)
    second = MockProvider(dataset.recordings)
    router_a = ToolRouter(Catalog(Store.from_fixtures(dataset.fixtures)), first, max_retries=2)
    router_b = ToolRouter(Catalog(Store.from_fixtures(dataset.fixtures)), second, max_retries=2)
    assert router_a.run(task).to_dict() == router_b.run(task).to_dict()
