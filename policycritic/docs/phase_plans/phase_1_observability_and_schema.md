# Phase 1 — Observability and Schema

> Status: NOT STARTED
> Prerequisite: Phase 0 complete (docs approved)
> Duration: 2-3 days estimated

## Goal

Define the PolicyCriticReview contract, register it in `contracts/registry.json`, and establish the audit trail schema. Zero runtime behavior change. This phase creates the typed contract that all subsequent phases populate.

## Entry Criteria

- [ ] Phase 0 exit criteria met (docs package approved)
- [ ] Design lock confirmed on advisory architecture
- [ ] PolicyCriticReview fields agreed (verdict enum, confidence_adjustment, is_advisory)

## Deliverables

1. **`contracts/schemas/policy_critic_review.schema.json`** — JSON Schema following existing contract patterns. Required fields: `schema_version`, `review_id`, `decision_event_id`, `verdict` (ALLOW | DOWNWEIGHT_CONFIDENCE | VETO_TO_NO_TRADE | REQUIRE_REVIEW), `confidence_adjustment_factor`, `rationale`, `review_tags`, `critic_artifact_version`, `is_advisory` (always true).

2. **`contracts/registry.json` entry** — Append PolicyCriticReview to the registry: `owner_domain: v7`, `version: 1.0.0`, `producers: [v7]`, `consumers: [v7, runtime]`.

3. **`contracts/compatibility.json` entry** — Add PolicyCriticReview ↔ DecisionEvent compatibility pair.

4. **`contracts/mappings/policy_critic_to_decision_event.json`** — Map critic verdict → runtime_interpretation fields (suppression_reason, should_surface_to_review, etc.).

5. **`contracts/fixtures/policy_critic_review_minimal.json`** — Minimal valid fixture for schema parity testing.

6. **Integration test** (optional for this phase) — Schema parity test + fixture roundtrip.

## Exit Criteria

- [ ] PolicyCriticReview schema validates against JSON Schema metaschema
- [ ] Fixture roundtrip test passes
- [ ] Registry entry consistent with existing entries
- [ ] Compatibility entry defines breaking-change rules
- [ ] Contract reviewed by at least one reviewer
- [ ] No Python implementation (typed dataclass deferred to Phase 4)

## Files Involved

**Created**: `contracts/schemas/policy_critic_review.schema.json`, `contracts/fixtures/policy_critic_review_minimal.json`, `contracts/mappings/policy_critic_to_decision_event.json`
**Modified**: `contracts/registry.json` (append only), `contracts/compatibility.json` (append only)

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Verdict enum too narrow | Low | Requires schema version bump | Include REQUIRE_REVIEW for edge cases |
| Registry conflict with existing contracts | Low | CI failure | Follow existing naming conventions |

## What Must NOT Be Implemented in This Phase

- ❌ Any Python dataclass (deferred to Phase 4)
- ❌ Any runtime service that reads/writes PolicyCriticReview
- ❌ Any shadow recording logic
- ❌ Any database migration

## Rollback Plan

Remove the appended registry/compatibility entries. Delete new schema/fixture/mapping files. Revert commit.
