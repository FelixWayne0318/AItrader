# S/R 强度 + 历史数据上下文 评估框架

**日期**: 2026-02-02
**状态**: 评估标准定义 (实施前)
**版本**: v3.0 (世界顶级量化标准)
**关联文档**: [SR_STRENGTH_RESEARCH.md](./SR_STRENGTH_RESEARCH.md)

> **v3.0 重大更新**: 按 Renaissance/Two Sigma/Citadel 级别标准重构
> - 修正 Sharpe Ratio 计算（年化 + 样本标准差 + 无风险利率）
> - 修正 Maximum Drawdown 计算（基于净值曲线）
> - 新增 Sortino/Calmar Ratio、VaR/CVaR
> - 新增交易成本建模、Walk-Forward 验证、策略衰减检测
> - 样本量要求从 50 次提升到 200+ 次

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
import numpy as np
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class Trade:
    """交易记录结构"""
    pnl: float              # 绝对盈亏 (USDT)
    pnl_pct: float          # 百分比盈亏
    entry_time: datetime
    exit_time: datetime
    market_condition: str   # 'NORMAL', 'EXTREME_BULL', 'EXTREME_BEAR'
    holding_period_hours: float


def calculate_trading_metrics(
    trades: List[Trade],
    initial_capital: float,
    risk_free_rate: float = 0.045,  # 年化无风险利率 (当前美债 ~4.5%)
    trading_days_per_year: int = 365,  # 加密货币 24/7
) -> Dict:
    """
    计算交易绩效指标 (世界顶级量化标准)

    参考:
    - Sharpe (1994): The Sharpe Ratio
    - Sortino & Price (1994): Performance Measurement in a Downside Risk Framework
    - Young (1991): Calmar Ratio

    Args:
        trades: 交易记录列表
        initial_capital: 初始资金
        risk_free_rate: 年化无风险利率 (默认 4.5%)
        trading_days_per_year: 年交易天数 (加密货币=365)
    """
    if not trades or len(trades) < 2:
        return {'error': '样本量不足，至少需要 2 笔交易'}

    n = len(trades)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]

    # ============================================================
    # 1. 基础统计
    # ============================================================
    win_rate = len(wins) / n
    avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t.pnl for t in losses) / len(losses)) if losses else 1
    risk_reward = avg_win / avg_loss if avg_loss > 0 else 0

    # Profit Factor
    total_profit = sum(t.pnl for t in wins)
    total_loss = abs(sum(t.pnl for t in losses))
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

    # ============================================================
    # 2. 净值曲线 (Equity Curve) - 用于回撤计算
    # ============================================================
    equity_curve = [initial_capital]
    for t in trades:
        equity_curve.append(equity_curve[-1] + t.pnl)

    # ============================================================
    # 3. Maximum Drawdown (正确计算)
    # ============================================================
    running_max = equity_curve[0]
    max_drawdown = 0
    max_drawdown_duration = 0
    current_drawdown_start = 0

    for i, value in enumerate(equity_curve):
        if value > running_max:
            running_max = value
            current_drawdown_start = i

        if running_max > 0:
            dd = (running_max - value) / running_max
            if dd > max_drawdown:
                max_drawdown = dd
                max_drawdown_duration = i - current_drawdown_start

    # ============================================================
    # 4. 收益率序列 (用于风险调整指标)
    # ============================================================
    returns = np.array([t.pnl_pct / 100 for t in trades])  # 转换为小数

    # 计算交易频率 (用于年化)
    total_days = (trades[-1].exit_time - trades[0].entry_time).days or 1
    trades_per_day = n / total_days
    annualization_factor = np.sqrt(trades_per_day * trading_days_per_year)

    # 日化无风险利率
    rf_per_trade = risk_free_rate / (trades_per_day * trading_days_per_year)

    # ============================================================
    # 5. Sharpe Ratio (正确计算 - 年化)
    #
    # 公式: SR = (E[R] - Rf) / σ(R) * √(trades_per_year)
    # 使用样本标准差 (n-1)
    # ============================================================
    excess_returns = returns - rf_per_trade
    avg_excess_return = np.mean(excess_returns)
    std_excess_return = np.std(excess_returns, ddof=1)  # 样本标准差 (n-1)

    sharpe_ratio = 0
    if std_excess_return > 0:
        sharpe_ratio = (avg_excess_return / std_excess_return) * annualization_factor

    # ============================================================
    # 6. Sortino Ratio (只惩罚下行波动)
    #
    # 公式: Sortino = (E[R] - Rf) / σ_downside * √(trades_per_year)
    # σ_downside = sqrt(E[min(R-Rf, 0)²])
    # ============================================================
    downside_returns = np.minimum(excess_returns, 0)
    downside_std = np.sqrt(np.mean(downside_returns ** 2))

    sortino_ratio = 0
    if downside_std > 0:
        sortino_ratio = (avg_excess_return / downside_std) * annualization_factor

    # ============================================================
    # 7. Calmar Ratio (收益/最大回撤)
    #
    # 公式: Calmar = 年化收益率 / 最大回撤
    # ============================================================
    total_return = (equity_curve[-1] - initial_capital) / initial_capital
    years = total_days / trading_days_per_year
    annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

    calmar_ratio = 0
    if max_drawdown > 0:
        calmar_ratio = annualized_return / max_drawdown

    # ============================================================
    # 8. 汇总结果
    # ============================================================
    return {
        # 基础统计
        'total_trades': n,
        'win_rate': win_rate,
        'risk_reward': risk_reward,
        'profit_factor': profit_factor,
        'avg_win': avg_win,
        'avg_loss': avg_loss,

        # 风险调整收益 (年化)
        'sharpe_ratio': sharpe_ratio,
        'sortino_ratio': sortino_ratio,
        'calmar_ratio': calmar_ratio,

        # 风险指标
        'max_drawdown': max_drawdown,
        'max_drawdown_duration_trades': max_drawdown_duration,

        # 收益指标
        'total_return': total_return,
        'annualized_return': annualized_return,

        # 元数据
        'annualization_factor': annualization_factor,
        'risk_free_rate_used': risk_free_rate,
    }
