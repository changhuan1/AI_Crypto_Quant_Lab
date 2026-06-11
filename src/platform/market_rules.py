from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


OrderSide = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class TradeCost:
    commission: float
    stamp_tax: float
    transfer_fee: float

    @property
    def total(self) -> float:
        return self.commission + self.stamp_tax + self.transfer_fee


@dataclass(frozen=True)
class TradeCheck:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class AShareTradingRules:
    lot_size: int = 100
    commission_rate: float = 0.0003
    min_commission: float = 5.0
    stamp_tax_rate: float = 0.0005
    transfer_fee_rate: float = 0.00001
    price_epsilon: float = 1e-6

    def round_buy_quantity(self, raw_quantity: float) -> int:
        if raw_quantity <= 0:
            return 0
        lots = int(raw_quantity // self.lot_size)
        return lots * self.lot_size

    def round_sell_quantity(self, raw_quantity: float, current_quantity: float) -> int:
        if raw_quantity <= 0 or current_quantity <= 0:
            return 0
        quantity = min(raw_quantity, current_quantity)
        if abs(quantity - current_quantity) < self.lot_size:
            return int(current_quantity)
        lots = int(quantity // self.lot_size)
        return lots * self.lot_size

    def max_affordable_buy_quantity(self, cash: float, price: float) -> int:
        if cash <= 0 or price <= 0:
            return 0
        estimated_fee_rate = self.commission_rate + self.transfer_fee_rate
        raw_quantity = cash / (price * (1 + estimated_fee_rate))
        quantity = self.round_buy_quantity(raw_quantity)
        while quantity > 0 and price * quantity + self.calculate_cost("BUY", price * quantity).total > cash:
            quantity -= self.lot_size
        return max(quantity, 0)

    def calculate_cost(self, side: OrderSide, notional: float) -> TradeCost:
        if notional <= 0:
            return TradeCost(commission=0.0, stamp_tax=0.0, transfer_fee=0.0)
        commission = max(notional * self.commission_rate, self.min_commission)
        stamp_tax = notional * self.stamp_tax_rate if side == "SELL" else 0.0
        transfer_fee = notional * self.transfer_fee_rate
        return TradeCost(commission=commission, stamp_tax=stamp_tax, transfer_fee=transfer_fee)

    def check_trade(
        self,
        side: OrderSide,
        asset_id: str,
        date_value,
        price: float,
        status: dict | None,
        last_buy_date=None,
    ) -> TradeCheck:
        if price <= 0 or pd.isna(price):
            return TradeCheck(False, "价格无效，无法交易")

        if status:
            if status.get("is_tradable") is False:
                return TradeCheck(False, "资产状态标记为不可交易")
            if status.get("is_suspended") is True:
                return TradeCheck(False, "停牌，无法交易")
            if status.get("is_st") is True:
                return TradeCheck(False, "ST 风险过滤，无法交易")
            if side == "BUY" and status.get("is_limit_up") is True:
                return TradeCheck(False, "涨停，无法买入")
            if side == "SELL" and status.get("is_limit_down") is True:
                return TradeCheck(False, "跌停，无法卖出")

            up_limit = status.get("up_limit")
            down_limit = status.get("down_limit")
            if side == "BUY" and up_limit is not None and price >= float(up_limit) - self.price_epsilon:
                return TradeCheck(False, "价格触及涨停价，无法买入")
            if side == "SELL" and down_limit is not None and price <= float(down_limit) + self.price_epsilon:
                return TradeCheck(False, "价格触及跌停价，无法卖出")

        if side == "SELL" and last_buy_date is not None and pd.Timestamp(last_buy_date) == pd.Timestamp(date_value):
            return TradeCheck(False, "T+1 限制，当日买入不可当日卖出")

        return TradeCheck(True, "交易规则检查通过")


DEFAULT_A_SHARE_RULES = AShareTradingRules()

