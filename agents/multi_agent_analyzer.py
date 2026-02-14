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
# INDICATOR_DEFINITIONS — Regime-Aware Trading Knowledge Manual
#
# Evolution:
# - v3.12: Basic calculation definitions (TradingAgents style)
# - v3.15: Added "entry at current market price" (removed in v3.17+)
# - v3.17: Replaced distance-based rules with R/R-driven entry criteria
# - v3.25: Complete rewrite — regime-aware usage guide with failure modes
# - v3.26: Risk Manager gets full manual + removed hard rules for AI autonomy
#
# Philosophy (nof1 Alpha Arena / TradingAgents):
# - Encode complete trading knowledge in the system prompt
# - Teach AI regime detection, indicator interpretation, and failure modes
# - Let AI synthesize all data and make independent decisions
# - No hard thresholds that override AI judgment
# =============================================================================
INDICATOR_DEFINITIONS = """
====================================================================
INDICATOR REFERENCE (v3.27)
====================================================================
This reference supplements your existing knowledge with regime-specific
interpretation rules, failure statistics, and specialized frameworks.
Apply this knowledge to the market data provided alongside it.

STEP 1: DETERMINE MARKET REGIME (this changes how all indicators read)
  ADX > 25 + clear price direction    → TRENDING
  ADX < 20 + price oscillating        → RANGING
  ADX < 20 + BB Width at lows         → SQUEEZE (pre-breakout)
  ADX > 25 + BB Width expanding fast  → VOLATILE TREND

REGIME BEHAVIOR:
  TRENDING:  Trend-following has higher win rates. Counter-trend has high failure
             rates. S/R levels frequently break.
  RANGING:   Mean-reversion most reliable. S/R bounces work.
  SQUEEZE:   Big move imminent, direction unknown. ~50% wrong-side risk pre-breakout.
  VOLATILE:  Trend-following works, wider stops needed.
The #1 source of retail losses: applying ranging logic in trending markets.

====================================================================
INDICATORS (each section: TRENDING use → RANGING use → failure mode)
====================================================================

--- RSI (Cardwell Range Shifts) ---
TRENDING: Shifted ranges, not traditional 30/70.
  Uptrend 40-80: pullbacks to 40-50 = with-trend entries. 80 = strong momentum.
  Downtrend 20-60: rallies to 50-60 = with-trend entries. 20 = strong momentum.
RANGING: Traditional 30/70 work as overbought/oversold.
⚠️ Buying RSI <30 in downtrend = most common retail mistake (RSI stays oversold).
   Cardwell: bullish divergences can CONFIRM downtrends, not reverse them.

--- ADX / DI+ / DI- ---
TRENDING: ADX 25-50 = strong trend. 50+ = very strong. DI+>DI- = up, DI->DI+ = down.
RANGING: ADX 0-20. ADX 75+ = potential exhaustion.
⚠️ ADX is lagging — confirms late. Brief spikes in choppy markets = false signals.

--- MACD ---
TRENDING: Crossovers = continuation signals. Zero-line cross = major shift.
  Histogram growth = momentum building. Histogram shrinking = weakening.
RANGING: Whipsaws repeatedly — 74-97% false positive rate in backtests.
⚠️ MACD alone has extremely poor reliability — requires confirmation.

--- BOLLINGER BANDS ---
TRENDING: Price "walks the band" — upper band touch in uptrend is NORMAL.
  Shorting upper band in uptrend = most common BB error. Middle = dynamic S/R.
RANGING: Mean-reversion at bands (upper = overbought, lower = oversold).
SQUEEZE: Low BB Width = big move imminent, direction unknown.
⚠️ Head fakes during squeezes are common.

--- SMA ---
TRENDING: Trend filter — Price > SMA200 = uptrend bias, < SMA200 = downtrend.
  SMA 20/50 = dynamic pullback levels. Golden/Death Cross = long-term shifts.
RANGING: Whipsaws around SMA.
⚠️ 35% false signal rate on crosses. Use as filter, not timing signal.

--- VOLUME ---
TRENDING: Rising price + rising volume = genuine. Falling volume = suspect move.
RANGING: Volume spikes at S/R = potential breakout.
⚠️ Low-volume moves are unreliable regardless of direction.

--- CVD (Cumulative Volume Delta) ---
TRENDING: CVD aligns with price = confirms move.
  CVD diverges: price up + CVD falling = hidden selling; price down + CVD rising = accumulation.
RANGING: Absorption pattern — positive CVD + flat price = large seller absorbing buys.
⚠️ CVD from candle data is approximate. Noisy during low-volume periods.

--- FUNDING RATE ---
Daily holding cost = rate × 3 settlements (every 8h).
  |Rate| < 0.03%: Normal (0.01-0.03% in bull markets is standard, not bearish).
  > +0.05%: Crowded longs. > +0.10%: Extreme, reversal probability rises.
  < -0.03%: Bearish pressure. < -0.10%: Extreme panic, bounce probability rises.
  Predicted vs settled difference > 0.01% = notable shift in market sentiment.
  Predicted vs settled sign reversal (e.g., +0.01% → -0.01%) = significant positioning change.
  Settlement countdown < 30min with extreme predicted rate: expect short-term volatility.
  History: Persistent same-sign rates (>3 settlements) = established positioning.
  Reversal from extreme = positioning unwind, expect opposite-side volatility.
⚠️ Funding alone without OI/price context = premature contrarian trades.

--- PREMIUM INDEX ---
Premium Index = (Mark Price - Index Price) / Index Price.
  Positive = futures trading above spot = long premium (bulls paying to hold).
  Negative = futures below spot = short premium (bears paying to hold).
  Predicts next funding rate direction. Premium > 0.05% = expect positive funding.
  Sharp premium spike = aggressive leveraged positioning, often precedes mean-reversion.
⚠️ Premium Index is instantaneous — confirm with funding trend before acting.

--- OPEN INTEREST (4-Quadrant Matrix) ---
  Price ↑ + OI ↑ = New longs entering → BULLISH CONFIRMATION
  Price ↑ + OI ↓ = Short covering     → WEAK rally (no new conviction)
  Price ↓ + OI ↑ = New shorts entering → BEARISH CONFIRMATION
  Price ↓ + OI ↓ = Long liquidation    → BEARISH EXHAUSTION (potential bottom)
Rising OI in consolidation = energy building. Sharp OI drop after crash = capitulation.
⚠️ OI alone reveals nothing — must combine with price direction.

--- ORDER BOOK ---
OBI: (Bid Vol - Ask Vol) / Total. Positive = buy support. Negative = sell pressure.
Dynamics: OBI/depth changes vs previous snapshot show evolving pressure.
Walls (>3x avg size): Potential S/R, but can be spoofed (placed and cancelled).
⚠️ High slippage = low liquidity → smaller position sizes needed.

--- S/R ZONES ---
Strength: HIGH (≥3 sources), MEDIUM (2), LOW (1).
TRENDING: S/R breaks frequently. Broken support → resistance and vice versa.
RANGING: S/R holds reliably. Mean-reversion at zones works.
⚠️ ADX > 40: S/R bounce rate drops to ~25%.

--- SENTIMENT (Binance L/S Ratio) ---
Contrarian at extremes: >55% long = squeeze risk. >55% short = rally risk.
⚠️ Extremes persist in strong trends. Only meaningful at very high readings (>60%).

--- TIME-SERIES DATA ---
All series ordered oldest → newest (chronological).
Look for: divergences, trend changes, acceleration/deceleration in momentum.

====================================================================
CONFLUENCE FRAMEWORK
====================================================================
Single indicators have high false positive rates. Confirm across layers:
  Layer 1 — TREND: SMA 200, ADX/DI direction
  Layer 2 — MOMENTUM: RSI, MACD histogram, CVD
  Layer 3 — KEY LEVEL: S/R zone, BB band, order book wall

Example — strong setup: All 3 layers align in same direction.
Example — weak setup: Trend layer (ADX/SMA) conflicts with momentum/levels
  → trend is statistically the stronger predictor in this conflict.
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
        sr_zones_config: Optional[Dict] = None,  # v3.0: S/R Zone config from base.yaml
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

        # Full call trace: every AI API call with input/output/timing
        self.call_trace: List[Dict[str, Any]] = []

        # Retry configuration (same as DeepSeekAnalyzer)
        self.max_retries = 2
        self.retry_delay = 1.0

        # v3.8: S/R Zone Calculator (multi-source support/resistance)
        # v3.0: Accept config from base.yaml sr_zones section
        sr_cfg = sr_zones_config or {}
        swing_cfg = sr_cfg.get('swing_detection', {})
        cluster_cfg = sr_cfg.get('clustering', {})
        scoring_cfg = sr_cfg.get('scoring', {})
        hard_ctrl_cfg = sr_cfg.get('hard_control', {})
        aggr_cfg = sr_cfg.get('aggregation', {})
        round_cfg = sr_cfg.get('round_number', {})

        self.sr_calculator = SRZoneCalculator(
            cluster_pct=cluster_cfg.get('cluster_pct', 0.5),
            zone_expand_pct=sr_cfg.get('zone_expand_pct', 0.1),
            hard_control_threshold_pct=hard_ctrl_cfg.get('threshold_pct', 1.0),
            # v5.1: ATR-adaptive hard control
            hard_control_threshold_mode=hard_ctrl_cfg.get('threshold_mode', 'fixed'),
            hard_control_atr_multiplier=hard_ctrl_cfg.get('atr_multiplier', 0.5),
            hard_control_atr_min_pct=hard_ctrl_cfg.get('atr_min_pct', 0.3),
            hard_control_atr_max_pct=hard_ctrl_cfg.get('atr_max_pct', 2.0),
            # v3.0: Swing Point config
            swing_detection_enabled=swing_cfg.get('enabled', True),
            swing_left_bars=swing_cfg.get('left_bars', 5),
            swing_right_bars=swing_cfg.get('right_bars', 5),
            swing_weight=swing_cfg.get('weight', 1.2),
            swing_max_age=swing_cfg.get('max_swing_age', 100),
            # v3.0: ATR adaptive clustering
            use_atr_adaptive=cluster_cfg.get('use_atr_adaptive', True),
            atr_cluster_multiplier=cluster_cfg.get('atr_cluster_multiplier', 0.5),
            # v3.0: Touch count scoring
            touch_count_enabled=scoring_cfg.get('touch_count_enabled', True),
            touch_threshold_atr=scoring_cfg.get('touch_threshold_atr', 0.3),
            optimal_touches=tuple(scoring_cfg.get('optimal_touches', [2, 3])),
            decay_after_touches=scoring_cfg.get('decay_after_touches', 4),
            # v4.0: Aggregation rules (from base.yaml: sr_zones.aggregation.*)
            same_data_weight_cap=aggr_cfg.get('same_data_weight_cap', 2.5),
            max_zone_weight=aggr_cfg.get('max_zone_weight', 6.0),
            confluence_bonus_2=aggr_cfg.get('confluence_bonus_2_sources', 0.2),
            confluence_bonus_3=aggr_cfg.get('confluence_bonus_3_sources', 0.5),
            # v4.0: Round Number config (from base.yaml: sr_zones.round_number.*)
            round_number_btc_step=round_cfg.get('btc_step', 5000),
            round_number_count=round_cfg.get('count', 3),
            logger=self.logger,
        )

        # Cache for S/R zones (updated in analyze())
        self._sr_zones_cache: Optional[Dict[str, Any]] = None

    def _call_api_with_retry(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        trace_label: str = "",
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
                t0 = time.monotonic()
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temp,
                )
                elapsed = time.monotonic() - t0
                content = response.choices[0].message.content
                # Record call trace for diagnostics
                usage = response.usage
                self.call_trace.append({
                    "label": trace_label or f"call_{len(self.call_trace)+1}",
                    "messages": messages,
                    "temperature": temp,
                    "response": content,
                    "elapsed_sec": round(elapsed, 2),
                    "tokens": {
                        "prompt": usage.prompt_tokens if usage else 0,
                        "completion": usage.completion_tokens if usage else 0,
                        "total": usage.total_tokens if usage else 0,
                    } if usage else {},
                })
                return content
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
        trace_label: str = "",
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
                result = self._call_api_with_retry(messages=messages, temperature=temperature, trace_label=trace_label)
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
        # ========== v3.0: OHLC bars for S/R Swing Detection ==========
        bars_data: Optional[List[Dict[str, Any]]] = None,
        # ========== v4.0: MTF bars for S/R pivot + volume profile ==========
        bars_data_4h: Optional[List[Dict[str, Any]]] = None,
        bars_data_1d: Optional[List[Dict[str, Any]]] = None,
        daily_bar: Optional[Dict[str, Any]] = None,
        weekly_bar: Optional[Dict[str, Any]] = None,
        atr_value: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Run multi-agent analysis with Bull/Bear debate.

        TradingAgents Architecture (Judge-based decision):
        - Phase 1: Bull/Bear debate (2 × debate_rounds AI calls, sequential)
        - Phase 2: Judge decision (1 AI call with optimized prompt)
        - Phase 3: Risk evaluation (1 AI call)

        Total: 2×debate_rounds + 2 AI calls (default debate_rounds=2 → 6 calls)

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
        bars_data_4h : List[Dict], optional
            v4.0: 4H OHLCV bars for MTF swing detection
        bars_data_1d : List[Dict], optional
            v4.0: 1D OHLCV bars for MTF swing detection
        daily_bar : Dict, optional
            v4.0: Most recent completed daily bar for pivot calculation
        weekly_bar : Dict, optional
            v4.0: Aggregated weekly bar for pivot calculation
        atr_value : float, optional
            v4.0: Cached ATR value for S/R buffer calculation

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

            # Clear call trace for this analysis cycle
            self.call_trace = []

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
            # v3.0: Pass bars_data for Swing Point detection and Touch Count
            # v4.0: Pass MTF bars for pivot points + volume profile
            sr_zones = self._calculate_sr_zones(
                current_price=current_price,
                technical_data=technical_report,
                orderbook_data=orderbook_report,
                bars_data=bars_data,
                bars_data_4h=bars_data_4h,
                bars_data_1d=bars_data_1d,
                daily_bar=daily_bar,
                weekly_bar=weekly_bar,
                atr_value=atr_value,
            )
            self._sr_zones_cache = sr_zones  # Cache for _evaluate_risk()
            # v2.0: Use detailed report (includes raw data + level/source_type)
            sr_zones_summary = sr_zones.get('ai_detailed_report', '') if sr_zones else ''
            if not sr_zones_summary:
                sr_zones_summary = sr_zones.get('ai_report', '') if sr_zones else ''

            # Phase 1: Bull/Bear Debate (2 × debate_rounds AI calls, sequential)
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
                    trace_label=f"Bull R{round_num + 1}",
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
                    trace_label=f"Bear R{round_num + 1}",
                )
                debate_history += f"\n\nBEAR ANALYST:\n{bear_argument}"

            # Store transcript for debugging
            self.last_debate_transcript = debate_history

            # Phase 2: Judge makes decision (1 AI call)
            self.logger.info("Phase 2: Judge evaluating debate...")
            # v3.23: Build key metrics for Judge's independent sanity check
            # v3.24: Pass all raw data sources for comprehensive verification
            key_metrics = self._build_key_metrics(
                technical_report, derivatives_report,
                order_flow_report, current_price,
                binance_derivatives_report, sentiment_report,
            )
            judge_decision = self._get_judge_decision(
                debate_history=debate_history,
                past_memories=self._get_past_memories(),
                key_metrics=key_metrics,
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
                derivatives_report=derivatives_summary,  # v3.22: Funding rate for cost analysis
                order_flow_report=order_flow_summary,  # v3.23: Liquidity for position sizing
                orderbook_report=orderbook_summary,  # v3.23: Slippage for position sizing
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
        trace_label: str = "Bull",
    ) -> str:
        """
        Generate bull analyst's argument.

        Borrowed from: TradingAgents/agents/researchers/bull_researcher.py
        TradingAgents v3.3: Indicator definitions in system prompt (like TradingAgents)
        v3.8: Added S/R zones report
        """
        # User prompt: Segmented data with clear markers + Chinese task instructions
        prompt = f"""## 📊 MARKET DATA (Technical Indicators)
{technical_report}

