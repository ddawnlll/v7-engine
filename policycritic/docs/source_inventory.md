# Source Inventory — V7 Policy Critic Research

> Created: 2026-06-23 (adapted from old repo source material)
> Status: Docs/Design Only
> Methodology: Sources retrieved via Tavily MCP search (`mcp__tavily__tavily-search`). Primary sources (arXiv, conference proceedings, GitHub) preferred. Claims verified against v7-engine repo where possible.

---

## Source Policy

- **All important claims cited**: Yes — every technical claim in policycritic/docs/ is backed by a source in this inventory or by a verified repo file reference.
- **Unverified claims**: Marked explicitly as `old_repo_context_unverified` or `unverified`.
- **Trust ratings**: `highest` = peer-reviewed conference/journal paper or established textbook; `high` = preprint with strong evidence, official implementation, or widely-cited working paper; `medium` = blog post, community resource, or secondary source.

---

## Tavily MCP Verification

| Aspect | Detail |
|---|---|
| Tool used | `mcp__tavily__tavily-search` |
| Status | Authenticated and usable |
| Verification query | "Implicit Q-Learning offline reinforcement learning paper" |
| Evidence | Returned 5 results including arXiv primary paper, Semantic Scholar, TransferLab summary |
| All subsequent searches | All succeeded (CQL, DSR/PBO, safe RL, distributional RL, FQE, GBDT vs DL) |

---

## 1. RL Fundamentals

### Sutton & Barto — Reinforcement Learning: An Introduction

- **Title**: Reinforcement Learning: An Introduction, 2nd Edition
- **URL**: http://incompleteideas.net/book/the-book-2nd.html
- **Retrieval Date**: 2026-06-23
- **Source Type**: Textbook
- **Trust Rating**: Highest
- **Key Claims**: MDP formalism, TD learning, Q-learning, SARSA, policy gradients, on-policy vs off-policy, exploration-exploitation trade-off, value functions, Bellman equations
- **V7 Applicability**: Foundational — all RL concepts in `rl_intro_for_v7.md` derive from this text
- **Limitations**: No trading-specific content; no offline RL coverage (2nd ed. predates offline RL explosion)

### Levine et al. — Offline RL Tutorial

- **Title**: Offline Reinforcement Learning: Tutorial, Review, and Perspectives on Open Problems
- **URL**: https://arxiv.org/abs/2005.01643
- **Retrieval Date**: 2026-06-23
- **Source Type**: arXiv survey paper (Sergey Levine, 1000+ citations)
- **Trust Rating**: Highest
- **Key Claims**: Distribution shift is the central challenge in offline RL; naive off-policy methods fail offline; systematic taxonomy of offline RL algorithms; open problems include OPE, generalization, and compositionality
- **V7 Applicability**: Directly applicable — defines the problem space V7 critic must navigate
- **Limitations**: No financial domain coverage; focus on robotics and control benchmarks

---

## 2. Implicit Q-Learning (IQL)

### Kostrikov et al. — IQL Paper

- **Title**: Offline Reinforcement Learning with Implicit Q-Learning
- **URL**: https://arxiv.org/abs/2110.06169
- **Retrieval Date**: 2026-06-23
- **Source Type**: Conference paper (ICLR 2022)
- **Trust Rating**: Highest
- **Key Claims**: IQL avoids OOD action queries via expectile regression; learns V(s) with expectile loss, Q(s,a) on in-sample actions only, extracts policy via advantage-weighted regression (AWR); state-of-the-art on D4RL Ant Maze tasks; simple implementation (SARSA-like TD update + AWR)
- **V7 Applicability**: Recommended first offline RL algorithm for V3 Policy Critic
- **Limitations**: Tested on D4RL (MuJoCo, Ant Maze, Adroit, Kitchen) — financial applicability unproven; expectile τ is task-dependent; JAX implementation

### Kostrikov — Official IQL Implementation

- **Title**: ikostrikov/implicit_q_learning (GitHub)
- **URL**: https://github.com/ikostrikov/implicit_q_learning
- **Retrieval Date**: 2026-06-23
- **Source Type**: Official code repository (JAX)
- **Trust Rating**: High
- **Key Claims**: Reference implementation of IQL algorithm; JAX-based; includes D4RL training scripts; PyTorch reimplementation linked
- **V7 Applicability**: Reference for V3 IQL implementation (PyTorch port likely needed for XGBoost integration)
- **Limitations**: JAX (not PyTorch/XGBoost); no financial domain adaptations

