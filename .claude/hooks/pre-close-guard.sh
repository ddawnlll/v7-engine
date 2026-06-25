#!/bin/bash
# Pre-close hook: Block issue closure without commit evidence
# Triggered when agent tries: gh issue close <num>
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

if echo "$COMMAND" | grep -qE 'gh issue (close|edit.*--add-label.*HOLD)'; then
  ISSUE_NUM=$(echo "$COMMAND" | grep -oP '\d+' | head -1)

  # Check for commits mentioning this issue in the last hour
  RECENT_COMMITS=$(git log --oneline --since="1 hour ago" --grep="#${ISSUE_NUM}" 2>/dev/null)

  # Check for ACCP report
  ACCP_EXISTS=$(ls reports/accp/issue-${ISSUE_NUM}*.yaml 2>/dev/null)

  if [ -z "$RECENT_COMMITS" ] && [ -z "$ACCP_EXISTS" ]; then
    echo "[PRE-CLOSE GUARD] BLOCKED: Issue #${ISSUE_NUM} has NO commit and NO ACCP report" >&2
    echo "[PRE-CLOSE GUARD] Cannot close without evidence. Requirements:" >&2
    echo "  1. Git commit referencing #${ISSUE_NUM}" >&2
    echo "  2. ACCP report in reports/accp/issue-${ISSUE_NUM}.yaml" >&2
    exit 2
  fi

  if [ -z "$RECENT_COMMITS" ]; then
    echo "[PRE-CLOSE GUARD] WARNING: Issue #${ISSUE_NUM} has ACCP but NO commit" >&2
  fi
fi

echo "$INPUT"
exit 0
