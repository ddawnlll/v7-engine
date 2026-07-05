export const meta = {
  name: 'milestone-3-phase-2',
  description: 'Execution stack, simulation interface, adapters, integration, evaluation modes',
  phases: [
    { title: 'Execution Stack', detail: '#39 layered execution-eligibility stack (6-layer gates)' },
    { title: 'Simulation Interface', detail: '#85 Runtime-hosted sim engine interface + #46 standardized adapters' },
    { title: 'Integration & Evaluation', detail: '#19 Runtime Simulation Integration + #20 Paper/Replay Evaluation Mode' },
  ],
}

phase('Execution Stack')

var issue39 = await agent(
  "Read the following files and implement Issue #39 (Layered execution-eligibility stack):\n" +
  "Existing code:\n" +
  "- v7/router.py -- MODE_PROFILES with mode config\n" +
  "- v7/policy.py -- evaluate_policy() with 4 gates (confidence, cost, risk, regime)\n" +
  "- v7/gates/evaluator.py -- G0-G10 gate evaluator\n" +
  "- v7/__init__.py\n" +
  "Issue #39 asks for a 6-layer execution-eligibility stack:\n" +
  "1. Structural -- valid request/result, mode supported\n" +
  "2. Engine -- model loaded, features available\n" +
  "3. Confidence -- model confidence >= mode threshold\n" +
  "4. Economic -- expected value positive after costs\n" +
  "5. Timing -- within trading window, cooldown respected\n" +
  "6. Operational -- exchange available, rate limits OK\n" +
  "Requirements:\n" +
  "- Each layer is an independent gate\n" +
  "- Each gate produces structured pass/fail with evidence\n" +
  "- Gates are ordered: if gate N fails, gate N+1 is not evaluated\n" +
  "- All gates transform a dict and return it with added gate evidence\n" +
  "Create v7/eligibility.py with:\n" +
  "- EligibilityLayer enum (STRUCTURAL, ENGINE, CONFIDENCE, ECONOMIC, TIMING, OPERATIONAL)\n" +
  "- EligibilityResult dataclass (eligible: bool, current_layer: str, gates: dict, blocking_reason: str, evidence: dict)\n" +
  "- EligibilityStack class:\n" +
  "  - evaluate(request, result, context) -> EligibilityResult\n" +
  "  - Each layer as a separate method\n" +
  "  - Layer 1 (Structural): validate request/result match, mode supported via router\n" +
  "  - Layer 2 (Engine): check model available, features fresh (config-driven)\n" +
  "  - Layer 3 (Confidence): confidence >= mode threshold from router profile\n" +
  "  - Layer 4 (Economic): expected_r_net >= min_expected_r (uses policy.py cost logic)\n" +
  "  - Layer 5 (Timing): cooldown check, trading window check (config-driven)\n" +
  "  - Layer 6 (Operational): exchange check, rate limit check (config-driven)\n" +
  "- Tests in v7/tests/test_eligibility.py covering all 6 layers, pass/fail paths, ordered evaluation",
  {
    label: '#39 Execution eligibility',
    phase: 'Execution Stack',
    agentType: 'general-purpose',
  }
)

phase('Simulation Interface')

