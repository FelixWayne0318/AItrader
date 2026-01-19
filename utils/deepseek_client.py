"""
DeepSeek AI Integration Module for NautilusTrader

Provides AI-powered market analysis and trading signal generation.
"""

import json
import re
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from openai import OpenAI


class DeepSeekAnalyzer:
    """
    DeepSeek AI analyzer for generating trading signals.

    Analyzes market conditions using technical indicators, K-line patterns,
    and sentiment data to produce structured trading signals.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        temperature: float = 0.1,
        base_url: str = "https://api.deepseek.com",
        max_retries: int = 2,
    ):
        """
        Initialize DeepSeek analyzer.

        Parameters
        ----------
        api_key : str
            DeepSeek API key
        model : str
            Model name (default: deepseek-chat)
        temperature : float
            Temperature for response generation (0.0-1.0)
        base_url : str
            API base URL
        max_retries : int
            Maximum retry attempts on failure
        """
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries

        # Setup logger
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Track signal history
        self.signal_history = []

    def analyze(
        self,
        price_data: Dict[str, Any],
        technical_data: Dict[str, Any],
        sentiment_data: Optional[Dict[str, Any]] = None,
        current_position: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Analyze market conditions and generate trading signal.

        Parameters
        ----------
        price_data : Dict
            Current price and K-line data
        technical_data : Dict
            Technical indicator values
        sentiment_data : Dict, optional
            Market sentiment data
        current_position : Dict, optional
            Current position information

        Returns
        -------
        Dict
            Trading signal with structure:
            {
                "signal": "BUY|SELL|HOLD",
                "confidence": "HIGH|MEDIUM|LOW",
                "reason": str,
                "stop_loss": float,
                "take_profit": float,
                "timestamp": str
            }
        """
        for attempt in range(self.max_retries):
            try:
                signal = self._analyze_with_retry(
                    price_data, technical_data, sentiment_data, current_position
                )

                if signal and not signal.get("is_fallback", False):
                    return signal

                self.logger.warning(f"⚠️ Attempt {attempt + 1} failed, retrying...")

            except Exception as e:
                self.logger.error(f"❌ Analysis attempt {attempt + 1} failed: {e}")
                if attempt == self.max_retries - 1:
                    return self._create_fallback_signal(price_data)

        return self._create_fallback_signal(price_data)

    def _analyze_with_retry(
        self,
        price_data: Dict[str, Any],
        technical_data: Dict[str, Any],
        sentiment_data: Optional[Dict[str, Any]],
        current_position: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Internal analysis with single attempt."""

        # Build comprehensive prompt
        prompt = self._build_analysis_prompt(
            price_data, technical_data, sentiment_data, current_position
        )

        # Call DeepSeek API
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an elite algorithmic trading system specializing in "
                        "high-frequency cryptocurrency trading on Binance Futures (BTCUSDT-PERP). "
                        "You analyze 15-minute K-line data with precision, combining multiple "
                        "technical indicators, market microstructure, and sentiment analysis. "
                        "Your decisions must be data-driven, risk-aware, and optimized for "
                        "15-minute timeframe characteristics. Always return responses strictly in JSON format."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            stream=False,
            temperature=self.temperature
        )

        # Parse response
        result = response.choices[0].message.content
        self.logger.info(f"🤖 DeepSeek Response: {result}")

        signal_data = self._safe_parse_json(result)

        if signal_data is None:
            return self._create_fallback_signal(price_data)

        # Validate required fields
        required_fields = ["signal", "reason", "stop_loss", "take_profit", "confidence"]
        optional_fields = ["trend_strength", "risk_assessment"]
        
        if not all(field in signal_data for field in required_fields):
            self.logger.warning(f"⚠️ Missing required fields in signal data")
            return self._create_fallback_signal(price_data)
        
        # Set defaults for optional fields if missing
        if "trend_strength" not in signal_data:
            signal_data["trend_strength"] = "MODERATE"
        if "risk_assessment" not in signal_data:
            signal_data["risk_assessment"] = "MEDIUM"

        # Add metadata
        signal_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Store in history
        self.signal_history.append(signal_data)
        if len(self.signal_history) > 30:
            self.signal_history.pop(0)

        # Log signal statistics
        self._log_signal_stats(signal_data)

        return signal_data

    def _build_analysis_prompt(
        self,
        price_data: Dict[str, Any],
        technical_data: Dict[str, Any],
        sentiment_data: Optional[Dict[str, Any]],
        current_position: Optional[Dict[str, Any]],
    ) -> str:
        """Build comprehensive analysis prompt for DeepSeek."""

        # K-line data
        kline_text = self._format_kline_data(price_data.get("kline_data", []))

        # Technical analysis
        technical_text = self._format_technical_data(technical_data)

        # Sentiment data
        sentiment_text = self._format_sentiment_data(sentiment_data)

        # Position info
        position_text = self._format_position_data(current_position)

        # Previous signal
        signal_text = ""
        if self.signal_history:
            last_signal = self.signal_history[-1]
            signal_text = (
                f"\n【Previous Signal】\n"
                f"Signal: {last_signal.get('signal', 'N/A')}\n"
                f"Confidence: {last_signal.get('confidence', 'N/A')}"
            )

        prompt = f"""
═══════════════════════════════════════════════════════════════
  BTC/USDT FUTURES - 15-MINUTE TIMEFRAME ANALYSIS
═══════════════════════════════════════════════════════════════

【MARKET CONTEXT - REAL-TIME DATA】

{kline_text}

{technical_text}

{sentiment_text}

{signal_text}

【CURRENT MARKET STATE】
├─ Current Price: ${price_data['price']:,.2f}
├─ Time: {price_data['timestamp']}
├─ Period High: ${price_data.get('high', 0):,.2f}
├─ Period Low: ${price_data.get('low', 0):,.2f}
├─ Volume: {price_data.get('volume', 0):.2f} BTC
├─ Price Change: {price_data.get('price_change', 0):+.2f}%
└─ Current Position: {position_text}

【CRITICAL TECHNICAL STATUS】
├─ Overall Trend: {technical_data.get('overall_trend', 'N/A')}
├─ Short-term Trend: {technical_data.get('short_term_trend', 'N/A')}
├─ RSI: {technical_data.get('rsi', 0):.1f} ({'🔴 Overbought' if technical_data.get('rsi', 0) > 70 else '🟢 Oversold' if technical_data.get('rsi', 0) < 30 else '⚪ Neutral'})
└─ MACD Direction: {technical_data.get('macd_trend', 'N/A')}

═══════════════════════════════════════════════════════════════
  TRADING STRATEGY FRAMEWORK - MUST FOLLOW
═══════════════════════════════════════════════════════════════

【1. DECISION HIERARCHY (Weight Distribution)】

Primary Layer (60% weight) - TECHNICAL ANALYSIS:
├─ Trend Direction (MA alignment, price action)
│  ├─ Strong uptrend: Price > SMA5 > SMA20 > SMA50 → BUY bias
│  ├─ Strong downtrend: Price < SMA5 < SMA20 < SMA50 → SELL bias
│  └─ Mixed/consolidation: No clear trend → HOLD/Cautious
├─ Support/Resistance Levels
│  ├─ Price near resistance with volume → Potential reversal SELL
│  ├─ Price near support with volume → Potential bounce BUY
│  └─ Price breaking key levels with volume → Strong signal
└─ K-line Patterns & Candlestick Formations
   ├─ Bullish patterns (hammer, engulfing, etc.) → BUY signal
   ├─ Bearish patterns (shooting star, dark cloud, etc.) → SELL signal
   └─ Doji/indecision → Wait for confirmation

Secondary Layer (30% weight) - MARKET SENTIMENT:
├─ Sentiment aligns with technical → Enhance confidence by 1 level
├─ Sentiment diverges from technical → Follow technical, sentiment as warning
└─ Sentiment data unavailable/delayed → Ignore, focus on technical

Tertiary Layer (10% weight) - RISK MANAGEMENT:
├─ Current position P&L status
├─ Stop-loss placement (should be 1-2% from entry)
└─ Position sizing constraints

【2. SIGNAL GENERATION LOGIC - STRICT RULES】

BUY Signal Conditions (Require at least 2 of 3):
├─ ✅ Strong uptrend confirmed by MA alignment
├─ ✅ Price breaks above resistance with volume surge
├─ ✅ RSI recovering from oversold (< 40) or healthy momentum (40-60)
├─ ✅ MACD bullish crossover or positive histogram
├─ ✅ Bullish K-line pattern (hammer, bullish engulfing, etc.)
└─ ✅ Sentiment positive (if available, adds confidence)

SELL Signal Conditions (Require at least 2 of 3):
├─ ✅ Strong downtrend confirmed by MA alignment
├─ ✅ Price breaks below support with volume surge
├─ ✅ RSI declining from overbought (> 60) or strong bearish momentum
├─ ✅ MACD bearish crossover or negative histogram
├─ ✅ Bearish K-line pattern (shooting star, bearish engulfing, etc.)
└─ ✅ Sentiment negative (if available, adds confidence)

HOLD Signal Conditions:
├─ ⚠️ Consolidation/narrow range trading (no clear direction)
├─ ⚠️ Mixed signals (some indicators bullish, some bearish)
├─ ⚠️ Waiting for confirmation (potential reversal but not confirmed)
└─ ⚠️ Low volume with indecisive candles

【3. CONFIDENCE LEVEL ASSIGNMENT】

HIGH Confidence:
├─ 3+ technical indicators align
├─ Clear trend with strong volume
├─ Price action confirms indicator signals
└─ Sentiment supports (if available)

MEDIUM Confidence:
├─ 2 technical indicators align
├─ Moderate trend strength
├─ Some conflicting signals present
└─ Sentiment neutral or unavailable

LOW Confidence:
├─ Only 1 strong indicator
├─ Mixed signals predominant
├─ Low volume/consolidation phase
└─ Sentiment contradicts technical

【4. ANTI-OVERTRADING PRINCIPLES】

1. Trend Continuity:
   └─ Don't reverse signal based on single candle fluctuation
   └─ Require 2-3 consecutive bars confirming reversal

2. Position Stability:
   └─ Maintain direction unless clear reversal pattern
   └─ Avoid frequent position changes (minimize transaction costs)

3. Signal Confirmation:
   └─ Wait for confirmation when in doubt
   └─ Better to HOLD than make wrong move

4. Volume Validation:
   └─ High-confidence signals require volume confirmation
   └─ Low volume moves are less reliable

【5. 15-MINUTE TIMEFRAME SPECIFIC CONSIDERATIONS】

├─ Balanced timeframe for both trend following and swing trading
├─ Signals are more reliable with reduced noise compared to 1-minute
├─ Volume analysis is important for confirmation
├─ RSI > 70 or < 30 indicates strong momentum (act with caution)
└─ MACD crossovers are significant and should be respected

【6. RISK MANAGEMENT INTEGRATION】

Stop-Loss Placement:
├─ BUY signal: Place 1-2% below entry or below recent support
├─ SELL signal: Place 1-2% above entry or above recent resistance
└─ Consider volatility: Tighter stops in volatile conditions

Take-Profit Targets:
├─ High confidence: 2-3% target
├─ Medium confidence: 1.5-2% target
└─ Low confidence: 1% target or consider HOLD

Position Management:
├─ Existing LONG position:
│  ├─ Trend continues → Maintain BUY signal
│  ├─ Trend reverses → Generate SELL signal to close/reverse
│  └─ Unrealized loss > 2% → Consider cutting losses
└─ Existing SHORT position:
   ├─ Trend continues → Maintain SELL signal
   ├─ Trend reverses → Generate BUY signal to close/reverse
   └─ Unrealized loss > 2% → Consider cutting losses

═══════════════════════════════════════════════════════════════
  OUTPUT REQUIREMENTS
═══════════════════════════════════════════════════════════════

Provide a comprehensive analysis and trading signal.

CRITICAL: Your response MUST be valid JSON only, no additional text.

**IMPORTANT JSON FORMATTING RULES:**
1. DO NOT use double quotes (") inside string values
2. Use single quotes (') or parentheses for emphasis instead
3. The "reason" field must be a single continuous string without internal quotes

JSON Format:
{{
    "signal": "BUY|SELL|HOLD",
    "confidence": "HIGH|MEDIUM|LOW",
    "reason": "Detailed analysis including: (1) Current trend assessment, (2) Key technical indicators analysis, (3) Support/resistance levels, (4) Volume analysis, (5) Risk factors, (6) Why this signal at this moment. Use ONLY single quotes or parentheses for emphasis, NEVER use double quotes inside this field.",
    "stop_loss": <numerical_price_value>,
    "take_profit": <numerical_price_value>,
    "trend_strength": "STRONG|MODERATE|WEAK",
    "risk_assessment": "LOW|MEDIUM|HIGH"
}}

Example stop_loss/take_profit values:
- BUY: stop_loss should be current_price * 0.98-0.99, take_profit should be current_price * 1.02-1.03
- SELL: stop_loss should be current_price * 1.01-1.02, take_profit should be current_price * 0.97-0.98
- HOLD: Set stop_loss and take_profit to current_price

Example CORRECT reason format:
"reason": "(1) Current trend shows strong downward momentum with price below all SMAs. (2) RSI at 35 indicates oversold conditions. (3) Key support at $110,000 being tested. Use single quotes for 'emphasis' if needed."

Example WRONG reason format (DO NOT USE):
"reason": "(1) Current trend "assessment" shows..." <- WRONG! Contains internal double quotes

Remember: Be decisive but not reckless. Quality over quantity.
"""
        return prompt

    def _format_kline_data(self, kline_data: list) -> str:
        """Format K-line data for prompt."""
        if not kline_data:
            return "【Recent K-line Data】\nNo K-line data available"

        kline_text = "【Recent 10 15-minute K-lines (Most Recent)】\n"
        for i, kline in enumerate(kline_data[-10:], 1):
            candle_type = "🟢 Bullish" if kline['close'] > kline['open'] else "🔴 Bearish"
            change = ((kline['close'] - kline['open']) / kline['open']) * 100
            body_size = abs(kline['close'] - kline['open'])
            total_range = kline['high'] - kline['low']
            body_ratio = (body_size / total_range * 100) if total_range > 0 else 0
            
            kline_text += (
                f"K{i}: {candle_type} | "
                f"O:{kline['open']:.2f} H:{kline['high']:.2f} L:{kline['low']:.2f} C:{kline['close']:.2f} | "
                f"Change:{change:+.2f}% | "
                f"Vol:{kline['volume']:.2f} | "
                f"Body:{body_ratio:.1f}%\n"
            )
        return kline_text

    def _format_technical_data(self, technical_data: Dict[str, Any]) -> str:
        """Format technical indicator data for prompt."""

        def safe_float(val, default=0):
            return float(val) if val is not None else default

        text = f"""
【Technical Indicator Analysis】
📈 Moving Averages (SMA):
{self._format_sma_data(technical_data)}

🎯 Trend Analysis:
├─ Short-term: {technical_data.get('short_term_trend', 'N/A')}
├─ Medium-term: {technical_data.get('medium_term_trend', 'N/A')}
├─ Overall: {technical_data.get('overall_trend', 'N/A')}
└─ MACD Direction: {technical_data.get('macd_trend', 'N/A')}

📊 Momentum Indicators:
├─ RSI: {safe_float(technical_data.get('rsi')):.2f} ({'🔴 Overbought (>70)' if safe_float(technical_data.get('rsi')) > 70 else '🟢 Oversold (<30)' if safe_float(technical_data.get('rsi')) < 30 else '⚪ Neutral (30-70)'})
├─ MACD Line: {safe_float(technical_data.get('macd')):.4f}
├─ Signal Line: {safe_float(technical_data.get('macd_signal')):.4f}
└─ Histogram: {safe_float(technical_data.get('macd_histogram')):.4f} {'🟢 Bullish' if safe_float(technical_data.get('macd_histogram')) > 0 else '🔴 Bearish'}

🎚️ Bollinger Bands:
├─ Upper Band: {safe_float(technical_data.get('bb_upper')):.2f}
├─ Middle Band (SMA): {safe_float(technical_data.get('bb_middle')):.2f}
├─ Lower Band: {safe_float(technical_data.get('bb_lower')):.2f}
└─ Price Position: {safe_float(technical_data.get('bb_position')):.2%} ({'🔴 Near Upper (>80%)' if safe_float(technical_data.get('bb_position')) > 0.8 else '🟢 Near Lower (<20%)' if safe_float(technical_data.get('bb_position')) < 0.2 else '⚪ Middle Zone (20-80%)'})

💰 Key Levels:
├─ Resistance: ${safe_float(technical_data.get('resistance')):.2f}
└─ Support: ${safe_float(technical_data.get('support')):.2f}

📦 Volume Analysis:
└─ Volume Ratio: {safe_float(technical_data.get('volume_ratio')):.2f}x average ({'🟢 High Volume' if safe_float(technical_data.get('volume_ratio')) > 1.5 else '🔴 Low Volume' if safe_float(technical_data.get('volume_ratio')) < 0.5 else '⚪ Normal'})
"""
        return text
    
    def _format_sma_data(self, technical_data: Dict[str, Any]) -> str:
        """Format SMA data dynamically based on available periods."""
        sma_text = ""
        sma_keys = [key for key in technical_data.keys() if key.startswith('sma_')]
        
        if sma_keys:
            for key in sorted(sma_keys, key=lambda x: int(x.split('_')[1])):
                period = key.split('_')[1]
                value = technical_data[key]
                sma_text += f"├─ SMA {period}: ${float(value):,.2f}\n"
            sma_text = sma_text.rstrip('\n')
        else:
            sma_text = "├─ SMA data not available"
        
        return sma_text

    def _format_sentiment_data(self, sentiment_data: Optional[Dict[str, Any]]) -> str:
        """Format sentiment data for prompt."""
        if not sentiment_data:
            return "【Market Sentiment】Data not available"

        sign = '+' if sentiment_data['net_sentiment'] >= 0 else ''
        return (
            f"【Market Sentiment】"
            f"Bullish {sentiment_data['positive_ratio']:.1%} | "
            f"Bearish {sentiment_data['negative_ratio']:.1%} | "
            f"Net {sign}{sentiment_data['net_sentiment']:.3f}"
        )

    def _format_position_data(self, position: Optional[Dict[str, Any]]) -> str:
        """Format position data for prompt."""
        if not position:
            return "No position"

        return (
            f"{position['side']} position, "
            f"Size: {position.get('quantity', 0):.3f} BTC, "
            f"Avg Price: ${position.get('avg_px', 0):.2f}, "
            f"P&L: {position.get('unrealized_pnl', 0):.2f} USDT"
        )

    def _safe_parse_json(self, json_str: str) -> Optional[Dict[str, Any]]:
        """Safely parse JSON response, handling format issues."""
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            start_idx = json_str.find('{')
            end_idx = json_str.rfind('}') + 1

            if start_idx != -1 and end_idx != 0:
                json_str_original = json_str[start_idx:end_idx]

                try:
                    # Parse line by line and fix quotes in string values
                    lines = json_str_original.split('\n')
                    fixed_lines = []
                    
                    for line in lines:
                        # Check if this is a line with a key-value pair containing quotes
                        if '": "' in line and line.strip().endswith((',', '",')):
                            # Find the value part (between the first ": " and the last ")
                            key_end = line.find('": "') + 4
                            if line.strip().endswith(','):
                                value_end = line.rfind('",')
                            else:
                                value_end = line.rfind('"')
                            
                            if key_end > 4 and value_end > key_end:
                                prefix = line[:key_end]
                                value = line[key_end:value_end]
                                suffix = line[value_end:]
                                
                                # Replace internal quotes with single quotes
                                fixed_value = value.replace('"', "'")
                                fixed_line = prefix + fixed_value + suffix
                                fixed_lines.append(fixed_line)
                            else:
                                fixed_lines.append(line)
                        else:
                            fixed_lines.append(line)
                    
                    json_str = '\n'.join(fixed_lines)
                    
                    # Try parsing
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    self.logger.error(f"❌ JSON parse failed: {e}")
                    self.logger.debug(f"Original content: {json_str_original[:500]}...")
                except Exception as e:
                    self.logger.error(f"❌ JSON fix error: {e}")

            return None

    def _create_fallback_signal(self, price_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create conservative fallback signal when AI analysis fails."""
        return {
            "signal": "HOLD",
            "reason": "Conservative strategy due to technical analysis unavailable",
            "stop_loss": price_data['price'] * 0.98,  # -2%
            "take_profit": price_data['price'] * 1.02,  # +2%
            "confidence": "LOW",
            "is_fallback": True,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def _log_signal_stats(self, signal_data: Dict[str, Any]):
        """Log signal statistics."""
        signal = signal_data['signal']
        signal_count = sum(1 for s in self.signal_history if s.get('signal') == signal)
        total = len(self.signal_history)

        self.logger.debug(f"📊 Signal Stats: {signal} (appeared {signal_count}/{total} times in recent history)")

        # Check for consecutive same signals
        if len(self.signal_history) >= 3:
            last_three = [s['signal'] for s in self.signal_history[-3:]]
            if len(set(last_three)) == 1:
                self.logger.warning(f"⚠️ Warning: 3 consecutive {signal} signals")
