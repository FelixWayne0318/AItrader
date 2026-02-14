"""
v5.1: S/R-Based SL/TP Calculator

核心逻辑:
1. SL = 关键支撑/阻力位 + ATR缓冲 (缓冲保护，防止假突破触发)
2. TP = 关键阻力/支撑位 - ATR缓冲 (zone 前方止盈，提高触达率)
3. R/R >= 1.5 才接受，否则尝试次级 zone → Measured Move → 拒绝
4. 无百分比兜底 — 没有 S/R zone 时拒绝交易 (S/R veto is final)

v5.1 改进 (vs v4.3):
- TP buffer: 在 zone 前方放置 TP (ATR × 0.25)，因价格在 zone 附近减速 (Osler 2003)
- 质量感知 TP 排序: 距离为主维度，质量提供"距离折扣" (每点 = 0.1 ATR)
- Measured Move 也加 buffer (半 size)，投影目标不确定性更高
- tp_buffer_multiplier = 0 时完全等同于 v4.3 行为 (可回退)

v4.3 改进 (vs v4.2):
- 移除 SL 百分比兜底: 无 S/R zone 时直接拒绝 (不用任意 2% SL)
- 移除 TP 百分比兜底: 只有 S/R zone + Measured Move 两种路径
- 设计原则: "S/R drives SL/TP" — 没有 S/R 支撑则不交易

v4.2 改进 (vs v4.1):
- SL anchor 选择感知 zone 质量: source_type + touch_count + has_swing_point
  (Chung & Bellotti 2021: 多次触碰的 S/R 更可靠)
- TP 候选按结构质量优先排序 (STRUCTURAL > PROJECTED > PSYCHOLOGICAL)
- BB/SMA 已从 zone 计算中移除 (见 sr_zone_calculator v4.2)

学术参考:
- Bulkowski (2021): Measured Move 85% hit rate
- Tsinaslanidis (2022): Fibonacci 回撤证伪 → 不实现
- Osler (2003): Round number 聚集效应, zone 前方价格减速
- Chung & Bellotti (2021): touch_count 越多的 S/R 越可靠，S/R 随时间衰减
- Lopez de Prado (2018): Triple Barrier Method, pt_sl=[1,2]
"""

import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# Strength priority for zone selection (higher = more reliable anchor)
_STRENGTH_SCORE = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}

# Source type quality for SL/TP anchor selection
# Academic basis: Swing points (STRUCTURAL) have P=0.81-0.88 (Spitsin 2025),
# Order flow clusters confirm real demand (Osler 2003),
# Pivots are mathematical projections with no historical confirmation
_SOURCE_QUALITY = {
    'STRUCTURAL': 3,       # Swing points + volume confirmation (Spitsin P=0.81-0.88)
    'ORDER_FLOW': 2,       # Real order clusters (Osler 2003)
    'PROJECTED': 1,        # Pivot points (mathematical, no historical confirmation)
    'PSYCHOLOGICAL': 0,    # Round numbers (auxiliary)
    'TECHNICAL': 0,        # BB/SMA (should no longer appear in zones after v4.2)
}


def _extract_price(zone) -> Optional[float]:
    """Extract price_center from SRZone (dataclass or dict)."""
    if zone is None:
        return None
    if hasattr(zone, 'price_center'):
        return zone.price_center
    if isinstance(zone, dict):
        return zone.get('price_center')
    return None


def _get_strength(zone) -> str:
    """Extract strength from SRZone (dataclass or dict)."""
    if hasattr(zone, 'strength'):
        return zone.strength
    if isinstance(zone, dict):
        return zone.get('strength', 'LOW')
    return 'LOW'


def _get_source_type(zone) -> str:
    """Extract source_type from SRZone (dataclass or dict)."""
    if hasattr(zone, 'source_type'):
        return zone.source_type
    if isinstance(zone, dict):
        return zone.get('source_type', 'TECHNICAL')
    return 'TECHNICAL'


def _get_touch_count(zone) -> int:
    """Extract touch_count from SRZone (dataclass or dict)."""
    if hasattr(zone, 'touch_count'):
        return zone.touch_count or 0
    if isinstance(zone, dict):
        return zone.get('touch_count', 0)
    return 0


def _has_swing(zone) -> bool:
    """Check if zone has swing point confirmation."""
    if hasattr(zone, 'has_swing_point'):
        return zone.has_swing_point
    if isinstance(zone, dict):
        return zone.get('has_swing_point', False)
    return False


