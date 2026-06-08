from datetime import datetime, timezone
from pathlib import Path

import akshare as ak
import duckdb
import pandas as pd
import yaml


DB_PATH = Path("data/db/quant_lab.duckdb")
ASSETS_CONFIG_PATH = Path("configs/assets_ai.yaml")


def load_ai_watchlist(config_path: Path = ASSETS_CONFIG_PATH) -> list[dict]:
    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
    return config.get("manual_watchlist", [])


def fetch_etf_daily(
    symbol: str,
    start_date: str = "20200101",
    end_date: str = "20261231",
) -> pd.DataFrame:
    df = ak.fund_etf_hist_em(
        symbol=symbol,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust="qfq",
    )

    if df.empty:
        return df

    df = df.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "turnover",
        }
    )
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["asset_id"] = f"AI_ETF_{symbol}"
    df["source"] = "akshare"
    df["created_at"] = datetime.now(timezone.utc)

    return df[
        [
            "asset_id",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover",
            "source",
            "created_at",
        ]
    ]


def save_prices(prices: pd.DataFrame, db_path: Path = DB_PATH) -> None:
    if prices.empty:
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.register("prices_temp", prices)
        con.execute(
            """
            INSERT OR REPLACE INTO prices_daily
            SELECT
                asset_id,
                date,
                open,
                high,
                low,
                close,
                volume,
                turnover,
                source,
                created_at
            FROM prices_temp
            """
        )


def save_assets(watchlist: list[dict], db_path: Path = DB_PATH) -> None:
    if not watchlist:
        return

    rows = pd.DataFrame(
        [
            {
                "asset_id": f"AI_ETF_{item['symbol']}",
                "symbol": item["symbol"],
                "name": item.get("name", item["symbol"]),
                "market": "cn",
                "asset_type": "etf",
                "theme": item.get("theme", ""),
                "is_active": True,
                "liquidity_tier": "watchlist",
                "created_at": datetime.now(timezone.utc),
            }
            for item in watchlist
        ]
    )

    with duckdb.connect(str(db_path)) as con:
        con.register("assets_temp", rows)
        con.execute(
            """
            INSERT OR REPLACE INTO assets
            SELECT
                asset_id,
                symbol,
                name,
                market,
                asset_type,
                theme,
                is_active,
                liquidity_tier,
                created_at
            FROM assets_temp
            """
        )


def update_ai_market_prices(
    start_date: str = "20200101",
    end_date: str = "20261231",
) -> pd.DataFrame:
    watchlist = load_ai_watchlist()
    frames = []

    for asset in watchlist:
        symbol = asset["symbol"]
        print(f"Fetching AI market ETF {symbol} ({asset.get('name', symbol)})")
        df = fetch_etf_daily(symbol, start_date=start_date, end_date=end_date)
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    prices = pd.concat(frames, ignore_index=True)
    save_assets(watchlist)
    save_prices(prices)
    return prices


def main() -> None:
    prices = update_ai_market_prices()
    print(f"AI market prices saved: {len(prices)} rows")


if __name__ == "__main__":
    main()
