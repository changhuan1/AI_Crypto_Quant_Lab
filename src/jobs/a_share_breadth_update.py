from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from src.features.a_share_breadth import BREADTH_ASSET_ID, calculate_a_share_breadth
from src.jobs.a_share_market_update import build_a_share_market_features, load_a_share_market_prices


DB_PATH = Path("data/db/quant_lab.duckdb")

BREADTH_COLUMNS = [
    "universe_count",
    "up_count",
    "down_count",
    "flat_count",
    "up_ratio",
    "down_ratio",
    "above_ma_120_ratio",
    "median_ret_1d",
    "avg_ret_20d",
    "turnover_total",
    "turnover_median",
    "turnover_total_ma20",
    "turnover_expansion",
    "breadth_score",
]


def to_feature_store_rows(breadth: pd.DataFrame) -> pd.DataFrame:
    if breadth.empty:
        return breadth

    rows = breadth.melt(
        id_vars=["asset_id", "date"],
        value_vars=BREADTH_COLUMNS,
        var_name="feature_name",
        value_name="value",
    )
    rows = rows.dropna(subset=["value"]).copy()
    rows["created_at"] = datetime.now(timezone.utc)
    return rows[["asset_id", "date", "feature_name", "value", "created_at"]]


def save_breadth_features(feature_rows: pd.DataFrame, db_path: Path = DB_PATH) -> None:
    if feature_rows.empty:
        return

    with duckdb.connect(str(db_path)) as con:
        con.register("features_temp", feature_rows)
        con.execute(
            """
            INSERT OR REPLACE INTO features_daily
            SELECT asset_id, date, feature_name, value, created_at
            FROM features_temp
            """
        )


def latest_summary(breadth: pd.DataFrame) -> dict:
    if breadth.empty:
        return {}
    latest = breadth.sort_values("date").iloc[-1]
    return {
        "date": latest["date"],
        "universe_count": int(latest["universe_count"]),
        "up_ratio": float(latest["up_ratio"]) if pd.notna(latest["up_ratio"]) else None,
        "above_ma_120_ratio": (
            float(latest["above_ma_120_ratio"])
            if pd.notna(latest["above_ma_120_ratio"])
            else None
        ),
        "breadth_score": float(latest["breadth_score"]) if pd.notna(latest["breadth_score"]) else None,
    }


def main() -> None:
    prices = load_a_share_market_prices()
    if prices.empty:
        raise RuntimeError(
            "No A-share market prices found. Run: python -m src.data_ingestion.a_share_market_prices"
        )

    features = build_a_share_market_features(prices)
    breadth = calculate_a_share_breadth(features)
    feature_rows = to_feature_store_rows(breadth)
    save_breadth_features(feature_rows)

    summary = latest_summary(breadth)
    print(f"A-share breadth features saved: {len(feature_rows)} rows")
    if summary:
        print(f"Breadth asset_id: {BREADTH_ASSET_ID}")
        print(f"Latest date: {summary['date']}")
        print(f"Universe count: {summary['universe_count']}")
        print(f"Up ratio: {summary['up_ratio']:.4f}")
        print(f"Above MA120 ratio: {summary['above_ma_120_ratio']:.4f}")
        print(f"Breadth score: {summary['breadth_score']:.4f}")


if __name__ == "__main__":
    main()
