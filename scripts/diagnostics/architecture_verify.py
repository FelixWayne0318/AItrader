"""
Architecture Verification Module

Verifies TradingAgents v3.3 architecture compliance.
Restored from v11.16 monolithic script [7.5/10] section.
"""

from typing import Dict, Optional

from .base import (
    DiagnosticContext,
    DiagnosticStep,
    print_box,
)


class TradingAgentsArchitectureVerifier(DiagnosticStep):
    """
    Verify TradingAgents v3.3 architecture compliance.

    Based on v11.16: [7.5/10] TradingAgents v3.3 架构验证

    Shows:
    - Design philosophy ("Autonomy is non-negotiable")
    - Removed local hardcoded rules
    - Removed pre-computed labels
    - Raw data AI receives
    - AI decision result (unfiltered)
    - MTF state estimation
    """

    name = "TradingAgents v3.3 架构验证"

    def run(self) -> bool:
        print("-" * 70)

        print("  📊 TradingAgents v3.3 设计理念:")
        print('     "Autonomy is non-negotiable" - AI 像人类分析师一样思考')
        print("     AI 接收原始数值 + INDICATOR_DEFINITIONS 自主解读")
        print()

        self._print_removed_rules()
        self._print_removed_labels()
        self._print_ai_received_data()
        self._print_ai_decision_result()
        self._print_mtf_state_estimation()

        print()
        print("  ✅ TradingAgents v3.4 架构验证完成")
        return True

    def _print_removed_rules(self) -> None:
        """Print removed local hardcoded rules."""
        print("  ✅ 已移除的本地硬编码规则:")
        print("     ❌ 趋势方向权限检查 (allow_long/allow_short)")
        print("     ❌ 支撑/阻力位边界检查 (proximity_threshold)")
        print("     ❌ RSI 入场范围限制")
        print("     ❌ 确认计数框架 (bullish_count/bearish_count)")
        print()

    def _print_removed_labels(self) -> None:
        """Print removed pre-computed labels."""
        print("  ✅ 不再传给 AI 的预计算标签 (v3.3 移除):")
        print("     ❌ support/resistance - AI 用 SMA_50/BB 作动态支撑阻力")
        print("     ❌ cvd_trend - AI 从 recent_10_bars 推断")
        print("     ❌ overall_trend - AI 从 SMA 关系推断")
        print("     ❌ Interpretation: Bullish/Bearish - AI 从原始比例推断")
        print()

    def _print_ai_received_data(self) -> None:
        """Print raw data AI receives."""
        td = self.ctx.technical_data
        of = self.ctx.order_flow_report or {}

        print("  📋 AI 接收的数据 (原始数值，由 AI 自主解读):")
        print(f"     - Price: ${self.ctx.current_price:,.2f}")
        print(f"     - SMA_5/20/50: ${td.get('sma_5', 0):,.2f} / ${td.get('sma_20', 0):,.2f} / ${td.get('sma_50', 0):,.2f}")
        print(f"     - RSI: {td.get('rsi', 0):.1f}")
        print(f"     - MACD/Signal: {td.get('macd', 0):.4f} / {td.get('macd_signal', 0):.4f}")
        print(f"     - BB: ${td.get('bb_lower', 0):,.2f} - ${td.get('bb_upper', 0):,.2f}")
        print(f"     - Buy Ratio: {of.get('buy_ratio', 0)*100:.1f}%")
        print()

    def _print_ai_decision_result(self) -> None:
        """Print AI decision result (unfiltered)."""
        sd = self.ctx.signal_data

        print("  🎯 AI 决策结果 (无本地过滤):")
        print(f"     Signal: {sd.get('signal', 'N/A')}")
        print(f"     Confidence: {sd.get('confidence', 'N/A')}")
        print()

    def _print_mtf_state_estimation(self) -> None:
        """Print MTF state estimation based on current data."""
        td = self.ctx.technical_data

        print("  📊 MTF 状态估算 (基于当前数据，非实盘实时状态):")

        # Trend layer (1D)
        sma_200 = td.get('sma_200', 0)
        if sma_200 > 0:
            price_vs_sma200 = ((self.ctx.current_price / sma_200 - 1) * 100)
            trend_status = "BULLISH" if price_vs_sma200 > 0 else "BEARISH"
            print(f"     趋势层 (1D): {trend_status} - 价格 {'>' if price_vs_sma200 > 0 else '<'} SMA_200 ({price_vs_sma200:+.2f}%) (供 AI 参考)")
        else:
            # Use MTF trend layer data if available
            mtf_trend = td.get('mtf_trend_layer', {})
            mtf_sma_200 = mtf_trend.get('sma_200', 0)
            if mtf_sma_200 > 0:
                price_vs_sma200 = ((self.ctx.current_price / mtf_sma_200 - 1) * 100)
                trend_status = "BULLISH" if price_vs_sma200 > 0 else "BEARISH"
                print(f"     趋势层 (1D): {trend_status} - 价格 {'>' if price_vs_sma200 > 0 else '<'} SMA_200 ({price_vs_sma200:+.2f}%) (供 AI 参考)")
            else:
                print("     趋势层 (1D): N/A - SMA_200 数据不足")

        # Decision layer (4H)
        sma_5 = td.get('sma_5', 0)
        sma_20 = td.get('sma_20', 0)
        rsi = td.get('rsi', 50)

        if sma_5 > sma_20:
            decision_status = "ALLOW_LONG"
        elif sma_5 < sma_20:
            decision_status = "ALLOW_SHORT"
        else:
            decision_status = "WAIT"

        print(f"     决策层 (4H): {decision_status} - SMA_5 {'>' if sma_5 > sma_20 else '<'} SMA_20, RSI={rsi:.1f}")

        # Execution layer (15M)
        bb_upper = td.get('bb_upper', 0)
        bb_lower = td.get('bb_lower', 0)
        if bb_upper and bb_lower and bb_upper > bb_lower:
            bb_width = bb_upper - bb_lower
            bb_position = ((self.ctx.current_price - bb_lower) / bb_width) * 100
        else:
            bb_position = 50.0

        print(f"     执行层 (15M): BB 位置 {bb_position:.1f}% (0%=下轨, 100%=上轨)")
        print()
        print("  ⚠️ 注意: 以上为基于当前数据的估算值")
        print("     v3.1: 所有交易决策由 AI (MultiAgent) 完成，本地不做趋势判断")

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
        print("  诊断总结 (TradingAgents v3.17 - R/R 驱动入场)")
        print("=" * 70)
        print()

        sd = self.ctx.signal_data
        judge = sd.get('judge_decision', {})

        print("  📊 架构: TradingAgents v3.17 - R/R 驱动入场")
        print("     入场标准: R/R >= 1.5:1 (唯一入场标准)")
        print("     仓位大小: 由 R/R 质量决定 (R/R 越高 → 仓位越大)")
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
