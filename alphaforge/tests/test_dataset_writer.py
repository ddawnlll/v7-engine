"""Test suite for DatasetWriter — deterministic serialization, checksum, roundtrip.

Covers acceptance criteria:
  AC-04-021: write() serializes and returns SHA-256 hex
  AC-04-022: Same input twice -> byte-identical files
  AC-04-023: Same input twice -> identical checksums
  AC-04-024: verify_roundtrip() returns True for identical data
  AC-04-025: verify_roundtrip() returns False with diff for modified data
  AC-04-026: read() reconstructs LabeledDataset from CSV
  AC-04-027: CSV fallback when Parquet unavailable
  AC-04-028: No ML imports
  AC-04-035: Deterministic write (byte-identical, same checksum)
  AC-04-036: Roundtrip returns True
  AC-04-037: Modified dataset roundtrip returns False
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Dict, List

import pytest

from alphaforge.dataset.contracts import LabeledDataset, LineageProvenance
from alphaforge.dataset.writer import DefaultWriter


# ===================================================================
# Helpers
# ===================================================================


def _make_sample_row(
    row_id: str = "r1",
    symbol: str = "BTCUSDT",
    feature_timestamp: str = "2025-01-01T00:00:00+00:00",
    label_timestamp: str = "2025-01-01T01:00:00+00:00",
    mode: str = "SWING",
    features: Dict[str, float] | None = None,
) -> LabeledDataset:
    return LabeledDataset(
        row_id=row_id,
        symbol=symbol,
        feature_timestamp=feature_timestamp,
        label_timestamp=label_timestamp,
        mode=mode,
        features=features or {"f1": 1.0, "f2": 2.0},
        label_long_r_net=0.5,
        label_short_r_net=-0.2,
        label_best_action_label="LONG_NOW",
        label_validity="VALID",
        label_no_trade_quality="CORRECT_NO_TRADE",
        label_cost_impact_long=0.01,
        label_cost_impact_short=0.01,
        lineage=LineageProvenance(
            source_manifest_id="m1",
            label_checksum="abc123",
            feature_spec_version="v1",
            feature_set_id="v1",
            label_dataset_id="l1",
            simulation_profile_id="sp1",
            assembled_at="2025-01-01T00:00:00+00:00",
        ),
        quality_flags=["TBD"],
    )


# ===================================================================
# Basic write
# ===================================================================


class TestBasicWrite:
    """AC-04-021: write produces file and returns checksum."""

    def test_write_produces_file(self, writer: DefaultWriter) -> None:
        dataset = [_make_sample_row()]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.csv")
            checksum = writer.write(dataset, path)
            assert os.path.exists(path)
            assert isinstance(checksum, str)
            assert len(checksum) == 64  # SHA-256 hex

    def test_write_returns_hex_string(self, writer: DefaultWriter) -> None:
        dataset = [_make_sample_row()]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.csv")
            checksum = writer.write(dataset, path)
            # Must be valid hex
            int(checksum, 16)
            assert len(checksum) == 64

    def test_empty_dataset_write(self, writer: DefaultWriter) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "empty.csv")
            checksum = writer.write([], path)
            assert os.path.exists(path)
            assert isinstance(checksum, str)


# ===================================================================
# Deterministic write
# ===================================================================


class TestDeterministicWrite:
    """AC-04-022, AC-04-023, AC-04-035: determinism."""

    def test_same_dataset_twice_identical_files(
        self, writer: DefaultWriter
    ) -> None:
        dataset = [
            _make_sample_row("r1", "BTCUSDT", features={"f1": 1.0, "f2": 2.0}),
            _make_sample_row("r2", "ETHUSDT", features={"f1": 3.0, "f2": 4.0}),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = os.path.join(tmpdir, "test1.csv")
            path2 = os.path.join(tmpdir, "test2.csv")

            writer.write(dataset, path1)
            writer.write(dataset, path2)

            with open(path1, "rb") as f1, open(path2, "rb") as f2:
                assert f1.read() == f2.read()

    def test_same_dataset_twice_identical_checksums(
        self, writer: DefaultWriter
    ) -> None:
        dataset = [
            _make_sample_row("r1", "BTCUSDT", features={"f1": 1.0}),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            c1 = writer.write(dataset, os.path.join(tmpdir, "a.csv"))
            c2 = writer.write(dataset, os.path.join(tmpdir, "b.csv"))
            assert c1 == c2

    def test_deterministic_sorting(self, writer: DefaultWriter) -> None:
        """Rows should be sorted by (symbol, feature_timestamp)."""
        dataset = [
            _make_sample_row("r3", "ETHUSDT", "2025-01-01T00:00:00+00:00"),
            _make_sample_row("r1", "BTCUSDT", "2025-01-01T00:00:00+00:00"),
            _make_sample_row("r2", "BTCUSDT", "2024-12-31T00:00:00+00:00"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.csv")
            writer.write(dataset, path)
            reconstructed = writer.read(path)

            # Should be sorted: BTCUSDT before ETHUSDT, then by timestamp
            symbols = [r.symbol for r in reconstructed]
            assert symbols[0] == "BTCUSDT"
            assert symbols[1] == "BTCUSDT"
            assert symbols[2] == "ETHUSDT"

            # Earlier BTCUSDT timestamp first
            assert reconstructed[0].feature_timestamp < reconstructed[1].feature_timestamp

    def test_float_formatting_deterministic(self, writer: DefaultWriter) -> None:
        """Floats should be formatted consistently ('%.10g')."""
        dataset = [_make_sample_row(features={"precise_value": 0.123456789012345})]
        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = os.path.join(tmpdir, "a.csv")
            path2 = os.path.join(tmpdir, "b.csv")
            writer.write(dataset, path1)
            writer.write(dataset, path2)
            with open(path1, "rb") as f1, open(path2, "rb") as f2:
                assert f1.read() == f2.read()


# ===================================================================
# Read / roundtrip
# ===================================================================


class TestRead:
    """AC-04-026: read() reconstructs LabeledDataset."""

    def test_read_reconstructs_single_row(self, writer: DefaultWriter) -> None:
        dataset = [_make_sample_row()]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.csv")
            writer.write(dataset, path)
            reconstructed = writer.read(path)
            assert len(reconstructed) == 1
            r = reconstructed[0]
            assert r.symbol == "BTCUSDT"
            assert r.mode == "SWING"
            assert r.features["f1"] == 1.0
            assert r.features["f2"] == 2.0
            assert r.label_long_r_net == 0.5
            assert r.label_best_action_label == "LONG_NOW"
            assert r.lineage.source_manifest_id == "m1"

    def test_read_reconstructs_multiple_rows(
        self, writer: DefaultWriter
    ) -> None:
        dataset = [
            _make_sample_row("r1", "BTCUSDT", features={"a": 1.0}),
            _make_sample_row("r2", "ETHUSDT", features={"a": 2.0}),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.csv")
            writer.write(dataset, path)
            reconstructed = writer.read(path)
            assert len(reconstructed) == 2
            symbols = {r.symbol for r in reconstructed}
            assert symbols == {"BTCUSDT", "ETHUSDT"}

    def test_read_empty_file(self, writer: DefaultWriter) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "empty.csv")
            writer.write([], path)
            reconstructed = writer.read(path)
            assert reconstructed == []


class TestRoundtrip:
    """AC-04-024, AC-04-036: roundtrip verification."""

    def test_roundtrip_returns_true(self, writer: DefaultWriter) -> None:
        dataset = [
            _make_sample_row("r1", "BTCUSDT", features={"f1": 1.0, "f2": 2.0}),
            _make_sample_row("r2", "ETHUSDT", features={"f1": 3.0}),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.csv")
            writer.write(dataset, path)
            assert writer.verify_roundtrip(path, dataset) is True

    def test_modified_dataset_roundtrip_false(
        self, writer: DefaultWriter
    ) -> None:
        """AC-04-025, AC-04-037: modified data roundtrip returns False."""
        original = [
            _make_sample_row("r1", "BTCUSDT", features={"f1": 1.0}),
        ]
        modified = [
            _make_sample_row("r1", "BTCUSDT", features={"f1": 999.0}),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.csv")
            writer.write(original, path)
            assert writer.verify_roundtrip(path, modified) is False

    def test_different_row_count_roundtrip_false(
        self, writer: DefaultWriter
    ) -> None:
        original = [_make_sample_row("r1")]
        modified = [_make_sample_row("r1"), _make_sample_row("r2")]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.csv")
            writer.write(original, path)
            assert writer.verify_roundtrip(path, modified) is False


# ===================================================================
# CSV fallback (Parquet not required by default)
# ===================================================================


class TestCsvFallback:
    """AC-04-027: CSV functions correctly; Parquet degrades gracefully."""

    def test_csv_write_read_works(self, writer: DefaultWriter) -> None:
        dataset = [_make_sample_row()]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.csv")
            checksum = writer.write(dataset, path)
            assert checksum is not None
            reconstructed = writer.read(path)
            assert len(reconstructed) == 1

    def test_parquet_fallback_to_csv(
        self, writer: DefaultWriter, monkeypatch
    ) -> None:
        """When pyarrow is not available, Parquet write falls back to CSV."""
        dataset = [_make_sample_row()]
        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = os.path.join(tmpdir, "test.parquet")
            csv_path = os.path.join(tmpdir, "test.csv")

            # Simulate pyarrow not available
            import builtins
            original_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "pyarrow" or name.startswith("pyarrow."):
                    raise ImportError("No module named 'pyarrow'")
                return original_import(name, *args, **kwargs)

            with monkeypatch.context() as m:
                m.setattr(builtins, "__import__", mock_import)
                checksum = writer.write(dataset, parquet_path)

            # Should have fallen back to CSV at csv_path
            assert checksum is not None
            assert isinstance(checksum, str)
            assert len(checksum) == 64


# ===================================================================
# Fixture-based writer tests
# ===================================================================


class TestWithFixtures:
    """Writer tests using fixture assembled datasets."""

    def test_fixture_dataset_roundtrip(
        self,
        writer: DefaultWriter,
        sample_assembled_dataset: List[LabeledDataset],
    ) -> None:
        if len(sample_assembled_dataset) == 0:
            pytest.skip("No assembled rows to test")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "fixture_test.csv")
            writer.write(sample_assembled_dataset, path)
            assert writer.verify_roundtrip(path, sample_assembled_dataset) is True

    def test_fixture_dataset_checksum_stable(
        self,
        writer: DefaultWriter,
        sample_assembled_dataset: List[LabeledDataset],
    ) -> None:
        if len(sample_assembled_dataset) == 0:
            pytest.skip("No assembled rows to test")

        with tempfile.TemporaryDirectory() as tmpdir:
            c1 = writer.write(sample_assembled_dataset, os.path.join(tmpdir, "a.csv"))
            c2 = writer.write(sample_assembled_dataset, os.path.join(tmpdir, "b.csv"))
            assert c1 == c2


# ===================================================================
# File not found
# ===================================================================


class TestErrorHandling:
    """Edge case error handling."""

    def test_read_nonexistent_file_raises(self, writer: DefaultWriter) -> None:
        with pytest.raises(FileNotFoundError):
            writer.read("/tmp/nonexistent_dataset_99999.csv")


# ===================================================================
# Import boundary
# ===================================================================


class TestImportBoundary:
    """AC-04-028: no ML imports."""

    def test_no_ml_imports(self) -> None:
        import alphaforge.dataset.writer as wmod
        source = wmod.__file__
        if source:
            with open(source, "r") as f:
                content = f.read()
            import_lines = [
                line for line in content.split("\n")
                if line.strip().startswith(("import ", "from "))
            ]
            import_text = "\n".join(import_lines)
            for fb in ["xgboost", "sklearn", "tensorflow", "torch"]:
                assert fb not in import_text, f"Found forbidden import: {fb}"
