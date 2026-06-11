from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

from src.jobs.init_db import DB_PATH
from src.platform.backtest_service import run_backtest
from src.platform.data_api import DataPortal
from src.platform.models import BacktestRequest
from src.platform.repository import ensure_platform_ready, list_strategies


APP_VERSION = "v1.0.0"
PAGES = [
    "首页",
    "数据中心",
    "策略中心",
    "回测中心",
    "回测结果",
    "模拟交易",
    "风控中心",
    "任务中心",
    "技术架构",
]

st.set_page_config(page_title=f"Quant Platform {APP_VERSION}", layout="wide")


@st.cache_data(show_spinner=False)
def query(sql: str, params: tuple | None = None) -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        return con.execute(sql, params or ()).df()


def main() -> None:
    ensure_platform_ready()
    st.title("Quant Platform")
    st.caption(f"{APP_VERSION} | 聚宽式本地量化研究与策略托管平台")

    page_from_url = _get_query_page()
    page = st.sidebar.radio("平台导航", PAGES, index=PAGES.index(page_from_url))
    _set_query_page(page)

    if page == "首页":
        render_home()
    elif page == "数据中心":
        render_data_center()
    elif page == "策略中心":
        render_strategy_center()
    elif page == "回测中心":
        render_backtest_center()
    elif page == "回测结果":
        render_backtest_results()
    elif page == "模拟交易":
        render_paper_trading()
    elif page == "风控中心":
        render_risk_center()
    elif page == "任务中心":
        render_task_center()
    else:
        render_architecture()


def render_home() -> None:
    st.subheader("平台总览")
    c1, c2, c3, c4 = st.columns(4)
    coverage = safe_df(lambda: DataPortal().price_coverage())
    strategies = safe_df(list_strategies)
    runs = safe_df(lambda: DataPortal().latest_runs(limit=100))

    a_share_count = _coverage_value(coverage, "A-share constituents", "asset_count")
    latest_price_date = _max_date(coverage, "end_date")
    success_runs = 0 if runs.empty else int((runs["status"] == "success").sum())

    c1.metric("策略数量", len(strategies))
    c2.metric("A股股票数", f"{a_share_count:,.0f}")
    c3.metric("最新行情日", latest_price_date or "-")
    c4.metric("成功回测", success_runs)

    st.markdown("### 用户主流程")
    st.graphviz_chart(
        """
        digraph {
            graph [rankdir=LR, bgcolor="transparent", pad="0.2"];
            node [shape=box, style="rounded,filled", color="#CBD5E1", fillcolor="#F8FAFC", fontname="Microsoft YaHei", fontsize=11];
            edge [color="#64748B", arrowsize=0.8, fontname="Microsoft YaHei", fontsize=10];
            data [label="数据中心\\n平台维护行情和质量"];
            strategy [label="策略中心\\n选择模板和参数"];
            backtest [label="回测中心\\n一键运行"];
            result [label="回测结果\\n净值/回撤/订单/持仓"];
            paper [label="模拟交易\\n每日目标仓位"];
            risk [label="风控中心\\n解释风险和限制"];
            data -> strategy -> backtest -> result -> paper -> risk;
        }
        """,
        width="stretch",
    )

    st.info("当前 v1.0.0 是本地单用户平台版：方向已经固定为策略托管平台，后续会继续增强任务调度、多用户和实盘前风控。")


def render_data_center() -> None:
    st.subheader("数据中心")
    st.write("数据中心负责展示平台后端数据是否可用。用户写策略时不需要直接关心 AKShare、CCXT 或 DuckDB。")
    coverage = safe_df(lambda: DataPortal().price_coverage())
    if coverage.empty:
        st.warning("还没有行情数据。请先运行数据采集任务。")
    else:
        st.dataframe(coverage, width="stretch", hide_index=True)

    st.markdown("### 后台数据任务")
    st.code(
        "\n".join(
            [
                "conda activate ai_crypto_quant_lab",
                "python -m src.jobs.init_db",
                "python -m src.data_ingestion.a_share_market_prices --limit 50",
                "python -m src.jobs.a_share_market_update",
                "python -m src.jobs.a_share_breadth_update",
            ]
        ),
        language="powershell",
    )
    st.caption("小样本验证通过后，可以去掉 `--limit 50` 拉取完整上证成分股。")


def render_strategy_center() -> None:
    st.subheader("策略中心")
    st.write("策略现在是平台对象，不再只是一个 Python 文件。第一版内置“上证成分股动量轮动”模板。")
    strategies = list_strategies()
    st.dataframe(
        strategies.drop(columns=["config_json"], errors="ignore"),
        width="stretch",
        hide_index=True,
    )

    strategy_id = st.selectbox("查看策略配置", strategies["strategy_id"].tolist())
    row = strategies.loc[strategies["strategy_id"] == strategy_id].iloc[0]
    st.json(json.loads(row["config_json"]))


