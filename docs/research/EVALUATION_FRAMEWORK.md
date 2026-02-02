# S/R 强度 + 历史数据上下文 评估框架

**日期**: 2026-02-02
**状态**: 评估标准定义 (实施前)
**关联文档**: [SR_STRENGTH_RESEARCH.md](./SR_STRENGTH_RESEARCH.md)

---

## 一、项目概述

### 1.1 待实施功能

| 工程 | 目标 | 预期收益 |
|-----|------|---------|
| **历史数据上下文** | AI 看到 20 值趋势而非孤立单值 | 提升 AI 决策质量 |
| **S/R 强度增强** | 自动识别支撑阻力强度 | 动态调整 SL/TP |

### 1.2 用户确认的需求

| 问题 | 用户确认 |
|-----|---------|
| 哪些数据需要历史上下文？ | ✅ 全部数据类型 |
| 历史数据保留多少个值？ | ✅ 20 个值 |
| 哪些时间框架需要？ | ✅ 全部 (15M, 4H, 1D) |
| 接受 Token 成本增加？ | ✅ 确认接受 |
| 数据持久化方式？ | ✅ 文件持久化 |

---

## 二、技术实现标准

### 2.1 数据质量指标

| 指标 | 目标值 | 测量方法 | 优先级 |
|-----|-------|---------|-------|
| **数据完整性** | ≥95% 无缺失 | 日志检查 `len(history) == 20` | P0 |
| **持久化可靠性** | 重启后数据保留 ≥95% | 重启测试对比 | P0 |
| **数据新鲜度** | 最新数据 < 15分钟 | 时间戳检查 | P1 |

### 2.2 性能指标

| 指标 | 目标值 | 最大容忍 | 测量方法 |
|-----|-------|---------|---------|
| **数据处理延迟** | < 50ms | < 100ms | 性能埋点 |
| **内存增量** | < 30MB | < 50MB | 监控对比 |
| **文件 I/O** | < 10ms/次 | < 20ms/次 | 持久化耗时 |

### 2.3 验收测试用例

```python
# 测试用例 1: 数据完整性
def test_history_completeness():
    """历史数据应包含 20 个值"""
    history = indicator_manager.get_history('rsi', timeframe='15m')
    assert len(history) == 20, f"Expected 20, got {len(history)}"

# 测试用例 2: 持久化可靠性
def test_persistence_after_restart():
    """重启后历史数据应保留"""
    before = load_history_from_file()
    # 模拟重启
    after = load_history_from_file()
    assert before == after, "Data lost after restart"

# 测试用例 3: 性能
def test_processing_latency():
    """数据处理延迟应 < 100ms"""
    start = time.time()
    process_all_indicators()
    elapsed = (time.time() - start) * 1000
    assert elapsed < 100, f"Too slow: {elapsed}ms"
```

---

## 三、S/R 强度准确性标准

### 3.1 准确率目标

| 指标 | Phase 1 目标 | Phase 2 目标 | Phase 3 目标 |
|-----|-------------|-------------|-------------|
| **强阻力识别率** | ≥55% | ≥65% | ≥75% |
| **强支撑识别率** | ≥55% | ≥65% | ≥75% |
| **假信号率** | ≤35% | ≤25% | ≤20% |
| **多框架共振准确率** | ≥60% | ≥70% | ≥80% |

### 3.2 测量定义

```python
def is_sr_prediction_correct(
    sr_zone: SRZone,
    price_history: List[float],
    atr: float
) -> bool:
    """
    S/R 预测成功的定义:

    条件 1: 价格触及 S/R Zone
      - 触及定义: |price - zone.price_center| < ATR * 0.3

    条件 2: 在 3 根 K 线内反弹
      - 反弹定义: 价格变化 ≥ 0.5%

    条件 3: 未在 6 根 K 线内突破
      - 突破定义: 收盘价穿越 zone.price_center ± ATR * 0.5

    Returns:
        True if all conditions met (成功预测)
        False otherwise (失败预测)
    """
    # 条件 1: 触及
    touch_threshold = atr * 0.3
    touched = any(
        abs(price - sr_zone.price_center) < touch_threshold
        for price in price_history[:3]
    )
    if not touched:
        return None  # 未触及，不计入统计

    # 条件 2: 反弹
    touch_price = price_history[0]
    max_bounce = max(
        abs(price - touch_price) / touch_price
        for price in price_history[1:4]
    )
    bounced = max_bounce >= 0.005  # 0.5%

    # 条件 3: 未突破
    break_threshold = atr * 0.5
    broke_through = any(
        abs(close - sr_zone.price_center) > break_threshold
        for close in price_history[1:7]  # 6 根 K 线
    )

    return bounced and not broke_through


def calculate_sr_accuracy(predictions: List[Dict]) -> Dict:
    """
    计算 S/R 准确率

    Returns:
        {
            'total_predictions': int,
            'touched': int,
            'correct': int,
            'accuracy': float,  # correct / touched
            'false_positive_rate': float  # 假信号率
        }
    """
    touched = [p for p in predictions if p['result'] is not None]
    correct = [p for p in touched if p['result'] == True]

    return {
        'total_predictions': len(predictions),
        'touched': len(touched),
        'correct': len(correct),
        'accuracy': len(correct) / len(touched) if touched else 0,
        'false_positive_rate': 1 - (len(correct) / len(touched)) if touched else 0
    }
```

