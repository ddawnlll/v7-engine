# OPERATION SCALP 0.05 — 8-Hour Overnight Campaign (Unattended, Never Idle)

## Supersedes / resumes
This supersedes `overnight-alpha-validation-task.md`. FIRST ACTION: read
`reports/overnight/ledger.jsonl` and `reports/overnight/*.md` if they exist —
any phase already completed there is DONE; skip it and credit its results.
Never redo finished work; never idle. If a phase blocks or crashes twice,
write a SKIPPED ledger row with the traceback and advance to the next item.

## Mission

One night. Two questions answered with simulation-engine truth:
1. **What is the TRUE per-trade expectancy of the 57-symbol SCALP alpha?**
2. **Which stack of levers pushes the honest selective book toward
   ≥ 0.05 net R/trade — and what does each lever cost in trade count?**

The owner's target is 0.05 net sim-space R/trade. That target applies to the
**frontier**, not to any single manufactured number: a valid claim of X R/trade
requires ≥ 500 OOS trades, positive in ≥ 4 of 6 folds, and top-2 symbols < 40%
of PnL. 0.05 on 80 cherry-picked trades is noise and will be called out as such.

## Iron rules (violating any invalidates the night)

1. **Holdout**: most recent 3 months reserved from the first command. Trained on
   never, tuned on never. Touched EXACTLY ONCE in Phase G with a frozen,
   committed config. No second attempt regardless of outcome.
2. **Simulation space only** for every cited expectancy number. Label-space
   numbers appear only annotated "(label-space)".
3. **`simulation/` domain**: ADDITIVE changes only, and only in Phase E — a new
   maker-execution profile behind config, taker remains default, existing tests
   untouched and passing. Never edit existing cost constants. `v7/` policy code:
   read-only. `contracts/`: read-only.
4. **Fixed grids only** — every sweep grid is written in this file. Do not extend
   grids. No Optuna. No unbounded searches.
5. **Ledger**: append-only `reports/overnight/ledger.jsonl` — one row per
   experiment {id, phase, config, sim_metrics, n_trades, duration_s, verdict}.
   Commit after every phase (`exp:`/`feat:`/`fix:` + phase ID). Push if remote configured.
6. **Crash policy**: two identical failures → SKIPPED row, move on. Max 20 min
   debugging any single failure.
7. **Time budgets** below. Overrun 50% → write partial results, advance. If behind
   schedule, drop stretch items (marked ⭐) — never drop Phase G or H.

## Phase queue (8 hours)

### Phase A (1.0h) — TRUE BASELINE: 57-symbol simulation scoreboard [V6]
1. Data pre-flight: per-symbol bars/date-range table; n_samples sanity (V1 loader);
   abort criteria: rank > 5 min, any fold > 15 min.
2. Full SCALP run, 6 folds, holdout excluded: WFV → discovery → simulation
   backtest → profitability. Then SWING (control).
3. Artifact `reports/overnight/scoreboard.md`: label vs sim space (total R,
   R/trade, trades, WR, PF, DD), cost decomposition (fee/slippage/funding),
   exit breakdown, per-symbol concentration.
4. **DECISION NODE A**: sim R/trade > 0 → continue. ≤ 0 → run gap decomposition
   (which cost bucket kills it; break-even at 2/4/6/8 bps round-trip) BEFORE
   continuing — Phase E's maker profile may be the rescue; the decomposition
   tells you exactly how much it must save.

### Phase B (0.5h) — RANKING POWER: selectivity frontier [V8]
1. Confidence-decile table from Phase A OOS predictions (sim space, per mode).
2. Threshold frontier via existing NESTED per-fold machinery (grid: 0.50, 0.55,
   0.60, 0.65, 0.70, 0.75): threshold → (n_trades, R/trade, total R).
3. **DECISION NODE B**: top decile ≤ overall average → RANKING=NONE → skip
   Phase C (meta multiplies ranking power; zero × anything = zero), reallocate
   its time to Phase D+E.

### Phase C (1.5h) — META-LABELING on real data [V9]
1. Wire `alphaforge/src/alphaforge/meta/` into OOS path. Fold k meta-model
   trains ONLY on folds < k outcomes. Unit test the fold boundary.
2. Veto-threshold grid (fixed): 0.50, 0.55, 0.60, 0.65, 0.70.
3. A/B sim-space table: base vs veto — R/trade, total R, n_trades, PF, DD.
   Accept-region: R/trade up AND total-R loss < 50%. Report the frontier
   regardless of acceptance.

### Phase D (1.5h) — NEW EDGE: time features + lead-lag activation [S3, S2]
1. **S3 time features** (~1h of work, do first): add `hour_of_day` (sin/cos pair),
   `day_of_week` (sin/cos), `is_us_hours` to the feature pipeline (causal,
   trivially so). Bump PIPELINE_VERSION (invalidates feature cache — expected).
   Re-run Phase A SCALP config → delta row in ledger. Evidence basis: documented
   intraday seasonality in BTC (SSRN 4081000).
