# DeepSeek AI Trading Strategy - Complete Logic Documentation

## Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [Strategy Flow](#strategy-flow)
- [Order Management (NEW: Bracket Orders)](#order-management-new-bracket-orders)
- [Risk Management](#risk-management)
- [Position Sizing](#position-sizing)
- [Trailing Stop Loss](#trailing-stop-loss)
- [Components](#components)
- [Configuration](#configuration)

---

## Overview

The **DeepSeek AI Trading Strategy** is an advanced algorithmic trading system for cryptocurrency futures that combines:

1. **AI-Powered Decision Making** - DeepSeek LLM analyzes market conditions
2. **Technical Analysis** - Multiple indicators (SMA, EMA, RSI, MACD, Bollinger Bands)
3. **Sentiment Analysis** - Real-time market sentiment data (optional)
4. **Automated Risk Management** - Bracket orders with SL/TP, trailing stops
5. **Remote Control** - Telegram bot for monitoring and commands

### Key Features After Refactoring

✅ **Built-in Bracket Orders (OCO + OTO)** - Replaced manual OCO management
✅ **Atomic Order Submission** - Entry, SL, and TP submitted together
✅ **Automatic OCO Handling** - NautilusTrader manages order cancellation
✅ **Simplified Codebase** - ~200 lines removed
✅ **More Reliable** - Framework-native order management

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DeepSeek AI Strategy                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   DeepSeek   │  │  Technical   │  │  Sentiment   │      │
│  │      AI      │  │  Indicators  │  │     Data     │      │
│  │   Analyzer   │  │   Manager    │  │   Fetcher    │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                  │                  │               │
│         └──────────────────┼──────────────────┘               │
│                            ▼                                  │
│                   ┌─────────────────┐                        │
│                   │ Signal Generator │                        │
│                   │  (BUY/SELL/HOLD) │                        │
│                   └────────┬─────────┘                        │
│                            ▼                                  │
│                   ┌─────────────────┐                        │
│                   │ Position Sizing  │                        │
│                   │   Calculator     │                        │
│                   └────────┬─────────┘                        │
│                            ▼                                  │
│                   ┌─────────────────┐                        │
│                   │ Bracket Order    │ ◄── NEW IMPLEMENTATION │
│                   │   Submission     │                        │
│                   └────────┬─────────┘                        │
│                            │                                  │
│         ┌──────────────────┼──────────────────┐              │
│         ▼                  ▼                  ▼              │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐          │
│  │  Entry   │      │   Stop   │      │   Take   │          │
│  │  Order   │      │   Loss   │      │  Profit  │          │
│  │ (MARKET) │      │  (STOP)  │      │ (LIMIT)  │          │
│  └──────────┘      └──────────┘      └──────────┘          │
│       │                  │                  │                │
│       └──────────────────┴──────────────────┘                │
│                          │                                   │
│                  OTO + OCO Linkage                           │
│              (Managed by NautilusTrader)                     │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

---

## Strategy Flow

### 1. Initialization (`on_start`)

```python
on_start() {
    1. Load instrument and validate configuration
    2. Initialize Technical Indicator Manager (SMA, RSI, MACD, BB)
    3. Initialize DeepSeek AI Analyzer
    4. Initialize Sentiment Fetcher (optional)
    5. Initialize Telegram Bot (optional)
    6. Subscribe to bar data (e.g., 15-minute bars)
    7. Set periodic timer (default: 15 minutes)
    8. Send startup notification to Telegram
}
```

### 2. Data Collection (`on_bar`)

```python
on_bar(bar) {
    1. Receive new bar data (OHLCV)
    2. Update all technical indicators:
       - Simple Moving Averages (5, 20, 50 period)
       - Exponential Moving Averages (12, 26 period)
       - RSI (14 period)
       - MACD (12, 26, 9)
       - Bollinger Bands (20 period, 2 std)
    3. Calculate support/resistance levels
    4. Store bar in rolling window
}
```

### 3. Periodic Analysis (`on_timer`)

Runs every 15 minutes (configurable):

```python
on_timer() {
    // Step 1: Data Preparation
    1. Check if indicators are initialized
    2. Get current market data:
       - Current price
       - Recent K-line data (10 bars)
       - Technical indicators
       - Price change %

    // Step 2: Sentiment Analysis (optional)
    3. Fetch sentiment data from external API
    4. Parse sentiment indicators

    // Step 3: AI Analysis
    5. Call DeepSeek AI with:
       - Price data
       - Technical data
       - Sentiment data
       - Current position info

    6. Receive AI signal:
       - signal: BUY / SELL / HOLD
       - confidence: HIGH / MEDIUM / LOW
       - reason: Detailed explanation

    // Step 4: Trade Execution
    7. If signal is BUY or SELL:
       a. Calculate position size
       b. Check risk parameters
       c. Execute trade with bracket order

    // Step 5: Maintenance
    8. Cleanup orphan orders (if any)
    9. Update trailing stops (if enabled)
    10. Send Telegram notifications
}
```

### 4. Trade Execution Flow

```python
_execute_trade(signal_data, price_data, technical_data, current_position) {

    // Step 1: Validate Signal
    1. Check minimum confidence threshold
       - If confidence < min_confidence: SKIP

    2. Handle HOLD signal:
       - Log and return

    // Step 2: Calculate Position Size
    3. Call _calculate_position_size():
       - Base amount: $100 USDT (configurable)
       - Confidence multiplier:
         * HIGH: 1.5x
         * MEDIUM: 1.0x
         * LOW: 0.5x
       - Trend strength multiplier: 1.2x (if strong trend)
       - RSI extreme adjustment: 0.7x (if RSI > 75 or < 25)
       - Max position: 10% of equity

    // Step 3: Position Management Logic
    4. If NO existing position:
       → _open_new_position()

    5. If existing position:
       → _manage_existing_position()
          - Same direction: Add to position
          - Opposite direction (reversal):
            * If allowed: Reverse position
            * If not allowed: Log warning
}
```

---

## Order Management (NEW: Bracket Orders)

### **NEW: Bracket Order Implementation**

The strategy now uses NautilusTrader's **built-in bracket orders** instead of manual OCO management.

#### What Changed?

| **Before** | **After** |
|------------|-----------|
| Submit entry order → Wait for fill → Submit SL/TP separately | Submit bracket order (entry + SL + TP) atomically |
| Manual OCO tracking with Redis | NautilusTrader handles OCO automatically |
| Manual peer order cancellation | Framework cancels peer orders |
| ~500 lines of OCO management code | ~200 lines using bracket orders |

#### Bracket Order Flow

```python
_submit_bracket_order(side, quantity) {

    // Step 1: Validate Parameters
    1. Check quantity >= min_trade_amount (0.001 BTC)
    2. Check if SL/TP enabled
    3. Validate signal/technical data available

    // Step 2: Calculate Prices
    4. Get current price estimate (from latest bar)

    5. Calculate Stop Loss:
       - For BUY: SL below support level (or 2% below entry)
       - For SELL: SL above resistance level (or 2% above entry)
       - Buffer: 0.1% (configurable)

    6. Calculate Take Profit:
       - Based on confidence:
         * HIGH: +3% profit
         * MEDIUM: +2% profit
         * LOW: +1% profit

    // Step 3: Create Bracket Order (with Emulation)
    7. Call OrderFactory.bracket():
       bracket_order_list = order_factory.bracket(
           instrument_id=instrument_id,
           order_side=side,                    // BUY or SELL
           quantity=quantity,                  // Position size
           sl_trigger_price=sl_price,          // Stop loss trigger
           tp_price=tp_price,                  // Take profit price
           time_in_force=GTC,                  // Good Till Cancel
           emulation_trigger=TriggerType.DEFAULT // Enable emulation (Binance compatibility)
       )

       IMPORTANT: Binance does NOT support native OCO+OTO orders.
       Using emulation_trigger makes NautilusTrader emulate the OCO/OTO logic
       locally instead of relying on exchange support.

    // Step 4: Submit Order List
    8. submit_order_list(bracket_order_list)

       This creates 3 linked orders:
       ┌─────────────────┐
       │  Entry (MARKET) │ ← Parent Order
       └────────┬────────┘
                │ OTO (One-Triggers-Other)
                ├──────────────┬──────────────┐
                ▼              ▼
       ┌──────────────┐  ┌──────────────┐
       │ SL (STOP)    │  │ TP (LIMIT)   │ ← Child Orders
       └──────────────┘  └──────────────┘
                │              │
                └──────OCO─────┘ (One-Cancels-Other)

    // Step 5: Initialize Trailing Stop State
    9. Extract SL order from bracket
    10. Save to trailing_stop_state:
        - entry_price
        - sl_order_id
        - current_sl_price
        - side (LONG/SHORT)
}
```

#### Order Lifecycle (Emulated Mode)

```
1. ENTRY ORDER SUBMITTED
   └─> Sent to Binance as normal MARKET order
       └─> SL and TP orders held in OrderEmulator (not sent to exchange yet)

2. ENTRY FILLS
   └─> OrderEmulator detects fill
       └─> Emulator ACTIVATES child orders (OTO logic)
           ├─> SL order submitted to Binance as STOP_MARKET
           └─> TP order submitted to Binance as LIMIT

3. If TP FILLS
   └─> OrderEmulator detects fill
       └─> Emulator automatically CANCELS SL order (OCO logic)
           └─> Cancel request sent to Binance

4. If SL FILLS
   └─> OrderEmulator detects fill
       └─> Emulator automatically CANCELS TP order (OCO logic)
           └─> Cancel request sent to Binance

5. Strategy receives fill events
   └─> Updates Telegram notifications
   └─> Logs order status

Why Emulation is Needed:
- Binance does NOT support native OCO contingency with conditional orders
- OrderEmulator handles OTO+OCO logic client-side
- Provides same functionality without exchange support
- More reliable than manual management
```

### Event Handlers

```python
on_order_filled(event) {
    1. Log fill details
    2. Send Telegram notification
    // Note: OCO cancellation handled automatically by NautilusTrader
    // No manual peer order cancellation needed
}

on_position_opened(event) {
    1. Log position opened
    2. Update trailing stop state with actual entry price
    3. Send Telegram notification
    // Note: SL/TP already submitted via bracket order
}

on_position_closed(event) {
    1. Log position closed
    2. Clear trailing stop state
    3. Send Telegram notification
}
```

---

## Risk Management

### Stop Loss Calculation

```python
Calculate SL Price {
    if (side == BUY):
        if (sl_use_support_resistance && support > 0):
            sl_price = support * (1 - sl_buffer_pct)
        else:
            sl_price = entry_price * 0.98  // 2% below entry

    else if (side == SELL):
        if (sl_use_support_resistance && resistance > 0):
            sl_price = resistance * (1 + sl_buffer_pct)
        else:
            sl_price = entry_price * 1.02  // 2% above entry
}
```

### Take Profit Calculation

```python
Calculate TP Price {
    tp_pct = confidence_based_tp_percentage

    if (side == BUY):
        tp_price = entry_price * (1 + tp_pct)

    else if (side == SELL):
        tp_price = entry_price * (1 - tp_pct)

    Confidence-based TP:
    - HIGH:   3% profit
    - MEDIUM: 2% profit
    - LOW:    1% profit
}
```

### Reversal Protection

```python
Check Reversal {
    if (signal_side != position_side):
        if (!allow_reversals):
            LOG WARNING and SKIP

        if (require_high_confidence && confidence != HIGH):
            LOG WARNING and SKIP
}
```

---

## Position Sizing

### Dynamic Position Sizing Algorithm

```python
_calculate_position_size(signal_data, price_data, technical_data, current_position) {

    // Base Amount
    base_usdt = $100  // Configurable

    // 1. Confidence Multiplier
    conf_mult = {
        'HIGH': 1.5,
        'MEDIUM': 1.0,
        'LOW': 0.5
    }[confidence]

    // 2. Trend Strength Multiplier
    trend = technical_data.overall_trend
    trend_mult = 1.0

    if (trend == '强势上涨' || trend == '强势下跌'):
        trend_mult = 1.2

    // 3. RSI Extreme Adjustment
    rsi = technical_data.rsi
    rsi_mult = 1.0

    if (rsi > 75 || rsi < 25):  // Extreme overbought/oversold
        rsi_mult = 0.7  // Reduce position size

    // 4. Calculate Target USDT
    target_usdt = base_usdt * conf_mult * trend_mult * rsi_mult

    // 5. Apply Max Position Ratio
    max_usdt = equity * leverage * max_position_ratio
    target_usdt = min(target_usdt, max_usdt)

    // 6. Convert to BTC Quantity
    btc_quantity = target_usdt / current_price

    // 7. Apply Minimum Trade Amount
    if (btc_quantity < min_trade_amount):
        return 0  // Skip trade

    return btc_quantity
}
```

### Example Calculation

```
Inputs:
- Base USDT: $100
- Confidence: HIGH → 1.5x
- Trend: 强势上涨 → 1.2x
- RSI: 45 (normal) → 1.0x
- Price: $95,000
- Equity: $10,000
- Leverage: 10x
- Max Position Ratio: 10%

Calculation:
target_usdt = $100 * 1.5 * 1.2 * 1.0 = $180
max_usdt = $10,000 * 10 * 0.10 = $10,000
final_usdt = min($180, $10,000) = $180

btc_quantity = $180 / $95,000 = 0.001895 BTC

Result: Trade 0.001895 BTC (~$180)
```

---

## Trailing Stop Loss

### How It Works

The trailing stop automatically adjusts the stop loss as the position becomes profitable.

```python
_update_trailing_stops(current_price) {

    state = trailing_stop_state[instrument]

    // Step 1: Calculate Profit %
    if (side == LONG):
        profit_pct = (current_price - entry_price) / entry_price

        // Track highest price
        if (current_price > highest_price):
            highest_price = current_price

        // Step 2: Activate Trailing Stop
        if (!activated && profit_pct >= activation_threshold):
            activated = True  // Default: 1% profit

        // Step 3: Update Stop Loss
        if (activated):
            new_sl_price = highest_price * (1 - trailing_distance_pct)
            // Default: 0.5% below highest

            // Only update if significant move
            if (new_sl_price > current_sl_price + threshold):
                _execute_trailing_stop_update(new_sl_price)

    else if (side == SHORT):
        profit_pct = (entry_price - current_price) / entry_price

        // Track lowest price
        if (current_price < lowest_price):
            lowest_price = current_price

        if (!activated && profit_pct >= activation_threshold):
            activated = True

        if (activated):
            new_sl_price = lowest_price * (1 + trailing_distance_pct)

            if (new_sl_price < current_sl_price - threshold):
                _execute_trailing_stop_update(new_sl_price)
}
```

### Trailing Stop Update Process

```python
_execute_trailing_stop_update(new_sl_price) {
    1. Log update details

    2. Cancel old SL order:
       - Find old SL order in cache
       - Call cancel_order(old_sl_order)

    3. Submit new SL order:
       - Create new STOP_MARKET order at new_sl_price
       - Set reduce_only = True
       - Submit order

    4. Update state:
       - current_sl_price = new_sl_price
       - sl_order_id = new_sl_order.client_order_id

    // Note: OCO relationship with TP is maintained automatically
    //       by NautilusTrader when new SL is submitted
}
```

### Example Scenario

```
Entry: BUY at $95,000
Initial SL: $93,100 (2% below)
Initial TP: $97,850 (3% above)

Price moves up:
$95,000 → $96,000 (+1.05% profit)
└─> Trailing stop ACTIVATED

$96,000 → $97,000 (+2.11% profit)
└─> New SL: $97,000 * (1 - 0.005) = $96,515
└─> Old SL ($93,100) cancelled
└─> New SL submitted at $96,515

$97,000 → $98,000 (+3.16% profit)
└─> New SL: $98,000 * (1 - 0.005) = $97,510
└─> SL updated to $97,510

Price retraces to $97,510:
└─> SL fills, position closed
└─> Profit locked: +$2,510 (2.64%)
└─> TP order auto-cancelled by OCO
```

---

## Components

### 1. Technical Indicator Manager

Manages all technical analysis calculations:

```python
TechnicalIndicatorManager {
    Indicators:
    - SMA (5, 20, 50 period)
    - EMA (12, 26 period)
    - RSI (14 period)
    - MACD (12, 26, 9)
    - Bollinger Bands (20, 2)

    Methods:
    - update(bar): Update all indicators with new bar
    - is_initialized(): Check if enough data
    - get_technical_data(): Get formatted indicator values
    - get_kline_data(): Get recent K-line data
    - calculate_support_resistance(): Dynamic S/R levels
}
```

### 2. DeepSeek AI Analyzer

AI-powered market analysis:

```python
DeepSeekAnalyzer {
    Configuration:
    - Model: deepseek-chat
    - Temperature: 0.1 (low = more deterministic)
    - Max Retries: 2

    analyze(price_data, technical_data, sentiment_data, position):
        → Returns:
          {
              "signal": "BUY" | "SELL" | "HOLD",
              "confidence": "HIGH" | "MEDIUM" | "LOW",
              "reason": "Detailed explanation..."
          }

    Considers:
    - Price trends and momentum
    - Technical indicator alignment
    - Support/resistance levels
    - Market sentiment
    - Current position (if any)
    - Risk/reward ratio
}
```

### 3. Sentiment Data Fetcher (Optional)

Fetches market sentiment from external APIs:

```python
SentimentDataFetcher {
    fetch():
        → Returns sentiment metrics:
          {
              "fear_greed_index": 0-100,
              "social_sentiment": "bullish" | "bearish",
              "trending_topics": [...],
              "volume_sentiment": float
          }
}
```

### 4. Telegram Bot (Optional)

Remote monitoring and control:

```python
TelegramBot {
    Features:
    - Startup notifications
    - Trade signal alerts
    - Order fill notifications
    - Position updates
    - Error alerts

    Commands:
    /status  - Get strategy status
    /position - Get current position
    /pause   - Pause trading
    /resume  - Resume trading
}
```

---

## Configuration

### Strategy Configuration Example

```yaml
# Instrument
instrument_id: "BTCUSDT-PERP.BINANCE"
bar_type: "BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-EXTERNAL"

# Capital
equity: 10000.0        # Starting capital
leverage: 10.0         # Leverage

# Position Sizing
base_usdt_amount: 100.0
high_confidence_multiplier: 1.5
medium_confidence_multiplier: 1.0
low_confidence_multiplier: 0.5
max_position_ratio: 0.10     # Max 10% of capital per trade
min_trade_amount: 0.001      # Minimum BTC

# Technical Indicators
sma_periods: [5, 20, 50]
rsi_period: 14
macd_fast: 12
macd_slow: 26
bb_period: 20
bb_std: 2.0

# AI Configuration
deepseek_api_key: "your-api-key"
deepseek_model: "deepseek-chat"
deepseek_temperature: 0.1

# Risk Management
min_confidence_to_trade: "MEDIUM"
allow_reversals: true
require_high_confidence_for_reversal: false

# Stop Loss & Take Profit
enable_auto_sl_tp: true
sl_use_support_resistance: true
sl_buffer_pct: 0.001         # 0.1% buffer
tp_high_confidence_pct: 0.03  # 3% profit
tp_medium_confidence_pct: 0.02 # 2% profit
tp_low_confidence_pct: 0.01   # 1% profit

# Bracket Orders (NEW)
enable_oco: true             # Enable OCO via bracket orders

# Trailing Stop
enable_trailing_stop: true
trailing_activation_pct: 0.01   # Activate at 1% profit
trailing_distance_pct: 0.005    # Keep 0.5% below peak
trailing_update_threshold_pct: 0.002  # Update every 0.2% move

# Telegram
enable_telegram: true
telegram_bot_token: "your-bot-token"
telegram_chat_id: "your-chat-id"
telegram_notify_signals: true
telegram_notify_fills: true
telegram_notify_positions: true
telegram_notify_errors: true

# Timing
timer_interval_sec: 900      # 15 minutes
```

---

## Summary of Bracket Order Benefits

### Before (Manual OCO)

❌ Complex manual order tracking
❌ Separate SL/TP submission after entry
❌ Custom Redis-based OCO management
❌ Manual peer order cancellation
❌ Race conditions possible
❌ ~500 lines of management code

### After (Built-in Bracket Orders)

✅ Simple, atomic order submission
✅ Entry + SL + TP submitted together
✅ NautilusTrader manages OCO automatically
✅ Framework handles cancellation
✅ No race conditions
✅ ~200 lines using bracket orders
✅ More reliable and maintainable
✅ Better venue compatibility

---

## Conclusion

The refactored strategy leverages **NautilusTrader's built-in bracket order functionality** for superior risk management and code simplicity. By combining AI-powered analysis, technical indicators, and automated order management, the strategy provides a robust, production-ready trading system.

**Key Advantages:**
- 🤖 AI-driven decision making
- 📊 Multi-factor technical analysis
- 🎯 Intelligent position sizing
- 🛡️ Automated risk management via bracket orders
- 📱 Remote monitoring and control
- 🔄 Dynamic trailing stops
- ⚡ Reliable, framework-native execution

---

**Generated with Claude Code** | Last Updated: 2025-11-11
