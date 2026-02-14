"""
Shared Trading Logic Module

This module contains core trading logic functions that are used by both:
- deepseek_strategy.py (live trading)
- diagnose_realtime.py (diagnostic tool)

This ensures 100% consistency between diagnostic and live trading behavior.

Functions:
- calculate_position_size() - 仓位计算
- validate_multiagent_sltp() - MultiAgent SL/TP 验证
- calculate_technical_sltp() - 技术分析 SL/TP 计算
"""

import math
from typing import Dict, Any, Optional, Tuple
import logging


# =============================================================================
# CONFIGURATION LOADING (Phase 3: ConfigManager Integration)
# =============================================================================

# Module-level configuration cache (lazy-loaded to avoid circular imports)
_TRADING_LOGIC_CONFIG = None


def _get_trading_logic_config() -> Dict[str, Any]:
    """
    从 ConfigManager 加载交易逻辑配置 (lazy-loaded)

    Returns
    -------
    Dict[str, Any]
        交易逻辑配置字典，包含所有 SL/TP 参数和 Binance 交易限制

    Notes
    -----
    使用延迟导入避免循环依赖:
    - config_manager → strategy → utils (正常)
    - 不触发: trading_logic (模块级) → config_manager (循环)

    Reference: CLAUDE.md - 配置分层架构原则
    """
    global _TRADING_LOGIC_CONFIG
    if _TRADING_LOGIC_CONFIG is None:
        # Lazy import to avoid circular dependency
        from utils.config_manager import get_config
        config = get_config()

        _TRADING_LOGIC_CONFIG = {
            # SL/TP 参数
            'min_sl_distance_pct': config.get('trading_logic', 'min_sl_distance_pct', default=0.01),
            'min_tp_distance_pct': config.get('trading_logic', 'min_tp_distance_pct', default=0.005),
            'default_sl_pct': config.get('trading_logic', 'default_sl_pct', default=0.02),
            'default_tp_pct': config.get('trading_logic', 'default_tp_pct', default=0.03),
            'min_rr_ratio': config.get('trading_logic', 'min_rr_ratio', default=1.5),
            'tp_pct_by_confidence': config.get('trading_logic', 'tp_pct_by_confidence', default={
                'high': 0.03,
                'medium': 0.02,
                'low': 0.01,
            }),
            # Binance 交易限制 (从配置读取，禁止硬编码)
            'min_notional_usdt': config.get('trading_logic', 'min_notional_usdt', default=100.0),
            'min_notional_safety_margin': config.get('trading_logic', 'min_notional_safety_margin', default=1.01),
            'quantity_adjustment_step': config.get('trading_logic', 'quantity_adjustment_step', default=0.001),
        }

    return _TRADING_LOGIC_CONFIG


# Public accessor functions (used by agents/multi_agent_analyzer.py)
def get_min_sl_distance_pct() -> float:
    """获取最小止损距离百分比"""
    return _get_trading_logic_config()['min_sl_distance_pct']


def get_min_tp_distance_pct() -> float:
    """获取最小止盈距离百分比"""
    return _get_trading_logic_config()['min_tp_distance_pct']


def get_min_rr_ratio() -> float:
    """获取最小风险收益比 (R/R)"""
    return _get_trading_logic_config()['min_rr_ratio']


def get_default_sl_pct() -> float:
    """获取默认止损百分比"""
    return _get_trading_logic_config()['default_sl_pct']


def get_default_tp_pct_buy() -> float:
    """获取买入默认止盈百分比"""
    return _get_trading_logic_config()['default_tp_pct']


def get_default_tp_pct_sell() -> float:
    """获取卖出默认止盈百分比"""
    return _get_trading_logic_config()['default_tp_pct']


def get_tp_pct_by_confidence(confidence: str) -> float:
    """
    根据信心级别获取止盈百分比

    Parameters
    ----------
    confidence : str
        信心级别 ('HIGH', 'MEDIUM', 'LOW')

    Returns
    -------
    float
        对应的止盈百分比
    """
    tp_config = _get_trading_logic_config()['tp_pct_by_confidence']
    return tp_config.get(confidence.lower(), tp_config['medium'])


def get_min_notional_usdt() -> float:
    """获取 Binance 最低名义价值 (USDT)"""
    return _get_trading_logic_config()['min_notional_usdt']


def get_min_notional_safety_margin() -> float:
    """获取最低名义价值安全边际"""
    return _get_trading_logic_config()['min_notional_safety_margin']


def get_quantity_adjustment_step() -> float:
    """获取仓位调整步长"""
    return _get_trading_logic_config()['quantity_adjustment_step']


# =============================================================================
# LOGIC CONSTANTS (不可配置 - 这些是业务逻辑规则)
# =============================================================================



