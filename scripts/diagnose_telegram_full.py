#!/usr/bin/env python3
"""
Telegram 全面诊断脚本 v2.0 (v3.13)

诊断内容:
1. 环境变量和配置检查
2. Bot API 连接测试
3. 心跳消息内容验证 (是否包含持仓/SL/TP/S/R Zone)
4. 开仓/平仓消息逻辑验证 (是否只发一条消息)
5. 数据真实性验证
6. 新增命令测试 (/daily, /weekly)

运行方式:
    cd /home/linuxuser/nautilus_AItrader
    source venv/bin/activate
    python3 scripts/diagnose_telegram_full.py
"""

import os
import sys
import re
import ast
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def print_header(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(name: str, status: bool, detail: str = ""):
    icon = "✅" if status else "❌"
    print(f"{icon} {name}")
    if detail:
        for line in detail.split('\n'):
            print(f"   └─ {line}")


def print_warning(msg: str):
    print(f"⚠️  {msg}")


def print_info(msg: str):
    print(f"ℹ️  {msg}")


def load_env() -> Tuple[str, str]:
    """加载环境变量"""
    env_file = Path.home() / ".env.aitrader"
    if not env_file.exists():
        env_file = project_root / ".env"

    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value

    return os.environ.get('TELEGRAM_BOT_TOKEN', ''), os.environ.get('TELEGRAM_CHAT_ID', '')


def check_heartbeat_message_content():
    """检查心跳消息是否包含所有必要字段 (问题1)"""
    print_header("3. 心跳消息内容验证 (问题1)")

    # 读取 deepseek_strategy.py 中 format_heartbeat_message 调用
    strategy_file = project_root / "strategy" / "deepseek_strategy.py"

    required_fields = {
        # 基础字段
        'signal': '信号方向',
        'confidence': '信心等级',
        'price': '当前价格',
        'rsi': 'RSI 指标',
        # 持仓信息
        'position_side': '持仓方向',
        'entry_price': '入场价格',
        'position_size': '持仓数量',
        'position_pnl_pct': '持仓盈亏比例',
        # 止盈止损 (v4.2)
        'sl_price': '止损价格',
        'tp_price': '止盈价格',
        # S/R Zone (v3.8)
        'sr_zone': 'S/R Zone 数据',
        # 其他高级数据
        'order_flow': '订单流数据 (v3.6)',
        'derivatives': '衍生品数据 (v3.6)',
        'order_book': '订单簿数据 (v3.7)',
        'signal_status': '信号执行状态 (v4.1)',
    }

    try:
        content = strategy_file.read_text()

        # 查找 format_heartbeat_message 调用
        pattern = r'format_heartbeat_message\(\{([^}]+(?:\{[^}]*\}[^}]*)*)\}\)'
        match = re.search(pattern, content, re.DOTALL)

        if match:
            heartbeat_call = match.group(1)

            print("\n  心跳消息包含的字段:")
            print("  " + "-" * 50)

            found_fields = []
            missing_fields = []

            for field, desc in required_fields.items():
                # 检查字段是否在调用中
                field_pattern = rf"'{field}':|{field}:"
                if re.search(field_pattern, heartbeat_call):
                    found_fields.append(field)
                    print(f"  ✅ {field}: {desc}")
                else:
                    missing_fields.append(field)
                    print(f"  ❌ {field}: {desc} [缺失]")

            print("\n  " + "-" * 50)
            print(f"  找到: {len(found_fields)}/{len(required_fields)} 个字段")

            if missing_fields:
                print_warning(f"缺失字段: {', '.join(missing_fields)}")
            else:
                print_result("心跳消息字段完整", True, "包含持仓、SL/TP、S/R Zone 所有必要字段")

        else:
            print_result("format_heartbeat_message 调用", False, "未找到调用代码")

    except Exception as e:
        print_result("心跳消息分析", False, str(e))


def check_position_message_logic():
    """检查开仓/平仓是否只发一条消息 (问题2)"""
    print_header("4. 开仓/平仓消息逻辑验证 (问题2)")

    strategy_file = project_root / "strategy" / "deepseek_strategy.py"

    try:
        content = strategy_file.read_text()

        # 检查 on_position_opened 中的消息发送
        print("\n[4.1] 检查 on_position_opened 消息发送...")

        # 查找 on_position_opened 方法
        opened_pattern = r'def on_position_opened\(self.*?\n(.*?)(?=\n    def |\nclass |\Z)'
        opened_match = re.search(opened_pattern, content, re.DOTALL)

        if opened_match:
            opened_code = opened_match.group(1)

            # 统计消息发送调用
            send_calls = re.findall(r'send_message_sync\(', opened_code)
            send_count = len(send_calls)

            # 检查是否有统一消息注释
            has_unified_comment = 'unified' in opened_code.lower() or '统一' in opened_code

            print(f"  消息发送次数: {send_count}")
            print(f"  统一消息模式: {'是' if has_unified_comment else '否'}")

            if send_count == 1:
                print_result("on_position_opened 消息", True, "只发送 1 条消息 (format_trade_execution)")
            else:
                print_result("on_position_opened 消息", False, f"发送 {send_count} 条消息")

            # 检查使用的格式化方法
            if 'format_trade_execution' in opened_code:
                print("  ✅ 使用 format_trade_execution() - 统一开仓通知")
            if 'format_order_fill' in opened_code:
                print("  ⚠️ 使用 format_order_fill() - 可能有额外消息")
            if 'format_trade_signal' in opened_code:
                print("  ⚠️ 使用 format_trade_signal() - 可能有额外消息")

        # 检查 on_position_closed 中的消息发送
        print("\n[4.2] 检查 on_position_closed 消息发送...")

        closed_pattern = r'def on_position_closed\(self.*?\n(.*?)(?=\n    def |\nclass |\Z)'
        closed_match = re.search(closed_pattern, content, re.DOTALL)

        if closed_match:
            closed_code = closed_match.group(1)

            send_calls = re.findall(r'send_message_sync\(', closed_code)
            send_count = len(send_calls)

            print(f"  消息发送次数: {send_count}")

            if send_count == 1:
                print_result("on_position_closed 消息", True, "只发送 1 条消息 (format_position_update)")
            else:
                print_result("on_position_closed 消息", False, f"发送 {send_count} 条消息")

            if 'format_position_update' in closed_code:
                print("  ✅ 使用 format_position_update() - 统一平仓通知")

        # 检查 on_order_filled 是否被禁用
        print("\n[4.3] 检查 on_order_filled 消息发送...")

        filled_pattern = r'def on_order_filled\(self.*?\n(.*?)(?=\n    def |\nclass |\Z)'
        filled_match = re.search(filled_pattern, content, re.DOTALL)

        if filled_match:
            filled_code = filled_match.group(1)
            send_calls = re.findall(r'send_message_sync\(', filled_code)
            send_count = len(send_calls)

            if send_count == 0:
                print_result("on_order_filled 消息", True, "不发送额外消息 (已移至 on_position_opened)")
            else:
                print_result("on_order_filled 消息", False, f"发送 {send_count} 条消息 (可能重复)")

    except Exception as e:
        print_result("消息逻辑分析", False, str(e))


def check_data_authenticity():
    """检查数据是否真实 (问题3)"""
    print_header("5. 数据真实性验证 (问题3)")

    strategy_file = project_root / "strategy" / "deepseek_strategy.py"

    try:
        content = strategy_file.read_text()

        print("\n[5.1] 检查数据来源...")

        # 数据来源检查点
        data_sources = {
            '_cached_current_price': ('价格数据', 'on_bar 事件更新的线程安全缓存'),
            '_get_current_position_data': ('持仓数据', 'NautilusTrader 缓存'),
            'binance_account.get_balance': ('余额数据', 'Binance API 实时查询'),
            'trailing_stop_state': ('SL/TP 数据', '实际订单状态'),
            'latest_sr_zones_data': ('S/R Zone', '基于历史 K 线计算'),
            'latest_order_flow_data': ('订单流数据', 'Binance K 线 taker_buy_volume'),
            'latest_derivatives_data': ('衍生品数据', 'Coinalyze API'),
        }

        for source, (name, desc) in data_sources.items():
            if source in content:
                print(f"  ✅ {name}: {desc}")
            else:
                print(f"  ❓ {name}: 未找到引用")

        # 检查是否有硬编码数据
        print("\n[5.2] 检查硬编码数据...")

        # 在心跳相关代码中查找硬编码
        heartbeat_section = re.search(
            r'def _send_heartbeat.*?(?=\n    def |\Z)',
            content, re.DOTALL
        )

        if heartbeat_section:
            hb_code = heartbeat_section.group(0)

            # 检查是否有测试数据
            test_patterns = [
                (r"price\s*=\s*\d+\.?\d*\s*#", "硬编码价格"),
                (r"rsi\s*=\s*\d+\.?\d*\s*#", "硬编码 RSI"),
                (r"position_side\s*=\s*['\"](?:LONG|SHORT)['\"]", "硬编码持仓方向"),
            ]

            hardcoded_found = False
            for pattern, desc in test_patterns:
                if re.search(pattern, hb_code):
                    print(f"  ⚠️ 发现 {desc}")
                    hardcoded_found = True

            if not hardcoded_found:
                print("  ✅ 未发现硬编码数据")

        # 测试真实 API 调用
        print("\n[5.3] 测试 Binance API 真实数据...")

        try:
            from utils.binance_account import BinanceAccountUtils

            binance = BinanceAccountUtils()
            balance = binance.get_balance()

            if balance and balance.get('total_balance', 0) > 0:
                print_result("Binance 余额获取", True,
                             f"总余额: ${balance.get('total_balance', 0):,.2f} USDT")
            else:
                print_result("Binance 余额获取", False, "返回空或零")

        except Exception as e:
            print_result("Binance 余额获取", False, str(e))

    except Exception as e:
        print_result("数据真实性分析", False, str(e))


def check_new_commands():
    """检查新增命令 /daily 和 /weekly (v3.13)"""
    print_header("6. 新增命令验证 (v3.13)")

    # 检查命令处理器
    handler_file = project_root / "utils" / "telegram_command_handler.py"

    try:
        content = handler_file.read_text()

        print("\n[6.1] 检查命令注册...")

        commands = {
            'daily': '/daily 每日绩效总结',
            'weekly': '/weekly 每周绩效总结',
        }

        for cmd, desc in commands.items():
            # 检查 CommandHandler 注册
            if f'CommandHandler("{cmd}"' in content:
                print(f"  ✅ {desc} - 已注册")
            else:
                print(f"  ❌ {desc} - 未注册")

        print("\n[6.2] 检查回调映射...")

        if "'cmd_daily': 'daily_summary'" in content:
            print("  ✅ cmd_daily 回调映射存在")
        else:
            print("  ❌ cmd_daily 回调映射缺失")

        if "'cmd_weekly': 'weekly_summary'" in content:
            print("  ✅ cmd_weekly 回调映射存在")
        else:
            print("  ❌ cmd_weekly 回调映射缺失")

        # 检查策略实现
        strategy_file = project_root / "strategy" / "deepseek_strategy.py"
        strategy_content = strategy_file.read_text()

        print("\n[6.3] 检查策略实现...")

        if "def _cmd_daily_summary" in strategy_content:
            print("  ✅ _cmd_daily_summary() 方法存在")
        else:
            print("  ❌ _cmd_daily_summary() 方法缺失")

        if "def _cmd_weekly_summary" in strategy_content:
            print("  ✅ _cmd_weekly_summary() 方法存在")
        else:
            print("  ❌ _cmd_weekly_summary() 方法缺失")

        # 检查 format 方法
        bot_file = project_root / "utils" / "telegram_bot.py"
        bot_content = bot_file.read_text()

        print("\n[6.4] 检查格式化方法...")

        if "def format_daily_summary" in bot_content:
            print("  ✅ format_daily_summary() 方法存在")
        else:
            print("  ❌ format_daily_summary() 方法缺失")

        if "def format_weekly_summary" in bot_content:
            print("  ✅ format_weekly_summary() 方法存在")
        else:
            print("  ❌ format_weekly_summary() 方法缺失")

    except Exception as e:
        print_result("命令验证", False, str(e))


def check_config():
    """检查配置"""
    print_header("2. 配置检查")

    try:
        from utils.config_manager import ConfigManager
        config = ConfigManager(env='production')
        config.load()
        print_result("ConfigManager 加载", True)

        # 检查所有 telegram.notify.* 配置
        notify_config = {
            'signals': ('信号通知', True),
            'fills': ('成交通知', True),
            'positions': ('持仓通知', True),
            'errors': ('错误通知', True),
            'heartbeat': ('心跳通知', True),
            'trailing_stop': ('移动止损通知', True),
            'startup': ('启动通知', True),
            'shutdown': ('关闭通知', True),
            'daily_summary': ('每日总结', False),
            'weekly_summary': ('每周总结', False),
        }

        print("\n  Telegram 通知配置:")
        print("  " + "-" * 40)

        for key, (desc, default) in notify_config.items():
            value = config.get('telegram', 'notify', key, default=default)
            status = "✅ ON" if value else "⚪ OFF"
            print(f"  {status} {key}: {desc}")

        # 检查 summary 配置
        print("\n  定时总结配置:")
        print("  " + "-" * 40)

        auto_daily = config.get('telegram', 'summary', 'auto_daily', default=False)
        auto_weekly = config.get('telegram', 'summary', 'auto_weekly', default=False)

        print(f"  {'✅' if auto_daily else '⚪'} auto_daily: 自动每日总结")
        print(f"  {'✅' if auto_weekly else '⚪'} auto_weekly: 自动每周总结")

    except Exception as e:
        print_result("配置加载", False, str(e))


def test_bot_api(bot_token: str, chat_id: str):
    """测试 Bot API"""
    print_header("7. Bot API 连接测试")

    # getMe
    print("\n[7.1] 验证 Bot Token...")
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        resp = requests.get(url, timeout=10)
        data = resp.json()

        if data.get('ok'):
            bot_info = data.get('result', {})
            print_result("Bot Token 有效", True)
            print(f"    Username: @{bot_info.get('username', 'N/A')}")
        else:
            print_result("Bot Token 有效", False, data.get('description', 'Unknown'))
            return
    except Exception as e:
        print_result("Bot Token 验证", False, str(e))
        return

    # 发送测试消息
    print("\n[7.2] 发送综合测试消息...")
    try:
        from utils.telegram_bot import TelegramBot

        telegram_bot = TelegramBot(token=bot_token, chat_id=chat_id)

        # 测试心跳消息 (包含所有字段)
        test_heartbeat = {
            'signal': 'HOLD',
            'confidence': 'MEDIUM',
            'price': 104500.0,
            'rsi': 55.5,
            'position_side': 'LONG',
            'entry_price': 103000.0,
            'position_size': 0.01,
            'position_pnl_pct': 1.46,
            'sl_price': 101000.0,
            'tp_price': 108000.0,
            'timer_count': 999,
            'equity': 1000.0,
            'uptime_str': '2h 30m',
            'sr_zone': {
                'nearest_support': 102000.0,
                'nearest_resistance': 106000.0,
                'block_long': False,
                'block_short': False,
            },
            'order_flow': {
                'buy_ratio': 0.58,
                'cvd_trend': 'RISING',
            },
        }

        msg = telegram_bot.format_heartbeat_message(test_heartbeat)

        # 添加诊断标记
        msg = f"🔬 *诊断测试 - 心跳消息预览*\n\n" + msg

        result = telegram_bot.send_message_sync(msg)
        if result:
            print_result("心跳测试消息发送", True)
        else:
            print_result("心跳测试消息发送", False)

        # 测试 daily summary
        print("\n[7.3] 测试每日总结格式...")
        daily_data = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'total_trades': 5,
            'winning_trades': 3,
            'losing_trades': 2,
            'total_pnl': 25.50,
            'total_pnl_pct': 2.55,
            'largest_win': 15.00,
            'largest_loss': 8.00,
            'starting_equity': 1000.0,
            'ending_equity': 1025.50,
            'signals_generated': 12,
            'signals_executed': 5,
        }

        daily_msg = "🔬 *诊断测试 - 每日总结预览*\n" + telegram_bot.format_daily_summary(daily_data)
        result = telegram_bot.send_message_sync(daily_msg)
        if result:
            print_result("每日总结测试发送", True)
        else:
            print_result("每日总结测试发送", False)

    except Exception as e:
        print_result("测试消息发送", False, str(e))


