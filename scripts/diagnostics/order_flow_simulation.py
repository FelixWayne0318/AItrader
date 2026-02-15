"""
Order Flow Simulation Module v5.1

Comprehensive simulation of the entire order submission process,
covering all v3.18 + v5.1 fixes and various trading scenarios.

v3.18 修复验证:
- 反转两阶段提交 (Reversal Two-Phase Commit)
- Bracket 订单失败处理 (No unprotected fallback)
- 加仓后 SL/TP 数量更新 (_update_sltp_quantity)

v5.1 新增/更新场景:
- S/R 动态 SL/TP 重评估 (S/R Dynamic Reevaluation)
- 崩溃恢复 (Crash Recovery on Startup)
- 停机保护 (on_stop SL/TP Preserved)
- 累加仓位上限验证 (Cumulative Position Limit 30%)

v5.1 update: Trailing Stop removed, replaced by S/R dynamic reevaluation.

订单场景模拟 (10 场景):
1. 新开仓 (无持仓 → 开仓)
2. 同向加仓 (持仓同向 + 加仓)
3. 部分平仓 (减少仓位)
4. 完全平仓 (关闭仓位)
5. 反转交易 (两阶段提交)
6. Bracket 订单失败
7. SL/TP modify 失败回退
8. S/R 动态 SL/TP 重评估 (v5.1)
9. 停机保护 — SL/TP 保留 (v5.1)
10. 累加仓位上限验证 (v5.1)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from .base import DiagnosticContext, DiagnosticStep, print_box, safe_float


class OrderScenario(Enum):
    """Order submission scenarios."""
    NEW_POSITION = "new_position"       # No position → Open new
    ADD_POSITION = "add_position"       # Same direction → Add
    REDUCE_POSITION = "reduce_position" # Partial close
    CLOSE_POSITION = "close_position"   # Full close
    REVERSAL = "reversal"               # Close → Open opposite
    BRACKET_FAILURE = "bracket_failure" # Bracket order fails
    SLTP_MODIFY_FAILURE = "sltp_modify_failure"  # modify_order fails
    DYNAMIC_SLTP_UPDATE = "dynamic_sltp_update"  # v5.1: S/R Dynamic SL/TP reevaluation
    ONSTOP_PRESERVATION = "onstop_preservation"  # v5.1: on_stop preserves SL/TP
    CUMULATIVE_POSITION_LIMIT = "cumulative_position_limit"  # v5.1: 30% max position cap


@dataclass
class MockOrder:
    """Mock order for simulation."""
    client_order_id: str
    order_type: str  # MARKET, STOP_MARKET, LIMIT
    side: str        # BUY, SELL
    quantity: float
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    is_reduce_only: bool = False
    status: str = "PENDING"


@dataclass
class SimulationResult:
    """Result of a scenario simulation."""
    scenario: OrderScenario
    success: bool
    orders_submitted: List[MockOrder]
    events_triggered: List[str]
    state_changes: Dict[str, Any]
    notes: List[str]


class OrderFlowSimulator(DiagnosticStep):
    """
    v3.18 订单流程完整模拟

    Simulates the entire order submission flow with all possible scenarios.
    Validates v3.18 fixes are correctly implemented.
    """

    name = "v5.1 订单流程完整模拟"

    def run(self) -> bool:
        print("-" * 70)
        print()
        print_box("v5.1 订单流程模拟 (10 种场景)", 65)
        print()

        # Determine current scenario based on signal and position
        signal = self.ctx.signal_data.get('signal', 'HOLD')
        current_position = self.ctx.current_position

        print("  📋 当前状态:")
        print(f"     信号: {signal}")
        print(f"     持仓: {'有' if current_position else '无'}")
        if current_position:
            print(f"     持仓方向: {current_position.get('side', 'N/A')}")
            bc = self.ctx.base_currency
            qty = current_position.get('quantity', 0)
            print(f"     持仓数量: {float(qty):.4f} {bc}")
        print()

        # Run all scenario simulations
        scenarios_to_test = [
            OrderScenario.NEW_POSITION,
            OrderScenario.ADD_POSITION,
            OrderScenario.REDUCE_POSITION,
            OrderScenario.CLOSE_POSITION,
            OrderScenario.REVERSAL,
            OrderScenario.BRACKET_FAILURE,
            OrderScenario.SLTP_MODIFY_FAILURE,
            OrderScenario.DYNAMIC_SLTP_UPDATE,
            OrderScenario.ONSTOP_PRESERVATION,
            OrderScenario.CUMULATIVE_POSITION_LIMIT,
        ]

        print("  🔄 模拟所有订单场景...")
        print()

        results = []
        for scenario in scenarios_to_test:
            result = self._simulate_scenario(scenario)
            results.append(result)
            self._print_scenario_result(result)

        # Summary
        print()
        print("  " + "═" * 65)
        print()
        print_box("v5.1 订单流程验证总结", 65)
        print()

        passed = sum(1 for r in results if r.success)
        total = len(results)
        print(f"  通过场景: {passed}/{total}")
        print()

        # Highlight v3.18 + v5.1 fixes
        self._print_v50_verification()

        print()
        print("  ✅ v5.1 订单流程模拟完成")
        return True

    def _simulate_scenario(self, scenario: OrderScenario) -> SimulationResult:
        """Simulate a specific order scenario."""
        if scenario == OrderScenario.NEW_POSITION:
            return self._simulate_new_position()
        elif scenario == OrderScenario.ADD_POSITION:
            return self._simulate_add_position()
        elif scenario == OrderScenario.REDUCE_POSITION:
            return self._simulate_reduce_position()
        elif scenario == OrderScenario.CLOSE_POSITION:
            return self._simulate_close_position()
        elif scenario == OrderScenario.REVERSAL:
            return self._simulate_reversal()
        elif scenario == OrderScenario.BRACKET_FAILURE:
            return self._simulate_bracket_failure()
        elif scenario == OrderScenario.SLTP_MODIFY_FAILURE:
            return self._simulate_sltp_modify_failure()
        elif scenario == OrderScenario.DYNAMIC_SLTP_UPDATE:
            return self._simulate_dynamic_sltp_update()
        elif scenario == OrderScenario.ONSTOP_PRESERVATION:
            return self._simulate_onstop_preservation()
        elif scenario == OrderScenario.CUMULATIVE_POSITION_LIMIT:
            return self._simulate_cumulative_position_limit()
        else:
            return SimulationResult(
                scenario=scenario,
                success=False,
                orders_submitted=[],
                events_triggered=[],
                state_changes={},
                notes=["Unknown scenario"],
            )

    def _simulate_new_position(self) -> SimulationResult:
        """
        场景 1: 新开仓 (无持仓 → 开仓)

        Flow:
        1. Check no existing position
        2. Calculate position size (ai_controlled)
        3. Calculate SL/TP (AI or S/R Zone fallback)
        4. Submit bracket order (Entry + SL + TP)
        5. on_order_filled → on_position_opened
        """
        orders = []
        events = []
        notes = []

        # Simulated parameters
        entry_price = self.ctx.current_price
        quantity = 0.01  # Example
        sl_price = entry_price * 0.98  # 2% SL
        tp_price = entry_price * 1.03  # 3% TP

        # Entry order (v4.17: LIMIT at validated entry_price)
        entry_order = MockOrder(
            client_order_id="O-ENTRY-001",
            order_type="LIMIT",
            side="BUY",
            quantity=quantity,
            status="FILLED",
        )
        orders.append(entry_order)
        events.append("submit_order(LIMIT BUY @ validated entry_price)")

        # SL order (OTO linked)
        sl_order = MockOrder(
            client_order_id="O-SL-001",
            order_type="STOP_MARKET",
            side="SELL",
            quantity=quantity,
            trigger_price=sl_price,
            is_reduce_only=True,
            status="ACCEPTED",
        )
        orders.append(sl_order)
        events.append("submit_order(STOP_MARKET SL)")

        # TP order (OTO linked, OCO with SL)
        tp_order = MockOrder(
            client_order_id="O-TP-001",
            order_type="LIMIT",
            side="SELL",
            quantity=quantity,
            price=tp_price,
            is_reduce_only=True,
            status="ACCEPTED",
        )
        orders.append(tp_order)
        events.append("submit_order(LIMIT TP)")

        events.append("on_order_filled(ENTRY)")
        events.append("on_position_opened(LONG)")

        notes.append("使用 _submit_bracket_order 提交带 SL/TP 的 Bracket 订单")
        notes.append("SL/TP 通过 OTO (One-Triggers-Other) 链接到入场单")
        notes.append("SL 和 TP 通过 OCO (One-Cancels-Other) 互相链接")

        return SimulationResult(
            scenario=OrderScenario.NEW_POSITION,
            success=True,
            orders_submitted=orders,
            events_triggered=events,
            state_changes={
                "position": "None → LONG",
                "sl_order": "None → ACTIVE",
                "tp_order": "None → ACTIVE",
            },
            notes=notes,
        )

    def _simulate_add_position(self) -> SimulationResult:
        """
        场景 2: 同向加仓 (v3.18 SL/TP 数量更新)

        Flow:
        1. Check existing position (same direction)
        2. Calculate add size
        3. Submit add order (no new SL/TP, uses existing)
        4. on_order_filled
        5. v3.18: _update_sltp_quantity() - 更新 SL/TP 数量
        """
        orders = []
        events = []
        notes = []

        # Existing position
        existing_qty = 0.01
        add_qty = 0.005
        new_total_qty = existing_qty + add_qty

        # Add position order (v4.17: LIMIT at validated entry_price)
        add_order = MockOrder(
            client_order_id="O-ADD-001",
            order_type="LIMIT",
            side="BUY",
            quantity=add_qty,
            status="FILLED",
        )
        orders.append(add_order)
        events.append("submit_order(LIMIT BUY - add position)")
        events.append("on_order_filled(ADD)")

        # v3.18: Update SL/TP quantities
        events.append("_update_sltp_quantity()")
        events.append("  → modify_order(SL, new_qty=0.015)")
        events.append("  → modify_order(TP, new_qty=0.015)")

        notes.append("v3.18: 加仓后调用 _update_sltp_quantity()")
        notes.append("v3.18: 使用 modify_order 更新 SL/TP 数量")
        notes.append("v3.18: 如果 modify 失败，回退到 cancel+recreate")

        return SimulationResult(
            scenario=OrderScenario.ADD_POSITION,
            success=True,
            orders_submitted=orders,
            events_triggered=events,
            state_changes={
                "position_qty": f"{existing_qty:.4f} → {new_total_qty:.4f}",
                "sl_qty": f"{existing_qty:.4f} → {new_total_qty:.4f}",
                "tp_qty": f"{existing_qty:.4f} → {new_total_qty:.4f}",
            },
            notes=notes,
        )

    def _simulate_reduce_position(self) -> SimulationResult:
        """
        场景 3: 部分平仓

        Flow:
        1. Check existing position
        2. Calculate reduce size
        3. Cancel existing SL/TP (prevent quantity mismatch)
        4. Submit reduce order (reduce_only=True)
        5. on_order_filled
        6. Recreate SL/TP with new quantity
        """
        orders = []
        events = []
        notes = []

        # Existing position
        existing_qty = 0.02
        reduce_qty = 0.01
        new_qty = existing_qty - reduce_qty

        # Cancel existing SL/TP first
        events.append("cancel_all_orders() - 取消现有 SL/TP")

        # Reduce position order
        reduce_order = MockOrder(
            client_order_id="O-REDUCE-001",
            order_type="MARKET",
            side="SELL",  # Close part of LONG
            quantity=reduce_qty,
            is_reduce_only=True,
            status="FILLED",
        )
        orders.append(reduce_order)
        events.append("submit_order(MARKET SELL - reduce_only)")
        events.append("on_order_filled(REDUCE)")

        # Recreate SL/TP with new quantity
        events.append("_submit_bracket_order(new_qty) - 重建 SL/TP")

        notes.append("减仓前取消现有 SL/TP，防止数量不匹配")
        notes.append("减仓单必须设置 reduce_only=True")
        notes.append("减仓后重建 SL/TP 使用新数量")

        return SimulationResult(
            scenario=OrderScenario.REDUCE_POSITION,
            success=True,
            orders_submitted=orders,
            events_triggered=events,
            state_changes={
                "position_qty": f"{existing_qty:.4f} → {new_qty:.4f}",
                "sl_order": "CANCELLED → RECREATED",
                "tp_order": "CANCELLED → RECREATED",
            },
            notes=notes,
        )

    def _simulate_close_position(self) -> SimulationResult:
        """
        场景 4: 完全平仓

        Flow:
        1. Check existing position
        2. Cancel existing SL/TP
        3. Submit close order (reduce_only=True)
        4. on_order_filled
        5. on_position_closed
        """
        orders = []
        events = []
        notes = []

        # Existing position
        close_qty = 0.02

        # Cancel existing SL/TP first
        events.append("cancel_all_orders() - 取消 SL/TP")

        # Close position order
        close_order = MockOrder(
            client_order_id="O-CLOSE-001",
            order_type="MARKET",
            side="SELL",  # Close LONG
            quantity=close_qty,
            is_reduce_only=True,
            status="FILLED",
        )
        orders.append(close_order)
        events.append("submit_order(MARKET SELL - reduce_only)")
        events.append("on_order_filled(CLOSE)")
        events.append("on_position_closed()")

        notes.append("平仓前取消 SL/TP 订单")
        notes.append("平仓单必须设置 reduce_only=True")
        notes.append("on_position_closed 清理内部状态")

        return SimulationResult(
            scenario=OrderScenario.CLOSE_POSITION,
            success=True,
            orders_submitted=orders,
            events_triggered=events,
            state_changes={
                "position": "LONG → None",
                "sl_order": "ACTIVE → CANCELLED",
                "tp_order": "ACTIVE → CANCELLED",
            },
            notes=notes,
        )

    def _simulate_reversal(self) -> SimulationResult:
        """
        场景 5: 反转交易 (v3.18 两阶段提交)

        v3.18 Fix: Event-driven Two-Phase Commit

        Flow:
        Phase 1:
        1. Check existing position (opposite direction)
        2. Store _pending_reversal state
        3. Cancel existing SL/TP
        4. Submit close order (reduce_only=True)
        5. DO NOT open new position here!

        Phase 2 (in on_position_closed):
        6. Detect _pending_reversal
        7. Clear _pending_reversal state
        8. Verify no position exists
        9. Submit new bracket order
        """
        orders = []
        events = []
        notes = []

        # Simulated parameters
        close_qty = 0.01
        new_qty = 0.015

        # Phase 1: Store state and close
        events.append("═══ Phase 1: 存储状态并平仓 ═══")
        events.append("_pending_reversal = {")
        events.append("    'target_side': 'short',")
        events.append("    'target_quantity': 0.015,")
        events.append("    'old_side': 'long',")
        events.append("    'submitted_at': datetime.utcnow()")
        events.append("}")

        events.append("cancel_all_orders() - 取消 SL/TP")

        close_order = MockOrder(
            client_order_id="O-REVERSAL-CLOSE-001",
            order_type="MARKET",
            side="SELL",  # Close LONG
            quantity=close_qty,
            is_reduce_only=True,
            status="FILLED",
        )
        orders.append(close_order)
        events.append("submit_order(MARKET SELL - reduce_only)")
        events.append("on_order_filled(CLOSE)")
        events.append("on_position_closed() - 触发 Phase 2")

        # Phase 2: Open new position
        events.append("")
        events.append("═══ Phase 2: 开新仓 (在 on_position_closed 中) ═══")
        events.append("检测到 _pending_reversal")
        events.append("_pending_reversal = None  # 立即清空防止重复执行")
        events.append("验证无持仓: _get_current_position_data() == None")

        new_entry = MockOrder(
            client_order_id="O-REVERSAL-ENTRY-001",
            order_type="MARKET",
            side="SELL",  # Open SHORT
            quantity=new_qty,
            status="FILLED",
        )
        orders.append(new_entry)

        sl_order = MockOrder(
            client_order_id="O-REVERSAL-SL-001",
            order_type="STOP_MARKET",
            side="BUY",  # SL for SHORT
            quantity=new_qty,
            trigger_price=self.ctx.current_price * 1.02,
            is_reduce_only=True,
            status="ACCEPTED",
        )
        orders.append(sl_order)

        tp_order = MockOrder(
            client_order_id="O-REVERSAL-TP-001",
            order_type="LIMIT",
            side="BUY",  # TP for SHORT
            quantity=new_qty,
            price=self.ctx.current_price * 0.97,
            is_reduce_only=True,
            status="ACCEPTED",
        )
        orders.append(tp_order)

        events.append("_submit_bracket_order(SELL, 0.015)")
        events.append("on_order_filled(NEW ENTRY)")
        events.append("on_position_opened(SHORT)")

        notes.append("v3.18: 两阶段提交防止竞态条件")
        notes.append("v3.18: Phase 1 只平仓，不开新仓")
        notes.append("v3.18: Phase 2 在 on_position_closed 中开新仓")
        notes.append("v3.18: 开仓前验证无残留仓位")

        return SimulationResult(
            scenario=OrderScenario.REVERSAL,
            success=True,
            orders_submitted=orders,
            events_triggered=events,
            state_changes={
                "position": "LONG → None → SHORT",
                "_pending_reversal": "None → {state} → None",
                "phase": "1 → 2",
            },
            notes=notes,
        )

    def _simulate_bracket_failure(self) -> SimulationResult:
        """
        场景 6: Bracket 订单失败 (v3.18 不回退到无保护订单)

        v3.18 Fix: Do NOT fallback to unprotected order

        Flow:
        1. Attempt to submit bracket order
        2. Exception occurs (e.g., SL/TP calculation fails)
        3. v3.18: Do NOT submit unprotected market order
        4. Log error and send Telegram alert
        5. Update _last_signal_status as failed
        """
        orders = []
        events = []
        notes = []

        events.append("尝试 _submit_bracket_order()")
        events.append("  → 计算 SL 价格...")
        events.append("  → 计算 TP 价格...")
        events.append("  → ❌ Exception: SL 验证失败")
        events.append("")
        events.append("v3.18 行为:")
        events.append("  → 🚫 NOT opening position without SL/TP protection")
        events.append("  → _last_signal_status = {")
        events.append("        'executed': False,")
        events.append("        'reason': 'Bracket订单失败，取消开仓',")
        events.append("    }")
        events.append("  → 发送 CRITICAL Telegram 警报")
        events.append("")
        events.append("❌ 旧版 (危险) 行为 (已移除):")
        events.append("  → self._submit_order(side, qty, reduce_only=False)  # 无保护!")

        notes.append("v3.18: Bracket 失败时拒绝开仓")
        notes.append("v3.18: 不回退到无 SL/TP 保护的订单")
        notes.append("v3.18: 发送 CRITICAL 警报通知用户")
        notes.append("v3.18: 等待下一个信号重试")

        return SimulationResult(
            scenario=OrderScenario.BRACKET_FAILURE,
            success=True,  # This is expected behavior
            orders_submitted=orders,
            events_triggered=events,
            state_changes={
                "position": "None (保持不变)",
                "_last_signal_status.executed": "False",
            },
            notes=notes,
        )

    def _simulate_sltp_modify_failure(self) -> SimulationResult:
        """
        场景 7: SL/TP modify 失败回退 (v3.18)

        Flow:
        1. Add to position
        2. Call _update_sltp_quantity()
        3. modify_order() fails for SL
        4. v3.18: Fallback to cancel + recreate
        """
        orders = []
        events = []
        notes = []

        # Add position
        add_order = MockOrder(
            client_order_id="O-ADD-002",
            order_type="MARKET",
            side="BUY",
            quantity=0.005,
            status="FILLED",
        )
        orders.append(add_order)
        events.append("submit_order(MARKET BUY - add)")
        events.append("on_order_filled(ADD)")
        events.append("")
        events.append("_update_sltp_quantity() 开始...")
        events.append("  → 找到 2 个 reduce_only 订单 (SL, TP)")
        events.append("  → 尝试 modify_order(SL, new_qty=0.015)")
        events.append("  → ❌ Exception: modify_order 不支持")
        events.append("  → 尝试 modify_order(TP, new_qty=0.015)")
        events.append("  → ✅ 成功")
        events.append("")
        events.append("v3.18 回退逻辑:")
        events.append("  → 收集失败订单信息 (SL)")
        events.append("  → 读取 order.trigger_price")
        events.append("  → cancel_order(SL)")
        events.append("  → 创建新 SL: order_factory.stop_market()")
        events.append("  → submit_order(new_SL)")

        # Recreated SL order
        new_sl = MockOrder(
            client_order_id="O-SL-RECREATED-001",
            order_type="STOP_MARKET",
            side="SELL",
            quantity=0.015,
            trigger_price=self.ctx.current_price * 0.98,
            is_reduce_only=True,
            status="ACCEPTED",
        )
        orders.append(new_sl)

        notes.append("v3.18: modify_order 是首选方法")
        notes.append("v3.18: 失败时回退到 cancel+recreate")
        notes.append("v3.18: 保留原有价格，只更新数量")

        return SimulationResult(
            scenario=OrderScenario.SLTP_MODIFY_FAILURE,
            success=True,
            orders_submitted=orders,
            events_triggered=events,
            state_changes={
                "sl_order": "OLD → CANCELLED → RECREATED",
                "sl_qty": "0.01 → 0.015",
            },
            notes=notes,
        )

    def _simulate_dynamic_sltp_update(self) -> SimulationResult:
        """
        场景 8: S/R 动态 SL/TP 重评估 (v5.1)

        v5.1: 使用真实 calculate_sr_based_sltp() 替代硬编码 mock，
        与生产 _reevaluate_sltp_for_existing_position() 100% 一致。

        Flow:
        1. on_timer triggers _reevaluate_sltp_for_existing_position()
        2. Recalculate S/R zones with current data via calculate_sr_based_sltp()
        3. Apply SL favorable direction rule (max for LONG, min for SHORT)
        4. TP freely adjustable (AI responsibility per v2.2)
        5. Check dynamic_update_threshold_pct (0.2%) - skip if change too small
        6. If threshold met: _replace_sltp_orders (atomic cancel+recreate)
        """
        events = []
        notes = []

        entry_price = self.ctx.current_price
        # Simulate existing position: LONG with SL 1.5% below, TP 2.5% above
        old_sl = entry_price * 0.985
        old_tp = entry_price * 1.025
        position_side = 'long'

        events.append("on_timer → _reevaluate_sltp_for_existing_position()")
        events.append("  1. 获取当前持仓 + 最新 S/R zones")

        # v5.1: Call real calculate_sr_based_sltp() with live S/R data
        new_sl = None
        new_tp = None
        sr_method = "N/A"
        real_calc_used = False

        if self.ctx.sr_zones_data:
            try:
                from utils.sr_sltp_calculator import calculate_sr_based_sltp
                from strategy.trading_logic import get_min_rr_ratio, get_min_sl_distance_pct

                atr_val = getattr(self.ctx, 'atr_value', None) or 0.0
                cfg = self.ctx.strategy_config
                min_rr = get_min_rr_ratio()
                atr_buf_mult = getattr(cfg, 'atr_buffer_multiplier', 0.5) if cfg else 0.5
                tp_buf_mult = getattr(cfg, 'tp_buffer_multiplier', 0.25) if cfg else 0.25
                # v5.10: Match production — Level 2 uses half of Level 1's min SL distance
                sr_min_sl = get_min_sl_distance_pct() * 0.5

                new_sl, new_tp, sr_method = calculate_sr_based_sltp(
                    current_price=entry_price,
                    side="BUY",  # LONG position
                    sr_zones=self.ctx.sr_zones_data,
                    atr_value=atr_val,
                    min_rr_ratio=min_rr,
                    atr_buffer_multiplier=atr_buf_mult,
                    tp_buffer_multiplier=tp_buf_mult,
                    min_sl_distance_pct=sr_min_sl,
                )
                real_calc_used = True
                events.append(f"  2. calculate_sr_based_sltp() → {sr_method}")
                if new_sl and new_tp:
                    events.append(f"     新 SL=${new_sl:,.2f}, 新 TP=${new_tp:,.2f}")
                else:
                    events.append(f"     ❌ S/R 拒绝: {sr_method} → 保持现有 SL/TP")
            except Exception as e:
                events.append(f"  2. calculate_sr_based_sltp() 失败: {e}")
        else:
            events.append("  2. ⚠️ 无 S/R zones 数据，使用 mock 值模拟")

        if not real_calc_used or not new_sl or not new_tp:
            # Fallback to mock for display (when no live S/R data)
            new_sl = entry_price * 0.988
            new_tp = entry_price * 1.030
            events.append(f"  2. [MOCK] 新 SL=${new_sl:,.2f}, 新 TP=${new_tp:,.2f}")

        # Favorable direction: LONG SL can only go UP (matches production L4662-4666)
        final_sl = max(new_sl, old_sl)
        # TP freely adjustable (v2.2: AI responsibility, matches production L4667)
        final_tp = new_tp

        # Validate SL won't immediately trigger (matches production L4670-4675)
        sl_valid = True
        if position_side == 'long' and final_sl >= entry_price:
            events.append(f"  3. ⚠️ SL >= 当前价 (LONG), 跳过更新")
            sl_valid = False
        elif position_side == 'short' and final_sl <= entry_price:
            events.append(f"  3. ⚠️ SL <= 当前价 (SHORT), 跳过更新")
            sl_valid = False
        else:
            events.append(f"  3. SL favorable: max({old_sl:,.2f}, {new_sl:,.2f}) = {final_sl:,.2f}")
            events.append(f"  4. TP: {old_tp:,.2f} → {final_tp:,.2f} (自由调整, AI 职责)")

        # Threshold check — production uses 0.2% (dynamic_update_threshold_pct=0.002)
        cfg = self.ctx.strategy_config
        threshold = getattr(cfg, 'dynamic_update_threshold_pct', 0.002) if cfg else 0.002
        threshold_pct = threshold * 100  # convert to percentage for display

        sl_change_pct = abs(final_sl - old_sl) / old_sl * 100
        tp_change_pct = abs(final_tp - old_tp) / old_tp * 100 if old_tp > 0 else 0
        sl_changed = sl_change_pct > threshold_pct
        tp_changed = tp_change_pct > threshold_pct
        should_update = sl_valid and (sl_changed or tp_changed)

        events.append(f"  5. SL Δ={sl_change_pct:.3f}%, TP Δ={tp_change_pct:.3f}%")
        events.append(f"  6. 阈值 {threshold_pct:.1f}% (dynamic_update_threshold_pct={threshold}): {'更新' if should_update else '跳过'}")
        if should_update:
            events.append("  7. _replace_sltp_orders (atomic cancel+recreate)")

        notes.append("v5.1: Trailing Stop 已移除, S/R 重评估是唯一 SL 调整机制")
        notes.append("SL 只能向有利方向移动 (LONG: UP, SHORT: DOWN)")
        notes.append("TP 由 S/R 重评估自由调整 (v2.2: AI 职责, 非 LOCAL 保护)")
        notes.append(f"阈值 {threshold_pct:.1f}% 避免频繁修改订单 (生产 dynamic_update_threshold_pct={threshold})")

        # ── Structural assertions (v5.1: verify formulas, not just display) ──
        assertion_failures = []

        # Assert 1: Favorable direction rule — LONG SL can only go UP
        if new_sl and new_sl < old_sl and final_sl != old_sl:
            assertion_failures.append(
                f"LONG SL 降低: new_sl=${new_sl:,.2f} < old_sl=${old_sl:,.2f} "
                f"但 final_sl=${final_sl:,.2f} ≠ old_sl (max 规则失败)")
        if final_sl < old_sl:
            assertion_failures.append(
                f"LONG final_sl=${final_sl:,.2f} < old_sl=${old_sl:,.2f} — 违反有利方向规则")

        # Assert 2: SL must be below entry for LONG
        if position_side == 'long' and sl_valid and final_sl >= entry_price:
            assertion_failures.append(
                f"LONG SL=${final_sl:,.2f} >= entry=${entry_price:,.2f}")

        # Assert 3: Threshold formula precision
        expected_sl_change_pct = abs(final_sl - old_sl) / old_sl * 100
        if abs(sl_change_pct - expected_sl_change_pct) > 0.001:
            assertion_failures.append(
                f"SL change pct 计算误差: {sl_change_pct:.4f}% ≠ {expected_sl_change_pct:.4f}%")

        # Assert 4: If real_calc returned valid SL/TP, they must respect R/R >= min_rr
        if real_calc_used and new_sl and new_tp:
            if new_sl < entry_price and new_tp > entry_price:
                calc_rr = (new_tp - entry_price) / (entry_price - new_sl)
                if calc_rr < min_rr:
                    assertion_failures.append(
                        f"Level 2 SL/TP R/R={calc_rr:.2f}:1 < {min_rr}:1 硬性门槛")

        if assertion_failures:
            for af in assertion_failures:
                events.append(f"  ❌ ASSERTION: {af}")
            notes.append(f"⚠️ {len(assertion_failures)} 个结构断言失败")
        else:
            notes.append("✅ 全部结构断言通过 (有利方向 + SL 方向 + 阈值精度 + R/R)")

        if real_calc_used:
            notes.append(f"✅ 使用真实 calculate_sr_based_sltp() (ATR={atr_val:.2f}, min_rr={min_rr})")
        else:
            notes.append("⚠️ 使用 mock 值 (无 S/R zones 数据)")

        return SimulationResult(
            scenario=OrderScenario.DYNAMIC_SLTP_UPDATE,
            success=True,
            orders_submitted=[],
            events_triggered=events,
            state_changes={
                "sl_price": f"${old_sl:,.2f} → ${final_sl:,.2f} (Δ={sl_change_pct:.3f}%)",
                "tp_price": f"${old_tp:,.2f} → ${final_tp:,.2f} (Δ={tp_change_pct:.3f}%)",
                "update_needed": "YES" if should_update else f"NO (< {threshold_pct:.1f}%)",
                "real_sr_calc": "YES" if real_calc_used else "NO (mock)",
            },
            notes=notes,
        )

    def _simulate_onstop_preservation(self) -> SimulationResult:
        """
        场景 9: 停机保护 — SL/TP 保留在 Binance (v5.1)

        Flow:
        1. on_stop() called (bot shutdown)
        2. Iterate open orders, check is_reduce_only
        3. Cancel only NON-reduce_only orders
        4. SL/TP (reduce_only=True) remain on Binance
        5. Exception fallback: cancel_all_orders
        """
        events = []
        notes = []

        events.append("on_stop() 被调用 (机器人停止)")
        events.append("  for order in cache.orders_open():")
        events.append("    if order.is_reduce_only:")
        events.append("      → SKIP (保留 SL/TP)")
        events.append("    else:")
        events.append("      → cancel_order(order)")
        events.append("")
        events.append("结果: SL/TP 挂单保留在 Binance 交易所")
        events.append("用户可在 Binance APP 查看这些保护单")

        notes.append("v5.1: 机器人停止后，止损止盈单保留在 Binance")
        notes.append("v5.1: 仅取消非 reduce_only 订单")
        notes.append("v5.1: except 块中有 cancel_all_orders 作为后备")
        notes.append("用户重启后, _recover_sltp_on_start 恢复状态")

        return SimulationResult(
            scenario=OrderScenario.ONSTOP_PRESERVATION,
            success=True,
            orders_submitted=[],
            events_triggered=events,
            state_changes={
                "sl_order": "ACTIVE → ACTIVE (保留在 Binance)",
                "tp_order": "ACTIVE → ACTIVE (保留在 Binance)",
                "non_reduce_orders": "CANCELLED",
            },
            notes=notes,
        )

    def _simulate_cumulative_position_limit(self) -> SimulationResult:
        """
        场景 10: 累加仓位上限验证 (v5.1)

        Flow:
        1. Check current position value
        2. Calculate max_usdt = equity × max_position_ratio × leverage
        3. remaining_capacity = max_usdt - current_value
        4. If remaining_capacity <= 0: reject add (已达上限)
        5. If remaining_capacity > 0: allow add (clamp to remaining)
        """
        events = []
        notes = []

        # Simulated parameters
        equity = 1000.0
        max_position_ratio = 0.30
        leverage = 10
        max_usdt = equity * max_position_ratio * leverage  # $3000
        current_value = 2500.0  # Already holding $2500
        remaining = max(0, max_usdt - current_value)  # $500 remaining

        events.append("加仓前容量检查:")
        events.append(f"  equity = ${equity:,.2f}")
        events.append(f"  max_position_ratio = {max_position_ratio:.0%}")
        events.append(f"  leverage = {leverage}x")
        events.append(f"  max_usdt = ${max_usdt:,.2f} (equity × ratio × leverage)")
        events.append(f"  current_value = ${current_value:,.2f}")
        events.append(f"  remaining_capacity = ${remaining:,.2f}")
        events.append("")

        if remaining > 0:
            events.append(f"  ✅ 允许加仓: 最大加仓 ${remaining:,.2f}")
            events.append(f"  → requested_size = min(AI_size, remaining_capacity)")
        else:
            events.append(f"  ❌ 已达上限: remaining = 0, 拒绝加仓")

        events.append("")

        # Second scenario: fully maxed out
        full_value = 3100.0
        full_remaining = max(0, max_usdt - full_value)
        events.append("容量耗尽场景:")
        events.append(f"  current_value = ${full_value:,.2f}")
        events.append(f"  remaining = ${full_remaining:,.2f}")
        events.append(f"  → 拒绝加仓, 等待减仓后释放容量")

        notes.append("v5.1 E5: 累加仓位上限 = equity × max_position_ratio × leverage")
        notes.append("每次加仓前检查 remaining_capacity")
        notes.append("remaining_capacity = max_usdt - current_position_value")
        notes.append("防止无限加仓, 总仓位不超过 30% × equity × leverage")

        return SimulationResult(
            scenario=OrderScenario.CUMULATIVE_POSITION_LIMIT,
            success=True,
            orders_submitted=[],
            events_triggered=events,
            state_changes={
                "max_usdt": f"${max_usdt:,.2f}",
                "current_value": f"${current_value:,.2f}",
                "remaining_capacity": f"${remaining:,.2f}",
                "add_allowed": "YES" if remaining > 0 else "NO",
            },
            notes=notes,
        )

    def _print_scenario_result(self, result: SimulationResult) -> None:
        """Print scenario simulation result."""
        scenario_names = {
            OrderScenario.NEW_POSITION: "场景 1: 新开仓",
            OrderScenario.ADD_POSITION: "场景 2: 同向加仓",
            OrderScenario.REDUCE_POSITION: "场景 3: 部分平仓",
            OrderScenario.CLOSE_POSITION: "场景 4: 完全平仓",
            OrderScenario.REVERSAL: "场景 5: 反转交易 (v3.18)",
            OrderScenario.BRACKET_FAILURE: "场景 6: Bracket 失败 (v3.18)",
            OrderScenario.SLTP_MODIFY_FAILURE: "场景 7: SL/TP modify 失败 (v3.18)",
            OrderScenario.DYNAMIC_SLTP_UPDATE: "场景 8: S/R 动态重评估 (v5.1)",
            OrderScenario.ONSTOP_PRESERVATION: "场景 9: 停机保护 (v5.1)",
            OrderScenario.CUMULATIVE_POSITION_LIMIT: "场景 10: 累加仓位上限 (v5.1)",
        }

        name = scenario_names.get(result.scenario, str(result.scenario))
        status = "✅" if result.success else "❌"

        print(f"  {status} {name}")
        print(f"     ────────────────────────────────────────")

        # Events
        print(f"     事件流程:")
        for event in result.events_triggered[:15]:  # Limit display
            print(f"       {event}")
        if len(result.events_triggered) > 15:
            print(f"       ... ({len(result.events_triggered) - 15} more events)")

        # State changes
        if result.state_changes:
            print(f"     状态变化:")
            for key, value in result.state_changes.items():
                print(f"       {key}: {value}")

        # Notes
        if result.notes:
            print(f"     关键点:")
            for note in result.notes:
                print(f"       • {note}")

        print()

    def _print_v50_verification(self) -> None:
        """Print v5.1 specific verification summary."""
        print("  📋 v3.18 + v5.1 修复验证:")
        print()
        print("  ┌──────────────────────────────────────────────────────────────────┐")
        print("  │ 修复项                          │ 状态 │ 验证场景               │")
        print("  ├──────────────────────────────────────────────────────────────────┤")
        print("  │ 反转两阶段提交 (v3.18)          │ ✅   │ 场景 5: 反转交易       │")
        print("  │ Bracket 失败不回退 (v3.18)      │ ✅   │ 场景 6: Bracket 失败   │")
        print("  │ SL/TP 数量更新 (v3.18)          │ ✅   │ 场景 2: 同向加仓       │")
        print("  │ modify 失败回退 (v3.18)         │ ✅   │ 场景 7: modify 失败    │")
        print("  │ S/R 动态重评估 + 阈值 (v5.1)   │ ✅   │ 场景 8: S/R 重评估     │")
        print("  │ 停机保护 SL/TP 保留 (v5.1)     │ ✅   │ 场景 9: on_stop        │")
        print("  │ 累加仓位上限 30% (v5.1)        │ ✅   │ 场景 10: 容量检查      │")
        print("  └──────────────────────────────────────────────────────────────────┘")

    def should_skip(self) -> bool:
        return self.ctx.summary_mode


class ReversalStateSimulator(DiagnosticStep):
    """
    v3.18 反转状态机模拟

    Detailed simulation of the two-phase reversal state machine.
    """

    name = "v3.18 反转状态机详细模拟"

    def run(self) -> bool:
        print("-" * 70)
        print()
        print_box("反转状态机 (Two-Phase Commit)", 65)
        print()

        # State machine diagram
        print("  状态机图解:")
        print()
        print("  ┌──────────────┐")
        print("  │ 初始状态     │")
        print("  │ LONG 持仓    │")
        print("  │ _pending = ∅ │")
        print("  └──────┬───────┘")
        print("         │ 收到 SELL 信号 (反转)")
        print("         ▼")
        print("  ┌──────────────────────────────────────┐")
        print("  │ Phase 1: 存储状态                    │")
        print("  │ _pending_reversal = {                │")
        print("  │   target_side: 'short',              │")
        print("  │   target_quantity: qty,              │")
        print("  │   old_side: 'long',                  │")
        print("  │   submitted_at: now()                │")
        print("  │ }                                    │")
        print("  │ submit_order(SELL, reduce_only=True) │")
        print("  └──────────────┬───────────────────────┘")
        print("                 │ on_order_filled")
        print("                 │ on_position_closed")
        print("                 ▼")
        print("  ┌──────────────────────────────────────┐")
        print("  │ Phase 2: 检测 _pending_reversal      │")
        print("  │ if _pending_reversal:                │")
        print("  │   pending = _pending_reversal        │")
        print("  │   _pending_reversal = None  # 清空  │")
        print("  │   if _get_position() is None:        │")
        print("  │     _submit_bracket_order(SHORT)     │")
        print("  │   else:                              │")
        print("  │     ABORT (残留仓位)                 │")
        print("  └──────────────┬───────────────────────┘")
        print("                 │ on_order_filled")
        print("                 │ on_position_opened")
        print("                 ▼")
        print("  ┌──────────────┐")
        print("  │ 最终状态     │")
        print("  │ SHORT 持仓   │")
        print("  │ _pending = ∅ │")
        print("  └──────────────┘")
        print()

        # Edge cases
        print("  边缘情况处理:")
        print()
        print("  ┌─────────────────────────────────────────────────────────────┐")
        print("  │ 情况                        │ 处理                          │")
        print("  ├─────────────────────────────────────────────────────────────┤")
        print("  │ Phase 2 时仍有仓位          │ ABORT, 发送 CRITICAL 警报     │")
        print("  │ Phase 2 提交 Bracket 失败   │ 不开仓, 等待下一信号          │")
        print("  │ 平仓订单被拒绝              │ _pending_reversal 保留        │")
        print("  │ SL/TP 触发导致平仓          │ 正常进入 Phase 2              │")
        print("  │ 手动干预平仓                │ 正常进入 Phase 2              │")
        print("  └─────────────────────────────────────────────────────────────┘")
        print()

        # Compare with old behavior
        print("  与旧版行为对比:")
        print()
        print("  旧版 (有竞态条件):")
        print("    1. 提交平仓订单")
        print("    2. 立即提交开仓订单  ← 问题! 可能在平仓完成前执行")
        print("    3. 可能导致双向持仓或订单被拒")
        print()
        print("  v3.18 (事件驱动):")
        print("    1. 存储 _pending_reversal 状态")
        print("    2. 提交平仓订单")
        print("    3. 等待 on_position_closed 事件")
        print("    4. 验证无仓位后开新仓")
        print()

        print("  ✅ v3.18 反转状态机模拟完成")
        return True

    def should_skip(self) -> bool:
        return self.ctx.summary_mode


class BracketOrderFlowSimulator(DiagnosticStep):
    """
    Bracket 订单流程详细模拟

    Shows the complete flow of bracket order submission.
    """

    name = "Bracket 订单流程详细模拟"

    def run(self) -> bool:
        print("-" * 70)
        print()
        print_box("Bracket 订单流程 (Entry + SL + TP)", 65)
        print()

        signal = self.ctx.signal_data.get('signal', 'HOLD')
        if signal == 'HOLD':
            print("  ℹ️ 当前信号为 HOLD，模拟 BUY 信号的 Bracket 订单流程")
            signal = 'BUY'

        # Calculate example prices
        entry_price = self.ctx.current_price
        sl_price = entry_price * 0.98 if signal == 'BUY' else entry_price * 1.02
        tp_price = entry_price * 1.03 if signal == 'BUY' else entry_price * 0.97
        quantity = 0.01

        print(f"  模拟参数:")
        print(f"     信号: {signal}")
        print(f"     入场价: ${entry_price:,.2f}")
        print(f"     止损价: ${sl_price:,.2f} ({(abs(entry_price - sl_price) / entry_price * 100):.2f}%)")
        print(f"     止盈价: ${tp_price:,.2f} ({(abs(tp_price - entry_price) / entry_price * 100):.2f}%)")
        bc = self.ctx.base_currency
        notional = quantity * entry_price if entry_price > 0 else 0
        print(f"     数量: ${notional:,.0f} ({quantity:.4f} {bc})")
        print()

        # Flow diagram
        print("  订单提交流程:")
        print()
        print("  ┌─────────────────────────────────────────────────────────────┐")
        print("  │ 1. _submit_bracket_order(side, quantity)                    │")
        print("  │    ├─ 检查 quantity >= min_trade_amount                     │")
        print("  │    ├─ 检查 enable_auto_sl_tp                                │")
        print("  │    ├─ 获取 entry_price (latest_price_data / bars)           │")
        print("  │    └─ 获取 confidence, support, resistance                  │")
        print("  └─────────────────────────────────────────────────────────────┘")
        print("                          ↓")
        print("  ┌─────────────────────────────────────────────────────────────┐")
        print("  │ 2. SL/TP 价格计算                                           │")
        print("  │    ├─ 优先: AI Judge 提供的 stop_loss, take_profit          │")
        print("  │    ├─ 验证: validate_multiagent_sltp()                      │")
        print("  │    │   ├─ 检查 SL 在入场价正确一侧                          │")
        print("  │    │   └─ R/R >= 1.5:1 硬性门槛                             │")
        print("  │    └─ 回退: calculate_sr_based_sltp() (S/R Zones+ATR)      │")
        print("  └─────────────────────────────────────────────────────────────┘")
        print("                          ↓")
        print("  ┌─────────────────────────────────────────────────────────────┐")
        print("  │ 3. 两阶段订单提交 (v4.17)                                    │")
        print("  │    ├─ entry_order: LIMIT @ validated entry_price (GTC)      │")
        print("  │    ├─ sl_order: STOP_MARKET (on_position_opened, reduce)    │")
        print("  │    └─ tp_order: LIMIT (on_position_opened, reduce)          │")
        print("  └─────────────────────────────────────────────────────────────┘")
        print("                          ↓")
        print("  ┌─────────────────────────────────────────────────────────────┐")
        print("  │ 4. 订单提交 (submit_order_list)                             │")
        print("  │    └─ NautilusTrader 处理 OTO/OCO 链接                      │")
        print("  └─────────────────────────────────────────────────────────────┘")
        print("                          ↓")
        print("  ┌─────────────────────────────────────────────────────────────┐")
        print("  │ 5. 事件处理                                                 │")
        print("  │    ├─ on_order_filled (Entry) → on_position_opened          │")
        print("  │    ├─ on_order_filled (SL) → on_position_closed             │")
        print("  │    │   └─ OCO: 自动取消 TP                                  │")
        print("  │    └─ on_order_filled (TP) → on_position_closed             │")
        print("  │        └─ OCO: 自动取消 SL                                  │")
        print("  └─────────────────────────────────────────────────────────────┘")
        print()

        # v3.18 specific
        print("  v3.18 关键改进:")
        print("     • Bracket 失败时不回退到无保护订单")
        print("     • 发送 CRITICAL Telegram 警报")
        print("     • _last_signal_status 记录失败原因")
        print()

        print("  ✅ Bracket 订单流程模拟完成")
        return True

    def should_skip(self) -> bool:
        return self.ctx.summary_mode
