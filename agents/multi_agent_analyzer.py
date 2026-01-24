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
        """
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.temperature = temperature
        self.debate_rounds = debate_rounds

        # Setup logger
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Memory for learning from past decisions (borrowed from TradingAgents)
        self.decision_memory: List[Dict] = []

        # Track debate history for debugging
        self.last_debate_transcript: str = ""

        # Retry configuration (same as DeepSeekAnalyzer)
        self.max_retries = 2
        self.retry_delay = 1.0

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

            # Get current price for calculations
            current_price = price_data.get('price', 0) if price_data else technical_report.get('price', 0)

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
                    history=debate_history,
                    bear_argument=bear_argument,
                )
                debate_history += f"\n\n=== ROUND {round_num + 1} ===\n\nBULL ANALYST:\n{bull_argument}"

                # Bear's turn
                bear_argument = self._get_bear_argument(
                    symbol=symbol,
                    technical_report=tech_summary,
                    sentiment_report=sent_summary,
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
        history: str,
        bear_argument: str,
    ) -> str:
        """
        Generate bull analyst's argument.

        Borrowed from: TradingAgents/agents/researchers/bull_researcher.py
        """
        prompt = f"""You are a Bull Analyst advocating for LONG position on {symbol}.
Your task is to build a strong, evidence-based case for going LONG.

Key points to focus on:
- BULLISH Technical Signals: Price above SMAs, RSI recovering from oversold, MACD bullish crossover
- Growth Momentum: Breakout patterns, increasing volume, support holding
- Counter Bear Arguments: Use specific numbers to refute bearish concerns

Resources Available:
Technical Analysis:
{technical_report}

Sentiment Data:
{sentiment_report}

Previous Debate:
{history if history else "This is the opening argument."}

Last Bear Argument:
{bear_argument if bear_argument else "No bear argument yet - make your opening case."}

INSTRUCTIONS:
1. Present 2-3 compelling reasons for LONG
2. Use specific numbers from the data (RSI values, price levels, etc.)
3. If bear made arguments, directly counter them with data
4. Be persuasive but factual

Deliver your argument now (2-3 paragraphs):"""

        return self._call_api_with_retry([
            {"role": "system", "content": "You are a professional Bull Analyst in a trading debate. Be persuasive and data-driven."},
            {"role": "user", "content": prompt}
        ])

    def _get_bear_argument(
        self,
        symbol: str,
        technical_report: str,
        sentiment_report: str,
        history: str,
        bull_argument: str,
    ) -> str:
        """
        Generate bear analyst's argument.

        Borrowed from: TradingAgents/agents/researchers/bear_researcher.py
        """
        prompt = f"""You are a Bear Analyst making the case AGAINST going LONG on {symbol}.
Your goal is to present well-reasoned arguments for SHORT or staying FLAT.

Key points to focus on:
- BEARISH Technical Signals: Price below SMAs, overbought RSI, MACD bearish divergence
- Downside Risks: Resistance levels, decreasing volume, support breaking
- Counter Bull Arguments: Expose over-optimistic assumptions with specific data

Resources Available:
Technical Analysis:
{technical_report}

Sentiment Data:
{sentiment_report}

Previous Debate:
{history}

Last Bull Argument:
{bull_argument}

INSTRUCTIONS:
1. Present 2-3 compelling reasons AGAINST long / FOR short
2. Use specific numbers from the data (RSI values, price levels, etc.)
3. Directly counter the bull's arguments with data
4. Highlight risks the bull is ignoring

