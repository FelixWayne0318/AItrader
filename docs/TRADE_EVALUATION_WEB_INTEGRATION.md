# 交易评估体系 Web 集成文档

## 概述

本文档描述如何将 AItrader 的交易评估体系 (Trade Evaluation System) 集成到 Web 网站系统中。

**集成目标**:
1. **透明度** - 公开展示交易质量评分 (Grade A+/A/B/C/D/F)
2. **信任度** - 用户可验证 AI 机器人的交易纪律 (SL/TP 执行)
3. **教育价值** - 帮助用户理解什么是好交易 (R/R 比率、执行质量)
4. **数据驱动** - 展示信心等级准确率 (HIGH 是否真的胜率更高?)

---

## 🏗️ 架构设计

### 数据流

```
交易机器人 (deepseek_strategy.py)
    ↓
    on_position_closed() → evaluate_trade()
    ↓
MultiAgentAnalyzer.record_outcome()
    ↓
decision_memory.json (持久化存储)
    ↓
TradeEvaluationService (后端服务)
    ↓
FastAPI Routes (/api/public/trade-evaluation/*)
    ↓
Next.js Frontend (SWR 缓存 + 数据展示)
```

### 职责划分

| 层级 | 职责 | 技术 |
|------|------|------|
| **交易系统** | 生成评估数据 | strategy/trading_logic.py |
| **存储层** | 持久化 decision_memory | JSON 文件 |
| **后端服务** | 数据读取、统计计算 | TradeEvaluationService |
| **API 层** | RESTful 端点、数据脱敏 | FastAPI |
| **前端** | 数据展示、可视化 | Next.js + SWR |

---

## 📊 评估体系核心指标

### Grade 系统 (A+ 至 F)

| Grade | 条件 | 说明 |
|-------|------|------|
| **A+** | 盈利 + actual R/R ≥ 2.5 | 超预期盈利 |
| **A** | 盈利 + actual R/R ≥ 1.5 | 强势盈利 |
| **B** | 盈利 + actual R/R ≥ 1.0 | 可接受盈利 |
| **C** | 盈利 + actual R/R < 1.0 | 小幅盈利 (R/R 不佳) |
| **D** | 亏损 ≤ 计划 SL × 120% | 受控亏损 (纪律良好) |
| **F** | 亏损 > 计划 SL × 120% 或无 SL | 失控亏损 |

### 关键指标说明

**Planned R/R** (计划风险收益比):
```
R/R = (Take Profit - Entry) / (Entry - Stop Loss)
例: Entry $100, SL $98, TP $104 → R/R = 4/2 = 2.0
```

**Actual R/R** (实际风险收益比):
```
R/R = (Exit - Entry) / (Entry - SL)
例: Entry $100, SL $98, Exit $103 → R/R = 3/2 = 1.5
```

**Execution Quality** (执行质量):
```
Quality = min(Actual R/R / Planned R/R, 2.0)
例: Planned 2.0, Actual 1.8 → Quality = 0.9 (90%)
```

**Exit Type** (出场方式):
- `TAKE_PROFIT` - 止盈单成交
- `STOP_LOSS` - 止损单成交
- `MANUAL` - 手动平仓 (或 AI 信号反转)
- `REVERSAL` - 反转交易 (平仓 + 开反向仓)

---

## 🔌 API 端点详解

### 公开端点 (无需认证)

#### 1. 评估统计摘要

```http
GET /api/public/trade-evaluation/summary?days=30
```

**Parameters**:
- `days` (int, optional): 回溯天数 (0 = 全部, 默认 30)

**Response**:
```json
{
  "total_evaluated": 30,
  "grade_distribution": {
    "A+": 3,
    "A": 8,
    "B": 7,
    "C": 4,
    "D": 6,
    "F": 2
  },
  "direction_accuracy": 70.0,        // 胜率 %
  "avg_winning_rr": 1.8,             // 平均盈利 R/R
  "avg_execution_quality": 0.85,     // 平均执行质量
  "avg_grade_score": 3.2,            // 平均评分 (0-5)
  "exit_type_distribution": {
    "TAKE_PROFIT": 12,
    "STOP_LOSS": 9,
    "MANUAL": 7,
    "REVERSAL": 2
  },
  "confidence_accuracy": {
    "HIGH": {
      "total": 10,
      "wins": 7,
      "accuracy": 70.0
    },
    "MEDIUM": {
      "total": 15,
      "wins": 9,
      "accuracy": 60.0
    },
    "LOW": {
      "total": 5,
      "wins": 2,
      "accuracy": 40.0
    }
  },
  "avg_hold_duration_min": 1200,    // 平均持仓 20 小时
  "last_updated": "2026-02-14T02:00:00"
}
```

