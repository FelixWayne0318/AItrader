#!/usr/bin/env python3
"""
Telegram Notification Diagnostic Script for AItrader

A standalone script that tests Telegram notification functionality
by making direct HTTP requests to the Telegram Bot API.

Checks performed:
  1. Environment file loading (~/.env.aitrader)
  2. TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID presence and format
  3. Bot token validity (getMe API)
  4. Active webhook detection (getWebhookInfo API)
  5. Test message delivery (sendMessage API)

Usage:
    python3 scripts/diagnose_telegram_notify.py
"""

import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# 1. Load environment variables
# ---------------------------------------------------------------------------

def load_environment() -> bool:
    """Load environment variables from ~/.env.aitrader (or project .env)."""
    env_permanent = Path.home() / ".env.aitrader"
    env_project = Path(__file__).resolve().parent.parent / ".env"

    loaded_from = None

    # Try python-dotenv first (preferred)
    try:
        from dotenv import load_dotenv

        if env_permanent.exists():
            load_dotenv(env_permanent, override=True)
            loaded_from = str(env_permanent)
        elif env_project.exists():
            load_dotenv(env_project, override=True)
            loaded_from = str(env_project)
        else:
            load_dotenv()
            loaded_from = "default search (no explicit file found)"
    except ImportError:
        # Fallback: manual parsing if python-dotenv is not installed
        target = None
        if env_permanent.exists():
            target = env_permanent
        elif env_project.exists():
            target = env_project

        if target is None:
            print("[FAIL] No .env file found and python-dotenv is not installed.")
            print(f"       Checked: {env_permanent}")
            print(f"       Checked: {env_project}")
            return False

        with open(target) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                # Strip inline comments
                if " #" in line:
                    line = line[: line.index(" #")].strip()
                key, _, value = line.partition("=")
                value = value.strip().strip("\"'")
                os.environ[key.strip()] = value
        loaded_from = str(target)

    print("=" * 64)
    print("  AItrader - Telegram Notification Diagnostics")
    print("=" * 64)
    print()
    print(f"[INFO] Environment loaded from: {loaded_from}")
    return True


# ---------------------------------------------------------------------------
# 2. Validate credentials
# ---------------------------------------------------------------------------

def check_credentials() -> tuple:
    """Check that TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set.

    Returns (token, chat_id) or (None, None) on failure.
    """
    print()
    print("-" * 64)
    print("Step 1: Check credentials")
    print("-" * 64)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    # --- Token ---
    if not token:
        print("[FAIL] TELEGRAM_BOT_TOKEN is not set or empty.")
        print("       Add it to ~/.env.aitrader:")
        print("       TELEGRAM_BOT_TOKEN=123456:ABC-DEF...")
        return None, None

    # Mask the token for display: show first 6 and last 4 chars
    if len(token) > 12:
        masked = token[:6] + "..." + token[-4:]
    else:
        masked = token[:3] + "***"
    print(f"[PASS] TELEGRAM_BOT_TOKEN found (length={len(token)}, preview={masked})")

    # Basic format check: should contain a colon
    if ":" not in token:
        print("[WARN] Token format looks unusual (no ':' found). Typical format: 123456789:ABCDEF...")

    # --- Chat ID ---
    if not chat_id:
        print("[FAIL] TELEGRAM_CHAT_ID is not set or empty.")
        print("       Add it to ~/.env.aitrader:")
        print("       TELEGRAM_CHAT_ID=123456789")
        return None, None

    print(f"[PASS] TELEGRAM_CHAT_ID found (value={chat_id})")

    # Check if chat_id looks numeric (can be negative for groups)
    stripped = chat_id.lstrip("-")
    if not stripped.isdigit():
        print(f"[WARN] TELEGRAM_CHAT_ID '{chat_id}' does not look numeric. "
              "Personal IDs are positive integers; group IDs are negative.")

    return token, chat_id


# ---------------------------------------------------------------------------
# 3. Validate bot token via getMe
# ---------------------------------------------------------------------------

