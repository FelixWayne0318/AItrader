#!/usr/bin/env python3
"""
支撑阻力位全面诊断脚本 v1.2

功能:
1. 检查所有支撑阻力数据来源
2. 对比不同计算方式的结果
3. 检查实盘服务的日志和缓存
4. 分析 Telegram Heartbeat 使用的数据
5. 给出诊断报告和修复建议
6. v1.1: 价格分布极值检测 (类似 Volume Profile)
7. v1.2: S/R 检测回测验证 (验证检测准确率)

使用方法:
    python3 scripts/diagnose_sr_zones.py
    python3 scripts/diagnose_sr_zones.py --export  # 导出到文件
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def print_header(title: str):
    """打印标题"""
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)
    print()


def print_section(title: str):
    """打印章节"""
    print()
    print(f"┌{'─' * 68}┐")
    print(f"│  {title:<64}  │")
    print(f"└{'─' * 68}┘")
    print()


def print_result(label: str, value: Any, status: str = "info"):
    """打印结果"""
    emoji = {"ok": "✅", "warn": "⚠️", "error": "❌", "info": "📊"}.get(status, "•")
    print(f"  {emoji} {label}: {value}")


def get_current_price() -> float:
    """获取当前 BTC 价格"""
    try:
        import requests
        resp = requests.get(
            "https://fapi.binance.com/fapi/v1/ticker/price",
            params={"symbol": "BTCUSDT"},
            timeout=10
        )
        return float(resp.json()["price"])
    except Exception as e:
        print(f"  ⚠️ 无法获取价格: {e}")
        return 0.0


def calculate_simple_high_low(bars: int = 20) -> Tuple[float, float]:
    """计算简单高低点 (模拟 TechnicalIndicatorManager)"""
    try:
        import requests
        resp = requests.get(
            "https://fapi.binance.com/fapi/v1/klines",
            params={"symbol": "BTCUSDT", "interval": "15m", "limit": bars},
            timeout=10
        )
        klines = resp.json()
        lows = [float(k[3]) for k in klines]  # Low price
        highs = [float(k[2]) for k in klines]  # High price
        return min(lows), max(highs)
    except Exception as e:
        print(f"  ⚠️ 无法计算简单高低点: {e}")
        return 0.0, 0.0


def calculate_sr_zones_with_orderwall(current_price: float) -> Dict[str, Any]:
    """使用 S/R Zone Calculator (含 Order Wall) 计算"""
    try:
        from utils.sr_zone_calculator import SRZoneCalculator
        from utils.binance_orderbook_client import BinanceOrderBookClient
        from utils.orderbook_processor import OrderBookProcessor
        from indicators.technical_manager import TechnicalIndicatorManager
        import requests

        # 获取技术数据
        resp = requests.get(
            "https://fapi.binance.com/fapi/v1/klines",
            params={"symbol": "BTCUSDT", "interval": "15m", "limit": 100},
            timeout=10
        )
        klines = resp.json()

        # 初始化指标管理器
        from nautilus_trader.model.data import Bar, BarType
        from nautilus_trader.model.objects import Price, Quantity
        from nautilus_trader.core.datetime import dt_to_unix_nanos
        manager = TechnicalIndicatorManager()

        for k in klines:
            class MockBar:
                def __init__(self, o, h, l, c, v, ts):
                    self.open = Price.from_str(str(o))
                    self.high = Price.from_str(str(h))
                    self.low = Price.from_str(str(l))
                    self.close = Price.from_str(str(c))
                    self.volume = Quantity.from_str(str(v))
                    self.ts_event = ts

            bar = MockBar(k[1], k[2], k[3], k[4], k[5], int(k[0]) * 1_000_000)
            manager.update(bar)

        tech_data = manager.get_technical_data(current_price)

        # 获取订单簿数据
        orderbook_client = BinanceOrderBookClient(timeout=10)
        raw_orderbook = orderbook_client.get_order_book(symbol="BTCUSDT", limit=100)

        orderbook_processor = OrderBookProcessor()
        orderbook_data = orderbook_processor.process(
            order_book=raw_orderbook,
            current_price=current_price,
            volatility=0.02
        )

        # 提取异常 (Order Wall)
        orderbook_anomalies = None
        if orderbook_data and orderbook_data.get('_status', {}).get('code') == 'OK':
            orderbook_anomalies = orderbook_data.get('anomalies', {})

        # 计算 S/R Zones
        sr_calc = SRZoneCalculator()
        bb_data = {
            'upper': tech_data.get('bb_upper', 0),
            'lower': tech_data.get('bb_lower', 0),
            'middle': tech_data.get('sma_20', 0),
        }
        sma_data = {
            'sma_50': tech_data.get('sma_50', 0),
            'sma_200': tech_data.get('sma_200', 0),
        }

        result = sr_calc.calculate_with_detailed_report(
            current_price=current_price,
            bb_data=bb_data,
            sma_data=sma_data,
            orderbook_anomalies=orderbook_anomalies,
        )

        return {
            'success': True,
            'result': result,
            'tech_data': tech_data,
            'orderbook_anomalies': orderbook_anomalies,
        }

    except Exception as e:
        import traceback
        return {
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc(),
        }


def calculate_price_distribution_sr(
    price_min: float = 55000,
    price_max: float = 70000,
    interval: float = 1000,
    bars: int = 500,
    current_price: float = 0,
    min_distance_pct: float = 1.0,  # 排除当前价格 ±1% 内的峰值
) -> Dict[str, Any]:
    """
    价格分布极值检测 v2.0 (Volume Profile 风格)

    基于全球标准做法:
    - CME Market Profile: POC, Value Area, HVN/LVN
    - Swing Point Detection: Left/Right lookback
    - IEEE Research: Kernel Density based S/R

    方法:
    1. 获取历史K线数据
    2. 统计每个价格区间的触及频率和成交量
    3. 计算 POC (Point of Control) 和 Value Area (70%)
    4. 找出 HVN (High Volume Nodes) 作为支撑阻力
    5. 排除当前价格附近的峰值 (避免误识别)

    参数:
    - price_min: 价格区间下限
    - price_max: 价格区间上限
    - interval: 每个区间的宽度
    - bars: 使用多少根K线
    - current_price: 当前价格 (用于过滤)
    - min_distance_pct: 最小距离阈值 (排除当前价格 ±N% 内的峰值)

    返回:
    - 价格分布直方图
    - POC (Point of Control)
    - Value Area (VA High / VA Low)
    - HVN (High Volume Nodes) 作为 S/R
    """
    try:
        import requests
        import numpy as np

        # 获取历史K线
        resp = requests.get(
            "https://fapi.binance.com/fapi/v1/klines",
            params={"symbol": "BTCUSDT", "interval": "15m", "limit": bars},
            timeout=30
        )
        klines = resp.json()

        if not klines:
            return {'success': False, 'error': 'No klines data'}

        # 创建价格区间
        bins = np.arange(price_min, price_max + interval, interval)
        bin_centers = (bins[:-1] + bins[1:]) / 2
        n_bins = len(bin_centers)

        # 统计每个区间的触及次数和成交量
        touch_count = np.zeros(n_bins)  # K线 high/low 落在该区间的次数
        volume_sum = np.zeros(n_bins)   # 该区间的成交量

        for k in klines:
            high = float(k[2])
            low = float(k[3])
            close = float(k[4])
            volume = float(k[5])

            # 统计 K 线覆盖的所有区间
            for i, (bin_low, bin_high) in enumerate(zip(bins[:-1], bins[1:])):
                # K 线覆盖了这个区间吗？
                if low <= bin_high and high >= bin_low:
                    touch_count[i] += 1
                    # 按覆盖比例分配成交量
                    overlap_low = max(low, bin_low)
                    overlap_high = min(high, bin_high)
                    if high > low:
                        overlap_ratio = (overlap_high - overlap_low) / (high - low)
                    else:
                        overlap_ratio = 1.0
                    volume_sum[i] += volume * overlap_ratio

        # 归一化
        touch_norm = touch_count / touch_count.max() if touch_count.max() > 0 else touch_count
        volume_norm = volume_sum / volume_sum.max() if volume_sum.max() > 0 else volume_sum

        # 综合得分 = 触及次数 * 0.5 + 成交量 * 0.5
        combined_score = touch_norm * 0.5 + volume_norm * 0.5

        # ========== POC (Point of Control) ==========
        # 成交量最高的价格区间
        poc_idx = np.argmax(volume_sum)
        poc_price = bin_centers[poc_idx]
        poc_volume = volume_sum[poc_idx]

        # ========== Value Area (70%) ==========
        # 从 POC 向两侧扩展，直到覆盖 70% 的总成交量
        total_volume = volume_sum.sum()
        target_volume = total_volume * 0.70

        va_low_idx = poc_idx
        va_high_idx = poc_idx
        current_volume = volume_sum[poc_idx]

        while current_volume < target_volume:
            # 向两侧扩展，选择成交量更大的一侧
            expand_low = volume_sum[va_low_idx - 1] if va_low_idx > 0 else 0
            expand_high = volume_sum[va_high_idx + 1] if va_high_idx < n_bins - 1 else 0

            if expand_low >= expand_high and va_low_idx > 0:
                va_low_idx -= 1
                current_volume += expand_low
            elif va_high_idx < n_bins - 1:
                va_high_idx += 1
                current_volume += expand_high
            else:
                break

        va_low = bin_centers[va_low_idx] - interval / 2
        va_high = bin_centers[va_high_idx] + interval / 2

        # ========== HVN Detection (High Volume Nodes) ==========
        # 检测局部极大值（峰值），排除当前价格附近
        peaks = []
        for i in range(1, n_bins - 1):
            if combined_score[i] > combined_score[i-1] and combined_score[i] > combined_score[i+1]:
                # 只保留得分较高的峰值 (> 0.3)
                if combined_score[i] > 0.3:
                    peak_price = bin_centers[i]

                    # v2.0: 排除当前价格附近的峰值
                    if current_price > 0:
                        distance_pct = abs(peak_price - current_price) / current_price * 100
                        if distance_pct < min_distance_pct:
                            continue  # 跳过太近的峰值

                    peaks.append({
                        'price': peak_price,
                        'score': round(combined_score[i], 3),
                        'touch_count': int(touch_count[i]),
                        'volume': round(volume_sum[i], 2),
                        'is_poc': (i == poc_idx),
                        'in_value_area': (va_low <= peak_price <= va_high),
                    })

        # 按得分排序
        peaks.sort(key=lambda x: x['score'], reverse=True)

        # ========== LVN Detection (Low Volume Nodes) ==========
        # 检测局部极小值（价格快速穿越区域）
        lvn = []
        for i in range(1, n_bins - 1):
            if combined_score[i] < combined_score[i-1] and combined_score[i] < combined_score[i+1]:
                if combined_score[i] < 0.2:  # 低成交量
                    lvn.append({
                        'price': bin_centers[i],
                        'score': round(combined_score[i], 3),
                    })

        # 创建分布数据
        distribution = []
        for i in range(n_bins):
            distribution.append({
                'range': f"${bins[i]:,.0f}-${bins[i+1]:,.0f}",
                'center': bin_centers[i],
                'touch_count': int(touch_count[i]),
                'volume': round(volume_sum[i], 2),
                'score': round(combined_score[i], 3),
                'is_poc': (i == poc_idx),
                'in_va': (va_low <= bin_centers[i] <= va_high),
            })

        return {
            'success': True,
            'distribution': distribution,
            'peaks': peaks,  # HVN = S/R candidates
            'lvn': lvn,      # Low Volume Nodes
            'poc': {
                'price': poc_price,
                'volume': round(poc_volume, 2),
            },
            'value_area': {
                'low': va_low,
                'high': va_high,
                'pct': round(current_volume / total_volume * 100, 1),
            },
            'bins': list(bins),
            'bars_analyzed': len(klines),
            'price_range': f"${price_min:,.0f} - ${price_max:,.0f}",
            'interval': interval,
        }

    except Exception as e:
        import traceback
        return {
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc(),
        }


def backtest_sr_detection(
    days: int = 3,
    interval: str = "15m",
    sr_tolerance_pct: float = 0.5,  # S/R 触及容差
    bounce_threshold_pct: float = 0.3,  # 反弹阈值
) -> Dict[str, Any]:
    """
    回测 S/R 检测准确率

    方法:
    1. 获取过去 N 天的 K 线数据
    2. 每隔一段时间计算 S/R (模拟实时检测)
    3. 检查后续价格是否在 S/R 处反弹
    4. 统计成功率

    参数:
    - days: 回测天数
    - interval: K 线周期
    - sr_tolerance_pct: 价格接近 S/R 的容差 (%)
    - bounce_threshold_pct: 判定反弹的最小幅度 (%)

    返回:
    - 各方法的成功率统计
    """
    try:
        import requests
        import numpy as np
        from datetime import datetime, timedelta

        # 计算需要多少根 K 线
        intervals_per_day = {
            "15m": 96,   # 24 * 4
            "1h": 24,
            "4h": 6,
        }
        bars_needed = days * intervals_per_day.get(interval, 96) + 100  # 额外 100 根用于计算

        # 获取历史 K 线
        resp = requests.get(
            "https://fapi.binance.com/fapi/v1/klines",
            params={"symbol": "BTCUSDT", "interval": interval, "limit": min(bars_needed, 1000)},
            timeout=30
        )
        klines = resp.json()

        if not klines or len(klines) < 200:
            return {'success': False, 'error': f'Insufficient data: {len(klines)} bars'}

        # 准备数据
        data = []
        for k in klines:
            data.append({
                'time': datetime.fromtimestamp(k[0] / 1000),
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5]),
            })

        # 回测结果
        results = {
            'simple_high_low': {'tests': 0, 'support_hits': 0, 'resistance_hits': 0, 'support_bounces': 0, 'resistance_bounces': 0},
            'value_area': {'tests': 0, 'support_hits': 0, 'resistance_hits': 0, 'support_bounces': 0, 'resistance_bounces': 0},
            'hvn': {'tests': 0, 'support_hits': 0, 'resistance_hits': 0, 'support_bounces': 0, 'resistance_bounces': 0},
        }

        test_events = []

        # 每 8 根 K 线 (2 小时) 做一次检测
        step = 8
        lookback = 100  # 用于计算 S/R 的历史数据量
        lookahead = 16  # 检查后续 16 根 K 线 (4 小时)

        for i in range(lookback, len(data) - lookahead, step):
            current_bar = data[i]
            current_price = current_bar['close']
            history = data[i-lookback:i]
            future = data[i:i+lookahead]

            # ========== 方法 1: 简单高低点 ==========
            lows = [d['low'] for d in history[-20:]]
            highs = [d['high'] for d in history[-20:]]
            support_simple = min(lows)
            resistance_simple = max(highs)

            # 检查未来是否触及并反弹
            future_lows = [d['low'] for d in future]
            future_highs = [d['high'] for d in future]
            future_closes = [d['close'] for d in future]

            results['simple_high_low']['tests'] += 1

            # 支撑测试: 价格是否接近支撑并反弹
            min_future_low = min(future_lows)
            if abs(min_future_low - support_simple) / support_simple * 100 < sr_tolerance_pct:
                results['simple_high_low']['support_hits'] += 1
                # 检查是否反弹 (之后价格上涨)
                min_idx = future_lows.index(min_future_low)
                if min_idx < len(future_closes) - 1:
                    bounce = (max(future_closes[min_idx:]) - min_future_low) / min_future_low * 100
                    if bounce > bounce_threshold_pct:
                        results['simple_high_low']['support_bounces'] += 1

            # 阻力测试: 价格是否接近阻力并回落
            max_future_high = max(future_highs)
            if abs(max_future_high - resistance_simple) / resistance_simple * 100 < sr_tolerance_pct:
                results['simple_high_low']['resistance_hits'] += 1
                max_idx = future_highs.index(max_future_high)
                if max_idx < len(future_closes) - 1:
                    rejection = (max_future_high - min(future_closes[max_idx:])) / max_future_high * 100
                    if rejection > bounce_threshold_pct:
                        results['simple_high_low']['resistance_bounces'] += 1

            # ========== 方法 2: Value Area ==========
            # 简化的 Volume Profile 计算
            price_min = min(d['low'] for d in history)
            price_max = max(d['high'] for d in history)
            bin_size = 500  # $500 区间

            bins = np.arange(price_min, price_max + bin_size, bin_size)
            if len(bins) < 3:
                continue

            bin_centers = (bins[:-1] + bins[1:]) / 2
            volume_sum = np.zeros(len(bin_centers))

            for d in history:
                for j, (bl, bh) in enumerate(zip(bins[:-1], bins[1:])):
                    if d['low'] <= bh and d['high'] >= bl:
                        overlap = (min(d['high'], bh) - max(d['low'], bl)) / (d['high'] - d['low']) if d['high'] > d['low'] else 1
                        volume_sum[j] += d['volume'] * overlap

            if volume_sum.sum() == 0:
                continue

            # POC 和 Value Area
            poc_idx = np.argmax(volume_sum)
            total_vol = volume_sum.sum()
            target_vol = total_vol * 0.70

            va_low_idx = va_high_idx = poc_idx
            current_vol = volume_sum[poc_idx]

            while current_vol < target_vol and (va_low_idx > 0 or va_high_idx < len(volume_sum) - 1):
                expand_low = volume_sum[va_low_idx - 1] if va_low_idx > 0 else 0
                expand_high = volume_sum[va_high_idx + 1] if va_high_idx < len(volume_sum) - 1 else 0

                if expand_low >= expand_high and va_low_idx > 0:
                    va_low_idx -= 1
                    current_vol += expand_low
                elif va_high_idx < len(volume_sum) - 1:
                    va_high_idx += 1
                    current_vol += expand_high
                else:
                    break

            va_low = bins[va_low_idx]
            va_high = bins[va_high_idx + 1]

            results['value_area']['tests'] += 1

            # VA Low 作为支撑测试
            if abs(min_future_low - va_low) / va_low * 100 < sr_tolerance_pct:
                results['value_area']['support_hits'] += 1
                min_idx = future_lows.index(min_future_low)
                if min_idx < len(future_closes) - 1:
                    bounce = (max(future_closes[min_idx:]) - min_future_low) / min_future_low * 100
                    if bounce > bounce_threshold_pct:
                        results['value_area']['support_bounces'] += 1

            # VA High 作为阻力测试
            if abs(max_future_high - va_high) / va_high * 100 < sr_tolerance_pct:
                results['value_area']['resistance_hits'] += 1
                max_idx = future_highs.index(max_future_high)
                if max_idx < len(future_closes) - 1:
                    rejection = (max_future_high - min(future_closes[max_idx:])) / max_future_high * 100
                    if rejection > bounce_threshold_pct:
                        results['value_area']['resistance_bounces'] += 1

            # ========== 方法 3: HVN 检测 ==========
            # 找局部极大值
            score = volume_sum / volume_sum.max() if volume_sum.max() > 0 else volume_sum
            hvn_supports = []
            hvn_resistances = []

            for j in range(1, len(score) - 1):
                if score[j] > score[j-1] and score[j] > score[j+1] and score[j] > 0.3:
                    hvn_price = bin_centers[j]
                    if hvn_price < current_price:
                        hvn_supports.append(hvn_price)
                    else:
                        hvn_resistances.append(hvn_price)

            results['hvn']['tests'] += 1

            # HVN 支撑测试
            for hvn_sup in hvn_supports[:2]:  # 最近 2 个
                if abs(min_future_low - hvn_sup) / hvn_sup * 100 < sr_tolerance_pct:
                    results['hvn']['support_hits'] += 1
                    min_idx = future_lows.index(min_future_low)
                    if min_idx < len(future_closes) - 1:
                        bounce = (max(future_closes[min_idx:]) - min_future_low) / min_future_low * 100
                        if bounce > bounce_threshold_pct:
                            results['hvn']['support_bounces'] += 1
                    break

            # HVN 阻力测试
            for hvn_res in hvn_resistances[:2]:
                if abs(max_future_high - hvn_res) / hvn_res * 100 < sr_tolerance_pct:
                    results['hvn']['resistance_hits'] += 1
                    max_idx = future_highs.index(max_future_high)
                    if max_idx < len(future_closes) - 1:
                        rejection = (max_future_high - min(future_closes[max_idx:])) / max_future_high * 100
                        if rejection > bounce_threshold_pct:
                            results['hvn']['resistance_bounces'] += 1
                    break

        # 计算统计
        stats = {}
        for method, r in results.items():
            if r['tests'] > 0:
                support_hit_rate = r['support_hits'] / r['tests'] * 100
                resistance_hit_rate = r['resistance_hits'] / r['tests'] * 100
                support_bounce_rate = r['support_bounces'] / r['support_hits'] * 100 if r['support_hits'] > 0 else 0
                resistance_bounce_rate = r['resistance_bounces'] / r['resistance_hits'] * 100 if r['resistance_hits'] > 0 else 0

                stats[method] = {
                    'tests': r['tests'],
                    'support_hit_rate': round(support_hit_rate, 1),
                    'resistance_hit_rate': round(resistance_hit_rate, 1),
                    'support_bounce_rate': round(support_bounce_rate, 1),
                    'resistance_bounce_rate': round(resistance_bounce_rate, 1),
                    'overall_effectiveness': round((support_bounce_rate + resistance_bounce_rate) / 2, 1),
                }

        return {
            'success': True,
            'days': days,
            'total_bars': len(data),
            'results': results,
            'stats': stats,
        }

    except Exception as e:
        import traceback
        return {
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc(),
        }


def calculate_sr_zones_without_orderwall(current_price: float) -> Dict[str, Any]:
    """使用 S/R Zone Calculator (不含 Order Wall) 计算"""
    try:
        from utils.sr_zone_calculator import SRZoneCalculator
        import requests

        # 获取技术数据 (简化版)
        resp = requests.get(
            "https://fapi.binance.com/fapi/v1/klines",
            params={"symbol": "BTCUSDT", "interval": "15m", "limit": 100},
            timeout=10
        )
        klines = resp.json()

        # 计算 BB 和 SMA (简化)
        closes = [float(k[4]) for k in klines]
        sma_20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else 0
        sma_50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else 0

        # BB 计算
        import statistics
        if len(closes) >= 20:
            std = statistics.stdev(closes[-20:])
            bb_upper = sma_20 + 2 * std
            bb_lower = sma_20 - 2 * std
        else:
            bb_upper = bb_lower = 0

        # 计算 S/R Zones (无 Order Wall)
        sr_calc = SRZoneCalculator()
        bb_data = {'upper': bb_upper, 'lower': bb_lower, 'middle': sma_20}
        sma_data = {'sma_50': sma_50, 'sma_200': 0}  # 简化，不计算 SMA_200

        result = sr_calc.calculate_with_detailed_report(
            current_price=current_price,
            bb_data=bb_data,
            sma_data=sma_data,
            orderbook_anomalies=None,  # 不传入 Order Wall
        )

        return {
            'success': True,
            'result': result,
        }

    except Exception as e:
        import traceback
        return {
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc(),
        }


def check_service_logs() -> Dict[str, Any]:
    """检查服务日志中的支撑阻力相关信息"""
    result = {
        'sr_zone_logs': [],
        'technical_logs': [],
        'heartbeat_logs': [],
        'errors': [],
    }

    try:
        # 获取最近的日志
        cmd = "journalctl -u nautilus-trader --no-pager -n 200 --output=cat 2>/dev/null | grep -i 'support\\|resistance\\|S/R\\|sr_zone' | tail -20"
        output = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if output.stdout:
            result['sr_zone_logs'] = output.stdout.strip().split('\n')

        # 获取 heartbeat 日志
        cmd = "journalctl -u nautilus-trader --no-pager -n 200 --output=cat 2>/dev/null | grep -i 'heartbeat' | tail -10"
        output = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if output.stdout:
            result['heartbeat_logs'] = output.stdout.strip().split('\n')

        # 获取错误日志
        cmd = "journalctl -u nautilus-trader --no-pager -n 100 --output=cat 2>/dev/null | grep -i 'error\\|warning' | grep -i 'sr\\|support\\|resistance' | tail -10"
        output = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if output.stdout:
            result['errors'] = output.stdout.strip().split('\n')

    except Exception as e:
        result['check_error'] = str(e)

    return result


def check_config() -> Dict[str, Any]:
    """检查配置"""
    result = {}

    try:
        from utils.config_manager import ConfigManager
        config = ConfigManager(env='production')
        config.load()

        result['order_book_enabled'] = config.get('order_book', 'enabled', default=False)
        result['sr_hard_control_enabled'] = config.get('risk', 'sr_hard_control_enabled', default=True)
        result['sr_hard_control_threshold'] = config.get('risk', 'sr_hard_control_threshold_pct', default=1.0)

    except Exception as e:
        result['error'] = str(e)

    return result


def analyze_telegram_data_source():
    """分析 Telegram 消息使用的数据源"""
    print_section("Telegram 数据源分析")

    print("  📝 Heartbeat 消息数据流:")
    print()
    print("     on_timer() 开始")
    print("         │")
    print("         ├─→ _send_heartbeat_notification()  ← 使用 self.latest_sr_zones_data")
    print("         │       (这是上一次分析的缓存数据!)")
    print("         │")
    print("         │   ... AI 分析过程 ...")
    print("         │")
    print("         └─→ multi_agent.analyze()")
    print("                 └─→ _calculate_sr_zones(orderbook_data)")
    print("                         └─→ 更新 _sr_zones_cache")
    print("                                 └─→ 更新 latest_sr_zones_data")
    print()
    print("  ⚠️ 时序问题: Heartbeat 在分析之前发送，使用的是 15 分钟前的数据!")
    print()

    print("  📝 数据来源对比:")
    print()
    print("     ┌─────────────────────┬─────────────────────────────────────┐")
    print("     │ 场景                │ 数据来源                            │")
    print("     ├─────────────────────┼─────────────────────────────────────┤")
    print("     │ Telegram Heartbeat  │ latest_sr_zones_data (15分钟前缓存) │")
    print("     │ 诊断脚本 [11]       │ SRZoneCalculator (实时, 含Order Wall)│")
    print("     │ 诊断脚本 [9.5.5]    │ SRZoneCalculator (实时, 无Order Wall)│")
    print("     │ SL/TP 计算          │ latest_sr_zones_data 或回退到简单高低│")
    print("     └─────────────────────┴─────────────────────────────────────┘")
    print()


def run_full_diagnosis():
    """运行完整诊断"""
    print_header("支撑阻力位全面诊断 v1.0")
    print(f"  时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

    # 1. 获取当前价格
    print_section("1. 当前市场数据")
    current_price = get_current_price()
    print_result("当前价格", f"${current_price:,.2f}", "info")

    # 2. 检查配置
    print_section("2. 配置检查")
    config = check_config()
    if 'error' not in config:
        print_result("Order Book 启用", config.get('order_book_enabled', False),
                    "ok" if config.get('order_book_enabled') else "warn")
        print_result("S/R 硬风控启用", config.get('sr_hard_control_enabled', True),
                    "ok" if config.get('sr_hard_control_enabled') else "warn")
        print_result("硬风控阈值", f"{config.get('sr_hard_control_threshold', 1.0)}%", "info")
    else:
        print_result("配置错误", config['error'], "error")

    # 3. 计算简单高低点
    print_section("3. 方法一: 简单高低点 (TechnicalIndicatorManager)")
    support_simple, resistance_simple = calculate_simple_high_low(20)
    print_result("支撑位", f"${support_simple:,.2f}", "info")
    print_result("阻力位", f"${resistance_simple:,.2f}", "info")
    if current_price > 0 and support_simple > 0:
        dist_sup = ((current_price - support_simple) / current_price) * 100
        dist_res = ((resistance_simple - current_price) / current_price) * 100
        print_result("距离支撑", f"{dist_sup:.2f}%", "ok" if dist_sup > 1 else "warn")
        print_result("距离阻力", f"{dist_res:.2f}%", "ok" if dist_res > 1 else "warn")

    print()
    print("  📝 计算方法: min(20根K线Low) / max(20根K线High)")
    print("  📝 来源: indicators/technical_manager.py:_calculate_support_resistance()")

    # 4. 计算 S/R Zone (无 Order Wall)
    print_section("4. 方法二: S/R Zone Calculator (无 Order Wall)")
    sr_no_wall = calculate_sr_zones_without_orderwall(current_price)
    if sr_no_wall['success']:
        result = sr_no_wall['result']
        sup_zones = result.get('support_zones', [])
        res_zones = result.get('resistance_zones', [])

        print_result("支撑区数量", len(sup_zones), "info")
        for i, zone in enumerate(sup_zones[:2]):
            print(f"      {i+1}. ${zone.price_center:,.0f} ({zone.distance_pct:.1f}% away) [{zone.strength}]")

        print_result("阻力区数量", len(res_zones), "info")
        for i, zone in enumerate(res_zones[:2]):
            print(f"      {i+1}. ${zone.price_center:,.0f} ({zone.distance_pct:.1f}% away) [{zone.strength}]")

        hard_control = result.get('hard_control', {})
        print_result("Block LONG", hard_control.get('block_long', False),
                    "warn" if hard_control.get('block_long') else "ok")
        print_result("Block SHORT", hard_control.get('block_short', False),
                    "warn" if hard_control.get('block_short') else "ok")
    else:
        print_result("计算失败", sr_no_wall.get('error', 'Unknown'), "error")

    print()
    print("  📝 计算方法: BB + SMA_50 聚合 (无订单簿数据)")
    print("  📝 来源: utils/sr_zone_calculator.py (orderbook_anomalies=None)")

    # 5. 计算 S/R Zone (含 Order Wall)
    print_section("5. 方法三: S/R Zone Calculator (含 Order Wall)")
    sr_with_wall = calculate_sr_zones_with_orderwall(current_price)
    if sr_with_wall['success']:
        result = sr_with_wall['result']
        sup_zones = result.get('support_zones', [])
        res_zones = result.get('resistance_zones', [])

        print_result("支撑区数量", len(sup_zones), "info")
        for i, zone in enumerate(sup_zones[:3]):
            wall_info = f" [Order Wall: {zone.wall_size_btc:.1f} BTC]" if zone.has_order_wall else ""
            src = ", ".join(zone.sources[:2]) if zone.sources else zone.source_type
            print(f"      {i+1}. ${zone.price_center:,.0f} ({zone.distance_pct:.1f}%) [{zone.strength}]{wall_info}")
            print(f"         来源: {src}")

        print_result("阻力区数量", len(res_zones), "info")
        for i, zone in enumerate(res_zones[:3]):
            wall_info = f" [Order Wall: {zone.wall_size_btc:.1f} BTC]" if zone.has_order_wall else ""
            src = ", ".join(zone.sources[:2]) if zone.sources else zone.source_type
            print(f"      {i+1}. ${zone.price_center:,.0f} ({zone.distance_pct:.1f}%) [{zone.strength}]{wall_info}")
            print(f"         来源: {src}")

        hard_control = result.get('hard_control', {})
        print_result("Block LONG", hard_control.get('block_long', False),
                    "warn" if hard_control.get('block_long') else "ok")
        print_result("Block SHORT", hard_control.get('block_short', False),
                    "warn" if hard_control.get('block_short') else "ok")
        if hard_control.get('reason'):
            print_result("阻止原因", hard_control.get('reason'), "warn")

        # Order Wall 详情
        anomalies = sr_with_wall.get('orderbook_anomalies', {})
        if anomalies:
            bid_anomalies = anomalies.get('bid_anomalies', [])
            ask_anomalies = anomalies.get('ask_anomalies', [])
            print()
            print(f"  📊 订单簿大单 (Order Walls):")
            print(f"      Bid 大单: {len(bid_anomalies)} 个")
            for a in bid_anomalies[:3]:
                print(f"         ${a.get('price', 0):,.0f}: {a.get('size', 0):.2f} BTC ({a.get('z_score', 0):.1f}σ)")
            print(f"      Ask 大单: {len(ask_anomalies)} 个")
            for a in ask_anomalies[:3]:
                print(f"         ${a.get('price', 0):,.0f}: {a.get('size', 0):.2f} BTC ({a.get('z_score', 0):.1f}σ)")
    else:
        print_result("计算失败", sr_with_wall.get('error', 'Unknown'), "error")
        if sr_with_wall.get('traceback'):
            print(f"  Traceback: {sr_with_wall['traceback'][:200]}...")

    print()
    print("  📝 计算方法: BB + SMA_50 + Order Wall 聚合")
    print("  📝 来源: utils/sr_zone_calculator.py + utils/orderbook_processor.py")

    # 6. 价格分布极值检测 (新方法 v2.0)
    print_section("6. 方法四: Volume Profile 风格分析 (CME 标准)")
    dist_result = calculate_price_distribution_sr(
        price_min=55000,
        price_max=70000,
        interval=1000,
        bars=500,
        current_price=current_price,
        min_distance_pct=1.0,  # 排除当前价格 ±1% 内的峰值
    )

    if dist_result['success']:
        print(f"  📊 分析范围: {dist_result['price_range']}")
        print(f"  📊 区间宽度: ${dist_result['interval']:,}")
        print(f"  📊 分析K线数: {dist_result['bars_analyzed']}")
        print()

        # POC 和 Value Area (CME 标准)
        poc = dist_result['poc']
        va = dist_result['value_area']
        print(f"  🎯 POC (Point of Control): ${poc['price']:,.0f}")
        print(f"     └─ 成交量最密集的价格，市场公认的\"公平价格\"")
        print()
        print(f"  📦 Value Area ({va['pct']:.0f}% 成交覆盖): ${va['low']:,.0f} - ${va['high']:,.0f}")
        print(f"     └─ 70% 交易活动发生的区域，VA边界是重要 S/R")
        print()

        # 显示分布直方图 (ASCII 风格)
        print("  📈 价格分布直方图:")
        print()
        distribution = dist_result['distribution']
        max_score = max(d['score'] for d in distribution)

        for d in distribution:
            bar_len = int(d['score'] / max_score * 30) if max_score > 0 else 0
            bar = "█" * bar_len
            # 标记当前价格所在区间
            is_current = d['center'] - 500 <= current_price <= d['center'] + 500
            marker = " ◀ 当前" if is_current else ""
            # 标记 POC
            poc_marker = " [POC]" if d.get('is_poc') else ""
            # 标记 Value Area
            va_marker = " VA" if d.get('in_va') else ""
            # 标记 HVN 峰值
            is_peak = any(p['price'] == d['center'] for p in dist_result['peaks'])
            peak_marker = " ⭐HVN" if is_peak else ""
            print(f"      {d['range']:>18} │{bar:<30} {d['score']:.2f}{poc_marker}{va_marker}{peak_marker}{marker}")

        print()
        print("  ⭐ HVN (High Volume Nodes) - 强 S/R 区域:")
        peaks = dist_result['peaks']
        if peaks:
            for i, peak in enumerate(peaks[:5], 1):
                sr_type = "支撑" if peak['price'] < current_price else "阻力"
                distance_pct = abs(peak['price'] - current_price) / current_price * 100
                va_tag = " [在VA内]" if peak.get('in_value_area') else ""
                print(f"      {i}. ${peak['price']:,.0f} [{sr_type}] (得分: {peak['score']:.3f}, "
                      f"触及: {peak['touch_count']}次, 距离: {distance_pct:.1f}%){va_tag}")
        else:
            print("      未检测到 ±1% 外的明显 HVN")

        # LVN (Low Volume Nodes)
        lvn = dist_result.get('lvn', [])
        if lvn:
            print()
            print("  ⚡ LVN (Low Volume Nodes) - 价格快速穿越区域:")
            for node in lvn[:3]:
                print(f"      ${node['price']:,.0f} (得分: {node['score']:.3f})")

        print()
        print("  📝 理论依据: CME Market Profile / Volume Profile")
        print("  📝 参考: POC 是价格吸引点, VA 边界是重要 S/R, HVN 是强支撑阻力")
    else:
        print_result("计算失败", dist_result.get('error', 'Unknown'), "error")

    # 7. S/R 检测回测验证
    print_section("7. S/R 检测回测验证 (过去 3 天)")
    print("  ⏳ 正在进行回测分析，请稍候...")
    print()

    backtest_result = backtest_sr_detection(days=3, interval="15m")

    if backtest_result['success']:
        stats = backtest_result['stats']
        print(f"  📊 回测数据: {backtest_result['total_bars']} 根 K 线 ({backtest_result['days']} 天)")
        print()

        print("  ┌─────────────────────┬──────────┬──────────┬──────────┬──────────┬──────────┐")
        print("  │ 检测方法            │ 测试次数 │ 支撑命中 │ 阻力命中 │ 支撑反弹 │ 阻力反弹 │")
        print("  ├─────────────────────┼──────────┼──────────┼──────────┼──────────┼──────────┤")

        for method, s in stats.items():
            method_name = {
                'simple_high_low': '简单高低点',
                'value_area': 'Value Area',
                'hvn': 'HVN 极值检测',
            }.get(method, method)
            print(f"  │ {method_name:<17} │ {s['tests']:>8} │ {s['support_hit_rate']:>7.1f}% │ "
                  f"{s['resistance_hit_rate']:>7.1f}% │ {s['support_bounce_rate']:>7.1f}% │ {s['resistance_bounce_rate']:>7.1f}% │")

        print("  └─────────────────────┴──────────┴──────────┴──────────┴──────────┴──────────┘")
        print()

        # 评估哪个方法最好
        best_method = max(stats.items(), key=lambda x: x[1]['overall_effectiveness'])
        print(f"  🏆 最有效方法: {best_method[0]} (综合有效率: {best_method[1]['overall_effectiveness']:.1f}%)")
        print()

        # 解释指标
        print("  📝 指标说明:")
        print("     • 支撑/阻力命中: 价格在 ±0.5% 范围内触及 S/R")
        print("     • 支撑/阻力反弹: 触及后在 4 小时内反弹 ≥0.3%")
        print("     • 综合有效率: (支撑反弹率 + 阻力反弹率) / 2")
        print()

        # 给出建议
        if best_method[1]['overall_effectiveness'] > 50:
            print(f"  ✅ {best_method[0]} 方法可靠性较高，建议作为主要 S/R 来源")
        elif best_method[1]['overall_effectiveness'] > 30:
            print(f"  ⚠️ {best_method[0]} 方法效果一般，建议结合多种方法使用")
        else:
            print("  ❌ 当前市场可能处于趋势行情，S/R 效果不明显")
    else:
        print_result("回测失败", backtest_result.get('error', 'Unknown'), "error")

    # 8. Telegram 数据源分析
    analyze_telegram_data_source()

    # 9. 服务日志检查
    print_section("9. 服务日志检查")
    logs = check_service_logs()
    if logs.get('sr_zone_logs'):
        print("  📋 最近的 S/R 相关日志:")
        for log in logs['sr_zone_logs'][-5:]:
            print(f"      {log[:100]}...")
    else:
        print("  ℹ️ 未找到 S/R 相关日志")

    if logs.get('errors'):
        print()
        print("  ⚠️ S/R 相关错误:")
        for err in logs['errors'][-3:]:
            print(f"      {err[:100]}...")

    # 10. 问题诊断
    print_section("10. 问题诊断")

    problems = []
    suggestions = []

    # 检查 Order Wall 问题
    if sr_with_wall['success']:
        result = sr_with_wall['result']
        nearest_sup = result.get('nearest_support')
        nearest_res = result.get('nearest_resistance')

        if nearest_sup and nearest_sup.distance_pct < 0.5:
            problems.append(f"支撑位距离太近 ({nearest_sup.distance_pct:.1f}%)")
            if nearest_sup.has_order_wall:
                problems.append("支撑位来自 Order Wall (可能是临时大单)")

        if nearest_res and nearest_res.distance_pct < 0.5:
            problems.append(f"阻力位距离太近 ({nearest_res.distance_pct:.1f}%)")
            if nearest_res.has_order_wall:
                problems.append("阻力位来自 Order Wall (可能是临时大单)")

        hard_control = result.get('hard_control', {})
        if hard_control.get('block_long') and hard_control.get('block_short'):
            problems.append("同时阻止 LONG 和 SHORT (无法交易)")

    # 对比简单高低点和 Order Wall
    if sr_with_wall['success'] and support_simple > 0:
        result = sr_with_wall['result']
        nearest_sup = result.get('nearest_support')
        if nearest_sup:
            diff = abs(nearest_sup.price_center - support_simple)
            diff_pct = (diff / support_simple) * 100
            if diff_pct > 5:
                problems.append(f"Order Wall 支撑和简单高低点差距大 ({diff_pct:.1f}%)")
                suggestions.append("考虑降低 Order Wall 权重或优先使用简单高低点")

    if problems:
        print("  ❌ 发现的问题:")
        for p in problems:
            print(f"      • {p}")
    else:
        print("  ✅ 未发现明显问题")

    # 11. 修复建议
    print_section("11. 修复建议")

    suggestions.extend([
        "将 Heartbeat 发送移到分析之后，使用最新数据",
        "降低 Order Wall 权重 (当前 2.0，建议 0.5-1.0)",
        "添加 Order Wall 最小 BTC 阈值 (如 > 10 BTC 才算大单)",
        "考虑使用简单高低点作为主要支撑阻力来源",
        "实现 Swing Point Detection (全球标准方法)",
    ])

    for i, s in enumerate(suggestions, 1):
        print(f"  {i}. {s}")

    # 12. 总结
    print_section("12. 总结对比表")

    print("  ┌─────────────────────────┬───────────────────┬───────────────────┐")
    print("  │ 计算方法                │ 支撑位            │ 阻力位            │")
    print("  ├─────────────────────────┼───────────────────┼───────────────────┤")
    print(f"  │ 简单高低点              │ ${support_simple:>14,.0f} │ ${resistance_simple:>14,.0f} │")

    if sr_no_wall['success']:
        result = sr_no_wall['result']
        sup = result.get('nearest_support')
        res = result.get('nearest_resistance')
        sup_price = f"${sup.price_center:,.0f}" if sup else "N/A"
        res_price = f"${res.price_center:,.0f}" if res else "N/A"
        print(f"  │ S/R Zone (无 Order Wall)│ {sup_price:>17} │ {res_price:>17} │")

    if sr_with_wall['success']:
        result = sr_with_wall['result']
        sup = result.get('nearest_support')
        res = result.get('nearest_resistance')
        sup_price = f"${sup.price_center:,.0f}" if sup else "N/A"
        res_price = f"${res.price_center:,.0f}" if res else "N/A"
        print(f"  │ S/R Zone (含 Order Wall)│ {sup_price:>17} │ {res_price:>17} │")

    # 添加价格分布检测结果
    if dist_result['success']:
        # Value Area 边界作为 S/R
        va = dist_result['value_area']
        print(f"  │ Value Area 边界        │ ${va['low']:>14,.0f} │ ${va['high']:>14,.0f} │")

        # HVN (排除当前价格附近)
        peaks = dist_result.get('peaks', [])
        supports = [p for p in peaks if p['price'] < current_price]
        resistances = [p for p in peaks if p['price'] > current_price]
        sup_price = f"${supports[0]['price']:,.0f}" if supports else "N/A"
        res_price = f"${resistances[0]['price']:,.0f}" if resistances else "N/A"
        print(f"  │ HVN 极值 (>1%距离)     │ {sup_price:>17} │ {res_price:>17} │")

    print("  └─────────────────────────┴───────────────────┴───────────────────┘")

    # 方法评估 (基于全球标准)
    print()
    print("  📊 方法评估 (基于 CME/IEEE 标准):")
    print()
    print("     ┌─────────────────────────┬──────────┬──────────┬──────────┬──────────┐")
    print("     │ 方法                    │ 稳定性   │ 实时性   │ 可靠性   │ 专业度   │")
    print("     ├─────────────────────────┼──────────┼──────────┼──────────┼──────────┤")
    print("     │ 简单高低点              │ ★★★★★    │ ★★★      │ ★★★      │ ★★       │")
    print("     │ S/R Zone (BB+SMA)       │ ★★★★     │ ★★★      │ ★★★★     │ ★★★      │")
    print("     │ Order Wall              │ ★★       │ ★★★★★    │ ★★       │ ★★★      │")
    print("     │ Value Area (CME)        │ ★★★★★    │ ★★       │ ★★★★★    │ ★★★★★    │")
    print("     │ HVN/LVN (Volume Profile)│ ★★★★★    │ ★★       │ ★★★★★    │ ★★★★★    │")
    print("     └─────────────────────────┴──────────┴──────────┴──────────┴──────────┘")
    print()
    print("  💡 全球标准做法:")
    print("     1. Value Area 边界 = 主要 S/R (CME Market Profile)")
    print("     2. HVN = 强支撑阻力 (价格在此停留时间长)")
    print("     3. LVN = 快速穿越区 (不适合作为 S/R)")
    print("     4. POC = 公平价格 (价格吸引点)")
    print()
    print("  📚 参考文献:")
    print("     - CME Group Market Profile User Guide")
    print("     - IEEE: Evolutionary Optimized Stock Support-Resistance")
    print("     - MDPI: Support Resistance Levels in Algorithmic Trading")

    print()
    print(f"  诊断完成: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="支撑阻力位全面诊断")
    parser.add_argument("--export", action="store_true", help="导出到文件")
    args = parser.parse_args()

    if args.export:
        # 重定向输出到文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = project_root / "logs" / f"sr_diagnosis_{timestamp}.txt"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        import io
        from contextlib import redirect_stdout

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            run_full_diagnosis()

        output = buffer.getvalue()
        print(output)  # 也打印到终端

        with open(output_file, 'w') as f:
            f.write(output)

        print(f"\n📁 诊断报告已保存到: {output_file}")
    else:
        run_full_diagnosis()


if __name__ == "__main__":
    main()
