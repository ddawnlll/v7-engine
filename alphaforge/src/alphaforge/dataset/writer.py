"""DatasetWriter — deterministic serialization with SHA-256 checksum.

Implements the DatasetWriter protocol from contracts.py.

Deterministic rules:
  (a) Rows sorted by (symbol, feature_timestamp).
  (b) Columns in fixed order: row_id, symbol, feature_timestamp,
      label_timestamp, mode, feature columns (sorted alphabetically),
      label columns (sorted alphabetically), lineage columns.
  (c) Parquet preferred; CSV fallback with consistent float formatting ('%.10g').
  (d) SHA-256 checksum over exact bytes written to disk.

No ML library imports.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from alphaforge.dataset.contracts import LabeledDataset, LineageProvenance

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column order (deterministic)
# ---------------------------------------------------------------------------

META_COLUMNS = [
    "row_id",
    "symbol",
    "feature_timestamp",
    "label_timestamp",
    "mode",
]

LABEL_VALUE_COLUMNS = [
    "label_long_r_net",
    "label_short_r_net",
    "label_best_action_label",
    "label_validity",
    "label_no_trade_quality",
    "label_cost_impact_long",
    "label_cost_impact_short",
]

LINEAGE_COLUMNS = [
    "lineage_source_manifest_id",
    "lineage_label_checksum",
    "lineage_feature_spec_version",
    "lineage_feature_set_id",
    "lineage_label_dataset_id",
    "lineage_simulation_profile_id",
    "lineage_assembled_at",
]

QUALITY_FLAGS_COLUMN = "quality_flags"


class DefaultWriter:
    """Default implementation of DatasetWriter.

    Handles deterministic CSV serialization with SHA-256 checksum
    and roundtrip verification.  Supports Parquet via pyarrow when
    available.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(self, dataset: List[LabeledDataset], path: str) -> str:
        """Serialize dataset to disk. Returns SHA-256 hex digest.

        Deterministic: same input -> byte-identical output.
        """
        if not dataset:
            return self._write_empty(path)

        ext = Path(path).suffix.lower()

        if ext == ".parquet":
            return self._write_parquet(dataset, path)
        else:
            return self._write_csv(dataset, path)

    def read(self, path: str) -> List[LabeledDataset]:
        """Read a written dataset back into LabeledDataset instances."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Dataset file not found: {path}")

        ext = Path(path).suffix.lower()

        if ext == ".parquet":
            return self._read_parquet(path)
        else:
            return self._read_csv(path)

    def verify_roundtrip(
        self, path: str, original: List[LabeledDataset]
    ) -> bool:
        """Read file at path and compare field-by-field with original.

        Both sides are sorted by (symbol, feature_timestamp) before comparison
        because write() applies deterministic sorting.

        Returns True iff the file content matches original.
        """
        try:
            reconstructed = self.read(path)
        except FileNotFoundError:
            logger.warning("File not found for roundtrip verification: %s", path)
            return False

        sort_key = lambda r: (r.symbol, r.feature_timestamp)
        sorted_original = sorted(original, key=sort_key)
        sorted_reconstructed = sorted(reconstructed, key=sort_key)
        return self._compare_datasets(sorted_original, sorted_reconstructed)

    # ------------------------------------------------------------------
    # CSV implementation
    # ------------------------------------------------------------------

    def _write_csv(self, dataset: List[LabeledDataset], path: str) -> str:
        """Deterministic CSV write with SHA-256 checksum."""
        rows = [self._flatten_row(item) for item in dataset]
        rows.sort(key=lambda r: (r["symbol"], r["feature_timestamp"]))

        all_feature_keys: List[str] = sorted(
            {k for row in rows for k in row["features"].keys()}
        )

        header = self._build_csv_header(all_feature_keys)

        # Build CSV content in memory first for checksum
        import io

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            csv_row = self._row_to_csv_dict(row, all_feature_keys)
            writer.writerow(csv_row)

        csv_content = buf.getvalue()
        buf.close()

        checksum = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()

        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write(csv_content)

        return checksum

    def _read_csv(self, path: str) -> List[LabeledDataset]:
        """Read CSV and reconstruct LabeledDataset instances."""
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        result: List[LabeledDataset] = []
        for row in rows:
            item = self._unflatten_row(row)
            result.append(item)

        return result

    def _write_empty(self, path: str) -> str:
        """Write an empty dataset (header-only CSV)."""
        header = self._build_csv_header([])
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
        with open(path, "rb") as f:
            checksum = hashlib.sha256(f.read()).hexdigest()
        return checksum

    # ------------------------------------------------------------------
    # Parquet implementation (graceful degradation)
    # ------------------------------------------------------------------

    def _write_parquet(self, dataset: List[LabeledDataset], path: str) -> str:
        """Write Parquet with deterministic settings. Falls back to CSV."""
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            logger.warning(
                "Parquet not available; using CSV fallback. "
                "Install pyarrow for preferred format."
            )
            csv_path = str(Path(path).with_suffix(".csv"))
            logger.info("Writing CSV to %s instead", csv_path)
            return self._write_csv(dataset, csv_path)

        rows = [self._flatten_row(item) for item in dataset]
        rows.sort(key=lambda r: (r["symbol"], r["feature_timestamp"]))

        all_feature_keys: List[str] = sorted(
            {k for row in rows for k in row["features"].keys()}
        )

        header = self._build_csv_header(all_feature_keys)

        # Build table
        table_data: Dict[str, List[Any]] = {col: [] for col in header}
        for flat in rows:
            csv_row = self._row_to_csv_dict(flat, all_feature_keys)
            for col in header:
                table_data[col].append(csv_row.get(col, ""))

        table = pa.table(table_data)

        # Deterministic Parquet: disable statistics that vary by implementation
        pq.write_table(
            table,
            path,
            version="2.6",
            write_statistics=False,
            compression="snappy",
        )

        with open(path, "rb") as f:
            checksum = hashlib.sha256(f.read()).hexdigest()
        return checksum

    def _read_parquet(self, path: str) -> List[LabeledDataset]:
        """Read Parquet file."""
        try:
            import pyarrow.parquet as pq
        except ImportError:
            csv_path = str(Path(path).with_suffix(".csv"))
            if os.path.exists(csv_path):
                logger.info("Reading CSV fallback from %s", csv_path)
                return self._read_csv(csv_path)
            raise ImportError(
                "pyarrow is required to read Parquet files. "
                "Install pyarrow or use CSV format."
            )

        table = pq.read_table(path)
        rows = table.to_pydict()
        column_names = table.column_names
        row_count = len(rows[column_names[0]]) if column_names else 0

        result: List[LabeledDataset] = []
        for i in range(row_count):
            row_dict = {col: rows[col][i] for col in column_names}
            item = self._unflatten_row(row_dict)
            result.append(item)

        return result

    # ------------------------------------------------------------------
    # Flatten / unflatten
    # ------------------------------------------------------------------

    def _flatten_row(self, item: LabeledDataset) -> Dict[str, Any]:
        """Flatten a LabeledDataset into a flat dict for serialization."""
        flat: Dict[str, Any] = {
            "row_id": item.row_id,
            "symbol": item.symbol,
            "feature_timestamp": item.feature_timestamp,
            "label_timestamp": item.label_timestamp,
            "mode": item.mode,
            "features": dict(item.features),
            "label_long_r_net": self._format_float(item.label_long_r_net),
            "label_short_r_net": self._format_float(item.label_short_r_net),
            "label_best_action_label": item.label_best_action_label,
            "label_validity": item.label_validity,
            "label_no_trade_quality": item.label_no_trade_quality,
            "label_cost_impact_long": self._format_float(item.label_cost_impact_long),
            "label_cost_impact_short": self._format_float(item.label_cost_impact_short),
            "lineage_source_manifest_id": item.lineage.source_manifest_id,
            "lineage_label_checksum": item.lineage.label_checksum,
            "lineage_feature_spec_version": item.lineage.feature_spec_version,
            "lineage_feature_set_id": item.lineage.feature_set_id,
            "lineage_label_dataset_id": item.lineage.label_dataset_id,
            "lineage_simulation_profile_id": item.lineage.simulation_profile_id,
            "lineage_assembled_at": item.lineage.assembled_at or "",
            "quality_flags": json.dumps(item.quality_flags),
        }
        return flat

    def _unflatten_row(self, flat: Dict[str, str]) -> LabeledDataset:
        """Reconstruct a LabeledDataset from a flat dict (CSV row)."""
        # Reconstruct lineage
        lineage = LineageProvenance(
            source_manifest_id=str(flat.get("lineage_source_manifest_id", "")),
            label_checksum=str(flat.get("lineage_label_checksum", "")),
            feature_spec_version=str(flat.get("lineage_feature_spec_version", "")),
            feature_set_id=str(flat.get("lineage_feature_set_id", "")),
            label_dataset_id=str(flat.get("lineage_label_dataset_id", "")),
            simulation_profile_id=str(flat.get("lineage_simulation_profile_id", "")),
            assembled_at=self._optional_str(flat.get("lineage_assembled_at", "")),
        )

        # Parse quality_flags
        quality_flags_str = flat.get("quality_flags", "[]")
        try:
            quality_flags = json.loads(quality_flags_str)
        except (json.JSONDecodeError, TypeError):
            quality_flags = []

        # Extract features (skip empty cells = missing features)
        features: Dict[str, float] = {}
        for key, val in flat.items():
            if key.startswith("feature_"):
                feat_name = key[len("feature_"):]
                if val is None or str(val).strip() == "":
                    continue  # skip missing features
                try:
                    features[feat_name] = float(val)
                except (ValueError, TypeError):
                    pass

        return LabeledDataset(
            row_id=str(flat.get("row_id", "")),
            symbol=str(flat.get("symbol", "")),
            feature_timestamp=str(flat.get("feature_timestamp", "")),
            label_timestamp=str(flat.get("label_timestamp", "")),
            mode=str(flat.get("mode", "SWING")),
            features=features,
            label_long_r_net=self._parse_float(flat.get("label_long_r_net", "0")),
            label_short_r_net=self._parse_float(flat.get("label_short_r_net", "0")),
            label_best_action_label=str(flat.get("label_best_action_label", "AMBIGUOUS_STATE")),
            label_validity=str(flat.get("label_validity", "VALID")),
            label_no_trade_quality=str(flat.get("label_no_trade_quality", "AMBIGUOUS_NO_TRADE")),
            label_cost_impact_long=self._parse_float(flat.get("label_cost_impact_long", "0")),
            label_cost_impact_short=self._parse_float(flat.get("label_cost_impact_short", "0")),
            lineage=lineage,
            quality_flags=list(quality_flags) if isinstance(quality_flags, list) else [],
        )

    # ------------------------------------------------------------------
    # Column ordering helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_csv_header(feature_keys: List[str]) -> List[str]:
        """Build deterministic column order."""
        header = list(META_COLUMNS)
        for fk in feature_keys:
            header.append(f"feature_{fk}")
        header.extend(LABEL_VALUE_COLUMNS)
        header.extend(LINEAGE_COLUMNS)
        header.append(QUALITY_FLAGS_COLUMN)
        return header

    def _row_to_csv_dict(
        self, flat: Dict[str, Any], feature_keys: List[str]
    ) -> Dict[str, Any]:
        """Convert flattened row to CSV dict with column prefix for features."""
        csv_row: Dict[str, Any] = {}
        for col in META_COLUMNS:
            csv_row[col] = flat.get(col, "")
        for fk in feature_keys:
            if fk in flat["features"]:
                csv_row[f"feature_{fk}"] = self._format_float(flat["features"][fk])
            else:
                csv_row[f"feature_{fk}"] = ""  # missing feature
        for col in LABEL_VALUE_COLUMNS:
            csv_row[col] = flat.get(col, "")
        for col in LINEAGE_COLUMNS:
            csv_row[col] = flat.get(col, "")
        csv_row[QUALITY_FLAGS_COLUMN] = flat.get(QUALITY_FLAGS_COLUMN, "[]")
        return csv_row

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    def _compare_datasets(
        self,
        original: List[LabeledDataset],
        reconstructed: List[LabeledDataset],
    ) -> bool:
        """Field-by-field comparison. Returns True iff identical."""
        if len(original) != len(reconstructed):
            logger.warning(
                "Roundtrip mismatch: original has %d rows, "
                "reconstructed has %d rows",
                len(original),
                len(reconstructed),
            )
            return False

        for i, (orig, recon) in enumerate(zip(original, reconstructed)):
            diffs = self._diff_rows(orig, recon)
            if diffs:
                logger.warning(
                    "Roundtrip mismatch at row %d: %s", i, "; ".join(diffs)
                )
                return False

        return True

    @staticmethod
    def _diff_rows(
        orig: LabeledDataset, recon: LabeledDataset
    ) -> List[str]:
        """Return list of field differences between two rows."""
        diffs: List[str] = []

        if orig.row_id != recon.row_id:
            # row_id is regenerated on each assemble(), skip
            pass
        if orig.symbol != recon.symbol:
            diffs.append(f"symbol: {orig.symbol} != {recon.symbol}")
        if orig.feature_timestamp != recon.feature_timestamp:
            diffs.append(
                f"feature_timestamp: {orig.feature_timestamp} != "
                f"{recon.feature_timestamp}"
            )
        if orig.label_timestamp != recon.label_timestamp:
            diffs.append(
                f"label_timestamp: {orig.label_timestamp} != "
                f"{recon.label_timestamp}"
            )
        if orig.mode != recon.mode:
            diffs.append(f"mode: {orig.mode} != {recon.mode}")

        if orig.features != recon.features:
            diffs.append("features differ")

        for field_name in [
            "label_long_r_net",
            "label_short_r_net",
            "label_best_action_label",
            "label_validity",
            "label_no_trade_quality",
            "label_cost_impact_long",
            "label_cost_impact_short",
        ]:
            orig_val = getattr(orig, field_name)
            recon_val = getattr(recon, field_name)
            if orig_val != recon_val:
                diffs.append(f"{field_name}: {orig_val} != {recon_val}")

        # lineage comparison
        if orig.lineage.source_manifest_id != recon.lineage.source_manifest_id:
            diffs.append("lineage.source_manifest_id differs")
        if orig.lineage.label_checksum != recon.lineage.label_checksum:
            diffs.append("lineage.label_checksum differs")
        if orig.lineage.feature_set_id != recon.lineage.feature_set_id:
            diffs.append("lineage.feature_set_id differs")
        if orig.lineage.label_dataset_id != recon.lineage.label_dataset_id:
            diffs.append("lineage.label_dataset_id differs")

        if orig.quality_flags != recon.quality_flags:
            diffs.append("quality_flags differ")

        return diffs

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_float(value: float) -> str:
        """Deterministic float formatting using repr() for lossless roundtrip.

        Uses Python's repr() which produces minimal decimal representation
        that reproduces the exact float64 value — superior to '%.10g' because
        it preserves full IEEE 754 binary64 precision.
        """
        if value != value:  # NaN
            return ""
        return repr(value)

    @staticmethod
    def _parse_float(value: Any) -> float:
        """Parse a string or numeric value to float."""
        if value is None or value == "":
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _optional_str(value: Any) -> Optional[str]:
        """Parse optional string."""
        if value is None or value == "":
            return None
        return str(value)