```

### 4.7 样本量要求 (v3.0 更新)

> **v3.0 重大更新**: 基于统计功效分析 (Power Analysis) 重新计算样本量

#### 4.7.1 统计功效分析

```python
def calculate_required_sample_size(
    effect_size: str = 'medium',  # 'small', 'medium', 'large'
    alpha: float = 0.05,          # Type I error rate
    power: float = 0.80,          # 统计功效 (1 - Type II error)
) -> Dict:
    """
    计算达到指定统计功效所需的样本量

    Cohen's d 效应量标准:
    - small: d = 0.2 (如 2% 胜率提升)
    - medium: d = 0.5 (如 5% 胜率提升)
    - large: d = 0.8 (如 10% 胜率提升)

    参考: Cohen (1988). Statistical Power Analysis for the Behavioral Sciences
    """
    # Cohen's d 对应的效应量
    effect_sizes = {'small': 0.2, 'medium': 0.5, 'large': 0.8}
    d = effect_sizes.get(effect_size, 0.5)

    # Z 值
    z_alpha = 1.96 if alpha == 0.05 else 2.58  # 双尾
    z_beta = 0.84 if power == 0.80 else 1.28   # 单尾

    # 公式: n = 2 * ((z_α + z_β) / d)²
    n_per_group = int(2 * ((z_alpha + z_beta) / d) ** 2)

    return {
        'effect_size': effect_size,
        'cohen_d': d,
        'alpha': alpha,
        'power': power,
        'required_n_per_group': n_per_group,
        'interpretation': f'需要 {n_per_group} 笔交易才能检测到 {effect_size} 效应'
    }

# 示例输出:
# - 检测 small 效应 (2% 提升): 需要 ~788 笔交易
# - 检测 medium 效应 (5% 提升): 需要 ~126 笔交易
# - 检测 large 效应 (10% 提升): 需要 ~50 笔交易
```

#### 4.7.2 样本量标准 (更新后)

| 要求 | 最小值 | 推荐值 | 理想值 | 能检测的效应 |
|-----|-------|-------|-------|------------|
| **交易次数** | ≥200 次 | ≥500 次 | ≥1000 次 | medium → small |
| **时间跨度** | ≥30 天 | ≥60 天 | ≥90 天 | 覆盖多种 regime |
| **牛市天数** | ≥10 天 | ≥20 天 | ≥30 天 | 避免偏差 |
| **熊市天数** | ≥10 天 | ≥20 天 | ≥30 天 | 避免偏差 |
| **震荡天数** | ≥10 天 | ≥20 天 | ≥30 天 | 避免偏差 |

#### 4.7.3 为什么 50 次不够？

| 原问题 | 后果 |
|-------|------|
| **统计功效不足** | 只能检测 large 效应 (d > 0.8)，错过中小改进 |
| **Type II Error 高** | 真实有效的策略可能被误判为无效 |
| **置信区间过宽** | 结果不确定性高，无法做出可靠决策 |
| **Regime 覆盖不全** | 50 次交易可能都在同一市场状态下 |

#### 4.7.4 分阶段样本量策略

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: 快速验证 (1-2 周)                                  │
│  ├─ 样本量: 50-100 次                                        │
│  ├─ 目的: 检测严重问题 (large 效应)                          │
│  └─ 决策: 继续 / 紧急回滚                                   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 2: 标准验证 (4-6 周)                                  │
│  ├─ 样本量: 200-500 次                                       │
│  ├─ 目的: 检测显著改进 (medium 效应)                         │
│  └─ 决策: 扩大部署 / 优化参数 / 回滚                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 3: 完整验证 (3+ 月)                                   │
│  ├─ 样本量: 500-1000+ 次                                     │
│  ├─ 目的: 检测微小改进 + 长期稳定性                          │
│  └─ 决策: 全面上线 / 继续优化                               │
└─────────────────────────────────────────────────────────────┘
```

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

