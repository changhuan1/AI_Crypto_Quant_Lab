from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st


DB_PATH = Path("data/db/quant_lab.duckdb")
A_SHARE_STRATEGY = "a_share_market_rotation_v0"
CRYPTO_STRATEGY = "crypto_spot_rotation_v0"
BREADTH_ASSET_ID = "A_MARKET_000001"


st.set_page_config(page_title="A-Share Crypto Quant Lab", layout="wide")
st.title("A-Share Crypto Quant Lab")


@st.cache_data(show_spinner=False)
def query(sql: str) -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        return con.execute(sql).df()


def require_database() -> None:
    if not DB_PATH.exists():
        st.error("数据库不存在，请先运行：python -m src.jobs.init_db")
        st.stop()


def render_metric_cards() -> None:
    nav = query(
        """
        SELECT strategy, date, nav, max_drawdown, gross_exposure
        FROM portfolio_nav
        QUALIFY ROW_NUMBER() OVER (PARTITION BY strategy ORDER BY date DESC) = 1
        ORDER BY strategy
        """
    )
    signals = query(
        """
        SELECT strategy, COUNT(*) AS signal_rows, MAX(date) AS latest_signal_date
        FROM signals_daily
        GROUP BY strategy
        ORDER BY strategy
        """
    )

    cols = st.columns(4)
    cols[0].metric("策略数量", len(nav))
    cols[1].metric("信号策略", len(signals))
    if not nav.empty:
        cols[2].metric("最新净值均值", f"{nav['nav'].mean():,.2f}")
        cols[3].metric("最深回撤", f"{nav['max_drawdown'].min():.2%}")
    else:
        cols[2].metric("最新净值均值", "-")
        cols[3].metric("最深回撤", "-")


def render_nav() -> None:
    st.subheader("组合净值")
    nav = query(
        """
        SELECT date, strategy, nav, max_drawdown, gross_exposure
        FROM portfolio_nav
        ORDER BY date, strategy
        """
    )
    if nav.empty:
        st.info("暂无净值数据，请先运行回测命令。")
        return

    fig = px.line(nav, x="date", y="nav", color="strategy", title=None)
    st.plotly_chart(fig, width="stretch")

    c1, c2 = st.columns(2)
    drawdown_fig = px.line(nav, x="date", y="max_drawdown", color="strategy", title=None)
    c1.plotly_chart(drawdown_fig, width="stretch")
    exposure_fig = px.line(nav, x="date", y="gross_exposure", color="strategy", title=None)
    c2.plotly_chart(exposure_fig, width="stretch")


def render_latest_signals() -> None:
    st.subheader("最新信号")
    strategy = st.selectbox(
        "策略",
        [A_SHARE_STRATEGY, CRYPTO_STRATEGY],
        index=0,
    )
    latest_date = query(
        f"""
        SELECT MAX(date) AS latest_date
        FROM signals_daily
        WHERE strategy = '{strategy}'
        """
    )["latest_date"].iloc[0]

    if pd.isna(latest_date):
        st.info("暂无信号数据。")
        return

    signals = query(
        f"""
        SELECT asset_id, date, strategy, score, signal, target_weight, risk_flag, reason
        FROM signals_daily
        WHERE strategy = '{strategy}'
          AND date = DATE '{latest_date}'
        ORDER BY target_weight DESC, score DESC NULLS LAST
        """
    )
    st.caption(f"最新信号日期：{latest_date}")
    st.dataframe(signals, width="stretch", hide_index=True)


def render_a_share_breadth() -> None:
    st.subheader("上证成分股市场宽度")
    breadth = query(
        f"""
        SELECT date, feature_name, value
        FROM features_daily
        WHERE asset_id = '{BREADTH_ASSET_ID}'
          AND feature_name IN (
            'up_ratio',
            'down_ratio',
            'above_ma_120_ratio',
            'turnover_expansion',
            'breadth_score',
            'universe_count'
          )
        ORDER BY date, feature_name
        """
    )
    if breadth.empty:
        st.info("暂无市场宽度数据，请先运行：python -m src.jobs.a_share_breadth_update")
        return

    wide = breadth.pivot(index="date", columns="feature_name", values="value").reset_index()
    latest = wide.sort_values("date").iloc[-1]

    cols = st.columns(4)
    cols[0].metric("股票池数量", f"{latest.get('universe_count', 0):.0f}")
    cols[1].metric("上涨比例", _fmt_pct(latest.get("up_ratio")))
    cols[2].metric("120日线上方比例", _fmt_pct(latest.get("above_ma_120_ratio")))
    cols[3].metric("宽度分数", f"{latest.get('breadth_score', float('nan')):.4f}")

    plot_cols = [c for c in ["up_ratio", "above_ma_120_ratio", "breadth_score"] if c in wide.columns]
    fig = px.line(wide, x="date", y=plot_cols, title=None)
    st.plotly_chart(fig, width="stretch")


def render_data_health() -> None:
    st.subheader("数据覆盖")
    coverage = query(
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
    )
    st.dataframe(coverage, width="stretch", hide_index=True)


def _fmt_pct(value) -> str:
    if pd.isna(value):
        return "-"
    return f"{value:.2%}"


require_database()
render_metric_cards()

tab_overview, tab_signals, tab_breadth, tab_data = st.tabs(
    ["净值", "信号", "市场宽度", "数据"]
)

with tab_overview:
    render_nav()

with tab_signals:
    render_latest_signals()

with tab_breadth:
    render_a_share_breadth()

with tab_data:
    render_data_health()
