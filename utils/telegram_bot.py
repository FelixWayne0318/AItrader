"""
Telegram Bot for Trading Notifications

Provides real-time notifications for trading signals, order fills,
position updates, and system status via Telegram.
"""

import asyncio
import logging
import concurrent.futures
from typing import Optional, Dict, Any
from datetime import datetime

try:
    from telegram import Bot
    from telegram.error import TelegramError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Bot = None
    TelegramError = Exception


class TelegramBot:
    """
    Telegram Bot for sending trading notifications.
    
    Features:
    - Send formatted trading signals
    - Send order fill notifications
    - Send position updates
    - Send error/warning alerts
    - Async message sending
    - Rate limiting support
    """
    
    def __init__(
        self,
        token: str,
        chat_id: str,
        logger: Optional[logging.Logger] = None,
        enabled: bool = True,
        message_timeout: float = 30.0
    ):
        """
        Initialize Telegram Bot.

        Parameters
        ----------
        token : str
            Telegram Bot token from @BotFather
        chat_id : str
            Telegram chat ID to send messages to
        logger : Optional[logging.Logger]
            Logger instance for logging
        enabled : bool
            Whether the bot is enabled (default: True)
        message_timeout : float
            Timeout for sending messages (seconds), default: 30.0
        """
        if not TELEGRAM_AVAILABLE:
            raise ImportError(
                "python-telegram-bot is not installed. "
                "Install it with: pip install python-telegram-bot"
            )

        self.token = token
        self.chat_id = chat_id
        self.logger = logger or logging.getLogger(__name__)
        self.enabled = enabled
        self.message_timeout = message_timeout

        # Initialize bot
        try:
            self.bot = Bot(token=token)
            self.logger.info("✅ Telegram Bot initialized successfully")
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Telegram Bot: {e}")
            self.enabled = False
            raise

    @staticmethod
    def escape_markdown(text: str) -> str:
        """
        Escape special Markdown characters in text.

        Telegram Markdown uses: _ * [ ] ( ) ~ ` > # + - = | { } . !
        For basic Markdown mode, we only need to escape: _ * ` [
        """
        if not text:
            return text
        # Escape characters that have special meaning in Telegram Markdown
        escape_chars = ['_', '*', '`', '[']
        result = str(text)
        for char in escape_chars:
            result = result.replace(char, '\\' + char)
        return result

    async def send_message(
        self,
        message: str,
        parse_mode: str = 'Markdown',
        disable_notification: bool = False
    ) -> bool:
        """
        Send a text message to Telegram.

        Parameters
        ----------
        message : str
            Message text to send
        parse_mode : str
            Parse mode for formatting (Markdown, HTML, or None)
        disable_notification : bool
            Send silently without notification

        Returns
        -------
        bool
            True if message sent successfully, False otherwise
        """
        if not self.enabled:
            self.logger.debug("Telegram bot is disabled, skipping message")
            return False

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode,
                disable_notification=disable_notification
            )
            self.logger.info(f"📱 Telegram message sent: {message[:50]}...")
            return True

        except TelegramError as e:
            # If parse error, retry without formatting
            if "can't parse" in str(e).lower() or "parse entities" in str(e).lower():
                self.logger.warning(f"⚠️ Markdown parse error, retrying without formatting: {e}")
                try:
                    await self.bot.send_message(
                        chat_id=self.chat_id,
                        text=message,
                        parse_mode=None,  # Send as plain text
                        disable_notification=disable_notification
                    )
                    self.logger.info(f"📱 Telegram message sent (plain text): {message[:50]}...")
                    return True
                except Exception as retry_e:
                    self.logger.error(f"❌ Failed to send even without formatting: {retry_e}")
                    return False
            else:
                self.logger.error(f"❌ Telegram error: {e}")
                return False
        except Exception as e:
            self.logger.error(f"❌ Failed to send Telegram message: {e}")
            return False
    
    def send_message_sync(self, message: str, **kwargs) -> bool:
        """
        Synchronous method to send Telegram message.

        Uses the `requests` library to call Telegram API directly.
        This is the recommended approach for sending messages from
        synchronous code, as python-telegram-bot v20+ is fully async
        and not thread-safe.

        Reference: https://github.com/python-telegram-bot/python-telegram-bot/discussions/4096
        """
        if not self.enabled:
            self.logger.debug("Telegram bot is disabled, skipping message")
            return False

        import requests

        parse_mode = kwargs.get('parse_mode', 'Markdown')
        disable_notification = kwargs.get('disable_notification', False)

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            'chat_id': self.chat_id,
            'text': message,
            'disable_notification': disable_notification,
        }
        if parse_mode:
            payload['parse_mode'] = parse_mode

        try:
            response = requests.post(url, json=payload, timeout=self.message_timeout)
            result = response.json()

            if result.get('ok'):
                self.logger.info(f"📱 Telegram message sent: {message[:50]}...")
                return True

            # Handle Markdown parse errors - retry without formatting
            error_desc = result.get('description', '')
            if "can't parse" in error_desc.lower() or "parse entities" in error_desc.lower():
                self.logger.warning(f"⚠️ Markdown parse error, retrying without formatting")
                payload.pop('parse_mode', None)
                response = requests.post(url, json=payload, timeout=self.message_timeout)
                result = response.json()
                if result.get('ok'):
                    return True

            self.logger.error(f"❌ Telegram API error: {error_desc}")
            return False

        except requests.Timeout:
            self.logger.warning(f"⚠️ Telegram message timed out ({self.message_timeout}s)")
            return False
        except Exception as e:
            self.logger.error(f"❌ Error sending Telegram message: {e}")
            return False
    
    # Message Formatters
    
    def format_startup_message(self, instrument_id: str, config: Dict[str, Any]) -> str:
        """Format strategy startup notification."""
        safe_instrument = self.escape_markdown(str(instrument_id))
        return f"""
🚀 *Strategy Started*

📊 *Instrument*: {safe_instrument}
⏰ *Timeframe*: 15 minutes
🕐 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

✅ *Features Enabled*:
• Automatic SL/TP
• Bracket Orders (NautilusTrader Built-in)
• Trailing Stop Loss
• S/R Zone Hard Control (v3.8)
• TradingAgents AI Decision

🎯 Strategy is now monitoring the market...
"""
    
    def format_trade_signal(self, signal_data: Dict[str, Any]) -> str:
        """Format trading signal notification (v2.0 - TradingAgents enhanced)."""
        signal = signal_data.get('signal', 'UNKNOWN')
        confidence = signal_data.get('confidence', 'UNKNOWN')
        price = signal_data.get('price', 0.0)
        timestamp = signal_data.get('timestamp', datetime.now())

        # Technical indicators
        rsi = signal_data.get('rsi', 0.0)
        macd = signal_data.get('macd', 0.0)
        support = signal_data.get('support', 0.0)
        resistance = signal_data.get('resistance', 0.0)

        # AI reasoning
        reasoning = signal_data.get('reasoning', 'No reasoning provided')

        # TradingAgents v3.8: Judge decision and debate info
        winning_side = signal_data.get('winning_side', '')
        debate_summary = signal_data.get('debate_summary', '')

        # Signal emoji
        signal_emoji = "🟢" if signal == "BUY" else "🔴" if signal == "SELL" else "⚪"

        # Build message
        msg = f"""
{signal_emoji} *Trading Signal Detected*

*Signal*: {signal}
*Confidence*: {confidence}
*Price*: ${price:,.2f}
*Time*: {timestamp}

📈 *Technical Indicators*:
• RSI: {rsi:.2f}
• MACD: {macd:.4f}
• Support: ${support:,.2f}
• Resistance: ${resistance:,.2f}

🤖 *AI Analysis*:
{reasoning[:200]}{'...' if len(reasoning) > 200 else ''}
"""

        # Add Judge decision if available (TradingAgents v3.8)
        if winning_side:
            side_emoji = "🐂" if winning_side.upper() == "BULL" else "🐻" if winning_side.upper() == "BEAR" else "⚖️"
            msg += f"\n{side_emoji} *Judge Decision*: {winning_side} wins"

        # Add debate summary if available
        if debate_summary:
            safe_summary = self.escape_markdown(debate_summary[:150])
            msg += f"\n📊 *Debate*: {safe_summary}{'...' if len(debate_summary) > 150 else ''}"

        return msg
    
    def format_order_fill(self, order_data: Dict[str, Any]) -> str:
        """Format order fill notification."""
        side = order_data.get('side', 'UNKNOWN')
        quantity = order_data.get('quantity', 0.0)
        price = order_data.get('price', 0.0)
        order_type = order_data.get('order_type', 'MARKET')
        
        side_emoji = "🟢" if side == "BUY" else "🔴" if side == "SELL" else "⚪"
        
        return f"""
{side_emoji} *Order Filled*

*Side*: {side}
*Type*: {order_type}
*Quantity*: {quantity} BTC
*Price*: ${price:,.2f}
*Total*: ${quantity * price:,.2f}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
    
    def format_position_update(self, position_data: Dict[str, Any]) -> str:
        """Format position update notification (v2.0 - with SL/TP info)."""
        action = position_data.get('action', 'UPDATE')  # OPENED, CLOSED, UPDATE
        side = position_data.get('side', 'UNKNOWN')
        quantity = position_data.get('quantity', 0.0)
        entry_price = position_data.get('entry_price', 0.0)
        current_price = position_data.get('current_price', 0.0)
        pnl = position_data.get('pnl', 0.0)
        pnl_pct = position_data.get('pnl_pct', 0.0)

        # Risk management info (v2.0)
        sl_price = position_data.get('sl_price')
        tp_price = position_data.get('tp_price')

        if action == "OPENED":
            emoji = "📈" if side == "LONG" else "📉"
            title = "Position Opened"
        elif action == "CLOSED":
            emoji = "✅" if pnl >= 0 else "❌"
            title = "Position Closed"
        else:
            emoji = "📊"
            title = "Position Update"

        pnl_emoji = "🟢" if pnl >= 0 else "🔴"

        message = f"""
{emoji} *{title}*