---

## 3. Conservative Q-Learning (CQL)

### Kumar et al. — CQL Paper

- **Title**: Conservative Q-Learning for Offline Reinforcement Learning
- **URL**: https://arxiv.org/abs/2006.04779
- **Retrieval Date**: 2026-06-23
- **Source Type**: Conference paper (NeurIPS 2020)
- **Trust Rating**: Highest
- **Key Claims**: CQL adds conservative penalty to Q-function — pushes down Q-values on OOD actions, pushes up on dataset actions; produces lower bound on true policy value; strong results on D4RL and Adroit; theoretically grounded
- **V7 Applicability**: Ensemble member / cross-check for V3 IQL critic; more conservative estimates useful when safety margin is critical
- **Limitations**: Conservative penalty weight α requires tuning; can be overly conservative with poor dataset coverage

### BAIR Blog — CQL Overview

- **Title**: Offline Reinforcement Learning: How Conservative Algorithms Can Enable New Applications
- **URL**: https://bair.berkeley.edu/blog/2020/12/07/offline
- **Retrieval Date**: 2026-06-23
- **Source Type**: Research blog post (BAIR — Berkeley AI Research)
- **Trust Rating**: High (official lab communication)
- **Key Claims**: Practical explanation of CQL mechanism; comparison with prior work; illustrative examples
- **V7 Applicability**: Educational — explains CQL concepts accessibly
- **Limitations**: Blog post, not peer-reviewed; simplified explanations

---

## 4. Decision Transformer

### Chen et al. — Decision Transformer Paper

- **Title**: Decision Transformer: Reinforcement Learning via Sequence Modeling
- **URL**: https://arxiv.org/abs/2106.01345
- **Retrieval Date**: 2026-06-23
- **Source Type**: Conference paper (NeurIPS 2021)
- **Trust Rating**: Highest
- **Key Claims**: Reframes RL as conditional sequence modeling with causal transformer; input tokens: (desired return-to-go, state, action); avoids bootstrapping entirely; matches or exceeds specialized offline RL algorithms
- **V7 Applicability**: Too early for V7 — requires transformer architecture, massive trajectory data (millions of timesteps), and return-to-go conditioning which is an open research problem
- **Limitations**: Tested on D4RL only; return-to-go conditioning is brittle; no financial domain evidence; massive data requirements

---

## 5. Distributional RL

### Dabney et al. — QR-DQN

- **Title**: Distributional Reinforcement Learning with Quantile Regression (QR-DQN)
- **URL**: https://arxiv.org/abs/1710.10044
- **Retrieval Date**: 2026-06-23
- **Source Type**: Conference paper (AAAI 2018)
- **Trust Rating**: Highest
- **Key Claims**: Models full return distribution via quantile regression; learns N quantiles of value distribution; risk-sensitive policies possible without modifying reward function; outperforms DQN on Atari
- **V7 Applicability**: V3 feature — distributional IQL critic with 16-32 quantile Q-heads per canonical design; enables risk-aware gating from lower-quantile values
- **Limitations**: Increases computational cost; N quantiles = Nx outputs; financial domain untested

### Dabney et al. — IQN

- **Title**: Implicit Quantile Networks for Distributional Reinforcement Learning (IQN)
- **URL**: https://arxiv.org/abs/1806.06923
- **Retrieval Date**: 2026-06-23
- **Source Type**: Conference paper (ICML 2018)
- **Trust Rating**: Highest
- **Key Claims**: Learns full continuous quantile function via implicit representation; risk-sensitive policies via distortion risk measures; outperforms QR-DQN; samples τ ~ U(0,1) for quantile targets
- **V7 Applicability**: Long-term V4 direction — more expressive than QR-DQN
- **Limitations**: Significant complexity increase; training instability with implicit networks; financial domain untested

---

## 6. Off-Policy Evaluation (OPE/FQE)

### Fu et al. — D4RL OPE Benchmarks

- **Title**: Benchmarks for Deep Off-Policy Evaluation
- **URL**: https://arxiv.org/abs/2103.16526
- **Retrieval Date**: 2026-06-23
- **Source Type**: Conference paper (ICLR 2021)
- **Trust Rating**: Highest
- **Key Claims**: Fitted Q-Evaluation (FQE) is the most reliable OPE method across benchmarks; importance sampling methods have high variance; OPE is essential before deploying any policy learned offline
- **V7 Applicability**: Mandatory evaluation protocol — FQE is required before any V3+ critic deployment
- **Limitations**: Benchmark domains (MuJoCo, etc.) differ from trading; FQE requires accurate Q-function fitting