def calculate_position_size(
    signal_data: Dict[str, Any],
    price_data: Dict[str, Any],
    technical_data: Dict[str, Any],
    config: Dict[str, Any],
    logger: Optional[logging.Logger] = None,
    risk_multiplier: float = 1.0,
) -> Tuple[float, Dict[str, Any]]:
    """
    Calculate intelligent position size.

    v3.12: Supports multiple sizing methods:
    - fixed_pct: Original confidence-based sizing
    - atr_based: ATR-based risk-adjusted sizing
    - ai_controlled: AI specifies position_size_pct directly

    Parameters
    ----------
    signal_data : Dict
        AI-generated signal with 'confidence', 'position_size_pct' (v3.12)
    price_data : Dict
        Current price data with 'price'
    technical_data : Dict
        Technical indicators with 'overall_trend', 'rsi', 'atr' (v3.12)
    config : Dict
        Configuration with keys:
        - base_usdt: Base USDT amount
        - equity: Total equity
        - position_sizing.method: 'fixed_pct' | 'atr_based' | 'ai_controlled'
        - position_sizing.atr_based.*: ATR sizing parameters
        - max_position_ratio
        - min_trade_amount
    logger : Logger, optional
        Logger for output messages
    risk_multiplier : float, optional
        Multiplier from RiskController (0.0-1.0), default 1.0

    Returns
    -------
    Tuple[float, Dict]
        (btc_quantity, calculation_details)
    """
    current_price = price_data.get('price', 0)
    if current_price <= 0:
        if logger:
            logger.error("Invalid price for position sizing")
        return 0.0, {'error': 'Invalid price'}

    equity = config.get('equity', 1000)
    leverage = config.get('leverage', 5)
    max_position_ratio = config.get('max_position_ratio', 0.30)
    # v4.8: max_usdt 现在包含杠杆
    # 例: $1000 × 30% × 10杠杆 = $3000 最大仓位
    max_usdt = equity * max_position_ratio * leverage

    # v3.12: Determine sizing method
    sizing_config = config.get('position_sizing', {})
    method = sizing_config.get('method', 'fixed_pct')

    # v3.13: Get AI position_size_pct (used by hybrid and ai_controlled)
    ai_size_pct = signal_data.get('position_size_pct')

    # v3.12 legacy: Override to ai_controlled if AI provides size and method is not hybrid
    if ai_size_pct is not None and ai_size_pct >= 0 and method not in ('hybrid_atr_ai',):
        method = 'ai_controlled'

    if method == 'hybrid_atr_ai':
        # v3.13: Hybrid ATR-AI Position Sizing
        # 公式: 最终仓位 = ATR仓位 × AI调节系数
        # AI调节系数 = min_mult + ai_weight × (AI_pct / 100), 范围 [min, max]
        atr_config = sizing_config.get('atr_based', {})
        hybrid_config = sizing_config.get('hybrid_atr_ai', {})

        risk_per_trade = atr_config.get('risk_per_trade_pct', 0.01)
        atr_multiplier = atr_config.get('atr_multiplier', 2.0)

        min_mult = hybrid_config.get('min_multiplier', 0.3)
        max_mult = hybrid_config.get('max_multiplier', 1.0)
        ai_weight = hybrid_config.get('ai_weight', 0.7)
        fallback_to_atr = hybrid_config.get('fallback_to_atr', True)

        # Step 1: Calculate ATR-based position (risk ceiling)
        atr = technical_data.get('atr', 0)
        if atr <= 0:
            atr = current_price * 0.02  # Fallback: 2% of price
            if logger:
                logger.warning(f"ATR not available, using estimate: ${atr:.2f}")

        dollar_risk = equity * risk_per_trade
        stop_distance = atr * atr_multiplier
        stop_pct = stop_distance / current_price if current_price > 0 else 0.02

        if stop_pct > 0:
            atr_position_usdt = dollar_risk / stop_pct
        else:
            atr_position_usdt = max_usdt

        # Apply max limit to ATR position
        atr_position_usdt = min(atr_position_usdt, max_usdt)

        # Step 2: Calculate AI adjustment multiplier
        if ai_size_pct is not None and ai_size_pct >= 0:
            # AI provided a position size percentage
            ai_pct_normalized = min(ai_size_pct / 100.0, 1.0)  # Cap at 100%
            ai_multiplier = min_mult + ai_weight * ai_pct_normalized
            ai_multiplier = max(min_mult, min(ai_multiplier, max_mult))  # Clamp to range
            ai_source = 'ai_provided'
        else:
            # AI didn't provide position size
            if fallback_to_atr:
                ai_multiplier = 1.0  # Use full ATR position
                ai_source = 'fallback_atr'
            else:
                ai_multiplier = (min_mult + max_mult) / 2  # Use middle value
                ai_source = 'default_middle'

        # Step 3: Apply AI multiplier to ATR position
        position_usdt = atr_position_usdt * ai_multiplier

        # Apply risk multiplier from RiskController
        position_usdt *= risk_multiplier

        final_usdt = position_usdt

        details = {
            'method': 'hybrid_atr_ai',
            'equity': equity,
            'risk_per_trade_pct': risk_per_trade,
            'dollar_risk': dollar_risk,
            'atr': atr,
            'atr_multiplier': atr_multiplier,
            'stop_distance': stop_distance,
            'stop_pct': stop_pct * 100,
            'atr_position_usdt': atr_position_usdt,
            'ai_size_pct': ai_size_pct,
            'ai_source': ai_source,
            'ai_multiplier': ai_multiplier,
            'min_multiplier': min_mult,
            'max_multiplier': max_mult,
            'risk_multiplier': risk_multiplier,
            'max_usdt': max_usdt,
            'final_usdt': final_usdt,
        }

        if logger:
            logger.info(
                f"📊 Hybrid ATR-AI: ATR=${atr_position_usdt:.2f} × "
                f"AI_mult={ai_multiplier:.2f} ({ai_source}) = ${final_usdt:.2f}"
            )

    elif method == 'atr_based':
        # ATR-Based Position Sizing
        atr_config = sizing_config.get('atr_based', {})
        risk_per_trade = atr_config.get('risk_per_trade_pct', 0.01)
        atr_multiplier = atr_config.get('atr_multiplier', 2.0)

        # Get ATR from technical data
        atr = technical_data.get('atr', 0)
        if atr <= 0:
            # Fallback: estimate ATR as 2% of price
            atr = current_price * 0.02
            if logger:
                logger.warning(f"ATR not available, using estimate: ${atr:.2f}")

        # Calculate dollar risk
        dollar_risk = equity * risk_per_trade

        # Calculate stop distance
        stop_distance = atr * atr_multiplier

        # Position size = Risk / (Stop Distance as % of price)
        stop_pct = stop_distance / current_price
        if stop_pct > 0:
            position_usdt = dollar_risk / stop_pct
        else:
            position_usdt = max_usdt

        # Apply risk multiplier from RiskController
        position_usdt *= risk_multiplier

        # Apply max limit
        final_usdt = min(position_usdt, max_usdt)

        details = {
            'method': 'atr_based',
            'equity': equity,
            'risk_per_trade_pct': risk_per_trade,
            'dollar_risk': dollar_risk,
            'atr': atr,
            'atr_multiplier': atr_multiplier,
            'stop_distance': stop_distance,
            'stop_pct': stop_pct * 100,
            'risk_multiplier': risk_multiplier,
            'position_usdt': position_usdt,
            'max_usdt': max_usdt,
            'final_usdt': final_usdt,
        }

    elif method == 'ai_controlled':
        # v4.8: AI 控制仓位计算
        # 公式: 最终仓位 = max_usdt × AI建议百分比
        # max_usdt = equity × max_position_ratio × leverage (已在上面计算)

        ai_config = sizing_config.get('ai_controlled', {})
        default_size_pct = ai_config.get('default_size_pct', 50)
        confidence_mapping = ai_config.get('confidence_mapping', {
            'HIGH': 80,
            'MEDIUM': 50,
            'LOW': 30
        })

        # 确定仓位百分比 (优先级: AI 输出 > 信心映射 > 默认值)
        if ai_size_pct is not None and ai_size_pct >= 0:
            # AI 直接提供了仓位百分比
            size_pct = float(ai_size_pct)
            size_source = 'ai_provided'
        else:
            # 根据信心等级映射
            confidence = signal_data.get('confidence', 'MEDIUM').upper()
            size_pct = confidence_mapping.get(confidence, default_size_pct)
            size_source = f'confidence_{confidence}'

        # 转换为小数并计算仓位
        size_ratio = size_pct / 100.0  # Convert 0-100 to 0-1
        position_usdt = max_usdt * size_ratio

        # Apply risk multiplier
        position_usdt *= risk_multiplier

        final_usdt = position_usdt

        details = {
            'method': 'ai_controlled',
            'ai_size_pct': ai_size_pct,
            'size_pct_used': size_pct,
            'size_source': size_source,
            'confidence': signal_data.get('confidence', 'MEDIUM'),
            'equity': equity,
            'leverage': leverage,
            'max_position_ratio': max_position_ratio,
            'max_usdt': max_usdt,
            'risk_multiplier': risk_multiplier,
            'final_usdt': final_usdt,
        }

        if logger:
            logger.info(
                f"📊 AI-controlled sizing: {size_pct}% of ${max_usdt:.0f} "
                f"(equity=${equity} × {max_position_ratio*100:.0f}% × {leverage}x) "
                f"({size_source}) = ${final_usdt:.2f}"
            )

    else:
        # Original fixed_pct method (legacy)
        base_usdt = config.get('base_usdt', 100)

        # Confidence multiplier
        confidence = signal_data.get('confidence', 'MEDIUM').lower()
        conf_mult = config.get(f'{confidence}_confidence_multiplier', 1.0)

        # Trend multiplier
        trend = technical_data.get('overall_trend', '震荡整理')
        trend_mult = (
            config.get('trend_strength_multiplier', 1.2)
            if trend in ['强势上涨', '强势下跌']
            else 1.0
        )

        # RSI multiplier (reduce size in extreme RSI)
        rsi = technical_data.get('rsi', 50)
        rsi_extreme_upper = config.get('rsi_extreme_upper', 70)
        rsi_extreme_lower = config.get('rsi_extreme_lower', 30)
        rsi_mult = (
            config.get('rsi_extreme_multiplier', 0.7)
            if rsi > rsi_extreme_upper or rsi < rsi_extreme_lower
            else 1.0
        )

        # Calculate suggested USDT
        suggested_usdt = base_usdt * conf_mult * trend_mult * rsi_mult

        # Apply risk multiplier
        suggested_usdt *= risk_multiplier

        # Apply max position ratio limit
        final_usdt = min(suggested_usdt, max_usdt)

        details = {
            'method': 'fixed_pct',
            'base_usdt': base_usdt,
            'conf_mult': conf_mult,
            'trend_mult': trend_mult,
            'trend': trend,
            'rsi_mult': rsi_mult,
            'rsi': rsi,
            'risk_multiplier': risk_multiplier,
            'suggested_usdt': suggested_usdt,
            'max_usdt': max_usdt,
            'final_usdt': final_usdt,
        }

    # Get Binance limits from config (禁止硬编码 - Reference: CLAUDE.md)
    min_notional_usdt = get_min_notional_usdt()
    min_notional_safety_margin = get_min_notional_safety_margin()
    quantity_step = get_quantity_adjustment_step()

    # Enforce Binance minimum notional requirement
    if final_usdt < min_notional_usdt:
        final_usdt = min_notional_usdt
        details['final_usdt'] = final_usdt

    # Convert to BTC quantity
    btc_quantity = final_usdt / current_price

    # Apply minimum trade amount
    min_trade = config.get('min_trade_amount', 0.001)
    if btc_quantity < min_trade:
        btc_quantity = min_trade

    # Round to instrument precision
    btc_quantity = round(btc_quantity, 3)  # Binance BTC precision

    # CRITICAL: Re-check notional after rounding
    min_notional_with_margin = min_notional_usdt * min_notional_safety_margin

    actual_notional = btc_quantity * current_price
    adjusted = False
    if actual_notional < min_notional_with_margin:
        # Increase quantity to meet minimum notional with safety margin (round UP)
        btc_quantity = min_notional_with_margin / current_price
        # Round up to next step
        btc_quantity = math.ceil(btc_quantity / quantity_step) * quantity_step
        # Final verification
        final_notional = btc_quantity * current_price
        if final_notional < min_notional_usdt:
            btc_quantity += quantity_step
        adjusted = True
        if logger:
            logger.warning(
                f"⚠️ Adjusted quantity after rounding: {btc_quantity:.3f} BTC "
                f"to meet ${min_notional_usdt} minimum notional"
            )

    # Calculate final notional
    notional = btc_quantity * current_price

    # Update details with final values
    details['btc_quantity'] = btc_quantity
    details['notional'] = notional
    details['adjusted'] = adjusted

    # Log calculation details
    if logger:
        method_name = details.get('method', 'unknown')
        logger.info(
            f"📊 Position Sizing ({method_name}): "
            f"${final_usdt:.2f} = {btc_quantity:.3f} BTC "
            f"(notional: ${notional:.2f}, risk_mult: {risk_multiplier:.1f})"
        )

    return btc_quantity, details


