# utils/ai_data_assembler.py

import logging
from typing import Dict, Any, List, Optional, Union


class AIDataAssembler:
    """
    AI 数据组装器 (同步版本)

    负责:
    1. 顺序获取外部数据 (Binance K线、Coinalyze、Sentiment)
    2. 格式转换 (Coinalyze → 统一格式, BTC → USD)
    3. 组装最终数据结构

    v2.0 更新:
    - 改为同步实现，兼容 on_timer() 回调
    - 支持双格式 K线输入
    - 添加数据新鲜度检查

    v3.0 更新:
    - 整合 BinanceDerivativesClient (大户数据、Taker 比等)
    - 整合 Coinalyze 历史数据 (OI/Funding/多空比趋势)
    - 添加 format_complete_report() 供 AI 使用

    v3.0.1 更新 (IMPLEMENTATION_PLAN Section 4.2.1):
    - 添加 historical_context 支持 (20 值趋势数据)
    - AI 可以看到指标趋势，而非孤立的单一值
    """

    def __init__(
        self,
        binance_kline_client,
        order_flow_processor,
        coinalyze_client,
        sentiment_client,
        binance_derivatives_client=None,
        binance_orderbook_client=None,
        orderbook_processor=None,
        config: Dict = None,
        logger: logging.Logger = None,
    ):
        """
        初始化数据组装器

        Parameters
        ----------
        binance_kline_client : BinanceKlineClient
            Binance K线客户端 (获取完整 12 列数据)
        order_flow_processor : OrderFlowProcessor
            订单流处理器
        coinalyze_client : CoinalyzeClient
            Coinalyze 衍生品客户端
        sentiment_client : SentimentDataFetcher
            情绪数据客户端
        binance_derivatives_client : BinanceDerivativesClient, optional
            Binance 衍生品客户端 (大户数据等) - v3.0 新增
        binance_orderbook_client : BinanceOrderBookClient, optional
            Binance 订单簿客户端 - v3.7 新增
        orderbook_processor : OrderBookProcessor, optional
            订单簿处理器 - v3.7 新增
        config : Dict, optional
            配置字典 (用于获取配置参数)
        """
        self.binance_klines = binance_kline_client
        self.order_flow = order_flow_processor
        self.coinalyze = coinalyze_client
        self.sentiment = sentiment_client
        self.binance_derivatives = binance_derivatives_client
        self.binance_orderbook = binance_orderbook_client
        self.orderbook_processor = orderbook_processor
        self.config = config or {}
        self.logger = logger or logging.getLogger(__name__)

        # OI 变化率计算缓存
        self._last_oi_usd: float = 0.0

    def assemble(
        self,
        technical_data: Dict[str, Any],
        position_data: Optional[Dict[str, Any]] = None,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        indicator_manager=None,
    ) -> Dict[str, Any]:
        """
        组装完整的 AI 输入数据 (同步方法)

        Parameters
        ----------
        technical_data : Dict
            技术指标数据 (来自 indicator_manager.get_technical_data())
        position_data : Dict, optional
            当前持仓信息
        symbol : str
            交易对
        interval : str
            K线周期
        indicator_manager : TechnicalIndicatorManager, optional
            技术指标管理器 (用于获取 historical_context) - v3.0.1 新增

        Returns
        -------
        Dict
            完整的 AI 输入数据字典
        """
        # Step 1: 获取 Binance 完整 K线 (12 列)
        raw_klines = self.binance_klines.get_klines(
            symbol=symbol,
            interval=interval,
            limit=50,
        )

        # Step 2: 处理订单流数据
        if raw_klines:
            order_flow_data = self.order_flow.process_klines(raw_klines)
            current_price = float(raw_klines[-1][4])
        else:
            self.logger.warning("⚠️ Failed to get Binance klines, using degraded mode")
            order_flow_data = self.order_flow._default_result()
            current_price = technical_data.get('price', 0)

        # Step 3: 获取 Coinalyze 衍生品数据 (包含历史)
        # v3.0: 使用 fetch_all_with_history 获取完整数据
        coinalyze_data = self.coinalyze.fetch_all_with_history(history_hours=4)

        # Step 4: 转换衍生品数据格式
        derivatives = self._convert_derivatives(
            oi_raw=coinalyze_data.get('open_interest'),
            liq_raw=coinalyze_data.get('liquidations'),
            funding_raw=coinalyze_data.get('funding_rate'),
            current_price=current_price,
        )

        # v3.0: 添加 Coinalyze 趋势数据
        derivatives["trends"] = coinalyze_data.get("trends", {})
        derivatives["long_short_ratio_history"] = coinalyze_data.get("long_short_ratio_history")

        # Step 5: 获取情绪数据
        sentiment_data = self.sentiment.fetch()
        if sentiment_data is None:
            sentiment_data = self._default_sentiment()

        # Step 6: 获取 Binance 衍生品数据 (大户数据等) - v3.0 新增
        binance_derivatives_data = None
        if self.binance_derivatives:
            try:
                binance_derivatives_data = self.binance_derivatives.fetch_all(
                    symbol=symbol,
                    period=interval,
                    history_limit=10,
                )
            except Exception as e:
                self.logger.warning(f"⚠️ Binance derivatives fetch error: {e}")

        # Step 7: 获取订单簿数据 - v3.7 新增
        orderbook_data = None
        if self.binance_orderbook and self.orderbook_processor:
            try:
                raw_orderbook = self.binance_orderbook.get_order_book(symbol=symbol)
                if raw_orderbook:
                    # 获取波动率用于自适应调整
                    volatility = self._get_recent_volatility(technical_data)
                    orderbook_data = self.orderbook_processor.process(
                        order_book=raw_orderbook,
                        current_price=current_price,
                        volatility=volatility,
                    )
                else:
                    orderbook_data = self._no_data_orderbook("API returned None")
            except Exception as e:
                self.logger.warning(f"⚠️ Order book fetch error: {e}")
                orderbook_data = self._no_data_orderbook(str(e))

        # Step 8: 获取历史上下文 (v3.0.1 - IMPLEMENTATION_PLAN Section 4.2.1)
        # count=35 确保 MACD 历史计算有足够数据 (slow_period=26 + 5 + buffer)
        historical_context = None
        if indicator_manager is not None:
            try:
                historical_context = indicator_manager.get_historical_context(count=35)
                self.logger.debug(
                    f"Historical context: trend={historical_context.get('trend_direction')}, "
                    f"momentum={historical_context.get('momentum_shift')}"
                )
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to get historical context: {e}")
                historical_context = {
                    "error": str(e),
                    "trend_direction": "ERROR",
                    "momentum_shift": "ERROR",
                }

        # Step 9: 组装最终数据
        return {
            "price": {
                "current": current_price,
                "change_pct": self._calc_change(raw_klines) if raw_klines else 0,
            },
            "technical": technical_data,
            "historical_context": historical_context,  # v3.0.1 新增
            "order_flow": order_flow_data,
            "derivatives": derivatives,
            "sentiment": sentiment_data,
            "binance_derivatives": binance_derivatives_data,  # v3.0 新增
            "order_book": orderbook_data,  # v3.7 新增
            "current_position": position_data or {},
            "_metadata": {
                "kline_source": "binance_raw" if raw_klines else "none",
                "coinalyze_enabled": self.coinalyze.is_enabled(),
                "binance_derivatives_enabled": self.binance_derivatives is not None,
                "orderbook_enabled": self.binance_orderbook is not None,
                "orderbook_status": orderbook_data.get("_status", {}).get("code") if orderbook_data else "DISABLED",
                "historical_context_enabled": historical_context is not None,  # v3.0.1 新增
            },
        }

    def _convert_derivatives(
        self,
        oi_raw: Optional[Dict],
        liq_raw: Optional[Dict],
        funding_raw: Optional[Dict],
        current_price: float,
    ) -> Dict[str, Any]:
        """
        Coinalyze API → 统一格式转换
        """
        result = {
            "open_interest": None,
            "liquidations": None,
            "funding_rate": None,
            "enabled": True,
        }

        # OI 转换 (BTC → USD)
        if oi_raw:
            try:
                oi_btc = float(oi_raw.get('value', 0))
                oi_usd = oi_btc * current_price if current_price > 0 else 0

                # 计算变化率 (首次为 None)
                change_pct = None
                if self._last_oi_usd > 0 and oi_usd > 0:
                    change_pct = round(
                        (oi_usd - self._last_oi_usd) / self._last_oi_usd * 100, 2
                    )
                self._last_oi_usd = oi_usd

                result["open_interest"] = {
                    "value": round(oi_btc, 2),
                    "total_usd": round(oi_usd, 0),
                    "total_btc": round(oi_btc, 2),
                    "change_pct": change_pct,
                }
            except Exception as e:
                self.logger.warning(f"⚠️ OI parse error: {e}")

        # Funding 转换 (v3.22: 完全以 Binance 为准，含预期费率和历史)
        # 获取 Binance premiumIndex (含预期费率)
        binance_funding = None
        try:
            binance_funding = self.binance_klines.get_funding_rate()
        except Exception as e:
            self.logger.debug(f"⚠️ Binance funding rate fetch error: {e}")

        # 获取 Binance 资金费率结算历史 (最近 10 次)
        binance_funding_history = None
        try:
            binance_funding_history = self.binance_klines.get_funding_rate_history(limit=10)
        except Exception as e:
            self.logger.debug(f"⚠️ Binance funding rate history fetch error: {e}")

        if binance_funding:
            # v3.22: 始终使用 Binance 作为主数据源 (我们在 Binance 交易)
            funding_rate = binance_funding['funding_rate']
            funding_pct = binance_funding['funding_rate_pct']

            # 构建历史趋势
            history_rates = []
            if binance_funding_history:
                for record in binance_funding_history:
                    try:
                        rate = float(record.get('fundingRate', 0))
                        history_rates.append({
                            "time": record.get('fundingTime'),
                            "rate": rate,
                            "rate_pct": round(rate * 100, 4),
                            "mark_price": record.get('markPrice'),
                        })
                    except (ValueError, TypeError):
                        continue

            # 计算历史趋势方向
            funding_trend = "N/A"
            if len(history_rates) >= 3:
                recent_3 = [r['rate'] for r in history_rates[-3:]]
                if recent_3[-1] > recent_3[0] * 1.1:
                    funding_trend = "RISING"
                elif recent_3[-1] < recent_3[0] * 0.9:
                    funding_trend = "FALLING"
                else:
                    funding_trend = "STABLE"

            result["funding_rate"] = {
                "value": funding_rate,
                "current": funding_rate,
                "current_pct": funding_pct,
                "interpretation": self._interpret_funding(funding_rate),
                "source": "binance_8h",
                "period": "8h",
                # v3.22: 预期费率 (从 mark-index 价差计算)
                "predicted_rate": binance_funding.get('predicted_rate'),
                "predicted_rate_pct": binance_funding.get('predicted_rate_pct'),
                # v3.22: 下次结算时间
                "next_funding_time": binance_funding.get('next_funding_time'),
                "next_funding_countdown_min": binance_funding.get('next_funding_countdown_min'),
                # v3.22: 结算历史 (最近 10 次)
                "history": history_rates,
                "trend": funding_trend,
                # v3.22: 溢价指数
                "premium_index": binance_funding.get('premium_index'),
                "mark_price": binance_funding.get('mark_price'),
                "index_price": binance_funding.get('index_price'),
                # 保留 Coinalyze 对比 (仅参考)
                "coinalyze_pct": None,
                "binance_pct": funding_pct,
            }

            # 记录 Coinalyze 对比值 (如果可用)
            if funding_raw:
                try:
                    coinalyze_pct = round(float(funding_raw.get('value', 0)) * 100, 4)
                    result["funding_rate"]["coinalyze_pct"] = coinalyze_pct
                except (ValueError, TypeError):
                    pass
        elif funding_raw:
            # Binance 不可用时降级到 Coinalyze
            try:
                coinalyze_value = float(funding_raw.get('value', 0))
                coinalyze_pct = round(coinalyze_value * 100, 4)
                result["funding_rate"] = {
                    "value": coinalyze_value,
                    "current": coinalyze_value,
                    "current_pct": coinalyze_pct,
                    "interpretation": self._interpret_funding(coinalyze_value),
                    "source": "coinalyze_fallback",
                    "period": "aggregated",
                    "predicted_rate": None,
                    "predicted_rate_pct": None,
                    "next_funding_time": None,
                    "next_funding_countdown_min": None,
                    "history": [],
                    "trend": "N/A",
                    "premium_index": None,
                    "mark_price": None,
                    "index_price": None,
                    "coinalyze_pct": coinalyze_pct,
                    "binance_pct": None,
                }
            except Exception as e:
                self.logger.warning(f"⚠️ Funding parse error: {e}")

        # Liquidation 转换 (嵌套结构)
        # v2.1: 即使 history 为空也返回结构 (区分"无爆仓"和"数据缺失")
        if liq_raw:
            try:
                history = liq_raw.get('history', [])

                # 计算总爆仓量 (BTC → USD)
                long_liq_btc = 0.0
                short_liq_btc = 0.0
                if history:
                    for item in history:
                        long_liq_btc += float(item.get('l', 0))
                        short_liq_btc += float(item.get('s', 0))

                long_liq_usd = long_liq_btc * current_price if current_price > 0 else 0
                short_liq_usd = short_liq_btc * current_price if current_price > 0 else 0

                result["liquidations"] = {
                    "history": history,
                    "has_data": len(history) > 0,  # 明确标记数据状态
                    "long_btc": round(long_liq_btc, 4),
                    "short_btc": round(short_liq_btc, 4),
                    "long_usd": round(long_liq_usd, 2),
                    "short_usd": round(short_liq_usd, 2),
                    "total_usd": round(long_liq_usd + short_liq_usd, 2),
                }
            except Exception as e:
                self.logger.warning(f"⚠️ Liquidation parse error: {e}")

        return result

    def _interpret_funding(self, funding_rate: float) -> str:
        """解读资金费率"""
        if funding_rate > 0.001:  # > 0.1%
            return "VERY_BULLISH"
        elif funding_rate > 0.0005:  # > 0.05%
            return "BULLISH"
        elif funding_rate < -0.001:  # < -0.1%
            return "VERY_BEARISH"
        elif funding_rate < -0.0005:  # < -0.05%
            return "BEARISH"
        else:
            return "NEUTRAL"

    def _calc_change(self, klines: List) -> float:
        """计算涨跌幅 (基于 K线数据)"""
        if not klines or len(klines) < 2:
            return 0.0
        old_close = float(klines[0][4])
        new_close = float(klines[-1][4])
        return round((new_close - old_close) / old_close * 100, 2) if old_close > 0 else 0.0

    def _default_sentiment(self) -> Dict[str, Any]:
        """默认情绪数据 (中性)"""
        return {
            'positive_ratio': 0.5,
            'negative_ratio': 0.5,
            'net_sentiment': 0.0,
            'long_short_ratio': 1.0,
            'source': 'default_neutral',
        }

    def format_complete_report(self, data: Dict[str, Any]) -> str:
        """
        格式化完整数据报告供 AI 分析 (v3.0 新增)

        Parameters
        ----------
        data : Dict
            assemble() 返回的完整数据

        Returns
        -------
        str
            格式化的完整市场数据报告
        """
        current_price = data.get("price", {}).get("current", 0)
        parts = []

        # =========================================================================
        # 1. 价格和技术指标
        # =========================================================================
        parts.append("=" * 50)
        parts.append("MARKET DATA REPORT")
        parts.append("=" * 50)

        price_data = data.get("price", {})
        parts.append(f"\nPRICE: ${current_price:,.2f} ({price_data.get('change_pct', 0):+.2f}%)")

        # =========================================================================
        # 2. 订单流数据
        # =========================================================================
        order_flow = data.get("order_flow", {})
        if order_flow:
            parts.append("\nORDER FLOW (from Binance Klines):")
            parts.append(f"  - Buy Ratio: {order_flow.get('buy_ratio', 0.5):.1%}")
            parts.append(f"  - CVD Trend: {order_flow.get('cvd_trend', 'N/A')}")
            parts.append(f"  - Avg Trade Size: ${order_flow.get('avg_trade_size', 0):,.0f}")

        # =========================================================================
        # 3. Coinalyze 衍生品数据 (含趋势)
        # =========================================================================
        derivatives = data.get("derivatives", {})
        if derivatives:
            parts.append("\nCOINALYZE DERIVATIVES:")
            trends = derivatives.get("trends", {})

            # OI
            oi = derivatives.get("open_interest")
            if oi:
                oi_trend = trends.get("oi_trend", "N/A")
                parts.append(
                    f"  - Open Interest: {oi.get('total_btc', 0):,.0f} BTC "
                    f"(${oi.get('total_usd', 0):,.0f}) [Trend: {oi_trend}]"
                )

            # Funding Rate (v3.22: 增强版 — 当前 + 预期 + 历史趋势)
            fr = derivatives.get("funding_rate")
            if fr:
                fr_trend = fr.get("trend") or trends.get("funding_trend", "N/A")
                parts.append(
                    f"  - Funding Rate (last settled): {fr.get('current_pct', 0):.4f}% "
                    f"({fr.get('interpretation', 'N/A')}) [Trend: {fr_trend}]"
                )
                # 溢价指数 + 预期费率
                premium_index = fr.get('premium_index')
                if premium_index is not None:
                    pi_pct = premium_index * 100
                    mark = fr.get('mark_price', 0)
                    index = fr.get('index_price', 0)
                    parts.append(
                        f"  - Premium Index: {pi_pct:+.4f}% "
                        f"(Mark: ${mark:,.2f}, Index: ${index:,.2f})"
                    )
                predicted_pct = fr.get('predicted_rate_pct')
                if predicted_pct is not None:
                    parts.append(
                        f"  - Predicted Next Funding Rate: {predicted_pct:.4f}%"
                    )
                # 下次结算倒计时
                countdown = fr.get('next_funding_countdown_min')
                if countdown is not None:
                    hours = countdown // 60
                    mins = countdown % 60
                    parts.append(
                        f"  - Next Settlement: {hours}h {mins}m"
                    )
                # 历史 (最近 10 次结算)
                history = fr.get('history', [])
                if history and len(history) >= 2:
                    rates_str = " → ".join(
                        [f"{r['rate_pct']:.4f}%" for r in history]
                    )
                    parts.append(f"  - Settlement History (last {len(history)}): {rates_str}")

            # Liquidations
            liq = derivatives.get("liquidations")
            if liq:
                parts.append(
                    f"  - Liquidations (1h): Long ${liq.get('long_usd', 0):,.0f} / "
                    f"Short ${liq.get('short_usd', 0):,.0f}"
                )

            # Long/Short Ratio (from Coinalyze)
            ls_hist = derivatives.get("long_short_ratio_history")
            if ls_hist and ls_hist.get("history"):
                latest = ls_hist["history"][-1]
                ls_trend = trends.get("long_short_trend", "N/A")
                parts.append(
                    f"  - Long/Short Ratio (Coinalyze): {latest.get('r', 1):.2f} "
                    f"(Long {latest.get('l', 50):.1f}% / Short {latest.get('s', 50):.1f}%) "
                    f"[Trend: {ls_trend}]"
                )

        # =========================================================================
        # 4. Binance 衍生品数据 (大户数据、Taker 比)
        # =========================================================================
        binance_deriv = data.get("binance_derivatives")
        if binance_deriv:
            parts.append("\nBINANCE DERIVATIVES (Unique Data):")

            # 大户持仓比
            top_pos = binance_deriv.get("top_long_short_position", {})
            latest = top_pos.get("latest")
            if latest:
                ratio = float(latest.get("longShortRatio", 1))
                long_pct = float(latest.get("longAccount", 0.5)) * 100
                trend = top_pos.get("trend", "N/A")
                parts.append(
                    f"  - Top Traders Position: Long {long_pct:.1f}% "
                    f"(Ratio: {ratio:.2f}) [Trend: {trend}]"
                )

            # Taker 买卖比
            taker = binance_deriv.get("taker_long_short", {})
            latest = taker.get("latest")
            if latest:
                ratio = float(latest.get("buySellRatio", 1))
                trend = taker.get("trend", "N/A")
                parts.append(f"  - Taker Buy/Sell Ratio: {ratio:.3f} [Trend: {trend}]")

            # OI 趋势 (Binance)
            oi_hist = binance_deriv.get("open_interest_hist", {})
            latest = oi_hist.get("latest")
            if latest:
                oi_usd = float(latest.get("sumOpenInterestValue", 0))
                trend = oi_hist.get("trend", "N/A")
                parts.append(f"  - OI (Binance): ${oi_usd:,.0f} [Trend: {trend}]")

            # 24h 统计
            ticker = binance_deriv.get("ticker_24hr")
            if ticker:
                change_pct = float(ticker.get("priceChangePercent", 0))
                volume = float(ticker.get("quoteVolume", 0))
                parts.append(
                    f"  - 24h Stats: Change {change_pct:+.2f}%, Volume ${volume:,.0f}"
                )

        # =========================================================================
        # 5. 市场情绪 (Binance 多空比)
        # =========================================================================
        sentiment = data.get("sentiment", {})
        if sentiment:
            parts.append("\nMARKET SENTIMENT (Binance Global L/S Ratio):")
            parts.append(
                f"  - Long: {sentiment.get('positive_ratio', 0.5):.1%} / "
                f"Short: {sentiment.get('negative_ratio', 0.5):.1%}"
            )
            parts.append(f"  - Net Sentiment: {sentiment.get('net_sentiment', 0):+.3f}")
            parts.append(f"  - L/S Ratio: {sentiment.get('long_short_ratio', 1):.2f}")

        # =========================================================================
        # 6. 数据源状态
        # =========================================================================
        metadata = data.get("_metadata", {})
        parts.append("\nDATA SOURCES:")
        parts.append(f"  - Klines: {metadata.get('kline_source', 'unknown')}")
        parts.append(f"  - Coinalyze: {'enabled' if metadata.get('coinalyze_enabled') else 'disabled'}")
        parts.append(f"  - Binance Derivatives: {'enabled' if metadata.get('binance_derivatives_enabled') else 'disabled'}")

        # =========================================================================
        # 7. 订单簿深度数据 (v3.7 新增)
        # =========================================================================
        order_book = data.get("order_book")
        if order_book:
            status = order_book.get("_status", {})
            status_code = status.get("code", "UNKNOWN")

            parts.append("\nORDER BOOK DEPTH (Binance, 100 levels):")
            parts.append(f"  Status: {status_code}")

            # v2.0: 处理 NO_DATA 状态
            if status_code == "NO_DATA":
                parts.append(f"  Reason: {status.get('message', 'Unknown')}")
                parts.append("  [All metrics unavailable - do not assume neutral market]")
            else:
                # OBI
                obi = order_book.get("obi", {})
                if obi:
                    parts.append(f"  Simple OBI: {obi.get('simple', 0):+.3f}")
                    decay = obi.get('decay_used', 0.8)
                    parts.append(f"  Weighted OBI: {obi.get('adaptive_weighted', 0):+.3f} (decay={decay})")
                    parts.append(
                        f"  Bid Volume: ${obi.get('bid_volume_usd', 0)/1e6:.1f}M "
                        f"({obi.get('bid_volume_btc', 0):.1f} BTC)"
                    )
                    parts.append(
                        f"  Ask Volume: ${obi.get('ask_volume_usd', 0)/1e6:.1f}M "
                        f"({obi.get('ask_volume_btc', 0):.1f} BTC)"
                    )

                # v2.0: Dynamics
                dynamics = order_book.get("dynamics", {})
                if dynamics and dynamics.get("samples_count", 0) > 0:
                    parts.append("  DYNAMICS (vs previous):")
                    if dynamics.get("obi_change") is not None:
                        parts.append(
                            f"    OBI Change: {dynamics['obi_change']:+.4f} "
                            f"({dynamics.get('obi_change_pct', 0):+.1f}%)"
                        )
                    if dynamics.get("bid_depth_change_pct") is not None:
                        parts.append(f"    Bid Depth: {dynamics['bid_depth_change_pct']:+.1f}%")
                    if dynamics.get("ask_depth_change_pct") is not None:
                        parts.append(f"    Ask Depth: {dynamics['ask_depth_change_pct']:+.1f}%")
                    parts.append(f"    Trend: {dynamics.get('trend', 'N/A')}")

                # v2.0: Pressure Gradient
                gradient = order_book.get("pressure_gradient", {})
                if gradient:
                    parts.append("  PRESSURE GRADIENT:")
                    parts.append(
                        f"    Bid: {gradient.get('bid_near_5', 0):.0%} near-5, "
                        f"{gradient.get('bid_near_10', 0):.0%} near-10 "
                        f"[{gradient.get('bid_concentration', 'N/A')}]"
                    )
                    parts.append(
                        f"    Ask: {gradient.get('ask_near_5', 0):.0%} near-5, "
                        f"{gradient.get('ask_near_10', 0):.0%} near-10 "
                        f"[{gradient.get('ask_concentration', 'N/A')}]"
                    )

                # 异常
                anomalies = order_book.get("anomalies", {})
                if anomalies and anomalies.get("has_significant"):
                    threshold = anomalies.get("threshold_used", 3.0)
                    reason = anomalies.get("threshold_reason", "normal")
                    parts.append(f"  ANOMALIES (threshold={threshold}x, {reason}):")
                    for a in anomalies.get("bid_anomalies", [])[:3]:  # 最多显示3个
                        parts.append(
                            f"    Bid @ ${a['price']:,.0f}: {a['volume_btc']:.0f} BTC "
                            f"({a['multiplier']:.1f}x)"
                        )
                    for a in anomalies.get("ask_anomalies", [])[:3]:  # 最多显示3个
                        parts.append(
                            f"    Ask @ ${a['price']:,.0f}: {a['volume_btc']:.0f} BTC "
                            f"({a['multiplier']:.1f}x)"
                        )

                # v2.0: 滑点 (含置信度)
                liquidity = order_book.get("liquidity", {})
                if liquidity:
                    parts.append(f"  Spread: {liquidity.get('spread_pct', 0):.3f}%")
                    slippage = liquidity.get("slippage", {})
                    if slippage.get("buy_1.0_btc"):
                        s = slippage["buy_1.0_btc"]
                        if s.get("estimated") is not None:
                            parts.append(
                                f"  Slippage (Buy 1 BTC): {s['estimated']:.3f}% "
                                f"[conf={s['confidence']:.0%}, range={s['range'][0]:.3f}%-{s['range'][1]:.3f}%]"
                            )

        # =========================================================================
        # 8. 历史上下文 (v3.0.1 新增 - IMPLEMENTATION_PLAN Section 4.2.1)
        # =========================================================================
        historical = data.get("historical_context")
        if historical and historical.get("trend_direction") not in ["INSUFFICIENT_DATA", "ERROR"]:
            parts.append("\nHISTORICAL CONTEXT (Last 20 bars):")
            parts.append(
                f"  - Trend Direction: {historical.get('trend_direction', 'N/A')} "
                f"{historical.get('price_arrow', '')}"
            )
            parts.append(f"  - Momentum Shift: {historical.get('momentum_shift', 'N/A')}")
            parts.append(f"  - Price Change: {historical.get('price_change_pct', 0):+.2f}%")
            parts.append(f"  - Volume Ratio: {historical.get('current_volume_ratio', 1):.2f}x")
            parts.append(f"  - RSI Current: {historical.get('rsi_current', 0):.1f}")
            parts.append(f"  - MACD Current: {historical.get('macd_current', 0):.4f}")

            # 可视化趋势 (简化版)
            price_trend = historical.get('price_trend', [])
            if len(price_trend) >= 5:
                # 取最近5个点展示趋势
                trend_str = " → ".join([f"${p:,.0f}" for p in price_trend[-5:]])
                parts.append(f"  - Price Trend: {trend_str}")

        parts.append("\n" + "=" * 50)

        return "\n".join(parts)

    def _get_recent_volatility(self, technical_data: Dict) -> float:
        """
        获取近期波动率 (用于自适应参数)

        Parameters
        ----------
        technical_data : Dict
            技术指标数据

        Returns
        -------
        float
            相对波动率 (ATR / price)
        """
        atr = technical_data.get("atr", 0)
        price = technical_data.get("price", 1)
        if price > 0:
            return atr / price  # 相对波动率
        return 0.02  # 默认 2%

    def _no_data_orderbook(self, reason: str) -> Dict:
        """
        返回 NO_DATA 状态订单簿 (v2.0 Critical)

        避免 AI 将缺失数据误解为中性市场

        Parameters
        ----------
        reason : str
            数据不可用的原因

        Returns
        -------
        Dict
            NO_DATA 状态字典
        """
        import time
        return {
            "obi": None,
            "dynamics": None,
            "pressure_gradient": None,
            "depth_distribution": None,
            "anomalies": None,
            "liquidity": None,
            "_status": {
                "code": "NO_DATA",
                "message": f"Order book data unavailable: {reason}",
                "timestamp": int(time.time() * 1000),
            },
        }
