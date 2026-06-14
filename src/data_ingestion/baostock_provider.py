from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import baostock as bs
import duckdb
import pandas as pd

from src.jobs.init_db import DB_PATH


HISTORY_FIELDS = (
    "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,"
    "tradestatus,pctChg,peTTM,pbMRQ,psTTM,isST"
)


class BaostockSession:
    def __enter__(self) -> "BaostockSession":
        result = bs.login()
        if result.error_code != "0":
            raise RuntimeError(f"Baostock login failed: {result.error_msg}")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        bs.logout()

    def query_shanghai_universe(self, trade_date: str) -> pd.DataFrame:
        result = bs.query_all_stock(day=trade_date)
        frame = _result_frame(result)
        if frame.empty:
            return frame
        frame = frame.loc[frame["code"].str.match(r"^sh\.6\d{5}$", na=False)].copy()
        frame["asset_id"] = frame["code"].map(baostock_code_to_asset_id)
        frame["date"] = pd.to_datetime(trade_date).date()
        frame["is_tradable"] = frame["tradeStatus"].astype(str).eq("1")
        frame["source"] = "baostock"
        frame["created_at"] = datetime.now(timezone.utc)
        return frame[["asset_id", "date", "code_name", "is_tradable", "source", "created_at"]]

    def query_trade_dates(self, start_date: str, end_date: str) -> list[str]:
        result = bs.query_trade_dates(start_date=start_date, end_date=end_date)
        frame = _result_frame(result)
        if frame.empty:
            return []
        return frame.loc[frame["is_trading_day"].astype(str).eq("1"), "calendar_date"].tolist()

    def query_stock_history(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        result = bs.query_history_k_data_plus(
            code,
            HISTORY_FIELDS,
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="3",
        )
        frame = _result_frame(result)
        if frame.empty:
            return frame
        frame["asset_id"] = frame["code"].map(baostock_code_to_asset_id)
        frame["date"] = pd.to_datetime(frame["date"]).dt.date
        numeric_columns = [
            "open", "high", "low", "close", "preclose", "volume", "amount", "turn", "pctChg",
            "peTTM", "pbMRQ", "psTTM",
        ]
        for column in numeric_columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["is_tradable"] = frame["tradestatus"].astype(str).eq("1")
        frame["is_st"] = frame["isST"].astype(str).eq("1")
        frame["source"] = "baostock"
        frame["created_at"] = datetime.now(timezone.utc)
        return frame


def save_baostock_history(frame: pd.DataFrame, db_path: Path = DB_PATH) -> None:
    if frame.empty:
        return
    raw = frame.rename(
        columns={"preclose": "pre_close", "pctChg": "pct_change", "amount": "turnover"}
    )[
        [
            "asset_id", "date", "open", "high", "low", "close", "pre_close", "pct_change",
            "volume", "turnover", "source", "created_at",
        ]
    ].copy()
    raw["change"] = raw["close"] - raw["pre_close"]
    raw = raw[
        [
            "asset_id", "date", "open", "high", "low", "close", "pre_close", "change",
            "pct_change", "volume", "turnover", "source", "created_at",
        ]
    ]

    indicators = frame.rename(
        columns={"turn": "turnover_rate", "peTTM": "pe_ttm", "pbMRQ": "pb", "psTTM": "ps_ttm"}
    )[["asset_id", "date", "turnover_rate", "pe_ttm", "pb", "ps_ttm", "source", "created_at"]].copy()
    for column in [
        "turnover_rate_free", "volume_ratio", "pe", "ps", "dividend_yield", "dividend_yield_ttm",
        "total_share", "float_share", "free_share", "total_market_value", "circulating_market_value",
    ]:
        indicators[column] = None
    indicators = indicators[
        [
            "asset_id", "date", "turnover_rate", "turnover_rate_free", "volume_ratio", "pe", "pe_ttm",
            "pb", "ps", "ps_ttm", "dividend_yield", "dividend_yield_ttm", "total_share", "float_share",
            "free_share", "total_market_value", "circulating_market_value", "source", "created_at",
        ]
    ]

    status = frame[
        ["asset_id", "date", "is_tradable", "is_st", "source", "created_at"]
    ].copy()
    status["is_suspended"] = ~status["is_tradable"]
    status["is_limit_up"] = False
    status["is_limit_down"] = False
    status["up_limit"] = None
    status["down_limit"] = None
    status["listed_days"] = None
    status = status[
        [
            "asset_id", "date", "is_tradable", "is_suspended", "is_st", "is_limit_up", "is_limit_down",
            "up_limit", "down_limit", "listed_days", "source", "created_at",
        ]
    ]

    with duckdb.connect(str(db_path)) as con:
        for table, rows in [
            ("raw_prices_daily", raw),
            ("daily_market_indicators", indicators),
            ("asset_status_daily", status),
        ]:
            con.register("rows_to_save", rows)
            con.execute(f"INSERT OR REPLACE INTO {table} SELECT * FROM rows_to_save")
            con.unregister("rows_to_save")


def save_market_universe(frame: pd.DataFrame, db_path: Path = DB_PATH) -> None:
    if frame.empty:
        return
    rows = frame.rename(columns={"code_name": "asset_name"}).copy()
    rows["market"] = "SSE"
    rows["is_listed"] = True
    rows = rows[
        ["market", "date", "asset_id", "asset_name", "is_listed", "is_tradable", "source", "created_at"]
    ]
    with duckdb.connect(str(db_path)) as con:
        snapshot_dates = rows[["market", "date"]].drop_duplicates().itertuples(index=False, name=None)
        for market, date_value in snapshot_dates:
            con.execute("DELETE FROM market_universe_daily WHERE market = ? AND date = ?", [market, date_value])
        con.register("rows_to_save", rows)
        con.execute("INSERT OR REPLACE INTO market_universe_daily SELECT * FROM rows_to_save")


def baostock_code_to_asset_id(code: str) -> str:
    return f"A_STOCK_{code.split('.')[-1]}"


def asset_id_to_baostock_code(asset_id: str) -> str:
    code = asset_id.replace("A_STOCK_", "")
    return f"sh.{code}"


def _result_frame(result) -> pd.DataFrame:
    if result.error_code != "0":
        raise RuntimeError(f"Baostock query failed: {result.error_msg}")
    rows = []
    while result.next():
        rows.append(result.get_row_data())
    return pd.DataFrame(rows, columns=result.fields)
