# S/R v4.0 + SL/TP 全链路重构 — 统一设计方案 (修订版 R2)

> 修订历史: R1 初版 → R2 整合三大风险修正 + 5 大订单 Bug 修复 + SL/TP 一致性重构
> 学术基础: Spitsin (2025), Chung & Bellotti (2021), Osler (2003), CME Market Profile

---

## 一、系统全局问题诊断

### 1.1 S/R 计算问题 (已识别)

| # | 问题 | 影响 |
|---|------|------|
| 1 | **时间尺度错误** | 所有 swing 在 15M×120=30h 内找，日线级别看不到 |
| 2 | **MTF 数据浪费** | `decision_manager`(4H) 和 `trend_manager`(1D) 已有 bar 数据，未传给 S/R |
| 3 | **SMA 含义错乱** | `SMA_200` 实际是 15M×200=50h，不是日线 SMA200 |
| 4 | **Swing 无成交量确认** | Spitsin (2025): 无确认 P=0.70; 有确认 P=0.81-0.88 |
| 5 | **Round Number 粒度** | $1000 步长对 BTC 太细，Osler (2003): $5k/$10k 级别 |
| 6 | **无 Volume Profile** | VPOC 有 90% 反应率 (SHS 2021)，当前缺失 |
| 7 | **无 Pivot 投射** | ATH 时无法投射上方阻力 |

### 1.2 SL/TP 和订单管理问题 (新增)

| # | 问题 | 实际报错 | 根因 |
|---|------|---------|------|
| 8 | **手动平仓后 SL/TP 报错** | -2022 ReduceOnly rejected | SL/TP 订单成为孤儿，无状态清理 |
| 9 | **减仓后 SL/TP 数量不更新** | -2022 (数量超仓位) | `_reduce_position()` 不更新 SL/TP 数量 |
| 10 | **SL 未验证当前价** | -2021 immediately trigger | 只验证 SL vs entry，不验证 SL vs current_price |
| 11 | **GTC 过期无恢复** | GTC Expired | `on_order_expired()` 只告警不恢复 |
| 12 | **动态 SL/TP 与开仓逻辑脱节** | — | 开仓用 AI+S/R，维护用固定 trailing，TP 完全不更新 |

### 1.3 已有可复用的好设计

- **两阶段订单提交** (v4.13): MARKET entry → `_pending_sltp` → SL/TP 分别提交
- **R/R >= 1.5 硬门槛**: `validate_multiagent_sltp()` + `calculate_technical_sltp()` 一致执行
- **Binance API 优先**: `_get_current_position_data()` 优先 API 而非缓存
- **OCO 手动取消**: `on_order_filled()` 取消对方订单
- **历史 bar 预加载**: `_prefetch_multi_timeframe_bars()` 启动时加载 220 根 1D bar（冷启动已解决）
- **ATR 自适应聚类**: zone 合并阈值随波动率调整
- **Touch Count 评分**: 2-3 次最优，4+ 次递减 (Chung 2021)
- **时间衰减**: `age_factor = max(0.5, 1.0 - bars_ago/max_age * 0.5)` (已实现)
- **S/R Flip**: 突破的阻力变支撑 (v3.1 已实现)

---

## 二、设计目标

### 量化标准

| 指标 | 当前估计 | 目标 | 参考基线 |
|------|---------|------|---------|
| S/R Precision (触及时确实反弹) | 未测量 | ≥ 0.75 | Spitsin: 0.81-0.88 (美股) |
| ATH 场景上方有阻力 | 0/3 次 | ≥ 2/3 | — |
| SL 提交被拒率 | ~5% | < 1% | — |
| 仓位无保护时间 | 未知 | < 30 秒 | — |
| 动态 SL/TP 与 S/R 一致性 | 0% (完全脱节) | 100% | — |

### 设计原则

1. **分层职责** — 检测/投射/确认/决策各层独立，数据源不重叠
2. **S/R 驱动 SL/TP** — SL 锚定在 S/R zone 上 + ATR 缓冲，不是固定百分比
3. **15 分钟闭环** — 每个分析周期重新评估 SL/TP，不依赖陈旧的开仓价
4. **提交前验证** — SL/TP 必须通过当前价验证，不只是入场价验证
5. **优雅降级** — 任何层失败时有明确的回退路径

