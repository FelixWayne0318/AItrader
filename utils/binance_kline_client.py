# utils/binance_kline_client.py

import time
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
        获取 Binance 完整的资金费率数据 (v3.22: 增强版)

        从 premiumIndex 提取所有字段，并计算预期资金费率。

        币安资金费率公式:
            Funding Rate = Premium Index + clamp(Interest Rate - Premium Index, ±0.05%)
            Premium Index = (Mark Price - Index Price) / Index Price

        Returns
        -------
        Dict or None
            {
                "symbol": "BTCUSDT",
                "funding_rate": 0.0001,           # 上次结算费率 (原始值)
                "funding_rate_pct": 0.01,         # 上次结算费率 (百分比)
                "predicted_rate": 0.00015,        # 预期下次费率 (原始值)
                "predicted_rate_pct": 0.015,      # 预期下次费率 (百分比)
                "next_funding_time": 1234567890000,
                "next_funding_countdown_min": 180, # 距下次结算分钟数
                "mark_price": 98000.0,
                "index_price": 97950.0,
                "interest_rate": 0.0001,          # 基础利率
                "premium_index": 0.00051,         # 当前溢价指数
                "source": "binance_direct",
            }
        """
        try:
            url = f"{self.BASE_URL}/fapi/v1/premiumIndex"
            params = {"symbol": symbol}

            response = requests.get(url, params=params, timeout=self.timeout)

            if response.status_code == 200:
                data = response.json()

                # 提取所有字段
                funding_rate = float(data.get('lastFundingRate', 0))
                mark_price = float(data.get('markPrice', 0))
                index_price = float(data.get('indexPrice', 0))
                interest_rate = float(data.get('interestRate', 0))
                next_funding_time = data.get('nextFundingTime', 0)

                # 计算当前溢价指数 (Premium Index)
                premium_index = 0.0
                if index_price > 0:
                    premium_index = (mark_price - index_price) / index_price

                # 计算预期资金费率 (Predicted Funding Rate)
                # 公式: FR = Premium Index + clamp(Interest Rate - Premium Index, ±0.05%)
                clamp_limit = 0.0005  # ±0.05%
                diff = interest_rate - premium_index
                clamped_diff = max(-clamp_limit, min(clamp_limit, diff))
                predicted_rate = premium_index + clamped_diff

                # 计算距下次结算的分钟数
                countdown_min = None
                if next_funding_time and next_funding_time > 0:
                    now_ms = int(time.time() * 1000)
                    remaining_ms = next_funding_time - now_ms
                    if remaining_ms > 0:
                        countdown_min = round(remaining_ms / 60000)

                return {
                    "symbol": data.get('symbol'),
                    "funding_rate": funding_rate,
                    "funding_rate_pct": round(funding_rate * 100, 4),
                    "predicted_rate": predicted_rate,
                    "predicted_rate_pct": round(predicted_rate * 100, 4),
                    "next_funding_time": next_funding_time,
                    "next_funding_countdown_min": countdown_min,
                    "mark_price": mark_price,
                    "index_price": index_price,
                    "interest_rate": interest_rate,
                    "premium_index": premium_index,
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

    def get_funding_rate_history(
        self,
        symbol: str = "BTCUSDT",
        limit: int = 10,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        获取币安资金费率结算历史 (v3.22 新增)

        每 8 小时结算一次 (00:00, 08:00, 16:00 UTC)
        limit=10 = 最近 ~3.3 天的结算记录

        Returns
        -------
        List[Dict] or None
            [
                {
                    "symbol": "BTCUSDT",
                    "fundingTime": 1234567890000,
                    "fundingRate": "0.00010000",
                    "markPrice": "50000.00"
                },
                ...
            ]
        """
        try:
            url = f"{self.BASE_URL}/fapi/v1/fundingRate"
            params = {"symbol": symbol, "limit": limit}

            response = requests.get(url, params=params, timeout=self.timeout)

            if response.status_code == 200:
                return response.json()
            else:
                self.logger.warning(
                    f"⚠️ Binance funding rate history API error: {response.status_code}"
                )
                return None

        except Exception as e:
            self.logger.warning(f"⚠️ Binance funding rate history fetch error: {e}")
            return None
