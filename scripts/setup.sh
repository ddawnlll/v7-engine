#!/usr/bin/env bash
# ===========================================================================
# V7 Engine — Environment Setup Script
#
# Prepares the development environment: Python version check, virtual
# environment, dependencies, and project verification.
#
# Usage:
#   ./scripts/setup.sh            Full setup + verify
#   ./scripts/setup.sh --quick    Skip venv creation, just verify
#   ./scripts/setup.sh --clean    Remove venv and rebuild
#   ./scripts/setup.sh --check    Only run checks (no install)
# ===========================================================================

set -euo pipefail

# ------------------------------------------------------------------
# Colors
# ------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()  { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; exit 1; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
step() { echo -e "  ${CYAN}→${NC} $1"; }

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
PYTHON_MIN_VER="3.12"

# ------------------------------------------------------------------
# Help
# ------------------------------------------------------------------
if [ "${1:-}" = "--help" ]; then
    echo "Usage: ./scripts/setup.sh [--quick|--clean|--check|--help]"
    echo ""
    echo "  (no flag)  Full setup: venv + deps + verify"
    echo "  --quick    Use existing venv, just verify"
    echo "  --clean    Remove venv and redo full setup"
    echo "  --check    Only run verification checks"
    echo "  --help     Show this message"
    exit 0
fi

echo ""
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  V7 Engine — Environment Setup${NC}"
echo -e "${CYAN}  $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo ""

# ==================================================================
# 1. Python version
# ==================================================================
echo -e "${YELLOW}[1/4]  Python${NC}"

PYTHON=$(command -v python3 || command -v python || echo "")
if [ -z "$PYTHON" ]; then
    fail "Python not found. Install Python ${PYTHON_MIN_VER}+ first."
fi

PY_VER=$($PYTHON --version 2>&1 | grep -oP '\d+\.\d+')
MAJOR=$(echo "$PY_VER" | cut -d. -f1)
MINOR=$(echo "$PY_VER" | cut -d. -f2)

if [ "$MAJOR" -lt 3 ] || { [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 12 ]; }; then
    fail "Python >= ${PYTHON_MIN_VER} required (found $PY_VER)"
fi
ok "Python ${PY_VER} at ${PYTHON}"

# ==================================================================
# 2. Virtual environment
# ==================================================================
echo -e "${YELLOW}[2/4]  Virtual environment${NC}"

DO_SETUP=true
if [ "${1:-}" = "--check" ]; then
    DO_SETUP=false
fi

if [ "${1:-}" = "--clean" ]; then
    step "Removing ${VENV_DIR}..."
    rm -rf "$VENV_DIR"
    ok "Removed"
fi

if $DO_SETUP; then
    if [ "${1:-}" = "--quick" ]; then
        if [ -d "$VENV_DIR" ]; then
            step "Quick mode: using existing venv"
        else
            step "No venv found — creating..."
            $PYTHON -m venv "$VENV_DIR"
            ok "Created"
        fi
    else
        if [ ! -d "$VENV_DIR" ]; then
            step "Creating ${VENV_DIR}..."
            $PYTHON -m venv "$VENV_DIR"
            ok "Created"
        else
            ok "Exists"
        fi
    fi

    source "$VENV_DIR/bin/activate"
    ok "Activated"

    step "Installing dependencies..."
    pip install --quiet -U pip setuptools wheel 2>/dev/null
    pip install --quiet pytest requests mypy ruff 2>/dev/null

    # Editable install so imports resolve without PYTHONPATH hacks
    step "Installing project in editable mode..."
    pip install -e "$PROJECT_DIR" 2>/dev/null
    ok "Project installed in editable mode"

    # Add alphaforge/src to path so `import alphaforge` works
    SITE_PKG="$("$PYTHON" -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || true)"
    if [ -n "$SITE_PKG" ]; then
        echo "$PROJECT_DIR/alphaforge/src" > "$SITE_PKG/v7_engine_alphaforge.pth"
        ok "alphaforge/src added to Python path"
    fi

    ok "Dependencies ready"
fi

# ==================================================================
# 3. Verification
# ==================================================================
echo -e "${YELLOW}[3/4]  Verification${NC}"

# 3a. lib/ importable
if $PYTHON -c "import lib" 2>/dev/null; then
    ok "lib/ importable"
else
    fail "lib/ cannot be imported — check PYTHONPATH"
fi

# 3b. Import boundary (hard stop)
PY_OK=true
$PYTHON -m pytest lib/tests/test_import_boundary.py -q 2>/dev/null || PY_OK=false

if $PY_OK; then
    ok "Import boundary: lib/ does NOT import v7/alphaforge"
else
    fail "IMPORT BOUNDARY VIOLATION: lib/ must not import v7* or alphaforge*"
fi

# 3c. Data directory
if [ -d "$PROJECT_DIR/data" ]; then
    ok "data/ exists"
else
    warn "data/ directory missing"
fi

# ==================================================================
# 4. Summary
# ==================================================================
echo -e "${YELLOW}[4/4]  Summary${NC}"
echo ""

# Source & test line counts
SRC_LINES=$(find lib/ -name '*.py' -not -path '*/tests/*' -exec cat {} + 2>/dev/null | wc -l)
TEST_LINES=$(find lib/tests/ -name '*.py' -exec cat {} + 2>/dev/null | wc -l)
TEST_COUNT=$($PYTHON -m pytest lib/tests/ --collect-only -q 2>/dev/null | grep -oP '^\d+' | head -1 || echo "?")

echo -e "  ${CYAN}lib/ source:${NC}     ${SRC_LINES} lines"
echo -e "  ${CYAN}lib/ tests:${NC}      ${TEST_LINES} lines (${TEST_COUNT} tests)"
echo ""

# Directory sizes
for dir in lib alphaforge v7 data; do
    if [ -d "$PROJECT_DIR/$dir" ]; then
        COUNT=$(find "$PROJECT_DIR/$dir" -type f 2>/dev/null | wc -l)
        printf "  %-18s %d files\n" "${dir}/" "$COUNT"
    fi
done

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Environment ready${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo ""
