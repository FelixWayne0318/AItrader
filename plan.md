# TP 不对称修复方案 v2 — 经量化专家评审后修订

## 量化专家评审结论

### Dimension 1: Statistical Rigor — 3/5

**问题 1: `min_rr_ratio` 降至 1.2/1.3 缺乏期望值数学论证**

v1 方案凭直觉说"TP buffer 提高胜率所以 R/R 门槛可以降"——这是 wishful thinking。
没有胜率数据就降 R/R 门槛，等于同时削弱两道防线。

**修正**: 不降 `min_rr_ratio`。保持 1.5。TP buffer 缩小了 reward，那些原来 R/R
刚过 1.5 的交易会被拒绝——这恰好是正确行为（边缘交易本来就不该做）。
真正 R/R 好的交易（2.0+）几乎不受影响。

**问题 2: ATR × 0.3 的 TP buffer 缺乏标定依据**

v1 方案说"保守值"但没有解释为什么是 0.3 而不是 0.2 或 0.5。

**修正**: TP buffer 应与 SL buffer 等比设计。SL buffer = ATR × 0.5 是为了
吸收假突破（价格穿越 zone 后回来的平均幅度）。TP buffer 的目的不同——
是为了在 zone 前方止盈（因为价格在 zone 附近减速）。
业界共识 (TradingWithRayner, LuxAlgo) 是 TP 偏移量 < SL 偏移量。
设定 TP buffer = SL buffer × 0.5 = ATR × 0.25，并作为可配置参数，
用实盘数据标定后调整。

### Dimension 2: Market Microstructure — 4/5

**问题: 未区分趋势市 vs 震荡市**

趋势市中，价格穿越阻力后加速（Osler 的 cascade 效应），TP buffer 会导致过早离场。
震荡市中，价格在 zone 前反转，TP buffer 提高触达率。

**修正**: 不在 calculator 层处理这个问题——市场状态判断属于 AI Judge 的职责。
但在日志中记录 buffer 影响量（`zone_price` vs `buffered_tp`），
方便事后分析 buffer 在不同市场状态下的表现。

### Dimension 3: Implementation Correctness — 2/5 (v1 有严重问题)

**问题 1: `_collect_tp_candidates` 返回类型变化导致 8+ 处调用方报错**

v1 把返回类型从 `List[float]` 改为 `List[Tuple[float, int]]`。
`calculate_sr_based_sltp()` 内部遍历时用 `candidate_tp` (期望 float)，
改后变成 `(price, quality)` 元组——所有 `abs(candidate_tp - current_price)` 直接崩溃。
此外诊断脚本中至少 6 处直接调用此函数。

**修正**: 不改返回类型。内部排序用质量评分，返回时仍提取为 `List[float]`。
这样所有调用方零改动。

**问题 2: 降级逻辑 (`min_quality=0`) 等于静默回退到旧行为**

当所有 zone 被质量过滤后降级到 `min_quality=0`，等于完全回退到
修改前的行为——这不是"降级"，是"放弃修复"。

**修正**: 移除降级。`min_quality` 不作为过滤门槛，而是作为排序加分项。
所有 zone 都参与排序，质量高的排前面。这样：
- 有强 zone → 优先选强 zone（改进）
- 只有弱 zone → 仍能选到最近的弱 zone（不比现在差）
- 没有 zone → 返回空（与现在一致）

**问题 3: 距离分段 `int(distance / band)` 的边界效应**

如果两个 zone 距离分别是 0.99×ATR 和 1.01×ATR，分段后变成 0 和 1，
导致 0.99 的弱 zone 被选中而 1.01 的强 zone 被跳过。

**修正**: 不用硬分段。改用**加权排序**: `sort_key = distance - quality_bonus × ATR × 0.1`。
质量高的 zone 获得等效"距离折扣"，但折扣量有限不会让远处 zone 反超近处。

### Dimension 4: Risk Management Integrity — 3/5

**问题: Level 1 (AI SL/TP) 也使用 `min_rr_ratio`，降低门槛会同时放松 AI 验证**