def _select_sl_anchor(
    zones: List,
    current_price: float,
    is_long: bool,
    atr_value: float,
) -> Optional[float]:
    """
    Select the best SL anchor zone, considering structural quality.

    For LONG: strongest support zone below current price.
    For SHORT: strongest resistance zone above current price.

    v4.2 scoring:
      score = strength×10 + source_quality×5 + touch_bonus×3 + swing_bonus×2 + proximity

    This ensures:
    - HIGH STRUCTURAL zone always beats MEDIUM PROJECTED zone
    - Within same strength, STRUCTURAL (swing-confirmed) beats PROJECTED (mathematical)
    - Within same quality tier, nearer zone preferred
    - Zone must be within 5× ATR distance (sanity limit)
    """
    if not zones:
        return None

    max_distance = atr_value * 5 if atr_value > 0 else current_price * 0.05

    best_zone = None
    best_score = -1

    for zone in zones:
        price = _extract_price(zone)
        if not price or price <= 0:
            continue

        # For LONG SL: support must be below price
        # For SHORT SL: resistance must be above price
        if is_long and price >= current_price:
            continue
        if not is_long and price <= current_price:
            continue

        distance = abs(current_price - price)
        if distance > max_distance:
            continue

        # --- v4.2: Multi-factor scoring ---
        strength = _get_strength(zone)
        strength_score = _STRENGTH_SCORE.get(strength, 1)

        source_type = _get_source_type(zone)
        quality_score = _SOURCE_QUALITY.get(source_type, 0)

        touch_count = _get_touch_count(zone)
        # Chung & Bellotti (2021): 2-3 touches optimal, 4+ diminishing
        if touch_count >= 2:
            touch_bonus = min(touch_count, 3)  # Cap at 3 (optimal)
        else:
            touch_bonus = 0

        swing_bonus = 2 if _has_swing(zone) else 0

        proximity = 1.0 - (distance / max_distance) if max_distance > 0 else 0

        score = (strength_score * 10
                 + quality_score * 5
                 + touch_bonus * 3
                 + swing_bonus
                 + proximity)

        if score > best_score:
            best_score = score
            best_zone = price

    return best_zone


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

    For LONG: resistance zones above current price.
    For SHORT: support zones below current price.
    """
    candidates = []
    for zone in zones:
        price = _extract_price(zone)
        if not price or price <= 0:
            continue

        if is_long and price > current_price:
            pass
        elif not is_long and price < current_price:
            pass
        else:
            continue

        # Quality score (0-7 range, intentionally lower than SL scoring)
        source_quality = _SOURCE_QUALITY.get(_get_source_type(zone), 0)
        strength_bonus = _STRENGTH_SCORE.get(_get_strength(zone), 1) - 1  # 0-2 (LOW=0)
        touch_count = _get_touch_count(zone)
        touch_bonus = 1 if touch_count >= 2 else 0  # Binary: meaningful touches or not
        swing_bonus = 1 if _has_swing(zone) else 0

        quality = source_quality + strength_bonus + touch_bonus + swing_bonus
        distance = abs(price - current_price)
        candidates.append((price, quality, distance))

    if not candidates:
        return []

    # Quality discount: each quality point = 0.1 ATR closer (max 0.7 ATR discount)
    discount_per_point = atr_value * 0.1 if atr_value > 0 else current_price * 0.001
    candidates.sort(key=lambda pqd: pqd[2] - pqd[1] * discount_per_point)

    return [p for p, q, d in candidates]


def _measured_move_target(
    current_price: float,
    sl_anchor: float,
    nearest_tp: float,
    is_long: bool,
) -> Optional[float]:
    """
    Measured Move projection (Bulkowski 2021: 85% hit rate).

    When price breaks through the nearest S/R zone, project
    the box height as the next target.

    For LONG:  target = nearest_resistance + box_height
    For SHORT: target = nearest_support - box_height

    Box height = distance between SL anchor and nearest opposite zone.
    """
    if not sl_anchor or not nearest_tp:
        return None

    # Box height = full range between SL anchor and nearest TP zone
    box_height = abs(nearest_tp - sl_anchor)

    if box_height <= 0:
        return None

    if is_long:
        target = nearest_tp + box_height
    else:
        target = nearest_tp - box_height

    # Sanity: target must be on correct side
    if is_long and target <= current_price:
        return None
    if not is_long and target >= current_price:
        return None

    return target


def calculate_sr_based_sltp(
    current_price: float,
    side: str,
    sr_zones: Dict[str, Any],
    atr_value: float = 0.0,
    min_rr_ratio: float = 1.5,
    atr_buffer_multiplier: float = 0.5,
    tp_buffer_multiplier: float = 0.25,
    **kwargs,
) -> Tuple[Optional[float], Optional[float], str]:
    """
    v5.1: Calculate SL/TP anchored to S/R zones with ATR buffer.

    No percentage fallback — S/R veto is final. If no valid S/R zone
    exists for SL or TP, returns (None, None) to reject the trade.

    Algorithm:
    1. Select SL anchor: strongest S/R zone in protective direction
       → No zone found → REJECT (no arbitrary percentage SL)
    2. SL = anchor ± ATR buffer (behind zone, absorb false breakouts)
    3. Select TP target: iterate S/R zones until R/R >= min_rr_ratio
       → TP placed in front of zone (ATR × tp_buffer_multiplier)
       → No zone passes → try Measured Move (Bulkowski 2021, half buffer)
       → Still no valid TP → REJECT (no arbitrary percentage TP)

    v5.1 improvements (vs v4.3):
    - TP buffer: place TP in front of zone to improve hit probability
      (Osler 2003: price decelerates near S/R zones)
    - Quality-aware TP sorting: quality provides distance discount
    - Measured Move also gets buffer (half size, projection uncertainty)

    Parameters
    ----------
    current_price : float
        Current market price (or entry price for new positions).
    side : str
        "BUY" for long, "SELL" for short.
    sr_zones : Dict
        S/R zone data from SRZoneCalculator.calculate().
        Keys: 'support_zones', 'resistance_zones', 'nearest_support', 'nearest_resistance'.
    atr_value : float
        Current ATR value for buffer calculation. 0 = use 0.5% price fallback.
    min_rr_ratio : float
        Minimum Risk/Reward ratio required. Default 1.5.
    atr_buffer_multiplier : float
        ATR multiplier for SL buffer. Default 0.5.
    tp_buffer_multiplier : float
        ATR multiplier for TP buffer (placed in front of zone). Default 0.25.
        Set to 0 to disable TP buffer (equivalent to pre-v5.1 behavior).

    Returns
    -------
    Tuple[Optional[float], Optional[float], str]
        (sl_price, tp_price, method_description)
        Returns (None, None, reason) if no valid SL/TP can be determined.
    """
    if current_price <= 0:
        return None, None, "invalid current price"

    is_long = side.upper() in ('BUY', 'LONG')

    # --- Extract zone lists ---
    support_zones = sr_zones.get('support_zones', [])
    resistance_zones = sr_zones.get('resistance_zones', [])

    # Fallback to nearest_* if zone lists are empty
    if not support_zones:
        ns = sr_zones.get('nearest_support')
        if ns:
            support_zones = [ns]
    if not resistance_zones:
        nr = sr_zones.get('nearest_resistance')
        if nr:
            resistance_zones = [nr]

    # --- SL zones and TP zones based on direction ---
    if is_long:
        sl_zones = support_zones
        tp_zones = resistance_zones
    else:
        sl_zones = resistance_zones
        tp_zones = support_zones

    # --- ATR buffer ---
    if atr_value > 0:
        buffer = atr_value * atr_buffer_multiplier
    else:
        buffer = current_price * 0.005  # 0.5% fallback for buffer only

    # ====================================================================
    # Step 1: Select SL anchor (strongest zone in protective direction)
    # v4.3: No percentage fallback — no zone means no trade
    # ====================================================================
    sl_anchor = _select_sl_anchor(sl_zones, current_price, is_long, atr_value)

    if not sl_anchor:
        direction = "support" if is_long else "resistance"
        return None, None, f"no S/R zone for SL anchor ({direction} side empty)"

    # SL = anchor ± ATR buffer (behind the zone)
    if is_long:
        sl_price = sl_anchor - buffer
    else:
        sl_price = sl_anchor + buffer

    # Validate SL is on correct side
    if is_long and sl_price >= current_price:
        sl_price = current_price - buffer * 2
    if not is_long and sl_price <= current_price:
        sl_price = current_price + buffer * 2

    risk = abs(current_price - sl_price)
    if risk <= 0:
        return None, None, "zero risk distance"

    # ====================================================================
    # Step 2: Select TP target — iterate zones until R/R satisfied
    # v5.1: Quality-aware sorting + TP buffer (in front of zone)
    # ====================================================================
    tp_candidates = _collect_tp_candidates(tp_zones, current_price, is_long,
                                           atr_value=atr_value)

    # TP buffer: place TP in front of zone to improve hit probability
    # (Osler 2003: price decelerates near S/R zones)
    tp_buffer = atr_value * tp_buffer_multiplier if atr_value > 0 else current_price * 0.0025

    tp_price = None
    tp_method = None

    # Try each TP candidate (quality-weighted distance, nearest first)
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

    # If no zone gave good R/R → try Measured Move (Bulkowski 2021: 85% hit rate)
    # Measured Move uses half buffer (projection target, not historical zone)
    if tp_price is None and tp_candidates and sl_anchor:
        nearest_tp_zone = tp_candidates[0]
        mm_target = _measured_move_target(
            current_price, sl_anchor, nearest_tp_zone, is_long
        )
        if mm_target:
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

    # v5.1: No percentage fallback — if all S/R paths failed, reject
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

    # Build method description
    method = f"sl:sr_zone|{tp_method}"

    # Final R/R for logging
    final_reward = abs(tp_price - current_price)
    final_rr = final_reward / risk if risk > 0 else 0
    method += f"|rr:{final_rr:.2f}"

    return sl_price, tp_price, method
