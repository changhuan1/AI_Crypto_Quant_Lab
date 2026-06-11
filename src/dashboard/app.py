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
st.caption("上证指数成分股 + Crypto 的本地量化研究驾驶舱")


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


def render_system_map() -> None:
    st.subheader("系统全景图")
    st.write(
        "这张图展示系统从原始数据到最终可视化的完整链路。你可以把它当成项目地图："
        "左边是数据来源，中间是数据库、因子和策略，右边是回测、信号和面板。"
    )

    st.graphviz_chart(
        """
        digraph {
            graph [rankdir=LR, bgcolor="transparent", pad="0.2", nodesep="0.35", ranksep="0.55"];
            node [shape=box, style="rounded,filled", color="#CBD5E1", fillcolor="#F8FAFC", fontname="Microsoft YaHei", fontsize=11];
            edge [color="#64748B", arrowsize=0.8, fontname="Microsoft YaHei", fontsize=10];

            a_data [label="A股数据\\n上证成分股 + 上证指数"];
            c_data [label="Crypto数据\\nBTC/ETH 日线"];
            db [label="DuckDB\\nprices_daily / features_daily / signals_daily / portfolio_nav", fillcolor="#EEF2FF"];
            features [label="因子层\\n收益率 / 均线 / 波动率 / 相对强弱 / 市场宽度", fillcolor="#F0FDFA"];
            risk [label="风险状态\\nrisk_on / neutral / risk_off", fillcolor="#FFF7ED"];
            scoring [label="评分层\\nA_Share_Market_Score / Crypto_Score", fillcolor="#F0F9FF"];
            portfolio [label="组合层\\n目标仓位 / 现金 / 风控标记", fillcolor="#FDF2F8"];
            backtest [label="回测层\\n净值 / 回撤 / 暴露 / 指标", fillcolor="#ECFDF5"];
            dashboard [label="Streamlit面板\\n流程 / 信号 / 宽度 / 净值 / 数据健康", fillcolor="#FAF5FF"];

            a_data -> db;
            c_data -> db;
            db -> features;
            features -> risk;
            features -> scoring;
            risk -> portfolio;
            scoring -> portfolio;
            portfolio -> backtest;
            db -> dashboard;
            features -> dashboard;
            portfolio -> dashboard;
            backtest -> dashboard;
        }
        """,
        width="stretch",
    )


def render_pipeline_status() -> None:
    st.subheader("运行流程")
    st.write("按从上到下的顺序运行。每一步右侧会根据当前 DuckDB 里的数据判断是否已经有结果。")

    status = build_pipeline_status()
    st.dataframe(status, width="stretch", hide_index=True)

    st.markdown("**推荐小样本验证命令**")
    st.code(
        "\n".join(
            [
                "conda activate ai_crypto_quant_lab",
                "python -m src.jobs.init_db",
                "python -m src.data_ingestion.a_share_market_prices --limit 50",
                "python -m src.jobs.a_share_market_update",
                "python -m src.jobs.a_share_breadth_update",
                "python -m src.backtest.backtest_a_share_market",
                "python -m src.data_ingestion.crypto_prices_ccxt",
                "python -m src.jobs.crypto_update",
                "python -m src.backtest.backtest_crypto",
                "streamlit run src/dashboard/app.py",
            ]
        ),
        language="powershell",
    )

    with st.expander("全量上证成分股运行说明"):
        st.write(
            "小样本通过后，把 `--limit 50` 去掉即可拉取上证指数全部成分股。"
            "全量会访问 2000 多只股票，耗时较长，也更依赖 AKShare 数据源和网络稳定性。"
        )
        st.code("python -m src.data_ingestion.a_share_market_prices", language="powershell")


def build_pipeline_status() -> pd.DataFrame:
    a_stock_pattern = "A_STOCK_%"
    crypto_pattern = "CRYPTO_%"
    a_stock_condition = "asset_id LIKE 'A_STOCK_%'"
    crypto_condition = "asset_id LIKE 'CRYPTO_%'"
    breadth_condition = "asset_id = 'A_MARKET_000001'"

    checks = [
        {
            "步骤": "1. 初始化数据库",
            "命令": "python -m src.jobs.init_db",
            "状态": "完成" if _table_count("prices_daily") is not None else "待运行",
            "结果": "DuckDB 表结构已存在" if DB_PATH.exists() else "未发现数据库文件",
        },
        {
            "步骤": "2. 拉取上证成分股行情",
            "命令": "python -m src.data_ingestion.a_share_market_prices --limit 50",
            "状态": _ok_if(_count_assets(a_stock_pattern) > 0),
            "结果": f"{_count_assets(a_stock_pattern)} 只股票，{_count_rows(a_stock_condition)} 行价格",
        },
        {
            "步骤": "3. 计算上证成分股特征",
            "命令": "python -m src.jobs.a_share_market_update",
            "状态": _ok_if(_count_feature_assets(a_stock_pattern) > 0),
            "结果": f"{_count_feature_assets(a_stock_pattern)} 只股票有特征",
        },
        {
            "步骤": "4. 计算上证市场宽度",
            "命令": "python -m src.jobs.a_share_breadth_update",
            "状态": _ok_if(_count_rows(breadth_condition, table="features_daily") > 0),
            "结果": f"{_count_rows(breadth_condition, table='features_daily')} 行宽度特征",
        },
        {
            "步骤": "5. 回测上证成分股策略",
            "命令": "python -m src.backtest.backtest_a_share_market",
            "状态": _ok_if(_strategy_nav_rows(A_SHARE_STRATEGY) > 0),
            "结果": f"{_strategy_nav_rows(A_SHARE_STRATEGY)} 行净值",
        },
        {
            "步骤": "6. 拉取 Crypto 行情",
            "命令": "python -m src.data_ingestion.crypto_prices_ccxt",
            "状态": _ok_if(_count_assets(crypto_pattern) > 0),
            "结果": f"{_count_assets(crypto_pattern)} 个币种，{_count_rows(crypto_condition)} 行价格",
        },
        {
            "步骤": "7. 计算 Crypto 特征",
            "命令": "python -m src.jobs.crypto_update",
            "状态": _ok_if(_count_feature_assets(crypto_pattern) > 0),
            "结果": f"{_count_feature_assets(crypto_pattern)} 个币种有特征",
        },
        {
            "步骤": "8. 回测 Crypto 策略",
            "命令": "python -m src.backtest.backtest_crypto",
            "状态": _ok_if(_strategy_nav_rows(CRYPTO_STRATEGY) > 0),
            "结果": f"{_strategy_nav_rows(CRYPTO_STRATEGY)} 行净值",
        },
    ]
    return pd.DataFrame(checks)


