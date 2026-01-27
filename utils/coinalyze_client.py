# utils/coinalyze_client.py

import requests
import time
import logging
from typing import Optional, Dict, Any
import os


class CoinalyzeClient:
    """
    Coinalyze API 客户端 (同步版本)

    获取衍生品数据: OI, 清算, 资金费率

    设计原则:
    - 同步调用，兼容 on_timer() 回调
    - 参考 sentiment_client.py 的错误处理模式
    - 支持指数退避重试
    """

    BASE_URL = "https://api.coinalyze.net/v1"
    DEFAULT_SYMBOL = "BTCUSDT_PERP.A"

    def __init__(
        self,
        api_key: str = None,
        timeout: int = 10,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        logger: logging.Logger = None,
    ):
        """
        初始化 Coinalyze 客户端

        Parameters
        ----------
        api_key : str
            API Key (从 ~/.env.aitrader 的 COINALYZE_API_KEY 读取)
        timeout : int
            请求超时 (秒)
        max_retries : int
            最大重试次数
        retry_delay : float
            重试基础延迟 (秒)，使用指数退避
        logger : Logger
            日志记录器
        """
        self.api_key = api_key or os.getenv("COINALYZE_API_KEY")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = logger or logging.getLogger(__name__)
        self._enabled = bool(self.api_key)

        if not self._enabled:
            self.logger.warning("⚠️ COINALYZE_API_KEY not set, Coinalyze client disabled")

    def _get_headers(self) -> Dict[str, str]:
        """构建请求头"""
        return {"api_key": self.api_key} if self.api_key else {}

    def _request_with_retry(
        self,
        endpoint: str,
        params: Dict[str, Any],
    ) -> Optional[Dict]:
        """
        带重试的 HTTP 请求

        Parameters
        ----------
        endpoint : str
            API 端点 (如 "/open-interest")
        params : Dict
            查询参数

        Returns
        -------
        Optional[Dict]
            API 响应，失败返回 None
        """
        url = f"{self.BASE_URL}{endpoint}"
        headers = self._get_headers()

        for attempt in range(self.max_retries + 1):
            try:
                response = requests.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )

                if response.status_code == 200:
                    data = response.json()
                    return data[0] if data else None

                elif response.status_code == 429:
                    self.logger.warning("⚠️ Coinalyze rate limit reached (429)")
                    # 速率限制时等待更长时间
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay * (2 ** attempt) * 2)
                        continue
                    return None

                else:
                    self.logger.warning(
                        f"⚠️ Coinalyze API error: {response.status_code}"
                    )
                    return None

            except requests.exceptions.Timeout:
                self.logger.warning(
                    f"⚠️ Coinalyze timeout (attempt {attempt + 1}/{self.max_retries + 1})"
                )
            except requests.exceptions.RequestException as e:
                self.logger.warning(
                    f"⚠️ Coinalyze request error (attempt {attempt + 1}): {e}"
                )

            # 指数退避
            if attempt < self.max_retries:
                time.sleep(self.retry_delay * (2 ** attempt))

        return None

    def get_open_interest(self, symbol: str = None) -> Optional[Dict]:
        """
        获取当前 Open Interest

        Returns:
            {
                "symbol": "BTCUSDT_PERP.A",
                "value": 102199.59,       # BTC 数量 (非 USD!)
                "update": 1769417410150   # 毫秒时间戳
            }

        注意: value 是 BTC 数量，需要乘以当前价格转换为 USD
        """
        if not self._enabled:
            return None

        symbol = symbol or self.DEFAULT_SYMBOL
        return self._request_with_retry(
            endpoint="/open-interest",
            params={"symbols": symbol},
        )

    def get_liquidations(
        self,
        symbol: str = None,
        interval: str = "1hour",
    ) -> Optional[Dict]:
        """
        获取清算历史

        Args:
            symbol: 交易对 (默认 BTCUSDT_PERP.A)
            interval: 1hour, 4hour, daily 等

        Returns:
            {
                "symbol": "...",
                "history": [
                    {"t": 1769418000, "l": 123456.78, "s": 98765.43}
                ]
            }

        注意:
        - t 是秒时间戳 (10位)
        - l = long liquidations (USD)
        - s = short liquidations (USD)
        """
        if not self._enabled:
            return None

        symbol = symbol or self.DEFAULT_SYMBOL
        return self._request_with_retry(
            endpoint="/liquidation-history",
            params={
                "symbols": symbol,
                "interval": interval,
                "from": int(time.time()) - 3600,  # 秒!
                "to": int(time.time()),
            },
        )

    def get_funding_rate(self, symbol: str = None) -> Optional[Dict]:
        """
        获取当前资金费率

        Returns:
            {
                "symbol": "BTCUSDT_PERP.A",
                "value": 0.002847,       # 0.2847%
                "update": 1769420174380  # 毫秒时间戳
            }
        """
        if not self._enabled:
            return None

        symbol = symbol or self.DEFAULT_SYMBOL
        return self._request_with_retry(
            endpoint="/funding-rate",
            params={"symbols": symbol},
        )

    def fetch_all(self, symbol: str = None) -> Dict[str, Any]:
        """
        一次性获取所有衍生品数据 (便捷方法)

        Returns:
            {
                "open_interest": {...} or None,
                "liquidations": {...} or None,
                "funding_rate": {...} or None,
                "enabled": bool,
            }
        """
        if not self._enabled:
            return {
                "open_interest": None,
                "liquidations": None,
                "funding_rate": None,
                "enabled": False,
            }

        return {
            "open_interest": self.get_open_interest(symbol),
            "liquidations": self.get_liquidations(symbol),
            "funding_rate": self.get_funding_rate(symbol),
            "enabled": True,
        }

    def is_enabled(self) -> bool:
        """检查客户端是否启用"""
        return self._enabled
