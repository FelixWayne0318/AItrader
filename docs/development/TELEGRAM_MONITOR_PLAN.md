# 📱 Telegram 监控功能开发计划

**创建日期**: 2025-11-06  
**分支**: `feature/telegram-monitor`  
**基于**: `v1.2.0-beta.1` (feature/stop-PnL)  
**状态**: 🚧 规划中

---

## 🎯 功能目标

实现实时的 Telegram 监控和通知系统，让您能够：

1. **接收交易通知**
   - 📊 新交易信号（BUY/SELL）
   - ✅ 订单成交通知
   - 🎯 止盈/止损触发
   - 📈 持仓状态更新

2. **接收系统状态**
   - ⚡ 策略启动/停止
   - ⚠️ 错误和警告
   - 📉 性能指标
   - 💰 账户余额变化

3. **远程控制（可选）**
   - 🛑 暂停/恢复交易
   - 📊 查询当前状态
   - 📈 查看持仓信息

---

## 🏗️ 技术架构

### 核心组件

```
nautilus_deepseek/
├── utils/
│   ├── telegram_bot.py       # Telegram Bot 核心类 (NEW)
│   └── telegram_notifier.py  # 通知管理器 (NEW)
├── strategy/
│   └── deepseek_strategy.py  # 集成 Telegram 通知
├── configs/
│   └── telegram_config.yaml  # Telegram 配置 (NEW)
└── .env                       # Telegram Token (SECRET)
```

### 依赖库

```python
# requirements.txt 需要添加
python-telegram-bot>=20.0  # Telegram Bot API
```

---

## 📋 实现步骤

### 阶段 1: 基础设置 ⏳

**目标**: 创建 Telegram Bot 并实现基础连接

**任务清单**:
- [ ] 在 BotFather 创建 Telegram Bot
- [ ] 获取 Bot Token
- [ ] 添加 `python-telegram-bot` 到 `requirements.txt`
- [ ] 创建 `utils/telegram_bot.py` 基础类
- [ ] 配置 `.env` 添加 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`
- [ ] 实现简单的 "Hello World" 消息测试

**预估时间**: 1-2 小时

### 阶段 2: 通知系统 ⏳

**目标**: 实现各类交易通知

**任务清单**:
- [ ] 创建 `TelegramNotifier` 类
- [ ] 实现交易信号通知
- [ ] 实现订单成交通知
- [ ] 实现止盈/止损通知
- [ ] 实现错误/警告通知
- [ ] 添加消息模板和格式化

**预估时间**: 3-4 小时

### 阶段 3: 策略集成 ⏳

**目标**: 将 Telegram 通知集成到交易策略

**任务清单**:
- [ ] 修改 `deepseek_strategy.py` 添加 Telegram 集成
- [ ] 在 `on_start()` 发送启动通知
- [ ] 在交易信号生成时发送通知
- [ ] 在 `on_order_filled()` 发送成交通知
- [ ] 在 `on_position_opened/closed()` 发送持仓通知
- [ ] 在异常处理中发送错误通知

**预估时间**: 2-3 小时

### 阶段 4: 远程控制（可选）⏳

**目标**: 实现通过 Telegram 控制策略

**任务清单**:
- [ ] 实现命令处理器
- [ ] `/status` - 查询策略状态
- [ ] `/position` - 查看当前持仓
- [ ] `/pause` - 暂停交易
- [ ] `/resume` - 恢复交易
- [ ] 添加身份验证（仅允许特定用户）

**预估时间**: 3-4 小时

### 阶段 5: 测试和文档 ⏳

**任务清单**:
- [ ] 单元测试
- [ ] 集成测试
- [ ] 创建 `TELEGRAM_MONITOR_GUIDE.md` 用户文档
- [ ] 更新 `README.md`
- [ ] 更新 `QUICKSTART.md`

**预估时间**: 2-3 小时

---

## 💻 代码示例

### 1. 基础 Telegram Bot 类

```python
# utils/telegram_bot.py

import os
import logging
from telegram import Bot
from telegram.error import TelegramError

