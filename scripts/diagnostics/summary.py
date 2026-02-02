"""
Summary Module

Generates comprehensive diagnostic summaries and analysis.
"""

from typing import Dict, List, Optional

from .base import (
    DiagnosticContext,
    DiagnosticStep,
    print_box,
    print_wrapped,
    safe_float,
)


class DataFlowSummary(DiagnosticStep):
    """
    Generate complete data flow summary.

    Outputs all collected data values in a structured format.
    """

    name = "完整数据流汇总"

    def run(self) -> bool:
        print("-" * 70)
        print()

        self._print_technical_data()
        self._print_sentiment_data()
        self._print_order_flow_data()
        self._print_derivatives_data()
        self._print_position_data()
        self._print_ai_decision()
        self._print_mtf_status()

        print()
        print("  ✅ 完整数据流汇总完成")
        return True

    def _print_technical_data(self) -> None:
        """Print technical indicator data."""
        print_box("技术指标数据")
        print()
        td = self.ctx.technical_data

        print(f"  价格数据:")
        print(f"    当前价格: ${self.ctx.current_price:,.2f}")
        print(f"    24H 最高: ${self.ctx.price_data.get('high', 0):,.2f}")
        print(f"    24H 最低: ${self.ctx.price_data.get('low', 0):,.2f}")
        print(f"    价格变化: {self.ctx.price_data.get('price_change', 0):.2f}%")
        print()

        print(f"  移动平均线:")
        print(f"    SMA_5:  ${td.get('sma_5', 0):,.2f}")
        print(f"    SMA_20: ${td.get('sma_20', 0):,.2f}")
        print(f"    SMA_50: ${td.get('sma_50', 0):,.2f}")
        print(f"    EMA_12: ${td.get('ema_12', 0):,.2f}")
        print(f"    EMA_26: ${td.get('ema_26', 0):,.2f}")
        print()

        print(f"  震荡指标:")
        print(f"    RSI:           {td.get('rsi', 0):.2f}")
        print(f"    MACD:          {td.get('macd', 0):.4f}")
        print(f"    MACD Signal:   {td.get('macd_signal', 0):.4f}")
        print(f"    MACD Histogram:{td.get('macd_histogram', 0):.4f}")
        print()

        print(f"  布林带:")
        print(f"    BB Upper: ${td.get('bb_upper', 0):,.2f}")
        print(f"    BB Middle: ${td.get('bb_middle', 0):,.2f}")
        print(f"    BB Lower: ${td.get('bb_lower', 0):,.2f}")
        print()

        print(f"  支撑/阻力:")
        print(f"    支撑位: ${td.get('support', 0):,.2f}")
        print(f"    阻力位: ${td.get('resistance', 0):,.2f}")
        print()
        print(f"  趋势判断: {td.get('overall_trend', 'N/A')}")

    def _print_sentiment_data(self) -> None:
        """Print sentiment data."""
        print()
        print_box("情绪数据")
        print()
        sd = self.ctx.sentiment_data

        print(f"  Binance 多空比:")
        print(f"    Long/Short Ratio: {sd.get('long_short_ratio', 0):.4f}")
        print(f"    Long Account %:   {sd.get('positive_ratio', 0)*100:.2f}%")
        print(f"    Short Account %:  {sd.get('negative_ratio', 0)*100:.2f}%")
        print(f"    Net Sentiment:    {sd.get('net_sentiment', 0):.4f}")
        print(f"    数据来源: {sd.get('source', 'N/A')}")

    def _print_order_flow_data(self) -> None:
        """Print order flow data."""
        if not self.ctx.order_flow_report:
            return

        print()
        print_box("订单流数据")
        print()
        of = self.ctx.order_flow_report

        bars_count = of.get('bars_count', 10)
        print(f"  Binance Taker 数据 [采样窗口: {bars_count} bars]:")
        print(f"    Buy Ratio:      {of.get('buy_ratio', 0):.4f} ({of.get('buy_ratio', 0)*100:.2f}%)")
        print(f"    CVD Trend:      {of.get('cvd_trend', 'N/A')}")
        print(f"    Avg Trade Size: ${of.get('avg_trade_usdt', 0):,.2f}")
        print(f"    Volume (USDT):  ${of.get('volume_usdt', 0):,.0f}")
        print(f"    数据来源: {of.get('data_source', 'N/A')}")

    def _print_derivatives_data(self) -> None:
        """Print derivatives data."""
        if not self.ctx.derivatives_report:
            return

        print()
        print_box("衍生品数据 (Coinalyze)")
        print()
        dr = self.ctx.derivatives_report

        oi_data = dr.get('open_interest', {})
        fr_data = dr.get('funding_rate', {})
        liq_data = dr.get('liquidations', {})

        print(f"  Open Interest:")
        if oi_data:
            print(f"    OI (BTC):    {oi_data.get('value', 0):,.2f}")
            print(f"    OI (USD):    ${oi_data.get('total_usd', 0):,.0f}")
            print(f"    OI Change:   {oi_data.get('change_pct', 'N/A')}")
        else:
            print(f"    (数据不可用)")

        print()
        print(f"  Funding Rate:")
        if fr_data:
            fr_value = fr_data.get('value', 0)
            source = fr_data.get('source', 'unknown')
            print(f"    Current:     {fr_value:.6f} ({fr_value*100:.4f}%)")
            print(f"    Source:      {source}")
        else:
            print(f"    (数据不可用)")

        print()
        print(f"  Liquidations (1h):")
        if liq_data:
            history = liq_data.get('history', [])
            if history:
                latest = history[-1]
                long_btc = float(latest.get('l', 0))
                short_btc = float(latest.get('s', 0))
                long_usd = long_btc * self.ctx.current_price
                short_usd = short_btc * self.ctx.current_price
                print(f"    Long:   {long_btc:.4f} BTC (${long_usd:,.0f})")
                print(f"    Short:  {short_btc:.4f} BTC (${short_usd:,.0f})")
            else:
                print(f"    (无爆仓记录)")
        else:
            print(f"    (数据不可用)")

    def _print_position_data(self) -> None:
        """Print current position data."""
        print()
        print_box("当前持仓 & v4.8 仓位状态")
        print()

        # v4.8: Display leverage and max_usdt
        leverage = self.ctx.binance_leverage
        ctx = self.ctx.account_context
        equity = ctx.get('equity', 0)
        max_usdt = ctx.get('max_usdt', 0)

        print(f"  v4.8 仓位参数:")
        print(f"    杠杆 (Binance): {leverage}x")
        print(f"    资金 (equity):  ${equity:,.2f}")
        print(f"    max_usdt:       ${max_usdt:,.2f}")

        if self.ctx.current_position:
            pos = self.ctx.current_position
            position_value = pos.get('position_value_usdt', 0)
            remaining = ctx.get('remaining_capacity', max_usdt - position_value)

            print()
            print(f"  持仓状态: 有持仓")
            print(f"    方向:     {pos.get('side', 'N/A').upper()}")
            print(f"    数量:     {pos.get('quantity', 0)} BTC")
            print(f"    持仓价值: ${position_value:,.2f}")
            print(f"    入场价:   ${pos.get('entry_price', 0):,.2f}")
            print(f"    未实现PnL: ${pos.get('unrealized_pnl', 0):,.2f}")
            print(f"    盈亏比例: {pos.get('pnl_pct', 0):+.2f}%")
            print()
            print(f"  v4.8 累加模式:")
            capacity_pct = (position_value / max_usdt * 100) if max_usdt > 0 else 0
            print(f"    已用容量: {capacity_pct:.1f}%")
            print(f"    剩余可加仓: ${remaining:,.2f}")
            if remaining <= 0:
                print(f"    ⚠️ 已达上限，无法加仓")
        else:
            print()
            print(f"  持仓状态: 无持仓 (FLAT)")
            print(f"  v4.8 累加模式: 可开首仓")

    def _print_ai_decision(self) -> None:
        """Print AI decision results."""
        print()
        print_box("AI 决策结果")
        print()
        sd = self.ctx.signal_data

        print(f"  原始信号: {sd.get('signal', 'N/A')}")
        print(f"  最终信号: {self.ctx.final_signal}")
        print(f"  信心等级: {sd.get('confidence', 'N/A')}")
        print(f"  风险等级: {sd.get('risk_level', 'N/A')}")

        judge = sd.get('judge_decision', {})
        print(f"  胜出方:   {judge.get('winning_side', 'N/A')}")
        print()

        # SL/TP
        signal = sd.get('signal', 'HOLD')
        sltp_note = " (仅供参考，HOLD 不使用)" if signal == 'HOLD' else ""

        sl = safe_float(sd.get('stop_loss'))
        tp = safe_float(sd.get('take_profit'))
        if sl:
            print(f"  AI 止损: ${sl:,.2f}{sltp_note}")
        else:
            print(f"  AI 止损: N/A")
        if tp:
            print(f"  AI 止盈: ${tp:,.2f}{sltp_note}")
        else:
            print(f"  AI 止盈: N/A")

        print()
        print(f"  关键理由:")
        key_reasons = judge.get('key_reasons', [])
        for i, reason in enumerate(key_reasons[:3], 1):
            print(f"    {i}. {reason[:70]}...")

        risks = judge.get('acknowledged_risks', [])
        if risks:
            print()
            print(f"  确认风险:")
            for i, risk in enumerate(risks[:2], 1):
                print(f"    {i}. {risk[:70]}...")

        print()
        reason = sd.get('reason', 'N/A')
        print(f"  决策理由: {reason[:100]}...")

    def _print_mtf_status(self) -> None:
        """Print MTF filter status."""
        print()
        print_box("MTF 过滤状态")
        print()

        print(f"  架构: TradingAgents v3.12 - AI 决策 + S/R Zone v2.0 风控")
        print(f"  本地风控: S/R Zone v2.0 Block (执行层，含 level/source_type)")
        print()

        sd = self.ctx.signal_data
        print(f"  AI 决策: {sd.get('signal')} (Confidence: {sd.get('confidence')})")
        judge = sd.get('judge_decision', {})
        print(f"  Winning Side: {judge.get('winning_side', 'N/A')}")

    def should_skip(self) -> bool:
        return self.ctx.summary_mode


