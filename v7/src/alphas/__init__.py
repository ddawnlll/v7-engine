"""Alpha Thesis Validation — systematic backtesting of three trading hypotheses.

Hypotheses:
  1. Altcoin Delay     — BTC moves → altcoins follow with 1-4h lag
  2. Volatility Compression — compressed ATR → breakout momentum
  3. Funding Divergence — high funding + flat spot → mean reversion

Usage:
    python -m alphas.main                        # full run
    python -m alphas.main --check-data-only       # verify data only
    python -m alphas.main --hypo 1                # Altcoin Delay only
    python -m alphas.main --hypo 2                # Volatility Compression only
    python -m alphas.main --hypo 3                # Funding Divergence only
"""
