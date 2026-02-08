"""
Code Integrity Checker Module (v4.12)

Static source code analysis without executing the strategy.
Validates critical code patterns using regex/AST inspection.

Checks:
  P1.1:  Bracket order has no emulation_trigger
  P1.2:  on_stop preserves SL/TP orders (selective cancel)
  P1.3:  _recover_sltp_on_start exists and called in on_start
  P1.4:  _dynamic_sltp_update exists and called from on_timer
  P1.5:  Reduce path uses _validate_sltp_for_entry + SL favorable
  P1.6:  Add path uses _replace_sltp_orders
  P1.7:  Unified SL/TP validation (_validate_sltp_for_entry)
  P1.8:  Dynamic SL/TP safety rules
  P1.9:  on_order_filled OCO management
  P1.10: Emergency SL method exists
"""

import re
from pathlib import Path
from typing import List, Optional, Tuple

from .base import DiagnosticContext, DiagnosticStep, print_box


def _extract_method(source_lines: List[str], method_name: str) -> Optional[str]:
    """Extract a method's source from lines, using indentation."""
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
    end_idx = start_idx + 1
    passed_signature = False
    while end_idx < len(source_lines):
        line = source_lines[end_idx]
        stripped = line.strip()
        if stripped == "":
            end_idx += 1
            continue
        curr_indent = len(line) - len(line.lstrip())
        if not passed_signature:
            if stripped.endswith("):") or stripped.endswith(") ->"):
                passed_signature = True
            if source_lines[start_idx].strip().endswith("):"):
                passed_signature = True
            end_idx += 1
            continue
        if curr_indent <= base_indent and (
            stripped.startswith("def ") or
            stripped.startswith("class ") or
            stripped.startswith("@")
        ):
            break
        end_idx += 1
    return "\n".join(source_lines[start_idx:end_idx])


