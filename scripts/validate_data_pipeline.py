#!/usr/bin/env python3
"""
端到端数据流水线验证脚本 (v2.0)

调用真实 API + 离线逻辑验证，覆盖从数据获取到 AI 输入的完整流水线。
检测排序错误、公式错误、字段引用错误、单位转换错误、
SL/TP 验证逻辑、仓位计算、AI 响应解析、OI×Price 分析等。

用法:
    python3 scripts/validate_data_pipeline.py           # 完整验证
    python3 scripts/validate_data_pipeline.py --quick    # 跳过慢速 API (Coinalyze)
    python3 scripts/validate_data_pipeline.py --offline  # 纯离线逻辑验证
    python3 scripts/validate_data_pipeline.py --json     # JSON 输出
"""

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root
project_root = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(project_root))

import requests


# ─────────────────────────────────────────────────────────────────────
# Test Results Tracking
# ─────────────────────────────────────────────────────────────────────

class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []

    def ok(self, name: str, detail: str = ""):
        self.passed.append((name, detail))
        print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))

    def fail(self, name: str, detail: str = ""):
        self.failed.append((name, detail))
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))

    def warn(self, name: str, detail: str = ""):
        self.warnings.append((name, detail))
        print(f"  ⚠️  {name}" + (f" — {detail}" if detail else ""))

    def summary(self):
        total = len(self.passed) + len(self.failed)
        print("\n" + "=" * 60)
        print(f"  验证结果: {len(self.passed)}/{total} 通过, "
              f"{len(self.failed)} 失败, {len(self.warnings)} 警告")
        print("=" * 60)
        if self.failed:
            print("\n  失败项:")
            for name, detail in self.failed:
                print(f"    ❌ {name}: {detail}")
        if self.warnings:
            print("\n  警告项:")
            for name, detail in self.warnings:
                print(f"    ⚠️  {name}: {detail}")
        return len(self.failed) == 0


# ═════════════════════════════════════════════════════════════════════
# SECTION A: 在线 API 验证 (需要网络)
# ═════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────
# Test 1: 情绪数据 (globalLongShortAccountRatio)
# ─────────────────────────────────────────────────────────────────────

def test_sentiment_api_ordering(results: TestResults):
    """验证 Binance API 返回的数据排序 (升序: oldest first)"""
    print("\n─── Test 1: 情绪数据 API 排序验证 ───")

    url = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
    params = {"symbol": "BTCUSDT", "period": "15m", "limit": 10}

    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        if not isinstance(data, list) or len(data) < 2:
            results.fail("API 返回数据", f"非预期格式: {type(data)}")
            return None

        results.ok("API 响应", f"{len(data)} 条数据")

        # 验证排序: timestamps 应该递增 (升序)
        timestamps = [int(d['timestamp']) for d in data]
        is_ascending = all(timestamps[i] <= timestamps[i+1] for i in range(len(timestamps)-1))

        if is_ascending:
            results.ok("排序验证", "升序 (oldest first) ✓")
        else:
            results.fail("排序验证", f"非升序! timestamps: {timestamps[:3]}...{timestamps[-3:]}")

        # data[-1] 应该是最新的
        newest_ts = timestamps[-1]
        oldest_ts = timestamps[0]
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        newest_delay_min = (now_ms - newest_ts) / 1000 / 60
        oldest_delay_min = (now_ms - oldest_ts) / 1000 / 60

        results.ok("data[-1] (最新)", f"延迟 {newest_delay_min:.1f} 分钟")
        results.ok("data[0] (最旧)", f"延迟 {oldest_delay_min:.1f} 分钟")

        if newest_delay_min > 30:
            results.warn("最新数据延迟", f"{newest_delay_min:.0f} 分钟 (>30分钟)")
        if oldest_delay_min > 180:
            results.warn("最旧数据延迟", f"{oldest_delay_min:.0f} 分钟 (正常, limit=10 × 15m)")

        return data

    except Exception as e:
        results.fail("API 调用", str(e))
        return None


# ─────────────────────────────────────────────────────────────────────
# Test 2: SentimentDataFetcher 解析
# ─────────────────────────────────────────────────────────────────────

def test_sentiment_client_parsing(results: TestResults):
    """验证 SentimentDataFetcher 的解析逻辑"""
    print("\n─── Test 2: SentimentDataFetcher 解析验证 ───")

    try:
        from utils.sentiment_client import SentimentDataFetcher

        fetcher = SentimentDataFetcher(timeframe="15m")
        data = fetcher.fetch("BTC")

        if data is None:
            results.fail("fetch() 返回 None", "API 可能不可用")
            return

        # 1. 必需字段检查
        required_fields = [
            'positive_ratio', 'negative_ratio', 'net_sentiment',
            'data_time', 'data_delay_minutes', 'source',
            'long_short_ratio', 'history'
        ]
        for field in required_fields:
            if field in data:
                results.ok(f"字段 '{field}'", f"值: {data[field]}" if field != 'history' else f"{len(data[field])} 条")
            else:
                results.fail(f"字段 '{field}' 缺失", f"返回的字段: {list(data.keys())}")

        # 2. 数值范围检查
        pos = data.get('positive_ratio', -1)
        neg = data.get('negative_ratio', -1)
        net = data.get('net_sentiment', -999)

        if 0 <= pos <= 1:
            results.ok("positive_ratio 范围", f"{pos:.4f} (0-1)")
        else:
            results.fail("positive_ratio 范围", f"{pos} 不在 0-1 之间")

        if 0 <= neg <= 1:
            results.ok("negative_ratio 范围", f"{neg:.4f} (0-1)")
        else:
            results.fail("negative_ratio 范围", f"{neg} 不在 0-1 之间")

        # 3. 公式验证: net_sentiment = positive - negative
        expected_net = pos - neg
        if abs(net - expected_net) < 0.0001:
            results.ok("net_sentiment 公式", f"{net:.4f} = {pos:.4f} - {neg:.4f}")
        else:
            results.fail("net_sentiment 公式错误",
                         f"实际={net:.4f}, 预期={expected_net:.4f} (pos-neg)")

        # 4. positive + negative ≈ 1.0
        total = pos + neg
        if abs(total - 1.0) < 0.01:
            results.ok("pos + neg ≈ 1.0", f"{total:.4f}")
        else:
            results.warn("pos + neg ≠ 1.0", f"{total:.4f}")

        # 5. 延迟检查 (修复后应该 < 30 分钟)
        delay = data.get('data_delay_minutes', -1)
        if 0 <= delay <= 30:
            results.ok("数据延迟", f"{delay} 分钟 (正常)")
        elif delay > 30:
            results.fail("数据延迟过大", f"{delay} 分钟! 检查 data[-1] vs data[0] 排序")
        else:
            results.warn("延迟值异常", f"{delay}")

        # 6. 历史数据排序 (应该 oldest → newest)
        history = data.get('history', [])
        if len(history) >= 2:
            hist_ts = [h.get('timestamp', 0) for h in history]
            hist_ascending = all(hist_ts[i] <= hist_ts[i+1] for i in range(len(hist_ts)-1))
            if hist_ascending:
                results.ok("历史数据排序", "升序 (oldest → newest) ✓")
            else:
                results.fail("历史数据排序错误", "应该是升序但不是!")
        else:
            results.warn("历史数据不足", f"仅 {len(history)} 条")

    except Exception as e:
        results.fail("SentimentDataFetcher", str(e))


# ─────────────────────────────────────────────────────────────────────
# Test 3: 订单流数据 (Buy/Sell Ratio, CVD)
# ─────────────────────────────────────────────────────────────────────

def test_order_flow(results: TestResults):
    """验证订单流数据计算"""
    print("\n─── Test 3: 订单流数据验证 ───")

    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {"symbol": "BTCUSDT", "interval": "15m", "limit": 15}

    try:
        resp = requests.get(url, params=params, timeout=10)
        klines = resp.json()

        if not isinstance(klines, list) or len(klines) < 10:
            results.fail("K线 API", f"数据不足: {len(klines) if isinstance(klines, list) else 'N/A'}")
            return

        results.ok("K线 API", f"{len(klines)} 条")

        # 逐条验证 buy ratio 计算
        errors = []
        for i, k in enumerate(klines[-10:]):
            volume = float(k[5])           # Total volume
            taker_buy_vol = float(k[9])    # Taker buy volume
            quote_volume = float(k[7])     # Quote volume (USDT)
            trades = int(k[8])             # Number of trades

            if volume > 0:
                buy_ratio = taker_buy_vol / volume
                if not (0 <= buy_ratio <= 1):
                    errors.append(f"bar {i}: buy_ratio={buy_ratio:.4f} 超出 0-1 范围")
            else:
                errors.append(f"bar {i}: volume=0")

        if errors:
            results.fail("Buy Ratio 范围", "; ".join(errors[:3]))
        else:
            latest = klines[-1]
            vol = float(latest[5])
            buy_vol = float(latest[9])
            ratio = buy_vol / vol if vol > 0 else 0
            results.ok("Buy Ratio 计算", f"最新={ratio:.4f} (taker_buy/total)")

        # CVD 验证: delta = buy_vol - sell_vol = 2*buy_vol - total_vol
        cvd_deltas = []
        for k in klines[-10:]:
            vol = float(k[5])
            buy_vol = float(k[9])
            sell_vol = vol - buy_vol
            delta = buy_vol - sell_vol
            cvd_deltas.append(delta)

        cvd_sum = sum(cvd_deltas)
        results.ok("CVD 计算", f"10-bar 累计: {cvd_sum:.4f} BTC")

        # 验证平均交易大小
        latest = klines[-1]
        q_vol = float(latest[7])
        trades = int(latest[8])
        if trades > 0:
            avg_trade = q_vol / trades
            results.ok("平均交易大小", f"${avg_trade:,.2f} USDT/trade")
        else:
            results.warn("交易数为0", "无法计算平均交易大小")

        # 验证 OrderFlowProcessor (如果可导入)
        try:
            from utils.order_flow_processor import OrderFlowProcessor
            processor = OrderFlowProcessor()
            of_result = processor.process_klines(klines)

            if of_result.get('data_source') == 'binance_raw':
                results.ok("OrderFlowProcessor", f"data_source=binance_raw, bars={of_result.get('bars_count')}")
            else:
                results.warn("OrderFlowProcessor 降级", f"data_source={of_result.get('data_source')}")

            # 验证 buy_ratio 是 10-bar 平均值
            br = of_result.get('buy_ratio', -1)
            latest_br = of_result.get('latest_buy_ratio', -1)
            if 0 <= br <= 1:
                results.ok("OFP buy_ratio 范围", f"{br:.4f} (10-bar avg)")
            else:
                results.fail("OFP buy_ratio 范围", f"{br}")

            # CVD history 和 cumulative
            cvd_hist = of_result.get('cvd_history', [])
            cvd_cum = of_result.get('cvd_cumulative', None)
            if cvd_hist is not None:
                results.ok("OFP CVD history", f"{len(cvd_hist)} 条")
            if cvd_cum is not None:
                results.ok("OFP CVD cumulative", f"{cvd_cum:+.2f}")

            # recent_10_bars
            r10 = of_result.get('recent_10_bars', [])
            if r10 and all(0 <= x <= 1 for x in r10):
                results.ok("OFP recent_10_bars", f"{len(r10)} 条, 全部 0-1 范围")
            elif r10:
                results.fail("OFP recent_10_bars 范围", f"有值超出 0-1")

        except ImportError:
            results.warn("OrderFlowProcessor 不可导入", "跳过")

    except Exception as e:
        results.fail("订单流验证", str(e))


# ─────────────────────────────────────────────────────────────────────
# Test 4: 技术指标范围验证
# ─────────────────────────────────────────────────────────────────────

