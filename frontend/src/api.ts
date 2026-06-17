import type {
  BacktestPayload,
  BacktestResponse,
  AShareDataPullPayload,
  DataCatalogRow,
  DataPullStatus,
  DataPreview,
  CoverageRow,
  DataQualityRow,
  FactorIcRow,
  MetricRow,
  NavRow,
  OrderRow,
  Overview,
  PlatformReadiness,
  PositionRow,
  PortfolioPayload,
  PortfolioResponse,
  RunRow,
  SingleStockPayload,
  SingleStockProfile,
  SingleStockResponse,
  SingleStockStrategyScript,
  SingleStockStrategyScriptPayload,
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
  dataQuality: () => request<DataQualityRow[]>("/api/data/quality"),
  dataCatalog: () => request<DataCatalogRow[]>("/api/data/catalog"),
  dataPreview: (dataset: string, limit: number) =>
    request<DataPreview>(`/api/data/preview/${dataset}?limit=${limit}`),
  dataPullStatus: () => request<DataPullStatus>("/api/data/pulls/a-share-prices/status"),
  startAShareDataPull: (payload: AShareDataPullPayload) =>
    request<DataPullStatus>("/api/data/pulls/a-share-prices", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  factorIc: () => request<FactorIcRow[]>("/api/research/factor-ic"),
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
    }),
  runPortfolio: (payload: PortfolioPayload) =>
    request<PortfolioResponse>("/api/portfolio/backtests", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  platformReadiness: () => request<PlatformReadiness>("/api/platform/readiness"),
  runSingleStock: (payload: SingleStockPayload) =>
    request<SingleStockResponse>("/api/single-stock/backtests", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  singleStockProfile: (assetCode: string, startDate?: string, endDate?: string, limit = 120) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    return request<SingleStockProfile>(`/api/single-stock/${assetCode}/profile?${params.toString()}`);
  },
  pullSingleStockPrices: (assetCode: string, startDate: string, endDate: string) =>
    request<SingleStockProfile>(`/api/single-stock/${assetCode}/prices/pull`, {
      method: "POST",
      body: JSON.stringify({ start_date: startDate, end_date: endDate })
    }),
  singleStockStrategyScripts: () => request<SingleStockStrategyScript[]>("/api/single-stock/strategy-scripts"),
  saveSingleStockStrategyScript: (payload: SingleStockStrategyScriptPayload) =>
    request<SingleStockStrategyScript>("/api/single-stock/strategy-scripts", {
      method: "POST",
      body: JSON.stringify(payload)
    })
};
