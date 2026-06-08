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


def classify_ai_market_risk_regime(features: pd.DataFrame) -> str:
    latest_date = features["date"].max()
    latest = features.loc[features["date"] == latest_date].copy()

    required = latest.dropna(subset=["ma_120", "ret_20d", "volatility_20d"])
    if required.empty:
        return "unknown"

    above_ratio = required["above_ma_120"].mean()
    avg_ret_20d = required["ret_20d"].mean()
    avg_vol_20d = required["volatility_20d"].mean()

    if above_ratio < 0.35 and avg_ret_20d < 0:
        return "risk_off"

    if above_ratio >= 0.60 and avg_ret_20d > 0 and avg_vol_20d < 0.04:
        return "risk_on"

    return "neutral"
