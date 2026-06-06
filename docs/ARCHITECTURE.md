# Architecture

```text
Streamlit dashboard / reports
        ^
Strategy engine
        ^
Feature store
        ^
Market data + alternative data + text data
        ^
DuckDB local research database
        ^
Backtest / dry-run workflow
```

The system is designed as a local research platform first. Live execution is outside the v0.1 scope.
