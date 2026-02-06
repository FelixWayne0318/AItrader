"""
Multi-Agent Trading Analyzer

Borrowed from TradingAgents (UCLA+MIT) and adapted for cryptocurrency trading.
Original: https://github.com/TaurusQ/tradingagents

This module implements a multi-agent debate system where Bull and Bear analysts
argue for their positions, followed by a Judge who makes the final decision,
and a Risk Evaluator who determines position sizing.

Key Features:
- Bull/Bear Debate: Two opposing views debate the market direction
- Research Manager (Judge): Evaluates debate and makes definitive decision
- Risk Evaluator: Assesses risk and determines position sizing
- Memory System: Learns from past decisions to avoid repeating mistakes
"""

import json
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

from openai import OpenAI

# S/R Zone Calculator (v3.8: Multi-source support/resistance detection)
from utils.sr_zone_calculator import SRZoneCalculator

# Import shared constants for consistency (Phase 3: migrated to functions)
from strategy.trading_logic import (
    get_min_sl_distance_pct,
    get_default_sl_pct,
    get_default_tp_pct_buy,
    get_default_tp_pct_sell,
)


# =============================================================================
# TradingAgents v3.15: Market Order Reality Check
#
# v3.15 Changes:
# - Updated Bull/Bear/Risk prompts to reflect market order entry behavior
# - AI now explicitly told: entry at CURRENT PRICE, not at S/R levels
# - LONG only recommended if price ALREADY near support (within 1-2%)
# - SHORT only recommended if price ALREADY near resistance (within 1-2%)
# - If price is in middle of S/R range, recommend HOLD (wait for better entry)
#
# v3.12: Indicator Definitions for AI
# Borrowed from: TradingAgents/agents/analysts/market_analyst.py
#
# Philosophy: "Teach AI WHAT indicators mean, not HOW to use them"
# - Provide calculation methods and mathematical definitions
# - Explain what values represent, not trading rules
# - Let AI form its own interpretation based on raw data
# - Aligned with TradingAgents "授人以渔" (teach fishing, not give fish) principle
# =============================================================================
INDICATOR_DEFINITIONS = """
TECHNICAL INDICATOR REFERENCE (Calculation and Meaning):

MOVING AVERAGES (SMA):
- Simple Moving Average of closing prices over N periods
- Calculation: Sum of last N closing prices / N
- Common periods: 5 (short-term), 20 (medium-term), 50/200 (long-term)
- Interpretation: Higher values = higher average price over that period
- Multiple SMAs show different timeframe averages simultaneously

RSI (Relative Strength Index):
- Momentum oscillator measuring magnitude and velocity of price changes
- Calculation: 100 - (100 / (1 + RS)), where RS = Avg Gain / Avg Loss (14 periods)
- Range: 0-100
  * 0 = Maximum downward momentum (all periods were losses)
  * 100 = Maximum upward momentum (all periods were gains)
  * 50 = Equal gains and losses (neutral momentum)
- Time sensitivity: Standard period is 14 bars, longer periods = smoother values

MACD (Moving Average Convergence Divergence):
- Trend-following momentum indicator comparing two exponential moving averages
- Components:
  * MACD Line: EMA(12) - EMA(26)
  * Signal Line: EMA(9) of MACD Line
  * Histogram: MACD Line - Signal Line
- Interpretation:
  * Positive MACD = short-term average above long-term average
  * Negative MACD = short-term average below long-term average
  * Histogram magnitude = strength of divergence/convergence
  * Histogram direction = rate of change in divergence

BOLLINGER BANDS:
- Volatility indicator based on standard deviation from moving average
- Components:
  * Middle Band: SMA(20)
  * Upper Band: SMA(20) + (2 × Standard Deviation)
  * Lower Band: SMA(20) - (2 × Standard Deviation)
- Band Width: Measures current volatility level
  * Narrow bands = low volatility period
  * Wide bands = high volatility period
- BB Position: Price location within bands (0% = lower band, 100% = upper band)
- Statistical meaning: ~95% of price action falls within 2 standard deviations

VOLUME:
- Number of contracts/coins traded in a given time period
- Volume Ratio: Current volume / Average volume over recent periods
- Interpretation:
  * Ratio > 1.0 = more trading activity than usual
  * Ratio < 1.0 = less trading activity than usual
  * Higher ratio = more market participants engaged

ORDER FLOW (Taker Buy/Sell Ratio):
- Measures aggressive buying vs selling pressure from market takers
- Calculation: Taker buy volume / Total volume
- Range: 0-100%
  * >50% = more aggressive buying (market buy orders)
  * <50% = more aggressive selling (market sell orders)
  * 50% = balanced aggressive activity
- CVD (Cumulative Volume Delta): Running sum of (buy volume - sell volume)
- Data source: Binance taker buy/sell volume from kline data

FUNDING RATE (Perpetual Futures):
- Periodic payment mechanism between long and short position holders
- Purpose: Keep perpetual contract price anchored to spot price
- Calculation: Based on premium/discount of perpetual vs spot + interest rate component
- Settlement: Every 8 hours (00:00, 08:00, 16:00 UTC) for Binance
- Interpretation:
  * Positive rate = longs pay shorts (indicating more long positions)
  * Negative rate = shorts pay longs (indicating more short positions)
  * Magnitude shows degree of position imbalance
- Note: Binance 8h funding rate is the actual rate traders pay/receive

OPEN INTEREST (OI):
- Total number of outstanding derivative contracts (sum of all open positions)
- Units: Number of contracts or BTC equivalent
- Change interpretation:
  * Rising OI + rising price = new long positions entering
  * Rising OI + falling price = new short positions entering
  * Falling OI + price move = position closing (profit taking or stop loss)
  * Stable OI + price move = position rotation between traders
- Does NOT indicate direction, only total exposure

ORDER BOOK DEPTH:
- Distribution of buy (bid) and sell (ask) limit orders at various price levels
- Data source: Binance /fapi/v1/depth API (100 levels analyzed)

- OBI (Order Book Imbalance):
  * Calculation: (Bid Volume - Ask Volume) / (Bid Volume + Ask Volume)
  * Range: -1.0 (all asks) to +1.0 (all bids)
  * Simple OBI: Equal weight to all levels
  * Weighted OBI: Exponential decay, closer levels weighted higher (decay factor ~0.8)
  * Adaptive OBI: Decay factor adjusts based on market volatility

- Dynamics (vs Previous Snapshot):
  * OBI Change: Shift in bid/ask balance over time
  * Depth Change: Change in total volume at bid/ask side
  * Trend: Direction of imbalance movement (STRENGTHENING_BIDS, WEAKENING_BIDS, etc.)
  * Note: Requires historical snapshots; first snapshot shows "no historical data"

- Pressure Gradient:
  * Measures concentration of orders near best bid/ask
  * Near-5/10/20: Percentage of volume within 0.5%/1.0%/2.0% of current price
  * Higher percentage = orders clustered close to market price
  * Concentration level: LOW/MEDIUM/HIGH based on near-5 percentage

- Anomalies (Order Walls):
  * Orders significantly larger than average (threshold: 3-4x mean size)
  * Dynamic threshold adjusts based on volatility
  * Shows price level, size in BTC, and multiplier vs average

- Slippage Estimate:
  * Expected price impact when executing a market order of given size
  * Includes confidence level and range (best/worst case)
  * Based on actual order book depth distribution

SUPPORT/RESISTANCE ZONES (v2.0):
- Price levels identified from multiple independent data sources
- Sources:
  * Order Book Walls: Large real limit orders (>2 BTC) at specific prices
  * Bollinger Bands: Upper/lower bands as statistical boundaries
  * SMA_50/SMA_200: Moving average levels
  * Pivot Points: Mathematical price levels calculated from high/low/close

- Zone Strength (based on source confluence):
  * HIGH: Multiple sources agree (≥3) OR large order wall present (>2 BTC)
  * MEDIUM: Two sources agree
  * LOW: Single source only

- Zone Level (timeframe significance, v2.0):
  * MAJOR: Daily/weekly significance (SMA_200, weekly BB) - strongest
  * INTERMEDIATE: 4H significance (SMA_50, 4H BB) - moderate
  * MINOR: 15M/1H significance (SMA_20, 15M BB, Order Walls) - short-term

- Zone Source Type (data reliability, v2.0):
  * ORDER_FLOW: Real-time order book data - most current but can change
  * TECHNICAL: Calculated indicators (SMA, BB) - widely followed
  * STRUCTURAL: Historical price levels (Pivot) - time-tested

- Zone Properties:
  * Price Center: Midpoint of the zone
  * Distance: Percentage distance from current price
  * Sources: Which indicators contributed to this zone
  * Width: Range of the zone (expanded by 0.1% from center)

- Trading Implications:
  * Zones with ORDER_FLOW type are real orders that can be eaten through
  * MAJOR level zones are more significant for longer-term trades
  * Multiple overlapping sources increase confidence in the zone

HISTORICAL CONTEXT (v3.0.1 - 20-bar trend data):
- Purpose: Shows indicator trends over last 20 bars instead of isolated single values
- Data provided:
  * price_trend: Last 20 closing prices
  * rsi_trend: Last 20 RSI values
  * macd_trend: Last 20 MACD values
- Trend Direction: Calculated from price movement
  * BULLISH: Clear upward trend (higher highs, higher lows)
  * BEARISH: Clear downward trend (lower highs, lower lows)
  * NEUTRAL: No clear direction (consolidation)
- Momentum Shift: Rate of change in trend strength
  * INCREASING: Trend is accelerating
  * DECREASING: Trend is weakening
  * STABLE: Trend strength unchanged
- Usage:
  * Compare current values to recent history
  * Identify divergences between price and indicators
  * Assess if current move is continuation or reversal
  * Last 5 values shown for quick pattern recognition
"""


