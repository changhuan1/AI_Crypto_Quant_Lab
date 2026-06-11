from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from src.jobs.init_db import DB_PATH


DEFAULT_FACTOR_COLUMNS = [
    "ret_20d",
    "ret_60d",
    "relative_strength_20d",
    "volatility_20d",
    "turnover",
    "a_share_market_score",
]


def calculate_factor_research(
    factor_frame: pd.DataFrame,
    prices: pd.DataFrame,
    factor_columns: list[str] | None = None,
    horizons: list[int] | None = None,
    quantiles: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    factor_columns = factor_columns or DEFAULT_FACTOR_COLUMNS
    horizons = horizons or [1, 5, 20]

    stocks = prices.loc[prices["asset_id"].str.startswith("A_STOCK_")].copy()
    stocks = stocks.sort_values(["asset_id", "date"])
    for horizon in horizons:
        stocks[f"forward_return_{horizon}d"] = (
            stocks.groupby("asset_id")["close"].shift(-horizon) / stocks["close"] - 1
        )

    base_columns = ["asset_id", "date"] + [f"forward_return_{horizon}d" for horizon in horizons]
    research = factor_frame.merge(stocks[base_columns], on=["asset_id", "date"], how="inner")
    research = research.loc[research["asset_id"].str.startswith("A_STOCK_")].copy()

    ic_rows = []
    quantile_rows = []
    created_at = datetime.now(timezone.utc)

    for factor_name in factor_columns:
        if factor_name not in research.columns:
            continue
        for horizon in horizons:
            return_col = f"forward_return_{horizon}d"
            for date_value, frame in research.groupby("date"):
                sample = frame[[factor_name, return_col]].dropna()
                if len(sample) < 5:
                    continue
                ic = sample[factor_name].corr(sample[return_col], method="pearson")
                rank_ic = sample[factor_name].corr(sample[return_col], method="spearman")
                ic_rows.append(
                    {
                        "factor_name": factor_name,
                        "horizon": horizon,
                        "date": date_value,
                        "ic": None if pd.isna(ic) else float(ic),
                        "rank_ic": None if pd.isna(rank_ic) else float(rank_ic),
                        "asset_count": len(sample),
                        "created_at": created_at,
                    }
                )

                quantile_frame = _assign_quantiles(sample, factor_name, quantiles)
                if quantile_frame.empty:
                    continue
                grouped = quantile_frame.groupby("quantile")[return_col].agg(["mean", "count"]).reset_index()
                for _, row in grouped.iterrows():
                    quantile_rows.append(
                        {
                            "factor_name": factor_name,
                            "horizon": horizon,
                            "date": date_value,
                            "quantile": int(row["quantile"]),
                            "mean_forward_return": float(row["mean"]),
                            "asset_count": int(row["count"]),
                            "created_at": created_at,
                        }
                    )

    return pd.DataFrame(ic_rows), pd.DataFrame(quantile_rows)


def summarize_factor_ic(ic: pd.DataFrame) -> pd.DataFrame:
    if ic.empty:
        return pd.DataFrame()
    return (
        ic.groupby(["factor_name", "horizon"])
        .agg(
            ic_mean=("ic", "mean"),
            rank_ic_mean=("rank_ic", "mean"),
            ic_win_rate=("ic", lambda values: float((values > 0).mean())),
            rank_ic_win_rate=("rank_ic", lambda values: float((values > 0).mean())),
            observations=("ic", "count"),
            avg_asset_count=("asset_count", "mean"),
        )
        .reset_index()
        .sort_values(["horizon", "rank_ic_mean"], ascending=[True, False])
    )


def save_factor_research(
    ic: pd.DataFrame,
    quantile_returns: pd.DataFrame,
    db_path: Path = DB_PATH,
) -> None:
    with duckdb.connect(str(db_path)) as con:
        if not ic.empty:
            con.register("factor_ic_rows", ic)
            con.execute("INSERT OR REPLACE INTO factor_ic_daily SELECT * FROM factor_ic_rows")
        if not quantile_returns.empty:
            con.register("factor_quantile_rows", quantile_returns)
            con.execute(
                """
                INSERT OR REPLACE INTO factor_quantile_returns
                SELECT *
                FROM factor_quantile_rows
                """
            )


def latest_factor_ic_summary(db_path: Path = DB_PATH) -> pd.DataFrame:
    with duckdb.connect(str(db_path)) as con:
        ic = con.execute("SELECT * FROM factor_ic_daily").df()
    return summarize_factor_ic(ic)


def _assign_quantiles(sample: pd.DataFrame, factor_name: str, quantiles: int) -> pd.DataFrame:
    if sample[factor_name].nunique(dropna=True) < 2:
        return pd.DataFrame()
    result = sample.copy()
    try:
        result["quantile"] = pd.qcut(
            result[factor_name].rank(method="first"),
            q=quantiles,
            labels=False,
            duplicates="drop",
        )
    except ValueError:
        return pd.DataFrame()
    result["quantile"] = result["quantile"].astype(int) + 1
    return result

