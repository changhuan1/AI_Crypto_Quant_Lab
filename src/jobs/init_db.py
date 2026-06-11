from pathlib import Path

import duckdb


DB_PATH = Path("data/db/quant_lab.duckdb")

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

CREATE TABLE IF NOT EXISTS strategies (
    strategy_id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    asset_class TEXT,
    market TEXT,
    template_id TEXT,
    config_json TEXT,
    status TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS strategy_runs (
    run_id TEXT PRIMARY KEY,
    strategy_id TEXT,
    strategy_name TEXT,
    run_type TEXT,
    status TEXT,
    start_date DATE,
    end_date DATE,
    initial_cash DOUBLE,
    config_json TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS strategy_run_metrics (
    run_id TEXT,
    metric_name TEXT,
    metric_value DOUBLE,
    created_at TIMESTAMP,
    PRIMARY KEY(run_id, metric_name)
);

CREATE TABLE IF NOT EXISTS backtest_nav (
    run_id TEXT,
    date DATE,
    strategy_id TEXT,
    nav DOUBLE,
    cash DOUBLE,
    gross_exposure DOUBLE,
    drawdown DOUBLE,
    benchmark_nav DOUBLE,
    created_at TIMESTAMP,
    PRIMARY KEY(run_id, date)
);

CREATE TABLE IF NOT EXISTS positions_daily (
    run_id TEXT,
    date DATE,
    strategy_id TEXT,
    asset_id TEXT,
    quantity DOUBLE,
    close_price DOUBLE,
    market_value DOUBLE,
    weight DOUBLE,
    created_at TIMESTAMP,
    PRIMARY KEY(run_id, date, asset_id)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    run_id TEXT,
    strategy_id TEXT,
    date DATE,
    asset_id TEXT,
    side TEXT,
    quantity DOUBLE,
    price DOUBLE,
    notional DOUBLE,
    target_weight DOUBLE,
    reason TEXT,
    status TEXT,
    created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trades (
    trade_id TEXT PRIMARY KEY,
    order_id TEXT,
    run_id TEXT,
    strategy_id TEXT,
    date DATE,
    asset_id TEXT,
    side TEXT,
    quantity DOUBLE,
    price DOUBLE,
    notional DOUBLE,
    fee DOUBLE,
    created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS risk_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT,
    strategy_id TEXT,
    date DATE,
    severity TEXT,
    rule_name TEXT,
    message TEXT,
    created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_runs (
    job_run_id TEXT PRIMARY KEY,
    job_name TEXT,
    status TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    duration_seconds DOUBLE,
    message TEXT
);
"""


def init_database(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.execute(DDL)


def main() -> None:
    init_database()
    print(f"Database initialized: {DB_PATH}")


if __name__ == "__main__":
    main()
