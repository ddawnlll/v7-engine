# V7-Lite Leverage-Native Master Todo

**Status:** `LOCKABLE_WITH_HOLDS`  
**Date:** 2026-07-13  
**Scope:** Binance USDⓈ-M perpetual execution, Simulation economic truth,
AlphaForge research, V7 policy, Runtime reconciliation, and V7-Lite promotion.

## Owner Intent

V7-Lite trades are Binance perpetual positions. Leverage is therefore a native
execution variable, not a post-hoc reporting multiplier. The system must learn
when to take no position (`0x`), what direction to take, and how much exchange
exposure is justified, while preserving a base-risk result that proves whether
an alpha exists without leverage.

**Locked principle:** leverage may amplify a positive, cost-honest edge; it
must never manufacture one. A negative 1x/base-risk result is an automatic
`0x / NO_TRADE` result for every higher leverage tier.

## Economic Definitions

The following metrics must always appear together in every research report:

| Metric | Meaning | Cannot be replaced by |
|---|---|---|
| `base_net_R` | Simulation-authority net R at base risk, including fee, slippage, funding and exit path | leveraged equity PnL |
| `equity_return_net` | Account-equity change after selected notional, leverage, margin and costs | `base_net_R` |
| `portfolio_log_growth` | Compounded growth over the replay sequence | sum of independent trade R |
| `liquidation_rate` | Fraction of positions closed/liquidated under the modeled margin path | stop-hit rate |
| `cost_survival` | Performance across explicit fee/slippage/funding/impact scenarios | a single baseline-cost run |

`R` is defined by initial price risk: `1R = abs(entry_price - stop_price)`
times position quantity. Changing leverage or margin must not change
`base_net_R`. If a report shows a higher R only because leverage increased, the
metric is invalid.

## Current Starting Point

| Surface | Exists today | Gap to close |
|---|---|---|
| Action contract | `NO_TRADE`, LONG/SHORT at 1x/2x/3x/5x | Extend versioned action space through 7x/10x and add notional/margin lineage |
| Simulation | Approximate isolated-margin liquidation price using one maintenance-margin value | Binance bracket, mark-price, margin-balance, liquidation-fee and account-path parity |
| AlphaForge | 3-class classifier and a research-only leverage action contract | True simulation-R labels, sizing/utility targets, calibration and nested evaluation |
| Cost model | Fee, slippage and funding components; basic cost stress | Explicit multi-dimensional stress scenarios with real account commission and execution inputs |
| V7-Lite | Candidate gate and interval portfolio replay | Leverage eligibility, portfolio margin budget and equity-path gates |
| Runtime | Manual USDⓈ-M order flow can set leverage | Automated safe path, bracket preflight, margin-type control, post-order reconciliation and no-bypass policy |

Important implementation facts:

- `SimulationProfile.leverage` is currently a single integer and uses an
  approximate tier-1 maintenance-margin ratio.
- Runtime already calls Binance `POST /fapi/v1/leverage` for a manual order.
  It must not be reused as the automatic policy surface without stronger
  preflight and reconciliation.
- Binance exposes the required native surfaces: `POST /fapi/v1/leverage`,
  `POST /fapi/v1/marginType`, `GET /fapi/v1/leverageBracket`,
  `GET /fapi/v3/positionRisk`, `GET /fapi/v1/commissionRate`, and
  `GET /fapi/v1/fundingRate`.
- Current AlphaForge fresh-run values labelled `net_r` are forward returns net
  of a fixed fee, not guaranteed risk-normalized simulation R. They cannot be
  used to decide leverage tiers until P0 below is complete.

## Scoreboard: One Honest Progress Number

Keep three public percentages, not one ambiguous number:

| Score | What it measures | Current planning baseline |
|---|---|---:|
| Infrastructure readiness | Code/evidence plumbing can execute the protocol | ~95% |
| XGBoost search exhaustion | How much of the justified XGBoost research space has actually been tested | ~30–35% |
| Economic deployment readiness | Cost-honest alpha + leverage + independent evidence + execution safety | ~25% |

The economic-deployment score is the primary V7-Lite number. Its initial
100-point rubric is deliberately stricter than implementation completion:

| Workstream | Points | Initial score | Evidence that adds points |
|---|---:|---:|---|
| P0 economic truth / R parity | 15 | 4 | Label, replay and simulator agree on the same true net R |
| P1 Binance execution parity | 15 | 5 | Bracket/margin/position reconciliation on testnet or shadow evidence |
| P2 cost survival | 15 | 4 | Candidate survives explicit independent cost scenarios |
| P3 AlphaForge leverage research | 20 | 5 | Nested-WFV specialist models with calibrated sizing outputs |
| P4 independent alpha portfolio | 20 | 2 | At least two non-overlapping, cost-positive families |
| P5 frozen OOS + replay | 10 | 0 | Preregistered, untouched evaluation with equity/margin replay |
| P6 shadow / paper evidence | 5 | 0 | Reconciled exchange observations and paper lifecycle |
| **Total** | **100** | **20–25** | Evidence only; code alone cannot raise economic points |

