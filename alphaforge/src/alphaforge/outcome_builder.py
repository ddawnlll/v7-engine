# Mini builder for the diagnostic run
import pandas as pd
from pathlib import Path

def build_candidate_outcome_dataset(sim_output_dir: Path) -> pd.DataFrame:
    """Read SimulationOutput CSV files (one per symbol) and return a DataFrame.

    The resulting DataFrame contains the minimal fields needed for the IC
    diagnostic:
        - symbol
        - ts (timestamp)
        - side (LONG/SHORT/NO_TRADE)
        - mode (SCALP/AGGRESSIVE_SCALP/SWING)
        - timeframe
        - net_R, cost_R, gross_R
        - MFE, MAE
        - exit_flag (stop/target/horizon hit indicator)
    """
    dfs = []
    for csv in sim_output_dir.glob("*.csv"):
        df = pd.read_csv(csv)
        df["symbol"] = csv.stem
        dfs.append(df)
    if not dfs:
        raise FileNotFoundError(f"No SimulationOutput CSV files found in {sim_output_dir}")
    return pd.concat(dfs, ignore_index=True)
