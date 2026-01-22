#!/usr/bin/env python
"""
Debug script to check Telegram configuration loading
"""
import os
import sys
import yaml

# Add project directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def load_env():
    """Load environment variables from .env"""
    env_file = '.env'
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    # Remove inline comments
                    if '#' in line:
                        line = line[:line.index('#')].strip()
                    key, value = line.split('=', 1)
                    value = value.strip().strip('"').strip("'")
                    os.environ[key] = value

def main():
    # Load .env
    load_env()
    
    # Load YAML config
    with open('configs/strategy_config.yaml') as f:
        yaml_config = yaml.safe_load(f)
    
    strategy_cfg = yaml_config.get('strategy', {})
    
    print("=" * 60)
    print("Telegram Configuration Diagnostic")
    print("=" * 60)
    print()
    
    print("📄 YAML Config (strategy):")
    print(f"  enable_telegram: {strategy_cfg.get('enable_telegram', 'NOT FOUND')}")
    print(f"  telegram_notify_signals: {strategy_cfg.get('telegram_notify_signals', 'NOT FOUND')}")
    print(f"  telegram_notify_fills: {strategy_cfg.get('telegram_notify_fills', 'NOT FOUND')}")
    print(f"  telegram_notify_positions: {strategy_cfg.get('telegram_notify_positions', 'NOT FOUND')}")
    print(f"  telegram_notify_errors: {strategy_cfg.get('telegram_notify_errors', 'NOT FOUND')}")
    print()
    
    print("🔐 Environment Variables:")
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
    # Only show status, not actual token content (security)
    print(f"  TELEGRAM_BOT_TOKEN: {'✅ Set (' + str(len(bot_token)) + ' chars)' if bot_token else '❌ NOT SET'}")
    print(f"  TELEGRAM_CHAT_ID: {'✅ Set (' + str(len(chat_id)) + ' chars)' if chat_id else '❌ NOT SET'}")
    print()

    print("🔍 What main_live.py will load:")
    print(f"  enable_telegram: {strategy_cfg.get('enable_telegram', False)}")
    print(f"  telegram_bot_token: {'[SET]' if bot_token else 'EMPTY'}")
    print(f"  telegram_chat_id: {'[SET]' if chat_id else 'EMPTY'}")
    print()
    
    if strategy_cfg.get('enable_telegram'):
        if bot_token and chat_id:
            print("✅ Configuration looks good!")
        else:
            print("❌ enable_telegram=true but credentials missing!")
    else:
        print("⚠️  enable_telegram=false - Telegram notifications disabled")
    print()

if __name__ == '__main__':
    main()

