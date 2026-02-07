"""
Telegram Command Handler v3.1 — Enhanced Command System

Minimal slash commands + menu-driven interaction.

Registered in "/" menu (9 commands):
  /menu    — 操作面板 (primary entry point)
  /s       — 快速状态
  /p       — 快速查看持仓 (含 SL/TP, ROE, 仓位价值, 保证金)
  /b       — 账户余额
  /a       — 技术面
  /fa      — 立即分析
  /profit  — 盈亏分析
  /close   — 平仓 (PIN required)
  /help    — 帮助

All commands (typed):
  Query: /status, /position, /balance, /orders, /history, /risk,
         /daily, /weekly, /analyze, /config, /version, /logs, /profit
  Control (PIN): /pause, /resume, /close, /force_analysis,
         /partial_close, /set_leverage, /toggle, /set,
         /modify_sl, /modify_tp, /reload_config, /restart

Security (v2.0, preserved):
- PIN verification for control commands
- Audit logging for all operations
- Rate limiting
"""

import asyncio
import logging
import random
import time
from typing import Optional, Callable, Dict, Any
from datetime import datetime, timedelta

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application, CommandHandler, CallbackQueryHandler,
        ContextTypes, MessageHandler, filters,
    )
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

try:
    from utils.audit_logger import AuditLogger, AuditEventType, get_audit_logger
    AUDIT_AVAILABLE = True
except ImportError:
    AUDIT_AVAILABLE = False
    AuditLogger = None
    AuditEventType = None
    get_audit_logger = None


# ============ Command Registry ============

# Query commands: command_name -> strategy callback name
QUERY_COMMANDS = {
    'status':   'status',
    'position': 'position',
    'orders':   'orders',
    'history':  'history',
    'risk':     'risk',
    'daily':    'daily_summary',
    'weekly':   'weekly_summary',
    'balance':  'balance',
    'analyze':  'analyze',
    'config':   'config',
    'version':  'version',
    'profit':   'profit',
}

# Query commands that accept arguments
QUERY_COMMANDS_WITH_ARGS = {
    'logs': ('logs', lambda args: {'lines': int(args[0]) if args else 20}),
}

# Control commands that require PIN verification
CONTROL_COMMANDS = {'pause', 'resume', 'close'}

# Control commands with arguments (require PIN)
CONTROL_COMMANDS_WITH_ARGS = {
    'force_analysis': ('force_analysis', None),
    'partial_close':  ('partial_close', lambda args: {'percent': int(args[0]) if args else 50}),
    'set_leverage':   ('set_leverage', lambda args: {'value': args[0] if args else None}),
    'toggle':         ('toggle', lambda args: {'feature': args[0] if args else ''}),
    'set':            ('set_param', lambda args: {'param': args[0] if args else '', 'value': args[1] if len(args) > 1 else None}),
    'restart':        ('restart', None),
    'update':         ('restart', None),  # alias for restart
    'modify_sl':      ('modify_sl', lambda args: {'price': args[0] if args else None}),
    'modify_tp':      ('modify_tp', lambda args: {'price': args[0] if args else None}),
    'reload_config':  ('reload_config', None),
}

# PIN confirmation messages (Chinese)
PIN_MESSAGES = {
    'pause':          '暂停交易',
    'resume':         '恢复交易',
    'close':          '平仓',
    'force_analysis': '立即分析',
    'partial_close':  '部分平仓',
    'set_leverage':   '修改杠杆',
    'toggle':         '功能开关',
    'set':            '修改参数',
    'restart':        '重启服务',
    'update':         '更新+重启',
    'modify_sl':      '修改止损',
    'modify_tp':      '修改止盈',
    'reload_config':  '重载配置',
}

# Menu callback_data -> strategy command mapping
CALLBACK_MAP = {
    # Query
    'q_status':    'status',
    'q_position':  'position',
    'q_orders':    'orders',
    'q_history':   'history',
    'q_risk':      'risk',
    'q_daily':     'daily_summary',
    'q_weekly':    'weekly_summary',
    'q_balance':   'balance',
    'q_analyze':   'analyze',
    'q_config':    'config',
    'q_version':   'version',
    'q_profit':    'profit',
    # Control
    'c_pause':     'pause',
    'c_resume':    'resume',
    'c_close':     'close',
    'c_fa':        'force_analysis',
    'c_restart':   'restart',
    'c_reload':    'reload_config',
}


