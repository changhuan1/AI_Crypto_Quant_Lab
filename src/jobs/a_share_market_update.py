from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from src.features.price_features import add_price_features
from src.features.relative_strength import add_relative_strength
from src.features.risk_regime import classify_a_share_market_risk_regime


DB_PATH = Path("data/db/quant_lab.duckdb")
BENCHMARK_ASSET_ID = "A_INDEX_000001"

FEATURE_COLUMNS = [
    "ret_1d",
    "ret_7d",
    "ret_20d",
    "ret_60d",
    "ma_20",
    "ma_60",
    "ma_120",
    "above_ma_120",
    "volatility_20d",
    "volatility_60d",
    "relative_strength_20d",
]


def load_a_share_market_prices(db_path: Path = DB_PATH) -> pd.DataFrame:
    with duckdb.connect(str(db_path)) as con:
        return con.execute(
            """
            SELECT *
            FROM prices_daily
            WHERE asset_id LIKE 'A_STOCK_%'
               OR asset_id = 'A_INDEX_000001'
            ORDER BY asset_id, date
            """
        ).df()


def build_a_share_market_features(prices: pd.DataFrame) -> pd.DataFrame:
    features = add_price_features(prices)
    return add_relative_strength(features, benchmark_asset_id=BENCHMARK_ASSET_ID, window=20)


def to_feature_store_rows(features: pd.DataFrame) -> pd.DataFrame:
    rows = features.melt(
        id_vars=["asset_id", "date"],
        value_vars=FEATURE_COLUMNS,
        var_name="feature_name",
        value_name="value",
    )
    rows = rows.dropna(subset=["value"]).copy()
    rows["created_at"] = datetime.now(timezone.utc)
    return rows[["asset_id", "date", "feature_name", "value", "created_at"]]


def save_features(feature_rows: pd.DataFrame, db_path: Path = DB_PATH) -> None:
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


def main() -> None:
    prices = load_a_share_market_prices()
    if prices.empty:
        raise RuntimeError(
            "No A-share market prices found. Run: python -m src.data_ingestion.a_share_market_prices"
        )

    features = build_a_share_market_features(prices)
    feature_rows = to_feature_store_rows(features)
    save_features(feature_rows)

    regime = classify_a_share_market_risk_regime(features)
    print(f"A-share market features saved: {len(feature_rows)} rows")
    print(f"A-share market risk regime: {regime}")


if __name__ == "__main__":
    main()
