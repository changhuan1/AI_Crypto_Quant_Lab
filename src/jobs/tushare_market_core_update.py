from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from src.data_ingestion.tushare_provider import (
    TushareClient,
    fetch_adjustment_factors,
    fetch_asset_name_history,
    fetch_daily_market_indicators,
    fetch_raw_daily,
    fetch_stock_basic,
    fetch_trade_calendar,
    save_adjustment_factors,
    save_asset_name_history,
    save_daily_market_indicators,
    save_raw_daily,
    save_stock_basic_to_assets,
    save_trade_calendar,
)
from src.jobs.init_db import init_database


@dataclass
class UpdateSummary:
    trade_dates: int = 0
    raw_price_rows: int = 0
    adjustment_rows: int = 0
    indicator_rows: int = 0
    name_history_rows: int = 0
    failed_steps: int = 0


def run_market_core_update(
    start_date: str,
    end_date: str,
    max_trade_dates: int | None = None,
    pause_seconds: float = 0.25,
    include_reference_data: bool = True,
) -> UpdateSummary:
    init_database()
    client = TushareClient(pause_seconds=pause_seconds)
    summary = UpdateSummary()

    calendar = fetch_trade_calendar(client, start_date=start_date, end_date=end_date)
    save_trade_calendar(calendar)
    trade_dates = _open_trade_dates(calendar, max_trade_dates)
    summary.trade_dates = len(trade_dates)

    if include_reference_data:
        summary.name_history_rows += _run_reference_updates(client, summary)

    for index, trade_date in enumerate(trade_dates, start=1):
        print(f"[{index}/{len(trade_dates)}] Updating Shanghai market core data for {trade_date}")
        summary.raw_price_rows += _fetch_and_save(
            "daily",
            lambda trade_date=trade_date: fetch_raw_daily(client, trade_date),
            save_raw_daily,
            summary,
        )
        summary.adjustment_rows += _fetch_and_save(
            "adj_factor",
            lambda trade_date=trade_date: fetch_adjustment_factors(client, trade_date),
            save_adjustment_factors,
            summary,
        )
        summary.indicator_rows += _fetch_and_save(
            "daily_basic",
            lambda trade_date=trade_date: fetch_daily_market_indicators(client, trade_date),
            save_daily_market_indicators,
            summary,
        )

    return summary


def _run_reference_updates(client: TushareClient, summary: UpdateSummary) -> int:
    rows = 0
    rows += _fetch_and_save("stock_basic", lambda: fetch_stock_basic(client), save_stock_basic_to_assets, summary)
    name_rows = _fetch_and_save(
        "namechange",
        lambda: fetch_asset_name_history(client),
        save_asset_name_history,
        summary,
    )
    return name_rows


def _fetch_and_save(name: str, fetch, save, summary: UpdateSummary) -> int:
    try:
        frame = fetch()
        if frame is None or frame.empty:
            print(f"  {name}: no rows")
            return 0
        save(frame)
        print(f"  {name}: saved {len(frame)} rows")
        return len(frame)
    except Exception as exc:
        summary.failed_steps += 1
        print(f"  {name}: failed: {exc}")
        return 0


def _open_trade_dates(calendar: pd.DataFrame, max_trade_dates: int | None) -> list[str]:
    dates = pd.to_datetime(calendar.loc[calendar["is_open"], "date"]).sort_values()
    if max_trade_dates is not None:
        dates = dates.iloc[-max_trade_dates:]
    return [value.strftime("%Y%m%d") for value in dates]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update canonical Shanghai A-share market data from Tushare.")
    parser.add_argument("--start-date", default="20240101", help="YYYYMMDD")
    parser.add_argument("--end-date", default=datetime.now().strftime("%Y%m%d"), help="YYYYMMDD")
    parser.add_argument(
        "--max-trade-dates",
        type=int,
        default=5,
        help="Only update the latest N open dates in the range. Use -1 for every open date.",
    )
    parser.add_argument("--pause-seconds", type=float, default=0.25)
    parser.add_argument("--skip-reference-data", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    max_trade_dates = None if args.max_trade_dates < 0 else args.max_trade_dates
    summary = run_market_core_update(
        start_date=args.start_date,
        end_date=args.end_date,
        max_trade_dates=max_trade_dates,
        pause_seconds=args.pause_seconds,
        include_reference_data=not args.skip_reference_data,
    )
    print("Market core update completed")
    print(f"trade_dates: {summary.trade_dates}")
    print(f"raw_price_rows: {summary.raw_price_rows}")
    print(f"adjustment_rows: {summary.adjustment_rows}")
    print(f"indicator_rows: {summary.indicator_rows}")
    print(f"name_history_rows: {summary.name_history_rows}")
    print(f"failed_steps: {summary.failed_steps}")


if __name__ == "__main__":
    main()