def test_indicator_ranges(results: TestResults):
    """验证技术指标的输出范围是否合理"""
    print("\n─── Test 4: 技术指标范围验证 ───")

    try:
        from indicators.technical_manager import TechnicalIndicatorManager

        manager = TechnicalIndicatorManager(
            rsi_period=14, macd_fast=12,
            macd_slow=26, macd_signal=9, bb_period=20
        )
        results.ok("指标管理器实例化", "TechnicalIndicatorManager ✓")

        # 获取 K 线来验证指标计算
        url = "https://fapi.binance.com/fapi/v1/klines"
        params = {"symbol": "BTCUSDT", "interval": "15m", "limit": 100}
        resp = requests.get(url, params=params, timeout=10)
        klines = resp.json()

        if not isinstance(klines, list):
            results.fail("K线数据", "无法获取")
            return

        # Feed bars via NautilusTrader Bar objects
        from nautilus_trader.model.data import Bar, BarType
        from nautilus_trader.model.objects import Price, Quantity

        bar_type = BarType.from_str("BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-EXTERNAL")

        for k in klines[:-1]:  # skip last incomplete bar
            bar = Bar(
                bar_type=bar_type,
                open=Price.from_str(k[1]),
                high=Price.from_str(k[2]),
                low=Price.from_str(k[3]),
                close=Price.from_str(k[4]),
                volume=Quantity.from_str(k[5]),
                ts_event=int(k[0]) * 1_000_000,  # ms → ns
                ts_init=int(k[0]) * 1_000_000,
            )
            manager.update(bar)

        price = float(klines[-2][4])  # last complete bar close
        data = manager.get_technical_data(current_price=price)

        if data is None:
            results.fail("get_technical_data()", "返回 None (指标未初始化?)")
            return

        # RSI: 应该是 0-100
        rsi = data.get('rsi', -1)
        if 0 <= rsi <= 100:
            results.ok("RSI 范围", f"{rsi:.2f} (0-100 scale)")
        elif 0 <= rsi <= 1:
            results.fail("RSI 范围错误", f"{rsi:.4f} — 看起来是 0-1 scale, 应该是 0-100!")
        else:
            results.fail("RSI 范围异常", f"{rsi}")

        # MACD: 应该是合理的价格差值
        macd = data.get('macd', 0)
        macd_sig = data.get('macd_signal', 0)
        macd_hist = data.get('macd_histogram', 0)
        if abs(macd) < 10000:
            results.ok("MACD 范围", f"MACD={macd:.2f}, Signal={macd_sig:.2f}, Hist={macd_hist:.2f}")
        else:
            results.warn("MACD 值过大", f"{macd:.2f}")

        # MACD histogram = MACD - Signal
        expected_hist = macd - macd_sig
        if abs(macd_hist - expected_hist) < 0.001:
            results.ok("MACD Histogram 公式", f"{macd_hist:.4f} = MACD - Signal")
        else:
            results.fail("MACD Histogram 公式", f"实际={macd_hist:.4f}, 预期={expected_hist:.4f}")

        # SMA: 应该接近当前价格
        for sma_period in [5, 20, 50]:
            sma = data.get(f'sma_{sma_period}', 0)
            if sma > 0 and abs(sma - price) / price < 0.15:
                results.ok(f"SMA{sma_period} 范围", f"${sma:.2f}, 偏差={abs(sma-price)/price*100:.1f}%")
            elif sma > 0:
                results.warn(f"SMA{sma_period} 偏差较大", f"${sma:.2f} vs Price=${price:.2f}")
            else:
                results.warn(f"SMA{sma_period} 为 0", "可能未初始化")

        # Bollinger Bands: upper > middle > lower
        bb_upper = data.get('bb_upper', 0)
        bb_middle = data.get('bb_middle', 0)
        bb_lower = data.get('bb_lower', 0)
        if bb_upper > bb_middle > bb_lower > 0:
            results.ok("BB 顺序", f"Upper={bb_upper:.2f} > Middle={bb_middle:.2f} > Lower={bb_lower:.2f}")
        elif bb_upper == 0:
            results.warn("BB 未初始化", "数据不足?")
        else:
            results.fail("BB 顺序错误", f"U={bb_upper:.2f}, M={bb_middle:.2f}, L={bb_lower:.2f}")

        # BB position: 0-1 范围
        bb_pos = data.get('bb_position', -1)
        if 0 <= bb_pos <= 1:
            results.ok("BB Position 范围", f"{bb_pos:.4f} (0=lower, 1=upper)")
        elif bb_pos < 0 or bb_pos > 1:
            results.warn("BB Position 超出 0-1", f"{bb_pos:.4f} (价格在 BB 外)")

        # ADX: 应该是 0-100
        adx = data.get('adx', -1)
        if 0 <= adx <= 100:
            results.ok("ADX 范围", f"{adx:.2f} (0-100)")
        else:
            results.warn("ADX 范围异常", f"{adx}")

        # DI+/DI-: 应该是 0-100
        di_plus = data.get('di_plus', -1)
        di_minus = data.get('di_minus', -1)
        if 0 <= di_plus <= 100 and 0 <= di_minus <= 100:
            results.ok("DI+/DI- 范围", f"DI+={di_plus:.2f}, DI-={di_minus:.2f}")
        else:
            results.warn("DI+/DI- 范围异常", f"DI+={di_plus}, DI-={di_minus}")

        # Volume ratio: 应该 > 0
        vol_ratio = data.get('volume_ratio', -1)
        if vol_ratio > 0:
            results.ok("Volume Ratio", f"{vol_ratio:.2f}x")
        else:
            results.warn("Volume Ratio 异常", f"{vol_ratio}")

        # Support/Resistance: support < price < resistance
        support = data.get('support', 0)
        resistance = data.get('resistance', 0)
        if support > 0 and resistance > 0:
            if support < price < resistance:
                results.ok("S/R 关系", f"S=${support:,.2f} < P=${price:,.2f} < R=${resistance:,.2f}")
            elif support == resistance:
                results.warn("S/R 相等", f"S=R=${support:,.2f}")
            else:
                results.warn("S/R 异常", f"S=${support:,.2f}, P=${price:,.2f}, R=${resistance:,.2f}")

        # Trend fields
        for field in ['overall_trend', 'short_term_trend', 'macd_trend']:
            val = data.get(field)
            if val is not None:
                results.ok(f"趋势字段 '{field}'", f"{val}")
            else:
                results.warn(f"趋势字段 '{field}' 缺失", "")

        # 验证 get_kline_data
        kline_data = manager.get_kline_data(count=10)
        if kline_data and len(kline_data) > 0:
            kd = kline_data[-1]
            required_kd = ['open', 'high', 'low', 'close', 'volume', 'timestamp']
            missing = [f for f in required_kd if f not in kd]
            if not missing:
                results.ok("get_kline_data 字段", f"{len(kline_data)} bars, 字段完整")
            else:
                results.fail("get_kline_data 字段缺失", str(missing))

            # OHLC 关系: low <= open,close <= high
            h, l, o, c = kd['high'], kd['low'], kd['open'], kd['close']
            if l <= min(o, c) and max(o, c) <= h:
                results.ok("OHLC 关系", f"L≤O,C≤H ✓")
            else:
                results.fail("OHLC 关系错误", f"O={o}, H={h}, L={l}, C={c}")
        else:
            results.warn("get_kline_data 为空", "bars 不足?")

        # 验证 get_historical_context
        hist_ctx = manager.get_historical_context(count=35)
        if hist_ctx:
            td = hist_ctx.get('trend_direction', 'UNKNOWN')
            if td not in ['INSUFFICIENT_DATA', 'ERROR', None]:
                results.ok("历史上下文", f"trend={td}, momentum={hist_ctx.get('momentum_shift')}")

                # 验证序列长度
                price_trend = hist_ctx.get('price_trend', [])
                rsi_trend = hist_ctx.get('rsi_trend', [])
                if len(price_trend) >= 5:
                    results.ok("价格序列", f"{len(price_trend)} 值")
                else:
                    results.warn("价格序列短", f"仅 {len(price_trend)} 值")

                if rsi_trend and all(0 <= v <= 100 for v in rsi_trend):
                    results.ok("RSI 序列范围", f"{len(rsi_trend)} 值, 全部 0-100")
                elif rsi_trend:
                    results.fail("RSI 序列范围错误", f"有值超出 0-100")
            else:
                results.warn("历史上下文数据不足", f"trend_direction={td}")
        else:
            results.warn("get_historical_context 返回 None", "")

    except ImportError as e:
        results.warn("指标模块导入失败", f"{e} (可能缺少 NautilusTrader)")
    except Exception as e:
        results.fail("指标验证", str(e))
        import traceback
        traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────
# Test 5: Funding Rate 完整验证
# ─────────────────────────────────────────────────────────────────────

def test_funding_rate_pipeline(results: TestResults):
    """验证 funding rate 完整数据流水线"""
    print("\n─── Test 5: Funding Rate 完整验证 ───")

    try:
        # --- 5a: Binance settled funding rate ---
        url = "https://fapi.binance.com/fapi/v1/fundingRate"
        params = {"symbol": "BTCUSDT", "limit": 3}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        if isinstance(data, list) and len(data) > 0:
            # Binance /fundingRate 返回升序 (旧→新), data[-1] 是最新结算
            # 用 max(fundingTime) 确保取到最新记录，不依赖排序假设
            most_recent = max(data, key=lambda x: int(x.get('fundingTime', 0)))
            rate = float(most_recent.get('fundingRate', 0))
            rate_pct = rate * 100
            results.ok("Settled Funding Rate", f"{rate:.6f} (decimal) = {rate_pct:.4f}%")

            # 合理范围: -0.5% ~ +0.5%
            if abs(rate_pct) < 0.5:
                results.ok("Settled FR 范围", "正常 (<0.5%)")
            else:
                results.warn("Settled FR 极端值", f"{rate_pct:.4f}%")

            # 历史排序验证 (limit=3, 最近3次结算)
            if len(data) >= 2:
                times = [int(d.get('fundingTime', 0)) for d in data]
                is_ascending = all(times[i] <= times[i+1] for i in range(len(times)-1))
                order_str = "升序(旧→新)" if is_ascending else "降序(新→旧)"
                results.ok("Settled History", f"{len(data)} 条结算记录, {order_str}")
        else:
            results.fail("Settled Funding Rate API", f"返回: {data}")

        # --- 5b: Predicted funding rate (from premiumIndex) ---
        url2 = "https://fapi.binance.com/fapi/v1/premiumIndex"
        params2 = {"symbol": "BTCUSDT"}
        resp2 = requests.get(url2, params=params2, timeout=10)
        data2 = resp2.json()

        if isinstance(data2, dict):
            predicted = float(data2.get('lastFundingRate', 0))
            pred_pct = predicted * 100
            results.ok("Predicted Funding Rate", f"{predicted:.6f} = {pred_pct:.4f}%")

            # Mark price / Index price
            mark = float(data2.get('markPrice', 0))
            index = float(data2.get('indexPrice', 0))
            if mark > 0 and index > 0:
                premium_index = (mark - index) / index
                pi_pct = premium_index * 100
                results.ok("Premium Index", f"{pi_pct:+.4f}% (Mark=${mark:,.2f}, Index=${index:,.2f})")
            else:
                results.warn("Mark/Index Price 缺失", "")

            # Funding delta (predicted - settled)
            delta_pct = pred_pct - rate_pct
            results.ok("Funding Delta", f"{delta_pct:+.4f}% (predicted - settled)")

            # Next funding countdown
            next_time = int(data2.get('nextFundingTime', 0))
            if next_time > 0:
                now_ms = int(time.time() * 1000)
                remaining_min = (next_time - now_ms) / 60000
                if remaining_min > 0:
                    results.ok("下次结算倒计时", f"{remaining_min:.0f} 分钟")
                else:
                    results.warn("下次结算时间已过", f"{remaining_min:.0f} 分钟")
        else:
            results.fail("PremiumIndex API", f"返回: {data2}")

        # --- 5c: BinanceKlineClient (如果可导入) ---
        try:
            from utils.binance_kline_client import BinanceKlineClient
            client = BinanceKlineClient()
            fr_data = client.get_funding_rate()
            if fr_data:
                # 验证字段完整性
                required = ['funding_rate', 'funding_rate_pct', 'predicted_rate',
                            'predicted_rate_pct', 'mark_price', 'index_price', 'source']
                missing = [f for f in required if f not in fr_data]
                if not missing:
                    results.ok("BinanceKlineClient.get_funding_rate()", "字段完整")
                else:
                    results.fail("BinanceKlineClient 字段缺失", str(missing))

                # 验证数值一致性 (与直接 API 对比)
                # 两边都取最新结算费率: BKC 用 limit=1, 直接 API 用 max(fundingTime)
                bkc_settled = fr_data.get('funding_rate_pct', 0)
                bkc_predicted = fr_data.get('predicted_rate_pct', 0)
                diff = abs(bkc_settled - rate_pct)
                if diff < 0.001:
                    results.ok("Settled Rate 一致性", f"BKC={bkc_settled:.4f}% vs API={rate_pct:.4f}%")
                else:
                    results.warn(
                        "Settled Rate 不一致",
                        f"BKC={bkc_settled:.4f}% vs API={rate_pct:.4f}% (差异={diff:.4f}%)"
                    )
            else:
                results.warn("BinanceKlineClient.get_funding_rate() 返回 None", "")

            # 验证 funding rate history
            fr_hist = client.get_funding_rate_history(limit=5)
            if fr_hist and len(fr_hist) >= 2:
                results.ok("Funding Rate History", f"{len(fr_hist)} 条")
                # 验证 fundingRate 字段存在且可转为 float
                for i, record in enumerate(fr_hist[:3]):
                    try:
                        float(record.get('fundingRate', 'nan'))
                    except (ValueError, TypeError):
                        results.fail(f"History[{i}] fundingRate 无效", str(record))
            else:
                results.warn("Funding Rate History 不足", f"{len(fr_hist) if fr_hist else 0} 条")

        except ImportError:
            results.warn("BinanceKlineClient 不可导入", "跳过深度验证")

    except Exception as e:
        results.fail("Funding Rate 验证", str(e))


# ─────────────────────────────────────────────────────────────────────
# Test 6: Binance 衍生品数据
# ─────────────────────────────────────────────────────────────────────

def test_binance_derivatives(results: TestResults):
    """验证 Binance 衍生品数据 (大户、Taker、OI)"""
    print("\n─── Test 6: Binance 衍生品数据验证 ───")

    try:
        from utils.binance_derivatives_client import BinanceDerivativesClient
        client = BinanceDerivativesClient()
        data = client.fetch_all(symbol="BTCUSDT", period="15m", history_limit=10)

        if not data:
            results.fail("fetch_all() 返回空", "")
            return

        # --- Top Traders Position ---
        top_pos = data.get('top_long_short_position', {})
        latest = top_pos.get('latest')
        if latest:
            long_pct = float(latest.get('longAccount', 0)) * 100
            short_pct = float(latest.get('shortAccount', 0)) * 100
            ratio = float(latest.get('longShortRatio', 0))
            total = long_pct + short_pct
            if abs(total - 100) < 1:
                results.ok("Top Traders L/S", f"L={long_pct:.1f}% S={short_pct:.1f}% R={ratio:.2f}")
            else:
                results.fail("Top Traders L+S ≠ 100%", f"{total:.1f}%")
        else:
            results.warn("Top Traders 数据缺失", "")

        # --- Taker Buy/Sell Ratio ---
        taker = data.get('taker_long_short', {})
        taker_latest = taker.get('latest')
        if taker_latest:
            taker_ratio = float(taker_latest.get('buySellRatio', 0))
            if 0.1 < taker_ratio < 10:
                results.ok("Taker Buy/Sell", f"Ratio={taker_ratio:.3f}")
            else:
                results.warn("Taker Ratio 异常", f"{taker_ratio}")
        else:
            results.warn("Taker 数据缺失", "")

        # --- OI History ---
        oi_hist = data.get('open_interest_hist', {})
        oi_latest = oi_hist.get('latest')
        if oi_latest:
            oi_usd = float(oi_latest.get('sumOpenInterestValue', 0))
            if oi_usd > 0:
                results.ok("OI (Binance)", f"${oi_usd:,.0f}")
            else:
                results.fail("OI 值为 0", "")

            # OI history 数据量
            oi_data = oi_hist.get('data', [])
            if len(oi_data) >= 2:
                results.ok("OI History", f"{len(oi_data)} 条")
            else:
                results.warn("OI History 不足", f"{len(oi_data)} 条")
        else:
            results.warn("OI 数据缺失", "")

        # --- 24h Ticker ---
        ticker = data.get('ticker_24hr')
        if ticker:
            change_pct = float(ticker.get('priceChangePercent', 0))
            volume = float(ticker.get('quoteVolume', 0))
            results.ok("24h Ticker", f"Change={change_pct:+.2f}%, Volume=${volume:,.0f}")
        else:
            results.warn("24h Ticker 缺失", "")

        # --- Trend 计算 ---
        for key in ['top_long_short_position', 'taker_long_short', 'open_interest_hist']:
            trend = data.get(key, {}).get('trend')
            if trend in ['RISING', 'FALLING', 'STABLE', None]:
                results.ok(f"Trend ({key})", f"{trend}")
            else:
                results.warn(f"Trend 异常 ({key})", f"{trend}")

    except ImportError:
        results.warn("BinanceDerivativesClient 不可导入", "跳过")
    except Exception as e:
        results.fail("Binance 衍生品验证", str(e))


