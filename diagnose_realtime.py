#!/usr/bin/env python3
"""
实盘信号诊断脚本 v3.0

关键特性:
1. 调用 main_live.py 中的 get_strategy_config() 获取真实配置
2. 使用与实盘完全相同的组件初始化参数
3. 模拟 deepseek_strategy.py 中 on_timer 的完整流程
4. 输出实盘环境下会产生的真实结果

使用方法:
    cd /home/linuxuser/nautilus_AItrader
    source venv/bin/activate
    python3 diagnose_realtime.py
"""

import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

# =============================================================================
# 关键: 使用与 main_live.py 完全相同的初始化流程
# =============================================================================

# 设置项目路径 (与 main_live.py 相同)
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 应用补丁 (与 main_live.py 相同)
from patches.binance_enums import apply_all_patches
apply_all_patches()

# 加载环境变量 (与 main_live.py 相同)
from dotenv import load_dotenv
env_permanent = Path.home() / ".env.aitrader"
env_local = project_root / ".env"

if env_permanent.exists():
    load_dotenv(env_permanent)
elif env_local.exists():
    load_dotenv(env_local)
else:
    load_dotenv()

print("=" * 70)
print("  实盘信号诊断工具 v3.0 (调用真实代码路径)")
print("=" * 70)
print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
print()

# =============================================================================
# 1. 从 main_live.py 导入并获取真实配置
# =============================================================================
print("[1/9] 从 main_live.py 加载真实配置...")

try:
    from main_live import get_strategy_config, load_yaml_config

    # 获取与实盘完全相同的配置
    strategy_config = get_strategy_config()
    yaml_config = load_yaml_config()

    print(f"  instrument_id: {strategy_config.instrument_id}")
    print(f"  bar_type: {strategy_config.bar_type}")
    print(f"  equity: ${strategy_config.equity}")
    print(f"  base_usdt_amount: ${strategy_config.base_usdt_amount}")
    print(f"  leverage: {strategy_config.leverage}x")
    print(f"  min_confidence_to_trade: {strategy_config.min_confidence_to_trade}")
    print(f"  timer_interval_sec: {strategy_config.timer_interval_sec}s")
    print(f"  sma_periods: {strategy_config.sma_periods}")
    print(f"  rsi_period: {strategy_config.rsi_period}")
    print(f"  macd_fast/slow: {strategy_config.macd_fast}/{strategy_config.macd_slow}")
    print(f"  debate_rounds: {strategy_config.debate_rounds}")
    print("  ✅ 配置加载成功 (与实盘完全一致)")
except Exception as e:
    print(f"  ❌ 配置加载失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# =============================================================================
# 2. 获取市场数据 (与实盘相同的数据源)
# =============================================================================
print("[2/9] 获取市场数据 (Binance Futures)...")

import requests

# 从 bar_type 解析时间周期 (注意: 必须先检查更长的字符串)
bar_type_str = strategy_config.bar_type
if "15-MINUTE" in bar_type_str:
    interval = "15m"
elif "5-MINUTE" in bar_type_str:
    interval = "5m"
elif "1-MINUTE" in bar_type_str:
    interval = "1m"
elif "4-HOUR" in bar_type_str:
    interval = "4h"
elif "1-HOUR" in bar_type_str:
    interval = "1h"
elif "1-DAY" in bar_type_str:
    interval = "1d"
else:
    interval = "15m"

symbol = "BTCUSDT"
limit = 100

try:
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url, timeout=10)
    klines_raw = response.json()

    if isinstance(klines_raw, list) and len(klines_raw) > 0:
        print(f"  交易对: {symbol}")
        print(f"  时间周期: {interval} (从 bar_type 解析)")
        print(f"  K线数量: {len(klines_raw)}")

        latest = klines_raw[-1]
        current_price = float(latest[4])
        print(f"  最新价格: ${current_price:,.2f}")
        print("  ✅ 市场数据获取成功")
    else:
        print(f"  ❌ K线数据异常: {klines_raw}")
        sys.exit(1)
except Exception as e:
    print(f"  ❌ 获取市场数据失败: {e}")
    sys.exit(1)

print()

# =============================================================================
# 3. 使用真实配置初始化 TechnicalIndicatorManager
# =============================================================================
print("[3/9] 初始化 TechnicalIndicatorManager (使用实盘配置)...")

