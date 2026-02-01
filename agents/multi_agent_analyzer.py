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
# TradingAgents v3.3: Indicator Definitions for AI
# Borrowed from: TradingAgents/agents/analysts/market_analyst.py
#
# These definitions teach AI how to interpret raw indicator values.
# AI receives raw numbers and uses these definitions to form its own judgment.
# =============================================================================
INDICATOR_DEFINITIONS = """
INDICATOR REFERENCE (How to interpret the data):

MOVING AVERAGES:
- SMA (Simple Moving Average): Trend direction indicator
  * Price > SMA = Bullish bias
  * Price < SMA = Bearish bias
  * SMA_5 > SMA_20 > SMA_50 = Strong uptrend (aligned)
  * SMA_5 < SMA_20 < SMA_50 = Strong downtrend (aligned)

RSI (Relative Strength Index):
- Range: 0-100
- >70 = Overbought (potential reversal down or pullback)
- <30 = Oversold (potential reversal up or bounce)
- 40-60 = Neutral zone

MACD (Moving Average Convergence Divergence):
- MACD > Signal = Bullish momentum
- MACD < Signal = Bearish momentum
- Histogram growing = Momentum strengthening
- Histogram shrinking = Momentum weakening
- Zero line crossover = Trend change signal

BOLLINGER BANDS:
- Price near Upper Band = Potentially overbought / strong momentum
- Price near Lower Band = Potentially oversold / weak momentum
- Price at Middle Band = Fair value / consolidation
- Band squeeze (narrow) = Low volatility, breakout coming
- Band expansion (wide) = High volatility
- SMA_50 and BB Middle can serve as dynamic support/resistance

SUPPORT/RESISTANCE RISK (IMPORTANT):
- BB Lower Band and recent swing lows act as SUPPORT
- BB Upper Band and recent swing highs act as RESISTANCE
- Risk consideration for trade direction:
  * SHORT near support (BB Lower, within 2%): HIGH RISK - support may hold, causing bounce
  * LONG near resistance (BB Upper, within 2%): HIGH RISK - resistance may hold, causing rejection
- When price is near support/resistance:
  * Require STRONGER evidence to trade against the level
  * Consider tighter stop loss or reduced position size
  * If evidence is weak, prefer HOLD over risky entry
- BB Position interpretation:
  * 0-15% = Very close to support (cautious on SHORT)
  * 85-100% = Very close to resistance (cautious on LONG)
  * 15-85% = Safe zone for directional trades

VOLUME:
- Volume Ratio > 1.5x = High interest, confirms move
- Volume Ratio < 0.5x = Low interest, weak move

ORDER FLOW (Buy Ratio):
- >55% = Buyers dominating (bullish)
- <45% = Sellers dominating (bearish)
- 45-55% = Balanced
- Recent 10 Bars: Look at trend direction (rising = bullish, falling = bearish)

FUNDING RATE (Derivatives):
- Positive (>0.01%) = Longs paying shorts, crowded long
- Negative (<-0.01%) = Shorts paying longs, crowded short
- Near zero = Balanced

OPEN INTEREST:
- Rising OI + Rising Price = New longs entering (bullish)
- Rising OI + Falling Price = New shorts entering (bearish)
- Falling OI = Positions closing, trend weakening

ORDER BOOK DEPTH (Microstructure):
- OBI (Order Book Imbalance):
  * +0.20 to +1.00 = Strong bid pressure (bullish)
  * +0.05 to +0.20 = Mild bid pressure (slight bullish)
  * -0.05 to +0.05 = Balanced
  * -0.20 to -0.05 = Mild ask pressure (slight bearish)
  * -1.00 to -0.20 = Strong ask pressure (bearish)
  * Weighted OBI gives higher weight to orders near best price

- ⭐ DYNAMICS (Critical for timing):
  * OBI Change > +0.05 = Bids strengthening (momentum building)
  * OBI Change < -0.05 = Asks strengthening (selling pressure building)
  * Trend values: BID_STRENGTHENING / ASK_STRENGTHENING / STABLE
  * Bid/Ask Depth Change: Large drops (< -5%) = Liquidity thinning (caution)

- ⭐ PRESSURE GRADIENT (Order concentration):
  * HIGH concentration (near_5 > 40%) = Orders clustered near best price
    - If on bid side: Strong immediate support
    - If on ask side: Strong immediate resistance
  * LOW concentration (near_5 < 25%) = Orders spread out
    - Gradual support/resistance, less likely to hold
  * Compare bid vs ask concentration for directional bias

- ANOMALIES (Large orders):
  * Wall detected = Large order blocking price movement
  * Bid wall = Support level, harder to break down
  * Ask wall = Resistance level, harder to break up
  * Recent pulls (walls removed) may signal trap

- LIQUIDITY (Execution quality):
  * Slippage < 0.05% = Deep book, safe for larger orders
  * Slippage > 0.10% = Thin book, use smaller position size
  * Low confidence slippage = Sparse data, be cautious

SUPPORT/RESISTANCE ZONES (Multi-source S/R):
- Zones are calculated from multiple sources for higher accuracy:
  * Order Book Walls (most reliable) = Real orders at that price
  * Bollinger Bands (dynamic) = Statistical price boundaries
  * SMA_50/SMA_200 (trend) = Moving average support/resistance

- Strength levels:
  * HIGH = Multiple sources agree OR Order Wall present (strong confluence)
  * MEDIUM = 2 sources agree
  * LOW = Single source only

- Trading implications:
  * LONG near HIGH resistance = HIGH RISK (multiple barriers to break)
  * SHORT near HIGH support = HIGH RISK (multiple buyers waiting)
  * Distance < 1% to HIGH zone = Extreme caution
  * Distance > 2% = Safer for directional trades

- Zone usage:
  * Use S/R zones for stop loss placement (beyond the zone)
  * Use S/R zones for take profit targets (before the zone)
  * Order Walls may be pulled (spoofed) - consider with other data
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

        # Memory for learning from past decisions (borrowed from TradingAgents)
        self.decision_memory: List[Dict] = []

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

        Returns
        -------
        Dict
            Final trading decision with structure:
            {
                "signal": "BUY|SELL|HOLD",
                "confidence": "HIGH|MEDIUM|LOW",
                "risk_level": "LOW|MEDIUM|HIGH",
                "position_size_pct": 25|50|100,
                "stop_loss": float,
                "take_profit": float,
                "reason": str,
                "debate_summary": str,
                "timestamp": str
            }
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
            sr_zones = self._calculate_sr_zones(
                current_price=current_price,
                technical_data=technical_report,
                orderbook_data=orderbook_report,
            )
            self._sr_zones_cache = sr_zones  # Cache for _evaluate_risk()
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
2. Present 2-3 compelling reasons AGAINST going LONG
3. Counter the bull's arguments with evidence

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
    ) -> Dict[str, Any]:
        """
        Final risk evaluation and position sizing.

        Borrowed from: TradingAgents/agents/risk_mgmt/conservative_debator.py
        Simplified v3.0: Let AI determine SL/TP based on market structure
        v3.7: Added BB position hardcoded checks for support/resistance risk control
        v3.8: Replaced BB-only check with multi-source S/R Zone check
        """
        action = proposed_action.get("decision", "HOLD")
        confidence = proposed_action.get("confidence", "LOW")
        # v3.10: Support both rationale (new) and key_reasons (legacy)
        rationale = proposed_action.get("rationale", "")
        strategic_actions = proposed_action.get("strategic_actions", [])
        risks = proposed_action.get("acknowledged_risks", [])
        if isinstance(risks, list):
            risks = risks.copy()  # Don't modify original

        # ========== v3.8: S/R Zone Hard Control ==========
        # Uses multi-source S/R zones (BB + SMA + Order Book Walls)
        # Only blocks when near HIGH strength zones (confluence of multiple sources)
        # v3.9: Can be disabled via sr_hard_control_enabled config
        sr_hard_control_enabled = getattr(self, 'sr_hard_control_enabled', True)
        blocked_reason = ""

        if sr_hard_control_enabled and self._sr_zones_cache:
            hard_control = self._sr_zones_cache.get('hard_control', {})

            # Block LONG if too close to HIGH strength resistance
            if action == "LONG" and hard_control.get('block_long'):
                blocked_reason = hard_control.get('reason', 'Too close to resistance')
                self.logger.warning(f"⚠️ {blocked_reason}")
                proposed_action["decision"] = "HOLD"
                proposed_action["confidence"] = "LOW"
                rationale = f"Blocked: {blocked_reason}"
                risks.append("Too close to HIGH strength resistance zone")
                action = "HOLD"

            # Block SHORT if too close to HIGH strength support
            elif action == "SHORT" and hard_control.get('block_short'):
                blocked_reason = hard_control.get('reason', 'Too close to support')
                self.logger.warning(f"⚠️ {blocked_reason}")
                proposed_action["decision"] = "HOLD"
                proposed_action["confidence"] = "LOW"
                rationale = f"Blocked: {blocked_reason}"
                risks.append("Too close to HIGH strength support zone")
                action = "HOLD"
        # ========== End of S/R Zone Hard Control ==========

        # Format strategic actions for prompt
        actions_str = ', '.join(strategic_actions) if strategic_actions else 'None specified'

        prompt = f"""As the Risk Manager, provide final trade parameters.