### 6.5 VaR/CVaR 尾部风险评估 (v3.0 新增)

> **世界顶级量化标准必备**: 监管机构 (Basel III/IV) 要求的风险指标

```python
import numpy as np
from typing import List, Dict

def calculate_var_cvar(
    returns: List[float],
    confidence_levels: List[float] = [0.95, 0.99],
    method: str = 'historical'  # 'historical', 'parametric', 'cornish_fisher'
) -> Dict:
    """
    计算 VaR (Value at Risk) 和 CVaR (Conditional VaR / Expected Shortfall)

    VaR: 在给定置信水平下，最大可能损失
    CVaR: 当损失超过 VaR 时的平均损失 (更保守的指标)

    参考:
    - Artzner et al. (1999): Coherent Measures of Risk
    - Basel III/IV 监管框架

    Args:
        returns: 收益率序列
        confidence_levels: 置信水平列表
        method: 计算方法
            - 'historical': 历史模拟法 (非参数)
            - 'parametric': 参数法 (假设正态分布)
            - 'cornish_fisher': Cornish-Fisher 展开 (考虑偏度和峰度)
    """
    returns = np.array(returns)
    n = len(returns)

    if n < 30:
        return {'error': 'VaR/CVaR 需要至少 30 个样本点'}

    results = {}

    for conf in confidence_levels:
        alpha = 1 - conf  # 如 95% 置信度 → alpha = 0.05

        if method == 'historical':
            # 历史模拟法: 直接使用分位数
            var = -np.percentile(returns, alpha * 100)
            # CVaR: 低于 VaR 的所有收益的平均值
            cvar = -np.mean(returns[returns <= -var])

        elif method == 'parametric':
            # 参数法: 假设正态分布
            from scipy import stats
            mu = np.mean(returns)
            sigma = np.std(returns, ddof=1)
            z = stats.norm.ppf(alpha)
            var = -(mu + z * sigma)
            # CVaR (正态): E[X | X < VaR] = μ - σ * φ(z) / α
            cvar = -(mu - sigma * stats.norm.pdf(z) / alpha)

        elif method == 'cornish_fisher':
            # Cornish-Fisher 展开: 考虑偏度和峰度
            from scipy import stats
            mu = np.mean(returns)
            sigma = np.std(returns, ddof=1)
            skew = stats.skew(returns)
            kurt = stats.kurtosis(returns)  # excess kurtosis

            z = stats.norm.ppf(alpha)
            # Cornish-Fisher 调整
            z_cf = (z + (z**2 - 1) * skew / 6
                    + (z**3 - 3*z) * (kurt - 3) / 24
                    - (2*z**3 - 5*z) * skew**2 / 36)
            var = -(mu + z_cf * sigma)
            # CVaR 近似
            cvar = var * 1.2  # 简化近似，实际需要数值积分

        results[f'var_{int(conf*100)}'] = var
        results[f'cvar_{int(conf*100)}'] = cvar

    # 风险评级
    var_95 = results.get('var_95', 0)
    if var_95 < 0.02:
        risk_level = 'LOW'
    elif var_95 < 0.05:
        risk_level = 'MEDIUM'
    else:
        risk_level = 'HIGH'

    results['risk_level'] = risk_level
    results['method_used'] = method
    results['sample_size'] = n

    return results

# 目标值:
# - VaR_95 < 3% (95% 置信度下单日最大亏损 < 3%)
# - CVaR_99 < 5% (极端情况下平均亏损 < 5%)
```

