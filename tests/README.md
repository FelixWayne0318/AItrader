# Testing Framework

This directory contains comprehensive tests for the DeepSeek Trading Strategy.

## Quick Start

```bash
# Activate virtual environment
source ~/deepseek_venv/bin/activate

# Run all tests
python tests/test_integration_mock.py

# Run specific test
python tests/test_strategy_components.py

# Manual dry-run (safe testing)
python tests/manual_order_test.py --dry-run --signal BUY
```

## Test Files

### 1. `test_strategy_components.py` - Unit Tests
Tests individual functions in isolation:
- Position sizing with $100 minimum notional
- Confidence-based scaling
- DeepSeek AI response parsing
- Stop loss/take profit calculations

**Run:** `python tests/test_strategy_components.py`

### 2. `test_integration_mock.py` - Integration Tests
Tests full trading flow with mocked APIs:
- Binance data → Technical analysis → AI analysis → Order creation
- Order validation (notional, SL, TP)
- Pre/post hotfix scenarios

**Run:** `python tests/test_integration_mock.py`

### 3. `manual_order_test.py` - Manual Testing Tool
For step-by-step debugging and verification:

```bash
# Dry run (recommended first)
python tests/manual_order_test.py --dry-run --signal BUY

# Test with testnet (requires setup)
python tests/manual_order_test.py --testnet --signal BUY

# Live test (DANGEROUS - use with extreme caution)
python tests/manual_order_test.py --live-danger --signal BUY
```

**Options:**
- `--dry-run`: Simulate without placing orders (safe)
- `--testnet`: Use Binance Testnet (requires testnet API keys)
- `--live-danger`: Use live exchange (real money!)
- `--signal BUY|SELL|HOLD`: Force specific signal for testing
- `--confidence LOW|MEDIUM|HIGH`: Set confidence level

### 4. `test_bracket_order.py` - Existing Tests
Tests bracket order creation logic.

## Testing Methodology

### Testing Pyramid (Professional Approach)

```
Level 4: Live Testing        [1%  of tests] - Real money, minimal amounts
Level 3: Testnet Testing     [9%  of tests] - Real API, fake money
Level 2: Integration Tests   [20% of tests] - Mocked APIs
Level 1: Unit Tests          [70% of tests] - Isolated functions
```

### Your Original Question

> "I want to test step-by-step, set breakpoint after DeepSeek AI analysis,
> and force a BUY signal to verify order placement. Is this professional?"

**Answer:**

Your approach has merit for debugging, but it's **risky on live exchange**. Here's the professional way:

**✅ GOOD Approach:**
1. Write unit tests → Test individual functions
2. Write integration tests → Test component interactions
3. Use dry-run mode → Step through logic without real orders
4. Use Binance Testnet → Test with real API, fake money
5. Use minimal amounts on live exchange → Final verification only

**❌ RISKY Approach:**
- Setting breakpoints in live trading code
- Forcing signals on production system
- Testing directly on live exchange
- No automated test suite

## Testing Workflow

### For New Features

```bash
# 1. Write unit tests
vim tests/test_my_feature.py

# 2. Run unit tests
python tests/test_strategy_components.py

# 3. Write integration tests
vim tests/test_integration_mock.py

# 4. Dry run test
python tests/manual_order_test.py --dry-run

# 5. Testnet test (if available)
python tests/manual_order_test.py --testnet

# 6. Live test (minimal amount)
# Monitor logs closely!
```

### For Debugging

```bash
# Test specific function
python tests/test_strategy_components.py

# Test full flow with mocked data
python tests/test_integration_mock.py

# Dry run with forced signal
python tests/manual_order_test.py --dry-run --signal BUY --confidence HIGH

# Check logs
tail -f /home/ubuntu/nautilus_deepseek/logs/trader.log
```

## Binance Testnet Setup

### 1. Create Testnet Account
- Visit: https://testnet.binancefuture.com/
- Register (separate from live account)
- Get free test USDT

### 2. Generate API Keys
- API Management → Create API Key
- Save Key and Secret

### 3. Configure Environment
Create `.env.testnet`:

```bash
BINANCE_TESTNET_API_KEY=your_testnet_key
BINANCE_TESTNET_API_SECRET=your_testnet_secret
BINANCE_TESTNET_BASE_URL=https://testnet.binancefuture.com
```

### 4. Install Dependencies
```bash
pip install ccxt  # For testnet connection
```

### 5. Run Testnet Test
```bash
export $(cat .env.testnet | xargs)
python tests/manual_order_test.py --testnet --signal BUY
```

## Safety Guidelines

### ⚠️ Never Do This
- ❌ Test on live exchange during development
- ❌ Force signals in production code
- ❌ Use large amounts for testing
- ❌ Skip automated tests
- ❌ Debug with real money

### ✅ Always Do This
- ✅ Write unit tests for new features
- ✅ Use dry-run mode first
- ✅ Test on Binance Testnet
- ✅ Use minimum notional on live ($100)
- ✅ Monitor logs during testing
- ✅ Set strict risk limits

## Test Results

### Integration Tests (Passed ✅)

```
Results: 2 passed, 0 failed

Test 1: Full Trading Flow
- ✓ Mock Binance data generation
- ✓ Technical indicator calculation
- ✓ DeepSeek AI response parsing
- ✓ Position sizing (enforces $100 minimum)
- ✓ Bracket order creation
- ✓ Order validation

Test 2: Order Rejection Scenario
- ✓ Old config ($30) → Would be rejected
- ✓ New config ($100) → Would be accepted
- ✓ Hotfix validation
```

## Documentation

See `/home/ubuntu/nautilus_deepseek/docs/TESTING_GUIDE.md` for comprehensive testing guide.

## Questions?

Your approach to testing (step-by-step with breakpoints and forced signals) is good for **debugging**, but should be done with:

1. **Dry runs** (no real orders) - Use `--dry-run` flag
2. **Testnet** (real API, fake money) - Use `--testnet` flag
3. **Minimal amounts** (real money) - Only for final verification

The test framework provides all these options safely!
