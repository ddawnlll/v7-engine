"""
simulation — Economic Truth Authority

/simulation is the single economic truth authority that evaluates
LONG_NOW, SHORT_NOW, and NO_TRADE outcomes under one configurable,
versioned, mode-specific simulation engine.

Ownership:
  - simulation owns economic truth semantics and contracts
  - V7 runtime hosts/executes simulation operationally
  - AlphaForge consumes simulation outputs through adapters
  - lib provides primitive math/indicators/costs

Import boundary: simulation may import from lib; must NOT import
v7, alphaforge, runtime, or interface.
"""

__version__ = "0.1.0"
