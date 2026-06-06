from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from src.backtest.metrics import calculate_metrics
from src.backtest.simple_rebalance_backtest import backtest_rebalance
from src.features.risk_regime import classify_btc_risk_regime
from src.jobs.crypto_update import build_crypto_features, load_crypto_prices
from src.strategies.crypto_rotation import generate_crypto_targets
from src.strategies.crypto_scoring import calculate_crypto_score


DB_PATH = Path("data/db/quant_lab.duckdb")


def generate_daily_crypto_signals(scores: pd.DataFrame) -> pd.DataFrame:
    records = []

    for date, frame in scores.groupby("date", sort=True):
        regime = classify_btc_risk_regime(scores.loc[scores["date"] <= date])
        targets = generate_crypto_targets(frame, regime)

        for asset_id, weight in targets.items():
            records.append(
                {
                    "asset_id": asset_id,
                    "date": date,
                    "strategy": "crypto_spot_rotation_v0",
                    "score": None if asset_id == "CASH" else _score_for_asset(frame, asset_id),
                    "signal": "hold_cash" if asset_id == "CASH" else "target_weight",
                    "target_weight": weight,
                    "risk_flag": regime == "risk_off",
                    "reason": f"crypto_regime={regime}",
                    "created_at": datetime.now(timezone.utc),
                }
            )

    return pd.DataFrame(records)


def _score_for_asset(scores: pd.DataFrame, asset_id: str) -> float | None:
    match = scores.loc[scores["asset_id"] == asset_id, "crypto_score"]
    if match.empty or pd.isna(match.iloc[0]):
        return None
    return float(match.iloc[0])


def save_signals(signals: pd.DataFrame, db_path: Path = DB_PATH) -> None:
    if signals.empty:
        return

    with duckdb.connect(str(db_path)) as con:
        con.register("signals_temp", signals)
        con.execute(
            """
            INSERT OR REPLACE INTO signals_daily
            SELECT
                asset_id,
                date,
                strategy,
                score,
                signal,
                target_weight,
                risk_flag,
                reason,
                created_at
            FROM signals_temp
            """
        )


def save_nav(nav: pd.DataFrame, strategy: str, db_path: Path = DB_PATH) -> None:
    if nav.empty:
        return

    rows = nav.copy()
    rows["strategy"] = strategy
    if "cash" not in rows.columns:
        rows["cash"] = 0.0
    if "gross_exposure" not in rows.columns:
        rows["gross_exposure"] = 1.0
    rows["max_drawdown"] = rows["drawdown"].cummin()
    rows["created_at"] = datetime.now(timezone.utc)
    rows = rows[["date", "strategy", "nav", "cash", "gross_exposure", "max_drawdown", "created_at"]]

    with duckdb.connect(str(db_path)) as con:
        con.register("nav_temp", rows)
        con.execute(
            """
            INSERT OR REPLACE INTO portfolio_nav
            SELECT date, strategy, nav, cash, gross_exposure, max_drawdown, created_at
            FROM nav_temp
            """
        )


def build_buy_and_hold_signals(
    prices: pd.DataFrame,
    asset_id: str = "CRYPTO_BTC_USDT",
    weight: float = 1.0,
) -> pd.DataFrame:
    first_date = prices.loc[prices["asset_id"] == asset_id, "date"].min()
    if pd.isna(first_date):
        return pd.DataFrame()

    return pd.DataFrame(
        [
            {
                "asset_id": asset_id,
                "date": first_date,
                "target_weight": weight,
            }
        ]
    )


def main() -> None:
    prices = load_crypto_prices()
    if prices.empty:
        raise RuntimeError("No crypto prices found. Run: python -m src.data_ingestion.crypto_prices_ccxt")

    features = build_crypto_features(prices)
    scores = calculate_crypto_score(features)
    signals = generate_daily_crypto_signals(scores)
    save_signals(signals)

    tradable_signals = signals.loc[signals["asset_id"] != "CASH"].copy()
    nav = backtest_rebalance(prices, tradable_signals)
    save_nav(nav, "crypto_spot_rotation_v0")

    btc_signals = build_buy_and_hold_signals(prices)
    btc_nav = backtest_rebalance(prices, btc_signals)

    metrics = calculate_metrics(nav)
    btc_metrics = calculate_metrics(btc_nav)
    print(f"Crypto signals saved: {len(signals)} rows")
    print(f"Backtest rows: {len(nav)}")
    print("Strategy metrics:")
    for name, value in metrics.items():
        print(f"{name}: {value:.4f}")
    print("BTC buy-and-hold metrics:")
    for name, value in btc_metrics.items():
        print(f"{name}: {value:.4f}")


if __name__ == "__main__":
    main()
