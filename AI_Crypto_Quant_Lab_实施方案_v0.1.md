# AI 市场 × 加密货币量化系统技术实施方案 v0.1

> 项目名称：AI Crypto Quant Lab  
> 项目目标：构建一个低成本、可回测、可模拟交易、可解释的 AI 市场与加密货币双市场量化研究系统。  
> 第一阶段目标不是自动实盘盈利，而是完成“数据采集 → 因子计算 → 评分 → 回测 → 模拟交易 → 风控 → 仪表盘”的闭环。

---

## 0. 重要声明

本项目文档仅用于技术研究、数据分析、回测和模拟交易，不构成投资建议。加密货币在不同地区存在监管差异，如果使用者在中国大陆，应将加密货币部分限定为研究、数据分析、回测和模拟交易。

第一版坚持以下边界：

1. 不做杠杆。
2. 不做合约。
3. 不做期权。
4. 不做高频。
5. 不做自动做市。
6. 不做小市值土狗币。
7. 不让 LLM 自动下单。
8. 所有信号必须能解释。
9. 所有策略必须先回测，再 dry-run，再小资金验证。
10. 第一阶段重点是系统稳定性、风控能力和可迭代性。

---

## 1. 项目总体目标

### 1.1 一句话定义

AI Crypto Quant Lab 是一个双市场量化研究系统：

```text
AI 技术趋势数据
+ AI/科技主题市场行情
+ 加密货币市场行情
+ GitHub / Hugging Face / 新闻 / 公告 / 链上数据
+ 风控规则
= 每日/每周生成可解释的交易信号和模拟仓位
```

### 1.2 v0.1 要完成的事情

v0.1 只做 6 件事：

```text
1. 建立 AI 市场资产池和 Crypto 资产池。
2. 自动采集日线行情。
3. 自动采集 GitHub 和 Hugging Face 热度数据。
4. 计算 AI_Market_Score 和 Crypto_Score。
5. 完成简化回测。
6. 生成 Streamlit 仪表盘和每日 Markdown 报告。
```

### 1.3 v0.1 不做的事情

```text
不做实盘自动交易
不做强化学习
不做深度神经网络预测价格
不做分钟级交易
不做盘口策略
不做跨交易所套利
不做 LLM 自主交易
不做高杠杆
```

---

## 2. 系统总体架构

```text
                         ┌──────────────────────┐
                         │      Streamlit        │
                         │  仪表盘 / 每日报告     │
                         └──────────▲───────────┘
                                    │
                         ┌──────────┴───────────┐
                         │    Strategy Engine    │
                         │ AI轮动 / Crypto轮动    │
                         └──────────▲───────────┘
                                    │
                         ┌──────────┴───────────┐
                         │     Feature Store     │
                         │  因子 / 分数 / 风控状态 │
                         └──────────▲───────────┘
                                    │
       ┌────────────────────────────┼────────────────────────────┐
       │                            │                            │
┌──────┴───────┐           ┌────────┴─────────┐          ┌───────┴────────┐
│ Market Data   │           │ Alternative Data │          │ Text Data      │
│ 行情 / 成交量  │           │ GitHub / HF / 链上 │          │ 新闻 / 公告      │
└──────▲───────┘           └────────▲─────────┘          └───────▲────────┘
       │                            │                            │
       └────────────────────────────┼────────────────────────────┘
                                    │
                         ┌──────────┴───────────┐
                         │       DuckDB          │
                         │ 本地研究数据库         │
                         └──────────▲───────────┘
                                    │
                         ┌──────────┴───────────┐
                         │  Backtest / Dry-run   │
                         │ vectorbt / Freqtrade  │
                         └──────────────────────┘
```

---

## 3. 技术栈

| 模块 | 工具 | 用途 |
|---|---|---|
| 开发语言 | Python 3.11+ | 主开发语言 |
| 数据库 | DuckDB | 本地轻量级研究数据库 |
| 数据处理 | Pandas / Polars | 数据清洗、因子计算 |
| A 股 / ETF 数据 | AKShare | 低成本金融数据采集 |
| Crypto 行情 | CCXT | 统一交易所行情接口 |
| Crypto 回测 / 模拟 | Freqtrade | 回测、dry-run、策略验证 |
| 快速回测 | vectorbt | 快速做资产轮动回测 |
| AI 社区数据 | Hugging Face Hub | 模型下载量、likes、task、tags |
| 开源数据 | GitHub API / PyGithub | repo stars、forks、issues、更新时间 |
| 新闻数据 | GDELT / RSS / 自建爬虫 | AI 资讯热度 |
| 仪表盘 | Streamlit | 本地 Web 可视化 |
| 调度 | APScheduler / cron | 每日任务调度 |
| 实验管理 | YAML + Git | 第一版轻量化 |
| 部署 | 本地电脑 / VPS / Docker | 后期部署 |

---

## 4. 资产池设计

## 4.1 AI 市场资产池

第一阶段不直接做美股 AI 龙头短线，不做科创板、创业板、港股通。优先做普通账户可研究、可模拟、可回测的 AI/科技主题 ETF 或行业篮子。

### 4.1.1 AI 主题分类

```yaml
ai_themes:
  ai_infrastructure:
    name: AI基础设施
    keywords:
      - 半导体
      - 算力
      - 数据中心
      - 云计算
      - 光模块
      - 通信设备

  ai_software:
    name: AI软件应用
    keywords:
      - 计算机
      - 软件
      - 办公
      - 教育
      - 工业软件
      - 金融科技
      - 医疗AI

  ai_data:
    name: AI数据层
    keywords:
      - 数据要素
      - 数据治理
      - 数据安全
      - 知识图谱
      - 向量数据库

  ai_terminal_robotics:
    name: AI终端与机器人
    keywords:
      - 机器人
      - 智能驾驶
      - 端侧AI
      - 消费电子
```

