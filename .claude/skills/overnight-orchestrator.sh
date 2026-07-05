#!/bin/bash
# ============================================================
# V7 Engine — Overnight Issue Orchestrator
# ============================================================
# Runs GitHub issues in dependency order, worktree-isolated,
# headless Claude Code per issue. HOLD on failure, continue.
#
# Usage: bash .claude/skills/overnight-orchestrator.sh [milestone]
# ============================================================
set -euo pipefail

REPO="ddawnlll/v7-engine"
MILESTONE="${1:-v0.1 — Model Training + V7 Policy Gates}"
MAX_PARALLEL="${2:-3}"
REPORT_DIR="reports/overnight/$(date +%Y-%m-%d_%H%M)"
mkdir -p "$REPORT_DIR"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$REPORT_DIR/orchestrator.log"; }
hold_issue() { gh issue edit "$1" --repo "$REPO" --add-label "HOLD" --remove-label "dep:blocks" 2>/dev/null; }

# === Phase 0: Fetch and classify issues ===
log "Phase 0: Fetching issues for milestone: $MILESTONE"

ISSUES=$(gh issue list --repo "$REPO" --milestone "$MILESTONE" --limit 50 --state open \
  --json number,title,labels --jq '
    .[] | {
      number: .number,
      title: .title,
      p0: ([.labels[].name] | index("priority:p0") != null),
      hard_gate: ([.labels[].name] | index("hard-gate") != null),
      blocked: ([.labels[].name] | index("dep:blocked-by") != null),
      blocks: ([.labels[].name] | index("dep:blocks") != null),
      hold: ([.labels[].name] | index("HOLD") != null),
      domain: ([.labels[].name | select(startswith("domain:"))][0] // "unknown")
    }')

# Classify: READY (no deps, no HOLD) vs BLOCKED vs HOLD
READY=$(echo "$ISSUES" | jq -c 'select(.blocked == false and .hold == false)')
BLOCKED=$(echo "$ISSUES" | jq -c 'select(.blocked == true and .hold == false)')

log "READY: $(echo "$READY" | jq -s 'length') issues"
log "BLOCKED: $(echo "$BLOCKED" | jq -s 'length') issues"

# === Phase 1: Process READY issues in parallel batches ===
process_issue() {
  local num=$1 title=$2 domain=$3
  local worktree=".claude/worktrees/issue-${num}"
  local branch="agent/issue-${num}"

  log "  Starting #${num}: ${title} [${domain}]"

  # Create worktree + branch
  git worktree add -b "$branch" "$worktree" HEAD 2>&1 | tail -1
  cd "$worktree" || return 1

  # Build the agent prompt
  cat > /tmp/agent-prompt-${num}.txt << 'PROMPT_EOF'
You are working on a GitHub issue for the v7-engine project.

ISSUE: ${title} (#${num})
DOMAIN: ${domain}
REPO: /home/erfolg/src/v7-engine

RULES:
1. Read the issue body at https://github.com/ddawnlll/v7-engine/issues/${num} for details
2. Follow the task completion protocol from CLAUDE.md:
   - Plan first (architect-reviewer)
   - Implement minimal patch
   - Add or update tests
   - Run relevant checks (make check-contracts, make check-boundaries, make test-all)
   - Write ACCP-YAML report to reports/accp/
   - Update roadmap if scope changed
3. NEVER do live trading, real API calls, or model training outside TR-05
4. If you cannot complete the task, explain why and mark as HOLD
5. Work ONLY in your domain boundary — do not cross into other domains

DOMAIN BOUNDARY: ${domain}
- lib/ = shared primitives
- simulation/ = economic truth
- alphaforge/ = alpha discovery
- v7/ = policy acceptance
- runtime/ = execution eligibility
- interface/ = React UI

OUTPUT: ACCP-YAML report in reports/accp/issue-${num}.yaml
PROMPT_EOF

  # Run headless Claude Code
  local start_time=$(date +%s)
  local exit_code=0

  timeout 1800 claude -p "$(cat /tmp/agent-prompt-${num}.txt)" \
    --allowedTools "Read,Write,Edit,Bash(gh issue view ${num} --repo ddawnlll/v7-engine),Bash(make *),Bash(python*),Bash(pytest*),Bash(git *),Bash(gh pr *),Bash(gh issue edit ${num}*),Bash(find *),Bash(ls *)" \
    2>&1 | tee "$REPORT_DIR/issue-${num}.log" || exit_code=$?

  local elapsed=$(($(date +%s) - start_time))

  # Run targeted tests
  if [ -d "tests" ] || [ -d "${domain}/tests" ]; then
    log "    Running tests for #${num}..."
    PYTHONPATH=. python3 -m pytest "${domain}/tests/" -q --tb=short 2>&1 | tail -5 | tee -a "$REPORT_DIR/issue-${num}.log" || true
  fi

  # Check for ACCP report
  if [ -f "reports/accp/issue-${num}.yaml" ]; then
    log "    ✓ ACCP report generated for #${num}"
    gh issue edit "$num" --repo "$REPO" --add-label "accp:done" 2>/dev/null || true
  fi

  # Commit if changes exist
  if ! git diff --quiet HEAD 2>/dev/null; then
    git add -A
    git commit -m "feat: #${num} ${title}

Co-Authored-By: Claude <noreply@anthropic.com>" 2>&1 | tail -1
    log "    ✓ Committed #${num}"
  fi

  # Return to repo root and clean up
  cd /home/erfolg/src/v7-engine
  git worktree remove "$worktree" --force 2>/dev/null || true
  git branch -D "$branch" 2>/dev/null || true

  if [ $exit_code -eq 0 ]; then
    log "  ✓ DONE #${num} (${elapsed}s)"
    return 0
  else
    log "  ✗ FAILED #${num} (${elapsed}s) — marking HOLD"
    hold_issue "$num"
    return 1
  fi
}

# === Main loop ===
log "Phase 1: Processing READY issues (max $MAX_PARALLEL parallel)"
cd /home/erfolg/src/v7-engine

# Process in batches
BATCH=0
echo "$READY" | jq -c '.' | while IFS= read -r issue; do
  num=$(echo "$issue" | jq -r '.number')
  title=$(echo "$issue" | jq -r '.title')
  domain=$(echo "$issue" | jq -r '.domain')

  # Run in background with concurrency limit
  while [ "$(jobs -r | wc -l)" -ge "$MAX_PARALLEL" ]; do
    sleep 10
  done

  process_issue "$num" "$title" "$domain" &
  BATCH=$((BATCH + 1))
done

# Wait for all background jobs
wait
log "Phase 1 complete"

# === Summary ===
log "========================================"
log "OVERNIGHT RUN COMPLETE"
log "Report: $REPORT_DIR"
log "Issues processed: $(ls "$REPORT_DIR"/issue-*.log 2>/dev/null | wc -l)"
log "========================================"
