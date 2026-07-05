# v0.30 — Real Data Lake + Evidence-Gated Workflow Research Report

**Date:** 2026-07-02
**Author:** v7-engine research workflow
**Status:** RESEARCH_COMPLETE — Implementation plan follows in companion documents

---

## Executive Summary

AlphaForge + V7 has reached the point where synthetic data is no longer sufficient for credible alpha claims. The existing pipeline can train, evaluate, and generate evidence — but the **data layer is the weakest link**.

This report:
1. Documents every available external data source with cost, depth, PIT safety
2. Analyzes the current repo state against best practices
3. Proposes a centralized Data Lake architecture
4. Identifies the metric plumbing gap and its root cause
5. Recommends a phased implementation roadmap

**Key verdict:** Centralized Data Lake is **required**. Synthetic fallback must be **opt-in only**. Binance public data is **sufficient for P0**. On-chain data is **not safe for labels** — feature/context only, and only after PIT gate passes.

---

## 1. Current Repo State

### 1.1 What Exists

| Component | Status | Details |
|-----------|--------|---------|
| BackfillPipeline | ✅ Works | Two paths: Binance API (key required) + Binance Vision public S3 mirror |
| DataManifest | ✅ Works | Checksummed, deterministic metadata records for simulation output fixtures |
| DataCatalog | ✅ Works | Tracks ingested symbol/interval/time ranges at `data/catalog.json` |
| Integrity validation | ✅ Works | SHA-256 sidecar, timestamp sort/gap/dup checks on Parquet files |
| FeaturePipeline | ✅ Works | 9 active feature groups, numpy-only, HMAC-cached |
| EvidencePassport | ✅ Works | Bridges AlphaForge WFV results → V7 gate mapping |
| Validator hard caps | ✅ Works | GR1-GR7, synthetic data caps at 25 economic score |
| **DataLake** | ❌ Missing | No centralized dataset spec, passport, backfill planner |
| **DataPassport** | ❌ Missing | No data provenance standard attached to claims |
| **RealDataRequired gate** | ❌ Missing | Synthetic fallback is still default, not explicit opt-in |
| **BackfillPlanner** | ❌ Missing | Backfill is manual, no gap analysis, no download manifest |

### 1.2 Real Data Currently Available

```
data/raw/
├── BTCUSDT/       — some Parquet files (Binance API downloads)
├── ETHUSDT/       — some Parquet files
└── SOLUSDT/       — some Parquet files
```

The existing backfill is partial and ad-hoc. No systematic:
- Coverage report
- Gap analysis
- Checksum verification against known good manifests
- Bronze/silver layer separation

### 1.3 Synthetic Data Dependency

The mode-specific manifest builders (`scalp_manifest.py`, `aggressive_manifest.py`) explicitly state *"No real market data — fixture-only build"*. The `AlphaTargetValidator` defaults `is_synthetic = True` unless explicitly marked "real" or "binance".

**Problem:** This means every research report produced today defaults to synthetic, which:
- Caps economic score at 25 (GR3)
- Blocks V7 gate progression
- Makes alpha claims non-credible

### 1.4 What Runs on Synthetic vs Real

| Claim Type | Current | Required |
|-----------|---------|----------|
| Unit tests | Synthetic | Synthetic (OK) |
| Smoke tests | Synthetic | Synthetic (OK) |
| Pipeline schema tests | Synthetic | Synthetic (OK) |
| Validator logic tests | Synthetic | Synthetic (OK) |
| Alpha edge claims | Synthetic | **REAL** |
| Baseline defeat | Synthetic | **REAL** |
| V7 readiness | Synthetic | **REAL** |
| WFV/PBO/DSR | Synthetic | **REAL** |
| Feature family ablation | Synthetic | **REAL** |

---

## 2. External Data Source Research

### 2.1 Binance Public Data — P0 Core Market Data

**Source:** `data.binance.vision` (public S3 mirror) + REST API

**Availability:**

