# AItrader 配置统一管理方案

> 版本: 2.5.3
> 日期: 2026-01-25
> 状态: **Phase 0 已完成，关联影响审查完成，补充 7 处遗漏，可实施 Phase 1-6**
> 审查: CONFIG_PROPOSAL_REVIEW.md

**v2.5.3 更新说明** (关联影响完整性审查):
- 🔴 **Phase 3 补充**: 添加 `agents/multi_agent_analyzer.py` 到修改列表 (导入语句需更新)
- 🔴 **Phase 4 补充**: 添加 `utils/deepseek_client.py` 到修改列表 (信号历史队列)
- 🔴 **Section 5.4.3 补充**: multi_agent_analyzer.py 导入失败诊断命令
- 🟡 **Section 5.4.7 新增**: 跨 Phase 综合诊断 (Phase 1-4 完成后验证)
- 🟡 **Section 5.6.3 扩展**: 补充嵌套 `.get()` 路径映射 (main_live.py:222-238)
- 🟡 **Section 3.5.5 新增**: 完整路径映射表 (旧路径 → 新路径，含特殊处理)
- ✅ 依赖链分析完成，7 处遗漏已全部修复

**v2.5.2 更新说明**:
- 🔴 **新增 Phase 6 文档更新清单**: 明确 CLAUDE.md 和 README.md 中 RSI 阈值更新要求 (75/25 → 70/30)
- ✅ 符合 CLAUDE.md 代码修改规范
- ✅ 符合 .claude/skills/code-review 审查标准

**v2.5.1 更新说明**:
- 🔴 **新增 Section 5.4.2.5**: Phase 2 回滚诊断 (main_live.py 配置加载失败)
- 🔴 **新增 Section 5.4.4.5**: Phase 5 回滚诊断 (CLI 环境切换失败)
- ✅ 关联影响完整性审查通过：所有 Phase 均有回滚方案

**v2.5 更新说明**:
- 🔴 **新增 Section 1.3**: 代码默认值不一致警告 (RSI 阈值 75/25 vs 70/30)
- 🔴 **新增 Section 3.3**: YAML 结构兼容层设计 (解决 `strategy.*` vs 扁平结构问题)
- 🔴 **重写 Section 5.4**: 按 Phase 回滚诊断命令 (具体可执行命令)
- 🟡 **新增 Section 5.7**: 配置迁移脚本设计 (旧结构 → 新结构)
- 🟡 **更新 base.yaml**: 新增诊断工具阈值配置

**v2.4 更新说明**:
- 新增 Section 5.6: Phase 间关联影响，包含依赖图、必须项详解、循环导入处理方案
- 扩展环境变量映射: 5 → 9 个核心变量 (新增 TEST_MODE, AUTO_CONFIRM, TESTNET API)
- 新增 Phase 1 必须项 (M1-M3) 和验证清单
- 新增敏感信息掩蔽实现要求

---

## 目录

