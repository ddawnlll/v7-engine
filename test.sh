#!/usr/bin/env bash
# ===========================================================================
# V7 Engine — Environment Preparation & Verification Script
#
# Usage:
#   ./test.sh              Full setup + all tests
#   ./test.sh quick        Quick: tests only (skip venv setup)
#   ./test.sh reset        Remove venv and rebuild from scratch
# ===========================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; exit 1; }
info() { echo -e "  ${CYAN}→${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
PYTHON_REQUIRED="3.11"

echo ""
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  V7 Engine — Environment & Test Runner${NC}"
echo -e "${CYAN}  $(date +%Y-%m-%d\ %H:%M:%S)${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo ""

# ------------------------------------------------------------------
# Phase 1: Python version check
# ------------------------------------------------------------------
echo -e "${YELLOW}[1/5] Python version check${NC}"
PYTHON=$(command -v python3 || command -v python || echo "")
if [ -z "$PYTHON" ]; then
    fail "Python not found. Install Python $PYTHON_REQUIRED+ first."
fi

PY_VER=$($PYTHON --version 2>&1 | grep -oP '\d+\.\d+')
MAJOR=$(echo "$PY_VER" | cut -d. -f1)
MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$MAJOR" -lt 3 ] || { [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 11 ]; }; then
    fail "Python >= 3.11 required (found $PY_VER)"
fi
pass "Python $PY_VER found at $PYTHON"

# ------------------------------------------------------------------
# Phase 2: Virtual environment
# ------------------------------------------------------------------
echo -e "${YELLOW}[2/5] Virtual environment${NC}"

if [ "${1:-}" = "reset" ]; then
    info "Resetting virtual environment..."
    rm -rf "$VENV_DIR"
fi

if [ "${1:-}" != "quick" ]; then
    if [ ! -d "$VENV_DIR" ]; then
        info "Creating virtual environment at $VENV_DIR"
        $PYTHON -m venv "$VENV_DIR"
        pass "Virtual environment created"
    else
        pass "Virtual environment exists"
    fi

    source "$VENV_DIR/bin/activate"
    pass "Virtual environment activated"

    info "Installing/updating dependencies..."
    pip install -q -U pip setuptools wheel 2>/dev/null
    pip install -q pytest requests mypy ruff 2>/dev/null
    pass "Dependencies installed"
else
    # quick mode: activate if it exists, but don't fail if not
    if [ -d "$VENV_DIR" ]; then
        source "$VENV_DIR/bin/activate" 2>/dev/null || true
    fi
    info "Quick mode: using existing environment"
fi

# ------------------------------------------------------------------
# Phase 3: Import boundary check (hard stop)
# ------------------------------------------------------------------
echo -e "${YELLOW}[3/5] Import boundary check${NC}"
$PYTHON -c "
import sys, importlib
try:
    import lib
    print('  lib/ importable ✓')
except ImportError as e:
    print(f'  lib/ import FAILED: {e}')
    sys.exit(1)
"

$PYTHON -m pytest lib/tests/test_import_boundary.py -v -q 2>&1 | tail -1 | grep -q "PASSED\|passed" && \
    pass "Import boundary clean (lib/ does not import v7/alphaforge)" || \
    fail "IMPORT BOUNDARY VIOLATION: lib/ imports from v7 or alphaforge"

# ------------------------------------------------------------------
# Phase 4: Run all tests
# ------------------------------------------------------------------
echo -e "${YELLOW}[4/5] Running all lib/ tests${NC}"

if [ "${1:-}" = "quick" ]; then
    # Quick: just one module per area
    TEST_FILES=(
        lib/tests/test_market_data_contracts.py
        lib/tests/test_indicators.py
        lib/tests/test_costs.py
        lib/tests/test_time.py
    )
else
    TEST_FILES=(lib/tests/)
fi

set +e
"$PYTHON" -m pytest "${TEST_FILES[@]}" -v 2>&1
EXIT_CODE=$?
set -e

if [ $EXIT_CODE -eq 0 ]; then
    pass "All tests passed"
else
    fail "Some tests failed (exit code $EXIT_CODE)"
fi

# ------------------------------------------------------------------
# Phase 5: Summary & structure
# ------------------------------------------------------------------
echo -e "${YELLOW}[5/5] Environment summary${NC}"
echo ""

# Count lines of code in lib/
LIB_PY=$(find lib/ -name '*.py' -not -path '*/tests/*' | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}')
LIB_TESTS=$(find lib/tests/ -name '*.py' | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}')
LIB_DOCS=$(find lib/docs/ -type f | wc -l)

echo -e "  ${CYAN}lib/ Python source:${NC}  ${LIB_PY:-?} lines"
echo -e "  ${CYAN}lib/ tests:${NC}         ${LIB_TESTS:-?} lines"
echo -e "  ${CYAN}lib/ doc files:${NC}    ${LIB_DOCS:-?} files"
echo ""

# Show repo structure
echo -e "  ${CYAN}Repo structure:${NC}"
for item in lib alphaforge v7 data; do
    if [ -d "$item" ]; then
        NUM=$(find "$item" -type f 2>/dev/null | wc -l)
        echo "    📁 $item/  ($NUM files)"
    else
        echo "    📁 $item/  (empty)"
    fi
done
echo ""

echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Environment ready${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo ""
