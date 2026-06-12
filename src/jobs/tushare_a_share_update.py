from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from src.data_ingestion.tushare_provider import (
    TushareClient,
    build_asset_status_from_tushare,
    fetch_index_weight,
    fetch_stock_basic,
    fetch_stock_limits,
    fetch_suspend_daily,
    fetch_trade_calendar,
    load_prices_for_status,
    save_asset_status,
    save_index_constituents,
    save_stock_basic_to_assets,
    save_trade_calendar,
)


@dataclass
class StepResult:
    name: str
    status: str
    rows: int
    message: str


def run_tushare_update(
    start_date: str,
    end_date: str,
    index_code: str = "000001.SH",
    max_status_dates: int | None = 10,
    pause_seconds: float = 0.25,
) -> list[StepResult]:
    client = TushareClient(pause_seconds=pause_seconds)
    results: list[StepResult] = []

    calendar = _run_step(
        results,
        "trade_cal",
        lambda: fetch_trade_calendar(client, start_date=start_date, end_date=end_date),
    )
    if calendar is not None and not calendar.empty:
        save_trade_calendar(calendar)

    stock_basic = _run_step(results, "stock_basic", lambda: fetch_stock_basic(client))
    if stock_basic is not None and not stock_basic.empty:
        save_stock_basic_to_assets(stock_basic)

    constituents = _run_step(
        results,
        "index_weight",
        lambda: fetch_index_weight(client, index_code=index_code, start_date=start_date, end_date=end_date),
    )
    if constituents is not None and not constituents.empty:
        save_index_constituents(constituents)

    limits = []
    suspensions = []
    open_dates = _open_dates(calendar, start_date, end_date, max_status_dates)
    for trade_date in open_dates:
        limit_frame = _run_step(
            results,
            f"stk_limit:{trade_date}",
            lambda trade_date=trade_date: fetch_stock_limits(client, trade_date=trade_date),
        )
        if limit_frame is not None and not limit_frame.empty:
            limits.append(limit_frame)

        suspension_frame = _run_step(
            results,
            f"suspend_d:{trade_date}",
            lambda trade_date=trade_date: fetch_suspend_daily(client, trade_date=trade_date),
        )
        if suspension_frame is not None and not suspension_frame.empty:
            suspensions.append(suspension_frame)

    prices = load_prices_for_status(start_date, end_date)
    limit_rows = pd.concat(limits, ignore_index=True) if limits else pd.DataFrame()
    suspension_rows = pd.concat(suspensions, ignore_index=True) if suspensions else pd.DataFrame()
    status = build_asset_status_from_tushare(
        prices=prices,
        stock_basic=stock_basic if stock_basic is not None else pd.DataFrame(),
        limits=limit_rows,
        suspensions=suspension_rows,
    )
    if not status.empty:
        save_asset_status(status)
    results.append(StepResult("asset_status_daily", "success", len(status), "built from Tushare and local prices"))

    return results


def _run_step(results: list[StepResult], name: str, fn):
    try:
        frame = fn()
        rows = 0 if frame is None else len(frame)
        results.append(StepResult(name, "success", rows, "ok"))
        return frame
    except Exception as exc:
        results.append(StepResult(name, "failed", 0, str(exc)))
        return None


def _open_dates(
    calendar: pd.DataFrame | None,
    start_date: str,
    end_date: str,
    max_status_dates: int | None,
) -> list[str]:
    if max_status_dates == 0:
        return []
    if calendar is None or calendar.empty:
        dates = pd.bdate_range(start=pd.to_datetime(start_date), end=pd.to_datetime(end_date))
    else:
        dates = pd.to_datetime(calendar.loc[calendar["is_open"], "date"])
    if max_status_dates is not None:
        dates = dates.sort_values()[-max_status_dates:]
    return [date.strftime("%Y%m%d") for date in dates]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update professional A-share metadata through Tushare.")
    parser.add_argument("--start-date", default="20260101", help="YYYYMMDD")
    parser.add_argument("--end-date", default=datetime.now().strftime("%Y%m%d"), help="YYYYMMDD")
    parser.add_argument("--index-code", default="000001.SH", help="Tushare index code")
    parser.add_argument(
        "--max-status-dates",
        type=int,
        default=10,
        help="Limit stk_limit/suspend_d daily calls. Use 0 to skip, -1 for all open dates.",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.25,
        help="Pause between Tushare API calls. Low-frequency accounts may need 65 seconds.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    max_status_dates = None if args.max_status_dates < 0 else args.max_status_dates
    if max_status_dates == 0:
        max_status_dates = 0
    results = run_tushare_update(
        start_date=args.start_date,
        end_date=args.end_date,
        index_code=args.index_code,
        max_status_dates=max_status_dates,
        pause_seconds=args.pause_seconds,
    )
    for result in results:
        print(f"{result.name}: {result.status}, rows={result.rows}, message={result.message}")


if __name__ == "__main__":
    main()
