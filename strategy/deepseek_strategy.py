"""
Multi-Agent Hierarchical Trading Strategy for NautilusTrader

AI-powered cryptocurrency trading strategy using TradingAgents-inspired architecture:
- Bull/Bear Analyst Debate: Two opposing AI agents argue market direction
- Judge (Portfolio Manager): Evaluates debate and makes final decision
- Risk Manager: Determines position sizing and stop/take profit levels

This implements a hierarchical decision architecture where the Judge's decision is final,
avoiding signal conflicts that can occur with parallel multi-agent systems.

Reference: TradingAgents (UCLA/MIT) - https://github.com/TauricResearch/TradingAgents
"""

import os
import asyncio
import threading
from decimal import Decimal
from typing import Dict, Any, Optional, List, Tuple

from nautilus_trader.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce, PositionSide, PriceType, TriggerType, OrderType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.position import Position
from nautilus_trader.model.orders import MarketOrder
from datetime import datetime, timedelta

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicators.technical_manager import TechnicalIndicatorManager
from utils.deepseek_client import DeepSeekAnalyzer
from utils.sentiment_client import SentimentDataFetcher
from utils.binance_account import BinanceAccountFetcher
from agents.multi_agent_analyzer import MultiAgentAnalyzer
# Order Flow and Derivatives clients (MTF v2.1)
from utils.binance_kline_client import BinanceKlineClient
from utils.order_flow_processor import OrderFlowProcessor
from utils.coinalyze_client import CoinalyzeClient
from strategy.trading_logic import (
    check_confidence_threshold,
    calculate_position_size,
    validate_multiagent_sltp,
    calculate_technical_sltp,
    # process_signals removed - Hierarchical architecture uses MultiAgent Judge as final decision maker
)
# OCOManager no longer needed - using NautilusTrader's built-in bracket orders


class DeepSeekAIStrategyConfig(StrategyConfig, frozen=True):
    """Configuration for DeepSeek AI Strategy."""

    # Instrument
    instrument_id: str
    bar_type: str

    # Capital
    equity: float = 1000.0  # 备用值，当无法获取真实余额时使用
    leverage: float = 5.0   # 杠杆倍数 (建议 3-10)
    use_real_balance_as_equity: bool = True  # 自动从 Binance 获取真实余额作为 equity

    # Position sizing
    base_usdt_amount: float = 100.0
    high_confidence_multiplier: float = 1.5
    medium_confidence_multiplier: float = 1.0
    low_confidence_multiplier: float = 0.5
    max_position_ratio: float = 0.30  # 最大仓位比例 (30% of equity)
    trend_strength_multiplier: float = 1.2
    min_trade_amount: float = 0.001

    # Technical indicators
    sma_periods: Tuple[int, ...] = (5, 20, 50)
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    bb_period: int = 20
    bb_std: float = 2.0
    volume_ma_period: int = 20  # Volume MA period for analysis
    support_resistance_lookback: int = 20  # Support/resistance lookback period

    # AI configuration
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_temperature: float = 0.3  # Increased for debate diversity
    deepseek_max_retries: int = 2
    deepseek_retry_delay: float = 1.0  # Retry delay in seconds
    deepseek_signal_history_count: int = 30  # Signal history size
    debate_rounds: int = 2  # Bull/Bear debate rounds (1-3)
    multi_agent_retry_delay: float = 1.0  # Multi-agent retry delay
    multi_agent_json_parse_max_retries: int = 2  # JSON parse max retries

    # Sentiment
    sentiment_enabled: bool = True
    sentiment_lookback_hours: int = 4
    sentiment_timeframe: str = "15m"  # Sentiment data timeframe (should match or be compatible with bar_type)

    # Risk management
    min_confidence_to_trade: str = "MEDIUM"
    allow_reversals: bool = True
    require_high_confidence_for_reversal: bool = False
    rsi_extreme_threshold_upper: float = 70.0  # 与 strategy_config.yaml 一致
    rsi_extreme_threshold_lower: float = 30.0  # 与 strategy_config.yaml 一致
    rsi_extreme_multiplier: float = 0.7

    # [LEGACY - 不再使用] Multi-Agent Divergence Handling
    # 层级决策架构中，Judge决策即最终决策，不存在信号合并/冲突
    # 以下选项保留用于向后兼容，但不再生效
    skip_on_divergence: bool = True  # [LEGACY] 不再使用
    use_confidence_fusion: bool = True  # [LEGACY] 不再使用
    
    # Stop Loss & Take Profit
    enable_auto_sl_tp: bool = True
    sl_use_support_resistance: bool = True
    sl_buffer_pct: float = 0.001
    tp_high_confidence_pct: float = 0.03
    tp_medium_confidence_pct: float = 0.02
    tp_low_confidence_pct: float = 0.01
    
    # OCO (One-Cancels-the-Other) - now handled by NautilusTrader bracket orders
    enable_oco: bool = True  # Controls orphan order cleanup (bracket orders handle OCO automatically)

    # Trailing Stop Loss
    enable_trailing_stop: bool = True
    trailing_activation_pct: float = 0.01
    trailing_distance_pct: float = 0.005
    trailing_update_threshold_pct: float = 0.002

    # Partial Take Profit - NOT IMPLEMENTED
    # WARNING: This feature is NOT YET IMPLEMENTED. Setting to True has no effect.
    # The config is preserved for future implementation.
    enable_partial_tp: bool = False  # Not implemented - keep False
    partial_tp_levels: Tuple[Dict[str, float], ...] = (
        {"profit_pct": 0.02, "position_pct": 0.5},
        {"profit_pct": 0.04, "position_pct": 0.5},
    )
    
    # Telegram Notifications
    enable_telegram: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_notify_signals: bool = True
    telegram_notify_fills: bool = True
    telegram_notify_positions: bool = True
    telegram_notify_errors: bool = True
    telegram_notify_heartbeat: bool = True  # v2.1: 每次 on_timer 发送心跳状态

    # Execution
    position_adjustment_threshold: float = 0.001

    # Timing
    timer_interval_sec: int = 900

    # Network configuration
    network_telegram_startup_delay: float = 5.0
    network_telegram_polling_max_retries: int = 3
    network_telegram_polling_base_delay: float = 10.0
    network_binance_recv_window: int = 5000
    network_binance_balance_cache_ttl: float = 5.0
    network_bar_persistence_max_limit: int = 1500
    network_bar_persistence_timeout: float = 10.0
    network_oco_manager_socket_timeout: float = 5.0
    network_oco_manager_socket_connect_timeout: float = 5.0
    network_instrument_discovery_max_retries: int = 60  # Instrument 加载最大重试次数
    network_instrument_discovery_retry_interval: float = 1.0  # Instrument 加载重试间隔 (秒)
    network_binance_api_timeout: float = 10.0  # Binance API 超时 (秒)
    network_telegram_message_timeout: float = 30.0  # Telegram 消息发送超时 (秒)
    sentiment_timeout: float = 10.0

    # Multi-Timeframe Configuration (v3.2.9)
    multi_timeframe_enabled: bool = False  # Default disabled for backward compatibility
    mtf_trend_sma_period: int = 200        # SMA period for trend layer (1D)
    mtf_trend_require_above_sma: bool = True
    mtf_trend_require_macd_positive: bool = True
    mtf_decision_debate_rounds: int = 2    # Debate rounds for decision layer (4H)
    mtf_execution_rsi_entry_min: int = 35  # RSI entry range for execution layer (15M)
    mtf_execution_rsi_entry_max: int = 65


