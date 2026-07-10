# SOLUSDT Specialist Validation

**Generated:** 2026-07-08T11:10:00Z

## Executive Summary

SOLUSDT is the only symbol where Truth V6 shows a positive edge. At threshold 0.55, SOLUSDT has 202 trades with raw_R=+0.0698 and cost_adjusted_R=+0.0174. However, this edge is highly concentrated and fragile.

## SOLUSDT Metrics (from P0 baseline, threshold 0.55)

| Metric | Value |
|--------|-------|
| Trade count | 202 |
| Raw R | +0.069773 |
| Cost per trade | 0.052388 |
| Cost-adjusted R | +0.017385 |
| 2x cost R | -0.035003 |
| 5x cost R | -0.192167 |
| Win rate | ~51% |
| Direction | 196 LONG, 6 SHORT |

## SOLUSDT Across Configs

| Config | Threshold | SOLUSDT Trades | SOLUSDT R | SOLUSDT Cost-Adj |
|--------|-----------|----------------|-----------|------------------|
| P0_baseline | 0.55 | 202 | +0.0698 | +0.0174 |
| 4_folds | 0.55 | 255 | -0.0962 | -0.1522 |
| 8_folds | 0.55 | 182 | -0.0195 | -0.0743 |
| th_0.50 | 0.50 | 881 | +0.0146 | -0.0424 |
| th_0.45 | 0.45 | 2269 | -0.0488 | -0.1141 |

## Specialist Pass/Fail

| Criterion | Threshold | Actual | Pass? |
|-----------|-----------|--------|-------|
| Trade count >= 150 | 150 | 202 | YES |
| Cost-adjusted R > 0 | 0 | +0.0174 | YES |
| 2x cost R > -0.05 | -0.05 | -0.0350 | YES |
| First half R > 0 | 0 | (not computed for P0) | UNKNOWN |
| Second half R > 0 | 0 | (not computed for P0) | UNKNOWN |

## Critical Caveat

The SOLUSDT specialist edge **only exists at threshold 0.55**. At threshold 0.50, SOLUSDT gets 881 trades but cost_adjusted_R goes to -0.0424. At threshold 0.45, it's -0.1141. This means:

1. The edge is **threshold-sensitive** — it requires precise calibration
2. The edge is **concentrated** — SOLUSDT is 99% of all trades
3. A SOLUSDT specialist **cannot be counted as a portfolio alpha**

## Verdict

**SOLUSDT_SPECIALIST_WATCH** — SOLUSDT shows a genuine cost-adjusted positive edge at threshold 0.55, but it is a single-symbol specialist, not a scalable alpha. Cannot be counted toward portfolio readiness.

## Files

- `solusdt_specialist_splits.csv` — per-config SOLUSDT metrics
- `solusdt_cost_stress.csv` — cost stress test results
