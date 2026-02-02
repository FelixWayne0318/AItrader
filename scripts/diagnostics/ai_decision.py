"""
AI Decision Module

Handles MultiAgent AI analysis and decision-making.
Enhanced from v11.16 monolithic script with:
- AI input data validation
- AI Prompt structure verification
- Bull/Bear debate transcript display
"""

from typing import Any, Dict, Optional

from .base import DiagnosticContext, DiagnosticStep, safe_float, print_wrapped, print_box


class AIInputDataValidator(DiagnosticStep):
    """
    Validate and display all data passed to MultiAgent AI.

    Shows exactly what data the AI receives for decision-making.

    Based on v11.16: AI 输入数据验证 (传给 MultiAgent)
    """

    name = "AI 输入数据验证 (传给 MultiAgent)"

    def run(self) -> bool:
        print("-" * 70)
        print()
        print_box("AI 输入数据验证 (传给 MultiAgent)", 65)
        print()

        # [1] Technical data
        self._print_technical_data()

        # [2] Sentiment data
        self._print_sentiment_data()

        # [3] Price data
        self._print_price_data()

        # [4] Order flow report
        self._print_order_flow_data()

        # [5] Derivatives report
        self._print_derivatives_data()

        # [5.5] Order book data
        self._print_orderbook_data()

        # [6] MTF Decision layer (4H)
        self._print_mtf_decision_data()

        # [7] MTF Trend layer (1D)
        self._print_mtf_trend_data()

        # [8] Current position
        self._print_position_data()

        # [9] Account context (v4.7)
        self._print_account_context()

        print()
        print("  ────────────────────────────────────────────────────────────────")
        print("  ✅ AI 输入数据验证完成")
        return True

    def _print_technical_data(self) -> None:
        """Print technical indicator data."""
        td = self.ctx.technical_data

        print("  [1] technical_data (15M 技术指标):")
        print(f"      price:           ${td.get('price', 0):,.2f}")
        print(f"      sma_5:           ${td.get('sma_5', 0):,.2f}")
        print(f"      sma_20:          ${td.get('sma_20', 0):,.2f}")
        print(f"      sma_50:          ${td.get('sma_50', 0):,.2f}")
        print(f"      rsi:             {td.get('rsi', 0):.2f}")
        print(f"      macd:            {td.get('macd', 0):.4f}")
        print(f"      macd_histogram:  {td.get('macd_histogram', 0):.4f}")
        print(f"      bb_upper:        ${td.get('bb_upper', 0):,.2f}")
        print(f"      bb_lower:        ${td.get('bb_lower', 0):,.2f}")
        bb_pos = td.get('bb_position', 0.5)
        print(f"      bb_position:     {bb_pos * 100:.1f}% (0%=下轨, 100%=上轨)")
        print(f"      [诊断用] overall_trend: {td.get('overall_trend', 'N/A')}")
        print()

    def _print_sentiment_data(self) -> None:
        """Print sentiment data."""
        sd = self.ctx.sentiment_data

        print("  [2] sentiment_data (情绪数据):")
        pos_ratio = sd.get('positive_ratio', sd.get('long_account_pct', 0))
        neg_ratio = sd.get('negative_ratio', sd.get('short_account_pct', 0))
        net_sent = sd.get('net_sentiment', 0)
        print(f"      positive_ratio:  {pos_ratio:.4f} ({pos_ratio*100:.2f}%)")
        print(f"      negative_ratio:  {neg_ratio:.4f} ({neg_ratio*100:.2f}%)")
        print(f"      net_sentiment:   {net_sent:.4f}")
        print()

    def _print_price_data(self) -> None:
        """Print price data."""
        pd = self.ctx.price_data

        print("  [3] price_data (价格数据 v3.6):")
        print(f"      price:           ${pd.get('price', 0):,.2f}")
        print(f"      price_change:    {pd.get('price_change', 0):.2f}% (上一根K线)")
        period_hours = pd.get('period_hours', 0)
        print(f"      period_high:     ${pd.get('period_high', 0):,.2f} ({period_hours:.0f}h)")
        print(f"      period_low:      ${pd.get('period_low', 0):,.2f} ({period_hours:.0f}h)")
        print(f"      period_change:   {pd.get('period_change_pct', 0):+.2f}% ({period_hours:.0f}h)")
        print()

    def _print_order_flow_data(self) -> None:
        """Print order flow data."""
        of = self.ctx.order_flow_report

        if of:
            print("  [4] order_flow_report (订单流 v3.6):")
            print(f"      buy_ratio:       {of.get('buy_ratio', 0):.4f} ({of.get('buy_ratio', 0)*100:.2f}%)")
            print(f"      volume_usdt:     ${of.get('volume_usdt', 0):,.0f}")
            print(f"      avg_trade_usdt:  ${of.get('avg_trade_usdt', 0):,.2f}")
            print(f"      trades_count:    {of.get('trades_count', 0):,}")
            print(f"      [诊断用] cvd_trend: {of.get('cvd_trend', 'N/A')}")
            print(f"      data_source:     {of.get('data_source', 'N/A')}")
        else:
            print("  [4] order_flow_report: None (未获取)")
        print()

    def _print_derivatives_data(self) -> None:
        """Print derivatives data."""
        dr = self.ctx.derivatives_report

        if dr:
            print("  [5] derivatives_report (衍生品数据):")
            oi = dr.get('open_interest', {})
            fr = dr.get('funding_rate', {})
            liq = dr.get('liquidations', {})
            print(f"      OI value (BTC):  {oi.get('value', 0) if oi else 0:,.2f}")
            print(f"      Funding rate:    {fr.get('value', 0) if fr else 0:.6f} ({fr.get('value', 0)*100 if fr else 0:.4f}%)")

            # v4.8: 优先显示 Binance 8h funding rate
            if self.ctx.binance_funding_rate:
                bfr = self.ctx.binance_funding_rate
                print(f"      [Binance 8h FR]: {bfr.get('funding_rate_pct', 0):.4f}% (主要数据源)")

            if liq:
                history = liq.get('history', [])
                if history:
                    latest = history[-1]
                    print(f"      Liq history[-1]:  l={latest.get('l', 0)} BTC, s={latest.get('s', 0)} BTC")
                else:
                    print("      Liq history:      empty")
            else:
                print("      liquidations:    None")
        else:
            print("  [5] derivatives_report: None (未获取)")
        print()

    def _print_orderbook_data(self) -> None:
        """Print order book data."""
        ob = self.ctx.orderbook_report
        ob_cfg = self.ctx.base_config.get('order_book', {})

        if ob:
            status = ob.get('_status', {})
            status_code = status.get('code', 'UNKNOWN')
            print(f"  [5.5] order_book_data (订单簿深度 v3.7) [状态: {status_code}]:")

            if status_code == 'OK':
                obi = ob.get('obi', {})
                dynamics = ob.get('dynamics', {})
                gradient = ob.get('pressure_gradient', {})
                liquidity = ob.get('liquidity', {})

                print(f"      OBI (simple):    {obi.get('simple', 0):+.4f}")
                print(f"      OBI (weighted):  {obi.get('weighted', 0):+.4f}")
                print(f"      OBI (adaptive):  {obi.get('adaptive_weighted', 0):+.4f}")

                if dynamics.get('samples_count', 0) > 0:
                    print(f"      OBI change:      {dynamics.get('obi_change', 0):+.4f}")
                    print(f"      Depth change:    {dynamics.get('depth_change_pct', 0):+.2f}%")
                    print(f"      Trend:           {dynamics.get('trend', 'N/A')}")
                else:
                    print("      Dynamics:        首次运行，无历史数据")
                    print("      ⚠️ 注意: adaptive OBI 无历史基线，数值可靠性降低")

                bid_near_5 = gradient.get('bid_near_5', 0) * 100
                ask_near_5 = gradient.get('ask_near_5', 0) * 100
                print(f"      Bid pressure:    near_5={bid_near_5:.1f}%")
                print(f"      Ask pressure:    near_5={ask_near_5:.1f}%")
                print(f"      Spread:          {liquidity.get('spread_pct', 0):.4f}%")
            else:
                print(f"      reason:          {status.get('reason', 'Unknown')}")
        else:
            if ob_cfg.get('enabled', False):
                print("  [5.5] order_book_data: 获取失败")
            else:
                print("  [5.5] order_book_data: 未启用 (order_book.enabled = false)")
        print()

    def _print_mtf_decision_data(self) -> None:
        """Print MTF 4H decision layer data."""
        td = self.ctx.technical_data
        mtf_decision = td.get('mtf_decision_layer')

        if mtf_decision:
            print("  [6] mtf_decision_layer (4H 决策层):")
            print(f"      rsi:             {mtf_decision.get('rsi', 0):.2f}")
            print(f"      macd:            {mtf_decision.get('macd', 0):.4f}")
            print(f"      sma_20:          ${mtf_decision.get('sma_20', 0):,.2f}")
            print(f"      sma_50:          ${mtf_decision.get('sma_50', 0):,.2f}")
            print(f"      bb_upper:        ${mtf_decision.get('bb_upper', 0):,.2f}")
            print(f"      bb_lower:        ${mtf_decision.get('bb_lower', 0):,.2f}")
            bb_pos = mtf_decision.get('bb_position', 0.5)
            print(f"      bb_position:     {bb_pos * 100:.1f}%")
        else:
            print("  [6] mtf_decision_layer (4H): 未初始化或未启用")
        print()

    def _print_mtf_trend_data(self) -> None:
        """Print MTF 1D trend layer data."""
        td = self.ctx.technical_data
        mtf_trend = td.get('mtf_trend_layer')

        if mtf_trend:
            print("  [7] mtf_trend_layer (1D 趋势层):")
            sma_200 = mtf_trend.get('sma_200', 0)
            print(f"      sma_200:         ${sma_200:,.2f}")
            if sma_200 > 0:
                price_vs_sma200 = ((self.ctx.current_price / sma_200 - 1) * 100)
                print(f"      price vs SMA200: {'+' if price_vs_sma200 >= 0 else ''}{price_vs_sma200:.2f}%")
            print(f"      macd:            {mtf_trend.get('macd', 0):.4f}")
            print(f"      macd_signal:     {mtf_trend.get('macd_signal', 0):.4f}")
        else:
            print("  [7] mtf_trend_layer (1D): 未初始化或未启用")
        print()

    def _print_position_data(self) -> None:
        """Print current position data."""
        pos = self.ctx.current_position

        if pos:
            print("  [8] current_position (当前持仓 - 25 fields v4.8.1):")
            print(f"      side:            {pos.get('side', 'N/A')}")
            print(f"      quantity:        {pos.get('quantity', 0)} BTC")
            entry = pos.get('entry_price') or pos.get('avg_px', 0)
            print(f"      entry_price:     ${entry:,.2f}")
            print(f"      unrealized_pnl:  ${pos.get('unrealized_pnl', 0):,.2f}")
            print(f"      pnl_percentage:  {pos.get('pnl_percentage', 0):+.2f}%")
            print(f"      duration_min:    {pos.get('duration_minutes', 0)}")

            # v4.7 fields
            liq_price = pos.get('liquidation_price')
            if liq_price:
                print(f"      liquidation:     ${liq_price:,.2f} (buffer: {pos.get('liquidation_buffer_pct', 0):.1f}%)")
            fr_cumulative = pos.get('funding_rate_cumulative_usd')
            if fr_cumulative:
                print(f"      funding_cost:    ${fr_cumulative:,.2f} (cumulative)")
            max_dd = pos.get('max_drawdown_pct')
            if max_dd:
                print(f"      max_drawdown:    {max_dd:.2f}%")
        else:
            print("  [8] current_position: None (无持仓)")
        print()

    def _print_account_context(self) -> None:
        """
        Print account context (v4.7).

        v4.8.1: Fixed to use correct field names matching production _get_account_context()
        """
        ac = self.ctx.account_context

        if ac:
            print("  [9] account_context (v4.7 Portfolio Risk - 13 fields):")

            # Core fields (8 fields) - v4.8.1 correct names
            print(f"      equity:             ${ac.get('equity', 0):,.2f}")
            print(f"      leverage:           {ac.get('leverage', 1)}x")
            print(f"      max_position_ratio: {ac.get('max_position_ratio', 0)*100:.0f}%")
            print(f"      max_position_value: ${ac.get('max_position_value', 0):,.2f}")
            print(f"      current_pos_value:  ${ac.get('current_position_value', 0):,.2f}")
            print(f"      available_capacity: ${ac.get('available_capacity', 0):,.2f}")
            print(f"      capacity_used_pct:  {ac.get('capacity_used_pct', 0):.1f}%")
            print(f"      can_add_position:   {ac.get('can_add_position', False)}")

            # v4.7 Portfolio-Level Risk Fields (5 fields)
            print()
            print("      [v4.7 Portfolio Risk]:")
            print(f"      unrealized_pnl:     ${ac.get('total_unrealized_pnl_usd', 0):,.2f}")

            liq_buffer = ac.get('liquidation_buffer_portfolio_min_pct')
            if liq_buffer is not None:
                risk_emoji = "🔴" if liq_buffer < 10 else "🟡" if liq_buffer < 15 else "🟢"
                print(f"      min_liq_buffer:     {risk_emoji} {liq_buffer:.1f}%")
            else:
                print(f"      min_liq_buffer:     N/A")

            daily_funding = ac.get('total_daily_funding_cost_usd')
            if daily_funding is not None:
                print(f"      daily_funding_cost: ${daily_funding:,.2f}")
            else:
                print(f"      daily_funding_cost: N/A")

            cumulative_funding = ac.get('total_cumulative_funding_paid_usd')
            if cumulative_funding is not None:
                print(f"      cumulative_funding: ${cumulative_funding:,.2f}")
            else:
                print(f"      cumulative_funding: N/A")

            can_safely = ac.get('can_add_position_safely', False)
            safety_emoji = "✅" if can_safely else "⚠️"
            print(f"      can_add_safely:     {safety_emoji} {can_safely}")
        else:
            print("  [9] account_context: None (未获取)")

    def should_skip(self) -> bool:
        return self.ctx.summary_mode