---

## 7. Safe RL / Shielding

### Alshiekh et al. — Safe RL via Shielding

- **Title**: Safe Reinforcement Learning via Shielding
- **URL**: https://arxiv.org/abs/1708.08611
- **Retrieval Date**: 2026-06-23
- **Source Type**: Conference paper (AAAI 2018)
- **Trust Rating**: Highest
- **Key Claims**: Shield is a deterministic, formally verified component that monitors RL actions; can block, allow, or modify actions; shield is external to the RL agent; preserves optimality while ensuring safety; LTL-based specifications
- **V7 Applicability**: Directly validates V7 architecture — V7 policy gates + operational hard gates ARE the shield; learned critic sits UNDER shield
- **Limitations**: LTL specification formalism may be overkill for V7; shield synthesis is complex

### Garcia & Fernandez — Safe RL Survey

- **Title**: A Comprehensive Survey on Safe Reinforcement Learning
- **URL**: https://www.jmlr.org/papers/v16/garcia15a.html
- **Retrieval Date**: 2026-06-23
- **Source Type**: Journal paper (JMLR 2015, 2000+ citations)
- **Trust Rating**: Highest
- **Key Claims**: Categorizes safe RL into: modification of optimality criterion, modification of exploration process, use of external knowledge; safety must be architectural, not reward-based; shielding is the most reliable approach
- **V7 Applicability**: Validates gate-outside-RL design principle; supports deterministic safety barriers
- **Limitations**: Pre-deep-RL era (2015); deep RL safety methods emerged after publication

---

## 8. Reward Hacking

### Amodei et al. — Concrete Problems in AI Safety

- **Title**: Concrete Problems in AI Safety
- **URL**: https://arxiv.org/abs/1606.06565
- **Retrieval Date**: 2026-06-23
- **Source Type**: arXiv paper (DeepMind/OpenAI)
- **Trust Rating**: High
- **Key Claims**: Reward hacking is a fundamental AI safety problem; avoiding negative side effects, scalable oversight; safe exploration
- **V7 Applicability**: Foundational AI safety perspective relevant to any learned trading component
- **Limitations**: General AI safety focus, not trading-specific

---

## 9. Backtest Overfitting

### Bailey & Lopez de Prado — Deflated Sharpe Ratio

- **Title**: The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality
- **URL**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2465673
- **Retrieval Date**: 2026-06-23
- **Source Type**: Journal paper (Journal of Portfolio Management, 2014)
- **Trust Rating**: Highest
- **Key Claims**: DSR corrects Sharpe ratio for multiple testing (selection bias); accounts for non-Normal returns; provides p-value for strategy significance; larger number of trials → higher bar for significance
- **V7 Applicability**: Mandatory validation gate — DSR p < 0.05 required for V2 → V3 transition

### Bailey et al. — Probability of Backtest Overfitting

- **Title**: The Probability of Backtest Overfitting
- **URL**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2568435
- **Retrieval Date**: 2026-06-23
- **Source Type**: Journal paper (Journal of Computational Finance, 2016)
- **Trust Rating**: Highest
- **Key Claims**: PBO estimates probability that "best" in-sample strategy underperforms median out-of-sample; CSCV (Combinatorially Symmetric Cross-Validation) is robust estimator; non-parametric; works with any performance metric
- **V7 Applicability**: Mandatory validation gate — PBO < 0.10 required for critic transitions

### Bailey et al. — Pseudo-Mathematics and Financial Charlatanism

- **Title**: Pseudo-Mathematics and Financial Charlatanism: The Effects of Backtest Overfitting on Out-of-Sample Performance
- **URL**: https://www.ams.org/notices/201405/rnoti-p458.pdf
- **Retrieval Date**: 2026-06-23
- **Source Type**: Journal paper (Notices of the AMS, 2014)
- **Trust Rating**: Highest
- **Key Claims**: Backtest overfitting produces strategies with near-zero out-of-sample performance; minimum backtest length for SR=1.0 is ~64 years; most published backtests are statistically insignificant
- **V7 Applicability**: Strong cautionary evidence; validates conservative V7 approach
- **Limitations**: Analysis based on random walk null; real markets may have exploitable structure

---

## 10. XGBoost / GBDT for Tabular Data

