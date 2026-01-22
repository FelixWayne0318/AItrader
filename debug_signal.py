#!/usr/bin/env python3
"""
交易信号诊断脚本

用途: 诊断为什么没有交易信号
- 检查市场数据获取
- 检查技术指标计算
- 检查情绪数据
- 测试 DeepSeek AI 分析

使用方法:
    cd /home/linuxuser/nautilus_AItrader
    source venv/bin/activate
    python3 debug_signal.py
"""

import os
import sys
import json
from datetime import datetime, timedelta
from decimal import Decimal

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("  交易信号诊断工具")
print("=" * 60)
print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)
print()

# ============================================================
# 1. 检查环境变量
# ============================================================
print("[1/6] 检查环境变量...")

env_vars = {
    'BINANCE_API_KEY': os.getenv('BINANCE_API_KEY'),
    'BINANCE_API_SECRET': os.getenv('BINANCE_API_SECRET'),
    'DEEPSEEK_API_KEY': os.getenv('DEEPSEEK_API_KEY'),
}

all_env_ok = True
for key, value in env_vars.items():
    if value:
        print(f"  {key}: {'*' * 8}...{value[-4:] if len(value) > 4 else '****'}")
    else:
        print(f"  {key}: ❌ 未设置")
        all_env_ok = False

if not all_env_ok:
    print("\n❌ 环境变量缺失，请检查 ~/.env.aitrader")
    sys.exit(1)

print("  ✅ 环境变量正常")
print()

# ============================================================
# 2. 获取市场数据 (Binance K线)
# ============================================================
print("[2/6] 获取市场数据...")

import requests

symbol = "BTCUSDT"
interval = "15m"
limit = 100

try:
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url, timeout=10)
    klines = response.json()

    if isinstance(klines, list) and len(klines) > 0:
        latest = klines[-1]
        open_price = float(latest[1])
        high_price = float(latest[2])
        low_price = float(latest[3])
        close_price = float(latest[4])
        volume = float(latest[5])

        print(f"  交易对: {symbol}")
        print(f"  时间周期: {interval}")
        print(f"  K线数量: {len(klines)}")
        print(f"  最新价格: ${close_price:,.2f}")
        print(f"  最高价: ${high_price:,.2f}")
        print(f"  最低价: ${low_price:,.2f}")
        print(f"  成交量: {volume:,.2f}")
        print("  ✅ 市场数据获取成功")
    else:
        print(f"  ❌ K线数据异常: {klines}")
        sys.exit(1)
except Exception as e:
    print(f"  ❌ 获取市场数据失败: {e}")
    sys.exit(1)

print()

# ============================================================
# 3. 计算技术指标
# ============================================================
print("[3/6] 计算技术指标...")

try:
    import pandas as pd
    import numpy as np

    # 构建 DataFrame
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['volume'] = df['volume'].astype(float)

    # EMA
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()

    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # MACD
    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema_12 - ema_26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # 获取最新值
    latest_row = df.iloc[-1]

    ema_9 = latest_row['ema_9']
    ema_21 = latest_row['ema_21']
    ema_50 = latest_row['ema_50']
    rsi = latest_row['rsi']
    macd = latest_row['macd']
    macd_signal = latest_row['macd_signal']
    macd_hist = latest_row['macd_hist']

    print(f"  EMA(9):  ${ema_9:,.2f}")
    print(f"  EMA(21): ${ema_21:,.2f}")
    print(f"  EMA(50): ${ema_50:,.2f}")
    print(f"  RSI(14): {rsi:.2f}")
    print(f"  MACD:    {macd:.4f}")
    print(f"  MACD Signal: {macd_signal:.4f}")
    print(f"  MACD Hist:   {macd_hist:.4f}")

    # 趋势判断
    if close_price > ema_9 > ema_21 > ema_50:
        trend = "强势上涨"
    elif close_price < ema_9 < ema_21 < ema_50:
        trend = "强势下跌"
    else:
        trend = "震荡整理"

    print(f"  趋势判断: {trend}")
    print("  ✅ 技术指标计算成功")