### 4.1.2 AI 市场筛选规则

```text
必须满足：
1. 数据可获取。
2. 日成交额较高。
3. 非 ST、非退市风险。
4. 非极端连续涨停状态。
5. 有明确 AI/科技主题关联。
6. 回测样本至少覆盖 2 年以上。

优先选择：
1. ETF。
2. 行业指数基金。
3. 大流动性主板标的。
4. 可解释的科技主题篮子。

暂不选择：
1. 科创板个股。
2. 创业板个股。
3. 北交所个股。
4. 港股通。
5. 美股实盘。
6. 单日暴涨题材股。
```

---

## 4.2 Crypto 资产池

Crypto 第一阶段只做现货研究、回测和 dry-run。

```yaml
crypto_core:
  - symbol: BTC/USDT
    role: market_regime
    max_weight: 0.30

  - symbol: ETH/USDT
    role: smart_contract_beta
    max_weight: 0.30

crypto_watchlist_rules:
  min_quote_volume_24h_usd: 50000000
  min_history_days: 365
  exclude_new_listing_days: 90
  exclude_meme: true
  exclude_leverage_token: true
  exclude_futures: true
  exclude_spread_too_wide: true

crypto_themes:
  ai:
    keywords:
      - artificial intelligence
      - ai
      - agent
      - decentralized compute
      - gpu
      - inference
      - data

  depin:
    keywords:
      - depin
      - storage
      - compute
      - network
      - render

  infrastructure:
    keywords:
      - layer1
      - layer2
      - oracle
      - data availability
      - interoperability
```

Crypto 不碰清单：

```text
1. 永续合约。
2. 杠杆代币。
3. 刚上线新币。
4. MEME 币。
5. 单日暴涨暴跌小币。
6. 没有足够成交量的币。
7. 只能在单一小交易所交易的币。
8. 无法解释基本逻辑的币。
```

---

## 5. 项目目录结构

```text
ai_crypto_quant_lab/
  README.md
  pyproject.toml
  requirements.txt
  .env.example
  docker-compose.yml

  configs/
    assets_ai.yaml
    assets_crypto.yaml
    data_sources.yaml
    strategy_ai_market.yaml
    strategy_crypto_spot.yaml
    risk.yaml

  data/
    raw/
    processed/
    reports/
    db/
      quant_lab.duckdb

  src/
    common/
      config.py
      logger.py
      db.py
      utils.py

    data_ingestion/
      ai_market_prices.py
      crypto_prices_ccxt.py
      github_collector.py
      huggingface_collector.py
      news_collector.py
      coingecko_collector.py
      defillama_collector.py

    features/
      price_features.py
      volume_features.py
      volatility_features.py
      relative_strength.py
      opensource_features.py
      text_features.py
      crypto_features.py
      risk_regime.py

    strategies/
      ai_market_scoring.py
      crypto_scoring.py
      ai_rotation.py
      crypto_rotation.py
      position_sizing.py
      risk_control.py

    backtest/
      simple_rebalance_backtest.py
      backtest_ai_market.py
      backtest_crypto.py
      metrics.py
      validation.py

    execution/
      paper_broker.py
      order_sheet.py
      freqtrade_adapter.py

    dashboard/
      app.py

    jobs/
      init_db.py
      daily_update.py
      crypto_update.py
      weekly_rebalance.py

  notebooks/
    01_check_data.ipynb
    02_crypto_score.ipynb
    03_ai_market_score.ipynb
    04_backtest_crypto.ipynb
    05_backtest_ai.ipynb

  tests/
    test_no_lookahead.py
    test_risk_control.py
    test_position_sizing.py
```

---

## 6. 环境安装步骤

### 6.1 创建项目

```bash
mkdir ai_crypto_quant_lab
cd ai_crypto_quant_lab

python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
```

### 6.2 安装依赖

创建 `requirements.txt`：

```txt
pandas
polars
duckdb
numpy
scipy
scikit-learn
pyyaml
requests
httpx
akshare
ccxt
vectorbt
streamlit
plotly
huggingface_hub
PyGithub
apscheduler
python-dotenv
```

安装：

```bash
pip install -r requirements.txt
```

### 6.3 安装 Freqtrade

建议将 Freqtrade 作为外部工具单独安装，避免依赖冲突。

```bash
mkdir external
cd external
git clone https://github.com/freqtrade/freqtrade.git
cd freqtrade
./setup.sh --install
```

Windows 用户可优先使用 WSL2 或 Docker。

---

## 7. 环境变量配置

创建 `.env.example`：

```bash
GITHUB_TOKEN=your_github_token
HF_TOKEN=your_huggingface_token
DB_PATH=data/db/quant_lab.duckdb

# 第一阶段不需要真实交易 API
EXCHANGE_ID=binance
EXCHANGE_API_KEY=
EXCHANGE_API_SECRET=
```

复制：

```bash
cp .env.example .env
```

注意事项：

```text
1. v0.1 不需要交易所真实 API。
2. Crypto 先用公开行情接口。
3. 即便后期接 API，也必须关闭提现权限。
4. API key 必须限制 IP。
5. 不要把 .env 上传到 GitHub。
```

创建 `.gitignore`：

```gitignore
.venv/
.env
data/db/
data/raw/
data/processed/
__pycache__/
*.pyc
.ipynb_checkpoints/
external/
```

---

## 8. 数据库设计

使用 DuckDB，第一版建立以下表。

文件：`src/jobs/init_db.py`

