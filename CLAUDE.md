# AItrader - NautilusTrader DeepSeek 交易机器人

## 项目概述
基于 NautilusTrader 框架的 AI 驱动加密货币交易系统，使用 DeepSeek AI 进行信号生成。

## 🚨 代码修改规范 (必读)

在修改任何代码之前，**必须**按以下顺序调研：

1. **官方文档** - NautilusTrader、python-telegram-bot 等框架的官方文档
2. **社区/GitHub Issues** - 查看是否有相关问题和解决方案
3. **原始仓库** - 对比 [Patrick-code-Bot/nautilus_AItrader](https://github.com/Patrick-code-Bot/nautilus_AItrader) 的实现
4. **提出方案** - 基于以上调研，结合当前系统问题，提出合理修改方案

**禁止**：
- ❌ 凭猜测直接修改代码
- ❌ 未经调研就"优化"或"改进"代码
- ❌ 忽略原始仓库的已验证实现
- ❌ 不了解框架线程模型就修改异步/多线程代码

**教训案例**：
- 将 `nautilus_trader.indicators` (Cython) 改为 `nautilus_trader.core.nautilus_pyo3` (Rust) 导致线程安全 panic
- 未研究 python-telegram-bot v20 的异步模型就混合使用 asyncio/threading

## ⚠️ 关键信息

| 项目 | 值 |
|------|-----|
| **入口文件** | `main_live.py` (不是 main.py!) |
| **服务器 IP** | 139.180.157.152 |
| **用户名** | linuxuser |
| **安装路径** | /home/linuxuser/nautilus_AItrader |
| **服务名** | nautilus-trader |
| **分支** | main |
| **Python** | 3.11+ (必须) |
| **NautilusTrader** | 1.221.0 |
| **配置文件** | ~/.env.aitrader (永久存储) |

## 配置文件管理

```
~/.env.aitrader          # 永久存储 (重装不删除)
     ↑
     │ 软链接
     │
.env ─┘                  # 项目目录中的软链接
```

| 位置 | 说明 |
|------|------|
| `~/.env.aitrader` | 永久存储，重装时自动保留 |
| `.env` | 软链接，指向 ~/.env.aitrader |

```bash
# 编辑配置
nano ~/.env.aitrader

# 查看软链接
ls -la /home/linuxuser/nautilus_AItrader/.env
```

## 部署/升级命令

```bash
# 一键清空重装 (完全重新安装)
curl -fsSL https://raw.githubusercontent.com/FelixWayne0318/AItrader/main/reinstall.sh | bash

# 或者本地执行
cd /home/linuxuser/nautilus_AItrader
chmod +x reinstall.sh && ./reinstall.sh

# 普通升级 (保留现有配置)
cd /home/linuxuser/nautilus_AItrader
git pull origin main
chmod +x setup.sh && ./setup.sh

# 安装/更新 systemd 服务
sudo cp nautilus-trader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable nautilus-trader
sudo systemctl restart nautilus-trader

# 查看日志
sudo journalctl -u nautilus-trader -f --no-hostname
```

## 常用命令

```bash
# 全面诊断 (唯一需要的检测工具)
python3 diagnose.py              # 运行全部检查
python3 diagnose.py --quick      # 快速检查 (跳过网络测试)
python3 diagnose.py --update     # 先更新代码再检查
python3 diagnose.py --restart    # 检查后重启服务
python3 diagnose.py --json       # 输出JSON格式

# 服务器操作
sudo systemctl restart nautilus-trader
sudo journalctl -u nautilus-trader -f --no-hostname

# 一键更新 + 重启
python3 diagnose.py --update --restart
```

### 服务器代码同步与实时诊断

完整流程 (强制同步远程代码 + 清除缓存 + 验证版本 + 运行诊断):

```bash
# 1. 进入项目目录
cd /home/linuxuser/nautilus_AItrader

# 2. 停止服务 (避免文件锁定)
sudo systemctl stop nautilus-trader

# 3. 强制同步远程代码 + 清除缓存
git fetch origin main
git reset --hard origin/main
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null

# 4. 显示最近提交记录 (验证版本)
echo ""
echo "========== 最近 5 次提交 =========="
git log --oneline -5
echo ""
echo "========== 当前 HEAD =========="
git rev-parse HEAD
echo ""

# 5. 激活虚拟环境
source venv/bin/activate

# 6. 运行实时诊断
python3 diagnose_realtime.py

# 7. (可选) 重启服务
# sudo systemctl start nautilus-trader
```

**一行命令版本** (复制粘贴即用):

```bash
cd /home/linuxuser/nautilus_AItrader && sudo systemctl stop nautilus-trader && git fetch origin main && git reset --hard origin/main && find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null && echo "=== 最近提交 ===" && git log --oneline -5 && source venv/bin/activate && python3 diagnose_realtime.py
```

| 步骤 | 命令 | 作用 |
|------|------|------|
| 停止服务 | `systemctl stop` | 避免运行中的进程锁定文件 |
| 强制同步 | `git reset --hard origin/main` | 丢弃本地修改，完全同步远程 |
| 清除缓存 | `find ... __pycache__` | 删除 Python 编译缓存，确保使用最新代码 |
| 显示提交 | `git log --oneline -5` | 核对 commit hash 确认版本 |
| 实时诊断 | `diagnose_realtime.py` | 调用真实 API，验证完整数据流 |

## systemd 服务配置

```ini
[Service]
ExecStart=/home/linuxuser/nautilus_AItrader/venv/bin/python main_live.py
Environment=AUTO_CONFIRM=true
```

## 已修复的问题

1. **止损Bug** (commit 7f940fb)
   - 问题：止损价格可能在入场价错误一侧
   - 修复：添加验证确保 LONG 止损 < 入场价，SHORT 止损 > 入场价

2. **CryptoOracle API** (commit 07cd27f)
   - 问题：API key 失效
   - 修复：替换为 Binance 多空比 API

3. **Binance POSITION_RISK_CONTROL** (commit 1ed1357)
   - 问题：Binance 新增 filter type，NautilusTrader 1.202.0 不支持
   - 错误：`msgspec.ValidationError: Invalid enum value 'POSITION_RISK_CONTROL'`
   - 修复：添加 `_missing_` 钩子动态处理未知枚举值
   - 文件：`patches/binance_enums.py`
   - 参考：[msgspec 官方方案](https://github.com/jcrist/msgspec/issues/531)

4. **非 ASCII 符号崩溃** (币安人生USDT-PERP) - **彻底修复**
   - 问题：Binance API 返回非 ASCII 符号导致 Rust 代码 panic
   - 错误：`Condition failed: invalid string for 'value' contained a non-ASCII char`
   - 根因：NautilusTrader 旧版本 Rust 代码只接受 ASCII
   - **最终修复**：升级到 Python 3.11 + NautilusTrader 1.221.0
   - 官方修复：[GitHub Issue #3053](https://github.com/nautechsystems/nautilus_trader/issues/3053), [PR #3105](https://github.com/nautechsystems/nautilus_trader/pull/3105)
   - 注意：1.211.0 只修复了 Currency，1.221.0 才完整修复 Symbol/PositionId

5. **LoggingConfig 兼容性** (NautilusTrader 1.202.0)
   - 问题：`log_file_format` 和 `log_colors` 参数不被支持
   - 修复：移除这两个参数

6. **多代理分歧处理** (skip_on_divergence) → **已被 TradingAgents 架构取代**
   - 问题：当 DeepSeek 和 MultiAgent 信号完全对立 (BUY vs SELL) 时，信号合并会导致过多 HOLD
   - **TradingAgents 修复**：改用层级决策架构，MultiAgent Judge 作为唯一决策者
   - 架构：Bull/Bear 辩论 (2 AI calls) → Judge 决策 (1 AI call, optimized prompt) → Risk 评估 (1 AI call) → 最终信号
   - 优化：Judge 使用量化决策框架，减少主观判断，降低 HOLD 比例
   - 参考：[TradingAgents Framework](https://github.com/TauricResearch/TradingAgents) UCLA/MIT 论文
   - 文件：`strategy/deepseek_strategy.py`, `agents/multi_agent_analyzer.py`
   - 注意：`skip_on_divergence` 和 `use_confidence_fusion` 配置项已标记为 LEGACY，不再生效

7. **时间周期解析Bug**
   - 问题：`15-MINUTE` 被错误解析为 `5m`
   - 原因：`5-MINUTE` 是 `15-MINUTE` 的子字符串
   - 修复：调整检查顺序，先检查更长的字符串
   - 影响文件：`deepseek_strategy.py`, `diagnose_realtime.py`

8. **Rust RSI 线程安全崩溃** (Telegram 命令处理)
   - 问题：服务崩溃，Rust panic: `RelativeStrengthIndex is unsendable, but sent to another thread`
   - 原因：Telegram 命令处理在后台线程 (Thread 7) 运行，访问了 `indicator_manager`
   - 根因：NautilusTrader 的 Rust 指标 (RSI, MACD) 不是 Send/Sync，不能跨线程访问
   - 修复：添加 `_cached_current_price` 变量，在 `on_bar` 中线程安全更新
   - 影响方法：`_cmd_status()`, `_cmd_position()` 改用缓存价格
   - 文件：`strategy/deepseek_strategy.py`

9. **Telegram Webhook 冲突** (polling 模式失败)
   - 问题：服务启动后持续报错 `can't use getUpdates method while webhook is active`
   - 原因：Bot 之前被设置了 webhook，与 polling 模式冲突
   - 根因：`delete_webhook()` 调用时机太晚，在 `Application.initialize()` 之后
   - 修复：添加 `_delete_webhook_standalone()` 方法，在初始化前先删除 webhook
   - 改进：双重删除 (初始化前 + 初始化后)，冲突重试时也删除
   - 文件：`utils/telegram_command_handler.py`
   - 手动修复：`curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook"`

10. **循环导入错误** (agents ↔ strategy)
    - 问题：启动时报错 `ImportError: cannot import name 'MultiAgentAnalyzer' from partially initialized module`
    - 原因：`agents/__init__.py` 导入 `multi_agent_analyzer` → 导入 `trading_logic` → 导入 `strategy` → 循环
    - 根因：`__init__.py` 中的自动导入触发了循环依赖链
    - 修复：移除 `agents/__init__.py` 和 `strategy/__init__.py` 中的自动导入
    - 使用方式：直接导入 `from agents.multi_agent_analyzer import MultiAgentAnalyzer`
    - 文件：`agents/__init__.py`, `strategy/__init__.py`

11. **DeepSeek net_sentiment KeyError** (情绪数据缺失)
    - 问题：AI 分析失败，报错 `KeyError: 'net_sentiment'`
    - 原因：当真实情绪数据不可用时，默认情绪结构缺少必需字段
    - 根因：默认情绪数据没有 `net_sentiment`, `positive_ratio`, `negative_ratio`
    - 修复：在默认情绪数据中添加所有必需字段
    - 防护：`_format_sentiment_data()` 改用 `.get()` 防止 KeyError
    - 文件：`strategy/deepseek_strategy.py`, `utils/deepseek_client.py`

12. **Telegram TCPTransport closed 错误** (跨事件循环问题)
    - 问题：发送 Telegram 消息时报错 `RuntimeError: unable to perform operation on <TCPTransport closed=True>`
    - 原因：python-telegram-bot v20+ 是完全异步的，不是线程安全的
    - 根因：混合 asyncio 和 threading 会导致 httpx 会话冲突
    - 修复：`send_message_sync` 改用 `requests` 直接调用 Telegram Bot API (官方推荐)
    - 参考：[PTB Discussion #4096](https://github.com/python-telegram-bot/python-telegram-bot/discussions/4096)
    - 文件：`utils/telegram_bot.py`

13. **Rust 指标线程安全 panic** (on_timer 崩溃)
    - 问题：服务崩溃，Rust panic: `RelativeStrengthIndex is unsendable, but sent to another thread`
    - 原因：使用 `nautilus_trader.core.nautilus_pyo3` 的 Rust 指标
    - 根因：Rust 指标有严格的 Send/Sync 检查，on_timer 在不同线程运行
    - 修复：改用 `nautilus_trader.indicators` 的 Cython 指标（与原始仓库一致）
    - 参考：[原始仓库](https://github.com/Patrick-code-Bot/nautilus_AItrader)
    - 文件：`indicators/technical_manager.py`
    - 注意：**不要**从 `nautilus_trader.core.nautilus_pyo3` 导入指标

## 常见错误避免

- ❌ 使用 `python` 命令 → ✅ **始终使用 `python3`** (确保使用正确版本)
- ❌ 使用 `main.py` 作为入口 → ✅ 使用 `main_live.py`
- ❌ 忘记设置 `AUTO_CONFIRM=true` → 会卡在确认提示
- ❌ 止损在入场价错误一侧 → 已修复，会自动回退到默认2%
- ❌ 使用 Python 3.10 → ✅ 必须使用 Python 3.11+
- ❌ 从后台线程访问 `indicator_manager` → ✅ 使用 `_cached_current_price` (Rust 指标不可跨线程)
- ❌ 使用 `nautilus_trader.core.nautilus_pyo3` 的指标 → ✅ 使用 `nautilus_trader.indicators` (Cython 版本，线程安全)
- ❌ 在 `__init__.py` 中自动导入 → ✅ 直接导入模块 (避免循环导入)
- ❌ 直接访问 `sentiment_data['key']` → ✅ 使用 `sentiment_data.get('key', default)` (防止 KeyError)
- ❌ **服务器命令不带 cd** → ✅ **始终先 cd 到项目目录**
  ```bash
  # 错误：直接执行命令会报 "not a git repository"
  git status

  # 正确：始终以 cd 开头
  cd /home/linuxuser/nautilus_AItrader && git status
  ```

## 文件结构

```
/home/user/AItrader/
├── main_live.py              # 入口文件 (不是 main.py!)
├── setup.sh                  # 一键部署脚本 (普通升级)
├── reinstall.sh              # 一键清空重装脚本 (完全重新安装)
├── requirements.txt          # Python 依赖
├── nautilus-trader.service   # systemd 服务文件
├── .claude/                  # Claude Code 配置
│   ├── settings.json         # 权限配置
│   └── skills/               # 自定义技能
│       ├── code-review/      # 代码审查 (多维度: bugs/安全/架构)
│       ├── deploy/           # 部署技能
│       ├── server-status/    # 服务器状态检查
│       ├── stop-loss-check/  # 止损验证
│       └── nautilustrader/   # NautilusTrader 参考文档
├── strategy/
│   └── deepseek_strategy.py  # 主策略 (含止损修复)
├── agents/
│   └── multi_agent_analyzer.py # 多代理分析 (Bull/Bear/Judge)
├── indicators/
│   └── technical_manager.py  # 技术指标管理器
├── utils/
│   ├── deepseek_client.py    # DeepSeek AI 客户端
│   ├── sentiment_client.py   # Binance 多空比 (替代 CryptoOracle)
│   ├── telegram_bot.py       # Telegram 通知
│   ├── telegram_command_handler.py # Telegram 命令处理
│   ├── bar_persistence.py    # K线数据持久化
│   └── oco_manager.py        # OCO 订单管理 (已由 NautilusTrader 内置替代)
├── patches/
│   ├── binance_enums.py      # Binance枚举兼容性补丁
│   └── binance_positions.py  # Binance持仓处理补丁
├── configs/
│   ├── strategy_config.yaml  # 策略配置
│   └── telegram_config.yaml  # Telegram 配置
├── tests/                    # 测试目录
│   ├── test_bracket_order.py # 括号订单测试
│   ├── test_integration_mock.py # 集成测试 (Mock)
│   ├── test_rounding_fix.py  # 四舍五入修复测试
│   └── test_strategy_components.py # 策略组件测试
├── test_sl_fix.py            # 止损修复测试 (根目录)
├── test_binance_patch.py     # 枚举补丁测试 (根目录)
├── test_multi_agent.py       # 多代理测试 (根目录)
├── diagnose.py               # 全面诊断工具 v2.0 (唯一检测脚本)
├── DEPLOYMENT.md             # 部署指南
└── README.md                 # 项目文档
```

## 配置参数完整列表

配置分为两部分：
- **敏感信息**: `~/.env.aitrader` (API 密钥等)
- **策略参数**: `configs/strategy_config.yaml`

### 环境变量 (~/.env.aitrader)

```bash
# 必填
BINANCE_API_KEY=xxx           # Binance API Key
BINANCE_API_SECRET=xxx        # Binance API Secret
DEEPSEEK_API_KEY=xxx          # DeepSeek AI API Key

# Telegram (可选，启用通知需要)
TELEGRAM_BOT_TOKEN=xxx        # Telegram Bot Token
TELEGRAM_CHAT_ID=xxx          # 你的个人用户 ID
```

### 策略参数 (configs/strategy_config.yaml)

#### 资金配置
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `equity` | 1000 | 备用资金值 (自动获取真实余额时不用) |
| `leverage` | 5 | 杠杆倍数 (建议 3-10) |
| `use_real_balance_as_equity` | true | 自动从 Binance 获取真实余额 |

#### 仓位管理
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `base_usdt_amount` | 100 | 基础仓位 USDT (Binance 最低 $100) |
| `high_confidence_multiplier` | 1.5 | 高信心仓位乘数 → $150 |
| `medium_confidence_multiplier` | 1.0 | 中等信心 → $100 |
| `low_confidence_multiplier` | 0.5 | 低信心 → $50 |
| `max_position_ratio` | 0.30 | 最大仓位比例 (30% of equity) |

#### 风险管理
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `min_confidence_to_trade` | MEDIUM | 最低交易信心 (LOW/MEDIUM/HIGH) |
| `skip_on_divergence` | true | AI 分歧时跳过交易 (保守模式后备) |
| `use_confidence_fusion` | true | 启用加权信心融合 (推荐) |
| `rsi_extreme_threshold_upper` | 70 | RSI 超买阈值 |
| `rsi_extreme_threshold_lower` | 30 | RSI 超卖阈值 |

**加权信心融合说明**：当 DeepSeek 和 MultiAgent 信号相反时 (BUY vs SELL)，使用信心更高的信号：
- HIGH 权重=3, MEDIUM=2, LOW=1
- 例：DeepSeek=BUY(HIGH) vs MultiAgent=SELL(MEDIUM) → 使用 BUY
- 只有权重相等时才跳过交易

#### 止损止盈
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enable_auto_sl_tp` | true | 启用自动止损止盈 |
| `sl_buffer_pct` | 0.001 | 止损缓冲 (0.1%) |
| `tp_high_confidence_pct` | 0.03 | 高信心止盈 3% |
| `tp_medium_confidence_pct` | 0.02 | 中等信心止盈 2% |
| `tp_low_confidence_pct` | 0.01 | 低信心止盈 1% |

#### 移动止损
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enable_trailing_stop` | true | 启用移动止损 |
| `trailing_activation_pct` | 0.01 | 盈利 1% 后启动 |
| `trailing_distance_pct` | 0.005 | 跟踪距离 0.5% |

#### AI 配置
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `deepseek.model` | deepseek-chat | DeepSeek 模型 |
| `deepseek.temperature` | 0.3 | 温度参数 |
| `debate_rounds` | 2 | 多代理辩论轮数 (1-3) |

#### 定时器
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `timer_interval_sec` | 900 | 分析间隔 (秒)，15分钟 |

### Telegram 命令

| 命令 | 说明 |
|------|------|
| `/menu` | 显示交互按钮菜单 |
| `/status` | 查看系统状态和真实余额 |
| `/position` | 查看当前持仓 |
| `/orders` | 查看挂单 |
| `/history` | 最近交易记录 |
| `/risk` | 风险指标 |
| `/pause` | 暂停交易 |
| `/resume` | 恢复交易 |
| `/close` | 平仓 |

### 修改配置

```bash
# 修改策略参数
nano /home/linuxuser/nautilus_AItrader/configs/strategy_config.yaml

# 修改 API 密钥
nano ~/.env.aitrader

# 修改后重启服务生效
sudo systemctl restart nautilus-trader
```

## 联系方式

- GitHub: FelixWayne0318
- 仓库: https://github.com/FelixWayne0318/AItrader