#### 2. 最近交易评估 (脱敏版)

```http
GET /api/public/trade-evaluation/recent?limit=20
```

**Parameters**:
- `limit` (int, optional): 返回数量 (默认 20, 最大 100)

**Response**:
```json
[
  {
    "grade": "A",
    "planned_rr": 2.0,
    "actual_rr": 1.8,
    "execution_quality": 0.9,
    "exit_type": "TAKE_PROFIT",
    "confidence": "HIGH",
    "hold_duration_min": 1847,
    "direction_correct": true,
    "timestamp": "2026-02-14T02:00:00"
  },
  // ... 最多 100 条
]
```

**数据脱敏**: 不包含 entry_price, exit_price, planned_sl, planned_tp, conditions 等敏感字段。

---

### 管理员端点 (需要 Google OAuth)

#### 3. 完整交易评估

```http
GET /api/admin/trade-evaluation/full?limit=50
Authorization: Bearer <token>
```

**Parameters**:
- `limit` (int, optional): 返回数量 (默认 50, 最大 500)

**Response**:
```json
[
  {
    // 所有公开字段 +
    "entry_price": 95000.0,
    "exit_price": 97500.0,
    "planned_sl": 93000.0,
    "planned_tp": 99000.0,
    "pnl": 2.5,
    "position_size_pct": 80,
    "conditions": "RSI 35, MACD bullish crossover, price above SMA200",
    "lesson": "Strong uptrend - entry near support",
    "decision": "LONG",
    "timestamp": "2026-02-14T02:00:00"
  },
  // ...
]
```

#### 4. 导出数据

```http
GET /api/admin/trade-evaluation/export?format=csv&days=30
Authorization: Bearer <token>
```

**Parameters**:
- `format` (str): `json` 或 `csv`
- `days` (int, optional): 回溯天数 (None = 全部)

**Response** (format=csv):
```json
{
  "format": "csv",
  "data": [
    {
      "timestamp": "2026-02-14T02:00:00",
      "decision": "LONG",
      "pnl": 2.5,
      "grade": "A",
      "direction_correct": true,
      "entry_price": 95000.0,
      "exit_price": 97500.0,
      "planned_sl": 93000.0,
      "planned_tp": 99000.0,
      "planned_rr": 2.0,
      "actual_rr": 1.8,
      "execution_quality": 0.9,
      "exit_type": "TAKE_PROFIT",
      "confidence": "HIGH",
      "position_size_pct": 80,
      "hold_duration_min": 1847,
      "conditions": "RSI 35, MACD bullish...",
      "lesson": "Strong uptrend - good entry"
    },
    // ...
  ],
  "count": 30,
  "exported_at": "2026-02-14T03:00:00"
}
```

---

## 🎨 前端集成建议

### 1. 首页 (index.tsx) - 评估卡片

**位置**: 性能统计下方

**组件**: `TradeQualityCard`

**数据源**: `GET /api/public/trade-evaluation/summary?days=30`

**UI 设计**:
```tsx
┌───────────────────────────────────────────┐
│ 📊 交易质量评分 (最近 30 天)               │
├───────────────────────────────────────────┤
│ Grade A/B:  60% (18/30 trades) [进度条]   │
│ 平均 R/R:   1.8:1                         │
│ 执行质量:   85%                           │
│ 止损纪律:   90% (SL 按计划执行)           │
└───────────────────────────────────────────┘
```

**关键指标**:
- Grade A/B 占比 (证明交易质量)
- 平均 R/R (风险收益比)
- 执行质量 (计划执行情况)
- 止损纪律 (Grade D 占亏损比例)

---

### 2. 性能页 (performance.tsx) - 详细表格

**位置**: Performance Stats 下方

**组件**: `TradeEvaluationTable`

**数据源**: `GET /api/public/trade-evaluation/recent?limit=20`

**UI 设计**:
```tsx
最近 20 笔交易评估:

| 时间 | Grade | R/R (计划→实际) | 出场方式 | 持仓时长 |
|------|-------|----------------|----------|----------|
| 2/14 | A     | 2.0 → 1.8      | TP       | 30h 47m  |
| 2/13 | D     | 2.0 → -0.5     | SL       | 2h 15m   |
| 2/12 | A+    | 2.5 → 2.7      | TP       | 15h 30m  |
| ...  | ...   | ...            | ...      | ...      |
```

**交互**:
- 点击行展开详情 (R/R 计算公式、执行质量说明)
- Grade 颜色编码 (A+/A=绿, B/C=黄, D/F=红)
- 排序功能 (按 Grade, R/R, 时间)

