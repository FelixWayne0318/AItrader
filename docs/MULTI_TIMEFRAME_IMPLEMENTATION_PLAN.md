# 多时间框架实施方案 v3.0

## 文档信息

| 项目 | 值 |
|------|-----|
| 版本 | 3.0 |
| 创建日期 | 2026-01-26 |
| 更新日期 | 2026-01-26 |
| 基于 | TradingAgents 架构 + AItrader 现有系统 |
| 状态 | 已审查修复 (v3.0 最终版) |

## 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-01-26 | 初始方案设计 |
| v2.0 | 2026-01-26 | 根据审查报告修复 API 兼容性问题 |
| v3.0 | 2026-01-26 | 全面仓库审查后修复，合并审查报告，删除冗余文件 |

### v3.0 主要更新

1. **删除独立审查报告** - 审查结论合并到本文档
2. **修复 ConfigManager 问题** - 辅助方法不存在，改用直接 `get()` 调用
3. **修复 SMA_200 缺失** - 需要在配置中添加 200 周期
4. **修复 conftest.py 缺失** - 当前测试无 pytest fixtures
5. **简化配置访问** - 移除不存在的辅助方法依赖

---

## 1. 架构概述

### 1.1 时间框架设计

基于用户需求和 TradingAgents 架构，采用三层时间框架：

| 层级 | 周期 | 职责 | 更新频率 | 触发方式 |
|------|------|------|----------|----------|
| **趋势层** | 1D | Risk-On / Risk-Off 判断 | 每日 1 次 | 日线 bar 收盘事件 |
| **决策层** | 4H | 允许做多 / 做空 / 观望 | 每 4 小时 | 4H bar 收盘事件 |
| **执行层** | 5M / 15M | 精确入场、SL、TP | 每 5-15 分钟 | 定时器 + bar 事件 |

### 1.2 决策流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           1D 趋势层 (日线收盘时更新)                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  输入: 1D K线数据                                                    │    │
│  │  指标: SMA_200, MACD趋势, 价格位置                                   │    │
│  │  输出: RISK_ON / RISK_OFF                                           │    │
│  │                                                                      │    │
│  │  规则 (v3.0 - 使用现有指标):                                         │    │
│  │  ├─ Price > SMA_200 + MACD > 0 → RISK_ON (可交易)                   │    │
│  │  └─ Price < SMA_200 或 MACD < 0 → RISK_OFF (观望)                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                     │                                        │
│                    RISK_OFF ────────┴──────── RISK_ON                       │
│                        │                          │                          │
│                        ▼                          ▼                          │
│                   [禁止交易]               [进入决策层]                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          4H 决策层 (4H bar 收盘时更新)                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  输入: 4H K线数据 + 1D 趋势状态                                      │    │
│  │  指标: MACD, RSI_14, BB_20, SMA_20/50                               │    │
│  │                                                                      │    │
│  │  Phase 1: Bull/Bear 辩论 (TradingAgents 架构)                       │    │
│  │  ├─ Bull Agent: 分析 4H 数据中的做多理由                            │    │
│  │  └─ Bear Agent: 分析 4H 数据中的做空理由                            │    │
│  │                                                                      │    │
│  │  Phase 2: Judge 决策                                                 │    │
│  │  └─ 基于辩论结果 + 量化规则，决定方向                               │    │
│  │                                                                      │    │
│  │  输出: ALLOW_LONG / ALLOW_SHORT / WAIT                              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      5M/15M 执行层 (定时器触发)                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  输入: 5M/15M K线数据 + 4H 决策方向                                  │    │
│  │  指标: RSI_14, EMA_10, 支撑/阻力                                    │    │
│  │                                                                      │    │
│  │  Phase 3: Risk Manager 评估 (TradingAgents 架构)                    │    │
│  │  └─ 确定: 入场价位、止损、止盈、仓位大小                            │    │
│  │                                                                      │    │
│  │  执行条件检查:                                                       │    │
│  │  ├─ 1D = RISK_ON ✓                                                  │    │
│  │  ├─ 4H = ALLOW_LONG/SHORT ✓                                         │    │
│  │  └─ 15M RSI 未极端 ✓                                                │    │
│  │                                                                      │    │
│  │  输出: 执行交易 或 继续等待                                          │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 与 TradingAgents 架构的对应关系

| TradingAgents 组件 | 当前 AItrader 实现 | 多时间框架改造 |
|-------------------|-------------------|----------------|
| Market Analyst | `TechnicalIndicatorManager` | 扩展为多周期版本 |
| Bull Researcher | `MultiAgentAnalyzer._get_bull_argument()` | 接收 4H 数据 |
| Bear Researcher | `MultiAgentAnalyzer._get_bear_argument()` | 接收 4H 数据 |
| Judge | `MultiAgentAnalyzer._get_judge_decision()` | 基于 4H 决策 |
| Risk Manager | `MultiAgentAnalyzer._evaluate_risk()` | 基于 5M/15M 执行 |
| Trader Agent | `DeepSeekAIStrategy._execute_trade()` | 综合三层信息 |

### 1.4 优先级规则

