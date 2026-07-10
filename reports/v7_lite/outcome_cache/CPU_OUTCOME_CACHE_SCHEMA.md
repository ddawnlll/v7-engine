# CPU Outcome Cache Schema — P0 Design

**Status:** `DESIGN_COMPLETE` — ready for implementation
**Generated:** 2026-07-08
**Mission:** Provide a persistent, queryable, CPU-based outcome cache that eliminates
re-simulation of repeated alpha candidates, enables fast candidate comparison,
and serves as the baseline for future GPU comparison.

---

## Schema Definition

### File Format

- **Primary format:** Parquet (columnar, compressed, fast I/O)
- **Fallback format:** CSV (for debugging and inspection)
- **Storage location:** `data/outcome_cache/v1/candidates.parquet`
- **Partition scheme:** By symbol (Hive-style: `symbol=BTCUSDT/`)
- **Index:** By (alpha_id, entry_bar) for O(1) lookup

### Schema Fields

| # | Field | Type | Description | Source |
|---|-------|------|-------------|--------|
| 1 | `candidate_id` | string | UUID v4 for this candidate-outcome record | Generated |
| 2 | `alpha_id` | string | Alpha identifier (e.g., `discovery_pipeline_v6`) | Ledger |
| 3 | `run_id` | string | Run identifier (e.g., `run-alpha-truth-v6-20260707`) | Ledger |
| 4 | `symbol` | string | Trading pair (e.g., `BTCUSDT`) | Market data |
| 5 | `entry_time` | datetime | Candle open time of entry decision | Market data |
| 6 | `entry_bar` | int64 | Bar index relative to dataset start | Derived |
| 7 | `direction` | string | `LONG` or `SHORT` | Candidate |
| 8 | `entry_price` | float64 | Price at entry (may be open or custom) | Market data |
| 9 | `stop_price` | float64 | Stop loss price level | Simulation config |
| 10 | `target_price` | float64 | Take profit price level | Simulation config |
| 11 | `exit_time` | datetime | Candle open time of exit | Simulation |
| 12 | `exit_bar` | int64 | Bar index of exit | Derived |
| 13 | `exit_reason` | string | `STOP_HIT` / `TARGET_HIT` / `TIME_EXIT` / `HORIZON_END` / `INVALIDATED` | Simulation |
| 14 | `gross_R` | float64 | Raw R-multiple (exit_price - entry_price) / ATR_at_entry | Simulation |
| 15 | `fee_R` | float64 | Fee cost in R units | Cost model |
| 16 | `spread_R` | float64 | Spread cost in R units | Cost model |
| 17 | `slippage_R` | float64 | Slippage cost in R units | Cost model |
| 18 | `net_R` | float64 | gross_R - fee_R - spread_R - slippage_R | Derived |
| 19 | `regime_id` | int64 | Regime classification at entry (0=unknown, 1=trend, 2=chop, 3=breakout) | Regime classifier |
| 20 | `spread_bucket` | int64 | Spread percentile bucket (1-5, 5=highest) | Market data |
| 21 | `volume_bucket` | int64 | Volume percentile bucket (1-5, 5=highest) | Market data |
| 22 | `volatility_bucket` | int64 | Volatility percentile bucket (1-5, 5=highest) | Market data |
| 23 | `session_bucket` | string | Trading session: `ASIA`, `LONDON`, `NEW_YORK`, `OVERLAP` | Time-based |
| 24 | `source_file` | string | Path to the original run artifact | Metadata |
| 25 | `config_hash` | string | SHA256 of the simulation config used | Metadata |

### Index Strategy

Primary index: `(alpha_id, symbol, entry_bar)` — unique per alpha + symbol + bar

Secondary indexes (for analysis):
- `(symbol, exit_reason)` — exit reason distribution
- `(alpha_id, net_R)` — sorted for distribution analysis
- `(alpha_id, regime_id)` — regime performance
- `(alpha_id, spread_bucket)` — spread sensitivity

### Partitioning

```
data/outcome_cache/v1/
  _metadata                   ← schema version, field list, row count
  symbol=BTCUSDT/
    part-0000.parquet          ← 100K rows per part
    part-0001.parquet
  symbol=ETHUSDT/
    part-0000.parquet
  ...
```

### Schema Versioning

Schema version tracked in `_metadata` file:
```json
{
  "schema_version": "1.0.0",
  "created": "2026-07-08T00:00:00Z",
  "fields": 25,
  "total_rows": 0,
  "alphas_cached": [],
  "simulation_family_version": "1.0.0",
  "cost_model_version": "1.0.0"
}
```

---

## Read/Write Interface

### Write API

```python
class OutcomeCacheWriter:
    def append(alpha_id, outcomes: list[OutcomeRecord]) -> int
    def flush() -> None
    def close() -> None
```

Write behavior:
- Append mode: open existing parquet files, add rows
- Batch threshold: flush every 10,000 rows or 60 seconds
- Idempotent: overwrite by (alpha_id, symbol, entry_bar) on conflict
- Checksum: SHA256 of each batch

### Read API

```python
class OutcomeCacheReader:
    def get_outcomes(alpha_id: str, symbol: str = None) -> pd.DataFrame
    def lookup(alpha_id: str, symbol: str, entry_bar: int) -> OutcomeRecord | None
    def query(filter_expr: str) -> pd.DataFrame
```

Query examples:
```python
cache.query("alpha_id='discovery_pipeline_v6' AND net_R > 2.0")
cache.query("alpha_id='discovery_pipeline_v6' AND regime_id=1")
cache.query("alpha_id='discovery_pipeline_v6' AND symbol='BTCUSDT'")
```

---

## Implementation Priority

### P0 (This sprint)
- [ ] Schema definition file (`_metadata.json`)
- [ ] Basic `OutcomeCacheWriter` with parquet append
- [ ] Basic `OutcomeCacheReader` with alpha_id + symbol lookup
- [ ] Integration test with 10K synthetic outcomes
- [ ] Verify round-trip: write → read → field equality

### P1 (Next sprint)
- [ ] Hive-style partitioning by symbol
- [ ] Batch flush logic
- [ ] Config_hash deduplication
- [ ] Query acceleration via predicate pushdown

### P2 (Future)
- [ ] Delta Lake / LakeFS integration
- [ ] Automatic GC of stale alphas
- [ ] Cross-candidate query optimization
- [ ] Real-time append pipeline from V7 runtime

---

## Dependencies

| Dependency | Version | Purpose |
|-----------|---------|---------|
| pyarrow | ≥14.0 | Parquet read/write |
| pandas | ≥2.0 | DataFrame manipulation |
| numpy | ≥1.24 | Array operations |
| duckdb | ≥0.10 | SQL queries on parquet (optional, for advanced queries) |

---

## File Structure

```
alphaforge/src/alphaforge/outcome_cache/
  __init__.py
  schema.py          ← Schema constants and validation
  writer.py          ← OutcomeCacheWriter
  reader.py          ← OutcomeCacheReader
  _metadata.py       ← Metadata management
  config.py          ← Config dataclass

tests/test_outcome_cache/
  test_schema.py      ← Schema validation
  test_writer.py      ← Write/read round-trip
  test_reader.py      ← Query correctness
  fixtures.py         ← Test data generators
```
