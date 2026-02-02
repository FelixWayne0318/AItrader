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

> **靠概率和盈亏比盈利，盈亏比根据 S/R 强度动态变化**

```
期望收益 = 胜率 × 平均盈利 - (1-胜率) × 平均亏损

正常行情: 胜率 55% × 盈亏比 1.5:1 = 正期望
极端行情: 胜率 50% × 盈亏比 3:1 = 更高期望 (顺势交易，放大止盈)
```

### 4.1 A/B 测试设计

```
┌─────────────────────────────────────────────────────────────┐
│  对照组 (A): 当前系统                                        │
│  ├─ 固定 SL: 2%                                             │
│  ├─ 固定 TP: 根据 confidence (1%/2%/3%)                     │
│  ├─ 无历史数据上下文                                         │
│  └─ 无 S/R 强度调整                                         │
└─────────────────────────────────────────────────────────────┘
                          vs
┌─────────────────────────────────────────────────────────────┐
│  实验组 (B): 新系统                                          │
│  ├─ 动态 SL: 基于支撑强度调整 (1.5%-2.5%)                   │
│  ├─ 动态 TP: 基于阻力强度 + 行情类型 (1%-8%)                │
│  │   ├─ 正常行情: 根据最近 S/R 距离设置                     │
│  │   └─ 极端行情: 顺势放大 2-3 倍                           │
│  ├─ 20 值历史数据上下文                                      │
│  └─ AI 可见趋势变化                                          │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 动态止盈策略 (核心创新)

#### 4.2.1 核心理念

> **止盈止损不是固定比例，而是由市场结构 (S/R 价位) 决定**

```
错误思路: 止盈 = 入场价 × (1 + 2%)        ← 固定比例
正确思路: 止盈 = 下一个阻力位价格         ← 市场结构决定

一般行情 → 止盈设在最近的 S/R 价位
大行情   → 止盈设在更远/更强的 S/R 价位
```

#### 4.2.2 行情分类标准

> **如何判定"一般行情" vs "大行情"？**

| 行情类型 | 判定条件 | 典型场景 |
|---------|---------|---------|
| **NORMAL** | 1小时波动 < 2% | 日常盘整、小幅震荡 |
| **EXTREME_BULLISH** | 1小时涨幅 > 3% + 趋势明确 | 重大利好、突破关键阻力 |
| **EXTREME_BEARISH** | 1小时跌幅 > 3% + 趋势明确 | 重大利空、跌破关键支撑 |
| **EXTREME_VOLATILE** | 5分钟波动 > 3% + 方向不明 | 黑天鹅、流动性危机 |

```python
def classify_market_condition(
    price_change_1h: float,       # 1小时价格变化 (%)
    volatility_5min: float,       # 5分钟波动率 (%)
    trend_direction: str,         # BULLISH/BEARISH/NEUTRAL
) -> str:
    """
    行情分类逻辑

    核心原则:
    1. 波动 > 3% 且方向明确 → 极端行情 (顺势机会)
    2. 波动 > 3% 但方向不明 → 极端震荡 (谨慎)
    3. 波动 < 2% → 正常行情
    """
    # 检测极端波动
    is_extreme = abs(price_change_1h) > 0.03 or volatility_5min > 0.03

    if not is_extreme:
        return 'NORMAL'

    # 判断方向
    if price_change_1h > 0.03 and trend_direction == 'BULLISH':
        return 'EXTREME_BULLISH'
    elif price_change_1h < -0.03 and trend_direction == 'BEARISH':
        return 'EXTREME_BEARISH'
    else:
        # 波动大但方向不明确
        return 'EXTREME_VOLATILE'