PROPOSED TRADE:
- Action: {action}
- Confidence: {confidence}
- Rationale: {rationale}
- Strategic Actions: {actions_str}
- Acknowledged Risks: {', '.join(risks)}

MARKET DATA:
{technical_report}

{sentiment_report}

CURRENT POSITION:
{self._format_position(current_position)}

CURRENT PRICE: ${current_price:,.2f}

YOUR TASK:
1. Evaluate if the proposed trade makes sense given the market data
2. Set stop loss based on market structure (support/resistance levels)
3. Set take profit based on confidence level and potential targets
4. Determine appropriate position size based on risk assessment

GUIDELINES:
- Stop loss should be placed at logical market structure levels
- Higher confidence = larger position size, wider targets
- Lower confidence = smaller position size, tighter stops
- Consider the acknowledged risks when setting parameters

OUTPUT FORMAT (JSON only, no other text):
{{
    "signal": "BUY|SELL|HOLD",
    "confidence": "HIGH|MEDIUM|LOW",
    "risk_level": "LOW|MEDIUM|HIGH",
    "position_size_pct": <number 25-100>,
    "stop_loss": <price_number>,
    "take_profit": <price_number>,
    "reason": "<one sentence explaining the final decision>",
    "debate_summary": "<brief summary of bull vs bear debate>"
}}

