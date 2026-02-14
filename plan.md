# TP 不对称修复方案 — 详细实施计划

## 问题诊断

当前 `sr_sltp_calculator.py` 中 SL 和 TP 的选择逻辑不对称：

| 维度 | SL (`_select_sl_anchor`) | TP (`_collect_tp_candidates`) |
|------|-------------------------|-------------------------------|
| 选择标准 | 多因子质量评分 | 距离排序，质量仅做 tiebreak |
| Buffer | ATR × 0.5 (zone 后方) | 无 |
| R/R 计算 | 用 buffer 后价格 | 用 zone 原始价格 |
| 结果 | 选远处强 zone，SL 不容易触发 | 选近处弱 zone，TP 不一定能到达 |

**后果**：名义 R/R = 1.5 虚高，TP 实际触达率低于预期。

---

## 修改文件清单

| 文件 | 改动内容 |
|------|---------|
| `utils/sr_sltp_calculator.py` | 核心修复 (3 个函数) |
| `configs/base.yaml` | 新增 `tp_buffer_multiplier` 参数 |
| `strategy/deepseek_strategy.py` | 传递新参数到 calculator |
| `main_live.py` | 从 ConfigManager 读取新参数 |

---

## 改动 1: `_collect_tp_candidates()` — TP 引入质量评分

**文件**: `utils/sr_sltp_calculator.py` L172-205

**当前代码**:
```python
def _collect_tp_candidates(
    zones: List,
    current_price: float,
    is_long: bool,
) -> List[float]:
    candidates = []
    for zone in zones:
        price = _extract_price(zone)
        quality = _SOURCE_QUALITY.get(_get_source_type(zone), 0)
        candidates.append((price, quality))

    # 距离优先，质量仅做 tiebreak
    candidates.sort(key=lambda pq: (abs(pq[0] - current_price), -pq[1]))
    return [p for p, q in candidates]
```

**问题**:
- 返回 `List[float]` 丢失了质量信息
- 排序时质量权重为零（纯 tiebreak）
- 弱 zone (PSYCHOLOGICAL, quality=0) 和强 zone (STRUCTURAL, quality=3) 等同对待

**修改后**:
```python
# TP candidate 结构: (price, quality_score)
# quality_score = _SOURCE_QUALITY + strength_bonus + touch_bonus
#
# 排序策略: 在 1×ATR 距离段内，优先选质量更高的 zone
# 超过 1×ATR 距离差，近的优先

def _collect_tp_candidates(
    zones: List,
    current_price: float,
    is_long: bool,
    atr_value: float = 0.0,            # 新增: 用于距离分段
    min_quality: int = 1,              # 新增: 最低质量门槛
) -> List[Tuple[float, int]]:          # 改: 返回 (price, quality) 元组
    candidates = []
    for zone in zones:
        price = _extract_price(zone)
        if not price or price <= 0:
            continue

        # 方向过滤
        if is_long and price <= current_price:
            continue
        if not is_long and price >= current_price:
            continue

        # 计算质量分 (与 SL 对齐)
        source_quality = _SOURCE_QUALITY.get(_get_source_type(zone), 0)
        strength_bonus = _STRENGTH_SCORE.get(_get_strength(zone), 1)
        touch_count = _get_touch_count(zone)
        touch_bonus = min(touch_count, 3) if touch_count >= 2 else 0
        swing_bonus = 1 if _has_swing(zone) else 0

        quality = source_quality + strength_bonus + touch_bonus + swing_bonus
        # quality 范围: 0 (PSYCHOLOGICAL+LOW+0touch) ~ 10 (STRUCTURAL+HIGH+3touch+swing)

        # 最低质量门槛: 过滤纯心理关口等弱 zone
        if quality < min_quality:
            continue

        candidates.append((price, quality))

    if not candidates:
        return []

    # 排序: 在 1×ATR 距离段内按质量排序，跨段按距离排序
    band = atr_value if atr_value > 0 else current_price * 0.01
    candidates.sort(key=lambda pq: (
        int(abs(pq[0] - current_price) / band),  # 距离段 (0, 1, 2...)
        -pq[1],                                    # 同段内质量优先
    ))
    return candidates  # 返回 (price, quality) 元组
```