```

#### 4.2.3 止盈目标选择逻辑

| 行情类型 | 做多止盈目标 | 做空止盈目标 |
|---------|-------------|-------------|
| **NORMAL** | 最近的阻力位 | 最近的支撑位 |
| **EXTREME_BULLISH** (做多) | 更远/更强的阻力位 | - |
| **EXTREME_BEARISH** (做空) | - | 更远/更强的支撑位 |
| **EXTREME_VOLATILE** | 最近的 S/R (保守) | 最近的 S/R (保守) |
| **无明显 S/R** | 备选: 固定比例 3% | 备选: 固定比例 3% |

#### 4.2.4 动态止盈公式

```python
def calculate_dynamic_tp(
    signal: str,                    # LONG/SHORT
    entry_price: float,             # 入场价格
    market_condition: str,          # NORMAL/EXTREME_BULLISH/EXTREME_BEARISH
    resistance_levels: List[Dict],  # [{'price': 76000, 'strength': 'WEAK'}, ...]
    support_levels: List[Dict],     # [{'price': 74000, 'strength': 'MEDIUM'}, ...]
) -> Dict:
    """
    动态计算止盈价位

    核心逻辑:
    1. 止盈设在 S/R 价位，不是固定比例
    2. 一般行情 → 最近的 S/R
    3. 大行情 → 更远/更强的 S/R
    4. 无 S/R 时用固定比例作为备选
    """
    result = {
        'tp_price': None,
        'tp_type': None,      # 'SR_LEVEL' or 'FALLBACK_PCT'
        'target_sr': None,
        'distance_pct': None,
    }

    # 根据信号方向选择 S/R 列表
    if signal == 'LONG':
        # 做多: 止盈在阻力位
        sr_levels = [r for r in resistance_levels if r['price'] > entry_price]
        sr_levels.sort(key=lambda x: x['price'])  # 按价格升序
    else:
        # 做空: 止盈在支撑位
        sr_levels = [s for s in support_levels if s['price'] < entry_price]
        sr_levels.sort(key=lambda x: x['price'], reverse=True)  # 按价格降序

    if not sr_levels:
        # 无 S/R 数据，使用固定比例备选
        fallback_pct = 0.03  # 3%
        if signal == 'LONG':
            result['tp_price'] = entry_price * (1 + fallback_pct)
        else:
            result['tp_price'] = entry_price * (1 - fallback_pct)
        result['tp_type'] = 'FALLBACK_PCT'
        result['distance_pct'] = fallback_pct
        return result

    # 根据行情类型选择目标 S/R
    if market_condition == 'NORMAL':
        # 一般行情: 选择最近的 S/R
        target_sr = sr_levels[0]
    elif market_condition in ['EXTREME_BULLISH', 'EXTREME_BEARISH']:
        # 大行情: 选择更远/更强的 S/R
        # 优先选择 STRONG 或 MEDIUM 强度的
        strong_levels = [s for s in sr_levels if s['strength'] in ['STRONG', 'MEDIUM']]
        if strong_levels:
            target_sr = strong_levels[0]  # 最近的强 S/R
        elif len(sr_levels) >= 2:
            target_sr = sr_levels[1]  # 第二个 S/R (跳过最近的弱 S/R)
        else:
            target_sr = sr_levels[0]  # 只有一个，就用它
    else:
        target_sr = sr_levels[0]

    # 设置止盈价位 (在 S/R 前留一点缓冲)
    buffer = 0.001  # 0.1% 缓冲
    if signal == 'LONG':
        result['tp_price'] = target_sr['price'] * (1 - buffer)
    else:
        result['tp_price'] = target_sr['price'] * (1 + buffer)

    result['tp_type'] = 'SR_LEVEL'
    result['target_sr'] = target_sr
    result['distance_pct'] = abs(result['tp_price'] - entry_price) / entry_price

    return result
```

#### 4.2.5 止盈场景示例

```
当前价格: $75,000
做多信号

阻力位分布:
  R1: $76,000 (WEAK)   - 距离 1.3%
  R2: $78,000 (MEDIUM) - 距离 4.0%
  R3: $82,000 (STRONG) - 距离 9.3%

支撑位分布:
  S1: $74,000 (WEAK)   - 距离 1.3%
  S2: $72,000 (MEDIUM) - 距离 4.0%
  S3: $68,000 (STRONG) - 距离 9.3%
