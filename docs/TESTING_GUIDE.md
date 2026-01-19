# Professional Testing Guide for DeepSeek Trading Strategy

This guide outlines professional software testing methodologies for trading systems.

## Table of Contents

1. [Testing Pyramid](#testing-pyramid)
2. [Unit Tests](#unit-tests)
3. [Integration Tests](#integration-tests)
4. [Manual Testing](#manual-testing)
5. [Testnet Testing](#testnet-testing)
6. [Live Testing](#live-testing)

---

## Testing Pyramid

Professional trading systems follow the **testing pyramid** approach:

```
                 /\
                /  \    Live Testing
               /____\   (minimal, small amounts)
              /      \
             /        \   Testnet Testing
            /__________\  (safe, real API)
           /            \
          /              \  Integration Tests
         /________________\ (mocked APIs)
        /                  \
       /                    \  Unit Tests
      /______________________\ (isolated functions)
```

### Why This Approach?

1. **Unit Tests** (70% of tests)
   - Fast, cheap, run frequently
   - Test individual functions in isolation
   - No real money at risk

2. **Integration Tests** (20% of tests)
   - Test component interactions
   - Use mocked APIs (no real network calls)
   - Verify data flow

3. **Testnet Testing** (9% of tests)
   - Real API calls, fake money
   - Test exchange integration
   - Verify order mechanics

4. **Live Testing** (1% of tests)
   - Real money, minimal amounts
   - Final validation only
   - Production monitoring

---

## Unit Tests

Test individual functions in isolation with mocked dependencies.

### Running Unit Tests

```bash
cd /home/ubuntu/nautilus_deepseek

# Run unit tests
python tests/test_strategy_components.py

# Expected output:
# ✅ Position sizing: 0.001097 BTC ($100.00) >= $100 minimum
# ✅ Confidence scaling: LOW < MEDIUM < HIGH
# ✅ DeepSeek response parsing: signal=BUY, confidence=HIGH
# Results: 5 passed, 0 failed
```

### What Unit Tests Cover

- ✅ Position sizing respects $100 minimum notional
- ✅ Position size scales with confidence (LOW < MEDIUM < HIGH)
- ✅ DeepSeek AI response parsing
- ✅ Stop loss calculation uses support levels
- ✅ Take profit scales with confidence

### Writing New Unit Tests

```python
def test_my_new_feature():
    """Test description."""
    # Arrange: Set up test data
    strategy = create_mock_strategy()

    # Act: Call function
    result = strategy.my_function(test_input)

    # Assert: Verify result
    assert result == expected_value, "Error message"
```

---

## Integration Tests

Test component interactions with mocked external APIs.

### Running Integration Tests

```bash
# Run integration tests (mocked APIs)
python tests/test_integration_mock.py

# Expected output:
# 📊 Step 1: Generating mock Binance data...
# 📈 Step 2: Calculating mock technical indicators...
# 🤖 Step 3: Mocking DeepSeek AI analysis...
# 💰 Step 4: Calculating position size...
# 📝 Step 5: Creating bracket order...
# ✅ Step 6: Validating order...
# Results: 2 passed, 0 failed
```

### What Integration Tests Cover

- ✅ Full flow: Binance → Indicators → AI → Order
- ✅ Order validation (notional, SL, TP)
- ✅ Pre/post hotfix scenarios
- ✅ Error handling

---

## Manual Testing

For step-by-step debugging and verification.

### Dry Run (Recommended First Step)

```bash
# Test order logic without placing real orders
python tests/manual_order_test.py --dry-run --signal BUY

# Output shows:
# Step 1: Testing Binance Connection
# Step 2: Fetching Live Market Data
# Step 3: Calculating Technical Indicators
# Step 4: Creating Forced BUY Signal
# Step 5: Calculating Order Parameters
# Step 6: Submitting Order (DRY RUN - no real order)
```

### Manual Test Options

```bash
# Dry run with forced BUY signal
python tests/manual_order_test.py --dry-run --signal BUY --confidence HIGH

# Dry run with SELL signal
python tests/manual_order_test.py --dry-run --signal SELL --confidence MEDIUM

# Test with testnet (safe)
python tests/manual_order_test.py --testnet --signal BUY
```

### ⚠️ What NOT to Do

```bash
# ❌ NEVER test on live exchange during development
python tests/manual_order_test.py --live-danger --signal BUY
# This is DANGEROUS and can lose real money!
```

---

## Testnet Testing

Use Binance Futures Testnet for safe API testing.

### Setting Up Binance Testnet

1. **Create Testnet Account**
   - Visit: https://testnet.binancefuture.com/
   - Create account (separate from live account)
   - Get free test USDT from faucet

2. **Generate API Keys**
   - Go to API Management
   - Create new API key
   - Save API Key and Secret

3. **Configure Environment**

Create `.env.testnet`:

```bash
# Binance Testnet Configuration
BINANCE_TESTNET_API_KEY=your_testnet_api_key_here
BINANCE_TESTNET_API_SECRET=your_testnet_secret_here

# Testnet endpoints
BINANCE_TESTNET_BASE_URL=https://testnet.binancefuture.com

# Same strategy config as production
EQUITY=10000
BASE_POSITION_USDT=100
TIMEFRAME=5m
```

4. **Run with Testnet**

```bash
# Load testnet environment
export $(cat .env.testnet | xargs)

# Run manual test
python tests/manual_order_test.py --testnet --signal BUY

# Or modify main_live.py to use testnet endpoints
```

### Testnet Benefits

- ✅ Real API calls (tests connectivity)
- ✅ Fake money (no risk)
- ✅ Test order mechanics
- ✅ Verify exchange integration
- ✅ Debug rate limits

### Testnet Limitations

- ⚠️ Market data may differ from production
- ⚠️ Liquidity may be different
- ⚠️ Some features may not work identically

---

## Live Testing

**Only after passing all previous test levels!**

### Prerequisites

- ✅ All unit tests pass
- ✅ All integration tests pass
- ✅ Dry run tests completed
- ✅ Testnet testing successful
- ✅ Code reviewed
- ✅ Risk limits configured

### Live Testing Protocol

1. **Start with Minimum Size**
   ```bash
   # Use absolute minimum ($100 notional)
   BASE_POSITION_USDT=100
   ```

2. **Enable Kill Switch**
   - Set maximum daily loss limit
   - Set maximum position size
   - Enable Telegram alerts

3. **Monitor Closely**
   ```bash
   # Watch logs in real-time
   tail -f logs/trader.log

   # Check for errors
   grep -i "error\|reject" logs/trader.log
   ```

4. **Verify First Order**
   - Check order was accepted
   - Verify notional >= $100
   - Confirm SL/TP placement
   - Monitor execution

5. **Gradual Scale-Up**
   - Only increase size after multiple successful trades
   - Never exceed risk limits
   - Keep position size small until proven

### Safety Checklist

Before live trading:

- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Dry run completed
- [ ] Testnet tested
- [ ] Stop loss configured
- [ ] Position limits set
- [ ] Telegram alerts enabled
- [ ] Emergency stop procedure documented
- [ ] Account balance is acceptable loss
- [ ] Trading logic reviewed

---

## Debugging Workflow

### When You Want to Test a Specific Function

**DON'T:** Set breakpoints in live trading code
**DO:** Write a unit test

```python
# tests/test_my_feature.py
def test_specific_function():
    strategy = create_mock_strategy()
    result = strategy.my_function(test_input)
    assert result == expected
```

### When You Want to Test Order Placement

**DON'T:** Force signals in live trading
**DO:** Use dry run script

```bash
python tests/manual_order_test.py --dry-run --signal BUY
```

### When You Want to Test with Real API

**DON'T:** Test on live exchange
**DO:** Use Binance Testnet

```bash
python tests/manual_order_test.py --testnet --signal BUY
```

### When You Want to Verify Live Trading

**DON'T:** Test with large amounts
**DO:** Use minimum size and monitor

```bash
# Set minimum position
BASE_POSITION_USDT=100

# Restart with monitoring
sudo systemctl restart deepseek-trader.service
tail -f logs/trader.log
```

---

## Best Practices

### ✅ DO

1. Write unit tests for new features
2. Run tests before committing code
3. Use testnet for API testing
4. Start with dry runs
5. Monitor logs during live trading
6. Set strict risk limits
7. Use small position sizes initially

### ❌ DON'T

1. Test order logic on live exchange
2. Skip unit/integration tests
3. Use large amounts for testing
4. Force signals in production
5. Debug with real money
6. Skip dry runs
7. Test without stop losses

---

## Testing Checklist

Use this checklist for any new feature or change:

```
Development Phase:
[ ] Unit tests written and passing
[ ] Integration tests updated
[ ] Code reviewed

Testing Phase:
[ ] Dry run completed
[ ] Testnet testing done
[ ] Edge cases tested
[ ] Error handling verified

Deployment Phase:
[ ] All tests passing
[ ] Configuration reviewed
[ ] Risk limits set
[ ] Monitoring enabled
[ ] Rollback plan ready

Live Phase:
[ ] Minimum position size
[ ] Close monitoring
[ ] Logs reviewed
[ ] Performance tracked
```

---

## Troubleshooting

### Tests Failing

```bash
# Check Python environment
which python
python --version

# Install test dependencies
pip install pytest pytest-mock

# Run with verbose output
python tests/test_strategy_components.py -v
```

### Testnet Connection Issues

```bash
# Verify testnet credentials
echo $BINANCE_TESTNET_API_KEY

# Test connection
curl https://testnet.binancefuture.com/fapi/v1/ping
```

### Live Trading Issues

```bash
# Check trader status
sudo systemctl status deepseek-trader.service

# View recent errors
grep -i "error\|reject" logs/trader.log | tail -20

# Check order rejections
grep "OrderRejected" logs/trader.log | tail -10
```

---

## Summary

The professional approach to testing trading software:

1. **Unit Tests** - Test functions in isolation (fast, cheap, safe)
2. **Integration Tests** - Test component interactions with mocks
3. **Manual Dry Runs** - Step-by-step verification without real orders
4. **Testnet Testing** - Real API with fake money
5. **Live Testing** - Real money with minimum amounts and close monitoring

**Never skip levels!** Each level builds confidence and reduces risk.

Your manual debugging approach (setting breakpoints, forcing BUY signals) should **only be done with:**
- Dry runs (no real orders)
- Testnet (fake money)
- Very small amounts on live exchange (final verification only)

This methodology is used by professional trading firms and will save you money and headaches!
