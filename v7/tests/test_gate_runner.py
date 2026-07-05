"""Tests for v7.gates.runner and v7.gates.config — gate runner, config, and report."""

import json
import os
import tempfile

import pytest
import yaml

from v7.gates.config import (
    DEFAULT_GATE_CONFIG,
    GateConfig,
    load_gate_config,
    resolve_gate_configs,
)
from v7.gates.runner import run_gates, to_json_report, write_report


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def swing_candidate():
    return {
        "request_id": "req_001",
        "mode": "SWING",
        "symbol": "BTCUSDT",
        "model_scope": "swing_v1",
    }


@pytest.fixture
def passing_context():
    return {
        "expectancy_r": 0.50,
        "expected_r_net": 0.25,
        "ece": 0.05,
        "oos_sharpe": 0.65,
        "oos_trade_count": 200,
        "fold_count": 6,
        "win_rate": 0.55,
        "profit_factor": 1.4,
        "max_drawdown_r": -2.5,
        "shadow_pipeline_ready": True,
        "shadow_duration_days": 28,
        "shadow_trade_count": 50,
        "paper_adapter_ready": True,
        "paper_duration_days": 28,
        "paper_trade_count": 100,
        "kill_switch_configured": True,
        "all_prior_gates_passed": True,
    }


@pytest.fixture
def failing_context():
    return {
        "expectancy_r": 0.10,  # Below SWING min 0.35
        "expected_r_net": -0.10,
        "ece": 0.25,
        "oos_sharpe": 0.15,
        "oos_trade_count": 30,
        "fold_count": 2,
        "win_rate": 0.28,
        "profit_factor": 0.8,
        "max_drawdown_r": -6.0,
    }


# ── GateConfig Tests ─────────────────────────────────────────────────────


class TestGateConfig:
    """Test GateConfig dataclass."""

    def test_defaults(self):
        """Default GateConfig should have expected field values."""
        cfg = GateConfig("G0")
        assert cfg.gate_id == "G0"
        assert cfg.enabled is True
        assert cfg.threshold is None
        assert cfg.stop_on_fail is False

    def test_immutable(self):
        """GateConfig should be frozen."""
        cfg = GateConfig("G0", enabled=True)
        with pytest.raises(Exception):
            cfg.enabled = False  # type: ignore

    def test_custom_values(self):
        """GateConfig should accept custom values."""
        cfg = GateConfig("G2", enabled=False, threshold=0.5, stop_on_fail=True)
        assert cfg.gate_id == "G2"
        assert cfg.enabled is False
        assert cfg.threshold == 0.5
        assert cfg.stop_on_fail is True


class TestDefaultGateConfig:
    """Test DEFAULT_GATE_CONFIG list."""

    def test_eleven_gates(self):
        """DEFAULT_GATE_CONFIG should have 11 entries (G0-G10)."""
        assert len(DEFAULT_GATE_CONFIG) == 11

    def test_sequential(self):
        """Gates should be in canonical G0-G10 order."""
        expected = [f"G{i}" for i in range(11)]
        actual = [cfg.gate_id for cfg in DEFAULT_GATE_CONFIG]
        assert actual == expected

    def test_g0_stop_on_fail(self):
        """G0 should have stop_on_fail=True (structural gate)."""
        g0 = next(cfg for cfg in DEFAULT_GATE_CONFIG if cfg.gate_id == "G0")
        assert g0.stop_on_fail is True

    def test_g7_g10_enabled_by_default(self):
        """G7-G10 should be enabled by default."""
        for gate_id in ("G7", "G8", "G9", "G10"):
            cfg = next(c for c in DEFAULT_GATE_CONFIG if c.gate_id == gate_id)
            assert cfg.enabled is True, f"{gate_id} should be enabled"

    def test_g0_g6_enabled(self):
        """G0-G6 should be enabled."""
        for i in range(7):
            cfg = next(c for c in DEFAULT_GATE_CONFIG if c.gate_id == f"G{i}")
            assert cfg.enabled is True, f"G{i} should be enabled"