### 3.3 强度分级标准

| 强度等级 | 条件 | 预期准确率 |
|---------|------|-----------|
| **STRONG** | Order Wall + 多框架共振 + Volume 确认 | ≥75% |
| **MEDIUM** | 2+ 指标共振 | 60-75% |
| **WEAK** | 单一指标 | 50-60% |

---

## 四、交易绩效标准 (核心)

### 4.0 盈利模式核心理念

> **靠概率和盈亏比盈利，盈亏比由 AI 根据市场结构动态决定**

```
期望收益 = 胜率 × 平均盈利 - (1-胜率) × 平均亏损

关键: 盈亏比不是固定值，而是 AI 根据 S/R 价位动态选择
```

### 4.1 架构设计: 本地 vs AI 职责划分

> **参考: [TradingAgents](https://github.com/TauricResearch/TradingAgents) (UCLA/MIT)**
>
> **核心原则: 本地做数据预处理，AI 做分析决策**

```
┌─────────────────────────────────────────────────────────────────────┐
│  本地职责 (数据层)                                                   │
│  ├─ 数据获取: K线、订单流、订单簿、情绪数据                         │
│  ├─ 预处理: 计算技术指标、识别 S/R Zone、格式化数据                 │
│  ├─ 结构化输出: 按 AI 可读格式组织数据                              │
│  │                                                                  │
│  │  ❌ 不做: 行情分类、交易决策、SL/TP 计算                        │
│  └─ 文件: sr_zone_calculator.py, indicator_manager.py               │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ 结构化数据
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  AI 职责 (决策层)                                                    │
│  ├─ 分析: 判断行情类型、趋势方向、市场情绪                          │
│  ├─ 决策: 交易方向 (LONG/SHORT/HOLD)、信心等级                      │
│  ├─ 风险管理: 根据 S/R 价位选择 SL/TP                               │
│  │                                                                  │
│  │  ✅ AI 看到 S/R 价位列表，自己选择止盈止损目标                   │
│  └─ 文件: multi_agent_analyzer.py (提示词引导)                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 S/R Zone 本地预处理

> **本地只负责识别和格式化 S/R Zone，由 AI 决定如何使用**

#### 4.2.1 本地输出格式 (sr_zone_calculator.py)

```python
# 本地预处理输出的数据结构
sr_zones = {
    "resistance_zones": [
        {
            "price_center": 76000.0,      # 价格中心
            "strength": "WEAK",            # 强度: STRONG/MEDIUM/WEAK
            "sources": ["swing_high"],     # 识别来源
            "level": "R1",                 # 阻力位标签
            "distance_pct": 1.3            # 距当前价格百分比
        },
        {
            "price_center": 78000.0,
            "strength": "MEDIUM",
            "sources": ["fib_level", "order_wall"],
            "level": "R2",
            "distance_pct": 4.0
        }
    ],
    "support_zones": [
        {
            "price_center": 74000.0,
            "strength": "WEAK",
            "sources": ["swing_low"],
            "level": "S1",
            "distance_pct": 1.3
        }
    ],
    "current_price": 75000.0,
    "atr": 800.0
}
```

#### 4.2.2 设计原则

> **来自 `sr_zone_calculator.py` 的设计文档:**

```
设计原则:
- 只做预处理，不做交易判断
- 输出结构化数据，让 AI 解读
- 硬风控只在 HIGH strength 时介入 (极端情况)
```

| 本地做 | 本地不做 |
|-------|---------|
| 识别 S/R Zone 位置 | ❌ 判断行情类型 (一般/极端) |
| 计算 S/R 强度 (STRONG/MEDIUM/WEAK) | ❌ 选择止盈目标 |
| 格式化数据给 AI | ❌ 计算具体 SL/TP 价格 |
| 计算距当前价格的距离 | ❌ 决定仓位大小 |

### 4.3 Bull/Bear 辩论机制 (TradingAgents 核心)

> **参考: [TradingAgents](https://github.com/TauricResearch/TradingAgents) Researcher Team**
>
> **核心原则: 对抗性辩论，强制更严格的分析**

#### 4.3.1 辩论流程 (multi_agent_analyzer.py)

```
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 1: Bull/Bear Debate (2 AI calls per round)                   │
│                                                                     │
│  Round 1:                                                           │
│  ├─ Bull Analyst: 分析数据，构建做多论据                            │
│  ├─ Bear Analyst: 反驳多头观点，构建做空论据                        │
│  │                                                                  │
│  Round 2 (可配置):                                                   │
│  ├─ Bull: 回应空头论据，强化多头立场                                │
│  └─ Bear: 进一步挑战，指出风险                                      │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ debate_transcript
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 2: Judge Decision (1 AI call)                                │
│                                                                     │
│  "Avoid defaulting to HOLD simply because both sides have valid     │
│   points; commit to a stance grounded in the debate's strongest     │
│   arguments."                                                       │
│                                                                     │
│  输出: LONG / SHORT / HOLD + rationale + acknowledged_risks         │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 3: Risk Evaluation (1 AI call)                               │
│                                                                     │
│  根据 Judge 决策 + S/R Zones 选择:                                  │
│  ├─ stop_loss: 基于最近 S/R 价位                                    │
│  ├─ take_profit: 基于目标 S/R 价位                                  │
│  └─ position_size: 基于风险和信心                                   │
└─────────────────────────────────────────────────────────────────────┘
```

#### 4.3.2 Bull/Bear Prompt 设计

**Bull Analyst:**
```
You are a professional Bull Analyst for {symbol}.
Your role is to analyze raw market data and build the strongest
possible case for going LONG.

TASK: Counter the bear's argument and strengthen your case...
```

**Bear Analyst:**
```
You are a professional Bear Analyst for {symbol}.
Your role is to analyze raw market data and build the strongest
possible case AGAINST going LONG.

TASK: Counter the bull's argument. Identify weaknesses and risks...
```

**Judge (Portfolio Manager):**
```
As the portfolio manager and debate facilitator, your role is to
critically evaluate this round of debate and make a definitive
decision: align with the bear analyst, the bull analyst, or choose
HOLD only if it is strongly justified.

Avoid defaulting to HOLD simply because both sides have valid points;
commit to a stance grounded in the debate's strongest arguments.
```

#### 4.3.3 为什么需要辩论机制

| 对比项 | 单一 AI 分析 | Bull/Bear 辩论 |
|-------|-------------|---------------|
| **偏见控制** | 可能偏向某一方 | 强制考虑对立观点 |
| **风险识别** | 可能忽略风险 | Bear 专门挑战风险 |
| **决策质量** | 依赖单一视角 | 多视角综合评估 |
| **HOLD 比例** | 可能过度保守 | Judge 被引导做出决定 |

### 4.4 Risk Manager 提示词引导

> **原则: 通过 prompt 引导 AI 利用数据，而不是本地写 if-else 规则**

#### 4.4.1 当前 AI 提示词 (multi_agent_analyzer.py)

```
YOUR TASK:
1. Review the trading decision from the Judge

2. Determine stop loss using S/R zones as reference:
   - For LONG: Place SL below nearest SUPPORT zone
   - For SHORT: Place SL above nearest RESISTANCE zone
   - Use the zone's strength to adjust buffer (stronger zone = tighter SL)

3. Determine take profit using S/R zones as reference:
   - For LONG: Target nearest RESISTANCE zone as TP
   - For SHORT: Target nearest SUPPORT zone as TP
   - Consider the zone's strength and distance

4. Calculate position size based on:
   - Risk per trade (use SL distance to calculate)
   - Account for zone strength in confidence
```

#### 4.4.2 为什么这是正确的架构

| 对比项 | 本地硬编码规则 ❌ | AI 提示词引导 ✅ |
|-------|-----------------|----------------|
| 行情分类 | `if price_change > 3%:` | AI 综合判断趋势方向和力度 |
| TP 选择 | `target_sr = sr_levels[0]` | AI 根据市场结构自行选择 |
| 异常处理 | `else: return FALLBACK` | AI 根据上下文灵活处理 |
| 可扩展性 | 每种情况都要写代码 | 修改 prompt 即可 |

#### 4.4.3 AI 决策自由度

> **AI 看到 S/R Zone 列表后，可以自由决定:**

| 决策项 | AI 自主判断 |
|-------|-----------|
| **行情类型** | 根据技术指标、订单流、情绪数据综合判断 |
| **TP 目标** | 选择最近的、更远的、或更强的 S/R |
| **SL 位置** | 根据支撑强度选择缓冲大小 |
| **盈亏比** | 动态计算，不设固定阈值 |
| **特殊处理** | 极端行情、无 S/R 数据等情况自行判断 |

### 4.5 核心绩效指标 (结果导向)

> **评估只看结果，不规定 AI 如何决策**

| 指标 | 定义 | 目标改进 | 最低接受 |
|-----|------|---------|---------|
| **胜率 (Win Rate)** | 盈利交易 / 总交易 | +5% | 不低于基准 |
| **盈亏比 (R:R)** | 平均盈利 / 平均亏损 (动态) | +20% | +10% |
| **最大回撤 (MDD)** | 最大峰谷跌幅 | -10% | 不高于基准 |
| **Sharpe Ratio** | (收益-无风险) / 波动率 | +0.2 | 不低于基准 |
| **Profit Factor** | 总盈利 / 总亏损 | +15% | +5% |
| **极端行情捕获率** | 极端行情盈利次数 / 极端行情交易次数 | ≥50% | ≥40% |

### 4.6 盈亏比分布分析

> **这是评估工具，不是决策逻辑**

```python
def analyze_risk_reward_distribution(trades: List[Trade]) -> Dict:
    """
    分析盈亏比分布，验证动态止盈效果
    """
    # 按行情类型分组
    normal_trades = [t for t in trades if t.market_condition == 'NORMAL']
    extreme_trades = [t for t in trades if 'EXTREME' in t.market_condition]

    # 计算各组盈亏比
    def calc_rr(trade_list):
        wins = [t for t in trade_list if t.pnl > 0]
        losses = [t for t in trade_list if t.pnl < 0]
        avg_win = sum(t.pnl_pct for t in wins) / len(wins) if wins else 0
        avg_loss = abs(sum(t.pnl_pct for t in losses) / len(losses)) if losses else 1
        return avg_win / avg_loss if avg_loss > 0 else 0

    return {
        'normal_rr': calc_rr(normal_trades),      # 目标: 1.2-1.5
        'extreme_rr': calc_rr(extreme_trades),    # 目标: 2.5-4.0
        'overall_rr': calc_rr(trades),
        'extreme_trade_pct': len(extreme_trades) / len(trades) if trades else 0,
    }

# 参考值 (非硬性要求，AI 可根据市场情况灵活调整):
# - 正常行情盈亏比: 参考 1.2-1.5
# - 极端行情盈亏比: 参考 2.5-4.0 (顺势交易)
# - 极端行情占比: 参考 10-20%
# 注意: 这些是评估参考，不是 AI 必须达到的目标
```

```python
def calculate_trading_metrics(trades: List[Trade]) -> Dict:
    """
    计算交易绩效指标
    """
    if not trades:
        return {}

    # 基础统计
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]

    # 胜率
    win_rate = len(wins) / len(trades) if trades else 0

    # 盈亏比
    avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t.pnl for t in losses) / len(losses)) if losses else 1
    risk_reward = avg_win / avg_loss if avg_loss > 0 else 0

    # Profit Factor
    total_profit = sum(t.pnl for t in wins)
    total_loss = abs(sum(t.pnl for t in losses))
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

    # 最大回撤
    cumulative = []
    running_total = 0
    for t in trades:
        running_total += t.pnl
        cumulative.append(running_total)

    peak = cumulative[0]
    max_drawdown = 0
    for value in cumulative:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak if peak > 0 else 0
        max_drawdown = max(max_drawdown, drawdown)

    # Sharpe Ratio (简化版，假设无风险利率=0)
    returns = [t.pnl_pct for t in trades]
    avg_return = sum(returns) / len(returns)
    std_return = (sum((r - avg_return)**2 for r in returns) / len(returns)) ** 0.5
    sharpe = avg_return / std_return if std_return > 0 else 0

    return {
        'total_trades': len(trades),
        'win_rate': win_rate,
        'risk_reward': risk_reward,
        'profit_factor': profit_factor,
        'max_drawdown': max_drawdown,
        'sharpe_ratio': sharpe,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
    }