# =============================================================================
# SL/TP VALIDATION FUNCTIONS (v9.0)
# Used by both deepseek_strategy.py and diagnose_realtime.py
# =============================================================================

# =============================================================================
# SL/TP CONFIGURATION (Phase 3: Migrated to ConfigManager)
# =============================================================================
# 这些值已迁移到 configs/base.yaml 的 trading_logic 节
#
# BREAKING CHANGE (Phase 3):
# - 旧代码使用: MIN_SL_DISTANCE_PCT (常量)
# - 新代码使用: get_min_sl_distance_pct() (函数)
#
# 为了避免循环导入，这些值不能在模块级别初始化
# 必须使用函数形式访问
# =============================================================================

# NOTE: 这些注释保留用于文档目的，实际值从配置加载
# MIN_SL_DISTANCE_PCT = 0.01   # 1% minimum SL distance (avoid too tight stops)
# MIN_TP_DISTANCE_PCT = 0.005  # 0.5% minimum TP distance
# DEFAULT_SL_PCT = 0.02        # 2% default stop loss distance
# DEFAULT_TP_PCT_BUY = 0.03    # 3% take profit for BUY (above entry)
# DEFAULT_TP_PCT_SELL = 0.03   # 3% take profit for SELL (below entry)
# TP_PCT_CONFIG = {'HIGH': 0.03, 'MEDIUM': 0.02, 'LOW': 0.01}

