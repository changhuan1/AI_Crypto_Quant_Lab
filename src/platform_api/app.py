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

from src.backtest.metrics import calculate_metrics
from src.data_ingestion.a_share_market_prices import fetch_stock_daily, save_prices
from src.jobs.init_db import DB_PATH
from src.platform.backtest_engine import backtest_target_weights
from src.platform.backtest_service import _save_successful_run, run_backtest
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
    "raw_prices_daily": {
        "label": "原始日线行情",
        "description": "Tushare 未复权日线行情。成交量统一为股，成交额统一为元。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM raw_prices_daily",
        "preview_sql": """
            SELECT r.date, r.asset_id, REPLACE(r.asset_id, 'A_STOCK_', '') AS asset_code,
                   COALESCE(a.name, r.asset_id) AS asset_name, r.open, r.high, r.low, r.close,
                   r.pre_close, r.change, r.pct_change, r.volume, r.turnover, r.source, r.created_at
            FROM raw_prices_daily r
            LEFT JOIN assets a ON r.asset_id = a.asset_id
            ORDER BY r.date DESC, r.asset_id
            LIMIT ?
        """,
    },
    "adjustment_factors": {
        "label": "复权因子",
        "description": "用于从原始价格计算前复权或后复权价格的每日复权因子。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM adjustment_factors",
        "preview_sql": """
            SELECT f.date, f.asset_id, REPLACE(f.asset_id, 'A_STOCK_', '') AS asset_code,
                   COALESCE(a.name, f.asset_id) AS asset_name, f.adj_factor, f.source, f.created_at
            FROM adjustment_factors f
            LEFT JOIN assets a ON f.asset_id = a.asset_id
            ORDER BY f.date DESC, f.asset_id
            LIMIT ?
        """,
    },
    "daily_market_indicators": {
        "label": "每日估值与市值",
        "description": "换手率、PE、PB、股息率、股本、总市值和流通市值等每日指标。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM daily_market_indicators",
        "preview_sql": """
            SELECT d.date, d.asset_id, REPLACE(d.asset_id, 'A_STOCK_', '') AS asset_code,
                   COALESCE(a.name, d.asset_id) AS asset_name, d.turnover_rate, d.volume_ratio,
                   d.pe, d.pe_ttm, d.pb, d.ps_ttm, d.dividend_yield_ttm,
                   d.total_market_value, d.circulating_market_value, d.source, d.created_at
            FROM daily_market_indicators d
            LEFT JOIN assets a ON d.asset_id = a.asset_id
            ORDER BY d.date DESC, d.asset_id
            LIMIT ?
        """,
    },
    "asset_name_history": {
        "label": "历史名称与 ST 区间",
        "description": "股票历史名称、生效区间、公告日期以及是否为 ST 名称。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM asset_name_history",
        "preview_sql": """
            SELECT h.asset_id, REPLACE(h.asset_id, 'A_STOCK_', '') AS asset_code,
                   h.name, h.start_date, h.end_date, h.announcement_date,
                   h.change_reason, h.is_st_name, h.source, h.created_at
            FROM asset_name_history h
            ORDER BY h.start_date DESC, h.asset_id
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
    "market_universe_daily": {
        "label": "沪市历史股票池",
        "description": "指定交易日沪市存在的证券及交易状态，不等同于官方上证指数历史权重。",
        "count_sql": "SELECT COUNT(*) AS row_count FROM market_universe_daily",
        "preview_sql": """
            SELECT date, asset_id, REPLACE(asset_id, 'A_STOCK_', '') AS asset_code,
                   asset_name, is_listed, is_tradable, market, source, created_at
            FROM market_universe_daily
            ORDER BY date DESC, asset_id
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


class SingleStockBacktestPayload(BaseModel):
    asset_code: str = Field(min_length=6, max_length=16)
    start_date: date
    end_date: date
    initial_cash: float = Field(default=100_000.0, ge=1_000)
    strategy_mode: str = Field(default="ma_filter")
    strategy_code: str | None = None
    strategy_script_id: str | None = None
    custom_strategy_name: str | None = None
    target_weight: float = Field(default=0.95, ge=0.01, le=1.0)
    ma_short: int = Field(default=5, ge=2, le=120)
    ma_long: int = Field(default=20, ge=3, le=250)
    fee_rate: float = Field(default=0.001, ge=0.0, le=0.05)


class SingleStockPricePullPayload(BaseModel):
    start_date: date
    end_date: date


class SingleStockStrategyScriptPayload(BaseModel):
    script_id: str | None = None
    name: str = Field(min_length=1, max_length=80)
    code: str = Field(min_length=20, max_length=20000)


class PortfolioBacktestPayload(BaseModel):
    start_date: date
    end_date: date
    initial_cash: float = Field(default=100_000.0, ge=1_000)
    universe_limit: int = Field(default=80, ge=5, le=600)
    top_n: int = Field(default=10, ge=1, le=100)
    lookback_days: int = Field(default=60, ge=5, le=250)
    rebalance_days: int = Field(default=20, ge=1, le=120)
    max_single_position: float = Field(default=0.1, ge=0.001, le=1.0)
    fee_rate: float = Field(default=0.001, ge=0.0, le=0.05)


DEFAULT_SINGLE_STOCK_STRATEGY_CODE = '''def generate_signals(context):
    prices = context["prices"].copy()
    target_weight = context.get("target_weight", 0.95)

    prices["ma_short"] = prices["close"].rolling(5).mean()
    prices["ma_long"] = prices["close"].rolling(20).mean()
    prices["target_weight"] = 0.0
    prices.loc[prices["ma_short"] > prices["ma_long"], "target_weight"] = target_weight
    prices["signal"] = prices["target_weight"].apply(lambda weight: "target_weight" if weight > 0 else "hold_cash")
    prices["score"] = (prices["ma_short"] / prices["ma_long"] - 1).fillna(0.0)
    prices["reason"] = prices["signal"].map({
        "target_weight": "短均线高于长均线，持有目标仓位",
        "hold_cash": "短均线未高于长均线，空仓"
    })
    return prices[["date", "signal", "target_weight", "score", "reason"]].dropna()
'''


@app.get("/api/single-stock/strategy-scripts")
def single_stock_strategy_scripts() -> list[dict[str, Any]]:
    ensure_platform_ready()
    _ensure_strategy_script_table()
    rows = _query(
        """
        SELECT script_id, name, code, created_at, updated_at
        FROM single_stock_strategy_scripts
        ORDER BY updated_at DESC
        """
    )
    if rows.empty:
        return [
            {
                "script_id": "template_ma_cross",
                "name": "模板：均线过滤持有",
                "code": DEFAULT_SINGLE_STOCK_STRATEGY_CODE,
                "created_at": None,
                "updated_at": None,
                "is_template": True,
            }
        ]
    records = _records(rows)
    for record in records:
        record["is_template"] = False
    return records


@app.post("/api/single-stock/strategy-scripts")
def save_single_stock_strategy_script(payload: SingleStockStrategyScriptPayload) -> dict[str, Any]:
    ensure_platform_ready()
    _ensure_strategy_script_table()
    script_id = payload.script_id or f"single_script_{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    with duckdb.connect(str(DB_PATH)) as con:
        existing = con.execute(
            "SELECT created_at FROM single_stock_strategy_scripts WHERE script_id = ?",
            [script_id],
        ).fetchone()
        created_at = existing[0] if existing else now
        con.execute(
            """
            INSERT OR REPLACE INTO single_stock_strategy_scripts
            (script_id, name, code, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [script_id, payload.name, payload.code, created_at, now],
        )
    return {
        "script_id": script_id,
        "name": payload.name,
        "code": payload.code,
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
        "updated_at": now.isoformat(),
        "is_template": False,
    }


@app.get("/api/single-stock/{asset_code}/profile")
def single_stock_profile(
    asset_code: str,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 120,
) -> dict[str, Any]:
    ensure_platform_ready()
    normalized_code = _normalize_asset_code(asset_code)
    asset_id = f"A_STOCK_{normalized_code}"
    asset = _asset_info(asset_id)
    coverage_info = _single_stock_price_coverage(asset_id)
    if coverage_info is None:
        return {
            "asset_id": asset_id,
            "asset_code": normalized_code,
            "asset_name": asset.get("asset_name") or asset_id,
            "coverage": {
                "rows": 0,
                "start_date": None,
                "end_date": None,
                "source": None,
            },
            "selected": {
                "rows": 0,
                "start_date": None,
                "end_date": None,
            },
            "prices": [],
        }

    safe_limit = _bounded_limit(limit)
    selected = _single_stock_price_coverage(asset_id, start_date=start_date, end_date=end_date)
    prices = _single_stock_prices(asset_id, start_date=start_date, end_date=end_date, limit=safe_limit)
    prices = prices.sort_values("date") if not prices.empty else prices
    return {
        "asset_id": asset_id,
        "asset_code": normalized_code,
        "asset_name": asset.get("asset_name") or asset_id,
        "coverage": {
            "rows": int(coverage_info["row_count"]),
            "start_date": _json_value(coverage_info["start_date"]),
            "end_date": _json_value(coverage_info["end_date"]),
            "source": coverage_info["source"],
        },
        "selected": {
            "rows": int(selected["row_count"]) if selected else 0,
            "start_date": selected.get("start_date") if selected else None,
            "end_date": selected.get("end_date") if selected else None,
        },
        "prices": _records(prices),
    }


@app.post("/api/single-stock/{asset_code}/prices/pull")
def pull_single_stock_prices(asset_code: str, payload: SingleStockPricePullPayload) -> dict[str, Any]:
    ensure_platform_ready()
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")

    normalized_code = _normalize_asset_code(asset_code)
    asset_id = f"A_STOCK_{normalized_code}"
    start_text = payload.start_date.strftime("%Y%m%d")
    end_text = payload.end_date.strftime("%Y%m%d")
    try:
        history = fetch_stock_daily(normalized_code, start_date=start_text, end_date=end_text)
        if not history.empty:
            save_prices(history)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"单股行情拉取失败：{exc}") from exc

    profile = single_stock_profile(
        asset_code=normalized_code,
        start_date=payload.start_date,
        end_date=payload.end_date,
        limit=160,
    )
    profile["pulled_rows"] = int(len(history))
    profile["message"] = (
        f"已拉取 {normalized_code} {payload.start_date.isoformat()} 至 "
        f"{payload.end_date.isoformat()} 行情，新增/更新 {len(history)} 行"
    )
    return profile


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


@app.post("/api/single-stock/backtests")
def create_single_stock_backtest(payload: SingleStockBacktestPayload) -> dict[str, Any]:
    ensure_platform_ready()
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
    if payload.strategy_mode not in {"ma_filter", "buy_hold", "custom_code"}:
        raise HTTPException(status_code=400, detail="策略模式仅支持 ma_filter、buy_hold 或 custom_code")
    if payload.strategy_mode == "ma_filter" and payload.ma_short >= payload.ma_long:
        raise HTTPException(status_code=400, detail="短均线周期必须小于长均线周期")
    if payload.strategy_mode == "custom_code" and not payload.strategy_code:
        raise HTTPException(status_code=400, detail="自定义策略需要填写策略代码")

    asset_code = _normalize_asset_code(payload.asset_code)
    asset_id = f"A_STOCK_{asset_code}"
    prices = _load_single_stock_prices(asset_id, payload.start_date, payload.end_date)
    if prices.empty:
        raise HTTPException(status_code=400, detail=f"没有找到 {asset_code} 在所选日期范围内的行情数据")
    if len(prices) < 2:
        raise HTTPException(status_code=400, detail="行情数据少于 2 行，无法回测")

    asset = _asset_info(asset_id)
    signals = _single_stock_signals(prices, asset_id, payload)
    if signals.empty:
        raise HTTPException(status_code=400, detail="没有生成任何信号，请扩大日期范围或调整均线参数")

    started_at = datetime.now(timezone.utc)
    run_id = f"single_{asset_code}_{started_at.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    strategy_id = f"single_stock_{asset_code}_{payload.strategy_mode}"
    strategy_name = (
        payload.custom_strategy_name
        or f"单股流程 {asset_code} {asset.get('asset_name') or ''}".strip()
    )
    asset_status = _load_single_stock_status(asset_id, payload.start_date, payload.end_date)
    ledger = backtest_target_weights(
        prices=prices,
        signals=signals,
        run_id=run_id,
        strategy_id=strategy_id,
        initial_cash=payload.initial_cash,
        fee_rate=payload.fee_rate,
        asset_status=asset_status,
        execution_delay_days=1,
    )

    nav = _attach_single_stock_benchmark(ledger.nav, prices, payload.initial_cash)
    metrics = calculate_metrics(nav, periods_per_year=252)
    finished_at = datetime.now(timezone.utc)
    request = BacktestRequest(
        strategy_id=strategy_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        initial_cash=payload.initial_cash,
        config_overrides=payload.dict(),
    )
    config = {
        **payload.dict(),
        "start_date": payload.start_date.isoformat(),
        "end_date": payload.end_date.isoformat(),
    }
    _save_successful_run(
        db_path=DB_PATH,
        run_id=run_id,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
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

    return {
        "run_id": run_id,
        "asset_id": asset_id,
        "asset_code": asset_code,
        "asset_name": asset.get("asset_name") or asset_id,
        "strategy_name": strategy_name,
        "status": "success",
        "data_summary": {
            "rows": len(prices),
            "start_date": str(prices["date"].min()),
            "end_date": str(prices["date"].max()),
            "source": ", ".join(sorted(str(value) for value in prices["source"].dropna().unique())),
        },
        "metrics": {key: _json_value(value) for key, value in metrics.items()},
        "nav": _records(nav),
        "signals": _records(signals.tail(80)),
        "orders": _records(_with_asset_labels(ledger.orders).tail(80)),
        "positions": _records(_with_asset_labels(ledger.positions).tail(80)),
        "daily_ledger": _records(_single_stock_daily_ledger(nav, ledger.orders, ledger.trades, ledger.positions)),
    }


@app.post("/api/portfolio/backtests")
def create_portfolio_backtest(payload: PortfolioBacktestPayload) -> dict[str, Any]:
    ensure_platform_ready()
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
    if payload.top_n > payload.universe_limit:
        raise HTTPException(status_code=400, detail="持仓数量不能大于股票池数量")

    prices = _load_portfolio_prices(payload.start_date, payload.end_date, payload.universe_limit)
    if prices.empty:
        raise HTTPException(status_code=400, detail="所选区间没有可用的股票池行情")
    if prices["asset_id"].nunique() < payload.top_n:
        raise HTTPException(status_code=400, detail="可用股票数量少于目标持仓数量，请扩大股票池或先补数据")

    signals = _portfolio_momentum_signals(prices, payload)
    if signals.empty:
        raise HTTPException(status_code=400, detail="没有生成组合调仓信号，请扩大日期范围或缩短动量窗口")

    started_at = datetime.now(timezone.utc)
    run_id = f"portfolio_momentum_{started_at.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    strategy_id = "portfolio_a_share_momentum"
    strategy_name = "组合实验室 A股动量轮动"
    asset_status = _load_asset_status_for_assets(
        list(prices["asset_id"].dropna().unique()),
        payload.start_date,
        payload.end_date,
    )
    ledger = backtest_target_weights(
        prices=prices,
        signals=signals,
        run_id=run_id,
        strategy_id=strategy_id,
        initial_cash=payload.initial_cash,
        fee_rate=payload.fee_rate,
        asset_status=asset_status,
        execution_delay_days=1,
    )
    nav = ledger.nav.copy()
    if not nav.empty:
        nav["benchmark_nav"] = _equal_weight_benchmark_nav(prices, payload.initial_cash)
    metrics = calculate_metrics(nav, periods_per_year=252)
    finished_at = datetime.now(timezone.utc)
    request = BacktestRequest(
        strategy_id=strategy_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        initial_cash=payload.initial_cash,
        config_overrides=payload.dict(),
    )
    config = {
        **payload.dict(),
        "start_date": payload.start_date.isoformat(),
        "end_date": payload.end_date.isoformat(),
    }
    _save_successful_run(
        db_path=DB_PATH,
        run_id=run_id,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
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

    return {
        "run_id": run_id,
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "status": "success",
        "data_summary": {
            "rows": len(prices),
            "asset_count": int(prices["asset_id"].nunique()),
            "start_date": str(prices["date"].min()),
            "end_date": str(prices["date"].max()),
            "source": ", ".join(sorted(str(value) for value in prices["source"].dropna().unique())),
        },
        "metrics": {key: _json_value(value) for key, value in metrics.items()},
        "nav": _records(nav),
        "signals": _records(_with_asset_labels(signals).tail(120)),
        "orders": _records(_with_asset_labels(ledger.orders).tail(120)),
        "positions": _records(_with_asset_labels(ledger.positions).tail(120)),
        "daily_ledger": _records(_portfolio_daily_ledger(nav, ledger.orders, ledger.trades, ledger.positions)),
    }


@app.get("/api/platform/readiness")
def platform_readiness() -> dict[str, Any]:
    ensure_platform_ready()
    quality = latest_data_quality_report()
    if quality.empty:
        quality = refresh_data_quality_report()
    severity_counts = (
        quality.groupby("severity").size().reset_index(name="count").to_dict(orient="records")
        if not quality.empty
        else []
    )
    return {
        "datasets": [
            {
                "dataset": key,
                "label": value["label"],
                "row_count": _row_count(value["count_sql"]),
            }
            for key, value in DATASET_PREVIEWS.items()
        ],
        "quality": severity_counts,
        "rules": [
            {"name": "T+1", "status": "enabled", "description": "当日买入的股票不能在同一交易日卖出"},
            {"name": "整手交易", "status": "enabled", "description": "买入数量按 100 股整数倍撮合"},
            {"name": "涨跌停过滤", "status": "enabled", "description": "涨停不买入，跌停不卖出"},
            {"name": "停牌/ST过滤", "status": "enabled", "description": "停牌、ST 标记资产不参与交易"},
            {"name": "交易费用", "status": "enabled", "description": "包含佣金、印花税、过户费和最低佣金"},
        ],
    }


def _query(sql: str, params: list[Any] | None = None) -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH)) as con:
        return con.execute(sql, params or []).df()


def _ensure_strategy_script_table() -> None:
    with duckdb.connect(str(DB_PATH)) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS single_stock_strategy_scripts (
                script_id TEXT PRIMARY KEY,
                name TEXT,
                code TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
            """
        )


def _normalize_asset_code(value: str) -> str:
    code = value.strip().upper()
    if "." in code:
        code = code.split(".")[0]
    return "".join(character for character in code if character.isdigit()).zfill(6)


def _load_single_stock_prices(asset_id: str, start_date: date, end_date: date) -> pd.DataFrame:
    return _single_stock_prices(asset_id, start_date=start_date, end_date=end_date)


def _load_single_stock_status(asset_id: str, start_date: date, end_date: date) -> pd.DataFrame:
    return _query(
        """
        SELECT *
        FROM asset_status_daily
        WHERE asset_id = ?
          AND date >= ?
          AND date <= ?
        ORDER BY date
        """,
        [asset_id, start_date, end_date],
    )


def _load_asset_status_for_assets(asset_ids: list[str], start_date: date, end_date: date) -> pd.DataFrame:
    if not asset_ids:
        return pd.DataFrame()
    placeholders = ", ".join(["?"] * len(asset_ids))
    return _query(
        f"""
        SELECT *
        FROM asset_status_daily
        WHERE asset_id IN ({placeholders})
          AND date >= ?
          AND date <= ?
        ORDER BY date, asset_id
        """,
        [*asset_ids, start_date, end_date],
    )


def _load_portfolio_prices(start_date: date, end_date: date, universe_limit: int) -> pd.DataFrame:
    return _query(
        """
        WITH asset_coverage AS (
            SELECT asset_id, date
            FROM raw_prices_daily
            WHERE asset_id LIKE 'A_STOCK_%'
              AND date >= ?
              AND date <= ?
            UNION ALL
            SELECT asset_id, date
            FROM prices_daily
            WHERE asset_id LIKE 'A_STOCK_%'
              AND date >= ?
              AND date <= ?
        ),
        ranked_assets AS (
            SELECT asset_id, COUNT(*) AS rows_available, MAX(date) AS latest_date
            FROM asset_coverage
            GROUP BY asset_id
            HAVING COUNT(*) >= 30
            ORDER BY latest_date DESC, rows_available DESC, asset_id
            LIMIT ?
        ),
        combined AS (
            SELECT
                p.asset_id, p.date, p.open, p.high, p.low, p.close, p.volume, p.turnover,
                p.source, p.created_at,
                CASE
                    WHEN p.source = 'tushare' THEN 0
                    WHEN p.source = 'baostock' THEN 1
                    ELSE 2
                END AS source_priority
            FROM raw_prices_daily p
            INNER JOIN ranked_assets r ON p.asset_id = r.asset_id
            WHERE p.date >= ?
              AND p.date <= ?
            UNION ALL
            SELECT
                p.asset_id, p.date, p.open, p.high, p.low, p.close, p.volume, p.turnover,
                p.source, p.created_at,
                CASE
                    WHEN p.source = 'tushare' THEN 0
                    WHEN p.source = 'baostock' THEN 1
                    ELSE 2
                END AS source_priority
            FROM prices_daily p
            INNER JOIN ranked_assets r ON p.asset_id = r.asset_id
            WHERE p.date >= ?
              AND p.date <= ?
        )
        SELECT asset_id, date, open, high, low, close, volume, turnover, source, created_at
        FROM combined
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY asset_id, date
            ORDER BY source_priority, created_at DESC
        ) = 1
        ORDER BY date, asset_id
        """,
        [start_date, end_date, start_date, end_date, universe_limit, start_date, end_date, start_date, end_date],
    )


def _portfolio_momentum_signals(prices: pd.DataFrame, payload: PortfolioBacktestPayload) -> pd.DataFrame:
    data = prices.sort_values(["date", "asset_id"]).copy()
    data["date"] = pd.to_datetime(data["date"]).dt.date
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    close = data.pivot(index="date", columns="asset_id", values="close").sort_index()
    momentum = close.pct_change(payload.lookback_days, fill_method=None)
    dates = list(close.index)
    records: list[dict[str, Any]] = []
    previous_assets: set[str] = set()
    now = datetime.now(timezone.utc)

    for index, date_value in enumerate(dates):
        if index < payload.lookback_days or (index - payload.lookback_days) % payload.rebalance_days != 0:
            continue
        scores = momentum.loc[date_value].dropna().sort_values(ascending=False)
        selected = list(scores.head(payload.top_n).index)
        if not selected:
            continue
        target_weight = min(1.0 / len(selected), payload.max_single_position)
        selected_set = set(selected)
        for asset_id in selected:
            score = float(scores.loc[asset_id])
            records.append(
                {
                    "asset_id": asset_id,
                    "date": date_value,
                    "strategy": "portfolio_a_share_momentum",
                    "score": score,
                    "signal": "target_weight",
                    "target_weight": target_weight,
                    "risk_flag": False,
                    "reason": f"{payload.lookback_days}日动量排名靠前，目标仓位={target_weight:.1%}",
                    "created_at": now,
                }
            )
        for asset_id in sorted(previous_assets - selected_set):
            records.append(
                {
                    "asset_id": asset_id,
                    "date": date_value,
                    "strategy": "portfolio_a_share_momentum",
                    "score": 0.0,
                    "signal": "hold_cash",
                    "target_weight": 0.0,
                    "risk_flag": True,
                    "reason": "调仓日未进入动量排名，目标清仓",
                    "created_at": now,
                }
            )
        previous_assets = selected_set

    return pd.DataFrame(records)


def _equal_weight_benchmark_nav(prices: pd.DataFrame, initial_cash: float) -> pd.Series:
    data = prices.sort_values(["date", "asset_id"]).copy()
    data["date"] = pd.to_datetime(data["date"]).dt.date
    close = data.pivot(index="date", columns="asset_id", values="close").sort_index()
    returns = close.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    benchmark = (1 + returns).cumprod() * initial_cash
    benchmark.name = "benchmark_nav"
    return benchmark.reindex(pd.to_datetime(data["date"]).dt.date.unique()).reset_index(drop=True)


def _single_stock_prices(
    asset_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    limit_sql = "LIMIT ?" if limit is not None else ""
    params: list[Any] = [
        asset_id,
        start_date,
        start_date,
        end_date,
        end_date,
        asset_id,
        start_date,
        start_date,
        end_date,
        end_date,
    ]
    if limit is not None:
        params.append(limit)
    return _query(
        f"""
        WITH combined AS (
            SELECT
                asset_id, date, open, high, low, close, volume, turnover, source, created_at,
                CASE
                    WHEN source = 'tushare' THEN 0
                    WHEN source = 'baostock' THEN 1
                    ELSE 2
                END AS source_priority
            FROM raw_prices_daily
            WHERE asset_id = ?
              AND (? IS NULL OR date >= ?)
              AND (? IS NULL OR date <= ?)
            UNION ALL
            SELECT
                asset_id, date, open, high, low, close, volume, turnover, source, created_at,
                CASE
                    WHEN source = 'tushare' THEN 0
                    WHEN source = 'baostock' THEN 1
                    ELSE 2
                END AS source_priority
            FROM prices_daily
            WHERE asset_id = ?
              AND (? IS NULL OR date >= ?)
              AND (? IS NULL OR date <= ?)
        )
        SELECT asset_id, date, open, high, low, close, volume, turnover, source, created_at
        FROM combined
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY asset_id, date
            ORDER BY source_priority, created_at DESC
        ) = 1
        ORDER BY date DESC
        {limit_sql}
        """,
        params,
    )


def _single_stock_price_coverage(
    asset_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any] | None:
    prices = _single_stock_prices(asset_id, start_date=start_date, end_date=end_date)
    if prices.empty:
        return None
    return {
        "row_count": int(prices["date"].nunique()),
        "start_date": prices["date"].min(),
        "end_date": prices["date"].max(),
        "source": ", ".join(sorted(str(value) for value in prices["source"].dropna().unique())),
    }


def _asset_info(asset_id: str) -> dict[str, Any]:
    frame = _query(
        """
        SELECT asset_id, symbol AS asset_code, name AS asset_name, market, asset_type
        FROM assets
        WHERE asset_id = ?
        LIMIT 1
        """,
        [asset_id],
    )
    return _records(frame)[0] if not frame.empty else {}


def _single_stock_signals(
    prices: pd.DataFrame,
    asset_id: str,
    payload: SingleStockBacktestPayload,
) -> pd.DataFrame:
    data = prices.sort_values("date").copy()
    data["date"] = pd.to_datetime(data["date"]).dt.date
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    data["volume"] = pd.to_numeric(data["volume"], errors="coerce")
    if payload.strategy_mode == "custom_code":
        data = _run_single_stock_strategy_code(data, payload)
    elif payload.strategy_mode == "ma_filter":
        data["ma_short"] = data["close"].rolling(payload.ma_short, min_periods=payload.ma_short).mean()
        data["ma_long"] = data["close"].rolling(payload.ma_long, min_periods=payload.ma_long).mean()
        data["target_weight"] = 0.0
        data.loc[data["ma_short"] > data["ma_long"], "target_weight"] = payload.target_weight
        data["score"] = data["ma_short"] / data["ma_long"] - 1
        data["reason"] = [
            (
                f"短均线({payload.ma_short})高于长均线({payload.ma_long})，目标仓位={payload.target_weight:.0%}"
                if weight > 0
                else f"短均线({payload.ma_short})未高于长均线({payload.ma_long})，空仓"
            )
            for weight in data["target_weight"]
        ]
        data = data.dropna(subset=["ma_short", "ma_long"])
    else:
        data["target_weight"] = payload.target_weight
        data["score"] = data["close"].pct_change().fillna(0.0)
        data["reason"] = f"买入并持有，目标仓位={payload.target_weight:.0%}"

    if data.empty:
        return pd.DataFrame()
    data["asset_id"] = asset_id
    data["strategy"] = f"single_stock_{_normalize_asset_code(asset_id)}_{payload.strategy_mode}"
    data["signal"] = data["target_weight"].apply(lambda value: "target_weight" if value > 0 else "hold_cash")
    data["risk_flag"] = data["target_weight"] <= 0
    data["created_at"] = datetime.now(timezone.utc)
    return data[
        [
            "asset_id",
            "date",
            "strategy",
            "score",
            "signal",
            "target_weight",
            "risk_flag",
            "reason",
            "created_at",
        ]
    ]


def _run_single_stock_strategy_code(
    prices: pd.DataFrame,
    payload: SingleStockBacktestPayload,
) -> pd.DataFrame:
    pending_targets: dict[str, float] = {}

    def order_target_percent(asset_code: str, target_weight: float) -> None:
        normalized = _normalize_asset_code(asset_code)
        pending_targets[f"A_STOCK_{normalized}"] = float(target_weight)

    namespace: dict[str, Any] = {}
    safe_builtins = {
        "abs": abs,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "range": range,
        "round": round,
        "str": str,
        "sum": sum,
        "zip": zip,
    }
    globals_dict = {
        "__builtins__": safe_builtins,
        "pd": pd,
        "order_target_percent": order_target_percent,
    }
    try:
        exec(payload.strategy_code or "", globals_dict, namespace)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"策略代码编译失败：{exc}") from exc

    context = {
        "prices": prices.copy(),
        "target_weight": payload.target_weight,
        "ma_short": payload.ma_short,
        "ma_long": payload.ma_long,
        "initial_cash": payload.initial_cash,
        "state": {},
        "order_target_percent": order_target_percent,
    }
    initialize = namespace.get("initialize") or globals_dict.get("initialize")
    generate_signals = namespace.get("generate_signals") or globals_dict.get("generate_signals")
    on_bar = (
        namespace.get("on_bar")
        or globals_dict.get("on_bar")
        or namespace.get("handle_data")
        or globals_dict.get("handle_data")
    )
    if callable(initialize):
        try:
            initialize(context)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"initialize 运行失败：{exc}") from exc

    if not callable(generate_signals) and callable(on_bar):
        records = []
        for _, bar in prices.sort_values("date").iterrows():
            pending_targets.clear()
            data = bar.to_dict()
            data["asset_code"] = _normalize_asset_code(str(bar["asset_id"]))
            try:
                result = on_bar(context, data)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"on_bar 运行失败：{exc}") from exc
            if isinstance(result, (int, float)):
                pending_targets[str(bar["asset_id"])] = float(result)
            target_weight = float(pending_targets.get(str(bar["asset_id"]), 0.0))
            records.append(
                {
                    "date": bar["date"],
                    "target_weight": max(0.0, min(target_weight, 1.0)),
                    "signal": "target_weight" if target_weight > 0 else "hold_cash",
                    "score": target_weight,
                    "reason": "on_bar/order_target_percent 生成信号",
                }
            )
        return pd.DataFrame(records)

    if not callable(generate_signals):
        raise HTTPException(
            status_code=400,
            detail="策略代码必须定义 generate_signals(context)，或定义 initialize(context)+on_bar(context, data)",
        )

    try:
        result = generate_signals(context)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"策略代码运行失败：{exc}") from exc

    if isinstance(result, list):
        signals = pd.DataFrame(result)
    elif isinstance(result, pd.DataFrame):
        signals = result.copy()
    else:
        raise HTTPException(status_code=400, detail="generate_signals 必须返回 pandas.DataFrame 或 list[dict]")

    required = {"date", "target_weight"}
    missing = required - set(signals.columns)
    if missing:
        raise HTTPException(status_code=400, detail=f"策略信号缺少必要字段：{', '.join(sorted(missing))}")

    signals["date"] = pd.to_datetime(signals["date"], errors="coerce").dt.date
    signals["target_weight"] = pd.to_numeric(signals["target_weight"], errors="coerce").clip(lower=0.0, upper=1.0)
    if "signal" not in signals.columns:
        signals["signal"] = signals["target_weight"].apply(lambda value: "target_weight" if value > 0 else "hold_cash")
    if "score" not in signals.columns:
        signals["score"] = signals["target_weight"]
    if "reason" not in signals.columns:
        signals["reason"] = "自定义策略信号"
    signals = signals.dropna(subset=["date", "target_weight"]).sort_values("date")
    return signals[["date", "signal", "target_weight", "score", "reason"]]