```python
# 跨层信号优先级: 趋势层 > 决策层 > 执行层
def get_final_action(risk_state, decision_state, execution_confirmed):
    """
    优先级规则:
    1. 趋势层 RISK_OFF → 禁止任何交易
    2. 决策层 WAIT → 等待方向确认
    3. 执行层未确认 → 等待入场时机
    """
    if risk_state == RiskState.RISK_OFF:
        return "NO_TRADE"  # 趋势层否决

    if decision_state == DecisionState.WAIT:
        return "WAIT_DIRECTION"  # 决策层等待

    if not execution_confirmed:
        return "WAIT_ENTRY"  # 执行层等待确认

    # 所有层都确认
    if decision_state == DecisionState.ALLOW_LONG:
        return "EXECUTE_LONG"
    elif decision_state == DecisionState.ALLOW_SHORT:
        return "EXECUTE_SHORT"

    return "HOLD"
```

---

## 2. 配置系统改动

### 2.1 新增配置结构 (configs/base.yaml)

```yaml
# =============================================================================
# 多时间框架配置 (Multi-Timeframe Framework) v3.0
# =============================================================================
multi_timeframe:
  enabled: false                      # 默认禁用，确保向后兼容

  # ---------------------------------------------------------------------------
  # 趋势层配置 (1D)
  # ---------------------------------------------------------------------------
  trend_layer:
    timeframe: "1d"
    sma_period: 200                   # SMA200 判断趋势
    require_above_sma: true           # 价格需在 SMA 上方
    require_macd_positive: true       # MACD > 0
    cache_ttl_hours: 4

  # ---------------------------------------------------------------------------
  # 决策层配置 (4H)
  # ---------------------------------------------------------------------------
  decision_layer:
    timeframe: "4h"
    debate_rounds: 2
    include_trend_context: true

  # ---------------------------------------------------------------------------
  # 执行层配置 (5M / 15M)
  # ---------------------------------------------------------------------------
  execution_layer:
    default_timeframe: "15m"
    high_volatility_timeframe: "5m"
    rsi_entry_min: 35                 # RSI 入场范围下限
    rsi_entry_max: 65                 # RSI 入场范围上限
```

### 2.2 配置访问方式 (v3.0 修正)

**重要**: ConfigManager 没有 `is_mtf_enabled()` 等辅助方法，必须使用 `get()` 直接访问。

```python
# v3.0 正确用法 - 直接使用 get()
from utils.config_manager import ConfigManager

config = ConfigManager(env='production')
config.load()

# 检查是否启用
mtf_enabled = config.get('multi_timeframe', 'enabled', default=False)

# 获取趋势层配置
trend_timeframe = config.get('multi_timeframe', 'trend_layer', 'timeframe', default='1d')
trend_sma_period = config.get('multi_timeframe', 'trend_layer', 'sma_period', default=200)

# 获取决策层配置
decision_timeframe = config.get('multi_timeframe', 'decision_layer', 'timeframe', default='4h')
debate_rounds = config.get('multi_timeframe', 'decision_layer', 'debate_rounds', default=2)

# 获取执行层配置
exec_timeframe = config.get('multi_timeframe', 'execution_layer', 'default_timeframe', default='15m')
rsi_entry_min = config.get('multi_timeframe', 'execution_layer', 'rsi_entry_min', default=35)
rsi_entry_max = config.get('multi_timeframe', 'execution_layer', 'rsi_entry_max', default=65)
```

### 2.3 向后兼容配置

当 `multi_timeframe.enabled: false` 时，系统行为与当前版本**完全一致**。

### 2.4 环境特定配置

**configs/production.yaml**:
```yaml
multi_timeframe:
  enabled: true
  execution_layer:
    default_timeframe: "15m"
```

**configs/development.yaml**:
```yaml
multi_timeframe:
  enabled: true
  trend_layer:
    timeframe: "4h"                   # 开发环境使用 4H 代替 1D
  decision_layer:
    timeframe: "1h"                   # 开发环境使用 1H 代替 4H
  execution_layer:
    default_timeframe: "5m"           # 开发环境使用 5M
```

---

## 3. 核心模块改动

### 3.1 新增: MultiTimeframeManager

创建新文件 `indicators/multi_timeframe_manager.py`:

