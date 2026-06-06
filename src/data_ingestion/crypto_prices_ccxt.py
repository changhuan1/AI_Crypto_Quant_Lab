from datetime import datetime, timezone
from pathlib import Path

import ccxt
import duckdb
import pandas as pd


DB_PATH = Path("data/db/quant_lab.duckdb")
DEFAULT_EXCHANGE_ID = "okx"
DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT"]


def fetch_crypto_ohlcv(
    exchange_id: str,
    symbol: str,
    timeframe: str = "1d",
    limit: int = 1000,
) -> pd.DataFrame:
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({"enableRateLimit": True})

    timeframe_ms = exchange.parse_timeframe(timeframe) * 1000
    batch_limit = min(limit, 300)
    since = exchange.milliseconds() - timeframe_ms * limit
    rows = []

    while len(rows) < limit:
        batch = exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            since=since,
            limit=min(batch_limit, limit - len(rows)),
        )

        if not batch:
            break

        rows.extend(batch)
        next_since = batch[-1][0] + timeframe_ms

        if next_since <= since:
            break
        since = next_since

        if len(batch) < batch_limit:
            break

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])

    if df.empty:
        return df

    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").tail(limit)

    df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.date
    df["asset_id"] = "CRYPTO_" + symbol.replace("/", "_")
    df["turnover"] = df["close"] * df["volume"]
    df["source"] = exchange_id
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


def save_prices(df: pd.DataFrame, db_path: Path = DB_PATH) -> None:
    if df.empty:
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.register("prices_temp", df)
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


def update_crypto_prices(
    exchange_id: str = DEFAULT_EXCHANGE_ID,
    symbols: list[str] | None = None,
    timeframe: str = "1d",
    limit: int = 1000,
) -> pd.DataFrame:
    selected_symbols = symbols or DEFAULT_SYMBOLS
    frames = []

    for symbol in selected_symbols:
        print(f"Fetching {symbol} from {exchange_id}")
        df = fetch_crypto_ohlcv(exchange_id, symbol, timeframe=timeframe, limit=limit)
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    save_prices(result)
    return result


def main() -> None:
    result = update_crypto_prices()
    print(f"Crypto prices saved: {len(result)} rows")


if __name__ == "__main__":
    main()
