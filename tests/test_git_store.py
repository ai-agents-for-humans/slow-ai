from pathlib import Path

import pytest

from slow_ai.execution.git_store import GitStore


@pytest.fixture
def store(tmp_path):
    return GitStore(run_id="test-run", base_path=tmp_path)


def test_init_creates_directory(tmp_path):
    store = GitStore(run_id="my-run", base_path=tmp_path)
    assert (tmp_path / "my-run").is_dir()


def test_commit_brief(store, tmp_path):
    brief = {"goal": "Find EO datasets", "domain": "agriculture"}
    sha = store.commit_brief(brief)
    assert len(sha) == 40
    assert (tmp_path / "test-run" / "problem_brief.json").exists()


def test_commit_milestone_writes_artefacts(store, tmp_path):
    store.commit_brief({"goal": "test"})
    sha = store.commit_milestone(
        "M0-plan",
        {"research_plan.json": {"specialists": []}},
        registry_snapshot={"agents": {}, "total_agents": 0, "running": 0},
    )
    assert len(sha) == 40
    assert (tmp_path / "test-run" / "research_plan.json").exists()
    assert (tmp_path / "test-run" / "registry.json").exists()


def test_commit_milestone_without_registry(store, tmp_path):
    store.commit_brief({"goal": "test"})
    store.commit_milestone("M0-plan", {"plan.json": {"data": 1}})
    assert (tmp_path / "test-run" / "plan.json").exists()
    assert not (tmp_path / "test-run" / "registry.json").exists()


def test_record_skipped_path(store, tmp_path):
    store.commit_brief({"goal": "test"})
    store.record_skipped_path("nasa-failed", reason="timeout", triggered_by="runner")
    assert (tmp_path / "test-run" / "paths" / "not_taken" / "nasa-failed.json").exists()


def test_get_log_returns_commits_in_order(store):
    store.commit_brief({"goal": "test"})
    store.commit_milestone("M0-plan", {"plan.json": {}})
    log = store.get_log()
    assert len(log) == 2
    # iter_commits returns newest first
    assert "[M0-plan]" in log[0]["message"]
    assert "[init] problem brief" in log[1]["message"]


def test_get_log_entry_fields(store):
    store.commit_brief({"goal": "test"})
    entry = store.get_log()[0]
    assert "sha" in entry
    assert "message" in entry
    assert "timestamp" in entry
    assert len(entry["sha"]) == 8
