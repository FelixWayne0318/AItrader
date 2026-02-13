#!/usr/bin/env python3
"""
Test S/R Zone Calculator with Market Data

Attempts to fetch real BTCUSDT bars from Binance Futures API. If the API is
unreachable (e.g., proxy restrictions), falls back to realistic synthetic data
that mirrors actual BTC price action around ~$96,000-$98,000.

The synthetic data includes:
- Realistic 15m OHLCV bars (100 bars = 25 hours) with swing highs/lows
- Realistic 4H bars (50 bars = 200 hours) with structural levels
- Realistic 1D bars (30 bars = 30 days) with major S/R levels
- Volume patterns (higher at swings, variable throughout)

Usage:
    python3 scripts/test_sr_live.py
"""

import sys
import os
import json
import logging
import math
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.config_manager import ConfigManager
from utils.sr_zone_calculator import SRZoneCalculator, SRZone

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_sr_live")


# ─────────────────────────────────────────────────────────────────────────────
# Binance Data Fetching (with fallback)
# ─────────────────────────────────────────────────────────────────────────────
BINANCE_FUTURES_BASE = "https://fapi.binance.com"


def fetch_klines(symbol: str, interval: str, limit: int) -> list:
    """
    Fetch klines from Binance Futures API and return as list of dicts.
    Returns None if the API is unreachable.
    """
    try:
        import requests
        url = f"{BINANCE_FUTURES_BASE}/fapi/v1/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}

        logger.info(f"Fetching {limit} {interval} bars for {symbol} from Binance ...")
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        raw = resp.json()

        bars = []
        for k in raw:
            bars.append({
                "open_time": int(k[0]),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": int(k[6]),
                "quote_volume": float(k[7]),
                "trades_count": int(k[8]),
                "taker_buy_volume": float(k[9]),
                "taker_buy_quote_volume": float(k[10]),
            })

        logger.info(
            f"  Got {len(bars)} bars | "
            f"First: {datetime.fromtimestamp(bars[0]['open_time']/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC | "
            f"Last:  {datetime.fromtimestamp(bars[-1]['open_time']/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"
        )
        return bars
    except Exception as e:
        logger.warning(f"  Binance API unreachable ({type(e).__name__}): {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Realistic Synthetic Data Generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_realistic_bars(
    interval: str,
    count: int,
    base_price: float = 96500.0,
    seed: int = 42,
) -> list:
    """
    Generate realistic BTCUSDT OHLCV bars with proper price action.

    The synthetic data models:
    - A base price around $96,500 with BTC-realistic volatility
    - Swing highs around $97,800-$98,200 and swing lows around $95,200-$95,800
    - Volume spikes at reversal points
    - Proper OHLC relationships (high >= open/close, low <= open/close)
    - Trend segments: down -> consolidation -> up -> resistance rejection

    Parameters
    ----------
    interval : str
        Timeframe: "15m", "4h", "1d"
    count : int
        Number of bars to generate.
    base_price : float
        Starting price.
    seed : int
        Random seed for reproducibility.
    """
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)

    # Interval-specific parameters
    if interval == "15m":
        delta = timedelta(minutes=15)
        volatility = 0.0015    # 0.15% per bar
        wick_factor = 0.001    # Wick size factor
        base_volume = 150.0    # BTC per bar
    elif interval == "4h":
        delta = timedelta(hours=4)
        volatility = 0.006     # 0.6% per bar
        wick_factor = 0.003
        base_volume = 2500.0
    elif interval == "1d":
        delta = timedelta(days=1)
        volatility = 0.015     # 1.5% per bar
        wick_factor = 0.008
        base_volume = 15000.0
    else:
        delta = timedelta(minutes=15)
        volatility = 0.0015
        wick_factor = 0.001
        base_volume = 150.0

    start_time = now - delta * count

    # Create a price path with realistic structure:
    # Phase 1 (0-25%):  Decline from ~97000 to ~95500
    # Phase 2 (25-45%): Consolidation around ~95500-96000
    # Phase 3 (45-75%): Rally from ~95500 to ~97800
    # Phase 4 (75-90%): Rejection and pullback to ~96500
    # Phase 5 (90-100%): Stabilization around ~96500-97000

    # Generate a smooth price path using sine wave + noise
    prices = []
    for i in range(count + 1):
        t = i / count  # 0 to 1

        # Multi-component price model
        # Component 1: Large cycle (decline then recovery)
        cycle1 = -1200.0 * math.sin(math.pi * t * 0.8)  # Dip and recover

        # Component 2: Medium oscillation
        cycle2 = 400.0 * math.sin(math.pi * t * 3.2 + 0.5)

        # Component 3: Small oscillation
        cycle3 = 150.0 * math.sin(math.pi * t * 7.5 + 1.2)

        # Component 4: Random noise
        noise = rng.gauss(0, base_price * volatility * 0.3)

        price = base_price + cycle1 + cycle2 + cycle3 + noise
        prices.append(max(price, base_price * 0.9))  # Floor at 90% of base

    bars = []
    for i in range(count):
        bar_time = start_time + delta * i
        open_time_ms = int(bar_time.timestamp() * 1000)
        close_time_ms = int((bar_time + delta).timestamp() * 1000) - 1

        open_price = prices[i]
        close_price = prices[i + 1]

        # Wicks: extend high above max(open, close) and low below min(open, close)
        bar_range = abs(close_price - open_price)
        upper_wick = abs(rng.gauss(0, base_price * wick_factor)) + bar_range * 0.1
        lower_wick = abs(rng.gauss(0, base_price * wick_factor)) + bar_range * 0.1

        high_price = max(open_price, close_price) + upper_wick
        low_price = min(open_price, close_price) - lower_wick

        # Volume: higher at extremes and during large moves
        price_change_pct = abs(close_price - open_price) / open_price
        # Volume spikes at swing points (low and high price extremes)
        distance_from_mean = abs(close_price - base_price) / base_price
        volume_multiplier = 1.0 + price_change_pct * 20 + distance_from_mean * 3
        volume = base_volume * volume_multiplier * (0.7 + rng.random() * 0.6)
        quote_volume = volume * close_price
        taker_buy_pct = 0.45 + rng.random() * 0.10  # 45-55% taker buy
        trades = int(volume * (50 + rng.random() * 30))

        bars.append({
            "open_time": open_time_ms,
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": round(volume, 3),
            "close_time": close_time_ms,
            "quote_volume": round(quote_volume, 2),
            "trades_count": trades,
            "taker_buy_volume": round(volume * taker_buy_pct, 3),
            "taker_buy_quote_volume": round(quote_volume * taker_buy_pct, 2),
        })

    # Report
    all_highs = [b["high"] for b in bars]
    all_lows = [b["low"] for b in bars]
    logger.info(
        f"  Generated {len(bars)} {interval} bars | "
        f"Range: ${min(all_lows):,.0f} - ${max(all_highs):,.0f} | "
        f"Last close: ${bars[-1]['close']:,.2f}"
    )
    return bars