Hard caps:

- No simulation-R parity: maximum 25/100.
- No base-risk-positive, cost-honest candidate: maximum 40/100.
- Fewer than two independent alpha families: maximum 55/100.
- No preregistered frozen OOS: maximum 70/100.
- No shadow evidence: maximum 85/100.
- No paper reconciliation: maximum 95/100.

Scores may decrease when a candidate fails. A run report must state the score
before, score after, changed evidence, and whether the result is independent or
selection-contaminated.

## Run Report Contract

Every run must record:

```text
run_id, hypothesis_id, preregistration_hash, data_cutoff,
feature_family, model/objective, train/inner/outer folds,
base_net_R, equity_return_net, portfolio_log_growth,
trade_count, fold_signs, cost scenarios, break-even cost,
leverage distribution, margin utilization, liquidation rate,
max drawdown, symbol concentration, alpha correlation,
score_before, score_after, candidate_status, next_safe_action
```

The economic report must show base-risk and selected-leverage metrics side by
side. It must never aggregate leveraged PnL as though it were base R.

## Master Todo

### P0 — Repair the Economic Truth Boundary

- [ ] Replace AlphaForge's forward-return fields that are currently called
  `gross_r` / `net_r` with explicit `gross_forward_return` /
  `net_forward_return` where applicable.
- [ ] Build canonical labels from Simulation action outcomes:
  `base_net_R_long`, `base_net_R_short`, fees, slippage, funding, MAE/MFE,
  exit reason, stop distance and realization timestamp.
- [ ] Add a simulation-parity test suite that compares AlphaForge labels,
  outcome-cache rows, replay outcomes and Simulation output for identical
  entries.
- [ ] Version the label dataset and cost model whenever economics change; make
  old forward-return datasets non-promotable for perpetual decisions.
- [ ] Add an explicit `risk_amount_quote` / quantity field so R normalization
  is unambiguous under variable notional.

**Exit:** one known fixture reproduces the same net R through label creation,
simulation, cache readback and portfolio replay.

### P1 — Version the Leverage and Margin Contract

- [ ] Introduce action-space `v2` with `NO_TRADE`, LONG and SHORT at
  `1x/2x/3x/5x/7x/10x` (13 discrete actions).
- [ ] Keep a decomposed representation alongside the action ID:
  `direction`, `target_leverage`, `target_notional`, `risk_budget`,
  `margin_type`, `position_side`, and `exchange_symbol`.
- [ ] Define `0x` only as `NO_TRADE`; sub-1x economic exposure is represented
  by lower notional/risk budget, not an invalid Binance leverage setting.
- [ ] Add lineage fields: exchange bracket snapshot ID, commission snapshot ID,
  funding snapshot ID, mark-price source, and margin model version.
- [ ] Update contract registry/schema compatibility tests before any producer
  or consumer implementation.

**Exit:** contracts accept all 13 actions, reject invalid leverage/margin
combinations, and preserve backwards compatibility for v1 research artifacts.

### P2 — Build Binance-Native Simulation Economics

- [ ] Add a futures position model owned by `simulation/`, initially isolated
  margin only. Cross/portfolio margin is a later explicit mode, never an
  implicit fallback.
- [ ] Query/cache symbol-specific Binance notional/leverage brackets and
  maintenance-margin parameters; never use one global 0.4% MMR for production
  evidence.
- [ ] Model initial margin, maintenance margin, unrealized PnL, fees, funding,
  liquidation fee/penalty, mark-price versus last-price path, and liquidation
  precedence relative to stop/target.
- [ ] Add a leverage scenario evaluator for every valid action. It must return
  base R, equity return, margin used, liquidation distance, liquidation event,
  and full cost decomposition.
- [ ] Add quantity/tick/min-notional rounding to simulation inputs so modeled
  positions are exchange-eligible.
- [ ] Preserve conservative intrabar ordering when candle data cannot prove
  whether stop, target and liquidation occurred first.
- [ ] Benchmark vectorized outcome-tensor generation on the 20-symbol and
  56-symbol panels; partition/cache by symbol and leverage tier.

**Exit:** the simulator produces a reproducible outcome tensor for all
direction × leverage actions, and testnet/shadow records can be reconciled
without changing the model after the fact.

### P3 — Make Cost Survival Real

- [ ] Replace mutable-default/monkey-patched cost stress with immutable,
  explicit `CostScenario` inputs.