### 6.6 交易成本建模 (v3.0 新增)

> **关键**: 不考虑交易成本的回测是不现实的

```python
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class TradingCosts:
    """Binance Futures 交易成本结构"""

    # 手续费 (VIP 0 等级)
    maker_fee: float = 0.0002      # 0.02% 挂单
    taker_fee: float = 0.0004      # 0.04% 吃单

    # 滑点估计 (基于流动性)
    base_slippage: float = 0.0005  # 0.05% 基础滑点
    slippage_per_size: float = 0.0001  # 每 $10k 额外滑点

    # 资金费率 (8小时结算一次)
    avg_funding_rate: float = 0.0001  # 0.01% 平均

    def calculate_per_trade_cost(
        self,
        position_size_usdt: float,
        holding_hours: float = 4,
        is_taker: bool = True
    ) -> Dict:
        """
        计算单笔交易的总成本

        Args:
            position_size_usdt: 仓位大小 (USDT)
            holding_hours: 持仓时间 (小时)
            is_taker: 是否为 Taker 单
        """
        # 手续费 (开仓 + 平仓)
        fee_rate = self.taker_fee if is_taker else self.maker_fee
        fee_cost = fee_rate * 2  # 开仓 + 平仓

        # 滑点 (开仓 + 平仓)
        size_factor = position_size_usdt / 10000
        slippage = (self.base_slippage + self.slippage_per_size * size_factor) * 2

        # 资金费率 (按持仓时间计算)
        funding_periods = holding_hours / 8
        funding_cost = self.avg_funding_rate * funding_periods

        total_cost = fee_cost + slippage + funding_cost

        return {
            'fee_cost': fee_cost,
            'slippage': slippage,
            'funding_cost': funding_cost,
            'total_cost': total_cost,
            'total_cost_pct': total_cost * 100,
            'breakeven_move': total_cost,  # 需要多少价格变动才能盈亏平衡
        }


def adjust_returns_for_costs(
    trades: List[Trade],
    costs: TradingCosts = TradingCosts()
) -> List[Trade]:
    """
    调整收益率以反映真实交易成本

    重要: 所有绩效评估应在扣除成本后进行
    """
    adjusted_trades = []

    for trade in trades:
        cost_info = costs.calculate_per_trade_cost(
            position_size_usdt=trade.position_size,
            holding_hours=trade.holding_period_hours,
            is_taker=True  # 假设都是 Taker
        )

        adjusted_pnl_pct = trade.pnl_pct - cost_info['total_cost_pct']

        adjusted_trade = Trade(
            pnl=trade.pnl - (trade.position_size * cost_info['total_cost']),
            pnl_pct=adjusted_pnl_pct,
            entry_time=trade.entry_time,
            exit_time=trade.exit_time,
            market_condition=trade.market_condition,
            holding_period_hours=trade.holding_period_hours,
        )
        adjusted_trades.append(adjusted_trade)

    return adjusted_trades


# 成本影响示例:
# - 假设每天 3 笔交易，每笔成本 ~0.18%
# - 月成本 = 3 * 30 * 0.18% = 16.2%
# - 这意味着策略需要月收益 > 16.2% 才能盈利

# 目标:
# - 扣除成本后 Sharpe Ratio > 1.0
# - 扣除成本后 Profit Factor > 1.5
```

#### 6.6.1 成本敏感性分析

| 交易频率 | 日交易次数 | 月成本估计 | 最低月收益要求 |
|---------|-----------|-----------|--------------|
| **低频** | 1 次/天 | ~5.4% | >6% |
| **中频** | 3 次/天 | ~16.2% | >18% |
| **高频** | 10 次/天 | ~54% | >60% |

> **结论**: 高频策略对成本极其敏感，必须严格控制交易频率或获得更低的手续费等级。

---

## 七、高级评估方法 (v3.0 新增)

### 7.1 Walk-Forward 验证框架

> **世界顶级标准**: 替代简单的 train/test split，检测策略对 regime 变化的鲁棒性