> **注**: Spitsin (2025) 发表于 Contemporary Mathematics (IF ~0.7)，样本为美股 (AAPL/MSFT/TSLA)。
> BTC 永续合约有 24/7 交易、杠杆清算、资金费率等独特性。
> 论文的 P=0.81-0.88 是参考基线而非直接预期目标。

---

## 三、S/R 分层架构

### 3.1 四层职责分离

```
┌─────────────────────────────────────────────────────────┐
│  第一层: 检测层 (DETECTION) — "历史上哪里有支撑阻力"      │
│  数据源: 1D bars + 4H bars (MTF swing points)           │
│  方法: Spitsin 成交量加权 Williams Fractal               │
│  输出: STRUCTURAL 类型候选                               │
│  特点: 历史验证，触碰次数和成交量确认                     │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  第二层: 投射层 (PROJECTION) — "上方/下方数学投射"        │
│  数据源: 最近日线/周线 bar 的 H/L/C                      │
│  方法: Floor Trader Pivot (Daily + Weekly)               │
│  输出: PROJECTED 类型候选 (强度上限 MEDIUM)               │
│  特点: 纯数学计算，ATH 时提供上方阻力                    │
│  ⚠️ AI 提示: "此为数学投射，无历史交易确认"               │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  第三层: 确认层 (CONFIRMATION) — "微观结构确认"           │
│  数据源: 15M bars 近 24h (与检测层时间粒度不同)          │
│  方法: Volume Profile (VPOC/VAH/VAL) + Order Wall       │
│  输出: 独立确认候选 (或增强第一层 zone 的权重)           │
│  解耦: VP 用 15M 近 24h，Swing 用 1D/4H → 避免循环论证 │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  第四层: 决策层 (DECISION) — DeepSeek AI                 │
│  输入: 第 1-3 层结构化 S/R 报告 + 技术指标 + 情绪       │
│  角色: 替代 Spitsin 的 Markov 链，做反弹/突破判断        │
│  输出: 交易信号 + SL/TP 建议                             │
└─────────────────────────────────────────────────────────┘
```

### 3.2 数据源解耦矩阵

| 层 | 时间框架 | 数据源 | 独立于其他层？ |
|----|---------|--------|-------------|
| 检测层 Swing | 1D (120 bars) + 4H (50 bars) | `trend_manager` + `decision_manager` | ✅ |
| 投射层 Pivot | 最近 1D bar + 最近 1W bar | `trend_manager` | ✅ |
| 确认层 VP | **15M (96 bars = 24h)** | `indicator_manager` | ✅ 与检测层时间粒度不同 |
| 确认层 OrderWall | 实时盘口 | `BinanceOrderBookClient` | ✅ 完全独立 |
| 辅助 Round# | 当前价格 | 计算得出 | ✅ |

### 3.3 候选来源和权重

```
_collect_candidates()
  │
  │ ===== 检测层 (STRUCTURAL) =====
  │
  ├ 1D Swing (成交量加权)           权重 2.0  level=MAJOR
  ├ 4H Swing (成交量加权)           权重 1.5  level=INTERMEDIATE
  ├ 15M Swing (成交量加权)          权重 0.8  level=MINOR
  │   └ 成交量加权: 百分位数连续缩放 (见 3.4)
  │
  │ ===== 投射层 (PROJECTED, 强度上限 MEDIUM) =====
  │
  ├ Daily Pivot (PP/R1/R2/R3/S1/S2/S3)   权重 1.0  level=MAJOR
  ├ Weekly Pivot (PP/R1/R2/S1/S2)         权重 1.2  level=MAJOR
  │   └ Weekly Pivot 在连续突破多日时仍有投射能力 (日线 range 更大)
  │
  │ ===== 确认层 (STRUCTURAL, 独立数据源) =====
  │
  ├ Volume Profile VPOC/VAH/VAL           权重 1.3  level=INTERMEDIATE
  │   └ 基于 15M 近 24h bars (与检测层 1D/4H 解耦)
  │   └ Range Uniform Distribution (按 OHLC 范围比例分配 volume)
  │
  ├ Order Wall (实时盘口)                 权重 0.8  level=MINOR
  │
  │ ===== 辅助 (PSYCHOLOGICAL) =====
  │
  └ Round Number (BTC: $5000 步长)        权重 0.5  level=MINOR
```