**关键设计决策**:
- `min_quality = 1` 意味着: PSYCHOLOGICAL (quality=0+1=1 if LOW) 勉强通过,
  但纯 TECHNICAL(0) + LOW(1) 的 zone 也能过。
  单独的 PSYCHOLOGICAL + LOW + 0 touch + no swing = 0+1+0+0 = 1，刚好通过。
  这是合理的——整数关口还是有参考价值的。
- 距离分段用 1×ATR: BTC 15min ATR ≈ $300-500，
  所以只有在距离差 < $300 时才优先选质量高的 zone。
  距离差 > $300 则近的优先（可达性更重要）。

---

## 改动 2: `calculate_sr_based_sltp()` — TP buffer + R/R 用实际价格

**文件**: `utils/sr_sltp_calculator.py` L248-399

**新增参数**: `tp_buffer_multiplier: float = 0.3`

**核心修改** (Step 2 部分，约 L352-397):

```python
# 当前: TP 直接用 zone 原始价格
tp_price = candidate_tp                                    # zone 原始价

# 修改后: TP = zone ∓ ATR × tp_buffer (zone 前方)
tp_buffer = atr_value * tp_buffer_multiplier if atr_value > 0 else current_price * 0.003
if is_long:
    buffered_tp = candidate_tp - tp_buffer   # 阻力位前方 (偏低)
else:
    buffered_tp = candidate_tp + tp_buffer   # 支撑位前方 (偏高)

# Sanity: buffer 后的 TP 必须仍在正确一侧
if is_long and buffered_tp <= current_price:
    continue  # buffer 后 TP 跑到入场价下方了, 跳过这个 zone
if not is_long and buffered_tp >= current_price:
    continue

# R/R 用 buffer 后的价格
reward = abs(buffered_tp - current_price)   # 实际可达 reward
rr = reward / risk if risk > 0 else 0

if rr >= min_rr_ratio:
    tp_price = buffered_tp                  # 存 buffer 后的价格
    tp_method = f"tp:sr_zone[{i}]|buf:{tp_buffer:.0f}"
    break
```

**Measured Move 也要调整**:
```python
# 当前: mm_target 直接使用
# 修改后: mm_target 不加 buffer (因为 Measured Move 本身就是投影目标，不是 zone)
# Bulkowski (2021) 的 85% 命中率是基于原始 MM 目标的，加 buffer 会改变统计基础
# 所以 Measured Move 路径不加 TP buffer，保持原样
```

**最终 R/R 日志也改**:
```python
final_reward = abs(tp_price - current_price)  # tp_price 已经是 buffer 后的
final_rr = final_reward / risk
method += f"|rr:{final_rr:.2f}"
```

---

## 改动 3: `_collect_tp_candidates` 无质量候选时的降级

如果 `min_quality` 过滤掉了所有 zone，需要降级处理:

```python
# 在 calculate_sr_based_sltp() 中:
tp_candidates = _collect_tp_candidates(tp_zones, current_price, is_long,
                                        atr_value=atr_value, min_quality=1)

# 如果质量过滤后没有候选，降级到不过滤
if not tp_candidates:
    tp_candidates = _collect_tp_candidates(tp_zones, current_price, is_long,
                                            atr_value=atr_value, min_quality=0)
    # 标记降级 (用于日志)
    tp_degraded = True
```

这保证了: 优先选质量 >= 1 的 zone，万一全都不合格，也不会直接拒绝交易。

---

## 改动 4: 配置参数

**`configs/base.yaml`** (约 L34，`atr_buffer_multiplier` 下方):

```yaml
trading_logic:
  atr_buffer_multiplier: 0.5       # SL: ATR 缓冲倍数 (zone 后方, 防假突破)
  tp_buffer_multiplier: 0.3        # TP: ATR 缓冲倍数 (zone 前方, 确保可达)
  min_rr_ratio: 1.2                # 实际 R/R 门槛 (buffer 后价格计算, 原 1.5 是名义值)
```

**`strategy/deepseek_strategy.py`** (config dataclass + __init__):