```
┌─────────────────────────────────────────────────────────────────────┐
│  Walk-Forward Analysis (滚动前进验证)                                │
│                                                                      │
│  传统方法 (有问题):                                                   │
│  [============ Training ============][======= Test =======]          │
│  问题: 无法检测策略是否对未来市场状态有效                            │
│                                                                      │
│  Walk-Forward 方法:                                                  │
│  [Train 1][Test 1]                                                   │
│           [Train 2][Test 2]                                          │
│                    [Train 3][Test 3]                                 │
│                             [Train 4][Test 4]                        │
│  优势: 模拟真实交易场景，检测策略衰减                                │
└─────────────────────────────────────────────────────────────────────┘
```

```python
from typing import List, Dict, Tuple
from datetime import datetime, timedelta

def walk_forward_analysis(
    trades: List[Trade],
    train_window_days: int = 30,
    test_window_days: int = 7,
    step_days: int = 7,
    min_trades_per_window: int = 20
) -> Dict:
    """
    执行 Walk-Forward 分析

    参考:
    - Pardo (2008): The Evaluation and Optimization of Trading Strategies
    - Bailey et al. (2014): The Deflated Sharpe Ratio

    Args:
        trades: 按时间排序的交易列表
        train_window_days: 训练窗口天数
        test_window_days: 测试窗口天数
        step_days: 滚动步长
        min_trades_per_window: 每个窗口最小交易数
    """
    results = []
    start_date = trades[0].entry_time
    end_date = trades[-1].exit_time

    current_start = start_date

    while current_start + timedelta(days=train_window_days + test_window_days) <= end_date:
        train_end = current_start + timedelta(days=train_window_days)
        test_end = train_end + timedelta(days=test_window_days)

        # 划分训练/测试集
        train_trades = [t for t in trades
                       if current_start <= t.entry_time < train_end]
        test_trades = [t for t in trades
                      if train_end <= t.entry_time < test_end]

        if len(train_trades) >= min_trades_per_window and len(test_trades) >= 5:
            # 计算各窗口的指标
            train_metrics = calculate_trading_metrics(train_trades, initial_capital=10000)
            test_metrics = calculate_trading_metrics(test_trades, initial_capital=10000)

            results.append({
                'window_start': current_start.isoformat(),
                'window_end': test_end.isoformat(),
                'train_sharpe': train_metrics.get('sharpe_ratio', 0),
                'test_sharpe': test_metrics.get('sharpe_ratio', 0),
                'train_win_rate': train_metrics.get('win_rate', 0),
                'test_win_rate': test_metrics.get('win_rate', 0),
                'degradation': (train_metrics.get('sharpe_ratio', 0) -
                               test_metrics.get('sharpe_ratio', 0)),
            })

        current_start += timedelta(days=step_days)

    # 汇总分析
    if results:
        avg_degradation = np.mean([r['degradation'] for r in results])
        degradation_std = np.std([r['degradation'] for r in results])
        test_sharpes = [r['test_sharpe'] for r in results]

        return {
            'n_windows': len(results),
            'avg_test_sharpe': np.mean(test_sharpes),
            'min_test_sharpe': np.min(test_sharpes),
            'max_test_sharpe': np.max(test_sharpes),
            'avg_degradation': avg_degradation,
            'degradation_std': degradation_std,
            'is_robust': avg_degradation < 0.5 and np.min(test_sharpes) > 0,
            'windows': results
        }

    return {'error': '样本量不足以进行 Walk-Forward 分析'}

# 验收标准:
# - avg_degradation < 0.5 (训练到测试的 Sharpe 下降 < 0.5)
# - min_test_sharpe > 0 (所有测试窗口 Sharpe > 0)
# - is_robust = True
```

### 7.2 策略衰减检测

> **关键**: 所有策略都会衰减，越早发现越好

