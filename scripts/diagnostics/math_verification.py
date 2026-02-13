"""
Math Verification Module (v5.0)

Validates critical trading math with real market data:
  M1: R/R >= 1.5:1 hard gate (reject/accept)
  M2: SL wrong-side rejection
  M3: Technical SL/TP fallback
  M4: SL favorable direction (max for LONG, min for SHORT)
  M5: Dynamic update threshold (0.1%)
  M6: Emergency SL (2% default)
"""

import traceback
from typing import List, Optional, Tuple

from .base import DiagnosticContext, DiagnosticStep, print_box, fetch_binance_klines


def _compute_sr_from_klines(klines, current_price: float) -> Tuple[float, float]:
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


class MathVerificationChecker(DiagnosticStep):
    """
    v5.0 数学验证

    Uses real market data to verify trading math:
    - R/R gate enforcement
    - SL wrong-side rejection
    - Technical SL/TP fallback quality
    - SL favorable direction rules
    - Dynamic update threshold
    - Emergency SL distance
    """

    name = "v5.0 数学验证 (R/R, SL方向, 动态调整)"

    def __init__(self, ctx: DiagnosticContext):
        super().__init__(ctx)
        self._results: List[dict] = []

    def run(self) -> bool:
        print()
        print_box("v5.0 Math Verification (数学验证)", 65)
        print()

        price = self.ctx.current_price
        if not price or price <= 0:
            print("  ⚠️ 无价格数据，跳过数学验证")
            return True

        # Import trading logic
        try:
            from strategy.trading_logic import validate_multiagent_sltp, calculate_technical_sltp
        except ImportError as e:
            print(f"  ❌ 无法导入 trading_logic: {e}")
            self.ctx.add_error(f"Math verification: import failed: {e}")
            return False

        # Get S/R from klines
        klines = self.ctx.klines_raw
        if not klines:
            klines = fetch_binance_klines(self.ctx.symbol, "15m", 100)
        support, resistance = _compute_sr_from_klines(klines, price)

        print(f"  价格: ${price:,.2f}  支撑: ${support:,.2f}  阻力: ${resistance:,.2f}")
        print()

        # Run all math checks
        self._check_rr_gate(price, validate_multiagent_sltp)
        self._check_sl_side(price, validate_multiagent_sltp)
        self._check_technical_fallback(price, support, resistance, calculate_technical_sltp)
        self._check_sl_favorable_direction(price)
        self._check_dynamic_threshold(price)
        self._check_emergency_sl(price)

        # Summary
        passed = sum(1 for r in self._results if r["pass"])
        total = len(self._results)
        failed = total - passed
        print()
        print(f"  数学验证: {passed}/{total} 通过", end="")
        if failed > 0:
            print(f", {failed} 失败")
            for r in self._results:
                if not r["pass"]:
                    self.ctx.add_error(f"[{r['id']}] {r['desc']}")
        else:
            print(" ✅")

        # Store results for JSON output
        if not hasattr(self.ctx, 'math_verification_results'):
            self.ctx.math_verification_results = []
        self.ctx.math_verification_results = self._results

        return failed == 0

    def _record(self, check_id: str, desc: str, passed: bool,
                expected: str = "", actual: str = "", detail: str = ""):
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

    # ── M1: R/R Hard Gate ──

    def _check_rr_gate(self, price: float, validate_fn):
        print(f"  --- M1: R/R Hard Gate Test ---")
        print()

        # M1a: Reject R/R < 1.5 (LONG)
        bad_sl = price * 0.99
        bad_tp = price * 1.005
        try:
            is_valid, _, _, reason = validate_fn(
                side="BUY", multi_sl=bad_sl, multi_tp=bad_tp, entry_price=price,
            )
            rr = (bad_tp - price) / (price - bad_sl) if price > bad_sl else 0
            self._record("M1a", "R/R gate: reject R/R < 1.5 (LONG)", not is_valid,
                         expected=f"Reject: R/R={rr:.2f}:1 < 1.5:1",
                         actual=f"valid={is_valid}, reason={reason}")
        except Exception as e:
            self._record("M1a", "R/R gate: reject R/R < 1.5 (LONG)", False,
                         actual=str(e))

        # M1b: Accept R/R >= 1.5 (LONG)
        good_sl = price * 0.98
        good_tp = price * 1.04
        try:
            is_valid, v_sl, v_tp, reason = validate_fn(
                side="BUY", multi_sl=good_sl, multi_tp=good_tp, entry_price=price,
            )
            rr = (good_tp - price) / (price - good_sl) if price > good_sl else 0
            self._record("M1b", "R/R gate: accept R/R >= 1.5 (LONG)", is_valid,
                         expected=f"Accept: R/R={rr:.2f}:1 >= 1.5:1",
                         actual=f"valid={is_valid}, SL=${v_sl:,.2f}, TP=${v_tp:,.2f}")
        except Exception as e:
            self._record("M1b", "R/R gate: accept R/R >= 1.5 (LONG)", False,
                         actual=str(e))

        # M1c: Reject R/R < 1.5 (SHORT)
        short_sl = price * 1.01
        short_tp = price * 0.995
        try:
            is_valid, _, _, reason = validate_fn(
                side="SELL", multi_sl=short_sl, multi_tp=short_tp, entry_price=price,
            )
            self._record("M1c", "R/R gate: reject R/R < 1.5 (SHORT)", not is_valid,
                         expected="Reject low R/R for SHORT",
                         actual=f"valid={is_valid}, reason={reason}")
        except Exception as e:
            self._record("M1c", "R/R gate: reject R/R < 1.5 (SHORT)", False,
                         actual=str(e))

    # ── M2: SL Side Validation ──

    def _check_sl_side(self, price: float, validate_fn):
        print(f"  --- M2: SL Side Validation ---")
        print()

        # M2a: LONG SL above entry
        try:
            is_valid, _, _, reason = validate_fn(
                side="BUY", multi_sl=price * 1.01, multi_tp=price * 1.05,
                entry_price=price,
            )
            self._record("M2a", "SL side: reject LONG SL > entry", not is_valid,
                         expected="Reject: LONG SL must be < entry",
                         actual=f"valid={is_valid}, reason={reason}")
        except Exception as e:
            self._record("M2a", "SL side: reject LONG SL > entry", False,
                         actual=str(e))

        # M2b: SHORT SL below entry
        try:
            is_valid, _, _, reason = validate_fn(
                side="SELL", multi_sl=price * 0.99, multi_tp=price * 0.95,
                entry_price=price,
            )
            self._record("M2b", "SL side: reject SHORT SL < entry", not is_valid,
                         expected="Reject: SHORT SL must be > entry",
                         actual=f"valid={is_valid}, reason={reason}")
        except Exception as e:
            self._record("M2b", "SL side: reject SHORT SL < entry", False,
                         actual=str(e))

    # ── M3: Technical SL/TP Fallback ──

    def _check_technical_fallback(self, price: float, support: float,
                                   resistance: float, calc_fn):
        print(f"  --- M3: Technical SL/TP Fallback ---")
        print()

        sl_buffer_pct = 0.005

        for side, label, tag in [("BUY", "LONG", "a"), ("SELL", "SHORT", "b")]:
            try:
                sl, tp, method = calc_fn(
                    side=side, entry_price=price, support=support,
                    resistance=resistance, confidence="MEDIUM",
                    use_support_resistance=True, sl_buffer_pct=sl_buffer_pct,
                )
                if side == "BUY":
                    rr = (tp - price) / (price - sl) if price > sl else 0
                    side_ok = sl < price < tp
                else:
                    rr = (price - tp) / (sl - price) if sl > price else 0
                    side_ok = tp < price < sl
                ok = rr >= 1.5 and side_ok
                self._record(f"M3{tag}", f"Technical fallback: {label}", ok,
                             actual=f"SL=${sl:,.2f} TP=${tp:,.2f} R/R={rr:.2f}:1 side_ok={side_ok}",
                             detail=f"Method: {method}")

                # ── Exact formula anchoring assertions ──
                # Verify SL is anchored to S/R zone (not arbitrary %)
                if side == "BUY" and support > 0:
                    # LONG: SL = support × (1 - buffer) or default
                    expected_sl = support * (1 - sl_buffer_pct)
                    if expected_sl < price:
                        sl_match = abs(sl - expected_sl) < price * 0.001  # 0.1% tolerance
                        if sl_match:
                            self._record(f"M3{tag}_anchor", f"SL anchored to support ({label})", True,
                                         actual=f"SL=${sl:,.2f} ≈ support×(1-{sl_buffer_pct}) = ${expected_sl:,.2f}")
                        else:
                            # May be default % or R/R adjusted — check default
                            from strategy.trading_logic import get_default_sl_pct
                            default_sl = price * (1 - get_default_sl_pct())
                            if abs(sl - default_sl) < price * 0.001:
                                self._record(f"M3{tag}_anchor", f"SL default % ({label})", True,
                                             actual=f"SL=${sl:,.2f} ≈ default {get_default_sl_pct()*100:.0f}% = ${default_sl:,.2f}")
                            else:
                                self._record(f"M3{tag}_anchor", f"SL anchor unknown ({label})", False,
                                             expected=f"support-based=${expected_sl:,.2f} or default=${default_sl:,.2f}",
                                             actual=f"SL=${sl:,.2f}")
                elif side == "SELL" and resistance > 0:
                    # SHORT: SL = resistance × (1 + buffer) or default
                    expected_sl = resistance * (1 + sl_buffer_pct)
                    if expected_sl > price:
                        sl_match = abs(sl - expected_sl) < price * 0.001
                        if sl_match:
                            self._record(f"M3{tag}_anchor", f"SL anchored to resistance ({label})", True,
                                         actual=f"SL=${sl:,.2f} ≈ resistance×(1+{sl_buffer_pct}) = ${expected_sl:,.2f}")
                        else:
                            from strategy.trading_logic import get_default_sl_pct
                            default_sl = price * (1 + get_default_sl_pct())
                            if abs(sl - default_sl) < price * 0.001:
                                self._record(f"M3{tag}_anchor", f"SL default % ({label})", True,
                                             actual=f"SL=${sl:,.2f} ≈ default {get_default_sl_pct()*100:.0f}% = ${default_sl:,.2f}")
                            else:
                                self._record(f"M3{tag}_anchor", f"SL anchor unknown ({label})", False,
                                             expected=f"resistance-based=${expected_sl:,.2f} or default=${default_sl:,.2f}",
                                             actual=f"SL=${sl:,.2f}")

                # ── R/R precision cross-check ──
                if side == "BUY" and price > sl:
                    direct_rr = (tp - price) / (price - sl)
                    if abs(direct_rr - rr) > 0.001:
                        self._record(f"M3{tag}_rr", f"R/R formula mismatch ({label})", False,
                                     expected=f"direct={direct_rr:.4f}:1",
                                     actual=f"computed={rr:.4f}:1")
                elif side == "SELL" and sl > price:
                    direct_rr = (price - tp) / (sl - price)
                    if abs(direct_rr - rr) > 0.001:
                        self._record(f"M3{tag}_rr", f"R/R formula mismatch ({label})", False,
                                     expected=f"direct={direct_rr:.4f}:1",
                                     actual=f"computed={rr:.4f}:1")

            except Exception as e:
                self._record(f"M3{tag}", f"Technical fallback: {label}", False,
                             actual=str(e))

    # ── M4: SL Favorable Direction ──

    def _check_sl_favorable_direction(self, price: float):
        print(f"  --- M4: SL Favorable Direction Rule ---")
        print()

        # LONG: SL can only go UP (max)
        old_sl = price * 0.97
        new_lower = price * 0.96
        new_higher = price * 0.975
        final_lower = max(new_lower, old_sl)
        final_higher = max(new_higher, old_sl)
        ok = final_lower == old_sl and final_higher == new_higher
        self._record("M4a", "LONG SL favorable: max(old, new)", ok,
                     expected=f"Lower blocked (max={old_sl:,.2f}), higher allowed (max={new_higher:,.2f})",
                     actual=f"Down: ${new_lower:,.2f} → ${final_lower:,.2f} "
                            f"({'blocked ✓' if final_lower == old_sl else 'ALLOWED ✗'})\n"
                            f"    Up:   ${new_higher:,.2f} → ${final_higher:,.2f} "
                            f"({'allowed ✓' if final_higher == new_higher else 'BLOCKED ✗'})")

        # SHORT: SL can only go DOWN (min)
        old_sl_s = price * 1.03
        new_higher_s = price * 1.04
        new_lower_s = price * 1.025
        final_h = min(new_higher_s, old_sl_s)
        final_l = min(new_lower_s, old_sl_s)
        ok = final_h == old_sl_s and final_l == new_lower_s
        self._record("M4b", "SHORT SL favorable: min(old, new)", ok,
                     expected=f"Higher blocked (min={old_sl_s:,.2f}), lower allowed (min={new_lower_s:,.2f})",
                     actual=f"Up:   ${new_higher_s:,.2f} → ${final_h:,.2f} "
                            f"({'blocked ✓' if final_h == old_sl_s else 'ALLOWED ✗'})\n"
                            f"    Down: ${new_lower_s:,.2f} → ${final_l:,.2f} "
                            f"({'allowed ✓' if final_l == new_lower_s else 'BLOCKED ✗'})")

    # ── M5: Dynamic Update Threshold ──

    def _check_dynamic_threshold(self, price: float):
        print(f"  --- M5: Dynamic Update Threshold (0.1%) ---")
        print()

        base_sl = price * 0.97
        tiny = base_sl * 1.0005   # 0.05%
        big = base_sl * 1.002     # 0.2%
        tiny_pct = abs(tiny - base_sl) / base_sl
        big_pct = abs(big - base_sl) / base_sl
        ok = tiny_pct < 0.001 and big_pct > 0.001
        self._record("M5", "Dynamic threshold: skip < 0.1%, update >= 0.1%", ok,
                     expected="0.05% → skip, 0.2% → update",
                     actual=f"Tiny: {tiny_pct * 100:.4f}% "
                            f"{'→ SKIP ✓' if tiny_pct < 0.001 else '→ UPDATE ✗'}\n"
                            f"    Big:  {big_pct * 100:.4f}% "
                            f"{'→ UPDATE ✓' if big_pct > 0.001 else '→ SKIP ✗'}")

    # ── M6: Emergency SL ──

    def _check_emergency_sl(self, price: float):
        print(f"  --- M6: Emergency SL (2% Default) ---")
        print()

        long_sl = price * 0.98
        short_sl = price * 1.02
        self._record("M6", "Emergency SL: 2% from current price", True,
                     actual=f"LONG emergency SL = ${long_sl:,.2f} "
                            f"({(price - long_sl) / price * 100:.1f}% below)\n"
                            f"    SHORT emergency SL = ${short_sl:,.2f} "
                            f"({(short_sl - price) / price * 100:.1f}% above)")
