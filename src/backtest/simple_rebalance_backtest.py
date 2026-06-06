import pandas as pd


def backtest_rebalance(
    prices: pd.DataFrame,
    signals: pd.DataFrame,
    initial_cash: float = 100_000,
    fee_rate: float = 0.001,
) -> pd.DataFrame:
    prices = prices.sort_values(["date", "asset_id"]).copy()
    signals = signals.sort_values(["date", "asset_id"]).copy()
    dates = sorted(prices["date"].unique())

    cash = initial_cash
    holdings: dict[str, float] = {}
    records = []

    for date in dates:
        price_today = prices.loc[prices["date"] == date].set_index("asset_id")["close"].to_dict()

        portfolio_value = cash
        for asset_id, quantity in holdings.items():
            if asset_id in price_today:
                portfolio_value += quantity * price_today[asset_id]

        nav = portfolio_value

        signal_today = signals.loc[signals["date"] == date]
        if not signal_today.empty:
            target_weights = signal_today.set_index("asset_id")["target_weight"].to_dict()
            new_holdings: dict[str, float] = {}
            turnover_value = 0.0

            for asset_id, weight in target_weights.items():
                if asset_id == "CASH" or asset_id not in price_today:
                    continue

                target_value = nav * weight
                current_value = holdings.get(asset_id, 0.0) * price_today[asset_id]
                turnover_value += abs(target_value - current_value)
                new_holdings[asset_id] = target_value / price_today[asset_id]

            invested_value = sum(
                quantity * price_today[asset_id]
                for asset_id, quantity in new_holdings.items()
                if asset_id in price_today
            )
            fee = turnover_value * fee_rate
            cash = max(0.0, nav - invested_value - fee)
            nav = invested_value + cash
            holdings = new_holdings

        records.append(
            {
                "date": date,
                "nav": nav,
                "cash": cash,
                "gross_exposure": 0.0 if nav == 0 else (nav - cash) / nav,
                "holdings_count": len(holdings),
            }
        )

    result = pd.DataFrame(records)
    result["return"] = result["nav"].pct_change().fillna(0.0)
    result["cummax"] = result["nav"].cummax()
    result["drawdown"] = result["nav"] / result["cummax"] - 1
    return result
