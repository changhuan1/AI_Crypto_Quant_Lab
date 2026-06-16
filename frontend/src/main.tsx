import React, { useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  Activity,
  BarChart3,
  CheckCircle2,
  Database,
  Download,
  Gauge,
  LayoutDashboard,
  LineChart,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  WalletCards
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart as ReLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { api } from "./api";
import type {
  AShareDataPullPayload,
  BacktestPayload,
  CoverageRow,
  DataCatalogRow,
  DataPreview,
  DataPullStatus,
  DataQualityRow,
  FactorIcRow,
  MetricRow,
  NavRow,
  OrderRow,
  Overview,
  PositionRow,
  RunRow,
  SingleStockPayload,
  SingleStockResponse,
  StrategyRow
} from "./types";
import "./styles.css";

type Page = "overview" | "data" | "singleStock" | "strategies" | "backtest" | "results" | "risk";

const pages: Array<{ id: Page; label: string; icon: React.ReactNode }> = [
  { id: "overview", label: "总览", icon: <LayoutDashboard size={18} /> },
  { id: "data", label: "数据中心", icon: <Database size={18} /> },
  { id: "singleStock", label: "单股实验室", icon: <Search size={18} /> },
  { id: "strategies", label: "策略中心", icon: <SlidersHorizontal size={18} /> },
  { id: "backtest", label: "回测工作台", icon: <Play size={18} /> },
  { id: "results", label: "绩效分析", icon: <BarChart3 size={18} /> },
  { id: "risk", label: "风控与模拟", icon: <ShieldCheck size={18} /> }
];

function App() {
  const [page, setPage] = useState<Page>("overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [coverage, setCoverage] = useState<CoverageRow[]>([]);
  const [dataQuality, setDataQuality] = useState<DataQualityRow[]>([]);
  const [dataCatalog, setDataCatalog] = useState<DataCatalogRow[]>([]);
  const [selectedDataset, setSelectedDataset] = useState("prices_daily");
  const [previewLimit, setPreviewLimit] = useState(100);
  const [dataPreview, setDataPreview] = useState<DataPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [dataPull, setDataPull] = useState<DataPullStatus | null>(null);
  const [factorIc, setFactorIc] = useState<FactorIcRow[]>([]);
  const [strategies, setStrategies] = useState<StrategyRow[]>([]);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [metrics, setMetrics] = useState<MetricRow[]>([]);
  const [nav, setNav] = useState<NavRow[]>([]);
  const [positions, setPositions] = useState<PositionRow[]>([]);
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [singleStockResult, setSingleStockResult] = useState<SingleStockResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [apiError, setApiError] = useState<string>("");

  const selectedRun = runs.find((run) => run.run_id === selectedRunId) ?? runs[0];
  const metricMap = useMemo(
    () => Object.fromEntries(metrics.map((metric) => [metric.metric_name, metric.metric_value])),
    [metrics]
  );

  async function loadBaseData() {
    setLoading(true);
    setApiError("");
    try {
      const [overviewData, coverageData, qualityData, catalogData, factorIcData, strategiesData, runsData] = await Promise.all([
        api.overview(),
        api.coverage(),
        api.dataQuality(),
        api.dataCatalog(),
        api.factorIc(),
        api.strategies(),
        api.runs()
      ]);
      setOverview(overviewData);
      setCoverage(coverageData);
      setDataQuality(qualityData);
      setDataCatalog(catalogData);
      setFactorIc(factorIcData);
      setStrategies(strategiesData);
      setRuns(runsData);
      const firstRun = runsData.find((run) => run.status === "success");
      if (firstRun && !selectedRunId) {
        setSelectedRunId(firstRun.run_id);
      }
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API 连接失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadRunDetails(runId: string) {
    if (!runId) return;
    try {
      const [metricRows, navRows, positionRows, orderRows] = await Promise.all([
        api.metrics(runId),
        api.nav(runId),
        api.positions(runId),
        api.orders(runId)
      ]);
      setMetrics(metricRows);
      setNav(navRows);
      setPositions(positionRows);
      setOrders(orderRows);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "回测结果读取失败");
    }
  }

  async function loadDataPreview(dataset = selectedDataset, limit = previewLimit) {
    setPreviewLoading(true);
    try {
      const preview = await api.dataPreview(dataset, limit);
      setDataPreview(preview);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "数据预览读取失败");
    } finally {
      setPreviewLoading(false);
    }
  }

  async function loadDataPullStatus(refreshAfterFinish = false) {
    try {
      const status = await api.dataPullStatus();
      setDataPull(status);
      if (refreshAfterFinish && status.status !== "running") {
        await Promise.all([loadBaseData(), loadDataPreview()]);
      }
      return status;
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "数据拉取状态读取失败");
      return null;
    }
  }

  async function handleStartDataPull(payload: AShareDataPullPayload) {
    setApiError("");
    try {
      const status = await api.startAShareDataPull(payload);
      setDataPull(status);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "数据拉取任务启动失败");
    }
  }

  useEffect(() => {
    loadBaseData();
    loadDataPullStatus();
  }, []);

  useEffect(() => {
    if (page === "data") {
      loadDataPreview(selectedDataset, previewLimit);
    }
  }, [page, selectedDataset, previewLimit]);

  useEffect(() => {
    if (page !== "data" || dataPull?.status !== "running") return;
    const timer = window.setInterval(() => loadDataPullStatus(true), 2000);
    return () => window.clearInterval(timer);
  }, [page, dataPull?.status]);

  useEffect(() => {
    const runId = selectedRunId || runs.find((run) => run.status === "success")?.run_id || "";
    if (runId) {
      loadRunDetails(runId);
    }
  }, [selectedRunId, runs.length]);

  async function handleRunBacktest(payload: BacktestPayload) {
    setLoading(true);
    setApiError("");
    try {
      const result = await api.runBacktest(payload);
      await loadBaseData();
      setSelectedRunId(result.run_id);
      setPage("results");
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "回测失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleRunSingleStock(payload: SingleStockPayload) {
    setLoading(true);
    setApiError("");
    try {
      const result = await api.runSingleStock(payload);
      setSingleStockResult(result);
      await loadBaseData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "单股流程运行失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <LineChart size={24} />
          </div>
          <div>
            <strong>Quant Platform</strong>
            <span>v1.0.0</span>
          </div>
        </div>
        <nav className="nav-list" aria-label="平台导航">
          {pages.map((item) => (
            <button
              key={item.id}
              className={item.id === page ? "nav-item active" : "nav-item"}
              onClick={() => setPage(item.id)}
              title={item.label}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-status">
          <span className="status-dot" />
          <div>
            <strong>本地平台模式</strong>
            <small>FastAPI + React + DuckDB</small>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">A股策略托管平台</p>
            <h1>{pageTitle(page)}</h1>
          </div>
          <div className="top-actions">
            <button className="icon-button" onClick={loadBaseData} title="刷新平台数据">
              <RefreshCw size={18} />
            </button>
            <div className="run-chip">
              <Activity size={16} />
              {selectedRun ? selectedRun.status : "no run"}
            </div>
          </div>
        </header>

        {apiError && <div className="error-banner">{apiError}</div>}
        {loading && <div className="loading-bar" />}

        {page === "overview" && (
          <OverviewPage overview={overview} nav={nav} runs={runs} metricMap={metricMap} />
        )}
        {page === "data" && (
          <DataPage
            coverage={coverage}
            dataQuality={dataQuality}
            dataCatalog={dataCatalog}
            selectedDataset={selectedDataset}
            setSelectedDataset={setSelectedDataset}
            previewLimit={previewLimit}
            setPreviewLimit={setPreviewLimit}
            dataPreview={dataPreview}
            previewLoading={previewLoading}
            dataPull={dataPull}
            onStartDataPull={handleStartDataPull}
            onRefreshPreview={() => loadDataPreview()}
          />
        )}
        {page === "singleStock" && (
          <SingleStockPage
            result={singleStockResult}
            onRun={handleRunSingleStock}
            disabled={loading}
          />
        )}
        {page === "strategies" && <StrategyPage strategies={strategies} factorIc={factorIc} />}
        {page === "backtest" && (
          <BacktestPage
            strategies={strategies}
            coverage={coverage}
            onRun={handleRunBacktest}
            disabled={loading}
          />
        )}
        {page === "results" && (
          <ResultsPage
            runs={runs}
            selectedRunId={selectedRunId}
            setSelectedRunId={setSelectedRunId}
            metricMap={metricMap}
            nav={nav}
            positions={positions}
            orders={orders}
          />
        )}
        {page === "risk" && (
          <RiskPage selectedRun={selectedRun} positions={positions} orders={orders} metricMap={metricMap} />
        )}
      </main>
    </div>
  );
}

function OverviewPage({
  overview,
  nav,
  runs,
  metricMap
}: {
  overview: Overview | null;
  nav: NavRow[];
  runs: RunRow[];
  metricMap: Record<string, number>;
}) {
  return (
    <section className="page-grid">
      <div className="metric-row">
        <MetricCard label="策略数量" value={overview?.strategy_count ?? 0} icon={<SlidersHorizontal />} />
        <MetricCard label="A股股票数" value={overview?.a_share_asset_count ?? 0} icon={<Database />} />
        <MetricCard
          label="最新行情日"
          value={cleanDate(overview?.latest_price_date) || "-"}
          icon={<CheckCircle2 />}
        />
        <MetricCard label="成功回测" value={overview?.successful_backtests ?? 0} icon={<Gauge />} />
      </div>

      <div className="panel panel-wide">
        <PanelHeader title="净值走势" action={formatPct(metricMap.total_return)} />
        <NavChart nav={nav} />
      </div>

      <div className="panel">
        <PanelHeader title="策略表现" />
        <div className="kpi-stack">
          <KpiLine label="年化收益" value={formatPct(metricMap.annual_return)} />
          <KpiLine label="最大回撤" value={formatPct(metricMap.max_drawdown)} intent="danger" />
          <KpiLine label="夏普比率" value={formatNumber(metricMap.sharpe)} />
          <KpiLine label="基准总收益" value={formatPct(metricMap.benchmark_total_return)} />
        </div>
      </div>

      <div className="panel">
        <PanelHeader title="最近运行" />
        <CompactRuns runs={runs} />
      </div>
    </section>
  );
}

function DataPage({
  coverage,
  dataQuality,
  dataCatalog,
  selectedDataset,
  setSelectedDataset,
  previewLimit,
  setPreviewLimit,
  dataPreview,
  previewLoading,
  dataPull,
  onStartDataPull,
  onRefreshPreview
}: {
  coverage: CoverageRow[];
  dataQuality: DataQualityRow[];
  dataCatalog: DataCatalogRow[];
  selectedDataset: string;
  setSelectedDataset: (dataset: string) => void;
  previewLimit: number;
  setPreviewLimit: (limit: number) => void;
  dataPreview: DataPreview | null;
  previewLoading: boolean;
  dataPull: DataPullStatus | null;
  onStartDataPull: (payload: AShareDataPullPayload) => void;
  onRefreshPreview: () => void;
}) {
  const [pullStartDate, setPullStartDate] = useState("2024-01-01");
  const [pullEndDate, setPullEndDate] = useState(new Date().toISOString().slice(0, 10));
  const [pullLimit, setPullLimit] = useState("20");
  const selectedMeta = dataCatalog.find((row) => row.dataset === selectedDataset);
  const previewRows =
    dataPreview?.rows.map((row) => dataPreview.columns.map((column) => formatCell(row[column]))) ?? [];

  return (
    <section className="page-grid single">
      <div className="panel">
        <PanelHeader
          title="A股行情拉取"
          action={
            <span className={`pull-status ${dataPull?.status ?? "idle"}`}>
              {dataPullStatusLabel(dataPull?.status)}
            </span>
          }
        />
        <div className="data-pull-form">
          <label>
            开始日期
            <input
              type="date"
              value={pullStartDate}
              onChange={(event) => setPullStartDate(event.target.value)}
              disabled={dataPull?.status === "running"}
            />
          </label>
          <label>
            结束日期
            <input
              type="date"
              value={pullEndDate}
              onChange={(event) => setPullEndDate(event.target.value)}
              disabled={dataPull?.status === "running"}
            />
          </label>
          <label>
            股票数量
            <input
              type="number"
              min="1"
              max="6000"
              placeholder="留空表示全部"
              value={pullLimit}
              onChange={(event) => setPullLimit(event.target.value)}
              disabled={dataPull?.status === "running"}
            />
          </label>
          <button
            className="primary-button"
            disabled={dataPull?.status === "running" || !pullStartDate || !pullEndDate}
            onClick={() =>
              onStartDataPull({
                start_date: pullStartDate,
                end_date: pullEndDate,
                limit: pullLimit ? Number(pullLimit) : null
              })
            }
          >
            <Download size={18} />
            {dataPull?.status === "running" ? "正在拉取" : "开始拉取"}
          </button>
        </div>
        <div className="pull-guidance">
          <span>数量留空会拉取当前上证指数全部成分股；数量越多，运行时间越长。</span>
          {dataPull?.message && <strong>{dataPull.message}</strong>}
        </div>
        {dataPull?.job_id && (
          <div className="pull-details">
            <span>任务：{dataPull.job_id}</span>
            <span>范围：{dataPull.start_date} 至 {dataPull.end_date}</span>
            <span>数量：{dataPull.limit ?? "全部成分股"}</span>
          </div>
        )}
        {dataPull?.log && <pre className="pull-log">{dataPull.log}</pre>}
      </div>
      <div className="panel">
        <PanelHeader
          title="数据浏览器"
          action={
            dataPreview
              ? `展示 ${dataPreview.rows.length.toLocaleString()} / ${dataPreview.row_count.toLocaleString()} 行`
              : "未加载"
          }
        />
        <div className="data-browser-toolbar">
          <label>
            数据集
            <select
              value={selectedDataset}
              onChange={(event) => setSelectedDataset(event.target.value)}
            >
              {dataCatalog.map((row) => (
                <option value={row.dataset} key={row.dataset}>
                  {row.label}（{row.row_count.toLocaleString()} 行）
                </option>
              ))}
            </select>
          </label>
          <label>
            展示行数
            <select
              value={previewLimit}
              onChange={(event) => setPreviewLimit(Number(event.target.value))}
            >
              {[50, 100, 200, 500].map((limit) => (
                <option value={limit} key={limit}>
                  前 {limit} 行
                </option>
              ))}
            </select>
          </label>
          <button className="secondary-button" onClick={onRefreshPreview} disabled={previewLoading}>
            <RefreshCw size={16} />
            {previewLoading ? "读取中" : "刷新预览"}
          </button>
        </div>
        <div className="dataset-summary">
          <div>
            <strong>{dataPreview?.label ?? selectedMeta?.label ?? selectedDataset}</strong>
            <span>{dataPreview?.description ?? selectedMeta?.description ?? "选择一个数据集查看表格预览"}</span>
          </div>
          <div>
            <strong>{(dataPreview?.row_count ?? selectedMeta?.row_count ?? 0).toLocaleString()}</strong>
            <span>总行数</span>
          </div>
        </div>
        {previewLoading ? (
          <div className="empty-state">正在读取数据预览</div>
        ) : dataPreview ? (
          <DataTable columns={dataPreview.columns} rows={previewRows} />
        ) : (
          <div className="empty-state">暂无数据预览</div>
        )}
      </div>
      <div className="panel">
        <PanelHeader title="数据覆盖" action={`${coverage.length} 组`} />
        <DataTable
          columns={["数据组", "资产数", "行数", "开始日期", "结束日期"]}
          rows={coverage.map((row) => [
            row.asset_group,
            row.asset_count.toLocaleString(),
            row.row_count.toLocaleString(),
            cleanDate(row.start_date),
            cleanDate(row.end_date)
          ])}
        />
      </div>
      <div className="panel">
        <PanelHeader title="数据质量与可信度" action={`${dataQuality.length} 项`} />
        <DataTable
          columns={["等级", "检查项", "资产组", "指标", "说明"]}
          rows={dataQuality.map((row) => [
            <span className={`severity ${row.severity}`} key={`${row.report_id}-severity`}>
              {row.severity}
            </span>,
            row.check_name,
            row.asset_group,
            `${row.metric_name}: ${formatNumber(row.metric_value)}`,
            row.message
          ])}
        />
      </div>
      <div className="command-panel">
        <strong>后台数据准备</strong>
        <code>python -m src.jobs.init_db</code>
        <code>python -m src.data_ingestion.a_share_market_prices --limit 50</code>
        <code>python -m src.jobs.a_share_market_update</code>
        <code>python -m src.jobs.a_share_breadth_update</code>
        <code>python -m src.jobs.data_quality_update</code>
        <code>python -m src.jobs.factor_research_update</code>
      </div>
    </section>
  );
}

function SingleStockPage({
  result,
  onRun,
  disabled
}: {
  result: SingleStockResponse | null;
  onRun: (payload: SingleStockPayload) => void;
  disabled: boolean;
}) {
  const [payload, setPayload] = useState<SingleStockPayload>({
    asset_code: "600000",
    start_date: "2026-06-01",
    end_date: "2026-06-05",
    initial_cash: 100000,
    strategy_mode: "buy_hold",
    target_weight: 0.95,
    ma_short: 5,
    ma_long: 20,
    fee_rate: 0.001
  });
  const metricMap = result?.metrics ?? {};

  return (
    <section className="page-grid single">
      <div className="panel">
        <PanelHeader title="单股完整流程" action={result?.run_id ?? "未运行"} />
        <div className="single-stock-layout">
          <div className="single-stock-form">
            <label>
              股票代码
              <input
                value={payload.asset_code}
                onChange={(event) => setPayload({ ...payload, asset_code: event.target.value })}
                placeholder="例如 600000"
              />
            </label>
            <label>
              策略模式
              <select
                value={payload.strategy_mode}
                onChange={(event) =>
                  setPayload({ ...payload, strategy_mode: event.target.value as SingleStockPayload["strategy_mode"] })
                }
              >
                <option value="buy_hold">买入并持有</option>
                <option value="ma_filter">均线过滤持有</option>
              </select>
            </label>
            <div className="form-row">
              <label>
                开始日期
                <input
                  type="date"
                  value={payload.start_date}
                  onChange={(event) => setPayload({ ...payload, start_date: event.target.value })}
                />
              </label>
              <label>
                结束日期
                <input
                  type="date"
                  value={payload.end_date}
                  onChange={(event) => setPayload({ ...payload, end_date: event.target.value })}
                />
              </label>
            </div>
            <div className="form-row">
              <label>
                初始资金
                <input
                  type="number"
                  value={payload.initial_cash}
                  onChange={(event) => setPayload({ ...payload, initial_cash: Number(event.target.value) })}
                />
              </label>
              <label>
                目标仓位
                <input
                  type="number"
                  min="0.01"
                  max="1"
                  step="0.05"
                  value={payload.target_weight}
                  onChange={(event) => setPayload({ ...payload, target_weight: Number(event.target.value) })}
                />
              </label>
            </div>
            <div className="form-row">
              <label>
                短均线
                <input
                  type="number"
                  value={payload.ma_short}
                  onChange={(event) => setPayload({ ...payload, ma_short: Number(event.target.value) })}
                  disabled={payload.strategy_mode !== "ma_filter"}
                />
              </label>
              <label>
                长均线
                <input
                  type="number"
                  value={payload.ma_long}
                  onChange={(event) => setPayload({ ...payload, ma_long: Number(event.target.value) })}
                  disabled={payload.strategy_mode !== "ma_filter"}
                />
              </label>
            </div>
            <label>
              交易费率
              <input
                type="number"
                step="0.0005"
                value={payload.fee_rate}
                onChange={(event) => setPayload({ ...payload, fee_rate: Number(event.target.value) })}
              />
            </label>
            <button
              className="primary-button"
              disabled={disabled || !payload.asset_code || !payload.start_date || !payload.end_date}
              onClick={() => onRun(payload)}
            >
              <Play size={18} />
              运行单股流程
            </button>
          </div>
          <div className="preview-ladder">
            {["读取单股行情", "生成单股信号", "按 T+1 撮合", "保存回测账本", "展示净值与订单"].map(
              (step, index) => (
                <div key={step}>
                  <span>{index + 1}</span>
                  <strong>{step}</strong>
                </div>
              )
            )}
          </div>
        </div>
      </div>

      {result && (
        <>
          <div className="metric-row compact">
            <MetricCard label="股票" value={`${result.asset_code} ${result.asset_name}`} icon={<Search />} />
            <MetricCard label="行情行数" value={result.data_summary.rows.toLocaleString()} icon={<Database />} />
            <MetricCard label="总收益" value={formatPct(metricMap.total_return)} icon={<BarChart3 />} />
            <MetricCard label="最大回撤" value={formatPct(metricMap.max_drawdown)} icon={<Gauge />} />
          </div>

          <div className="panel">
            <PanelHeader
              title="单股净值"
              action={`${cleanDate(result.data_summary.start_date)} 至 ${cleanDate(result.data_summary.end_date)}`}
            />
            <NavChart nav={result.nav} />
          </div>

          <div className="table-grid">
            <div className="panel">
              <PanelHeader title="最近信号" action={`${result.signals.length} 条`} />
              <DataTable
                columns={["日期", "信号", "目标仓位", "评分", "原因"]}
                rows={result.signals.slice(-20).reverse().map((row) => [
                  cleanDate(String(row.date ?? "")),
                  String(row.signal ?? ""),
                  formatPct(Number(row.target_weight ?? 0)),
                  formatNumber(Number(row.score ?? 0)),
                  String(row.reason ?? "")
                ])}
              />
            </div>
            <div className="panel">
              <PanelHeader title="订单明细" action={`${result.orders.length} 条`} />
              <DataTable
                columns={["日期", "状态", "方向", "代码", "名称", "数量", "价格", "金额", "原因"]}
                rows={result.orders.slice(-20).reverse().map((row) => [
                  cleanDate(String(row.date ?? "")),
                  String(row.status ?? ""),
                  String(row.side ?? ""),
                  String(row.asset_code ?? result.asset_code),
                  String(row.asset_name ?? result.asset_name),
                  formatNumber(Number(row.quantity ?? 0)),
                  formatNumber(Number(row.price ?? 0)),
                  formatMoney(Number(row.notional ?? 0)),
                  String(row.reason ?? "")
                ])}
              />
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function StrategyPage({
  strategies,
  factorIc
}: {
  strategies: StrategyRow[];
  factorIc: FactorIcRow[];
}) {
  return (
    <section className="page-grid single">
      <div className="strategy-grid">
        {strategies.map((strategy) => (
          <article className="strategy-card" key={strategy.strategy_id}>
            <div className="strategy-card-head">
              <div>
                <span className="tag">{strategy.market}</span>
                <h2>{strategy.name}</h2>
              </div>
              <span className="status-pill">{strategy.status}</span>
            </div>
            <p>{strategy.description}</p>
            <div className="config-grid">
              {Object.entries(JSON.parse(strategy.config_json)).map(([key, value]) => (
                <div key={key}>
                  <span>{key}</span>
                  <strong>{String(value)}</strong>
                </div>
              ))}
            </div>
          </article>
        ))}
      </div>
      <div className="panel">
        <PanelHeader title="因子 IC 摘要" action={`${factorIc.length} 项`} />
        <DataTable
          columns={["因子", "周期", "IC均值", "Rank IC均值", "IC胜率", "样本期数"]}
          rows={factorIc.map((row) => [
            row.factor_name,
            `${row.horizon}日`,
            formatNumber(row.ic_mean),
            formatNumber(row.rank_ic_mean),
            formatPct(row.ic_win_rate),
            row.observations
          ])}
        />
      </div>
    </section>
  );
}

function BacktestPage({
  strategies,
  coverage,
  onRun,
  disabled
}: {
  strategies: StrategyRow[];
  coverage: CoverageRow[];
  onRun: (payload: BacktestPayload) => void;
  disabled: boolean;
}) {
  const defaultStrategy = strategies[0]?.strategy_id ?? "";
  const aShare = coverage.find((row) => row.asset_group === "A-share constituents");
  const [payload, setPayload] = useState<BacktestPayload>({
    strategy_id: defaultStrategy,
    start_date: cleanDate(aShare?.start_date) || null,
    end_date: cleanDate(aShare?.end_date) || null,
    initial_cash: 100000,
    top_n: 30,
    max_single_position: 0.03,
    fee_rate: 0.001
  });

  useEffect(() => {
    if (defaultStrategy && !payload.strategy_id) {
      setPayload((current) => ({ ...current, strategy_id: defaultStrategy }));
    }
  }, [defaultStrategy]);

  return (
    <section className="page-grid two">
      <form
        className="panel form-panel"
        onSubmit={(event) => {
          event.preventDefault();
          onRun(payload);
        }}
      >
        <PanelHeader title="回测参数" />
        <label>
          策略
          <select
            value={payload.strategy_id}
            onChange={(event) => setPayload({ ...payload, strategy_id: event.target.value })}
          >
            {strategies.map((strategy) => (
              <option value={strategy.strategy_id} key={strategy.strategy_id}>
                {strategy.name}
              </option>
            ))}
          </select>
        </label>
        <div className="form-row">
          <label>
            开始日期
            <input
              type="date"
              value={payload.start_date ?? ""}
              onChange={(event) => setPayload({ ...payload, start_date: event.target.value })}
            />
          </label>
          <label>
            结束日期
            <input
              type="date"
              value={payload.end_date ?? ""}
              onChange={(event) => setPayload({ ...payload, end_date: event.target.value })}
            />
          </label>
        </div>
        <div className="form-row">
          <label>
            初始资金
            <input
              type="number"
              value={payload.initial_cash}
              onChange={(event) => setPayload({ ...payload, initial_cash: Number(event.target.value) })}
            />
          </label>
          <label>
            最大持仓数
            <input
              type="number"
              value={payload.top_n}
              onChange={(event) => setPayload({ ...payload, top_n: Number(event.target.value) })}
            />
          </label>
        </div>
        <div className="form-row">
          <label>
            单票仓位
            <input
              type="number"
              step="0.005"
              value={payload.max_single_position}
              onChange={(event) =>
                setPayload({ ...payload, max_single_position: Number(event.target.value) })
              }
            />
          </label>
          <label>
            交易费率
            <input
              type="number"
              step="0.0005"
              value={payload.fee_rate}
              onChange={(event) => setPayload({ ...payload, fee_rate: Number(event.target.value) })}
            />
          </label>
        </div>
        <button className="primary-button" disabled={disabled || !payload.strategy_id}>
          <Play size={18} />
          运行回测
        </button>
      </form>

      <div className="panel run-preview">
        <PanelHeader title="执行预览" />
        <div className="preview-ladder">
          {["读取平台数据", "计算因子评分", "生成目标仓位", "撮合订单成交", "保存结果账本"].map(
            (step, index) => (
              <div key={step}>
                <span>{index + 1}</span>
                <strong>{step}</strong>
              </div>
            )
          )}
        </div>
      </div>
    </section>
  );
}

function ResultsPage({
  runs,
  selectedRunId,
  setSelectedRunId,
  metricMap,
  nav,
  positions,
  orders
}: {
  runs: RunRow[];
  selectedRunId: string;
  setSelectedRunId: (runId: string) => void;
  metricMap: Record<string, number>;
  nav: NavRow[];
  positions: PositionRow[];
  orders: OrderRow[];
}) {
  return (
    <section className="page-grid single">
      <div className="panel">
        <PanelHeader
          title="回测选择"
          action={
            <select value={selectedRunId} onChange={(event) => setSelectedRunId(event.target.value)}>
              {runs
                .filter((run) => run.status === "success")
                .map((run) => (
                  <option value={run.run_id} key={run.run_id}>
                    {run.run_id}
                  </option>
                ))}
            </select>
          }
        />
        <div className="metric-row compact">
          <MetricCard label="总收益" value={formatPct(metricMap.total_return)} icon={<BarChart3 />} />
          <MetricCard label="年化收益" value={formatPct(metricMap.annual_return)} icon={<Activity />} />
          <MetricCard label="最大回撤" value={formatPct(metricMap.max_drawdown)} icon={<Gauge />} />
          <MetricCard label="胜率" value={formatPct(metricMap.win_rate)} icon={<CheckCircle2 />} />
        </div>
        <NavChart nav={nav} />
      </div>

      <div className="table-grid">
        <div className="panel">
          <PanelHeader title="最新持仓" action={`${positions.length} 条`} />
          <DataTable
            columns={["日期", "代码", "名称", "市值", "权重", "价格"]}
            rows={positions.map((row) => [
              cleanDate(row.date),
              row.asset_code,
              row.asset_name,
              formatMoney(row.market_value),
              formatPct(row.weight),
              formatNumber(row.close_price)
            ])}
          />
        </div>
        <div className="panel">
          <PanelHeader title="最近订单" action={`${orders.length} 条`} />
          <DataTable
            columns={["日期", "状态", "方向", "代码", "名称", "金额", "目标仓位", "原因"]}
            rows={orders.slice(0, 12).map((row) => [
              cleanDate(row.date),
              row.status,
              row.side,
              row.asset_code,
              row.asset_name,
              formatMoney(row.notional),
              formatPct(row.target_weight),
              row.reason
            ])}
          />
        </div>
      </div>
    </section>
  );
}

function RiskPage({
  selectedRun,
  positions,
  orders,
  metricMap
}: {
  selectedRun?: RunRow;
  positions: PositionRow[];
  orders: OrderRow[];
  metricMap: Record<string, number>;
}) {
  const buyOrders = orders.filter((order) => order.side === "BUY").length;
  const sellOrders = orders.filter((order) => order.side === "SELL").length;
  const maxWeight = Math.max(0, ...positions.map((position) => position.weight));

  return (
    <section className="page-grid two">
      <div className="panel">
        <PanelHeader title="风控快照" />
        <div className="risk-grid">
          <KpiLine label="运行状态" value={selectedRun?.status ?? "-"} />
          <KpiLine label="最大单票仓位" value={formatPct(maxWeight)} />
          <KpiLine label="最大回撤" value={formatPct(metricMap.max_drawdown)} intent="danger" />
          <KpiLine label="买入/卖出订单" value={`${buyOrders} / ${sellOrders}`} />
        </div>
      </div>
      <div className="panel">
        <PanelHeader title="模拟交易目标" />
        <DataTable
          columns={["代码", "名称", "目标权重", "市值"]}
          rows={positions.slice(0, 10).map((row) => [
            row.asset_code,
            row.asset_name,
            formatPct(row.weight),
            formatMoney(row.market_value)
          ])}
        />
      </div>
    </section>
  );
}

function MetricCard({ label, value, icon }: { label: string; value: React.ReactNode; icon: React.ReactNode }) {
  return (
    <div className="metric-card">
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PanelHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="panel-header">
      <h2>{title}</h2>
      {action && <div className="panel-action">{action}</div>}
    </div>
  );
}

function NavChart({ nav }: { nav: NavRow[] }) {
  if (!nav.length) {
    return <div className="empty-state">暂无净值数据</div>;
  }
  const chartData = nav.map((row) => ({ ...row, date_label: cleanDate(row.date) }));
  return (
    <div className="chart-box">
      <ResponsiveContainer width="100%" height="100%">
        <ReLineChart data={chartData}>
          <CartesianGrid stroke="#e4e8ef" strokeDasharray="3 3" />
          <XAxis dataKey="date_label" tick={{ fontSize: 11 }} tickLine={false} minTickGap={28} />
          <YAxis tick={{ fontSize: 11 }} tickLine={false} domain={["auto", "auto"]} />
          <Tooltip contentStyle={{ borderRadius: 6, border: "1px solid #d8dee9" }} />
          <Legend />
          <Line type="monotone" dataKey="nav" stroke="#16705a" strokeWidth={2} dot={false} name="策略净值" />
          <Line
            type="monotone"
            dataKey="benchmark_nav"
            stroke="#52677a"
            strokeWidth={2}
            dot={false}
            name="基准净值"
          />
        </ReLineChart>
      </ResponsiveContainer>
    </div>
  );
}

function CompactRuns({ runs }: { runs: RunRow[] }) {
  if (!runs.length) {
    return <div className="empty-state">暂无运行记录</div>;
  }
  return (
    <div className="run-list">
      {runs.slice(0, 6).map((run) => (
        <div className="run-item" key={run.run_id}>
          <div>
            <strong>{run.strategy_name}</strong>
            <small>{run.run_id}</small>
          </div>
          <span className={run.status === "success" ? "status-pill" : "status-pill warn"}>{run.status}</span>
        </div>
      ))}
    </div>
  );
}

function DataTable({ columns, rows }: { columns: string[]; rows: React.ReactNode[][] }) {
  if (!rows.length) {
    return <div className="empty-state">暂无数据</div>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function KpiLine({
  label,
  value,
  intent
}: {
  label: string;
  value: React.ReactNode;
  intent?: "danger";
}) {
  return (
    <div className="kpi-line">
      <span>{label}</span>
      <strong className={intent === "danger" ? "danger-text" : ""}>{value}</strong>
    </div>
  );
}

function pageTitle(page: Page) {
  return pages.find((item) => item.id === page)?.label ?? "总览";
}

function dataPullStatusLabel(status?: DataPullStatus["status"]) {
  if (status === "running") return "运行中";
  if (status === "success") return "已完成";
  if (status === "failed") return "失败";
  return "未运行";
}

function formatPct(value?: number) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(2)}%`;
}

function formatNumber(value?: number) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return value.toFixed(4);
}

function formatMoney(value?: number) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}

function formatCell(value: unknown): React.ReactNode {
  if (value === undefined || value === null) return "-";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "-";
    if (Number.isInteger(value)) return value.toLocaleString("zh-CN");
    if (Math.abs(value) >= 1000) {
      return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
    }
    return value.toFixed(4);
  }

  const text = String(value);
  if (text.length <= 80) return text;
  return <span title={text}>{`${text.slice(0, 77)}...`}</span>;
}

function cleanDate(value?: string | null) {
  if (!value) return "";
  return value.slice(0, 10);
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
