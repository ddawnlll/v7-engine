export const meta = {
  name: 'milestone-3-phase-1',
  description: 'Foundation: contracts, lifecycle, builders, router, scope, gates, cross-domain mapping',
  phases: [
    { title: 'Contract Lifecycle', detail: '#17 AnalysisRequest/Result + #18 DecisionEvent/TradeOutcome lifecycle code' },
    { title: 'Builders & Router', detail: '#31 Request Builder, #33 Result Validator, #34 Mod Router + scope' },
    { title: 'Cross-Domain & Gates', detail: '#81 field mapping code, #42 promotion gates CI, #84/#88 scope validation' },
    { title: 'Policy Critic Phase 1', detail: '#91 observability + schema -- metrics pipeline' },
  ],
}

var CONTEXT = [
  "builder.py, validator.py, router.py exist as basic V6-style implementations",
  "contracts/ has all schemas (analysis_request, analysis_result, decision_event, trade_outcome)",
  "simulation/adapters/ has thin wrappers (TrainingAdapter, EvaluationAdapter, PaperDriver, ReplayDriver)",
  "gates/evaluator.py has G0-G10 with G1-G3/G5-G6 placeholders, G7-G10 NOT_APPLICABLE",
  "v7/__init__.py version 0.1.0",
  "Policy Critic Phase 0 complete (replay_buffer, regret, expected_return)",
  "Closed issues: #110 (PolicyCriticReview contract), #134, #133, #132, #45",
].join("\n")

phase('Contract Lifecycle')

var issue17 = await agent(
  "Read the following files and implement Issue #17 (AnalysisRequest/Result Contract Implementation):\n" +
  "Existing code:\n" +
  "- v7/builder.py -- has build_analysis_request() and validate_analysis_request()\n" +
  "- v7/validator.py -- has build_analysis_result() and validate_analysis_result()\n" +
  "- contracts/schemas/analysis_request.schema.json\n" +
  "- contracts/schemas/analysis_result.schema.json\n" +
  "The issue asks for:\n" +
  "1. Full AnalysisRequest builder implementation that matches the contract spec (all required fields from v7/docs/contracts/analysis_request.md: contract_version, state_schema_version, snapshot_builder_version, request_kind, identity section, scope section with symbol/requested_trade_mode/model_scope/primary_interval/analysis_mode, canonical_state)\n" +
  "2. Full AnalysisResult validator that matches the contract spec (contract section, identity, request_link, status with signal_status/decision_status/is_actionable, decision with recommended_action/direction/decision_summary, scores section with confidence/confidence_kind/expected_r, execution_guidance, fallback_and_degradation)\n" +
  "3. Serialization/deserialization round-trip tests\n" +
  "4. Schema version alignment verification\n" +
  "5. Contract validation tests\n" +
  "The existing builder.py is too simple -- it doesn't cover the full contract shape (no canonical_state, no contract_version/state_schema_version, no request_kind, no analysis_mode). The validator.py uses V6-style decisions (ENTER_LONG/ENTER_SHORT/HOLD) instead of V7's LONG_NOW/SHORT_NOW/NO_TRADE.\n" +
  "Implement the complete versions matching the V7 contract authority docs. Create tests in v7/tests/test_contract_full.py.",
  {
    label: '#17 AnalysisRequest/Result',
    phase: 'Contract Lifecycle',
    agentType: 'general-purpose',
  }
)

