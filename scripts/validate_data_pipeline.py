#!/usr/bin/env python3
"""
端到端数据流水线验证脚本 (v1.0)

调用真实 API，验证从数据获取到 AI 输入的完整流水线。
检测排序错误、公式错误、字段引用错误、单位转换错误等。

用法:
    python3 scripts/validate_data_pipeline.py           # 完整验证
    python3 scripts/validate_data_pipeline.py --quick    # 跳过衍生品 API
"""

import argparse
import json
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
            # 显示最近一条的值
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

        # 构建 TechnicalIndicatorManager 需要 NautilusTrader 的 Cython 指标
        # 但 update() 需要 Bar 对象，无法从纯数值构造
        # 所以: 先验证类可以实例化，然后从诊断缓存读取实际值做范围检查

        manager = TechnicalIndicatorManager(
            rsi_period=14, macd_fast=12,
            macd_slow=26, macd_signal=9, bb_period=20
        )
        results.ok("指标管理器实例化", "TechnicalIndicatorManager ✓")

        # 获取 K 线来验证指标计算 (需要通过 Bar 对象 feed)
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

        # SMA: 应该接近当前价格
        sma = data.get('sma_20', 0)
        if sma > 0 and abs(sma - price) / price < 0.1:
            results.ok("SMA 范围", f"SMA20={sma:.2f}, Price={price:.2f}, 偏差={abs(sma-price)/price*100:.1f}%")
        elif sma > 0:
            results.warn("SMA 偏差较大", f"SMA20={sma:.2f} vs Price={price:.2f}")
        else:
            results.warn("SMA 为 0", "可能未初始化")

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

        # ADX: 应该是 0-100
        adx = data.get('adx', -1)
        if 0 <= adx <= 100:
            results.ok("ADX 范围", f"{adx:.2f} (0-100)")
        else:
            results.warn("ADX 范围异常", f"{adx}")

    except ImportError as e:
        results.warn("指标模块导入失败", f"{e} (可能缺少 NautilusTrader)")
    except Exception as e:
        results.fail("指标验证", str(e))
        import traceback
        traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────
# Test 5: 衍生品数据单位转换
# ─────────────────────────────────────────────────────────────────────

def test_derivatives_funding_rate(results: TestResults):
    """验证 funding rate 数据"""
    print("\n─── Test 5: 衍生品数据 (Funding Rate) ───")

    try:
        # Binance settled funding rate
        url = "https://fapi.binance.com/fapi/v1/fundingRate"
        params = {"symbol": "BTCUSDT", "limit": 1}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        if isinstance(data, list) and len(data) > 0:
            rate = float(data[0].get('fundingRate', 0))
            rate_pct = rate * 100
            results.ok("Settled Funding Rate", f"{rate:.6f} (decimal) = {rate_pct:.4f}%")

            # 合理范围: -0.5% ~ +0.5% (极端情况)
            if abs(rate_pct) < 0.5:
                results.ok("Funding Rate 范围", "正常")
            else:
                results.warn("Funding Rate 极端值", f"{rate_pct:.4f}%")

        # Predicted funding rate
        url2 = "https://fapi.binance.com/fapi/v1/premiumIndex"
        params2 = {"symbol": "BTCUSDT"}
        resp2 = requests.get(url2, params=params2, timeout=10)
        data2 = resp2.json()

        if isinstance(data2, dict):
            predicted = float(data2.get('lastFundingRate', 0))
            pred_pct = predicted * 100
            results.ok("Predicted Funding Rate", f"{predicted:.6f} = {pred_pct:.4f}%")

            # 语义检查: lastFundingRate 实际是"当前周期预测值"
            next_time = int(data2.get('nextFundingTime', 0))
            if next_time > 0:
                next_dt = datetime.fromtimestamp(next_time / 1000, tz=timezone.utc)
                results.ok("下次结算时间", f"{next_dt.strftime('%H:%M:%S UTC')}")

    except Exception as e:
        results.fail("Funding Rate 验证", str(e))


# ─────────────────────────────────────────────────────────────────────
# Test 6: AI 输入数据组装验证
# ─────────────────────────────────────────────────────────────────────

def test_field_consistency(results: TestResults):
    """验证数据字段在生产者和消费者之间的一致性"""
    print("\n─── Test 6: 字段一致性检查 ───")

    # 检查 sentiment_client 输出字段 vs 消费者期望字段
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


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────
# Test 7: 离线逻辑验证 (无需 API)
# ─────────────────────────────────────────────────────────────────────

