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

# =============================================================================
# SIGNAL CONFIDENCE MATRIX (v1.2)
# =============================================================================
# - Quantified per-signal, per-regime confidence multipliers
# - Only injected into Judge + Risk Manager prompts (NOT Bull/Bear)
# - See docs/INDICATOR_CONFIDENCE_MATRIX.md for full design rationale
# =============================================================================
SIGNAL_CONFIDENCE_MATRIX = """
====================================================================
SIGNAL CONFIDENCE MATRIX (v1.2)
====================================================================
When evaluating each confluence layer in STEP 2, apply these confidence
multipliers to weight each signal's reliability in the current regime
(determined in STEP 1).

MULTIPLIER SCALE:
  HIGH (1.2+) = Signal is especially reliable in this regime
  STD  (1.0)  = Standard confidence
  LOW  (0.7)  = Needs other signals to confirm before trusting
  SKIP (≤0.4) = Unreliable in this regime — ignore as primary basis

REGIME COLUMNS: Match your STEP 1 regime to the correct column.
  ADX>40     = Strong trend (趋势层主导)
  ADX 25-40  = Weak trend (趋势重要但非绝对)
  ADX<20     = Ranging / 震荡 (关键水平层权重最高)
  SQUEEZE    = ADX<20 + BB Width at lows (等待突破)
  VOLATILE   = ADX>25 + BB Width expanding fast (趋势跟随 + 宽止损)

REGIME TRANSITION: When ADX is near a boundary (18-22 or 35-45),
blend the multipliers of adjacent regimes (take the average).

====================================================================
SECTION A: SNAPSHOT SIGNALS (per confluence layer)
====================================================================

--- LAYER 1: TREND (1D) → fill confluence.trend_1d ---

| Signal              | ADX>40 | ADX 25-40 | ADX<20 | SQUEEZE | VOLATILE | Nature  |
|---------------------|:---:|:---:|:---:|:---:|:---:|---------|
| 1D SMA200 direction | 1.3 | 1.0 | 0.4 | 0.3 | 1.1 | Lagging |
| 1D ADX/DI direction | 1.2 | 1.0 | 0.3 | 0.3 | 1.1 | Lagging |
| 1D MACD zero-line   | 1.1 | 1.0 | 0.3 | 0.5 | 1.0 | Lagging |
| 1D RSI level        | 0.9 | 1.0 | 0.7 | 0.6 | 0.8 | Sync    |

Notes:
- ADX>40: This layer is DOMINANT — all signals reliable.
- ADX<20: This layer is nearly irrelevant (trend data is noise).
- SQUEEZE: Historical trend direction has low predictive value (about to change).
- VOLATILE: Trend is real but noisy — slightly less reliable than calm strong trend.
- ⚠️ 1D TREND VERDICT (STRONG_BULLISH etc.) is pre-computed from these 4 signals.
  It is a SUMMARY — do NOT count it as a 5th independent signal. (See RULE 2)

--- LAYER 2: MOMENTUM (4H) → fill confluence.momentum_4h ---

| Signal               | ADX>40 | ADX 25-40 | ADX<20 | SQUEEZE | VOLATILE | Nature   |
|----------------------|:---:|:---:|:---:|:---:|:---:|----------|
| 4H RSI level         | 0.8 | 1.0 | 1.2 | 0.9 | 0.7 | Sync     |
| 4H RSI divergence*   | 0.6 | 0.8 | 1.3 | 1.1 | 0.5 | Leading  |
| 4H MACD cross        | 1.2 | 1.0 | 0.3 | 0.5 | 1.1 | Lagging  |
| 4H MACD histogram    | 1.0 | 1.0 | 0.5 | 0.7 | 0.9 | Sync-lag |
| 4H ADX/DI direction  | 1.1 | 1.0 | 0.4 | 0.5 | 1.0 | Lagging  |
| 4H BB position       | 0.6 | 0.9 | 1.2 | 0.8 | 0.5 | Sync     |
| 4H SMA 20/50 cross   | 1.1 | 1.0 | 0.4 | 0.6 | 1.0 | Lagging  |
| CVD single-bar delta | 0.9 | 1.0 | 1.2 | 1.3 | 1.0 | Leading  |
| CVD trend (cumul.)   | 1.1 | 1.0 | 0.8 | 0.7 | 1.0 | Sync-lag |
| CVD divergence*      | 0.7 | 0.9 | 1.3 | 1.2 | 0.5 | Leading  |
| Buy Ratio (taker %)  | 0.8 | 1.0 | 1.1 | 1.2 | 0.9 | Realtime |
| Avg Trade Size chg   | 0.7 | 0.9 | 1.0 | 1.2 | 0.8 | Leading  |

Notes:
- *Divergence = inferred from series data (RSI or CVD vs price opposite directions).
- RSI in ADX>40: Cardwell range shifts apply (40-80 uptrend, 20-60 downtrend),
  traditional 30/70 FAIL. Divergence at 0.6 because it still signals deceleration.
- MACD cross in ADX<20: 74-97% false positive rate — nearly useless.
- VOLATILE: Divergence signals (RSI/CVD) are very unreliable (0.5) due to noise-induced
  false divergences. Trend-confirming signals (MACD cross, ADX/DI) remain useful.
  BB position also unreliable — price swings overshoot bands frequently.
- Buy Ratio: Taker buy % from Order Flow data. >55% = buy pressure, <45% = sell.
- Avg Trade Size: Sudden increase = institutional activity (leading).

--- LAYER 3: KEY LEVELS (15M) → fill confluence.levels_15m ---

| Signal               | ADX>40 | ADX 25-40 | ADX<20 | SQUEEZE | VOLATILE | Nature   |
|----------------------|:---:|:---:|:---:|:---:|:---:|----------|
| S/R zone test (bnce) | 0.5 | 0.8 | 1.3 | 1.0 | 0.4 | Static   |
| S/R zone breakout    | 1.3 | 1.0 | 0.6 | 1.2 | 1.3 | Event    |
| 15M BB position      | 0.6 | 0.9 | 1.2 | 0.8 | 0.5 | Sync     |
| 15M BB Width level   | 0.7 | 0.8 | 0.9 | 1.3 | 0.8 | Sync     |
| OBI (book imbalance) | 0.6 | 0.8 | 1.1 | 1.2 | 0.5 | Realtime |
| OBI change rate      | 0.7 | 0.9 | 1.2 | 1.3 | 0.6 | Leading  |
| Bid/Ask depth change | 0.7 | 0.9 | 1.1 | 1.2 | 0.6 | Leading  |
| Pressure gradient    | 0.6 | 0.8 | 1.1 | 1.2 | 0.5 | Leading  |
| Order walls (>3x)    | 0.4 | 0.6 | 0.9 | 1.0 | 0.3 | Realtime |
| 15M SMA cross (5/20) | 0.9 | 1.0 | 0.6 | 0.7 | 0.8 | Lagging  |
| 15M Volume ratio     | 0.9 | 1.0 | 1.1 | 1.3 | 1.2 | Sync     |
| Price vs period H/L  | 0.8 | 1.0 | 1.1 | 1.0 | 0.9 | Sync     |
| Spread (liquidity)   | 0.9 | 1.0 | 1.0 | 1.1 | 1.1 | Quality  |
| Slippage (execution) | 0.9 | 1.0 | 1.0 | 1.1 | 1.1 | Quality  |

Notes:
- S/R bounce rate: ADX>40 → ~25%, ADX<20 → ~70%.
- VOLATILE: S/R breaks violently (0.4 bounce, 1.3 breakout). Order book is unstable
  (walls eaten or pulled quickly). Volume ratio is meaningful (confirms volatile move).
- Order walls in crypto: Spoofing probability HIGH (>70% of large walls are pulled
  before touch in trending markets). SKIP in ADX>40 and VOLATILE.
- Spread & Slippage: Not directional — indicate execution quality. High spread (>0.05%)
  or high slippage (>0.1% for 1 BTC) → reduce Layer 3 confidence by one tier
  AND reduce position size.

--- LAYER 4: DERIVATIVES → fill confluence.derivatives ---
⚠️ This layer has the most signals. To prevent it from dominating,
group related signals and evaluate the GROUP as one input:
  Group A: Funding Rate (current + extreme + predicted + history + countdown) → 1 input
  Group B: Open Interest (OI 4-quadrant + OI trend + Premium Index) → 1 input
  Group C: Positioning (Top Traders + Global L/S + Coinalyze L/S) → 1 input
  Group D: Real-time flow (Taker Ratio + Liquidations + 24h context) → 1 input
Then synthesize the 4 group conclusions into ONE overall BULLISH/BEARISH/NEUTRAL
for confluence.derivatives.

| Signal                       | ADX>40 | ADX 25-40 | ADX<20 | SQUEEZE | VOLATILE | Nature   |
|------------------------------|:---:|:---:|:---:|:---:|:---:|----------|
| — GROUP A: FUNDING RATE —    |     |     |     |     |     |          |
| FR current value             | 0.8 | 0.9 | 1.0 | 1.0 | 0.8 | Sentiment|
| FR extreme (>±0.05%)        | 0.8 | 1.1 | 1.3 | 1.2 | 0.9 | Leading  |
| FR predicted vs settled diff | 0.9 | 1.0 | 1.1 | 1.2 | 0.9 | Leading  |
| FR settlement history trend  | 0.8 | 1.0 | 1.1 | 1.0 | 0.8 | Sync     |
| FR settlement countdown      | 0.7 | 0.8 | 0.9 | 1.0 | 0.7 | Temporal |
| — GROUP B: OPEN INTEREST —   |     |     |     |     |     |          |
| Premium Index                | 0.8 | 1.0 | 1.1 | 1.2 | 0.9 | Leading  |
| OI↑+Price↑ (new longs)      | 1.2 | 1.0 | 0.8 | 0.9 | 1.1 | Confirm  |
| OI↑+Price↓ (new shorts)     | 1.2 | 1.0 | 0.8 | 0.9 | 1.1 | Confirm  |
| OI↓ (unwinding/liquidation)  | 0.9 | 1.0 | 1.0 | 0.8 | 1.0 | Event    |
| — GROUP C: POSITIONING —     |     |     |     |     |     |          |
| Top Traders L/S position     | 1.0 | 1.0 | 1.2 | 1.1 | 1.0 | Leading  |
| Global L/S extreme (>60%)   | 0.6 | 0.9 | 1.2 | 1.1 | 0.7 | Sentiment|
| Coinalyze L/S Ratio + trend | 0.7 | 0.9 | 1.1 | 1.0 | 0.7 | Sentiment|
| — GROUP D: REAL-TIME FLOW —  |     |     |     |     |     |          |
| Taker Buy/Sell Ratio         | 0.9 | 1.0 | 1.1 | 1.2 | 1.0 | Realtime |
| Liquidation (large event)    | 1.0 | 1.1 | 1.2 | 1.3 | 1.2 | Leading  |
| 24h Volume level             | 0.8 | 1.0 | 1.0 | 1.1 | 1.1 | Context  |
| 24h Price Change %           | 0.7 | 0.9 | 0.9 | 1.0 | 0.8 | Context  |

Notes:
- ⚠️ GROUP RULE: Pick the strongest signal within each group to represent it.
  Do NOT stack all FR signals into one massive FR-driven conclusion.
- FR current in ADX>40: 0.01-0.03% in bull market is NORMAL — don't over-interpret.
- FR predicted vs settled: Sign reversal (+→-) = significant positioning change.
- OI 4-quadrant in ADX>40: New positioning confirms trend — high reliability.
- OI 4-quadrant in ADX<20: May be hedging — moderate value (0.8).
- Top Traders in ADX>40: Smart money WITH trend = confirmation (1.0).
  Top Traders AGAINST trend = early warning, needs 2+ confirmations.
- VOLATILE: FR signals slightly less predictive (volatile markets amplify FR).
  OI confirmation still useful (1.1). Liquidation events are significant (1.2)
  — cascade liquidations in volatile markets can be extreme.

====================================================================
SECTION B: TIME-SERIES PATTERN SIGNALS
====================================================================
AI receives 20-bar (15M) time-series data. Detect patterns from
series, then apply multipliers.

--- PRICE SERIES PATTERNS ---

| Pattern                | ADX>40 | ADX 25-40 | ADX<20 | SQUEEZE | VOLATILE | Nature  |
|------------------------|:---:|:---:|:---:|:---:|:---:|---------|
| Higher highs/lows      | 1.3 | 1.0 | 0.5 | 0.6 | 1.2 | Confirm |
| Lower highs/lows       | 1.3 | 1.0 | 0.5 | 0.6 | 1.2 | Confirm |
| Range-bound oscillation| 0.4 | 0.7 | 1.3 | 1.0 | 0.3 | Confirm |
| Tightening range       | 0.5 | 0.8 | 1.0 | 1.3 | 0.5 | Leading |
| Volume climax (spike)  | 1.0 | 1.1 | 1.2 | 1.3 | 1.2 | Event   |

--- INDICATOR SERIES PATTERNS ---

| Pattern                | ADX>40 | ADX 25-40 | ADX<20 | SQUEEZE | VOLATILE | Nature  |
|------------------------|:---:|:---:|:---:|:---:|:---:|---------|
| ADX series rising      | 1.2 | 1.1 | 1.3 | 1.2 | 1.1 | Leading — trend strengthening |
| ADX series falling     | 0.8 | 1.0 | 0.7 | 0.7 | 0.9 | Leading — trend weakening    |
| BB Width narrowing     | 0.6 | 0.8 | 1.0 | 1.3 | 0.5 | Leading — squeeze forming    |
| BB Width expanding     | 1.1 | 1.0 | 0.8 | 1.3 | 1.2 | Confirm — breakout active    |
| SMA convergence (5→20) | 0.7 | 0.9 | 1.1 | 1.2 | 0.7 | Leading — regime change      |
| SMA divergence (spread)| 1.2 | 1.0 | 0.5 | 0.8 | 1.1 | Confirm — trend established  |
| RSI trend (accel/decel)| 0.9 | 1.0 | 1.1 | 1.0 | 0.8 | Sync                         |
| MACD histogram momentum| 1.0 | 1.0 | 0.5 | 0.8 | 0.9 | Sync-lag                     |
| Volume trend (expand)  | 1.1 | 1.0 | 1.0 | 1.3 | 1.2 | Sync-leading                 |
| Volume trend (shrink)  | 0.8 | 0.9 | 0.9 | 0.7 | 0.8 | Warning                      |

--- K-LINE OHLCV PATTERNS ---

| Pattern                | ADX>40 | ADX 25-40 | ADX<20 | SQUEEZE | VOLATILE | Nature  |
|------------------------|:---:|:---:|:---:|:---:|:---:|---------|
| Engulfing candle       | 0.7 | 1.0 | 1.2 | 1.3 | 0.6 | Leading — reversal     |
| Doji at S/R            | 0.5 | 0.8 | 1.3 | 1.1 | 0.4 | Leading — indecision   |
| Long wicks (rejection) | 0.6 | 0.9 | 1.2 | 1.1 | 0.5 | Leading — rejection    |
| Consecutive same-dir   | 1.2 | 1.0 | 0.6 | 0.8 | 1.1 | Confirm — continuation |

Notes:
- ADX rising in ADX<20 (1.3) = CRITICAL leading signal. ADX climbing 12→18 means
  regime is about to shift to TRENDING. One of the most valuable signals.
- BB Width narrowing in SQUEEZE at 1.3 (not 1.5): narrowing DEFINES squeeze,
  so highest multiplier would be circular. 1.3 for the process is appropriate.
- VOLATILE: Reversal patterns (engulfing, doji, wicks) are very unreliable
  (0.4-0.6) — volatility creates many false reversal signals. Trend continuation
  patterns remain useful (1.1-1.2). Volume and BB Width expansion confirm the move.

====================================================================
SECTION C: MULTI-SOURCE SIGNAL DIFFERENTIATION
====================================================================
The system receives similar data from multiple sources. These are NOT
redundant — each has different predictive characteristics.

--- LONG/SHORT POSITIONING (3 sources) ---

| Source                | Represents              | Edge                    | Relative |
|-----------------------|-------------------------|-------------------------|:---:|
| Top Traders Position  | Institutional/whale     | Best predictor          | Highest  |
| Taker Buy/Sell Ratio  | Real-time aggressive flow| Real-time direction    | High     |
| Binance Global L/S    | Retail sentiment        | Contrarian at extremes  | Base     |
| Coinalyze L/S Ratio   | Exchange-specific       | Cross-validates Binance | Below    |

RULE: Top Traders vs Global L/S diverge → weight Top Traders.
      All 3+ agree at extremes → very HIGH confidence.

--- OPEN INTEREST (2 sources) ---

| Source        | Characteristic            | Best for             |
|---------------|---------------------------|----------------------|
| Coinalyze OI  | Aggregated multi-exchange | Macro trend (4H)     |
| Binance OI    | Single exchange, real-time| Short-term moves(15M)|

RULE: Same trend → add one confidence tier to OI assessment.
      Disagree → use Binance for execution, Coinalyze for context.

--- FUND FLOW (2 sources) ---

| Source        | Calculation              | Best for              |
|---------------|--------------------------|----------------------|
| CVD (K-line)  | Cumulative taker delta   | Trend over bars      |
| Taker Ratio   | Buy/Sell vol snapshot    | Real-time pressure   |

RULE: Same direction → cross-validated, add one confidence tier.
      Diverge → transitioning, reduce one tier.

====================================================================
SECTION D: GLOBAL SIGNAL QUALITY MODIFIERS
====================================================================
These modify RELIABILITY of all signals. Apply BEFORE final decision.
Use TIER shifts (not math): each condition shifts confidence DOWN/UP
by one tier (HIGH→STD, STD→LOW, LOW→SKIP).

| Condition                                    | Effect        | Applies to              |
|----------------------------------------------|:---:|--------------------------|
| Volume Ratio < 0.5x (from 15M data)         | DOWN one tier | ALL signals              |
| Volume Ratio > 2.0x                          | UP one tier   | ALL signals              |
| Spread > 0.05% OR Slippage > 0.1%           | DOWN one tier | Layer 3 + position size  |
| 2+ data sources unavailable                  | DOWN one tier | Affected layers          |
| FR settlement < 30 min away                  | DOWN one tier | Short-term (15M) signals |
| Low volume + thin orderbook across bars      | DOWN one tier | ALL signals (weekend/off-hours) |

Notes:
- Tier shifts stack: 2 conditions = DOWN two tiers.
- Volume Ratio comes from 15M data ("Volume Ratio: X.XXx average").
- Weekend/off-hours: No date data available. Infer from persistently low
  volume ratio + reduced orderbook depth across multiple snapshots.

====================================================================
SECTION E: APPLICATION RULES
====================================================================

RULE 1 — Layer evaluation:
  For each confluence layer, assess each signal weighted by its
  confidence tier in the current regime:
    HIGH (1.2+) = Primary evidence for layer judgment
    STD  (1.0)  = Supporting evidence
    LOW  (0.7)  = Note but don't base judgment on it alone
    SKIP (≤0.4) = Ignore for this regime

RULE 2 — TREND VERDICT is not a 5th signal:
  The pre-computed 1D TREND VERDICT is a summary of the 4 Layer 1
  signals. Use for quick reference ONLY. Do NOT count as independent.

RULE 3 — Conflict resolution:
  If leading and lagging signals within one layer conflict, prioritize
  the one with HIGHER confidence tier in current regime.

RULE 4 — Neutral threshold:
  If only SKIP or LOW signals support a direction in a layer,
  that layer should be judged NEUTRAL.

RULE 5 — SQUEEZE special case:
  Wait for breakout confirmation (volume + price) before applying
  directional multipliers. Pre-breakout: focus on BB Width, Volume,
  OBI change rate, ADX rising.

RULE 6 — Counter-trend in ADX>40:
  Even HIGH counter-trend signals require at least 2 independent
  confirming signals before consideration.

RULE 7 — Multi-source agreement:
  3+ independent sources agree on direction → upgrade that layer
  by one confidence tier.

RULE 8 — Layer 4 grouping → confluence.derivatives:
  Evaluate Layer 4 in 4 groups (A/B/C/D). Each group = 1 input.
  Then synthesize the 4 group conclusions into ONE overall
  BULLISH/BEARISH/NEUTRAL judgment for the confluence.derivatives field.

RULE 9 — Global quality check:
  Before final decision, check Section D. Apply tier shifts.
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
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)
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

            # v5.4: Extract base currency from symbol for dynamic unit display
            # e.g., "BTCUSDT" → "BTC", "ETHUSDT" → "ETH", "SOLUSDT" → "SOL"
            self._base_currency = symbol.replace('USDT', '') if 'USDT' in symbol else symbol

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

            # v5.10: Build current conditions snapshot for similarity-based memory retrieval
            current_conditions = self._build_current_conditions(
                technical_report, sentiment_report
            )
            past_memories = self._get_past_memories(current_conditions)

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
                    past_memories=past_memories,                # v5.9
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
                    past_memories=past_memories,                # v5.9
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
                past_memories=past_memories,  # v5.9: Reuse same instance
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
                past_memories=past_memories,  # v5.9: Past trade patterns for risk assessment
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
        past_memories: str = "",     # v5.9: Past trade patterns
    ) -> str:
        """
        Generate bull analyst's argument.

        Borrowed from: TradingAgents/agents/researchers/bull_researcher.py
        TradingAgents v3.3: Indicator definitions in system prompt (like TradingAgents)
        v3.8: Added S/R zones report
        v5.9: Added past_memories for pattern learning
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

