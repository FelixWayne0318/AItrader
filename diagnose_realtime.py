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
if deepseek_signal == multi_signal:
    print("  ✅ Consensus: Both analyzers agree")
    consensus = True
    # 当共识时，使用 MultiAgent 的 SL/TP
    if signal_multi.get('stop_loss') and signal_multi.get('take_profit'):
        print(f"  📊 Using MultiAgent SL/TP:")
        print(f"     SL: ${signal_multi['stop_loss']:,.2f}")
        print(f"     TP: ${signal_multi['take_profit']:,.2f}")
else:
    print(f"  ⚠️ Divergence: DeepSeek={deepseek_signal}, MultiAgent={multi_signal}")
    print("     → Using DeepSeek signal (as per on_timer logic)")
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

# 2. 检查是否 HOLD
if deepseek_signal == 'HOLD':
    print("  ℹ️ Signal is HOLD → No action")
    would_trade = False
elif deepseek_signal in ['BUY', 'SELL']:
    print(f"  ✅ Signal is {deepseek_signal} → Actionable")
else:
    print(f"  ❌ Signal is {deepseek_signal} → Error state")
    would_trade = False

# 3. 计算仓位大小 (模拟 _calculate_position_size)
if would_trade and deepseek_signal in ['BUY', 'SELL']:
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

final_signal = deepseek_signal
print(f"  📊 Final Signal: {final_signal}")
print(f"  📊 Confidence: {confidence}")
print(f"  📊 Consensus: {'Yes' if consensus else 'No (Divergence)'}")
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