| Data Type | Historical Depth | Resolution | Bulk Export | Cost | PIT Safe |
|-----------|-----------------|------------|-------------|------|----------|
| USD-M Futures klines | Full (since ~2019) | 1s,1m,3m,5m,15m,30m,1h,2h,4h,6h,8h,12h,1d,3d,1w,1mo | Monthly ZIP + daily ZIP + REST API | Free | ✅ Yes (archived files have CHECKSUM) |
| Funding Rate | Full | 8h intervals | REST API (max 1000 per call) | Free | ✅ Yes (markPrice included) |
| Mark Price | Full | Same as klines | Via klines | Free | ✅ Yes |
| Index Price | Full | Same as klines | Via klines | Free | ✅ Yes |
| Premium Index | Full | Same as klines | Via klines | Free | ✅ Yes |
| Open Interest | Latest 30 days only | 5m-1d | REST API (max 500) | Free | ⚠️ 30-day window |
| Taker Buy/Sell Vol | Latest 30 days only | 5m-1d | REST API (max 500, IP rate 1000/5min) | Free | ⚠️ 30-day window |
| Long/Short Ratio | Latest 30 days only | 5m-1d | REST API (max 500) | Free | ⚠️ 30-day window |
| aggTrades | Full | Tick-level | Monthly ZIP + daily ZIP | Free | ✅ Yes |

**Key findings:**
- **Klines are the most reliable source**: historical archive has CHECKSUM files, no revision risk
- **Perpetual futures data** available at `data.binance.vision/data/futures/um/`
- **Funding rate history**: REST API `GET /fapi/v1/fundingRate` — max 1000 records per call, need pagination for multi-year backfill
- **OI/Taker/LongShort**: Only 30 days via REST — NOT suitable for backtesting P0. Need historical archive or alternative source
- **Update frequency**: Daily files available next day; Monthly files on first Monday of month

**Verdict: ✅ P0 sufficient for klines + funding rate**
- OI/Taker/LongShort: P1 (limited historical depth; use current data for context features only)
- aggTrades: P2 (very large volume; orderflow proxy research only)

### 2.2 Coinalyze — Free Alternative for OI/Funding/Liquidations

**Source:** `api.coinalyze.net/v1`

| Feature | Detail |
|---------|--------|
| Cost | Free (40 req/min) |
| Historical depth | Unknown (not well documented) |
| Data types | OI, funding rate, predicted funding, liquidations, CVD |
| Coverage | 300+ assets, 25 exchanges |
| PIT safe | Unknown / needs verification |
| Bulk export | No — API only |

**Verdict: ⚠️ P3 candidate — needs PIT/revision testing**
- Free API makes it easy to test
- Historical depth needs verification
- Rate limit (40/min) makes bulk backfill impractical

### 2.3 Crypto Lake — Order Book & Tick Data

**Source:** `crypto-lake.com` (Python API: `lakeapi`)

| Feature | Detail |
|--------|--------|
| Cost | Paid subscription (€64/mo reported for basic) |
| Historical depth | Several years |
| Data types | L2 order book (20 levels, 100ms snapshots), tick trades, 1m OHLCV, OI, funding |
| Coverage | 10 exchanges, top 50+ tokens |
| PIT safe | Unknown |
| Free tier | Sample data via `lakeapi.use_sample_data()` |
| Python API | ✅ `pip install lakeapi` |

**Verdict: ✅ P4 candidate for L2 research**
- Order book data is unique offering vs Binance public data
- Pricing reasonable for research
- PIT safety needs verification before backtest use

### 2.4 Tardis.dev — Tick-Level Multi-Exchange

**Source:** `tardis.dev` (Python: `tardis-dev`)

| Feature | Detail |
|--------|--------|
| Cost | Solo/Pro/Business ($50-500+/mo est) |
| Historical depth | Years (depends on plan) |
| Data types | Trades, order book (full depth + incremental), OI, funding, liquidations, options |
| Coverage | All major exchanges |
| PIT safe | Unknown |
| Python API | ✅ `pip install tardis-dev` |
| Bulk export | CSV download + replay API (Pro+) |
| Node.js client | ✅ Full normalized replay |

**Verdict: ✅ P4 — Most comprehensive but expensive**
- Gold standard for quantitative crypto research
- Overkill for P0-P1 needs when Binance public data is free
- Consider after P0-P2 are stable and L2 research becomes active priority

### 2.5 Glassnode — On-Chain Analytics

**Source:** `glassnode.com` (API via Professional plan)