## 📚 PAST TRADE PATTERNS
{past_memories if past_memories else "No historical data yet."}

## 🎯 【分析任务 — 请严格按步骤执行】

**第一步：判断 MARKET REGIME**
用指标手册判断当前市场状态 (TRENDING / RANGING / SQUEEZE)
— 这决定了后续所有指标的解读方式。

**第二步：识别看多信号**
从上方数据中找出具体的 BULLISH 信号，附带数值。
必须使用当前 regime 对应的解读规则 (例如 RSI 30 在趋势市场 vs 震荡市场含义不同)。
如果历史数据中有类似条件的成功做多案例，可以引用。

**第三步：构建论点**
提出 2-3 个有说服力的做多理由。
如果 Bear 已有论点，用数据反驳。

**第四步：评估入场条件**
入场价为当前市场价 — 基于 S/R zones 和市场结构评估 R:R 比。

**第五步：陈述失效条件**
什么情况下你的看多论点会被推翻？
"""
        # v5.5: R2+ enhancement — force new arguments and direct rebuttals
        if history and bear_argument:
            prompt += """
⚠️ 【第二轮辩论规则 — 必须遵守】
这是后续辩论轮次，不是 R1 的重复。你必须：
1. **直接引用并反驳** Bear 最新论点中的具体数据（如 "Bear 声称 RSI 从 X 下降到 Y，但实际原始数据显示..."）
2. **提出至少 1 个 R1 中未使用的新证据或数据点**
3. **承认** Bear 论点中有道理的部分，然后解释为什么整体仍然看多
❌ 简单重复 R1 论点将被裁判忽略。
"""

        prompt += "\n请用 2-3 段落交付你的论点："

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
        past_memories: str = "",     # v5.9: Past trade patterns
    ) -> str:
        """
        Generate bear analyst's argument.

        Borrowed from: TradingAgents/agents/researchers/bear_researcher.py
        TradingAgents v3.3: AI interprets raw data using indicator definitions
        v3.8: Added S/R zones report
        v5.9: Added past_memories for pattern learning
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