## 📈 ORDER FLOW (Taker Data)
{order_flow_report}

## 📉 DERIVATIVES (Funding / OI / Liquidations)
{derivatives_report}

## 📖 ORDER BOOK DEPTH
{orderbook_report}

## 🔑 SUPPORT / RESISTANCE ZONES
{sr_zones_report}

## 💬 SENTIMENT (Long/Short Ratio)
{sentiment_report}

## 🗣️ DEBATE CONTEXT
Previous Debate:
{history if history else "This is the opening argument."}

Last Bear Argument:
{bear_argument if bear_argument else "No bear argument yet - make your opening case."}

## 🎯 【分析任务 — 请严格按步骤执行】

**第一步：判断 MARKET REGIME**
用指标手册判断当前市场状态 (TRENDING / RANGING / SQUEEZE)
— 这决定了后续所有指标的解读方式。

**第二步：识别看多信号**
从上方数据中找出具体的 BULLISH 信号，附带数值。
必须使用当前 regime 对应的解读规则 (例如 RSI 30 在趋势市场 vs 震荡市场含义不同)。

**第三步：构建论点**
提出 2-3 个有说服力的做多理由。
如果 Bear 已有论点，用数据反驳。

**第四步：评估入场条件**
入场价为当前市场价 — 基于 S/R zones 和市场结构评估 R:R 比。

**第五步：陈述失效条件**
什么情况下你的看多论点会被推翻？

请用 2-3 段落交付你的论点："""

        # System prompt: Role + Indicator manual (v3.25: regime-aware)
        # v3.28: Chinese instructions for better DeepSeek instruction-following
        system_prompt = f"""你是 {symbol} 的专业多头分析师 (Bull Analyst)。
你的职责是分析原始市场数据，构建最强有力的做多论据。

{INDICATOR_DEFINITIONS}

【关键规则 — 必须遵守】
⚠️ 你必须先判断 market regime (指标手册第一步)，然后用对应 regime 的规则解读所有指标。
⚠️ 在趋势市场使用震荡市场逻辑 (或反之) 是致命错误。
⚠️ 只基于数据中的证据，不做无根据的假设。"""

        # Store prompts for diagnosis (v11.4)
        self.last_prompts["bull"] = {
            "system": system_prompt,
            "user": prompt,
        }

        return self._call_api_with_retry([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ], trace_label=trace_label)

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
        trace_label: str = "Bear",
    ) -> str:
        """
        Generate bear analyst's argument.

        Borrowed from: TradingAgents/agents/researchers/bear_researcher.py
        TradingAgents v3.3: AI interprets raw data using indicator definitions
        v3.8: Added S/R zones report
        """
        # User prompt: Segmented data with clear markers + Chinese task instructions
        prompt = f"""## 📊 MARKET DATA (Technical Indicators)
{technical_report}

## 📈 ORDER FLOW (Taker Data)
{order_flow_report}

## 📉 DERIVATIVES (Funding / OI / Liquidations)
{derivatives_report}

## 📖 ORDER BOOK DEPTH
{orderbook_report}

## 🔑 SUPPORT / RESISTANCE ZONES
{sr_zones_report}

## 💬 SENTIMENT (Long/Short Ratio)
{sentiment_report}

## 🗣️ DEBATE CONTEXT
Previous Debate:
{history}

Last Bull Argument:
{bull_argument}

## 🎯 【分析任务 — 请严格按步骤执行】

**第一步：判断 MARKET REGIME**
用指标手册判断当前市场状态 (TRENDING / RANGING / SQUEEZE)
— 这决定了后续所有指标的解读方式。

**第二步：识别看空信号和风险**
从上方数据中找出具体的 BEARISH 信号或风险，附带数值。
必须使用当前 regime 对应的解读规则 (例如 "support" 在趋势市场 vs 震荡市场含义不同)。

**第三步：构建论点**
提出 2-3 个反对做多 (或支持做空) 的有力理由。
用数据反驳 Bull 的论点。

**第四步：评估入场条件**
入场价为当前市场价 — 基于 S/R zones 和市场结构评估 R:R 比。

**第五步：陈述失效条件**
什么情况下你的看空论点会被推翻？

请用 2-3 段落交付你的论点："""

        # System prompt: Role + Indicator manual (v3.25: regime-aware)
        # v3.28: Chinese instructions for better DeepSeek instruction-following
        system_prompt = f"""你是 {symbol} 的专业空头分析师 (Bear Analyst)。
你的职责是分析原始市场数据，构建最强有力的反对做多 (或支持做空) 的论据。

{INDICATOR_DEFINITIONS}

