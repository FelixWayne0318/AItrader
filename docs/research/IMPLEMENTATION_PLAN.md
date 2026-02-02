# S/R 强度 + 历史数据上下文 实施方案

**日期**: 2026-02-02
**状态**: 实施规划
**关联文档**: [EVALUATION_FRAMEWORK.md](./EVALUATION_FRAMEWORK.md)

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

### 3.3 验证脚本

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

| 数据项 | 目标量 | 存储位置 |
|-------|-------|---------|
| S/R 预测记录 | ≥100 次 | `data/sr_predictions.json` |
| 交易记录 | ≥50 次 | `data/trades.json` |
| AI 决策日志 | 全部 | `logs/ai_decisions/` |
| 辩论记录 | 全部 | `logs/debates/` |

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

### 5.4 评估检查点

| 时间点 | 检查项 | 决策 |
|-------|-------|------|
| Week 6 | S/R 识别率 ≥55% | 继续 / 优化 |
| Week 7 | 胜率 ≥45% | 继续 / 调参 |
| Week 8 | 盈亏比 ≥1.2 | 继续 / 回滚 |

---

## 六、评估阶段 (Week 9-12)

### 6.1 评估指标

根据 EVALUATION_FRAMEWORK.md 4.5 核心绩效指标：

| 指标 | 最低接受 | 目标值 |
|-----|---------|-------|
| 胜率 | 不低于基准 | +5% |
| 盈亏比 | +10% | +20% |
| 最大回撤 | 不高于基准 | -10% |
| HOLD 比例 | < 50% | < 40% |

### 6.2 评估报告模板

使用 EVALUATION_FRAMEWORK.md 第八章的模板生成评估报告。

### 6.3 决策矩阵

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
| 极端行情损失 | 低 | 高 | 硬风控边界 (6.4) |
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

**文档版本**: v1.0
**创建日期**: 2026-02-02
**负责人**: AI Trading Team