## 📚 PAST TRADE PATTERNS
{past_memories if past_memories else "No historical data yet."}

## 🎯 【分析任务 — 请严格按步骤执行】

**第一步：判断 MARKET REGIME**
用指标手册判断当前市场状态 (TRENDING / RANGING / SQUEEZE)
— 这决定了后续所有指标的解读方式。

**第二步：识别看空信号和风险**
从上方数据中找出具体的 BEARISH 信号或风险，附带数值。
必须使用当前 regime 对应的解读规则 (例如 "support" 在趋势市场 vs 震荡市场含义不同)。
如果历史数据中有类似条件的失败做多案例，可以引用作为风险警告。

**第三步：构建论点**
提出 2-3 个反对做多 (或支持做空) 的有力理由。
用数据反驳 Bull 的论点。

**第四步：评估入场条件**
入场价为当前市场价 — 基于 S/R zones 和市场结构评估 R:R 比。

**第五步：陈述失效条件**
什么情况下你的看空论点会被推翻？
"""
        # v5.5: R2+ enhancement — force new arguments and direct rebuttals
        if history and bull_argument and "ROUND" in history:
            prompt += """
⚠️ 【第二轮辩论规则 — 必须遵守】
这是后续辩论轮次，不是 R1 的重复。你必须：
1. **直接引用并反驳** Bull 最新论点中的具体数据（如 "Bull 声称 RSI 反弹至 X，但实际 RSI 序列显示..."）
2. **提出至少 1 个 R1 中未使用的新证据或数据点**
3. **承认** Bull 论点中有道理的部分，然后解释为什么风险仍然大于收益
❌ 简单重复 R1 论点将被裁判忽略。
"""

        prompt += "\n请用 2-3 段落交付你的论点："

        # System prompt: Role + Indicator manual (v3.25: regime-aware)
        # v3.28: Chinese instructions for better DeepSeek instruction-following
        # v5.6: Adversarial mandate — structurally enforce opposition to Bull
        system_prompt = f"""你是 {symbol} 的专业空头分析师 (Bear Analyst) — 你的角色是辩论中的 **反方**。

🚨 【核心使命 — 你必须与 Bull 对立】
你的存在价值就是找出 Bull 看不到或故意忽视的风险。
- 如果 Bull 说 "做多"，你必须解释为什么做多是危险的
- 如果 Bull 引用某个指标支持多头，你必须找到该指标的弱点或相反解读
- 你**禁止**得出与 Bull 相同的方向结论
- 如果你真的找不到反对 Bull 的理由，你必须解释为什么当前不是好的入场时机 (timing risk)