```python
"""
Multi-Timeframe Indicator Manager v3.0

管理多个时间框架的技术指标，提供跨周期分析能力。

v3.0 更新:
- 移除对不存在的 ConfigManager 辅助方法的依赖
- 使用 MACD 替代 ADX (ADX 未在 TechnicalIndicatorManager 实现)
- 添加 SMA_200 支持 (需要在 TechnicalIndicatorManager 初始化时指定)
"""

from typing import Dict, Any, Optional
from enum import Enum
from datetime import datetime
import logging

from nautilus_trader.model.data import Bar, BarType
from indicators.technical_manager import TechnicalIndicatorManager


class RiskState(Enum):
    """趋势层风险状态"""
    RISK_ON = "RISK_ON"       # 可交易
    RISK_OFF = "RISK_OFF"     # 观望


class DecisionState(Enum):
    """决策层方向状态"""
    ALLOW_LONG = "ALLOW_LONG"   # 允许做多
    ALLOW_SHORT = "ALLOW_SHORT" # 允许做空
    WAIT = "WAIT"               # 等待


class MultiTimeframeManager:
    """
    多时间框架管理器 v3.0

    管理三层时间框架:
    - trend_layer (1D): Risk-On/Risk-Off 判断
    - decision_layer (4H): 方向决策
    - execution_layer (5M/15M): 入场执行
    """

    def __init__(
        self,
        config: Dict[str, Any],
        trend_bar_type: Optional[BarType] = None,
        decision_bar_type: Optional[BarType] = None,
        execution_bar_type: Optional[BarType] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        初始化多时间框架管理器

        Parameters
        ----------
        config : Dict
            多时间框架配置 (从 ConfigManager.get('multi_timeframe') 获取)
        trend_bar_type : BarType
            趋势层 BarType (用于精确匹配)
        decision_bar_type : BarType
            决策层 BarType
        execution_bar_type : BarType
            执行层 BarType
        logger : Logger
            日志记录器
        """
        self.config = config
        self.enabled = config.get('enabled', False)
        self.logger = logger or logging.getLogger(__name__)

        # 存储 BarType 用于精确匹配
        self.trend_bar_type = trend_bar_type
        self.decision_bar_type = decision_bar_type
        self.execution_bar_type = execution_bar_type

        if not self.enabled:
            self.logger.info("MultiTimeframeManager: disabled")
            return

        # 初始化三层指标管理器
        self.trend_manager: Optional[TechnicalIndicatorManager] = None
        self.decision_manager: Optional[TechnicalIndicatorManager] = None
        self.execution_manager: Optional[TechnicalIndicatorManager] = None

        # 状态缓存
        self._risk_state: RiskState = RiskState.RISK_OFF
        self._risk_state_updated: Optional[datetime] = None

        self._decision_state: DecisionState = DecisionState.WAIT
        self._decision_confidence: str = "LOW"
        self._decision_updated: Optional[datetime] = None

        # 上次更新的价格
        self._last_trend_price: float = 0.0
        self._last_decision_price: float = 0.0
        self._last_execution_price: float = 0.0

        # 初始化各层管理器
        self._init_managers()

        self.logger.info("MultiTimeframeManager: initialized with 3 layers")

    def _init_managers(self):
        """初始化各层技术指标管理器"""
        trend_config = self.config.get('trend_layer', {})
        decision_config = self.config.get('decision_layer', {})
        exec_config = self.config.get('execution_layer', {})

        # 趋势层 (1D) - 需要 SMA_200
        sma_period = trend_config.get('sma_period', 200)
        self.trend_manager = TechnicalIndicatorManager(
            sma_periods=[sma_period],  # SMA_200 用于趋势判断
            rsi_period=14,
            macd_fast=12,
            macd_slow=26,
        )
        self.logger.debug(f"趋势层管理器初始化: SMA_{sma_period}")

        # 决策层 (4H)
        self.decision_manager = TechnicalIndicatorManager(
            sma_periods=[20, 50],
            rsi_period=14,
            macd_fast=12,
            macd_slow=26,
            bb_period=20,
            bb_std=2.0,
        )
        self.logger.debug("决策层管理器初始化")

        # 执行层 (5M/15M)
        self.execution_manager = TechnicalIndicatorManager(
            sma_periods=[5, 20],
            ema_periods=[10],
            rsi_period=14,
            support_resistance_lookback=20,
        )
        self.logger.debug("执行层管理器初始化")

    def route_bar(self, bar: Bar) -> str:
        """
        路由 bar 到对应的管理器 (精确 BarType 匹配)

        Parameters
        ----------
        bar : Bar
            接收到的 bar 数据

        Returns
        -------
        str
            路由目标: "trend" / "decision" / "execution" / "unknown" / "disabled"
        """
        if not self.enabled:
            return "disabled"

        # 使用精确的 BarType 匹配
        if self.trend_bar_type and bar.bar_type == self.trend_bar_type:
            self.trend_manager.update(bar)
            self._last_trend_price = float(bar.close)
            self.logger.debug(f"[1D] 趋势层 bar 更新: close={bar.close}")
            return "trend"

        elif self.decision_bar_type and bar.bar_type == self.decision_bar_type:
            self.decision_manager.update(bar)
            self._last_decision_price = float(bar.close)
            self.logger.debug(f"[4H] 决策层 bar 更新: close={bar.close}")
            return "decision"

        elif self.execution_bar_type and bar.bar_type == self.execution_bar_type:
            self.execution_manager.update(bar)
            self._last_execution_price = float(bar.close)
            self.logger.debug(f"[15M] 执行层 bar 更新: close={bar.close}")
            return "execution"

        else:
            self.logger.warning(f"Unknown bar type: {bar.bar_type}")
            return "unknown"

    def evaluate_risk_state(self, current_price: float) -> RiskState:
        """
        评估趋势层风险状态 (Risk-On / Risk-Off)

        使用 MACD 替代 ADX (ADX 未在 TechnicalIndicatorManager 实现)

        Parameters
        ----------
        current_price : float
            当前价格

        Returns
        -------
        RiskState
            RISK_ON (可交易) 或 RISK_OFF (观望)
        """
        if not self.trend_manager or not self.trend_manager.is_initialized():
            self.logger.warning("趋势层未初始化，返回 RISK_OFF")
            return RiskState.RISK_OFF

        trend_config = self.config.get('trend_layer', {})
        tech_data = self.trend_manager.get_technical_data(current_price)

        # 规则 1: 价格在 SMA_200 上方
        sma_period = trend_config.get('sma_period', 200)
        sma_value = tech_data.get(f'sma_{sma_period}', current_price)
        price_above_sma = current_price > sma_value

        # 规则 2: MACD > 0 (替代 ADX，判断趋势方向)
        macd_value = tech_data.get('macd', 0)
        macd_positive = macd_value > 0

        # 综合判断
        require_above_sma = trend_config.get('require_above_sma', True)
        require_macd_positive = trend_config.get('require_macd_positive', True)

        conditions_met = True
        if require_above_sma:
            conditions_met = conditions_met and price_above_sma
        if require_macd_positive:
            conditions_met = conditions_met and macd_positive

        if conditions_met:
            self._risk_state = RiskState.RISK_ON
        else:
            self._risk_state = RiskState.RISK_OFF

        self._risk_state_updated = datetime.utcnow()

        self.logger.info(
            f"[1D] 趋势层评估: {self._risk_state.value} "
            f"(price={current_price:.2f}, SMA_{sma_period}={sma_value:.2f}, MACD={macd_value:.2f})"
        )

        return self._risk_state

    def get_risk_state(self) -> RiskState:
        """获取当前风险状态 (带缓存)"""
        return self._risk_state

    def get_decision_state(self) -> DecisionState:
        """获取当前决策状态"""
        return self._decision_state

    def set_decision_state(self, state: DecisionState, confidence: str = "MEDIUM"):
        """设置决策状态 (由 MultiAgentAnalyzer 调用)"""
        old_state = self._decision_state
        self._decision_state = state
        self._decision_confidence = confidence
        self._decision_updated = datetime.utcnow()

        self.logger.info(
            f"[4H] 决策层状态更新: {old_state.value} → {state.value} "
            f"(confidence={confidence})"
        )

    def get_technical_data_for_layer(self, layer: str, current_price: float) -> Dict[str, Any]:
        """
        获取指定层的技术数据

        Parameters
        ----------
        layer : str
            "trend" / "decision" / "execution"
        current_price : float
            当前价格

        Returns
        -------
        Dict
            技术指标数据
        """
        manager = {
            "trend": self.trend_manager,
            "decision": self.decision_manager,
            "execution": self.execution_manager,
        }.get(layer)

        if manager and manager.is_initialized():
            data = manager.get_technical_data(current_price)
            data['_layer'] = layer
            data['_timeframe'] = {
                'trend': '1D',
                'decision': '4H',
                'execution': '15M',
            }.get(layer, 'unknown')
            return data
        return {'_layer': layer, '_initialized': False}

    def check_execution_confirmation(self, current_price: float) -> Dict[str, Any]:
        """
        检查执行层入场确认条件

        Returns
        -------
        Dict
            {
                'confirmed': bool,
                'rsi': float,
                'rsi_in_range': bool,
                'reason': str
            }
        """
        if not self.execution_manager or not self.execution_manager.is_initialized():
            return {
                'confirmed': False,
                'reason': '执行层未初始化'
            }

        exec_config = self.config.get('execution_layer', {})
        tech_data = self.execution_manager.get_technical_data(current_price)

        rsi = tech_data.get('rsi', 50)
        rsi_min = exec_config.get('rsi_entry_min', 35)
        rsi_max = exec_config.get('rsi_entry_max', 65)
        rsi_in_range = rsi_min <= rsi <= rsi_max

        return {
            'confirmed': rsi_in_range,
            'rsi': rsi,
            'rsi_in_range': rsi_in_range,
            'rsi_range': [rsi_min, rsi_max],
            'reason': f'RSI={rsi:.1f} {"在" if rsi_in_range else "不在"}范围[{rsi_min}, {rsi_max}]内'
        }

    def is_all_layers_initialized(self) -> bool:
        """检查所有层是否都已初始化"""
        if not self.enabled:
            return True

        return (
            self.trend_manager and self.trend_manager.is_initialized() and
            self.decision_manager and self.decision_manager.is_initialized() and
            self.execution_manager and self.execution_manager.is_initialized()
        )

    def get_summary(self) -> Dict[str, Any]:
        """获取多时间框架状态摘要"""
        return {
            "enabled": self.enabled,
            "risk_state": self._risk_state.value if self._risk_state else "UNKNOWN",
            "risk_state_updated": self._risk_state_updated.isoformat() if self._risk_state_updated else None,
            "decision_state": self._decision_state.value if self._decision_state else "UNKNOWN",
            "decision_confidence": self._decision_confidence,
            "decision_updated": self._decision_updated.isoformat() if self._decision_updated else None,
            "layers_initialized": {
                "trend": self.trend_manager.is_initialized() if self.trend_manager else False,
                "decision": self.decision_manager.is_initialized() if self.decision_manager else False,
                "execution": self.execution_manager.is_initialized() if self.execution_manager else False,
            },
            "last_prices": {
                "trend": self._last_trend_price,
                "decision": self._last_decision_price,
                "execution": self._last_execution_price,
            }
        }
```

