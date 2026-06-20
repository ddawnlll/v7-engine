# AlphaForge Decision Log

**Purpose:** Canonical record of locked AlphaForge decisions. Each decision is authoritative unless explicitly overridden by a newer decision.

**Authority:** LOCKED. Change requires evidence of contradiction or explicit owner review.

---

## Locked Decisions

### DEC-AF-001 — Authority Boundary

**Decision:** AlphaForge is the anomaly discovery and alpha research authority. It does NOT own trade execution, final policy, runtime lifecycle, or exchange connectivity.

**Rationale:** Authority separation (PRINCIPLE-001). AlphaForge discovers; V7 decides; Simulation measures truth.

**Locked:** P0.8B

**See:** [discovery_authority.md](discovery_authority.md)

---

### DEC-AF-002 — Mode Priority: SCALP and AGGRESSIVE_SCALP Primary

**Decision:** SCALP and AGGRESSIVE_SCALP are the PRIMARY business and research modes.

**Rationale:** These modes represent the highest expected value per the profitability thesis. All research prioritization flows from this.

**Locked:** P0.7E

**See:** [../v7/docs/v7_mode_centric_architecture.md](../../v7/docs/v7_mode_centric_architecture.md)

---

### DEC-AF-003 — Mode Priority: SWING Secondary Baseline

**Decision:** SWING is a SECONDARY_BASELINE/control mode. Its thresholds are LOCKED_INITIAL_BASELINE. It does NOT override primary mode priority.

**Rationale:** SWING provides a safer, lower-frequency baseline for architectural validation. It is NOT the primary product.

**Locked:** P0.7E

**See:** [../v7/docs/v7_mode_centric_architecture.md](../../v7/docs/v7_mode_centric_architecture.md)

---

### DEC-AF-004 — AlphaForge Outputs Evidence, Not Trade Commands

**Decision:** AlphaForge outputs research reports and handoff packages. It does NOT issue trade commands, position directives, or execution orders.

**Rationale:** V7 owns final trade decisions (PRINCIPLE-001). AlphaForge evidence informs V7; it does not command V7.

**Locked:** P0.8B

**See:** [report_contracts.md](report_contracts.md), [handoff_to_v7.md](handoff_to_v7.md)

---

### DEC-AF-005 — SimulationOutput is Economic Truth

**Decision:** SimulationOutput is the authoritative economic truth source for AlphaForge labels. AlphaForge does NOT create labels from raw price data.

**Rationale:** Simulation owns economic truth. AlphaForge must consume authoritative outcomes, not invent its own.

**Locked:** P0.7A

**See:** [label_contract.md](label_contract.md), [../simulation/docs/](../../simulation/docs/)

---

### DEC-AF-006 — V7 Remains Final Authority

**Decision:** V7 is the final acceptance and policy authority. V7 can REJECT any AlphaForge handoff package regardless of AlphaForge's recommendation.

**Rationale:** Authority separation (PRINCIPLE-001). AlphaForge recommends; V7 decides.

**Locked:** P0.8B

**See:** [handoff_to_v7.md](handoff_to_v7.md)

---

### DEC-AF-007 — All Three Modes Require Report Contracts

**Decision:** SCALP, AGGRESSIVE_SCALP, and SWING each require ModeResearchReport contracts. No mode is exempt from the report requirement.

**Rationale:** Even baseline/control modes must produce evidence. SWING reports are secondary_baseline_report type, not primary_research_report.

**Locked:** P0.8B

**See:** [report_contracts.md](report_contracts.md)

---

### DEC-AF-008 — Large Data and Models NOT in Repo

**Decision:** Raw data, normalized datasets, feature matrices, label datasets, and model binaries are stored outside the git repository. Only schemas, fixtures, manifests, configs, and reports are stored in repo.

**Rationale:** PRINCIPLE-007. Keeps repo cloneable; enables proper data/model storage solutions.

**Locked:** P0.8B

**See:** [storage_policy.md](storage_policy.md)

---

### DEC-AF-009 — NO_TRADE Comparison Mandatory

**Decision:** Every alpha report must include NO_TRADE as a first-class comparator. An alpha that cannot beat doing nothing is automatically rejected.

**Rationale:** PRINCIPLE-009. NO_TRADE is the null hypothesis that every alpha must overcome.

**Locked:** P0.8B

**See:** [report_contracts.md](report_contracts.md), [validation_contract.md](validation_contract.md)

---

### DEC-AF-010 — Funding DEFERRED Blocks Perpetual/Live Claims

**Decision:** The funding cost model is DEFERRED. Any alpha thesis that requires perpetual/live trading must carry this limitation. Funding-aware labels are blocked until the funding model is implemented.

**Rationale:** Funding costs are non-trivial for perpetual futures. Claiming live readiness without funding is misleading.

**Locked:** P0.7A (Simulation MVP)

**See:** [label_contract.md](label_contract.md), [../simulation/docs/cost_model.md](../../simulation/docs/cost_model.md)

---

## Decision Change Policy

1. A LOCKED decision may only be changed if:
   - New empirical evidence directly contradicts it, OR
   - An owner review explicitly authorizes the change.
2. A changed decision must be re-logged with a new revision entry.
3. The old decision is marked SUPERSEDED, not deleted.
4. All dependent docs must be updated.

---

## Related Docs

- [ai_summary.md](ai_summary.md)
- [discovery_authority.md](discovery_authority.md)
- [phase_plan.md](phase_plan.md)
- [../../v7/docs/roadmap.md](../../v7/docs/roadmap.md)

## Forbidden Assumptions

- LOCKED does not mean immutable — it means "requires evidence to change."
- Decisions are not preferences — they are binding constraints on implementation.

## Open Holds

- DEC-AF-002/003 depend on P0.7E mode priority alignment (PASS).
- DEC-AF-010 depends on future funding model implementation.
