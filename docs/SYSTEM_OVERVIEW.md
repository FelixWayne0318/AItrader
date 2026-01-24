# AItrader 系统功能全面概述

本文档对 AItrader 项目进行全面梳理，涵盖系统架构、核心功能、技术实现和运维要点。

## 1. 项目概述

AItrader 是一个基于 NautilusTrader 框架的 AI 驱动加密货币交易系统，专注于 Binance Futures BTCUSDT-PERP 永续合约交易。

| 项目 | 说明 |
|------|------|
| **入口文件** | `main_live.py` (非 main.py) |
| **框架** | NautilusTrader 1.221.0 |
| **AI 引擎** | DeepSeek API |
| **Python** | 3.11+ (必须) |
| **交易对** | BTCUSDT-PERP (BTC/USDT 永续合约) |
| **默认周期** | 15 分钟 K线 |

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    执行层 (NautilusTrader)                       │
│              TradingNode + Binance Live Client                   │
└────────────────────────────────────────────────────────────────┘
                            ▲
                            │ (事件驱动)
┌────────────────────────────────────────────────────────────────┐
│                    策略层 (DeepSeekAIStrategy)                   │
│  • on_bar() 处理K线       • on_order_filled() 订单成交           │
│  • on_position_opened()   • on_position_closed()                │
│  • on_timer() 定时分析    • Telegram 通知                        │
└────────────────────────────────────────────────────────────────┘
                            ▲
                    ┌───────┴────────┐
                    │                │
    ┌───────────────▼──────┐  ┌──────▼───────────────┐
    │   技术分析层          │  │   AI 决策层          │
    │  TechnicalManager     │  │  MultiAgentAnalyzer  │
    │                      │  │                       │
    │ • SMA 5/20/50        │  │ • Bull Analyst        │
    │ • RSI 14             │  │ • Bear Analyst        │
    │ • MACD 12/26/9       │  │ • Judge (决策者)      │
    │ • Bollinger 20       │  │ • Risk Evaluator      │
    │ • 支撑/阻力           │  │                       │
    └──────────────────────┘  └───────────────────────┘
                    │                │
    ┌───────────────┴────────────────┴──────────────┐
    │              数据获取层                         │
    │  • Binance Futures API (K线、订单、持仓)        │
    │  • Binance Long/Short Ratio API (情绪数据)     │
    │  • DeepSeek API (AI 分析)                      │
    └───────────────────────────────────────────────┘
```

---

## 3. 核心组件详解

### 3.1 入口文件 (`main_live.py`)

- 加载环境变量 (`~/.env.aitrader` → `.env`)
- 应用 Binance 枚举补丁 (处理未知 filter types)
- 创建策略配置 `DeepSeekAIStrategyConfig`
- 初始化 `TradingNode` 并注册 Binance 工厂
- 启动事件处理循环

### 3.2 策略核心 (`strategy/deepseek_strategy.py`)

**主要职责：**
- 接收市场数据事件 (K线、Tick)
- 调用 AI 分析器生成信号
- 执行订单 (Market + Bracket Orders)
- 管理止损止盈和移动止损
- 发送 Telegram 通知

**关键方法：**
| 方法 | 功能 |
|------|------|
| `on_start()` | 初始化指标、AI客户端、Telegram |
| `on_bar()` | 每根K线更新指标、触发分析 |
| `on_timer()` | 定时分析 (默认 900 秒) |
| `on_order_filled()` | 订单成交处理 |
| `on_position_opened/closed()` | 持仓变更处理 |
| `_execute_signal()` | 执行交易信号 |

**线程安全注意：**
- 使用 `_cached_current_price` 缓存价格
- Telegram 命令处理不直接访问 `indicator_manager`
- 使用 Cython 指标 (非 Rust PyO3) 避免线程 panic

### 3.3 多代理分析器 (`agents/multi_agent_analyzer.py`)

实现 TradingAgents 论文的层级决策架构：

```
技术数据 + 情绪数据
        ↓
[Bull Analyst] ←→ [Bear Analyst]  (辩论 2 轮)
        ↓
[Judge/Portfolio Manager]  (最终决策)
        ↓
[Risk Evaluator]  (仓位大小、SL/TP)
        ↓