🔍 【分析优先级 — 从宏观到微观】
你必须按此顺序分析数据，而不是从 15M 开始：
1. **1D 宏观趋势** — SMA_200 方向、ADX 趋势强度、MACD 趋势
2. **4H 中期动量** — RSI 位置、MACD 交叉、BB 位置
3. **15M 微观执行** — 仅用于入场时机判断

⚠️ 层级权重取决于 ADX 判定的市场环境:
- ADX > 40 (强趋势): 1D 趋势层主导，逆势信号需极强确认
- 25 < ADX < 40: 1D 趋势层重要但非绝对
- ADX < 20 (震荡市): 15M 关键水平层权重最高，均值回归信号有效

{INDICATOR_DEFINITIONS}

【关键规则 — 必须遵守】
⚠️ 你必须先判断 market regime (指标手册第一步)，然后用对应 regime 的规则解读所有指标。
⚠️ 在趋势市场使用震荡市场逻辑 (或反之) 是致命错误。
⚠️ 聚焦于 Bull 论点中最薄弱的环节 — 用数据拆解它。"""

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

### STEP 2: Confluence 多层对齐度评估 (必须填入 JSON 的 confluence 字段)
逐层评估每一层的方向倾向，填入 JSON 输出的 confluence 对象中：

| 层级 | 评估内容 | 填入字段 |
|------|---------|---------|
| 趋势层 (1D) | SMA200 位置, ADX/DI 方向, MACD | confluence.trend_1d |
| 动量层 (4H) | RSI, MACD, ADX, CVD | confluence.momentum_4h |
| 关键水平 (15M) | S/R zone, BB, Order Book | confluence.levels_15m |
| 衍生品数据 | Funding, OI, Liquidations | confluence.derivatives |

每层判定为 BULLISH / BEARISH / NEUTRAL，附简要理由。

⚠️ 层级权重取决于 1D ADX 判定的市场环境 (先完成 STEP 1 再评估):
- 强趋势 (ADX > 40): 趋势层主导，逆势信号需其他 3 层全部确认
- 弱趋势 (25 < ADX < 40): 趋势层重要但非绝对，2 层逆势确认即可考虑
- 震荡市 (ADX < 20): 关键水平层权重最高，均值回归信号有效，趋势层降权
- 挤压 (ADX < 20 + BB Width 收窄): 等待突破方向，不预判

对齐度规则 (基于 aligned_layers 计数):
- 3-4 层一致 → HIGH confidence 交易
- 2 层一致 → MEDIUM confidence 交易
- 0-1 层一致 → 应该 HOLD

### STEP 3: 总结双方核心论据
聚焦最有说服力的证据，不要罗列所有观点。

### STEP 4: 做出明确决策
- 你的建议 — LONG、SHORT 或 HOLD — 必须清晰可执行
- ‼️ 不要因为双方都有道理就默认 HOLD — 选择证据更强的一方
- 参考过去的失误教训，避免重复犯错
- confidence 必须与 aligned_layers 一致

## 📤 OUTPUT FORMAT (只输出 JSON，不要其他文字):
{{
    "confluence": {{
        "trend_1d": "BULLISH|BEARISH|NEUTRAL — 简要理由 (如: ADX=55 DI->DI+, 强下跌趋势)",
        "momentum_4h": "BULLISH|BEARISH|NEUTRAL — 简要理由 (如: RSI=60 偏多, MACD 金叉)",
        "levels_15m": "BULLISH|BEARISH|NEUTRAL — 简要理由 (如: 价格在 S1 支撑上方, BB 下轨触及)",
        "derivatives": "BULLISH|BEARISH|NEUTRAL — 简要理由 (如: FR 偏多, OI 下降)",
        "aligned_layers": 0
    }},
    "decision": "LONG|SHORT|HOLD",
    "winning_side": "BULL|BEAR|TIE",
    "confidence": "HIGH|MEDIUM|LOW",
    "rationale": "基于 confluence 分析的决策理由 (可以 2-4 句话充分说明)",
    "strategic_actions": ["Concrete step 1", "Concrete step 2"],
    "acknowledged_risks": ["risk1", "risk2"]
}}"""

        # v3.28: Chinese instructions + few-shot + confluence matrix for better DeepSeek performance
        system_prompt = f"""你是投资组合经理兼辩论裁判 (Portfolio Manager / Judge)。
批判性地评估辩论内容，做出果断的交易建议。选择证据更强的一方。从过去的错误中学习。

{INDICATOR_DEFINITIONS}

{SIGNAL_CONFIDENCE_MATRIX}

【关键规则 — 必须遵守】
⚠️ 用指标手册独立验证分析师是否使用了正确的 regime 解读。
⚠️ 参考信号置信度矩阵 (SIGNAL CONFIDENCE MATRIX) 量化评估每个信号在当前 regime 下的可靠性。
⚠️ 用中文进行内部推理分析，最终以 JSON 格式输出结果。
⚠️ 不要因为双方都有道理就默认 HOLD — 这是最常见的错误。

【正确决策示例 — Few-shot】

示例 1: 趋势一致 → 选择顺势方
情况: 1D ADX=33 上涨趋势, Bull 引用趋势+动量, Bear 引用 RSI 超买
分析: ADX>25 = TRENDING。Bear 用震荡市场逻辑 (RSI 70 = 超买) 在趋势市场中是错误的。
结果: {{"confluence":{{"trend_1d":"BULLISH — ADX=33 DI+>DI-, 明确上涨趋势","momentum_4h":"BULLISH — RSI=65 趋势范围内, MACD 正值","levels_15m":"BULLISH — 价格在 SMA20 上方, BB 上半部","derivatives":"NEUTRAL — FR 正常, OI 稳定","aligned_layers":3}},"decision":"LONG","winning_side":"BULL","confidence":"HIGH","rationale":"3 层一致看多，趋势层确认上涨。Bear 用震荡逻辑解读 RSI，在趋势市场中无效。","strategic_actions":["顺势做多，目标下一阻力位"],"acknowledged_risks":["ADX 可能见顶回落"]}}

示例 2: 强趋势中逆势信号 (ADX>40 → 趋势层主导)
情况: 1D 强下跌趋势 (ADX=45), 4H 出现 MACD 金叉, Bull 认为反转
分析: ADX=45 > 40 = 强趋势，趋势层主导。4H MACD 金叉在强下跌中可能是反弹而非反转。
结果: {{"confluence":{{"trend_1d":"BEARISH — ADX=45 DI->DI+, 强下跌趋势","momentum_4h":"BULLISH — MACD 金叉, RSI 回升至 55","levels_15m":"NEUTRAL — 价格在 range 中间","derivatives":"BEARISH — FR 负值, OI 下降","aligned_layers":2}},"decision":"SHORT","winning_side":"BEAR","confidence":"MEDIUM","rationale":"趋势层(1D)看空 + 衍生品看空 = 2 层一致。4H MACD 金叉在强下跌趋势中有 74-97% 假信号率，不足以推翻 1D。","strategic_actions":["等待反弹至阻力位后做空"],"acknowledged_risks":["4H 动量转多可能形成更大反弹"]}}

示例 3: 真正需要 HOLD 的情况
情况: ADX=12 (RANGING), 价格在 range 中间, 两方都没有强证据
分析: 震荡市场 + 无明确方向 + 无关键水平触及。等待价格到达 range 边缘。
结果: {{"confluence":{{"trend_1d":"NEUTRAL — ADX=12 无趋势","momentum_4h":"NEUTRAL — RSI=50 中性","levels_15m":"NEUTRAL — 价格在 range 中间，远离 S/R","derivatives":"NEUTRAL — FR 接近零, OI 无变化","aligned_layers":0}},"decision":"HOLD","winning_side":"TIE","confidence":"LOW","rationale":"0 层有明确方向，所有层级均为中性。等待价格触及 range 边缘再决策。","strategic_actions":["等待价格到达 range 边缘"],"acknowledged_risks":["可能错过突破"]}}

示例 4: 震荡市 → 关键水平层主导 (均值回归)
情况: 1D ADX=15 (RANGING), 价格触及 BB 下轨 + S1 支撑, RSI=28 超卖, 订单簿买墙
分析: ADX<20 = 震荡市，关键水平层权重最高。价格在强支撑 + BB 下轨 + RSI 超卖 = 均值回归信号。
      虽然 1D 趋势不明确，但震荡市中这正是关键水平层发挥作用的时候。
结果: {{"confluence":{{"trend_1d":"NEUTRAL — ADX=15 无趋势，SMA200 持平","momentum_4h":"BULLISH — RSI=32 超卖反弹, MACD 柱状图收敛","levels_15m":"BULLISH — 价格触及 S1 支撑 + BB 下轨, OBI=+0.8 买墙","derivatives":"NEUTRAL — FR 接近零, OI 稳定","aligned_layers":2}},"decision":"LONG","winning_side":"BULL","confidence":"MEDIUM","rationale":"ADX=15 震荡市中，关键水平层权重最高。价格触及强支撑 + BB 下轨 + RSI 超卖，均值回归概率高。趋势层中性不构成阻碍。","strategic_actions":["在 S1 支撑做多，目标 BB 中轨"],"acknowledged_risks":["若支撑被跌破，震荡区间可能转为下跌趋势"]}}

示例 5: 信号置信度矩阵 — 震荡市忽略 MACD，信任 S/R + RSI
情况: 1D ADX=16 (ADX<20 = 震荡), 4H MACD 金叉, 4H RSI=33 超卖, 价格触及 S1 (HIGH 强度), OBI change +0.25
分析: ADX<20 = 震荡市。查信号矩阵:
  Layer 1 (趋势): ADX<20 列全部 ≤0.7 → 趋势层 NEUTRAL (忽略)
  Layer 2 (动量): MACD 交叉在 ADX<20 = 0.3 (SKIP，几乎无效)。RSI 值在 ADX<20 = 1.2 (HIGH)。RSI=33 超卖 = 看多信号。
  Layer 3 (水平): S/R 测试在 ADX<20 = 1.3 (HIGH)。OBI change 在 ADX<20 = 1.2 (HIGH)。两个 HIGH 信号确认。
  Layer 4: FR 正常，OI 稳定 → NEUTRAL
  → 动量+水平 2 层看多，MACD 金叉被矩阵标为 SKIP 正确忽略。
结果: {{"confluence":{{"trend_1d":"NEUTRAL — ADX=16 无趋势，矩阵标记趋势层 SKIP","momentum_4h":"BULLISH — RSI=33 超卖 (矩阵 1.2=HIGH)，MACD 交叉忽略 (矩阵 0.3=SKIP)","levels_15m":"BULLISH — S1 支撑触及 (矩阵 1.3=HIGH) + OBI 变化+0.25 (矩阵 1.2=HIGH)","derivatives":"NEUTRAL — FR 正常, OI 稳定","aligned_layers":2}},"decision":"LONG","winning_side":"BULL","confidence":"MEDIUM","rationale":"ADX=16 震荡市。矩阵指导: MACD 在震荡中 SKIP (0.3)，RSI+S/R 在震荡中 HIGH (1.2-1.3)。2 层以 HIGH 信号看多。","strategic_actions":["在 S1 支撑做多，目标 BB 中轨"],"acknowledged_risks":["若 S1 被跌破，考虑出场"]}}

示例 6: 信号置信度矩阵 — 强趋势中反转信号被降级
情况: 1D ADX=48 DI->DI+ (强下跌), 4H RSI 出现看多背离, 4H MACD 仍为负值, S/R zone 被跌破, FR=+0.06%
分析: ADX=48 > 40 = 强趋势 (ADX>40 列)。查信号矩阵:
  Layer 1 (趋势): SMA200=1.3 + ADX/DI=1.2 + MACD=1.1 → 全部 HIGH，强看空
  Layer 2 (动量): RSI 背离在 ADX>40 = 0.6 (LOW)。RULE 6: 逆势信号需 2 个独立确认。RSI 背离只有 1 个 → 不足。MACD 仍为负=顺势。
  Layer 3 (水平): S/R breakout 在 ADX>40 = 1.3 (HIGH) → 确认下跌延续
  Layer 4: FR=+0.06% extreme (ADX>40 = 0.8)，适度看空。Group A: BEARISH (LOW)。
  → 趋势+水平+衍生品 3 层看空，RSI 背离被矩阵降为 LOW + RULE 6 否决。
结果: {{"confluence":{{"trend_1d":"BEARISH — ADX=48 DI->DI+, 趋势层全 HIGH (矩阵 1.1-1.3)","momentum_4h":"BEARISH — MACD 负值顺势 (矩阵 1.2)，RSI 背离被降级 (矩阵 0.6=LOW + RULE 6 需 2 确认)","levels_15m":"BEARISH — S/R 被跌破 (矩阵 1.3=HIGH，趋势延续确认)","derivatives":"BEARISH — FR +0.06% 拥挤多头 (矩阵 0.8=LOW)","aligned_layers":4}},"decision":"SHORT","winning_side":"BEAR","confidence":"HIGH","rationale":"ADX=48 强下跌。矩阵将 RSI 背离从 HIGH 降为 LOW (0.6)，加上 RULE 6 要求 2 个逆势确认但只有 1 个。4 层一致看空。","strategic_actions":["顺势做空，SL 设在上方阻力位"],"acknowledged_risks":["RSI 背离可能预示反弹，但单一 LOW 信号不构成改变决策的理由"]}}"""

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
            "confluence": {
                "trend_1d": "N/A — parse failure",
                "momentum_4h": "N/A — parse failure",
                "levels_15m": "N/A — parse failure",
                "derivatives": "N/A — parse failure",
                "aligned_layers": 0,
            },
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

                # v5.5: Add 1D trend layer data for Judge's independent verification
                # Previously 1D data was only in tech_summary (Bull/Bear debate text),
                # but Judge's key_metrics lacked it, preventing independent verification
                mtf_trend = technical_data.get('mtf_trend_layer')
                if mtf_trend and isinstance(mtf_trend, dict):
                    lines.append("")
                    lines.append("--- 1D MACRO TREND (weight depends on ADX regime) ---")
                    trend_sma200 = mtf_trend.get('sma_200')
                    if trend_sma200 is not None and trend_sma200 > 0 and current_price > 0:
                        pct_vs_sma200 = (current_price - trend_sma200) / trend_sma200 * 100
                        lines.append(f"1D SMA200: ${trend_sma200:,.2f} (Price vs SMA200: {pct_vs_sma200:+.2f}%)")
                    trend_adx = mtf_trend.get('adx')
                    trend_di_plus = mtf_trend.get('di_plus')
                    trend_di_minus = mtf_trend.get('di_minus')
                    trend_adx_regime = mtf_trend.get('adx_regime', '')
                    if trend_adx is not None:
                        adx_str = f"1D ADX: {trend_adx:.1f} ({trend_adx_regime})"
                        if trend_di_plus is not None and trend_di_minus is not None:
                            adx_str += f" | DI+: {trend_di_plus:.1f}, DI-: {trend_di_minus:.1f}"
                        lines.append(adx_str)
                    trend_rsi = mtf_trend.get('rsi')
                    if trend_rsi is not None:
                        lines.append(f"1D RSI: {trend_rsi:.1f}")
                    trend_macd = mtf_trend.get('macd')
                    if trend_macd is not None:
                        lines.append(f"1D MACD: {trend_macd:.4f}")
                    # v5.5: Explicit macro trend assessment for Judge
                    if trend_adx is not None and trend_di_plus is not None and trend_di_minus is not None:
                        if trend_adx > 25 and trend_di_minus > trend_di_plus:
                            if trend_sma200 and current_price > 0 and current_price < trend_sma200 * 0.85:
                                lines.append("⚠️ MACRO ASSESSMENT: RISK_OFF (strong 1D downtrend + price far below SMA200)")
                            else:
                                lines.append("⚠️ MACRO ASSESSMENT: BEARISH (1D ADX strong, DI- > DI+)")
                        elif trend_adx > 25 and trend_di_plus > trend_di_minus:
                            lines.append("MACRO ASSESSMENT: RISK_ON (strong 1D uptrend, DI+ > DI-)")
                        else:
                            lines.append("MACRO ASSESSMENT: NEUTRAL (1D trend not decisively strong)")

            if derivatives_data and isinstance(derivatives_data, dict):
                fr = derivatives_data.get('funding_rate', {})
                if isinstance(fr, dict):
                    fr_pct = fr.get('current_pct')
                    if fr_pct is not None:
                        predicted = fr.get('predicted_rate_pct')
                        fr_str = f"Funding Rate: {fr_pct:.5f}%"
                        if predicted is not None:
                            fr_str += f" (predicted: {predicted:.5f}%)"
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
        past_memories: str = "",  # v5.9: Past trade patterns
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

