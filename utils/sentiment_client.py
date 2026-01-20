"""
Sentiment Data Fetcher for NautilusTrader

Fetches market sentiment indicators from Binance Long/Short Ratio API.
(Replaced CryptoOracle with Binance due to invalid API key)
"""

import requests
from typing import Dict, Any, Optional
from datetime import datetime


class SentimentDataFetcher:
    """
    Fetches BTC market sentiment data from Binance Futures API.

    Uses the global long/short account ratio as sentiment indicator.
    """

    # Binance Futures API (free, no API key required)
    BINANCE_URL = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"

    def __init__(self, lookback_hours: int = 4, timeframe: str = "15m"):
        """
        Initialize sentiment data fetcher.

        Parameters
        ----------
        lookback_hours : int
            Not used for Binance API (kept for compatibility)
        timeframe : str
            Time interval for data: "5m", "15m", "30m", "1h", "4h", "1d"
        """
        self.lookback_hours = lookback_hours
        # Map timeframe to Binance period format
        self.timeframe = self._map_timeframe(timeframe)

    def _map_timeframe(self, timeframe: str) -> str:
        """Map common timeframe formats to Binance period format."""
        mapping = {
            "1m": "5m",    # Binance minimum is 5m
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "4h": "4h",
            "1d": "1d",
        }
        return mapping.get(timeframe, "15m")

    def fetch(self, token: str = "BTC") -> Optional[Dict[str, Any]]:
        """
        Fetch sentiment data for specified token.

        Parameters
        ----------
        token : str
            Token symbol (default: "BTC")

        Returns
        -------
        Dict or None
            Sentiment data with structure:
            {
                'positive_ratio': float,  # Long ratio (bullish)
                'negative_ratio': float,  # Short ratio (bearish)
                'net_sentiment': float,   # Long - Short
                'data_time': str,
                'data_delay_minutes': int
            }
        """
        try:
            # Build request
            params = {
                "symbol": f"{token}USDT",
                "period": self.timeframe,
                "limit": 1
            }

            # Make request
            response = requests.get(
                self.BINANCE_URL,
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return self._parse_binance_data(data[0])

            print(f"⚠️ Binance API returned unexpected response: {response.status_code}")
            return None

        except Exception as e:
            print(f"❌ Sentiment data fetch failed: {e}")
            return None

    def _parse_binance_data(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse sentiment data from Binance API response."""
        try:
            # Extract long/short ratios
            long_ratio = float(data["longAccount"])
            short_ratio = float(data["shortAccount"])
            net_sentiment = long_ratio - short_ratio

            # Parse timestamp
            timestamp_ms = data["timestamp"]
            data_time = datetime.fromtimestamp(timestamp_ms / 1000)

            # Calculate delay
            data_delay = int((datetime.now() - data_time).total_seconds() // 60)

            print(f"✅ Using Binance sentiment data from: {data_time.strftime('%Y-%m-%d %H:%M:%S')} (delay: {data_delay} minutes)")

            return {
                'positive_ratio': long_ratio,
                'negative_ratio': short_ratio,
                'net_sentiment': net_sentiment,
                'data_time': data_time.strftime('%Y-%m-%d %H:%M:%S'),
                'data_delay_minutes': data_delay,
                'source': 'binance',
                'long_short_ratio': float(data["longShortRatio"])
            }

        except Exception as e:
            print(f"❌ Sentiment data parsing failed: {e}")
            return None

    def format_for_display(self, sentiment_data: Optional[Dict[str, Any]]) -> str:
        """
        Format sentiment data for logging/display.

        Parameters
        ----------
        sentiment_data : Dict or None
            Sentiment data from fetch()

        Returns
        -------
        str
            Formatted sentiment string
        """
        if not sentiment_data:
            return "Market Sentiment: Data unavailable"

        sign = '+' if sentiment_data['net_sentiment'] >= 0 else ''
        return (
            f"Market Sentiment (Binance): "
            f"Long {sentiment_data['positive_ratio']:.1%} | "
            f"Short {sentiment_data['negative_ratio']:.1%} | "
            f"Net {sign}{sentiment_data['net_sentiment']:.3f} | "
            f"Ratio {sentiment_data.get('long_short_ratio', 0):.2f}"
        )
