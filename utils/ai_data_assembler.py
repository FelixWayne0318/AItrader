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
    """

    def __init__(
        self,
        binance_kline_client,
        order_flow_processor,
        coinalyze_client,
        sentiment_client,
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
        """
        self.binance_klines = binance_kline_client
        self.order_flow = order_flow_processor
        self.coinalyze = coinalyze_client
        self.sentiment = sentiment_client
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

        # Step 3: 获取 Coinalyze 衍生品数据
        coinalyze_data = self.coinalyze.fetch_all()

        # Step 4: 转换衍生品数据格式
        derivatives = self._convert_derivatives(
            oi_raw=coinalyze_data.get('open_interest'),
            liq_raw=coinalyze_data.get('liquidations'),
            funding_raw=coinalyze_data.get('funding_rate'),
            current_price=current_price,
        )

        # Step 5: 获取情绪数据
        sentiment_data = self.sentiment.fetch()
        if sentiment_data is None:
            sentiment_data = self._default_sentiment()

        # Step 6: 组装最终数据
        return {
            "price": {
                "current": current_price,
                "change_pct": self._calc_change(raw_klines) if raw_klines else 0,
            },
            "technical": technical_data,
            "order_flow": order_flow_data,
            "derivatives": derivatives,
            "sentiment": sentiment_data,
            "current_position": position_data or {},
            "_metadata": {
                "kline_source": "binance_raw" if raw_klines else "none",
                "coinalyze_enabled": self.coinalyze.is_enabled(),
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

        # Funding 转换
        if funding_raw:
            try:
                funding_value = float(funding_raw.get('value', 0))
                result["funding_rate"] = {
                    "value": funding_value,
                    "current": funding_value,
                    "current_pct": round(funding_value * 100, 4),  # 转为百分比
                    "interpretation": self._interpret_funding(funding_value),
                }
            except Exception as e:
                self.logger.warning(f"⚠️ Funding parse error: {e}")

        # Liquidation 转换 (嵌套结构)
        if liq_raw:
            try:
                history = liq_raw.get('history', [])
                if history:
                    result["liquidations"] = {
                        "history": history
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