```python
from scipy import stats
import numpy as np
from typing import List, Dict, Optional

def detect_strategy_decay(
    rolling_metrics: List[Dict],
    metric_name: str = 'sharpe_ratio',
    lookback_windows: int = 10,
    decay_threshold: float = 0.3
) -> Dict:
    """
    检测策略是否在衰减

    参考:
    - Lo (2002): The Statistics of Sharpe Ratios
    - Harvey et al. (2016): Lucky Factors

    检测方法:
    1. 趋势检测: 线性回归斜率
    2. 结构突变检测: Chow test
    3. 均值比较: t-test 近期 vs 历史
    """
    if len(rolling_metrics) < lookback_windows * 2:
        return {'error': f'需要至少 {lookback_windows * 2} 个窗口的数据'}

    values = [m[metric_name] for m in rolling_metrics if metric_name in m]

    recent = values[-lookback_windows:]
    historical = values[:-lookback_windows]

    # 1. 趋势检测 (线性回归)
    x = np.arange(len(recent))
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, recent)
    trend_declining = slope < 0 and p_value < 0.1

    # 2. 均值比较 (Welch's t-test)
    t_stat, p_val_ttest = stats.ttest_ind(recent, historical, equal_var=False)
    mean_declined = t_stat < 0 and p_val_ttest < 0.05

    # 3. 衰减幅度
    recent_mean = np.mean(recent)
    historical_mean = np.mean(historical)
    decay_magnitude = (historical_mean - recent_mean) / historical_mean if historical_mean != 0 else 0

    # 综合判断
    is_decaying = (
        (trend_declining and decay_magnitude > decay_threshold) or
        (mean_declined and decay_magnitude > decay_threshold)
    )

    severity = 'NONE'
    if is_decaying:
        if decay_magnitude > 0.5:
            severity = 'SEVERE'
        elif decay_magnitude > 0.3:
            severity = 'MODERATE'
        else:
            severity = 'MILD'

    return {
        'is_decaying': is_decaying,
        'severity': severity,
        'decay_magnitude': decay_magnitude,
        'trend_slope': slope,
        'trend_p_value': p_value,
        'mean_comparison_p_value': p_val_ttest,
        'recent_mean': recent_mean,
        'historical_mean': historical_mean,
        'recommendation': _get_decay_recommendation(severity)
    }


def _get_decay_recommendation(severity: str) -> str:
    """根据衰减严重程度给出建议"""
    recommendations = {
        'NONE': '策略表现稳定，继续监控',
        'MILD': '轻微衰减，建议调整参数或减小仓位',
        'MODERATE': '明显衰减，建议暂停交易，重新评估策略',
        'SEVERE': '严重衰减，建议立即停止交易，考虑回滚'
    }
    return recommendations.get(severity, '未知状态')

# 监控频率建议:
# - 每周运行一次策略衰减检测
# - 连续 2 周 MILD 衰减 → 升级为 MODERATE 处理
# - 任何 SEVERE 衰减 → 立即人工审查
```

### 7.3 Bootstrap 置信区间

> **统计鲁棒性**: 当样本量有限时，Bootstrap 比参数方法更可靠

```python
import numpy as np
from typing import List, Dict, Callable

def bootstrap_confidence_interval(
    data: List[float],
    statistic_func: Callable,
    n_bootstrap: int = 10000,
    confidence_level: float = 0.95,
    random_seed: int = 42
) -> Dict:
    """
    使用 Bootstrap 方法计算统计量的置信区间

    参考:
    - Efron & Tibshirani (1993): An Introduction to the Bootstrap
    - Davison & Hinkley (1997): Bootstrap Methods and Their Application

    优势:
    - 不假设数据分布
    - 适用于小样本
    - 可用于复杂统计量 (Sharpe, MDD 等)

    Args:
        data: 原始数据
        statistic_func: 计算统计量的函数
        n_bootstrap: Bootstrap 重采样次数
        confidence_level: 置信水平
    """
    np.random.seed(random_seed)
    n = len(data)
    data = np.array(data)

    # 原始统计量
    original_stat = statistic_func(data)

    # Bootstrap 重采样
    bootstrap_stats = []
    for _ in range(n_bootstrap):
        # 有放回抽样
        sample = np.random.choice(data, size=n, replace=True)
        bootstrap_stats.append(statistic_func(sample))

    bootstrap_stats = np.array(bootstrap_stats)

    # 计算置信区间 (百分位数法)
    alpha = 1 - confidence_level
    lower = np.percentile(bootstrap_stats, alpha / 2 * 100)
    upper = np.percentile(bootstrap_stats, (1 - alpha / 2) * 100)

    # 计算标准误差
    se = np.std(bootstrap_stats)

    # 偏差校正 (BCa 方法简化版)
    bias = np.mean(bootstrap_stats) - original_stat

    return {
        'point_estimate': original_stat,
        'ci_lower': lower,
        'ci_upper': upper,
        'confidence_level': confidence_level,
        'standard_error': se,
        'bias': bias,
        'n_bootstrap': n_bootstrap,
        'interpretation': f'{confidence_level*100:.0f}% CI: [{lower:.4f}, {upper:.4f}]'
    }


def bootstrap_sharpe_ratio(trades: List[Trade], **kwargs) -> Dict:
    """专门用于 Sharpe Ratio 的 Bootstrap 分析"""
    returns = [t.pnl_pct / 100 for t in trades]

    def sharpe_func(r):
        if len(r) < 2 or np.std(r) == 0:
            return 0
        return np.mean(r) / np.std(r) * np.sqrt(252)  # 年化

    return bootstrap_confidence_interval(returns, sharpe_func, **kwargs)


def bootstrap_max_drawdown(trades: List[Trade], initial_capital: float = 10000, **kwargs) -> Dict:
    """专门用于 Maximum Drawdown 的 Bootstrap 分析"""

    def mdd_func(trade_indices):
        # 根据索引重构净值曲线
        equity = [initial_capital]
        for i in trade_indices:
            if 0 <= int(i) < len(trades):
                equity.append(equity[-1] + trades[int(i)].pnl)

        running_max = equity[0]
        max_dd = 0
        for v in equity:
            running_max = max(running_max, v)
            if running_max > 0:
                max_dd = max(max_dd, (running_max - v) / running_max)
        return max_dd

    indices = list(range(len(trades)))
    return bootstrap_confidence_interval(indices, mdd_func, **kwargs)


# 使用示例:
# sharpe_ci = bootstrap_sharpe_ratio(trades, confidence_level=0.95)
# print(f"Sharpe Ratio: {sharpe_ci['point_estimate']:.2f}")
# print(f"95% CI: [{sharpe_ci['ci_lower']:.2f}, {sharpe_ci['ci_upper']:.2f}]")

# 验收标准:
# - Sharpe Ratio 95% CI 下界 > 0.5 (不能包含负值)
# - Maximum Drawdown 95% CI 上界 < 15%
```

