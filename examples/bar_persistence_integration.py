"""
Example: Integrating Bar Persistence into DeepSeek Strategy

This file shows 3 approaches for persisting and loading bar data:
1. ParquetDataCatalog (Recommended)
2. Redis Storage
3. Binance API Pre-fetch (Simplest)

Choose the one that fits your needs best.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from typing import Optional
from nautilus_trader.model.data import Bar
from utils.bar_persistence import (
    BarPersistenceManager,
    RedisBarsStorage,
    BinanceBarFetcher,
)


# ============================================================================
# APPROACH 1: ParquetDataCatalog Integration (RECOMMENDED)
# ============================================================================

class DeepSeekStrategyWithParquetPersistence:
    """
    Example showing ParquetDataCatalog integration.

    Benefits:
    - Native NautilusTrader support
    - Efficient storage (~KB per day)
    - Backtest compatibility
    """

    def __init__(self, config):
        # ... your existing initialization ...

        # Initialize bar persistence
        self.bar_persistence = BarPersistenceManager(
            catalog_path="./nautilus_data_catalog"
        )

        # Flag to track if we've loaded historical data
        self.historical_bars_loaded = False

    def on_start(self):
        """Modified on_start with historical bar loading."""
        self.log.info("Starting DeepSeek AI Strategy...")

        # Load instrument
        self.instrument = self.cache.instrument(self.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument {self.instrument_id}")
            self.stop()
            return

        # *** LOAD HISTORICAL BARS FROM CATALOG ***
        self._load_historical_bars_from_catalog()

        # Subscribe to bars (continue receiving live bars)
        self.subscribe_bars(self.bar_type)
        self.log.info(f"Subscribed to {self.bar_type}")

        # ... rest of your on_start code ...

    def _load_historical_bars_from_catalog(self):
        """Load historical bars from Parquet catalog and feed to indicators."""
        try:
            # Load last 200 bars (adjust based on your indicator requirements)
            # Example: If you need 50 SMA, load at least 50+ bars
            bars = self.bar_persistence.load_bars(
                instrument_id=self.instrument_id,
                bar_type=self.bar_type,
                limit=200,
            )

            if bars:
                self.log.info(f"📊 Loading {len(bars)} historical bars from catalog...")

                # Feed bars to indicator manager
                for bar in bars:
                    self.indicator_manager.update(bar)

                self.log.info(
                    f"✅ Loaded {len(bars)} bars. "
                    f"Indicators ready: {self.indicator_manager.is_initialized()}"
                )
                self.historical_bars_loaded = True
            else:
                self.log.warning(
                    "⚠️ No historical bars found in catalog. "
                    "Waiting for live bars..."
                )

        except Exception as e:
            self.log.error(f"❌ Failed to load historical bars: {e}")
            self.log.warning("Continuing with live bars only...")

    def on_bar(self, bar: Bar):
        """Modified on_bar to save bars to catalog."""
        self.bars_received += 1

        # Update indicators
        self.indicator_manager.update(bar)

        # *** SAVE BAR TO CATALOG ***
        try:
            self.bar_persistence.save_bar(bar)
        except Exception as e:
            self.log.warning(f"Failed to save bar to catalog: {e}")

        # Log bar data
        if self.bars_received % 10 == 0:
            self.log.info(
                f"Bar #{self.bars_received}: "
                f"O:{bar.open} H:{bar.high} L:{bar.low} C:{bar.close} V:{bar.volume}"
            )


# ============================================================================
# APPROACH 2: Redis Storage Integration
# ============================================================================

class DeepSeekStrategyWithRedisPersistence:
    """
    Example showing Redis integration.

    Benefits:
    - Fast in-memory access
    - Cross-strategy data sharing
    - Real-time updates

    Drawbacks:
    - Uses RAM
    - Requires Redis server
    """

    def __init__(self, config):
        # ... your existing initialization ...

        # Initialize Redis bar storage
        self.redis_storage = RedisBarsStorage(
            host=config.get('redis_host', 'localhost'),
            port=config.get('redis_port', 6379),
            db=config.get('redis_bars_db', 1),  # Use different DB from OCO
            ttl_hours=168,  # Keep bars for 7 days
        )

        self.historical_bars_loaded = False

    def on_start(self):
        """Modified on_start with Redis historical bar loading."""
        self.log.info("Starting DeepSeek AI Strategy...")

        # Load instrument
        self.instrument = self.cache.instrument(self.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument {self.instrument_id}")
            self.stop()
            return

        # *** LOAD HISTORICAL BARS FROM REDIS ***
        self._load_historical_bars_from_redis()

        # Subscribe to bars
        self.subscribe_bars(self.bar_type)
        self.log.info(f"Subscribed to {self.bar_type}")

        # ... rest of your on_start code ...

    def _load_historical_bars_from_redis(self):
        """Load historical bars from Redis and feed to indicators."""
        try:
            bars = self.redis_storage.load_bars(
                instrument_id=self.instrument_id,
                bar_type=self.bar_type,
                limit=200,
            )

            if bars:
                self.log.info(f"📊 Loading {len(bars)} historical bars from Redis...")

                for bar in bars:
                    self.indicator_manager.update(bar)

                self.log.info(
                    f"✅ Loaded {len(bars)} bars. "
                    f"Indicators ready: {self.indicator_manager.is_initialized()}"
                )
                self.historical_bars_loaded = True
            else:
                self.log.warning(
                    "⚠️ No historical bars found in Redis. "
                    "Waiting for live bars..."
                )

        except Exception as e:
            self.log.error(f"❌ Failed to load historical bars from Redis: {e}")
            self.log.warning("Continuing with live bars only...")

    def on_bar(self, bar: Bar):
        """Modified on_bar to save bars to Redis."""
        self.bars_received += 1

        # Update indicators
        self.indicator_manager.update(bar)

        # *** SAVE BAR TO REDIS ***
        try:
            self.redis_storage.save_bar(bar)
        except Exception as e:
            self.log.warning(f"Failed to save bar to Redis: {e}")

        # Log bar data
        if self.bars_received % 10 == 0:
            self.log.info(
                f"Bar #{self.bars_received}: "
                f"O:{bar.open} H:{bar.high} L:{bar.low} C:{bar.close} V:{bar.volume}"
            )


# ============================================================================
# APPROACH 3: Binance API Pre-fetch (SIMPLEST)
# ============================================================================

class DeepSeekStrategyWithBinancePrefetch:
    """
    Example showing Binance API pre-fetch on startup.

    Benefits:
    - Zero storage needed
    - Always fresh data
    - Simplest implementation

    Drawbacks:
    - 1-2 second API call on startup
    - Requires internet connection
    """

    def __init__(self, config):
        # ... your existing initialization ...

        # Initialize Binance fetcher
        self.binance_fetcher = BinanceBarFetcher(api_type="futures")

        self.historical_bars_loaded = False

    def on_start(self):
        """Modified on_start with Binance API pre-fetch."""
        self.log.info("Starting DeepSeek AI Strategy...")

        # Load instrument
        self.instrument = self.cache.instrument(self.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument {self.instrument_id}")
            self.stop()
            return

        # *** PRE-FETCH HISTORICAL BARS FROM BINANCE ***
        self._prefetch_bars_from_binance()

        # Subscribe to bars
        self.subscribe_bars(self.bar_type)
        self.log.info(f"Subscribed to {self.bar_type}")

        # ... rest of your on_start code ...

    def _prefetch_bars_from_binance(self):
        """Pre-fetch historical bars from Binance API."""
        try:
            # Extract symbol from instrument_id
            # Example: BTCUSDT-PERP.BINANCE -> BTCUSDT
            symbol = str(self.instrument_id).split('-')[0]

            # Convert bar type to Binance interval
            # Example: '5-MINUTE' -> '5m'
            interval = self._convert_bar_type_to_interval(str(self.bar_type))

            self.log.info(
                f"📡 Pre-fetching historical bars from Binance API "
                f"(symbol={symbol}, interval={interval})..."
            )

            # Fetch bars (200 bars should be enough for most indicators)
            klines = self.binance_fetcher.fetch_bars(
                symbol=symbol,
                interval=interval,
                limit=200,
            )

            if klines:
                self.log.info(f"📊 Received {len(klines)} bars from Binance")

                # Convert to NautilusTrader bars and feed to indicators
                for kline_data in klines:
                    # Create a Bar object
                    # Note: You'll need to properly construct Bar objects
                    # This is a simplified example
                    bar = self._convert_kline_to_bar(kline_data)
                    if bar:
                        self.indicator_manager.update(bar)

                self.log.info(
                    f"✅ Pre-fetched {len(klines)} bars. "
                    f"Indicators ready: {self.indicator_manager.is_initialized()}"
                )
                self.historical_bars_loaded = True
            else:
                self.log.warning("⚠️ No bars received from Binance API")

        except Exception as e:
            self.log.error(f"❌ Failed to pre-fetch bars from Binance: {e}")
            self.log.warning("Continuing with live bars only...")

    def _convert_bar_type_to_interval(self, bar_type_str: str) -> str:
        """Convert bar type to Binance interval string."""
        # Example: 'BTCUSDT-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL' -> '5m'
        if '1-MINUTE' in bar_type_str:
            return '1m'
        elif '5-MINUTE' in bar_type_str:
            return '5m'
        elif '15-MINUTE' in bar_type_str:
            return '15m'
        elif '1-HOUR' in bar_type_str:
            return '1h'
        elif '4-HOUR' in bar_type_str:
            return '4h'
        elif '1-DAY' in bar_type_str:
            return '1d'
        else:
            return '5m'  # Default

    def _convert_kline_to_bar(self, kline_data: dict) -> Optional[Bar]:
        """
        Convert Binance kline data to NautilusTrader Bar.

        This is a simplified example. You may need to adjust based on
        your exact Bar construction requirements.
        """
        try:
            from nautilus_trader.model.data import Bar
            from nautilus_trader.core.datetime import millis_to_nanos

            # Create Bar using NautilusTrader's Bar.from_dict or constructor
            # Note: Exact construction depends on NautilusTrader version
            # This is a placeholder - you'll need proper Bar construction

            # Example (adjust based on your version):
            bar = Bar(
                bar_type=self.bar_type,
                open=self.instrument.make_price(kline_data['open']),
                high=self.instrument.make_price(kline_data['high']),
                low=self.instrument.make_price(kline_data['low']),
                close=self.instrument.make_price(kline_data['close']),
                volume=self.instrument.make_qty(kline_data['volume']),
                ts_event=millis_to_nanos(kline_data['timestamp']),
                ts_init=millis_to_nanos(kline_data['timestamp']),
            )

            return bar

        except Exception as e:
            self.log.warning(f"Failed to convert kline to bar: {e}")
            return None

    def on_bar(self, bar: Bar):
        """Standard on_bar - no persistence needed with API pre-fetch."""
        self.bars_received += 1

        # Update indicators
        self.indicator_manager.update(bar)

        # Log bar data
        if self.bars_received % 10 == 0:
            self.log.info(
                f"Bar #{self.bars_received}: "
                f"O:{bar.open} H:{bar.high} L:{bar.low} C:{bar.close} V:{bar.volume}"
            )


# ============================================================================
# COMPARISON SUMMARY
# ============================================================================

"""
┌─────────────────────┬─────────────────┬───────────┬────────────┬─────────────────────┐
│ Approach            │ Storage         │ Startup   │ Complexity │ Best For            │
├─────────────────────┼─────────────────┼───────────┼────────────┼─────────────────────┤
│ 1. ParquetCatalog   │ Disk (Parquet)  │ Fast      │ Low        │ Production + R&D    │
│ 2. Redis            │ RAM             │ Very Fast │ Medium     │ Cross-strategy data │
│ 3. Binance Pre-fetch│ None            │ 1-2 sec   │ Very Low   │ Simple production   │
└─────────────────────┴─────────────────┴───────────┴────────────┴─────────────────────┘

RECOMMENDATION:
- For most users: Use Approach 3 (Binance Pre-fetch) - simplest and most reliable
- For research/backtest: Use Approach 1 (ParquetCatalog) - native integration
- For advanced users: Use Approach 2 (Redis) - if you need real-time sharing
"""
