"""Smoke tests for v7_lite dataset expansion scripts."""
import json
import csv
from pathlib import Path

import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parent.parent  # v7-engine root
REPORTS = ROOT / "reports" / "v7_lite" / "dataset_expansion"
CACHE = ROOT / "cache" / "v7_lite_expanded_panel_v1"


class TestRequiredArtifacts:
    """All required success-condition artifacts must exist and be non-empty."""

    @pytest.mark.parametrize("path", [
        "registry/SYMBOL_UNIVERSE_REGISTRY.csv",
        "registry/SYMBOL_CLUSTER_MAP.yaml",
        "coverage/PANEL_CACHE_COVERAGE_REPORT.md",
        "quality/DATA_QUALITY_AUDIT.csv",
        "expansion/DATASET_EXPANSION_PLAN.md",
        "DATASET_EXPANSION_SUMMARY.md",
    ])
    def test_artifact_exists(self, path):
        f = REPORTS / path
        assert f.exists(), f"Missing: {path}"
        assert f.stat().st_size > 0, f"Empty: {path}"

    def test_loop_state_json(self):
        with open(REPORTS / "LOOP_STATE.json") as f:
            state = json.load(f)
        assert state["status"] == "COMPLETE"
        assert isinstance(state["overall_readiness_current"], int)
        assert len(state["artifacts_produced"]) >= 5

    def test_experiments_jsonl(self):
        rows = []
        with open(REPORTS / "experiments.jsonl") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        assert len(rows) >= 4, f"Expected ≥4 ledger rows, got {len(rows)}"
        for r in rows:
            assert "timestamp" in r
            assert "task" in r
            assert "status" in r
            assert r["status"] in ("PASS", "PARTIAL", "FAIL", "BLOCKED")


class TestExpandedPanelCache:
    """Expanded panel cache must exist and be readable."""

    @pytest.mark.parametrize("field", ["open", "high", "low", "close", "volume"])
    def test_panel_file_readable(self, field):
        path = CACHE / f"panel_v7lite_expanded_{field}.parquet"
        assert path.exists(), f"Missing panel: {field}"
        t = pq.read_table(path)
        assert len(t) > 1_000_000, f"Panel {field} too small: {len(t)}"
        assert "timestamp" in t.column_names
        assert "symbol" in t.column_names
        assert field in t.column_names

    def test_manifest_json(self):
        with open(CACHE / "manifest.json") as f:
            manifest = json.load(f)
        assert manifest["symbols_count"] >= 50
        assert manifest["timeframe"] == "1h"
        assert len(manifest["output_files"]) == 5


class TestRegistryCSV:
    """SYMBOL_UNIVERSE_REGISTRY.csv must be well-formed."""

    def test_registry_rows(self):
        with open(REPORTS / "registry" / "SYMBOL_UNIVERSE_REGISTRY.csv") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) >= 50, f"Expected ≥50 registry rows, got {len(rows)}"

    def test_registry_columns(self):
        with open(REPORTS / "registry" / "SYMBOL_UNIVERSE_REGISTRY.csv") as f:
            reader = csv.DictReader(f)
            row = next(reader)
        required = {"symbol", "cluster_primary", "priority", "available_in_current_cache"}
        assert required.issubset(set(row.keys())), f"Missing columns: {required - set(row.keys())}"


class TestQualityAudit:
    """DATA_QUALITY_AUDIT.csv must be well-formed with no failures."""

    def test_quality_rows(self):
        with open(REPORTS / "quality" / "DATA_QUALITY_AUDIT.csv") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) >= 80, f"Expected ≥80 quality rows, got {len(rows)}"

    def test_no_quality_failures(self):
        with open(REPORTS / "quality" / "DATA_QUALITY_AUDIT.csv") as f:
            reader = csv.DictReader(f)
            failures = [r for r in reader if "FAIL" in r.get("verdict", "")]
        assert len(failures) == 0, f"Quality failures: {failures[:3]}"
