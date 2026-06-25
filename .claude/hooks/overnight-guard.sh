#!/bin/bash
# Overnight safety guard — PreToolUse hook
# Blocks dangerous operations during autonomous overnight runs
# Invoked before every Bash/Edit/Write tool use

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // ""')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // ""')

# === BLOCK: Network/API calls (whitelist approach) ===
if echo "$COMMAND" | grep -qE '(curl|wget|httpx|requests\.(get|post)|urllib|http\.client|nc |ncat |socat |aria2c|gcloud |aws |ssh |scp |rsync |pip install|npm install|yarn add)'; then
  if ! echo "$COMMAND" | grep -qE '(localhost|127\.0\.0\.1|github\.com/api|api\.github\.com)'; then
    echo "[OVERNIGHT-GUARD] BLOCKED: External network call: $COMMAND" >&2
    exit 2
  fi
fi
# URL pattern block (catch Python/Node network calls with URLs)
if echo "$COMMAND $CONTENT" | grep -qE '[a-z]+://[^/]' && ! echo "$COMMAND $CONTENT" | grep -qE '(file://|localhost|127\.0\.0\.1|github\.com/api)'; then
  echo "[OVERNIGHT-GUARD] BLOCKED: URL pattern in command (potential network call)" >&2
  exit 2
fi

# === BLOCK: Live trading / real money ===
if echo "$COMMAND $CONTENT" | grep -qiE '(create_order|market_order|live_trading|real_money|production_key|BINANCE_API_KEY|BINANCE_SECRET)'; then
  echo "[OVERNIGHT-GUARD] BLOCKED: Live trading or real money operation" >&2
  exit 2
fi

# === BLOCK: Training outside Plan 05 ===
if echo "$COMMAND $CONTENT" | grep -qE '(\.fit\(|\.train\(|XGBClassifier|XGBRegressor|xgboost\.train)'; then
  if ! echo "$CONTENT" | grep -q 'TR-05\|Plan 05\|plan_05'; then
    echo "[OVERNIGHT-GUARD] BLOCKED: Model training outside TR-05 context" >&2
    exit 2
  fi
fi

# === BLOCK: Plans directory modification during implementation ===
FILE_NORM=$(realpath -m "$FILE" 2>/dev/null || echo "$FILE")
if echo "$FILE_NORM" | grep -qE '(^|/)plans/' && echo "$TOOL" | grep -qE '(Write|Edit)'; then
  echo "[OVERNIGHT-GUARD] BLOCKED: Cannot modify plans/ during implementation phase" >&2
  exit 2
fi

# === BLOCK: Schema/template mutation ===
if echo "$FILE" | grep -qE '(contracts/registry\.json|contracts/compatibility\.json)' && echo "$TOOL" | grep -qE '(Write|Edit)'; then
  echo "[OVERNIGHT-GUARD] WARNING: Contract registry modification detected" >&2
  # Allow but warn — contract additions may be legitimate
fi

# === WARN: Working outside worktree ===
if ! echo "$PWD" | grep -q '.claude/worktrees'; then
  echo "[OVERNIGHT-GUARD] WARNING: Working outside worktree isolation: $PWD" >&2
fi

# All checks passed
echo "$INPUT"
exit 0
