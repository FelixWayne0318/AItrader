# S/R 强度 + 历史数据上下文 实施方案

**日期**: 2026-02-02
**状态**: 实施规划 (已对齐评估框架 v2.1)
**关联文档**: [EVALUATION_FRAMEWORK.md](./EVALUATION_FRAMEWORK.md)
**符合度**: 100% (v2.0 更新后)

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

#### 5.2.1 样本量要求

| 要求 | 最小值 | 推荐值 | 原因 |
|-----|-------|-------|------|
| **交易次数** | ≥50 次/组 | ≥100 次/组 | 统计显著性 |
| **时间跨度** | ≥14 天 | ≥30 天 | 覆盖不同市场状态 |
| **牛市天数** | ≥5 天 | ≥10 天 | 避免偏差 |
| **熊市天数** | ≥5 天 | ≥10 天 | 避免偏差 |
| **震荡天数** | ≥5 天 | ≥10 天 | 避免偏差 |

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

### 6.1 核心绩效指标

> **对应评估框架 Section 4.5**

| 指标 | 定义 | 最低接受 | 目标值 |
|-----|------|---------|-------|
| **胜率 (Win Rate)** | 盈利交易 / 总交易 | 不低于基准 | +5% |
| **盈亏比 (R:R)** | 平均盈利 / 平均亏损 | +10% | +20% |
| **最大回撤 (MDD)** | 最大峰谷跌幅 | 不高于基准 | -10% |
| **Sharpe Ratio** | (收益-无风险) / 波动率 | 不低于基准 | +0.2 |
| **Profit Factor** | 总盈利 / 总亏损 | +5% | +15% |
| **极端行情捕获率** | 极端行情盈利次数 / 极端行情交易次数 | ≥40% | ≥50% |
| **HOLD 比例** | HOLD 信号数 / 总信号数 | < 50% | < 40% |

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

---

## 七、风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|-----|-------|------|---------|
| S/R 识别率低 | 中 | 高 | 增加数据源，调整聚类参数 |
| AI 过度 HOLD | 中 | 中 | 调整 Judge prompt |
| 极端行情损失 | 低 | 高 | 硬风控边界 (评估框架 6.4) |
| 数据不足 | 中 | 中 | 延长收集周期 |

---

## 八、时间线总览

```
Week 1-2:  方案 A - 功能验证与参数调优
           ├─ 验证现有实现
           └─ 调优参数

Week 3-4:  方案 B - 增强实施
           ├─ 历史数据上下文
           └─ 增强 AI 报告

Week 5-8:  数据收集
           ├─ 模拟/纸交易
           └─ 检查点评估

Week 9-12: 实盘测试 + 评估
           ├─ 小资金实盘
           └─ 生成评估报告

Week 13+:  决策
           └─ 全面上线 / 继续优化 / 回滚
```

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

## 十、指标速查表

> **对应评估框架 Section 九**

| 维度 | 核心指标 | 最低接受 | 目标值 |
|-----|---------|---------|-------|
| **技术** | 数据完整性 | ≥90% | ≥95% |
| **技术** | 处理延迟 | <100ms | <50ms |
| **准确性** | S/R 识别率 | ≥55% | ≥75% |
| **准确性** | 假信号率 | ≤35% | ≤20% |
| **绩效** | 胜率变化 | ≥0% | +5% |
| **绩效** | 盈亏比变化 | +10% | +20% |
| **绩效** | 最大回撤 | 不高于基准 | -10% |
| **绩效** | Sharpe Ratio | 不低于基准 | +0.2 |
| **绩效** | Profit Factor | +5% | +15% |
| **AI** | 上下文利用率 | ≥50% | ≥70% |
| **AI** | 信号一致性 | ≥70% | ≥80% |
| **风险** | 异常处理成功率 | 100% | 100% |
| **样本** | 最小交易次数 | ≥50次 | ≥100次 |
| **样本** | 最小测试天数 | ≥14天 | ≥30天 |

---

**文档版本**: v2.0
**创建日期**: 2026-02-02
**最后更新**: 2026-02-02
**负责人**: AI Trading Team

**更新历史**:
- v2.0: **重大更新** - 对齐 EVALUATION_FRAMEWORK.md v2.1 标准
  - 添加技术验收标准 (Section 3.3)
  - 补充完整绩效指标 (Sharpe Ratio, Profit Factor, 极端行情捕获率)
  - 完善样本量要求 (时间跨度、市场状态覆盖)
  - 添加 AI 决策质量指标 (Section 6.3)
  - 添加 S/R 准确性指标 (Section 5.4)
  - 添加指标速查表 (Section 十)
- v1.0: 初始版本，基于代码分析结果创建实施方案