MAPPING: LONG→BUY, SHORT→SELL, HOLD→HOLD"""

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

            # Validate stop loss / take profit
            decision = self._validate_sl_tp(decision, current_price)

            return decision

        # Fallback if all retries failed
        self.logger.warning("Risk evaluation parsing failed after retries, using fallback")
        return self._create_fallback_signal({"price": current_price})

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
                decision["stop_loss"] = current_price * (1 - default_sl)
                self.logger.warning(f"Fixed BUY stop loss (wrong side): {sl} -> {decision['stop_loss']}")
            elif sl_distance < min_sl_distance:
                decision["stop_loss"] = current_price * (1 - default_sl)
                self.logger.warning(f"Fixed BUY stop loss (too close {sl_distance*100:.2f}%): {sl} -> {decision['stop_loss']}")

            if tp <= current_price:
                decision["take_profit"] = current_price * (1 + default_tp_buy)
                self.logger.warning(f"Fixed BUY take profit: {tp} -> {decision['take_profit']}")

        elif signal == "SELL":
            # For SHORT: SL should be above entry, TP below
            sl_distance = (sl - current_price) / current_price if sl > 0 else 0

            if sl <= current_price:
                decision["stop_loss"] = current_price * (1 + default_sl)
                self.logger.warning(f"Fixed SELL stop loss (wrong side): {sl} -> {decision['stop_loss']}")
            elif sl_distance < min_sl_distance:
                decision["stop_loss"] = current_price * (1 + default_sl)
                self.logger.warning(f"Fixed SELL stop loss (too close {sl_distance*100:.2f}%): {sl} -> {decision['stop_loss']}")

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

        return report

    def _format_sentiment_report(self, data: Optional[Dict[str, Any]]) -> str:
        """Format sentiment data for prompts.

        TradingAgents v3.3: Pass raw ratios only, no interpretation.
        """
        if not data:
            return "SENTIMENT: Data not available"

        net = data.get('net_sentiment') or 0
        pos_ratio = data.get('positive_ratio') or 0
        neg_ratio = data.get('negative_ratio') or 0
        sign = '+' if net >= 0 else ''

        # TradingAgents v3.3: Raw data only, AI interprets
        return f"""