class MultiAgentAnalyzer(DiagnosticStep):
    """
    Run MultiAgent AI analysis.

    Implements the TradingAgents architecture with Bull/Bear/Judge/Risk phases.
    """

    name = "MultiAgent 层级决策 (TradingAgents 架构)"

    def run(self) -> bool:
        print("-" * 70)
        print("  📋 决策流程:")
        print("     Phase 1: Bull/Bear Debate (辩论)")
        print("     Phase 2: Judge (Portfolio Manager) Decision")
        print("     Phase 3: Risk Evaluation")
        print()

        try:
            from agents.multi_agent_analyzer import MultiAgentAnalyzer as MAAnalyzer

            cfg = self.ctx.strategy_config

            # Initialize with same parameters as deepseek_strategy.py
            self.ctx.multi_agent = MAAnalyzer(
                api_key=cfg.deepseek_api_key,
                model=cfg.deepseek_model,
                temperature=cfg.deepseek_temperature,
                debate_rounds=cfg.debate_rounds,
                memory_file="data/trading_memory.json",  # v3.12
            )

            print(f"  Model: {cfg.deepseek_model}")
            print(f"  Temperature: {cfg.deepseek_temperature}")
            print(f"  Debate Rounds: {cfg.debate_rounds}")
            print()
            print("  🐂 Bull Agent 分析中...")
            print("  🐻 Bear Agent 分析中...")
            print("  ⚖️ Judge Agent 判断中...")
            print("  🛡️ Risk Manager 评估中...")

            # Get MTF data if available
            order_flow_report, derivatives_report = self._get_mtf_data()

            # Run analysis (v4.7: include account_context for portfolio risk)
            signal_data = self.ctx.multi_agent.analyze(
                symbol=self.ctx.symbol,
                technical_report=self.ctx.technical_data,
                sentiment_report=self.ctx.sentiment_data,
                current_position=self.ctx.current_position,
                price_data=self.ctx.price_data,
                order_flow_report=order_flow_report,
                derivatives_report=derivatives_report,
                account_context=self.ctx.account_context,  # v4.7
            )

            self.ctx.signal_data = signal_data
            self.ctx.order_flow_report = order_flow_report
            self.ctx.derivatives_report = derivatives_report

            # Display results
            self._display_results(signal_data)

            return True

        except Exception as e:
            self.ctx.add_error(f"MultiAgent 分析失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _get_mtf_data(self) -> tuple:
        """Get order flow and derivatives data if available."""
        order_flow_report = None
        derivatives_report = None

        try:
            from utils.binance_kline_client import BinanceKlineClient
            from utils.order_flow_processor import OrderFlowProcessor
            from utils.coinalyze_client import CoinalyzeClient
            from utils.ai_data_assembler import AIDataAssembler
            from utils.sentiment_client import SentimentDataFetcher
            import os

            kline_client = BinanceKlineClient(timeout=10)
            processor = OrderFlowProcessor(logger=None)

            # Get Coinalyze config
            coinalyze_cfg = self.ctx.base_config.get('order_flow', {}).get('coinalyze', {})
            coinalyze_api_key = coinalyze_cfg.get('api_key') or os.getenv('COINALYZE_API_KEY')

            coinalyze_client = CoinalyzeClient(
                api_key=coinalyze_api_key,
                timeout=coinalyze_cfg.get('timeout', 10),
                max_retries=coinalyze_cfg.get('max_retries', 2),
                logger=None
            )

            sentiment_client = SentimentDataFetcher()

            assembler = AIDataAssembler(
                binance_kline_client=kline_client,
                order_flow_processor=processor,
                coinalyze_client=coinalyze_client,
                sentiment_client=sentiment_client,
                logger=None
            )

            assembled_data = assembler.assemble(
                technical_data=self.ctx.technical_data,
                position_data=self.ctx.current_position,
                symbol=self.ctx.symbol,
                interval=self.ctx.interval
            )

            order_flow_report = assembled_data.get('order_flow')
            derivatives_report = assembled_data.get('derivatives')

        except Exception as e:
            print(f"  ⚠️ MTF 数据获取失败: {e}, 继续使用基础数据")

        return order_flow_report, derivatives_report

    def _display_results(self, signal_data: Dict) -> None:
        """Display analysis results."""
        print()
        print("  🎯 Judge 最终决策:")
        judge_signal = signal_data.get('signal', 'N/A')
        print(f"     Signal: {judge_signal}")
        print(f"     Confidence: {signal_data.get('confidence', 'N/A')}")
        print(f"     Risk Level: {signal_data.get('risk_level', 'N/A')}")

        # SL/TP (v11.14: label HOLD signals)
        sltp_suffix = " (仅供参考，HOLD 不使用)" if judge_signal == 'HOLD' else ""
        sl = safe_float(signal_data.get('stop_loss'))
        tp = safe_float(signal_data.get('take_profit'))
        if sl:
            print(f"     Stop Loss: ${sl:,.2f}{sltp_suffix}")
        if tp:
            print(f"     Take Profit: ${tp:,.2f}{sltp_suffix}")

        # Judge decision details (v3.0 AI 完全自主)
        judge = signal_data.get('judge_decision', {})
        if judge:
            winning_side = judge.get('winning_side', 'N/A')
            print(f"     Winning Side: {winning_side}")
            print()
            print("     📋 Judge 决策 (v3.0 AI 完全自主):")
            print("        - AI 自主分析 Bull/Bear 辩论")
            print("        - AI 自主判断证据强度")
            print("        - 无硬编码规则或阈值")

            key_reasons = judge.get('key_reasons', [])
            if key_reasons:
                print()
                print(f"     Key Reasons:")
                for reason in key_reasons[:3]:
                    reason_text = reason[:80] + "..." if len(reason) > 80 else reason
                    print(f"       • {reason_text}")

            acknowledged_risks = judge.get('acknowledged_risks', [])
            if acknowledged_risks:
                print(f"     Acknowledged Risks:")
                for risk in acknowledged_risks[:2]:
                    risk_text = risk[:80] + "..." if len(risk) > 80 else risk
                    print(f"       • {risk_text}")

        # Debate summary
        if signal_data.get('debate_summary'):
            summary = signal_data['debate_summary']
            print()
            print(f"     Debate Summary:")
            summary_text = summary[:200] + "..." if len(summary) > 200 else summary
            print_wrapped(summary_text, indent="       ")

        # Reason
        reason = signal_data.get('reason', 'N/A')
        print()
        reason_text = reason[:200] + "..." if len(reason) > 200 else reason
        print(f"     Reason: {reason_text}")

        # Display debate transcript (v11.16)
        self._display_debate_transcript()

        # Display AI Prompt structure (v11.15)
        self._display_prompt_structure()

        print()
        print("  ✅ MultiAgent 分析完成")

    def _display_debate_transcript(self) -> None:
        """Display Bull/Bear debate transcript."""
        if not self.ctx.multi_agent:
            return

        if hasattr(self.ctx.multi_agent, 'get_last_debate') and callable(self.ctx.multi_agent.get_last_debate):
            debate_transcript = self.ctx.multi_agent.get_last_debate()
            if debate_transcript:
                print()
                print("  📜 辩论记录 (Bull/Bear Debate):")
                # Show first 600 characters
                if len(debate_transcript) > 600:
                    lines = debate_transcript[:600].split('\n')
                    for line in lines[:8]:
                        print(f"     {line[:100]}")
                    print(f"     [截断, 完整长度: {len(debate_transcript)} 字符]")
                else:
                    for line in debate_transcript.split('\n')[:8]:
                        print(f"     {line[:100]}")

    def _display_prompt_structure(self) -> None:
        """Display AI Prompt structure verification (v11.15)."""
        if not self.ctx.multi_agent:
            return

        if not hasattr(self.ctx.multi_agent, 'get_last_prompts'):
            return

        last_prompts = self.ctx.multi_agent.get_last_prompts()
        if not last_prompts:
            return

        print()
        print_box("AI Prompt 结构验证 (v3.12 System/User + Memory)", 65)
        print()

        for agent_name in ["bull", "bear", "judge", "risk"]:
            if agent_name not in last_prompts:
                continue

            prompts = last_prompts[agent_name]
            system_prompt = prompts.get("system", "")
            user_prompt = prompts.get("user", "")

            # Check INDICATOR_DEFINITIONS in System Prompt
            has_indicator_defs = "INDICATOR REFERENCE" in system_prompt

            # v11.15: Check PAST REFLECTIONS (memory) in Judge's User Prompt
            has_past_memories = "PAST REFLECTIONS" in user_prompt

            print(f"  [{agent_name.upper()}] Prompt 结构:")
            print(f"     System Prompt 长度: {len(system_prompt)} 字符")
            print(f"     User Prompt 长度:   {len(user_prompt)} 字符")
            print(f"     INDICATOR_DEFINITIONS 在 System: {'✅ 是' if has_indicator_defs else '❌ 否'}")

            # v11.15: Judge-specific check - memory system
            if agent_name == "judge":
                print(f"     PAST REFLECTIONS (记忆): {'✅ 是' if has_past_memories else '⚠️ 无历史交易'}")

            # Show System Prompt preview (first 150 chars)
            if system_prompt:
                preview = system_prompt[:150].replace('\n', ' ')
                print(f"     System 预览: {preview}...")

            # Show User Prompt preview (first 150 chars)
            if user_prompt:
                preview = user_prompt[:150].replace('\n', ' ')
                print(f"     User 预览:   {preview}...")

            # v11.15: For Judge, show memory section preview
            if agent_name == "judge" and has_past_memories:
                start_idx = user_prompt.find("PAST REFLECTIONS")
                if start_idx != -1:
                    end_idx = user_prompt.find("\n\nYOUR TASK", start_idx)
                    if end_idx == -1:
                        end_idx = start_idx + 300
                    memory_section = user_prompt[start_idx:end_idx]
                    memory_preview = memory_section[:200].replace('\n', '\n        ')
                    print(f"     📝 记忆内容预览:")
                    print(f"        {memory_preview}...")

            print()

        print("  📋 v3.12 架构要求:")
        print("     - System Prompt: 角色定义 + INDICATOR_DEFINITIONS (知识背景)")
        print("     - User Prompt: 原始数据 + 任务指令 (当前任务)")
        print("     - Judge Prompt: 包含 PAST REFLECTIONS (过去交易记忆)")


class SignalProcessor(DiagnosticStep):
    """
    Process and validate AI signal.

    Applies confidence filters and determines final signal.
    """

    name = "信号处理与验证"

    def run(self) -> bool:
        signal_data = self.ctx.signal_data
        cfg = self.ctx.strategy_config

        raw_signal = signal_data.get('signal', 'HOLD')
        confidence = signal_data.get('confidence', 'LOW')

        # Apply confidence filter
        confidence_order = ['LOW', 'MEDIUM', 'HIGH']
        min_conf = cfg.min_confidence_to_trade

        try:
            raw_idx = confidence_order.index(confidence.upper())
            min_idx = confidence_order.index(min_conf.upper())
            passes_threshold = raw_idx >= min_idx
        except ValueError:
            passes_threshold = False

        print(f"  原始信号: {raw_signal}")
        print(f"  信心等级: {confidence}")
        print(f"  最低要求: {min_conf}")
        print(f"  通过阈值: {'✅' if passes_threshold else '❌'}")

        if passes_threshold:
            self.ctx.final_signal = raw_signal
        else:
            self.ctx.final_signal = 'HOLD'
            print(f"  → 信心不足，最终信号改为 HOLD")

        print(f"  最终信号: {self.ctx.final_signal}")
        print("  ✅ 信号处理完成")

        return True


class OrderSimulator(DiagnosticStep):
    """
    Simulate order submission flow.

    Tests _submit_bracket_order parameter validation.
    """

    name = "订单提交流程模拟 (_submit_bracket_order)"

    def run(self) -> bool:
        print("-" * 70)

        signal = self.ctx.signal_data.get('signal', 'HOLD')
        confidence = self.ctx.signal_data.get('confidence', 'MEDIUM')

        print("  📋 订单提交前提检查:")
        print(f"     信号: {signal}")
        print(f"     信心: {confidence}")
        print(f"     当前价格: ${self.ctx.current_price:,.2f}")
        print()

        if signal == 'HOLD':
            print("  ℹ️ 信号为 HOLD，不会提交订单")
            return True

        try:
            self._simulate_order(signal, confidence)
            return True
        except Exception as e:
            self.ctx.add_error(f"订单模拟失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _simulate_order(self, signal: str, confidence: str) -> None:
        """Simulate order submission."""
        from strategy.trading_logic import (
            calculate_position_size,
            validate_multiagent_sltp,
            calculate_technical_sltp,
        )

        cfg = self.ctx.strategy_config

        # v4.8: Get equity and leverage from context (real Binance values)
        equity = getattr(self.ctx, 'account_balance', {}).get('total_balance', 0)
        if equity <= 0:
            equity = getattr(cfg, 'equity', 1000)

        leverage = getattr(self.ctx, 'binance_leverage', 10)
        max_position_ratio = getattr(cfg, 'max_position_ratio', 0.30)

        # v4.8: ai_controlled config
        confidence_mapping = {
            'HIGH': getattr(cfg, 'position_sizing_high_pct', 80),
            'MEDIUM': getattr(cfg, 'position_sizing_medium_pct', 50),
            'LOW': getattr(cfg, 'position_sizing_low_pct', 30),
        }

        calc_config = {
            'equity': equity,
            'leverage': leverage,
            'max_position_ratio': max_position_ratio,
            'min_trade_amount': getattr(cfg, 'min_trade_amount', 0.001),
            # v4.8: ai_controlled method
            'method': 'ai_controlled',
            'confidence_mapping': confidence_mapping,
            'default_size_pct': getattr(cfg, 'position_sizing_default_pct', 50),
        }

        # v4.8: Calculate position using ai_controlled formula
        max_usdt = equity * max_position_ratio * leverage
        size_pct = confidence_mapping.get(confidence.upper(), 50)
        usdt_amount = max_usdt * (size_pct / 100)

        # Apply remaining capacity in cumulative mode
        if self.ctx.current_position:
            current_value = self.ctx.current_position.get('position_value_usdt', 0)
            remaining = max(0, max_usdt - current_value)
            usdt_amount = min(usdt_amount, remaining)

        quantity = usdt_amount / self.ctx.current_price if self.ctx.current_price else 0

        # Validate SL/TP
        multi_sl = safe_float(self.ctx.signal_data.get('stop_loss'))
        multi_tp = safe_float(self.ctx.signal_data.get('take_profit'))

        print("  📋 SL/TP 验证流程:")
        print(f"     AI Judge SL: ${multi_sl:,.2f}" if multi_sl else "     AI Judge SL: None")
        print(f"     AI Judge TP: ${multi_tp:,.2f}" if multi_tp else "     AI Judge TP: None")
        print()

        support = self.ctx.technical_data.get('support', 0.0)
        resistance = self.ctx.technical_data.get('resistance', 0.0)
        use_sr = getattr(cfg, 'sl_use_support_resistance', True)
        sl_buffer = getattr(cfg, 'sl_buffer_pct', 0.001)

        if multi_sl and multi_tp:
            is_valid, final_sl, final_tp, reason = validate_multiagent_sltp(
                side=signal,
                multi_sl=multi_sl,
                multi_tp=multi_tp,
                entry_price=self.ctx.current_price,
            )
            print(f"     验证结果: {'✅ 通过' if is_valid else '❌ 失败'} - {reason}")

            if not is_valid:
                print("     ⚠️ AI SL/TP 验证失败，回退到技术分析")
                final_sl, final_tp, calc_method = calculate_technical_sltp(
                    side=signal,
                    entry_price=self.ctx.current_price,
                    support=support,
                    resistance=resistance,
                    confidence=confidence,
                    use_support_resistance=use_sr,
                    sl_buffer_pct=sl_buffer,
                )
        else:
            print("     ⚠️ AI 未提供 SL/TP，使用技术分析计算")
            final_sl, final_tp, calc_method = calculate_technical_sltp(
                side=signal,
                entry_price=self.ctx.current_price,
                support=support,
                resistance=resistance,
                confidence=confidence,
                use_support_resistance=use_sr,
                sl_buffer_pct=sl_buffer,
            )

        final_sl = safe_float(final_sl) or 0.0
        final_tp = safe_float(final_tp) or 0.0

        print()
        print("  📋 最终订单参数 (模拟):")
        print(f"     order_side: {'BUY' if signal in ['BUY', 'LONG'] else 'SELL'}")
        print(f"     quantity: {quantity:.6f} BTC")
        print(f"     entry_price: ${self.ctx.current_price:,.2f} (MARKET)")
        print(f"     sl_trigger_price: ${final_sl:,.2f}")
        print(f"     tp_price: ${final_tp:,.2f}")

        # Risk/reward analysis
        if final_sl > 0 and final_tp > 0:
            if signal in ['BUY', 'LONG']:
                sl_pct = ((self.ctx.current_price - final_sl) / self.ctx.current_price) * 100
                tp_pct = ((final_tp - self.ctx.current_price) / self.ctx.current_price) * 100
            else:
                sl_pct = ((final_sl - self.ctx.current_price) / self.ctx.current_price) * 100
                tp_pct = ((self.ctx.current_price - final_tp) / self.ctx.current_price) * 100

            rr_ratio = tp_pct / sl_pct if sl_pct > 0 else 0

            print()
            print("  📊 风险/收益分析:")
            print(f"     止损距离: {sl_pct:.2f}%")
            print(f"     止盈距离: {tp_pct:.2f}%")
            print(f"     风险/收益比: 1:{rr_ratio:.2f}")
            print(f"     最大亏损: ${quantity * self.ctx.current_price * sl_pct / 100:,.2f}")
            print(f"     最大盈利: ${quantity * self.ctx.current_price * tp_pct / 100:,.2f}")

        print()
        print("  ✅ 订单提交流程模拟完成")

    def should_skip(self) -> bool:
        return self.ctx.summary_mode


class PositionCalculator(DiagnosticStep):
    """
    Test position size calculation.

    Tests calculate_position_size() with v4.8 ai_controlled method.
    """

    name = "v4.8 仓位计算测试 (ai_controlled 累加模式)"

    def run(self) -> bool:
        print("-" * 70)

        try:
            from strategy.trading_logic import calculate_position_size

            cfg = self.ctx.strategy_config
            signal = self.ctx.signal_data.get('signal', 'HOLD')

            # v4.8: Get equity and leverage from context (real Binance values)
            equity = getattr(self.ctx, 'account_balance', {}).get('total_balance', 0)
            if equity <= 0:
                equity = getattr(cfg, 'equity', 1000)

            leverage = getattr(self.ctx, 'binance_leverage', 10)

            # v4.8: ai_controlled config
            max_position_ratio = getattr(cfg, 'max_position_ratio', 0.30)
            max_usdt = equity * max_position_ratio * leverage

            # v4.8 confidence mapping (percentage of max_usdt)
            confidence_mapping = {
                'HIGH': getattr(cfg, 'position_sizing_high_pct', 80),
                'MEDIUM': getattr(cfg, 'position_sizing_medium_pct', 50),
                'LOW': getattr(cfg, 'position_sizing_low_pct', 30),
            }

            calc_config = {
                'equity': equity,
                'leverage': leverage,
                'max_position_ratio': max_position_ratio,
                'min_trade_amount': getattr(cfg, 'min_trade_amount', 0.001),
                # v4.8: ai_controlled method
                'method': 'ai_controlled',
                'confidence_mapping': confidence_mapping,
                'default_size_pct': getattr(cfg, 'position_sizing_default_pct', 50),
            }

            print("  📋 v4.8 仓位计算配置 (ai_controlled):")
            print(f"     equity: ${equity:,.2f} (from Binance)")
            print(f"     leverage: {leverage}x (from Binance)")
            print(f"     max_position_ratio: {max_position_ratio*100:.0f}%")
            print(f"     max_position_value: ${max_usdt:,.2f}")
            print()

            print("  📋 v4.8 信心百分比映射:")
            for conf, pct in confidence_mapping.items():
                usdt = max_usdt * (pct / 100)
                btc = usdt / self.ctx.current_price if self.ctx.current_price else 0
                print(f"     {conf} ({pct}%): ${usdt:,.0f} ({btc:.6f} BTC)")
            print()

            # v4.8: Show cumulative mode status
            current_position_value = 0
            if self.ctx.current_position:
                current_position_value = self.ctx.current_position.get('position_value_usdt', 0)
            remaining_capacity = max(0, max_usdt - current_position_value)

            print("  📋 v4.8 累加模式状态:")
            print(f"     当前持仓价值: ${current_position_value:,.2f}")
            print(f"     可用容量: ${remaining_capacity:,.2f}")
            capacity_pct = (current_position_value / max_usdt * 100) if max_usdt > 0 else 0
            print(f"     容量使用率: {capacity_pct:.1f}%")
            print()

            if signal == 'HOLD':
                print("  📊 当前信号: HOLD (不计算仓位)")
                print()
                print("  📊 不同信心级别仓位参考 (假设 BUY/SELL 信号时):")
            else:
                print(f"  📊 当前信号: {signal}")
                print()
                print("  📊 不同信心级别仓位对比:")

            for conf_level in ['HIGH', 'MEDIUM', 'LOW']:
                # v4.8: Direct calculation using ai_controlled formula
                size_pct = confidence_mapping.get(conf_level, 50)
                usdt_amount = max_usdt * (size_pct / 100)

                # Apply remaining capacity limit in cumulative mode
                if self.ctx.current_position:
                    usdt_amount = min(usdt_amount, remaining_capacity)

                btc_qty = usdt_amount / self.ctx.current_price if self.ctx.current_price else 0

                capped = " (受限)" if usdt_amount < max_usdt * (size_pct / 100) else ""
                print(f"     {conf_level}: {btc_qty:.6f} BTC (${usdt_amount:,.2f}){capped}")

            print()
            print("  ✅ v4.8 仓位计算测试完成")
            return True

        except Exception as e:
            self.ctx.add_error(f"仓位计算测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def should_skip(self) -> bool:
        return self.ctx.summary_mode
