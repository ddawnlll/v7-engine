# V7 AnalysisRequest Contract

## Purpose

This document defines the **`AnalysisRequest`** contract for V7.

`AnalysisRequest` is the atomic **runtime-to-engine analysis input** contract.

It answers one question:

> What exact market state and runtime context must be provided so the engine can evaluate one market state consistently, safely, and replay-compatibly?

This document defines **analysis input semantics only**.

It does not define:

- execution commands
- order placement behavior
- training dataset control flow
- label semantics
- event persistence semantics
- outcome semantics
- portfolio allocation logic

Those belong to other documents.

---

## Core Position

V7 keeps the strong V6 request principle:

- one atomic request
- one evaluated market state
- one engine response

But V7 tightens and extends it in four ways:

1. **canonical-state centered**
2. **interval-aware through explicit state views**
3. **batch/session-aware through lineage fields**
4. **lighter and easier to analyze than the V6 section-heavy shape**

The request remains an **analysis boundary**, not a portfolio controller or execution object.

It also is not a simulation execution request for the model. Normal inference requests may include fields needed for runtime routing and model inference, but they must not ask the model to run simulation. Simulation/replay/training adapters may build deterministic runtime simulation inputs from request/state lineage, but that simulation path is runtime-owned and side-effect-free.

---

## Role In The System

`AnalysisRequest` sits at the runtime ↔ engine boundary.

### Runtime owns
- orchestration
- request assembly
- state construction
- persistence
- execution control
- scan scheduling
- batch/session coordination

### Engine owns
- state interpretation
- scoring
- calibrated decision reasoning
- uncertainty-aware analysis output

`AnalysisRequest` must preserve that boundary.

---

## In Scope

`AnalysisRequest` defines:

- request identity
- analysis scope
- symbol and interval identity
- canonical market state
- explicit state views
- deterministic annotations as context only
- runtime context relevant to analysis
- data quality and freshness visibility
- degraded-input visibility
- lightweight portfolio/risk context where needed
- batch/session lineage metadata

---

## Out of Scope

`AnalysisRequest` does **not** define:

- trade execution commands
- portfolio ranking outputs
- position sizing instructions
- capital allocation instructions
- future outcomes
- simulation execution loops or future simulation payloads
- labels
- realized PnL or realized R
- event storage schema
- outcome storage schema
- training dataset row format
- multiprocessing or GPU execution topology

---

## Atomic Unit Rule

A valid V7 `AnalysisRequest` evaluates:

- **one symbol**
- **one primary interval**
- **one timestamped market state**

This rule stays first-class.

V7 does **not** make the atomic request multi-symbol.

Fast scanning, centralized multi-symbol inference, and GPU batching should be handled by higher-level grouping objects such as:

- `AnalysisBatchRequest`
- `AnalysisBatchResult`
- `DecisionSession`

The atomic request remains audit-friendly and replay-friendly.

---

## Scope And Interval Rule

V7 `AnalysisRequest` is **scope-aware** and **interval-aware**, but still atomic.

That means:

- one request targets exactly one `model_scope`
- the request carries `requested_trade_mode` and the selected/declared `model_scope`
- the request has **one `primary_interval`** for that scope
- the request may include `context_intervals` and `refinement_intervals` as contextual state views
- the request may carry `label_horizon_family` in training/evaluation or replay context for lineage, but runtime inference must not use it as future truth
- the request does **not** ask all scopes to compete
- the request does **not** represent multiple independent decision intervals in one atomic object

First recommended scopes:

- `SWING`: `primary_interval` `4h`, `context_intervals` `1d`, `refinement_intervals` `1h`, `label_horizon_family` swing horizon
- `SCALP`: `primary_interval` `15m`, `context_intervals` `1h`, `refinement_intervals` `5m`, `label_horizon_family` scalp horizon
- `AGGRESSIVE_SCALP`: `primary_interval` `1m` or `3m`, `context_intervals` `5m` + `15m`, `refinement_intervals` `1m/3m` micro context where applicable, `label_horizon_family` immediate continuation / very short horizon

The runtime `scope_router` chooses the scope before model inference. If `requested_trade_mode` and `model_scope` are incompatible, runtime/result handling must reject the request/result or downgrade to safe no-trade behavior as a visible `scope_mismatch`.

This keeps the request compact while still supporting V7’s multi-view state design within one selected scope.

---

## Top-Level Shape

The semantic shape of `AnalysisRequest` should be:

```text
AnalysisRequest
├── contract
├── identity
├── scope
├── canonical_state
├── state_views
├── deterministic_context
├── runtime_context
├── quality_and_freshness
├── degradation_context
├── portfolio_context
├── risk_context
└── lineage
```

This is intentionally simpler than the V6 split across many parallel sections.

---

## 1. Contract

This section defines the request as a versioned contract artifact.

### Required fields
- `contract_version`
- `state_schema_version`
- `snapshot_builder_version`
- `request_kind`

### Purpose
These fields make replay/live parity and contract evolution explicit.

### Notes
- `contract_version` identifies the request contract semantics
- `state_schema_version` identifies the **semantic meaning of `canonical_state`**
- `snapshot_builder_version` identifies the builder logic used
- `request_kind` distinguishes contexts such as:
  - `live_scan`
  - `paper_scan`
  - `replay_eval`
  - `shadow`
  - `validation`

### What `state_schema_version` versions

`state_schema_version` versions the meaning of the `canonical_state` subtree, including:

- which sub-sections exist
- field names and field ownership
- unit conventions
- enum meanings
- interpretation of derived metrics
- required vs optional state elements
- compatibility assumptions between live and replay state construction

It should be bumped when the **meaning** of canonical state changes materially, not for every implementation-only refactor.

---

## 2. Identity

This section uniquely identifies one request instance.

### Required fields
- `request_id`
- `timestamp_utc`

### Recommended fields
- `run_id`
- `trace_id`

### Optional fields
- `parent_decision_event_id`

### `parent_decision_event_id`

This field is optional because not every request is a fresh standalone evaluation.

Typical uses:
- re-evaluation of a previously recorded decision
- watch or follow-up analysis on an existing decision lineage
- explicit retry flows where runtime wants lineage continuity
- shadow or comparison flows attached to an earlier event family

If the request is a fresh first-pass evaluation, this field should usually be null or omitted.

### Rules
- `request_id` must be unique
- `timestamp_utc` is non-negotiable
- identity must remain stable across logs and replay lineage

---

## 3. Scope

This section defines what instrument and operating mode the request belongs to.

### Required fields
- `symbol`
- `requested_trade_mode`
- `model_scope`
- `primary_interval`
- `analysis_mode`

### Strongly recommended fields
- `context_intervals`
- `refinement_intervals`
- `label_horizon_family` where relevant to training/evaluation/replay lineage

### Optional fields
- `exchange`
- `market_type`
- `base_asset`
- `quote_asset`
- `symbol_class`

### Rules
- `symbol`, `requested_trade_mode`, `model_scope`, and `primary_interval` remain first-class required fields
- one request targets one model scope and does not make all scopes compete
- `primary_interval` and `label_horizon_family` must be compatible with `model_scope`
- the scope is descriptive/routing input only
- these fields do not turn the request into a ranking request

---

## 4. Canonical State

This is the most important part of the request.

### Required field
- `canonical_state`

### Purpose
`canonical_state` is the fully assembled market state the engine should evaluate.

### Canonical state responsibilities

`canonical_state` should contain, in one stable internal structure:

- recent raw market window
- derived local state
- higher-timeframe context
- volatility and regime context
- symbol and interval identity
- data-quality and freshness metadata
- optional runtime-safe context where justified

### Rules
- deterministic for the same visible history
- no future leakage
- same semantics across live, replay, evaluation, and analysis reuse
- compact enough to stay inspectable
- extensible through additive schema evolution

### Minimal semantic shape

```text
canonical_state
├── raw_window
├── derived_state
├── context
├── quality
└── metadata
```

### Recommended canonical state schema

#### `raw_window`
Contains the raw local market window.

Recommended fields:
- `candles`
- `window_length`
- `window_start_utc`
- `window_end_utc`

Each candle should minimally contain:
- `open`
- `high`
- `low`
- `close`
- `volume`
- `close_time_utc`

Optional candle fields:
- `quote_volume`
- `trade_count`
- `taker_buy_base_volume`
- `taker_buy_quote_volume`

#### `derived_state`
Contains state derived from the visible market window.

Recommended sub-sections:
- `indicator_state`
- `candle_geometry`
- `volatility_state`
- `structure_state`
- `session_state`
- `cyclical_time_features`

#### `context`
Contains non-primary but decision-relevant context.

Recommended sub-sections:
- `higher_timeframe`
- `regime_context`
- `symbol_context`

Examples:
- HTF bias
- HTF trend strength
- HTF freshness
- volatility regime
- local structure regime

#### `quality`
Contains state-quality and freshness semantics.