**权重说明：这些是初始估计值，需通过离线回测校准。设计原则：高时间框架 > 低时间框架，历史验证 > 投射。**

**投射层强度封顶规则：**
```python
PROJECTED_MAX_STRENGTH = 'MEDIUM'  # 投射来源最高 MEDIUM
# 仅当投射层 zone 与 ORDER_FLOW 或 STRUCTURAL 来源聚合时，才可升为 HIGH
```

**同源聚合封顶：**
```python
# 同一 zone 中来自同一数据时间框架的候选，合并后权重不超过:
SAME_DATA_WEIGHT_CAP = 2.5
```

**多源独立性奖励：**
```python
unique_source_types = len(set(c.source_type for c in cluster))
if unique_source_types >= 3:    # STRUCTURAL + ORDER_FLOW + PROJECTED 等
    confluence_bonus = 0.5
elif unique_source_types >= 2:
    confluence_bonus = 0.2
```

### 3.4 成交量加权算法 (百分位数连续缩放)

**R1 版本问题**: `volume > MA(20) × 1.0` 是二元过滤，不区分"稍高于 MA"和"5 倍 MA"。

**R2 修正**: 百分位数连续缩放，无新参数，所有时间框架通用。

```python
def _volume_weight_factor(self, bar_volume: float, all_volumes: List[float]) -> float:
    """
    百分位数连续缩放 (Spitsin 2025 精神: 成交量确认重要性)

    优势:
    - 连续函数，不是二元判断
    - 百分位数天然归一化，1D/4H/15M 通用
    - 无新参数 (30%/70% 对应约 ±0.5 标准差)
    - 低成交量 swing 不丢弃 (保底 0.3)
    """
    if not all_volumes or bar_volume <= 0:
        return 0.5  # 无数据时给中间值

    # 计算百分位排名
    rank = sum(1 for v in all_volumes if v <= bar_volume) / len(all_volumes)

    # 三段式连续加权
    if rank >= 0.7:       # Top 30% 高成交量
        return 1.0
    elif rank >= 0.3:     # 中等成交量 (30th-70th percentile)
        return 0.5 + (rank - 0.3) * 1.25   # 0.5 → 1.0 线性
    else:                 # Bottom 30% 低成交量
        return 0.3        # 最低保底

# 使用:
# weight = base_weight * age_factor * vol_factor
```

### 3.5 Volume Profile 算法 (Range Uniform Distribution)

**R1 版本问题**: 仅按 close 分配 volume，VPOC 系统性偏移。

**R2 修正**: 按 OHLC 范围比例分配 (本项目 `diagnose_sr_zones.py` L288-299 已有正确实现)。

```python
def _calculate_volume_profile(self, bars_15m: List[Dict], current_price: float):
    """
    Volume Profile (Range Uniform Distribution)

    来源: 15M bars 近 24h (96 根) — 与检测层 (1D/4H) 解耦
    算法: 按每根 bar 的 H-L 范围比例分配 volume 到各 bin
    参考: CME Market Profile, diagnose_sr_zones.py L288-299 (已验证)
    """
    # ... 确定 price_range, bin_size, num_bins ...

    for bar in bars_15m:
        high = float(bar['high'])
        low = float(bar['low'])
        volume = float(bar['volume'])
        bar_range = high - low

        for j, (bin_low, bin_high) in enumerate(zip(bin_edges[:-1], bin_edges[1:])):
            if low <= bin_high and high >= bin_low:
                if bar_range > 0:
                    overlap = (min(high, bin_high) - max(low, bin_low)) / bar_range
                else:
                    overlap = 1.0  # Doji
                vol_bins[j] += volume * overlap

    # VPOC, VAH, VAL 计算同 R1 ...
```

### 3.6 Pivot Points (Daily + Weekly)

