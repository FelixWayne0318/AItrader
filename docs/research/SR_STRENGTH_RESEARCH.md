# S/R 强度测量研究报告

**日期**: 2026-02-02
**状态**: 研究阶段 (未实施)
**作者**: AI Assistant

---

## 研究背景

用户提出需要增强 S/R (支撑/阻力) 强度评估，以便在极端行情时动态调整止盈位。当前系统 (`utils/sr_zone_calculator.py`) 使用基于 confluence 的权重系统，但缺少：
- 历史触及次数追踪
- 反弹力度测量
- 时间框架权重依据

本文档整理行业标准、学术研究和最佳实践，为后续实施提供依据。

---

## 一、权重设置的依据

### 1.1 当前系统权重

```python
# utils/sr_zone_calculator.py:108-115
WEIGHTS = {
    'Order_Wall': 2.0,      # 订单簿大单 (最重要)
    'SMA_200': 1.5,         # 长期趋势
    'BB_Upper': 1.0,        # 布林带
    'BB_Lower': 1.0,
    'SMA_50': 0.8,          # 中期趋势
    'Pivot': 0.7,           # Pivot Points
}
```

### 1.2 行业惯例

权重设置在业界**没有统一标准**。不同平台和机构使用不同方法：

| 来源类型 | 常见权重范围 | 依据 |
|---------|------------|------|
| Order Flow (订单簿) | 最高 (2.0-3.0x) | 实时数据，反映当前供需 |
| Volume Profile POC | 高 (1.5-2.0x) | 统计验证，70%交易量集中区 |
| SMA_200 | 中高 (1.2-1.5x) | 广泛认可的长期趋势指标 |
| Bollinger Bands | 中 (1.0x) | 波动率边界，但非硬阻力 |
| Fibonacci | 中低 (0.8-1.0x) | 自我实现效应，但无统计支持 |
| Pivot Points | 低 (0.5-0.8x) | 简单计算，适合日内交易 |

### 1.3 学术研究支持

