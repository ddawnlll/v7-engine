# v0.30 — Data Workflow Implementation Plan

**Date:** 2026-07-02
**Status:** RESEARCH_COMPLETE — Ready for implementation
**Prerequisite:** v030_real_data_lake_research.md + v030_data_source_matrix.yaml

---

## 1. Phased Implementation

### Phase v0.30A — DatasetSpec + DataCatalog (3-5 days)

**Objective:** Define what data we need and what we already have.

#### Components

**`lib/data_lake/spec.py` — DatasetSpec**
```python
@dataclass(frozen=True)
class DatasetSpec:
    """What data is needed for a research run or pipeline."""
    dataset_id: str
    source: str                    # "binance" | "coinalyze"
    market: str                    # "um_futures"
    symbols: list[str]
    intervals: list[str]
    data_types: list[str]          # ["klines", "funding_rate"]
    start: datetime
    end: datetime
    priority: str                  # "P0" | "P1" | "P2"
    backtest_required: bool
    allow_synthetic: bool          # explicit opt-in
```

**`lib/data_lake/catalog.py` — DataCatalog (extended)**
```python
class DataCatalog:
    """What data exists — extends existing catalog with gap analysis."""
    
    def query(self, symbol, interval, data_type) -> list[TimeRange]:
        """Return existing time ranges for a given symbol/interval/type."""
        
    def find_gaps(self, spec: DatasetSpec) -> list[TimeRange]:
        """Find missing time ranges given a spec."""
        
    def coverage(self, spec: DatasetSpec) -> CoverageReport:
        """Return coverage percentage and gap list."""
        
    def register(self, manifest: CacheManifest):
        """Register new data in catalog after successful backfill."""
```

**Key decision:** Extend existing `lib/market_data/catalog.py` rather than replacing it. Add gap analysis methods to the existing catalog.

#### Tests
- DatasetSpec validation (invalid intervals rejected, date ranges validated)
- Catalog query with overlapping ranges
- Gap analysis: exact match, partial overlap, complete miss
- Coverage report: 0%, 50%, 100% cases

#### Affected files (new)
- `lib/data_lake/__init__.py`
- `lib/data_lake/spec.py`
- `lib/data_lake/catalog.py`

#### Affected files (modified)
- `lib/market_data/catalog.py` — extend with gap analysis methods

---

### Phase v0.30B — Binance UM Data Lake Bootstrap (5-7 days)

**Objective:** Download, validate, and index 5-symbol Binance UM futures data.

#### Components

**`lib/data_lake/storage.py` — Storage Layout**
```python
class DataLakePaths:
    """Centralized path resolution for data lake storage."""
    
    RAW_BINANCE_UM = "data_lake/raw/binance/um"
    BRONZE_BINANCE_UM = "data_lake/bronze/binance/um"
    MANIFESTS = "data_lake/manifests"
    
    @staticmethod
    def klines_path(symbol, interval, year, month) -> Path:
        
    @staticmethod
    def funding_rate_path(symbol, year, month) -> Path:
```

**`lib/data_lake/downloader.py` — Multi-Worker Downloader**
```python
class DownloadManifest:
    """Ordered list of download tasks."""
    entries: list[DownloadEntry]
    source: str
    total_size_estimate: int
    
class ParallelDownloader:
    """Multi-worker download with rate limiting and resume."""
    
    def __init__(self, max_workers=4, rate_per_minute=1200):
        
    def execute(self, manifest: DownloadManifest) -> DownloadResult:
        """Download all entries in parallel, return results."""
```

**`lib/data_lake/coverage.py` — Coverage Report**
```python
@dataclass(frozen=True)
class CoverageReport:
    dataset_spec: DatasetSpec
    total_expected_bars: int
    total_actual_bars: int
    coverage_pct: float
    gaps: list[TimeRange]
    duplicates: list[TimeRange]
    integrity_pass: bool
```

**`lib/data_lake/checksum.py` — Checksum Report**
```python
@dataclass(frozen=True)
class ChecksumReport:
    total_files: int
    files_checked: int
    files_passed: int
    files_failed: list[Path]
    algorithm: str  # "sha256"
```

