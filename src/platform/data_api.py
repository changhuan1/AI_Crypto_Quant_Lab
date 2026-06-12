from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from src.jobs.init_db import DB_PATH


class DataPortal:
    """Unified data access layer for strategy and platform services."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path

    def price_coverage(self) -> pd.DataFrame:
        with duckdb.connect(str(self.db_path)) as con:
            return con.execute(
                """
                SELECT
                    CASE
                        WHEN asset_id LIKE 'A_STOCK_%' THEN 'A-share constituents'
                        WHEN asset_id = 'A_INDEX_000001' THEN 'Shanghai Composite'
                        WHEN asset_id LIKE 'CRYPTO_%' THEN 'Crypto'
                        ELSE 'Other'
                    END AS asset_group,
                    COUNT(DISTINCT asset_id) AS asset_count,
                    COUNT(*) AS row_count,
                    MIN(date) AS start_date,
                    MAX(date) AS end_date
                FROM prices_daily
                GROUP BY asset_group
                ORDER BY asset_group
                """
            ).df()

    def load_prices(
        self,
        asset_filter: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        conditions = []
        params = []
        if asset_filter:
            conditions.append(asset_filter)
        if start_date:
            conditions.append("date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("date <= ?")
            params.append(end_date)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"""
            SELECT *
            FROM prices_daily
            {where_clause}
            ORDER BY asset_id, date
        """
        with duckdb.connect(str(self.db_path)) as con:
            return con.execute(sql, params).df()

    def load_a_share_market_prices(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        return self.load_prices(
            asset_filter="(asset_id LIKE 'A_STOCK_%' OR asset_id = 'A_INDEX_000001')",
            start_date=start_date,
            end_date=end_date,
        )

    def latest_signals(self, strategy_id: str) -> pd.DataFrame:
        with duckdb.connect(str(self.db_path)) as con:
            latest = con.execute(
                """
                SELECT MAX(date)
                FROM signals_daily
                WHERE strategy = ?
                """,
                [strategy_id],
            ).fetchone()[0]
            if latest is None:
                return pd.DataFrame()

            return con.execute(
                """
                SELECT
                    s.asset_id,
                    CASE
                        WHEN s.asset_id LIKE 'A_STOCK_%' THEN REPLACE(s.asset_id, 'A_STOCK_', '')
                        WHEN s.asset_id LIKE 'A_INDEX_%' THEN REPLACE(s.asset_id, 'A_INDEX_', '')
                        WHEN s.asset_id LIKE 'CRYPTO_%' THEN REPLACE(s.asset_id, 'CRYPTO_', '')
                        ELSE s.asset_id
                    END AS asset_code,
                    COALESCE(a.name, s.asset_id) AS asset_name,
                    s.date,
                    s.strategy,
                    s.score,
                    s.signal,
                    s.target_weight,
                    s.risk_flag,
                    s.reason
                FROM signals_daily s
                LEFT JOIN assets a ON s.asset_id = a.asset_id
                WHERE s.strategy = ?
                  AND s.date = ?
                ORDER BY target_weight DESC, score DESC NULLS LAST
                """,
                [strategy_id, latest],
            ).df()

    def latest_runs(self, limit: int = 20) -> pd.DataFrame:
        with duckdb.connect(str(self.db_path)) as con:
            return con.execute(
                """
                SELECT
                    run_id,
                    strategy_id,
                    strategy_name,
                    run_type,
                    status,
                    start_date,
                    end_date,
                    initial_cash,
                    started_at,
                    finished_at,
                    error_message
                FROM strategy_runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                [limit],
            ).df()

    def load_asset_status(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        conditions = []
        params = []
        if start_date:
            conditions.append("date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("date <= ?")
            params.append(end_date)
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"""
            SELECT *
            FROM asset_status_daily
            {where_clause}
            ORDER BY asset_id, date
        """
        with duckdb.connect(str(self.db_path)) as con:
            return con.execute(sql, params).df()