```

### 4.7 样本量要求

| 要求 | 最小值 | 推荐值 | 原因 |
|-----|-------|-------|------|
| **交易次数** | ≥50 次/组 | ≥100 次/组 | 统计显著性 |
| **时间跨度** | ≥14 天 | ≥30 天 | 覆盖不同市场状态 |
| **牛市天数** | ≥5 天 | ≥10 天 | 避免偏差 |
| **熊市天数** | ≥5 天 | ≥10 天 | 避免偏差 |
| **震荡天数** | ≥5 天 | ≥10 天 | 避免偏差 |

### 4.8 统计显著性检验

```python
from scipy import stats

def is_improvement_significant(
    control_results: List[float],
    experiment_results: List[float],
    alpha: float = 0.05
) -> Dict:
    """
    检验实验组是否显著优于对照组

    使用 Welch's t-test (不假设等方差)
    """
    t_stat, p_value = stats.ttest_ind(
        experiment_results,
        control_results,
        equal_var=False
    )

    # 单尾检验 (实验组 > 对照组)
    p_value_one_tail = p_value / 2 if t_stat > 0 else 1 - p_value / 2

    return {
        't_statistic': t_stat,
        'p_value': p_value_one_tail,
        'is_significant': p_value_one_tail < alpha,
        'confidence_level': 1 - alpha,
        'conclusion': '实验组显著优于对照组' if p_value_one_tail < alpha else '无显著差异'
    }
