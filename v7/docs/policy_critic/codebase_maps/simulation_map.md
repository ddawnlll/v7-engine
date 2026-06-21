# Codebase Map: Simulation (economic truth authority)

## Subsystem Identity
The /simulation engine is a pure function `simulate(SimulationInput) -> SimulationOutput` (simulation/engine/engine.py). End-to-end flow for one candidate decision point:

1. Input carries: symbol, decision_timestamp, mode (SWING/SCALP/AGGRESSIVE_SCALP), primary_interval, entry_price, atr, future_path.candles[], and a SimulationProfile (stop_multiplier, target_multiplier, max_holding_bars, penalty weights, ambiguity_margin_r, min_action_edge_r, no_trade_default).
2. entry_risk (1R) = atr * profile.stop_multiplier. notional = entry_price (1 unit base).
3. Stop/target levels: long_stop = entry - atr*stop_mult; long_target = entry + atr*target_mult (mirror for short).
4. For BOTH LONG_NOW and SHORT_NOW: simulate_path() walks future candles up to max_holding_bars. Conservative same-candle rule: stop checked before target (adverse move assumed to execute first); same_candle_ambiguity flagged. Returns ExitResult with exit_reason (STOP_HIT/TARGET_HIT/TIME_EXIT), exit_price, realized_r_gross, mfe/mae (+ R-normalized mfe_r/mae_r), time_to_mfe/time_to_mae.
5. Cost model (simulation/engine/costs.py total_cost_r): fee_cost_r = (entry_fee+exit_fee)/1R using taker_fee_bps=4.0 conservative; slippage_cost_r = volatility-adjusted (slippage_bps=1.0, scaled by atr/entry_price) on both sides / 1R. total_cost_r = fee_cost_r + slippage_cost_r. Funding cost is DEFERRED (not implemented; blocked at G3 for perps).
6. realized_r_net = realized_r_gross - total_cost_r (per ActionOutcome). NO funding term yet.
7. action_utility = realized_r_net - mae_penalty_weight*abs(mae_r) - cost_penalty_weight*total_cost_r - time_penalty_weight*time_to_mfe*0.1 (mode-weighted).
8. NoTradeOutcome derived from directional outcomes: saved_loss_r = max(0,-min(long_r_net,short_r_net)); missed_opportunity_r = best_r if best_r > min_action_edge_r else 0; quality classified CORRECT_NO_TRADE/SAVED_LOSS/MISSED_OPPORTUNITY/AMBIGUOUS_NO_TRADE.
9. _select_best_action ranks {LONG_NOW, SHORT_NOW, NO_TRADE} by utility (NO_TRADE utility = saved_loss_r - 0.5*missed_opportunity_r). action_gap_r = best-second; is_ambiguous = action_gap < ambiguity_margin_r; if ambiguous, no_trade_default flips to NO_TRADE (or AMBIGUOUS_STATE for SWING).
10. Output: SimulationOutput with long_outcome, short_outcome, no_trade_outcome, best_action, second_best_action, action_gap_r, regret_r (currently always 0.0), is_ambiguous, resolution_status, lineage (versions + adapter_kind).

Selection is comparative and cost-aware: no action is chosen by policy inside simulation; simulation produces raw economic evidence and a utility-ranked best_action that V7 policy may override (regime constraints are policy-layer, recorded separately, never hidden inside simulation).

