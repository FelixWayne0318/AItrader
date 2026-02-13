# Quick Start Guide

**For Experienced Traders** - Get running in 5 minutes ⚡

---

## Prerequisites Check

```bash
✅ Python 3.12+
✅ Binance Futures account with API key
✅ DeepSeek API key
✅ $500+ USDT in Futures wallet
✅ Basic Linux/terminal knowledge
```

---

## Installation (2 minutes)

### 1. Clone and Setup

```bash
cd /home/ubuntu
git clone <repo-url> nautilus_deepseek
cd nautilus_deepseek

# Create venv
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Create .env
cat > .env << 'EOF'
# Exchange
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here

# AI
DEEPSEEK_API_KEY=your_deepseek_key_here

# Trading
EQUITY=400
LEVERAGE=10
BASE_POSITION_USDT=30
TIMEFRAME=1m

# Risk
MIN_CONFIDENCE_TO_TRADE=MEDIUM
MAX_POSITION_RATIO=0.10
EOF

# Secure it
chmod 600 .env
```

### 3. Binance Setup

```bash
# Via Binance Web:
1. Navigate to: Futures → BTCUSDT-PERP
2. Set margin: CROSS (not isolated)
3. Set leverage: 10x
4. Verify balance: 400+ USDT
```

---

## Configuration (1 minute)

### Quick Config Review

```bash
# Check main config
cat configs/base.yaml | grep -A2 -E "equity|leverage|timer_interval"

# Should see:
#   equity: 400
#   leverage: 10
#   timer_interval_sec: 900
```

### Key Parameters

| Parameter | Default | Adjust For |
|-----------|---------|------------|
| `equity` | 400 | Your capital |
| `base_usdt_amount` | 30 | Position size |
| `max_position_ratio` | 0.10 | Max 10% per trade |
| `timer_interval_sec` | 900 | AI analysis frequency |
| `min_confidence_to_trade` | MEDIUM | Risk tolerance |

---

## Run (30 seconds)

### Option 1: Foreground (Testing)

```bash
# Development environment (1-minute bars, DEBUG logging)
python main_live.py --env development

# Production environment (15-minute bars, INFO logging)
python main_live.py --env production

# Validate config without starting (dry-run)
python main_live.py --env development --dry-run
```

**Expected Output:**
```
🚀 Starting DeepSeek AI Trading Strategy
✅ Environment loaded
✅ Binance credentials validated
✅ DeepSeek API key loaded
✅ Connecting to Binance Futures...
✅ Strategy started successfully
⏱️  Analysis timer: 900 seconds (15 minutes)
```

### Option 2: Background (Production)

```bash
# Start
nohup python main_live.py > logs/trader_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo $! > trader.pid

# Monitor
tail -f logs/trader_*.log

# Stop
kill $(cat trader.pid)
```

### Option 3: Helper Scripts

```bash
# Start
./start_trader.sh

# Restart
./restart_trader.sh

# Stop
./stop_trader.sh

# Status
./check_strategy_status.sh
```

---

## Monitor (Ongoing)

### Real-Time Monitoring

```bash
# Follow all logs
tail -f logs/trader.log

# Watch signals only
tail -f logs/trader.log | grep "🤖 Signal:"

# Check errors
tail -f logs/trader_error.log

# Last 10 signals
grep "🤖 Signal:" logs/trader.log | tail -10
```

### Key Log Patterns

**Successful Long Entry:**
```
🤖 Signal: BUY | Confidence: HIGH | Reason: (1) Strong uptrend...
📊 Position: Opening LONG 0.0008 BTC @ $70,125.50
✅ Order filled: 0.0008 BTC
```

**Position Adjustment:**
```
🤖 Signal: BUY | Confidence: MEDIUM | Reason: (1) Trend continuation...
📊 Signal: BUY - Adding to position
📈 Adding: 0.0004 BTC
```

**Hold Signal:**
```
🤖 Signal: HOLD | Confidence: MEDIUM | Reason: (1) Mixed signals...
📊 Signal: HOLD - No action taken
```

### Performance Tracking