### 7.4 多重假设检验校正

> **避免 p-hacking**: 当同时检验多个指标时，需要校正

```python
from typing import List, Dict

def bonferroni_correction(
    p_values: List[float],
    alpha: float = 0.05
) -> Dict:
    """
    Bonferroni 校正 (最保守)

    校正后的 α = α / n
    """
    n = len(p_values)
    corrected_alpha = alpha / n
    significant = [p < corrected_alpha for p in p_values]

    return {
        'method': 'bonferroni',
        'original_alpha': alpha,
        'corrected_alpha': corrected_alpha,
        'n_tests': n,
        'significant': significant,
        'n_significant': sum(significant)
    }


def benjamini_hochberg_correction(
    p_values: List[float],
    alpha: float = 0.05
) -> Dict:
    """
    Benjamini-Hochberg 校正 (控制 False Discovery Rate)

    参考: Benjamini & Hochberg (1995)
    """
    n = len(p_values)
    sorted_pairs = sorted(enumerate(p_values), key=lambda x: x[1])
    significant = [False] * n

    for rank, (original_idx, p) in enumerate(sorted_pairs, 1):
        threshold = (rank / n) * alpha
        if p <= threshold:
            significant[original_idx] = True

    return {
        'method': 'benjamini_hochberg',
        'original_alpha': alpha,
        'n_tests': n,
        'significant': significant,
        'n_significant': sum(significant),
        'fdr_controlled': True
    }

# 应用场景:
# 当同时检验多个指标 (胜率、Sharpe、MDD 等) 的显著性时
# 使用 BH 校正避免假阳性
```

---

## 八、评估时间线 (v3.0 更新)

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

## 九、指标速查表 (v3.0 更新)

### 9.1 核心绩效指标

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

### 9.2 风险调整收益指标 (v3.0 新增)

| 指标 | 最低接受 | 目标值 | 理想值 | 说明 |
|-----|---------|-------|-------|------|
| **Sharpe Ratio** (年化) | >0.5 | >1.0 | >1.5 | 扣除成本后 |
| **Sortino Ratio** (年化) | >0.7 | >1.2 | >2.0 | 只惩罚下行 |
| **Calmar Ratio** | >0.5 | >1.0 | >2.0 | 收益/MDD |
| **Profit Factor** | >1.2 | >1.5 | >2.0 | 扣除成本后 |

### 9.3 尾部风险指标 (v3.0 新增)

| 指标 | 最低接受 | 目标值 | 说明 |
|-----|---------|-------|------|
| **VaR_95** | <5% | <3% | 单日最大亏损 (95% 置信度) |
| **CVaR_99** | <8% | <5% | 极端损失平均值 (99% 置信度) |

### 9.4 样本量与验证要求 (v3.0 更新)