## Key Files
- **/home/erfolg/src/v7-engine/simulation/engine/engine.py** — Core comparative simulation engine: simulate(SimulationInput)->SimulationOutput; builds ActionOutcome/NoTradeOutcome, action_utility, best_action selection
- **/home/erfolg/src/v7-engine/simulation/engine/costs.py** — Authoritative cost model: compute_entry_risk, fee_cost_r, slippage_cost_r, total_cost_r (taker 4bps, slippage 1bps vol-adjusted, both sides). Funding DEFERRED
- **/home/erfolg/src/v7-engine/simulation/engine/exits.py** — Exit resolver: simulate_path (stop-before-target conservative, TIME_EXIT fallback), ExitResult, compute_utility (mode-weighted)
- **/home/erfolg/src/v7-engine/simulation/contracts/models.py** — All contract types: SimulationInput, SimulationOutput, ActionOutcome, NoTradeOutcome, PathMetrics, SimulationProfile, SimulationLineage, enums (TradingMode, Action, ExitReason, NoTradeQuality)
- **/home/erfolg/src/v7-engine/lib/costs/r_costs.py** — Primitive R-normalized cost helpers (fee_cost_r/slippage_cost_r/total_cost_r) used by simulation cost wrapper
- **/home/erfolg/src/v7-engine/simulation/docs/ai_summary.md** — Canonical simulation subsystem synthesis (read first)
- **/home/erfolg/src/v7-engine/simulation/docs/cost_model.md** — Cost model authority: fee/slippage formulas, funding DEFERRED_FOR_SPOT_OR_NON_PERP_FIRST_PHASE, versioning
- **/home/erfolg/src/v7-engine/simulation/docs/profiles.md** — SWING/SCALP/AGGRESSIVE_SCALP profile parameters and action utility function
- **/home/erfolg/src/v7-engine/simulation/docs/exits_and_horizons.md** — Stop/target/time-exit/horizon-end/unresolved/invalidated precedence rules
- **/home/erfolg/src/v7-engine/simulation/docs/no_trade_quality.md** — NO_TRADE first-class quality classification and saved-loss/missed-opportunity semantics
- **/home/erfolg/src/v7-engine/simulation/docs/replay_paper_and_runtime_hosting.md** — Adapter model: TRAINING/EVALUATION/REPLAY/PAPER/MONTE_CARLO; parity guarantee; regime visibility
- **/home/erfolg/src/v7-engine/runtime/services/historical_simulation_engine.py** — CRITICAL: runtime-owned historical backtest/replay harness. Does NOT use /simulation engine; uses analyzer + own _settle_position with separate fee_bps/slippage_bps. Produces trades{realized_r, pnl, fees, drawdown, equity_curve}. Parity divergence from /simulation
- **/home/erfolg/src/v7-engine/runtime/services/simulation_service.py** — Runtime service orchestrating HistoricalSimulationEngine runs, persisting results + decision traces

## Critic Integration Points
A PolicyCritic would plug in between the simulation's raw comparative economic evidence and V7's final policy action. Concrete insertion points:

1. After simulate() produces SimulationOutput (long_outcome, short_outcome, no_trade_outcome with realized_r_net + action_utility + action_gap_r) and BEFORE V7 policy/risk applies regime gates and final TradeOutcome materialization. The critic consumes the three ActionOutcomes + PathMetrics + NoTradeOutcome as the reward/realization signal and can re-rank or veto best_action. This mirrors the existing regime-constraint pattern (ADVISORY/SOFT_BLOCK/HARD_BLOCK recorded as policy-layer override, simulation evidence preserved) — a critic override must likewise be recorded separately and must NOT mutate simulation outputs.

2. For offline critic TRAINING, the reward/realization must come from the REPLAY adapter (adapter_kind=REPLAY) or TRAINING adapter over historical windows, both of which call the same /simulation engine. The critic learns Q(s,a) where s = canonical market state (from alphaforge/v6 snapshot, NOT simulation-owned) and a in {LONG_NOW, SHORT_NOW, NO_TRADE}; the realization (net_R_after_cost, drawdown proxy via mae_r, saved_loss_r/missed_opportunity_r) is exactly what SimulationOutput.ActionOutcome/NoTradeOutcome/PathMetrics provide.

3. The historical_simulation_engine in runtime already iterates historical decision points and settles trades, but it does NOT emit (state, action, net_R, drawdown) tuples and does NOT route through /simulation. To train a critic without violating domain boundaries, either (a) wrap HistoricalSimulationEngine's iteration with a /simulation simulate() call per decision point to get authoritative SimulationOutput, or (b) build a new replay-tuple emitter in alphaforge (side-effect-free TRAINING adapter) that pairs canonical state with SimulationOutput. The critic itself belongs to the v7 policy layer (or a dedicated offline training harness), NEVER inside /simulation.

CRITICAL FINDING: No replay buffer / offline-RL tuple store / experience dataset exists anywhere in the repo. grep for replay_buffer, offline_rl, experience_buffer, rl_buffer across *.py returns zero hits. The infrastructure to emit (state, action, net_R_after_cost, drawdown) tuples for offline RL does not yet exist and must be built.