var issue18 = await agent(
  "Read the following files and implement Issue #18 (DecisionEvent & TradeOutcome Lifecycle):\n" +
  "Existing code/schemas:\n" +
  "- contracts/schemas/decision_event.schema.json\n" +
  "- contracts/schemas/trade_outcome.schema.json\n" +
  "- v7/policy.py has a basic build_decision_event() function\n" +
  "- contracts/fixtures/decision_event_minimal.json\n" +
  "- contracts/fixtures/trade_outcome_minimal.json\n" +
  "The issue asks for:\n" +
  "1. DecisionEvent contract lifecycle: create -> persist -> update -> close\n" +
  "   - Create DecisionEvent from AnalysisResult\n" +
  "   - Include all required sections: contract, identity, lineage, scope, request_summary, decision_summary, runtime_interpretation, execution_linkage, outcome_linkage, observability\n" +
  "   - Match the schema at contracts/schemas/decision_event.schema.json\n" +
  "2. TradeOutcome contract lifecycle: create -> update -> resolve\n" +
  "   - Create TradeOutcome from DecisionEvent\n" +
  "   - Include all required sections: contract, identity, lineage, execution_summary, resolution_status, realized_outcome, path_metrics, comparative_outcome, quality_and_interpretation\n" +
  "   - Match the schema at contracts/schemas/trade_outcome.schema.json\n" +
  "3. Event lifecycle management: PENDING -> RESOLVED/PARTIALLY_RESOLVED/INVALIDATED\n" +
  "4. Outcome tracking (outcome_source: LIVE_EXECUTION, PAPER_EXECUTION, REPLAY_PROJECTION, etc.)\n" +
  "5. Lifecycle integration tests\n" +
  "6. Traceability verification\n" +
  "The existing build_decision_event() in v7/policy.py is too basic -- it doesn't match the full contract shape. Replace/rewrite it.\n" +
  "Create a new module v7/lifecycle.py with DecisionEventManager and TradeOutcomeManager classes.\n" +
  "Create tests in v7/tests/test_lifecycle.py.",
  {
    label: '#18 DecisionEvent/TradeOutcome',
    phase: 'Contract Lifecycle',
    agentType: 'general-purpose',
  }
)

phase('Builders & Router')

var issue31_33_34 = await agent(
  "Read the following files and implement Issues #31, #33, #34 together:\n" +
  "Existing code:\n" +
  "- v7/builder.py -- has basic build_analysis_request()\n" +
  "- v7/validator.py -- has basic build_analysis_result() and validate_analysis_result()\n" +
  "- v7/router.py -- has RouteResult, route_request(), get_mode_profile(), get_available_modes()\n" +
  "- contracts/schemas/analysis_request.schema.json\n" +
  "- contracts/schemas/analysis_result.schema.json\n" +
  "- v7/tests/test_builder.py\n" +
  "- v7/tests/test_validator.py\n" +
  "- v7/tests/test_router.py\n" +
  "Issue #31 asks for (V7 Request Builder):\n" +
  "1. Implement request builder with schema validation\n" +
  "2. Populate required fields: symbol, mode, timeframe, feature_window, confidence_window\n" +
  "3. Validate against AnalysisRequest contract schema\n" +
  "4. Unit tests\n" +
  "Enhance the existing builder.py to:\n" +
  "- Full contract_version/state_schema_version/snapshot_builder_version\n" +
  "- Proper identity section (request_id, timestamp_utc, trace_id)\n" +
  "- Full scope section (symbol, requested_trade_mode, model_scope, primary_interval, analysis_mode, context_intervals, refinement_intervals)\n" +
  "- canonical_state construction (raw_window, derived_state, context, quality, metadata)\n" +
  "- quality_and_freshness, degradation_context, runtime_context\n" +
  "- Handle all request_kind values: live_scan, paper_scan, replay_eval, shadow, validation\n" +
  "Issue #33 asks for (V7 Result Validator):\n" +
  "1. Schema validation against AnalysisResult contract\n" +
  "2. Sanity checks: confidence in [0,1], threshold comparisons\n" +
  "3. Reject malformed results with structured errors\n" +
  "4. Unit tests\n" +
  "Update the existing validator.py from V6 to V7 semantics:\n" +
  "- recommended_action: LONG_NOW, SHORT_NOW, NO_TRADE\n" +
  "- signal_status: SIGNAL, NO_TRADE, FILTERED, DEGRADED, ERROR\n" +
  "- decision_status: VALID, LOW_CONFIDENCE, BLOCKED, DEGRADED, FAILED\n" +
  "- Add request_link validation (symbol match, model_scope match, trade_mode match)\n" +
  "- Add execution_guidance validation (entry_price, stop_loss, take_profit for actionable trades)\n" +
  "- Add fallback_and_degradation validation\n" +
  "Issue #34 asks for (V7 Mod Router):\n" +
  "1. Implement mode router class in v7/\n" +
  "2. Scope compatibility rules: SWING vs SCALP vs AGGRESSIVE_SCALP\n" +
  "3. Reject invalid mode/scope combinations\n" +
  "4. Unit tests for all routing paths\n" +
  "Enhance the existing router.py with:\n" +
  "- Scope compatibility validation (not just mode status)\n" +
  "- Artifact scope tagging support\n" +
  "- Model_scope validation (swing_v1, scalp_v1, aggressive_scalp_v1)\n" +
  "Create enhanced versions in place. Update tests accordingly.",
  {
    label: '#31+#33+#34 Builder/Router/Validator',
    phase: 'Builders & Router',
    agentType: 'general-purpose',
  }
)

