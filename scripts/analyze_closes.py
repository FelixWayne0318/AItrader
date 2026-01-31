#!/usr/bin/env python3
"""
分析最近平仓原因的诊断脚本

平仓方式:
1. 止损 (Stop Loss) - 触发止损价格
2. 止盈 (Take Profit) - 触发止盈价格
3. 移动止损 (Trailing Stop) - 移动止损被触发
4. 手动平仓 (Telegram /close) - 用户通过命令平仓
5. 信号反转 (Signal Reversal) - AI 信号从 LONG→SHORT 或 SHORT→LONG
6. 减仓 (Reduce Position) - 部分平仓
7. 清算 (Liquidation) - 被交易所强制平仓

用法:
    python3 scripts/analyze_closes.py
    python3 scripts/analyze_closes.py --days 7
    python3 scripts/analyze_closes.py --json
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

def load_env():
    """加载环境变量"""
    env_path = Path.home() / ".env.aitrader"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())

def get_binance_client():
    """获取 Binance 客户端"""
    try:
        from binance.client import Client
        api_key = os.environ.get('BINANCE_API_KEY')
        api_secret = os.environ.get('BINANCE_API_SECRET')
        if not api_key or not api_secret:
            print("❌ 缺少 BINANCE_API_KEY 或 BINANCE_API_SECRET")
            return None
        return Client(api_key, api_secret)
    except ImportError:
        print("❌ 请安装 python-binance: pip install python-binance")
        return None

def analyze_trade_history(client, symbol="BTCUSDT", days=30):
    """分析交易历史"""

    # 获取最近的交易记录
    start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

    print(f"\n📊 获取最近 {days} 天的交易记录...")

    try:
        # 获取合约交易历史
        trades = client.futures_account_trades(symbol=symbol, startTime=start_time)

        if not trades:
            print("ℹ️ 没有找到交易记录")
            return None

        print(f"✅ 找到 {len(trades)} 条交易记录")

        # 获取订单历史 (包含订单类型信息)
        orders = client.futures_get_all_orders(symbol=symbol, startTime=start_time)

        # 建立订单 ID 到订单信息的映射
        order_map = {str(o['orderId']): o for o in orders}

        return trades, order_map, orders

    except Exception as e:
        print(f"❌ 获取交易记录失败: {e}")
        return None

def classify_close_reason(order):
    """根据订单信息分类平仓原因"""

    order_type = order.get('type', '')
    reduce_only = order.get('reduceOnly', False)
    close_position = order.get('closePosition', False)
    stop_price = float(order.get('stopPrice', 0))
    status = order.get('status', '')

    # 判断逻辑
    if order_type == 'STOP_MARKET' and reduce_only:
        if 'trailing' in str(order.get('clientOrderId', '')).lower():
            return 'TRAILING_STOP', '移动止损触发'
        return 'STOP_LOSS', '止损触发'

    elif order_type == 'TAKE_PROFIT_MARKET' and reduce_only:
        return 'TAKE_PROFIT', '止盈触发'

    elif order_type == 'LIMIT' and reduce_only:
        return 'TAKE_PROFIT', '限价止盈触发'

    elif order_type == 'MARKET' and reduce_only:
        return 'MANUAL_CLOSE', '手动/信号平仓'

    elif order_type == 'LIQUIDATION':
        return 'LIQUIDATION', '强制清算'

    elif close_position:
        return 'CLOSE_POSITION', '完全平仓'

    else:
        return 'UNKNOWN', f'未知类型: {order_type}'

def analyze_closes(trades, order_map, orders):
    """分析平仓记录"""

    close_stats = defaultdict(list)
    close_details = []

    # 按订单分组交易
    trades_by_order = defaultdict(list)
    for trade in trades:
        order_id = str(trade['orderId'])
        trades_by_order[order_id].append(trade)

    # 分析每个订单
    for order in orders:
        order_id = str(order['orderId'])
        status = order.get('status', '')

        # 只分析已成交的平仓订单
        if status != 'FILLED':
            continue

        reduce_only = order.get('reduceOnly', False)
        close_position = order.get('closePosition', False)

        if not reduce_only and not close_position:
            continue  # 不是平仓订单

        reason_code, reason_desc = classify_close_reason(order)

        # 计算平仓信息
        order_trades = trades_by_order.get(order_id, [])
        total_qty = sum(float(t['qty']) for t in order_trades)
        avg_price = sum(float(t['price']) * float(t['qty']) for t in order_trades) / total_qty if total_qty > 0 else 0
        realized_pnl = sum(float(t['realizedPnl']) for t in order_trades)

        time_str = datetime.fromtimestamp(order['updateTime'] / 1000).strftime('%Y-%m-%d %H:%M:%S')

        close_info = {
            'time': time_str,
            'reason_code': reason_code,
            'reason_desc': reason_desc,
            'order_type': order.get('type', 'N/A'),
            'side': order.get('side', 'N/A'),
            'quantity': total_qty,
            'avg_price': avg_price,
            'stop_price': float(order.get('stopPrice', 0)),
            'realized_pnl': realized_pnl,
            'order_id': order_id,
        }

        close_stats[reason_code].append(close_info)
        close_details.append(close_info)

    return close_stats, close_details

def print_analysis(close_stats, close_details, output_json=False):
    """打印分析结果"""

    if output_json:
        result = {
            'summary': {code: len(items) for code, items in close_stats.items()},
            'details': close_details
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    total_closes = len(close_details)

    if total_closes == 0:
        print("\n❌ 没有找到平仓记录")
        return

    print("\n" + "=" * 70)
    print("📊 平仓原因统计分析")
    print("=" * 70)

    # 统计汇总
    print("\n📈 平仓方式分布:")
    print("-" * 50)

    reason_names = {
        'STOP_LOSS': '🔴 止损',
        'TAKE_PROFIT': '🟢 止盈',
        'TRAILING_STOP': '📈 移动止损',
        'MANUAL_CLOSE': '👆 手动/信号平仓',
        'LIQUIDATION': '💀 强制清算',
        'CLOSE_POSITION': '🔄 完全平仓',
        'UNKNOWN': '❓ 未知',
    }

    # 按数量排序
    sorted_stats = sorted(close_stats.items(), key=lambda x: len(x[1]), reverse=True)

    for reason_code, items in sorted_stats:
        count = len(items)
        pct = (count / total_closes) * 100
        total_pnl = sum(item['realized_pnl'] for item in items)
        avg_pnl = total_pnl / count if count > 0 else 0

        reason_name = reason_names.get(reason_code, reason_code)
        pnl_color = "+" if total_pnl >= 0 else ""

        print(f"  {reason_name:20} | {count:3} 次 ({pct:5.1f}%) | "
              f"总盈亏: {pnl_color}${total_pnl:,.2f} | 平均: {pnl_color}${avg_pnl:,.2f}")

    print("-" * 50)
    print(f"  {'总计':20} | {total_closes:3} 次")

    # 最近的平仓详情
    print("\n\n📋 最近 10 次平仓详情:")
    print("-" * 90)
    print(f"{'时间':<20} {'原因':<15} {'方向':<6} {'数量':>10} {'价格':>12} {'盈亏':>12}")
    print("-" * 90)

    recent_closes = sorted(close_details, key=lambda x: x['time'], reverse=True)[:10]

    for item in recent_closes:
        pnl = item['realized_pnl']
        pnl_str = f"+${pnl:,.2f}" if pnl >= 0 else f"-${abs(pnl):,.2f}"
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"

        reason_short = {
            'STOP_LOSS': '止损',
            'TAKE_PROFIT': '止盈',
            'TRAILING_STOP': '移动止损',
            'MANUAL_CLOSE': '手动平仓',
            'LIQUIDATION': '清算',
            'CLOSE_POSITION': '完全平仓',
            'UNKNOWN': '未知',
        }.get(item['reason_code'], item['reason_code'])

        print(f"{item['time']:<20} {reason_short:<15} {item['side']:<6} "
              f"{item['quantity']:>10.4f} ${item['avg_price']:>10,.2f} {pnl_emoji} {pnl_str:>10}")

    # 分析主要平仓原因
    print("\n\n🔍 分析结论:")
    print("-" * 70)

    if sorted_stats:
        main_reason_code, main_items = sorted_stats[0]
        main_reason_name = reason_names.get(main_reason_code, main_reason_code)
        main_pct = (len(main_items) / total_closes) * 100
        main_total_pnl = sum(item['realized_pnl'] for item in main_items)

        print(f"\n  主要平仓方式: {main_reason_name} ({main_pct:.1f}%)")

        # 根据主要原因给出分析
        if main_reason_code == 'STOP_LOSS':
            print("""
  📌 止损触发占主导，可能原因:
     1. 止损距离设置过紧 (当前默认 2%)
     2. 入场时机不佳，市场波动触发止损
     3. 市场处于高波动期，正常止损

  💡 建议:
     - 检查 configs/base.yaml 中的 sl_buffer_pct (当前: 0.1%)
     - 考虑使用 ATR 动态止损
     - 检查入场信号质量
