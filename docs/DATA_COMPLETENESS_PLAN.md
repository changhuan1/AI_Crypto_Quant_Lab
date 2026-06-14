# A股数据完整性建设方案

## 当前结论

项目当前已经能够保存以下规范化数据：

- `raw_prices_daily`：未复权日线，成交量单位为股，成交额单位为元。
- `adjustment_factors`：每日复权因子。
- `daily_market_indicators`：换手率、估值、股本和市值。
- `asset_name_history`：历史名称与 ST 名称区间。
- `trading_calendar`：交易日历。
- `assets`：证券主数据。

当前 Tushare 账号实测能力：

| 接口 | 状态 | 用途 |
|---|---|---|
| `stock_basic` | 可用 | 股票代码、名称、市场、上市日期 |
| `trade_cal` | 可用 | 交易日历 |
| `daily` | 可用 | 未复权日线 |
| `adj_factor` | 可用 | 复权因子 |
| `daily_basic` | 可用 | 估值、换手率、股本、市值 |
| `namechange` | 可用 | 历史名称与 ST 区间 |
| `dividend` | 可用 | 分红送转 |
| `suspend_d` | 无权限 | 停复牌历史 |
| `stk_limit` | 无权限 | 每日涨跌停价格 |
| `index_weight` | 无权限 | 历史指数成分与权重 |
| 财务三表、财务指标 | 无权限 | 基本面因子 |

高级接口当前实测频率约为每接口每小时一次。该频率适合每日增量，不适合多年历史回填。

## 推荐的数据源分工

### 当前账户即可完成

1. 每日收盘后通过 Tushare 更新当天原始行情、复权因子和每日指标。
2. 定期更新证券主数据、交易日历和历史名称。
3. 使用 AKShare 做行情缺口补充和交叉校验，不作为唯一标准表来源。

### Baostock 历史回填

Baostock 用于低成本回填沪市 A 股历史数据，能够提供未复权行情、交易状态、ST 状态、换手率和部分估值指标。历史股票池通过指定交易日全部证券接口生成，并过滤为沪市 `6xxxxx` A 股。

小范围验证：

```powershell
python -m src.jobs.baostock_history_backfill --start-date 2024-01-01 --end-date 2026-06-14 --limit 5 --max-universe-dates 5
```

全部当前沪市股票价格回填，并建立全部交易日股票池：

```powershell
python -m src.jobs.baostock_history_backfill --start-date 2024-01-01 --end-date 2026-06-14 --limit -1 --max-universe-dates -1
```

全量任务会产生数千次股票历史查询，应在小范围验证后单独运行，并保留日志。

### 需要升级权限或第二数据源

1. 历史指数成分与权重：Tushare `index_weight`、聚宽、米筐或商业数据源。
2. 停复牌与涨跌停：Tushare `suspend_d`、`stk_limit` 或商业数据源。
3. 财务数据：Tushare 财务权限、聚宽、米筐或其他带公告日期的数据源。
4. 多年全市场快速回填：提高 Tushare 积分频率，或购买支持批量历史下载的数据服务。

## 更新命令

日常增量，默认更新日期范围内最近 5 个交易日：

```powershell
python -m src.jobs.tushare_market_core_update --start-date 20260601 --end-date 20260614
```

只更新最近一个交易日：

```powershell
python -m src.jobs.tushare_market_core_update --start-date 20260601 --end-date 20260614 --max-trade-dates 1
```

更新范围内全部交易日：

```powershell
python -m src.jobs.tushare_market_core_update --start-date 20240101 --end-date 20260614 --max-trade-dates -1
```

当前低频账号不建议直接执行全量命令。应先升级频率或确定第二数据源。

## 建设顺序

1. 使用 Baostock 回填原始行情、历史股票池、交易状态和 ST 状态。
2. 使用 Tushare 每日增量复权因子、估值市值并交叉校验行情。
3. 接入每日涨跌停价格，完善真实可交易判断。
4. 接入官方历史指数成分与权重，精确复现上证综指样本。
5. 接入按公告日期可见的财务数据。
6. 回测引擎迁移到原始价格加复权因子的标准数据层。