【关键规则 — 必须遵守】
⚠️ 你必须先判断 market regime (指标手册第一步)，然后用对应 regime 的规则解读所有指标。
⚠️ 在趋势市场使用震荡市场逻辑 (或反之) 是致命错误。
⚠️ 聚焦于数据中的风险和看空信号。"""

        # Store prompts for diagnosis (v11.4)
        self.last_prompts["bear"] = {
            "system": system_prompt,
            "user": prompt,
        }

        return self._call_api_with_retry([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ], trace_label=trace_label)

    def _get_judge_decision(
        self,
        debate_history: str,
        past_memories: str,
        key_metrics: str = "",
    ) -> Dict[str, Any]:
        """
        Judge evaluates the debate and makes decision.

        Borrowed from: TradingAgents/agents/managers/research_manager.py
        Simplified v3.0: Let AI autonomously evaluate without hardcoded rules
        v3.9: Removed duplicate S/R check from prompt (handled by _evaluate_risk)
        v3.10: Aligned with TradingAgents original design (rationale + strategic_actions)
        v3.23: Added key_metrics for independent sanity checking
        """
        prompt = f"""你是投资组合经理兼辩论裁判。请批判性地评估本轮辩论，做出明确的交易决策：
支持空头分析师、支持多头分析师、或仅在有强有力理由时选择 HOLD。

## 🗣️ DEBATE TRANSCRIPT
{debate_history}

## 📊 KEY MARKET METRICS (用于独立验证 — 检查分析师是否遗漏了什么)
{key_metrics if key_metrics else "N/A"}

## 📚 PAST REFLECTIONS ON MISTAKES
{past_memories if past_memories else "No past data - this is a fresh start."}

---

## 🎯 【决策任务 — 请严格按步骤执行】

### STEP 1: 独立验证 MARKET REGIME
用指标手册和 Key Metrics 独立判断当前 regime (TRENDING / RANGING / SQUEEZE)。
然后评估：双方分析师是否都使用了正确的 regime 解读逻辑？
⚠️ 在趋势市场使用震荡逻辑 (或反之) = 结论不可信。

### STEP 2: Confluence 多层对齐度评估
请用以下框架评估信号一致性：

| 层级 | 评估内容 | Bull 证据 | Bear 证据 | 哪方更强？ |
|------|---------|----------|----------|-----------|
| 趋势层 (1D) | SMA200, ADX/DI 方向 | ? | ? | ? |
| 动量层 (4H) | RSI, MACD, CVD | ? | ? | ? |
| 关键水平 (15M) | S/R zone, BB, Order Book | ? | ? | ? |
| 衍生品数据 | Funding, OI, Liquidations | ? | ? | ? |

对齐度评估：
- 3-4 层一致 → HIGH confidence 交易
- 2 层一致 → MEDIUM confidence 交易
- 0-1 层一致 → 应该 HOLD
- ‼️ 趋势层 (1D) 权重最高 — 与 1D 趋势矛盾的信号需要其他 3 层全部确认才可采纳

### STEP 3: 总结双方核心论据
聚焦最有说服力的证据，不要罗列所有观点。

### STEP 4: 做出明确决策
- 你的建议 — LONG、SHORT 或 HOLD — 必须清晰可执行
- ‼️ 不要因为双方都有道理就默认 HOLD — 选择证据更强的一方
- 参考过去的失误教训，避免重复犯错

## 📤 OUTPUT FORMAT (只输出 JSON，不要其他文字):
{{
    "decision": "LONG|SHORT|HOLD",
    "winning_side": "BULL|BEAR|TIE",
    "confidence": "HIGH|MEDIUM|LOW",
    "rationale": "Why these arguments lead to your conclusion (1-2 sentences)",
    "strategic_actions": ["Concrete step 1", "Concrete step 2"],
    "acknowledged_risks": ["risk1", "risk2"]
}}"""

        # v3.28: Chinese instructions + few-shot + confluence matrix for better DeepSeek performance
        system_prompt = f"""你是投资组合经理兼辩论裁判 (Portfolio Manager / Judge)。
批判性地评估辩论内容，做出果断的交易建议。选择证据更强的一方。从过去的错误中学习。

{INDICATOR_DEFINITIONS}

【关键规则 — 必须遵守】
⚠️ 用指标手册独立验证分析师是否使用了正确的 regime 解读。
⚠️ 用中文进行内部推理分析，最终以 JSON 格式输出结果。
⚠️ 不要因为双方都有道理就默认 HOLD — 这是最常见的错误。

【正确决策示例 — Few-shot】

示例 1: 趋势一致 → 选择顺势方
情况: 1D ADX=33 上涨趋势, Bull 引用趋势+动量, Bear 引用 RSI 超买
分析: ADX>25 = TRENDING。Bear 用震荡市场逻辑 (RSI 70 = 超买) 在趋势市场中是错误的。
      Cardwell 规则: 上涨趋势中 RSI 40-80 为正常范围，80 = 强动量。
结果: {{"decision":"LONG","winning_side":"BULL","confidence":"HIGH"}}

示例 2: 数据矛盾但趋势层主导
情况: 1D 强下跌趋势, 4H 出现 MACD 金叉, Bull 认为反转
分析: MACD 在震荡市场有 74-97% 假信号率。1D 强趋势未改变。
      4H MACD 金叉在强下跌趋势中更可能是反弹而非反转。
结果: {{"decision":"SHORT","winning_side":"BEAR","confidence":"MEDIUM"}}

示例 3: 真正需要 HOLD 的情况
情况: ADX=12 (RANGING), 价格在 range 中间, 两方都没有强证据
分析: 震荡市场 + 无明确方向 + 无关键水平触及。等待价格到达 range 边缘。
结果: {{"decision":"HOLD","winning_side":"TIE","confidence":"LOW"}}"""

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
            trace_label="Judge",
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

    def _build_key_metrics(
        self,
        technical_data: Optional[Dict] = None,
        derivatives_data: Optional[Dict] = None,
        order_flow_data: Optional[Dict] = None,
        current_price: float = 0.0,
        binance_derivatives_data: Optional[Dict] = None,
        sentiment_data: Optional[Dict] = None,
    ) -> str:
        """
        Build concise key metrics for Judge's independent sanity check (v3.23).

        v3.24: Expanded from ~8 to ~18 fields for comprehensive verification.
        Only includes raw numbers — no interpretation — so Judge can verify
        whether Bull/Bear analysts correctly used the data.
        """
        lines = []
        try:
            if current_price > 0:
                lines.append(f"Price: ${current_price:,.2f}")

            if technical_data and isinstance(technical_data, dict):
                # RSI
                rsi = technical_data.get('rsi')
                if rsi is not None:
                    lines.append(f"RSI: {rsi:.1f}")
                # ADX + DI+/DI- (v3.24: added DI for trend direction)
                adx = technical_data.get('adx')
                if adx is not None:
                    di_plus = technical_data.get('di_plus')
                    di_minus = technical_data.get('di_minus')
                    adx_str = f"ADX: {adx:.1f}"
                    if di_plus is not None and di_minus is not None:
                        adx_str += f" (DI+: {di_plus:.1f}, DI-: {di_minus:.1f})"
                    lines.append(adx_str)
                # MACD
                macd = technical_data.get('macd')
                macd_signal = technical_data.get('macd_signal')
                if macd is not None and macd_signal is not None:
                    lines.append(f"MACD: {macd:.2f} (signal: {macd_signal:.2f})")
                # v3.24: BB Position (where price sits within Bollinger Bands)
                bb_pos = technical_data.get('bb_position')
                if bb_pos is not None:
                    lines.append(f"BB Position: {bb_pos:.1%}")
                # v3.24: SMA positions relative to price
                # NOTE: These are 15M-based SMAs (SMA50 ≈ 12.5h, SMA200 ≈ 50h)
                # Daily SMA200 is in the 1D Timeframe section
                for period in [50, 200]:
                    sma_val = technical_data.get(f'sma_{period}')
                    if sma_val is not None and sma_val > 0 and current_price > 0:
                        pct = (current_price - sma_val) / sma_val * 100
                        lines.append(f"Price vs SMA{period}_15M: {pct:+.2f}%")
                # v3.24: Volume ratio
                vol_ratio = technical_data.get('volume_ratio')
                if vol_ratio is not None:
                    lines.append(f"Volume Ratio: {vol_ratio:.2f}x")

            if derivatives_data and isinstance(derivatives_data, dict):
                fr = derivatives_data.get('funding_rate', {})
                if isinstance(fr, dict):
                    fr_pct = fr.get('current_pct')
                    if fr_pct is not None:
                        predicted = fr.get('predicted_rate_pct')
                        fr_str = f"Funding Rate: {fr_pct:.4f}%"
                        if predicted is not None:
                            fr_str += f" (predicted: {predicted:.4f}%)"
                        lines.append(fr_str)
                liq = derivatives_data.get('liquidations', {})
                if isinstance(liq, dict) and liq.get('total_usd', 0) > 0:
                    lines.append(f"Liquidations (24h): ${liq['total_usd']:,.0f}")
                # v3.24: OI change
                oi = derivatives_data.get('open_interest', {})
                if isinstance(oi, dict):
                    oi_change = oi.get('change_pct')
                    if oi_change is not None:
                        lines.append(f"OI Change: {oi_change:+.2f}%")

            if order_flow_data and isinstance(order_flow_data, dict):
                buy_ratio = order_flow_data.get('buy_ratio')
                if buy_ratio is not None:
                    lines.append(f"Buy Ratio: {buy_ratio:.1%}")
                cvd = order_flow_data.get('cvd_trend')
                if cvd:
                    lines.append(f"CVD Trend: {cvd}")

            # v3.24: Binance derivatives (top traders)
            if binance_derivatives_data and isinstance(binance_derivatives_data, dict):
                top_pos = binance_derivatives_data.get('top_long_short_position', {})
                latest = top_pos.get('latest') if isinstance(top_pos, dict) else None
                if latest:
                    long_pct = float(latest.get('longAccount', 0.5)) * 100
                    lines.append(f"Top Traders Long: {long_pct:.1f}%")

            # v3.24: Sentiment
            if sentiment_data and isinstance(sentiment_data, dict):
                net = sentiment_data.get('net_sentiment')
                if net is not None:
                    try:
                        lines.append(f"Sentiment Net: {float(net):+.3f}")
                    except (ValueError, TypeError):
                        pass

        except Exception:
            pass

        return "\n".join(lines) if lines else "N/A"

    def _evaluate_risk(
        self,
        proposed_action: Dict[str, Any],
        technical_report: str,
        sentiment_report: str,
        current_position: Optional[Dict[str, Any]],
        current_price: float,
        technical_data: Optional[Dict[str, Any]] = None,
        account_context: Optional[Dict[str, Any]] = None,
        derivatives_report: str = "",
        order_flow_report: str = "",
        orderbook_report: str = "",
    ) -> Dict[str, Any]:
        """
        Final risk evaluation and position sizing.

        Borrowed from: TradingAgents/agents/risk_mgmt/conservative_debator.py
        Simplified v3.0: Let AI determine SL/TP based on market structure
        v3.7: Added BB position hardcoded checks for support/resistance risk control
        v3.8: Replaced BB-only check with multi-source S/R Zone check
        v3.11: Removed preset rules from prompt, let AI decide autonomously
        v4.6: Added account_context for position sizing decisions
        v3.22: Added derivatives_report for funding rate cost analysis
        v3.23: Added order_flow_report + orderbook_report for liquidity/slippage
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
## ‼️ 【S/R ZONE 风险警报 — 请务必评估】
⚠️ S/R ZONE PROXIMITY ALERT:
- 接近 HIGH 强度阻力位 (Near HIGH Strength RESISTANCE): {'**YES**' if block_long else 'No'}
- 接近 HIGH 强度支撑位 (Near HIGH Strength SUPPORT): {'**YES**' if block_short else 'No'}
- 详情 (Detail): {hc_reason if hc_reason else 'N/A'}

