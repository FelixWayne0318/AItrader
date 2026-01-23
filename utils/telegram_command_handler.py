"""
Telegram Command Handler for Trading Strategy

Handles incoming Telegram commands for remote control of the trading strategy.
"""

import asyncio
import logging
from typing import Optional, Callable, Dict, Any
from datetime import datetime

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
    from telegram.error import Conflict as TelegramConflict
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Application = None
    CommandHandler = None
    CallbackQueryHandler = None
    Update = None
    ContextTypes = None
    TelegramConflict = Exception
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None


class TelegramCommandHandler:
    """
    Handles Telegram commands for strategy control.

    Query Commands:
    - /status: Get strategy status
    - /position: Get current position info
    - /orders: View open orders
    - /history: View recent trade history
    - /risk: View risk metrics
    - /help: Show available commands
    - /menu: Show interactive button menu

    Control Commands:
    - /pause: Pause trading
    - /resume: Resume trading
    - /close: Close current position
    """
    
    def __init__(
        self,
        token: str,
        allowed_chat_ids: list,
        strategy_callback: Callable,
        logger: Optional[logging.Logger] = None
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
        """
        if not TELEGRAM_AVAILABLE:
            raise ImportError("python-telegram-bot not installed")
        
        self.token = token
        self.allowed_chat_ids = [str(cid) for cid in allowed_chat_ids]
        self.strategy_callback = strategy_callback
        self.logger = logger or logging.getLogger(__name__)
        
        self.application = None
        self.is_running = False
        self.start_time = datetime.utcnow()
    
    def _is_authorized(self, update: Update) -> bool:
        """Check if the user is authorized to send commands."""
        chat_id = str(update.effective_chat.id)
        is_authorized = chat_id in self.allowed_chat_ids

        # Log authorization attempt for debugging
        if not is_authorized:
            self.logger.warning(
                f"Unauthorized command attempt from chat_id: {chat_id} "
                f"(allowed: {self.allowed_chat_ids})"
            )
        else:
            self.logger.info(f"Authorized command from chat_id: {chat_id}")

        return is_authorized
    
    async def _send_response(self, update: Update, message: str):
        """Send response message."""
        try:
            await update.message.reply_text(
                message,
                parse_mode='Markdown'
            )
        except Exception as e:
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
        """Handle /pause command."""
        self.logger.info("Received /pause command")

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        try:
            # Call strategy callback to pause
            result = self.strategy_callback('pause', {})

            if result.get('success'):
                await self._send_response(update, result.get('message', '⏸️ Trading paused'))
            else:
                await self._send_response(update, f"❌ Error: {result.get('error', 'Unknown')}")
        except Exception as e:
            self.logger.error(f"Error handling /pause: {e}")
            await self._send_response(update, f"❌ Error: {str(e)}")
    
    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command."""
        self.logger.info("Received /resume command")

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        try:
            # Call strategy callback to resume
            result = self.strategy_callback('resume', {})

            if result.get('success'):
                await self._send_response(update, result.get('message', '▶️ Trading resumed'))
            else:
                await self._send_response(update, f"❌ Error: {result.get('error', 'Unknown')}")
        except Exception as e:
            self.logger.error(f"Error handling /resume: {e}")
            await self._send_response(update, f"❌ Error: {str(e)}")
    
    async def cmd_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /close command - close current position."""
        self.logger.info("Received /close command")

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        try:
            result = self.strategy_callback('close', {})

            if result.get('success'):
                await self._send_response(update, result.get('message', '✅ Position closed'))
            else:
                await self._send_response(update, f"❌ Error: {result.get('error', 'Unknown')}")
        except Exception as e:
            self.logger.error(f"Error handling /close: {e}")
            await self._send_response(update, f"❌ Error: {str(e)}")

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

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        self.logger.info("Received /help command")

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        help_msg = (
            "🤖 *Available Commands*\n\n"
            "*Query Commands*:\n"
            "• `/status` - View strategy status\n"
            "• `/position` - View current position\n"
            "• `/orders` - View open orders\n"
            "• `/history` - Recent trade history\n"
            "• `/risk` - View risk metrics\n"
            "• `/help` - Show this help message\n"
            "• `/menu` - Show interactive buttons\n\n"
            "*Control Commands*:\n"
            "• `/pause` - Pause trading (no new orders)\n"
            "• `/resume` - Resume trading\n"
            "• `/close` - Close current position\n\n"
            "💡 _Commands are case-insensitive_\n"
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
            # Row 3: Control commands
            [
                InlineKeyboardButton("⏸️ 暂停", callback_data='cmd_pause'),
                InlineKeyboardButton("▶️ 恢复", callback_data='cmd_resume'),
            ],
            # Row 4: Dangerous command (separate row)
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

        # Map callback data to commands
        command_map = {
            'cmd_status': 'status',
            'cmd_position': 'position',
            'cmd_orders': 'orders',
            'cmd_history': 'history',
            'cmd_risk': 'risk',
            'cmd_pause': 'pause',
            'cmd_resume': 'resume',
            'cmd_close': 'close',
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
            from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats

            commands = [
                BotCommand("menu", "显示操作菜单"),
                BotCommand("status", "查看系统状态"),
                BotCommand("position", "查看当前持仓"),
                BotCommand("orders", "查看挂单"),
                BotCommand("history", "最近交易记录"),
                BotCommand("risk", "风险指标"),
                BotCommand("pause", "暂停交易"),
                BotCommand("resume", "恢复交易"),
                BotCommand("close", "平仓"),
                BotCommand("help", "帮助信息"),
            ]

            # Register commands ONLY for private chats
            await self.application.bot.set_my_commands(
                commands,
                scope=BotCommandScopeAllPrivateChats()
            )
            self.logger.info("✅ Bot commands registered for private chats")

            # Remove commands from group chats (set empty list)
            await self.application.bot.set_my_commands(
                [],
                scope=BotCommandScopeAllGroupChats()
            )
            self.logger.info("✅ Bot commands removed from group chats")

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
        startup_delay = 5
        self.logger.info(f"⏳ Waiting {startup_delay}s for Telegram servers to sync...")
        await asyncio.sleep(startup_delay)

        max_retries = 3
        retry_count = 0
        base_delay = 10  # Reduced since we already deleted webhook

        while retry_count < max_retries:
            try:
                # Create application
                self.application = Application.builder().token(self.token).build()

                # Register command handlers
                self.application.add_handler(CommandHandler("status", self.cmd_status))
                self.application.add_handler(CommandHandler("position", self.cmd_position))
                self.application.add_handler(CommandHandler("orders", self.cmd_orders))
                self.application.add_handler(CommandHandler("history", self.cmd_history))
                self.application.add_handler(CommandHandler("risk", self.cmd_risk))
                self.application.add_handler(CommandHandler("pause", self.cmd_pause))
                self.application.add_handler(CommandHandler("resume", self.cmd_resume))
                self.application.add_handler(CommandHandler("close", self.cmd_close))
                self.application.add_handler(CommandHandler("help", self.cmd_help))
                self.application.add_handler(CommandHandler("menu", self.cmd_menu))  # Inline keyboard menu
                self.application.add_handler(CommandHandler("start", self.cmd_help))  # Alias for help

                # Register callback handler for inline keyboard buttons
                self.application.add_handler(CallbackQueryHandler(self.handle_callback))

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
                delay = base_delay * (2 ** (retry_count - 1))  # Exponential backoff

                if retry_count < max_retries:
                    self.logger.warning(
                        f"⚠️ Telegram Conflict error. "
                        f"Retry {retry_count}/{max_retries} in {delay}s: {e}"
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
                        f"❌ Telegram Conflict error persists after {max_retries} retries. "
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