```

---

### 4.9 行业实践调研

#### 4.9.1 调研结论

> **基于 S/R 价位设置止盈止损是专业交易的主流做法**

| 方法 | 使用者 | 优点 | 缺点 |
|-----|-------|------|------|
| **固定百分比** | 散户、简单策略 | 简单易用 | 不考虑市场结构 |
| **S/R 价位** | 机构、专业交易者 | 符合市场心理 | 实现复杂 |

#### 4.9.2 机构观点

**Analyzing Alpha (机构交易研究)**:
> "The institutional trader at the margin determines most securities' prices and the support and resistance levels... Institutions have target buy and sell prices for every security."

机构交易者为每个持仓设定目标买入/卖出价位，这些价位通常就是 S/R 水平。

**D.E. Shaw (量化基金巨头)**:
> "Stop-losses are set in advance, which accounts for the staleness, and they are a function of only **one form of information – price**."

David Shaw 认为固定止损的问题是**信息单一且陈旧**，支持动态/结构化止损。

#### 4.9.3 主流平台实现

| 平台 | S/R 功能 | 备注 |
|-----|---------|------|
| **3Commas** | "Placing SL/TP based on key S/R levels... These levels often act as price barriers" | 交易机器人平台 |
| **TradingView** | AI 指标验证 S/R 区域 | 图表分析平台 |
| **ATAS** | 专业订单流 + S/R 分析 | 机构级工具 |
| **Pionex** | Grid Bot 上下限基于 S/R | 网格交易 |

#### 4.9.4 学术研究支持

[MDPI 论文 - S/R Levels in Algorithmic Trading](https://www.mdpi.com/2227-7390/10/20/3888):
使用神经网络学习 S/R 与价格运动的关系，证明了 S/R 对交易决策的价值。

#### 4.9.5 最佳实践建议

来自 [Algorithmic Trading Library](https://algotradinglib.com/en/pedia/d/dynamic_stop-loss_strategies.html):

| 实践 | 说明 |
|-----|------|
| **缓冲区** | "Place stops 0.5-1.0 ATR beyond the S/R zone" |
| **多时间框架** | "Use larger time frames (daily/4H) for significant S/R, smaller for entries" |
| **动态调整** | "Adaptive algorithms adjust stop parameters based on changing market conditions" |

#### 4.9.6 我们的方案定位

| 对比项 | 散户工具 (如 Pionex) | 我们的方案 | 机构标准 |
|-------|---------------------|-----------|---------|
| 止盈止损 | 固定百分比或网格 | S/R 价位 + 行情动态调整 | S/R 价位 + 多因子 |
| 极端行情 | 无特殊处理 | 顺势放大止盈 | 风险模型调整 |
| 数据来源 | 单一指标 | 多层 S/R + 订单流 | 多层 S/R + 订单流 + 私有数据 |

**结论**: 我们的方案符合专业交易标准，超越大多数散户交易机器人。

#### 4.9.7 参考资料

- [Analyzing Alpha - Support and Resistance](https://analyzingalpha.com/support-and-resistance)
- [Quantified Strategies - Stop Loss Strategy](https://www.quantifiedstrategies.com/stop-loss-trading-strategy/)
- [3Commas - Advanced Stop-Loss Logic 2025](https://3commas.io/blog/optimizing-your-trades-advanced-stop-loss-and-take)
- [Algorithmic Trading Library - Dynamic Stop-Loss](https://algotradinglib.com/en/pedia/d/dynamic_stop-loss_strategies.html)
- [MDPI - S/R Levels in Algorithmic Trading](https://www.mdpi.com/2227-7390/10/20/3888)

---

## 五、AI 决策质量标准

### 5.1 信号质量指标

| 指标 | 目标 | 测量方法 |
|-----|------|---------|
| **HOLD 信号比例** | 减少 20% | 对比新旧系统 |
| **信号一致性** | ≥70% | 相同数据重复测试 |
| **HIGH confidence 胜率** | ≥60% | 高信心信号的实际胜率 |
| **信号变化频率** | 合理范围 | 避免过度交易或过度保守 |

### 5.2 历史上下文利用率

```python
def analyze_ai_reasoning(reasoning_text: str) -> Dict:
    """
    分析 AI 是否实际使用了历史数据上下文

    检查关键词:
    - 趋势类: 趋势, trend, rising, falling, increasing, decreasing
    - 历史类: 连续, consecutive, previous, 之前, 历史
    - 变化类: 变化, change, shift, 转变
    - 比较类: 相比, compared, versus, vs
    """
    text_lower = reasoning_text.lower()

    trend_keywords = ['趋势', 'trend', 'rising', 'falling', 'increasing',
                      'decreasing', 'upward', 'downward', '上升', '下降']
    history_keywords = ['连续', 'consecutive', 'previous', '之前', '历史',
                        'earlier', 'past', '前']
    change_keywords = ['变化', 'change', 'shift', '转变', 'moved', 'shifted']
    compare_keywords = ['相比', 'compared', 'versus', 'vs', '对比', 'than']

    uses_trend = any(kw in text_lower for kw in trend_keywords)
    uses_history = any(kw in text_lower for kw in history_keywords)
    uses_change = any(kw in text_lower for kw in change_keywords)
    uses_compare = any(kw in text_lower for kw in compare_keywords)

    utilization_score = sum([uses_trend, uses_history, uses_change, uses_compare])

    return {
        'uses_trend': uses_trend,
        'uses_history': uses_history,
        'uses_change': uses_change,
        'uses_compare': uses_compare,
        'utilization_score': utilization_score,  # 0-4
        'utilizes_context': utilization_score >= 1
    }

