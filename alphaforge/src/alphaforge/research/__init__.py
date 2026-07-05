"""AlphaForge research analysis — model evolution, head-to-head comparison.

This subpackage provides model evolution research tools that compare
alternative architectures (RandomForest, MLP) against the XGBoost baseline
on identical data. It includes:

- Alternative trainers wrapping sklearn classifiers
- Head-to-head model comparison (accuracy, logloss, training speed,
  inference speed, model size)
- Best architecture recommendation per trading mode
- Inference cost benchmarking (batched and single-sample)

P0.11 (Issue #144): Model Evolution Research — XGBoost vs RandomForest vs MLP.
"""

from alphaforge.research.evolution import (
    AlternativeModelResult,
    BenchmarkResult,
    InferenceBenchmark,
    ModelComparisonResult,
    RandomForestTrainer,
    MLPTrainer,
    compare_models,
    inference_cost_benchmark,
    recommend_best_per_mode,
)

__all__ = [
    "AlternativeModelResult",
    "BenchmarkResult",
    "InferenceBenchmark",
    "ModelComparisonResult",
    "RandomForestTrainer",
    "MLPTrainer",
    "compare_models",
    "inference_cost_benchmark",
    "recommend_best_per_mode",
]
