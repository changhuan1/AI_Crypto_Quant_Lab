from __future__ import annotations

from datetime import date
from typing import Any

import duckdb
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.jobs.init_db import DB_PATH
from src.platform.backtest_service import run_backtest
from src.platform.data_api import DataPortal
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


class BacktestPayload(BaseModel):
    strategy_id: str
    start_date: date | None = None
    end_date: date | None = None
    initial_cash: float = Field(default=100_000.0, ge=1_000)
    top_n: int = Field(default=30, ge=1, le=200)
    max_single_position: float = Field(default=0.03, ge=0.001, le=1.0)
    fee_rate: float = Field(default=0.001, ge=0.0, le=0.05)


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


@app.get("/api/strategies")
def strategies() -> list[dict[str, Any]]:
    ensure_platform_ready()
    return _records(list_strategies())


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
            SELECT date, asset_id, quantity, close_price, market_value, weight
            FROM positions_daily
            WHERE run_id = ?
            QUALIFY date = MAX(date) OVER ()
            ORDER BY weight DESC
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
            SELECT date, asset_id, side, quantity, price, notional, target_weight, reason
            FROM orders
            WHERE run_id = ?
            ORDER BY date DESC, notional DESC
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