### 3.2 改动: DeepSeekAIStrategyConfig

由于 `frozen=True` 的 dataclass 不支持 `dict` 默认值，使用扁平化字段：

```python
# strategy/deepseek_strategy.py

class DeepSeekAIStrategyConfig(StrategyConfig, frozen=True):
    """Configuration for DeepSeek AI Strategy."""

    # ... 现有字段 ...

    # Multi-Timeframe Configuration (v3.0)
    # 使用基本类型，避免 frozen dataclass 限制
    multi_timeframe_enabled: bool = False

    # 趋势层 (1D)
    mtf_trend_timeframe: str = "1d"
    mtf_trend_sma_period: int = 200
    mtf_trend_require_above_sma: bool = True
    mtf_trend_require_macd_positive: bool = True

    # 决策层 (4H)
    mtf_decision_timeframe: str = "4h"
    mtf_decision_debate_rounds: int = 2

    # 执行层 (15M)
    mtf_execution_timeframe: str = "15m"
    mtf_execution_rsi_entry_min: int = 35
    mtf_execution_rsi_entry_max: int = 65
```

### 3.3 改动: main_live.py

```python
# main_live.py

def get_strategy_config(config_manager: ConfigManager) -> DeepSeekAIStrategyConfig:
    """Build strategy configuration from ConfigManager."""

    # ... 现有代码 ...

    # Multi-Timeframe Configuration (v3.0)
    # 注意: 使用 get() 直接访问，不依赖不存在的辅助方法
    mtf_enabled = config_manager.get('multi_timeframe', 'enabled', default=False)

    config_kwargs = {
        # ... 现有参数 ...

        # Multi-Timeframe
        'multi_timeframe_enabled': mtf_enabled,
    }

    if mtf_enabled:
        # 直接使用 get() 访问嵌套配置
        config_kwargs.update({
            # 趋势层
            'mtf_trend_timeframe': config_manager.get('multi_timeframe', 'trend_layer', 'timeframe', default='1d'),
            'mtf_trend_sma_period': config_manager.get('multi_timeframe', 'trend_layer', 'sma_period', default=200),
            'mtf_trend_require_above_sma': config_manager.get('multi_timeframe', 'trend_layer', 'require_above_sma', default=True),
            'mtf_trend_require_macd_positive': config_manager.get('multi_timeframe', 'trend_layer', 'require_macd_positive', default=True),

            # 决策层
            'mtf_decision_timeframe': config_manager.get('multi_timeframe', 'decision_layer', 'timeframe', default='4h'),
            'mtf_decision_debate_rounds': config_manager.get('multi_timeframe', 'decision_layer', 'debate_rounds', default=2),

            # 执行层
            'mtf_execution_timeframe': config_manager.get('multi_timeframe', 'execution_layer', 'default_timeframe', default='15m'),
            'mtf_execution_rsi_entry_min': config_manager.get('multi_timeframe', 'execution_layer', 'rsi_entry_min', default=35),
            'mtf_execution_rsi_entry_max': config_manager.get('multi_timeframe', 'execution_layer', 'rsi_entry_max', default=65),
        })

        print(f"[CONFIG] Multi-Timeframe enabled: 1D→4H→{config_kwargs['mtf_execution_timeframe']}")

    return DeepSeekAIStrategyConfig(**config_kwargs)
```