class DeepAnalysis(DiagnosticStep):
    """
    Deep analysis of signal conditions.

    Provides detailed reasoning for the current signal.
    """

    name = "深入分析: 信号产生条件"

    def run(self) -> bool:
        print()
        print("=" * 70)
        print("  📋 深入分析: 信号产生条件")
        print("=" * 70)
        print()

        self._analyze_technical_indicators()
        self._analyze_trend()
        self._analyze_sentiment()
        self._analyze_judge_decision()
        self._provide_recommendations()

        return True

    def _analyze_technical_indicators(self) -> None:
        """Analyze technical indicator thresholds."""
        print("[分析1] 技术指标阈值检查")
        print("-" * 50)

        td = self.ctx.technical_data
        cfg = self.ctx.strategy_config

        rsi = td.get('rsi', 50)
        rsi_upper = getattr(cfg, 'rsi_extreme_threshold_upper', 70)
        rsi_lower = getattr(cfg, 'rsi_extreme_threshold_lower', 30)

        print(f"  RSI: {rsi:.2f}")
        print(f"    参考阈值: 超卖<{rsi_lower}, 超买>{rsi_upper}")

        if rsi > rsi_upper:
            print(f"    → 🔴 超买区 (>{rsi_upper}) - AI 可能倾向 SHORT")
        elif rsi < rsi_lower:
            print(f"    → 🟢 超卖区 (<{rsi_lower}) - AI 可能倾向 LONG")
        else:
            print(f"    → ⚪ 中性区间 ({rsi_lower}-{rsi_upper}) - AI 综合其他因素判断")

        macd = td.get('macd', 0)
        macd_signal = td.get('macd_signal', 0)
        macd_hist = td.get('macd_histogram', 0)

        print()
        print(f"  MACD: {macd:.4f}")
        print(f"  MACD Signal: {macd_signal:.4f}")
        if macd > macd_signal:
            print("    → 🟢 MACD 在信号线上方 - 看涨")
        else:
            print("    → 🔴 MACD 在信号线下方 - 看跌")

        if macd_hist > 0:
            print(f"    → 🟢 柱状图为正 (+{macd_hist:.4f}) - 上涨动能")
        else:
            print(f"    → 🔴 柱状图为负 ({macd_hist:.4f}) - 下跌动能")

        # SMA analysis
        print()
        sma_5 = td.get('sma_5', 0)
        sma_20 = td.get('sma_20', 0)
        sma_50 = td.get('sma_50', 0)
        price = self.ctx.current_price

        print(f"  SMA_5: ${sma_5:,.2f}")
        print(f"  SMA_20: ${sma_20:,.2f}")
        print(f"  SMA_50: ${sma_50:,.2f}")
        print(f"  当前价格: ${price:,.2f}")

        if price > sma_5 > sma_20 > sma_50:
            print("    → 🟢 完美多头排列 (价格 > SMA5 > SMA20 > SMA50)")
        elif price < sma_5 < sma_20 < sma_50:
            print("    → 🔴 完美空头排列 (价格 < SMA5 < SMA20 < SMA50)")
        else:
            print("    → ⚪ 无明确趋势排列")

        # Bollinger Bands
        print()
        bb_upper = td.get('bb_upper', 0)
        bb_lower = td.get('bb_lower', 0)
        bb_width = bb_upper - bb_lower if bb_upper and bb_lower else 0
        bb_position = ((price - bb_lower) / bb_width * 100) if bb_width > 0 else 50

        print(f"  BB Upper: ${bb_upper:,.2f}")
        print(f"  BB Lower: ${bb_lower:,.2f}")
        print(f"  价格在带内位置: {bb_position:.1f}%")

        if bb_position > self.ctx.bb_overbought_threshold:
            print(f"    → 🔴 接近上轨 (>{self.ctx.bb_overbought_threshold}%, 可能超买)")
        elif bb_position < self.ctx.bb_oversold_threshold:
            print(f"    → 🟢 接近下轨 (<{self.ctx.bb_oversold_threshold}%, 可能超卖)")
        else:
            print("    → ⚪ 带内中间区域")

    def _analyze_trend(self) -> None:
        """Analyze trend strength."""
        print()
        print("[分析2] 趋势强度分析")
        print("-" * 50)

        td = self.ctx.technical_data
        trend = td.get('overall_trend', 'N/A')
        print(f"  整体趋势判断: {trend}")

        bars = self.ctx.indicator_manager.recent_bars if self.ctx.indicator_manager else []

        if len(bars) >= 10:
            price_10_bars_ago = float(bars[-10].close)
            price_change = ((self.ctx.current_price - price_10_bars_ago) / price_10_bars_ago) * 100
            print(f"  近10根K线变化: {price_change:+.2f}%")
        else:
            print(f"  近10根K线变化: N/A (K线数量不足)")

        if len(bars) >= 20:
            price_20_bars_ago = float(bars[-20].close)
            price_change = ((self.ctx.current_price - price_20_bars_ago) / price_20_bars_ago) * 100
            print(f"  近20根K线变化: {price_change:+.2f}%")

    def _analyze_sentiment(self) -> None:
        """Analyze market sentiment."""
        print()
        print("[分析3] 市场情绪分析")
        print("-" * 50)

        ls_ratio = self.ctx.sentiment_data.get('long_short_ratio', 1.0)
        print(f"  多空比: {ls_ratio:.4f}")

        if ls_ratio > self.ctx.ls_ratio_extreme_bullish:
            print(f"    → 🔴 极度看多 (>{self.ctx.ls_ratio_extreme_bullish}, 逆向指标: 可能下跌)")
        elif ls_ratio > self.ctx.ls_ratio_bullish:
            print(f"    → 🟡 偏多 (>{self.ctx.ls_ratio_bullish}, 市场乐观)")
        elif ls_ratio < self.ctx.ls_ratio_extreme_bearish:
            print(f"    → 🔴 极度看空 (<{self.ctx.ls_ratio_extreme_bearish}, 逆向指标: 可能上涨)")
        elif ls_ratio < self.ctx.ls_ratio_bearish:
            print(f"    → 🟡 偏空 (<{self.ctx.ls_ratio_bearish}, 市场悲观)")
        else:
            print("    → ⚪ 多空平衡")

    def _analyze_judge_decision(self) -> None:
        """Analyze Judge decision reasoning."""
        print()
        print("[分析4] Judge 决策原因分析 (TradingAgents)")
        print("-" * 50)

        sd = self.ctx.signal_data
        print(f"  ⚖️ Judge 最终决策: {sd.get('signal', 'N/A')}")
        print()

        judge = sd.get('judge_decision', {})
        if judge:
            print(f"  Winning Side: {judge.get('winning_side', 'N/A')}")

            key_reasons = judge.get('key_reasons', [])
            if key_reasons:
                print(f"  Key Reasons:")
                for reason in key_reasons[:3]:
                    print(f"    • {reason}")

            risks = judge.get('acknowledged_risks', [])
            if risks:
                print(f"  Acknowledged Risks:")
                for risk in risks[:2]:
                    print(f"    • {risk}")

        print()
        print(f"  📋 Judge 完整理由:")
        reason = sd.get('reason', 'N/A')
        print_wrapped(reason)

    def _provide_recommendations(self) -> None:
        """Provide recommendations based on analysis."""
        print()
        print("[分析5] 诊断建议")
        print("-" * 50)

        td = self.ctx.technical_data
        rsi = td.get('rsi', 50)

        if self.ctx.final_signal == 'HOLD':
            print("  📌 当前市场状态分析:")

            # Calculate bullish/bearish scores
            bullish = 0
            bearish = 0

            if rsi < 40:
                bullish += 1
            elif rsi > 60:
                bearish += 1

            macd = td.get('macd', 0)
            macd_signal = td.get('macd_signal', 0)
            if macd > macd_signal:
                bullish += 1
            else:
                bearish += 1

            sma_20 = td.get('sma_20', 0)
            if self.ctx.current_price > sma_20:
                bullish += 1
            else:
                bearish += 1

            print(f"    多头信号得分: {bullish}/3")
            print(f"    空头信号得分: {bearish}/3")

            if bullish > bearish + 1:
                print("    → 偏多头，但信号不够强烈")
            elif bearish > bullish + 1:
                print("    → 偏空头，但信号不够强烈")
            else:
                print("    → 多空信号混杂，无明确方向")

            print()
            print("  💡 HOLD 的常见原因:")
            print("    1. 技术指标处于中性区间")
            print("    2. 趋势不明确 (震荡整理)")
            print("    3. 多头和空头信号相互矛盾")
            print()
            print("  ⏳ 等待以下情况之一发生:")
            print(f"    • RSI 突破 30 或 70 (当前: {rsi:.1f})")
            print("    • MACD 形成明确金叉/死叉")
            print(f"    • 价格突破支撑位 ${td.get('support', 0):,.2f}")
            print(f"    • 价格突破阻力位 ${td.get('resistance', 0):,.2f}")

        print()
        print("=" * 70)
        print("  深入分析完成")
        print("=" * 70)

    def should_skip(self) -> bool:
        return self.ctx.summary_mode
