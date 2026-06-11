from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from src.platform.market_rules import AShareTradingRules


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
    asset_status: pd.DataFrame | None = None,
    execution_delay_days: int = 1,
    rules: AShareTradingRules | None = None,
) -> LedgerBacktestResult:
    """Backtest target-weight signals with an A-share-aware ledger.

    Signals are treated as decisions known after the signal date close. By default
    they are executed on the next available price date at the open price.
    """

    if prices.empty:
        return LedgerBacktestResult(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame())

    rules = rules or AShareTradingRules(commission_rate=fee_rate)
    prices = prices.sort_values(["date", "asset_id"]).copy()
    signals = signals.sort_values(["date", "asset_id"]).copy()
    dates = sorted(pd.to_datetime(prices["date"]).dt.date.unique())
    status_lookup = _build_status_lookup(asset_status)

    cash = float(initial_cash)
    holdings: dict[str, int] = {}
    last_buy_dates: dict[str, object] = {}
    last_close: dict[str, float] = {}
    nav_records = []
    position_records = []
    order_records = []
    trade_records = []
    now = datetime.now(timezone.utc)
    order_seq = 0

    for date_index, date_value in enumerate(dates):
        price_frame = prices.loc[pd.to_datetime(prices["date"]).dt.date == date_value]
        execution_prices = _price_dict(price_frame, "open", fallback_column="close")
        close_prices = _price_dict(price_frame, "close")
        for asset_id, close_price in close_prices.items():
            if close_price > 0 and not pd.isna(close_price):
                last_close[asset_id] = close_price

        portfolio_value_for_trade = cash + _value_holdings(holdings, execution_prices, last_close)

        signal_date = _signal_date_for_execution(dates, date_index, execution_delay_days)
        signal_today = (
            signals.loc[pd.to_datetime(signals["date"]).dt.date == signal_date]
            if signal_date is not None
            else pd.DataFrame()
        )

        if not signal_today.empty:
            target_weights = signal_today.set_index("asset_id")["target_weight"].to_dict()
            reasons = signal_today.set_index("asset_id")["reason"].to_dict()
            requested_orders = _build_rebalance_orders(
                holdings=holdings,
                target_weights=target_weights,
                execution_prices=execution_prices,
                portfolio_value=portfolio_value_for_trade,
                rules=rules,
            )

            for requested in sorted(requested_orders, key=lambda item: 0 if item["side"] == "SELL" else 1):
                asset_id = requested["asset_id"]
                side = requested["side"]
                requested_quantity = int(requested["quantity"])
                price = requested["price"]
                target_weight = requested["target_weight"]
                signal_reason = reasons.get(asset_id, "rebalance target changed")
                order_seq += 1
                order_id = f"{run_id}-{date_value}-{order_seq:06d}"

                if requested_quantity <= 0:
                    _append_rejected_order(
                        order_records,
                        order_id,
                        run_id,
                        strategy_id,
                        date_value,
                        asset_id,
                        side,
                        requested_quantity,
                        price,
                        target_weight,
                        f"{signal_reason}；数量不足 100 股或无需交易",
                        now,
                    )
                    continue

                check = rules.check_trade(
                    side=side,
                    asset_id=asset_id,
                    date_value=date_value,
                    price=price,
                    status=status_lookup.get((asset_id, date_value)),
                    last_buy_date=last_buy_dates.get(asset_id),
                )
                if not check.allowed:
                    _append_rejected_order(
                        order_records,
                        order_id,
                        run_id,
                        strategy_id,
                        date_value,
                        asset_id,
                        side,
                        requested_quantity,
                        price,
                        target_weight,
                        f"{signal_reason}；{check.reason}",
                        now,
                    )
                    continue

                quantity = requested_quantity
                if side == "BUY":
                    affordable = rules.max_affordable_buy_quantity(cash, price)
                    quantity = min(quantity, affordable)
                    quantity = rules.round_buy_quantity(quantity)
                    if quantity <= 0:
                        _append_rejected_order(
                            order_records,
                            order_id,
                            run_id,
                            strategy_id,
                            date_value,
                            asset_id,
                            side,
                            requested_quantity,
                            price,
                            target_weight,
                            f"{signal_reason}；现金不足，无法买入 100 股",
                            now,
                        )
                        continue
                else:
                    quantity = rules.round_sell_quantity(quantity, holdings.get(asset_id, 0))
                    if quantity <= 0:
                        _append_rejected_order(
                            order_records,
                            order_id,
                            run_id,
                            strategy_id,
                            date_value,
                            asset_id,
                            side,
                            requested_quantity,
                            price,
                            target_weight,
                            f"{signal_reason}；无可卖持仓",
                            now,
                        )
                        continue

                notional = quantity * price
                cost = rules.calculate_cost(side, notional)

                if side == "BUY":
                    cash -= notional + cost.total
                    holdings[asset_id] = holdings.get(asset_id, 0) + quantity
                    last_buy_dates[asset_id] = date_value
                else:
                    cash += notional - cost.total
                    holdings[asset_id] = max(0, holdings.get(asset_id, 0) - quantity)
                    if holdings[asset_id] == 0:
                        holdings.pop(asset_id, None)
                        last_buy_dates.pop(asset_id, None)

                order_records.append(
                    {
                        "order_id": order_id,
                        "run_id": run_id,
                        "strategy_id": strategy_id,
                        "date": date_value,
                        "asset_id": asset_id,
                        "side": side,
                        "quantity": quantity,
                        "price": price,
                        "notional": notional,
                        "target_weight": target_weight,
                        "reason": f"{signal_reason}；信号日={signal_date}；{check.reason}",
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
                        "quantity": quantity,
                        "price": price,
                        "notional": notional,
                        "fee": cost.total,
                        "created_at": now,
                    }
                )

        portfolio_value = cash + _value_holdings(holdings, close_prices, last_close)
        for asset_id, quantity in holdings.items():
            close_price = close_prices.get(asset_id, last_close.get(asset_id))
            if close_price is None:
                continue
            market_value = quantity * close_price
            position_records.append(
                {
                    "run_id": run_id,
                    "date": date_value,
                    "strategy_id": strategy_id,
                    "asset_id": asset_id,
                    "quantity": quantity,
                    "close_price": close_price,
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


def _signal_date_for_execution(
    dates: list[object],
    date_index: int,
    execution_delay_days: int,
) -> object | None:
    signal_index = date_index - execution_delay_days
    if signal_index < 0:
        return None
    return dates[signal_index]


def _build_rebalance_orders(
    holdings: dict[str, int],
    target_weights: dict[str, float],
    execution_prices: dict[str, float],
    portfolio_value: float,
    rules: AShareTradingRules,
) -> list[dict]:
    orders = []
    target_assets = [asset_id for asset_id in target_weights if asset_id != "CASH"]
    for asset_id in sorted(set(holdings) | set(target_assets)):
        price = execution_prices.get(asset_id)
        if price is None or price <= 0 or pd.isna(price):
            continue

        current_quantity = holdings.get(asset_id, 0)
        target_weight = float(target_weights.get(asset_id, 0.0))
        target_value = portfolio_value * target_weight
        target_quantity = rules.round_buy_quantity(target_value / price)
        quantity_delta = target_quantity - current_quantity

        if quantity_delta > 0:
            orders.append(
                {
                    "asset_id": asset_id,
                    "side": "BUY",
                    "quantity": quantity_delta,
                    "price": price,
                    "target_weight": target_weight,
                }
            )
        elif quantity_delta < 0:
            orders.append(
                {
                    "asset_id": asset_id,
                    "side": "SELL",
                    "quantity": abs(quantity_delta),
                    "price": price,
                    "target_weight": target_weight,
                }
            )
        elif asset_id in target_assets and target_weight > 0 and current_quantity == 0:
            orders.append(
                {
                    "asset_id": asset_id,
                    "side": "BUY",
                    "quantity": 0,
                    "price": price,
                    "target_weight": target_weight,
                }
            )
    return orders


def _append_rejected_order(
    order_records: list[dict],
    order_id: str,
    run_id: str,
    strategy_id: str,
    date_value,
    asset_id: str,
    side: str,
    quantity: int,
    price: float,
    target_weight: float,
    reason: str,
    created_at: datetime,
) -> None:
    order_records.append(
        {
            "order_id": order_id,
            "run_id": run_id,
            "strategy_id": strategy_id,
            "date": date_value,
            "asset_id": asset_id,
            "side": side,
            "quantity": quantity,
            "price": price,
            "notional": max(quantity, 0) * price,
            "target_weight": target_weight,
            "reason": reason,
            "status": "rejected",
            "created_at": created_at,
        }
    )


def _price_dict(
    price_frame: pd.DataFrame,
    column: str,
    fallback_column: str | None = None,
) -> dict[str, float]:
    if price_frame.empty:
        return {}
    values = {}
    for _, row in price_frame.iterrows():
        value = row.get(column)
        if (value is None or pd.isna(value)) and fallback_column is not None:
            value = row.get(fallback_column)
        if value is not None and not pd.isna(value):
            values[row["asset_id"]] = float(value)
    return values


def _value_holdings(
    holdings: dict[str, int],
    prices: dict[str, float],
    fallback_prices: dict[str, float],
) -> float:
    value = 0.0
    for asset_id, quantity in holdings.items():
        price = prices.get(asset_id, fallback_prices.get(asset_id))
        if price is not None and not pd.isna(price):
            value += quantity * price
    return value


def _build_status_lookup(asset_status: pd.DataFrame | None) -> dict[tuple[str, object], dict]:
    if asset_status is None or asset_status.empty:
        return {}
    lookup = {}
    for _, row in asset_status.iterrows():
        key = (row["asset_id"], pd.Timestamp(row["date"]).date())
        lookup[key] = row.to_dict()
    return lookup

