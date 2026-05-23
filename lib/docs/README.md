# lib/ — Shared Primitives & Services

## Purpose

A minimal shared library for primitives that are **nearly identical usage** between `v7/` and `alphaforge/`. Nothing goes here unless it's genuinely reusable as-is.

## Contents

| Subdirectory | What | Why Shared |
|---|---|---|
| `lib/market_data/` | Binance API client + klines/funding fetching + standard schema | Both systems need the same raw candle data |
| `lib/indicators/` | ATR, returns, volatility, rolling window math | Pure math — same everywhere |
| `lib/costs/` | Fee percentage, slippage estimation | Basic formulas are identical |
| `lib/time/` | Interval conversion, walk-forward fold generation | Temporal logic is identical |

## What Does NOT Go Here

| Thing | Reason |
|---|---|
| Regime detection / enums | V7 uses for policy authority; alphaforge uses for feature evidence. Different semantics. |
| R-multiple computation | V7 has ATR-based mode-specific truth; research uses fixed-percent helpers. Different. |
| I/O utilities | Each system has different output patterns. |
| Generic serialization | Premature abstraction — add when a concrete need emerges. |
| Cache abstractions | Each system handles caching differently. |
| Adapters | Adapters are owned by v7/ and alphaforge/ respectively. |

## Import Rules

- `lib/` must NOT import `v7.*` or `alphaforge.*`
- `v7/` and `alphaforge/` may import `lib/` directly for these primitives (no adapter needed for math/utils)
- For market data, use the service layer — don't call Binance HTTP directly from v7 or alphaforge
