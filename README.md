# A-Share Crypto Quant Lab

A-Share Crypto Quant Lab is a research-first quantitative lab for A-share broad-market and crypto-spot analysis.

The v0.1 goal is to build a low-cost, explainable loop:

```text
data ingestion -> features -> scoring -> backtest -> paper trading -> risk control -> dashboard/report
```

## Scope

v0.1 focuses on project scaffolding, reproducible configuration, and a clear implementation roadmap.

This repository does not start with production trading code. Strategy, data, and execution modules should be implemented step by step after the framework is reviewed.

## Boundaries

- No leverage.
- No futures, options, or perpetual contracts.
- No high-frequency trading.
- No automatic live trading.
- No LLM-driven order placement.
- No small-cap meme coins or unclear assets.
- Every signal must be explainable.
- Every strategy must pass backtesting and paper trading before any real-money validation.

## Project Layout

```text
configs/       YAML configuration for assets, data sources, strategies, and risk rules
data/          Local raw data, processed data, reports, and DuckDB files
docs/          Product and technical planning documents
src/           Future Python package modules
notebooks/     Research notebooks
tests/         Future test suite
external/      Optional external tools such as Freqtrade
```

## First Milestone

The first implementation milestone should make these commands possible:

```powershell
conda activate ai_crypto_quant_lab
python -m src.jobs.init_db
python -m src.data_ingestion.crypto_prices_ccxt
python -m src.jobs.crypto_update
python -m src.backtest.backtest_crypto
python -m src.data_ingestion.a_share_market_prices --limit 50
python -m src.jobs.a_share_market_update
python -m src.jobs.a_share_breadth_update
python -m src.backtest.backtest_a_share_market
streamlit run src/dashboard/app.py
```

Current status:

- `src.jobs.init_db` initializes the local DuckDB database.
- `src.data_ingestion.crypto_prices_ccxt` collects BTC/USDT and ETH/USDT daily OHLCV data through CCXT. The default exchange is OKX because Binance may rate-limit or block some IPs.
- `src.jobs.crypto_update` calculates first-pass crypto price features and prints the BTC risk regime.
- `src.backtest.backtest_crypto` generates daily crypto rotation signals, runs a simple rebalance backtest, and compares it with BTC buy-and-hold.
- `src.data_ingestion.a_share_market_prices` collects Shanghai Composite constituents through AKShare. Use `--limit 50` for a small smoke test, or omit it for the full constituent universe.
- `src.jobs.a_share_market_update` calculates first-pass constituent-level price features and prints the A-share market risk regime.
- `src.jobs.a_share_breadth_update` calculates Shanghai Composite constituent breadth, including up/down ratio, above-MA120 ratio, turnover expansion, and a market breadth score.
- `src.backtest.backtest_a_share_market` generates weekly Shanghai Composite constituent stock-selection signals and compares them with the Shanghai Composite index.
- `src.dashboard.app` provides a local Streamlit dashboard for NAV, signals, breadth, and data coverage.

Full Shanghai Composite constituent ingestion can take a long time because it may fetch more than 2,000 stocks. Start with a smoke test, then run the full ingestion when the data source/network is stable:

```powershell
python -m src.data_ingestion.a_share_market_prices --limit 50
python -m src.data_ingestion.a_share_market_prices
```

The A-share stock data collector uses Eastmoney first and falls back to Sina when Eastmoney is blocked or unstable.

The Streamlit dashboard is still reserved for a later milestone.

If DuckDB reports that `data/db/quant_lab.duckdb` is already in use, close any editor tab or database plugin that has opened the file, then rerun the command.

## Documentation

See [docs/A_SHARE_MARKET_PLAN.md](docs/A_SHARE_MARKET_PLAN.md) for the updated A-share market implementation plan. The original AI-market plan is kept in `docs/` as historical context.
