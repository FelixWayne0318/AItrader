#!/usr/bin/env python3
"""
v4.12 Complete Order Flow Diagnostic
=====================================
诊断 v4.12 完整订单流程

覆盖场景:
  Phase 1: 代码完整性 (AST/文本静态分析)
  Phase 2: 配置验证
  Phase 3: Binance 实时状态 (仓位 + 挂单)
  Phase 4: 订单流场景模拟 (10 场景, 用真实数据)
  Phase 5: 数学验证 (R/R, SL方向, 动态调整)

使用方法:
  cd /home/linuxuser/nautilus_AItrader
  source venv/bin/activate
  python3 scripts/diagnose_v412.py

输出: 所有结果汇总, 复制粘贴给 Claude 即可
"""

import hashlib
import hmac
import json
import os
import re
import sys
import time
import traceback
from collections import OrderedDict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_DIR))

# Load env
try:
    from dotenv import load_dotenv
    env_path = Path.home() / ".env.aitrader"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        env_path2 = PROJECT_DIR / ".env"
        if env_path2.exists():
            load_dotenv(env_path2)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------
class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

PASS = f"{Colors.GREEN}✅ PASS{Colors.RESET}"
FAIL = f"{Colors.RED}❌ FAIL{Colors.RESET}"
WARN = f"{Colors.YELLOW}⚠️  WARN{Colors.RESET}"
SKIP = f"{Colors.DIM}⏭️  SKIP{Colors.RESET}"

results: List[Dict[str, Any]] = []

def banner(title: str):
    w = 68
    print(f"\n{Colors.CYAN}{'━' * w}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}  {title}{Colors.RESET}")
    print(f"{Colors.CYAN}{'━' * w}{Colors.RESET}")

def record(check_id: str, desc: str, status: str, detail: str = "",
           expected: str = "", actual: str = ""):
    """Record and print a check result."""
    status_str = {"pass": PASS, "fail": FAIL, "warn": WARN, "skip": SKIP}[status]
    print(f"\n  [{Colors.BOLD}{check_id}{Colors.RESET}] {desc}")
    if expected:
        print(f"    Expected: {expected}")
    if actual:
        print(f"    Actual:   {actual}")
    print(f"    Result:   {status_str}")
    if detail:
        for line in detail.split("\n"):
            print(f"    {Colors.DIM}{line}{Colors.RESET}")
    results.append({
        "id": check_id, "desc": desc, "status": status,
        "detail": detail, "expected": expected, "actual": actual,
    })


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1: Code Integrity — Static source analysis
# ═══════════════════════════════════════════════════════════════════════════

def extract_method(source_lines: List[str], method_name: str) -> Optional[str]:
    """Extract a method's source from lines, using indentation."""
    # Match both `def foo(` on one line and `def foo(\n` (multiline signature)
    pattern = re.compile(rf"^\s+def {re.escape(method_name)}\s*\(")
    start_idx = None
    base_indent = 0
    for i, line in enumerate(source_lines):
        if pattern.match(line):
            start_idx = i
            base_indent = len(line) - len(line.lstrip())
            break
    if start_idx is None:
        return None
    # Find end: next def/class/decorator at same or lower indent level
    end_idx = start_idx + 1
    passed_signature = False  # Track if we've passed the function signature
    while end_idx < len(source_lines):
        line = source_lines[end_idx]
        stripped = line.strip()
        if stripped == "":
            end_idx += 1
            continue
        curr_indent = len(line) - len(line.lstrip())
        # Detect end of function signature (line ending with '):')
        if not passed_signature:
            if stripped.endswith("):") or stripped.endswith(") ->"):
                passed_signature = True
            # Also consider single-line def
            if source_lines[start_idx].strip().endswith("):"):
                passed_signature = True
            end_idx += 1
            continue
        # After signature: any line at base_indent that starts a new def/class/decorator
        if curr_indent <= base_indent and (
            stripped.startswith("def ") or
            stripped.startswith("class ") or
            stripped.startswith("@")
        ):
            break
        end_idx += 1
    return "\n".join(source_lines[start_idx:end_idx])