最终信号: {signal, confidence, reason, SL, TP}
```

**AI 调用流程：**
1. Bull 分析 (做多论据)
2. Bear 分析 (做空论据)
3. Judge 决策 (量化评分，遵循规则)
4. Risk 评估 (仓位管理)

**决策规则 (Judge)：**
- Bullish count >= 3 → LONG + HIGH confidence
- Bearish count >= 3 → SHORT + HIGH confidence
- 2 vs 1 → 使用多数方向 + MEDIUM confidence
- 均衡 → HOLD + LOW confidence (应尽量避免)

### 3.4 技术指标管理器 (`indicators/technical_manager.py`)

使用 NautilusTrader 的 **Cython 指标**（非 Rust PyO3）：

| 指标 | 周期 | 用途 |
|------|------|------|
| SMA | 5, 20, 50 | 趋势判断 |
| EMA | 12, 26 | MACD 计算 |
| RSI | 14 | 超买/超卖 |
| MACD | 12/26/9 | 动量和趋势 |
| Bollinger | 20, 2σ | 波动率 |
| Volume MA | 20 | 成交量分析 |

**重要：** 必须使用 `from nautilus_trader.indicators import ...`，不能从 `nautilus_trader.core.nautilus_pyo3` 导入。

### 3.5 DeepSeek 客户端 (`utils/deepseek_client.py`)

- 构建结构化 Prompt (含技术数据、K线模式、情绪)
- 调用 DeepSeek API 生成信号
- JSON 解析和重试逻辑
- 信号历史记录追踪

### 3.6 情绪数据获取 (`utils/sentiment_client.py`)

- 调用 Binance Futures Long/Short Ratio API
- 免费、无需认证
- 返回多空比例和净情绪值

### 3.7 Telegram 集成

**`utils/telegram_bot.py`：**
- 发送交易通知 (信号、成交、持仓)
- 使用 `requests` 库直接调用 API (线程安全)
- Markdown 格式化和错误处理

**`utils/telegram_command_handler.py`：**
- 处理远程命令 (`/status`, `/position`, `/pause` 等)
- 内联键盘菜单支持
- 授权检查

### 3.8 Binance 补丁 (`patches/binance_enums.py`)

解决 NautilusTrader 与 Binance 的兼容性问题：

- 动态处理未知枚举值 (如 `POSITION_RISK_CONTROL`)
- 使用 `_missing_` 钩子创建伪成员
- 必须在导入 NautilusTrader 前应用

---

## 4. 交易逻辑流程

### 4.1 每根 K线的处理流程

```python
1. on_bar() 被触发
2. 更新所有技术指标
3. 获取情绪数据 (Binance L/S Ratio)
4. 获取账户余额 (真实 Equity)

5. AI 决策:
   a. MultiAgentAnalyzer.analyze()
      - Bull 分析 (AI call)
      - Bear 分析 (AI call)
      - Judge 决策 (AI call)
      - Risk 评估 (AI call)
   b. 返回: signal + confidence + SL + TP

6. 验证:
   - 最低信心阈值检查
   - SL 位置验证 (LONG SL < entry, SHORT SL > entry)
   - RSI 极值检查
   - 当前持仓检查

7. 订单执行:
   - 计算仓位大小 (基于 confidence multiplier)
   - 创建 Market Order + Bracket Order (SL + TP)
   - 提交订单

8. 监控:
   - 应用移动止损 (如果盈利)
   - 缓存当前价格
   - 发送 Telegram 通知
```

### 4.2 仓位计算逻辑

```python
final_usdt = base_usdt × conf_mult × trend_mult × rsi_mult

# 限制最大仓位
final_usdt = min(final_usdt, equity × max_position_ratio)

# 确保最低名义价值 ($100 Binance 最低要求)
final_usdt = max(final_usdt, 100)

btc_quantity = final_usdt / current_price
```

**信心乘数：**
- HIGH: 1.5x
- MEDIUM: 1.0x
- LOW: 0.5x

### 4.3 止损止盈计算

```python
# BUY 信号
SL = support × (1 - buffer) 或 entry × 0.98 (默认 2%)
TP = entry × (1 + tp_pct)  # tp_pct 基于信心等级

# SELL 信号
SL = resistance × (1 + buffer) 或 entry × 1.02 (默认 2%)
TP = entry × (1 - tp_pct)
```

**TP 百分比：**
- HIGH: 3%
- MEDIUM: 2%
- LOW: 1%

### 4.4 移动止损

```python
if profit_pct >= activation_pct:  # 默认 1%
    new_sl = current_price × (1 - trailing_distance)  # LONG
    if new_sl > current_sl and (new_sl - current_sl) > update_threshold:
        update_stop_loss(new_sl)
```

---

## 5. 配置管理

### 5.1 环境变量 (`~/.env.aitrader`)

```bash
# 必填
BINANCE_API_KEY=xxx
BINANCE_API_SECRET=xxx
DEEPSEEK_API_KEY=xxx

# 可选 (Telegram)
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx

# 运行参数
AUTO_CONFIRM=true  # 跳过确认提示
TIMEFRAME=15m
```

### 5.2 策略配置 (`configs/strategy_config.yaml`)

关键配置项：

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `equity` | 1000 | 备用资金 (实际使用真实余额) |
| `leverage` | 5 | 杠杆倍数 |
| `base_usdt_amount` | 100 | 基础仓位 |
| `min_confidence_to_trade` | LOW | 最低交易信心 |
| `timer_interval_sec` | 900 | 分析间隔 (15分钟) |
| `enable_trailing_stop` | true | 启用移动止损 |

---

## 6. 诊断工具

### 6.1 全面诊断 (`diagnose.py`)

```bash
python3 diagnose.py              # 完整检查
python3 diagnose.py --quick      # 跳过网络测试
python3 diagnose.py --update     # 更新代码后检查
python3 diagnose.py --restart    # 检查后重启服务
```

**检查项目：**
1. 系统环境 (Python 版本、虚拟环境)
2. 依赖包 (NautilusTrader 版本)
3. 文件完整性
4. 环境变量
5. 策略配置
6. 止损逻辑验证
7. Binance 补丁
8. 网络连接
9. API 认证
10. Systemd 服务状态
11. 进程检查
12. Git 状态
13. 模块导入测试

### 6.2 实时诊断 (`diagnose_realtime.py`)

调用真实 API 验证完整数据流：
- 获取真实 K线数据
- 调用 DeepSeek AI
- 生成完整信号
- 不模拟任何数据

---

## 7. 部署运维

### 7.1 服务管理

```bash
# 启动/停止/重启
sudo systemctl start|stop|restart nautilus-trader

# 查看日志
sudo journalctl -u nautilus-trader -f --no-hostname

# 查看状态
sudo systemctl status nautilus-trader
```

### 7.2 一键部署

```bash
# 完全重装
curl -fsSL https://raw.githubusercontent.com/FelixWayne0318/AItrader/main/reinstall.sh | bash

# 普通升级
cd /home/linuxuser/nautilus_AItrader && ./setup.sh
```

### 7.3 代码同步

```bash
cd /home/linuxuser/nautilus_AItrader
sudo systemctl stop nautilus-trader
git fetch origin main && git reset --hard origin/main
find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null
source venv/bin/activate
python3 diagnose_realtime.py
```

---

## 8. 已修复问题汇总

| 问题 | 修复 | Commit |
|------|------|--------|
| 止损价格在错误一侧 | 添加验证逻辑 | 7f940fb |
| CryptoOracle API 失效 | 替换为 Binance L/S Ratio | 07cd27f |
| Binance POSITION_RISK_CONTROL | 枚举 `_missing_` 钩子 | 1ed1357 |
| 非 ASCII 符号崩溃 | 升级 NautilusTrader 1.221.0 | - |
| Rust 指标线程 panic | 改用 Cython 指标 | - |
| Telegram webhook 冲突 | 预删除 webhook | - |
| 循环导入错误 | 移除 `__init__.py` 自动导入 | - |
| net_sentiment KeyError | 默认情绪数据添加必需字段 | - |
| 时间周期解析错误 | 检查顺序调整 | - |

---

## 9. 开发注意事项

### 9.1 代码修改规范

1. **必须调研**：官方文档 → 社区 Issues → 原始仓库
2. **禁止**：
   - 凭猜测修改代码
   - 忽略原始仓库实现
   - 不了解框架线程模型就修改异步代码

### 9.2 常见错误避免

- ❌ `python` → ✅ `python3`
- ❌ `main.py` → ✅ `main_live.py`
- ❌ 从 `nautilus_pyo3` 导入指标 → ✅ 从 `nautilus_trader.indicators` 导入
- ❌ 后台线程访问 `indicator_manager` → ✅ 使用 `_cached_current_price`
- ❌ 直接 `data['key']` → ✅ `data.get('key', default)`

---

## 10. 文件结构

```
/home/user/AItrader/
├── main_live.py              # 入口文件
├── strategy/
│   ├── deepseek_strategy.py  # 主策略
│   └── trading_logic.py      # 共享交易逻辑
├── agents/
│   └── multi_agent_analyzer.py # 多代理分析器
├── indicators/
│   └── technical_manager.py  # 技术指标
├── utils/
│   ├── deepseek_client.py    # DeepSeek AI
│   ├── sentiment_client.py   # 情绪数据
│   ├── telegram_bot.py       # Telegram 通知
│   ├── telegram_command_handler.py # 命令处理
│   ├── binance_account.py    # Binance 账户
│   └── bar_persistence.py    # K线持久化
├── patches/
│   ├── binance_enums.py      # 枚举补丁
│   └── binance_positions.py  # 持仓补丁
├── configs/
│   ├── strategy_config.yaml  # 策略配置
│   └── telegram_config.yaml  # Telegram 配置
├── diagnose.py               # 诊断工具
├── diagnose_realtime.py      # 实时诊断
├── setup.sh                  # 安装脚本
├── reinstall.sh              # 重装脚本
└── nautilus-trader.service   # Systemd 服务
```

---

*文档版本: 2026-01-24*
*适用于: AItrader v1.0 + NautilusTrader 1.221.0*