# ─────────────────────────────────────────────────────────────────────────────
# BB/SMA computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_bb_sma_from_bars(bars: list, bb_period: int = 20, bb_std: float = 2.0):
    """
    Compute Bollinger Bands and SMAs from bar close prices.
    Returns (bb_data, sma_data).
    """
    closes = [b["close"] for b in bars]

    # BB from last bb_period closes
    if len(closes) >= bb_period:
        window = closes[-bb_period:]
        bb_middle = sum(window) / len(window)
        variance = sum((x - bb_middle) ** 2 for x in window) / len(window)
        std_dev = variance ** 0.5
        bb_upper = bb_middle + bb_std * std_dev
        bb_lower = bb_middle - bb_std * std_dev
    else:
        bb_middle = closes[-1]
        bb_upper = bb_middle
        bb_lower = bb_middle

    bb_data = {
        "upper": round(bb_upper, 2),
        "lower": round(bb_lower, 2),
        "middle": round(bb_middle, 2),
    }

    # SMAs
    sma_data = {}
    if len(closes) >= 50:
        sma_data["sma_50"] = round(sum(closes[-50:]) / 50, 2)
    if len(closes) >= 200:
        sma_data["sma_200"] = round(sum(closes[-200:]) / 200, 2)
    elif len(closes) >= 30:
        # Use all available as approximate long-term SMA
        sma_data["sma_200"] = round(sum(closes) / len(closes), 2)

    return bb_data, sma_data


