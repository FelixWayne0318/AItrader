# S/R 强度 + 历史数据上下文 实施方案

**日期**: 2026-02-02
**状态**: 实施规划 (已对齐评估框架 v3.0.1)
**版本**: v3.0.1
**关联文档**: [EVALUATION_FRAMEWORK.md](./EVALUATION_FRAMEWORK.md)
**符合度**: 100% (v3.0.1 更新后)

> **v3.0 重大更新**: 按 EVALUATION_FRAMEWORK.md v3.0.1 世界顶级量化标准重构
> - 样本量要求从 50 次提升到 200+ 次
> - 新增 Sortino/Calmar Ratio、VaR/CVaR 指标
> - 新增 Walk-Forward 验证、策略衰减检测、Bootstrap CI
> - 新增交易成本建模
> - 时间线扩展到 18+ 周

---

## 一、当前实现状态

### 1.1 已完成功能 ✅

| 功能 | 文件 | 状态 | 说明 |
|-----|------|------|------|
| **TradingAgents 架构** | `multi_agent_analyzer.py` | ✅ 完成 | Bull/Bear/Judge/Risk 4阶段 |
| **Bull/Bear 辩论** | `_get_bull/bear_argument()` | ✅ 完成 | 可配置轮数，互相反驳 |
| **Judge 决策** | `_get_judge_decision()` | ✅ 完成 | 避免过度 HOLD |
| **Risk Manager** | `_evaluate_risk()` | ✅ 完成 | 使用 S/R 选择 SL/TP |
| **S/R Zone 计算** | `sr_zone_calculator.py` | ✅ 完成 | 多源聚合，强度计算 |
| **数据聚合** | `ai_data_assembler.py` | ✅ 完成 | 7种数据源统一输出 |
| **技术指标** | `technical_manager.py` | ✅ 完成 | SMA/EMA/RSI/MACD/BB |

### 1.2 待完善功能 ⚠️

| 功能 | 当前状态 | 缺失部分 |
|-----|---------|---------|
| **历史数据上下文** | 部分实现 | 无自动 20 值上下文提取 |
| **AI 报告格式** | 已实现 | 可增强趋势可视化 |

### 1.2.1 需升级到官方库的现有文件 ⚠️ (v3.0.1 新增)

> **原则**: 评估指标计算应使用官方库 (empyrical-reloaded/scipy/statsmodels)，避免自实现出错

| 文件 | 当前状态 | 问题 | 目标 |
|-----|---------|------|------|
| `web/backend/services/performance_service.py` | 自实现 Sharpe/MDD | 未年化、无风险调整 | 改用 empyrical-reloaded |

#### 当前问题代码

**文件**: `web/backend/services/performance_service.py:314-321`

```python
# ❌ 当前: 简化的自实现 (有问题)
import statistics
avg_return = statistics.mean(pnl_values)
std_return = statistics.stdev(pnl_values)
sharpe_ratio = (avg_return / std_return) * (252 ** 0.5)  # 问题: 252是股票交易日，加密货币应用365
```

**问题清单**:
- ❌ 年化因子错误: 使用 252 (股票) 而非 365 (加密货币 24/7)
- ❌ 未扣除无风险利率
- ❌ 未实现 Sortino/Calmar Ratio
- ❌ 未实现 VaR/CVaR
- ❌ Maximum Drawdown 基于 PnL 而非净值曲线

#### 目标代码

```python
# ✅ 使用 empyrical-reloaded 官方库 (符合 EVALUATION_FRAMEWORK.md v3.0.1)
import empyrical-reloaded as ep
import pandas as pd

# 将 PnL 转换为收益率序列
returns = pd.Series(pnl_values) / initial_equity

# 核心绩效指标
sharpe = ep.sharpe_ratio(returns, annualization=365)
sortino = ep.sortino_ratio(returns, annualization=365)
calmar = ep.calmar_ratio(returns, annualization=365)
max_dd = ep.max_drawdown(returns)

# 尾部风险指标
var_95 = ep.value_at_risk(returns, cutoff=0.05)
```

