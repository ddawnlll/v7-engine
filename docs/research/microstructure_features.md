# Microstructure Features — Research Archive

## Source Papers
- arXiv 2602.00776 — Feature ranking across 5 crypto assets
- Cont, Kukanov & Stoikov (2014) — Order Flow Imbalance
- Stoikov (2018) "The Micro-Price" SSRN 2970694

## Implemented Features (AlphaForge v0.1)
| Feature | File | SHAP Rank |
|---------|------|-----------|
| OBI (L1) | orderbook.py | #1 |
| OBI_N (multi-level) | orderbook.py | #1 (depth-extended) |
| OFI | orderbook.py | Top 10 |
| VAMP | orderbook.py | Top 15 |
| Spread (bps) | orderbook.py | #2-3 |
| VWAP-to-mid deviation | orderbook.py | #3-4 |
| Micro-price | orderbook.py | #5 |
| Volume HHI | orderbook.py | Top 10 |

## Key Findings
- 86% of depth is outside L1 (arXiv 2604.24366)
- Micro-price gap is leading indicator for mean reversion
- OFI has linear relationship with price changes per Cont et al.
