#!/bin/bash
# V7 Engine — Git Auto-Sync
# Installed at /root/v7-git-autosync.sh, runs every minute via crontab.
# Only operates on main branch — testing branches are left alone.
set -e

cd /root/v7-engine || exit 0

# Only sync on main branch — don't disrupt testing branches
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if [ "$BRANCH" != "main" ]; then
  exit 0
fi

# 1. Commit any working tree changes (from Mutagen sync)
git add alphaforge/src/ alphaforge/scripts/ alphaforge/tests/ cli/ contracts/ \
        docs/ lib/ runtime/ scripts/ simulation/ tests/ v6/ v7/ \
        configs/ config/ Makefile pyproject.toml AGENTS.md CLAUDE.md \
        requirements.txt mutagen.yml 2>/dev/null || true
if ! git diff --cached --quiet 2>/dev/null; then
  git commit -m "auto: sync $(date --iso=minutes)" --no-verify 2>/dev/null || true
  git push origin main 2>&1 | tail -1 || true
fi

# 2. Pull latest from origin (reset to avoid merge conflicts with Mutagen)
git fetch origin main 2>/dev/null || true
git reset --hard origin/main 2>/dev/null || true
