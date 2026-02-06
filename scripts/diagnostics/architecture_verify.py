"""
Architecture Verification Module

Verifies TradingAgents v3.27.1 architecture compliance.
Performs live data completeness checks against the actual live system.
"""

from typing import Dict, Optional

from .base import (
    DiagnosticContext,
    DiagnosticStep,
    print_box,
)


class TradingAgentsArchitectureVerifier(DiagnosticStep):
    """
    Verify TradingAgents v3.27.1 architecture compliance.

    v3.0.0 rewrite: Replaces static text with live data completeness verification.

    Checks:
    - analyze() parameter completeness vs live system
    - INDICATOR_DEFINITIONS presence in all 4 AI prompts
    - Prompt architecture: pure knowledge, no directives
    - Data pipeline coverage (13 categories)
    - Timing breakdown
    """

    name = "TradingAgents v3.27.1 架构验证"

    def run(self) -> bool:
        print("-" * 70)
        print()
        print_box("TradingAgents v3.27.1 架构验证", 65)
        print()

        print("  📊 架构原则 (v3.27.1):")
        print('     "Autonomy is non-negotiable" - AI 完全自主决策')
        print("     Prompts 包含纯知识描述，无 MUST/NEVER/ALWAYS 指令")
        print("     INDICATOR_DEFINITIONS v3.27: 117 行精简版 (统一 TRENDING/RANGING/failure)")
        print("     Risk Manager output 包含 invalidation 字段 (nof1 对齐)")
        print()

        self._verify_data_completeness()
        self._verify_prompt_architecture()
        self._verify_ai_decision()
        self._print_timing_breakdown()

        print()
        print("  ✅ TradingAgents v3.27.1 架构验证完成")
        return True

    def _verify_data_completeness(self) -> None:
        """Verify all 13 data categories are available."""
        print("  📋 数据完整性检查 (13 类):")

        checks = [
            ("[1] technical_data (15M)", self.ctx.technical_data, True),
            ("[2] sentiment_data", self.ctx.sentiment_data, True),
            ("[3] price_data", self.ctx.price_data, True),
            ("[4] order_flow_report", self.ctx.order_flow_report, False),
            ("[5] derivatives_report (Coinalyze)", self.ctx.derivatives_report, False),
            ("[6] binance_derivatives (Top Traders)", getattr(self.ctx, 'binance_derivatives_data', None), False),
            ("[7] orderbook_report", self.ctx.orderbook_report, False),
            ("[8] mtf_decision_layer (4H)", self.ctx.technical_data.get('mtf_decision_layer') if self.ctx.technical_data else None, False),
            ("[9] mtf_trend_layer (1D)", self.ctx.technical_data.get('mtf_trend_layer') if self.ctx.technical_data else None, False),
            ("[10] current_position", self.ctx.current_position, False),
            ("[11] account_context", self.ctx.account_context, True),
            ("[12] historical_context", getattr(self.ctx, 'historical_context', None), False),
            ("[13] sr_zones_data", self.ctx.sr_zones_data, False),
        ]

        available = 0
        required_ok = True
        for label, data, required in checks:
            has_data = data is not None and data != {}
            if has_data:
                available += 1
                if isinstance(data, dict):
                    detail = f"{len(data)} fields"
                elif isinstance(data, list):
                    detail = f"{len(data)} items"
                else:
                    detail = "present"
                print(f"     ✅ {label}: {detail}")
            else:
                marker = "❌" if required else "⚠️"
                note = " (REQUIRED)" if required else " (optional)"
                print(f"     {marker} {label}: None{note}")
                if required:
                    required_ok = False

        # kline_ohlcv check (nested in technical_data)
        kline_ohlcv = self.ctx.technical_data.get('kline_ohlcv', []) if self.ctx.technical_data else []
        if kline_ohlcv:
            print(f"     ✅ [+] kline_ohlcv: {len(kline_ohlcv)} bars (in technical_data)")
        else:
            print(f"     ⚠️ [+] kline_ohlcv: None (in technical_data)")

        # bars_data check
        sr_bars = self.ctx.sr_bars_data
        if sr_bars:
            print(f"     ✅ [+] bars_data (S/R Swing): {len(sr_bars)} bars")
        else:
            print(f"     ⚠️ [+] bars_data (S/R Swing): None")

        print()
        status = "✅ COMPLETE" if required_ok else "❌ MISSING REQUIRED DATA"
        print(f"     数据覆盖率: {available}/13 ({available/13*100:.0f}%) {status}")
        print()

    def _verify_prompt_architecture(self) -> None:
        """Verify prompt architecture matches v3.27.1 specifications."""
        print("  📋 Prompt 架构验证:")

        if not self.ctx.multi_agent:
            print("     ⚠️ MultiAgent 未初始化，跳过 Prompt 验证")
            return

        if not hasattr(self.ctx.multi_agent, 'get_last_prompts'):
            print("     ⚠️ get_last_prompts() 不可用")
            return

        last_prompts = self.ctx.multi_agent.get_last_prompts()
        if not last_prompts:
            print("     ⚠️ 无 Prompt 数据")
            return

        for agent_name in ["bull", "bear", "judge", "risk"]:
            if agent_name not in last_prompts:
                print(f"     ⚠️ {agent_name.upper()}: 无 Prompt 数据")
                continue

            prompts = last_prompts[agent_name]
            sys_prompt = prompts.get("system", "")
            user_prompt = prompts.get("user", "")

            has_indicator_ref = "INDICATOR REFERENCE" in sys_prompt
            has_memories = "PAST REFLECTIONS" in user_prompt
            has_invalidation = "invalidation" in user_prompt.lower() if agent_name == "risk" else None

            # Check for directive language (should be zero)
            directive_patterns = ["you MUST", "Do NOT", "NEVER trade", "ALWAYS defer", "RULE:"]
            directive_count = sum(1 for p in directive_patterns if p in sys_prompt or p in user_prompt)

            status = "✅" if has_indicator_ref else "⚠️"
            extras = []
            if agent_name == "judge" and has_memories:
                extras.append("memories")
            if has_invalidation:
                extras.append("invalidation")
            if directive_count > 0:
                extras.append(f"WARN: {directive_count} directives found")

            extra_str = f" [{', '.join(extras)}]" if extras else ""
            print(f"     {status} {agent_name.upper()}: sys={len(sys_prompt)}ch, user={len(user_prompt)}ch, "
                  f"INDICATOR_REF={'yes' if has_indicator_ref else 'NO'}{extra_str}")

        print()

    def _verify_ai_decision(self) -> None:
        """Verify AI decision output format."""
        sd = self.ctx.signal_data
        print("  📋 AI 决策输出验证:")

        expected_fields = ['signal', 'confidence', 'risk_level', 'position_size_pct',
                          'stop_loss', 'take_profit', 'reason', 'invalidation', 'debate_summary']
        present = [f for f in expected_fields if f in sd and sd[f] is not None]
        missing = [f for f in expected_fields if f not in sd or sd[f] is None]

        for f in present:
            val = sd[f]
            if isinstance(val, str) and len(val) > 50:
                val = val[:50] + "..."
            print(f"     ✅ {f}: {val}")
        for f in missing:
            marker = "❌" if f in ['signal', 'confidence'] else "⚠️"
            print(f"     {marker} {f}: missing")

        print(f"     覆盖率: {len(present)}/{len(expected_fields)}")
        print()

    def _print_timing_breakdown(self) -> None:
        """Print timing breakdown for all measured steps."""
        timings = self.ctx.step_timings
        if not timings:
            return

        print("  📋 耗时分析:")
        total = sum(timings.values())
        for label, elapsed in sorted(timings.items(), key=lambda x: -x[1]):
            pct = (elapsed / total * 100) if total > 0 else 0
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            print(f"     {bar} {elapsed:6.2f}s ({pct:4.1f}%) {label}")
        print(f"     {'─' * 20} {total:6.2f}s TOTAL")
        print()

    def should_skip(self) -> bool:
        return self.ctx.summary_mode


