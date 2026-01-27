# Changelog

All notable changes to AItrader will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] - 2026-01-27

### Added - Multi-Timeframe Framework (MTF)

**Major Architecture Enhancement**: Three-layer decision framework based on [TradingAgents](https://github.com/TauricResearch/TradingAgents) (UCLA/MIT research).

#### Core Features

- **Multi-Timeframe Analysis**
  - Trend Layer (1D): Risk-On/Risk-Off market regime filter
    - SMA_200 for long-term trend identification
    - MACD for trend strength confirmation
    - Blocks all trades during bearish macro trends
  - Decision Layer (4H): Bull/Bear debate with quantitative Judge framework
    - Bull Analyst: Persuasive bullish arguments (temperature=0.3)
    - Bear Analyst: Skeptical bearish arguments (temperature=0.3)
    - Judge: Confirmation counting algorithm (temperature=0.1)
    - Reduces subjective HOLD bias through algorithmic decision rules
  - Execution Layer (15M): Precise entry timing
    - RSI entry range validation (35-65)
    - Support/resistance-based stop loss placement
    - Exact entry point determination

#### Data Source Enhancements

- **Order Flow Analysis** (from Binance K-line complete fields)
  - Buy/Sell Ratio: Measures buying vs selling pressure
    - Bullish threshold: >55% buy volume
    - Bearish threshold: <45% buy volume
  - CVD (Cumulative Volume Delta): Tracks net money flow direction
    - RISING: Sustained buying pressure
    - FALLING: Sustained selling pressure
    - NEUTRAL: Balanced market
  - Average Trade Size: Identifies institutional vs retail activity
  - 10-bar rolling window: Short-term trend confirmation

- **Derivatives Data Integration** (via Coinalyze API)
  - Open Interest (OI): Position accumulation indicator
    - +5% change = strong trend confirmation
    - -5% change = potential trend exhaustion
  - Funding Rate: Market sentiment and squeeze risk
    - >0.01% = overleveraged longs (bearish signal)
    - <-0.01% = overleveraged shorts (bullish signal)
  - Liquidations (1-hour): Extreme market stress indicator
    - High liquidations = capitulation signal
    - Direction indicates which side is getting squeezed

#### Technical Implementation

- **New Modules**
  - `utils/binance_kline_client.py`: Multi-timeframe K-line data fetcher
  - `utils/order_flow_processor.py`: Buy/sell ratio and CVD calculator
  - `utils/coinalyze_client.py`: Derivatives data client with fallback
  - `utils/ai_data_assembler.py`: Unified data aggregation layer

- **Enhanced Modules**
  - `agents/multi_agent_analyzer.py`:
    - Added `order_flow_report` parameter to `analyze()` method
    - Added `derivatives_report` parameter to `analyze()` method
    - New `_format_order_flow_report()` for AI prompt integration
    - New `_format_derivatives_report()` for derivatives context
  - `strategy/deepseek_strategy.py`:
    - MTF framework integration in `on_timer()`
    - Multi-timeframe bar routing
    - Enhanced AI context with 4 data sources

#### Configuration

- **New Config Sections** (`configs/base.yaml`)
  - `multi_timeframe.*`: Three-layer framework configuration
    - `trend_layer.*`: 1D trend filter settings
    - `decision_layer.*`: 4H debate configuration
    - `execution_layer.*`: 15M entry timing parameters
  - `order_flow.*`: Order flow analysis settings
    - `binance.*`: K-line field selection
    - `buy_ratio.*`: Bullish/bearish thresholds
  - `coinalyze.*`: Derivatives data configuration
    - `endpoints.*`: OI/Funding/Liquidations toggle
    - `fallback_*`: Graceful degradation defaults

- **Environment Variables**
  - `COINALYZE_API_KEY`: Optional API key for derivatives data
    - System works without it (uses order flow + technical only)
    - Get key at: https://coinalyze.net/

#### Robustness Improvements

- **Complete Degradation Strategy**
  - Priority 1: RISK_OFF filter (trend layer blocks bearish markets)
  - Priority 2: Decision state matching (prevents counter-signal trades)
  - Priority 3: RSI confirmation (avoids overbought/oversold entries)
  - API Failures: Graceful fallback to neutral default values
  - Data Staleness: Automatic invalidation and fallback

- **Data Validation**
  - Binance K-line format compatibility (both NautilusTrader and raw formats)
  - Coinalyze API response validation with error handling
  - Freshness checks for all external data sources

#### Performance Optimizations

- Synchronous architecture (no asyncio overhead)
- Cached trend layer state (4-hour TTL, reduces API calls)
- Efficient data aggregation (single pass through AI Data Assembler)
- Smart request batching for Coinalyze endpoints

#### Expected Improvements

- **Signal Quality**: Order flow confirms real trade intent, reduces false breakouts
- **Risk Management**: Derivatives data warns of liquidation cascades and funding squeezes
- **Decision Efficiency**: Judge confirmation counting reduces HOLD bias from 40% to <30%
- **Market Regime Awareness**: Trend filter prevents counter-trend disasters

### Changed

- **AI Temperature Settings Clarification**
  - Bull/Bear Analysts: 0.3 (need debate diversity)
  - Judge/Risk Manager: 0.1 (need deterministic logic)
  - Documented rationale in CLAUDE.md

- **TradingAgents Architecture Evolution**
  - Original: Parallel signal merging (DeepSeek + MultiAgent)
  - v2.1: Hierarchical decision (MultiAgent Judge is final authority)
  - Eliminated signal fusion logic (legacy `skip_on_divergence`, `use_confidence_fusion`)

### Documentation

- **New Documents**
  - `docs/MTF_UNIMPLEMENTED_FEATURES.md`: Complete implementation guide
  - `docs/MTF_EVALUATION_AND_FIXES.md`: Architectural evaluation report
  - `CHANGELOG.md`: Version history (this file)

- **Updated Documents**
  - `CLAUDE.md`: Added MTF configuration section with examples
  - `README.md`: Updated architecture diagrams with MTF components
  - `configs/base.yaml`: Comprehensive MTF parameter documentation

### Technical Debt Addressed

- P0: Interface signature mismatch in `MultiAgentAnalyzer.analyze()` - ✅ Fixed
- P1: Order flow formatting methods missing - ✅ Implemented
- P2: Coinalyze client not implemented - ✅ Completed with fallback

### Deployment Notes

- **Backward Compatible**: MTF can be disabled via `multi_timeframe.enabled: false`
- **Gradual Rollout Recommended**:
  - Week 1: Enable `order_flow.enabled: true` only
  - Week 2: Add `coinalyze.enabled: true` (if API key available)
  - Week 3: Full MTF with `multi_timeframe.enabled: true`
- **Validation Scripts**:
  - `python3 scripts/validate_path_aliases.py`: Config integrity check
  - `python3 scripts/smart_commit_analyzer.py`: Regression detection

### Credits

- MTF Architecture: Based on [TradingAgents Framework](https://github.com/TauricResearch/TradingAgents) by Tauric Research (UCLA/MIT)
- Order Flow Concepts: Adapted from institutional trading practices
- Derivatives Integration: Powered by [Coinalyze API](https://coinalyze.net/)

---

## [1.2.2] - 2025-11-15

### Fixed

- **Bracket Order Emulation**: Corrected order emulation flow for Binance
- **Telegram Sync Error**: Fixed event loop error in `send_message_sync()`
- **OCO Error Handling**: Improved error handling in OCO manager

### Improved

- Bracket order documentation and flow diagrams
- Error messages for common configuration issues

---

## [1.2.0] - 2025-10-20

### Added

- **Partial Take Profit System**
  - Multi-level profit-taking (e.g., 50% at +2%, 50% at +4%)
  - Configurable thresholds and position percentages
  - Risk reduction while maintaining upside potential

- **Trailing Stop Loss**
  - Dynamic stop loss that follows price
  - Activation threshold (default: +1% profit)
  - Trailing distance (default: 0.5%)
  - Update threshold to reduce order spam

- **Telegram Remote Control**
  - `/status`: System status and balance
  - `/position`: Current positions
  - `/orders`: Active orders
  - `/pause` / `/resume`: Trading control
  - `/close`: Emergency position closure

- **OCO (One-Cancels-the-Other) Management**
  - Redis persistence for OCO groups
  - Automatic peer order cancellation
  - Orphan order cleanup
  - Survives strategy restarts

- **Bracket Orders**
  - Native NautilusTrader bracket order support
  - Simultaneous SL/TP with entry order
  - Order emulation for unsupported exchanges

---

## [1.1.0] - 2025-09-10

### Added

- **Automated Stop Loss & Take Profit**
  - Support/resistance-based stop loss calculation
  - Configurable buffer percentage (default: 0.1%)
  - AI confidence-based take profit targets:
    - HIGH: 3% profit target
    - MEDIUM: 2% profit target
    - LOW: 1% profit target
  - STOP_MARKET for stop loss
  - LIMIT orders for take profit

### Improved

- Risk management framework
- Position sizing logic
- Error handling for order placement

---

## [1.0.0] - 2025-08-01

### Added

- **Core Trading System**
  - DeepSeek AI integration for signal generation
  - NautilusTrader framework migration from original implementation
  - Binance Futures support (BTCUSDT-PERP)
  - Event-driven architecture

- **Technical Analysis**
  - Moving Averages: SMA (5, 20, 50), EMA (12, 26)
  - Momentum: RSI (14), MACD (12, 26, 9)
  - Volatility: Bollinger Bands (20, 2σ)
  - Support/Resistance detection
  - Volume analysis

- **Sentiment Integration**
  - Binance Long/Short Ratio API
  - Real-time market sentiment analysis
  - Weighted sentiment in AI decision-making

- **Position Sizing**
  - AI confidence-based multipliers
  - Trend strength adjustments
  - RSI extreme adjustments
  - Maximum position ratio enforcement

- **Configuration Management**
  - Multi-environment support (production/development/backtest)
  - Centralized configuration via ConfigManager
  - Environment variable integration

### Documentation

- Initial README with quick start guide
- Deployment documentation (DEPLOYMENT.md)
- Architecture overview
- Risk disclaimers

---

## Version Numbering

- **Major.Minor.Patch** (Semantic Versioning)
  - **Major**: Breaking changes or major architecture overhauls
  - **Minor**: New features, non-breaking enhancements
  - **Patch**: Bug fixes, documentation updates

## Links

- [GitHub Repository](https://github.com/FelixWayne0318/AItrader)
- [TradingAgents Framework](https://github.com/TauricResearch/TradingAgents)
- [NautilusTrader Documentation](https://nautilustrader.io/)
- [DeepSeek AI](https://www.deepseek.com/)

---

**For detailed technical documentation, see:**
- `docs/MTF_UNIMPLEMENTED_FEATURES.md` - MTF implementation guide
- `docs/MTF_EVALUATION_AND_FIXES.md` - Architecture evaluation
- `CLAUDE.md` - Development guidelines and configuration
- `README.md` - User guide and quick start