phase('Cross-Domain & Gates')

var issue81 = await agent(
  "Read the following files and implement Issue #81 (V7 <-> AlphaForge <-> Simulation cross-domain field mapping):\n" +
  "Existing docs:\n" +
  "- contracts/mappings/simulation_to_v7.json\n" +
  "- contracts/mappings/simulation_to_alphaforge.json\n" +
  "- contracts/mappings/simulation_to_alphaforge.md\n" +
  "- contracts/mappings/alphaforge_to_v7.md\n" +
  "- contracts/registry.json\n" +
  "The issue asks for:\n" +
  "1. Map every field that crosses domain boundaries\n" +
  "2. Document field transformations (renames, unit conversions, aggregations)\n" +
  "3. Implement field mapping validation\n" +
  "4. Add to contract registry\n" +
  "The mapping docs exist but no runtime code validates or enforces them.\n" +
  "Create v7/mappings.py with:\n" +
  "- FieldMapping dataclass (source_domain, source_field, target_domain, target_field, transform_fn, validation_rules)\n" +
  "- CrossDomainMapper class with methods:\n" +
  "  - map_simulation_to_v7(sim_output) -> dict (using simulation_to_v7.json mappings)\n" +
  "  - map_simulation_to_alphaforge(sim_output) -> dict (using simulation_to_alphaforge.json)\n" +
  "  - map_alphaforge_to_v7(af_output) -> dict (using alphaforge_to_v7.md mappings)\n" +
  "  - validate_field_mapping(mapping_def) -> list[str] (validation errors)\n" +
  "- Tests in v7/tests/test_mappings.py covering all mapped fields",
  {
    label: '#81 Cross-domain mapping',
    phase: 'Cross-Domain & Gates',
    agentType: 'general-purpose',
  }
)

var issue42 = await agent(
  "Read the following files and implement Issue #42 (Promotion gate automation -- CI-integrated G0-G10 evaluation pipeline):\n" +
  "Existing code:\n" +
  "- v7/gates/evaluator.py -- has G0-G10 with G0 fully implemented, G4 fully implemented, others placeholders\n" +
  "- v7/tests/test_gates.py\n" +
  "- .github/workflows/ci.yml\n" +
  "The issue asks for:\n" +
  "1. Implement G0-G10 gate evaluator as automated checks\n" +
  "2. CI integration: every model candidate passes gates automatically\n" +
  "3. Gate results as structured output (JSON report)\n" +
  "4. Block promotion on gate failure\n" +
  "5. Gate configuration as version-controlled config\n" +
  "What needs to change:\n" +
  "- v7/gates/evaluator.py: Implement real gate logic for G1, G5 (beyond placeholders):\n" +
  "  - G1 RESEARCH_BACKTEST: check research backtest metrics from WFV results\n" +
  "  - G5 SYMBOL_STABILITY: real per-symbol contribution check when multi-symbol data available\n" +
  "- Create v7/gates/runner.py: automated gate runner that:\n" +
  "  - Loads candidate artifact\n" +
  "  - Runs all applicable gates\n" +
  "  - Produces structured JSON report\n" +
  "  - Returns pass/fail with evidence\n" +
  "- Create .github/actions/gate-check/action.yml: reusable CI action for gate evaluation\n" +
  "- Update .github/workflows/ci.yml to include gate check step\n" +
  "- Create configs/gates.yaml: gate configuration (thresholds, enabled gates, stop_on_fail)\n" +
  "- Tests in v7/tests/test_gate_runner.py",
  {
    label: '#42 Gate automation CI',
    phase: 'Cross-Domain & Gates',
    agentType: 'general-purpose',
  }
)