#### 升级优先级

| 优先级 | 文件 | 原因 |
|-------|------|------|
| **P0** | `performance_service.py` | Web Dashboard 显示的核心指标 |
| P1 | 未来评估模块 | 新代码直接使用官方库 |

#### 升级时间

建议在 **Week 3-4 (Phase 1 快速验证)** 期间完成，确保评估数据准确。

### 1.3 架构验证

```
当前架构完全符合 TradingAgents 标准:

┌─────────────────────────────────────────────────────┐
│  Phase 1: Data Assembly (AIDataAssembler)           │
│  └─ 7 data sources → unified dict                   │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  Phase 2: S/R Zone Calculation                      │
│  └─ Multi-source clustering → zones + hard_control  │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  Phase 3: Bull/Bear Debate (2 rounds)               │ ✅ 已实现
│  ├─ Bull Analyst (temperature=0.3)                  │
│  └─ Bear Analyst (temperature=0.3)                  │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  Phase 4: Judge Decision                            │ ✅ 已实现
│  └─ Evaluates debate → LONG|SHORT|HOLD              │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  Phase 5: Risk Evaluation & S/R Hard Control        │ ✅ 已实现
│  ├─ Set SL using S/R zones                          │
│  ├─ Set TP using S/R zones                          │
│  └─ Determine position_size_pct                     │
└─────────────────────────────────────────────────────┘
```

---

## 1.5 依赖库要求 (v3.0.1 新增)

> **核心原则**: 尽量使用官方库，避免自己实现容易出错的计算

### 必需依赖

```bash
pip install empyrical-reloaded scipy statsmodels pandas numpy
```