MARKET SENTIMENT (Binance Long/Short Ratio):
- Long Ratio: {pos_ratio:.1%}
- Short Ratio: {neg_ratio:.1%}
- Net: {sign}{net:.3f}
"""

    def _format_position(self, position: Optional[Dict[str, Any]]) -> str:
        """Format current position for prompts."""
        if not position:
            return "No current position (FLAT)"

        qty = position.get('quantity') or 0
        avg_px = position.get('avg_px') or 0
        unrealized_pnl = position.get('unrealized_pnl') or 0

        return f"""
Side: {position.get('side', 'N/A')}
Size: {qty:.4f} BTC
Avg Entry: ${avg_px:,.2f}
Unrealized P&L: ${unrealized_pnl:,.2f}
"""

    def _get_past_memories(self) -> str:
        """Get past decision memories for learning."""
        if not self.decision_memory:
            return ""

        memories = []
        for mem in self.decision_memory[-5:]:  # Last 5 decisions
            outcome = "PROFIT" if mem.get('pnl', 0) > 0 else "LOSS"
            memories.append(
                f"- {mem.get('decision')}: {outcome} ({mem.get('pnl', 0):+.2f}%) | "
                f"Lesson: {mem.get('lesson', 'N/A')}"
            )
        return "\n".join(memories)

    def record_outcome(self, decision: str, pnl: float, lesson: str = ""):
        """
        Record trade outcome for learning.

        Call this after a trade is closed to help the system learn.

        Parameters
        ----------
        decision : str
            The decision that was made (BUY/SELL/HOLD)
        pnl : float
            Percentage profit/loss
        lesson : str
            Lesson learned from this trade
        """
        if not lesson:
            if pnl < -1:
                lesson = f"Lost {abs(pnl):.1f}% - be more cautious in similar conditions"
            elif pnl > 1:
                lesson = f"Gained {pnl:.1f}% - this setup worked well"
            else:
                lesson = "Marginal result - entry/exit timing could improve"

        self.decision_memory.append({
            "decision": decision,
            "pnl": pnl,
            "lesson": lesson,
            "timestamp": datetime.now().isoformat(),
        })

        # Keep only last 20 memories
        if len(self.decision_memory) > 20:
            self.decision_memory.pop(0)

        self.logger.info(f"Recorded outcome: {decision} -> {pnl:+.2f}% | Lesson: {lesson}")

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

            # Open Interest with trend
            oi = data.get('open_interest')
            trends = data.get('trends', {})
            if oi:
                oi_btc = oi.get('value', 0)
                oi_trend = trends.get('oi_trend', 'N/A')
                parts.append(f"- Open Interest: {oi_btc:,.2f} BTC [Trend: {oi_trend}]")
            else:
                parts.append("- Open Interest: N/A")

            # Funding Rate with trend
            funding = data.get('funding_rate')
            if funding:
                rate = funding.get('value', 0)
                rate_pct = rate * 100
                fr_trend = trends.get('funding_trend', 'N/A')
                parts.append(f"- Funding Rate: {rate_pct:.4f}% [Trend: {fr_trend}]")
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

            # Long/Short Ratio from Coinalyze
            ls_hist = data.get('long_short_ratio_history')
            if ls_hist and ls_hist.get('history'):
                latest = ls_hist['history'][-1]
                ls_ratio = float(latest.get('r', 1))
                long_pct = float(latest.get('l', 50))
                short_pct = float(latest.get('s', 50))
                ls_trend = trends.get('long_short_trend', 'N/A')
                parts.append(
                    f"- Long/Short Ratio: {ls_ratio:.2f} (Long {long_pct:.1f}% / Short {short_pct:.1f}%) "
                    f"[Trend: {ls_trend}]"
                )
        else:
            parts.append("COINALYZE: Data not available")

        # =========================================================================
        # Section 2: Binance Derivatives (Unique Data)
        # =========================================================================
        if binance_derivatives:
            parts.append("\nBINANCE DERIVATIVES (Top Traders & Taker):")

            # Top Traders Position Ratio
            top_pos = binance_derivatives.get('top_long_short_position', {})
            latest = top_pos.get('latest')
            if latest:
                ratio = float(latest.get('longShortRatio', 1))
                long_pct = float(latest.get('longAccount', 0.5)) * 100
                short_pct = float(latest.get('shortAccount', 0.5)) * 100
                trend = top_pos.get('trend', 'N/A')
                parts.append(
                    f"- Top Traders Position: Long {long_pct:.1f}% / Short {short_pct:.1f}% "
                    f"(Ratio: {ratio:.2f}) [Trend: {trend}]"
                )

            # Taker Buy/Sell Ratio
            taker = binance_derivatives.get('taker_long_short', {})
            latest = taker.get('latest')
            if latest:
                ratio = float(latest.get('buySellRatio', 1))
                trend = taker.get('trend', 'N/A')
                parts.append(f"- Taker Buy/Sell Ratio: {ratio:.3f} [Trend: {trend}]")

            # OI from Binance
            oi_hist = binance_derivatives.get('open_interest_hist', {})
            latest = oi_hist.get('latest')
            if latest:
                oi_usd = float(latest.get('sumOpenInterestValue', 0))
                trend = oi_hist.get('trend', 'N/A')
                parts.append(f"- OI (Binance): ${oi_usd:,.0f} [Trend: {trend}]")

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

        # Calculate S/R zones
        try:
            result = self.sr_calculator.calculate(
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
        obi = data.get('obi', {})
        simple_obi = obi.get('simple', 0)
        weighted_obi = obi.get('weighted', 0)
        adaptive_obi = obi.get('adaptive_weighted', weighted_obi)
        decay_used = obi.get('decay_used', 0.8)

        bid_vol_usd = obi.get('bid_volume_usd', 0)
        ask_vol_usd = obi.get('ask_volume_usd', 0)
        bid_vol_btc = obi.get('bid_volume_btc', 0)
        ask_vol_btc = obi.get('ask_volume_btc', 0)

        parts.append("IMBALANCE:")
        parts.append(f"  Simple OBI: {simple_obi:+.2f}")
        parts.append(f"  Weighted OBI: {weighted_obi:+.2f} (decay={decay_used:.2f}, adaptive)")
        parts.append(f"  Bid Volume: ${bid_vol_usd/1e6:.1f}M ({bid_vol_btc:.1f} BTC)")
        parts.append(f"  Ask Volume: ${ask_vol_usd/1e6:.1f}M ({ask_vol_btc:.1f} BTC)")
        parts.append("")

        # ========== DYNAMICS Section (v2.0 Critical) ==========
        dynamics = data.get('dynamics', {})
        samples_count = dynamics.get('samples_count', 0) if dynamics else 0

        parts.append("⭐ DYNAMICS (vs previous snapshot):")
        if samples_count > 0:
            obi_change = dynamics.get('obi_change')
            obi_change_pct = dynamics.get('obi_change_pct')
            bid_depth_change = dynamics.get('bid_depth_change_pct')
            ask_depth_change = dynamics.get('ask_depth_change_pct')
            spread_change = dynamics.get('spread_change_pct')
            trend = dynamics.get('trend', 'N/A')

            if obi_change is not None:
                pct_str = f" ({obi_change_pct:+.1f}%)" if obi_change_pct is not None else ""
                parts.append(f"  OBI Change: {obi_change:+.2f}{pct_str}")
            if bid_depth_change is not None:
                parts.append(f"  Bid Depth Change: {bid_depth_change:+.1f}%")
            if ask_depth_change is not None:
                parts.append(f"  Ask Depth Change: {ask_depth_change:+.1f}%")
            if spread_change is not None:
                parts.append(f"  Spread Change: {spread_change:+.1f}%")
            parts.append(f"  Trend: {trend}")
        else:
            parts.append("  [First snapshot - no historical data yet]")
        parts.append("")

        # ========== PRESSURE GRADIENT Section (v2.0) ==========
        gradient = data.get('pressure_gradient', {})
        if gradient:
            # Convert to percentage (values are 0-1 ratios)
            bid_near_5 = gradient.get('bid_near_5', 0) * 100
            bid_near_10 = gradient.get('bid_near_10', 0) * 100
            bid_near_20 = gradient.get('bid_near_20', 0) * 100
            ask_near_5 = gradient.get('ask_near_5', 0) * 100
            ask_near_10 = gradient.get('ask_near_10', 0) * 100
            ask_near_20 = gradient.get('ask_near_20', 0) * 100
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
                volume_usd = band.get('volume_usd', 0)
                # Format volume in millions with 1 decimal
                vol_str = f"${volume_usd/1e6:.1f}M" if volume_usd >= 1e6 else f"${volume_usd/1e3:.0f}K"
                parts.append(f"  {range_str}: {side} {vol_str}")
            parts.append("")

        # ========== ANOMALIES Section ==========
        anomalies = data.get('anomalies', {})
        bid_anomalies = anomalies.get('bid_anomalies', [])
        ask_anomalies = anomalies.get('ask_anomalies', [])
        threshold = anomalies.get('threshold_used', 3.0)
        threshold_reason = anomalies.get('threshold_reason', 'default')

        if bid_anomalies or ask_anomalies:
            parts.append(f"ANOMALIES (threshold={threshold:.1f}x, {threshold_reason}):")
            for anom in bid_anomalies[:3]:  # Show up to 3 per side
                price = anom.get('price', 0)
                amount = anom.get('amount', 0)
                multiple = anom.get('multiple', 0)
                parts.append(f"  Bid: ${price:,.0f} @ {amount:.1f} BTC ({multiple:.1f}x)")
            for anom in ask_anomalies[:3]:
                price = anom.get('price', 0)
                amount = anom.get('amount', 0)
                multiple = anom.get('multiple', 0)
                parts.append(f"  Ask: ${price:,.0f} @ {amount:.1f} BTC ({multiple:.1f}x)")
            parts.append("")

        # ========== LIQUIDITY Section ==========
        liquidity = data.get('liquidity', {})
        if liquidity:
            spread_pct = liquidity.get('spread_pct', 0)
            spread_usd = liquidity.get('spread_usd', 0)

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
                        pct = est.get('estimated', 0)
                        conf = est.get('confidence', 0)
                        range_vals = est.get('range', [0, 0])
                        range_low = range_vals[0] if range_vals[0] is not None else 0
                        range_high = range_vals[1] if range_vals[1] is not None else 0
                        side_label = "Buy" if side == "buy" else "Sell"
                        parts.append(
                            f"  Slippage ({side_label} 1 BTC): {pct:.2f}% "
                            f"[confidence={conf:.0%}, range={range_low:.2f}%-{range_high:.2f}%]"
                        )

        return "\n".join(parts)