```

| 场景 | 行情 | 止盈目标 | 止盈价 | 盈亏比* |
|-----|------|---------|-------|--------|
| 做多，一般行情 | NORMAL | R1 (最近阻力) | $75,900 | 1.3:2 |
| 做多，大行情 | EXTREME_BULL | R2 (中等阻力) | $77,920 | 4:2 |
| 做多，超大行情 | EXTREME_BULL | R3 (强阻力) | $81,920 | 9:2 |
| 做空，一般行情 | NORMAL | S1 (最近支撑) | $74,070 | 1.3:2 |
| 做空，大行情 | EXTREME_BEAR | S2 (中等支撑) | $72,070 | 4:2 |

*假设止损固定 2%

#### 4.2.6 止损同理

```python
def calculate_dynamic_sl(
    signal: str,
    entry_price: float,
    support_levels: List[Dict],
    resistance_levels: List[Dict],
) -> Dict:
    """
    动态计算止损价位

    做多: 止损设在最近的支撑位下方
    做空: 止损设在最近的阻力位上方
    """
    result = {
        'sl_price': None,
        'sl_type': None,
        'reference_sr': None,
    }

    if signal == 'LONG':
        # 做多: 止损在支撑位下方
        supports = [s for s in support_levels if s['price'] < entry_price]
        if supports:
            supports.sort(key=lambda x: x['price'], reverse=True)
            nearest_support = supports[0]
            buffer = 0.002  # 0.2% 缓冲
            result['sl_price'] = nearest_support['price'] * (1 - buffer)
            result['sl_type'] = 'SR_LEVEL'
            result['reference_sr'] = nearest_support
        else:
            # 无支撑数据，用固定比例
            result['sl_price'] = entry_price * (1 - 0.02)
            result['sl_type'] = 'FALLBACK_PCT'
    else:
        # 做空: 止损在阻力位上方
        resistances = [r for r in resistance_levels if r['price'] > entry_price]
        if resistances:
            resistances.sort(key=lambda x: x['price'])
            nearest_resistance = resistances[0]
            buffer = 0.002
            result['sl_price'] = nearest_resistance['price'] * (1 + buffer)
            result['sl_type'] = 'SR_LEVEL'
            result['reference_sr'] = nearest_resistance
        else:
            result['sl_price'] = entry_price * (1 + 0.02)
            result['sl_type'] = 'FALLBACK_PCT'

    return result
