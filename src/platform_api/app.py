from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import os
import subprocess
import sys
import threading
from typing import Any
from uuid import uuid4

import duckdb
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.jobs.init_db import DB_PATH
from src.platform.backtest_service import run_backtest
from src.platform.data_api import DataPortal
from src.platform.data_quality import latest_data_quality_report, refresh_data_quality_report
from src.platform.factor_research import latest_factor_ic_summary
from src.platform.models import BacktestRequest
from src.platform.repository import ensure_platform_ready, list_strategies


app = FastAPI(title="Quant Platform API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PULL_LOG_DIR = PROJECT_ROOT / "data" / "logs" / "data_pulls"
DATA_PULL_LOCK = threading.Lock()
DATA_PULL_STATE: dict[str, Any] = {
    "job_id": None,
    "status": "idle",
    "dataset": "a_share_prices",
    "start_date": None,
    "end_date": None,
    "limit": None,
    "started_at": None,
    "finished_at": None,
    "return_code": None,
    "message": "尚未启动数据拉取任务",
    "log_path": None,
    "process": None,
}


DATASET_PREVIEWS: dict[str, dict[str, str]] = {
    "assets": {
        "label": "资产主数据",
        "description": "股票、指数、加密资产等基础信息，包含代码、名称、市场、资产类型与是否启用。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM assets",
        "preview_sql": """
            SELECT asset_id, symbol AS asset_code, name AS asset_name, market, asset_type, theme,
                   is_active, liquidity_tier, created_at
            FROM assets
            ORDER BY market, asset_type, symbol
            LIMIT ?
        """,
    },
    "prices_daily": {
        "label": "日线行情",
        "description": "策略研究和回测使用的 OHLCV 日线行情，默认按最新日期优先展示。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM prices_daily",
        "preview_sql": """
            SELECT
                p.date,
                p.asset_id,
                CASE
                    WHEN p.asset_id LIKE 'A_STOCK_%' THEN REPLACE(p.asset_id, 'A_STOCK_', '')
                    WHEN p.asset_id LIKE 'A_INDEX_%' THEN REPLACE(p.asset_id, 'A_INDEX_', '')
                    WHEN p.asset_id LIKE 'A_ETF_%' THEN REPLACE(p.asset_id, 'A_ETF_', '')
                    WHEN p.asset_id LIKE 'CRYPTO_%' THEN REPLACE(p.asset_id, 'CRYPTO_', '')
                    ELSE p.asset_id
                END AS asset_code,
                COALESCE(a.name, p.asset_id) AS asset_name,
                p.open,
                p.high,
                p.low,
                p.close,
                p.volume,
                p.turnover,
                p.source,
                p.created_at
            FROM prices_daily p
            LEFT JOIN assets a ON p.asset_id = a.asset_id
            ORDER BY p.date DESC, p.asset_id
            LIMIT ?
        """,
    },
    "trading_calendar": {
        "label": "交易日历",
        "description": "交易所开闭市日历，以及前后交易日映射。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM trading_calendar",
        "preview_sql": """
            SELECT market, date, is_open, previous_open_date, next_open_date, source, created_at
            FROM trading_calendar
            ORDER BY date DESC, market
            LIMIT ?
        """,
    },
    "index_constituents_history": {
        "label": "指数成分历史",
        "description": "指数成分股和权重历史。当前 Tushare 权限不足时，这张表可能为空。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM index_constituents_history",
        "preview_sql": """
            SELECT
                c.index_id,
                c.date,
                c.asset_id,
                CASE
                    WHEN c.asset_id LIKE 'A_STOCK_%' THEN REPLACE(c.asset_id, 'A_STOCK_', '')
                    WHEN c.asset_id LIKE 'A_INDEX_%' THEN REPLACE(c.asset_id, 'A_INDEX_', '')
                    WHEN c.asset_id LIKE 'A_ETF_%' THEN REPLACE(c.asset_id, 'A_ETF_', '')
                    ELSE c.asset_id
                END AS asset_code,
                COALESCE(a.name, c.asset_id) AS asset_name,
                c.weight,
                c.source,
                c.created_at
            FROM index_constituents_history c
            LEFT JOIN assets a ON c.asset_id = a.asset_id
            ORDER BY c.date DESC, c.index_id, c.weight DESC
            LIMIT ?
        """,
    },
    "asset_status_daily": {
        "label": "股票交易状态",
        "description": "停牌、ST、涨跌停、上市天数等每日交易约束状态。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM asset_status_daily",
        "preview_sql": """
            SELECT
                s.date,
                s.asset_id,
                CASE
                    WHEN s.asset_id LIKE 'A_STOCK_%' THEN REPLACE(s.asset_id, 'A_STOCK_', '')
                    WHEN s.asset_id LIKE 'A_ETF_%' THEN REPLACE(s.asset_id, 'A_ETF_', '')
                    ELSE s.asset_id
                END AS asset_code,
                COALESCE(a.name, s.asset_id) AS asset_name,
                s.is_tradable,
                s.is_suspended,
                s.is_st,
                s.is_limit_up,
                s.is_limit_down,
                s.up_limit,
                s.down_limit,
                s.listed_days,
                s.source,
                s.created_at
            FROM asset_status_daily s
            LEFT JOIN assets a ON s.asset_id = a.asset_id
            ORDER BY s.date DESC, s.asset_id
            LIMIT ?
        """,
    },
    "features_daily": {
        "label": "价格与市场特征",
        "description": "由原始行情加工得到的特征，例如收益率、均线、波动率、动量等。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM features_daily",
        "preview_sql": """
            SELECT
                f.date,
                f.asset_id,
                CASE
                    WHEN f.asset_id LIKE 'A_STOCK_%' THEN REPLACE(f.asset_id, 'A_STOCK_', '')
                    WHEN f.asset_id LIKE 'A_INDEX_%' THEN REPLACE(f.asset_id, 'A_INDEX_', '')
                    WHEN f.asset_id LIKE 'A_ETF_%' THEN REPLACE(f.asset_id, 'A_ETF_', '')
                    WHEN f.asset_id LIKE 'CRYPTO_%' THEN REPLACE(f.asset_id, 'CRYPTO_', '')
                    ELSE f.asset_id
                END AS asset_code,
                COALESCE(a.name, f.asset_id) AS asset_name,
                f.feature_name,
                f.value,
                f.created_at
            FROM features_daily f
            LEFT JOIN assets a ON f.asset_id = a.asset_id
            ORDER BY f.date DESC, f.asset_id, f.feature_name
            LIMIT ?
        """,
    },
    "signals_daily": {
        "label": "策略信号",
        "description": "策略每日评分、信号、目标仓位与生成原因。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM signals_daily",
        "preview_sql": """
            SELECT
                s.date,
                s.strategy,
                s.asset_id,
                CASE
                    WHEN s.asset_id LIKE 'A_STOCK_%' THEN REPLACE(s.asset_id, 'A_STOCK_', '')
                    WHEN s.asset_id LIKE 'A_INDEX_%' THEN REPLACE(s.asset_id, 'A_INDEX_', '')
                    WHEN s.asset_id LIKE 'A_ETF_%' THEN REPLACE(s.asset_id, 'A_ETF_', '')
                    WHEN s.asset_id LIKE 'CRYPTO_%' THEN REPLACE(s.asset_id, 'CRYPTO_', '')
                    ELSE s.asset_id
                END AS asset_code,
                COALESCE(a.name, s.asset_id) AS asset_name,
                s.score,
                s.signal,
                s.target_weight,
                s.risk_flag,
                s.reason,
                s.created_at
            FROM signals_daily s
            LEFT JOIN assets a ON s.asset_id = a.asset_id
            ORDER BY s.date DESC, s.strategy, s.score DESC
            LIMIT ?
        """,
    },
    "data_quality_reports": {
        "label": "数据质量报告",
        "description": "数据覆盖率、缺失、状态字段完整性等检查结果。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM data_quality_reports",
        "preview_sql": """
            SELECT report_id, check_name, severity, asset_group, asset_id, date, metric_name,
                   metric_value, message, created_at
            FROM data_quality_reports
            ORDER BY created_at DESC, severity
            LIMIT ?
        """,
    },
    "factor_ic_daily": {
        "label": "因子 IC 明细",
        "description": "每日因子 IC 与 Rank IC，用来观察因子预测能力是否稳定。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM factor_ic_daily",
        "preview_sql": """
            SELECT factor_name, horizon, date, ic, rank_ic, asset_count, created_at
            FROM factor_ic_daily
            ORDER BY date DESC, factor_name, horizon
            LIMIT ?
        """,
    },
    "factor_quantile_returns": {
        "label": "因子分层收益",
        "description": "不同因子分位数组合的远期平均收益，用来判断因子单调性。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM factor_quantile_returns",
        "preview_sql": """
            SELECT factor_name, horizon, date, quantile, mean_forward_return, asset_count, created_at
            FROM factor_quantile_returns
            ORDER BY date DESC, factor_name, horizon, quantile
            LIMIT ?
        """,
    },
    "strategy_runs": {
        "label": "回测运行记录",
        "description": "每次回测或模拟运行的参数、状态与时间范围。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM strategy_runs",
        "preview_sql": """
            SELECT run_id, strategy_id, strategy_name, run_type, status, start_date, end_date,
                   initial_cash, started_at, finished_at, error_message
            FROM strategy_runs
            ORDER BY started_at DESC
            LIMIT ?
        """,
    },
    "orders": {
        "label": "订单账本",
        "description": "回测撮合生成的订单，包括方向、数量、金额、目标仓位和拒单原因。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM orders",
        "preview_sql": """
            SELECT
                o.date,
                o.run_id,
                o.strategy_id,
                o.asset_id,
                CASE
                    WHEN o.asset_id LIKE 'A_STOCK_%' THEN REPLACE(o.asset_id, 'A_STOCK_', '')
                    WHEN o.asset_id LIKE 'A_INDEX_%' THEN REPLACE(o.asset_id, 'A_INDEX_', '')
                    WHEN o.asset_id LIKE 'A_ETF_%' THEN REPLACE(o.asset_id, 'A_ETF_', '')
                    WHEN o.asset_id LIKE 'CRYPTO_%' THEN REPLACE(o.asset_id, 'CRYPTO_', '')
                    ELSE o.asset_id
                END AS asset_code,
                COALESCE(a.name, o.asset_id) AS asset_name,
                o.side,
                o.status,
                o.quantity,
                o.price,
                o.notional,
                o.target_weight,
                o.reason,
                o.created_at
            FROM orders o
            LEFT JOIN assets a ON o.asset_id = a.asset_id
            ORDER BY o.date DESC, o.notional DESC
            LIMIT ?
        """,
    },
    "positions_daily": {
        "label": "持仓账本",
        "description": "回测每日持仓、收盘价、市值与权重。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM positions_daily",
        "preview_sql": """
            SELECT
                p.date,
                p.run_id,
                p.strategy_id,
                p.asset_id,
                CASE
                    WHEN p.asset_id LIKE 'A_STOCK_%' THEN REPLACE(p.asset_id, 'A_STOCK_', '')
                    WHEN p.asset_id LIKE 'A_INDEX_%' THEN REPLACE(p.asset_id, 'A_INDEX_', '')
                    WHEN p.asset_id LIKE 'A_ETF_%' THEN REPLACE(p.asset_id, 'A_ETF_', '')
                    WHEN p.asset_id LIKE 'CRYPTO_%' THEN REPLACE(p.asset_id, 'CRYPTO_', '')
                    ELSE p.asset_id
                END AS asset_code,
                COALESCE(a.name, p.asset_id) AS asset_name,
                p.quantity,
                p.close_price,
                p.market_value,
                p.weight,
                p.created_at
            FROM positions_daily p
            LEFT JOIN assets a ON p.asset_id = a.asset_id
            ORDER BY p.date DESC, p.weight DESC
            LIMIT ?
        """,
    },
    "trades": {
        "label": "成交账本",
        "description": "回测中实际成交的交易明细和费用。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM trades",
        "preview_sql": """
            SELECT
                t.date,
                t.run_id,
                t.strategy_id,
                t.asset_id,
                CASE
                    WHEN t.asset_id LIKE 'A_STOCK_%' THEN REPLACE(t.asset_id, 'A_STOCK_', '')
                    WHEN t.asset_id LIKE 'A_INDEX_%' THEN REPLACE(t.asset_id, 'A_INDEX_', '')
                    WHEN t.asset_id LIKE 'A_ETF_%' THEN REPLACE(t.asset_id, 'A_ETF_', '')
                    WHEN t.asset_id LIKE 'CRYPTO_%' THEN REPLACE(t.asset_id, 'CRYPTO_', '')
                    ELSE t.asset_id
                END AS asset_code,
                COALESCE(a.name, t.asset_id) AS asset_name,
                t.side,
                t.quantity,
                t.price,
                t.notional,
                t.fee,
                t.created_at
            FROM trades t
            LEFT JOIN assets a ON t.asset_id = a.asset_id
            ORDER BY t.date DESC, t.notional DESC
            LIMIT ?
        """,
    },
}


class BacktestPayload(BaseModel):
    strategy_id: str
    start_date: date | None = None
    end_date: date | None = None
    initial_cash: float = Field(default=100_000.0, ge=1_000)
    top_n: int = Field(default=30, ge=1, le=200)
    max_single_position: float = Field(default=0.03, ge=0.001, le=1.0)
    fee_rate: float = Field(default=0.001, ge=0.0, le=0.05)


class AShareDataPullPayload(BaseModel):
    start_date: date
    end_date: date
    limit: int | None = Field(default=None, ge=1, le=6000)


@app.on_event("startup")
def startup() -> None:
    ensure_platform_ready()


@app.get("/api/health")
def health() -> dict[str, Any]:
    ensure_platform_ready()
    return {"status": "ok", "database": str(DB_PATH), "version": "1.0.0"}


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    ensure_platform_ready()
    coverage = DataPortal().price_coverage()
    strategies = list_strategies()
    runs = _query(
        """
        SELECT status
        FROM strategy_runs
        """
    )
    latest_run = _query(
        """
        SELECT run_id, strategy_id, strategy_name, status, start_date, end_date, finished_at
        FROM strategy_runs
        ORDER BY started_at DESC
        LIMIT 1
        """
    )

    return {
        "strategy_count": len(strategies),
        "a_share_asset_count": _coverage_value(coverage, "A-share constituents", "asset_count"),
        "latest_price_date": _max_value(coverage, "end_date"),
        "successful_backtests": int((runs["status"] == "success").sum()) if not runs.empty else 0,
        "coverage": _records(coverage),
        "latest_run": _records(latest_run)[0] if not latest_run.empty else None,
    }


@app.get("/api/data/coverage")
def data_coverage() -> list[dict[str, Any]]:
    ensure_platform_ready()
    return _records(DataPortal().price_coverage())


@app.get("/api/data/quality")
def data_quality(refresh: bool = False) -> list[dict[str, Any]]:
    ensure_platform_ready()
    if refresh:
        return _records(refresh_data_quality_report())
    report = latest_data_quality_report()
    if report.empty:
        report = refresh_data_quality_report()
    return _records(report)


@app.get("/api/data/catalog")
def data_catalog() -> list[dict[str, Any]]:
    ensure_platform_ready()
    rows: list[dict[str, Any]] = []
    for dataset, config in DATASET_PREVIEWS.items():
        rows.append(
            {
                "dataset": dataset,
                "label": config["label"],
                "description": config["description"],
                "row_count": _row_count(config["count_sql"]),
            }
        )
    return rows


@app.get("/api/data/preview/{dataset}")
def data_preview(dataset: str, limit: int = 100) -> dict[str, Any]:
    ensure_platform_ready()
    config = DATASET_PREVIEWS.get(dataset)
    if config is None:
        allowed = ", ".join(DATASET_PREVIEWS)
        raise HTTPException(status_code=404, detail=f"Unknown dataset: {dataset}. Allowed: {allowed}")

    safe_limit = _bounded_limit(limit)
    frame = _query(config["preview_sql"], [safe_limit])
    return {
        "dataset": dataset,
        "label": config["label"],
        "description": config["description"],
        "row_count": _row_count(config["count_sql"]),
        "limit": safe_limit,
        "columns": list(frame.columns),
        "rows": _records(frame),
    }


@app.post("/api/data/pulls/a-share-prices")
def start_a_share_data_pull(payload: AShareDataPullPayload) -> dict[str, Any]:
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")

    with DATA_PULL_LOCK:
        _refresh_data_pull_state()
        if DATA_PULL_STATE["status"] == "running":
            raise HTTPException(status_code=409, detail="已有 A 股行情拉取任务正在运行")

        job_id = f"a_share_{uuid4().hex[:12]}"
        DATA_PULL_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = DATA_PULL_LOG_DIR / f"{job_id}.log"
        command = [
            sys.executable,
            "-u",
            "-m",
            "src.data_ingestion.a_share_market_prices",
            "--start-date",
            payload.start_date.strftime("%Y%m%d"),
            "--end-date",
            payload.end_date.strftime("%Y%m%d"),
        ]
        if payload.limit is not None:
            command.extend(["--limit", str(payload.limit)])

        log_file = log_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(
                command,
                cwd=str(PROJECT_ROOT),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            log_file.close()
            raise
        log_file.close()

        DATA_PULL_STATE.update(
            {
                "job_id": job_id,
                "status": "running",
                "dataset": "a_share_prices",
                "start_date": payload.start_date.isoformat(),
                "end_date": payload.end_date.isoformat(),
                "limit": payload.limit,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "return_code": None,
                "message": "正在拉取 A 股行情",
                "log_path": str(log_path),
                "process": process,
            }
        )
        return _data_pull_response()


@app.get("/api/data/pulls/a-share-prices/status")
def a_share_data_pull_status() -> dict[str, Any]:
    with DATA_PULL_LOCK:
        _refresh_data_pull_state()
        return _data_pull_response()


@app.get("/api/strategies")
def strategies() -> list[dict[str, Any]]:
    ensure_platform_ready()
    return _records(list_strategies())


@app.get("/api/research/factor-ic")
def factor_ic_summary() -> list[dict[str, Any]]:
    ensure_platform_ready()
    return _records(latest_factor_ic_summary())


@app.get("/api/runs")
def runs(limit: int = 30) -> list[dict[str, Any]]:
    ensure_platform_ready()
    return _records(DataPortal().latest_runs(limit=limit))


@app.get("/api/runs/{run_id}/metrics")
def run_metrics(run_id: str) -> list[dict[str, Any]]:
    return _records(
        _query(
            """
            SELECT metric_name, metric_value
            FROM strategy_run_metrics
            WHERE run_id = ?
            ORDER BY metric_name
            """,
            [run_id],
        )
    )


@app.get("/api/runs/{run_id}/nav")
def run_nav(run_id: str) -> list[dict[str, Any]]:
    return _records(
        _query(
            """
            SELECT date, nav, benchmark_nav, cash, gross_exposure, drawdown
            FROM backtest_nav
            WHERE run_id = ?
            ORDER BY date
            """,
            [run_id],
        )
    )


@app.get("/api/runs/{run_id}/positions")
def run_positions(run_id: str) -> list[dict[str, Any]]:
    return _records(
        _query(
            """
            SELECT
                p.date,
                p.asset_id,
                CASE
                    WHEN p.asset_id LIKE 'A_STOCK_%' THEN REPLACE(p.asset_id, 'A_STOCK_', '')
                    WHEN p.asset_id LIKE 'A_INDEX_%' THEN REPLACE(p.asset_id, 'A_INDEX_', '')
                    WHEN p.asset_id LIKE 'A_ETF_%' THEN REPLACE(p.asset_id, 'A_ETF_', '')
                    WHEN p.asset_id LIKE 'CRYPTO_%' THEN REPLACE(p.asset_id, 'CRYPTO_', '')
                    ELSE p.asset_id
                END AS asset_code,
                COALESCE(a.name, p.asset_id) AS asset_name,
                p.quantity,
                p.close_price,
                p.market_value,
                p.weight
            FROM positions_daily p
            LEFT JOIN assets a ON p.asset_id = a.asset_id
            WHERE p.run_id = ?
            QUALIFY p.date = MAX(p.date) OVER ()
            ORDER BY p.weight DESC
            LIMIT 100
            """,
            [run_id],
        )
    )


@app.get("/api/runs/{run_id}/orders")
def run_orders(run_id: str, limit: int = 200) -> list[dict[str, Any]]:
    return _records(
        _query(
            """
            SELECT
                o.date,
                o.asset_id,
                CASE
                    WHEN o.asset_id LIKE 'A_STOCK_%' THEN REPLACE(o.asset_id, 'A_STOCK_', '')
                    WHEN o.asset_id LIKE 'A_INDEX_%' THEN REPLACE(o.asset_id, 'A_INDEX_', '')
                    WHEN o.asset_id LIKE 'A_ETF_%' THEN REPLACE(o.asset_id, 'A_ETF_', '')
                    WHEN o.asset_id LIKE 'CRYPTO_%' THEN REPLACE(o.asset_id, 'CRYPTO_', '')
                    ELSE o.asset_id
                END AS asset_code,
                COALESCE(a.name, o.asset_id) AS asset_name,
                o.side,
                o.status,
                o.quantity,
                o.price,
                o.notional,
                o.target_weight,
                o.reason
            FROM orders o
            LEFT JOIN assets a ON o.asset_id = a.asset_id
            WHERE o.run_id = ?
            ORDER BY o.date DESC, o.notional DESC
            LIMIT ?
            """,
            [run_id, limit],
        )
    )


@app.get("/api/signals/latest/{strategy_id}")
def latest_signals(strategy_id: str) -> list[dict[str, Any]]:
    ensure_platform_ready()
    return _records(DataPortal().latest_signals(strategy_id))


@app.post("/api/backtests")
def create_backtest(payload: BacktestPayload) -> dict[str, Any]:
    try:
        result = run_backtest(
            BacktestRequest(
                strategy_id=payload.strategy_id,
                start_date=payload.start_date,
                end_date=payload.end_date,
                initial_cash=payload.initial_cash,
                config_overrides={
                    "top_n": payload.top_n,
                    "max_single_position": payload.max_single_position,
                    "fee_rate": payload.fee_rate,
                },
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "run_id": result.run_id,
        "strategy_id": result.strategy_id,
        "strategy_name": result.strategy_name,
        "status": result.status,
        "metrics": result.metrics,
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat(),
    }


def _query(sql: str, params: list[Any] | None = None) -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH)) as con:
        return con.execute(sql, params or []).df()


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    cleaned = frame.astype(object).where(pd.notna(frame), None)
    return [
        {key: _json_value(value) for key, value in row.items()}
        for row in cleaned.to_dict(orient="records")
    ]


def _json_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _row_count(sql: str) -> int:
    frame = _query(sql)
    if frame.empty or "row_count" not in frame.columns:
        return 0
    value = frame["row_count"].iloc[0]
    if pd.isna(value):
        return 0
    return int(value)


def _bounded_limit(limit: int) -> int:
    return max(1, min(int(limit), 500))


def _refresh_data_pull_state() -> None:
    process = DATA_PULL_STATE.get("process")
    if process is None or DATA_PULL_STATE["status"] != "running":
        return
    return_code = process.poll()
    if return_code is None:
        return
    DATA_PULL_STATE["return_code"] = return_code
    DATA_PULL_STATE["finished_at"] = datetime.now(timezone.utc).isoformat()
    DATA_PULL_STATE["status"] = "success" if return_code == 0 else "failed"
    DATA_PULL_STATE["message"] = "数据拉取完成" if return_code == 0 else "数据拉取失败，请查看日志"
    DATA_PULL_STATE["process"] = None


def _data_pull_response() -> dict[str, Any]:
    log_text = ""
    log_path = DATA_PULL_STATE.get("log_path")
    if log_path and Path(log_path).exists():
        lines = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
        log_text = "\n".join(lines[-80:])
    return {
        key: value
        for key, value in DATA_PULL_STATE.items()
        if key not in {"process", "log_path"}
    } | {"log": log_text}


def _coverage_value(coverage: pd.DataFrame, group: str, column: str) -> int:
    if coverage.empty or column not in coverage.columns:
        return 0
    match = coverage.loc[coverage["asset_group"] == group, column]
    if match.empty or pd.isna(match.iloc[0]):
        return 0
    return int(match.iloc[0])


def _max_value(frame: pd.DataFrame, column: str) -> str | None:
    if frame.empty or column not in frame.columns:
        return None
    value = frame[column].max()
    if pd.isna(value):
        return None
    return str(value)
