# Quant Platform

Quant Platform is a local quant research and strategy-hosting platform inspired by JoinQuant.

The project direction is now fixed:

- Users should interact with strategies through a web platform.
- Data ingestion, cleaning, feature calculation, backtesting, ledger generation, and risk checks belong to the platform backend.
- Strategy users should not need to read database tables or run many scripts by hand.
- The first supported market is Shanghai Composite constituents, with crypto kept as an extension area.

## Version

Current version: `v1.0.0`

This is a local single-user platform release. It is not yet a commercial multi-user production system, but the core direction and architecture are now platform-based rather than script-based.

## What v1.0.0 Includes

- Platform core package: `src/platform`
- Strategy object and strategy template registry
- Built-in strategy: Shanghai Composite constituent momentum rotation
- Unified data access layer: `DataPortal`
- One-click backtest service
- Backtest run records
- Backtest NAV table
- Daily positions
- Orders
- Trades
- Strategy metrics
- FastAPI platform API
- React/Vite platform frontend

The React frontend now includes:

- Overview
- Data Center
- Strategy Center
- Backtest Workbench
- Performance Analysis
- Risk and Paper Trading

## Quick Start

Start the Python API:

```powershell
conda activate ai_crypto_quant_lab
python -m src.jobs.init_db
python -m uvicorn src.platform_api.app:app --host 127.0.0.1 --port 8000
```

Start the React frontend in another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

The old Streamlit dashboard is still kept as a legacy prototype, but the main frontend direction is now React + FastAPI.

## Prepare A-Share Data

For a quick smoke test:

```powershell
python -m src.data_ingestion.a_share_market_prices --limit 50
python -m src.jobs.a_share_market_update
python -m src.jobs.a_share_breadth_update
```

For the full Shanghai Composite constituent universe:

```powershell
python -m src.data_ingestion.a_share_market_prices
python -m src.jobs.a_share_market_update
python -m src.jobs.a_share_breadth_update
```

Full ingestion can take a long time because the Shanghai Composite has many constituents and the data source can be unstable.

## Main User Flow

```text
Open platform
  -> Data Center: confirm data coverage
  -> Strategy Center: inspect strategy template
  -> Backtest Center: configure and run backtest
  -> Backtest Results: inspect NAV, drawdown, holdings, orders, trades
  -> Paper Trading: inspect latest target weights
  -> Risk Center: inspect risk flags
```

## Project Layout

```text
configs/       YAML configuration for data sources, strategies, and risk rules
data/          Local raw data, reports, and DuckDB files
docs/          Product, platform, and roadmap documents
src/platform/  Platform core: strategy objects, data API, backtest service
src/platform_api/ FastAPI HTTP API for the frontend
frontend/      React/Vite frontend application
src/dashboard/ Legacy Streamlit prototype
src/jobs/      Backend maintenance jobs
src/features/  Feature calculation
src/strategies/Strategy scoring and target generation logic
src/backtest/  Legacy and reusable backtest utilities
tests/         Test suite
```

## Current Boundaries

v1.0.0 does not include:

- Real-money live trading
- Broker API integration
- Multi-user login
- Strategy code sandboxing
- Distributed task queues
- High-frequency trading
- Futures, options, or leveraged derivatives

These are planned for later versions after the local single-user platform is stable.

## Documentation

- [Platform Requirements](docs/QUANT_PLATFORM_REQUIREMENTS.md)
- [Research Roadmap](docs/QUANT_PLATFORM_RESEARCH_ROADMAP.md)
- [A-Share Market Plan](docs/A_SHARE_MARKET_PLAN.md)