# 实际值通过以下函数访问:
# - get_min_sl_distance_pct()
# - get_min_tp_distance_pct()
# - get_default_sl_pct()
# - get_default_tp_pct_buy()
# - get_default_tp_pct_sell()
# - get_tp_pct_by_confidence(confidence)


def validate_multiagent_sltp(
    side: str,
    multi_sl: Optional[float],
    multi_tp: Optional[float],
    entry_price: float,
) -> Tuple[bool, Optional[float], Optional[float], str]:
    """
    Validate MultiAgent SL/TP values.

    This function validates that SL/TP values from MultiAgent are correct:
    - BUY/LONG: SL must be below entry, TP must be above entry
    - SELL/SHORT: SL must be above entry, TP must be below entry
    - Both must have minimum distance from entry
    - R/R ratio must meet minimum threshold (default 1.5:1)

    Parameters
    ----------
    side : str
        Trade side ('BUY', 'SELL', 'LONG', or 'SHORT')
    multi_sl : float, optional
        Stop loss price from MultiAgent
    multi_tp : float, optional
        Take profit price from MultiAgent
    entry_price : float
        Entry price

    Returns
    -------
    Tuple[bool, Optional[float], Optional[float], str]
        (is_valid, final_sl, final_tp, reason)
    """
    if not multi_sl or not multi_tp or multi_sl <= 0 or multi_tp <= 0:
        return False, None, None, "MultiAgent SL/TP not provided or invalid"

    sl_distance = abs(multi_sl - entry_price) / entry_price
    tp_distance = abs(multi_tp - entry_price) / entry_price

    # v3.12: Support both legacy (BUY/SELL) and new (LONG/SHORT) formats
    is_long = side.upper() in ('BUY', 'LONG')

    # v3.15: Enforce minimum SL distance (reverts v3.13 "trust AI" approach)
    # Problem: AI can return SL too close to entry (e.g., 0.09%), causing immediate stop-outs
    # Solution: Reject AI SL/TP if distance < min threshold, force fallback to S/R-based calculation
    min_sl = get_min_sl_distance_pct()
    min_tp = get_min_tp_distance_pct()

    # Hard rejection for SL too close (this is the key fix)
    if sl_distance < min_sl:
        return False, None, None, (
            f"SL too close to entry ({sl_distance*100:.2f}% < {min_sl*100}% minimum). "
            f"Will use S/R-based technical analysis instead."
        )

    if is_long:
        # BUY: SL must be < entry, TP must be > entry
        if multi_sl >= entry_price:
            return False, None, None, f"BUY SL (${multi_sl:,.2f}) must be < entry (${entry_price:,.2f})"
        if multi_tp <= entry_price:
            return False, None, None, f"BUY TP (${multi_tp:,.2f}) must be > entry (${entry_price:,.2f})"

        # R/R hard gate: reject if risk/reward ratio below minimum
        risk = entry_price - multi_sl
        reward = multi_tp - entry_price
        if risk > 0:
            rr_ratio = reward / risk
            min_rr = get_min_rr_ratio()
            if rr_ratio < min_rr:
                return False, None, None, (
                    f"R/R {rr_ratio:.2f}:1 < {min_rr}:1 minimum "
                    f"(SL ${multi_sl:,.2f}, TP ${multi_tp:,.2f}). "
                    f"Will use S/R-based technical analysis instead."
                )

        if tp_distance < min_tp:
            return True, multi_sl, multi_tp, f"Valid with note: TP close to entry ({tp_distance*100:.2f}%)"
        return True, multi_sl, multi_tp, f"Valid (SL: {sl_distance*100:.2f}%, TP: {tp_distance*100:.2f}%)"

    else:  # SELL
        # SELL: SL must be > entry, TP must be < entry
        if multi_sl <= entry_price:
            return False, None, None, f"SELL SL (${multi_sl:,.2f}) must be > entry (${entry_price:,.2f})"
        if multi_tp >= entry_price:
            return False, None, None, f"SELL TP (${multi_tp:,.2f}) must be < entry (${entry_price:,.2f})"

        # R/R hard gate: reject if risk/reward ratio below minimum
        risk = multi_sl - entry_price
        reward = entry_price - multi_tp
        if risk > 0:
            rr_ratio = reward / risk
            min_rr = get_min_rr_ratio()
            if rr_ratio < min_rr:
                return False, None, None, (
                    f"R/R {rr_ratio:.2f}:1 < {min_rr}:1 minimum "
                    f"(SL ${multi_sl:,.2f}, TP ${multi_tp:,.2f}). "
                    f"Will use S/R-based technical analysis instead."
                )

        if tp_distance < min_tp:
            return True, multi_sl, multi_tp, f"Valid with note: TP close to entry ({tp_distance*100:.2f}%)"
        return True, multi_sl, multi_tp, f"Valid (SL: {sl_distance*100:.2f}%, TP: {tp_distance*100:.2f}%)"


