"""
lib — Shared Primitives & Services

A minimal shared library for primitives that are **nearly identical usage**
between v7/ (semantic authority) and alphaforge/ (training/research authority).

Scope:
  - lib/market_data/   — Binance client, klines/funding, standard schema
  - lib/indicators/    — ATR, returns, volatility, rolling window (pure math)
  - lib/costs/         — Fee %, slippage estimation (basic formulas)
  - lib/time/          — Interval conversion, fold generation (temporal utilities)

NOT in lib/:
  - Regime enums/detectors (different semantics per system)
  - R-multiple (V7=ATR truth, research=fixed%)
  - IO, serialization, cache abstractions (each system differs)
  - Adapters (owned by v7/ and alphaforge/)
"""

__version__ = "0.1.0"
