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

        # Binance server time offset (local_time + offset = binance_time)
        self._time_offset_ms: int = 0
        self._time_offset_synced: bool = False

    def _sync_server_time(self) -> bool:
        """
        Synchronize local clock with Binance server time.

        Calculates the offset between local time and Binance server time
        to prevent -1021 (Timestamp outside recvWindow) errors.

        Returns
        -------
        bool
            True if sync succeeded
        """
        try:
            url = f"{self.BASE_URL}/fapi/v1/time"
            req = urllib.request.Request(url, headers={
                "User-Agent": "AItrader/1.0"
            })

            t_before = int(time.time() * 1000)
            response = urllib.request.urlopen(req, timeout=self._api_timeout)
            t_after = int(time.time() * 1000)
            data = json.loads(response.read())

            server_time = data.get('serverTime', 0)
            if server_time <= 0:
                self.logger.warning("Binance server time response invalid")
                return False

            # Use midpoint of request as local reference (accounts for network latency)
            local_time = (t_before + t_after) // 2
            self._time_offset_ms = server_time - local_time
            self._time_offset_synced = True
            self._time_offset_synced_at = time.time()

            if abs(self._time_offset_ms) > 1000:
                self.logger.warning(
                    f"Binance time offset: {self._time_offset_ms}ms "
                    f"(local clock is {'behind' if self._time_offset_ms > 0 else 'ahead'})"
                )
            else:
                self.logger.debug(f"Binance time offset: {self._time_offset_ms}ms")

            return True

        except Exception as e:
            self.logger.error(f"Failed to sync Binance server time: {e}")
            return False

    def _get_synced_timestamp(self) -> int:
        """Get current timestamp adjusted for Binance server time offset."""
        # Re-sync every 30 minutes (clock drift)
        if (not self._time_offset_synced or
                (time.time() - getattr(self, '_time_offset_synced_at', 0)) > 1800):
            self._sync_server_time()

        return int(time.time() * 1000) + self._time_offset_ms

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
        """Make authenticated request to Binance API with time sync."""
        if not self.api_key or not self.api_secret:
            self.logger.warning("Binance API credentials not configured")
            return None

        max_retries = 2  # retry once on -1021
        for attempt in range(max_retries):
            try:
                if params is None:
                    params = {}
                # Use synced timestamp instead of raw local time
                params['timestamp'] = self._get_synced_timestamp()
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

                # Handle -1021: Timestamp outside recvWindow
                if e.code == 400 and '-1021' in error_body:
                    if attempt < max_retries - 1:
                        self.logger.warning(
                            f"Binance -1021 timestamp error, re-syncing server time (attempt {attempt + 1})"
                        )
                        self._time_offset_synced = False
                        self._sync_server_time()
                        # Remove stale signature for retry
                        params.pop('signature', None)
                        params.pop('timestamp', None)
                        continue
                    else:
                        self.logger.error(
                            f"Binance -1021 timestamp error persists after re-sync. "
                            f"Offset: {self._time_offset_ms}ms"
                        )

                self.logger.error(f"Binance API HTTP error {e.code}: {error_body}")
                return None
            except Exception as e:
                self.logger.error(f"Binance API request failed: {e}")
                return None

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

    def get_leverage(self, symbol: str) -> int:
        """
        Get the actual leverage setting for a symbol from Binance.

        Parameters
        ----------
        symbol : str
            Trading symbol (e.g., 'BTCUSDT' or 'BTCUSDT-PERP.BINANCE')

        Returns
        -------
        int
            Leverage multiplier (e.g., 10 for 10x leverage)
            Returns 1 if unable to fetch
        """
        account = self.get_account_info()
        if not account:
            self.logger.warning("Cannot fetch leverage: account info unavailable")
            return 1

        # Clean symbol format
        clean_symbol = symbol.replace('-PERP', '').replace('.BINANCE', '').upper()

        # Find position info for this symbol
        positions = account.get('positions', [])
        for pos in positions:
            if pos.get('symbol', '').upper() == clean_symbol:
                leverage = int(pos.get('leverage', 1))
                self.logger.debug(f"Binance leverage for {clean_symbol}: {leverage}x")
                return leverage

        self.logger.warning(f"Symbol {clean_symbol} not found in account positions")
        return 1

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

    def get_position_mode(self) -> str:
        """
        Get Binance Futures position mode.

        Returns
        -------
        str
            "ONE_WAY" when dualSidePosition is false,
            "HEDGE" when dualSidePosition is true,
            "UNKNOWN" on API failure.
        """
        data = self._make_request("/fapi/v1/positionSide/dual")
        if not data:
            return "UNKNOWN"

        dual_side = data.get('dualSidePosition')
        if isinstance(dual_side, bool):
            return "HEDGE" if dual_side else "ONE_WAY"

        # Defensive parsing for non-boolean payloads
        dual_side_str = str(dual_side).lower()
        if dual_side_str in ('true', '1'):
            return "HEDGE"
        if dual_side_str in ('false', '0'):
            return "ONE_WAY"

        return "UNKNOWN"

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """
        获取当前挂单列表 (用于恢复 SL/TP 状态).

        Parameters
        ----------
        symbol : str, optional
            交易对 (e.g., 'BTCUSDT')，不指定则返回所有挂单

        Returns
        -------
        list
            挂单列表，每个订单包含:
            - orderId, symbol, type, side, price, stopPrice, origQty, status
        """
        params = {}
        if symbol:
            clean_symbol = symbol.replace('-PERP', '').replace('.BINANCE', '').upper()
            params['symbol'] = clean_symbol

        data = self._make_request("/fapi/v1/openOrders", params)

        if data is None:
            return []

        return data

    def get_sl_tp_from_orders(self, symbol: str, position_side: str) -> Dict[str, Optional[float]]:
        """
        从挂单中提取止损止盈价格.

        服务器重启后，trailing_stop_state 会丢失，但 Binance 上的挂单还在。
        此方法用于恢复 SL/TP 状态。

        Parameters
        ----------
        symbol : str
            交易对 (e.g., 'BTCUSDT')
        position_side : str
            持仓方向 ('long' 或 'short')

        Returns
        -------
        dict
            {'sl_price': float or None, 'tp_price': float or None}
        """
        orders = self.get_open_orders(symbol)
        if not orders:
            return {'sl_price': None, 'tp_price': None}

        sl_price = None
        tp_price = None

        # 分析每个挂单
        for order in orders:
            order_type = order.get('type', '').upper()
            order_side = order.get('side', '').upper()
            stop_price = float(order.get('stopPrice', 0))
            limit_price = float(order.get('price', 0))
            reduce_only = order.get('reduceOnly', False)

            # 只看 reduce-only 订单 (SL/TP 都是 reduce-only)
            if not reduce_only:
                continue

            is_long = position_side.lower() == 'long'

            # LONG 持仓的 SL: SELL + STOP_MARKET (stop < entry)
            # LONG 持仓的 TP: SELL + TAKE_PROFIT_MARKET (stop > entry)
            # SHORT 持仓的 SL: BUY + STOP_MARKET (stop > entry)
            # SHORT 持仓的 TP: BUY + TAKE_PROFIT_MARKET (stop < entry)

            if order_type in ['STOP_MARKET', 'STOP']:
                # 止损单
                if is_long and order_side == 'SELL':
                    sl_price = stop_price
                elif not is_long and order_side == 'BUY':
                    sl_price = stop_price

            elif order_type in ['TAKE_PROFIT_MARKET', 'TAKE_PROFIT']:
                # 止盈单
                if is_long and order_side == 'SELL':
                    tp_price = stop_price
                elif not is_long and order_side == 'BUY':
                    tp_price = stop_price

            elif order_type == 'LIMIT' and reduce_only:
                # 限价止盈单
                if is_long and order_side == 'SELL' and limit_price > 0:
                    tp_price = limit_price
                elif not is_long and order_side == 'BUY' and limit_price > 0:
                    tp_price = limit_price

        self.logger.debug(f"从 Binance 挂单恢复 SL/TP: SL=${sl_price}, TP=${tp_price}")
        return {'sl_price': sl_price, 'tp_price': tp_price}

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

    def get_realtime_price(self, symbol: str) -> Optional[float]:
        """
        Get real-time mark price from Binance Futures API.

        This is the actual current price, not a cached bar close price.

        Parameters
        ----------
        symbol : str
            Trading symbol (e.g., 'BTCUSDT' or 'BTCUSDT-PERP.BINANCE')

        Returns
        -------
        float or None
            Current mark price
        """
        clean_symbol = symbol.replace('-PERP', '').replace('.BINANCE', '').upper()
        try:
            url = f"{self.BASE_URL}/fapi/v1/ticker/price?symbol={clean_symbol}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "AItrader/1.0"
            })
            response = urllib.request.urlopen(req, timeout=self._api_timeout)
            data = json.loads(response.read())
            price = float(data.get('price', 0))
            return price if price > 0 else None
        except Exception as e:
            self.logger.debug(f"Failed to fetch realtime price for {clean_symbol}: {e}")
            return None

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