| Feature | Detail |
|--------|--------|
| Cost | Professional plan (not publicly priced; >$500/mo est) |
| Historical depth | Full (all available data per plan) |
| Coverage | 1500+ assets, 11 blockchains |
| Data types | On-chain (addresses, supply, P/L), derivatives (OI, funding), spot, ETFs, macro |
| PIT availability | ✅ **Yes** — "Point-in-Time metrics are immutable — they never receive retroactive updates" |
| Resolution | Varies by metric (daily, hourly) |
| API type | REST, credits-based (1 BTC, 2 alts per call) |
| Bulk export | Via API; no public bulk archive |

**Key finding:** Glassnode explicitly offers Point-in-Time data. This is **critical** — of all on-chain vendors surveyed, Glassnode is the only one that explicitly markets PIT safety.

**Verdict: ⚠️ P3 candidate — PIT test PASS likely**
- API cost is significant barrier for early research
- If PIT test passes, viable as feature context candidate
- **NEVER for label generation** (on-chain data cannot be ground truth for trading labels)

### 2.6 CryptoQuant — On-Chain Analytics

**Source:** `cryptoquant.com` (API)

| Feature | Detail |
|--------|--------|
| Cost | Paid subscription (not publicly priced) |
| Historical depth | Full |
| Coverage | Major blockchains, exchange flows, mining data |
| PIT safety | **Unknown** — no explicit PIT guarantee found in research |
| API type | REST |

**Verdict: ❌ P4 / DEFERRED — No PIT guarantee found**
- Without explicit PIT guarantee, cannot be used for backtest features
- Live/context-only candidate at best
- Needs vendor evaluation before any integration

### 2.7 Santiment — Social + On-Chain Analytics

**Source:** `santiment.net` (GraphQL API)

| Feature | Detail |
|--------|--------|
| Cost | Free tier (7-day history); Paid for full history |
| Historical depth | 7 days free; full history paid |
| Coverage | 2800+ assets, 1000+ metrics |
| Data types | Social sentiment, on-chain, dev activity |
| PIT safety | ❌ **Known revision risk** — some metrics have `canMutate: true` |
| API type | GraphQL (SanAPI) |
| Rate limit | Depends on plan |

**Critical finding:** Santiment's own API documentation shows `exchange_inflow_per_exchange` has `"Can Mutate": true` and a stabilization period of 12h. This means historical data can change retroactively. This is a **hard blocker** for backtest use.

**Verdict: ❌ Backtest use forbidden — PIT risk confirmed**
- Live/context-only candidate at absolute best
- Social sentiment has limited value for trading alpha on major pairs
- Not recommended for v0.30 scope

---

## 3. Data Source Comparison Matrix

| Source | Tier | Historical Depth | PIT Safe | Cost | Backtest | Live/Context | Label Gen |
|--------|------|-----------------|----------|------|----------|-------------|-----------|
| Binance Klines (public archive) | P0 | Full (2019+) | ✅ Yes | Free | ✅ | ✅ | ✅ |
| Binance Funding Rate | P0 | Full (2019+) | ✅ Yes | Free | ✅ | ✅ | ⚠️ Context only |
| Binance Mark/Index/Premium | P0 | Full (2019+) | ✅ Yes | Free | ✅ | ✅ | ⚠️ Context only |
| Binance OI (REST) | P1 | 30 days | ⚠️ N/A | Free | ❌ | ✅ | ❌ |
| Binance Taker Vol (REST) | P1 | 30 days | ⚠️ N/A | Free | ❌ | ✅ | ❌ |
| Binance aggTrades | P2 | Full | ✅ Yes | Free | ✅ | ⚠️ Too large | ❌ |
| Coinalyze | P3 | Unknown | Unknown | Free | ❌ | ✅ | ❌ |
| Glassnode | P3 | Full (paid) | ✅ Explicit | High | ⚠️ If PIT passes | ✅ | ❌ |
| CryptoQuant | P4 | Full (paid) | ❌ Unknown | High | ❌ | ⚠️ | ❌ |
| Santiment | P4 | Full (paid) | ❌ Mutates | Medium | ❌ | ⚠️ Context only | ❌ |
| Crypto Lake | P4 | Years (paid) | Unknown | Medium | ⚠️ | ⚠️ | ❌ |
| Tardis.dev | P4 | Full (paid) | Unknown | High | ⚠️ | ✅ | ❌ |

---

## 4. Architecture Recommendation: Centralized Data Lake

### 4.1 Why Centralized?

