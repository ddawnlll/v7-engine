"""Tests for ResearchRunIndex — Research Artifact Registry + Canonical Run Index.

Tests cover:
- Writing and reloading a fresh index
- Adding runs and resolving canonical/superseded status
- Duplicate detection (same run_id)
- Multiple mode tracking
- Persistence round-trip
- Edge cases (empty artifact paths, zero counts, missing index path)
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

_src = Path(__file__).resolve().parent.parent / "src"
import sys

if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from alphaforge.reports.run_index import (
    ResearchRunIndex,
    STATUS_CANONICAL,
    STATUS_SUPERSEDED,
    STATUS_DUPLICATE,
    _default_index,
    _make_entry,
    _now_iso,
)


# ===================================================================
# Helpers
# ===================================================================


def _make_minimal_entry(
    run_id: str = "run-test-001",
    mode: str = "SWING",
    status: str = STATUS_CANONICAL,
    **overrides: Any,
) -> dict:
    """Build a minimal run entry with sensible defaults."""
    base = {
        "run_id": run_id,
        "mode": mode,
        "timestamp": "2026-07-01T00:00:00Z",
        "canonical_report_path": f"data/reports/{mode.lower()}/report_{run_id}.json",
        "candidate_count": 3,
        "trial_count": 124,
        "verdict": "BASELINE_VALID",
        "artifact_paths": [],
        "superseded_reports": [],
        "duplicate_reports": [],
        "status": status,
    }
    base.update(overrides)
    return base


# ===================================================================
# _default_index
# ===================================================================


class TestDefaultIndex:
    def test_structure(self):
        """Fresh default index has the expected keys."""
        idx = _default_index()
        assert idx["index_version"] == "1.0.0"
        assert "created_at" in idx
        assert "updated_at" in idx
        assert idx["runs"] == []
        assert idx["canonical"] == {}

    def test_timestamp_format(self):
        """created_at and updated_at are valid ISO-8601."""
        idx = _default_index()
        assert "T" in idx["created_at"]
        assert "Z" in idx["created_at"]
        assert "T" in idx["updated_at"]


# ===================================================================
# _make_entry
# ===================================================================


class TestMakeEntry:
    def test_all_fields_present(self):
        """Entry contains all required fields."""
        entry = _make_entry(
            run_id="r1",
            mode="SCALP",
            canonical_report_path="path.json",
            candidate_count=5,
            trial_count=100,
            verdict="REJECT",
            artifact_paths=["model.bin"],
            superseded_reports=["old.json"],
            duplicate_reports=[],
            status=STATUS_CANONICAL,
        )
        assert entry["run_id"] == "r1"
        assert entry["mode"] == "SCALP"
        assert entry["canonical_report_path"] == "path.json"
        assert entry["candidate_count"] == 5
        assert entry["trial_count"] == 100
        assert entry["verdict"] == "REJECT"
        assert entry["artifact_paths"] == ["model.bin"]
        assert entry["superseded_reports"] == ["old.json"]
        assert entry["duplicate_reports"] == []
        assert entry["status"] == STATUS_CANONICAL

    def test_timestamp_auto_generated(self):
        """Entry timestamp is a non-empty ISO string."""
        entry = _make_entry(
            run_id="r1", mode="SWING", canonical_report_path="p.json",
            candidate_count=0, trial_count=0, verdict="X",
            artifact_paths=[], superseded_reports=[], duplicate_reports=[],
            status=STATUS_CANONICAL,
        )
        assert len(entry["timestamp"]) > 10
        assert "T" in entry["timestamp"]


# ===================================================================
# ResearchRunIndex — construction
# ===================================================================


class TestInit:
    def test_default_path_resolved(self):
        """Default index path resolves to alphaforge_report/research_run_index.json."""
        index = ResearchRunIndex()
        assert "alphaforge_report" in str(index.index_path)
        assert index.index_path.name == "research_run_index.json"

    def test_custom_path(self):
        """Custom index path is used when provided."""
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "custom_index.json"
            index = ResearchRunIndex(index_path=custom)
            assert index.index_path == custom

    def test_nonexistent_file_starts_empty(self):
        """Loading a nonexistent path returns a fresh empty index."""
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "no_such_file.json"
            index = ResearchRunIndex(index_path=missing)
            assert index.runs == []
            assert index.canonical == {}

    def test_load_existing_file(self):
        """Pre-existing index file is loaded correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "existing.json"
            data = _default_index()
            data["runs"].append(
                _make_minimal_entry(run_id="existing_run")
            )
            data["canonical"]["SWING"] = "existing_run"
            with open(path, "w") as f:
                json.dump(data, f)

            index = ResearchRunIndex(index_path=path)
            assert len(index.runs) == 1
            assert index.runs[0]["run_id"] == "existing_run"
            assert index.canonical["SWING"] == "existing_run"

    def test_load_corrupted_file_starts_fresh(self):
        """A corrupted JSON file falls back to a fresh index."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corrupt.json"
            path.write_text("NOT JSON", encoding="utf-8")
            index = ResearchRunIndex(index_path=path)
            assert index.runs == []


# ===================================================================
# ResearchRunIndex — add_run
# ===================================================================


class TestAddRun:
    def test_first_run_becomes_canonical(self):
        """First run added for a mode becomes canonical."""
        index = ResearchRunIndex()
        entry = index.add_run(
            run_id="run-swing-001",
            mode="SWING",
            canonical_report_path="data/reports/swing/r1.json",
            candidate_count=5,
            trial_count=124,
            verdict="BASELINE_VALID",
        )
        assert entry["status"] == STATUS_CANONICAL
        assert entry["run_id"] == "run-swing-001"
        assert index.canonical["SWING"] == "run-swing-001"
        assert len(index.runs) == 1

    def test_second_run_supersedes_first(self):
        """Second run for same mode supersedes the first."""
        index = ResearchRunIndex()
        index.add_run(
            run_id="run-swing-001", mode="SWING",
            canonical_report_path="data/reports/swing/r1.json",
        )
        entry2 = index.add_run(
            run_id="run-swing-002", mode="SWING",
            canonical_report_path="data/reports/swing/r2.json",
            candidate_count=8,
            trial_count=200,
            verdict="CANDIDATE_FOR_V7_GATES",
        )

        # New entry is canonical
        assert entry2["status"] == STATUS_CANONICAL
        assert index.canonical["SWING"] == "run-swing-002"

        # Old entry is superseded
        first_entry = index.get_run("run-swing-001")
        assert first_entry is not None
        assert first_entry["status"] == STATUS_SUPERSEDED

        # New entry has superseded_reports pointing to old path
        assert "data/reports/swing/r1.json" in entry2["superseded_reports"]

    def test_independent_modes(self):
        """Different modes do not interfere with each other."""
        index = ResearchRunIndex()
        swing = index.add_run(
            run_id="run-swing-001", mode="SWING",
            canonical_report_path="data/reports/swing/r1.json",
        )
        scalp = index.add_run(
            run_id="run-scalp-001", mode="SCALP",
            canonical_report_path="data/reports/scalp/r1.json",
        )

        assert swing["status"] == STATUS_CANONICAL
        assert scalp["status"] == STATUS_CANONICAL
        assert index.canonical["SWING"] == "run-swing-001"
        assert index.canonical["SCALP"] == "run-scalp-001"

    def test_duplicate_run_id_detected(self):
        """Adding a run with an existing run_id marks it as duplicate."""
        index = ResearchRunIndex()
        index.add_run(
            run_id="run-swing-001", mode="SWING",
            canonical_report_path="data/reports/swing/r1.json",
        )
        dup = index.add_run(
            run_id="run-swing-001", mode="SWING",
            canonical_report_path="data/reports/swing/r1_dup.json",
        )

        assert dup["status"] == STATUS_DUPLICATE
        # Original remains canonical
        original = index.get_run("run-swing-001")
        assert original is not None
        assert original["status"] == STATUS_CANONICAL

    def test_duplicate_does_not_change_canonical(self):
        """Duplicate entry does NOT update the canonical map."""
        index = ResearchRunIndex()
        index.add_run(run_id="r1", mode="SWING", canonical_report_path="p1.json")
        index.add_run(run_id="r1", mode="SWING", canonical_report_path="p2.json")
        # Canonical still points to original r1
        assert index.canonical.get("SWING") == "r1"
        assert index.get_canonical_for_mode("SWING")["canonical_report_path"] == "p1.json"

    def test_multiple_supersedes_chain(self):
        """Three runs: each new canonical supersedes the previous."""
        index = ResearchRunIndex()
        index.add_run(run_id="r1", mode="SWING", canonical_report_path="p1.json")
        index.add_run(run_id="r2", mode="SWING", canonical_report_path="p2.json")
        index.add_run(run_id="r3", mode="SWING", canonical_report_path="p3.json")

        assert index.get_run("r1")["status"] == STATUS_SUPERSEDED
        assert index.get_run("r2")["status"] == STATUS_SUPERSEDED
        assert index.get_run("r3")["status"] == STATUS_CANONICAL

        # Last one only supersedes the immediate previous
        assert "p2.json" in index.get_run("r3")["superseded_reports"]

    def test_artifact_paths_stored(self):
        """Artifact paths list is preserved."""
        index = ResearchRunIndex()
        entry = index.add_run(
            run_id="r1", mode="SWING",
            canonical_report_path="p.json",
            artifact_paths=["model.json", "calibration.json"],
        )
        assert entry["artifact_paths"] == ["model.json", "calibration.json"]

    def test_default_artifact_paths_empty(self):
        """When artifact_paths is not provided, it defaults to empty list."""
        index = ResearchRunIndex()
        entry = index.add_run(
            run_id="r1", mode="SWING",
            canonical_report_path="p.json",
        )
        assert entry["artifact_paths"] == []

    def test_candidate_count_and_trial_count(self):
        """Candidate count and trial count are stored as provided."""
        index = ResearchRunIndex()
        entry = index.add_run(
            run_id="r1", mode="SCALP",
            canonical_report_path="p.json",
            candidate_count=12,
            trial_count=300,
        )
        assert entry["candidate_count"] == 12
        assert entry["trial_count"] == 300

    def test_verdict_stored(self):
        """Verdict string is preserved."""
        index = ResearchRunIndex()
        entry = index.add_run(
            run_id="r1", mode="AGGRESSIVE_SCALP",
            canonical_report_path="p.json",
            verdict="CONTINUE_RESEARCH",
        )
        assert entry["verdict"] == "CONTINUE_RESEARCH"


# ===================================================================
# ResearchRunIndex — get_canonical_for_mode / get_run
# ===================================================================


class TestLookup:
    def test_get_canonical_for_mode_returns_correct(self):
        index = ResearchRunIndex()
        index.add_run(run_id="r1", mode="SWING", canonical_report_path="p1.json")
        index.add_run(run_id="r2", mode="SCALP", canonical_report_path="p2.json")
        assert index.get_canonical_for_mode("SWING")["run_id"] == "r1"
        assert index.get_canonical_for_mode("SCALP")["run_id"] == "r2"

    def test_get_canonical_for_mode_nonexistent(self):
        index = ResearchRunIndex()
        assert index.get_canonical_for_mode("SWING") is None
        assert index.get_canonical_for_mode("UNKNOWN_MODE") is None

    def test_get_run_found(self):
        index = ResearchRunIndex()
        index.add_run(run_id="find-me", mode="SWING", canonical_report_path="p.json")
        entry = index.get_run("find-me")
        assert entry is not None
        assert entry["run_id"] == "find-me"

    def test_get_run_not_found(self):
        index = ResearchRunIndex()
        assert index.get_run("nonexistent") is None


# ===================================================================
# ResearchRunIndex — write + round-trip persistence
# ===================================================================


class TestWriteRoundTrip:
    def test_write_creates_file(self):
        """write() creates the index file on disk."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "idx.json"
            index = ResearchRunIndex(index_path=path)
            index.add_run(run_id="r1", mode="SWING", canonical_report_path="p.json")
            written = index.write()
            assert written.exists()
            assert written == path

    def test_round_trip_preserves_entries(self):
        """Written and re-loaded index has the same entries."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "idx.json"
            index = ResearchRunIndex(index_path=path)
            index.add_run(run_id="r1", mode="SWING", canonical_report_path="p.json",
                          candidate_count=5, trial_count=124, verdict="BASELINE_VALID")
            index.add_run(run_id="r2", mode="SCALP", canonical_report_path="p2.json",
                          candidate_count=3, trial_count=60, verdict="CONTINUE_RESEARCH")
            index.write()

            # Reload in a new instance
            index2 = ResearchRunIndex(index_path=path)
            assert len(index2.runs) == 2
            assert index2.canonical["SWING"] == "r1"
            assert index2.canonical["SCALP"] == "r2"
            r1 = index2.get_run("r1")
            assert r1 is not None
            assert r1["candidate_count"] == 5
            assert r1["verdict"] == "BASELINE_VALID"
            assert r1["status"] == STATUS_CANONICAL

    def test_round_trip_superseded_status_preserved(self):
        """Superseded status survives write + reload."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "idx.json"
            index = ResearchRunIndex(index_path=path)
            index.add_run(run_id="r1", mode="SWING", canonical_report_path="p1.json")
            index.add_run(run_id="r2", mode="SWING", canonical_report_path="p2.json")
            index.write()

            index2 = ResearchRunIndex(index_path=path)
            assert index2.get_run("r1")["status"] == STATUS_SUPERSEDED
            assert index2.get_run("r2")["status"] == STATUS_CANONICAL

    def test_round_trip_duplicate_preserved(self):
        """Duplicate status survives write + reload."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "idx.json"
            index = ResearchRunIndex(index_path=path)
            index.add_run(run_id="r1", mode="SWING", canonical_report_path="p1.json")
            index.add_run(run_id="r1", mode="SWING", canonical_report_path="p2.json")
            index.write()

            index2 = ResearchRunIndex(index_path=path)
            assert len(index2.runs) == 2
            dup = index2.get_run("r1")  # Returns first match
            # First is canonical, second is duplicate
            assert index2.runs[0]["status"] == STATUS_CANONICAL
            assert index2.runs[1]["status"] == STATUS_DUPLICATE

    def test_write_directory_created(self):
        """Parent directories are auto-created."""
        with tempfile.TemporaryDirectory() as tmp:
            deep = Path(tmp) / "a" / "b" / "c" / "idx.json"
            index = ResearchRunIndex(index_path=deep)
            index.add_run(run_id="r1", mode="SWING", canonical_report_path="p.json")
            index.write()
            assert deep.exists()


# ===================================================================
# ResearchRunIndex — reload
# ===================================================================


class TestReload:
    def test_reload_discards_in_memory_changes(self):
        """reload() discards un-written changes."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "idx.json"
            index = ResearchRunIndex(index_path=path)
            index.add_run(run_id="r1", mode="SWING", canonical_report_path="p.json",
                          verdict="BASELINE_VALID")
            # Persist the initial state
            index.write()

            # Make in-memory changes (not written to disk)
            index.add_run(run_id="r2", mode="SWING", canonical_report_path="p2.json")
            r1_entry = index.get_run("r1")
            assert r1_entry is not None
            r1_entry["verdict"] = "MODIFIED_BUT_NOT_SAVED"

            # Reload should restore the persisted state
            index.reload()
            assert len(index.runs) == 1  # r2 was in-memory only
            assert index.get_run("r1")["verdict"] == "BASELINE_VALID"  # original value from disk
