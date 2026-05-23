#!/usr/bin/env python3
"""Entry-point redirect — delegates to alphas.main."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from alphas.main import main

if __name__ == "__main__":
    main()
