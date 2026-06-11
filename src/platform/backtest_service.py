from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from src.backtest.metrics import calculate_metrics
from src.features.risk_regime import classify_a_share_market_risk_regime
from src.jobs.a_share_market_update import build_a_share_market_features
from src.jobs.init_db import DB_PATH
from src.platform.backtest_engine import backtest_target_weights
from src.platform.data_api import DataPortal
from src.platform.models import BacktestRequest, BacktestResult
from src.platform.repository import ensure_platform_ready, get_strategy
from src.platform.strategy_templates import A_SHARE_MOMENTUM_TEMPLATE_ID, merge_config
from src.strategies.a_share_market_scoring import calculate_a_share_market_score


def run_backtest(request: BacktestRequest, db_path: Path = DB_PATH) -> BacktestResult:
    ensure_platform_ready(db_path)
    strategy = get_strategy(request.strategy_id, db_path)
    started_at = datetime.now(timezone.utc)
    run_id = f"bt_{started_at.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    config = merge_config(strategy.config, request.config_overrides)

    try:
        if strategy.template_id != A_SHARE_MOMENTUM_TEMPLATE_ID:
            raise ValueError(f"Unsupported strategy template: {strategy.template_id}")

        data = DataPortal(db_path)
        prices = data.load_a_share_market_prices(
            start_date=request.start_date.isoformat() if request.start_date else None,
            end_date=request.end_date.isoformat() if request.end_date else None,
        )
        asset_status = data.load_asset_status(
            start_date=request.start_date.isoformat() if request.start_date else None,
            end_date=request.end_date.isoformat() if request.end_date else None,
        )
        if prices.empty:
            raise RuntimeError(
                "没有找到 A 股价格数据。请先运行数据更新，或在数据中心确认 prices_daily 已有 A_STOCK 数据。"
            )

        features = build_a_share_market_features(prices)
        scores = calculate_a_share_market_score(features)
        signals = generate_a_share_momentum_signals(scores, strategy.strategy_id, config)
        if signals.empty:
            raise RuntimeError("策略没有生成任何调仓信号，请检查数据区间和特征是否足够。")

        ledger = backtest_target_weights(
            prices=prices,
            signals=signals.loc[signals["asset_id"] != "CASH"].copy(),
            run_id=run_id,
            strategy_id=strategy.strategy_id,
            initial_cash=request.initial_cash,
            fee_rate=float(config.get("fee_rate", 0.001)),
            asset_status=asset_status,
            execution_delay_days=int(config.get("execution_delay_days", 1)),
        )

        benchmark_nav = _run_benchmark(
            prices=prices,
            run_id=run_id,
            strategy_id=f"{strategy.strategy_id}_benchmark",
            initial_cash=request.initial_cash,
            fee_rate=float(config.get("fee_rate", 0.001)),
            benchmark_asset_id=str(config.get("benchmark_asset_id", "A_INDEX_000001")),
            asset_status=asset_status,
        )
        nav = _attach_benchmark(ledger.nav, benchmark_nav)
        metrics = calculate_metrics(nav, periods_per_year=252)
        benchmark_metrics = calculate_metrics(benchmark_nav, periods_per_year=252)
        metrics.update({f"benchmark_{key}": value for key, value in benchmark_metrics.items()})

        finished_at = datetime.now(timezone.utc)
        _save_successful_run(
            db_path=db_path,
            run_id=run_id,
            strategy_id=strategy.strategy_id,
            strategy_name=strategy.name,
            request=request,
            config=config,
            started_at=started_at,
            finished_at=finished_at,
            signals=signals,
            nav=nav,
            positions=ledger.positions,
            orders=ledger.orders,
            trades=ledger.trades,
            metrics=metrics,
        )
        return BacktestResult(
            run_id=run_id,
            strategy_id=strategy.strategy_id,
            strategy_name=strategy.name,
            status="success",
            metrics=metrics,
            started_at=started_at,
            finished_at=finished_at,
            message="backtest completed",
        )
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        _save_failed_run(
            db_path=db_path,
            run_id=run_id,
            strategy_id=strategy.strategy_id,
            strategy_name=strategy.name,
            request=request,
            config=config,
            started_at=started_at,
            finished_at=finished_at,
            error_message=str(exc),
        )
        raise


