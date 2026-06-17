export type Overview = {
  strategy_count: number;
  a_share_asset_count: number;
  latest_price_date: string | null;
  successful_backtests: number;
  coverage: CoverageRow[];
  latest_run: RunRow | null;
};

export type CoverageRow = {
  asset_group: string;
  asset_count: number;
  row_count: number;
  start_date: string | null;
  end_date: string | null;
};

export type DataQualityRow = {
  report_id: string;
  check_name: string;
  severity: "error" | "warning" | "pass" | "info";
  asset_group: string;
  asset_id: string | null;
  date: string | null;
  metric_name: string;
  metric_value: number;
  message: string;
  created_at: string;
};

export type DataCatalogRow = {
  dataset: string;
  label: string;
  description: string;
  row_count: number;
};

export type DataPreview = {
  dataset: string;
  label: string;
  description: string;
  row_count: number;
  limit: number;
  columns: string[];
  rows: Record<string, unknown>[];
};

export type AShareDataPullPayload = {
  start_date: string;
  end_date: string;
  limit: number | null;
};

export type DataPullStatus = {
  job_id: string | null;
  status: "idle" | "running" | "success" | "failed";
  dataset: string;
  start_date: string | null;
  end_date: string | null;
  limit: number | null;
  started_at: string | null;
  finished_at: string | null;
  return_code: number | null;
  message: string;
  log: string;
};

export type FactorIcRow = {
  factor_name: string;
  horizon: number;
  ic_mean: number;
  rank_ic_mean: number;
  ic_win_rate: number;
  rank_ic_win_rate: number;
  observations: number;
  avg_asset_count: number;
};

export type StrategyRow = {
  strategy_id: string;
  name: string;
  description: string;
  asset_class: string;
  market: string;
  template_id: string;
  status: string;
  config_json: string;
  created_at: string;
  updated_at: string;
};

export type RunRow = {
  run_id: string;
  strategy_id: string;
  strategy_name: string;
  run_type: string;
  status: string;
  start_date: string | null;
  end_date: string | null;
  initial_cash: number;
  started_at: string;
  finished_at: string;
  error_message: string | null;
};

export type MetricRow = {
  metric_name: string;
  metric_value: number;
};

export type NavRow = {
  date: string;
  nav: number;
  benchmark_nav: number | null;
  cash: number;
  gross_exposure: number;
  drawdown: number;
};

export type PositionRow = {
  date: string;
  asset_id: string;
  asset_code: string;
  asset_name: string;
  quantity: number;
  close_price: number;
  market_value: number;
  weight: number;
};

export type OrderRow = {
  date: string;
  asset_id: string;
  asset_code: string;
  asset_name: string;
  side: "BUY" | "SELL";
  status: "filled" | "rejected";
  quantity: number;
  price: number;
  notional: number;
  target_weight: number;
  reason: string;
};

export type BacktestPayload = {
  strategy_id: string;
  start_date: string | null;
  end_date: string | null;
  initial_cash: number;
  top_n: number;
  max_single_position: number;
  fee_rate: number;
};

export type BacktestResponse = {
  run_id: string;
  strategy_id: string;
  strategy_name: string;
  status: string;
  metrics: Record<string, number>;
  started_at: string;
  finished_at: string;
};

export type PortfolioPayload = {
  start_date: string;
  end_date: string;
  initial_cash: number;
  universe_limit: number;
  top_n: number;
  lookback_days: number;
  rebalance_days: number;
  max_single_position: number;
  fee_rate: number;
};

export type PortfolioResponse = {
  run_id: string;
  strategy_id: string;
  strategy_name: string;
  status: string;
  data_summary: {
    rows: number;
    asset_count: number;
    start_date: string;
    end_date: string;
    source: string;
  };
  metrics: Record<string, number>;
  nav: NavRow[];
  signals: Array<Record<string, unknown>>;
  orders: Array<Record<string, unknown>>;
  positions: Array<Record<string, unknown>>;
  daily_ledger: Array<Record<string, unknown>>;
};

export type PlatformReadiness = {
  datasets: Array<{
    dataset: string;
    label: string;
    row_count: number;
  }>;
  quality: Array<{
    severity: string;
    count: number;
  }>;
  rules: Array<{
    name: string;
    status: string;
    description: string;
  }>;
};

export type SingleStockPayload = {
  asset_code: string;
  start_date: string;
  end_date: string;
  initial_cash: number;
  strategy_mode: "buy_hold" | "ma_filter" | "custom_code";
  strategy_code?: string | null;
  strategy_script_id?: string | null;
  custom_strategy_name?: string | null;
  target_weight: number;
  ma_short: number;
  ma_long: number;
  fee_rate: number;
};

export type SingleStockStrategyScript = {
  script_id: string;
  name: string;
  code: string;
  created_at: string | null;
  updated_at: string | null;
  is_template?: boolean;
};

export type SingleStockStrategyScriptPayload = {
  script_id?: string | null;
  name: string;
  code: string;
};

export type SingleStockPriceRow = {
  asset_id: string;
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  turnover: number | null;
  source: string | null;
};

export type SingleStockProfile = {
  asset_id: string;
  asset_code: string;
  asset_name: string;
  coverage: {
    rows: number;
    start_date: string | null;
    end_date: string | null;
    source: string | null;
  };
  selected: {
    rows: number;
    start_date: string | null;
    end_date: string | null;
  };
  prices: SingleStockPriceRow[];
  pulled_rows?: number;
  message?: string;
};

export type SingleStockResponse = {
  run_id: string;
  asset_id: string;
  asset_code: string;
  asset_name: string;
  strategy_name: string;
  status: string;
  data_summary: {
    rows: number;
    start_date: string;
    end_date: string;
    source: string;
  };
  metrics: Record<string, number>;
  nav: NavRow[];
  signals: Array<Record<string, unknown>>;
  orders: Array<Record<string, unknown>>;
  positions: Array<Record<string, unknown>>;
  daily_ledger: Array<Record<string, unknown>>;
};