def _attach_single_stock_benchmark(
    nav: pd.DataFrame,
    prices: pd.DataFrame,
    initial_cash: float,
) -> pd.DataFrame:
    if nav.empty:
        return nav
    benchmark = prices.sort_values("date")[["date", "close"]].copy()
    benchmark["date"] = pd.to_datetime(benchmark["date"]).dt.date
    first_close = benchmark["close"].dropna().iloc[0]
    benchmark["benchmark_nav"] = benchmark["close"] / first_close * initial_cash
    return nav.merge(benchmark[["date", "benchmark_nav"]], on="date", how="left")


def _single_stock_daily_ledger(
    nav: pd.DataFrame,
    orders: pd.DataFrame,
    trades: pd.DataFrame,
    positions: pd.DataFrame,
) -> pd.DataFrame:
    if nav.empty:
        return pd.DataFrame()

    ledger = nav.copy()
    ledger["date"] = pd.to_datetime(ledger["date"]).dt.date

    if not trades.empty:
        trade_rows = trades.copy()
        trade_rows["date"] = pd.to_datetime(trade_rows["date"]).dt.date
        trade_rows["buy_quantity"] = trade_rows.apply(
            lambda row: row["quantity"] if row["side"] == "BUY" else 0,
            axis=1,
        )
        trade_rows["sell_quantity"] = trade_rows.apply(
            lambda row: row["quantity"] if row["side"] == "SELL" else 0,
            axis=1,
        )
        trade_rows["buy_amount"] = trade_rows.apply(
            lambda row: row["notional"] if row["side"] == "BUY" else 0.0,
            axis=1,
        )
        trade_rows["sell_amount"] = trade_rows.apply(
            lambda row: row["notional"] if row["side"] == "SELL" else 0.0,
            axis=1,
        )
        trade_summary = trade_rows.groupby("date", as_index=False).agg(
            buy_quantity=("buy_quantity", "sum"),
            sell_quantity=("sell_quantity", "sum"),
            buy_amount=("buy_amount", "sum"),
            sell_amount=("sell_amount", "sum"),
            fee=("fee", "sum"),
        )
    else:
        trade_summary = pd.DataFrame(columns=["date", "buy_quantity", "sell_quantity", "buy_amount", "sell_amount", "fee"])

    if not orders.empty:
        order_rows = orders.copy()
        order_rows["date"] = pd.to_datetime(order_rows["date"]).dt.date
        order_summary = order_rows.groupby("date", as_index=False).agg(
            filled_orders=("status", lambda values: int((values == "filled").sum())),
            rejected_orders=("status", lambda values: int((values == "rejected").sum())),
        )
    else:
        order_summary = pd.DataFrame(columns=["date", "filled_orders", "rejected_orders"])

    if not positions.empty:
        position_rows = positions.copy()
        position_rows["date"] = pd.to_datetime(position_rows["date"]).dt.date
        position_summary = position_rows.groupby("date", as_index=False).agg(
            position_quantity=("quantity", "sum"),
            position_value=("market_value", "sum"),
            close_price=("close_price", "last"),
            position_weight=("weight", "sum"),
        )
    else:
        position_summary = pd.DataFrame(columns=["date", "position_quantity", "position_value", "close_price", "position_weight"])

    ledger = ledger.merge(trade_summary, on="date", how="left")
    ledger = ledger.merge(order_summary, on="date", how="left")
    ledger = ledger.merge(position_summary, on="date", how="left")
    fill_columns = [
        "buy_quantity", "sell_quantity", "buy_amount", "sell_amount", "fee",
        "filled_orders", "rejected_orders", "position_quantity", "position_value",
        "position_weight",
    ]
    for column in fill_columns:
        if column in ledger.columns:
            ledger[column] = ledger[column].fillna(0)
    ledger["net_trade_amount"] = ledger["buy_amount"] - ledger["sell_amount"]
    return ledger[
        [
            "date", "nav", "cash", "position_value", "position_quantity", "close_price",
            "position_weight", "gross_exposure", "buy_quantity", "sell_quantity",
            "buy_amount", "sell_amount", "net_trade_amount", "fee", "filled_orders",
            "rejected_orders", "drawdown",
        ]
    ]


