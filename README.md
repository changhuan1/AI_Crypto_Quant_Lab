# AI Crypto Quant Lab

AI Crypto Quant Lab is a research-first quantitative lab for AI-market and crypto-spot analysis.

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
```

Current status:

- `src.jobs.init_db` initializes the local DuckDB database.
- `src.data_ingestion.crypto_prices_ccxt` collects BTC/USDT and ETH/USDT daily OHLCV data through CCXT. The default exchange is OKX because Binance may rate-limit or block some IPs.
- `src.jobs.crypto_update` calculates first-pass crypto price features and prints the BTC risk regime.
- `src.backtest.backtest_crypto` generates daily crypto rotation signals, runs a simple rebalance backtest, and compares it with BTC buy-and-hold.

The Streamlit dashboard is still reserved for a later milestone.

If DuckDB reports that `data/db/quant_lab.duckdb` is already in use, close any editor tab or database plugin that has opened the file, then rerun the command.

## Documentation

See [docs/AI_Crypto_Quant_Lab_实施方案_v0.1.md](docs/AI_Crypto_Quant_Lab_实施方案_v0.1.md) for the full v0.1 implementation plan.