# 目标: ≥60% 的 AI 决策 utilizes_context == True
```

### 5.3 决策质量分级

| 质量等级 | 条件 | 预期比例 |
|---------|------|---------|
| **优秀** | 使用 3+ 类上下文关键词 | ≥20% |
| **良好** | 使用 1-2 类上下文关键词 | ≥40% |
| **一般** | 未明确使用上下文 | ≤40% |

---

## 六、风险控制标准

### 6.0 风险控制核心理念

> **极端行情是机会，关键是 AI 识别方向和控制风险**

```
核心原则:
- 行情分类由 AI 判断，不是本地硬编码 3% 阈值
- SL/TP 调整由 AI 决定，基于 S/R Zone 数据
- 本地只提供数据，AI 做风险决策
```

### 6.1 AI 风险管理职责

> **Risk Manager 提示词引导 AI 处理风险:**

```
Risk Manager 的职责 (multi_agent_analyzer.py):
1. 评估市场风险水平
2. 根据 S/R Zone 选择 SL/TP 价位
3. 根据信心和风险调整仓位大小
4. 考虑当前市场条件 (订单流、情绪、波动率)

AI 自主判断:
- 当前是否为极端行情
- 顺势还是逆势交易
- SL/TP 应该收紧还是放大
- 仓位应该增加还是减少
```

### 6.2 本地数据支持 (供 AI 决策)

| 数据类型 | 本地提供 | AI 用途 |
|---------|---------|--------|
| **波动率数据** | ATR, 近期价格变化 | 判断市场状态 |
| **S/R Zone** | 价位、强度、来源 | 选择 SL/TP 目标 |
| **订单流** | Buy/Sell Ratio, CVD | 判断资金流向 |
| **情绪数据** | Long/Short Ratio | 判断市场情绪 |

### 6.3 异常场景处理 (本地降级)

> **这些是本地系统的异常处理，不是交易决策**

| 风险场景 | 本地处理 | 说明 |
|---------|---------|------|
| **S/R 数据缺失** | 标记 `sr_available: false`，告知 AI | AI 自行决定是否交易 |
| **历史数据不足** | 标记 `data_quality: low`，告知 AI | AI 可降低信心 |
| **API 超时** | 使用缓存数据，标记 `data_stale: true` | AI 可选择观望 |
| **订单簿异常** | 提供异常指标，AI 决定仓位 | 不硬编码减仓逻辑 |

### 6.4 安全边界 (硬风控)

| 参数 | 硬限制 | 原因 |
|-----|-------|------|
| **最大止损** | ≤5% | 防止单笔巨亏 |
| **最小止损** | ≥0.5% | 避免被噪音止损 |
| **最大止盈** | ≤10% | 即使极端行情也有上限 |
| **最小止盈** | ≥0.5% | 覆盖手续费 |
| **最小仓位** | ≥10% 标准仓位 | 保持参与度 |
| **逆势最大仓位** | ≤50% 标准仓位 | 控制逆势风险 |

---

## 七、评估时间线

```
┌─────────────────────────────────────────────────────────────┐
│  Week 1-2: 技术实现 + 单元测试                               │
│  ├─ 目标: 完成代码实现                                       │
│  ├─ 评估: 技术实现标准 (Section 二)                         │
│  ├─ 产出: 功能完成，所有测试通过                             │
│  └─ 里程碑: 代码合并到 main 分支                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Week 3-4: 数据收集 (模拟/纸交易)                            │
│  ├─ 目标: 收集 S/R 预测数据                                 │
│  ├─ 评估: S/R 准确性标准 (Section 三)                       │
│  ├─ 产出: 初步准确率报告                                     │
│  └─ 决策点: 准确率 ≥55% 继续，否则优化                      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Week 5-8: 实盘测试 (小资金)                                 │
│  ├─ 目标: 验证新系统绩效                                     │
│  ├─ 评估: 交易绩效标准 (Section 四)                         │
│  ├─ 样本: ≥50 次交易                                        │
│  ├─ 产出: 绩效报告                                          │
│  └─ 决策点: 达到最低接受标准继续                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Week 9-12: 扩展测试 + 优化                                  │
│  ├─ 目标: 增加样本量，优化参数                               │
│  ├─ 评估: 所有标准                                          │
│  ├─ 样本: ≥100 次交易/组                                    │
│  ├─ 产出: 完整评估报告                                       │
│  └─ 决策点: 全面上线 / 继续优化 / 回滚                      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Week 13+: 全面上线或回滚                                    │
│  ├─ 条件: 达到所有最低接受标准                               │
│  ├─ 监控: 持续跟踪绩效指标                                   │
│  └─ 迭代: 根据数据持续优化                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 八、评估报告模板