```python
from pathlib import Path
import duckdb

DB_PATH = Path("data/db/quant_lab.duckdb")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DDL = """
CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    symbol TEXT,
    name TEXT,
    market TEXT,
    asset_type TEXT,
    theme TEXT,
    is_active BOOLEAN,
    liquidity_tier TEXT,
    created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prices_daily (
    asset_id TEXT,
    date DATE,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    turnover DOUBLE,
    source TEXT,
    created_at TIMESTAMP,
    PRIMARY KEY(asset_id, date, source)
);

CREATE TABLE IF NOT EXISTS github_metrics (
    repo_full_name TEXT,
    date DATE,
    stars INTEGER,
    forks INTEGER,
    open_issues INTEGER,
    pushed_at TIMESTAMP,
    theme TEXT,
    source TEXT,
    created_at TIMESTAMP,
    PRIMARY KEY(repo_full_name, date)
);

CREATE TABLE IF NOT EXISTS huggingface_metrics (
    model_id TEXT,
    date DATE,
    author TEXT,
    task TEXT,
    downloads INTEGER,
    likes INTEGER,
    last_modified TIMESTAMP,
    tags TEXT,
    theme TEXT,
    created_at TIMESTAMP,
    PRIMARY KEY(model_id, date)
);

CREATE TABLE IF NOT EXISTS features_daily (
    asset_id TEXT,
    date DATE,
    feature_name TEXT,
    value DOUBLE,
    created_at TIMESTAMP,
    PRIMARY KEY(asset_id, date, feature_name)
);

CREATE TABLE IF NOT EXISTS signals_daily (
    asset_id TEXT,
    date DATE,
    strategy TEXT,
    score DOUBLE,
    signal TEXT,
    target_weight DOUBLE,
    risk_flag BOOLEAN,
    reason TEXT,
    created_at TIMESTAMP,
    PRIMARY KEY(asset_id, date, strategy)
);

CREATE TABLE IF NOT EXISTS portfolio_nav (
    date DATE,
    strategy TEXT,
    nav DOUBLE,
    cash DOUBLE,
    gross_exposure DOUBLE,
    max_drawdown DOUBLE,
    created_at TIMESTAMP,
    PRIMARY KEY(date, strategy)
);
"""

def main():
    con = duckdb.connect(str(DB_PATH))
    con.execute(DDL)
    con.close()
    print(f"Database initialized: {DB_PATH}")

if __name__ == "__main__":
    main()
```

运行：

```bash
python -m src.jobs.init_db
```

---

## 9. 配置文件

### 9.1 风控配置

文件：`configs/risk.yaml`

```yaml
global:
  max_total_drawdown_warning: -0.05
  max_total_drawdown_reduce: -0.08
  max_total_drawdown_stop: -0.12
  allow_leverage: false
  allow_short: false
  allow_derivatives: false

ai_market:
  max_gross_exposure: 0.80
  max_single_position: 0.25
  max_positions: 5
  rebalance_frequency: weekly
  min_avg_turnover_20d: 50000000
  avoid_limit_up_chasing: true

crypto:
  max_gross_exposure: 0.60
  max_core_position: 0.30
  max_satellite_position: 0.08
  max_ai_crypto_total: 0.20
  max_positions: 5
  allow_futures: false
  allow_margin: false
  allow_new_listings: false
  min_quote_volume_24h_usd: 50000000
```

### 9.2 Crypto 资产配置

文件：`configs/assets_crypto.yaml`

```yaml
core:
  - symbol: BTC/USDT
    role: benchmark
    max_weight: 0.30

  - symbol: ETH/USDT
    role: benchmark
    max_weight: 0.30

watchlist_rules:
  min_quote_volume_24h_usd: 50000000
  min_history_days: 365
  exclude_new_listing_days: 90
  exclude_if_spread_too_wide: true
  exclude_meme: true
  exclude_leverage_token: true
  exclude_futures: true

manual_watchlist:
  - BTC/USDT
  - ETH/USDT
```

### 9.3 Crypto 策略配置

文件：`configs/strategy_crypto_spot.yaml`

```yaml
risk_regime:
  btc_ma_long: 120
  btc_ma_mid: 60
  btc_momentum_window: 20
  volatility_window: 30

score_weights:
  price_momentum: 0.35
  volume_acceleration: 0.20
  relative_strength_vs_btc: 0.15
  narrative_heat: 0.15
  fundamental_confirmation: 0.10
  risk_penalty: -0.20

rebalance:
  frequency: daily
  top_n: 5
  min_score: 0.0
```

### 9.4 AI 市场策略配置

文件：`configs/strategy_ai_market.yaml`

```yaml
score_weights:
  price_momentum: 0.30
  volume_confirmation: 0.20
  ai_news_heat: 0.20
  open_source_heat: 0.20
  risk_penalty: -0.10

rebalance:
  frequency: weekly
  top_n: 5
  min_score: 0.0

risk_filter:
  require_above_ma120: true
  avoid_extreme_20d_return: true
  avoid_low_liquidity: true
```

---

## 10. 数据采集模块

### 10.1 Crypto 行情采集

文件：`src/data_ingestion/crypto_prices_ccxt.py`