```bash
# Count trades today
grep "Order filled" logs/trader.log | grep $(date +%Y-%m-%d) | wc -l

# View P&L mentions
grep -i "pnl\|profit\|loss" logs/trader.log | tail -20

# Signal distribution
grep "🤖 Signal:" logs/trader.log | grep -oE "Signal: \w+" | sort | uniq -c
```

### External Monitoring

- **Binance App**: Live P&L, positions
- **TradingView**: Chart analysis
- **Process Status**: `ps aux | grep main_live.py`

---

## Configuration Deep Dive

### Risk Profiles

#### Conservative
```yaml
# configs/base.yaml
risk:
  min_confidence_to_trade: "HIGH"
  require_high_confidence_for_reversal: true
  
position_management:
  base_usdt_amount: 20
  max_position_ratio: 0.05  # 5% max
```

#### Aggressive
```yaml
risk:
  min_confidence_to_trade: "LOW"
  require_high_confidence_for_reversal: false
  
position_management:
  base_usdt_amount: 50
  max_position_ratio: 0.20  # 20% max (⚠️ high risk)
```

### Timer Interval Options

```yaml
# Very active (⚠️ high API costs)
timer_interval_sec: 60  # 1 minute

# Default (recommended)
timer_interval_sec: 900  # 15 minutes

# Conservative (lower API costs)
timer_interval_sec: 1800  # 30 minutes
```

### Technical Indicator Tuning

```yaml
# For 1-minute bars (fast testing)
indicators:
  sma_periods: [3, 7, 15]
  rsi_period: 7
  macd_fast: 5
  macd_slow: 10

# For 15-minute bars (production)
indicators:
  sma_periods: [5, 20, 50]
  rsi_period: 14
  macd_fast: 12
  macd_slow: 26
```

---

## Troubleshooting (Common Issues)

### Issue: "Indicators not yet initialized"

**Cause**: Need 50+ bars for SMA(50)

**Solution**: Wait 50 minutes (1m bars) or 12 hours (15m bars)

```bash
# Check initialization
grep "initialized" logs/trader.log
```

### Issue: "Order quantity below minimum"

**Cause**: Position size < 0.001 BTC

**Solution**: Increase base position
```bash
# .env
BASE_POSITION_USDT=50  # Increase from 30

# At $70k BTC: 50/70000 = 0.000714 BTC ✅
```

### Issue: Running every 1 minute instead of 15

**Check**:
```bash
grep "Running periodic analysis" logs/trader.log | tail -5
```

**Fix**:
```bash
# Verify config
grep timer_interval_sec configs/base.yaml

# Should be: 900

# Restart
./restart_trader.sh
```

### Issue: Connection failures

**Quick Checks**:
```bash
# Test Binance connectivity
curl -I https://fapi.binance.com/fapi/v1/ping

# Test DNS
nslookup fstream.binance.com

# Check API key
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print('✅' if os.getenv('BINANCE_API_KEY') else '❌')"
```

### Issue: High CPU/Memory usage

**Check**:
```bash
# Monitor process
top -p $(pgrep -f main_live.py)

# Expected:
# CPU: 5-15%
# Memory: 200-500MB
```

**Optimize**:
```bash
# Increase timer interval
# Edit configs/base.yaml:
timer_interval_sec: 1800  # 30 minutes

# Restart
./restart_trader.sh
```

---

## Trading Logic Summary

### Position Sizing Formula

```python
Position = Base × Confidence × Trend × RSI × Min(1, Max_Ratio)

Where:
- Base: 30 USDT (config)
- Confidence: 1.5 (HIGH), 1.0 (MEDIUM), 0.5 (LOW)
- Trend: 1.2 (STRONG), 1.0 (others)
- RSI: 0.7 (extreme), 1.0 (normal)
- Max_Ratio: 10% of equity

Example:
30 × 1.5 × 1.2 × 1.0 = 54 USDT
Capped at 400 × 0.10 = 40 USDT
= 40 / 70000 = 0.000571 BTC
```

### Signal Flow

```
Every 15 minutes:
1. Collect market data (1-min bars)
2. Calculate technical indicators
3. Fetch sentiment data
4. Send to DeepSeek AI
5. Receive signal (BUY/SELL/HOLD)
6. Validate confidence
7. Calculate position size
8. Execute order (if validated)
9. Log results
```

### Position Management States

