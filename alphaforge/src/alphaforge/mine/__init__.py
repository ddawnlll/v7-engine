"""AlphaForge Mining Engine — boolean mask bitsets and condition discovery.

Exports:
    FeatureBucketizer — bins continuous feature columns into decile-based
        boolean masks for use as bitsets in the mining engine.
    ConditionRecord — dataclass describing a single condition in the registry.
"""

from alphaforge.mine.bucketizer import (
    ConditionRecord,
    FeatureBucketizer,
)

__version__ = "0.1.0"
__authority__ = "alphaforge"
__domain__ = "mining_engine"

__all__ = [
    "ConditionRecord",
    "FeatureBucketizer",
]
