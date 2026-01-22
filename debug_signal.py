#!/usr/bin/env python3
"""
交易信号诊断脚本 v2.0

用途: 使用真实组件诊断信号产生全流程
- 使用真实的 TechnicalManager 计算指标
- 使用真实的 SentimentDataFetcher 获取情绪数据
- 使用真实的 DeepSeekAnalyzer 分析 (阶段6)
- 使用真实的 MultiAgentAnalyzer 辩论 (阶段7)
- 检查共识/分歧逻辑

使用方法:
    cd /home/linuxuser/nautilus_AItrader
    source venv/bin/activate
    python3 debug_signal.py
"""

import os
import sys
import json
from datetime import datetime
from decimal import Decimal

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

print("=" * 70)
print("  交易信号诊断工具 v2.0 (使用真实组件)")
print("=" * 70)
print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
print()

# ============================================================
# 1. 检查环境变量
# ============================================================
print("[1/8] 检查环境变量...")

env_vars = {
    'BINANCE_API_KEY': os.getenv('BINANCE_API_KEY'),
    'BINANCE_API_SECRET': os.getenv('BINANCE_API_SECRET'),
    'DEEPSEEK_API_KEY': os.getenv('DEEPSEEK_API_KEY'),
}

all_env_ok = True
for key, value in env_vars.items():
    if value:
        masked = '*' * 8 + '...' + value[-4:] if len(value) > 4 else '****'
        print(f"  ✅ {key}: {masked}")
    else:
        print(f"  ❌ {key}: 未设置")
        all_env_ok = False

if not all_env_ok:
    print("\n❌ 环境变量缺失，请检查 ~/.env.aitrader")
    sys.exit(1)

print()

# ============================================================
# 2. 获取市场数据 (模拟 K 线数据)
# ============================================================
print("[2/8] 获取市场数据 (Binance Futures)...")

import requests

symbol = "BTCUSDT"
interval = "15m"
limit = 100

try:
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url, timeout=10)
    klines_raw = response.json()

    if isinstance(klines_raw, list) and len(klines_raw) > 0:
        print(f"  交易对: {symbol}")
        print(f"  时间周期: {interval}")
        print(f"  K线数量: {len(klines_raw)}")

        latest = klines_raw[-1]
        current_price = float(latest[4])  # close price
        print(f"  最新价格: ${current_price:,.2f}")
        print("  ✅ 市场数据获取成功")
    else:
        print(f"  ❌ K线数据异常: {klines_raw}")
        sys.exit(1)
except Exception as e:
    print(f"  ❌ 获取市场数据失败: {e}")
    sys.exit(1)

print()

# ============================================================
# 3. 使用真实的 TechnicalManager 计算指标
# ============================================================
print("[3/8] 使用 TechnicalManager 计算技术指标...")

try:
    from indicators.technical_manager import TechnicalManager

    # 初始化技术指标管理器
    tech_manager = TechnicalManager(
        ema_periods=[9, 21, 50],
        rsi_period=14,
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,
        atr_period=14,
        lookback_bars=100,
    )

    # 转换 K 线数据为管理器需要的格式
    import pandas as pd

    df = pd.DataFrame(klines_raw, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])

    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)

    # 模拟添加 K 线到管理器
    for _, row in df.iterrows():
        # 创建简单的 bar 对象模拟
        class MockBar:
            def __init__(self, o, h, l, c, v):
                self.open = Decimal(str(o))
                self.high = Decimal(str(h))
                self.low = Decimal(str(l))
                self.close = Decimal(str(c))
                self.volume = Decimal(str(v))

        bar = MockBar(row['open'], row['high'], row['low'], row['close'], row['volume'])
        tech_manager.update(bar)

    # 获取技术数据
    technical_data = tech_manager.get_technical_data(current_price)

    print(f"  EMA(9):  ${technical_data.get('ema_9', 0):,.2f}")
    print(f"  EMA(21): ${technical_data.get('ema_21', 0):,.2f}")
    print(f"  EMA(50): ${technical_data.get('ema_50', 0):,.2f}")
    print(f"  RSI(14): {technical_data.get('rsi', 0):.2f}")
    print(f"  MACD:    {technical_data.get('macd', 0):.4f}")
    print(f"  MACD Signal: {technical_data.get('macd_signal', 0):.4f}")
    print(f"  MACD Hist:   {technical_data.get('macd_hist', 0):.4f}")
    print(f"  ATR:     {technical_data.get('atr', 0):.2f}")
    print(f"  支撑位:  ${technical_data.get('support', 0):,.2f}")
    print(f"  阻力位:  ${technical_data.get('resistance', 0):,.2f}")
    print(f"  趋势判断: {technical_data.get('overall_trend', 'N/A')}")
    print("  ✅ TechnicalManager 指标计算成功")