**`lib/data_lake/gateway.py` — Data Gateway**
```python
class DataGateway:
    """Unified read interface. Pipeline never guesses local paths."""
    
    def read_klines(self, symbol, interval, start, end,
                    source="bronze") -> pd.DataFrame:
        
    def read_funding_rate(self, symbol, start, end) -> pd.DataFrame:
```

#### Integration Points

| Current | New | Migration |
|---------|-----|-----------|
| `alphaforge/data/backfill.py` downloads → `data/raw/` | `lib/data_lake/downloader.py` → `data_lake/raw/` | Keep both during transition |
| Feature pipeline reads from absolute paths | `DataGateway` resolves paths | Pipeline config → `gateway` |
| SHA-256 sidecar per file | `ChecksumReport` batches verification | Add batch report on top of existing |
| `data/catalog.json` tracks ingestion | `DataCatalog` + gap analysis | Extend, don't replace |

#### Backfill Scope (P0)

| Symbol | Intervals | Data Types | Period | Est. Size |
|--------|-----------|------------|--------|-----------|
| BTCUSDT | 1h, 15m, 4h, 1d | klines + funding_rate | 2022-01 to present | ~5 GB |
| ETHUSDT | 1h, 15m, 4h, 1d | klines + funding_rate | 2022-01 to present | ~5 GB |
| SOLUSDT | 1h, 15m, 4h, 1d | klines + funding_rate | 2022-01 to present | ~5 GB |
| BNBUSDT | 1h, 15m, 4h, 1d | klines + funding_rate | 2022-01 to present | ~5 GB |
| XRPUSDT | 1h, 15m, 4h, 1d | klines + funding_rate | 2022-01 to present | ~5 GB |

**Total estimate:** ~25-30 GB raw (Parquet+Zstd compressed)

#### Source Priority

1. **Binance Vision public archive** (`data.binance.vision`) — primary, no API key needed
2. **Binance REST API** — for recent data not yet in archive
3. **Existing `data/raw/` files** — migrate to new structure if checksum valid

#### Tests
- Downloader: rate limiting, resume, error handling
- Coverage: 0% before download, X% after
- Checksum: valid data passes, corrupted data fails
- Gateway: round-trip read after download
- Integration: DataCatalog updated after download

#### Affected files (new)
- `lib/data_lake/storage.py`
- `lib/data_lake/downloader.py`
- `lib/data_lake/coverage.py`
- `lib/data_lake/checksum.py`
- `lib/data_lake/gateway.py`

#### Affected files (modified)
- `alphaforge/data/backfill.py` — optionally delegate to lib/data_lake/ downloader
- `alphaforge/data/integrity.py` — integrate with ChecksumReport

---

### Phase v0.30C — DataPassport + RealDataRequired Gate (2-3 days)

**Objective:** Every claim carries data provenance. Real data is mandatory for serious claims.

#### Components

**`lib/data_lake/passport.py` — DataPassport**
```python
@dataclass(frozen=True)
class DataPassport:
    passport_id: str
    dataset_id: str
    source: str
    source_type: str
    market: str
    symbols: list[str]
    intervals: list[str]
    data_types: list[str]
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
    cache_paths: list[str]
    manifest_hash: str
    passport_version: str
    
    @classmethod
    def from_catalog(cls, spec: DatasetSpec, catalog: DataCatalog) -> "DataPassport":
        """Build passport from a spec and current catalog state."""
        
    def is_trustworthy_for_backtest(self) -> bool:
        """Real data + PIT safe + coverage > 90% + checksum pass."""
        
    def is_trustworthy_for_context(self) -> bool:
        """Real data + checksum pass (PIT not required for live context)."""
```

