"""
Shared Trading Logic Module

This module contains core trading logic functions that are used by both:
- deepseek_strategy.py (live trading)
- diagnose_realtime.py (diagnostic tool)

This ensures 100% consistency between diagnostic and live trading behavior.

当前使用的函数 (v9.0):
- check_confidence_threshold() - 信心阈值检查
- calculate_position_size() - 仓位计算
- validate_multiagent_sltp() - MultiAgent SL/TP 验证 (v9.0 新增)
- calculate_technical_sltp() - 技术分析 SL/TP 计算 (v9.0 新增)

以下函数已被标记为 LEGACY (不再使用):
- process_signals() - 层级架构使用Judge决策，无需信号合并
- check_divergence() - 层级架构不存在信号分歧
- resolve_divergence_by_confidence() - 层级架构不存在信号分歧
- create_hold_signal() - 可选保留
"""

import math
from typing import Dict, Any, Optional, Tuple
import logging


# Confidence weight mapping (used across all functions)
CONFIDENCE_WEIGHT = {
    'HIGH': 3,
    'MEDIUM': 2,
    'LOW': 1,
}

CONFIDENCE_LEVELS = {
    'LOW': 0,
    'MEDIUM': 1,
    'HIGH': 2,
}

VALID_CONFIDENCES = {'HIGH', 'MEDIUM', 'LOW'}


# =============================================================================
# LEGACY FUNCTIONS - 不再使用，保留用于向后兼容
# =============================================================================


def check_divergence(
    signal_deepseek: str,
    signal_multi: str,
) -> Tuple[bool, bool, bool]:
    """
    Check if two signals are divergent.

    Parameters
    ----------
    signal_deepseek : str
        DeepSeek signal ('BUY', 'SELL', 'HOLD')
    signal_multi : str
        MultiAgent signal ('BUY', 'SELL', 'HOLD')

    Returns
    -------
    Tuple[bool, bool, bool]
        (is_consensus, is_opposing, is_hold_vs_action)
        - is_consensus: True if signals match
        - is_opposing: True if BUY vs SELL
        - is_hold_vs_action: True if HOLD vs BUY/SELL
    """
    # Check for consensus
    if signal_deepseek == signal_multi:
        return True, False, False

    # Check for opposing signals (BUY vs SELL)
    opposing_signals = {signal_deepseek, signal_multi} == {'BUY', 'SELL'}

    # Check for HOLD vs actionable signal (HOLD vs BUY or HOLD vs SELL)
    hold_vs_action = (
        (signal_deepseek == 'HOLD' and signal_multi in ['BUY', 'SELL']) or
        (signal_multi == 'HOLD' and signal_deepseek in ['BUY', 'SELL'])
    )

    return False, opposing_signals, hold_vs_action