### 3.4 改动: DeepSeekAIStrategy

#### 3.4.1 __init__ 修改

```python
def __init__(self, config: DeepSeekAIStrategyConfig):
    super().__init__(config)

    # ... 现有初始化 ...

    # Multi-Timeframe Manager (v3.0)
    self.mtf_enabled = config.multi_timeframe_enabled
    self.mtf_manager = None

    if self.mtf_enabled:
        # 构建 BarType 对象
        symbol = str(config.instrument_id).split('.')[0]

        self.trend_bar_type = BarType.from_str(
            f"{symbol}.BINANCE-1-DAY-LAST-EXTERNAL"
        )
        self.decision_bar_type = BarType.from_str(
            f"{symbol}.BINANCE-4-HOUR-LAST-EXTERNAL"
        )
        self.execution_bar_type = BarType.from_str(
            f"{symbol}.BINANCE-15-MINUTE-LAST-EXTERNAL"
        )

        # 构建 MTF 配置字典
        mtf_config = {
            'enabled': True,
            'trend_layer': {
                'timeframe': config.mtf_trend_timeframe,
                'sma_period': config.mtf_trend_sma_period,
                'require_above_sma': config.mtf_trend_require_above_sma,
                'require_macd_positive': config.mtf_trend_require_macd_positive,
            },
            'decision_layer': {
                'timeframe': config.mtf_decision_timeframe,
                'debate_rounds': config.mtf_decision_debate_rounds,
            },
            'execution_layer': {
                'default_timeframe': config.mtf_execution_timeframe,
                'rsi_entry_min': config.mtf_execution_rsi_entry_min,
                'rsi_entry_max': config.mtf_execution_rsi_entry_max,
            }
        }

        from indicators.multi_timeframe_manager import MultiTimeframeManager
        self.mtf_manager = MultiTimeframeManager(
            config=mtf_config,
            trend_bar_type=self.trend_bar_type,
            decision_bar_type=self.decision_bar_type,
            execution_bar_type=self.execution_bar_type,
            logger=self.log,
        )

        self.log.info(f"Multi-Timeframe enabled: 1D/4H/15M")
```

#### 3.4.2 on_start 修改

```python
def on_start(self):
    """Actions to be performed on strategy start."""
    # ... 现有代码 ...

    if self.mtf_enabled:
        # 订阅多个时间框架
        self.subscribe_bars(self.trend_bar_type)
        self.subscribe_bars(self.decision_bar_type)
        self.subscribe_bars(self.execution_bar_type)
        self.log.info(f"MTF: Subscribed to 1D, 4H, 15M bars")

        # 预取各层历史数据
        self._prefetch_multi_timeframe_bars()
    else:
        # 现有单时间框架逻辑
        self.subscribe_bars(self.bar_type)
```

#### 3.4.3 on_bar 修改 (精确匹配)