```python
# dataclass 新增字段:
tp_buffer_multiplier: float = 0.3

# __init__ 中:
self.tp_buffer_multiplier = config.tp_buffer_multiplier

# 调用 calculate_sr_based_sltp 时传入:
sr_sl, sr_tp, sr_method = calculate_sr_based_sltp(
    current_price=entry_price,
    side=side.name,
    sr_zones=self.latest_sr_zones_data,
    atr_value=self._cached_atr_value,
    min_rr_ratio=self.min_rr_ratio,
    atr_buffer_multiplier=self.atr_buffer_multiplier,
    tp_buffer_multiplier=self.tp_buffer_multiplier,       # 新增
)
```

**`main_live.py`** (get_strategy_config):

```python
tp_buffer_multiplier=config_manager.get('trading_logic', 'tp_buffer_multiplier', default=0.3),
```

---

## 改动 5: `min_rr_ratio` 从 1.5 → 1.2

**理由**:

加 TP buffer 前后的等价关系 (以 BTC 为例):

```
假设: entry=$100,000, SL zone=$98,500, TP zone=$103,000, ATR=$400

修改前 (无 TP buffer):
  SL = $98,500 - $200 = $98,300   → risk = $1,700
  TP = $103,000                    → reward = $3,000
  名义 R/R = 3000/1700 = 1.76     ✓ (通过 1.5 门槛)

修改后 (TP buffer = ATR × 0.3):
  SL = $98,300 (不变)              → risk = $1,700
  TP = $103,000 - $120 = $102,880  → reward = $2,880
  实际 R/R = 2880/1700 = 1.69     ✓ (通过 1.2 门槛)

  如果保持 1.5 门槛:
  TP 需要 $1,700 × 1.5 = $2,550 的 reward
  $102,880 → reward = $2,880 > $2,550 → 也通过

  但如果 TP zone 更近 (如 $101,800):
  修改前: reward = $1,800, R/R = 1.06 → 失败
  修改后: reward = $1,680, R/R = 0.99 → 失败
  两种情况都失败，不影响
```

实际上在大多数情况下, ATR×0.3 的 buffer ($120) 相对于 reward ($2000+) 很小，
R/R 下降幅度约 4-6%。从 1.5 降到 1.2 的主要原因不是 buffer 造成的下降，
而是**承认名义 R/R 本来就虚高**——用实际可达的 TP 计算后，
1.2 的实际 R/R 比 1.5 的名义 R/R 更接近真实期望值。

**但也有风险**: 降到 1.2 意味着更多边缘交易会被放行。
如果胜率没有因为 TP buffer 而明显提高，期望值可能为负。

**保守做法**: 先设 1.3 (而非 1.2)，留有安全边际。上线后通过实际交易统计调整。

---

## 影响范围分析

### 调用链路 (谁调用了 `calculate_sr_based_sltp`):

1. **开仓路径**: `_validate_sltp_for_entry()` L3851 → 所有参数都会传入
2. **动态更新路径**: `_reevaluate_sltp_for_existing_position()` L4892 → 也需要传入 `tp_buffer_multiplier`
3. **Zone cross-validation**: `_zone_cross_validate_sltp()` L3834 → 不调用此函数，不受影响
4. **诊断工具**: `scripts/diagnose_realtime.py` → 如果直接调用了此函数，需要同步更新签名

### 不受影响的部分:

- `validate_multiagent_sltp()` (Level 1 AI SL/TP 验证) → 不涉及 zone 选择
- `_submit_bracket_order()` → 只消费 SL/TP 价格，不关心如何计算
- `on_position_opened()` → 同上
- `_update_sltp_quantity()` → 只更新数量，不更新价格

---

## 具体代码改动位置总结