def _portfolio_daily_ledger(
    nav: pd.DataFrame,
    orders: pd.DataFrame,
    trades: pd.DataFrame,
    positions: pd.DataFrame,
) -> pd.DataFrame:
    if nav.empty:
        return pd.DataFrame()

    ledger = nav.copy()
    ledger["date"] = pd.to_datetime(ledger["date"]).dt.date

    if not trades.empty:
        trade_rows = trades.copy()
        trade_rows["date"] = pd.to_datetime(trade_rows["date"]).dt.date
        trade_rows["buy_amount"] = trade_rows.apply(
            lambda row: row["notional"] if row["side"] == "BUY" else 0.0,
            axis=1,
        )
        trade_rows["sell_amount"] = trade_rows.apply(
            lambda row: row["notional"] if row["side"] == "SELL" else 0.0,
            axis=1,
        )
        trade_summary = trade_rows.groupby("date", as_index=False).agg(
            buy_amount=("buy_amount", "sum"),
            sell_amount=("sell_amount", "sum"),
            fee=("fee", "sum"),
            trade_count=("trade_id", "count"),
        )
    else:
        trade_summary = pd.DataFrame(columns=["date", "buy_amount", "sell_amount", "fee", "trade_count"])

    if not orders.empty:
        order_rows = orders.copy()
        order_rows["date"] = pd.to_datetime(order_rows["date"]).dt.date
        order_summary = order_rows.groupby("date", as_index=False).agg(
            filled_orders=("status", lambda values: int((values == "filled").sum())),
            rejected_orders=("status", lambda values: int((values == "rejected").sum())),
        )
    else:
        order_summary = pd.DataFrame(columns=["date", "filled_orders", "rejected_orders"])

    if not positions.empty:
        position_rows = positions.copy()
        position_rows["date"] = pd.to_datetime(position_rows["date"]).dt.date
        position_summary = position_rows.groupby("date", as_index=False).agg(
            holding_count=("asset_id", "nunique"),
            position_value=("market_value", "sum"),
        )
    else:
        position_summary = pd.DataFrame(columns=["date", "holding_count", "position_value"])

    ledger = ledger.merge(trade_summary, on="date", how="left")
    ledger = ledger.merge(order_summary, on="date", how="left")
    ledger = ledger.merge(position_summary, on="date", how="left")
    for column in [
        "buy_amount",
        "sell_amount",
        "fee",
        "trade_count",
        "filled_orders",
        "rejected_orders",
        "holding_count",
        "position_value",
    ]:
        if column in ledger.columns:
            ledger[column] = ledger[column].fillna(0)
    return ledger[
        [
            "date",
            "nav",
            "cash",
            "position_value",
            "gross_exposure",
            "holding_count",
            "buy_amount",
            "sell_amount",
            "fee",
            "trade_count",
            "filled_orders",
            "rejected_orders",
            "drawdown",
        ]
    ]


def _with_asset_labels(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "asset_id" not in frame.columns:
        return frame
    assets = _query(
        """
        SELECT asset_id,
               CASE
                   WHEN asset_id LIKE 'A_STOCK_%' THEN REPLACE(asset_id, 'A_STOCK_', '')
                   WHEN asset_id LIKE 'A_INDEX_%' THEN REPLACE(asset_id, 'A_INDEX_', '')
                   WHEN asset_id LIKE 'A_ETF_%' THEN REPLACE(asset_id, 'A_ETF_', '')
                   WHEN asset_id LIKE 'CRYPTO_%' THEN REPLACE(asset_id, 'CRYPTO_', '')
                   ELSE asset_id
               END AS asset_code,
               COALESCE(name, asset_id) AS asset_name
        FROM assets
        """
    )
    return frame.merge(assets, on="asset_id", how="left")


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