class CodeIntegrityChecker(DiagnosticStep):
    """
    v4.12 静态代码完整性检查

    Uses regex/AST to inspect deepseek_strategy.py source code
    without executing it. Validates all v4.12 order flow safety patterns.
    """

    name = "v4.12 代码完整性检查 (静态分析)"

    def __init__(self, ctx: DiagnosticContext):
        super().__init__(ctx)
        self._results: List[dict] = []

    def run(self) -> bool:
        print()
        print_box("v4.12 Code Integrity (静态代码检查)", 65)
        print()

        strategy_path = self.ctx.project_root / "strategy" / "deepseek_strategy.py"
        if not strategy_path.exists():
            self._record("P1.0", "Strategy file exists", False,
                         actual=f"{strategy_path} not found")
            return False

        source = strategy_path.read_text()
        lines = source.splitlines()

        self._check_bracket_no_emulation(lines)
        self._check_on_stop_preserves_sltp(lines)
        self._check_recover_sltp_on_start(source, lines)
        self._check_dynamic_sltp_update(source, lines)
        self._check_reduce_path(lines)
        self._check_add_path_replace(source, lines)
        self._check_validate_sltp_for_entry(lines)
        self._check_dynamic_sltp_safety(lines)
        self._check_on_order_filled_oco(lines)
        self._check_emergency_sl(source)

        # Summary
        passed = sum(1 for r in self._results if r["pass"])
        total = len(self._results)
        failed = total - passed

        print()
        print(f"  代码完整性: {passed}/{total} 通过", end="")
        if failed > 0:
            print(f", {failed} 失败")
            for r in self._results:
                if not r["pass"]:
                    self.ctx.add_error(f"[{r['id']}] {r['desc']}: {r.get('actual', '')}")
        else:
            print(" ✅")

        # Store results for JSON output
        if not hasattr(self.ctx, 'code_integrity_results'):
            self.ctx.code_integrity_results = []
        self.ctx.code_integrity_results = self._results

        return failed == 0

    def _record(self, check_id: str, desc: str, passed: bool,
                expected: str = "", actual: str = "", detail: str = ""):
        """Record and print a check result."""
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  [{check_id}] {desc}")
        if expected:
            print(f"    Expected: {expected}")
        if actual:
            print(f"    Actual:   {actual}")
        print(f"    Result:   {status}")
        if detail:
            for line in detail.split("\n"):
                print(f"    {line}")
        print()
        self._results.append({
            "id": check_id, "desc": desc, "pass": passed,
            "expected": expected, "actual": actual,
        })

    # ── P1.1: Bracket order has no emulation_trigger ──

    def _check_bracket_no_emulation(self, lines: List[str]):
        bracket_method = _extract_method(lines, "_submit_bracket_order")
        if bracket_method is None:
            self._record("P1.1", "Bracket order: no emulation_trigger", False,
                         actual="_submit_bracket_order method not found")
            return
        code_lines = [l for l in bracket_method.splitlines()
                      if l.strip() and not l.strip().startswith("#")]
        has_emulation = any("emulation_trigger" in l and "=" in l
                            for l in code_lines)
        has_bracket = "order_factory.bracket" in bracket_method
        if has_emulation:
            self._record("P1.1", "Bracket order: no emulation_trigger", False,
                         expected="emulation_trigger removed (v4.12)",
                         actual="emulation_trigger= still present as active code",
                         detail="SL/TP 仍在本地模拟, 崩溃会丢失!")
        else:
            self._record("P1.1", "Bracket order: no emulation_trigger",
                         has_bracket,
                         expected="order_factory.bracket() without emulation_trigger",
                         actual=f"emulation_trigger removed, bracket call: "
                                f"{'found' if has_bracket else 'NOT found'}")

    # ── P1.2: on_stop preserves SL/TP ──

    def _check_on_stop_preserves_sltp(self, lines: List[str]):
        on_stop = _extract_method(lines, "on_stop")
        if on_stop is None:
            self._record("P1.2", "on_stop: preserves SL/TP orders", False,
                         actual="on_stop method not found")
            return
        has_selective = "is_reduce_only" in on_stop
        main_path_cancel = False
        in_except = False
        for line in on_stop.splitlines():
            stripped = line.strip()
            if "except" in stripped:
                in_except = True
            if "cancel_all_orders" in stripped and not in_except:
                main_path_cancel = True
                break
        if has_selective and not main_path_cancel:
            self._record("P1.2", "on_stop: preserves SL/TP orders", True,
                         expected="Selective cancel (skip reduce_only), cancel_all only in fallback",
                         actual="is_reduce_only check present, cancel_all_orders only in except block")
        elif main_path_cancel:
            self._record("P1.2", "on_stop: preserves SL/TP orders", False,
                         expected="cancel_all_orders NOT in main path",
                         actual="cancel_all_orders in main execution path — SL/TP will be lost!")
        else:
            self._record("P1.2", "on_stop: preserves SL/TP orders", False,
                         actual=f"selective={has_selective}, cancel_all_main={main_path_cancel}")

    # ── P1.3: _recover_sltp_on_start ──

    def _check_recover_sltp_on_start(self, source: str, lines: List[str]):
        has_def = "def _recover_sltp_on_start" in source
        on_start = _extract_method(lines, "on_start")
        has_call = "_recover_sltp_on_start()" in (on_start or "")
        self._record("P1.3", "on_start: crash recovery (_recover_sltp_on_start)",
                     has_def and has_call,
                     expected="Method defined + called in on_start",
                     actual=f"defined={has_def}, called_in_on_start={has_call}")

    # ── P1.4: _dynamic_sltp_update ──

    def _check_dynamic_sltp_update(self, source: str, lines: List[str]):
        has_def = "def _dynamic_sltp_update" in source
        on_timer = _extract_method(lines, "on_timer")
        has_call = "_dynamic_sltp_update()" in (on_timer or "")
        self._record("P1.4", "on_timer: dynamic SL/TP update",
                     has_def and has_call,
                     expected="Method defined + called in on_timer",
                     actual="Both present — SL/TP 每 15 分钟动态调整"
                            if (has_def and has_call)
                            else f"defined={has_def}, called_in_on_timer={has_call}")

    # ── P1.5: Reduce path ──

    def _check_reduce_path(self, lines: List[str]):
        recreate = _extract_method(lines, "_recreate_sltp_after_reduce")
        if recreate is None:
            self._record("P1.5", "Reduce path: S/R recalculation + favorable SL", False,
                         actual="_recreate_sltp_after_reduce not found")
            return
        uses_validate = "_validate_sltp_for_entry" in recreate
        has_favorable = any(x in recreate for x in [
            "max(new_sl_price", "min(new_sl_price",
            "max(new_sl", "min(new_sl",
        ])
        self._record("P1.5", "Reduce path: S/R recalculation + favorable SL",
                     uses_validate and has_favorable,
                     expected="_validate_sltp_for_entry + SL favorable direction rule",
                     actual=f"validate={uses_validate}, favorable_rule={has_favorable}")

    # ── P1.6: Add path _replace_sltp_orders ──

    def _check_add_path_replace(self, source: str, lines: List[str]):
        has_replace = "def _replace_sltp_orders" in source
        manage = _extract_method(lines, "_manage_existing_position") or ""
        add = _extract_method(lines, "_add_to_position") or ""
        used = "_replace_sltp_orders" in manage or "_replace_sltp_orders" in add
        if not used:
            for i, l in enumerate(lines):
                if "_replace_sltp_orders" in l and "add" in "\n".join(lines[max(0, i - 20):i + 1]).lower():
                    used = True
                    break
        self._record("P1.6", "Add path: _replace_sltp_orders (price + qty)",
                     has_replace and used,
                     expected="cancel+recreate SL/TP at new prices after adding",
                     actual="Method defined and used in add-to-position path"
                            if (has_replace and used)
                            else f"defined={has_replace}, used_in_add={used}")

    # ── P1.7: _validate_sltp_for_entry ──

    def _check_validate_sltp_for_entry(self, lines: List[str]):
        method = _extract_method(lines, "_validate_sltp_for_entry")
        if method is None:
            self._record("P1.7", "Unified SL/TP validation (_validate_sltp_for_entry)", False,
                         actual="Method not found")
            return
        has_rr = "validate_multiagent_sltp" in method
        has_fallback = "calculate_technical_sltp" in method
        has_price_chain = "binance_account" in method or "latest_price_data" in method
        ok = has_rr and has_fallback
        self._record("P1.7", "Unified SL/TP validation (_validate_sltp_for_entry)", ok,
                     expected="validate_multiagent_sltp + calculate_technical_sltp fallback + price chain",
                     actual=f"AI R/R check={has_rr}, tech fallback={has_fallback}, "
                            f"price_chain={has_price_chain}")

    # ── P1.8: Dynamic SL/TP safety ──

    def _check_dynamic_sltp_safety(self, lines: List[str]):
        method = _extract_method(lines, "_dynamic_sltp_update")
        if method is None:
            self._record("P1.8", "Dynamic SL/TP: safety rules", False,
                         actual="_dynamic_sltp_update not found")
            return
        has_favorable = "max(new_sl" in method or "max(final_sl" in method
        has_trailing = "trailing_active" in method
        has_threshold = "0.001" in method
        has_replace = "_replace_sltp_orders" in method
        ok = all([has_favorable, has_trailing, has_threshold, has_replace])
        self._record("P1.8", "Dynamic SL/TP: safety rules", ok,
                     expected="SL favorable + trailing coexist + 0.1% threshold + replace_sltp",
                     actual=f"favorable_sl={has_favorable}, trailing={has_trailing}, "
                            f"threshold={has_threshold}, replace={has_replace}")

    # ── P1.9: on_order_filled OCO ──

    def _check_on_order_filled_oco(self, lines: List[str]):
        method = _extract_method(lines, "on_order_filled")
        if method:
            has_oco = "reduce_only" in method or "cancel" in method.lower()
            self._record("P1.9", "on_order_filled: manual OCO management", has_oco,
                         expected="SL fills → cancel TP, TP fills → cancel SL",
                         actual=f"OCO logic present={has_oco}")
        else:
            self._record("P1.9", "on_order_filled: manual OCO management", False,
                         actual="on_order_filled not found")

    # ── P1.10: Emergency SL ──

    def _check_emergency_sl(self, source: str):
        has_emergency = "def _submit_emergency_sl" in source
        self._record("P1.10", "Emergency SL method exists", has_emergency,
                     expected="_submit_emergency_sl defined",
                     actual=f"Present={has_emergency}")
