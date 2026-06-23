#!/usr/bin/env bash
set -euo pipefail

# Zip uncommitted (unstaged + staged + untracked) changes of the current git repo.
# Usage: ./scripts/zip-uncommitted.sh [output-name.zip]

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || { echo "Not a git repo"; exit 1; })
OUTPUT="${1:-uncommitted-changes.zip}"

cd "$REPO_ROOT"

# Collect: staged (diff-index), unstaged modified (diff-files), untracked (ls-files --others)
# Deduplicate with sort -u, then zip preserving directory structure.
{
  git diff-index --name-only --cached HEAD 2>/dev/null
  git diff-files --name-only 2>/dev/null
  git ls-files --others --exclude-standard 2>/dev/null
} | sort -u | zip -q "$OUTPUT" -@

# Count files in the zip
COUNT=$(unzip -l "$OUTPUT" 2>/dev/null | tail -1 | awk '{print $2}')
echo "→ Created $OUTPUT ($COUNT files)"
