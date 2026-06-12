from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from src.jobs.init_db import DB_PATH


def build_data_quality_report(db_path: Path = DB_PATH) -> pd.DataFrame:
    reports = []
    created_at = datetime.now(timezone.utc)

    with duckdb.connect(str(db_path)) as con:
        price_coverage = con.execute(
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
            """
        ).df()
        status_summary = con.execute(
            """
            SELECT
                COUNT(*) AS status_count,
                SUM(CASE WHEN up_limit IS NOT NULL THEN 1 ELSE 0 END) AS up_limit_count,
                SUM(CASE WHEN down_limit IS NOT NULL THEN 1 ELSE 0 END) AS down_limit_count,
                SUM(CASE WHEN is_suspended THEN 1 ELSE 0 END) AS suspended_count,
                SUM(CASE WHEN source LIKE '%no_limit%' THEN 1 ELSE 0 END) AS no_limit_source_count,
                SUM(CASE WHEN source LIKE '%no_suspend%' THEN 1 ELSE 0 END) AS no_suspend_source_count
            FROM asset_status_daily
            """
        ).df().iloc[0]
        constituents_count = con.execute("SELECT COUNT(*) FROM index_constituents_history").fetchone()[0]
        invalid_price_count = con.execute(
            """
            SELECT COUNT(*)
            FROM prices_daily
            WHERE close IS NULL
               OR close <= 0
               OR high < low
               OR open <= 0
            """
        ).fetchone()[0]

    for _, row in price_coverage.iterrows():
        reports.append(
            _report(
                check_name="price_coverage",
                severity="info",
                asset_group=row["asset_group"],
                metric_name="row_count",
                metric_value=float(row["row_count"]),
                message=(
                    f"{row['asset_group']} 覆盖 {int(row['asset_count'])} 个资产，"
                    f"日期 {row['start_date']} 到 {row['end_date']}"
                ),
                created_at=created_at,
            )
        )

    if invalid_price_count > 0:
        reports.append(
            _report(
                check_name="invalid_price",
                severity="error",
                asset_group="all",
                metric_name="invalid_price_count",
                metric_value=float(invalid_price_count),
                message="存在 close<=0、open<=0、close 为空或 high<low 的价格记录",
                created_at=created_at,
            )
        )
    else:
        reports.append(
            _report(
                check_name="invalid_price",
                severity="pass",
                asset_group="all",
                metric_name="invalid_price_count",
                metric_value=0.0,
                message="未发现基础价格异常",
                created_at=created_at,
            )
        )

    status_count = int(status_summary["status_count"] or 0)
    up_limit_count = int(status_summary["up_limit_count"] or 0)
    down_limit_count = int(status_summary["down_limit_count"] or 0)
    no_limit_source_count = int(status_summary["no_limit_source_count"] or 0)
    no_suspend_source_count = int(status_summary["no_suspend_source_count"] or 0)
    status_is_partial = (
        status_count > 0
        and (up_limit_count == 0 or down_limit_count == 0 or no_limit_source_count > 0 or no_suspend_source_count > 0)
    )
    severity = "warning" if status_count == 0 or status_is_partial else "pass"
    if status_count == 0:
        status_message = "缺少停牌、ST、涨跌停等资产状态数据；当前回测只能在状态未知时按可交易处理"
    elif status_is_partial:
        status_message = (
            f"资产状态表已有 {status_count} 行，但涨跌停或停复牌字段不完整；"
            "当前回测仍可能低估交易限制"
        )
    else:
        status_message = f"资产状态表已有 {status_count} 行，且涨跌停/停复牌字段可用"
    reports.append(
        _report(
            check_name="asset_status_daily",
            severity=severity,
            asset_group="A-share constituents",
            metric_name="status_rows",
            metric_value=float(status_count),
            message=status_message,
            created_at=created_at,
        )
    )

    severity = "warning" if constituents_count == 0 else "pass"
    reports.append(
        _report(
            check_name="index_constituents_history",
            severity=severity,
            asset_group="A-share constituents",
            metric_name="constituent_rows",
            metric_value=float(constituents_count),
            message=(
                "缺少历史指数成分股，当前回测存在幸存者偏差风险"
                if constituents_count == 0
                else f"历史成分股表已有 {constituents_count} 行"
            ),
            created_at=created_at,
        )
    )

    return pd.DataFrame(reports)


def save_data_quality_report(report: pd.DataFrame, db_path: Path = DB_PATH) -> None:
    if report.empty:
        return
    with duckdb.connect(str(db_path)) as con:
        con.register("quality_report", report)
        con.execute(
            """
            INSERT OR REPLACE INTO data_quality_reports
            SELECT *
            FROM quality_report
            """
        )


def latest_data_quality_report(db_path: Path = DB_PATH) -> pd.DataFrame:
    with duckdb.connect(str(db_path)) as con:
        return con.execute(
            """
            SELECT *
            FROM data_quality_reports
            QUALIFY created_at = MAX(created_at) OVER ()
            ORDER BY
                CASE severity
                    WHEN 'error' THEN 1
                    WHEN 'warning' THEN 2
                    WHEN 'pass' THEN 3
                    ELSE 4
                END,
                check_name
            """
        ).df()


def refresh_data_quality_report(db_path: Path = DB_PATH) -> pd.DataFrame:
    report = build_data_quality_report(db_path)
    save_data_quality_report(report, db_path)
    return report


def _report(
    check_name: str,
    severity: str,
    asset_group: str,
    metric_name: str,
    metric_value: float,
    message: str,
    created_at: datetime,
    asset_id: str | None = None,
    date_value=None,
) -> dict:
    return {
        "report_id": f"dq_{uuid.uuid4().hex}",
        "check_name": check_name,
        "severity": severity,
        "asset_group": asset_group,
        "asset_id": asset_id,
        "date": date_value,
        "metric_name": metric_name,
        "metric_value": metric_value,
        "message": message,
        "created_at": created_at,
    }
