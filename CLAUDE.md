# AItrader - NautilusTrader DeepSeek 交易机器人

## 项目概述
基于 NautilusTrader 框架的 AI 驱动加密货币交易系统，使用 DeepSeek AI 进行多代理辩论式信号生成。

## ⚠️ 关键信息

| 项目 | 值 |
|------|-----|
| **入口文件** | `main_live.py` (不是 main.py!) |
| **服务器 IP** | 139.180.157.152 |
| **用户名** | linuxuser |
| **安装路径** | /home/linuxuser/nautilus_AItrader |
| **服务名** | nautilus-trader |
| **分支** | main |
| **Python** | 3.12+ (必须) |
| **NautilusTrader** | 1.222.0 |
| **配置文件** | ~/.env.aitrader (永久存储) |
| **记忆文件** | data/trading_memory.json |

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

**修改后必须运行**：
```bash
python3 scripts/smart_commit_analyzer.py
# 预期: ✅ 所有规则验证通过
```

## 🏗️ TradingAgents 架构 (当前版本)

基于 [TradingAgents](https://github.com/TauricResearch/TradingAgents) (UCLA/MIT) 框架的多代理辩论架构。

### 决策流程 (6 次 AI 调用)

```
on_timer (15分钟)
  ↓
AIDataAssembler 聚合 13 类数据
  ↓
Phase 1: Bull/Bear 辩论 (×2 rounds = 4 AI calls)
  ├─ Bull Analyst (看多论据 + 历史记忆)
  └─ Bear Analyst (看空论据 + 历史记忆)
  ↓
Phase 2: Judge 决策 (1 AI call)
  └─ 量化决策框架 + 辩论总结 + 历史记忆
  ↓
Phase 3: Risk Manager (1 AI call)
  └─ SL/TP 设定 + 仓位大小 + 历史记忆
  ↓
validate_multiagent_sltp() → R/R >= 1.5:1 硬性门槛
  ↓
最终交易信号
```

### 三层时间框架 (MTF)

| 层级 | 时间框架 | 职责 |
|------|---------|------|
| 趋势层 | 1D | SMA_200 + MACD，Risk-On/Off 过滤 |
| 决策层 | 4H | Bull/Bear 辩论 + Judge 决策 |
| 执行层 | 15M | RSI 入场时机 + S/R 止损止盈 |

### 13 类数据覆盖

| # | 数据 | 必需 | 来源 |
|---|------|------|------|
| 1 | technical_data (15M) | ✅ | IndicatorManager |
| 2 | sentiment_data | ✅ | Binance 多空比 |
| 3 | price_data | ✅ | Binance ticker |
| 4 | order_flow_report | | BinanceKlineClient |
| 5 | derivatives_report (Coinalyze) | | CoinalyzeClient |
| 6 | binance_derivatives (Top Traders) | | BinanceDerivativesClient |
| 7 | orderbook_report | | BinanceOrderbookClient |
| 8 | mtf_decision_layer (4H) | | 技术指标 |
| 9 | mtf_trend_layer (1D) | | 技术指标 |
| 10 | current_position | | Binance |
| 11 | account_context | ✅ | Binance |
| 12 | historical_context | | 内部计算 |
| 13 | sr_zones_data | | S/R 计算器 |

### 记忆系统 (v5.9)

**文件**: `data/trading_memory.json` (最多 500 条)

**数据流**:
```
on_position_closed → evaluate_trade() → record_outcome() → trading_memory.json
                                                                 ↓
                            _get_past_memories() ← 读取 ←────────┘
                                     ↓
                      Bull / Bear / Judge / Risk (全部 6 次 AI 调用)
                                     ↓
                      Web API / Telegram Daily/Weekly 报告
```

**v5.9 关键**: 所有 4 个 Agent 都接收历史记忆:
- Bull/Bear/Risk: `PAST TRADE PATTERNS` 段落
- Judge: `PAST REFLECTIONS` 段落

### 交易评估框架

每笔交易平仓后自动评估 (`trading_logic.py:evaluate_trade()`):

| 等级 | 盈利交易 | 亏损交易 |
|------|---------|---------|
| A+ | R/R ≥ 2.5 | — |
| A | R/R ≥ 1.5 | — |
| B | R/R ≥ 1.0 | — |
| C | R/R < 1.0 (小盈利) | — |
| D | — | 亏损 ≤ 计划 SL × 1.2 (有纪律) |
| F | — | 亏损 > 计划 SL × 1.2 (失控) |

**Web 集成**: `TradeEvaluationService` 读取同一文件，提供:
- 公开 API: `/api/public/trade-evaluation/summary`, `/api/public/trade-evaluation/recent`
- 管理 API: `/api/admin/trade-evaluation/full`, `/api/admin/trade-evaluation/export`

### 核心架构决策 (仍生效)

| 版本 | 决策 | 说明 |
|------|------|------|
| v3.16 | S/R 硬风控移至 AI | Risk Manager prompt 包含 block_long/block_short，AI 自主判断 |
| v3.17 | R/R 驱动入场 | R/R ≥ 1.5:1 是唯一入场标准，由 `validate_multiagent_sltp()` 硬性执行 |
| v3.18 | 订单流程安全 | 反转两阶段提交、Bracket 失败不回退、加仓更新 SL/TP 数量 |
| v4.13 | 分步订单提交 | entry → on_position_opened → SL + TP 单独提交 (NT 1.222.0) |
| v4.14 | Risk Manager 只管风险 | 不重判方向，只设 SL/TP + 仓位，仅 R/R<1.5/FR>0.1%/流动性枯竭否决 |
| v4.17 | LIMIT 入场 | LIMIT @ validated entry_price 取代 MARKET，R/R 永不低于验证值 |
| v5.9 | 全 Agent 记忆 | 所有 4 个 Agent 接收 past_memories，不仅仅是 Judge |

## 📋 配置管理

### 分层架构

```
Layer 1: 代码常量 (业务规则，不可配置)
Layer 2: configs/base.yaml (所有业务参数)
Layer 3: configs/{env}.yaml (环境覆盖: production/development/backtest)
Layer 4: ~/.env.aitrader (仅 API keys 等敏感信息)
```

| 数据类型 | 正确来源 | 错误做法 |
|---------|---------|---------|
| **敏感信息** (API keys) | `~/.env.aitrader` | ❌ 写在代码或 YAML 中 |
| **业务参数** (止损比例等) | `configs/*.yaml` | ❌ 环境变量或代码硬编码 |
| **环境差异** (日志级别等) | `configs/{env}.yaml` | ❌ 在代码中 if/else 判断 |

### ConfigManager 使用

```python
from utils.config_manager import ConfigManager
config = ConfigManager(env='production')
config.load()
temperature = config.get('ai', 'deepseek', 'temperature')
```

### 命令行环境切换

```bash
python3 main_live.py --env production    # 生产 (15分钟, INFO)
python3 main_live.py --env development   # 开发 (1分钟, DEBUG)
python3 main_live.py --env backtest      # 回测 (无Telegram)
python3 main_live.py --env development --dry-run  # 验证配置
```

### 环境变量 (~/.env.aitrader)

```bash
# ===== 仅敏感信息 =====
BINANCE_API_KEY=xxx
BINANCE_API_SECRET=xxx
DEEPSEEK_API_KEY=xxx
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
COINALYZE_API_KEY=xxx          # 可选，无则自动降级
# ❌ 禁止放业务参数 (EQUITY, LEVERAGE 等应在 configs/*.yaml)
```

### 关键策略参数 (configs/base.yaml)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `position_sizing.method` | ai_controlled | 仓位计算方法 |
| `max_position_ratio` | 0.30 | 最大仓位比例 |
| `min_confidence_to_trade` | MEDIUM | 最低信心 |
| `trading_logic.min_rr_ratio` | 1.5 | R/R 硬性门槛 |
| `deepseek.model` | deepseek-chat | AI 模型 |
| `deepseek.temperature` | 0.3 | 温度参数 |
| `debate_rounds` | 2 | 辩论轮数 |
| `timer_interval_sec` | 900 | 分析间隔 (秒) |
| `agents.memory_file` | data/trading_memory.json | 记忆文件路径 |

完整参数列表参见 `configs/base.yaml`。

## 常用命令

```bash
# 全面诊断
python3 scripts/diagnose.py              # 运行全部检查
python3 scripts/diagnose.py --quick      # 快速检查
python3 scripts/diagnose.py --update --restart  # 更新+重启

# 实时诊断 (调用真实 API)
python3 scripts/diagnose_realtime.py
python3 scripts/diagnose_realtime.py --summary   # 仅关键结果
python3 scripts/diagnose_realtime.py --export --push  # 导出+推送

# 回归检测 (代码修改后必须运行)
python3 scripts/smart_commit_analyzer.py

# 服务器操作
sudo systemctl restart nautilus-trader
sudo journalctl -u nautilus-trader -f --no-hostname
```

### 服务器代码同步 (一行命令)

```bash
cd /home/linuxuser/nautilus_AItrader && sudo systemctl stop nautilus-trader && git fetch origin main && git reset --hard origin/main && find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null && echo "=== 最近提交 ===" && git log --oneline -5 && source venv/bin/activate && python3 scripts/diagnose_realtime.py
```

## 部署/升级

```bash
# 一键清空重装
curl -fsSL https://raw.githubusercontent.com/FelixWayne0318/AItrader/main/reinstall.sh | bash

# 普通升级
cd /home/linuxuser/nautilus_AItrader && git pull origin main && chmod +x setup.sh && ./setup.sh

# systemd 服务
sudo cp nautilus-trader.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable nautilus-trader && sudo systemctl restart nautilus-trader
```

## 常见错误避免

- ❌ 使用 `python` → ✅ **始终 `python3`**
- ❌ 使用 `main.py` → ✅ `main_live.py`
- ❌ 忘记 `AUTO_CONFIRM=true` → 会卡在确认提示
- ❌ Python 3.11 或更低 → ✅ 必须 3.12+ (NT 1.222.0 要求)
- ❌ 从后台线程访问 `indicator_manager` → ✅ 使用 `_cached_current_price` (Rust 不可跨线程)
- ❌ `nautilus_trader.core.nautilus_pyo3` 指标 → ✅ `nautilus_trader.indicators` (Cython 版本)
- ❌ `__init__.py` 自动导入 → ✅ 直接导入模块 (避免循环导入)
- ❌ `sentiment_data['key']` → ✅ `sentiment_data.get('key', default)` (防 KeyError)
- ❌ 环境变量存业务参数 → ✅ 业务参数只在 `configs/*.yaml`
- ❌ 服务器命令不带 cd → ✅ 始终先 `cd /home/linuxuser/nautilus_AItrader`
- ❌ `order_factory.bracket()` + `submit_order_list()` → ✅ 分步提交 (v4.13)
- ❌ Risk Manager 重判方向 → ✅ 只设 SL/TP + 仓位 (v4.14)
- ❌ BB/卖墙/OBI 否决方向 → ✅ 只调仓位大小 (v4.14)
- ❌ Bracket 失败回退无保护单 → ✅ CRITICAL 告警 + HOLD (v3.18)
- ❌ 反转交易直接平仓后开仓 → ✅ `_pending_reversal` 两阶段提交 (v3.18)
- ❌ 加仓后不更新 SL/TP 量 → ✅ `_update_sltp_quantity()` (v3.18)
- ❌ 仅 prompt 要求 R/R ≥ 1.5 → ✅ `validate_multiagent_sltp()` 硬性执行
- ❌ Funding Rate 精度 4 位 → ✅ 5 位小数 `:.5f` / `round(..., 6)` (匹配 Binance)

## 文件结构

```
/home/user/AItrader/
├── main_live.py              # 入口文件
├── setup.sh / reinstall.sh   # 部署脚本
├── requirements.txt
├── nautilus-trader.service    # systemd 服务
│
├── strategy/                 # 策略模块
│   ├── deepseek_strategy.py  # 主策略 (订单管理、事件处理)
│   └── trading_logic.py      # 交易逻辑 + evaluate_trade() 评估
│
├── agents/                   # 多代理系统
│   └── multi_agent_analyzer.py # Bull/Bear/Judge/Risk + 记忆系统
│
├── indicators/               # 技术指标
│   └── technical_manager.py  # Cython 版本 (不可用 Rust pyo3)
│
├── utils/                    # 工具模块
│   ├── config_manager.py     # 统一配置管理器
│   ├── deepseek_client.py    # DeepSeek AI 客户端
│   ├── ai_data_assembler.py  # 13 类数据聚合
│   ├── binance_kline_client.py       # K线 + 订单流 + Funding Rate
│   ├── binance_derivatives_client.py # Top Traders 多空比
│   ├── binance_orderbook_client.py   # 订单簿深度
│   ├── coinalyze_client.py   # OI + Liquidations
│   ├── sentiment_client.py   # Binance 多空比
│   ├── sr_zone_calculator.py # S/R 区域计算
│   ├── sr_sltp_calculator.py # S/R 基础 SL/TP
│   ├── telegram_bot.py       # Telegram 通知
│   ├── telegram_command_handler.py # Telegram 命令 (v3.0)
│   ├── binance_account.py    # 账户工具
│   ├── bar_persistence.py    # K线持久化
│   └── risk_controller.py    # 风险控制
│
├── configs/                  # 配置 (分层架构)
│   ├── base.yaml             # 基础配置 (所有参数)
│   ├── production.yaml       # 生产环境
│   ├── development.yaml      # 开发环境
│   └── backtest.yaml         # 回测环境
│
├── scripts/                  # 脚本工具
│   ├── diagnostics/          # 诊断模块 (15 个步骤)
│   │   ├── base.py           # 诊断基类
│   │   ├── ai_decision.py    # AI 决策验证
│   │   ├── architecture_verify.py # 架构合规检查
│   │   ├── order_flow_simulation.py # v3.18 订单流程模拟
│   │   └── ...
│   ├── diagnose.py           # 全面诊断
│   ├── diagnose_realtime.py  # 实时 API 诊断
│   └── smart_commit_analyzer.py # 回归检测
│
├── data/                     # 数据目录
│   ├── trading_memory.json   # 交易记忆 (运行后生成)
│   └── snapshots/
│
├── web/                      # Web 管理界面
│   ├── backend/              # FastAPI
│   │   ├── api/routes/       # public.py, admin.py, ...
│   │   └── services/         # trade_evaluation_service.py, ...
│   └── frontend/             # Next.js
│       ├── hooks/useTradeEvaluation.ts
│       └── components/trade-evaluation/  # 5 个评估组件
│
├── patches/                  # 兼容性补丁
│   ├── binance_enums.py      # 未知枚举处理
│   └── binance_positions.py  # 持仓处理
│
├── tests/                    # 测试
├── tools/                    # 运维工具
├── docs/                     # 文档
└── .github/workflows/        # CI/CD
```

## 🎨 Web 前端设计规范 (DipSway 风格)

### 导航栏设计

导航栏采用 **DipSway 风格**：透明背景 + 独立浮动组件组。

| 组件组 | 背景 | 说明 |
|--------|------|------|
| Logo (AlgVex) | 无背景 | Logo 图标 + 文字 |
| 导航链接 | `bg-background/60 backdrop-blur-xl border rounded-xl` | 独立浮动 |
| Bot Status / Signal / Markets | `bg-background/60 backdrop-blur-xl border rounded-xl` | 独立浮动 |
| CTA 按钮 | `bg-gradient-to-r from-primary to-primary/80` | 主色渐变 |

### 响应式设计

| 屏幕 | 显示内容 |
|------|----------|
| 桌面 (lg+) | 全部组件 |
| 手机横屏 | 同桌面 |
| 手机竖屏 | Logo + Bot Status + Signal + 汉堡菜单 |

### 前端部署

```bash
cd /home/linuxuser/nautilus_AItrader/web/frontend
rm -rf .next && npm run build && pm2 restart algvex-frontend
```

**关键**: 必须清除 `.next` 缓存，否则 Tailwind 响应式类可能失效。

## Telegram 命令 (v3.0)

**快捷菜单**: `/menu` (推荐入口), `/s` 状态, `/p` 持仓, `/b` 余额, `/a` 技术面, `/fa` 触发分析, `/close` 平仓, `/help`

**查询命令** (无需 PIN): `/status`, `/position`, `/balance`, `/analyze`, `/orders`, `/history`, `/risk`, `/daily`, `/weekly`, `/config`, `/version`, `/logs`

**控制命令** (需 PIN): `/pause`, `/resume`, `/close`, `/force_analysis`, `/partial_close 50`, `/set_leverage 10`, `/toggle trailing`, `/set min_confidence HIGH`, `/restart`

## GitHub Actions

| 工作流 | 触发 | 功能 |
|--------|------|------|
| Commit Analysis | push/PR to main | 回归检测 + AI 分析 + 依赖分析 |
| CodeQL Analysis | push/PR + 每周一 | 安全漏洞 + 代码质量 |
| Claude Code | issue/PR | Claude Code Action |

## 联系方式

- GitHub: FelixWayne0318
- 仓库: https://github.com/FelixWayne0318/AItrader