```markdown
# S/R 强度 + 历史数据上下文 评估报告

## 基本信息
- **测试周期**: YYYY-MM-DD 至 YYYY-MM-DD
- **测试阶段**: Phase X (Week Y-Z)
- **测试环境**: 模拟/小资金实盘/全资金实盘

## 一、技术实现评估

| 指标 | 目标 | 实际 | 状态 |
|-----|------|------|------|
| 数据完整性 | ≥95% | __% | ✅/❌ |
| 持久化可靠性 | ≥95% | __% | ✅/❌ |
| 处理延迟 | <100ms | __ms | ✅/❌ |
| 内存增量 | <50MB | __MB | ✅/❌ |

**技术评估结论**: 通过 / 需改进

## 二、S/R 准确性评估

| 指标 | 目标 | 实际 | 状态 |
|-----|------|------|------|
| 强阻力识别率 | ≥__% | __% | ✅/❌ |
| 强支撑识别率 | ≥__% | __% | ✅/❌ |
| 假信号率 | ≤__% | __% | ✅/❌ |
| 多框架共振准确率 | ≥__% | __% | ✅/❌ |

**样本量**: __ 次 S/R 预测
**准确性评估结论**: 通过 / 需改进

## 三、交易绩效评估

### 3.1 绩效数据
- 交易次数: __
- 胜率: __%
- 盈亏比: __
- 最大回撤: __%
- Sharpe Ratio: __
- Profit Factor: __

### 3.2 分行情类型统计 (AI 判断)
| 行情类型 | 交易次数 | 胜率 | 平均盈亏比 |
|---------|---------|------|-----------|
| 正常行情 | __ | __% | __ |
| 极端行情 (顺势) | __ | __% | __ |
| 极端行情 (逆势) | __ | __% | __ |

**绩效评估结论**: 通过 / 需改进

## 四、AI 决策质量评估

| 指标 | 目标 | 实际 | 状态 |
|-----|------|------|------|
| HOLD 信号比例变化 | -20% | __% | ✅/❌ |
| 信号一致性 | ≥70% | __% | ✅/❌ |
| HIGH confidence 胜率 | ≥60% | __% | ✅/❌ |
| 历史上下文利用率 | ≥60% | __% | ✅/❌ |

**AI 质量评估结论**: 通过 / 需改进

## 五、风险控制评估

| 场景 | 测试次数 | 正确处理 | 成功率 |
|-----|---------|---------|-------|
| 极端波动回退 | __ | __ | __% |
| S/R 数据缺失 | __ | __ | __% |
| 历史数据不足 | __ | __ | __% |
| 连续亏损处理 | __ | __ | __% |

**风险控制评估结论**: 通过 / 需改进

## 六、总体结论

### 6.1 各维度评估汇总

| 维度 | 状态 | 备注 |
|-----|------|------|
| 技术实现 | ✅/❌ | |
| S/R 准确性 | ✅/❌ | |
| 交易绩效 | ✅/❌ | |
| AI 决策质量 | ✅/❌ | |
| 风险控制 | ✅/❌ | |

### 6.2 决策建议

- [ ] **全面上线**: 所有指标达标，建议全面启用
- [ ] **继续优化**: 部分指标达标，建议优化后重新测试
- [ ] **回滚**: 多项指标未达标，建议回滚到原系统

### 6.3 后续行动

1. __________________
2. __________________
3. __________________

## 附录

### A. 详细交易记录
(附表或链接)

### B. S/R 预测详细数据
(附表或链接)

### C. AI 决策样本分析
(附表或链接)

---
报告生成时间: YYYY-MM-DD HH:MM:SS
报告人: __________
```

