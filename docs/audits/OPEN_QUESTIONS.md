# V7 Engine — Open Questions

> **Status:** ACTIVE
> **Purpose:** Unverified suspicions, unresolved issues, and investigations that need worker attention.
> When a question is resolved, move the finding to `FINDINGS_LEDGER.md` and link it here as `RESOLVED → F-NNN`.
>
> **Format:** Each entry has an ID (Q-NNN), confidence, hypothesis, and suggested investigation.

---

## Q-001 — Is JPEG/Image Decode the Primary Bottleneck in Preprocessing?

**Confidence:** HYPOTHESIS
**Scope:** `alphaforge/data/preprocessing.py`
**Suggested investigation:**
- Profile decode stage vs transform stage independently (F-009 showed 68% overhead but did not break down by stage)
- Compare `cv2.imread` / `PIL.Image.open` timing against transform-only timing
- Check if data is stored as images or directly as arrays

**Background:** F-009 identified 68% pre-training overhead as single-core CPU bound, but the breakdown between decode, parsing, transforms, batching, and H2D transfer is unknown.

---

## Q-002 — Which Transforms Are Suitable for torch/CUDA?

**Confidence:** HYPOTHESIS
**Scope:** Feature transforms in training pipeline
**Suggested investigation:**
- List all transforms applied in preprocessing
- For each: is it vectorizable? Does it need CPU-only logic?
- Prototype a CUDA-enabled transform pipeline on one symbol
- Compare end-to-end timing

**Background:** DEC-006 says to identify CUDA-suitable transforms but no inventory exists yet.

---

## Q-003 — Should Delisted Symbols (MATIC) Be Excluded from Training?

**Confidence:** STRONG INFERENCE
**Scope:** Training dataset assembly
**Suggested investigation:**
- MATICUSDT has 50.33% NaN in cache panels (F-004)
- Check if MATIC predictions are used in live trading or only in backtesting
- Recommend exclusion or masking in training config

---

## Q-004 — Is the AlphaForge Training Pipeline Verified to NOT Use Outcome Columns as Features?

**Confidence:** HYPOTHESIS
**Scope:** `alphaforge/` training code
**Suggested investigation:**
- F-006 confirms outcome columns are stored as labels, but training code audit is pending
- Search for `net_R`, `gross_R`, `mfe_R`, `mae_R` usage in feature engineering code
- Verify train/test split doesn't leak simulation outcomes into feature matrix

---

## Q-005 — Does the BTC Gap Affect Current Training Windows?

**Confidence:** STRONG INFERENCE
**Scope:** Training data pipeline
**Suggested investigation:**
- BTC data gap is 2024-01-02 to 2024-03-01 (F-003)
- Check which training splits/windows span this period
- If no current training run uses Q1 2024 data, document as acceptable gap
- If runs use that period, backfill or exclude BTC from those runs

---

## Q-006 — What Is the Optimal DataLoader Worker Count for Preprocessing?

**Confidence:** HYPOTHESIS
**Scope:** Training pipeline configuration
**Suggested investigation:**
- Test multiprocessing with `num_workers=0, 2, 4, 8, 16`
- Profile CPU, memory, and GPU utilization at each setting
- Compare end-to-end training time

**Background:** DEC-006 recommends DataLoader workers as first optimization step.

---

## Q-007 — Does AGGRESSIVE_SCALP Need Its Own Profile or Can It Share SCALP Parameters?

**Confidence:** HYPOTHESIS
**Scope:** Simulation profiles
**Suggested investigation:**
- Compare required behavior differences between SCALP and AGGRESSIVE_SCALP
- Assess if AGGRESSIVE_SCALP is just tighter stops + larger size, or fundamentally different semantics
- Document minimum viable profile delta

---

## Q-008 — Are There Lookahead Risks in the Cache Factor Panel Generation Code?

**Confidence:** UNKNOWN
**Scope:** Cache factor pipeline (`cache/factor_sprint/`)
**Suggested investigation:**
- Code audit of factor computation for causal correctness
- Check that no future data leaks into factor values at time T
- Verify rolling windows are computed with shift()

---

## Q-009 — What Is the Policy Critic Integration Surface Area?

**Confidence:** HYPOTHESIS
**Scope:** `policycritic/` → `v7/` integration
**Suggested investigation:**
- Map the API boundary between Policy Critic recommendations and V7 decision-making
- Assess data flow: what signals does the critic consume? What does it produce?
- Identify pre-requisite gates before integration can begin

---

## Q-010 — Is There a Standard for Profiling Data Format?

**Confidence:** HYPOTHESIS
**Scope:** `reports/`, `scripts/`
**Suggested investigation:**
- F-015 identified inconsistent profiling JSON schemas
- Propose a standard schema for pipeline timing data
- Update profiling scripts to emit standard format
- Enable automatic comparison across runs

---

## Recently Resolved

| Q-ID | Resolution | Date | Moved To |
|------|-----------|------|----------|
| — | — | — | — |