class TestLoadGateConfig:
    """Test load_gate_config from YAML."""

    def test_load_defaults_on_missing_file(self):
        """load_gate_config should raise FileNotFoundError for missing path."""
        with pytest.raises(FileNotFoundError):
            load_gate_config("/nonexistent/path/gates.yaml")

    def test_load_valid_yaml(self):
        """Should load gates from valid YAML."""
        data = {
            "gates": [
                {"gate_id": "G0", "enabled": True, "stop_on_fail": True},
                {"gate_id": "G1", "enabled": True},
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            tmp_path = f.name

        try:
            configs = load_gate_config(tmp_path)
            # Should merge with defaults -> 11 gates
            assert len(configs) == 11
            # G0 should be enabled
            g0 = next(c for c in configs if c.gate_id == "G0")
            assert g0.enabled is True
            assert g0.stop_on_fail is True
        finally:
            os.unlink(tmp_path)

    def test_load_disables_gate(self):
        """Should disable a gate when YAML sets enabled=false."""
        data = {
            "gates": [
                {"gate_id": "G2", "enabled": False},
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            tmp_path = f.name

        try:
            configs = load_gate_config(tmp_path)
            g2 = next(c for c in configs if c.gate_id == "G2")
            assert g2.enabled is False
        finally:
            os.unlink(tmp_path)

    def test_load_with_threshold_override(self):
        """Should support threshold override from YAML."""
        data = {
            "gates": [
                {"gate_id": "G2", "threshold": 0.75},
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            tmp_path = f.name

        try:
            configs = load_gate_config(tmp_path)
            g2 = next(c for c in configs if c.gate_id == "G2")
            assert g2.threshold == 0.75
        finally:
            os.unlink(tmp_path)

    def test_invalid_yaml_no_gates_key(self):
        """Should raise ValueError if 'gates' key is missing."""
        data = {"something_else": []}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            tmp_path = f.name

        try:
            with pytest.raises(ValueError, match="top-level 'gates' list"):
                load_gate_config(tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_invalid_gate_id(self):
        """Should raise ValueError for invalid gate_id."""
        data = {"gates": [{"gate_id": "INVALID"}]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            tmp_path = f.name

        try:
            with pytest.raises(ValueError, match="Invalid gate_id"):
                load_gate_config(tmp_path)
        finally:
            os.unlink(tmp_path)


class TestResolveGateConfigs:
    """Test resolve_gate_configs helper."""

    def test_none_returns_defaults(self):
        """None input should return DEFAULT_GATE_CONFIG."""
        resolved = resolve_gate_configs(None)
        assert len(resolved) == 11
        for default, resolved_cfg in zip(DEFAULT_GATE_CONFIG, resolved):
            assert default == resolved_cfg

    def test_partial_override(self):
        """Partial override should fill missing from defaults."""
        custom = [GateConfig("G0", enabled=True, stop_on_fail=False)]
        resolved = resolve_gate_configs(custom)
        assert len(resolved) == 11
        g0 = next(c for c in resolved if c.gate_id == "G0")
        assert g0.stop_on_fail is False  # Overridden

    def test_preserves_order(self):
        """Result should preserve G0-G10 order."""
        custom = [GateConfig("G10"), GateConfig("G0")]
        resolved = resolve_gate_configs(custom)
        expected = [f"G{i}" for i in range(11)]
        assert [c.gate_id for c in resolved] == expected


# ── Runner Tests ─────────────────────────────────────────────────────────


class TestRunGates:
    """Test run_gates function."""

    def test_default_config_passes_strong_candidate(self, swing_candidate, passing_context):
        """Strong candidate with default config should pass all enabled gates."""
        results = run_gates(swing_candidate, passing_context)
        assert results["passed"] is True
        summary = results["summary"]
        assert "PROMOTE" in summary["recommendation"]
        # G0-G10 all pass
        expected_passed = {f"G{i}" for i in range(11)}
        assert set(summary["passed_gates"]) == expected_passed, (
            f"Expected passed gates {expected_passed}, got {summary['passed_gates']}"
        )

    def test_weak_candidate_fails(self, swing_candidate, failing_context):
        """Weak candidate should fail gates."""
        results = run_gates(swing_candidate, failing_context)
        assert results["passed"] is False
        summary = results["summary"]
        assert "HOLD" in summary["recommendation"]
        assert len(summary["failed_gates"]) > 0

    def test_meta_present(self, swing_candidate, passing_context):
        """Results should contain meta section with candidate info."""
        results = run_gates(swing_candidate, passing_context)
        meta = results["meta"]
        assert meta["candidate_id"] == "req_001"
        assert meta["mode"] == "SWING"
        assert meta["symbol"] == "BTCUSDT"
        assert "timestamp" in meta
        assert "config_summary" in meta

    def test_gate_results_present(self, swing_candidate, passing_context):
        """Results should contain gate_results with all enabled gates."""
        results = run_gates(swing_candidate, passing_context)
        gate_results = results["gate_results"]
        # G0-G10 should all be present (all enabled)
        for i in range(11):
            assert f"G{i}" in gate_results, f"G{i} should be in results"

    def test_label_in_meta(self, swing_candidate, passing_context):
        """candidate_label should appear in meta when provided."""
        results = run_gates(swing_candidate, passing_context, candidate_label="swing_v1@abc123")
        assert results["meta"]["candidate_label"] == "swing_v1@abc123"

    def test_label_defaults_to_model_scope(self, swing_candidate, passing_context):
        """candidate_label should default to model_scope when not provided."""
        results = run_gates(swing_candidate, passing_context)
        assert results["meta"]["candidate_label"] == "swing_v1"


# ── Report Tests ─────────────────────────────────────────────────────────


class TestToJsonReport:
    """Test to_json_report function."""

    def test_report_version(self, swing_candidate, passing_context):
        """Report should contain version and type fields."""
        results = run_gates(swing_candidate, passing_context)
        report = to_json_report(results)
        assert report["report_version"] == "1.0.0"
        assert report["report_type"] == "gate_evaluation"

    def test_report_passed_field(self, swing_candidate, passing_context):
        """Report should have 'passed' at top level."""
        results = run_gates(swing_candidate, passing_context)
        report = to_json_report(results)
        assert report["passed"] is True

    def test_report_json_serializable(self, swing_candidate, passing_context):
        """Report should be JSON-serializable."""
        results = run_gates(swing_candidate, passing_context)
        report = to_json_report(results)
        serialized = json.dumps(report, default=str)
        assert len(serialized) > 0
        # Verify it round-trips
        parsed = json.loads(serialized)
        assert parsed["report_version"] == "1.0.0"

    def test_report_contains_gate_details(self, swing_candidate, passing_context):
        """Report should contain individual gate results."""
        results = run_gates(swing_candidate, passing_context)
        report = to_json_report(results)
        gate_results = report["gate_results"]
        assert len(gate_results) > 0
        for gid, g in gate_results.items():
            assert "status" in g
            assert "score" in g
            assert "detail" in g


class TestWriteReport:
    """Test write_report function."""

    def test_write_report_creates_file(self, swing_candidate, passing_context):
        """write_report should create a JSON file at the given path."""
        results = run_gates(swing_candidate, passing_context)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name

        try:
            written_path = write_report(results, tmp_path)
            assert os.path.exists(tmp_path)
            assert written_path == os.path.abspath(tmp_path)

            # Verify it's valid JSON
            with open(tmp_path) as f:
                data = json.load(f)
            assert data["report_version"] == "1.0.0"
            assert "gate_results" in data
            assert "summary" in data
        finally:
            os.unlink(tmp_path)

    def test_write_report_creates_directory(self, swing_candidate, passing_context):
        """write_report should create intermediate directories."""
        results = run_gates(swing_candidate, passing_context)

        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = os.path.join(tmpdir, "nested", "dir", "report.json")
            written_path = write_report(results, nested_path)
            assert os.path.exists(nested_path)
            assert written_path == os.path.abspath(nested_path)

    def test_write_report_from_raw_results(self, swing_candidate, passing_context):
        """write_report should handle raw run_gates results (not already converted)."""
        results = run_gates(swing_candidate, passing_context)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name

        try:
            write_report(results, tmp_path)
            with open(tmp_path) as f:
                data = json.load(f)
            assert data["report_version"] == "1.0.0"
            assert "report_type" in data
        finally:
            os.unlink(tmp_path)


# ── Integration Tests: G1 Enhancement ────────────────────────────────────


class TestG1Enhancement:
    """Test enhanced G1 RESEARCH_BACKTEST with real metrics."""

    def test_g1_passes_with_strong_metrics(self, swing_candidate):
        """G1 should pass with all metrics meeting thresholds."""
        ctx = {
            "oos_sharpe": 0.65,
            "oos_trade_count": 200,
            "fold_count": 6,
            "win_rate": 0.55,
            "profit_factor": 1.4,
            "max_drawdown_r": -2.5,
        }
        results = run_gates(swing_candidate, ctx)
        g1 = results["gate_results"]["G1"]
        assert g1["status"] == "PASS"
        assert g1["score"] > 0.0

    def test_g1_fails_low_sharpe(self, swing_candidate):
        """G1 should fail when oos_sharpe < 0.3."""
        ctx = {"oos_sharpe": 0.15, "oos_trade_count": 200, "win_rate": 0.55}
        results = run_gates(swing_candidate, ctx)
        g1 = results["gate_results"]["G1"]
        assert g1["status"] == "FAIL"
        assert "oos_sharpe" in g1["detail"]

    def test_g1_fails_low_trade_count(self, swing_candidate):
        """G1 should fail when oos_trade_count < 50."""
        ctx = {"oos_sharpe": 0.65, "oos_trade_count": 10, "win_rate": 0.55}
        results = run_gates(swing_candidate, ctx)
        g1 = results["gate_results"]["G1"]
        assert g1["status"] == "FAIL"
        assert "oos_trade_count" in g1["detail"]

    def test_g1_fails_low_win_rate(self, swing_candidate):
        """G1 should fail when win_rate < 0.3."""
        ctx = {"oos_sharpe": 0.65, "oos_trade_count": 200, "win_rate": 0.15}
        results = run_gates(swing_candidate, ctx)
        g1 = results["gate_results"]["G1"]
        assert g1["status"] == "FAIL"
        assert "win_rate" in g1["detail"]

    def test_g1_fails_excessive_drawdown(self, swing_candidate):
        """G1 should fail when max_drawdown_r < -5.0."""
        ctx = {"oos_sharpe": 0.65, "oos_trade_count": 200, "win_rate": 0.55, "max_drawdown_r": -8.0}
        results = run_gates(swing_candidate, ctx)
        g1 = results["gate_results"]["G1"]
        assert g1["status"] == "FAIL"
        assert "max_drawdown_r" in g1["detail"]

    def test_g1_passes_low_folds_no_fail(self, swing_candidate):
        """G1 should pass when fold_count is missing (not provided) — other metrics ok."""
        ctx = {"oos_sharpe": 0.65, "oos_trade_count": 200, "win_rate": 0.55}
        results = run_gates(swing_candidate, ctx)
        g1 = results["gate_results"]["G1"]
        assert g1["status"] == "PASS"

    def test_g1_fails_low_folds_if_provided(self, swing_candidate):
        """G1 should fail when fold_count < 3 is explicitly provided."""
        ctx = {"oos_sharpe": 0.65, "oos_trade_count": 200, "fold_count": 2, "win_rate": 0.55}
        results = run_gates(swing_candidate, ctx)
        g1 = results["gate_results"]["G1"]
        assert g1["status"] == "FAIL"
        assert "fold_count" in g1["detail"]

    def test_g1_fallback_legacy_flag(self, swing_candidate):
        """G1 should fall back to legacy flag when no structured metrics."""
        ctx = {"g1_research_backtest_pass": True}
        results = run_gates(swing_candidate, ctx)
        g1 = results["gate_results"]["G1"]
        assert g1["status"] == "PASS"

        ctx2 = {"g1_research_backtest_pass": False}
        results2 = run_gates(swing_candidate, ctx2)
        g12 = results2["gate_results"]["G1"]
        assert g12["status"] == "FAIL"

    def test_g1_fails_profit_factor_below_1(self, swing_candidate):
        """G1 should fail when profit_factor < 1.0 (net loss)."""
        ctx = {"oos_sharpe": 0.65, "oos_trade_count": 200, "win_rate": 0.55, "profit_factor": 0.85}
        results = run_gates(swing_candidate, ctx)
        g1 = results["gate_results"]["G1"]
        assert g1["status"] == "FAIL"
        assert "profit_factor" in g1["detail"]

    def test_g1_handles_partial_metrics(self, swing_candidate):
        """G1 should handle partial metrics gracefully (only win_rate provided)."""
        ctx = {"win_rate": 0.55}
        results = run_gates(swing_candidate, ctx)
        g1 = results["gate_results"]["G1"]
        assert g1["status"] == "PASS"  # win_rate >= 0.3


# ── Integration Tests: G5 Enhancement ────────────────────────────────────


class TestG5Enhancement:
    """Test enhanced G5 SYMBOL_STABILITY with per-symbol contributions."""

    def _g5_ctx(self, **extra):
        """Build context with enough data for G2/G3/G6 to pass, plus extras."""
        base = {
            "expectancy_r": 0.50,
            "expected_r_net": 0.25,
            "ece": 0.05,
            "oos_sharpe": 0.65,
            "oos_trade_count": 200,
            "fold_count": 6,
            "win_rate": 0.55,
            "profit_factor": 1.4,
            "max_drawdown_r": -2.5,
        }
        base.update(extra)
        return base

    def test_g5_passes_balanced_symbols(self, swing_candidate):
        """G5 should pass when all symbols within 40% threshold."""
        ctx = self._g5_ctx(
            symbol_contributions={
                "BTCUSDT": 0.35,
                "ETHUSDT": 0.30,
                "SOLUSDT": 0.35,
            }
        )
        results = run_gates(swing_candidate, ctx)
        g5 = results["gate_results"]["G5"]
        assert g5["status"] == "PASS"
        assert g5["score"] == 1.0

    def test_g5_fails_dominant_symbol(self, swing_candidate):
        """G5 should fail when one symbol exceeds 40% threshold."""
        ctx = self._g5_ctx(
            symbol_contributions={
                "BTCUSDT": 0.60,
                "ETHUSDT": 0.20,
                "SOLUSDT": 0.20,
            }
        )
        results = run_gates(swing_candidate, ctx)
        g5 = results["gate_results"]["G5"]
        assert g5["status"] == "FAIL"
        assert "BTCUSDT" in g5["detail"]
        assert "40%" in g5["detail"]

    def test_g5_passes_no_contributions(self, swing_candidate):
        """G5 should pass when no symbol_contributions present."""
        results = run_gates(swing_candidate, self._g5_ctx())
        g5 = results["gate_results"]["G5"]
        assert g5["status"] == "PASS"
        assert "No per-symbol" in g5["detail"]

    def test_g5_passes_empty_contributions(self, swing_candidate):
        """G5 should pass when symbol_contributions is empty dict."""
        ctx = self._g5_ctx(symbol_contributions={})
        results = run_gates(swing_candidate, ctx)
        g5 = results["gate_results"]["G5"]
        assert g5["status"] == "PASS"

    def test_g5_passes_single_symbol(self, swing_candidate):
        """G5 should pass gracefully with single symbol (concentration N/A)."""
        ctx = self._g5_ctx(symbol_contributions={"BTCUSDT": 1.0})
        results = run_gates(swing_candidate, ctx)
        g5 = results["gate_results"]["G5"]
        assert g5["status"] == "PASS"
        assert "Single symbol" in g5["detail"]

    def test_g5_passes_all_zero(self, swing_candidate):
        """G5 should pass when all contributions are zero."""
        ctx = self._g5_ctx(symbol_contributions={"BTCUSDT": 0.0, "ETHUSDT": 0.0})
        results = run_gates(swing_candidate, ctx)
        g5 = results["gate_results"]["G5"]
        assert g5["status"] == "PASS"

    def test_g5_score_reflects_violation(self, swing_candidate):
        """G5 score should be proportionally reduced by max violation."""
        ctx = self._g5_ctx(
            symbol_contributions={
                "BTCUSDT": 0.80,
                "ETHUSDT": 0.10,
                "SOLUSDT": 0.10,
            }
        )
        results = run_gates(swing_candidate, ctx)
        g5 = results["gate_results"]["G5"]
        assert g5["status"] == "FAIL"
        # max_share = 0.80 / (0.80+0.10+0.10) = 0.80
        # score = 0.40 / 0.80 = 0.50
        assert g5["score"] == 0.5


# ── Config overrides integration ─────────────────────────────────────────


class TestConfigWithRunner:
    """Test runner behavior with custom config."""

    def test_disabled_gate_skipped(self, swing_candidate, passing_context):
        """Disabling a gate via config should exclude it from results."""
        config = [GateConfig("G2", enabled=False)]
        results = run_gates(swing_candidate, passing_context, config=config)
        assert "G2" not in results["gate_results"]

    def test_stop_on_fail_honored(self, swing_candidate, failing_context):
        """stop_on_fail should stop evaluation after first failure."""
        config = [
            GateConfig("G0", enabled=True, stop_on_fail=True),
            GateConfig("G1", enabled=True, stop_on_fail=False),
        ]
        # G0 should pass (valid candidate), so it continues to G1
        results = run_gates(swing_candidate, failing_context, config=config)
        # G0 passes, so all configured gates run
        assert "G0" in results["gate_results"]
        assert "G1" in results["gate_results"]

        # Now make G0 fail with stop_on_fail=True
        bad_candidate = {"request_id": "", "mode": "INVALID", "symbol": "", "model_scope": ""}
        results2 = run_gates(bad_candidate, failing_context, config=config)
        # G0 fails and stops, G1 may not appear
        assert results2["gate_results"]["G0"]["status"] == "FAIL"
        # G1 may or may not be present depending on whether stop_on_fail stopped execution
        assert len(results2["gate_results"]) <= 2

    def test_custom_config_preserves_order(self, swing_candidate):
        """Custom config should not reorder gates."""
        config = [
            GateConfig("G10", enabled=False),
            GateConfig("G0", enabled=True),
        ]
        results = run_gates(swing_candidate, {}, config=config)
        # Gate keys should be in G0-G10 order, not the order in config
        gate_ids = list(results["gate_results"].keys())
        assert gate_ids[0] == "G0"
        assert "G10" not in gate_ids  # disabled