class TelegramCommandHandler:
    """
    Telegram command handler with menu-driven interaction.

    Query Commands (no PIN): /s, /p, /status, /position, /orders, /history, /risk, /daily, /weekly
    Control Commands (PIN required): /pause, /resume, /close
    UI Commands: /menu, /help
    """

    def __init__(
        self,
        token: str,
        allowed_chat_ids: list,
        strategy_callback: Callable,
        logger: Optional[logging.Logger] = None,
        startup_delay: float = 5.0,
        polling_max_retries: int = 3,
        polling_base_delay: float = 10.0,
        enable_pin: bool = True,
        pin_code: Optional[str] = None,
        pin_expiry_seconds: int = 60,
        enable_audit: bool = True,
        audit_log_dir: str = "logs/audit",
        rate_limit_per_minute: int = 30,
    ):
        if not TELEGRAM_AVAILABLE:
            raise ImportError("python-telegram-bot not installed")

        self.token = token
        self.allowed_chat_ids = [str(cid) for cid in allowed_chat_ids]
        self.strategy_callback = strategy_callback
        self.logger = logger or logging.getLogger(__name__)

        self.startup_delay = startup_delay
        self.polling_max_retries = polling_max_retries
        self.polling_base_delay = polling_base_delay

        self.application = None
        self.is_running = False
        self.start_time = datetime.utcnow()

        # PIN verification
        self.enable_pin = enable_pin
        self.fixed_pin = pin_code
        self.pin_expiry_seconds = pin_expiry_seconds
        self._pending_pins: Dict[str, Dict[str, Any]] = {}

        # Audit logging
        self.enable_audit = enable_audit and AUDIT_AVAILABLE
        self.audit_logger: Optional[AuditLogger] = None
        if self.enable_audit:
            try:
                self.audit_logger = get_audit_logger(audit_log_dir) if get_audit_logger else None
            except Exception as e:
                self.logger.warning(f"Audit logger init failed: {e}")
                self.audit_logger = None

        # Rate limiting
        self.rate_limit_per_minute = rate_limit_per_minute
        self._rate_limit_tracker: Dict[str, list] = {}

    # ==================== Auth & Security ====================

    def _is_authorized(self, update: Update) -> bool:
        """Check if the user is authorized."""
        chat_id = str(update.effective_chat.id)
        is_authorized = chat_id in self.allowed_chat_ids

        if self.audit_logger:
            self.audit_logger.log_auth(
                user_id=chat_id,
                success=is_authorized,
                method="chat_id",
                reason=None if is_authorized else "not_in_allowed_list"
            )

        if not is_authorized:
            self.logger.warning(
                f"Unauthorized attempt from chat_id: {chat_id} "
                f"(allowed: {self.allowed_chat_ids})"
            )

        return is_authorized

    def _check_rate_limit(self, chat_id: str) -> bool:
        """Check rate limit. Returns True if within limit."""
        now = time.time()
        cutoff = now - 60

        if chat_id not in self._rate_limit_tracker:
            self._rate_limit_tracker[chat_id] = []

        self._rate_limit_tracker[chat_id] = [
            ts for ts in self._rate_limit_tracker[chat_id] if ts > cutoff
        ]

        if len(self._rate_limit_tracker[chat_id]) >= self.rate_limit_per_minute:
            self.logger.warning(f"Rate limit exceeded for chat_id: {chat_id}")
            return False

        self._rate_limit_tracker[chat_id].append(now)
        return True

    def _generate_pin(self) -> str:
        """Generate a 6-digit PIN code."""
        if self.fixed_pin:
            return self.fixed_pin
        return ''.join(random.choices('0123456789', k=6))

    def _request_pin(self, chat_id: str, command: str) -> str:
        """Generate and store a PIN for command verification."""
        pin = self._generate_pin()
        expires = datetime.utcnow() + timedelta(seconds=self.pin_expiry_seconds)

        self._pending_pins[chat_id] = {
            'pin': pin,
            'command': command,
            'expires': expires,
            'attempts': 0,
        }

        if self.audit_logger:
            self.audit_logger.log_2fa(user_id=chat_id, event="requested", command=command)

        return pin

    def _verify_pin(self, chat_id: str, entered_pin: str) -> Dict[str, Any]:
        """Verify entered PIN. Returns {'valid': bool, 'command': str, 'error': str}."""
        if chat_id not in self._pending_pins:
            return {'valid': False, 'command': None, 'error': 'no_pending_request'}

        pending = self._pending_pins[chat_id]

        if datetime.utcnow() > pending['expires']:
            del self._pending_pins[chat_id]
            if self.audit_logger:
                self.audit_logger.log_2fa(user_id=chat_id, event="failed", command=pending['command'])
            return {'valid': False, 'command': pending['command'], 'error': 'pin_expired'}

        pending['attempts'] += 1
        if pending['attempts'] > 3:
            del self._pending_pins[chat_id]
            if self.audit_logger:
                self.audit_logger.log_2fa(user_id=chat_id, event="failed", command=pending['command'])
            return {'valid': False, 'command': pending['command'], 'error': 'too_many_attempts'}

        if entered_pin == pending['pin']:
            command = pending['command']
            cmd_args = pending.get('args', [])
            del self._pending_pins[chat_id]
            if self.audit_logger:
                self.audit_logger.log_2fa(user_id=chat_id, event="success", command=command)
            return {'valid': True, 'command': command, 'error': None, 'args': cmd_args}

        return {'valid': False, 'command': pending['command'], 'error': 'invalid_pin'}

    def _audit_command(self, chat_id: str, command: str, result: str, error: Optional[str] = None):
        """Log command to audit log."""
        if self.audit_logger:
            self.audit_logger.log_command(
                user_id=chat_id,
                command=command,
                result=result,
                error_message=error,
            )

    # ==================== Helpers ====================

    async def _send_response(self, update: Update, message: str):
        """Send response with Markdown fallback."""
        try:
            await update.message.reply_text(message, parse_mode='Markdown')
        except Exception as e:
            error_str = str(e).lower()
            if "can't parse" in error_str or "parse entities" in error_str:
                self.logger.warning(f"Markdown parse error, retrying plain: {e}")
                try:
                    await update.message.reply_text(message)
                except Exception as retry_error:
                    self.logger.error(f"Failed to send plain text: {retry_error}")
            else:
                self.logger.error(f"Failed to send response: {e}")

    async def _edit_message(self, query, message: str, reply_markup=None):
        """Edit callback query message with Markdown fallback."""
        try:
            await query.edit_message_text(
                message, parse_mode='Markdown', reply_markup=reply_markup
            )
        except Exception as e:
            error_str = str(e).lower()
            if "can't parse" in error_str or "parse entities" in error_str:
                self.logger.warning(f"Markdown parse error in edit, retrying plain: {e}")
                try:
                    await query.edit_message_text(message, reply_markup=reply_markup)
                except Exception:
                    pass
            else:
                self.logger.error(f"Failed to edit message: {e}")

    @staticmethod
    def _menu_keyboard():
        """Build the main menu inline keyboard."""
        return InlineKeyboardMarkup([
            # Row 1: Core info
            [
                InlineKeyboardButton("📊 状态", callback_data='q_status'),
                InlineKeyboardButton("💰 持仓", callback_data='q_position'),
                InlineKeyboardButton("💵 余额", callback_data='q_balance'),
            ],
            # Row 2: Market data
            [
                InlineKeyboardButton("📈 技术面", callback_data='q_analyze'),
                InlineKeyboardButton("📋 订单", callback_data='q_orders'),
                InlineKeyboardButton("⚠️ 风险", callback_data='q_risk'),
            ],
            # Row 3: Reports & Analytics
            [
                InlineKeyboardButton("📅 日报", callback_data='q_daily'),
                InlineKeyboardButton("📆 周报", callback_data='q_weekly'),
                InlineKeyboardButton("💹 盈亏", callback_data='q_profit'),
            ],
            # Row 4: Trading control
            [
                InlineKeyboardButton("⏸️ 暂停", callback_data='c_pause'),
                InlineKeyboardButton("▶️ 恢复", callback_data='c_resume'),
                InlineKeyboardButton("🔄 分析", callback_data='c_fa'),
            ],
            # Row 5: Dangerous operations
            [
                InlineKeyboardButton("🔴 平仓", callback_data='c_close'),
                InlineKeyboardButton("🔁 重启", callback_data='c_restart'),
                InlineKeyboardButton("🔃 重载配置", callback_data='c_reload'),
            ],
            # Row 6: System
            [
                InlineKeyboardButton("📈 历史", callback_data='q_history'),
                InlineKeyboardButton("⚙️ 配置", callback_data='q_config'),
                InlineKeyboardButton("ℹ️ 版本", callback_data='q_version'),
            ],
        ])

    @staticmethod
    def _back_button():
        """Create 'back to menu' inline keyboard."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ 返回菜单", callback_data='main_menu')]
        ])

    # ==================== Generic Dispatchers ====================

    async def _dispatch_query(self, update_or_query, strategy_command: str, is_callback: bool = False):
        """Execute a query command and send result."""
        try:
            result = self.strategy_callback(strategy_command, {})

            if result.get('success'):
                message = result.get('message', '无数据')
                if len(message) > 4000:
                    message = message[:4000] + "..."
            else:
                message = f"❌ {result.get('error', 'Unknown error')}"

            if is_callback:
                await self._edit_message(
                    update_or_query, message, reply_markup=self._back_button()
                )
            else:
                await self._send_response(update_or_query, message)

        except Exception as e:
            self.logger.error(f"Error dispatching query '{strategy_command}': {e}")
            error_msg = f"❌ Error: {str(e)}"
            if is_callback:
                await self._edit_message(update_or_query, error_msg, reply_markup=self._back_button())
            else:
                await self._send_response(update_or_query, error_msg)

    async def _dispatch_control(self, update, chat_id: str, command: str):
        """Execute a control command (after PIN verification or PIN disabled)."""
        await self._dispatch_control_with_args(update, chat_id, command, [])

    async def _dispatch_control_with_args(self, update, chat_id: str, command: str, cmd_args: list):
        """Execute a control command with arguments."""
        try:
            # Map command to strategy callback name and parse args
            if command in CONTROL_COMMANDS:
                strategy_cmd = command
                args = {}
            elif command in CONTROL_COMMANDS_WITH_ARGS:
                strategy_cmd, args_parser = CONTROL_COMMANDS_WITH_ARGS[command]
                args = args_parser(cmd_args) if args_parser and cmd_args else {}
            else:
                strategy_cmd = command
                args = {}

            result = self.strategy_callback(strategy_cmd, args)

            if result.get('success'):
                self._audit_command(chat_id, f'/{command}', 'success')
                await self._send_response(update, result.get('message', f'✅ {command}'))
            else:
                error = result.get('error', 'Unknown')
                self._audit_command(chat_id, f'/{command}', 'failed', error)
                await self._send_response(update, f"❌ {error}")
        except Exception as e:
            self._audit_command(chat_id, f'/{command}', 'error', str(e))
            self.logger.error(f"Error executing /{command}: {e}")
            await self._send_response(update, f"❌ {str(e)}")

    # ==================== Slash Command Handlers ====================

    async def _handle_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE, command_name: str):
        """Generic handler for all query slash commands."""
        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        self.logger.info(f"Received /{command_name} command")
        strategy_cmd = QUERY_COMMANDS.get(command_name, command_name)
        await self._dispatch_query(update, strategy_cmd)

    async def _handle_query_with_args(self, update: Update, context: ContextTypes.DEFAULT_TYPE, command_name: str):
        """Handler for query commands that accept arguments."""
        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        self.logger.info(f"Received /{command_name} command with args: {context.args}")

        cmd_info = QUERY_COMMANDS_WITH_ARGS.get(command_name)
        if not cmd_info:
            await self._send_response(update, "❌ Unknown command")
            return

        strategy_cmd, args_parser = cmd_info
        args = args_parser(context.args) if args_parser and context.args else {}

        try:
            result = self.strategy_callback(strategy_cmd, args)
            if result.get('success'):
                message = result.get('message', '无数据')
                if len(message) > 4000:
                    message = message[:4000] + "..."
            else:
                message = f"❌ {result.get('error', 'Unknown error')}"
            await self._send_response(update, message)
        except Exception as e:
            await self._send_response(update, f"❌ {str(e)}")

    async def _handle_control(self, update: Update, context: ContextTypes.DEFAULT_TYPE, command_name: str):
        """Generic handler for control slash commands with PIN flow."""
        chat_id = str(update.effective_chat.id)

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        if not self._check_rate_limit(chat_id):
            await self._send_response(update, "⚠️ 请求过于频繁，请稍后再试")
            return

        self.logger.info(f"Received /{command_name} command with args: {getattr(context, 'args', [])}")

        # Store args for after PIN verification
        cmd_args = getattr(context, 'args', []) or []

        if self.enable_pin:
            # For close, include position info in PIN prompt
            position_info = ""
            if command_name == 'close':
                try:
                    pos_result = self.strategy_callback('position', {})
                    if pos_result.get('success') and pos_result.get('data', {}).get('has_position'):
                        data = pos_result['data']
                        side = data.get('side', 'N/A')
                        qty = data.get('quantity', 0)
                        pnl = data.get('unrealized_pnl', 0)
                        pnl_pct = data.get('pnl_pct', 0)
                        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                        position_info = (
                            f"\n\n当前持仓: {side} {qty:.4f} BTC\n"
                            f"盈亏: {pnl_emoji} ${pnl:,.2f} ({pnl_pct:+.2f}%)"
                        )
                    elif pos_result.get('success'):
                        position_info = "\n\n⚠️ 当前无持仓"
                except Exception:
                    pass

            pin = self._request_pin(chat_id, command_name)
            # Store args with PIN for later retrieval
            self._pending_pins[chat_id]['args'] = cmd_args
            pin_msg = PIN_MESSAGES.get(command_name, command_name)
            await self._send_response(
                update,
                f"🔐 *安全验证*\n\n"
                f"请在 {self.pin_expiry_seconds} 秒内回复验证码以确认{pin_msg}:{position_info}\n\n"
                f"`{pin}`\n\n"
                f"_直接回复验证码，或忽略以取消_"
            )
            return

        # PIN disabled — execute directly
        await self._dispatch_control_with_args(update, chat_id, command_name, cmd_args)

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show interactive inline keyboard menu."""
        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        try:
            await update.message.reply_text(
                "🤖 *交易控制面板*\n\n点击按钮执行操作：",
                reply_markup=self._menu_keyboard(),
                parse_mode='Markdown'
            )
        except Exception as e:
            self.logger.error(f"cmd_menu error: {e}")
            # Fallback: send plain text without keyboard
            try:
                await update.message.reply_text(
                    "🤖 交易控制面板\n\n点击按钮执行操作：",
                    reply_markup=self._menu_keyboard(),
                )
            except Exception as e2:
                self.logger.error(f"cmd_menu fallback error: {e2}")
                await self._send_response(update, f"❌ Menu error: {e2}")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help with quick commands."""
        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        help_msg = (
            "🤖 *交易机器人*\n\n"
            "*快捷命令*:\n"
            "  `/s` 状态 | `/p` 持仓 | `/b` 余额\n"
            "  `/a` 技术面 | `/v` 版本 | `/l` 日志\n"
            "  `/fa` 立即分析 | `/pc` 部分平仓\n\n"
            "*查询*:\n"
            "  `/status` `/position` `/balance`\n"
            "  `/orders` `/risk` `/analyze`\n"
            "  `/daily` `/weekly` `/history`\n"
            "  `/profit` `/config` `/version` `/logs`\n\n"
            "*控制* (需 PIN):\n"
            "  `/pause` `/resume` `/close`\n"
            "  `/force_analysis` — 立即触发 AI 分析\n"
            "  `/partial_close 50` — 部分平仓 50%\n"
            "  `/modify_sl 95000` — 修改止损价\n"
            "  `/modify_tp 105000` — 修改止盈价\n"
            "  `/set_leverage 10` — 修改杠杆\n"
            "  `/toggle trailing` — 功能开关\n"
            "  `/set min_confidence HIGH` — 修改参数\n"
            "  `/reload_config` — 重载 YAML 配置\n"
            "  `/restart` — 重启服务\n\n"
            "💡 推荐使用 /menu 按钮操作\n"
        )
        await self._send_response(update, help_msg)

    # ==================== Callback Handler ====================

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard button callbacks."""
        query = update.callback_query
        await query.answer()

        chat_id = str(query.message.chat.id)
        if chat_id not in self.allowed_chat_ids:
            await query.edit_message_text("❌ Unauthorized")
            return

        callback_data = query.data
        self.logger.info(f"Received callback: {callback_data}")

        # Back to menu
        if callback_data == 'main_menu':
            await self._edit_message(
                query,
                "🤖 *交易控制面板*\n\n点击按钮执行操作：",
                reply_markup=self._menu_keyboard()
            )
            return

        # Close confirmation flow
        if callback_data == 'confirm_close':
            try:
                result = self.strategy_callback('close', {})
                if result.get('success'):
                    self._audit_command(chat_id, '/close', 'success')
                    if self.audit_logger:
                        self.audit_logger.log_trading_action(chat_id, 'close_confirm', 'success')
                    msg = "✅ *平仓成功*\n\n" + result.get('message', '持仓已平仓')
                else:
                    msg = f"❌ 平仓失败: {result.get('error', 'Unknown')}"
                await self._edit_message(query, msg, reply_markup=self._back_button())
            except Exception as e:
                self.logger.error(f"Error executing close: {e}")
                await self._edit_message(query, f"❌ 平仓失败: {str(e)}", reply_markup=self._back_button())
            return

        if callback_data == 'cancel_close':
            await self._edit_message(query, "ℹ️ 操作已取消", reply_markup=self._back_button())
            return

        # Look up strategy command
        strategy_cmd = CALLBACK_MAP.get(callback_data)
        if not strategy_cmd:
            await self._edit_message(query, "❌ 未知操作")
            return

        # Control commands from menu
        if callback_data.startswith('c_'):
            command = callback_data[2:]  # 'c_pause' -> 'pause'

            # Close: show confirmation dialog
            if command == 'close':
                # Get position info for confirmation
                position_info = ""
                try:
                    pos_result = self.strategy_callback('position', {})
                    if pos_result.get('success') and pos_result.get('data', {}).get('has_position'):
                        data = pos_result['data']
                        side = data.get('side', 'N/A')
                        qty = data.get('quantity', 0)
                        pnl = data.get('unrealized_pnl', 0)
                        pnl_pct = data.get('pnl_pct', 0)
                        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                        position_info = (
                            f"\n\n当前持仓: {side} {qty:.4f} BTC\n"
                            f"盈亏: {pnl_emoji} ${pnl:,.2f} ({pnl_pct:+.2f}%)"
                        )
                    elif pos_result.get('success'):
                        position_info = "\n\n⚠️ 当前无持仓"
                except Exception:
                    pass

                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ 确认平仓", callback_data='confirm_close'),
                        InlineKeyboardButton("❌ 取消", callback_data='cancel_close'),
                    ],
                ])
                await self._edit_message(
                    query,
                    f"⚠️ *确认平仓？*\n\n此操作将立即以市价平掉所有持仓。{position_info}\n\n请确认操作：",
                    reply_markup=keyboard
                )
                return

            # Pause/Resume/ForceAnalysis/Restart from menu: execute with audit
            try:
                result = self.strategy_callback(strategy_cmd, {})
                if result.get('success'):
                    self._audit_command(chat_id, f'/{command}', 'success')
                    msg = result.get('message', f'✅ {command}')
                else:
                    error = result.get('error', 'Unknown')
                    self._audit_command(chat_id, f'/{command}', 'failed', error)
                    msg = f"❌ {error}"
                await self._edit_message(query, msg, reply_markup=self._back_button())
            except Exception as e:
                self._audit_command(chat_id, f'/{command}', 'error', str(e))
                self.logger.error(f"Error executing {command} from menu: {e}")
                await self._edit_message(query, f"❌ {str(e)}", reply_markup=self._back_button())
            return

        # Query commands from menu
        await self._dispatch_query(query, strategy_cmd, is_callback=True)

    # ==================== PIN Input Handler ====================

    async def handle_pin_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle PIN verification input messages."""
        chat_id = str(update.effective_chat.id)

        if chat_id not in self._pending_pins:
            return

        if not self._is_authorized(update):
            await self._send_response(update, "❌ Unauthorized")
            return

        entered_pin = update.message.text.strip()
        result = self._verify_pin(chat_id, entered_pin)

        if result['valid']:
            command = result['command']
            cmd_args = result.get('args', [])
            self.logger.info(f"PIN verified for: {command}")
            await self._dispatch_control_with_args(update, chat_id, command, cmd_args)
        else:
            error = result['error']
            if error == 'pin_expired':
                await self._send_response(update, "❌ 验证码已过期，请重新发送命令")
            elif error == 'too_many_attempts':
                await self._send_response(update, "❌ 验证失败次数过多，请重新发送命令")
            elif error == 'invalid_pin':
                await self._send_response(update, "❌ 验证码错误，请重试")

    # ==================== Command Registration ====================

    async def _register_commands(self) -> bool:
        """Register minimal commands in Telegram "/" menu (private chats only)."""
        try:
            from telegram import (
                BotCommand, BotCommandScopeAllPrivateChats,
                BotCommandScopeAllGroupChats, BotCommandScopeDefault,
            )

            commands = [
                BotCommand("menu", "操作面板"),
                BotCommand("s", "快速状态"),
                BotCommand("p", "查看持仓"),
                BotCommand("b", "账户余额"),
                BotCommand("a", "技术面"),
                BotCommand("fa", "立即分析"),
                BotCommand("profit", "盈亏分析"),
                BotCommand("close", "平仓"),
                BotCommand("help", "帮助"),
            ]

            # Clear all scopes
            await self.application.bot.set_my_commands([], scope=BotCommandScopeDefault())
            await self.application.bot.set_my_commands([], scope=BotCommandScopeAllGroupChats())
            self.logger.info("Cleared old bot commands from all scopes")

            # Register for private chats only
            await self.application.bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())
            self.logger.info(f"✅ Bot commands registered ({len(commands)} commands): {[c.command for c in commands]}")

            # Also register for default scope (ensures "/" menu appears everywhere)
            await self.application.bot.set_my_commands(commands, scope=BotCommandScopeDefault())
            self.logger.info("✅ Bot commands also registered in default scope")

            return True

        except Exception as e:
            self.logger.warning(f"Failed to register bot commands: {e}")
            return False

    # ==================== Webhook & Polling ====================

    async def _delete_webhook_standalone(self) -> bool:
        """Delete webhook before Application initialization."""
        try:
            from telegram import Bot
            bot = Bot(token=self.token)

            webhook_info = await bot.get_webhook_info()
            if webhook_info.url:
                self.logger.info(f"Found active webhook: {webhook_info.url}")
                await bot.delete_webhook(drop_pending_updates=True)
                self.logger.info("Webhook deleted successfully")
            else:
                self.logger.info("No active webhook found")

            await bot.close()
            return True

        except Exception as e:
            self.logger.warning(f"Failed to delete webhook (standalone): {e}")
            return False

    async def start_polling(self):
        """Start the command handler polling loop with conflict handling."""
        if not TELEGRAM_AVAILABLE:
            self.logger.error("Telegram not available")
            return

        # Delete any existing webhook
        self.logger.info("Pre-startup webhook cleanup...")
        await self._delete_webhook_standalone()

        self.logger.info(f"Waiting {self.startup_delay}s for Telegram servers to sync...")
        await asyncio.sleep(self.startup_delay)

        retry_count = 0

        while retry_count < self.polling_max_retries:
            try:
                self.application = Application.builder().token(self.token).build()

                # --- Register all handlers ---

                # Shortcut commands (registered in "/" menu)
                self.application.add_handler(
                    CommandHandler("s", lambda u, c: self._handle_query(u, c, 'status'))
                )
                self.application.add_handler(
                    CommandHandler("p", lambda u, c: self._handle_query(u, c, 'position'))
                )
                self.application.add_handler(
                    CommandHandler("b", lambda u, c: self._handle_query(u, c, 'balance'))
                )
                self.application.add_handler(
                    CommandHandler("a", lambda u, c: self._handle_query(u, c, 'analyze'))
                )
                self.application.add_handler(
                    CommandHandler("v", lambda u, c: self._handle_query(u, c, 'version'))
                )

                # Query commands (no PIN)
                for cmd_name in QUERY_COMMANDS:
                    self.application.add_handler(
                        CommandHandler(cmd_name, lambda u, c, n=cmd_name: self._handle_query(u, c, n))
                    )

                # Query commands with args
                for cmd_name in QUERY_COMMANDS_WITH_ARGS:
                    self.application.add_handler(
                        CommandHandler(cmd_name, lambda u, c, n=cmd_name: self._handle_query_with_args(u, c, n))
                    )
                # Shortcut: /l = logs
                self.application.add_handler(
                    CommandHandler("l", lambda u, c: self._handle_query_with_args(u, c, 'logs'))
                )

                # Control commands (PIN required)
                for cmd_name in CONTROL_COMMANDS:
                    self.application.add_handler(
                        CommandHandler(cmd_name, lambda u, c, n=cmd_name: self._handle_control(u, c, n))
                    )

                # Control commands with args (PIN required)
                for cmd_name in CONTROL_COMMANDS_WITH_ARGS:
                    self.application.add_handler(
                        CommandHandler(cmd_name, lambda u, c, n=cmd_name: self._handle_control(u, c, n))
                    )
                # Shortcuts: /fa = force_analysis, /pc = partial_close
                self.application.add_handler(
                    CommandHandler("fa", lambda u, c: self._handle_control(u, c, 'force_analysis'))
                )
                self.application.add_handler(
                    CommandHandler("pc", lambda u, c: self._handle_control(u, c, 'partial_close'))
                )

                # UI commands
                self.application.add_handler(CommandHandler("help", self.cmd_help))
                self.application.add_handler(CommandHandler("start", self.cmd_help))
                self.application.add_handler(CommandHandler("menu", self.cmd_menu))
                self.logger.info("Registered /menu, /help, /start handlers")

                # Inline keyboard callback handler
                self.application.add_handler(CallbackQueryHandler(self.handle_callback))

                # Error handler - log unhandled exceptions
                async def _error_handler(update, context):
                    self.logger.error(f"Telegram handler error: {context.error}", exc_info=context.error)
                self.application.add_error_handler(_error_handler)

                # PIN verification text handler (must come after command handlers)
                if self.enable_pin and MessageHandler and filters:
                    self.application.add_handler(
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_pin_input)
                    )
                    self.logger.info("PIN verification handler registered")

                self.logger.info("Starting Telegram command handler...")

                await self.application.initialize()

                # Post-init webhook cleanup
                self.logger.info("Post-init webhook cleanup...")
                await self.application.bot.delete_webhook(drop_pending_updates=True)

                # Register slash menu commands
                await self._register_commands()

                await self.application.start()
                await self.application.updater.start_polling(
                    allowed_updates=["message", "callback_query"],
                    drop_pending_updates=True,
                )

                self.is_running = True
                self.logger.info("Telegram command handler started successfully")

                stop_signal = asyncio.Event()
                await stop_signal.wait()

            except TelegramConflict as e:
                retry_count += 1
                delay = self.polling_base_delay * (2 ** (retry_count - 1))

                if retry_count < self.polling_max_retries:
                    self.logger.warning(
                        f"Telegram Conflict error. "
                        f"Retry {retry_count}/{self.polling_max_retries} in {delay}s: {e}"
                    )
                    if self.application:
                        try:
                            await self.application.shutdown()
                        except Exception:
                            pass
                        self.application = None

                    self.logger.info("Attempting webhook cleanup before retry...")
                    await self._delete_webhook_standalone()
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(
                        f"Telegram Conflict persists after {self.polling_max_retries} retries. "
                        f"Command handler disabled. Possible causes:\n"
                        f"  1. Another bot instance using the same token\n"
                        f"  2. External service setting webhooks\n"
                        f"  Run: curl 'https://api.telegram.org/bot<TOKEN>/deleteWebhook'"
                    )
                    self.is_running = False
                    return

            except Exception as e:
                self.logger.error(f"Failed to start command handler: {e}")
                self.is_running = False
                raise

    async def stop_polling(self):
        """Stop the command handler."""
        if self.application and self.is_running:
            try:
                self.logger.info("Stopping Telegram command handler...")
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                self.is_running = False
                self.logger.info("Command handler stopped")
            except Exception as e:
                self.logger.error(f"Error stopping command handler: {e}")
