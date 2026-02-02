"""
Binance Account Utilities

Provides real-time account balance and position information from Binance Futures API.
"""

import os
import time
import hmac
import hashlib
import logging
import urllib.request
import urllib.error
import json
from typing import Dict, Any, Optional


class BinanceAccountFetcher:
    """
    Fetches real-time account information from Binance Futures API.

    This class provides methods to:
    - Get account balance (total wallet balance, available balance)
    - Get open positions with unrealized PnL
    - Get account leverage and margin info
    """

    BASE_URL = "https://fapi.binance.com"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        cache_ttl: float = 5.0,
        recv_window: int = 5000,
        api_timeout: float = 10.0,
    ):
        """
        Initialize Binance account fetcher.

        Parameters
        ----------
        api_key : str, optional
            Binance API key (defaults to BINANCE_API_KEY env var)
        api_secret : str, optional
            Binance API secret (defaults to BINANCE_API_SECRET env var)
        logger : logging.Logger, optional
            Logger instance
        cache_ttl : float, optional
            Cache time-to-live (seconds), default: 5.0
        recv_window : int, optional
            Binance API receive window (ms), default: 5000
        api_timeout : float, optional
            API request timeout (seconds), default: 10.0
        """
        self.api_key = api_key or os.getenv('BINANCE_API_KEY', '')
        self.api_secret = api_secret or os.getenv('BINANCE_API_SECRET', '')
        self.logger = logger or logging.getLogger(__name__)

        # Cache for rate limiting
        self._cache: Dict[str, Any] = {}
        self._cache_time: float = 0
        self._cache_ttl: float = cache_ttl

        # Binance API configuration
        self._recv_window: int = recv_window
        self._api_timeout: float = api_timeout

    def _sign_request(self, params: Dict[str, Any]) -> str:
        """Create HMAC SHA256 signature for request."""
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(
            self.api_secret.encode(),
            query_string.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Make authenticated request to Binance API."""
        if not self.api_key or not self.api_secret:
            self.logger.warning("Binance API credentials not configured")
            return None

        try:
            # Add timestamp
            if params is None:
                params = {}
            params['timestamp'] = int(time.time() * 1000)
            params['recvWindow'] = self._recv_window

            # Sign request
            signature = self._sign_request(params)
            params['signature'] = signature

            # Build URL
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            url = f"{self.BASE_URL}{endpoint}?{query_string}"

            # Make request
            req = urllib.request.Request(url, headers={
                "X-MBX-APIKEY": self.api_key,
                "User-Agent": "AItrader/1.0"
            })

            response = urllib.request.urlopen(req, timeout=self._api_timeout)
            data = json.loads(response.read())
            return data

        except urllib.error.HTTPError as e:
            error_body = e.read().decode()[:200]
            self.logger.error(f"Binance API HTTP error {e.code}: {error_body}")
            return None
        except Exception as e:
            self.logger.error(f"Binance API request failed: {e}")
            return None

    def get_account_info(self, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get full account information from Binance Futures.

        Returns
        -------
        dict or None
            Account info including balances, positions, etc.
        """
        # Check cache
        if use_cache and self._cache and (time.time() - self._cache_time) < self._cache_ttl:
            return self._cache

        data = self._make_request("/fapi/v2/account")

        if data:
            self._cache = data
            self._cache_time = time.time()

        return data

    def get_balance(self) -> Dict[str, float]:
        """
        Get account balance information.

        Returns
        -------
        dict
            Balance info with keys:
            - total_balance: Total wallet balance (USDT)
            - available_balance: Available for trading (USDT)
            - unrealized_pnl: Total unrealized PnL (USDT)
            - margin_balance: Margin balance (USDT)
        """
        account = self.get_account_info()

        if not account:
            return {
                'total_balance': 0.0,
                'available_balance': 0.0,
                'unrealized_pnl': 0.0,
                'margin_balance': 0.0,
                'error': 'Failed to fetch account info'
            }

        return {
            'total_balance': float(account.get('totalWalletBalance', 0)),
            'available_balance': float(account.get('availableBalance', 0)),
            'unrealized_pnl': float(account.get('totalUnrealizedProfit', 0)),
            'margin_balance': float(account.get('totalMarginBalance', 0)),
        }

    def get_positions(self, symbol: Optional[str] = None) -> list:
        """
        Get open positions.

        Parameters
        ----------
        symbol : str, optional
            Filter by symbol (e.g., 'BTCUSDT')

        Returns
        -------
        list
            List of position dicts with non-zero amounts
        """
        account = self.get_account_info()

        if not account:
            return []

        positions = account.get('positions', [])

        # Filter non-zero positions
        active_positions = [
            p for p in positions
            if float(p.get('positionAmt', 0)) != 0
        ]

        # Filter by symbol if specified
        if symbol:
            # Remove -PERP suffix if present
            clean_symbol = symbol.replace('-PERP', '').replace('.BINANCE', '')
            active_positions = [
                p for p in active_positions
                if p.get('symbol', '').upper() == clean_symbol.upper()
            ]

        return active_positions

    def get_position_summary(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get a summary of position information.

        Returns
        -------
        dict
            Position summary with balance and position info
        """
        balance = self.get_balance()
        positions = self.get_positions(symbol)

        return {
            'balance': balance,
            'positions': positions,
            'positions_count': len(positions),
            'has_position': len(positions) > 0,
        }

    def get_trades(self, symbol: str, limit: int = 10) -> list:
        """
        获取最近的交易记录。

        Parameters
        ----------
        symbol : str
            交易对 (e.g., 'BTCUSDT')
        limit : int, optional
            返回记录数量, 默认 10

        Returns
        -------
        list
            交易记录列表
        """
        # 清理 symbol 格式
        clean_symbol = symbol.replace('-PERP', '').replace('.BINANCE', '').upper()

        params = {
            'symbol': clean_symbol,
            'limit': limit,
        }

        data = self._make_request("/fapi/v1/userTrades", params)

        if data is None:
            return []

        return data

    def get_income_history(self, income_type: Optional[str] = None, limit: int = 20) -> list:
        """
        获取收益历史 (包含资金费率、盈亏等)。

        Parameters
        ----------
        income_type : str, optional
            收益类型: REALIZED_PNL, FUNDING_FEE, COMMISSION, etc.
        limit : int, optional
            返回记录数量, 默认 20

        Returns
        -------
        list
            收益记录列表
        """
        params = {'limit': limit}

        if income_type:
            params['incomeType'] = income_type

        data = self._make_request("/fapi/v1/income", params)

        if data is None:
            return []

        return data


# Singleton instance for convenience
_fetcher_instance: Optional[BinanceAccountFetcher] = None


def get_binance_fetcher(
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    cache_ttl: float = 5.0,
    recv_window: int = 5000,
    api_timeout: float = 10.0,
) -> BinanceAccountFetcher:
    """Get or create a BinanceAccountFetcher instance."""
    global _fetcher_instance

    if _fetcher_instance is None:
        _fetcher_instance = BinanceAccountFetcher(
            api_key=api_key,
            api_secret=api_secret,
            logger=logger,
            cache_ttl=cache_ttl,
            recv_window=recv_window,
            api_timeout=api_timeout,
        )

    return _fetcher_instance


def fetch_real_balance() -> Dict[str, float]:
    """
    Convenience function to fetch real account balance.

    Returns
    -------
    dict
        Balance info with total_balance, available_balance, etc.
    """
    fetcher = get_binance_fetcher()
    return fetcher.get_balance()
