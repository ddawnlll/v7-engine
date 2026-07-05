"""Tests for run_context.py -- timestamped run folder management."""

import json

from run_context import RunContext


def test_run_dir_creation(tmp_path):
    """RunContext with base_dir=tmp_path creates timestamped dir."""
    ctx = RunContext(base_dir=str(tmp_path), goal="test goal")
    assert ctx.run_dir.exists()
    assert ctx.run_dir.is_dir()

    goal_file = ctx.run_dir / "goal.json"
    assert goal_file.exists()
    data = json.loads(goal_file.read_text(encoding="utf-8"))
    assert data["goal"] == "test goal"


def test_iter_dir(tmp_path):
    """iter_dir() creates iter_000/ subdirectory."""
    ctx = RunContext(base_dir=str(tmp_path))
    it_dir = ctx.iter_dir()
    assert it_dir.exists()
    assert it_dir.name == "iter_000"


def test_save_methods(tmp_path):
    """All save methods create files in the iteration directory."""
    ctx = RunContext(base_dir=str(tmp_path))
    ctx.iter_dir()  # ensure iter_000/ exists

    p1 = ctx.save_strategist_request({"msg": "hello"})
    assert p1.exists()
    assert p1.name == "strategist_request.json"

    p2 = ctx.save_strategist_response({"task": "test"})
    assert p2.exists()
    assert p2.name == "strategist_response.json"

    p3 = ctx.save_worker_task("do the thing")
    assert p3.exists()
    assert p3.read_text(encoding="utf-8") == "do the thing"
    assert p3.name == "worker_task.txt"

    p4 = ctx.save_worker_log('{"exit_code": 0}')
    assert p4.exists()
    assert p4.name == "worker_output.json"

    p5 = ctx.save_gate_result({"verdict": "PASS"})
    assert p5.exists()
    assert p5.name == "gate_result.json"

    p6 = ctx.save_git_snapshot({"head": "abc123"})
    assert p6.exists()
    assert p6.name == "git_snapshot.json"

    p7 = ctx.save_summary({"final": "ok"})
    assert p7.exists()
    assert p7.name == "summary.json"


def test_next_iter(tmp_path):
    """next_iter increments counter and creates new directory."""
    ctx = RunContext(base_dir=str(tmp_path))
    it0 = ctx.iter_dir()
    assert it0.name == "iter_000"
    assert ctx.iteration == 0

    it1 = ctx.next_iter()
    assert it1.name == "iter_001"
    assert ctx.iteration == 1

    it2 = ctx.next_iter()
    assert it2.name == "iter_002"
    assert ctx.iteration == 2