Current state: backfill is split between `alphaforge/data/backfill.py` (high-level) and `lib/market_data/` (low-level). There is no:
- Single source of truth for dataset specs
- Coverage reporting
- Gap analysis
- Download manifest generation
- Data passport standard

A centralized `lib/data_lake/` module solves all of these while respecting domain boundaries.

### 4.2 Proposed Module Structure

```
lib/data_lake/
├── __init__.py                  # Public API exports
├── spec.py                      # DatasetSpec — what data is needed
├── catalog.py                   # DataCatalog — what data exists
├── passport.py                  # DataPassport — data provenance for claims
├── backfill_planner.py          # BackfillPlanner — gap analysis → manifest
├── download_manifest.py         # DownloadManifest — what to download
├── cache_manifest.py            # CacheManifest — what is cached
├── coverage.py                  # CoverageReport — % coverage, gaps, duplicates
├── checksum.py                  # ChecksumReport — integrity verification
├── gateway.py                   # DataGateway — unified read interface
└── storage.py                   # Storage layout constants, path resolution
```

### 4.3 Domain Boundary Compliance

```
lib/data_lake/ imports only:
  - lib/ primitives (time utils, path utils)
  - Standard library (pathlib, hashlib, json)

lib/data_lake/ MUST NOT import:
  - alphaforge/
  - v7/
  - simulation/
  - runtime/

Consumers:
  - alphaforge/ may import lib/data_lake/ for dataset discovery
  - v7/ may import lib/data_lake/ via evidence passport
  - But data lake never imports them
```

### 4.4 Data Storage Layout

```
data_lake/
├── raw/                         # Immutable raw downloads
│   └── binance/
│       └── um/
│           ├── klines/
│           │   └── {symbol}/{interval}/{year}/{month:02d}.parquet
│           ├── fundingRate/
│           │   └── {symbol}/{year}/{month:02d}.parquet
│           ├── markPrice/
│           │   └── {symbol}/{year}/{month:02d}.parquet
│           ├── openInterest/
│           │   └── {symbol}/{year}/{month:02d}.parquet
│           └── takerVolume/
│               └── {symbol}/{year}/{month:02d}.parquet
├── bronze/                      # Validated, cleaned, indexed
│   └── binance/
│       └── um/
│           ├── klines/
│           ├── funding_rate/
│           ├── mark_price/
│           ├── open_interest/
│           └── taker_volume/
├── silver/                      # Enriched, feature-ready views (future)
└── manifests/                   # All manifests and reports
    ├── dataset_specs/
    ├── download_manifests/
    ├── cache_manifests/
    ├── coverage_reports/
    └── checksum_reports/
```

**Design principle:** Raw is **append-only, never modified**. Bronze is **validated and indexed**. Silver is **computed and cacheable**. This mirrors the medallion architecture proven in production data engineering.

---

## 5. DataPassport Standard

### 5.1 Purpose

Every research run, claim, and evidence package must carry a DataPassport that answers: *"Can I trust this data for this purpose?"*

### 5.2 Schema

```yaml
data_passport:
  # Identity
  passport_id: str                     # UUID
  dataset_id: str                      # Reference to DatasetSpec
  generated_at: str                    # ISO 8601

  # Source
  source: str                          # "binance" | "coinalyze" | "glassnode" | etc.
  source_type: str                     # "public_archive" | "api" | "vendor_api"
  market: str                          # "um_futures" | "spot" | "cm_futures"

  # Scope
  symbols: list[str]
  intervals: list[str]
  data_types: list[str]               # ["klines", "funding_rate", "mark_price", ...]
  start: str                          # ISO 8601
  end: str                            # ISO 8601

  # Data quality
  is_real_data: bool
  allow_synthetic: bool               # If true, synthetic data may be mixed in
  coverage_pct: float                 # 0-100, actual data vs expected
  gap_count: int
  duplicate_count: int
  checksum_pass: bool

  # Point-in-time safety
  point_in_time_safe: bool            # True = no revision risk
  revision_risk: str                  # "none" | "low" | "medium" | "high" | "unknown"

  # Provenance
  cache_paths: list[str]
  manifest_hash: str                  # SHA-256 of the manifest
  passport_version: str               # Schema version
```

### 5.3 Usage Rules

