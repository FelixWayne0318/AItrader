"""
v4.1: S/R-Based SL/TP Calculator (Rewrite)

核心逻辑 (参考对称性分析):
1. SL = 关键支撑/阻力位 + ATR缓冲 (缓冲保护，防止假突破触发)
2. TP = 关键阻力/支撑位 (直接锚定，不减缓冲)
3. R/R >= 1.5 才接受，否则尝试次级 zone → Measured Move → 拒绝

改进 (vs v4.0):
- 遍历所有 zone，按 strength 加权选择最优 SL/TP 锚点
- TP 直接使用 S/R zone.price_center (不减缓冲)
- R/R 不足时尝试次级 zone + Measured Move 投射 (Bulkowski 85%)
- R/R 仍不足时直接拒绝 (return None)，不人为调整 TP

学术参考:
- Bulkowski (2021): Measured Move 85% hit rate
- Tsinaslanidis (2022): Fibonacci 回撤证伪 → 不实现
- Osler (2003): Round number 聚集效应
"""

import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# Strength priority for zone selection (higher = more reliable anchor)
_STRENGTH_SCORE = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}


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


def _select_sl_anchor(
    zones: List,
    current_price: float,
    is_long: bool,
    atr_value: float,
) -> Optional[float]:
    """
    Select the best SL anchor zone.

    For LONG: strongest support zone below current price.
    For SHORT: strongest resistance zone above current price.

    Selection logic:
    - Prefer HIGH strength over closer MEDIUM/LOW
    - Within same strength, prefer nearer zone
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

        strength = _get_strength(zone)
        strength_score = _STRENGTH_SCORE.get(strength, 1)

        # Score = strength × 10 + proximity bonus (nearer = higher)
        # This ensures HIGH zones beat MEDIUM zones regardless of distance
        proximity = 1.0 - (distance / max_distance) if max_distance > 0 else 0
        score = strength_score * 10 + proximity

        if score > best_score:
            best_score = score
            best_zone = price

    return best_zone


def _collect_tp_candidates(
    zones: List,
    current_price: float,
    is_long: bool,
) -> List[float]:
    """
    Collect all valid TP target prices, sorted by distance (nearest first).

    For LONG: resistance zones above current price.
    For SHORT: support zones below current price.
    """
    candidates = []
    for zone in zones:
        price = _extract_price(zone)
        if not price or price <= 0:
            continue

        if is_long and price > current_price:
            candidates.append(price)
        elif not is_long and price < current_price:
            candidates.append(price)

    # Sort by distance from current price (nearest first)
    candidates.sort(key=lambda p: abs(p - current_price))
    return candidates


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
    default_sl_pct: float = 0.02,
    default_tp_pct: float = 0.03,
) -> Tuple[Optional[float], Optional[float], str]:
    """
    Calculate SL/TP anchored to S/R zones with ATR buffer.

    Algorithm:
    1. Select SL anchor: strongest S/R zone in protective direction
    2. SL = anchor ± ATR buffer (behind zone, absorb false breakouts)
    3. Select TP target: S/R zone directly (no buffer subtraction)
    4. Validate R/R >= min_rr_ratio
    5. If R/R poor: try next zone → Measured Move → reject

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
        Current ATR value for buffer calculation. 0 = use percentage fallback.
    min_rr_ratio : float
        Minimum Risk/Reward ratio required. Default 1.5.
    atr_buffer_multiplier : float
        ATR multiplier for SL buffer. Default 0.5.
    default_sl_pct : float
        Fallback SL percentage if no S/R zones. Default 2%.
    default_tp_pct : float
        Fallback TP percentage if no S/R zones. Default 3%.

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
        buffer = current_price * 0.005  # 0.5% fallback

    # ====================================================================
    # Step 1: Select SL anchor (strongest zone in protective direction)
    # ====================================================================
    sl_anchor = _select_sl_anchor(sl_zones, current_price, is_long, atr_value)
    method_parts = []

    if sl_anchor:
        # SL = anchor ± ATR buffer (behind the zone)
        if is_long:
            sl_price = sl_anchor - buffer
        else:
            sl_price = sl_anchor + buffer
        method_parts.append("sl:sr_zone")
    else:
        # Percentage fallback
        if is_long:
            sl_price = current_price * (1 - default_sl_pct)
        else:
            sl_price = current_price * (1 + default_sl_pct)
        method_parts.append("sl:pct_fallback")

    # Validate SL is on correct side
    if is_long and sl_price >= current_price:
        sl_price = current_price - buffer * 2
        method_parts.append("sl:adjusted")
    if not is_long and sl_price <= current_price:
        sl_price = current_price + buffer * 2
        method_parts.append("sl:adjusted")

    risk = abs(current_price - sl_price)
    if risk <= 0:
        return None, None, "zero risk distance"

    # ====================================================================
    # Step 2: Select TP target — iterate zones until R/R satisfied
    # ====================================================================
    tp_candidates = _collect_tp_candidates(tp_zones, current_price, is_long)

    tp_price = None
    tp_method = None

    # Try each TP candidate (nearest first)
    for i, candidate_tp in enumerate(tp_candidates):
        reward = abs(candidate_tp - current_price)
        rr = reward / risk if risk > 0 else 0

        if rr >= min_rr_ratio:
            tp_price = candidate_tp
            tp_method = f"tp:sr_zone[{i}]" if i == 0 else f"tp:sr_zone_secondary[{i}]"
            break

    # If no zone gave good R/R → try Measured Move
    if tp_price is None and tp_candidates and sl_anchor:
        nearest_tp_zone = tp_candidates[0]
        mm_target = _measured_move_target(
            current_price, sl_anchor, nearest_tp_zone, is_long
        )
        if mm_target:
            reward = abs(mm_target - current_price)
            rr = reward / risk if risk > 0 else 0
            if rr >= min_rr_ratio:
                tp_price = mm_target
                tp_method = "tp:measured_move"

    # If still nothing → percentage fallback, but still validate R/R
    if tp_price is None:
        if is_long:
            pct_tp = current_price * (1 + default_tp_pct)
        else:
            pct_tp = current_price * (1 - default_tp_pct)

        reward = abs(pct_tp - current_price)
        rr = reward / risk if risk > 0 else 0
        if rr >= min_rr_ratio:
            tp_price = pct_tp
            tp_method = "tp:pct_fallback"

    # If ALL paths failed R/R check → reject
    if tp_price is None:
        best_rr = 0
        if tp_candidates:
            best_rr = abs(tp_candidates[0] - current_price) / risk if risk > 0 else 0
        return None, None, f"R/R {best_rr:.2f}:1 < {min_rr_ratio}:1, all targets insufficient"

    method_parts.append(tp_method)

    # Final R/R for logging
    final_reward = abs(tp_price - current_price)
    final_rr = final_reward / risk if risk > 0 else 0
    method_parts.append(f"rr:{final_rr:.2f}")

    return sl_price, tp_price, "|".join(method_parts)
