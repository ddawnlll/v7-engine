"""Outcome cache writer: buffer and flush trade outcomes to partitioned Parquet."""

from pathlib import Path
import pandas as pd
import threading
import uuid
from datetime import datetime
from typing import Optional

from .schema import OutcomeRecord, OUTCOME_CACHE_SCHEMA_V1


class OutcomeCacheWriter:
    """Thread-safe, buffered Parquet writer for trade outcomes.

    Writes partitioned by symbol (Hive-style: symbol=BTCUSDT/).
    Flushes automatically at threshold or on explicit close.
    """

    def __init__(
        self,
        base_path: str = "data/outcome_cache/v1",
        flush_threshold: int = 10_000,
    ):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._flush_threshold = flush_threshold
        self._buffer: list[dict] = []
        self._buffer_size = 0
        self._lock = threading.Lock()
        self._closed = False
        self._total_written = 0

    def append(self, records: list[OutcomeRecord]) -> int:
        """Append outcome records, returning count of new records."""
        validated = []
        for rec in records:
            errs = rec.validate()
            if errs:
                raise ValueError(f"Validation failed for {rec.candidate_id}: {errs}")
            validated.append(rec.to_dict())

        with self._lock:
            self._buffer.extend(validated)
            self._buffer_size += len(validated)

        if self._buffer_size >= self._flush_threshold:
            self.flush()
        return len(validated)

    def append_dataframe(self, df: pd.DataFrame, alpha_id: str = "unknown",
                         run_id: str = "") -> int:
        """Append records from a DataFrame, auto-converting columns."""
        records = []
        for _, row in df.iterrows():
            rec = OutcomeRecord(
                alpha_id=alpha_id,
                run_id=run_id,
                symbol=str(row.get("symbol", "")),
                entry_bar=int(row.get("entry_bar", 0)),
                direction=str(row.get("side", row.get("direction", ""))),
                entry_price=float(row.get("entry_price", 0.0)),
                stop_price=float(row.get("stop_price", 0.0)),
                target_price=float(row.get("target_price", 0.0)),
                exit_bar=int(row.get("exit_bar", 0)),
                exit_reason=str(row.get("exit_reason", "")),
                gross_R=float(row.get("gross_R", 0.0)),
                net_R=float(row.get("net_R", 0.0)),
                fee_R=float(row.get("cost_R", row.get("fee_R", 0.0))),
                source_file="",
                config_hash="",
            )
            # Map regime
            regime_str = str(row.get("regime_trend", ""))
            regime_map = {"up": 1, "down": 2, "range": 3, "trend": 1, "chop": 4}
            rec.regime_id = regime_map.get(regime_str, 0)

            # Map volatility percentile to bucket
            vol = float(row.get("volatility_percentile", 50))
            if vol < 25:
                rec.volatility_bucket = 1
            elif vol < 50:
                rec.volatility_bucket = 2
            elif vol < 75:
                rec.volatility_bucket = 3
            else:
                rec.volatility_bucket = 4

            # Map spread proxy to bucket
            spread = float(row.get("spread_proxy", 50))
            if spread < 0.1:
                rec.spread_bucket = 1
            elif spread < 0.3:
                rec.spread_bucket = 2
            elif spread < 0.6:
                rec.spread_bucket = 3
            else:
                rec.spread_bucket = 4

            rec.session_bucket = "unknown"
            records.append(rec)
        return self.append(records)

    def flush(self):
        """Flush buffered records to partitioned Parquet files."""
        if self._buffer_size == 0:
            return
        with self._lock:
            buf = self._buffer[:]
            self._buffer.clear()
            self._buffer_size = 0

        if not buf:
            return

        df = pd.DataFrame(buf)
        for col in ("entry_time", "exit_time"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")

        for symbol, group in df.groupby("symbol"):
            part_dir = self.base_path / f"symbol={symbol}"
            part_dir.mkdir(parents=True, exist_ok=True)
            part_file = part_dir / f"part-{uuid.uuid4().hex[:12]}.parquet"
            group.to_parquet(
                part_file,
                index=False,
                schema=OUTCOME_CACHE_SCHEMA_V1,
                version="2.6",
            )
        self._total_written += len(buf)

    def close(self):
        """Flush remaining records and mark writer as closed."""
        self.flush()
        self._closed = True
        self._write_metadata()

    def _write_metadata(self):
        """Write _metadata.json with summary stats."""
        import json
        meta = {
            "schema_version": "1.0.0",
            "created": datetime.utcnow().isoformat(),
            "total_records": self._total_written,
            "partitioned_by": "symbol",
        }
        meta_path = self.base_path / "_metadata.json"
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

    @property
    def total_written(self) -> int:
        return self._total_written