def calculate_technical_sltp(
    side: str,
    entry_price: float,
    support: float,
    resistance: float,
    confidence: str,
    use_support_resistance: bool = True,
    sl_buffer_pct: float = 0.005,  # 0.5% buffer to confirm real S/R breakout
    tp_buffer_pct: float = 0.005,  # 0.5% buffer before S/R for TP
    min_rr_ratio: float = 1.5,
) -> Tuple[float, float, str]:
    """
    Calculate SL/TP based on simple min/max support/resistance.

    .. deprecated:: v5.0
        **DIAGNOSTIC ONLY** — Not used in production trading.
        Production code uses ``calculate_sr_based_sltp()`` from
        ``utils/sr_sltp_calculator.py``, which uses full SRZone objects
        with strength, touch_count, source_type, and ATR buffer.

        This function uses naive float support/resistance (min low / max high
        from TechnicalIndicatorManager's 20-bar lookback) and provides a
        percentage-based fallback — both of which are inferior to zone-based
        calculation.

        **Callers**: diagnostic scripts only
        (``scripts/diagnostics/*.py``, ``scripts/diagnose_*.py``)

    v3.14 Changes:
    - TP now uses S/R zones instead of fixed percentage
    - LONG: TP targets resistance level (with buffer before it)
    - SHORT: TP targets support level (with buffer before it)
    - R/R validation: if R/R < min_rr_ratio, adjusts TP to meet requirement

    Parameters
    ----------
    side : str
        Trade side ('BUY', 'SELL', 'LONG', or 'SHORT')
    entry_price : float
        Entry price
    support : float
        Support level price (nearest support zone center)
    resistance : float
        Resistance level price (nearest resistance zone center)
    confidence : str
        Signal confidence ('HIGH', 'MEDIUM', 'LOW')
    use_support_resistance : bool
        Whether to use support/resistance levels
    sl_buffer_pct : float
        Buffer percentage beyond S/R for SL (default 0.1%)
    tp_buffer_pct : float
        Buffer percentage before S/R for TP (default 0.1%)
    min_rr_ratio : float
        Minimum required Risk/Reward ratio (default 1.5)

    Returns
    -------
    Tuple[float, float, str]
        (stop_loss_price, take_profit_price, calculation_method)
    """
    PRICE_EPSILON = max(entry_price * 1e-8, 1e-8)

    # v3.12: Support both legacy (BUY/SELL) and new (LONG/SHORT) formats
    is_long = side.upper() in ('BUY', 'LONG')

    # Get default TP percentage for fallback
    tp_pct = get_tp_pct_by_confidence(confidence)
    default_sl_pct = get_default_sl_pct()

    method_parts = []

    if is_long:
        # =====================================================
        # LONG: SL below support, TP at resistance
        # =====================================================

        # --- Stop Loss ---
        default_sl = entry_price * (1 - default_sl_pct)

        if use_support_resistance and support > 0:
            potential_sl = support * (1 - sl_buffer_pct)
            if potential_sl < entry_price - PRICE_EPSILON:
                stop_loss_price = potential_sl
                method_parts.append(f"SL: Support-based (${support:,.0f} - {sl_buffer_pct*100:.1f}% buffer)")
            else:
                stop_loss_price = default_sl
                method_parts.append(f"SL: Default {default_sl_pct*100:.0f}% (support too close)")
        else:
            stop_loss_price = default_sl
            method_parts.append(f"SL: Default {default_sl_pct*100:.0f}%")

        # --- Take Profit ---
        default_tp = entry_price * (1 + tp_pct)

        if use_support_resistance and resistance > 0:
            # TP at resistance minus buffer (take profit slightly before resistance)
            potential_tp = resistance * (1 - tp_buffer_pct)
            if potential_tp > entry_price + PRICE_EPSILON:
                take_profit_price = potential_tp
                method_parts.append(f"TP: Resistance-based (${resistance:,.0f} - {tp_buffer_pct*100:.1f}% buffer)")
            else:
                take_profit_price = default_tp
                method_parts.append(f"TP: Default {tp_pct*100:.0f}% (resistance too close)")
        else:
            take_profit_price = default_tp
            method_parts.append(f"TP: Default {tp_pct*100:.0f}%")

        # --- R/R Validation ---
        sl_distance = entry_price - stop_loss_price
        tp_distance = take_profit_price - entry_price

        if sl_distance > 0:
            rr_ratio = tp_distance / sl_distance
            if rr_ratio < min_rr_ratio:
                # Adjust TP to meet minimum R/R ratio
                adjusted_tp = entry_price + (sl_distance * min_rr_ratio)
                if adjusted_tp > take_profit_price:
                    take_profit_price = adjusted_tp
                    method_parts.append(f"TP adjusted for R/R >= {min_rr_ratio}:1")

    else:
        # =====================================================
        # SHORT: SL above resistance, TP at support
        # =====================================================

        # --- Stop Loss ---
        default_sl = entry_price * (1 + default_sl_pct)

        if use_support_resistance and resistance > 0:
            potential_sl = resistance * (1 + sl_buffer_pct)
            if potential_sl > entry_price + PRICE_EPSILON:
                stop_loss_price = potential_sl
                method_parts.append(f"SL: Resistance-based (${resistance:,.0f} + {sl_buffer_pct*100:.1f}% buffer)")
            else:
                stop_loss_price = default_sl
                method_parts.append(f"SL: Default {default_sl_pct*100:.0f}% (resistance too close)")
        else:
            stop_loss_price = default_sl
            method_parts.append(f"SL: Default {default_sl_pct*100:.0f}%")

        # --- Take Profit ---
        default_tp = entry_price * (1 - tp_pct)

        if use_support_resistance and support > 0:
            # TP at support plus buffer (take profit slightly before support)
            potential_tp = support * (1 + tp_buffer_pct)
            if potential_tp < entry_price - PRICE_EPSILON:
                take_profit_price = potential_tp
                method_parts.append(f"TP: Support-based (${support:,.0f} + {tp_buffer_pct*100:.1f}% buffer)")
            else:
                take_profit_price = default_tp
                method_parts.append(f"TP: Default {tp_pct*100:.0f}% (support too close)")
        else:
            take_profit_price = default_tp
            method_parts.append(f"TP: Default {tp_pct*100:.0f}%")

        # --- R/R Validation ---
        sl_distance = stop_loss_price - entry_price
        tp_distance = entry_price - take_profit_price

        if sl_distance > 0:
            rr_ratio = tp_distance / sl_distance
            if rr_ratio < min_rr_ratio:
                # Adjust TP to meet minimum R/R ratio
                adjusted_tp = entry_price - (sl_distance * min_rr_ratio)
                if adjusted_tp < take_profit_price:
                    take_profit_price = adjusted_tp
                    method_parts.append(f"TP adjusted for R/R >= {min_rr_ratio}:1")

    method = " | ".join(method_parts)
    return stop_loss_price, take_profit_price, method