**`lib/evidence_engine/hard_caps.py` — V11 RealDataRequired Gate**
```python
# V11 — Real Data Required Gate
REAL_DATA_REQUIRED_CLAIMS = {
    "ALPHA_HAS_EDGE",
    "MODEL_BEATS_BASELINES",
    "FEATURE_FAMILY_HAS_SIGNAL",
    "V7_RESEARCH_BACKTEST_READY",
    "V7_WALK_FORWARD_READY",
    "V7_PROMOTION_CANDIDATE",
}

class RealDataGate:
    def evaluate(self, claim_type: str, passport: DataPassport) -> GateResult:
        if claim_type in REAL_DATA_REQUIRED_CLAIMS:
            if not passport.is_real_data:
                return GateResult(
                    passed=False,
                    max_alpha_score=15,
                    alpha_candidate=False,
                    reason="Real data required for this claim type",
                )
            if not passport.is_trustworthy_for_backtest():
                return GateResult(
                    passed=False,
                    max_alpha_score=15,
                    alpha_candidate=False,
                    reason=f"Data quality insufficient: "
                           f"coverage={passport.coverage_pct}%, "
                           f"checksum={passport.checksum_pass}",
                )
        return GateResult(passed=True)
```

**`alphaforge/src/alphaforge/evidence_adapter.py` — Integration**
```python
def build_alphaforge_passport(wfv_results, mode, data_passport=None):
    """Build EvidencePassport with DataPassport attached."""
    passport = EvidencePassport(...)
    if data_passport:
        passport.data_passport = data_passport
        passport.real_data_verified = data_passport.is_trustworthy_for_backtest()
    return passport
```

**Validator update (target_validator.py):**
- Replace `is_synthetic` string check with DataPassport check
- `is_synthetic = not (passport and passport.is_real_data)`

#### Tests
- DataPassport from catalog: correct real_data flag
- RealDataGate: blocks synthetic, allows real
- Validator: synthetic vs real data passport
- EvidenceAdapter: passport attached correctly

#### Affected files (new)
- `lib/data_lake/passport.py`

#### Affected files (modified)
- `lib/evidence_engine/hard_caps.py`
- `alphaforge/src/alphaforge/evidence_adapter.py`
- `alphaforge/src/alphaforge/validation/target_validator.py`

---

### Phase v0.30D — Metric Plumbing Integrity Fix (1 day)

**Objective:** Fix consolidated report showing `active_trade_count=0`.

#### Root Cause (from research)
Two WFV implementations produce differently-shaped dicts:
- `walk_forward_runner.py` → `aggregate_metrics.total_oos_trades`
- `train.py` → `metrics.active_trade_count`
- Consumer (`target_validator.py:_extract_metrics`) only knows `active_trade_count`

#### Fix

**File: `alphaforge/src/alphaforge/validation/target_validator.py`**

```python
# In _extract_metrics(), ~line 401:
# Add fallback for walk_forward_runner output
active_trade_count = (
    met.get("active_trade_count")
    or oos.get("active_trade_count")
    or oos_trade_count
    or agg.get("total_oos_trades", 0)     # NEW: runner fallback
)

# exposure_pct needs computation:
oos_predictions = wfv_results.get("oos_predictions") or []
total_bars = len(oos_predictions) if oos_predictions else 0
exposure_pct = (
    met.get("exposure_pct")
    or oos.get("exposure_pct")
    or (active_trade_count / total_bars * 100) if total_bars > 0 else 0.0
)
```

**File: `alphaforge/src/alphaforge/validation/walk_forward_runner.py` (optional):**
- Add `active_trade_count` and `exposure_pct` to `aggregate_metrics` for forward compatibility

#### Acceptance Criteria
1. ✅ Consolidated report `metric_details.active_trade_count` = WFV detail count (1344)
2. ✅ Consolidated report `metric_details.exposure_pct` > 0
3. ✅ GR1 no longer triggers incorrectly
4. ✅ All existing tests pass
5. ✅ No model behavior changes

#### Affected files (modified only)
- `alphaforge/src/alphaforge/validation/target_validator.py`
- (optional) `alphaforge/src/alphaforge/validation/walk_forward_runner.py`

---

### Phase v0.30E — Real Data Baseline Evidence Control (2-3 days)

**Objective:** First real-data run with correct metrics and DataPassport.

#### Steps