```python
def on_bar(self, bar: Bar):
    """Handle bar updates."""
    self.bars_received += 1

    if self.mtf_enabled and self.mtf_manager:
        # 使用 MTF Manager 的精确路由
        layer = self.mtf_manager.route_bar(bar)

        if layer == "trend":
            # 日线收盘，触发趋势层评估
            self._on_trend_bar_close(bar)
        elif layer == "decision":
            # 4H 收盘，触发决策层分析
            self._on_decision_bar_close(bar)
        elif layer == "execution":
            # 执行层更新
            with self._state_lock:
                self._cached_current_price = float(bar.close)
        elif layer == "unknown":
            self.log.warning(f"Unknown bar type received: {bar.bar_type}")
    else:
        # 现有单时间框架逻辑
        self.indicator_manager.update(bar)
        with self._state_lock:
            self._cached_current_price = float(bar.close)

def _on_trend_bar_close(self, bar: Bar):
    """日线收盘处理"""
    from indicators.multi_timeframe_manager import RiskState

    current_price = float(bar.close)
    risk_state = self.mtf_manager.evaluate_risk_state(current_price)

    self.log.info(f"[1D] 趋势层评估完成: {risk_state.value}")

    if risk_state == RiskState.RISK_OFF:
        if self.telegram_bot and self.enable_telegram:
            self.telegram_bot.send_message_sync(
                f"⚠️ [1D] 趋势层: RISK_OFF\n"
                f"价格: ${current_price:,.2f}\n"
                f"暂停新开仓"
            )

def _on_decision_bar_close(self, bar: Bar):
    """4H 收盘处理 - 触发 Bull/Bear 辩论"""
    self.log.info("[4H] 决策层 bar 收盘，将在下次定时器触发分析")
```

#### 3.4.4 on_timer 修改

```python
def on_timer(self, event):
    """Periodic analysis and trading logic."""
    if not self.mtf_enabled:
        return self._on_timer_single_timeframe(event)

    return self._on_timer_multi_timeframe(event)

def _on_timer_multi_timeframe(self, event):
    """多时间框架定时分析"""
    from indicators.multi_timeframe_manager import RiskState, DecisionState

    self.log.info("=" * 60)
    self.log.info("[MTF] Running Multi-Timeframe Analysis...")

    # Step 1: 检查趋势层状态
    risk_state = self.mtf_manager.get_risk_state()

    if risk_state == RiskState.RISK_OFF:
        self.log.info("[1D] ⚠️ RISK_OFF - 跳过交易分析")
        return

    # Step 2: 获取决策层技术数据
    current_price = self._cached_current_price
    decision_tech_data = self.mtf_manager.get_technical_data_for_layer("decision", current_price)
    decision_tech_data['trend_layer_state'] = risk_state.value

    # Step 3: 运行 MultiAgent 分析 (基于 4H 数据)
    self.log.info("[4H] 开始 Bull/Bear 辩论...")

    multi_agent_result = self.multi_agent.analyze(
        symbol=str(self.instrument_id),
        technical_report=decision_tech_data,
        sentiment_report=self._get_sentiment_data(),
        current_position=self._get_current_position_info(),
        price_data={'price': current_price},
    )

    # Step 4: 更新决策层状态
    signal = multi_agent_result.get('signal', 'HOLD')
    confidence = multi_agent_result.get('confidence', 'LOW')

    if signal == 'BUY':
        self.mtf_manager.set_decision_state(DecisionState.ALLOW_LONG, confidence)
    elif signal == 'SELL':
        self.mtf_manager.set_decision_state(DecisionState.ALLOW_SHORT, confidence)
    else:
        self.mtf_manager.set_decision_state(DecisionState.WAIT, confidence)

    # Step 5: 执行层入场确认
    if signal in ['BUY', 'SELL']:
        confirmation = self.mtf_manager.check_execution_confirmation(current_price)

        if confirmation['confirmed']:
            self.log.info(f"[15M] ✅ 执行层确认: {confirmation['reason']}")
            self._execute_trade(multi_agent_result)
        else:
            self.log.info(f"[15M] ⏳ 执行层等待: {confirmation['reason']}")
    else:
        self.log.info(f"[4H] 决策层信号: {signal} - 不执行交易")
```

---

## 4. 诊断工具适配

### 4.1 diagnose_realtime.py 新增函数

```python
def diagnose_multi_timeframe(config_manager: ConfigManager):
    """诊断多时间框架配置和状态"""
    print("\n" + "=" * 60)
    print("🕐 多时间框架诊断")
    print("=" * 60)

    # 使用 get() 直接访问
    mtf_enabled = config_manager.get('multi_timeframe', 'enabled', default=False)
    print(f"多时间框架启用状态: {'✅ 已启用' if mtf_enabled else '❌ 未启用'}")

    if not mtf_enabled:
        print("跳过多时间框架诊断 (未启用)")
        return

    # 趋势层配置
    print(f"\n📈 趋势层 (1D):")
    print(f"  - 时间框架: {config_manager.get('multi_timeframe', 'trend_layer', 'timeframe', default='1d')}")
    print(f"  - SMA 周期: {config_manager.get('multi_timeframe', 'trend_layer', 'sma_period', default=200)}")
    print(f"  - 要求价格在 SMA 上方: {config_manager.get('multi_timeframe', 'trend_layer', 'require_above_sma', default=True)}")
    print(f"  - 要求 MACD > 0: {config_manager.get('multi_timeframe', 'trend_layer', 'require_macd_positive', default=True)}")

    # 决策层配置
    print(f"\n📊 决策层 (4H):")
    print(f"  - 时间框架: {config_manager.get('multi_timeframe', 'decision_layer', 'timeframe', default='4h')}")
    print(f"  - 辩论轮数: {config_manager.get('multi_timeframe', 'decision_layer', 'debate_rounds', default=2)}")

    # 执行层配置
    print(f"\n⚡ 执行层 (15M):")
    print(f"  - 默认周期: {config_manager.get('multi_timeframe', 'execution_layer', 'default_timeframe', default='15m')}")
    rsi_min = config_manager.get('multi_timeframe', 'execution_layer', 'rsi_entry_min', default=35)
    rsi_max = config_manager.get('multi_timeframe', 'execution_layer', 'rsi_entry_max', default=65)
    print(f"  - RSI 入场范围: [{rsi_min}, {rsi_max}]")

    # 实时数据验证
    print("\n📡 实时数据验证:")
    try:
        import requests

        for tf, name in [('1d', '趋势层'), ('4h', '决策层'), ('15m', '执行层')]:
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval={tf}&limit=1"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()[0]
                print(f"  ✅ {name} ({tf.upper()}): close=${float(data[4]):,.2f}")
            else:
                print(f"  ❌ {name} ({tf.upper()}): 获取失败")
    except Exception as e:
        print(f"  ❌ API 调用失败: {e}")
```

