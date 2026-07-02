"""AlphaForge CLI — python3 -m cli.alphaforge

Usage:
    python3 -m cli.alphaforge status              Show all alphas and their metrics
    python3 -m cli.alphaforge discover             Run all discovery pipelines
    python3 -m cli.alphaforge simulate <id>        Run simulation on an alpha
    python3 -m cli.alphaforge simulate --all       Run simulation on all alphas
    python3 -m cli.alphaforge report list          List all report types
    python3 -m cli.alphaforge report generate ...  Generate a specific report
    python3 -m cli.alphaforge report status        Show generated reports
    python3 -m cli.alphaforge report menu          Interactive report menu
"""

from __future__ import annotations

import sys
from cli.alphaforge.run import main

if __name__ == "__main__":
    sys.exit(main())