‼️ 评估要点:
- "HIGH 强度" = 多源确认 (Swing Point + Volume Profile + Pivot 共振)，历史反弹率较高
- 逆 HIGH 强度 zone 交易的成功率显著降低
- 但伴随放量的强力突破可能是强势信号
- 这是参考信息，不是硬性规则 — 请结合所有数据综合判断
"""

        prompt = f"""你是风险管理者 (Risk Manager)，负责为 Judge 的交易决策设定执行参数。
{hard_control_section}

## 📋 PROPOSED TRADE (Judge 建议 — 你必须尊重此方向)
- Action: {action}
- Confidence: {confidence}
- Rationale: {rationale}
- Strategic Actions: {actions_str}
- Acknowledged Risks: {', '.join(risks)}

## 📊 MARKET DATA
{technical_report}

{sentiment_report}

## 🔑 S/R ZONES
{sr_zones_for_risk}

## 📉 DERIVATIVES & FUNDING RATE
{derivatives_report if derivatives_report else "N/A"}

## 📈 ORDER FLOW & LIQUIDITY
{order_flow_report if order_flow_report else "N/A"}

{orderbook_report if orderbook_report else ""}

## 💼 CURRENT POSITION
{self._format_position(current_position)}

## 🏦 ACCOUNT CONTEXT
{self._format_account(account_context)}

**当前价格: ${current_price:,.2f}** (入场将以此价格执行，不是 S/R 价位)

---

## 🎯 【你的职责 — 只管风险，不管方向】

‼️ **核心原则**: Judge 已经听完 Bull/Bear 4 轮辩论后做出了方向决策。
你的工作不是重新判断方向，而是为这个方向设定最优的执行参数。

Judge 建议 {action} → 你的任务:
- 如果是 LONG/SHORT: 设定 SL/TP 价位 + 确定仓位大小
- 如果是 HOLD: 直接传递，signal = HOLD
- 如果是 CLOSE/REDUCE: 直接传递

### STEP 1: 计算 SL/TP
基于 S/R zones 和市场结构设定止损止盈：
- LONG: SL 在最近 SUPPORT 下方, TP 在最近 RESISTANCE
- SHORT: SL 在最近 RESISTANCE 上方, TP 在最近 SUPPORT
- 优先选择 HIGH 强度或有 ORDER_FLOW 确认的 zone
- ‼️ 最小 SL 距离 ≥ 1.0% (硬性门槛，低于此值会被系统拒绝)
- 参考 S/R Zone Proximity Alert（如有）作为 SL/TP 选择参考
- ‼️ **必须在 sl_zone 和 tp_zone 中标注你选择的 S/R zone** (如 "S1 $68,386 (HIGH)")
- ‼️ **必须在 rr_calculation 中展示计算过程** (如 "Risk=$500, Reward=$1,200, R/R=2.4:1")

⚠️ **S/R ZONE 宽度预检**:
- 计算最近 Support 和 Resistance 之间的价差百分比
- 如果 S/R 范围 < 2.5% 且价格在中间 → R/R 几乎不可能达标 → **直接 HOLD**
- 不要在窄幅 S/R 区间内强行设定 SL/TP，这会导致 SL 距离 < 1.0% 被系统拒绝
- 宁可 HOLD 等待价格接近 S/R zone 后再入场

### STEP 2: 评估 Risk/Reward
计算: Risk = |current_price - stop_loss|, Reward = |take_profit - current_price|, R/R = Reward / Risk

R/R 参考标准 (机构交易研究):
| R/R | 评价 | 仓位建议 |
|-----|------|---------|
| >= 2.5:1 | 优秀 | 80-100% |
| 2.0-2.5:1 | 良好 | 50-80% |
| 1.5-2.0:1 | 可接受 | 30-50% |
| < 1.5:1 | 不可接受 | → 改为 HOLD (⚠️ 这是唯一允许改方向的 R/R 条件) |

R/R 与价格位置的关系：
- 价格靠近 SUPPORT → LONG R/R 好 (小风险、大回报)
- 价格靠近 RESISTANCE → SHORT R/R 好
- 价格在中间 → 两个方向 R/R 都差

### STEP 3: 确定仓位大小
综合以下因素调整仓位大小 (不改变方向，只调大小):
- **R/R 质量**: R/R 越高可承受越大仓位
- **Regime 一致性**: 顺势交易 → 正常仓位; 逆势交易 → 缩小仓位 (但不改为 HOLD)
- **Funding Rate 成本**:
  - 每 8 小时结算一次，持仓直接成本
  - LONG 在 rate > 0 时付费, SHORT 在 rate < 0 时付费
  - 日成本估算 = |predicted_rate| × 3
  - |rate| < 0.03%: 正常 → 不影响仓位
  - |rate| 0.03-0.05%: 偏高 → 仓位 ×0.8
  - |rate| 0.05-0.10%: 高 → 仓位 ×0.5
  - |rate| > 0.10%: 极端 → ⚠️ 这是允许否决的条件 (见 STEP 4)
- **流动性和滑点**:
  - 检查 ORDER FLOW 和 ORDER BOOK 的执行风险
  - 预期滑点高 → 缩小仓位 (不改方向)
  - 大额挂单墙在入场方向上 → 缩小仓位 (不改方向)

### STEP 4: 检查是否触发紧急否决条件
⚠️ **只有以下极端情况才允许将 Judge 的 LONG/SHORT 改为 HOLD**:
1. R/R < 1.5:1 — 无法设定合理的 SL/TP
2. |Funding Rate| > 0.10% — 极端拥挤，成本过高
3. 流动性枯竭 — 预期滑点 > 50bps 且深度极低

‼️ 除了以上 3 个条件，**禁止**将 Judge 的方向改为 HOLD。
- BB 上轨/下轨 → 调仓位大小，不改方向
- 卖墙/买墙 → 调仓位大小，不改方向
- 逆势交易 → 缩小仓位，不改方向
- 资金费率 0.03-0.10% → 缩小仓位，不改方向
- 订单流不利 → 缩小仓位，不改方向

---

## 📋 SIGNAL TYPES
- **LONG**: 开新多仓或加仓
- **SHORT**: 开新空仓或加仓
- **CLOSE**: 完全平仓 (不开反向仓位)
- **HOLD**: 不操作，维持现状
- **REDUCE**: 减仓但保持方向 (设置较低的 position_size_pct)

## 📐 POSITION SIZE RULES
- position_size_pct: 目标仓位占最大允许仓位的百分比 (0-100)
- 100 = 全仓 (full position), 50 = 半仓 (half position), 0 = 清仓 (close all)
- REDUCE: 设为目标剩余大小 (如 50 = 减半)
- CLOSE: 设为 0

## 📤 OUTPUT FORMAT (只输出 JSON，不要其他文字):
{{
    "signal": "LONG|SHORT|CLOSE|HOLD|REDUCE",
    "confidence": "HIGH|MEDIUM|LOW",
    "risk_level": "LOW|MEDIUM|HIGH",
    "position_size_pct": <number 0-100>,
    "stop_loss": <price_number>,
    "take_profit": <price_number>,
    "sl_zone": "<which S/R zone the SL is based on, e.g. 'S1 $68,386 (HIGH)'>",
    "tp_zone": "<which S/R zone the TP is based on, e.g. 'R2 $71,200 (MEDIUM)'>",
    "rr_calculation": "<show math: Risk=$X, Reward=$Y, R/R=Z:1>",
    "reason": "<one sentence explaining the final decision>",
    "invalidation": "<specific condition that would prove this trade wrong>",
    "debate_summary": "<brief summary of bull vs bear debate>"
}}"""

        # v4.14: Risk Manager 角色重定义 — 只管风险不管方向
        # 旧版 (v3.28): Risk Manager 是独立决策者，经常否决 Judge → 过多 HOLD
        # 新版 (v4.14): Risk Manager 只设 SL/TP + 仓位大小，极端条件才否决
        system_prompt = f"""你是风险管理者 (Risk Manager)。
你的职责是为 Judge 的交易决策设定最优执行参数: SL/TP 价位和仓位大小。

{INDICATOR_DEFINITIONS}

【核心原则 — 必须遵守】
✅ **信任 Judge 的方向判断** — Judge 已听完 Bull/Bear 4 轮辩论后做出决策，你不需要重新判断方向。
✅ 你的工作: 设定 SL/TP + 根据风险条件调整仓位大小。
✅ 用风险因素（FR、流动性、OBI）来调整仓位大小，而不是否决方向。
⚠️ 只有 3 种极端情况才允许否决方向: R/R < 1.5:1 | |FR| > 0.10% | 流动性枯竭
⚠️ 用中文进行内部推理分析，最终以 JSON 格式输出结果。

【正确分析示例 — Few-shot】

示例 1: 顺势交易 → 设定 SL/TP + 大仓位
情况: ADX=35, DI+ > DI-, Judge 建议 LONG, 当前价 $95,500
你的工作: 设 SL/TP，不质疑方向。
分析: Support S1=$95,000 (HIGH), Resistance R1=$99,000 (MEDIUM)。
      SL=$94,500 (S1 下方), TP=$98,800 (R1 附近)。
      Risk=$1,000, Reward=$3,300, R/R=3.3:1 → 优秀。FR=0.01% 正常。流动性充足。
结果: {{"signal":"LONG","confidence":"HIGH","position_size_pct":85,"stop_loss":94500,"take_profit":98800,"sl_zone":"S1 $95,000 (HIGH)","tp_zone":"R1 $99,000 (MEDIUM)","rr_calculation":"Risk=$1,000, Reward=$3,300, R/R=3.3:1","reason":"顺势交易，R/R 3.3:1 优秀，FR 正常"}}

示例 2: R/R < 1.5:1 → 唯一允许否决的 R/R 条件
情况: Judge 建议 LONG, 当前价 $94,800, 价格在 range 中间
分析: S1=$93,500 (LOW), R1=$95,800 (MEDIUM)。
      SL=$93,500, TP=$95,800。Risk=$1,300, Reward=$1,000, R/R=0.77:1 → 远低于 1.5:1 门槛。
      无法设定合理的 SL/TP → 这是允许否决的条件。
