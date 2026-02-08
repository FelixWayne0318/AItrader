#!/usr/bin/env python3
"""
Telegram System Comprehensive Diagnostic v2.0

Analyzes BOTH the Telegram command system and notification system for correctness.
Designed to run on the production server and report all issues.

Sections:
  1. Command Registry Completeness (QUERY/CONTROL/CALLBACK/PIN)
  2. Strategy Command Dispatcher Mapping (handle_telegram_command → _cmd_*)
  3. Bot Format Method Completeness (format_* methods)
  4. Format Method Mock Tests (call with mock data)
  5. SL/TP Data Flow Verification (6 notification touchpoints)
  6. Message Queue System (TelegramMessageQueue)
  7. API Connectivity (getMe, webhook, markdown)
  8. Shortcut Command Registration
  9. Markdown Safety Checks (edge cases)

Usage:
    python3 scripts/diagnose_telegram.py           # Full diagnostic
    python3 scripts/diagnose_telegram.py --quick   # Skip API tests
"""

import sys
import os
import re
import inspect
import asyncio
import traceback
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Any, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Check if python-telegram-bot is available
try:
    from telegram.ext import ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False


# ═══════════════════════════════════════════
#  Utilities
# ═══════════════════════════════════════════

class DiagResult:
    """Single diagnostic check result."""
    def __init__(self, section: str, check_id: str, desc: str, passed: bool,
                 detail: str = "", severity: str = "error"):
        self.section = section
        self.check_id = check_id
        self.desc = desc
        self.passed = passed
        self.detail = detail
        self.severity = severity  # "error", "warning", "info"


results: List[DiagResult] = []


def record(section: str, check_id: str, desc: str, passed: bool,
           detail: str = "", severity: str = "error"):
    """Record and print a check result."""
    icon = "✅" if passed else ("⚠️" if severity == "warning" else "❌")
    print(f"  {icon} [{check_id}] {desc}")
    if detail and not passed:
        for line in detail.strip().split("\n"):
            print(f"      {line}")
    results.append(DiagResult(section, check_id, desc, passed, detail, severity))


def print_section(title: str, num: int):
    print()
    print(f"{'=' * 65}")
    print(f"  Section {num}: {title}")
    print(f"{'=' * 65}")
    print()


def load_env():
    """Load environment variables from .env or ~/.env.aitrader."""
    for env_path in [PROJECT_ROOT / '.env', Path.home() / '.env.aitrader']:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        if '#' in line:
                            # Remove inline comments (but not inside values)
                            idx = line.index('#')
                            if idx > line.index('='):
                                line = line[:idx].strip()
                        key, value = line.split('=', 1)
                        value = value.strip().strip('"').strip("'")
                        os.environ.setdefault(key.strip(), value)
            return True
    return False


# ═══════════════════════════════════════════
#  Section 1: Command Registry Completeness
# ═══════════════════════════════════════════

def _parse_registries_from_source():
    """Parse command registries from source when import is unavailable."""
    handler_path = PROJECT_ROOT / "utils" / "telegram_command_handler.py"
    if not handler_path.exists():
        return None
    source = handler_path.read_text()

    # Parse QUERY_COMMANDS = { 'key': 'value', ... }
    query_cmds = dict(re.findall(r"'(\w+)':\s+'(\w+)'",
                                  _extract_dict_block(source, "QUERY_COMMANDS")))
    query_args_block = _extract_dict_block(source, "QUERY_COMMANDS_WITH_ARGS")
    query_args_keys = set(re.findall(r"'(\w+)':\s*\(", query_args_block))
    control_block = _extract_set_block(source, "CONTROL_COMMANDS")
    control_set = set(re.findall(r"'(\w+)'", control_block))
    control_args_block = _extract_dict_block(source, "CONTROL_COMMANDS_WITH_ARGS")
    # Match 'key': ('value', ...) or 'key': ('value', lambda ...)
    control_args_keys = set(re.findall(r"'(\w+)':\s*\(", control_args_block))
    if not control_args_keys:
        # Broader pattern: match any 'key': at start of line
        control_args_keys = set(re.findall(r"^\s*'(\w+)':", control_args_block, re.MULTILINE))
    callback_map = dict(re.findall(r"'(\w+)':\s+'(\w+)'",
                                    _extract_dict_block(source, "CALLBACK_MAP")))
    pin_block = _extract_dict_block(source, "PIN_MESSAGES")
    pin_keys = set(re.findall(r"'(\w+)':\s+", pin_block))

    return {
        'QUERY_COMMANDS': query_cmds,
        'QUERY_COMMANDS_WITH_ARGS': query_args_keys,
        'CONTROL_COMMANDS': control_set,
        'CONTROL_COMMANDS_WITH_ARGS': {k: k for k in control_args_keys},
        'CALLBACK_MAP': callback_map,
        'PIN_MESSAGES': pin_keys,
    }


def _extract_dict_block(source: str, var_name: str) -> str:
    """Extract a dict/set assignment block from source, handling nested braces."""
    pattern = rf'^{var_name}\s*=\s*\{{'
    m = re.search(pattern, source, re.MULTILINE)
    if not m:
        return ""
    start = m.end()
    depth = 1
    i = start
    while i < len(source) and depth > 0:
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
        i += 1
    return source[start:i - 1]


def _extract_set_block(source: str, var_name: str) -> str:
    """Extract a set assignment block from source."""
    return _extract_dict_block(source, var_name)


