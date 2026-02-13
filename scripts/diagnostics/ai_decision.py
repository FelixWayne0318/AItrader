"""
AI Decision Module

Handles MultiAgent AI analysis and decision-making:
- AI input data validation (13 categories)
- Sequential AI call execution (6 DeepSeek API calls)
- Prompt structure verification
- Bull/Bear debate transcript display
"""

from typing import Any, Dict, Optional

import time

from .base import DiagnosticContext, DiagnosticStep, safe_float, print_wrapped, print_box, step_timer


class AIInputDataValidator(DiagnosticStep):
    """
    Validate and display all 13 data categories passed to MultiAgent AI.

    Shows exactly what data the AI receives for decision-making,
    matching the live system's analyze() call parameters.
    """

    name = "AI 输入数据验证 (传给 MultiAgent, 13 类数据)"

    def run(self) -> bool:
        print("-" * 70)
        print()
        print_box("AI 输入数据验证 (传给 MultiAgent, 13 类)", 65)
        print()

        # v3.0.0: Fetch all external data FIRST (matches live on_timer flow)
        self._fetch_all_data()

        # [1] Technical data (15M)
        self._print_technical_data()

        # [2] Sentiment data
        self._print_sentiment_data()

        # [3] Price data (v3.6)
        self._print_price_data()

        # [4] Order flow report (Binance klines)
        self._print_order_flow_data()

        # [5] Derivatives report (Coinalyze)
        self._print_derivatives_data()

        # [6] Binance Derivatives (Top Traders, Taker Ratio) v3.21
        self._print_binance_derivatives_data()

        # [7] Order book data (v3.7)
        self._print_orderbook_data()

        # [8] MTF Decision layer (4H)
        self._print_mtf_decision_data()

        # [9] MTF Trend layer (1D)
        self._print_mtf_trend_data()

        # [10] Current position
        self._print_position_data()

        # [11] Account context (v4.7)
        self._print_account_context()

        # [12] Historical context (EVALUATION_FRAMEWORK v3.0.1)
        self._print_historical_context()

        # [13] S/R Zones (v2.6.0) + bars_data for Swing Detection
        self._print_sr_zones_data()

        print()
        print("  ────────────────────────────────────────────────────────────────")
        print("  ✅ AI 输入数据验证完成 (13 类数据)")
        return True

    def _fetch_all_data(self) -> None:
        """
        Fetch ALL external data before printing — 100% matches live on_timer() flow.

        Live system data fetch order (deepseek_strategy.py:1620-1731):
        1. Order flow (Binance klines → OrderFlowProcessor)
        2. Derivatives (Coinalyze OI/Funding/Liquidations)
        3. Order book (if enabled)
        4. Binance derivatives (Top Traders, Taker Ratio) ← was MISSING
        5. S/R bars (120 bars for Swing Point detection) ← was MISSING
        6. kline_ohlcv (20 bars OHLCV for AI) ← was MISSING
        7. historical_context (35-bar trend data)
        8. S/R Zones calculation
        """
        import os
        timings = self.ctx.step_timings

        try:
            from utils.binance_kline_client import BinanceKlineClient
            from utils.order_flow_processor import OrderFlowProcessor
            from utils.coinalyze_client import CoinalyzeClient
            from utils.ai_data_assembler import AIDataAssembler
            from utils.sentiment_client import SentimentDataFetcher

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

            # ========== Order book client (v3.7) ==========
            order_book_cfg = self.ctx.base_config.get('order_book', {})
            order_book_enabled = order_book_cfg.get('enabled', False)
            binance_orderbook = None
            orderbook_processor = None

            if order_book_enabled:
                try:
                    from utils.binance_orderbook_client import BinanceOrderBookClient
                    from utils.orderbook_processor import OrderBookProcessor

                    ob_api_cfg = order_book_cfg.get('api', {})
                    ob_proc_cfg = order_book_cfg.get('processing', {})

                    binance_orderbook = BinanceOrderBookClient(
                        timeout=ob_api_cfg.get('timeout', 10),
                        max_retries=ob_api_cfg.get('max_retries', 2),
                        logger=None
                    )

                    weighted_obi_cfg = ob_proc_cfg.get('weighted_obi', {})
                    anomaly_cfg = ob_proc_cfg.get('anomaly_detection', {})
                    slippage_amounts = ob_proc_cfg.get('slippage_amounts', [0.1, 0.5, 1.0])

                    weighted_obi_config = {
                        "base_decay": weighted_obi_cfg.get('base_decay', 0.8),
                        "adaptive": weighted_obi_cfg.get('adaptive', True),
                        "volatility_factor": weighted_obi_cfg.get('volatility_factor', 0.1),
                        "min_decay": weighted_obi_cfg.get('min_decay', 0.5),
                        "max_decay": weighted_obi_cfg.get('max_decay', 0.95),
                    }
                    orderbook_processor = OrderBookProcessor(
                        base_anomaly_threshold=anomaly_cfg.get('base_threshold', 3.0),
                        slippage_amounts=slippage_amounts,
                        weighted_obi_config=weighted_obi_config,
                        history_size=ob_proc_cfg.get('history', {}).get('size', 10),
                        logger=None
                    )
                except ImportError as e:
                    print(f"  ⚠️ Order book modules not available: {e}")

            # ========== Binance Derivatives client (v3.21) ==========
            binance_derivatives_client = None
            try:
                from utils.binance_derivatives_client import BinanceDerivativesClient
                bd_cfg = self.ctx.base_config.get('binance_derivatives', {})
                binance_derivatives_client = BinanceDerivativesClient(
                    timeout=bd_cfg.get('timeout', 10),
                    logger=None,
                    config=self.ctx.base_config,
                )
            except ImportError as e:
                print(f"  ⚠️ BinanceDerivativesClient not available: {e}")

            # ========== AIDataAssembler (matches live system) ==========
            assembler = AIDataAssembler(
                binance_kline_client=kline_client,
                order_flow_processor=processor,
                coinalyze_client=coinalyze_client,
                sentiment_client=sentiment_client,
                binance_derivatives_client=binance_derivatives_client,
                binance_orderbook_client=binance_orderbook,
                orderbook_processor=orderbook_processor,
                logger=None
            )

            with step_timer("AIDataAssembler.assemble()", timings):
                assembled_data = assembler.assemble(
                    technical_data=self.ctx.technical_data,
                    position_data=self.ctx.current_position,
                    symbol=self.ctx.symbol,
                    interval=self.ctx.interval
                )

            # Store ALL data in context (matches live system exactly)
            self.ctx.order_flow_report = assembled_data.get('order_flow')
            self.ctx.derivatives_report = assembled_data.get('derivatives')
            self.ctx.orderbook_report = assembled_data.get('order_book')

            # v3.21: Binance Derivatives (Top Traders, Taker Ratio)
            if assembled_data.get('binance_derivatives'):
                self.ctx.binance_derivatives_data = assembled_data.get('binance_derivatives')
            elif binance_derivatives_client:
                # Fallback: fetch directly if assembler didn't include it
                try:
                    with step_timer("BinanceDerivatives.fetch_all()", timings):
                        bd_data = binance_derivatives_client.fetch_all()
                    if bd_data:
                        self.ctx.binance_derivatives_data = bd_data
                except Exception as bd_err:
                    print(f"  ⚠️ Binance derivatives fetch failed: {bd_err}")

            # Order book status logging
            ob_data = assembled_data.get('order_book')
            if ob_data:
                ob_status = ob_data.get('_status', {})
                ob_code = ob_status.get('code', 'UNKNOWN')
                if ob_code != 'OK':
                    ob_msg = ob_status.get('message', 'No message')
                    print(f"  ℹ️ Order book status: {ob_code} - {ob_msg}")
            else:
                metadata = assembled_data.get('_metadata', {})
                ob_enabled = metadata.get('orderbook_enabled', False)
                ob_status = metadata.get('orderbook_status', 'UNKNOWN')
                print(f"  ℹ️ Order book data is None (enabled={ob_enabled}, status={ob_status})")

        except Exception as e:
            print(f"  ⚠️ AIDataAssembler 数据获取失败: {e}")
            import traceback
            traceback.print_exc()

        # ========== Indicator-based data (matches live on_timer enrichment) ==========
        if hasattr(self.ctx, 'indicator_manager') and self.ctx.indicator_manager:
            # v3.21: kline_ohlcv (20 bars) — live line 1613
            try:
                kline_ohlcv = self.ctx.indicator_manager.get_kline_data(count=20)
                if kline_ohlcv:
                    self.ctx.technical_data['kline_ohlcv'] = kline_ohlcv
                    print(f"  ℹ️ kline_ohlcv: {len(kline_ohlcv)} bars added to technical_data")
            except Exception as e:
                print(f"  ⚠️ kline_ohlcv 获取失败: {e}")

            # v3.0: S/R bars (120 bars for Swing Point detection) — live line 1712
            try:
                sr_bars = self.ctx.indicator_manager.get_kline_data(count=120)
                if sr_bars:
                    self.ctx.sr_bars_data = sr_bars
                    print(f"  ℹ️ sr_bars_data: {len(sr_bars)} bars for S/R detection")
            except Exception as e:
                print(f"  ⚠️ sr_bars_data 获取失败: {e}")

            # historical_context (35-bar trend data) — live line 1599
            try:
                historical_context = self.ctx.indicator_manager.get_historical_context(count=35)
                if historical_context and historical_context.get('trend_direction') not in ['INSUFFICIENT_DATA', 'ERROR']:
                    self.ctx.historical_context = historical_context
                    if self.ctx.technical_data:
                        self.ctx.technical_data['historical_context'] = historical_context
                else:
                    self.ctx.historical_context = None
            except Exception as hc_err:
                print(f"  ⚠️ Historical context 获取失败: {hc_err}")
                self.ctx.historical_context = None
        else:
            self.ctx.historical_context = None

        # ========== Enrich technical_data (matches live on_timer lines 1551-1575) ==========
        td = self.ctx.technical_data
        if td:
            td['timeframe'] = '15M'
            td['price'] = self.ctx.current_price
            if self.ctx.price_data:
                td['price_change'] = self.ctx.price_data.get('price_change', 0)
                td['period_high'] = self.ctx.price_data.get('period_high', 0)
                td['period_low'] = self.ctx.price_data.get('period_low', 0)
                td['period_change_pct'] = self.ctx.price_data.get('period_change_pct', 0)
                td['period_hours'] = self.ctx.price_data.get('period_hours', 0)

        # ========== S/R Zones calculation ==========
        try:
            from utils.sr_zone_calculator import SRZoneCalculator

            td = self.ctx.technical_data
            sr_calculator = SRZoneCalculator()

            bb_data = {
                'upper': td.get('bb_upper', 0),
                'lower': td.get('bb_lower', 0),
                'middle': td.get('sma_20', 0),
            }
            sma_data = {
                'sma_50': td.get('sma_50', 0),
                'sma_200': td.get('sma_200', 0),
            }

            orderbook_anomalies = None
            if self.ctx.orderbook_report and self.ctx.orderbook_report.get('_status', {}).get('code') == 'OK':
                orderbook_anomalies = self.ctx.orderbook_report.get('anomalies', {})

            sr_result = sr_calculator.calculate_with_detailed_report(
                current_price=self.ctx.current_price,
                bb_data=bb_data,
                sma_data=sma_data,
                orderbook_anomalies=orderbook_anomalies,
                bars_data=self.ctx.sr_bars_data,
                bars_data_4h=self.ctx.bars_data_4h,
                bars_data_1d=self.ctx.bars_data_1d,
                daily_bar=self.ctx.daily_bar,
                weekly_bar=self.ctx.weekly_bar,
            )

            self.ctx.sr_zones_data = sr_result
            print(f"  ℹ️ S/R Zones: {len(sr_result.get('support_zones', []))} 支撑, {len(sr_result.get('resistance_zones', []))} 阻力")

        except Exception as sr_err:
            print(f"  ⚠️ S/R Zones 计算失败: {sr_err}")
            self.ctx.sr_zones_data = None

        print()

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

            # v5.1: Binance funding rate (settled + predicted)
            if self.ctx.binance_funding_rate:
                bfr = self.ctx.binance_funding_rate
                print(f"      [Binance FR] Settled: {bfr.get('funding_rate_pct', 0):.4f}% | Predicted: {bfr.get('predicted_rate_pct', 0):.4f}%")

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

    def _print_binance_derivatives_data(self) -> None:
        """Print Binance Derivatives data (Top Traders, Taker Ratio) v3.21."""
        bd = getattr(self.ctx, 'binance_derivatives_data', None)

        if bd:
            print("  [6] binance_derivatives (大户数据 v3.21):")
            # Top Traders Long/Short Position Ratio
            top_pos = bd.get('top_long_short_position', {})
            latest_pos = top_pos.get('latest')
            if latest_pos:
                ratio = float(latest_pos.get('longShortRatio', 1))
                long_pct = float(latest_pos.get('longAccount', 50))
                short_pct = float(latest_pos.get('shortAccount', 50))
                print(f"      Top Traders Position L/S:  {ratio:.2f} (Long {long_pct:.1f}% / Short {short_pct:.1f}%)")
            else:
                print(f"      Top Traders Position L/S:  N/A")

            # Top Traders Long/Short Account Ratio
            top_acc = bd.get('top_long_short_account', {})
            latest_acc = top_acc.get('latest')
            if latest_acc:
                ratio = float(latest_acc.get('longShortRatio', 1))
                print(f"      Top Traders Account L/S:   {ratio:.2f}")
            else:
                print(f"      Top Traders Account L/S:   N/A")

            # Taker Buy/Sell Ratio
            taker = bd.get('taker_long_short', {})
            latest_taker = taker.get('latest')
            if latest_taker:
                ratio = float(latest_taker.get('buySellRatio', 1))
                print(f"      Taker Buy/Sell Ratio:      {ratio:.2f}")
            else:
                print(f"      Taker Buy/Sell Ratio:      N/A")

            # Trends
            trends = bd.get('trends', {})
            if trends:
                print(f"      Position Trend:            {trends.get('position_trend', 'N/A')}")
                print(f"      Account Trend:             {trends.get('account_trend', 'N/A')}")
                print(f"      Taker Trend:               {trends.get('taker_trend', 'N/A')}")
        else:
            print("  [6] binance_derivatives: None (未获取)")
        print()

    def _print_orderbook_data(self) -> None:
        """Print order book data."""
        ob = self.ctx.orderbook_report
        ob_cfg = self.ctx.base_config.get('order_book', {})

        if ob:
            status = ob.get('_status', {})
            status_code = status.get('code', 'UNKNOWN')
            print(f"  [7] order_book_data (订单簿深度 v3.7) [状态: {status_code}]:")

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
                    print("      ℹ️ 注: 诊断脚本每次新建实例，无历史数据正常")
                    print("         实盘服务中 OrderBookProcessor 会累积历史")

                bid_near_5 = gradient.get('bid_near_5', 0) * 100
                ask_near_5 = gradient.get('ask_near_5', 0) * 100
                print(f"      Bid pressure:    near_5={bid_near_5:.1f}%")
                print(f"      Ask pressure:    near_5={ask_near_5:.1f}%")
                print(f"      Spread:          {liquidity.get('spread_pct', 0):.4f}%")
            else:
                # v2.4.4: 修复 reason → message (数据结构使用 message 字段)
                print(f"      reason:          {status.get('message', 'Unknown')}")
        else:
            if ob_cfg.get('enabled', False):
                print("  [7] order_book_data: 获取失败")
            else:
                print("  [7] order_book_data: 未启用 (order_book.enabled = false)")
        print()

    def _print_mtf_decision_data(self) -> None:
        """Print MTF 4H decision layer data."""
        td = self.ctx.technical_data
        mtf_decision = td.get('mtf_decision_layer')

        if mtf_decision:
            print("  [8] mtf_decision_layer (4H 决策层):")
            print(f"      rsi:             {mtf_decision.get('rsi', 0):.2f}")
            print(f"      macd:            {mtf_decision.get('macd', 0):.4f}")
            print(f"      sma_20:          ${mtf_decision.get('sma_20', 0):,.2f}")
            print(f"      sma_50:          ${mtf_decision.get('sma_50', 0):,.2f}")
            print(f"      bb_upper:        ${mtf_decision.get('bb_upper', 0):,.2f}")
            print(f"      bb_lower:        ${mtf_decision.get('bb_lower', 0):,.2f}")
            bb_pos = mtf_decision.get('bb_position', 0.5)
            print(f"      bb_position:     {bb_pos * 100:.1f}%")
        else:
            print("  [8] mtf_decision_layer (4H): 未初始化或未启用")
        print()

    def _print_mtf_trend_data(self) -> None:
        """Print MTF 1D trend layer data."""
        td = self.ctx.technical_data
        mtf_trend = td.get('mtf_trend_layer')

        if mtf_trend:
            print("  [9] mtf_trend_layer (1D 趋势层):")
            sma_200 = mtf_trend.get('sma_200', 0)
            print(f"      sma_200:         ${sma_200:,.2f}")
            if sma_200 > 0:
                price_vs_sma200 = ((self.ctx.current_price / sma_200 - 1) * 100)
                print(f"      price vs SMA200: {'+' if price_vs_sma200 >= 0 else ''}{price_vs_sma200:.2f}%")
            print(f"      macd:            {mtf_trend.get('macd', 0):.4f}")
            print(f"      macd_signal:     {mtf_trend.get('macd_signal', 0):.4f}")
        else:
            print("  [9] mtf_trend_layer (1D): 未初始化或未启用")
        print()

    def _print_position_data(self) -> None:
        """Print current position data."""
        pos = self.ctx.current_position

        if pos:
            print("  [10] current_position (当前持仓 - 25 fields v4.8.1):")
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
            print("  [10] current_position: None (无持仓)")
        print()

    def _print_account_context(self) -> None:
        """
        Print account context (v4.7).

        v4.8.1: Fixed to use correct field names matching production _get_account_context()
        """
        ac = self.ctx.account_context

        if ac:
            print("  [11] account_context (v4.7 Portfolio Risk - 13 fields):")

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
            print("  [11] account_context: None (未获取)")
        print()

    def _print_historical_context(self) -> None:
        """
        Print historical context data (v2.5.0 / EVALUATION_FRAMEWORK v3.0.1).

        AI needs trend data for proper trend analysis, not isolated values.
        Uses count=35 to ensure MACD history has enough data (slow_period=26).
        """
        hc = getattr(self.ctx, 'historical_context', None)

        if hc and hc.get('trend_direction') not in ['INSUFFICIENT_DATA', 'ERROR', None]:
            print("  [12] historical_context (35-bar 趋势数据 v3.0.1):")
            print(f"      trend_direction:    {hc.get('trend_direction', 'N/A')}")
            print(f"      momentum_shift:     {hc.get('momentum_shift', 'N/A')}")
            print(f"      data_points:        {hc.get('data_points', 0)}")

            # Format trend arrays (show last 5 values)
            def format_recent(values, fmt=".2f"):
                if not values or not isinstance(values, list):
                    return "N/A"
                recent = values[-5:] if len(values) >= 5 else values
                return " → ".join([f"{v:{fmt}}" for v in recent])

            price_trend = hc.get('price_trend', [])
            rsi_trend = hc.get('rsi_trend', [])
            macd_trend = hc.get('macd_trend', [])
            volume_trend = hc.get('volume_trend', [])

            print()
            print("      📈 趋势数据 (最近 5 值):")
            print(f"      price_trend:        {format_recent(price_trend)}")
            print(f"      rsi_trend:          {format_recent(rsi_trend)}")
            print(f"      macd_trend:         {format_recent(macd_trend, '.4f')}")
            print(f"      volume_trend:       {format_recent(volume_trend, '.0f')}")

            # Statistics
            if price_trend and len(price_trend) >= 2:
                price_change = ((price_trend[-1] / price_trend[0]) - 1) * 100 if price_trend[0] > 0 else 0
                trend_emoji = "📈" if price_change > 0 else "📉" if price_change < 0 else "➡️"
                print()
                print(f"      {trend_emoji} 35-bar 价格变化: {price_change:+.2f}%")

            if rsi_trend:
                avg_rsi = sum(rsi_trend) / len(rsi_trend)
                rsi_emoji = "🔴" if avg_rsi > 70 else "🟢" if avg_rsi < 30 else "🟡"
                print(f"      {rsi_emoji} 平均 RSI: {avg_rsi:.1f}")

            print()
            print("      ℹ️ 数据来源: indicator_manager.get_historical_context()")
            print("      ℹ️ 参考: EVALUATION_FRAMEWORK.md Section 2.1 数据完整性")
        else:
            if hasattr(self.ctx, 'indicator_manager') and self.ctx.indicator_manager:
                print("  [12] historical_context: 数据不足 (需要至少 35 根 K线)")
                print("      ℹ️ 诊断脚本刚启动，历史数据可能不足")
                print("      ℹ️ 实盘服务运行后会自动累积数据")
            else:
                print("  [12] historical_context: indicator_manager 未初始化")

    def _print_sr_zones_data(self) -> None:
        """
        Print S/R Zone data (v2.6.0).

        Shows support/resistance zones calculated from Swing Points, Volume Profile,
        Pivot Points, Order Walls, and Round Numbers (v4.0+).
        This data is used for SL/TP calculation when AI doesn't provide valid values.
        """
        sr_data = getattr(self.ctx, 'sr_zones_data', None)

        if sr_data:
            print("  [13] S/R Zones (支撑/阻力区 v2.6.0):")

            # Nearest support
            nearest_sup = sr_data.get('nearest_support')
            if nearest_sup and hasattr(nearest_sup, 'price_center'):
                wall_info = f" [Order Wall: {nearest_sup.wall_size_btc:.1f} BTC]" if nearest_sup.has_order_wall else ""
                print(f"      最近支撑: ${nearest_sup.price_center:,.0f} ({nearest_sup.distance_pct:.1f}% away)")
                print(f"        强度: {nearest_sup.strength} | 级别: {nearest_sup.level}{wall_info}")
                print(f"        来源: {', '.join(nearest_sup.sources)}")
            else:
                print("      最近支撑: N/A")

            print()

            # Nearest resistance
            nearest_res = sr_data.get('nearest_resistance')
            if nearest_res and hasattr(nearest_res, 'price_center'):
                wall_info = f" [Order Wall: {nearest_res.wall_size_btc:.1f} BTC]" if nearest_res.has_order_wall else ""
                print(f"      最近阻力: ${nearest_res.price_center:,.0f} ({nearest_res.distance_pct:.1f}% away)")
                print(f"        强度: {nearest_res.strength} | 级别: {nearest_res.level}{wall_info}")
                print(f"        来源: {', '.join(nearest_res.sources)}")
            else:
                print("      最近阻力: N/A")

            print()

            # Hard control status (v3.16: AI 自主决策，非本地覆盖)
            hard_control = sr_data.get('hard_control', {})
            if hard_control.get('block_long') or hard_control.get('block_short'):
                print("      ⚠️ S/R Zone 建议 (v3.16 由 AI 自主判断):")
                if hard_control.get('block_long'):
                    print("        📋 建议避免 LONG (太靠近 HIGH 强度阻力位)")
                if hard_control.get('block_short'):
                    print("        📋 建议避免 SHORT (太靠近 HIGH 强度支撑位)")
                if hard_control.get('reason'):
                    print(f"        原因: {hard_control['reason']}")
                print("        ℹ️ Risk Manager (AI) 可自主决定是否遵守")
            else:
                print("      ✅ 硬风控: 无限制")

            print()

            # R/R Analysis (if both S/R available)
            if nearest_sup and nearest_res and hasattr(nearest_sup, 'price_center') and hasattr(nearest_res, 'price_center'):
                price = self.ctx.current_price
                support = nearest_sup.price_center
                resistance = nearest_res.price_center

                upside = resistance - price
                downside = price - support

                if downside > 0:
                    long_rr = upside / downside
                    rr_status = "✅ FAVORABLE" if long_rr >= 1.5 else "⚠️ UNFAVORABLE"
                    print(f"      LONG R/R: {long_rr:.2f}:1 {rr_status}")
                if upside > 0:
                    short_rr = downside / upside
                    rr_status = "✅ FAVORABLE" if short_rr >= 1.5 else "⚠️ UNFAVORABLE"
                    print(f"      SHORT R/R: {short_rr:.2f}:1 {rr_status}")

            print()
            print("      ℹ️ 数据来源: SRZoneCalculator (Swing + VP + Pivot + Order Walls)")
        else:
            print("  [13] S/R Zones: 未计算 (可能缺少技术数据)")

        print()

    def should_skip(self) -> bool:
        return self.ctx.summary_mode