## Available Reward Signals for Offline RL Training
EXACT real field names produced by /simulation (simulation/contracts/models.py):

Per ActionOutcome (LONG_NOW / SHORT_NOW):
- realized_r_gross (float) — pre-cost R-multiple
- realized_r_net (float) — NET R AFTER COST = realized_r_gross - total_cost_r (the primary offline-RL reward)
- fee_cost_r (float) — fee cost in R
- slippage_cost_r (float) — slippage cost in R
- total_cost_r (float) — fee_cost_r + slippage_cost_r
- action_utility (float) — mode-weighted composite (realized_r_net - mae_w*abs(mae_r) - cost_w*total_cost_r - time_w*time_to_mfe*0.1)
- exit_reason (STOP_HIT/TARGET_HIT/TIME_EXIT)
- exit_price, exit_bar_index, hold_duration_bars

Per PathMetrics (per directional path):
- mfe, mae (price terms), mfe_r, mae_r (R-multiples — mae_r is the closest simulation-native per-trade drawdown proxy)
- time_to_mfe, time_to_mae
- path_quality_score (0-1), path_quality_bucket (HIGH/MEDIUM/LOW)

Per NoTradeOutcome (NO_TRADE):
- saved_loss_r (float) — avoided loss in R (a saved_loss reward signal)
- saved_loss_score (0-1)
- missed_opportunity_r (float) — foregone best-directional R (a missed_opportunity signal)
- missed_opportunity_score (0-1)
- no_trade_quality (CORRECT_NO_TRADE/SAVED_LOSS/MISSED_OPPORTUNITY/AMBIGUOUS_NO_TRADE)
- was_correct_skip (bool)

Per SimulationOutput (comparative/selection):
- best_action, second_best_action, action_gap_r, regret_r (currently hardcoded 0.0 — not yet a real regret signal), is_ambiguous, resolution_status

AGGREGATE / NOT per-tuple: drawdown is NOT produced by the /simulation engine. Only runtime/services/historical_simulation_engine.py produces max_drawdown_pct and a normalized equity_curve at run level (aggregate, not per-decision). There is NO per-decision drawdown field in SimulationOutput; mae_r is the per-path adverse-excursion proxy. funding_cost_r is defined in docs (LOCK_CANDIDATE formula) but NOT implemented in code (DEFERRED). missed_opportunity and saved_loss ARE real produced fields.

## Domain Boundary Constraints
Per CLAUDE.md domain rules (truth hierarchy: simulation > realized > contract > runtime > model):

1. The critic MUST NOT bypass simulation costs. Any reward used for critic training must be realized_r_net from /simulation (gross minus fee_cost_r + slippage_cost_r), never a gross-only or model-imagined R. No component may compute its own cost-adjusted R outside /simulation.
2. The critic MUST NOT invent economic truth. It consumes SimulationOutput; it does not produce alternative realized outcomes. /simulation is the single economic truth authority.
3. The critic is a POLICY-LAYER construct (like regime constraints), NOT a simulation semantic. It may re-rank/veto best_action but must preserve simulation evidence visibility — both the simulation output (market truth) and the critic override must be recorded separately (mirroring the regime ADVISORY/SOFT_BLOCK/HARD_BLOCK + reason_code pattern). It must never be a hidden mechanism for suppressing simulation evidence.
4. Model confidence must NOT override risk gates (CLAUDE.md forbidden action). A critic scoring high Q(s,a) cannot bypass V7 risk gates or simulation cost truth.
5. simulation/ MUST NOT import v7/ or alphaforge/ (hard-stop import boundary). The critic therefore cannot live inside simulation/; it lives in v7 policy layer or an offline training harness that consumes simulation via side-effect-free adapters.
6. UNRESOLVED and INVALIDATED outcomes must NOT be used as training labels (forbidden pattern, tested). Critic training data must filter on resolution_status == COMPLETE.
7. Monte Carlo outputs must never be used as realized truth (separate monte_carlo_run_id lineage) — the critic must train on realized SimulationOutput, not MC distributions.
8. The existing runtime historical_simulation_engine.py applies its OWN fee_bps/slippage_bps settlement and does NOT route through /simulation — this is a parity divergence. The critic must NOT be trained on that engine's realized_r/pnl as authoritative economic truth; either route through /simulation or explicitly mark it as non-authoritative replay signal.

