# AItrader - NautilusTrader DeepSeek 交易机器人

## 项目概述
基于 NautilusTrader 框架的 AI 驱动加密货币交易系统，使用 DeepSeek AI 进行信号生成。

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

## 常见错误避免

- ❌ 使用 `python` 命令 → ✅ **始终使用 `python3`** (确保使用正确版本)
- ❌ 使用 `main.py` 作为入口 → ✅ 使用 `main_live.py`
- ❌ 忘记设置 `AUTO_CONFIRM=true` → 会卡在确认提示
- ❌ 止损在入场价错误一侧 → 已修复，会自动回退到默认2%
- ❌ 使用 Python 3.10 → ✅ 必须使用 Python 3.11+

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

## API 密钥 (保存在 ~/.env.aitrader)

```bash
# 编辑配置文件
nano ~/.env.aitrader
```

```
BINANCE_API_KEY=xxx
BINANCE_API_SECRET=xxx
DEEPSEEK_API_KEY=xxx
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
```

## 联系方式

- GitHub: FelixWayne0318
- 仓库: https://github.com/FelixWayne0318/AItrader