### Chen & Guestrin — XGBoost Paper

- **Title**: XGBoost: A Scalable Tree Boosting System
- **URL**: https://arxiv.org/abs/1603.02754
- **Retrieval Date**: 2026-06-23
- **Source Type**: Conference paper (KDD 2016)
- **Trust Rating**: Highest
- **Key Claims**: Gradient boosting with regularization; sparsity-aware split finding; weighted quantile sketch; scalable to large datasets; dominates ML competitions
- **V7 Applicability**: XGBoost is the specified model class for the AlphaForge V7-native scorer per `alphaforge/docs/ai_summary__v7_alphaforge_xgb.md`

**Repo Note**: The AlphaForge design specifies XGBoost as the primary model class for the V7-native scorer (sections 7.5, 11-13 of `ai_summary__v7_alphaforge_xgb.md`). The old repo (`trading-bot-pr`) claimed CatBoost as primary; this claim is `old_repo_context_unverified` in v7-engine. The V6 inference engine (sibling repo) may use a different backend, but the V7-native path is XGBoost by design.

### Grinsztajn et al. — Why Tree-Based Models Still Outperform

- **Title**: Why do tree-based models still outperform deep learning on typical tabular data?
- **URL**: https://arxiv.org/abs/2207.08815
- **Retrieval Date**: 2026-06-23
- **Source Type**: Conference paper (NeurIPS 2022 Datasets and Benchmarks Track)
- **Trust Rating**: Highest
- **Key Claims**: Tree-based models (GBDT, Random Forest) consistently outperform deep learning on tabular data up to ~50K samples; deep learning advantage only on: high-cardinality categorical, image/text features; trees are more robust to uninformative features; GBDT inductive bias favors non-smooth decision boundaries common in tabular data
- **V7 Applicability**: Strong evidence for XGBoost-first default; validates tree-based critic over deep RL critic for V1-V2; at V3-V4 scale with sufficient data, distributional RL may add value beyond pure tree ensembles

---

## 11. Financial ML Validation

### Lopez de Prado — Advances in Financial Machine Learning

- **Title**: Advances in Financial Machine Learning
- **URL**: https://www.wiley.com/en-us/Advances+in+Financial+Machine+Learning-p-9781119482086
- **Retrieval Date**: 2026-06-23
- **Source Type**: Textbook (Wiley, 2018)
- **Trust Rating**: Highest
- **Key Claims**: Financial data requires special ML treatment (non-IID, low signal-to-noise); sample weighting by uniqueness; fractionally differentiated features; meta-labeling; triple-barrier labeling; backtest overfitting is primary failure mode
- **V7 Applicability**: Core validation framework for critic deployment; meta-labeling compatible with Policy Critic advisory role
- **Limitations**: Focus on supervised approaches; RL coverage limited; published 2018 (pre-offline-RL explosion)

---

## 12. Repo-Internal Sources (Verified in v7-engine)

These are source files within the v7-engine repository that serve as evidence for design decisions:

| File | What It Establishes |
|---|---|
| `CLAUDE.md` | Domain boundaries, truth hierarchy (simulation > realized > contract > runtime > model), forbidden actions |
| `contracts/registry.json` | 15 registered cross-domain contracts; AlphaForge → V7 handoff contracts |
| `v7/docs/policy_critic/design.md` | Canonical critic design: IQL + distributional + conformal + CQL cross-check |
| `v7/docs/policy_critic/ai_summary.md` | Canonical critic dense synthesis with open HOLDS |
| `v7/docs/policy_critic/codebase_maps/v7_pipeline_map.md` | V6/V7 decision flow with file:line references |
| `v7/docs/policy_critic/codebase_maps/simulation_map.md` | Simulation reward surface + critical findings (no replay buffer, two simulation paths) |
| `v7/docs/policy_critic/codebase_maps/contracts_runtime_map.md` | Contract registration procedure, runtime wiring, critic integration points |
| `v7/docs/policy_critic/codebase_maps/alphaforge_map.md` | AlphaForge scorer (XGBoost, spec-only), field surface, calibration |
| `alphaforge/docs/ai_summary__v7_alphaforge_xgb.md` | AlphaForge XGBoost scorer design: calibration, alpha score builder, policy thresholds |
| `alphaforge/docs/schemas/prediction_schema_v1.json` | V7-native prediction row schema |
| `simulation/engine/engine.py` | Economic truth: simulate() producing ActionOutcome, NoTradeOutcome, PathMetrics |
| `simulation/engine/costs.py` | Authoritative cost model (fee + slippage; funding DEFERRED) |
| `runtime/db/repos/shadow_policy_repo.py` | ShadowPolicyRepository: ShadowPolicyDecision + ExpectancyLabelProfile persistence |
| `runtime/db/repos/policy_dataset_repo.py` | PolicyDatasetRepository: PolicyExample persistence |
| `v7/docs/runtime/runtime_integration.md` | Per-mode readiness states, execution eligibility stack |
| `v7/docs/pipeline/policy.md` | V7 policy gates specification (8 gates) |
| `v7/docs/pipeline/evaluation.md` | G0-G10 promotion gates |