| Context | Requires Real Data | Requires PIT Safe |
|---------|-------------------|-------------------|
| Unit test | ❌ | ❌ |
| Smoke test | ❌ | ❌ |
| Schema test | ❌ | ❌ |
| Validator test | ❌ | ❌ |
| Feature research | ✅ When making claims | ✅ |
| Alpha edge claim | ✅ HARD | ✅ |
| Baseline comparison | ✅ HARD | ✅ |
| WFV/PBO/DSR | ✅ HARD | ✅ |
| V7 readiness gate | ✅ HARD | ✅ |
| Live trading context | ⚠️ Recommended | ❌ Not needed |

---

## 6. Real Data Required Gate

### 6.1 Hard Rules

```python
if claim_type in {
    "ALPHA_HAS_EDGE",
    "MODEL_BEATS_BASELINES",
    "FEATURE_FAMILY_HAS_SIGNAL",
    "V7_RESEARCH_BACKTEST_READY",
    "V7_WALK_FORWARD_READY",
    "V7_PROMOTION_CANDIDATE",
}:
    require_real_data = True
    if not passport.is_real_data:
        max_alpha_score = 15
        alpha_candidate = False
        v7_gate_mapping = BLOCKED
```

### 6.2 Synthetic-Only Claims

```python
if not passport.is_real_data:
    max_alpha_score = 15          # Hard cap
    alpha_candidate = False        # Cannot advance to V7
    evidence_status = "INCONCLUSIVE"  # Overrides any metric
```

### 6.3 Implementation Point

The gate should live in:
- `lib/evidence_engine/hard_caps.py` — new hard cap rule (V11 or integrated into V7)
- `lib/evidence_engine/evidence_passport.py` — DataPassport integration
- `alphaforge/src/alphaforge/evidence_adapter.py` — consume DataPassport in passport builder

---

## 7. Backfill Centralization Plan

### 7.1 Current Problems

1. **No gap analysis** — BackfillPipeline downloads what it's told; doesn't know what's missing
2. **No DownloadManifest** — Can't audit what was requested vs what was downloaded
3. **No parallel download orchestration** — Sequential download is slow
4. **No resume capability at manifest level** — Individual file resume exists, but no "resume this 20-symbol backfill"
5. **No bronze layer** — Raw parquet is used directly; no validation/cleaning separation

### 7.2 Proposed Flow

```
DatasetSpec (what we need)
    ↓
BackfillPlanner (what we have vs what we need)
    ↓
DownloadManifest (what to download)
    ↓
Parallel Downloader (multi-worker download with rate limiting)
    ↓
Checksum Verification (SHA-256 validate each file)
    ↓
Raw Cache Write (append-only, never modify)
    ↓
Bronze Write (validate, index, deduplicate)
    ↓
CoverageReport (how much we got)
    ↓
DataCatalog Update (make available)
    ↓
Pipeline: ONLY if catalog PASS
```

### 7.3 Backfill Planner Logic

```python
class BackfillPlanner:
    def plan(self, spec: DatasetSpec, catalog: DataCatalog) -> DownloadManifest:
        """Compare spec vs catalog, produce manifest of missing data."""
        missing = []
        for symbol in spec.symbols:
            for interval in spec.intervals:
                for data_type in spec.data_types:
                    existing = catalog.query(symbol, interval, data_type)
                    gaps = self._find_gaps(spec.start, spec.end, existing)
                    missing.extend(gaps)
        return DownloadManifest(
            entries=missing,
            total_size_estimate=self._estimate_size(missing),
            source=spec.source,
        )
```

---

## 8. Dataset Tier Plan (Validated)

The proposed tier plan is validated with minor adjustments:

