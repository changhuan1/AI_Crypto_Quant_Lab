import pandas as pd


def generate_crypto_targets(
    scores: pd.DataFrame,
    crypto_regime: str,
    top_n: int = 5,
) -> dict[str, float]:
    latest = scores.copy()

    if crypto_regime in {"risk_off", "unknown"}:
        return {"CASH": 1.0}

    max_exposure = 0.30 if crypto_regime == "neutral" else 0.60
    candidates = latest.dropna(subset=["crypto_score"]).sort_values(
        "crypto_score",
        ascending=False,
    ).head(top_n)

    if candidates.empty:
        return {"CASH": 1.0}

    targets: dict[str, float] = {}
    suggested_weight = max_exposure / len(candidates)

    for _, row in candidates.iterrows():
        asset_id = row["asset_id"]
        max_weight = 0.30 if asset_id in {"CRYPTO_BTC_USDT", "CRYPTO_ETH_USDT"} else 0.08
        targets[asset_id] = min(max_weight, suggested_weight)

    used = sum(targets.values())
    targets["CASH"] = max(0.0, 1.0 - used)
    return targets