```

#### 4.2.7 完整决策流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SL/TP 决策流程                                │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  1. 获取信号方向 (LONG/SHORT)                                        │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  2. 识别行情类型                                                     │
│     ├─ price_change_1h > 3% + BULLISH → EXTREME_BULLISH             │
│     ├─ price_change_1h < -3% + BEARISH → EXTREME_BEARISH            │
│     ├─ volatility_5min > 3% + 方向不明 → EXTREME_VOLATILE           │
│     └─ else → NORMAL                                                │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  3. 获取 S/R 价位列表                                                │
│     ├─ LONG: 上方阻力位列表 (按距离排序)                            │
│     └─ SHORT: 下方支撑位列表 (按距离排序)                           │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                        ┌──────────┴──────────┐
                        │                     │
                        ▼                     ▼
              ┌─────────────────┐   ┌─────────────────┐
              │  有 S/R 数据     │   │  无 S/R 数据     │
              └─────────────────┘   └─────────────────┘
                        │                     │
                        ▼                     ▼
┌─────────────────────────────────┐  ┌─────────────────────┐
│  4a. 根据行情选择目标 S/R        │  │  4b. 使用固定比例    │
│  ├─ NORMAL: 最近的 S/R          │  │      TP: 3%          │
│  ├─ EXTREME_顺势: 更远/强的 S/R │  │      SL: 2%          │
│  └─ EXTREME_VOLATILE: 最近 S/R  │  └─────────────────────┘
└─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  5. 设置止盈价位 (在 S/R 前留 0.1% 缓冲)                            │
│     ├─ LONG TP: target_resistance × 0.999                          │
│     └─ SHORT TP: target_support × 1.001                            │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  6. 设置止损价位 (在 S/R 外留 0.2% 缓冲)                            │
│     ├─ LONG SL: nearest_support × 0.998                            │
│     └─ SHORT SL: nearest_resistance × 1.002                        │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  7. 验证盈亏比                                                       │
│     ├─ NORMAL: R:R ≥ 1.0 → 执行                                     │
│     ├─ EXTREME_顺势: R:R ≥ 1.5 → 执行                               │
│     └─ R:R 不足 → 调整或跳过                                        │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.3 核心绩效指标

| 指标 | 定义 | 目标改进 | 最低接受 |
|-----|------|---------|---------|
| **胜率 (Win Rate)** | 盈利交易 / 总交易 | +5% | 不低于基准 |
| **盈亏比 (R:R)** | 平均盈利 / 平均亏损 (动态) | +20% | +10% |
| **最大回撤 (MDD)** | 最大峰谷跌幅 | -10% | 不高于基准 |
| **Sharpe Ratio** | (收益-无风险) / 波动率 | +0.2 | 不低于基准 |
| **Profit Factor** | 总盈利 / 总亏损 | +15% | +5% |
| **极端行情捕获率** | 极端行情盈利次数 / 极端行情交易次数 | ≥50% | ≥40% |

### 4.4 盈亏比分布分析

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

# 验收标准:
# - 正常行情盈亏比: 1.2-1.5
# - 极端行情盈亏比: 2.5-4.0 (顺势交易)
# - 极端行情应占总交易 10-20%
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

### 4.5 样本量要求

| 要求 | 最小值 | 推荐值 | 原因 |
|-----|-------|-------|------|
| **交易次数** | ≥50 次/组 | ≥100 次/组 | 统计显著性 |
| **时间跨度** | ≥14 天 | ≥30 天 | 覆盖不同市场状态 |
| **牛市天数** | ≥5 天 | ≥10 天 | 避免偏差 |
| **熊市天数** | ≥5 天 | ≥10 天 | 避免偏差 |
| **震荡天数** | ≥5 天 | ≥10 天 | 避免偏差 |

### 4.6 统计显著性检验

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

## 4.7 行业实践调研

### 4.7.1 调研结论

> **基于 S/R 价位设置止盈止损是专业交易的主流做法**

| 方法 | 使用者 | 优点 | 缺点 |
|-----|-------|------|------|
| **固定百分比** | 散户、简单策略 | 简单易用 | 不考虑市场结构 |
| **S/R 价位** | 机构、专业交易者 | 符合市场心理 | 实现复杂 |

### 4.7.2 机构观点

**Analyzing Alpha (机构交易研究)**:
> "The institutional trader at the margin determines most securities' prices and the support and resistance levels... Institutions have target buy and sell prices for every security."

机构交易者为每个持仓设定目标买入/卖出价位，这些价位通常就是 S/R 水平。

**D.E. Shaw (量化基金巨头)**:
> "Stop-losses are set in advance, which accounts for the staleness, and they are a function of only **one form of information – price**."

David Shaw 认为固定止损的问题是**信息单一且陈旧**，支持动态/结构化止损。

### 4.7.3 主流平台实现

| 平台 | S/R 功能 | 备注 |
|-----|---------|------|
| **3Commas** | "Placing SL/TP based on key S/R levels... These levels often act as price barriers" | 交易机器人平台 |
| **TradingView** | AI 指标验证 S/R 区域 | 图表分析平台 |
| **ATAS** | 专业订单流 + S/R 分析 | 机构级工具 |
| **Pionex** | Grid Bot 上下限基于 S/R | 网格交易 |

### 4.7.4 学术研究支持

[MDPI 论文 - S/R Levels in Algorithmic Trading](https://www.mdpi.com/2227-7390/10/20/3888):
使用神经网络学习 S/R 与价格运动的关系，证明了 S/R 对交易决策的价值。

### 4.7.5 最佳实践建议

来自 [Algorithmic Trading Library](https://algotradinglib.com/en/pedia/d/dynamic_stop-loss_strategies.html):

| 实践 | 说明 |
|-----|------|
| **缓冲区** | "Place stops 0.5-1.0 ATR beyond the S/R zone" |
| **多时间框架** | "Use larger time frames (daily/4H) for significant S/R, smaller for entries" |
| **动态调整** | "Adaptive algorithms adjust stop parameters based on changing market conditions" |

### 4.7.6 我们的方案定位

| 对比项 | 散户工具 (如 Pionex) | 我们的方案 | 机构标准 |
|-------|---------------------|-----------|---------|
| 止盈止损 | 固定百分比或网格 | S/R 价位 + 行情动态调整 | S/R 价位 + 多因子 |
| 极端行情 | 无特殊处理 | 顺势放大止盈 | 风险模型调整 |
| 数据来源 | 单一指标 | 多层 S/R + 订单流 | 多层 S/R + 订单流 + 私有数据 |

**结论**: 我们的方案符合专业交易标准，超越大多数散户交易机器人。

### 4.7.7 参考资料

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

> **极端行情是机会，关键是识别方向和控制风险，而不是一味回避**

```
错误思路: 极端行情 → 回退保守策略 → 错失大行情
正确思路: 极端行情 → 识别方向 → 顺势交易 → 放大止盈 → 控制风险
```

### 6.1 极端行情处理策略

| 行情类型 | 信号方向 | 止损 | 止盈 | 仓位 |
|---------|---------|------|------|------|
| **极端利空** | 顺势做空 | 保持 2% | **放大到 5-8%** | 标准或略降 |
| **极端利多** | 顺势做多 | 保持 2% | **放大到 5-8%** | 标准或略降 |
| **极端利空** | 逆势做多 | 收紧 1.5% | 收紧 1% | 降低 50% |
| **极端利多** | 逆势做空 | 收紧 1.5% | 收紧 1% | 降低 50% |
| **剧烈震荡** | 方向不明 | 标准 2% | 标准 | 降低 30-50% |

### 6.2 异常场景处理

| 风险场景 | 检测条件 | 预期行为 | 验收标准 |
|---------|---------|---------|---------|
| **极端行情 (方向明确)** | 5分钟波动 >3% 且趋势明确 | 顺势交易，放大止盈 | 正确识别方向 |
| **极端行情 (方向不明)** | 5分钟波动 >3% 且震荡 | 减仓或观望 | 100% 触发 |
| **S/R 数据缺失** | nearest_support=None | 使用默认值，不崩溃 | 100% 正常运行 |
| **历史数据不足** | len(history) < 10 | 标记数据质量低，告知 AI | 100% 正确标记 |
| **API 超时** | 数据获取 >5秒 | 使用缓存数据 | 100% 降级成功 |
| **连续亏损** | 3 次连续止损 | 降低仓位或发出警告 | 可配置触发 |
| **流动性不足** | 订单簿深度低 | 减小仓位，避免滑点 | 100% 检测 |

### 6.3 极端行情识别与处理

```python
def handle_extreme_market(
    volatility_5min: float,
    price_change_1h: float,
    signal: str,
    sr_strength: str,
) -> Dict:
    """
    极端行情处理逻辑

    核心原则:
    1. 极端行情顺势交易，放大止盈
    2. 逆势交易收紧止盈，降低仓位
    3. 方向不明时谨慎
    """
    result = {
        'market_condition': 'NORMAL',
        'tp_multiplier': 1.0,
        'sl_multiplier': 1.0,
        'position_multiplier': 1.0,
        'action': 'NORMAL_TRADE',
    }

    # 检测极端行情
    is_extreme = volatility_5min > 0.03  # 5分钟波动 >3%

    if not is_extreme:
        return result

    # 判断方向
    is_bullish = price_change_1h > 0.03   # 1小时涨幅 >3%
    is_bearish = price_change_1h < -0.03  # 1小时跌幅 >3%

    if is_bullish:
        result['market_condition'] = 'EXTREME_BULLISH'
        if signal == 'LONG':
            # 极端利多做多 = 顺势
            result['tp_multiplier'] = 2.5  # 放大止盈
            result['action'] = 'TREND_FOLLOW_LONG'
        else:
            # 极端利多做空 = 逆势
            result['tp_multiplier'] = 0.7
            result['sl_multiplier'] = 0.75  # 收紧止损
            result['position_multiplier'] = 0.5
            result['action'] = 'COUNTER_TREND_SHORT'

    elif is_bearish:
        result['market_condition'] = 'EXTREME_BEARISH'
        if signal == 'SHORT':
            # 极端利空做空 = 顺势
            result['tp_multiplier'] = 2.5  # 放大止盈
            result['action'] = 'TREND_FOLLOW_SHORT'
        else:
            # 极端利空做多 = 逆势
            result['tp_multiplier'] = 0.7
            result['sl_multiplier'] = 0.75
            result['position_multiplier'] = 0.5
            result['action'] = 'COUNTER_TREND_LONG'

    else:
        # 方向不明的剧烈震荡
        result['market_condition'] = 'EXTREME_VOLATILE'
        result['position_multiplier'] = 0.5
        result['action'] = 'REDUCE_EXPOSURE'

    return result