```python
from datetime import datetime
from pathlib import Path

import ccxt
import duckdb
import pandas as pd

DB_PATH = Path("data/db/quant_lab.duckdb")

def fetch_crypto_ohlcv(exchange_id: str, symbol: str, timeframe: str = "1d", limit: int = 1000) -> pd.DataFrame:
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({"enableRateLimit": True})

    rows = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms").dt.date
    df["asset_id"] = "CRYPTO_" + symbol.replace("/", "_")
    df["turnover"] = df["close"] * df["volume"]
    df["source"] = exchange_id
    df["created_at"] = datetime.utcnow()

    return df[["asset_id", "date", "open", "high", "low", "close", "volume", "turnover", "source", "created_at"]]

def save_prices(df: pd.DataFrame) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.register("df_temp", df)
    con.execute("INSERT OR REPLACE INTO prices_daily SELECT * FROM df_temp")
    con.close()

def main():
    symbols = ["BTC/USDT", "ETH/USDT"]
    all_df = []

    for symbol in symbols:
        print(f"Fetching {symbol}")
        df = fetch_crypto_ohlcv("binance", symbol)
        all_df.append(df)

    result = pd.concat(all_df, ignore_index=True)
    save_prices(result)
    print("Crypto prices saved.")

if __name__ == "__main__":
    main()
```

运行：

```bash
python -m src.data_ingestion.crypto_prices_ccxt
```

### 10.2 AI 市场行情采集

文件：`src/data_ingestion/ai_market_prices.py`

```python
from datetime import datetime
from pathlib import Path

import akshare as ak
import duckdb
import pandas as pd

DB_PATH = Path("data/db/quant_lab.duckdb")

def fetch_a_share_daily(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    df = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust="qfq",
    )

    if df.empty:
        return df

    df = df.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "turnover",
        }
    )

    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["asset_id"] = f"A_{symbol}"
    df["source"] = "akshare"
    df["created_at"] = datetime.utcnow()

    return df[["asset_id", "date", "open", "high", "low", "close", "volume", "turnover", "source", "created_at"]]

def save_prices(df: pd.DataFrame) -> None:
    con = duckdb.connect(str(DB_PATH))
    con.register("df_temp", df)
    con.execute("INSERT OR REPLACE INTO prices_daily SELECT * FROM df_temp")
    con.close()

def main():
    # 示例代码。实际项目中这里应替换为你的 ETF / 主题篮子代码。
    symbols = ["000001", "000300"]

    all_df = []
    for symbol in symbols:
        print(f"Fetching {symbol}")
        df = fetch_a_share_daily(symbol, "20200101", "20261231")
        if not df.empty:
            all_df.append(df)

    if all_df:
        result = pd.concat(all_df, ignore_index=True)
        save_prices(result)
        print("AI market prices saved.")

if __name__ == "__main__":
    main()
```

---

## 11. 特征工程

### 11.1 价格特征

文件：`src/features/price_features.py`

```python
import numpy as np
import pandas as pd

def add_price_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["asset_id", "date"]).copy()
    group = df.groupby("asset_id", group_keys=False)

    df["ret_1d"] = group["close"].pct_change(1)
    df["ret_7d"] = group["close"].pct_change(7)
    df["ret_20d"] = group["close"].pct_change(20)
    df["ret_60d"] = group["close"].pct_change(60)

    df["ma_20"] = group["close"].transform(lambda x: x.rolling(20).mean())
    df["ma_60"] = group["close"].transform(lambda x: x.rolling(60).mean())
    df["ma_120"] = group["close"].transform(lambda x: x.rolling(120).mean())

    df["volatility_20d"] = group["ret_1d"].transform(lambda x: x.rolling(20).std()) * np.sqrt(252)
    df["above_ma_120"] = (df["close"] > df["ma_120"]).astype(int)

    return df
```

### 11.2 相对强弱特征

文件：`src/features/relative_strength.py`

```python
import pandas as pd

def add_relative_strength(df: pd.DataFrame, benchmark_asset_id: str, window: int = 20) -> pd.DataFrame:
    df = df.copy()

    bench = df[df["asset_id"] == benchmark_asset_id][["date", "close"]].copy()
    bench = bench.rename(columns={"close": "benchmark_close"})
    bench["benchmark_ret"] = bench["benchmark_close"].pct_change(window)

    df = df.merge(bench[["date", "benchmark_ret"]], on="date", how="left")
    df[f"ret_{window}d_for_rs"] = df.groupby("asset_id")["close"].pct_change(window)
    df[f"relative_strength_{window}d"] = df[f"ret_{window}d_for_rs"] - df["benchmark_ret"]

    return df
```

---

## 12. 风险状态判断

文件：`src/features/risk_regime.py`

```python
def detect_crypto_regime(btc_row: dict) -> str:
    close = btc_row["close"]
    ma_60 = btc_row["ma_60"]
    ma_120 = btc_row["ma_120"]
    ret_20d = btc_row["ret_20d"]
    vol_20d = btc_row["volatility_20d"]

    if close > ma_120 and close > ma_60 and ret_20d > 0:
        return "risk_on"

    if close < ma_120 or ret_20d < -0.15 or vol_20d > 1.2:
        return "risk_off"

    return "neutral"

def detect_ai_market_regime(benchmark_row: dict) -> str:
    close = benchmark_row["close"]
    ma_120 = benchmark_row["ma_120"]
    ret_20d = benchmark_row["ret_20d"]
    vol_20d = benchmark_row["volatility_20d"]

    if close > ma_120 and ret_20d > 0:
        return "risk_on"

    if close < ma_120 and ret_20d < 0:
        return "risk_off"

    if vol_20d > 0.45:
        return "high_volatility"

    return "neutral"
```

---

## 13. 评分模型

### 13.1 Crypto_Score

文件：`src/strategies/crypto_scoring.py`

