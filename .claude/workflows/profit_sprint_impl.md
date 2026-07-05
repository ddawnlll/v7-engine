# Profitability Sprint Implementation Workflow

## Objective
Build the smallest working AlphaForge profitability sprint system: file-based run registry, deterministic factor runner, leaderboard, eval gate, and top candidate report. No MLflow, no DVC, no Hydra, no dashboards.

## Agent Tasks

### Agent 1: architect-reviewer — Map integration points
- Map all existing files that the profit sprint will touch
- Identify cost model interface, evaluation interface, data gateway interface
- Define acceptance criteria for each sprint component
- Output: integration map with file paths and function signatures

### Agent 2: implementation — Sprint 0 (Cost Sanity)
- Verify net/gross R calculation correctness
- Verify short/long polarity
- Verify cost application (fee + slippage + funding)
- Create `alphaforge/src/alphaforge/sprint/cost_sanity.py` if needed
- Output: cost sanity check that can be run as smoke test

### Agent 3: implementation — Sprint 1 (Factor Sprint Runner)
- Create `alphaforge/src/alphaforge/sprint/runner.py` — deterministic factor sprint runner
- Create `alphaforge/src/alphaforge/sprint/config.py` — factor definitions and parameters
- 20-50 deterministic factors: momentum, reversal, volume zscore, range expansion, volatility compression, relative strength, liquidity-adjusted, funding-aware, regime filter
- Output: runner that produces metrics.json per factor

### Agent 4: implementation — Sprint 1 (Leaderboard)
- Create `alphaforge/src/alphaforge/sprint/leaderboard.py` — CSV-based leaderboard
- Columns: factor, mode, timeframe, lookback, hold_bars, trade_count, gross_return, net_return, expectancy_r, profit_factor, max_drawdown, win_rate, turnover, cost_drag, positive_folds, decision
- Output: leaderboard.csv generation

### Agent 5: implementation — Sprint 2 (Eval Gate)
- Create `alphaforge/src/alphaforge/sprint/eval_gate.py` — minimal walk-forward eval gate
- Gates: min_trades >= 200, positive_folds >= 4/6, net_expectancy_r > 0, profit_factor > 1.10, max_drawdown acceptable, cost_drag doesn't kill alpha, beats random/no-trade baseline
- Output: gate pass/fail with reasons

### Agent 6: implementation — Sprint 3 (Top Candidate Report)
- Create `alphaforge/src/alphaforge/sprint/candidate_report.py`
- For top 3: when it works, when it dies, net cost survival, mode recommendation, V7 handoff readiness
- Output: markdown report per top candidate

### Agent 7: test-automator — Tests for all sprint modules
- Unit tests for cost sanity, runner, leaderboard, eval gate, candidate report
- Integration test that runs a mini sprint end-to-end
- Output: test files in alphaforge/tests/test_sprint_*.py

### Agent 8: code-reviewer — Final review
- Review all sprint code for correctness
- Verify no dead code, no unwired features
- Check cost model integration is real (not placeholder)
- Output: review findings

## Acceptance Criteria
1. `python -m pytest alphaforge/tests/test_sprint_*.py` passes
2. Running the sprint produces leaderboard.csv with real metrics
3. Eval gate correctly filters candidates
4. Top candidate report is generated for top 3
5. Net/gross R are correctly computed and visible
6. No MLflow, no DVC, no external dependencies beyond existing stack