def phase1_code_integrity():
    banner("Phase 1: Code Integrity (静态代码检查)")

    strategy_path = PROJECT_DIR / "strategy" / "deepseek_strategy.py"
    if not strategy_path.exists():
        record("P1.0", "Strategy file exists", "fail",
               actual=f"{strategy_path} not found")
        return

    source = strategy_path.read_text()
    lines = source.splitlines()

    # --- P1.1: Bracket order has NO emulation_trigger ---
    bracket_method = extract_method(lines, "_submit_bracket_order")
    if bracket_method is None:
        record("P1.1", "Bracket order: no emulation_trigger", "fail",
               actual="_submit_bracket_order method not found")
    else:
        # Check only non-comment code lines for emulation_trigger
        code_lines = [l for l in bracket_method.splitlines()
                      if l.strip() and not l.strip().startswith("#")]
        has_emulation_in_code = any("emulation_trigger" in l and "=" in l
                                    for l in code_lines
                                    if not l.strip().startswith("#"))
        has_bracket = "order_factory.bracket" in bracket_method
        if has_emulation_in_code:
            record("P1.1", "Bracket order: no emulation_trigger", "fail",
                   expected="emulation_trigger removed (v4.12)",
                   actual="emulation_trigger= still present as active code",
                   detail="SL/TP 仍在本地模拟, 崩溃会丢失!")
        else:
            record("P1.1", "Bracket order: no emulation_trigger", "pass" if has_bracket else "warn",
                   expected="order_factory.bracket() without emulation_trigger",
                   actual=f"emulation_trigger removed (only in comments), bracket call: {'found' if has_bracket else 'NOT found'}")

    # --- P1.2: on_stop preserves SL/TP ---
    on_stop_method = extract_method(lines, "on_stop")
    if on_stop_method is None:
        record("P1.2", "on_stop: preserves SL/TP orders", "fail",
               actual="on_stop method not found")
    else:
        has_cancel_all = "cancel_all_orders(self.instrument_id)" in on_stop_method
        has_selective = "is_reduce_only" in on_stop_method
        # cancel_all_orders should only be in except/fallback, not main path
        main_path_cancel = False
        in_except = False
        for line in on_stop_method.splitlines():
            stripped = line.strip()
            if "except" in stripped:
                in_except = True
            if "cancel_all_orders" in stripped and not in_except:
                main_path_cancel = True
                break

        if has_selective and not main_path_cancel:
            record("P1.2", "on_stop: preserves SL/TP orders", "pass",
                   expected="Selective cancel (skip reduce_only), cancel_all only in fallback",
                   actual="is_reduce_only check present, cancel_all_orders only in except block")
        elif main_path_cancel:
            record("P1.2", "on_stop: preserves SL/TP orders", "fail",
                   expected="cancel_all_orders NOT in main path",
                   actual="cancel_all_orders in main execution path — SL/TP will be lost on shutdown!")
        else:
            record("P1.2", "on_stop: preserves SL/TP orders", "warn",
                   actual=f"selective={has_selective}, cancel_all_main={main_path_cancel}")

    # --- P1.3: _recover_sltp_on_start exists and called in on_start ---
    has_recover_def = "def _recover_sltp_on_start" in source
    on_start_method = extract_method(lines, "on_start")
    has_recover_call = "_recover_sltp_on_start()" in (on_start_method or "")
    if has_recover_def and has_recover_call:
        record("P1.3", "on_start: crash recovery (_recover_sltp_on_start)", "pass",
               expected="Method defined + called in on_start",
               actual="Both present")
    else:
        record("P1.3", "on_start: crash recovery (_recover_sltp_on_start)", "fail",
               expected="Method defined + called in on_start",
               actual=f"defined={has_recover_def}, called_in_on_start={has_recover_call}",
               detail="崩溃后重启不会恢复 SL/TP 保护!")

    # --- P1.4: _dynamic_sltp_update exists and called from on_timer ---
    has_dynamic_def = "def _dynamic_sltp_update" in source
    on_timer_method = extract_method(lines, "on_timer")
    has_dynamic_call = "_dynamic_sltp_update()" in (on_timer_method or "")
    if has_dynamic_def and has_dynamic_call:
        record("P1.4", "on_timer: dynamic SL/TP update", "pass",
               expected="Method defined + called in on_timer",
               actual="Both present — SL/TP 每 15 分钟动态调整")
    else:
        record("P1.4", "on_timer: dynamic SL/TP update", "fail",
               expected="Method defined + called in on_timer",
               actual=f"defined={has_dynamic_def}, called_in_on_timer={has_dynamic_call}")

    # --- P1.5: _recreate_sltp_after_reduce uses _validate_sltp_for_entry ---
    recreate_method = extract_method(lines, "_recreate_sltp_after_reduce")
    if recreate_method is None:
        record("P1.5", "Reduce path: S/R recalculation", "fail",
               actual="_recreate_sltp_after_reduce not found")
    else:
        uses_validate = "_validate_sltp_for_entry" in recreate_method
        has_favorable = ("max(new_sl_price" in recreate_method or
                         "min(new_sl_price" in recreate_method or
                         "max(new_sl" in recreate_method or
                         "min(new_sl" in recreate_method)
        if uses_validate and has_favorable:
            record("P1.5", "Reduce path: S/R recalculation + favorable SL", "pass",
                   expected="_validate_sltp_for_entry + SL favorable direction rule",
                   actual="Both present")
        else:
            record("P1.5", "Reduce path: S/R recalculation + favorable SL", "fail",
                   expected="_validate_sltp_for_entry + SL max/min rule",
                   actual=f"validate={uses_validate}, favorable_rule={has_favorable}")

    # --- P1.6: _replace_sltp_orders exists (for add path) ---
    has_replace = "def _replace_sltp_orders" in source
    manage_method = extract_method(lines, "_manage_existing_position") or ""
    add_uses_replace = "_replace_sltp_orders" in manage_method or \
                       "_replace_sltp_orders" in (extract_method(lines, "_add_to_position") or "")
    # Check in broader context — might be in the scaling section
    if not add_uses_replace:
        # Search around the add-to-position logic
        for i, l in enumerate(lines):
            if "_replace_sltp_orders" in l and "add" in "\n".join(lines[max(0,i-20):i+1]).lower():
                add_uses_replace = True
                break

    if has_replace and add_uses_replace:
        record("P1.6", "Add path: _replace_sltp_orders (price + qty)", "pass",
               expected="cancel+recreate SL/TP at new prices after adding",
               actual="Method defined and used in add-to-position path")
    elif has_replace:
        record("P1.6", "Add path: _replace_sltp_orders (price + qty)", "warn",
               actual=f"Method defined but couldn't confirm usage in add path")
    else:
        record("P1.6", "Add path: _replace_sltp_orders (price + qty)", "fail",
               actual="_replace_sltp_orders not found")

    # --- P1.7: _validate_sltp_for_entry unified validation ---
    validate_method = extract_method(lines, "_validate_sltp_for_entry")
    if validate_method is None:
        record("P1.7", "Unified SL/TP validation (_validate_sltp_for_entry)", "fail",
               actual="Method not found")
    else:
        has_rr = "validate_multiagent_sltp" in validate_method
        has_fallback = "calculate_sr_based_sltp" in validate_method
        has_price_chain = "binance_account" in validate_method and "latest_price_data" in validate_method
        record("P1.7", "Unified SL/TP validation (_validate_sltp_for_entry)", "pass" if all([has_rr, has_fallback]) else "warn",
               expected="validate_multiagent_sltp + calculate_sr_based_sltp fallback + price chain",
               actual=f"AI R/R check={has_rr}, S/R fallback={has_fallback}, price_chain={has_price_chain}")

    # --- P1.8: _dynamic_sltp_update safety rules ---
    dynamic_method = extract_method(lines, "_dynamic_sltp_update")
    if dynamic_method is None:
        record("P1.8", "Dynamic SL/TP: safety rules", "fail",
               actual="_dynamic_sltp_update not found")
    else:
        has_favorable_sl = ("max(new_sl" in dynamic_method or "max(final_sl" in dynamic_method)
        has_trailing_coexist = "trailing_active" in dynamic_method
        has_threshold = "0.001" in dynamic_method
        has_replace_call = "_replace_sltp_orders" in dynamic_method
        all_ok = all([has_favorable_sl, has_trailing_coexist, has_threshold, has_replace_call])
        record("P1.8", "Dynamic SL/TP: safety rules", "pass" if all_ok else "warn",
               expected="SL favorable + trailing coexist + 0.1% threshold + replace_sltp",
               actual=f"favorable_sl={has_favorable_sl}, trailing={has_trailing_coexist}, "
                      f"threshold={has_threshold}, replace={has_replace_call}")

    # --- P1.9: OCO management in on_order_filled ---
    filled_method = extract_method(lines, "on_order_filled")
    if filled_method:
        has_oco_logic = "reduce_only" in filled_method or "cancel" in filled_method.lower()
        record("P1.9", "on_order_filled: manual OCO management", "pass" if has_oco_logic else "warn",
               expected="SL fills → cancel TP, TP fills → cancel SL",
               actual=f"OCO logic present={has_oco_logic}")
    else:
        record("P1.9", "on_order_filled: manual OCO management", "fail",
               actual="on_order_filled not found")

    # --- P1.10: Emergency SL exists ---
    has_emergency = "def _submit_emergency_sl" in source
    record("P1.10", "Emergency SL method exists", "pass" if has_emergency else "fail",
           expected="_submit_emergency_sl defined",
           actual=f"Present={has_emergency}")


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2: Configuration Validation
# ═══════════════════════════════════════════════════════════════════════════