```python
import pandas as pd
from scipy.stats import zscore

def safe_zscore(s: pd.Series) -> pd.Series:
    if s.std() == 0 or s.isna().all():
        return pd.Series(0, index=s.index)
    return pd.Series(zscore(s.fillna(s.median())), index=s.index)

def calculate_crypto_score(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    by_date = df.groupby("date", group_keys=False)

    df["z_ret_7d"] = by_date["ret_7d"].transform(safe_zscore)
    df["z_ret_20d"] = by_date["ret_20d"].transform(safe_zscore)
    df["z_ret_60d"] = by_date["ret_60d"].transform(safe_zscore)
    df["z_volume"] = by_date["turnover"].transform(safe_zscore)
    df["z_relative_btc"] = by_date["relative_strength_20d"].transform(safe_zscore)
    df["z_volatility"] = by_date["volatility_20d"].transform(safe_zscore)

    df["price_momentum"] = 0.3 * df["z_ret_7d"] + 0.4 * df["z_ret_20d"] + 0.3 * df["z_ret_60d"]
    df["volume_acceleration"] = df["z_volume"]
    df["relative_strength_vs_btc"] = df["z_relative_btc"]

    # v0.1 暂时置 0，v0.2 再接入新闻、CoinGecko 分类、链上数据
    df["narrative_heat"] = 0
    df["fundamental_confirmation"] = 0
    df["risk_penalty"] = df["z_volatility"]

    df["crypto_score"] = (
        0.35 * df["price_momentum"]
        + 0.20 * df["volume_acceleration"]
        + 0.15 * df["relative_strength_vs_btc"]
        + 0.15 * df["narrative_heat"]
        + 0.10 * df["fundamental_confirmation"]
        - 0.20 * df["risk_penalty"]
    )

    return df
```

### 13.2 AI_Market_Score

文件：`src/strategies/ai_market_scoring.py`

```python
import pandas as pd
from scipy.stats import zscore

def safe_zscore(s: pd.Series) -> pd.Series:
    if s.std() == 0 or s.isna().all():
        return pd.Series(0, index=s.index)
    return pd.Series(zscore(s.fillna(s.median())), index=s.index)

def calculate_ai_market_score(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    by_date = df.groupby("date", group_keys=False)

    df["z_mom_20"] = by_date["ret_20d"].transform(safe_zscore)
    df["z_mom_60"] = by_date["ret_60d"].transform(safe_zscore)
    df["z_turnover"] = by_date["turnover"].transform(safe_zscore)
    df["z_volatility"] = by_date["volatility_20d"].transform(safe_zscore)

    if "relative_strength_20d" in df.columns:
        df["z_relative"] = by_date["relative_strength_20d"].transform(safe_zscore)
    else:
        df["z_relative"] = 0

    df["price_momentum"] = 0.4 * df["z_mom_20"] + 0.4 * df["z_mom_60"] + 0.2 * df["z_relative"]
    df["volume_confirmation"] = df["z_turnover"]

    # v0.1 暂时置 0，v0.2 接 GitHub、HF、新闻
    df["ai_news_heat"] = 0
    df["open_source_heat"] = 0

    df["risk_penalty"] = 0.7 * df["z_volatility"] + 0.3 * (1 - df["above_ma_120"])

    df["ai_market_score"] = (
        0.30 * df["price_momentum"]
        + 0.20 * df["volume_confirmation"]
        + 0.20 * df["ai_news_heat"]
        + 0.20 * df["open_source_heat"]
        - 0.10 * df["risk_penalty"]
    )

    return df
```

---

## 14. 仓位生成规则

### 14.1 Crypto 仓位

文件：`src/strategies/crypto_rotation.py`

```python
def generate_crypto_targets(scores_df, crypto_regime: str):
    latest = scores_df.copy()

    if crypto_regime == "risk_off":
        return {"CASH": 1.0}

    if crypto_regime == "neutral":
        max_exposure = 0.30
    else:
        max_exposure = 0.60

    candidates = latest.sort_values("crypto_score", ascending=False).head(5)
    targets = {}

    for _, row in candidates.iterrows():
        asset_id = row["asset_id"]

        if "BTC" in asset_id or "ETH" in asset_id:
            max_w = 0.30
        else:
            max_w = 0.08

        suggested = max_exposure / len(candidates)
        targets[asset_id] = min(max_w, suggested)

    used = sum(targets.values())
    targets["CASH"] = max(0, 1 - used)

    return targets
```

### 14.2 AI 市场仓位

文件：`src/strategies/ai_rotation.py`

```python
def generate_ai_targets(scores_df, market_regime: str):
    latest = scores_df.copy()

    if market_regime == "risk_off":
        return {"CASH": 0.8, "LOW_RISK_FUND": 0.2}

    if market_regime == "high_volatility":
        max_exposure = 0.3
    elif market_regime == "neutral":
        max_exposure = 0.5
    else:
        max_exposure = 0.8

    candidates = latest[
        (latest["above_ma_120"] == 1)
        & (latest["turnover"] > latest["turnover"].quantile(0.5))
    ].sort_values("ai_market_score", ascending=False).head(5)

    if candidates.empty:
        return {"CASH": 1.0}

    weight = min(0.25, max_exposure / len(candidates))

    targets = {
        row["asset_id"]: weight
        for _, row in candidates.iterrows()
    }

    used = sum(targets.values())
    targets["CASH"] = max(0, 1 - used)

    return targets
```

---

## 15. 简化回测

文件：`src/backtest/simple_rebalance_backtest.py`