var issue85 = await agent(
  "Read the following files and implement Issue #85 (Runtime-hosted simulation engine interface):\n" +
  "Existing code:\n" +
  "- simulation/engine/engine.py -- simulate() function\n" +
  "- simulation/contracts/models.py -- SimulationInput, SimulationOutput\n" +
  "- simulation/adapters/__init__.py -- empty\n" +
  "- simulation/adapters/training_adapter.py -- TrainingAdapter\n" +
  "- simulation/adapters/evaluation_adapter.py -- EvaluationAdapter\n" +
  "- simulation/adapters/paper_driver.py -- PaperDriver\n" +
  "- simulation/adapters/replay_driver.py -- ReplayDriver\n" +
  "- simulation/adapters/market_data_adapter.py -- market data adapter\n" +
  "- simulation/docs/replay_paper_and_runtime_hosting.md\n" +
  "Issue #85 asks for:\n" +
  "1. Define SimulationEngine interface (abstract base)\n" +
  "2. Implement adapter registration\n" +
  "3. Standardize input/output formats\n" +
  "4. Ensure side-effect-free execution guarantee\n" +
  "The existing adapters are thin wrappers around simulate(). Create a proper interface:\n" +
  "Create simulation/engine/interface.py with:\n" +
  "- SimulationEngine(ABC): abstract base with:\n" +
  "  - run(input: SimulationInput) -> SimulationOutput\n" +
  "  - get_adapter_kind() -> str\n" +
  "  - validate_input(input) -> list[str]\n" +
  "  - validate_output(output) -> list[str]\n" +
  "- AdapterRegistry class:\n" +
  "  - register(kind, adapter_class)\n" +
  "  - get(kind) -> SimulationEngine\n" +
  "  - list_adapters() -> list[str]\n" +
  "  - Standard kinds: TRAINING, EVALUATION, PAPER, REPLAY, MONTE_CARLO\n" +
  "- Refactor existing adapters (training_adapter.py, evaluation_adapter.py, paper_driver.py, replay_driver.py) to implement this interface\n" +
  "- Side-effect-free guarantee: add decorator or check that no network I/O or file mutation occurs during simulation run\n" +
  "- Tests in simulation/tests/test_engine_interface.py",
  {
    label: '#85 Sim engine interface',
    phase: 'Simulation Interface',
    agentType: 'general-purpose',
  }
)

var issue46 = await agent(
  "Read the following files and implement Issue #46 (Runtime simulation adapters -- paper forward, historical replay, training, evaluation, Monte Carlo):\n" +
  "Existing code:\n" +
  "- simulation/adapters/training_adapter.py -- thin TrainingAdapter wrapper\n" +
  "- simulation/adapters/evaluation_adapter.py -- thin EvaluationAdapter wrapper\n" +
  "- simulation/adapters/paper_driver.py -- thin PaperDriver wrapper\n" +
  "- simulation/adapters/replay_driver.py -- thin ReplayDriver wrapper\n" +
  "- simulation/docs/replay_paper_and_runtime_hosting.md\n" +
  "- simulation/adapters/__init__.py -- just a docstring\n" +
  "Issue #46 asks for 5 runtime simulation adapters:\n" +
  "1. Paper forward -- simulate trades going forward from current state\n" +
  "2. Historical replay -- replay past decisions against realized data\n" +
  "3. Training -- generate training samples from simulation\n" +
  "4. Evaluation -- backtest with cost model\n" +
  "5. Monte Carlo -- randomized scenarios for robustness\n" +
  "Design constraint: all adapters must be side-effect-free.\n" +
  "The existing thin wrappers exist but need to be standardized and enhanced:\n" +
  "1. Refactor simulation/adapters/__init__.py to export all adapters\n" +
  "2. Each adapter should implement the SimulationEngine interface (from #85)\n" +
  "3. Add proper input validation per adapter kind\n" +
  "4. Add proper output lineage tagging per adapter kind\n" +
  "5. Add adapter registration in AdapterRegistry\n" +
  "6. Ensure side-effect-free execution with explicit check\n" +
  "7. Tests in simulation/tests/test_adapters_standardized.py",
  {
    label: '#46 Simulation adapters',
    phase: 'Simulation Interface',
    agentType: 'general-purpose',
  }
)

phase('Integration & Evaluation')

