import pandas as pd


BREADTH_ASSET_ID = "A_MARKET_000001"


def calculate_a_share_breadth(features: pd.DataFrame) -> pd.DataFrame:
    stocks = features.loc[features["asset_id"].str.startswith("A_STOCK_")].copy()
    if stocks.empty:
        return pd.DataFrame()

    rows = []
    for date, frame in stocks.groupby("date", sort=True):
        valid_ret = frame.dropna(subset=["ret_1d"])
        valid_ma = frame.dropna(subset=["above_ma_120"])
        valid_turnover = frame.dropna(subset=["turnover"])

        universe_count = int(frame["asset_id"].nunique())
        up_count = int((valid_ret["ret_1d"] > 0).sum())
        down_count = int((valid_ret["ret_1d"] < 0).sum())
        flat_count = int((valid_ret["ret_1d"] == 0).sum())
        above_ma_120_count = int((valid_ma["above_ma_120"] == 1).sum())

        rows.append(
            {
                "date": date,
                "universe_count": universe_count,
                "up_count": up_count,
                "down_count": down_count,
                "flat_count": flat_count,
                "up_ratio": _safe_ratio(up_count, len(valid_ret)),
                "down_ratio": _safe_ratio(down_count, len(valid_ret)),
                "above_ma_120_ratio": _safe_ratio(above_ma_120_count, len(valid_ma)),
                "median_ret_1d": valid_ret["ret_1d"].median() if not valid_ret.empty else None,
                "avg_ret_20d": frame["ret_20d"].mean(),
                "turnover_total": valid_turnover["turnover"].sum() if not valid_turnover.empty else None,
                "turnover_median": valid_turnover["turnover"].median() if not valid_turnover.empty else None,
            }
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    result["turnover_total_ma20"] = result["turnover_total"].rolling(20).mean()
    result["turnover_expansion"] = result["turnover_total"] / result["turnover_total_ma20"] - 1
    result["breadth_score"] = (
        0.45 * result["above_ma_120_ratio"].fillna(0)
        + 0.35 * result["up_ratio"].fillna(0)
        + 0.20 * result["turnover_expansion"].fillna(0).clip(-1, 1)
    )
    result["asset_id"] = BREADTH_ASSET_ID
    return result


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator
