"""
Live Trading Entrypoint for DeepSeek AI Strategy

Runs the DeepSeek AI strategy on Binance Futures (BTCUSDT-PERP) with live market data.
"""

import os
import sys
import argparse
import yaml
from decimal import Decimal
from pathlib import Path

# =============================================================================
# CRITICAL: Apply patches BEFORE importing NautilusTrader
# This fixes Binance enum compatibility issues (e.g., POSITION_RISK_CONTROL)
# =============================================================================
# Ensure project root is in path for patches import
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from patches.binance_enums import apply_all_patches
apply_all_patches()
# =============================================================================

from dotenv import load_dotenv

from utils.config_manager import ConfigManager

from nautilus_trader.adapters.binance.common.enums import BinanceAccountType
from nautilus_trader.adapters.binance.config import BinanceDataClientConfig, BinanceExecClientConfig
from nautilus_trader.adapters.binance.factories import BinanceLiveDataClientFactory, BinanceLiveExecClientFactory
from nautilus_trader.config import InstrumentProviderConfig, LiveExecEngineConfig, LoggingConfig, TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import TraderId, InstrumentId
from nautilus_trader.trading.config import ImportableStrategyConfig

from strategy.deepseek_strategy import DeepSeekAIStrategy, DeepSeekAIStrategyConfig


# Load environment variables
# Priority: 1. ~/.env.aitrader (permanent) 2. .env (local/symlink)
env_permanent = Path.home() / ".env.aitrader"
env_local = project_root / ".env"

if env_permanent.exists():
    load_dotenv(env_permanent)
    print(f"[CONFIG] Loaded environment from {env_permanent}")
elif env_local.exists():
    load_dotenv(env_local)
    print(f"[CONFIG] Loaded environment from {env_local}")
else:
    load_dotenv()  # Try default locations
    print("[CONFIG] Warning: No .env file found, using system environment")


def load_yaml_config() -> dict:
    """
    Load strategy configuration from YAML file.

    Returns
    -------
    dict
        Configuration dictionary from YAML, or empty dict if loading fails
    """
    config_path = Path(__file__).parent / "configs" / "strategy_config.yaml"
    if not config_path.exists():
        print(f"[CONFIG] Warning: {config_path} not found, using defaults")
        return {}

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            if config is None:
                print(f"[CONFIG] Warning: {config_path} is empty, using defaults")
                return {}
            return config
    except yaml.YAMLError as e:
        print(f"[CONFIG] Error parsing YAML config: {e}")
        raise
    except Exception as e:
        print(f"[CONFIG] Error loading config file: {e}")
        raise


def _strip_env_comment(value: str) -> str:
    """
    Safely strip inline comments from environment variable value.

    Only strips comments that are clearly separated (space + #).
    This preserves values that legitimately contain '#' (like API keys).

    Examples:
        "abc123"       -> "abc123"       (no comment)
        "abc#123"      -> "abc#123"      (# is part of value, no space before)
        "abc123 #note" -> "abc123"       (space+# indicates comment)
        "abc # test"   -> "abc"          (space+# indicates comment)
    """
    # Only strip if there's " #" (space followed by #)
    if ' #' in value:
        value = value.split(' #')[0]
    return value.strip()


def get_env_float(key: str, default: str) -> float:
    """
    Safely get float environment variable, removing any inline comments.
    """
    value = os.getenv(key, default)
    value = _strip_env_comment(value)
    return float(value)


def get_env_str(key: str, default: str) -> str:
    """
    Safely get string environment variable, removing any inline comments.
    """
    value = os.getenv(key, default)
    return _strip_env_comment(value)


def get_env_int(key: str, default: str) -> int:
    """
    Safely get integer environment variable, removing any inline comments.
    """
    value = os.getenv(key, default)
    value = _strip_env_comment(value)
    return int(value)


def get_strategy_config(config_manager: ConfigManager) -> DeepSeekAIStrategyConfig:
    """
    Build strategy configuration from ConfigManager.

    Parameters
    ----------
    config_manager : ConfigManager
        Configuration manager instance

    Returns
    -------
    DeepSeekAIStrategyConfig
        Strategy configuration
    """
    # Get API keys from environment (only sensitive info allowed in env vars)
    deepseek_api_key = get_env_str('DEEPSEEK_API_KEY', '')
    if not deepseek_api_key:
        raise ValueError("DEEPSEEK_API_KEY not found in environment variables")

    # Get configuration values from ConfigManager ONLY (no env var overrides for business params)
    # Reference: CLAUDE.md - 配置分层架构原则
    equity = config_manager.get('capital', 'equity', default=1000)
    leverage = config_manager.get('capital', 'leverage', default=5)
    base_position = config_manager.get('position', 'base_usdt_amount', default=100)

    # Get timeframe from config (environment-specific via {env}.yaml)
    timeframe = config_manager.get('trading', 'timeframe', default='15m')

    # Debug output
    print(f"[CONFIG] Equity: {equity}")
    print(f"[CONFIG] Base Position: {base_position}")
    print(f"[CONFIG] Timeframe: {timeframe}")

    # Parse timeframe to bar specification
    timeframe_to_bar_spec = {
        '1m': '1-MINUTE-LAST',
        '5m': '5-MINUTE-LAST',
        '15m': '15-MINUTE-LAST',
        '1h': '1-HOUR-LAST',
        '4h': '4-HOUR-LAST',
        '1d': '1-DAY-LAST',
    }
    bar_spec = timeframe_to_bar_spec.get(timeframe, '15-MINUTE-LAST')

    # Get instrument from config
    instrument_id = config_manager.get('trading', 'instrument_id', default='BTCUSDT-PERP.BINANCE')
    symbol = instrument_id.split('.')[0]  # Extract symbol from instrument_id
    final_bar_type = f"{symbol}.BINANCE-{bar_spec}-EXTERNAL"

    return DeepSeekAIStrategyConfig(
        instrument_id=instrument_id,
        bar_type=final_bar_type,

        # Capital
        equity=equity,
        leverage=leverage,
        use_real_balance_as_equity=config_manager.get('capital', 'use_real_balance_as_equity', default=True),

        # Position sizing (all from ConfigManager, no env var overrides)
        base_usdt_amount=base_position,
        high_confidence_multiplier=config_manager.get('position', 'high_confidence_multiplier', default=1.5),
        medium_confidence_multiplier=config_manager.get('position', 'medium_confidence_multiplier', default=1.0),
        low_confidence_multiplier=config_manager.get('position', 'low_confidence_multiplier', default=0.5),
        max_position_ratio=config_manager.get('position', 'max_position_ratio', default=0.30),
        trend_strength_multiplier=config_manager.get('position', 'trend_strength_multiplier', default=1.2),
        min_trade_amount=config_manager.get('position', 'min_trade_amount', default=0.001),

        # Technical indicators (all from ConfigManager)
        # For 1m timeframe, use development.yaml with shorter periods
        sma_periods=config_manager.get('indicators', 'sma_periods', default=[5, 20, 50]),
        rsi_period=config_manager.get('indicators', 'rsi_period', default=14),
        macd_fast=config_manager.get('indicators', 'macd_fast', default=12),
        macd_slow=config_manager.get('indicators', 'macd_slow', default=26),
        bb_period=config_manager.get('indicators', 'bb_period', default=20),
        bb_std=config_manager.get('indicators', 'bb_std', default=2.0),
        volume_ma_period=config_manager.get('indicators', 'volume_ma_period', default=20),
        support_resistance_lookback=config_manager.get('indicators', 'support_resistance_lookback', default=20),

        # AI
        deepseek_api_key=deepseek_api_key,
        deepseek_model=config_manager.get('ai', 'deepseek', 'model', default='deepseek-chat'),
        deepseek_temperature=config_manager.get('ai', 'deepseek', 'temperature', default=0.3),
        deepseek_max_retries=config_manager.get('ai', 'deepseek', 'max_retries', default=2),
        deepseek_retry_delay=config_manager.get('ai', 'deepseek', 'retry_delay', default=1.0),
        deepseek_signal_history_count=config_manager.get('ai', 'signal', 'history_count', default=30),
        debate_rounds=config_manager.get('ai', 'multi_agent', 'debate_rounds', default=2),
        multi_agent_retry_delay=config_manager.get('ai', 'multi_agent', 'retry_delay', default=1.0),
        multi_agent_json_parse_max_retries=config_manager.get('ai', 'multi_agent', 'json_parse_max_retries', default=2),

        # Sentiment
        sentiment_enabled=config_manager.get('sentiment', 'enabled', default=True),
        sentiment_lookback_hours=config_manager.get('sentiment', 'lookback_hours', default=4),
        # Set sentiment timeframe based on bar timeframe (default to 15m)
        sentiment_timeframe="1m" if timeframe == "1m" else ("5m" if timeframe == "5m" else config_manager.get('sentiment', 'timeframe', default='15m')),

        # Risk (all from ConfigManager, no env var overrides)
        min_confidence_to_trade=config_manager.get('risk', 'min_confidence_to_trade', default='MEDIUM'),
        allow_reversals=config_manager.get('risk', 'allow_reversals', default=True),
        require_high_confidence_for_reversal=config_manager.get('risk', 'require_high_confidence_for_reversal', default=False),
        rsi_extreme_threshold_upper=config_manager.get('risk', 'rsi_extreme_threshold_upper', default=70.0),
        rsi_extreme_threshold_lower=config_manager.get('risk', 'rsi_extreme_threshold_lower', default=30.0),
        rsi_extreme_multiplier=config_manager.get('risk', 'rsi_extreme_multiplier', default=0.7),

        # Stop Loss & Take Profit (from ConfigManager)
        enable_auto_sl_tp=config_manager.get('risk', 'stop_loss', 'enabled', default=True),
        sl_use_support_resistance=config_manager.get('risk', 'stop_loss', 'use_support_resistance', default=True),
        sl_buffer_pct=config_manager.get('risk', 'stop_loss', 'buffer_pct', default=0.001),
        tp_high_confidence_pct=config_manager.get('risk', 'take_profit', 'high_confidence_pct', default=0.03),
        tp_medium_confidence_pct=config_manager.get('risk', 'take_profit', 'medium_confidence_pct', default=0.02),
        tp_low_confidence_pct=config_manager.get('risk', 'take_profit', 'low_confidence_pct', default=0.01),

        # Trailing Stop (from ConfigManager)
        enable_trailing_stop=config_manager.get('risk', 'trailing_stop', 'enabled', default=True),
        trailing_activation_pct=config_manager.get('risk', 'trailing_stop', 'activation_pct', default=0.01),
        trailing_distance_pct=config_manager.get('risk', 'trailing_stop', 'distance_pct', default=0.005),
        trailing_update_threshold_pct=config_manager.get('risk', 'trailing_stop', 'update_threshold_pct', default=0.002),

        # OCO (from ConfigManager)
        enable_oco=config_manager.get('risk', 'oco', 'enabled', default=True),

        # [LEGACY - 不再使用] Multi-Agent Divergence Handling
        # 保留用于向后兼容，但不再生效
        # Support both old (strategy.risk.*) and new (ai.signal.*) paths via PATH_ALIASES
        skip_on_divergence=config_manager.get('ai', 'signal', 'skip_on_divergence', default=True),
        use_confidence_fusion=config_manager.get('ai', 'signal', 'use_confidence_fusion', default=True),

        # Execution
        position_adjustment_threshold=config_manager.get('execution', 'position_adjustment_threshold', default=0.001),

        # Timing (from ConfigManager, environment-specific via {env}.yaml)
        timer_interval_sec=config_manager.get('timing', 'timer_interval_sec', default=900),

        # Telegram Notifications
        enable_telegram=config_manager.get('telegram', 'enabled', default=False),
        telegram_bot_token=get_env_str('TELEGRAM_BOT_TOKEN', ''),
        telegram_chat_id=get_env_str('TELEGRAM_CHAT_ID', ''),
        telegram_notify_signals=config_manager.get('telegram', 'notify_signals', default=True),
        telegram_notify_fills=config_manager.get('telegram', 'notify_fills', default=True),
        telegram_notify_positions=config_manager.get('telegram', 'notify_positions', default=True),
        telegram_notify_errors=config_manager.get('telegram', 'notify_errors', default=True),

        # Network configuration
        network_telegram_startup_delay=config_manager.get('network', 'telegram', 'startup_delay', default=5.0),
        network_telegram_polling_max_retries=config_manager.get('network', 'telegram', 'polling_max_retries', default=3),
        network_telegram_polling_base_delay=config_manager.get('network', 'telegram', 'polling_base_delay', default=10.0),
        network_binance_recv_window=config_manager.get('network', 'binance', 'recv_window', default=5000),
        network_binance_balance_cache_ttl=config_manager.get('network', 'binance', 'balance_cache_ttl', default=5.0),
        network_bar_persistence_max_limit=config_manager.get('network', 'bar_persistence', 'max_limit', default=1500),
        network_bar_persistence_timeout=config_manager.get('network', 'bar_persistence', 'timeout', default=10.0),
        network_oco_manager_socket_timeout=config_manager.get('network', 'oco_manager', 'socket_timeout', default=5.0),
        network_oco_manager_socket_connect_timeout=config_manager.get('network', 'oco_manager', 'socket_connect_timeout', default=5.0),
        sentiment_timeout=config_manager.get('sentiment', 'timeout', default=10.0),
    )