## Fields Produced/Consumed
- `best_action`
- `second_best_action`
- `action_gap_r`
- `regret_r`
- `is_ambiguous`
- `action_utility`
- `realized_r_net`
- `realized_r_gross`
- `fee_cost_r`
- `slippage_cost_r`
- `total_cost_r`
- `exit_reason`
- `hold_duration_bars`
- `mfe_r`
- `mae_r`
- `time_to_mfe`
- `time_to_mae`
- `path_quality_score`
- `path_quality_bucket`
- `saved_loss_r`
- `saved_loss_score`
- `missed_opportunity_r`
- `missed_opportunity_score`
- `no_trade_quality`
- `was_correct_skip`
- `resolution_status`
- `mode`
- `primary_interval`
- `no_trade_default`
- `ambiguity_margin_r`
- `min_action_edge_r`

## Notes
CRITICAL FINDING 1 — No replay buffer / offline-RL tuple store exists. grep across all *.py for replay_buffer|offline_rl|experience_buffer|rl_buffer|policy_critic returns zero source hits (critic mentions are docs-only, e.g. v7/docs/profitability_thesis.md, alphaforge phase plans). The (state, action, net_R_after_cost, drawdown) tuple emitter for offline RL is NOT implemented and must be built. /simulation produces the realization half (action, realized_r_net, mae_r, saved_loss_r, missed_opportunity_r); the state half must come from the canonical snapshot (alphaforge/v6 UnifiedSnapshotBuilder) since /simulation does not own state. A tuple assembler would pair snapshot-at-decision-time + SimulationOutput per historical decision point.

CRITICAL FINDING 2 — Two parallel simulation paths exist and they diverge. (a) /simulation engine (engine.py) is the authoritative economic truth, pure function, used by TRAINING/EVALUATION/REPLAY/PAPER adapters per docs. (b) runtime/services/historical_simulation_engine.py is a separate runtime-owned backtest harness that calls the analyzer engine and settles trades with its own _settle_position using fee_bps/slippage_bps params and its own stop/target logic — it does NOT call simulation.engine.simulate() and does NOT produce ActionOutcome/NoTradeOutcome/PathMetrics. Its outputs (realized_r, pnl, fees, max_drawdown_pct, equity_curve) are NOT /simulation-authoritative. This is a parity gap vs the docs one-engine/no-backtest-only-simulator rule. For offline RL, route through /simulation to get authoritative net_R_after_cost.

CRITICAL FINDING 3 — regret_r is hardcoded to 0.0 in _select_best_action (engine.py line 168); it is not yet a real regret signal. A critic providing regret-style rewards would need this wired.

CRITICAL FINDING 4 — Drawdown is only available as an aggregate run-level metric (max_drawdown_pct in HistoricalSimulationEngine._finalize) or as the per-path adverse-excursion proxy mae_r. There is no per-decision portfolio drawdown field in SimulationOutput. For offline RL drawdown shaping, mae_r is the simulation-native signal; true portfolio drawdown requires a portfolio-equity replay layer (runtime-owned) on top of per-trade realized_r_net.

CRITICAL FINDING 5 — Funding cost (funding_cost_r) is DEFERRED_FOR_SPOT_OR_NON_PERP_FIRST_PHASE. The formula is a LOCK_CANDIDATE in cost_model.md but not implemented in costs.py. realized_r_net currently = gross - fee - slippage only. Perp promotion is blocked at G3 until funding is implemented. A critic trained today on spot-only data must not be assumed valid for perps.

CONFIDENCE FIELD NOTE: confidence is NOT a simulation-produced field. In the runtime historical engine, confidence comes from the analyzer signal (signal.confidence / confidence_raw / confidence_final) and is carried on SimPosition and the settled trade dict, but /simulation itself does not produce or consume confidence — that is a model/analyzer-layer quantity. The critic must treat confidence as an input feature (from alphaforge/v6 snapshot), not as a simulation reward.

Reward recommendation for offline RL: use realized_r_net as primary scalar reward; use action_utility as the mode-aware shaped reward; use mae_r as drawdown penalty signal; use saved_loss_r/missed_opportunity_r for NO_TRADE action value; filter resolution_status==COMPLETE and exclude UNRESOLVED/INVALIDATED.