# Outcome Cache P0 Implementation Plan

**Status:** `PLAN_COMPLETE` — ready for implementation
**Generated:** 2026-07-08
**Estimated effort:** 4-6 hours for P0

---

## Objective

Build a minimal CPU outcome cache that:
1. Accepts per-trade outcome records from any alpha run
2. Stores them in partitioned Parquet format
3. Enables fast lookup by (alpha_id, symbol)
4. Supports basic filtering queries
5. Provides the caching layer for V7-Lite's candidate comparison

---

## Implementation Steps

### Step 1: Schema Definition (0.5h)

Create `alphaforge/src/alphaforge/outcome_cache/schema.py`:

```python
from dataclasses import dataclass
from datetime import datetime
import pyarrow as pa

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
```

### Step 2: Writer Implementation (1.5h)

Create `alphaforge/src/alphaforge/outcome_cache/writer.py`:

```python
class OutcomeCacheWriter:
    def __init__(self, base_path: str = "data/outcome_cache/v1"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._buffer: list[dict] = []
        self._buffer_size = 0
        self._flush_threshold = 10_000
        self._lock = threading.Lock()

    def append(self, alpha_id: str, outcomes: list[OutcomeRecord]) -> int:
        """Append outcomes, return count of new records."""
        validated = [self._validate(o) for o in outcomes]
        with self._lock:
            self._buffer.extend(validated)
            self._buffer_size += len(validated)
        if self._buffer_size >= self._flush_threshold:
            self.flush()
        return len(validated)

    def flush(self):
        """Flush buffer to parquet files."""
        if not self._buffer:
            return
        df = pd.DataFrame(self._buffer)
        for symbol, group in df.groupby("symbol"):
            path = self.base_path / f"symbol={symbol}" / f"part-{uuid4().hex[:8]}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            group.to_parquet(path, index=False, schema=OUTCOME_CACHE_SCHEMA_V1)
        self._buffer.clear()
        self._buffer_size = 0
        self._update_metadata()
```

### Step 3: Reader Implementation (1h)

Create `alphaforge/src/alphaforge/outcome_cache/reader.py`:

```python
class OutcomeCacheReader:
    def __init__(self, base_path: str = "data/outcome_cache/v1"):
        self.base_path = Path(base_path)

    def get_outcomes(self, alpha_id: str, symbol: str = None) -> pd.DataFrame:
        """Load all outcomes for an alpha, optionally filtered by symbol."""
        if symbol:
            path = self.base_path / f"symbol={symbol}"
            if not path.exists():
                return pd.DataFrame()
            files = list(path.glob("*.parquet"))
        else:
            files = list(self.base_path.glob("symbol=*/*.parquet"))

        dfs = []
        for f in files:
            df = pd.read_parquet(f)
            df = df[df["alpha_id"] == alpha_id]
            dfs.append(df)

        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    def lookup(self, alpha_id: str, symbol: str, entry_bar: int) -> dict | None:
        """O(1) lookup by primary key."""
        outcomes = self.get_outcomes(alpha_id, symbol)
        match = outcomes[outcomes["entry_bar"] == entry_bar]
        return match.iloc[0].to_dict() if len(match) > 0 else None
```

### Step 4: Test Fixtures (1h)

Create synthetic test data with known R values:
- 10,000 outcomes across 4 symbols
- Mix of exit reasons
- Known net_R for spot-check verification
- Regime, spread, volume, volatility buckets populated

### Step 5: Integration Test (1h)

- Round-trip: write → read → verify fields match
- Idempotent append test
- Partition pruning correctness test
- Empty result edge case
- Large batch (1M records) performance baseline

### Step 6: CLI Entry Point (1h)

```bash
python -m alphaforge.outcome_cache.cli \
    --alpha discovery_pipeline_v6 \
    --input trades.csv \
    --cache-dir data/outcome_cache/v1
```

---

## Success Criteria

| Criterion | Target | Verification |
|-----------|--------|-------------|
| Write throughput | ≥ 100K rows/sec | `pytest --benchmark` |
| Read by alpha_id | < 100ms for 1M rows | Reader benchmark |
| Lookup by key | < 10ms | Single-key lookup |
| Schema adherence | 100% | Schema validation |
| Round-trip parity | 100% | Write → Read → Compare |
| Partition pruning | Reads only relevant symbol dir | Verify via strace |

---

## Risks

| Risk | Mitigation |
|------|-----------|
| No trade data to insert yet | Use synthetic fixtures for validation; actual data will come from re-running Truth V6 |
| Parquet append is slow | Use buffer-and-flush pattern |
| Many small parquet files | Periodic compaction job (P1, not P0) |
| Schema evolution | Version _metadata file, support schema upgrades |