class DiagnosticSummaryBox(DiagnosticStep):
    """
    Print comprehensive diagnostic summary box.

    Based on v11.16: 诊断总结 section (after [8/10])

    Shows:
    - Architecture version
    - AI Signal / Final Signal / Confidence / Winning Side / Risk Level
    - Current Position
    - WOULD EXECUTE simulation
    - 实盘执行流程 steps
    """

    name = "诊断总结"

    def run(self) -> bool:
        print()
        print("=" * 70)
        print("  诊断总结 (TradingAgents v3.27.1)")
        print("=" * 70)
        print()

        sd = self.ctx.signal_data
        judge = sd.get('judge_decision', {})

        print("  📊 架构: TradingAgents v3.27.1")
        print("     AI Prompts: 纯知识描述 (无 MUST/NEVER 指令)")
        print("     INDICATOR_DEFINITIONS: v3.27 精简版 (117 行)")
        print("     Risk Manager: invalidation 字段 (nof1 对齐)")
        print()

        print(f"  📊 AI Signal: {sd.get('signal', 'N/A')}")
        print(f"  📊 Final Signal: {self.ctx.final_signal}")
        print(f"  📊 Confidence: {sd.get('confidence', 'N/A')}")
        print(f"  📊 Winning Side: {judge.get('winning_side', 'N/A')}")
        print(f"  📊 Risk Level: {sd.get('risk_level', 'N/A')}")
        print()

        # Current position
        if self.ctx.current_position:
            pos = self.ctx.current_position
            side = pos.get('side', 'N/A').upper()
            qty = pos.get('quantity', 0)
            print(f"  📊 Current Position: {side} {qty:.4f} BTC")
        else:
            print("  📊 Current Position: FLAT (无持仓)")
        print()

        # Would execute simulation
        self._print_execution_simulation(sd)

        # 实盘执行流程
        self._print_live_execution_flow(sd)

        return True

    def _print_execution_simulation(self, sd: Dict) -> None:
        """Print execution simulation."""
        signal = sd.get('signal', 'HOLD')
        confidence = sd.get('confidence', 'MEDIUM')

        if signal == 'HOLD':
            print("  ⚪ WOULD NOT EXECUTE: Signal is HOLD")
            return

        # v4.8: Calculate position using ai_controlled formula
        cfg = self.ctx.strategy_config
        equity = getattr(self.ctx, 'account_balance', {}).get('total_balance', 0)
        if equity <= 0:
            equity = getattr(cfg, 'equity', 1000)

        leverage = getattr(self.ctx, 'binance_leverage', 10)
        max_position_ratio = getattr(cfg, 'max_position_ratio', 0.30)
        max_usdt = equity * max_position_ratio * leverage

        confidence_mapping = {
            'HIGH': getattr(cfg, 'position_sizing_high_pct', 80),
            'MEDIUM': getattr(cfg, 'position_sizing_medium_pct', 50),
            'LOW': getattr(cfg, 'position_sizing_low_pct', 30),
        }

        size_pct = confidence_mapping.get(confidence.upper(), 50)
        usdt_amount = max_usdt * (size_pct / 100)

        # Apply remaining capacity in cumulative mode
        if self.ctx.current_position:
            current_value = self.ctx.current_position.get('position_value_usdt', 0)
            remaining = max(0, max_usdt - current_value)
            usdt_amount = min(usdt_amount, remaining)

        quantity = usdt_amount / self.ctx.current_price if self.ctx.current_price else 0
        notional = quantity * self.ctx.current_price

        # Get SL/TP
        sl = sd.get('stop_loss')
        tp = sd.get('take_profit')

        action = "BUY" if signal in ['BUY', 'LONG'] else "SELL"
        emoji = "🟢" if signal in ['BUY', 'LONG'] else "🔴"

        print(f"  {emoji} WOULD EXECUTE: {action} {quantity:.4f} BTC @ ${self.ctx.current_price:,.2f}")
        print(f"     Notional: ${notional:,.2f}")

        if sl:
            try:
                sl_val = float(sl)
                print(f"     Stop Loss: ${sl_val:,.2f}")
            except (ValueError, TypeError):
                pass

        if tp:
            try:
                tp_val = float(tp)
                print(f"     Take Profit: ${tp_val:,.2f}")
            except (ValueError, TypeError):
                pass

        # SL/TP source
        judge = sd.get('judge_decision', {})
        if sl and tp:
            print("     SL/TP 来源: MultiAgent (Judge)")

    def _print_live_execution_flow(self, sd: Dict) -> None:
        """Print live execution flow steps."""
        print()
        print("-" * 70)
        print("  📱 实盘执行流程:")
        print("-" * 70)
        print()

        signal = sd.get('signal', 'HOLD')
        confidence = sd.get('confidence', 'MEDIUM')
        cfg = self.ctx.strategy_config
        min_conf = getattr(cfg, 'min_confidence_to_trade', 'MEDIUM')

        confidence_order = ['LOW', 'MEDIUM', 'HIGH']
        try:
            signal_conf_idx = confidence_order.index(confidence.upper())
            min_conf_idx = confidence_order.index(min_conf.upper())
            passes_threshold = signal_conf_idx >= min_conf_idx
        except ValueError:
            passes_threshold = False

        print(f"  Step 1: AI 分析完成 → Signal = {signal}")
        print("  Step 2: 📱 发送 Telegram 信号通知")
        print("          → 此时你会收到交易信号消息")
        print("  Step 3: 调用 _execute_trade()")

        if signal == 'HOLD':
            print("          → ⚪ Signal is HOLD, 不执行交易")
        elif not passes_threshold:
            print(f"          → ❌ Confidence {confidence} < minimum {min_conf}")
            print("          → 不执行交易")
        else:
            print("          → ✅ 所有检查通过")
            print("          → 📊 提交订单到 Binance")

        print()
        print("  💡 关键点: Telegram 通知在 _execute_trade 之前发送!")
        print("     如果收到信号但无交易，检查服务日志查看 _execute_trade 输出")

    def should_skip(self) -> bool:
        return self.ctx.summary_mode
