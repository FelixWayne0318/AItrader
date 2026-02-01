#!/usr/bin/env python3
"""
检查最近被风控阻止的信号

分析日志和信号历史，找出：
1. AI 原本发出的信号（LONG/SHORT）
2. 是否因为 S/R 风控被阻止
3. 阻止时的价格和市场情况

用法:
    python3 scripts/check_blocked_signals.py
    python3 scripts/check_blocked_signals.py --log /path/to/journal.log
"""

import os
import sys
import json
import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path

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

def parse_journal_logs(log_content: str) -> list:
    """解析 journalctl 日志，找出被阻止的信号"""
    blocked_signals = []

    # 匹配被阻止的信号
    # 格式: ⚠️ LONG blocked: ... 或 ⚠️ SHORT blocked: ...
    block_pattern = re.compile(
        r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})?.*?'
        r'⚠️\s*(LONG|SHORT)\s+blocked:\s*(.+?)(?:\n|$)',
        re.IGNORECASE
    )

    # 也匹配日志中的 Blocked: 记录
    blocked_pattern = re.compile(
        r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})?.*?'
        r'Blocked:\s*(LONG|SHORT)\s+blocked:\s*(.+?)(?:\n|$)',
        re.IGNORECASE
    )

    for match in block_pattern.finditer(log_content):
        timestamp = match.group(1) or "Unknown"
        direction = match.group(2).upper()
        reason = match.group(3).strip()
        blocked_signals.append({
            'timestamp': timestamp,
            'original_signal': direction,
            'blocked_to': 'HOLD',
            'reason': reason,
        })

    return blocked_signals

def analyze_signal_history(logs_dir: Path) -> list:
    """分析信号历史文件"""
    blocked = []

    # 检查 signal_history.json
    signal_history_file = logs_dir / "signal_history.json"
    if signal_history_file.exists():
        try:
            with open(signal_history_file) as f:
                history = json.load(f)

            for entry in history:
                reason = entry.get('reason', '')
                if 'Blocked:' in reason:
                    blocked.append({
                        'timestamp': entry.get('timestamp', 'Unknown'),
                        'signal': entry.get('signal', 'HOLD'),
                        'reason': reason,
                        'confidence': entry.get('confidence', 'N/A'),
                    })
        except Exception as e:
            print(f"⚠️ 读取 signal_history.json 失败: {e}")

    return blocked

