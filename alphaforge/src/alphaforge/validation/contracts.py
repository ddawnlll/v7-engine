"""AlphaForge Validation contracts — dataclasses, enums, sentinels, and helpers.

Defines the WalkForwardConfig, Fold, FoldResult, ValidationReport, and all
supporting dataclasses for walk-forward validation. Also provides NOT_EVALUATED
sentinel, purge/embargo helpers, mode-specific defaults, and ValidationError.

This module imports ZERO ML libraries (no xgboost, sklearn, tensorflow, torch).
All metric fields use the NOT_EVALUATED sentinel — no fake numeric values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# NOT_EVALUATED sentinel
# ---------------------------------------------------------------------------

class _NotEvaluatedType:
    """Singleton sentinel for metric fields that have not been computed.

    Distinguishable from None, 0.0, '', and any other value.
    Compares equal only to itself.  Has a visually distinctive repr.
    """

    _instance: Optional[_NotEvaluatedType] = None

    def __new__(cls) -> _NotEvaluatedType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "NOT_EVALUATED"

    def __str__(self) -> str:
        return "NOT_EVALUATED"

    def __bool__(self) -> bool:
        return False

    def __eq__(self, other: object) -> bool:
        return other is self

    def __hash__(self) -> int:
        return id(self)

    # Ensure NOT_EVALUATED != any numeric value
    def __lt__(self, other: object) -> bool:
        return False

    def __le__(self, other: object) -> bool:
        return other is self

    def __gt__(self, other: object) -> bool:
        return False

    def __ge__(self, other: object) -> bool:
        return other is self


NOT_EVALUATED = _NotEvaluatedType()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Mode(str, Enum):
    """Canonical V7 trading modes."""

    SCALP = "SCALP"
    AGGRESSIVE_SCALP = "AGGRESSIVE_SCALP"
    SWING = "SWING"


class WindowType(str, Enum):
    """Walk-forward window strategy."""

    ANCHORED = "ANCHORED"
    ROLLING = "ROLLING"


class ValidationVerdict(str, Enum):
    """Validation verdict per validation_contract.md.

    Seven verdicts (plus BLOCKED_FOR_MHT from the schema):
    """

    PASS = "PASS"
    PASS_WITH_LIMITATIONS = "PASS_WITH_LIMITATIONS"
    FAIL_OVERFIT = "FAIL_OVERFIT"
    FAIL_COST = "FAIL_COST"
    FAIL_REGIME = "FAIL_REGIME"
    FAIL_OOS = "FAIL_OOS"
    INCONCLUSIVE = "INCONCLUSIVE"
    FAIL_MHT = "FAIL_MHT"            # from schema
    BLOCKED_FOR_MHT = "BLOCKED_FOR_MHT"  # from schema


class RegimeLabel(str, Enum):
    """V7 canonical regime taxonomy (per evaluation.md G4)."""

    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"


# ---------------------------------------------------------------------------
# Mode-specific purge window constants (validation_contract.md)
# ---------------------------------------------------------------------------

MODE_PURGE_BARS: Dict[Mode, int] = {
    Mode.SCALP: 100,
    Mode.AGGRESSIVE_SCALP: 200,
    Mode.SWING: 20,
}

MODE_EMBARGO_BARS: Dict[Mode, int] = {
    Mode.SCALP: 100,
    Mode.AGGRESSIVE_SCALP: 200,
    Mode.SWING: 20,
}


# ---------------------------------------------------------------------------
# ValidationError
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationError(Exception):
    """Raised when walk-forward validation cannot proceed.

    Fields:
        message: Human-readable error description.
        mode: The mode for which validation was attempted.
        required_folds: Minimum folds required (6).
        available_bars: Bar count in the provided dataset.
        required_bars: Minimum bars needed for the mode.
        suggestion: Human-readable fix guidance.
    """

    message: str
    mode: Optional[Mode] = None
    required_folds: int = 6
    available_bars: int = 0
    required_bars: int = 0
    suggestion: str = ""

    def __str__(self) -> str:
        return self.message


# ---------------------------------------------------------------------------
# Core dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WalkForwardConfig:
    """Configuration for walk-forward validation per mode.

    Fields:
        mode: Trading mode (SCALP, AGGRESSIVE_SCALP, SWING).
        min_folds: Minimum walk-forward folds (default 6, per G2).
        train_ratio: Fraction for training (default 0.6).
        val_ratio: Fraction for validation (default 0.2).
        oos_ratio: Fraction for OOS testing (default 0.2).
        train_window_bars: Training window size in bars.
        test_window_bars: Test (val + oos) window size in bars.
        purge_bars: Purge gap between train and test in bars.
        embargo_bars: Minimum bar distance between train and any test sample.
        window_type: ANCHORED (train expands) or ROLLING (train slides).
    """

    mode: Mode
    min_folds: int = 6
    train_ratio: float = 0.6
    val_ratio: float = 0.2
    oos_ratio: float = 0.2
    train_window_bars: int = 2000
    test_window_bars: int = 500
    purge_bars: int = 20
    embargo_bars: int = 20
    window_type: WindowType = WindowType.ANCHORED

    def __post_init__(self) -> None:
        total = self.train_ratio + self.val_ratio + self.oos_ratio
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"Split ratios must sum to 1.0, got {total} "
                f"(train={self.train_ratio}, val={self.val_ratio}, oos={self.oos_ratio})"
            )
        if self.train_window_bars < 1:
            raise ValueError("train_window_bars must be positive")
        if self.test_window_bars < 1:
            raise ValueError("test_window_bars must be positive")
        if self.purge_bars < 0:
            raise ValueError("purge_bars must be non-negative")
        if self.embargo_bars < 0:
            raise ValueError("embargo_bars must be non-negative")


@dataclass(frozen=True)
class Fold:
    """One walk-forward fold with datetime boundaries and index ranges.

    All start/end fields are ISO 8601 strings derived from the dataset's
    feature_timestamp field.  Indices are integer positions into the sorted
    dataset list.
    """

    fold_index: int
    # Datetime boundaries (ISO 8601)
    train_start: str
    train_end: str
    val_start: str
    val_end: str
    oos_start: str
    oos_end: str
    # Index ranges (integer positions into sorted dataset)
    train_indices: List[int] = field(default_factory=list)
    val_indices: List[int] = field(default_factory=list)
    oos_indices: List[int] = field(default_factory=list)
    # Purge / embargo metadata
    purge_before_val: int = 0   # bars between train end and val start
    purge_before_oos: int = 0   # bars between val end and oos start
    embargo_applied: bool = False


@dataclass(frozen=True)
class OOSSummary:
    """Aggregate OOS summary — all metrics NOT_EVALUATED until models run."""

    oos_sharpe: Any = NOT_EVALUATED       # Optional[float]
    oos_win_rate: Any = NOT_EVALUATED     # Optional[float]
    oos_expectancy: Any = NOT_EVALUATED   # Optional[float]
    oos_max_drawdown: Any = NOT_EVALUATED  # Optional[float]
    oos_profit_factor: Any = NOT_EVALUATED  # Optional[float]
    oos_trades_count: Any = NOT_EVALUATED  # Optional[int]
    oos_stability: Any = NOT_EVALUATED    # Optional[float]
    oos_positive_expectancy: Any = NOT_EVALUATED  # Optional[bool]


@dataclass(frozen=True)
class CostStressResult:
    """Cost stress analysis — all levels NOT_EVALUATED.

    funding_deferred_block is populated with the DEFERRED explanation text.
    """

    fee_baseline: Any = NOT_EVALUATED
    fee_stress_1_5x: Any = NOT_EVALUATED
    fee_stress_2x: Any = NOT_EVALUATED
    fee_stress_3x: Any = NOT_EVALUATED
    slippage_baseline: Any = NOT_EVALUATED
    slippage_stress_1_5x: Any = NOT_EVALUATED
    slippage_stress_2x: Any = NOT_EVALUATED
    slippage_stress_3x: Any = NOT_EVALUATED
    spread_baseline: Any = NOT_EVALUATED
    spread_stress_1_5x: Any = NOT_EVALUATED
    spread_stress_2x: Any = NOT_EVALUATED
    combined_stress: Any = NOT_EVALUATED
    break_even_cost: Any = NOT_EVALUATED
    funding_deferred_block: str = (
        "Funding model is DEFERRED. Live/perpetual promotion is blocked "
        "until funding cost model is implemented. See simulation/docs/cost_model.md."
    )
    fee_stress_edge_survives: Any = NOT_EVALUATED
    slippage_stress_edge_survives: Any = NOT_EVALUATED
    combined_stress_edge_survives: Any = NOT_EVALUATED


@dataclass(frozen=True)
class RegimeBreakdown:
    """Per-regime metrics using V7 canonical TREND_UP/DOWN/RANGE/TRANSITION.

    All per-regime fields are NOT_EVALUATED.
    """

    TREND_UP: Any = NOT_EVALUATED
    TREND_DOWN: Any = NOT_EVALUATED
    RANGE: Any = NOT_EVALUATED
    TRANSITION: Any = NOT_EVALUATED
    edge_only_in_rare_regime: Any = NOT_EVALUATED
    rare_regime_untradeable: Any = NOT_EVALUATED


@dataclass(frozen=True)
class SymbolStability:
    """Symbol concentration and cross-symbol variance.

    Limits are immutable constants.  All metric fields are NOT_EVALUATED.
    """

    MAX_SINGLE_SYMBOL_CONCENTRATION: float = 0.40
    MAX_CLUSTER_CONCENTRATION: float = 0.60

    symbols_tested: Any = NOT_EVALUATED
    symbol_count: Any = NOT_EVALUATED
    max_single_symbol_concentration: Any = NOT_EVALUATED
    max_cluster_concentration: Any = NOT_EVALUATED
    cross_symbol_variance: Any = NOT_EVALUATED
    min_symbols_tested: Any = NOT_EVALUATED
    single_symbol_limitation: Any = NOT_EVALUATED


@dataclass(frozen=True)
class MHTControls:
    """Multiple hypothesis testing and data-snooping controls.

    All fields set per P0.8E defaults: NOT_EVALUATED or NONE_APPLIED.
    data_snooping_risk_flag is HIGH because no correction has been applied.
    """

    tested_hypothesis_count: Any = NOT_EVALUATED
    correction_method: str = "NONE_APPLIED"
    corrected_significance: Any = NOT_EVALUATED
    false_discovery_control: Any = NOT_EVALUATED
    deflated_sharpe: Any = NOT_EVALUATED
    pbo_risk: Any = NOT_EVALUATED
    trial_count_disclosure: Any = NOT_EVALUATED
    rejected_candidate_count: Any = NOT_EVALUATED
    data_snooping_risk_flag: str = "HIGH"


@dataclass(frozen=True)
class OverfitFlag:
    """Single overfit risk indicator."""

    indicator: str          # e.g. "train_oos_gap", "fold_instability"
    severity: str           # LOW, MEDIUM, HIGH, CRITICAL
    description: str = ""


@dataclass(frozen=True)
class FoldResult:
    """Per-fold results — all metrics NOT_EVALUATED except structural counts."""

    fold_index: int
    train_metrics: Any = NOT_EVALUATED
    val_metrics: Any = NOT_EVALUATED
    oos_metrics: Any = NOT_EVALUATED
    regime_breakdown: Any = NOT_EVALUATED
    cost_stress: Any = NOT_EVALUATED
    sample_counts: Dict[str, int] = field(default_factory=dict)

    @property
    def train_count(self) -> int:
        return self.sample_counts.get("train", 0)

    @property
    def val_count(self) -> int:
        return self.sample_counts.get("val", 0)

    @property
    def oos_count(self) -> int:
        return self.sample_counts.get("oos", 0)


@dataclass(frozen=True)
class ValidationReport:
    """Complete walk-forward validation report skeleton.

    All metric fields use NOT_EVALUATED.  The only real numbers are structural
    (fold counts, sample counts).  Verdict is INCONCLUSIVE until metrics exist.
    """

    config: WalkForwardConfig
    folds: List[FoldResult] = field(default_factory=list)
    oos_summary: OOSSummary = field(default_factory=OOSSummary)
    cost_stress: CostStressResult = field(default_factory=CostStressResult)
    regime_breakdown: RegimeBreakdown = field(default_factory=RegimeBreakdown)
    symbol_stability: SymbolStability = field(default_factory=SymbolStability)
    overfit_risk_flags: List[OverfitFlag] = field(default_factory=list)
    mht_controls: MHTControls = field(default_factory=MHTControls)
    verdict: ValidationVerdict = ValidationVerdict.INCONCLUSIVE
    report_id: str = ""
    generated_at: str = ""


# ---------------------------------------------------------------------------
# Purge / embargo helpers
# ---------------------------------------------------------------------------

# Alias for type hints in external callers
# (LabeledDataset is imported lazily to avoid circular imports)
LabeledDatasetRow = Any  # duck-typed: has feature_timestamp, symbol attributes


def _distinct_timestamp_count(
    dataset: List[LabeledDatasetRow], start_idx: int, end_idx: int
) -> int:
    """Count distinct feature_timestamps in dataset slice [start_idx, end_idx)."""
    if start_idx >= end_idx:
        return 0
    seen: Set[str] = set()
    for i in range(start_idx, min(end_idx, len(dataset))):
        seen.add(dataset[i].feature_timestamp)
    return len(seen)


def _get_timestamps(
    dataset: List[LabeledDatasetRow], indices: List[int]
) -> Set[str]:
    """Extract distinct feature_timestamps for the given index list."""
    return {dataset[i].feature_timestamp for i in indices if 0 <= i < len(dataset)}


def _distinct_bars_between(
    dataset: List[LabeledDatasetRow],
    ts_set_a: Set[str],
    ts_set_b: Set[str],
) -> int:
    """Count distinct feature_timestamps that fall between two timestamp sets.

    Only timestamps in the dataset that are strictly between
    max(ts_set_a) and min(ts_set_b) count.
    """
    if not ts_set_a or not ts_set_b:
        return 0
    max_a = max(ts_set_a)
    min_b = min(ts_set_b)
    # Collect all distinct timestamps in the dataset that fall between
    between: Set[str] = set()
    for row in dataset:
        ts = row.feature_timestamp
        if max_a < ts < min_b:
            between.add(ts)
    return len(between)


def purge_gap(
    fold: Fold,  # type: ignore[valid-type]
    dataset: List[LabeledDatasetRow],
    mode: Mode,
    required: int | None = None,
) -> Tuple[int, int]:
    """Compute purge bar gaps for a fold.

    Returns (gap_val, gap_oos) — the number of distinct timestamps between
    train end / val start and val end / oos start respectively.

    Raises ValidationError if either gap is below the purge threshold.

    If required is None, the mode-specific default from MODE_PURGE_BARS is used.
    """
    if required is None:
        required = MODE_PURGE_BARS.get(mode, 20)

    train_ts = _get_timestamps(dataset, fold.train_indices)
    val_ts = _get_timestamps(dataset, fold.val_indices)
    oos_ts = _get_timestamps(dataset, fold.oos_indices)

    gap_val = _distinct_bars_between(dataset, train_ts, val_ts)
    gap_oos = _distinct_bars_between(dataset, val_ts, oos_ts)

    if gap_val < required:
        raise ValidationError(
            message=(
                f"Purge violation: gap between train end and val start is "
                f"{gap_val} bars, but mode {mode.value} requires >= {required} bars."
            ),
            mode=mode,
            suggestion=(
                f"Increase the purge window or reduce folds. "
                f"Required: {required} bars. Actual: {gap_val} bars."
            ),
        )
    if gap_oos < required:
        raise ValidationError(
            message=(
                f"Purge violation: gap between val end and oos start is "
                f"{gap_oos} bars, but mode {mode.value} requires >= {required} bars."
            ),
            mode=mode,
            suggestion=(
                f"Increase the purge window or reduce folds. "
                f"Required: {required} bars. Actual: {gap_oos} bars."
            ),
        )

    return gap_val, gap_oos


def embargo_distance(
    train_indices: List[int],
    test_indices: List[int],
    dataset: List[LabeledDatasetRow],
) -> int:
    """Compute minimum bar distance between train and test sets.

    Returns the number of distinct timestamps between the closest train sample
    and the closest test sample.  0 if they share a timestamp.

    Raises ValidationError if min distance < embargo_bars.
    """
    train_ts = _get_timestamps(dataset, train_indices)
    test_ts = _get_timestamps(dataset, test_indices)

    # If timestamp sets overlap or touch, distance is 0
    if train_ts & test_ts:
        return 0

    # Sort timestamps and find minimum gap
    train_sorted = sorted(train_ts)
    test_sorted = sorted(test_ts)

    # The distance in bars is the count of distinct timestamps between
    # max(train) and min(test).  If train ends before test starts.
    max_train = train_sorted[-1]
    min_test = test_sorted[0]

    if max_train < min_test:
        distance = _distinct_bars_between(dataset, {max_train}, {min_test})
        return distance

    # Test is before train — shouldn't happen in chronological split
    return 0


# ---------------------------------------------------------------------------
# PurgePolicy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PurgePolicy:
    """Bundles mode, purge_bars, and embargo_bars for a validation run.

    Provides validate_purge() to confirm a fold satisfies purge constraints.
    """

    mode: Mode
    purge_bars: int
    embargo_bars: int

    @classmethod
    def for_mode(cls, mode: Mode) -> PurgePolicy:
        """Create PurgePolicy with mode-specific defaults."""
        return cls(
            mode=mode,
            purge_bars=MODE_PURGE_BARS.get(mode, 20),
            embargo_bars=MODE_EMBARGO_BARS.get(mode, 20),
        )

    def validate_purge(
        self, fold: Fold, dataset: List[LabeledDatasetRow]  # type: ignore[valid-type]
    ) -> Tuple[int, int]:
        """Validate that a fold satisfies purge constraints.

        Returns (gap_val, gap_oos) bar counts on success.
        Raises ValidationError on failure.
        """
        return purge_gap(fold, dataset, self.mode, required=self.purge_bars)

    def validate_embargo(
        self,
        fold: Fold,
        dataset: List[LabeledDatasetRow],  # type: ignore[valid-type]
    ) -> bool:
        """Confirm train-test embargo distance is satisfied.

        Raises ValidationError if any train sample is within embargo_bars of
        any test (val or oos) sample.
        """
        test_indices = fold.val_indices + fold.oos_indices

        if not test_indices:
            return True

        min_dist = embargo_distance(fold.train_indices, test_indices, dataset)

        if min_dist < self.embargo_bars:
            raise ValidationError(
                message=(
                    f"Embargo violation: minimum bar distance between train and test "
                    f"samples is {min_dist} bars, but mode {self.mode.value} requires "
                    f">= {self.embargo_bars} bars."
                ),
                mode=self.mode,
                suggestion=(
                    f"Increase embargo window or reduce fold overlap."
                ),
            )
        return True


# ---------------------------------------------------------------------------
# Mode-specific default configurations
# ---------------------------------------------------------------------------

DEFAULT_PURGE_POLICIES: Dict[Mode, PurgePolicy] = {
    Mode.SCALP: PurgePolicy(
        mode=Mode.SCALP, purge_bars=100, embargo_bars=100
    ),
    Mode.AGGRESSIVE_SCALP: PurgePolicy(
        mode=Mode.AGGRESSIVE_SCALP, purge_bars=200, embargo_bars=200
    ),
    Mode.SWING: PurgePolicy(
        mode=Mode.SWING, purge_bars=20, embargo_bars=20
    ),
}

DEFAULT_FOLD_CONFIGS: Dict[Mode, WalkForwardConfig] = {
    Mode.SCALP: WalkForwardConfig(
        mode=Mode.SCALP,
        min_folds=6,
        train_ratio=0.6,
        val_ratio=0.2,
        oos_ratio=0.2,
        train_window_bars=5000,
        test_window_bars=1000,
        purge_bars=100,
        embargo_bars=100,
        window_type=WindowType.ROLLING,
    ),
    Mode.AGGRESSIVE_SCALP: WalkForwardConfig(
        mode=Mode.AGGRESSIVE_SCALP,
        min_folds=6,
        train_ratio=0.6,
        val_ratio=0.2,
        oos_ratio=0.2,
        train_window_bars=5000,
        test_window_bars=1000,
        purge_bars=200,
        embargo_bars=200,
        window_type=WindowType.ROLLING,
    ),
    Mode.SWING: WalkForwardConfig(
        mode=Mode.SWING,
        min_folds=6,
        train_ratio=0.6,
        val_ratio=0.2,
        oos_ratio=0.2,
        train_window_bars=2000,
        test_window_bars=500,
        purge_bars=20,
        embargo_bars=20,
        window_type=WindowType.ANCHORED,
    ),
}
