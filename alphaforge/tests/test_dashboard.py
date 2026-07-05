"""Tests for the AlphaForge Mining Dashboard.

Tests cover:
- FastAPI endpoint returns 200 and valid JSON
- Template renders HTML with expected sections
- Empty data state renders gracefully
- Health endpoint returns ok
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Generator

import pytest
from fastapi.testclient import TestClient

from alphaforge.dashboard.app import app as dashboard_app
from alphaforge.paths import _find_repo_root


# ── Helpers ─────────────────────────────────────────────────────────────


def _make_mining_summary(
    candidates: int = 1000,
    rules: int = 50,
    l1: int = 25,
    l2: int = 15,
    l3: int = 10,
    speed: float = 8.5,
    pipeline: str = "running",
) -> dict[str, Any]:
    """Create a synthetic mining_summary dict for testing."""
    return {
        "run_id": "test_run_001",
        "generated_at": "2026-07-03T12:00:00Z",
        "mining_overview": {
            "total_candidates_scanned": candidates,
            "total_rules_found": rules,
            "level_distribution": {"level_1": l1, "level_2": l2, "level_3": l3},
            "mining_speed_candidates_per_sec": speed,
        },
        "rule_performance": {
            "active_rules": [
                {
                    "rule_id": f"rule_{i:03d}",
                    "name": f"test_rule_{i}",
                    "mode": "SCALP",
                    "net_r": round(2.0 - i * 0.2, 2),
                    "win_rate": round(0.6 - i * 0.03, 2),
                    "rolling_sharpe": round(1.4 - i * 0.1, 2),
                    "trade_count": 100 - i * 10,
                }
                for i in range(5)
            ],
            "summary": {
                "avg_net_r": 1.6,
                "avg_win_rate": 0.54,
                "avg_rolling_sharpe": 1.1,
                "total_active_rules": 5,
            },
            "top_5_rules": [
                {
                    "rule_id": "rule_000",
                    "name": "test_rule_0",
                    "mode": "SCALP",
                    "net_r": 2.0,
                    "win_rate": 0.6,
                    "rolling_sharpe": 1.4,
                    "trade_count": 100,
                }
            ],
            "bottom_5_rules": [
                {
                    "rule_id": "rule_004",
                    "name": "test_rule_4",
                    "mode": "SCALP",
                    "net_r": 1.2,
                    "win_rate": 0.48,
                    "rolling_sharpe": 1.0,
                    "trade_count": 60,
                }
            ],
        },
        "mining_depth": {
            "features_scanned": 120,
            "total_features": 250,
            "bucket_coverage_pct": 48.0,
            "space_explored_pct": 35.0,
            "space_remaining_pct": 65.0,
        },
        "system_health": {
            "pipeline_status": pipeline,
            "last_run_timestamp": "2026-07-03T12:00:00Z",
            "error_rate": 0.01,
            "total_errors": 3,
            "uptime_seconds": 3600,
        },
    }


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Provide a TestClient for the dashboard app."""
    app = dashboard_app
    with TestClient(app) as tc:
        yield tc


@pytest.fixture
def mining_data_dir() -> Generator[Path, None, None]:
    """Create a temporary mining data directory with a sample summary.

    Overrides the app's repo root resolution by patching the path.
    """
    repo_root = _find_repo_root()
    target = repo_root / "reports" / "alphaforge" / "mining" / "test_run_20260703"
    target.mkdir(parents=True, exist_ok=True)
    summary_path = target / "mining_summary.json"
    data = _make_mining_summary()
    with open(summary_path, "w") as f:
        json.dump(data, f)
    yield target
    # Cleanup
    if summary_path.exists():
        summary_path.unlink()
    if target.exists():
        target.rmdir()


# ── Tests ───────────────────────────────────────────────────────────────