## 📚 PAST TRADE PATTERNS (SL/TP 执行质量参考)
{past_memories if past_memories else "No historical data yet."}

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
- ‼️ 最小 SL 距离 ≥ 1.0% (硬性门槛，低于此值会被系统拒绝并回退到 S/R 重算)
- ⚠️ 如果最近的 S/R zone 距入场价 < 1.0%，应选择更远的 zone 或改为 HOLD
- 参考 S/R Zone Proximity Alert（如有）作为 SL/TP 选择参考
- ‼️ **必须在 sl_zone 和 tp_zone 中标注你选择的 S/R zone** (如 "S1 $68,386 (HIGH)")
- ‼️ **必须在 rr_calculation 中展示完整计算过程**:
  1. Risk = |当前价格 - stop_loss| (精确到美元)
  2. Reward = |take_profit - 当前价格| (精确到美元)
  3. R/R = Reward ÷ Risk (保留两位小数)
  ⚠️ 请逐步验算，避免算术错误。系统会用代码独立校验你的 R/R

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

{SIGNAL_CONFIDENCE_MATRIX}

【核心原则 — 必须遵守】
✅ **信任 Judge 的方向判断** — Judge 已听完 Bull/Bear 4 轮辩论后做出决策，你不需要重新判断方向。
✅ 你的工作: 设定 SL/TP + 根据风险条件调整仓位大小。
✅ 参考信号置信度矩阵评估信号可靠性，用于调整仓位大小和 SL/TP 设定。
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

    def _compute_trend_verdict(self, data: Dict[str, Any]) -> str:
        """
        v5.6: Pre-compute 1D macro trend verdict and place it at TOP of technical report.

        This ensures AI reads the highest-weight timeframe FIRST, preventing
        the weight inversion bug where 15M data (presented first) dominates analysis.

        Returns
        -------
        str
            Formatted 1D TREND VERDICT block, or empty string if no 1D data.
        """
        mtf_trend = data.get('mtf_trend_layer')
        if not mtf_trend:
            return ""

        def tget(key, default=0):
            val = mtf_trend.get(key)
            return float(val) if val is not None else default

        sma_200 = tget('sma_200')
        macd_1d = tget('macd')
        macd_signal_1d = tget('macd_signal')
        rsi_1d = tget('rsi')
        adx_1d = tget('adx')
        di_plus_1d = tget('di_plus')
        di_minus_1d = tget('di_minus')
        adx_regime = mtf_trend.get('adx_regime', 'UNKNOWN')
        price = data.get('price', 0)

        # Determine macro assessment
        above_sma200 = price > sma_200 if sma_200 > 0 else None
        macd_bullish = macd_1d > macd_signal_1d
        di_bullish = di_plus_1d > di_minus_1d

        # Count bullish/bearish signals
        bull_count = sum([
            above_sma200 is True,
            macd_bullish,
            di_bullish,
            rsi_1d > 50,
        ])
        bear_count = 4 - bull_count

        if adx_1d < 20:
            regime = "RANGING (weak trend)"
            if bull_count >= 3:
                verdict = "NEUTRAL_BULLISH — No strong trend, slight bullish lean"
            elif bear_count >= 3:
                verdict = "NEUTRAL_BEARISH — No strong trend, slight bearish lean"
            else:
                verdict = "NEUTRAL — No clear macro direction"
        elif bull_count >= 3:
            if adx_1d >= 30:
                verdict = "STRONG_BULLISH — Clear uptrend with momentum"
            else:
                verdict = "BULLISH — Uptrend developing"
            regime = f"TRENDING ({adx_regime})"
        elif bear_count >= 3:
            if adx_1d >= 30:
                verdict = "STRONG_BEARISH — Clear downtrend with momentum"
            else:
                verdict = "BEARISH — Downtrend developing"
            regime = f"TRENDING ({adx_regime})"
        else:
            verdict = "MIXED — Conflicting macro signals"
            regime = f"TRANSITIONAL ({adx_regime})"

        pct_vs_sma = ((price / sma_200 - 1) * 100) if sma_200 > 0 else 0

        # Also include 4H mini-summary if available
        mtf_decision = data.get('mtf_decision_layer')
        decision_line = ""
        if mtf_decision:
            def dget(key, default=0):
                val = mtf_decision.get(key)
                return float(val) if val is not None else default
            rsi_4h = dget('rsi')
            macd_4h = dget('macd')
            macd_sig_4h = dget('macd_signal')
            adx_4h = dget('adx')
            adx_regime_4h = mtf_decision.get('adx_regime', 'N/A')
            decision_line = f"""
4H SNAPSHOT: RSI={rsi_4h:.1f} | MACD={macd_4h:.4f} vs Signal={macd_sig_4h:.4f} | ADX={adx_4h:.1f} ({adx_regime_4h})"""

        return f"""
╔══════════════════════════════════════════════════════════╗
║  1D MACRO TREND VERDICT (weight depends on ADX regime)   ║
╚══════════════════════════════════════════════════════════╝
VERDICT: {verdict}
REGIME: {regime}
- Price vs SMA_200: {pct_vs_sma:+.2f}% ({'ABOVE' if above_sma200 else 'BELOW' if above_sma200 is False else 'N/A'})
- 1D MACD: {macd_1d:.4f} vs Signal {macd_signal_1d:.4f} ({'BULLISH' if macd_bullish else 'BEARISH'})
- 1D RSI: {rsi_1d:.1f} ({'Above 50' if rsi_1d > 50 else 'Below 50'})
- 1D ADX: {adx_1d:.1f} | DI+ {di_plus_1d:.1f} / DI- {di_minus_1d:.1f} ({'Bulls lead' if di_bullish else 'Bears lead'})
{decision_line}
⚠️ Layer weights depend on ADX: Strong trend (ADX>40) → 1D dominant | Ranging (ADX<20) → 15M levels dominant
"""

    def _format_technical_report(self, data: Dict[str, Any]) -> str:
        """Format technical data for prompts."""
        if not data:
            return "Technical data not available"

        def safe_get(key, default=0):
            val = data.get(key)
            return float(val) if val is not None else default

        # v5.6: Prepend 1D TREND VERDICT at TOP of report so AI reads it first
        report = self._compute_trend_verdict(data)

        # Base report (15M execution layer data)
        # TradingAgents v3.6: Added period statistics for trend assessment
        period_hours = safe_get('period_hours')
        report += f"""
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
            # v5.6: Added ADX/DI to 4H section (was missing → AI blind to 4H trend strength)
            mtf_adx = mtf_safe_get('adx')
            mtf_di_plus = mtf_safe_get('di_plus')
            mtf_di_minus = mtf_safe_get('di_minus')
            mtf_adx_regime = mtf_decision.get('adx_regime', 'N/A')
            report += f"""