def render_backtest_center() -> None:
    st.subheader("回测中心")
    st.write("这里是 v1.0.0 最关键的入口：选择策略、配置参数、点击运行回测。")
    strategies = list_strategies()
    if strategies.empty:
        st.warning("没有策略。请先进入策略中心初始化内置策略。")
        return

    start_default, end_default = _price_date_bounds()
    with st.form("backtest_form"):
        strategy_id = st.selectbox("策略", strategies["strategy_id"].tolist())
        col1, col2, col3 = st.columns(3)
        start_date = col1.date_input("开始日期", value=start_default)
        end_date = col2.date_input("结束日期", value=end_default)
        initial_cash = col3.number_input("初始资金", min_value=10_000.0, value=100_000.0, step=10_000.0)

        col4, col5, col6 = st.columns(3)
        top_n = col4.number_input("最大持仓数", min_value=1, max_value=100, value=30, step=1)
        max_single = col5.number_input("单票最大仓位", min_value=0.005, max_value=0.20, value=0.03, step=0.005)
        fee_rate = col6.number_input("交易费率", min_value=0.0, max_value=0.02, value=0.001, step=0.0005, format="%.4f")

        submitted = st.form_submit_button("运行回测")

    if submitted:
        with st.spinner("正在运行回测，平台会保存净值、订单、成交和持仓..."):
            try:
                result = run_backtest(
                    BacktestRequest(
                        strategy_id=strategy_id,
                        start_date=start_date,
                        end_date=end_date,
                        initial_cash=initial_cash,
                        config_overrides={
                            "top_n": int(top_n),
                            "max_single_position": float(max_single),
                            "fee_rate": float(fee_rate),
                        },
                    )
                )
                st.cache_data.clear()
                st.success(f"回测完成：{result.run_id}")
                render_metric_grid(result.metrics)
            except Exception as exc:
                st.error(f"回测失败：{exc}")


def render_backtest_results() -> None:
    st.subheader("回测结果")
    runs = safe_df(lambda: DataPortal().latest_runs(limit=50))
    if runs.empty:
        st.info("还没有回测记录。请先在回测中心运行一次回测。")
        return

    st.dataframe(runs, width="stretch", hide_index=True)
    success_runs = runs.loc[runs["status"] == "success"]
    if success_runs.empty:
        return

    run_id = st.selectbox("选择回测记录", success_runs["run_id"].tolist())
    nav = query(
        """
        SELECT date, nav, benchmark_nav, cash, gross_exposure, drawdown
        FROM backtest_nav
        WHERE run_id = ?
        ORDER BY date
        """,
        (run_id,),
    )
    metrics = query(
        """
        SELECT metric_name, metric_value
        FROM strategy_run_metrics
        WHERE run_id = ?
        ORDER BY metric_name
        """,
        (run_id,),
    )
    positions = query(
        """
        SELECT date, asset_id, quantity, close_price, market_value, weight
        FROM positions_daily
        WHERE run_id = ?
        QUALIFY date = MAX(date) OVER ()
        ORDER BY weight DESC
        """,
        (run_id,),
    )
    orders = query(
        """
        SELECT date, asset_id, side, quantity, price, notional, target_weight, reason
        FROM orders
        WHERE run_id = ?
        ORDER BY date DESC, notional DESC
        LIMIT 200
        """,
        (run_id,),
    )

    if not metrics.empty:
        render_metric_grid(dict(zip(metrics["metric_name"], metrics["metric_value"])))

    if not nav.empty:
        plot_nav = nav[["date", "nav", "benchmark_nav"]].melt(
            id_vars="date", var_name="series", value_name="value"
        )
        st.plotly_chart(px.line(plot_nav, x="date", y="value", color="series"), width="stretch")
        c1, c2 = st.columns(2)
        c1.plotly_chart(px.line(nav, x="date", y="drawdown"), width="stretch")
        c2.plotly_chart(px.line(nav, x="date", y="gross_exposure"), width="stretch")

    st.markdown("### 最新持仓")
    st.dataframe(positions, width="stretch", hide_index=True)
    st.markdown("### 最近订单")
    st.dataframe(orders, width="stretch", hide_index=True)


def render_paper_trading() -> None:
    st.subheader("模拟交易")
    st.write("v1.0.0 先展示最近一次策略信号，作为模拟交易目标仓位。后续会加入独立模拟账户和每日自动调度。")
    strategies = list_strategies()
    strategy_id = st.selectbox("策略", strategies["strategy_id"].tolist())
    signals = DataPortal().latest_signals(strategy_id)
    if signals.empty:
        st.info("还没有信号。请先运行回测或策略任务。")
        return
    st.dataframe(signals, width="stretch", hide_index=True)


def render_risk_center() -> None:
    st.subheader("风控中心")
    st.write("风控中心把市场状态、仓位限制和交易限制集中展示。第一版先展示信号级风险标记。")
    risk = safe_df(
        lambda: query(
            """
            SELECT strategy, date, COUNT(*) AS signal_count,
                   SUM(CASE WHEN risk_flag THEN 1 ELSE 0 END) AS risk_flag_count
            FROM signals_daily
            GROUP BY strategy, date
            QUALIFY ROW_NUMBER() OVER (PARTITION BY strategy ORDER BY date DESC) = 1
            ORDER BY strategy
            """
        )
    )
    if risk.empty:
        st.info("暂无风险数据。")
    else:
        st.dataframe(risk, width="stretch", hide_index=True)

    events = safe_df(
        lambda: query(
            """
            SELECT *
            FROM risk_events
            ORDER BY created_at DESC
            LIMIT 100
            """
        )
    )
    st.markdown("### 风险事件")
    st.dataframe(events, width="stretch", hide_index=True)