`validate_multiagent_sltp()` 内部调用 `get_min_rr_ratio()` 读取同一个配置值。
降 `min_rr_ratio` 不仅影响 Level 2 (S/R)，还影响 Level 1 (AI)——
等于允许 AI 返回更差的 SL/TP。这是未预期的副作用。

**修正**: 不降 `min_rr_ratio`。保持 1.5 对两条路径一致适用。

### Dimension 5: Consistency & Symmetry — 3/5

**问题: TP 质量评分权重直接复制 SL 的权重，但 TP 和 SL 的目标不同**

SL 选 zone: 目标是"这个 zone 能不能挡住价格"→ 强度和可靠性最重要。
TP 选 zone: 目标是"价格能不能到达这个 zone"→ 可达性(距离)更重要，
质量是次要考量(只是为了避免选完全不可靠的 zone)。

如果用相同权重 `strength×10 + quality×5 + touch×3 + swing×2`，
会过度偏向远处强 zone 作为 TP，降低 TP 触达率——适得其反。

**修正**: TP 的质量分仅作为**距离折扣**，不作为主排序维度。具体做法：

```
sort_key = distance - quality_bonus * atr * 0.1
```

其中 `quality_bonus` 上限为 3（约 0.3×ATR 的折扣），不会让质量碾压距离。

### Dimension 6: Configurability & Observability — 4/5

**问题: 缺少 A/B 回退能力**

**修正**: `tp_buffer_multiplier = 0` 时等价于修改前行为（零 buffer），
保留完全回退能力。在日志中记录 `zone_price`, `buffered_tp`, `buffer_amount`
便于事后分析。

### Dimension 7: Academic Foundation — 4/5

**问题: Measured Move 不加 buffer 的论证有 special pleading 嫌疑**

Bulkowski 的 85% 命中率是在传统市场（股票）研究的。加密市场的波动率
和 order flow 动态不同，直接引用命中率不严谨。

**修正**: Measured Move 也加 buffer，但使用更小的系数 (ATR × 0.15)。
理由：MM 是投影目标不是历史 zone，不确定性更高，应该更保守。

---

## 总评

| 维度 | v1 得分 | 修正后 |
|------|---------|--------|
| 统计严谨性 | 3/5 | 4/5 (不降 R/R) |
| 微观结构 | 4/5 | 4/5 |
| 实现正确性 | 2/5 | 4/5 (不改返回类型) |
| 风险管理 | 3/5 | 4/5 (不连带影响 AI 验证) |
| 一致性 | 3/5 | 4/5 (TP 权重独立设计) |
| 可配置性 | 4/5 | 5/5 (0=关闭) |
| 学术基础 | 4/5 | 4/5 |
| **总分** | **23/35** | **29/35** |

---

## 修订后方案

### 修改文件清单 (简化)

| 文件 | 改动 |
|------|------|
| `utils/sr_sltp_calculator.py` | `_collect_tp_candidates` 排序逻辑 + `calculate_sr_based_sltp` TP buffer |
| `configs/base.yaml` | 新增 `tp_buffer_multiplier: 0.25` |
| `strategy/deepseek_strategy.py` | dataclass 字段 + 传参 |
| `main_live.py` | 读取配置 |

**不改的东西**:
- `min_rr_ratio` 保持 1.5（不降）
- `_collect_tp_candidates` 返回类型保持 `List[float]`（不改）
- 无降级机制（质量分作为排序加分，不作为过滤门槛）
- 所有诊断脚本不受影响（函数签名通过 `**kwargs` 兼容）

---

### 改动 1: `_collect_tp_candidates()` — 质量感知排序

**原则**: 距离仍是主排序维度，质量提供"距离折扣"。

