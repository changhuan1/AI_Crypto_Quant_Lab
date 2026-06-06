import pandas as pd


def add_price_features(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices.sort_values(["asset_id", "date"]).copy()
    by_asset = df.groupby("asset_id", group_keys=False)

    df["ret_1d"] = by_asset["close"].pct_change(1)
    df["ret_7d"] = by_asset["close"].pct_change(7)
    df["ret_20d"] = by_asset["close"].pct_change(20)
    df["ret_60d"] = by_asset["close"].pct_change(60)

    df["ma_20"] = by_asset["close"].transform(lambda s: s.rolling(20).mean())
    df["ma_60"] = by_asset["close"].transform(lambda s: s.rolling(60).mean())
    df["ma_120"] = by_asset["close"].transform(lambda s: s.rolling(120).mean())
    df["above_ma_120"] = (df["close"] > df["ma_120"]).astype(float)

    df["volatility_20d"] = by_asset["ret_1d"].transform(lambda s: s.rolling(20).std())
    df["volatility_60d"] = by_asset["ret_1d"].transform(lambda s: s.rolling(60).std())

    return df