```python
import pandas as pd

def backtest_rebalance(
    prices: pd.DataFrame,
    signals: pd.DataFrame,
    initial_cash: float = 100000,
    fee_rate: float = 0.001,
):
    prices = prices.sort_values(["date", "asset_id"])
    dates = sorted(prices["date"].unique())

    nav = initial_cash
    holdings = {}
    nav_records = []

    for date in dates:
        price_today = prices[prices["date"] == date].set_index("asset_id")["close"].to_dict()

        portfolio_value = 0
        for asset_id, qty in holdings.items():
            if asset_id in price_today:
                portfolio_value += qty * price_today[asset_id]

        if holdings:
            nav = portfolio_value

        signal_today = signals[signals["date"] == date]

        if not signal_today.empty:
            target_weights = signal_today.set_index("asset_id")["target_weight"].to_dict()
            new_holdings = {}
            turnover_value = 0

            for asset_id, weight in target_weights.items():
                if asset_id == "CASH":
                    continue
                if asset_id not in price_today:
                    continue

                target_value = nav * weight
                current_value = holdings.get(asset_id, 0) * price_today[asset_id]
                turnover_value += abs(target_value - current_value)
                new_holdings[asset_id] = target_value / price_today[asset_id]

            fee = turnover_value * fee_rate
            nav -= fee
            holdings = new_holdings

        nav_records.append({"date": date, "nav": nav, "holdings_count": len(holdings)})

    result = pd.DataFrame(nav_records)
    result["return"] = result["nav"].pct_change().fillna(0)
    result["cummax"] = result["nav"].cummax()
    result["drawdown"] = result["nav"] / result["cummax"] - 1

    return result
```

---

## 16. 评价指标

文件：`src/backtest/metrics.py`

```python
import numpy as np
import pandas as pd

def calculate_metrics(nav_df: pd.DataFrame, periods_per_year: int = 252) -> dict:
    df = nav_df.copy()
    returns = df["nav"].pct_change().dropna()

    total_return = df["nav"].iloc[-1] / df["nav"].iloc[0] - 1
    years = len(df) / periods_per_year

    if years > 0:
        annual_return = (1 + total_return) ** (1 / years) - 1
    else:
        annual_return = 0

    annual_vol = returns.std() * np.sqrt(periods_per_year)

    sharpe = 0
    if annual_vol != 0:
        sharpe = annual_return / annual_vol

    max_drawdown = (df["nav"] / df["nav"].cummax() - 1).min()
    win_rate = (returns > 0).mean()

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "annual_volatility": annual_vol,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
    }
```

---

## 17. Freqtrade dry-run 配置

Crypto 第一阶段不要直接实盘，使用 dry-run。

示例配置：

```json
{
  "dry_run": true,
  "dry_run_wallet": 10000,
  "trading_mode": "spot",
  "margin_mode": "",
  "stake_currency": "USDT",
  "stake_amount": "unlimited",
  "max_open_trades": 5,
  "cancel_open_orders_on_exit": true,
  "exchange": {
    "name": "binance",
    "key": "",
    "secret": "",
    "ccxt_config": {
      "enableRateLimit": true
    },
    "pair_whitelist": [
      "BTC/USDT",
      "ETH/USDT"
    ],
    "pair_blacklist": [
      ".*UP/USDT",
      ".*DOWN/USDT",
      ".*BULL/USDT",
      ".*BEAR/USDT"
    ]
  }
}
```

运行示例：

```bash
freqtrade backtesting -c user_data/config.json --strategy YourStrategy
freqtrade trade -c user_data/config.json --strategy YourStrategy
```

---

## 18. Dashboard

文件：`src/dashboard/app.py`

```python
from pathlib import Path

import duckdb
import streamlit as st

DB_PATH = Path("data/db/quant_lab.duckdb")

st.set_page_config(page_title="AI Crypto Quant Lab", layout="wide")
st.title("AI × Crypto Quant Lab")

if not DB_PATH.exists():
    st.error("数据库不存在，请先运行：python -m src.jobs.init_db")
    st.stop()

con = duckdb.connect(str(DB_PATH))

st.header("今日信号")

try:
    latest_signals = con.execute(
        """
        SELECT *
        FROM signals_daily
        WHERE date = (SELECT MAX(date) FROM signals_daily)
        ORDER BY strategy, score DESC
        """
    ).df()

    st.dataframe(latest_signals, use_container_width=True)

except Exception as e:
    st.warning(f"暂无信号数据：{e}")

st.header("组合净值")

try:
    nav = con.execute(
        """
        SELECT *
        FROM portfolio_nav
        ORDER BY date
        """
    ).df()

    if not nav.empty:
        st.line_chart(nav.set_index("date")["nav"])
    else:
        st.info("暂无组合净值数据。")

except Exception as e:
    st.warning(f"暂无净值数据：{e}")

con.close()
```

运行：

```bash
streamlit run src/dashboard/app.py
```

---

## 19. 每日任务

文件：`src/jobs/daily_update.py`

```python
def daily_update():
    print("Step 1: update market data")
    # update_ai_market_prices()
    # update_crypto_prices()

    print("Step 2: update alternative data")
    # update_github_metrics()
    # update_huggingface_metrics()

    print("Step 3: build features")
    # build_price_features()
    # build_open_source_features()

    print("Step 4: calculate scores")
    # calculate_ai_scores()
    # calculate_crypto_scores()

    print("Step 5: generate signals")
    # generate_ai_signals()
    # generate_crypto_signals()

    print("Step 6: risk control")
    # run_risk_checks()

    print("Step 7: save report")
    # save_daily_report()

if __name__ == "__main__":
    daily_update()
```

本地定时任务示例：

```bash
# Linux / macOS crontab
0 20 * * 1-5 cd /path/to/ai_crypto_quant_lab && . .venv/bin/activate && python -m src.jobs.daily_update
0 8 * * * cd /path/to/ai_crypto_quant_lab && . .venv/bin/activate && python -m src.jobs.crypto_update
```

---

## 20. 每日报告模板

文件：`data/reports/YYYY-MM-DD_daily_report.md`