def render_task_center() -> None:
    st.subheader("任务中心")
    st.write("任务中心用于承接未来的自动更新、自动回测、每日信号和日报。")
    jobs = safe_df(
        lambda: query(
            """
            SELECT *
            FROM job_runs
            ORDER BY started_at DESC
            LIMIT 100
            """
        )
    )
    if jobs.empty:
        st.info("暂无任务运行记录。当前阶段仍以手动触发为主，后续会接入 APScheduler。")
    else:
        st.dataframe(jobs, width="stretch", hide_index=True)

    st.markdown("### 建议自动化顺序")
    st.code(
        "\n".join(
            [
                "每日收盘后：更新 A 股行情",
                "行情完成后：计算特征和市场宽度",
                "特征完成后：运行策略信号",
                "信号完成后：更新模拟账户",
                "最后：生成日报和风险检查",
            ]
        )
    )


def render_architecture() -> None:
    st.subheader("技术架构")
    st.graphviz_chart(
        """
        digraph {
            graph [rankdir=LR, bgcolor="transparent", pad="0.2", nodesep="0.35", ranksep="0.55"];
            node [shape=box, style="rounded,filled", color="#CBD5E1", fillcolor="#F8FAFC", fontname="Microsoft YaHei", fontsize=11];
            edge [color="#64748B", arrowsize=0.8, fontname="Microsoft YaHei", fontsize=10];
            ui [label="Streamlit 平台入口"];
            service [label="Platform Service\\n策略/回测/风控"];
            data_api [label="DataPortal\\n统一数据 API"];
            engine [label="Backtest Engine\\n撮合/订单/持仓"];
            db [label="DuckDB\\n行情/策略/回测结果"];
            source [label="AKShare / CCXT\\n后端数据源"];
            ui -> service;
            service -> data_api;
            service -> engine;
            data_api -> db;
            engine -> db;
            source -> db;
        }
        """,
        width="stretch",
    )
    st.markdown(
        """
        **v1.0.0 当前定位**

        - 本地单用户平台版。
        - 已建立策略对象、策略模板、统一数据 API、回测运行记录、订单、成交、持仓和结果页面。
        - 下一步增强任务调度、模拟账户、多策略对比和 FastAPI/React 标准 Web 架构。
        """
    )


def render_metric_grid(metrics: dict[str, float]) -> None:
    labels = [
        ("total_return", "总收益"),
        ("annual_return", "年化收益"),
        ("annual_volatility", "年化波动"),
        ("sharpe", "夏普"),
        ("max_drawdown", "最大回撤"),
        ("win_rate", "胜率"),
        ("benchmark_total_return", "基准总收益"),
        ("benchmark_max_drawdown", "基准最大回撤"),
    ]
    cols = st.columns(4)
    for index, (key, label) in enumerate(labels):
        value = metrics.get(key)
        if value is None or pd.isna(value):
            text = "-"
        elif "return" in key or "volatility" in key or "drawdown" in key or key == "win_rate":
            text = f"{value:.2%}"
        else:
            text = f"{value:.4f}"
        cols[index % 4].metric(label, text)


def safe_df(fn) -> pd.DataFrame:
    try:
        return fn()
    except Exception:
        return pd.DataFrame()


def _coverage_value(coverage: pd.DataFrame, group: str, column: str) -> float:
    if coverage.empty or column not in coverage.columns:
        return 0.0
    match = coverage.loc[coverage["asset_group"] == group, column]
    if match.empty or pd.isna(match.iloc[0]):
        return 0.0
    return float(match.iloc[0])


def _max_date(frame: pd.DataFrame, column: str) -> str | None:
    if frame.empty or column not in frame.columns:
        return None
    value = frame[column].max()
    if pd.isna(value):
        return None
    return str(value)


def _price_date_bounds() -> tuple[date, date]:
    fallback = date.today()
    try:
        bounds = query(
            """
            SELECT MIN(date) AS start_date, MAX(date) AS end_date
            FROM prices_daily
            WHERE asset_id LIKE 'A_STOCK_%'
            """
        )
        start = _to_date(bounds["start_date"].iloc[0], fallback)
        end = _to_date(bounds["end_date"].iloc[0], fallback)
        return start, end
    except Exception:
        return fallback, fallback


def _to_date(value, fallback: date) -> date:
    if value is None or pd.isna(value):
        return fallback
    return pd.to_datetime(value).date()


def _get_query_page() -> str:
    try:
        page = st.query_params.get("page", "首页")
    except Exception:
        return "首页"
    if isinstance(page, list):
        page = page[0] if page else "首页"
    return page if page in PAGES else "首页"


def _set_query_page(page: str) -> None:
    try:
        st.query_params["page"] = page
    except Exception:
        return


if __name__ == "__main__":
    main()
