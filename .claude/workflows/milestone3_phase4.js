export const meta = {
  name: 'milestone-3-phase-4',
  description: 'Monte Carlo robustness simulation + Portfolio risk integration',
  phases: [
    { title: 'Monte Carlo', detail: '#101 Sim S4: N-path robustness simulation driver' },
    { title: 'Portfolio Risk', detail: '#105 V7 Phase 7: Portfolio risk + runtime integration' },
  ],
}

phase('Monte Carlo')

var issue101 = await agent(
  "Read the following files and implement Issue #101 (Sim S4: Monte Carlo driver -- implement N-path robustness simulation):\n" +
  "Existing code:\n" +
  "- simulation/docs/monte_carlo.md -- full spec\n" +
  "- simulation/docs/phases/S4__path_metrics_no-trade_quality_and_monte_carlo.md -- phase plan\n" +
  "- simulation/engine/engine.py -- simulate() function\n" +
  "- simulation/contracts/models.py -- SimulationInput, SimulationOutput, ActionOutcome, NoTradeOutcome data classes\n" +
  "- simulation/tests/\n" +
  "Issue #101 asks for the Monte Carlo robustness driver per the spec:\n" +
  "The spec says:\n" +
  "- N perturbed paths (default N=100) per trade scenario\n" +
  "- Perturbation Method 1: Price Noise (Gaussian noise on candles, sigma=0.002)\n" +
  "- Perturbation Method 2: Path Resampling with Bootstrap (resample bar-level returns)\n" +
  "- MonteCarloOutput with: expected_r_distribution (mean, std, p5, p25, p50, p75, p95), downside_risk (CVaR), target_before_stop_probability, stop_before_target_probability, tail_risk, confidence_stability\n" +
  "- Each output carries monte_carlo_run_id separate from base simulation_run_id\n" +
  "Create simulation/engine/monte_carlo.py with:\n" +
  "- PerturbationMethod enum (PRICE_NOISE, PATH_RESAMPLE)\n" +
  "- MonteCarloConfig dataclass (num_paths=100, perturbation_method=PRICE_NOISE, sigma=0.002, seed=42)\n" +
  "- MonteCarloResult dataclass with all spec fields:\n" +
  "  - monte_carlo_run_id, monte_carlo_family_version\n" +
  "  - base_simulation_run_id\n" +
  "  - perturbation_method, perturbation_sigma, num_paths\n" +
  "  - expected_r_distribution (with mean, std, p5, p25, p50, p75, p95)\n" +
  "  - downside_risk (CVaR)\n" +
  "  - target_before_stop_probability\n" +
  "  - stop_before_target_probability\n" +
  "  - tail_risk\n" +
  "  - confidence_stability (0-1)\n" +
  "- MonteCarloDriver class:\n" +
  "  - run(input: SimulationInput, config: MonteCarloConfig) -> MonteCarloResult\n" +
  "  - _perturb_price_noise(input, sigma) -> list[SimulationInput]: N perturbed inputs\n" +
  "  - _perturb_path_resample(input) -> list[SimulationInput]: N bootstrapped inputs\n" +
  "  - _run_batch(inputs) -> list[SimulationOutput]: run simulation on each\n" +
  "  - _aggregate(outputs) -> MonteCarloResult: compute distributional metrics\n" +
  "  - _compute_cvar(values, alpha=0.05) -> float: CVaR / expected shortfall\n" +
  "  - _compute_stability(values) -> float: confidence stability metric\n" +
  "- Tests in simulation/tests/test_monte_carlo.py covering:\n" +
  "  - Price noise perturbation (shape preservation, noise distribution)\n" +
  "  - Path resampling bootstrap\n" +
  "  - MonteCarloDriver run with synthetic inputs\n" +
  "  - Aggregation correctness (mean, std, percentiles, CVaR)\n" +
  "  - Edge cases: N=1, N=1000, invalid sigma, seed determinism",
  {
    label: '#101 Monte Carlo',
    phase: 'Monte Carlo',
    agentType: 'general-purpose',
  }
)

phase('Portfolio Risk')

var issue105 = await agent(
  "Read the following files and implement Issue #105 (V7 Phase 7: Portfolio risk + runtime integration):\n" +
  "Existing code:\n" +
  "- v7/docs/roadmap.md -- Phase 6-7 descriptions\n" +
  "- v7/docs/implementation/phase_7_portfolio_risk_and_runtime_integration.md\n" +
  "- v7/policy.py -- evaluate_policy()\n" +
  "- v7/eligibility.py -- should exist after #39\n" +
  "- v7/gates/evaluator.py\n" +
  "- runtime/api/routes/portfolio.py -- existing portfolio routes\n" +
  "- runtime/services/ -- various services\n" +
  "Issue #105 asks for:\n" +
  "1. Policy surface per model_scope -- per-mode policy decisions\n" +
  "2. Portfolio suppression -- prevent over-concentration, correlated bets\n" +
  "3. Risk hard guards -- absolute position limits, drawdown kill\n" +
  "4. Runtime integration -- wire into existing runtime services\n" +
  "Create v7/portfolio.py with:\n" +
  "- PortfolioManager class:\n" +
  "  - evaluate_portfolio(requests: list, results: list, positions: dict) -> PortfolioResult\n" +
  "  - suppress_overconcentration(decisions, symbol_exposure) -> list: lower rank for over-concentrated\n" +
  "  - suppress_correlated(decisions, correlation_matrix) -> list: lower rank for correlated bets\n" +
  "  - apply_position_limits(decisions, max_positions, max_exposure) -> list: cap by limits\n" +
  "- PortfolioResult dataclass (suppressed: list, ranked: list, exposure_remaining: float, concentration_warnings: list)\n" +
  "Create v7/risk.py with:\n" +
  "- RiskManager class:\n" +
  "  - check_hard_guards(portfolio_result, account_state) -> RiskResult\n" +
  "  - Hard guards: max_drawdown, max_exposure_per_symbol, max_correlated_exposure, kill_switch_active\n" +
  "  - Each guard returns structured pass/fail with reason\n" +
  "- RiskResult dataclass (risk_ok: bool, blocking_guards: list, drawdown_state: dict, warnings: list)\n" +
  "Create v7/tests/test_portfolio.py, v7/tests/test_risk.py with full test coverage",
  {
    label: '#105 Portfolio risk',
    phase: 'Portfolio Risk',
    agentType: 'general-purpose',
  }
)

return {
  issue_101: issue101,
  issue_105: issue105,
}
