"""
Telegram Command Handler for Trading Strategy

Handles incoming Telegram commands for remote control of the trading strategy.

v2.0 Security Improvements (2026-02):
- PIN verification for control commands
- Audit logging for all operations
- Rate limiting to prevent abuse
- Enhanced authorization checks
"""

import asyncio
import logging
import random
import time
import hashlib
from typing import Optional, Callable, Dict, Any
from datetime import datetime, timedelta

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
    from telegram.error import Conflict as TelegramConflict
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Application = None
    CommandHandler = None
    CallbackQueryHandler = None
    MessageHandler = None
    filters = None
    Update = None
    ContextTypes = None
    TelegramConflict = Exception
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None

# Import audit logger (optional, graceful degradation)
try:
    from utils.audit_logger import AuditLogger, AuditEventType, get_audit_logger
    AUDIT_AVAILABLE = True
except ImportError:
    AUDIT_AVAILABLE = False
    AuditLogger = None
    AuditEventType = None
    get_audit_logger = None


class TelegramCommandHandler:
    """
    Handles Telegram commands for strategy control.

    Query Commands (no PIN required):
    - /status: Get strategy status
    - /position: Get current position info
    - /orders: View open orders
    - /history: View recent trade history
    - /risk: View risk metrics
    - /help: Show available commands
    - /menu: Show interactive button menu

    Control Commands (PIN required):
    - /pause: Pause trading
    - /resume: Resume trading
    - /close: Close current position

    Security Features (v2.0):
    - PIN verification for control commands
    - Audit logging for all operations
    - Rate limiting (configurable)
    """

    # Commands that require PIN verification
    CONTROL_COMMANDS = {'pause', 'resume', 'close'}

    def __init__(
        self,
        token: str,
        allowed_chat_ids: list,
        strategy_callback: Callable,
        logger: Optional[logging.Logger] = None,
        startup_delay: float = 5.0,
        polling_max_retries: int = 3,
        polling_base_delay: float = 10.0,
        # v2.0 Security options
        enable_pin: bool = True,
        pin_code: Optional[str] = None,  # If None, auto-generate
        pin_expiry_seconds: int = 60,
        enable_audit: bool = True,
        audit_log_dir: str = "logs/audit",
        rate_limit_per_minute: int = 30,
    ):
        """
        Initialize command handler.

        Parameters
        ----------
        token : str
            Telegram Bot token
        allowed_chat_ids : list
            List of allowed chat IDs (for security)
        strategy_callback : callable
            Callback function to execute commands on strategy
            Signature: callback(command: str, args: dict) -> dict
        logger : logging.Logger, optional
            Logger instance
        startup_delay : float, optional
            Delay after webhook deletion (seconds), default: 5.0
        polling_max_retries : int, optional
            Maximum polling retry attempts, default: 3
        polling_base_delay : float, optional
            Base delay for exponential backoff (seconds), default: 10.0
        enable_pin : bool
            Enable PIN verification for control commands (default: True)
        pin_code : str, optional
            Fixed PIN code. If None, generates random PIN each time.
        pin_expiry_seconds : int
            PIN expiry time in seconds (default: 60)
        enable_audit : bool
            Enable audit logging (default: True)
        audit_log_dir : str
            Directory for audit logs
        rate_limit_per_minute : int
            Maximum commands per minute per user (default: 30)
        """
        if not TELEGRAM_AVAILABLE:
            raise ImportError("python-telegram-bot not installed")

        self.token = token
        self.allowed_chat_ids = [str(cid) for cid in allowed_chat_ids]
        self.strategy_callback = strategy_callback
        self.logger = logger or logging.getLogger(__name__)

        # Network configuration
        self.startup_delay = startup_delay
        self.polling_max_retries = polling_max_retries
        self.polling_base_delay = polling_base_delay

        self.application = None
        self.is_running = False
        self.start_time = datetime.utcnow()

        # v2.0: PIN verification
        self.enable_pin = enable_pin
        self.fixed_pin = pin_code
        self.pin_expiry_seconds = pin_expiry_seconds
        self._pending_pins: Dict[str, Dict[str, Any]] = {}  # {chat_id: {pin, command, expires}}

        # v2.0: Audit logging
        self.enable_audit = enable_audit and AUDIT_AVAILABLE
        self.audit_logger: Optional[AuditLogger] = None
        if self.enable_audit:
            try:
                self.audit_logger = get_audit_logger(audit_log_dir) if get_audit_logger else None
            except Exception as e:
                self.logger.warning(f"⚠️ Audit logger init failed: {e}")
                self.audit_logger = None

        # v2.0: Rate limiting
        self.rate_limit_per_minute = rate_limit_per_minute
        self._rate_limit_tracker: Dict[str, list] = {}  # {chat_id: [timestamps]}
    
    def _is_authorized(self, update: Update) -> bool:
        """Check if the user is authorized to send commands."""
        chat_id = str(update.effective_chat.id)
        is_authorized = chat_id in self.allowed_chat_ids

        # v2.0: Audit log authorization attempts
        if self.audit_logger:
            self.audit_logger.log_auth(
                user_id=chat_id,
                success=is_authorized,
                method="chat_id",
                reason=None if is_authorized else "not_in_allowed_list"
            )

        # Log authorization attempt for debugging
        if not is_authorized:
            self.logger.warning(
                f"Unauthorized command attempt from chat_id: {chat_id} "
                f"(allowed: {self.allowed_chat_ids})"
            )
        else:
            self.logger.debug(f"Authorized command from chat_id: {chat_id}")

        return is_authorized

    def _check_rate_limit(self, chat_id: str) -> bool:
        """
        Check if user is within rate limit (v2.0).

        Returns True if within limit, False if exceeded.
        """
        now = time.time()
        cutoff = now - 60  # Last minute

        # Get or create tracker for this chat
        if chat_id not in self._rate_limit_tracker:
            self._rate_limit_tracker[chat_id] = []

        # Clean old entries
        self._rate_limit_tracker[chat_id] = [
            ts for ts in self._rate_limit_tracker[chat_id] if ts > cutoff
        ]

        # Check limit
        if len(self._rate_limit_tracker[chat_id]) >= self.rate_limit_per_minute:
            self.logger.warning(f"⚠️ Rate limit exceeded for chat_id: {chat_id}")
            return False

        # Record this request
        self._rate_limit_tracker[chat_id].append(now)
        return True

    def _generate_pin(self) -> str:
        """Generate a 6-digit PIN code."""
        if self.fixed_pin:
            return self.fixed_pin
        return ''.join(random.choices('0123456789', k=6))

    def _request_pin(self, chat_id: str, command: str) -> str:
        """
        Generate and store a PIN for command verification (v2.0).

        Returns the generated PIN.
        """
        pin = self._generate_pin()
        expires = datetime.utcnow() + timedelta(seconds=self.pin_expiry_seconds)

        self._pending_pins[chat_id] = {
            'pin': pin,
            'command': command,
            'expires': expires,
            'attempts': 0,
        }

        # Audit log
        if self.audit_logger:
            self.audit_logger.log_2fa(user_id=chat_id, event="requested", command=command)

        return pin

    def _verify_pin(self, chat_id: str, entered_pin: str) -> Dict[str, Any]:
        """
        Verify entered PIN against pending request (v2.0).

        Returns:
            {'valid': bool, 'command': str or None, 'error': str or None}
        """
        if chat_id not in self._pending_pins:
            return {'valid': False, 'command': None, 'error': 'no_pending_request'}

        pending = self._pending_pins[chat_id]

        # Check expiry
        if datetime.utcnow() > pending['expires']:
            del self._pending_pins[chat_id]
            if self.audit_logger:
                self.audit_logger.log_2fa(user_id=chat_id, event="failed", command=pending['command'])
            return {'valid': False, 'command': pending['command'], 'error': 'pin_expired'}

        # Check attempts
        pending['attempts'] += 1
        if pending['attempts'] > 3:
            del self._pending_pins[chat_id]
            if self.audit_logger:
                self.audit_logger.log_2fa(user_id=chat_id, event="failed", command=pending['command'])
            return {'valid': False, 'command': pending['command'], 'error': 'too_many_attempts'}

        # Verify PIN
        if entered_pin == pending['pin']:
            command = pending['command']
            del self._pending_pins[chat_id]
            if self.audit_logger:
                self.audit_logger.log_2fa(user_id=chat_id, event="success", command=command)
            return {'valid': True, 'command': command, 'error': None}

        return {'valid': False, 'command': pending['command'], 'error': 'invalid_pin'}

    def _audit_command(self, chat_id: str, command: str, result: str, error: Optional[str] = None):
        """Log command execution to audit log (v2.0)."""
        if self.audit_logger:
            self.audit_logger.log_command(
                user_id=chat_id,
                command=command,
                result=result,
                error_message=error,
            )

    async def _send_response(self, update: Update, message: str):
        """Send response message with Markdown parse error handling."""
        try:
            await update.message.reply_text(
                message,
                parse_mode='Markdown'
            )
        except Exception as e:
            error_str = str(e).lower()
            # Handle Markdown parse errors - retry without formatting
            if "can't parse" in error_str or "parse entities" in error_str:
                self.logger.warning(f"⚠️ Markdown parse error, retrying without formatting: {e}")
                try:
                    await update.message.reply_text(message)  # No parse_mode
                    return
                except Exception as retry_error:
                    self.logger.error(f"Failed to send plain text response: {retry_error}")
            else:
                self.logger.error(f"Failed to send response: {e}")
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        self.logger.info("Received /status command")

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        try:
            # Call strategy callback to get status
            result = self.strategy_callback('status', {})

            if result.get('success'):
                await self._send_response(update, result.get('message', 'No status available'))
            else:
                await self._send_response(update, f"❌ Error: {result.get('error', 'Unknown')}")
        except Exception as e:
            self.logger.error(f"Error handling /status: {e}")
            await self._send_response(update, f"❌ Error: {str(e)}")
    
    async def cmd_position(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /position command."""
        self.logger.info("Received /position command")

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        try:
            # Call strategy callback to get position
            result = self.strategy_callback('position', {})

            if result.get('success'):
                await self._send_response(update, result.get('message', 'No position info'))
            else:
                await self._send_response(update, f"❌ Error: {result.get('error', 'Unknown')}")
        except Exception as e:
            self.logger.error(f"Error handling /position: {e}")
            await self._send_response(update, f"❌ Error: {str(e)}")
    
    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command (v2.0: requires PIN)."""
        self.logger.info("Received /pause command")
        chat_id = str(update.effective_chat.id)

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        # v2.0: Rate limit check
        if not self._check_rate_limit(chat_id):
            await self._send_response(update, "⚠️ 请求过于频繁，请稍后再试")
            return

        # v2.0: PIN verification for control commands
        if self.enable_pin:
            pin = self._request_pin(chat_id, 'pause')
            await self._send_response(
                update,
                f"🔐 *安全验证*\n\n"
                f"请在 {self.pin_expiry_seconds} 秒内回复以下验证码以确认暂停交易:\n\n"
                f"`{pin}`\n\n"
                f"_直接回复此消息输入验证码_"
            )
            return

        # Execute directly if PIN disabled
        await self._execute_pause(update, chat_id)

    async def _execute_pause(self, update: Update, chat_id: str):
        """Execute pause command after verification."""
        try:
            result = self.strategy_callback('pause', {})

            if result.get('success'):
                self._audit_command(chat_id, '/pause', 'success')
                await self._send_response(update, result.get('message', '⏸️ Trading paused'))
            else:
                error = result.get('error', 'Unknown')
                self._audit_command(chat_id, '/pause', 'failed', error)
                await self._send_response(update, f"❌ Error: {error}")
        except Exception as e:
            self._audit_command(chat_id, '/pause', 'error', str(e))
            self.logger.error(f"Error handling /pause: {e}")
            await self._send_response(update, f"❌ Error: {str(e)}")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command (v2.0: requires PIN)."""
        self.logger.info("Received /resume command")
        chat_id = str(update.effective_chat.id)

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        # v2.0: Rate limit check
        if not self._check_rate_limit(chat_id):
            await self._send_response(update, "⚠️ 请求过于频繁，请稍后再试")
            return

        # v2.0: PIN verification for control commands
        if self.enable_pin:
            pin = self._request_pin(chat_id, 'resume')
            await self._send_response(
                update,
                f"🔐 *安全验证*\n\n"
                f"请在 {self.pin_expiry_seconds} 秒内回复以下验证码以确认恢复交易:\n\n"
                f"`{pin}`\n\n"
                f"_直接回复此消息输入验证码_"
            )
            return

        # Execute directly if PIN disabled
        await self._execute_resume(update, chat_id)

    async def _execute_resume(self, update: Update, chat_id: str):
        """Execute resume command after verification."""
        try:
            result = self.strategy_callback('resume', {})

            if result.get('success'):
                self._audit_command(chat_id, '/resume', 'success')
                await self._send_response(update, result.get('message', '▶️ Trading resumed'))
            else:
                error = result.get('error', 'Unknown')
                self._audit_command(chat_id, '/resume', 'failed', error)
                await self._send_response(update, f"❌ Error: {error}")
        except Exception as e:
            self._audit_command(chat_id, '/resume', 'error', str(e))
            self.logger.error(f"Error handling /resume: {e}")
            await self._send_response(update, f"❌ Error: {str(e)}")
    
    async def cmd_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /close command - show confirmation before closing position (v2.0: requires PIN)."""
        self.logger.info("Received /close command")
        chat_id = str(update.effective_chat.id)

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        # v2.0: Rate limit check
        if not self._check_rate_limit(chat_id):
            await self._send_response(update, "⚠️ 请求过于频繁，请稍后再试")
            return

        # First get position info to show what will be closed
        try:
            pos_result = self.strategy_callback('position', {})
            position_info = ""
            if pos_result.get('success') and pos_result.get('data', {}).get('has_position'):
                data = pos_result.get('data', {})
                side = data.get('side', 'N/A')
                qty = data.get('quantity', 0)
                pnl = data.get('unrealized_pnl', 0)
                pnl_pct = data.get('pnl_pct', 0)
                pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                position_info = f"\n\n当前持仓: {side} {qty:.4f} BTC\n盈亏: {pnl_emoji} ${pnl:,.2f} ({pnl_pct:+.2f}%)"
            else:
                position_info = "\n\n⚠️ 当前无持仓"
        except Exception:
            position_info = ""

        # v2.0: PIN verification for close command
        if self.enable_pin:
            pin = self._request_pin(chat_id, 'close')
            await self._send_response(
                update,
                f"🔐 *安全验证 - 平仓确认*\n\n"
                f"此操作将立即以市价平掉所有持仓。{position_info}\n\n"
                f"请在 {self.pin_expiry_seconds} 秒内回复以下验证码确认平仓:\n\n"
                f"`{pin}`\n\n"
                f"_直接回复此消息输入验证码，或忽略以取消_"
            )
            return

        # If PIN disabled, show confirmation with inline buttons
        keyboard = [
            [
                InlineKeyboardButton("✅ 确认平仓", callback_data='confirm_close'),
                InlineKeyboardButton("❌ 取消", callback_data='cancel_close'),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"⚠️ *确认平仓？*\n\n"
            f"此操作将立即以市价平掉所有持仓。{position_info}\n\n"
            f"请确认操作：",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def _execute_close(self, update_or_query, chat_id: str):
        """Execute close command after verification."""
        try:
            result = self.strategy_callback('close', {})
            if result.get('success'):
                self._audit_command(chat_id, '/close', 'success')
                if self.audit_logger:
                    self.audit_logger.log_trading_action(chat_id, 'close_confirm', 'success')
                message = "✅ *平仓成功*\n\n" + result.get('message', '持仓已平仓')
            else:
                error = result.get('error', 'Unknown')
                self._audit_command(chat_id, '/close', 'failed', error)
                message = f"❌ 平仓失败: {error}"

            # Send response based on update type
            if hasattr(update_or_query, 'message'):
                await self._send_response(update_or_query, message)
            else:
                await update_or_query.edit_message_text(message, parse_mode='Markdown')

        except Exception as e:
            self._audit_command(chat_id, '/close', 'error', str(e))
            self.logger.error(f"Error executing close: {e}")
            error_msg = f"❌ 平仓失败: {str(e)}"
            if hasattr(update_or_query, 'message'):
                await self._send_response(update_or_query, error_msg)
            else:
                await update_or_query.edit_message_text(error_msg)

    async def handle_pin_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle PIN verification input messages (v2.0)."""
        chat_id = str(update.effective_chat.id)

        # Only process if there's a pending PIN request for this chat
        if chat_id not in self._pending_pins:
            return  # Not a PIN input, ignore

        # Authorization check
        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        entered_pin = update.message.text.strip()

        # Verify the PIN
        result = self._verify_pin(chat_id, entered_pin)

        if result['valid']:
            command = result['command']
            self.logger.info(f"PIN verified for command: {command}")

            # Execute the pending command
            if command == 'pause':
                await self._execute_pause(update, chat_id)
            elif command == 'resume':
                await self._execute_resume(update, chat_id)
            elif command == 'close':
                await self._execute_close(update, chat_id)
            else:
                await self._send_response(update, f"⚠️ 未知命令: {command}")
        else:
            error = result['error']
            if error == 'pin_expired':
                await self._send_response(update, "❌ 验证码已过期，请重新发送命令")
            elif error == 'too_many_attempts':
                await self._send_response(update, "❌ 验证失败次数过多，请重新发送命令")
            elif error == 'invalid_pin':
                await self._send_response(update, "❌ 验证码错误，请重试")

    async def cmd_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /orders command - view open orders."""
        self.logger.info("Received /orders command")

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        try:
            result = self.strategy_callback('orders', {})

            if result.get('success'):
                await self._send_response(update, result.get('message', 'No orders info'))
            else:
                await self._send_response(update, f"❌ Error: {result.get('error', 'Unknown')}")
        except Exception as e:
            self.logger.error(f"Error handling /orders: {e}")
            await self._send_response(update, f"❌ Error: {str(e)}")

    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /history command - view recent trades."""
        self.logger.info("Received /history command")

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        try:
            result = self.strategy_callback('history', {})

            if result.get('success'):
                await self._send_response(update, result.get('message', 'No history available'))
            else:
                await self._send_response(update, f"❌ Error: {result.get('error', 'Unknown')}")
        except Exception as e:
            self.logger.error(f"Error handling /history: {e}")
            await self._send_response(update, f"❌ Error: {str(e)}")

    async def cmd_risk(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /risk command - view risk metrics."""
        self.logger.info("Received /risk command")

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        try:
            result = self.strategy_callback('risk', {})

            if result.get('success'):
                await self._send_response(update, result.get('message', 'No risk info'))
            else:
                await self._send_response(update, f"❌ Error: {result.get('error', 'Unknown')}")
        except Exception as e:
            self.logger.error(f"Error handling /risk: {e}")
            await self._send_response(update, f"❌ Error: {str(e)}")

    async def cmd_daily(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /daily command - view daily performance summary (v3.13)."""
        self.logger.info("Received /daily command")

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        try:
            result = self.strategy_callback('daily_summary', {})

            if result.get('success'):
                await self._send_response(update, result.get('message', 'No daily data available'))
            else:
                await self._send_response(update, f"❌ Error: {result.get('error', 'Unknown')}")
        except Exception as e:
            self.logger.error(f"Error handling /daily: {e}")
            await self._send_response(update, f"❌ Error: {str(e)}")

    async def cmd_weekly(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /weekly command - view weekly performance summary (v3.13)."""
        self.logger.info("Received /weekly command")

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        try:
            result = self.strategy_callback('weekly_summary', {})

            if result.get('success'):
                await self._send_response(update, result.get('message', 'No weekly data available'))
            else:
                await self._send_response(update, f"❌ Error: {result.get('error', 'Unknown')}")
        except Exception as e:
            self.logger.error(f"Error handling /weekly: {e}")
            await self._send_response(update, f"❌ Error: {str(e)}")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        self.logger.info("Received /help command")

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        help_msg = (
            "🤖 *可用命令*\n\n"
            "*📊 查询命令*:\n"
            "• `/status` - 查看策略状态\n"
            "• `/position` - 查看当前持仓\n"
            "• `/orders` - 查看挂单\n"
            "• `/history` - 查看交易记录\n"
            "• `/risk` - 查看风险指标\n"
            "• `/daily` - 查看日报\n"
            "• `/weekly` - 查看周报\n\n"
            "*⚙️ 控制命令*:\n"
            "• `/pause` - 暂停交易\n"
            "• `/resume` - 恢复交易\n"
            "• `/close` - 平仓\n\n"
            "*📋 其他命令*:\n"
            "• `/menu` - 显示按钮菜单\n"
            "• `/help` - 显示帮助信息\n\n"
            "💡 _命令不区分大小写_\n"
        )
        await self._send_response(update, help_msg)

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /menu command - show interactive inline keyboard."""
        self.logger.info("Received /menu command")

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        # Create inline keyboard with buttons
        keyboard = [
            # Row 1: Query commands
            [
                InlineKeyboardButton("📊 状态", callback_data='cmd_status'),
                InlineKeyboardButton("💰 持仓", callback_data='cmd_position'),
                InlineKeyboardButton("📋 订单", callback_data='cmd_orders'),
            ],
            # Row 2: More query commands
            [
                InlineKeyboardButton("📈 历史", callback_data='cmd_history'),
                InlineKeyboardButton("⚠️ 风险", callback_data='cmd_risk'),
            ],
            # Row 3: Performance summaries (v3.13)
            [
                InlineKeyboardButton("📅 日报", callback_data='cmd_daily'),
                InlineKeyboardButton("📆 周报", callback_data='cmd_weekly'),
            ],
            # Row 4: Control commands
            [
                InlineKeyboardButton("⏸️ 暂停", callback_data='cmd_pause'),
                InlineKeyboardButton("▶️ 恢复", callback_data='cmd_resume'),
            ],
            # Row 5: Dangerous command (separate row)
            [
                InlineKeyboardButton("🔴 平仓", callback_data='cmd_close'),
            ],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🤖 *交易控制面板*\n\n点击按钮执行操作：",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard button callbacks."""
        query = update.callback_query

        # Acknowledge the callback
        await query.answer()

        # Check authorization
        chat_id = str(query.message.chat.id)
        if chat_id not in self.allowed_chat_ids:
            await query.edit_message_text("❌ Unauthorized")
            return

        callback_data = query.data
        self.logger.info(f"Received callback: {callback_data}")

        # Handle close confirmation specially
        if callback_data == 'confirm_close':
            try:
                result = self.strategy_callback('close', {})
                if result.get('success'):
                    await query.edit_message_text(
                        "✅ *平仓成功*\n\n" + result.get('message', '持仓已平仓'),
                        parse_mode='Markdown'
                    )
                else:
                    await query.edit_message_text(f"❌ 平仓失败: {result.get('error', 'Unknown')}")
            except Exception as e:
                self.logger.error(f"Error executing close: {e}")
                await query.edit_message_text(f"❌ 平仓失败: {str(e)}")
            return

        if callback_data == 'cancel_close':
            await query.edit_message_text("ℹ️ 平仓操作已取消")
            return

        # Handle menu close button specially (from /menu -> 平仓)
        if callback_data == 'cmd_close':
            # Show confirmation instead of executing directly
            keyboard = [
                [
                    InlineKeyboardButton("✅ 确认平仓", callback_data='confirm_close'),
                    InlineKeyboardButton("❌ 取消", callback_data='cancel_close'),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "⚠️ *确认平仓？*\n\n此操作将立即以市价平掉所有持仓。\n\n请确认操作：",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return

        # Map callback data to commands
        command_map = {
            'cmd_status': 'status',
            'cmd_position': 'position',
            'cmd_orders': 'orders',
            'cmd_history': 'history',
            'cmd_risk': 'risk',
            'cmd_daily': 'daily_summary',    # v3.13
            'cmd_weekly': 'weekly_summary',  # v3.13
            'cmd_pause': 'pause',
            'cmd_resume': 'resume',
        }

        command = command_map.get(callback_data)
        if not command:
            await query.edit_message_text("❌ Unknown command")
            return

        try:
            # Execute the command
            result = self.strategy_callback(command, {})

            if result.get('success'):
                message = result.get('message', f'✅ {command} executed')
                # Truncate if too long for Telegram
                if len(message) > 4000:
                    message = message[:4000] + "..."
                await query.edit_message_text(message, parse_mode='Markdown')
            else:
                await query.edit_message_text(f"❌ Error: {result.get('error', 'Unknown')}")

        except Exception as e:
            self.logger.error(f"Error handling callback {callback_data}: {e}")
            await query.edit_message_text(f"❌ Error: {str(e)}")

    async def _register_commands(self) -> bool:
        """
        Register bot commands with Telegram (shows in command menu).

        Commands are registered ONLY for private chats, not for groups.
        This makes commands appear when user clicks the "/" button
        or types "/" in private chat with the bot.
        """
        try:
            from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats, BotCommandScopeDefault

            commands = [
                BotCommand("menu", "显示操作菜单"),
                BotCommand("status", "查看系统状态"),
                BotCommand("position", "查看当前持仓"),
                BotCommand("orders", "查看挂单"),
                BotCommand("history", "最近交易记录"),
                BotCommand("risk", "风险指标"),
                BotCommand("daily", "查看日报"),
                BotCommand("weekly", "查看周报"),
                BotCommand("pause", "暂停交易"),
                BotCommand("resume", "恢复交易"),
                BotCommand("close", "平仓"),
                BotCommand("help", "帮助信息"),
            ]

            # 1. Clear default/global scope first (removes old commands)
            await self.application.bot.set_my_commands(
                [],
                scope=BotCommandScopeDefault()
            )
            self.logger.info("✅ Cleared default bot commands")

            # 2. Explicitly remove commands from ALL group chats
            await self.application.bot.set_my_commands(
                [],
                scope=BotCommandScopeAllGroupChats()
            )
            self.logger.info("✅ Bot commands removed from all group chats")

            # 3. Register commands ONLY for private chats
            await self.application.bot.set_my_commands(
                commands,
                scope=BotCommandScopeAllPrivateChats()
            )
            self.logger.info("✅ Bot commands registered for private chats")

            return True

        except Exception as e:
            self.logger.warning(f"⚠️ Failed to register bot commands: {e}")
            return False

    async def _delete_webhook_standalone(self) -> bool:
        """
        Delete webhook using a standalone Bot instance.

        This is called BEFORE Application initialization to ensure
        no webhook conflicts occur during polling startup.

        Returns True if webhook was deleted successfully.
        """
        try:
            from telegram import Bot
            bot = Bot(token=self.token)

            # Get current webhook info
            webhook_info = await bot.get_webhook_info()
            if webhook_info.url:
                self.logger.info(f"🔍 Found active webhook: {webhook_info.url}")
                await bot.delete_webhook(drop_pending_updates=True)
                self.logger.info("✅ Webhook deleted successfully")
            else:
                self.logger.info("ℹ️ No active webhook found")

            # Close the standalone bot connection
            await bot.close()
            return True

        except Exception as e:
            self.logger.warning(f"⚠️ Failed to delete webhook (standalone): {e}")
            return False

    async def start_polling(self):
        """Start the command handler polling loop with conflict handling."""
        if not TELEGRAM_AVAILABLE:
            self.logger.error("Telegram not available")
            return

        # CRITICAL: Delete any existing webhook BEFORE doing anything else
        # This prevents "can't use getUpdates while webhook is active" errors
        self.logger.info("🔄 Pre-startup webhook cleanup...")
        await self._delete_webhook_standalone()

        # Short delay after webhook deletion to let Telegram servers sync
        self.logger.info(f"⏳ Waiting {self.startup_delay}s for Telegram servers to sync...")
        await asyncio.sleep(self.startup_delay)

        retry_count = 0

        while retry_count < self.polling_max_retries:
            try:
                # Create application
                self.application = Application.builder().token(self.token).build()

                # Register command handlers
                self.application.add_handler(CommandHandler("status", self.cmd_status))
                self.application.add_handler(CommandHandler("position", self.cmd_position))
                self.application.add_handler(CommandHandler("orders", self.cmd_orders))
                self.application.add_handler(CommandHandler("history", self.cmd_history))
                self.application.add_handler(CommandHandler("risk", self.cmd_risk))
                self.application.add_handler(CommandHandler("daily", self.cmd_daily))    # v3.13
                self.application.add_handler(CommandHandler("weekly", self.cmd_weekly))  # v3.13
                self.application.add_handler(CommandHandler("pause", self.cmd_pause))
                self.application.add_handler(CommandHandler("resume", self.cmd_resume))
                self.application.add_handler(CommandHandler("close", self.cmd_close))
                self.application.add_handler(CommandHandler("help", self.cmd_help))
                self.application.add_handler(CommandHandler("menu", self.cmd_menu))  # Inline keyboard menu
                self.application.add_handler(CommandHandler("start", self.cmd_help))  # Alias for help

                # Register callback handler for inline keyboard buttons
                self.application.add_handler(CallbackQueryHandler(self.handle_callback))

                # v2.0: Register message handler for PIN verification input
                # This must come after command handlers so commands are processed first
                if self.enable_pin and MessageHandler and filters:
                    self.application.add_handler(
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_pin_input)
                    )
                    self.logger.info("🔐 PIN verification handler registered")

                self.logger.info("🤖 Starting Telegram command handler...")

                # Start polling - compatible with python-telegram-bot v20+
                await self.application.initialize()

                # Delete webhook again after initialization (belt and suspenders)
                self.logger.info("🔄 Post-init webhook cleanup...")
                await self.application.bot.delete_webhook(drop_pending_updates=True)
                self.logger.info("✅ Webhook cleanup complete")

                # Register commands for the command menu (shows when user types "/")
                await self._register_commands()

                await self.application.start()
                await self.application.updater.start_polling(
                    allowed_updates=["message", "callback_query"],  # Listen to messages and button callbacks
                    drop_pending_updates=True,  # Clear stale updates to avoid conflicts on restart
                )

                self.is_running = True
                self.logger.info("✅ Telegram command handler started successfully")

                # Keep the event loop running
                # Create a never-ending task to keep polling alive
                stop_signal = asyncio.Event()
                await stop_signal.wait()  # This will wait forever until explicitly set

            except TelegramConflict as e:
                retry_count += 1
                delay = self.polling_base_delay * (2 ** (retry_count - 1))  # Exponential backoff

                if retry_count < self.polling_max_retries:
                    self.logger.warning(
                        f"⚠️ Telegram Conflict error. "
                        f"Retry {retry_count}/{self.polling_max_retries} in {delay}s: {e}"
                    )
                    # Clean up current application before retry
                    if self.application:
                        try:
                            await self.application.shutdown()
                        except Exception:
                            pass
                        self.application = None

                    # Try to delete webhook again before retry
                    self.logger.info("🔄 Attempting webhook cleanup before retry...")
                    await self._delete_webhook_standalone()

                    await asyncio.sleep(delay)
                else:
                    self.logger.error(
                        f"❌ Telegram Conflict error persists after {self.polling_max_retries} retries. "
                        f"Command handler disabled. Possible causes:\n"
                        f"  1. Another bot instance using the same token\n"
                        f"  2. External service setting webhooks\n"
                        f"  Run: curl 'https://api.telegram.org/bot<TOKEN>/deleteWebhook'"
                    )
                    self.is_running = False
                    return  # Give up after max retries

            except Exception as e:
                self.logger.error(f"❌ Failed to start command handler: {e}")
                self.is_running = False
                raise
    
    async def stop_polling(self):
        """Stop the command handler."""
        if self.application and self.is_running:
            try:
                self.logger.info("🛑 Stopping Telegram command handler...")
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                self.is_running = False
                self.logger.info("✅ Command handler stopped")
            except Exception as e:
                self.logger.error(f"Error stopping command handler: {e}")