```markdown
# AI × Crypto Quant Lab Daily Report

日期：YYYY-MM-DD

## 1. 总体风险状态

AI 市场状态：Risk-On / Neutral / Risk-Off  
Crypto 市场状态：Risk-On / Neutral / Risk-Off  

## 2. AI 市场

今日 AI 主题热度排名：

1. Agent
2. RAG
3. Inference
4. Robotics
5. Data Infra

今日候选资产：

| 资产 | 分数 | 趋势 | 成交额 | 风险 | 建议权重 |
|---|---:|---:|---:|---:|---:|
| 示例 | 0.82 | 正 | 放大 | 低 | 20% |

## 3. Crypto 市场

BTC 状态：

- 是否在 120 日均线上方：
- 20 日收益：
- 波动率：
- 风险状态：

Crypto 候选资产：

| 资产 | 分数 | 相对 BTC 强弱 | 成交量 | 风险 | 建议权重 |
|---|---:|---:|---:|---:|---:|
| BTC | 0.70 | 基准 | 正常 | 中 | 25% |

## 4. 风控

当前模拟仓位：  
最大回撤：  
是否触发风控：  
是否允许新开仓：  

## 5. 今日结论

今日是否交易：  
原因：  
下一步观察：  
```

---

## 21. 30 天实施日程

### 第 1–3 天：项目初始化

目标：项目能运行，数据库能创建。

任务：

```text
1. 创建 Git 仓库。
2. 创建 Python 虚拟环境。
3. 安装 requirements.txt。
4. 创建目录结构。
5. 写 .env.example 和 .gitignore。
6. 写 init_db.py。
7. 成功创建 DuckDB 数据库。
```

验收标准：

```bash
python -m src.jobs.init_db
```

看到：

```text
Database initialized: data/db/quant_lab.duckdb
```

---

### 第 4–7 天：Crypto 数据闭环

目标：跑通 BTC/ETH 日线数据。

任务：

```text
1. 完成 crypto_prices_ccxt.py。
2. 拉取 BTC/USDT 和 ETH/USDT。
3. 写入 prices_daily。
4. 计算 ret_20d、ret_60d、ma_120、volatility_20d。
5. 判断 BTC risk_regime。
```

验收标准：

```text
1. prices_daily 中有 BTC 和 ETH 数据。
2. 每个资产至少有 365 天数据。
3. 能输出 crypto risk_on / neutral / risk_off。
```

---

### 第 8–10 天：Crypto_Score 和回测

目标：完成 crypto 第一版评分和回测。

任务：

```text
1. 写 price_features.py。
2. 写 relative_strength.py。
3. 写 crypto_scoring.py。
4. 写 crypto_rotation.py。
5. 写 simple_rebalance_backtest.py。
6. 与 BTC buy & hold 对比。
```

验收标准：

```text
输出：
1. 每日 Crypto_Score。
2. 每日目标仓位。
3. 策略净值曲线。
4. 最大回撤。
5. 与 BTC 持有策略对比结果。
```

---

### 第 11–14 天：AI 市场数据闭环

目标：跑通 AI 市场候选资产行情。

任务：

```text
1. 完成 ai_market_prices.py。
2. 确定 5–20 个 AI/科技主题 ETF 或观察标的。
3. 拉取历史日线。
4. 计算价格特征。
5. 完成 AI 市场风险状态判断。
```

验收标准：

```text
1. prices_daily 中有 AI 市场资产数据。
2. 每个资产有 2 年以上历史数据。
3. 能输出 AI market risk_on / neutral / risk_off。
```

---

### 第 15–18 天：AI_Market_Score 和回测

目标：完成 AI 市场第一版评分和周频轮动。

任务：

```text
1. 写 ai_market_scoring.py。
2. 写 ai_rotation.py。
3. 写 AI 市场回测。
4. 与宽基指数、科技主题基准对比。
5. 加入交易成本。
```

验收标准：

```text
输出：
1. AI_Market_Score。
2. 每周目标仓位。
3. 策略净值。
4. 最大回撤。
5. 与基准对比结果。
```

---

### 第 19–22 天：GitHub + Hugging Face 热度

目标：加入 AI 技术趋势数据。

任务：

```text
1. 写 github_collector.py。
2. 写 huggingface_collector.py。
3. 建立 AI 技术主题分类。
4. 计算 GitHub stars_delta_7d。
5. 计算 HF downloads_delta_7d。
6. 合并到 open_source_heat。
```

验收标准：

```text
每日能回答：
1. 哪些 AI 技术方向热度上升？
2. 哪些 GitHub repo 增长最快？
3. 哪些 Hugging Face 模型下载增长最快？
4. 这些技术方向对应哪些 AI 市场主题？
```

---

### 第 23–25 天：Dashboard

目标：完成可视化面板。

任务：

```text
1. 写 Streamlit 首页。
2. 显示今日信号。
3. 显示 AI 市场评分表。
4. 显示 Crypto 评分表。
5. 显示组合净值。
6. 显示风险警报。
```

验收标准：

```bash
streamlit run src/dashboard/app.py
```

浏览器能看到：

```text
1. 今日信号
2. AI 市场评分
3. Crypto 评分
4. 风险状态
5. 回测净值曲线
```

---

### 第 26–28 天：Dry-run 和手工模拟

目标：进入模拟交易阶段。

任务：

```text
1. 配置 Freqtrade dry-run。
2. Crypto 运行 dry-run。
3. AI 市场生成人工订单表。
4. 每日保存交易日志。
5. 检查是否超仓位。
```

验收标准：

```text
连续运行 3 天：
1. 不重复下单。
2. 不超仓位。
3. 不买排除资产。
4. 每个信号都有原因。
```

---

### 第 29–30 天：复盘和 v0.2 规划

目标：形成 v0.1 复盘报告。

任务：