```

### 6.4 回退机制测试

```python
def test_extreme_market_handling():
    """测试极端行情处理"""

    # 场景 1: 极端利多顺势做多
    result = handle_extreme_market(
        volatility_5min=0.05,
        price_change_1h=0.05,
        signal='LONG',
        sr_strength='WEAK'
    )
    assert result['market_condition'] == 'EXTREME_BULLISH'
    assert result['tp_multiplier'] == 2.5  # 放大止盈
    assert result['action'] == 'TREND_FOLLOW_LONG'

    # 场景 2: 极端利空顺势做空
    result = handle_extreme_market(
        volatility_5min=0.05,
        price_change_1h=-0.05,
        signal='SHORT',
        sr_strength='NONE'
    )
    assert result['market_condition'] == 'EXTREME_BEARISH'
    assert result['tp_multiplier'] == 2.5  # 放大止盈

    # 场景 3: 逆势交易 - 应收紧
    result = handle_extreme_market(
        volatility_5min=0.05,
        price_change_1h=0.05,
        signal='SHORT',  # 逆势
        sr_strength='STRONG'
    )
    assert result['tp_multiplier'] == 0.7  # 收紧止盈
    assert result['position_multiplier'] == 0.5  # 降低仓位

def test_fallback_mechanisms():
    """测试其他异常场景的回退机制"""

    # 场景 1: S/R 数据缺失
    result = calculate_sl_tp(sr_zone=None, confidence='MEDIUM')
    assert result['sl_pct'] == 0.02, "Should fallback to default 2%"

    # 场景 2: 历史数据不足
    history = [1, 2, 3]  # 只有 3 个值
    quality = assess_data_quality(history, required=20)
    assert quality['is_sufficient'] == False
    assert quality['warning'] == 'Insufficient history data'