def check_bot_identity(token: str) -> bool:
    """Call getMe to verify the bot token is valid."""
    import requests

    print()
    print("-" * 64)
    print("Step 2: Verify bot token (getMe)")
    print("-" * 64)

    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        resp = requests.get(url, timeout=15)
    except requests.exceptions.ConnectionError as exc:
        print(f"[FAIL] Connection error: {exc}")
        print("       Cannot reach api.telegram.org. Check network / DNS / firewall.")
        return False
    except requests.exceptions.Timeout:
        print("[FAIL] Request timed out (15s). Network may be slow or blocked.")
        return False
    except Exception as exc:
        print(f"[FAIL] Unexpected error: {exc}")
        return False

    print(f"       HTTP status: {resp.status_code}")
    body = resp.json()
    print(f"       Response ok: {body.get('ok')}")

    if body.get("ok"):
        result = body["result"]
        print(f"[PASS] Bot verified:")
        print(f"       id:         {result.get('id')}")
        print(f"       username:   @{result.get('username', 'N/A')}")
        print(f"       first_name: {result.get('first_name', 'N/A')}")
        print(f"       can_join_groups:    {result.get('can_join_groups', 'N/A')}")
        print(f"       can_read_all_msgs:  {result.get('can_read_all_group_messages', 'N/A')}")
        return True
    else:
        print(f"[FAIL] Bot token is invalid or revoked.")
        print(f"       API error: {body.get('description', 'unknown')}")
        print("       Generate a new token via @BotFather on Telegram.")
        return False


# ---------------------------------------------------------------------------
# 4. Check for active webhook
# ---------------------------------------------------------------------------

def check_webhook(token: str) -> bool:
    """Check if there is an active webhook (which blocks polling / getUpdates)."""
    import requests

    print()
    print("-" * 64)
    print("Step 3: Check for active webhook (getWebhookInfo)")
    print("-" * 64)

    url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    try:
        resp = requests.get(url, timeout=15)
    except Exception as exc:
        print(f"[FAIL] Request failed: {exc}")
        return False

    print(f"       HTTP status: {resp.status_code}")
    body = resp.json()

    if not body.get("ok"):
        print(f"[FAIL] API error: {body.get('description', 'unknown')}")
        return False

    result = body["result"]
    webhook_url = result.get("url", "")
    pending = result.get("pending_update_count", 0)
    last_error = result.get("last_error_message", "")
    last_error_date = result.get("last_error_date", "")

    if webhook_url:
        print(f"[WARN] Active webhook detected!")
        print(f"       Webhook URL: {webhook_url}")
        print(f"       Pending updates: {pending}")
        if last_error:
            print(f"       Last error: {last_error} (date: {last_error_date})")
        print()
        print("       An active webhook prevents getUpdates (polling) from working.")
        print("       To remove it, run:")
        print(f"         curl \"https://api.telegram.org/bot<TOKEN>/deleteWebhook\"")
        print("       Or the bot should call deleteWebhook on startup.")
        return True  # Not a hard failure, but worth noting
    else:
        print(f"[PASS] No active webhook. Polling mode is clear.")
        if pending:
            print(f"       Pending updates: {pending}")
        return True


# ---------------------------------------------------------------------------
# 5. Send a test message
# ---------------------------------------------------------------------------