def get_binance_config() -> tuple:
    """
    Build Binance data and execution client configs.

    Returns
    -------
    tuple
        (data_config, exec_config)
    """
    # Get API credentials
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')

    if not api_key or not api_secret:
        raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET required in .env")

    # CRITICAL: Use load_all=True for proper instrument initialization
    # NautilusTrader 1.221.0 has fixed non-ASCII symbol issues
    # The binance_positions.py patch provides additional filtering if needed

    # Data client config
    data_config = BinanceDataClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        account_type=BinanceAccountType.USDT_FUTURES,  # Binance Futures
        testnet=False,  # Set to True for testnet
        instrument_provider=InstrumentProviderConfig(
            load_all=True,  # Load all instruments for proper execution
        ),
    )

    # Execution client config
    exec_config = BinanceExecClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        account_type=BinanceAccountType.USDT_FUTURES,
        testnet=False,
        instrument_provider=InstrumentProviderConfig(
            load_all=True,  # Load all instruments for proper execution
        ),
    )

    return data_config, exec_config


def setup_trading_node(config_manager: ConfigManager) -> TradingNodeConfig:
    """
    Configure the NautilusTrader trading node.

    Parameters
    ----------
    config_manager : ConfigManager
        Configuration manager instance

    Returns
    -------
    TradingNodeConfig
        Trading node configuration
    """
    # Get configurations
    strategy_config = get_strategy_config(config_manager)
    data_config, exec_config = get_binance_config()

    # Wrap strategy config in ImportableStrategyConfig
    importable_config = ImportableStrategyConfig(
        strategy_path="strategy.deepseek_strategy:DeepSeekAIStrategy",
        config_path="strategy.deepseek_strategy:DeepSeekAIStrategyConfig",
        config=strategy_config.dict(),
    )

    # Logging configuration (from ConfigManager, environment-specific via {env}.yaml)
    log_level = config_manager.get('logging', 'level', default='INFO')

    # LoggingConfig - only use parameters supported by NautilusTrader 1.202.0
    logging_config = LoggingConfig(
        log_level=log_level,
        log_level_file=log_level,
        log_directory="logs",
        log_file_name="deepseek_trader",
        bypass_logging=False,
    )

    # Trading node config
    config = TradingNodeConfig(
        trader_id=TraderId("DeepSeekTrader-001"),
        logging=logging_config,
        exec_engine=LiveExecEngineConfig(
            reconciliation=True,  # Enable position reconciliation with Binance
            inflight_check_interval_ms=5000,  # Check in-flight orders every 5s
            filter_position_reports=True,  # Filter positions to only known instruments
            filter_unclaimed_external_orders=True,  # Filter unknown external orders
        ),
        # Data clients
        data_clients={
            "BINANCE": data_config,
        },
        # Execution clients
        exec_clients={
            "BINANCE": exec_config,
        },
        # Strategy configs
        strategies=[importable_config],
    )

    return config


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description='AItrader - NautilusTrader DeepSeek Bot')
    parser.add_argument(
        '--env',
        type=str,
        default='production',
        choices=['production', 'development', 'backtest'],
        help='Trading environment (default: production)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode (load config but don\'t start trading)'
    )
    return parser.parse_args()