| 要求 | Phase 1 | Phase 2 | Phase 3 |
|-----|---------|---------|---------|
| **最小交易次数** | ≥50次 | ≥200次 | ≥500次 |
| **最小测试天数** | ≥14天 | ≥30天 | ≥60天 |
| **能检测的效应** | Large (10%+) | Medium (5%+) | Small (2%+) |
| **统计功效** | ~50% | ~80% | ~95% |

### 9.5 高级验证标准 (v3.0 新增)

| 验证方法 | 通过标准 | 说明 |
|---------|---------|------|
| **Walk-Forward** | avg_degradation < 0.5, min_test_sharpe > 0 | 策略鲁棒性 |
| **Bootstrap CI** | Sharpe 95% CI 下界 > 0.5 | 统计置信度 |
| **策略衰减** | severity = NONE or MILD | 长期稳定性 |
| **成本扣除** | 扣除后仍盈利 | 现实可行性 |

---

## 十、参考资料

### 项目文档
- S/R 强度研究报告: [SR_STRENGTH_RESEARCH.md](./SR_STRENGTH_RESEARCH.md)

### 学术研究 (v3.0 扩充)
- Cont et al. (2014). The Price Impact of Order Book Events
- [MDPI - S/R Levels in Algorithmic Trading](https://www.mdpi.com/2227-7390/10/20/3888)
- Sharpe (1994). The Sharpe Ratio. Journal of Portfolio Management.
- Sortino & Price (1994). Performance Measurement in a Downside Risk Framework.
- Artzner et al. (1999). Coherent Measures of Risk. Mathematical Finance.
- Efron & Tibshirani (1993). An Introduction to the Bootstrap.
- Pardo (2008). The Evaluation and Optimization of Trading Strategies.
- Bailey et al. (2014). The Deflated Sharpe Ratio. Journal of Portfolio Management.
- Lo (2002). The Statistics of Sharpe Ratios. Financial Analysts Journal.
- Cohen (1988). Statistical Power Analysis for the Behavioral Sciences.
- Benjamini & Hochberg (1995). Controlling the False Discovery Rate.

### 行业实践
- [Analyzing Alpha - Support and Resistance](https://analyzingalpha.com/support-and-resistance)
- [Quantified Strategies - Stop Loss Strategy](https://www.quantifiedstrategies.com/stop-loss-trading-strategy/)
- [3Commas - Advanced Stop-Loss Logic 2025](https://3commas.io/blog/optimizing-your-trades-advanced-stop-loss-and-take)
- [Algorithmic Trading Library - Dynamic Stop-Loss](https://algotradinglib.com/en/pedia/d/dynamic_stop-loss_strategies.html)

### 监管框架
- Basel III/IV - VaR/CVaR 风险计量标准

### 工具
- 12-Factor App Configuration: https://12factor.net/config
- A/B Testing Calculator: https://www.evanmiller.org/ab-testing/
- Statistical Power Calculator: https://www.stat.ubc.ca/~rollin/stats/ssize/

---

**文档版本**: v3.0 (世界顶级量化标准)
**创建日期**: 2026-02-02
**最后更新**: 2026-02-05
**更新历史**:
- v3.0: **重大升级** - 按 Renaissance/Two Sigma/Citadel 级别标准重构
  - 修正 Sharpe Ratio 计算 (年化 + 样本标准差 + 无风险利率)
  - 修正 Maximum Drawdown 计算 (基于净值曲线)
  - 新增 Sortino Ratio、Calmar Ratio
  - 新增 VaR/CVaR 尾部风险评估 (Basel III/IV 标准)
  - 新增交易成本建模 (手续费 + 滑点 + 资金费率)
  - 新增 Walk-Forward 验证框架
  - 新增策略衰减检测
  - 新增 Bootstrap 置信区间
  - 新增多重假设检验校正 (Bonferroni, Benjamini-Hochberg)
  - 样本量要求从 50 次提升到 200+ 次 (基于统计功效分析)
- v2.1: 添加 Bull/Bear 辩论机制描述 (4.3)，明确验收标准是参考值而非硬性要求
- v2.0: **重大重构** - 按 TradingAgents 架构重写，明确本地 vs AI 职责划分
  - 移除所有本地硬编码决策规则 (classify_market_condition, calculate_dynamic_tp 等)
  - 移除 A/B 测试对照组设计，改为直接实施
  - 第四章改为描述正确的架构 (本地预处理 + AI 决策)
  - 第六章简化为 AI 风险管理职责描述
- v1.2: 添加行情分类标准 (4.2.2)、完整决策流程图 (4.2.7)、修正章节编号
- v1.1: 添加行业实践调研章节 (4.7)
