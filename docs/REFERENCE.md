# Quick Reference Card

## Essential Commands

```bash
# Setup (first time only)
./setup.sh

# Edit configuration
nano .env

# Run strategy (test mode)
python main_live.py

# Stop strategy
Ctrl+C
```

## Key Configuration (.env)

```bash
# Required
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
DEEPSEEK_API_KEY=your_key

# Important
EQUITY=10000                    # Trading capital
LEVERAGE=10                     # Position leverage
BASE_POSITION_USDT=100         # Base position size
TEST_MODE=false                # true=simulation, false=live

# Optional
MIN_CONFIDENCE_TO_TRADE=MEDIUM  # LOW/MEDIUM/HIGH
TIMER_INTERVAL_SEC=900         # 15 minutes
```

## Project Structure

```
nautilus_deepseek/
├── main_live.py              → Entry point
├── .env                      → Your API keys (create from .env.template)
├── configs/
│   └── strategy_config.yaml  → Strategy parameters
├── strategy/
│   └── deepseek_strategy.py  → Main strategy logic
├── indicators/
│   └── technical_manager.py  → Technical indicators
└── utils/
    ├── deepseek_client.py    → AI integration
    └── sentiment_client.py   → Sentiment data
```

## Strategy Flow

```
Every 15 minutes:
1. Get market data (price, volume, etc.)
2. Calculate indicators (SMA, RSI, MACD, BB)
3. Fetch sentiment data (bullish/bearish)
4. Analyze with DeepSeek AI → Generate signal
5. Execute trade if confident enough
```

## Signal Types

- **BUY**: Open long or add to long position
- **SELL**: Open short or add to short position
- **HOLD**: No action, maintain current position

## Confidence Levels

- **HIGH**: 1.5x position size multiplier
- **MEDIUM**: 1.0x position size multiplier
- **LOW**: 0.5x position size multiplier

## Position Sizing Formula

```
Final Size = Base × Confidence × Trend × RSI × Min(1, MaxRatio)

Example:
100 USDT × 1.5 (HIGH) × 1.2 (strong trend) × 1.0 (normal RSI) = 180 USDT
At BTC=$90k → 0.002 BTC position
```

## Log Symbols

- 🤖 AI signal generated
- 📊 Position sizing calculated
- 🚀 Opening new position
- 📈 Adding to position
- 📉 Reducing position
- 🔄 Reversing position
- ✅ Order filled successfully
- ❌ Error occurred
- ⚠️  Warning message

## Safety Checklist

Before going live:
- [ ] Test mode works
- [ ] API keys valid
- [ ] Binance set to cross-margin
- [ ] Leverage set to 10x
- [ ] USDT balance sufficient
- [ ] Understand position sizing
- [ ] Read full README.md

## Common Issues

| Issue | Solution |
|-------|----------|
| "DEEPSEEK_API_KEY not found" | Add to .env file |
| "Indicators not initialized" | Wait 30 minutes |
| "Order below minimum" | Increase BASE_POSITION_USDT |
| "WebSocket failed" | Check internet/VPN |

## Risk Warning

⚠️ **10x leverage amplifies both gains AND losses**

- Start small ($1000-$5000)
- Use test mode first
- Monitor closely
- Never risk more than you can afford to lose

## Emergency Stop

```bash
# In terminal running strategy
Ctrl+C

# Or close positions manually
Go to Binance Futures web interface → Close all positions
```

## Performance Monitoring

Watch for:
- Signal frequency (2-4 per day expected)
- Position size appropriateness
- Win rate over time
- Drawdown levels
- AI reasoning quality

## File Locations

- **Logs**: Console output (redirect to file if needed)
- **Config**: `configs/strategy_config.yaml`
- **Environment**: `.env`
- **Strategy**: `strategy/deepseek_strategy.py`

## Getting Help

1. Check error message in logs
2. Review README.md troubleshooting section
3. Verify API keys and permissions
4. Check Binance account settings
5. Consult NautilusTrader docs

## Key Differences from Original

| Original (OKX) | New (Binance/Nautilus) |
|----------------|------------------------|
| Single file | Modular architecture |
| Polling loop | Event-driven |
| Manual indicators | Built-in indicators |
| Direct API calls | NautilusTrader framework |

## Documentation Files

- `README.md` - Comprehensive documentation
- `QUICKSTART.md` - Quick start guide
- `PROJECT_SUMMARY.md` - Technical overview
- `REFERENCE.md` - This file

## Environment Variables Priority

1. `.env` file (highest)
2. `strategy_config.yaml`
3. Code defaults (lowest)

Use `.env` to override YAML settings without editing files.

## Timeframes

Default: 15-minute bars

To change:
```bash
# In .env
TIMEFRAME=5m   # 5 minutes
TIMEFRAME=1h   # 1 hour
```

## Leverage Settings

Set on Binance before running:
1. Open BTC/USDT perpetual
2. Click leverage indicator (e.g., "20x")
3. Set to desired leverage (1-125)
4. Must match `.env` LEVERAGE setting

## Order Types

- Market orders only (immediate execution)
- No limit orders
- No stop loss orders placed (calculated only)
- Reduce-only flag for position closes

## Position Modes

- Cross-margin (uses full account balance as collateral)
- One-way mode (not hedge mode)
- Must be configured on Binance before running

## Update Strategy

To modify trading logic:
1. Edit `strategy/deepseek_strategy.py`
2. Edit `configs/strategy_config.yaml`
3. Edit `.env` for parameter tweaks
4. Restart strategy

## Backup Original Settings

Before modifying:
```bash
cp .env .env.backup
cp configs/strategy_config.yaml configs/strategy_config.yaml.backup
```

---

**Quick Start:** `./setup.sh` → Edit `.env` → `python main_live.py`