# =============================================================================
# TRADE EVALUATION (v5.1: Trading Evaluation Standards)
# Integrated with decision_memory for AI learning
# =============================================================================

# Grade thresholds (business logic constants, not configurable)
GRADE_THRESHOLDS = {
    'A+': 2.5,   # actual R/R >= 2.5 (exceptional trade)
    'A':  1.5,   # actual R/R >= 1.5 (strong win)
    'B':  1.0,   # actual R/R >= 1.0 (acceptable profit)
    'C':  0.0,   # pnl > 0 but R/R < 1.0 (small profit, poor R/R)
    'D':  None,   # loss within planned SL (controlled loss)
    'F':  None,   # loss exceeded planned SL (uncontrolled)
}


def evaluate_trade(
    entry_price: float,
    exit_price: float,
    planned_sl: Optional[float],
    planned_tp: Optional[float],
    direction: str,
    pnl_pct: float,
    confidence: str = "MEDIUM",
    position_size_pct: float = 0.0,
    entry_timestamp: Optional[str] = None,
    exit_timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluate trade quality and assign a grade.

    Integrated with decision_memory - the returned dict is stored as the
    'evaluation' field in each memory entry.

    Grading System:
        A+ : Actual R/R >= 2.5 (exceptional)
        A  : Actual R/R >= 1.5 (strong win)
        B  : Actual R/R >= 1.0 (acceptable profit)
        C  : Profit but R/R < 1.0 (small profit)
        D  : Loss within planned SL (controlled loss - discipline maintained)
        F  : Loss exceeded planned SL by > 20% (uncontrolled)

    Parameters
    ----------
    entry_price : float
        Actual entry price
    exit_price : float
        Actual exit price
    planned_sl : float, optional
        Planned stop loss price at entry
    planned_tp : float, optional
        Planned take profit price at entry
    direction : str
        Trade direction ('LONG' or 'SHORT')
    pnl_pct : float
        Realized P&L percentage
    confidence : str
        Signal confidence level ('HIGH', 'MEDIUM', 'LOW')
    position_size_pct : float
        Position size percentage used
    entry_timestamp : str, optional
        ISO format entry timestamp
    exit_timestamp : str, optional
        ISO format exit timestamp

    Returns
    -------
    Dict[str, Any]
        Evaluation data dict to be stored in decision_memory
    """
    is_long = direction.upper() in ('LONG', 'BUY')

    # --- Determine exit type ---
    exit_type = _classify_exit_type(
        exit_price, planned_sl, planned_tp, entry_price, is_long,
    )

    # --- Calculate actual R/R ---
    actual_rr = 0.0
    planned_rr = 0.0
    direction_correct = pnl_pct > 0

    if entry_price > 0 and planned_sl and planned_sl > 0:
        risk = abs(entry_price - planned_sl)
        if risk > 0:
            if is_long:
                actual_reward = exit_price - entry_price
            else:
                actual_reward = entry_price - exit_price
            actual_rr = round(actual_reward / risk, 2)

            # Planned R/R
            if planned_tp and planned_tp > 0:
                planned_reward = abs(planned_tp - entry_price)
                planned_rr = round(planned_reward / risk, 2)

    # --- Execution quality (how well did actual match plan) ---
    execution_quality = 0.0
    if planned_rr > 0:
        execution_quality = round(min(actual_rr / planned_rr, 2.0), 2)

    # --- Assign grade ---
    grade = _assign_grade(pnl_pct, actual_rr, exit_type, planned_sl, exit_price, entry_price, is_long)

    # --- Hold duration ---
    hold_duration_min = _calc_hold_duration(entry_timestamp, exit_timestamp)

    return {
        'grade': grade,
        'direction_correct': direction_correct,
        'entry_price': round(entry_price, 2),
        'exit_price': round(exit_price, 2),
        'planned_sl': round(planned_sl, 2) if planned_sl else None,
        'planned_tp': round(planned_tp, 2) if planned_tp else None,
        'planned_rr': planned_rr,
        'actual_rr': actual_rr,
        'execution_quality': execution_quality,
        'exit_type': exit_type,
        'confidence': confidence.upper(),
        'position_size_pct': position_size_pct,
        'hold_duration_min': hold_duration_min,
    }


def _classify_exit_type(
    exit_price: float,
    planned_sl: Optional[float],
    planned_tp: Optional[float],
    entry_price: float,
    is_long: bool,
) -> str:
    """
    Classify how the trade was closed.

    Returns: 'TAKE_PROFIT', 'STOP_LOSS', 'MANUAL', or 'REVERSAL'
    """
    if not planned_sl or not planned_tp or entry_price <= 0:
        return 'MANUAL'

    tolerance = entry_price * 0.003  # 0.3% tolerance for SL/TP matching

    if is_long:
        if exit_price <= planned_sl + tolerance and exit_price < entry_price:
            return 'STOP_LOSS'
        if exit_price >= planned_tp - tolerance and exit_price > entry_price:
            return 'TAKE_PROFIT'
    else:
        if exit_price >= planned_sl - tolerance and exit_price > entry_price:
            return 'STOP_LOSS'
        if exit_price <= planned_tp + tolerance and exit_price < entry_price:
            return 'TAKE_PROFIT'

    return 'MANUAL'


def _assign_grade(
    pnl_pct: float,
    actual_rr: float,
    exit_type: str,
    planned_sl: Optional[float],
    exit_price: float,
    entry_price: float,
    is_long: bool,
) -> str:
    """
    Assign A+/A/B/C/D/F grade based on trade outcome.

    Profitable trades graded by actual R/R achieved.
    Losing trades graded by discipline (did SL work?).
    """
    if pnl_pct > 0:
        # Profitable - grade by R/R achievement
        if actual_rr >= 2.5:
            return 'A+'
        elif actual_rr >= 1.5:
            return 'A'
        elif actual_rr >= 1.0:
            return 'B'
        else:
            return 'C'
    else:
        # Loss - grade by discipline
        if not planned_sl or planned_sl <= 0:
            return 'F'  # No SL plan = undisciplined

        # Check if loss was within planned SL (with 20% tolerance)
        planned_loss_pct = abs(entry_price - planned_sl) / entry_price
        actual_loss_pct = abs(pnl_pct) / 100.0

        # D = loss within SL (controlled), F = exceeded SL significantly
        if actual_loss_pct <= planned_loss_pct * 1.2:
            return 'D'
        else:
            return 'F'


def _calc_hold_duration(
    entry_ts: Optional[str],
    exit_ts: Optional[str],
) -> int:
    """Calculate hold duration in minutes from ISO timestamps."""
    if not entry_ts or not exit_ts:
        return 0
    try:
        from datetime import datetime
        # Handle both with and without microseconds
        for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
            try:
                entry_dt = datetime.fromisoformat(entry_ts.replace('Z', ''))
                exit_dt = datetime.fromisoformat(exit_ts.replace('Z', ''))
                delta = exit_dt - entry_dt
                return max(0, int(delta.total_seconds() / 60))
            except ValueError:
                continue
    except Exception:
        pass
    return 0


def get_evaluation_summary(memories: list) -> Dict[str, Any]:
    """
    Compute aggregate evaluation statistics from decision_memory.

    Used by daily/weekly summaries and Telegram reports.

    Parameters
    ----------
    memories : list
        List of decision_memory entries (each may have 'evaluation' field)

    Returns
    -------
    Dict[str, Any]
        Aggregate stats: grade distribution, avg R/R, direction accuracy, etc.
    """
    evaluated = [m for m in memories if m.get('evaluation')]
    if not evaluated:
        return {}

    evals = [m['evaluation'] for m in evaluated]
    total = len(evals)

    # Grade distribution
    grade_counts = {}
    for e in evals:
        g = e.get('grade', '?')
        grade_counts[g] = grade_counts.get(g, 0) + 1

    # Direction accuracy
    correct = sum(1 for e in evals if e.get('direction_correct'))
    direction_accuracy = round(correct / total * 100, 1) if total > 0 else 0.0

    # Average actual R/R (only for profitable trades)
    profitable_rrs = [e.get('actual_rr', 0) for e in evals if e.get('direction_correct')]
    avg_winning_rr = round(sum(profitable_rrs) / len(profitable_rrs), 2) if profitable_rrs else 0.0

    # Average execution quality
    exec_quals = [e.get('execution_quality', 0) for e in evals if e.get('execution_quality', 0) > 0]
    avg_exec_quality = round(sum(exec_quals) / len(exec_quals), 2) if exec_quals else 0.0

    # Exit type distribution
    exit_types = {}
    for e in evals:
        et = e.get('exit_type', 'UNKNOWN')
        exit_types[et] = exit_types.get(et, 0) + 1

    # Confidence accuracy (does HIGH confidence actually win more?)
    confidence_stats = {}
    for e in evals:
        conf = e.get('confidence', 'MEDIUM')
        if conf not in confidence_stats:
            confidence_stats[conf] = {'total': 0, 'wins': 0}
        confidence_stats[conf]['total'] += 1
        if e.get('direction_correct'):
            confidence_stats[conf]['wins'] += 1

    for conf, stats in confidence_stats.items():
        stats['accuracy'] = round(stats['wins'] / stats['total'] * 100, 1) if stats['total'] > 0 else 0.0

    # Average hold duration
    durations = [e.get('hold_duration_min', 0) for e in evals if e.get('hold_duration_min', 0) > 0]
    avg_hold_min = round(sum(durations) / len(durations)) if durations else 0

    return {
        'total_evaluated': total,
        'grade_distribution': grade_counts,
        'direction_accuracy': direction_accuracy,
        'avg_winning_rr': avg_winning_rr,
        'avg_execution_quality': avg_exec_quality,
        'exit_type_distribution': exit_types,
        'confidence_accuracy': confidence_stats,
        'avg_hold_duration_min': avg_hold_min,
    }


