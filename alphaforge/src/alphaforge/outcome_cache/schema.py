"""Outcome cache schema definitions."""

import pyarrow as pa
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
import uuid

OUTCOME_CACHE_SCHEMA_V1 = pa.schema([
    pa.field("candidate_id", pa.string()),
    pa.field("alpha_id", pa.string()),
    pa.field("run_id", pa.string()),
    pa.field("symbol", pa.string()),
    pa.field("entry_time", pa.timestamp("ms")),
    pa.field("entry_bar", pa.int64()),
    pa.field("direction", pa.string()),
    pa.field("entry_price", pa.float64()),
    pa.field("stop_price", pa.float64()),
    pa.field("target_price", pa.float64()),
    pa.field("exit_time", pa.timestamp("ms")),
    pa.field("exit_bar", pa.int64()),
    pa.field("exit_reason", pa.string()),
    pa.field("gross_R", pa.float64()),
    pa.field("fee_R", pa.float64()),
    pa.field("spread_R", pa.float64()),
    pa.field("slippage_R", pa.float64()),
    pa.field("net_R", pa.float64()),
    pa.field("regime_id", pa.int64()),
    pa.field("spread_bucket", pa.int64()),
    pa.field("volume_bucket", pa.int64()),
    pa.field("volatility_bucket", pa.int64()),
    pa.field("session_bucket", pa.string()),
    pa.field("source_file", pa.string()),
    pa.field("config_hash", pa.string()),
])

REQUIRED_FIELDS = ["alpha_id", "symbol", "entry_bar", "direction", "net_R"]
INDEX_FIELDS = ["alpha_id", "symbol", "entry_bar"]


@dataclass
class OutcomeRecord:
    """One candidate trade outcome for caching."""
    candidate_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    alpha_id: str = ""
    run_id: str = ""
    symbol: str = ""
    entry_time: Optional[datetime] = None
    entry_bar: int = 0
    direction: str = ""
    entry_price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    exit_time: Optional[datetime] = None
    exit_bar: int = 0
    exit_reason: str = ""
    gross_R: float = 0.0
    fee_R: float = 0.0
    spread_R: float = 0.0
    slippage_R: float = 0.0
    net_R: float = 0.0
    regime_id: int = 0
    spread_bucket: int = 0
    volume_bucket: int = 0
    volatility_bucket: int = 0
    session_bucket: str = ""
    source_file: str = ""
    config_hash: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("entry_time", "exit_time"):
            if isinstance(d.get(k), datetime):
                d[k] = d[k].isoformat()
        return d

    def validate(self) -> list[str]:
        errors = []
        for f in REQUIRED_FIELDS:
            val = getattr(self, f, None)
            if val is None or (isinstance(val, str) and val == ""):
                errors.append(f"Missing required field: {f}")
        return errors


def record_from_dataframe_row(row) -> OutcomeRecord:
    """Convert a pandas Series or dict row to OutcomeRecord."""
    data = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
    rec = OutcomeRecord(
        alpha_id=data.get("alpha_id", "unknown"),
        run_id=data.get("run_id", ""),
        symbol=data.get("symbol", ""),
        entry_bar=int(data.get("entry_bar", 0)),
        direction=data.get("direction", data.get("side", "")),
        entry_price=float(data.get("entry_price", 0.0)),
        stop_price=float(data.get("stop_price", 0.0)),
        target_price=float(data.get("target_price", 0.0)),
        exit_bar=int(data.get("exit_bar", 0)),
        exit_reason=data.get("exit_reason", ""),
        gross_R=float(data.get("gross_R", 0.0)),
        net_R=float(data.get("net_R", 0.0)),
    )
    # Optional fields
    for opt_field in ["fee_R", "spread_R", "slippage_R", "regime_id",
                       "spread_bucket", "volume_bucket", "volatility_bucket",
                       "session_bucket", "source_file", "config_hash"]:
        if opt_field in data:
            setattr(rec, opt_field, data[opt_field])
    # Map common field names
    if "cost_R" in data and rec.fee_R == 0.0:
        rec.fee_R = float(data["cost_R"])
    if not rec.session_bucket:
        rec.session_bucket = "unknown"
    return rec


METADATA_SCHEMA = {
    "schema_version": "1.0.0",
    "fields": len(OUTCOME_CACHE_SCHEMA_V1),
    "field_names": [f.name for f in OUTCOME_CACHE_SCHEMA_V1],
}