Recommended fields:
- `stale_flag`
- `data_source`
- `data_quality_flags`
- `missing_context_flags`
- `snapshot_validity`
- `partial_state_flag`
- `latest_bar_timestamp_utc`
- `htf_freshness`

#### `metadata`
Contains compact semantic metadata needed to interpret the state.

Recommended fields:
- `symbol`
- `primary_interval`
- `state_timestamp_utc`
- `snapshot_builder_version_seen`
- `state_schema_version_seen`

### Design note
V7 prefers a strong `canonical_state` instead of scattering meaning across too many parallel top-level sections.

---

## 5. State Views

This section makes interval-aware context explicit.

### Recommended field
- `state_views`

### Typical views
- `primary`
- `higher_timeframe`
- `refinement`

### Rules
- one view remains primary
- contextual views must be explicitly named
- contextual views do not become separate independent decision contracts
- adding a new view should be additive and versioned

### Example semantic shape

```text
state_views
├── primary: 4h
├── htf: 1d
└── refinement: 1h
```

This is how V7 supports multi-view analysis without collapsing the atomic request. It produces one fused decision surface, not an average of separate interval outputs.

---

## 6. Deterministic Context

This section carries structured deterministic annotations.

### Recommended field
- `deterministic_context`

### Example contents
- regime hints
- structural annotations
- volatility bucket
- explicit warning flags
- liquidity/risk flags
- allowed/blocked action hints where still supported

### Rules
- annotation only
- not labels
- not future truth
- not silent authority
- must remain visible if used

Deterministic context may help the engine reason, but it must not silently redefine market truth.

### Distinction from `canonical_state.context`

The distinction is:

- `canonical_state.context` is part of the **market-state description**
- `deterministic_context` is a **runtime-supplied annotation layer**

Examples:
- HTF trend, volatility regime, or structure regime that describe the market belong in `canonical_state.context`
- runtime heuristics, explicit allowed/blocked-action hints, or operational annotations belong in `deterministic_context`

A good rule is:
- if the field describes the market itself, prefer `canonical_state.context`
- if the field describes runtime-owned interpretation aid, prefer `deterministic_context`

---

## 7. Runtime Context

This section describes runtime-owned analysis context that is not part of the market itself.

### Recommended field
- `runtime_context`

### Example contents
- `source_context`
- `requested_by`
- `paper_or_live_mode`
- `runtime_phase`
- `engine_budget_hint`
- `engine_timeout_ms`

### Rules
- useful for safe analysis
- must not embed execution commands
- must not redefine scoring semantics
- low-latency live vs offline replay differences may appear here

---

## 8. Quality And Freshness

This section makes input quality explicit.

### Recommended field
- `quality_and_freshness`

### Example contents
- `stale_flag`
- `data_source`
- `data_quality_flags`
- `missing_context_flags`
- `snapshot_validity`
- `partial_state_flag`
- `latest_bar_timestamp_utc`
- `htf_freshness`

### Rules
- degraded or stale state must be visible
- quality flags must be structured, not hidden in logs
- invalid state must be detectable before engine routing where possible

### Relationship to `canonical_state.quality`
If the same semantics appear in both places:
- `canonical_state.quality` is the embedded state view
- `quality_and_freshness` is the top-level runtime-visible request surface

These must remain semantically consistent.

---

## 9. Degradation Context

This section exists so degraded request assembly is explicit.

### Recommended field
- `degradation_context`

### Example contents
- missing HTF context
- fallback builder path used
- incomplete auxiliary view
- partial state due to data issue
- reduced-confidence assembly reason

### Rules
- explicit if present
- machine-readable and human-readable
- no silent degraded path
- degradation visibility must survive into downstream lineage where needed

This is separate from general quality flags because V7 wants degraded behavior to remain clearly auditable.

---

## 10. Portfolio Context

This section is optional and lightweight.

### Recommended field
- `portfolio_context`

### Example contents
- open-position count
- symbol exposure tier
- cluster/correlation bucket hint
- drawdown state tier
- portfolio pressure tier

### Rules
- contextual only
- not allocation control
- not ranking control
- not position sizing
- not portfolio engine governance

This supports V7’s centralized multi-symbol world without collapsing the request into a portfolio object.

---

## 11. Risk Context

This section is also optional and lightweight.

### Recommended field
- `risk_context`

### Example contents
- cooldown-active flag
- exposure-cap-near flag
- operational caution tier
- runtime risk regime tag