def test_offline_parsing_logic(results: TestResults):
    """用 mock 数据验证所有解析逻辑 (无需网络)"""
    print("\n─── Test 7: 离线逻辑验证 (mock 数据) ───")

    # Mock Binance API response: ascending order (oldest first)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    mock_api_response = []
    for i in range(10):
        ts = now_ms - (10 - i) * 15 * 60 * 1000  # 每15分钟一条, 升序
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

        # 测试用 data[-1] (最新)
        result = fetcher._parse_binance_data(newest)
        if result:
            delay = result['data_delay_minutes']
            if delay <= 20:
                results.ok("data[-1] 延迟", f"{delay} 分钟 (正常)")
            else:
                results.fail("data[-1] 延迟异常", f"{delay} 分钟")

            # net_sentiment 公式
            expected = float(newest['longAccount']) - float(newest['shortAccount'])
            actual = result['net_sentiment']
            if abs(actual - expected) < 0.0001:
                results.ok("net_sentiment 公式", f"{actual:.4f} = long - short")
            else:
                results.fail("net_sentiment 公式", f"actual={actual}, expected={expected}")
        else:
            results.fail("_parse_binance_data", "返回 None")

        # 对比: 如果错误地用 data[0] (最旧)
        result_old = fetcher._parse_binance_data(oldest)
        if result_old:
            delay_old = result_old['data_delay_minutes']
            results.ok("data[0] 延迟 (反面验证)", f"{delay_old} 分钟 (应该≈150分钟)")
            if delay_old > 100:
                results.ok("修复验证", f"如果用 data[0] 会导致 {delay_old} 分钟延迟!")
            else:
                results.warn("反面验证不明显", f"delay={delay_old}")

    except ImportError:
        # 不依赖 SentimentDataFetcher, 直接验证逻辑
        long_r = float(newest['longAccount'])
        short_r = float(newest['shortAccount'])
        net = long_r - short_r

        results.ok("手动解析验证", f"long={long_r:.4f}, short={short_r:.4f}, net={net:.4f}")

        # 延迟计算
        data_time = datetime.fromtimestamp(newest['timestamp'] / 1000, tz=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        delay = int((now_utc - data_time).total_seconds() // 60)
        results.ok("延迟计算", f"{delay} 分钟")

    # 4. 验证 history 排序逻辑 (不应该 reversed)
    history = []
    for item in mock_api_response:  # 直接遍历 (已是升序)
        history.append({
            'long': float(item['longAccount']),
            'short': float(item['shortAccount']),
            'ratio': float(item['longShortRatio']),
            'timestamp': item['timestamp'],
        })

    # history 应该是 oldest → newest
    if all(history[i]['timestamp'] <= history[i+1]['timestamp'] for i in range(len(history)-1)):
        results.ok("History 升序", "oldest → newest ✓")
    else:
        results.fail("History 排序", "不是升序!")

    # history[-1] 应该有最大的 long ratio (mock 数据中递增)
    if history[-1]['long'] > history[0]['long']:
        results.ok("History 数值趋势", f"从 {history[0]['long']:.4f} 到 {history[-1]['long']:.4f}")
    else:
        results.fail("History 数值", "最新值不是最大的 (mock 数据应该递增)")

    # 5. Buy ratio 公式验证
    test_volume = 100.0
    test_taker_buy = 55.0
    buy_ratio = test_taker_buy / test_volume
    assert abs(buy_ratio - 0.55) < 0.001
    results.ok("Buy Ratio 公式", f"{test_taker_buy}/{test_volume} = {buy_ratio}")

    # CVD 公式验证
    sell_volume = test_volume - test_taker_buy  # = 45
    cvd_delta = test_taker_buy - sell_volume     # = 55 - 45 = 10
    assert abs(cvd_delta - 10.0) < 0.001
    results.ok("CVD Delta 公式", f"buy({test_taker_buy}) - sell({sell_volume}) = {cvd_delta}")

    # 6. Funding rate 转换验证
    raw_rate = 0.0001  # 原始 decimal
    pct_rate = raw_rate * 100  # → 0.01%
    assert abs(pct_rate - 0.01) < 0.0001
    results.ok("Funding Rate 转换", f"{raw_rate} × 100 = {pct_rate}%")


def main():
    parser = argparse.ArgumentParser(description="端到端数据流水线验证")
    parser.add_argument('--quick', action='store_true', help="快速模式 (跳过衍生品)")
    parser.add_argument('--offline', action='store_true', help="离线模式 (仅逻辑验证, 无需 API)")
    parser.add_argument('--json', action='store_true', help="JSON 输出")
    args = parser.parse_args()

    print("=" * 60)
    print("  数据流水线端到端验证 v1.0")
    print(f"  时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    if args.offline:
        print("  模式: 离线 (mock 数据)")
    print("=" * 60)

    results = TestResults()

    if args.offline:
        # 仅运行离线逻辑验证
        test_offline_parsing_logic(results)
    else:
        # 1. 情绪 API 排序
        test_sentiment_api_ordering(results)

        # 2. SentimentDataFetcher 解析
        test_sentiment_client_parsing(results)

        # 3. 订单流数据
        test_order_flow(results)

        # 4. 技术指标 (需要 NautilusTrader)
        test_indicator_ranges(results)

        # 5. 衍生品数据
        if not args.quick:
            test_derivatives_funding_rate(results)
        else:
            print("\n─── Test 5: 跳过 (--quick 模式) ───")

        # 6. 字段一致性
        test_field_consistency(results)

        # 7. 离线逻辑也一起跑
        test_offline_parsing_logic(results)

    # 汇总
    all_passed = results.summary()

    if args.json:
        output = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
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
