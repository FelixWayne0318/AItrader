"""
Technical Indicator Manager for NautilusTrader Strategy

Manages all technical indicators using NautilusTrader's built-in indicators.
"""

from typing import Dict, Any, List
from decimal import Decimal

# Use Cython indicators (not Rust PyO3) to avoid thread safety panics
# Reference: https://github.com/Patrick-code-Bot/nautilus_AItrader
# The original repo imports directly from nautilus_trader.indicators
from nautilus_trader.indicators import (
    SimpleMovingAverage,
    ExponentialMovingAverage,
    RelativeStrengthIndex,
    MovingAverageConvergenceDivergence,
)
from nautilus_trader.model.data import Bar


class TechnicalIndicatorManager:
    """
    Manages technical indicators for strategy analysis.

    Uses NautilusTrader's built-in indicators for efficiency and consistency.
    """

    def __init__(
        self,
        sma_periods: List[int] = [5, 20, 50],
        ema_periods: List[int] = [12, 26],
        rsi_period: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        bb_period: int = 20,
        bb_std: float = 2.0,
        volume_ma_period: int = 20,
        support_resistance_lookback: int = 20,
    ):
        """
        Initialize technical indicator manager.

        Parameters
        ----------
        sma_periods : List[int]
            Periods for Simple Moving Averages
        ema_periods : List[int]
            Periods for Exponential Moving Averages
        rsi_period : int
            Period for RSI
        macd_fast : int
            Fast period for MACD
        macd_slow : int
            Slow period for MACD
        macd_signal : int
            Signal period for MACD
        bb_period : int
            Period for Bollinger Bands
        bb_std : float
            Standard deviation multiplier for Bollinger Bands
        volume_ma_period : int
            Period for volume moving average
        support_resistance_lookback : int
            Lookback period for support/resistance calculation
        """
        # SMA indicators
        self.smas = {period: SimpleMovingAverage(period) for period in sma_periods}

        # EMA indicators (for MACD calculation reference)
        self.emas = {period: ExponentialMovingAverage(period) for period in ema_periods}

        # RSI
        self.rsi = RelativeStrengthIndex(rsi_period)

        # MACD
        self.macd = MovingAverageConvergenceDivergence(
            fast_period=macd_fast,
            slow_period=macd_slow,
        )
        self.macd_signal = ExponentialMovingAverage(macd_signal)

        # For Bollinger Bands calculation
        self.bb_sma = SimpleMovingAverage(bb_period)
        self.bb_period = bb_period
        self.bb_std = bb_std

        # Volume MA
        self.volume_sma = SimpleMovingAverage(volume_ma_period)

        # Store recent bars for calculations
        self.recent_bars: List[Bar] = []
        self.max_bars = max(list(sma_periods) + [bb_period, volume_ma_period, support_resistance_lookback]) + 10

        # Configuration
        self.support_resistance_lookback = support_resistance_lookback
        self.sma_periods = sma_periods
        self.ema_periods = ema_periods
        self.rsi_period = rsi_period
        self.macd_slow_period = macd_slow
        self.macd_fast_period = macd_fast
        self.macd_signal_period = macd_signal

    def update(self, bar: Bar):
        """
        Update all indicators with new bar data.

        Parameters
        ----------
        bar : Bar
            New bar data
        """
        # Store bar for manual calculations
        self.recent_bars.append(bar)
        if len(self.recent_bars) > self.max_bars:
            self.recent_bars.pop(0)

        # Update SMA indicators
        for sma in self.smas.values():
            sma.update_raw(float(bar.close))

        # Update EMA indicators
        for ema in self.emas.values():
            ema.update_raw(float(bar.close))

        # Update RSI
        self.rsi.update_raw(float(bar.close))

        # Update MACD
        self.macd.update_raw(float(bar.close))
        self.macd_signal.update_raw(self.macd.value)

        # Update Bollinger Band SMA
        self.bb_sma.update_raw(float(bar.close))

        # Update Volume SMA
        self.volume_sma.update_raw(float(bar.volume))

    def get_technical_data(self, current_price: float) -> Dict[str, Any]:
        """
        Get all technical indicator values.

        Parameters
        ----------
        current_price : float
            Current market price

        Returns
        -------
        Dict
            Dictionary containing all technical indicator values
        """
        # Basic SMA values
        sma_values = {f'sma_{period}': self.smas[period].value for period in self.sma_periods}

        # EMA values
        ema_values = {f'ema_{period}': self.emas[period].value for period in self.ema_periods}

        # RSI (convert from 0-1 scale to 0-100 scale)
        rsi_value = self.rsi.value * 100

        # MACD
        macd_value = self.macd.value
        macd_signal_value = self.macd_signal.value  # Signal line from MACD indicator

        # Bollinger Bands
        bb_middle = self.bb_sma.value
        bb_std_dev = self._calculate_std_dev(self.bb_period)
        bb_upper = bb_middle + (self.bb_std * bb_std_dev)
        bb_lower = bb_middle - (self.bb_std * bb_std_dev)
        bb_position = (current_price - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5

        # Volume analysis
        volume_ma = self.volume_sma.value
        current_volume = float(self.recent_bars[-1].volume) if self.recent_bars else 0
        volume_ratio = current_volume / volume_ma if volume_ma > 0 else 1.0

        # Support and Resistance
        support, resistance = self._calculate_support_resistance()

        # Trend analysis
        trend_data = self._analyze_trend(
            current_price, sma_values, macd_value, macd_signal_value
        )

        # Combine all data
        technical_data = {
            # SMAs
            **sma_values,
            # EMAs
            **ema_values,
            # RSI
            "rsi": rsi_value,
            # MACD
            "macd": macd_value,
            "macd_signal": macd_signal_value,
            "macd_histogram": macd_value - macd_signal_value,
            # Bollinger Bands
            "bb_upper": bb_upper,
            "bb_middle": bb_middle,
            "bb_lower": bb_lower,
            "bb_position": bb_position,
            # Volume
            "volume_ratio": volume_ratio,
            # Support/Resistance
            "support": support,
            "resistance": resistance,
            # Trend analysis
            **trend_data,
        }

        return technical_data

    def _calculate_std_dev(self, period: int) -> float:
        """Calculate standard deviation for Bollinger Bands."""
        if len(self.recent_bars) < period:
            return 0.0

        recent_closes = [float(bar.close) for bar in self.recent_bars[-period:]]
        mean = sum(recent_closes) / len(recent_closes)
        variance = sum((x - mean) ** 2 for x in recent_closes) / len(recent_closes)
        return variance ** 0.5

    def _calculate_support_resistance(self) -> tuple:
        """Calculate support and resistance levels."""
        if len(self.recent_bars) < self.support_resistance_lookback:
            return 0.0, 0.0

        recent = self.recent_bars[-self.support_resistance_lookback:]
        support = min(float(bar.low) for bar in recent)
        resistance = max(float(bar.high) for bar in recent)

        return support, resistance

    def _analyze_trend(
        self,
        current_price: float,
        sma_values: Dict[str, float],
        macd_value: float,
        macd_signal_value: float,
    ) -> Dict[str, Any]:
        """
        Analyze market trend using multiple indicators.

        Returns
        -------
        Dict
            Trend analysis data
        """
        sma_20 = sma_values.get('sma_20', current_price)
        sma_50 = sma_values.get('sma_50', current_price)

        # Short-term trend (price vs SMA20)
        short_term_trend = "上涨" if current_price > sma_20 else "下跌"

        # Medium-term trend (price vs SMA50)
        medium_term_trend = "上涨" if current_price > sma_50 else "下跌"

        # MACD trend
        macd_trend = "bullish" if macd_value > macd_signal_value else "bearish"

        # Overall trend
        if short_term_trend == "上涨" and medium_term_trend == "上涨":
            overall_trend = "强势上涨"
        elif short_term_trend == "下跌" and medium_term_trend == "下跌":
            overall_trend = "强势下跌"
        else:
            overall_trend = "震荡整理"

        return {
            'short_term_trend': short_term_trend,
            'medium_term_trend': medium_term_trend,
            'macd_trend': macd_trend,
            'overall_trend': overall_trend,
        }

    def is_initialized(self) -> bool:
        """Check if indicators have enough data to be valid."""
        # Check if we have minimum bars for key indicators
        # Use dynamic calculation based on actual indicator periods
        min_required_bars = max(
            self.rsi_period,  # RSI period (e.g., 7 or 14)
            self.macd_slow_period,  # MACD slow period (e.g., 10 or 26)
            self.bb_period,  # Bollinger Bands period (e.g., 10 or 20)
            min(self.sma_periods) if self.sma_periods else 0  # At least shortest SMA
        )
        
        if len(self.recent_bars) < min_required_bars:
            return False

        # Check if key indicators are initialized
        if not self.rsi.initialized:
            return False

        if not self.macd.initialized:
            return False

        # Check if we have at least one SMA initialized (for trend analysis)
        if not any(sma.initialized for sma in self.smas.values()):
            return False

        return True

    def get_kline_data(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent K-line data for analysis.

        Parameters
        ----------
        count : int
            Number of recent bars to return

        Returns
        -------
        List[Dict]
            List of K-line data dictionaries
        """
        if not self.recent_bars:
            return []

        kline_data = []
        for bar in self.recent_bars[-count:]:
            kline_data.append({
                'timestamp': bar.ts_init,
                'open': float(bar.open),
                'high': float(bar.high),
                'low': float(bar.low),
                'close': float(bar.close),
                'volume': float(bar.volume),
            })

        return kline_data

    def get_historical_context(self, count: int = 20) -> Dict[str, Any]:
        """
        Get AI-friendly historical data context for enhanced decision making.

        This method provides trending data (last N values) for each indicator,
        allowing AI to see the trajectory of indicators rather than isolated snapshots.

        Implementation Plan Section 4.2.1:
        - price_trend: Last 20 closing prices
        - volume_trend: Last 20 volumes
        - rsi_trend: Last 20 RSI values
        - macd_trend: Last 20 MACD values
        - trend_direction: BULLISH/BEARISH/NEUTRAL
        - momentum_shift: INCREASING/DECREASING/STABLE

        Parameters
        ----------
        count : int
            Number of historical values to return (default 20)

        Returns
        -------
        Dict[str, Any]
            Historical context data for AI analysis
        """
        if len(self.recent_bars) < count:
            # Not enough data yet
            return {
                "price_trend": [],
                "volume_trend": [],
                "rsi_trend": [],
                "macd_trend": [],
                "trend_direction": "INSUFFICIENT_DATA",
                "momentum_shift": "INSUFFICIENT_DATA",
                "data_points": len(self.recent_bars),
                "required_points": count,
            }

        recent = self.recent_bars[-count:]

        # Extract price trend (closing prices)
        price_trend = [float(bar.close) for bar in recent]

        # Extract volume trend
        volume_trend = [float(bar.volume) for bar in recent]

        # Calculate RSI trend from stored bars
        # Note: We recalculate RSI for each bar to get the trend
        rsi_trend = self._calculate_indicator_history('rsi', count)

        # Calculate MACD trend
        macd_trend = self._calculate_indicator_history('macd', count)

        # Determine trend direction
        trend_direction = self._determine_trend_direction(price_trend)

        # Determine momentum shift
        momentum_shift = self._determine_momentum_shift(rsi_trend, macd_trend)

        # Additional context metrics
        price_change_pct = ((price_trend[-1] - price_trend[0]) / price_trend[0] * 100) if price_trend[0] > 0 else 0
        avg_volume = sum(volume_trend) / len(volume_trend) if volume_trend else 0
        current_volume_ratio = volume_trend[-1] / avg_volume if avg_volume > 0 else 1.0

        return {
            # Core trend data
            "price_trend": price_trend,
            "volume_trend": volume_trend,
            "rsi_trend": rsi_trend,
            "macd_trend": macd_trend,
            # Trend analysis
            "trend_direction": trend_direction,
            "momentum_shift": momentum_shift,
            # Summary metrics
            "price_change_pct": round(price_change_pct, 2),
            "current_volume_ratio": round(current_volume_ratio, 2),
            "data_points": count,
            # Visual indicators for AI
            "price_arrow": "↑" if price_change_pct > 1 else ("↓" if price_change_pct < -1 else "→"),
            "rsi_current": rsi_trend[-1] if rsi_trend else 0,
            "macd_current": macd_trend[-1] if macd_trend else 0,
        }

    def _calculate_indicator_history(self, indicator_name: str, count: int) -> List[float]:
        """
        Calculate historical values for an indicator.

        Note: This is an approximation since we only store recent bars.
        For accurate historical RSI/MACD, we would need to recalculate from scratch.
        Here we use a simplified approach based on recent closes.
        """
        if len(self.recent_bars) < count:
            return []

        recent = self.recent_bars[-count:]
        closes = [float(bar.close) for bar in recent]

        if indicator_name == 'rsi':
            # Simplified RSI calculation for history
            # For true historical RSI, we'd need to recalculate with full lookback
            rsi_values = []
            period = min(self.rsi_period, len(closes) - 1)

            for i in range(period, len(closes)):
                window = closes[i - period:i + 1]
                changes = [window[j + 1] - window[j] for j in range(len(window) - 1)]
                gains = [c for c in changes if c > 0]
                losses = [-c for c in changes if c < 0]

                avg_gain = sum(gains) / period if gains else 0
                avg_loss = sum(losses) / period if losses else 0.0001

                rs = avg_gain / avg_loss if avg_loss > 0 else 100
                rsi = 100 - (100 / (1 + rs))
                rsi_values.append(round(rsi, 2))

            return rsi_values

        elif indicator_name == 'macd':
            # Simplified MACD calculation for history
            macd_values = []
            fast_period = self.macd_fast_period
            slow_period = self.macd_slow_period

            if len(closes) < slow_period:
                return []

            for i in range(slow_period, len(closes) + 1):
                window = closes[:i]
                fast_ema = self._simple_ema(window, fast_period)
                slow_ema = self._simple_ema(window, slow_period)
                macd = fast_ema - slow_ema
                macd_values.append(round(macd, 4))

            return macd_values

        return []

    def _simple_ema(self, values: List[float], period: int) -> float:
        """Calculate a simple EMA for historical data."""
        if len(values) < period:
            return values[-1] if values else 0

        multiplier = 2 / (period + 1)
        ema = sum(values[:period]) / period  # Start with SMA

        for value in values[period:]:
            ema = (value - ema) * multiplier + ema

        return ema

    def _determine_trend_direction(self, price_trend: List[float]) -> str:
        """
        Determine overall trend direction from price trend.

        Uses linear regression slope approach.
        """
        if len(price_trend) < 5:
            return "INSUFFICIENT_DATA"

        # Simple linear regression slope
        n = len(price_trend)
        x_mean = (n - 1) / 2
        y_mean = sum(price_trend) / n

        numerator = sum((i - x_mean) * (price_trend[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return "NEUTRAL"

        slope = numerator / denominator
        slope_pct = (slope / y_mean * 100) if y_mean > 0 else 0

        # Classify based on slope percentage
        if slope_pct > 0.5:  # >0.5% slope per bar
            return "BULLISH"
        elif slope_pct < -0.5:
            return "BEARISH"
        else:
            return "NEUTRAL"

    def _determine_momentum_shift(
        self,
        rsi_trend: List[float],
        macd_trend: List[float]
    ) -> str:
        """
        Determine if momentum is increasing, decreasing, or stable.

        Analyzes the trajectory of RSI and MACD.
        """
        if len(rsi_trend) < 5 or len(macd_trend) < 5:
            return "INSUFFICIENT_DATA"

        # Check RSI momentum (last 5 values)
        rsi_recent = rsi_trend[-5:]
        rsi_slope = (rsi_recent[-1] - rsi_recent[0]) / 5

        # Check MACD momentum (last 5 values)
        macd_recent = macd_trend[-5:]
        macd_slope = (macd_recent[-1] - macd_recent[0]) / 5

        # Normalize slopes for comparison
        rsi_momentum = "up" if rsi_slope > 2 else ("down" if rsi_slope < -2 else "stable")
        macd_momentum = "up" if macd_slope > 0 else ("down" if macd_slope < 0 else "stable")

        # Combine signals
        if rsi_momentum == "up" and macd_momentum == "up":
            return "INCREASING"
        elif rsi_momentum == "down" and macd_momentum == "down":
            return "DECREASING"
        else:
            return "STABLE"
