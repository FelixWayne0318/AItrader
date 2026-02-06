#!/usr/bin/env python3
"""
支撑阻力位全面诊断脚本 v1.0

功能:
1. 检查所有支撑阻力数据来源
2. 对比不同计算方式的结果
3. 检查实盘服务的日志和缓存
4. 分析 Telegram Heartbeat 使用的数据
5. 给出诊断报告和修复建议

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

    # 6. Telegram 数据源分析
    analyze_telegram_data_source()

    # 7. 服务日志检查
    print_section("7. 服务日志检查")
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

    # 8. 问题诊断
    print_section("8. 问题诊断")

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

    # 9. 修复建议
    print_section("9. 修复建议")

    suggestions.extend([
        "将 Heartbeat 发送移到分析之后，使用最新数据",
        "降低 Order Wall 权重 (当前 2.0，建议 0.5-1.0)",
        "添加 Order Wall 最小 BTC 阈值 (如 > 10 BTC 才算大单)",
        "考虑使用简单高低点作为主要支撑阻力来源",
        "实现 Swing Point Detection (全球标准方法)",
    ])

    for i, s in enumerate(suggestions, 1):
        print(f"  {i}. {s}")

    # 10. 总结
    print_section("10. 总结对比表")

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

    print("  └─────────────────────────┴───────────────────┴───────────────────┘")

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
