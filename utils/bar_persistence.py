"""
Bar Persistence Utilities for NautilusTrader Strategy

Provides multiple options for storing and loading historical bar data:
1. ParquetDataCatalog (NautilusTrader built-in)
2. Redis storage
3. Binance API pre-fetch
"""

from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta
import os

from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.model.identifiers import InstrumentId


class BarPersistenceManager:
    """
    Manages bar data persistence using NautilusTrader's ParquetDataCatalog.

    This is the recommended approach for persisting bar data as it:
    - Integrates natively with NautilusTrader
    - Uses efficient Parquet format
    - Supports backtesting with same data
    - Requires no external dependencies
    """

    def __init__(self, catalog_path: str = "./data_catalog"):
        """
        Initialize bar persistence manager.

        Parameters
        ----------
        catalog_path : str
            Path to the Parquet data catalog directory
        """
        self.catalog_path = Path(catalog_path)
        self.catalog = ParquetDataCatalog(self.catalog_path)

    def save_bar(self, bar: Bar):
        """
        Save a single bar to the catalog.

        Parameters
        ----------
        bar : Bar
            The bar to save
        """
        try:
            self.catalog.write_data([bar])
        except (IOError, OSError) as e:
            raise RuntimeError(f"Failed to save bar to catalog (I/O error): {e}")
        except Exception as e:
            # Log unexpected errors but still raise
            import logging
            logging.getLogger(__name__).critical(f"Unexpected error saving bar: {e}", exc_info=True)
            raise RuntimeError(f"Failed to save bar to catalog (unexpected error): {e}")

    def save_bars(self, bars: List[Bar]):
        """
        Save multiple bars to the catalog.

        Parameters
        ----------
        bars : List[Bar]
            List of bars to save
        """
        try:
            if bars:
                self.catalog.write_data(bars)
        except Exception as e:
            raise RuntimeError(f"Failed to save bars to catalog: {e}")

    def load_bars(
        self,
        instrument_id: InstrumentId,
        bar_type: BarType,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Bar]:
        """
        Load historical bars from the catalog.

        Parameters
        ----------
        instrument_id : InstrumentId
            The instrument identifier
        bar_type : BarType
            The bar type specification
        start : datetime, optional
            Start time for data range
        end : datetime, optional
            End time for data range
        limit : int, optional
            Maximum number of bars to load (most recent)

        Returns
        -------
        List[Bar]
            List of bars loaded from catalog
        """
        try:
            # Query bars from catalog
            bars = self.catalog.bars(
                instrument_ids=[str(instrument_id)],
                bar_types=[str(bar_type)],
                start=start,
                end=end,
            )

            if bars is None or len(bars) == 0:
                return []

            # Apply limit if specified (take most recent)
            if limit and len(bars) > limit:
                bars = bars[-limit:]

            return bars

        except Exception as e:
            raise RuntimeError(f"Failed to load bars from catalog: {e}")

    def get_bar_count(
        self,
        instrument_id: InstrumentId,
        bar_type: BarType,
    ) -> int:
        """
        Get the count of stored bars.

        Parameters
        ----------
        instrument_id : InstrumentId
            The instrument identifier
        bar_type : BarType
            The bar type specification

        Returns
        -------
        int
            Number of bars stored
        """
        try:
            bars = self.load_bars(instrument_id, bar_type)
            return len(bars)
        except Exception:
            return 0