结果: {{"signal":"HOLD","confidence":"LOW","position_size_pct":0,"sl_zone":"S1 $93,500 (LOW)","tp_zone":"R1 $95,800 (MEDIUM)","rr_calculation":"Risk=$1,300, Reward=$1,000, R/R=0.77:1","reason":"R/R 0.77:1 远低于 1.5:1 门槛，无法设定合理 SL/TP"}}

示例 3: 逆势交易 → 缩小仓位，不否决方向
情况: ADX=38 (STRONG TREND down, DI- > DI+), Judge 建议 LONG (逆势), 当前价 $95,000
你的工作: 尊重 Judge 的方向，但因逆势风险缩小仓位。
分析: S2=$94,000 (HIGH), R1=$96,500 (MEDIUM)。
      SL=$94,000 (S2 下方), TP=$96,500 (R1 附近)。
      Risk=$1,000, Reward=$1,500, R/R=1.5:1 → 达标。
      逆势交易风险更高 → 仓位缩小到 30%。FR=0.02% 正常。
结果: {{"signal":"LONG","confidence":"MEDIUM","position_size_pct":30,"stop_loss":94000,"take_profit":96500,"sl_zone":"S2 $94,000 (HIGH)","tp_zone":"R1 $96,500 (MEDIUM)","rr_calculation":"Risk=$1,000, Reward=$1,500, R/R=1.5:1","reason":"逆势交易但 R/R 1.5:1 达标，缩小仓位至 30% 控制风险"}}

示例 4: 极端资金费率 → 允许否决
情况: Judge 建议 LONG, FR=+0.12% (极端拥挤)
分析: |FR|=0.12% > 0.10% 极端阈值 → 触发紧急否决条件。
      日成本 0.36%，且极端拥挤暗示反转风险极高。
结果: {{"signal":"HOLD","confidence":"LOW","position_size_pct":0,"reason":"FR +0.12% 触发极端否决阈值 (>0.10%)，成本过高且拥挤风险极大"}}

示例 5: 各种风险因素 → 缩小仓位，不否决
情况: Judge 建议 LONG, 当前价 $67,200, BB上轨99%, 卖墙30x, FR=+0.06%, OBI=-0.8
你的工作: 这些是风险因素，用来调仓位大小，不是否决方向。
分析: S1=$66,800 (HIGH), R2=$68,300 (MEDIUM)。
      SL=$66,800 (S1 下方), TP=$68,300 (R2 附近)。
      Risk=$400, Reward=$1,100, R/R=2.75:1 → 优秀。
      BB 上轨 → 仓位 ×0.8。卖墙 → 仓位 ×0.8。FR 0.06% (偏高) → 仓位 ×0.5。
      综合: 基础仓位 70% × 0.5 = 35%。
结果: {{"signal":"LONG","confidence":"MEDIUM","position_size_pct":35,"stop_loss":66800,"take_profit":68300,"sl_zone":"S1 $66,800 (HIGH)","tp_zone":"R2 $68,300 (MEDIUM)","rr_calculation":"Risk=$400, Reward=$1,100, R/R=2.75:1","reason":"尊重 Judge 方向，因 FR 偏高+卖墙+BB 上轨缩小仓位至 35%"}}"""

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
            trace_label="Risk Manager",
        )

        if decision:
            decision["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            decision["debate_rounds"] = self.debate_rounds
            decision["judge_decision"] = proposed_action

            # v4.16: Reask mechanism — validate R/R before accepting SL/TP
            # Two-tier constraint model:
            #   Tier 1 (reask): R/R < 1.5 → reask once with specific feedback
            #   Tier 2 (pass): R/R >= 1.5 → accept as-is
            # Changed from v4.15: R/R < 1.0 now also triggers reask instead of
            # being silently skipped. This gives AI a chance to self-correct or
            # switch to HOLD, rather than wasting the signal.
            signal = decision.get("signal", "HOLD").upper()
            if signal in ("LONG", "SHORT", "BUY", "SELL"):
                rr_ratio = self._compute_rr_ratio(decision, current_price)
                decision["computed_rr"] = round(rr_ratio, 2)

                if 0 < rr_ratio < 1.5:
                    self.logger.info(
                        f"📊 R/R {rr_ratio:.2f}:1 < 1.5 — attempting reask for "
                        f"better SL/TP placement or HOLD decision."
                    )
                    decision = self._reask_rm_sltp(
                        decision=decision,
                        current_price=current_price,
                        system_prompt=system_prompt,
                        original_user_prompt=prompt,
                        sr_zones_summary=sr_zones_for_risk,
                    )
                    # Preserve metadata after reask
                    decision.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    decision.setdefault("debate_rounds", self.debate_rounds)
                    decision.setdefault("judge_decision", proposed_action)
                elif rr_ratio >= 1.5:
                    self.logger.info(f"📊 R/R {rr_ratio:.2f}:1 — passes threshold, no reask needed.")

            # v3.12: Normalize signal type (handle legacy BUY/SELL)
            decision = self._normalize_signal(decision)

            # Validate stop loss / take profit
            decision = self._validate_sl_tp(decision, current_price)

            return decision

        # Fallback if all retries failed
        self.logger.warning("Risk evaluation parsing failed after retries, using fallback")
        return self._create_fallback_signal({"price": current_price})

    def _compute_rr_ratio(self, decision: Dict[str, Any], current_price: float) -> float:
        """
        Compute the actual Risk/Reward ratio from RM's SL/TP output.

        Parameters
        ----------
        decision : Dict
            RM decision containing stop_loss and take_profit
        current_price : float
            Current market price

        Returns
        -------
        float
            R/R ratio (reward / risk), or 0.0 if invalid
        """
        signal = decision.get("signal", "HOLD").upper()
        if signal not in ("LONG", "SHORT", "BUY", "SELL"):
            return 0.0

        try:
            sl = float(decision.get("stop_loss", 0))
            tp = float(decision.get("take_profit", 0))
        except (ValueError, TypeError):
            return 0.0

        if sl <= 0 or tp <= 0 or current_price <= 0:
            return 0.0

        if signal in ("LONG", "BUY"):
            risk = current_price - sl
            reward = tp - current_price
        else:  # SHORT / SELL
            risk = sl - current_price
            reward = current_price - tp

        if risk <= 0:
            return 0.0

        return reward / risk

    def _reask_rm_sltp(
        self,
        decision: Dict[str, Any],
        current_price: float,
        system_prompt: str,
        original_user_prompt: str,
        sr_zones_summary: str,
    ) -> Dict[str, Any]:
        """
        Reask the Risk Manager with specific feedback when R/R is suboptimal (< 1.5).

        This implements the reask tier:
        - R/R >= 1.5: pass through (no reask needed)
        - R/R < 1.5: reask once with specific error feedback (AI can fix or switch to HOLD)

        Parameters
        ----------
        decision : Dict
            Initial RM decision with suboptimal R/R
        current_price : float
            Current market price
        system_prompt : str
            Original system prompt for RM
        original_user_prompt : str
            Original user prompt for RM
        sr_zones_summary : str
            S/R zones text for reference in reask

        Returns
        -------
        Dict
            Improved decision if reask succeeds, or original decision
        """
        signal = decision.get("signal", "HOLD").upper()
        sl = float(decision.get("stop_loss", 0))
        tp = float(decision.get("take_profit", 0))
        rr_ratio = self._compute_rr_ratio(decision, current_price)
        sl_zone = decision.get("sl_zone", "未指定")
        tp_zone = decision.get("tp_zone", "未指定")
        rr_calc = decision.get("rr_calculation", "未提供")

        # Build focused reask prompt
        if signal in ("LONG", "BUY"):
            direction_hint = (
                "LONG: SL 应在 SUPPORT 下方 (选择更远的 support 可缩小 risk)，"
                "TP 应在 RESISTANCE 附近 (选择更远的 resistance 可增大 reward)。"
            )
        else:
            direction_hint = (
                "SHORT: SL 应在 RESISTANCE 上方 (选择更近的 resistance 可缩小 risk)，"
                "TP 应在 SUPPORT 附近 (选择更远的 support 可增大 reward)。"
            )

        reask_prompt = f"""⚠️ **SL/TP 需要调整 — R/R 不达标**

你上一次输出的 SL/TP:
- Stop Loss: ${sl:,.2f} (基于: {sl_zone})
- Take Profit: ${tp:,.2f} (基于: {tp_zone})
- 你的计算: {rr_calc}
- **实际 R/R: {rr_ratio:.2f}:1** ← 低于 1.5:1 最低标准

当前价格: ${current_price:,.2f}
方向: {signal}

## 🔑 可用的 S/R ZONES (重新参考):
{sr_zones_summary if sr_zones_summary else "S/R 数据不可用"}

## 📐 调整方向:
{direction_hint}

## ✅ 要求:
1. 重新选择 SL/TP，使 R/R >= 1.5:1
2. SL 和 TP 必须基于具体的 S/R zone (在 sl_zone 和 tp_zone 中说明)
3. 在 rr_calculation 中展示完整计算过程
4. 如果确实无法达到 1.5:1 → 改为 HOLD

