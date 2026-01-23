# AItrader 配置统一管理方案

> 版本: 1.0
> 日期: 2026-01-23
> 状态: 待评估

---

## 目录

1. [现状分析](#1-现状分析)
2. [目标架构](#2-目标架构)
3. [配置文件设计](#3-配置文件设计)
4. [ConfigManager 类设计](#4-configmanager-类设计)
5. [迁移计划](#5-迁移计划)
6. [验证规则](#6-验证规则)
7. [使用方式](#7-使用方式)
8. [风险评估](#8-风险评估)

---

## 1. 现状分析

### 1.1 当前配置分布

| 位置 | 参数数量 | 用途 | 问题 |
|------|---------|------|------|
| `~/.env.aitrader` | 8 | API 密钥、敏感信息 | ✅ 合理 |
| `configs/strategy_config.yaml` | 60+ | 策略参数 | ⚠️ 未完全使用 |
| `strategy/deepseek_strategy.py` | 52 | 默认值 | ❌ 与 YAML 重复/不同步 |
| `main_live.py` | 15 | 加载逻辑 + 硬编码 | ❌ 混乱 |
| `utils/*.py` | 15 | 工具类硬编码 | ❌ 分散 |

### 1.2 已识别的硬编码 (36 处需处理)

#### 交易核心参数 (P0 - 必须配置化)
```python
# deepseek_strategy.py:1067
MIN_NOTIONAL_USDT = 100.0  # Binance 最低名义价值

# deepseek_strategy.py:1085
MIN_NOTIONAL_SAFETY_MARGIN = 1.01  # 安全边际

# main_live.py:254
instrument_id = "BTCUSDT-PERP.BINANCE"  # 交易对

# deepseek_strategy.py:566
limit: int = 200  # 历史K线数量
```

#### 网络重试参数 (P1)
```python
# deepseek_strategy.py:409-410
max_retries = 60
retry_interval = 1.0

# telegram_command_handler.py:453-459
startup_delay = 5
max_retries = 3
base_delay = 10

# binance_account.py:55,78
_cache_ttl = 5.0
recvWindow = 5000
```

#### AI/分析参数 (P2)
```python
# deepseek_client.py:598
signal_history_count = 3

# multi_agent_analyzer.py:75
retry_delay = 1.0
```

#### 测试模式参数 (P3)
```python
# main_live.py:191-195 (1分钟测试模式特殊值)
sma_periods = [3, 7, 15]
rsi_period = 7
macd_fast = 5
```

### 1.3 当前加载优先级 (不明确)

```
环境变量 (.env) → YAML → 代码默认值 → ??? (混乱)
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
│  4. ConfigManager.validate() (类型检查 + 范围验证)               │
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

# =============================================================================
# 交易配置
# =============================================================================
trading:
  # 交易对配置
  instrument_id: "BTCUSDT-PERP.BINANCE"
  bar_type: "BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-EXTERNAL"

  # Binance 交易限制
  min_notional_usdt: 100.0        # Binance 最低名义价值 (不建议修改)
  min_notional_safety_margin: 1.01  # 安全边际 1%

  # 数据获取
  historical_bars_limit: 200      # 启动时获取的历史K线数量

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
    temperature: 0.3
    max_retries: 2
    base_url: "https://api.deepseek.com"

  # 多代理辩论配置
  multi_agent:
    debate_rounds: 2              # 辩论轮数 (1-3)
    retry_delay: 1.0              # 重试延迟 (秒)

  # 信号处理
  signal:
    history_count: 3              # 检查连续信号数量
    skip_on_divergence: true      # AI 分歧时跳过交易

# =============================================================================
# 情绪数据
# =============================================================================
sentiment:
  enabled: true
  provider: "binance"             # binance / cryptooracle (已弃用)
  lookback_hours: 4
  timeframe: "15m"
  weight: 0.30                    # 决策权重

# =============================================================================
# 风险管理
# =============================================================================
risk:
  # 信心阈值
  min_confidence_to_trade: "MEDIUM"  # LOW / MEDIUM / HIGH
  allow_reversals: true
  require_high_confidence_for_reversal: false

  # RSI 阈值
  rsi_extreme_threshold_upper: 75.0
  rsi_extreme_threshold_lower: 25.0
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
  # 通用重试
  max_retries: 60                 # 最大重试次数
  retry_interval: 1.0             # 重试间隔 (秒)

  # Binance API
  binance:
    recv_window: 5000             # 接收窗口 (ms)
    balance_cache_ttl: 5.0        # 余额缓存时间 (秒)

  # Telegram
  telegram:
    startup_delay: 5              # 启动延迟 (秒)
    max_retries: 3                # 最大重试次数
    base_delay: 10                # 重试基础延迟 (秒)

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
from typing import Any, Dict, Optional
import yaml
from dataclasses import dataclass
from dotenv import load_dotenv
import os


@dataclass
class ConfigValidationError:
    """配置验证错误"""
    field: str
    message: str
    value: Any


class ConfigManager:
    """
    统一配置管理器

    功能:
    - 分层加载配置 (base → env → .env)
    - 类型验证
    - 范围检查
    - 环境切换
    """

    def __init__(
        self,
        config_dir: Path = None,
        env: str = "production"
    ):
        """
        初始化配置管理器

        Parameters
        ----------
        config_dir : Path
            配置目录，默认为项目根目录/configs
        env : str
            环境名称: production / development / backtest
        """
        self.config_dir = config_dir or Path(__file__).parent.parent / "configs"
        self.env = env
        self._config: Dict[str, Any] = {}
        self._errors: list[ConfigValidationError] = []

    def load(self) -> Dict[str, Any]:
        """
        加载并合并所有配置

        Returns
        -------
        dict
            合并后的配置字典
        """
        # 1. 加载 base.yaml
        base_config = self._load_yaml("base.yaml")
        self._config = base_config

        # 2. 加载环境配置并合并
        env_file = f"{self.env}.yaml"
        if (self.config_dir / env_file).exists():
            env_config = self._load_yaml(env_file)
            self._config = self._deep_merge(self._config, env_config)

        # 3. 加载 .env 敏感信息
        self._load_env_secrets()

        # 4. 验证配置
        self.validate()

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

        # 验证规则
        rules = [
            # (字段路径, 类型, 最小值, 最大值, 必填)
            (('capital', 'equity'), (int, float), 100, 1000000, True),
            (('capital', 'leverage'), (int, float), 1, 125, True),
            (('position', 'base_usdt_amount'), (int, float), 100, None, True),
            (('position', 'max_position_ratio'), float, 0.01, 1.0, True),
            (('risk', 'rsi_extreme_threshold_upper'), (int, float), 50, 100, True),
            (('risk', 'rsi_extreme_threshold_lower'), (int, float), 0, 50, True),
            (('timing', 'timer_interval_sec'), int, 60, 86400, True),
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
                    message=f"Expected {expected_type}, got {type(value)}",
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

        return len(self._errors) == 0

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

    def get_errors(self) -> list[ConfigValidationError]:
        """获取验证错误列表"""
        return self._errors

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
        )

    def print_summary(self):
        """打印配置摘要"""
        print("=" * 60)
        print("  Configuration Summary")
        print("=" * 60)
        print(f"  Environment: {self.env}")
        print(f"  Instrument: {self.get('trading', 'instrument_id')}")
        print(f"  Equity: ${self.get('capital', 'equity'):,.2f}")
        print(f"  Leverage: {self.get('capital', 'leverage')}x")
        print(f"  Timer: {self.get('timing', 'timer_interval_sec')}s")
        print(f"  Telegram: {'Enabled' if self.get('telegram', 'enabled') else 'Disabled'}")

        if self._errors:
            print("\n  ⚠️ Validation Errors:")
            for error in self._errors:
                print(f"    - {error.field}: {error.message}")
        else:
            print("\n  ✅ Configuration validated successfully")
        print("=" * 60)
```

---

## 5. 迁移计划

### 5.1 分阶段实施

| 阶段 | 任务 | 文件变更 | 风险 | 预计时间 |
|------|------|---------|------|---------|
| **Phase 1** | 创建 ConfigManager 和 base.yaml | 新增 2 文件 | 低 | - |
| **Phase 2** | 修改 main_live.py 使用 ConfigManager | 修改 1 文件 | 中 | - |
| **Phase 3** | 移除 deepseek_strategy.py 默认值 | 修改 1 文件 | 中 | - |
| **Phase 4** | 迁移 utils 中的硬编码 | 修改 4 文件 | 低 | - |
| **Phase 5** | 添加环境切换和 CLI 参数 | 修改 1 文件 | 低 | - |
| **Phase 6** | 测试和文档更新 | 多文件 | 低 | - |

### 5.2 回滚方案

如果出现问题，可以快速回滚：

```bash
# 保留旧的 main_live.py
git checkout HEAD~1 -- main_live.py

# 或完全回滚
git revert <commit-hash>
```

### 5.3 兼容性保证

- 旧的 `.env.aitrader` 格式完全兼容
- 旧的 `strategy_config.yaml` 可以继续使用
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

### 6.3 依赖验证

| 条件 | 说明 |
|------|------|
| `rsi_extreme_threshold_lower < rsi_extreme_threshold_upper` | RSI 下限必须小于上限 |
| `macd_fast < macd_slow` | MACD 快线周期必须小于慢线 |
| `telegram.enabled` 时需要 `bot_token` 和 `chat_id` | Telegram 依赖检查 |

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

# 获取策略配置对象
strategy_config = config.to_strategy_config()
```

### 7.3 Telegram 命令 (可选扩展)

```
/config                 - 查看当前配置摘要
/config get capital.equity  - 查看特定配置
/config set capital.leverage 5  - 修改配置 (需要重启)
```

---

## 8. 风险评估

### 8.1 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 配置加载失败 | 低 | 高 | 保留旧加载逻辑作为后备 |
| 类型转换错误 | 中 | 中 | 完善类型检查和错误提示 |
| 环境变量丢失 | 低 | 高 | 启动时检查必要配置 |
| 性能影响 | 低 | 低 | YAML 解析只在启动时进行 |

### 8.2 测试计划

1. **单元测试**: ConfigManager 各方法测试
2. **集成测试**: 完整配置加载流程测试
3. **回归测试**: 与旧系统行为对比
4. **生产验证**: 先在测试账户验证

---

## 9. 总结

### 9.1 改进收益

| 方面 | 改进前 | 改进后 |
|------|--------|--------|
| 配置来源 | 4 处分散 | 1 个 base.yaml |
| 默认值同步 | 手动维护 | 自动单一来源 |
| 环境切换 | 手动修改 | --env 参数 |
| 配置验证 | 无 | 类型 + 范围检查 |
| 错误提示 | 运行时崩溃 | 启动时明确提示 |

### 9.2 决策点

请确认以下事项：

1. **是否采用此方案？**
2. **是否需要 Telegram 命令修改配置功能？**
3. **是否需要配置热重载（不重启生效）？**
4. **是否需要 JSON Schema 验证？**

---

*等待您的评估和反馈。*
