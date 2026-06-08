import pandas as pd

from src.strategies.crypto_scoring import safe_zscore


def calculate_ai_market_score(features: pd.DataFrame) -> pd.DataFrame:
    df = features.copy()
    by_date = df.groupby("date", group_keys=False)

    df["z_mom_20"] = by_date["ret_20d"].transform(safe_zscore)
    df["z_mom_60"] = by_date["ret_60d"].transform(safe_zscore)
    df["z_turnover"] = by_date["turnover"].transform(safe_zscore)
    df["z_volatility"] = by_date["volatility_20d"].transform(safe_zscore)
    df["z_relative"] = by_date["relative_strength_20d"].transform(safe_zscore)

    df["price_momentum"] = 0.4 * df["z_mom_20"] + 0.4 * df["z_mom_60"] + 0.2 * df["z_relative"]
    df["volume_confirmation"] = df["z_turnover"]

    # v0.1 placeholders. Later versions can merge GitHub/Hugging Face/news heat here.
    df["ai_news_heat"] = 0.0
    df["open_source_heat"] = 0.0
    df["risk_penalty"] = 0.7 * df["z_volatility"] + 0.3 * (1 - df["above_ma_120"])

    df["ai_market_score"] = (
        0.30 * df["price_momentum"]
        + 0.20 * df["volume_confirmation"]
        + 0.20 * df["ai_news_heat"]
        + 0.20 * df["open_source_heat"]
        - 0.10 * df["risk_penalty"]
    )

    return df