**Cont, Kukanov & Stoikov (2014)** - [The Price Impact of Order Book Events](https://www.researchgate.net/publication/47860140_The_Price_Impact_of_Order_Book_Events):
- 研究 NYSE TAQ 数据中 50 只股票
- 发现价格变化与订单流失衡 (Order Flow Imbalance) 呈线性关系
- OBI 比简单的交易量指标更有预测力
- **结论**: Order Flow 数据权重应高于技术指标

**Multi-Level Order-Flow Imbalance (2019)** - [World Scientific](https://www.worldscientific.com/doi/10.1142/S2382626619500114):
- OBI 可从多个价格档位聚合
- 权重应随距离盘口衰减 (Decay Factor)
- **建议公式**: `weight = base_weight * (decay ^ distance_from_mid)`

### 1.4 权重校准方法

**推荐方法：Backtesting Optimization**

```
1. 设置权重参数范围
   - Order_Wall: [1.5, 2.0, 2.5, 3.0]
   - SMA_200: [1.0, 1.2, 1.5, 1.8]
   - ...

2. 对每组参数组合:
   - 计算 S/R zones
   - 追踪价格在 zone 处的反应
   - 统计 bounce rate (反弹率)
   - 统计 break rate (突破率)

3. 评估指标:
   - HIGH strength zones 的 hold rate 应 > 70%
   - LOW strength zones 的 break rate 应 > 60%

4. 选择最佳参数组合
```

**参考工具**:
- [QuantifiedStrategies - Volume Profile](https://www.quantifiedstrategies.com/volume-profile-indicator-trading-strategies/)
- [PyQuantLab - Volume Profile Backtesting](https://pyquantlab.medium.com/precision-trading-with-volume-profile-an-enhanced-strategy-and-rolling-backtest-analysis-369cb4e1c2c5)

---

## 二、Touch Count (触及次数) 研究

### 2.1 两种对立观点

**传统观点** - "越多次测试越强":
> "The more often price tests a level of resistance or support without breaking it, the stronger the area of resistance or support is."
> -- [Analyzing Alpha](https://analyzingalpha.com/support-and-resistance)

**反传统观点** - "多次测试意味着弱化":
> "Contrary to popular belief, multiple tests of a level can actually indicate weakness rather than strength. The strongest support and resistance levels often show powerful price reactions with just a few touches."
> -- [Mind Math Money](https://www.mindmathmoney.com/articles/master-support-and-resistance-trading-complete-guide-for-all-markets-2025)

### 2.2 学术研究

**Osler (2000)** - [Support for Resistance](https://www.researchgate.net/publication/5050393_Support_for_Resistance_Technical_Analysis_and_Intraday_Exchange_Rates):
- 研究外汇市场日内支撑阻力
- 使用 "bounce frequency" (反弹频率) 作为预测能力指标
- 发现: **多家机构共识的价位并不比单家发布的价位更强**
- 暗示: 质量 > 数量

### 2.3 实际应用建议

| 指标 | 说明 | 权重建议 |
|-----|------|---------|
| **首次触及后的反弹** | 第一次测试后的强烈反弹最有意义 | +2.0 |
| **2-3 次触及仍守住** | 证明该价位有真实供需 | +1.5 |
| **4+ 次触及** | 可能正在弱化，准备突破 | +0.5 或 -0.5 |
| **"Hugging" 行为** | 价格长时间停留在价位附近 | -1.0 (弱化信号) |

### 2.4 数据需求

要追踪 Touch Count，需要：

```python
# 需要的数据结构
class TouchRecord:
    timestamp: datetime
    price_level: float
    touch_price: float      # 实际触及价格
    rejection_strength: float  # 反弹力度 (见下节)
    time_at_level: timedelta   # 在价位停留时间
    volume_at_level: float     # 触及时的成交量
```

**数据来源**:
- 历史 K线数据 (已有: `indicator_manager.recent_bars`)
- 需要新增: 价位触及检测逻辑

---

## 三、Rejection Strength (反弹力度) 测量

### 3.1 行业方法

**Pin Bar / Wick Rejection**:
> "A pin bar that closes near its wick, with the tail poking out above the price, is a rejection pattern. The longer the tail, the stronger the rejection."
> -- [Price Action Trading](https://priceaction.com/price-action-university/strategies/support-resistance-levels/)

**关键指标**:

| 指标 | 公式 | 说明 |
|-----|------|------|
| **Wick Ratio** | `wick_length / body_length` | >2.0 为强反弹 |
| **Bounce Speed** | `price_change / time` | 快速反弹 = 强拒绝 |
| **Volume Spike** | `touch_volume / avg_volume` | >1.5x 为强信号 |
| **Follow-Through** | 反弹后 N 根 K 线的方向 | 持续 = 强，回撤 = 弱 |

### 3.2 计算公式建议

```python
def calculate_rejection_strength(
    touch_candle: dict,
    avg_volume: float,
    atr: float,
    follow_through_candles: list
) -> float:
    """
    计算反弹力度 (0-10 分)

    Components:
    - Wick score: 0-3 分
    - Volume score: 0-3 分
    - Speed score: 0-2 分
    - Follow-through: 0-2 分
    """
    score = 0.0

    # 1. Wick Score (影线长度)
    body = abs(touch_candle['close'] - touch_candle['open'])
    lower_wick = min(touch_candle['open'], touch_candle['close']) - touch_candle['low']
    upper_wick = touch_candle['high'] - max(touch_candle['open'], touch_candle['close'])

    # 对于支撑位，看下影线
    wick_ratio = lower_wick / body if body > 0 else lower_wick / atr
    if wick_ratio >= 2.0:
        score += 3.0
    elif wick_ratio >= 1.0:
        score += 2.0
    elif wick_ratio >= 0.5:
        score += 1.0

    # 2. Volume Score
    volume_ratio = touch_candle['volume'] / avg_volume if avg_volume > 0 else 1.0
    if volume_ratio >= 2.0:
        score += 3.0
    elif volume_ratio >= 1.5:
        score += 2.0
    elif volume_ratio >= 1.0:
        score += 1.0

    # 3. Bounce Speed (下一根 K 线的反弹幅度)
    if follow_through_candles:
        next_candle = follow_through_candles[0]
        bounce = next_candle['close'] - touch_candle['close']
        bounce_atr_ratio = abs(bounce) / atr
        if bounce_atr_ratio >= 1.0:
            score += 2.0
        elif bounce_atr_ratio >= 0.5:
            score += 1.0

    # 4. Follow-Through (后续 3 根 K 线趋势一致性)
    if len(follow_through_candles) >= 3:
        bullish_count = sum(1 for c in follow_through_candles[:3] if c['close'] > c['open'])
        if bullish_count >= 3:  # 全部阳线
            score += 2.0
        elif bullish_count >= 2:
            score += 1.0

    return min(score, 10.0)  # 最高 10 分
```

### 3.3 数据需求

当前系统已有的数据:
- ✅ K 线数据 (`indicator_manager.recent_bars`)
- ✅ 成交量 (`bar.volume`)
- ✅ ATR (可从 K 线计算)

需要新增:
- ❌ 触及检测逻辑 (检测价格何时触及 S/R zone)
- ❌ 历史触及记录 (需要持久化)

---

## 四、TimeFrame (时间框架) 权重

### 4.1 行业共识

> "The strength of a particular support or resistance level increases when they are drawn on higher time frames. A monthly support level will be stronger than an intraday support level."
> -- [CME Group Education](https://www.cmegroup.com/education/courses/technical-analysis/support-and-resistance)

### 4.2 建议权重

| 时间框架 | Level 级别 | 基础权重 | 说明 |
|---------|-----------|---------|------|
| 1D / Weekly | MAJOR | 2.0x | 机构参与，长期有效 |
| 4H | INTERMEDIATE | 1.5x | 波段交易主力框架 |
| 1H | INTERMEDIATE | 1.2x | 日内波段 |
| 15M | MINOR | 1.0x | 执行入场 |
| 5M / 1M | MINOR | 0.5x | 噪音较多 |

### 4.3 Multi-Timeframe Confluence (多框架共振)

> "Identifying confluence zones—where support, resistance, or trend indicators from various timeframes intersect—increases the reliability of entry and exit points."
> -- [TradeFundrr](https://tradefundrr.com/multiple-timeframe-confluence-trading/)

**共振加分规则**:

```python
# 如果同一价位在多个时间框架出现
confluence_bonus = {
    1: 0.0,      # 仅 1 个框架
    2: +0.5,     # 2 个框架共振
    3: +1.0,     # 3 个框架共振 (推荐)
    4: +1.5,     # 4+ 个框架 (极强)
}
```

**TradingView 实现参考**:
- [Multi-Timeframe S/R Confluence - Enhanced](https://www.tradingview.com/script/nlnTaxjS-Multi-Timeframe-S-R-Confluence-Enhanced/)
- 使用 "merge nearby levels" 算法聚合多框架价位

---

## 五、综合评分公式建议

基于以上研究，建议的 S/R 强度评分公式：

```python
def calculate_sr_strength(
    zone: SRZone,
    touch_history: List[TouchRecord],
    timeframe_confluence: int,
) -> float:
    """
    综合 S/R 强度评分 (0-10 分)

    Components:
    1. Base Weight (来源权重): 0-3 分
    2. Touch Quality (触及质量): 0-3 分
    3. TimeFrame Weight (时间框架): 0-2 分
    4. Confluence Bonus (共振加分): 0-2 分
    """

    # 1. Base Weight (已有)
    # Order_Wall=2.0, SMA_200=1.5, BB=1.0, SMA_50=0.8, Pivot=0.7
    base_score = min(zone.total_weight, 3.0)

    # 2. Touch Quality
    if not touch_history:
        touch_score = 1.0  # 未经测试，给中性分
    else:
        # 计算平均反弹力度
        avg_rejection = sum(t.rejection_strength for t in touch_history) / len(touch_history)

        # 考虑触及次数 (2-3 次最优)
        touch_count = len(touch_history)
        if touch_count <= 1:
            count_factor = 0.8
        elif touch_count <= 3:
            count_factor = 1.0  # 最优
        elif touch_count <= 5:
            count_factor = 0.9
        else:
            count_factor = 0.7  # 多次测试，可能弱化

        touch_score = (avg_rejection / 10.0) * 3.0 * count_factor

    # 3. TimeFrame Weight
    tf_weights = {
        SRLevel.MAJOR: 2.0,
        SRLevel.INTERMEDIATE: 1.5,
        SRLevel.MINOR: 1.0,
    }
    tf_score = tf_weights.get(zone.level, 1.0)

    # 4. Confluence Bonus
    confluence_bonus = {1: 0.0, 2: 0.5, 3: 1.0, 4: 1.5}
    confluence_score = confluence_bonus.get(min(timeframe_confluence, 4), 1.5)

    # 总分
    total = base_score + touch_score + tf_score + confluence_score

    return min(total, 10.0)
```

---

## 六、实施优先级建议

### Phase 1: 基础数据收集 (低风险)
1. 添加 Touch Detection 逻辑
2. 存储历史触及记录 (JSON 文件)
3. 计算基础 Rejection Strength

### Phase 2: 权重校准 (中风险)
1. 收集足够的历史数据 (建议 30 天)
2. Backtest 不同权重组合
3. 根据结果调整权重

### Phase 3: 多框架共振 (中风险)
1. 扩展 SRZoneCalculator 支持多框架输入
2. 实现共振检测算法
3. 添加 Confluence Bonus

### Phase 4: 动态止盈 (高风险)
1. 根据 S/R 强度动态调整止盈位
2. 需要更多 backtesting 验证

---

## 七、参考资料

### 学术论文
- Cont, Kukanov & Stoikov (2014). [The Price Impact of Order Book Events](https://www.researchgate.net/publication/47860140_The_Price_Impact_of_Order_Book_Events). Journal of Financial Econometrics.
- Osler (2000). [Support for Resistance: Technical Analysis and Intraday Exchange Rates](https://www.researchgate.net/publication/5050393_Support_for_Resistance_Technical_Analysis_and_Intraday_Exchange_Rates). FRBNY Economic Policy Review.

### 行业资源
- [LuxAlgo - Volume Profile](https://www.luxalgo.com/blog/volume-profile-map-where-smart-money-trades/)
- [TrendSpider - Volume Profile Strategies](https://trendspider.com/learning-center/volume-profile-strategies/)
- [QuantifiedStrategies - Volume Profile](https://www.quantifiedstrategies.com/volume-profile-indicator-trading-strategies/)

### TradingView 指标参考
- [Multi-Timeframe S/R Confluence - Enhanced](https://www.tradingview.com/script/nlnTaxjS-Multi-Timeframe-S-R-Confluence-Enhanced/)
- [Support and Resistance Adaptive](https://www.mql5.com/en/market/product/150199)

### 系统现有实现
- `utils/sr_zone_calculator.py` - S/R Zone 计算器 v2.0
- `utils/orderbook_analyzer.py` - 订单簿分析 (Order Wall 检测)

---

## 八、待解答问题

1. **权重校准需要多长历史数据？**
   - 建议: 至少 30 天交易数据 (含不同市场状态)

2. **Touch Detection 的精度阈值？**
   - 建议: `|price - level| < ATR * 0.3` 视为触及

3. **如何处理假突破后的回归？**
   - 建议: 假突破后回归算作 "强反弹"，给予额外加分

4. **高频数据 vs 低频数据的权衡？**
   - 建议: 对于 15M 框架，使用 1M 或 5M 数据检测触及，但不需要 tick 级别数据

---

**下一步**: 等待用户确认研究方向，再开始实施。
