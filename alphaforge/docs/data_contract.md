# AlphaForge Data Contract

**Purpose:** Define the data layers AlphaForge operates on, from raw market data through normalized data, feature datasets, label datasets, and research run manifests.

**Authority:** AlphaForge owns data scope definition. Simulation owns economic truth. This document is LOCKED.

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
| interval | string | Candle interval (e.g., "1m", "5m", "15m", "1h", "4h") |
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
| timeframe_stack | array | Timeframes used (e.g., ["5m", "15m", "1h"]) |
| feature_groups | array | Feature group identifiers |
| features | array | Individual feature specifications |
| source_dataset_refs | array | References to normalized data sources |
| leakage_policy | object | Leakage prevention rules |
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
| label_fields | object | Label field definitions |
| cost_model_ref | string | Cost model version reference |
| funding_status | string | Current funding model status |
| no_trade_comparison | object | NO_TRADE comparison metrics |
| lineage | object | Provenance metadata |
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

## Timeframe Requirements Per Mode

| Mode | Primary Timeframes | Secondary Timeframes |
|------|-------------------|---------------------|
| SCALP | 1m, 5m | 15m, 1h (context) |
| AGGRESSIVE_SCALP | 1m, 3m, 5m | 15m (context) |
| SWING | 1h, 4h | 1d (context) |

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

## Forbidden Assumptions

- Raw data is NOT stored in repo.
- External APIs are NOT called during authority lock tasks.
- Data quality flags are NOT optional — they are required.

## Open Holds

- Actual data sources not yet configured (implementation phase).
- Funding model DEFERRED — impacts label cost semantics.