def check_command_registry():
    print_section("Command Registry Completeness", 1)

    QUERY_COMMANDS = None
    QUERY_COMMANDS_WITH_ARGS = None
    CONTROL_COMMANDS = None
    CONTROL_COMMANDS_WITH_ARGS = None
    CALLBACK_MAP = None
    PIN_MESSAGES = None

    if TELEGRAM_AVAILABLE:
        try:
            from utils.telegram_command_handler import (
                QUERY_COMMANDS, QUERY_COMMANDS_WITH_ARGS,
                CONTROL_COMMANDS, CONTROL_COMMANDS_WITH_ARGS,
                CALLBACK_MAP, PIN_MESSAGES,
            )
            record("registry", "R1.0", "Import command registries (live)", True)
        except ImportError as e:
            record("registry", "R1.0", "Import command registries", False, str(e))

    if QUERY_COMMANDS is None:
        # Fallback: parse from source
        parsed = _parse_registries_from_source()
        if parsed is None:
            record("registry", "R1.0", "Parse command registries from source", False,
                   "telegram_command_handler.py not found")
            return
        QUERY_COMMANDS = parsed['QUERY_COMMANDS']
        QUERY_COMMANDS_WITH_ARGS = parsed['QUERY_COMMANDS_WITH_ARGS']
        CONTROL_COMMANDS = parsed['CONTROL_COMMANDS']
        CONTROL_COMMANDS_WITH_ARGS = parsed['CONTROL_COMMANDS_WITH_ARGS']
        CALLBACK_MAP = parsed['CALLBACK_MAP']
        PIN_MESSAGES = parsed['PIN_MESSAGES']
        if not TELEGRAM_AVAILABLE:
            record("registry", "R1.0", "Parse command registries from source (telegram not installed)", True)

    # R1.1: Expected query commands
    expected_query = {
        'status', 'position', 'orders', 'history', 'risk',
        'daily', 'weekly', 'balance', 'analyze', 'config',
        'version', 'profit',
    }
    missing_query = expected_query - set(QUERY_COMMANDS.keys())
    extra_query = set(QUERY_COMMANDS.keys()) - expected_query
    record("registry", "R1.1", f"QUERY_COMMANDS ({len(QUERY_COMMANDS)} registered)",
           len(missing_query) == 0,
           f"Missing: {missing_query}" if missing_query else
           f"Extra: {extra_query}" if extra_query else "")

    # R1.2: Expected query commands with args
    expected_query_args = {'logs'}
    qa_keys = set(QUERY_COMMANDS_WITH_ARGS.keys()) if isinstance(QUERY_COMMANDS_WITH_ARGS, dict) else set(QUERY_COMMANDS_WITH_ARGS)
    missing_qa = expected_query_args - qa_keys
    record("registry", "R1.2", f"QUERY_COMMANDS_WITH_ARGS ({len(qa_keys)} registered)",
           len(missing_qa) == 0,
           f"Missing: {missing_qa}" if missing_qa else "")

    # R1.3: Expected control commands (no args)
    expected_control = {'pause', 'resume', 'close'}
    ctrl_actual = CONTROL_COMMANDS if isinstance(CONTROL_COMMANDS, set) else set(CONTROL_COMMANDS)
    missing_ctrl = expected_control - ctrl_actual
    record("registry", "R1.3", f"CONTROL_COMMANDS ({len(ctrl_actual)} registered)",
           len(missing_ctrl) == 0,
           f"Missing: {missing_ctrl}" if missing_ctrl else "")

    # R1.4: Expected control commands with args
    expected_ctrl_args = {
        'force_analysis', 'partial_close', 'set_leverage', 'toggle',
        'set', 'restart', 'modify_sl', 'modify_tp', 'reload_config',
    }
    actual_ctrl_args = set(CONTROL_COMMANDS_WITH_ARGS.keys())
    missing_ca = expected_ctrl_args - actual_ctrl_args
    record("registry", "R1.4", f"CONTROL_COMMANDS_WITH_ARGS ({len(CONTROL_COMMANDS_WITH_ARGS)} registered)",
           len(missing_ca) == 0,
           f"Missing: {missing_ca}" if missing_ca else "")

    # R1.5: CALLBACK_MAP covers all query + control
    expected_callbacks = {
        'q_status', 'q_position', 'q_orders', 'q_history', 'q_risk',
        'q_daily', 'q_weekly', 'q_balance', 'q_analyze', 'q_config',
        'q_version', 'q_profit',
        'c_pause', 'c_resume', 'c_close', 'c_fa', 'c_restart', 'c_reload',
    }
    actual_callbacks = set(CALLBACK_MAP.keys())
    missing_cb = expected_callbacks - actual_callbacks
    record("registry", "R1.5", f"CALLBACK_MAP ({len(CALLBACK_MAP)} entries)",
           len(missing_cb) == 0,
           f"Missing callbacks: {missing_cb}" if missing_cb else "")

    # R1.6: PIN_MESSAGES covers all control commands
    ctrl_set = CONTROL_COMMANDS if isinstance(CONTROL_COMMANDS, set) else set(CONTROL_COMMANDS)
    all_control = ctrl_set | set(CONTROL_COMMANDS_WITH_ARGS.keys())
    pin_keys = set(PIN_MESSAGES.keys()) if isinstance(PIN_MESSAGES, dict) else set(PIN_MESSAGES)
    missing_pin = all_control - pin_keys
    record("registry", "R1.6", f"PIN_MESSAGES ({len(pin_keys)} entries)",
           len(missing_pin) == 0,
           f"Missing PIN messages for: {missing_pin}" if missing_pin else "",
           severity="warning")

    # R1.7: CALLBACK_MAP values match actual strategy command names
    all_strategy_cmds = set()
    for v in QUERY_COMMANDS.values():
        all_strategy_cmds.add(v)
    if isinstance(QUERY_COMMANDS_WITH_ARGS, dict):
        for k, v in QUERY_COMMANDS_WITH_ARGS.items():
            all_strategy_cmds.add(v[0] if isinstance(v, (tuple, list)) else k)
    else:
        for k in QUERY_COMMANDS_WITH_ARGS:
            all_strategy_cmds.add(k)
    for cmd in CONTROL_COMMANDS:
        all_strategy_cmds.add(cmd)
    for k, v in CONTROL_COMMANDS_WITH_ARGS.items():
        all_strategy_cmds.add(v[0] if isinstance(v, tuple) else k)

    invalid_callbacks = []
    for cb_key, cb_val in CALLBACK_MAP.items():
        if cb_val not in all_strategy_cmds:
            invalid_callbacks.append(f"{cb_key} → {cb_val}")
    record("registry", "R1.7", "CALLBACK_MAP values → valid strategy commands",
           len(invalid_callbacks) == 0,
           f"Invalid: {invalid_callbacks}" if invalid_callbacks else "")