```python
def _calculate_pivots(self, daily_bar: Dict, weekly_bar: Optional[Dict],
                      current_price: float) -> List[SRCandidate]:
    """
    Floor Trader Pivot Points (Daily + Weekly)

    Daily: 从最近完成的日线 bar 计算
    Weekly: 从最近完成的周线 bar 计算 (覆盖连续突破多日场景)

    所有 Pivot 候选标记为 source_type=PROJECTED, 强度上限 MEDIUM。
    AI 报告中标注: "⚠️ PROJECTED - 数学投射，无历史交易确认"
    """
    candidates = []

    for bar, period, base_weight in [
        (daily_bar, 'Daily', 1.0),
        (weekly_bar, 'Weekly', 1.2),
    ]:
        if not bar:
            continue
        H, L, C = float(bar['high']), float(bar['low']), float(bar['close'])
        if H <= 0 or L <= 0 or C <= 0:
            continue

        PP = (H + L + C) / 3
        pivots = {
            'PP': PP, 'R1': 2*PP-L, 'R2': PP+(H-L), 'R3': H+2*(PP-L),
            'S1': 2*PP-H, 'S2': PP-(H-L), 'S3': L-2*(H-PP),
        }

        for name, price in pivots.items():
            if price <= 0:
                continue
            side = 'support' if price < current_price else 'resistance'
            candidates.append(SRCandidate(
                price=price,
                source=f"{period}Pivot_{name}",
                weight=base_weight,
                side=side,
                level=SRLevel.MAJOR,
                source_type=SRSourceType.PROJECTED,  # ← 关键: 标记为投射
            ))

    return candidates
```

**Weekly Pivot 数据来源：** 从 `trend_manager` 的 1D bars 中聚合最近 5 根获取周 H/L/C。无需额外数据源。

### 3.7 AI 报告中的 PROJECTED 标注

```
【CALCULATED S/R ZONES】
RESISTANCE ZONES:
>>>[R1] $99,200 (+2.3%) [MAJOR|MEDIUM] ⚠️ PROJECTED
      Source: WeeklyPivot_R2 (数学投射，无历史交易确认)
   [R2] $98,500 (+1.5%) [INTERMEDIATE|MEDIUM]
      Source: VPOC (15M 24h Volume Profile)

SUPPORT ZONES:
>>>[S1] $96,300 (-0.7%) [INTERMEDIATE|HIGH] ✅ CONFIRMED
      Source: Swing_4H + OrderWall (多源独立确认)
      Touch Count: 3 (optimal)
   [S2] $95,000 (-2.1%) [MAJOR|HIGH] ✅ CONFIRMED
      Source: Swing_1D (S/R flip) + Round_Number ($95k)
```

### 3.8 强度阈值

```python
STRENGTH_THRESHOLDS = {
    'HIGH':   3.0,   # 维持 v3.1 值 (不贸然提高，待回测校准)
    'MEDIUM': 1.5,   # 维持 v3.1 值
    'LOW':    0.0,
}
```

**理由**: R1 提议提高到 3.5/2.0，但没有回测支撑。维持现有值，后续通过离线回测工具校准。

---

## 四、SL/TP 全链路重构

### 4.1 核心原则

```
SL/TP 必须基于 S/R zones + ATR 缓冲，不是固定百分比。
开仓和动态更新使用同一套计算函数。
每 15 分钟闭环: 新 S/R → 新 SL/TP → 验证 → 更新。
```

### 4.2 统一 SL/TP 计算函数

**当前问题**: 开仓用 `calculate_technical_sltp()` (S/R-based)，动态更新用 `_update_trailing_stops()` (固定百分比)。两套完全不同的逻辑。

**修复: 新增 `calculate_sr_based_sltp()` — 唯一的 SL/TP 计算入口。**

```python
def calculate_sr_based_sltp(
    current_price: float,
    side: str,              # 'BUY' or 'SELL'
    sr_zones: Dict,         # S/R zones 计算结果
    atr_value: float,       # 当前 ATR
    min_rr_ratio: float = 1.5,
    atr_buffer_multiplier: float = 0.5,
) -> Tuple[Optional[float], Optional[float], str]:
    """
    统一 SL/TP 计算 (基于 S/R zones + ATR 缓冲)

    原则:
    - LONG: SL = nearest_support - ATR×buffer, TP = nearest_resistance
    - SHORT: SL = nearest_resistance + ATR×buffer, TP = nearest_support
    - R/R >= min_rr_ratio 才有效
    - ATR 缓冲防止噪音触发 (比固定百分比更自适应)

    用于:
    - 开仓时初始 SL/TP (替代部分 calculate_technical_sltp 逻辑)
    - 每 15 分钟动态更新 (替代 trailing stop 的固定百分比)
    """
    nearest_support = sr_zones.get('nearest_support')
    nearest_resistance = sr_zones.get('nearest_resistance')
    atr_buffer = atr_value * atr_buffer_multiplier

    if side == 'BUY':
        # SL: 最近支撑下方 + ATR 缓冲
        if nearest_support:
            sl = nearest_support.price_center - atr_buffer
        else:
            sl = current_price * (1 - 0.02)  # 2% 默认回退

        # TP: 最近阻力
        if nearest_resistance:
            tp = nearest_resistance.price_center
        else:
            tp = current_price * (1 + 0.03)  # 3% 默认回退

        # 安全检查: SL 必须低于当前价
        if sl >= current_price:
            sl = current_price - atr_buffer * 2

    elif side == 'SELL':
        # SL: 最近阻力上方 + ATR 缓冲
        if nearest_resistance:
            sl = nearest_resistance.price_center + atr_buffer
        else:
            sl = current_price * (1 + 0.02)

        # TP: 最近支撑
        if nearest_support:
            tp = nearest_support.price_center
        else:
            tp = current_price * (1 - 0.03)

        if sl <= current_price:
            sl = current_price + atr_buffer * 2

    # R/R 验证
    risk = abs(current_price - sl)
    reward = abs(tp - current_price)
    rr_ratio = reward / risk if risk > 0 else 0

    if rr_ratio < min_rr_ratio:
        return None, None, f"R/R {rr_ratio:.2f}:1 < {min_rr_ratio}:1"

    return sl, tp, f"R/R {rr_ratio:.2f}:1 ✅"
```

### 4.3 15 分钟动态 SL/TP 更新闭环

**当前问题**: TP 完全不更新; SL 只通过 trailing stop (固定百分比) 更新。

**修复: 在 `on_timer()` 中增加 SL/TP 重新评估。**

```python
# 在 on_timer() 中，AI 分析完成后:
def _reevaluate_sltp_for_existing_position(self, current_position, sr_zones, atr):
    """
    每 15 分钟基于最新 S/R zones 重新评估 SL/TP

    规则:
    1. 用 calculate_sr_based_sltp() 计算新 SL/TP (同开仓逻辑)
    2. SL 只能向有利方向移动 (LONG: 只能上移, SHORT: 只能下移)
    3. TP 可以双向调整 (新 S/R 可能比旧的更近或更远)
    4. 变化超过 threshold 才实际更新 (避免频繁修改)
    5. 提交前验证: new_sl 必须未被当前价触发
    """
    side = current_position['side']  # 'LONG' or 'SHORT'
    current_price = self._cached_current_price

    new_sl, new_tp, reason = calculate_sr_based_sltp(
        current_price=current_price,
        side='BUY' if side == 'LONG' else 'SELL',
        sr_zones=sr_zones,
        atr_value=atr,
    )

    if new_sl is None:
        return  # R/R 不满足，保持现有 SL/TP

    state = self.trailing_stop_state.get(instrument_key, {})
    old_sl = state.get('current_sl_price')
    old_tp = state.get('current_tp_price')

    # 规则 2: SL 只能向有利方向移动
    if side == 'LONG' and old_sl and new_sl < old_sl:
        new_sl = old_sl  # LONG 的 SL 不能下移
    if side == 'SHORT' and old_sl and new_sl > old_sl:
        new_sl = old_sl  # SHORT 的 SL 不能上移

    # 规则 4: 变化超过阈值才更新
    sl_changed = old_sl is None or abs(new_sl - old_sl) / old_sl > 0.002  # 0.2%
    tp_changed = old_tp is None or abs(new_tp - old_tp) / old_tp > 0.002

    # 规则 5: 提交前验证当前价
    if side == 'LONG' and new_sl >= current_price:
        return  # 会立即触发
    if side == 'SHORT' and new_sl <= current_price:
        return  # 会立即触发

    if sl_changed or tp_changed:
        self._replace_sltp_orders(
            new_total_quantity=current_position['quantity'],
            position_side=side,
            new_sl_price=new_sl,
            new_tp_price=new_tp,
        )
```

**与 Trailing Stop 的关系:**

```
Trailing Stop (on_bar, 每根 bar):
  → 快速响应 (价格快速拉升时立即跟踪)
  → 只移动 SL，不动 TP
  → 简单公式: highest × (1 - distance%)

S/R 动态更新 (on_timer, 每 15 分钟):
  → 深度分析 (基于最新 S/R zones)
  → SL + TP 都可更新
  → 锚定在结构性价位

两者共存，取更有利的 SL:
  final_sl = max(trailing_sl, sr_sl)  # LONG 时取更高的
  final_sl = min(trailing_sl, sr_sl)  # SHORT 时取更低的
```

---

## 五、订单安全修复

### 5.1 修复手动平仓后报错 (Bug #8)

```python
# 在 on_order_expired() 和 on_order_rejected() 中增加:
def _handle_orphan_order(self, order_id, reason):
    """清理孤儿订单的内部状态"""
    # 1. 检查仓位是否还存在
    current_position = self._get_current_position_data()

    if not current_position:
        # 仓位已不存在 → 清理所有相关状态
        self._clear_position_state()
        self.log.info("Position closed externally, cleared internal state")
    else:
        # 仓位存在但订单失败 → 尝试重新提交
        self._resubmit_sltp_if_needed(current_position)

def _clear_position_state(self):
    """清理所有仓位相关的内部状态"""
    instrument_key = str(self.instrument_id)
    self.trailing_stop_state.pop(instrument_key, None)
    self._pending_sltp = None
    self._pending_reversal = None
```

### 5.2 修复减仓后 SL/TP 不更新 (Bug #9)

```python
# 在 _reduce_position() 成功后:
def _reduce_position(self, current_position, target_pct):
    # ... 现有减仓逻辑 ...

    # 新增: 减仓后更新 SL/TP 数量
    if reduce_success:
        new_quantity = current_position['quantity'] * (1 - target_pct/100)
        self._replace_sltp_orders(
            new_total_quantity=new_quantity,
            position_side=current_position['side'],
            new_sl_price=current_sl,  # 保持原价
            new_tp_price=current_tp,  # 保持原价
        )
```

### 5.3 修复 SL 未验证当前价 (Bug #10)

```python
# 在 on_position_opened() 提交 SL 前增加:
def _validate_sl_against_current_price(self, sl_price, side, current_price):
    """确保 SL 不会立即触发"""
    if side == 'LONG' and sl_price >= current_price:
        # SL 已在当前价上方 → 用 ATR 缓冲重算
        sl_price = current_price - self.atr_value * 0.5
        self.log.warning(f"SL adjusted: would immediately trigger. New: {sl_price}")
    if side == 'SHORT' and sl_price <= current_price:
        sl_price = current_price + self.atr_value * 0.5
        self.log.warning(f"SL adjusted: would immediately trigger. New: {sl_price}")
    return sl_price
```

### 5.4 修复 GTC 过期无恢复 (Bug #11)

```python
# 改进 on_order_expired():
def on_order_expired(self, event):
    # 现有: 日志 + 告警

    # 新增: 检查仓位是否仍存在
    current_position = self._get_current_position_data()
    if current_position:
        # 仓位还在但 SL/TP 过期了 → 仓位无保护!
        self.log.error("CRITICAL: Position exists but SL/TP expired!")
        self._resubmit_sltp_if_needed(current_position)
    else:
        # 仓位已不存在 → 正常 (SL/TP fill 后的预期过期)
        self._clear_position_state()
```

---

## 六、模块拆分

**当前 `sr_zone_calculator.py` 1461 行，新增后预计 ~1900 行。需要拆分。**

```
utils/
├── sr_zone_calculator.py        # 编排器: _collect_candidates, _cluster_to_zones (保留)
├── sr_swing_detector.py         # 新文件: MTF swing 检测 + 成交量加权
├── sr_volume_profile.py         # 新文件: VP (VPOC/VAH/VAL) + Range Uniform Distribution
├── sr_pivot_calculator.py       # 新文件: Daily/Weekly Pivot Points
└── sr_sltp_calculator.py        # 新文件: 统一 SL/TP 计算 (calculate_sr_based_sltp)
```

### 各模块预估行数

| 模块 | 内容 | 预估行数 |
|------|------|---------|
| `sr_zone_calculator.py` | 编排 + 聚类 + 评分 + 报告 (瘦身后) | ~900 |
| `sr_swing_detector.py` | Williams Fractal + MTF + 成交量加权 | ~250 |
| `sr_volume_profile.py` | VP + Range Distribution + VPOC/VAH/VAL | ~200 |
| `sr_pivot_calculator.py` | Daily/Weekly Pivot + PROJECTED 标记 | ~150 |
| `sr_sltp_calculator.py` | 统一 SL/TP + 15 分钟闭环 + 当前价验证 | ~200 |

---

## 七、配置

```yaml
# configs/base.yaml 新增/修改

sr_zones:
  enabled: true

  swing_detection:
    enabled: true
    left_bars: 5
    right_bars: 5
    max_swing_age: 100
    # v4.0: 成交量加权 (百分位数连续缩放, 无额外参数)
    volume_weighting: true

  # v4.0: 投射层
  pivots:
    enabled: true
    daily: true
    weekly: true
    projected_max_strength: "MEDIUM"    # 投射来源强度上限

  # v4.0: Volume Profile (确认层)
  volume_profile:
    enabled: true
    bars_source: "15m"                  # 使用 15M bars (与检测层解耦)
    lookback_bars: 96                   # 24 小时
    value_area_pct: 70
    min_bins: 30
    max_bins: 80

  # v4.0: Round Number
  round_number:
    btc_step: 5000
    count: 3

  # v4.0: 聚合规则
  aggregation:
    same_data_weight_cap: 2.5           # 同源聚合权重上限
    confluence_bonus_2_sources: 0.2     # 2 种独立来源 bonus
    confluence_bonus_3_sources: 0.5     # 3+ 种独立来源 bonus

# SL/TP 统一配置
trading_logic:
  sltp_method: "sr_based"               # v4.0: 改为 S/R 驱动
  atr_buffer_multiplier: 0.5            # SL = S/R zone ± ATR × 0.5
  min_rr_ratio: 1.5
  min_sl_distance_pct: 0.01             # 1% 最小 SL 距离 (安全网)
  dynamic_sltp_update: true             # 每 15 分钟动态更新
  dynamic_update_threshold_pct: 0.002   # 0.2% 变化阈值才实际更新
  sl_only_favorable: true               # SL 只能向有利方向移动
```

---

## 八、向后兼容

| 场景 | 行为 |
|------|------|
| MTF 未启用 | 回退到只用 15M bars (v3.1 行为) |
| `trend_manager` 未初始化 | 跳过日线 swing 和 Weekly Pivot |
| `decision_manager` 未初始化 | 跳过 4H swing |
| `bars_data` 传入是 `List` 而非 `Dict` | 兼容 v3.1: 当作 15M bars |
| `sltp_method: "legacy"` | 使用旧版 `calculate_technical_sltp()` |
| `dynamic_sltp_update: false` | 仅使用 trailing stop (旧行为) |

---

## 九、实施步骤

| 阶段 | 步骤 | 内容 | 影响范围 |
|------|------|------|---------|
| **A: 订单安全修复** | A1 | `on_order_expired()` / `on_order_rejected()` 增加状态清理和恢复 | `deepseek_strategy.py` |
| | A2 | `on_position_opened()` 增加 SL vs current_price 验证 | `deepseek_strategy.py` |
| | A3 | `_reduce_position()` 后更新 SL/TP 数量 | `deepseek_strategy.py` |
| **B: 模块拆分** | B1 | 创建 `sr_swing_detector.py` 提取 swing 检测逻辑 | 纯重构 |
| | B2 | 创建 `sr_volume_profile.py` (Range Uniform Distribution) | 新文件 |
| | B3 | 创建 `sr_pivot_calculator.py` (Daily + Weekly) | 新文件 |
| | B4 | 创建 `sr_sltp_calculator.py` (`calculate_sr_based_sltp`) | 新文件 |
| **C: S/R v4.0** | C1 | `_detect_swing_points()` 增加 timeframe 参数 + 成交量加权 | 修改 |
| | C2 | `_collect_candidates()` 集成新来源 + PROJECTED 标记 | 修改 |
| | C3 | `calculate()` 接受 `bars_data_mtf` + `daily_bar` + `weekly_bar` | 修改 (兼容) |
| | C4 | 权重表 + 聚合规则更新 | 修改 |
| | C5 | AI 报告模板增加 PROJECTED 标注 | 修改 |
| **D: SL/TP 闭环** | D1 | `deepseek_strategy.py`: 收集 MTF bars 传入 S/R | 修改 |
| | D2 | `on_timer()` 增加 `_reevaluate_sltp_for_existing_position()` | 修改 |
| | D3 | Trailing stop 与 S/R 动态更新取有利值 | 修改 |
| **E: 配置** | E1 | `configs/base.yaml` 添加 v4.0 配置 | 修改 |

**建议实施顺序: A → B → C → D → E (先修 Bug, 再拆模块, 再加功能)**

---

## 十、验证计划

### 10.1 订单安全验证 (阶段 A)

1. **模拟手动平仓**: 在 Binance APP 手动平仓，观察系统是否正确清理状态
2. **模拟减仓**: 使用 `/partial_close 50`，验证 SL/TP 数量更新
3. **模拟价格快速移动**: SL 设在入场价 -1%，但当前价已跌 2%，验证 SL 自动调整

### 10.2 S/R 质量验证 (阶段 C)

1. **ATH 场景**: 手动设 current_price > 所有 bars 最高价，确认上方有 Pivot 投射
2. **MTF 一致性**: 验证 1D swing 被标为 MAJOR，15M swing 为 MINOR
3. **VP 解耦验证**: VP 和 Swing 的 zone 重合时权重不超过 `same_data_weight_cap`
4. **PROJECTED 标注**: 确认 Pivot 来源的 zone 强度不超过 MEDIUM

### 10.3 SL/TP 闭环验证 (阶段 D)

1. **开仓+动态一致性**: 开仓 SL/TP 和 15 分钟后重算的结果在 S/R 不变时应一致
2. **SL 有利方向**: LONG 仓位的 SL 只能上移
3. **TP 可双向**: 新 S/R 出现时 TP 可以调整
4. **Trailing + S/R 取有利值**: 两者都触发时取更有利的 SL

### 10.4 离线回测工具 (后续)

```bash
# 用历史 bars 计算 S/R，然后检查后续价格是否在 zone 处反弹
python3 scripts/backtest_sr_quality.py --symbol BTCUSDT --days 30
# 输出: Precision, Recall, 各来源贡献度
```

---

## 十一、学术参考

| 编号 | 论文/来源 | 贡献 | 适用性说明 |
|------|----------|------|-----------|
| [1] | Spitsin et al. (2025) Contemporary Mathematics 6(6) | 成交量加权极值 + L1 聚类 | 美股样本 (AAPL/MSFT/TSLA)，P 值为参考基线 |
| [2] | Chung & Bellotti (2021) arXiv:2101.07410 | 触碰记忆效应 + 时间衰减 | 系统已实现 age_factor + touch_count |
| [3] | Osler (2003) Journal of Finance | 整数位订单聚集效应 | 直接适用于 BTC ($5k/$10k) |
| [4] | Chan et al. (2022) MDPI Mathematics 10(20):3888 | S/R 特征 → ML 盈利 +65% | Swing 检测方法参考 |
| [5] | SHS Conferences (2021) | VPOC 90% 反应率 (WIG20) | WIG20 指数，BTC 需验证 |
| [6] | Tsinaslanidis et al. (2022) Expert Systems | Fibonacci Retracement 证伪 | 适用: 不实现 Fibonacci |
| [7] | CME Market Profile User Guide | VP 标准算法 | 行业标准 |
| [8] | Bulkowski, Thomas (2021) Encyclopedia of Chart Patterns | Measured Move 85% hit rate | 仅参考，暂不实施 |
