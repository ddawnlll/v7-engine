# Phases 1b-2 Results

## Baseline (th=0.70, 30 symbols)
- Trades: 745, Winrate: 96.5%, NetR: +0.0864

## Phase 1b — Regime Filter (block HIGH vol)
- Trades: 167 (78% reduction!)
- Winrate: 96.4% (no improvement)
- NetR: +0.0665 (WORSE)
- **Verdict: NOT HELPFUL** — removes good trades without improving winrate

## Phase 1c — Meta-Labeling (best meta_thr=0.80)
- Trades: 457, Winrate: **98.9%** (+2.4%)
- NetR: +0.0837 (slightly lower)
- **Verdict: IMPROVES WINRATE** — from 96.5% to 98.9%

## Phase 1d — Combined (Regime + Meta)
- Trades: 136 (too few), Winrate: 97.1%
- NetR: +0.0652 (WORSE)
- **Verdict: NOT HELPFUL** — combination is worse than meta alone

## Phase 2 — Fractional Kelly Sizing
- Full Kelly: 95.26% (too aggressive)
- Quarter Kelly: 23.81%
- Hard risk cap: 2.00%
- **Recommended position size: 2.00% per trade** (cap binds before Kelly)