### Rules
- advisory only
- no hidden execution policy
- no order-management internals
- no position-sizing instructions

---

## 12. Lineage

This section connects atomic requests to broader centralized scans or evaluation sessions.

### Recommended fields
- `analysis_batch_id`
- `decision_session_id`
- `batch_rank_context` (optional)

### Purpose
These fields support:
- centralized scanning
- GPU batch inference
- replay batch audit
- session-level grouping
- later portfolio-aware review

### Rules
- identity only
- not control semantics
- optional for atomic validity
- explicit if used

---

## Required vs Optional

### Required in first V7 request
- `contract.contract_version`
- `contract.state_schema_version`
- `contract.snapshot_builder_version`
- `identity.request_id`
- `identity.timestamp_utc`
- `scope.symbol`
- `scope.requested_trade_mode`
- `scope.model_scope`
- `scope.primary_interval`
- `scope.analysis_mode`
- `canonical_state`

### Strongly recommended in first V7 request
- `state_views`
- `quality_and_freshness`
- `runtime_context`
- `degradation_context` when degraded
- `lineage.analysis_batch_id`
- `lineage.decision_session_id`

### Optional for controlled later expansion
- `deterministic_context`
- `portfolio_context`
- `risk_context`
- broader market context
- specialized auxiliary views

---

## What Must Not Be In The Request

To keep the contract disciplined, the following must **not** be embedded into `AnalysisRequest`:

### 1. Multiple symbols
Do not make one atomic request evaluate many symbols.

### 2. Multiple independent decision intervals
Do not make one atomic request represent separate decisions for `1h`, `4h`, and `1d` at once. An atomic request includes multiple state views but must produce one unified, primary-anchored decision, not an average of separate interval outputs.

### 3. Future outcomes or simulation loops
No future prices, labels, realized results, replay-only truth, or model-owned simulation execution loops.

### 4. Execution commands
No order placement instructions, leverage commands, or broker mutation payloads.

### 5. Allocation control
No target capital percentage, no portfolio priority override, no target position size.

### 6. Hidden debug blobs
If a field matters, it must have explicit section ownership and semantic meaning.

### 7. Runtime execution topology
No multiprocessing or GPU-worker details in the request contract.

---

## Validation Rules

`AnalysisRequest` should be validated before routing to the engine.

At minimum, validation should check:

- required fields exist
- `symbol`, `requested_trade_mode`, `model_scope`, `primary_interval`, and `analysis_mode` are valid
- `requested_trade_mode` is compatible with `model_scope`
- `primary_interval`, `context_intervals`, `refinement_intervals`, and any `label_horizon_family` are compatible with `model_scope`
- `timestamp_utc` is present and parseable
- contract versions are supported
- `canonical_state` is present and structurally valid
- contextual state views do not conflict with primary scope
- degraded flags and quality flags are internally consistent
- no forbidden future-derived fields are present

### Missing-section behavior
If a required section is missing or invalid, runtime should reject the request before engine routing unless an explicitly documented degraded path exists.

Fallback policy belongs in runtime policy docs, not in this contract.

---

## Example Semantic Shape