class RedisBarsStorage:
    """
    Redis-based bar storage (alternative to ParquetDataCatalog).

    Use this if you need:
    - Real-time cross-strategy data sharing
    - In-memory fast access
    - TTL-based expiration

    Not recommended for primary storage due to RAM usage.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 1,
        password: Optional[str] = None,
        ttl_hours: int = 168,  # 7 days default
    ):
        """
        Initialize Redis bar storage.

        Parameters
        ----------
        host : str
            Redis host
        port : int
            Redis port
        db : int
            Redis database number
        password : str, optional
            Redis password
        ttl_hours : int
            Time-to-live for bars in hours
        """
        try:
            import redis
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=False,  # We'll handle serialization
            )
            self.ttl_seconds = ttl_hours * 3600
            self.redis_client.ping()  # Test connection
        except ImportError:
            raise ImportError("redis-py not installed. Run: pip install redis")
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Redis: {e}")

    def save_bar(self, bar: Bar):
        """
        Save bar to Redis.

        Parameters
        ----------
        bar : Bar
            The bar to save
        """
        try:
            import pickle

            # Create key: bars:{instrument}:{bar_type}:{timestamp}
            key = f"bars:{bar.bar_type.instrument_id}:{bar.bar_type}:{bar.ts_init}"

            # Serialize bar
            bar_data = pickle.dumps(bar)

            # Store with TTL
            self.redis_client.setex(key, self.ttl_seconds, bar_data)

        except Exception as e:
            raise RuntimeError(f"Failed to save bar to Redis: {e}")

    def load_bars(
        self,
        instrument_id: InstrumentId,
        bar_type: BarType,
        limit: int = 100,
    ) -> List[Bar]:
        """
        Load bars from Redis.

        Parameters
        ----------
        instrument_id : InstrumentId
            The instrument identifier
        bar_type : BarType
            The bar type specification
        limit : int
            Maximum number of bars to load

        Returns
        -------
        List[Bar]
            List of bars loaded from Redis
        """
        try:
            import pickle

            # Pattern match keys
            pattern = f"bars:{instrument_id}:{bar_type}:*"
            keys = self.redis_client.keys(pattern)

            if not keys:
                return []

            # Sort keys by timestamp (last part of key)
            keys = sorted(keys, key=lambda k: int(k.decode().split(':')[-1]))

            # Take most recent 'limit' bars
            keys = keys[-limit:] if len(keys) > limit else keys

            # Load bars
            bars = []
            for key in keys:
                bar_data = self.redis_client.get(key)
                if bar_data:
                    bar = pickle.loads(bar_data)
                    bars.append(bar)

            return bars

        except Exception as e:
            raise RuntimeError(f"Failed to load bars from Redis: {e}")

    def clear_bars(self, instrument_id: InstrumentId, bar_type: BarType):
        """Clear all bars for an instrument/bar_type."""
        try:
            pattern = f"bars:{instrument_id}:{bar_type}:*"
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
        except Exception as e:
            raise RuntimeError(f"Failed to clear bars from Redis: {e}")


class BinanceBarFetcher:
    """
    Fetch historical bars directly from Binance API on startup.

    This is the simplest approach - no storage needed!
    """

    def __init__(
        self,
        api_type: str = "futures",
        max_limit: int = 1500,
        timeout: float = 10.0,
    ):
        """
        Initialize Binance bar fetcher.

        Parameters
        ----------
        api_type : str
            Either 'spot' or 'futures'
        max_limit : int, optional
            Maximum klines to fetch per request, default: 1500
        timeout : float, optional
            Request timeout (seconds), default: 10.0
        """
        self.api_type = api_type
        self.base_url = (
            "https://fapi.binance.com" if api_type == "futures"
            else "https://api.binance.com"
        )
        self.max_limit = max_limit
        self.timeout = timeout

    def fetch_bars(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
    ) -> List[dict]:
        """
        Fetch historical klines from Binance.

        Parameters
        ----------
        symbol : str
            Trading pair symbol (e.g., 'BTCUSDT')
        interval : str
            Kline interval (e.g., '1m', '5m', '15m', '1h', '4h', '1d')
        limit : int
            Number of klines to fetch (max 1500)

        Returns
        -------
        List[dict]
            List of kline data dictionaries
        """
        try:
            import requests

            endpoint = f"{self.base_url}/fapi/v1/klines" if self.api_type == "futures" else f"{self.base_url}/api/v3/klines"

            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': min(limit, self.max_limit),  # Binance max
            }

            response = requests.get(endpoint, params=params, timeout=self.timeout)
            response.raise_for_status()

            klines = response.json()

            # Convert to structured format
            bars_data = []
            for kline in klines:
                bars_data.append({
                    'timestamp': kline[0],  # Open time
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5]),
                })

            return bars_data

        except Exception as e:
            raise RuntimeError(f"Failed to fetch bars from Binance: {e}")

    def convert_interval_from_bar_type(self, bar_type: str) -> str:
        """
        Convert NautilusTrader bar type to Binance interval.

        Parameters
        ----------
        bar_type : str
            Bar type string (e.g., 'BTCUSDT-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL')

        Returns
        -------
        str
            Binance interval string (e.g., '5m')
        """
        # Extract aggregation from bar type
        # Format: INSTRUMENT-AGGREGATION-SPEC-PRICE-TYPE
        parts = bar_type.split('-')

        if 'MINUTE' in bar_type:
            # Find the number before MINUTE
            for i, part in enumerate(parts):
                if part == 'MINUTE' and i > 0:
                    minutes = parts[i-1]
                    return f"{minutes}m"
        elif 'HOUR' in bar_type:
            for i, part in enumerate(parts):
                if part == 'HOUR' and i > 0:
                    hours = parts[i-1]
                    return f"{hours}h"
        elif 'DAY' in bar_type:
            return "1d"

        # Default fallback
        return "5m"
