from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from src.backtest.metrics import calculate_metrics
from src.backtest.simple_rebalance_backtest import backtest_rebalance
from src.features.risk_regime import classify_a_share_market_risk_regime
from src.jobs.a_share_market_update import build_a_share_market_features, load_a_share_market_prices
from src.strategies.a_share_market_scoring import calculate_a_share_market_score
from src.strategies.a_share_rotation import generate_a_share_targets


DB_PATH = Path("data/db/quant_lab.duckdb")
STRATEGY_NAME = "a_share_market_rotation_v0"
BENCHMARK_ASSET_ID = "A_INDEX_000001"


def is_weekly_rebalance_date(date_value) -> bool:
    return pd.Timestamp(date_value).weekday() == 4


def generate_weekly_a_share_signals(scores: pd.DataFrame) -> pd.DataFrame:
    records = []

    for date, frame in scores.groupby("date", sort=True):
        if not is_weekly_rebalance_date(date):
            continue

        regime = classify_a_share_market_risk_regime(scores.loc[scores["date"] <= date])
        targets = generate_a_share_targets(frame, regime)

        for asset_id, weight in targets.items():
            records.append(
                {
                    "asset_id": asset_id,
                    "date": date,
                    "strategy": STRATEGY_NAME,
                    "score": None if asset_id == "CASH" else _score_for_asset(frame, asset_id),
                    "signal": "hold_cash" if asset_id == "CASH" else "target_weight",
                    "target_weight": weight,
                    "risk_flag": regime in {"risk_off", "unknown"},
                    "reason": f"a_share_market_regime={regime}",
                    "created_at": datetime.now(timezone.utc),
                }
            )

    return pd.DataFrame(records)


def _score_for_asset(scores: pd.DataFrame, asset_id: str) -> float | None:
    match = scores.loc[scores["asset_id"] == asset_id, "a_share_market_score"]
    if match.empty or pd.isna(match.iloc[0]):
        return None
    return float(match.iloc[0])


def _latest_signal_date(signals: pd.DataFrame) -> object | None:
    if signals.empty:
        return None
    return signals["date"].max()


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
    asset_id: str = BENCHMARK_ASSET_ID,
    weight: float = 1.0,
) -> pd.DataFrame:
    first_date = prices.loc[prices["asset_id"] == asset_id, "date"].min()
    if pd.isna(first_date):
        return pd.DataFrame()

    return pd.DataFrame([{"asset_id": asset_id, "date": first_date, "target_weight": weight}])


def main() -> None:
    prices = load_a_share_market_prices()
    if prices.empty:
        raise RuntimeError(
            "No A-share market prices found. Run: python -m src.data_ingestion.a_share_market_prices"
        )

    features = build_a_share_market_features(prices)
    scores = calculate_a_share_market_score(features)
    signals = generate_weekly_a_share_signals(scores)
    save_signals(signals)

    tradable_signals = signals.loc[signals["asset_id"] != "CASH"].copy()
    nav = backtest_rebalance(prices, tradable_signals)
    save_nav(nav, STRATEGY_NAME)

    benchmark_signals = build_buy_and_hold_signals(prices)
    benchmark_nav = backtest_rebalance(prices, benchmark_signals)

    metrics = calculate_metrics(nav, periods_per_year=252)
    benchmark_metrics = calculate_metrics(benchmark_nav, periods_per_year=252)

    print(f"A-share market signals saved: {len(signals)} rows")
    latest_date = _latest_signal_date(signals)
    if latest_date is not None:
        latest_targets = signals.loc[
            (signals["date"] == latest_date) & (signals["asset_id"] != "CASH")
        ].sort_values("score", ascending=False)
        print(f"Latest rebalance date: {latest_date}")
        print("Latest selected stocks:")
        print(latest_targets[["asset_id", "score", "target_weight", "reason"]].head(30).to_string(index=False))
    print(f"Backtest rows: {len(nav)}")
    print("Strategy metrics:")
    for name, value in metrics.items():
        print(f"{name}: {value:.4f}")
    print("Benchmark buy-and-hold metrics:")
    for name, value in benchmark_metrics.items():
        print(f"{name}: {value:.4f}")


if __name__ == "__main__":
    main()
