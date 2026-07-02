# AlphaForge Data Contract

**Purpose:** Define the data layers AlphaForge operates on, from raw market data through normalized data, feature datasets, label datasets, and research run manifests.

**Authority:** AlphaForge owns data scope definition. Simulation owns economic truth. This document is LOCKED.

**P0.8E note:** Timeframe requirements corrected to match locked simulation profiles (`simulation/docs/profiles.md`). SCALP = 1h primary / 4h context / 15m refine. AGGRESSIVE_SCALP = 15m primary / 1h context / 5m refine. SWING = 4h primary / 1d context / 1h refine. Previous incorrect timeframes (SCALP 1m/5m, AGGRESSIVE_SCALP 1m/3m/5m) removed.

---

## Data Layers

### Layer 1: Raw Market Data

External/local source layer. NOT stored as large files in repo.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| source | string | Data provider identifier (e.g., "binance", "local_csv") |
| exchange | string | Exchange name |
| symbol | string | Trading symbol (e.g., "BTCUSDT") |
| interval | string | Candle interval (e.g., "1m", "5m", "15m", "1h", "4h", "1d") |
| start_ts | string (ISO 8601) | Start timestamp |
| end_ts | string (ISO 8601) | End timestamp |
| checksum | string | Content hash for data integrity |
| storage_uri | string | Path or URI to external storage |
| quality_flags | object | Data quality indicators |

**Storage policy:** Raw data lives outside the repo. Only data manifests and references are stored in repo.

### Layer 2: Normalized Market Data

Clean OHLCV/event layer. Standardized format regardless of source.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| symbol | string | Trading symbol |
| timestamp | string (ISO 8601) | Bar open timestamp |
| open | number | Open price |
| high | number | High price |
| low | number | Low price |
| close | number | Close price |
| volume | number | Volume |
| interval | string | Candle interval |
| quality_flags | object | Per-bar quality indicators (gaps, outliers, etc.) |

**Requirements:**
- Timestamps must be UTC.
- No duplicate bars.
- No missing bars within date range (or explicitly flagged).
- Quality flags must indicate any data issues.

### Layer 3: Feature Dataset

Mode/timeframe-aware feature matrix. Defined by FeatureSetSpec.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| feature_set_id | string | Unique identifier |
| mode | enum | SCALP, AGGRESSIVE_SCALP, SWING |
| timeframe_stack | object | { primary, context, refinement } with canonical intervals |
| feature_groups | array | Feature group identifiers |
| features | array | Individual feature specifications |
| source_dataset_refs | array | References to normalized data sources |
| leakage_policy | object | Leakage prevention rules |
| cross_sectional | object | Cross-sectional data requirements (P0.9B) |
| created_at | string (ISO 8601) | Creation timestamp |
| checksum | string | Content hash |

### Layer 4: Label Dataset

Simulation-derived economic labels. Defined by LabelDatasetSpec.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| label_dataset_id | string | Unique identifier |
| mode | enum | SCALP, AGGRESSIVE_SCALP, SWING |
| simulation_profile_id | string | Simulation profile reference |
| label_source | string | "simulation_output" |
| label_fields | object | Label field definitions (classification, regression, path_metrics, quality, cost) |
| cost_model_ref | string | Cost model version reference |
| funding_status | string | Current funding model status (DEFERRED/IMPLEMENTED/NOT_APPLICABLE) |
| no_trade_comparison | object | NO_TRADE comparison metrics |
| lineage | object | Provenance metadata |
| cross_sectional_requirements | object | P0.9B: point-in-time universe, survivorship, delisting |
| checksum | string | Content hash |

### Layer 5: Research Run Manifest

Reproducibility metadata for AlphaForge runs.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| run_id | string | Unique run identifier |
| created_at | string (ISO 8601) | Run timestamp |
| git_commit | string | Git commit hash at run time |
| data_refs | array | Data source references |
| feature_set_refs | array | Feature set references |
| label_dataset_refs | array | Label dataset references |
| simulation_profile_refs | array | Simulation profile references |
| config_hash | string | Configuration hash for reproducibility |
| command | string | Command or entrypoint used |
| limitations | array | Known limitations of this run |

---

## Timeframe Requirements Per Mode (LOCKED)

Source of truth: `simulation/docs/profiles.md` and `v7/docs/profitability_thesis.md`.

| Mode | Primary | Context | Refinement |
|------|---------|---------|------------|
| SCALP (PRIMARY) | **1h** | 4h | 15m |
| AGGRESSIVE_SCALP (PRIMARY) | **15m** | 1h | 5m |
| SWING (SECONDARY_BASELINE) | **4h** | 1d | 1h |

**Previous incorrect values removed in P0.8E:** SCALP 1m/5m and AGGRESSIVE_SCALP 1m/3m/5m were AlphaForge-invented timeframe assumptions that contradict the locked simulation profiles. These incorrect references are purged from all canonical docs and fixtures.

**If 1m/3m/5m appear anywhere:** They must be explicitly marked as DEFERRED/FUTURE and are NOT the canonical locked profile. Real research must use the locked primary timeframes above. Refinement intervals may be explored during research but are not the primary analytical unit.

---

## Cross-Sectional Data Requirements (P0.9B dependency)