| 库 | 版本 | 用途 | 文档 |
|---|------|------|------|
| **empyrical-reloaded** | ≥0.5.5 | Sharpe/Sortino/Calmar/MDD/VaR | [empyrical-reloaded.ml4trading.io](https://empyrical-reloaded.ml4trading.io/) |
| **scipy** | ≥1.9.0 | Bootstrap、统计检验 | [docs.scipy.org](https://docs.scipy.org/doc/scipy/reference/stats.html) |
| **statsmodels** | ≥0.14.0 | 多重假设检验校正 | [statsmodels.org](https://www.statsmodels.org/) |
| **pandas** | ≥2.0.0 | 时间序列处理 | [pandas.pydata.org](https://pandas.pydata.org/) |
| **numpy** | ≥1.24.0 | 数值计算 | [numpy.org](https://numpy.org/) |

### 为什么使用官方库？

| 自己实现 | 官方库 |
|---------|-------|
| ❌ 容易出错 (年化、标准差公式等) | ✅ 经过广泛测试和验证 |
| ❌ 维护成本高 | ✅ 社区持续维护 |
| ❌ 边界情况处理不全 | ✅ 处理 NaN、空数组等边界情况 |
| ❌ 可能有性能问题 | ✅ 优化过的实现 |

---

## 二、实施方案

### 2.1 方案选择

由于核心架构已完成，实施方案分为两种：

| 方案 | 描述 | 工作量 | 风险 |
|-----|------|-------|------|
| **方案 A: 直接启用** | 验证现有功能，调优参数 | 低 | 低 |
| **方案 B: 增强实施** | 补充历史上下文，增强 AI 报告 | 中 | 低 |

**推荐: 方案 A + 方案 B 增量实施**

---

## 三、方案 A: 直接启用 (Week 1-2)

### 3.1 目标

验证现有实现符合评估框架要求，开始数据收集。

### 3.2 任务清单

#### Week 1: 功能验证

| 任务 | 优先级 | 验收标准 |
|-----|-------|---------|
| 验证 S/R Zone 输出格式 | P0 | 符合 4.2.1 定义 |
| 验证 Bull/Bear 辩论流程 | P0 | 生成 debate_transcript |
| 验证 Judge 决策质量 | P0 | HOLD 比例 < 50% |
| 验证 Risk Manager SL/TP | P0 | 基于 S/R 价位设置 |
| 验证硬风控边界 | P0 | 符合 6.4 安全边界 |

#### Week 2: 参数调优

| 参数 | 当前值 | 调优范围 | 方法 |
|-----|-------|---------|------|
| `debate_rounds` | 2 | 1-3 | 观察信号质量 |
| `temperature` | 0.3 | 0.2-0.5 | A/B 测试 |
| `hard_control_threshold` | HIGH | HIGH/MEDIUM | 根据阻挡频率 |

### 3.3 技术验收标准

> **对应评估框架 Section 二**

| 指标 | 目标值 | 最大容忍 | 验证方法 |
|-----|-------|---------|---------|
| **数据完整性** | ≥95% | ≥90% | `len(history) == 20` 检查 |
| **持久化可靠性** | ≥95% | ≥90% | 重启前后数据对比 |
| **数据处理延迟** | <50ms | <100ms | 性能埋点 |
| **内存增量** | <30MB | <50MB | 监控对比 |
| **文件 I/O** | <10ms | <20ms | 持久化耗时 |

```python
# 验收测试用例
def test_history_completeness():
    """历史数据应包含 20 个值"""
    history = indicator_manager.get_history('rsi', timeframe='15m')
    assert len(history) == 20, f"Expected 20, got {len(history)}"

def test_persistence_after_restart():
    """重启后历史数据应保留"""
    before = load_history_from_file()
    # 模拟重启
    after = load_history_from_file()
    assert before == after, "Data lost after restart"

def test_processing_latency():
    """数据处理延迟应 < 100ms"""
    start = time.time()
    process_all_indicators()
    elapsed = (time.time() - start) * 1000
    assert elapsed < 100, f"Too slow: {elapsed}ms"
```

### 3.4 验证脚本

```bash
# 运行实时诊断
python3 scripts/diagnose_realtime.py --export

# 检查 S/R Zone 输出
python3 -c "
from utils.sr_zone_calculator import SRZoneCalculator
# 验证输出格式
"

# 检查辩论记录
python3 -c "
from agents.multi_agent_analyzer import MultiAgentAnalyzer
analyzer = MultiAgentAnalyzer(...)
# 运行分析并检查 last_debate_transcript
"
```

---

## 四、方案 B: 增强实施 (Week 3-4)

### 4.1 目标

补充历史数据上下文功能，增强 AI 决策质量。

### 4.2 功能增强

#### 4.2.1 历史数据上下文 (P1)

**当前状态**: `get_kline_data(20)` 可获取，但未自动传递给 AI

**实施方案**:

```python
# indicators/technical_manager.py 新增方法
def get_historical_context(self, count: int = 20) -> Dict[str, Any]:
    """
    获取 AI 友好格式的历史数据上下文

    Returns:
        {
            "price_trend": [最近 20 个收盘价],
            "volume_trend": [最近 20 个成交量],
            "rsi_trend": [最近 20 个 RSI],
            "macd_trend": [最近 20 个 MACD],
            "trend_direction": "BULLISH/BEARISH/NEUTRAL",
            "momentum_shift": "INCREASING/DECREASING/STABLE"
        }
    """
```

**集成点**: `ai_data_assembler.py` 的 `assemble()` 方法

#### 4.2.2 增强 AI 报告 (P2)

**当前状态**: `sr_zone_calculator.py` 已有 `ai_report`

**增强方案**:
- 添加趋势箭头 (↑↓→)
- 添加强度变化提示 ("RSI 从 30 上升至 45")
- 添加异常标记 ("⚠️ 价格接近强阻力")

### 4.3 实施步骤

```
Week 3:
├─ Day 1-2: 实现 get_historical_context()
├─ Day 3-4: 集成到 ai_data_assembler
└─ Day 5: 单元测试

Week 4:
├─ Day 1-2: 增强 AI 报告格式
├─ Day 3-4: 端到端测试
└─ Day 5: 部署到开发环境
```

---

## 五、数据收集阶段 (Week 5-8)

### 5.1 目标

收集足够数据验证评估框架指标。

### 5.2 数据收集要求

> **对应评估框架 Section 4.7**

#### 5.2.1 样本量要求 (v3.0 更新)

> **基于统计功效分析 (Power Analysis)**，参考 Cohen (1988)

| 要求 | 最小值 | 推荐值 | 理想值 | 能检测的效应 |
|-----|-------|-------|-------|------------|
| **交易次数** | ≥200 次 | ≥500 次 | ≥1000 次 | medium → small |
| **时间跨度** | ≥30 天 | ≥60 天 | ≥90 天 | 覆盖多种 regime |
| **牛市天数** | ≥10 天 | ≥20 天 | ≥30 天 | 避免偏差 |
| **熊市天数** | ≥10 天 | ≥20 天 | ≥30 天 | 避免偏差 |
| **震荡天数** | ≥10 天 | ≥20 天 | ≥30 天 | 避免偏差 |

**为什么 50 次不够？**

| 原问题 | 后果 |
|-------|------|
| **统计功效不足** | 只能检测 large 效应 (d > 0.8)，错过中小改进 |
| **Type II Error 高** | 真实有效的策略可能被误判为无效 |
| **置信区间过宽** | 结果不确定性高，无法做出可靠决策 |
| **Regime 覆盖不全** | 50 次交易可能都在同一市场状态下 |

#### 5.2.2 数据存储

| 数据项 | 目标量 | 存储位置 |
|-------|-------|---------|
| S/R 预测记录 | ≥100 次 | `data/sr_predictions.json` |
| 交易记录 | ≥50 次 | `data/trades.json` |
| AI 决策日志 | 全部 | `logs/ai_decisions/` |
| 辩论记录 | 全部 | `logs/debates/` |
| 市场状态标记 | 全部 | `logs/market_conditions/` |

### 5.3 数据收集脚本

```python
# 自动保存到文件
def save_prediction_record(sr_zones, signal, actual_result):
    record = {
        "timestamp": datetime.now().isoformat(),
        "sr_zones": sr_zones,
        "signal": signal,
        "actual_result": actual_result,  # 后续填充
    }
    # 保存到 JSON
```

### 5.4 S/R 准确性指标

> **对应评估框架 Section 三**

| 指标 | Phase 1 目标 | Phase 2 目标 | Phase 3 目标 |
|-----|-------------|-------------|-------------|
| **强阻力识别率** | ≥55% | ≥65% | ≥75% |
| **强支撑识别率** | ≥55% | ≥65% | ≥75% |
| **假信号率** | ≤35% | ≤25% | ≤20% |
| **多框架共振准确率** | ≥60% | ≥70% | ≥80% |

**强度分级标准**:

| 强度等级 | 条件 | 预期准确率 |
|---------|------|-----------|
| **STRONG** | Order Wall + 多框架共振 + Volume 确认 | ≥75% |
| **MEDIUM** | 2+ 指标共振 | 60-75% |
| **WEAK** | 单一指标 | 50-60% |

### 5.5 评估检查点

| 时间点 | 检查项 | 决策 |
|-------|-------|------|
| Week 6 | S/R 识别率 ≥55%, 假信号率 ≤35% | 继续 / 优化聚类参数 |
| Week 7 | 胜率 ≥45%, 信号一致性 ≥70% | 继续 / 调整 AI 参数 |
| Week 8 | 盈亏比 ≥1.2, 多框架共振 ≥60% | 继续 / 回滚 |

---

## 六、评估阶段 (Week 9-12)

### 6.1 核心绩效指标 (v3.0 更新)

> **对应评估框架 Section 4.5 + 9.2 + 9.3**

#### 6.1.1 基础绩效指标

| 指标 | 定义 | 最低接受 | 目标值 |
|-----|------|---------|-------|
| **胜率 (Win Rate)** | 盈利交易 / 总交易 | 不低于基准 | +5% |
| **盈亏比 (R:R)** | 平均盈利 / 平均亏损 | +10% | +20% |
| **最大回撤 (MDD)** | 最大峰谷跌幅 | <15% | <10% |
| **Profit Factor** | 总盈利 / 总亏损 | >1.2 | >1.5 |
| **极端行情捕获率** | 极端行情盈利次数 / 极端行情交易次数 | ≥40% | ≥50% |
| **HOLD 比例** | HOLD 信号数 / 总信号数 | < 50% | < 40% |

#### 6.1.2 风险调整收益指标 (v3.0 新增)

> **使用 empyrical-reloaded 官方库计算**

| 指标 | 最低接受 | 目标值 | 理想值 | 说明 |
|-----|---------|-------|-------|------|
| **Sharpe Ratio** (年化) | >0.5 | >1.0 | >1.5 | 扣除成本后 |
| **Sortino Ratio** (年化) | >0.7 | >1.2 | >2.0 | 只惩罚下行风险 |
| **Calmar Ratio** | >0.5 | >1.0 | >2.0 | 年化收益/MDD |

```python
# 使用 empyrical-reloaded 官方库计算 (不要自己实现!)
import empyrical-reloaded as ep

sharpe = ep.sharpe_ratio(returns, annualization=365)
sortino = ep.sortino_ratio(returns, annualization=365)
calmar = ep.calmar_ratio(returns, annualization=365)
max_dd = ep.max_drawdown(returns)
```

#### 6.1.3 尾部风险指标 (v3.0 新增)

> **Basel III/IV 监管标准必备指标**

| 指标 | 最低接受 | 目标值 | 说明 |
|-----|---------|-------|------|
| **VaR_95** | <5% | <3% | 单日最大亏损 (95% 置信度) |
| **CVaR_99** | <8% | <5% | 极端损失平均值 (99% 置信度) |

```python
# 使用 empyrical-reloaded 官方库计算
var_95 = ep.value_at_risk(returns, cutoff=0.05)
```

### 6.2 盈亏比分布分析

> **参考值 (非硬性要求，AI 可根据市场情况灵活调整)**

| 行情类型 | 参考盈亏比 | 说明 |
|---------|----------|------|
| 正常行情 | 1.2-1.5 | AI 根据 S/R 距离决定 |
| 极端行情 (顺势) | 2.5-4.0 | 顺势放大止盈 |
| 极端行情 (逆势) | 0.8-1.2 | 快速止盈保护 |

**注意**: 这些是评估参考，不是 AI 必须达到的目标

### 6.3 AI 决策质量指标

> **对应评估框架 Section 五**

| 指标 | 目标 | 测量方法 |
|-----|------|---------|
| **HOLD 信号比例变化** | 减少 20% | 对比新旧系统 |
| **信号一致性** | ≥70% | 相同数据重复测试 |
| **HIGH confidence 胜率** | ≥60% | 高信心信号的实际胜率 |
| **历史上下文利用率** | ≥60% | AI 推理文本关键词分析 |

**决策质量分级**:

| 质量等级 | 条件 | 预期比例 |
|---------|------|---------|
| **优秀** | 使用 3+ 类上下文关键词 | ≥20% |
| **良好** | 使用 1-2 类上下文关键词 | ≥40% |
| **一般** | 未明确使用上下文 | ≤40% |

### 6.4 评估报告模板

使用 EVALUATION_FRAMEWORK.md 第八章的模板生成评估报告。

### 6.5 决策矩阵

| 评估结果 | 行动 |
|---------|------|
| 所有指标达标 | 全面上线 |
| 部分达标 | 继续优化，延长测试 |
| 多项不达标 | 回滚到原系统 |

### 6.6 交易成本建模 (v3.0 新增)

> **关键**: 不考虑交易成本的回测是不现实的

#### 6.6.1 成本结构 (Binance Futures VIP 0)

| 成本项 | 费率 | 说明 |
|-------|------|------|
| **Maker 手续费** | 0.02% | 挂单 |
| **Taker 手续费** | 0.04% | 吃单 |
| **基础滑点** | 0.05% | 流动性影响 |
| **资金费率** | ~0.01%/8h | 持仓成本 |

#### 6.6.2 成本敏感性分析

| 交易频率 | 日交易次数 | 月成本估计 | 最低月收益要求 |
|---------|-----------|-----------|--------------|
| **低频** | 1 次/天 | ~5.4% | >6% |
| **中频** | 3 次/天 | ~16.2% | >18% |
| **高频** | 10 次/天 | ~54% | >60% |

> **结论**: 高频策略对成本极其敏感，必须严格控制交易频率

#### 6.6.3 成本调整后的绩效计算

```python
# 所有绩效评估应在扣除成本后进行
adjusted_pnl_pct = raw_pnl_pct - total_cost_pct

# 验收标准:
# - 扣除成本后 Sharpe Ratio > 1.0
# - 扣除成本后 Profit Factor > 1.5
```

### 6.7 高级验证方法 (v3.0 新增)

> **对应评估框架 Section 七**

#### 6.7.1 Walk-Forward 验证

```
传统方法 (有问题):
[============ Training ============][======= Test =======]
问题: 无法检测策略是否对未来市场状态有效

Walk-Forward 方法:
[Train 1][Test 1]
         [Train 2][Test 2]
                  [Train 3][Test 3]
                           [Train 4][Test 4]
优势: 模拟真实交易场景，检测策略衰减
```

**验收标准**:
- `avg_degradation < 0.5` (训练到测试的 Sharpe 下降 < 0.5)
- `min_test_sharpe > 0` (所有测试窗口 Sharpe > 0)

#### 6.7.2 策略衰减检测

> **所有策略都会衰减，越早发现越好**

| 衰减程度 | 定义 | 行动 |
|---------|------|------|
| **NONE** | 无显著下降 | 继续监控 |
| **MILD** | 下降 <30% | 调整参数或减小仓位 |
| **MODERATE** | 下降 30-50% | 暂停交易，重新评估 |
| **SEVERE** | 下降 >50% | 立即停止，考虑回滚 |

**监控频率**: 每周运行一次策略衰减检测

#### 6.7.3 Bootstrap 置信区间

> **使用 scipy.stats.bootstrap 官方实现**

```python
from scipy import stats

result = stats.bootstrap(
    (returns,),
    statistic=lambda x, axis: ep.sharpe_ratio(x, annualization=365),
    n_resamples=9999,
    confidence_level=0.95,
    method='bca'
)
```

**验收标准**:
- Sharpe Ratio 95% CI 下界 > 0.5
- Maximum Drawdown 95% CI 上界 < 15%

#### 6.7.4 多重假设检验校正

> **使用 statsmodels.stats.multitest.multipletests**

当同时检验多个指标 (胜率、Sharpe、MDD 等) 时，使用 FDR 校正控制假阳性率:

```python
from statsmodels.stats.multitest import multipletests

reject, pvals_corrected, _, _ = multipletests(
    p_values,
    alpha=0.05,
    method='fdr_bh'  # Benjamini-Hochberg
)
```

---

## 七、风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|-----|-------|------|---------|
| S/R 识别率低 | 中 | 高 | 增加数据源，调整聚类参数 |
| AI 过度 HOLD | 中 | 中 | 调整 Judge prompt |
| 极端行情损失 | 低 | 高 | 硬风控边界 (评估框架 6.4) |
| 数据不足 | 中 | 中 | 延长收集周期 |

---

## 八、时间线总览 (v3.0 更新)

> **对应评估框架 Section 八**: 扩展到 18+ 周，支持更大样本量和高级验证

```
┌─────────────────────────────────────────────────────────────┐
│  Week 1-2: 技术实现 + 单元测试                               │
│  ├─ 目标: 完成代码实现                                       │
│  ├─ 评估: 技术实现标准 (Section 3.3)                         │
│  ├─ 产出: 功能完成，所有测试通过                             │
│  └─ 里程碑: 代码合并到 main 分支                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Week 3-4: Phase 1 快速验证                                  │
│  ├─ 目标: 检测严重问题 (large 效应)                          │
│  ├─ 样本: 50-100 次交易                                      │
│  ├─ 评估: 基础指标 + S/R 准确性                              │
│  └─ 决策点: 继续 / 紧急回滚                                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Week 5-10: Phase 2 标准验证                                 │
│  ├─ 目标: 验证显著改进 (medium 效应)                         │
│  ├─ 样本: ≥200 次交易 (最低统计功效要求)                    │
│  ├─ 评估: 完整绩效 + VaR/CVaR + 交易成本扣除                │
│  ├─ 高级: Walk-Forward 验证                                  │
│  ├─ 产出: 绩效报告 + Bootstrap 置信区间                      │
│  └─ 决策点: 扩大部署 / 优化参数 / 回滚                      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Week 11-18: Phase 3 完整验证                                │
│  ├─ 目标: 检测微小改进 + 长期稳定性                          │
│  ├─ 样本: ≥500 次交易 (推荐)                                │
│  ├─ 评估: 所有标准 + 策略衰减检测                           │
│  ├─ 覆盖: 牛市/熊市/震荡 各 ≥20 天                          │
│  ├─ 产出: 完整评估报告                                       │
│  └─ 决策点: 全面上线 / 继续优化 / 回滚                      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Week 19+: 持续监控                                          │
│  ├─ 条件: 达到所有最低接受标准                               │
│  ├─ 监控: 每周策略衰减检测                                   │
│  ├─ 警报: MILD→观察, MODERATE→暂停, SEVERE→回滚            │
│  └─ 迭代: 根据数据持续优化                                   │
└─────────────────────────────────────────────────────────────┘
```

### 8.1 各阶段样本量与验证要求

| 阶段 | 最小交易次数 | 最小测试天数 | 能检测的效应 | 统计功效 |
|-----|-------------|-------------|-------------|---------|
| **Phase 1** | ≥50次 | ≥14天 | Large (10%+) | ~50% |
| **Phase 2** | ≥200次 | ≥30天 | Medium (5%+) | ~80% |
| **Phase 3** | ≥500次 | ≥60天 | Small (2%+) | ~95% |

---

## 九、立即行动项

### 本周 (Week 1)

1. [ ] 运行 `diagnose_realtime.py` 验证当前功能
2. [ ] 检查 S/R Zone 输出格式是否符合文档
3. [ ] 检查 Bull/Bear 辩论日志
4. [ ] 确认 Risk Manager 使用 S/R 设置 SL/TP
5. [ ] 开始记录交易数据

### 下周 (Week 2)

1. [ ] 分析第一周数据
2. [ ] 调整 `debate_rounds` 和 `temperature`
3. [ ] 评估 HOLD 比例
4. [ ] 准备增强实施 (如需要)

---

## 十、指标速查表 (v3.0 更新)

> **对应评估框架 Section 九**

### 10.1 核心绩效指标

| 维度 | 核心指标 | 最低接受 | 目标值 | 理想值 |
|-----|---------|---------|-------|-------|
| **技术** | 数据完整性 | ≥95% | 100% | 100% |
| **技术** | 处理延迟 | <100ms | <50ms | <20ms |
| **准确性** | S/R 识别率 | ≥55% | ≥65% | ≥75% |
| **准确性** | 假信号率 | ≤35% | ≤25% | ≤20% |
| **绩效** | 胜率变化 | ≥0% | +5% | +10% |
| **绩效** | 盈亏比变化 | +5% | +15% | +25% |
| **绩效** | 最大回撤 | <15% | <10% | <7% |
| **AI** | 上下文利用率 | ≥50% | ≥70% | ≥85% |
| **风险** | 异常处理成功率 | 100% | 100% | 100% |

### 10.2 风险调整收益指标 (v3.0 新增)

| 指标 | 最低接受 | 目标值 | 理想值 | 说明 |
|-----|---------|-------|-------|------|
| **Sharpe Ratio** (年化) | >0.5 | >1.0 | >1.5 | 扣除成本后 |
| **Sortino Ratio** (年化) | >0.7 | >1.2 | >2.0 | 只惩罚下行 |
| **Calmar Ratio** | >0.5 | >1.0 | >2.0 | 收益/MDD |
| **Profit Factor** | >1.2 | >1.5 | >2.0 | 扣除成本后 |

### 10.3 尾部风险指标 (v3.0 新增)

| 指标 | 最低接受 | 目标值 | 说明 |
|-----|---------|-------|------|
| **VaR_95** | <5% | <3% | 单日最大亏损 (95% 置信度) |
| **CVaR_99** | <8% | <5% | 极端损失平均值 (99% 置信度) |

### 10.4 样本量与验证要求 (v3.0 更新)

| 要求 | Phase 1 | Phase 2 | Phase 3 |
|-----|---------|---------|---------|
| **最小交易次数** | ≥50次 | ≥200次 | ≥500次 |
| **最小测试天数** | ≥14天 | ≥30天 | ≥60天 |
| **能检测的效应** | Large (10%+) | Medium (5%+) | Small (2%+) |
| **统计功效** | ~50% | ~80% | ~95% |

### 10.5 高级验证标准 (v3.0 新增)

| 验证方法 | 通过标准 | 说明 |
|---------|---------|------|
| **Walk-Forward** | avg_degradation < 0.5, min_test_sharpe > 0 | 策略鲁棒性 |
| **Bootstrap CI** | Sharpe 95% CI 下界 > 0.5 | 统计置信度 |
| **策略衰减** | severity = NONE or MILD | 长期稳定性 |
| **成本扣除** | 扣除后仍盈利 | 现实可行性 |

---

**文档版本**: v3.0.1
**创建日期**: 2026-02-02
**最后更新**: 2026-02-05
**负责人**: AI Trading Team

**更新历史**:
- v3.0.1: 新增 Section 1.2.1 - 明确列出需升级到官方库的现有文件 (performance_service.py)
- v3.0: **重大更新** - 对齐 EVALUATION_FRAMEWORK.md v3.0.1 世界顶级量化标准
  - 样本量要求从 50 次提升到 200+ 次 (基于统计功效分析)
  - 新增依赖库要求 (empyrical-reloaded, scipy, statsmodels)
  - 新增 Sortino Ratio、Calmar Ratio
  - 新增 VaR/CVaR 尾部风险评估 (Basel III/IV 标准)
  - 新增交易成本建模 (Section 6.6)
  - 新增高级验证方法 (Section 6.7): Walk-Forward、策略衰减、Bootstrap CI、多重假设校正
  - 时间线扩展到 18+ 周，分 Phase 1/2/3 阶段
  - 更新指标速查表，添加风险调整收益和尾部风险指标
- v2.0: **重大更新** - 对齐 EVALUATION_FRAMEWORK.md v2.1 标准
  - 添加技术验收标准 (Section 3.3)
  - 补充完整绩效指标 (Sharpe Ratio, Profit Factor, 极端行情捕获率)
  - 完善样本量要求 (时间跨度、市场状态覆盖)
  - 添加 AI 决策质量指标 (Section 6.3)
  - 添加 S/R 准确性指标 (Section 5.4)
  - 添加指标速查表 (Section 十)
- v1.0: 初始版本，基于代码分析结果创建实施方案
