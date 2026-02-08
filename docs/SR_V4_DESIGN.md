# S/R Zone Calculator v4.0 — 设计方案

> 基于 Spitsin (2025)、Chung & Bellotti (2021)、Osler (2003) 学术研究重新设计

## 一、当前系统诊断

### 1.1 现状数据流

```
deepseek_strategy.py (L1812)
  sr_bars_data = self.indicator_manager.get_kline_data(count=120)
                 ^^^^^^^^^^^^^^^^^^^^^^^^
                 这是 15M 的 indicator_manager
                 120 × 15min = 30 小时

  → multi_agent_analyzer._calculate_sr_zones() (L2373)
    → sr_calculator.calculate_with_detailed_report()
      → _collect_candidates()        ← 收集候选
        ├ _detect_swing_points()     ← 15M bars, max_age=100 → 25 小时
        ├ BB_Upper/Lower             ← 15M 布林带
        ├ SMA_50/SMA_200             ← 15M 的 SMA (= 12.5h / 50h)
        ├ Order Wall                 ← 实时盘口
        ├ Pivot Points               ← 可选，目前未传入
        └ Round Number               ← v3.1 新增
      → _cluster_to_zones()          ← ATR 自适应聚类
      → touch_count scoring          ← 对 15M bars 做触碰统计
```

### 1.2 核心问题

| # | 问题 | 影响 |
|---|------|------|
| 1 | **时间尺度错误** | 所有 swing points 都在 15M×120=30h 内找，日线级别的重要高低点看不到 |
| 2 | **MTF 数据浪费** | `decision_manager`(4H) 和 `trend_manager`(1D) 已有 bar 数据，但没传给 S/R |
| 3 | **SMA 含义错乱** | `SMA_200` 标记为 `MAJOR`，但实际是 15M×200=50h，不是日线 SMA200 |
| 4 | **Swing 无成交量确认** | Spitsin (2025): 无成交量确认的极值是噪声 → P=0.70; 有确认 → P=0.81-0.88 |
| 5 | **Round Number 粒度** | $1000 步长对 BTC 太细 ($71k≈$72k)，Osler (2003): 尾数 "00" 有序效应 → $5k/$10k 级别 |
| 6 | **无 Volume Profile** | VPOC 有 90% 反应率 (SHS 2021)，是机构标准工具，当前缺失 |
| 7 | **无日线 Pivot** | 日线/周线 Pivot R1/R2/R3 在 ATH 场景可投射上方阻力，当前未使用 |

### 1.3 已有可复用的好设计

- `SRCandidate` → `SRZone` 的聚类管线：ATR 自适应阈值、zone 扩展、来源类型分层
- Touch Count 评分：逻辑正确（进出判定、衰减机制），只是数据时间窗口太短
- AI 报告输出：结构化数据 + 交易含义 → 给 AI 判断（不做本地硬规则）
- `SRLevel`（MAJOR/INTERMEDIATE/MINOR）分层体系：正确设计，只是实际赋值有误

---

## 二、设计目标

### 量化标准（参照 Spitsin 2025 论文基线）

