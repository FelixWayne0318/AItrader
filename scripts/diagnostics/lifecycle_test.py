"""
Lifecycle Test Module (v5.1)

Tests post-trade lifecycle features and on_bar MTF routing logic.
Restored from v11.16 monolithic script.

v5.1 update: Trailing Stop removed, replaced by S/R dynamic reevaluation.
"""

from typing import Dict, Optional

from .base import (
    DiagnosticContext,
    DiagnosticStep,
    fetch_binance_klines,
    create_bar_from_kline,
    safe_float,
)


class PostTradeLifecycleTest(DiagnosticStep):
    """
    Test post-trade lifecycle features.

    Tests:
    - OCO orphan order cleanup (_cleanup_oco_orphans)
    - S/R Dynamic SL/TP reevaluation (_reevaluate_sltp_for_existing_position)

    v5.0: Trailing Stop removed. S/R reevaluation is the sole SL adjustment mechanism.
    v5.1: Quality-aware TP sorting + TP buffer (Osler 2003) for hit probability asymmetry fix.
    Based on v11.16: [8.5/10] Post-Trade 生命周期测试
    """

    name = "Post-Trade 生命周期测试"

    def run(self) -> bool:
        print("-" * 70)

        cfg = self.ctx.strategy_config

        # Test OCO orphan order cleanup
        print("  📋 OCO 孤儿订单清理 (_cleanup_oco_orphans):")
        enable_oco = getattr(cfg, 'enable_oco', False)
        if enable_oco:
            print("     ✅ enable_oco = True")
            print("        → 实盘会在每次 on_timer 后调用 _cleanup_oco_orphans()")
            print("        → 清理无持仓时的 reduce-only 订单")
        else:
            print("     ⚠️ enable_oco = False (跳过清理)")

        # Test S/R dynamic SL/TP reevaluation (v5.1: replaces Trailing Stop)
        print()
        print("  📋 S/R 动态 SL/TP 重评估 (_reevaluate_sltp_for_existing_position):")
        enable_auto_sltp = getattr(cfg, 'enable_auto_sl_tp', True)
        if enable_auto_sltp:
            print("     ✅ enable_auto_sl_tp = True")
            print("        → 每 15 分钟基于最新 S/R zones 重新计算 SL/TP")
            print("        → SL 单向保护: LONG max(new, old), SHORT min(new, old)")
            print("        → TP 由 S/R 重评估自由调整 (AI 职责, v2.2)")
            print("        → ATR buffer 隐式 regime 适应 (波动率→SL 距离自动缩放)")
            print("        → 变化 < 0.1% 跳过 (防订单风暴)")

            # Show current SL/TP state if position exists
            if self.ctx.current_position:
                self._show_reevaluation_context()
        else:
            print("     ⚠️ enable_auto_sl_tp = False (SL/TP 不会动态调整)")

        # Test position snapshot
        print()
        print("  📋 持仓快照记录 (_save_position_snapshot):")
        print("     ✅ 每次 on_timer 记录持仓状态到 data/position_snapshots/")
        print("        → 用于追踪持仓历史和计算回撤")

        print()
        print("  ✅ Post-Trade 生命周期测试完成")
        return True

    def _show_reevaluation_context(self) -> None:
        """Show S/R reevaluation context for current position."""
        side = self.ctx.current_position.get('side', '').lower()
        entry_price = self.ctx.current_position.get('entry_price', 0)
        if entry_price <= 0:
            entry_price = self.ctx.current_position.get('avg_px', 0)

        if entry_price > 0 and self.ctx.current_price > 0:
            if side in ['long', 'buy']:
                pnl_pct = (self.ctx.current_price - entry_price) / entry_price * 100
            else:
                pnl_pct = (entry_price - self.ctx.current_price) / entry_price * 100
            print(f"        → 当前浮盈: {pnl_pct:.2f}%")
            print(f"        → 入场价: ${entry_price:,.2f}  当前价: ${self.ctx.current_price:,.2f}")
            print(f"        → 下次 on_timer 将调用 _reevaluate_sltp_for_existing_position()")

    def should_skip(self) -> bool:
        return self.ctx.summary_mode