```python
def _collect_tp_candidates(
    zones: List,
    current_price: float,
    is_long: bool,
    atr_value: float = 0.0,
) -> List[float]:
    """
    v5.1: Quality-aware TP candidate collection.

    Sorting: distance is primary, quality provides a "distance discount".
    A HIGH STRUCTURAL zone 0.3 ATR further away is treated as equivalent
    to a LOW PSYCHOLOGICAL zone at the current distance.

    This avoids the v4.3 problem of choosing weak zones just because
    they're nearest, while not over-rotating to pick distant strong zones.

    Returns List[float] (unchanged signature for compatibility).
    """
    candidates = []
    for zone in zones:
        price = _extract_price(zone)
        if not price or price <= 0:
            continue

        if is_long and price <= current_price:
            continue
        if not is_long and price >= current_price:
            continue

        # Quality score (0-7 range, intentionally lower than SL scoring)
        source_quality = _SOURCE_QUALITY.get(_get_source_type(zone), 0)
        strength_bonus = _STRENGTH_SCORE.get(_get_strength(zone), 1) - 1  # 0-2 (normalize: LOW=0)
        touch_count = _get_touch_count(zone)
        touch_bonus = 1 if touch_count >= 2 else 0  # Binary: has meaningful touches or not
        swing_bonus = 1 if _has_swing(zone) else 0

        quality = source_quality + strength_bonus + touch_bonus + swing_bonus
        # Range: 0 (PSYCHOLOGICAL+LOW+0touch+no_swing) ~ 7 (STRUCTURAL+HIGH+2touch+swing)

        distance = abs(price - current_price)
        candidates.append((price, quality, distance))

    if not candidates:
        return []

    # Quality discount: each quality point = 0.1 ATR closer (max 0.7 ATR discount)
    discount_per_point = atr_value * 0.1 if atr_value > 0 else current_price * 0.001
    candidates.sort(key=lambda pqd: pqd[2] - pqd[1] * discount_per_point)

    return [p for p, q, d in candidates]
```

**设计要点**:
- **返回类型不变**: `List[float]`，所有下游调用方零改动
- **质量权重故意压低**: `strength_bonus` 用 `score - 1` 归一化为 0-2（而非 SL 的 1-3）
- **touch_bonus 简化为二值**: TP 不需要精确的触碰次数，"有意义的触碰"和"没有"就够了
- **discount 上限**: 最大折扣 7 × 0.1 ATR = 0.7 ATR ≈ $280 (BTC)。这意味着：
  - $101,000 的 STRUCTURAL zone 和 $100,720 的 PSYCHOLOGICAL zone 排序等价
  - $102,000 的 STRUCTURAL zone 不会被拉到 $100,000 zone 前面（距离差 > 折扣）
- **`atr_value = 0` 兼容**: 退化为纯距离排序（与当前行为一致）

---

### 改动 2: `calculate_sr_based_sltp()` — TP buffer

**新增参数**: `tp_buffer_multiplier: float = 0.25` (通过 `**kwargs` 兼容旧调用)

```python
def calculate_sr_based_sltp(
    current_price: float,
    side: str,
    sr_zones: Dict[str, Any],
    atr_value: float = 0.0,
    min_rr_ratio: float = 1.5,          # 不变
    atr_buffer_multiplier: float = 0.5,  # SL buffer, 不变
    tp_buffer_multiplier: float = 0.25,  # 新增: TP buffer
    **kwargs,
) -> Tuple[Optional[float], Optional[float], str]:
```

**Step 2 TP 选择修改**:

```python
    # --- TP buffer ---
    tp_buffer = atr_value * tp_buffer_multiplier if atr_value > 0 else current_price * 0.0025

    # --- Step 2: Select TP target ---
    tp_candidates = _collect_tp_candidates(tp_zones, current_price, is_long,
                                            atr_value=atr_value)

    tp_price = None
    tp_method = None

    for i, candidate_tp in enumerate(tp_candidates):
        # Apply TP buffer: move TP in front of zone
        if is_long:
            buffered_tp = candidate_tp - tp_buffer
        else:
            buffered_tp = candidate_tp + tp_buffer

        # Sanity: buffered TP must still be on correct side of entry
        if is_long and buffered_tp <= current_price:
            continue
        if not is_long and buffered_tp >= current_price:
            continue

        # R/R uses buffered (actual) TP price
        reward = abs(buffered_tp - current_price)
        rr = reward / risk if risk > 0 else 0

        if rr >= min_rr_ratio:
            tp_price = buffered_tp
            zone_label = "primary" if i == 0 else f"secondary[{i}]"
            tp_method = f"tp:sr_zone_{zone_label}|buf:{tp_buffer:.0f}"
            break

    # Measured Move fallback (with reduced buffer)
    if tp_price is None and tp_candidates and sl_anchor:
        nearest_tp_zone = tp_candidates[0]
        mm_target = _measured_move_target(
            current_price, sl_anchor, nearest_tp_zone, is_long
        )
        if mm_target:
            # MM uses half buffer (projection target, not historical zone)
            mm_buffer = tp_buffer * 0.5
            if is_long:
                buffered_mm = mm_target - mm_buffer
            else:
                buffered_mm = mm_target + mm_buffer

            reward = abs(buffered_mm - current_price)
            rr = reward / risk if risk > 0 else 0
            if rr >= min_rr_ratio:
                tp_price = buffered_mm
                tp_method = f"tp:measured_move|buf:{mm_buffer:.0f}"

    # No percentage fallback (unchanged)
    if tp_price is None:
        best_rr = 0
        if tp_candidates:
            # Show best possible R/R (with buffer) for diagnostic
            best_candidate = tp_candidates[0]
            if is_long:
                best_buffered = best_candidate - tp_buffer
            else:
                best_buffered = best_candidate + tp_buffer
            best_reward = abs(best_buffered - current_price)
            best_rr = best_reward / risk if risk > 0 and best_reward > 0 else 0
        return None, None, f"R/R {best_rr:.2f}:1 < {min_rr_ratio}:1 (after TP buffer)"

    # Final R/R logging
    method = f"sl:sr_zone|{tp_method}"
    final_reward = abs(tp_price - current_price)
    final_rr = final_reward / risk if risk > 0 else 0
    method += f"|rr:{final_rr:.2f}"

    return sl_price, tp_price, method
```

**关键决策**:
- **`min_rr_ratio` 保持 1.5**: R/R 用 buffer 后价格算，边缘交易被自然淘汰
- **Measured Move 用半 buffer**: MM 是投影不是 zone，不确定性更大用更保守的 buffer
- **`tp_buffer_multiplier = 0` 时**: `tp_buffer = 0`，行为完全等同于修改前——保留回退能力
- **诊断脚本兼容**: `**kwargs` 吸收旧调用中不存在的参数

---

### 改动 3: 配置

**`configs/base.yaml`**:

```yaml
trading_logic:
  min_rr_ratio: 1.5               # 不变
  atr_buffer_multiplier: 0.5      # SL buffer (不变)
  tp_buffer_multiplier: 0.25      # TP buffer (zone 前方, 确保可达; 0=关闭)
```

**`strategy/deepseek_strategy.py`** (config dataclass):

```python
tp_buffer_multiplier: float = 0.25  # TP: ATR buffer for zone front offset
```

**`strategy/deepseek_strategy.py`** (__init__):

```python
self.tp_buffer_multiplier = config.tp_buffer_multiplier
```

**`strategy/deepseek_strategy.py`** (两处调用):

```python
# _validate_sltp_for_entry() 中:
sr_sl, sr_tp, sr_method = calculate_sr_based_sltp(
    ...,
    tp_buffer_multiplier=self.tp_buffer_multiplier,
)

# _reevaluate_sltp_for_existing_position() 中:
new_sl, new_tp, sr_method = calculate_sr_based_sltp(
    ...,
    tp_buffer_multiplier=self.tp_buffer_multiplier,
)
```

**`main_live.py`** (get_strategy_config):

```python
tp_buffer_multiplier=config_manager.get('trading_logic', 'tp_buffer_multiplier', default=0.25),
```

---

### 不改的东西 (明确列出)

| 项目 | 原因 |
|------|------|
| `min_rr_ratio` = 1.5 | 无胜率数据支撑降低；buffer 后 R/R 自然筛掉边缘交易 |
| `_collect_tp_candidates` 返回类型 | `List[float]` 不变，避免 8+ 处调用方报错 |
| `validate_multiagent_sltp()` | Level 1 AI 验证不受影响 |
| 诊断脚本 | `**kwargs` 兼容，零改动 |
| `_measured_move_target()` 函数 | 内部逻辑不变，buffer 在外部应用 |

---

## 场景验证

### 场景 1: 正常交易 (LONG, 强 TP zone)

