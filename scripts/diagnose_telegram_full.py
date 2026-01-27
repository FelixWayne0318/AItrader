#!/usr/bin/env python3
"""
Telegram 全面诊断脚本 v1.0
用于诊断 Telegram 通知不工作的问题

运行方式:
    cd /home/linuxuser/nautilus_AItrader
    source venv/bin/activate
    python3 scripts/diagnose_telegram_full.py
"""

import os
import sys
import time
import requests
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def print_header(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

def print_result(name: str, status: bool, detail: str = ""):
    icon = "✅" if status else "❌"
    print(f"{icon} {name}")
    if detail:
        print(f"   └─ {detail}")

def print_warning(msg: str):
    print(f"⚠️  {msg}")

def print_info(msg: str):
    print(f"ℹ️  {msg}")

def main():
    print_header("Telegram 全面诊断 v1.0")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ========== 1. 检查环境变量 ==========
    print_header("1. 环境变量检查")

    # 加载 .env 文件
    env_file = Path.home() / ".env.aitrader"
    if not env_file.exists():
        env_file = project_root / ".env"

    if env_file.exists():
        print_result("环境文件存在", True, str(env_file))
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
    else:
        print_result("环境文件存在", False, "找不到 ~/.env.aitrader 或 .env")

    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')

    print_result("TELEGRAM_BOT_TOKEN", bool(bot_token),
                 f"长度={len(bot_token)}, 前缀={bot_token[:10]}..." if bot_token else "未设置")
    print_result("TELEGRAM_CHAT_ID", bool(chat_id), chat_id if chat_id else "未设置")

    if not bot_token or not chat_id:
        print("\n❌ 缺少必要的环境变量，无法继续诊断")
        return

    # ========== 2. 检查配置文件 ==========
    print_header("2. 配置文件检查")

    try:
        from utils.config_manager import ConfigManager
        config = ConfigManager(env='production')
        config.load()
        print_result("ConfigManager 加载", True)

        # 检查 telegram.notify.* 配置
        notify_signals = config.get('telegram', 'notify', 'signals', default=True)
        notify_fills = config.get('telegram', 'notify', 'fills', default=True)
        notify_positions = config.get('telegram', 'notify', 'positions', default=True)
        notify_errors = config.get('telegram', 'notify', 'errors', default=True)
        notify_heartbeat = config.get('telegram', 'notify', 'heartbeat', default=True)

        print(f"\n  Telegram 通知配置:")
        print(f"    signals:    {notify_signals}")
        print(f"    fills:      {notify_fills}")
        print(f"    positions:  {notify_positions}")
        print(f"    errors:     {notify_errors}")
        print(f"    heartbeat:  {notify_heartbeat}")

        if not notify_heartbeat:
            print_warning("heartbeat 配置为 False，不会发送心跳！")

    except Exception as e:
        print_result("ConfigManager 加载", False, str(e))

    # ========== 3. 测试 Telegram Bot API 直接调用 ==========
    print_header("3. Telegram Bot API 直接测试")

    # 3.1 getMe - 验证 token
    print("\n[3.1] 验证 Bot Token (getMe)...")
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        resp = requests.get(url, timeout=10)
        data = resp.json()

        if data.get('ok'):
            bot_info = data.get('result', {})
            print_result("Bot Token 有效", True)
            print(f"    Bot Username: @{bot_info.get('username', 'N/A')}")
            print(f"    Bot ID: {bot_info.get('id', 'N/A')}")
            print(f"    Can Read Messages: {bot_info.get('can_read_all_group_messages', False)}")
        else:
            print_result("Bot Token 有效", False, data.get('description', 'Unknown error'))
    except Exception as e:
        print_result("Bot Token 有效", False, str(e))

    # 3.2 getWebhookInfo - 检查 webhook 状态
    print("\n[3.2] 检查 Webhook 状态...")
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
        resp = requests.get(url, timeout=10)
        data = resp.json()

        if data.get('ok'):
            webhook_info = data.get('result', {})
            webhook_url = webhook_info.get('url', '')
            pending_count = webhook_info.get('pending_update_count', 0)

            if webhook_url:
                print_result("Webhook 状态", False, f"Webhook 已设置: {webhook_url}")
                print_warning("Webhook 与 polling 模式冲突！需要删除 webhook")
            else:
                print_result("Webhook 状态", True, "无 webhook (polling 模式兼容)")

            print(f"    Pending Updates: {pending_count}")
            if webhook_info.get('last_error_message'):
                print(f"    Last Error: {webhook_info.get('last_error_message')}")
        else:
            print_result("Webhook 状态", False, data.get('description', 'Unknown error'))
    except Exception as e:
        print_result("Webhook 状态", False, str(e))

    # 3.3 发送测试消息 (直接 requests)
    print("\n[3.3] 发送测试消息 (requests 直接调用)...")
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        test_msg = f"🔬 *诊断测试消息*\n\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n方法: requests 直接调用\n\n如果你看到这条消息，说明 Telegram API 正常工作。"

        payload = {
            'chat_id': chat_id,
            'text': test_msg,
            'parse_mode': 'Markdown'
        }

        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()

        if data.get('ok'):
            msg_id = data.get('result', {}).get('message_id', 'N/A')
            print_result("发送测试消息", True, f"message_id={msg_id}")
        else:
            error_code = data.get('error_code', 'N/A')
            error_desc = data.get('description', 'Unknown error')
            print_result("发送测试消息", False, f"Error {error_code}: {error_desc}")

            if error_code == 400 and 'chat not found' in error_desc.lower():
                print_warning(f"Chat ID {chat_id} 无效或 Bot 未加入该聊天")
                print_info("请确认: 1) Chat ID 正确  2) 已向 Bot 发送过消息  3) Bot 已加入群组(如果是群)")
    except Exception as e:
        print_result("发送测试消息", False, str(e))

    # ========== 4. 测试 TelegramBot 类 ==========
    print_header("4. TelegramBot 类测试")

    try:
        from utils.telegram_bot import TelegramBot

        telegram_bot = TelegramBot(
            token=bot_token,
            chat_id=chat_id
        )
        print_result("TelegramBot 初始化", True)

        # 测试 send_message_sync
        print("\n[4.1] 测试 send_message_sync()...")
        test_msg = f"🔬 *TelegramBot 类测试*\n\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n方法: TelegramBot.send_message_sync()\n\n如果你看到这条消息，说明 TelegramBot 类正常工作。"

        result = telegram_bot.send_message_sync(test_msg)
        if result:
            print_result("send_message_sync()", True)
        else:
            print_result("send_message_sync()", False, "返回 False 或 None")

        # 测试 format_heartbeat_message
        print("\n[4.2] 测试 format_heartbeat_message()...")
        try:
            heartbeat_data = {
                'signal': 'HOLD',
                'confidence': 'MEDIUM',
                'price': 104500.0,
                'rsi': 55.5,
                'has_position': False,
                'position_side': None,
                'position_pnl_pct': 0.0,
                'timer_count': 999,
            }
            heartbeat_msg = telegram_bot.format_heartbeat_message(heartbeat_data)
            print_result("format_heartbeat_message()", True)
            print(f"\n  预览:\n{heartbeat_msg[:300]}...")

            # 发送心跳测试消息
            print("\n[4.3] 发送心跳测试消息...")
            result = telegram_bot.send_message_sync(heartbeat_msg)
            if result:
                print_result("发送心跳测试消息", True)
            else:
                print_result("发送心跳测试消息", False)

        except AttributeError as e:
            print_result("format_heartbeat_message()", False, f"方法不存在: {e}")
        except Exception as e:
            print_result("format_heartbeat_message()", False, str(e))

    except ImportError as e:
        print_result("TelegramBot 导入", False, str(e))
    except Exception as e:
        print_result("TelegramBot 初始化", False, str(e))

    # ========== 5. 检查服务日志 ==========
    print_header("5. 服务日志检查建议")

    print("""
请运行以下命令检查服务日志中的 Telegram 相关信息:

# 查看最近的心跳日志
sudo journalctl -u nautilus-trader --no-hostname | grep -i "heartbeat" | tail -20

# 查看 Telegram 相关错误
sudo journalctl -u nautilus-trader --no-hostname | grep -i "telegram" | tail -50

# 查看最近的 on_timer 日志
sudo journalctl -u nautilus-trader --no-hostname | grep -i "on_timer\|timer" | tail -20

# 实时查看日志 (观察下一次 on_timer)
sudo journalctl -u nautilus-trader -f --no-hostname
""")

    # ========== 6. 总结 ==========
    print_header("6. 诊断总结")

    print("""
如果所有测试都通过但服务仍不发送消息，可能的原因:

1. 配置未正确加载
   - 检查 configs/base.yaml 中 telegram.notify.heartbeat 是否为 true
   - 检查 main_live.py 是否正确传递 telegram_notify_heartbeat 参数

2. 代码未正确部署
   - 确认服务器代码是最新版本: git log --oneline -3
   - 确认 __pycache__ 已清除

3. on_timer 未正确触发
   - 检查日志中 on_timer 是否每 15 分钟触发一次

4. 策略初始化问题
   - 检查 enable_telegram 是否为 True
   - 检查 telegram_bot 是否正确初始化

下一步: 运行上面的日志检查命令，查看具体错误信息。
""")

if __name__ == "__main__":
    main()