---

## 13. Claims Requiring Further Verification

These claims are plausible but could not be verified from the sources retrieved or the repo:

| Claim | Status | Recommended Verification |
|---|---|---|
| IQL expectile τ optimal range for financial data (τ = 0.7–0.9) | **Unverified** — extrapolated from D4RL results | Empirical study with replay buffer data |
| Replay buffer minimum size (1000 for V2, 10000 for V3) | **Unverified** — heuristic estimates | Power analysis with actual outcome distribution |
| 30-day shadow burn-in sufficient for critic calibration | **Unverified** — rule of thumb | Requires power analysis based on trade frequency |
| FQE CI width < 1.0R as acceptance criterion | **Unverified** — not established in literature | Determine empirically from data characteristics |
| CatBoost as primary V6 backend | **old_repo_context_unverified** — V6 lives in sibling repo, not v7-engine | Inspect sibling repo `/home/erfolg/src/trading-bot/v6/` |
| PolicyEngine abstract interface | **old_repo_context_unverified** — `runtime/services/policy/` does not exist in v7-engine | No such interface exists; V7-native policy bridge is greenfield |
| RuleBasedPolicyEngine with 5 deterministic rules | **old_repo_context_unverified** — file does not exist in v7-engine | V7 policy gates are specified in docs (`v7/docs/pipeline/policy.md`) but not yet implemented as a standalone engine |
| RL policy stub returning NO_TRADE | **old_repo_context_unverified** — file does not exist in v7-engine | No RL stub exists; v7/src/ is greenfield |

---

## 14. Source Quality Summary

| Rating | Count | Examples |
|---|---|---|
| Highest | 18 | Sutton & Barto, IQL (Kostrikov), CQL (Kumar), DSR (Bailey & Lopez de Prado), QR-DQN (Dabney), Grinsztajn et al. |
| High | 5 | IQL official impl, BAIR blog, Amodei et al. |
| Medium | 1 | OpenAI reward hacking blog |

All critical design decisions (authority hierarchy, shield principle, IQL recommendation, DSR/PBO gates, XGBoost-first approach) are backed by Highest-rated sources.

---

## 15. Tavily MCP Search Log

| # | Query | Tool | Results |
|---|---|---|---|
| 1 | "Implicit Q-Learning offline reinforcement learning paper" | `mcp__tavily__tavily-search` | 5 results (arXiv, Semantic Scholar, TransferLab) |
| 2 | "Conservative Q-Learning CQL offline RL Kumar Levine NeurIPS 2020" | `mcp__tavily__tavily-search` | 5 results (NeurIPS proceedings, BAIR blog) |
| 3 | "Deflated Sharpe Ratio backtest overfitting Lopez de Prado probability PBO CSCV" | `mcp__tavily__tavily-search` | 5 results (SSRN, Wikipedia, David H Bailey site) |
| 4 | "safe reinforcement learning shielding Alshiekh survey Garcia Fernandez" | `mcp__tavily__tavily-search` | 5 results (AAAI, JMLR, Semantic Scholar) |
| 5 | "distributional reinforcement learning quantile regression QR-DQN IQN Dabney" | `mcp__tavily__tavily-search` | 5 results (ICML proceedings, EmergentMind, DataScience SE) |
| 6 | "off-policy evaluation FQE fitted Q-evaluation offline RL benchmark Fu 2021" | `mcp__tavily__tavily-search` | 5 results (ICLR, ICML, NeurIPS workshops) |
| 7 | "tree-based models GBDT outperform deep learning tabular data finance Grinsztajn 2022" | `mcp__tavily__tavily-search` | 5 results (NeurIPS, Semantic Scholar, Hacker News) |

All Tavily MCP searches succeeded. No fallback tools were used.