class MultiAgentAnalyzer:
    """
    Multi-agent trading analysis system with Bull/Bear debate mechanism.

    This replaces the single-agent DeepSeek analysis with a multi-perspective
    debate system that produces more balanced and well-reasoned trading decisions.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        temperature: float = 0.3,
        base_url: str = "https://api.deepseek.com",
        debate_rounds: int = 2,
        retry_delay: float = 1.0,  # Configurable retry delay
        json_parse_max_retries: int = 2,  # Configurable JSON parse retries
        memory_file: str = "data/trading_memory.json",  # v3.12: Persistent memory
    ):
        """
        Initialize the multi-agent analyzer.

        Parameters
        ----------
        api_key : str
            DeepSeek API key
        model : str
            Model name (default: deepseek-chat)
        temperature : float
            Temperature for responses (higher = more creative)
        base_url : str
            API base URL
        debate_rounds : int
            Number of debate rounds between Bull and Bear
        retry_delay : float
            Delay in seconds between retry attempts (default: 1.0)
        json_parse_max_retries : int
            Maximum retries for JSON parsing failures (default: 2)
        """
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.temperature = temperature
        self.debate_rounds = debate_rounds
        self.retry_delay = retry_delay
        self.json_parse_max_retries = json_parse_max_retries

        # Setup logger
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # v3.12: Persistent memory for learning from past decisions
        # Based on TradingGroup paper: label outcomes, compile experience summary
        self.memory_file = memory_file
        self.decision_memory: List[Dict] = self._load_memory()

        # Track debate history for debugging
        self.last_debate_transcript: str = ""

        # Track last prompts for diagnosis (v11.4)
        self.last_prompts: Dict[str, Dict[str, str]] = {}

        # Retry configuration (same as DeepSeekAnalyzer)
        self.max_retries = 2
        self.retry_delay = 1.0

        # v3.8: S/R Zone Calculator (multi-source support/resistance)
        self.sr_calculator = SRZoneCalculator(
            cluster_pct=0.5,              # 聚类阈值 0.5%
            zone_expand_pct=0.1,          # Zone 扩展 0.1%
            hard_control_threshold_pct=1.0,  # 硬风控阈值 1% (仅对 HIGH strength)
            logger=self.logger,
        )

        # Cache for S/R zones (updated in analyze())
        self._sr_zones_cache: Optional[Dict[str, Any]] = None

    def _call_api_with_retry(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
    ) -> str:
        """
        Call DeepSeek API with retry logic for robustness.

        Parameters
        ----------
        messages : List[Dict]
            Chat messages to send
        temperature : float, optional
            Override default temperature

        Returns
        -------
        str
            API response content

        Raises
        ------
        Exception
            If all retries fail
        """
        last_error = None
        temp = temperature if temperature is not None else self.temperature

        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temp,
                )
                return response.choices[0].message.content
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    self.logger.warning(
                        f"API call failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}. "
                        f"Retrying in {self.retry_delay}s..."
                    )
                    time.sleep(self.retry_delay)
                else:
                    self.logger.error(f"API call failed after {self.max_retries + 1} attempts: {e}")

        raise last_error

    def _extract_json_with_retry(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_json_retries: int = 2,
    ) -> Optional[Dict[str, Any]]:
        """
        Call API and extract JSON, with retry on parse failure.

        Parameters
        ----------
        messages : List[Dict]
            Chat messages to send
        temperature : float
            Temperature for API call
        max_json_retries : int
            Maximum retries for JSON parsing failures

        Returns
        -------
        Optional[Dict]
            Parsed JSON dict, or None if all retries fail
        """
        for retry_attempt in range(max_json_retries + 1):
            try:
                result = self._call_api_with_retry(messages=messages, temperature=temperature)
                self.logger.debug(f"API response (attempt {retry_attempt + 1}): {result}")

                # Extract JSON from response
                start = result.find('{')
                end = result.rfind('}') + 1
                if start != -1 and end > 0 and start < end:
                    json_str = result[start:end]
                    if json_str.strip():
                        return json.loads(json_str)

                # If we reach here, JSON extraction failed
                if retry_attempt < max_json_retries:
                    self.logger.warning(
                        f"Failed to extract valid JSON (attempt {retry_attempt + 1}/{max_json_retries + 1}). Retrying..."
                    )
                    time.sleep(self.retry_delay)
                else:
                    self.logger.error(f"Failed to extract valid JSON after {max_json_retries + 1} attempts")

            except (json.JSONDecodeError, TypeError, ValueError) as e:
                if retry_attempt < max_json_retries:
                    self.logger.warning(
                        f"JSON parse error (attempt {retry_attempt + 1}/{max_json_retries + 1}): {e}. Retrying..."
                    )
                    time.sleep(self.retry_delay)
                else:
                    self.logger.error(f"JSON parse failed after {max_json_retries + 1} attempts: {e}")

        return None

    def analyze(
        self,
        symbol: str,
        technical_report: Dict[str, Any],
        sentiment_report: Optional[Dict[str, Any]] = None,
        current_position: Optional[Dict[str, Any]] = None,
        price_data: Optional[Dict[str, Any]] = None,
        # ========== MTF v2.1: Multi-Timeframe Support ==========
        order_flow_report: Optional[Dict[str, Any]] = None,
        derivatives_report: Optional[Dict[str, Any]] = None,
        # ========== v3.0: Binance Derivatives (Top Traders, Taker Ratio) ==========
        binance_derivatives_report: Optional[Dict[str, Any]] = None,
        # ========== v3.7: Order Book Depth ==========
        orderbook_report: Optional[Dict[str, Any]] = None,
        # ========== v4.6: Account Context for Add/Reduce Decisions ==========
        account_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run multi-agent analysis with Bull/Bear debate.

        TradingAgents Architecture (Judge-based decision):
        - Phase 1: Bull/Bear debate (2 AI calls)
        - Phase 2: Judge decision (1 AI call with optimized prompt)
        - Phase 3: Risk evaluation (1 AI call)

        Total: 4 AI calls (complete TradingAgents framework)

        Reference: https://github.com/TauricResearch/TradingAgents (UCLA/MIT paper)

        Parameters
        ----------
        symbol : str
            Trading symbol (e.g., "BTCUSDT")
        technical_report : Dict
            Technical indicator data
        sentiment_report : Dict, optional
            Market sentiment data
        current_position : Dict, optional
            Current position information
        price_data : Dict, optional
            Current price data for stop/take profit calculation
        order_flow_report : Dict, optional
            Order flow data (buy/sell ratio, CVD trend) - MTF v2.1
        derivatives_report : Dict, optional
            Derivatives market data (OI, funding, liquidations) - MTF v2.1
        binance_derivatives_report : Dict, optional
            Binance-specific derivatives (top traders, taker ratio) - v3.0
        orderbook_report : Dict, optional
            Order book depth data (OBI, liquidity, slippage) - v3.7
        account_context : Dict, optional
            Account-level info for add/reduce decisions (v4.6):
            - equity, leverage, max_position_value
            - available_capacity, capacity_used_pct, can_add_position

        Returns
        -------
        Dict
            Final trading decision with structure:
            {
                "signal": "LONG|SHORT|CLOSE|HOLD|REDUCE",  # v3.12: Extended signals
                "confidence": "HIGH|MEDIUM|LOW",
                "risk_level": "LOW|MEDIUM|HIGH",
                "position_size_pct": 0-100,  # Target position as % of max allowed
                "stop_loss": float,
                "take_profit": float,
                "reason": str,
                "debate_summary": str,
                "timestamp": str
            }

            Signal types (v3.12):
            - LONG: Open/add to long position
            - SHORT: Open/add to short position
            - CLOSE: Close current position (no reverse)
            - HOLD: No action, maintain current state
            - REDUCE: Reduce current position size (keep direction)
        """
        try:
            self.logger.info("Starting multi-agent analysis (TradingAgents architecture)...")

            # Format reports for prompts
            tech_summary = self._format_technical_report(technical_report)
            sent_summary = self._format_sentiment_report(sentiment_report)

            # Get current price for calculations (确保是数值类型)
            # 注意: 需要在 _format_derivatives_report 之前计算，用于 Liquidations BTC→USD 转换
            raw_price = price_data.get('price', 0) if price_data else technical_report.get('price', 0)
            try:
                current_price = float(raw_price) if raw_price is not None else 0.0
            except (ValueError, TypeError):
                current_price = 0.0

            # MTF v2.1: Format order flow and derivatives for prompts
            order_flow_summary = self._format_order_flow_report(order_flow_report)
            derivatives_summary = self._format_derivatives_report(
                derivatives_report, current_price, binance_derivatives_report
            )
            # v3.7: Format order book depth data
            orderbook_summary = self._format_orderbook_report(orderbook_report)

            # v3.8: Calculate S/R Zones (multi-source support/resistance)
            # v2.0: Use detailed report with raw data for AI verification
            sr_zones = self._calculate_sr_zones(
                current_price=current_price,
                technical_data=technical_report,
                orderbook_data=orderbook_report,
            )
            self._sr_zones_cache = sr_zones  # Cache for _evaluate_risk()
            # v2.0: Use detailed report (includes raw data + level/source_type)
            sr_zones_summary = sr_zones.get('ai_detailed_report', '') if sr_zones else ''
            if not sr_zones_summary:
                sr_zones_summary = sr_zones.get('ai_report', '') if sr_zones else ''

            # Phase 1: Bull/Bear Debate (2 AI calls)
            self.logger.info("Phase 1: Starting Bull/Bear debate...")
            debate_history = ""
            bull_argument = ""
            bear_argument = ""

            for round_num in range(self.debate_rounds):
                self.logger.info(f"Debate Round {round_num + 1}/{self.debate_rounds}")

                # Bull's turn
                bull_argument = self._get_bull_argument(
                    symbol=symbol,
                    technical_report=tech_summary,
                    sentiment_report=sent_summary,
                    order_flow_report=order_flow_summary,      # MTF v2.1
                    derivatives_report=derivatives_summary,     # MTF v2.1
                    orderbook_report=orderbook_summary,         # v3.7
                    sr_zones_report=sr_zones_summary,           # v3.8
                    history=debate_history,
                    bear_argument=bear_argument,
                )
                debate_history += f"\n\n=== ROUND {round_num + 1} ===\n\nBULL ANALYST:\n{bull_argument}"

                # Bear's turn
                bear_argument = self._get_bear_argument(
                    symbol=symbol,
                    technical_report=tech_summary,
                    sentiment_report=sent_summary,
                    order_flow_report=order_flow_summary,      # MTF v2.1
                    derivatives_report=derivatives_summary,     # MTF v2.1
                    orderbook_report=orderbook_summary,         # v3.7
                    sr_zones_report=sr_zones_summary,           # v3.8
                    history=debate_history,
                    bull_argument=bull_argument,
                )
                debate_history += f"\n\nBEAR ANALYST:\n{bear_argument}"

            # Store transcript for debugging
            self.last_debate_transcript = debate_history

            # Phase 2: Judge makes decision (1 AI call)
            self.logger.info("Phase 2: Judge evaluating debate...")
            judge_decision = self._get_judge_decision(
                debate_history=debate_history,
                past_memories=self._get_past_memories(),
            )

            self.logger.info(
                f"🎯 Judge decision: {judge_decision.get('decision', 'HOLD')} "
                f"({judge_decision.get('confidence', 'LOW')} confidence)"
            )

            # Phase 3: Risk evaluation (1 AI call)
            self.logger.info("Phase 3: Risk evaluation...")
            final_decision = self._evaluate_risk(
                proposed_action=judge_decision,
                technical_report=tech_summary,
                sentiment_report=sent_summary,
                current_position=current_position,
                current_price=current_price,
                technical_data=technical_report,  # v3.7: Pass dict for BB checks
                account_context=account_context,  # v4.6: Account info for add/reduce
            )

            self.logger.info(f"Multi-agent decision: {final_decision.get('signal')} "
                           f"({final_decision.get('confidence')} confidence)")

            return final_decision

        except Exception as e:
            self.logger.error(f"Multi-agent analysis failed: {e}")
            return self._create_fallback_signal(price_data or technical_report)

    def _get_bull_argument(
        self,
        symbol: str,
        technical_report: str,
        sentiment_report: str,
        order_flow_report: str,      # MTF v2.1
        derivatives_report: str,     # MTF v2.1
        orderbook_report: str,       # v3.7
        sr_zones_report: str,        # v3.8
        history: str,
        bear_argument: str,
    ) -> str:
        """
        Generate bull analyst's argument.

        Borrowed from: TradingAgents/agents/researchers/bull_researcher.py
        TradingAgents v3.3: Indicator definitions in system prompt (like TradingAgents)
        v3.8: Added S/R zones report
        """
        # User prompt: Only data and task (no indicator definitions)
        prompt = f"""AVAILABLE DATA:

{technical_report}

{order_flow_report}

{derivatives_report}

{orderbook_report}

{sr_zones_report}

{sentiment_report}

Previous Debate:
{history if history else "This is the opening argument."}

Last Bear Argument:
{bear_argument if bear_argument else "No bear argument yet - make your opening case."}

TASK:
1. Identify BULLISH signals with specific numbers from the data
2. Present 2-3 compelling reasons for going LONG
3. If bear made arguments, counter them with evidence
4. CRITICAL - S/R ZONE ENTRY RULES (v3.15 - Market Order Reality):
   ⚠️ IMPORTANT: System will enter at CURRENT MARKET PRICE, not at S/R levels.
   - ONLY argue for LONG if current price is ALREADY near SUPPORT (within 1-2%)
   - DO NOT argue for LONG if price is in the middle of S/R range (wait for pullback)
   - DO NOT argue for LONG if price is near RESISTANCE (bad entry, high rejection risk)
   - If price is far from support, recommend HOLD and wait for better entry
   - LONG R/R CHECK: Only recommend LONG if R/R ratio >= 1.5:1 at CURRENT price
   - If S/R report shows "LONG entry NOT recommended" - DO NOT argue for LONG
5. If price is far from both S/R zones, recommend HOLD (not a good entry point)

Deliver your argument (2-3 paragraphs):"""

        # System prompt: Role + Indicator definitions (TradingAgents style)
        system_prompt = f"""You are a professional Bull Analyst for {symbol}.
Your role is to analyze raw market data and build the strongest possible case for going LONG.

{INDICATOR_DEFINITIONS}

Use the indicator definitions above to interpret the numbers correctly.
Focus on evidence from the data, not assumptions."""

        # Store prompts for diagnosis (v11.4)
        self.last_prompts["bull"] = {
            "system": system_prompt,
            "user": prompt,
        }

        return self._call_api_with_retry([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ])

    def _get_bear_argument(
        self,
        symbol: str,
        technical_report: str,
        sentiment_report: str,
        order_flow_report: str,      # MTF v2.1
        derivatives_report: str,     # MTF v2.1
        orderbook_report: str,       # v3.7
        sr_zones_report: str,        # v3.8
        history: str,
        bull_argument: str,
    ) -> str:
        """
        Generate bear analyst's argument.

        Borrowed from: TradingAgents/agents/researchers/bear_researcher.py
        TradingAgents v3.3: AI interprets raw data using indicator definitions
        v3.8: Added S/R zones report
        """
        # User prompt: Only data and task (no indicator definitions)
        prompt = f"""AVAILABLE DATA:

{technical_report}

{order_flow_report}

{derivatives_report}

{orderbook_report}

{sr_zones_report}

{sentiment_report}

Previous Debate:
{history}

Last Bull Argument:
{bull_argument}

TASK:
1. Identify BEARISH signals or risks with specific numbers from the data
2. Present 2-3 compelling reasons AGAINST going LONG (or for going SHORT)
3. Counter the bull's arguments with evidence
4. CRITICAL - S/R ZONE ENTRY RULES (v3.15 - Market Order Reality):
   ⚠️ IMPORTANT: System will enter at CURRENT MARKET PRICE, not at S/R levels.
   - ONLY argue for SHORT if current price is ALREADY near RESISTANCE (within 1-2%)
   - DO NOT argue for SHORT if price is in the middle of S/R range (wait for rally)
   - DO NOT argue for SHORT if price is near SUPPORT (bad entry, high bounce risk)
   - If price is far from resistance, recommend HOLD and wait for better entry
   - SHORT R/R CHECK: Only recommend SHORT if R/R ratio >= 1.5:1 at CURRENT price
   - If S/R report shows "SHORT entry NOT recommended" - DO NOT argue for SHORT
5. If price is far from both S/R zones, recommend HOLD (not a good entry point)

Deliver your argument (2-3 paragraphs):"""

        # System prompt: Role + Indicator definitions (TradingAgents style)
        system_prompt = f"""You are a professional Bear Analyst for {symbol}.
Your role is to analyze raw market data and build the strongest possible case AGAINST going LONG.

{INDICATOR_DEFINITIONS}

Use the indicator definitions above to interpret the numbers correctly.
Focus on risks and bearish signals in the data."""

        # Store prompts for diagnosis (v11.4)
        self.last_prompts["bear"] = {
            "system": system_prompt,
            "user": prompt,
        }

        return self._call_api_with_retry([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ])

    def _get_judge_decision(
        self,
        debate_history: str,
        past_memories: str,
    ) -> Dict[str, Any]:
        """
        Judge evaluates the debate and makes decision.

        Borrowed from: TradingAgents/agents/managers/research_manager.py
        Simplified v3.0: Let AI autonomously evaluate without hardcoded rules
        v3.9: Removed duplicate S/R check from prompt (handled by _evaluate_risk)
        v3.10: Aligned with TradingAgents original design (rationale + strategic_actions)
        """
        prompt = f"""As the portfolio manager and debate facilitator, your role is to critically evaluate this round of debate and make a definitive decision: align with the bear analyst, the bull analyst, or choose HOLD only if it is strongly justified based on the arguments presented.

DEBATE TRANSCRIPT:
{debate_history}

PAST REFLECTIONS ON MISTAKES:
{past_memories if past_memories else "No past data - this is a fresh start."}

YOUR TASK:
Summarize the key points from both sides concisely, focusing on the most compelling evidence or reasoning. Your recommendation—LONG, SHORT, or HOLD—must be clear and actionable.

Avoid defaulting to HOLD simply because both sides have valid points; commit to a stance grounded in the debate's strongest arguments.

Take into account your past mistakes on similar situations. Use these insights to refine your decision-making and ensure you are learning and improving.

OUTPUT FORMAT (JSON only, no other text):
{{
    "decision": "LONG|SHORT|HOLD",
    "winning_side": "BULL|BEAR|TIE",
    "confidence": "HIGH|MEDIUM|LOW",
    "rationale": "Why these arguments lead to your conclusion (1-2 sentences)",
    "strategic_actions": ["Concrete step 1", "Concrete step 2"],
    "acknowledged_risks": ["risk1", "risk2"]
}}"""

        system_prompt = "You are a Portfolio Manager and debate facilitator. Critically evaluate the debate and make a decisive trading recommendation. Avoid defaulting to HOLD - commit to the side with stronger evidence. Learn from past mistakes."

        # Store prompts for diagnosis (v11.4)
        self.last_prompts["judge"] = {
            "system": system_prompt,
            "user": prompt,
        }

        # Use JSON retry mechanism to improve reliability
        decision = self._extract_json_with_retry(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # Slightly higher for more nuanced judgment
            max_json_retries=2,
        )

        if decision:
            self.logger.info(f"📊 Judge decision: {decision.get('decision')} ({decision.get('confidence')})")
            return decision

        # Fallback decision if all retries failed
        self.logger.warning("Judge decision parsing failed after retries, using fallback")
        return {
            "decision": "HOLD",
            "winning_side": "TIE",
            "confidence": "LOW",
            "rationale": "JSON parse error - defaulting to HOLD for safety",
            "strategic_actions": ["Wait for next analysis cycle"],
            "acknowledged_risks": ["Parse failure"]
        }

    def _evaluate_risk(
        self,
        proposed_action: Dict[str, Any],
        technical_report: str,
        sentiment_report: str,
        current_position: Optional[Dict[str, Any]],
        current_price: float,
        technical_data: Optional[Dict[str, Any]] = None,
        account_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Final risk evaluation and position sizing.

        Borrowed from: TradingAgents/agents/risk_mgmt/conservative_debator.py
        Simplified v3.0: Let AI determine SL/TP based on market structure
        v3.7: Added BB position hardcoded checks for support/resistance risk control
        v3.8: Replaced BB-only check with multi-source S/R Zone check
        v3.11: Removed preset rules from prompt, let AI decide autonomously
        v4.6: Added account_context for position sizing decisions
        """
        action = proposed_action.get("decision", "HOLD")
        confidence = proposed_action.get("confidence", "LOW")
        # v3.10: Support both rationale (new) and key_reasons (legacy)
        rationale = proposed_action.get("rationale", "")
        strategic_actions = proposed_action.get("strategic_actions", [])
        risks = proposed_action.get("acknowledged_risks", [])
        if isinstance(risks, list):
            risks = risks.copy()  # Don't modify original

        # ========== v3.16: S/R Zone Hard Control moved to AI ==========
        # v3.8-v3.15: Local hard control (blocked trades programmatically)
        # v3.16: Moved to AI - Risk Manager now decides autonomously
        #        Local override only for emergency (sr_hard_control_enabled: true)
        #
        # TradingAgents principle: "Autonomy is non-negotiable"
        # AI receives hard_control info and decides whether to block
        # ================================================================
        sr_hard_control_enabled = getattr(self, 'sr_hard_control_enabled', False)  # v3.16: Default FALSE
        blocked_reason = ""
        hard_control_info = {}

        if self._sr_zones_cache:
            hard_control_info = self._sr_zones_cache.get('hard_control', {})

            # v3.16: Only use local override if explicitly enabled (emergency mode)
            if sr_hard_control_enabled:
                # Block LONG if too close to HIGH strength resistance
                if action == "LONG" and hard_control_info.get('block_long'):
                    blocked_reason = hard_control_info.get('reason', 'Too close to resistance')
                    self.logger.warning(f"⚠️ [LOCAL OVERRIDE] {blocked_reason}")
                    proposed_action["decision"] = "HOLD"
                    proposed_action["confidence"] = "LOW"
                    rationale = f"Blocked: {blocked_reason}"
                    risks.append("Too close to HIGH strength resistance zone")
                    action = "HOLD"

                # Block SHORT if too close to HIGH strength support
                elif action == "SHORT" and hard_control_info.get('block_short'):
                    blocked_reason = hard_control_info.get('reason', 'Too close to support')
                    self.logger.warning(f"⚠️ [LOCAL OVERRIDE] {blocked_reason}")
                    proposed_action["decision"] = "HOLD"
                    proposed_action["confidence"] = "LOW"
                    rationale = f"Blocked: {blocked_reason}"
                    risks.append("Too close to HIGH strength support zone")
                    action = "HOLD"
        # ========== End of S/R Zone Hard Control ==========

        # Format strategic actions for prompt
        actions_str = ', '.join(strategic_actions) if strategic_actions else 'None specified'

        # v2.0: Get S/R zones summary for SL/TP reference
        sr_zones_for_risk = ""
        if self._sr_zones_cache:
            sr_zones_for_risk = self._sr_zones_cache.get('ai_detailed_report', '')
            if not sr_zones_for_risk:
                sr_zones_for_risk = self._sr_zones_cache.get('ai_report', '')

        # v3.16: Format hard control info for AI (moved from local override to AI decision)
        hard_control_section = ""
        if hard_control_info:
            block_long = hard_control_info.get('block_long', False)
            block_short = hard_control_info.get('block_short', False)
            hc_reason = hard_control_info.get('reason', '')
            if block_long or block_short:
                hard_control_section = f"""
⛔ S/R ZONE HARD CONTROL ALERT (v3.16 - AI Decision Required):
- Block LONG Signal: {'YES - TOO CLOSE TO HIGH STRENGTH RESISTANCE' if block_long else 'No'}
- Block SHORT Signal: {'YES - TOO CLOSE TO HIGH STRENGTH SUPPORT' if block_short else 'No'}
- Reason: {hc_reason if hc_reason else 'N/A'}

YOU MUST evaluate this alert and decide:
- If block_long=YES and proposed action is LONG → You SHOULD change to HOLD (unless you have exceptional reasoning)
- If block_short=YES and proposed action is SHORT → You SHOULD change to HOLD (unless you have exceptional reasoning)
- "HIGH strength" means multiple sources confirm this S/R zone (BB + SMA + Order Wall confluence)
- Trading against HIGH strength zones has historically low success rate
"""

        prompt = f"""As the Risk Manager, provide final trade parameters.
{hard_control_section}

PROPOSED TRADE:
- Action: {action}
- Confidence: {confidence}
- Rationale: {rationale}
- Strategic Actions: {actions_str}
- Acknowledged Risks: {', '.join(risks)}

MARKET DATA:
{technical_report}

{sentiment_report}

{sr_zones_for_risk}

CURRENT POSITION:
{self._format_position(current_position)}

ACCOUNT CONTEXT:
{self._format_account(account_context)}

CURRENT PRICE: ${current_price:,.2f}

YOUR TASK:
⚠️ CRITICAL: Entry will be at CURRENT MARKET PRICE (${current_price:,.2f}), not at S/R levels.

0. PRIORITY CHECK - S/R Zone Hard Control (v3.16):
   - If a "⛔ S/R ZONE HARD CONTROL ALERT" is shown above, you MUST address it first
   - Block LONG=YES + proposed LONG → Change to HOLD (price too close to HIGH strength resistance)
   - Block SHORT=YES + proposed SHORT → Change to HOLD (price too close to HIGH strength support)
   - HIGH strength zones have multiple confirming sources - trading against them is high risk
   - You may override ONLY if you have exceptional reasoning (e.g., major breakout with volume confirmation)
   - If you override, you MUST explain why in your "reason" field

1. Calculate SL/TP based on S/R zones:
   - For LONG: SL below nearest SUPPORT, TP at nearest RESISTANCE
   - For SHORT: SL above nearest RESISTANCE, TP at nearest SUPPORT
   - Prefer zones with HIGH strength or ORDER_FLOW confirmation
   - Minimum SL distance: 0.5-1% to avoid noise-triggered stops

2. Evaluate Risk/Reward ratio (THIS IS THE ONLY ENTRY CRITERION - v3.17):
   - Calculate: Risk = |current_price - stop_loss|, Reward = |take_profit - current_price|
   - R/R = Reward / Risk
   - MINIMUM acceptable R/R is 1.5:1

   Understanding R/R and price position:
   - Price closer to SUPPORT → LONG has better R/R (small risk, large reward)
   - Price closer to RESISTANCE → SHORT has better R/R (small risk, large reward)
   - Price in MIDDLE → Both directions have poor R/R → likely HOLD

   ⚠️ R/R is the ONLY criterion for entry quality. Do NOT use arbitrary distance rules.
   ⚠️ If R/R < 1.5:1, you MUST change signal to HOLD regardless of other factors.

3. Position sizing based on R/R quality:
   - R/R >= 2.5:1 → Can use higher position size (80-100%)
   - R/R 2.0-2.5:1 → Medium position size (50-80%)
   - R/R 1.5-2.0:1 → Conservative position size (30-50%)
   - R/R < 1.5:1 → HOLD (do not trade)

4. Final validation:
   - Entry happens at CURRENT MARKET PRICE
   - If proposed signal has R/R >= 1.5:1 → APPROVE
   - If proposed signal has R/R < 1.5:1 → Change to HOLD
   - When in doubt, calculate R/R - it tells you everything about entry quality

SIGNAL TYPES (v3.12 - choose the most appropriate):
- LONG: Open new long or add to existing long position
- SHORT: Open new short or add to existing short position
- CLOSE: Close current position completely (do NOT open opposite position)
- HOLD: No action, maintain current state
- REDUCE: Reduce current position size but keep direction (use with lower position_size_pct)

POSITION SIZE RULES:
- position_size_pct: Target position as percentage of maximum allowed (0-100)
- 100 = full position, 50 = half position, 0 = close all
- For REDUCE signal: set position_size_pct to desired remaining size (e.g., 50 = reduce to half)
- For CLOSE signal: position_size_pct should be 0

OUTPUT FORMAT (JSON only, no other text):
{{
    "signal": "LONG|SHORT|CLOSE|HOLD|REDUCE",
    "confidence": "HIGH|MEDIUM|LOW",
    "risk_level": "LOW|MEDIUM|HIGH",
    "position_size_pct": <number 0-100>,
    "stop_loss": <price_number>,
    "take_profit": <price_number>,
    "reason": "<one sentence explaining the final decision>",
    "debate_summary": "<brief summary of bull vs bear debate>"
}}"""

        system_prompt = "You are a Risk Manager. Analyze the market data and set appropriate trade parameters based on market structure and risk/reward."

        # Store prompts for diagnosis (v11.4)
        self.last_prompts["risk"] = {
            "system": system_prompt,
            "user": prompt,
        }

        # Use JSON retry mechanism to improve reliability
        decision = self._extract_json_with_retry(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_json_retries=2,
        )

        if decision:
            decision["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            decision["debate_rounds"] = self.debate_rounds
            decision["judge_decision"] = proposed_action

            # v3.12: Normalize signal type (handle legacy BUY/SELL)
            decision = self._normalize_signal(decision)

            # Validate stop loss / take profit
            decision = self._validate_sl_tp(decision, current_price)

            return decision

        # Fallback if all retries failed
        self.logger.warning("Risk evaluation parsing failed after retries, using fallback")
        return self._create_fallback_signal({"price": current_price})

    def _normalize_signal(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize signal type to v3.12 format.

        Handles legacy BUY/SELL signals and converts to LONG/SHORT.
        Valid signals: LONG, SHORT, CLOSE, HOLD, REDUCE

        Parameters
        ----------
        decision : Dict
            Raw decision from AI

        Returns
        -------
        Dict
            Decision with normalized signal
        """
        signal = decision.get("signal", "HOLD").upper().strip()

        # Legacy mapping
        legacy_mapping = {
            "BUY": "LONG",
            "SELL": "SHORT",
        }

        # Valid v3.12 signals
        valid_signals = {"LONG", "SHORT", "CLOSE", "HOLD", "REDUCE"}

        # Check if legacy signal
        if signal in legacy_mapping:
            new_signal = legacy_mapping[signal]
            self.logger.info(f"Signal normalized: {signal} → {new_signal}")
            decision["signal"] = new_signal
            decision["original_signal"] = signal  # Keep original for debugging
        elif signal in valid_signals:
            decision["signal"] = signal
        else:
            # Unknown signal, default to HOLD
            self.logger.warning(f"Unknown signal '{signal}', defaulting to HOLD")
            decision["signal"] = "HOLD"
            decision["original_signal"] = signal

        # Validate position_size_pct
        size_pct = decision.get("position_size_pct", 100)
        try:
            size_pct = float(size_pct)
            size_pct = max(0, min(100, size_pct))  # Clamp to 0-100
        except (ValueError, TypeError):
            size_pct = 100 if decision["signal"] in {"LONG", "SHORT"} else 0

        # Special handling for CLOSE signal
        if decision["signal"] == "CLOSE":
            size_pct = 0

        decision["position_size_pct"] = size_pct

        return decision

    def _validate_sl_tp(self, decision: Dict[str, Any], current_price: float) -> Dict[str, Any]:
        """Validate and fix stop loss / take profit values."""
        # 修复: 确保 current_price 是数值类型
        try:
            current_price = float(current_price) if current_price is not None else 0.0
        except (ValueError, TypeError):
            current_price = 0.0
        # Defensive check: ensure current_price is valid before calculations
        if current_price is None or current_price <= 0:
            self.logger.warning(f"Invalid current_price ({current_price}) for SL/TP validation, skipping")
            return decision

        signal = decision.get("signal", "HOLD")
        # 修复: 确保 sl/tp 是数值类型 (AI 可能返回字符串)
        sl_raw = decision.get("stop_loss", 0)
        tp_raw = decision.get("take_profit", 0)
        try:
            sl = float(sl_raw) if sl_raw is not None else 0.0
        except (ValueError, TypeError):
            sl = 0.0
        try:
            tp = float(tp_raw) if tp_raw is not None else 0.0
        except (ValueError, TypeError):
            tp = 0.0

        # Get configuration values (Phase 3: migrated to ConfigManager)
        min_sl_distance = get_min_sl_distance_pct()
        default_sl = get_default_sl_pct()
        default_tp_buy = get_default_tp_pct_buy()
        default_tp_sell = get_default_tp_pct_sell()

        if signal == "BUY":
            # For LONG: SL should be below entry, TP above
            sl_distance = (current_price - sl) / current_price if sl > 0 else 0

            if sl >= current_price:
                # Critical error: SL on wrong side - must fix
                decision["stop_loss"] = current_price * (1 - default_sl)
                self.logger.warning(f"Fixed BUY stop loss (wrong side): {sl} -> {decision['stop_loss']}")
            elif sl_distance < min_sl_distance:
                # v3.13: TradingAgents style - warn but trust AI's S/R-based decision
                # The AI was prompted to consider volatility and R/R ratio
                self.logger.info(
                    f"📍 BUY stop loss is close ({sl_distance*100:.2f}%) - "
                    f"trusting AI's S/R-based SL: ${sl:,.2f}"
                )
                decision["sl_warning"] = f"SL distance {sl_distance*100:.2f}% is below recommended {min_sl_distance*100:.1f}%"

            if tp <= current_price:
                decision["take_profit"] = current_price * (1 + default_tp_buy)
                self.logger.warning(f"Fixed BUY take profit: {tp} -> {decision['take_profit']}")

        elif signal == "SELL":
            # For SHORT: SL should be above entry, TP below
            sl_distance = (sl - current_price) / current_price if sl > 0 else 0

            if sl <= current_price:
                # Critical error: SL on wrong side - must fix
                decision["stop_loss"] = current_price * (1 + default_sl)
                self.logger.warning(f"Fixed SELL stop loss (wrong side): {sl} -> {decision['stop_loss']}")
            elif sl_distance < min_sl_distance:
                # v3.13: TradingAgents style - warn but trust AI's S/R-based decision
                self.logger.info(
                    f"📍 SELL stop loss is close ({sl_distance*100:.2f}%) - "
                    f"trusting AI's S/R-based SL: ${sl:,.2f}"
                )
                decision["sl_warning"] = f"SL distance {sl_distance*100:.2f}% is below recommended {min_sl_distance*100:.1f}%"

            if tp >= current_price:
                decision["take_profit"] = current_price * (1 - default_tp_sell)
                self.logger.warning(f"Fixed SELL take profit: {tp} -> {decision['take_profit']}")

        return decision

    def _format_technical_report(self, data: Dict[str, Any]) -> str:
        """Format technical data for prompts."""
        if not data:
            return "Technical data not available"

        def safe_get(key, default=0):
            val = data.get(key)
            return float(val) if val is not None else default

        # Base report (15M execution layer data)
        # TradingAgents v3.6: Added period statistics for trend assessment
        period_hours = safe_get('period_hours')
        report = f"""
=== MARKET DATA (15M Timeframe) ===

PRICE:
- Current: ${safe_get('price'):,.2f}
- Period High ({period_hours:.0f}h): ${safe_get('period_high'):,.2f}
- Period Low ({period_hours:.0f}h): ${safe_get('period_low'):,.2f}
- Period Change ({period_hours:.0f}h): {safe_get('period_change_pct'):+.2f}%

MOVING AVERAGES:
- SMA 5: ${safe_get('sma_5'):,.2f}
- SMA 20: ${safe_get('sma_20'):,.2f}
- SMA 50: ${safe_get('sma_50'):,.2f}

MOMENTUM:
- RSI: {safe_get('rsi'):.1f}
- MACD: {safe_get('macd'):.4f}
- MACD Signal: {safe_get('macd_signal'):.4f}
- MACD Histogram: {safe_get('macd_histogram'):.4f}

VOLATILITY (Bollinger Bands):
- Upper: ${safe_get('bb_upper'):,.2f}
- Middle: ${safe_get('bb_middle'):,.2f}
- Lower: ${safe_get('bb_lower'):,.2f}
- Position: {safe_get('bb_position'):.1f}% (0%=Lower Band, 100%=Upper Band)

VOLUME:
- Volume Ratio: {safe_get('volume_ratio'):.2f}x average
"""

        # Add 4H decision layer data if available (Multi-Timeframe Analysis)
        mtf_decision = data.get('mtf_decision_layer')
        if mtf_decision:
            def mtf_safe_get(key, default=0):
                val = mtf_decision.get(key)
                return float(val) if val is not None else default

            mtf_rsi = mtf_safe_get('rsi')
            mtf_macd = mtf_safe_get('macd')

            # TradingAgents v3.3: Raw 4H data without interpretation guidance
            report += f"""
=== MARKET DATA (4H Timeframe) ===

MOMENTUM (4H):
- RSI: {mtf_rsi:.1f}
- MACD: {mtf_macd:.4f}
- MACD Signal: {mtf_safe_get('macd_signal'):.4f}

MOVING AVERAGES (4H):
- SMA 20: ${mtf_safe_get('sma_20'):,.2f}
- SMA 50: ${mtf_safe_get('sma_50'):,.2f}

BOLLINGER BANDS (4H):
- Upper: ${mtf_safe_get('bb_upper'):,.2f}
- Middle: ${mtf_safe_get('bb_middle'):,.2f}
- Lower: ${mtf_safe_get('bb_lower'):,.2f}
- Position: {mtf_safe_get('bb_position'):.1f}% (0%=Lower, 100%=Upper)
"""

        # Add 1D trend layer data if available (MTF v3.5)
        mtf_trend = data.get('mtf_trend_layer')
        if mtf_trend:
            def trend_safe_get(key, default=0):
                val = mtf_trend.get(key)
                return float(val) if val is not None else default

            report += f"""
=== MARKET DATA (1D Timeframe - Macro Trend) ===

TREND INDICATORS (1D):
- SMA 200: ${trend_safe_get('sma_200'):,.2f}
- Price vs SMA_200: {'+' if data.get('price', 0) > trend_safe_get('sma_200') else ''}{((data.get('price', 0) / trend_safe_get('sma_200') - 1) * 100) if trend_safe_get('sma_200') > 0 else 0:.2f}%
- MACD: {trend_safe_get('macd'):.4f}
- MACD Signal: {trend_safe_get('macd_signal'):.4f}
"""

        # Add historical context if available (EVALUATION_FRAMEWORK v3.0.1)
        # This shows AI the 20-value trends instead of isolated single values
        historical = data.get('historical_context')
        if historical and historical.get('trend_direction') not in ['INSUFFICIENT_DATA', 'ERROR', None]:
            trend_dir = historical.get('trend_direction', 'N/A')
            momentum = historical.get('momentum_shift', 'N/A')

            # Format recent values (last 5 of 20 for brevity)
            def format_recent(values, fmt=".1f"):
                if not values or not isinstance(values, list):
                    return "N/A"
                recent = values[-5:] if len(values) >= 5 else values
                return " → ".join([f"{v:{fmt}}" for v in recent])

            price_trend = historical.get('price_trend', [])
            rsi_trend = historical.get('rsi_trend', [])
            macd_trend = historical.get('macd_trend', [])

            report += f"""
=== HISTORICAL CONTEXT (Last 20 bars) ===

TREND ANALYSIS:
- Overall Direction: {trend_dir}
- Momentum Shift: {momentum}

RECENT PRICE MOVEMENT (last 5 of 20):
- Prices: ${format_recent(price_trend, ",.0f")}

RECENT RSI MOVEMENT (last 5 of 20):
- RSI: {format_recent(rsi_trend)}

RECENT MACD MOVEMENT (last 5 of 20):
- MACD: {format_recent(macd_trend, ".4f")}
"""

        return report

    def _format_sentiment_report(self, data: Optional[Dict[str, Any]]) -> str:
        """Format sentiment data for prompts.

        TradingAgents v3.3: Pass raw ratios only, no interpretation.
        """
        if not data:
            return "SENTIMENT: Data not available"

        # Fix: Ensure numeric types for formatting (API may return strings)
        try:
            net = float(data.get('net_sentiment') or 0)
        except (ValueError, TypeError):
            net = 0.0
        try:
            pos_ratio = float(data.get('positive_ratio') or 0)
        except (ValueError, TypeError):
            pos_ratio = 0.0
        try:
            neg_ratio = float(data.get('negative_ratio') or 0)
        except (ValueError, TypeError):
            neg_ratio = 0.0
        sign = '+' if net >= 0 else ''

        # TradingAgents v3.3: Raw data only, AI interprets
        return f"""
MARKET SENTIMENT (Binance Long/Short Ratio):
- Long Ratio: {pos_ratio:.1%}
- Short Ratio: {neg_ratio:.1%}
- Net: {sign}{net:.3f}
"""

    def _format_position(self, position: Optional[Dict[str, Any]]) -> str:
        """
        Format current position for AI prompts with Tier 1 + Tier 2 + v4.7 fields.

        v4.5: Enhanced position data for better AI decision making.
        v4.7: Added liquidation risk, funding rate, and drawdown attribution.
        """
        if not position:
            return "No current position (FLAT)"

        # === Safe extraction of all fields ===
        def safe_float(val, default=0.0):
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        def safe_str(val, default='N/A'):
            return str(val) if val is not None else default

        # Basic fields
        side = position.get('side', 'N/A').upper()
        qty = safe_float(position.get('quantity'))
        avg_px = safe_float(position.get('avg_px'))
        unrealized_pnl = safe_float(position.get('unrealized_pnl'))
        current_price = safe_float(position.get('current_price'))

        # Tier 1 fields
        pnl_pct = safe_float(position.get('pnl_percentage'))
        duration_mins = position.get('duration_minutes', 0) or 0
        sl_price = position.get('sl_price')
        tp_price = position.get('tp_price')
        rr_ratio = position.get('risk_reward_ratio')

        # Tier 2 fields
        peak_pnl = position.get('peak_pnl_pct')
        worst_pnl = position.get('worst_pnl_pct')
        entry_conf = position.get('entry_confidence')
        margin_pct = position.get('margin_used_pct')

        # v4.7: Liquidation risk fields
        liquidation_price = position.get('liquidation_price')
        liquidation_buffer_pct = position.get('liquidation_buffer_pct')
        is_liquidation_risk_high = position.get('is_liquidation_risk_high', False)

        # v4.7: Funding rate fields
        funding_rate_current = position.get('funding_rate_current')
        funding_rate_cumulative_usd = position.get('funding_rate_cumulative_usd')
        effective_pnl = position.get('effective_pnl_after_funding')
        daily_funding_cost = position.get('daily_funding_cost_usd')

        # v4.7: Drawdown fields
        max_drawdown_pct = position.get('max_drawdown_pct')
        max_drawdown_duration_bars = position.get('max_drawdown_duration_bars')
        consecutive_lower_lows = position.get('consecutive_lower_lows', 0)

        # === Build formatted output ===
        lines = []

        # Header
        lines.append(f"Side: {side} | Size: {qty:.4f} BTC | Entry: ${avg_px:,.2f}")
        lines.append("")

        # Performance section
        lines.append("Performance:")
        pnl_sign = '+' if pnl_pct >= 0 else ''
        lines.append(f"  P&L: ${unrealized_pnl:+,.2f} ({pnl_sign}{pnl_pct:.2f}%)")

        # v4.7: Show effective PnL after funding
        if effective_pnl is not None and funding_rate_cumulative_usd:
            eff_sign = '+' if effective_pnl >= 0 else ''
            lines.append(f"  Effective P&L (after funding): ${effective_pnl:+,.2f}")

        # Peak/worst if available
        if peak_pnl is not None or worst_pnl is not None:
            peak_str = f"+{peak_pnl:.2f}%" if peak_pnl is not None else "N/A"
            worst_str = f"{worst_pnl:+.2f}%" if worst_pnl is not None else "N/A"
            lines.append(f"  Peak: {peak_str} | Worst: {worst_str}")

        # v4.7: Drawdown attribution
        if max_drawdown_pct is not None and max_drawdown_pct > 0:
            dd_bars = max_drawdown_duration_bars or 0
            lines.append(f"  Current Drawdown: -{max_drawdown_pct:.2f}% (for {dd_bars} bars)")

        # Duration
        if duration_mins > 0:
            if duration_mins >= 60:
                hours = duration_mins // 60
                mins = duration_mins % 60
                duration_str = f"{hours}h {mins}m"
            else:
                duration_str = f"{duration_mins} minutes"
            lines.append(f"  Duration: {duration_str}")

        lines.append("")

        # v4.7: Liquidation Risk section (CRITICAL)
        lines.append("Liquidation Risk:")
        if liquidation_price is not None:
            lines.append(f"  Liquidation Price: ${liquidation_price:,.2f}")
            if liquidation_buffer_pct is not None:
                risk_emoji = "🔴" if is_liquidation_risk_high else "🟢"
                lines.append(f"  Buffer: {risk_emoji} {liquidation_buffer_pct:.1f}%")
                if is_liquidation_risk_high:
                    lines.append("  ⚠️ WARNING: Liquidation risk HIGH (<10% buffer)")
        else:
            lines.append("  Liquidation data not available")

        lines.append("")

        # v4.7: Funding Rate section (for perpetuals)
        lines.append("Funding Rate Impact:")
        if funding_rate_current is not None:
            fr_pct = funding_rate_current * 100
            fr_emoji = "🔴" if fr_pct > 0.01 else "🟢" if fr_pct < -0.01 else "⚪"
            lines.append(f"  Current Rate: {fr_emoji} {fr_pct:.4f}% per 8h")
            if daily_funding_cost is not None:
                lines.append(f"  Daily Cost: ${daily_funding_cost:.2f}")
            if funding_rate_cumulative_usd is not None:
                cum_sign = '+' if funding_rate_cumulative_usd >= 0 else ''
                lines.append(f"  Cumulative Paid: ${funding_rate_cumulative_usd:+.2f}")
        else:
            lines.append("  Funding rate data not available")

        lines.append("")

        # Risk Management section
        lines.append("Risk Management:")
        if sl_price is not None:
            sl_dist = ((sl_price - avg_px) / avg_px * 100) if avg_px > 0 else 0
            lines.append(f"  Stop Loss: ${sl_price:,.2f} ({sl_dist:+.2f}%)")
        else:
            lines.append("  Stop Loss: NOT SET")

        if tp_price is not None:
            tp_dist = ((tp_price - avg_px) / avg_px * 100) if avg_px > 0 else 0
            lines.append(f"  Take Profit: ${tp_price:,.2f} ({tp_dist:+.2f}%)")
        else:
            lines.append("  Take Profit: NOT SET")

        if rr_ratio is not None:
            lines.append(f"  Risk/Reward Ratio: {rr_ratio:.1f}:1")

        if margin_pct is not None:
            lines.append(f"  Margin Used: {margin_pct:.1f}% of equity")

        lines.append("")

        # Entry Context section
        lines.append("Entry Context:")
        if entry_conf:
            lines.append(f"  Entry Confidence: {entry_conf}")
        else:
            lines.append("  Entry Confidence: UNKNOWN")

        if current_price and avg_px > 0:
            price_vs_entry = ((current_price - avg_px) / avg_px * 100)
            lines.append(f"  Current vs Entry: {price_vs_entry:+.2f}%")

        # v4.7: Market structure hint
        if consecutive_lower_lows and consecutive_lower_lows >= 3:
            lines.append(f"  ⚠️ Bearish structure: {consecutive_lower_lows} consecutive lower lows")

        return "\n".join(lines)

    def _format_account(self, account: Optional[Dict[str, Any]]) -> str:
        """
        Format account context for AI prompts (v4.6 + v4.7).

        Provides capital, capacity, and portfolio-level risk information.
        v4.7: Added liquidation buffer, funding costs, and total P&L.
        """
        if not account:
            return "Account context not available"

        lines = []

        # Capital info
        equity = account.get('equity', 0)
        leverage = account.get('leverage', 1)
        lines.append(f"Equity: ${equity:,.2f} | Leverage: {leverage}x")

        # Position capacity
        max_pos_value = account.get('max_position_value', 0)
        current_pos_value = account.get('current_position_value', 0)
        available = account.get('available_capacity', 0)
        capacity_pct = account.get('capacity_used_pct', 0)

        lines.append("")
        lines.append("Position Capacity:")
        lines.append(f"  Max Allowed: ${max_pos_value:,.2f}")
        lines.append(f"  Currently Used: ${current_pos_value:,.2f} ({capacity_pct:.1f}%)")
        lines.append(f"  Available: ${available:,.2f}")

        # v4.7: Portfolio P&L
        total_pnl = account.get('total_unrealized_pnl_usd')
        if total_pnl is not None:
            lines.append("")
            lines.append("Portfolio P&L:")
            pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
            lines.append(f"  Total Unrealized: {pnl_emoji} ${total_pnl:+,.2f}")

        # v4.7: Portfolio Liquidation Risk
        liq_buffer_min = account.get('liquidation_buffer_portfolio_min_pct')
        if liq_buffer_min is not None:
            lines.append("")
            lines.append("Portfolio Liquidation Risk:")
            risk_emoji = "🔴" if liq_buffer_min < 10 else "🟡" if liq_buffer_min < 15 else "🟢"
            lines.append(f"  Min Liquidation Buffer: {risk_emoji} {liq_buffer_min:.1f}%")
            if liq_buffer_min < 10:
                lines.append("  ⚠️ CRITICAL: Portfolio near liquidation!")
            elif liq_buffer_min < 15:
                lines.append("  ⚠️ WARNING: Reduce risk or add margin")

        # v4.7: Funding Costs
        daily_funding = account.get('total_daily_funding_cost_usd')
        cumulative_funding = account.get('total_cumulative_funding_paid_usd')
        if daily_funding is not None or cumulative_funding is not None:
            lines.append("")
            lines.append("Funding Costs:")
            if daily_funding is not None:
                lines.append(f"  Daily Cost: ${daily_funding:.2f}")
            if cumulative_funding is not None:
                lines.append(f"  Cumulative Paid: ${cumulative_funding:+.2f}")

        # Add/reduce guidance
        can_add = account.get('can_add_position', False)
        can_add_safely = account.get('can_add_position_safely', False)
        lines.append("")
        if can_add_safely:
            lines.append("✅ Safe to add position (capacity + liquidation buffer OK)")
        elif can_add:
            lines.append("⚠️ Capacity available but liquidation buffer low - add with caution")
        else:
            lines.append("🔴 Near max capacity - consider REDUCE or HOLD")

        return "\n".join(lines)

    # =========================================================================
    # v3.12: Persistent Memory System (TradingGroup-style experience summary)
    # =========================================================================

    def _load_memory(self) -> List[Dict]:
        """Load memory from JSON file."""
        import os
        try:
            if os.path.exists(self.memory_file):
                with open(self.memory_file, 'r') as f:
                    data = json.load(f)
                    self.logger.info(f"📚 Loaded {len(data)} memories from {self.memory_file}")
                    return data
        except Exception as e:
            self.logger.warning(f"Failed to load memory: {e}")
        return []

    def _save_memory(self):
        """Save memory to JSON file."""
        import os
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
            with open(self.memory_file, 'w') as f:
                json.dump(self.decision_memory, f, indent=2)
            self.logger.debug(f"💾 Saved {len(self.decision_memory)} memories")
        except Exception as e:
            self.logger.warning(f"Failed to save memory: {e}")

    def _get_past_memories(self) -> str:
        """
        Get past decision memories formatted for AI learning.

        Based on TradingGroup paper: show both successes and failures
        to help AI identify patterns and avoid repeating mistakes.
        """
        if not self.decision_memory:
            return ""

        # Separate successes and failures
        successes = [m for m in self.decision_memory if m.get('pnl', 0) > 0]
        failures = [m for m in self.decision_memory if m.get('pnl', 0) <= 0]

        # Take most recent 3 of each
        recent_successes = successes[-3:] if successes else []
        recent_failures = failures[-3:] if failures else []

        lines = []

        if recent_successes:
            lines.append("SUCCESSFUL TRADES (learn from these):")
            for mem in recent_successes:
                conditions = mem.get('conditions', 'N/A')
                lines.append(
                    f"  ✅ {mem.get('decision')} → {mem.get('pnl', 0):+.2f}% | "
                    f"Conditions: {conditions}"
                )

        if recent_failures:
            lines.append("FAILED TRADES (avoid repeating):")
            for mem in recent_failures:
                conditions = mem.get('conditions', 'N/A')
                lesson = mem.get('lesson', 'N/A')
                lines.append(
                    f"  ❌ {mem.get('decision')} → {mem.get('pnl', 0):+.2f}% | "
                    f"Conditions: {conditions} | Lesson: {lesson}"
                )

        return "\n".join(lines)

    def record_outcome(
        self,
        decision: str,
        pnl: float,
        conditions: str = "",
        lesson: str = "",
    ):
        """
        Record trade outcome for learning.

        Call this after a trade is closed to help the system learn.

        Parameters
        ----------
        decision : str
            The decision that was made (BUY/SELL/HOLD)
        pnl : float
            Percentage profit/loss
        conditions : str
            Market conditions at entry (e.g., "RSI=65, trend=UP, funding=0.01%")
        lesson : str
            Lesson learned from this trade (auto-generated if empty)
        """
        # Auto-generate lesson based on outcome
        if not lesson:
            if pnl < -2:
                lesson = "Significant loss - review entry conditions carefully"
            elif pnl < 0:
                lesson = "Small loss - timing or direction may need adjustment"
            elif pnl > 2:
                lesson = "Good profit - this setup worked well"
            elif pnl > 0:
                lesson = "Small profit - consider holding longer or tighter stops"
            else:
                lesson = "Breakeven - entry/exit timing needs improvement"

        self.decision_memory.append({
            "decision": decision,
            "pnl": round(pnl, 2),
            "conditions": conditions,
            "lesson": lesson,
            "timestamp": datetime.now().isoformat(),
        })

        # Keep only last 50 memories (enough for pattern recognition)
        if len(self.decision_memory) > 50:
            self.decision_memory.pop(0)

        # Persist to file
        self._save_memory()

        self.logger.info(
            f"📝 Recorded: {decision} → {pnl:+.2f}% | "
            f"Conditions: {conditions[:50]}... | Lesson: {lesson}"
        )

    def _create_fallback_signal(self, price_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create conservative fallback signal when analysis fails."""
        price = price_data.get('price', 0) if price_data else 0
        default_sl = get_default_sl_pct()

        return {
            "signal": "HOLD",
            "confidence": "LOW",
            "risk_level": "HIGH",
            "position_size_pct": 0,
            "stop_loss": price * (1 - default_sl) if price else 0,
            "take_profit": price * (1 + default_sl) if price else 0,  # Use SL_PCT for HOLD
            "reason": "Multi-agent analysis failed - defaulting to HOLD",
            "debate_summary": "Analysis error occurred",
            "is_fallback": True,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def get_last_debate(self) -> str:
        """Return the last debate transcript for debugging/logging."""
        return self.last_debate_transcript

    def get_last_prompts(self) -> Dict[str, Dict[str, str]]:
        """
        Return the last prompts sent to each agent (v11.4 diagnostic feature).

        Returns
        -------
        Dict[str, Dict[str, str]]
            {
                "bull": {"system": "...", "user": "..."},
                "bear": {"system": "...", "user": "..."},
                "judge": {"system": "...", "user": "..."},
                "risk": {"system": "...", "user": "..."},
            }
        """
        return self.last_prompts

    def _format_order_flow_report(self, data: Optional[Dict[str, Any]]) -> str:
        """
        Format order flow data for AI prompts.

        MTF v2.1: New method for order flow integration

        Parameters
        ----------
        data : Dict, optional
            Order flow data containing buy_ratio, cvd_trend, etc.

        Returns
        -------
        str
            Formatted order flow report for AI prompts
        """
        if not data or data.get('data_source') == 'none':
            return "ORDER FLOW: Data not available (using neutral assumptions)"

        buy_ratio = data.get('buy_ratio', 0.5)
        avg_trade = data.get('avg_trade_usdt', 0)
        volume_usdt = data.get('volume_usdt', 0)
        trades_count = data.get('trades_count', 0)
        recent_bars = data.get('recent_10_bars', [])

        # Format recent bars (raw data only, AI infers trend)
        recent_str = ", ".join([f"{r:.1%}" for r in recent_bars]) if recent_bars else "N/A"

        # TradingAgents v3.6: Added volume_usdt for market activity assessment
        return f"""
ORDER FLOW (Binance Taker Data):
- Buy Ratio (10-bar avg): {buy_ratio:.1%}
- Volume (USDT): ${volume_usdt:,.0f}
- Avg Trade Size: ${avg_trade:,.0f} USDT
- Trade Count: {trades_count:,}
- Recent 10 Bars: [{recent_str}]
"""

    def _format_derivatives_report(
        self,
        data: Optional[Dict[str, Any]],
        current_price: float = 0.0,
        binance_derivatives: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Format derivatives data for AI prompts.

        MTF v2.1: New method for derivatives integration
        v3.0: Added binance_derivatives (top traders, taker ratio)

        Parameters
        ----------
        data : Dict, optional
            Coinalyze derivatives data (OI, funding rate, liquidations)
        current_price : float
            Current BTC price for converting liquidations from BTC to USD
        binance_derivatives : Dict, optional
            Binance-specific derivatives (top traders, taker ratio) - v3.0

        Returns
        -------
        str
            Formatted derivatives report for AI prompts
        """
        parts = []

        # =========================================================================
        # Section 1: Coinalyze Data
        # =========================================================================
        if data and data.get('enabled', True):
            parts.append("COINALYZE DERIVATIVES:")

            # Open Interest (v3.9: removed trend label for AI autonomy)
            oi = data.get('open_interest')
            if oi:
                try:
                    oi_btc = float(oi.get('value', 0) or 0)
                except (ValueError, TypeError):
                    oi_btc = 0.0
                parts.append(f"- Open Interest: {oi_btc:,.2f} BTC")
            else:
                parts.append("- Open Interest: N/A")

            # Funding Rate (v3.9: removed trend label for AI autonomy)
            funding = data.get('funding_rate')
            if funding:
                try:
                    rate = float(funding.get('value', 0) or 0)
                except (ValueError, TypeError):
                    rate = 0.0
                rate_pct = rate * 100
                parts.append(f"- Funding Rate: {rate_pct:.4f}%")
            else:
                parts.append("- Funding Rate: N/A")

            # Liquidations
            liq = data.get('liquidations')
            if liq:
                history = liq.get('history', [])
                if history:
                    item = history[-1]
                    long_liq_btc = float(item.get('l', 0))
                    short_liq_btc = float(item.get('s', 0))
                    total_btc = long_liq_btc + short_liq_btc

                    price_for_conversion = current_price if current_price > 0 else 88000
                    total_usd = total_btc * price_for_conversion

                    parts.append(f"- Liquidations (1h): {total_btc:.4f} BTC (${total_usd:,.0f})")
                    if total_btc > 0:
                        long_ratio = long_liq_btc / total_btc
                        parts.append(f"  - Long Liq: {long_liq_btc:.4f} BTC ({long_ratio:.0%})")
                        parts.append(f"  - Short Liq: {short_liq_btc:.4f} BTC ({1-long_ratio:.0%})")
                else:
                    parts.append("- Liquidations (1h): N/A")
            else:
                parts.append("- Liquidations (1h): N/A")

            # Long/Short Ratio from Coinalyze (v3.9: removed trend label)
            ls_hist = data.get('long_short_ratio_history')
            if ls_hist and ls_hist.get('history'):
                latest = ls_hist['history'][-1]
                ls_ratio = float(latest.get('r', 1))
                long_pct = float(latest.get('l', 50))
                short_pct = float(latest.get('s', 50))
                parts.append(
                    f"- Long/Short Ratio: {ls_ratio:.2f} (Long {long_pct:.1f}% / Short {short_pct:.1f}%)"
                )
        else:
            parts.append("COINALYZE: Data not available")

        # =========================================================================
        # Section 2: Binance Derivatives (Unique Data)
        # =========================================================================
        if binance_derivatives:
            parts.append("\nBINANCE DERIVATIVES (Top Traders & Taker):")

            # Top Traders Position Ratio (v3.9: removed trend label)
            top_pos = binance_derivatives.get('top_long_short_position', {})
            latest = top_pos.get('latest')
            if latest:
                ratio = float(latest.get('longShortRatio', 1))
                long_pct = float(latest.get('longAccount', 0.5)) * 100
                short_pct = float(latest.get('shortAccount', 0.5)) * 100
                parts.append(
                    f"- Top Traders Position: Long {long_pct:.1f}% / Short {short_pct:.1f}% "
                    f"(Ratio: {ratio:.2f})"
                )

            # Taker Buy/Sell Ratio (v3.9: removed trend label)
            taker = binance_derivatives.get('taker_long_short', {})
            latest = taker.get('latest')
            if latest:
                ratio = float(latest.get('buySellRatio', 1))
                parts.append(f"- Taker Buy/Sell Ratio: {ratio:.3f}")

            # OI from Binance (v3.9: removed trend label)
            oi_hist = binance_derivatives.get('open_interest_hist', {})
            latest = oi_hist.get('latest')
            if latest:
                oi_usd = float(latest.get('sumOpenInterestValue', 0))
                parts.append(f"- OI (Binance): ${oi_usd:,.0f}")

            # 24h Stats
            ticker = binance_derivatives.get('ticker_24hr')
            if ticker:
                change_pct = float(ticker.get('priceChangePercent', 0))
                volume = float(ticker.get('quoteVolume', 0))
                parts.append(f"- 24h: Change {change_pct:+.2f}%, Volume ${volume:,.0f}")

        if not parts:
            return "DERIVATIVES: No data available"

        return "\n".join(parts)

    def _calculate_sr_zones(
        self,
        current_price: float,
        technical_data: Optional[Dict[str, Any]],
        orderbook_data: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Calculate S/R Zones from multiple data sources (v3.8).

        Combines:
        - Bollinger Bands (BB Upper/Lower)
        - SMA (SMA_50, SMA_200)
        - Order Book Walls (bid/ask anomalies)

        Parameters
        ----------
        current_price : float
            Current market price
        technical_data : Dict, optional
            Technical indicator data containing BB and SMA values
        orderbook_data : Dict, optional
            Order book data containing anomalies (walls)

        Returns
        -------
        Dict
            S/R zones result from SRZoneCalculator
        """
        if current_price <= 0:
            return self.sr_calculator._empty_result()

        # Extract BB data
        bb_data = None
        if technical_data:
            bb_upper = technical_data.get('bb_upper')
            bb_lower = technical_data.get('bb_lower')
            bb_middle = technical_data.get('bb_middle')
            if bb_upper and bb_lower:
                bb_data = {
                    'upper': bb_upper,
                    'lower': bb_lower,
                    'middle': bb_middle,
                }

        # Extract SMA data
        sma_data = None
        if technical_data:
            sma_50 = technical_data.get('sma_50')
            sma_200 = technical_data.get('sma_200')
            if sma_50 or sma_200:
                sma_data = {
                    'sma_50': sma_50,
                    'sma_200': sma_200,
                }

        # Extract Order Book anomalies (walls)
        orderbook_anomalies = None
        if orderbook_data:
            anomalies = orderbook_data.get('anomalies', {})
            if anomalies:
                orderbook_anomalies = {
                    'bid_anomalies': anomalies.get('bid_anomalies', []),
                    'ask_anomalies': anomalies.get('ask_anomalies', []),
                }

        # Calculate S/R zones with detailed report (v2.0)
        try:
            result = self.sr_calculator.calculate_with_detailed_report(
                current_price=current_price,
                bb_data=bb_data,
                sma_data=sma_data,
                orderbook_anomalies=orderbook_anomalies,
            )

            # Log S/R zone detection
            if result.get('nearest_resistance'):
                r = result['nearest_resistance']
                self.logger.debug(
                    f"S/R Zone: Nearest Resistance ${r.price_center:,.0f} "
                    f"({r.distance_pct:.1f}% away) [{r.strength}]"
                )
            if result.get('nearest_support'):
                s = result['nearest_support']
                self.logger.debug(
                    f"S/R Zone: Nearest Support ${s.price_center:,.0f} "
                    f"({s.distance_pct:.1f}% away) [{s.strength}]"
                )

            return result

        except Exception as e:
            self.logger.warning(f"S/R zone calculation failed: {e}")
            return self.sr_calculator._empty_result()

    def _format_orderbook_report(self, data: Optional[Dict[str, Any]]) -> str:
        """
        Format order book depth data for AI prompts.

        v3.7.2: Fully compliant with ORDER_BOOK_IMPLEMENTATION_PLAN.md v2.0 spec

        Spec reference: docs/ORDER_BOOK_IMPLEMENTATION_PLAN.md section 3.3

        Parameters
        ----------
        data : Dict, optional
            Order book depth data from OrderBookProcessor.process()

        Returns
        -------
        str
            Formatted order book report for AI prompts (v2.0 format)
        """
        if not data:
            return "ORDER BOOK DEPTH: Data not available"

        # Check data status
        status = data.get('_status', {})
        status_code = status.get('code', 'UNKNOWN')

        # v2.0: NO_DATA status handling
        if status_code == 'NO_DATA':
            return f"""ORDER BOOK DEPTH (Binance /fapi/v1/depth):
Status: NO_DATA
Reason: {status.get('message', 'Unknown')}

[All metrics unavailable - AI should not assume neutral market]"""

        if status_code != 'OK':
            return f"ORDER BOOK DEPTH: {status.get('message', 'Error occurred')}"

        # ========== Header ==========
        levels = status.get('levels_analyzed', 100)
        history_samples = status.get('history_samples', 0)
        parts = [
            f"ORDER BOOK DEPTH (Binance /fapi/v1/depth, {levels} levels):",
            f"Status: OK ({history_samples} history samples)",
            "",
        ]

        # ========== IMBALANCE Section ==========
        # Fix: Ensure numeric types for formatting (data may contain strings)
        def _safe_float(val, default=0.0):
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        obi = data.get('obi', {})
        simple_obi = _safe_float(obi.get('simple', 0))
        weighted_obi = _safe_float(obi.get('weighted', 0))
        adaptive_obi = _safe_float(obi.get('adaptive_weighted', weighted_obi))
        decay_used = _safe_float(obi.get('decay_used', 0.8), 0.8)

        bid_vol_usd = _safe_float(obi.get('bid_volume_usd', 0))
        ask_vol_usd = _safe_float(obi.get('ask_volume_usd', 0))
        bid_vol_btc = _safe_float(obi.get('bid_volume_btc', 0))
        ask_vol_btc = _safe_float(obi.get('ask_volume_btc', 0))

        parts.append("IMBALANCE:")
        parts.append(f"  Simple OBI: {simple_obi:+.2f}")
        parts.append(f"  Weighted OBI: {weighted_obi:+.2f} (decay={decay_used:.2f}, adaptive)")
        parts.append(f"  Bid Volume: ${bid_vol_usd/1e6:.1f}M ({bid_vol_btc:.1f} BTC)")
        parts.append(f"  Ask Volume: ${ask_vol_usd/1e6:.1f}M ({ask_vol_btc:.1f} BTC)")
        parts.append("")

        # ========== DYNAMICS Section (v2.0 Critical) ==========
        dynamics = data.get('dynamics', {})
        samples_count = int(_safe_float(dynamics.get('samples_count', 0))) if dynamics else 0

        parts.append("⭐ DYNAMICS (vs previous snapshot):")
        if samples_count > 0:
            obi_change = dynamics.get('obi_change')
            obi_change_pct = dynamics.get('obi_change_pct')
            bid_depth_change = dynamics.get('bid_depth_change_pct')
            ask_depth_change = dynamics.get('ask_depth_change_pct')
            spread_change = dynamics.get('spread_change_pct')
            trend = dynamics.get('trend', 'N/A')

            if obi_change is not None:
                obi_change_f = _safe_float(obi_change)
                pct_str = f" ({_safe_float(obi_change_pct):+.1f}%)" if obi_change_pct is not None else ""
                parts.append(f"  OBI Change: {obi_change_f:+.2f}{pct_str}")
            if bid_depth_change is not None:
                parts.append(f"  Bid Depth Change: {_safe_float(bid_depth_change):+.1f}%")
            if ask_depth_change is not None:
                parts.append(f"  Ask Depth Change: {_safe_float(ask_depth_change):+.1f}%")
            if spread_change is not None:
                parts.append(f"  Spread Change: {_safe_float(spread_change):+.1f}%")
            parts.append(f"  Trend: {trend}")
        else:
            parts.append("  [First snapshot - no historical data yet]")
        parts.append("")

        # ========== PRESSURE GRADIENT Section (v2.0) ==========
        gradient = data.get('pressure_gradient', {})
        if gradient:
            # Convert to percentage (values are 0-1 ratios)
            bid_near_5 = _safe_float(gradient.get('bid_near_5', 0)) * 100
            bid_near_10 = _safe_float(gradient.get('bid_near_10', 0)) * 100
            bid_near_20 = _safe_float(gradient.get('bid_near_20', 0)) * 100
            ask_near_5 = _safe_float(gradient.get('ask_near_5', 0)) * 100
            ask_near_10 = _safe_float(gradient.get('ask_near_10', 0)) * 100
            ask_near_20 = _safe_float(gradient.get('ask_near_20', 0)) * 100
            bid_conc = gradient.get('bid_concentration', 'N/A')
            ask_conc = gradient.get('ask_concentration', 'N/A')

            parts.append("⭐ PRESSURE GRADIENT:")
            parts.append(f"  Bid: {bid_near_5:.0f}% near-5, {bid_near_10:.0f}% near-10, {bid_near_20:.0f}% near-20 [{bid_conc} concentration]")
            parts.append(f"  Ask: {ask_near_5:.0f}% near-5, {ask_near_10:.0f}% near-10, {ask_near_20:.0f}% near-20 [{ask_conc} concentration]")
            parts.append("")

        # ========== DEPTH DISTRIBUTION Section (v2.0 - Previously Missing!) ==========
        depth_dist = data.get('depth_distribution', {})
        bands = depth_dist.get('bands', [])
        if bands:
            parts.append("DEPTH DISTRIBUTION (0.5% bands):")
            for band in bands:
                range_str = band.get('range', '')
                side = band.get('side', '').upper()
                volume_usd = _safe_float(band.get('volume_usd', 0))
                # Format volume in millions with 1 decimal
                vol_str = f"${volume_usd/1e6:.1f}M" if volume_usd >= 1e6 else f"${volume_usd/1e3:.0f}K"
                parts.append(f"  {range_str}: {side} {vol_str}")
            parts.append("")

        # ========== ANOMALIES Section ==========
        anomalies = data.get('anomalies', {})
        bid_anomalies = anomalies.get('bid_anomalies', [])
        ask_anomalies = anomalies.get('ask_anomalies', [])
        threshold = _safe_float(anomalies.get('threshold_used', 3.0), 3.0)
        threshold_reason = anomalies.get('threshold_reason', 'default')

        if bid_anomalies or ask_anomalies:
            parts.append(f"ANOMALIES (threshold={threshold:.1f}x, {threshold_reason}):")
            for anom in bid_anomalies[:3]:  # Show up to 3 per side
                price = _safe_float(anom.get('price', 0))
                amount = _safe_float(anom.get('amount', 0))
                multiple = _safe_float(anom.get('multiple', 0))
                parts.append(f"  Bid: ${price:,.0f} @ {amount:.1f} BTC ({multiple:.1f}x)")
            for anom in ask_anomalies[:3]:
                price = _safe_float(anom.get('price', 0))
                amount = _safe_float(anom.get('amount', 0))
                multiple = _safe_float(anom.get('multiple', 0))
                parts.append(f"  Ask: ${price:,.0f} @ {amount:.1f} BTC ({multiple:.1f}x)")
            parts.append("")

        # ========== LIQUIDITY Section ==========
        liquidity = data.get('liquidity', {})
        if liquidity:
            spread_pct = _safe_float(liquidity.get('spread_pct', 0))
            spread_usd = _safe_float(liquidity.get('spread_usd', 0))

            parts.append("LIQUIDITY:")
            parts.append(f"  Spread: {spread_pct:.2f}% (${spread_usd:.2f})")

            # Slippage estimates with confidence and range (v2.0)
            slippage = liquidity.get('slippage', {})
            if slippage:
                # Show 1 BTC slippage as the main indicator
                for side in ['buy', 'sell']:
                    key = f"{side}_1.0_btc"
                    est = slippage.get(key, {})
                    if isinstance(est, dict) and est.get('estimated') is not None:
                        pct = _safe_float(est.get('estimated', 0))
                        conf = _safe_float(est.get('confidence', 0))
                        range_vals = est.get('range', [0, 0])
                        range_low = _safe_float(range_vals[0] if range_vals[0] is not None else 0)
                        range_high = _safe_float(range_vals[1] if range_vals[1] is not None else 0)
                        side_label = "Buy" if side == "buy" else "Sell"
                        parts.append(
                            f"  Slippage ({side_label} 1 BTC): {pct:.2f}% "
                            f"[confidence={conf:.0%}, range={range_low:.2f}%-{range_high:.2f}%]"
                        )

        return "\n".join(parts)