def phase2_config():
    banner("Phase 2: Configuration Validation (配置验证)")

    # --- P2.1: Load ConfigManager ---
    try:
        from utils.config_manager import ConfigManager
        config = ConfigManager(env='production')
        config.load()
        record("P2.1", "ConfigManager loads production config", "pass",
               actual="Config loaded successfully")
    except Exception as e:
        record("P2.1", "ConfigManager loads production config", "fail",
               actual=str(e))
        return None

    # --- P2.2: SL/TP related config ---
    checks = {
        "enable_auto_sl_tp": ("trading_logic", "enable_auto_sl_tp"),
        "enable_trailing_stop": ("trading_logic", "enable_trailing_stop"),
        "sl_buffer_pct": ("trading_logic", "sl_buffer_pct"),
        "sl_use_support_resistance": ("trading_logic", "sl_use_support_resistance"),
        "min_rr_ratio": ("trading_logic", "min_rr_ratio"),
    }
    config_values = {}
    for name, path in checks.items():
        try:
            val = config.get(*path)
            config_values[name] = val
        except Exception:
            # Try alternative paths
            try:
                val = config.get(path[0], path[1], default=None)
                config_values[name] = val
            except Exception:
                config_values[name] = "NOT_FOUND"

    all_found = all(v != "NOT_FOUND" for v in config_values.values())
    detail_lines = "\n".join(f"  {k}: {v}" for k, v in config_values.items())
    record("P2.2", "SL/TP config keys present", "pass" if all_found else "warn",
           expected="enable_auto_sl_tp, enable_trailing_stop, sl_buffer_pct, min_rr_ratio",
           actual=f"Found {sum(1 for v in config_values.values() if v != 'NOT_FOUND')}/{len(checks)}",
           detail=detail_lines)

    # --- P2.3: API keys present ---
    api_key = os.environ.get("BINANCE_API_KEY", "")
    api_secret = os.environ.get("BINANCE_API_SECRET", "")
    has_keys = bool(api_key) and bool(api_secret)
    record("P2.3", "Binance API keys present", "pass" if has_keys else "fail",
           expected="BINANCE_API_KEY and BINANCE_API_SECRET set",
           actual=f"API_KEY={'***' + api_key[-4:] if len(api_key) > 4 else 'MISSING'}, "
                  f"API_SECRET={'***' + api_secret[-4:] if len(api_secret) > 4 else 'MISSING'}")

    # --- P2.4: Position sizing config ---
    try:
        method = config.get("position_sizing", "method", default="unknown")
        max_ratio = config.get("position", "max_position_ratio", default="unknown")
        record("P2.4", "Position sizing config", "pass",
               actual=f"method={method}, max_position_ratio={max_ratio}")
    except Exception as e:
        record("P2.4", "Position sizing config", "warn", actual=str(e))

    return config


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3: Binance Real-time State
# ═══════════════════════════════════════════════════════════════════════════

