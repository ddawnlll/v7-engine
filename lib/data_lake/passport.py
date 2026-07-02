"""
DataPassport --- immutable quality passport for a dataset.

A DataPassport records provenance, coverage, and trustworthiness metadata
for a dataset at a point in time.  It is the canonical artifact used by
the evidence engine to gate claims that require real, verified data.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from lib.data_lake.catalog import DataCatalog
from lib.data_lake.checksum import ChecksumReport
from lib.data_lake.spec import DatasetSpec

# ---------------------------------------------------------------------------
# Source classification helpers
# ---------------------------------------------------------------------------

# Sources that represent real (non-synthetic) market data.
_REAL_DATA_SOURCES: frozenset[str] = frozenset({
    "binance",
    "coinalyze",
    "glassnode",
    "tardis",
    "crypto_lake",
})

# Sources that are point-in-time safe (data is not revised or restated).
_PIT_SAFE_SOURCES: frozenset[str] = frozenset({
    "binance",
    "glassnode",
})

# Sources with no revision risk.
_NO_REVISION_RISK_SOURCES: frozenset[str] = frozenset({
    "binance",
    "glassnode",
})

_SOURCE_TYPE_MAP: dict[str, str] = {
    "binance": "public_archive",
    "coinalyze": "vendor_api",
    "glassnode": "vendor_api",
    "tardis": "vendor_api",
    "crypto_lake": "api",
    "custom": "api",
}


# ---------------------------------------------------------------------------
# DataPassport
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DataPassport:
    """Immutable quality passport for a dataset.

    Attributes
    ----------
    passport_id:
        UUID string identifying this passport instance.
    dataset_id:
        Identifier of the originating :class:`DatasetSpec`.
    source:
        Data source name (e.g. ``"binance"``).
    source_type:
        Category of source: ``"public_archive"`` | ``"api"`` | ``"vendor_api"``.
    market:
        Market type (e.g. ``"um_futures"``).
    symbols:
        Trading pairs covered.
    intervals:
        Candle intervals covered.
    data_types:
        Data type names (e.g. ``"klines"``, ``"funding_rate"``).
    start:
        ISO-8601 string for the inclusive start of the dataset range.
    end:
        ISO-8601 string for the exclusive end of the dataset range.
    is_real_data:
        Whether the source provides real (non-synthetic) market data.
    allow_synthetic:
        Whether synthetic fallback is permitted.
    coverage_pct:
        Percentage of expected bars present in the catalog.
    gap_count:
        Number of time-range gaps found in the coverage analysis.
    duplicate_count:
        Number of duplicate entries detected (e.g. from checksum
        analysis).
    checksum_pass:
        Whether all file checksums verified successfully.
    point_in_time_safe:
        Whether the source guarantees point-in-time data (no
        retrospective revisions).
    revision_risk:
        Level of revision risk: ``"none"`` | ``"low"`` | ``"medium"`` |
        ``"high"`` | ``"unknown"``.
    generated_at:
        ISO-8601 timestamp of when this passport was created.
    manifest_hash:
        SHA-256 hash covering the spec identity and catalog summary at
        the time of creation.
    passport_version:
        Version string for schema tracking (default ``"1.0.0"``).
    """

    passport_id: str
    dataset_id: str
    source: str
    source_type: str
    market: str
    symbols: tuple[str, ...]
    intervals: tuple[str, ...]
    data_types: tuple[str, ...]
    start: str
    end: str
    is_real_data: bool
    allow_synthetic: bool
    coverage_pct: float
    gap_count: int
    duplicate_count: int
    checksum_pass: bool
    point_in_time_safe: bool
    revision_risk: str
    generated_at: str
    manifest_hash: str
    passport_version: str = "1.0.0"

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_spec(
        cls,
        spec: DatasetSpec,
        catalog: DataCatalog,
        checksum_report: ChecksumReport | None = None,
    ) -> DataPassport:
        """Build a :class:`DataPassport` from a :class:`DatasetSpec` and
        :class:`DataCatalog`.

        Parameters
        ----------
        spec:
            The dataset specification to passport.
        catalog:
            The catalog of ingested data used to compute coverage and
            gap counts.
        checksum_report:
            Optional :class:`ChecksumReport`.  When provided, the
            passport's ``checksum_pass`` and ``duplicate_count``
            fields are derived from it.

        Returns
        -------
        DataPassport
        """
        now = datetime.now(timezone.utc)
        source = spec.source

        # ------------------------------------------------------------------
        # Source classification
        # ------------------------------------------------------------------
        source_type = _SOURCE_TYPE_MAP.get(source, "api")
        is_real_data = source in _REAL_DATA_SOURCES
        point_in_time_safe = source in _PIT_SAFE_SOURCES
        revision_risk = (
            "none" if source in _NO_REVISION_RISK_SOURCES else "unknown"
        )

        # ------------------------------------------------------------------
        # Coverage from catalog
        # ------------------------------------------------------------------
        coverage_pct = catalog.coverage_pct(spec)
        gap_count = len(catalog.find_gaps(spec))

        # ------------------------------------------------------------------
        # Checksum-derived fields
        # ------------------------------------------------------------------
        if checksum_report is not None:
            checksum_pass = len(checksum_report.files_failed) == 0
            duplicate_count = max(
                0,
                checksum_report.files_checked - checksum_report.files_passed,
            )
        else:
            checksum_pass = False
            duplicate_count = 0

        # ------------------------------------------------------------------
        # Manifest hash: reproducible from the same spec + catalog state
        # ------------------------------------------------------------------
        summary = catalog.to_summary(spec)
        hash_parts = [
            spec.dataset_id,
            spec.source,
            spec.market,
            str(spec.symbols),
            str(spec.intervals),
            str(spec.data_types),
            spec.start.isoformat(),
            spec.end.isoformat(),
            str(summary.get("coverage_pct", coverage_pct)),
            str(summary.get("gap_count", gap_count)),
        ]
        hash_input = "|".join(hash_parts)
        manifest_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        return cls(
            passport_id=str(uuid.uuid4()),
            dataset_id=spec.dataset_id,
            source=source,
            source_type=source_type,
            market=spec.market,
            symbols=spec.symbols,
            intervals=spec.intervals,
            data_types=spec.data_types,
            start=spec.start.isoformat(),
            end=spec.end.isoformat(),
            is_real_data=is_real_data,
            allow_synthetic=spec.allow_synthetic,
            coverage_pct=coverage_pct,
            gap_count=gap_count,
            duplicate_count=duplicate_count,
            checksum_pass=checksum_pass,
            point_in_time_safe=point_in_time_safe,
            revision_risk=revision_risk,
            generated_at=now.isoformat(),
            manifest_hash=manifest_hash,
            passport_version="1.0.0",
        )

    # ------------------------------------------------------------------
    # Trustworthiness checks
    # ------------------------------------------------------------------

    def is_trustworthy_for_backtest(self) -> bool:
        """Whether this passport's data is trustworthy for backtesting.

        Returns ``True`` when the data is real, point-in-time safe, has
        >= 90 % coverage, and passed checksum verification.
        """
        return (
            self.is_real_data
            and self.point_in_time_safe
            and self.coverage_pct >= 90.0
            and self.checksum_pass
        )

    def is_trustworthy_for_context(self) -> bool:
        """Whether this passport's data is trustworthy for research context.

        Returns ``True`` when the data is real and passed checksum
        verification.
        """
        return self.is_real_data and self.checksum_pass

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe ``dict`` representation of this passport."""
        return {
            "passport_id": self.passport_id,
            "dataset_id": self.dataset_id,
            "source": self.source,
            "source_type": self.source_type,
            "market": self.market,
            "symbols": list(self.symbols),
            "intervals": list(self.intervals),
            "data_types": list(self.data_types),
            "start": self.start,
            "end": self.end,
            "is_real_data": self.is_real_data,
            "allow_synthetic": self.allow_synthetic,
            "coverage_pct": self.coverage_pct,
            "gap_count": self.gap_count,
            "duplicate_count": self.duplicate_count,
            "checksum_pass": self.checksum_pass,
            "point_in_time_safe": self.point_in_time_safe,
            "revision_risk": self.revision_risk,
            "generated_at": self.generated_at,
            "manifest_hash": self.manifest_hash,
            "passport_version": self.passport_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DataPassport:
        """Restore a :class:`DataPassport` from a ``dict``.

        This is the inverse of :meth:`to_dict`.  List-typed fields
        (``symbols``, ``intervals``, ``data_types``) are automatically
        converted back to tuples.

        Parameters
        ----------
        data:
            Dictionary representation as produced by :meth:`to_dict`.

        Returns
        -------
        DataPassport
        """
        data = dict(data)  # shallow copy to avoid mutating the input
        for lst_field in ("symbols", "intervals", "data_types"):
            if isinstance(data.get(lst_field), list):
                data[lst_field] = tuple(data[lst_field])
        return cls(**data)
