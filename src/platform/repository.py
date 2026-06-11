from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from src.jobs.init_db import DB_PATH, init_database
from src.platform.models import Strategy
from src.platform.strategy_templates import default_strategies


def ensure_platform_ready(db_path: Path = DB_PATH) -> None:
    init_database(db_path)
    seed_default_strategies(db_path)


def seed_default_strategies(db_path: Path = DB_PATH) -> None:
    now = datetime.now(timezone.utc)
    rows = []
    for strategy in default_strategies():
        rows.append(
            {
                "strategy_id": strategy.strategy_id,
                "name": strategy.name,
                "description": strategy.description,
                "asset_class": strategy.asset_class,
                "market": strategy.market,
                "template_id": strategy.template_id,
                "config_json": json.dumps(strategy.config, ensure_ascii=False),
                "status": strategy.status,
                "created_at": now,
                "updated_at": now,
            }
        )

    with duckdb.connect(str(db_path)) as con:
        con.register("strategy_seed", pd.DataFrame(rows))
        con.execute(
            """
            INSERT OR IGNORE INTO strategies
            SELECT
                strategy_id,
                name,
                description,
                asset_class,
                market,
                template_id,
                config_json,
                status,
                created_at,
                updated_at
            FROM strategy_seed
            """
        )


def list_strategies(db_path: Path = DB_PATH) -> pd.DataFrame:
    ensure_platform_ready(db_path)
    with duckdb.connect(str(db_path)) as con:
        return con.execute(
            """
            SELECT
                strategy_id,
                name,
                description,
                asset_class,
                market,
                template_id,
                status,
                config_json,
                created_at,
                updated_at
            FROM strategies
            ORDER BY updated_at DESC, strategy_id
            """
        ).df()


def get_strategy(strategy_id: str, db_path: Path = DB_PATH) -> Strategy:
    ensure_platform_ready(db_path)
    with duckdb.connect(str(db_path)) as con:
        row = con.execute(
            """
            SELECT *
            FROM strategies
            WHERE strategy_id = ?
            """,
            [strategy_id],
        ).fetchone()

    if row is None:
        raise ValueError(f"Strategy not found: {strategy_id}")

    columns = [
        "strategy_id",
        "name",
        "description",
        "asset_class",
        "market",
        "template_id",
        "config_json",
        "status",
        "created_at",
        "updated_at",
    ]
    data: dict[str, Any] = dict(zip(columns, row))
    return Strategy(
        strategy_id=data["strategy_id"],
        name=data["name"],
        description=data["description"],
        asset_class=data["asset_class"],
        market=data["market"],
        template_id=data["template_id"],
        config=json.loads(data["config_json"]),
        status=data["status"],
    )


def save_strategy(strategy: Strategy, db_path: Path = DB_PATH) -> None:
    ensure_platform_ready(db_path)
    now = datetime.now(timezone.utc)
    row = pd.DataFrame(
        [
            {
                "strategy_id": strategy.strategy_id,
                "name": strategy.name,
                "description": strategy.description,
                "asset_class": strategy.asset_class,
                "market": strategy.market,
                "template_id": strategy.template_id,
                "config_json": json.dumps(strategy.config, ensure_ascii=False),
                "status": strategy.status,
                "created_at": now,
                "updated_at": now,
            }
        ]
    )
    with duckdb.connect(str(db_path)) as con:
        con.register("strategy_row", row)
        con.execute(
            """
            INSERT OR REPLACE INTO strategies
            SELECT
                strategy_id,
                name,
                description,
                asset_class,
                market,
                template_id,
                config_json,
                status,
                created_at,
                updated_at
            FROM strategy_row
            """
        )