---

### 3. 图表页 (chart.tsx) - AI 侧边栏

**位置**: AI Signal 面板下方

**组件**: `RecentTradeQuality`

**数据源**: `GET /api/public/trade-evaluation/recent?limit=5`

**UI 设计**:
```tsx
┌─────────────────────────────┐
│ 📈 最近交易质量              │
├─────────────────────────────┤
│ [Grade 分布饼图]             │
│ A+: 15%, A: 25%, B: 20%...  │
│                             │
│ 最近 5 笔:                   │
│ ● A  - 2/14 (1.8 R/R)       │
│ ● D  - 2/13 (-0.5 R/R, SL)  │
│ ● A+ - 2/12 (2.7 R/R)       │
│ ● B  - 2/11 (1.2 R/R)       │
│ ● C  - 2/10 (0.8 R/R)       │
└─────────────────────────────┘
```

---

### 4. 管理后台 (admin/dashboard.tsx) - 深度分析

**位置**: 新增 "Trade Quality Analysis" 标签页

**组件**: `TradeQualityAnalysis`

**数据源**:
- `GET /api/admin/trade-evaluation/full?limit=100`
- `GET /api/admin/trade-evaluation/summary-admin?days=0`

**功能模块**:

#### 4.1 Confidence Accuracy 表格
```
信心等级准确率分析:

| 等级 | 交易数 | 盈利数 | 胜率 | 平均 R/R | 平均持仓 |
|------|-------|-------|------|----------|----------|
| HIGH | 20    | 14    | 70%  | 1.9      | 25h      |
| MEDIUM | 30  | 18    | 60%  | 1.5      | 18h      |
| LOW  | 10    | 4     | 40%  | 1.2      | 12h      |
```

**洞察**: HIGH 是否真的胜率更高? 是否值得在 HIGH 时加大仓位?

#### 4.2 Exit Type 分析
```
出场方式分布:

[饼图]
- TAKE_PROFIT: 40% (12 trades)
- STOP_LOSS: 30% (9 trades)
- MANUAL: 20% (6 trades)
- REVERSAL: 10% (3 trades)
```

**洞察**: 止盈单比例是否足够高? 是否有过早手动平仓的问题?

#### 4.3 R/R 分布直方图
```
实际 R/R 分布:

[直方图]
3.0+  : ███ (3)
2.0-3.0 : ██████ (6)
1.0-2.0 : ████████████ (12)
0.0-1.0 : ██████ (6)
负数   : ████ (4)
```

**洞察**: 多少交易达到计划 R/R? 是否有系统性提前平仓问题?

#### 4.4 导出功能
```
[下载 CSV] [下载 JSON]

格式: timestamp, decision, pnl, grade, entry_price, ...
用途: Excel 分析、回测验证、AI 训练
```

---

## 🔧 实施步骤

### Phase 1: 后端 (已完成 ✅)

- [x] 创建 `TradeEvaluationService`
- [x] 添加公开 API 端点
- [x] 添加管理员 API 端点
- [x] 数据脱敏和安全验证

### Phase 2: 前端 (待实施)

#### 2.1 创建通用组件
```bash
web/frontend/components/trade-evaluation/
├── GradeCard.tsx          # Grade 卡片 (A+/A/B...)
├── TradeQualityCard.tsx   # 评估摘要卡片 (首页)
├── TradeTable.tsx         # 交易表格 (性能页)
├── GradePieChart.tsx      # Grade 分布饼图
├── ConfidenceTable.tsx    # 信心等级表格 (管理后台)
└── RRHistogram.tsx        # R/R 分布直方图
```

#### 2.2 集成到页面

**首页** (`pages/index.tsx`):
```tsx
import TradeQualityCard from '@/components/trade-evaluation/TradeQualityCard';

// 在性能统计下方添加
<TradeQualityCard days={30} />
```

**性能页** (`pages/performance.tsx`):
```tsx
import TradeTable from '@/components/trade-evaluation/TradeTable';

// 添加新 section
<section>
  <h2>交易质量分析</h2>
  <TradeTable limit={20} />
</section>
```

**图表页** (`pages/chart.tsx`):
```tsx
import { GradePieChart } from '@/components/trade-evaluation/GradePieChart';

// 在 AI 侧边栏添加
<GradePieChart limit={5} />
```

**管理后台** (`pages/admin/dashboard.tsx`):
```tsx
import TradeQualityAnalysis from '@/components/trade-evaluation/TradeQualityAnalysis';

// 添加新标签页
<Tab label="Trade Quality">
  <TradeQualityAnalysis />
</Tab>
```

