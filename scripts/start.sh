#!/usr/bin/env bash
# =============================================================================
# V7 Engine — Start Services
# =============================================================================
# Starts the docker-compose services with validation.
# Usage: ./scripts/start.sh [profile]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"
PROFILE="${1:-production}"

cd "$PROJECT_ROOT"

echo "=== V7 Engine — Starting Services (profile: $PROFILE) ==="

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "ERROR: docker-compose.yml not found at $COMPOSE_FILE"
    exit 1
fi

if [ ! -f ".env" ] && [ "$PROFILE" != "development" ]; then
    echo "WARNING: .env file not found. Copy .env.example to .env first."
    echo "  cp .env.example .env"
fi

if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker is not running. Please start Docker first."
    exit 1
fi

echo "Starting services..."
docker compose -f "$COMPOSE_FILE" up -d

echo "Waiting for backend to be healthy..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/api/v3/health >/dev/null 2>&1; then
        echo "Backend is healthy!"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "WARNING: Backend did not become healthy within 30 seconds."
        echo "  Check logs with: docker compose logs backend"
    fi
    sleep 2
done

echo ""
echo "=== Services Status ==="
docker compose -f "$COMPOSE_FILE" ps

echo ""
echo "=== V7 Engine Started ==="
echo "  Backend:  http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo "  Health:   http://localhost:8000/api/v3/health"