```text
1. 检查数据缺失。
2. 检查是否有前视偏差。
3. 检查交易成本影响。
4. 检查策略换手率。
5. 检查回撤是否可接受。
6. 规划 v0.2。
```

验收标准：

```text
输出 v0.1 复盘报告：
1. 哪些模块已经稳定。
2. 哪些数据质量差。
3. 哪些因子有效。
4. 哪些规则要删除。
5. v0.2 要加入哪些功能。
```

---

## 22. v0.2 规划

v0.1 跑通后，v0.2 再加入：

```text
1. CoinGecko 分类和市值数据。
2. DefiLlama TVL、收入、费用数据。
3. Dune 链上 SQL 查询。
4. 新闻情绪分析。
5. FinBERT 金融文本情绪。
6. LLM 公告和新闻结构化抽取。
7. LightGBM 排序模型。
8. 更完整的样本外验证。
9. 更严格的交易成本和滑点模拟。
10. API 风控和一键停止机制。
```

---

## 23. 关键风控清单

### 23.1 策略风控

```text
1. 最大账户回撤达到 -5%：预警。
2. 最大账户回撤达到 -8%：降仓。
3. 最大账户回撤达到 -12%：停止策略。
4. 单个 crypto 非 BTC/ETH 仓位不超过 8%。
5. AI 市场单个标的不超过 25%。
6. Crypto 总仓位不超过 60%。
7. AI 市场总仓位不超过 80%。
```

### 23.2 API 风控

```text
1. v0.1 不使用真实交易 API。
2. 后期接 API 时禁止提现权限。
3. API key 限制 IP。
4. 使用子账户。
5. 交易日志本地保存。
6. 每日核对交易所余额和本地账本。
7. 必须有一键停止脚本。
```

### 23.3 数据风控

```text
1. 不允许用未来数据。
2. 调仓信号必须使用上一交易日或更早数据。
3. 回测必须扣手续费。
4. Crypto 回测必须考虑滑点。
5. 缺失数据不得自动填成 0。
6. 数据源异常时不生成交易信号。
```

---

## 24. 最小验收标准

项目 v0.1 完成的最低标准：

```text
1. 能自动拉取 BTC/ETH 日线数据。
2. 能自动拉取 AI 市场候选资产日线数据。
3. 能计算价格动量、波动率、均线、相对强弱。
4. 能判断 Crypto 风险状态。
5. 能判断 AI 市场风险状态。
6. 能计算 Crypto_Score。
7. 能计算 AI_Market_Score。
8. 能生成目标仓位。
9. 能完成简化回测。
10. 能显示 Streamlit 仪表盘。
11. 能生成每日 Markdown 报告。
12. 能连续运行 30 天。
```

---

## 25. 立即开工命令清单

```bash
# 1. 创建项目
mkdir ai_crypto_quant_lab
cd ai_crypto_quant_lab

# 2. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 3. 安装依赖
pip install --upgrade pip
pip install pandas polars duckdb numpy scipy scikit-learn pyyaml requests httpx akshare ccxt vectorbt streamlit plotly huggingface_hub PyGithub apscheduler python-dotenv

# 4. 创建目录
mkdir -p configs data/raw data/processed data/reports data/db
mkdir -p src/common src/data_ingestion src/features src/strategies src/backtest src/execution src/dashboard src/jobs
mkdir -p notebooks tests

# 5. 初始化数据库
python -m src.jobs.init_db

# 6. 拉取 crypto 数据
python -m src.data_ingestion.crypto_prices_ccxt

# 7. 启动 dashboard
streamlit run src/dashboard/app.py
```

---

## 26. 项目最终交付物

v0.1 最终应该交付以下内容：

```text
1. GitHub 项目仓库。
2. 完整项目目录。
3. DuckDB 本地数据库。
4. Crypto 数据采集模块。
5. AI 市场数据采集模块。
6. GitHub/Hugging Face 热度采集模块。
7. 因子计算模块。
8. 评分模块。
9. 回测模块。
10. 风控模块。
11. Streamlit 仪表盘。
12. 每日报告模板。
13. v0.1 复盘报告。
```

---

## 27. 推荐开发顺序

最推荐的实际开发顺序是：

```text
1. 先做 Crypto BTC/ETH 数据。
2. 再做 Crypto_Score。
3. 再做 Crypto 回测。
4. 再做 AI 市场行情。
5. 再做 AI_Market_Score。
6. 再接 GitHub 和 Hugging Face。
7. 再做 Dashboard。
8. 再做 Freqtrade dry-run。
9. 最后再考虑小资金验证。
```

原因：

```text
Crypto 行情数据最容易拉，最快能验证系统骨架。
AI 市场数据和主题映射更复杂，适合第二步加入。
GitHub/Hugging Face 是差异化优势，但不应该成为第一天的阻塞点。
```

---

## 28. 参考资料

1. Freqtrade 官方文档：https://www.freqtrade.io/en/stable/
2. Freqtrade 配置文档：https://www.freqtrade.io/en/stable/configuration/
3. Freqtrade 回测文档：https://www.freqtrade.io/en/stable/backtesting/
4. CCXT 官方仓库：https://github.com/ccxt/ccxt
5. CCXT 官方文档：https://docs.ccxt.com/
6. AKShare 官方文档：https://akshare.akfamily.xyz/
7. AKShare GitHub：https://github.com/akfamily/akshare
8. Hugging Face Hub Python Client：https://huggingface.co/docs/huggingface_hub/index
9. GitHub REST API 文档：https://docs.github.com/en/rest
10. Streamlit 官方文档：https://docs.streamlit.io/
11. DuckDB 官方文档：https://duckdb.org/docs/
12. vectorbt 官方文档：https://vectorbt.dev/
