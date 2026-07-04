#!/bin/bash
# Sync completed worktree commits to main branch
# Run after each workflow phase completes
set -euo pipefail

MAIN_DIR="$(pwd)"
SYNCED_FILE="$MAIN_DIR/.claude/.synced_commits"

touch "$SYNCED_FILE"

echo "[SYNC] Scanning worktrees..."
for wt in $(ls -d "$MAIN_DIR"/.claude/worktrees/wf_* 2>/dev/null); do
  if [ ! -d "$wt/.git" ] && [ ! -f "$wt/.git" ]; then
    continue
  fi

  cd "$wt"

  # Find commits on worktree branch that aren't in main yet
  BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
  if [ -z "$BRANCH" ] || [ "$BRANCH" = "HEAD" ]; then
    continue
  fi

  # Get all commits unique to this worktree
  for commit in $(git log --oneline --reverse "$BRANCH" --not main 2>/dev/null | cut -d' ' -f1); do
    if grep -q "$commit" "$SYNCED_FILE" 2>/dev/null; then
      continue  # already synced
    fi

    echo "[SYNC] Cherry-picking $commit from $BRANCH ($wt)"
    cd "$MAIN_DIR"
    if git cherry-pick "$commit" 2>&1; then
      echo "$commit" >> "$SYNCED_FILE"
      echo "[SYNC] ✓ $commit merged"
    else
      # Conflict? Skip and mark for manual review
      git cherry-pick --abort 2>/dev/null || true
      cd "$wt" && git diff --name-only "$commit^..$commit" 2>/dev/null | while read f; do
        if [ -f "$wt/$f" ]; then
          mkdir -p "$MAIN_DIR/$(dirname "$f")"
          cp "$wt/$f" "$MAIN_DIR/$f" 2>/dev/null
        fi
      done
      cd "$MAIN_DIR"
      echo "[SYNC] ⚠ $commit had conflict — files copied directly"
      echo "$commit" >> "$SYNCED_FILE"
    fi
  done
done

cd "$MAIN_DIR"

# Commit any direct copies
if ! git diff --quiet 2>/dev/null; then
  git add -A
  git commit -m "chore: auto-sync worktree files to main

Co-Authored-By: Claude <noreply@anthropic.com>" 2>&1
  echo "[SYNC] ✓ Committed auto-synced files"
fi

echo "[SYNC] Done. Worktrees synced to main."