# ═══════════════════════════════════════════
#  Section 2: Strategy Command Dispatcher
# ═══════════════════════════════════════════

def check_strategy_dispatcher():
    print_section("Strategy Command Dispatcher Mapping", 2)

    strategy_path = PROJECT_ROOT / "strategy" / "deepseek_strategy.py"
    if not strategy_path.exists():
        record("dispatcher", "D2.0", "Strategy file exists", False,
               f"{strategy_path} not found")
        return

    source = strategy_path.read_text()

    # D2.1: handle_telegram_command exists
    has_handler = "def handle_telegram_command" in source
    record("dispatcher", "D2.1", "handle_telegram_command() exists", has_handler)

    if not has_handler:
        return

    # Extract the dispatcher method
    lines = source.splitlines()
    handler_start = None
    for i, line in enumerate(lines):
        if "def handle_telegram_command" in line:
            handler_start = i
            break

    if handler_start is None:
        record("dispatcher", "D2.2", "Extract dispatcher method", False)
        return

    # Find all command → _cmd_* mappings in the dispatcher
    dispatch_map = {}
    handler_lines = lines[handler_start:handler_start + 120]
    for line in handler_lines:
        m = re.search(r"command\s*==\s*'(\w+)'", line)
        if m:
            cmd_name = m.group(1)
        m2 = re.search(r"self\._cmd_(\w+)\(", line)
        if m2:
            method_name = m2.group(1)
            if 'cmd_name' in dir() and cmd_name:
                dispatch_map[cmd_name] = f"_cmd_{method_name}"

    # Re-parse more carefully
    dispatch_map = {}
    current_cmd = None
    for line in handler_lines:
        m = re.search(r"command\s*==\s*'(\w+)'", line)
        if m:
            current_cmd = m.group(1)
        m2 = re.search(r"self\.(_cmd_\w+)\(", line)
        if m2 and current_cmd:
            dispatch_map[current_cmd] = m2.group(1)
            current_cmd = None

    record("dispatcher", "D2.2", f"Dispatcher routes ({len(dispatch_map)} found)",
           len(dispatch_map) >= 20,
           f"Found: {len(dispatch_map)}, expected >= 20")

    # D2.3: All expected strategy commands are dispatched
    # Note: 'update' is an alias for 'restart', 'set' maps to 'set_param'
    # The command handler does the translation, so we check the *strategy* command names
    parsed = _parse_registries_from_source()
    if parsed:
        expected_strategy_cmds = set()
        for v in parsed['QUERY_COMMANDS'].values():
            expected_strategy_cmds.add(v)
        for cmd in parsed['CONTROL_COMMANDS']:
            expected_strategy_cmds.add(cmd)
        # For CONTROL_COMMANDS_WITH_ARGS, the strategy command name is in the tuple value
        # When parsed from source, we get command_name → tuple ('strategy_cmd', ...)
        # The handler maps: command_name → strategy_cmd via tuple[0]
        # We need to check strategy_cmd names, not command_names
        handler_source = (PROJECT_ROOT / "utils" / "telegram_command_handler.py").read_text()
        ctrl_args_block = _extract_dict_block(handler_source, "CONTROL_COMMANDS_WITH_ARGS")
        # Extract strategy command names: ('strategy_cmd', ...)
        strategy_cmds_in_ctrl = set(re.findall(r"\(\s*'(\w+)'", ctrl_args_block))
        expected_strategy_cmds |= strategy_cmds_in_ctrl

        dispatched = set(dispatch_map.keys())
        missing = expected_strategy_cmds - dispatched
        record("dispatcher", "D2.3", "All registry commands → dispatcher",
               len(missing) == 0,
               f"Missing from dispatcher: {missing}" if missing else "")
    else:
        record("dispatcher", "D2.3", "All registry commands → dispatcher", False,
               "Cannot parse command registries", severity="warning")

    # D2.4: All _cmd_* methods exist in source
    all_cmd_methods = re.findall(r"def (_cmd_\w+)\s*\(self", source)
    all_cmd_set = set(all_cmd_methods)
    missing_methods = []
    for cmd, method in dispatch_map.items():
        if method not in all_cmd_set:
            missing_methods.append(f"{cmd} → {method}")
    record("dispatcher", "D2.4", f"All _cmd_* methods exist ({len(all_cmd_set)} found)",
           len(missing_methods) == 0,
           f"Missing methods: {missing_methods}" if missing_methods else "")

    # D2.5: _cmd_* methods return dict (check signature pattern)
    methods_without_return_type = []
    for method in all_cmd_set:
        pattern = rf"def {re.escape(method)}\(self.*\)\s*->\s*Dict"
        if not re.search(pattern, source):
            methods_without_return_type.append(method)
    record("dispatcher", "D2.5", "All _cmd_* methods declare -> Dict return",
           len(methods_without_return_type) == 0,
           f"Missing type hint: {methods_without_return_type[:5]}" if methods_without_return_type else "",
           severity="warning")


# ═══════════════════════════════════════════
#  Section 3: Bot Format Method Completeness
# ═══════════════════════════════════════════

