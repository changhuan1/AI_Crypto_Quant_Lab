import pandas as pd


def classify_btc_risk_regime(features: pd.DataFrame) -> str:
    btc = features.loc[features["asset_id"] == "CRYPTO_BTC_USDT"].sort_values("date")
    if btc.empty:
        return "unknown"

    latest = btc.iloc[-1]
    above_ma_120 = latest["close"] > latest["ma_120"]
    ret_20d = latest["ret_20d"]
    volatility_20d = latest["volatility_20d"]

    if pd.isna(latest["ma_120"]) or pd.isna(ret_20d) or pd.isna(volatility_20d):
        return "unknown"

    if not above_ma_120 and ret_20d < 0:
        return "risk_off"

    if above_ma_120 and ret_20d > 0 and volatility_20d < 0.06:
        return "risk_on"

    return "neutral"