def render_strategy_explainer() -> None:
    st.subheader("策略逻辑说明")
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### 上证成分股策略")
        st.write(
            "股票池来自 `ak.index_stock_cons('000001')`，也就是上证指数成分股。"
            "系统为每只股票计算动量、成交额、相对上证指数强弱、波动率和是否站上 120 日均线。"
        )
        st.markdown(
            """
            **当前选股逻辑**

            - 每周五调仓。
            - 只考虑站上 120 日均线的股票。
            - 过滤成交额低于横截面中位数的股票。
            - 按 `a_share_market_score` 排名。
            - 默认最多选 30 只。
            - 单只股票最大 3% 仓位。
            - `risk_off` 时空仓。
            """
        )

    with c2:
        st.markdown("### Crypto 策略")
        st.write(
            "Crypto 第一版只使用现货 BTC/USDT 和 ETH/USDT，用 OKX 日线数据。"
            "策略更偏风控验证，而不是追求最高收益。"
        )
        st.markdown(
            """
            **当前轮动逻辑**

            - 每日生成信号。
            - 根据 BTC 均线、动量和波动判断风险状态。
            - `risk_off` 时保持现金。
            - `neutral` 最大 30% Crypto 仓位。
            - `risk_on` 最大 60% Crypto 仓位。
            - BTC/ETH 单个最大 30%。
            """
        )

    st.markdown("### 评分公式直观解释")
    formula = pd.DataFrame(
        [
            ["价格动量", "近 7/20/60 日收益表现", "越强越靠前"],
            ["成交额确认", "成交额在横截面中的相对水平", "越活跃越靠前"],
            ["相对强弱", "相对基准的 20 日强弱", "跑赢基准加分"],
            ["市场宽度", "上证成分股整体上涨和均线状态", "市场环境好时加分"],
            ["风险惩罚", "波动率和跌破均线", "风险高则扣分"],
        ],
        columns=["因子", "含义", "作用"],
    )
    st.dataframe(formula, width="stretch", hide_index=True)


def render_current_snapshot() -> None:
    st.subheader("当前系统快照")
    c1, c2 = st.columns(2)
    with c1:
        render_latest_signals()
    with c2:
        render_a_share_breadth()


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


def _table_count(table: str) -> int | None:
    try:
        result = query(f"SELECT COUNT(*) AS n FROM {table}")
        return int(result["n"].iloc[0])
    except Exception:
        return None


def _count_assets(pattern: str) -> int:
    result = query(
        f"""
        SELECT COUNT(DISTINCT asset_id) AS n
        FROM prices_daily
        WHERE asset_id LIKE '{pattern}'
        """
    )
    return int(result["n"].iloc[0])


def _count_feature_assets(pattern: str) -> int:
    result = query(
        f"""
        SELECT COUNT(DISTINCT asset_id) AS n
        FROM features_daily
        WHERE asset_id LIKE '{pattern}'
        """
    )
    return int(result["n"].iloc[0])


def _count_rows(condition: str, table: str = "prices_daily") -> int:
    result = query(f"SELECT COUNT(*) AS n FROM {table} WHERE {condition}")
    return int(result["n"].iloc[0])


def _strategy_nav_rows(strategy: str) -> int:
    result = query(
        f"""
        SELECT COUNT(*) AS n
        FROM portfolio_nav
        WHERE strategy = '{strategy}'
        """
    )
    return int(result["n"].iloc[0])


def _ok_if(condition: bool) -> str:
    return "完成" if condition else "待运行"


def _fmt_pct(value) -> str:
    if pd.isna(value):
        return "-"
    return f"{value:.2%}"


require_database()
render_metric_cards()

tab_map, tab_flow, tab_explain, tab_snapshot, tab_nav, tab_signals, tab_breadth, tab_data = st.tabs(
    ["系统地图", "运行流程", "策略解释", "当前快照", "净值", "信号", "市场宽度", "数据"]
)

with tab_map:
    render_system_map()

with tab_flow:
    render_pipeline_status()

with tab_explain:
    render_strategy_explainer()

with tab_snapshot:
    render_current_snapshot()

with tab_nav:
    render_nav()

with tab_signals:
    render_latest_signals()

with tab_breadth:
    render_a_share_breadth()

with tab_data:
    render_data_health()
