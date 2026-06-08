from datetime import datetime, timezone
from pathlib import Path
import argparse

import akshare as ak
import duckdb
import pandas as pd
import yaml


DB_PATH = Path("data/db/quant_lab.duckdb")
ASSETS_CONFIG_PATH = Path("configs/assets_a_share.yaml")
DEFAULT_INDEX_SYMBOL = "000001"
DEFAULT_BENCHMARK_SYMBOL = "sh000001"


def load_a_share_config(config_path: Path = ASSETS_CONFIG_PATH) -> dict:
    with config_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def fetch_index_constituents(index_symbol: str = DEFAULT_INDEX_SYMBOL) -> pd.DataFrame:
    df = ak.index_stock_cons(symbol=index_symbol)
    df = df.rename(columns={"品种代码": "symbol", "品种名称": "name", "纳入日期": "included_at"})
    df["symbol"] = df["symbol"].astype(str).str.zfill(6)
    df["asset_id"] = "A_STOCK_" + df["symbol"]
    return df[["asset_id", "symbol", "name", "included_at"]]


def fetch_stock_daily(
    symbol: str,
    start_date: str = "20200101",
    end_date: str = "20261231",
) -> pd.DataFrame:
    try:
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
        source = "akshare_eastmoney"
    except Exception:
        df = ak.stock_zh_a_daily(
            symbol=f"sh{symbol}",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
        source = "akshare_sina"

    if df.empty:
        return df

    if "amount" in df.columns and "成交额" not in df.columns:
        if "turnover" in df.columns:
            df = df.drop(columns=["turnover"])
        df["成交额"] = df["amount"]

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
    df["asset_id"] = f"A_STOCK_{symbol}"
    df["source"] = source
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


def fetch_benchmark_daily(
    symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    start_date: str = "20200101",
    end_date: str = "20261231",
) -> pd.DataFrame:
    df = ak.stock_zh_index_daily(symbol=symbol)
    if df.empty:
        return df

    df = df.rename(columns={"date": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    start = pd.to_datetime(start_date).date()
    end = pd.to_datetime(end_date).date()
    df = df[(df["date"] >= start) & (df["date"] <= end)].copy()
    df["asset_id"] = "A_INDEX_000001"
    df["turnover"] = pd.NA
    df["source"] = "akshare_sina"
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


def save_assets(constituents: pd.DataFrame, db_path: Path = DB_PATH) -> None:
    if constituents.empty:
        return

    rows = pd.DataFrame(
        [
            {
                "asset_id": row["asset_id"],
                "symbol": row["symbol"],
                "name": row["name"],
                "market": "cn_a_share",
                "asset_type": "index_constituent",
                "theme": "shanghai_composite",
                "is_active": True,
                "liquidity_tier": "unclassified",
                "created_at": datetime.now(timezone.utc),
            }
            for _, row in constituents.iterrows()
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


def update_a_share_market_prices(
    start_date: str = "20200101",
    end_date: str = "20261231",
    limit: int | None = None,
    include_benchmark: bool = True,
) -> pd.DataFrame:
    config = load_a_share_config()
    index_symbol = config["a_share_market"]["watchlist_rules"].get(
        "index_symbol",
        DEFAULT_INDEX_SYMBOL,
    )
    constituents = fetch_index_constituents(index_symbol)
    if limit is not None:
        constituents = constituents.head(limit)

    frames = []

    if include_benchmark:
        print("Fetching benchmark index 000001 (上证指数)")
        try:
            benchmark = fetch_benchmark_daily(start_date=start_date, end_date=end_date)
            if not benchmark.empty:
                frames.append(benchmark)
        except Exception as exc:
            print(f"Skipped benchmark index 000001: {exc}")

    for _, asset in constituents.iterrows():
        symbol = asset["symbol"]
        print(f"Fetching Shanghai Composite constituent {symbol} ({asset.get('name', symbol)})")
        try:
            df = fetch_stock_daily(symbol, start_date=start_date, end_date=end_date)
        except Exception as exc:
            print(f"Skipped {symbol}: {exc}")
            continue
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    prices = pd.concat(frames, ignore_index=True)
    save_assets(constituents)
    save_prices(prices)
    return prices


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="20200101")
    parser.add_argument("--end-date", default="20261231")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    prices = update_a_share_market_prices(
        start_date=args.start_date,
        end_date=args.end_date,
        limit=args.limit,
    )
    print(f"A-share market prices saved: {len(prices)} rows")


if __name__ == "__main__":
    main()