*Side*: {side}
*Quantity*: {quantity} BTC
*Entry Price*: ${entry_price:,.2f}
*Current Price*: ${current_price:,.2f}
"""

        # Add SL/TP for OPENED positions (v2.0)
        if action == "OPENED":
            if sl_price:
                sl_pct = ((sl_price / entry_price) - 1) * 100 if entry_price > 0 else 0
                message += f"🛡️ *Stop Loss*: ${sl_price:,.2f} ({sl_pct:+.2f}%)\n"
            if tp_price:
                tp_pct = ((tp_price / entry_price) - 1) * 100 if entry_price > 0 else 0
                message += f"🎯 *Take Profit*: ${tp_price:,.2f} ({tp_pct:+.2f}%)\n"

        if action == "CLOSED" or action == "UPDATE":
            message += f"""
{pnl_emoji} *P&L*: ${pnl:,.2f} ({pnl_pct:+.2f}%)
"""

        message += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"

        return message
    
    def format_error_alert(self, error_data: Dict[str, Any]) -> str:
        """Format error/warning notification."""
        level = error_data.get('level', 'ERROR')  # ERROR, WARNING, CRITICAL
        message = self.escape_markdown(str(error_data.get('message', 'Unknown error')))
        context = error_data.get('context', '')

        if level == "CRITICAL":
            emoji = "🚨"
        elif level == "WARNING":
            emoji = "⚠️"
        else:
            emoji = "❌"

        formatted = f"""
{emoji} *{level}*