""")
        elif main_reason_code == 'TAKE_PROFIT':
            print("""
  📌 止盈触发占主导 - 这是理想情况!
     表明策略能够成功捕捉盈利机会

  💡 建议:
     - 可以考虑适当提高止盈目标
     - 或使用移动止损锁定更多利润
""")
        elif main_reason_code == 'TRAILING_STOP':
            print("""
  📌 移动止损触发占主导
     表明策略成功锁定了部分利润

  💡 建议:
     - 检查 trailing_activation_pct (激活阈值)
     - 检查 trailing_distance_pct (跟踪距离)
     - 距离太紧会过早平仓，太松会损失利润
""")
        elif main_reason_code == 'MANUAL_CLOSE':
            print("""
  📌 手动/信号平仓占主导
     可能是 AI 信号反转或用户手动操作

  💡 建议:
     - 检查 AI 信号是否频繁反转
     - 减少 Telegram /close 手动操作
""")
        elif main_reason_code == 'LIQUIDATION':
            print("""
  ⚠️ 警告: 清算占主导 - 这是严重问题!

  💡 紧急建议:
     - 立即降低杠杆 (当前可能过高)
     - 减小仓位大小
     - 扩大止损距离
     - 检查账户保证金是否充足
""")

        # 盈亏分析
        total_pnl = sum(item['realized_pnl'] for item in close_details)
        win_count = sum(1 for item in close_details if item['realized_pnl'] > 0)
        loss_count = sum(1 for item in close_details if item['realized_pnl'] < 0)
        win_rate = (win_count / total_closes * 100) if total_closes > 0 else 0

        print(f"\n  📊 总体盈亏: {'🟢 +' if total_pnl >= 0 else '🔴 '}${total_pnl:,.2f}")
        print(f"  📊 胜率: {win_rate:.1f}% ({win_count}胜 / {loss_count}负)")

def main():
    parser = argparse.ArgumentParser(description='分析平仓原因')
    parser.add_argument('--days', type=int, default=30, help='分析最近几天 (默认: 30)')
    parser.add_argument('--symbol', type=str, default='BTCUSDT', help='交易对 (默认: BTCUSDT)')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    args = parser.parse_args()

    print("=" * 70)
    print("🔍 平仓原因分析工具")
    print("=" * 70)

    # 加载环境变量
    load_env()

    # 获取 Binance 客户端
    client = get_binance_client()
    if not client:
        sys.exit(1)

    # 获取交易历史
    result = analyze_trade_history(client, args.symbol, args.days)
    if not result:
        sys.exit(1)

    trades, order_map, orders = result

    # 分析平仓
    close_stats, close_details = analyze_closes(trades, order_map, orders)

    # 打印分析
    print_analysis(close_stats, close_details, args.json)

if __name__ == '__main__':
    main()
