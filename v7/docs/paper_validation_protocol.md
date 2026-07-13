# Alpha #1 Paper Validation Protocol

> **Locked decision (#278).** Do not change without explicit contradiction evidence.
> Protocol version: 1.0.0 | Status: LOCKED

## Purpose

Before paper trading accumulates a meaningful sample, the acceptance criteria for
"paper validation succeeded" must be written down and locked. This prevents
post-hoc rationalization once real paper numbers come in.

## Kill-Switch Conditions

Paper trading SHALL be killed (all positions closed, no new signals) when ANY of:

| # | Condition | Threshold | Rationale |
|---|-----------|-----------|-----------|
| 1 | Net expectancy R (30-trade trailing) | < -0.10 | Strategy destroys capital faster than costs |
| 2 | Consecutive losing trades | >= 5 | Regime change or signal broken |
| 3 | Max drawdown (peak-to-trough R) | > -5.0 R | Risk limit exceeded |
| 4 | Win rate (30-trade trailing) | < 25% | Signal quality collapsed |
| 5 | Profit factor (30-trade trailing) | < 0.5 | Costs exceed gross edge |

## Go / No-Go Criteria for Live

Paper validation passes (→ shadow mode eligible) when ALL of:

| # | Condition | Threshold |
|---|-----------|-----------|
| 1 | Minimum trades | >= 60 |
| 2 | Net expectancy R (overall) | > 0.05 |
| 3 | Profit factor | > 1.2 |
| 4 | Win rate | > 35% |
| 5 | Sharpe (daily returns) | > 0.5 |
| 6 | Max drawdown | > -4.0 R (less bad than kill) |

## BB Position Drift Monitor

The `bb_position` mechanism SHALL be monitored for drift every 20 trades:

| Metric | Warning | Kill |
|--------|---------|------|
| Position duration vs expected (max_holding_bars) | > 2x expected | > 4x expected |
| Fill rate (filled / attempted) | < 70% | < 50% |
| Slippage vs expected (1 tick) | > 2x | > 5x |

## Execution Parity

Paper fills SHALL use the same simulation formula:
`1R = ATR × stop_multiplier` (authority: Phase 3 decision).

Paper costs SHALL use authority taker fee (8 bps round-trip).