| Current | Signal | Action |
|---------|--------|--------|
| None | BUY | Open LONG |
| None | SELL | Open SHORT |
| LONG | BUY | Add/Maintain LONG |
| LONG | SELL | Reverse to SHORT (if allowed) |
| SHORT | SELL | Add/Maintain SHORT |
| SHORT | BUY | Reverse to LONG (if allowed) |
| Any | HOLD | No action |

---

## Performance Expectations

### Target Metrics

| Metric | Target | Notes |
|--------|--------|-------|
| Weekly Return | 0.5-1.0% | Net of fees |
| Max Drawdown | <5% | Peak to trough |
| Sharpe Ratio | >1.0 | Risk-adjusted |
| Win Rate | 55-65% | Profitable trades |

### Realistic Scenario (Monthly)

```
Starting Capital: $400
Average Return: 2-4% per month
Ending Range: $408-$416
Profit Range: $8-$16

Best Case: +6% ($424)
Worst Case: -2% ($392)
```

---

## API Costs Estimation

### DeepSeek AI API

```
Analysis interval: 15 minutes
Analyses per day: 96
Token usage: ~2000 tokens/analysis

Daily cost: 96 × $0.001 = ~$0.10
Monthly cost: ~$3

With 1-minute interval: ~$14/month (not recommended)
```

### Binance Trading Fees

```
Position size: 0.0008 BTC × $70,000 = $56
Taker fee: 0.04%
Fee per trade: $0.022

4 trades/day × $0.022 = $0.088/day
Monthly: ~$2.50

Note: Use limit orders when possible for 0.02% maker fee
```

---

## Security Checklist

```bash
# ✅ API key permissions
# - Enable: Futures trading, Read
# - Disable: Withdrawals, Transfer

# ✅ IP restrictions (optional but recommended)
# Add your server IP in Binance API settings

# ✅ File permissions
chmod 600 .env
chmod 700 *.sh

# ✅ .gitignore check
cat .gitignore | grep .env  # Should be listed

# ✅ API key test (without withdrawal)
# Place small test order first
```

---

## Optimization Tips

### For Lower Risk

```yaml
# 1. Increase confidence threshold
min_confidence_to_trade: "HIGH"

# 2. Reduce position sizes
base_usdt_amount: 20
max_position_ratio: 0.05

# 3. Require HIGH confidence for reversals
require_high_confidence_for_reversal: true

# 4. Increase timer interval
timer_interval_sec: 1800  # 30 minutes
```

### For Higher Frequency

```yaml
# 1. Reduce timer interval (⚠️ higher costs)
timer_interval_sec: 300  # 5 minutes

# 2. Lower confidence requirement
min_confidence_to_trade: "LOW"

# 3. Use faster indicators
indicators:
  sma_periods: [3, 7, 15]
  rsi_period: 7
```

### For Testing

```yaml
# 1. Very small positions
base_usdt_amount: 10
max_position_ratio: 0.02

# 2. HIGH confidence only
min_confidence_to_trade: "HIGH"

# 3. Frequent analysis for testing
timer_interval_sec: 60  # 1 minute
```

---

## Advanced: Custom Modifications

### Adjust AI Temperature

```python
# In main_live.py or configs/base.yaml
deepseek:
  temperature: 0.1  # Default (consistent)
  temperature: 0.3  # More creative/varied (⚠️ less predictable)
```

### Disable Sentiment Data

```yaml
# If CryptoOracle unavailable
sentiment:
  enabled: false

# Strategy uses technical-only mode (70% technical, 30% null)
```

### Custom Indicator Periods

```yaml
# For different market conditions
indicators:
  # Faster (trending markets)
  sma_periods: [3, 7, 15]
  rsi_period: 7
  
  # Slower (stable markets)
  sma_periods: [10, 30, 100]
  rsi_period: 21
```

### Multi-Timeframe (Advanced)

```bash
# Run multiple instances with different timeframes
# Terminal 1:
TIMEFRAME=1m python main_live.py

# Terminal 2 (different API keys or in sync)
TIMEFRAME=15m python main_live.py

# Requires separate config files and coordination
```

---

## Maintenance Schedule

### Daily

