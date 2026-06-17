import React, { useEffect, useMemo, useRef, useState } from "react";
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
  PlatformReadiness,
  PositionRow,
  PortfolioPayload,
  PortfolioResponse,
  RunRow,
  SingleStockPayload,
  SingleStockPriceRow,
  SingleStockProfile,
  SingleStockResponse,
  SingleStockStrategyScript,
  StrategyRow
} from "./types";
import "./styles.css";

type Page = "overview" | "data" | "singleStock" | "portfolio" | "strategies" | "backtest" | "results" | "risk";

const DEFAULT_SINGLE_STOCK_START_DATE = "2025-01-01";
const DEFAULT_SINGLE_STOCK_CODE = `def generate_signals(context):
    prices = context["prices"].copy()
    target_weight = context.get("target_weight", 0.95)

    prices["ma5"] = prices["close"].rolling(5).mean()
    prices["ma20"] = prices["close"].rolling(20).mean()
    prices["target_weight"] = 0.0
    prices.loc[prices["ma5"] > prices["ma20"], "target_weight"] = target_weight
    prices["signal"] = prices["target_weight"].apply(lambda weight: "target_weight" if weight > 0 else "hold_cash")
    prices["score"] = (prices["ma5"] / prices["ma20"] - 1).fillna(0.0)
    prices["reason"] = prices["signal"].map({
        "target_weight": "5日均线高于20日均线，持有目标仓位",
        "hold_cash": "5日均线未高于20日均线，空仓"
    })
    return prices[["date", "signal", "target_weight", "score", "reason"]].dropna()
`;

