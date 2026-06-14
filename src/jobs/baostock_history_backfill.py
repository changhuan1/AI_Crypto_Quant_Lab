from __future__ import annotations

import argparse

import duckdb

from src.data_ingestion.baostock_provider import (
    BaostockSession,
    asset_id_to_baostock_code,
    save_baostock_history,
    save_market_universe,
)
from src.jobs.init_db import DB_PATH, init_database


def run_history_backfill(
    start_date: str,
    end_date: str,
    limit: int | None = None,
    max_universe_dates: int | None = 5,
    universe_only: bool = False,
) -> dict[str, int]:
    init_database()
    result = {"assets": 0, "price_rows": 0, "universe_dates": 0, "universe_rows": 0, "failed_assets": 0}

    with BaostockSession() as session:
        trade_dates = session.query_trade_dates(start_date, end_date)
        if max_universe_dates is not None:
            trade_dates = trade_dates[-max_universe_dates:]
        for index, trade_date in enumerate(trade_dates, start=1):
            print(f"[universe {index}/{len(trade_dates)}] {trade_date}")
            universe = session.query_shanghai_universe(trade_date)
            save_market_universe(universe)
            result["universe_dates"] += 1
            result["universe_rows"] += len(universe)

        if universe_only:
            return result

        asset_ids = _shanghai_asset_ids(limit)
        result["assets"] = len(asset_ids)
        for index, asset_id in enumerate(asset_ids, start=1):
            code = asset_id_to_baostock_code(asset_id)
            print(f"[prices {index}/{len(asset_ids)}] {code}")
            try:
                history = session.query_stock_history(code, start_date, end_date)
                save_baostock_history(history)
                result["price_rows"] += len(history)
            except Exception as exc:
                result["failed_assets"] += 1
                print(f"  failed: {exc}")

    return result


def _shanghai_asset_ids(limit: int | None) -> list[str]:
    sql = """
        SELECT asset_id
        FROM assets
        WHERE asset_id LIKE 'A_STOCK_%'
          AND (symbol LIKE '%.SH' OR REPLACE(asset_id, 'A_STOCK_', '') LIKE '6%')
        ORDER BY asset_id
    """
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        rows = con.execute(sql).fetchall()
    asset_ids = [row[0] for row in rows]
    return asset_ids[:limit] if limit is not None else asset_ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill Shanghai A-share history from Baostock.")
    parser.add_argument("--start-date", default="2024-01-01", help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=5, help="Asset count for testing. Omit with -1 for all assets.")
    parser.add_argument(
        "--max-universe-dates",
        type=int,
        default=5,
        help="Latest N trading dates for universe snapshots. Use -1 for every date.",
    )
    parser.add_argument("--universe-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    limit = None if args.limit < 0 else args.limit
    max_universe_dates = None if args.max_universe_dates < 0 else args.max_universe_dates
    result = run_history_backfill(
        start_date=args.start_date,
        end_date=args.end_date,
        limit=limit,
        max_universe_dates=max_universe_dates,
        universe_only=args.universe_only,
    )
    print("Baostock history backfill completed")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