{message}
"""

        if context:
            formatted += f"\n*Context*: {self.escape_markdown(str(context))}\n"
        
        formatted += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        
        return formatted

    # Note: format_partial_tp_notification was removed as enable_partial_tp is disabled
    # and the feature is not implemented. If partial TP is implemented in the future,
    # add a new formatter here.

    def format_trailing_stop_update(self, ts_data: Dict[str, Any]) -> str:
        """Format trailing stop update notification."""
        old_sl = ts_data.get('old_sl_price', 0.0)
        new_sl = ts_data.get('new_sl_price', 0.0)
        current_price = ts_data.get('current_price', 0.0)
        profit_pct = ts_data.get('profit_pct', 0.0)
        
        return f"""
🔄 *Trailing Stop Updated*

*Current Price*: ${current_price:,.2f}
*Profit*: +{profit_pct*100:.1f}%

*Stop Loss*:
  Old: ${old_sl:,.2f}
  New: ${new_sl:,.2f} ⬆️

🛡️ Stop loss moved up to lock in more profit!

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""

    def format_heartbeat_message(self, heartbeat_data: Dict[str, Any]) -> str:
        """
        Format heartbeat status message (v3.0 - TradingAgents enhanced).

        统一格式，包含 v3.6/3.7/3.8 指标数据。
        """
        # 安全获取所有值，确保不为 None
        signal = heartbeat_data.get('signal') or 'PENDING'
        confidence = heartbeat_data.get('confidence') or 'N/A'
        price = heartbeat_data.get('price') or 0
        rsi = heartbeat_data.get('rsi') or 0
        timer_count = heartbeat_data.get('timer_count') or 0
        equity = heartbeat_data.get('equity') or 0
        uptime_str = heartbeat_data.get('uptime_str') or 'N/A'

        # 持仓信息（统一显示，无则显示 0 或 无）
        position_side = heartbeat_data.get('position_side') or '无'
        entry_price = heartbeat_data.get('entry_price') or 0
        position_size = heartbeat_data.get('position_size') or 0
        position_pnl_pct = heartbeat_data.get('position_pnl_pct') or 0

        # v3.6 MTF Order Flow (optional)
        order_flow = heartbeat_data.get('order_flow') or {}
        buy_ratio = order_flow.get('buy_ratio')
        cvd_trend = order_flow.get('cvd_trend')

        # v3.6 Derivatives (optional)
        derivatives = heartbeat_data.get('derivatives') or {}
        funding_rate = derivatives.get('funding_rate')
        oi_change_pct = derivatives.get('oi_change_pct')

        # v3.7 Order Book (optional)
        order_book = heartbeat_data.get('order_book') or {}
        weighted_obi = order_book.get('weighted_obi')
        obi_trend = order_book.get('obi_trend')

        # v3.8 S/R Zone (optional)
        sr_zone = heartbeat_data.get('sr_zone') or {}
        nearest_support = sr_zone.get('nearest_support')
        nearest_resistance = sr_zone.get('nearest_resistance')
        block_long = sr_zone.get('block_long', False)
        block_short = sr_zone.get('block_short', False)

        # Signal emoji
        signal_emoji = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '⚪'}.get(signal, '❓')

        # Position emoji
        if position_side == 'LONG':
            pos_emoji = '🟢 LONG'
        elif position_side == 'SHORT':
            pos_emoji = '🔴 SHORT'
        else:
            pos_emoji = '⚪ 无'

        # PnL emoji
        pnl_emoji = '📈' if position_pnl_pct > 0 else '📉' if position_pnl_pct < 0 else '➖'

        # 构建消息 - 统一格式
        msg = f"💓 *Heartbeat #{timer_count}*\n"
        msg += f"━━━━━━━━━━━━━━━━\n"
        msg += f"💵 价格: ${price:,.2f}\n"
        msg += f"📈 RSI: {rsi:.1f}\n"
        msg += f"🎯 信号: {signal_emoji} {signal} ({confidence})\n"

        # v3.8 S/R Zone Hard Control (if available)
        if nearest_support is not None or nearest_resistance is not None:
            msg += f"━━━━━━━━━━━━━━━━\n"
            msg += f"🎯 *S/R Zone (v3.8)*\n"
            if nearest_support is not None:
                dist_sup = ((price - nearest_support) / price * 100) if price > 0 else 0
                msg += f"  支撑: ${nearest_support:,.2f} ({dist_sup:+.2f}%)\n"
            if nearest_resistance is not None:
                dist_res = ((nearest_resistance - price) / price * 100) if price > 0 else 0
                msg += f"  阻力: ${nearest_resistance:,.2f} (+{dist_res:.2f}%)\n"
            # Block status
            if block_long or block_short:
                block_str = []
                if block_long:
                    block_str.append("🚫 LONG")
                if block_short:
                    block_str.append("🚫 SHORT")
                msg += f"  风控: {' | '.join(block_str)}\n"

        # v3.6 Order Flow (if available)
        if buy_ratio is not None or cvd_trend:
            msg += f"━━━━━━━━━━━━━━━━\n"
            msg += f"📊 *订单流 (v3.6)*\n"
            if buy_ratio is not None:
                ratio_emoji = "🟢" if buy_ratio > 0.55 else "🔴" if buy_ratio < 0.45 else "⚪"
                msg += f"  买入比: {ratio_emoji} {buy_ratio*100:.1f}%\n"
            if cvd_trend:
                trend_emoji = "📈" if cvd_trend == "RISING" else "📉" if cvd_trend == "FALLING" else "➖"
                msg += f"  CVD: {trend_emoji} {cvd_trend}\n"

        # v3.6 Derivatives (if available)
        if funding_rate is not None or oi_change_pct is not None:
            if buy_ratio is None and cvd_trend is None:
                msg += f"━━━━━━━━━━━━━━━━\n"
            msg += f"📉 *衍生品 (v3.6)*\n"
            if funding_rate is not None:
                fr_emoji = "🔴" if funding_rate > 0.01 else "🟢" if funding_rate < -0.01 else "⚪"
                msg += f"  资金费: {fr_emoji} {funding_rate*100:.4f}%\n"
            if oi_change_pct is not None:
                oi_emoji = "📈" if oi_change_pct > 5 else "📉" if oi_change_pct < -5 else "➖"
                msg += f"  OI变化: {oi_emoji} {oi_change_pct:+.2f}%\n"

        # v3.7 Order Book (if available)
        if weighted_obi is not None:
            msg += f"━━━━━━━━━━━━━━━━\n"
            msg += f"📖 *订单簿 (v3.7)*\n"
            obi_emoji = "🟢" if weighted_obi > 0.1 else "🔴" if weighted_obi < -0.1 else "⚪"
            msg += f"  OBI: {obi_emoji} {weighted_obi:+.3f}\n"
            if obi_trend:
                trend_emoji = "📈" if obi_trend == "STRENGTHENING" else "📉" if obi_trend == "WEAKENING" else "➖"
                msg += f"  趋势: {trend_emoji} {obi_trend}\n"

        msg += f"━━━━━━━━━━━━━━━━\n"
        msg += f"💰 持仓: {pos_emoji}\n"
        msg += f"📍 入场: ${entry_price:,.2f}\n"
        msg += f"📦 数量: {position_size:.4f}\n"
        msg += f"💹 盈亏: {pnl_emoji} {position_pnl_pct:+.2f}%\n"
        msg += f"━━━━━━━━━━━━━━━━\n"
        msg += f"🏦 余额: ${equity:,.2f}\n"
        msg += f"⏱ 运行: {uptime_str}\n"
        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"

        return msg

    async def test_connection(self) -> bool:
        """
        Test Telegram bot connection.
        
        Returns
        -------
        bool
            True if connection successful, False otherwise
        """
        try:
            me = await self.bot.get_me()
            self.logger.info(f"✅ Connected to Telegram as @{me.username}")
            return True
        except Exception as e:
            self.logger.error(f"❌ Failed to connect to Telegram: {e}")
            return False
    
    # ===== Remote Control Command Formatters =====
    
    def format_status_response(self, status_info: Dict[str, Any]) -> str:
        """
        Format strategy status response for /status command.
        
        Parameters
        ----------
        status_info : dict
            Status information containing:
            - is_running: bool
            - is_paused: bool
            - instrument_id: str
            - current_price: float
            - equity: float
            - unrealized_pnl: float
            - last_signal: str
            - last_signal_time: str
            - uptime: str
        """
        is_running = status_info.get('is_running', False)
        is_paused = status_info.get('is_paused', False)
        
        # Status emoji
        if not is_running:
            status_emoji = "🔴"
            status_text = "STOPPED"
        elif is_paused:
            status_emoji = "⏸️"
            status_text = "PAUSED"
        else:
            status_emoji = "🟢"
            status_text = "RUNNING"
        
        msg = f"{status_emoji} *Strategy Status*\n\n"
        msg += f"*Status*: {status_text}\n"
        msg += f"*Instrument*: {self.escape_markdown(str(status_info.get('instrument_id', 'N/A')))}\n"
        msg += f"*Current Price*: ${status_info.get('current_price', 0):,.2f}\n"
        msg += f"*Equity*: ${status_info.get('equity', 0):,.2f}\n"
        
        pnl = status_info.get('unrealized_pnl', 0)
        pnl_emoji = "📈" if pnl > 0 else "📉" if pnl < 0 else "➖"
        msg += f"*Unrealized P&L*: {pnl_emoji} ${pnl:,.2f}\n\n"
        
        msg += f"*Last Signal*: {self.escape_markdown(str(status_info.get('last_signal', 'N/A')))}\n"
        msg += f"*Signal Time*: {self.escape_markdown(str(status_info.get('last_signal_time', 'N/A')))}\n"
        msg += f"*Uptime*: {self.escape_markdown(str(status_info.get('uptime', 'N/A')))}\n"
        
        return msg
    
    def format_position_response(self, position_info: Dict[str, Any]) -> str:
        """
        Format position information response for /position command.
        
        Parameters
        ----------
        position_info : dict
            Position information containing:
            - has_position: bool
            - side: LONG/SHORT
            - quantity: float
            - entry_price: float
            - current_price: float
            - unrealized_pnl: float
            - pnl_pct: float
            - sl_price: float (optional)
            - tp_price: float (optional)
        """
        if not position_info.get('has_position', False):
            return "ℹ️ *No Open Position*\n\nCurrently not holding any position."
        
        side = position_info.get('side', 'UNKNOWN')
        side_emoji = "🟢" if side == "LONG" else "🔴" if side == "SHORT" else "⚪"
        
        msg = f"{side_emoji} *Open Position*\n\n"
        msg += f"*Side*: {side}\n"
        msg += f"*Quantity*: {position_info.get('quantity', 0):.4f}\n"
        msg += f"*Entry Price*: ${position_info.get('entry_price', 0):,.2f}\n"
        msg += f"*Current Price*: ${position_info.get('current_price', 0):,.2f}\n\n"
        
        pnl = position_info.get('unrealized_pnl', 0)
        pnl_pct = position_info.get('pnl_pct', 0)
        pnl_emoji = "📈" if pnl > 0 else "📉" if pnl < 0 else "➖"
        msg += f"*Unrealized P&L*: {pnl_emoji} ${pnl:,.2f} ({pnl_pct:+.2f}%)\n\n"
        
        # Add SL/TP if available
        sl_price = position_info.get('sl_price')
        tp_price = position_info.get('tp_price')
        
        if sl_price:
            msg += f"🛡️ *Stop Loss*: ${sl_price:,.2f}\n"
        if tp_price:
            msg += f"🎯 *Take Profit*: ${tp_price:,.2f}\n"
        
        return msg
    
    def format_pause_response(self, success: bool, message: str = "") -> str:
        """Format response for /pause command."""
        if success:
            return "⏸️ *Strategy Paused*\n\nTrading has been paused. No new orders will be placed.\nUse /resume to continue trading."
        else:
            return f"❌ *Failed to Pause*\n\n{message}"
    
    def format_resume_response(self, success: bool, message: str = "") -> str:
        """Format response for /resume command."""
        if success:
            return "▶️ *Strategy Resumed*\n\nTrading has been resumed. Strategy is now active."
        else:
            return f"❌ *Failed to Resume*\n\n{message}"
    
    def format_help_response(self) -> str:
        """Format help message with available commands."""
        msg = "🤖 *Available Commands*\n\n"
        msg += "*Query Commands*:\n"
        msg += "• `/status` - View strategy status\n"
        msg += "• `/position` - View current position\n"
        msg += "• `/help` - Show this help message\n\n"
        msg += "*Control Commands*:\n"
        msg += "• `/pause` - Pause trading (no new orders)\n"
        msg += "• `/resume` - Resume trading\n\n"
        msg += "💡 _Commands are case-insensitive_\n"
        return msg


# Convenience function for quick testing
async def test_telegram_bot(token: str, chat_id: str) -> bool:
    """
    Quick test function for Telegram bot.
    
    Parameters
    ----------
    token : str
        Bot token from @BotFather
    chat_id : str
        Chat ID to send test message to
    
    Returns
    -------
    bool
        True if test successful
    """
    try:
        bot = TelegramBot(token=token, chat_id=chat_id)
        
        # Test connection
        if not await bot.test_connection():
            return False
        
        # Send test message
        success = await bot.send_message(
            "🧪 *Test Message*\n\n"
            "Telegram bot is working correctly!\n"
            "Ready to send trading notifications."
        )
        
        return success
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    """
    Standalone test mode.
    
    Usage:
        python telegram_bot.py <token> <chat_id>
    """
    import sys
    
    if len(sys.argv) != 3:
        print("Usage: python telegram_bot.py <token> <chat_id>")
        sys.exit(1)
    
    token = sys.argv[1]
    chat_id = sys.argv[2]
    
    # Run test
    result = asyncio.run(test_telegram_bot(token, chat_id))
    
    if result:
        print("✅ Test successful!")
        sys.exit(0)
    else:
        print("❌ Test failed!")
        sys.exit(1)