# ─────────────────────────────────────────────────────────────────────────────
# Pretty Printing
# ─────────────────────────────────────────────────────────────────────────────
def print_zone(zone: SRZone, label: str, index: int):
    """Pretty-print a single SRZone."""
    swing_tag = " [SwingPt]" if zone.has_swing_point else ""
    touch_tag = f" [Touches:{zone.touch_count}]" if zone.touch_count > 0 else ""
    wall_tag = f" [Wall:{zone.wall_size_btc:.1f}BTC]" if zone.has_order_wall else ""
    proj_tag = ""
    if zone.source_type == "PROJECTED":
        proj_tag = " PROJECTED"
    elif zone.source_type in ("STRUCTURAL", "ORDER_FLOW"):
        proj_tag = " CONFIRMED"

    print(
        f"  {label}{index:2d}  ${zone.price_center:>10,.2f}  "
        f"({zone.distance_pct:+5.2f}% away)  "
        f"[{zone.strength:6s}]  "
        f"wt={zone.total_weight:<5.2f}  "
        f"level={zone.level:<13s}  "
        f"type={zone.source_type:<14s}{proj_tag}{swing_tag}{touch_tag}{wall_tag}"
    )
    print(f"           Zone: ${zone.price_low:,.2f} - ${zone.price_high:,.2f}")
    print(f"           Sources: {', '.join(zone.sources[:8])}")
    if len(zone.sources) > 8:
        print(f"                    ... and {len(zone.sources) - 8} more")
    print()