```

### 6.5 安全边界

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
│  Week 5-8: A/B 测试 (小资金实盘)                             │
│  ├─ 目标: 对比新旧系统绩效                                   │
│  ├─ 评估: 交易绩效标准 (Section 四)                         │
│  ├─ 样本: ≥50 次交易/组                                     │
│  ├─ 产出: 绩效对比报告                                       │
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

### 3.1 基准数据 (对照组 A)
- 交易次数: __
- 胜率: __%
- 盈亏比: __
- 最大回撤: __%
- Sharpe Ratio: __
- Profit Factor: __

### 3.2 实验数据 (实验组 B)
- 交易次数: __
- 胜率: __% (vs 基准: __%）
- 盈亏比: __ (vs 基准: __%)
- 最大回撤: __% (vs 基准: __%)
- Sharpe Ratio: __ (vs 基准: __)
- Profit Factor: __ (vs 基准: __%)

### 3.3 统计显著性
- t-statistic: __
- p-value: __
- 结论: 显著优于 / 无显著差异 / 显著劣于

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
| **样本** | 最小交易次数 | ≥50次/组 | ≥100次/组 |
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

**文档版本**: v1.2
**创建日期**: 2026-02-02
**最后更新**: 2026-02-02
**更新历史**:
- v1.2: 添加行情分类标准 (4.2.2)、完整决策流程图 (4.2.7)、修正章节编号
- v1.1: 添加行业实践调研章节 (4.7)
