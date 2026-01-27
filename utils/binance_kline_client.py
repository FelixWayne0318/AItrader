# utils/binance_kline_client.py

import requests
import logging
from typing import List, Optional, Dict, Any


class BinanceKlineClient:
    """
    Binance K线数据客户端

    获取完整 12 列 K线数据，包含订单流所需字段:
    - taker_buy_volume (列[9])
    - quote_volume (列[7])
    - trades_count (列[8])

    注意: 此接口无需 API Key，是公开数据
    """

    # Binance Futures API (永续合约)
    BASE_URL = "https://fapi.binance.com"

    def __init__(
        self,
        timeout: int = 10,
        logger: logging.Logger = None,
    ):
        self.timeout = timeout
        self.logger = logger or logging.getLogger(__name__)

    def get_klines(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        limit: int = 50,
    ) -> Optional[List[List]]:
        """
        获取 K线数据 (完整 12 列)

        Parameters
        ----------
        symbol : str
            交易对 (如 BTCUSDT)
        interval : str
            时间周期 (1m/5m/15m/1h/4h/1d)
        limit : int
            获取数量 (最大 1500)

        Returns
        -------
        List[List]
            Binance 原始 K线数据 (12 列)，失败返回 None

        示例返回:
        [
            [
                1499040000000,      # [0] open_time (ms)
                "0.01634000",       # [1] open
                "0.80000000",       # [2] high
                "0.01575800",       # [3] low
                "0.01577100",       # [4] close
                "148976.11427815",  # [5] volume
                1499644799999,      # [6] close_time (ms)
                "2434.19055334",    # [7] quote_volume ⭐
                308,                # [8] trades_count ⭐
                "1756.87402397",    # [9] taker_buy_volume ⭐
                "28.46694368",      # [10] taker_buy_quote
                "17928899.62484339" # [11] ignore
            ],
            ...
        ]
        """
        try:
            url = f"{self.BASE_URL}/fapi/v1/klines"
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            }

            response = requests.get(url, params=params, timeout=self.timeout)

            if response.status_code == 200:
                return response.json()
            else:
                self.logger.warning(
                    f"⚠️ Binance klines API error: {response.status_code}"
                )
                return None

        except Exception as e:
            self.logger.warning(f"⚠️ Binance klines fetch error: {e}")
            return None

    def get_current_price(self, symbol: str = "BTCUSDT") -> Optional[float]:
        """获取当前价格"""
        klines = self.get_klines(symbol=symbol, interval="1m", limit=1)
        if klines and len(klines) > 0:
            return float(klines[-1][4])  # close price
        return None

    def get_funding_rate(self, symbol: str = "BTCUSDT") -> Optional[Dict[str, Any]]:
        """
        获取 Binance 直接的 Funding Rate (用于对比 Coinalyze 数据)

        Returns
        -------
        Dict or None
            {
                "symbol": "BTCUSDT",
                "funding_rate": 0.0001,      # 原始值 (0.01%)
                "funding_rate_pct": 0.01,    # 百分比形式
                "next_funding_time": 1234567890000,
                "source": "binance_direct"
            }
        """
        try:
            url = f"{self.BASE_URL}/fapi/v1/premiumIndex"
            params = {"symbol": symbol}

            response = requests.get(url, params=params, timeout=self.timeout)

            if response.status_code == 200:
                data = response.json()
                funding_rate = float(data.get('lastFundingRate', 0))
                return {
                    "symbol": data.get('symbol'),
                    "funding_rate": funding_rate,
                    "funding_rate_pct": round(funding_rate * 100, 4),  # 转为百分比
                    "next_funding_time": data.get('nextFundingTime'),
                    "mark_price": float(data.get('markPrice', 0)),
                    "source": "binance_direct",
                }
            else:
                self.logger.warning(
                    f"⚠️ Binance funding rate API error: {response.status_code}"
                )
                return None

        except Exception as e:
            self.logger.warning(f"⚠️ Binance funding rate fetch error: {e}")
            return None