```json
{
  "contract": {
    "contract_version": "v7-0.2",
    "state_schema_version": "state-0.2",
    "snapshot_builder_version": "snapshot-0.2",
    "request_kind": "live_scan"
  },
  "identity": {
    "request_id": "req_123",
    "run_id": "scan_456",
    "timestamp_utc": "2026-04-05T12:00:00Z"
  },
  "scope": {
    "symbol": "BTCUSDT",
    "requested_trade_mode": "SWING",
    "model_scope": "SWING",
    "primary_interval": "4h",
    "context_intervals": ["1d"],
    "refinement_intervals": ["1h"],
    "label_horizon_family": "swing_horizon",
    "analysis_mode": "live",
    "exchange": "BINANCE",
    "market_type": "PERP"
  },
  "canonical_state": {
    "raw_window": {
      "window_length": 256,
      "window_start_utc": "2026-03-24T08:00:00Z",
      "window_end_utc": "2026-04-05T12:00:00Z",
      "candles": [
        {
          "open": 100.0,
          "high": 105.0,
          "low": 99.0,
          "close": 104.0,
          "volume": 1200.0,
          "close_time_utc": "2026-04-05T08:00:00Z"
        }
      ]
    },
    "derived_state": {
      "indicator_state": {},
      "candle_geometry": {},
      "volatility_state": {},
      "structure_state": {},
      "session_state": {}
    },
    "context": {
      "higher_timeframe": {
        "interval": "1d",
        "bias": "BULLISH",
        "trend_strength": 0.71,
        "freshness": "FRESH"
      },
      "regime_context": {
        "regime_label": "TRENDING",
        "volatility_bucket": "MEDIUM"
      },
      "symbol_context": {
        "symbol": "BTCUSDT",
        "primary_interval": "4h"
      }
    },
    "quality": {
      "stale_flag": false,
      "data_source": "fresh_exchange",
      "data_quality_flags": [],
      "missing_context_flags": [],
      "snapshot_validity": "VALID",
      "partial_state_flag": false,
      "latest_bar_timestamp_utc": "2026-04-05T08:00:00Z",
      "htf_freshness": "FRESH"
    },
    "metadata": {
      "symbol": "BTCUSDT",
      "primary_interval": "4h",
      "state_timestamp_utc": "2026-04-05T12:00:00Z",
      "snapshot_builder_version_seen": "snapshot-0.2",
      "state_schema_version_seen": "state-0.2"
    }
  },
  "state_views": {
    "primary": "4h",
    "higher_timeframe": "1d"
  },
  "runtime_context": {
    "source_context": "autonomous_loop",
    "requested_by": "runtime",
    "paper_or_live_mode": "PAPER",
    "engine_budget_hint": "low_latency_live",
    "engine_timeout_ms": 500
  },
  "quality_and_freshness": {
    "stale_flag": false,
    "data_source": "fresh_exchange",
    "data_quality_flags": [],
    "snapshot_validity": "VALID"
  },
  "degradation_context": null,
  "lineage": {
    "analysis_batch_id": "batch_001",
    "decision_session_id": "session_001"
  }
}
```

This example is semantic guidance, not final transport syntax.

### Scope Variant Examples

These compact examples show only the scope-specific fields that differ by `model_scope`; all other request sections keep the same atomic contract shape.

```json
{
  "scope": {
    "symbol": "BTCUSDT",
    "requested_trade_mode": "SCALP",
    "model_scope": "SCALP",
    "primary_interval": "15m",
    "context_intervals": ["1h"],
    "refinement_intervals": ["5m"],
    "label_horizon_family": "scalp_horizon",
    "analysis_mode": "live"
  },
  "state_views": {
    "primary": "15m",
    "higher_timeframe": "1h",
    "refinement": "5m"
  }
}
```

```json
{
  "scope": {
    "symbol": "BTCUSDT",
    "requested_trade_mode": "AGGRESSIVE_SCALP",
    "model_scope": "AGGRESSIVE_SCALP",
    "primary_interval": "1m",
    "context_intervals": ["5m", "15m"],
    "refinement_intervals": ["1m"],
    "label_horizon_family": "immediate_continuation_short_horizon",
    "analysis_mode": "live"
  },
  "state_views": {
    "primary": "1m",
    "context": ["5m", "15m"],
    "refinement": "1m"
  }
}
```

A request with `requested_trade_mode = "SCALP"` and `model_scope = "SWING"` is a `scope_mismatch` and must not be routed silently to either artifact family.

---

## V6 to V7 Mapping Note

The V7 request keeps the V6 semantic ingredients but organizes them differently.

### Typical mapping
- `market_window` → `canonical_state.raw_window`
- `derived_state` → `canonical_state.derived_state`
- `htf_context` → `canonical_state.context.higher_timeframe`
- `quality_and_freshness` → `canonical_state.quality` and top-level `quality_and_freshness`
- `runtime_context` → top-level `runtime_context`
- `execution_context` → split into lightweight `portfolio_context` and `risk_context` where needed

This is how V7 keeps V6’s concreteness while moving to a more compact canonical-state model.

---

## Evolution Rules

V7 request evolution should follow these rules:

1. prefer additive fields over breaking renames
2. keep old meanings stable during transition windows
3. bump `contract_version` when contract semantics change materially
4. bump `state_schema_version` when canonical-state meaning changes materially
5. bump `snapshot_builder_version` when state construction changes in replay/live-parity-relevant ways
6. document deprecations explicitly

A stable contract must remain evolvable.

---

## Final Position

`AnalysisRequest` in V7 should stay simple in principle:

- one atomic request
- one symbol
- one primary interval
- one canonical market state
- explicit contextual state views
- explicit quality and degradation visibility
- optional lightweight portfolio/risk context
- optional batch/session lineage
- no future truth
- no execution-control collapse

This keeps the strongest V6 request principles while adapting the contract for V7’s centralized, interval-aware, batch-capable architecture.