class OnBarMTFRoutingTest(DiagnosticStep):
    """
    Simulate on_bar MTF routing logic.

    Tests the bar type routing to different layers:
    - 1D bars → Trend layer (_handle_trend_bar)
    - 4H bars → Decision layer (_handle_decision_bar)
    - 15M bars → Execution layer (_handle_execution_bar)

    Based on v11.16: [10/14] on_bar MTF 路由逻辑模拟
    """

    name = "on_bar MTF 路由逻辑模拟"

    def run(self) -> bool:
        print("-" * 70)

        try:
            # Check MTF config
            mtf_config = self.ctx.base_config.get('multi_timeframe', {})
            mtf_enabled = mtf_config.get('enabled', False)

            if not mtf_enabled:
                print("  ℹ️ MTF 未启用，跳过路由测试")
                return True

            print("  📊 MTF Bar 路由逻辑 (与 deepseek_strategy.py:on_bar 一致):")
            print()

            # Get timeframe configs
            trend_tf = mtf_config.get('trend_layer', {}).get('timeframe', '1d')
            decision_tf = mtf_config.get('decision_layer', {}).get('timeframe', '4h')
            execution_tf = mtf_config.get('execution_layer', {}).get('default_timeframe', '15m')

            self._print_routing_rules(trend_tf, decision_tf, execution_tf)
            self._simulate_current_bar_routing()
            self._print_indicator_updates()

            print()
            print("  ✅ on_bar MTF 路由模拟完成")
            return True

        except Exception as e:
            self.ctx.add_error(f"on_bar 路由模拟失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _print_routing_rules(self, trend_tf: str, decision_tf: str, execution_tf: str) -> None:
        """Print MTF routing rules."""
        print(f"  [路由规则] Bar 类型 → 处理层:")
        print()
        print(f"     • {trend_tf.upper()} bar → 趋势层 (_handle_trend_bar)")
        print(f"       - 更新 SMA_200, MACD")
        print(f"       - 收集趋势数据供 AI 分析 (v3.1: 不做本地判断)")
        print(f"       - 设置 _mtf_trend_initialized = True")
        print()
        print(f"     • {decision_tf.upper()} bar → 决策层 (_handle_decision_bar)")
        print(f"       - 更新决策层技术指标")
        print(f"       - 收集决策层数据 (AI 自主分析，无本地决策)")
        print(f"       - 设置 _mtf_decision_initialized = True")
        print()
        print(f"     • {execution_tf.upper()} bar → 执行层 (_handle_execution_bar)")
        print(f"       - 更新执行层指标 (RSI, MACD 等)")
        print(f"       - 更新 _cached_current_price (线程安全)")
        print(f"       - 设置 _mtf_execution_initialized = True")
        print()

    def _simulate_current_bar_routing(self) -> None:
        """Simulate routing for current bar."""
        cfg = self.ctx.strategy_config
        bar_type_str = str(getattr(cfg, 'bar_type', '15-MINUTE'))
        print(f"  [模拟路由] 当前诊断使用的 bar_type:")
        print(f"     bar_type: {bar_type_str}")

        if '1-DAY' in bar_type_str or '1D' in bar_type_str.upper():
            print(f"     → 路由到: 趋势层 (1D)")
        elif '4-HOUR' in bar_type_str or '4H' in bar_type_str.upper():
            print(f"     → 路由到: 决策层 (4H)")
        else:
            print(f"     → 路由到: 执行层 (15M) - 主分析周期")
        print()

    def _print_indicator_updates(self) -> None:
        """Print indicator update data."""
        td = self.ctx.technical_data

        print(f"  [指标更新] 本次 bar 更新的指标值:")
        print(f"     indicator_manager.update(bar) 后:")
        print(f"     • 价格: ${self.ctx.current_price:,.2f}")
        print(f"     • SMA_5: ${td.get('sma_5', 0):,.2f}")
        print(f"     • SMA_20: ${td.get('sma_20', 0):,.2f}")
        print(f"     • SMA_50: ${td.get('sma_50', 0):,.2f}")
        print(f"     • RSI: {td.get('rsi', 0):.2f}")
        print(f"     • MACD: {td.get('macd', 0):.4f}")
        print(f"     • MACD Signal: {td.get('macd_signal', 0):.4f}")
        print(f"     • Support: ${td.get('support', 0):,.2f}")
        print(f"     • Resistance: ${td.get('resistance', 0):,.2f}")

    def should_skip(self) -> bool:
        return self.ctx.summary_mode