---

## 5. 测试用例

### 5.1 tests/test_multi_timeframe.py

**注意**: 当前测试目录没有 `conftest.py`，测试使用手动设置方式。

```python
"""
Multi-Timeframe Manager Tests v3.0

注意: 当前测试框架不使用 pytest fixtures (无 conftest.py)，
使用 unittest 风格的手动设置。
"""
import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime


class TestMultiTimeframeManager:
    """多时间框架管理器测试"""

    def get_disabled_config(self):
        """获取禁用配置"""
        return {"enabled": False}

    def get_enabled_config(self):
        """获取启用配置"""
        return {
            "enabled": True,
            "trend_layer": {
                "timeframe": "1d",
                "sma_period": 200,
                "require_above_sma": True,
                "require_macd_positive": True,
            },
            "decision_layer": {
                "timeframe": "4h",
                "debate_rounds": 2,
            },
            "execution_layer": {
                "default_timeframe": "15m",
                "rsi_entry_min": 35,
                "rsi_entry_max": 65,
            }
        }

    def test_init_disabled(self):
        """测试禁用状态初始化"""
        from indicators.multi_timeframe_manager import MultiTimeframeManager

        manager = MultiTimeframeManager(self.get_disabled_config())
        assert not manager.enabled
        assert manager.trend_manager is None

    def test_init_enabled(self):
        """测试启用状态初始化"""
        from indicators.multi_timeframe_manager import MultiTimeframeManager

        manager = MultiTimeframeManager(self.get_enabled_config())
        assert manager.enabled
        assert manager.trend_manager is not None
        assert manager.decision_manager is not None
        assert manager.execution_manager is not None

    def test_risk_state_default(self):
        """测试默认风险状态"""
        from indicators.multi_timeframe_manager import MultiTimeframeManager, RiskState

        manager = MultiTimeframeManager(self.get_enabled_config())
        assert manager.get_risk_state() == RiskState.RISK_OFF

    def test_decision_state_default(self):
        """测试默认决策状态"""
        from indicators.multi_timeframe_manager import MultiTimeframeManager, DecisionState

        manager = MultiTimeframeManager(self.get_enabled_config())
        assert manager.get_decision_state() == DecisionState.WAIT

    def test_set_decision_state(self):
        """测试设置决策状态"""
        from indicators.multi_timeframe_manager import MultiTimeframeManager, DecisionState

        manager = MultiTimeframeManager(self.get_enabled_config())
        manager.set_decision_state(DecisionState.ALLOW_LONG, "HIGH")

        assert manager.get_decision_state() == DecisionState.ALLOW_LONG
        assert manager._decision_confidence == "HIGH"

    def test_route_bar_disabled(self):
        """测试禁用时的 bar 路由"""
        from indicators.multi_timeframe_manager import MultiTimeframeManager

        manager = MultiTimeframeManager(self.get_disabled_config())
        mock_bar = Mock()

        result = manager.route_bar(mock_bar)
        assert result == "disabled"

    def test_check_execution_confirmation_in_range(self):
        """测试执行层确认 - RSI 在范围内"""
        from indicators.multi_timeframe_manager import MultiTimeframeManager

        manager = MultiTimeframeManager(self.get_enabled_config())

        # Mock execution_manager
        manager.execution_manager = Mock()
        manager.execution_manager.is_initialized.return_value = True
        manager.execution_manager.get_technical_data.return_value = {'rsi': 50}

        result = manager.check_execution_confirmation(100000)
        assert result['confirmed'] == True
        assert result['rsi'] == 50

    def test_check_execution_confirmation_out_of_range(self):
        """测试执行层确认 - RSI 超出范围"""
        from indicators.multi_timeframe_manager import MultiTimeframeManager

        manager = MultiTimeframeManager(self.get_enabled_config())

        manager.execution_manager = Mock()
        manager.execution_manager.is_initialized.return_value = True
        manager.execution_manager.get_technical_data.return_value = {'rsi': 75}

        result = manager.check_execution_confirmation(100000)
        assert result['confirmed'] == False
        assert result['rsi'] == 75

    def test_get_summary(self):
        """测试获取状态摘要"""
        from indicators.multi_timeframe_manager import MultiTimeframeManager

        manager = MultiTimeframeManager(self.get_enabled_config())
        summary = manager.get_summary()

        assert 'enabled' in summary
        assert 'risk_state' in summary
        assert 'decision_state' in summary
        assert 'layers_initialized' in summary


class TestRiskEvaluation:
    """风险评估测试"""

    def get_config(self):
        return {
            "enabled": True,
            "trend_layer": {
                "sma_period": 200,
                "require_above_sma": True,
                "require_macd_positive": True,
            },
            "decision_layer": {},
            "execution_layer": {},
        }

    def test_risk_on_above_sma_macd_positive(self):
        """测试价格在 SMA 上方且 MACD > 0 时应为 RISK_ON"""
        from indicators.multi_timeframe_manager import MultiTimeframeManager, RiskState

        manager = MultiTimeframeManager(self.get_config())
        manager.trend_manager = Mock()
        manager.trend_manager.is_initialized.return_value = True
        manager.trend_manager.get_technical_data.return_value = {
            'sma_200': 95000,
            'macd': 100,
        }

        result = manager.evaluate_risk_state(100000)
        assert result == RiskState.RISK_ON

    def test_risk_off_below_sma(self):
        """测试价格在 SMA 下方时应为 RISK_OFF"""
        from indicators.multi_timeframe_manager import MultiTimeframeManager, RiskState

        manager = MultiTimeframeManager(self.get_config())
        manager.trend_manager = Mock()
        manager.trend_manager.is_initialized.return_value = True
        manager.trend_manager.get_technical_data.return_value = {
            'sma_200': 105000,
            'macd': 100,
        }

        result = manager.evaluate_risk_state(100000)
        assert result == RiskState.RISK_OFF

    def test_risk_off_macd_negative(self):
        """测试 MACD < 0 时应为 RISK_OFF"""
        from indicators.multi_timeframe_manager import MultiTimeframeManager, RiskState

        manager = MultiTimeframeManager(self.get_config())
        manager.trend_manager = Mock()
        manager.trend_manager.is_initialized.return_value = True
        manager.trend_manager.get_technical_data.return_value = {
            'sma_200': 95000,
            'macd': -50,
        }

        result = manager.evaluate_risk_state(100000)
        assert result == RiskState.RISK_OFF


class TestBackwardCompatibility:
    """向后兼容测试"""

    def test_single_timeframe_mode(self):
        """确保禁用 MTF 时系统行为不变"""
        from indicators.multi_timeframe_manager import MultiTimeframeManager

        config = {"enabled": False}
        manager = MultiTimeframeManager(config)

        assert not manager.enabled
        assert manager.is_all_layers_initialized() == True  # 未启用视为已初始化

        mock_bar = Mock()
        assert manager.route_bar(mock_bar) == "disabled"
```

