import pandas as pd


def add_relative_strength(
    features: pd.DataFrame,
    benchmark_asset_id: str = "CRYPTO_BTC_USDT",
    window: int = 20,
) -> pd.DataFrame:
    df = features.copy()
    benchmark = df.loc[df["asset_id"] == benchmark_asset_id, ["date", f"ret_{window}d"]]
    benchmark = benchmark.rename(columns={f"ret_{window}d": f"benchmark_ret_{window}d"})

    df = df.merge(benchmark, on="date", how="left")
    df[f"relative_strength_{window}d"] = (
        df[f"ret_{window}d"] - df[f"benchmark_ret_{window}d"]
    )
    return df.drop(columns=[f"benchmark_ret_{window}d"])