- [ ] Stress independently and jointly: account commission, maker fill
  probability/adverse selection, spread, slippage, market impact, funding,
  latency-to-fill, stop-gap loss, liquidation fee and partial-fill risk.
- [ ] Use account/symbol commission snapshots from Binance rather than a
  universal fee assumption when execution evidence is evaluated.
- [ ] Report 1x actual, 1.5x, 2x and 3x combined scenarios; use 5x as a
  diagnostic tail scenario. The exact promotion threshold remains empirical,
  not locked by this document.
- [ ] Produce break-even curves by leverage tier and execution mode
  (taker/maker/hybrid), including the contribution of each cost component.
- [ ] Block leverage optimization when base-risk cost survival is negative.
- [ ] Add cost-survival tests to the frozen holdout and V7 candidate gate
  packet; a placeholder slippage stress must fail closed.

**Exit:** a candidate can state exactly which costs it survives and which
scenario kills it; cost stress is no longer inferred from a fixed typical ATR.

### P4 — Train AlphaForge for Direction *and* Exposure

- [ ] Keep the first model output as direction/no-trade probability. Do not
  discard the interpretable 3-class baseline.
- [ ] Add a separate expected-outcome head or regressor for each direction:
  expected base net R, lower-tail R, MAE, liquidation probability and expected
  holding cost.
- [ ] Compare two leverage-learning forms on sealed outer folds:
  hierarchical direction + sizing versus one flat 13-class action classifier.
- [ ] Train the sizing policy only on simulation-authority outcomes, with a
  conservative utility such as log-growth minus drawdown, tail-loss,
  liquidation and turnover penalties. Numeric penalty weights stay `HOLD`
  until calibrated from replay/shadow data.
- [ ] Calibrate probabilities and uncertainty before sizing. High uncertainty,
  poor liquidity, adverse funding, high volatility or correlated exposure must
  only downgrade exposure; they may never upgrade it.
- [ ] Run specialist banks rather than one monolith: volume/liquidity,
  momentum/trend, breakout/volatility, mean-reversion, funding/OI and
  symbol/regime specialists.
- [ ] Use nested WFV: inner folds select feature set, threshold, objective and
  hyperparameters; outer folds are untouched. Track multiple-hypothesis count.
- [ ] Compare classifier, expected-R regression and ranking/top-k objectives
  for each specialist. Freeze only the winner before the next independent run.

**Exit:** AlphaForge emits a calibrated, evidence-backed recommendation of
`NO_TRADE` or `(direction, risk budget, leverage tier)` with base-R evidence.

### P5 — V7 Portfolio and Leverage Eligibility

- [ ] Add a V7-owned leverage eligibility gate. Inputs are AlphaForge evidence
  only; V7 owns final allowance, downgrade or veto.
- [ ] Enforce per-symbol exchange bracket, per-position risk budget, total
  margin utilization, total portfolio leverage, correlation-cluster exposure,
  daily drawdown and liquidation-risk ceilings.
- [ ] Make existing open positions consume margin/risk capacity in every entry
  batch, not merely count toward display limits.
- [ ] Select candidates by forecast available at entry; realized R may be
  booked only at exit.
- [ ] Keep a no-trade baseline in every comparison. If leverage policy cannot
  beat a fixed-risk/no-trade baseline after costs, it is rejected.
- [ ] Produce a portfolio equity curve, margin curve and liquidation/ADL
  diagnostic distribution, not just a sum of trade outcomes.

**Exit:** V7 can demonstrably block an AlphaForge 10x recommendation when the
exchange, account, portfolio or uncertainty constraint makes it unsafe.

### P6 — Runtime Binance Execution and Reconciliation

- [ ] Build the automatic execution path separately from manual live tools;
  manual overrides must never bypass automatic V7-Lite safety caps.
- [ ] Before every order: obtain current account/symbol configuration,
  leverage bracket, commission, position risk, mark price, open orders and
  available balance.
- [ ] Apply margin type and requested leverage idempotently; verify Binance's
  applied leverage does not exceed the V7-approved tier before submitting the
  entry order.
- [ ] Submit exchange-valid quantity and protective stop/target orders using
  deterministic client IDs; reconcile REST acknowledgement and user-data
  stream fills.
- [ ] After every fill/exit: persist realized fees, funding, fill prices,
  position leverage, margin type, liquidation price and exchange order IDs.
- [ ] Fail closed on stale account snapshots, bracket mismatch, missing stop,
  API timeout/unknown status, rate-limit breach or incomplete reconciliation.
- [ ] Use Binance testnet first, then shadow/paper observation. No live orders
  are permitted by this roadmap.

**Exit:** a testnet lifecycle is idempotent, reconciled and audit-complete from
preflight through exit, without any risk-cap bypass.

### P7 — Evidence Campaign and Promotion