```yaml
P0 — Core Market Data (BACKTEST ESSENTIAL, START HERE):
  binance_um_klines:
    intervals: [1h, 15m, 4h, 1d]
    symbols: [BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT]
    period: 2022-01-01 to present
    priority: IMMEDIATE
    backtest: REQUIRED
    cost: FREE

  binance_um_funding_rate:
    intervals: [8h]
    symbols: [BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT]
    period: 2022-01-01 to present
    priority: IMMEDIATE
    backtest: REQUIRED
    cost: FREE

  binance_um_mark_price:
    intervals: [1h, 15m, 4h, 1d]
    symbols: same 5
    period: 2022-01-01 to present
    priority: IMMEDIATE
    backtest: REQUIRED
    cost: FREE

P1 — Expanded Universe + Context Data:
  binance_um_klines:
    symbols: +15 (20 total: ADA, AVAX, DOGE, DOT, LINK, MATIC, NEAR, etc.)
    intervals: same P0
    period: 2023-01-01 to present
    priority: AFTER P0 STABLE

  binance_um_open_interest:
    note: 30-day REST API limit — current data only for context features
    backtest: NOT AVAILABLE (30d window)
    priority: P1 for live context only

  binance_um_taker_volume:
    note: 30-day REST API limit
    backtest: NOT AVAILABLE
    priority: P1 for live context only

P2 — Orderflow Proxy Research:
  binance_um_agg_trades:
    note: Extremely large volume; research use only
    priority: P2 — DEFERRED until P0/P1 stable

P3 — On-Chain Vendor Pilot:
  glassnode:
    condition: PIT/revision gate must PASS
    usage: Context features only. NOT for labels.
    candidate_count: 5-10 BTC/ETH metrics
    priority: P3

P4 — L2 Order Book:
  crypto_lake:
    condition: P0-P3 stable, active L2 research need
    priority: P4 — not needed for current alpha research
  tardis_dev:
    condition: Only if Crypto Lake insufficient
    priority: P4 — most expensive, most comprehensive
```

---

## 9. On-Chain Vendor Workflow

### 9.1 Hard Rules

```
1. On-chain data cannot generate labels
2. On-chain data cannot be ground truth
3. If NOT point-in-time safe:
   - Backtest feature usage: FORBIDDEN
   - Live/context only
4. If point-in-time safe:
   - Backtest feature usage: ALLOWED with explicit DataPassport marker
   - PIT test must be re-run quarterly
```

### 9.2 Evaluation Protocol

Each vendor must pass a PIT/revision test:

```
Phase 1 — 30-day BTC metric fetch:
  1. Fetch daily BTC metric for a fixed 30-day range
  2. Save as reference snapshot
  3. After 7 days, refetch same range
  4. Compare: if ANY value differs → FAIL

Phase 2 — 180-day multi-asset fetch:
  1. Fetch BTC/ETH/USDT metrics for 180-day range
  2. After 14 days, refetch same range
  3. Generate diff report
```

### 9.3 Vendor-Specific Assessment

| Vendor | PIT Test Needed | Likely Outcome | Timeline |
|--------|----------------|---------------|----------|
| Glassnode | ✅ | PASS (explicit PIT available) | v0.30F |
| CryptoQuant | ✅ | Unknown — no PIT guarantee found | Deferred |
| Santiment | ✅ | FAIL (known mutation) | Deferred |

---

## 10. Metric Plumbing Issue — Root Cause Analysis

### 10.1 The Bug

Consolidated report shows `active_trade_count` and `exposure_pct` = 0, while WFV detail shows 1344 active trades.

### 10.2 Root Cause

**Two independent WFV implementations produce differently-shaped result dicts, and the consumer code only knows how to read one shape.**

### 10.3 Code Paths

**Path A — Empirical Report (WORKS):**
```
train.py:walk_forward_validate()
  → returns list[dict] with "active_trade_count" per fold
  → real_training.py builds wfv_results with "metrics" and "oos_summary" sections
  → empirical.py reads from wfv_results["metrics"]["active_trade_count"] → 1344 ✅
```

**Path B — Consolidated Report (BROKEN):**
```
walk_forward_runner.py:walk_forward_result_to_dict()
  → produces dict with "aggregate_metrics" (key="total_oos_trades") but NO "metrics" or "oos_summary"
  → v7_pipeline.py loads this JSON
  → target_validator.py:_extract_metrics() tries:
      met.get("active_trade_count")       → None (no "metrics" section)
      oos.get("active_trade_count")       → None (no "oos_summary" section)
      oos.get("oos_trade_count", 0)       → 0
    → active_trade_count = 0 ❌
```

### 10.4 Affected Files

| File | Lines | Issue |
|------|-------|-------|
| `alphaforge/src/alphaforge/validation/walk_forward_runner.py` | 1166-1188 | `aggregate_metrics` uses `total_oos_trades` not `active_trade_count` |
| `alphaforge/src/alphaforge/validation/target_validator.py` | 401-404 | `_extract_metrics()` missing fallback to `agg["total_oos_trades"]` |
| `alphaforge/src/alphaforge/validation/target_validator.py` | 259-260 | GR1 guardrail triggered by zero — zeroes entire economic score |
| `alphaforge/src/alphaforge/validation/target_validator.py` | 947-950 | Same missing fallback in blocker detection |