var issue19 = await agent(
  "Read the following files and implement Issue #19 (Runtime Simulation Integration):\n" +
  "Existing code:\n" +
  "- simulation/adapters/training_adapter.py\n" +
  "- simulation/adapters/evaluation_adapter.py\n" +
  "- simulation/adapters/paper_driver.py\n" +
  "- simulation/adapters/replay_driver.py\n" +
  "- simulation/engine/engine.py -- simulate()\n" +
  "- v7/builder.py -- build_analysis_request()\n" +
  "- v7/validator.py -- validate_analysis_result()\n" +
  "- v7/policy.py -- evaluate_policy(), build_decision_event()\n" +
  "- v7/lifecycle.py -- should exist after #18 (DecisionEventManager, TradeOutcomeManager)\n" +
  "- v7/docs/runtime/runtime_integration.md\n" +
  "Issue #19 asks for V7 pipeline -> runtime simulation engine integration:\n" +
  "1. Training adapter (side-effect-free) -- DONE (exists)\n" +
  "2. Evaluation adapter -- DONE (exists)\n" +
  "3. Replay adapter -- DONE (exists)\n" +
  "4. Paper forward simulation adapter -- DONE (exists)\n" +
  "5. Monte Carlo robustness adapter -- NOT IMPLEMENTED\n" +
  "6. Integration tests -- NEEDED\n" +
  "7. Simulation output -> V7 contract mapping -- NEEDED\n" +
  "What to implement:\n" +
  "1. Create v7/runtime_integration.py that wires the full flow:\n" +
  "   Request -> Builder -> Router -> Policy -> Eligibility -> DecisionEvent -> Outcome\n" +
  "   Each step uses the appropriate simulation adapter for the mode\n" +
  "2. Integration flow class V7PipelineExecutor:\n" +
  "   - execute_request(raw_input) -> AnalysisRequest (uses builder)\n" +
  "   - route_and_validate(request) -> RouteResult (uses router)\n" +
  "   - evaluate_policy_and_eligibility(request, result) -> PolicyResult (uses policy + eligibility)\n" +
  "   - materialize_event(request, result, policy_result) -> DecisionEvent (uses lifecycle)\n" +
  "   - attach_outcome(event, sim_output) -> TradeOutcome (uses lifecycle)\n" +
  "3. Simulation output -> V7 contract mapping (simulation Output to TradeOutcome)\n" +
  "4. Integration tests in v7/tests/test_runtime_integration.py that exercise full flow",
  {
    label: '#19 Runtime sim integration',
    phase: 'Integration & Evaluation',
    agentType: 'general-purpose',
  }
)

var issue20 = await agent(
  "Read the following files and implement Issue #20 (Paper/Replay Evaluation Mode):\n" +
  "Existing code:\n" +
  "- simulation/adapters/paper_driver.py -- PaperDriver\n" +
  "- simulation/adapters/replay_driver.py -- ReplayDriver\n" +
  "- simulation/adapters/evaluation_adapter.py -- EvaluationAdapter\n" +
  "- simulation/engine/engine.py -- simulate()\n" +
  "Issue #20 asks for paper/replay evaluation mode implementation:\n" +
  "1. Paper mode implementation (per model_scope)\n" +
  "2. Replay mode implementation\n" +
  "3. Evaluation -> simulation adapter\n" +
  "4. No-trade behavior validation\n" +
  "5. Confidence surface validation\n" +
  "6. Integration tests\n" +
  "Create v7/evaluation.py with:\n" +
  "- PaperMode class:\n" +
  "  - run(symbol, mode, model_scope) -> Dict with DecisionEvent + TradeOutcome\n" +
  "  - Uses PaperDriver for forward simulation\n" +
  "  - Validates no-trade behavior (expected vs actual NO_TRADE rate)\n" +
  "  - Validates confidence surface (confidence vs realized outcome)\n" +
  "- ReplayMode class:\n" +
  "  - run(symbol, mode, model_scope, start, end) -> list of TradeOutcome\n" +
  "  - Uses ReplayDriver for historical simulation\n" +
  "  - Batch outcome collection with summary statistics\n" +
  "- EvaluationDriver class:\n" +
  "  - run_evaluation(symbol, mode) -> EvaluationReport\n" +
  "  - Combines paper + replay results\n" +
  "  - Produces structured EvaluationReport with metrics\n" +
  "- Tests in v7/tests/test_evaluation.py",
  {
    label: '#20 Paper/Replay eval',
    phase: 'Integration & Evaluation',
    agentType: 'general-purpose',
  }
)

return {
  issue_39: issue39,
  issue_85: issue85,
  issue_46: issue46,
  issue_19: issue19,
  issue_20: issue20,
}
