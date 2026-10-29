import json

from scripts.build_dataset import build

from toolrouter.bench import run_benchmark, split_site
from toolrouter.dataset import load_dataset, repo_root, resolve_dataset_path
from toolrouter.provider import MockProvider

ROOT = repo_root()

# baseline_valid, router_first, router_valid, router_retries, router_correct, baseline_correct
EXPECTED = {
    "cal-01": (True, True, True, 0, True, True),
    "cal-02": (True, True, True, 0, True, True),
    "cal-03": (False, True, True, 0, True, False),
    "cal-04": (False, False, True, 1, True, False),
    "cal-05": (False, False, False, 2, False, False),
    "cal-06": (False, False, True, 2, True, False),
    "cal-07": (False, True, True, 0, True, False),
    "cal-08": (False, False, False, 2, False, False),
    "cal-09": (True, True, True, 0, False, False),
    "trk-01": (True, True, True, 0, True, True),
    "trk-02": (False, True, True, 0, True, False),
    "trk-03": (False, True, True, 0, True, False),
    "trk-04": (False, True, True, 0, True, False),
    "trk-05": (False, True, True, 0, True, False),
    "trk-06": (False, False, True, 1, True, False),
    "trk-07": (False, True, True, 0, True, False),
    "trk-08": (False, True, True, 0, True, False),
    "trk-09": (False, True, True, 0, True, False),
    "look-01": (True, True, True, 0, True, True),
    "look-02": (False, False, True, 1, True, False),
    "look-03": (False, True, True, 0, True, False),
    "look-04": (True, True, True, 0, False, False),
}


def test_dataset_files_match_spec():
    spec = build()
    data = ROOT / "demo" / "data"
    for name in ("tasks", "recordings", "fixtures"):
        on_disk = json.loads((data / f"{name}.json").read_text(encoding="utf-8"))
        assert on_disk == spec[name]


def test_synthetic_data_has_no_emails_or_phones():
    import re

    text = "\n".join(
        (ROOT / "demo" / "data" / name).read_text(encoding="utf-8")
        for name in ("tasks.json", "recordings.json", "fixtures.json")
    )
    assert not re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    assert not re.search(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b", text)


def test_benchmark_gap_matches_the_fixed_task_set():
    dataset = load_dataset()
    report = run_benchmark(dataset, MockProvider(dataset.recordings), max_retries=2, seed=42)
    by_id = {task["id"]: task for task in report["tasks"]}
    assert set(by_id) == set(EXPECTED)
    for task_id, (
        base_valid,
        router_first,
        router_valid,
        retries,
        router_correct,
        base_correct,
    ) in EXPECTED.items():
        row = by_id[task_id]
        with_arm = row["with_router"]
        without = row["without_router"]
        assert without["validated"] is base_valid, task_id
        assert without["retries"] == 0, task_id
        assert with_arm["attempts"][0]["valid"] is router_first, task_id
        assert with_arm["validated"] is router_valid, task_id
        assert with_arm["retries"] == retries, task_id
        assert with_arm["task_correct"] is router_correct, task_id
        assert without["task_correct"] is base_correct, task_id
        if not with_arm["validated"]:
            assert with_arm["execution"] is None
            assert with_arm["failure"]["code"] == "unrecoverable"
        if not without["validated"]:
            assert without["execution"] is None

    with_metrics = report["with_router"]
    without_metrics = report["without_router"]
    assert with_metrics["first_try_valid"] == 16
    assert with_metrics["valid_after_retry"] == 20
    assert with_metrics["unrecoverable"] == 2
    assert with_metrics["retry_total"] == 9
    assert with_metrics["mean_retries"] == 0.41
    assert with_metrics["task_correct"] == 18
    assert without_metrics["first_try_valid"] == 6
    assert without_metrics["valid_after_retry"] == 6
    assert without_metrics["mean_retries"] == 0.0
    assert without_metrics["unrecoverable"] == 16
    assert without_metrics["task_correct"] == 4
    assert with_metrics["first_try_valid_display"] == "72.7% (16/22)"
    assert with_metrics["valid_after_retry_display"] == "90.9% (20/22)"
    assert with_metrics["unrecoverable_display"] == "9.1% (2/22)"
    assert without_metrics["first_try_valid_display"] == "27.3% (6/22)"
    assert without_metrics["unrecoverable_display"] == "72.7% (16/22)"
    assert without_metrics["task_correct_display"] == "18.2% (4/22)"
    assert with_metrics["task_correct_display"] == "81.8% (18/22)"
    assert report["provider"] == "mock"
    assert "not a live model sample" in report["provider_label"]

    scoreboard, traces = split_site(report)
    assert "tasks" not in scoreboard
    assert len(traces["tasks"]) == 22
    assert "system_prompt" in traces


def test_recorded_site_matches_engine():
    dataset = load_dataset()
    fresh = run_benchmark(
        dataset,
        MockProvider(dataset.recordings),
        max_retries=2,
        seed=42,
        recorded_at="2026-10-29",
    )
    scoreboard, traces = split_site(fresh)
    saved_board = json.loads((ROOT / "site" / "data" / "scoreboard.json").read_text(encoding="utf-8"))
    saved_traces = json.loads((ROOT / "site" / "data" / "traces.json").read_text(encoding="utf-8"))
    assert saved_board == scoreboard
    assert saved_traces == traces
    saved_run = json.loads((ROOT / "results" / "runs" / "mock-seed42.json").read_text(encoding="utf-8"))
    assert saved_run == fresh


def test_dataset_uri_override(tmp_path, monkeypatch):
    for name in ("tasks.json", "recordings.json", "fixtures.json"):
        (tmp_path / name).write_text((ROOT / "demo" / "data" / name).read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("HL_DATASET_URI", str(tmp_path))
    dataset = load_dataset()
    assert len(dataset.tasks) == 22
    assert dataset.display == "custom"

    file_uri = tmp_path.as_uri()
    path, display = resolve_dataset_path(file_uri)
    assert path == tmp_path
    assert display == "custom"


def test_default_dataset_display_is_relative():
    path, display = resolve_dataset_path(None)
    assert path == ROOT / "demo" / "data"
    assert display == "demo/data"
    assert "home" not in display
