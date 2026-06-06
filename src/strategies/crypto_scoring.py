import pandas as pd


def safe_zscore(values: pd.Series) -> pd.Series:
    if values.isna().all():
        return pd.Series(0.0, index=values.index)

    filled = values.astype(float).fillna(values.median())
    std = filled.std()
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=values.index)
    return (filled - filled.mean()) / std


def calculate_crypto_score(features: pd.DataFrame) -> pd.DataFrame:
    df = features.copy()
    by_date = df.groupby("date", group_keys=False)

    df["z_ret_7d"] = by_date["ret_7d"].transform(safe_zscore)
    df["z_ret_20d"] = by_date["ret_20d"].transform(safe_zscore)
    df["z_ret_60d"] = by_date["ret_60d"].transform(safe_zscore)
    df["z_volume"] = by_date["turnover"].transform(safe_zscore)
    df["z_relative_btc"] = by_date["relative_strength_20d"].transform(safe_zscore)
    df["z_volatility"] = by_date["volatility_20d"].transform(safe_zscore)

    df["price_momentum"] = (
        0.3 * df["z_ret_7d"]
        + 0.4 * df["z_ret_20d"]
        + 0.3 * df["z_ret_60d"]
    )
    df["volume_acceleration"] = df["z_volume"]
    df["relative_strength_vs_btc"] = df["z_relative_btc"]

    # v0.1 placeholders. Later versions can replace these with narrative/fundamental data.
    df["narrative_heat"] = 0.0
    df["fundamental_confirmation"] = 0.0
    df["risk_penalty"] = df["z_volatility"]

    df["crypto_score"] = (
        0.35 * df["price_momentum"]
        + 0.20 * df["volume_acceleration"]
        + 0.15 * df["relative_strength_vs_btc"]
        + 0.15 * df["narrative_heat"]
        + 0.10 * df["fundamental_confirmation"]
        - 0.20 * df["risk_penalty"]
    )

    return df