2. **S2 lead-lag**: wire the existing `features/lead_lag.py` (DEFERRED — its
   cross-sectional data dependency is satisfied by the 57-symbol panel) into the
   V3 two-phase cross-sectional path. Feature-flag, default OFF. One A/B run
   flag-ON. Evidence basis: BTC→altcoin lagged price transmission, strongest in
   low-liquidity small caps (Springer 2026) — the 57-symbol tail is exactly that.
   Scope-bound: wiring + one A/B. No new lead-lag research.

### Phase E (1.5h) — THE ARITHMETIC LEVER: maker execution profile [S1]
Rationale: 4bps round-trip saving ÷ ~1% stop distance ≈ +0.03–0.04 R on EVERY
trade — the single largest lever toward 0.05. But it is only real if fill risk
is modeled honestly.
1. ADD (additive-only, Iron Rule 3) a maker execution profile to the simulation
   config: maker fee from authority constants, entry via post-only limit at
   signal-bar close with a **fill-probability model** — fill iff the next bar's
   range crosses the limit price by a conservative margin. Grid of fill
   assumptions (fixed): {pessimistic: bar must trade THROUGH price by 0.05%,
   base: touch + 1 tick, optimistic: touch}. Unfilled signal = missed trade
   (logged, not free).
2. A/B sim-space: taker (default) vs maker under all three fill assumptions —
   R/trade, n_trades (fill rate!), total R. The claim "maker adds +X R/trade"
   must cite the PESSIMISTIC row.
3. Adverse-selection check: compare win rate of filled vs missed maker trades.
   If filled trades are systematically worse (adverse selection), report it —
   that is the honest cost of maker execution.
4. All existing simulation tests must still pass; taker remains the default profile.

### Phase F (1.0h) — STACK & STRETCH ⭐ [S4, S5]
1. **Best-stack run**: combine the winning settings so far (selectivity threshold
   + meta veto if accepted + time features + lead-lag if positive + maker-base
   fill) → ONE run → the "candidate config". This is the number that goes on
   the frontier chart against 0.05.
2. ⭐ S4 funding-window timing: veto SHORT entries in the 2 bars before a
   negative-funding settlement and LONG entries before positive (deterministic
   carry). One A/B.
3. ⭐ S5 ensemble consensus: wire existing `training/ensemble.py`
   (agreement_threshold grid fixed: 0.6, 0.8) as an additional veto. One A/B.

### Phase G (0.5h) — THE HOLDOUT, exactly once [V7]
1. Freeze the candidate config from Phase F.1. Commit it FIRST
   (`feat(V7): frozen candidate config for holdout`).
2. Train on all pre-holdout data; evaluate ONCE on the 3-month holdout through
   the full simulation path. Report verbatim, good or bad. NO retry, NO tweak.
3. Overfit battery: overfit_gap, train-OOS corr, inter-fold consistency, PBO
   note, and an honest multiple-testing statement (count tonight's experiments
   from the ledger — that number IS the MHT exposure).

### Phase H (0.5h, MANDATORY) — MORNING REPORT
`reports/overnight/MORNING_REPORT.md`:
1. Top: one paragraph — the true base R, the best honest stack R, the holdout
   verdict, distance to 0.05, go/no-go recommendation.
2. **The frontier chart** (table): config stack → (R/trade, n_trades, total R,
   folds positive, concentration) — every row ≥ 500 trades or marked
   "INSUFFICIENT-N". Mark which rows clear 0.05 honestly, if any.
3. All phase tables, SKIPPED ledger, ranked top-5 next actions with expected value.
4. ACCP report `reports/accp/operation_scalp_005.yaml`; roadmap + alphaforge
   ai_summary updates; alpha_registry updated with sim-space numbers ONLY;
   final commit + push; worktree sync per CLAUDE.md.

## Research protocol (internet + arXiv, bounded)

Research is a TOOL for unblocking phases, run IN PARALLEL with long training/
backtest runs — never as a substitute for running experiments.

1. **When to search**: (a) a phase hits a design decision this file doesn't
   settle (e.g. exact fill-probability modeling for post-only orders, funding
   settlement timing conventions, purge/embargo sizing for a new label horizon);
   (b) a result is SURPRISING (edge vanishes, metric flips sign) and you need to
   know if it's a known phenomenon before burning debug time; (c) a lever
   underperforms expectations and literature may explain the gap.
2. **While a long run executes** (57-symbol WFV, backtest), use the wall-clock:
   pre-research the NEXT phase's open questions instead of waiting idle.
3. **Source order** (per repo routing policy): parallel-search / DuckDuckGo →
   arXiv for academic claims → exa if needed. Tavily forbidden. Prefer primary
   sources: arXiv/SSRN papers, exchange docs (Binance fee/funding specs),
   official library docs. SEO blogs are secondary signal only.
4. **Budget**: ≤ 15 min per research question, ≤ 5 questions per phase. Research
   NEVER extends a grid or adds an unplanned experiment — findings that suggest
   new work go into the morning report's next-actions list, not into tonight's queue.
5. **Ledger**: every research question gets a row {id, phase, question, answer
   summary, sources[], action_taken}. Findings cited in the morning report link
   their sources.