try:
    from indicators.technical_manager import TechnicalIndicatorManager

    # 使用与 deepseek_strategy.py __init__ 完全相同的参数
    indicator_manager = TechnicalIndicatorManager(
        sma_periods=list(strategy_config.sma_periods),  # 从配置读取
        ema_periods=[strategy_config.macd_fast, strategy_config.macd_slow],  # MACD 周期
        rsi_period=strategy_config.rsi_period,
        macd_fast=strategy_config.macd_fast,
        macd_slow=strategy_config.macd_slow,
        macd_signal=9,  # 固定值
        bb_period=strategy_config.bb_period,
        bb_std=strategy_config.bb_std,
        volume_ma_period=20,
        support_resistance_lookback=20,
    )

    print(f"  sma_periods: {list(strategy_config.sma_periods)}")
    print(f"  ema_periods: [{strategy_config.macd_fast}, {strategy_config.macd_slow}]")
    print(f"  rsi_period: {strategy_config.rsi_period}")
    print(f"  macd: {strategy_config.macd_fast}/{strategy_config.macd_slow}/9")
    print(f"  bb_period: {strategy_config.bb_period}")
    print("  ✅ TechnicalIndicatorManager 初始化成功")

    # 喂入 K 线数据
    for kline in klines_raw:
        class MockBar:
            def __init__(self, o, h, l, c, v, ts):
                self.open = Decimal(str(o))
                self.high = Decimal(str(h))
                self.low = Decimal(str(l))
                self.close = Decimal(str(c))
                self.volume = Decimal(str(v))
                self.ts_init = int(ts)

        bar = MockBar(
            float(kline[1]), float(kline[2]), float(kline[3]),
            float(kline[4]), float(kline[5]), int(kline[0])
        )
        indicator_manager.update(bar)

    # 检查是否初始化完成
    if indicator_manager.is_initialized():
        print(f"  ✅ 指标已初始化 ({len(klines_raw)} 根K线)")
    else:
        print(f"  ⚠️ 指标未完全初始化，可能数据不足")

