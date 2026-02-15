# S/R v4.0 + SL/TP 全链路重构 — 统一设计方案 (修订版 R4)

> 修订历史:
> - R1: 初版 S/R v4.0 方案
> - R2: 整合三大风险修正 + 5 大订单 Bug 修复 + SL/TP 一致性重构
> - R3: 补全 12 个集成细节 — 数据类型定义、完整调用链、配置传播、错误隔离、Bug-9 异步修正
> - R4: 补全 13 个 GAP — ATR 缓存、pivot_data 迁移、字段名修正、辅助方法定义、实施顺序修正、安全灰度发布
>
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

- **两阶段订单提交** (v4.13→v4.17): LIMIT entry @ validated price → `_pending_sltp` → SL/TP 分别提交
- **R/R >= 1.5 硬门槛**: `validate_multiagent_sltp()` + `calculate_sr_based_sltp()` 一致执行 (v4.3: 无百分比兜底)
- **Binance API 优先**: `_get_current_position_data()` 优先 API 而非缓存
- **OCO 手动取消**: `on_order_filled()` 取消对方订单
- **历史 bar 预加载**: `_prefetch_multi_timeframe_bars()` 启动时加载 220 根 1D bar（冷启动已解决）
- **ATR 自适应聚类**: zone 合并阈值随波动率调整 (贪婪顺序合并，ATR 阈值补偿)
- **Touch Count 评分**: 2-3 次最优，4+ 次递减 (Chung 2021)
- **时间衰减**: `age_factor = max(0.5, 1.0 - bars_ago/max_age * 0.5)` (已实现)
- **S/R Flip**: 突破的阻力变支撑 (v3.1 已实现)

> **关于 Spitsin L1 聚类 vs 当前贪婪合并:**
> Spitsin (2025) 使用 L1-norm (Manhattan distance) 聚类找最优 zone 中心，对异常值更稳健。
> 当前系统使用贪婪顺序合并 (价格排序后间距 < ATR 阈值合并)，算法更简单、更快。
> **有意取舍**: ATR 自适应阈值部分补偿了贪婪合并的精度不足。L1 聚类作为后续优化项
> 保留 (可通过 A/B 测试评估差异)，当前阶段不引入以控制复杂度。

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
5. **优雅降级** — 任何层失败时有明确的回退路径，per-layer 错误隔离

> **注**: Spitsin (2025) 发表于 Contemporary Mathematics (IF ~0.7)，样本为美股 (AAPL/MSFT/TSLA)。
> BTC 永续合约有 24/7 交易、杠杆清算、资金费率等独特性。
> 论文的 P=0.81-0.88 是参考基线而非直接预期目标。
> AI 可参考的量化先验: "成交量确认的 S/R 历史反弹率约 85% (Spitsin 2025, 美股基线)"。

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

### 3.3 数据类型定义变更 (R3 新增)

**当前 `SRSourceType` (sr_zone_calculator.py L55-59) 缺少 `PROJECTED` 和 `PSYCHOLOGICAL`。**

```python
# ===== 修改 sr_zone_calculator.py L55-59 =====
class SRSourceType:
    """S/R 来源类型"""
    ORDER_FLOW = "ORDER_FLOW"       # 订单流 (Order Wall) - 最实时
    TECHNICAL = "TECHNICAL"         # 技术指标 (SMA, BB) - 广泛认可
    STRUCTURAL = "STRUCTURAL"       # 结构性 (前高/前低, Swing Point) - 历史验证
    PROJECTED = "PROJECTED"         # v4.0 新增: 数学投射 (Pivot Points) - 无历史确认
    PSYCHOLOGICAL = "PSYCHOLOGICAL" # v4.0 新增: 心理关口 (Round Numbers)
```

**当前 `SRCandidate` (L62-72) 缺少 `timeframe` 字段，无法实现同源封顶。**

```python
# ===== 修改 sr_zone_calculator.py L62-72 =====
@dataclass
class SRCandidate:
    """S/R 候选价位"""
    price: float
    source: str
    weight: float
    side: str
    extra: Dict = field(default_factory=dict)
    level: str = SRLevel.MINOR
    source_type: str = SRSourceType.TECHNICAL
    timeframe: str = ""  # v4.0 新增: "1d", "4h", "15m", "daily_pivot", "weekly_pivot"
```

**`timeframe` 字段赋值规则：**

| 候选来源 | timeframe 值 | 说明 |
|---------|-------------|------|
| 1D Swing | `"1d"` | 日线 swing point |
| 4H Swing | `"4h"` | 4H swing point |
| 15M Swing | `"15m"` | 15M swing point |
| Daily Pivot | `"daily_pivot"` | 日线 Pivot |
| Weekly Pivot | `"weekly_pivot"` | 周线 Pivot |
| VP (VPOC/VAH/VAL) | `"15m_vp"` | 15M Volume Profile |
| Order Wall | `"realtime"` | 实时盘口 |
| SMA/BB | `"15m"` | 当前 15M 指标 |
| Round Number | `"static"` | 静态计算 |

**同源判定规则：`timeframe` 字段相同即为"同源"。**
- 1D Swing + 4H Swing = 不同源 (✅ 不封顶)
- 1D Swing + 1D Swing = 同源 (⚠️ 封顶 2.5)
- Daily Pivot R1 + Daily Pivot R2 = 同源 (⚠️ 封顶 2.5)
- Daily Pivot + Weekly Pivot = 不同源 (✅ 不封顶)

> **R4 关键注意 (G6): Phase B+D 必须原子部署。**
> 如果添加 `timeframe` 字段 (Phase B) 并启用同源封顶 (Phase D)，
> 但没有同时更新**所有现有候选生成器**设置 `timeframe`，
> 所有未设置 timeframe 的候选将归入 `"unknown"` 桶并被封顶 2.5 —
> 这会导致 zone 质量回退到 v3.1 以下。
>
> **必须同时修改的现有代码 (Phase B 中一并完成):**
> - `_detect_swing_points()` L730-732: 给 swing 候选添加 `timeframe="15m"`
> - `_bb_candidates()` L740-757: 给 BB 候选添加 `timeframe="15m"`
> - `_sma_candidates()` L764-784: 给 SMA 候选添加 `timeframe="15m"`
> - `_orderwall_candidates()` L816-864: 给 Order Wall 候选添加 `timeframe="realtime"`
> - `_generate_round_number_levels()` L466-473: 给 Round Number 候选添加 `timeframe="static"`
> - 旧版 Pivot (L866-893): 将在 Phase C/D 中删除并由 `sr_pivot_calculator` 替代

### 3.4 候选来源和权重

```
_collect_candidates()
  │
  │ ===== 检测层 (STRUCTURAL) =====
  │
  ├ 1D Swing (成交量加权)           权重 2.0  level=MAJOR      timeframe="1d"
  ├ 4H Swing (成交量加权)           权重 1.5  level=INTERMEDIATE timeframe="4h"
  ├ 15M Swing (成交量加权)          权重 0.8  level=MINOR      timeframe="15m"
  │   └ 成交量加权: 百分位数连续缩放 (见 3.6)
  │
  │ ===== 投射层 (PROJECTED, 强度上限 MEDIUM) =====
  │
  ├ Daily Pivot (PP/R1/R2/R3/S1/S2/S3)   权重 1.0  level=MAJOR  timeframe="daily_pivot"
  ├ Weekly Pivot (PP/R1/R2/S1/S2)         权重 1.2  level=MAJOR  timeframe="weekly_pivot"
  │
  │ ===== 确认层 (STRUCTURAL, 独立数据源) =====
  │
  ├ Volume Profile VPOC/VAH/VAL           权重 1.3  level=INTERMEDIATE timeframe="15m_vp"
  │   └ 基于 15M 近 24h bars (与检测层 1D/4H 解耦)
  │   └ Range Uniform Distribution (按 OHLC 范围比例分配 volume)
  │
  ├ Order Wall (实时盘口)                 权重 0.8  level=MINOR  timeframe="realtime"
  │
  │ ===== 辅助 (PSYCHOLOGICAL) =====
  │
  └ Round Number (BTC: $5000 步长)        权重 0.5  level=MINOR  timeframe="static"
```

**权重说明：这些是初始估计值，需通过离线回测校准。设计原则：高时间框架 > 低时间框架，历史验证 > 投射。**

> **R4 修复 (G13)**: SMA_200 source 标签从 `"SMA_200"` 改为 `"SMA_200_15M"`
> 明确标注这是 15M 周期的 SMA_200 (≈ 50 小时), 不是日线 SMA_200 (≈ 200 天)。
> 同时在 AI 报告中注明: `"SMA_200 基于 15 分钟周期 (≈ 50 小时, 非日线 200 天)"`。
> 修改位置: `sr_zone_calculator.py` L777-784 的 `source='SMA_200'` → `source='SMA_200_15M'`。

### 3.5 聚合规则 (R3 补全执行细节)

**三条规则在 `_create_zone()` 中顺序执行：**

```python
def _create_zone(self, cluster: List[SRCandidate], current_price: float) -> SRZone:
    """
    从候选簇创建 S/R Zone。
    v4.0: 新增同源封顶、多源奖励、PROJECTED 强度封顶、总权重上限。
    """
    # ========== 步骤 1: 同源聚合封顶 (在求和时执行) ==========
    # 按 timeframe 分组，每组权重和不超过 SAME_DATA_WEIGHT_CAP
    SAME_DATA_WEIGHT_CAP = 2.5

    weight_by_timeframe = {}
    for c in cluster:
        tf = c.timeframe or "unknown"
        weight_by_timeframe.setdefault(tf, 0.0)
        weight_by_timeframe[tf] = min(
            weight_by_timeframe[tf] + c.weight,
            SAME_DATA_WEIGHT_CAP
        )

    # 总权重 = 各时间框架封顶后的权重之和
    total_weight = sum(weight_by_timeframe.values())

    # ========== 步骤 2: 多源独立性奖励 ==========
    unique_source_types = len(set(c.source_type for c in cluster))
    if unique_source_types >= 3:
        total_weight += 0.5   # STRUCTURAL + ORDER_FLOW + PROJECTED 等
    elif unique_source_types >= 2:
        total_weight += 0.2

    # ========== 步骤 3: 总权重上限 (防止极端分数差距) ==========
    MAX_ZONE_WEIGHT = 6.0
    total_weight = min(total_weight, MAX_ZONE_WEIGHT)

    # ========== 步骤 4: 评估强度 (含 PROJECTED 封顶) ==========
    strength = self._evaluate_strength_v4(total_weight, cluster)

    # ========== R4 G7: 更新 type_priority (新增 PROJECTED + PSYCHOLOGICAL) ==========
    # 当前 L1011-1015 的 type_priority 只有 3 种类型，需扩展:
    type_priority = {
        SRSourceType.ORDER_FLOW: 4,      # 最实时
        SRSourceType.STRUCTURAL: 3,      # 历史验证
        SRSourceType.PROJECTED: 2,       # v4.0: 数学投射
        SRSourceType.TECHNICAL: 1,       # 技术指标
        SRSourceType.PSYCHOLOGICAL: 0,   # v4.0: 心理关口 (最低优先级)
    }
    zone_source_type = SRSourceType.TECHNICAL
    for c in cluster:
        if type_priority.get(c.source_type, 0) > type_priority.get(zone_source_type, 0):
            zone_source_type = c.source_type

    # ... 构建 SRZone (zone_source_type 用于 SRZone.source_type) ...
```

**步骤 4 的 `_evaluate_strength_v4` 详细逻辑：**

```python
def _evaluate_strength_v4(self, total_weight: float, cluster: List[SRCandidate]) -> str:
    """
    评估 zone 强度，增加 PROJECTED 封顶逻辑。

    规则:
    - total_weight >= 3.0 → HIGH (除非被 PROJECTED 封顶)
    - total_weight >= 1.5 → MEDIUM
    - 其他 → LOW

    PROJECTED 封顶:
    - 如果 zone 的所有候选都是 PROJECTED 类型 → 强度上限 MEDIUM
    - 如果有任何 STRUCTURAL 或 ORDER_FLOW 候选确认 → 解除封顶 (允许 HIGH)
    """
    # 基础强度判断 (同 v3.1)
    has_order_wall = any(c.source_type == SRSourceType.ORDER_FLOW for c in cluster)
    wall_btc = sum(c.extra.get('wall_size_btc', 0) for c in cluster if c.source_type == SRSourceType.ORDER_FLOW)

    if total_weight >= self.STRENGTH_THRESHOLDS['HIGH'] or wall_btc >= 100.0:
        base_strength = 'HIGH'
    elif total_weight >= self.STRENGTH_THRESHOLDS['MEDIUM']:
        base_strength = 'MEDIUM'
    else:
        base_strength = 'LOW'

    # PROJECTED 封顶规则
    source_types_in_zone = set(c.source_type for c in cluster)
    has_confirmed = bool(source_types_in_zone & {SRSourceType.STRUCTURAL, SRSourceType.ORDER_FLOW})

    if not has_confirmed and SRSourceType.PROJECTED in source_types_in_zone:
        # Zone 仅由 PROJECTED (+ 可能的 TECHNICAL/PSYCHOLOGICAL) 组成
        # 无历史交易确认 → 强度封顶 MEDIUM
        if base_strength == 'HIGH':
            base_strength = 'MEDIUM'

    return base_strength
```

**强度阈值 (维持 v3.1 值)：**

```python
STRENGTH_THRESHOLDS = {
    'HIGH':   3.0,   # 维持 v3.1 值 (不贸然提高，待回测校准)
    'MEDIUM': 1.5,   # 维持 v3.1 值
    'LOW':    0.0,
}
```

### 3.6 成交量加权算法 (百分位数连续缩放)

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

### 3.7 Volume Profile 算法 (Range Uniform Distribution)

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

### 3.8 Pivot Points (Daily + Weekly)

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

    for bar, period, base_weight, tf in [
        (daily_bar, 'Daily', 1.0, 'daily_pivot'),
        (weekly_bar, 'Weekly', 1.2, 'weekly_pivot'),
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
                source_type=SRSourceType.PROJECTED,
                timeframe=tf,  # v4.0: 用于同源封顶
            ))

    return candidates
```

**Weekly Pivot 数据来源：** 从 `trend_manager` 的 1D bars 中聚合最近 5 根获取周 H/L/C。无需额外数据源。

### 3.9 AI 报告中的 PROJECTED 标注

AI 报告模板变更在 `generate_ai_detailed_report()` 中实现。
Bull/Bear/Judge/Risk Manager 四个 agent 都通过 `sr_zones_for_risk` 接收同一份报告。

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

📊 S/R 历史反弹率参考: ~85% (Spitsin 2025, 美股基线; BTC 需验证)
```

### 3.10 编排器 `_collect_candidates()` 完整调用 (R3 新增)

**编排器 `sr_zone_calculator.py` 的 `_collect_candidates()` 需要调用所有检测模块。
每个模块调用用 try/except 包裹，确保单一模块失败不影响其他模块。**

```python
def _collect_candidates(
    self,
    current_price: float,
    bb_data: Optional[Dict],
    sma_data: Optional[Dict],
    orderbook_anomalies: Optional[Dict],
    bars_data_15m: Optional[List[Dict]] = None,
    bars_data_4h: Optional[List[Dict]] = None,
    bars_data_1d: Optional[List[Dict]] = None,
    daily_bar: Optional[Dict] = None,
    weekly_bar: Optional[Dict] = None,
    atr_value: float = 0,
) -> List[SRCandidate]:
    """
    收集所有来源的 S/R 候选。
    v4.0: 每个来源独立 try/except — 单一模块失败不影响其他模块。
    """
    candidates = []

    # ===== 检测层: MTF Swing Points (per-layer error isolation) =====
    if self.swing_detection_enabled:
        # 1D Swing
        if bars_data_1d:
            try:
                candidates.extend(
                    self.swing_detector.detect(bars_data_1d, timeframe="1d",
                                               base_weight=2.0, level=SRLevel.MAJOR)
                )
            except Exception as e:
                self.logger.warning(f"1D Swing detection failed: {e}")

        # 4H Swing
        if bars_data_4h:
            try:
                candidates.extend(
                    self.swing_detector.detect(bars_data_4h, timeframe="4h",
                                               base_weight=1.5, level=SRLevel.INTERMEDIATE)
                )
            except Exception as e:
                self.logger.warning(f"4H Swing detection failed: {e}")

        # 15M Swing (保持兼容)
        if bars_data_15m:
            try:
                candidates.extend(
                    self.swing_detector.detect(bars_data_15m, timeframe="15m",
                                               base_weight=0.8, level=SRLevel.MINOR)
                )
            except Exception as e:
                self.logger.warning(f"15M Swing detection failed: {e}")

    # ===== 投射层: Pivot Points =====
    if self.config.get('pivots', {}).get('enabled', True):
        try:
            candidates.extend(
                self.pivot_calculator.calculate(daily_bar, weekly_bar, current_price)
            )
        except Exception as e:
            self.logger.warning(f"Pivot calculation failed: {e}")

    # ===== 确认层: Volume Profile =====
    if self.config.get('volume_profile', {}).get('enabled', True):
        try:
            candidates.extend(
                self.volume_profile.calculate(bars_data_15m, current_price)
            )
        except Exception as e:
            self.logger.warning(f"Volume Profile failed: {e}")

    # ===== 现有来源: BB, SMA, OrderWall, Round# (保持不变) =====
    try:
        candidates.extend(self._bb_candidates(bb_data, current_price))
    except Exception as e:
        self.logger.warning(f"BB candidates failed: {e}")

    try:
        candidates.extend(self._sma_candidates(sma_data, current_price))
    except Exception as e:
        self.logger.warning(f"SMA candidates failed: {e}")

    try:
        candidates.extend(self._orderwall_candidates(orderbook_anomalies, current_price))
    except Exception as e:
        self.logger.warning(f"OrderWall candidates failed: {e}")

    try:
        candidates.extend(self._round_number_candidates(current_price))
    except Exception as e:
        self.logger.warning(f"Round number candidates failed: {e}")

    return candidates
```

---

## 四、SL/TP 全链路重构

### 4.1 核心原则

```
SL/TP 必须基于 S/R zones + ATR 缓冲，不是固定百分比。
开仓和动态更新使用同一套计算函数。
每 15 分钟闭环: 新 S/R → 新 SL/TP → 验证 → 更新。
```

### 4.2 统一 SL/TP 计算函数 (v4.3 更新)

**修复: `calculate_sr_based_sltp()` — 位于 `utils/sr_sltp_calculator.py`。**

> **v4.3 重要变更**: 移除所有百分比兜底。无 S/R zone 时直接拒绝交易。
> - SL: 无 zone → return (None, None) (不用任意 2% SL)
> - TP: S/R zones + Measured Move 两条路径，无百分比 TP
> - 设计原则: "S/R drives SL/TP" — 没有 S/R 支撑则不交易

```python
def calculate_sr_based_sltp(
    current_price: float,
    side: str,              # 'BUY' or 'SELL'
    sr_zones: Dict,         # S/R zones 计算结果
    atr_value: float,       # 当前 ATR
    min_rr_ratio: float = 1.5,
    atr_buffer_multiplier: float = 0.5,
    **kwargs,               # v4.3: 吸收旧调用方的 default_sl_pct/default_tp_pct
) -> Tuple[Optional[float], Optional[float], str]:
    """
    v4.3: 统一 SL/TP 计算 (基于 S/R zones + ATR 缓冲, 无百分比兜底)

    算法:
    1. SL anchor = 多因子评分选最优 zone (strength + quality + touch + swing + proximity)
       → 无 zone → REJECT
    2. SL = anchor ± ATR buffer
    3. TP = 逐个检查 S/R zones → Measured Move (Bulkowski 2021) → REJECT
    4. R/R >= min_rr_ratio 才有效
    """
    # Step 1: SL anchor (multi-factor scoring)
    sl_anchor = _select_sl_anchor(sl_zones, current_price, is_long, atr_value)
    if not sl_anchor:
        return None, None, "no S/R zone for SL anchor"
    sl = sl_anchor - atr_buffer if is_long else sl_anchor + atr_buffer

    # Step 2: TP candidates (quality-sorted) → Measured Move → reject
    for candidate_tp in tp_candidates:
        if rr >= min_rr_ratio:
            tp = candidate_tp; break
    else:
        mm_target = _measured_move_target(...)  # Bulkowski 2021: 85% hit rate
        if mm_target and rr >= min_rr_ratio:
            tp = mm_target
        else:
            return None, None, "R/R insufficient, all S/R targets failed"

    return sl, tp, method
```

### 4.3 SL/TP 完整调用链 — 开仓路径 + 维护路径 (R3 新增)

**当前系统有两条 SL/TP 路径。R3 明确统一两条路径。**

```
路径 A: 开仓 (_validate_sltp_for_entry, 在 on_position_opened 之前调用)
────────────────────────────────────────────────────────────────────
当前 (v4.12):
  validate_multiagent_sltp()  → 如果 AI 的 SL/TP 通过 R/R 验证 → 用 AI 的
                               → 如果不通过 → calculate_technical_sltp() (旧版)

v4.3 修改:
  validate_multiagent_sltp()  → 如果通过 → 用 AI 的 (不变)
                               → 如果不通过 → calculate_sr_based_sltp() (v4.3, 无百分比兜底)
                                              → 如果 R/R 不满足 → return None (拒绝交易, S/R veto is final)
                                              → ❌ 不再回退到 calculate_technical_sltp() (v4.2 移除)

具体代码位置: deepseek_strategy.py `_validate_sltp_for_entry()`:
  # v4.3: S/R-based SL/TP (无百分比兜底)
  if self.sltp_method == 'sr_based' and hasattr(self, 'latest_sr_zones_data') and self.latest_sr_zones_data:
      sr_sl, sr_tp, reason = calculate_sr_based_sltp(
          current_price=entry_price,
          side=side.name,
          sr_zones=self.latest_sr_zones_data,
          atr_value=self._cached_atr_value,
          min_rr_ratio=self.min_rr_ratio,
          atr_buffer_multiplier=self.atr_buffer_multiplier,
      )
      if sr_sl and sr_tp:
          stop_loss_price, tp_price = sr_sl, sr_tp
      else:
          # v4.3: S/R veto is final — 拒绝交易，不回退到百分比兜底
          return None, None, reason


路径 B: 维护 (每 15 分钟动态更新, on_timer 中调用)
────────────────────────────────────────────────────────────────────
当前 (v4.12):
  _dynamic_sltp_update() → _validate_sltp_for_entry() → 间接用旧版计算

v4.0 修改:
  _reevaluate_sltp_for_existing_position()  ← ⚠️ 替代 _dynamic_sltp_update()
    → 直接调用 calculate_sr_based_sltp() (同路径 A 的计算函数)
    → SL 只能向有利方向移动
    → 与 trailing stop 取有利值
```

**关键: `_reevaluate_sltp_for_existing_position()` 替代 `_dynamic_sltp_update()`，不是共存。**

在 `on_timer()` L1915-1917:

```python
# 当前 (v4.12):
if self.enable_auto_sl_tp:
    self._dynamic_sltp_update()

# v4.0 修改为:
if self.enable_auto_sl_tp and self.dynamic_sltp_update_enabled:
    self._reevaluate_sltp_for_existing_position()
elif self.enable_auto_sl_tp:
    self._dynamic_sltp_update()  # legacy 回退
```

### 4.4 15 分钟动态 SL/TP 更新闭环

**替代 `_dynamic_sltp_update()` (L4378-4478)。使用同一个 `calculate_sr_based_sltp()` 函数。**

```python
def _reevaluate_sltp_for_existing_position(self):
    """
    每 15 分钟基于最新 S/R zones 重新评估 SL/TP。
    替代旧版 _dynamic_sltp_update()。

    规则:
    1. 用 calculate_sr_based_sltp() 计算新 SL/TP (同开仓路径 A)
    2. SL 只能向有利方向移动 (LONG: 只能上移, SHORT: 只能下移)
    3. TP 可以双向调整 (新 S/R 可能比旧的更近或更远)
    4. 变化超过 threshold 才实际更新 (避免频繁修改)
    5. 提交前验证: new_sl 必须未被当前价触发
    6. 与 trailing stop 取有利值 (trailing 更高则用 trailing)
    """
    try:
        current_position = self._get_current_position_data()
        if not current_position:
            return

        side = current_position.get('side', '').lower()
        quantity = abs(float(current_position.get('quantity', 0)))
        if quantity <= 0 or side not in ('long', 'short'):
            return

        # 读取最新 S/R zones (本周期刚在 multi_agent.analyze() 中计算)
        sr_zones = self.latest_sr_zones_data
        if not sr_zones:
            return

        instrument_key = str(self.instrument_id)
        state = self.trailing_stop_state.get(instrument_key)
        if not state:
            return

        old_sl = state.get("current_sl_price")
        old_tp = state.get("current_tp_price")
        if not old_sl or old_sl <= 0:
            return

        current_price = self._cached_current_price

        # 步骤 1: 用统一函数计算
        new_sl, new_tp, reason = calculate_sr_based_sltp(
            current_price=current_price,
            side='BUY' if side == 'long' else 'SELL',
            sr_zones=sr_zones,
            atr_value=self._cached_atr_value,
            min_rr_ratio=self.min_rr_ratio,
            atr_buffer_multiplier=self.atr_buffer_multiplier,
        )

        if new_sl is None:
            return  # R/R 不满足，保持现有

        # 步骤 2: SL 只能向有利方向
        if side == 'long' and new_sl < old_sl:
            new_sl = old_sl
        if side == 'short' and new_sl > old_sl:
            new_sl = old_sl

        # 步骤 5: 提交前验证当前价
        if side == 'long' and new_sl >= current_price:
            return
        if side == 'short' and new_sl <= current_price:
            return

        # 步骤 6: 与 trailing stop 取有利值
        if self.enable_trailing_stop and state.get("activated"):
            trailing_sl = state.get("current_sl_price", 0)
            if side == 'long':
                new_sl = max(new_sl, trailing_sl)
            else:
                new_sl = min(new_sl, trailing_sl)

        # 步骤 4: 变化超过阈值才更新
        sl_changed = abs(new_sl - old_sl) / old_sl > self.dynamic_update_threshold_pct
        tp_changed = old_tp and old_tp > 0 and abs(new_tp - old_tp) / old_tp > self.dynamic_update_threshold_pct

        if not sl_changed and not tp_changed:
            return

        self._replace_sltp_orders(
            new_total_quantity=quantity,
            position_side=side,
            new_sl_price=new_sl,
            new_tp_price=new_tp,
        )

        # Telegram 通知 (复用旧版逻辑)
        # ...

    except Exception as e:
        self.log.warning(f"⚠️ S/R SL/TP reevaluation failed (position still protected): {e}")
```

**与 Trailing Stop 的关系:**

```
Trailing Stop (on_bar, 每根 bar):
  → 快速响应 (价格快速拉升时立即跟踪)
  → 只移动 SL，不动 TP
  → 简单公式: highest × (1 - distance%)
  → 独立运行，更新 trailing_stop_state["current_sl_price"]

S/R 动态更新 (on_timer, 每 15 分钟):
  → 深度分析 (基于最新 S/R zones)
  → SL + TP 都可更新
  → 读取 trailing_stop_state 并与 S/R SL 取有利值
  → 最终结果写回 trailing_stop_state

两者共存规则 (在 _reevaluate 步骤 6 中):
  final_sl = max(trailing_sl, sr_sl)  # LONG 时取更高的
  final_sl = min(trailing_sl, sr_sl)  # SHORT 时取更低的
```

> **R4 修复 (G4)**: trailing_stop_state 中激活标志字段名为 `"activated"` (L4816, L5721, L5735)，
> **不是** `"trailing_active"`。R3 和现有 `_dynamic_sltp_update` L4427 都用了错误的字段名
> `state.get("trailing_active")`，导致 trailing 集成始终被跳过 (返回 None = falsy)。
> R4 已全部修正为 `state.get("activated")`。
> **注意**: 现有 `_dynamic_sltp_update` L4427 也需要修正 (无论是否实施 v4.0)。

---

## 五、订单安全修复

### 5.1 修复手动平仓后报错 (Bug #8)

```python
# 在 on_order_expired() 和 on_order_rejected() 和 on_order_canceled() 中增加:
# ⚠️ R4 (G9): on_order_canceled 也需要覆盖 — Binance algoOrder 被取消时
# NT 可能触发 canceled 而非 expired

def _handle_orphan_order(self, order_id, reason):
    """清理孤儿订单的内部状态"""
    current_position = self._get_current_position_data()

    if not current_position:
        self._clear_position_state()
        self.log.info("Position closed externally, cleared internal state")
    else:
        self._resubmit_sltp_if_needed(current_position)

def _clear_position_state(self):
    """清理所有仓位相关的内部状态 (R4 补全 G5 — 完整实现)"""
    instrument_key = str(self.instrument_id)
    self.trailing_stop_state.pop(instrument_key, None)
    self._pending_sltp = None
    self._pending_reversal = None
    self._pending_reduce_sltp = None   # v4.0 新增
    self.latest_signal_data = None     # 清除旧信号
    self.log.info("🧹 Position state cleared (external close detected)")

def _resubmit_sltp_if_needed(self, current_position):
    """
    检测仓位仍存在但 SL/TP 缺失时，重新提交保护订单。
    (R4 补全 G5 — 完整实现)

    调用场景:
    - Bug #8: 手动平仓导致 SL/TP expired/rejected，但仓位通过其他方式重建
    - Bug #11: GTC 过期后仓位仍在

    策略: 使用 _submit_emergency_sl 提交紧急止损 (2% 固定距离)，
    因为此时可能没有最新的 S/R zones 数据。
    """
    try:
        position_side = current_position.get('side', '').lower()
        quantity = abs(float(current_position.get('quantity', 0)))
        if quantity <= 0 or position_side not in ('long', 'short'):
            return

        # 检查是否已有活跃 SL 订单
        instrument_key = str(self.instrument_id)
        state = self.trailing_stop_state.get(instrument_key)
        if state and state.get("sl_order_id"):
            # SL 订单可能仍有效，不重复提交
            self.log.info("🔍 SL order may still be active, skipping resubmit")
            return

        # 没有活跃 SL → 提交紧急止损
        self.log.warning(f"⚠️ No active SL detected, submitting emergency SL")
        self._submit_emergency_sl(quantity, position_side,
                                  reason="SL/TP expired/rejected, 仓位仍存在")

        # 发送 Telegram 告警
        if self.telegram_bot and self.enable_telegram:
            try:
                alert_msg = self.telegram_bot.format_error_alert({
                    'level': 'CRITICAL',
                    'message': f"SL/TP 过期/被拒 — 已提交紧急止损",
                    'context': f"Side: {position_side}, Qty: {quantity:.4f}",
                })
                self.telegram_bot.send_message_sync(alert_msg)
            except Exception:
                pass
    except Exception as e:
        self.log.error(f"❌ Failed to resubmit SL/TP: {e}")
```

### 5.2 修复减仓后 SL/TP 不更新 (Bug #9) — R3 修正异步问题

**R2 问题**: 假设 `reduce_success` 同步可知，但 `_submit_order()` (L4620) 是异步的 —
减仓 MARKET 单提交后立即返回，实际成交通过 `on_position_changed()` (L5552) 回调通知。**

**R3 修正: SL/TP 更新必须在 `on_position_changed()` 中执行，而非 `_reduce_position()` 内联。**

```python
# ===== 修改 _reduce_position() (L4604-4624) =====
# 当前代码在减仓前取消 SL/TP (L4604-4616)，之后提交减仓 MARKET 单 (L4620)。
# 问题: 取消了 SL/TP 但减仓还没成交，此时仓位无保护。
# 修复: 在 _reduce_position 中设置 _pending_reduce 标记:

def _reduce_position(self, current_position, target_pct):
    # ... 现有验证逻辑 ...

    # 取消现有 SL/TP (保持不变)
    # ... L4604-4616 ...

    # 提交减仓 MARKET 单 (保持不变)
    self._submit_order(side=reduce_side, quantity=reduce_qty, reduce_only=True)

    # v4.0 新增: 标记等待减仓成交 (R4 G8: 增加时间戳和互斥检查)
    import time
    assert not self._pending_sltp, "Cannot reduce while _pending_sltp is active"  # R4 G12: 互斥断言
    self._pending_reduce_sltp = {
        'expected_quantity': current_qty - reduce_qty,  # 减仓后预期数量
        'position_side': current_side,
        'old_sl': state.get('current_sl_price'),  # 保持原 SL 价格
        'old_tp': state.get('current_tp_price'),   # 保持原 TP 价格
        'timestamp': time.time(),                   # R4 G8: 超时检测用
        'reduce_order_side': reduce_side.name,      # R4 G8: 事件关联用
    }


# ===== 修改 on_position_changed() (L5552+) =====
def on_position_changed(self, event):
    # ... 现有日志逻辑 ...

    # v4.0 新增: 减仓成交后重建 SL/TP (R4 G8: 增加超时和事件关联检查)
    if hasattr(self, '_pending_reduce_sltp') and self._pending_reduce_sltp:
        pending = self._pending_reduce_sltp
        import time
        elapsed = time.time() - pending.get('timestamp', 0)

        # R4 G8: 超时清理 (60 秒内未触发说明减仓单可能被拒)
        if elapsed > 60:
            self.log.warning(f"⚠️ _pending_reduce_sltp expired ({elapsed:.0f}s), clearing stale state")
            self._pending_reduce_sltp = None
            return  # 不处理，等下一个 on_timer 周期的 _resubmit_sltp_if_needed

        # R4 G8: 事件关联检查 — 确认是减仓导致的 position change
        new_qty = float(event.quantity)
        expected_qty = pending.get('expected_quantity', 0)
        qty_matches = abs(new_qty - expected_qty) / max(expected_qty, 0.0001) < 0.05  # 5% 容差

        if not qty_matches:
            # 可能是其他原因导致的 position change (如 SL 触发)
            self.log.warning(
                f"⚠️ Position change qty {new_qty:.4f} != expected {expected_qty:.4f}, "
                f"not consuming _pending_reduce_sltp"
            )
            return

        self._pending_reduce_sltp = None  # 清除标记
        self.log.info(f"🔄 Reduce filled, rebuilding SL/TP for qty={new_qty:.4f}")

        try:
            self._replace_sltp_orders(
                new_total_quantity=new_qty,
                position_side=pending['position_side'],
                new_sl_price=pending['old_sl'],   # 保持原价
                new_tp_price=pending['old_tp'],    # 保持原价
            )
        except Exception as e:
            self.log.error(f"❌ Failed to rebuild SL/TP after reduce: {e}")
            self._submit_emergency_sl(new_qty, pending['position_side'],
                                      reason="减仓后SL重建失败")

    # ... 现有 trailing stop 更新逻辑 ...
```

### 5.3 修复 SL 未验证当前价 (Bug #10)

```python
# 在 on_position_opened() 提交 SL 前增加:
def _validate_sl_against_current_price(self, sl_price, side, current_price):
    """确保 SL 不会立即触发"""
    if side == 'LONG' and sl_price >= current_price:
        sl_price = current_price - self._cached_atr_value * 0.5
        self.log.warning(f"SL adjusted: would immediately trigger. New: {sl_price}")
    if side == 'SHORT' and sl_price <= current_price:
        sl_price = current_price + self._cached_atr_value * 0.5
        self.log.warning(f"SL adjusted: would immediately trigger. New: {sl_price}")
    return sl_price
```

### 5.4 修复 GTC 过期无恢复 (Bug #11)

```python
# 改进 on_order_expired() (L5462+):
def on_order_expired(self, event):
    # 现有: 日志 + 告警

    # 新增: 检查仓位是否仍存在
    current_position = self._get_current_position_data()
    if current_position:
        self.log.error("CRITICAL: Position exists but SL/TP expired!")
        self._resubmit_sltp_if_needed(current_position)
    else:
        self._clear_position_state()
```

---

## 六、完整数据流链路 (R3 新增)

### 6.1 MTF Bar 提取和传递

**当前问题**: `on_timer()` 只提取 15M bars (L1812)，1D/4H bars 存在于 MTF manager 但未传给 S/R。

**修复位置: `deepseek_strategy.py` on_timer() L1811-L1831**

```python
# ===== 当前代码 (L1811-1812) =====
sr_bars_data = self.indicator_manager.get_kline_data(count=120)

# ===== v4.0 修改为 =====
# 提取 15M bars (确认层 VP + 15M swing)
sr_bars_15m = self.indicator_manager.get_kline_data(count=96)

# 提取 1D bars (检测层 1D swing + Pivot)
sr_bars_1d = None
daily_bar = None
weekly_bar = None
if hasattr(self, 'mtf_manager') and self.mtf_manager:
    trend_mgr = self.mtf_manager.trend_manager
    if trend_mgr and hasattr(trend_mgr, 'recent_bars') and len(trend_mgr.recent_bars) >= 5:
        # 转换 NautilusTrader Bar → Dict
        sr_bars_1d = [
            {'high': float(b.high), 'low': float(b.low),
             'close': float(b.close), 'open': float(b.open),
             'volume': float(b.volume)}
            for b in trend_mgr.recent_bars
        ]
        # 最近完成的日线 bar (用于 Daily Pivot)
        daily_bar = sr_bars_1d[-1]
        # 聚合最近 5 根 1D → Weekly bar
        last_5 = sr_bars_1d[-5:]
        weekly_bar = {
            'high': max(b['high'] for b in last_5),
            'low': min(b['low'] for b in last_5),
            'close': last_5[-1]['close'],
        }

# 提取 4H bars (检测层 4H swing)
sr_bars_4h = None
if hasattr(self, 'mtf_manager') and self.mtf_manager:
    decision_mgr = self.mtf_manager.decision_manager
    if decision_mgr and hasattr(decision_mgr, 'recent_bars') and len(decision_mgr.recent_bars) >= 5:
        sr_bars_4h = [
            {'high': float(b.high), 'low': float(b.low),
             'close': float(b.close), 'open': float(b.open),
             'volume': float(b.volume)}
            for b in decision_mgr.recent_bars
        ]
```

### 6.2 ATR 缓存变量: `_cached_atr_value` (R4 新增 — 修复 G1)

**R3 问题**: `_cached_atr_value` 在 3 处引用 (Section 4.3, 4.4, 5.3) 但从未定义初始化和更新逻辑。
当前代码中只有 `_cached_current_price` (L312)，没有 `_cached_atr_value`。

**修复: 在策略初始化中添加，在 on_timer 数据采集阶段更新。**

```python
# ===== 修改 1: deepseek_strategy.py __init__ (L312 附近) =====
self._cached_current_price: float = 0.0
self._cached_atr_value: float = 0.0    # v4.0 新增: S/R SL/TP 计算用

# ===== 修改 2: on_timer() 数据采集阶段 (L1811+ 附近, 在 MTF bar 提取之后) =====
# 在提取 sr_bars_15m 后立即计算 ATR
sr_bars_15m = self.indicator_manager.get_kline_data(count=96)

# v4.0: 缓存 ATR (基于 15M bars, 与 sr_zone_calculator 一致)
if sr_bars_15m:
    from utils.sr_zone_calculator import SRZoneCalculator
    self._cached_atr_value = SRZoneCalculator._calculate_atr_from_bars(sr_bars_15m)
```

**设计决策:**
- **用 15M bars 计算 ATR** — 与 `sr_zone_calculator.py` L629 一致 (`_calculate_atr_from_bars(bars_data)`)
- **在 on_timer 头部更新** — 确保同一周期内 `_reevaluate_sltp` 和 `_validate_sltp_for_entry` 读到相同值
- **使用 `@staticmethod`** — `_calculate_atr_from_bars` 已是静态方法 (L363)，可直接调用
- **`__init__` 中默认 0.0** — 首次 on_timer 之前调用 `calculate_sr_based_sltp()` 时，ATR=0 会走 fallback 路径

**生命周期:**

```
__init__: _cached_atr_value = 0.0
     ↓
on_timer() 数据采集:
  sr_bars_15m = get_kline_data(96)
  _cached_atr_value = _calculate_atr_from_bars(sr_bars_15m)  ← 每 15 分钟更新
     ↓
on_timer() 后续使用:
  _validate_sltp_for_entry()  → 读 _cached_atr_value
  _reevaluate_sltp_for_existing_position() → 读 _cached_atr_value
  _validate_sl_against_current_price() → 读 _cached_atr_value
```

### 6.3 `analyze()` 接口变更

**修改 `multi_agent_analyzer.py` L409-427 的 `analyze()` 签名:**

```python
def analyze(
    self,
    symbol: str,
    technical_report: Dict[str, Any],
    # ... 现有参数不变 ...
    bars_data: Optional[List[Dict[str, Any]]] = None,
    # ========== v4.0 新增: MTF bars for S/R ==========
    bars_data_4h: Optional[List[Dict[str, Any]]] = None,
    bars_data_1d: Optional[List[Dict[str, Any]]] = None,
    daily_bar: Optional[Dict[str, Any]] = None,
    weekly_bar: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
```

**传递到 `_calculate_sr_zones()`:**

```python
# 修改 _calculate_sr_zones() 签名 (L2373-2378):
def _calculate_sr_zones(
    self,
    current_price: float,
    technical_data: Optional[Dict[str, Any]],
    orderbook_data: Optional[Dict[str, Any]],
    bars_data: Optional[List[Dict[str, Any]]] = None,
    # ========== v4.0 新增 ==========
    bars_data_4h: Optional[List[Dict[str, Any]]] = None,
    bars_data_1d: Optional[List[Dict[str, Any]]] = None,
    daily_bar: Optional[Dict[str, Any]] = None,
    weekly_bar: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # ... 现有 bb_data, sma_data, orderbook 提取 ...

    # v4.0: 传递给 sr_calculator
    result = self.sr_calculator.calculate_with_detailed_report(
        current_price=current_price,
        bb_data=bb_data,
        sma_data=sma_data,
        orderbook_anomalies=orderbook_anomalies,
        bars_data=bars_data,           # 15M (兼容旧参数名)
        bars_data_4h=bars_data_4h,     # v4.0
        bars_data_1d=bars_data_1d,     # v4.0
        daily_bar=daily_bar,           # v4.0
        weekly_bar=weekly_bar,         # v4.0
    )
```

### 6.5 `pivot_data` 参数迁移: `calculate()` + `calculate_with_detailed_report()` (R4 新增 — 修复 G2)

**R3 问题**: R3 只修改了 `_collect_candidates()` 签名 (删除 `pivot_data`，新增 MTF 参数)，
但遗漏了中间层 `calculate()` (L575-585) 和 `calculate_with_detailed_report()` (L1408-1417)。
当前三层签名都有 `pivot_data` 参数。如果只改内层会导致 `TypeError`。

**修复: 三层签名必须同步修改。**

```python
# ===== 当前三层调用链 (v3.1) =====
#
# calculate(current_price, bb_data, sma_data, orderbook_anomalies, pivot_data, bars_data, atr_value)
#     ↓ L634-637:
#     _collect_candidates(current_price, bb_data, sma_data, orderbook_anomalies, pivot_data, bars_data=bars_data)
#
# calculate_with_detailed_report(current_price, bb_data, sma_data, orderbook_anomalies, pivot_data, bars_data, atr_value)
#     ↓ L1427-1435:
#     self.calculate(current_price, bb_data, sma_data, orderbook_anomalies, pivot_data, bars_data, atr_value)

# ===== v4.0 修改后 (统一移除 pivot_data，新增 MTF 参数) =====

# 层 1: calculate()
def calculate(
    self,
    current_price: float,
    bb_data=None,
    sma_data=None,
    orderbook_anomalies=None,
    # v4.0: pivot_data 已移除 — Pivot 改由 sr_pivot_calculator 内部计算
    bars_data=None,              # 15M bars (兼容旧参数名)
    atr_value=None,
    bars_data_4h=None,           # v4.0
    bars_data_1d=None,           # v4.0
    daily_bar=None,              # v4.0
    weekly_bar=None,             # v4.0
    **kwargs,                    # 吸收旧调用方传的 pivot_data
) -> Dict[str, Any]:
    # ... 内部调用:
    candidates = self._collect_candidates(
        current_price=current_price,
        bb_data=bb_data,
        sma_data=sma_data,
        orderbook_anomalies=orderbook_anomalies,
        bars_data_15m=bars_data,
        bars_data_4h=bars_data_4h,
        bars_data_1d=bars_data_1d,
        daily_bar=daily_bar,
        weekly_bar=weekly_bar,
        atr_value=effective_atr,
    )

# 层 2: calculate_with_detailed_report()
def calculate_with_detailed_report(
    self,
    current_price: float,
    bb_data=None, sma_data=None, orderbook_anomalies=None,
    bars_data=None, atr_value=None,
    bars_data_4h=None, bars_data_1d=None,
    daily_bar=None, weekly_bar=None,
    **kwargs,                    # 吸收旧调用方传的 pivot_data
) -> Dict[str, Any]:
    result = self.calculate(
        current_price=current_price, bb_data=bb_data, sma_data=sma_data,
        orderbook_anomalies=orderbook_anomalies, bars_data=bars_data, atr_value=atr_value,
        bars_data_4h=bars_data_4h, bars_data_1d=bars_data_1d,
        daily_bar=daily_bar, weekly_bar=weekly_bar,
    )
    # ... 生成详细报告 ...

# 层 3: _collect_candidates() — 已在 R3 Section 3.10 定义
```

**向后兼容策略:**
- `**kwargs` 吸收旧调用方传入的 `pivot_data=xxx` — 不报错，只是忽略
- 旧的 `_collect_candidates()` 中 L866-893 的 `if pivot_data:` 代码段**需删除**
- `multi_agent_analyzer.py` L2447-2453 当前不传 `pivot_data`，**不受影响**

**需同步删除的旧代码** (`sr_zone_calculator.py` L866-893):

```python
# ===== 删除以下代码段 =====
# Pivot Points (STRUCTURAL type)
if pivot_data:
    for key, price in pivot_data.items():
        # ... 旧版 Pivot 处理 ...
```

此功能由 `sr_pivot_calculator.calculate(daily_bar, weekly_bar, current_price)` 替代 (Section 3.8)。

### 6.6 on_timer() 调用链全貌

```python
# deepseek_strategy.py on_timer() 调用链 (v4.0):

on_timer()
  │
  ├─ [数据采集]
  │   ├─ indicator_manager.get_kline_data(96)     → sr_bars_15m
  │   ├─ mtf_manager.trend_manager.recent_bars    → sr_bars_1d + daily_bar + weekly_bar
  │   ├─ mtf_manager.decision_manager.recent_bars → sr_bars_4h
  │   └─ _cached_atr_value = _calculate_atr_from_bars(sr_bars_15m)  ← R4 新增
  │
  ├─ [AI 分析]
  │   └─ multi_agent.analyze(
  │         bars_data=sr_bars_15m,
  │         bars_data_4h=sr_bars_4h,
  │         bars_data_1d=sr_bars_1d,
  │         daily_bar=daily_bar,
  │         weekly_bar=weekly_bar,
  │         ...
  │       )
  │       └─ _calculate_sr_zones(...)
  │             └─ sr_calculator.calculate_with_detailed_report(...)
  │                   └─ _collect_candidates(bars_data_15m, bars_data_4h, bars_data_1d,
  │                   │                      daily_bar, weekly_bar, ...)
  │                   │    ├─ swing_detector.detect(1d) → STRUCTURAL candidates
  │                   │    ├─ swing_detector.detect(4h) → STRUCTURAL candidates
  │                   │    ├─ swing_detector.detect(15m) → STRUCTURAL candidates
  │                   │    ├─ pivot_calculator.calculate(daily, weekly) → PROJECTED candidates
  │                   │    ├─ volume_profile.calculate(15m) → STRUCTURAL candidates
  │                   │    ├─ _bb_candidates() → TECHNICAL candidates
  │                   │    ├─ _sma_candidates("SMA_200_15M") → TECHNICAL candidates  ← R4: 加后缀
  │                   │    ├─ _orderwall_candidates() → ORDER_FLOW candidates
  │                   │    └─ _round_number_candidates() → PSYCHOLOGICAL candidates
  │                   └─ _cluster_to_zones() → _create_zone() with v4.0 聚合规则
  │
  ├─ [缓存 S/R 结果]
  │   └─ self.latest_sr_zones_data = multi_agent._sr_zones_cache
  │
  ├─ [执行交易]
  │   └─ _execute_trade()
  │       └─ _validate_sltp_for_entry()  ← 路径 A (开仓 SL/TP)
  │           └─ validate_multiagent_sltp() → [fail] → calculate_sr_based_sltp()
  │                                                     → [fail] → return None (拒绝交易)
  │
  ├─ [OCO 清理]
  │   └─ _cleanup_oco_orphans()
  │
  ├─ [S/R 动态 SL/TP]  ← 路径 B (维护 SL/TP) — R4: 移到 trailing 之前 (修复 G11)
  │   └─ _reevaluate_sltp_for_existing_position()  ← 替代 _dynamic_sltp_update()
  │       └─ calculate_sr_based_sltp() → 写入 trailing_stop_state
  │
  └─ [Trailing Stop]  ← R4: 移到最后，读取 _reevaluate 写入的 SL 值
      └─ _update_trailing_stops()
          └─ 如果本周期 _reevaluate 已更新 SL → 与 trailing SL 比较，取有利值
```

> **R4 修改 (G11)**: `_reevaluate_sltp` 移到 `_update_trailing_stops` 之前。
> 原因: 避免同一周期两次 cancel+recreate SL 订单。`_reevaluate` 先基于 S/R zones 计算新 SL/TP
> 并写入 `trailing_stop_state`，`_update_trailing_stops` 再基于价格高点微调，两者只产生一次订单操作。

### 6.7 向后兼容: `bars_data` 参数类型分派

**`sr_zone_calculator.calculate()` 入口增加兼容逻辑:**

```python
def calculate_with_detailed_report(
    self,
    current_price: float,
    bb_data=None,
    sma_data=None,
    orderbook_anomalies=None,
    bars_data=None,          # 旧参数: 15M bars as List[Dict]
    bars_data_4h=None,       # v4.0 新增
    bars_data_1d=None,       # v4.0 新增
    daily_bar=None,          # v4.0 新增
    weekly_bar=None,         # v4.0 新增
    atr_value=None,
):
    """
    向后兼容:
    - 如果只传 bars_data (List[Dict]) → v3.1 行为，当作 15M bars
    - 如果同时传 bars_data + bars_data_4h + bars_data_1d → v4.0 行为
    """
    # 统一为 15M bars (兼容旧调用方)
    bars_data_15m = bars_data

    candidates = self._collect_candidates(
        current_price=current_price,
        bb_data=bb_data,
        sma_data=sma_data,
        orderbook_anomalies=orderbook_anomalies,
        bars_data_15m=bars_data_15m,
        bars_data_4h=bars_data_4h,
        bars_data_1d=bars_data_1d,
        daily_bar=daily_bar,
        weekly_bar=weekly_bar,
        atr_value=atr_value or self._calculate_atr(bars_data_15m),
    )
    # ... 聚类、评分、生成报告 ...
```

---

## 七、模块拆分

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
| `sr_sltp_calculator.py` | 统一 SL/TP + 当前价验证 | ~200 |

---

## 八、配置及传播链 (R3 补全)

### 8.1 YAML 配置

```yaml
# configs/base.yaml 新增/修改

sr_zones:
  enabled: true

  swing_detection:
    enabled: true
    left_bars: 5
    right_bars: 5
    max_swing_age: 100
    volume_weighting: true

  # v4.0: 投射层
  pivots:
    enabled: true
    daily: true
    weekly: true
    projected_max_strength: "MEDIUM"

  # v4.0: Volume Profile (确认层)
  volume_profile:
    enabled: true
    bars_source: "15m"
    lookback_bars: 96
    value_area_pct: 70
    min_bins: 30
    max_bins: 80

  # v4.0: Round Number
  round_number:
    btc_step: 5000
    count: 3

  # v4.0: 聚合规则
  aggregation:
    same_data_weight_cap: 2.5
    max_zone_weight: 6.0
    confluence_bonus_2_sources: 0.2
    confluence_bonus_3_sources: 0.5

# SL/TP 统一配置
trading_logic:
  sltp_method: "legacy"                  # v4.0: "legacy" (默认) 或 "sr_based" — R4 G10: 默认 legacy，显式启用
  atr_buffer_multiplier: 0.5
  min_rr_ratio: 1.5
  min_sl_distance_pct: 0.01
  dynamic_sltp_update: true             # 每 15 分钟动态更新
  dynamic_update_threshold_pct: 0.002
  sl_only_favorable: true
```

### 8.2 配置传播链 (R3 补全)

**`sr_zones.*` 子配置**: 已有完整链路，作为 Dict 透传。

```
ConfigManager.get('sr_zones') → main_live.py L192 (sr_zones_config=...)
  → DeepSeekAIStrategyConfig.sr_zones_config (Dict)
  → strategy.__init__ L451 → MultiAgentAnalyzer(sr_zones_config=...)
  → SRZoneCalculator(config=sr_zones_config)
  ✅ 新增子 key (pivots, volume_profile, aggregation) 自动透传
```

**`trading_logic.*` 新字段**: 当前链路断裂，需要补全。

```python
# ===== 修改 1: main_live.py 加载 trading_logic 新字段 =====
# 在 L192 附近增加:
sltp_method=config_manager.get('trading_logic', 'sltp_method', default='legacy'),
atr_buffer_multiplier=config_manager.get('trading_logic', 'atr_buffer_multiplier', default=0.5),
dynamic_sltp_update=config_manager.get('trading_logic', 'dynamic_sltp_update', default=True),
dynamic_update_threshold_pct=config_manager.get('trading_logic', 'dynamic_update_threshold_pct', default=0.002),

# ===== 修改 2: DeepSeekAIStrategyConfig (L85-133) 增加字段 =====
@dataclass(frozen=True)
class DeepSeekAIStrategyConfig:
    # ... 现有字段 ...

    # v4.0: SL/TP method
    sltp_method: str = "legacy"    # R4 G10: 默认 legacy，部署后通过 YAML 显式切到 sr_based
    atr_buffer_multiplier: float = 0.5
    dynamic_sltp_update: bool = True
    dynamic_update_threshold_pct: float = 0.002

# ===== 修改 3: strategy.__init__ (L272-275 附近) 存储字段 =====
self.sltp_method = config.sltp_method
self.atr_buffer_multiplier = config.atr_buffer_multiplier
self.dynamic_sltp_update_enabled = config.dynamic_sltp_update
self.dynamic_update_threshold_pct = config.dynamic_update_threshold_pct
self.min_rr_ratio = config.min_rr_ratio  # 已有，从 trading_logic 读取
```

**完整传播链 (修复后):**

```
ConfigManager.get('trading_logic', 'sltp_method')
  → main_live.py: sltp_method=...
  → DeepSeekAIStrategyConfig.sltp_method
  → strategy.__init__: self.sltp_method = config.sltp_method
  → _validate_sltp_for_entry(): if self.sltp_method == 'sr_based': ...
  → _reevaluate_sltp_for_existing_position(): self.atr_buffer_multiplier
  ✅ 完整链路
```

---

## 九、向后兼容

| 场景 | 行为 | 实现方式 |
|------|------|---------|
| MTF 未启用 | 只用 15M bars (v3.1 行为) | `bars_data_1d/4h=None` → `_collect_candidates` 跳过相应 swing 检测 |
| `trend_manager` 未初始化 | 跳过日线 swing 和 Weekly Pivot | `if trend_mgr and len(trend_mgr.recent_bars) >= 5:` 检查 |
| `decision_manager` 未初始化 | 跳过 4H swing | 同上 |
| `bars_data` 传入是 `List` (旧调用) | 当作 15M bars | `bars_data_15m = bars_data` (6.4 节) |
| `sltp_method: "legacy"` | 使用旧版 `calculate_technical_sltp()` | 路径 A 中 `if self.sltp_method == 'sr_based':` 分支 (v4.3 默认 sr_based) |
| `dynamic_sltp_update: false` | 使用旧版 `_dynamic_sltp_update()` | on_timer() 中 `if self.dynamic_sltp_update_enabled:` 分支 |
| 旧调用方传入 `pivot_data` | 被 `**kwargs` 吸收，不报错 | `calculate()` 和 `calculate_with_detailed_report()` 的 `**kwargs` |
| `_pending_reduce_sltp` 超时 | 60 秒后自动清理 | `on_position_changed()` 检查 `elapsed > 60` |

---

## 十、实施步骤

| 阶段 | 步骤 | 内容 | 影响范围 |
|------|------|------|---------|
| **A: 订单安全修复** | A1 | `on_order_expired()` / `on_order_rejected()` / `on_order_canceled()` 增加 `_handle_orphan_order` | `deepseek_strategy.py` |
| | A2 | `on_position_opened()` 增加 `_validate_sl_against_current_price` | `deepseek_strategy.py` |
| | A3 | `_reduce_position()` 设 `_pending_reduce_sltp` + `on_position_changed()` 重建 SL/TP (含超时+关联检查) | `deepseek_strategy.py` |
| | A4 | 实现 `_resubmit_sltp_if_needed()` + `_clear_position_state()` | `deepseek_strategy.py` |
| | A5 | 修复 `_dynamic_sltp_update()` L4427: `"trailing_active"` → `"activated"` (现有 bug) | `deepseek_strategy.py` |
| **B: 数据类型 + 现有候选 timeframe** | B1 | `SRSourceType` 增加 `PROJECTED` / `PSYCHOLOGICAL` | `sr_zone_calculator.py` |
| | B2 | `SRCandidate` 增加 `timeframe` 字段 | `sr_zone_calculator.py` |
| | B3 | **所有现有候选生成器**添加 `timeframe` (⚠️ 必须与 B2 原子部署) | `sr_zone_calculator.py` |
| | B4 | `type_priority` 字典添加 `PROJECTED: 2` + `PSYCHOLOGICAL: 0` | `sr_zone_calculator.py` |
| | B5 | SMA_200 source 标签改为 `"SMA_200_15M"` | `sr_zone_calculator.py` |
| **G: 配置** (⚠️ R4 提前到 B 之后) | G1 | `configs/base.yaml` 添加 v4.0 配置 (`sltp_method: "legacy"` 默认) | 修改 |
| | G2 | `main_live.py` 加载 trading_logic 新字段 | 修改 |
| | G3 | `DeepSeekAIStrategyConfig` 增加新字段 | `deepseek_strategy.py` |
| | G4 | `__init__` 添加 `_cached_atr_value = 0.0` + `_pending_reduce_sltp = None` | `deepseek_strategy.py` |
| **C: 模块拆分** | C1 | 创建 `sr_swing_detector.py` 提取 swing 检测逻辑 | 纯重构 |
| | C2 | 创建 `sr_volume_profile.py` (Range Uniform Distribution) | 新文件 |
| | C3 | 创建 `sr_pivot_calculator.py` (Daily + Weekly) | 新文件 |
| | C4 | 创建 `sr_sltp_calculator.py` (`calculate_sr_based_sltp`) | 新文件 |
| **D: S/R v4.0** | D1 | `_collect_candidates()` 集成新来源 + per-layer try/except + 删除旧 `pivot_data` 代码段 | 修改 |
| | D2 | `_create_zone()` 增加同源封顶 + 多源奖励 + 总权重上限 | 修改 |
| | D3 | `_evaluate_strength_v4()` 增加 PROJECTED 封顶 | 修改 |
| | D4 | `calculate()` + `calculate_with_detailed_report()` 迁移签名 (移除 pivot_data, 加 **kwargs) | 修改 |
| | D5 | AI 报告模板 `generate_ai_detailed_report()` 增加 PROJECTED/CONFIRMED 标注 | 修改 |
| **E: 数据流** | E1 | `deepseek_strategy.on_timer()` 提取 MTF bars + 更新 `_cached_atr_value` | 修改 |
| | E2 | `analyze()` + `_calculate_sr_zones()` 增加新参数 | `multi_agent_analyzer.py` |
| **F: SL/TP 闭环** | F1 | `_validate_sltp_for_entry()` 集成 `calculate_sr_based_sltp()` 三级回退 | `deepseek_strategy.py` |
| | F2 | 新增 `_reevaluate_sltp_for_existing_position()` 替代 `_dynamic_sltp_update()` | `deepseek_strategy.py` |
| | F3 | on_timer() 中替换调用点 (reevaluate 在 trailing 之前) | `deepseek_strategy.py` |
| **H: 灰度发布** (R4 新增) | H1 | 部署代码，`sltp_method: "legacy"` (默认)，验证无回退 | 运维 |
| | H2 | `development.yaml`: `sltp_method: "sr_based"`，观察 1-2 天 | 开发环境 |
| | H3 | `production.yaml`: `sltp_method: "sr_based"`，正式启用 | 生产环境 |

**R4 修正实施顺序: A → B → G → C → D → E → F → H**

> **R3→R4 顺序变更说明 (修复 G3):**
> - **G 提前到 C 之前** — Phase F (SL/TP 闭环) 依赖 `self.sltp_method`, `self.atr_buffer_multiplier`,
>   `self.dynamic_sltp_update_enabled`, `self.dynamic_update_threshold_pct` 等实例变量，
>   这些变量只有 Phase G (配置) 完成后才存在。将 G 提前避免 F 阶段的 `AttributeError`。
> - **H 新增** — 灰度发布阶段，确保安全上线。默认 `"legacy"` 意味着部署新代码不会自动启用新逻辑。
> - **B 扩展** — B3 要求所有现有候选生成器同时添加 `timeframe`，确保同源封顶不会误伤现有候选。

---

## 十一、验证计划

### 11.1 订单安全验证 (阶段 A)

1. **模拟手动平仓**: 在 Binance APP 手动平仓，观察系统是否正确清理状态
2. **模拟减仓**: 使用 `/partial_close 50`，验证 `on_position_changed` 触发后 SL/TP 数量更新
3. **模拟价格快速移动**: SL 设在入场价 -1%，但当前价已跌 2%，验证 SL 自动调整

### 11.2 数据类型验证 (阶段 B)

1. **PROJECTED 枚举**: 确认 `SRSourceType.PROJECTED` 可正确赋值
2. **timeframe 字段**: 确认候选的 `timeframe` 正确标记，同源封顶正确执行

### 11.3 S/R 质量验证 (阶段 D)

1. **ATH 场景**: 手动设 current_price > 所有 bars 最高价，确认上方有 Pivot 投射
2. **MTF 一致性**: 验证 1D swing 被标为 MAJOR，15M swing 为 MINOR
3. **VP 解耦验证**: VP 和 Swing 的 zone 重合时权重不超过 `same_data_weight_cap`
4. **PROJECTED 标注**: 确认 Pivot 来源的 zone 强度不超过 MEDIUM
5. **错误隔离**: 人为让 pivot_calculator raise Exception，确认 swing/VP 候选不受影响

### 11.4 数据流验证 (阶段 E)

1. **MTF bar 提取**: 确认 `trend_manager.recent_bars` 正确转换为 Dict 列表
2. **参数传递**: 确认 1D/4H bars 到达 `_collect_candidates()`

### 11.5 SL/TP 闭环验证 (阶段 F)

1. **开仓+动态一致性**: 开仓 SL/TP 和 15 分钟后重算的结果在 S/R 不变时应一致
2. **SL 有利方向**: LONG 仓位的 SL 只能上移
3. **TP 可双向**: 新 S/R 出现时 TP 可以调整
4. **Trailing + S/R 取有利值**: 两者都触发时取更有利的 SL
5. **Legacy 回退**: 设 `sltp_method: "legacy"`，确认使用旧版逻辑

### 11.6 离线回测工具 (后续)

```bash
# 用历史 bars 计算 S/R，然后检查后续价格是否在 zone 处反弹
python3 scripts/backtest_sr_quality.py --symbol BTCUSDT --days 30
# 输出: Precision, Recall, 各来源贡献度
```

**回测工具定义:**
- **"反弹"**: 价格进入 zone (price_low ~ price_high) 后，12 根 bar 内反向移动 >= 0.5%
- **Precision**: 真反弹次数 / zone 触碰总次数
- **目标函数**: 最大化 Precision × weight_sum (加权精度)
- **校准方法**: 网格搜索 weight 比率 (约束: 1D > 4H > 15M, 权重 > 0)

---

## 十二、R4 GAP 修复汇总

**R3 评审发现 13 个 GAP (4 个 P0 + 6 个 P1 + 3 个 P2/LOW)，R4 全部修复。**

| GAP | 优先级 | 问题 | R4 修复位置 | 状态 |
|-----|--------|------|------------|------|
| G1 | P0 | `_cached_atr_value` 幽灵变量 — 从未定义初始化和更新 | Section 6.2: 初始化 + on_timer 更新逻辑 | ✅ |
| G2 | P0 | `pivot_data` 删除未同步 `calculate()` 中间层 | Section 6.5: 三层签名同步迁移 + `**kwargs` 兼容 | ✅ |
| G3 | P0 | 实施顺序 F 依赖 G — A→B→C→D→E→F→G 错误 | Section 十: 修正为 A→B→**G**→C→D→E→F→H | ✅ |
| G4 | P0 | `"trailing_active"` 字段名错误 → 应为 `"activated"` | Section 4.4 + 全文替换 | ✅ |
| G5 | P1 | `_resubmit_sltp_if_needed()` + `_clear_position_state()` 未定义 | Section 5.1: 完整实现代码 | ✅ |
| G6 | P1 | Phase B+D 必须原子: 所有候选生成器必须同时设 `timeframe` | Section 3.3: 注意事项 + B3 步骤 | ✅ |
| G7 | P1 | `type_priority` 字典缺 PROJECTED/PSYCHOLOGICAL | Section 3.5: 更新后的 type_priority (5 种类型) | ✅ |
| G8 | P1 | `_pending_reduce_sltp` 无超时 + 无事件关联 | Section 5.2: 60s 超时 + 5% 数量容差检查 | ✅ |
| G9 | P1 | `_handle_orphan_order` 需覆盖 `on_order_canceled` | Section 5.1: 注释中明确列出三个回调 | ✅ |
| G10 | P1 | `sltp_method` 默认值应为 `"legacy"` | Section 8.1 + 8.2: 全部改为 `"legacy"` 默认 | ✅ |
| G11 | P2 | trailing + reevaluate 执行顺序 → 避免双重 cancel+recreate | Section 6.6: reevaluate 移到 trailing 之前 | ✅ |
| G12 | P2 | `_pending_sltp` 与 `_pending_reduce_sltp` 互斥断言 | Section 5.2: `assert not self._pending_sltp` | ✅ |
| G13 | LOW | SMA_200 语义标签加 `"_15M"` 后缀 | Section 3.4 + 6.6 调用链 | ✅ |

---

## 十三、学术参考

| 编号 | 论文/来源 | 贡献 | 适用性说明 |
|------|----------|------|-----------|
| [1] | Spitsin et al. (2025) Contemporary Mathematics 6(6) | 成交量加权极值 + L1 聚类 | 美股样本; 本方案采用成交量加权, 有意暂缓 L1 聚类 (见 1.3 注) |
| [2] | Chung & Bellotti (2021) arXiv:2101.07410 | 触碰记忆效应 + 时间衰减 | 系统已实现 age_factor + touch_count |
| [3] | Osler (2003) Journal of Finance | 整数位订单聚集效应 | 直接适用于 BTC ($5k/$10k) |
| [4] | Chan et al. (2022) MDPI Mathematics 10(20):3888 | S/R 特征 → ML 盈利 +65% | Swing 检测方法参考 |
| [5] | SHS Conferences (2021) | VPOC 90% 反应率 (WIG20) | WIG20 指数，BTC 需验证 |
| [6] | Tsinaslanidis et al. (2022) Expert Systems | Fibonacci Retracement 证伪 | 适用: 不实现 Fibonacci |
| [7] | CME Market Profile User Guide | VP 标准算法 | 行业标准 |
| [8] | Bulkowski, Thomas (2021) Encyclopedia of Chart Patterns | Measured Move 85% hit rate | 仅参考，暂不实施 |