def main():
    """
    Main entry point for live trading.
    """
    # Parse command-line arguments
    args = parse_args()

    print("=" * 70)
    print("DeepSeek AI Trading Strategy - Live Trading Mode")
    print("=" * 70)
    print(f"Environment: {args.env}")
    print(f"Exchange: Binance Futures (USDT-M)")
    print(f"Strategy: AI-powered with DeepSeek")
    print("=" * 70)

    # Initialize ConfigManager
    print("\n📋 Loading configuration...")
    config_manager = ConfigManager(env=args.env)
    config_dict = config_manager.load()

    # Validate configuration
    if not config_manager.validate():
        print("\n❌ Configuration validation failed:")
        errors = config_manager.get_errors()
        for error in errors:
            print(f"  - {error.field}: {error.message}")
        sys.exit(1)

    print(f"✅ Configuration loaded and validated ({args.env} environment)")

    # Dry run mode - print config summary and exit
    if args.dry_run:
        print("\n" + "=" * 70)
        print("DRY RUN MODE - Configuration Summary")
        print("=" * 70)
        config_manager.print_summary()
        print("\n✅ Dry run complete. Configuration is valid. Exiting.")
        return

    # Get instrument from config
    instrument_id = config_manager.get('trading', 'instrument_id', default='BTCUSDT-PERP.BINANCE')
    print(f"Instrument: {instrument_id}")

    # Safety check
    test_mode = os.getenv('TEST_MODE', 'false').strip().lower() == 'true'
    auto_confirm = os.getenv('AUTO_CONFIRM', 'false').strip().lower() == 'true'

    if test_mode:
        print("⚠️  TEST_MODE=true - This is a simulation, no real orders will be placed")
    else:
        print("🚨 LIVE TRADING MODE - Real orders will be placed!")
        if auto_confirm:
            print("⚠️  AUTO_CONFIRM=true - Skipping user confirmation")
        else:
            response = input("Are you sure you want to continue? (yes/no): ")
            if response.lower() != 'yes':
                print("Exiting...")
                return

    # Build configuration
    print("\n📋 Building trading node configuration...")
    config = setup_trading_node(config_manager)

    print(f"✅ Trader ID: {config.trader_id}")
    print(f"✅ Strategy configured with DeepSeek AI")
    print(f"✅ Binance Futures adapter configured")

    # Create and start trading node
    print("\n🚀 Starting trading node...")
    node = TradingNode(config=config)
    
    # Register Binance factories
    node.add_data_client_factory("BINANCE", BinanceLiveDataClientFactory)
    node.add_exec_client_factory("BINANCE", BinanceLiveExecClientFactory)
    print("✅ Binance factories registered")

    try:
        # Build the node (connects to exchange, loads instruments)
        node.build()
        print("✅ Trading node built successfully")

        # Run the node (this starts strategies and begins event processing)
        print("✅ Starting trading node...")
        print("\n🟢 Strategy is now running. Press Ctrl+C to stop.\n")
        
        # Run the node - this is a blocking call that processes all events
        node.run()

    except KeyboardInterrupt:
        print("\n\n⚠️  Keyboard interrupt received...")

    except Exception as e:
        print(f"\n❌ Error occurred: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Dispose the node to clean up resources
        print("\n🛑 Cleaning up resources...")
        node.dispose()
        print("✅ Resources cleaned up")

        print("\n" + "=" * 70)
        print("Trading session ended")
        print("=" * 70)


if __name__ == "__main__":
    # Run the trading bot (Python path already configured at module level)
    try:
        main()
    except KeyboardInterrupt:
        print("\n✅ Program terminated by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
