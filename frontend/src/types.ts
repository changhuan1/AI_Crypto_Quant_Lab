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
  quantity: number;
  close_price: number;
  market_value: number;
  weight: number;
};

export type OrderRow = {
  date: string;
  asset_id: string;
  side: "BUY" | "SELL";
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
