from dataclasses import dataclass, field


@dataclass(frozen=True)
class SprintConfig:
    """Configuration for a profitability sprint run.

    Parameters
    ----------
    enable_pairwise : bool
        If True, enable pairwise comparison between factor candidates
        to select the strongest signals and reduce redundant factors.
    pairwise_min_ic_ir : float
        Minimum IC/IR threshold for a factor to be considered in
        pairwise ranking. Factors below this are excluded from
        pairwise comparison. Used only when enable_pairwise is True.
    """

    symbols: list[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"])
    modes: list[str] = field(default_factory=lambda: ["SCALP"])
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    data_dir: str = "data_lake"
    output_dir: str = "reports/alphaforge/profit_sprint"
    fee_bps: float = 4.0
    slippage_bps: float = 1.0
    min_trades: int = 200
    min_positive_folds: int = 4
    min_expectancy_r: float = 0.0
    min_profit_factor: float = 1.10
    max_drawdown_pct: float = 0.30
    enable_pairwise: bool = False  # Enable pairwise comparison between factor candidates; eliminates redundant/dominated factors before final gate
    pairwise_min_ic_ir: float = 0.05  # Minimum IC/IR for pairwise ranking; factors below this threshold are excluded
    horizon: int = 1  # Forward-return horizon in bars (1, 4, 12, 24)
