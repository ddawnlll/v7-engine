"""Alpha factor registry."""
from __future__ import annotations
from alphaforge.alphas.base import AlphaBase
from alphaforge.alphas.alpha_momentum import AlphaMomentum

ALPHA_REGISTRY: dict[str, type[AlphaBase]] = {
    "momentum_21d": AlphaMomentum,
}

def get_alpha(name: str) -> AlphaBase:
    cls = ALPHA_REGISTRY.get(name)
    if cls is None:
        raise KeyError(f"Unknown alpha '{name}'. Available: {list(ALPHA_REGISTRY.keys())}")
    return cls()

def list_alphas() -> list[str]:
    return list(ALPHA_REGISTRY.keys())