### 10.5 Fix (Safe — No Model Behavior Change)

```python
# In target_validator.py:_extract_metrics()
# Add fourth fallback:
active_trade_count = (
    met.get("active_trade_count")
    or oos.get("active_trade_count")
    or oos_trade_count
    or agg.get("total_oos_trades", 0)     # NEW: fallback for runner output
)

# exposure_pct needs computation:
total_bars = len(oos_predictions) if oos_predictions else 0
exposure_pct = (
    met.get("exposure_pct")
    or oos.get("exposure_pct")
    or (active_trade_count / total_bars * 100) if total_bars else 0.0
)
```

### 10.6 Acceptance Criteria

1. Consolidated report `metric_details.active_trade_count` matches WFV detail count
2. Consolidated report `metric_details.exposure_pct` > 0
3. GR1 no longer triggers incorrectly (economic score reflects real data)
4. All existing tests still pass
5. No model behavior, config, or threshold changes

---

## 11. Key Decision Answers

### Q1: Centralized Data Lake gerekli mi?
**Evet.** Mevcut yapı dağınık: backfill `alphaforge/` ve `lib/` arasında bölünmüş durumda. DatasetSpec, DownloadManifest, CoverageReport, DataPassport gibi temel bileşenler eksik. Tek bir `lib/data_lake/` modülü tüm bu sorumlulukları üstlenmeli.

### Q2: Backfill merkezi olmalı mı?
**Evet.** BackfillPlanner → DownloadManifest → Parallel Downloader → Checksum → Bronze → CoverageReport akışı tek bir authority'de olmalı.

### Q3: Synthetic fallback default olarak yasaklanmalı mı?
**Evet, ciddi iddialar için.** Unit test, smoke test, schema test gibi alanlarda synthetic serbest. Ama ALPHA_HAS_EDGE, MODEL_BEATS_BASELINES gibi claim'ler REAL DATA zorunluluğu getirmeli.

### Q4: Real data olmadan alpha validation yapılmalı mı?
**Hayır.** Real data olmadan yapılan alpha validation anlamsızdır. Validator zaten synthetic veriyi 25 puana kapatıyor (GR3) — bu doğru davranıştır.

### Q5: Binance public data P0 için yeterli mi?
**Evet.** Klines + funding rate + mark/index price ücretsiz, CHECKSUM korumalı, PIT safe. 5 sembol için 2022'den itibaren yeterli.

### Q6: Klines başlangıç için yeterli mi?
**Evet.** P0 için klines + funding rate yeterli. OI ve taker volume 30 günlük pencere nedeniyle backtest için uygun değil.

### Q7: Funding/OI/aggTrades ne zaman eklenmeli?
- **Funding Rate**: P0 ile birlikte hemen (8h interval, düşük hacim)
- **OI**: P1 (30 gün limitationı kabul ederek sadece context feature olarak)
- **aggTrades**: P2 (çok büyük veri hacmi, araştırma amaçlı)

### Q8: On-chain data training label'da kullanılabilir mi?
**Kesinlikle hayır.** On-chain veri asla label generation için kullanılamaz. Bu değişmez kuraldır.

### Q9: On-chain data backtest feature olarak ne şartla kullanılabilir?
**Ancak PIT testi geçerse.** Glassnode PIT testini geçerse (beklenen: PASS), sınırlı BTC/ETH metrikleri context feature olarak kullanılabilir. Santiment ve CryptoQuant için PIT riski yüksek.

### Q10: L2 vendor ne zaman satın alınmalı?
**P4 aşamasında.** Önce P0 (klines+funding), P1 (20 sembol), P2 (aggTrades research) tamamlansın. L2 verisi şu anki alpha araştırması için kritik değil.

### Q11: Metric plumbing fix önce mi, real data backfill önce mi?
**Önce metric plumbing fix.** Çünkü:
- Fix çok küçük (< 10 satır), backfill ise büyük iş
- Fix olmadan consolidated report güvenilmez, backfill sonrası da aynı hata görülür
- Fix model behavior değiştirmez, sadece raporlama doğruluğunu düzeltir