const pages: Array<{ id: Page; label: string; icon: React.ReactNode }> = [
  { id: "overview", label: "总览", icon: <LayoutDashboard size={18} /> },
  { id: "data", label: "数据中心", icon: <Database size={18} /> },
  { id: "singleStock", label: "单股实验室", icon: <Search size={18} /> },
  { id: "portfolio", label: "组合实验室", icon: <WalletCards size={18} /> },
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
  const [readiness, setReadiness] = useState<PlatformReadiness | null>(null);
  const [factorIc, setFactorIc] = useState<FactorIcRow[]>([]);
  const [strategies, setStrategies] = useState<StrategyRow[]>([]);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [metrics, setMetrics] = useState<MetricRow[]>([]);
  const [nav, setNav] = useState<NavRow[]>([]);
  const [positions, setPositions] = useState<PositionRow[]>([]);
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [singleStockResult, setSingleStockResult] = useState<SingleStockResponse | null>(null);
  const [portfolioResult, setPortfolioResult] = useState<PortfolioResponse | null>(null);
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
      const [overviewData, coverageData, qualityData, catalogData, readinessData, factorIcData, strategiesData, runsData] = await Promise.all([
        api.overview(),
        api.coverage(),
        api.dataQuality(),
        api.dataCatalog(),
        api.platformReadiness(),
        api.factorIc(),
        api.strategies(),
        api.runs()
      ]);
      setOverview(overviewData);
      setCoverage(coverageData);
      setDataQuality(qualityData);
      setDataCatalog(catalogData);
      setReadiness(readinessData);
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

  async function handleRunPortfolio(payload: PortfolioPayload) {
    setLoading(true);
    setApiError("");
    try {
      const result = await api.runPortfolio(payload);
      setPortfolioResult(result);
      await loadBaseData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "组合流程运行失败");
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
            readiness={readiness}
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
        {page === "portfolio" && (
          <PortfolioPage
            result={portfolioResult}
            onRun={handleRunPortfolio}
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
  readiness,
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
  readiness: PlatformReadiness | null;
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
      <div className="panel">
        <PanelHeader title="平台就绪检查" action={readiness ? "已启用" : "未加载"} />
        <div className="readiness-grid">
          <div>
            <strong>核心数据</strong>
            {(readiness?.datasets ?? []).slice(0, 8).map((row) => (
              <KpiLine key={row.dataset} label={row.label} value={`${row.row_count.toLocaleString()} 行`} />
            ))}
          </div>
          <div>
            <strong>交易规则</strong>
            {(readiness?.rules ?? []).map((rule) => (
              <div className="rule-line" key={rule.name}>
                <span className="status-pill">{rule.status}</span>
                <div>
                  <b>{rule.name}</b>
                  <small>{rule.description}</small>
                </div>
              </div>
            ))}
          </div>
        </div>
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
    start_date: DEFAULT_SINGLE_STOCK_START_DATE,
    end_date: new Date().toISOString().slice(0, 10),
    initial_cash: 100000,
    strategy_mode: "buy_hold",
    target_weight: 0.95,
    ma_short: 5,
    ma_long: 20,
    fee_rate: 0.001
  });
  const [profile, setProfile] = useState<SingleStockProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [pricePullLoading, setPricePullLoading] = useState(false);
  const [pricePullMessage, setPricePullMessage] = useState("");
  const lastAutoPullKey = useRef("");
  const [strategyScripts, setStrategyScripts] = useState<SingleStockStrategyScript[]>([]);
  const [selectedScriptId, setSelectedScriptId] = useState<string>("template_ma_cross");
  const [customStrategyName, setCustomStrategyName] = useState("我的单股策略");
  const [strategyCode, setStrategyCode] = useState(DEFAULT_SINGLE_STOCK_CODE);
  const [strategySaveMessage, setStrategySaveMessage] = useState("");
  const [showTradeDaysOnly, setShowTradeDaysOnly] = useState(false);
  const metricMap = result?.metrics ?? {};

  async function loadProfile() {
    const assetCode = payload.asset_code.trim();
    if (assetCode.length < 6) {
      setProfile(null);
      return;
    }
    setProfileLoading(true);
    try {
      const data = await api.singleStockProfile(assetCode, payload.start_date, payload.end_date, 500);
      setProfile(data);
    } catch {
      setProfile(null);
    } finally {
      setProfileLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    const assetCode = payload.asset_code.trim();
    if (assetCode.length < 6) {
      setProfile(null);
      return;
    }
    setProfileLoading(true);
    api
      .singleStockProfile(assetCode, payload.start_date, payload.end_date, 500)
      .then((data) => {
        if (active) setProfile(data);
      })
      .catch(() => {
        if (active) setProfile(null);
      })
      .finally(() => {
        if (active) setProfileLoading(false);
      });
    return () => {
      active = false;
    };
  }, [payload.asset_code, payload.start_date, payload.end_date]);

  useEffect(() => {
    api
      .singleStockStrategyScripts()
      .then((scripts) => {
        setStrategyScripts(scripts);
        const firstScript = scripts[0];
        if (firstScript) {
          setSelectedScriptId(firstScript.script_id);
          setCustomStrategyName(firstScript.is_template ? "我的单股策略" : firstScript.name);
          setStrategyCode(firstScript.code);
        }
      })
      .catch(() => {
        setStrategyScripts([]);
      });
  }, []);

  useEffect(() => {
    const assetCode = payload.asset_code.trim();
    if (assetCode.length < 6 || !payload.start_date || !payload.end_date) return;
    const key = `${assetCode}|${payload.start_date}|${payload.end_date}`;
    if (key === lastAutoPullKey.current) return;

    const timer = window.setTimeout(() => {
      autoPullPrices(key);
    }, 800);
    return () => window.clearTimeout(timer);
  }, [payload.asset_code, payload.start_date, payload.end_date]);

  async function autoPullPrices(key: string) {
    const assetCode = payload.asset_code.trim();
    if (assetCode.length < 6 || !payload.start_date || !payload.end_date) return;
    lastAutoPullKey.current = key;
    setPricePullLoading(true);
    setPricePullMessage("正在自动拉取所选日期范围的行情...");
    try {
      const data = await api.pullSingleStockPrices(assetCode, payload.start_date, payload.end_date);
      setProfile(data);
      setPricePullMessage(data.message ?? `已自动拉取 ${data.selected.rows} 条行情`);
      await loadProfile();
    } catch (error) {
      lastAutoPullKey.current = "";
      setPricePullMessage(error instanceof Error ? error.message : "自动拉取行情失败");
    } finally {
      setPricePullLoading(false);
    }
  }

  function handleSelectScript(scriptId: string) {
    setSelectedScriptId(scriptId);
    if (scriptId === "__new__") {
      setCustomStrategyName("我的单股策略");
      setStrategyCode(DEFAULT_SINGLE_STOCK_CODE);
      return;
    }
    const script = strategyScripts.find((item) => item.script_id === scriptId);
    if (!script) return;
    setCustomStrategyName(script.is_template ? "我的单股策略" : script.name);
    setStrategyCode(script.code);
  }

  async function handleSaveStrategyCode() {
    setStrategySaveMessage("");
    try {
      const saved = await api.saveSingleStockStrategyScript({
        script_id: selectedScriptId && selectedScriptId !== "__new__" && !selectedScriptId.startsWith("template_")
          ? selectedScriptId
          : null,
        name: customStrategyName,
        code: strategyCode
      });
      const scripts = await api.singleStockStrategyScripts();
      setStrategyScripts(scripts);
      setSelectedScriptId(saved.script_id);
      setStrategySaveMessage(`已保存：${saved.name}`);
    } catch (error) {
      setStrategySaveMessage(error instanceof Error ? error.message : "策略保存失败");
    }
  }

  function runSingleStockWorkflow() {
    onRun({
      ...payload,
      strategy_code: payload.strategy_mode === "custom_code" ? strategyCode : null,
      strategy_script_id: payload.strategy_mode === "custom_code" ? selectedScriptId : null,
      custom_strategy_name: payload.strategy_mode === "custom_code" ? customStrategyName : null
    });
  }

  const dailyLedger = result?.daily_ledger ?? [];
  const tradeDayLedger = dailyLedger.filter((row) => {
    const buyQuantity = Number(row.buy_quantity ?? 0);
    const sellQuantity = Number(row.sell_quantity ?? 0);
    const buyAmount = Number(row.buy_amount ?? 0);
    const sellAmount = Number(row.sell_amount ?? 0);
    const filledOrders = Number(row.filled_orders ?? 0);
    const rejectedOrders = Number(row.rejected_orders ?? 0);
    return buyQuantity > 0 || sellQuantity > 0 || buyAmount > 0 || sellAmount > 0 || filledOrders > 0 || rejectedOrders > 0;
  });
  const visibleDailyLedger = showTradeDaysOnly ? tradeDayLedger : dailyLedger;

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
                <option value="custom_code">代码策略</option>
              </select>
            </label>
            {payload.strategy_mode === "custom_code" && (
              <div className="strategy-code-panel">
                <div className="form-row">
                  <label>
                    已保存策略
                    <select value={selectedScriptId} onChange={(event) => handleSelectScript(event.target.value)}>
                      <option value="__new__">新建策略</option>
                      {strategyScripts.map((script) => (
                        <option value={script.script_id} key={script.script_id}>
                          {script.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    策略名称
                    <input
                      value={customStrategyName}
                      onChange={(event) => setCustomStrategyName(event.target.value)}
                      placeholder="例如 我的均线策略"
                    />
                  </label>
                </div>
                <label>
                  策略代码
                  <textarea
                    className="strategy-code-editor"
                    value={strategyCode}
                    onChange={(event) => setStrategyCode(event.target.value)}
                    spellCheck={false}
                  />
                </label>
                <div className="strategy-code-help">
                  必须定义 <code>generate_signals(context)</code>，返回包含 <code>date</code> 和{" "}
                  <code>target_weight</code> 的 DataFrame 或列表；可选字段有 <code>signal</code>、<code>score</code>、
                  <code>reason</code>。
                </div>
                <button className="secondary-button" type="button" onClick={handleSaveStrategyCode}>
                  <Download size={18} />
                  保存策略代码
                </button>
                {strategySaveMessage && <div className="inline-message">{strategySaveMessage}</div>}
              </div>
            )}
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
            {payload.strategy_mode === "ma_filter" && (
              <div className="form-row">
                <label>
                  短均线
                  <input
                    type="number"
                    value={payload.ma_short}
                    onChange={(event) => setPayload({ ...payload, ma_short: Number(event.target.value) })}
                  />
                </label>
                <label>
                  长均线
                  <input
                    type="number"
                    value={payload.ma_long}
                    onChange={(event) => setPayload({ ...payload, ma_long: Number(event.target.value) })}
                  />
                </label>
              </div>
            )}
            <label>
              交易费率
              <input
                type="number"
                step="0.0005"
                value={payload.fee_rate}
                onChange={(event) => setPayload({ ...payload, fee_rate: Number(event.target.value) })}
              />
            </label>
            <div className="button-row">
              <button
                className="primary-button"
                disabled={disabled || !payload.asset_code || !payload.start_date || !payload.end_date}
                onClick={runSingleStockWorkflow}
              >
                <Play size={18} />
                运行单股流程
              </button>
            </div>
            {(pricePullLoading || pricePullMessage) && <div className="inline-message">{pricePullMessage}</div>}
          </div>
          <div className="single-stock-preview">
            <PanelHeader
              title="行情预览"
              action={profileLoading ? "读取中" : `${profile?.selected.rows ?? 0} 条`}
            />
            <div className="stock-profile-strip">
              <KpiLine
                label="股票"
                value={profile ? `${profile.asset_code} ${profile.asset_name}` : payload.asset_code}
              />
              <KpiLine
                label="完整数据范围"
                value={
                  profile?.coverage.start_date
                    ? `${cleanDate(profile.coverage.start_date)} 至 ${cleanDate(profile.coverage.end_date)}`
                    : "暂无"
                }
              />
              <KpiLine label="数据源" value={profile?.coverage.source ?? "-"} />
            </div>
            <CandlestickChart prices={profile?.prices ?? []} orders={result?.orders ?? []} />
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

          <div className="panel">
            <PanelHeader
              title="每日交易账本"
              action={
                <label className="compact-toggle">
                  <input
                    type="checkbox"
                    checked={showTradeDaysOnly}
                    onChange={(event) => setShowTradeDaysOnly(event.target.checked)}
                  />
                  只看有交易日
                  <span>
                    {visibleDailyLedger.length}/{dailyLedger.length} 日
                  </span>
                </label>
              }
            />
            <DataTable
              columns={[
                "日期",
                "总资产",
                "现金",
                "持仓市值",
                "持仓股数",
                "收盘价",
                "仓位",
                "买入股数",
                "卖出股数",
                "买入金额",
                "卖出金额",
                "手续费",
                "成交单",
                "拒单"
              ]}
              rows={[...visibleDailyLedger].reverse().map((row) => [
                cleanDate(String(row.date ?? "")),
                formatMoney(Number(row.nav ?? 0)),
                formatMoney(Number(row.cash ?? 0)),
                formatMoney(Number(row.position_value ?? 0)),
                formatMoney(Number(row.position_quantity ?? 0)),
                formatNumber(Number(row.close_price ?? 0)),
                formatPct(Number(row.position_weight ?? row.gross_exposure ?? 0)),
                formatMoney(Number(row.buy_quantity ?? 0)),
                formatMoney(Number(row.sell_quantity ?? 0)),
                formatMoney(Number(row.buy_amount ?? 0)),
                formatMoney(Number(row.sell_amount ?? 0)),
                formatMoney(Number(row.fee ?? 0)),
                String(row.filled_orders ?? 0),
                String(row.rejected_orders ?? 0)
              ])}
            />
          </div>

        </>
      )}
    </section>
  );
}

function PortfolioPage({
  result,
  onRun,
  disabled
}: {
  result: PortfolioResponse | null;
  onRun: (payload: PortfolioPayload) => void;
  disabled: boolean;
}) {
  const [payload, setPayload] = useState<PortfolioPayload>({
    start_date: "2025-01-01",
    end_date: new Date().toISOString().slice(0, 10),
    initial_cash: 100000,
    universe_limit: 80,
    top_n: 10,
    lookback_days: 60,
    rebalance_days: 20,
    max_single_position: 0.1,
    fee_rate: 0.001
  });
  const metricMap = result?.metrics ?? {};
  const latestPositionDate = result?.positions?.reduce((latest, row) => {
    const rowDate = cleanDate(String(row.date ?? ""));
    return rowDate > latest ? rowDate : latest;
  }, "");
  const latestPositions = (result?.positions ?? [])
    .filter((row) => cleanDate(String(row.date ?? "")) === latestPositionDate)
    .slice(0, 30);
  const tradeLedger = (result?.daily_ledger ?? []).filter((row) => {
    const buyAmount = Number(row.buy_amount ?? 0);
    const sellAmount = Number(row.sell_amount ?? 0);
    const filledOrders = Number(row.filled_orders ?? 0);
    const rejectedOrders = Number(row.rejected_orders ?? 0);
    return buyAmount > 0 || sellAmount > 0 || filledOrders > 0 || rejectedOrders > 0;
  });

  return (
    <section className="page-grid single">
      <div className="panel">
        <PanelHeader title="组合策略实验室" action={result?.run_id ?? "未运行"} />
        <div className="portfolio-layout">
          <div className="single-stock-form">
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
                股票池数量
                <input
                  type="number"
                  min="5"
                  max="600"
                  value={payload.universe_limit}
                  onChange={(event) => setPayload({ ...payload, universe_limit: Number(event.target.value) })}
                />
              </label>
            </div>
            <div className="form-row">
              <label>
                持仓数量
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={payload.top_n}
                  onChange={(event) => setPayload({ ...payload, top_n: Number(event.target.value) })}
                />
              </label>
              <label>
                单股上限
                <input
                  type="number"
                  min="0.001"
                  max="1"
                  step="0.01"
                  value={payload.max_single_position}
                  onChange={(event) => setPayload({ ...payload, max_single_position: Number(event.target.value) })}
                />
              </label>
            </div>
            <div className="form-row">
              <label>
                动量窗口
                <input
                  type="number"
                  min="5"
                  max="250"
                  value={payload.lookback_days}
                  onChange={(event) => setPayload({ ...payload, lookback_days: Number(event.target.value) })}
                />
              </label>
              <label>
                调仓周期
                <input
                  type="number"
                  min="1"
                  max="120"
                  value={payload.rebalance_days}
                  onChange={(event) => setPayload({ ...payload, rebalance_days: Number(event.target.value) })}
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
              disabled={disabled || !payload.start_date || !payload.end_date}
              onClick={() => onRun(payload)}
            >
              <Play size={18} />
              运行组合回测
            </button>
          </div>
          <div className="strategy-brief">
            <strong>当前内置策略：A股动量轮动</strong>
            <p>
              系统在每个调仓日计算过去 N 个交易日涨跌幅，选出排名靠前的股票，按等权和单股上限生成目标仓位，再经过
              T+1、整手、涨跌停、停牌/ST、费用规则撮合。
            </p>
            <div className="rule-line">
              <span className="status-pill">enabled</span>
              <div>
                <b>从单股走向组合</b>
                <small>这里是未来全市场选股、因子打分、行业约束和参数优化的入口。</small>
              </div>
            </div>
          </div>
        </div>
      </div>

      {result && (
        <>
          <div className="metric-row compact">
            <MetricCard label="股票池" value={`${result.data_summary.asset_count} 只`} icon={<Database />} />
            <MetricCard label="总收益" value={formatPct(metricMap.total_return)} icon={<BarChart3 />} />
            <MetricCard label="最大回撤" value={formatPct(metricMap.max_drawdown)} icon={<Gauge />} />
            <MetricCard label="夏普比率" value={formatNumber(metricMap.sharpe)} icon={<Activity />} />
          </div>
          <div className="panel">
            <PanelHeader
              title="组合净值"
              action={`${cleanDate(result.data_summary.start_date)} 至 ${cleanDate(result.data_summary.end_date)}`}
            />
            <NavChart nav={result.nav} />
          </div>
          <div className="table-grid">
            <div className="panel">
              <PanelHeader title="最新持仓" action={`${latestPositions.length} 只`} />
              <DataTable
                columns={["日期", "代码", "名称", "股数", "收盘价", "市值", "权重"]}
                rows={latestPositions.map((row) => [
                  cleanDate(String(row.date ?? "")),
                  String(row.asset_code ?? ""),
                  String(row.asset_name ?? ""),
                  formatMoney(Number(row.quantity ?? 0)),
                  formatNumber(Number(row.close_price ?? 0)),
                  formatMoney(Number(row.market_value ?? 0)),
                  formatPct(Number(row.weight ?? 0))
                ])}
              />
            </div>
            <div className="panel">
              <PanelHeader title="调仓账本" action={`${tradeLedger.length}/${result.daily_ledger.length} 日`} />
              <DataTable
                columns={["日期", "总资产", "现金", "持仓市值", "仓位", "持仓数", "买入", "卖出", "费用", "成交单", "拒单"]}
                rows={[...tradeLedger].reverse().map((row) => [
                  cleanDate(String(row.date ?? "")),
                  formatMoney(Number(row.nav ?? 0)),
                  formatMoney(Number(row.cash ?? 0)),
                  formatMoney(Number(row.position_value ?? 0)),
                  formatPct(Number(row.gross_exposure ?? 0)),
                  String(row.holding_count ?? 0),
                  formatMoney(Number(row.buy_amount ?? 0)),
                  formatMoney(Number(row.sell_amount ?? 0)),
                  formatMoney(Number(row.fee ?? 0)),
                  String(row.filled_orders ?? 0),
                  String(row.rejected_orders ?? 0)
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

function CandlestickChart({ prices, orders = [] }: { prices: SingleStockPriceRow[]; orders?: Array<Record<string, unknown>> }) {
  const allRows = prices.filter(
    (row) =>
      row.open !== null &&
      row.high !== null &&
      row.low !== null &&
      row.close !== null &&
      Number.isFinite(row.open) &&
      Number.isFinite(row.high) &&
      Number.isFinite(row.low) &&
      Number.isFinite(row.close)
  );
  const [visibleCount, setVisibleCount] = useState(120);
  const [endIndex, setEndIndex] = useState(allRows.length);
  const [dragState, setDragState] = useState<{ x: number; endIndex: number } | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const dragMovedRef = useRef(false);

  useEffect(() => {
    setVisibleCount(Math.min(120, Math.max(20, allRows.length)));
    setEndIndex(allRows.length);
  }, [allRows.length]);

  if (!allRows.length) {
    return <div className="empty-state">暂无行情数据，请先在数据中心拉取这只股票的历史日线</div>;
  }

  const minVisible = Math.min(20, allRows.length);
  const maxVisible = Math.min(240, allRows.length);
  const safeVisibleCount = Math.min(Math.max(visibleCount, minVisible), maxVisible);
  const safeEndIndex = Math.min(Math.max(endIndex, safeVisibleCount), allRows.length);
  const startIndex = Math.max(0, safeEndIndex - safeVisibleCount);
  const rows = allRows.slice(startIndex, safeEndIndex);
  const selectedRow = rows.find((row) => cleanDate(row.date) === selectedDate) ?? rows[rows.length - 1];
  const selectedIndex = allRows.findIndex((row) => cleanDate(row.date) === cleanDate(selectedRow.date));
  const previousClose =
    selectedIndex > 0 && allRows[selectedIndex - 1].close !== null ? Number(allRows[selectedIndex - 1].close) : null;
  const selectedClose = Number(selectedRow.close);
  const selectedChange = previousClose === null ? null : selectedClose - previousClose;
  const selectedPctChange = previousClose === null || previousClose === 0 ? null : selectedChange! / previousClose;
  const movingAverages = [
    { label: "MA5", window: 5, color: "#c27a1a" },
    { label: "MA10", window: 10, color: "#2563eb" },
    { label: "MA20", window: 20, color: "#7c3aed" }
  ].map((item) => ({
    ...item,
    values: allRows.map((_, index) => {
      const start = index - item.window + 1;
      if (start < 0) return null;
      const slice = allRows.slice(start, index + 1);
      return slice.reduce((sum, row) => sum + Number(row.close), 0) / item.window;
    })
  }));

  function setWindow(nextVisibleCount: number, nextEndIndex = safeEndIndex) {
    const count = Math.min(Math.max(nextVisibleCount, minVisible), maxVisible);
    const nextEnd = Math.min(Math.max(nextEndIndex, count), allRows.length);
    setVisibleCount(count);
    setEndIndex(nextEnd);
  }

  function pointerRatio(clientX: number, element: HTMLElement) {
    const rect = element.getBoundingClientRect();
    const ratio = (clientX - rect.left) / Math.max(rect.width, 1);
    return Math.min(Math.max(ratio, 0), 1);
  }

  function zoom(multiplier: number, anchorRatio = 1) {
    const nextCount = Math.round(safeVisibleCount * multiplier);
    const count = Math.min(Math.max(nextCount, minVisible), maxVisible);
    const anchorIndex = startIndex + anchorRatio * safeVisibleCount;
    const nextStart = Math.round(anchorIndex - anchorRatio * count);
    setWindow(count, nextStart + count);
  }

  function handleWheel(event: React.WheelEvent<HTMLDivElement>) {
    event.preventDefault();
    zoom(event.deltaY > 0 ? 1.15 : 0.85, pointerRatio(event.clientX, event.currentTarget));
  }

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    dragMovedRef.current = false;
    setDragState({ x: event.clientX, endIndex: safeEndIndex });
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragState) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const candlePixelWidth = Math.max(rect.width / safeVisibleCount, 1);
    const movedCandles = Math.round((dragState.x - event.clientX) / candlePixelWidth);
    if (Math.abs(event.clientX - dragState.x) > 4) {
      dragMovedRef.current = true;
    }
    setWindow(safeVisibleCount, dragState.endIndex + movedCandles);
  }

  function handlePointerUp(event: React.PointerEvent<HTMLDivElement>) {
    if (dragState) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setDragState(null);
    window.setTimeout(() => {
      dragMovedRef.current = false;
    }, 0);
  }

  function selectCandle(row: SingleStockPriceRow) {
    if (dragMovedRef.current) return;
    setSelectedDate(cleanDate(row.date));
  }

  function handleChartClick(event: React.MouseEvent<HTMLDivElement>) {
    if (dragMovedRef.current) return;
    const ratio = pointerRatio(event.clientX, event.currentTarget);
    const index = Math.min(rows.length - 1, Math.max(0, Math.round(ratio * (rows.length - 1))));
    selectCandle(rows[index]);
  }

  const visibleLabel = `${cleanDate(rows[0].date)} 至 ${cleanDate(rows[rows.length - 1].date)}`;
  const allLabel = `${allRows.length} 条 / 显示 ${rows.length} 条`;

  const width = 960;
  const priceHeight = 260;
  const volumeHeight = 78;
  const top = 18;
  const left = 54;
  const right = 18;
  const volumeTop = top + priceHeight + 24;
  const height = volumeTop + volumeHeight + 28;
  const chartWidth = width - left - right;
  const visibleAverageValues = movingAverages
    .flatMap((item) => item.values.slice(startIndex, safeEndIndex))
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const highs = [...rows.map((row) => Number(row.high)), ...visibleAverageValues];
  const lows = [...rows.map((row) => Number(row.low)), ...visibleAverageValues];
  const maxPrice = Math.max(...highs);
  const minPrice = Math.min(...lows);
  const priceRange = Math.max(maxPrice - minPrice, 0.01);
  const maxVolume = Math.max(...rows.map((row) => Number(row.volume ?? 0)), 1);
  const candleGap = chartWidth / rows.length;
  const candleWidth = Math.max(3, Math.min(10, candleGap * 0.55));
  const priceY = (price: number) => top + ((maxPrice - price) / priceRange) * priceHeight;
  const volumeY = (volume: number) => volumeTop + volumeHeight - (volume / maxVolume) * volumeHeight;
  const ticks = [maxPrice, minPrice + priceRange * 0.5, minPrice];
  const averagePaths = movingAverages.map((item) => {
    const points = item.values
      .slice(startIndex, safeEndIndex)
      .map((value, index) => {
        if (value === null) return null;
        const x = left + index * candleGap + candleGap / 2;
        return `${x.toFixed(2)},${priceY(value).toFixed(2)}`;
      })
      .filter((value): value is string => value !== null);
    return { ...item, points: points.join(" ") };
  });
  const orderMarkers = orders
    .filter((order) => String(order.status ?? "") === "filled")
    .map((order) => ({
      date: cleanDate(String(order.date ?? "")),
      side: String(order.side ?? ""),
      quantity: Number(order.quantity ?? 0),
      price: Number(order.price ?? 0),
      notional: Number(order.notional ?? 0),
    }))
    .filter((order) => order.date && Number.isFinite(order.price));

  return (
    <div className="kline-panel">
      <div className="kline-toolbar">
        <div>
          <strong>{visibleLabel}</strong>
          <span>{allLabel}</span>
        </div>
        <div className="kline-toolbar-right">
          <div className="ma-legend">
            {movingAverages.map((item) => (
              <span key={item.label}>
                <i style={{ background: item.color }} />
                {item.label}
              </span>
            ))}
          </div>
          <span className="kline-hint">滚轮缩放，按住拖拽平移，点击蜡烛查看明细</span>
        </div>
      </div>
      <div
        className={dragState ? "kline-chart dragging" : "kline-chart"}
        aria-label="单股K线图"
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onClick={handleChartClick}
      >
      <svg viewBox={`0 0 ${width} ${height}`} role="img">
        {ticks.map((tick) => {
          const y = priceY(tick);
          return (
            <g key={tick}>
              <line x1={left} x2={width - right} y1={y} y2={y} className="chart-grid-line" />
              <text x={12} y={y + 4} className="axis-label">
                {tick.toFixed(2)}
              </text>
            </g>
          );
        })}
        {rows.map((row, index) => {
          const open = Number(row.open);
          const high = Number(row.high);
          const low = Number(row.low);
          const close = Number(row.close);
          const volume = Number(row.volume ?? 0);
          const x = left + index * candleGap + candleGap / 2;
          const rising = close >= open;
          const selected = cleanDate(row.date) === cleanDate(selectedRow.date);
          const bodyTop = priceY(Math.max(open, close));
          const bodyHeight = Math.max(2, Math.abs(priceY(open) - priceY(close)));
          const volumeTopY = volumeY(volume);
          return (
            <g
              key={`${row.date}-${index}`}
              className={`${rising ? "candle rising" : "candle falling"}${selected ? " selected" : ""}`}
              onClick={(event) => {
                event.stopPropagation();
                selectCandle(row);
              }}
            >
              <title>
                {`${cleanDate(row.date)} 开 ${formatNumber(open)} 高 ${formatNumber(high)} 低 ${formatNumber(
                  low
                )} 收 ${formatNumber(close)}`}
              </title>
              <line x1={x} x2={x} y1={priceY(high)} y2={priceY(low)} />
              <rect x={x - candleWidth / 2} y={bodyTop} width={candleWidth} height={bodyHeight} rx={1} />
              <rect
                className="volume-bar"
                x={x - candleWidth / 2}
                y={volumeTopY}
                width={candleWidth}
                height={Math.max(1, volumeTop + volumeHeight - volumeTopY)}
                rx={1}
              />
            </g>
          );
        })}
        {rows.map((row, index) => {
          const date = cleanDate(row.date);
          const markers = orderMarkers.filter((order) => order.date === date);
          if (!markers.length) return null;
          const x = left + index * candleGap + candleGap / 2;
          return markers.map((marker, markerIndex) => {
            const y = priceY(marker.price);
            const isBuy = marker.side === "BUY";
            const offset = markerIndex * 12;
            return (
              <g className={isBuy ? "trade-marker buy" : "trade-marker sell"} key={`${date}-${marker.side}-${markerIndex}`}>
                <title>
                  {`${date} ${marker.side} ${formatMoney(marker.quantity)}股 @ ${formatNumber(marker.price)}，金额 ${formatMoney(marker.notional)}`}
                </title>
                <path
                  d={
                    isBuy
                      ? `M ${x} ${y - 12 - offset} l 7 10 h -14 z`
                      : `M ${x} ${y + 12 + offset} l 7 -10 h -14 z`
                  }
                />
                <text x={x + 8} y={isBuy ? y - 8 - offset : y + 14 + offset}>
                  {isBuy ? "B" : "S"}
                </text>
              </g>
            );
          });
        })}
        {averagePaths.map((item) =>
          item.points ? (
            <polyline
              key={item.label}
              points={item.points}
              fill="none"
              stroke={item.color}
              strokeWidth={1.6}
              className="ma-line"
            />
          ) : null
        )}
        <line x1={left} x2={width - right} y1={volumeTop + volumeHeight} y2={volumeTop + volumeHeight} className="axis-line" />
        <text x={left} y={height - 6} className="axis-label">
          {cleanDate(rows[0].date)}
        </text>
        <text x={width - right - 78} y={height - 6} className="axis-label">
          {cleanDate(rows[rows.length - 1].date)}
        </text>
      </svg>
      </div>
      <div className="kline-detail-grid">
        <KpiLine label="日期" value={cleanDate(selectedRow.date)} />
        <KpiLine label="开盘" value={formatNumber(Number(selectedRow.open))} />
        <KpiLine label="收盘" value={formatNumber(Number(selectedRow.close))} />
        <KpiLine label="最高" value={formatNumber(Number(selectedRow.high))} />
        <KpiLine label="最低" value={formatNumber(Number(selectedRow.low))} />
        <KpiLine
          label="涨跌幅"
          value={selectedPctChange === null ? "-" : formatPct(selectedPctChange)}
          intent={selectedPctChange !== null && selectedPctChange < 0 ? "danger" : undefined}
        />
        <KpiLine label="成交量" value={formatMoney(Number(selectedRow.volume ?? 0))} />
        <KpiLine label="成交额" value={formatMoney(Number(selectedRow.turnover ?? 0))} />
        <KpiLine label="数据源" value={selectedRow.source ?? "-"} />
      </div>
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