| # | 文件 | 行号 | 改动 |
|---|------|------|------|
| 1 | `sr_sltp_calculator.py` | L172-205 | 重写 `_collect_tp_candidates()`：加质量评分 + 距离分段排序 + 最低质量门槛 + 返回元组 |
| 2 | `sr_sltp_calculator.py` | L248-256 | `calculate_sr_based_sltp()` 签名加 `tp_buffer_multiplier` |
| 3 | `sr_sltp_calculator.py` | L352-397 | Step 2: TP 加 buffer + R/R 用 buffer 后价格 + Measured Move 不加 buffer |
| 4 | `configs/base.yaml` | L34-35 | 加 `tp_buffer_multiplier: 0.3`，改 `min_rr_ratio: 1.3` |
| 5 | `strategy/deepseek_strategy.py` | L130 | dataclass 加 `tp_buffer_multiplier` 字段 |
| 6 | `strategy/deepseek_strategy.py` | L301 | `__init__` 存 `self.tp_buffer_multiplier` |
| 7 | `strategy/deepseek_strategy.py` | L3851-3858 | `_validate_sltp_for_entry()` 传入 `tp_buffer_multiplier` |
| 8 | `strategy/deepseek_strategy.py` | L4892-4898 | `_reevaluate_sltp_for_existing_position()` 传入 `tp_buffer_multiplier` |
| 9 | `main_live.py` | L231 | `get_strategy_config()` 读取 `tp_buffer_multiplier` |

---

## 修改前后行为对比

### 场景 1: 正常 S/R zone (LONG)

```
entry = $100,000, ATR = $400
SL zone = $98,500 (HIGH, STRUCTURAL, 3 touch) → 强
TP zone = $103,000 (MEDIUM, PROJECTED, 1 touch) → 中等

修改前:
  SL = $98,500 - $200 = $98,300 (zone 后方)
  TP = $103,000 (zone 原价)
  R/R = $3,000 / $1,700 = 1.76:1 ✓

修改后:
  SL = $98,300 (不变)
  TP = $103,000 - $120 = $102,880 (zone 前方)
  R/R = $2,880 / $1,700 = 1.69:1 ✓
  效果: TP 从 zone 上退后 $120，更容易触达
```

### 场景 2: 弱 TP zone + 远处强 zone (LONG)

```
entry = $100,000, ATR = $400

TP candidates:
  Zone A: $101,000 (LOW, PSYCHOLOGICAL, 0 touch) → quality = 0+1+0+0 = 1
  Zone B: $101,300 (HIGH, STRUCTURAL, 2 touch)   → quality = 3+3+2+0 = 8

修改前:
  选 Zone A ($101,000) — 最近优先
  R/R = $1,000 / $1,700 = 0.59:1 ✗ (失败, 尝试 Zone B)
  选 Zone B ($101,300) — R/R = 0.76:1 ✗ (也失败)

修改后:
  Zone A 和 B 在同一距离段内 (差 $300 < 1×ATR=$400)
  按质量排序: Zone B (quality=8) > Zone A (quality=1)
  选 Zone B ($101,300)，buffer 后 = $101,180
  R/R = $1,180 / $1,700 = 0.69:1 ✗ (失败)
  效果: 同样失败，但选了更可靠的 zone。如果 zone 更远则差异更明显。
```

### 场景 3: Measured Move 不加 buffer

```
entry = $100,000, ATR = $400
SL zone = $98,500
TP zone最近 = $101,000 (R/R < 1.3)
Measured Move = $101,000 + ($101,000 - $98,500) = $103,500

修改前: MM target = $103,500
修改后: MM target = $103,500 (不变, Bulkowski 统计基础不改)
R/R = $3,500 / $1,700 = 2.06:1 ✓
```

---

## 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 交易频率下降 (质量过滤) | 低 | 中 | `min_quality=1` 门槛很低，降级机制兜底 |
| R/R 门槛降低导致亏损交易增加 | 中 | 中 | 用 1.3 而非 1.2，留安全边际 |
| 动态更新路径行为变化 | 低 | 低 | 同一函数，参数一致传入 |
| TP buffer 导致在趋势市中过早止盈 | 中 | 低 | buffer 仅 ATR×0.3 ≈ $120，影响很小 |
| `_collect_tp_candidates` 返回类型变化 | 确定 | 中 | 需要更新所有调用方 |

---

## 验证计划

1. **单元测试**: 在现有 `tests/` 中添加测试用例验证 TP buffer 和质量过滤
2. **日志验证**: 修改后运行 `--dry-run`，对比 SL/TP 输出变化
3. **回归检测**: `python3 scripts/smart_commit_analyzer.py`
