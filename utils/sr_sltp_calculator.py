"""
v4.0: S/R-Based SL/TP Calculator

Calculates stop loss and take profit prices using S/R zones as anchor points.
Three-level fallback: AI SL/TP → S/R-based → percentage-based.

This module provides the unified SL/TP calculation function used by both:
1. Entry flow (_validate_sltp_for_entry)
2. Dynamic reevaluation (_reevaluate_sltp_for_existing_position)
"""

import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)


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

    For LONG: SL below nearest support zone, TP at nearest resistance zone.
    For SHORT: SL above nearest resistance zone, TP at nearest support zone.

    Fallback chain:
    1. S/R zone + ATR buffer → R/R validation
    2. If no suitable S/R zones → percentage-based fallback

    Parameters
    ----------
    current_price : float
        Current market price (or entry price for new positions).
    side : str
        "BUY" for long, "SELL" for short.
    sr_zones : Dict
        S/R zone data from SRZoneCalculator.calculate().
        Must contain 'nearest_support' and 'nearest_resistance' keys.
    atr_value : float
        Current ATR value for buffer calculation. 0 = use percentage fallback.
    min_rr_ratio : float
        Minimum Risk/Reward ratio required. Default 1.5.
    atr_buffer_multiplier : float
        ATR multiplier for SL buffer behind S/R zone. Default 0.5.
    default_sl_pct : float
        Fallback SL percentage if no S/R zones. Default 2%.
    default_tp_pct : float
        Fallback TP percentage if no S/R zones. Default 3%.

    Returns
    -------
    Tuple[Optional[float], Optional[float], str]
        (sl_price, tp_price, method_description)
        Returns (None, None, reason) if R/R requirement cannot be met.
    """
    if current_price <= 0:
        return None, None, "invalid current price"

    is_long = side.upper() in ('BUY', 'LONG')

    # Extract nearest S/R zones
    nearest_support = sr_zones.get('nearest_support')
    nearest_resistance = sr_zones.get('nearest_resistance')

    support_price = None
    resistance_price = None

    if nearest_support:
        support_price = nearest_support.price_center if hasattr(nearest_support, 'price_center') else nearest_support.get('price_center')
    if nearest_resistance:
        resistance_price = nearest_resistance.price_center if hasattr(nearest_resistance, 'price_center') else nearest_resistance.get('price_center')

    # Calculate ATR buffer (or fallback to percentage)
    if atr_value > 0:
        buffer = atr_value * atr_buffer_multiplier
    else:
        buffer = current_price * 0.005  # 0.5% fallback

    sl_price = None
    tp_price = None
    method = "sr_based"

    if is_long:
        # SL: below nearest support - buffer
        if support_price and support_price > 0 and support_price < current_price:
            sl_price = support_price - buffer
        else:
            sl_price = current_price * (1 - default_sl_pct)
            method = "percentage_fallback"

        # TP: at nearest resistance - small buffer (to exit before hitting resistance)
        if resistance_price and resistance_price > 0 and resistance_price > current_price:
            tp_price = resistance_price - buffer * 0.5  # Smaller buffer for TP
        else:
            tp_price = current_price * (1 + default_tp_pct)
            if method != "percentage_fallback":
                method = "sr_based_partial"
    else:
        # SHORT
        # SL: above nearest resistance + buffer
        if resistance_price and resistance_price > 0 and resistance_price > current_price:
            sl_price = resistance_price + buffer
        else:
            sl_price = current_price * (1 + default_sl_pct)
            method = "percentage_fallback"

        # TP: at nearest support + small buffer
        if support_price and support_price > 0 and support_price < current_price:
            tp_price = support_price + buffer * 0.5
        else:
            tp_price = current_price * (1 - default_tp_pct)
            if method != "percentage_fallback":
                method = "sr_based_partial"

    # Validate R/R ratio
    if sl_price and tp_price:
        if is_long:
            risk = current_price - sl_price
            reward = tp_price - current_price
        else:
            risk = sl_price - current_price
            reward = current_price - tp_price

        if risk <= 0:
            return None, None, "SL on wrong side of price"

        rr_ratio = reward / risk if risk > 0 else 0

        if rr_ratio < min_rr_ratio:
            # Try to adjust TP to meet R/R requirement
            required_reward = risk * min_rr_ratio
            if is_long:
                tp_price = current_price + required_reward
            else:
                tp_price = current_price - required_reward
            method += f"_rr_adjusted({rr_ratio:.1f}→{min_rr_ratio})"

    return sl_price, tp_price, method