class TestDashboardEndpoints:
    """Verify that FastAPI endpoints respond correctly."""

    def test_health_endpoint(self, client: TestClient) -> None:
        """GET /api/health returns ok status."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["app"] == "alphaforge-dashboard"

    def test_api_mining_summary_returns_json(self, client: TestClient) -> None:
        """GET /api/mining-summary returns valid JSON."""
        resp = client.get("/api/mining-summary")
        assert resp.status_code == 200
        body = resp.json()
        # Should have expected top-level keys
        assert "mining_overview" in body
        assert "rule_performance" in body
        assert "mining_depth" in body
        assert "system_health" in body

    def test_api_mining_summary_structure(self, client: TestClient) -> None:
        """Verify the JSON structure contains required sections."""
        resp = client.get("/api/mining-summary")
        body = resp.json()

        mo = body.get("mining_overview", {})
        assert "total_candidates_scanned" in mo
        assert "total_rules_found" in mo
        assert "level_distribution" in mo
        assert "mining_speed_candidates_per_sec" in mo

        rp = body.get("rule_performance", {})
        assert "active_rules" in rp
        assert "summary" in rp
        assert "top_5_rules" in rp
        assert "bottom_5_rules" in rp

        md = body.get("mining_depth", {})
        assert "features_scanned" in md
        assert "total_features" in md
        assert "bucket_coverage_pct" in md
        assert "space_explored_pct" in md
        assert "space_remaining_pct" in md

        sh = body.get("system_health", {})
        assert "pipeline_status" in sh
        assert "last_run_timestamp" in sh
        assert "error_rate" in sh
        assert "total_errors" in sh
        assert "uptime_seconds" in sh

    def test_index_returns_html(self, client: TestClient) -> None:
        """GET / returns HTML with expected page title."""
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert "AlphaForge Mining Dashboard" in html
        assert "Mining Overview" in html
        assert "Rule Performance" in html
        assert "Mining Depth" in html
        assert "System Health" in html

    def test_index_contains_section_ids(self, client: TestClient) -> None:
        """HTML template includes all four panel sections."""
        resp = client.get("/")
        html = resp.text
        assert 'id="panel-overview"' in html
        assert 'id="panel-rules"' in html
        assert 'id="panel-depth"' in html
        assert 'id="panel-health"' in html

    def test_index_has_auto_refresh_script(self, client: TestClient) -> None:
        """Template includes the auto-refresh JavaScript."""
        resp = client.get("/")
        html = resp.text
        assert "/api/mining-summary" in html
        assert "REFRESH_INTERVAL" in html or "10000" in html

    def test_index_shows_empty_state_when_no_data(self, client: TestClient) -> None:
        """When no mining data exists, the template renders empty states."""
        resp = client.get("/")
        html = resp.text
        # Should have some empty-state indicator text
        assert "no_data" in html or "Waiting" in html or "unavailable" in html or "empty-state" in html


class TestDataLoading:
    """Verify the data loading from mining_summary.json."""

    def test_load_with_real_data(self, client: TestClient, mining_data_dir: Path) -> None:
        """When mining_summary.json exists, data loads correctly."""
        resp = client.get("/api/mining-summary")
        body = resp.json()
        assert body["_status"] == "ok"
        assert body["mining_overview"]["total_candidates_scanned"] == 1000
        assert body["mining_overview"]["total_rules_found"] == 50
        assert body["rule_performance"]["summary"]["total_active_rules"] == 5

    def test_load_missing_file_returns_defaults(self, client: TestClient) -> None:
        """When no mining data file exists, defaults are returned."""
        resp = client.get("/api/mining-summary")
        body = resp.json()
        assert body["_status"] == "no_data"
        # Defaults should be zeros
        assert body["mining_overview"]["total_candidates_scanned"] == 0
        assert body["mining_overview"]["total_rules_found"] == 0
        assert body["rule_performance"]["summary"]["total_active_rules"] == 0

    def test_load_corrupted_json_returns_defaults(self, client: TestClient) -> None:
        """Corrupted JSON files are handled gracefully."""
        repo_root = _find_repo_root()
        target = repo_root / "reports" / "alphaforge" / "mining" / "corrupt_run"
        target.mkdir(parents=True, exist_ok=True)
        summary_path = target / "mining_summary.json"
        try:
            with open(summary_path, "w") as f:
                f.write("{not valid json!!!}")

            resp = client.get("/api/mining-summary")
            body = resp.json()
            assert body["_status"] == "no_data"
        finally:
            if summary_path.exists():
                summary_path.unlink()
            if target.exists():
                target.rmdir()

    def test_level_distribution_renders_in_template(self, client: TestClient, mining_data_dir: Path) -> None:
        """Level distribution data appears in the rendered HTML."""
        resp = client.get("/")
        html = resp.text
        assert "Level 1" in html
        assert "Level 2" in html
        assert "Level 3" in html
        assert "bar-l1" in html
        assert "bar-l2" in html
        assert "bar-l3" in html

    def test_rule_tables_render(self, client: TestClient, mining_data_dir: Path) -> None:
        """Top and bottom rule tables are rendered."""
        resp = client.get("/")
        html = resp.text
        assert "Top Rules by Net R" in html
        assert "Bottom Rules by Net R" in html
        assert "test_rule_0" in html
        assert "test_rule_4" in html


class TestAppFactory:
    """Verify the app factory function."""

    def test_create_app_returns_fastapi_app(self) -> None:
        """dashboard_app is a configured FastAPI instance."""
        app = dashboard_app
        assert app.title == "AlphaForge Mining Dashboard"
        assert app.version == "0.1.0"

    def test_create_app_has_routes(self) -> None:
        """The app has the expected routes registered."""
        app = create_app()
        routes = [route.path for route in app.routes]
        assert "/" in routes
        assert "/api/mining-summary" in routes
        assert "/api/health" in routes
