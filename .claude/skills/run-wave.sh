#!/bin/bash
# ============================================================
# V7 Engine — Wave Runner
# Usage: bash .claude/skills/run-wave.sh <wave_number>
# ============================================================
set -euo pipefail

WAVE="${1:-1}"
LOG_DIR="reports/overnight/$(date +%Y-%m-%d_%H%M)"
mkdir -p "$LOG_DIR"

echo "=== V7 Engine Wave $WAVE Runner ==="
echo "Log: $LOG_DIR"
echo "Started: $(date)"
echo ""

case "$WAVE" in
  1)
    echo "Wave 1: UNBLOCK — 8 parallel independent issues"
    echo "  #32 Funding cost model"
    echo "  #63 Lifecycle contracts"
    echo "  #51 Dockerfile"
    echo "  #61 Runtime tests"
    echo "  #49 Centralized logging"
    echo "  #55 Secret audit"
    echo "  #13 Data backfill"
    echo "  #4  TR-00 Reality baseline"
    echo ""
    echo "Launch with: claude --worktree 'Wave 1: solve unblock issues...' "
    echo "Or use the Workflow tool from within Claude Code."
    ;;

  2)
    echo "Wave 2: TR CHAIN + RESEARCH"
    echo "Sequential: TR-00→01→02→03→04→05→06→07→08"
    echo "Parallel: #76 IQL tau + #77 Conformal + #54 Exception audit + #73 TODO_V4"
    echo ""
    echo "TR chain must run sequentially. Research can run parallel."
    echo "After TR-07: #37 Policy Critic RL + #38 CI green run"
    ;;

  3)
    echo "Wave 3: EVIDENCE — walk-forward + threshold locking"
    echo "Sequential: #75(WF protocol) + #32(funding) → #35(profitability)"
    echo "Parallel: #14(Feature tuning), #15(Lead-lag), #40(Regime), #41(Ablation)"
    echo "After #35: #44(SCALP lock) + #36(AGGRESSIVE_SCALP lock)"
    ;;

  4)
    echo "Wave 4: RUNTIME WIRING"
    echo "Sequential: #31→33→34→88→39→85→46→84→86"
    echo "Parallel: #81(Field mapping), #42(Promotion gates)"
    ;;

  5)
    echo "Wave 5: SAFETY + TESTS"
    echo "Parallel safety: #21 #22 #23 #24 #25 #83"
    echo "Parallel tests: #57 #58 #59 #64 #65"
    echo "UI chain: #48→80→82→74"
    ;;

  6)
    echo "Wave 6: OPS + DOCS"
    echo "Parallel ops: #50 #52 #53 #54 #56 #60 #62"
    echo "Parallel docs: #66 #67 #68 #69 #71 #72 #73"
    ;;

  *)
    echo "Unknown wave: $WAVE"
    echo "Usage: bash .claude/skills/run-wave.sh [1-6]"
    exit 1
    ;;
esac

echo ""
echo "=== Ready to launch ==="
echo "Run in tmux: tmux new-session -d -s v7-wave$WAVE 'bash .claude/skills/run-wave.sh $WAVE'"
