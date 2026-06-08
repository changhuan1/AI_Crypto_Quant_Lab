import pandas as pd

from src.features.a_share_breadth import calculate_a_share_breadth
from src.strategies.crypto_scoring import safe_zscore


def calculate_a_share_market_score(features: pd.DataFrame) -> pd.DataFrame:
    df = features.copy()
    breadth = _extract_breadth_score(df)
    by_date = df.groupby("date", group_keys=False)

    df["z_mom_20"] = by_date["ret_20d"].transform(safe_zscore)
    df["z_mom_60"] = by_date["ret_60d"].transform(safe_zscore)
    df["z_turnover"] = by_date["turnover"].transform(safe_zscore)
    df["z_volatility"] = by_date["volatility_20d"].transform(safe_zscore)
    df["z_relative"] = by_date["relative_strength_20d"].transform(safe_zscore)

    df["price_momentum"] = 0.4 * df["z_mom_20"] + 0.4 * df["z_mom_60"] + 0.2 * df["z_relative"]
    df["volume_confirmation"] = df["z_turnover"]
    df = df.merge(breadth, on="date", how="left")
    df["breadth_proxy"] = df["breadth_score"].fillna(df["above_ma_120"])
    df["risk_penalty"] = 0.7 * df["z_volatility"] + 0.3 * (1 - df["above_ma_120"])

    df["a_share_market_score"] = (
        0.35 * df["price_momentum"]
        + 0.20 * df["volume_confirmation"]
        + 0.20 * df["breadth_proxy"]
        - 0.15 * df["risk_penalty"]
    )

    return df


def _extract_breadth_score(features: pd.DataFrame) -> pd.DataFrame:
    breadth = calculate_a_share_breadth(features)
    if breadth.empty:
        return pd.DataFrame(columns=["date", "breadth_score"])
    return breadth[["date", "breadth_score"]]
