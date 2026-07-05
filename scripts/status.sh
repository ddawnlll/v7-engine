#!/usr/bin/env bash
# =============================================================================
# V7 Engine — Status Check
# =============================================================================
# Reports the health status of all services.
# Usage: ./scripts/status.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"

cd "$PROJECT_ROOT"

echo "=== V7 Engine — Status Check ==="
echo ""

if [ -f "$COMPOSE_FILE" ]; then
    echo "--- Docker Services ---"
    if docker compose -f "$COMPOSE_FILE" ps 2>/dev/null; then
        echo ""
    else
        echo "  (not running)"
    fi
fi

echo "--- API Health ---"
HEALTH=$(curl -sf http://localhost:8000/api/v3/health 2>/dev/null || true)
if [ -n "$HEALTH" ]; then
    echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
else
    echo "  Backend not reachable at localhost:8000"
fi

echo ""
echo "--- Database ---"
if docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U v7 2>/dev/null; then
    echo "  PostgreSQL: connected"
else
    echo "  PostgreSQL: not reachable"
fi

echo ""
echo "--- Disk Usage ---"
du -sh data/ 2>/dev/null || echo "  (no data directory)"
du -sh logs/ 2>/dev/null || echo "  (no logs directory)"

echo ""
echo "=== Status Check Complete ==="