```bash
# Morning routine (2 minutes)
1. Check if running: ps aux | grep main_live
2. Review overnight signals: grep "🤖 Signal:" logs/trader.log | tail -20
3. Check for errors: tail -50 logs/trader_error.log
4. Verify Binance position matches: via app or web
```

### Weekly

```bash
# Weekend review (10 minutes)
1. Calculate weekly P&L
2. Review signal distribution (BUY/SELL/HOLD ratio)
3. Check win rate
4. Rotate logs: tar -czf logs_week_$(date +%W).tar.gz logs/*.log
5. Update dependencies: pip list --outdated
```

### Monthly

```bash
# Monthly optimization (30 minutes)
1. Full performance analysis
2. Adjust risk parameters if needed
3. Update packages: pip install --upgrade -r requirements.txt
4. Archive old logs
5. Review and optimize config
```

---

## Emergency Procedures

### Immediate Stop

```bash
# Method 1: Kill process
kill $(cat trader.pid)

# Method 2: Stop script
./stop_trader.sh

# Method 3: Keyboard interrupt (if in terminal)
Ctrl+C
```

### Close All Positions (Emergency)

```bash
# Via Binance Web:
1. Login → Futures → Positions
2. BTCUSDT-PERP → Close → Market Close

# Via Binance App:
Futures → Positions → Swipe to close
```

### Backup Before Changes

```bash
# Backup everything
tar -czf backup_$(date +%Y%m%d).tar.gz \
  configs/ \
  .env \
  logs/trader.log \
  strategy/

# Restore if needed
tar -xzf backup_YYYYMMDD.tar.gz
```

---

## Quick Reference Commands

```bash
# Status
ps aux | grep main_live.py                    # Check if running
tail -f logs/trader.log | grep "Signal:"      # Watch signals
grep "Order filled" logs/trader.log | wc -l   # Count trades

# Control
./start_trader.sh                             # Start
./restart_trader.sh                           # Restart
./stop_trader.sh                              # Stop

# Analysis
grep "🤖 Signal: BUY" logs/trader.log | wc -l     # Count BUYs
grep "🤖 Signal: SELL" logs/trader.log | wc -l    # Count SELLs
grep "🤖 Signal: HOLD" logs/trader.log | wc -l    # Count HOLDs
grep "unrealized_pnl" logs/trader.log | tail -20  # Recent P&L

# Maintenance
du -sh logs/                                  # Log size
df -h                                         # Disk space
free -h                                       # Memory
```

---

## Resources

### Documentation

- **Full README**: `README.md` - Complete guide
- **Strategy Logic**: `STRATEGY.md` - Trading algorithm details
- **Reference**: `REFERENCE.md` - API reference
- **Security**: `SECURITY.md` - Security best practices

### External

- **NautilusTrader**: https://nautilustrader.io/docs/
- **DeepSeek API**: https://platform.deepseek.com/docs
- **Binance Futures**: https://binance-docs.github.io/apidocs/futures/en/

### Support

1. Check logs first: `logs/trader_error.log`
2. Review troubleshooting section above
3. Check GitHub issues (if applicable)
4. Verify configuration: `configs/base.yaml`

---

## Final Checklist

Before going live:

```bash
✅ Environment configured (.env with valid API keys)
✅ Binance account setup (cross-margin, 10x leverage)
✅ USDT balance adequate (≥$500 recommended)
✅ Config reviewed (configs/base.yaml)
✅ Test run successful (indicators initialized)
✅ Monitoring setup (logs, alerts)
✅ Emergency procedures understood
✅ Risk limits comfortable
```

---

## Quick Start TL;DR

```bash
# 1. Install (2 min)
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Configure (1 min)
cp .env.template .env
nano .env  # Add API keys
chmod 600 .env

# 3. Binance setup (1 min)
# Web: Futures → BTCUSDT-PERP → Cross margin → 10x leverage

# 4. Run (30 sec)
python main_live.py
# OR
./start_trader.sh

# 5. Monitor
tail -f logs/trader.log

# Done! 🚀
```

---

**Remember**: 
- Start small
- Monitor closely first 24-48 hours
- Adjust risk parameters to your comfort level
- Never risk more than you can afford to lose

**Happy Trading! 📈**

---

*Quick Start Guide - Version 1.0 - November 2024*
