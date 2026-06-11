from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd


@dataclass(frozen=True)
class LedgerBacktestResult:
    nav: pd.DataFrame
    positions: pd.DataFrame
    orders: pd.DataFrame
    trades: pd.DataFrame


def backtest_target_weights(
    prices: pd.DataFrame,
    signals: pd.DataFrame,
    run_id: str,
    strategy_id: str,
    initial_cash: float = 100_000.0,
    fee_rate: float = 0.001,
) -> LedgerBacktestResult:
    prices = prices.sort_values(["date", "asset_id"]).copy()
    signals = signals.sort_values(["date", "asset_id"]).copy()
    dates = sorted(prices["date"].unique())

    cash = float(initial_cash)
    holdings: dict[str, float] = {}
    nav_records = []
    position_records = []
    order_records = []
    trade_records = []
    now = datetime.now(timezone.utc)

    for date_value in dates:
        price_today = prices.loc[prices["date"] == date_value].set_index("asset_id")["close"].to_dict()
        portfolio_value = cash + sum(
            quantity * price_today.get(asset_id, 0.0)
            for asset_id, quantity in holdings.items()
            if asset_id in price_today
        )

        signal_today = signals.loc[signals["date"] == date_value]
        if not signal_today.empty:
            target_weights = signal_today.set_index("asset_id")["target_weight"].to_dict()
            reasons = signal_today.set_index("asset_id")["reason"].to_dict()
            new_holdings: dict[str, float] = {}
            total_fee = 0.0

            target_assets = [asset_id for asset_id in target_weights if asset_id != "CASH"]
            for asset_id in sorted(set(holdings) | set(target_assets)):
                price = price_today.get(asset_id)
                if price is None or price <= 0:
                    continue

                current_quantity = holdings.get(asset_id, 0.0)
                current_value = current_quantity * price
                target_weight = float(target_weights.get(asset_id, 0.0))
                target_value = portfolio_value * target_weight
                target_quantity = target_value / price
                quantity_delta = target_quantity - current_quantity

                if abs(quantity_delta) < 1e-9:
                    if target_quantity > 0:
                        new_holdings[asset_id] = target_quantity
                    continue

                side = "BUY" if quantity_delta > 0 else "SELL"
                notional = abs(quantity_delta * price)
                fee = notional * fee_rate
                total_fee += fee
                order_id = f"{run_id}-{date_value}-{asset_id}-{side}"
                reason = reasons.get(asset_id, "rebalance target changed")

                order_records.append(
                    {
                        "order_id": order_id,
                        "run_id": run_id,
                        "strategy_id": strategy_id,
                        "date": date_value,
                        "asset_id": asset_id,
                        "side": side,
                        "quantity": abs(quantity_delta),
                        "price": price,
                        "notional": notional,
                        "target_weight": target_weight,
                        "reason": reason,
                        "status": "filled",
                        "created_at": now,
                    }
                )
                trade_records.append(
                    {
                        "trade_id": f"{order_id}-trade",
                        "order_id": order_id,
                        "run_id": run_id,
                        "strategy_id": strategy_id,
                        "date": date_value,
                        "asset_id": asset_id,
                        "side": side,
                        "quantity": abs(quantity_delta),
                        "price": price,
                        "notional": notional,
                        "fee": fee,
                        "created_at": now,
                    }
                )

                if target_quantity > 0:
                    new_holdings[asset_id] = target_quantity

            invested_value = sum(
                quantity * price_today[asset_id]
                for asset_id, quantity in new_holdings.items()
                if asset_id in price_today
            )
            cash = max(0.0, portfolio_value - invested_value - total_fee)
            holdings = new_holdings
            portfolio_value = invested_value + cash

        for asset_id, quantity in holdings.items():
            price = price_today.get(asset_id)
            if price is None:
                continue
            market_value = quantity * price
            position_records.append(
                {
                    "run_id": run_id,
                    "date": date_value,
                    "strategy_id": strategy_id,
                    "asset_id": asset_id,
                    "quantity": quantity,
                    "close_price": price,
                    "market_value": market_value,
                    "weight": 0.0 if portfolio_value == 0 else market_value / portfolio_value,
                    "created_at": now,
                }
            )

        nav_records.append(
            {
                "date": date_value,
                "nav": portfolio_value,
                "cash": cash,
                "gross_exposure": 0.0 if portfolio_value == 0 else (portfolio_value - cash) / portfolio_value,
            }
        )

    nav = pd.DataFrame(nav_records)
    if not nav.empty:
        nav["return"] = nav["nav"].pct_change().fillna(0.0)
        nav["cummax"] = nav["nav"].cummax()
        nav["drawdown"] = nav["nav"] / nav["cummax"] - 1

    return LedgerBacktestResult(
        nav=nav,
        positions=pd.DataFrame(position_records),
        orders=pd.DataFrame(order_records),
        trades=pd.DataFrame(trade_records),
    )