def check_bot_format_methods():
    print_section("Bot Format Method Completeness", 3)

    bot_path = PROJECT_ROOT / "utils" / "telegram_bot.py"
    if not bot_path.exists():
        record("format", "F3.0", "telegram_bot.py exists", False)
        return

    source = bot_path.read_text()

    # Find all format_* methods
    format_methods = re.findall(r"def (format_\w+)\s*\(self", source)
    format_set = set(format_methods)

    expected_formats = {
        'format_heartbeat_message',
        'format_trade_execution',
        'format_position_update',
        'format_startup_message',
        'format_shutdown_message',
        'format_error_alert',
        'format_trailing_stop_update',
        'format_dynamic_sltp_update',
        'format_daily_summary',
        'format_weekly_summary',
        'format_trade_signal',
        'format_order_fill',
        'format_status_response',
        'format_position_response',
        'format_scaling_notification',
        'format_pause_response',
        'format_resume_response',
        'format_help_response',
    }

    record("format", "F3.0", f"Format methods found ({len(format_set)})",
           len(format_set) >= 15)

    missing_formats = expected_formats - format_set
    record("format", "F3.1", "All expected format methods exist",
           len(missing_formats) == 0,
           f"Missing: {missing_formats}" if missing_formats else "")

    extra_formats = format_set - expected_formats
    if extra_formats:
        record("format", "F3.2", f"Extra format methods ({len(extra_formats)})", True,
               f"Extra: {extra_formats}", severity="info")

    # F3.3: Key notification format methods have SL/TP support
    sltp_methods = ['format_status_response', 'format_position_response',
                    'format_heartbeat_message', 'format_dynamic_sltp_update']
    for method_name in sltp_methods:
        if method_name in format_set:
            # Check if the method body references SL/TP
            method_pattern = rf"def {re.escape(method_name)}\(self.*?\n(.*?)(?=\n    def |\nclass |\Z)"
            m = re.search(method_pattern, source, re.DOTALL)
            if m:
                body = m.group(1)
                has_sl = 'sl' in body.lower() or 'stop_loss' in body.lower() or 'SL' in body
                has_tp = 'tp' in body.lower() or 'take_profit' in body.lower() or 'TP' in body
                record("format", f"F3.3-{method_name}", f"{method_name} includes SL/TP data",
                       has_sl and has_tp,
                       f"SL ref={has_sl}, TP ref={has_tp}" if not (has_sl and has_tp) else "",
                       severity="warning")

    # F3.4: send_message_sync uses requests (thread-safe)
    has_requests = "requests.post" in source or "import requests" in source
    record("format", "F3.4", "send_message_sync uses requests (thread-safe)",
           has_requests,
           "Should use requests library, not async telegram bot" if not has_requests else "")

    # F3.5: Markdown fallback in _send_response
    has_markdown_fallback = "parse_mode" in source and ("parse entities" in source.lower() or "can't parse" in source.lower())
    record("format", "F3.5", "Markdown parse error fallback exists",
           has_markdown_fallback,
           severity="warning")


# ═══════════════════════════════════════════
#  Section 4: Format Method Mock Tests
# ═══════════════════════════════════════════