### Q12: AlphaForge ve V7 hangi ortak contractları paylaşmalı?
**DataPassport** ortak contract olmalı. AlphaForge üretir, V7 tüketir. EvidencePassport zaten bu köprüyü kuruyor — DataPassport da benzer şekilde `lib/` katmanında tanımlanmalı.

---

## 12. Final Roadmap

```
v0.30A — DatasetSpec + DataCatalog (3-5 days)
  ├── lib/data_lake/spec.py — DatasetSpec frozen dataclass
  ├── lib/data_lake/catalog.py — Catalog query/gap methods
  ├── Tests for both
  └── Integration: existing DataCatalog → new interface

v0.30B — Binance UM Data Lake Bootstrap (5-7 days)
  ├── lib/data_lake/storage.py — Storage layout + path resolution
  ├── lib/data_lake/backfill_planner.py — Gap analysis → DownloadManifest
  ├── lib/data_lake/coverage.py — CoverageReport
  ├── lib/data_lake/checksum.py — ChecksumReport
  ├── lib/data_lake/downloader.py — Multi-worker parallel download
  ├── Backfill 5 symbols: klines + funding rate (2022-present)
  └── Integration: replace alphaforge/data/backfill.py → lib/data_lake/

v0.30C — DataPassport + RealDataRequired Gate (2-3 days)
  ├── lib/data_lake/passport.py — DataPassport schema + builder
  ├── lib/evidence_engine/hard_caps.py — V11: RealDataRequired gate
  ├── alphaforge/src/alphaforge/evidence_adapter.py — DataPassport integration
  └── Validator real-data check: replace string match → passport check

v0.30D — Metric Plumbing Integrity Fix (1 day)
  ├── target_validator.py:_extract_metrics() — Add agg["total_oos_trades"] fallback
  ├── target_validator.py:exposure_pct — Add computation fallback
  ├── Tests: active_trade_count + exposure_pct > 0 in consolidated
  └── Verify: consolidated matches WFV detail

v0.30E — Real Data Baseline Evidence Control (2-3 days)
  ├── First real-data run: 5 symbols, 1h/4h, SCALP mode
  ├── Verify: consolidated report shows correct metrics
  ├── Verify: DataPassport present and correct
  ├── Verify: GR1 no longer triggers incorrectly
  └── Baseline evidence snapshot
```

### Phase Ordering Justification

**v0.30A before v0.30B** — DatasetSpec ve Catalog altyapısı olmadan backfill planner çalışamaz.

**v0.30C after v0.30B** — DataPassport'un anlamlı olması için real data'nın bir yerden gelmesi gerekir.

**v0.30D early** — Metric plumbing fix çok küçük ve bağımsız. v0.30A ile paralel yapılabilir. Backfill'i beklemez.

**v0.30E last** — Her şey çalıştıktan sonra ilk real data run'ı yapılır ve baseline oluşturulur.

---

## 13. Open Questions

1. **Binance API key mevcut mu?** Public archive için gerekmez ama real-time/fresh data için gerekebilir.
2. **OI/taker volume için 30 gün limitationı kabul edilebilir mi?** Context feature olarak evet, backtest için hayır.
3. **20 sembol backfill için disk alanı yeterli mi?** 5 sembol + 4 interval (1h/15m/4h/1d) + funding rate için ~50-100 GB tahmini. WSL2 ext4'te ~1 TB var — sorun yok.
4. **Funding rate 8h interval backtest metric'i olarak nasıl kullanılacak?** Mevcut cost model funding rate'i LOCKED_INITIAL_BASELINE olarak işliyor. Gerçek funding rate verisi ile cost model doğrulanabilir.
5. **Bronze layer'a ne zaman ihtiyaç duyulacak?** v0.30B'de bronze basit (validasyon+indeks). Silver layer sonraki versiyonlara ertelendi.

---

## 14. Do-Not-Do List

- ❌ Model tuning yapma
- ❌ Feature set değiştirme
- ❌ Optuna çalıştırma
- ❌ Yeni model ekleme
- ❌ Threshold değiştirme
- ❌ Synthetic veri ile yeni alpha claim'i üretme
- ❌ On-chain vendor satın alma
- ❌ Backfill'i araştırma yapmadan başlatma
- ❌ Mevcut pipeline logic'ini değiştirme (sadece data layer ekle)
- ❌ Config değiştirme