def generate_a_share_momentum_signals(
    scores: pd.DataFrame,
    strategy_id: str,
    config: dict[str, Any],
) -> pd.DataFrame:
    records = []
    for date_value, frame in scores.groupby("date", sort=True):
        if not _is_rebalance_date(date_value, config):
            continue

        history = scores.loc[scores["date"] <= date_value]
        regime = classify_a_share_market_risk_regime(history)
        targets = _generate_targets(frame, regime, config)
        for asset_id, weight in targets.items():
            score = _score_for_asset(frame, asset_id)
            records.append(
                {
                    "asset_id": asset_id,
                    "date": date_value,
                    "strategy": strategy_id,
                    "score": score,
                    "signal": "hold_cash" if asset_id == "CASH" else "target_weight",
                    "target_weight": weight,
                    "risk_flag": regime in {"risk_off", "unknown"},
                    "reason": _build_reason(asset_id, regime, score, config),
                    "created_at": datetime.now(timezone.utc),
                }
            )
    return pd.DataFrame(records)


def _is_rebalance_date(date_value, config: dict[str, Any]) -> bool:
    frequency = config.get("rebalance_frequency", "weekly_friday")
    if frequency == "daily":
        return True
    return pd.Timestamp(date_value).weekday() == 4


def _generate_targets(
    scores: pd.DataFrame,
    market_regime: str,
    config: dict[str, Any],
) -> dict[str, float]:
    latest = scores.loc[scores["asset_id"].str.startswith("A_STOCK_")].copy()
    if latest.empty or market_regime in {"risk_off", "unknown"}:
        return {"CASH": 1.0}

    max_exposure = (
        float(config.get("neutral_max_exposure", 0.50))
        if market_regime == "neutral"
        else float(config.get("risk_on_max_exposure", 0.80))
    )
    min_turnover_quantile = float(config.get("min_turnover_quantile", 0.50))
    min_turnover = latest["turnover"].quantile(min_turnover_quantile)

    candidates = latest.dropna(subset=["a_share_market_score"]).copy()
    if config.get("require_above_ma120", True):
        candidates = candidates.loc[candidates["above_ma_120"] == 1]
    candidates = candidates.loc[candidates["turnover"] >= min_turnover]
    candidates = candidates.sort_values("a_share_market_score", ascending=False)
    candidates = candidates.head(int(config.get("top_n", 30)))

    if candidates.empty:
        return {"CASH": 1.0}

    weight = min(float(config.get("max_single_position", 0.03)), max_exposure / len(candidates))
    targets = {row["asset_id"]: weight for _, row in candidates.iterrows()}
    targets["CASH"] = max(0.0, 1.0 - sum(targets.values()))
    return targets


def _score_for_asset(scores: pd.DataFrame, asset_id: str) -> float | None:
    if asset_id == "CASH":
        return None
    match = scores.loc[scores["asset_id"] == asset_id, "a_share_market_score"]
    if match.empty or pd.isna(match.iloc[0]):
        return None
    return float(match.iloc[0])


def _build_reason(
    asset_id: str,
    market_regime: str,
    score: float | None,
    config: dict[str, Any],
) -> str:
    if asset_id == "CASH":
        return f"市场状态={market_regime}，保留现金"
    return (
        f"市场状态={market_regime}；评分={score:.4f}；"
        f"进入前{int(config.get('top_n', 30))}；满足均线与流动性过滤"
    )


def _run_benchmark(
    prices: pd.DataFrame,
    run_id: str,
    strategy_id: str,
    initial_cash: float,
    fee_rate: float,
    benchmark_asset_id: str,
    asset_status: pd.DataFrame | None = None,
) -> pd.DataFrame:
    benchmark = prices.loc[prices["asset_id"] == benchmark_asset_id].sort_values("date").copy()
    benchmark = benchmark.dropna(subset=["close"])
    if benchmark.empty:
        return pd.DataFrame()
    benchmark["date"] = pd.to_datetime(benchmark["date"]).dt.date
    first_close = benchmark["close"].iloc[0]
    benchmark["nav"] = benchmark["close"] / first_close * initial_cash
    benchmark["cash"] = 0.0
    benchmark["gross_exposure"] = 1.0
    benchmark["return"] = benchmark["nav"].pct_change().fillna(0.0)
    benchmark["cummax"] = benchmark["nav"].cummax()
    benchmark["drawdown"] = benchmark["nav"] / benchmark["cummax"] - 1
    return benchmark[["date", "nav", "cash", "gross_exposure", "return", "cummax", "drawdown"]]


