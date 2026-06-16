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

export type SingleStockPayload = {
  asset_code: string;
  start_date: string;
  end_date: string;
  initial_cash: number;
  strategy_mode: "buy_hold" | "ma_filter";
  target_weight: number;
  ma_short: number;
  ma_long: number;
  fee_rate: number;
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
};
