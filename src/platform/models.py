from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class StrategyTemplate:
    template_id: str
    name: str
    description: str
    asset_class: str
    market: str
    default_config: dict[str, Any]


@dataclass(frozen=True)
class Strategy:
    strategy_id: str
    name: str
    description: str
    asset_class: str
    market: str
    template_id: str
    config: dict[str, Any]
    status: str = "draft"


@dataclass(frozen=True)
class BacktestRequest:
    strategy_id: str
    start_date: date | None = None
    end_date: date | None = None
    initial_cash: float = 100_000.0
    config_overrides: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    strategy_id: str
    strategy_name: str
    status: str
    metrics: dict[str, float]
    started_at: datetime
    finished_at: datetime
    message: str = ""