def _attach_benchmark(nav: pd.DataFrame, benchmark_nav: pd.DataFrame) -> pd.DataFrame:
    if nav.empty or benchmark_nav.empty:
        result = nav.copy()
        result["benchmark_nav"] = None
        return result

    benchmark = benchmark_nav[["date", "nav"]].rename(columns={"nav": "benchmark_nav"})
    return nav.merge(benchmark, on="date", how="left")


def _save_successful_run(
    db_path: Path,
    run_id: str,
    strategy_id: str,
    strategy_name: str,
    request: BacktestRequest,
    config: dict[str, Any],
    started_at: datetime,
    finished_at: datetime,
    signals: pd.DataFrame,
    nav: pd.DataFrame,
    positions: pd.DataFrame,
    orders: pd.DataFrame,
    trades: pd.DataFrame,
    metrics: dict[str, float],
) -> None:
    _save_run(
        db_path,
        run_id,
        strategy_id,
        strategy_name,
        "backtest",
        "success",
        request,
        config,
        started_at,
        finished_at,
        None,
    )
    _save_signals(db_path, signals)
    _save_nav(db_path, run_id, strategy_id, nav)
    _save_legacy_portfolio_nav(db_path, strategy_id, nav)
    _save_table(db_path, "positions_daily", positions)
    _save_table(db_path, "orders", orders)
    _save_table(db_path, "trades", trades)
    _save_metrics(db_path, run_id, metrics)


def _save_failed_run(
    db_path: Path,
    run_id: str,
    strategy_id: str,
    strategy_name: str,
    request: BacktestRequest,
    config: dict[str, Any],
    started_at: datetime,
    finished_at: datetime,
    error_message: str,
) -> None:
    _save_run(
        db_path,
        run_id,
        strategy_id,
        strategy_name,
        "backtest",
        "failed",
        request,
        config,
        started_at,
        finished_at,
        error_message,
    )


def _save_run(
    db_path: Path,
    run_id: str,
    strategy_id: str,
    strategy_name: str,
    run_type: str,
    status: str,
    request: BacktestRequest,
    config: dict[str, Any],
    started_at: datetime,
    finished_at: datetime,
    error_message: str | None,
) -> None:
    row = pd.DataFrame(
        [
            {
                "run_id": run_id,
                "strategy_id": strategy_id,
                "strategy_name": strategy_name,
                "run_type": run_type,
                "status": status,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "initial_cash": request.initial_cash,
                "config_json": json.dumps(config, ensure_ascii=False),
                "started_at": started_at,
                "finished_at": finished_at,
                "error_message": error_message,
            }
        ]
    )
    _save_table(db_path, "strategy_runs", row)


def _save_signals(db_path: Path, signals: pd.DataFrame) -> None:
    if signals.empty:
        return
    _save_table(db_path, "signals_daily", signals)


def _save_nav(db_path: Path, run_id: str, strategy_id: str, nav: pd.DataFrame) -> None:
    if nav.empty:
        return
    rows = nav.copy()
    rows["run_id"] = run_id
    rows["strategy_id"] = strategy_id
    rows["created_at"] = datetime.now(timezone.utc)
    rows = rows[
        [
            "run_id",
            "date",
            "strategy_id",
            "nav",
            "cash",
            "gross_exposure",
            "drawdown",
            "benchmark_nav",
            "created_at",
        ]
    ]
    _save_table(db_path, "backtest_nav", rows)


def _save_legacy_portfolio_nav(db_path: Path, strategy_id: str, nav: pd.DataFrame) -> None:
    if nav.empty:
        return
    rows = nav.copy()
    rows["strategy"] = strategy_id
    rows["max_drawdown"] = rows["drawdown"].cummin()
    rows["created_at"] = datetime.now(timezone.utc)
    rows = rows[["date", "strategy", "nav", "cash", "gross_exposure", "max_drawdown", "created_at"]]
    _save_table(db_path, "portfolio_nav", rows)


def _save_metrics(db_path: Path, run_id: str, metrics: dict[str, float]) -> None:
    rows = pd.DataFrame(
        [
            {
                "run_id": run_id,
                "metric_name": name,
                "metric_value": value,
                "created_at": datetime.now(timezone.utc),
            }
            for name, value in metrics.items()
        ]
    )
    _save_table(db_path, "strategy_run_metrics", rows)


def _save_table(db_path: Path, table: str, rows: pd.DataFrame) -> None:
    if rows.empty:
        return
    with duckdb.connect(str(db_path)) as con:
        con.register("rows_to_save", rows)
        con.execute(f"INSERT OR REPLACE INTO {table} SELECT * FROM rows_to_save")