def get_recent_journal_logs(hours: int = 24) -> str:
    """获取最近的 journalctl 日志"""
    import subprocess

    try:
        # 获取最近 N 小时的日志
        result = subprocess.run(
            ['journalctl', '-u', 'nautilus-trader', '--no-hostname',
             '--since', f'{hours} hours ago', '--no-pager'],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        print("⚠️ journalctl 超时")
        return ""
    except FileNotFoundError:
        print("⚠️ journalctl 不可用（可能不在服务器上）")
        return ""
    except Exception as e:
        print(f"⚠️ 获取日志失败: {e}")
        return ""

def analyze_price_movement(hours: int = 24) -> dict:
    """分析最近的价格走势"""
    import requests

    try:
        # 获取最近的 K 线数据
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(hours=hours)).timestamp() * 1000)

        url = "https://fapi.binance.com/fapi/v1/klines"
        params = {
            'symbol': 'BTCUSDT',
            'interval': '1h',
            'startTime': start_time,
            'endTime': end_time,
            'limit': hours + 1
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        klines = response.json()

        if not klines:
            return {}

        # 计算价格变化
        first_close = float(klines[0][4])
        last_close = float(klines[-1][4])
        high = max(float(k[2]) for k in klines)
        low = min(float(k[3]) for k in klines)

        change_pct = (last_close - first_close) / first_close * 100

        return {
            'start_price': first_close,
            'end_price': last_close,
            'high': high,
            'low': low,
            'change_pct': change_pct,
            'hours': hours,
        }
    except Exception as e:
        print(f"⚠️ 获取价格数据失败: {e}")
        return {}

def check_should_have_shorted(price_data: dict, blocked_signals: list) -> list:
    """分析是否应该做空但被阻止"""
    missed_opportunities = []

    if not price_data:
        return missed_opportunities

    change_pct = price_data.get('change_pct', 0)

    # 如果价格下跌超过 2%，检查是否有 SHORT 被阻止
    if change_pct < -2:
        for signal in blocked_signals:
            if signal.get('original_signal') == 'SHORT' or 'SHORT blocked' in signal.get('reason', ''):
                missed_opportunities.append({
                    **signal,
                    'market_move': f"价格下跌 {abs(change_pct):.2f}%",
                    'potential_profit': f"可能错过 {abs(change_pct):.1f}% 盈利",
                })

    return missed_opportunities

def main():
    parser = argparse.ArgumentParser(description='检查被风控阻止的信号')
    parser.add_argument('--hours', type=int, default=48, help='分析最近几小时 (默认: 48)')
    parser.add_argument('--log', type=str, help='指定日志文件路径')
    args = parser.parse_args()

    print("=" * 70)
    print("🔍 S/R 风控阻止信号检查")
    print("=" * 70)

    load_env()

    # 1. 获取价格走势
    print(f"\n📊 分析最近 {args.hours} 小时价格走势...")
    price_data = analyze_price_movement(args.hours)

    if price_data:
        change = price_data['change_pct']
        direction = "📈 上涨" if change > 0 else "📉 下跌"
        print(f"\n{direction} {abs(change):.2f}%")
        print(f"  起始: ${price_data['start_price']:,.2f}")
        print(f"  当前: ${price_data['end_price']:,.2f}")
        print(f"  最高: ${price_data['high']:,.2f}")
        print(f"  最低: ${price_data['low']:,.2f}")

    # 2. 获取日志
    print(f"\n📋 获取最近 {args.hours} 小时的日志...")

    if args.log and Path(args.log).exists():
        with open(args.log) as f:
            log_content = f.read()
    else:
        log_content = get_recent_journal_logs(args.hours)

    # 3. 解析被阻止的信号
    blocked_signals = parse_journal_logs(log_content)

    # 4. 检查信号历史文件
    logs_dir = Path(__file__).parent.parent / "logs"
    history_blocked = analyze_signal_history(logs_dir)

    print("\n" + "=" * 70)
    print("📊 被阻止的信号统计")
    print("=" * 70)

    if blocked_signals:
        print(f"\n从日志中发现 {len(blocked_signals)} 个被阻止的信号:")
        for i, sig in enumerate(blocked_signals[-10:], 1):  # 最近 10 个
            print(f"\n  {i}. [{sig['timestamp']}]")
            print(f"     原信号: {sig['original_signal']} → 被改为: HOLD")
            print(f"     原因: {sig['reason']}")
    else:
        print("\n✅ 日志中未发现被阻止的信号")

    if history_blocked:
        print(f"\n从信号历史中发现 {len(history_blocked)} 个被阻止的记录:")
        for i, sig in enumerate(history_blocked[-10:], 1):
            print(f"\n  {i}. [{sig['timestamp']}]")
            print(f"     信号: {sig['signal']}, 信心: {sig['confidence']}")
            print(f"     原因: {sig['reason'][:100]}...")

    # 5. 分析错过的机会
    print("\n" + "=" * 70)
    print("💰 错过的做空机会分析")
    print("=" * 70)

    all_blocked = blocked_signals + [
        {'original_signal': 'SHORT' if 'SHORT blocked' in b.get('reason', '') else 'LONG',
         'reason': b.get('reason', ''),
         'timestamp': b.get('timestamp', '')}
        for b in history_blocked
    ]

    missed = check_should_have_shorted(price_data, all_blocked)

    if missed:
        print(f"\n⚠️ 发现 {len(missed)} 个可能错过的做空机会:")
        for i, m in enumerate(missed, 1):
            print(f"\n  {i}. [{m.get('timestamp', 'N/A')}]")
            print(f"     {m.get('market_move', 'N/A')}")
            print(f"     {m.get('potential_profit', 'N/A')}")
            print(f"     阻止原因: {m.get('reason', 'N/A')[:80]}...")
    else:
        if price_data.get('change_pct', 0) < -2:
            print(f"\n⚠️ 价格下跌了 {abs(price_data['change_pct']):.2f}%，但未发现被阻止的 SHORT 信号")
            print("   可能原因:")
            print("   1. AI 本身判断为 HOLD，不是因为风控")
            print("   2. 日志记录不完整")
            print("   3. 服务当时未运行")
        else:
            print("\n✅ 价格未大幅下跌，无明显错过的做空机会")

    # 6. 建议
    print("\n" + "=" * 70)
    print("💡 建议")
    print("=" * 70)

    if missed or (price_data.get('change_pct', 0) < -3):
        print("""
  ⚠️ 15 分钟 S/R 风控可能过于敏感:

  问题: 15 分钟支撑位在大跌时不断被突破，
        但风控仍然阻止做空（因为价格接近支撑）

  解决方案:
  1. 禁用 S/R 硬风控 (推荐测试)
  2. 改用更高周期的 S/R (4H/1D)
  3. 只在 Order Wall 存在时才阻止

  禁用命令:
  在 agents/multi_agent_analyzer.py 中注释掉 _evaluate_risk 的风控逻辑
        """)
    else:
        print("\n  当前风控表现正常，暂无需调整")

if __name__ == '__main__':
    main()