1. [现状分析](#1-现状分析)
   - 1.5 [代码默认值不一致警告](#15-代码默认值不一致警告-) 🔴 **v2.5 新增**
2. [目标架构](#2-目标架构)
3. [配置文件设计](#3-配置文件设计)
   - 3.5 [YAML 结构兼容层](#35-yaml-结构兼容层-) 🔴 **v2.5 新增**
4. [ConfigManager 类设计](#4-configmanager-类设计)
5. [迁移计划](#5-迁移计划)
   - 5.4 [按 Phase 回滚诊断](#54-按-phase-回滚诊断) 🔴 **v2.5 重写**
   - 5.6 [Phase 间关联影响](#56-phase-间关联影响)
   - 5.7 [配置迁移脚本设计](#57-配置迁移脚本设计) 🟡 **v2.5 新增**
6. [验证规则](#6-验证规则)
7. [使用方式](#7-使用方式)
8. [Pydantic 升级建议](#8-pydantic-升级建议-可选)
9. [风险评估](#9-风险评估)
10. [总结](#10-总结)

---

## 1. 现状分析

### 1.1 当前配置分布

| 位置 | 参数数量 | 用途 | 问题 |
|------|---------|------|------|
| `~/.env.aitrader` | 8 | API 密钥、敏感信息 | ✅ 合理 |
| `configs/strategy_config.yaml` | 60+ | 策略参数 | ⚠️ 部分被硬编码覆盖 |
| `strategy/deepseek_strategy.py` | 45 | 策略默认值 | ⚠️ 部分与 YAML 重复 |
| `strategy/trading_logic.py` | 7 | 交易核心常量 | ❌ **新文件，未配置化** |
| `main_live.py` | 18 | 加载逻辑 + 硬编码 | ❌ **覆盖 YAML 配置** |
| `utils/*.py` | 12 | 工具类硬编码 | ❌ 分散 |

### 1.2 已识别的硬编码 (50 处需处理)

#### 🔴 紧急：配置冲突 (main_live.py 硬编码覆盖 YAML)

```python
# main_live.py:201 - YAML 配置被忽略！
deepseek_temperature=0.1,          # 硬编码 0.1
# strategy_config.yaml:41 定义为 0.3，但被覆盖

# main_live.py:214-215 - YAML 配置被忽略！
rsi_extreme_threshold_upper=75.0,  # 硬编码 75
rsi_extreme_threshold_lower=25.0,  # 硬编码 25
# strategy_config.yaml:60-61 定义为 70/30，但被覆盖

# main_live.py:187 - YAML 配置被忽略！
min_trade_amount=0.001,            # 硬编码
# strategy_config.yaml:23 定义为 0.001，但加载逻辑未使用
```

#### 交易核心参数 (P0 - 必须配置化)

```python
# strategy/trading_logic.py:294-296  [新文件]
MIN_NOTIONAL_USDT = 100.0          # Binance 最低名义价值

# strategy/trading_logic.py:311
MIN_NOTIONAL_SAFETY_MARGIN = 1.01  # 安全边际 1%

# strategy/trading_logic.py:370
MIN_SL_DISTANCE_PCT = 0.01         # 最小止损距离 1%

# strategy/trading_logic.py:374-376
DEFAULT_SL_PCT = 0.02              # 默认止损 2%
DEFAULT_TP_PCT_BUY = 0.03          # 默认止盈 3% (做多)
DEFAULT_TP_PCT_SELL = 0.03         # 默认止盈 3% (做空)

# strategy/trading_logic.py:379-383 [新增]
TP_PCT_CONFIG = {                  # 按信心级别的止盈配置
    'HIGH': 0.03,
    'MEDIUM': 0.02,
    'LOW': 0.01,
}

# strategy/trading_logic.py:324 [新增]
btc_quantity += 0.001              # 仓位精度调整步长

# strategy/deepseek_strategy.py:473
limit = 200                        # 历史K线获取数量
```

#### 网络重试参数 (P1)

```python
# strategy/deepseek_strategy.py:424-425
max_retries = 60                   # 合约发现重试次数
retry_interval = 1.0               # 重试间隔

# utils/telegram_command_handler.py:476-482
startup_delay = 5                  # Telegram 启动延迟
max_retries = 3                    # 轮询重试次数
base_delay = 10                    # 重试基础延迟

# utils/binance_account.py:55,78
_cache_ttl = 5.0                   # 余额缓存时间
recvWindow = 5000                  # Binance 接收窗口

# utils/sentiment_client.py:89
timeout = 10                       # 情绪数据请求超时

# utils/telegram_bot.py:185
timeout = 30                       # 消息发送超时

# utils/bar_persistence.py:346 [新增]
max_limit = 1500                   # Binance K线最大获取数量

# utils/bar_persistence.py:349 [新增]
timeout = 10                       # K线数据请求超时 (秒)

# utils/oco_manager.py:89-90 [新增]
socket_timeout = 5                 # Redis socket 超时
socket_connect_timeout = 5         # Redis 连接超时
```

#### 指标参数 (P1 补充)

```python
# indicators/technical_manager.py:39-40 [新增]
volume_ma_period: int = 20         # 成交量 MA 周期
support_resistance_lookback: int = 20  # 支撑阻力回看周期
```

#### AI/分析参数 (P2)

```python
# utils/deepseek_client.py:58
maxlen = 30                        # 信号历史队列大小

# agents/multi_agent_analyzer.py:83
retry_delay = 1.0                  # API 重试延迟

# agents/multi_agent_analyzer.py:138
max_json_retries = 2               # JSON 解析重试次数
```

#### 测试模式参数 (P3 - 已正确处理)

```python
# main_live.py:191-195 (基于 timeframe 动态切换)
# 1分钟模式特殊值 - 这是正确的条件逻辑，不需要配置化
sma_periods = [3, 7, 15] if timeframe == '1m' else [5, 20, 50]
rsi_period = 7 if timeframe == '1m' else 14
macd_fast = 5 if timeframe == '1m' else 12
```

### 1.3 硬编码统计汇总

| 类别 | 数量 | 状态 |
|------|------|------|
| 🔴 紧急配置冲突 | 3 | ✅ **已修复** (Phase 0 完成) |
| P0 交易核心参数 | 9 | 必须配置化 |
| P1 网络重试参数 | 14 | 应该配置化 |
| P1 指标参数 | 2 | 应该配置化 (新增) |
| P2 AI/分析参数 | 3 | 应该配置化 |
| P3 测试模式参数 | 4 | ✅ 已正确处理 |
| ✅ 已配置化 | 15 | 无需处理 |
| **总计待处理** | **28** | (3 处已修复) |

### 1.4 当前加载优先级 (问题所在)

```
环境变量 (.env) → YAML → 代码硬编码覆盖 ← 问题！
                              ↑
                    main_live.py 硬编码值覆盖了 YAML 配置
```

### 1.5 代码默认值不一致警告 🔴

> ⚠️ **此问题必须在 Phase 1 实施前修复，否则 YAML 加载失败时会使用错误的默认值**

**问题描述**: `DeepSeekAIStrategyConfig` 类中的默认值与 `strategy_config.yaml` 不一致。

| 参数 | YAML 值 (正确) | 代码默认值 (错误) | 文件位置 |
|------|---------------|-----------------|---------|
| `rsi_extreme_threshold_upper` | 70 | ~~75.0~~ **70.0** ✅ | `strategy/deepseek_strategy.py:94` |
| `rsi_extreme_threshold_lower` | 30 | ~~25.0~~ **30.0** ✅ | `strategy/deepseek_strategy.py:95` |

**状态**: ✅ **已修复** (commit d7701d3)

**影响分析**:
- 正常情况: YAML 配置加载成功，使用 70/30 ✅
- 异常情况: YAML 加载失败，回退到代码默认值 ~~75/25~~ **70/30** ✅
- 后果: ~~RSI 极值检测行为不一致~~ **已修复，代码与 YAML 一致**

**验证命令**:

```bash
# 检查当前代码默认值
grep -n "rsi_extreme_threshold" strategy/deepseek_strategy.py | head -4

# 检查 YAML 配置值
grep -n "rsi_extreme_threshold" configs/strategy_config.yaml
```

**修复记录**:

```python
# strategy/deepseek_strategy.py - 已修改默认值与 YAML 一致
@dataclass
class DeepSeekAIStrategyConfig:
    # ...
    rsi_extreme_threshold_upper: float = 70.0  # ✅ 已从 75.0 改为 70.0
    rsi_extreme_threshold_lower: float = 30.0  # ✅ 已从 25.0 改为 30.0
```

**修复验证清单**:
- [x] `strategy/deepseek_strategy.py` 默认值已修改为 70.0/30.0
- [ ] 运行 `python3 -c "from strategy.deepseek_strategy import DeepSeekAIStrategyConfig; c = DeepSeekAIStrategyConfig(); print(c.rsi_extreme_threshold_upper, c.rsi_extreme_threshold_lower)"` 输出 `70.0 30.0` (需在服务器 venv 中验证)
- [ ] 运行 `python3 diagnose.py --quick` 无 RSI 相关警告 (需在服务器验证)

---

## 2. 目标架构

### 2.1 新架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        配置加载流程                              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. 加载 configs/base.yaml (所有参数完整定义 + 默认值)           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. 加载环境配置 (根据 --env 参数)                               │
│     • configs/production.yaml  (生产环境覆盖)                    │
│     • configs/development.yaml (开发环境覆盖)                    │
│     • configs/backtest.yaml    (回测环境覆盖)                    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. 加载 ~/.env.aitrader (敏感信息覆盖)                          │
│     • API_KEY, API_SECRET, BOT_TOKEN 等                         │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. ConfigManager.validate() (类型检查 + 范围验证 + 依赖检查)     │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. 生成 DeepSeekAIStrategyConfig (类型安全的配置对象)           │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 设计原则

| 原则 | 说明 |
|------|------|
| **单一来源** | 所有参数只在 `base.yaml` 定义一次 |
| **分层覆盖** | base → environment → .env，后者覆盖前者 |
| **类型安全** | 配置加载时进行类型验证 |
| **范围检查** | 数值参数检查合理范围 |
| **环境隔离** | 生产/开发/回测环境独立配置 |
| **敏感分离** | API 密钥只存放在 .env，不进入 git |
| **禁止硬编码覆盖** | main_live.py 不得硬编码覆盖 YAML 值 |

---

## 3. 配置文件设计

### 3.1 文件结构

```
AItrader/
├── configs/
│   ├── base.yaml           # 完整配置定义 (所有参数 + 默认值)
│   ├── production.yaml     # 生产环境覆盖
│   ├── development.yaml    # 开发环境覆盖
│   ├── backtest.yaml       # 回测环境覆盖
│   └── schema.json         # JSON Schema (可选，用于验证)
├── ~/.env.aitrader         # 敏感信息 (不进入 git)
└── utils/
    └── config_manager.py   # 配置管理器
```

### 3.2 base.yaml 完整定义

```yaml
# configs/base.yaml
# AItrader 配置文件 - 所有参数的完整定义
# 此文件包含所有配置项的默认值，是配置的唯一来源
# 版本: 2.0

# =============================================================================
# 交易配置
# =============================================================================
trading:
  # 交易对配置
  instrument_id: "BTCUSDT-PERP.BINANCE"
  bar_type: "BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-EXTERNAL"

  # 数据获取
  historical_bars_limit: 200      # 启动时获取的历史K线数量

# =============================================================================
# 交易逻辑常量 (来自 strategy/trading_logic.py)
# =============================================================================
trading_logic:
  # Binance 交易限制
  min_notional_usdt: 100.0        # Binance 最低名义价值 (不建议修改)
  min_notional_safety_margin: 1.01  # 安全边际 1%

  # 止损止盈默认值
  min_sl_distance_pct: 0.01       # 最小止损距离 1%
  min_tp_distance_pct: 0.005      # 最小止盈距离 0.5%
  default_sl_pct: 0.02            # 默认止损 2%
  default_tp_pct: 0.03            # 默认止盈 3%

  # 按信心级别的止盈配置 [新增]
  tp_pct_by_confidence:
    high: 0.03                    # 高信心: 3%
    medium: 0.02                  # 中等信心: 2%
    low: 0.01                     # 低信心: 1%

  # 仓位精度调整 [新增]
  quantity_adjustment_step: 0.001 # BTC 仓位调整步长

# =============================================================================
# 资金配置
# =============================================================================
capital:
  equity: 1000                    # 备用资金值 (当无法获取真实余额时使用)
  leverage: 5                     # 杠杆倍数 (建议 3-10)
  use_real_balance_as_equity: true  # 自动从 Binance 获取真实余额

# =============================================================================
# 仓位管理
# =============================================================================
position:
  base_usdt_amount: 100           # 基础仓位 USDT (Binance 最低 $100)
  high_confidence_multiplier: 1.5   # 高信心仓位乘数
  medium_confidence_multiplier: 1.0 # 中等信心仓位乘数
  low_confidence_multiplier: 0.5    # 低信心仓位乘数
  max_position_ratio: 0.30        # 最大仓位比例 (占 equity 的比例)
  trend_strength_multiplier: 1.2  # 趋势强度乘数
  min_trade_amount: 0.001         # 最小交易量 (BTC)
  adjustment_threshold: 0.001     # 仓位调整阈值 (BTC)

# =============================================================================
# 技术指标
# =============================================================================
indicators:
  # SMA 配置
  sma_periods: [5, 20, 50]

  # EMA 配置
  ema_periods: [12, 26]

  # RSI 配置
  rsi_period: 14

  # MACD 配置
  macd_fast: 12
  macd_slow: 26
  macd_signal: 9

  # 布林带配置
  bb_period: 20
  bb_std: 2.0

  # 其他
  volume_ma_period: 20
  support_resistance_lookback: 20

# =============================================================================
# AI 配置
# =============================================================================
ai:
  # DeepSeek 配置
  deepseek:
    model: "deepseek-chat"
    temperature: 0.3              # 注意: main_live.py 曾硬编码为 0.1
    max_retries: 2
    retry_delay: 1.0              # 新增: API 重试延迟
    base_url: "https://api.deepseek.com"

  # 多代理辩论配置
  multi_agent:
    debate_rounds: 2              # 辩论轮数 (1-3)
    retry_delay: 1.0              # 重试延迟 (秒)
    json_parse_max_retries: 2     # 新增: JSON 解析重试

  # 信号处理
  signal:
    history_count: 30             # 新增: 信号历史队列大小 (原 maxlen=30)
    skip_on_divergence: true      # [LEGACY] AI 分歧时跳过交易
    use_confidence_fusion: true   # [LEGACY] 不再使用

# =============================================================================
# 情绪数据
# =============================================================================
sentiment:
  enabled: true
  provider: "binance"             # binance / cryptooracle (已弃用)
  lookback_hours: 4
  timeframe: "15m"
  weight: 0.30                    # 决策权重
  timeout: 10                     # 新增: 请求超时 (秒)

# =============================================================================
# 风险管理
# =============================================================================
risk:
  # 信心阈值
  min_confidence_to_trade: "MEDIUM"  # LOW / MEDIUM / HIGH
  allow_reversals: true
  require_high_confidence_for_reversal: false

  # RSI 阈值 - 注意: main_live.py 曾硬编码为 75/25
  rsi_extreme_threshold_upper: 70.0  # RSI 超买阈值
  rsi_extreme_threshold_lower: 30.0  # RSI 超卖阈值
  rsi_extreme_multiplier: 0.7

  # 止损止盈
  stop_loss:
    enabled: true
    use_support_resistance: true
    buffer_pct: 0.001             # 缓冲 0.1%

  take_profit:
    high_confidence_pct: 0.03     # 高信心: 3%
    medium_confidence_pct: 0.02   # 中等信心: 2%
    low_confidence_pct: 0.01      # 低信心: 1%

  # 移动止损
  trailing_stop:
    enabled: true
    activation_pct: 0.01          # 盈利 1% 后启动
    distance_pct: 0.005           # 跟踪距离 0.5%
    update_threshold_pct: 0.002   # 更新阈值 0.2%

  # OCO 订单
  oco:
    enabled: true                 # 控制孤儿订单清理

# =============================================================================
# 网络配置
# =============================================================================
network:
  # 合约发现重试
  instrument_discovery:
    max_retries: 60               # 最大重试次数
    retry_interval: 1.0           # 重试间隔 (秒)

  # Binance API
  binance:
    recv_window: 5000             # 接收窗口 (ms)
    balance_cache_ttl: 5.0        # 余额缓存时间 (秒)

  # K线数据持久化 [新增]
  bar_persistence:
    max_limit: 1500               # Binance K线最大获取数量
    timeout: 10                   # 请求超时 (秒)

  # OCO 订单管理 (Redis) [新增]
  oco_manager:
    socket_timeout: 5             # Redis socket 超时 (秒)
    socket_connect_timeout: 5     # Redis 连接超时 (秒)

  # Telegram
  telegram:
    startup_delay: 5              # 启动延迟 (秒)
    polling_max_retries: 3        # 轮询最大重试次数
    polling_base_delay: 10        # 轮询重试基础延迟 (秒)
    message_timeout: 30           # 消息发送超时 (秒)

# =============================================================================
# Telegram 通知
# =============================================================================
telegram:
  enabled: true
  # bot_token 和 chat_id 从 .env 读取

  # 通知类型
  notify:
    signals: true
    fills: true
    positions: true
    errors: true

# =============================================================================
# 定时器配置
# =============================================================================
timing:
  timer_interval_sec: 900         # 分析间隔 (秒)，15分钟

# =============================================================================
# 日志配置
# =============================================================================
logging:
  level: "INFO"
  to_file: true
  file: "logs/deepseek_strategy.log"
  log_signals: true
  log_positions: true
  log_ai_responses: true

# =============================================================================
# 诊断工具阈值 (diagnose_realtime.py 使用) 🟡 v2.5 新增
# =============================================================================
diagnostics:
  # 布林带阈值
  bb_overbought_threshold: 80       # BB% 超买阈值
  bb_oversold_threshold: 20         # BB% 超卖阈值

  # 多空比阈值
  ls_ratio_extreme_bullish: 2.0     # 极度看多阈值
  ls_ratio_bullish: 1.5             # 看多阈值
  ls_ratio_extreme_bearish: 0.5     # 极度看空阈值
  ls_ratio_bearish: 0.7             # 看空阈值

  # MACD 阈值
  macd_strong_signal_threshold: 50  # 强信号阈值

  # 成交量阈值
  volume_spike_multiplier: 2.0      # 成交量突增倍数
```

> **说明**: 诊断工具阈值用于 `diagnose_realtime.py` 中的市场状态判断。
> 将这些值配置化可确保诊断工具与策略使用相同的判断标准。

### 3.3 production.yaml (生产环境覆盖)

```yaml
# configs/production.yaml
# 生产环境配置覆盖

capital:
  leverage: 5                     # 生产环境使用较低杠杆

timing:
  timer_interval_sec: 900         # 15分钟

logging:
  level: "INFO"
```

### 3.4 development.yaml (开发环境覆盖)

```yaml
# configs/development.yaml
# 开发/测试环境配置覆盖

trading:
  bar_type: "BTCUSDT-PERP.BINANCE-1-MINUTE-LAST-EXTERNAL"

capital:
  leverage: 3                     # 测试用低杠杆

# 1分钟模式特殊指标参数
indicators:
  sma_periods: [3, 7, 15]
  rsi_period: 7
  macd_fast: 5
  macd_slow: 10
  bb_period: 10

timing:
  timer_interval_sec: 60          # 1分钟

logging:
  level: "DEBUG"
```

### 3.5 YAML 结构兼容层 🔴

> ⚠️ **关键决策**: 当前 `strategy_config.yaml` 使用 `strategy.*` 前缀结构，与 `base.yaml` 设计的扁平结构不同

#### 3.5.1 结构对比

| 位置 | 当前结构 (`strategy_config.yaml`) | 设计结构 (`base.yaml`) |
|------|--------------------------------|----------------------|
| 仓位配置 | `strategy.position_management.base_usdt_amount` | `position.base_usdt_amount` |
| AI 配置 | `strategy.deepseek.temperature` | `ai.deepseek.temperature` |
| 风险配置 | `strategy.risk.rsi_extreme_threshold_upper` | `risk.rsi_extreme_threshold_upper` |
| 指标配置 | `strategy.indicators.rsi_period` | `indicators.rsi_period` |

#### 3.5.2 解决方案: 兼容层

**推荐方案**: 在 ConfigManager 中实现路径别名兼容层

```python
# ConfigManager 兼容层设计
class ConfigManager:
    # 路径别名映射: 旧路径 → 新路径
    PATH_ALIASES = {
        ('strategy', 'position_management'): ('position',),
        ('strategy', 'deepseek'): ('ai', 'deepseek'),
        ('strategy', 'risk'): ('risk',),
        ('strategy', 'indicators'): ('indicators',),
        ('strategy', 'equity'): ('capital', 'equity'),
        ('strategy', 'leverage'): ('capital', 'leverage'),
    }

    def get(self, *path, default=None) -> Any:
        """
        获取配置值，支持路径别名兼容

        示例:
        - config.get('strategy', 'position_management', 'base_usdt_amount')
          → 自动映射到 config.get('position', 'base_usdt_amount')
        """
        # 1. 先尝试原始路径
        value = self._get_nested(self._config, path)
        if value is not None:
            return value

        # 2. 尝试路径别名
        for old_prefix, new_prefix in self.PATH_ALIASES.items():
            if path[:len(old_prefix)] == old_prefix:
                new_path = new_prefix + path[len(old_prefix):]
                value = self._get_nested(self._config, new_path)
                if value is not None:
                    self.logger.debug(f"Path alias: {path} → {new_path}")
                    return value

        return default
```

#### 3.5.3 迁移策略

| 阶段 | 操作 | 兼容性 |
|------|------|--------|
| Phase 1 | ConfigManager 支持两种路径 | 旧代码继续工作 |
| Phase 2 | main_live.py 使用新路径 | 旧 YAML 通过别名访问 |
| Phase 3-4 | 其他文件使用新路径 | 旧 YAML 通过别名访问 |
| Phase 5 | 迁移 YAML 到新结构 | 移除别名兼容层 |
| Phase 6 | 删除 PATH_ALIASES | 只支持新结构 |

#### 3.5.4 兼容层验证

```bash
# 验证兼容层工作正常
python3 -c "
from utils.config_manager import ConfigManager
config = ConfigManager()
config.load()

# 测试两种路径都能访问
old_path = config.get('strategy', 'position_management', 'base_usdt_amount')
new_path = config.get('position', 'base_usdt_amount')
print(f'Old path: {old_path}')
print(f'New path: {new_path}')
assert old_path == new_path, 'Path alias not working!'
print('✅ 兼容层验证通过')
"
```

#### 3.5.5 完整路径映射表 🟡

**旧路径 → 新路径映射**:

| 旧路径 (strategy_config.yaml) | 新路径 (base.yaml) | 兼容方式 | 备注 |
|------------------------------|-------------------|---------|------|
| `strategy.instrument_id` | `trading.instrument_id` | 别名映射 | ✅ |
| `strategy.bar_type` | `trading.bar_type` | 别名映射 | ✅ |
| `strategy.equity` | `capital.equity` | 别名映射 | ✅ |
| `strategy.leverage` | `capital.leverage` | 别名映射 | ✅ |
| `strategy.use_real_balance_as_equity` | `capital.use_real_balance_as_equity` | 别名映射 | ✅ |
| `strategy.position_management.*` | `position.*` | 别名映射 | ✅ |
| `strategy.indicators.*` | `indicators.*` | 别名映射 | ✅ |
| `strategy.deepseek.*` | `ai.deepseek.*` | 别名映射 | ✅ |
| `strategy.risk.rsi_extreme_threshold_*` | `risk.rsi_extreme_threshold_*` | 别名映射 | ✅ |
| `strategy.risk.skip_on_divergence` | `ai.signal.skip_on_divergence` | ⚠️ 路径变化 | 特殊处理 |
| `strategy.risk.use_confidence_fusion` | `ai.signal.use_confidence_fusion` | ⚠️ 路径变化 | 特殊处理 |
| `strategy.telegram.*` | `telegram.*` | 别名映射 | ✅ |
| `strategy.timer_interval_sec` | `timing.timer_interval_sec` | 别名映射 | ✅ |
| `logging.*` | `logging.*` | 无变化 | ✅ |

**特殊处理**: `skip_on_divergence` 和 `use_confidence_fusion` 从 `strategy.risk.*` 移到 `ai.signal.*`

兼容层需要同时检查两个路径：

```python
# ConfigManager.get() 特殊处理
def get(self, *path, default=None) -> Any:
    # ... 标准逻辑 ...

    # 特殊处理: skip_on_divergence 和 use_confidence_fusion
    if path == ('ai', 'signal', 'skip_on_divergence'):
        value = (
            self._get_nested(self._config, ('ai', 'signal', 'skip_on_divergence'))
            or self._get_nested(self._config, ('strategy', 'risk', 'skip_on_divergence'))
        )
        if value is not None:
            return value

    if path == ('ai', 'signal', 'use_confidence_fusion'):
        value = (
            self._get_nested(self._config, ('ai', 'signal', 'use_confidence_fusion'))
            or self._get_nested(self._config, ('strategy', 'risk', 'use_confidence_fusion'))
        )
        if value is not None:
            return value

    return default
```

---

## 4. ConfigManager 类设计

### 4.1 类结构

```python
# utils/config_manager.py

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import yaml
from dataclasses import dataclass, field
from dotenv import load_dotenv
import os
import logging


@dataclass
class ConfigValidationError:
    """配置验证错误"""
    field: str
    message: str
    value: Any
    severity: str = "error"  # error / warning


class ConfigManager:
    """
    统一配置管理器

    功能:
    - 分层加载配置 (base → env → .env)
    - 类型验证
    - 范围检查
    - 依赖验证
    - 环境切换
    - 配置迁移日志
    """

    def __init__(
        self,
        config_dir: Path = None,
        env: str = "production",
        logger: logging.Logger = None
    ):
        """
        初始化配置管理器

        Parameters
        ----------
        config_dir : Path
            配置目录，默认为项目根目录/configs
        env : str
            环境名称: production / development / backtest
        logger : logging.Logger
            日志记录器
        """
        self.config_dir = config_dir or Path(__file__).parent.parent / "configs"
        self.env = env
        self._config: Dict[str, Any] = {}
        self._errors: List[ConfigValidationError] = []
        self._warnings: List[ConfigValidationError] = []
        self.logger = logger or logging.getLogger(__name__)

    def load(self) -> Dict[str, Any]:
        """
        加载并合并所有配置

        Returns
        -------
        dict
            合并后的配置字典
        """
        self.logger.info(f"Loading configuration for environment: {self.env}")

        # 1. 加载 base.yaml
        base_config = self._load_yaml("base.yaml")
        self._config = base_config
        self.logger.debug(f"Loaded base.yaml with {len(base_config)} top-level keys")

        # 2. 加载环境配置并合并
        env_file = f"{self.env}.yaml"
        if (self.config_dir / env_file).exists():
            env_config = self._load_yaml(env_file)
            self._config = self._deep_merge(self._config, env_config)
            self.logger.debug(f"Merged {env_file}")
        else:
            self.logger.warning(f"Environment config not found: {env_file}")

        # 3. 加载 .env 敏感信息
        self._load_env_secrets()

        # 4. 验证配置
        self.validate()

        # 5. 打印配置摘要
        self._log_config_summary()

        return self._config

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """加载 YAML 文件"""
        path = self.config_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """
        深度合并字典，override 覆盖 base
        """
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _load_env_secrets(self):
        """从 .env 加载敏感信息"""
        # 加载 ~/.env.aitrader
        env_path = Path.home() / ".env.aitrader"
        if env_path.exists():
            load_dotenv(env_path)
            self.logger.debug(f"Loaded secrets from {env_path}")

        # 映射环境变量到配置 (完整映射，共 9 个核心变量)
        env_mappings = {
            # Binance 主网 API
            'BINANCE_API_KEY': ('binance', 'api_key'),
            'BINANCE_API_SECRET': ('binance', 'api_secret'),

            # Binance 测试网 API (可选，回测/开发环境)
            'BINANCE_TESTNET_API_KEY': ('binance', 'testnet_api_key'),
            'BINANCE_TESTNET_API_SECRET': ('binance', 'testnet_api_secret'),

            # AI 服务
            'DEEPSEEK_API_KEY': ('ai', 'deepseek', 'api_key'),

            # Telegram 通知
            'TELEGRAM_BOT_TOKEN': ('telegram', 'bot_token'),
            'TELEGRAM_CHAT_ID': ('telegram', 'chat_id'),

            # 运行模式控制
            'TEST_MODE': ('runtime', 'test_mode'),
            'AUTO_CONFIRM': ('runtime', 'auto_confirm'),
        }

        for env_var, config_path in env_mappings.items():
            value = os.getenv(env_var)
            if value:
                self._set_nested(self._config, config_path, value)

    def _set_nested(self, d: dict, path: tuple, value: Any):
        """设置嵌套字典值"""
        for key in path[:-1]:
            d = d.setdefault(key, {})
        d[path[-1]] = value

    def validate(self) -> bool:
        """
        验证配置

        Returns
        -------
        bool
            是否通过验证
        """
        self._errors = []
        self._warnings = []

        # 类型和范围验证规则
        # (字段路径, 类型, 最小值, 最大值, 必填)
        rules = [
            # 资金配置
            (('capital', 'equity'), (int, float), 100, 1000000, True),
            (('capital', 'leverage'), (int, float), 1, 125, True),

            # 仓位管理
            (('position', 'base_usdt_amount'), (int, float), 100, None, True),
            (('position', 'max_position_ratio'), float, 0.01, 1.0, True),
            (('position', 'min_trade_amount'), float, 0.0001, 1.0, True),

            # 风险管理
            (('risk', 'rsi_extreme_threshold_upper'), (int, float), 50, 100, True),
            (('risk', 'rsi_extreme_threshold_lower'), (int, float), 0, 50, True),

            # 交易逻辑
            (('trading_logic', 'min_notional_usdt'), (int, float), 1, 10000, True),
            (('trading_logic', 'min_sl_distance_pct'), float, 0.001, 0.1, True),
            (('trading_logic', 'default_sl_pct'), float, 0.005, 0.2, True),

            # 定时器
            (('timing', 'timer_interval_sec'), int, 60, 86400, True),

            # AI 配置
            (('ai', 'deepseek', 'temperature'), float, 0.0, 2.0, True),
            (('ai', 'multi_agent', 'debate_rounds'), int, 1, 5, True),

            # 网络配置
            (('network', 'instrument_discovery', 'max_retries'), int, 1, 300, True),
            (('network', 'binance', 'recv_window'), int, 1000, 60000, True),
            (('network', 'bar_persistence', 'max_limit'), int, 100, 2000, True),
            (('network', 'bar_persistence', 'timeout'), int, 1, 60, True),
            (('network', 'oco_manager', 'socket_timeout'), int, 1, 30, True),

            # 交易逻辑
            (('trading_logic', 'quantity_adjustment_step'), float, 0.0001, 0.01, True),
        ]

        for path, expected_type, min_val, max_val, required in rules:
            value = self._get_nested(self._config, path)

            if value is None:
                if required:
                    self._errors.append(ConfigValidationError(
                        field='.'.join(path),
                        message="Required field is missing",
                        value=None
                    ))
                continue

            # 类型检查
            if not isinstance(value, expected_type):
                self._errors.append(ConfigValidationError(
                    field='.'.join(path),
                    message=f"Expected {expected_type}, got {type(value).__name__}",
                    value=value
                ))
                continue

            # 范围检查
            if min_val is not None and value < min_val:
                self._errors.append(ConfigValidationError(
                    field='.'.join(path),
                    message=f"Value {value} is below minimum {min_val}",
                    value=value
                ))

            if max_val is not None and value > max_val:
                self._errors.append(ConfigValidationError(
                    field='.'.join(path),
                    message=f"Value {value} is above maximum {max_val}",
                    value=value
                ))

        # 依赖验证
        self._validate_dependencies()

        return len(self._errors) == 0

    def _validate_dependencies(self):
        """验证配置依赖关系"""
        # RSI 阈值顺序
        rsi_upper = self.get('risk', 'rsi_extreme_threshold_upper')
        rsi_lower = self.get('risk', 'rsi_extreme_threshold_lower')
        if rsi_upper and rsi_lower and rsi_lower >= rsi_upper:
            self._errors.append(ConfigValidationError(
                field='risk.rsi_extreme_threshold_*',
                message=f"RSI lower ({rsi_lower}) must be less than upper ({rsi_upper})",
                value=(rsi_lower, rsi_upper)
            ))

        # MACD 周期顺序
        macd_fast = self.get('indicators', 'macd_fast')
        macd_slow = self.get('indicators', 'macd_slow')
        if macd_fast and macd_slow and macd_fast >= macd_slow:
            self._errors.append(ConfigValidationError(
                field='indicators.macd_*',
                message=f"MACD fast ({macd_fast}) must be less than slow ({macd_slow})",
                value=(macd_fast, macd_slow)
            ))

        # Telegram 依赖
        if self.get('telegram', 'enabled'):
            if not self.get('telegram', 'bot_token'):
                self._warnings.append(ConfigValidationError(
                    field='telegram.bot_token',
                    message="Telegram enabled but bot_token not set",
                    value=None,
                    severity="warning"
                ))
            if not self.get('telegram', 'chat_id'):
                self._warnings.append(ConfigValidationError(
                    field='telegram.chat_id',
                    message="Telegram enabled but chat_id not set",
                    value=None,
                    severity="warning"
                ))

    def _get_nested(self, d: dict, path: tuple) -> Any:
        """获取嵌套字典值"""
        for key in path:
            if not isinstance(d, dict) or key not in d:
                return None
            d = d[key]
        return d

    def get(self, *path, default=None) -> Any:
        """
        获取配置值

        Example:
            config.get('capital', 'equity')
            config.get('ai', 'deepseek', 'temperature')
        """
        value = self._get_nested(self._config, path)
        return value if value is not None else default

    def get_errors(self) -> List[ConfigValidationError]:
        """获取验证错误列表"""
        return self._errors

    def get_warnings(self) -> List[ConfigValidationError]:
        """获取验证警告列表"""
        return self._warnings

    def _log_config_summary(self):
        """记录配置摘要"""
        self.logger.info("=" * 50)
        self.logger.info("Configuration Summary")
        self.logger.info("=" * 50)
        self.logger.info(f"  Environment: {self.env}")
        self.logger.info(f"  Instrument: {self.get('trading', 'instrument_id')}")
        self.logger.info(f"  Equity: ${self.get('capital', 'equity'):,.2f}")
        self.logger.info(f"  Leverage: {self.get('capital', 'leverage')}x")
        self.logger.info(f"  Timer: {self.get('timing', 'timer_interval_sec')}s")
        self.logger.info(f"  AI Temperature: {self.get('ai', 'deepseek', 'temperature')}")
        self.logger.info(f"  RSI Thresholds: {self.get('risk', 'rsi_extreme_threshold_lower')}/{self.get('risk', 'rsi_extreme_threshold_upper')}")
        self.logger.info(f"  Telegram: {'Enabled' if self.get('telegram', 'enabled') else 'Disabled'}")

        if self._errors:
            self.logger.error(f"  Validation Errors: {len(self._errors)}")
            for error in self._errors:
                self.logger.error(f"    - {error.field}: {error.message}")
        else:
            self.logger.info("  Validation: PASSED")

        if self._warnings:
            self.logger.warning(f"  Warnings: {len(self._warnings)}")
            for warning in self._warnings:
                self.logger.warning(f"    - {warning.field}: {warning.message}")

        self.logger.info("=" * 50)

    def to_strategy_config(self) -> 'DeepSeekAIStrategyConfig':
        """
        转换为策略配置对象

        Returns
        -------
        DeepSeekAIStrategyConfig
            类型安全的策略配置
        """
        from strategy.deepseek_strategy import DeepSeekAIStrategyConfig

        return DeepSeekAIStrategyConfig(
            instrument_id=self.get('trading', 'instrument_id'),
            bar_type=self.get('trading', 'bar_type'),

            # Capital
            equity=self.get('capital', 'equity'),
            leverage=self.get('capital', 'leverage'),
            use_real_balance_as_equity=self.get('capital', 'use_real_balance_as_equity'),

            # Position
            base_usdt_amount=self.get('position', 'base_usdt_amount'),
            high_confidence_multiplier=self.get('position', 'high_confidence_multiplier'),
            medium_confidence_multiplier=self.get('position', 'medium_confidence_multiplier'),
            low_confidence_multiplier=self.get('position', 'low_confidence_multiplier'),
            max_position_ratio=self.get('position', 'max_position_ratio'),
            min_trade_amount=self.get('position', 'min_trade_amount'),

            # Indicators
            sma_periods=tuple(self.get('indicators', 'sma_periods')),
            rsi_period=self.get('indicators', 'rsi_period'),
            macd_fast=self.get('indicators', 'macd_fast'),
            macd_slow=self.get('indicators', 'macd_slow'),
            bb_period=self.get('indicators', 'bb_period'),
            bb_std=self.get('indicators', 'bb_std'),

            # AI
            deepseek_api_key=self.get('ai', 'deepseek', 'api_key', default=''),
            deepseek_model=self.get('ai', 'deepseek', 'model'),
            deepseek_temperature=self.get('ai', 'deepseek', 'temperature'),
            deepseek_max_retries=self.get('ai', 'deepseek', 'max_retries'),
            debate_rounds=self.get('ai', 'multi_agent', 'debate_rounds'),
            skip_on_divergence=self.get('ai', 'signal', 'skip_on_divergence'),

            # Risk
            min_confidence_to_trade=self.get('risk', 'min_confidence_to_trade'),
            rsi_extreme_threshold_upper=self.get('risk', 'rsi_extreme_threshold_upper'),
            rsi_extreme_threshold_lower=self.get('risk', 'rsi_extreme_threshold_lower'),

            # Stop Loss & Take Profit
            enable_auto_sl_tp=self.get('risk', 'stop_loss', 'enabled'),
            sl_buffer_pct=self.get('risk', 'stop_loss', 'buffer_pct'),
            tp_high_confidence_pct=self.get('risk', 'take_profit', 'high_confidence_pct'),
            tp_medium_confidence_pct=self.get('risk', 'take_profit', 'medium_confidence_pct'),
            tp_low_confidence_pct=self.get('risk', 'take_profit', 'low_confidence_pct'),

            # Trailing Stop
            enable_trailing_stop=self.get('risk', 'trailing_stop', 'enabled'),
            trailing_activation_pct=self.get('risk', 'trailing_stop', 'activation_pct'),
            trailing_distance_pct=self.get('risk', 'trailing_stop', 'distance_pct'),

            # Telegram
            enable_telegram=self.get('telegram', 'enabled'),
            telegram_bot_token=self.get('telegram', 'bot_token', default=''),
            telegram_chat_id=self.get('telegram', 'chat_id', default=''),

            # Timing
            timer_interval_sec=self.get('timing', 'timer_interval_sec'),

            # Trading Logic (新增)
            historical_bars_limit=self.get('trading', 'historical_bars_limit'),
        )

    def print_summary(self):
        """打印配置摘要到控制台"""
        print("=" * 60)
        print("  Configuration Summary")
        print("=" * 60)
        print(f"  Environment: {self.env}")
        print(f"  Instrument: {self.get('trading', 'instrument_id')}")
        print(f"  Equity: ${self.get('capital', 'equity'):,.2f}")
        print(f"  Leverage: {self.get('capital', 'leverage')}x")
        print(f"  Timer: {self.get('timing', 'timer_interval_sec')}s")
        print(f"  AI Temperature: {self.get('ai', 'deepseek', 'temperature')}")
        print(f"  RSI Thresholds: {self.get('risk', 'rsi_extreme_threshold_lower')}/{self.get('risk', 'rsi_extreme_threshold_upper')}")
        print(f"  Telegram: {'Enabled' if self.get('telegram', 'enabled') else 'Disabled'}")

        if self._errors:
            print(f"\n  ⚠️ Validation Errors ({len(self._errors)}):")
            for error in self._errors:
                print(f"    - {error.field}: {error.message}")
        else:
            print("\n  ✅ Configuration validated successfully")

        if self._warnings:
            print(f"\n  ⚠️ Warnings ({len(self._warnings)}):")
            for warning in self._warnings:
                print(f"    - {warning.field}: {warning.message}")

        print("=" * 60)
```

---

## 5. 迁移计划

### 5.1 分阶段实施

| 阶段 | 任务 | 文件变更 | 风险 | 优先级 |
|------|------|---------|------|--------|
| **Phase 0** | 🔴 **修复配置冲突** | main_live.py | **高** | **紧急** |
| **Phase 1** | 创建 ConfigManager 和 base.yaml | 新增 2 文件 | 低 | 高 |
| **Phase 2** | 修改 main_live.py 使用 ConfigManager | 修改 1 文件 | 中 | 高 |
| **Phase 3** | 迁移 trading_logic.py 常量 | 修改 3 文件 | 中 | 中 |
| **Phase 4** | 迁移 utils 中的硬编码 | 修改 6 文件 | 低 | 中 |
| **Phase 5** | 添加环境切换和 CLI 参数 | 修改 1 文件 | 低 | 低 |
| **Phase 6** | 测试和文档更新 | 多文件 | 低 | 低 |

### 5.2 Phase 0: 紧急修复配置冲突

**必须先执行！** 修复 main_live.py 中覆盖 YAML 配置的硬编码：

```python
# main_live.py 修改

# BEFORE (硬编码覆盖 YAML):
deepseek_temperature=0.1,
rsi_extreme_threshold_upper=75.0,
rsi_extreme_threshold_lower=25.0,
min_trade_amount=0.001,

# AFTER (从 YAML 加载):
deepseek_temperature=deepseek_config.get('temperature', 0.3),
rsi_extreme_threshold_upper=risk_config.get('rsi_extreme_threshold_upper', 70.0),
rsi_extreme_threshold_lower=risk_config.get('rsi_extreme_threshold_lower', 30.0),
min_trade_amount=position_config.get('min_trade_amount', 0.001),
```

**注意**: 此修复会改变系统行为：
- DeepSeek temperature: 0.1 → 0.3 (AI 输出更多样)
- RSI 阈值: 75/25 → 70/30 (更早触发极值逻辑)

### 5.3 Phase 3: 迁移 trading_logic.py 常量

**修改文件列表**:
1. `strategy/trading_logic.py` - 常量改为函数
2. `agents/multi_agent_analyzer.py` - 修改导入语句 (常量 → 函数)
3. `diagnose_realtime.py` - 检查是否需要修改 (如果导入常量)

```python
# 1. strategy/trading_logic.py 修改

# BEFORE (硬编码):
MIN_NOTIONAL_USDT = 100.0
MIN_NOTIONAL_SAFETY_MARGIN = 1.01
MIN_SL_DISTANCE_PCT = 0.01
DEFAULT_SL_PCT = 0.02
DEFAULT_TP_PCT_BUY = 0.03
DEFAULT_TP_PCT_SELL = 0.03

# AFTER (从配置加载):
def get_trading_logic_config():
    """从配置加载交易逻辑常量"""
    from utils.config_manager import ConfigManager
    config = ConfigManager()
    config.load()

    return {
        'min_notional_usdt': config.get('trading_logic', 'min_notional_usdt', default=100.0),
        'min_notional_safety_margin': config.get('trading_logic', 'min_notional_safety_margin', default=1.01),
        'min_sl_distance_pct': config.get('trading_logic', 'min_sl_distance_pct', default=0.01),
        'default_sl_pct': config.get('trading_logic', 'default_sl_pct', default=0.02),
        'default_tp_pct': config.get('trading_logic', 'default_tp_pct', default=0.03),
    }

# 模块级别缓存
_TRADING_LOGIC_CONFIG = None

def _get_config():
    global _TRADING_LOGIC_CONFIG
    if _TRADING_LOGIC_CONFIG is None:
        _TRADING_LOGIC_CONFIG = get_trading_logic_config()
    return _TRADING_LOGIC_CONFIG

# 提供常量访问接口 (函数形式)
def get_min_notional_usdt():
    return _get_config()['min_notional_usdt']

def get_min_sl_distance_pct():
    return _get_config()['min_sl_distance_pct']

def get_default_sl_pct():
    return _get_config()['default_sl_pct']

def get_default_tp_pct_buy():
    return _get_config()['default_tp_pct']

def get_default_tp_pct_sell():
    return _get_config()['default_tp_pct']

# 2. agents/multi_agent_analyzer.py 修改导入

# BEFORE (导入常量):
from strategy.trading_logic import (
    MIN_SL_DISTANCE_PCT,
    DEFAULT_SL_PCT,
    DEFAULT_TP_PCT_BUY,
    DEFAULT_TP_PCT_SELL,
)

# AFTER (导入函数):
from strategy.trading_logic import (
    get_min_sl_distance_pct,
    get_default_sl_pct,
    get_default_tp_pct_buy,
    get_default_tp_pct_sell,
)

# 使用时也需要修改 (常量 → 函数调用)
# BEFORE: sl_pct = DEFAULT_SL_PCT
# AFTER:  sl_pct = get_default_sl_pct()
```

### 5.4 按 Phase 回滚诊断 🔴

> ⚠️ **每个 Phase 必须有明确的诊断命令和回滚步骤**

#### 5.4.1 Phase 0 回滚 (RSI 行为异常)

**症状**: RSI 极值检测提前/延迟触发，交易信号异常增加或减少

**诊断命令**:

```bash
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate

# 1. 检查当前 RSI 阈值配置
python3 -c "
import yaml
with open('configs/strategy_config.yaml') as f:
    cfg = yaml.safe_load(f)
upper = cfg.get('strategy',{}).get('risk',{}).get('rsi_extreme_threshold_upper', 'NOT_SET')
lower = cfg.get('strategy',{}).get('risk',{}).get('rsi_extreme_threshold_lower', 'NOT_SET')
print(f'YAML RSI Upper: {upper}')
print(f'YAML RSI Lower: {lower}')
if upper == 70 and lower == 30:
    print('✅ YAML 配置正确')
else:
    print('❌ YAML 配置异常')
"

# 2. 检查日志中的 RSI 值
sudo journalctl -u nautilus-trader --since "1 hour ago" | grep -i "rsi"
```

**回滚命令**:

```bash
# 回滚 main_live.py 到 Phase 0 之前
git log --oneline -5  # 找到 Phase 0 之前的 commit
git checkout <commit-before-phase0> -- main_live.py
sudo systemctl restart nautilus-trader
```

---

#### 5.4.2 Phase 1 回滚 (ConfigManager 加载失败)

**症状**: 启动失败，报错 `FileNotFoundError: base.yaml` 或 `ImportError: config_manager`

**诊断命令**:

```bash
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate

# 1. 检查 ConfigManager 是否能加载
python3 -c "
try:
    from utils.config_manager import ConfigManager
    config = ConfigManager()
    config.load()
    print('✅ ConfigManager 加载成功')
    print(f'  Environment: {config.env}')
    print(f'  Equity: {config.get(\"capital\", \"equity\")}')
except Exception as e:
    print(f'❌ ConfigManager 加载失败: {e}')
"

# 2. 检查 base.yaml 是否存在
ls -la configs/base.yaml

# 3. 检查 YAML 语法
python3 -c "
import yaml
try:
    with open('configs/base.yaml') as f:
        yaml.safe_load(f)
    print('✅ base.yaml 语法正确')
except Exception as e:
    print(f'❌ YAML 语法错误: {e}')
"
```

**回滚命令**:

```bash
# 删除 ConfigManager，恢复旧加载方式
git checkout HEAD~1 -- utils/config_manager.py main_live.py
rm -f configs/base.yaml configs/production.yaml configs/development.yaml
sudo systemctl restart nautilus-trader
```

---

#### 5.4.2.5 Phase 2 回滚 (main_live.py 配置加载失败) 🔴 v2.5 新增

**症状**: 启动时配置加载失败，报错 `KeyError` 或配置值为 None

**诊断命令**:

```bash
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate

# 1. 检查 main_live.py 是否能正确加载配置
python3 -c "
import sys
sys.path.insert(0, '.')
try:
    from main_live import get_strategy_config, load_yaml_config
    yaml_config = load_yaml_config('configs/strategy_config.yaml')
    config = get_strategy_config(yaml_config)
    print('✅ 配置加载成功')
    print(f'  equity: {config.equity}')
    print(f'  leverage: {config.leverage}')
    print(f'  deepseek_temperature: {config.deepseek_temperature}')
except Exception as e:
    print(f'❌ 配置加载失败: {e}')
"

# 2. 检查 ConfigManager 路径映射是否正常
python3 -c "
from utils.config_manager import get_config
config = get_config()
# 测试新旧路径都能访问
tests = [
    ('position.base_usdt_amount', config.get('position', 'base_usdt_amount')),
    ('strategy.position_management.base_usdt_amount', config.get('strategy', 'position_management', 'base_usdt_amount')),
]
for path, value in tests:
    status = '✅' if value else '❌'
    print(f'{status} {path}: {value}')
"
```

**回滚命令**:

```bash
# 恢复 main_live.py 到 Phase 1 状态
git log --oneline -5  # 找到 Phase 1 完成后的 commit
git checkout <phase1-commit> -- main_live.py
sudo systemctl restart nautilus-trader
```

---

#### 5.4.3 Phase 3 回滚 (循环导入错误 / multi_agent_analyzer 导入失败)

**症状 1**: 启动失败，报错 `ImportError: cannot import name ... from partially initialized module`

**症状 2**: 启动失败，报错 `ImportError: cannot import name 'MIN_SL_DISTANCE_PCT' from 'strategy.trading_logic'`

**诊断命令**:

```bash
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate

# 1. 检查 trading_logic 是否有循环导入
python3 -c "
try:
    import strategy.trading_logic
    print('✅ trading_logic 导入成功')
except ImportError as e:
    print(f'❌ 循环导入错误: {e}')
"

# 2. 检查 multi_agent_analyzer 是否能正常导入 (新增)
python3 -c "
try:
    from agents.multi_agent_analyzer import MultiAgentAnalyzer
    print('✅ MultiAgentAnalyzer 导入成功')
except ImportError as e:
    print(f'❌ multi_agent_analyzer.py 导入失败: {e}')
    print('  原因: trading_logic.py 常量改为函数，但 multi_agent_analyzer.py 未同步修改')
"

# 3. 检查模块导入顺序
python3 -c "
import sys
sys.settrace(lambda *args: print(args[0].f_code.co_filename) if 'trading_logic' in str(args) else None)
import strategy.trading_logic
" 2>&1 | head -20
```

**回滚命令**:

```bash
# 恢复 trading_logic.py 和 multi_agent_analyzer.py 到 Phase 2 状态
git checkout HEAD~1 -- strategy/trading_logic.py agents/multi_agent_analyzer.py
sudo systemctl restart nautilus-trader
```

---

#### 5.4.4 Phase 4 回滚 (单个 utils 文件失败)

**症状**: 特定功能失败 (如 Telegram 通知、K线持久化)

**诊断命令**:

```bash
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate

# 1. 检查哪个 utils 模块有问题
for module in telegram_bot telegram_command_handler bar_persistence binance_account deepseek_client; do
    python3 -c "from utils.$module import *" 2>&1 | grep -q "Error" && echo "❌ $module" || echo "✅ $module"
done

# 2. 检查特定模块
python3 -c "
from utils.telegram_command_handler import TelegramCommandHandler
print('✅ TelegramCommandHandler 导入成功')
"
```

**回滚命令** (单文件):

```bash
# 只回滚有问题的文件
git checkout HEAD~1 -- utils/telegram_command_handler.py

# 或批量回滚所有 utils
git checkout HEAD~1 -- utils/bar_persistence.py utils/telegram_command_handler.py utils/deepseek_client.py
sudo systemctl restart nautilus-trader
```

---

#### 5.4.4.5 Phase 5 回滚 (CLI 环境切换失败) 🔴 v2.5 新增

**症状**: `--env` 参数无效，或环境配置加载错误

**诊断命令**:

```bash
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate

# 1. 检查 CLI 参数解析
python3 main_live.py --help 2>&1 | grep -i "env"

# 2. 测试不同环境配置加载
for env in production development backtest; do
    echo "=== Testing $env ==="
    python3 -c "
from utils.config_manager import ConfigManager
try:
    config = ConfigManager(env='$env')
    config.load()
    print(f'✅ {\"$env\"} 环境加载成功')
    print(f'  timer_interval: {config.get(\"timing\", \"timer_interval_sec\")}')
except Exception as e:
    print(f'❌ {\"$env\"} 加载失败: {e}')
" 2>&1
done

# 3. 检查环境配置文件是否存在
ls -la configs/*.yaml
```

**回滚命令**:

```bash
# 恢复 main_live.py 到 Phase 4 状态 (移除 CLI 参数)
git checkout HEAD~1 -- main_live.py

# 或删除环境配置文件，只保留 base.yaml
rm -f configs/development.yaml configs/backtest.yaml
sudo systemctl restart nautilus-trader
```

---

#### 5.4.7 跨 Phase 综合诊断 🟡

> **场景**: Phase 1-4 全部完成后，验证完整数据流和配置加载

**诊断命令**:

```bash
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate

# 1. 运行实时诊断 (真实 API 调用)
python3 diagnose_realtime.py
# 预期: 输出完整信号，无 ImportError/KeyError/AttributeError

# 2. 检查配置加载次数 (验证单例模式)
sudo journalctl -u nautilus-trader --since "5 min ago" | grep -c "Configuration Summary"
# 预期: ≤ 1 (单例模式生效，配置只加载一次)

# 3. 验证所有配置路径可访问
python3 -c "
from utils.config_manager import get_config
config = get_config()

# 测试关键配置路径
test_paths = [
    ('ai', 'deepseek', 'temperature'),
    ('risk', 'rsi_extreme_threshold_upper'),
    ('trading_logic', 'min_notional_usdt'),
    ('network', 'binance', 'recv_window'),
    ('ai', 'signal', 'history_count'),
    ('telegram', 'enabled'),
]

print('配置路径验证:')
for path in test_paths:
    val = config.get(*path)
    status = '✅' if val is not None else '❌'
    path_str = '.'.join(path)
    print(f'{status} {path_str}: {val}')
"

# 4. 检查是否有配置加载错误
sudo journalctl -u nautilus-trader --since "10 min ago" | grep -i "error\|warning" | grep -i "config"
# 预期: 无配置相关错误/警告
```

**性能检测**:

```bash
# 检查 API 响应时间 (确保配置加载未导致性能退化)
sudo journalctl -u nautilus-trader --since "5 min ago" | grep -i "timeout\|slow"
# 预期: 无超时警告
```

**回滚命令**:

如果综合诊断失败，回滚到 Phase 0 (稳定状态):

```bash
git log --oneline -10  # 找到 Phase 0 完成后的 commit
git reset --hard <phase0-commit>
sudo systemctl restart nautilus-trader
```

---

#### 5.4.5 跨 Phase 回滚表

| 当前 Phase | 回滚到 | 需要恢复的文件 | 命令 |
|-----------|-------|--------------|------|
| Phase 1 | Phase 0 | `config_manager.py`, `main_live.py`, `base.yaml` | 见 5.4.2 |
| Phase 2 | Phase 1 | `main_live.py` | `git checkout HEAD~1 -- main_live.py` |
| Phase 3 | Phase 2 | `trading_logic.py` | `git checkout HEAD~1 -- strategy/trading_logic.py` |
| Phase 4 | Phase 3 | `utils/*.py` (多文件) | `git checkout HEAD~1 -- utils/` |
| Phase 5 | Phase 4 | `main_live.py` (CLI 参数) | `git checkout HEAD~1 -- main_live.py` |

**完全回滚到初始状态**:

```bash
cd /home/linuxuser/nautilus_AItrader
git fetch origin main
git reset --hard origin/main
sudo systemctl restart nautilus-trader
```

### 5.5 兼容性保证

- 旧的 `.env.aitrader` 格式完全兼容
- 旧的 `strategy_config.yaml` 可以继续使用 (但建议迁移到 base.yaml)
- 添加迁移脚本自动转换旧配置

### 5.6 Phase 间关联影响

> ⚠️ **关键：修改一个 Phase 可能影响其他 Phase，必须理解依赖关系**

#### 5.6.1 Phase 依赖图

```
Phase 0 (紧急修复)
    │
    ├──→ Phase 2 (main_live.py 迁移)
    │        │
    │        └──→ 验证: deepseek_temperature 配置路径一致性
    │             验证: rsi_extreme_threshold 配置路径一致性
    │
    ↓
Phase 1 (ConfigManager) ←─── 阻塞后续所有 Phase
    │
    ├── 必须项 (不可跳过):
    │   ├── [M1] 单例模式: get_config() 函数
    │   ├── [M2] 敏感信息掩蔽: _mask_sensitive() 方法
    │   └── [M3] 环境变量完整映射 (9 个核心变量)
    │
    ├──→ Phase 3 (trading_logic.py)
    │        │
    │        ├── 风险: 循环导入 (trading_logic ↔ config_manager)
    │        └── 方案: 延迟导入 + 模块级缓存
    │
    └──→ Phase 4 (utils/*.py)
             │
             ├── 依赖: bar_persistence.py 需要 retry_delay
             ├── 依赖: oco_manager.py 需要 socket_timeout
             └── 依赖: telegram_command_handler.py 需要 startup_delay
```

#### 5.6.2 Phase 1 必须项详解

| 编号 | 必须项 | 描述 | 影响范围 | 验证方法 |
|------|--------|------|---------|---------|
| M1 | **单例模式** | `get_config()` 全局访问函数 | 所有模块 | `id(get_config()) == id(get_config())` |
| M2 | **敏感信息掩蔽** | 日志/异常中隐藏 API_KEY 等 | 安全性 | 日志搜索无敏感信息明文 |
| M3 | **环境变量映射** | 9 个核心变量完整映射 | 启动加载 | `config.get('binance', 'api_key')` 有值 |

**M1 单例模式实现要求**:

```python
# utils/config_manager.py

_instance: Optional['ConfigManager'] = None

def get_config() -> ConfigManager:
    """
    获取 ConfigManager 单例实例

    线程安全说明:
    - NautilusTrader 多线程环境下必须保证单例
    - 首次调用在主线程 (on_start)，后续调用可能在其他线程
    """
    global _instance
    if _instance is None:
        _instance = ConfigManager()
        _instance.load()
    return _instance
```

**M2 敏感信息掩蔽要求**:

```python
# 需要掩蔽的字段列表
SENSITIVE_FIELDS = [
    'api_key', 'api_secret', 'bot_token',
    'testnet_api_key', 'testnet_api_secret'
]

def _mask_sensitive(self, key: str, value: Any) -> str:
    """
    掩蔽敏感信息用于日志输出

    示例:
    - 'sk-xxxxxxxxxxxx1234' → 'sk-****1234'
    - '' → '(未设置)'
    """
    if any(field in key.lower() for field in SENSITIVE_FIELDS):
        if not value:
            return '(未设置)'
        return f"{str(value)[:4]}****{str(value)[-4:]}"
    return str(value)
```

**M3 环境变量映射验证清单**:

| 变量名 | 配置路径 | 必需 | 说明 |
|--------|---------|------|------|
| `BINANCE_API_KEY` | `binance.api_key` | ✅ | 主网 API |
| `BINANCE_API_SECRET` | `binance.api_secret` | ✅ | 主网密钥 |
| `BINANCE_TESTNET_API_KEY` | `binance.testnet_api_key` | ❌ | 测试网 |
| `BINANCE_TESTNET_API_SECRET` | `binance.testnet_api_secret` | ❌ | 测试网 |
| `DEEPSEEK_API_KEY` | `ai.deepseek.api_key` | ✅ | AI 服务 |
| `TELEGRAM_BOT_TOKEN` | `telegram.bot_token` | ❌ | 通知 |
| `TELEGRAM_CHAT_ID` | `telegram.chat_id` | ❌ | 通知 |
| `TEST_MODE` | `runtime.test_mode` | ❌ | 测试模式 |
| `AUTO_CONFIRM` | `runtime.auto_confirm` | ❌ | 自动确认 |

#### 5.6.3 Phase 0 → Phase 2 过渡验证

Phase 0 修复了 main_live.py 的硬编码问题，Phase 2 将完全迁移到 ConfigManager。必须验证配置路径一致性：

**核心参数路径映射**:

| 参数 | Phase 0 路径 | Phase 2 路径 | 验证 |
|------|-------------|-------------|------|
| `deepseek_temperature` | `deepseek_config.get('temperature')` | `config.get('ai', 'deepseek', 'temperature')` | ✅ 一致 |
| `rsi_extreme_threshold_upper` | `risk_config.get('rsi_extreme_threshold_upper')` | `config.get('risk', 'rsi_extreme_threshold_upper')` | ✅ 一致 |
| `rsi_extreme_threshold_lower` | `risk_config.get('rsi_extreme_threshold_lower')` | `config.get('risk', 'rsi_extreme_threshold_lower')` | ✅ 一致 |
| `min_trade_amount` | `position_config.get('min_trade_amount')` | `config.get('position', 'min_trade_amount')` | ✅ 一致 |

**嵌套 .get() 路径映射** (main_live.py:222-238):

| 参数 | Phase 0 路径 | Phase 2 路径 | 位置 |
|------|-------------|-------------|------|
| `skip_on_divergence` | `strategy_yaml.get('risk', {}).get('skip_on_divergence', True)` | `config.get('ai', 'signal', 'skip_on_divergence', default=True)` | :222 |
| `use_confidence_fusion` | `strategy_yaml.get('risk', {}).get('use_confidence_fusion', True)` | `config.get('ai', 'signal', 'use_confidence_fusion', default=True)` | :223 |
| `enable_telegram` | `strategy_yaml.get('telegram', {}).get('enabled', False)` | `config.get('telegram', 'enabled', default=False)` | :232 |
| `telegram_notify_signals` | `strategy_yaml.get('telegram', {}).get('notify_signals', True)` | `config.get('telegram', 'notify_signals', default=True)` | :235 |
| `telegram_notify_fills` | `strategy_yaml.get('telegram', {}).get('notify_fills', True)` | `config.get('telegram', 'notify_fills', default=True)` | :236 |
| `telegram_notify_positions` | `strategy_yaml.get('telegram', {}).get('notify_positions', True)` | `config.get('telegram', 'notify_positions', default=True)` | :237 |
| `telegram_notify_errors` | `strategy_yaml.get('telegram', {}).get('notify_errors', True)` | `config.get('telegram', 'notify_errors', default=True)` | :238 |

**验证脚本**:

```bash
# 验证 Phase 0 修复后配置值
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate
python3 -c "
import yaml
with open('configs/strategy_config.yaml') as f:
    cfg = yaml.safe_load(f)
print('Phase 0 配置验证:')
print(f'  temperature: {cfg.get(\"deepseek\", {}).get(\"temperature\")}')
print(f'  rsi_upper: {cfg.get(\"risk\", {}).get(\"rsi_extreme_threshold_upper\")}')
print(f'  rsi_lower: {cfg.get(\"risk\", {}).get(\"rsi_extreme_threshold_lower\")}')
"
```

#### 5.6.4 Phase 3 循环导入处理

**问题描述**:

```
trading_logic.py
    ├── 导入 config_manager.py (获取配置)
    │
config_manager.py
    ├── 导入 trading_logic.py (获取常量定义)  ← 循环！
```

**解决方案: 延迟导入 + 模块级缓存**

```python
# strategy/trading_logic.py

# ❌ 错误: 顶层导入会触发循环
# from utils.config_manager import get_config

# ✅ 正确: 延迟导入
_TRADING_LOGIC_CONFIG = None

def _get_config():
    """延迟导入并缓存配置"""
    global _TRADING_LOGIC_CONFIG
    if _TRADING_LOGIC_CONFIG is None:
        # 仅在首次调用时导入
        from utils.config_manager import get_config
        config = get_config()
        _TRADING_LOGIC_CONFIG = {
            'min_notional_usdt': config.get('trading_logic', 'min_notional_usdt', default=100.0),
            'min_sl_distance_pct': config.get('trading_logic', 'min_sl_distance_pct', default=0.01),
            # ... 其他配置
        }
    return _TRADING_LOGIC_CONFIG

# 提供兼容接口
def get_min_notional_usdt():
    return _get_config()['min_notional_usdt']
```

#### 5.6.5 Phase 4 依赖关系

**修改文件列表** (6 个):

| 文件 | 行号 | 硬编码值 | 配置路径 | 影响说明 |
|------|------|---------|---------|---------|
| `bar_persistence.py` | 346, 349 | `max_limit=1500`, `timeout=10` | `network.bar_persistence.*` | K线数据获取 |
| `oco_manager.py` | 89-90 | `socket_timeout=5` | `network.oco_manager.*` | Redis连接 |
| `telegram_command_handler.py` | 476-482 | `startup_delay=5` | `telegram.startup_delay` | Telegram轮询 |
| `binance_account.py` | 55, 78 | `_cache_ttl=5.0` | `network.binance.balance_cache_ttl` | 余额缓存 |
| `sentiment_client.py` | 89 | `timeout=10` | `sentiment.timeout` | 情绪数据 |
| `deepseek_client.py` | 58 | `maxlen=30` | `ai.signal.history_count` | 信号历史队列 |

**Phase 4 新增**: `deepseek_client.py:58` 信号历史队列大小

```python
# utils/deepseek_client.py 修改

# BEFORE (硬编码):
self.signal_history = deque(maxlen=30)

# AFTER (从配置加载):
from utils.config_manager import get_config
config = get_config()
history_count = config.get('ai', 'signal', 'history_count', default=30)
self.signal_history = deque(maxlen=history_count)
```

**Phase 4 部分回滚方案**:

如果某个文件迁移失败，可以单独回滚：

```bash
# 只回滚 oco_manager.py 的更改
git checkout HEAD~1 -- utils/oco_manager.py

# 保留其他文件的迁移
```

#### 5.6.6 关联影响检查清单

在实施每个 Phase 前，完成以下检查：

**Phase 1 实施前**:
- [ ] 确认 Phase 0 已完成并测试通过
- [ ] 确认 base.yaml 包含所有必需配置项
- [ ] 确认 _mask_sensitive() 覆盖所有敏感字段

**Phase 2 实施前**:
- [ ] 确认 Phase 1 ConfigManager 加载正常
- [ ] 验证配置路径映射 (5.6.3 表格)
- [ ] 运行 `python3 diagnose.py --quick` 无报错

**Phase 3 实施前**:
- [ ] 确认 Phase 1 单例模式工作正常
- [ ] 测试延迟导入无循环错误
- [ ] 验证缓存机制 (`_TRADING_LOGIC_CONFIG` 只初始化一次)

**Phase 4 实施前**:
- [ ] 确认 Phase 1-3 全部完成
- [ ] 列出所有 utils/*.py 文件的配置依赖
- [ ] 准备单文件回滚脚本

**Phase 5-6 实施前**:
- [ ] 全量功能测试通过
- [ ] 运行 `python3 diagnose.py` 全部检查通过
- [ ] 更新 CLAUDE.md 和 README.md (详见下方)

**Phase 6 文档更新清单** ✅ **已完成**:

> ✅ **文档已同步** (commit 3cb6897)：CLAUDE.md 和 README.md 中的 RSI 阈值已更新为 70/30

| 文件 | 行号 | 旧值 | 新值 | 状态 |
|------|------|------|------|------|
| `CLAUDE.md` | 369-370 | ~~75/25~~ | 70/30 | ✅ 已更新 |
| `README.md` | 527-528 | ~~75/25~~ | 70/30 | ✅ 已更新 |
| `README.md` | 1164-1165 | ~~75/25~~ | 70/30 | ✅ 已更新 |

**验证命令**:
```bash
# 确认无遗漏的旧值
grep -rn "rsi_extreme_threshold.*75\|rsi_extreme_threshold.*25" CLAUDE.md README.md
# 应该没有输出
```

**验证命令**:
```bash
grep -n "rsi_extreme_threshold" CLAUDE.md README.md | grep -E "75|25"
# 应该没有输出，表示已全部更新
```

### 5.7 配置迁移脚本设计 🟡

> 用于将旧的 `strategy_config.yaml` 结构迁移到新的 `base.yaml` 结构

#### 5.7.1 迁移路径映射

```python
# scripts/migrate_config.py

"""
配置迁移脚本：strategy_config.yaml → base.yaml

使用方法:
    python3 scripts/migrate_config.py --input configs/strategy_config.yaml --output configs/base.yaml
    python3 scripts/migrate_config.py --dry-run  # 只显示将要进行的更改
"""

# 路径映射规则
PATH_MIGRATIONS = {
    # 旧路径 → 新路径
    ('strategy', 'instrument_id'): ('trading', 'instrument_id'),
    ('strategy', 'bar_type'): ('trading', 'bar_type'),

    # 资金配置
    ('strategy', 'equity'): ('capital', 'equity'),
    ('strategy', 'leverage'): ('capital', 'leverage'),
    ('strategy', 'use_real_balance_as_equity'): ('capital', 'use_real_balance_as_equity'),

    # 仓位管理
    ('strategy', 'position_management', 'base_usdt_amount'): ('position', 'base_usdt_amount'),
    ('strategy', 'position_management', 'high_confidence_multiplier'): ('position', 'high_confidence_multiplier'),
    ('strategy', 'position_management', 'medium_confidence_multiplier'): ('position', 'medium_confidence_multiplier'),
    ('strategy', 'position_management', 'low_confidence_multiplier'): ('position', 'low_confidence_multiplier'),
    ('strategy', 'position_management', 'max_position_ratio'): ('position', 'max_position_ratio'),
    ('strategy', 'position_management', 'min_trade_amount'): ('position', 'min_trade_amount'),

    # 技术指标 (路径保持但去掉 strategy 前缀)
    ('strategy', 'indicators', '*'): ('indicators', '*'),

    # AI 配置
    ('strategy', 'deepseek', '*'): ('ai', 'deepseek', '*'),

    # 风险配置
    ('strategy', 'risk', '*'): ('risk', '*'),

    # Telegram
    ('strategy', 'telegram', '*'): ('telegram', '*'),

    # 时间配置
    ('strategy', 'timer_interval_sec'): ('timing', 'timer_interval_sec'),

    # 日志配置
    ('logging', '*'): ('logging', '*'),
}
```

#### 5.7.2 迁移脚本核心逻辑

```python
import yaml
from pathlib import Path

def migrate_config(old_config: dict) -> dict:
    """
    将旧配置结构迁移到新结构

    Returns:
        迁移后的配置字典
    """
    new_config = {}

    def set_nested(d: dict, path: tuple, value):
        """设置嵌套字典值"""
        for key in path[:-1]:
            d = d.setdefault(key, {})
        d[path[-1]] = value

    def get_nested(d: dict, path: tuple):
        """获取嵌套字典值"""
        for key in path:
            if key == '*':
                return d  # 通配符，返回整个子树
            if not isinstance(d, dict) or key not in d:
                return None
            d = d[key]
        return d

    # 执行迁移
    for old_path, new_path in PATH_MIGRATIONS.items():
        if '*' in old_path:
            # 通配符处理：迁移整个子树
            prefix = old_path[:-1]
            subtree = get_nested(old_config, prefix)
            if subtree:
                new_prefix = new_path[:-1] if new_path[-1] == '*' else new_path
                set_nested(new_config, new_prefix, subtree)
        else:
            value = get_nested(old_config, old_path)
            if value is not None:
                set_nested(new_config, new_path, value)

    return new_config

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Migrate config structure')
    parser.add_argument('--input', default='configs/strategy_config.yaml')
    parser.add_argument('--output', default='configs/base.yaml')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    with open(args.input) as f:
        old_config = yaml.safe_load(f)

    new_config = migrate_config(old_config)

    if args.dry_run:
        print(yaml.dump(new_config, allow_unicode=True, default_flow_style=False))
    else:
        with open(args.output, 'w') as f:
            yaml.dump(new_config, f, allow_unicode=True, default_flow_style=False)
        print(f'✅ Migrated {args.input} → {args.output}')
```

#### 5.7.3 迁移验证

```bash
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate

# 1. 干运行，查看将要迁移的内容
python3 scripts/migrate_config.py --dry-run

# 2. 执行迁移
python3 scripts/migrate_config.py

# 3. 验证迁移结果
python3 -c "
import yaml
with open('configs/base.yaml') as f:
    cfg = yaml.safe_load(f)

# 验证关键路径
checks = [
    ('trading.instrument_id', cfg.get('trading', {}).get('instrument_id')),
    ('capital.equity', cfg.get('capital', {}).get('equity')),
    ('position.base_usdt_amount', cfg.get('position', {}).get('base_usdt_amount')),
    ('ai.deepseek.temperature', cfg.get('ai', {}).get('deepseek', {}).get('temperature')),
    ('risk.rsi_extreme_threshold_upper', cfg.get('risk', {}).get('rsi_extreme_threshold_upper')),
]

for path, value in checks:
    status = '✅' if value is not None else '❌'
    print(f'{status} {path}: {value}')
"

# 4. 对比新旧配置
diff <(python3 -c "import yaml; print(yaml.dump(yaml.safe_load(open('configs/strategy_config.yaml')), sort_keys=True))") \
     <(python3 -c "import yaml; print(yaml.dump(yaml.safe_load(open('configs/base.yaml')), sort_keys=True))")
```

#### 5.7.4 回滚迁移

```bash
# 如果迁移出现问题，可以从 git 恢复
git checkout HEAD~1 -- configs/base.yaml

# 或删除 base.yaml，继续使用旧结构
rm configs/base.yaml
# ConfigManager 会自动回退到 strategy_config.yaml
```

---

## 6. 验证规则

### 6.1 类型验证

| 参数 | 类型 | 说明 |
|------|------|------|
| equity | float | 必须为数字 |
| leverage | int/float | 必须为数字 |
| sma_periods | list[int] | 必须为整数列表 |
| min_confidence_to_trade | str | 必须为 LOW/MEDIUM/HIGH |
| temperature | float | 必须为 0.0-2.0 |

### 6.2 范围验证

| 参数 | 最小值 | 最大值 | 说明 |
|------|--------|--------|------|
| equity | 100 | 1,000,000 | 合理资金范围 |
| leverage | 1 | 125 | Binance 限制 |
| base_usdt_amount | 100 | - | Binance 最低 |
| max_position_ratio | 0.01 | 1.0 | 百分比 |
| rsi_extreme_threshold_upper | 50 | 100 | RSI 范围 |
| rsi_extreme_threshold_lower | 0 | 50 | RSI 范围 |
| timer_interval_sec | 60 | 86400 | 1分钟到1天 |
| min_sl_distance_pct | 0.001 | 0.1 | 0.1% 到 10% |
| default_sl_pct | 0.005 | 0.2 | 0.5% 到 20% |

### 6.3 依赖验证

| 条件 | 说明 |
|------|------|
| `rsi_extreme_threshold_lower < rsi_extreme_threshold_upper` | RSI 下限必须小于上限 |
| `macd_fast < macd_slow` | MACD 快线周期必须小于慢线 |
| `telegram.enabled` 时需要 `bot_token` 和 `chat_id` | Telegram 依赖检查 |
| `min_sl_distance_pct <= default_sl_pct` | 最小距离不能超过默认值 |

---

## 7. 使用方式

### 7.1 命令行启动

```bash
# 生产环境 (默认)
python main_live.py

# 开发环境
python main_live.py --env development

# 回测环境
python main_live.py --env backtest

# 指定配置目录
python main_live.py --config-dir /path/to/configs
```

### 7.2 代码中使用

```python
from utils.config_manager import ConfigManager

# 加载配置
config = ConfigManager(env="production")
config.load()

# 获取配置值
equity = config.get('capital', 'equity')
leverage = config.get('capital', 'leverage')
temperature = config.get('ai', 'deepseek', 'temperature')

# 获取嵌套配置
min_sl = config.get('trading_logic', 'min_sl_distance_pct')

# 获取策略配置对象
strategy_config = config.to_strategy_config()

# 检查验证结果
if config.get_errors():
    for error in config.get_errors():
        print(f"Error: {error.field} - {error.message}")
```

### 7.3 Telegram 命令 (可选扩展)

```
/config                 - 查看当前配置摘要
/config get capital.equity  - 查看特定配置
/config set capital.leverage 5  - 修改配置 (需要重启)
```

---

## 8. Pydantic 升级建议 (可选)

### 8.1 为什么考虑 Pydantic

根据 [Pydantic Settings 官方文档](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) 和社区最佳实践，`pydantic-settings` 是 2025 年 Python 配置管理的推荐方案：

| 特性 | 当前方案 (YAML + ConfigManager) | Pydantic Settings |
|------|--------------------------------|-------------------|
| 类型验证 | ✅ 手动实现 | ✅ 自动 |
| 嵌套配置 | ✅ 支持 | ✅ 支持 |
| .env 集成 | ✅ python-dotenv | ✅ 内置 |
| YAML 支持 | ✅ 原生 | ⚠️ 需扩展 |
| IDE 自动补全 | ❌ 无 | ✅ 完整 |
| 敏感信息处理 | ⚠️ 手动 | ✅ SecretStr |
| 维护成本 | 中 | 低 |

### 8.2 Pydantic 版本 ConfigManager

```python
# utils/config_manager_pydantic.py (可选升级)

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class TradingLogicConfig(BaseModel):
    """交易逻辑配置"""
    min_notional_usdt: float = Field(100.0, ge=1, le=10000)
    min_sl_distance_pct: float = Field(0.01, ge=0.001, le=0.1)
    default_sl_pct: float = Field(0.02, ge=0.005, le=0.2)
    quantity_adjustment_step: float = Field(0.001, ge=0.0001, le=0.01)

class AIConfig(BaseModel):
    """AI 配置"""
    model: str = "deepseek-chat"
    temperature: float = Field(0.3, ge=0.0, le=2.0)
    max_retries: int = Field(2, ge=1, le=10)

class RiskConfig(BaseModel):
    """风险配置"""
    rsi_extreme_threshold_upper: float = Field(70.0, ge=50, le=100)
    rsi_extreme_threshold_lower: float = Field(30.0, ge=0, le=50)

    @field_validator('rsi_extreme_threshold_lower')
    @classmethod
    def validate_rsi_order(cls, v, info):
        upper = info.data.get('rsi_extreme_threshold_upper', 70.0)
        if v >= upper:
            raise ValueError('RSI lower must be less than upper')
        return v

class AppSettings(BaseSettings):
    """应用配置 (自动从环境变量和 .env 加载)"""
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        env_nested_delimiter='__',
        extra='ignore'
    )

    # 敏感信息 (从 .env 加载)
    binance_api_key: SecretStr
    binance_api_secret: SecretStr
    deepseek_api_key: SecretStr
    telegram_bot_token: Optional[SecretStr] = None

    # 嵌套配置
    trading_logic: TradingLogicConfig = TradingLogicConfig()
    ai: AIConfig = AIConfig()
    risk: RiskConfig = RiskConfig()
```

### 8.3 升级路径

| 阶段 | 任务 | 复杂度 |
|------|------|--------|
| 当前 | 使用 YAML + ConfigManager (已设计) | - |
| Phase 1+ | 可选: 迁移到 pydantic-settings | 中 |

**建议**:
- 如果团队熟悉 Pydantic，可在 Phase 1 直接使用 pydantic-settings
- 否则，先使用当前 YAML + ConfigManager 方案，后续再考虑升级

---

## 9. 风险评估

### 9.1 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 配置加载失败 | 低 | 高 | 保留旧加载逻辑作为后备 |
| 类型转换错误 | 中 | 中 | 完善类型检查和错误提示 |
| 环境变量丢失 | 低 | 高 | 启动时检查必要配置 |
| 性能影响 | 低 | 低 | YAML 解析只在启动时进行 |
| **Phase 0 行为变化** | **高** | **中** | 先在测试环境验证 |
| **trading_logic 迁移影响** | 中 | 中 | 添加配置缓存机制 |
| **敏感信息泄露** | 中 | **高** | API_KEY 掩蔽机制 |
| **多线程安全** | 中 | 中 | ConfigManager 单例模式 |
| **配置版本不兼容** | 低 | 中 | 版本号和迁移脚本 |

### 9.2 高优先级风险详细评估

#### 🔴 风险 1: 敏感信息泄露

**风险描述**: API_KEY、API_SECRET 等敏感信息可能在日志、调试输出或错误信息中泄露。

**影响范围**:
- `BINANCE_API_KEY` / `BINANCE_API_SECRET`
- `DEEPSEEK_API_KEY`
- `TELEGRAM_BOT_TOKEN`

**缓解措施**:

```python
# ConfigManager 中添加敏感字段掩蔽
SENSITIVE_FIELDS = {'api_key', 'api_secret', 'bot_token', 'password'}

def _mask_sensitive(self, key: str, value: str) -> str:
    """掩蔽敏感信息"""
    if any(s in key.lower() for s in SENSITIVE_FIELDS):
        if len(value) > 8:
            return value[:4] + '****' + value[-4:]
        return '****'
    return value

def _log_config_summary(self):
    """记录配置摘要 (敏感信息已掩蔽)"""
    # 不记录 API_KEY 原始值
    self.logger.info(f"  Binance API: {self._mask_sensitive('api_key', self.get('binance', 'api_key', default=''))}")
```

**验证检查清单**:
- [ ] ConfigManager 日志不包含明文 API_KEY
- [ ] 错误信息不包含敏感配置值
- [ ] 调试模式下敏感字段已掩蔽

---

#### 🔴 风险 2: 多线程安全

**风险描述**: NautilusTrader 使用多线程架构，ConfigManager 可能被多个线程同时访问。

**影响场景**:
- 主线程: 策略初始化
- 后台线程: Telegram 命令处理
- 定时器线程: on_timer 回调

**缓解措施**:

```python
# 方案 A: 单例模式 + 启动时加载 (推荐)
_config_instance = None
_config_lock = threading.Lock()

def get_config() -> ConfigManager:
    """获取全局配置实例 (线程安全)"""
    global _config_instance
    if _config_instance is None:
        with _config_lock:
            if _config_instance is None:
                _config_instance = ConfigManager()
                _config_instance.load()
    return _config_instance

# 方案 B: 配置只读 + 启动时冻结
class ConfigManager:
    def __init__(self):
        self._frozen = False

    def load(self):
        # ... 加载配置 ...
        self._frozen = True  # 加载后冻结

    def set(self, *path, value):
        if self._frozen:
            raise RuntimeError("Configuration is frozen after load")
```

**设计原则**:
1. 配置只在启动时加载一次
2. 加载后配置不可变 (immutable)
3. 使用单例模式保证全局一致性

**验证检查清单**:
- [ ] ConfigManager 使用单例模式
- [ ] 配置加载后标记为只读
- [ ] 多线程访问测试通过

---

#### 🔴 风险 3: 运行时性能影响

**风险描述**: YAML 解析和配置验证可能增加启动时间。

**性能预期**:

| 操作 | 预期时间 | 可接受阈值 |
|------|---------|-----------|
| YAML 加载 (base.yaml) | < 10ms | 50ms |
| 环境文件合并 | < 5ms | 20ms |
| 配置验证 | < 20ms | 100ms |
| **总启动开销** | **< 50ms** | **200ms** |

**缓解措施**:

```python
# 添加性能监控
import time

def load(self) -> Dict[str, Any]:
    start = time.perf_counter()

    # ... 加载逻辑 ...

    elapsed = (time.perf_counter() - start) * 1000
    self.logger.info(f"Configuration loaded in {elapsed:.1f}ms")

    if elapsed > 200:
        self.logger.warning(f"Configuration loading exceeded threshold: {elapsed:.1f}ms > 200ms")
```

**性能优化建议**:
1. 使用 `yaml.CSafeLoader` 代替 `yaml.SafeLoader` (C 实现更快)
2. 避免在验证中进行网络请求
3. 缓存解析结果，避免重复加载

**验证检查清单**:
- [ ] 启动时间基准测试 < 200ms
- [ ] 使用 CSafeLoader 加速 YAML 解析
- [ ] 配置加载时间记录到日志

---

#### 🔴 风险 4: 配置版本管理

**风险描述**: 升级 base.yaml 时，用户自定义的 production.yaml 可能与新版本不兼容。

**不兼容场景**:
- 新增必填字段，旧配置缺失
- 字段重命名，旧配置使用旧名称
- 字段类型变更，旧配置类型错误
- 字段废弃，旧配置仍在使用

**缓解措施**:

```yaml
# base.yaml 添加版本号
_meta:
  version: "2.2"
  min_compatible_version: "2.0"
  deprecated_fields:
    - "risk.skip_on_divergence"      # 已废弃，使用 TradingAgents 架构
    - "risk.use_confidence_fusion"   # 已废弃
```

```python
# ConfigManager 添加版本检查
def _check_version_compatibility(self):
    """检查配置版本兼容性"""
    meta = self._config.get('_meta', {})
    version = meta.get('version', '1.0')
    min_version = meta.get('min_compatible_version', '1.0')

    # 检查用户配置版本
    user_version = self._user_config.get('_meta', {}).get('version', '1.0')
    if self._version_compare(user_version, min_version) < 0:
        self._errors.append(ConfigValidationError(
            field='_meta.version',
            message=f"Configuration version {user_version} is incompatible. Minimum required: {min_version}",
            value=user_version
        ))

    # 警告废弃字段
    deprecated = meta.get('deprecated_fields', [])
    for field in deprecated:
        if self._get_nested(self._user_config, field.split('.')):
            self._warnings.append(ConfigValidationError(
                field=field,
                message=f"Field '{field}' is deprecated and will be removed in future versions",
                value=None,
                severity="warning"
            ))
```

**迁移脚本设计**:

```bash
# scripts/migrate_config.py
# 用途: 升级用户配置到新版本

python scripts/migrate_config.py --from 2.1 --to 2.2 --config production.yaml
```

**验证检查清单**:
- [ ] base.yaml 包含 `_meta.version` 字段
- [ ] ConfigManager 检查版本兼容性
- [ ] 废弃字段产生警告而非错误
- [ ] 提供迁移脚本文档

---

### 9.3 Phase 0 行为变化说明

修复配置冲突后，以下参数将改变：

| 参数 | 旧值 (硬编码) | 新值 (YAML) | 影响 |
|------|--------------|-------------|------|
| `deepseek_temperature` | 0.1 | 0.3 | AI 输出更多样，信号可能更多变 |
| `rsi_extreme_threshold_upper` | 75 | 70 | 更早触发超买判断 |
| `rsi_extreme_threshold_lower` | 25 | 30 | 更早触发超卖判断 |

**建议**: 如需保持旧行为，可以在 production.yaml 中覆盖这些值。

### 9.4 测试计划

1. **单元测试**: ConfigManager 各方法测试
2. **集成测试**: 完整配置加载流程测试
3. **回归测试**: 与旧系统行为对比
4. **Phase 0 验证**: 在测试账户运行 24 小时
5. **生产验证**: 先在小资金账户验证
6. **性能测试**: 配置加载时间 < 200ms
7. **多线程测试**: 并发访问配置无竞态条件
8. **安全测试**: 日志和错误信息不包含敏感数据

### 9.5 实施前检查清单

#### 必须完成 (阻塞实施)

- [ ] **敏感信息保护**: API_KEY 掩蔽机制已实现
- [ ] **线程安全**: ConfigManager 使用单例模式
- [ ] **性能基准**: 配置加载时间 < 200ms
- [ ] **版本管理**: base.yaml 包含 `_meta.version`
- [ ] **回滚方案**: 各 Phase 回滚步骤已验证

#### 建议完成 (不阻塞)

- [ ] 配置权限检查 (.env 应为 600 权限)
- [ ] 配置导出/导入功能
- [ ] Telegram `/config` 命令支持
- [ ] 配置变更审计日志

---

## 10. 总结

### 10.1 改进收益

| 方面 | 改进前 | 改进后 |
|------|--------|--------|
| 配置来源 | 6 处分散 | 1 个 base.yaml |
| 硬编码参数 | 50 处 | 0 处 (全部配置化) |
| 配置冲突 | 3 处硬编码覆盖 | ✅ **已消除** (Phase 0) |
| 环境切换 | 手动修改 | --env 参数 |
| 配置验证 | 无 | 类型 + 范围 + 依赖检查 |
| 错误提示 | 运行时崩溃 | 启动时明确提示 |
| trading_logic | 9 处硬编码 | 可配置 |
| network | 16 处硬编码 | 可配置 |

### 10.2 实施优先级

```
✅ 完成 (Phase 0): 修复 main_live.py 中的 3 处配置冲突
🟠 高   (Phase 1-2): 创建 ConfigManager 并迁移核心配置
🟡 中   (Phase 3-4): 迁移 trading_logic.py 和 utils 硬编码
🟢 低   (Phase 5-6): 添加环境切换和高级功能
```

### 10.3 变更日志

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-01-23 | 初始方案 |
| 2.0 | 2026-01-24 | 基于代码审查更新:<br>- 添加 trading_logic.py 新文件<br>- 识别 3 处配置冲突<br>- 硬编码从 36 处更新到 42 处<br>- 添加 Phase 0 紧急修复<br>- 扩展 base.yaml 配置结构<br>- 增强 ConfigManager 验证逻辑 |
| 2.1 | 2026-01-24 | 补充遗漏项 (基于 CLAUDE.md 规范):<br>- 硬编码从 42 处更新到 48 处<br>- 新增: TP_PCT_CONFIG 止盈配置字典<br>- 新增: 仓位精度调整步长 (0.001)<br>- 新增: bar_persistence 超时和限制<br>- 新增: oco_manager Redis 超时<br>- 更新 ConfigManager 验证规则 |
| 2.2 | 2026-01-24 | 执行建议并更新方案:<br>- ✅ **Phase 0 完成**: 修复 main_live.py 配置冲突<br>- 硬编码从 48 处更新到 50 处<br>- 新增: indicators/technical_manager.py 参数<br>- 新增: 第 8 章 Pydantic 升级建议<br>- 更新统计表标记 Phase 0 已完成 |
| 2.3 | 2026-01-24 | 补充高优先级风险评估:<br>- 🔴 敏感信息泄露防护 (API_KEY 掩蔽机制)<br>- 🔴 多线程安全 (单例模式设计)<br>- 🔴 运行时性能影响 (< 200ms 基准)<br>- 🔴 配置版本管理 (版本号 + 迁移脚本)<br>- 新增: 实施前检查清单<br>- 修正: 第 9 章节编号 |

---

*方案 v2.3 已完成风险评估补充。Phase 0 已完成，可按检查清单开始实施 Phase 1。*