except Exception as e:
    print(f"  ❌ TechnicalManager 初始化/计算失败: {e}")
    import traceback
    traceback.print_exc()
    # 使用简化版本作为备份
    print("  ⚠️ 使用简化版本计算...")
    technical_data = {
        'ema_9': current_price * 0.999,
        'ema_21': current_price * 0.998,
        'ema_50': current_price * 0.995,
        'rsi': 50.0,
        'macd': 0.0,
        'macd_signal': 0.0,
        'macd_hist': 0.0,
        'atr': current_price * 0.01,
        'support': current_price * 0.98,
        'resistance': current_price * 1.02,
        'overall_trend': '震荡整理',
    }

print()

# ============================================================
# 4. 使用真实的 SentimentDataFetcher 获取情绪数据
# ============================================================
print("[4/8] 使用 SentimentDataFetcher 获取情绪数据...")

try:
    from utils.sentiment_client import SentimentDataFetcher

    sentiment_fetcher = SentimentDataFetcher(
        lookback_hours=4,
        timeframe="15m",
    )

    sentiment_data = sentiment_fetcher.fetch()

    if sentiment_data:
        print(f"  多头比例: {sentiment_data.get('positive_ratio', 0):.2%}")
        print(f"  空头比例: {sentiment_data.get('negative_ratio', 0):.2%}")
        print(f"  多空比:   {sentiment_data.get('long_short_ratio', 0):.4f}")
        print(f"  净情绪:   {sentiment_data.get('net_sentiment', 0):.4f}")
        print(f"  数据来源: {sentiment_data.get('source', 'N/A')}")
        print("  ✅ SentimentDataFetcher 数据获取成功")
    else:
        print("  ⚠️ 情绪数据为空，使用中性默认值")
        sentiment_data = {
            'positive_ratio': 0.5,
            'negative_ratio': 0.5,
            'net_sentiment': 0.0,
            'long_short_ratio': 1.0,
            'source': 'default_neutral',
        }

except Exception as e:
    print(f"  ❌ SentimentDataFetcher 失败: {e}")
    sentiment_data = {
        'positive_ratio': 0.5,
        'negative_ratio': 0.5,
        'net_sentiment': 0.0,
        'long_short_ratio': 1.0,
        'source': 'fallback',
    }

print()

# ============================================================
# 5. 构建价格数据
# ============================================================
print("[5/8] 构建价格数据...")

# 获取最近10根K线用于AI分析
kline_data = []
for kline in klines_raw[-10:]:
    kline_data.append({
        'open': float(kline[1]),
        'high': float(kline[2]),
        'low': float(kline[3]),
        'close': float(kline[4]),
        'volume': float(kline[5]),
    })

price_data = {
    'price': current_price,
    'timestamp': datetime.now().isoformat(),
    'high': float(klines_raw[-1][2]),
    'low': float(klines_raw[-1][3]),
    'volume': float(klines_raw[-1][5]),
    'price_change': ((current_price - float(klines_raw[-2][4])) / float(klines_raw[-2][4])) * 100,
    'kline_data': kline_data,
}

print(f"  当前价格: ${price_data['price']:,.2f}")
print(f"  最高价:   ${price_data['high']:,.2f}")
print(f"  最低价:   ${price_data['low']:,.2f}")
print(f"  价格变化: {price_data['price_change']:.2f}%")
print(f"  K线数据:  {len(price_data['kline_data'])} 根")
print("  ✅ 价格数据构建成功")
print()

# ============================================================
# 6. 使用真实的 DeepSeekAnalyzer (阶段6)
# ============================================================
print("[6/8] 阶段6: 使用 DeepSeekAnalyzer 分析...")
print("-" * 70)

try:
    from utils.deepseek_client import DeepSeekAnalyzer

    deepseek = DeepSeekAnalyzer(
        api_key=os.getenv('DEEPSEEK_API_KEY'),
        model="deepseek-chat",
        temperature=0.3,
        max_retries=3,
    )

    print("  正在调用 DeepSeek API...")

    signal_deepseek = deepseek.analyze(
        price_data=price_data,
        technical_data=technical_data,
        sentiment_data=sentiment_data,
        current_position=None,  # 假设无持仓
    )

    print()
    print("  🤖 DeepSeek 分析结果:")
    print(f"     信号:     {signal_deepseek.get('signal', 'N/A')}")
    print(f"     信心:     {signal_deepseek.get('confidence', 'N/A')}")
    print(f"     止损:     {signal_deepseek.get('stop_loss', 'N/A')}")
    print(f"     止盈:     {signal_deepseek.get('take_profit', 'N/A')}")
    print(f"     理由:     {signal_deepseek.get('reason', 'N/A')[:100]}...")
    print("  ✅ DeepSeekAnalyzer 分析成功")

