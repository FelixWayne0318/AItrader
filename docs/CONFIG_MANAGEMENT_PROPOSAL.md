# AItrader 配置统一管理方案

> 版本: 2.2
> 日期: 2026-01-24
> 状态: **Phase 0 已完成，继续实施 Phase 1-6**
> 审查: CONFIG_PROPOSAL_REVIEW.md

---

## 目录

1. [现状分析](#1-现状分析)
2. [目标架构](#2-目标架构)
3. [配置文件设计](#3-配置文件设计)
4. [ConfigManager 类设计](#4-configmanager-类设计)
5. [迁移计划](#5-迁移计划)
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
```

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

        # 映射环境变量到配置
        env_mappings = {
            'BINANCE_API_KEY': ('binance', 'api_key'),
            'BINANCE_API_SECRET': ('binance', 'api_secret'),
            'DEEPSEEK_API_KEY': ('ai', 'deepseek', 'api_key'),
            'TELEGRAM_BOT_TOKEN': ('telegram', 'bot_token'),
            'TELEGRAM_CHAT_ID': ('telegram', 'chat_id'),
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
| **Phase 3** | 迁移 trading_logic.py 常量 | 修改 2 文件 | 中 | 中 |
| **Phase 4** | 迁移 utils 中的硬编码 | 修改 5 文件 | 低 | 中 |
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

```python
# strategy/trading_logic.py 修改

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

# 提供常量访问接口
MIN_NOTIONAL_USDT = property(lambda self: _get_config()['min_notional_usdt'])
# ... 或使用函数:
def get_min_notional_usdt():
    return _get_config()['min_notional_usdt']
```

### 5.4 回滚方案

如果出现问题，可以快速回滚：

```bash
# 保留旧的 main_live.py
git checkout HEAD~1 -- main_live.py

# 或完全回滚
git revert <commit-hash>
```

### 5.5 兼容性保证

- 旧的 `.env.aitrader` 格式完全兼容
- 旧的 `strategy_config.yaml` 可以继续使用 (但建议迁移到 base.yaml)
- 添加迁移脚本自动转换旧配置

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

### 8.1 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 配置加载失败 | 低 | 高 | 保留旧加载逻辑作为后备 |
| 类型转换错误 | 中 | 中 | 完善类型检查和错误提示 |
| 环境变量丢失 | 低 | 高 | 启动时检查必要配置 |
| 性能影响 | 低 | 低 | YAML 解析只在启动时进行 |
| **Phase 0 行为变化** | **高** | **中** | 先在测试环境验证 |
| **trading_logic 迁移影响** | 中 | 中 | 添加配置缓存机制 |

### 8.2 Phase 0 行为变化说明

修复配置冲突后，以下参数将改变：

| 参数 | 旧值 (硬编码) | 新值 (YAML) | 影响 |
|------|--------------|-------------|------|
| `deepseek_temperature` | 0.1 | 0.3 | AI 输出更多样，信号可能更多变 |
| `rsi_extreme_threshold_upper` | 75 | 70 | 更早触发超买判断 |
| `rsi_extreme_threshold_lower` | 25 | 30 | 更早触发超卖判断 |

**建议**: 如需保持旧行为，可以在 production.yaml 中覆盖这些值。

### 8.3 测试计划

1. **单元测试**: ConfigManager 各方法测试
2. **集成测试**: 完整配置加载流程测试
3. **回归测试**: 与旧系统行为对比
4. **Phase 0 验证**: 在测试账户运行 24 小时
5. **生产验证**: 先在小资金账户验证

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

---

*方案已审查，可以开始实施。建议从 Phase 0 (修复配置冲突) 开始。*