Deliver your argument now (2-3 paragraphs):"""

        return self._call_api_with_retry([
            {"role": "system", "content": "You are a professional Bear Analyst in a trading debate. Be skeptical and highlight risks."},
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
        Optimized with prescriptive prompt engineering to reduce HOLD bias.
        """
        prompt = f"""You are the Portfolio Manager and Debate Judge.
Your role is to evaluate the Bull vs Bear debate and make a DEFINITIVE trading decision.

=== MANDATORY RULES (YOU MUST FOLLOW EXACTLY) ===

1. ⚠️ YOU MUST COUNT TECHNICAL CONFIRMATIONS BEFORE DECIDING
2. ⚠️ YOU MUST FOLLOW THE DECISION RULES ALGORITHMICALLY - NO SUBJECTIVE INTERPRETATION
3. ⚠️ DO NOT DEFAULT TO HOLD - It causes missed opportunities
4. ⚠️ One side almost always has stronger evidence - FIND IT and COMMIT TO IT

Past Trading Mistakes to AVOID:
{past_memories if past_memories else "No past data - this is a fresh start."}

FULL DEBATE TRANSCRIPT:
{debate_history}

=== STEP 1: COUNT TECHNICAL CONFIRMATIONS (MANDATORY) ===

You MUST count how many of these specific confirmations each side presented:

BULLISH Confirmations (count in Bull's arguments):
1. Price above SMA20 OR Price above SMA50
2. RSI < 60 (not overbought, has room to rise)
3. MACD > Signal (bullish crossover) OR MACD histogram > 0
4. Price near support level OR Price near BB lower band
5. Increasing volume OR bullish volume pattern mentioned

BEARISH Confirmations (count in Bear's arguments):
1. Price below SMA20 OR Price below SMA50
2. RSI > 40 (showing weakness or overbought)
3. MACD < Signal (bearish crossover) OR MACD histogram < 0
4. Price near resistance level OR Price near BB upper band
5. Decreasing volume OR bearish volume pattern mentioned

IMPORTANT: Each confirmation is worth 1 point if ANY of the conditions in that item are true.
Example: If price is above SMA50 but below SMA20, confirmation #1 STILL COUNTS as 1.

=== STEP 2: APPLY DECISION RULES (MANDATORY - NO EXCEPTIONS) ===

You MUST follow these rules EXACTLY as written:

IF Bullish count >= 3:
    → decision = "LONG"
    → confidence = "HIGH"
    → STOP HERE, DO NOT CONTINUE

ELSE IF Bearish count >= 3:
    → decision = "SHORT"
    → confidence = "HIGH"
    → STOP HERE, DO NOT CONTINUE

ELSE IF Bullish count == 2 AND Bullish count > Bearish count:
    → decision = "LONG"
    → confidence = "MEDIUM"
    → STOP HERE, DO NOT CONTINUE

ELSE IF Bearish count == 2 AND Bearish count > Bullish count:
    → decision = "SHORT"
    → confidence = "MEDIUM"
    → STOP HERE, DO NOT CONTINUE

ELSE IF Bullish count >= 2 AND Bull's argument quality is clearly superior:
    → decision = "LONG"
    → confidence = "MEDIUM"
    → STOP HERE, DO NOT CONTINUE

ELSE IF Bearish count >= 2 AND Bear's argument quality is clearly superior:
    → decision = "SHORT"
    → confidence = "MEDIUM"
    → STOP HERE, DO NOT CONTINUE

ELSE:
    → decision = "HOLD"
    → confidence = "LOW"
    (This should be RARE - only when both sides have < 2 confirmations AND are truly balanced)

=== STEP 3: VERIFICATION CHECKLIST (BEFORE RESPONDING) ===

Before you provide your JSON response, verify:
✓ Did you count all 5 bullish confirmations? (Write the count)
✓ Did you count all 5 bearish confirmations? (Write the count)
✓ Did you apply the decision rules EXACTLY as written above?
✓ Did you avoid using HOLD as a default safe choice?
✓ If you chose HOLD, are BOTH counts < 2 AND truly balanced?

=== OUTPUT FORMAT ===

Provide your decision in this EXACT JSON format (no additional text):
{{
    "decision": "LONG|SHORT|HOLD",
    "winning_side": "BULL|BEAR|TIE",
    "confidence": "HIGH|MEDIUM|LOW",
    "bullish_count": <number 0-5>,
    "bearish_count": <number 0-5>,
    "key_reasons": ["reason1", "reason2", "reason3"],
    "acknowledged_risks": ["risk1", "risk2"]
}}

JSON response only (no preamble, no explanation):"""

        # Use JSON retry mechanism to improve reliability
        decision = self._extract_json_with_retry(
            messages=[
                {"role": "system", "content": "You are a Portfolio Manager. You MUST follow the quantitative decision rules EXACTLY. Do NOT use subjective judgment to override the rules. Count confirmations accurately and apply the decision logic algorithmically."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Lower temperature for more consistent output
            max_json_retries=2,
        )

        if decision:
            # Log the confirmation counts for transparency
            bullish = decision.get('bullish_count', 'N/A')
            bearish = decision.get('bearish_count', 'N/A')
            self.logger.info(f"📊 Judge counted: Bullish {bullish}/5, Bearish {bearish}/5")
            return decision

        # Fallback decision if all retries failed
        self.logger.warning("Judge decision parsing failed after retries, using fallback")
        return {
            "decision": "HOLD",
            "winning_side": "TIE",
            "confidence": "LOW",
            "bullish_count": 0,
            "bearish_count": 0,
            "key_reasons": ["JSON parse error - defaulting to HOLD"],
            "acknowledged_risks": ["Parse failure"]
        }

    def _evaluate_risk(
        self,
        proposed_action: Dict[str, Any],
        technical_report: str,
        sentiment_report: str,
        current_position: Optional[Dict[str, Any]],
        current_price: float,
    ) -> Dict[str, Any]:
        """
        Final risk evaluation and position sizing.

        Borrowed from: TradingAgents/agents/risk_mgmt/conservative_debator.py
        """
        action = proposed_action.get("decision", "HOLD")
        confidence = proposed_action.get("confidence", "LOW")
        reasons = proposed_action.get("key_reasons", [])
        risks = proposed_action.get("acknowledged_risks", [])

        prompt = f"""As the Risk Manager, provide final trade parameters.

PROPOSED TRADE:
- Action: {action}
- Confidence: {confidence}
- Key Reasons: {', '.join(reasons)}
- Acknowledged Risks: {', '.join(risks)}

MARKET DATA:
{technical_report}

{sentiment_report}

CURRENT POSITION:
{self._format_position(current_position)}

CURRENT PRICE: ${current_price:,.2f}

RISK RULES:
1. Position sizing based on confidence:
   - HIGH confidence + clear trend → 100% of base position
   - MEDIUM confidence → 50% of base position
   - LOW confidence → 25% or skip trade

2. Stop Loss:
   - LONG: 1-2% below entry (use support levels if available)
   - SHORT: 1-2% above entry (use resistance levels if available)

3. Take Profit:
   - HIGH confidence: 2-3% target
   - MEDIUM confidence: 1.5-2% target
   - LOW confidence: 1% target

Provide final recommendation in this exact JSON format:
{{
    "signal": "BUY|SELL|HOLD",
    "confidence": "HIGH|MEDIUM|LOW",
    "risk_level": "LOW|MEDIUM|HIGH",
    "position_size_pct": 25|50|100,
    "stop_loss": <price_number>,
    "take_profit": <price_number>,
    "reason": "<one sentence explaining the final decision>",
    "debate_summary": "<brief summary of bull vs bear debate>"
}}

MAPPING: LONG→BUY, SHORT→SELL, HOLD→HOLD

JSON response only:"""

        # Use JSON retry mechanism to improve reliability
        decision = self._extract_json_with_retry(
            messages=[
                {"role": "system", "content": "You are a Risk Manager. Provide precise trade parameters with specific price levels."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
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
        # Defensive check: ensure current_price is valid before calculations
        if current_price is None or current_price <= 0:
            self.logger.warning(f"Invalid current_price ({current_price}) for SL/TP validation, skipping")
            return decision

        signal = decision.get("signal", "HOLD")
        sl = decision.get("stop_loss", 0) or 0  # Handle None
        tp = decision.get("take_profit", 0) or 0  # Handle None

        if signal == "BUY":
            # For LONG: SL should be below entry, TP above
            if sl >= current_price:
                decision["stop_loss"] = current_price * 0.98  # 2% below
                self.logger.warning(f"Fixed BUY stop loss: {sl} -> {decision['stop_loss']}")
            if tp <= current_price:
                decision["take_profit"] = current_price * 1.03  # 3% above
                self.logger.warning(f"Fixed BUY take profit: {tp} -> {decision['take_profit']}")

        elif signal == "SELL":
            # For SHORT: SL should be above entry, TP below
            if sl <= current_price:
                decision["stop_loss"] = current_price * 1.02  # 2% above
                self.logger.warning(f"Fixed SELL stop loss: {sl} -> {decision['stop_loss']}")
            if tp >= current_price:
                decision["take_profit"] = current_price * 0.97  # 3% below
                self.logger.warning(f"Fixed SELL take profit: {tp} -> {decision['take_profit']}")

        return decision

    def _format_technical_report(self, data: Dict[str, Any]) -> str:
        """Format technical data for prompts."""
        if not data:
            return "Technical data not available"

        def safe_get(key, default=0):
            val = data.get(key)
            return float(val) if val is not None else default

        return f"""
Price: ${safe_get('price'):,.2f}
24h Change: {safe_get('price_change'):+.2f}%

TREND ANALYSIS:
- Overall Trend: {data.get('overall_trend', 'N/A')}
- Short-term: {data.get('short_term_trend', 'N/A')}
- MACD Direction: {data.get('macd_trend', 'N/A')}

MOVING AVERAGES:
- SMA 5: ${safe_get('sma_5'):,.2f}
- SMA 20: ${safe_get('sma_20'):,.2f}
- SMA 50: ${safe_get('sma_50'):,.2f}

MOMENTUM:
- RSI: {safe_get('rsi'):.1f} ({'Overbought >70' if safe_get('rsi') > 70 else 'Oversold <30' if safe_get('rsi') < 30 else 'Neutral 30-70'})
- MACD: {safe_get('macd'):.4f}
- MACD Signal: {safe_get('macd_signal'):.4f}
- MACD Histogram: {safe_get('macd_histogram'):.4f} ({'Bullish' if safe_get('macd_histogram') > 0 else 'Bearish'})

VOLATILITY (Bollinger Bands):
- Upper: ${safe_get('bb_upper'):,.2f}
- Middle: ${safe_get('bb_middle'):,.2f}
- Lower: ${safe_get('bb_lower'):,.2f}
- Price Position: {safe_get('bb_position'):.1%}

KEY LEVELS:
- Resistance: ${safe_get('resistance'):,.2f}
- Support: ${safe_get('support'):,.2f}

VOLUME:
- Volume Ratio: {safe_get('volume_ratio'):.2f}x average
"""

    def _format_sentiment_report(self, data: Optional[Dict[str, Any]]) -> str:
        """Format sentiment data for prompts."""
        if not data:
            return "SENTIMENT: Data not available"

        net = data.get('net_sentiment') or 0
        pos_ratio = data.get('positive_ratio') or 0
        neg_ratio = data.get('negative_ratio') or 0
        sign = '+' if net >= 0 else ''

        return f"""
MARKET SENTIMENT (Long/Short Ratio):
- Bullish Ratio: {pos_ratio:.1%}
- Bearish Ratio: {neg_ratio:.1%}
- Net Sentiment: {sign}{net:.3f}
- Interpretation: {'Bullish bias' if net > 0.1 else 'Bearish bias' if net < -0.1 else 'Neutral'}
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

        return {
            "signal": "HOLD",
            "confidence": "LOW",
            "risk_level": "HIGH",
            "position_size_pct": 0,
            "stop_loss": price * 0.98 if price else 0,
            "take_profit": price * 1.02 if price else 0,
            "reason": "Multi-agent analysis failed - defaulting to HOLD",
            "debate_summary": "Analysis error occurred",
            "is_fallback": True,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def get_last_debate(self) -> str:
        """Return the last debate transcript for debugging/logging."""
        return self.last_debate_transcript