def print_separator(title: str, char: str = "=", width: int = 90):
    print()
    print(f" {title} ".center(width, char))
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print_separator("S/R ZONE LIVE TEST", "=", 90)
    print(f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print()

    # ── 1. Load config ──────────────────────────────────────────────────────
    logger.info("Loading config from configs/base.yaml via ConfigManager ...")
    config = ConfigManager(env="production")
    cfg = config.load()

    sr_cfg = cfg.get("sr_zones", {})
    swing_cfg = sr_cfg.get("swing_detection", {})
    cluster_cfg = sr_cfg.get("clustering", {})
    scoring_cfg = sr_cfg.get("scoring", {})
    hc_cfg = sr_cfg.get("hard_control", {})
    agg_cfg = sr_cfg.get("aggregation", {})
    rn_cfg = sr_cfg.get("round_number", {})

    logger.info("Config loaded successfully.")
    print()

    # ── 2. Fetch live bars (or generate synthetic) ──────────────────────────
    data_source = "LIVE (Binance API)"
    bars_15m = fetch_klines("BTCUSDT", "15m", 100)
    if bars_15m is None:
        data_source = "SYNTHETIC (Binance API unreachable - using realistic generated data)"
        logger.info("Falling back to synthetic data generation ...")
        print()
        bars_15m = generate_realistic_bars("15m", 100, base_price=96500.0, seed=42)
        bars_4h = generate_realistic_bars("4h", 50, base_price=96500.0, seed=43)
        bars_1d = generate_realistic_bars("1d", 30, base_price=96500.0, seed=44)
    else:
        bars_4h = fetch_klines("BTCUSDT", "4h", 50)
        bars_1d = fetch_klines("BTCUSDT", "1d", 30)
        if bars_4h is None:
            bars_4h = generate_realistic_bars("4h", 50, base_price=bars_15m[-1]["close"], seed=43)
        if bars_1d is None:
            bars_1d = generate_realistic_bars("1d", 30, base_price=bars_15m[-1]["close"], seed=44)

    print(f"  Data Source: {data_source}")
    current_price = bars_15m[-1]["close"]
    print(f"  Current BTCUSDT Price: ${current_price:,.2f}")

    # Show price range for each timeframe
    for label, bars in [("15m", bars_15m), ("4h", bars_4h), ("1d", bars_1d)]:
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        print(f"  {label:>3s} range: ${min(lows):>10,.2f} - ${max(highs):>10,.2f}  ({len(bars)} bars)")
    print()

    # ── 3. Compute BB & SMA from 15m bars ───────────────────────────────────
    ind_cfg = cfg.get("indicators", {})
    bb_period = ind_cfg.get("bb_period", 20)
    bb_std = ind_cfg.get("bb_std", 2.0)

    bb_data, sma_data = compute_bb_sma_from_bars(bars_15m, bb_period, bb_std)
    print(f"  Bollinger Bands (15m, {bb_period}-period, {bb_std}x std):")
    print(f"    Upper:  ${bb_data['upper']:,.2f}")
    print(f"    Middle: ${bb_data['middle']:,.2f}")
    print(f"    Lower:  ${bb_data['lower']:,.2f}")
    print()
    print(f"  SMA Data:")
    for k, v in sma_data.items():
        print(f"    {k}: ${v:,.2f}")
    print()

    # ── 4. Calculate ATR from 15m bars ──────────────────────────────────────
    atr_value = SRZoneCalculator._calculate_atr_from_bars(bars_15m, period=14)
    print(f"  ATR (14-period from 15m bars): ${atr_value:,.2f}")
    print(f"  ATR as % of price: {atr_value / current_price * 100:.3f}%")
    print()

    # ── 5. Prepare daily/weekly bars for Pivot Points ───────────────────────
    daily_bar = None
    weekly_bar = None
    if len(bars_1d) >= 2:
        d = bars_1d[-2]  # Most recent *completed* daily bar
        daily_bar = {
            "high": d["high"],
            "low": d["low"],
            "close": d["close"],
            "open": d["open"],
            "volume": d["volume"],
        }
        print(f"  Daily Pivot bar (completed): H=${d['high']:,.2f} L=${d['low']:,.2f} C=${d['close']:,.2f}")

    # For weekly, approximate from last 7 daily bars
    if len(bars_1d) >= 7:
        week_bars = bars_1d[-8:-1]  # Last 7 completed daily bars
        weekly_bar = {
            "high": max(b["high"] for b in week_bars),
            "low": min(b["low"] for b in week_bars),
            "close": week_bars[-1]["close"],
            "open": week_bars[0]["open"],
            "volume": sum(b["volume"] for b in week_bars),
        }
        print(f"  Weekly Pivot bar (approx 7d): H=${weekly_bar['high']:,.2f} L=${weekly_bar['low']:,.2f} C=${weekly_bar['close']:,.2f}")

    print()

    # ── 6. Create SRZoneCalculator with config ──────────────────────────────
    calculator = SRZoneCalculator(
        cluster_pct=cluster_cfg.get("cluster_pct", 0.5),
        zone_expand_pct=sr_cfg.get("zone_expand_pct", 0.1),
        hard_control_threshold_pct=hc_cfg.get("threshold_pct", 1.0),
        hard_control_threshold_mode=hc_cfg.get("threshold_mode", "fixed"),
        hard_control_atr_multiplier=hc_cfg.get("atr_multiplier", 0.5),
        hard_control_atr_min_pct=hc_cfg.get("atr_min_pct", 0.3),
        hard_control_atr_max_pct=hc_cfg.get("atr_max_pct", 2.0),
        swing_detection_enabled=swing_cfg.get("enabled", True),
        swing_left_bars=swing_cfg.get("left_bars", 5),
        swing_right_bars=swing_cfg.get("right_bars", 5),
        swing_weight=swing_cfg.get("weight", 1.2),
        swing_max_age=swing_cfg.get("max_swing_age", 100),
        use_atr_adaptive=cluster_cfg.get("use_atr_adaptive", True),
        atr_cluster_multiplier=cluster_cfg.get("atr_cluster_multiplier", 0.5),
        touch_count_enabled=scoring_cfg.get("touch_count_enabled", True),
        touch_threshold_atr=scoring_cfg.get("touch_threshold_atr", 0.3),
        optimal_touches=tuple(scoring_cfg.get("optimal_touches", [2, 3])),
        decay_after_touches=scoring_cfg.get("decay_after_touches", 4),
        same_data_weight_cap=agg_cfg.get("same_data_weight_cap", 2.5),
        max_zone_weight=agg_cfg.get("max_zone_weight", 6.0),
        confluence_bonus_2=agg_cfg.get("confluence_bonus_2", 0.2),
        confluence_bonus_3=agg_cfg.get("confluence_bonus_3", 0.5),
        round_number_btc_step=rn_cfg.get("btc_step", 5000),
        round_number_count=rn_cfg.get("count", 3),
        logger=logger,
    )

    logger.info("SRZoneCalculator created with production config.")

    # ── 7. Run calculate_with_detailed_report() ─────────────────────────────
    logger.info("Running calculate_with_detailed_report() ...")

    result = calculator.calculate_with_detailed_report(
        current_price=current_price,
        bb_data=bb_data,
        sma_data=sma_data,
        orderbook_anomalies=None,  # No order book data in this test
        bars_data=bars_15m,
        atr_value=atr_value,
        bars_data_4h=bars_4h,
        bars_data_1d=bars_1d,
        daily_bar=daily_bar,
        weekly_bar=weekly_bar,
    )

    # ── 8. Display Results ──────────────────────────────────────────────────
    support_zones = result["support_zones"]
    resistance_zones = result["resistance_zones"]
    nearest_support = result["nearest_support"]
    nearest_resistance = result["nearest_resistance"]
    hard_control = result["hard_control"]

    print_separator("RESISTANCE ZONES", "-", 90)
    if resistance_zones:
        for i, zone in enumerate(resistance_zones, 1):
            marker = ">>>" if zone == nearest_resistance else "   "
            print_zone(zone, f"{marker} R", i)
    else:
        print("  (none detected)")

    print_separator("SUPPORT ZONES", "-", 90)
    if support_zones:
        for i, zone in enumerate(support_zones, 1):
            marker = ">>>" if zone == nearest_support else "   "
            print_zone(zone, f"{marker} S", i)
    else:
        print("  (none detected)")

    print_separator("NEAREST S/R", "-", 90)
    if nearest_resistance:
        print(f"  Nearest Resistance: ${nearest_resistance.price_center:,.2f}  "
              f"({nearest_resistance.distance_pct:.2f}% away)  [{nearest_resistance.strength}]")
        print(f"    Sources: {', '.join(nearest_resistance.sources[:5])}")
    else:
        print("  Nearest Resistance: NONE")

    if nearest_support:
        print(f"  Nearest Support:    ${nearest_support.price_center:,.2f}  "
              f"({nearest_support.distance_pct:.2f}% away)  [{nearest_support.strength}]")
        print(f"    Sources: {', '.join(nearest_support.sources[:5])}")
    else:
        print("  Nearest Support: NONE")

    print_separator("HARD CONTROL DECISION", "-", 90)
    print(f"  Block LONG:  {hard_control['block_long']}")
    print(f"  Block SHORT: {hard_control['block_short']}")
    print(f"  Reason:      {hard_control['reason'] or '(no blocks)'}")

    print_separator("SUMMARY STATISTICS", "-", 90)
    print(f"  Total Resistance Zones: {len(resistance_zones)}")
    print(f"  Total Support Zones:    {len(support_zones)}")

    swing_r = sum(1 for z in resistance_zones if z.has_swing_point)
    swing_s = sum(1 for z in support_zones if z.has_swing_point)
    print(f"  Zones with Swing Points: {swing_r} resistance, {swing_s} support")

    touched_r = sum(1 for z in resistance_zones if z.touch_count > 0)
    touched_s = sum(1 for z in support_zones if z.touch_count > 0)
    print(f"  Zones with Touches:      {touched_r} resistance, {touched_s} support")

    high_r = sum(1 for z in resistance_zones if z.strength == "HIGH")
    high_s = sum(1 for z in support_zones if z.strength == "HIGH")
    med_r = sum(1 for z in resistance_zones if z.strength == "MEDIUM")
    med_s = sum(1 for z in support_zones if z.strength == "MEDIUM")
    low_r = sum(1 for z in resistance_zones if z.strength == "LOW")
    low_s = sum(1 for z in support_zones if z.strength == "LOW")
    print(f"  Strength distribution (R): HIGH={high_r}, MEDIUM={med_r}, LOW={low_r}")
    print(f"  Strength distribution (S): HIGH={high_s}, MEDIUM={med_s}, LOW={low_s}")

    # Source type breakdown
    r_types = Counter(z.source_type for z in resistance_zones)
    s_types = Counter(z.source_type for z in support_zones)
    print(f"  Source types (R): {dict(r_types)}")
    print(f"  Source types (S): {dict(s_types)}")

    # R/R analysis
    if nearest_support and nearest_resistance:
        upside = nearest_resistance.price_center - current_price
        downside = current_price - nearest_support.price_center
        if downside > 0:
            rr_long = upside / downside
            print(f"\n  LONG  R/R: {rr_long:.2f}:1  "
                  f"(upside ${upside:,.0f} / downside ${downside:,.0f})")
        if upside > 0:
            rr_short = downside / upside
            print(f"  SHORT R/R: {rr_short:.2f}:1  "
                  f"(downside ${downside:,.0f} / upside ${upside:,.0f})")

    print_separator("AI DETAILED REPORT", "=", 90)
    print(result.get("ai_detailed_report", "(not generated)"))

    print_separator("AI REPORT (short)", "-", 90)
    print(result.get("ai_report", "(not generated)"))

    print()
    print_separator("RAW DATA COUNTS", "-", 90)
    raw = result.get("raw_data", {})
    print(f"  bars_count (15m): {raw.get('bars_count', 'N/A')}")
    print(f"  bars_count (4h):  {raw.get('bars_count_4h', 'N/A')}")
    print(f"  bars_count (1d):  {raw.get('bars_count_1d', 'N/A')}")
    print(f"  ATR value:        ${raw.get('atr_value', 0):,.2f}")
    print()

    logger.info("Test completed successfully.")


if __name__ == "__main__":
    main()