Real alpha research requires multi-symbol data with:
- **Point-in-time universe snapshots:** Which symbols existed at each timestamp.
- **Symbol membership tracking:** `symbol_membership_start_ts` / `symbol_membership_end_ts`.
- **Delisting policy:** How symbols that delist during the period are handled.
- **Missing candle policy:** How gaps are filled or flagged.
- **Survivorship bias flag:** Explicit indicator that filtering to survivors-only is forbidden.
- **Cross-sectional rank features:** Relative strength, lead-lag scores, cross-symbol rankings.
- **UTC grid alignment:** All symbols aligned to common UTC timestamp grid.

These are NOT implemented in P0.8E. They are contract requirements for P0.9B data pipeline.

---

## Data Quality Flags

Every data layer must carry quality flags:

| Flag | Meaning |
|------|---------|
| MISSING_BARS | Gaps in bar sequence detected |
| PRICE_SPIKE | Extreme price movement detected |
| VOLUME_SPIKE | Extreme volume detected |
| STALE_DATA | Data may be delayed or incomplete |
| OUT_OF_HOURS | Bar outside normal trading hours |
| SURVIVORSHIP_BIAS_RISK | Universe may be survivors-only |
| TBD | Quality assessment pending |

---

## Storage Policy

**In repo:** Schemas, fixtures, manifests, configuration files, report documents.
**Outside repo:** Raw market data, normalized datasets, feature matrices, label datasets, model binaries.

Full details: [storage_policy.md](storage_policy.md)

---

## Minimum Metadata Requirements

Every data artifact must include:

| Field | Required |
|-------|----------|
| source | YES |
| symbol | YES |
| interval | YES |
| start_ts | YES |
| end_ts | YES |
| timezone | YES (must be UTC) |
| checksum | YES |
| generation_command | YES (for derived data) |

---

## Feature Provenance

Every feature group in the pipeline maps to a source module and a data dependency. This table documents the provenance of the two groups implemented beyond the core OHLCV feature set (Issue #184).

| Feature Group | Module | Status | Source Data | Output Keys | Count | Notes |
|---------------|--------|--------|-------------|-------------|-------|-------|
| PERPETUAL_FUNDING | `alphaforge/features/funding.py` | ACTIVE | OHLCV (close, high, low, volume); optional real `funding_rate` column | `funding_rate`, `funding_rate_ma_N`, `funding_rate_vol_N`, `funding_rate_zscore_N`, `funding_rate_change_N`, `open_interest_proxy_N`, `funding_oi_divergence_N` | 7 | OHLCV-derived funding proxy when real funding_rate is absent. OI proxy (#119) uses volume * \|price change\|. Uses per-mode windows from `_MODE_DEFAULTS`. |
| CROSS_SECTIONAL_RANK | `alphaforge/features/cross_sectional_rank.py` | DEFERRED (P0.9B) | Multi-symbol OHLCV across >= 2 symbols (close, high, low, volume) | `rank_momentum_1h`, `rank_momentum_4h`, `rank_momentum_24h`, `rank_volatility`, `rank_volume`, `correlation_with_median`, `correlation_zscore` | 7 | Cross-sectional rank requires multi-symbol data pipeline (P0.9B). Wired in `FEATURE_GROUP_MAP` but not computed in single-symbol `compute_features()`. Re-enable when multi-symbol data is available. |

Both groups are wired into `alphaforge/features/pipeline.py`:
- `FEATURE_GROUP_MAP` includes entries for both groups with their compute functions.
- `_MODE_DEFAULTS` contains per-mode window parameters for all three trading modes (SWING, SCALP, AGGRESSIVE_SCALP).
- `FeatureGroup` enum entries are `PERPETUAL_FUNDING` and `CROSS_SECTIONAL_RANK`.
- Only `compute_funding_group()` is called in `compute_features()`. `compute_cross_sectional_rank_group()` requires a `Dict[str, Dict[str, np.ndarray]]` multi-symbol input and is deferred.

Total pipeline output: 67 features across 10 active groups (9 computed + 1 active Funding group). Cross-Sectional Rank is the 11th group but DEFERRED.

## Related Docs

- [ai_summary.md](ai_summary.md)
- [feature_contract.md](feature_contract.md)
- [label_contract.md](label_contract.md)
- [storage_policy.md](storage_policy.md)
- [validation_contract.md](validation_contract.md)

## Related Contracts

- [../../contracts/schemas/alphaforge/feature_set_spec.schema.json](../../contracts/schemas/alphaforge/feature_set_spec.schema.json)
- [../../contracts/schemas/alphaforge/label_dataset_spec.schema.json](../../contracts/schemas/alphaforge/label_dataset_spec.schema.json)
- [../../contracts/mappings/simulation_to_alphaforge.md](../../contracts/mappings/simulation_to_alphaforge.md)
- [../../simulation/docs/profiles.md](../../simulation/docs/profiles.md) — locked mode profiles (source of truth for timeframes)

## Forbidden Assumptions

- Raw data is NOT stored in repo.
- External APIs are NOT called during authority lock tasks.
- Data quality flags are NOT optional — they are required.
- AlphaForge data timeframes MUST match simulation profile timeframes — no divergence allowed.
- Cross-sectional research requires point-in-time universe data — NOT single-symbol.

## Open Holds

- Actual data sources not yet configured (P0.9B implementation phase).
- Funding model: ACTIVE (OHLCV-derived proxy). Real funding_rate integration: P0.9B.
- Cross-sectional data layer is NOT implemented — contract requirement only.
- Cross-sectional rank features (cross_sectional_rank group) are wired but DEFERRED — require P0.9B multi-symbol pipeline.
- Survivorship bias controls are NOT implemented — contract requirement only.
