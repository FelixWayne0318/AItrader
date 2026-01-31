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
    """

    def __init__(
        self,
        binance_kline_client,
        order_flow_processor,
        coinalyze_client,
        sentiment_client,
        binance_derivatives_client=None,
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
        """
        self.binance_klines = binance_kline_client
        self.order_flow = order_flow_processor
        self.coinalyze = coinalyze_client
        self.sentiment = sentiment_client
        self.binance_derivatives = binance_derivatives_client
        self.logger = logger or logging.getLogger(__name__)

        # OI 变化率计算缓存
        self._last_oi_usd: float = 0.0

    def assemble(
        self,
        technical_data: Dict[str, Any],
        position_data: Optional[Dict[str, Any]] = None,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
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

        # Step 7: 组装最终数据
        return {
            "price": {
                "current": current_price,
                "change_pct": self._calc_change(raw_klines) if raw_klines else 0,
            },
            "technical": technical_data,
            "order_flow": order_flow_data,
            "derivatives": derivatives,
            "sentiment": sentiment_data,
            "binance_derivatives": binance_derivatives_data,  # v3.0 新增
            "current_position": position_data or {},
            "_metadata": {
                "kline_source": "binance_raw" if raw_klines else "none",
                "coinalyze_enabled": self.coinalyze.is_enabled(),
                "binance_derivatives_enabled": self.binance_derivatives is not None,
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

        # Funding 转换 (v2.1: 添加 Binance 直接对比)
        # 先获取 Binance 直接的 Funding Rate
        binance_funding = None
        try:
            binance_funding = self.binance_klines.get_funding_rate()
        except Exception as e:
            self.logger.debug(f"⚠️ Binance funding rate fetch error: {e}")

        if funding_raw:
            try:
                coinalyze_value = float(funding_raw.get('value', 0))
                coinalyze_pct = round(coinalyze_value * 100, 4)

                # 决定使用哪个数据源 (v3.7: 配置化)
                # 读取配置
                funding_config = self.config.get('coinalyze', {}).get('funding_rate', {})
                prefer_binance = funding_config.get('prefer_binance_when_divergent', True)
                max_ratio = funding_config.get('max_divergence_ratio', 10.0)
                always_binance = funding_config.get('always_use_binance', False)

                use_binance = False
                binance_pct = None
                if binance_funding:
                    binance_pct = binance_funding.get('funding_rate_pct', 0)

                    # 如果配置为始终使用 Binance
                    if always_binance:
                        use_binance = True
                    # 否则检查差异
                    elif prefer_binance and binance_pct > 0 and coinalyze_pct > 0:
                        ratio = coinalyze_pct / binance_pct
                        if ratio > max_ratio or ratio < (1 / max_ratio):
                            self.logger.warning(
                                f"⚠️ Funding rate 数据差异大: "
                                f"Coinalyze={coinalyze_pct:.4f}%, Binance={binance_pct:.4f}%, "
                                f"ratio={ratio:.2f} (threshold={max_ratio})"
                            )
                            # Coinalyze 异常时使用 Binance
                            use_binance = True

                # 选择最终使用的值
                if use_binance and binance_funding:
                    final_value = binance_funding['funding_rate']
                    final_pct = binance_pct
                    source = "binance_direct"
                else:
                    final_value = coinalyze_value
                    final_pct = coinalyze_pct
                    source = "coinalyze"

                result["funding_rate"] = {
                    "value": final_value,
                    "current": final_value,
                    "current_pct": final_pct,
                    "interpretation": self._interpret_funding(final_value),
                    "source": source,
                    # 保留两个数据源供对比
                    "coinalyze_pct": coinalyze_pct,
                    "binance_pct": binance_pct,
                }
            except Exception as e:
                self.logger.warning(f"⚠️ Funding parse error: {e}")
        elif binance_funding:
            # Coinalyze 无数据，使用 Binance
            result["funding_rate"] = {
                "value": binance_funding['funding_rate'],
                "current": binance_funding['funding_rate'],
                "current_pct": binance_funding['funding_rate_pct'],
                "interpretation": self._interpret_funding(binance_funding['funding_rate']),
                "source": "binance_direct",
                "coinalyze_pct": None,
                "binance_pct": binance_funding['funding_rate_pct'],
            }

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

            # Funding Rate
            fr = derivatives.get("funding_rate")
            if fr:
                fr_trend = trends.get("funding_trend", "N/A")
                parts.append(
                    f"  - Funding Rate: {fr.get('current_pct', 0):.4f}% "
                    f"({fr.get('interpretation', 'N/A')}) [Trend: {fr_trend}]"
                )

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

        parts.append("\n" + "=" * 50)

        return "\n".join(parts)
