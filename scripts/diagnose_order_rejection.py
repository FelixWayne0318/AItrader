#!/usr/bin/env python3
"""
diagnose_order_rejection.py — 诊断订单被拒原因

在服务器运行:
  cd /home/linuxuser/nautilus_AItrader
  source venv/bin/activate
  python3 scripts/diagnose_order_rejection.py

功能:
1. 从 journalctl 日志提取最近的 SL/TP 验证和拒单信息
2. 查询 Binance 实时仓位和余额
3. 查询最近订单历史
4. 重新计算 S/R-based SL/TP 和 R/R
5. 判断拒单是否合理
"""

import os
import sys
import subprocess
import json
from datetime import datetime, timezone

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def get_recent_logs(lines: int = 500) -> str:
    """从 journalctl 获取最近的服务日志"""
    try:
        result = subprocess.run(
            ['journalctl', '-u', 'nautilus-trader', '--no-pager',
             '-n', str(lines), '--no-hostname'],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout
    except Exception as e:
        print(f"  ⚠️ 无法读取 journalctl: {e}")
        # Try fallback: PM2 logs
        try:
            result = subprocess.run(
                ['pm2', 'logs', 'nautilus-trader', '--lines', str(lines), '--nostream'],
                capture_output=True, text=True, timeout=10
            )
            return result.stdout + result.stderr
        except Exception:
            return ""


def analyze_logs(logs: str):
    """分析日志中的订单拒绝信息"""
    section("1. 日志分析 — 最近的 SL/TP 验证和拒单")

    # Keywords to search for
    patterns = {
        '🚫 SL/TP validation failed': [],
        '🚫 S/R-based SL/TP rejected': [],
        '⚠️ AI SL/TP invalid': [],
        '❌ SL/TP validation failed': [],
        '❌ Cannot determine price': [],
        '🚫 开仓被阻止': [],
        '✅ SL/TP validated': [],
        '📍 S/R-based SL/TP': [],
        '🎯 SL/TP validated for entry': [],
        'R/R': [],
        '🎯 Judge Decision': [],
        'validate_multiagent_sltp': [],
    }

    lines = logs.split('\n')
    for line in lines:
        for pattern in patterns:
            if pattern in line:
                patterns[pattern].append(line.strip())

    # Show most recent matches
    for pattern, matches in patterns.items():
        if matches:
            print(f"\n  📌 '{pattern}' ({len(matches)} 条)")
            # Show last 3 matches
            for m in matches[-3:]:
                # Truncate long lines
                display = m[-200:] if len(m) > 200 else m
                print(f"    {display}")

    # Specific: last rejection reason
    rejections = (
        patterns['🚫 SL/TP validation failed'] +
        patterns['🚫 S/R-based SL/TP rejected'] +
        patterns['❌ SL/TP validation failed'] +
        patterns['🚫 开仓被阻止']
    )
    if rejections:
        print(f"\n  🔍 最后一次拒绝:")
        print(f"    {rejections[-1]}")
    else:
        print(f"\n  ✅ 日志中未发现拒单记录")

    # Last successful validation
    successes = patterns['✅ SL/TP validated'] + patterns['🎯 SL/TP validated for entry']
    if successes:
        print(f"\n  🔍 最后一次成功验证:")
        print(f"    {successes[-1]}")


def check_binance_position():
    """查询 Binance 实时仓位"""
    section("2. Binance 实时状态")

    try:
        from dotenv import load_dotenv
        env_path = os.path.expanduser('~/.env.aitrader')
        if os.path.exists(env_path):
            load_dotenv(env_path)

        api_key = os.environ.get('BINANCE_API_KEY')
        api_secret = os.environ.get('BINANCE_API_SECRET')

        if not api_key or not api_secret:
            print("  ⚠️ 未找到 BINANCE_API_KEY/SECRET, 跳过")
            return

        from utils.binance_account import BinanceAccountFetcher
        client = BinanceAccountFetcher(api_key, api_secret)

        # Get position
        positions = client.get_positions(symbol='BTCUSDT')
        if positions:
            for pos in positions:
                amt = float(pos.get('positionAmt', 0))
                entry = float(pos.get('entryPrice', 0))
                pnl = float(pos.get('unrealized_pnl', pos.get('unRealizedProfit', 0)))
                leverage = pos.get('leverage', '?')
                side = 'LONG' if amt > 0 else 'SHORT'
                print(f"  📊 持仓: {side} {abs(amt)} BTC")
                print(f"  💰 入场: ${entry:,.2f}")
                print(f"  📈 未实现盈亏: ${pnl:,.2f}")
                print(f"  🔧 杠杆: {leverage}x")
        else:
            print("  💼 BTCUSDT: 空仓")

        # Get balance
        balance = client.get_balance()
        if balance:
            print(f"\n  🏦 余额: ${balance.get('total_balance', 0):,.2f}")
            print(f"  📊 可用: ${balance.get('available_balance', 0):,.2f}")

        # Get recent price
        price = client.get_realtime_price('BTCUSDT')
        if price:
            print(f"\n  💲 BTC 当前价: ${price:,.2f}")

        return price

    except ImportError as e:
        print(f"  ⚠️ 导入失败: {e}")
        print("  提示: 确保在虚拟环境中运行")
    except Exception as e:
        print(f"  ❌ Binance 查询失败: {e}")

    return None


def check_recent_orders():
    """查询最近的订单历史"""
    section("3. 最近订单历史 (Binance)")

    try:
        from dotenv import load_dotenv
        env_path = os.path.expanduser('~/.env.aitrader')
        if os.path.exists(env_path):
            load_dotenv(env_path)

        import hmac
        import hashlib
        import time
        import requests

        api_key = os.environ.get('BINANCE_API_KEY')
        api_secret = os.environ.get('BINANCE_API_SECRET')

        if not api_key or not api_secret:
            print("  ⚠️ 跳过 (无 API key)")
            return

        base_url = 'https://fapi.binance.com'

        # Get recent orders (last 24h)
        timestamp = int(time.time() * 1000)
        params = f'symbol=BTCUSDT&limit=10&timestamp={timestamp}'
        signature = hmac.new(
            api_secret.encode(), params.encode(), hashlib.sha256
        ).hexdigest()

        resp = requests.get(
            f'{base_url}/fapi/v1/allOrders?{params}&signature={signature}',
            headers={'X-MBX-APIKEY': api_key},
            timeout=10,
        )

        if resp.status_code == 200:
            orders = resp.json()
            if orders:
                print(f"  最近 {len(orders)} 个订单:\n")
                for o in orders[-5:]:  # Show last 5
                    status = o.get('status', '?')
                    side = o.get('side', '?')
                    otype = o.get('type', '?')
                    price_o = float(o.get('price', 0) or o.get('stopPrice', 0) or 0)
                    qty = float(o.get('origQty', 0))
                    update_time = o.get('updateTime', 0)
                    time_str = datetime.fromtimestamp(
                        update_time / 1000, tz=timezone.utc
                    ).strftime('%m-%d %H:%M') if update_time else '?'

                    status_icon = '✅' if status == 'FILLED' else '❌' if status in ('CANCELED', 'EXPIRED', 'REJECTED') else '⏳'
                    print(f"  {status_icon} {time_str} | {side} {otype} | "
                          f"${price_o:,.2f} × {qty} | {status}")
            else:
                print("  📭 无最近订单")
        else:
            print(f"  ❌ API 错误: {resp.status_code} {resp.text[:200]}")

    except Exception as e:
        print(f"  ❌ 订单查询失败: {e}")


def simulate_sltp_validation(current_price: float = None):
    """模拟 SL/TP 验证，显示 R/R 计算过程"""
    section("4. SL/TP 验证模拟")

    if not current_price:
        print("  ⚠️ 无法获取当前价格，跳过模拟")
        return

    try:
        from utils.config_manager import ConfigManager
        config = ConfigManager(env='production')
        config.load()

        min_rr = config.get('trading_logic', 'min_rr_ratio', default=1.5)
        sl_buffer_pct = config.get('trading_logic', 'sl_buffer_pct', default=0.005)
        print(f"  📋 配置:")
        print(f"    min_rr_ratio: {min_rr}")
        print(f"    sl_buffer_pct: {sl_buffer_pct}")
    except Exception as e:
        print(f"  ⚠️ 配置加载失败: {e}")
        min_rr = 1.5
        sl_buffer_pct = 0.005

    # Try to get S/R zones from the data assembler
    try:
        from utils.sr_zone_detector import SRZoneDetector
        from utils.binance_kline_client import BinanceKlineClient

        print(f"\n  📊 获取 S/R zones...")
        kline_client = BinanceKlineClient()

        # Get klines for S/R detection
        klines_1d = kline_client.get_klines('BTCUSDT', '1d', limit=60)
        klines_4h = kline_client.get_klines('BTCUSDT', '4h', limit=60)
        klines_15m = kline_client.get_klines('BTCUSDT', '15m', limit=60)

        detector = SRZoneDetector()
        zones = detector.detect_zones(
            klines_1d=klines_1d,
            klines_4h=klines_4h,
            klines_15m=klines_15m,
            current_price=current_price,
        )

        if zones:
            nearest_s = zones.get('nearest_support')
            nearest_r = zones.get('nearest_resistance')

            if nearest_s and hasattr(nearest_s, 'price_center'):
                s_price = nearest_s.price_center
                s_dist = ((current_price - s_price) / current_price) * 100
                print(f"  📍 最近支撑: ${s_price:,.0f} ({s_dist:+.1f}%)")
                print(f"    强度: {nearest_s.strength}, 级别: {nearest_s.level}")
            else:
                s_price = 0
                print(f"  ⚠️ 未检测到支撑位")

            if nearest_r and hasattr(nearest_r, 'price_center'):
                r_price = nearest_r.price_center
                r_dist = ((r_price - current_price) / current_price) * 100
                print(f"  📍 最近阻力: ${r_price:,.0f} ({r_dist:+.1f}%)")
                print(f"    强度: {nearest_r.strength}, 级别: {nearest_r.level}")
            else:
                r_price = 0
                print(f"  ⚠️ 未检测到阻力位")

            # Simulate LONG R/R
            if s_price > 0 and r_price > 0:
                print(f"\n  📐 R/R 模拟:")

                # LONG: SL below support, TP at resistance
                long_sl = s_price * (1 - sl_buffer_pct)
                long_tp = r_price
                long_risk = current_price - long_sl
                long_reward = long_tp - current_price
                long_rr = long_reward / long_risk if long_risk > 0 else 0
                long_pass = '✅' if long_rr >= min_rr else '❌'

                print(f"    LONG:  SL=${long_sl:,.0f} TP=${long_tp:,.0f}")
                print(f"           Risk=${long_risk:,.0f} Reward=${long_reward:,.0f}")
                print(f"           R/R={long_rr:.2f}:1 {long_pass} (需要 >= {min_rr}:1)")

                # SHORT: SL above resistance, TP at support
                short_sl = r_price * (1 + sl_buffer_pct)
                short_tp = s_price
                short_risk = short_sl - current_price
                short_reward = current_price - short_tp
                short_rr = short_reward / short_risk if short_risk > 0 else 0
                short_pass = '✅' if short_rr >= min_rr else '❌'

                print(f"    SHORT: SL=${short_sl:,.0f} TP=${short_tp:,.0f}")
                print(f"           Risk=${short_risk:,.0f} Reward=${short_reward:,.0f}")
                print(f"           R/R={short_rr:.2f}:1 {short_pass} (需要 >= {min_rr}:1)")

                # Position analysis
                total_range = r_price - s_price
                from_support = current_price - s_price
                position_pct = (from_support / total_range * 100) if total_range > 0 else 50
                print(f"\n  📍 价格位置:")
                print(f"    S/R 范围: ${s_price:,.0f} — ${r_price:,.0f} (${total_range:,.0f})")
                print(f"    当前价格在范围的 {position_pct:.0f}% 位置")

                if position_pct > 40 and position_pct < 60:
                    print(f"    ⚠️ 价格在 S/R 中间区域 (no-man's-land)")
                    print(f"    📝 这就是为什么两个方向的 R/R 都不够 — 合理的 HOLD")
                elif position_pct <= 40:
                    print(f"    📝 靠近支撑位 — LONG R/R 较好")
                else:
                    print(f"    📝 靠近阻力位 — SHORT R/R 较好")

            # Show all zones
            support_zones = zones.get('support_zones', [])
            resistance_zones = zones.get('resistance_zones', [])
            if support_zones or resistance_zones:
                print(f"\n  📊 所有 S/R 区域:")
                for z in sorted(resistance_zones, key=lambda x: x.price_center, reverse=True)[:5]:
                    dist = ((z.price_center - current_price) / current_price) * 100
                    print(f"    R ${z.price_center:,.0f} ({dist:+.1f}%) [{z.strength}/{z.level}]")
                print(f"    ── 当前 ${current_price:,.0f} ──")
                for z in sorted(support_zones, key=lambda x: x.price_center, reverse=True)[:5]:
                    dist = ((z.price_center - current_price) / current_price) * 100
                    print(f"    S ${z.price_center:,.0f} ({dist:+.1f}%) [{z.strength}/{z.level}]")
        else:
            print("  ⚠️ S/R zone 检测返回空")

    except ImportError as e:
        print(f"  ⚠️ 模块导入失败: {e}")
        print("  尝试手动计算...")

        # Manual R/R calculation with simple percentage
        print(f"\n  📐 手动 R/R 计算 (基于固定 2% SL):")
        for side_name in ['LONG', 'SHORT']:
            sl_pct = 0.02
            tp_pct = 0.03
            if side_name == 'LONG':
                sl = current_price * (1 - sl_pct)
                tp = current_price * (1 + tp_pct)
            else:
                sl = current_price * (1 + sl_pct)
                tp = current_price * (1 - tp_pct)
            risk = abs(current_price - sl)
            reward = abs(tp - current_price)
            rr = reward / risk if risk > 0 else 0
            print(f"    {side_name}: SL=${sl:,.0f} TP=${tp:,.0f} R/R={rr:.2f}:1")

    except Exception as e:
        print(f"  ❌ S/R 分析失败: {e}")
        import traceback
        traceback.print_exc()


def check_config():
    """检查关键配置"""
    section("5. 关键配置检查")

    try:
        from utils.config_manager import ConfigManager
        config = ConfigManager(env='production')
        config.load()

        checks = [
            ('trading_logic', 'min_rr_ratio'),
            ('trading_logic', 'sl_buffer_pct'),
            ('trading_logic', 'min_confidence_to_trade'),
            ('trading_logic', 'sltp_method'),
            ('trading_logic', 'min_notional_usdt'),
            ('position', 'max_position_ratio'),
            ('capital', 'leverage'),
            ('capital', 'equity'),
        ]

        for *path, key in [c for c in checks]:
            try:
                val = config.get(*path, key)
                path_str = '.'.join([*path, key]) if len(path) > 0 else key
                print(f"  {path_str}: {val}")
            except Exception:
                path_str = '.'.join([*path, key]) if len(path) > 0 else key
                print(f"  {path_str}: ⚠️ 未找到")

    except Exception as e:
        print(f"  ⚠️ 配置加载失败: {e}")


def summary():
    """总结"""
    section("6. 诊断总结")
    print("""
  拒单原因判断:

  ✅ 合理拒绝的情况:
    - R/R < 1.5:1 → 价格在 S/R 中间区域，风险不划算
    - 无有效 S/R zones → 无法确定止损止盈
    - 价格数据缺失 → 无法计算

  ❌ 不合理拒绝的情况:
    - R/R > 1.5:1 但仍被拒绝 → 检查 validate_multiagent_sltp 逻辑
    - S/R zones 检测到了但距离计算错误 → 检查 sl_buffer_pct
    - 配置值异常 (如 min_rr_ratio 设太高)

  📝 如需调整:
    - 降低 R/R 门槛: configs/base.yaml → trading_logic.min_rr_ratio: 1.2
    - 调整 SL buffer: configs/base.yaml → trading_logic.sl_buffer_pct: 0.003
    - 修改后重启: sudo systemctl restart nautilus-trader
""")


def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     AItrader 订单拒绝诊断工具 v1.0                       ║")
    print("║     诊断 SL/TP 验证失败和 R/R 不足问题                    ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"  时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")

    # 1. Analyze logs
    logs = get_recent_logs(500)
    if logs:
        analyze_logs(logs)
    else:
        print("\n  ⚠️ 无法读取日志，跳过日志分析")

    # 2. Check Binance position
    current_price = check_binance_position()

    # 3. Check recent orders
    check_recent_orders()

    # 4. Simulate SL/TP validation
    simulate_sltp_validation(current_price)

    # 5. Check config
    check_config()

    # 6. Summary
    summary()


if __name__ == '__main__':
    main()