def main():
    print_header("Telegram 全面诊断 v2.0 (v3.13)")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"项目: {project_root}")

    # 1. 加载环境变量
    print_header("1. 环境变量检查")
    bot_token, chat_id = load_env()

    if bot_token:
        print_result("TELEGRAM_BOT_TOKEN", True, f"长度={len(bot_token)}")
    else:
        print_result("TELEGRAM_BOT_TOKEN", False, "未设置")
        return

    if chat_id:
        print_result("TELEGRAM_CHAT_ID", True, chat_id)
    else:
        print_result("TELEGRAM_CHAT_ID", False, "未设置")
        return

    # 2. 配置检查
    check_config()

    # 3. 心跳消息内容 (问题1)
    check_heartbeat_message_content()

    # 4. 开仓/平仓消息逻辑 (问题2)
    check_position_message_logic()

    # 5. 数据真实性 (问题3)
    check_data_authenticity()

    # 6. 新增命令 (v3.13)
    check_new_commands()

    # 7. Bot API 测试
    test_bot_api(bot_token, chat_id)

    # 8. 总结
    print_header("8. 诊断总结")

    print("""
诊断完成！请检查上面的结果：

问题1 - 心跳消息内容:
  ✅ 应包含: signal, confidence, price, rsi
  ✅ 应包含: position_side, entry_price, position_size, position_pnl_pct
  ✅ 应包含: sl_price, tp_price (v4.2)
  ✅ 应包含: sr_zone (v3.8)

问题2 - 开仓/平仓消息:
  ✅ on_position_opened: 只发 1 条 (format_trade_execution)
  ✅ on_position_closed: 只发 1 条 (format_position_update)
  ✅ on_order_filled: 不发额外消息

问题3 - 数据真实性:
  ✅ 价格: _cached_current_price (on_bar 更新)
  ✅ 持仓: NautilusTrader 缓存 + Binance API
  ✅ 余额: binance_account.get_balance()
  ✅ 无硬编码测试数据

如果有 ❌ 标记的项目，需要修复对应问题。
""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
