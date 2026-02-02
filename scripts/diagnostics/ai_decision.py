"""
AI Decision Module

Handles MultiAgent AI analysis and decision-making.
"""

from typing import Any, Dict, Optional

from .base import DiagnosticContext, DiagnosticStep, safe_float, print_wrapped


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
        print("  📊 决策结果:")
        print(f"     信号: {signal_data.get('signal', 'N/A')}")
        print(f"     信心: {signal_data.get('confidence', 'N/A')}")
        print(f"     风险: {signal_data.get('risk_level', 'N/A')}")

        # Judge decision details
        judge = signal_data.get('judge_decision', {})
        if judge:
            print(f"     胜出方: {judge.get('winning_side', 'N/A')}")

            key_reasons = judge.get('key_reasons', [])
            if key_reasons:
                print("     关键理由:")
                for reason in key_reasons[:3]:
                    print(f"       • {reason[:60]}...")

        # SL/TP
        sl = signal_data.get('stop_loss')
        tp = signal_data.get('take_profit')
        if sl:
            print(f"     止损: ${safe_float(sl):,.2f}" if safe_float(sl) else "     止损: N/A")
        if tp:
            print(f"     止盈: ${safe_float(tp):,.2f}" if safe_float(tp) else "     止盈: N/A")

        print()
        print("  ✅ MultiAgent 分析完成")


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
            print(f"     max_usdt: ${max_usdt:,.2f}")
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
            print(f"     剩余可加仓: ${remaining_capacity:,.2f}")
            capacity_pct = (current_position_value / max_usdt * 100) if max_usdt > 0 else 0
            print(f"     已用容量: {capacity_pct:.1f}%")
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