def resolve_divergence_by_confidence(
    signal_deepseek: Dict[str, Any],
    signal_multi: Dict[str, Any],
    logger: Optional[logging.Logger] = None,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Resolve opposing signals using weighted confidence fusion.

    Based on industry best practices from QuantAgent and TradingAgents frameworks:
    - Use the signal with higher confidence
    - Only skip when confidence levels are equal

    Parameters
    ----------
    signal_deepseek : Dict
        DeepSeek AI signal with 'signal' and 'confidence'
    signal_multi : Dict
        MultiAgent signal with 'signal' and 'confidence'
    logger : Logger, optional
        Logger for output messages

    Returns
    -------
    Tuple[Optional[Dict], str]
        (resolved_signal, log_message)
        - resolved_signal: Dict with the winning signal, or None if equal confidence
        - log_message: Description of what happened
    """
    # Parameter validation - check for None signals
    if signal_deepseek is None or signal_multi is None:
        msg = (
            f"❌ Confidence fusion failed: signal is None "
            f"(deepseek={signal_deepseek is not None}, multi={signal_multi is not None})"
        )
        if logger:
            logger.error(msg)
        return None, msg

    # Check for required 'signal' key
    if 'signal' not in signal_deepseek:
        msg = "❌ Confidence fusion failed: DeepSeek signal missing 'signal' key"
        if logger:
            logger.error(msg)
        return None, msg
    if 'signal' not in signal_multi:
        msg = "❌ Confidence fusion failed: MultiAgent signal missing 'signal' key"
        if logger:
            logger.error(msg)
        return None, msg

    ds_signal = signal_deepseek['signal']
    ds_conf = signal_deepseek.get('confidence', 'MEDIUM')
    ma_signal = signal_multi['signal']
    ma_conf = signal_multi.get('confidence', 'MEDIUM')

    # Validate and fix invalid confidence values
    if ds_conf not in VALID_CONFIDENCES:
        msg = f"⚠️ Invalid DeepSeek confidence '{ds_conf}', using MEDIUM as default"
        if logger:
            logger.warning(msg)
        ds_conf = 'MEDIUM'
    if ma_conf not in VALID_CONFIDENCES:
        msg = f"⚠️ Invalid MultiAgent confidence '{ma_conf}', using MEDIUM as default"
        if logger:
            logger.warning(msg)
        ma_conf = 'MEDIUM'

    ds_weight = CONFIDENCE_WEIGHT.get(ds_conf, 2)
    ma_weight = CONFIDENCE_WEIGHT.get(ma_conf, 2)

    fusion_msg = (
        f"🔀 Confidence fusion: DeepSeek={ds_signal}({ds_conf}, w={ds_weight}) "
        f"vs MultiAgent={ma_signal}({ma_conf}, w={ma_weight})"
    )
    if logger:
        logger.info(fusion_msg)

    if ds_weight > ma_weight:
        # DeepSeek has higher confidence - use its signal
        result_msg = f"✅ Fusion result: Using DeepSeek signal ({ds_signal}) - higher confidence"
        if logger:
            logger.info(result_msg)
        return signal_deepseek, result_msg

    elif ma_weight > ds_weight:
        # MultiAgent has higher confidence - use its signal
        result_msg = f"✅ Fusion result: Using MultiAgent signal ({ma_signal}) - higher confidence"
        if logger:
            logger.info(result_msg)
        # Construct signal in DeepSeek format
        resolved = {
            'signal': ma_signal,
            'confidence': ma_conf,
            'reason': f"MultiAgent signal selected (higher confidence: {ma_conf} vs {ds_conf}). {signal_multi.get('debate_summary', '')}",
            'stop_loss': signal_multi.get('stop_loss'),
            'take_profit': signal_multi.get('take_profit'),
        }
        return resolved, result_msg

    else:
        # Equal confidence - return None to trigger skip
        result_msg = f"⚖️ Equal confidence ({ds_conf}) - cannot resolve divergence"
        if logger:
            logger.warning(result_msg)
        return None, result_msg


def check_confidence_threshold(
    confidence: str,
    min_confidence: str,
) -> Tuple[bool, str]:
    """
    Check if signal confidence meets minimum threshold.

    Parameters
    ----------
    confidence : str
        Signal confidence ('LOW', 'MEDIUM', 'HIGH')
    min_confidence : str
        Minimum required confidence

    Returns
    -------
    Tuple[bool, str]
        (passes_threshold, message)
    """
    min_conf_level = CONFIDENCE_LEVELS.get(min_confidence, 1)
    signal_conf_level = CONFIDENCE_LEVELS.get(confidence, 1)

    if signal_conf_level < min_conf_level:
        msg = f"⚠️ Signal confidence {confidence} below minimum {min_confidence}, skipping trade"
        return False, msg

    msg = f"✅ Confidence {confidence} >= minimum {min_confidence}"
    return True, msg


def calculate_position_size(
    signal_data: Dict[str, Any],
    price_data: Dict[str, Any],
    technical_data: Dict[str, Any],
    config: Dict[str, Any],
    logger: Optional[logging.Logger] = None,
) -> Tuple[float, Dict[str, Any]]:
    """
    Calculate intelligent position size.

    Parameters
    ----------
    signal_data : Dict
        AI-generated signal with 'confidence'
    price_data : Dict
        Current price data with 'price'
    technical_data : Dict
        Technical indicators with 'overall_trend', 'rsi'
    config : Dict
        Configuration with keys:
        - base_usdt: Base USDT amount
        - equity: Total equity
        - high_confidence_multiplier
        - medium_confidence_multiplier
        - low_confidence_multiplier
        - trend_strength_multiplier
        - rsi_extreme_multiplier
        - rsi_extreme_upper
        - rsi_extreme_lower
        - max_position_ratio
        - min_trade_amount
    logger : Logger, optional
        Logger for output messages

    Returns
    -------
    Tuple[float, Dict]
        (btc_quantity, calculation_details)
    """
    # Base USDT amount
    base_usdt = config['base_usdt']

    # Confidence multiplier
    confidence = signal_data.get('confidence', 'MEDIUM').lower()
    conf_mult = config.get(f'{confidence}_confidence_multiplier', 1.0)

    # Trend multiplier
    trend = technical_data.get('overall_trend', '震荡整理')
    trend_mult = (
        config['trend_strength_multiplier']
        if trend in ['强势上涨', '强势下跌']
        else 1.0
    )

    # RSI multiplier (reduce size in extreme RSI)
    rsi = technical_data.get('rsi', 50)
    rsi_mult = (
        config['rsi_extreme_multiplier']
        if rsi > config['rsi_extreme_upper'] or rsi < config['rsi_extreme_lower']
        else 1.0
    )

    # Calculate suggested USDT
    suggested_usdt = base_usdt * conf_mult * trend_mult * rsi_mult

    # Apply max position ratio limit
    max_usdt = config['equity'] * config['max_position_ratio']
    final_usdt = min(suggested_usdt, max_usdt)

    # Enforce Binance minimum notional requirement ($100)
    MIN_NOTIONAL_USDT = 100.0
    if final_usdt < MIN_NOTIONAL_USDT:
        final_usdt = MIN_NOTIONAL_USDT

    # Convert to BTC quantity
    current_price = price_data['price']
    btc_quantity = final_usdt / current_price

    # Apply minimum trade amount
    min_trade = config.get('min_trade_amount', 0.001)
    if btc_quantity < min_trade:
        btc_quantity = min_trade

    # Round to instrument precision
    btc_quantity = round(btc_quantity, 3)  # Binance BTC precision

    # CRITICAL: Re-check notional after rounding
    MIN_NOTIONAL_SAFETY_MARGIN = 1.01  # 1% safety margin
    MIN_NOTIONAL_WITH_MARGIN = MIN_NOTIONAL_USDT * MIN_NOTIONAL_SAFETY_MARGIN

    actual_notional = btc_quantity * current_price
    adjusted = False
    if actual_notional < MIN_NOTIONAL_WITH_MARGIN:
        # Increase quantity to meet minimum notional with safety margin (round UP)
        btc_quantity = MIN_NOTIONAL_WITH_MARGIN / current_price
        # Round up to next 0.001
        btc_quantity = math.ceil(btc_quantity * 1000) / 1000
        # Final verification
        final_notional = btc_quantity * current_price
        if final_notional < MIN_NOTIONAL_USDT:
            btc_quantity += 0.001
        adjusted = True
        if logger:
            logger.warning(
                f"⚠️ Adjusted quantity after rounding: {btc_quantity:.3f} BTC "
                f"to meet ${MIN_NOTIONAL_USDT} minimum notional"
            )

    # Calculate final notional
    notional = btc_quantity * current_price

    # Log calculation details
    if logger:
        logger.info(
            f"📊 Position Sizing: "
            f"Base:{base_usdt} × Conf:{conf_mult} × Trend:{trend_mult} × RSI:{rsi_mult} "
            f"= ${final_usdt:.2f} = {btc_quantity:.3f} BTC "
            f"(notional: ${notional:.2f})"
        )

    # Return calculation details for diagnostic display
    details = {
        'base_usdt': base_usdt,
        'conf_mult': conf_mult,
        'trend_mult': trend_mult,
        'trend': trend,
        'rsi_mult': rsi_mult,
        'rsi': rsi,
        'suggested_usdt': suggested_usdt,
        'max_usdt': max_usdt,
        'final_usdt': final_usdt,
        'btc_quantity': btc_quantity,
        'notional': notional,
        'adjusted': adjusted,
    }

    return btc_quantity, details


# =============================================================================
# SL/TP VALIDATION FUNCTIONS (v9.0)
# Used by both deepseek_strategy.py and diagnose_realtime.py
# =============================================================================

# SL/TP validation constants
# NOTE: Must match multi_agent_analyzer.py MIN_SL_DISTANCE_PCT
MIN_SL_DISTANCE_PCT = 0.01   # 1% minimum SL distance (avoid too tight stops)
MIN_TP_DISTANCE_PCT = 0.005  # 0.5% minimum TP distance

# Default SL/TP fallback percentages (used when AI returns invalid values)
DEFAULT_SL_PCT = 0.02        # 2% default stop loss distance
DEFAULT_TP_PCT_BUY = 0.03    # 3% take profit for BUY (above entry)
DEFAULT_TP_PCT_SELL = 0.03   # 3% take profit for SELL (below entry)

# TP percentage configuration by confidence level
TP_PCT_CONFIG = {
    'HIGH': 0.03,    # 3%
    'MEDIUM': 0.02,  # 2%
    'LOW': 0.01,     # 1%
}


def validate_multiagent_sltp(
    side: str,
    multi_sl: Optional[float],
    multi_tp: Optional[float],
    entry_price: float,
) -> Tuple[bool, Optional[float], Optional[float], str]:
    """
    Validate MultiAgent SL/TP values.

    This function validates that SL/TP values from MultiAgent are correct:
    - BUY: SL must be below entry, TP must be above entry
    - SELL: SL must be above entry, TP must be below entry
    - Both must have minimum distance from entry

    Parameters
    ----------
    side : str
        Trade side ('BUY' or 'SELL')
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

    if side == 'BUY':
        # BUY: SL must be < entry, TP must be > entry
        if multi_sl >= entry_price:
            return False, None, None, f"BUY SL (${multi_sl:,.2f}) must be < entry (${entry_price:,.2f})"
        if multi_tp <= entry_price:
            return False, None, None, f"BUY TP (${multi_tp:,.2f}) must be > entry (${entry_price:,.2f})"

        # Check minimum distances
        if sl_distance < MIN_SL_DISTANCE_PCT:
            return False, None, None, f"SL too close to entry ({sl_distance*100:.3f}% < {MIN_SL_DISTANCE_PCT*100}%)"
        if tp_distance < MIN_TP_DISTANCE_PCT:
            return False, None, None, f"TP too close to entry ({tp_distance*100:.3f}% < {MIN_TP_DISTANCE_PCT*100}%)"

        return True, multi_sl, multi_tp, f"Valid (SL: {sl_distance*100:.2f}%, TP: {tp_distance*100:.2f}%)"

    else:  # SELL
        # SELL: SL must be > entry, TP must be < entry
        if multi_sl <= entry_price:
            return False, None, None, f"SELL SL (${multi_sl:,.2f}) must be > entry (${entry_price:,.2f})"
        if multi_tp >= entry_price:
            return False, None, None, f"SELL TP (${multi_tp:,.2f}) must be < entry (${entry_price:,.2f})"

        # Check minimum distances
        if sl_distance < MIN_SL_DISTANCE_PCT:
            return False, None, None, f"SL too close to entry ({sl_distance*100:.3f}% < {MIN_SL_DISTANCE_PCT*100}%)"
        if tp_distance < MIN_TP_DISTANCE_PCT:
            return False, None, None, f"TP too close to entry ({tp_distance*100:.3f}% < {MIN_TP_DISTANCE_PCT*100}%)"

        return True, multi_sl, multi_tp, f"Valid (SL: {sl_distance*100:.2f}%, TP: {tp_distance*100:.2f}%)"


def calculate_technical_sltp(
    side: str,
    entry_price: float,
    support: float,
    resistance: float,
    confidence: str,
    use_support_resistance: bool = True,
    sl_buffer_pct: float = 0.001,
) -> Tuple[float, float, str]:
    """
    Calculate SL/TP based on technical analysis.

    This function calculates stop loss and take profit prices using:
    - Support/resistance levels (if available and valid)
    - Default percentage-based fallback

    Parameters
    ----------
    side : str
        Trade side ('BUY' or 'SELL')
    entry_price : float
        Entry price
    support : float
        Support level price
    resistance : float
        Resistance level price
    confidence : str
        Signal confidence ('HIGH', 'MEDIUM', 'LOW')
    use_support_resistance : bool
        Whether to use support/resistance levels
    sl_buffer_pct : float
        Buffer percentage to add to support/resistance

    Returns
    -------
    Tuple[float, float, str]
        (stop_loss_price, take_profit_price, calculation_method)
    """
    PRICE_EPSILON = max(entry_price * 1e-8, 1e-8)

    if side == 'BUY':
        # BUY: Stop loss below entry
        default_sl = entry_price * 0.98  # Default 2% below

        if use_support_resistance and support > 0:
            potential_sl = support * (1 - sl_buffer_pct)
            if potential_sl < entry_price - PRICE_EPSILON:
                stop_loss_price = potential_sl
                method = f"Support-based SL (${support:,.2f} - buffer)"
            else:
                stop_loss_price = default_sl
                method = f"Default 2% SL (support ${support:,.2f} >= entry)"
        else:
            stop_loss_price = default_sl
            method = "Default 2% SL"

        # TP
        tp_pct = TP_PCT_CONFIG.get(confidence, 0.02)
        take_profit_price = entry_price * (1 + tp_pct)

    else:  # SELL
        # SELL: Stop loss above entry
        default_sl = entry_price * 1.02  # Default 2% above

        if use_support_resistance and resistance > 0:
            potential_sl = resistance * (1 + sl_buffer_pct)
            if potential_sl > entry_price + PRICE_EPSILON:
                stop_loss_price = potential_sl
                method = f"Resistance-based SL (${resistance:,.2f} + buffer)"
            else:
                stop_loss_price = default_sl
                method = f"Default 2% SL (resistance ${resistance:,.2f} <= entry)"
        else:
            stop_loss_price = default_sl
            method = "Default 2% SL"

        # TP
        tp_pct = TP_PCT_CONFIG.get(confidence, 0.02)
        take_profit_price = entry_price * (1 - tp_pct)

    return stop_loss_price, take_profit_price, method


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def create_hold_signal(reason: str) -> Dict[str, Any]:
    """
    Create a standardized HOLD signal.

    Parameters
    ----------
    reason : str
        Reason for HOLD

    Returns
    -------
    Dict
        Standardized HOLD signal
    """
    return {
        'signal': 'HOLD',
        'confidence': 'LOW',
        'reason': reason,
        'stop_loss': None,
        'take_profit': None,
    }


def process_signals(
    signal_deepseek: Dict[str, Any],
    signal_multi: Dict[str, Any],
    use_confidence_fusion: bool = True,
    skip_on_divergence: bool = True,
    logger: Optional[logging.Logger] = None,
) -> Tuple[Dict[str, Any], bool, str]:
    """
    Process and merge DeepSeek and MultiAgent signals.

    This is the main signal processing logic used by both live trading and diagnostic.

    Parameters
    ----------
    signal_deepseek : Dict
        DeepSeek AI signal
    signal_multi : Dict
        MultiAgent signal
    use_confidence_fusion : bool
        Whether to use confidence fusion for divergence
    skip_on_divergence : bool
        Whether to skip trade on unresolved divergence
    logger : Logger, optional
        Logger for output messages

    Returns
    -------
    Tuple[Dict, bool, str]
        (final_signal, is_consensus, status_message)
    """
    ds_signal = signal_deepseek.get('signal', 'ERROR')
    ma_signal = signal_multi.get('signal', 'ERROR')

    # Check divergence
    is_consensus, is_opposing, is_hold_vs_action = check_divergence(ds_signal, ma_signal)

    if is_consensus:
        # Both agree - use DeepSeek signal but with MultiAgent SL/TP if available
        msg = f"✅ Consensus: Both analyzers agree on {ds_signal}"
        if logger:
            logger.info(msg)

        # Merge SL/TP from MultiAgent if available
        final_signal = signal_deepseek.copy()
        if signal_multi.get('stop_loss') and signal_multi.get('take_profit'):
            final_signal['stop_loss_multi'] = signal_multi['stop_loss']
            final_signal['take_profit_multi'] = signal_multi['take_profit']
            if logger:
                logger.info(
                    f"📊 Using MultiAgent SL/TP: "
                    f"SL=${signal_multi['stop_loss']:,.2f}, TP=${signal_multi['take_profit']:,.2f}"
                )

        return final_signal, True, msg

    # Handle divergence
    if is_opposing or is_hold_vs_action:
        divergence_type = "BUY vs SELL" if is_opposing else "HOLD vs action"

        if use_confidence_fusion:
            resolved_signal, fusion_msg = resolve_divergence_by_confidence(
                signal_deepseek, signal_multi, logger
            )

            if resolved_signal:
                return resolved_signal, False, fusion_msg

            # Equal confidence - check skip_on_divergence
            if skip_on_divergence:
                msg = f"🚫 Equal confidence divergence ({divergence_type}) - SKIPPING trade"
                if logger:
                    logger.warning(msg)
                return create_hold_signal(msg), False, msg
            else:
                msg = f"⚠️ Equal confidence but skip_on_divergence=False - using DeepSeek"
                if logger:
                    logger.warning(msg)
                return signal_deepseek, False, msg

        elif skip_on_divergence:
            msg = f"🚫 Divergence ({divergence_type}): skip_on_divergence=True - SKIPPING"
            if logger:
                logger.warning(msg)
            return create_hold_signal(msg), False, msg

        else:
            msg = f"⚠️ Divergence ({divergence_type}): using DeepSeek signal"
            if logger:
                logger.warning(msg)
            return signal_deepseek, False, msg

    # Unexpected divergence type
    msg = f"⚠️ Unexpected divergence: DeepSeek={ds_signal}, MultiAgent={ma_signal}"
    if logger:
        logger.warning(msg)
    return signal_deepseek, False, msg