=== MARKET DATA (4H Timeframe) ===

MOMENTUM (4H):
- RSI: {mtf_rsi:.1f}
- MACD: {mtf_macd:.4f}
- MACD Signal: {mtf_safe_get('macd_signal'):.4f}

TREND STRENGTH (4H ADX):
- ADX(14): {mtf_adx:.1f} ({mtf_adx_regime})
- DI+: {mtf_di_plus:.1f}, DI-: {mtf_di_minus:.1f} → {'BULLISH' if mtf_di_plus > mtf_di_minus else 'BEARISH'} direction

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

MACD SIGNAL SERIES ({len(historical.get('macd_signal_trend', []))} values):
{format_all_values(historical.get('macd_signal_trend', []), ".4f")}

VOLUME SERIES ({len(volume_trend)} values, USDT, converted from {getattr(self, '_base_currency', 'BTC')}):
{format_all_values([v * p for v, p in zip(volume_trend, price_trend)] if price_trend and len(price_trend) == len(volume_trend) else volume_trend, ",.0f")}
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

        # Header (v5.4: show notional USDT value + dynamic base currency for cross-check)
        bc = getattr(self, '_base_currency', 'BTC')
        notional_usd = qty * avg_px if avg_px > 0 else 0
        lines.append(f"Side: {side} | Size: ${notional_usd:,.0f} ({qty:.4f} {bc}) | Entry: ${avg_px:,.2f}")
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

    def _build_current_conditions(
        self,
        technical_report: Optional[Dict[str, Any]],
        sentiment_report: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        v5.10: Build a conditions snapshot from raw analysis data for memory matching.

        Extracts the same fields that _format_entry_conditions() stores in conditions
        string, so scoring is apple-to-apple.
        """
        result: Dict[str, Any] = {}
        if technical_report:
            rsi = technical_report.get('rsi')
            if rsi is not None:
                result['rsi'] = float(rsi)

            macd = technical_report.get('macd')
            macd_signal = technical_report.get('macd_signal')
            if macd is not None and macd_signal is not None:
                result['macd'] = 'bullish' if float(macd) > float(macd_signal) else 'bearish'

            bb_pos = technical_report.get('bb_position')
            if bb_pos is not None:
                result['bb'] = float(bb_pos) * 100  # 0-1 → 0-100 to match stored format

        if sentiment_report:
            ls_ratio = sentiment_report.get('long_short_ratio')
            if ls_ratio is not None:
                try:
                    ratio = float(ls_ratio)
                    if ratio > 2.0:
                        result['sentiment'] = 'crowded_long'
                    elif ratio < 0.5:
                        result['sentiment'] = 'crowded_short'
                    else:
                        result['sentiment'] = 'neutral'
                except (ValueError, TypeError):
                    result['sentiment'] = 'neutral'

        # v5.11: Derive preliminary direction from MACD + RSI lean.
        # Direction (weight=3) is the highest-scored similarity dimension,
        # but the actual trade direction is unknown before the debate.
        # Use the technical lean so the dimension is not always zero.
        macd_lean = result.get('macd', '')
        rsi_val = result.get('rsi')
        if macd_lean:
            if macd_lean == 'bullish':
                result['direction'] = 'LONG'
            else:
                result['direction'] = 'SHORT'
        elif rsi_val is not None:
            result['direction'] = 'LONG' if rsi_val >= 50 else 'SHORT'

        return result

    # ── v5.10: Structured similarity matching for memory retrieval ──

    @staticmethod
    def _parse_conditions(conditions_str: str) -> Dict[str, str]:
        """
        Parse conditions string into structured fields.

        Input:  "price=$70,412, RSI=65, MACD=bullish, BB=72%, conf=HIGH, winner=bull, sentiment=neutral"
        Output: {"rsi": "65", "macd": "bullish", "bb": "72", "conf": "HIGH",
                 "sentiment": "neutral", "decision": ""}
        """
        result = {}
        if not conditions_str or conditions_str == 'N/A':
            return result
        for part in conditions_str.split(','):
            part = part.strip()
            if '=' not in part:
                continue
            key, val = part.split('=', 1)
            key = key.strip().lower()
            val = val.strip().rstrip('%')
            result[key] = val
        return result

    @staticmethod
    def _classify_rsi(rsi_val: float) -> str:
        if rsi_val < 35:
            return "oversold"
        if rsi_val > 65:
            return "overbought"
        return "neutral"

    @staticmethod
    def _classify_bb(bb_val: float) -> str:
        if bb_val < 30:
            return "low"
        if bb_val > 70:
            return "high"
        return "mid"

    @staticmethod
    def _classify_sentiment(raw: str) -> str:
        raw = raw.lower()
        if "crowded_long" in raw:
            return "crowded_long"
        if "crowded_short" in raw:
            return "crowded_short"
        return "neutral"

    def _score_memory(self, mem: Dict, current: Dict) -> float:
        """
        Score how similar a memory entry is to current market conditions.

        Dimensions and weights:
          direction  (LONG/SHORT)              : 3   — most important
          rsi_zone   (oversold/neutral/overbought) : 2
          macd       (bullish/bearish)          : 1
          bb_zone    (low/mid/high)             : 1
          sentiment  (crowded_long/neutral/crowded_short) : 1
          confidence (HIGH/MEDIUM/LOW)          : 0.5
          grade_value (A+/A→high, F→high for losses) : 1  — v5.11

        Returns 0..9.5 (higher = more similar / more instructive).
        """
        mem_cond = self._parse_conditions(mem.get('conditions', ''))
        if not mem_cond:
            return 0.0

        score = 0.0

        # Direction (from decision field, weight=3)
        cur_dir = current.get('direction', '').upper()
        mem_dir = mem.get('decision', '').upper()
        # Normalize BUY/SELL → LONG/SHORT
        dir_map = {'BUY': 'LONG', 'SELL': 'SHORT'}
        cur_dir = dir_map.get(cur_dir, cur_dir)
        mem_dir = dir_map.get(mem_dir, mem_dir)
        if cur_dir and mem_dir and cur_dir == mem_dir:
            score += 3.0

        # RSI zone (weight=2)
        try:
            cur_rsi_zone = self._classify_rsi(float(current.get('rsi', 50)))
            mem_rsi_zone = self._classify_rsi(float(mem_cond.get('rsi', 50)))
            if cur_rsi_zone == mem_rsi_zone:
                score += 2.0
            elif {cur_rsi_zone, mem_rsi_zone} != {"oversold", "overbought"}:
                score += 0.6  # adjacent zones
        except (ValueError, TypeError):
            pass

        # MACD direction (weight=1)
        cur_macd = current.get('macd', '').lower()
        mem_macd = mem_cond.get('macd', '').lower()
        if cur_macd and mem_macd and cur_macd == mem_macd:
            score += 1.0

        # BB zone (weight=1)
        try:
            cur_bb_zone = self._classify_bb(float(current.get('bb', 50)))
            mem_bb_zone = self._classify_bb(float(mem_cond.get('bb', 50)))
            if cur_bb_zone == mem_bb_zone:
                score += 1.0
            elif {cur_bb_zone, mem_bb_zone} != {"low", "high"}:
                score += 0.3
        except (ValueError, TypeError):
            pass

        # Sentiment (weight=1)
        cur_sent = self._classify_sentiment(current.get('sentiment', 'neutral'))
        mem_sent = self._classify_sentiment(mem_cond.get('sentiment', 'neutral'))
        if cur_sent == mem_sent:
            score += 1.0

        # Confidence (weight=0.5)
        cur_conf = current.get('conf', '').upper()
        mem_conf = mem_cond.get('conf', '').upper()
        if cur_conf and mem_conf and cur_conf == mem_conf:
            score += 0.5

        # v5.11: Grade instructive value (weight=1)
        # Among similar conditions, prefer memories with more extreme grades:
        #   Wins:  A+ (1.0) > A (0.7) > B (0.4) > C (0.2) — stronger wins teach more
        #   Losses: F (1.0) > D (0.3)                      — bigger failures warn more
        ev = mem.get('evaluation', {})
        grade = ev.get('grade', '') if ev else ''
        if grade:
            _grade_value = {
                'A+': 1.0, 'A': 0.7, 'B': 0.4, 'C': 0.2,
                'D': 0.3, 'F': 1.0,
            }
            score += _grade_value.get(grade, 0)

        return score

    def _get_past_memories(self, current_conditions: Optional[Dict[str, Any]] = None) -> str:
        """
        Get past decision memories formatted for AI learning.

        v5.10: Similarity-based retrieval.
        When current_conditions is provided AND memory pool >= 20 entries,
        scores each memory by structured similarity (RSI zone, MACD direction,
        BB position, sentiment, direction match) and returns the top-5 most
        similar successes + top-5 most similar failures.

        When memory pool < 20 entries, uses most-recent ordering (not enough
        data for meaningful similarity matching).

        Parameters
        ----------
        current_conditions : dict, optional
            Current market snapshot. Expected keys:
            rsi (float), macd (str), bb (float), sentiment (str),
            direction (str), conf (str).
        """
        if not self.decision_memory:
            return ""

        # Separate successes and failures
        successes = [m for m in self.decision_memory if m.get('pnl', 0) > 0]
        failures = [m for m in self.decision_memory if m.get('pnl', 0) <= 0]

        use_similarity = (
            current_conditions
            and len(self.decision_memory) >= 20
        )

        if use_similarity:
            # Score and rank by similarity
            scored_wins = sorted(
                successes,
                key=lambda m: self._score_memory(m, current_conditions),
                reverse=True,
            )
            scored_losses = sorted(
                failures,
                key=lambda m: self._score_memory(m, current_conditions),
                reverse=True,
            )
            selected_successes = scored_wins[:5]
            selected_failures = scored_losses[:5]
            retrieval_mode = "similarity"
        else:
            # Not enough data — use most recent
            selected_successes = successes[-5:] if successes else []
            selected_failures = failures[-5:] if failures else []
            retrieval_mode = "recent"

        lines = []

        if selected_successes:
            lines.append("SUCCESSFUL TRADES (learn from these):")
            for mem in selected_successes:
                conditions = mem.get('conditions', 'N/A')
                ev = mem.get('evaluation', {})
                grade = ev.get('grade', '')
                rr_str = f" R/R={ev.get('actual_rr', 0):.1f}:1" if ev else ""
                grade_str = f" [{grade}]" if grade else ""
                sim_str = ""
                if use_similarity:
                    sim = self._score_memory(mem, current_conditions)
                    sim_str = f" (sim={sim:.1f})"
                lines.append(
                    f"  ✅ {mem.get('decision')} → {mem.get('pnl', 0):+.2f}%{grade_str}{rr_str}{sim_str} | "
                    f"Conditions: {conditions}"
                )

        if selected_failures:
            lines.append("FAILED TRADES (avoid repeating):")
            for mem in selected_failures:
                conditions = mem.get('conditions', 'N/A')
                lesson = mem.get('lesson', 'N/A')
                ev = mem.get('evaluation', {})
                grade = ev.get('grade', '')
                exit_type = ev.get('exit_type', '')
                grade_str = f" [{grade}]" if grade else ""
                exit_str = f" via {exit_type}" if exit_type else ""
                sim_str = ""
                if use_similarity:
                    sim = self._score_memory(mem, current_conditions)
                    sim_str = f" (sim={sim:.1f})"
                lines.append(
                    f"  ❌ {mem.get('decision')} → {mem.get('pnl', 0):+.2f}%{grade_str}{exit_str}{sim_str} | "
                    f"Conditions: {conditions} | Lesson: {lesson}"
                )

        # Aggregate stats (always based on full history, not filtered)
        evaluated = [m for m in self.decision_memory if m.get('evaluation')]
        if len(evaluated) >= 5:
            grades = [m['evaluation'].get('grade', '?') for m in evaluated[-20:]]
            grade_counts: Dict[str, int] = {}
            for g in grades:
                grade_counts[g] = grade_counts.get(g, 0) + 1
            grade_summary = " ".join(f"{g}:{c}" for g, c in sorted(grade_counts.items()))

            correct = sum(1 for m in evaluated[-20:] if m['evaluation'].get('direction_correct'))
            total = len(evaluated[-20:])
            accuracy = round(correct / total * 100) if total > 0 else 0

            lines.append(f"\nTRADE QUALITY (last {total}): {grade_summary} | Direction accuracy: {accuracy}%")

        self.logger.info(
            f"📚 Memory retrieval: mode={retrieval_mode}, pool={len(self.decision_memory)}, "
            f"wins={len(selected_successes)}, losses={len(selected_failures)}"
        )

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
            Current BTC price for converting BTC-denominated data to USDT
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
                oi_usd = oi_btc * current_price if current_price > 0 else 0
                oi_trend = trends.get('oi_trend', 'N/A')
                bc = getattr(self, '_base_currency', 'BTC')
                # v5.4: USDT primary + base currency for cross-check
                if oi_usd >= 1e9:
                    parts.append(f"- Open Interest: ${oi_usd/1e9:.2f}B ({oi_btc:,.0f} {bc}) [Trend: {oi_trend}]")
                else:
                    parts.append(f"- Open Interest: ${oi_usd/1e6:.1f}M ({oi_btc:,.0f} {bc}) [Trend: {oi_trend}]")

                # v5.2: OI hourly history (price divergence analysis)
                # v5.4: Convert BTC series to USDT + base currency for cross-check
                oi_hist = data.get('open_interest_history')
                if oi_hist and oi_hist.get('history'):
                    oi_closes_btc = [float(h.get('c', 0)) for h in oi_hist['history']]
                    if len(oi_closes_btc) >= 2 and current_price > 0:
                        oi_closes_usd = [v * current_price for v in oi_closes_btc]
                        oi_series_str = " → ".join([f"${v/1e9:.2f}B" for v in oi_closes_usd])
                        oi_change_btc = oi_closes_btc[-1] - oi_closes_btc[0]
                        oi_change_usd = oi_closes_usd[-1] - oi_closes_usd[0]
                        oi_change_pct = (oi_change_usd / oi_closes_usd[0] * 100) if oi_closes_usd[0] != 0 else 0
                        parts.append(f"  OI History ({len(oi_closes_btc)}h): {oi_series_str}")
                        parts.append(f"  OI Change: ${oi_change_usd/1e6:+,.0f}M ({oi_change_btc:+,.0f} {bc}, {oi_change_pct:+.2f}%)")
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
                parts.append(f"- Last Settled Funding Rate: {settled_pct:.5f}%")

                # 预期费率 (from premiumIndex.lastFundingRate, 实时变化)
                predicted_pct = funding.get('predicted_rate_pct')
                if predicted_pct is not None:
                    parts.append(f"- Predicted Next Funding Rate: {predicted_pct:.5f}%")
                    # v5.2: Settled vs Predicted delta (key sentiment shift signal)
                    delta_pct = predicted_pct - settled_pct
                    direction = "↑ more bullish pressure" if delta_pct > 0 else "↓ more bearish pressure" if delta_pct < 0 else "→ stable"
                    parts.append(f"- Funding Delta (Predicted - Settled): {delta_pct:+.5f}% ({direction})")

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
                        [f"{r['rate_pct']:.5f}%" for r in history]
                    )
                    parts.append(f"- Funding History (last {len(history)}): {rates_str}")

                    # 趋势
                    trend = funding.get('trend', 'N/A')
                    if trend != 'N/A':
                        parts.append(f"- Funding Trend: {trend}")
            else:
                parts.append("- Funding Rate: N/A")

            # Liquidations (v3.24: expanded to 24h with history trend)
            # v5.4: USDT-primary display for consistent denomination
            liq = data.get('liquidations')
            if liq:
                history = liq.get('history', [])
                if history:
                    price_for_conversion = current_price if current_price > 0 else 88000

                    # Calculate 24h totals in USDT
                    total_long_btc = sum(float(h.get('l', 0)) for h in history)
                    total_short_btc = sum(float(h.get('s', 0)) for h in history)
                    total_long_usd = total_long_btc * price_for_conversion
                    total_short_usd = total_short_btc * price_for_conversion
                    total_btc = total_long_btc + total_short_btc
                    total_usd = total_long_usd + total_short_usd
                    bc = getattr(self, '_base_currency', 'BTC')

                    parts.append(f"- Liquidations (24h): ${total_usd:,.0f} ({total_btc:.4f} {bc})")
                    if total_usd > 0:
                        long_ratio = total_long_usd / total_usd
                        parts.append(f"  - Long Liq: ${total_long_usd:,.0f} ({total_long_btc:.4f} {bc}, {long_ratio:.0%})")
                        parts.append(f"  - Short Liq: ${total_short_usd:,.0f} ({total_short_btc:.4f} {bc}, {1-long_ratio:.0%})")

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
        bc = getattr(self, '_base_currency', 'BTC')

        parts.append("IMBALANCE:")
        parts.append(f"  Simple OBI: {simple_obi:+.2f}")
        parts.append(f"  Weighted OBI: {weighted_obi:+.2f} (decay={decay_used:.2f}, adaptive)")
        # v5.4: USDT-primary + base currency cross-check
        parts.append(f"  Bid Volume: ${bid_vol_usd/1e6:.1f}M ({bid_vol_btc:.1f} {bc})")
        parts.append(f"  Ask Volume: ${ask_vol_usd/1e6:.1f}M ({ask_vol_btc:.1f} {bc})")
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

            # v5.10: OBI trend array (oldest → newest) for multi-cycle analysis
            obi_trend = dynamics.get('obi_trend', [])
            if len(obi_trend) >= 2:
                trend_str = " → ".join(f"{v:+.2f}" for v in obi_trend[-5:])
                parts.append(f"  OBI Trend ({len(obi_trend)} samples): {trend_str}")
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
            bc = getattr(self, '_base_currency', 'BTC')
            parts.append(f"ANOMALIES (threshold={threshold:.1f}x, {threshold_reason}):")
            for anom in bid_anomalies[:3]:  # Show up to 3 per side
                price = _safe_float(anom.get('price', 0))
                amount_btc = _safe_float(anom.get('volume_btc', anom.get('amount', 0)))
                amount_usd = amount_btc * price if price > 0 else 0
                multiple = _safe_float(anom.get('multiplier', anom.get('multiple', 0)))
                # v5.4: USDT-primary + base currency cross-check
                vol_str = f"${amount_usd/1e6:.1f}M" if amount_usd >= 1e6 else f"${amount_usd/1e3:.0f}K"
                parts.append(f"  Bid: ${price:,.0f} @ {vol_str} ({amount_btc:.1f} {bc}, {multiple:.1f}x)")
            for anom in ask_anomalies[:3]:
                price = _safe_float(anom.get('price', 0))
                amount_btc = _safe_float(anom.get('volume_btc', anom.get('amount', 0)))
                amount_usd = amount_btc * price if price > 0 else 0
                multiple = _safe_float(anom.get('multiplier', anom.get('multiple', 0)))
                vol_str = f"${amount_usd/1e6:.1f}M" if amount_usd >= 1e6 else f"${amount_usd/1e3:.0f}K"
                parts.append(f"  Ask: ${price:,.0f} @ {vol_str} ({amount_btc:.1f} {bc}, {multiple:.1f}x)")
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
                bc = getattr(self, '_base_currency', 'BTC')
                # Show 1 unit slippage as the main indicator
                for side in ['buy', 'sell']:
                    key = f"{side}_1.0_btc"  # data key from order book processor
                    est = slippage.get(key, {})
                    if isinstance(est, dict) and est.get('estimated') is not None:
                        pct = _safe_float(est.get('estimated', 0))
                        conf = _safe_float(est.get('confidence', 0))
                        range_vals = est.get('range', [0, 0])
                        range_low = _safe_float(range_vals[0] if range_vals[0] is not None else 0)
                        range_high = _safe_float(range_vals[1] if range_vals[1] is not None else 0)
                        side_label = "Buy" if side == "buy" else "Sell"
                        parts.append(
                            f"  Slippage ({side_label} 1 {bc}): {pct:.2f}% "
                            f"[confidence={conf:.0%}, range={range_low:.2f}%-{range_high:.2f}%]"
                        )

        return "\n".join(parts)
