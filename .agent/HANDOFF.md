# Agent Handoff — Kelly Sizing Experiment (2026-07-14)

## Current state

The requested real-data Kelly sizing experiment is complete and persisted at
`/root/v7-engine-main/data/reports/kelly_sizing_results.json`.

**Research verdict: PASS_WITH_HOLDS.** The experiment itself completed and its
artifact validated, but **no threshold reached the requested 80% economic win
rate**. The maximum was 64.19% at threshold 0.70, so no leverage tier or
confidence threshold is authorized or locked.

## Work completed

- Added `alphaforge/src/alphaforge/kelly_sizing_experiment.py`.
  - Validates long-panel row identity across open/high/low/close/volume.
  - Loads all 56 real symbols from `/root/v7-engine/cache/v7_lite_expanded_panel_v1/`.
  - Builds 2,094,784 aligned rows with 91 `build_aligned_training_frame`
    features.
  - Uses six timestamp-grouped expanding folds, 1,406-group purge and
    703-group embargo; all rows sharing a candle timestamp stay on one side of
    a boundary.
  - Fits fixed three-class XGBoost models on CUDA and sweeps thresholds
    0.30–0.90 in 0.05 increments.
  - Computes economic win rate / avg win / avg loss, raw Kelly, half-Kelly
    (max 5x), quarter-Kelly (max 3x), and adjusted return.
- Wrote the required JSON artifact, ACCP-YAML completion report, audit finding,
  open question, and roadmap entry.

## Confirmed result

- Best win rate: **64.1856%** at threshold **0.70**, 1,142 candidate trades,
  12.15 candidates/day.
- Best unconstrained sizing illustration: **0.70**, half-Kelly **1.591433x**,
  base net return **0.034301**, adjusted return **0.054587**.
- `selection.best_80pct_winrate_by_adjusted_R` is `null` — no threshold meets
  the 80% rule.
- `base_net_R` is AlphaForge `action_net_r`: a fractional net forward-return
  proxy, **not** true risk-normalized R or leverage-aware exchange P&L.

## Files inspected

- `/root/v7-engine-main/AGENTS.md`
- `/root/v7-engine-main/.agent/{CONTEXT_INDEX.md,project_context.md,CURRENT_TASK.md,EVIDENCE_REQUIREMENTS.md,HANDOFF.md}`
- `/root/v7-engine-main/docs/{decisions/DECISIONS.md,audits/FINDINGS_LEDGER.md,audits/OPEN_QUESTIONS.md}`
- `/root/v7-engine-main/ai_summary.md`
- `/root/v7-engine-main/alphaforge/docs/ai_summary.md`
- `/root/v7-engine-main/alphaforge/src/alphaforge/{train.py,meta/meta_labeler.py,training/xgb_trainer.py}`
- `/root/v7-engine-main/alphaforge/tests/{test_training_entrypoint.py,test_wfv_purge_embargo.py}`
- `/root/v7-engine/cache/v7_lite_expanded_panel_v1/manifest.json`
- `/tmp/leverage_sizing_test.py` (unverified prototype; replaced by the audited module)

## Files modified

- `/root/v7-engine-main/alphaforge/src/alphaforge/kelly_sizing_experiment.py`
- `/root/v7-engine-main/data/reports/kelly_sizing_results.json`
- `/root/v7-engine-main/docs/audits/FINDINGS_LEDGER.md`
- `/root/v7-engine-main/docs/audits/OPEN_QUESTIONS.md`
- `/root/v7-engine-main/v7/docs/roadmap.md`
- `/root/v7-engine-main/reports/accp/kelly_sizing_experiment_2026-07-14.accp.yaml`
- `/root/v7-engine-main/.agent/HANDOFF.md`

## Commands and verification

- `PYTHONPATH=alphaforge/src:. python3 -m py_compile alphaforge/src/alphaforge/kelly_sizing_experiment.py` — PASS.
- Preflight assertions for six split boundaries, Kelly formula/caps, and CUDA
  `predict_proba` shape — PASS.
- `PYTHONPATH=alphaforge/src:. python3 -m alphaforge.kelly_sizing_experiment` — PASS; real panel artifact written.
- JSON assertion harness — PASS: 91 features, six folds, 13 thresholds,
  temporal gaps, finite values, and `adjusted_R == base_net_R * leverage`.
- `PYTHONPATH=alphaforge/src:. python3 -m pytest alphaforge/tests/test_training_entrypoint.py alphaforge/tests/test_wfv_purge_embargo.py -q` — 4 passed, 2 unrelated existing failures:
  1. `simulation/tests/test_leverage_training.py` imports XGBoost outside the
     entrypoint test's blessed paths.
  2. A SWING WFV expectation still assumes `max_hold` instead of the current
     `label_horizon` purge policy.

## Unresolved blockers

- No evaluated threshold reaches the 80% win-rate target.
- The threshold sweep is retrospective and needs a preregistered untouched
  holdout before it can guide even research selection.
- Leverage-dependent liquidation, rounding, and Binance-margin economic parity
  are not modeled by the `action_net_r` proxy; no execution action is allowed.
- An unrelated `alphaforge/src/alphaforge/features/scalp_momentum.py` edit has
  a 2026-07-13T22:30:27Z mtime, after this artifact's 22:29:43Z write time.
  It is not part of this task and must be preserved; it did not affect the
  completed run.

## Exact recommended next action

Do **not** select a leverage tier. Freeze a new causal feature/model hypothesis,
then run it once on a later untouched chronological holdout with the same
timestamp-grouped folds. Require at least 80% economic win rate and one
candidate/day before commissioning a new margin-aware Kelly study.
