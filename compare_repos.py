#!/usr/bin/env python3
"""
对比测试脚本：比较本仓库和参考仓库的信号生成流程
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 加载环境变量
from dotenv import load_dotenv
project_root = Path(__file__).parent
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)

print("=" * 70)
print("  仓库对比测试：信号生成流程")
print("=" * 70)
print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
print()

# =============================================================================
# 1. 获取市场数据 (共用)
# =============================================================================
print("[1/5] 获取市场数据...")

import requests

url = "https://fapi.binance.com/fapi/v1/klines"
params = {'symbol': 'BTCUSDT', 'interval': '15m', 'limit': 200}

try:
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    klines = response.json()
    current_price = float(klines[-1][4])
    print(f"  当前价格: ${current_price:,.2f}")
    print(f"  K线数量: {len(klines)}")
except Exception as e:
    print(f"  ❌ 获取数据失败: {e}")
    sys.exit(1)

print()

# =============================================================================
# 2. 初始化技术指标 (共用)
# =============================================================================
print("[2/5] 初始化技术指标...")

from decimal import Decimal
from indicators.technical_manager import TechnicalIndicatorManager

indicator_manager = TechnicalIndicatorManager(
    sma_periods=[5, 20],
    ema_periods=[12, 26],
    rsi_period=14,
    macd_fast=12,
    macd_slow=26,
    macd_signal=9,
    bb_period=20,
    bb_std=2.0,
)

# 喂入K线
for kline in klines:
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

technical_data = indicator_manager.get_technical_data(current_price)
print(f"  RSI: {technical_data.get('rsi', 0):.2f}")
print(f"  MACD: {technical_data.get('macd', 0):.4f}")
print(f"  Trend: {technical_data.get('overall_trend', 'N/A')}")
print(f"  指标初始化: {'✅' if indicator_manager.is_initialized() else '❌'}")

print()

# =============================================================================
# 3. 构建价格数据 (共用)
# =============================================================================
print("[3/5] 构建价格数据...")

kline_data = indicator_manager.get_kline_data(count=10)
bars = indicator_manager.recent_bars
if len(bars) >= 2:
    price_change = ((float(bars[-1].close) - float(bars[-2].close)) / float(bars[-2].close)) * 100
else:
    price_change = 0.0

price_data = {
    'price': current_price,
    'timestamp': datetime.now().isoformat(),
    'high': float(bars[-1].high) if bars else current_price,
    'low': float(bars[-1].low) if bars else current_price,
    'volume': float(bars[-1].volume) if bars else 0,
    'price_change': price_change,
    'kline_data': kline_data,
}

sentiment_data = {
    'long_short_ratio': 1.0,
    'long_account_pct': 50.0,
    'short_account_pct': 50.0,
    'source': 'default_neutral',
}

print(f"  价格变化: {price_change:+.2f}%")
print()

# =============================================================================
# 4. 参考仓库流程 (仅 DeepSeek)
# =============================================================================
print("=" * 70)
print("  📦 参考仓库流程 (Patrick-code-Bot/nautilus_AItrader)")
print("=" * 70)
print()
print("  特点: 仅使用 DeepSeek，无 MultiAgent")
print()

# 导入 DeepSeek 客户端
from utils.deepseek_client import DeepSeekAnalyzer

api_key = os.getenv('DEEPSEEK_API_KEY', '')
if not api_key:
    print("  ❌ 未找到 DEEPSEEK_API_KEY")
    sys.exit(1)

# 参考仓库使用 temperature=0.1
print("  [参考仓库配置]")
print("    temperature: 0.1 (原始值)")
print("    无 MultiAgent")
print()

print("  正在调用 DeepSeek API (模拟参考仓库)...")
start_time = time.time()

try:
    # 使用参考仓库的配置 (temperature=0.1)
    deepseek_ref = DeepSeekAnalyzer(
        api_key=api_key,
        model="deepseek-chat",
        temperature=0.1,  # 参考仓库原始值
    )

    signal_ref = deepseek_ref.analyze(
        price_data=price_data,
        technical_data=technical_data,
        sentiment_data=sentiment_data,
        current_position=None,
    )

    ref_time = time.time() - start_time

    print()
    print(f"  ⏱️ 耗时: {ref_time:.2f}秒")
    print(f"  🤖 DeepSeek 信号: {signal_ref.get('signal', 'ERROR')}")
    print(f"  📊 信心: {signal_ref.get('confidence', 'N/A')}")
    print(f"  📝 原因: {signal_ref.get('reason', 'N/A')[:100]}...")

    ref_signal = signal_ref.get('signal', 'ERROR')
    ref_confidence = signal_ref.get('confidence', 'N/A')

except Exception as e:
    print(f"  ❌ DeepSeek 调用失败: {e}")
    ref_signal = 'ERROR'
    ref_confidence = 'N/A'
    ref_time = 0

print()

# =============================================================================
# 5. 本仓库流程 (DeepSeek + MultiAgent)
# =============================================================================
print("=" * 70)
print("  📦 本仓库流程 (FelixWayne0318/AItrader)")
print("=" * 70)
print()
print("  特点: DeepSeek + MultiAgent (Bull/Bear 辩论)")
print()

print("  [本仓库配置]")
print("    temperature: 0.3 (已优化)")
print("    MultiAgent debate_rounds: 2")
print()

# 步骤 A: DeepSeek
print("  [Step A] 调用 DeepSeek API...")
start_time = time.time()

try:
    deepseek_ours = DeepSeekAnalyzer(
        api_key=api_key,
        model="deepseek-chat",
        temperature=0.3,  # 我们的优化值
    )

    signal_deepseek = deepseek_ours.analyze(
        price_data=price_data,
        technical_data=technical_data,
        sentiment_data=sentiment_data,
        current_position=None,
    )

    ds_time = time.time() - start_time

    print(f"    ⏱️ 耗时: {ds_time:.2f}秒")
    print(f"    🤖 DeepSeek: {signal_deepseek.get('signal', 'ERROR')} ({signal_deepseek.get('confidence', 'N/A')})")

except Exception as e:
    print(f"    ❌ DeepSeek 失败: {e}")
    signal_deepseek = {'signal': 'ERROR', 'confidence': 'LOW', 'reason': str(e)}
    ds_time = 0

print()

# 步骤 B: MultiAgent
print("  [Step B] 调用 MultiAgent API (Bull/Bear 辩论)...")
start_time = time.time()

try:
    from agents.multi_agent_analyzer import MultiAgentAnalyzer

    multi_agent = MultiAgentAnalyzer(
        api_key=api_key,
        model="deepseek-chat",
        temperature=0.3,
        debate_rounds=2,
    )

    print("    🐂 Bull Agent 分析中...")
    print("    🐻 Bear Agent 分析中...")
    print("    ⚖️ Judge 判断中...")

    signal_multi = multi_agent.analyze(
        symbol="BTCUSDT",
        technical_report=technical_data,
        sentiment_report=sentiment_data,
        current_position=None,
        price_data=price_data,
    )

    ma_time = time.time() - start_time

    print(f"    ⏱️ 耗时: {ma_time:.2f}秒")
    print(f"    🎯 MultiAgent: {signal_multi.get('signal', 'ERROR')} ({signal_multi.get('confidence', 'N/A')})")

except Exception as e:
    print(f"    ❌ MultiAgent 失败: {e}")
    import traceback
    traceback.print_exc()
    signal_multi = {'signal': 'ERROR', 'confidence': 'LOW', 'reason': str(e)}
    ma_time = 0

print()

# 步骤 C: 信号合并
print("  [Step C] 信号合并 (process_signals)...")

try:
    from strategy.trading_logic import process_signals

    final_signal, consensus, status_msg = process_signals(
        signal_deepseek=signal_deepseek,
        signal_multi=signal_multi,
        use_confidence_fusion=True,
        skip_on_divergence=True,
        logger=None,
    )

    print(f"    {status_msg}")
    print(f"    📊 最终信号: {final_signal.get('signal', 'ERROR')} ({final_signal.get('confidence', 'N/A')})")

    our_signal = final_signal.get('signal', 'ERROR')
    our_confidence = final_signal.get('confidence', 'N/A')
    our_total_time = ds_time + ma_time

except Exception as e:
    print(f"    ❌ 信号合并失败: {e}")
    import traceback
    traceback.print_exc()
    our_signal = signal_deepseek.get('signal', 'ERROR')
    our_confidence = signal_deepseek.get('confidence', 'N/A')
    our_total_time = ds_time

print()

# =============================================================================
# 6. 结果对比
# =============================================================================
print("=" * 70)
print("  📊 结果对比")
print("=" * 70)
print()

print(f"  {'项目':<20} {'参考仓库':<20} {'本仓库':<20}")
print(f"  {'-'*20} {'-'*20} {'-'*20}")
print(f"  {'最终信号':<20} {ref_signal:<20} {our_signal:<20}")
print(f"  {'信心等级':<20} {ref_confidence:<20} {our_confidence:<20}")
print(f"  {'API调用次数':<20} {'1':<20} {'6 (DeepSeek + 5×MultiAgent)':<20}")
print(f"  {'总耗时':<20} {f'{ref_time:.1f}秒':<20} {f'{our_total_time:.1f}秒':<20}")

print()
print("=" * 70)
print("  🔍 分析")
print("=" * 70)
print()

# 检查是否会发送 Telegram
would_send_telegram_ref = ref_signal in ['BUY', 'SELL']
would_send_telegram_ours = our_signal in ['BUY', 'SELL']

print(f"  参考仓库会发送 Telegram 信号: {'✅ 是' if would_send_telegram_ref else '❌ 否'}")
print(f"  本仓库会发送 Telegram 信号: {'✅ 是' if would_send_telegram_ours else '❌ 否'}")
print()

if not would_send_telegram_ours and would_send_telegram_ref:
    print("  ⚠️ 问题发现: 参考仓库会发送信号，但本仓库不会!")
    print()
    print("  可能原因:")
    print("    1. MultiAgent 返回不同信号，导致分歧")
    print("    2. 信号合并后变成 HOLD")
    print("    3. MultiAgent 失败，使用 DeepSeek 信号但仍是 HOLD")
elif not would_send_telegram_ours and not would_send_telegram_ref:
    print("  ℹ️ 两个仓库都不会发送信号 (都是 HOLD)")
    print()
    print("  这意味着:")
    print("    - AI 认为当前市场不适合交易")
    print("    - 不是代码问题，是 AI 判断结果")
elif would_send_telegram_ours:
    print("  ✅ 本仓库会发送信号")

print()
print("=" * 70)
print("  测试完成")
print("=" * 70)
