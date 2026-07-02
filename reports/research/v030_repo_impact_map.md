# v0.30 — Repo Impact Map

**Date:** 2026-07-02
**Status:** RESEARCH_COMPLETE
**Prerequisite:** All v0.30 research reports

---

## 1. Module Impact Summary

| Module | Phase | Impact Type | Details |
|--------|-------|-------------|---------|
| `lib/data_lake/` | v0.30A-C | **NEW** | Core data lake module (6-8 new files) |
| `lib/market_data/catalog.py` | v0.30A | EXTEND | Add gap analysis methods |
| `lib/evidence_engine/hard_caps.py` | v0.30C | EXTEND | Add V11 RealDataRequired gate |
| `lib/evidence_engine/evidence_passport.py` | v0.30C | EXTEND | Optional DataPassport field |
| `alphaforge/data/backfill.py` | v0.30B | MODIFY | Optionally delegate to lib/data_lake/downloader |
| `alphaforge/data/integrity.py` | v0.30B | MODIFY | Integrate with ChecksumReport |
| `alphaforge/validation/target_validator.py` | v0.30C-D | **MODIFY** | DataPassport check + metric plumbing fix |
| `alphaforge/validation/walk_forward_runner.py` | v0.30D | MODIFY | Optional: add active_trade_count to aggregate_metrics |
| `alphaforge/evidence_adapter.py` | v0.30C | MODIFY | DataPassport integration |
| `alphaforge/reports/empirical.py` | v0.30D | MODIFY | Optional: add total_oos_trades fallback |
| `contracts/` | v0.30C | EXTEND | DataPassport schema if cross-domain needed |
| `data_lake/` | v0.30B | **NEW** | Storage directory (raw/bronze/silver/manifests) |

---

## 2. New Files Detail

### `lib/data_lake/` — New Module

| File | Phase | Purpose | Dependencies |
|------|-------|---------|-------------|
| `__init__.py` | A | Public API exports, version | — |
| `spec.py` | A | DatasetSpec frozen dataclass | `dataclasses`, `datetime` |
| `catalog.py` | A | Extended DataCatalog with gap analysis | `lib/market_data/catalog` |
| `storage.py` | B | DataLakePaths, path resolution | `pathlib` |
| `downloader.py` | B | ParallelDownloader, DownloadManifest | `concurrent.futures`, `urllib` |
| `coverage.py` | B | CoverageReport | `dataclasses` |
| `checksum.py` | B | ChecksumReport | `hashlib`, `pathlib` |
| `gateway.py` | B | DataGateway unified read interface | `pandas`, `pyarrow` |
| `passport.py` | C | DataPassport schema + builder | `dataclasses`, `hashlib` |

### `data_lake/` — Storage Directory

```
data_lake/
├── raw/
│   └── binance/um/
│       ├── klines/BTCUSDT/1h/2022/01.parquet
│       └── fundingRate/BTCUSDT/2022/01.parquet
├── bronze/
│   └── binance/um/...
├── silver/               (future)
└── manifests/
    ├── dataset_specs/
    ├── coverage_reports/
    └── checksum_reports/
```

---

## 3. Modified Files Detail

### `lib/market_data/catalog.py` — EXTEND (v0.30A)

**Additions:**
```python
def find_gaps(self, spec: DatasetSpec) -> list[TimeRange]:
def coverage(self, spec: DatasetSpec) -> CoverageReport:
```

**Backward compatibility:** All existing methods unchanged.

### `lib/evidence_engine/hard_caps.py` — EXTEND (v0.30C)

**Additions:**
```python
REAL_DATA_REQUIRED_CLAIMS = set(...)
class RealDataGate: ...
V11_REAL_DATA_REQUIRED: HardCapRule = ...
```

### `alphaforge/validation/target_validator.py` — MODIFY (v0.30C-D)

**Changes (v0.30C):**
- `_extract_metrics()`: Add DataPassport-based `is_synthetic` detection
- Replace string-matching `is_synthetic` with passport check

**Changes (v0.30D):**
- `_extract_metrics()`: Add `agg.get("total_oos_trades", 0)` fallback for active_trade_count
- `_extract_metrics()`: Add exposure_pct computation from active_trade_count / total_bars
- GR1 guardrail: verify economic score correctly computed
- Blocker detection: same fallback at line ~947-950

**No changes to:**
- Scoring logic
- Thresholds
- Claim status logic
- Schema validation

### `alphaforge/validation/walk_forward_runner.py` — MODIFY (v0.30D, optional)

**Optional additions:**
```python
aggregate_metrics["active_trade_count"] = total_active_trades
aggregate_metrics["exposure_pct"] = total_active_trades / total_oos_bars * 100
```

Forward compatibility — downstream consumers can find metrics at either location.

### `alphaforge/evidence_adapter.py` — MODIFY (v0.30C)

**Changes:**
- `build_alphaforge_passport()`: Accept optional `data_passport: DataPassport`
- Attach DataPassport to EvidencePassport
- Set `real_data_verified` flag based on passport check

---

## 4. No-Change Zones

The following MUST NOT be modified during v0.30:

| Module | Reason |
|--------|--------|
| `simulation/` | No data layer changes needed |
| `v7/` pipeline | No contract or pipeline logic changes |
| `runtime/` | No operational changes |
| `interface/` | No UI changes |
| `alphaforge/features/` | Feature pipeline unaffected |
| `alphaforge/labels/` | Label logic unaffected |
| `alphaforge/models/` | Model training unaffected |
| `alphaforge/dataset/` | Dataset assembly unaffected |
| Any config file | Config changes explicitly excluded |
| Any threshold | Threshold changes explicitly excluded |

---

## 5. Integration Points

```
DataLake ───> AlphaForge
  │               │
  │    DataGateway.read_klines()
  │    DataPassport.from_catalog()
  │               │
  │               v
  │         EvidenceAdapter
  │         (attaches passport)
  │               │
  │               v
  │         EvidencePassport
  │         (V7 consumption)
  │
  └──> V7 (via Evidence Engine)
       GateMapper reads DataPassport
       RealDataGate blocks synthetic
```

---

## 6. File Count Summary

| Action | Count |
|--------|-------|
| New files (code) | 9 |
| New files (reports) | 6 |
| Modified files | 6 |
| New directories | 2 (`lib/data_lake/`, `data_lake/`) |
| Unchanged modules | 12+ |
| **Total touch points** | **17 new + 6 modified** |
