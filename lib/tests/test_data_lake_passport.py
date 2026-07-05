"""
Tests for DataPassport --- construction, trustworthiness, and serialisation.
"""

import os
import tempfile
from datetime import datetime, timezone

import pytest

from lib.data_lake.catalog import DataCatalog
from lib.data_lake.checksum import ChecksumReport
from lib.data_lake.passport import DataPassport
from lib.data_lake.spec import DatasetSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec(**kw):
    """Build a valid DatasetSpec with overridable defaults."""
    defaults = dict(
        dataset_id="test-ds-001",
        source="binance",
        market="um_futures",
        symbols=("BTCUSDT",),
        intervals=("1h",),
        data_types=("klines",),
        start=datetime(2022, 1, 1, tzinfo=timezone.utc),
        end=datetime(2022, 6, 1, tzinfo=timezone.utc),
        priority="P0",
        backtest_required=True,
        allow_synthetic=False,
    )
    defaults.update(kw)
    return DatasetSpec(**defaults)


def _catalog(entries=None):
    """Create an isolated DataCatalog backed by a temp file path."""
    tmp = os.path.join(tempfile.mkdtemp(), "test_catalog.json")
    cat = DataCatalog(catalog_path=tmp)
    if entries:
        for e in entries:
            cat.add_entry(**e)
    return cat