class TelegramBot:
    """Telegram Bot for trading notifications"""
    
    def __init__(self, token: str, chat_id: str, logger=None):
        self.token = token
        self.chat_id = chat_id
        self.bot = Bot(token=token)
        self.logger = logger or logging.getLogger(__name__)
        self.enabled = True
        
    async def send_message(self, message: str, parse_mode='Markdown'):
        """Send a text message"""
        if not self.enabled:
            return
            
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode
            )
            self.logger.info(f"📱 Telegram message sent: {message[:50]}...")
        except TelegramError as e:
            self.logger.error(f"❌ Failed to send Telegram message: {e}")
            
    def format_trade_signal(self, signal_data: dict) -> str:
        """Format trading signal for Telegram"""
        return f"""
🔔 *Trading Signal*

Signal: *{signal_data['signal']}*
Confidence: {signal_data['confidence']}
Price: ${signal_data['price']:,.2f}
Time: {signal_data['timestamp']}

Technical:
• RSI: {signal_data['rsi']:.2f}
• MACD: {signal_data['macd']:.4f}
• Support: ${signal_data['support']:,.2f}
• Resistance: ${signal_data['resistance']:,.2f}

AI Reasoning:
{signal_data['reasoning'][:200]}...
"""
```

### 2. 集成到策略

```python
# strategy/deepseek_strategy.py

class DeepSeekAIStrategy(Strategy):
    def __init__(self, config: DeepSeekAIStrategyConfig):
        super().__init__(config)
        # ... existing init ...
        
        # Telegram Bot
        self.telegram_bot = None
        if config.enable_telegram:
            try:
                from utils.telegram_bot import TelegramBot
                self.telegram_bot = TelegramBot(
                    token=config.telegram_bot_token,
                    chat_id=config.telegram_chat_id,
                    logger=self.log
                )
                self.log.info("✅ Telegram Bot initialized")
            except Exception as e:
                self.log.warning(f"⚠️ Failed to initialize Telegram Bot: {e}")
    
    def on_start(self):
        """Called when strategy starts"""
        # ... existing code ...
        
        # Send startup notification
        if self.telegram_bot:
            import asyncio
            asyncio.create_task(
                self.telegram_bot.send_message(
                    f"🚀 *Strategy Started*\n\n"
                    f"Instrument: {self.instrument_id}\n"
                    f"Timeframe: 15m\n"
                    f"Features: SL/TP, OCO, Trailing Stop, Partial TP"
                )
            )
```

### 3. 配置文件

```yaml
# configs/telegram_config.yaml

telegram:
  enabled: true
  bot_token: "${TELEGRAM_BOT_TOKEN}"  # From .env
  chat_id: "${TELEGRAM_CHAT_ID}"      # From .env
  
  # Notification settings
  notifications:
    trade_signals: true
    order_fills: true
    position_updates: true
    errors: true
    system_status: true
    
  # Message settings
  message_format: "markdown"
  include_charts: false  # Future: send chart images
  
  # Rate limiting
  max_messages_per_minute: 10
  quiet_hours:
    enabled: false
    start: "00:00"
    end: "08:00"
```

### 4. 环境变量

```bash
# .env

# Telegram Configuration
TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"  # From @BotFather
TELEGRAM_CHAT_ID="987654321"  # Your Telegram user ID
```

---

## 🧪 测试计划

### 单元测试

```python
# tests/test_telegram_bot.py

import pytest
from utils.telegram_bot import TelegramBot

@pytest.mark.asyncio
async def test_send_message():
    bot = TelegramBot(
        token=os.getenv("TELEGRAM_BOT_TOKEN"),
        chat_id=os.getenv("TELEGRAM_CHAT_ID")
    )
    
    await bot.send_message("Test message from unit test")
    # Should not raise exception

def test_format_trade_signal():
    bot = TelegramBot(token="test", chat_id="test")
    
    signal_data = {
        "signal": "BUY",
        "confidence": "HIGH",
        "price": 50000.0,
        # ... other data
    }
    
    message = bot.format_trade_signal(signal_data)
    assert "BUY" in message
    assert "HIGH" in message
```

### 集成测试

1. **启动通知测试**
   - 启动策略，验证收到 Telegram 启动消息

2. **交易信号测试**
   - 等待 AI 产生信号，验证收到信号通知

3. **订单成交测试**
   - 订单成交时，验证收到成交通知

4. **错误通知测试**
   - 模拟错误，验证收到错误通知

---

## 📊 Git 工作流

### 提交策略

使用小而频繁的提交（Plan A）：

```bash
# 阶段 1 完成后
git add utils/telegram_bot.py requirements.txt
git commit -m "feat: Add basic Telegram bot integration

