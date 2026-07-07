# OPERATION SCALP 0.05 — Scoreboard (Phase A)

Generated: 2026-07-07T22:57:19Z
Symbols: 56

## Baseline Results

| Run | N Trades | Avg R | Total R | WR | PF | Max DD | WF Acc | Overfit | Status |
|-----|----------|-------|---------|----|----|--------|---------|---------|--------|
| SCALP_baseline_12 | 4076     | -0.0926 | -377.4196 | 0.4465 | 0.8155 | -391.6244 | 0.1576 |  0.3735 | REJECT |
| SWING_control_12 | 1396     | -0.1688 | -235.6221 | 0.3968 | 0.7138 | -357.0512 | 0.1803 |  0.3555 | REJECT |

## Cost Decomposition (from metrics)

### SCALP_baseline_12
- avg_net_R = -0.0926
- Fee impact = 190.9182
- Slippage impact = 48.2730
- Funding impact = 0.0000
- Avg cost per trade = 0.0587
- Total cost drag = 239.1912
- Cost drag % of gross = 173.0400%
### SWING_control_12
- avg_net_R = -0.1688
- Fee impact = 74.5460
- Slippage impact = 18.7761
- Funding impact = 0.0000
- Avg cost per trade = 0.0669
- Total cost drag = 93.3221
- Cost drag % of gross = 65.5800%

## Symbol Concentration

### SCALP_baseline_12
  - DOGEUSDT: 873 trades, R=-10.9630, share=21.4%
  - AVAXUSDT: 806 trades, R=-199.6998, share=19.8%
  - SOLUSDT: 659 trades, R=-61.9289, share=16.2%
  - BCHUSDT: 579 trades, R=-37.9204, share=14.2%
  - LINKUSDT: 245 trades, R=15.3748, share=6.0%
  Top-2 share: 41.2%
  **⚠️  Concentration > 40% — risk**
### SWING_control_12
  - AVAXUSDT: 1058 trades, R=-224.7551, share=75.8%
  - SOLUSDT: 151 trades, R=-7.5328, share=10.8%
  - DOGEUSDT: 79 trades, R=-6.2412, share=5.7%
  - BTCUSDT: 39 trades, R=-10.4690, share=2.8%
  - BCHUSDT: 17 trades, R=0.3887, share=1.2%
  Top-2 share: 86.6%
  **⚠️  Concentration > 40% — risk**

---
_Phase A complete at 2026-07-07T22:57:19Z_