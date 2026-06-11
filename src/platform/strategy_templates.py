from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.platform.models import Strategy, StrategyTemplate


A_SHARE_MOMENTUM_TEMPLATE_ID = "a_share_momentum_rotation"
A_SHARE_MOMENTUM_STRATEGY_ID = "a_share_momentum_rotation_v1"


DEFAULT_A_SHARE_MOMENTUM_CONFIG: dict[str, Any] = {
    "universe": "000001.SH",
    "benchmark_asset_id": "A_INDEX_000001",
    "rebalance_frequency": "weekly_friday",
    "execution_delay_days": 1,
    "top_n": 30,
    "max_single_position": 0.03,
    "neutral_max_exposure": 0.50,
    "risk_on_max_exposure": 0.80,
    "min_turnover_quantile": 0.50,
    "require_above_ma120": True,
    "fee_rate": 0.001,
}


STRATEGY_TEMPLATES: dict[str, StrategyTemplate] = {
    A_SHARE_MOMENTUM_TEMPLATE_ID: StrategyTemplate(
        template_id=A_SHARE_MOMENTUM_TEMPLATE_ID,
        name="上证成分股动量轮动",
        description=(
            "在上证指数成分股中，过滤趋势和流动性后，按动量、相对强弱、成交额和市场宽度评分，"
            "每周生成目标持仓。"
        ),
        asset_class="equity",
        market="cn_a_share",
        default_config=DEFAULT_A_SHARE_MOMENTUM_CONFIG,
    )
}


def default_strategies() -> list[Strategy]:
    template = STRATEGY_TEMPLATES[A_SHARE_MOMENTUM_TEMPLATE_ID]
    return [
        Strategy(
            strategy_id=A_SHARE_MOMENTUM_STRATEGY_ID,
            name=template.name,
            description=template.description,
            asset_class=template.asset_class,
            market=template.market,
            template_id=template.template_id,
            config=deepcopy(template.default_config),
            status="active",
        )
    ]


def merge_config(base: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    result = deepcopy(base)
    if overrides:
        for key, value in overrides.items():
            if value is not None:
                result[key] = value
    return result