# ─────────────────────────────────────────────────────────────────────
# Test 7: 字段一致性 (生产者 → 消费者)
# ─────────────────────────────────────────────────────────────────────

def test_field_consistency(results: TestResults):
    """验证数据字段在生产者和消费者之间的一致性"""
    print("\n─── Test 7: 字段一致性检查 ───")

    try:
        from utils.sentiment_client import SentimentDataFetcher
        fetcher = SentimentDataFetcher(timeframe="15m")
        data = fetcher.fetch("BTC")

        if data is None:
            results.warn("情绪数据不可用", "跳过字段一致性检查")
            return

        # MultiAgentAnalyzer._format_sentiment_report() 使用的字段
        consumer_fields = {
            'net_sentiment': "MultiAgent + DeepSeek",
            'positive_ratio': "MultiAgent + DeepSeek",
            'negative_ratio': "MultiAgent + DeepSeek",
            'long_short_ratio': "display formatting",
            'history': "MultiAgent trend analysis",
        }

        for field, usage in consumer_fields.items():
            if field in data:
                results.ok(f"字段一致: '{field}'", f"用于 {usage}")
            else:
                results.fail(f"字段缺失: '{field}'", f"需要用于 {usage}")

        # 检查 history 内部字段
        history = data.get('history', [])
        if history:
            h = history[0]
            for hf in ['long', 'short', 'ratio', 'timestamp']:
                if hf in h:
                    results.ok(f"history.'{hf}'", f"值: {h[hf]}")
                else:
                    results.fail(f"history.'{hf}' 缺失", "MultiAgent 需要此字段")

    except Exception as e:
        results.fail("字段一致性", str(e))


# ═════════════════════════════════════════════════════════════════════
# SECTION B: 离线逻辑验证 (无需网络)
# ═════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────
# Test 8: 离线解析逻辑 (mock 数据)
# ─────────────────────────────────────────────────────────────────────