def check_format_mock_tests():
    print_section("Format Method Mock Tests", 4)

    try:
        from utils.telegram_bot import TelegramBot
    except ImportError as e:
        record("mock", "M4.0", "Import TelegramBot", False, str(e))
        return

    # Create a bot instance with dummy credentials
    try:
        bot = TelegramBot.__new__(TelegramBot)
        bot.token = "dummy"
        bot.chat_id = "dummy"
        bot.logger = __import__('logging').getLogger('diag_mock')
        bot.enabled = True
        bot.message_timeout = 5.0
        bot.use_queue = False
        bot.message_queue = None
        record("mock", "M4.0", "Create mock TelegramBot", True)
    except Exception as e:
        record("mock", "M4.0", "Create mock TelegramBot", False, str(e))
        return

    # Mock data for each format method
    test_cases = {
        'format_status_response': {
            'current_price': 97500.0,
            'equity': 1000.0,
            'available_balance': 800.0,
            'unrealized_pnl': 50.0,
            'last_signal': 'BUY',
            'last_confidence': 'HIGH',
            'is_paused': False,
            'position_side': 'LONG',
            'sl_price': 95000.0,
            'tp_price': 102000.0,
            'trailing_active': True,
        },
        'format_position_response': {
            'has_position': True,
            'instrument': 'BTCUSDT-PERP',
            'side': 'LONG',
            'quantity': 0.01,
            'entry_price': 96000.0,
            'current_price': 97500.0,
            'unrealized_pnl': 15.0,
            'pnl_pct': 1.56,
            'sl_price': 95000.0,
            'tp_price': 102000.0,
            'trailing_active': True,
            'leverage': 10,
            'position_value': 975.0,
            'margin_used': 97.5,
        },
        'format_heartbeat_message': {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'current_price': 97500.0,
            'has_position': True,
            'position_side': 'LONG',
            'position_qty': 0.01,
            'entry_price': 96000.0,
            'unrealized_pnl': 15.0,
            'pnl_pct': 1.56,
            'equity': 1000.0,
            'last_signal': 'BUY (上次)',
            'last_confidence': 'HIGH',
            'rsi': 55.0,
            'sma_20': 96500.0,
            'sma_50': 95000.0,
            'macd_value': 150.0,
            'macd_signal': 120.0,
            'bb_upper': 99000.0,
            'bb_lower': 94000.0,
            'sl_price': 95000.0,
            'tp_price': 102000.0,
        },
        'format_trade_execution': {
            'signal': 'BUY',
            'confidence': 'HIGH',
            'instrument': 'BTCUSDT-PERP',
            'entry_price': 97500.0,
            'quantity': 0.01,
            'sl_price': 95000.0,
            'tp_price': 102000.0,
            'reason': 'Strong bullish signal with high R/R',
            'leverage': 10,
        },
        'format_trailing_stop_update': {
            'side': 'LONG',
            'current_price': 98500.0,
            'old_sl': 95000.0,
            'new_sl': 96500.0,
            'trailing_distance_pct': 0.5,
        },
        'format_dynamic_sltp_update': {
            'side': 'LONG',
            'current_price': 98500.0,
            'old_sl': 95000.0,
            'new_sl': 96000.0,
            'old_tp': 102000.0,
            'new_tp': 103000.0,
            'sl_changed': True,
            'tp_changed': True,
        },
        'format_error_alert': {
            'error_type': 'OrderRejected',
            'message': 'Insufficient margin',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
        'format_startup_message': ('BTCUSDT-PERP.BINANCE', {
            'equity': 1000.0,
            'leverage': 10,
            'timer_interval': 900,
        }),
        'format_daily_summary': {
            'date': '2026-02-08',
            'total_trades': 3,
            'winning_trades': 2,
            'losing_trades': 1,
            'total_pnl': 50.0,
            'win_rate': 66.7,
        },
        'format_scaling_notification': {
            'action': 'ADD',
            'side': 'LONG',
            'old_qty': 0.005,
            'new_qty': 0.01,
            'price': 97500.0,
            'sl_price': 95000.0,
            'tp_price': 102000.0,
        },
        'format_pause_response': (True, "Trading paused"),
    }

    passed_count = 0
    total_count = 0

    for method_name, mock_data in test_cases.items():
        total_count += 1
        method = getattr(bot, method_name, None)
        if method is None:
            record("mock", f"M4.{total_count}", f"{method_name}() exists", False,
                   "Method not found on TelegramBot")
            continue

        try:
            if isinstance(mock_data, tuple):
                result = method(*mock_data)
            else:
                result = method(mock_data)

            if not isinstance(result, str):
                record("mock", f"M4.{total_count}", f"{method_name}() returns string", False,
                       f"Returned {type(result).__name__}: {repr(result)[:100]}")
                continue

            if len(result) == 0:
                record("mock", f"M4.{total_count}", f"{method_name}() returns non-empty", False,
                       "Returned empty string")
                continue

            if len(result) > 4096:
                record("mock", f"M4.{total_count}", f"{method_name}() within Telegram limit", False,
                       f"Length: {len(result)} > 4096 (Telegram max)",
                       severity="warning")
                continue

            record("mock", f"M4.{total_count}", f"{method_name}() → OK ({len(result)} chars)", True)
            passed_count += 1

        except Exception as e:
            record("mock", f"M4.{total_count}", f"{method_name}() runs without error", False,
                   f"Exception: {type(e).__name__}: {e}")

    # Edge case: format_status_response with None values
    total_count += 1
    try:
        result = bot.format_status_response({
            'current_price': None,
            'equity': None,
            'available_balance': None,
            'unrealized_pnl': None,
            'last_signal': None,
            'last_confidence': None,
            'is_paused': False,
        })
        record("mock", f"M4.{total_count}", "format_status_response(None values) → no crash",
               isinstance(result, str) and len(result) > 0,
               severity="warning")
    except Exception as e:
        record("mock", f"M4.{total_count}", "format_status_response(None values) → no crash", False,
               f"Crashed: {type(e).__name__}: {e}\n      Fix: use .get() with defaults in format_status_response",
               severity="warning")

    # Edge case: format_position_response with no position
    total_count += 1
    try:
        result = bot.format_position_response({
            'has_position': False,
            'instrument': 'BTCUSDT-PERP',
        })
        record("mock", f"M4.{total_count}", "format_position_response(no position) → no crash",
               isinstance(result, str) and len(result) > 0)
    except Exception as e:
        record("mock", f"M4.{total_count}", "format_position_response(no position) → no crash", False,
               f"Crashed: {type(e).__name__}: {e}")


# ═══════════════════════════════════════════
#  Section 5: SL/TP Data Flow Verification
# ═══════════════════════════════════════════

def check_sltp_data_flow():
    print_section("SL/TP Data Flow Verification", 5)

    strategy_path = PROJECT_ROOT / "strategy" / "deepseek_strategy.py"
    bot_path = PROJECT_ROOT / "utils" / "telegram_bot.py"

    if not strategy_path.exists() or not bot_path.exists():
        record("sltp", "S5.0", "Required files exist", False)
        return

    strat_source = strategy_path.read_text()
    bot_source = bot_path.read_text()

    # S5.1: _cmd_status includes SL/TP data
    cmd_status_match = re.search(
        r"def _cmd_status\(self\).*?(?=\n    def )", strat_source, re.DOTALL
    )
    if cmd_status_match:
        body = cmd_status_match.group(0)
        has_sl = 'sl_price' in body
        has_tp = 'tp_price' in body
        record("sltp", "S5.1", "/status command includes SL/TP",
               has_sl and has_tp,
               f"sl_price={has_sl}, tp_price={has_tp}")
    else:
        record("sltp", "S5.1", "/status command includes SL/TP", False,
               "_cmd_status not found")

    # S5.2: _cmd_position includes SL/TP data
    cmd_pos_match = re.search(
        r"def _cmd_position\(self\).*?(?=\n    def )", strat_source, re.DOTALL
    )
    if cmd_pos_match:
        body = cmd_pos_match.group(0)
        has_sl = 'sl_price' in body or 'stop_loss' in body
        has_tp = 'tp_price' in body or 'take_profit' in body
        record("sltp", "S5.2", "/position command includes SL/TP",
               has_sl and has_tp,
               f"sl_price={has_sl}, tp_price={has_tp}")
    else:
        record("sltp", "S5.2", "/position command includes SL/TP", False,
               "_cmd_position not found")

    # S5.3: _dynamic_sltp_update sends Telegram notification
    dynamic_match = re.search(
        r"def _dynamic_sltp_update\(self\).*?(?=\n    def )", strat_source, re.DOTALL
    )
    if dynamic_match:
        body = dynamic_match.group(0)
        has_tg = 'telegram_bot' in body and ('format_dynamic_sltp_update' in body or 'send_message' in body)
        record("sltp", "S5.3", "_dynamic_sltp_update sends Telegram notification",
               has_tg,
               "No telegram_bot notification found" if not has_tg else "")
    else:
        record("sltp", "S5.3", "_dynamic_sltp_update sends Telegram notification", False,
               "Method not found")

    # S5.4: format_dynamic_sltp_update exists in bot
    has_format = 'def format_dynamic_sltp_update' in bot_source
    record("sltp", "S5.4", "format_dynamic_sltp_update exists in TelegramBot", has_format)

    # S5.5: format_trailing_stop_update exists in bot
    has_trailing = 'def format_trailing_stop_update' in bot_source
    record("sltp", "S5.5", "format_trailing_stop_update exists in TelegramBot", has_trailing)

    # S5.6: Heartbeat includes SL/TP
    heartbeat_match = re.search(
        r"def format_heartbeat_message\(self.*?\n(.*?)(?=\n    def )", bot_source, re.DOTALL
    )
    if heartbeat_match:
        body = heartbeat_match.group(1)
        has_sl = 'sl_price' in body or 'SL' in body
        has_tp = 'tp_price' in body or 'TP' in body
        record("sltp", "S5.6", "Heartbeat message includes SL/TP",
               has_sl and has_tp,
               f"SL ref={has_sl}, TP ref={has_tp}" if not (has_sl and has_tp) else "",
               severity="warning")
    else:
        record("sltp", "S5.6", "Heartbeat message includes SL/TP", False,
               "format_heartbeat_message not found", severity="warning")

    # S5.7: SL/TP data source is thread-safe
    if cmd_status_match:
        body = cmd_status_match.group(0)
        uses_trailing_state = 'trailing_stop_state' in body
        uses_binance_fallback = 'binance_account' in body or 'get_sl_tp' in body
        # Must NOT use indicator_manager in actual code (exclude comments)
        code_lines = [l for l in body.splitlines()
                      if l.strip() and not l.strip().startswith('#')]
        code_only = '\n'.join(code_lines)
        uses_indicator = 'indicator_manager' in code_only and 'self.indicator_manager' in code_only
        record("sltp", "S5.7", "/status SL/TP data source is thread-safe",
               uses_trailing_state and not uses_indicator,
               f"trailing_stop_state={uses_trailing_state}, "
               f"binance_fallback={uses_binance_fallback}, "
               f"indicator_manager_in_code={uses_indicator} (MUST be False)")

    # S5.8: format_status_response handles SL/TP display
    status_format_match = re.search(
        r"def format_status_response\(self.*?\n(.*?)(?=\n    def )", bot_source, re.DOTALL
    )
    if status_format_match:
        body = status_format_match.group(1)
        has_sl_display = 'SL' in body or 'sl_price' in body or '止损' in body
        has_tp_display = 'TP' in body or 'tp_price' in body or '止盈' in body
        record("sltp", "S5.8", "format_status_response displays SL/TP",
               has_sl_display and has_tp_display,
               f"SL display={has_sl_display}, TP display={has_tp_display}")
    else:
        record("sltp", "S5.8", "format_status_response displays SL/TP", False,
               "Method not found")


# ═══════════════════════════════════════════
#  Section 6: Message Queue System
# ═══════════════════════════════════════════

def check_message_queue():
    print_section("Message Queue System", 6)

    try:
        from utils.telegram_queue import TelegramMessageQueue, MessagePriority
        record("queue", "Q6.1", "Import TelegramMessageQueue", True)
    except ImportError as e:
        record("queue", "Q6.1", "Import TelegramMessageQueue", False, str(e))
        return

    # Q6.2: MessagePriority has expected levels
    expected_levels = {'LOW', 'NORMAL', 'HIGH', 'CRITICAL'}
    actual_levels = {name for name, _ in MessagePriority.__members__.items()}
    missing_levels = expected_levels - actual_levels
    record("queue", "Q6.2", f"MessagePriority levels ({len(actual_levels)})",
           len(missing_levels) == 0,
           f"Missing: {missing_levels}" if missing_levels else "")

    # Q6.3: Priority ordering
    try:
        order_ok = (MessagePriority.LOW < MessagePriority.NORMAL <
                     MessagePriority.HIGH < MessagePriority.CRITICAL)
        record("queue", "Q6.3", "Priority ordering LOW < NORMAL < HIGH < CRITICAL",
               order_ok)
    except Exception as e:
        record("queue", "Q6.3", "Priority ordering", False, str(e))

    # Q6.4: Queue has essential methods
    essential_methods = ['enqueue', 'start', 'stop']
    missing = [m for m in essential_methods if not hasattr(TelegramMessageQueue, m)]
    record("queue", "Q6.4", f"Essential queue methods exist",
           len(missing) == 0,
           f"Missing: {missing}" if missing else "")

    # Q6.5: Bot uses queue
    bot_source = (PROJECT_ROOT / "utils" / "telegram_bot.py").read_text()
    uses_queue = 'TelegramMessageQueue' in bot_source or 'message_queue' in bot_source
    record("queue", "Q6.5", "TelegramBot integrates message queue",
           uses_queue)

    # Q6.6: Queue has persistence (SQLite)
    queue_source = (PROJECT_ROOT / "utils" / "telegram_queue.py").read_text()
    has_sqlite = 'sqlite3' in queue_source or 'sqlite' in queue_source.lower()
    record("queue", "Q6.6", "Queue has SQLite persistence",
           has_sqlite)


# ═══════════════════════════════════════════
#  Section 7: API Connectivity
# ═══════════════════════════════════════════

async def check_api_connectivity():
    print_section("API Connectivity", 7)

    load_env()
    token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')

    if not token:
        record("api", "A7.0", "TELEGRAM_BOT_TOKEN configured", False,
               "Not found in environment")
        return
    record("api", "A7.0", f"TELEGRAM_BOT_TOKEN configured ({token[:8]}...)", True)

    if not chat_id:
        record("api", "A7.1", "TELEGRAM_CHAT_ID configured", False,
               "Not found in environment")
        return
    record("api", "A7.1", f"TELEGRAM_CHAT_ID configured ({chat_id})", True)

    # A7.2: getMe test
    try:
        from telegram import Bot
        bot = Bot(token=token)
        me = await bot.get_me()
        record("api", "A7.2", f"Bot connected: @{me.username} ({me.first_name})", True)
    except Exception as e:
        record("api", "A7.2", "Bot getMe", False, str(e))
        return

    # A7.3: Webhook status
    try:
        webhook_info = await bot.get_webhook_info()
        has_webhook = bool(webhook_info.url)
        record("api", "A7.3", "No active webhook (polling mode)",
               not has_webhook,
               f"Active webhook: {webhook_info.url}" if has_webhook else "")
    except Exception as e:
        record("api", "A7.3", "Webhook check", False, str(e))

    # A7.4: Send test message with Markdown
    try:
        test_msg = (
            "🧪 *诊断测试*\n\n"
            f"时间: `{datetime.now().strftime('%H:%M:%S')}`\n"
            "状态: ✅ Markdown 正常\n"
            "SL: $95,000.00 | TP: $102,000.00\n"
            "R/R: 2.33:1\n\n"
            "by diagnose telegram v2.0"
        )
        msg = await bot.send_message(
            chat_id=chat_id, text=test_msg, parse_mode='Markdown'
        )
        record("api", "A7.4", "Send Markdown message to chat", True,
               f"Message ID: {msg.message_id}")
    except Exception as e:
        error_str = str(e)
        if "can't parse" in error_str.lower():
            record("api", "A7.4", "Send Markdown message", False,
                   f"Markdown parse error: {error_str}")
        else:
            record("api", "A7.4", "Send Markdown message", False, error_str)

    # A7.5: Test plain text fallback
    try:
        plain_msg = (
            "🧪 诊断测试 (纯文本)\n\n"
            f"时间: {datetime.now().strftime('%H:%M:%S')}\n"
            "如果你看到这条消息，Telegram 发送功能正常。"
        )
        msg2 = await bot.send_message(chat_id=chat_id, text=plain_msg)
        record("api", "A7.5", "Send plain text message", True)
    except Exception as e:
        record("api", "A7.5", "Send plain text message", False, str(e))

    try:
        await bot.close()
    except Exception:
        pass


# ═══════════════════════════════════════════
#  Section 8: Shortcut Command Registration
# ═══════════════════════════════════════════

def check_shortcut_commands():
    print_section("Shortcut Command Registration", 8)

    handler_path = PROJECT_ROOT / "utils" / "telegram_command_handler.py"
    if not handler_path.exists():
        record("shortcut", "SC8.0", "Command handler file exists", False)
        return

    source = handler_path.read_text()

    # Expected shortcuts
    shortcuts = {
        '/s': 'status',
        '/p': 'position',
        '/b': 'balance',
        '/a': 'analyze',
        '/v': 'version',
        '/l': 'logs',
        '/fa': 'force_analysis',
        '/pc': 'partial_close',
    }

    for shortcut, target in shortcuts.items():
        cmd = shortcut.lstrip('/')
        # Check if CommandHandler("cmd", ...) is registered
        pattern = rf'CommandHandler\(\s*"{re.escape(cmd)}"'
        found = bool(re.search(pattern, source))
        record("shortcut", f"SC8-{cmd}", f"{shortcut} → {target}",
               found,
               f"CommandHandler(\"{cmd}\", ...) not found" if not found else "")

    # SC8.9: Menu commands registered
    menu_cmds = ['menu', 'help', 'start']
    for cmd in menu_cmds:
        pattern = rf'CommandHandler\(\s*"{re.escape(cmd)}"'
        found = bool(re.search(pattern, source))
        record("shortcut", f"SC8-{cmd}", f"/{cmd} handler registered", found)

    # SC8.10: _register_commands lists expected slash menu items
    register_match = re.search(
        r"def _register_commands\(self\).*?(?=\n    (?:async\s+)?def )", source, re.DOTALL
    )
    if register_match:
        body = register_match.group(0)
        menu_items = re.findall(r'BotCommand\(\s*"(\w+)"', body)
        expected_menu = {'menu', 's', 'p', 'b', 'a', 'fa', 'profit', 'close', 'help'}
        actual_menu = set(menu_items)
        missing_menu = expected_menu - actual_menu
        record("shortcut", "SC8.10", f"Slash menu items ({len(actual_menu)} registered)",
               len(missing_menu) == 0,
               f"Missing from menu: {missing_menu}" if missing_menu else "")
    else:
        record("shortcut", "SC8.10", "_register_commands method exists", False)


# ═══════════════════════════════════════════
#  Section 9: Markdown Safety Checks
# ═══════════════════════════════════════════

def check_markdown_safety():
    print_section("Markdown Safety Checks", 9)

    try:
        from utils.telegram_bot import TelegramBot
    except ImportError as e:
        record("markdown", "MD9.0", "Import TelegramBot", False, str(e))
        return

    bot = TelegramBot.__new__(TelegramBot)
    bot.token = "dummy"
    bot.chat_id = "dummy"
    bot.logger = __import__('logging').getLogger('diag_md')
    bot.enabled = True
    bot.message_timeout = 5.0
    bot.use_queue = False
    bot.message_queue = None

    # MD9.1: Special characters in reason text
    edge_cases = [
        ("Markdown special chars in reason", {
            'current_price': 97500.0,
            'equity': 1000.0,
            'available_balance': 800.0,
            'unrealized_pnl': 50.0,
            'last_signal': 'BUY',
            'last_confidence': 'HIGH',
            'is_paused': False,
            'position_side': 'LONG',
            'sl_price': 95000.0,
            'tp_price': 102000.0,
        }),
        ("Zero price values", {
            'current_price': 0,
            'equity': 0,
            'available_balance': 0,
            'unrealized_pnl': 0,
            'last_signal': 'HOLD',
            'last_confidence': 'LOW',
            'is_paused': True,
        }),
        ("Very large numbers", {
            'current_price': 999999999.99,
            'equity': 9999999.99,
            'available_balance': 8888888.88,
            'unrealized_pnl': -999999.99,
            'last_signal': 'SELL',
            'last_confidence': 'MEDIUM',
            'is_paused': False,
        }),
    ]

    for i, (desc, data) in enumerate(edge_cases, 1):
        try:
            result = bot.format_status_response(data)
            # Check for unbalanced Markdown markers
            asterisk_count = result.count('*')
            backtick_count = result.count('`')
            underscore_sections = re.findall(r'_[^_]+_', result)

            issues = []
            if asterisk_count % 2 != 0:
                issues.append(f"Unbalanced * ({asterisk_count})")
            if backtick_count % 2 != 0:
                issues.append(f"Unbalanced ` ({backtick_count})")

            record("markdown", f"MD9.{i}", f"format_status_response: {desc}",
                   len(issues) == 0,
                   "; ".join(issues) if issues else "",
                   severity="warning")
        except Exception as e:
            record("markdown", f"MD9.{i}", f"format_status_response: {desc}", False,
                   f"Crashed: {type(e).__name__}: {e}")

    # MD9.4: format_dynamic_sltp_update edge cases
    sltp_edge_cases = [
        ("No change (both unchanged)", {
            'side': 'LONG', 'current_price': 97500.0,
            'old_sl': 95000.0, 'new_sl': 95000.0,
            'old_tp': 102000.0, 'new_tp': 102000.0,
            'sl_changed': False, 'tp_changed': False,
        }),
        ("Zero old values", {
            'side': 'SHORT', 'current_price': 97500.0,
            'old_sl': 0, 'new_sl': 99000.0,
            'old_tp': 0, 'new_tp': 95000.0,
            'sl_changed': True, 'tp_changed': True,
        }),
    ]

    for i, (desc, data) in enumerate(sltp_edge_cases, len(edge_cases) + 1):
        try:
            if hasattr(bot, 'format_dynamic_sltp_update'):
                result = bot.format_dynamic_sltp_update(data)
                record("markdown", f"MD9.{i}", f"format_dynamic_sltp_update: {desc}",
                       isinstance(result, str) and len(result) > 0)
            else:
                record("markdown", f"MD9.{i}", f"format_dynamic_sltp_update: {desc}",
                       False, "Method not found")
        except Exception as e:
            record("markdown", f"MD9.{i}", f"format_dynamic_sltp_update: {desc}", False,
                   f"Crashed: {type(e).__name__}: {e}")

    # MD9.6: Escape special chars test
    try:
        data_with_special = {
            'signal': 'BUY',
            'confidence': 'HIGH',
            'instrument': 'BTCUSDT-PERP',
            'entry_price': 97500.0,
            'quantity': 0.01,
            'sl_price': 95000.0,
            'tp_price': 102000.0,
            'reason': 'Test_with_special *chars* and `backticks` and [brackets]',
            'leverage': 10,
        }
        result = bot.format_trade_execution(data_with_special)
        record("markdown", "MD9.6", "format_trade_execution with special chars",
               isinstance(result, str) and len(result) > 0,
               severity="warning")
    except Exception as e:
        record("markdown", "MD9.6", "format_trade_execution with special chars", False,
               f"Crashed: {type(e).__name__}: {e}")


# ═══════════════════════════════════════════
#  Summary
# ═══════════════════════════════════════════

def print_summary():
    print()
    print("=" * 65)
    print("  DIAGNOSTIC SUMMARY")
    print("=" * 65)
    print()

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed_errors = [r for r in results if not r.passed and r.severity == "error"]
    failed_warnings = [r for r in results if not r.passed and r.severity == "warning"]

    print(f"  Total checks: {total}")
    print(f"  ✅ Passed:    {passed}")
    print(f"  ❌ Failed:    {len(failed_errors)}")
    print(f"  ⚠️  Warnings:  {len(failed_warnings)}")
    print()

    if failed_errors:
        print("  ─── ❌ ERRORS (must fix) ───")
        for r in failed_errors:
            print(f"  [{r.check_id}] {r.desc}")
            if r.detail:
                for line in r.detail.strip().split("\n"):
                    print(f"      {line}")
        print()

    if failed_warnings:
        print("  ─── ⚠️  WARNINGS (should fix) ───")
        for r in failed_warnings:
            print(f"  [{r.check_id}] {r.desc}")
            if r.detail:
                for line in r.detail.strip().split("\n"):
                    print(f"      {line}")
        print()

    # Section summary
    sections = {}
    for r in results:
        if r.section not in sections:
            sections[r.section] = {'total': 0, 'passed': 0}
        sections[r.section]['total'] += 1
        if r.passed:
            sections[r.section]['passed'] += 1

    section_names = {
        'registry': '1. Command Registry',
        'dispatcher': '2. Strategy Dispatcher',
        'format': '3. Bot Format Methods',
        'mock': '4. Format Mock Tests',
        'sltp': '5. SL/TP Data Flow',
        'queue': '6. Message Queue',
        'api': '7. API Connectivity',
        'shortcut': '8. Shortcut Commands',
        'markdown': '9. Markdown Safety',
    }

    print("  ─── Section Results ───")
    for key, name in section_names.items():
        if key in sections:
            s = sections[key]
            icon = "✅" if s['passed'] == s['total'] else "❌"
            print(f"  {icon} {name}: {s['passed']}/{s['total']}")
    print()

    overall = "✅ ALL CHECKS PASSED" if len(failed_errors) == 0 else "❌ ISSUES FOUND"
    print(f"  Overall: {overall}")
    print()

    return len(failed_errors) == 0


# ═══════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════

async def main():
    quick_mode = '--quick' in sys.argv

    print()
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║        Telegram System Diagnostic v2.0                      ║")
    print("║        Command System + Notification System                 ║")
    print(f"║        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                              ║")
    print("╚═══════════════════════════════════════════════════════════════╝")

    # Run all sections
    check_command_registry()
    check_strategy_dispatcher()
    check_bot_format_methods()
    check_format_mock_tests()
    check_sltp_data_flow()
    check_message_queue()

    if not quick_mode:
        await check_api_connectivity()
    else:
        print_section("API Connectivity (SKIPPED --quick)", 7)
        print("  ⏩ Skipped in quick mode")

    check_shortcut_commands()
    check_markdown_safety()

    success = print_summary()

    return 0 if success else 1


if __name__ == '__main__':
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)