- Created TelegramBot class with send_message capability
- Added python-telegram-bot>=20.0 to requirements
- Implemented basic error handling

Status: Basic bot functional, can send messages
Next: Implement notification templates"

# 阶段 2 完成后
git add utils/telegram_notifier.py
git commit -m "feat: Implement trading notification system

- Created TelegramNotifier with message templates
- Added formatters for signals, orders, positions
- Implemented rate limiting (10 msg/min)

Status: Notification system ready for integration
Next: Integrate with strategy"

# ... 继续按阶段提交
```

### 推送到 GitHub

```bash
# 每完成一个阶段后推送
git push origin feature/telegram-monitor
```

### 最终合并策略

```
Option 1: 分别测试，分别合并
feature/stop-PnL (测试7天) → main (v1.2.0)
feature/telegram-monitor (测试3天) → main (v1.3.0)

Option 2: 合并后一起测试
feature/stop-PnL → feature/telegram-monitor (本地测试)
feature/telegram-monitor → main (v1.3.0 包含所有功能)

推荐: Option 1 (更稳健)
```

---

## 🔒 安全注意事项

### 1. Token 保护

```bash
# .gitignore 应包含
.env
.env.*
telegram_config.local.yaml
```

### 2. 身份验证

```python
# utils/telegram_bot.py

ALLOWED_USER_IDS = [123456789]  # Your Telegram user ID

def is_authorized(self, user_id: int) -> bool:
    """Check if user is authorized"""
    return user_id in ALLOWED_USER_IDS
```

### 3. 敏感信息过滤

```python
def sanitize_message(self, message: str) -> str:
    """Remove sensitive information from messages"""
    # Don't send API keys, full account balance, etc.
    message = message.replace(self.api_key, "***")
    return message
```

---

## 📚 参考资源

### Telegram Bot API
- [python-telegram-bot 文档](https://docs.python-telegram-bot.org/)
- [Telegram Bot API 官方文档](https://core.telegram.org/bots/api)
- [BotFather](https://t.me/botfather) - 创建 Bot

### NautilusTrader 集成
- [NautilusTrader Events](https://nautilustrader.io/docs/concepts/events)
- [Strategy Lifecycle](https://nautilustrader.io/docs/concepts/strategies)

---

## 🎯 成功标准

功能完成标准：

- [ ] ✅ 可以发送交易信号通知
- [ ] ✅ 可以发送订单成交通知
- [ ] ✅ 可以发送持仓更新通知
- [ ] ✅ 可以发送错误/警告通知
- [ ] ✅ 消息格式清晰易读
- [ ] ✅ 不影响策略性能
- [ ] ✅ 有完整的错误处理
- [ ] ✅ 有详细的文档
- [ ] ✅ 通过所有测试

---

## 📝 当前状态

**分支**: `feature/telegram-monitor`  
**基于**: `v1.2.0-beta.1` (367a9ec)  
**包含功能**:
- ✅ 自动止损止盈
- ✅ OCO 管理
- ✅ 移动止损
- ✅ 部分止盈
- ⏳ Telegram 监控 (开发中)

**下一步**:
1. 在 Telegram 创建 Bot
2. 安装依赖并创建基础类
3. 实现通知系统
4. 集成到策略
5. 测试验证

---

## 🚀 开始开发

### 立即执行

```bash
# 1. 确认在正确的分支
git branch
# 应显示: * feature/telegram-monitor

# 2. 创建 Telegram Bot
# 打开 Telegram，搜索 @BotFather
# 发送 /newbot
# 按提示创建 Bot
# 保存 Bot Token

# 3. 获取您的 Chat ID
# 方法 1: 使用 @userinfobot
# 方法 2: 发送消息给您的 Bot，然后访问：
# https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates

# 4. 安装依赖
source /home/ubuntu/deepseek_venv/bin/activate
pip install python-telegram-bot

# 5. 开始编码！
# 创建 utils/telegram_bot.py
```

---

**Last Updated**: 2025-11-06  
**Author**: AI Assistant  
**Status**: 📋 Planning Complete - Ready to Start Development

