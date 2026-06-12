from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import requests
from dotenv import load_dotenv

from src.jobs.init_db import DB_PATH


DEFAULT_TUSHARE_API_URL = "http://api.tushare.pro"


class TushareClient:
    def __init__(
        self,
        token: str | None = None,
        api_url: str | None = None,
        timeout: int = 30,
        pause_seconds: float = 0.25,
    ) -> None:
        load_dotenv()
        self.token = token or os.getenv("TUSHARE_TOKEN", "")
        self.api_url = api_url or os.getenv("TUSHARE_API_URL", DEFAULT_TUSHARE_API_URL)
        self.timeout = timeout
        self.pause_seconds = pause_seconds
        if not self.token:
            raise RuntimeError("TUSHARE_TOKEN is not configured. Put it in local .env first.")

    def query(
        self,
        api_name: str,
        params: dict[str, Any] | None = None,
        fields: str = "",
    ) -> pd.DataFrame:
        payload = {
            "api_name": api_name,
            "token": self.token,
            "params": params or {},
            "fields": fields,
        }
        response = requests.post(self.api_url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        result = response.json()
        if result.get("code") != 0:
            message = result.get("msg") or "unknown Tushare error"
            raise RuntimeError(f"Tushare API {api_name} failed: {message}")
        data = result.get("data") or {}
        frame = pd.DataFrame(data.get("items", []), columns=data.get("fields", []))
        if self.pause_seconds > 0:
            time.sleep(self.pause_seconds)
        return frame


def fetch_trade_calendar(
    client: TushareClient,
    start_date: str,
    end_date: str,
    exchange: str = "SSE",
) -> pd.DataFrame:
    frame = client.query(
        "trade_cal",
        params={"exchange": exchange, "start_date": start_date, "end_date": end_date},
        fields="exchange,cal_date,is_open,pretrade_date",
    )
    if frame.empty:
        return frame

    frame = frame.rename(columns={"cal_date": "date", "pretrade_date": "previous_open_date"})
    frame["market"] = exchange
    frame["date"] = pd.to_datetime(frame["date"], format="%Y%m%d").dt.date
    frame["is_open"] = frame["is_open"].astype(int).astype(bool)
    frame["previous_open_date"] = pd.to_datetime(
        frame["previous_open_date"].replace("", pd.NA),
        format="%Y%m%d",
        errors="coerce",
    ).dt.date
    open_dates = frame.loc[frame["is_open"], "date"].sort_values().tolist()
    next_open = {date: open_dates[index + 1] if index + 1 < len(open_dates) else None for index, date in enumerate(open_dates)}
    frame["next_open_date"] = frame["date"].map(next_open)
    frame["source"] = "tushare"
    frame["created_at"] = datetime.now(timezone.utc)
    return frame[["market", "date", "is_open", "previous_open_date", "next_open_date", "source", "created_at"]]


def fetch_stock_basic(client: TushareClient) -> pd.DataFrame:
    return client.query(
        "stock_basic",
        params={"list_status": "L"},
        fields="ts_code,symbol,name,area,industry,market,list_date",
    )


def fetch_index_weight(
    client: TushareClient,
    index_code: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    frame = client.query(
        "index_weight",
        params={"index_code": index_code, "start_date": start_date, "end_date": end_date},
        fields="index_code,con_code,trade_date,weight",
    )
    if frame.empty:
        return frame
    frame = frame.rename(columns={"index_code": "index_id", "con_code": "asset_id", "trade_date": "date"})
    frame["asset_id"] = frame["asset_id"].map(tushare_code_to_asset_id)
    frame["date"] = pd.to_datetime(frame["date"], format="%Y%m%d").dt.date
    frame["weight"] = pd.to_numeric(frame["weight"], errors="coerce")
    frame["source"] = "tushare"
    frame["created_at"] = datetime.now(timezone.utc)
    return frame[["index_id", "date", "asset_id", "weight", "source", "created_at"]]


def fetch_stock_limits(
    client: TushareClient,
    trade_date: str,
) -> pd.DataFrame:
    frame = client.query(
        "stk_limit",
        params={"trade_date": trade_date},
        fields="trade_date,ts_code,up_limit,down_limit",
    )
    if frame.empty:
        return frame
    frame = frame.rename(columns={"trade_date": "date", "ts_code": "asset_id"})
    frame["asset_id"] = frame["asset_id"].map(tushare_code_to_asset_id)
    frame["date"] = pd.to_datetime(frame["date"], format="%Y%m%d").dt.date
    frame["up_limit"] = pd.to_numeric(frame["up_limit"], errors="coerce")
    frame["down_limit"] = pd.to_numeric(frame["down_limit"], errors="coerce")
    return frame[["asset_id", "date", "up_limit", "down_limit"]]


def fetch_suspend_daily(
    client: TushareClient,
    trade_date: str,
) -> pd.DataFrame:
    frame = client.query(
        "suspend_d",
        params={"trade_date": trade_date},
        fields="ts_code,suspend_date,resume_date,ann_date,suspend_reason,reason_type",
    )
    if frame.empty:
        return frame
    frame = frame.rename(columns={"ts_code": "asset_id", "suspend_date": "date"})
    frame["asset_id"] = frame["asset_id"].map(tushare_code_to_asset_id)
    frame["date"] = pd.to_datetime(frame["date"], format="%Y%m%d", errors="coerce").dt.date
    return frame[["asset_id", "date"]].dropna()


def build_asset_status_from_tushare(
    prices: pd.DataFrame,
    stock_basic: pd.DataFrame,
    limits: pd.DataFrame,
    suspensions: pd.DataFrame,
) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()

    base = prices.loc[prices["asset_id"].str.startswith("A_STOCK_"), ["asset_id", "date", "close"]].copy()
    base["date"] = pd.to_datetime(base["date"]).dt.date
    base = base.drop_duplicates(["asset_id", "date"])

    if not limits.empty:
        base = base.merge(limits, on=["asset_id", "date"], how="left")
    else:
        base["up_limit"] = pd.NA
        base["down_limit"] = pd.NA
    base["close"] = pd.to_numeric(base["close"], errors="coerce")
    base["up_limit"] = pd.to_numeric(base["up_limit"], errors="coerce")
    base["down_limit"] = pd.to_numeric(base["down_limit"], errors="coerce")

    suspension_keys = set()
    if not suspensions.empty:
        suspension_keys = set(zip(suspensions["asset_id"], suspensions["date"]))

    st_assets = set()
    listed_dates: dict[str, object] = {}
    if not stock_basic.empty:
        stock_basic = stock_basic.copy()
        stock_basic["asset_id"] = stock_basic["ts_code"].map(tushare_code_to_asset_id)
        st_assets = set(stock_basic.loc[stock_basic["name"].fillna("").str.contains("ST", case=False), "asset_id"])
        stock_basic["list_date"] = pd.to_datetime(stock_basic["list_date"], format="%Y%m%d", errors="coerce").dt.date
        listed_dates = dict(zip(stock_basic["asset_id"], stock_basic["list_date"]))

    base["is_suspended"] = [(asset_id, date_value) in suspension_keys for asset_id, date_value in zip(base["asset_id"], base["date"])]
    base["is_st"] = base["asset_id"].isin(st_assets)
    base["is_limit_up"] = False
    base.loc[base["up_limit"].notna(), "is_limit_up"] = (
        base.loc[base["up_limit"].notna(), "close"] >= base.loc[base["up_limit"].notna(), "up_limit"]
    )
    base["is_limit_down"] = False
    base.loc[base["down_limit"].notna(), "is_limit_down"] = (
        base.loc[base["down_limit"].notna(), "close"] <= base.loc[base["down_limit"].notna(), "down_limit"]
    )
    base["is_tradable"] = ~(base["is_suspended"] | base["is_st"])
    base["listed_days"] = [
        (pd.Timestamp(date_value) - pd.Timestamp(listed_dates[asset_id])).days
        if asset_id in listed_dates and pd.notna(listed_dates[asset_id])
        else None
        for asset_id, date_value in zip(base["asset_id"], base["date"])
    ]
    source_parts = ["tushare"]
    if limits.empty:
        source_parts.append("no_limit")
    if suspensions.empty:
        source_parts.append("no_suspend")
    if stock_basic.empty:
        source_parts.append("no_stock_basic")
    base["source"] = "_".join(source_parts)
    base["created_at"] = datetime.now(timezone.utc)
    return base[
        [
            "asset_id",
            "date",
            "is_tradable",
            "is_suspended",
            "is_st",
            "is_limit_up",
            "is_limit_down",
            "up_limit",
            "down_limit",
            "listed_days",
            "source",
            "created_at",
        ]
    ]


def save_trade_calendar(calendar: pd.DataFrame, db_path: Path = DB_PATH) -> None:
    _insert_or_replace(db_path, "trading_calendar", calendar)


def save_stock_basic_to_assets(stock_basic: pd.DataFrame, db_path: Path = DB_PATH) -> None:
    if stock_basic.empty:
        return
    rows = stock_basic.copy()
    rows["asset_id"] = rows["ts_code"].map(tushare_code_to_asset_id)
    rows["symbol"] = rows["ts_code"]
    rows["market"] = "cn_a_share"
    rows["asset_type"] = "stock"
    rows["theme"] = rows["industry"].fillna("")
    rows["is_active"] = True
    rows["liquidity_tier"] = None
    rows["created_at"] = datetime.now(timezone.utc)
    rows = rows[["asset_id", "symbol", "name", "market", "asset_type", "theme", "is_active", "liquidity_tier", "created_at"]]
    _insert_or_replace(db_path, "assets", rows)


def save_index_constituents(constituents: pd.DataFrame, db_path: Path = DB_PATH) -> None:
    _insert_or_replace(db_path, "index_constituents_history", constituents)


def save_asset_status(status: pd.DataFrame, db_path: Path = DB_PATH) -> None:
    _insert_or_replace(db_path, "asset_status_daily", status)


def load_prices_for_status(start_date: str, end_date: str, db_path: Path = DB_PATH) -> pd.DataFrame:
    with duckdb.connect(str(db_path)) as con:
        return con.execute(
            """
            SELECT asset_id, date, close
            FROM prices_daily
            WHERE asset_id LIKE 'A_STOCK_%'
              AND date >= ?
              AND date <= ?
            ORDER BY asset_id, date
            """,
            [pd.to_datetime(start_date).date(), pd.to_datetime(end_date).date()],
        ).df()


def tushare_code_to_asset_id(ts_code: str) -> str:
    if not isinstance(ts_code, str) or "." not in ts_code:
        return ts_code
    code = ts_code.split(".")[0]
    return f"A_STOCK_{code}"


def _insert_or_replace(db_path: Path, table: str, frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    with duckdb.connect(str(db_path)) as con:
        con.register("rows_to_save", frame)
        con.execute(f"INSERT OR REPLACE INTO {table} SELECT * FROM rows_to_save")