6. Known starting points already vetted: BTC→altcoin lead-lag (Springer
   s10690-026-09589-z), intraday BTC seasonality (SSRN 4081000), OFI feature
   stability (arXiv 2602.00776), meta-labeling methodology (López de Prado /
   SSRN evaluations), perp funding mechanics (arXiv 2212.06888). Do not re-search
   these; fetch the full text only if a phase needs implementation detail.

## Anti-drift (the 4am list)
- The 0.05 target NEVER justifies: extending a grid, re-running the holdout,
  shrinking the trade-count floor, quoting the optimistic fill row, or quoting
  label-space numbers. A true 0.03 beats a fake 0.06 — the fake one costs real
  money later.
- No refactors beyond what a phase explicitly names. No new modes. No edits to
  existing cost constants. No force-push. Append-only reports.
- If data itself is broken: loader fix ≤ 30 min allowed, else descope to the
  largest clean subset (≥ 20 symbols) and flag prominently in the report.
- Morning report RECOMMENDS; G0-G10 gates and the owner decide promotion.

## Success definition
By morning the owner knows: the true base R; the full lever frontier with
honest trade counts; whether maker execution survives pessimistic fill
assumptions; whether lead-lag and time features add real edge; what the holdout
says; and the exact ranked path to close any remaining gap to 0.05.
"The stack reaches 0.038 honestly, here is the gap decomposition and the two
levers left" is a SUCCESSFUL night. A fabricated 0.05 is the only failure mode.

---

## ADDENDUM — Pre-Authorization & Non-Stall Policy

## Why this exists
The 2026-07-07 run stalled silently in Phase A when the agent hit an action
requiring permission approval, with no owner awake to grant it. No traceback,
no SKIPPED row — just a frozen process for the rest of the night. This
directly violates the "unattended, never idle" mission. This addendum fixes
that class of failure.

## Iron Rule 0 — Pre-authorized action scope (read before starting)
The owner pre-authorizes, for the full 8-hour window, WITHOUT further prompts:
- Reading any file under `reports/`, `simulation/`, `alphaforge/`, `v7/`, `contracts/`.
- Writing/appending to `reports/overnight/*` and `reports/accp/*`.
- Writing new files under `simulation/` ONLY if additive (new file, not edit
  to an existing one) — per Iron Rule 3.
- Running existing test suites (`pytest`, etc.) read-only against the repo.
- Git: `add`, `commit` with the required prefixes, and `push` to the existing
  configured remote (no new remotes, no force-push).
- Installing/using already-vetted research sources per the Research protocol
  section (web/arXiv search, fetching cited papers).

Explicitly NOT pre-authorized (must stay blocked, no exception):
- Any edit to `v7/` or `contracts/` (read-only, per Iron Rule 3).
- Any edit to existing `simulation/` cost constants.
- Force-push, new remotes, credential/secret access, deleting any file.
- Anything touching the live/production trading path (this campaign is
  simulation-only; if any action would touch real order execution, STOP and
  write a BLOCKED row — never proceed).

## Iron Rule 0b — BLOCKED is a first-class ledger state
Add `BLOCKED` alongside `ERROR`/`SKIPPED`/`CRASHED` as a valid verdict.
If the agent hits an action that:
(a) is genuinely outside the pre-authorized scope above, or
(b) is ambiguous enough that proceeding without a human would be reckless,

then it must NOT sit idle waiting for a response. Instead:
1. Write a ledger row immediately: `{id, phase, verdict: "BLOCKED",
   blocked_action: "<exact command/edit that needs approval>",
   reason: "<why it's outside pre-authorized scope>", timestamp}`.
2. Treat this exactly like the existing crash policy: do NOT retry the same
   blocked action a second time this session. Move to the next phase or
   sub-step that does not depend on the blocked result.
3. If a later phase strictly depends on the blocked output (e.g. Phase E
   needs Phase A's completed backtest), skip forward to the next
   *independent* phase instead (e.g. pre-research for Phase D, or dry-run
   config validation for Phase C) rather than idling.
4. List every BLOCKED row prominently at the TOP of the morning report,
   with the exact action needed, so the owner can grant it in 30 seconds
   and resume — instead of discovering at 8am that nothing ran.

## Resume checklist (do this before restarting tonight)
1. Confirm `overnight-scalp-005.md` (this file, with the addendum) exists at
   a fixed path the agent will actually read — last run's audit could not
   find the spec file in the repo at all. Commit it if it isn't tracked yet.
2. Confirm the ledger's one ERROR row is understood as "Phase A incomplete,
   not started fresh" — the agent should re-attempt Phase A, not skip it.
3. Resolve the symbol-count (20 vs 56) and threshold (0.45/0.48/0.50)
   discrepancies BEFORE restart — pick one canonical symbol list and one
   canonical threshold, hard-code them in exactly one place, and reference
   that one place from ledger logging so future audits don't see 3 numbers
   for 1 run.
4. Consider descoping Phase A's first attempt to a smaller symbol subset
   (10-12 liquid symbols) to rule out the OOM/heterogeneous-length-array
   hypothesis before committing to the full 56/57-symbol run.
