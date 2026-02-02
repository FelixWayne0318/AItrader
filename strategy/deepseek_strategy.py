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
from utils.binance_orderbook_client import BinanceOrderBookClient
from utils.orderbook_processor import OrderBookProcessor
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

    # v4.8: Position sizing method configuration
    position_sizing_method: str = "ai_controlled"  # fixed_pct | atr_based | ai_controlled | hybrid_atr_ai
    position_sizing_default_pct: float = 50.0  # AI 未提供时的默认百分比
    position_sizing_high_pct: float = 80.0     # HIGH 信心仓位百分比
    position_sizing_medium_pct: float = 50.0   # MEDIUM 信心仓位百分比
    position_sizing_low_pct: float = 30.0      # LOW 信心仓位百分比
    position_sizing_cumulative: bool = True    # 累加模式：允许多次加仓 (v4.8)

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
    telegram_notify_trailing_stop: bool = True  # v3.13: 移动止损更新通知
    telegram_notify_startup: bool = True  # v3.13: 策略启动通知
    telegram_notify_shutdown: bool = True  # v3.13: 策略关闭通知
    telegram_auto_daily: bool = False  # v3.13: 自动发送每日总结
    telegram_auto_weekly: bool = False  # v3.13: 自动发送每周总结
    telegram_daily_hour_utc: int = 0  # v3.13: 每日总结发送时间 (UTC 小时)
    telegram_weekly_day: int = 0  # v3.13: 每周总结发送日 (0=周一)

    # Telegram Queue (v4.0 - Non-blocking message sending)
    telegram_queue_enabled: bool = True  # 启用消息队列 (默认开启)
    telegram_queue_db_path: str = "data/telegram_queue.db"  # SQLite 持久化路径
    telegram_queue_max_retries: int = 3  # 最大重试次数
    telegram_queue_alert_cooldown: int = 300  # 告警收敛冷却时间 (秒)
    telegram_queue_send_interval: float = 0.5  # 发送间隔 (秒)

    # Telegram Security (v4.0 - Enhanced authentication)
    telegram_security_enable_pin: bool = True  # 启用 PIN 码验证
    telegram_security_pin_code: str = ""  # PIN 码 (空则自动生成)
    telegram_security_pin_expiry_seconds: int = 60  # PIN 过期时间 (秒)
    telegram_security_rate_limit_per_minute: int = 30  # 每分钟速率限制
    telegram_security_enable_audit: bool = True  # 启用审计日志
    telegram_security_audit_log_dir: str = "logs/audit"  # 审计日志目录

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

    # Multi-Timeframe Configuration (v3.3)
    multi_timeframe_enabled: bool = False  # Default disabled for backward compatibility
    mtf_trend_sma_period: int = 200        # SMA period for trend layer (1D)
    mtf_decision_debate_rounds: int = 2    # Debate rounds for decision layer (4H)

    # Order Book Configuration (v3.7)
    order_book_enabled: bool = False  # 启用订单簿深度数据 (默认关闭)
    order_book_api_timeout: float = 10.0  # API 超时 (秒)
    order_book_api_max_retries: int = 2  # 最大重试次数
    order_book_api_retry_delay: float = 1.0  # 重试延迟 (秒)
    order_book_price_band_pct: float = 0.5  # 价格带百分比 (深度分布)
    order_book_anomaly_threshold: float = 3.0  # 异常检测阈值 (倍数)
    order_book_slippage_amounts: Tuple[float, ...] = (0.1, 0.5, 1.0)  # 滑点估算数量 (BTC)
    order_book_weighted_decay: float = 0.8  # 加权 OBI 衰减因子
    order_book_adaptive_decay: bool = True  # 启用自适应衰减 (基于波动率)
    order_book_history_size: int = 10  # 历史缓存大小 (用于计算变化率)


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

        # v4.8: Position sizing configuration
        self.position_sizing_config = {
            'method': config.position_sizing_method,
            'ai_controlled': {
                'default_size_pct': config.position_sizing_default_pct,
                'confidence_mapping': {
                    'HIGH': config.position_sizing_high_pct,
                    'MEDIUM': config.position_sizing_medium_pct,
                    'LOW': config.position_sizing_low_pct,
                }
            }
        }
        self.position_sizing_cumulative = config.position_sizing_cumulative

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

        # v3.6/3.7/3.8: Store latest indicator data for Telegram heartbeat
        self.latest_order_flow_data: Optional[Dict[str, Any]] = None
        self.latest_derivatives_data: Optional[Dict[str, Any]] = None
        self.latest_orderbook_data: Optional[Dict[str, Any]] = None
        self.latest_sr_zones_data: Optional[Dict[str, Any]] = None

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
        # Throttle trailing stop notifications (5 minutes = 300 seconds)
        self._last_trailing_stop_notify_time: float = 0.0
        self._trailing_stop_notify_throttle: float = 300.0  # seconds

        # v4.0: Store pending execution data for unified Telegram notification
        # This allows on_position_opened to send a comprehensive message with signal + fill + position
        self._pending_execution_data: Optional[Dict[str, Any]] = None

        # v4.1: Track signal execution status for heartbeat display
        # Shows whether the signal was actually executed and why not if blocked
        self._last_signal_status: Dict[str, Any] = {
            'executed': False,       # Whether trade was executed
            'reason': '',            # Reason if not executed
            'action_taken': '',      # What action was taken (if any)
        }
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

        self._mtf_trend_initialized = False
        self._mtf_decision_initialized = False
        self._mtf_execution_initialized = False

        if self.mtf_enabled:
            try:
                from indicators.multi_timeframe_manager import MultiTimeframeManager

                # Build BarType objects for each layer
                instrument_str = str(self.instrument_id)
                self.trend_bar_type = BarType.from_str(f"{instrument_str}-1-DAY-LAST-EXTERNAL")
                self.decision_bar_type = BarType.from_str(f"{instrument_str}-4-HOUR-LAST-EXTERNAL")
                self.execution_bar_type = BarType.from_str(f"{instrument_str}-15-MINUTE-LAST-EXTERNAL")

                # Build MTF config from strategy config (v3.3: removed unused filter configs)
                mtf_config = {
                    'enabled': True,
                    'trend_layer': {
                        'timeframe': '1d',
                        'sma_period': getattr(config, 'mtf_trend_sma_period', 200),
                    },
                    'decision_layer': {
                        'timeframe': '4h',
                        'debate_rounds': getattr(config, 'mtf_decision_debate_rounds', 2),
                    },
                    'execution_layer': {
                        'timeframe': '15m',
                    }
                }

                self.mtf_manager = MultiTimeframeManager(
                    config=mtf_config,
                    trend_bar_type=self.trend_bar_type,
                    decision_bar_type=self.decision_bar_type,
                    execution_bar_type=self.execution_bar_type,
                    logger=self.log,
                )
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
                        message_timeout=config.network_telegram_message_timeout,
                        # v4.0 Queue configuration (non-blocking message sending)
                        use_queue=config.telegram_queue_enabled,
                        queue_db_path=config.telegram_queue_db_path,
                        queue_max_retries=config.telegram_queue_max_retries,
                        queue_alert_cooldown=config.telegram_queue_alert_cooldown,
                        queue_send_interval=config.telegram_queue_send_interval,
                    )
                    # Store notification preferences
                    self.telegram_notify_signals = config.telegram_notify_signals
                    self.telegram_notify_fills = config.telegram_notify_fills
                    self.telegram_notify_positions = config.telegram_notify_positions
                    self.telegram_notify_errors = config.telegram_notify_errors
                    self.telegram_notify_heartbeat = config.telegram_notify_heartbeat  # v2.1
                    # v3.13: 新增通知开关
                    self.telegram_notify_trailing_stop = config.telegram_notify_trailing_stop
                    self.telegram_notify_startup = config.telegram_notify_startup
                    self.telegram_notify_shutdown = config.telegram_notify_shutdown
                    # v3.13: 自动总结配置
                    self.telegram_auto_daily = config.telegram_auto_daily
                    self.telegram_auto_weekly = config.telegram_auto_weekly
                    self.telegram_daily_hour_utc = config.telegram_daily_hour_utc
                    self.telegram_weekly_day = config.telegram_weekly_day
                    # v3.13: 日期跟踪 (避免重复发送)
                    self._last_daily_summary_date = None
                    self._last_weekly_summary_date = None

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
                            # v4.0 Security configuration (PIN verification + audit logging)
                            enable_pin=config.telegram_security_enable_pin,
                            pin_code=config.telegram_security_pin_code or None,
                            pin_expiry_seconds=config.telegram_security_pin_expiry_seconds,
                            rate_limit_per_minute=config.telegram_security_rate_limit_per_minute,
                            enable_audit=config.telegram_security_enable_audit,
                            audit_log_dir=config.telegram_security_audit_log_dir,
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

            # ========== Order Book Depth (v3.7) ==========
            # 订单簿深度数据 (提供流动性、不平衡、滑点等指标)
            order_book_enabled = config.order_book_enabled if hasattr(config, 'order_book_enabled') else False
            if order_book_enabled:
                # Binance 订单簿客户端
                self.binance_orderbook_client = BinanceOrderBookClient(
                    timeout=config.order_book_api_timeout if hasattr(config, 'order_book_api_timeout') else 10,
                    max_retries=config.order_book_api_max_retries if hasattr(config, 'order_book_api_max_retries') else 2,
                    retry_delay=config.order_book_api_retry_delay if hasattr(config, 'order_book_api_retry_delay') else 1.0,
                    logger=self.log,
                )

                # 订单簿处理器 (计算 OBI、滑点、异常等)
                self.orderbook_processor = OrderBookProcessor(
                    price_band_pct=config.order_book_price_band_pct if hasattr(config, 'order_book_price_band_pct') else 0.5,
                    base_anomaly_threshold=config.order_book_anomaly_threshold if hasattr(config, 'order_book_anomaly_threshold') else 3.0,
                    slippage_amounts=config.order_book_slippage_amounts if hasattr(config, 'order_book_slippage_amounts') else [0.1, 0.5, 1.0],
                    weighted_obi_config={
                        'base_decay': config.order_book_weighted_decay if hasattr(config, 'order_book_weighted_decay') else 0.8,
                        'adaptive': config.order_book_adaptive_decay if hasattr(config, 'order_book_adaptive_decay') else True,
                    },
                    history_size=config.order_book_history_size if hasattr(config, 'order_book_history_size') else 10,
                    logger=self.log,
                )
                self.log.info("✅ Order Book clients initialized")
            else:
                self.binance_orderbook_client = None
                self.orderbook_processor = None
                self.log.info("Order Book disabled by config")

            self.log.info("✅ Order Flow & Derivatives clients initialized")
        else:
            self.binance_kline_client = None
            self.order_flow_processor = None
            self.coinalyze_client = None
            self.binance_orderbook_client = None
            self.orderbook_processor = None
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
        # v3.13: Added notify_startup switch
        if (self.telegram_bot and self.enable_telegram and
            getattr(self, 'telegram_notify_startup', True)):
            try:
                # v4.0: Extract timeframe from bar_type for display
                bar_type_str = str(self.bar_type)
                if '15-MINUTE' in bar_type_str:
                    timeframe = '15m'
                elif '5-MINUTE' in bar_type_str:
                    timeframe = '5m'
                elif '1-MINUTE' in bar_type_str:
                    timeframe = '1m'
                elif '30-MINUTE' in bar_type_str:
                    timeframe = '30m'
                elif '1-HOUR' in bar_type_str:
                    timeframe = '1h'
                elif '4-HOUR' in bar_type_str:
                    timeframe = '4h'
                elif '1-DAY' in bar_type_str:
                    timeframe = '1d'
                else:
                    timeframe = '15m'  # Default

                startup_msg = self.telegram_bot.format_startup_message(
                    instrument_id=str(self.instrument_id),
                    config={
                        'timeframe': timeframe,
                        'enable_auto_sl_tp': self.enable_auto_sl_tp,
                        'enable_oco': self.enable_oco,
                        'enable_trailing_stop': self.enable_trailing_stop,
                        'mtf_enabled': getattr(self, 'mtf_enabled', False),
                        'sr_hard_control_enabled': True,  # Always enabled in current version
                    }
                )
                self.telegram_bot.send_message_sync(startup_msg)
                # Note: Help message removed - users can use /help command if needed

            except Exception as e:
                self.log.warning(f"Failed to send Telegram startup notification: {e}")

    def on_stop(self):
        """Actions to be performed on strategy stop."""
        self.log.info("Stopping DeepSeek AI Strategy...")

        # v3.13: Send shutdown notification
        if (self.telegram_bot and self.enable_telegram and
            getattr(self, 'telegram_notify_shutdown', True)):
            try:
                # Calculate uptime
                uptime_str = "N/A"
                if self.strategy_start_time:
                    uptime_delta = datetime.utcnow() - self.strategy_start_time
                    hours = int(uptime_delta.total_seconds() // 3600)
                    minutes = int((uptime_delta.total_seconds() % 3600) // 60)
                    uptime_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

                shutdown_msg = self.telegram_bot.format_shutdown_message({
                    'instrument_id': str(self.instrument_id),
                    'reason': 'normal',
                    'uptime': uptime_str,
                })
                # Use direct send (not queue) to ensure message is sent before shutdown
                self.telegram_bot.send_message_sync(shutdown_msg, use_queue=False)
                self.log.info("📱 Sent shutdown notification to Telegram")
            except Exception as e:
                self.log.warning(f"Failed to send shutdown notification: {e}")

        # Stop Telegram message queue if running
        if self.telegram_bot:
            try:
                self.telegram_bot.stop_queue()
            except Exception as e:
                self.log.warning(f"Error stopping Telegram queue: {e}")

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
                # 决策层 (4H) 数据由 AI 在 on_timer 中使用，这里只记录
                self.log.debug(f"[MTF] 4H bar 收盘，数据已更新 (AI 将在 on_timer 中使用)")
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

            # v3.13: 检查是否需要发送定时总结 (每日/每周)
            self._check_scheduled_summaries()

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

            # Build price data for AI (v3.6: 添加周期统计数据)
            period_stats = self._calculate_period_statistics()
            price_data = {
                'price': current_price,
                'timestamp': self.clock.utc_now().isoformat(),
                'high': float(current_bar.high),
                'low': float(current_bar.low),
                'volume': float(current_bar.volume),
                'price_change': self._calculate_price_change(),
                'kline_data': kline_data,
                # v3.6: 周期统计 (基于可用 K 线历史)
                'period_high': period_stats['period_high'],
                'period_low': period_stats['period_low'],
                'period_change_pct': period_stats['period_change_pct'],
                'period_hours': period_stats['period_hours'],
            }

            # Get current position
            current_position = self._get_current_position_data()

            # Get account context for position sizing decisions (v4.6)
            account_context = self._get_account_context(current_price)

            # Log current state
            self.log.info(f"Current Price: ${current_price:,.2f}")
            self.log.info(f"Overall Trend: {technical_data.get('overall_trend', 'N/A')}")
            self.log.info(f"RSI: {technical_data.get('rsi', 0):.2f}")
            if current_position:
                self.log.info(
                    f"Current Position: {current_position['side']} "
                    f"{current_position['quantity']} @ ${current_position['avg_px']:.2f}"
                )
                # v4.7: Log critical risk fields
                liq_buffer = current_position.get('liquidation_buffer_pct')
                if liq_buffer is not None:
                    risk_level = "HIGH" if liq_buffer < 10 else "MEDIUM" if liq_buffer < 15 else "OK"
                    self.log.info(f"Liquidation Buffer: {liq_buffer:.1f}% ({risk_level})")
                funding_rate = current_position.get('funding_rate_current')
                if funding_rate is not None:
                    daily_cost = current_position.get('daily_funding_cost_usd', 0)
                    self.log.info(f"Funding Rate: {funding_rate*100:.4f}%/8h (Daily Est: ${daily_cost:.2f})")

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
                # v3.6: 添加价格统计数据 (周期高/低/变化)
                ai_technical_data['price_change'] = price_data.get('price_change', 0)
                ai_technical_data['period_high'] = price_data.get('period_high', 0)
                ai_technical_data['period_low'] = price_data.get('period_low', 0)
                ai_technical_data['period_change_pct'] = price_data.get('period_change_pct', 0)
                ai_technical_data['period_hours'] = price_data.get('period_hours', 0)
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
                        'bb_position': decision_layer_data.get('bb_position', 50),  # v3.5: 支撑/阻力距离
                        # 'overall_trend' 已移除 - AI 使用 INDICATOR_DEFINITIONS 自己判断
                    }
                    self.log.info(f"[MTF] AI 分析使用 4H 决策层数据: RSI={ai_technical_data['mtf_decision_layer']['rsi']:.1f}")

                # ========== 获取 1D 趋势层数据 (MTF v3.5) ==========
                trend_layer_data = None
                if self.mtf_enabled and self.mtf_manager:
                    try:
                        trend_layer_data = self.mtf_manager.get_technical_data_for_layer("trend", current_price)
                        if trend_layer_data and trend_layer_data.get('_initialized', True):
                            ai_technical_data['mtf_trend_layer'] = {
                                'timeframe': '1D',
                                'sma_200': trend_layer_data.get('sma_200', 0),
                                'macd': trend_layer_data.get('macd', 0),
                                'macd_signal': trend_layer_data.get('macd_signal', 0),
                            }
                            self.log.info(f"[MTF] AI 分析使用 1D 趋势层数据: SMA_200=${ai_technical_data['mtf_trend_layer']['sma_200']:,.2f}")
                    except Exception as e:
                        self.log.warning(f"[MTF] 获取趋势层数据失败: {e}")

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
                            self.latest_order_flow_data = order_flow_data  # v3.6: Store for heartbeat
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
                        self.latest_derivatives_data = derivatives_data  # v3.6: Store for heartbeat
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

                # ========== 获取订单簿深度数据 (v3.7) ==========
                orderbook_data = None
                if self.binance_orderbook_client and self.orderbook_processor:
                    try:
                        # 获取订单簿数据
                        raw_orderbook = self.binance_orderbook_client.get_order_book(
                            symbol="BTCUSDT",
                            limit=100,
                        )
                        if raw_orderbook:
                            # 处理订单簿数据 (计算 OBI、滑点、异常等)
                            orderbook_data = self.orderbook_processor.process(
                                order_book=raw_orderbook,
                                current_price=current_price,
                                volatility=technical_data.get('bb_bandwidth', 0.02),  # 使用 BB 带宽作为波动率代理
                            )
                            # 提取关键指标用于日志 (v3.7.1: 修正字段路径)
                            if orderbook_data.get('_status', {}).get('code') == 'OK':
                                self.latest_orderbook_data = orderbook_data  # v3.7: Store for heartbeat
                                obi = orderbook_data.get('obi', {})
                                simple_obi = obi.get('simple', 0)
                                weighted_obi = obi.get('weighted', 0)
                                spread_pct = orderbook_data.get('liquidity', {}).get('spread_pct', 0)
                                self.log.info(
                                    f"📖 Order Book: OBI={simple_obi:+.2f} (weighted={weighted_obi:+.2f}), "
                                    f"spread={spread_pct:.4f}%"
                                )
                            else:
                                status_msg = orderbook_data.get('_status', {}).get('message', 'Unknown error')
                                self.log.warning(f"⚠️ Order Book: {status_msg}")
                        else:
                            self.log.warning("⚠️ Failed to get order book data")
                    except Exception as e:
                        self.log.warning(f"⚠️ Order book processing failed: {e}")

                signal_data = self.multi_agent.analyze(
                    symbol="BTCUSDT",
                    technical_report=ai_technical_data,
                    sentiment_report=sentiment_data,
                    current_position=current_position,
                    price_data=price_data,
                    # ========== MTF v2.1 新增参数 ==========
                    order_flow_report=order_flow_data,
                    derivatives_report=derivatives_data,
                    # ========== v3.7 新增参数 ==========
                    orderbook_report=orderbook_data,
                    # ========== v4.6 新增参数 ==========
                    account_context=account_context,
                )

                # v3.8: Store S/R Zone data for heartbeat (from MultiAgentAnalyzer cache)
                if hasattr(self.multi_agent, '_sr_zones_cache') and self.multi_agent._sr_zones_cache:
                    self.latest_sr_zones_data = self.multi_agent._sr_zones_cache

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
                    # v3.10: Support both rationale (new) and key_reasons (legacy)
                    rationale = judge_decision.get('rationale', '')
                    strategic_actions = judge_decision.get('strategic_actions', [])
                    self.log.info(f"⚖️ Winning Side: {winning_side}")
                    if rationale:
                        self.log.info(f"📌 Rationale: {rationale}")
                    if strategic_actions:
                        self.log.info(f"🎯 Actions: {', '.join(strategic_actions[:2])}")

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
                self._save_decision_snapshot(
                    signal_data=signal_data,
                    technical_data=technical_data,
                    sentiment_data=sentiment_data,
                    order_flow_data=order_flow_data if 'order_flow_data' in locals() else None,
                    derivatives_data=derivatives_data if 'derivatives_data' in locals() else None,
                    current_position=current_position,
                    price_data=price_data,
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
    ):
        """
        🔍 Fix C16/J43: Save complete decision snapshot for debugging and replay.

        Saves all inputs and AI outputs to a JSON file.
        This enables full replay of "why did the system make this decision?"

        Note: All trading decisions are made by AI (Bull/Bear/Judge).
        Local code only handles risk control (S/R proximity blocking).
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
            }

            with open(snapshot_file, 'w') as f:
                json.dump(snapshot, f, indent=2, default=str)

            self.log.debug(f"📸 Decision snapshot saved: {snapshot_file}")

            # 📡 Write latest_signal.json for web frontend API
            # This file is read by /api/public/latest-signal endpoint
            latest_signal_file = 'logs/latest_signal.json'
            latest_signal = {
                'signal': signal_data.get('signal', 'HOLD'),
                'confidence': signal_data.get('confidence', 'MEDIUM'),
                'reason': signal_data.get('reason', ''),
                'symbol': 'BTCUSDT',
                'timestamp': datetime.now().isoformat(),
                'risk_level': signal_data.get('risk_level', 'MEDIUM'),
                'stop_loss': signal_data.get('stop_loss'),
                'take_profit': signal_data.get('take_profit'),
                'debate_summary': signal_data.get('debate_summary', ''),
            }
            with open(latest_signal_file, 'w') as f:
                json.dump(latest_signal, f, indent=2, default=str)
            self.log.debug(f"📡 Latest signal updated: {latest_signal_file}")

            # 📊 Write latest_analysis.json for AI analysis page (Bull/Bear/Judge)
            # This file is read by /api/public/ai-analysis endpoint
            latest_analysis_file = 'logs/latest_analysis.json'

            # Extract Bull/Bear arguments from debate transcript
            debate_transcript = getattr(self.multi_agent, 'last_debate_transcript', '') if self.multi_agent else ''
            bull_analysis = ''
            bear_analysis = ''
            if debate_transcript:
                # Parse transcript to extract bull/bear sections
                import re
                bull_matches = re.findall(r'BULL ANALYST:\n(.*?)(?=\n\nBEAR ANALYST:|$)', debate_transcript, re.DOTALL)
                bear_matches = re.findall(r'BEAR ANALYST:\n(.*?)(?=\n\n=== ROUND|$)', debate_transcript, re.DOTALL)
                if bull_matches:
                    bull_analysis = bull_matches[-1].strip()  # Get last round's argument
                if bear_matches:
                    bear_analysis = bear_matches[-1].strip()

            # Get judge decision details (v3.10: support rationale + legacy key_reasons)
            judge_decision = signal_data.get('judge_decision', {})
            if isinstance(judge_decision, dict):
                # Prefer rationale (v3.10), fallback to key_reasons (legacy)
                judge_reasoning = judge_decision.get('rationale', '')
                if not judge_reasoning:
                    judge_reasons = judge_decision.get('key_reasons', [])
                    judge_reasoning = '. '.join(judge_reasons) if judge_reasons else ''
            else:
                judge_reasoning = ''
            judge_reasoning = judge_reasoning or signal_data.get('reason', '')

            # Calculate confidence score (HIGH=80, MEDIUM=60, LOW=40)
            confidence_map = {'HIGH': 80, 'MEDIUM': 60, 'LOW': 40}
            confidence_score = confidence_map.get(signal_data.get('confidence', 'MEDIUM'), 60)

            # Get current price for entry
            current_price = price_data.get('price') if price_data else None

            latest_analysis = {
                'signal': signal_data.get('signal', 'HOLD'),
                'confidence': signal_data.get('confidence', 'MEDIUM'),
                'confidence_score': confidence_score,
                'bull_analysis': bull_analysis or 'No bull analysis available',
                'bear_analysis': bear_analysis or 'No bear analysis available',
                'judge_reasoning': judge_reasoning or 'No judge reasoning available',
                'entry_price': current_price,
                'stop_loss': signal_data.get('stop_loss'),
                'take_profit': signal_data.get('take_profit'),
                'technical_score': technical_data.get('rsi', 50) if technical_data else 50,  # Use RSI as proxy
                'sentiment_score': sentiment_data.get('net_sentiment', 50) if sentiment_data else 50,
                'timestamp': datetime.now().isoformat(),
            }
            with open(latest_analysis_file, 'w') as f:
                json.dump(latest_analysis, f, indent=2, default=str)
            self.log.debug(f"📊 Latest analysis updated: {latest_analysis_file}")

            # 📜 Update signal_history.json (append mode, keep last 100 signals)
            # This file is read by /api/public/signal-history endpoint
            signal_history_file = 'logs/signal_history.json'
            signal_entry = {
                'signal': signal_data.get('signal', 'HOLD'),
                'confidence': signal_data.get('confidence', 'MEDIUM'),
                'reason': signal_data.get('reason', ''),
                'timestamp': datetime.now().isoformat(),
                'result': None,  # Will be updated later when trade completes
                'stop_loss': signal_data.get('stop_loss'),
                'take_profit': signal_data.get('take_profit'),
            }

            # Load existing history or create new
            try:
                if os.path.exists(signal_history_file):
                    with open(signal_history_file, 'r') as f:
                        history_data = json.load(f)
                        signals = history_data.get('signals', []) if isinstance(history_data, dict) else history_data
                else:
                    signals = []
            except Exception:
                signals = []

            # Prepend new signal and keep last 100
            signals.insert(0, signal_entry)
            signals = signals[:100]

            with open(signal_history_file, 'w') as f:
                json.dump({'signals': signals}, f, indent=2, default=str)
            self.log.debug(f"📜 Signal history updated: {signal_history_file} ({len(signals)} signals)")

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

            # 3. 获取账户余额
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

            # 6. 获取持仓信息 (v4.2: 修复字段名 + 添加 SL/TP)
            position_side = None
            entry_price = 0
            position_size = 0
            position_pnl_pct = 0
            sl_price = None
            tp_price = None
            try:
                pos_data = self._get_current_position_data(current_price=cached_price, from_telegram=True)
                # Fix: _get_current_position_data returns 'quantity' not 'size', 'avg_px' not 'entry_price'
                if pos_data and pos_data.get('quantity', 0) != 0:
                    # Fix: side is lowercase ('long'/'short'), convert to uppercase for display
                    raw_side = pos_data.get('side', '')
                    position_side = raw_side.upper() if raw_side else None
                    entry_price = pos_data.get('avg_px') or 0
                    position_size = abs(pos_data.get('quantity') or 0)
                    if entry_price > 0 and cached_price:
                        if position_side == 'LONG':
                            position_pnl_pct = ((cached_price - entry_price) / entry_price) * 100
                        else:
                            position_pnl_pct = ((entry_price - cached_price) / entry_price) * 100

                    # v4.2: Get SL/TP from trailing_stop_state
                    instrument_key = str(self.instrument_id)
                    if instrument_key in self.trailing_stop_state:
                        ts_state = self.trailing_stop_state[instrument_key]
                        sl_price = ts_state.get('current_sl_price')
                        tp_price = ts_state.get('current_tp_price')
            except Exception:
                pass

            # 7. 获取上次信号
            last_signal = getattr(self, 'last_signal', None) or {}
            signal = last_signal.get('signal') or 'PENDING'
            confidence = last_signal.get('confidence') or 'N/A'

            # 8. 组装 v3.6/3.7/3.8 数据 (如果可用)
            order_flow_heartbeat = None
            if self.latest_order_flow_data:
                order_flow_heartbeat = {
                    'buy_ratio': self.latest_order_flow_data.get('buy_ratio'),
                    'cvd_trend': self.latest_order_flow_data.get('cvd_trend'),
                }

            derivatives_heartbeat = None
            if self.latest_derivatives_data and self.latest_derivatives_data.get('enabled'):
                funding = self.latest_derivatives_data.get('funding_rate', {})
                oi = self.latest_derivatives_data.get('open_interest', {})
                derivatives_heartbeat = {
                    'funding_rate': funding.get('value') if funding else None,
                    'oi_change_pct': oi.get('change_pct') if oi else None,
                }

            orderbook_heartbeat = None
            if self.latest_orderbook_data and self.latest_orderbook_data.get('_status', {}).get('code') == 'OK':
                obi = self.latest_orderbook_data.get('obi', {})
                dynamics = self.latest_orderbook_data.get('dynamics', {})
                orderbook_heartbeat = {
                    'weighted_obi': obi.get('weighted'),
                    'obi_trend': dynamics.get('obi_trend'),
                }

            sr_zone_heartbeat = None
            if self.latest_sr_zones_data:
                # v3.8 fix: Access SRZone objects directly, extract price_center
                nearest_sup = self.latest_sr_zones_data.get('nearest_support')
                nearest_res = self.latest_sr_zones_data.get('nearest_resistance')
                hard_control = self.latest_sr_zones_data.get('hard_control', {})
                sr_zone_heartbeat = {
                    'nearest_support': nearest_sup.price_center if nearest_sup else None,
                    'nearest_resistance': nearest_res.price_center if nearest_res else None,
                    'block_long': hard_control.get('block_long', False),
                    'block_short': hard_control.get('block_short', False),
                }

            # 9. 获取信号执行状态 (v4.1)
            # v4.4: 状态一致性检查 - 防止缓存状态与实时仓位矛盾
            signal_status_heartbeat = getattr(self, '_last_signal_status', None)
            if signal_status_heartbeat and not position_side:
                # 缓存状态说有仓位，但实时查询无仓位 → 状态过时
                cached_reason = signal_status_heartbeat.get('reason', '')
                if '已持有' in cached_reason:
                    # 仓位已被止损/止盈平掉，清除过时状态
                    signal_status_heartbeat = {
                        'executed': False,
                        'reason': '仓位已平仓 (SL/TP 触发)',
                        'action_taken': '等待新信号',
                    }
                    self._last_signal_status = signal_status_heartbeat
                    self.log.info("🔄 检测到仓位已平仓，更新信号状态")

            # 10. 发送消息 (v4.2: 添加 SL/TP)
            heartbeat_msg = self.telegram_bot.format_heartbeat_message({
                'signal': signal,
                'confidence': confidence,
                'price': cached_price or 0,
                'rsi': rsi,
                'position_side': position_side,
                'position_pnl_pct': position_pnl_pct,
                'entry_price': entry_price,
                'position_size': position_size,
                'sl_price': sl_price,      # v4.2: Add stop loss
                'tp_price': tp_price,      # v4.2: Add take profit
                'timer_count': getattr(self, '_timer_count', 0),
                'equity': equity,
                'uptime_str': uptime_str,
                # v3.6/3.7/3.8 data
                'order_flow': order_flow_heartbeat,
                'derivatives': derivatives_heartbeat,
                'order_book': orderbook_heartbeat,
                'sr_zone': sr_zone_heartbeat,
                # v4.1 signal execution status
                'signal_status': signal_status_heartbeat,
            })
            self.telegram_bot.send_message_sync(heartbeat_msg)
            self.log.info(f"💓 Sent heartbeat #{self._timer_count}")
        except Exception as e:
            self.log.warning(f"Failed to send Telegram heartbeat: {e}")

    def _calculate_price_change(self) -> float:
        """Calculate price change percentage (last bar only)."""
        bars = self.indicator_manager.recent_bars
        if len(bars) < 2:
            return 0.0

        current = float(bars[-1].close)
        previous = float(bars[-2].close)

        return ((current - previous) / previous) * 100

    def _calculate_period_statistics(self) -> Dict[str, Any]:
        """
        Calculate price statistics from available K-line history.

        Returns period high/low/change based on available bars.
        With 15m K-lines: 50 bars ≈ 12.5h, 96 bars = 24h

        Returns
        -------
        Dict with:
            - period_high: Highest price in period
            - period_low: Lowest price in period
            - period_change_pct: Price change % from period start
            - period_hours: Actual hours of data available
        """
        bars = self.indicator_manager.recent_bars
        if not bars or len(bars) < 2:
            return {
                'period_high': 0,
                'period_low': 0,
                'period_change_pct': 0,
                'period_hours': 0,
            }

        current_price = float(bars[-1].close)
        period_start_price = float(bars[0].open)

        # Calculate high/low from all available bars
        period_high = max(float(bar.high) for bar in bars)
        period_low = min(float(bar.low) for bar in bars)

        # Calculate price change from period start
        period_change_pct = ((current_price - period_start_price) / period_start_price) * 100 if period_start_price > 0 else 0

        # Estimate hours based on bar count (assuming 15m bars)
        period_hours = len(bars) * 15 / 60

        return {
            'period_high': period_high,
            'period_low': period_low,
            'period_change_pct': period_change_pct,
            'period_hours': round(period_hours, 1),
        }

    def _get_account_context(self, current_price: Optional[float] = None) -> Dict[str, Any]:
        """
        Get account-level information for AI decision making (v4.6 + v4.7).

        This provides context for add/reduce position decisions:
        - How much capital is available
        - Current leverage setting
        - Maximum position capacity
        - Remaining capacity for new positions
        - Portfolio-level risk metrics (v4.7)

        Returns
        -------
        Dict with account fields:
            - equity: Total account equity (USDT)
            - leverage: Current leverage multiplier
            - max_position_value: Maximum position value allowed (equity * max_position_ratio * leverage)
            - current_position_value: Current position value (if any)
            - available_capacity: Remaining capacity for new positions
            - capacity_used_pct: Percentage of max capacity currently used
            - can_add_position: Boolean indicating if more positions can be added
            v4.7 additions:
            - total_unrealized_pnl_usd: Sum of all positions' unrealized P&L
            - liquidation_buffer_portfolio_min_pct: Minimum liquidation buffer across all positions
            - total_daily_funding_cost_usd: Daily funding cost for all positions
            - total_cumulative_funding_paid_usd: Cumulative funding paid since positions opened
            - can_add_position_safely: True if liquidation buffer > 15%
        """
        # Get equity (real balance or configured)
        equity = getattr(self, 'equity', 0) or self.config.equity

        # Get leverage
        leverage = getattr(self, 'leverage', self.config.leverage)

        # Get max position ratio from config
        max_position_ratio = getattr(self.config, 'max_position_ratio', 0.30)

        # Calculate max position value (notional)
        # max_position_value = equity * max_position_ratio * leverage
        max_position_value = equity * max_position_ratio * leverage

        # Calculate current position value and aggregate portfolio metrics
        current_position_value = 0.0
        total_unrealized_pnl_usd = 0.0
        liquidation_buffer_portfolio_min_pct = 100.0  # Start high, find minimum
        total_daily_funding_cost_usd = 0.0
        total_cumulative_funding_paid_usd = 0.0

        positions = self.cache.positions_open(instrument_id=self.instrument_id)
        maintenance_margin_ratio = 0.004  # Binance standard

        for position in positions:
            if position and position.is_open:
                quantity = float(position.quantity)
                avg_px = float(position.avg_px_open)
                side = 'long' if position.side == PositionSide.LONG else 'short'

                # Use current_price or entry price
                pos_price = current_price if current_price and current_price > 0 else avg_px
                position_value = quantity * pos_price
                current_position_value += position_value

                # Unrealized PnL
                try:
                    pnl = float(position.unrealized_pnl(pos_price)) if pos_price else 0.0
                    total_unrealized_pnl_usd += pnl
                except Exception:
                    pass

                # Calculate liquidation buffer for this position
                if avg_px > 0 and leverage > 0:
                    if side == 'long':
                        liq_price = avg_px * (1 - 1/leverage + maintenance_margin_ratio)
                        if pos_price and liq_price > 0:
                            buffer_pct = ((pos_price - liq_price) / pos_price) * 100
                    else:
                        liq_price = avg_px * (1 + 1/leverage - maintenance_margin_ratio)
                        if pos_price and liq_price > 0:
                            buffer_pct = ((liq_price - pos_price) / pos_price) * 100

                    if buffer_pct is not None:
                        liquidation_buffer_portfolio_min_pct = min(
                            liquidation_buffer_portfolio_min_pct,
                            max(0, buffer_pct)
                        )

                # Get funding rate and calculate costs
                funding_data = getattr(self, 'latest_derivatives_data', None)
                funding_rate = 0.0
                if funding_data:
                    fr = funding_data.get('funding_rate', {})
                    if fr and isinstance(fr, dict):
                        funding_rate = fr.get('value', 0) or 0

                if funding_rate != 0 and position_value > 0:
                    # Daily funding cost
                    daily_cost = position_value * abs(funding_rate) * 3
                    total_daily_funding_cost_usd += daily_cost

                    # Estimate cumulative funding
                    try:
                        ts_opened_ns = position.ts_opened
                        if ts_opened_ns:
                            now_ns = self.clock.timestamp_ns()
                            hours_held = (now_ns - ts_opened_ns) / 1e9 / 3600
                            settlements = hours_held / 8
                            if side == 'long':
                                cumulative = position_value * funding_rate * settlements
                            else:
                                cumulative = -position_value * funding_rate * settlements
                            total_cumulative_funding_paid_usd += cumulative
                    except Exception:
                        pass

        # If no positions, reset min buffer to N/A
        if not positions or current_position_value == 0:
            liquidation_buffer_portfolio_min_pct = None

        # Calculate available capacity
        available_capacity = max(0, max_position_value - current_position_value)

        # Calculate capacity used percentage
        capacity_used_pct = 0.0
        if max_position_value > 0:
            capacity_used_pct = (current_position_value / max_position_value) * 100

        # Determine if can add position (at least 10% capacity remaining)
        can_add_position = capacity_used_pct < 90

        # v4.7: Safer check - also consider liquidation buffer
        can_add_position_safely = can_add_position and (
            liquidation_buffer_portfolio_min_pct is None or
            liquidation_buffer_portfolio_min_pct > 15
        )

        return {
            'equity': round(equity, 2),
            'leverage': leverage,
            'max_position_ratio': max_position_ratio,
            'max_position_value': round(max_position_value, 2),
            'current_position_value': round(current_position_value, 2),
            'available_capacity': round(available_capacity, 2),
            'capacity_used_pct': round(capacity_used_pct, 1),
            'can_add_position': can_add_position,
            # === v4.7: Portfolio-Level Risk Fields ===
            'total_unrealized_pnl_usd': round(total_unrealized_pnl_usd, 2),
            'liquidation_buffer_portfolio_min_pct': round(liquidation_buffer_portfolio_min_pct, 2) if liquidation_buffer_portfolio_min_pct is not None else None,
            'total_daily_funding_cost_usd': round(total_daily_funding_cost_usd, 2),
            'total_cumulative_funding_paid_usd': round(total_cumulative_funding_paid_usd, 2),
            'can_add_position_safely': can_add_position_safely,
        }

    def _get_current_position_data(self, current_price: Optional[float] = None, from_telegram: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get current position information with enhanced data for AI decision making.

        Parameters
        ----------
        current_price : float, optional
            If provided, use this price for PnL calculation.
        from_telegram : bool, default False
            If True, NEVER access indicator_manager (Telegram thread safety).
            When True, will use cache.price() as fallback instead of indicator_manager.

        Returns
        -------
        Dict with Tier 1 + Tier 2 position fields for AI:
            - side, quantity, avg_px, unrealized_pnl (basic)
            - pnl_percentage, duration_minutes, entry_timestamp (Tier 1)
            - sl_price, tp_price, risk_reward_ratio (Tier 1)
            - peak_pnl_pct, worst_pnl_pct, entry_confidence (Tier 2)
            - margin_used_pct (Tier 2)
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

            # === Basic fields (existing) ===
            side = 'long' if position.side == PositionSide.LONG else 'short'
            quantity = float(position.quantity)
            avg_px = float(position.avg_px_open)
            unrealized_pnl = float(position.unrealized_pnl(current_price)) if current_price else 0.0

            # === Tier 1: Must have ===
            # PnL percentage
            pnl_percentage = 0.0
            if avg_px > 0 and current_price:
                if side == 'long':
                    pnl_percentage = ((current_price - avg_px) / avg_px) * 100
                else:
                    pnl_percentage = ((avg_px - current_price) / avg_px) * 100

            # Duration in minutes
            duration_minutes = 0
            entry_timestamp = None
            try:
                # NautilusTrader Position has ts_opened (nanoseconds)
                ts_opened_ns = position.ts_opened
                if ts_opened_ns:
                    from datetime import datetime, timezone
                    entry_timestamp = datetime.fromtimestamp(ts_opened_ns / 1e9, tz=timezone.utc).isoformat()
                    now_ns = self.clock.timestamp_ns()
                    duration_minutes = int((now_ns - ts_opened_ns) / 1e9 / 60)
            except Exception:
                pass

            # SL/TP from trailing_stop_state
            sl_price = None
            tp_price = None
            risk_reward_ratio = None
            instrument_key = str(self.instrument_id)
            if instrument_key in self.trailing_stop_state:
                ts_state = self.trailing_stop_state[instrument_key]
                sl_price = ts_state.get('current_sl_price')
                tp_price = ts_state.get('current_tp_price')

                # Calculate R/R ratio
                if sl_price and tp_price and avg_px > 0:
                    if side == 'long':
                        risk = avg_px - sl_price
                        reward = tp_price - avg_px
                    else:
                        risk = sl_price - avg_px
                        reward = avg_px - tp_price
                    if risk > 0:
                        risk_reward_ratio = round(reward / risk, 2)

            # === Tier 2: Recommended ===
            # Peak/worst PnL (from trailing_stop_state if tracking)
            peak_pnl_pct = None
            worst_pnl_pct = None
            if instrument_key in self.trailing_stop_state:
                ts_state = self.trailing_stop_state[instrument_key]
                highest_price = ts_state.get('highest_price')
                lowest_price = ts_state.get('lowest_price')

                if side == 'long':
                    if highest_price and avg_px > 0:
                        peak_pnl_pct = round(((highest_price - avg_px) / avg_px) * 100, 2)
                    if lowest_price and avg_px > 0:
                        worst_pnl_pct = round(((lowest_price - avg_px) / avg_px) * 100, 2)
                else:  # short
                    if lowest_price and avg_px > 0:
                        peak_pnl_pct = round(((avg_px - lowest_price) / avg_px) * 100, 2)
                    if highest_price and avg_px > 0:
                        worst_pnl_pct = round(((avg_px - highest_price) / avg_px) * 100, 2)

            # Entry confidence from last_signal
            entry_confidence = None
            last_signal = getattr(self, 'last_signal', None)
            if last_signal:
                entry_confidence = last_signal.get('confidence')

            # Margin used percentage (position value / equity)
            margin_used_pct = None
            equity = getattr(self, 'equity', 0)
            position_value = 0.0
            if equity and equity > 0 and current_price:
                position_value = quantity * current_price
                margin_used_pct = round((position_value / equity) * 100, 2)

            # === v4.7: Liquidation Risk Fields (CRITICAL) ===
            # Calculate liquidation price using simplified formula
            # LONG: liq_price = entry * (1 - 1/leverage + maintenance_margin)
            # SHORT: liq_price = entry * (1 + 1/leverage - maintenance_margin)
            leverage = getattr(self, 'leverage', self.config.leverage)
            maintenance_margin_ratio = 0.004  # Binance standard for 20x leverage tier

            liquidation_price = None
            liquidation_buffer_pct = None
            is_liquidation_risk_high = False

            if avg_px > 0 and leverage > 0:
                if side == 'long':
                    liquidation_price = avg_px * (1 - 1/leverage + maintenance_margin_ratio)
                    if current_price and liquidation_price > 0:
                        liquidation_buffer_pct = ((current_price - liquidation_price) / current_price) * 100
                else:  # short
                    liquidation_price = avg_px * (1 + 1/leverage - maintenance_margin_ratio)
                    if current_price and liquidation_price > 0:
                        liquidation_buffer_pct = ((liquidation_price - current_price) / current_price) * 100

                if liquidation_buffer_pct is not None:
                    liquidation_buffer_pct = round(max(0, liquidation_buffer_pct), 2)
                    is_liquidation_risk_high = liquidation_buffer_pct < 10  # < 10% buffer is risky

            # === v4.7: Funding Rate Fields (CRITICAL for perpetuals) ===
            funding_rate_current = None
            funding_rate_cumulative_usd = None
            effective_pnl_after_funding = None
            daily_funding_cost_usd = None

            # Get funding rate from latest_derivatives_data
            funding_data = getattr(self, 'latest_derivatives_data', None)
            if funding_data:
                fr = funding_data.get('funding_rate', {})
                if fr and isinstance(fr, dict):
                    funding_rate_current = fr.get('value', 0) or 0

            # Calculate funding costs if we have the rate
            if funding_rate_current is not None and position_value > 0:
                # Daily funding cost = position_value * |rate| * 3 settlements/day
                daily_funding_cost_usd = round(position_value * abs(funding_rate_current) * 3, 2)

                # Estimate cumulative funding based on position duration
                # 8-hour settlements, so settlements_passed = hours_held / 8
                hours_held = duration_minutes / 60 if duration_minutes > 0 else 0
                settlements_passed = hours_held / 8

                # For LONG with positive funding: we pay; for SHORT with positive funding: we receive
                if side == 'long':
                    funding_rate_cumulative_usd = round(position_value * funding_rate_current * settlements_passed, 2)
                else:
                    funding_rate_cumulative_usd = round(-position_value * funding_rate_current * settlements_passed, 2)

                # Effective PnL = unrealized PnL - cumulative funding paid
                effective_pnl_after_funding = round(unrealized_pnl - funding_rate_cumulative_usd, 2)

            # === v4.7: Drawdown Attribution Fields (RECOMMENDED) ===
            max_drawdown_pct = None
            max_drawdown_duration_bars = None
            consecutive_lower_lows = 0

            # Calculate drawdown from peak
            if peak_pnl_pct is not None and pnl_percentage is not None:
                if peak_pnl_pct > pnl_percentage:
                    max_drawdown_pct = round(peak_pnl_pct - pnl_percentage, 2)
                else:
                    max_drawdown_pct = 0.0

            # Estimate drawdown duration in 15-min bars
            if max_drawdown_pct and max_drawdown_pct > 0:
                # Simplified: assume drawdown started at some point during position
                max_drawdown_duration_bars = max(1, duration_minutes // 15)

            # Count consecutive lower lows from recent bars (if accessible)
            if not from_telegram:  # Only in main thread
                try:
                    bars = self.indicator_manager.recent_bars
                    if bars and len(bars) >= 3:
                        count = 0
                        for i in range(len(bars) - 1, 0, -1):
                            if bars[i].low < bars[i-1].low:
                                count += 1
                            else:
                                break
                        consecutive_lower_lows = count
                except Exception:
                    pass

            return {
                # Basic (existing)
                'side': side,
                'quantity': quantity,
                'avg_px': avg_px,
                'unrealized_pnl': unrealized_pnl,
                # Tier 1
                'pnl_percentage': round(pnl_percentage, 2),
                'duration_minutes': duration_minutes,
                'entry_timestamp': entry_timestamp,
                'sl_price': sl_price,
                'tp_price': tp_price,
                'risk_reward_ratio': risk_reward_ratio,
                # Tier 2
                'peak_pnl_pct': peak_pnl_pct,
                'worst_pnl_pct': worst_pnl_pct,
                'entry_confidence': entry_confidence,
                'margin_used_pct': margin_used_pct,
                # Context
                'current_price': float(current_price) if current_price else None,
                # === v4.7: Liquidation Risk (CRITICAL) ===
                'liquidation_price': round(liquidation_price, 2) if liquidation_price else None,
                'liquidation_buffer_pct': liquidation_buffer_pct,
                'is_liquidation_risk_high': is_liquidation_risk_high,
                # === v4.7: Funding Rate (CRITICAL) ===
                'funding_rate_current': funding_rate_current,
                'funding_rate_cumulative_usd': funding_rate_cumulative_usd,
                'effective_pnl_after_funding': effective_pnl_after_funding,
                'daily_funding_cost_usd': daily_funding_cost_usd,
                # === v4.7: Drawdown Attribution (RECOMMENDED) ===
                'max_drawdown_pct': max_drawdown_pct,
                'max_drawdown_duration_bars': max_drawdown_duration_bars,
                'consecutive_lower_lows': consecutive_lower_lows,
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
                # v4.1: Update signal status
                self._last_signal_status = {
                    'executed': False,
                    'reason': '交易已暂停',
                    'action_taken': '',
                }
                return

        # Store signal and technical data for SL/TP calculation
        self.latest_signal_data = signal_data
        self.latest_technical_data = technical_data
        self.latest_price_data = price_data

        signal = signal_data['signal']
        confidence = signal_data['confidence']

        # v3.12: Normalize legacy signals (BUY→LONG, SELL→SHORT)
        legacy_mapping = {'BUY': 'LONG', 'SELL': 'SHORT'}
        if signal in legacy_mapping:
            signal = legacy_mapping[signal]
            signal_data['signal'] = signal  # Update for downstream use

        # Check minimum confidence (skip for CLOSE and REDUCE - always allow risk reduction)
        if signal not in ('CLOSE', 'REDUCE', 'HOLD'):
            confidence_levels = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}
            min_conf_level = confidence_levels.get(self.min_confidence, 1)
            signal_conf_level = confidence_levels.get(confidence, 1)

            if signal_conf_level < min_conf_level:
                self.log.warning(
                    f"⚠️ Signal confidence {confidence} below minimum {self.min_confidence}, skipping trade"
                )
                self._last_signal_status = {
                    'executed': False,
                    'reason': f'信心不足 ({confidence} < {self.min_confidence})',
                    'action_taken': '',
                }
                return

        # Handle HOLD signal
        if signal == 'HOLD':
            self.log.info("📊 Signal: HOLD - No action taken")
            self._last_signal_status = {
                'executed': False,
                'reason': 'AI 建议观望',
                'action_taken': '',
            }
            return

        # v3.12: Handle CLOSE signal - close position without opening opposite
        if signal == 'CLOSE':
            if not current_position:
                self.log.info("📊 Signal: CLOSE - No position to close")
                self._last_signal_status = {
                    'executed': False,
                    'reason': '无持仓可平',
                    'action_taken': '',
                }
                return

            # Close the existing position
            self._close_position_only(current_position)
            return

        # v3.12: Handle REDUCE signal - reduce position size but keep direction
        if signal == 'REDUCE':
            if not current_position:
                self.log.info("📊 Signal: REDUCE - No position to reduce")
                self._last_signal_status = {
                    'executed': False,
                    'reason': '无持仓可减',
                    'action_taken': '',
                }
                return

            # Calculate target size from position_size_pct
            position_size_pct = signal_data.get('position_size_pct', 50)
            self._reduce_position(current_position, position_size_pct)
            return

        # For LONG/SHORT signals, calculate position size
        calculated_quantity = self._calculate_position_size(
            signal_data, price_data, technical_data, current_position
        )

        # v4.8: 累加模式下，calculated_quantity 是"本次加仓量"
        # 需要转换为"目标仓位"供 _manage_existing_position 使用
        if self.position_sizing_cumulative and current_position:
            current_qty = current_position.get('quantity', 0)
            target_quantity = current_qty + calculated_quantity
            self.log.info(
                f"📊 累加模式: 当前 {current_qty:.4f} + 加仓 {calculated_quantity:.4f} = 目标 {target_quantity:.4f} BTC"
            )
        else:
            target_quantity = calculated_quantity

        if target_quantity == 0 and calculated_quantity == 0:
            self.log.warning("⚠️ Calculated position size is 0, skipping trade")
            self._last_signal_status = {
                'executed': False,
                'reason': '仓位计算为0 (余额不足)',
                'action_taken': '',
            }

            # Notify user about insufficient position size
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

        # v3.12: Determine order side from normalized signal
        target_side = 'long' if signal == 'LONG' else 'short'

        # v4.0: Store execution data for unified Telegram notification in on_position_opened
        # This replaces the separate signal/fill/position notifications with one comprehensive message
        if self.telegram_bot and self.enable_telegram:
            judge_info = signal_data.get('judge_decision', {})
            self._pending_execution_data = {
                'signal': signal,
                'confidence': confidence,
                'target_quantity': target_quantity,
                'price': price_data.get('price', 0),
                'rsi': technical_data.get('rsi'),
                'macd': technical_data.get('macd'),
                'winning_side': judge_info.get('winning_side', ''),
                'reasoning': signal_data.get('reason', ''),
            }

        # Execute position management logic
        if current_position:
            self._manage_existing_position(
                current_position, target_side, target_quantity, confidence
            )
        else:
            self._open_new_position(target_side, target_quantity)

        # v3.11: Add action_taken to pending execution data for Telegram notification
        # This allows Telegram to show specific action (开多/平空/反转 etc.) instead of just BUY/SELL
        if self._pending_execution_data and self._last_signal_status:
            self._pending_execution_data['action_taken'] = self._last_signal_status.get('action_taken', '')
            self._pending_execution_data['was_executed'] = self._last_signal_status.get('executed', False)

        # Note: Telegram notification is now sent in on_position_opened for new positions
        # This ensures we have accurate fill price and SL/TP info

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
            'leverage': self.leverage,  # v4.8: 添加杠杆
            'high_confidence_multiplier': self.position_config.get('high_confidence_multiplier', 1.5),
            'medium_confidence_multiplier': self.position_config.get('medium_confidence_multiplier', 1.0),
            'low_confidence_multiplier': self.position_config.get('low_confidence_multiplier', 0.5),
            'trend_strength_multiplier': self.position_config.get('trend_strength_multiplier', 1.2),
            'rsi_extreme_multiplier': self.rsi_extreme_mult,
            'rsi_extreme_upper': self.rsi_extreme_upper,
            'rsi_extreme_lower': self.rsi_extreme_lower,
            'max_position_ratio': self.position_config.get('max_position_ratio', 0.3),
            'min_trade_amount': self.position_config.get('min_trade_amount', 0.001),
            'position_sizing': self.position_sizing_config,  # v4.8: 添加仓位计算配置
        }

        btc_quantity, details = calculate_position_size(
            signal_data, price_data, technical_data, config, logger
        )

        # v4.8: 累加模式 - 计算的是"本次加仓量"而不是"目标仓位"
        if self.position_sizing_cumulative and current_position:
            # 累加模式下，btc_quantity 就是本次要加的量
            # 需要检查是否超过 max_usdt 限制
            current_qty = current_position.get('quantity', 0)
            current_price = price_data.get('price', 100000)
            current_value = current_qty * current_price

            max_usdt = details.get('max_usdt', self.equity * self.leverage * 0.3)
            remaining_capacity = max_usdt - current_value

            if remaining_capacity <= 0:
                self.log.warning(
                    f"⚠️ 仓位已达上限 (${current_value:.0f} >= ${max_usdt:.0f}), 无法加仓"
                )
                return 0.0

            # 限制加仓量不超过剩余容量
            max_add_btc = remaining_capacity / current_price
            if btc_quantity > max_add_btc:
                self.log.info(
                    f"📊 加仓受限: {btc_quantity:.4f} → {max_add_btc:.4f} BTC "
                    f"(剩余容量: ${remaining_capacity:.0f})"
                )
                btc_quantity = max_add_btc

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
                # v4.1: Update signal status - same direction, holding
                side_cn = '多' if current_side == 'long' else '空'
                self._last_signal_status = {
                    'executed': False,
                    'reason': f'已持有{side_cn}仓 ({current_qty:.4f} BTC)',
                    'action_taken': '维持现有仓位',
                }
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
                # v4.1: Update signal status - adding to position
                self._last_signal_status = {
                    'executed': True,
                    'reason': '',
                    'action_taken': f'加仓 +{abs(size_diff):.4f} BTC',
                }
            else:
                # Reduce position
                # v3.10: Cancel pending SL/TP before reducing to prevent quantity mismatch
                # Old SL/TP might have larger quantity than reduced position
                cancel_failed = False
                try:
                    open_orders = self.cache.orders_open(instrument_id=self.instrument_id)
                    reduce_only_orders = [o for o in open_orders if o.is_reduce_only]
                    if reduce_only_orders:
                        self.log.info(f"🗑️ Cancelling {len(reduce_only_orders)} SL/TP orders before reduce")
                        for order in reduce_only_orders:
                            try:
                                self.cancel_order(order)
                            except Exception as e:
                                self.log.warning(f"Failed to cancel order: {e}")
                                cancel_failed = True
                except Exception as e:
                    self.log.error(f"❌ Failed to cancel SL/TP orders: {e}")
                    cancel_failed = True

                if cancel_failed:
                    # v3.10: Warn but continue - reduce is less risky than reversal
                    # Orphan cleanup will handle remaining orders later
                    self.log.warning("⚠️ Some orders failed to cancel, continuing with reduce (orphan cleanup will handle)")

                # v4.4: Re-verify position exists before submitting reduce_only order
                verified_position = self._get_current_position_data()
                if not verified_position:
                    self.log.warning("⚠️ Position no longer exists (likely closed by SL/TP), skipping reduce order")
                    self._last_signal_status = {
                        'executed': False,
                        'reason': '仓位已平仓 (SL/TP 触发)',
                        'action_taken': '',
                    }
                    return
                # Use fresh position quantity for reduce calculation
                fresh_qty = verified_position['quantity']
                actual_reduce = min(abs(size_diff), fresh_qty)  # Can't reduce more than current

                self._submit_order(
                    side=OrderSide.SELL if target_side == 'long' else OrderSide.BUY,
                    quantity=actual_reduce,
                    reduce_only=True,
                )
                self.log.info(
                    f"📉 Reducing {target_side} position: {abs(size_diff):.3f} BTC "
                    f"({current_qty:.3f} → {target_quantity:.3f})"
                )
                # v4.1: Update signal status - reducing position
                self._last_signal_status = {
                    'executed': True,
                    'reason': '',
                    'action_taken': f'减仓 -{abs(size_diff):.4f} BTC',
                }

        # Opposite direction - reverse position
        elif self.allow_reversals:
            # Check if high confidence required for reversal
            if self.require_high_conf_reversal and confidence != 'HIGH':
                self.log.warning(
                    f"🔒 Reversal requires HIGH confidence, got {confidence}. "
                    f"Keeping {current_side} position."
                )
                # v4.1: Update signal status - reversal blocked
                side_cn = '多' if current_side == 'long' else '空'
                self._last_signal_status = {
                    'executed': False,
                    'reason': f'反转需HIGH信心 (当前{confidence})',
                    'action_taken': f'保持{side_cn}仓',
                }
                return

            self.log.info(f"🔄 Reversing position: {current_side} → {target_side}")

            # v4.4: Re-verify position exists before reversal
            verified_position = self._get_current_position_data()
            if not verified_position:
                self.log.warning("⚠️ Position no longer exists (likely closed by SL/TP), skipping reversal")
                self._last_signal_status = {
                    'executed': False,
                    'reason': '仓位已平仓 (SL/TP 触发)',
                    'action_taken': '',
                }
                return
            # Update with fresh position data
            current_qty = verified_position['quantity']

            # v3.10: Cancel all pending orders BEFORE reversing to prevent -2022 ReduceOnly rejection
            # Old position's SL/TP orders are reduce_only=True, they'll be rejected if position closes first
            try:
                open_orders = self.cache.orders_open(instrument_id=self.instrument_id)
                if open_orders:
                    self.log.info(f"🗑️ Cancelling {len(open_orders)} pending orders before reversal")
                    self.cancel_all_orders(self.instrument_id)
            except Exception as e:
                # v3.10: ABORT reversal if cancel fails - continuing would cause -2022 errors
                self.log.error(f"❌ Failed to cancel pending orders, aborting reversal: {e}")
                self._last_signal_status = {
                    'executed': False,
                    'reason': f'取消挂单失败: {str(e)[:30]}',
                    'action_taken': '中止反转',
                }
                return

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
            # v4.1: Update signal status - reversal executed
            old_side_cn = '多' if current_side == 'long' else '空'
            new_side_cn = '多' if target_side == 'long' else '空'
            self._last_signal_status = {
                'executed': True,
                'reason': '',
                'action_taken': f'反转: {old_side_cn}→{new_side_cn}',
            }

        else:
            self.log.warning(
                f"⚠️ Signal suggests {target_side} but have {current_side} position. "
                f"Reversals disabled."
            )
            # v4.1: Update signal status - reversal disabled
            current_cn = '多' if current_side == 'long' else '空'
            target_cn = '多' if target_side == 'long' else '空'
            self._last_signal_status = {
                'executed': False,
                'reason': f'禁止反转 (持有{current_cn}仓)',
                'action_taken': '',
            }

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

        # v4.1: Update signal status - new position opened
        side_cn = '多' if side == 'long' else '空'
        self._last_signal_status = {
            'executed': True,
            'reason': '',
            'action_taken': f'开{side_cn}仓 {quantity:.4f} BTC',
        }

    def _close_position_only(self, current_position: Dict[str, Any]):
        """
        v3.12: Close position without opening opposite side.

        This is used when AI sends CLOSE signal, meaning:
        - Close the current position completely
        - Do NOT open any new position
        - Cancel all pending SL/TP orders first

        Different from reversal which closes then opens opposite.
        """
        # v4.4: Re-verify position exists before submitting reduce_only order
        # Position might have been closed by SL/TP between signal analysis and execution
        verified_position = self._get_current_position_data()
        if not verified_position:
            self.log.warning("⚠️ Position no longer exists (likely closed by SL/TP), skipping close order")
            self._last_signal_status = {
                'executed': False,
                'reason': '仓位已平仓 (SL/TP 触发)',
                'action_taken': '',
            }
            return

        current_side = verified_position['side']
        current_qty = verified_position['quantity']
        side_cn = '多' if current_side == 'long' else '空'

        self.log.info(f"🔴 Closing {current_side} position: {current_qty:.4f} BTC (CLOSE signal)")

        # Cancel all pending orders (SL/TP) before closing
        try:
            open_orders = self.cache.orders_open(instrument_id=self.instrument_id)
            if open_orders:
                self.log.info(f"🗑️ Cancelling {len(open_orders)} pending orders before close")
                self.cancel_all_orders(self.instrument_id)
        except Exception as e:
            self.log.warning(f"⚠️ Failed to cancel some orders: {e}, continuing with close")

        # Submit close order (reduce_only=True)
        close_side = OrderSide.SELL if current_side == 'long' else OrderSide.BUY
        self._submit_order(
            side=close_side,
            quantity=current_qty,
            reduce_only=True,
        )

        # Update signal status
        self._last_signal_status = {
            'executed': True,
            'reason': '',
            'action_taken': f'平{side_cn}仓 {current_qty:.4f} BTC',
        }

        # v4.2: Telegram notification moved to on_position_closed to avoid duplicate messages
        # The on_position_closed event will send a single comprehensive close notification

    def _reduce_position(self, current_position: Dict[str, Any], target_pct: int):
        """
        v3.12: Reduce position to target percentage.

        This is used when AI sends REDUCE signal with position_size_pct:
        - REDUCE with position_size_pct=50 means keep 50% of current position
        - REDUCE with position_size_pct=0 is equivalent to CLOSE

        Args:
            current_position: Current position info dict
            target_pct: Target position size as percentage (0-100)
                       0 = close all, 50 = keep half, 100 = no change
        """
        # v4.4: Re-verify position exists before submitting reduce_only order
        verified_position = self._get_current_position_data()
        if not verified_position:
            self.log.warning("⚠️ Position no longer exists (likely closed by SL/TP), skipping reduce order")
            self._last_signal_status = {
                'executed': False,
                'reason': '仓位已平仓 (SL/TP 触发)',
                'action_taken': '',
            }
            return

        current_side = verified_position['side']
        current_qty = verified_position['quantity']
        side_cn = '多' if current_side == 'long' else '空'

        # Validate and calculate target quantity
        target_pct = max(0, min(100, target_pct))  # Clamp to 0-100

        if target_pct >= 100:
            self.log.info(f"📊 REDUCE signal with 100% - no action needed")
            self._last_signal_status = {
                'executed': False,
                'reason': '减仓比例=100%',
                'action_taken': '维持现有仓位',
            }
            return

        if target_pct == 0:
            # Equivalent to CLOSE
            self.log.info(f"📊 REDUCE signal with 0% - equivalent to CLOSE")
            self._close_position_only(current_position)
            return

        # Calculate reduction amount
        target_qty = current_qty * (target_pct / 100.0)
        reduce_qty = current_qty - target_qty

        # Check minimum trade amount
        if reduce_qty < self.position_config['min_trade_amount']:
            self.log.warning(
                f"⚠️ Reduce quantity {reduce_qty:.4f} below minimum "
                f"{self.position_config['min_trade_amount']:.4f}, skipping"
            )
            self._last_signal_status = {
                'executed': False,
                'reason': f'减仓量低于最小交易量',
                'action_taken': '',
            }
            return

        self.log.info(
            f"📉 Reducing {current_side} position by {100-target_pct}%: "
            f"{current_qty:.4f} → {target_qty:.4f} BTC"
        )

        # Cancel SL/TP orders before reducing (they have old quantity)
        try:
            open_orders = self.cache.orders_open(instrument_id=self.instrument_id)
            reduce_only_orders = [o for o in open_orders if o.is_reduce_only]
            if reduce_only_orders:
                self.log.info(f"🗑️ Cancelling {len(reduce_only_orders)} SL/TP orders before reduce")
                for order in reduce_only_orders:
                    try:
                        self.cancel_order(order)
                    except Exception as e:
                        self.log.warning(f"Failed to cancel order: {e}")
        except Exception as e:
            self.log.warning(f"⚠️ Failed to cancel some orders: {e}, continuing with reduce")

        # Submit reduce order
        reduce_side = OrderSide.SELL if current_side == 'long' else OrderSide.BUY
        self._submit_order(
            side=reduce_side,
            quantity=reduce_qty,
            reduce_only=True,
        )

        # Update signal status
        self._last_signal_status = {
            'executed': True,
            'reason': '',
            'action_taken': f'减{side_cn}仓 {100-target_pct}% (-{reduce_qty:.4f} BTC)',
        }

        # v4.2: Telegram notification moved to on_position_changed events
        # This avoids duplicate messages (order submission + position update)

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
                        "current_tp_price": tp_price,  # v3.8: Store TP price for notifications
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

        # v4.0: Order fill notification is now combined with position notification
        # See on_position_opened for unified trade execution message
        # This reduces message spam (3 messages -> 1 comprehensive message)
    

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

        # v3.12: Store entry conditions for memory system
        self._last_entry_conditions = self._format_entry_conditions()

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

        # v4.0: Send unified trade execution notification (combines signal + fill + position)
        # This replaces 3 separate messages with 1 comprehensive notification
        if self.telegram_bot and self.enable_telegram and self.telegram_notify_positions:
            try:
                # Retrieve SL/TP prices from trailing_stop_state (v3.8)
                instrument_key = str(self.instrument_id)
                sl_price = None
                tp_price = None
                if instrument_key in self.trailing_stop_state:
                    state = self.trailing_stop_state[instrument_key]
                    sl_price = state.get("current_sl_price")
                    tp_price = state.get("current_tp_price")

                # v4.2: Retrieve S/R Zone data (v3.8 fix: extract price_center)
                sr_zone_data = None
                if self.latest_sr_zones_data:
                    nearest_sup = self.latest_sr_zones_data.get('nearest_support')
                    nearest_res = self.latest_sr_zones_data.get('nearest_resistance')
                    sr_zone_data = {
                        'nearest_support': nearest_sup.price_center if nearest_sup else None,
                        'nearest_resistance': nearest_res.price_center if nearest_res else None,
                    }

                # Build unified execution data from pending data + event data
                execution_data = {
                    'side': event.side.name,
                    'quantity': float(event.quantity),
                    'entry_price': float(event.avg_px_open),
                    'sl_price': sl_price,
                    'tp_price': tp_price,
                    'sr_zone': sr_zone_data,  # v4.2: Add S/R Zone
                }

                # Merge with pending execution data (signal info, technical indicators, AI analysis)
                if self._pending_execution_data:
                    execution_data.update({
                        'signal': self._pending_execution_data.get('signal', 'BUY' if event.side.name == 'LONG' else 'SELL'),
                        'confidence': self._pending_execution_data.get('confidence', 'MEDIUM'),
                        'rsi': self._pending_execution_data.get('rsi'),
                        'macd': self._pending_execution_data.get('macd'),
                        'winning_side': self._pending_execution_data.get('winning_side', ''),
                        'reasoning': self._pending_execution_data.get('reasoning', ''),
                    })
                    # Clear pending data after use
                    self._pending_execution_data = None
                else:
                    # Fallback if no pending data (shouldn't happen normally)
                    execution_data['signal'] = 'BUY' if event.side.name == 'LONG' else 'SELL'
                    execution_data['confidence'] = 'MEDIUM'

                # Send unified message
                execution_msg = self.telegram_bot.format_trade_execution(execution_data)
                self.telegram_bot.send_message_sync(execution_msg)
                self.log.info("✅ Sent unified trade execution notification")
            except Exception as e:
                self.log.warning(f"Failed to send Telegram trade execution notification: {e}")

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

        # v3.12: Calculate P&L percentage upfront (needed for both Telegram and memory system)
        # v3.13: Fix - NautilusTrader uses Money/Quantity types, need .as_double()
        # realized_pnl is Money type, quantity is Quantity type
        try:
            # Money type has .as_double() method
            pnl = event.realized_pnl.as_double() if hasattr(event.realized_pnl, 'as_double') else float(event.realized_pnl)
        except (AttributeError, TypeError, ValueError):
            pnl = 0.0
            self.log.warning(f"Failed to extract realized_pnl from event: {type(event.realized_pnl)}")

        try:
            # Quantity type has .as_double() method
            if hasattr(event, 'quantity'):
                quantity = event.quantity.as_double() if hasattr(event.quantity, 'as_double') else float(event.quantity)
            else:
                quantity = 0.0
        except (AttributeError, TypeError, ValueError):
            quantity = 0.0

        # avg_px_open and avg_px_close are plain doubles in PositionClosed event
        entry_price = float(event.avg_px_open) if hasattr(event, 'avg_px_open') else 0.0
        exit_price = float(event.avg_px_close) if hasattr(event, 'avg_px_close') else 0.0
        position_value = entry_price * quantity
        pnl_pct = (pnl / position_value * 100) if position_value > 0 else 0.0

        # v3.13: Debug logging to diagnose memory system issues
        self.log.debug(
            f"📊 P&L calculation: pnl={pnl:.4f}, qty={quantity:.4f}, "
            f"entry={entry_price:.2f}, exit={exit_price:.2f}, pnl_pct={pnl_pct:.2f}%"
        )

        # Send Telegram position closed notification
        if self.telegram_bot and self.enable_telegram and self.telegram_notify_positions:
            try:
                # v4.2: Retrieve S/R Zone data for close message (v3.8 fix: extract price_center)
                sr_zone_data = None
                if self.latest_sr_zones_data:
                    nearest_sup = self.latest_sr_zones_data.get('nearest_support')
                    nearest_res = self.latest_sr_zones_data.get('nearest_resistance')
                    sr_zone_data = {
                        'nearest_support': nearest_sup.price_center if nearest_sup else None,
                        'nearest_resistance': nearest_res.price_center if nearest_res else None,
                    }

                position_msg = self.telegram_bot.format_position_update({
                    'action': 'CLOSED',
                    'side': event.side.name,
                    'quantity': quantity,
                    'entry_price': entry_price,
                    'current_price': exit_price,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'sr_zone': sr_zone_data,  # v4.2: Add S/R Zone
                })
                self.telegram_bot.send_message_sync(position_msg)
            except Exception as e:
                self.log.warning(f"Failed to send Telegram position closed notification: {e}")

        # v3.12: Record outcome for AI learning
        try:
            if hasattr(self, 'multi_agent') and self.multi_agent:
                # Get decision from last signal
                decision = "UNKNOWN"
                if hasattr(self, 'last_signal') and self.last_signal:
                    signal = self.last_signal.get('signal', '')
                    # v3.12: Handle both legacy (BUY/SELL) and new (LONG/SHORT) formats
                    legacy_mapping = {'BUY': 'LONG', 'SELL': 'SHORT'}
                    decision = legacy_mapping.get(signal, signal)

                # Get entry conditions
                conditions = getattr(self, '_last_entry_conditions', 'N/A')

                # Record the outcome
                self.multi_agent.record_outcome(
                    decision=decision,
                    pnl=pnl_pct,
                    conditions=conditions,
                )
                self.log.info(f"📝 Trade outcome recorded for AI learning")
        except Exception as e:
            self.log.warning(f"Failed to record trade outcome: {e}")

    def on_order_canceled(self, event):
        """
        Handle order canceled events.

        v3.10: Track order cancellations for better order lifecycle management.
        This helps with:
        - Detecting manual cancellations vs system-initiated cancellations
        - Tracking SL/TP order cancellations before position changes
        - Debugging order flow issues
        """
        client_order_id = str(event.client_order_id)[:8] if hasattr(event, 'client_order_id') else 'N/A'

        self.log.info(
            f"🗑️ Order canceled: {client_order_id}... "
            f"(instrument: {getattr(event, 'instrument_id', self.instrument_id)})"
        )

        # Track in metrics if available
        if hasattr(self, '_order_cancel_count'):
            self._order_cancel_count += 1
        else:
            self._order_cancel_count = 1

    def on_order_expired(self, event):
        """
        Handle order expired events.

        v3.10: Track GTC order expirations (e.g., SL/TP orders that expire due to
        position close or market conditions).

        Common causes:
        - GTC orders reaching exchange time limits
        - Orders expiring due to market close (crypto: shouldn't happen)
        - Manual order expiration settings
        """
        client_order_id = str(event.client_order_id)[:8] if hasattr(event, 'client_order_id') else 'N/A'

        self.log.warning(
            f"⏰ Order expired: {client_order_id}... "
            f"(instrument: {getattr(event, 'instrument_id', self.instrument_id)})"
        )

        # Send Telegram alert for unexpected expirations
        if self.telegram_bot and self.enable_telegram:
            try:
                alert_msg = self.telegram_bot.format_error_alert({
                    'level': 'WARNING',
                    'message': f"Order Expired: {client_order_id}...",
                    'context': "GTC order expired unexpectedly",
                })
                self.telegram_bot.send_message_sync(alert_msg)
            except Exception as e:
                self.log.warning(f"Failed to send Telegram alert for order expiration: {e}")

    def on_order_denied(self, event):
        """
        Handle order denied events (system-level denial, before reaching exchange).

        v3.10: This is CRITICAL for bracket/contingent orders where partial failures
        can leave positions unprotected.

        Common causes:
        - Insufficient margin
        - Risk limit exceeded
        - Rate limiting
        - System pre-trade checks failed

        NautilusTrader docs: "Always handle OrderDenied and OrderRejected events
        in your strategy, especially for contingent orders where partial failures
        can leave positions unprotected."
        """
        reason = getattr(event, 'reason', 'Unknown reason')
        client_order_id = str(event.client_order_id)[:8] if hasattr(event, 'client_order_id') else 'N/A'

        self.log.error(f"🚫 Order DENIED (pre-exchange): {client_order_id}... - {reason}")

        # 🚨 CRITICAL: Send immediate Telegram alert
        if self.telegram_bot and self.enable_telegram:
            try:
                alert_msg = self.telegram_bot.format_error_alert({
                    'level': 'CRITICAL',
                    'message': f"Order DENIED: {reason}",
                    'context': f"Order ID: {client_order_id}... (pre-exchange denial)",
                })
                self.telegram_bot.send_message_sync(alert_msg)
                self.log.info("📱 Telegram alert sent for order denial")
            except Exception as e:
                self.log.warning(f"Failed to send Telegram alert for order denial: {e}")

        # Check if this leaves a position unprotected
        try:
            positions = self.cache.positions_open(instrument_id=self.instrument_id)
            if positions:
                self.log.error(
                    f"⚠️ CRITICAL: Position exists but order was denied! "
                    f"Position may be unprotected. Manual intervention recommended."
                )

                # Try to send additional critical alert
                if self.telegram_bot and self.enable_telegram:
                    try:
                        alert_msg = self.telegram_bot.format_error_alert({
                            'level': 'CRITICAL',
                            'message': "Position may be UNPROTECTED!",
                            'context': f"Order denial while position open. Check SL/TP orders manually.",
                        })
                        self.telegram_bot.send_message_sync(alert_msg)
                    except Exception:
                        pass
        except Exception as e:
            self.log.warning(f"Failed to check position status after denial: {e}")

    def on_position_changed(self, event):
        """
        Handle position quantity change events (partial fills, partial closes).

        v3.10: Track position size changes that don't result in full open/close.
        This is important for:
        - Detecting partial fills that may need SL/TP quantity adjustments
        - Tracking position scaling (adding to or reducing from position)
        - Debugging position synchronization issues
        """
        self.log.info(
            f"📊 Position changed: {event.side.name} "
            f"qty {event.quantity} (signed: {getattr(event, 'signed_qty', 'N/A')})"
        )

        # Update trailing stop state if position size changed
        if self.enable_trailing_stop:
            instrument_key = str(self.instrument_id)
            if instrument_key in self.trailing_stop_state:
                new_qty = float(event.quantity)
                old_qty = self.trailing_stop_state[instrument_key].get("quantity", 0)

                if new_qty != old_qty:
                    self.trailing_stop_state[instrument_key]["quantity"] = new_qty
                    self.log.info(
                        f"📊 Updated trailing stop quantity: {old_qty} → {new_qty}"
                    )

                    # Warning: SL/TP orders may need adjustment if position size changed
                    if new_qty < old_qty:
                        self.log.warning(
                            f"⚠️ Position reduced. Existing SL/TP orders may have larger "
                            f"quantity than current position. Consider adjusting manually."
                        )

    def _format_entry_conditions(self) -> str:
        """
        Format current market conditions for memory recording.

        v3.12: Captures key indicators at entry for pattern learning.
        """
        try:
            parts = []

            # Get cached price for context
            if hasattr(self, '_cached_current_price') and self._cached_current_price:
                parts.append(f"price=${self._cached_current_price:,.0f}")

            # Get technical indicators from indicator_manager
            if hasattr(self, 'indicator_manager') and self.indicator_manager:
                # RSI
                if hasattr(self.indicator_manager, 'rsi') and self.indicator_manager.rsi.initialized:
                    rsi = self.indicator_manager.rsi.value * 100
                    parts.append(f"RSI={rsi:.0f}")

                # MACD direction
                if hasattr(self.indicator_manager, 'macd') and self.indicator_manager.macd.initialized:
                    macd = self.indicator_manager.macd.value
                    macd_signal = self.indicator_manager.macd_signal.value if hasattr(self.indicator_manager, 'macd_signal') else 0
                    macd_dir = "bullish" if macd > macd_signal else "bearish"
                    parts.append(f"MACD={macd_dir}")

                # BB position (requires current price)
                if hasattr(self, '_cached_current_price') and self._cached_current_price:
                    try:
                        tech_data = self.indicator_manager.get_technical_data(self._cached_current_price)
                        bb_pos = tech_data.get('bb_position', 0.5) * 100
                        parts.append(f"BB={bb_pos:.0f}%")
                    except Exception:
                        pass

            # Get confidence and winning side from last signal
            if hasattr(self, 'last_signal') and self.last_signal:
                confidence = self.last_signal.get('confidence', 'N/A')
                parts.append(f"conf={confidence}")

                judge = self.last_signal.get('judge_decision', {})
                if judge:
                    winning = judge.get('winning_side', 'N/A')
                    parts.append(f"winner={winning}")

            # Get sentiment data if available
            if hasattr(self, 'latest_sentiment_data') and self.latest_sentiment_data:
                ls_ratio = self.latest_sentiment_data.get('long_short_ratio')
                if ls_ratio:
                    sentiment = "crowded_long" if ls_ratio > 2.0 else "crowded_short" if ls_ratio < 0.5 else "neutral"
                    parts.append(f"sentiment={sentiment}")

            return ", ".join(parts) if parts else "N/A"

        except Exception as e:
            self.log.debug(f"Failed to format entry conditions: {e}")
            return "N/A"

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

            # Verify position still exists (fix for -2022 ReduceOnly rejection)
            position = self.cache.position(self.position_id)
            if position is None or position.is_closed:
                self.log.debug(f"Position closed, cleaning up trailing_stop_state")
                del self.trailing_stop_state[instrument_key]
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
            # First, verify position still exists (fix for -2022 ReduceOnly rejection)
            position = self.cache.position(self.position_id)
            if position is None or position.is_closed:
                self.log.warning(
                    f"⚠️ Position no longer exists, skipping trailing stop update. "
                    f"Cleaning up trailing_stop_state."
                )
                # Clean up state
                if instrument_key in self.trailing_stop_state:
                    del self.trailing_stop_state[instrument_key]
                return

            state = self.trailing_stop_state[instrument_key]
            old_sl_price = state["current_sl_price"]
            old_sl_order_id = state["sl_order_id"]
            quantity = state["quantity"]

            # Verify quantity matches current position
            current_qty = float(position.quantity)
            if abs(current_qty - quantity) > 0.0001:
                self.log.warning(
                    f"⚠️ Position quantity changed ({quantity:.4f} → {current_qty:.4f}), "
                    f"updating trailing stop state"
                )
                state["quantity"] = current_qty
                quantity = current_qty

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

            # Send Telegram notification for trailing stop update (with throttle)
            # v3.13: Added notify_trailing_stop switch
            if (self.telegram_bot and self.enable_telegram and old_sl_price and
                getattr(self, 'telegram_notify_trailing_stop', True)):
                import time
                current_time = time.time()
                time_since_last = current_time - self._last_trailing_stop_notify_time

                if time_since_last >= self._trailing_stop_notify_throttle:
                    try:
                        entry_price = state.get("entry_price", 0)
                        profit_pct = ((current_price - entry_price) / entry_price) if entry_price > 0 else 0
                        if side == "SHORT":
                            profit_pct = -profit_pct  # SHORT profit is inverse

                        ts_msg = self.telegram_bot.format_trailing_stop_update({
                            'old_sl_price': old_sl_price,
                            'new_sl_price': new_sl_price,
                            'current_price': current_price,
                            'profit_pct': profit_pct,
                            'side': side,  # v4.0: Pass side for direction-aware message
                        })
                        self.telegram_bot.send_message_sync(ts_msg)
                        self._last_trailing_stop_notify_time = current_time
                    except Exception as te:
                        self.log.warning(f"Failed to send trailing stop notification: {te}")
                else:
                    self.log.debug(
                        f"Trailing stop notification throttled "
                        f"({time_since_last:.0f}s < {self._trailing_stop_notify_throttle:.0f}s)"
                    )

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
            elif command == 'daily_summary':
                return self._cmd_daily_summary()
            elif command == 'weekly_summary':
                return self._cmd_weekly_summary()
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

            # v4.7: Get account context for portfolio risk fields
            account_context = self._get_account_context(current_price) if current_price > 0 else {}

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
                # v4.7: Portfolio Risk Fields (CRITICAL)
                'total_unrealized_pnl_usd': account_context.get('total_unrealized_pnl_usd'),
                'liquidation_buffer_portfolio_min_pct': account_context.get('liquidation_buffer_portfolio_min_pct'),
                'total_daily_funding_cost_usd': account_context.get('total_daily_funding_cost_usd'),
                'can_add_position_safely': account_context.get('can_add_position_safely'),
                # v4.6: Account capacity fields
                'available_margin': account_context.get('available_margin'),
                'used_margin_pct': account_context.get('used_margin_pct'),
                'leverage': account_context.get('leverage'),
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
                    # v4.7: Liquidation Risk Fields (CRITICAL)
                    'liquidation_price': current_position.get('liquidation_price'),
                    'liquidation_buffer_pct': current_position.get('liquidation_buffer_pct'),
                    'is_liquidation_risk_high': current_position.get('is_liquidation_risk_high', False),
                    # v4.7: Funding Rate Fields (CRITICAL for perpetuals)
                    'funding_rate_current': current_position.get('funding_rate_current'),
                    'daily_funding_cost_usd': current_position.get('daily_funding_cost_usd'),
                    'funding_rate_cumulative_usd': current_position.get('funding_rate_cumulative_usd'),
                    'effective_pnl_after_funding': current_position.get('effective_pnl_after_funding'),
                    # v4.7: Drawdown Attribution Fields
                    'max_drawdown_pct': current_position.get('max_drawdown_pct'),
                    'peak_pnl_pct': current_position.get('peak_pnl_pct'),
                    # v4.5: Position context fields
                    'duration_minutes': current_position.get('duration_minutes'),
                    'entry_confidence': current_position.get('entry_confidence'),
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
                    'message': "ℹ️ *无持仓*\n\n当前没有需要平仓的仓位。"
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

            # v3.10: Cancel all pending orders BEFORE closing to prevent -2022 ReduceOnly rejection
            try:
                open_orders = self.cache.orders_open(instrument_id=self.instrument_id)
                if open_orders:
                    self.log.info(f"🗑️ Cancelling {len(open_orders)} pending orders before close")
                    self.cancel_all_orders(self.instrument_id)
            except Exception as e:
                # v3.10: ABORT close if cancel fails - user should retry
                self.log.error(f"❌ Failed to cancel pending orders, aborting close: {e}")
                return {
                    'success': False,
                    'error': f"Failed to cancel pending orders: {str(e)[:50]}. Please try again."
                }

            # Submit close order
            self._submit_order(
                side=close_side,
                quantity=quantity,
                reduce_only=True,
            )

            self.log.info(f"🔴 Position closed by Telegram command: {side_str} {quantity:.4f} BTC")

            return {
                'success': True,
                'message': f"✅ *正在平仓*\n\n"
                          f"平仓方向: {side_str}\n"
                          f"数量: {quantity:.4f} BTC\n\n"
                          f"⏳ 订单已提交，等待成交..."
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
                    'message': "ℹ️ *无挂单*\n\n当前没有待处理的订单。"
                }

            msg = f"📋 *挂单列表* ({len(orders)} 个)\n\n"

            for i, order in enumerate(orders, 1):
                order_type = order.order_type.name
                side = order.side.name
                side_cn = "买入" if side == "BUY" else "卖出"
                qty = float(order.quantity)

                # Get price for limit/stop orders
                price_str = ""
                if hasattr(order, 'price') and order.price:
                    price_str = f"@ ${float(order.price):,.2f}"
                elif hasattr(order, 'trigger_price') and order.trigger_price:
                    price_str = f"触发价 @ ${float(order.trigger_price):,.2f}"

                # Order status
                status = order.status.name
                reduce_only = "🔻" if order.is_reduce_only else ""

                msg += f"{i}. {side_cn} {order_type} {reduce_only}\n"
                msg += f"   数量: {qty:.4f} BTC {price_str}\n"
                msg += f"   状态: {status}\n\n"

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

        Thread-safe: Uses Binance API directly.
        """
        try:
            from datetime import datetime
            from utils.binance_account import get_binance_fetcher

            # 获取交易对 symbol
            symbol = str(self.instrument_id).split('.')[0] if self.instrument_id else "BTCUSDT"

            # 从 Binance API 获取最近交易
            fetcher = get_binance_fetcher()
            trades = fetcher.get_trades(symbol=symbol, limit=10)

            if not trades:
                return {
                    'success': True,
                    'message': "ℹ️ *无交易记录*\n\n暂无已执行的交易。"
                }

            msg = f"📊 *最近交易记录* (最近 {len(trades)} 笔)\n\n"

            for trade in reversed(trades):  # 最新的在前
                side = trade.get('side', 'UNKNOWN')
                side_emoji = "🟢" if side == "BUY" else "🔴"
                side_cn = "买入" if side == "BUY" else "卖出"
                qty = float(trade.get('qty', 0))
                price = float(trade.get('price', 0))
                realized_pnl = float(trade.get('realizedPnl', 0))
                commission = float(trade.get('commission', 0))
                ts = trade.get('time', 0)

                # 格式化时间
                try:
                    dt = datetime.utcfromtimestamp(ts / 1000) if ts else datetime.utcnow()
                    time_str = dt.strftime("%m-%d %H:%M")
                except (ValueError, TypeError, OSError):
                    time_str = "N/A"

                pnl_emoji = "📈" if realized_pnl > 0 else ("📉" if realized_pnl < 0 else "➖")
                msg += f"{side_emoji} {side_cn} {qty:.4f} @ ${price:,.2f}\n"
                msg += f"   {pnl_emoji} 盈亏: ${realized_pnl:+,.2f}\n"
                msg += f"   ⏰ 时间: {time_str} UTC\n\n"

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

            msg = "📊 *风险指标*\n\n"

            # Real Account Balance from Binance
            msg += "*账户 (实时)*:\n"
            if total_balance > 0:
                msg += f"• 余额: ${total_balance:,.2f} USDT\n"
                msg += f"• 可用: ${available_balance:,.2f} USDT\n"
                if unrealized_pnl_total != 0:
                    pnl_emoji = "📈" if unrealized_pnl_total >= 0 else "📉"
                    msg += f"• 未实现盈亏: {pnl_emoji} ${unrealized_pnl_total:,.2f}\n"
            else:
                msg += f"• 余额: ⚠️ 无法获取 (配置值: ${self.equity:,.2f})\n"
            msg += f"• 杠杆: {self.leverage}x\n"
            msg += f"• 最大仓位: {self.position_config.get('max_position_ratio', 0.3)*100:.0f}%\n\n"

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
                side_cn = "多头" if side == "LONG" else "空头"

                msg += "*当前持仓*:\n"
                msg += f"• 方向: {side_cn}\n"
                msg += f"• 数量: {qty:.4f} BTC (${position_value:,.2f})\n"
                msg += f"• 开仓价: ${entry_price:,.2f}\n"
                msg += f"• 当前价: ${cached_price:,.2f}\n"
                msg += f"• 盈亏: {pnl_emoji} ${pnl:,.2f} ({pnl_pct:+.2f}%)\n\n"

                # Risk exposure using real balance
                exposure_pct = (position_value / effective_equity) * 100 if effective_equity > 0 else 0
                msg += "*风险敞口*:\n"
                msg += f"• 仓位/余额: {exposure_pct:.1f}%\n"
                msg += f"• 杠杆敞口: {exposure_pct * self.leverage:.1f}%\n"
            else:
                msg += "*当前持仓*: 无\n"
                msg += "*风险敞口*: 0%\n"

            # Strategy settings
            msg += f"\n*策略设置*:\n"
            msg += f"• 最低信心: {self.min_confidence}\n"
            msg += f"• 自动止损止盈: {'✅' if self.enable_auto_sl_tp else '❌'}\n"
            msg += f"• 移动止损: {'✅' if self.enable_trailing_stop else '❌'}\n"
            msg += f"• 交易暂停: {'⏸️ 是' if self.is_trading_paused else '▶️ 否'}\n"

            return {
                'success': True,
                'message': msg
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _cmd_daily_summary(self) -> Dict[str, Any]:
        """
        Handle /daily command - view daily performance summary (v3.13).

        Thread-safe: Uses thread-safe state and cached data.
        """
        try:
            from datetime import datetime, timedelta

            today = datetime.utcnow().strftime('%Y-%m-%d')

            # Get real balance from Binance
            real_balance = self.binance_account.get_balance()
            current_equity = real_balance.get('total_balance', self.equity)

            # Calculate stats from session data
            with self._state_lock:
                timer_count = getattr(self, '_timer_count', 0)
                signals_generated = getattr(self, '_signals_generated_today', timer_count)
                signals_executed = getattr(self, '_signals_executed_today', 0)

            # Get trade history for today from memory system
            total_trades = 0
            winning_trades = 0
            losing_trades = 0
            total_pnl = 0.0
            largest_win = 0.0
            largest_loss = 0.0

            if hasattr(self, 'multi_agent_analyzer') and self.multi_agent_analyzer:
                memories = self.multi_agent_analyzer.decision_memory
                today_memories = [m for m in memories if m.get('timestamp', '').startswith(today)]

                for m in today_memories:
                    pnl = m.get('pnl', 0)
                    if pnl != 0:  # Only count actual trades
                        total_trades += 1
                        total_pnl += pnl
                        if pnl > 0:
                            winning_trades += 1
                            largest_win = max(largest_win, pnl)
                        else:
                            losing_trades += 1
                            largest_loss = min(largest_loss, pnl)

            # Calculate PnL percentage
            starting_equity = getattr(self, '_daily_starting_equity', current_equity)
            pnl_pct = ((current_equity - starting_equity) / starting_equity * 100) if starting_equity > 0 else 0.0

            summary_data = {
                'date': today,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'total_pnl': total_pnl,
                'total_pnl_pct': pnl_pct,
                'largest_win': largest_win,
                'largest_loss': abs(largest_loss),
                'starting_equity': starting_equity,
                'ending_equity': current_equity,
                'signals_generated': signals_generated,
                'signals_executed': signals_executed,
            }

            if self.telegram_bot:
                msg = self.telegram_bot.format_daily_summary(summary_data)
            else:
                # Fallback simple format
                msg = f"📊 Daily Summary ({today})\n"
                msg += f"Trades: {total_trades} (W: {winning_trades}, L: {losing_trades})\n"
                msg += f"PnL: ${total_pnl:+,.2f} ({pnl_pct:+.2f}%)\n"
                msg += f"Equity: ${current_equity:,.2f}"

            return {
                'success': True,
                'message': msg
            }
        except Exception as e:
            self.log.error(f"Error in _cmd_daily_summary: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _cmd_weekly_summary(self) -> Dict[str, Any]:
        """
        Handle /weekly command - view weekly performance summary (v3.13).

        Thread-safe: Uses thread-safe state and cached data.
        """
        try:
            from datetime import datetime, timedelta

            today = datetime.utcnow()
            # Calculate week start (Monday) and end (Sunday)
            week_start = today - timedelta(days=today.weekday())
            week_end = week_start + timedelta(days=6)
            week_start_str = week_start.strftime('%Y-%m-%d')
            week_end_str = week_end.strftime('%Y-%m-%d')

            # Get real balance from Binance
            real_balance = self.binance_account.get_balance()
            current_equity = real_balance.get('total_balance', self.equity)

            # Initialize stats
            total_trades = 0
            winning_trades = 0
            losing_trades = 0
            total_pnl = 0.0
            daily_pnls = {}
            max_drawdown_pct = 0.0

            if hasattr(self, 'multi_agent_analyzer') and self.multi_agent_analyzer:
                memories = self.multi_agent_analyzer.decision_memory

                # Filter memories for this week
                for m in memories:
                    ts = m.get('timestamp', '')[:10]  # YYYY-MM-DD
                    if ts >= week_start_str and ts <= week_end_str:
                        pnl = m.get('pnl', 0)
                        if pnl != 0:
                            total_trades += 1
                            total_pnl += pnl
                            if pnl > 0:
                                winning_trades += 1
                            else:
                                losing_trades += 1

                            # Track daily PnL
                            if ts not in daily_pnls:
                                daily_pnls[ts] = 0.0
                            daily_pnls[ts] += pnl

            # Calculate best/worst days
            best_day = {'date': 'N/A', 'pnl': 0.0}
            worst_day = {'date': 'N/A', 'pnl': 0.0}
            daily_breakdown = []

            for date, pnl in sorted(daily_pnls.items()):
                daily_breakdown.append({'date': date, 'pnl': pnl})
                if pnl > best_day['pnl']:
                    best_day = {'date': date, 'pnl': pnl}
                if pnl < worst_day['pnl']:
                    worst_day = {'date': date, 'pnl': pnl}

            # Calculate averages
            days_with_trades = len(daily_pnls)
            avg_daily_pnl = total_pnl / days_with_trades if days_with_trades > 0 else 0.0

            # Calculate PnL percentage
            starting_equity = getattr(self, '_weekly_starting_equity', current_equity)
            pnl_pct = ((current_equity - starting_equity) / starting_equity * 100) if starting_equity > 0 else 0.0

            summary_data = {
                'week_start': week_start_str,
                'week_end': week_end_str,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'total_pnl': total_pnl,
                'total_pnl_pct': pnl_pct,
                'best_day': best_day,
                'worst_day': worst_day,
                'avg_daily_pnl': avg_daily_pnl,
                'starting_equity': starting_equity,
                'ending_equity': current_equity,
                'max_drawdown_pct': max_drawdown_pct,
                'daily_breakdown': daily_breakdown,
            }

            if self.telegram_bot:
                msg = self.telegram_bot.format_weekly_summary(summary_data)
            else:
                # Fallback simple format
                msg = f"📊 Weekly Summary ({week_start_str} ~ {week_end_str})\n"
                msg += f"Trades: {total_trades} (W: {winning_trades}, L: {losing_trades})\n"
                msg += f"PnL: ${total_pnl:+,.2f} ({pnl_pct:+.2f}%)\n"
                msg += f"Equity: ${current_equity:,.2f}"

            return {
                'success': True,
                'message': msg
            }
        except Exception as e:
            self.log.error(f"Error in _cmd_weekly_summary: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _check_scheduled_summaries(self):
        """
        Check if daily/weekly summaries need to be sent (v3.13).

        Called from on_timer. Checks current UTC time against configured schedule.
        Uses date tracking to avoid duplicate sends.
        """
        if not self.telegram_bot or not self.enable_telegram:
            return

        try:
            from datetime import datetime

            now = datetime.utcnow()
            current_hour = now.hour
            current_weekday = now.weekday()  # 0=Monday, 6=Sunday
            today_str = now.strftime('%Y-%m-%d')
            week_str = now.strftime('%Y-W%W')  # Year-Week format

            # Check daily summary
            if getattr(self, 'telegram_auto_daily', False):
                daily_hour = getattr(self, 'telegram_daily_hour_utc', 0)

                # Send at the configured hour, once per day
                if current_hour == daily_hour:
                    last_daily = getattr(self, '_last_daily_summary_date', None)
                    if last_daily != today_str:
                        self.log.info(f"📊 Sending scheduled daily summary...")
                        result = self._cmd_daily_summary()
                        if result.get('success') and result.get('message'):
                            self.telegram_bot.send_message_sync(result['message'])
                            self._last_daily_summary_date = today_str
                            self.log.info("✅ Daily summary sent")
                        else:
                            self.log.warning(f"Failed to generate daily summary: {result.get('error')}")

            # Check weekly summary
            if getattr(self, 'telegram_auto_weekly', False):
                weekly_day = getattr(self, 'telegram_weekly_day', 0)  # 0=Monday
                daily_hour = getattr(self, 'telegram_daily_hour_utc', 0)

                # Send on the configured day at the configured hour
                if current_weekday == weekly_day and current_hour == daily_hour:
                    last_weekly = getattr(self, '_last_weekly_summary_date', None)
                    if last_weekly != week_str:
                        self.log.info(f"📊 Sending scheduled weekly summary...")
                        result = self._cmd_weekly_summary()
                        if result.get('success') and result.get('message'):
                            self.telegram_bot.send_message_sync(result['message'])
                            self._last_weekly_summary_date = week_str
                            self.log.info("✅ Weekly summary sent")
                        else:
                            self.log.warning(f"Failed to generate weekly summary: {result.get('error')}")

        except Exception as e:
            self.log.warning(f"Error checking scheduled summaries: {e}")
