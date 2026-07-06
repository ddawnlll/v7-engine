"""Tests for AlphaRunner shadow mode skeleton.

Issue #276: Verify the class skeleton has no order submission path,
correct feature count, locked threshold, and stub behavior.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALPHA_RUNNER_PATH = Path(__file__).resolve().parent.parent / "services" / "alpha_runner.py"
ALPHA_RUNNER_SOURCE = ALPHA_RUNNER_PATH.read_text()
ALPHA_RUNNER_MODULE = "runtime.services.alpha_runner"


# Forbidden import patterns — order submission / broker / execution
FORBIDDEN_PATTERNS = [
    "paper_execution",
    "execution_orchestrator",
    "binance_client",
    "PaperBroker",
    "PaperExecution",
    "submit_order",
    "place_order",
]

LOCKED_FEATURES = [
    "bb_position",
    "ofi_N",
    "atr_expansion_N",
    "return_zscore_N",
    "vwap_mid_deviation_N",
    "trade_count_N",
    "multi_level_obi_N",
    "microprice_N",
    "log_return_1",
    "garman_klass_vol_N",
    "doji_N",
    "hammer_N",
    "volume_trend_N",
    "cusum_positive",
    "rsi_N",
    "parkinson_vol_N",
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAlphaRunnerHasNoOrderSubmissionPath:
    """Verify no order submission, broker, or execution imports exist."""

    def test_no_order_submission_imports_in_source(self):
        """AST parse the source and assert no forbidden imports."""
        tree = ast.parse(ALPHA_RUNNER_SOURCE)
        imported_names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_names.append(node.module)

        for name in imported_names:
            for pattern in FORBIDDEN_PATTERNS:
                assert pattern not in name.lower(), (
                    f"AlphaRunner source imports forbidden module: {name} "
                    f"(matches pattern '{pattern}'). "
                    "This module is observe-only and must not submit orders."
                )

    def test_no_order_submission_references_in_docstrings(self):
        """Verify no execution/broker references in docstrings."""
        # The module docstring should mention observe-only but not reference execution APIs
        lines = ALPHA_RUNNER_SOURCE.split("\n")
        # Check first docstring block
        in_docstring = False
        for line in lines[:30]:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
            if in_docstring:
                for forbidden in ["submit_order", "place_order", "execute_order"]:
                    assert forbidden not in stripped.lower(), (
                        f"Module docstring contains execution reference: {forbidden}"
                    )

    def test_class_has_no_broker_attributes(self):
        """Assert the class does not declare broker/execution attributes."""
        tree = ast.parse(ALPHA_RUNNER_SOURCE)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "AlphaRunner":
                attr_names = []
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                attr_names.append(target.id)
                            elif isinstance(target, ast.Attribute):
                                attr_names.append(target.attr)
                for attr in attr_names:
                    for pattern in FORBIDDEN_PATTERNS:
                        assert pattern not in attr.lower(), (
                            f"AlphaRunner has forbidden attribute: {attr}"
                        )


class TestAlphaRunnerFeatureManifestCompleteness:
    """Assert exactly 16 features in feature_names."""

    def test_feature_names_count(self):
        from runtime.services.alpha_runner import ALPHA1_LOCKED_FEATURES

        assert len(ALPHA1_LOCKED_FEATURES) == 16, (
            f"Expected exactly 16 locked features, got {len(ALPHA1_LOCKED_FEATURES)}"
        )

    def test_feature_names_match_locked_set(self):
        from runtime.services.alpha_runner import ALPHA1_LOCKED_FEATURES

        assert ALPHA1_LOCKED_FEATURES == LOCKED_FEATURES

    def test_class_feature_names_property(self):
        from runtime.services.alpha_runner import AlphaRunner

        runner = AlphaRunner(
            artifact_path="/tmp/fake_model.bin",
            expected_model_sha256="abc123",
            expected_manifest_sha256="def456",
            expected_threshold=0.550,
        )
        assert len(runner.feature_names) == 16
        assert runner.feature_names == LOCKED_FEATURES


class TestAlphaRunnerThresholdMatchesLockedValue:
    """Assert threshold == 0.550."""

    def test_locked_threshold_constant(self):
        from runtime.services.alpha_runner import ALPHA1_LOCKED_THRESHOLD

        assert ALPHA1_LOCKED_THRESHOLD == 0.550

    def test_class_threshold_property(self):
        from runtime.services.alpha_runner import AlphaRunner

        runner = AlphaRunner(
            artifact_path="/tmp/fake_model.bin",
            expected_model_sha256="abc123",
            expected_manifest_sha256="def456",
            expected_threshold=0.550,
        )
        assert runner.threshold == 0.550


class TestAlphaRunnerComputeFeaturesIsStub:
    """Assert NotImplementedError when live engine not available."""

    def test_compute_features_raises_not_implemented(self):
        import pandas as pd

        from runtime.services.alpha_runner import AlphaRunner

        runner = AlphaRunner(
            artifact_path="/tmp/fake_model.bin",
            expected_model_sha256="abc123",
            expected_manifest_sha256="def456",
            expected_threshold=0.550,
        )
        dummy_candles = pd.DataFrame(
            {"open": [1.0], "high": [1.1], "low": [0.9], "close": [1.0], "volume": [100.0]}
        )
        with pytest.raises(NotImplementedError, match="Pending lib/alpha1_inference"):
            runner.compute_features(dummy_candles)

    def test_run_shadow_returns_none_when_feature_engine_missing(self):
        import pandas as pd

        from runtime.services.alpha_runner import AlphaRunner

        runner = AlphaRunner(
            artifact_path="/tmp/fake_model.bin",
            expected_model_sha256="a" * 64,
            expected_manifest_sha256="b" * 64,
            expected_threshold=0.550,
        )
        # Manually set bundle to bypass hash check (skeleton — no real model)
        runner._bundle = {"model": None, "manifest": {}}

        dummy_candles = pd.DataFrame(
            {"open": [1.0], "high": [1.1], "low": [0.9], "close": [1.0], "volume": [100.0]}
        )
        # predict should work when bundle is loaded
        result = runner.predict({"feat": 0.0})
        assert result["signal"] == "NEUTRAL"
        assert result["threshold"] == 0.550
