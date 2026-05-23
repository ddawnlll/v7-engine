# P0.5 — Shared Lib Foundation (Focused)

# Part 1 — Phase Plan

## 0. TL;DR

**Phase:** `P0.5`
**One-line goal:** Create a minimal `lib/` with only the primitives that are **nearly identical usage** between v7 and alphaforge: Binance data fetching, pure math indicators, basic cost formulas, and time utilities.
**Scope rule:** If a primitive is used differently by v7 vs alphaforge, it stays in its owning package. `lib/` is curated, not comprehensive.
**Blast radius:** `lib/`, `docs/lib/`, existing data utilities that should be migrated.
**Done when:** All acceptance criteria pass.

---

## 1. Header

| Field | Value |
|---|---|
| Phase | `P0.5` |
| Title | `Shared Lib Foundation (Focused)` |
| Status | `Planned` |
| Last updated | `2026-05-23` |
| Primary focus | `Minimal lib/ for truly shared primitives only` |
| Product-code changes | `Allowed` |

---

## 2. What Goes in lib/

| Module | Contents | Why Shared |
|---|---|---|
| `market_data/binance/` | Binance HTTP client, klines service, funding service, market data service | Raw data fetching is identical |
| `market_data/contracts.py` | KlineRecord, MarketDataResult, DataQualityReport | Standard schema shared by both systems |
| `market_data/quality.py` | Gap/duplicate detection | Same quality rules |
| `indicators/atr.py` | `compute_atr()` | Pure math, identical |
| `indicators/returns.py` | Log/simple returns | Pure math, identical |
| `indicators/volatility.py` | Rolling std, range-based vol | Pure math, identical |
| `indicators/rolling.py` | Generic rolling window | Utility, identical |
| `costs/fees.py` | Maker/taker fee estimation | Basic formulas, identical |
| `costs/slippage.py` | `get_slippage()` | Basic estimation, identical |
| `time/intervals.py` | Interval string ↔ minutes | Utility, identical |
| `time/folds.py` | `generate_folds()` | Temporal walk-forward, identical |

## 3. What Does NOT Go in lib/

| Thing | Reason |
|---|---|
| Regime enums/detectors | V7 uses for policy; alphaforge uses for features. Different semantics. |
| R-multiple | V7 = ATR+mode truth; research = fixed%. Not the same thing. |
| IO utilities | Each system writes output differently. |
| Generic serialization | Premature. Add when needed. |
| Cache abstractions | Each system caches differently. |
| Adapters | Owned by v7 and alphaforge respectively. |

## 4. Dependency

| Phase | Depends On |
|---|---|
| P0.5 | P0 |

Downstream phases that use lib primitives (P1's data contracts, P2's simulation, P3's features, P4's dataset) now depend on P0.5.

## 5. Acceptance Criteria

- `lib/` skeleton exists with only the modules listed above
- Binance client does NOT live in v7 or alphaforge — it's in `lib/market_data/binance/`
- Pure math functions (ATR, returns, vol) live in `lib/indicators/` not in any system package
- Fee/slippage estimation lives in `lib/costs/` not in simulation or labels
- Fold generation lives in `lib/time/` not in dataset assembly
- No regime, risk, IO, or adapter logic lives in lib/
- Import-boundary test passes: `lib/` must NOT import v7 or alphaforge
- Docs clearly state what's shared and what's not (this file + lib/README.md)

## 6. Hard Stops

- `direct_binance_call_outside_lib` — Binance API call from v7/ or alphaforge/
- `lib_import_boundary_violation` — lib/ imports v7 or alphaforge
- `shared_everything_mistake` — putting regime, risk, IO, or adapters in lib/
