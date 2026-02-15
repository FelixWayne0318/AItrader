#!/usr/bin/env python3
"""
支撑阻力位全面诊断脚本 v3.1

功能:
1. 检查所有支撑阻力数据来源
2. 对比不同计算方式的结果
3. 检查实盘服务的日志和缓存
4. 分析 Telegram Heartbeat 使用的数据
5. 给出诊断报告和修复建议
6. v1.1: 价格分布极值检测 (类似 Volume Profile)
7. v1.2: S/R 检测回测验证 (验证检测准确率)
8. v2.0: 完整交易模拟回测 (模拟 AI R/R 决策 + SL/TP 盈亏统计)
9. v3.0: Swing Point 检测 + ATR 自适应聚类 + Touch Count 评分
10. v3.1: 完整 S/R + SL/TP 详情, 14天默认回测, 质量分析

使用方法:
    python3 scripts/diagnose_sr_zones.py                      # 完整诊断
    python3 scripts/diagnose_sr_zones.py --export             # 导出到文件
    python3 scripts/diagnose_sr_zones.py --backtest           # 仅运行回测 (14天)
    python3 scripts/diagnose_sr_zones.py --backtest --days 30 # 回测30天
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

        # 构建 bars_data (v3.0: Swing Point / ATR / Touch Count)
        bars_data = []
        for k in klines:
            bars_data.append({
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
            })

        # 加载 sr_zones 配置
        sr_cfg = {}
        try:
            from utils.config_manager import ConfigManager
            cm = ConfigManager(env='production')
            cm.load()
            sr_cfg = cm.get('sr_zones', default={})
        except Exception:
            pass

        swing_cfg = sr_cfg.get('swing_detection', {})
        cluster_cfg = sr_cfg.get('clustering', {})
        scoring_cfg = sr_cfg.get('scoring', {})

        # 计算 S/R Zones (v3.0 with Swing Point + ATR + Touch Count)
        sr_calc = SRZoneCalculator(
            swing_detection_enabled=swing_cfg.get('enabled', True),
            swing_left_bars=swing_cfg.get('left_bars', 5),
            swing_right_bars=swing_cfg.get('right_bars', 5),
            swing_weight=swing_cfg.get('weight', 1.2),
            swing_max_age=swing_cfg.get('max_swing_age', 100),
            use_atr_adaptive=cluster_cfg.get('use_atr_adaptive', True),
            atr_cluster_multiplier=cluster_cfg.get('atr_cluster_multiplier', 0.5),
            touch_count_enabled=scoring_cfg.get('touch_count_enabled', True),
            touch_threshold_atr=scoring_cfg.get('touch_threshold_atr', 0.3),
            optimal_touches=scoring_cfg.get('optimal_touches', [2, 3]),
            decay_after_touches=scoring_cfg.get('decay_after_touches', 4),
        )
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
            bars_data=bars_data,
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


def generate_mock_klines(days: int = 7, interval: str = "15m") -> list:
    """
    生成模拟 K 线数据用于本地测试 (无网络环境)

    模拟一个典型的 BTC 价格走势:
    - 基础价格: ~$95,000
    - 日波动率: ~2-3%
    - 包含趋势和震荡
    """
    import random
    from datetime import datetime, timedelta

    intervals_per_day = {"15m": 96, "1h": 24, "4h": 6}
    bars_per_day = intervals_per_day.get(interval, 96)
    total_bars = days * bars_per_day + 200

    # 初始价格
    price = 95000.0
    klines = []

    # 15分钟间隔 (毫秒)
    interval_ms = {"15m": 15 * 60 * 1000, "1h": 60 * 60 * 1000, "4h": 4 * 60 * 60 * 1000}
    delta_ms = interval_ms.get(interval, 15 * 60 * 1000)

    start_time = int((datetime.now() - timedelta(days=days + 3)).timestamp() * 1000)

    # 模拟市场周期: 上涨 -> 震荡 -> 下跌 -> 反弹
    trend_phases = [
        (0.0003, 0.3),   # 上涨阶段
        (0.0, 0.4),      # 震荡阶段
        (-0.0002, 0.35), # 下跌阶段
        (0.0002, 0.3),   # 反弹阶段
    ]

    for i in range(total_bars):
        # 确定当前趋势阶段
        phase_idx = (i // (total_bars // 4)) % 4
        drift, volatility = trend_phases[phase_idx]

        # 随机波动
        change_pct = random.gauss(drift, volatility / 100)

        # 生成 OHLCV
        open_price = price
        high_price = price * (1 + abs(random.gauss(0, 0.3)) / 100)
        low_price = price * (1 - abs(random.gauss(0, 0.3)) / 100)
        close_price = price * (1 + change_pct)
        volume = random.uniform(500, 2000)  # BTC

        # 确保 high >= open/close, low <= open/close
        high_price = max(high_price, open_price, close_price)
        low_price = min(low_price, open_price, close_price)

        kline = [
            start_time + i * delta_ms,  # Open time
            str(open_price),
            str(high_price),
            str(low_price),
            str(close_price),
            str(volume),
            start_time + (i + 1) * delta_ms - 1,  # Close time
            str(volume * price),  # Quote volume
            random.randint(1000, 5000),  # Trades
            str(volume * 0.45),  # Taker buy volume
            str(volume * price * 0.45),  # Taker buy quote volume
            "0"
        ]
        klines.append(kline)

        price = close_price

    return klines


def backtest_sr_trading_simulation(
    days: int = 7,
    interval: str = "15m",
    min_rr_ratio: float = 1.5,
    sl_buffer_pct: float = 0.5,
    position_usdt: float = 1000,
    leverage: int = 10,
    use_mock: bool = False,
) -> Dict[str, Any]:
    """
    完整的 S/R 交易模拟回测 (v2.0)

    模拟 v3.17 R/R 驱动的 AI 决策:
    1. 每隔一段时间计算 S/R zones
    2. 基于 R/R >= 1.5:1 决定是否入场
    3. 使用 S/R 计算 SL/TP
    4. 跟踪后续价格，判断触及 SL 还是 TP
    5. 统计胜率、盈亏比、预期收益

    参数:
    - days: 回测天数
    - interval: K 线周期
    - min_rr_ratio: 最小 R/R 比率 (v3.17 默认 1.5)
    - sl_buffer_pct: SL 缓冲百分比
    - position_usdt: 每笔仓位 USDT
    - leverage: 杠杆倍数
    - use_mock: 使用模拟数据 (无网络环境)

    返回:
    - 完整的交易统计和分析
    """
    try:
        from datetime import datetime, timedelta

        # 计算需要多少根 K 线
        intervals_per_day = {
            "15m": 96,   # 24 * 4
            "1h": 24,
            "4h": 6,
        }
        bars_per_day = intervals_per_day.get(interval, 96)
        bars_needed = days * bars_per_day + 200  # 额外用于计算

        if use_mock:
            # 使用模拟数据
            print("  📊 使用模拟数据 (--mock 模式)")
            all_klines = generate_mock_klines(days, interval)
        else:
            # 从 Binance API 获取真实数据
            import requests

            # Binance API 限制每次 1500 根，需要分批获取
            all_klines = []
            end_time = None

            while len(all_klines) < bars_needed:
                params = {
                    "symbol": "BTCUSDT",
                    "interval": interval,
                    "limit": min(1500, bars_needed - len(all_klines) + 100),
                }
                if end_time:
                    params["endTime"] = end_time

                resp = requests.get(
                    "https://fapi.binance.com/fapi/v1/klines",
                    params=params,
                    timeout=30
                )
                klines = resp.json()

                if not klines:
                    break

                # 插入到开头 (旧数据在前)
                all_klines = klines + all_klines
                end_time = klines[0][0] - 1  # 下一批的结束时间

                if len(klines) < 100:  # 没有更多数据了
                    break

        if len(all_klines) < 300:
            return {'success': False, 'error': f'数据不足: {len(all_klines)} bars'}

        # 准备数据
        data = []
        for k in all_klines:
            data.append({
                'time': datetime.fromtimestamp(k[0] / 1000),
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5]),
            })

        # 只保留最近 days 天的数据用于回测
        test_start_idx = len(data) - (days * bars_per_day)
        if test_start_idx < 100:
            test_start_idx = 100

        # 交易记录
        trades = []
        trade_id = 0

        # 每 4 根 K 线 (1 小时) 做一次检测
        step = 4
        lookback = 100  # 用于计算 S/R 的历史数据量
        max_hold_bars = 48  # 最长持仓时间 (12 小时)

        for i in range(test_start_idx, len(data) - max_hold_bars, step):
            current_bar = data[i]
            current_price = current_bar['close']
            current_time = current_bar['time']
            history = data[i-lookback:i]

            # ========== 计算 S/R Zones (简化版 Volume Profile) ==========
            price_min = min(d['low'] for d in history)
            price_max = max(d['high'] for d in history)
            bin_size = 500  # $500 区间

            # 使用列表代替 numpy
            bins = []
            p = price_min - bin_size
            while p <= price_max + bin_size * 2:
                bins.append(p)
                p += bin_size

            if len(bins) < 5:
                continue

            bin_centers = [(bins[i] + bins[i+1]) / 2 for i in range(len(bins) - 1)]
            volume_sum = [0.0] * len(bin_centers)

            for d in history:
                for j, (bl, bh) in enumerate(zip(bins[:-1], bins[1:])):
                    if d['low'] <= bh and d['high'] >= bl:
                        if d['high'] > d['low']:
                            overlap = (min(d['high'], bh) - max(d['low'], bl)) / (d['high'] - d['low'])
                        else:
                            overlap = 1.0
                        volume_sum[j] += d['volume'] * overlap

            if sum(volume_sum) == 0:
                continue

            # 找到当前价格所在的 bin
            current_bin_idx = 0
            for idx, b in enumerate(bins):
                if b > current_price:
                    current_bin_idx = max(0, idx - 1)
                    break
            current_bin_idx = max(0, min(current_bin_idx, len(bin_centers) - 1))

            # ========== 找支撑位 (当前价格下方的 HVN) ==========
            support = None
            support_score = 0
            max_vol = max(volume_sum) if volume_sum else 1
            score = [v / max_vol if max_vol > 0 else 0 for v in volume_sum]

            for j in range(current_bin_idx - 1, 0, -1):
                if score[j] > score[j-1] and score[j] > score[j+1] and score[j] > 0.3:
                    support = bin_centers[j]
                    support_score = score[j]
                    break

            # 回退: 使用最近 20 根 K 线最低点
            if support is None:
                support = min(d['low'] for d in history[-20:])
                support_score = 0.2

            # ========== 找阻力位 (当前价格上方的 HVN) ==========
            resistance = None
            resistance_score = 0

            for j in range(current_bin_idx + 1, len(score) - 1):
                if score[j] > score[j-1] and score[j] > score[j+1] and score[j] > 0.3:
                    resistance = bin_centers[j]
                    resistance_score = score[j]
                    break

            # 回退: 使用最近 20 根 K 线最高点
            if resistance is None:
                resistance = max(d['high'] for d in history[-20:])
                resistance_score = 0.2

            # ========== 计算 R/R 并决定是否入场 ==========
            # LONG: SL 在支撑下方, TP 在阻力位
            long_sl = support * (1 - sl_buffer_pct / 100)
            long_tp = resistance
            long_risk = current_price - long_sl
            long_reward = long_tp - current_price
            long_rr = long_reward / long_risk if long_risk > 0 else 0

            # SHORT: SL 在阻力上方, TP 在支撑位
            short_sl = resistance * (1 + sl_buffer_pct / 100)
            short_tp = support
            short_risk = short_sl - current_price
            short_reward = current_price - short_tp
            short_rr = short_reward / short_risk if short_risk > 0 else 0

            # v3.17 决策: 只有 R/R >= min_rr_ratio 才入场
            signal = None
            sl_price = 0
            tp_price = 0
            rr_ratio = 0

            if long_rr >= min_rr_ratio and long_rr > short_rr:
                signal = "LONG"
                sl_price = long_sl
                tp_price = long_tp
                rr_ratio = long_rr
            elif short_rr >= min_rr_ratio and short_rr > long_rr:
                signal = "SHORT"
                sl_price = short_sl
                tp_price = short_tp
                rr_ratio = short_rr

            if signal is None:
                continue  # R/R 不达标，跳过

            # ========== 模拟交易执行 ==========
            trade_id += 1
            entry_price = current_price

            # 跟踪后续 K 线，看是否触及 SL 或 TP
            result = "OPEN"
            exit_price = 0
            exit_time = None
            bars_held = 0

            for k in range(i + 1, min(i + max_hold_bars, len(data))):
                future_bar = data[k]
                bars_held += 1

                if signal == "LONG":
                    # 检查是否触及 SL (先检查 SL，再检查 TP)
                    if future_bar['low'] <= sl_price:
                        result = "LOSS"
                        exit_price = sl_price
                        exit_time = future_bar['time']
                        break
                    elif future_bar['high'] >= tp_price:
                        result = "WIN"
                        exit_price = tp_price
                        exit_time = future_bar['time']
                        break
                else:  # SHORT
                    if future_bar['high'] >= sl_price:
                        result = "LOSS"
                        exit_price = sl_price
                        exit_time = future_bar['time']
                        break
                    elif future_bar['low'] <= tp_price:
                        result = "WIN"
                        exit_price = tp_price
                        exit_time = future_bar['time']
                        break

            # 超时平仓
            if result == "OPEN":
                result = "TIMEOUT"
                exit_price = data[min(i + max_hold_bars, len(data) - 1)]['close']
                exit_time = data[min(i + max_hold_bars, len(data) - 1)]['time']

            # 计算盈亏
            if signal == "LONG":
                pnl_pct = (exit_price - entry_price) / entry_price * 100
            else:
                pnl_pct = (entry_price - exit_price) / entry_price * 100

            pnl_usdt = position_usdt * leverage * pnl_pct / 100

            trade = {
                'id': trade_id,
                'time': current_time.strftime('%Y-%m-%d %H:%M'),
                'signal': signal,
                'entry_price': round(entry_price, 2),
                'sl_price': round(sl_price, 2),
                'tp_price': round(tp_price, 2),
                'rr_ratio': round(rr_ratio, 2),
                'support': round(support, 2),
                'resistance': round(resistance, 2),
                'support_score': round(support_score, 3),
                'resistance_score': round(resistance_score, 3),
                'result': result,
                'exit_price': round(exit_price, 2),
                'exit_time': exit_time.strftime('%Y-%m-%d %H:%M') if exit_time else None,
                'bars_held': bars_held,
                'pnl_pct': round(pnl_pct, 2),
                'pnl_usdt': round(pnl_usdt, 2),
            }
            trades.append(trade)

        # ========== 统计分析 ==========
        if not trades:
            return {'success': False, 'error': '没有产生任何交易信号'}

        total_trades = len(trades)
        wins = [t for t in trades if t['result'] == 'WIN']
        losses = [t for t in trades if t['result'] == 'LOSS']
        timeouts = [t for t in trades if t['result'] == 'TIMEOUT']

        win_count = len(wins)
        loss_count = len(losses)
        timeout_count = len(timeouts)

        win_rate = win_count / total_trades * 100 if total_trades > 0 else 0

        total_pnl_usdt = sum(t['pnl_usdt'] for t in trades)
        win_pnls = [t['pnl_usdt'] for t in wins]
        loss_pnls = [t['pnl_usdt'] for t in losses]
        avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0
        avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0

        # 期望收益
        expected_value = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss) if total_trades > 0 else 0

        # 按信号类型分析
        long_trades = [t for t in trades if t['signal'] == 'LONG']
        short_trades = [t for t in trades if t['signal'] == 'SHORT']

        long_wins = len([t for t in long_trades if t['result'] == 'WIN'])
        short_wins = len([t for t in short_trades if t['result'] == 'WIN'])

        long_win_rate = long_wins / len(long_trades) * 100 if long_trades else 0
        short_win_rate = short_wins / len(short_trades) * 100 if short_trades else 0

        # 最大连续亏损
        max_consecutive_losses = 0
        current_losses = 0
        for t in trades:
            if t['result'] == 'LOSS':
                current_losses += 1
                max_consecutive_losses = max(max_consecutive_losses, current_losses)
            else:
                current_losses = 0

        # 最大回撤
        cumulative_pnl = []
        running_pnl = 0
        for t in trades:
            running_pnl += t['pnl_usdt']
            cumulative_pnl.append(running_pnl)

        peak = 0
        max_drawdown = 0
        for pnl in cumulative_pnl:
            if pnl > peak:
                peak = pnl
            drawdown = peak - pnl
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # 平均 R/R (实际)
        actual_rrs = []
        for t in trades:
            if t['result'] == 'WIN':
                actual_rrs.append(t['rr_ratio'])
            elif t['result'] == 'LOSS':
                actual_rrs.append(-1)  # 亏损 = -1R
        avg_actual_rr = sum(actual_rrs) / len(actual_rrs) if actual_rrs else 0

        # 盈利因子
        gross_profit = sum(t['pnl_usdt'] for t in trades if t['pnl_usdt'] > 0)
        gross_loss = abs(sum(t['pnl_usdt'] for t in trades if t['pnl_usdt'] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        return {
            'success': True,
            'config': {
                'days': days,
                'interval': interval,
                'min_rr_ratio': min_rr_ratio,
                'sl_buffer_pct': sl_buffer_pct,
                'position_usdt': position_usdt,
                'leverage': leverage,
            },
            'data': {
                'total_bars': len(data),
                'test_bars': len(data) - test_start_idx,
                'date_range': f"{data[test_start_idx]['time'].strftime('%Y-%m-%d')} - {data[-1]['time'].strftime('%Y-%m-%d')}",
            },
            'summary': {
                'total_trades': total_trades,
                'win_count': win_count,
                'loss_count': loss_count,
                'timeout_count': timeout_count,
                'win_rate': round(win_rate, 1),
                'long_trades': len(long_trades),
                'short_trades': len(short_trades),
                'long_win_rate': round(long_win_rate, 1),
                'short_win_rate': round(short_win_rate, 1),
            },
            'pnl': {
                'total_pnl_usdt': round(total_pnl_usdt, 2),
                'avg_win_usdt': round(avg_win, 2),
                'avg_loss_usdt': round(avg_loss, 2),
                'expected_value_per_trade': round(expected_value, 2),
                'profit_factor': round(profit_factor, 2),
                'gross_profit': round(gross_profit, 2),
                'gross_loss': round(gross_loss, 2),
            },
            'risk': {
                'max_consecutive_losses': max_consecutive_losses,
                'max_drawdown_usdt': round(max_drawdown, 2),
                'avg_actual_rr': round(avg_actual_rr, 2),
            },
            'trades': trades[-20:],  # 最近 20 笔交易
            'all_trades': trades,    # 所有交易 (供详细分析)
        }

    except Exception as e:
        import traceback
        return {
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc(),
        }


def print_backtest_results(result: Dict[str, Any]) -> None:
    """打印回测结果 (v3.0: 完整 S/R + SL/TP 详情)"""
    print_header(f"S/R 交易模拟回测 v3.0 (v3.17 R/R 驱动)")

    if not result['success']:
        print_result("回测失败", result.get('error', 'Unknown'), "error")
        if result.get('traceback'):
            print(f"  {result['traceback'][:300]}")
        return

    cfg = result['config']
    data = result['data']
    summary = result['summary']
    pnl = result['pnl']
    risk = result['risk']

    # 配置信息
    print_section("回测配置")
    print(f"  回测周期: {cfg['days']} 天")
    print(f"  K 线周期: {cfg['interval']}")
    print(f"  最小 R/R: {cfg['min_rr_ratio']}:1 (v3.17 标准)")
    print(f"  SL 缓冲: {cfg['sl_buffer_pct']}%")
    print(f"  仓位大小: ${cfg['position_usdt']:,} × {cfg['leverage']}x = ${cfg['position_usdt'] * cfg['leverage']:,}")
    print()
    print(f"  数据范围: {data['date_range']}")
    print(f"  K 线数量: {data['total_bars']} (测试: {data['test_bars']})")

    # 交易统计
    print_section("交易统计")
    print(f"  ┌─────────────────────┬──────────────────────────────────────┐")
    print(f"  │ 总交易次数          │ {summary['total_trades']:>36} │")
    print(f"  │ 胜利 / 亏损 / 超时  │ {summary['win_count']} / {summary['loss_count']} / {summary['timeout_count']:>27} │")
    print(f"  │ 胜率                │ {summary['win_rate']:>35.1f}% │")
    print(f"  ├─────────────────────┼──────────────────────────────────────┤")
    print(f"  │ LONG 交易           │ {summary['long_trades']:>26} ({summary['long_win_rate']:.1f}% 胜率) │")
    print(f"  │ SHORT 交易          │ {summary['short_trades']:>26} ({summary['short_win_rate']:.1f}% 胜率) │")
    print(f"  └─────────────────────┴──────────────────────────────────────┘")

    # 盈亏分析
    print_section("盈亏分析")
    pnl_status = "ok" if pnl['total_pnl_usdt'] > 0 else "error"
    print_result("总盈亏", f"${pnl['total_pnl_usdt']:,.2f}", pnl_status)
    print_result("平均盈利", f"${pnl['avg_win_usdt']:,.2f}", "info")
    print_result("平均亏损", f"${pnl['avg_loss_usdt']:,.2f}", "info")
    print_result("每笔期望收益", f"${pnl['expected_value_per_trade']:,.2f}",
                "ok" if pnl['expected_value_per_trade'] > 0 else "warn")
    print_result("盈利因子", f"{pnl['profit_factor']:.2f}",
                "ok" if pnl['profit_factor'] > 1.5 else "warn" if pnl['profit_factor'] > 1 else "error")
    print()
    print(f"     毛利润: ${pnl['gross_profit']:,.2f}")
    print(f"     毛亏损: ${pnl['gross_loss']:,.2f}")

    # 风险指标
    print_section("风险指标")
    print_result("最大连续亏损", f"{risk['max_consecutive_losses']} 笔",
                "ok" if risk['max_consecutive_losses'] <= 5 else "warn")
    print_result("最大回撤", f"${risk['max_drawdown_usdt']:,.2f}",
                "ok" if risk['max_drawdown_usdt'] < cfg['position_usdt'] else "warn")
    print_result("平均实际 R/R", f"{risk['avg_actual_rr']:.2f}",
                "ok" if risk['avg_actual_rr'] > 0 else "error")

    # ========== 全部交易记录 (完整 S/R + SL/TP 详情) ==========
    all_trades = result.get('all_trades', result.get('trades', []))
    print_section(f"全部交易记录 ({len(all_trades)} 笔, 含 S/R + SL/TP 详情)")

    if all_trades:
        # 表头
        print("  ┌──────┬──────────────────┬───────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────┬────────┬──────────┬──────────┐")
        print("  │  ID  │ 时间             │ 方向  │ 入场价   │ 支撑位   │ 阻力位   │  SL 价   │  TP 价   │ R/R  │ 结果   │ 出场价   │ 盈亏     │")
        print("  ├──────┼──────────────────┼───────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────┼────────┼──────────┼──────────┤")

        for t in all_trades:
            result_emoji = {"WIN": "✅", "LOSS": "❌", "TIMEOUT": "⏱️"}.get(t['result'], "?")
            pnl_str = f"${t['pnl_usdt']:+.0f}"
            print(f"  │ {t['id']:>4} │ {t['time']:<16} │ {t['signal']:<5} │ "
                  f"${t['entry_price']:>7,.0f} │ ${t['support']:>7,.0f} │ ${t['resistance']:>7,.0f} │ "
                  f"${t['sl_price']:>7,.0f} │ ${t['tp_price']:>7,.0f} │ {t['rr_ratio']:>4.1f} │ "
                  f"{result_emoji:<2}{t['result']:<4} │ ${t['exit_price']:>7,.0f} │ {pnl_str:>8} │")

        print("  └──────┴──────────────────┴───────┴──────────┴──────────┴──────────┴──────────┴──────────┴──────┴────────┴──────────┴──────────┘")

        # ========== 每笔交易的 SL/TP 距离分析 ==========
        print()
        print_section("SL/TP 距离分析 (每笔交易)")
        print("  ┌──────┬───────┬────────────┬────────────┬─────────────┬─────────────┬──────────────────────┐")
        print("  │  ID  │ 方向  │ SL距入场   │ TP距入场   │ 支撑距入场  │ 阻力距入场  │ S/R评分 (支撑/阻力)  │")
        print("  ├──────┼───────┼────────────┼────────────┼─────────────┼─────────────┼──────────────────────┤")

        for t in all_trades:
            entry = t['entry_price']
            sl_dist = abs(t['sl_price'] - entry) / entry * 100
            tp_dist = abs(t['tp_price'] - entry) / entry * 100
            sup_dist = abs(entry - t['support']) / entry * 100
            res_dist = abs(t['resistance'] - entry) / entry * 100
            score_str = f"{t['support_score']:.2f} / {t['resistance_score']:.2f}"
            print(f"  │ {t['id']:>4} │ {t['signal']:<5} │ {sl_dist:>8.2f}%  │ {tp_dist:>8.2f}%  │ "
                  f"{sup_dist:>9.2f}%   │ {res_dist:>9.2f}%   │ {score_str:>20} │")

        print("  └──────┴───────┴────────────┴────────────┴─────────────┴─────────────┴──────────────────────┘")

    # ========== S/R + SL/TP 质量分析 ==========
    print_section("S/R + SL/TP 质量分析")

    if all_trades:
        # SL 距离统计
        sl_distances = []
        tp_distances = []
        sup_distances = []
        res_distances = []

        for t in all_trades:
            entry = t['entry_price']
            sl_distances.append(abs(t['sl_price'] - entry) / entry * 100)
            tp_distances.append(abs(t['tp_price'] - entry) / entry * 100)
            sup_distances.append(abs(entry - t['support']) / entry * 100)
            res_distances.append(abs(t['resistance'] - entry) / entry * 100)

        avg_sl_dist = sum(sl_distances) / len(sl_distances)
        avg_tp_dist = sum(tp_distances) / len(tp_distances)
        avg_sup_dist = sum(sup_distances) / len(sup_distances)
        avg_res_dist = sum(res_distances) / len(res_distances)
        min_sl_dist = min(sl_distances)
        max_sl_dist = max(sl_distances)
        min_tp_dist = min(tp_distances)
        max_tp_dist = max(tp_distances)

        print("  📏 距离统计:")
        print(f"     SL 距入场:  平均 {avg_sl_dist:.2f}%  (最小 {min_sl_dist:.2f}%, 最大 {max_sl_dist:.2f}%)")
        print(f"     TP 距入场:  平均 {avg_tp_dist:.2f}%  (最小 {min_tp_dist:.2f}%, 最大 {max_tp_dist:.2f}%)")
        print(f"     支撑距入场: 平均 {avg_sup_dist:.2f}%")
        print(f"     阻力距入场: 平均 {avg_res_dist:.2f}%")

        # SL 合理性评估
        print()
        print("  📊 SL 合理性评估:")
        tight_sl = sum(1 for d in sl_distances if d < 0.3)
        normal_sl = sum(1 for d in sl_distances if 0.3 <= d <= 2.0)
        wide_sl = sum(1 for d in sl_distances if d > 2.0)
        total = len(sl_distances)
        print(f"     过紧 (<0.3%): {tight_sl}/{total} ({tight_sl/total*100:.0f}%)"
              f"  {'⚠️ 容易被噪音触发' if tight_sl/total > 0.2 else ''}")
        print(f"     正常 (0.3-2%): {normal_sl}/{total} ({normal_sl/total*100:.0f}%)"
              f"  {'✅ 合理范围' if normal_sl/total > 0.5 else ''}")
        print(f"     过宽 (>2%):   {wide_sl}/{total} ({wide_sl/total*100:.0f}%)"
              f"  {'⚠️ 风险过大' if wide_sl/total > 0.3 else ''}")

        # TP 合理性评估
        print()
        print("  📊 TP 合理性评估:")
        tight_tp = sum(1 for d in tp_distances if d < 0.5)
        normal_tp = sum(1 for d in tp_distances if 0.5 <= d <= 3.0)
        ambitious_tp = sum(1 for d in tp_distances if d > 3.0)
        print(f"     过近 (<0.5%): {tight_tp}/{total} ({tight_tp/total*100:.0f}%)"
              f"  {'⚠️ 盈利空间不足' if tight_tp/total > 0.2 else ''}")
        print(f"     正常 (0.5-3%): {normal_tp}/{total} ({normal_tp/total*100:.0f}%)"
              f"  {'✅ 合理范围' if normal_tp/total > 0.5 else ''}")
        print(f"     过远 (>3%):   {ambitious_tp}/{total} ({ambitious_tp/total*100:.0f}%)"
              f"  {'⚠️ 难以触及, 多TIMEOUT' if ambitious_tp/total > 0.3 else ''}")

        # S/R 评分与胜率相关性
        print()
        print("  📊 S/R 评分与胜率相关性:")
        high_score_trades = [t for t in all_trades if t['support_score'] >= 0.5 or t['resistance_score'] >= 0.5]
        low_score_trades = [t for t in all_trades if t['support_score'] < 0.5 and t['resistance_score'] < 0.5]

        if high_score_trades:
            high_wins = len([t for t in high_score_trades if t['result'] == 'WIN'])
            high_wr = high_wins / len(high_score_trades) * 100
            print(f"     高评分 (≥0.5) S/R: {len(high_score_trades)} 笔, 胜率 {high_wr:.1f}%")
        if low_score_trades:
            low_wins = len([t for t in low_score_trades if t['result'] == 'WIN'])
            low_wr = low_wins / len(low_score_trades) * 100
            print(f"     低评分 (<0.5) S/R: {len(low_score_trades)} 笔, 胜率 {low_wr:.1f}%")

        if high_score_trades and low_score_trades:
            high_wr = len([t for t in high_score_trades if t['result'] == 'WIN']) / len(high_score_trades) * 100
            low_wr = len([t for t in low_score_trades if t['result'] == 'WIN']) / len(low_score_trades) * 100
            if high_wr > low_wr + 5:
                print("     ✅ S/R 评分与胜率正相关 — 高评分 S/R 更可靠")
            elif abs(high_wr - low_wr) <= 5:
                print("     ⚠️ S/R 评分与胜率无明显相关 — 评分系统需优化")
            else:
                print("     ❌ S/R 评分与胜率负相关 — 评分逻辑可能有问题")

        # 按日期分组的表现 (检测趋势vs震荡)
        print()
        print("  📊 按日期分组表现:")
        from collections import defaultdict
        daily_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'timeouts': 0, 'pnl': 0.0, 'trades': 0})
        for t in all_trades:
            date = t['time'][:10]
            daily_stats[date]['trades'] += 1
            daily_stats[date]['pnl'] += t['pnl_usdt']
            if t['result'] == 'WIN':
                daily_stats[date]['wins'] += 1
            elif t['result'] == 'LOSS':
                daily_stats[date]['losses'] += 1
            else:
                daily_stats[date]['timeouts'] += 1

        print("  ┌────────────┬───────┬──────┬──────┬──────┬──────────┬────────┐")
        print("  │ 日期       │ 交易  │ 胜利 │ 亏损 │ 超时 │ 盈亏     │ 胜率   │")
        print("  ├────────────┼───────┼──────┼──────┼──────┼──────────┼────────┤")

        for date in sorted(daily_stats.keys()):
            d = daily_stats[date]
            wr = d['wins'] / d['trades'] * 100 if d['trades'] > 0 else 0
            pnl_str = f"${d['pnl']:+,.0f}"
            wr_emoji = "✅" if wr >= 50 else "❌" if wr < 30 else "⚠️"
            print(f"  │ {date} │ {d['trades']:>5} │ {d['wins']:>4} │ {d['losses']:>4} │ "
                  f"{d['timeouts']:>4} │ {pnl_str:>8} │ {wr_emoji}{wr:>4.0f}% │")

        print("  └────────────┴───────┴──────┴──────┴──────┴──────────┴────────┘")

        # 识别连续亏损段
        print()
        print("  📊 连续亏损段分析:")
        streak_start = None
        streak_count = 0
        streaks = []
        for i, t in enumerate(all_trades):
            if t['result'] == 'LOSS':
                if streak_start is None:
                    streak_start = i
                streak_count += 1
            else:
                if streak_count >= 3:  # 3连续亏损以上才记录
                    streaks.append({
                        'start_idx': streak_start,
                        'count': streak_count,
                        'start_time': all_trades[streak_start]['time'],
                        'end_time': all_trades[streak_start + streak_count - 1]['time'],
                        'total_loss': sum(all_trades[streak_start + j]['pnl_usdt'] for j in range(streak_count)),
                        'directions': [all_trades[streak_start + j]['signal'] for j in range(streak_count)],
                    })
                streak_start = None
                streak_count = 0
        # 检查尾部
        if streak_count >= 3:
            streaks.append({
                'start_idx': streak_start,
                'count': streak_count,
                'start_time': all_trades[streak_start]['time'],
                'end_time': all_trades[streak_start + streak_count - 1]['time'],
                'total_loss': sum(all_trades[streak_start + j]['pnl_usdt'] for j in range(streak_count)),
                'directions': [all_trades[streak_start + j]['signal'] for j in range(streak_count)],
            })

        if streaks:
            for s in streaks:
                dir_counts = {}
                for d in s['directions']:
                    dir_counts[d] = dir_counts.get(d, 0) + 1
                dir_str = ", ".join(f"{k}×{v}" for k, v in dir_counts.items())
                print(f"     {s['start_time']} ~ {s['end_time']}: "
                      f"{s['count']} 连亏, 亏损 ${s['total_loss']:,.0f} ({dir_str})")
                # 诊断原因
                if len(dir_counts) == 1:
                    only_dir = list(dir_counts.keys())[0]
                    print(f"       → 全部 {only_dir}: 可能是单边行情中逆势操作")
                elif dir_counts.get('LONG', 0) > dir_counts.get('SHORT', 0) * 2:
                    print(f"       → LONG 为主: 可能处于下跌趋势")
                elif dir_counts.get('SHORT', 0) > dir_counts.get('LONG', 0) * 2:
                    print(f"       → SHORT 为主: 可能处于上涨趋势")
        else:
            print("     ✅ 无 3 连亏以上的情况")

    # 结论
    print_section("结论")

    if pnl['total_pnl_usdt'] > 0 and pnl['profit_factor'] > 1.5:
        print("  ✅ 策略盈利能力: 强")
        print(f"     基于 S/R 的 SL/TP 设置在过去 {cfg['days']} 天表现良好")
        print(f"     v3.17 R/R >= {cfg['min_rr_ratio']}:1 入场标准有效过滤低质量信号")
    elif pnl['total_pnl_usdt'] > 0:
        print("  ⚠️ 策略盈利能力: 中等")
        print(f"     盈利但盈利因子偏低 ({pnl['profit_factor']:.2f})")
        print("     建议: 提高 R/R 要求 或 优化 S/R 计算方法")
    else:
        print("  ❌ 策略盈利能力: 弱")
        print("     S/R 基础的 SL/TP 在当前市场条件下表现不佳")
        print("     可能原因: 趋势行情突破 S/R, 或 S/R 计算不准确")

    # 建议
    print()
    print("  📊 分析:")
    if summary['win_rate'] < 40:
        print("     - 胜率偏低 - 考虑更严格的入场条件")
    if summary['long_win_rate'] < summary['short_win_rate'] - 10:
        print("     - LONG 胜率明显低于 SHORT - 可能处于下跌趋势")
    elif summary['short_win_rate'] < summary['long_win_rate'] - 10:
        print("     - SHORT 胜率明显低于 LONG - 可能处于上涨趋势")
    if risk['max_consecutive_losses'] > 5:
        print("     - 连续亏损次数较多 - 考虑加入趋势过滤 (ADX v3.20)")

    if all_trades:
        # SL/TP 优化建议
        print()
        print("  💡 SL/TP 优化建议:")
        if avg_sl_dist < 0.5:
            print(f"     - SL 平均距离 {avg_sl_dist:.2f}% 偏小, 建议增大 sl_buffer_pct (当前 {cfg['sl_buffer_pct']}%)")
        if avg_tp_dist > 3.0:
            print(f"     - TP 平均距离 {avg_tp_dist:.2f}% 偏大, 阻力位可能不准确或市场无法到达")
        timeout_rate = summary['timeout_count'] / summary['total_trades'] * 100 if summary['total_trades'] > 0 else 0
        if timeout_rate > 20:
            print(f"     - 超时率 {timeout_rate:.0f}% 偏高, TP 可能设置过远或持仓时间不足")


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

        # 构建 bars_data (v3.0: Swing Point / ATR / Touch Count)
        bars_data = []
        for k in klines:
            bars_data.append({
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
            })

        # 计算 S/R Zones v3.0 (无 Order Wall, 含 Swing Point)
        sr_calc = SRZoneCalculator(
            swing_detection_enabled=True,
            use_atr_adaptive=True,
        )
        bb_data = {'upper': bb_upper, 'lower': bb_lower, 'middle': sma_20}
        sma_data = {'sma_50': sma_50, 'sma_200': 0}  # 简化，不计算 SMA_200

        result = sr_calc.calculate_with_detailed_report(
            current_price=current_price,
            bb_data=bb_data,
            sma_data=sma_data,
            orderbook_anomalies=None,  # 不传入 Order Wall
            bars_data=bars_data,
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

        # v3.0 sr_zones config
        sr_cfg = config.get('sr_zones', default={})
        result['sr_zones_enabled'] = sr_cfg.get('enabled', True) if sr_cfg else True
        swing_cfg = sr_cfg.get('swing_detection', {}) if sr_cfg else {}
        result['swing_detection_enabled'] = swing_cfg.get('enabled', True)
        cluster_cfg = sr_cfg.get('clustering', {}) if sr_cfg else {}
        result['atr_adaptive_enabled'] = cluster_cfg.get('use_atr_adaptive', True)
        scoring_cfg = sr_cfg.get('scoring', {}) if sr_cfg else {}
        result['touch_count_enabled'] = scoring_cfg.get('touch_count_enabled', True)

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
    print_header("支撑阻力位全面诊断 v3.1")
    print(f"  时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

    # Dynamic base currency from symbol
    _symbol = "BTCUSDT"
    base_currency = _symbol.replace('USDT', '') if 'USDT' in _symbol else _symbol.split('-')[0] if '-' in _symbol else 'BTC'

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
        # v3.0 features
        print_result("Swing Point 检测", config.get('swing_detection_enabled', True),
                    "ok" if config.get('swing_detection_enabled') else "warn")
        print_result("ATR 自适应聚类", config.get('atr_adaptive_enabled', True),
                    "ok" if config.get('atr_adaptive_enabled') else "warn")
        print_result("Touch Count 评分", config.get('touch_count_enabled', True),
                    "ok" if config.get('touch_count_enabled') else "warn")
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
            swing_tag = " [Swing]" if zone.has_swing_point else ""
            touch_tag = f" [T:{zone.touch_count}]" if zone.touch_count > 0 else ""
            print(f"      {i+1}. ${zone.price_center:,.0f} ({zone.distance_pct:.1f}% away) [{zone.strength}]{swing_tag}{touch_tag}")

        print_result("阻力区数量", len(res_zones), "info")
        for i, zone in enumerate(res_zones[:2]):
            swing_tag = " [Swing]" if zone.has_swing_point else ""
            touch_tag = f" [T:{zone.touch_count}]" if zone.touch_count > 0 else ""
            print(f"      {i+1}. ${zone.price_center:,.0f} ({zone.distance_pct:.1f}% away) [{zone.strength}]{swing_tag}{touch_tag}")

        hard_control = result.get('hard_control', {})
        print_result("Block LONG", hard_control.get('block_long', False),
                    "warn" if hard_control.get('block_long') else "ok")
        print_result("Block SHORT", hard_control.get('block_short', False),
                    "warn" if hard_control.get('block_short') else "ok")
    else:
        print_result("计算失败", sr_no_wall.get('error', 'Unknown'), "error")

    print()
    print("  📝 计算方法: BB + SMA_50 + Swing Point + ATR聚类 + Touch Count (v3.0)")
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
            wall_info = f" [Order Wall: {zone.wall_size_btc:.1f} {base_currency}]" if zone.has_order_wall else ""
            swing_tag = " [Swing]" if zone.has_swing_point else ""
            touch_tag = f" [T:{zone.touch_count}]" if zone.touch_count > 0 else ""
            src = ", ".join(zone.sources[:2]) if zone.sources else zone.source_type
            print(f"      {i+1}. ${zone.price_center:,.0f} ({zone.distance_pct:.1f}%) [{zone.strength}]{wall_info}{swing_tag}{touch_tag}")
            print(f"         来源: {src}")

        print_result("阻力区数量", len(res_zones), "info")
        for i, zone in enumerate(res_zones[:3]):
            wall_info = f" [Order Wall: {zone.wall_size_btc:.1f} {base_currency}]" if zone.has_order_wall else ""
            swing_tag = " [Swing]" if zone.has_swing_point else ""
            touch_tag = f" [T:{zone.touch_count}]" if zone.touch_count > 0 else ""
            src = ", ".join(zone.sources[:2]) if zone.sources else zone.source_type
            print(f"      {i+1}. ${zone.price_center:,.0f} ({zone.distance_pct:.1f}%) [{zone.strength}]{wall_info}{swing_tag}{touch_tag}")
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
                print(f"         ${a.get('price', 0):,.0f}: {a.get('size', 0):.2f} {base_currency} ({a.get('z_score', 0):.1f}σ)")
            print(f"      Ask 大单: {len(ask_anomalies)} 个")
            for a in ask_anomalies[:3]:
                print(f"         ${a.get('price', 0):,.0f}: {a.get('size', 0):.2f} {base_currency} ({a.get('z_score', 0):.1f}σ)")
    else:
        print_result("计算失败", sr_with_wall.get('error', 'Unknown'), "error")
        if sr_with_wall.get('traceback'):
            print(f"  Traceback: {sr_with_wall['traceback'][:200]}...")

    print()
    print("  📝 计算方法: BB + SMA_50 + Order Wall + Swing Point + ATR聚类 + Touch Count (v3.0)")
    print("  📝 来源: utils/sr_zone_calculator.py + utils/orderbook_processor.py")

    # 5.5 ADX 趋势强度 (v3.20)
    if sr_with_wall['success'] and sr_with_wall.get('tech_data'):
        tech = sr_with_wall['tech_data']
        adx_val = tech.get('adx', 0)
        di_plus = tech.get('di_plus', 0)
        di_minus = tech.get('di_minus', 0)
        adx_regime = tech.get('adx_regime', 'N/A')
        adx_dir = tech.get('adx_direction', 'N/A')

        print()
        print_section("5.5 趋势强度 (ADX v3.20)")
        adx_status = "ok" if adx_val < 25 else "warn"
        print_result("ADX(14)", f"{adx_val:.1f} ({adx_regime})", adx_status)
        print_result("方向", f"DI+={di_plus:.1f}, DI-={di_minus:.1f} → {adx_dir}", "info")

        if adx_val < 20:
            print_result("S/R 可靠性", "HIGH — 震荡市，S/R 反弹概率 ~70%", "ok")
        elif adx_val < 25:
            print_result("S/R 可靠性", "MODERATE — 弱趋势，需要确认", "warn")
        elif adx_val < 40:
            print_result("S/R 可靠性", "LOW — 强趋势，S/R 反弹概率 ~25%，优先顺势", "warn")
        else:
            print_result("S/R 可靠性", "VERY LOW — 极强趋势，避免逆势 S/R 入场", "error")

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
        "[v3.0 已实现] Swing Point Detection (Williams Fractal, Chan 2022 MDPI)",
        "[v3.0 已实现] ATR 自适应聚类 (替代固定 0.5% 阈值)",
        "[v3.0 已实现] Touch Count 评分 (Osler 2000, FRB NY: 2-3次最优)",
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
    print("     ┌──────────────────────────┬──────────┬──────────┬──────────┬──────────┐")
    print("     │ 方法                     │ 稳定性   │ 实时性   │ 可靠性   │ 专业度   │")
    print("     ├──────────────────────────┼──────────┼──────────┼──────────┼──────────┤")
    print("     │ 简单高低点               │ ★★★★★    │ ★★★      │ ★★★      │ ★★       │")
    print("     │ S/R Zone (BB+SMA)        │ ★★★★     │ ★★★      │ ★★★★     │ ★★★      │")
    print("     │ Swing Point (v3.0)       │ ★★★★★    │ ★★★★     │ ★★★★★    │ ★★★★★    │")
    print("     │ Order Wall               │ ★★       │ ★★★★★    │ ★★       │ ★★★      │")
    print("     │ Value Area (CME)         │ ★★★★★    │ ★★       │ ★★★★★    │ ★★★★★    │")
    print("     │ HVN/LVN (Volume Profile) │ ★★★★★    │ ★★       │ ★★★★★    │ ★★★★★    │")
    print("     └──────────────────────────┴──────────┴──────────┴──────────┴──────────┘")
    print()
    print("  💡 全球标准做法:")
    print("     1. Swing Point (N-bar Pivot) = 最强 S/R 来源 (Chan 2022 MDPI, +65% ML利润)")
    print("     2. ATR 自适应聚类 = 波动率感知的区域合并")
    print("     3. Touch Count 2-3次 = 最佳强度 (Osler 2000, FRB NY)")
    print("     4. Value Area 边界 = 主要 S/R (CME Market Profile)")
    print("     5. HVN = 强支撑阻力 (价格在此停留时间长)")
    print("     6. LVN = 快速穿越区 (不适合作为 S/R)")
    print()
    print("  📚 参考文献:")
    print("     - Chan 2022 (MDPI): Support/Resistance in Algorithmic Trading")
    print("     - Osler 2000 (FRB NY): Support/Resistance Technical Analysis")
    print("     - CME Group Market Profile User Guide")
    print("     - IEEE: Evolutionary Optimized Stock Support-Resistance")

    print()
    print(f"  诊断完成: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="支撑阻力位全面诊断 v3.1")
    parser.add_argument("--export", action="store_true", help="导出到文件")
    parser.add_argument("--backtest", action="store_true", help="仅运行交易模拟回测")
    parser.add_argument("--mock", action="store_true", help="使用模拟数据 (无网络环境)")
    parser.add_argument("--days", type=int, default=14, help="回测天数 (默认 14)")
    parser.add_argument("--min-rr", type=float, default=1.5, help="最小 R/R 比率 (默认 1.5)")
    parser.add_argument("--position", type=float, default=1000, help="每笔仓位 USDT (默认 1000)")
    parser.add_argument("--leverage", type=int, default=10, help="杠杆倍数 (默认 10)")
    args = parser.parse_args()

    def run_backtest_only():
        """仅运行回测"""
        print("  ⏳ 正在获取历史数据并运行回测，请稍候...")
        print()
        result = backtest_sr_trading_simulation(
            days=args.days,
            min_rr_ratio=args.min_rr,
            position_usdt=args.position,
            leverage=args.leverage,
            use_mock=args.mock,
        )
        print_backtest_results(result)

    if args.backtest:
        # 仅运行回测
        if args.export:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = project_root / "logs" / f"sr_backtest_{timestamp}.txt"
            output_file.parent.mkdir(parents=True, exist_ok=True)

            import io
            from contextlib import redirect_stdout

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                run_backtest_only()

            output = buffer.getvalue()
            print(output)

            with open(output_file, 'w') as f:
                f.write(output)

            print(f"\n📁 回测报告已保存到: {output_file}")
        else:
            run_backtest_only()

    elif args.export:
        # 完整诊断 + 导出
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = project_root / "logs" / f"sr_diagnosis_{timestamp}.txt"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        import io
        from contextlib import redirect_stdout

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            run_full_diagnosis()
            # 添加完整交易回测
            print()
            print(f"  ⏳ 正在运行完整交易模拟回测 ({args.days} 天)...")
            print()
            result = backtest_sr_trading_simulation(days=args.days)
            print_backtest_results(result)

        output = buffer.getvalue()
        print(output)

        with open(output_file, 'w') as f:
            f.write(output)

        print(f"\n📁 诊断报告已保存到: {output_file}")
    else:
        # 完整诊断
        run_full_diagnosis()
        # 添加完整交易回测
        print()
        print(f"  ⏳ 正在运行完整交易模拟回测 ({args.days} 天)...")
        print()
        result = backtest_sr_trading_simulation(days=args.days)
        print_backtest_results(result)


if __name__ == "__main__":
    main()
