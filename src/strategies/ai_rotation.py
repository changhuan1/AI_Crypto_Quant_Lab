import pandas as pd


def generate_ai_targets(
    scores: pd.DataFrame,
    market_regime: str,
    top_n: int = 5,
) -> dict[str, float]:
    latest = scores.copy()

    if market_regime in {"risk_off", "unknown"}:
        return {"CASH": 0.8, "LOW_RISK_FUND": 0.2}

    if market_regime == "neutral":
        max_exposure = 0.50
    else:
        max_exposure = 0.80

    min_turnover = latest["turnover"].quantile(0.5)
    candidates = latest[
        (latest["above_ma_120"] == 1)
        & (latest["turnover"] >= min_turnover)
    ].dropna(subset=["ai_market_score"])
    candidates = candidates.sort_values("ai_market_score", ascending=False).head(top_n)

    if candidates.empty:
        return {"CASH": 1.0}

    weight = min(0.25, max_exposure / len(candidates))
    targets = {row["asset_id"]: weight for _, row in candidates.iterrows()}
    targets["CASH"] = max(0.0, 1.0 - sum(targets.values()))
    return targets