| 指标 | 当前估计 | 目标 | Spitsin 论文 |
|------|---------|------|-------------|
| Precision (S/R 被触及时确实反弹) | 未测量 | ≥ 0.75 | 0.81-0.88 |
| Recall (真实反弹被 S/R 覆盖) | 未测量 | ≥ 0.70 | 0.78-0.82 |
| ATH 场景上方有阻力 | 0/3 次 (Round# 除外) | ≥ 2/3 | N/A |
| 误报率 (虚假 S/R) | 高 (15M swing 噪声多) | 降低 30%+ | 假突破 -12~15% |

### 设计原则

1. **用对时间尺度** — 日线 swing = MAJOR, 4H swing = INTERMEDIATE, 15M = MINOR
2. **成交量是必要条件** — 没有成交量确认的极值点不入选（Spitsin 2025）
3. **不堆砌指标** — 每增加一个数据源必须有学术证据或机构惯例支撑
4. **输出给 AI 判断** — 本地只做预处理和结构化，不做交易决策

---

## 三、架构设计

### 3.1 新的数据流

```
deepseek_strategy.py on_timer()
  │
  ├── bars_15m = indicator_manager.get_kline_data(count=120)      # 15M, 30h
  ├── bars_4h  = mtf_manager.decision_manager.get_kline_data(50)  # 4H,  8.3天
  ├── bars_1d  = mtf_manager.trend_manager.get_kline_data(120)    # 1D,  120天
  │
  └── multi_agent.analyze(...,
        bars_data={                    # v4.0: 多时间框架 bars
          '15m': bars_15m,
          '4h':  bars_4h,
          '1d':  bars_1d,
        }
      )
        │
        └── _calculate_sr_zones(bars_data=multi_tf_bars)
              │
              └── sr_calculator.calculate(
                    bars_data_mtf={...},    # v4.0: 新参数
                    bb_data=...,
                    sma_data=...,
                    ...
                  )
```

### 3.2 候选来源重新设计

v3.1 当前:

```
_collect_candidates()
  ├ Swing Points (15M only, 无成交量确认)        权重 1.2
  ├ BB_Upper/Lower (15M)                         权重 1.0
  ├ SMA_50/200 (15M 的,标记有误)                  权重 0.8/1.5
  ├ Order Wall (实时)                             权重 0.8
  ├ Pivot Points (未使用)                          权重 0.7
  └ Round Number ($1000 步长)                     权重 0.6
```

v4.0 设计:

```
_collect_candidates()
  │
  │ ===== 结构性 (STRUCTURAL) — 学术验证最有效 =====
  │
  ├ 日线 Swing Points (1D bars, 成交量加权)        权重 2.0  level=MAJOR
  │   └ 要求: 该 swing bar 的 volume > MA(20) 的 volume
  │
  ├ 4H Swing Points (4H bars, 成交量加权)          权重 1.5  level=INTERMEDIATE
  │   └ 同上成交量要求
  │
  ├ 15M Swing Points (15M bars, 成交量加权)        权重 0.8  level=MINOR
  │   └ 降权: 15M swing 噪声多, 仅作微调参考
  │
  ├ 日线 Pivot Points (PP/R1/R2/R3/S1/S2/S3)      权重 1.2  level=MAJOR
  │   └ 从最近一根日线 bar 的 H/L/C 计算
  │   └ ATH 时 R1/R2/R3 可投射上方阻力
  │
  ├ Volume Profile VPOC/VAH/VAL (4H bars)          权重 1.5  level=INTERMEDIATE
  │   └ 从 4H bars 计算成交量-价格分布
  │   └ VPOC = 成交量最大的价格 = 价格磁铁
  │
  │ ===== 技术性 (TECHNICAL) =====
  │
  ├ BB_Upper/Lower (15M, 维持现有)                 权重 0.8  level=MINOR
  │
  ├ 4H BB_Upper/Lower (从 decision_manager)        权重 1.0  level=INTERMEDIATE
  │
  │ ===== 订单流 (ORDER_FLOW) =====
  │
  ├ Order Wall (实时盘口, 维持现有)                 权重 0.8  level=MINOR
  │
  │ ===== 心理层面 =====
  │
  └ Round Number (BTC: $5000 步长)                  权重 0.5  level=MINOR
      └ 改为 $5000 步长: $65k, $70k, $75k, $80k
      └ $10000 级别 ($70k, $80k) 额外 +0.3 权重加成
```

### 3.3 各模块修改清单

#### 文件 1: `utils/sr_zone_calculator.py`

**修改 `_detect_swing_points()`**:
- 新增参数 `volume_data: List[float]` 和 `volume_ma: float`
- Swing 候选额外检查: 该 bar 的 volume > volume_ma × volume_threshold (默认 1.0)
- 不满足成交量要求的 swing → 权重减半（不丢弃，但标记为 unconfirmed）

**新增 `_detect_swing_points_mtf()`**:
- 接收 `bars_data_mtf: Dict[str, List[Dict]]`
- 分别对 1D / 4H / 15M 调用 `_detect_swing_points()`
- 根据 timeframe 赋予不同 level 和权重

**新增 `_calculate_daily_pivots()`**:
- 输入: 最近一根日线 bar 的 `high, low, close`
- 输出: `PP, R1, R2, R3, S1, S2, S3`
- 公式 (Floor Trader Pivots):
  ```
  PP = (H + L + C) / 3
  R1 = 2 * PP - L
  S1 = 2 * PP - H
  R2 = PP + (H - L)
  S2 = PP - (H - L)
  R3 = H + 2 * (PP - L)
  S3 = L - 2 * (H - PP)
  ```
- 生成 SRCandidate，side 按价格位置判断

**新增 `_calculate_volume_profile()`**:
- 输入: 4H bars (OHLCV)
- 步骤:
  1. 确定价格范围 `[min_low, max_high]`
  2. 分成 N 个 bin (N = 价格范围 / ATR，通常 30-80 个)
  3. 每根 bar 的 volume 分配到 close 所在 bin
  4. VPOC = volume 最大的 bin 中心价
  5. Value Area = 从 VPOC 向两侧扩展直到包含 70% 总 volume
  6. VAH = Value Area 上界, VAL = Value Area 下界
- 输出: 3 个 SRCandidate (VPOC, VAH, VAL)

**修改 `_generate_round_number_levels()`**:
- BTC (price >= 10000): 主级 $5000, 次级 $10000 加权
- ETH (1000-10000): 主级 $500
- 其他: 维持现有逻辑

**修改 `calculate()` 和 `calculate_with_detailed_report()`**:
- 新增参数 `bars_data_mtf: Optional[Dict[str, List[Dict]]]`
- 新增参数 `daily_bar: Optional[Dict]` (最近日线 bar 用于 Pivot)
- 修改 `_collect_candidates()` 签名匹配

**修改权重体系**:

```python
WEIGHTS = {
    # STRUCTURAL — 学术验证有效
    'Swing_1D':       2.0,   # 日线 swing: 最重要的结构性 S/R
    'Swing_4H':       1.5,   # 4H swing: 中期结构
    'Swing_15M':      0.8,   # 15M swing: 日内微调 (降权)
    'VPOC':           1.5,   # Volume Profile POC: 90% 反应率
    'VAH':            1.2,   # Value Area High
    'VAL':            1.2,   # Value Area Low
    'Pivot_PP':       1.0,   # Pivot Point
    'Pivot_R1':       1.2,   # 日线 Pivot R1/S1
    'Pivot_S1':       1.2,
    'Pivot_R2':       1.0,   # Pivot R2/S2
    'Pivot_S2':       1.0,
    'Pivot_R3':       0.8,   # Pivot R3/S3 (较远，权重低)
    'Pivot_S3':       0.8,

    # TECHNICAL
    'BB_Upper_4H':    1.0,   # 4H 布林带
    'BB_Lower_4H':    1.0,
    'BB_Upper_15M':   0.6,   # 15M 布林带 (降权)
    'BB_Lower_15M':   0.6,

    # ORDER_FLOW
    'Order_Wall':     0.8,   # 维持现有

    # PSYCHOLOGICAL
    'Round_Number':   0.5,   # 降权，$5000 粒度
}
```

**修改强度评估**:

```python
STRENGTH_THRESHOLDS = {
    'HIGH':   3.5,   # 提高门槛 (v3.1 是 3.0)
    'MEDIUM': 2.0,   # 提高门槛 (v3.1 是 1.5)
    'LOW':    0.0,
}
```
提高门槛是因为高时间框架 swing 权重更高，需要更高的 confluence 才算 HIGH。

#### 文件 2: `agents/multi_agent_analyzer.py`

**修改 `_calculate_sr_zones()` (L2373)**:
- 接收新参数 `bars_data_mtf` 和 `daily_bar`
- 从 `bars_data_mtf['4h']` 提取 4H 的 BB/SMA 数据
- 将 `bars_data_mtf` 和 `daily_bar` 传给 `sr_calculator`

**修改 `analyze()` (L409)**:
- 接收新参数 `bars_data_mtf: Dict[str, List[Dict]]`
- 替代原来的 `bars_data: List[Dict]`

#### 文件 3: `strategy/deepseek_strategy.py`

**修改 `on_timer()` (L1811 附近)**:
- 收集多时间框架 bars:
```python
# v4.0: Multi-timeframe bars for S/R
sr_bars_data_mtf = {
    '15m': self.indicator_manager.get_kline_data(count=120),
}
if self.mtf_enabled and self.mtf_manager:
    dm = self.mtf_manager.decision_manager
    tm = self.mtf_manager.trend_manager
    if dm and hasattr(dm, 'recent_bars') and dm.recent_bars:
        sr_bars_data_mtf['4h'] = dm.get_kline_data(count=50)
    if tm and hasattr(tm, 'recent_bars') and tm.recent_bars:
        sr_bars_data_mtf['1d'] = tm.get_kline_data(count=120)
```
- 传入 `analyze()`:
```python
bars_data=sr_bars_data_mtf,  # v4.0: 改为 dict
```

#### 文件 4: `configs/base.yaml`

```yaml
sr_zones:
  enabled: true

  swing_detection:
    enabled: true
    left_bars: 5
    right_bars: 5
    max_swing_age: 100
    # v4.0: 成交量确认
    volume_confirmation: true
    volume_threshold: 1.0      # swing bar volume > MA(20) × threshold
    unconfirmed_penalty: 0.5   # 未确认 swing 权重乘以此系数

  # v4.0: 多时间框架权重
  weights:
    swing_1d: 2.0
    swing_4h: 1.5
    swing_15m: 0.8
    vpoc: 1.5
    vah: 1.2
    val: 1.2
    pivot: 1.2
    bb_4h: 1.0
    bb_15m: 0.6
    order_wall: 0.8
    round_number: 0.5

  # v4.0: Volume Profile
  volume_profile:
    enabled: true
    value_area_pct: 70          # Value Area 包含的成交量百分比
    bin_count_auto: true        # 自动根据 ATR 确定 bin 数量
    min_bins: 30
    max_bins: 80

  # v4.0: 日线 Pivot Points
  daily_pivots:
    enabled: true
    method: "floor_trader"      # floor_trader / fibonacci / camarilla

  # v4.0: Round Number
  round_number:
    btc_step: 5000              # BTC: $5000 步长 ($65k, $70k, $75k...)
    major_step_multiplier: 2    # $10k 级别 ($70k, $80k) 额外加权 ×2
    count: 3                    # 上下各 3 个
```

---

## 四、新增算法详细设计

### 4.1 成交量加权 Swing 检测 (Spitsin 2025)

```python
def _detect_swing_points(self, bars_data, current_price,
                          timeframe='15m'):
    """
    v4.0: 成交量加权 Williams Fractal

    变更:
    1. 计算 bars 的 volume MA(20)
    2. 对每个 swing 候选检查: bar.volume > volume_ma × threshold
    3. 通过 → 使用完整权重
    4. 未通过 → 权重 × unconfirmed_penalty (0.5)
    5. 根据 timeframe 赋予 level 和基础权重
    """
    # 1. 计算 volume MA
    volumes = [float(b.get('volume', 0)) for b in bars_data]
    vol_ma = sum(volumes[-20:]) / min(20, len(volumes)) if volumes else 0

    # 2. 根据 timeframe 确定基础权重和 level
    tf_config = {
        '1d':  {'weight': self.WEIGHTS['Swing_1D'],  'level': SRLevel.MAJOR},
        '4h':  {'weight': self.WEIGHTS['Swing_4H'],  'level': SRLevel.INTERMEDIATE},
        '15m': {'weight': self.WEIGHTS['Swing_15M'], 'level': SRLevel.MINOR},
    }
    base_weight = tf_config[timeframe]['weight']
    level = tf_config[timeframe]['level']

    # 3. Williams Fractal 检测 (现有逻辑)
    for i in range(left, n - right):
        # ... 现有 swing high/low 检测 ...

        # 4. 成交量确认
        bar_volume = float(bars[i].get('volume', 0))
        vol_confirmed = (bar_volume > vol_ma * self.volume_threshold) if vol_ma > 0 else True

        # 5. 权重计算
        weight = base_weight * age_factor
        if not vol_confirmed:
            weight *= self.unconfirmed_penalty  # 0.5

        # 6. S/R Flip (维持 v3.1 逻辑)
        side = ...

        candidates.append(SRCandidate(
            price=bar_high,
            source=f"Swing_High_{timeframe.upper()}",
            weight=weight,
            side=side,
            extra={
                'bar_index': i,
                'bars_ago': bars_ago,
                'age_factor': age_factor,
                'volume_confirmed': vol_confirmed,
                'timeframe': timeframe,
            },
            level=level,
            source_type=SRSourceType.STRUCTURAL,
        ))
```

### 4.2 Volume Profile (VPOC / VAH / VAL)

```python
def _calculate_volume_profile(self, bars_data, current_price):
    """
    计算 Volume Profile: VPOC, VAH, VAL

    参考: CME Market Profile, SHS Conferences 2021 (90% 反应率)

    算法:
    1. 确定价格范围 [min_low, max_high]
    2. 分成 N 个 bin
    3. 分配成交量到各 bin
    4. 找最大 volume bin = VPOC
    5. 从 VPOC 向两侧扩展到包含 70% volume = VAH/VAL
    """
    if not bars_data or len(bars_data) < 10:
        return []

    # 收集数据
    closes = []
    volumes = []
    min_price = float('inf')
    max_price = 0
    for bar in bars_data:
        c = float(bar.get('close', 0))
        v = float(bar.get('volume', 0))
        h = float(bar.get('high', 0))
        l = float(bar.get('low', 0))
        if c <= 0:
            continue
        closes.append(c)
        volumes.append(v)
        min_price = min(min_price, l)
        max_price = max(max_price, h)

    if not closes or max_price <= min_price:
        return []

    # 确定 bin 数量 (基于价格范围和 ATR)
    price_range = max_price - min_price
    atr = self._calculate_atr_from_bars(bars_data)
    if atr > 0:
        num_bins = max(self.vp_min_bins,
                       min(self.vp_max_bins, int(price_range / atr)))
    else:
        num_bins = 50

    bin_size = price_range / num_bins

    # 分配成交量到各 bin
    vol_bins = [0.0] * num_bins
    for close_price, volume in zip(closes, volumes):
        bin_idx = int((close_price - min_price) / bin_size)
        bin_idx = min(bin_idx, num_bins - 1)
        vol_bins[bin_idx] += volume

    total_volume = sum(vol_bins)
    if total_volume <= 0:
        return []

    # VPOC: 成交量最大的 bin
    vpoc_idx = vol_bins.index(max(vol_bins))
    vpoc_price = min_price + (vpoc_idx + 0.5) * bin_size

    # Value Area: 从 VPOC 向两侧扩展到 70%
    va_volume = vol_bins[vpoc_idx]
    low_idx = vpoc_idx
    high_idx = vpoc_idx
    target_volume = total_volume * (self.value_area_pct / 100)

    while va_volume < target_volume and (low_idx > 0 or high_idx < num_bins - 1):
        # 比较两侧下一个 bin 的 volume，取大的那侧扩展
        expand_low = vol_bins[low_idx - 1] if low_idx > 0 else 0
        expand_high = vol_bins[high_idx + 1] if high_idx < num_bins - 1 else 0

        if expand_low >= expand_high and low_idx > 0:
            low_idx -= 1
            va_volume += vol_bins[low_idx]
        elif high_idx < num_bins - 1:
            high_idx += 1
            va_volume += vol_bins[high_idx]
        else:
            break

    vah_price = min_price + (high_idx + 1) * bin_size
    val_price = min_price + low_idx * bin_size

    # 生成候选
    candidates = []
    vpoc_side = 'support' if vpoc_price < current_price else 'resistance'
    candidates.append(SRCandidate(
        price=vpoc_price,
        source='VPOC',
        weight=self.WEIGHTS['VPOC'],
        side=vpoc_side,
        level=SRLevel.INTERMEDIATE,
        source_type=SRSourceType.STRUCTURAL,
    ))

    if vah_price > current_price:
        candidates.append(SRCandidate(
            price=vah_price,
            source='VAH',
            weight=self.WEIGHTS['VAH'],
            side='resistance',
            level=SRLevel.INTERMEDIATE,
            source_type=SRSourceType.STRUCTURAL,
        ))
    else:
        candidates.append(SRCandidate(
            price=vah_price,
            source='VAH',
            weight=self.WEIGHTS['VAH'],
            side='support',
            level=SRLevel.INTERMEDIATE,
            source_type=SRSourceType.STRUCTURAL,
        ))

    if val_price < current_price:
        candidates.append(SRCandidate(
            price=val_price,
            source='VAL',
            weight=self.WEIGHTS['VAL'],
            side='support',
            level=SRLevel.INTERMEDIATE,
            source_type=SRSourceType.STRUCTURAL,
        ))
    else:
        candidates.append(SRCandidate(
            price=val_price,
            source='VAL',
            weight=self.WEIGHTS['VAL'],
            side='resistance',
            level=SRLevel.INTERMEDIATE,
            source_type=SRSourceType.STRUCTURAL,
        ))

    return candidates
```

### 4.3 日线 Pivot Points

```python
def _calculate_daily_pivots(self, daily_bar, current_price):
    """
    Floor Trader Pivot Points (从最近日线 bar 计算)

    公式:
      PP = (H + L + C) / 3
      R1 = 2*PP - L      S1 = 2*PP - H
      R2 = PP + (H-L)    S2 = PP - (H-L)
      R3 = H + 2*(PP-L)  S3 = L - 2*(H-PP)

    ATH 优势: R1/R2/R3 是纯数学投射，不依赖历史价格，
    即使在全新高度也能产生上方阻力位。
    """
    if not daily_bar:
        return []

    H = float(daily_bar.get('high', 0))
    L = float(daily_bar.get('low', 0))
    C = float(daily_bar.get('close', 0))

    if H <= 0 or L <= 0 or C <= 0:
        return []

    PP = (H + L + C) / 3
    R1 = 2 * PP - L
    R2 = PP + (H - L)
    R3 = H + 2 * (PP - L)
    S1 = 2 * PP - H
    S2 = PP - (H - L)
    S3 = L - 2 * (H - PP)

    pivots = {
        'PP': PP, 'R1': R1, 'R2': R2, 'R3': R3,
        'S1': S1, 'S2': S2, 'S3': S3,
    }

    candidates = []
    for name, price in pivots.items():
        if price <= 0:
            continue
        side = 'support' if price < current_price else 'resistance'
        weight_key = f'Pivot_{name}' if f'Pivot_{name}' in self.WEIGHTS else 'Pivot_PP'
        candidates.append(SRCandidate(
            price=price,
            source=f"DailyPivot_{name}",
            weight=self.WEIGHTS.get(weight_key, 1.0),
            side=side,
            level=SRLevel.MAJOR,
            source_type=SRSourceType.STRUCTURAL,
        ))

    return candidates
```

---

## 五、移除和降级

| 项目 | 操作 | 原因 |
|------|------|------|
| `SMA_200` (15M) 标记为 `MAJOR` | 改为 `MINOR` | 15M×200 = 50h，不是日线 SMA200 |
| `SMA_50` (15M) 标记为 `INTERMEDIATE` | 改为 `MINOR` | 同上 |
| `Round_Number` $1000 步长 | 改为 $5000 (BTC) | Osler 2003: "00" 尾数效应，$1000 级别太细 |
| Fibonacci Extensions | **不实现** | Tsinaslanidis 2022: 学术证伪，统计不显著 |
| v3.1 S/R Flip 逻辑 | **保留** | 逻辑正确，现在配合日线 swing 更有意义 |

---

## 六、对 Telegram Heartbeat 的影响

修改后 heartbeat 显示示例（BTC 在 $97,000 附近的 ATH 场景）:

```
📍 支撑 / 阻力
  🔴 R $99,200 (+2.3%) [日|HIGH T2]        ← 日线 Pivot R2
  ⚪ R $98,100 (+1.1%) [日|MEDIUM]          ← 日线 Pivot R1
  ── 当前 $97,000 ──
  🟡 S $96,300 (-0.7%) [4H|MEDIUM T3]      ← 4H swing + VPOC 聚合
  🟢 S $95,000 (-2.1%) [日|HIGH T2]        ← 日线 swing high (S/R flip) + $95k 整数
  ⚪ S $93,800 (-3.3%) [4H|MEDIUM]          ← VAL + 4H swing
```

vs 当前 (ATH 时):
```
📍 支撑 / 阻力
  ── 当前 $97,000 ──
  ⚪ S $96,200 (-0.8%) [4H|LOW T10]         ← 只有下方 15M swing
  ⚪ S $95,800 (-1.2%) [4H|LOW T7]
  🟢 S $95,100 (-2.0%) [日|HIGH T3]
```

**关键改善**: ATH 时上方有日线 Pivot R1/R2 作为投射阻力。

---

## 七、向后兼容

### 降级策略

| 场景 | 行为 |
|------|------|
| MTF 未启用 (`multi_timeframe.enabled: false`) | 回退到只用 15M bars (v3.1 行为) |
| `trend_manager` 未初始化 (bar 数不足) | 跳过日线 swing 和 Pivot，只用 4H + 15M |
| `decision_manager` 未初始化 | 跳过 4H swing 和 Volume Profile，只用 15M |
| `bars_data` 传入是 `List` 而非 `Dict` | 兼容 v3.1: 当作 15M bars 处理 |

### 参数兼容

`calculate()` 方法保持旧参数可用:
```python
def calculate(self,
    current_price,
    bb_data=None, sma_data=None,
    orderbook_anomalies=None, pivot_data=None,
    bars_data=None,         # v3.x 兼容: List[Dict] → 当作 15M
    atr_value=None,
    # v4.0 新增:
    bars_data_mtf=None,     # Dict[str, List[Dict]] → 多 TF
    daily_bar=None,         # Dict → 最近日线 bar
):
```

---

## 八、实施步骤

| 步骤 | 内容 | 影响范围 |
|------|------|---------|
| 1 | `sr_zone_calculator.py`: 新增 `_calculate_daily_pivots()` | 纯新增 |
| 2 | `sr_zone_calculator.py`: 新增 `_calculate_volume_profile()` | 纯新增 |
| 3 | `sr_zone_calculator.py`: 修改 `_detect_swing_points()` 添加成交量加权 + timeframe 参数 | 修改 |
| 4 | `sr_zone_calculator.py`: 新增 `_detect_swing_points_mtf()` 分发到各 TF | 纯新增 |
| 5 | `sr_zone_calculator.py`: 修改 `_collect_candidates()` 集成新来源 | 修改 |
| 6 | `sr_zone_calculator.py`: 修改 `calculate()` 接受新参数 | 修改 (向后兼容) |
| 7 | `sr_zone_calculator.py`: 修改 `_generate_round_number_levels()` 改粒度 | 修改 |
| 8 | `sr_zone_calculator.py`: 更新权重表和强度阈值 | 修改 |
| 9 | `sr_zone_calculator.py`: 更新 `generate_ai_detailed_report()` | 修改 |
| 10 | `agents/multi_agent_analyzer.py`: 修改 `_calculate_sr_zones()` 传新参数 | 修改 |
| 11 | `agents/multi_agent_analyzer.py`: 修改 `analyze()` 接口 | 修改 (向后兼容) |
| 12 | `strategy/deepseek_strategy.py`: 收集 MTF bars 传入 | 修改 |
| 13 | `configs/base.yaml`: 添加 v4.0 配置 | 修改 |
| 14 | 更新 AI 报告模板 | 修改 |

---

## 九、验证计划

1. **单元测试**: 用模拟 bars 验证各算法独立正确性
   - swing 检测 + 成交量过滤
   - Volume Profile VPOC/VAH/VAL 计算
   - Pivot Points 数值正确性
   - Round Number 新粒度

2. **集成测试**: 用真实 Binance 数据跑完整管线
   ```bash
   python3 scripts/diagnose_realtime.py  # 应显示 MTF 数据
   ```

3. **ATH 场景验证**: 手动设 current_price > 所有 bars 最高价，确认上方有阻力

4. **向后兼容测试**: MTF 禁用时回退到 v3.1 行为

---

## 十、学术参考

| 编号 | 论文/来源 | 贡献 |
|------|----------|------|
| [1] | Spitsin et al. (2025) "Modeling S/R Zones with Stochastic and Volume-Weighted Methods" | 成交量加权 + Markov 链; P=0.81-0.88 |
| [2] | Chung & Bellotti (2021) arXiv:2101.07410 | 触碰记忆效应 + 时间衰减的统计验证 |
| [3] | Osler (2003) Journal of Finance | 10% 订单在整数位; take-profit 聚集 = S/R |
| [4] | Chan et al. (2022) MDPI Mathematics 10(20):3888 | S/R 特征 → ML 盈利 +65% |
| [5] | SHS Conferences (2021) | VPOC 90% 反应率 |
| [6] | Tsinaslanidis et al. (2022) Expert Systems | Fibonacci 学术证伪: 不优于随机价位 |
| [7] | DeepSupp (2025) arXiv:2507.01971 | DBSCAN + Attention SOTA (未来参考) |