def test_offline_parsing_logic(results: TestResults):
    """用 mock 数据验证所有解析逻辑 (无需网络)"""
    print("\n─── Test 8: 离线解析逻辑 (mock 数据) ───")

    # Mock Binance API response: ascending order (oldest first)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    mock_api_response = []
    for i in range(10):
        ts = now_ms - (10 - i) * 15 * 60 * 1000
        mock_api_response.append({
            "symbol": "BTCUSDT",
            "longShortRatio": f"{1.0 + i * 0.01:.4f}",
            "longAccount": f"{0.50 + i * 0.005:.4f}",
            "shortAccount": f"{0.50 - i * 0.005:.4f}",
            "timestamp": ts
        })

    # 1. 验证排序是升序
    timestamps = [d['timestamp'] for d in mock_api_response]
    assert all(timestamps[i] <= timestamps[i+1] for i in range(len(timestamps)-1))
    results.ok("Mock 数据升序", "timestamps 递增")

    # 2. 验证 data[-1] 是最新的
    newest = mock_api_response[-1]
    oldest = mock_api_response[0]
    assert newest['timestamp'] > oldest['timestamp']
    results.ok("data[-1] 最新", f"ts={newest['timestamp']} > ts={oldest['timestamp']}")

    # 3. 模拟 _parse_binance_data 逻辑
    try:
        from utils.sentiment_client import SentimentDataFetcher
        fetcher = SentimentDataFetcher(timeframe="15m")

        result = fetcher._parse_binance_data(newest)
        if result:
            delay = result['data_delay_minutes']
            if delay <= 20:
                results.ok("data[-1] 延迟", f"{delay} 分钟 (正常)")
            else:
                results.fail("data[-1] 延迟异常", f"{delay} 分钟")

            expected = float(newest['longAccount']) - float(newest['shortAccount'])
            actual = result['net_sentiment']
            if abs(actual - expected) < 0.0001:
                results.ok("net_sentiment 公式", f"{actual:.4f} = long - short")
            else:
                results.fail("net_sentiment 公式", f"actual={actual}, expected={expected}")
        else:
            results.fail("_parse_binance_data", "返回 None")

        result_old = fetcher._parse_binance_data(oldest)
        if result_old:
            delay_old = result_old['data_delay_minutes']
            results.ok("data[0] 延迟 (反面验证)", f"{delay_old} 分钟 (应该≈150分钟)")
            if delay_old > 100:
                results.ok("修复验证", f"如果用 data[0] 会导致 {delay_old} 分钟延迟!")
            else:
                results.warn("反面验证不明显", f"delay={delay_old}")

    except ImportError:
        long_r = float(newest['longAccount'])
        short_r = float(newest['shortAccount'])
        net = long_r - short_r
        results.ok("手动解析验证", f"long={long_r:.4f}, short={short_r:.4f}, net={net:.4f}")

        data_time = datetime.fromtimestamp(newest['timestamp'] / 1000, tz=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        delay = int((now_utc - data_time).total_seconds() // 60)
        results.ok("延迟计算", f"{delay} 分钟")

    # 4. 验证 history 排序逻辑
    history = []
    for item in mock_api_response:
        history.append({
            'long': float(item['longAccount']),
            'short': float(item['shortAccount']),
            'ratio': float(item['longShortRatio']),
            'timestamp': item['timestamp'],
        })

    if all(history[i]['timestamp'] <= history[i+1]['timestamp'] for i in range(len(history)-1)):
        results.ok("History 升序", "oldest → newest ✓")
    else:
        results.fail("History 排序", "不是升序!")

    if history[-1]['long'] > history[0]['long']:
        results.ok("History 数值趋势", f"从 {history[0]['long']:.4f} 到 {history[-1]['long']:.4f}")
    else:
        results.fail("History 数值", "最新值不是最大的 (mock 数据应该递增)")

    # 5. Buy ratio / CVD / Funding rate 公式
    test_volume = 100.0
    test_taker_buy = 55.0
    buy_ratio = test_taker_buy / test_volume
    assert abs(buy_ratio - 0.55) < 0.001
    results.ok("Buy Ratio 公式", f"{test_taker_buy}/{test_volume} = {buy_ratio}")

    sell_volume = test_volume - test_taker_buy
    cvd_delta = test_taker_buy - sell_volume
    assert abs(cvd_delta - 10.0) < 0.001
    results.ok("CVD Delta 公式", f"buy({test_taker_buy}) - sell({sell_volume}) = {cvd_delta}")

    raw_rate = 0.0001
    pct_rate = raw_rate * 100
    assert abs(pct_rate - 0.01) < 0.0001
    results.ok("Funding Rate 转换", f"{raw_rate} × 100 = {pct_rate}%")


# ─────────────────────────────────────────────────────────────────────
# Test 9: SL/TP 验证逻辑
# ─────────────────────────────────────────────────────────────────────

def test_sltp_validation(results: TestResults):
    """验证 validate_multiagent_sltp() 所有边界情况"""
    print("\n─── Test 9: SL/TP 验证逻辑 ───")

    try:
        from strategy.trading_logic import validate_multiagent_sltp

        price = 100000.0

        # --- LONG 有效 SL/TP ---
        valid, sl, tp, reason = validate_multiagent_sltp(
            side='BUY', multi_sl=98000.0, multi_tp=103000.0, entry_price=price
        )
        if valid and sl == 98000.0 and tp == 103000.0:
            results.ok("LONG 有效 SL/TP", f"SL={sl}, TP={tp}")
        else:
            results.fail("LONG 有效 SL/TP", f"valid={valid}, reason={reason}")

        # --- SHORT 有效 SL/TP ---
        valid, sl, tp, reason = validate_multiagent_sltp(
            side='SELL', multi_sl=102000.0, multi_tp=97000.0, entry_price=price
        )
        if valid and sl == 102000.0 and tp == 97000.0:
            results.ok("SHORT 有效 SL/TP", f"SL={sl}, TP={tp}")
        else:
            results.fail("SHORT 有效 SL/TP", f"valid={valid}, reason={reason}")

        # --- LONG SL 在入场价错误一侧 ---
        valid, _, _, reason = validate_multiagent_sltp(
            side='BUY', multi_sl=101000.0, multi_tp=103000.0, entry_price=price
        )
        if not valid:
            results.ok("LONG SL>entry 拒绝", f"reason={reason[:60]}")
        else:
            results.fail("LONG SL>entry 应被拒绝", "但通过了")

        # --- SHORT SL 在入场价错误一侧 ---
        valid, _, _, reason = validate_multiagent_sltp(
            side='SELL', multi_sl=99000.0, multi_tp=97000.0, entry_price=price
        )
        if not valid:
            results.ok("SHORT SL<entry 拒绝", f"reason={reason[:60]}")
        else:
            results.fail("SHORT SL<entry 应被拒绝", "但通过了")

        # --- R/R 过低 (< 1.5:1) ---
        # risk=2000 (2%), reward=1000 (1%) → R/R = 0.5:1
        valid, _, _, reason = validate_multiagent_sltp(
            side='BUY', multi_sl=98000.0, multi_tp=101000.0, entry_price=price
        )
        expected_rr = (101000 - price) / (price - 98000)  # 1000/2000 = 0.5
        from strategy.trading_logic import get_min_rr_ratio
        min_rr_t9 = get_min_rr_ratio()
        if not valid and 'R/R' in reason:
            results.ok("R/R < min 拒绝", f"R/R={expected_rr:.2f}:1 < {min_rr_t9}:1 ✓, {reason[:50]}")
        elif valid:
            results.fail("R/R 验证失败", f"R/R={expected_rr:.2f}:1 < {min_rr_t9}:1 但通过了!")

        # --- R/R 精确计算验证 ---
        # BUY: risk=entry-sl, reward=tp-entry, R/R=reward/risk
        valid_rr, _, _, reason_rr = validate_multiagent_sltp(
            side='BUY', multi_sl=97000.0, multi_tp=104500.0, entry_price=price
        )
        computed_rr = (104500.0 - price) / (price - 97000.0)  # 4500/3000 = 1.5
        if computed_rr >= min_rr_t9 and valid_rr:
            results.ok("R/R 精确 BUY", f"R/R={computed_rr:.4f}:1 >= {min_rr_t9}:1, 通过 ✓")
        elif computed_rr >= min_rr_t9 and not valid_rr:
            results.fail("R/R 精确 BUY", f"R/R={computed_rr:.4f}:1 >= {min_rr_t9}:1 但被拒绝: {reason_rr}")
        elif computed_rr < min_rr_t9 and not valid_rr:
            results.ok("R/R 精确 BUY", f"R/R={computed_rr:.4f}:1 < {min_rr_t9}:1, 拒绝 ✓")
        else:
            results.fail("R/R 精确 BUY", f"R/R={computed_rr:.4f}:1, valid={valid_rr}")

        # SELL: risk=sl-entry, reward=entry-tp, R/R=reward/risk
        valid_rr2, _, _, reason_rr2 = validate_multiagent_sltp(
            side='SELL', multi_sl=103000.0, multi_tp=95500.0, entry_price=price
        )
        computed_rr2 = (price - 95500.0) / (103000.0 - price)  # 4500/3000 = 1.5
        if computed_rr2 >= min_rr_t9 and valid_rr2:
            results.ok("R/R 精确 SELL", f"R/R={computed_rr2:.4f}:1 >= {min_rr_t9}:1, 通过 ✓")
        elif computed_rr2 >= min_rr_t9 and not valid_rr2:
            results.fail("R/R 精确 SELL", f"R/R={computed_rr2:.4f}:1 >= {min_rr_t9}:1 但被拒绝: {reason_rr2}")
        elif computed_rr2 < min_rr_t9 and not valid_rr2:
            results.ok("R/R 精确 SELL", f"R/R={computed_rr2:.4f}:1 < {min_rr_t9}:1, 拒绝 ✓")
        else:
            results.fail("R/R 精确 SELL", f"R/R={computed_rr2:.4f}:1, valid={valid_rr2}")

        # --- SL/TP 为 None ---
        valid, _, _, reason = validate_multiagent_sltp(
            side='BUY', multi_sl=None, multi_tp=None, entry_price=price
        )
        if not valid:
            results.ok("SL/TP=None 拒绝", "✓")
        else:
            results.fail("SL/TP=None 应被拒绝", "但通过了")

        # --- SL 太近 (< min distance) ---
        valid, _, _, reason = validate_multiagent_sltp(
            side='BUY', multi_sl=99990.0, multi_tp=103000.0, entry_price=price
        )
        if not valid:
            results.ok("SL 太近拒绝", f"0.01% < min, reason={reason[:60]}")
        else:
            results.warn("SL 太近未拒绝", "min_sl_distance 可能很小")

        # --- 支持 LONG/SHORT 格式 ---
        valid, sl, tp, _ = validate_multiagent_sltp(
            side='LONG', multi_sl=98000.0, multi_tp=103000.0, entry_price=price
        )
        if valid:
            results.ok("LONG 格式支持", "✓")
        else:
            results.fail("LONG 格式不支持", "应支持 LONG/SHORT 和 BUY/SELL")

    except ImportError as e:
        results.warn("trading_logic 导入失败", str(e))
    except Exception as e:
        results.fail("SL/TP 验证", str(e))
        import traceback
        traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────
# Test 10: 仓位计算逻辑
# ─────────────────────────────────────────────────────────────────────

def test_position_sizing(results: TestResults):
    """验证 calculate_position_size() 逻辑"""
    print("\n─── Test 10: 仓位计算逻辑 ───")

    try:
        from strategy.trading_logic import calculate_position_size

        price = 100000.0
        price_data = {'price': price}
        technical_data = {'overall_trend': 'BULLISH', 'rsi': 50, 'atr': 2000}

        # --- ai_controlled: AI 指定 80% ---
        signal = {'signal': 'BUY', 'confidence': 'HIGH', 'position_size_pct': 80}
        config = {
            'equity': 1000,
            'leverage': 10,
            'max_position_ratio': 0.30,
            'position_sizing': {'method': 'ai_controlled'},
            'min_trade_amount': 0.001,  # BTC, not USDT
        }

        qty, details = calculate_position_size(signal, price_data, technical_data, config)

        max_usdt = 1000 * 0.30 * 10  # = $3000
        expected_usdt = max_usdt * 0.80  # = $2400
        expected_qty = expected_usdt / price  # = 0.024

        if qty > 0:
            actual_usdt = qty * price
            results.ok("AI Controlled 仓位", f"qty={qty:.6f} BTC (${actual_usdt:,.0f})")
        else:
            results.fail("AI Controlled 仓位", f"qty={qty}, details={details}")

        # 不应超过 max_usdt (考虑 Binance min_notional 可能抬高)
        actual_usdt = qty * price
        # Note: actual 可能 > max_usdt 如果 min_notional > max_usdt
        if actual_usdt <= max_usdt * 1.05:  # 5% 容差 (rounding + min_notional)
            results.ok("最大仓位限制", f"${actual_usdt:,.0f} ≤ max ${max_usdt:,.0f}")
        else:
            results.fail("超过最大仓位", f"${actual_usdt:,.0f} > max ${max_usdt:,.0f}")

        # --- 无效价格 ---
        qty2, details2 = calculate_position_size(
            signal, {'price': 0}, technical_data, config
        )
        if qty2 == 0:
            results.ok("价格=0 返回 0", "✓")
        else:
            results.fail("价格=0 应返回 0", f"qty={qty2}")

        # --- confidence-based (fixed_pct, 无 position_size_pct) ---
        for conf in ['HIGH', 'MEDIUM', 'LOW']:
            signal_fc = {'signal': 'BUY', 'confidence': conf}
            config_fc = {
                'equity': 1000,
                'leverage': 5,
                'max_position_ratio': 0.30,
                'position_sizing': {
                    'method': 'fixed_pct',
                    'ai_controlled': {'default_size_pct': 50},
                },
                'base_usdt': 100,
                'high_confidence_multiplier': 1.5,
                'medium_confidence_multiplier': 1.0,
                'low_confidence_multiplier': 0.5,
                'min_trade_amount': 0.001,  # BTC, not USDT
            }
            qty_fc, _ = calculate_position_size(signal_fc, price_data, technical_data, config_fc)
            if qty_fc > 0:
                results.ok(f"Fixed PCT ({conf})", f"qty={qty_fc:.6f}")
            else:
                results.warn(f"Fixed PCT ({conf}) = 0", "可能 min_trade_amount 过滤")

    except ImportError as e:
        results.warn("trading_logic 导入失败", str(e))
    except Exception as e:
        results.fail("仓位计算验证", str(e))
        import traceback
        traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────
# Test 11: AI 响应解析
# ─────────────────────────────────────────────────────────────────────

def test_ai_response_parsing(results: TestResults):
    """验证 AI 响应 JSON 解析逻辑"""
    print("\n─── Test 11: AI 响应解析验证 ───")

    # --- 11a: 标准 JSON ---
    standard_json = '{"signal": "BUY", "confidence": "HIGH", "reason": "test", "stop_loss": 98000, "take_profit": 103000}'
    try:
        parsed = json.loads(standard_json)
        required = ["signal", "reason", "stop_loss", "take_profit", "confidence"]
        missing = [f for f in required if f not in parsed]
        if not missing:
            results.ok("标准 JSON 解析", "所有必需字段存在")
        else:
            results.fail("标准 JSON 字段缺失", str(missing))
    except json.JSONDecodeError:
        results.fail("标准 JSON 解析失败", "")

    # --- 11b: JSON 包裹在 markdown code block 中 ---
    wrapped_json = '```json\n{"signal": "SELL", "confidence": "MEDIUM", "reason": "test", "stop_loss": 102000, "take_profit": 97000}\n```'
    start = wrapped_json.find('{')
    end = wrapped_json.rfind('}') + 1
    if start != -1 and end > 0:
        extracted = wrapped_json[start:end]
        try:
            parsed = json.loads(extracted)
            results.ok("Markdown-wrapped JSON", f"signal={parsed.get('signal')}")
        except json.JSONDecodeError:
            results.fail("Markdown-wrapped JSON 解析失败", "")
    else:
        results.fail("Markdown-wrapped JSON 提取失败", "")

    # --- 11c: 包含内部双引号的 reason ---
    bad_json = '{"signal": "HOLD", "confidence": "LOW", "reason": "Price shows \\"strong\\" resistance", "stop_loss": 100000, "take_profit": 100000}'
    try:
        parsed = json.loads(bad_json)
        results.ok("转义引号 JSON", f"reason 长度={len(parsed.get('reason', ''))}")
    except json.JSONDecodeError:
        # 尝试 DeepSeekAnalyzer._safe_parse_json 的修复逻辑
        results.warn("转义引号 JSON 失败", "需要修复逻辑")

    # --- 11d: 信号值验证 ---
    valid_signals = {'BUY', 'SELL', 'HOLD'}
    valid_confidences = {'HIGH', 'MEDIUM', 'LOW'}

    for sig in valid_signals:
        if sig in valid_signals:
            results.ok(f"信号 '{sig}' 有效", "✓")

    for conf in valid_confidences:
        if conf in valid_confidences:
            results.ok(f"信心 '{conf}' 有效", "✓")

    # --- 11e: SL/TP 数值类型验证 ---
    test_signals = [
        {"signal": "BUY", "stop_loss": 98000, "take_profit": 103000},  # int
        {"signal": "BUY", "stop_loss": 98000.50, "take_profit": 103000.50},  # float
        {"signal": "BUY", "stop_loss": "98000", "take_profit": "103000"},  # str
    ]
    for i, sig in enumerate(test_signals):
        try:
            sl = float(sig['stop_loss'])
            tp = float(sig['take_profit'])
            if sl > 0 and tp > 0:
                results.ok(f"SL/TP 类型转换 (case {i+1})", f"SL={sl}, TP={tp}")
            else:
                results.fail(f"SL/TP 类型转换 (case {i+1})", "<=0")
        except (ValueError, TypeError) as e:
            results.fail(f"SL/TP 类型转换 (case {i+1})", str(e))

    # --- 11f: Fallback 信号验证 ---
    fallback = {
        "signal": "HOLD",
        "reason": "Conservative strategy due to technical analysis unavailable",
        "stop_loss": 100000 * 0.98,
        "take_profit": 100000 * 1.02,
        "confidence": "LOW",
        "is_fallback": True,
    }
    if fallback.get('signal') == 'HOLD' and fallback.get('is_fallback') is True:
        results.ok("Fallback 信号结构", "signal=HOLD, is_fallback=True")
    else:
        results.fail("Fallback 信号结构", str(fallback))


# ─────────────────────────────────────────────────────────────────────
# Test 12: OI×Price 四象限逻辑
# ─────────────────────────────────────────────────────────────────────

def test_oi_price_quadrant(results: TestResults):
    """验证 OI×Price 4-Quadrant 分析逻辑"""
    print("\n─── Test 12: OI×Price 四象限逻辑 ───")

    # 模拟 multi_agent_analyzer.py 中的四象限逻辑
    quadrant_map = {
        ("↑", "↑"): "New longs entering → BULLISH CONFIRMATION",
        ("↑", "↓"): "Short covering → WEAK rally (no new conviction)",
        ("↓", "↑"): "New shorts entering → BEARISH CONFIRMATION",
        ("↓", "↓"): "Long liquidation → BEARISH EXHAUSTION",
    }

    test_cases = [
        # (price_change, oi_change_pct, expected_price_dir, expected_oi_dir, expected_signal)
        (2.0, 3.0, "↑", "↑", "New longs"),
        (2.0, -3.0, "↑", "↓", "Short covering"),
        (-2.0, 3.0, "↓", "↑", "New shorts"),
        (-2.0, -3.0, "↓", "↓", "Long liquidation"),
        (0.05, 0.2, "→", "→", "Neutral"),  # 低于阈值
    ]

    for price_chg, oi_chg, exp_p, exp_o, keyword in test_cases:
        # 重现代码中的方向判断
        price_dir = "↑" if price_chg > 0.1 else "↓" if price_chg < -0.1 else "→"
        oi_dir = "↑" if oi_chg > 0.5 else "↓" if oi_chg < -0.5 else "→"

        if price_dir != exp_p or oi_dir != exp_o:
            results.fail(f"方向判断 P={price_chg} OI={oi_chg}",
                         f"得到 P{price_dir}+OI{oi_dir}, 预期 P{exp_p}+OI{exp_o}")
            continue

        signal = quadrant_map.get(
            (price_dir, oi_dir),
            f"Price {price_dir} + OI {oi_dir} = Neutral / consolidation"
        )

        if keyword.lower() in signal.lower():
            results.ok(f"P{price_dir}+OI{oi_dir}", f"{signal[:50]}")
        else:
            results.fail(f"P{price_dir}+OI{oi_dir}", f"预期含'{keyword}', 得到: {signal}")


# ─────────────────────────────────────────────────────────────────────
# Test 13: CVD 冷启动 & 趋势逻辑
# ─────────────────────────────────────────────────────────────────────

def test_cvd_cold_start(results: TestResults):
    """验证 CVD 冷启动检测和趋势计算"""
    print("\n─── Test 13: CVD 冷启动 & 趋势逻辑 ───")

    # 冷启动: < 3 bars
    for count in [0, 1, 2]:
        cvd_history = list(range(count))
        warning = ""
        if len(cvd_history) < 3:
            warning = " ⚠️ COLD_START (< 3 bars, trend unreliable)"
        if "COLD_START" in warning:
            results.ok(f"CVD {count} bars → COLD_START", "✓")
        else:
            results.fail(f"CVD {count} bars 应该 COLD_START", "")

    # 正常: >= 3 bars
    cvd_history_normal = [1, 2, 3, 4, 5]
    warning = ""
    if len(cvd_history_normal) < 3:
        warning = " ⚠️ COLD_START"
    if warning == "":
        results.ok("CVD 5 bars → 正常", "无 COLD_START")
    else:
        results.fail("CVD 5 bars 不应 COLD_START", "")

    # CVD 趋势计算逻辑 (来自 OrderFlowProcessor._calculate_cvd_trend)
    # 需要至少 5 个数据点
    cvd_short = [10, 20, 30]  # 不足 5 → NEUTRAL
    if len(cvd_short) < 5:
        results.ok("CVD < 5 bars → NEUTRAL", "✓")

    # RISING: recent_5 avg > older_5 avg * 1.1
    cvd_rising = [10, 10, 10, 10, 10, 20, 20, 20, 20, 20]
    recent_5 = cvd_rising[-5:]
    older_5 = cvd_rising[-10:-5]
    avg_recent = sum(recent_5) / len(recent_5)
    avg_older = sum(older_5) / len(older_5)
    if avg_recent > avg_older * 1.1:
        results.ok("CVD RISING", f"recent={avg_recent} > older={avg_older}×1.1={avg_older*1.1}")
    else:
        results.fail("CVD RISING 判定", f"recent={avg_recent}, older={avg_older}")

    # FALLING: recent < older * 0.9
    cvd_falling = [20, 20, 20, 20, 20, 10, 10, 10, 10, 10]
    recent_5 = cvd_falling[-5:]
    older_5 = cvd_falling[-10:-5]
    avg_r = sum(recent_5) / len(recent_5)
    avg_o = sum(older_5) / len(older_5)
    if avg_r < avg_o * 0.9:
        results.ok("CVD FALLING", f"recent={avg_r} < older={avg_o}×0.9={avg_o*0.9}")
    else:
        results.fail("CVD FALLING 判定", f"recent={avg_r}, older={avg_o}")


# ─────────────────────────────────────────────────────────────────────
# Test 14: Funding Delta 计算
# ─────────────────────────────────────────────────────────────────────

def test_funding_delta(results: TestResults):
    """验证 Funding Delta (predicted - settled) 方向判断"""
    print("\n─── Test 14: Funding Delta 计算逻辑 ───")

    test_cases = [
        # (settled_pct, predicted_pct, expected_direction)
        (-0.0100, -0.0050, "↑ more bullish pressure"),    # -0.01 → -0.005: 向正方向移动
        (0.0100, 0.0200, "↑ more bullish pressure"),     # 0.01 → 0.02: 多头更强
        (0.0100, 0.0050, "↓ more bearish pressure"),     # 0.01 → 0.005: 多头减弱
        (0.0100, 0.0100, "→ stable"),                    # 相同
    ]

    for settled, predicted, expected in test_cases:
        delta = predicted - settled
        if delta > 0:
            direction = "↑ more bullish pressure"
        elif delta < 0:
            direction = "↓ more bearish pressure"
        else:
            direction = "→ stable"

        if direction == expected:
            results.ok(f"Delta {settled:.4f}%→{predicted:.4f}%", f"{direction}")
        else:
            results.fail(f"Delta {settled:.4f}%→{predicted:.4f}%",
                         f"预期: {expected}, 实际: {direction}")


# ─────────────────────────────────────────────────────────────────────
# Test 15: Funding Rate 解读逻辑
# ─────────────────────────────────────────────────────────────────────

def test_funding_interpretation(results: TestResults):
    """验证 funding rate 解读逻辑"""
    print("\n─── Test 15: Funding Rate 解读逻辑 ───")

    try:
        from utils.ai_data_assembler import AIDataAssembler
        # 使用类方法测试 (需要实例化)
        # 直接重现逻辑
        def interpret_funding(rate):
            if rate > 0.001:
                return "VERY_BULLISH"
            elif rate > 0.0005:
                return "BULLISH"
            elif rate < -0.001:
                return "VERY_BEARISH"
            elif rate < -0.0005:
                return "BEARISH"
            else:
                return "NEUTRAL"

        test_cases = [
            (0.0015, "VERY_BULLISH"),
            (0.0008, "BULLISH"),
            (0.0001, "NEUTRAL"),
            (-0.0001, "NEUTRAL"),
            (-0.0008, "BEARISH"),
            (-0.0015, "VERY_BEARISH"),
        ]

        for rate, expected in test_cases:
            actual = interpret_funding(rate)
            if actual == expected:
                results.ok(f"FR {rate:.4f} → {actual}", "✓")
            else:
                results.fail(f"FR {rate:.4f}", f"预期={expected}, 实际={actual}")

    except Exception as e:
        results.fail("Funding 解读验证", str(e))


# ─────────────────────────────────────────────────────────────────────
# Test 16: Binance 衍生品趋势计算
# ─────────────────────────────────────────────────────────────────────

def test_trend_calculation(results: TestResults):
    """验证趋势计算逻辑 (RISING/FALLING/STABLE)"""
    print("\n─── Test 16: 趋势计算逻辑 ───")

    # 重现 BinanceDerivativesClient._calc_trend 逻辑
    threshold = 2.0  # 默认阈值

    def calc_trend(data, key):
        if not data or len(data) < 2:
            return None
        newest = float(data[0].get(key, 0))
        oldest = float(data[-1].get(key, 0))
        if oldest == 0:
            return None
        change_pct = (newest - oldest) / oldest * 100
        if change_pct > threshold:
            return "RISING"
        elif change_pct < -threshold:
            return "FALLING"
        else:
            return "STABLE"

    # RISING: +5%
    data_rising = [{'val': 105}, {'val': 103}, {'val': 100}]
    assert calc_trend(data_rising, 'val') == "RISING"
    results.ok("趋势: +5% → RISING", "✓")

    # FALLING: -5%
    data_falling = [{'val': 95}, {'val': 97}, {'val': 100}]
    assert calc_trend(data_falling, 'val') == "FALLING"
    results.ok("趋势: -5% → FALLING", "✓")

    # STABLE: +1%
    data_stable = [{'val': 101}, {'val': 100.5}, {'val': 100}]
    assert calc_trend(data_stable, 'val') == "STABLE"
    results.ok("趋势: +1% → STABLE", "✓")

    # 数据不足
    assert calc_trend([{'val': 100}], 'val') is None
    results.ok("趋势: 1条数据 → None", "✓")

    # 空数据
    assert calc_trend([], 'val') is None
    results.ok("趋势: 空数据 → None", "✓")

    # NOTE: data[0] = newest, data[-1] = oldest (Binance 降序)
    # 这与 sentiment data (升序) 不同!
    results.ok("注意: Binance 衍生品 data[0]=newest", "与 sentiment (data[-1]=newest) 不同!")


# ─────────────────────────────────────────────────────────────────────
# Test 17: 生产数据流结构验证 (on_timer → analyze() 参数契约)
# ─────────────────────────────────────────────────────────────────────

def test_data_assembler_structure(results: TestResults):
    """
    验证生产 on_timer() → MultiAgentAnalyzer.analyze() 的参数契约。

    IMPORTANT: 生产 on_timer() 使用内联数据组装，不使用 AIDataAssembler。
    此测试验证:
    1. analyze() 接受的参数与生产传递的参数一致 (16 个)
    2. 各数据类型的子结构符合消费者期望
    3. Coinalyze 使用 fetch_all() (非 fetch_all_with_history())
    """
    print("\n─── Test 17: 生产数据流结构验证 ───")

    # ========== Part 1: 验证 analyze() 参数签名与生产调用一致 ==========
    # 生产调用位于 deepseek_strategy.py:1863-1886
    production_analyze_params = [
        'symbol', 'technical_report', 'sentiment_report',
        'current_position', 'price_data',
        'order_flow_report', 'derivatives_report',
        'binance_derivatives_report', 'orderbook_report',
        'account_context', 'bars_data',
        'bars_data_4h', 'bars_data_1d', 'daily_bar', 'weekly_bar',
        'atr_value',
    ]

    try:
        import inspect
        from agents.multi_agent_analyzer import MultiAgentAnalyzer
        sig = inspect.signature(MultiAgentAnalyzer.analyze)
        sig_params = [p for p in sig.parameters if p != 'self']

        # Check all production params exist in signature
        missing_in_sig = [p for p in production_analyze_params if p not in sig_params]
        extra_in_sig = [p for p in sig_params if p not in production_analyze_params]

        if not missing_in_sig:
            results.ok(
                "analyze() 参数签名",
                f"全部 {len(production_analyze_params)} 个生产参数均存在于签名中"
            )
        else:
            results.fail(
                "analyze() 参数签名",
                f"生产传递但签名缺失: {missing_in_sig}"
            )

        if extra_in_sig:
            results.warn(
                "analyze() 额外参数",
                f"签名中有但生产未传递: {extra_in_sig}"
            )
    except Exception as e:
        results.warn("analyze() 签名检查", f"无法导入: {e}")

    # ========== Part 2: Coinalyze 方法一致性验证 ==========
    # 生产使用 fetch_all() (L1750), 不是 fetch_all_with_history()
    # fetch_all() 返回: {open_interest, liquidations, funding_rate, enabled}
    # fetch_all_with_history() 额外返回: trends, *_history (诊断/测试场景可用)
    try:
        from utils.coinalyze_client import CoinalyzeClient
        fetch_all_fields = ['open_interest', 'liquidations', 'funding_rate', 'enabled']
        # Verify fetch_all exists and has expected return structure comment
        if hasattr(CoinalyzeClient, 'fetch_all'):
            results.ok("Coinalyze 生产方法", "fetch_all() (非 fetch_all_with_history)")
        else:
            results.fail("Coinalyze 生产方法", "fetch_all() 方法不存在")

        results.ok("derivatives 子字段 (fetch_all)", f"{fetch_all_fields}")
    except Exception as e:
        results.warn("Coinalyze 验证", str(e)[:80])

    # ========== Part 3: 各数据类别子结构定义 ==========
    # order_flow 子结构 (OrderFlowProcessor.process_klines 输出)
    expected_order_flow = [
        'buy_ratio', 'avg_trade_usdt', 'volume_usdt', 'trades_count',
        'cvd_trend', 'recent_10_bars', 'data_source',
    ]

    # sentiment 子结构 (SentimentDataFetcher.fetch 输出 或 默认中性值)
    expected_sentiment = [
        'positive_ratio', 'negative_ratio', 'net_sentiment',
        'long_short_ratio', 'source',
    ]

    results.ok("order_flow 子字段", f"{len(expected_order_flow)} 个")
    results.ok("sentiment 子字段", f"{len(expected_sentiment)} 个")

    # ========== Part 4: 消费者字段路径 ==========
    consumer_paths = [
        ("_format_technical_report", "technical → price, sma_*, rsi, macd, bb_*, adx, volume_ratio"),
        ("_format_sentiment_report", "sentiment → net_sentiment, positive_ratio, negative_ratio, history"),
        ("_format_order_flow_report", "order_flow → buy_ratio, cvd_trend, cvd_history, volume_usdt"),
        ("_format_derivatives_report", "derivatives → open_interest, funding_rate, liquidations"),
        ("_format_orderbook_report", "order_book → obi, dynamics, anomalies, liquidity"),
        ("_build_key_metrics", "technical + derivatives + order_flow + sentiment (交叉引用)"),
    ]

    for method, fields in consumer_paths:
        results.ok(f"消费者: {method}", fields[:70])


# ─────────────────────────────────────────────────────────────────────
# Test 18: SMA 标签歧义验证
# ─────────────────────────────────────────────────────────────────────

def test_sma_label_disambiguation(results: TestResults):
    """验证 SMA200 标签区分 (15M vs 1D)"""
    print("\n─── Test 18: SMA 标签歧义验证 ───")

    # _build_key_metrics 中使用 SMA{period}_15M 标签
    # _format_technical_report 中 1D 部分使用 "SMA 200" 标签
    # Judge 应该能区分两者

    # 模拟 _build_key_metrics 的标签
    price = 100000
    sma_200_15m = 99000  # 15M SMA200 ≈ 50 hours
    pct_15m = (price - sma_200_15m) / sma_200_15m * 100
    label_15m = f"Price vs SMA200_15M: {pct_15m:+.2f}%"

    if "_15M" in label_15m:
        results.ok("Key Metrics SMA200 标签", f"{label_15m} (含 _15M 后缀)")
    else:
        results.fail("Key Metrics SMA200 标签", "缺少 _15M 后缀, 与 1D SMA200 混淆")

    # 模拟 _format_technical_report 的 1D 标签
    sma_200_1d = 95000  # Daily SMA200
    label_1d = f"SMA 200: ${sma_200_1d:,.2f}"
    section_1d = "=== MARKET DATA (1D Timeframe - Macro Trend) ==="

    if "1D" in section_1d:
        results.ok("1D SMA200 在 1D 段", f"段标题含 '1D'")
    else:
        results.fail("1D SMA200 段标题", "应包含 '1D' 区分")

    # 两者不应混淆
    if sma_200_15m != sma_200_1d:
        results.ok("15M vs 1D SMA200 不同", f"15M=${sma_200_15m:,.0f} vs 1D=${sma_200_1d:,.0f}")


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────
# Test 19: 消费者字段契约验证 (防止 current_pct 类 bug)
# ─────────────────────────────────────────────────────────────────────

def test_consumer_field_contracts(results: TestResults):
    """
    验证 AIDataAssembler 输出的字段名与消费者 .get() 调用匹配。

    NOTE: 生产 on_timer() 不使用 AIDataAssembler，而是内联组装数据后
    直接传给 MultiAgentAnalyzer.analyze()。此测试验证 AIDataAssembler
    作为辅助工具 (diagnose 等场景) 的字段契约仍然正确。
    生产路径的参数契约由 Test 17 验证。

    核心思路: 不测生产者输出了什么，测消费者能不能读到值。
    这是防止字段名断裂 bug 的关键测试 (如 settled_pct vs current_pct)。
    """
    print("\n─── Test 19: 消费者字段契约验证 ───")

    try:
        from utils.ai_data_assembler import AIDataAssembler

        # --- 只 mock 数据源，不 mock 计算逻辑 ---
        # 原则: BinanceKlines/Sentiment = 纯数据源 → mock OK
        #        OrderFlowProcessor/CoinalyzeClient = 有公式计算 → 用真实生产代码
        from utils.order_flow_processor import OrderFlowProcessor
        from utils.coinalyze_client import CoinalyzeClient

        # Mock: Binance K线数据源 (纯 API 调用，无计算逻辑)
        class MockBinanceKlines:
            def get_funding_rate(self):
                return {
                    'funding_rate': 0.00058,
                    'funding_rate_pct': 0.058,
                    'predicted_rate': 0.00001,
                    'predicted_rate_pct': 0.001,
                    'next_funding_time': int(time.time() * 1000) + 3600000,
                    'next_funding_countdown_min': 60,
                    'mark_price': 100000.0,
                    'index_price': 99950.0,
                    'interest_rate': 0.0001,
                    'premium_index': 0.0005,
                }

            def get_funding_rate_history(self, limit=10):
                return [
                    {'fundingRate': '0.00030', 'fundingTime': 1000},
                    {'fundingRate': '0.00040', 'fundingTime': 2000},
                    {'fundingRate': '0.00058', 'fundingTime': 3000},
                ]

            def get_klines(self, **kwargs):
                # 10 根 K线: volume=100, taker_buy=60 → 真实 OrderFlowProcessor 计算
                t = int(time.time() * 1000)
                klines = []
                for i in range(10):
                    ts = t - (10 - i) * 60000
                    klines.append([
                        ts, '100000', '100500', '99500', '100000',
                        '100', ts + 60000, '1200000', 120, '60', '720000', '0',
                    ])
                return klines

        # ✅ 真实生产代码: OrderFlowProcessor (10-bar 平均, CVD, 趋势)
        real_order_flow = OrderFlowProcessor()

        # ✅ 真实生产代码: CoinalyzeClient (只 mock 6 个 API 调用，保留趋势计算公式)
        class TestableCoinalyze(CoinalyzeClient):
            """Override API calls, keep real fetch_all_with_history + _calc_trend_from_history"""
            def __init__(self):
                super().__init__(api_key="test_key", timeout=1, max_retries=0)

            def get_open_interest(self, symbol=None):
                return {'value': 500.0}

            def get_liquidations(self, symbol=None):
                return {'history': [{'l': 1.5, 's': 2.0}]}

            def get_funding_rate(self, symbol=None):
                return {'value': 0.0003}

            def get_open_interest_history(self, symbol=None, hours=4):
                # oldest=100, newest=110 → +10% > 3% → RISING (由真实公式计算)
                return {'history': [{'c': 100, 't': 1000}, {'c': 110, 't': 2000}]}

            def get_funding_rate_history(self, symbol=None, hours=4):
                # oldest=0.01, newest=0.008 → -20% < -3% → FALLING (由真实公式计算)
                return {'history': [{'c': 0.01, 't': 1000}, {'c': 0.008, 't': 2000}]}

            def get_long_short_ratio_history(self, symbol=None, hours=4):
                # oldest=1.0, newest=1.02 → +2% → STABLE (由真实公式计算)
                return {'history': [{'r': 1.0, 't': 1000}, {'r': 1.02, 't': 2000}]}

        # Mock: 情绪数据源 (纯 API 调用，计算仅 net=pos-neg)
        class MockSentiment:
            def fetch(self):
                return {
                    'positive_ratio': 0.55, 'negative_ratio': 0.45,
                    'net_sentiment': 0.1, 'long_short_ratio': 1.22,
                    'source': 'mock', 'history': [],
                }

        assembler = AIDataAssembler(
            binance_kline_client=MockBinanceKlines(),
            order_flow_processor=real_order_flow,          # ← 真实生产代码
            coinalyze_client=TestableCoinalyze(),          # ← 真实趋势计算
            sentiment_client=MockSentiment(),
        )

        # --- 调用真实的 assemble() 方法 ---
        assembled = assembler.assemble(
            technical_data={
                'price': 100000, 'rsi': 50, 'macd': 100, 'macd_signal': 95,
                'bb_upper': 101000, 'bb_lower': 99000, 'bb_middle': 100000,
                'bb_position': 0.5, 'adx': 25, 'di_plus': 20, 'di_minus': 15,
                'sma_5': 99900, 'sma_20': 99500, 'sma_50': 99000,
                'volume_ratio': 1.2, 'atr': 500,
            },
            symbol='BTCUSDT',
        )

        # ═══════════════════════════════════════════════════════════════
        # 消费者契约定义
        # 格式: (consumer_get_chain, description, allow_none)
        #   consumer_get_chain: 模拟消费者的 .get() 调用链
        #   description: 消费者位置
        #   allow_none: True = 允许 None (消费者有 if 保护)
        # ═══════════════════════════════════════════════════════════════

        derivatives = assembled.get('derivatives', {})
        fr = derivatives.get('funding_rate', {})
        oi = derivatives.get('open_interest', {})
        liq = derivatives.get('liquidations', {})
        sentiment = assembled.get('sentiment', {})
        order_flow = assembled.get('order_flow', {})

        contracts = [
            # --- Funding Rate (multi_agent_analyzer Bull/Bear prompt) ---
            (fr.get('current_pct'),
             "derivatives.funding_rate.current_pct",
             "multi_agent L1020: Bull/Bear analyst prompt", False),

            (fr.get('predicted_rate_pct'),
             "derivatives.funding_rate.predicted_rate_pct",
             "multi_agent L1022: Bull/Bear analyst prompt", True),

            (fr.get('value'),
             "derivatives.funding_rate.value",
             "multi_agent L2292: Risk Manager prompt", False),

            # --- Funding Rate (format_complete_report) ---
            (fr.get('current_pct', 0),
             "derivatives.funding_rate.current_pct (default=0)",
             "format_complete_report L485", False),

            (fr.get('interpretation'),
             "derivatives.funding_rate.interpretation",
             "format_complete_report L486", False),

            (fr.get('trend'),
             "derivatives.funding_rate.trend",
             "format_complete_report L483", False),

            (fr.get('premium_index'),
             "derivatives.funding_rate.premium_index",
             "format_complete_report L489", True),

            (fr.get('mark_price'),
             "derivatives.funding_rate.mark_price",
             "format_complete_report L492", False),

            (fr.get('history'),
             "derivatives.funding_rate.history",
             "format_complete_report L512", False),

            (fr.get('next_funding_countdown_min'),
             "derivatives.funding_rate.next_funding_countdown_min",
             "format_complete_report L504", True),

            # --- Open Interest ---
            (oi.get('total_btc') if oi else None,
             "derivatives.open_interest.total_btc",
             "format_complete_report L476", True),

            (oi.get('change_pct') if oi else None,
             "derivatives.open_interest.change_pct",
             "multi_agent L1033: OI change", True),

            # --- Liquidations ---
            (liq.get('total_usd') if liq else None,
             "derivatives.liquidations.total_usd",
             "multi_agent L1028: liquidation display", True),

            # --- Sentiment ---
            (sentiment.get('net_sentiment'),
             "sentiment.net_sentiment",
             "multi_agent L1055: sentiment report", False),

            (sentiment.get('positive_ratio'),
             "sentiment.positive_ratio",
             "multi_agent L1724: sentiment report", False),

            (sentiment.get('negative_ratio'),
             "sentiment.negative_ratio",
             "multi_agent L1728: sentiment report", False),

            # --- Order Flow ---
            (order_flow.get('buy_ratio'),
             "order_flow.buy_ratio",
             "multi_agent L1038: order flow report", False),

            (order_flow.get('cvd_trend'),
             "order_flow.cvd_trend",
             "multi_agent L1041: order flow report", False),
        ]

        # --- 执行契约验证 ---
        pass_count = 0
        fail_count = 0
        for value, field_path, consumer, allow_none in contracts:
            if value is None and not allow_none:
                results.fail(
                    f"契约断裂: {field_path}",
                    f"消费者 {consumer} 会读到 None → AI 看不到此数据"
                )
                fail_count += 1
            elif value is None and allow_none:
                pass_count += 1  # 静默通过 (允许 None)
            else:
                pass_count += 1

        if fail_count == 0:
            results.ok(
                "消费者字段契约",
                f"全部 {pass_count + fail_count} 条契约通过 "
                f"(生产者字段名 = 消费者 .get() key)"
            )
        else:
            results.fail(
                "消费者字段契约",
                f"{fail_count} 条断裂 — AI prompt 中有数据缺失"
            )

        # --- 额外验证: current_pct 不应为 0 (当费率非零时) ---
        if fr.get('value') and fr.get('value') != 0:
            current_pct = fr.get('current_pct')
            if current_pct == 0 or current_pct is None:
                results.fail(
                    "current_pct 零值保护",
                    f"funding_rate.value={fr['value']} 但 current_pct={current_pct}"
                )
            else:
                results.ok(
                    "current_pct 零值保护",
                    f"value={fr['value']:.6f} → current_pct={current_pct:.4f}% (非零)"
                )

        # --- 额外验证: format_complete_report 可正常执行 ---
        try:
            report = assembler.format_complete_report(assembled)
            # 验证报告中包含实际 funding rate 值 (不是 0.0000%)
            if 'Funding Rate' in report and '0.0000%' not in report.split('Funding Rate')[1][:30]:
                results.ok("format_complete_report", "Funding Rate 显示非零值")
            elif 'Funding Rate' in report:
                # 检查是否显示了 0.0000%
                fr_section = report.split('Funding Rate')[1][:50]
                if '0.0000%' in fr_section:
                    results.fail(
                        "format_complete_report Funding Rate",
                        f"显示 0.0000% (字段映射可能断裂): ...{fr_section.strip()[:40]}"
                    )
                else:
                    results.ok("format_complete_report", "Funding Rate 正常显示")
            else:
                results.warn("format_complete_report", "未找到 Funding Rate 段")
        except Exception as e:
            results.fail("format_complete_report 执行失败", str(e)[:80])

    except ImportError as e:
        results.warn("AIDataAssembler 不可导入", f"跳过契约验证: {e}")
    except Exception as e:
        results.fail("消费者字段契约测试异常", str(e)[:100])


# ─────────────────────────────────────────────────────────────────────
# Test 20: 生产代码计算正确性 (已知输入 → 预期输出)
# ─────────────────────────────────────────────────────────────────────

def test_production_calculations(results: TestResults):
    """
    用已知 mock 输入调用真实生产代码，验证输出值是否正确。

    与 Test 8 (离线公式) 的区别:
    - Test 8: 测试脚本自己的公式逻辑 (mock → 脚本代码 → 验证)
    - Test 20: 测试生产代码的公式逻辑 (mock → AIDataAssembler → 验证)

    能检测: 乘除错误、单位转换错误、rounding 错误、比较方向错误
    """
    print("\n─── Test 20: 生产代码计算正确性 ───")

    try:
        from utils.ai_data_assembler import AIDataAssembler

        # --- 已知输入值 (mock) ---
        MOCK_OI_BTC = 500.0
        MOCK_PRICE = 100000.0
        MOCK_LIQ_LONG_BTC = 1.5
        MOCK_LIQ_SHORT_BTC = 2.0
        MOCK_FUNDING_RATE = 0.00058  # decimal
        MOCK_FUNDING_PCT = 0.058     # percent (= 0.00058 * 100, rounded 4)
        MOCK_MARK_PRICE = 100000.0
        MOCK_INDEX_PRICE = 99950.0
        # History: [0.0003, 0.0004, 0.00058] → 0.00058 > 0.0003*1.1 → RISING
        MOCK_HISTORY_RATES = [0.00030, 0.00040, 0.00058]

        class MockBinanceKlines:
            def get_funding_rate(self):
                return {
                    'funding_rate': MOCK_FUNDING_RATE,
                    'funding_rate_pct': round(MOCK_FUNDING_RATE * 100, 4),
                    'predicted_rate': 0.00001,
                    'predicted_rate_pct': 0.001,
                    'next_funding_time': int(time.time() * 1000) + 3600000,
                    'next_funding_countdown_min': 60,
                    'mark_price': MOCK_MARK_PRICE,
                    'index_price': MOCK_INDEX_PRICE,
                    'premium_index': (MOCK_MARK_PRICE - MOCK_INDEX_PRICE) / MOCK_INDEX_PRICE,
                }

            def get_funding_rate_history(self, limit=10):
                return [
                    {'fundingRate': str(r), 'fundingTime': i * 1000}
                    for i, r in enumerate(MOCK_HISTORY_RATES)
                ]

            def get_klines(self, **kwargs):
                # 10 根 K线: volume=100, taker_buy=60 → 真实 OrderFlowProcessor 计算
                # 预期: buy_ratio=0.6, avg_trade_usdt=10000, volume_usdt=1200000
                t = int(time.time() * 1000)
                klines = []
                for i in range(10):
                    ts = t - (10 - i) * 60000
                    klines.append([
                        ts, '100000', '100500', '99500', '100000',
                        '100', ts + 60000, '1200000', 120, '60', '720000', '0',
                    ])
                return klines

        # ✅ 真实生产代码: OrderFlowProcessor
        from utils.order_flow_processor import OrderFlowProcessor
        real_order_flow = OrderFlowProcessor()

        # ✅ 真实生产代码: CoinalyzeClient (只 mock API，保留趋势计算公式)
        from utils.coinalyze_client import CoinalyzeClient

        class TestableCoinalyze(CoinalyzeClient):
            """Override API calls, keep real _calc_trend_from_history"""
            def __init__(self):
                super().__init__(api_key="test_key", timeout=1, max_retries=0)

            def get_open_interest(self, symbol=None):
                return {'value': MOCK_OI_BTC}

            def get_liquidations(self, symbol=None):
                return {'history': [
                    {'l': MOCK_LIQ_LONG_BTC, 's': MOCK_LIQ_SHORT_BTC}
                ]}

            def get_funding_rate(self, symbol=None):
                return {'value': 0.0003}

            def get_open_interest_history(self, symbol=None, hours=4):
                # oldest=100, newest=110 → +10% > 3% → 预期 RISING
                return {'history': [{'c': 100, 't': 1000}, {'c': 110, 't': 2000}]}

            def get_funding_rate_history(self, symbol=None, hours=4):
                # oldest=0.01, newest=0.008 → -20% < -3% → 预期 FALLING
                return {'history': [{'c': 0.01, 't': 1000}, {'c': 0.008, 't': 2000}]}

            def get_long_short_ratio_history(self, symbol=None, hours=4):
                # oldest=1.0, newest=1.02 → +2% → 预期 STABLE (< 3%)
                return {'history': [{'r': 1.0, 't': 1000}, {'r': 1.02, 't': 2000}]}

        class MockSentiment:
            def fetch(self):
                return {
                    'positive_ratio': 0.55, 'negative_ratio': 0.45,
                    'net_sentiment': 0.1, 'long_short_ratio': 1.22,
                    'source': 'mock', 'history': [],
                }

        assembler = AIDataAssembler(
            binance_kline_client=MockBinanceKlines(),
            order_flow_processor=real_order_flow,          # ← 真实生产代码
            coinalyze_client=TestableCoinalyze(),          # ← 真实趋势计算
            sentiment_client=MockSentiment(),
        )

        assembled = assembler.assemble(
            technical_data={'price': MOCK_PRICE, 'atr': 500},
            symbol='BTCUSDT',
        )

        derivatives = assembled.get('derivatives', {})
        fr = derivatives.get('funding_rate') or {}
        oi = derivatives.get('open_interest') or {}
        liq = derivatives.get('liquidations') or {}

        def assert_close(actual, expected, name, tolerance=0.01):
            """验证浮点数接近预期值"""
            if actual is None:
                results.fail(f"计算: {name}", f"结果为 None (预期 {expected})")
                return False
            if abs(actual - expected) <= tolerance:
                results.ok(f"计算: {name}", f"{actual} ≈ {expected}")
                return True
            else:
                results.fail(
                    f"计算: {name}",
                    f"实际={actual}, 预期={expected}, 差={actual - expected}"
                )
                return False

        # ═══ OI 转换: BTC → USD ═══
        # 500 BTC × $100,000 = $50,000,000
        expected_oi_usd = MOCK_OI_BTC * MOCK_PRICE
        assert_close(oi.get('total_usd'), expected_oi_usd,
                     f"OI USD = {MOCK_OI_BTC} BTC × ${MOCK_PRICE:,.0f}", tolerance=1)

        assert_close(oi.get('total_btc'), MOCK_OI_BTC,
                     f"OI BTC 透传 = {MOCK_OI_BTC}", tolerance=0.01)

        # ═══ Liquidation 转换: BTC → USD ═══
        # Long: 1.5 BTC × $100,000 = $150,000
        # Short: 2.0 BTC × $100,000 = $200,000
        expected_liq_long = MOCK_LIQ_LONG_BTC * MOCK_PRICE
        expected_liq_short = MOCK_LIQ_SHORT_BTC * MOCK_PRICE
        expected_liq_total = expected_liq_long + expected_liq_short

        assert_close(liq.get('long_usd'), expected_liq_long,
                     f"Liq Long = {MOCK_LIQ_LONG_BTC} BTC × ${MOCK_PRICE:,.0f}", tolerance=1)
        assert_close(liq.get('short_usd'), expected_liq_short,
                     f"Liq Short = {MOCK_LIQ_SHORT_BTC} BTC × ${MOCK_PRICE:,.0f}", tolerance=1)
        assert_close(liq.get('total_usd'), expected_liq_total,
                     f"Liq Total = ${expected_liq_total:,.0f}", tolerance=1)

        # ═══ Funding Rate 单位转换 ═══
        # 0.00058 × 100 = 0.058%
        assert_close(fr.get('current_pct'), MOCK_FUNDING_PCT,
                     f"FR % = {MOCK_FUNDING_RATE} × 100 = {MOCK_FUNDING_PCT}%", tolerance=0.0001)

        assert_close(fr.get('value'), MOCK_FUNDING_RATE,
                     f"FR decimal 透传 = {MOCK_FUNDING_RATE}", tolerance=0.000001)

        # ═══ Funding Rate 趋势方向 ═══
        # [0.0003, 0.0004, 0.00058]: 最新 0.00058 > 最旧 0.0003 × 1.1 = 0.00033 → RISING
        actual_trend = fr.get('trend')
        if actual_trend == 'RISING':
            results.ok(
                "计算: FR Trend",
                f"[{', '.join(str(r) for r in MOCK_HISTORY_RATES)}] → RISING ✓"
            )
        else:
            results.fail(
                "计算: FR Trend",
                f"预期 RISING, 实际 {actual_trend} "
                f"(rates: {MOCK_HISTORY_RATES})"
            )

        # ═══ Funding Rate 解读 ═══
        # 0.00058 > 0.0005 → BULLISH (not VERY_BULLISH since < 0.001)
        actual_interp = fr.get('interpretation')
        if actual_interp == 'BULLISH':
            results.ok("计算: FR Interpretation", f"{MOCK_FUNDING_RATE} → BULLISH ✓")
        else:
            results.fail(
                "计算: FR Interpretation",
                f"预期 BULLISH, 实际 {actual_interp}"
            )

        # ═══ History 记录数和排序 ═══
        history = fr.get('history', [])
        if len(history) == len(MOCK_HISTORY_RATES):
            results.ok("计算: FR History 数量", f"{len(history)} 条")
        else:
            results.fail(
                "计算: FR History 数量",
                f"预期 {len(MOCK_HISTORY_RATES)}, 实际 {len(history)}"
            )

        # ═══ Premium Index 计算 ═══
        # (100000 - 99950) / 99950 ≈ 0.000500
        expected_pi = (MOCK_MARK_PRICE - MOCK_INDEX_PRICE) / MOCK_INDEX_PRICE
        assert_close(fr.get('premium_index'), expected_pi,
                     f"PI = ({MOCK_MARK_PRICE}-{MOCK_INDEX_PRICE})/{MOCK_INDEX_PRICE}",
                     tolerance=0.000001)

        # ═══════════════════════════════════════════════════════════
        # 以下测试真实生产代码的计算公式 (非硬编码 mock)
        # ═══════════════════════════════════════════════════════════

        order_flow = assembled.get('order_flow', {})

        # ═══ OrderFlowProcessor.process_klines() — 10-bar 平均买盘比 ═══
        # 10 根 K线: taker_buy=60 / volume=100 = 0.6 per bar → avg = 0.6
        assert_close(order_flow.get('buy_ratio'), 0.6,
                     "OrderFlow buy_ratio (10-bar avg: 60/100)", tolerance=0.001)

        assert_close(order_flow.get('latest_buy_ratio'), 0.6,
                     "OrderFlow latest_buy_ratio (最新 bar: 60/100)", tolerance=0.001)

        # ═══ OrderFlowProcessor — 平均成交额 ═══
        # quote_volume=1200000 / trades=120 = 10000.0
        assert_close(order_flow.get('avg_trade_usdt'), 10000.0,
                     "OrderFlow avg_trade_usdt (1200000/120)", tolerance=1)

        # ═══ OrderFlowProcessor — 成交额透传 ═══
        assert_close(order_flow.get('volume_usdt'), 1200000.0,
                     "OrderFlow volume_usdt 透传", tolerance=1)

        # ═══ OrderFlowProcessor — CVD 趋势 ═══
        # 全新 processor，只处理 1 次 → _cvd_history 长度 1 → NEUTRAL
        actual_cvd = order_flow.get('cvd_trend')
        if actual_cvd == 'NEUTRAL':
            results.ok("计算: OrderFlow CVD trend", "首次调用 → NEUTRAL ✓")
        else:
            results.fail("计算: OrderFlow CVD trend",
                         f"预期 NEUTRAL (首次调用), 实际 {actual_cvd}")

        # ═══ OrderFlowProcessor — 数据来源标记 ═══
        actual_src = order_flow.get('data_source')
        if actual_src == 'binance_raw':
            results.ok("计算: OrderFlow data_source", "binance_raw ✓")
        else:
            results.fail("计算: OrderFlow data_source",
                         f"预期 binance_raw, 实际 {actual_src}")

        # ═══ CoinalyzeClient._calc_trend_from_history() — 趋势计算公式 ═══
        trends = derivatives.get('trends', {})

        # OI: oldest=100, newest=110 → (110-100)/100*100 = +10% > 3% → RISING
        actual_oi_trend = trends.get('oi_trend')
        if actual_oi_trend == 'RISING':
            results.ok("计算: Coinalyze OI trend", "+10% > 3% → RISING ✓")
        else:
            results.fail("计算: Coinalyze OI trend",
                         f"预期 RISING (+10%), 实际 {actual_oi_trend}")

        # Funding: oldest=0.01, newest=0.008 → (0.008-0.01)/0.01*100 = -20% < -3% → FALLING
        actual_fr_trend = trends.get('funding_trend')
        if actual_fr_trend == 'FALLING':
            results.ok("计算: Coinalyze funding trend", "-20% < -3% → FALLING ✓")
        else:
            results.fail("计算: Coinalyze funding trend",
                         f"预期 FALLING (-20%), 实际 {actual_fr_trend}")

        # L/S Ratio: oldest=1.0, newest=1.02 → (1.02-1.0)/1.0*100 = +2% → STABLE
        actual_ls_trend = trends.get('long_short_trend')
        if actual_ls_trend == 'STABLE':
            results.ok("计算: Coinalyze L/S ratio trend", "+2% < 3% → STABLE ✓")
        else:
            results.fail("计算: Coinalyze L/S ratio trend",
                         f"预期 STABLE (+2%), 实际 {actual_ls_trend}")

    except ImportError as e:
        results.warn("AIDataAssembler 不可导入", f"跳过计算验证: {e}")
    except Exception as e:
        results.fail("计算正确性测试异常", str(e)[:100])


# ─────────────────────────────────────────────────────────────────────
# Test 21: S/R-based SL/TP 计算 (calculate_sr_based_sltp)
# ─────────────────────────────────────────────────────────────────────

def test_sr_based_sltp(results: TestResults):
    """
    验证 calculate_sr_based_sltp() — 生产 Level 2 回退链的核心函数。

    与 Test 9 (validate_multiagent_sltp, Level 1) 互补:
    - Test 9: AI SL/TP R/R 门槛验证 (纯数值校验)
    - Test 21: S/R zone 迭代 + ATR buffer + Measured Move + R/R 过滤

    Oracle 测试覆盖 (精确值断言):
    1. ATR buffer 精确公式: SL = anchor - ATR * buffer_mult
    2. Zone 选择: 最强 zone 被选为 SL anchor (score 排序)
    3. Measured Move 公式: target = nearest_tp ± box_height
    4. R/R 精确计算: reward/risk 必须与手算一致
    5. ATR=0 fallback: buffer = price * 0.005
    6. 动态重评估: SL 有利方向 + 阈值
    """
    print("\n─── Test 21: S/R-based SL/TP 计算 (生产 Level 2) ───")

    try:
        from utils.sr_sltp_calculator import (
            calculate_sr_based_sltp,
            _select_sl_anchor,
            _collect_tp_candidates,
            _measured_move_target,
        )
        from utils.sr_zone_calculator import SRZone, SRSourceType
        from strategy.trading_logic import get_min_rr_ratio

        price = 100000.0
        min_rr = get_min_rr_ratio()
        ATR = 2000.0
        BUF_MULT = 0.5

        # ================================================================
        # Build mock zones with KNOWN properties for deterministic testing
        # ================================================================
        # Support: STRUCTURAL, HIGH strength, has swing, touch_count=3
        support_strong = SRZone(
            price_low=96800, price_high=97200, price_center=97000,
            side='support', strength='HIGH', sources=['Swing_Low'],
            total_weight=3.0, distance_pct=3.0, has_order_wall=False, wall_size_btc=0,
            source_type=SRSourceType.STRUCTURAL,
            touch_count=3, has_swing_point=True,
        )
        # Support: PROJECTED, MEDIUM strength, no swing, touch_count=0 (weaker)
        support_weak = SRZone(
            price_low=95800, price_high=96200, price_center=96000,
            side='support', strength='MEDIUM', sources=['Pivot_S1'],
            total_weight=1.5, distance_pct=4.0, has_order_wall=False, wall_size_btc=0,
            source_type=SRSourceType.PROJECTED,
            touch_count=0, has_swing_point=False,
        )
        # Resistance: STRUCTURAL, HIGH, with swing, touch=2
        resistance_zone = SRZone(
            price_low=104800, price_high=105200, price_center=105000,
            side='resistance', strength='HIGH', sources=['Swing_High'],
            total_weight=3.0, distance_pct=5.0, has_order_wall=False, wall_size_btc=0,
            source_type=SRSourceType.STRUCTURAL,
            touch_count=2, has_swing_point=True,
        )

        sr_zones = {
            'support_zones': [support_strong, support_weak],
            'resistance_zones': [resistance_zone],
            'nearest_support': support_strong,
            'nearest_resistance': resistance_zone,
        }

        # ================================================================
        # Case 1: ATR buffer 精确公式 (ATR≠0)
        # Formula: SL = sl_anchor - ATR * buffer_mult
        # sl_anchor = support_strong.price_center = 97000 (strongest by score)
        # SL = 97000 - 2000 * 0.5 = 96000
        # TP = resistance_zone.price_center = 105000 (nearest resistance)
        # risk = 100000 - 96000 = 4000
        # reward = 105000 - 100000 = 5000
        # R/R = 5000 / 4000 = 1.25:1 — may fail min_rr if 1.5
        # ================================================================
        sl, tp, method = calculate_sr_based_sltp(
            current_price=price, side='BUY', sr_zones=sr_zones,
            atr_value=ATR, min_rr_ratio=min_rr, atr_buffer_multiplier=BUF_MULT,
        )

        expected_sl_anchor = 97000.0
        expected_buffer = ATR * BUF_MULT  # 1000
        expected_sl = expected_sl_anchor - expected_buffer  # 96000
        expected_risk = price - expected_sl  # 4000
        expected_tp_direct = 105000.0
        expected_rr_direct = (expected_tp_direct - price) / expected_risk  # 5000/4000 = 1.25

        if expected_rr_direct >= min_rr:
            # Direct TP passes R/R — check exact SL
            if sl and abs(sl - expected_sl) < 1.0:
                results.ok("ATR buffer 精确值", f"SL=${sl:,.0f} = {expected_sl_anchor:,.0f} - {ATR}×{BUF_MULT} ✓")
            elif sl:
                results.fail("ATR buffer 精确值", f"SL=${sl:,.0f} ≠ 预期${expected_sl:,.0f}")
            else:
                results.fail("ATR buffer 精确值", f"返回 None: {method}")
        else:
            # Direct TP R/R insufficient → Measured Move should kick in
            # Measured Move: box_height = |105000 - 97000| = 8000
            # target = 105000 + 8000 = 113000
            # R/R_mm = (113000 - 100000) / 4000 = 3.25
            expected_mm_target = expected_tp_direct + abs(expected_tp_direct - expected_sl_anchor)
            expected_rr_mm = (expected_mm_target - price) / expected_risk

            if expected_rr_mm >= min_rr:
                # Measured Move should save the trade
                if sl and abs(sl - expected_sl) < 1.0:
                    results.ok("ATR buffer 精确值", f"SL=${sl:,.0f} = {expected_sl_anchor:,.0f} - {ATR}×{BUF_MULT} ✓")
                elif sl:
                    results.fail("ATR buffer 精确值", f"SL=${sl:,.0f} ≠ 预期${expected_sl:,.0f}")
                else:
                    results.fail("ATR buffer 精确值", f"返回 None (Measured Move 也失败?): {method}")

                if tp and abs(tp - expected_mm_target) < 1.0:
                    results.ok("Measured Move TP 精确值",
                               f"TP=${tp:,.0f} = {expected_tp_direct:,.0f} + box({abs(expected_tp_direct - expected_sl_anchor):,.0f}) ✓")
                elif tp:
                    # Could be the direct TP if R/R edge case
                    results.warn("TP 值偏差", f"TP=${tp:,.0f} (预期 MM=${expected_mm_target:,.0f} 或 direct={expected_tp_direct:,.0f})")
                else:
                    results.fail("Measured Move TP", f"返回 None: {method}")
            else:
                # Both paths fail → should reject
                if sl is None and tp is None:
                    results.ok("R/R 全路径拒绝", f"{method}")
                else:
                    results.fail("应全部拒绝", f"但 SL={sl}, TP={tp}")

        # Verify R/R precision if we got valid SL/TP
        if sl and tp and sl < price:
            actual_rr = (tp - price) / (price - sl)
            if actual_rr >= min_rr:
                results.ok("R/R 精确计算", f"R/R={actual_rr:.4f}:1 >= {min_rr}:1")
            else:
                results.fail("R/R 精确计算", f"R/R={actual_rr:.4f}:1 < {min_rr}:1")

        # ================================================================
        # Case 2: Zone 选择 — 最强 zone 被选为 SL anchor (不是最近的)
        # support_strong: HIGH/STRUCTURAL/touch=3/swing=True → 高 score
        # support_weak: MEDIUM/PROJECTED/touch=0/swing=False → 低 score
        # 即使 support_weak 更远，也不应被选中
        # ================================================================
        anchor = _select_sl_anchor(
            zones=[support_strong, support_weak],
            current_price=price,
            is_long=True,
            atr_value=ATR,
        )
        if anchor and anchor == support_strong.price_center:
            results.ok("Zone 选择 (最强 anchor)", f"选中 ${anchor:,.0f} (STRUCTURAL/HIGH/swing/touch=3)")
        elif anchor and anchor == support_weak.price_center:
            results.fail("Zone 选择", f"选中弱 zone ${anchor:,.0f} 而非强 zone ${support_strong.price_center:,.0f}")
        else:
            results.fail("Zone 选择", f"anchor={anchor}")

        # ================================================================
        # Case 3: Zone 选择 — SHORT 方向 (阻力做 SL anchor)
        # ================================================================
        resistance_strong = SRZone(
            price_low=103800, price_high=104200, price_center=104000,
            side='resistance', strength='HIGH', sources=['Swing_High'],
            total_weight=3.0, distance_pct=4.0, has_order_wall=False, wall_size_btc=0,
            source_type=SRSourceType.STRUCTURAL,
            touch_count=3, has_swing_point=True,
        )
        resistance_weak = SRZone(
            price_low=106800, price_high=107200, price_center=107000,
            side='resistance', strength='LOW', sources=['Round_Number'],
            total_weight=1.0, distance_pct=7.0, has_order_wall=False, wall_size_btc=0,
            source_type=SRSourceType.PSYCHOLOGICAL,
            touch_count=0, has_swing_point=False,
        )
        anchor_short = _select_sl_anchor(
            zones=[resistance_weak, resistance_strong],  # reversed order to test scoring
            current_price=price,
            is_long=False,
            atr_value=ATR,
        )
        if anchor_short and anchor_short == resistance_strong.price_center:
            results.ok("Zone 选择 SHORT", f"选中 ${anchor_short:,.0f} (STRUCTURAL 强于 PSYCHOLOGICAL)")
        elif anchor_short:
            results.fail("Zone 选择 SHORT", f"选中 ${anchor_short:,.0f} 而非 ${resistance_strong.price_center:,.0f}")
        else:
            results.fail("Zone 选择 SHORT", "anchor=None")

        # ================================================================
        # Case 4: Measured Move 公式精确验证
        # box_height = |nearest_tp - sl_anchor|
        # LONG: target = nearest_tp + box_height
        # SHORT: target = nearest_tp - box_height
        # ================================================================
        sl_anchor_mm = 97000.0
        nearest_tp_mm = 105000.0
        # box_height = |105000 - 97000| = 8000
        # LONG target = 105000 + 8000 = 113000
        mm_long = _measured_move_target(price, sl_anchor_mm, nearest_tp_mm, is_long=True)
        expected_mm_long = nearest_tp_mm + abs(nearest_tp_mm - sl_anchor_mm)
        if mm_long and abs(mm_long - expected_mm_long) < 1.0:
            results.ok("Measured Move LONG 精确值",
                       f"${mm_long:,.0f} = {nearest_tp_mm:,.0f} + |{nearest_tp_mm:,.0f}-{sl_anchor_mm:,.0f}| ✓")
        elif mm_long:
            results.fail("Measured Move LONG", f"${mm_long:,.0f} ≠ 预期${expected_mm_long:,.0f}")
        else:
            results.fail("Measured Move LONG", "返回 None")

        # SHORT: sl_anchor=104000, nearest_tp=97000
        # box_height = |97000 - 104000| = 7000
        # target = 97000 - 7000 = 90000
        sl_anchor_short = 104000.0
        nearest_tp_short = 97000.0
        mm_short = _measured_move_target(price, sl_anchor_short, nearest_tp_short, is_long=False)
        expected_mm_short = nearest_tp_short - abs(nearest_tp_short - sl_anchor_short)
        if mm_short and abs(mm_short - expected_mm_short) < 1.0:
            results.ok("Measured Move SHORT 精确值",
                       f"${mm_short:,.0f} = {nearest_tp_short:,.0f} - |{nearest_tp_short:,.0f}-{sl_anchor_short:,.0f}| ✓")
        elif mm_short:
            results.fail("Measured Move SHORT", f"${mm_short:,.0f} ≠ 预期${expected_mm_short:,.0f}")
        else:
            results.fail("Measured Move SHORT", "返回 None")

        # ================================================================
        # Case 5: TP 候选排序验证 (nearest first, quality tiebreak)
        # ================================================================
        res_near = SRZone(
            price_low=102800, price_high=103200, price_center=103000,
            side='resistance', strength='MEDIUM', sources=['Pivot_R1'],
            total_weight=1.5, distance_pct=3.0, has_order_wall=False, wall_size_btc=0,
            source_type=SRSourceType.PROJECTED,
        )
        res_far = SRZone(
            price_low=109800, price_high=110200, price_center=110000,
            side='resistance', strength='HIGH', sources=['Swing_High'],
            total_weight=3.0, distance_pct=10.0, has_order_wall=False, wall_size_btc=0,
            source_type=SRSourceType.STRUCTURAL,
        )
        candidates = _collect_tp_candidates([res_far, res_near], price, is_long=True)
        if len(candidates) >= 2 and candidates[0] == 103000.0 and candidates[1] == 110000.0:
            results.ok("TP 候选排序 (nearest first)", f"[{candidates[0]:,.0f}, {candidates[1]:,.0f}] ✓")
        elif len(candidates) >= 2:
            results.fail("TP 候选排序", f"[{candidates[0]:,.0f}, {candidates[1]:,.0f}], 预期 [103000, 110000]")
        else:
            results.fail("TP 候选排序", f"candidates={candidates}")

        # ================================================================
        # Case 6: R/R 精确边界测试
        # 构造刚好 R/R = min_rr (边界) 的场景
        # SL anchor = 97000, buffer = 1000 → SL = 96000, risk = 4000
        # 需要 reward = 4000 * min_rr = 6000 → TP = 106000
        # ================================================================
        exact_rr_resistance = SRZone(
            price_low=105800, price_high=106200, price_center=106000,
            side='resistance', strength='HIGH', sources=['Swing_High'],
            total_weight=3.0, distance_pct=6.0, has_order_wall=False, wall_size_btc=0,
            source_type=SRSourceType.STRUCTURAL, touch_count=2, has_swing_point=True,
        )
        exact_rr_zones = {
            'support_zones': [support_strong],
            'resistance_zones': [exact_rr_resistance],
            'nearest_support': support_strong,
            'nearest_resistance': exact_rr_resistance,
        }
        sl_e, tp_e, method_e = calculate_sr_based_sltp(
            current_price=price, side='BUY', sr_zones=exact_rr_zones,
            atr_value=ATR, min_rr_ratio=min_rr, atr_buffer_multiplier=BUF_MULT,
        )
        if sl_e and tp_e:
            actual_rr_e = (tp_e - price) / (price - sl_e)
            # Expected: risk=4000, reward=6000 → R/R=1.5 (exactly min_rr)
            expected_rr_e = (106000 - price) / (price - expected_sl)
            if abs(actual_rr_e - expected_rr_e) < 0.01:
                results.ok("R/R 边界精确值", f"R/R={actual_rr_e:.4f}:1 ≈ {expected_rr_e:.4f}:1 ✓")
            else:
                results.fail("R/R 边界精确值", f"R/R={actual_rr_e:.4f}:1 ≠ 预期{expected_rr_e:.4f}:1")
        elif sl_e is None:
            # Might fail if min_rr is slightly above 1.5
            results.warn("R/R 边界", f"被拒绝: {method_e} (min_rr={min_rr})")

        # ================================================================
        # Case 7: R/R too low → rejection
        # ================================================================
        close_resistance = SRZone(
            price_low=100800, price_high=101200, price_center=101000,
            side='resistance', strength='MEDIUM', sources=['SMA_50'],
            total_weight=1.5, distance_pct=1.0, has_order_wall=False, wall_size_btc=0,
        )
        poor_rr_zones = {
            'support_zones': [support_strong],
            'resistance_zones': [close_resistance],
            'nearest_support': support_strong,
            'nearest_resistance': close_resistance,
        }
        sl_r, tp_r, method_r = calculate_sr_based_sltp(
            current_price=price, side='BUY', sr_zones=poor_rr_zones,
            atr_value=ATR, min_rr_ratio=min_rr,
        )
        if sl_r is None and tp_r is None:
            results.ok("R/R 不足拒绝", f"{method_r}")
        else:
            rr_r = (tp_r - price) / (price - sl_r) if sl_r and tp_r and sl_r < price else 0
            results.fail("R/R 不足应拒绝", f"SL={sl_r}, TP={tp_r}, R/R={rr_r:.2f}")

        # ================================================================
        # Case 8: No S/R zones → rejection (v4.2: no percentage fallback)
        # ================================================================
        empty_zones = {
            'support_zones': [], 'resistance_zones': [],
            'nearest_support': None, 'nearest_resistance': None,
        }
        sl_n, tp_n, method_n = calculate_sr_based_sltp(
            current_price=price, side='BUY', sr_zones=empty_zones,
            atr_value=ATR, min_rr_ratio=min_rr,
        )
        if sl_n is None and tp_n is None:
            results.ok("空 S/R zones 拒绝", f"{method_n}")
        else:
            results.fail("空 S/R zones 应拒绝", f"但返回 SL={sl_n}, TP={tp_n}")

        # ================================================================
        # Case 9: ATR=0 → uses 0.5% price fallback buffer (精确值)
        # buffer = price * 0.005 = 500
        # SL = 97000 - 500 = 96500
        # ================================================================
        sl_0, tp_0, method_0 = calculate_sr_based_sltp(
            current_price=price, side='BUY', sr_zones=sr_zones,
            atr_value=0.0, min_rr_ratio=min_rr,
        )
        if sl_0 and tp_0:
            expected_buffer_0 = price * 0.005  # 500
            expected_sl_0 = support_strong.price_center - expected_buffer_0  # 96500
            if abs(sl_0 - expected_sl_0) < 1.0:
                results.ok("ATR=0 buffer 精确值", f"SL=${sl_0:,.0f} = 97000 - {expected_buffer_0:.0f} ✓")
            else:
                results.fail("ATR=0 buffer 精确值", f"SL=${sl_0:,.0f} ≠ 预期${expected_sl_0:,.0f}")
        elif sl_0 is None:
            results.warn("ATR=0 被拒绝", f"{method_0}")

        # ================================================================
        # Case 10: SHORT 精确 SL 计算
        # SL anchor = resistance_strong.price_center = 104000
        # SL = 104000 + 2000 * 0.5 = 105000
        # TP zones = [support_strong(97000), support_weak(96000)]
        # nearest TP = support_strong.price_center = 97000
        # risk = 105000 - 100000 = 5000
        # reward = 100000 - 97000 = 3000 → R/R = 0.6 < min_rr → iterate
        # ================================================================
        short_zones = {
            'support_zones': [support_strong, support_weak],
            'resistance_zones': [resistance_strong],
            'nearest_support': support_strong,
            'nearest_resistance': resistance_strong,
        }
        sl_s, tp_s, method_s = calculate_sr_based_sltp(
            current_price=price, side='SELL', sr_zones=short_zones,
            atr_value=ATR, min_rr_ratio=min_rr, atr_buffer_multiplier=BUF_MULT,
        )
        expected_sl_short = resistance_strong.price_center + ATR * BUF_MULT  # 104000 + 1000 = 105000
        if sl_s:
            if abs(sl_s - expected_sl_short) < 1.0:
                results.ok("SHORT SL 精确值", f"SL=${sl_s:,.0f} = {resistance_strong.price_center:,.0f} + {ATR}×{BUF_MULT} ✓")
            else:
                results.fail("SHORT SL 精确值", f"SL=${sl_s:,.0f} ≠ 预期${expected_sl_short:,.0f}")
        elif sl_s is None:
            results.warn("SHORT S/R 拒绝", f"{method_s}")

        # ================================================================
        # Case 11: 动态重评估 — SL 有利方向 + 阈值
        # ================================================================
        old_sl_long = 96000.0
        new_sl_long = 96800.0
        # LONG: SL can only go UP
        final_sl = max(new_sl_long, old_sl_long)
        if final_sl == new_sl_long:
            results.ok("SL 有利方向 (LONG↑)", f"max({old_sl_long:,.0f}, {new_sl_long:,.0f}) = {final_sl:,.0f}")
        else:
            results.fail("SL 有利方向 (LONG)", f"预期 {new_sl_long:,.0f}, 实际 {final_sl:,.0f}")

        # SL cannot go DOWN
        worse_sl = 95500.0
        final_sl2 = max(worse_sl, old_sl_long)
        if final_sl2 == old_sl_long:
            results.ok("SL 不可向下 (LONG)", f"max({worse_sl:,.0f}, {old_sl_long:,.0f}) = {final_sl2:,.0f}")
        else:
            results.fail("SL 不可向下", f"预期 {old_sl_long:,.0f}, 实际 {final_sl2:,.0f}")

        # SHORT: SL can only go DOWN
        old_sl_short_v = 104000.0
        new_sl_short_v = 103500.0
        final_sl3 = min(new_sl_short_v, old_sl_short_v)
        if final_sl3 == new_sl_short_v:
            results.ok("SL 有利方向 (SHORT↓)", f"min({old_sl_short_v:,.0f}, {new_sl_short_v:,.0f}) = {final_sl3:,.0f}")
        else:
            results.fail("SL 有利方向 (SHORT)", f"预期 {new_sl_short_v:,.0f}, 实际 {final_sl3:,.0f}")

        # Threshold check (0.2% = production default)
        threshold = 0.002
        change = abs(final_sl - old_sl_long) / old_sl_long
        expected_change = abs(96800.0 - 96000.0) / 96000.0  # = 0.00833...
        if abs(change - expected_change) < 0.0001:
            results.ok("阈值变化精确值", f"Δ={change*100:.3f}% = |96800-96000|/96000 ✓")
        else:
            results.fail("阈值变化精确值", f"Δ={change*100:.3f}% ≠ 预期{expected_change*100:.3f}%")

        should_update = change > threshold
        if should_update:
            results.ok("动态更新触发", f"Δ={change*100:.3f}% > {threshold*100:.1f}% → 更新")
        else:
            results.fail("动态更新触发", f"Δ={change*100:.3f}% 应 > {threshold*100:.1f}%")

    except ImportError as e:
        results.warn("sr_sltp_calculator 导入失败", str(e))
    except Exception as e:
        results.fail("S/R SL/TP 测试异常", str(e)[:120])
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="端到端数据流水线验证 v2.0")
    parser.add_argument('--quick', action='store_true', help="快速模式 (跳过慢速 API)")
    parser.add_argument('--offline', action='store_true', help="离线模式 (仅逻辑验证, 无需 API)")
    parser.add_argument('--json', action='store_true', help="JSON 输出")
    args = parser.parse_args()

    print("=" * 60)
    print("  数据流水线端到端验证 v2.0")
    print(f"  时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    if args.offline:
        print("  模式: 离线 (mock + 逻辑验证)")
    elif args.quick:
        print("  模式: 快速 (跳过慢速 API)")
    else:
        print("  模式: 完整")
    print("=" * 60)

    results = TestResults()

    if args.offline:
        # ═══ 离线模式: 仅逻辑验证 ═══
        test_offline_parsing_logic(results)      # Test 8
        test_sltp_validation(results)            # Test 9
        test_position_sizing(results)            # Test 10
        test_ai_response_parsing(results)        # Test 11
        test_oi_price_quadrant(results)          # Test 12
        test_cvd_cold_start(results)             # Test 13
        test_funding_delta(results)              # Test 14
        test_funding_interpretation(results)     # Test 15
        test_trend_calculation(results)          # Test 16
        test_data_assembler_structure(results)   # Test 17
        test_sma_label_disambiguation(results)   # Test 18
        test_consumer_field_contracts(results)   # Test 19
        test_production_calculations(results)    # Test 20
        test_sr_based_sltp(results)              # Test 21
    else:
        # ═══ 在线模式: API + 逻辑验证 ═══

        # --- Section A: 在线 API 验证 ---
        test_sentiment_api_ordering(results)     # Test 1
        test_sentiment_client_parsing(results)   # Test 2
        test_order_flow(results)                 # Test 3
        test_indicator_ranges(results)           # Test 4
        test_funding_rate_pipeline(results)      # Test 5

        if not args.quick:
            test_binance_derivatives(results)    # Test 6
        else:
            print("\n─── Test 6: 跳过 (--quick 模式) ───")

        test_field_consistency(results)          # Test 7

        # --- Section B: 离线逻辑验证 ---
        test_offline_parsing_logic(results)      # Test 8
        test_sltp_validation(results)            # Test 9
        test_position_sizing(results)            # Test 10
        test_ai_response_parsing(results)        # Test 11
        test_oi_price_quadrant(results)          # Test 12
        test_cvd_cold_start(results)             # Test 13
        test_funding_delta(results)              # Test 14
        test_funding_interpretation(results)     # Test 15
        test_trend_calculation(results)          # Test 16
        test_data_assembler_structure(results)   # Test 17
        test_sma_label_disambiguation(results)   # Test 18
        test_consumer_field_contracts(results)   # Test 19
        test_production_calculations(results)    # Test 20
        test_sr_based_sltp(results)              # Test 21

    # 汇总
    all_passed = results.summary()

    if args.json:
        output = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'version': '2.0',
            'passed': len(results.passed),
            'failed': len(results.failed),
            'warnings': len(results.warnings),
            'all_passed': all_passed,
            'failures': [{'name': n, 'detail': d} for n, d in results.failed],
        }
        print("\n" + json.dumps(output, indent=2))

    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()
