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
    max_position_ratio = config.get('max_position_ratio', 0.30)
    max_usdt = equity * max_position_ratio

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
        # v3.12: AI specifies target position as percentage
        size_pct = float(ai_size_pct) / 100.0  # Convert 0-100 to 0-1

        # Calculate target USDT based on percentage of max allowed
        position_usdt = max_usdt * size_pct

        # Apply risk multiplier
        position_usdt *= risk_multiplier

        final_usdt = position_usdt

        details = {
            'method': 'ai_controlled',
            'ai_size_pct': ai_size_pct,
            'equity': equity,
            'max_usdt': max_usdt,
            'risk_multiplier': risk_multiplier,
            'final_usdt': final_usdt,
        }

        if logger:
            logger.info(f"📊 AI-controlled sizing: {ai_size_pct}% of max = ${final_usdt:.2f}")

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

    if is_long:
        # BUY: SL must be < entry, TP must be > entry
        if multi_sl >= entry_price:
            return False, None, None, f"BUY SL (${multi_sl:,.2f}) must be < entry (${entry_price:,.2f})"
        if multi_tp <= entry_price:
            return False, None, None, f"BUY TP (${multi_tp:,.2f}) must be > entry (${entry_price:,.2f})"

        # Check minimum distances
        min_sl = get_min_sl_distance_pct()
        min_tp = get_min_tp_distance_pct()
        if sl_distance < min_sl:
            return False, None, None, f"SL too close to entry ({sl_distance*100:.3f}% < {min_sl*100}%)"
        if tp_distance < min_tp:
            return False, None, None, f"TP too close to entry ({tp_distance*100:.3f}% < {min_tp*100}%)"

        return True, multi_sl, multi_tp, f"Valid (SL: {sl_distance*100:.2f}%, TP: {tp_distance*100:.2f}%)"

    else:  # SELL
        # SELL: SL must be > entry, TP must be < entry
        if multi_sl <= entry_price:
            return False, None, None, f"SELL SL (${multi_sl:,.2f}) must be > entry (${entry_price:,.2f})"
        if multi_tp >= entry_price:
            return False, None, None, f"SELL TP (${multi_tp:,.2f}) must be < entry (${entry_price:,.2f})"

        # Check minimum distances
        min_sl = get_min_sl_distance_pct()
        min_tp = get_min_tp_distance_pct()
        if sl_distance < min_sl:
            return False, None, None, f"SL too close to entry ({sl_distance*100:.3f}% < {min_sl*100}%)"
        if tp_distance < min_tp:
            return False, None, None, f"TP too close to entry ({tp_distance*100:.3f}% < {min_tp*100}%)"

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
        Trade side ('BUY', 'SELL', 'LONG', or 'SHORT')
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

    # v3.12: Support both legacy (BUY/SELL) and new (LONG/SHORT) formats
    is_long = side.upper() in ('BUY', 'LONG')

    if is_long:
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
        tp_pct = get_tp_pct_by_confidence(confidence)
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
        tp_pct = get_tp_pct_by_confidence(confidence)
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
