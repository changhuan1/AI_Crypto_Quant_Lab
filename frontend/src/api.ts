import type {
  BacktestPayload,
  BacktestResponse,
  CoverageRow,
  MetricRow,
  NavRow,
  OrderRow,
  Overview,
  PositionRow,
  RunRow,
  StrategyRow
} from "./types";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  overview: () => request<Overview>("/api/overview"),
  coverage: () => request<CoverageRow[]>("/api/data/coverage"),
  strategies: () => request<StrategyRow[]>("/api/strategies"),
  runs: () => request<RunRow[]>("/api/runs"),
  metrics: (runId: string) => request<MetricRow[]>(`/api/runs/${runId}/metrics`),
  nav: (runId: string) => request<NavRow[]>(`/api/runs/${runId}/nav`),
  positions: (runId: string) => request<PositionRow[]>(`/api/runs/${runId}/positions`),
  orders: (runId: string) => request<OrderRow[]>(`/api/runs/${runId}/orders`),
  runBacktest: (payload: BacktestPayload) =>
    request<BacktestResponse>("/api/backtests", {
      method: "POST",
      body: JSON.stringify(payload)
    })
};