class DeepSeekAIStrategy(Strategy):
    """
    DeepSeek AI-powered trading strategy.

    Combines AI decision making, technical analysis, and sentiment data
    for intelligent cryptocurrency trading on Binance Futures.
    """

    def __init__(self, config: DeepSeekAIStrategyConfig):
        """
        Initialize DeepSeek AI strategy.

        Parameters
        ----------
        config : DeepSeekAIStrategyConfig
            Strategy configuration
        """
        super().__init__(config)

        # Configuration
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.bar_type = BarType.from_str(config.bar_type)

        # Position sizing config
        self.equity = config.equity
        self.leverage = config.leverage
        self.base_usdt = config.base_usdt_amount
        self.position_config = {
            'high_confidence_multiplier': config.high_confidence_multiplier,
            'medium_confidence_multiplier': config.medium_confidence_multiplier,
            'low_confidence_multiplier': config.low_confidence_multiplier,
            'max_position_ratio': config.max_position_ratio,
            'trend_strength_multiplier': config.trend_strength_multiplier,
            'min_trade_amount': config.min_trade_amount,
            'adjustment_threshold': config.position_adjustment_threshold,
        }

        # Risk management
        self.min_confidence = config.min_confidence_to_trade
        self.allow_reversals = config.allow_reversals
        self.require_high_conf_reversal = config.require_high_confidence_for_reversal
        self.rsi_extreme_upper = config.rsi_extreme_threshold_upper
        self.rsi_extreme_lower = config.rsi_extreme_threshold_lower
        self.rsi_extreme_mult = config.rsi_extreme_multiplier

        # Multi-Agent Divergence Handling
        self.skip_on_divergence = config.skip_on_divergence
        self.use_confidence_fusion = config.use_confidence_fusion

        # Stop Loss & Take Profit
        self.enable_auto_sl_tp = config.enable_auto_sl_tp
        self.sl_use_support_resistance = config.sl_use_support_resistance
        self.sl_buffer_pct = config.sl_buffer_pct
        self.tp_pct_config = {
            'HIGH': config.tp_high_confidence_pct,
            'MEDIUM': config.tp_medium_confidence_pct,
            'LOW': config.tp_low_confidence_pct,
        }
        
        # Store latest signal, technical, and price data for SL/TP calculation
        self.latest_signal_data: Optional[Dict[str, Any]] = None
        self.latest_technical_data: Optional[Dict[str, Any]] = None
        self.latest_price_data: Optional[Dict[str, Any]] = None

        # OCO (One-Cancels-the-Other) - Now handled by NautilusTrader's bracket orders
        # No need for manual OCO manager anymore
        self.enable_oco = config.enable_oco  # Keep for config compatibility
        self.oco_manager = None  # Deprecated: bracket orders handle OCO automatically
        
        # Trailing Stop Loss
        self.enable_trailing_stop = config.enable_trailing_stop
        self.trailing_activation_pct = config.trailing_activation_pct
        self.trailing_distance_pct = config.trailing_distance_pct
        self.trailing_update_threshold_pct = config.trailing_update_threshold_pct
        
        # Thread lock for shared state (Telegram thread safety)
        self._state_lock = threading.Lock()

        # Thread lock for on_timer (prevent re-entry if AI calls take > timer_interval)
        self._timer_lock = threading.Lock()

        # Thread-safe cached price (updated in on_bar, read by Telegram commands)
        # IMPORTANT: Do NOT access indicator_manager from Telegram thread - it contains
        # Rust indicators (RSI, MACD) that are not Send/Sync and will cause panic
        self._cached_current_price: float = 0.0

        # Real-time Binance account fetcher for accurate balance info
        self.binance_account = BinanceAccountFetcher(
            logger=self.log,
            cache_ttl=config.network_binance_balance_cache_ttl,
            recv_window=config.network_binance_recv_window,
            api_timeout=config.network_binance_api_timeout,
        )
        self._real_balance: Dict[str, float] = {}  # Cached real balance from Binance

        # Track trailing stop state for each position
        self.trailing_stop_state: Dict[str, Dict[str, Any]] = {}
        # Format: {
        #   "instrument_id": {
        #       "entry_price": float,
        #       "highest_price": float (for LONG) or "lowest_price": float (for SHORT),
        #       "current_sl_price": float,
        #       "sl_order_id": str,
        #       "activated": bool,
        #       "side": str (LONG/SHORT)
        #   }
        # }

        # Technical indicators manager
        sma_periods = config.sma_periods if config.sma_periods else [5, 20, 50]
        self.indicator_manager = TechnicalIndicatorManager(
            sma_periods=sma_periods,
            ema_periods=[config.macd_fast, config.macd_slow],
            rsi_period=config.rsi_period,
            macd_fast=config.macd_fast,
            macd_slow=config.macd_slow,
            bb_period=config.bb_period,
            bb_std=config.bb_std,
            volume_ma_period=config.volume_ma_period,
            support_resistance_lookback=config.support_resistance_lookback,
        )

        # Multi-Timeframe Manager (v3.2.8)
        self.mtf_enabled = getattr(config, 'multi_timeframe_enabled', False)
        self.mtf_manager = None
        self.trend_bar_type = None
        self.decision_bar_type = None
        self.execution_bar_type = None

        # Async request tracking for request_bars (v3.2.8)
        self._pending_requests: Dict[str, Any] = {}  # layer -> request_id
        self._mtf_trend_initialized = False
        self._mtf_decision_initialized = False
        self._mtf_execution_initialized = False

        if self.mtf_enabled:
            try:
                from indicators.multi_timeframe_manager import MultiTimeframeManager, RiskState, DecisionState

                # Build BarType objects for each layer
                instrument_str = str(self.instrument_id)
                self.trend_bar_type = BarType.from_str(f"{instrument_str}-1-DAY-LAST-EXTERNAL")
                self.decision_bar_type = BarType.from_str(f"{instrument_str}-4-HOUR-LAST-EXTERNAL")
                self.execution_bar_type = BarType.from_str(f"{instrument_str}-15-MINUTE-LAST-EXTERNAL")

                # Build MTF config from strategy config
                mtf_config = {
                    'enabled': True,
                    'trend_layer': {
                        'timeframe': '1d',
                        'sma_period': getattr(config, 'mtf_trend_sma_period', 200),
                        'require_above_sma': getattr(config, 'mtf_trend_require_above_sma', True),
                        'require_macd_positive': getattr(config, 'mtf_trend_require_macd_positive', True),
                    },
                    'decision_layer': {
                        'timeframe': '4h',
                        'debate_rounds': getattr(config, 'mtf_decision_debate_rounds', 2),
                    },
                    'execution_layer': {
                        'timeframe': '15m',
                        'rsi_entry_min': getattr(config, 'mtf_execution_rsi_entry_min', 35),
                        'rsi_entry_max': getattr(config, 'mtf_execution_rsi_entry_max', 65),
                    }
                }

                self.mtf_manager = MultiTimeframeManager(
                    config=mtf_config,
                    trend_bar_type=self.trend_bar_type,
                    decision_bar_type=self.decision_bar_type,
                    execution_bar_type=self.execution_bar_type,
                    logger=self.log,
                )
                # Store enums for use in on_timer (avoid import in hot path)
                self._RiskState = RiskState
                self._DecisionState = DecisionState
                self.log.info(f"✅ MTF Manager initialized: trend={self.trend_bar_type}, decision={self.decision_bar_type}, exec={self.execution_bar_type}")
            except Exception as e:
                self.log.error(f"❌ Failed to initialize MTF Manager: {e}")
                self.mtf_enabled = False

        # DeepSeek AI analyzer
        api_key = config.deepseek_api_key or os.getenv('DEEPSEEK_API_KEY')
        if not api_key:
            raise ValueError("DeepSeek API key not provided")

        self.deepseek = DeepSeekAnalyzer(
            api_key=api_key,
            model=config.deepseek_model,
            temperature=config.deepseek_temperature,
            max_retries=config.deepseek_max_retries,
            signal_history_count=config.deepseek_signal_history_count,
            retry_delay=config.deepseek_retry_delay,
        )

        # Multi-Agent AI analyzer (Bull/Bear Debate) - for parallel comparison
        self.multi_agent = MultiAgentAnalyzer(
            api_key=api_key,
            model=config.deepseek_model,
            temperature=config.deepseek_temperature,
            debate_rounds=config.debate_rounds,
            retry_delay=config.multi_agent_retry_delay,
            json_parse_max_retries=config.multi_agent_json_parse_max_retries,
        )
        self.log.info(f"✅ Multi-Agent analyzer initialized (debate_rounds={config.debate_rounds})")

        # Telegram Bot
        self.telegram_bot = None
        self.enable_telegram = config.enable_telegram
        if self.enable_telegram:
            try:
                from utils.telegram_bot import TelegramBot
                
                bot_token = config.telegram_bot_token or os.getenv('TELEGRAM_BOT_TOKEN', '')
                chat_id = config.telegram_chat_id or os.getenv('TELEGRAM_CHAT_ID', '')
                
                if bot_token and chat_id:
                    self.telegram_bot = TelegramBot(
                        token=bot_token,
                        chat_id=chat_id,
                        logger=self.log,
                        enabled=True,
                        message_timeout=config.network_telegram_message_timeout
                    )
                    # Store notification preferences
                    self.telegram_notify_signals = config.telegram_notify_signals
                    self.telegram_notify_fills = config.telegram_notify_fills
                    self.telegram_notify_positions = config.telegram_notify_positions
                    self.telegram_notify_errors = config.telegram_notify_errors
                    self.telegram_notify_heartbeat = config.telegram_notify_heartbeat  # v2.1

                    self.log.info("✅ Telegram Bot initialized successfully")
                    
                    # Initialize command handler for remote control
                    # Note: The command handler runs in a separate thread with its own event loop
                    # and handles Telegram Conflict errors gracefully with retries
                    try:
                        from utils.telegram_command_handler import TelegramCommandHandler
                        # Note: threading is already imported at module level (line 10)

                        # Create callback function for commands
                        def command_callback(command: str, args: Dict[str, Any]) -> Dict[str, Any]:
                            """Callback function for Telegram commands."""
                            return self.handle_telegram_command(command, args)

                        # Initialize command handler
                        allowed_chat_ids = [chat_id]  # Only allow the configured chat ID
                        self.telegram_command_handler = TelegramCommandHandler(
                            token=bot_token,
                            allowed_chat_ids=allowed_chat_ids,
                            strategy_callback=command_callback,
                            logger=self.log,
                            startup_delay=config.network_telegram_startup_delay,
                            polling_max_retries=config.network_telegram_polling_max_retries,
                            polling_base_delay=config.network_telegram_polling_base_delay,
                        )

                        # Start command handler in background thread with isolated event loop
                        def run_command_handler():
                            """Run command handler in background thread with proper event loop isolation."""
                            loop = None
                            try:
                                # Create isolated event loop for this thread
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                # Start polling (this will run indefinitely)
                                # Note: start_polling() handles Telegram Conflict errors with retries
                                loop.run_until_complete(self.telegram_command_handler.start_polling())
                            except asyncio.CancelledError:
                                self.log.info("🔌 Telegram command handler cancelled")
                            except Exception as e:
                                # Log as warning, not error - command handler is non-critical
                                self.log.warning(f"⚠️ Telegram command handler stopped: {e}")
                            finally:
                                # Cleanup event loop
                                if loop is not None:
                                    try:
                                        loop.close()
                                    except Exception as e:
                                        self.log.warning(f"⚠️ Failed to close event loop: {e}")

                        # Start background thread for command listening
                        command_thread = threading.Thread(
                            target=run_command_handler,
                            daemon=True,
                            name="TelegramCommandHandler"
                        )
                        command_thread.start()
                        self.log.info("✅ Telegram Command Handler starting in background thread (conflicts will be retried)")

                    except ImportError:
                        self.log.warning("⚠️ Telegram command handler not available")
                        self.telegram_command_handler = None
                    except Exception as e:
                        self.log.warning(f"⚠️ Could not initialize command handler (non-critical): {e}")
                        self.telegram_command_handler = None
                    
                else:
                    self.log.warning("⚠️ Telegram enabled but token/chat_id not configured")
                    self.enable_telegram = False
            except ImportError:
                self.log.warning("⚠️ Telegram bot not available (python-telegram-bot not installed)")
                self.enable_telegram = False
            except Exception as e:
                self.log.error(f"❌ Failed to initialize Telegram Bot: {e}")
                self.enable_telegram = False
        
        # Strategy control state for remote commands
        self.is_trading_paused = False
        self.strategy_start_time = None

        # Sentiment data fetcher
        self.sentiment_enabled = config.sentiment_enabled
        if self.sentiment_enabled:
            # Use sentiment_timeframe from config, or derive from bar_type if not specified
            sentiment_tf = config.sentiment_timeframe
            if not sentiment_tf or sentiment_tf == "":
                # Extract timeframe from bar_type (e.g., "15-MINUTE" -> "15m")
                # NOTE: Must check longer strings first (15-MINUTE before 5-MINUTE)
                bar_str = str(self.bar_type)
                if "15-MINUTE" in bar_str:
                    sentiment_tf = "15m"
                elif "5-MINUTE" in bar_str:
                    sentiment_tf = "5m"
                elif "1-MINUTE" in bar_str:
                    sentiment_tf = "1m"
                elif "4-HOUR" in bar_str:
                    sentiment_tf = "4h"
                elif "1-HOUR" in bar_str:
                    sentiment_tf = "1h"
                else:
                    sentiment_tf = "15m"  # Default fallback
            
            self.sentiment_fetcher = SentimentDataFetcher(
                lookback_hours=config.sentiment_lookback_hours,
                timeframe=sentiment_tf,
                timeout=config.sentiment_timeout,
            )
            self.log.info(f"Sentiment fetcher initialized with timeframe: {sentiment_tf}")
        else:
            self.sentiment_fetcher = None

        # ========== Order Flow & Derivatives (MTF v2.1) ==========
        # 从配置读取参数
        order_flow_enabled = config.order_flow_enabled if hasattr(config, 'order_flow_enabled') else True

        if order_flow_enabled:
            # Binance K线客户端 (获取完整 12 列数据)
            self.binance_kline_client = BinanceKlineClient(
                timeout=config.order_flow_binance_timeout if hasattr(config, 'order_flow_binance_timeout') else 10,
                logger=self.log,
            )

            # 订单流处理器
            self.order_flow_processor = OrderFlowProcessor(logger=self.log)

            # Coinalyze 客户端 (衍生品数据)
            coinalyze_enabled = config.order_flow_coinalyze_enabled if hasattr(config, 'order_flow_coinalyze_enabled') else True
            if coinalyze_enabled:
                self.coinalyze_client = CoinalyzeClient(
                    api_key=None,  # 从环境变量读取
                    timeout=config.order_flow_coinalyze_timeout if hasattr(config, 'order_flow_coinalyze_timeout') else 10,
                    max_retries=config.order_flow_coinalyze_max_retries if hasattr(config, 'order_flow_coinalyze_max_retries') else 2,
                    retry_delay=config.order_flow_coinalyze_retry_delay if hasattr(config, 'order_flow_coinalyze_retry_delay') else 1.0,
                    logger=self.log,
                )
            else:
                self.coinalyze_client = None
                self.log.info("Coinalyze client disabled by config")

            self.log.info("✅ Order Flow & Derivatives clients initialized")
        else:
            self.binance_kline_client = None
            self.order_flow_processor = None
            self.coinalyze_client = None
            self.log.info("Order Flow disabled by config")

        # State tracking
        self.instrument: Optional[Instrument] = None
        self.last_signal: Optional[Dict[str, Any]] = None
        self.bars_received = 0

        self.log.info(f"DeepSeek AI Strategy initialized for {self.instrument_id}")

    def on_start(self):
        """Actions to be performed on strategy start."""
        self.log.info("Starting DeepSeek AI Strategy...")

        # v2.2: 记录启动时间 (用于心跳消息显示运行时长)
        from datetime import datetime
        self._start_time = datetime.now()

        # Load instrument with retry mechanism
        # The instrument may not be immediately available as the data client
        # loads instruments asynchronously from Binance
        import time
        # 从配置读取重试参数 (原硬编码 60/1.0)
        max_retries = self.config.network_instrument_discovery_max_retries
        retry_interval = self.config.network_instrument_discovery_retry_interval

        self.instrument = None
        for attempt in range(max_retries):
            self.instrument = self.cache.instrument(self.instrument_id)
            if self.instrument is not None:
                break

            if attempt == 0:
                self.log.info(f"Waiting for instrument {self.instrument_id} to be loaded...")
                # Log cache state for debugging
                all_instruments = self.cache.instruments()
                if all_instruments:
                    self.log.info(f"Currently loaded instruments: {[str(i.id) for i in all_instruments]}")
                else:
                    self.log.info("No instruments loaded yet in cache")
            elif attempt % 10 == 0:
                self.log.info(f"Still waiting for instrument... (attempt {attempt + 1}/{max_retries})")
                # Log cache state periodically for debugging
                all_instruments = self.cache.instruments()
                if all_instruments:
                    self.log.info(f"Currently loaded instruments: {[str(i.id) for i in all_instruments]}")

            time.sleep(retry_interval)

        if self.instrument is None:
            # Final diagnostic: list all instruments in cache
            all_instruments = self.cache.instruments()
            if all_instruments:
                available_ids = [str(i.id) for i in all_instruments]
                self.log.error(
                    f"Could not find instrument {self.instrument_id} after {max_retries} seconds. "
                    f"Available instruments: {available_ids}"
                )
            else:
                self.log.error(
                    f"Could not find instrument {self.instrument_id} after {max_retries} seconds. "
                    f"No instruments loaded in cache! Check that: "
                    f"1) Binance API keys are valid, "
                    f"2) Network connectivity to api.binance.com is working, "
                    f"3) InstrumentProviderConfig.load_ids contains the correct instrument ID."
                )
            self.stop()
            return

        self.log.info(f"Loaded instrument: {self.instrument.id}")

        # Pre-fetch historical bars before subscribing to live data
        self._prefetch_historical_bars(limit=200)

        # Subscribe to bars (live data)
        self.subscribe_bars(self.bar_type)
        self.log.info(f"Subscribed to {self.bar_type}")

        # Multi-Timeframe subscriptions (v3.2.9)
        if self.mtf_enabled and self.mtf_manager:
            try:
                # Subscribe to all three timeframes
                self.subscribe_bars(self.trend_bar_type)
                self.subscribe_bars(self.decision_bar_type)
                self.subscribe_bars(self.execution_bar_type)
                self.log.info(f"MTF: Subscribed to 1D, 4H, 15M bars")

                # Prefetch historical data for each layer (async)
                self._prefetch_multi_timeframe_bars()
            except Exception as e:
                self.log.error(f"MTF: Failed to subscribe/prefetch: {e}")
                # Continue without MTF - graceful degradation

        # Set up timer for periodic analysis (clock-aligned to 00/15/30/45 minutes)
        interval_minutes = self.config.timer_interval_sec // 60  # 默认 15 分钟
        next_aligned_time = self._calculate_next_aligned_time(interval_minutes)
        self.log.info(f"Timer aligned to clock: next trigger at {next_aligned_time.strftime('%H:%M:%S')} UTC")

        self.clock.set_timer(
            name="analysis_timer",
            interval=timedelta(seconds=self.config.timer_interval_sec),
            start_time=next_aligned_time,
            callback=self.on_timer,
        )

        self.log.info("Strategy started successfully")

        # Fetch real account balance from Binance
        self._update_real_balance()

        # Record start time for uptime tracking
        from datetime import datetime
        self.strategy_start_time = datetime.utcnow()

        # v2.1: Timer counter for heartbeat tracking
        self._timer_count = 0

        # Send Telegram startup notification
        if self.telegram_bot and self.enable_telegram:
            try:
                startup_msg = self.telegram_bot.format_startup_message(
                    instrument_id=str(self.instrument_id),
                    config={
                        'enable_auto_sl_tp': self.enable_auto_sl_tp,
                        'enable_oco': self.enable_oco,
                        'enable_trailing_stop': self.enable_trailing_stop,
                        'enable_partial_tp': hasattr(self, 'enable_partial_tp') and getattr(self, 'enable_partial_tp', False),
                    }
                )
                self.telegram_bot.send_message_sync(startup_msg)

                # Send command help message
                help_msg = self.telegram_bot.format_help_response()
                self.telegram_bot.send_message_sync(help_msg)

            except Exception as e:
                self.log.warning(f"Failed to send Telegram startup notification: {e}")

    def on_stop(self):
        """Actions to be performed on strategy stop."""
        self.log.info("Stopping DeepSeek AI Strategy...")

        # Cancel any pending orders
        self.cancel_all_orders(self.instrument_id)

        # Unsubscribe from data
        self.unsubscribe_bars(self.bar_type)

        self.log.info("Strategy stopped")

    def _calculate_next_aligned_time(self, interval_minutes: int = 15) -> datetime:
        """
        Calculate the next clock-aligned time point.

        For 15-minute interval, returns next 00/15/30/45 minute mark.
        For 5-minute interval, returns next 00/05/10/.../55 minute mark.

        Args:
            interval_minutes: Timer interval in minutes (default 15)

        Returns:
            datetime: Next aligned UTC time
        """
        now = datetime.utcnow()

        # Calculate next aligned minute
        current_minute = now.minute
        minutes_since_aligned = current_minute % interval_minutes
        minutes_to_next = interval_minutes - minutes_since_aligned

        if minutes_to_next == interval_minutes:
            # We're exactly at an aligned time, go to next interval
            minutes_to_next = interval_minutes

        # Calculate next aligned time (reset seconds and microseconds)
        next_time = now.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_next)

        return next_time

    def _update_real_balance(self) -> Dict[str, float]:
        """
        Fetch real account balance from Binance and update internal state.

        This method is called:
        - On strategy startup
        - Periodically by Telegram /risk command
        - Before position size calculation (optional)

        When use_real_balance_as_equity is True (default), this will automatically
        update self.equity to match the real Binance account balance.

        Returns
        -------
        dict
            Balance info with total_balance, available_balance, etc.
        """
        try:
            balance = self.binance_account.get_balance()

            if 'error' not in balance:
                self._real_balance = balance

                real_total = balance.get('total_balance', 0)
                if real_total > 0:
                    # Auto-update equity if enabled
                    if self.config.use_real_balance_as_equity:
                        old_equity = self.equity
                        self.equity = real_total
                        # Also update position_config for position sizing
                        # max_position_ratio is based on equity
                        if abs(old_equity - real_total) > 1:
                            self.log.info(
                                f"💰 Equity auto-updated: ${old_equity:.2f} → ${real_total:.2f} "
                                f"(from Binance real balance)"
                            )
                    else:
                        # Just log if there's a significant difference
                        if abs(real_total - self.equity) > 10:
                            self.log.info(
                                f"💰 Real balance from Binance: ${real_total:.2f} "
                                f"(configured equity: ${self.equity:.2f})"
                            )

                return balance
            else:
                self.log.warning(f"Failed to fetch real balance: {balance.get('error')}")
                return {}

        except Exception as e:
            self.log.error(f"Error fetching real balance: {e}")
            return {}

    def _prefetch_historical_bars(self, limit: int = 200):
        """
        Pre-fetch historical bars from Binance API on startup.

        This eliminates the waiting period for indicators to initialize by loading
        historical data directly from Binance exchange on strategy startup.

        Parameters
        ----------
        limit : int
            Number of historical bars to fetch (default: 200)
        """
        try:
            import requests
            from nautilus_trader.core.datetime import millis_to_nanos

            # Extract symbol from instrument_id
            # Example: BTCUSDT-PERP.BINANCE -> BTCUSDT
            symbol_str = str(self.instrument_id)
            symbol = symbol_str.split('-')[0]

            # Convert bar type to Binance interval
            # NOTE: Must check longer strings first (15-MINUTE before 5-MINUTE)
            bar_type_str = str(self.bar_type)
            if '15-MINUTE' in bar_type_str:
                interval = '15m'
            elif '5-MINUTE' in bar_type_str:
                interval = '5m'
            elif '1-MINUTE' in bar_type_str:
                interval = '1m'
            elif '4-HOUR' in bar_type_str:
                interval = '4h'
            elif '1-HOUR' in bar_type_str:
                interval = '1h'
            elif '1-DAY' in bar_type_str:
                interval = '1d'
            else:
                interval = '15m'  # Default fallback

            self.log.info(
                f"📡 Pre-fetching {limit} historical bars from Binance "
                f"(symbol={symbol}, interval={interval})..."
            )

            # Binance Futures API endpoint
            url = "https://fapi.binance.com/fapi/v1/klines"
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': min(limit, 1500),  # Binance max
            }

            response = requests.get(url, params=params, timeout=self.config.network_bar_persistence_timeout)
            response.raise_for_status()
            klines = response.json()

            if not klines:
                self.log.warning("⚠️ No bars received from Binance API")
                return

            self.log.info(f"📊 Received {len(klines)} bars from Binance")

            # Convert to NautilusTrader bars and feed to indicators
            bars_fed = 0
            for kline in klines:
                try:
                    # Create Bar object
                    bar = Bar(
                        bar_type=self.bar_type,
                        open=self.instrument.make_price(float(kline[1])),
                        high=self.instrument.make_price(float(kline[2])),
                        low=self.instrument.make_price(float(kline[3])),
                        close=self.instrument.make_price(float(kline[4])),
                        volume=self.instrument.make_qty(float(kline[5])),
                        ts_event=millis_to_nanos(kline[0]),
                        ts_init=millis_to_nanos(kline[0]),
                    )

                    # Feed to indicator manager
                    self.indicator_manager.update(bar)
                    bars_fed += 1

                except Exception as e:
                    self.log.warning(f"Failed to convert kline to bar: {e}")
                    continue

            self.log.info(
                f"✅ Pre-fetched {bars_fed} bars successfully! "
                f"Indicators ready: {self.indicator_manager.is_initialized()}"
            )

        except Exception as e:
            self.log.error(f"❌ Failed to pre-fetch bars from Binance: {e}")
            self.log.warning("Continuing with live bars only...")

    def on_bar(self, bar: Bar):
        """
        Handle bar updates.

        Parameters
        ----------
        bar : Bar
            The bar received
        """
        self.bars_received += 1

        # Multi-Timeframe routing (v3.2.8)
        if self.mtf_enabled and self.mtf_manager:
            layer = self.mtf_manager.route_bar(bar)
            if layer == "trend":
                # 趋势层 (1D) 只更新指标，RISK 状态在 on_timer 中评估
                self.log.debug(f"MTF: trend (1D) bar routed")
                return
            elif layer == "decision":
                # 决策层 (4H) 收盘时评估方向 - 核心 MTF 逻辑
                self.log.info(f"[MTF] 4H bar 收盘，触发决策层评估...")
                self._evaluate_decision_layer_on_bar_close(bar)
                return
            elif layer == "execution":
                # Update cached price for execution layer
                with self._state_lock:
                    self._cached_current_price = float(bar.close)
                # Continue to normal bar processing
            elif layer == "unknown":
                self.log.warning(f"MTF: Unknown bar type, falling back to single-timeframe")
                # Fall through to single-timeframe processing

        # Update technical indicators (single-timeframe mode)
        self.indicator_manager.update(bar)

        # Update cached price (thread-safe for Telegram commands)
        # This avoids accessing indicator_manager from Telegram thread which causes Rust panic
        with self._state_lock:
            self._cached_current_price = float(bar.close)

        # Log bar data
        if self.bars_received % 10 == 0:
            self.log.info(
                f"Bar #{self.bars_received}: "
                f"O:{bar.open} H:{bar.high} L:{bar.low} C:{bar.close} V:{bar.volume}"
            )

    def _evaluate_decision_layer_on_bar_close(self, bar: Bar):
        """
        评估决策层方向 (在 4H bar 收盘时调用)

        根据设计文档 Section 1.5.4，决策层应该在 4H bar 收盘时评估，
        使用技术指标规则确定方向 (ALLOW_LONG / ALLOW_SHORT / WAIT)。

        这个方向状态将持续到下一个 4H bar 收盘，期间 on_timer 中的
        交易信号必须符合此方向才能执行。

        Parameters
        ----------
        bar : Bar
            4H bar 数据
        """
        if not self.mtf_manager or not self.mtf_manager.decision_manager:
            self.log.warning("[MTF] 决策层管理器未初始化")
            return

        current_price = float(bar.close)

        # 获取 4H 决策层技术数据
        try:
            decision_data = self.mtf_manager.get_technical_data_for_layer("decision", current_price)

            if not decision_data.get('_initialized', True):
                self.log.warning("[MTF] 决策层指标未完全初始化，保持当前状态")
                return

            # 提取关键指标
            macd = decision_data.get('macd', 0)
            macd_signal = decision_data.get('macd_signal', 0)
            rsi = decision_data.get('rsi', 50)
            sma_20 = decision_data.get('sma_20', current_price)
            sma_50 = decision_data.get('sma_50', current_price)
            overall_trend = decision_data.get('overall_trend', 'NEUTRAL')

            # 决策规则 (基于 4H 技术指标)
            # 规则设计参考业界最佳实践：
            # - MACD 金叉/死叉 作为主要方向信号
            # - RSI 区间确认动量
            # - 价格与均线关系确认趋势

            bullish_signals = 0
            bearish_signals = 0

            # 规则 1: MACD 方向
            if macd > macd_signal and macd > 0:
                bullish_signals += 2  # MACD 金叉且为正，强看涨
            elif macd > macd_signal:
                bullish_signals += 1  # MACD 金叉但为负，弱看涨
            elif macd < macd_signal and macd < 0:
                bearish_signals += 2  # MACD 死叉且为负，强看跌
            elif macd < macd_signal:
                bearish_signals += 1  # MACD 死叉但为正，弱看跌

            # 规则 2: RSI 区间
            if rsi > 55:
                bullish_signals += 1
            elif rsi < 45:
                bearish_signals += 1

            # 规则 3: 价格与均线关系
            if current_price > sma_20 and sma_20 > sma_50:
                bullish_signals += 1  # 多头排列
            elif current_price < sma_20 and sma_20 < sma_50:
                bearish_signals += 1  # 空头排列

            # 决定方向
            old_state = self.mtf_manager.get_decision_state()

            if bullish_signals >= 3 and bullish_signals > bearish_signals:
                confidence = "HIGH" if bullish_signals >= 4 else "MEDIUM"
                self.mtf_manager.set_decision_state(self._DecisionState.ALLOW_LONG, confidence)
                self.log.info(
                    f"[MTF] 4H 决策层评估: ALLOW_LONG ({confidence}) | "
                    f"多头信号={bullish_signals}, 空头信号={bearish_signals} | "
                    f"MACD={macd:.2f}, RSI={rsi:.1f}, Price vs SMA20={current_price:.2f}/{sma_20:.2f}"
                )
            elif bearish_signals >= 3 and bearish_signals > bullish_signals:
                confidence = "HIGH" if bearish_signals >= 4 else "MEDIUM"
                self.mtf_manager.set_decision_state(self._DecisionState.ALLOW_SHORT, confidence)
                self.log.info(
                    f"[MTF] 4H 决策层评估: ALLOW_SHORT ({confidence}) | "
                    f"多头信号={bullish_signals}, 空头信号={bearish_signals} | "
                    f"MACD={macd:.2f}, RSI={rsi:.1f}, Price vs SMA20={current_price:.2f}/{sma_20:.2f}"
                )
            else:
                self.mtf_manager.set_decision_state(self._DecisionState.WAIT, "LOW")
                self.log.info(
                    f"[MTF] 4H 决策层评估: WAIT (方向不明确) | "
                    f"多头信号={bullish_signals}, 空头信号={bearish_signals} | "
                    f"MACD={macd:.2f}, RSI={rsi:.1f}"
                )

            # 如果状态变化，发送 Telegram 通知
            new_state = self.mtf_manager.get_decision_state()
            if old_state != new_state and self.telegram_bot and self.enable_telegram:
                try:
                    state_emoji = {
                        self._DecisionState.ALLOW_LONG: "🟢",
                        self._DecisionState.ALLOW_SHORT: "🔴",
                        self._DecisionState.WAIT: "🟡",
                    }
                    emoji = state_emoji.get(new_state, "⚪")
                    msg = (
                        f"{emoji} [MTF 4H 方向更新]\n"
                        f"方向: {old_state.value} → {new_state.value}\n"
                        f"价格: ${current_price:,.2f}\n"
                        f"MACD: {macd:.2f}\n"
                        f"RSI: {rsi:.1f}"
                    )
                    self.telegram_bot.send_message_sync(msg)
                except Exception as e:
                    self.log.warning(f"Telegram 通知发送失败: {e}")

        except Exception as e:
            self.log.error(f"[MTF] 决策层评估失败: {e}")

    def on_historical_data(self, data):
        """
        Handle historical data from request_bars() (v3.2.8).

        NautilusTrader calls this method when historical bars arrive
        from an asynchronous request_bars() call.

        Parameters
        ----------
        data : BarDataResponse
            Historical bar data response containing bars and bar_type
        """
        if not hasattr(data, 'bars') or not data.bars:
            self.log.warning("on_historical_data: Received empty or invalid data")
            return

        bars = data.bars
        bar_type = data.bar_type if hasattr(data, 'bar_type') else None

        if not self.mtf_enabled or not self.mtf_manager:
            # Single-timeframe mode: update indicator_manager
            for bar in bars:
                self.indicator_manager.update(bar)
            self.log.info(f"Historical data loaded: {len(bars)} bars")
            return

        # Multi-Timeframe mode: route to appropriate layer
        if bar_type == self.trend_bar_type:
            for bar in bars:
                self.mtf_manager.trend_manager.update(bar)
            self._mtf_trend_initialized = True
            self.log.info(f"MTF: 趋势层预取完成 ({len(bars)} bars)")

        elif bar_type == self.decision_bar_type:
            for bar in bars:
                self.mtf_manager.decision_manager.update(bar)
            self._mtf_decision_initialized = True
            self.log.info(f"MTF: 决策层预取完成 ({len(bars)} bars)")

        elif bar_type == self.execution_bar_type:
            for bar in bars:
                self.mtf_manager.execution_manager.update(bar)
            self._mtf_execution_initialized = True
            self.log.info(f"MTF: 执行层预取完成 ({len(bars)} bars)")

        else:
            # Unknown bar_type, update single-timeframe indicator
            for bar in bars:
                self.indicator_manager.update(bar)
            self.log.info(f"Historical data loaded (unknown type): {len(bars)} bars")

        # Check if all MTF layers are initialized
        if (self._mtf_trend_initialized and
            self._mtf_decision_initialized and
            self._mtf_execution_initialized):
            self._verify_mtf_initialization()

    def _verify_mtf_initialization(self):
        """Verify all MTF layers have sufficient data (v3.2.8)."""
        if not self.mtf_manager:
            return

        issues = []

        # Check trend layer (needs 200 bars for SMA_200)
        if self.mtf_manager.trend_manager:
            trend_bars = len(self.mtf_manager.trend_manager.recent_bars) if hasattr(self.mtf_manager.trend_manager, 'recent_bars') else 0
            if trend_bars < 200:
                issues.append(f"趋势层 bars 不足: {trend_bars}/200")

        # Check decision layer (needs 50 bars for SMA_50)
        if self.mtf_manager.decision_manager:
            decision_bars = len(self.mtf_manager.decision_manager.recent_bars) if hasattr(self.mtf_manager.decision_manager, 'recent_bars') else 0
            if decision_bars < 50:
                issues.append(f"决策层 bars 不足: {decision_bars}/50")

        # Check execution layer (needs 20 bars)
        if self.mtf_manager.execution_manager:
            exec_bars = len(self.mtf_manager.execution_manager.recent_bars) if hasattr(self.mtf_manager.execution_manager, 'recent_bars') else 0
            if exec_bars < 20:
                issues.append(f"执行层 bars 不足: {exec_bars}/20")

        if issues:
            self.log.warning(f"MTF 初始化警告: {', '.join(issues)}")
            if self.telegram_bot and self.enable_telegram:
                self.telegram_bot.send_message_sync(
                    f"⚠️ MTF 初始化警告:\n" + "\n".join(f"• {i}" for i in issues)
                )
        else:
            self.log.info("MTF: 所有层指标管理器初始化完成 ✓")

    def _prefetch_multi_timeframe_bars(self):
        """
        Prefetch historical bars for all MTF layers using direct Binance API.

        v3.2.10: Fixed to use direct Binance API calls instead of NautilusTrader
        request_bars() which doesn't work with EXTERNAL data sources.

        Uses the same approach as _prefetch_historical_bars() for reliability.
        """
        if not self.mtf_enabled or not self.mtf_manager:
            return

        self.log.info("MTF: 开始预取历史数据 (直接 Binance API)...")

        try:
            import requests
            from nautilus_trader.core.datetime import millis_to_nanos

            # Extract symbol from instrument_id (BTCUSDT-PERP.BINANCE -> BTCUSDT)
            symbol_str = str(self.instrument_id)
            symbol = symbol_str.split('-')[0]

            # Binance Futures API endpoint
            url = "https://fapi.binance.com/fapi/v1/klines"
            timeout = self.config.network_bar_persistence_timeout

            # === Trend Layer (1D) - SMA_200 needs 220 bars ===
            self.log.info(f"MTF: 预取趋势层 (1D, 220 bars)...")
            trend_bars = self._fetch_binance_klines(
                url, symbol, '1d', 220, timeout,
                self.trend_bar_type, self.mtf_manager.trend_manager
            )
            if trend_bars > 0:
                self._mtf_trend_initialized = True
                self.log.info(f"✅ MTF 趋势层预取完成: {trend_bars} bars")

            # === Decision Layer (4H) - SMA_50, MACD need 60 bars ===
            self.log.info(f"MTF: 预取决策层 (4H, 60 bars)...")
            decision_bars = self._fetch_binance_klines(
                url, symbol, '4h', 60, timeout,
                self.decision_bar_type, self.mtf_manager.decision_manager
            )
            if decision_bars > 0:
                self._mtf_decision_initialized = True
                self.log.info(f"✅ MTF 决策层预取完成: {decision_bars} bars")

            # === Execution Layer (15M) - RSI, EMA need 40 bars ===
            self.log.info(f"MTF: 预取执行层 (15M, 40 bars)...")
            execution_bars = self._fetch_binance_klines(
                url, symbol, '15m', 40, timeout,
                self.execution_bar_type, self.mtf_manager.execution_manager
            )
            if execution_bars > 0:
                self._mtf_execution_initialized = True
                self.log.info(f"✅ MTF 执行层预取完成: {execution_bars} bars")

            # Summary
            self.log.info(
                f"✅ MTF 历史数据预取完成: "
                f"趋势={trend_bars}, 决策={decision_bars}, 执行={execution_bars}"
            )

        except Exception as e:
            self.log.error(f"❌ MTF 预取历史数据失败: {e}")
            self.log.warning("MTF 将使用实时数据初始化 (需要等待更长时间)")

    def _fetch_binance_klines(self, url, symbol, interval, limit, timeout, bar_type, indicator_manager):
        """
        Fetch klines from Binance API and feed to indicator manager.

        Returns number of bars successfully fed.
        """
        import requests
        from nautilus_trader.core.datetime import millis_to_nanos

        try:
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': min(limit, 1500),  # Binance max
            }

            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            klines = response.json()

            if not klines:
                self.log.warning(f"⚠️ Binance API 返回空数据 (interval={interval})")
                return 0

            bars_fed = 0
            for kline in klines:
                try:
                    bar = Bar(
                        bar_type=bar_type,
                        open=self.instrument.make_price(float(kline[1])),
                        high=self.instrument.make_price(float(kline[2])),
                        low=self.instrument.make_price(float(kline[3])),
                        close=self.instrument.make_price(float(kline[4])),
                        volume=self.instrument.make_qty(float(kline[5])),
                        ts_event=millis_to_nanos(kline[0]),
                        ts_init=millis_to_nanos(kline[0]),
                    )
                    indicator_manager.update(bar)
                    bars_fed += 1
                except Exception as e:
                    self.log.debug(f"转换 kline 失败: {e}")
                    continue

            return bars_fed

        except Exception as e:
            self.log.error(f"Binance API 请求失败 ({interval}): {e}")
            return 0

    def on_timer(self, event):
        """
        Periodic analysis and trading logic.

        Called every timer_interval_sec seconds (default: 15 minutes).
        """
        # 🔒 Fix I38: Prevent re-entry if previous on_timer is still running
        # (e.g., AI calls take longer than timer_interval_sec)
        if not self._timer_lock.acquire(blocking=False):
            self.log.warning("⚠️ Previous on_timer still running, skipping this cycle")
            return

        try:
            self.log.info("=" * 60)
            self.log.info("Running periodic analysis...")

            # v2.1: Increment timer counter for heartbeat tracking
            self._timer_count = getattr(self, '_timer_count', 0) + 1

            # v2.1: 发送心跳 - 移到 on_timer 开始位置，确保每次都发送
            # 即使后续分析失败，用户也能知道服务器在运行
            self._send_heartbeat_notification()

            # Check if indicators are ready
            if not self.indicator_manager.is_initialized():
                self.log.warning("Indicators not yet initialized, skipping analysis")
                return

            # ========== MTF 初始化检查 ==========
            # 如果启用了 MTF，检查三层是否都已初始化
            if self.mtf_enabled and self.mtf_manager:
                if not self.mtf_manager.is_all_layers_initialized():
                    self.log.warning("[MTF] 多时间框架未完全初始化，跳过分析")
                    self.log.debug(f"[MTF] 初始化状态: trend={self._mtf_trend_initialized}, "
                                  f"decision={self._mtf_decision_initialized}, "
                                  f"execution={self._mtf_execution_initialized}")
                    return

            # Get current market data
            current_bar = self.indicator_manager.recent_bars[-1] if self.indicator_manager.recent_bars else None
            if not current_bar:
                self.log.warning("No bars available for analysis")
                return

            current_price = float(current_bar.close)

            # Get technical data (15M - execution layer)
            try:
                technical_data = self.indicator_manager.get_technical_data(current_price)
                self.log.debug(f"Technical data (15M) retrieved: {len(technical_data)} indicators")
            except Exception as e:
                self.log.error(f"Failed to get technical data: {e}")
                return

            # Get 4H decision layer technical data for AI debate (MTF Phase 2)
            decision_layer_data = None
            if self.mtf_enabled and self.mtf_manager:
                try:
                    decision_layer_data = self.mtf_manager.get_technical_data_for_layer("decision", current_price)
                    if decision_layer_data.get('_initialized', True):
                        self.log.info(
                            f"[MTF] 决策层 (4H) 数据: RSI={decision_layer_data.get('rsi', 0):.1f}, "
                            f"MACD={decision_layer_data.get('macd', 0):.2f}, "
                            f"SMA_20={decision_layer_data.get('sma_20', 0):.2f}"
                        )
                    else:
                        self.log.warning("[MTF] 决策层 (4H) 未完全初始化，使用 15M 数据")
                        decision_layer_data = None
                except Exception as e:
                    self.log.warning(f"[MTF] 获取决策层数据失败: {e}")
                    decision_layer_data = None

            # Get K-line data
            kline_data = self.indicator_manager.get_kline_data(count=10)
            self.log.debug(f"Retrieved {len(kline_data)} K-lines for analysis")

            # Get sentiment data (with default neutral values as fallback)
            sentiment_data = None
            if self.sentiment_enabled and self.sentiment_fetcher:
                try:
                    sentiment_data = self.sentiment_fetcher.fetch()
                    if sentiment_data:
                        self.log.info(self.sentiment_fetcher.format_for_display(sentiment_data))
                except Exception as e:
                    self.log.warning(f"Failed to fetch sentiment data: {e}")

            # Provide default neutral sentiment if unavailable (prevents None being passed to AI)
            if sentiment_data is None:
                sentiment_data = {
                    'long_short_ratio': 1.0,  # Neutral (equal longs and shorts)
                    'long_account_pct': 50.0,
                    'short_account_pct': 50.0,
                    'positive_ratio': 0.5,   # Required by deepseek_client
                    'negative_ratio': 0.5,   # Required by deepseek_client
                    'net_sentiment': 0.0,    # Required by deepseek_client (long - short = 0)
                    'source': 'default_neutral',
                    'timestamp': None,
                }
                self.log.info("📊 Using neutral sentiment data (no data available)")

            # Build price data for AI
            price_data = {
                'price': current_price,
                'timestamp': self.clock.utc_now().isoformat(),
                'high': float(current_bar.high),
                'low': float(current_bar.low),
                'volume': float(current_bar.volume),
                'price_change': self._calculate_price_change(),
                'kline_data': kline_data,
            }

            # Get current position
            current_position = self._get_current_position_data()

            # Log current state
            self.log.info(f"Current Price: ${current_price:,.2f}")
            self.log.info(f"Overall Trend: {technical_data.get('overall_trend', 'N/A')}")
            self.log.info(f"RSI: {technical_data.get('rsi', 0):.2f}")
            if current_position:
                self.log.info(
                    f"Current Position: {current_position['side']} "
                    f"{current_position['quantity']} @ ${current_position['avg_px']:.2f}"
                )

            # ========== 层级决策架构 (TradingAgents v3.1) ==========
            # 设计理念: AI 负责所有交易决策，本地仅做支撑/阻力位边界检查
            # 移除了 RISK_OFF 趋势过滤 - AI 自主判断趋势方向
            # MultiAgent 的 Judge 作为最终决策者，不再与 DeepSeek 并行合并
            # 流程: Bull/Bear 辩论 → Judge 决策 → Risk 评估 → 最终信号
            try:
                self.log.info("🎭 Starting Multi-Agent Hierarchical Analysis...")
                self.log.info("   Phase 1: Bull/Bear Debate (using 4H decision layer data)")
                self.log.info("   Phase 2: Judge (Portfolio Manager) Decision")
                self.log.info("   Phase 3: Risk Evaluation")

                # 准备 AI 分析数据：优先使用 4H 决策层数据
                # 根据 MTF 设计文档 Section 1.5.4，Bull/Bear 辩论应使用 4H 数据
                ai_technical_data = technical_data.copy()  # 15M 作为基础
                # 🏷️ Fix A4: 添加 timeframe 标记，避免 AI 混淆不同周期数据
                ai_technical_data['timeframe'] = '15M'
                # 重要: 添加 price 到 technical_data (multi_agent_analyzer._format_technical_report 需要)
                ai_technical_data['price'] = current_price
                if decision_layer_data and decision_layer_data.get('_initialized', True):
                    # 添加 4H 数据作为决策层信息
                    # TradingAgents v3.3: 只传原始数据，不传 overall_trend 预判断
                    ai_technical_data['mtf_decision_layer'] = {
                        'timeframe': '4H',
                        'rsi': decision_layer_data.get('rsi', 50),
                        'macd': decision_layer_data.get('macd', 0),
                        'macd_signal': decision_layer_data.get('macd_signal', 0),
                        'sma_20': decision_layer_data.get('sma_20', 0),
                        'sma_50': decision_layer_data.get('sma_50', 0),
                        'bb_upper': decision_layer_data.get('bb_upper', 0),
                        'bb_middle': decision_layer_data.get('bb_middle', 0),
                        'bb_lower': decision_layer_data.get('bb_lower', 0),
                        # 'overall_trend' 已移除 - AI 使用 INDICATOR_DEFINITIONS 自己判断
                    }
                    self.log.info(f"[MTF] AI 分析使用 4H 决策层数据: RSI={ai_technical_data['mtf_decision_layer']['rsi']:.1f}")

                # ========== 获取订单流数据 (MTF v2.1) ==========
                order_flow_data = None
                if self.binance_kline_client and self.order_flow_processor:
                    try:
                        # 获取 Binance 完整 K线 (12 列，包含订单流字段)
                        raw_klines = self.binance_kline_client.get_klines(
                            symbol="BTCUSDT",
                            interval="15m",
                            limit=50,
                        )
                        if raw_klines:
                            order_flow_data = self.order_flow_processor.process_klines(raw_klines)
                            self.log.info(
                                f"📊 Order Flow: buy_ratio={order_flow_data.get('buy_ratio', 0):.1%}, "
                                f"cvd_trend={order_flow_data.get('cvd_trend', 'N/A')}"
                            )
                        else:
                            self.log.warning("⚠️ Failed to get Binance klines for order flow")
                    except Exception as e:
                        self.log.warning(f"⚠️ Order flow processing failed: {e}")

                # ========== 获取衍生品数据 (MTF v2.1) ==========
                derivatives_data = None
                if self.coinalyze_client and self.coinalyze_client.is_enabled():
                    try:
                        derivatives_data = self.coinalyze_client.fetch_all()
                        if derivatives_data.get('enabled'):
                            oi = derivatives_data.get('open_interest')
                            funding = derivatives_data.get('funding_rate')
                            self.log.info(
                                f"📊 Derivatives: OI={oi.get('value', 0):.2f} BTC, "
                                f"Funding={funding.get('value', 0)*100:.4f}%" if oi and funding else "Derivatives: partial data"
                            )
                        else:
                            self.log.debug("Coinalyze client disabled, no derivatives data")
                    except Exception as e:
                        self.log.warning(f"⚠️ Derivatives fetch failed: {e}")

                signal_data = self.multi_agent.analyze(
                    symbol="BTCUSDT",
                    technical_report=ai_technical_data,
                    sentiment_report=sentiment_data,
                    current_position=current_position,
                    price_data=price_data,
                    # ========== MTF v2.1 新增参数 ==========
                    order_flow_report=order_flow_data,
                    derivatives_report=derivatives_data,
                )

                # ========== TradingAgents v3.1: AI 完全自主决策 ==========
                # 设计理念: "Autonomy is non-negotiable" - AI 像人类分析师一样思考
                # 移除了所有本地硬编码规则:
                #   - 趋势方向权限检查 (allow_long/allow_short) - AI 自主判断
                #   - 支撑/阻力位边界检查 - AI 从数据中自己理解
                # AI 看到的数据包含 support/resistance，由 AI 自己决定是否参考

                # Log Judge's final decision
                self.log.info(
                    f"🎯 Judge Decision: {signal_data['signal']} | "
                    f"Confidence: {signal_data['confidence']} | "
                    f"Risk: {signal_data.get('risk_level', 'N/A')}"
                )
                self.log.info(f"📋 Reason: {signal_data.get('reason', 'N/A')}")

                if signal_data.get('debate_summary'):
                    self.log.info(f"🗣️ Debate Summary: {signal_data['debate_summary'][:200]}...")

                # Log judge's detailed decision if available
                judge_decision = signal_data.get('judge_decision', {})
                if judge_decision:
                    winning_side = judge_decision.get('winning_side', 'N/A')
                    key_reasons = judge_decision.get('key_reasons', [])
                    self.log.info(f"⚖️ Winning Side: {winning_side}")
                    if key_reasons:
                        self.log.info(f"📌 Key Reasons: {', '.join(key_reasons[:3])}")

                # Telegram notification moved to after execution (see _execute_trade)
                # This prevents "signal sent but not executed" confusion
                            
            except Exception as e:
                self.log.error(f"Multi-Agent analysis failed: {e}", exc_info=True)

                # Send error notification
                if self.telegram_bot and self.enable_telegram and self.telegram_notify_errors:
                    try:
                        error_msg = self.telegram_bot.format_error_alert({
                            'level': 'ERROR',
                            'message': f"Multi-Agent Analysis Failed: {str(e)[:100]}",
                            'context': 'on_timer'
                        })
                        self.telegram_bot.send_message_sync(error_msg)
                    except Exception as e:
                        self.log.warning(f"Failed to send Telegram error notification: {e}")
                return

            # Store signal
            self.last_signal = signal_data

            # 📸 Fix C16/J43: Save complete decision snapshot for replay
            try:
                mtf_perms = permissions if self.mtf_enabled and self.mtf_manager and 'permissions' in locals() else None
                orig_sig = original_signal if 'original_signal' in locals() else None
                self._save_decision_snapshot(
                    signal_data=signal_data,
                    technical_data=technical_data,
                    sentiment_data=sentiment_data,
                    order_flow_data=order_flow_data if 'order_flow_data' in locals() else None,
                    derivatives_data=derivatives_data if 'derivatives_data' in locals() else None,
                    current_position=current_position,
                    price_data=price_data,
                    mtf_permissions=mtf_perms,
                    original_signal=orig_sig,
                )
            except Exception as e:
                self.log.debug(f"Failed to save decision snapshot: {e}")

            # Execute trade
            self._execute_trade(signal_data, price_data, technical_data, current_position)
            
            # Orphan order cleanup: cancel reduce-only orders when no position exists
            if self.enable_oco:
                self._cleanup_oco_orphans()
            
            # Trailing stop maintenance: check and update trailing stops
            if self.enable_trailing_stop:
                self._update_trailing_stops(price_data['price'])


        finally:
            # 🔒 Fix I38: Always release lock when on_timer exits
            self._timer_lock.release()

    def _save_decision_snapshot(
        self,
        signal_data: dict,
        technical_data: dict,
        sentiment_data: dict,
        order_flow_data: dict,
        derivatives_data: dict,
        current_position: dict,
        price_data: dict,
        mtf_permissions: dict = None,
        original_signal: str = None,
    ):
        """
        🔍 Fix C16/J43: Save complete decision snapshot for debugging and replay.

        Saves all inputs, AI outputs, and filtering decisions to a JSON file.
        This enables full replay of "why did the system make this decision?"
        """
        try:
            import json
            from datetime import datetime
            import os

            # Create logs directory if it doesn't exist
            os.makedirs('logs/decisions', exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            snapshot_file = f'logs/decisions/decision_{timestamp}.json'

            snapshot = {
                'timestamp': datetime.now().isoformat(),
                'inputs': {
                    'technical_data': technical_data,
                    'sentiment_data': sentiment_data,
                    'order_flow_data': order_flow_data,
                    'derivatives_data': derivatives_data,
                    'current_position': current_position,
                    'price_data': price_data,
                },
                'ai_outputs': {
                    'signal': signal_data.get('signal'),
                    'confidence': signal_data.get('confidence'),
                    'risk_level': signal_data.get('risk_level'),
                    'position_size_pct': signal_data.get('position_size_pct'),
                    'stop_loss': signal_data.get('stop_loss'),
                    'take_profit': signal_data.get('take_profit'),
                    'reason': signal_data.get('reason'),
                    'debate_summary': signal_data.get('debate_summary'),
                    'judge_decision': signal_data.get('judge_decision'),
                },
                'mtf_filtering': {
                    'original_signal': original_signal or signal_data.get('signal'),
                    'final_signal': signal_data.get('signal'),
                    'permissions': mtf_permissions,
                    'filtered': original_signal != signal_data.get('signal') if original_signal else False,
                },
            }

            with open(snapshot_file, 'w') as f:
                json.dump(snapshot, f, indent=2, default=str)

            self.log.debug(f"📸 Decision snapshot saved: {snapshot_file}")

        except Exception as e:
            self.log.warning(f"Failed to save decision snapshot: {e}")

    def _send_heartbeat_notification(self):
        """
        v2.3: 发送心跳通知 (简化版) - 在 on_timer 开始时调用

        统一格式，简单可靠。
        """
        if not (self.telegram_bot and self.enable_telegram and getattr(self, 'telegram_notify_heartbeat', False)):
            return

        try:
            # 1. 获取价格
            cached_price = getattr(self, '_cached_current_price', None)
            if cached_price is None and self.indicator_manager.recent_bars:
                cached_price = float(self.indicator_manager.recent_bars[-1].close)

            # 2. 获取 RSI
            rsi = 0
            try:
                if self.indicator_manager.is_initialized():
                    tech_data = self.indicator_manager.get_technical_data(cached_price or 0)
                    rsi = tech_data.get('rsi') or 0
            except Exception:
                pass

            # 3. 获取趋势状态
            trend_status = 'N/A'
            try:
                if self.mtf_enabled and self.mtf_manager:
                    trend_result = self.mtf_manager.check_trend_filter(cached_price or 0)
                    if trend_result:
                        trend_status = 'RISK_ON' if trend_result.get('risk_on', False) else 'RISK_OFF'
            except Exception:
                pass

            # 4. 获取账户余额
            equity = getattr(self, 'equity', 0) or 0

            # 5. 计算运行时长
            uptime_str = 'N/A'
            try:
                start_time = getattr(self, '_start_time', None)
                if start_time:
                    from datetime import datetime
                    uptime_seconds = (datetime.now() - start_time).total_seconds()
                    hours = int(uptime_seconds // 3600)
                    minutes = int((uptime_seconds % 3600) // 60)
                    uptime_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            except Exception:
                pass

            # 6. 获取持仓信息
            position_side = None
            entry_price = 0
            position_size = 0
            position_pnl_pct = 0
            try:
                pos_data = self._get_current_position_data(current_price=cached_price, from_telegram=True)
                if pos_data and pos_data.get('size', 0) != 0:
                    position_side = pos_data.get('side')
                    entry_price = pos_data.get('entry_price') or 0
                    position_size = abs(pos_data.get('size') or 0)
                    if entry_price > 0 and cached_price:
                        if position_side == 'LONG':
                            position_pnl_pct = ((cached_price - entry_price) / entry_price) * 100
                        else:
                            position_pnl_pct = ((entry_price - cached_price) / entry_price) * 100
            except Exception:
                pass

            # 7. 获取上次信号
            last_signal = getattr(self, 'last_signal', None) or {}
            signal = last_signal.get('signal') or 'PENDING'
            confidence = last_signal.get('confidence') or 'N/A'

            # 8. 发送消息
            heartbeat_msg = self.telegram_bot.format_heartbeat_message({
                'signal': signal,
                'confidence': confidence,
                'price': cached_price or 0,
                'rsi': rsi,
                'position_side': position_side,
                'position_pnl_pct': position_pnl_pct,
                'entry_price': entry_price,
                'position_size': position_size,
                'timer_count': getattr(self, '_timer_count', 0),
                'equity': equity,
                'trend_status': trend_status,
                'uptime_str': uptime_str,
            })
            self.telegram_bot.send_message_sync(heartbeat_msg)
            self.log.info(f"💓 Sent heartbeat #{self._timer_count}")
        except Exception as e:
            self.log.warning(f"Failed to send Telegram heartbeat: {e}")

    def _calculate_price_change(self) -> float:
        """Calculate price change percentage."""
        bars = self.indicator_manager.recent_bars
        if len(bars) < 2:
            return 0.0

        current = float(bars[-1].close)
        previous = float(bars[-2].close)

        return ((current - previous) / previous) * 100

    def _get_current_position_data(self, current_price: Optional[float] = None, from_telegram: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get current position information.

        Parameters
        ----------
        current_price : float, optional
            If provided, use this price for PnL calculation.
        from_telegram : bool, default False
            If True, NEVER access indicator_manager (Telegram thread safety).
            When True, will use cache.price() as fallback instead of indicator_manager.
        """
        # Get open positions for this instrument
        positions = self.cache.positions_open(instrument_id=self.instrument_id)

        if not positions:
            return None

        # Get the first open position (should only be one for netting OMS)
        position = positions[0]

        if position and position.is_open:
            # Get current price for PnL calculation
            if current_price is None or current_price == 0:
                if from_telegram:
                    # CRITICAL: Never access indicator_manager from Telegram thread!
                    # Rust indicators (RSI, MACD) are not Send/Sync and will panic
                    try:
                        current_price = self.cache.price(self.instrument_id, PriceType.LAST)
                    except (TypeError, AttributeError):
                        current_price = None
                else:
                    # Main thread: safe to access indicator_manager
                    bars = self.indicator_manager.recent_bars
                    if bars:
                        current_price = bars[-1].close
                    else:
                        try:
                            current_price = self.cache.price(self.instrument_id, PriceType.LAST)
                        except (TypeError, AttributeError):
                            current_price = None

            return {
                'side': 'long' if position.side == PositionSide.LONG else 'short',
                'quantity': float(position.quantity),
                'avg_px': float(position.avg_px_open),
                'unrealized_pnl': float(position.unrealized_pnl(current_price)) if current_price else 0.0,
            }

        return None

    # NOTE: Hierarchical Decision Architecture - MultiAgent Judge 作为唯一决策者
    # 不再需要信号合并逻辑，Judge 决策即最终决策

    def _execute_trade(
        self,
        signal_data: Dict[str, Any],
        price_data: Dict[str, Any],
        technical_data: Dict[str, Any],
        current_position: Optional[Dict[str, Any]],
    ):
        """
        Execute trading logic based on signal.

        Parameters
        ----------
        signal_data : Dict
            AI-generated signal
        price_data : Dict
            Current price data
        technical_data : Dict
            Technical indicators
        current_position : Dict or None
            Current position info
        """
        # Check if trading is paused (thread-safe read)
        with self._state_lock:
            if self.is_trading_paused:
                self.log.info("⏸️ Trading is paused - skipping signal execution")
                return
        
        # Store signal and technical data for SL/TP calculation
        self.latest_signal_data = signal_data
        self.latest_technical_data = technical_data
        self.latest_price_data = price_data
        
        signal = signal_data['signal']
        confidence = signal_data['confidence']

        # Check minimum confidence
        confidence_levels = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}
        min_conf_level = confidence_levels.get(self.min_confidence, 1)
        signal_conf_level = confidence_levels.get(confidence, 1)

        if signal_conf_level < min_conf_level:
            self.log.warning(
                f"⚠️ Signal confidence {confidence} below minimum {self.min_confidence}, skipping trade"
            )
            return

        # Handle HOLD signal
        if signal == 'HOLD':
            self.log.info("📊 Signal: HOLD - No action taken")
            return

        # Calculate target position size
        target_quantity = self._calculate_position_size(
            signal_data, price_data, technical_data, current_position
        )

        if target_quantity == 0:
            self.log.warning("⚠️ Calculated position size is 0, skipping trade")

            # Notify user about insufficient position size (helpful for low-balance accounts)
            if self.telegram_bot and self.enable_telegram and self.telegram_notify_errors:
                try:
                    current_price = price_data.get('price', 0) if price_data else 0
                    error_msg = self.telegram_bot.format_error_alert({
                        'type': 'POSITION_SIZE_ZERO',
                        'message': f"Cannot trade {signal} signal - position size calculated as 0",
                        'details': f"Price: ${current_price:.2f}, Signal: {signal} ({confidence})",
                        'action': "Check account balance or adjust position sizing parameters"
                    })
                    self.telegram_bot.send_message_sync(error_msg)
                except Exception as notify_error:
                    self.log.error(f"Failed to send Telegram alert: {notify_error}")

            return

        # Determine order side
        target_side = 'long' if signal == 'BUY' else 'short'

        # Execute position management logic
        if current_position:
            self._manage_existing_position(
                current_position, target_side, target_quantity, confidence
            )
        else:
            self._open_new_position(target_side, target_quantity)

        # Send Telegram notification AFTER execution (符合 TradingAgents 意图)
        # This prevents "signal sent but not executed" confusion
        if self.telegram_bot and self.enable_telegram and self.telegram_notify_signals:
            try:
                judge_info = signal_data.get('judge_decision', {})
                winning_side = judge_info.get('winning_side', 'N/A')
                debate_summary = signal_data.get('debate_summary', '')

                signal_notification = self.telegram_bot.format_trade_signal({
                    'signal': signal,
                    'confidence': confidence,
                    'price': price_data['price'],
                    'timestamp': price_data['timestamp'],
                    'rsi': technical_data.get('rsi', 0),
                    'macd': technical_data.get('macd', 0),
                    'support': technical_data.get('support', 0),
                    'resistance': technical_data.get('resistance', 0),
                    'reasoning': signal_data.get('reason', ''),
                    'winning_side': winning_side,
                    'debate_summary': debate_summary[:100] if debate_summary else '',
                })
                self.telegram_bot.send_message_sync(signal_notification)
                self.log.info("✅ Telegram notification sent after execution")
            except Exception as e:
                self.log.warning(f"Failed to send Telegram signal notification: {e}")

    def _calculate_position_size(
        self,
        signal_data: Dict[str, Any],
        price_data: Dict[str, Any],
        technical_data: Dict[str, Any],
        current_position: Optional[Dict[str, Any]],
    ) -> float:
        """
        Calculate intelligent position size.

        Uses shared trading_logic module to ensure consistency with diagnostic tool.
        Returns BTC quantity based on confidence, trend, and RSI.
        """
        # Create a simple logger adapter that uses self.log
        class LogAdapter:
            def __init__(self, strategy_log):
                self._log = strategy_log
            def info(self, msg):
                self._log.info(msg)
            def warning(self, msg):
                self._log.warning(msg)
            def error(self, msg):
                self._log.error(msg)

        logger = LogAdapter(self.log)

        # Build config dict from instance variables
        config = {
            'base_usdt': self.base_usdt,
            'equity': self.equity,
            'high_confidence_multiplier': self.position_config.get('high_confidence_multiplier', 1.5),
            'medium_confidence_multiplier': self.position_config.get('medium_confidence_multiplier', 1.0),
            'low_confidence_multiplier': self.position_config.get('low_confidence_multiplier', 0.5),
            'trend_strength_multiplier': self.position_config.get('trend_strength_multiplier', 1.2),
            'rsi_extreme_multiplier': self.rsi_extreme_mult,
            'rsi_extreme_upper': self.rsi_extreme_upper,
            'rsi_extreme_lower': self.rsi_extreme_lower,
            'max_position_ratio': self.position_config.get('max_position_ratio', 0.3),
            'min_trade_amount': self.position_config.get('min_trade_amount', 0.001),
        }

        btc_quantity, _ = calculate_position_size(
            signal_data, price_data, technical_data, config, logger
        )
        return btc_quantity

    def _manage_existing_position(
        self,
        current_position: Dict[str, Any],
        target_side: str,
        target_quantity: float,
        confidence: str,
    ):
        """Manage existing position (add, reduce, or reverse)."""
        current_side = current_position['side']
        current_qty = current_position['quantity']

        # Same direction - adjust position
        if target_side == current_side:
            size_diff = target_quantity - current_qty
            threshold = self.position_config['adjustment_threshold']

            if abs(size_diff) < threshold:
                self.log.info(
                    f"✅ Position size appropriate ({current_qty:.3f} BTC), no adjustment needed"
                )
                return

            if size_diff > 0:
                # Add to position with simple market order
                # NOTE: Bracket orders CANNOT be used for adding to existing positions
                # They can only be used for opening new positions (entry + SL + TP linked)
                order_side = OrderSide.BUY if target_side == 'long' else OrderSide.SELL
                self._submit_order(
                    side=order_side,
                    quantity=abs(size_diff),
                    reduce_only=False,
                )
                self.log.info(
                    f"📈 Adding to {target_side} position: {abs(size_diff):.3f} BTC "
                    f"({current_qty:.3f} → {target_quantity:.3f})"
                )
            else:
                # Reduce position
                self._submit_order(
                    side=OrderSide.SELL if target_side == 'long' else OrderSide.BUY,
                    quantity=abs(size_diff),
                    reduce_only=True,
                )
                self.log.info(
                    f"📉 Reducing {target_side} position: {abs(size_diff):.3f} BTC "
                    f"({current_qty:.3f} → {target_quantity:.3f})"
                )

        # Opposite direction - reverse position
        elif self.allow_reversals:
            # Check if high confidence required for reversal
            if self.require_high_conf_reversal and confidence != 'HIGH':
                self.log.warning(
                    f"🔒 Reversal requires HIGH confidence, got {confidence}. "
                    f"Keeping {current_side} position."
                )
                return

            self.log.info(f"🔄 Reversing position: {current_side} → {target_side}")

            # Close current position
            self._submit_order(
                side=OrderSide.SELL if current_side == 'long' else OrderSide.BUY,
                quantity=current_qty,
                reduce_only=True,
            )

            # Open opposite position with bracket order (entry + SL + TP)
            # This ensures the new position has proper risk protection from the start
            new_order_side = OrderSide.BUY if target_side == 'long' else OrderSide.SELL
            self._submit_bracket_order(
                side=new_order_side,
                quantity=target_quantity,
            )
            self.log.info(
                f"🔄 Opened new {target_side} position: {target_quantity:.3f} BTC (with bracket SL/TP)"
            )

        else:
            self.log.warning(
                f"⚠️ Signal suggests {target_side} but have {current_side} position. "
                f"Reversals disabled."
            )

    def _open_new_position(self, side: str, quantity: float):
        """
        Open new position using bracket order (entry + SL + TP).

        This method submits a bracket order which automatically includes:
        - Entry order (MARKET)
        - Stop Loss order (STOP_MARKET)
        - Take Profit order(s) (LIMIT)

        The SL and TP orders are linked with OCO, so when one fills, the others cancel.
        """
        order_side = OrderSide.BUY if side == 'long' else OrderSide.SELL

        # Submit bracket order with SL/TP
        self._submit_bracket_order(
            side=order_side,
            quantity=quantity,
        )

        self.log.info(f"🚀 Opening {side} position: {quantity:.3f} BTC (with bracket SL/TP)")

    def _submit_order(
        self,
        side: OrderSide,
        quantity: float,
        reduce_only: bool = False,
    ):
        """Submit market order to exchange."""
        if quantity < self.position_config['min_trade_amount']:
            self.log.warning(
                f"⚠️ Order quantity {quantity:.3f} below minimum "
                f"{self.position_config['min_trade_amount']:.3f}, skipping"
            )
            return

        # Create market order
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=self.instrument.make_qty(quantity),
            time_in_force=TimeInForce.GTC,
            reduce_only=reduce_only,
        )

        # Submit order
        self.submit_order(order)

        self.log.info(
            f"📤 Submitted {side.name} market order: {quantity:.3f} BTC "
            f"(reduce_only={reduce_only})"
        )
    
    def _submit_bracket_order(
        self,
        side: OrderSide,
        quantity: float,
    ):
        """
        Submit a bracket order with entry, stop loss, and take profit using NautilusTrader's built-in bracket orders.

        This uses the OrderFactory.bracket() method which automatically creates:
        - Entry order (MARKET)
        - Stop Loss order (STOP_MARKET) linked with OTO (One-Triggers-Other)
        - Take Profit order (LIMIT) linked with OTO and OCO with SL

        The OCO linkage is handled automatically by NautilusTrader.

        Parameters
        ----------
        side : OrderSide
            Side of the entry order (BUY or SELL)
        quantity : float
            Quantity to trade
        """
        if quantity < self.position_config['min_trade_amount']:
            self.log.warning(
                f"⚠️ Order quantity {quantity:.3f} below minimum "
                f"{self.position_config['min_trade_amount']:.3f}, skipping"
            )
            return

        if not self.enable_auto_sl_tp:
            self.log.warning("⚠️ Auto SL/TP is disabled - submitting simple market order instead")
            self._submit_order(side=side, quantity=quantity, reduce_only=False)
            return

        if not self.latest_signal_data or not self.latest_technical_data:
            self.log.warning("⚠️ No signal/technical data available for SL/TP - submitting simple market order")
            self._submit_order(side=side, quantity=quantity, reduce_only=False)
            return

        # Determine latest price for entry estimation
        entry_price: Optional[float] = None

        if self.latest_price_data and self.latest_price_data.get('price'):
            entry_price = float(self.latest_price_data['price'])

        if entry_price is None and hasattr(self.indicator_manager, "recent_bars"):
            recent_bars = self.indicator_manager.recent_bars
            if recent_bars:
                entry_price = float(recent_bars[-1].close)

        if entry_price is None:
            cache_bars = self.cache.bars(self.bar_type)
            if cache_bars:
                entry_price = float(cache_bars[-1].close)

        if entry_price is None or entry_price <= 0:
            self.log.error("❌ Unable to determine entry price for bracket order, submitting market order instead")
            self._submit_order(side=side, quantity=quantity, reduce_only=False)
            return

        # Get confidence and technical data
        confidence = self.latest_signal_data.get('confidence', 'MEDIUM')
        support = self.latest_technical_data.get('support', 0.0)
        resistance = self.latest_technical_data.get('resistance', 0.0)

        # Check for MultiAgent SL/TP (from Judge decision)
        # Note: MultiAgent returns 'stop_loss' and 'take_profit' fields directly
        multi_sl = self.latest_signal_data.get('stop_loss')
        multi_tp = self.latest_signal_data.get('take_profit')

        # Use shared function to validate MultiAgent SL/TP (same logic as diagnose_realtime.py)
        is_valid, validated_sl, validated_tp, validation_reason = validate_multiagent_sltp(
            side=side.name,  # Convert OrderSide.BUY → 'BUY'
            multi_sl=multi_sl,
            multi_tp=multi_tp,
            entry_price=entry_price,
        )

        if is_valid:
            # MultiAgent SL/TP validated successfully
            stop_loss_price = validated_sl
            tp_price = validated_tp
            self.log.info(f"🎯 Using MultiAgent SL/TP: {validation_reason}")
        else:
            # Fall back to technical analysis using shared function
            if multi_sl or multi_tp:
                self.log.warning(f"⚠️ MultiAgent SL/TP invalid: {validation_reason}, falling back to technical analysis")

            stop_loss_price, tp_price, calc_method = calculate_technical_sltp(
                side=side.name,  # Convert OrderSide.BUY → 'BUY'
                entry_price=entry_price,
                support=support,
                resistance=resistance,
                confidence=confidence,
                use_support_resistance=self.sl_use_support_resistance,
                sl_buffer_pct=self.sl_buffer_pct,
            )
            self.log.info(f"📍 Using technical analysis: {calc_method}")

        # Log SL/TP summary
        self.log.info(
            f"🎯 Creating bracket order for {side.name}:\n"
            f"   Entry: ~${entry_price:,.2f} (MARKET)\n"
            f"   Stop Loss: ${stop_loss_price:,.2f} ({((stop_loss_price/entry_price - 1) * 100):.2f}%)\n"
            f"   Take Profit: ${tp_price:,.2f} ({((tp_price/entry_price - 1) * 100):.2f}%)\n"
            f"   Quantity: {quantity:.3f}\n"
            f"   Confidence: {confidence}"
        )

        try:
            # Create bracket order using OrderFactory
            # This automatically creates entry + SL + TP with OTO/OCO linkage
            # IMPORTANT: Use emulation_trigger to enable order emulation for Binance compatibility
            # Binance doesn't support native OCO+OTO orders, so NautilusTrader will emulate them
            bracket_order_list = self.order_factory.bracket(
                instrument_id=self.instrument_id,
                order_side=side,
                quantity=self.instrument.make_qty(quantity),
                sl_trigger_price=self.instrument.make_price(stop_loss_price),
                tp_price=self.instrument.make_price(tp_price),
                time_in_force=TimeInForce.GTC,
                emulation_trigger=TriggerType.DEFAULT,  # Enable order emulation
            )

            # Submit the bracket order list
            self.submit_order_list(bracket_order_list)

            self.log.info(
                f"✅ Submitted bracket order: {side.name} {quantity:.3f} BTC with SL/TP\n"
                f"   OrderList ID: {bracket_order_list.id}"
            )

            # Save bracket order info for trailing stop
            if self.enable_trailing_stop:
                instrument_key = str(self.instrument_id)

                # Extract SL order from bracket (it's typically the second order in the list)
                sl_order = None
                for order in bracket_order_list.orders:
                    if order.order_type == OrderType.STOP_MARKET:
                        sl_order = order
                        break

                if sl_order:
                    self.trailing_stop_state[instrument_key] = {
                        "entry_price": entry_price,
                        "highest_price": entry_price if side == OrderSide.BUY else None,
                        "lowest_price": entry_price if side == OrderSide.SELL else None,
                        "current_sl_price": stop_loss_price,
                        "sl_order_id": str(sl_order.client_order_id),
                        "activated": False,
                        "side": "LONG" if side == OrderSide.BUY else "SHORT",
                        "quantity": quantity,
                    }
                    self.log.debug(
                        f"📌 Saved SL order ID for trailing stop: {str(sl_order.client_order_id)[:8]}..."
                    )

        except Exception as e:
            self.log.error(f"❌ Failed to submit bracket order: {e}")
            self.log.warning("⚠️ Falling back to simple market order without SL/TP")

            # Send Telegram alert for critical bracket order failure
            if self.telegram_bot and self.enable_telegram and self.telegram_notify_errors:
                try:
                    error_msg = self.telegram_bot.format_error_alert({
                        'type': 'BRACKET_ORDER_FAILURE',
                        'message': f"Bracket order failed, opening position WITHOUT SL/TP protection",
                        'details': f"Error: {str(e)}",
                        'action': f"Opening {side.name} {quantity:.3f} BTC with simple order"
                    })
                    self.telegram_bot.send_message_sync(error_msg)
                except Exception as notify_error:
                    self.log.error(f"Failed to send Telegram alert: {notify_error}")

            self._submit_order(side=side, quantity=quantity, reduce_only=False)

    def on_order_filled(self, event):
        """
        Handle order filled events.

        Note: OCO logic is now handled automatically by NautilusTrader's bracket orders.
        We no longer need to manually cancel peer orders.
        """
        filled_order_id = str(event.client_order_id)

        self.log.info(
            f"✅ Order filled: {event.order_side.name} "
            f"{event.last_qty} @ {event.last_px} "
            f"(ID: {filled_order_id[:8]}...)"
        )

        # Send Telegram order fill notification
        if self.telegram_bot and self.enable_telegram and self.telegram_notify_fills:
            try:
                fill_msg = self.telegram_bot.format_order_fill({
                    'side': event.order_side.name,
                    'quantity': float(event.last_qty),
                    'price': float(event.last_px),
                    'order_type': 'MARKET',  # Could extract from order if needed
                })
                self.telegram_bot.send_message_sync(fill_msg)
            except Exception as e:
                self.log.warning(f"Failed to send Telegram fill notification: {e}")
    

    def on_order_rejected(self, event):
        """
        Handle order rejected events.

        🚨 Fix G34: Send critical Telegram alert for order rejections.
        """
        reason = getattr(event, 'reason', 'Unknown reason')
        client_order_id = getattr(event, 'client_order_id', 'N/A')

        self.log.error(f"❌ Order rejected: {reason}")

        # 🚨 Fix G34: Force Telegram alert for order rejections
        if self.telegram_bot and self.enable_telegram:
            try:
                alert_msg = self.telegram_bot.format_error_alert({
                    'level': 'CRITICAL',
                    'message': f"Order Rejected: {reason}",
                    'context': f"Order ID: {client_order_id}",
                })
                self.telegram_bot.send_message_sync(alert_msg)
                self.log.info("📱 Telegram alert sent for order rejection")
            except Exception as e:
                self.log.warning(f"Failed to send Telegram alert for order rejection: {e}")

    def on_position_opened(self, event):
        """
        Handle position opened events.

        Note: With bracket orders, SL/TP orders are automatically submitted as part of the bracket.
        We no longer need to manually submit them here.
        """
        # PositionOpened event contains position data directly
        self.log.info(
            f"🟢 Position opened: {event.side.name} "
            f"{event.quantity} @ {event.avg_px_open}"
        )

        # Update trailing stop state with actual entry price if it exists
        # (bracket order already initialized it with estimated price)
        if self.enable_trailing_stop:
            instrument_key = str(self.instrument_id)
            entry_price = float(event.avg_px_open)

            if instrument_key in self.trailing_stop_state:
                # Update with actual entry price
                self.trailing_stop_state[instrument_key]["entry_price"] = entry_price
                if event.side == PositionSide.LONG:
                    self.trailing_stop_state[instrument_key]["highest_price"] = entry_price
                else:
                    self.trailing_stop_state[instrument_key]["lowest_price"] = entry_price

                self.log.debug(
                    f"📊 Updated trailing stop state with actual entry price: ${entry_price:,.2f}"
                )
            else:
                # Fallback: initialize if not already set (shouldn't happen with bracket orders)
                self.trailing_stop_state[instrument_key] = {
                    "entry_price": entry_price,
                    "highest_price": entry_price if event.side == PositionSide.LONG else None,
                    "lowest_price": entry_price if event.side == PositionSide.SHORT else None,
                    "current_sl_price": None,
                    "sl_order_id": None,
                    "activated": False,
                    "side": event.side.name,
                    "quantity": float(event.quantity),
                }
                self.log.info(
                    f"📊 Trailing stop initialized for {event.side.name} position @ ${entry_price:,.2f}"
                )

        # Send Telegram position opened notification
        if self.telegram_bot and self.enable_telegram and self.telegram_notify_positions:
            try:
                position_msg = self.telegram_bot.format_position_update({
                    'action': 'OPENED',
                    'side': event.side.name,
                    'quantity': float(event.quantity),
                    'entry_price': float(event.avg_px_open),
                    'current_price': float(event.avg_px_open),
                    'pnl': 0.0,
                    'pnl_pct': 0.0,
                })
                self.telegram_bot.send_message_sync(position_msg)
            except Exception as e:
                self.log.warning(f"Failed to send Telegram position opened notification: {e}")

    def on_position_closed(self, event):
        """Handle position closed events."""
        # PositionOpened event contains position data directly
        self.log.info(
            f"🔴 Position closed: {event.side.name} "
            f"P&L: {float(event.realized_pnl):.2f} USDT"
        )
        
        # Clear trailing stop state
        instrument_key = str(self.instrument_id)
        if instrument_key in self.trailing_stop_state:
            del self.trailing_stop_state[instrument_key]
            self.log.debug(f"🗑️ Cleared trailing stop state for {instrument_key}")
        
        # Send Telegram position closed notification
        if self.telegram_bot and self.enable_telegram and self.telegram_notify_positions:
            try:
                # Calculate P&L percentage
                pnl = float(event.realized_pnl)
                quantity = float(event.quantity) if hasattr(event, 'quantity') else 0.0
                entry_price = float(event.avg_px_open) if hasattr(event, 'avg_px_open') else 0.0
                exit_price = float(event.avg_px_close) if hasattr(event, 'avg_px_close') else 0.0

                # Calculate position value for percentage: PnL / (entry_price * quantity) * 100
                position_value = entry_price * quantity
                pnl_pct = (pnl / position_value * 100) if position_value > 0 else 0.0

                position_msg = self.telegram_bot.format_position_update({
                    'action': 'CLOSED',
                    'side': event.side.name,
                    'quantity': quantity,
                    'entry_price': entry_price,
                    'current_price': exit_price,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                })
                self.telegram_bot.send_message_sync(position_msg)
            except Exception as e:
                self.log.warning(f"Failed to send Telegram position closed notification: {e}")
    
    def _cleanup_oco_orphans(self):
        """
        Clean up orphan orders.

        This is a safety mechanism that runs periodically to:
        1. Cancel orphan reduce-only orders when no position exists

        Note: OCO group management is no longer needed as NautilusTrader handles it automatically.
        """
        try:
            # Get current positions
            positions = self.cache.positions_open(instrument_id=self.instrument_id)
            has_position = len(positions) > 0

            if not has_position:
                # No position but check for orphan orders
                open_orders = self.cache.orders_open(instrument_id=self.instrument_id)

                if open_orders:
                    orphan_count = 0
                    for order in open_orders:
                        if order.is_reduce_only:
                            # This is a reduce-only order without a position - orphan!
                            try:
                                self.cancel_order(order)
                                orphan_count += 1
                                self.log.info(
                                    f"🗑️ Cancelled orphan reduce-only order: "
                                    f"{str(order.client_order_id)[:8]}..."
                                )
                            except Exception as e:
                                self.log.error(
                                    f"Failed to cancel orphan order: {e}"
                                )

                    if orphan_count > 0:
                        self.log.warning(
                            f"⚠️ Cleaned up {orphan_count} orphan orders"
                        )

        except Exception as e:
            self.log.error(f"❌ Orphan order cleanup failed: {e}")
    
    def _update_trailing_stops(self, current_price: float):
        """
        Update trailing stop loss orders based on current price.
        
        Logic:
        1. Check if position is profitable enough to activate trailing stop
        2. Track highest price (LONG) or lowest price (SHORT)
        3. Update stop loss when price moves favorably beyond threshold
        4. Stop loss only moves in favorable direction, never backwards
        
        Parameters
        ----------
        current_price : float
            Current market price
        """
        try:
            instrument_key = str(self.instrument_id)
            
            # Check if we have trailing stop state for this instrument
            if instrument_key not in self.trailing_stop_state:
                return
            
            state = self.trailing_stop_state[instrument_key]
            entry_price = state["entry_price"]
            side = state["side"]
            activated = state["activated"]
            
            # Calculate profit percentage
            if side == "LONG":
                profit_pct = (current_price - entry_price) / entry_price
                
                # Update highest price
                if state["highest_price"] is None or current_price > state["highest_price"]:
                    state["highest_price"] = current_price
                
                highest_price = state["highest_price"]
                
                # Check if we should activate trailing stop
                if not activated and profit_pct >= self.trailing_activation_pct:
                    state["activated"] = True
                    self.log.info(
                        f"🎯 Trailing stop ACTIVATED for LONG @ ${current_price:,.2f} "
                        f"(Profit: {profit_pct*100:.2f}%)"
                    )
                    activated = True
                
                # If activated, check if we should update stop loss
                if activated:
                    # Calculate new stop loss based on highest price
                    new_sl_price = highest_price * (1 - self.trailing_distance_pct)
                    current_sl_price = state["current_sl_price"]
                    
                    # Only update if new SL is significantly higher than current
                    if current_sl_price is None:
                        should_update = True
                    else:
                        price_move_pct = (new_sl_price - current_sl_price) / current_sl_price
                        should_update = price_move_pct >= self.trailing_update_threshold_pct
                    
                    if should_update and (current_sl_price is None or new_sl_price > current_sl_price):
                        self._execute_trailing_stop_update(
                            instrument_key=instrument_key,
                            new_sl_price=new_sl_price,
                            current_price=current_price,
                            side="LONG"
                        )
            
            elif side == "SHORT":
                profit_pct = (entry_price - current_price) / entry_price
                
                # Update lowest price
                if state["lowest_price"] is None or current_price < state["lowest_price"]:
                    state["lowest_price"] = current_price
                
                lowest_price = state["lowest_price"]
                
                # Check if we should activate trailing stop
                if not activated and profit_pct >= self.trailing_activation_pct:
                    state["activated"] = True
                    self.log.info(
                        f"🎯 Trailing stop ACTIVATED for SHORT @ ${current_price:,.2f} "
                        f"(Profit: {profit_pct*100:.2f}%)"
                    )
                    activated = True
                
                # If activated, check if we should update stop loss
                if activated:
                    # Calculate new stop loss based on lowest price
                    new_sl_price = lowest_price * (1 + self.trailing_distance_pct)
                    current_sl_price = state["current_sl_price"]
                    
                    # Only update if new SL is significantly lower than current
                    if current_sl_price is None:
                        should_update = True
                    else:
                        price_move_pct = (current_sl_price - new_sl_price) / current_sl_price
                        should_update = price_move_pct >= self.trailing_update_threshold_pct
                    
                    if should_update and (current_sl_price is None or new_sl_price < current_sl_price):
                        self._execute_trailing_stop_update(
                            instrument_key=instrument_key,
                            new_sl_price=new_sl_price,
                            current_price=current_price,
                            side="SHORT"
                        )
                        
        except Exception as e:
            self.log.error(f"❌ Trailing stop update failed: {e}")
    
    def _execute_trailing_stop_update(
        self,
        instrument_key: str,
        new_sl_price: float,
        current_price: float,
        side: str
    ):
        """
        Execute the actual update of trailing stop loss order.
        
        Parameters
        ----------
        instrument_key : str
            Instrument identifier
        new_sl_price : float
            New stop loss price
        current_price : float
            Current market price
        side : str
            Position side (LONG/SHORT)
        """
        try:
            state = self.trailing_stop_state[instrument_key]
            old_sl_price = state["current_sl_price"]
            old_sl_order_id = state["sl_order_id"]
            quantity = state["quantity"]
            
            # Log the update
            if old_sl_price:
                move_pct = ((new_sl_price - old_sl_price) / old_sl_price) * 100
                self.log.info(
                    f"⬆️ Trailing Stop Update ({side}):\n"
                    f"   Current Price: ${current_price:,.2f}\n"
                    f"   Old SL: ${old_sl_price:,.2f}\n"
                    f"   New SL: ${new_sl_price:,.2f} ({move_pct:+.2f}%)\n"
                    f"   Distance: {abs((new_sl_price - current_price) / current_price * 100):.2f}%"
                )
            else:
                self.log.info(
                    f"📍 Initial Trailing Stop ({side}):\n"
                    f"   Current Price: ${current_price:,.2f}\n"
                    f"   SL Price: ${new_sl_price:,.2f}\n"
                    f"   Distance: {abs((new_sl_price - current_price) / current_price * 100):.2f}%"
                )
            
            # Cancel old stop loss order if it exists
            if old_sl_order_id:
                try:
                    from nautilus_trader.model.identifiers import ClientOrderId
                    old_order_id_obj = ClientOrderId(old_sl_order_id)
                    old_order = self.cache.order(old_order_id_obj)
                    
                    if old_order and old_order.is_open:
                        self.cancel_order(old_order)
                        self.log.debug(f"🔴 Cancelled old SL order: {old_sl_order_id[:8]}...")
                except Exception as e:
                    self.log.warning(f"⚠️ Failed to cancel old SL order: {e}")
            
            # Submit new stop loss order
            exit_side = OrderSide.SELL if side == "LONG" else OrderSide.BUY
            
            new_sl_order = self.order_factory.stop_market(
                instrument_id=self.instrument_id,
                order_side=exit_side,
                quantity=self.instrument.make_qty(quantity),
                trigger_price=self.instrument.make_price(new_sl_price),
                trigger_type=TriggerType.LAST_PRICE,
                reduce_only=True,
            )
            self.submit_order(new_sl_order)
            
            # Update state
            state["current_sl_price"] = new_sl_price
            state["sl_order_id"] = str(new_sl_order.client_order_id)

            self.log.info(f"✅ New trailing SL order submitted @ ${new_sl_price:,.2f}")

            # Note: OCO relationship is handled automatically by NautilusTrader
            # When the new SL is submitted, it will be linked to the existing TP orders

        except Exception as e:
            self.log.error(f"❌ Failed to execute trailing stop update: {e}")
    
    # ===== Remote Control Methods (for Telegram commands) =====
    
    def handle_telegram_command(self, command: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle Telegram commands.
        
        Parameters
        ----------
        command : str
            Command name (status, position, pause, resume)
        args : dict
            Command arguments
        
        Returns
        -------
        dict
            Response with 'success', 'message', and optional 'error'
        """
        try:
            if command == 'status':
                return self._cmd_status()
            elif command == 'position':
                return self._cmd_position()
            elif command == 'orders':
                return self._cmd_orders()
            elif command == 'history':
                return self._cmd_history()
            elif command == 'risk':
                return self._cmd_risk()
            elif command == 'pause':
                return self._cmd_pause()
            elif command == 'resume':
                return self._cmd_resume()
            elif command == 'close':
                return self._cmd_close()
            else:
                return {
                    'success': False,
                    'error': f"Unknown command: {command}"
                }
        except Exception as e:
            self.log.error(f"Error handling command '{command}': {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _cmd_status(self) -> Dict[str, Any]:
        """Handle /status command - shows REAL account balance."""
        try:
            from datetime import datetime

            # Get current price from thread-safe cache
            # IMPORTANT: Do NOT access indicator_manager here - it's called from
            # Telegram thread and Rust indicators (RSI) are not thread-safe
            with self._state_lock:
                current_price = self._cached_current_price

            # Fetch REAL balance from Binance
            real_balance = self.binance_account.get_balance()
            total_balance = real_balance.get('total_balance', 0)

            # Get unrealized PnL from real balance or calculate from position
            unrealized_pnl = real_balance.get('unrealized_pnl', 0)
            positions = self.cache.positions_open(instrument_id=self.instrument_id)
            if positions and current_price > 0:
                position = positions[0]
                # Use position-specific PnL if available
                position_pnl = float(position.unrealized_pnl(current_price))
                if position_pnl != 0:
                    unrealized_pnl = position_pnl

            # Calculate uptime
            uptime_str = "N/A"
            if self.strategy_start_time:
                uptime_delta = datetime.utcnow() - self.strategy_start_time
                hours = uptime_delta.total_seconds() // 3600
                minutes = (uptime_delta.total_seconds() % 3600) // 60
                uptime_str = f"{int(hours)}h {int(minutes)}m"

            # Get last signal
            last_signal = "N/A"
            last_signal_time = "N/A"
            if hasattr(self, 'last_signal') and self.last_signal:
                last_signal = f"{self.last_signal.get('signal', 'N/A')} ({self.last_signal.get('confidence', 'N/A')})"

            # Use real balance if available, otherwise fall back to configured equity
            display_equity = total_balance if total_balance > 0 else self.equity

            status_info = {
                'is_running': True,  # If this method is called, strategy is running
                'is_paused': self.is_trading_paused,
                'instrument_id': str(self.instrument_id),
                'current_price': current_price,
                'equity': display_equity,  # Now shows REAL balance
                'unrealized_pnl': unrealized_pnl,
                'last_signal': last_signal,
                'last_signal_time': last_signal_time,
                'uptime': uptime_str,
            }

            message = self.telegram_bot.format_status_response(status_info) if self.telegram_bot else "Status unavailable"
            
            return {
                'success': True,
                'message': message
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _cmd_position(self) -> Dict[str, Any]:
        """Handle /position command."""
        try:
            # Get current price from thread-safe cache FIRST
            # IMPORTANT: Do NOT access indicator_manager here - it's called from
            # Telegram thread and Rust indicators (RSI) are not thread-safe
            with self._state_lock:
                cached_price = self._cached_current_price

            # Get current position - from_telegram=True ensures we NEVER access indicator_manager
            current_position = self._get_current_position_data(current_price=cached_price, from_telegram=True)

            position_info = {
                'has_position': current_position is not None,
            }

            if current_position:
                # Use cached price, fallback to entry price
                current_price = cached_price if cached_price > 0 else current_position['avg_px']

                entry_price = current_position['avg_px']
                pnl = current_position['unrealized_pnl']
                pnl_pct = (pnl / (entry_price * current_position['quantity'])) * 100 if entry_price > 0 else 0

                position_info.update({
                    'side': current_position['side'].upper(),
                    'quantity': current_position['quantity'],
                    'entry_price': entry_price,
                    'current_price': current_price,
                    'unrealized_pnl': pnl,
                    'pnl_pct': pnl_pct,
                    # SL/TP prices would need to be tracked separately if needed
                })
            
            message = self.telegram_bot.format_position_response(position_info) if self.telegram_bot else "Position unavailable"
            
            return {
                'success': True,
                'message': message
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _cmd_pause(self) -> Dict[str, Any]:
        """Handle /pause command (thread-safe)."""
        try:
            with self._state_lock:
                if self.is_trading_paused:
                    message = self.telegram_bot.format_pause_response(False, "Trading is already paused") if self.telegram_bot else "Already paused"
                else:
                    self.is_trading_paused = True
                    self.log.info("⏸️ Trading paused by Telegram command")
                    message = self.telegram_bot.format_pause_response(True) if self.telegram_bot else "Trading paused"

            return {
                'success': True,
                'message': message
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _cmd_resume(self) -> Dict[str, Any]:
        """Handle /resume command (thread-safe)."""
        try:
            with self._state_lock:
                if not self.is_trading_paused:
                    message = self.telegram_bot.format_resume_response(False, "Trading is not paused") if self.telegram_bot else "Not paused"
                else:
                    self.is_trading_paused = False
                    self.log.info("▶️ Trading resumed by Telegram command")
                    message = self.telegram_bot.format_resume_response(True) if self.telegram_bot else "Trading resumed"

            return {
                'success': True,
                'message': message
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _cmd_close(self) -> Dict[str, Any]:
        """
        Handle /close command - close current position.

        Thread-safe: Does not access indicator_manager.
        """
        try:
            from nautilus_trader.model.enums import OrderSide

            # Get open positions
            positions = self.cache.positions_open(instrument_id=self.instrument_id)

            if not positions:
                return {
                    'success': True,
                    'message': "ℹ️ *No Open Position*\n\nThere is no position to close."
                }

            position = positions[0]
            quantity = float(position.quantity)

            # Determine closing side (opposite of position)
            if position.side.name == 'LONG':
                close_side = OrderSide.SELL
                side_str = "LONG"
            else:
                close_side = OrderSide.BUY
                side_str = "SHORT"

            # Submit close order
            self._submit_order(
                side=close_side,
                quantity=quantity,
                reduce_only=True,
            )

            self.log.info(f"🔴 Position closed by Telegram command: {side_str} {quantity:.4f} BTC")

            return {
                'success': True,
                'message': f"✅ *Position Closing*\n\n"
                          f"Closing {side_str} position\n"
                          f"Quantity: {quantity:.4f} BTC\n\n"
                          f"⏳ Order submitted, waiting for fill..."
            }
        except Exception as e:
            self.log.error(f"Error closing position: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _cmd_orders(self) -> Dict[str, Any]:
        """
        Handle /orders command - view open orders.

        Thread-safe: Does not access indicator_manager.
        """
        try:
            # Get open orders
            orders = self.cache.orders_open(instrument_id=self.instrument_id)

            if not orders:
                return {
                    'success': True,
                    'message': "ℹ️ *No Open Orders*\n\nThere are no pending orders."
                }

            msg = f"📋 *Open Orders* ({len(orders)})\n\n"

            for i, order in enumerate(orders, 1):
                order_type = order.order_type.name
                side = order.side.name
                qty = float(order.quantity)

                # Get price for limit/stop orders
                price_str = ""
                if hasattr(order, 'price') and order.price:
                    price_str = f"@ ${float(order.price):,.2f}"
                elif hasattr(order, 'trigger_price') and order.trigger_price:
                    price_str = f"trigger @ ${float(order.trigger_price):,.2f}"

                # Order status
                status = order.status.name
                reduce_only = "🔻" if order.is_reduce_only else ""

                msg += f"{i}. {side} {order_type} {reduce_only}\n"
                msg += f"   Qty: {qty:.4f} BTC {price_str}\n"
                msg += f"   Status: {status}\n\n"

            return {
                'success': True,
                'message': msg
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _cmd_history(self) -> Dict[str, Any]:
        """
        Handle /history command - view recent trade history.

        Thread-safe: Does not access indicator_manager.
        """
        try:
            # Get recent fills (last 10)
            fills = list(self.cache.order_fills())[-10:]

            if not fills:
                return {
                    'success': True,
                    'message': "ℹ️ *No Trade History*\n\nNo trades have been executed yet."
                }

            msg = f"📊 *Recent Trades* (last {len(fills)})\n\n"

            for fill in reversed(fills):  # Most recent first
                side = fill.order_side.name
                side_emoji = "🟢" if side == "BUY" else "🔴"
                qty = float(fill.last_qty)
                price = float(fill.last_px)
                ts = fill.ts_event

                # Format timestamp with defensive handling
                from datetime import datetime
                try:
                    dt = datetime.utcfromtimestamp(ts / 1e9) if ts else datetime.utcnow()
                    time_str = dt.strftime("%m-%d %H:%M")
                except (ValueError, TypeError, OSError):
                    time_str = "N/A"

                msg += f"{side_emoji} {side} {qty:.4f} @ ${price:,.2f}\n"
                msg += f"   Time: {time_str} UTC\n\n"

            return {
                'success': True,
                'message': msg
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _cmd_risk(self) -> Dict[str, Any]:
        """
        Handle /risk command - view risk metrics.

        Thread-safe: Does not access indicator_manager.
        Shows REAL account balance from Binance API.
        """
        try:
            with self._state_lock:
                cached_price = self._cached_current_price

            # Fetch REAL balance from Binance (with cache)
            real_balance = self.binance_account.get_balance()
            total_balance = real_balance.get('total_balance', 0)
            available_balance = real_balance.get('available_balance', 0)
            unrealized_pnl_total = real_balance.get('unrealized_pnl', 0)

            # Get position info from NautilusTrader cache
            positions = self.cache.positions_open(instrument_id=self.instrument_id)

            msg = "📊 *Risk Metrics*\n\n"

            # Real Account Balance from Binance
            msg += "*Account (Real-time)*:\n"
            if total_balance > 0:
                msg += f"• Balance: ${total_balance:,.2f} USDT\n"
                msg += f"• Available: ${available_balance:,.2f} USDT\n"
                if unrealized_pnl_total != 0:
                    pnl_emoji = "📈" if unrealized_pnl_total >= 0 else "📉"
                    msg += f"• Unrealized P&L: {pnl_emoji} ${unrealized_pnl_total:,.2f}\n"
            else:
                msg += f"• Balance: ⚠️ Unable to fetch (configured: ${self.equity:,.2f})\n"
            msg += f"• Leverage: {self.leverage}x\n"
            msg += f"• Max Position: {self.position_config.get('max_position_ratio', 0.3)*100:.0f}%\n\n"

            # Use real balance for calculations if available, otherwise fall back to configured equity
            effective_equity = total_balance if total_balance > 0 else self.equity

            # Position risk
            if positions:
                position = positions[0]
                qty = float(position.quantity)
                entry_price = float(position.avg_px_open)
                side = position.side.name

                # Calculate position value
                position_value = qty * cached_price if cached_price > 0 else qty * entry_price

                # Calculate unrealized PnL
                if cached_price > 0:
                    if side == 'LONG':
                        pnl = (cached_price - entry_price) * qty
                        pnl_pct = ((cached_price / entry_price) - 1) * 100
                    else:
                        pnl = (entry_price - cached_price) * qty
                        pnl_pct = ((entry_price / cached_price) - 1) * 100
                else:
                    pnl = 0
                    pnl_pct = 0

                pnl_emoji = "📈" if pnl >= 0 else "📉"

                msg += "*Current Position*:\n"
                msg += f"• Side: {side}\n"
                msg += f"• Size: {qty:.4f} BTC (${position_value:,.2f})\n"
                msg += f"• Entry: ${entry_price:,.2f}\n"
                msg += f"• Current: ${cached_price:,.2f}\n"
                msg += f"• P&L: {pnl_emoji} ${pnl:,.2f} ({pnl_pct:+.2f}%)\n\n"

                # Risk exposure using real balance
                exposure_pct = (position_value / effective_equity) * 100 if effective_equity > 0 else 0
                msg += "*Risk Exposure*:\n"
                msg += f"• Position/Balance: {exposure_pct:.1f}%\n"
                msg += f"• Leveraged Exposure: {exposure_pct * self.leverage:.1f}%\n"
            else:
                msg += "*Current Position*: None\n"
                msg += "*Risk Exposure*: 0%\n"

            # Strategy settings
            msg += f"\n*Strategy Settings*:\n"
            msg += f"• Min Confidence: {self.min_confidence}\n"
            msg += f"• Auto SL/TP: {'✅' if self.enable_auto_sl_tp else '❌'}\n"
            msg += f"• Trailing Stop: {'✅' if self.enable_trailing_stop else '❌'}\n"
            msg += f"• Trading Paused: {'⏸️ Yes' if self.is_trading_paused else '▶️ No'}\n"

            return {
                'success': True,
                'message': msg
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
