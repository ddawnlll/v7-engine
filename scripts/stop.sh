#!/usr/bin/env bash
# =============================================================================
# V7 Engine — Stop Services
# =============================================================================
# Graceful shutdown of docker-compose services.
# Usage: ./scripts/stop.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"

cd "$PROJECT_ROOT"

echo "=== V7 Engine — Stopping Services ==="

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "No docker-compose.yml found. Nothing to stop."
    exit 0
fi

echo "Sending graceful shutdown signal..."
docker compose -f "$COMPOSE_FILE" down --timeout 30

echo "Services stopped."