except Exception as e:
    print(f"  ❌ TechnicalIndicatorManager 失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# =============================================================================
# 4. 获取技术数据 (与 on_timer 相同)
# =============================================================================
print("[4/9] 获取技术数据 (模拟 on_timer 流程)...")

try:
    technical_data = indicator_manager.get_technical_data(current_price)

    # 显示关键指标
    sma_keys = [k for k in technical_data.keys() if k.startswith('sma_')]
    for key in sorted(sma_keys):
        print(f"  {key.upper()}: ${technical_data[key]:,.2f}")

    ema_keys = [k for k in technical_data.keys() if k.startswith('ema_')]
    for key in sorted(ema_keys):
        print(f"  {key.upper()}: ${technical_data[key]:,.2f}")

    print(f"  RSI: {technical_data.get('rsi', 0):.2f}")
    print(f"  MACD: {technical_data.get('macd', 0):.4f}")
    print(f"  MACD Signal: {technical_data.get('macd_signal', 0):.4f}")
    print(f"  MACD Histogram: {technical_data.get('macd_histogram', 0):.4f}")
    print(f"  BB Upper: ${technical_data.get('bb_upper', 0):,.2f}")
    print(f"  BB Lower: ${technical_data.get('bb_lower', 0):,.2f}")
    print(f"  Support: ${technical_data.get('support', 0):,.2f}")
    print(f"  Resistance: ${technical_data.get('resistance', 0):,.2f}")
    print(f"  Overall Trend: {technical_data.get('overall_trend', 'N/A')}")
    print("  ✅ 技术数据获取成功")

except Exception as e:
    print(f"  ❌ 技术数据获取失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# =============================================================================
# 5. 初始化并获取情绪数据 (使用实盘配置)
# =============================================================================
print("[5/9] 获取情绪数据 (使用实盘配置)...")

try:
    from utils.sentiment_client import SentimentDataFetcher

    # 使用与 deepseek_strategy.py on_start 相同的参数
    sentiment_fetcher = SentimentDataFetcher(
        lookback_hours=strategy_config.sentiment_lookback_hours,
        timeframe=strategy_config.sentiment_timeframe,
    )

    print(f"  lookback_hours: {strategy_config.sentiment_lookback_hours}")
    print(f"  timeframe: {strategy_config.sentiment_timeframe}")

    sentiment_data = sentiment_fetcher.fetch()

    if sentiment_data:
        print(f"  Long/Short Ratio: {sentiment_data.get('long_short_ratio', 0):.4f}")
        print(f"  Long Account %: {sentiment_data.get('long_account_pct', 0):.2f}%")
        print(f"  Short Account %: {sentiment_data.get('short_account_pct', 0):.2f}%")
        print(f"  Source: {sentiment_data.get('source', 'N/A')}")
        print("  ✅ 情绪数据获取成功")
    else:
        # 与 on_timer 相同的 fallback 逻辑
        sentiment_data = {
            'long_short_ratio': 1.0,
            'long_account_pct': 50.0,
            'short_account_pct': 50.0,
            'source': 'default_neutral',
            'timestamp': None,
        }
        print("  ⚠️ 使用中性默认值 (与 on_timer fallback 相同)")

except Exception as e:
    print(f"  ❌ 情绪数据获取失败: {e}")
    sentiment_data = {
        'long_short_ratio': 1.0,
        'long_account_pct': 50.0,
        'short_account_pct': 50.0,
        'source': 'fallback',
    }

print()

# =============================================================================
# 6. 构建价格数据 (与 on_timer 相同结构)
# =============================================================================
print("[6/9] 构建价格数据...")

kline_data = indicator_manager.get_kline_data(count=10)

# 计算价格变化
bars = indicator_manager.recent_bars
if len(bars) >= 2:
    price_change = ((float(bars[-1].close) - float(bars[-2].close)) / float(bars[-2].close)) * 100
else:
    price_change = 0.0

price_data = {
    'price': current_price,
    'timestamp': datetime.now().isoformat(),
    'high': float(klines_raw[-1][2]),
    'low': float(klines_raw[-1][3]),
    'volume': float(klines_raw[-1][5]),
    'price_change': price_change,
    'kline_data': kline_data,
}

print(f"  Current Price: ${price_data['price']:,.2f}")
print(f"  High: ${price_data['high']:,.2f}")
print(f"  Low: ${price_data['low']:,.2f}")
print(f"  Price Change: {price_data['price_change']:.2f}%")
print(f"  K-line Count: {len(price_data['kline_data'])}")
print("  ✅ 价格数据构建成功")

print()

# =============================================================================
# 7. DeepSeek AI 分析 (阶段6 - 使用实盘配置)
# =============================================================================
print("[7/9] 阶段6: DeepSeek AI 分析 (使用实盘配置)...")
print("-" * 70)

try:
    from utils.deepseek_client import DeepSeekAnalyzer

    # 使用与 deepseek_strategy.py 完全相同的初始化参数
    deepseek = DeepSeekAnalyzer(
        api_key=strategy_config.deepseek_api_key,
        model=strategy_config.deepseek_model,
        temperature=strategy_config.deepseek_temperature,
        max_retries=strategy_config.deepseek_max_retries,
    )

    print(f"  Model: {strategy_config.deepseek_model}")
    print(f"  Temperature: {strategy_config.deepseek_temperature}")
    print(f"  Max Retries: {strategy_config.deepseek_max_retries}")
    print("  正在调用 DeepSeek API...")

    # 调用分析 (与 on_timer 相同)
    signal_deepseek = deepseek.analyze(
        price_data=price_data,
        technical_data=technical_data,
        sentiment_data=sentiment_data,
        current_position=None,  # 无持仓
    )

    print()
    print("  🤖 DeepSeek 分析结果:")
    print(f"     Signal: {signal_deepseek.get('signal', 'N/A')}")
    print(f"     Confidence: {signal_deepseek.get('confidence', 'N/A')}")
    print(f"     Stop Loss: {signal_deepseek.get('stop_loss', 'N/A')}")
    print(f"     Take Profit: {signal_deepseek.get('take_profit', 'N/A')}")
    reason = signal_deepseek.get('reason', 'N/A')
    print(f"     Reason: {reason[:150]}..." if len(reason) > 150 else f"     Reason: {reason}")
    print("  ✅ DeepSeek 分析成功")

except Exception as e:
    print(f"  ❌ DeepSeek 分析失败: {e}")
    import traceback
    traceback.print_exc()
    signal_deepseek = {
        'signal': 'ERROR',
        'confidence': 'LOW',
        'reason': str(e),
        'stop_loss': None,
        'take_profit': None,
    }

print()

# =============================================================================
# 8. MultiAgent 辩论 (阶段7 - 使用实盘配置)
# =============================================================================
print("[8/9] 阶段7: MultiAgent 辩论 (使用实盘配置)...")
print("-" * 70)

try:
    from agents.multi_agent_analyzer import MultiAgentAnalyzer

    # 使用与 deepseek_strategy.py 完全相同的初始化参数
    multi_agent = MultiAgentAnalyzer(
        api_key=strategy_config.deepseek_api_key,
        model=strategy_config.deepseek_model,
        temperature=strategy_config.deepseek_temperature,
        debate_rounds=strategy_config.debate_rounds,
    )

    print(f"  Model: {strategy_config.deepseek_model}")
    print(f"  Temperature: {strategy_config.deepseek_temperature}")
    print(f"  Debate Rounds: {strategy_config.debate_rounds}")
    print("  正在进行 Bull/Bear 辩论...")
    print("  🐂 Bull Agent 分析中...")
    print("  🐻 Bear Agent 分析中...")
    print("  ⚖️ Judge Agent 判断中...")

    # 调用分析 (与 on_timer 相同)
    signal_multi = multi_agent.analyze(
        symbol="BTCUSDT",
        technical_report=technical_data,
        sentiment_report=sentiment_data,
        current_position=None,
        price_data=price_data,
    )

    print()
    print("  🎯 MultiAgent 辩论结果:")
    print(f"     Signal: {signal_multi.get('signal', 'N/A')}")
    print(f"     Confidence: {signal_multi.get('confidence', 'N/A')}")
    print(f"     Stop Loss: {signal_multi.get('stop_loss', 'N/A')}")
    print(f"     Take Profit: {signal_multi.get('take_profit', 'N/A')}")
    if signal_multi.get('debate_summary'):
        summary = signal_multi['debate_summary']
        print(f"     Debate Summary: {summary[:150]}..." if len(summary) > 150 else f"     Debate Summary: {summary}")
    print("  ✅ MultiAgent 辩论成功")

except Exception as e:
    print(f"  ❌ MultiAgent 辩论失败: {e}")
    import traceback
    traceback.print_exc()
    signal_multi = {
        'signal': 'ERROR',
        'confidence': 'LOW',
        'reason': str(e),
    }

print()

# =============================================================================
# 9. 共识检查和最终决策 (与 on_timer 完全相同的逻辑)
# =============================================================================
print("[9/9] 共识检查和交易决策 (模拟 _execute_trade)...")
print("-" * 70)

deepseek_signal = signal_deepseek.get('signal', 'ERROR')
multi_signal = signal_multi.get('signal', 'ERROR')
confidence = signal_deepseek.get('confidence', 'LOW')

print(f"  DeepSeek Signal: {deepseek_signal}")
print(f"  MultiAgent Signal: {multi_signal}")
print()

# 共识检查 (与 on_timer 相同)
# 获取分歧处理配置
skip_on_divergence = getattr(strategy_config, 'skip_on_divergence', True)
use_confidence_fusion = getattr(strategy_config, 'use_confidence_fusion', True)
print(f"  skip_on_divergence: {skip_on_divergence}")
print(f"  use_confidence_fusion: {use_confidence_fusion}")
print()

# 加权信心融合辅助函数 (与 _resolve_divergence_by_confidence 相同逻辑)
def resolve_divergence_by_confidence(ds_signal, ds_conf, ma_signal, ma_conf):
    """使用加权信心融合解决对立信号"""
    confidence_weight = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
    ds_weight = confidence_weight.get(ds_conf, 2)
    ma_weight = confidence_weight.get(ma_conf, 2)

    print(f"  🔀 Confidence fusion: DeepSeek={ds_signal}({ds_conf}, w={ds_weight}) "
          f"vs MultiAgent={ma_signal}({ma_conf}, w={ma_weight})")

    if ds_weight > ma_weight:
        print(f"  ✅ Fusion result: Using DeepSeek signal ({ds_signal}) - higher confidence")
        return ds_signal, ds_conf
    elif ma_weight > ds_weight:
        print(f"  ✅ Fusion result: Using MultiAgent signal ({ma_signal}) - higher confidence")
        return ma_signal, ma_conf
    else:
        print(f"  ⚖️ Equal confidence ({ds_conf}) - cannot resolve divergence")
        return None, None  # 需要跳过

if deepseek_signal == multi_signal:
    print("  ✅ Consensus: Both analyzers agree")
    consensus = True
    final_signal = deepseek_signal
    # 当共识时，使用 MultiAgent 的 SL/TP
    if signal_multi.get('stop_loss') and signal_multi.get('take_profit'):
        print(f"  📊 Using MultiAgent SL/TP:")
        print(f"     SL: ${signal_multi['stop_loss']:,.2f}")
        print(f"     TP: ${signal_multi['take_profit']:,.2f}")
else:
    # 检查是否是 BUY vs SELL 完全对立
    opposing_signals = {deepseek_signal, multi_signal} == {'BUY', 'SELL'}

    # 检查是否是 HOLD vs 可执行信号 (BUY/SELL)
    hold_vs_action = (
        (deepseek_signal == 'HOLD' and multi_signal in ['BUY', 'SELL']) or
        (multi_signal == 'HOLD' and deepseek_signal in ['BUY', 'SELL'])
    )

    if opposing_signals or hold_vs_action:
        # 使用加权信心融合 (与 strategy 代码一致)
        if use_confidence_fusion:
            ds_conf = signal_deepseek.get('confidence', 'MEDIUM')
            ma_conf = signal_multi.get('confidence', 'MEDIUM')
            resolved_signal, resolved_conf = resolve_divergence_by_confidence(
                deepseek_signal, ds_conf, multi_signal, ma_conf
            )
            if resolved_signal:
                final_signal = resolved_signal
                confidence = resolved_conf
            elif skip_on_divergence:
                print(f"  🚫 Equal confidence divergence - SKIPPING trade")
                final_signal = 'HOLD'
                confidence = 'LOW'
                signal_deepseek['reason'] = "Equal confidence divergence - trade skipped for safety"
            else:
                print(f"  ⚠️ Equal confidence but skip_on_divergence=False - using DeepSeek signal")
                final_signal = deepseek_signal
        elif skip_on_divergence:
            print(f"  🚫 Divergence: DeepSeek={deepseek_signal}, MultiAgent={multi_signal}")
            print("     → SKIPPING trade (skip_on_divergence=True)")
            final_signal = 'HOLD'
            confidence = 'LOW'
            signal_deepseek['reason'] = f"Trade skipped: divergence without fusion"
        else:
            print(f"  ⚠️ Divergence: DeepSeek={deepseek_signal}, MultiAgent={multi_signal}")
            print("     → Using DeepSeek signal")
            final_signal = deepseek_signal
    else:
        # 其他非对立分歧 (不应该出现)
        print(f"  ⚠️ Unexpected divergence: DeepSeek={deepseek_signal}, MultiAgent={multi_signal}")
        print("     → Using DeepSeek signal")
        final_signal = deepseek_signal
    consensus = False

print()

# 模拟 _execute_trade 的检查逻辑
print("  模拟 _execute_trade 检查:")

# 1. 检查 min_confidence
confidence_levels = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}
min_conf_level = confidence_levels.get(strategy_config.min_confidence_to_trade, 1)
signal_conf_level = confidence_levels.get(confidence, 1)

if signal_conf_level < min_conf_level:
    print(f"  ❌ Confidence {confidence} < minimum {strategy_config.min_confidence_to_trade}")
    print("     → Trade would be SKIPPED")
    would_trade = False
else:
    print(f"  ✅ Confidence {confidence} >= minimum {strategy_config.min_confidence_to_trade}")
    would_trade = True

# 2. 检查是否 HOLD (使用 final_signal，考虑分歧跳过)
if final_signal == 'HOLD':
    print("  ℹ️ Signal is HOLD → No action")
    would_trade = False
elif final_signal in ['BUY', 'SELL']:
    print(f"  ✅ Signal is {final_signal} → Actionable")
else:
    print(f"  ❌ Signal is {final_signal} → Error state")
    would_trade = False

# 3. 计算仓位大小 (模拟 _calculate_position_size)
if would_trade and final_signal in ['BUY', 'SELL']:
    print()
    print("  模拟仓位计算 (_calculate_position_size):")

    base_usdt = strategy_config.base_usdt_amount
    conf_mult = {
        'HIGH': strategy_config.high_confidence_multiplier,
        'MEDIUM': strategy_config.medium_confidence_multiplier,
        'LOW': strategy_config.low_confidence_multiplier,
    }.get(confidence, 1.0)

    trend = technical_data.get('overall_trend', '震荡整理')
    trend_mult = strategy_config.trend_strength_multiplier if trend in ['强势上涨', '强势下跌'] else 1.0

    rsi = technical_data.get('rsi', 50)
    rsi_mult = strategy_config.rsi_extreme_multiplier if (rsi > strategy_config.rsi_extreme_threshold_upper or rsi < strategy_config.rsi_extreme_threshold_lower) else 1.0

    suggested_usdt = base_usdt * conf_mult * trend_mult * rsi_mult
    max_usdt = strategy_config.equity * strategy_config.max_position_ratio
    final_usdt = min(suggested_usdt, max_usdt)

    # Binance minimum notional
    if final_usdt < 100:
        final_usdt = 100

    btc_quantity = final_usdt / current_price
    btc_quantity = round(btc_quantity, 3)

    # 确保最小名义值
    import math
    if btc_quantity * current_price < 101:
        btc_quantity = math.ceil(101 / current_price * 1000) / 1000

    print(f"     Base: ${base_usdt}")
    print(f"     × Confidence Mult: {conf_mult}")
    print(f"     × Trend Mult: {trend_mult} (trend={trend})")
    print(f"     × RSI Mult: {rsi_mult} (RSI={rsi:.1f})")
    print(f"     = ${suggested_usdt:.2f}")
    print(f"     Max allowed: ${max_usdt:.2f}")
    print(f"     Final: ${final_usdt:.2f}")
    print(f"     BTC Quantity: {btc_quantity:.4f} BTC")
    print(f"     Notional: ${btc_quantity * current_price:.2f}")

print()

# =============================================================================
# 最终诊断总结
# =============================================================================
print("=" * 70)
print("  诊断总结 (实盘代码路径)")
print("=" * 70)
print()

# final_signal 已在共识检查阶段设置，考虑了分歧处理逻辑
print(f"  📊 Final Signal: {final_signal}")
print(f"  📊 Confidence: {confidence}")
print(f"  📊 Consensus: {'Yes' if consensus else 'No (Divergence)'}")
print(f"  📊 use_confidence_fusion: {use_confidence_fusion}")
print(f"  📊 skip_on_divergence: {skip_on_divergence}")
print()

if would_trade and final_signal in ['BUY', 'SELL']:
    print(f"  🟢 WOULD EXECUTE: {final_signal} {btc_quantity:.4f} BTC @ ${current_price:,.2f}")
    print(f"     Notional: ${btc_quantity * current_price:.2f}")
    if signal_deepseek.get('stop_loss'):
        print(f"     Stop Loss: ${signal_deepseek['stop_loss']:,.2f}")
    if signal_deepseek.get('take_profit'):
        print(f"     Take Profit: ${signal_deepseek['take_profit']:,.2f}")
elif final_signal == 'HOLD':
    print("  🟡 NO TRADE: AI recommends HOLD")
    print(f"     Reason: {signal_deepseek.get('reason', 'N/A')[:100]}...")
else:
    print(f"  🔴 NO TRADE: Signal={final_signal}, Confidence={confidence}")
    if signal_conf_level < min_conf_level:
        print(f"     → Confidence below minimum ({strategy_config.min_confidence_to_trade})")

print()
print("=" * 70)
print("  诊断完成 - 以上结果与实盘运行完全一致")
print("=" * 70)

# =============================================================================
# 深入分析: 为什么没有交易信号?
# =============================================================================
print()
print("=" * 70)
print("  📋 深入分析: 信号产生条件")
print("=" * 70)
print()

# 1. 技术指标详细分析
print("[分析1] 技术指标阈值检查")
print("-" * 50)

rsi = technical_data.get('rsi', 50)
rsi_upper = getattr(strategy_config, 'rsi_extreme_threshold_upper', 70)
rsi_lower = getattr(strategy_config, 'rsi_extreme_threshold_lower', 30)

print(f"  RSI: {rsi:.2f}")
print(f"    配置阈值: 超卖<{rsi_lower}, 超买>{rsi_upper}")
if rsi > rsi_upper:
    print(f"    → 🔴 超买区 (>{rsi_upper}) - 可能触发 SELL")
elif rsi < rsi_lower:
    print(f"    → 🟢 超卖区 (<{rsi_lower}) - 可能触发 BUY")
else:
    print(f"    → ⚪ 中性区间 ({rsi_lower}-{rsi_upper}) - 无明确方向")
    print(f"    → 距离超买: {rsi_upper - rsi:.2f} 点")
    print(f"    → 距离超卖: {rsi - rsi_lower:.2f} 点")

macd = technical_data.get('macd', 0)
macd_signal = technical_data.get('macd_signal', 0)
macd_hist = technical_data.get('macd_histogram', 0)
print()
print(f"  MACD: {macd:.4f}")
print(f"  MACD Signal: {macd_signal:.4f}")
print(f"  MACD Histogram: {macd_hist:.4f}")
if macd > macd_signal:
    print("    → 🟢 MACD 在信号线上方 - 看涨")
else:
    print("    → 🔴 MACD 在信号线下方 - 看跌")

if macd_hist > 0:
    print(f"    → 🟢 柱状图为正 (+{macd_hist:.4f}) - 上涨动能")
else:
    print(f"    → 🔴 柱状图为负 ({macd_hist:.4f}) - 下跌动能")

# SMA 分析
print()
sma_5 = technical_data.get('sma_5', 0)
sma_20 = technical_data.get('sma_20', 0)
sma_50 = technical_data.get('sma_50', 0)
print(f"  SMA_5: ${sma_5:,.2f}")
print(f"  SMA_20: ${sma_20:,.2f}")
print(f"  SMA_50: ${sma_50:,.2f}")
print(f"  当前价格: ${current_price:,.2f}")

if current_price > sma_5 > sma_20 > sma_50:
    print("    → 🟢 完美多头排列 (价格 > SMA5 > SMA20 > SMA50)")
elif current_price < sma_5 < sma_20 < sma_50:
    print("    → 🔴 完美空头排列 (价格 < SMA5 < SMA20 < SMA50)")
else:
    print("    → ⚪ 无明确趋势排列")
    if current_price > sma_20:
        print(f"       价格在 SMA20 上方 (+{((current_price/sma_20)-1)*100:.2f}%)")
    else:
        print(f"       价格在 SMA20 下方 ({((current_price/sma_20)-1)*100:.2f}%)")

# 布林带分析
print()
bb_upper = technical_data.get('bb_upper', 0)
bb_lower = technical_data.get('bb_lower', 0)
bb_width = bb_upper - bb_lower if bb_upper and bb_lower else 0
bb_position = ((current_price - bb_lower) / bb_width * 100) if bb_width > 0 else 50

print(f"  BB Upper: ${bb_upper:,.2f}")
print(f"  BB Lower: ${bb_lower:,.2f}")
print(f"  BB Width: ${bb_width:,.2f} ({bb_width/current_price*100:.2f}%)")
print(f"  价格在带内位置: {bb_position:.1f}%")

if bb_position > 80:
    print("    → 🔴 接近上轨 (可能超买)")
elif bb_position < 20:
    print("    → 🟢 接近下轨 (可能超卖)")
else:
    print("    → ⚪ 带内中间区域")

# 2. 趋势分析
print()
print("[分析2] 趋势强度分析")
print("-" * 50)

trend = technical_data.get('overall_trend', 'N/A')
print(f"  整体趋势判断: {trend}")

# 计算近期价格变化
if len(bars) >= 10:
    price_10_bars_ago = float(bars[-10].close)
    price_change_10 = ((current_price - price_10_bars_ago) / price_10_bars_ago) * 100
    print(f"  近10根K线变化: {price_change_10:+.2f}%")

if len(bars) >= 20:
    price_20_bars_ago = float(bars[-20].close)
    price_change_20 = ((current_price - price_20_bars_ago) / price_20_bars_ago) * 100
    print(f"  近20根K线变化: {price_change_20:+.2f}%")

# 3. 情绪分析
print()
print("[分析3] 市场情绪分析")
print("-" * 50)

ls_ratio = sentiment_data.get('long_short_ratio', 1.0)
print(f"  多空比: {ls_ratio:.4f}")

if ls_ratio > 2.0:
    print("    → 🔴 极度看多 (逆向指标: 可能下跌)")
elif ls_ratio > 1.5:
    print("    → 🟡 偏多 (市场乐观)")
elif ls_ratio < 0.5:
    print("    → 🔴 极度看空 (逆向指标: 可能上涨)")
elif ls_ratio < 0.7:
    print("    → 🟡 偏空 (市场悲观)")
else:
    print("    → ⚪ 多空平衡")

# 4. 为什么 AI 返回 HOLD
print()
print("[分析4] AI 决策原因分析")
print("-" * 50)

print(f"  DeepSeek 完整理由:")
deepseek_reason = signal_deepseek.get('reason', 'N/A')
# 分行显示
for i in range(0, len(deepseek_reason), 80):
    print(f"    {deepseek_reason[i:i+80]}")

print()
print(f"  MultiAgent 辩论摘要:")
multi_summary = signal_multi.get('debate_summary', signal_multi.get('reason', 'N/A'))
for i in range(0, len(str(multi_summary)), 80):
    print(f"    {str(multi_summary)[i:i+80]}")

# 5. 触发交易的条件 (基于更新后的提示词)
print()
print("[分析5] 触发交易所需条件 (最新提示词)")
print("-" * 50)

print("  要触发 BUY 信号 (ANY 2 of these is sufficient):")
print(f"    • 价格在 SMA5/SMA20 上方 (当前: {'✅' if current_price > sma_5 and current_price > sma_20 else '❌'})")
print(f"    • RSI < 60 且不超买 (当前: {rsi:.2f}, {'✅' if rsi < 60 else '❌'})")
print(f"    • MACD 金叉或柱状图为正 (当前: {'✅' if macd > macd_signal or macd_hist > 0 else '❌'})")
print(f"    • 价格接近支撑或 BB 下轨 (当前位置: {bb_position:.1f}%)")
print()
print("  要触发 SELL 信号 (ANY 2 of these is sufficient):")
print(f"    • 价格在 SMA5/SMA20 下方 (当前: {'✅' if current_price < sma_5 and current_price < sma_20 else '❌'})")
print(f"    • RSI > 40 且显示弱势 (当前: {rsi:.2f}, {'✅' if rsi > 40 else '❌'})")
print(f"    • MACD 死叉或柱状图为负 (当前: {'✅' if macd < macd_signal or macd_hist < 0 else '❌'})")
print(f"    • 价格接近阻力或 BB 上轨 (当前位置: {bb_position:.1f}%)")
print()
print("  📌 提示词更新后，HOLD 仅在信号真正冲突时使用")
print(f"     当前 min_confidence_to_trade: {strategy_config.min_confidence_to_trade}")

# 6. 建议
print()
print("[分析6] 诊断建议")
print("-" * 50)

if final_signal == 'HOLD':
    print("  📌 当前市场状态分析:")

    # 综合评分
    bullish_score = 0
    bearish_score = 0

    # RSI
    if rsi < 40:
        bullish_score += 1
    elif rsi > 60:
        bearish_score += 1

    # MACD
    if macd > macd_signal:
        bullish_score += 1
    else:
        bearish_score += 1

    # Price vs SMA20
    if current_price > sma_20:
        bullish_score += 1
    else:
        bearish_score += 1

    # BB position
    if bb_position < 30:
        bullish_score += 1
    elif bb_position > 70:
        bearish_score += 1

    # Long/Short ratio (逆向)
    if ls_ratio > 2.0:
        bearish_score += 1
    elif ls_ratio < 0.7:
        bullish_score += 1

    print(f"    多头信号得分: {bullish_score}/5")
    print(f"    空头信号得分: {bearish_score}/5")

    if bullish_score > bearish_score + 1:
        print("    → 偏多头，但信号不够强烈")
    elif bearish_score > bullish_score + 1:
        print("    → 偏空头，但信号不够强烈")
    else:
        print("    → 多空信号混杂，无明确方向")

    print()
    print("  💡 HOLD 的常见原因:")
    print("    1. 技术指标处于中性区间 (RSI 30-70)")
    print("    2. 趋势不明确 (震荡整理)")
    print("    3. 多头和空头信号相互矛盾")
    print("    4. 市场波动率低，缺乏明确方向")
    print()
    print("  ⏳ 等待以下情况之一发生:")
    print("    • RSI 突破 30 或 70")
    print("    • MACD 形成明确金叉/死叉")
    print("    • 价格突破关键支撑/阻力位")
    print(f"      支撑: ${technical_data.get('support', 0):,.2f}")
    print(f"      阻力: ${technical_data.get('resistance', 0):,.2f}")

print()
print("=" * 70)
print("  深入分析完成")
print("=" * 70)
