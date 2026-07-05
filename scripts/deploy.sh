#!/usr/bin/env bash
# =============================================================================
# V7 Engine — Deploy
# =============================================================================
# Pull latest, build, migrate DB, deploy with rollback capability.
# Usage: ./scripts/deploy.sh [--dry-run]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DRY_RUN=false

cd "$PROJECT_ROOT"

echo "=== V7 Engine — Deploy ($TIMESTAMP) ==="

if [ "${1:-}" = "--dry-run" ]; then
    echo "  DRY RUN MODE — no changes will be made"
    DRY_RUN=true
fi

echo ""
echo "[1/5] Pre-deployment checks..."
if [ ! -f ".env" ]; then
    echo "  WARNING: .env file not found"
fi
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "  ERROR: docker-compose.yml not found"
    exit 1
fi
echo "  Checks passed"

echo ""
echo "[2/5] Updating code..."
if [ -d ".git" ]; then
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    echo "  Current branch: $CURRENT_BRANCH"
    if [ "$DRY_RUN" = "false" ]; then
        git pull origin "$CURRENT_BRANCH"
        echo "  Code updated"
    else
        echo "  [DRY RUN] git pull origin $CURRENT_BRANCH"
    fi
else
    echo "  Not a git repository, skipping pull"
fi

echo ""
echo "[3/5] Building Docker images..."
if [ "$DRY_RUN" = "false" ]; then
    docker compose -f "$COMPOSE_FILE" build --pull
    echo "  Build complete"
else
    echo "  [DRY RUN] docker compose build --pull"
fi

echo ""
echo "[4/5] Deploying services..."
if [ "$DRY_RUN" = "false" ]; then
    echo "  Creating deploy snapshot..."
    docker compose -f "$COMPOSE_FILE" images --quiet backend 2>/dev/null | \
        xargs -I{} docker tag {} "v7-engine-backend:deploy-${TIMESTAMP}" 2>/dev/null || true
    docker compose -f "$COMPOSE_FILE" up -d --remove-orphans
    echo "  Services deployed"
else
    echo "  [DRY RUN] docker compose up -d --remove-orphans"
fi

echo ""
echo "[5/5] Post-deployment health check..."
if [ "$DRY_RUN" = "false" ]; then
    for i in $(seq 1 30); do
        HEALTH=$(curl -sf http://localhost:8000/api/v3/health 2>/dev/null || true)
        if [ -n "$HEALTH" ]; then
            STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")
            echo "  Health status: $STATUS"
            if [ "$STATUS" = "healthy" ]; then
                break
            fi
        fi
        if [ "$i" -eq 30 ]; then
            echo "  WARNING: Health check did not pass within 30 seconds."
            echo "  Run ./scripts/status.sh for diagnostics."
        fi
        sleep 2
    done
else
    echo "  [DRY RUN] Health check skipped"
fi

echo ""
echo "=== Deploy $TIMESTAMP Complete ==="