#### 2.3 数据获取 (SWR)

**创建 hooks**: `hooks/useTradeEvaluation.ts`
```typescript
import useSWR from 'swr';

export function useTradeEvaluationSummary(days: number = 30) {
  const { data, error } = useSWR(
    `/api/public/trade-evaluation/summary?days=${days}`,
    fetcher,
    { refreshInterval: 60000 } // 每分钟刷新
  );

  return {
    summary: data,
    isLoading: !error && !data,
    isError: error
  };
}

export function useRecentTrades(limit: number = 20) {
  const { data, error } = useSWR(
    `/api/public/trade-evaluation/recent?limit=${limit}`,
    fetcher,
    { refreshInterval: 30000 } // 每 30 秒刷新
  );

  return {
    trades: data || [],
    isLoading: !error && !data,
    isError: error
  };
}
```

---

### Phase 3: 测试

#### 3.1 API 测试

**创建测试数据** (`scripts/create_test_evaluation_data.py`):
```python
# 生成模拟的 decision_memory.json
# 包含各种 Grade (A+/A/B/C/D/F)
# 用于前端开发测试
```

**手动测试**:
```bash
# 测试公开端点
curl http://localhost:8000/api/public/trade-evaluation/summary?days=30

# 测试管理员端点 (需要 token)
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/admin/trade-evaluation/full?limit=10
```

#### 3.2 前端测试

- Grade 卡片正确显示颜色 (A=绿, F=红)
- 百分比计算正确 (Grade A/B 占比)
- 表格排序功能正常
- SWR 缓存工作 (不重复请求)
- 数据空状态显示 (无评估数据时)

---

## 📈 成功指标

### 用户体验指标
- ✅ 首页加载时间 < 2 秒 (包含评估卡片)
- ✅ 性能页表格可交互 (排序、分页)
- ✅ 管理后台导出功能正常 (CSV/JSON)

### 数据质量指标
- ✅ API 响应时间 < 500ms (100 条记录)
- ✅ Grade 分布合理 (不全是 A 或 F)
- ✅ 信心等级准确率有差异 (HIGH > MEDIUM > LOW)

### 业务指标
- ✅ 用户在性能页停留时间增加 (证明有价值)
- ✅ 管理员使用导出功能 (证明有实用性)
- ✅ 用户反馈积极 (透明度增加信任)

---

## 🔒 安全考虑

### 数据脱敏
- ✅ 公开 API 不暴露价格 (entry/exit/SL/TP)
- ✅ 公开 API 不暴露详细 conditions
- ✅ 管理员 API 需要 Google OAuth 认证

### 性能优化
- ✅ API 限制返回数量 (最大 100 公开, 500 管理员)
- ✅ 前端 SWR 缓存减少请求
- ✅ 后端文件读取缓存 (考虑 Redis)

### 错误处理
- ✅ 文件不存在返回空数据 (不报错)
- ✅ JSON 解析失败返回空数据
- ✅ 前端优雅降级 (无数据时显示提示)

---

## 📚 参考资料

- **交易评估标准**: `strategy/trading_logic.py:817-1111`
- **MultiAgent 记忆**: `agents/multi_agent_analyzer.py:2360-2389`
- **Web 架构规范**: `docs/WEB_ARCHITECTURE_ANALYSIS.md`
- **API 文档**: FastAPI Swagger UI (`http://localhost:8000/docs`)

---

## 🎯 未来改进

### v5.2 计划
- [ ] WebSocket 实时推送 (交易评估实时更新)
- [ ] Grade 趋势图 (过去 30 天 Grade 变化)
- [ ] Confidence vs Grade 热力图 (哪个组合最成功)
- [ ] 自动生成月度报告 (PDF 导出)

### v5.3 计划
- [ ] A/B 测试不同仓位策略 (基于 Grade 历史)
- [ ] AI 学习建议 (基于失败交易 Grade F 的共性)
- [ ] 用户自定义 Grade 阈值 (调整 R/R 要求)

---

## 🤝 贡献指南

如需添加新指标或修改评估逻辑:

1. **修改评估逻辑**: `strategy/trading_logic.py`
2. **更新服务层**: `web/backend/services/trade_evaluation_service.py`
3. **更新 API 文档**: 本文档 + FastAPI docstrings
4. **更新前端组件**: `web/frontend/components/trade-evaluation/`
5. **运行测试**: 确保所有端点正常工作

---

**文档版本**: v5.1.0
**最后更新**: 2026-02-14
**作者**: Claude Code Agent
