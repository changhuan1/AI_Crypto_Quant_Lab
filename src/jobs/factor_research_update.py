from src.jobs.a_share_market_update import build_a_share_market_features, load_a_share_market_prices
from src.platform.factor_research import (
    calculate_factor_research,
    save_factor_research,
    summarize_factor_ic,
)
from src.strategies.a_share_market_scoring import calculate_a_share_market_score


def main() -> None:
    prices = load_a_share_market_prices()
    if prices.empty:
        raise RuntimeError(
            "No A-share market prices found. Run: python -m src.data_ingestion.a_share_market_prices"
        )

    features = build_a_share_market_features(prices)
    scores = calculate_a_share_market_score(features)
    ic, quantile_returns = calculate_factor_research(scores, prices)
    save_factor_research(ic, quantile_returns)

    summary = summarize_factor_ic(ic)
    print(f"Factor IC rows saved: {len(ic)}")
    print(f"Factor quantile return rows saved: {len(quantile_returns)}")
    if not summary.empty:
        print(summary.to_string(index=False))


if __name__ == "__main__":
    main()

