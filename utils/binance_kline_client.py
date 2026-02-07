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
        获取 Binance 资金费率数据 (含预期费率)

        从 premiumIndex 提取当前费率，从 premiumIndexKlines 计算预期费率。
        - lastFundingRate: 上次已结算费率 (8小时一次)
        - predicted_rate: 通过时间加权平均溢价指数计算的预期费率

        预期费率计算方法 (与币安 App 一致):
        Funding Rate = avg_premium + clamp(interest_rate - avg_premium, -0.05%, +0.05%)
        avg_premium = 时间加权平均(premiumIndexKlines 1m bars)

        Returns
        -------
        Dict or None
            {
                "symbol": "BTCUSDT",
                "funding_rate": 0.0001,           # 上次结算费率 (原始值)
                "funding_rate_pct": 0.01,         # 上次结算费率 (百分比)
                "predicted_rate": -0.000137,      # 预期费率 (原始值)
                "predicted_rate_pct": -0.0137,    # 预期费率 (百分比)
                "next_funding_time": 1234567890000,
                "next_funding_countdown_min": 180,
                "mark_price": 98000.0,
                "index_price": 97950.0,
                "interest_rate": 0.0001,
                "premium_index": 0.00051,         # 当前瞬时溢价指数
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

                # 瞬时溢价指数 (仅供参考，不等于平均溢价)
                premium_index = 0.0
                if index_price > 0:
                    premium_index = (mark_price - index_price) / index_price

                # 计算距下次结算的分钟数
                countdown_min = None
                if next_funding_time and next_funding_time > 0:
                    now_ms = int(time.time() * 1000)
                    remaining_ms = next_funding_time - now_ms
                    if remaining_ms > 0:
                        countdown_min = round(remaining_ms / 60000)

                # 计算预期资金费率 (从 premiumIndexKlines 时间加权平均)
                predicted_rate = None
                predicted_rate_pct = None
                try:
                    predicted = self._calc_predicted_funding_rate(
                        symbol=symbol,
                        interest_rate=interest_rate,
                    )
                    if predicted is not None:
                        predicted_rate = predicted
                        predicted_rate_pct = round(predicted * 100, 4)
                except Exception as e:
                    self.logger.debug(f"⚠️ Predicted funding rate calc error: {e}")

                return {
                    "symbol": data.get('symbol'),
                    "funding_rate": funding_rate,
                    "funding_rate_pct": round(funding_rate * 100, 4),
                    "predicted_rate": predicted_rate,
                    "predicted_rate_pct": predicted_rate_pct,
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

    def _calc_predicted_funding_rate(
        self,
        symbol: str = "BTCUSDT",
        interest_rate: float = 0.0001,
        interval_hours: int = 8,
    ) -> Optional[float]:
        """
        计算预期资金费率 (与币安 App 显示一致)

        使用 premiumIndexKlines 1分钟数据计算时间加权平均溢价指数,
        然后应用 Binance 资金费率公式。

        公式:
        Funding Rate = avg_premium + clamp(interest - avg_premium, -0.05%, +0.05%)

        其中 avg_premium = 线性加权平均(从当前 funding period 开始到现在的溢价指数)

        Parameters
        ----------
        symbol : str
            交易对
        interest_rate : float
            利息率 (通常 0.0001 = 0.01%)
        interval_hours : int
            资金费率结算周期 (BTCUSDT = 8h)

        Returns
        -------
        float or None
            预期资金费率 (原始值, 如 -0.000137)
        """
        # 获取当前 funding period 内的 premiumIndex K线
        # interval_hours * 60 = 分钟数, 但只取到当前 period 内的
        bars_needed = interval_hours * 60  # 最多 480 根 1m bar (8h)

        url = f"{self.BASE_URL}/fapi/v1/premiumIndexKlines"
        params = {
            "symbol": symbol,
            "interval": "1m",
            "limit": bars_needed,
        }

        response = requests.get(url, params=params, timeout=self.timeout)
        if response.status_code != 200:
            return None

        klines = response.json()
        if not klines or len(klines) < 10:  # 至少需要 10 根 K线
            return None

        # 提取 close 价格 (溢价指数值)
        premiums = [float(k[4]) for k in klines]
        n = len(premiums)

        # 时间加权平均 (线性权重: 最旧=1, 最新=n)
        # 这与 Binance 内部的 TWAP 算法一致
        weight_sum = n * (n + 1) / 2
        weighted_sum = sum((i + 1) * p for i, p in enumerate(premiums))
        avg_premium = weighted_sum / weight_sum

        # 应用资金费率公式
        damper = 0.0005  # 0.05% clamp 阈值
        clamped = max(-damper, min(damper, interest_rate - avg_premium))
        predicted_rate = avg_premium + clamped

        return predicted_rate

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