def send_test_message(token: str, chat_id: str) -> bool:
    """Send a test message via the Telegram Bot API (direct HTTP)."""
    import requests
    from datetime import datetime, timezone

    print()
    print("-" * 64)
    print("Step 4: Send test message (sendMessage)")
    print("-" * 64)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    message = (
        f"[AItrader Diagnostic]\n"
        f"Telegram notification test.\n"
        f"Timestamp: {timestamp}\n"
        f"Status: OK"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
    }

    print(f"       Target chat_id: {chat_id}")
    print(f"       Message length: {len(message)} chars")

    try:
        resp = requests.post(url, json=payload, timeout=15)
    except requests.exceptions.ConnectionError as exc:
        print(f"[FAIL] Connection error: {exc}")
        return False
    except requests.exceptions.Timeout:
        print("[FAIL] Request timed out (15s).")
        return False
    except Exception as exc:
        print(f"[FAIL] Unexpected error: {exc}")
        return False

    print(f"       HTTP status: {resp.status_code}")
    body = resp.json()
    print(f"       Response ok: {body.get('ok')}")

    if body.get("ok"):
        result = body["result"]
        msg_id = result.get("message_id", "N/A")
        chat_info = result.get("chat", {})
        print(f"[PASS] Message sent successfully!")
        print(f"       message_id: {msg_id}")
        print(f"       chat type:  {chat_info.get('type', 'N/A')}")
        if chat_info.get("username"):
            print(f"       chat user:  @{chat_info['username']}")
        elif chat_info.get("title"):
            print(f"       chat title: {chat_info['title']}")
        elif chat_info.get("first_name"):
            print(f"       chat user:  {chat_info['first_name']}")
        return True
    else:
        desc = body.get("description", "unknown error")
        error_code = body.get("error_code", "N/A")
        print(f"[FAIL] Message delivery failed.")
        print(f"       Error code: {error_code}")
        print(f"       Description: {desc}")
        print()

        # Provide targeted advice based on common errors
        if "chat not found" in desc.lower():
            print("       Likely cause: The TELEGRAM_CHAT_ID is incorrect, or the bot")
            print("       has never received a message from this chat.")
            print("       Fix: Send /start to the bot first, then use @userinfobot")
            print("       or @RawDataBot to find your numeric chat ID.")
        elif "bot was blocked" in desc.lower():
            print("       Likely cause: You blocked the bot on Telegram.")
            print("       Fix: Unblock the bot and send /start again.")
        elif "not enough rights" in desc.lower():
            print("       Likely cause: Bot lacks permission to send messages in this group.")
            print("       Fix: Make the bot an admin, or check group permissions.")
        elif "unauthorized" in desc.lower() or error_code == 401:
            print("       Likely cause: Bot token is invalid or revoked.")
            print("       Fix: Generate a new token via @BotFather.")

        return False


# ---------------------------------------------------------------------------
# 6. Bonus: test Markdown mode (same as production uses)
# ---------------------------------------------------------------------------

def send_test_markdown(token: str, chat_id: str) -> bool:
    """Send a test message with Markdown formatting (mirrors production behavior)."""
    import requests

    print()
    print("-" * 64)
    print("Step 5: Send Markdown-formatted message (production mode)")
    print("-" * 64)

    message = (
        "*AItrader Diagnostic*\n"
        "Markdown formatting test.\n"
        "`parse_mode = Markdown`\n"
        "If you see this with bold and monospace, Markdown works."
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
    except Exception as exc:
        print(f"[FAIL] Request failed: {exc}")
        return False

    body = resp.json()
    print(f"       HTTP status: {resp.status_code}")
    print(f"       Response ok: {body.get('ok')}")

    if body.get("ok"):
        print("[PASS] Markdown message sent successfully.")
        return True
    else:
        desc = body.get("description", "unknown error")
        print(f"[WARN] Markdown send failed: {desc}")
        if "parse" in desc.lower():
            print("       This may cause issues in production. The bot falls back to")
            print("       plain text on parse errors, but check message formatting.")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run all diagnostic checks. Returns 0 on full success, 1 on any failure."""
    if not load_environment():
        return 1

    token, chat_id = check_credentials()
    if token is None or chat_id is None:
        print()
        print("=" * 64)
        print("  RESULT: FAIL - Missing credentials. Cannot proceed.")
        print("=" * 64)
        return 1

    results = {}

    # Check bot identity
    results["getMe"] = check_bot_identity(token)
    if not results["getMe"]:
        print()
        print("=" * 64)
        print("  RESULT: FAIL - Bot token is invalid. Fix the token first.")
        print("=" * 64)
        return 1

    # Check webhook
    results["webhook"] = check_webhook(token)

    # Send plain text test message
    results["sendMessage"] = send_test_message(token, chat_id)

    # Send Markdown test message
    results["markdown"] = send_test_markdown(token, chat_id)

    # Summary
    print()
    print("=" * 64)
    print("  SUMMARY")
    print("=" * 64)
    all_pass = True
    for check, passed in results.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {check}")

    print()
    if all_pass:
        print("  RESULT: ALL CHECKS PASSED")
        print("  Telegram notifications are working correctly.")
    else:
        print("  RESULT: SOME CHECKS FAILED")
        print("  Review the details above for troubleshooting steps.")
    print("=" * 64)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