1. **Complete v0.30A-D** — all prerequisites must pass
2. **Backfill 5 symbols** — klines + funding rate via v0.30B pipeline
3. **Run SCALP mode training** on real data
4. **Verify consolidated report:**
   - DataPassport present: source="binance", is_real_data=True
   - active_trade_count > 0
   - exposure_pct > 0
   - GR1 not triggered
   - V7 gate mapping reflects real data status
5. **Take baseline evidence snapshot:**
   - Save consolidated report as baseline
   - Compare with synthetic run
   - Document differences

#### Expected Outcomes
- GR1 no longer blocks (economic score reflects real data)
- Alpha scores may differ from synthetic (synthetic typically overoptimistic)
- WFV metrics are credible for V7 gate evaluation
- DataPassport becomes part of standard evidence package

#### Affected files
- (none — this phase is operational, not developmental)

---

### Phase v0.30F — On-Chain Vendor Evidence Gate (future)

**Objective:** Evaluate and conditionally integrate on-chain data.

#### Steps
1. **Glassnode PIT test:** 30-day fetch → 7-day refetch → diff report
2. **If PASS:** Pilot 5-10 BTC/ETH metrics as context features
3. **Document results** in onchain_revision_test_report

#### Hard Rules (from research)
- On-chain data CANNOT generate labels
- On-chain data CANNOT be ground truth
- If NOT PIT safe: backtest feature usage FORBIDDEN
- Must pass 30+7 day PIT test before any integration

#### Affected files (new)
- `reports/research/v030_onchain_vendor_workflow.md` (this plan)

---

### Phase v0.30G — 20-Symbol Expansion (future)

**Objective:** Expand from 5 to 20 symbols.

#### Scope
- Add 15 symbols: ADA, AVAX, DOGE, DOT, LINK, MATIC, NEAR, ATOM, FIL, APT, SUI, OP, ARB, INJ, RUNE
- Same intervals and data types as P0
- Priority: after P0 baseline is stable

#### Acceptance Criteria
- All 20 symbols have > 90% coverage from 2023
- Coverage report shows gaps if any
- DataGateway handles multi-symbol reads
- Feature pipeline handles expanded universe

---

## 2. Dependency Graph

```
v0.30A (DatasetSpec + Catalog)
    |
    v
v0.30B (Binance Data Lake Bootstrap)
    |
    v
v0.30C (DataPassport + RealDataGate)
    |
    ├──> v0.30E (Baseline Evidence)
    |
v0.30D (Metric Plumbing Fix) ────────┘
    (independent, can parallel with A-B-C)

v0.30F (On-Chain Gate) ── after E, if needed
v0.30G (20-Symbol) ── after E, if needed
```

**Key:** v0.30D is independent and can run in parallel with v0.30A-C.

---

## 3. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Binance Vision archive rate limiting | Low | Medium | Use parallel downloader with backoff |
| Disk space insufficient for 20 symbols | Low | Low | 5 symbols ~30 GB; ~1 TB available |
| Funding rate API pagination slow | Medium | Low | Multi-month parallel fetch |
| Existing tests break with catalog changes | Low | Medium | Keep backward compatibility layer |
| Metric fix changes GR1 behavior | Medium | Medium | Verify economic score changes are correct |
| Backfill takes longer than estimated | Medium | Medium | Start P0 backfill first; expand later |
| WSL2 file system performance | Low | Low | Parquet+Zstd is efficient; batch writes |

---

## 4. Acceptance Criteria (Complete)

- [ ] `lib/data_lake/` module exists with all components
- [ ] DatasetSpec validates at construction time
- [ ] DataCatalog finds gaps correctly
- [ ] Backfill downloads 5 symbols × 4 intervals × 2 data types
- [ ] Coverage report shows > 90% coverage
- [ ] Checksum report passes for all downloaded files
- [ ] DataGateway reads data without path guessing
- [ ] DataPassport attached to EvidencePassport
- [ ] RealDataGate blocks synthetic claims
- [ ] Consolidated report shows correct active_trade_count
- [ ] Consolidated report shows exposure_pct > 0
- [ ] All existing tests pass (lib/ + integration/ + simulation/ + alphaforge/)
- [ ] Synthetic data still works for unit/smoke/schema tests
- [ ] No model behavior changes
- [ ] No config changes