---

## 九、指标速查表

| 维度 | 核心指标 | 最低接受 | 目标值 |
|-----|---------|---------|-------|
| **技术** | 数据完整性 | ≥95% | 100% |
| **技术** | 处理延迟 | <100ms | <50ms |
| **准确性** | S/R 识别率 | ≥55% | ≥75% |
| **准确性** | 假信号率 | ≤35% | ≤20% |
| **绩效** | 胜率变化 | ≥0% | +5% |
| **绩效** | 盈亏比变化 | +5% | +15% |
| **绩效** | 最大回撤 | 不高于基准 | -10% |
| **AI** | 上下文利用率 | ≥50% | ≥70% |
| **风险** | 异常处理成功率 | 100% | 100% |
| **样本** | 最小交易次数 | ≥50次 | ≥100次 |
| **样本** | 最小测试天数 | ≥14天 | ≥30天 |

---

## 十、参考资料

### 项目文档
- S/R 强度研究报告: [SR_STRENGTH_RESEARCH.md](./SR_STRENGTH_RESEARCH.md)

### 学术研究
- Cont et al. (2014). The Price Impact of Order Book Events
- [MDPI - S/R Levels in Algorithmic Trading](https://www.mdpi.com/2227-7390/10/20/3888)

### 行业实践
- [Analyzing Alpha - Support and Resistance](https://analyzingalpha.com/support-and-resistance)
- [Quantified Strategies - Stop Loss Strategy](https://www.quantifiedstrategies.com/stop-loss-trading-strategy/)
- [3Commas - Advanced Stop-Loss Logic 2025](https://3commas.io/blog/optimizing-your-trades-advanced-stop-loss-and-take)
- [Algorithmic Trading Library - Dynamic Stop-Loss](https://algotradinglib.com/en/pedia/d/dynamic_stop-loss_strategies.html)

### 工具
- 12-Factor App Configuration: https://12factor.net/config
- A/B Testing Calculator: https://www.evanmiller.org/ab-testing/

---

**文档版本**: v2.1
**创建日期**: 2026-02-02
**最后更新**: 2026-02-02
**更新历史**:
- v2.1: 添加 Bull/Bear 辩论机制描述 (4.3)，明确验收标准是参考值而非硬性要求
- v2.0: **重大重构** - 按 TradingAgents 架构重写，明确本地 vs AI 职责划分
  - 移除所有本地硬编码决策规则 (classify_market_condition, calculate_dynamic_tp 等)
  - 移除 A/B 测试对照组设计，改为直接实施
  - 第四章改为描述正确的架构 (本地预处理 + AI 决策)
  - 第六章简化为 AI 风险管理职责描述
- v1.2: 添加行情分类标准 (4.2.2)、完整决策流程图 (4.2.7)、修正章节编号
- v1.1: 添加行业实践调研章节 (4.7)