---

## 6. 实施阶段和优先级

### Phase 1: 基础设施 (优先级: 高)

| 任务 | 文件 | 状态 |
|------|------|------|
| 1.1 添加配置结构 | `configs/base.yaml` | ✅ 已设计 |
| 1.2 创建 MultiTimeframeManager | `indicators/multi_timeframe_manager.py` | ✅ 已设计 |
| 1.3 修改 DeepSeekAIStrategyConfig | `strategy/deepseek_strategy.py` | ✅ 已设计 |

### Phase 2: 策略集成 (优先级: 高)

| 任务 | 文件 | 状态 |
|------|------|------|
| 2.1 修改 main_live.py | `main_live.py` | ✅ 已设计 |
| 2.2 修改 __init__ | `strategy/deepseek_strategy.py` | ✅ 已设计 |
| 2.3 修改 on_start | `strategy/deepseek_strategy.py` | ✅ 已设计 |
| 2.4 修改 on_bar (精确匹配) | `strategy/deepseek_strategy.py` | ✅ 已设计 |
| 2.5 修改 on_timer | `strategy/deepseek_strategy.py` | ✅ 已设计 |

### Phase 3: 诊断和测试 (优先级: 中)

| 任务 | 文件 | 状态 |
|------|------|------|
| 3.1 添加 MTF 诊断函数 | `scripts/diagnose_realtime.py` | ✅ 已设计 |
| 3.2 添加单元测试 | `tests/test_multi_timeframe.py` | ✅ 已设计 |
| 3.3 回归测试验证 | 全部测试文件 | 待实施 |

---

## 7. 审查结论 (合并自 v2.0 审查报告)

### 7.1 已解决的问题

| 原问题 | 解决方案 |
|--------|----------|
| ADX 指标未实现 | 使用 MACD > 0 替代 ADX 判断趋势 |
| on_bar 字符串匹配问题 | 改用 `bar.bar_type == self.xxx_bar_type` 精确匹配 |
| frozen dataclass 不支持 dict | 使用扁平化基本类型字段 |
| ConfigManager 辅助方法不存在 | 直接使用 `get()` 方法访问嵌套配置 |
| SMA_200 未包含在默认周期 | 在 TechnicalIndicatorManager 初始化时指定 |
| 测试无 conftest.py | 使用手动设置方式编写测试 |

### 7.2 剩余风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 多 bar 订阅内存增加 | 系统稳定性 | 限制历史 bar 数量 |
| 时间框架同步问题 | 信号准确性 | 使用 UTC 时间，添加日志 |
| AI 调用次数增加 | 成本和延迟 | 缓存决策结果 |

### 7.3 回滚计划

1. **立即回滚**: 设置 `multi_timeframe.enabled: false`
2. **代码回滚**: `git revert` 到稳定版本
3. **服务恢复**: 重启服务，验证单时间框架模式正常

---

## 8. 附录

### 8.1 参考资料

- [TradingAgents GitHub](https://github.com/TauricResearch/TradingAgents)
- [NautilusTrader 文档](https://nautilustrader.io/docs/)
- [CLAUDE.md 项目规范](/home/user/AItrader/CLAUDE.md)

### 8.2 文件清理记录

v3.0 删除了以下冗余文件 (内容已合并到本文档):

- `docs/MULTI_TIMEFRAME_REVIEW_REPORT.md` - 审查结论已合并到第 7 节

---

*文档更新于 2026-01-26 v3.0*