class MultiAgentAnalyzer(DiagnosticStep):
    """
    Run MultiAgent AI analysis.

    Implements the TradingAgents architecture with sequential DeepSeek API calls.
    With debate_rounds=N, total API calls = 2*N (Bull/Bear) + 1 (Judge) + 1 (Risk).
    Default debate_rounds=2 → 6 sequential API calls.
    """

    name = "MultiAgent 层级决策 (TradingAgents 架构)"

    def run(self) -> bool:
        print("-" * 70)
        print()
        print_box("MultiAgent 层级决策 (顺序 AI 调用)", 65)
        print()
        print("  📋 决策流程 (顺序执行, 100% 匹配实盘):")
        print("     ┌─ Round 1: Bull Analyst → Bear Analyst  (2 API calls)")
        print("     ├─ Round 2: Bull Analyst → Bear Analyst  (2 API calls)")
        print("     ├─ Judge (Portfolio Manager) Decision    (1 API call)")
        print("     └─ Risk Manager Evaluation               (1 API call)")
        print("     ─────────────────────────────────────────────────────")
        print("     合计: 2×debate_rounds + 2 次 DeepSeek 顺序调用")
        print()

        try:
            from agents.multi_agent_analyzer import MultiAgentAnalyzer as MAAnalyzer

            cfg = self.ctx.strategy_config
            timings = self.ctx.step_timings

            # Initialize with same parameters as deepseek_strategy.py
            self.ctx.multi_agent = MAAnalyzer(
                api_key=cfg.deepseek_api_key,
                model=cfg.deepseek_model,
                temperature=cfg.deepseek_temperature,
                debate_rounds=cfg.debate_rounds,
                memory_file="data/trading_memory.json",  # v3.12
            )

            total_calls = 2 * cfg.debate_rounds + 2  # Bull/Bear per round + Judge + Risk
            print(f"  Model: {cfg.deepseek_model}")
            print(f"  Temperature: {cfg.deepseek_temperature}")
            print(f"  Debate Rounds: {cfg.debate_rounds}")
            print(f"  Total API Calls: {total_calls} (顺序执行)")
            print()

            # Data completeness check (all 15 analyze() parameters)
            params = {
                'symbol': self.ctx.symbol,
                'technical_report': self.ctx.technical_data,
                'sentiment_report': self.ctx.sentiment_data,
                'current_position': self.ctx.current_position,
                'price_data': self.ctx.price_data,
                'order_flow_report': self.ctx.order_flow_report,
                'derivatives_report': self.ctx.derivatives_report,
                'binance_derivatives_report': getattr(self.ctx, 'binance_derivatives_data', None),
                'orderbook_report': self.ctx.orderbook_report,
                'account_context': self.ctx.account_context,
                'bars_data': self.ctx.sr_bars_data,
                'bars_data_4h': self.ctx.bars_data_4h,
                'bars_data_1d': self.ctx.bars_data_1d,
                'daily_bar': self.ctx.daily_bar,
                'weekly_bar': self.ctx.weekly_bar,
            }

            print("  📊 analyze() 参数完整性检查 (vs 实盘):")
            live_params = [
                'symbol', 'technical_report', 'sentiment_report',
                'current_position', 'price_data', 'order_flow_report',
                'derivatives_report', 'binance_derivatives_report',
                'orderbook_report', 'account_context', 'bars_data',
                'bars_data_4h', 'bars_data_1d', 'daily_bar', 'weekly_bar',
            ]
            for param_name in live_params:
                value = params[param_name]
                if value is not None:
                    if isinstance(value, dict):
                        status = f"✅ ({len(value)} fields)"
                    elif isinstance(value, list):
                        status = f"✅ ({len(value)} items)"
                    elif isinstance(value, str):
                        status = f"✅ ({value})"
                    else:
                        status = f"✅"
                else:
                    status = "⚠️ None"
                print(f"     {param_name:32s} {status}")
            print()

            # Run analysis with all parameters (6 sequential API calls)
            print("  Running AI analysis...")
            t_start = time.monotonic()

            signal_data = self.ctx.multi_agent.analyze(
                symbol=self.ctx.symbol,
                technical_report=self.ctx.technical_data,
                sentiment_report=self.ctx.sentiment_data,
                current_position=self.ctx.current_position,
                price_data=self.ctx.price_data,
                order_flow_report=self.ctx.order_flow_report,
                derivatives_report=self.ctx.derivatives_report,
                binance_derivatives_report=getattr(self.ctx, 'binance_derivatives_data', None),
                orderbook_report=self.ctx.orderbook_report,
                account_context=self.ctx.account_context,
                bars_data=self.ctx.sr_bars_data,
                # v4.0: MTF bars for S/R pivot + volume profile + swing detection
                bars_data_4h=self.ctx.bars_data_4h,
                bars_data_1d=self.ctx.bars_data_1d,
                daily_bar=self.ctx.daily_bar,
                weekly_bar=self.ctx.weekly_bar,
            )

            t_elapsed = time.monotonic() - t_start
            timings['MultiAgent.analyze() total'] = t_elapsed
            print(f"  [{t_elapsed:.1f}s] AI analysis complete")

            self.ctx.signal_data = signal_data

            # Display call trace summary
            self._display_call_trace_summary()

            # Save full call trace to context for log export
            if hasattr(self.ctx.multi_agent, 'get_call_trace'):
                self.ctx.ai_call_trace = self.ctx.multi_agent.get_call_trace()

            # Display results
            self._display_results(signal_data)

            return True

        except Exception as e:
            self.ctx.add_error(f"MultiAgent 分析失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _display_call_trace_summary(self) -> None:
        """Display a summary table of all AI API calls with timing and tokens."""
        if not hasattr(self.ctx.multi_agent, 'get_call_trace'):
            return

        trace = self.ctx.multi_agent.get_call_trace()
        if not trace:
            return

        print()
        print_box(f"AI API 调用追踪 ({len(trace)} 次顺序调用)", 65)
        print()
        print(f"  {'#':<4} {'Agent':<16} {'耗时':>6} {'Tokens':>10} {'Prompt':>8} {'Reply':>8}")
        print(f"  {'─'*4} {'─'*16} {'─'*6} {'─'*10} {'─'*8} {'─'*8}")

        total_time = 0
        total_tokens = 0
        for i, call in enumerate(trace, 1):
            label = call.get('label', f'call_{i}')
            elapsed = call.get('elapsed_sec', 0)
            tokens = call.get('tokens', {})
            prompt_tk = tokens.get('prompt', 0)
            completion_tk = tokens.get('completion', 0)
            total_tk = tokens.get('total', 0)
            total_time += elapsed
            total_tokens += total_tk
            print(f"  {i:<4} {label:<16} {elapsed:>5.1f}s {total_tk:>10,} {prompt_tk:>8,} {completion_tk:>8,}")

        print(f"  {'─'*4} {'─'*16} {'─'*6} {'─'*10} {'─'*8} {'─'*8}")
        print(f"  {'':4} {'TOTAL':<16} {total_time:>5.1f}s {total_tokens:>10,}")
        print()
        print(f"  💡 完整 AI 输入/输出已保存到独立日志文件 (--export 模式)")

    def _display_results(self, signal_data: Dict) -> None:
        """Display analysis results."""
        print()
        print("  🎯 Judge 最终决策:")
        judge_signal = signal_data.get('signal', 'N/A')
        print(f"     Signal: {judge_signal}")
        print(f"     Confidence: {signal_data.get('confidence', 'N/A')}")
        print(f"     Risk Level: {signal_data.get('risk_level', 'N/A')}")

        # SL/TP
        sltp_suffix = " (仅供参考，HOLD 不使用)" if judge_signal == 'HOLD' else ""
        sl = safe_float(signal_data.get('stop_loss'))
        tp = safe_float(signal_data.get('take_profit'))
        if sl:
            print(f"     Stop Loss: ${sl:,.2f}{sltp_suffix}")
        if tp:
            print(f"     Take Profit: ${tp:,.2f}{sltp_suffix}")

        # Judge decision details
        judge = signal_data.get('judge_decision', {})
        if judge:
            winning_side = judge.get('winning_side', 'N/A')
            print(f"     Winning Side: {winning_side}")
            print()
            print("     📋 Judge 决策 (AI 完全自主):")
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

        # Invalidation conditions
        invalidation = signal_data.get('invalidation', 'N/A')
        if invalidation and invalidation != 'N/A':
            inv_text = invalidation[:200] + "..." if len(str(invalidation)) > 200 else str(invalidation)
            print(f"     Invalidation: {inv_text}")

        # Display debate transcript
        self._display_debate_transcript()

        # Display AI Prompt structure
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
        """Display AI Prompt structure verification."""
        if not self.ctx.multi_agent:
            return

        if not hasattr(self.ctx.multi_agent, 'get_last_prompts'):
            return

        last_prompts = self.ctx.multi_agent.get_last_prompts()
        if not last_prompts:
            return

        print()
        print_box("AI Prompt 结构验证 (System/User + Memory)", 65)
        print()

        for agent_name in ["bull", "bear", "judge", "risk"]:
            if agent_name not in last_prompts:
                continue

            prompts = last_prompts[agent_name]
            system_prompt = prompts.get("system", "")
            user_prompt = prompts.get("user", "")

            # Check INDICATOR_DEFINITIONS in System Prompt
            has_indicator_defs = "INDICATOR REFERENCE" in system_prompt

            # Check PAST REFLECTIONS (memory) in Judge's User Prompt
            has_past_memories = "PAST REFLECTIONS" in user_prompt

            print(f"  [{agent_name.upper()}] Prompt 结构:")
            print(f"     System Prompt 长度: {len(system_prompt)} 字符")
            print(f"     User Prompt 长度:   {len(user_prompt)} 字符")
            print(f"     INDICATOR_DEFINITIONS 在 System: {'✅ 是' if has_indicator_defs else '❌ 否'}")

            # Judge-specific check - memory system
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

            # For Judge, show memory section preview
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

        print("  📋 Prompt 架构要求:")
        print("     - System Prompt: 角色定义 + INDICATOR_DEFINITIONS")
        print("     - User Prompt: 原始数据 + 任务指令 (纯知识，无指令性语句)")
        print("     - Judge Prompt: 包含 PAST REFLECTIONS (过去交易记忆)")
        print("     - Risk Manager output: 包含 invalidation 字段")


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

        # v2.6.0: Use S/R Zone data (more sophisticated) instead of basic technical_data
        # S/R Zone Calculator aggregates: BB, SMA_50, SMA_200, Order Walls
        # Falls back to basic technical_data if S/R Zones not available
        support = 0.0
        resistance = 0.0
        sr_source = "none"

        if self.ctx.sr_zones_data:
            nearest_support = self.ctx.sr_zones_data.get('nearest_support')
            nearest_resistance = self.ctx.sr_zones_data.get('nearest_resistance')
            if nearest_support and hasattr(nearest_support, 'price_center'):
                support = nearest_support.price_center
                sr_source = f"S/R Zone ({nearest_support.strength}, {nearest_support.level})"
            if nearest_resistance and hasattr(nearest_resistance, 'price_center'):
                resistance = nearest_resistance.price_center
                sr_source = f"S/R Zone ({nearest_resistance.strength}, {nearest_resistance.level})"
            print(f"     使用 {sr_source}:")
            print(f"       Support: ${support:,.0f}" if support > 0 else "       Support: N/A")
            print(f"       Resistance: ${resistance:,.0f}" if resistance > 0 else "       Resistance: N/A")
        else:
            # Fallback to basic technical data
            support = self.ctx.technical_data.get('support', 0.0)
            resistance = self.ctx.technical_data.get('resistance', 0.0)
            if support > 0 or resistance > 0:
                sr_source = "technical_data (basic)"
                print(f"     使用 {sr_source}:")
                print(f"       Support: ${support:,.0f}" if support > 0 else "       Support: N/A")
                print(f"       Resistance: ${resistance:,.0f}" if resistance > 0 else "       Resistance: N/A")

        print()
        use_sr = getattr(cfg, 'sl_use_support_resistance', True)
        sl_buffer = getattr(cfg, 'sl_buffer_pct', 0.005)  # v3.15.1: 0.5% buffer for real S/R breakout

        from strategy.trading_logic import get_min_rr_ratio
        min_rr = get_min_rr_ratio()
        print("  📋 入场验证规则 (R/R 驱动):")
        print(f"     - R/R >= {min_rr}:1 硬性门槛 (validate_multiagent_sltp 强制执行)")
        print("     - 最小止损距离: 1% (技术要求)")
        print(f"     - S/R 突破缓冲: {sl_buffer*100:.1f}% (确认真正突破)")
        print()

        if multi_sl and multi_tp:
            is_valid, final_sl, final_tp, reason = validate_multiagent_sltp(
                side=signal,
                multi_sl=multi_sl,
                multi_tp=multi_tp,
                entry_price=self.ctx.current_price,
            )
            print(f"     验证结果: {'✅ 通过' if is_valid else '❌ 失败'} - {reason}")

            if not is_valid:
                print("     ⚠️ AI SL/TP 验证失败，回退到 S/R Zone 技术分析")
                final_sl, final_tp, calc_method = calculate_technical_sltp(
                    side=signal,
                    entry_price=self.ctx.current_price,
                    support=support,
                    resistance=resistance,
                    confidence=confidence,
                    use_support_resistance=use_sr,
                    sl_buffer_pct=sl_buffer,
                )
                print(f"     {calc_method}")
        else:
            print("     ⚠️ AI 未提供 SL/TP，使用 S/R Zone 技术分析计算")
            final_sl, final_tp, calc_method = calculate_technical_sltp(
                side=signal,
                entry_price=self.ctx.current_price,
                support=support,
                resistance=resistance,
                confidence=confidence,
                use_support_resistance=use_sr,
                sl_buffer_pct=sl_buffer,
            )
            print(f"     {calc_method}")

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
            print(f"     R/R 比率: {rr_ratio:.2f}:1")

            # R/R-based position sizing guidance
            if rr_ratio >= 2.5:
                rr_status = "✅ 优秀 (建议 80-100% 仓位)"
            elif rr_ratio >= 2.0:
                rr_status = "✅ 良好 (建议 50-80% 仓位)"
            elif rr_ratio >= 1.5:
                rr_status = "✅ 可接受 (建议 30-50% 仓位)"
            else:
                rr_status = f"❌ 不达标 (< {min_rr}:1 硬性门槛，已被 validate_multiagent_sltp 拦截)"
            print(f"     评估: {rr_status}")

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