```
entry=$100,000, ATR=$400, SL zone=$98,500 (HIGH STRUCTURAL)
TP zone=$103,000 (MEDIUM PROJECTED, quality=4)

SL = $98,500 - $200 = $98,300         → risk = $1,700
TP = $103,000 - $100 = $102,900       → reward = $2,900
R/R = 2900/1700 = 1.71:1 ✓ (通过 1.5)
```

**效果**: R/R 从 1.76 微降至 1.71，交易仍被放行，TP 提前 $100 更容易触达。

### 场景 2: 边缘交易 (LONG, R/R 刚过线)

```
entry=$100,000, ATR=$400, SL zone=$98,900 (HIGH STRUCTURAL)
TP zone=$101,700 (LOW PSYCHOLOGICAL, quality=1)

修改前:
  SL = $98,900 - $200 = $98,700       → risk = $1,300
  TP = $101,700                        → reward = $1,700
  R/R = 1700/1300 = 1.31:1 ✗ (不过 1.5)

修改后:
  SL = $98,700 (不变)                  → risk = $1,300
  TP = $101,700 - $100 = $101,600      → reward = $1,600
  R/R = 1600/1300 = 1.23:1 ✗ (不过 1.5)
```

**效果**: 两种情况都被拒绝。边缘交易无论如何都不该做。

### 场景 3: 质量感知排序 (两个近距离 zone)

```
entry=$100,000, ATR=$400

Zone A: $101,200 (LOW PSYCHOLOGICAL, quality=1, distance=1200)
Zone B: $101,400 (HIGH STRUCTURAL, quality=7, distance=1400)

修改前: 选 A (距离 1200 < 1400)
修改后:
  A sort_key = 1200 - 1×40 = 1160
  B sort_key = 1400 - 7×40 = 1120  ← B 更小, 排前面
  选 B ($101,400)，buffer 后 = $101,300

  R/R check: reward=1300, risk=1300 → R/R=1.0 ✗
  尝试下一个: A ($101,200), buffer 后 = $101,100
  R/R: reward=1100 → R/R=0.85 ✗
  → 交易被拒绝 (R/R < 1.5)
```

**效果**: 优先选了更强的 zone，但 R/R 不够都被拒绝——正确行为。

### 场景 4: `tp_buffer_multiplier = 0` 回退

```
configs/base.yaml: tp_buffer_multiplier: 0

tp_buffer = 400 * 0 = 0
buffered_tp = candidate_tp - 0 = candidate_tp (原始价格)
```

**效果**: 完全等同于修改前行为。可随时关闭 buffer。

### 场景 5: Measured Move + 半 buffer

```
entry=$100,000, ATR=$400
SL zone=$98,500, 最近 TP zone=$101,000 (R/R 不够)
MM target = $101,000 + ($101,000 - $98,500) = $103,500

mm_buffer = $100 × 0.5 = $50
buffered_mm = $103,500 - $50 = $103,450
R/R = 3450/1700 = 2.03:1 ✓
```

**效果**: MM 路径仅减去 $50 buffer，几乎不影响。

---

## 风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 调用方报错 | 零 | - | 返回类型不变 + `**kwargs` 兼容 |
| 交易频率下降 | 低 | 中 | ATR×0.25 很小 ($100)，R/R 影响 < 6% |
| 趋势市过早止盈 | 中 | 低 | buffer 仅 $100，动态 SL/TP 会追踪利润 |
| 强 zone 过度偏好 | 低 | 低 | discount 上限 0.7 ATR，距离仍是主维度 |
| 回退需求 | - | - | `tp_buffer_multiplier: 0` 完全回退 |

---

## 实施步骤

1. 修改 `utils/sr_sltp_calculator.py` — `_collect_tp_candidates()` + `calculate_sr_based_sltp()`
2. 修改 `configs/base.yaml` — 新增 `tp_buffer_multiplier: 0.25`
3. 修改 `strategy/deepseek_strategy.py` — dataclass + __init__ + 两处调用
4. 修改 `main_live.py` — 读取配置
5. 运行 `python3 scripts/smart_commit_analyzer.py` 回归检测