except Exception as e:
    print(f"  ❌ DeepSeekAnalyzer 失败: {e}")
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

# ============================================================
# 7. 使用真实的 MultiAgentAnalyzer (阶段7)
# ============================================================
print("[7/8] 阶段7: 使用 MultiAgentAnalyzer 辩论...")
print("-" * 70)

try:
    from agents.multi_agent_analyzer import MultiAgentAnalyzer

    multi_agent = MultiAgentAnalyzer(
        api_key=os.getenv('DEEPSEEK_API_KEY'),
        model="deepseek-chat",
        temperature=0.3,
        debate_rounds=2,
    )

    print("  正在进行 Bull/Bear 辩论...")
    print("  🐂 Bull Agent (看多派) 分析中...")
    print("  🐻 Bear Agent (看空派) 分析中...")
    print("  ⚖️ Judge Agent (裁判) 判断中...")

    signal_multi = multi_agent.analyze(
        symbol="BTCUSDT",
        technical_report=technical_data,
        sentiment_report=sentiment_data,
        current_position=None,
        price_data=price_data,
    )

    print()
    print("  🎯 MultiAgent 辩论结果:")
    print(f"     信号:     {signal_multi.get('signal', 'N/A')}")
    print(f"     信心:     {signal_multi.get('confidence', 'N/A')}")
    print(f"     止损:     {signal_multi.get('stop_loss', 'N/A')}")
    print(f"     止盈:     {signal_multi.get('take_profit', 'N/A')}")
    if signal_multi.get('debate_summary'):
        print(f"     辩论摘要: {signal_multi.get('debate_summary', '')[:150]}...")
    print("  ✅ MultiAgentAnalyzer 辩论成功")

except Exception as e:
    print(f"  ❌ MultiAgentAnalyzer 失败: {e}")
    import traceback
    traceback.print_exc()
    signal_multi = {
        'signal': 'ERROR',
        'confidence': 'LOW',
        'reason': str(e),
        'stop_loss': None,
        'take_profit': None,
    }

print()

# ============================================================
# 8. 共识检查和最终决策
# ============================================================
print("[8/8] 共识检查和最终决策...")
print("-" * 70)

deepseek_signal = signal_deepseek.get('signal', 'ERROR')
multi_signal = signal_multi.get('signal', 'ERROR')

print(f"  DeepSeek 信号:   {deepseek_signal}")
print(f"  MultiAgent 信号: {multi_signal}")
print()

if deepseek_signal == multi_signal:
    print("  ✅ 共识达成: 两个分析器意见一致")
    consensus = True

    # 检查是否使用 MultiAgent 的 SL/TP
    if signal_multi.get('stop_loss') and signal_multi.get('take_profit'):
        print(f"  📊 将使用 MultiAgent 的 SL/TP:")
        print(f"     止损: ${signal_multi.get('stop_loss'):,.2f}")
        print(f"     止盈: ${signal_multi.get('take_profit'):,.2f}")
else:
    print("  ⚠️ 分歧: 两个分析器意见不一致")
    print(f"     → 将使用 DeepSeek 的信号 (更保守)")
    consensus = False

print()

# ============================================================
# 最终诊断总结
# ============================================================
print("=" * 70)
print("  诊断总结")
print("=" * 70)
print()

final_signal = deepseek_signal  # 最终使用 DeepSeek 信号

print(f"  📊 最终信号: {final_signal}")
print(f"  📊 信心水平: {signal_deepseek.get('confidence', 'N/A')}")
print(f"  📊 共识状态: {'✅ 一致' if consensus else '⚠️ 分歧'}")
print()

if final_signal == 'HOLD':
    print("  🔍 没有交易信号的原因:")
    print(f"     - AI 建议观望 (HOLD)")
    print(f"     - DeepSeek 理由: {signal_deepseek.get('reason', 'N/A')[:80]}...")
    if signal_multi.get('debate_summary'):
        print(f"     - 辩论结论: {signal_multi.get('debate_summary', '')[:80]}...")
    print()
    print("  💡 这是市场原因，不是代码问题")
    print("     - 等待更好的入场时机")
    print("     - 或调整策略参数降低阈值")
elif final_signal in ['BUY', 'SELL']:
    print(f"  🚀 有交易信号: {final_signal}")
    print(f"     - 如果服务没有执行，请检查:")
    print(f"       1. 最低信心要求 (min_confidence)")
    print(f"       2. 交易是否暂停 (is_trading_paused)")
    print(f"       3. 仓位计算是否为 0")
else:
    print(f"  ❌ 异常信号: {final_signal}")
    print("     - 请检查 API 连接和配置")

print()
print("=" * 70)
print("  诊断完成")
print("=" * 70)