var issue84_88 = await agent(
  "Read the following files and implement Issues #84 and #88:\n" +
  "Existing code:\n" +
  "- v7/router.py -- has MODE_PROFILES with mode statuses and configuration\n" +
  "- v7/__init__.py\n" +
  "Issue #84 (Scope-compatible artifact selection):\n" +
  "1. Implement artifact scope tagging\n" +
  "2. Selection logic: only return artifacts matching requested scope\n" +
  "3. Block with structured scope_mismatch error\n" +
  "4. Unit tests\n" +
  "Issue #88 (Scope compatibility validation):\n" +
  "1. Define scope compatibility matrix\n" +
  "2. Implement validation in mod router\n" +
  "3. Add scope_mismatch blocking with clear error\n" +
  "4. Unit tests\n" +
  "Create v7/scope.py with:\n" +
  "- ArtifactScope dataclass (model_scope, trade_mode, primary_interval, version)\n" +
  "- SCOPE_COMPATIBILITY_MATRIX: which scopes can be used with which modes\n" +
  "  - swing_v1 -> SWING only\n" +
  "  - scalp_v1 -> SCALP only (and HOLD-aware)\n" +
  "  - aggressive_scalp_v1 -> AGGRESSIVE_SCALP only (and HOLD-aware)\n" +
  "- select_compatible_artifacts(artifacts, requested_scope) -> tuple[list, list[str]]\n" +
  "- validate_scope_compatibility(request_scope, artifact_scope) -> list[str]\n" +
  "- ScopeMismatchError exception with structured fields\n" +
  "- Tests covering all compatibility paths, mismatch scenarios, HOLD-mode blocking",
  {
    label: '#84+#88 Scope validation',
    phase: 'Cross-Domain & Gates',
    agentType: 'general-purpose',
  }
)

phase('Policy Critic Phase 1')

var issue91 = await agent(
  "Read the following files and implement Issue #91 (PC Phase 1: Observability + schema -- metrics pipeline):\n" +
  "Existing code:\n" +
  "- v7/policy_critic/replay_buffer.py -- replay buffer with (s,a,r,s',terminal) tuples\n" +
  "- v7/policy_critic/regret.py -- regret computation\n" +
  "- v7/policy_critic/expected_return.py -- expected return computation\n" +
  "- contracts/schemas/policy_critic_review.schema.json\n" +
  "- contracts/fixtures/policy_critic_review_minimal.json\n" +
  "Issue #110 is already CLOSED (PolicyCriticReview contract registered)\n" +
  "The issue asks for:\n" +
  "1. Register PolicyCriticReview contract in contracts/registry.json with full schema (DONE -- #110 closed)\n" +
  "2. Implement metrics pipeline for critic outputs:\n" +
  "   - critic_value_LONG, critic_value_SHORT, critic_verdict (BULLISH/BEARISH/NEUTRAL/SKIP)\n" +
  "   - conformal_p_value, regret_r, expected_R\n" +
  "3. Wire into runtime observability (emit structured metric events)\n" +
  "4. Schema version alignment tests\n" +
  "5. Contract fixture updates if needed\n" +
  "Create v7/policy_critic/metrics.py with:\n" +
  "- CriticMetrics dataclass (critic_value_LONG, critic_value_SHORT, critic_verdict, conformal_p_value, regret_r, expected_R, timestamp_utc, symbol, model_scope)\n" +
  "- CriticMetricsPipeline class:\n" +
  "  - ingest(decision_event) -> CriticMetrics: extract critic-relevant metrics from DecisionEvent\n" +
  "  - to_review_schema(metrics) -> dict: convert to PolicyCriticReview contract shape\n" +
  "  - validate(metrics) -> list[str]: validate against schema\n" +
  "- Tests in v7/policy_critic/tests/test_metrics.py\n" +
  "Verify the contract is registered in contracts/registry.json and update if needed.",
  {
    label: '#91 PC Phase 1 metrics',
    phase: 'Policy Critic Phase 1',
    agentType: 'general-purpose',
  }
)

return {
  issue_17: issue17,
  issue_18: issue18,
  issue_31_33_34: issue31_33_34,
  issue_81: issue81,
  issue_42: issue42,
  issue_84_88: issue84_88,
  issue_91: issue91,
}