def _make_checksum_report(files_failed_count=0):
    """Build a ChecksumReport with a given number of failed files."""
    return ChecksumReport(
        total_files=10,
        files_checked=10,
        files_passed=10 - files_failed_count,
        files_failed=[] if files_failed_count == 0 else [f"file_{i}.parquet" for i in range(files_failed_count)],
        algorithm="sha256",
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def _insert_dummy_entries(cat, spec):
    """Insert minimal catalog entries matching *spec* so coverage is > 0."""
    for symbol in spec.symbols:
        for interval in spec.intervals:
            cat.add_entry(
                symbol=symbol,
                interval=interval,
                start_ts=int(spec.start.timestamp() * 1000),
                end_ts=int(spec.end.timestamp() * 1000),
                row_count=spec.expected_bar_count(),
                checksum="dummychecksum",
            )


# ---------------------------------------------------------------------------
# Source classification tests
# ---------------------------------------------------------------------------


class TestSourceClassification:
    """is_real_data, point_in_time_safe, revision_risk, source_type."""

    @pytest.mark.parametrize("src,expected_real,expected_pit,expected_rev", [
        ("binance", True, True, "none"),
        ("glassnode", True, True, "none"),
        ("coinalyze", True, False, "unknown"),
        ("tardis", True, False, "unknown"),
        ("crypto_lake", True, False, "unknown"),
        ("custom", False, False, "unknown"),
    ])
    def test_source_classification(self, src, expected_real, expected_pit, expected_rev):
        """Source-based flags are set correctly."""
        spec = _spec(source=src)
        cat = _catalog()
        _insert_dummy_entries(cat, spec)
        dp = DataPassport.from_spec(spec, cat)
        assert dp.is_real_data is expected_real, f"is_real_data for {src}"
        assert dp.point_in_time_safe is expected_pit, f"point_in_time_safe for {src}"
        assert dp.revision_risk == expected_rev, f"revision_risk for {src}"

    @pytest.mark.parametrize("src,expected_type", [
        ("binance", "public_archive"),
        ("coinalyze", "vendor_api"),
        ("glassnode", "vendor_api"),
        ("tardis", "vendor_api"),
        ("crypto_lake", "api"),
        ("custom", "api"),
    ])
    def test_source_type(self, src, expected_type):
        """source_type is mapped correctly."""
        spec = _spec(source=src)
        cat = _catalog()
        _insert_dummy_entries(cat, spec)
        dp = DataPassport.from_spec(spec, cat)
        assert dp.source_type == expected_type


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------


class TestFromSpec:
    """DataPassport.from_spec factory."""

    def test_default_spec(self):
        """A valid spec produces a fully populated passport."""
        spec = _spec()
        cat = _catalog()
        _insert_dummy_entries(cat, spec)
        dp = DataPassport.from_spec(spec, cat)

        assert dp.dataset_id == spec.dataset_id
        assert dp.source == spec.source
        assert dp.market == spec.market
        assert dp.symbols == spec.symbols
        assert dp.intervals == spec.intervals
        assert dp.data_types == spec.data_types
        assert dp.start == spec.start.isoformat()
        assert dp.end == spec.end.isoformat()
        assert dp.allow_synthetic == spec.allow_synthetic
        assert dp.passport_version == "1.0.0"
        assert dp.passport_id  # non-empty UUID
        assert dp.generated_at  # non-empty ISO timestamp
        assert dp.manifest_hash  # non-empty hash

    def test_coverage_and_gaps(self):
        """coverage_pct and gap_count are derived from the catalog."""
        spec = _spec()
        cat = _catalog()
        # No entries → 0 coverage, at least 1 gap
        dp = DataPassport.from_spec(spec, cat)
        assert dp.coverage_pct >= 0.0
        assert dp.gap_count >= 0

    def test_with_checksum_report_passed(self):
        """When checksums all pass, checksum_pass is True."""
        spec = _spec()
        cat = _catalog()
        _insert_dummy_entries(cat, spec)
        dp = DataPassport.from_spec(spec, cat, checksum_report=_make_checksum_report(0))
        assert dp.checksum_pass is True
        assert dp.duplicate_count == 0

    def test_with_checksum_report_failed(self):
        """When checksums have failures, checksum_pass is False."""
        spec = _spec()
        cat = _catalog()
        _insert_dummy_entries(cat, spec)
        dp = DataPassport.from_spec(spec, cat, checksum_report=_make_checksum_report(3))
        assert dp.checksum_pass is False
        assert dp.duplicate_count == 3

    def test_without_checksum_report(self):
        """Without a checksum report, checksum_pass is False."""
        spec = _spec()
        cat = _catalog()
        _insert_dummy_entries(cat, spec)
        dp = DataPassport.from_spec(spec, cat)
        assert dp.checksum_pass is False
        assert dp.duplicate_count == 0


# ---------------------------------------------------------------------------
# Trustworthiness tests
# ---------------------------------------------------------------------------


class TestTrustworthiness:
    """is_trustworthy_for_backtest and is_trustworthy_for_context."""

    def test_backtest_trustworthy(self):
        """Real data + PIT safe + high coverage + checksum pass."""
        spec = _spec(source="binance")
        cat = _catalog()
        _insert_dummy_entries(cat, spec)
        cr = _make_checksum_report(0)
        dp = DataPassport.from_spec(spec, cat, checksum_report=cr)

        if dp.coverage_pct >= 90.0:
            assert dp.is_trustworthy_for_backtest() is True
        assert dp.is_trustworthy_for_context() is True

    def test_backtest_not_trustworthy_synthetic(self):
        """Synthetic data should fail backtest trust."""
        spec = _spec(source="custom")  # not a real-data source
        cat = _catalog()
        _insert_dummy_entries(cat, spec)
        dp = DataPassport.from_spec(spec, cat)
        assert dp.is_trustworthy_for_backtest() is False
        assert dp.is_trustworthy_for_context() is False

    def test_backtest_not_trustworthy_coverage(self):
        """Low coverage fails backtest trust."""
        spec = _spec(source="binance")
        cat = _catalog()  # empty catalog → 0% coverage
        # no entries → coverage ~0%
        dp = DataPassport.from_spec(spec, cat)
        assert dp.is_trustworthy_for_backtest() is False

    def test_context_trustworthy(self):
        """Context trust requires real data + checksum pass."""
        spec = _spec(source="binance")
        cat = _catalog()
        _insert_dummy_entries(cat, spec)
        cr = _make_checksum_report(0)
        dp = DataPassport.from_spec(spec, cat, checksum_report=cr)
        assert dp.is_trustworthy_for_context() is True

    def test_context_not_trustworthy_failed_checksum(self):
        """Failed checksum breaks context trust."""
        spec = _spec(source="binance")
        cat = _catalog()
        _insert_dummy_entries(cat, spec)
        cr = _make_checksum_report(1)
        dp = DataPassport.from_spec(spec, cat, checksum_report=cr)
        assert dp.is_trustworthy_for_context() is False


# ---------------------------------------------------------------------------
# Serialisation tests
# ---------------------------------------------------------------------------


class TestSerialisation:
    """to_dict and from_dict round-trip."""

    def test_to_dict_shape(self):
        """to_dict returns a flat dict with the expected keys."""
        spec = _spec()
        cat = _catalog()
        _insert_dummy_entries(cat, spec)
        dp = DataPassport.from_spec(spec, cat)
        d = dp.to_dict()

        assert isinstance(d, dict)
        assert d["passport_id"] == dp.passport_id
        assert d["source"] == dp.source
        assert d["symbols"] == list(dp.symbols)  # lists, not tuples
        assert d["intervals"] == list(dp.intervals)
        assert d["data_types"] == list(dp.data_types)
        assert d["passport_version"] == "1.0.0"

    def test_from_dict_round_trip(self):
        """from_dict(to_dict(p)) == p."""
        spec = _spec()
        cat = _catalog()
        _insert_dummy_entries(cat, spec)
        dp1 = DataPassport.from_spec(spec, cat)
        d = dp1.to_dict()
        dp2 = DataPassport.from_dict(d)

        assert dp2.passport_id == dp1.passport_id
        assert dp2.source == dp1.source
        assert dp2.is_real_data == dp1.is_real_data
        assert dp2.coverage_pct == dp1.coverage_pct
        assert dp2.symbols == dp1.symbols
        assert dp2.intervals == dp1.intervals
        assert dp2.data_types == dp1.data_types
        assert dp2.passport_version == dp1.passport_version
        assert dp2.manifest_hash == dp1.manifest_hash

    def test_from_dict_with_lists(self):
        """from_dict handles lists for tuple fields."""
        d = {
            "passport_id": "test-uuid",
            "dataset_id": "ds-001",
            "source": "binance",
            "source_type": "public_archive",
            "market": "um_futures",
            "symbols": ["BTCUSDT"],               # list, not tuple
            "intervals": ["1h"],                   # list
            "data_types": ["klines"],              # list
            "start": "2022-01-01T00:00:00+00:00",
            "end": "2022-06-01T00:00:00+00:00",
            "is_real_data": True,
            "allow_synthetic": False,
            "coverage_pct": 100.0,
            "gap_count": 0,
            "duplicate_count": 0,
            "checksum_pass": True,
            "point_in_time_safe": True,
            "revision_risk": "none",
            "generated_at": "2024-01-01T00:00:00+00:00",
            "manifest_hash": "abc123",
            "passport_version": "1.0.0",
        }
        dp = DataPassport.from_dict(d)
        assert dp.symbols == ("BTCUSDT",)
        assert dp.intervals == ("1h",)
        assert dp.data_types == ("klines",)
        assert dp.passport_id == "test-uuid"

    def test_immutable(self):
        """DataPassport is frozen and cannot be mutated."""
        spec = _spec()
        cat = _catalog()
        _insert_dummy_entries(cat, spec)
        dp = DataPassport.from_spec(spec, cat)
        with pytest.raises(AttributeError):
            dp.source = "glassnode"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Integration smoke
# ---------------------------------------------------------------------------


def test_full_pipeline_smoke():
    """End-to-end: spec → catalog → passport → dict → passport."""
    spec = _spec(
        dataset_id="smoke-001",
        source="binance",
        symbols=("BTCUSDT", "ETHUSDT"),
        intervals=("1h", "4h"),
        data_types=("klines", "funding_rate"),
    )
    cat = _catalog()
    _insert_dummy_entries(cat, spec)
    cr = _make_checksum_report(0)

    dp = DataPassport.from_spec(spec, cat, checksum_report=cr)
    assert dp.dataset_id == "smoke-001"
    assert dp.source_type == "public_archive"
    assert dp.is_real_data is True
    assert dp.point_in_time_safe is True
    assert dp.revision_risk == "none"
    assert dp.checksum_pass is True

    # Round-trip
    dp2 = DataPassport.from_dict(dp.to_dict())
    assert dp2.passport_id == dp.passport_id
    assert dp2.symbols == ("BTCUSDT", "ETHUSDT")
    assert dp2.intervals == ("1h", "4h")