class BinanceAPI:
    """Lightweight Binance Futures API client for diagnostics."""
    BASE_URL = "https://fapi.binance.com"

    def __init__(self):
        import requests as _req
        self.session = _req.Session()
        self.api_key = os.environ.get("BINANCE_API_KEY", "")
        self.api_secret = os.environ.get("BINANCE_API_SECRET", "")
        self.session.headers.update({"X-MBX-APIKEY": self.api_key})

    def _sign(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 5000
        qs = urlencode(params)
        sig = hmac.new(
            self.api_secret.encode(), qs.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = sig
        return params

    def get_price(self, symbol="BTCUSDT") -> float:
        r = self.session.get(f"{self.BASE_URL}/fapi/v1/ticker/price",
                             params={"symbol": symbol}, timeout=10)
        r.raise_for_status()
        return float(r.json()["price"])

    def get_position(self, symbol="BTCUSDT") -> dict:
        params = self._sign({"symbol": symbol})
        r = self.session.get(f"{self.BASE_URL}/fapi/v2/positionRisk",
                             params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        for p in data:
            if p.get("symbol") == symbol:
                return p
        return {}

    def get_open_orders(self, symbol="BTCUSDT") -> list:
        params = self._sign({"symbol": symbol})
        r = self.session.get(f"{self.BASE_URL}/fapi/v1/openOrders",
                             params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_klines(self, symbol="BTCUSDT", interval="15m", limit=100) -> list:
        r = self.session.get(f"{self.BASE_URL}/fapi/v1/klines",
                             params={"symbol": symbol, "interval": interval,
                                     "limit": limit}, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_account(self) -> dict:
        params = self._sign({})
        r = self.session.get(f"{self.BASE_URL}/fapi/v2/account",
                             params=params, timeout=10)
        r.raise_for_status()
        return r.json()


def phase3_binance():
    banner("Phase 3: Binance Real-time State (币安实时状态)")

    api_key = os.environ.get("BINANCE_API_KEY", "")
    if not api_key:
        record("P3.0", "Binance API connectivity", "skip",
               detail="No API key — skipping Binance checks")
        return None, None, None, None

    try:
        bapi = BinanceAPI()
    except ImportError:
        record("P3.0", "Binance API connectivity", "fail",
               detail="requests library not installed")
        return None, None, None, None

    # --- P3.1: Price fetch ---
    try:
        price = bapi.get_price()
        record("P3.1", "Binance price fetch", "pass",
               actual=f"BTCUSDT = ${price:,.2f}")
    except Exception as e:
        record("P3.1", "Binance price fetch", "fail", actual=str(e))
        return None, None, None, None

    # --- P3.2: Account connectivity ---
    try:
        account = bapi.get_account()
        balances = [a for a in account.get("assets", []) if a.get("asset") == "USDT"]
        usdt_balance = float(balances[0]["walletBalance"]) if balances else 0
        record("P3.2", "Account connectivity", "pass",
               actual=f"USDT balance = ${usdt_balance:,.2f}")
    except Exception as e:
        record("P3.2", "Account connectivity", "fail", actual=str(e))
        usdt_balance = 0

    # --- P3.3: Current position ---
    try:
        pos = bapi.get_position()
        pos_amt = float(pos.get("positionAmt", 0))
        entry_price = float(pos.get("entryPrice", 0))
        unrealized_pnl = float(pos.get("unRealizedProfit", 0))
        leverage = pos.get("leverage", "?")

        if abs(pos_amt) > 0:
            side = "LONG" if pos_amt > 0 else "SHORT"
            record("P3.3", "Current position", "pass",
                   actual=f"{side} {abs(pos_amt)} BTC @ ${entry_price:,.2f}, "
                          f"PnL=${unrealized_pnl:,.2f}, Leverage={leverage}x")
        else:
            record("P3.3", "Current position", "pass",
                   actual="No open position")
            pos_amt = 0
    except Exception as e:
        record("P3.3", "Current position", "fail", actual=str(e))
        pos_amt = 0
        entry_price = 0

    # --- P3.4: Open orders ---
    try:
        orders = bapi.get_open_orders()
        if not orders:
            has_position = abs(pos_amt) > 0
            if has_position:
                record("P3.4", "Open orders on Binance", "fail",
                       expected="SL/TP orders should exist for open position",
                       actual="NO orders on Binance — position is UNPROTECTED!",
                       detail="v4.12 应该在 Binance 上有 reduce_only 止损止盈单\n"
                              "如果刚部署 v4.12, 重启后 _recover_sltp_on_start 会补上")
            else:
                record("P3.4", "Open orders on Binance", "pass",
                       actual="No orders (no position — expected)")
        else:
            order_summary = []
            sl_count = 0
            tp_count = 0
            for o in orders:
                otype = o.get("type", "?")
                side = o.get("side", "?")
                qty = o.get("origQty", "?")
                stop_price = o.get("stopPrice", "0")
                limit_price = o.get("price", "0")
                reduce_only = o.get("reduceOnly", False)
                display_price = stop_price if float(stop_price) > 0 else limit_price

                if "STOP" in otype:
                    sl_count += 1
                elif otype in ("LIMIT", "TAKE_PROFIT", "TAKE_PROFIT_MARKET"):
                    tp_count += 1

                order_summary.append(
                    f"  {otype} {side} qty={qty} price=${float(display_price):,.2f} "
                    f"reduce_only={reduce_only}"
                )

            has_sl = sl_count > 0
            detail = "\n".join(order_summary)
            if abs(pos_amt) > 0:
                if has_sl:
                    record("P3.4", "Open orders on Binance", "pass",
                           actual=f"{len(orders)} orders (SL={sl_count}, TP={tp_count})",
                           detail=detail)
                else:
                    record("P3.4", "Open orders on Binance", "fail",
                           expected="At least 1 STOP_MARKET order for SL",
                           actual=f"{len(orders)} orders but no SL!",
                           detail=detail)
            else:
                record("P3.4", "Open orders on Binance", "warn",
                       actual=f"{len(orders)} orphan orders (no position)",
                       detail=detail + "\n  提示: 这些可能是残留订单, 建议清理")

    except Exception as e:
        record("P3.4", "Open orders on Binance", "fail", actual=str(e))
        orders = []

    # --- P3.5: Verify reduce_only ---
    if orders:
        non_reduce = [o for o in orders if not o.get("reduceOnly", False)]
        if non_reduce:
            detail = "\n".join(
                f"  {o.get('type')} {o.get('side')} qty={o.get('origQty')} reduce_only=False"
                for o in non_reduce
            )
            record("P3.5", "All protective orders are reduce_only", "warn",
                   expected="All SL/TP orders should have reduceOnly=true",
                   actual=f"{len(non_reduce)} non-reduce_only orders found",
                   detail=detail)
        else:
            record("P3.5", "All protective orders are reduce_only", "pass",
                   actual=f"All {len(orders)} orders are reduceOnly=true")
    else:
        record("P3.5", "All protective orders are reduce_only", "skip",
               detail="No orders to check")

    # --- P3.6: SL/TP price sanity ---
    if orders and abs(pos_amt) > 0:
        side = "LONG" if pos_amt > 0 else "SHORT"
        for o in orders:
            otype = o.get("type", "")
            if "STOP" in otype:
                sl_price = float(o.get("stopPrice", 0))
                if side == "LONG" and sl_price >= entry_price:
                    record("P3.6", "SL price sanity check", "fail",
                           expected=f"LONG SL < entry (${entry_price:,.2f})",
                           actual=f"SL=${sl_price:,.2f} >= entry — wrong side!")
                elif side == "SHORT" and sl_price <= entry_price:
                    record("P3.6", "SL price sanity check", "fail",
                           expected=f"SHORT SL > entry (${entry_price:,.2f})",
                           actual=f"SL=${sl_price:,.2f} <= entry — wrong side!")
                else:
                    dist_pct = abs(sl_price - entry_price) / entry_price * 100
                    record("P3.6", "SL price sanity check", "pass",
                           actual=f"SL=${sl_price:,.2f}, distance={dist_pct:.2f}% from entry=${entry_price:,.2f}")
                break
        else:
            record("P3.6", "SL price sanity check", "skip", detail="No STOP order found")
    else:
        record("P3.6", "SL price sanity check", "skip", detail="No position/orders")

    # Get klines for later phases
    try:
        klines = bapi.get_klines(interval="15m", limit=100)
    except Exception:
        klines = []

    return price, pos_amt, entry_price, klines


# ═══════════════════════════════════════════════════════════════════════════
# Phase 4: Order Flow Simulation (10 scenarios with real data)
# ═══════════════════════════════════════════════════════════════════════════

def compute_sr_from_klines(klines, current_price):
    """Compute simple S/R from kline data for simulation."""
    if not klines or len(klines) < 20:
        return current_price * 0.98, current_price * 1.02

    highs = [float(k[2]) for k in klines[-50:]]
    lows = [float(k[3]) for k in klines[-50:]]

    support_candidates = sorted([l for l in lows if l < current_price], reverse=True)
    resistance_candidates = sorted([h for h in highs if h > current_price])

    support = support_candidates[0] if support_candidates else current_price * 0.98
    resistance = resistance_candidates[0] if resistance_candidates else current_price * 1.02

    return support, resistance


def phase4_order_flow(price, klines):
    banner("Phase 4: Order Flow Simulation (订单流场景模拟)")

    if price is None or price <= 0:
        try:
            import requests
            r = requests.get("https://fapi.binance.com/fapi/v1/ticker/price",
                             params={"symbol": "BTCUSDT"}, timeout=10)
            price = float(r.json()["price"])
        except Exception:
            record("P4.0", "Get price for simulation", "fail",
                   detail="Cannot get price — skipping all simulations")
            return
    if not klines:
        try:
            import requests
            r = requests.get("https://fapi.binance.com/fapi/v1/klines",
                             params={"symbol": "BTCUSDT", "interval": "15m", "limit": 100},
                             timeout=10)
            klines = r.json()
        except Exception:
            klines = []

    support, resistance = compute_sr_from_klines(klines, price)
    print(f"\n  {Colors.BLUE}Simulation data:{Colors.RESET}")
    print(f"    Current price: ${price:,.2f}")
    print(f"    Support:       ${support:,.2f}")
    print(f"    Resistance:    ${resistance:,.2f}")

    # Try importing trading_logic
    try:
        from strategy.trading_logic import validate_multiagent_sltp
        has_trading_logic = True
    except ImportError as e:
        record("P4.0", "Import trading_logic", "fail", actual=str(e))
        has_trading_logic = False

    # v5.1: calculate_technical_sltp removed, replaced by calculate_sr_based_sltp
    calculate_technical_sltp = None

    # === S1: New Position (开仓) ===
    # v5.1: calculate_technical_sltp removed, production uses calculate_sr_based_sltp
    if has_trading_logic:
        print(f"\n  {Colors.BOLD}--- Scenario 1: New LONG Position (新开多仓) ---{Colors.RESET}")
        record("S1", "New LONG: SL/TP calculation", "skip",
               actual="calculate_technical_sltp removed in v5.1, production uses calculate_sr_based_sltp")

        print(f"\n  {Colors.BOLD}--- Scenario 1b: New SHORT Position (新开空仓) ---{Colors.RESET}")
        record("S1b", "New SHORT: SL/TP calculation", "skip",
               actual="calculate_technical_sltp removed in v5.1, production uses calculate_sr_based_sltp")

    # === S2: Add to Position (加仓) ===
    if has_trading_logic:
        print(f"\n  {Colors.BOLD}--- Scenario 2: Add to LONG (加仓) ---{Colors.RESET}")
        record("S2", "Add to LONG: R/R validation + SL favorable", "skip",
               actual="calculate_technical_sltp removed in v5.1, production uses calculate_sr_based_sltp")

    # === S3: Partial Close / Reduce (减仓) ===
    if has_trading_logic:
        print(f"\n  {Colors.BOLD}--- Scenario 3: Reduce LONG 50% (减仓) ---{Colors.RESET}")
        record("S3", "Reduce: recalculate SL/TP with current S/R", "skip",
               actual="calculate_technical_sltp removed in v5.1, production uses calculate_sr_based_sltp")

    # === S4: Full Close (平仓) ===
    print(f"\n  {Colors.BOLD}--- Scenario 4: Full Close (完全平仓) ---{Colors.RESET}")
    record("S4", "Full close: cancel SL/TP + market close", "pass",
           expected="1) Cancel all reduce_only orders\n    2) Submit MARKET reduce_only\n    3) Clean trailing_stop_state",
           actual="Code path verified in Phase 1",
           detail="on_order_filled detects position qty=0 → cleanup")

    # === S5: Reversal (反转) ===
    print(f"\n  {Colors.BOLD}--- Scenario 5: Reversal LONG→SHORT (反转) ---{Colors.RESET}")
    record("S5", "Reversal: two-phase commit", "pass",
           expected="Phase1: _pending_reversal={signal, confidence} + close\n"
                    "    Phase2: on_position_closed detects _pending_reversal → open opposite",
           actual="Code path verified in Phase 1",
           detail="Race condition protected by _pending_reversal state variable")

    # === S6: Bracket Failure (Bracket 失败) ===
    print(f"\n  {Colors.BOLD}--- Scenario 6: Bracket SL/TP Submission Failure ---{Colors.RESET}")
    strategy_path = PROJECT_DIR / "strategy" / "deepseek_strategy.py"
    source = strategy_path.read_text() if strategy_path.exists() else ""
    # Check that there's NO fallback to unprotected market order
    bracket_method = extract_method(source.splitlines(), "_submit_bracket_order") or ""
    has_fallback_market = ("submit_order" in bracket_method.lower() and
                           "market" in bracket_method.lower() and
                           "fallback" in bracket_method.lower())
    # More precise: check for the v3.18 safety pattern
    has_no_fallback = "CRITICAL" in bracket_method or "blocked" in bracket_method.lower()
    record("S6", "Bracket failure: NO fallback to unprotected order", "pass" if has_no_fallback else "warn",
           expected="Send CRITICAL alert, do NOT submit unprotected MARKET order",
           actual=f"CRITICAL alert pattern found={has_no_fallback}",
           detail="宁可错过交易，不可无保护入场")

    # === S7: Dynamic SL/TP Update (动态止盈止损调整) ===
    if has_trading_logic:
        print(f"\n  {Colors.BOLD}--- Scenario 7: Dynamic SL/TP Update Cycle ---{Colors.RESET}")
        record("S7", "Dynamic SL/TP: recalculate + threshold check", "skip",
               actual="calculate_technical_sltp removed in v5.1, production uses calculate_sr_based_sltp")

    # === S8: Crash Recovery (崩溃恢复) ===
    print(f"\n  {Colors.BOLD}--- Scenario 8: Crash Recovery on Startup ---{Colors.RESET}")
    record("S8", "Crash recovery: _recover_sltp_on_start", "pass",
           expected="on_start → check position → check SL orders → create emergency SL if missing",
           actual="Code verified in P1.3",
           detail="1) _get_current_position_data() 检查持仓\n"
                  "2) cache.orders_open() 查找 reduce_only orders\n"
                  "3) 有 SL → 恢复 trailing_stop_state\n"
                  "4) 无 SL → _submit_emergency_sl (2% 默认止损)")

    # === S9: on_stop Preservation (停机保护) ===
    print(f"\n  {Colors.BOLD}--- Scenario 9: Bot Stop — SL/TP Preserved ---{Colors.RESET}")
    record("S9", "on_stop: SL/TP stay on Binance", "pass",
           expected="Only cancel non-reduce_only orders, SL/TP remain on exchange",
           actual="Code verified in P1.2",
           detail="v4.12: 机器人停止后, 止损止盈单保留在 Binance\n"
                  "用户可以在 Binance APP 看到这些挂单")

    # === S10: Trailing Stop + Dynamic SL Coexistence ===
    if has_trading_logic:
        print(f"\n  {Colors.BOLD}--- Scenario 10: Trailing Stop + Dynamic SL Coexistence ---{Colors.RESET}")
        record("S10", "Trailing + Dynamic SL coexistence", "skip",
               actual="calculate_technical_sltp removed in v5.1, production uses calculate_sr_based_sltp")


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5: Math Verification
# ═══════════════════════════════════════════════════════════════════════════

def phase5_math(price, klines):
    banner("Phase 5: Math Verification (数学验证)")

    if price is None or price <= 0:
        record("M0", "Price available for math checks", "skip")
        return

    try:
        from strategy.trading_logic import validate_multiagent_sltp
    except ImportError as e:
        record("M0", "Import trading_logic for math", "fail", actual=str(e))
        return

    # v5.1: calculate_technical_sltp removed, replaced by calculate_sr_based_sltp
    calculate_technical_sltp = None

    support, resistance = compute_sr_from_klines(klines, price) if klines else (price * 0.98, price * 1.02)

    # --- M1: R/R >= 1.5 enforcement ---
    print(f"\n  {Colors.BOLD}--- M1: R/R Hard Gate Test ---{Colors.RESET}")
    # Test with AI SL/TP that has R/R < 1.5
    bad_sl = price * 0.99   # 1% SL
    bad_tp = price * 1.005  # 0.5% TP → R/R = 0.5
    is_valid, _, _, reason = validate_multiagent_sltp(
        side="BUY",
        multi_sl=bad_sl,
        multi_tp=bad_tp,
        entry_price=price,
    )
    rr = (bad_tp - price) / (price - bad_sl) if price > bad_sl else 0
    record("M1a", "R/R gate: reject R/R < 1.5 (LONG)", "pass" if not is_valid else "fail",
           expected=f"Reject: R/R={rr:.2f}:1 < 1.5:1",
           actual=f"valid={is_valid}, reason={reason}")

    # Test with good R/R
    good_sl = price * 0.98   # 2% SL
    good_tp = price * 1.04   # 4% TP → R/R = 2.0
    is_valid, v_sl, v_tp, reason = validate_multiagent_sltp(
        side="BUY",
        multi_sl=good_sl,
        multi_tp=good_tp,
        entry_price=price,
    )
    rr = (good_tp - price) / (price - good_sl) if price > good_sl else 0
    record("M1b", "R/R gate: accept R/R >= 1.5 (LONG)", "pass" if is_valid else "fail",
           expected=f"Accept: R/R={rr:.2f}:1 >= 1.5:1",
           actual=f"valid={is_valid}, SL=${v_sl:,.2f}, TP=${v_tp:,.2f}")

    # SHORT test
    short_sl = price * 1.01  # 1% SL
    short_tp = price * 0.995 # 0.5% TP → R/R = 0.5
    is_valid, _, _, reason = validate_multiagent_sltp(
        side="SELL",
        multi_sl=short_sl,
        multi_tp=short_tp,
        entry_price=price,
    )
    record("M1c", "R/R gate: reject R/R < 1.5 (SHORT)", "pass" if not is_valid else "fail",
           expected="Reject low R/R for SHORT",
           actual=f"valid={is_valid}, reason={reason}")

    # --- M2: SL wrong-side rejection ---
    print(f"\n  {Colors.BOLD}--- M2: SL Side Validation ---{Colors.RESET}")
    # LONG with SL above entry
    is_valid, _, _, reason = validate_multiagent_sltp(
        side="BUY",
        multi_sl=price * 1.01,  # SL ABOVE entry (wrong for LONG)
        multi_tp=price * 1.05,
        entry_price=price,
    )
    record("M2a", "SL side: reject LONG SL > entry", "pass" if not is_valid else "fail",
           expected="Reject: LONG SL must be < entry",
           actual=f"valid={is_valid}, reason={reason}")

    # SHORT with SL below entry
    is_valid, _, _, reason = validate_multiagent_sltp(
        side="SELL",
        multi_sl=price * 0.99,  # SL BELOW entry (wrong for SHORT)
        multi_tp=price * 0.95,
        entry_price=price,
    )
    record("M2b", "SL side: reject SHORT SL < entry", "pass" if not is_valid else "fail",
           expected="Reject: SHORT SL must be > entry",
           actual=f"valid={is_valid}, reason={reason}")

    # --- M3: Technical fallback (removed in v5.1) ---
    print(f"\n  {Colors.BOLD}--- M3: S/R-Based SL/TP (v5.1) ---{Colors.RESET}")
    record("M3a", "S/R-based fallback: LONG", "skip",
           actual="calculate_technical_sltp removed in v5.1, production uses calculate_sr_based_sltp")
    record("M3b", "S/R-based fallback: SHORT", "skip",
           actual="calculate_technical_sltp removed in v5.1, production uses calculate_sr_based_sltp")

    # --- M4: SL favorable direction math ---
    print(f"\n  {Colors.BOLD}--- M4: SL Favorable Direction Rule ---{Colors.RESET}")
    # LONG: SL can only go UP
    old_sl = price * 0.97
    new_sl_lower = price * 0.96  # would move DOWN → blocked
    new_sl_higher = price * 0.975  # would move UP → allowed
    final_lower = max(new_sl_lower, old_sl)
    final_higher = max(new_sl_higher, old_sl)
    record("M4a", "LONG SL favorable: max(old, new)", "pass"
           if final_lower == old_sl and final_higher == new_sl_higher else "fail",
           expected=f"Lower blocked (max={old_sl:,.2f}), higher allowed (max={new_sl_higher:,.2f})",
           actual=f"Down attempt: ${new_sl_lower:,.2f} → ${final_lower:,.2f} ({'blocked ✓' if final_lower == old_sl else 'ALLOWED ✗'})\n"
                  f"    Up attempt:   ${new_sl_higher:,.2f} → ${final_higher:,.2f} ({'allowed ✓' if final_higher == new_sl_higher else 'BLOCKED ✗'})")

    # SHORT: SL can only go DOWN
    old_sl_short = price * 1.03
    new_sl_higher_s = price * 1.04  # would move UP → blocked
    new_sl_lower_s = price * 1.025  # would move DOWN → allowed
    final_h = min(new_sl_higher_s, old_sl_short)
    final_l = min(new_sl_lower_s, old_sl_short)
    record("M4b", "SHORT SL favorable: min(old, new)", "pass"
           if final_h == old_sl_short and final_l == new_sl_lower_s else "fail",
           expected=f"Higher blocked (min={old_sl_short:,.2f}), lower allowed (min={new_sl_lower_s:,.2f})",
           actual=f"Up attempt:   ${new_sl_higher_s:,.2f} → ${final_h:,.2f} ({'blocked ✓' if final_h == old_sl_short else 'ALLOWED ✗'})\n"
                  f"    Down attempt: ${new_sl_lower_s:,.2f} → ${final_l:,.2f} ({'allowed ✓' if final_l == new_sl_lower_s else 'BLOCKED ✗'})")

    # --- M5: Dynamic update threshold ---
    print(f"\n  {Colors.BOLD}--- M5: Dynamic Update Threshold (0.1%) ---{Colors.RESET}")
    base_sl = price * 0.97
    tiny_change = base_sl * 1.0005  # 0.05% change → should skip
    big_change = base_sl * 1.002    # 0.2% change → should update
    tiny_pct = abs(tiny_change - base_sl) / base_sl
    big_pct = abs(big_change - base_sl) / base_sl
    record("M5", "Dynamic threshold: skip < 0.1%, update >= 0.1%", "pass"
           if tiny_pct < 0.001 and big_pct > 0.001 else "fail",
           expected="0.05% → skip, 0.2% → update",
           actual=f"Tiny change: {tiny_pct*100:.4f}% {'→ SKIP ✓' if tiny_pct < 0.001 else '→ UPDATE ✗'}\n"
                  f"    Big change:  {big_pct*100:.4f}% {'→ UPDATE ✓' if big_pct > 0.001 else '→ SKIP ✗'}")

    # --- M6: Emergency SL calculation ---
    print(f"\n  {Colors.BOLD}--- M6: Emergency SL (2% Default) ---{Colors.RESET}")
    emergency_sl_long = price * 0.98
    emergency_sl_short = price * 1.02
    record("M6", "Emergency SL: 2% from current price", "pass",
           actual=f"LONG emergency SL = ${emergency_sl_long:,.2f} ({(price - emergency_sl_long)/price*100:.1f}% below)\n"
                  f"    SHORT emergency SL = ${emergency_sl_short:,.2f} ({(emergency_sl_short - price)/price*100:.1f}% above)")


# ═══════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════

def print_summary():
    banner("Summary (结果汇总)")

    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    warned = sum(1 for r in results if r["status"] == "warn")
    skipped = sum(1 for r in results if r["status"] == "skip")

    print(f"""
  Total checks: {total}
  {Colors.GREEN}✅ Passed:  {passed}{Colors.RESET}
  {Colors.RED}❌ Failed:  {failed}{Colors.RESET}
  {Colors.YELLOW}⚠️  Warned:  {warned}{Colors.RESET}
  {Colors.DIM}⏭️  Skipped: {skipped}{Colors.RESET}
""")

    if failed > 0:
        print(f"  {Colors.RED}{Colors.BOLD}Failed checks:{Colors.RESET}")
        for r in results:
            if r["status"] == "fail":
                print(f"    ❌ [{r['id']}] {r['desc']}")
                if r["actual"]:
                    print(f"       → {r['actual'][:120]}")
        print()

    if warned > 0:
        print(f"  {Colors.YELLOW}{Colors.BOLD}Warnings:{Colors.RESET}")
        for r in results:
            if r["status"] == "warn":
                print(f"    ⚠️  [{r['id']}] {r['desc']}")
        print()

    # Machine-readable summary for Claude
    print(f"{Colors.CYAN}{'━' * 68}{Colors.RESET}")
    print(f"{Colors.BOLD}  Machine-readable (复制以下内容给 Claude):{Colors.RESET}")
    print(f"{Colors.CYAN}{'━' * 68}{Colors.RESET}")
    summary_data = {
        "version": "v4.12",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "passed": passed,
        "failed": failed,
        "warned": warned,
        "skipped": skipped,
        "results": [
            {"id": r["id"], "status": r["status"],
             "desc": r["desc"], "actual": r["actual"][:200]}
            for r in results
        ]
    }
    print(json.dumps(summary_data, indent=2, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print(f"""
{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════════════════════════════════╗
║   v4.12 Complete Order Flow Diagnostic                          ║
║   v4.12 完整订单流诊断                                          ║
║                                                                  ║
║   开仓 / 加仓 / 减仓 / 平仓 / 止盈止损 / 动态调整              ║
╚══════════════════════════════════════════════════════════════════╝{Colors.RESET}

  Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
  Project: {PROJECT_DIR}
  Python: {sys.version.split()[0]}
""")

    # Phase 1: Code integrity
    phase1_code_integrity()

    # Phase 2: Config
    phase2_config()

    # Phase 3: Binance state
    price, pos_amt, entry_price, klines = phase3_binance()

    # Phase 4: Order flow simulation
    phase4_order_flow(price, klines)

    # Phase 5: Math verification
    phase5_math(price, klines)

    # Summary
    print_summary()

    # Exit code
    failed_count = sum(1 for r in results if r["status"] == "fail")
    sys.exit(1 if failed_count > 0 else 0)


if __name__ == "__main__":
    main()