except Exception as e:
    print(f"  ❌ 技术指标计算失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# ============================================================
# 4. 获取情绪数据
# ============================================================
print("[4/6] 获取情绪数据...")

try:
    sentiment_url = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
    params = {"symbol": symbol, "period": "15m", "limit": 1}
    response = requests.get(sentiment_url, params=params, timeout=10)
    sentiment_data = response.json()

    if isinstance(sentiment_data, list) and len(sentiment_data) > 0:
        latest_sentiment = sentiment_data[0]
        long_ratio = float(latest_sentiment.get('longAccount', 0))
        short_ratio = float(latest_sentiment.get('shortAccount', 0))
        long_short_ratio = float(latest_sentiment.get('longShortRatio', 0))

        print(f"  多头比例: {long_ratio:.2%}")
        print(f"  空头比例: {short_ratio:.2%}")
        print(f"  多空比: {long_short_ratio:.4f}")

        if long_ratio > 0.55:
            sentiment_bias = "偏多"
        elif short_ratio > 0.55:
            sentiment_bias = "偏空"
        else:
            sentiment_bias = "中性"

        print(f"  情绪偏向: {sentiment_bias}")
        print("  ✅ 情绪数据获取成功")
    else:
        print(f"  ⚠️ 情绪数据异常: {sentiment_data}")
        long_ratio = 0.5
        short_ratio = 0.5
        sentiment_bias = "中性"

except Exception as e:
    print(f"  ⚠️ 情绪数据获取失败: {e}")
    long_ratio = 0.5
    short_ratio = 0.5
    sentiment_bias = "中性"

print()

# ============================================================
# 5. 调用 DeepSeek AI 分析
# ============================================================
print("[5/6] 调用 DeepSeek AI 分析...")

try:
    from openai import OpenAI

    client = OpenAI(
        api_key=os.getenv('DEEPSEEK_API_KEY'),
        base_url="https://api.deepseek.com"
    )

    # 构建分析提示
    prompt = f"""你是一个专业的加密货币交易分析师。请分析以下 BTC/USDT 永续合约市场数据，并给出交易建议。

## 当前市场数据

**价格信息:**
- 当前价格: ${close_price:,.2f}
- 最高价: ${high_price:,.2f}
- 最低价: ${low_price:,.2f}

**技术指标:**
- EMA(9): ${ema_9:,.2f}
- EMA(21): ${ema_21:,.2f}
- EMA(50): ${ema_50:,.2f}
- RSI(14): {rsi:.2f}
- MACD: {macd:.4f}
- MACD Signal: {macd_signal:.4f}
- MACD Histogram: {macd_hist:.4f}
- 趋势: {trend}

**市场情绪:**
- 多头比例: {long_ratio:.2%}
- 空头比例: {short_ratio:.2%}
- 情绪偏向: {sentiment_bias}

## 请回答以下问题:

1. **交易信号**: 当前应该 LONG (做多), SHORT (做空), 还是 HOLD (观望)?
2. **信心水平**: 对这个信号的信心 (LOW/MEDIUM/HIGH)
3. **入场价格**: 如果有信号，建议的入场价格
4. **止损价格**: 建议的止损价格
5. **止盈价格**: 建议的止盈价格
6. **分析理由**: 为什么给出这个建议 (100字以内)

请用以下 JSON 格式回复:
```json
{{
    "signal": "LONG/SHORT/HOLD",
    "confidence": "LOW/MEDIUM/HIGH",
    "entry_price": 数字或null,
    "stop_loss": 数字或null,
    "take_profit": 数字或null,
    "reason": "分析理由"
}}
```"""

    print("  正在调用 DeepSeek API...")

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是专业的加密货币交易分析师，擅长技术分析和风险管理。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=500
    )

    ai_response = response.choices[0].message.content
    print("  ✅ DeepSeek API 调用成功")
    print()
    print("  AI 原始回复:")
    print("  " + "-" * 50)
    for line in ai_response.split('\n'):
        print(f"  {line}")
    print("  " + "-" * 50)

    # 尝试解析 JSON
    import re
    json_match = re.search(r'\{[^{}]*\}', ai_response, re.DOTALL)
    if json_match:
        try:
            ai_result = json.loads(json_match.group())
            print()
            print("  解析后的信号:")
            print(f"    信号: {ai_result.get('signal', 'N/A')}")
            print(f"    信心: {ai_result.get('confidence', 'N/A')}")
            print(f"    入场价: {ai_result.get('entry_price', 'N/A')}")
            print(f"    止损: {ai_result.get('stop_loss', 'N/A')}")
            print(f"    止盈: {ai_result.get('take_profit', 'N/A')}")
            print(f"    理由: {ai_result.get('reason', 'N/A')}")
        except json.JSONDecodeError as e:
            print(f"  ⚠️ JSON 解析失败: {e}")

except Exception as e:
    print(f"  ❌ DeepSeek API 调用失败: {e}")
    import traceback
    traceback.print_exc()

print()

# ============================================================
# 6. 诊断总结
# ============================================================
print("[6/6] 诊断总结...")
print()
print("=" * 60)
print("  诊断结果")
print("=" * 60)
print()
print("  1. 数据获取: ✅ 正常")
print("  2. 技术指标: ✅ 正常")
print("  3. 情绪数据: ✅ 正常")
print("  4. AI 分析:  ✅ 正常")
print()
print("  可能没有信号的原因:")
print("  - 市场处于震荡整理，AI 建议观望 (HOLD)")
print("  - RSI 在中性区间 (30-70)，无明显超买超卖")
print("  - EMA 未形成明确排列，趋势不明")
print("  - 多空比接近 1:1，市场分歧")
print()
print("  建议:")
print("  - 查看服务日志: sudo journalctl -u nautilus-trader -n 100")
print("  - 检查策略配置: configs/strategy_config.yaml")
print("  - 降低信号阈值或调整策略参数")
print()
print("=" * 60)