请重新输出完整 JSON (格式与之前相同)。"""

        self.logger.info(
            f"🔄 Reask RM: R/R {rr_ratio:.2f}:1 < 1.5:1, "
            f"SL=${sl:,.2f}, TP=${tp:,.2f}, signal={signal}"
        )

        # Make the reask API call
        reask_decision = self._extract_json_with_retry(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": original_user_prompt},
                {"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)},
                {"role": "user", "content": reask_prompt},
            ],
            temperature=0.1,  # Lower temperature for more focused correction
            max_json_retries=1,
            trace_label="Risk Manager (Reask)",
        )

        if reask_decision:
            new_rr = self._compute_rr_ratio(reask_decision, current_price)
            # v5.2: Use `or 0` to handle null SL/TP when RM returns HOLD
            # .get('stop_loss', 0) returns None when key exists with null value;
            # float(None) raises TypeError which propagated to analyze()'s
            # except block, replacing the real AI reason with fallback message.
            reask_sl = reask_decision.get('stop_loss') or 0
            reask_tp = reask_decision.get('take_profit') or 0
            self.logger.info(
                f"🔄 Reask result: R/R {new_rr:.2f}:1, "
                f"SL=${float(reask_sl):,.2f}, "
                f"TP=${float(reask_tp):,.2f}, "
                f"signal={reask_decision.get('signal', '?')}"
            )
            reask_decision["reask_applied"] = True
            reask_decision["original_rr"] = round(rr_ratio, 2)
            reask_decision["reask_rr"] = round(new_rr, 2)
            return reask_decision

        # Reask failed to produce valid JSON — return original
        self.logger.warning("Reask failed to produce valid JSON, keeping original decision")
        decision["reask_attempted"] = True
        decision["reask_failed"] = True
        return decision

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

        if signal in ("BUY", "LONG"):
            # For LONG: SL should be below entry, TP above
            sl_distance = (current_price - sl) / current_price if sl > 0 else 0

            if sl >= current_price:
                # Critical error: SL on wrong side - must fix
                decision["stop_loss"] = current_price * (1 - default_sl)
                self.logger.warning(f"Fixed LONG stop loss (wrong side): {sl} -> {decision['stop_loss']}")
            elif sl_distance < min_sl_distance:
                # v3.13: TradingAgents style - warn but trust AI's S/R-based decision
                # The AI was prompted to consider volatility and R/R ratio
                self.logger.info(
                    f"📍 LONG stop loss is close ({sl_distance*100:.2f}%) - "
                    f"trusting AI's S/R-based SL: ${sl:,.2f}"
                )
                decision["sl_warning"] = f"SL distance {sl_distance*100:.2f}% is below recommended {min_sl_distance*100:.1f}%"

            if tp <= current_price:
                decision["take_profit"] = current_price * (1 + default_tp_buy)
                self.logger.warning(f"Fixed LONG take profit: {tp} -> {decision['take_profit']}")

        elif signal in ("SELL", "SHORT"):
            # For SHORT: SL should be above entry, TP below
            sl_distance = (sl - current_price) / current_price if sl > 0 else 0

            if sl <= current_price:
                # Critical error: SL on wrong side - must fix
                decision["stop_loss"] = current_price * (1 + default_sl)
                self.logger.warning(f"Fixed SHORT stop loss (wrong side): {sl} -> {decision['stop_loss']}")
            elif sl_distance < min_sl_distance:
                # v3.13: TradingAgents style - warn but trust AI's S/R-based decision
                self.logger.info(
                    f"📍 SHORT stop loss is close ({sl_distance*100:.2f}%) - "
                    f"trusting AI's S/R-based SL: ${sl:,.2f}"
                )
                decision["sl_warning"] = f"SL distance {sl_distance*100:.2f}% is below recommended {min_sl_distance*100:.1f}%"

            if tp >= current_price:
                decision["take_profit"] = current_price * (1 - default_tp_sell)
                self.logger.warning(f"Fixed SHORT take profit: {tp} -> {decision['take_profit']}")

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

TREND STRENGTH (ADX):
- ADX(14): {safe_get('adx'):.1f} ({data.get('adx_regime', 'N/A')})
- DI+: {safe_get('di_plus'):.1f}, DI-: {safe_get('di_minus'):.1f} → {data.get('adx_direction', 'N/A')} direction
- S/R Reliability: {"HIGH (~70% bounce rate, mean-reversion reliable)" if safe_get('adx') < 20 else "MODERATE (~50% bounce rate, confirm with volume)" if safe_get('adx') < 25 else "LOW (~25% bounce rate, S/R breakouts frequent)" if safe_get('adx') < 40 else "VERY LOW (<25% bounce rate, counter-trend S/R historically poor)"}
- Note: ADX < 20 = ranging (S/R bounces ~70% reliable), ADX > 30 = strong trend (S/R bounces ~25% reliable)

VOLATILITY (Bollinger Bands):
- Upper: ${safe_get('bb_upper'):,.2f}
- Middle: ${safe_get('bb_middle'):,.2f}
- Lower: ${safe_get('bb_lower'):,.2f}
- Position: {safe_get('bb_position') * 100:.1f}% (0%=Lower Band, 100%=Upper Band)

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
- Position: {mtf_safe_get('bb_position') * 100:.1f}% (0%=Lower, 100%=Upper)
"""

        # Add 1D trend layer data if available (MTF v3.5)
        mtf_trend = data.get('mtf_trend_layer')
        if mtf_trend:
            def trend_safe_get(key, default=0):
                val = mtf_trend.get(key)
                return float(val) if val is not None else default

            # v3.25: 增加 1D RSI + ADX
            trend_rsi = trend_safe_get('rsi')
            trend_adx = trend_safe_get('adx')
            trend_di_plus = trend_safe_get('di_plus')
            trend_di_minus = trend_safe_get('di_minus')
            trend_adx_regime = mtf_trend.get('adx_regime', 'UNKNOWN')

            report += f"""
=== MARKET DATA (1D Timeframe - Macro Trend) ===

TREND INDICATORS (1D):
- SMA 200: ${trend_safe_get('sma_200'):,.2f}
- Price vs SMA_200: {'+' if data.get('price', 0) > trend_safe_get('sma_200') else ''}{((data.get('price', 0) / trend_safe_get('sma_200') - 1) * 100) if trend_safe_get('sma_200') > 0 else 0:.2f}%
- MACD: {trend_safe_get('macd'):.4f}
- MACD Signal: {trend_safe_get('macd_signal'):.4f}
- RSI(14): {trend_rsi:.1f}
- ADX(14): {trend_adx:.1f} ({trend_adx_regime}) | DI+ {trend_di_plus:.1f} / DI- {trend_di_minus:.1f}
"""

        # Add historical context if available (EVALUATION_FRAMEWORK v3.0.1)
        # v3.21: Show ALL values (not truncated to 5) for better AI trend analysis
        historical = data.get('historical_context')
        if historical and historical.get('trend_direction') not in ['INSUFFICIENT_DATA', 'ERROR', None]:
            trend_dir = historical.get('trend_direction', 'N/A')
            momentum = historical.get('momentum_shift', 'N/A')
            price_change = historical.get('price_change_pct', 0)
            vol_ratio = historical.get('current_volume_ratio', 1.0)

            # v3.21: Format ALL values (full time-series for AI pattern recognition)
            def format_all_values(values, fmt=".1f"):
                if not values or not isinstance(values, list):
                    return "N/A"
                return " → ".join([f"{v:{fmt}}" for v in values])

            price_trend = historical.get('price_trend', [])
            rsi_trend = historical.get('rsi_trend', [])
            macd_trend = historical.get('macd_trend', [])
            volume_trend = historical.get('volume_trend', [])
            n_bars = len(price_trend)
            hours_covered = n_bars * 15 / 60  # 15min bars → hours

            report += f"""
=== HISTORICAL CONTEXT (Last {n_bars} bars, ~{hours_covered:.1f} hours) ===

TREND ANALYSIS:
- Overall Direction: {trend_dir}
- Momentum Shift: {momentum}
- Price Change: {price_change:+.2f}% over {n_bars} bars
- Current Volume vs Avg: {vol_ratio:.2f}x

PRICE SERIES ({n_bars} bars, 15min each):
{format_all_values(price_trend, ",.0f")}

RSI SERIES ({len(rsi_trend)} values):
{format_all_values(rsi_trend)}

MACD SERIES ({len(macd_trend)} values):
{format_all_values(macd_trend, ".4f")}

VOLUME SERIES ({len(volume_trend)} values, BTC):
{format_all_values(volume_trend, ",.1f")}
"""
            # v3.24: ADX/DI history (trend strength trajectory)
            adx_trend = historical.get('adx_trend', [])
            di_plus_trend = historical.get('di_plus_trend', [])
            di_minus_trend = historical.get('di_minus_trend', [])
            if adx_trend and len(adx_trend) >= 2:
                report += f"""
ADX SERIES ({len(adx_trend)} values):
{format_all_values(adx_trend)}

DI+ SERIES:
{format_all_values(di_plus_trend)}

DI- SERIES:
{format_all_values(di_minus_trend)}
"""

            # v3.24: BB Width history (volatility squeeze/expansion)
            bb_width_trend = historical.get('bb_width_trend', [])
            if bb_width_trend and len(bb_width_trend) >= 2:
                report += f"""
BB WIDTH SERIES ({len(bb_width_trend)} values, % of middle band):
{format_all_values(bb_width_trend, ".2f")}
"""

            # v3.24: SMA history for crossover detection
            sma_history = historical.get('sma_history', {})
            if sma_history:
                report += "\nSMA SERIES (for crossover detection):\n"
                for sma_key, sma_vals in sorted(sma_history.items()):
                    if sma_vals and len(sma_vals) >= 2:
                        report += f"{sma_key.upper()} ({len(sma_vals)} values): {format_all_values(sma_vals, ',.0f')}\n"

        # v3.21: Add K-line OHLCV data (让 AI 看到实际价格形态)
        kline_ohlcv = data.get('kline_ohlcv')
        if kline_ohlcv and isinstance(kline_ohlcv, list) and len(kline_ohlcv) > 0:
            from datetime import datetime
            n_klines = len(kline_ohlcv)
            report += f"""
=== K-LINE OHLCV DATA (Last {n_klines} bars, 15min) ===
"""
            report += "Time            | Open      | High      | Low       | Close     | Volume\n"
            report += "-" * 85 + "\n"
            for bar in kline_ohlcv:
                ts = bar.get('timestamp', 0)
                try:
                    # NautilusTrader ts_init is in nanoseconds
                    time_str = datetime.utcfromtimestamp(ts / 1e9).strftime('%m-%d %H:%M') if ts > 1e15 else (
                        datetime.utcfromtimestamp(ts / 1000).strftime('%m-%d %H:%M') if ts > 1e10 else
                        datetime.utcfromtimestamp(ts).strftime('%m-%d %H:%M') if ts > 0 else "N/A"
                    )
                except (OSError, ValueError):
                    time_str = "N/A"
                o = bar.get('open', 0)
                h = bar.get('high', 0)
                l = bar.get('low', 0)
                c = bar.get('close', 0)
                v = bar.get('volume', 0)
                report += f"{time_str:<15} | ${o:>8,.0f} | ${h:>8,.0f} | ${l:>8,.0f} | ${c:>8,.0f} | {v:>8,.1f}\n"

        return report

    def _format_sentiment_report(self, data: Optional[Dict[str, Any]]) -> str:
        """Format sentiment data for prompts.

        TradingAgents v3.3: Pass raw ratios only, no interpretation.
        v3.24: Added history series for continuous data.
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

        lines = [
            "MARKET SENTIMENT (Binance Long/Short Ratio):",
            f"- Long Ratio: {pos_ratio:.1%}",
            f"- Short Ratio: {neg_ratio:.1%}",
            f"- Net: {sign}{net:.3f}",
        ]

        # v3.24: Show history series (oldest → newest)
        history = data.get('history', [])
        if history and len(history) >= 2:
            long_series = [f"{h['long']*100:.1f}%" for h in history]
            ratio_series = [f"{h['ratio']:.3f}" for h in history]
            lines.append(f"- Long% History: {' → '.join(long_series)}")
            lines.append(f"- L/S Ratio History: {' → '.join(ratio_series)}")

        return "\n" + "\n".join(lines) + "\n"

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

        # v5.1: Funding Rate section (settled + predicted)
        lines.append("Funding Rate Impact:")
        if funding_rate_current is not None:
            fr_pct = funding_rate_current * 100
            fr_emoji = "🔴" if fr_pct > 0.01 else "🟢" if fr_pct < -0.01 else "⚪"
            lines.append(f"  Last Settled Rate: {fr_emoji} {fr_pct:.4f}% per 8h")
            if daily_funding_cost is not None:
                lines.append(f"  Estimated Daily Cost: ${daily_funding_cost:.2f}")
            if funding_rate_cumulative_usd is not None:
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

        v5.1: Enhanced with trade grades and R/R data for deeper pattern learning.
        """
        if not self.decision_memory:
            return ""

        # Separate successes and failures
        successes = [m for m in self.decision_memory if m.get('pnl', 0) > 0]
        failures = [m for m in self.decision_memory if m.get('pnl', 0) <= 0]

        # Take most recent 5 of each (increased from 3 for richer patterns)
        recent_successes = successes[-5:] if successes else []
        recent_failures = failures[-5:] if failures else []

        lines = []

        if recent_successes:
            lines.append("SUCCESSFUL TRADES (learn from these):")
            for mem in recent_successes:
                conditions = mem.get('conditions', 'N/A')
                ev = mem.get('evaluation', {})
                grade = ev.get('grade', '')
                rr_str = f" R/R={ev.get('actual_rr', 0):.1f}:1" if ev else ""
                grade_str = f" [{grade}]" if grade else ""
                lines.append(
                    f"  ✅ {mem.get('decision')} → {mem.get('pnl', 0):+.2f}%{grade_str}{rr_str} | "
                    f"Conditions: {conditions}"
                )

        if recent_failures:
            lines.append("FAILED TRADES (avoid repeating):")
            for mem in recent_failures:
                conditions = mem.get('conditions', 'N/A')
                lesson = mem.get('lesson', 'N/A')
                ev = mem.get('evaluation', {})
                grade = ev.get('grade', '')
                exit_type = ev.get('exit_type', '')
                grade_str = f" [{grade}]" if grade else ""
                exit_str = f" via {exit_type}" if exit_type else ""
                lines.append(
                    f"  ❌ {mem.get('decision')} → {mem.get('pnl', 0):+.2f}%{grade_str}{exit_str} | "
                    f"Conditions: {conditions} | Lesson: {lesson}"
                )

        # v5.1: Add aggregate stats if enough evaluated trades
        evaluated = [m for m in self.decision_memory if m.get('evaluation')]
        if len(evaluated) >= 5:
            grades = [m['evaluation'].get('grade', '?') for m in evaluated[-20:]]
            grade_counts = {}
            for g in grades:
                grade_counts[g] = grade_counts.get(g, 0) + 1
            grade_summary = " ".join(f"{g}:{c}" for g, c in sorted(grade_counts.items()))

            correct = sum(1 for m in evaluated[-20:] if m['evaluation'].get('direction_correct'))
            total = len(evaluated[-20:])
            accuracy = round(correct / total * 100) if total > 0 else 0

            lines.append(f"\nTRADE QUALITY (last {total}): {grade_summary} | Direction accuracy: {accuracy}%")

        return "\n".join(lines)

    def record_outcome(
        self,
        decision: str,
        pnl: float,
        conditions: str = "",
        lesson: str = "",
        evaluation: Optional[Dict[str, Any]] = None,
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
        evaluation : Dict, optional
            Trade evaluation data from trading_logic.evaluate_trade()
            Contains: grade, direction_correct, actual_rr, planned_rr,
            execution_quality, exit_type, hold_duration_min, etc.
        """
        # v5.1: Auto-generate lesson based on evaluation grade (if available)
        if not lesson and evaluation:
            grade = evaluation.get('grade', '')
            actual_rr = evaluation.get('actual_rr', 0)
            exit_type = evaluation.get('exit_type', '')
            if grade in ('A+', 'A'):
                lesson = f"Grade {grade}: Strong win (R/R {actual_rr:.1f}:1) - repeat this pattern"
            elif grade == 'B':
                lesson = f"Grade B: Acceptable profit (R/R {actual_rr:.1f}:1)"
            elif grade == 'C':
                lesson = f"Grade C: Small profit but low R/R ({actual_rr:.1f}:1) - tighten entry"
            elif grade == 'D':
                lesson = f"Grade D: Controlled loss via {exit_type} - discipline maintained"
            elif grade == 'F':
                lesson = f"Grade F: Uncontrolled loss - review SL placement"

        # Fallback to original lesson generation
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

        entry = {
            "decision": decision,
            "pnl": round(pnl, 2),
            "conditions": conditions,
            "lesson": lesson,
            "timestamp": datetime.now().isoformat(),
        }

        # v5.1: Attach evaluation data if provided
        if evaluation:
            entry["evaluation"] = evaluation

        self.decision_memory.append(entry)

        # v5.1: Increased from 50 to 500 for better statistical analysis
        if len(self.decision_memory) > 500:
            self.decision_memory.pop(0)

        # Persist to file
        self._save_memory()

        grade_str = f" [Grade: {evaluation.get('grade', '?')}]" if evaluation else ""
        self.logger.info(
            f"📝 Recorded: {decision} → {pnl:+.2f}%{grade_str} | "
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

    def get_call_trace(self) -> List[Dict[str, Any]]:
        """
        Return the full call trace for the last analysis cycle.

        Each entry contains:
        - messages: List[Dict] (system + user prompts sent to API)
        - temperature: float
        - response: str (full API response)
        - elapsed_sec: float
        - tokens: Dict with prompt/completion/total counts
        """
        return self.call_trace

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
        cvd_trend = data.get('cvd_trend', 'N/A')
        recent_bars = data.get('recent_10_bars', [])

        # Format recent bars (raw data only, AI infers trend)
        recent_str = ", ".join([f"{r:.1%}" for r in recent_bars]) if recent_bars else "N/A"

        # v5.1: Compute buy ratio range statistics for microstructure analysis
        # Helps AI detect: compression (low range → breakout imminent),
        # anomalies (extreme values → potential spoofing/wash), one-sided flow
        range_stats = ""
        if recent_bars and len(recent_bars) >= 3:
            br_min = min(recent_bars)
            br_max = max(recent_bars)
            br_range = br_max - br_min
            br_std = (sum((r - buy_ratio) ** 2 for r in recent_bars) / len(recent_bars)) ** 0.5
            range_stats = (
                f"- Buy Ratio Range: {br_min:.1%}-{br_max:.1%} "
                f"(spread={br_range:.1%}, stddev={br_std:.1%})\n"
            )

        # v5.2: Added CVD numerical history (was trend-only — AI needs magnitude)
        cvd_history = data.get('cvd_history', [])
        cvd_cumulative = data.get('cvd_cumulative', 0)
        cvd_history_str = ", ".join([f"{v:+,.0f}" for v in cvd_history]) if cvd_history else "N/A"

        # v5.3: Cold start warning when insufficient CVD history
        cvd_warning = ""
        if len(cvd_history) < 3:
            cvd_warning = " ⚠️ COLD_START (< 3 bars, trend unreliable)"

        return f"""
ORDER FLOW (Binance Taker Data):
- Buy Ratio (10-bar avg): {buy_ratio:.1%}
{range_stats}- CVD Trend: {cvd_trend}{cvd_warning}
- CVD History (last {len(cvd_history)} bars): [{cvd_history_str}]
- CVD Cumulative: {cvd_cumulative:+,.0f}
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
            Coinalyze derivatives data (OI, liquidations) + Binance funding rate
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
        # Section 1: Derivatives Data (OI/Liq from Coinalyze, FR from Binance)
        # =========================================================================
        if data and data.get('enabled', True):
            parts.append("DERIVATIVES DATA:")

            # Open Interest (v5.2: add hourly history series for OI×Price analysis)
            trends = data.get('trends', {})
            oi = data.get('open_interest')
            if oi:
                try:
                    oi_btc = float(oi.get('value', 0) or 0)
                except (ValueError, TypeError):
                    oi_btc = 0.0
                oi_trend = trends.get('oi_trend', 'N/A')
                parts.append(f"- Open Interest: {oi_btc:,.2f} BTC (Trend: {oi_trend})")

                # v5.2: OI hourly history (price divergence analysis)
                oi_hist = data.get('open_interest_history')
                if oi_hist and oi_hist.get('history'):
                    oi_closes = [float(h.get('c', 0)) for h in oi_hist['history']]
                    if len(oi_closes) >= 2:
                        oi_series_str = " → ".join([f"{v:,.0f}" for v in oi_closes])
                        oi_change = oi_closes[-1] - oi_closes[0]
                        oi_change_pct = (oi_change / oi_closes[0] * 100) if oi_closes[0] != 0 else 0
                        parts.append(f"  OI History ({len(oi_closes)}h): {oi_series_str}")
                        parts.append(f"  OI Change: {oi_change:+,.0f} BTC ({oi_change_pct:+.2f}%)")
            else:
                parts.append("- Open Interest: N/A")

            # Funding Rate (v5.2: use current_pct directly from Binance, no manual *100)
            funding = data.get('funding_rate')
            if funding:
                # 已结算费率 (from Binance /fapi/v1/fundingRate, already in % form)
                settled_pct = 0.0
                try:
                    # Prefer current_pct (already in percentage), fall back to value * 100
                    raw_pct = funding.get('current_pct') or funding.get('settled_pct')
                    if raw_pct is not None:
                        settled_pct = float(raw_pct)
                    else:
                        settled_pct = float(funding.get('value', 0) or 0) * 100
                except (ValueError, TypeError):
                    settled_pct = 0.0
                parts.append(f"- Last Settled Funding Rate: {settled_pct:.4f}%")

                # 预期费率 (from premiumIndex.lastFundingRate, 实时变化)
                predicted_pct = funding.get('predicted_rate_pct')
                if predicted_pct is not None:
                    parts.append(f"- Predicted Next Funding Rate: {predicted_pct:.4f}%")
                    # v5.2: Settled vs Predicted delta (key sentiment shift signal)
                    delta_pct = predicted_pct - settled_pct
                    direction = "↑ more bullish pressure" if delta_pct > 0 else "↓ more bearish pressure" if delta_pct < 0 else "→ stable"
                    parts.append(f"- Funding Delta (Predicted - Settled): {delta_pct:+.4f}% ({direction})")

                # 溢价指数 (瞬时值)
                premium_index = funding.get('premium_index')
                if premium_index is not None:
                    pi_pct = premium_index * 100
                    mark = funding.get('mark_price', 0)
                    index = funding.get('index_price', 0)
                    parts.append(
                        f"- Premium Index: {pi_pct:+.4f}% "
                        f"(Mark: ${mark:,.2f}, Index: ${index:,.2f})"
                    )

                # 下次结算倒计时
                countdown = funding.get('next_funding_countdown_min')
                if countdown is not None:
                    hours = countdown // 60
                    mins = countdown % 60
                    parts.append(f"- Next Settlement: {hours}h {mins}m")

                # 结算历史 (最近 10 次 = ~3.3 天)
                history = funding.get('history', [])
                if history and len(history) >= 2:
                    rates_str = " → ".join(
                        [f"{r['rate_pct']:.4f}%" for r in history]
                    )
                    parts.append(f"- Funding History (last {len(history)}): {rates_str}")

                    # 趋势
                    trend = funding.get('trend', 'N/A')
                    if trend != 'N/A':
                        parts.append(f"- Funding Trend: {trend}")
            else:
                parts.append("- Funding Rate: N/A")

            # Liquidations (v3.24: expanded to 24h with history trend)
            liq = data.get('liquidations')
            if liq:
                history = liq.get('history', [])
                if history:
                    price_for_conversion = current_price if current_price > 0 else 88000

                    # Calculate 24h totals
                    total_long_btc = sum(float(h.get('l', 0)) for h in history)
                    total_short_btc = sum(float(h.get('s', 0)) for h in history)
                    total_btc = total_long_btc + total_short_btc
                    total_usd = total_btc * price_for_conversion

                    parts.append(f"- Liquidations (24h): {total_btc:.4f} BTC (${total_usd:,.0f})")
                    if total_btc > 0:
                        long_ratio = total_long_btc / total_btc
                        parts.append(f"  - Long Liq: {total_long_btc:.4f} BTC ({long_ratio:.0%})")
                        parts.append(f"  - Short Liq: {total_short_btc:.4f} BTC ({1-long_ratio:.0%})")

                    # v3.24: Show hourly history (oldest → newest) for trend
                    if len(history) >= 3:
                        hourly_totals = []
                        for h in history:
                            h_total = float(h.get('l', 0)) + float(h.get('s', 0))
                            h_usd = h_total * price_for_conversion
                            hourly_totals.append(f"${h_usd:,.0f}")
                        parts.append(f"  Hourly Trend: {' → '.join(hourly_totals)}")
                else:
                    parts.append("- Liquidations (24h): N/A")
            else:
                parts.append("- Liquidations (24h): N/A")

            # Long/Short Ratio from Coinalyze (v3.26: restored trend for single-snapshot context)
            ls_hist = data.get('long_short_ratio_history')
            if ls_hist and ls_hist.get('history'):
                latest = ls_hist['history'][-1]
                ls_ratio = float(latest.get('r', 1))
                long_pct = float(latest.get('l', 50))
                short_pct = float(latest.get('s', 50))
                ls_trend = trends.get('long_short_trend', 'N/A')
                parts.append(
                    f"- Long/Short Ratio: {ls_ratio:.2f} (Long {long_pct:.1f}% / Short {short_pct:.1f}%) "
                    f"(Trend: {ls_trend})"
                )
        else:
            parts.append("COINALYZE: Data not available")

        # =========================================================================
        # Section 2: Binance Derivatives (Unique Data)
        # v3.24: Unhide full history series (previously only showed latest)
        # =========================================================================
        if binance_derivatives:
            parts.append("\nBINANCE DERIVATIVES (Top Traders & Taker):")

            # Top Traders Position Ratio — with full history series
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
                # v3.24: Show history series
                history = top_pos.get('data', [])
                if history and len(history) >= 2:
                    ratios = [f"{float(h.get('longAccount', 0.5))*100:.1f}%" for h in reversed(history)]
                    parts.append(f"  History (Long%): {' → '.join(ratios)}")

            # Taker Buy/Sell Ratio — with full history series
            taker = binance_derivatives.get('taker_long_short', {})
            latest = taker.get('latest')
            if latest:
                ratio = float(latest.get('buySellRatio', 1))
                parts.append(f"- Taker Buy/Sell Ratio: {ratio:.3f}")
                # v3.24: Show history series
                history = taker.get('data', [])
                if history and len(history) >= 2:
                    ratios = [f"{float(h.get('buySellRatio', 1)):.3f}" for h in reversed(history)]
                    parts.append(f"  History: {' → '.join(ratios)}")

            # OI from Binance — with full history series
            oi_hist = binance_derivatives.get('open_interest_hist', {})
            latest = oi_hist.get('latest')
            if latest:
                oi_usd = float(latest.get('sumOpenInterestValue', 0))
                parts.append(f"- OI (Binance): ${oi_usd:,.0f}")
                # v3.24: Show history series
                history = oi_hist.get('data', [])
                if history and len(history) >= 2:
                    oi_values = [f"${float(h.get('sumOpenInterestValue', 0))/1e9:.2f}B" for h in reversed(history)]
                    parts.append(f"  History: {' → '.join(oi_values)}")

                    # v5.3: OI×Price 4-Quadrant analysis
                    # (Price ↑+OI ↑=New longs, Price ↑+OI ↓=Short covering,
                    #  Price ↓+OI ↑=New shorts, Price ↓+OI ↓=Long liquidation)
                    ticker_data = binance_derivatives.get('ticker_24hr')
                    if ticker_data and current_price > 0:
                        price_change = float(ticker_data.get('priceChangePercent', 0))
                        oldest_oi = float(history[-1].get('sumOpenInterestValue', 0))
                        newest_oi = float(history[0].get('sumOpenInterestValue', 0))
                        if oldest_oi > 0:
                            oi_change_pct = (newest_oi - oldest_oi) / oldest_oi * 100
                            price_dir = "↑" if price_change > 0.1 else "↓" if price_change < -0.1 else "→"
                            oi_dir = "↑" if oi_change_pct > 0.5 else "↓" if oi_change_pct < -0.5 else "→"
                            quadrant_map = {
                                ("↑", "↑"): "New longs entering → BULLISH CONFIRMATION",
                                ("↑", "↓"): "Short covering → WEAK rally (no new conviction)",
                                ("↓", "↑"): "New shorts entering → BEARISH CONFIRMATION",
                                ("↓", "↓"): "Long liquidation → BEARISH EXHAUSTION",
                            }
                            signal = quadrant_map.get(
                                (price_dir, oi_dir),
                                f"Price {price_dir} + OI {oi_dir} = Neutral / consolidation"
                            )
                            parts.append(
                                f"  OI×Price: Price {price_dir}{price_change:+.1f}% + "
                                f"OI {oi_dir}{oi_change_pct:+.1f}% = {signal}"
                            )

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
        bars_data: Optional[List[Dict[str, Any]]] = None,
        bars_data_4h: Optional[List[Dict[str, Any]]] = None,
        bars_data_1d: Optional[List[Dict[str, Any]]] = None,
        daily_bar: Optional[Dict[str, Any]] = None,
        weekly_bar: Optional[Dict[str, Any]] = None,
        atr_value: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Calculate S/R Zones from multiple data sources (v3.0, v4.0).

        Combines:
        - Bollinger Bands (BB Upper/Lower)
        - SMA (SMA_50, SMA_200)
        - Order Book Walls (bid/ask anomalies)
        - v3.0: Swing Points (from OHLC bars)
        - v3.0: ATR-adaptive clustering
        - v3.0: Touch Count scoring
        - v4.0: MTF swing detection (4H, 1D)
        - v4.0: Pivot Points (Daily + Weekly)
        - v4.0: Volume Profile (VPOC, VAH, VAL)

        Parameters
        ----------
        current_price : float
            Current market price
        technical_data : Dict, optional
            Technical indicator data containing BB and SMA values
        orderbook_data : Dict, optional
            Order book data containing anomalies (walls)
        bars_data : List[Dict], optional
            v3.0: OHLC bar data for swing detection and touch count
            [{'high': float, 'low': float, 'close': float}, ...]
        bars_data_4h : List[Dict], optional
            v4.0: 4H OHLCV bars for MTF swing detection
        bars_data_1d : List[Dict], optional
            v4.0: 1D OHLCV bars for MTF swing detection
        daily_bar : Dict, optional
            v4.0: Most recent completed daily bar for pivot calculation
        weekly_bar : Dict, optional
            v4.0: Aggregated weekly bar for pivot calculation
        atr_value : float, optional
            v4.0: ATR value for buffer calculation

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

        # Calculate S/R zones with detailed report (v3.0: bars_data for swing/touch)
        # v4.0: Pass MTF bars for pivot points + volume profile
        try:
            result = self.sr_calculator.calculate_with_detailed_report(
                current_price=current_price,
                bb_data=bb_data,
                sma_data=sma_data,
                orderbook_anomalies=orderbook_anomalies,
                bars_data=bars_data,
                bars_data_4h=bars_data_4h,
                bars_data_1d=bars_data_1d,
                daily_bar=daily_bar,
                weekly_bar=weekly_bar,
                atr_value=atr_value,
            )

            # Log S/R zone detection
            if result.get('nearest_resistance'):
                r = result['nearest_resistance']
                swing_tag = " [Swing]" if r.has_swing_point else ""
                touch_tag = f" [T:{r.touch_count}]" if r.touch_count > 0 else ""
                self.logger.debug(
                    f"S/R Zone: Nearest Resistance ${r.price_center:,.0f} "
                    f"({r.distance_pct:.1f}% away) [{r.strength}]{swing_tag}{touch_tag}"
                )
            if result.get('nearest_support'):
                s = result['nearest_support']
                swing_tag = " [Swing]" if s.has_swing_point else ""
                touch_tag = f" [T:{s.touch_count}]" if s.touch_count > 0 else ""
                self.logger.debug(
                    f"S/R Zone: Nearest Support ${s.price_center:,.0f} "
                    f"({s.distance_pct:.1f}% away) [{s.strength}]{swing_tag}{touch_tag}"
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
            parts.append("  [First snapshot - no historical data yet] ⚠️ COLD_START (dynamics available after 2nd cycle)")
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
                amount = _safe_float(anom.get('volume_btc', anom.get('amount', 0)))
                multiple = _safe_float(anom.get('multiplier', anom.get('multiple', 0)))
                parts.append(f"  Bid: ${price:,.0f} @ {amount:.1f} BTC ({multiple:.1f}x)")
            for anom in ask_anomalies[:3]:
                price = _safe_float(anom.get('price', 0))
                amount = _safe_float(anom.get('volume_btc', anom.get('amount', 0)))
                multiple = _safe_float(anom.get('multiplier', anom.get('multiple', 0)))
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