- [ ] Run P0–P3 on one small, preregistered fixture before broad mining.
- [ ] Create the 20-symbol 1h leverage tensor first; use 56 symbols only after
  parity and storage/throughput checks pass.
- [ ] Run a staged research campaign: broad specialist screen → strict inner
  tuning for a small shortlist → sealed outer folds → frozen post-cutoff OOS.
- [ ] Require at least two demonstrably independent families before portfolio
  readiness can rise above its hard cap.
- [ ] Run interval-aware portfolio replay using actual holding intervals,
  selected leverage, margin usage and exit-time outcomes.
- [ ] Shadow only a frozen candidate; then reconcile paper/testnet outcomes
  against modeled costs and liquidation distance before any promotion request.

**Exit:** promotion evidence is chronological, cost-honest, portfolio-aware and
exchange-reconciled.

## Critical Path and Expected Research Cost

| Sequence | Deliverable | Estimate | Dependency |
|---|---|---:|---|
| 1 | P0 true-R parity + field correction | 1–3 engineering days | none |
| 2 | P1 contracts + P2 isolated-margin simulator | 3–6 engineering days | P0 |
| 3 | P3 explicit cost scenarios | 2–4 engineering days | P0/P2 |
| 4 | P4 leverage outcome tensor + first specialist models | 4–8 engineering days | P0–P3 |
| 5 | P5 V7 leverage gate + portfolio equity replay | 2–4 engineering days | P2/P4 |
| 6 | P6 testnet reconciliation path | 3–6 engineering days | P1/P5 |
| 7 | Frozen OOS and shadow evidence | market-time dependent | P0–P6 |

Initial compute estimate, after data/feature cache is warm:

| Campaign | Approximate work | Expected compute |
|---|---|---:|
| Parity fixture | One symbol, all 13 actions | minutes to <1 CPU hour |
| 20-symbol tensor screen | 13 actions × cost scenarios, cached | several CPU/GPU hours |
| Shortlist tuning | 3–5 specialists × 30–60 inner trials × WFV | roughly 10–40 GPU-hours, depending on data and preprocessing |
| 56-symbol confirmation | only frozen finalists | roughly 20–80 GPU-hours |

These are planning estimates, not benchmark results. Preprocessing remains a
known bottleneck and must be measured per run.

## Profitability Scenarios — Explicitly Conditional

These are hypotheses for prioritization, not return promises.

| Scenario | Preconditions | Expected effect versus fixed 1x/current sizing |
|---|---|---|
| Failure case | No positive base-risk alpha after true costs | 0% uplift; leverage makes results worse and candidate is rejected |
| Conservative success | One calibrated, cost-positive specialist | ~0–15% better geometric growth from avoiding weak trades and controlled sizing |
| Base success | One-to-two independent cost-surviving specialists | ~15–40% better geometric growth; expected drawdown can be lower than a fixed 3x policy because uncertainty is sized down |
| Strong success | Three independent specialists, stable calibration and portfolio caps | ~40–80% better geometric growth than fixed 1x sizing is plausible, but must be proven on frozen OOS and shadow evidence |

Cost survival is likely the first measurable improvement. In the existing
Truth-V6 example, modeled baseline cost was about `0.052R/trade`; reducing
avoidable execution drag or rejecting cost-fragile trades can plausibly recover
roughly `0.01–0.03R/trade` **if** the underlying gross edge is real. It cannot
rescue a negative base-risk alpha.

The primary upside of leverage-aware training is not a larger per-trade R. It
is allocating less capital to uncertain/tail-risk trades, allocating more only
to validated opportunities, and compounding a surviving portfolio more
efficiently. A 10x cap is an execution envelope and diagnostic scenario, not a
target average leverage.

## Immediate Next Task

Start with **P0 + P2.1** only:

1. Correct the forward-return versus true-R semantic mismatch.
2. Write the isolated-margin position contract and Binance bracket snapshot
adapter in Simulation.
3. Generate one 13-action, one-symbol parity fixture.
4. Run explicit 1x/1.5x/2x/3x cost scenarios on that fixture.

Do not train leverage models or submit any Binance order until that fixture
passes parity and cost-accounting tests.

## Sources

- [Binance USDⓈ-M Futures API index](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/Introduction)
  — official REST/WebSocket integration surface; reviewed 2026-07-13.
- [Binance Developer documentation index](https://developers.binance.com/en/docs/agent-native/llms-txt)
  — official index confirming USDⓈ-M leverage, margin type, bracket, position,
  commission and funding endpoints; reviewed 2026-07-13.
- [CFTC virtual-currency risk advisory](https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/understand_risks_of_virtual_currency.html)
  — leverage amplifies both gains and losses.
- [Leverage and Uncertainty](https://arxiv.org/abs/1612.07194) — supports
  fractional sizing under parameter uncertainty and heavy tails.

