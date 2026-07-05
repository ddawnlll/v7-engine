export const meta = {
  name: 'milestone-3-phase-3',
  description: 'Handoff, AlphaForge promotion, Policy Critic Phase 2',
  phases: [
    { title: 'Handoff & Promotion', detail: '#86 V7 handoff package + #99 AlphaForge -> V7 promotion' },
    { title: 'Policy Critic Phase 2', detail: '#92 Shadow replay buffer collection' },
  ],
}

phase('Handoff & Promotion')

var issue86 = await agent(
  "Read the following files and implement Issue #86 (V7 handoff package acceptance workflow -- AlphaForge -> V7 artifact promotion):\n" +
  "Existing code:\n" +
  "- contracts/schemas/alphaforge/v7_handoff_package.schema.json\n" +
  "- contracts/fixtures/alphaforge/v7_handoff_package_minimal.json\n" +
  "- alphaforge/docs/handoff_to_v7.md\n" +
  "- v7/gates/evaluator.py -- G0-G10 gate evaluator\n" +
  "- v7/evidence_consumer.py -- consume_evidence_passport()\n" +
  "Issue #86 asks for:\n" +
  "1. Define V7HandoffPackage contract (DONE -- schema + fixture exist)\n" +
  "2. Implement acceptance workflow: validate -> test -> accept/reject\n" +
  "3. Version handoff packages\n" +
  "4. Automated acceptance tests\n" +
  "Create v7/handoff.py with:\n" +
  "- HandoffPackage dataclass wrapping the contract schema\n" +
  "- HandoffAcceptor class:\n" +
  "  - accept(package: dict) -> HandoffResult: validate + test + accept/reject\n" +
  "  - validate_contract(package) -> list[str]: schema validation\n" +
  "  - run_gates(package) -> dict: run G0-G6 gates on the package\n" +
  "  - accept_candidate(package, gate_results) -> dict: produce accepted artifact record\n" +
  "  - reject_candidate(package, gate_results, reason) -> dict: produce rejection record\n" +
  "- HandoffResult dataclass (accepted: bool, artifact_id: str, gates: dict, acceptance_report: dict)\n" +
  "- Tests in v7/tests/test_handoff.py",
  {
    label: '#86 Handoff workflow',
    phase: 'Handoff & Promotion',
    agentType: 'general-purpose',
  }
)

var issue99 = await agent(
  "Read the following files and implement Issue #99 (AlphaForge P1.0: V7 handoff candidate -- artifact promotion from AlphaForge to V7):\n" +
  "Existing code:\n" +
  "- alphaforge/docs/handoff_to_v7.md\n" +
  "- v7/docs/roadmap.md -- artifact lifecycle section\n" +
  "- contracts/schemas/alphaforge/v7_handoff_package.schema.json\n" +
  "- contracts/schemas/alphaforge/mode_research_report.schema.json\n" +
  "- v7/handoff.py -- should exist from #86\n" +
  "- v7/gates/evaluator.py -- G0-G6 gates\n" +
  "Issue #99 asks for:\n" +
  "1. Formalize the AlphaForge -> V7 handoff protocol:\n" +
  "   - AlphaForge produces candidate model artifact + report package\n" +
  "   - Package passes G0-G6 gate validation\n" +
  "   - V7 accepts candidate into its artifact registry\n" +
  "   - V7 begins paper/shadow evaluation of accepted candidate\n" +
  "2. Document: which gates are AlphaForge-side vs V7-side\n" +
  "3. Version lock: handoff protocol versioning\n" +
  "What to implement:\n" +
  "- Create v7/promotion.py:\n" +
  "  - V7PromotionEngine class:\n" +
  "    - promote_from_alphaforge(handoff_package) -> PromotionResult: full promotion flow\n" +
  "    - run_pre_acceptance_gates(package) -> dict: G0-G4 gates (AlphaForge-side)\n" +
  "    - run_post_acceptance_gates(package) -> dict: G5-G10 gates (V7-side)\n" +
  "    - register_artifact(artifact) -> str: artifact_id\n" +
  "    - begin_shadow_evaluation(artifact_id) -> None: schedule shadow evaluation\n" +
  "  - PromotionResult dataclass (promoted: bool, artifact_id: str, gates_summary: dict, next_steps: list)\n" +
  "- Update alphaforge/docs/handoff_to_v7.md with gate ownership table\n" +
  "- Tests in v7/tests/test_promotion.py",
  {
    label: '#99 AlphaForge promotion',
    phase: 'Handoff & Promotion',
    agentType: 'general-purpose',
  }
)

phase('Policy Critic Phase 2')

var issue92 = await agent(
  "Read the following files and implement Issue #92 (PC Phase 2: Shadow replay buffer -- collect (s,a,r,s',t) tuples from paper trades):\n" +
  "Existing code:\n" +
  "- v7/policy_critic/replay_buffer.py -- existing replay buffer with (s,a,r,s',t) tuples\n" +
  "- v7/policy_critic/regret.py -- regret computation\n" +
  "- v7/policy_critic/expected_return.py -- expected return computation\n" +
  "- v7/policy_critic/docs/phase_plans/phase_2_shadow_replay_buffer.md\n" +
  "- v7/policy_critic/docs/replay_buffer_design.md\n" +
  "- v7/tests/test_replay_buffer.py -- existing tests\n" +
  "Issue #92 asks for:\n" +
  "1. Collect (state, action, reward, next_state, terminal) tuples from paper trading execution\n" +
  "2. Store in the existing replay buffer infrastructure\n" +
  "3. Subsampling strategy to prevent class imbalance (per-mode)\n" +
  "4. Shadow mode integration: observe without affecting execution\n" +
  "Create v7/policy_critic/shadow_collector.py with:\n" +
  "- ShadowCollector class:\n" +
  "  - collect_from_paper(decision_event, outcome) -> CriticTuple | None\n" +
  "  - extract_state(analysis_request) -> dict: feature vector from request\n" +
  "  - extract_action(decision_event) -> str: map to critic action space\n" +
  "  - extract_reward(trade_outcome) -> float: realized_r_net\n" +
  "  - extract_next_state(next_request) -> dict: feature vector at next step\n" +
  "  - is_terminal(trade_outcome) -> bool: resolution check\n" +
  "- SubsamplingStrategy class:\n" +
  "  - rebalance(tuples, target_ratios) -> list: balanced subset\n" +
  "  - Default ratios weighted toward NO_TRADE to prevent class imbalance\n" +
  "- ShadowIntegration class:\n" +
  "  - observe(request, event, outcome) -> None: observe paper trade without acting\n" +
  "  - get_shadow_buffer() -> ReplayBuffer: access to accumulated tuples\n" +
  "  - get_statistics() -> dict: buffer composition stats\n" +
  "- Tests in v7/policy_critic/tests/test_shadow_collector.py",
  {
    label: '#92 PC Phase 2 shadow',
    phase: 'Policy Critic Phase 2',
    agentType: 'general-purpose',
  }
)

return {
  issue_86: issue86,
  issue_99: issue99,
  issue_92: issue92,
}
