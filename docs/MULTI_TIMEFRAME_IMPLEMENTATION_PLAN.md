# 多时间框架实施方案 v1.0

## 文档信息

| 项目 | 值 |
|------|-----|
| 版本 | 1.0 |
| 创建日期 | 2026-01-26 |
| 基于 | TradingAgents 架构 + AItrader 现有系统 |
| 状态 | 设计阶段 |

---

## 1. 架构概述

### 1.1 时间框架设计

基于用户需求和 TradingAgents 架构，采用三层时间框架：

| 层级 | 周期 | 职责 | 更新频率 |
|------|------|------|----------|
| **趋势层** | 1D | Risk-On / Risk-Off 判断 | 每日 1 次 |
| **决策层** | 4H | 允许做多 / 做空 / 观望 | 每 4 小时 |
| **执行层** | 5M / 15M | 精确入场、SL、TP | 每 5-15 分钟 |

### 1.2 决策流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           1D 趋势层 (每日更新)                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  输入: 1D K线数据                                                    │    │
│  │  指标: SMA_200, ATR_14, ADX_14                                      │    │
│  │  输出: RISK_ON / RISK_OFF                                           │    │
│  │                                                                      │    │
│  │  规则:                                                               │    │
│  │  ├─ Price > SMA_200 + ATR正常 + ADX > 20 → RISK_ON (可交易)         │    │
│  │  └─ Price < SMA_200 或 ATR异常 或 ADX < 15 → RISK_OFF (观望)        │    │
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
│                          4H 决策层 (每4小时更新)                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  输入: 4H K线数据 + 1D 趋势状态                                      │    │
│  │  指标: MACD, RSI_14, BB_20, SMA_50                                  │    │
│  │                                                                      │    │
│  │  Phase 1: Bull/Bear 辩论 (TradingAgents 架构)                       │    │
│  │  ├─ 🐂 Bull Agent: 分析 4H 数据中的做多理由                         │    │
│  │  └─ 🐻 Bear Agent: 分析 4H 数据中的做空理由                         │    │
│  │                                                                      │    │
│  │  Phase 2: Judge 决策                                                 │    │
│  │  └─ ⚖️ 基于辩论结果 + 量化规则，决定方向                            │    │
│  │                                                                      │    │
│  │  输出: ALLOW_LONG / ALLOW_SHORT / WAIT                              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                     │                                        │
│          ALLOW_SHORT ───────────────┼──────────── ALLOW_LONG                │
│              │                      │                    │                   │
│              ▼                      ▼                    ▼                   │
│         [等待空信号]            [观望]              [等待多信号]             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      5M/15M 执行层 (每5-15分钟更新)                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  输入: 5M/15M K线数据 + 4H 决策方向                                  │    │
│  │  指标: RSI_14, EMA_10, 支撑/阻力                                    │    │
│  │                                                                      │    │
│  │  Phase 3: Risk Manager 评估 (TradingAgents 架构)                    │    │
│  │  └─ 🛡️ 基于执行层数据，确定:                                       │    │
│  │      ├─ 入场价位 (当前价或限价)                                     │    │
│  │      ├─ 止损价位 (基于支撑/阻力 + ATR)                              │    │
│  │      ├─ 止盈价位 (基于信心级别)                                     │    │
│  │      └─ 仓位大小 (基于信心 + Risk-On 状态)                          │    │
│  │                                                                      │    │
│  │  执行条件检查:                                                       │    │
│  │  ├─ 1D = RISK_ON ✓                                                  │    │
│  │  ├─ 4H = ALLOW_LONG/SHORT ✓                                         │    │
│  │  ├─ 5M/15M RSI 未极端 ✓                                             │    │
│  │  └─ 入场确认信号 ✓                                                  │    │
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

---

## 2. 配置系统改动

### 2.1 新增配置结构 (configs/base.yaml)

```yaml
# =============================================================================
# 多时间框架配置 (Multi-Timeframe Framework)
# =============================================================================
multi_timeframe:
  enabled: true                       # 是否启用多时间框架

  # ---------------------------------------------------------------------------
  # 趋势层配置 (1D)
  # ---------------------------------------------------------------------------
  trend_layer:
    timeframe: "1d"                   # 日线
    bar_type_suffix: "1-DAY-LAST"     # NautilusTrader bar type 后缀

    # Risk-On/Risk-Off 判断规则
    risk_assessment:
      # SMA 过滤
      sma_period: 200                 # 使用 SMA200 判断趋势
      require_above_sma: true         # 价格需在 SMA 上方才能 Risk-On

      # 波动率过滤
      atr_period: 14
      atr_percentile_max: 90          # ATR 百分位 > 90 视为异常波动

      # 趋势强度过滤
      adx_period: 14
      adx_min_for_trend: 20           # ADX > 20 才认为有趋势
      adx_min_for_risk_on: 15         # ADX > 15 才允许 Risk-On

    # 缓存设置 (避免频繁计算)
    cache_ttl_hours: 4                # 趋势状态缓存 4 小时
    update_on_bar_close: true         # 仅在日线收盘时更新

  # ---------------------------------------------------------------------------
  # 决策层配置 (4H)
  # ---------------------------------------------------------------------------
  decision_layer:
    timeframe: "4h"                   # 4小时线
    bar_type_suffix: "4-HOUR-LAST"

    # 指标配置
    indicators:
      macd:
        fast: 12
        slow: 26
        signal: 9
      rsi:
        period: 14
        overbought: 70
        oversold: 30
      bollinger:
        period: 20
        std: 2.0
      sma_periods: [20, 50]

    # Bull/Bear 辩论配置 (继承 TradingAgents)
    debate:
      rounds: 2                       # 辩论轮数
      include_trend_context: true     # 在 prompt 中包含趋势层状态

    # 决策阈值
    decision:
      min_confirmations_for_signal: 3 # 至少 3 个确认才能产生信号
      require_trend_alignment: true   # 决策需与趋势层一致

  # ---------------------------------------------------------------------------
  # 执行层配置 (5M / 15M)
  # ---------------------------------------------------------------------------
  execution_layer:
    default_timeframe: "15m"          # 默认使用 15M
    high_volatility_timeframe: "5m"   # 高波动时切换到 5M
    bar_type_suffix: "15-MINUTE-LAST"

    # 切换到 5M 的条件
    switch_to_5m_conditions:
      atr_percentile_above: 80        # ATR 百分位 > 80
      bb_width_percentile_above: 75   # BB 宽度百分位 > 75

    # 指标配置
    indicators:
      rsi:
        period: 14
        entry_confirmation_range: [35, 65]  # RSI 在此范围内才确认入场
      ema:
        period: 10                    # 快速 EMA 用于入场确认
      support_resistance:
        lookback: 20                  # 支撑阻力回溯期

    # 入场确认规则
    entry_confirmation:
      require_rsi_in_range: true      # RSI 需在合理范围
      require_price_near_level: true  # 价格需接近支撑/阻力
      price_level_threshold_pct: 0.5  # 距离支撑/阻力 0.5% 内

    # 止损止盈配置 (继承现有配置，基于执行层数据计算)
    sl_tp:
      sl_based_on: "execution_layer"  # SL 基于执行层支撑/阻力
      tp_based_on: "confidence"       # TP 基于信心级别
      min_sl_distance_pct: 0.01       # 最小 SL 距离 1%
      atr_multiplier_for_sl: 1.5      # SL 距离 = 1.5 * ATR

# ---------------------------------------------------------------------------
# 定时器配置 (更新以支持多时间框架)
# ---------------------------------------------------------------------------
timing:
  # 主定时器 (执行层)
  timer_interval_sec: 900             # 15 分钟 (执行层周期)

  # 趋势层更新时间 (可选，默认在日线收盘时自动更新)
  trend_layer_update_times_utc:
    - "00:00"                         # UTC 00:00 (日线收盘后)

  # 决策层定时器
  decision_layer_timer_sec: 14400     # 4 小时 (决策层周期)
```

### 2.2 向后兼容配置

为确保现有系统不受影响，当 `multi_timeframe.enabled: false` 时，系统行为与当前版本完全一致：

```yaml
multi_timeframe:
  enabled: false                      # 禁用多时间框架

trading:
  timeframe: "15m"                    # 使用单一时间框架 (现有行为)
```

### 2.3 环境特定配置

**configs/production.yaml**:
```yaml
multi_timeframe:
  enabled: true
  execution_layer:
    default_timeframe: "15m"          # 生产环境使用 15M
```

**configs/development.yaml**:
```yaml
multi_timeframe:
  enabled: true
  execution_layer:
    default_timeframe: "5m"           # 开发环境使用 5M (快速测试)
  decision_layer:
    timeframe: "1h"                   # 开发环境使用 1H 代替 4H
  trend_layer:
    timeframe: "4h"                   # 开发环境使用 4H 代替 1D
```

---

## 3. 核心模块改动

### 3.1 新增: MultiTimeframeManager

创建新文件 `indicators/multi_timeframe_manager.py`:

```python
"""
Multi-Timeframe Indicator Manager

管理多个时间框架的技术指标，提供跨周期分析能力。
遵循 TradingAgents 架构，支持趋势层/决策层/执行层分离。
"""

from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime, timedelta
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
    多时间框架管理器

    管理三层时间框架:
    - trend_layer (1D): Risk-On/Risk-Off 判断
    - decision_layer (4H): 方向决策
    - execution_layer (5M/15M): 入场执行
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化多时间框架管理器

        Parameters
        ----------
        config : Dict
            多时间框架配置 (从 ConfigManager 获取)
        """
        self.config = config
        self.enabled = config.get('enabled', False)

        if not self.enabled:
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

        # 初始化各层管理器
        self._init_managers()

    def _init_managers(self):
        """初始化各层技术指标管理器"""
        # 趋势层 (1D)
        trend_config = self.config.get('trend_layer', {})
        self.trend_manager = TechnicalIndicatorManager(
            sma_periods=[trend_config.get('risk_assessment', {}).get('sma_period', 200)],
            rsi_period=14,  # 趋势层不使用 RSI，但需要初始化
            # ADX 需要单独实现或使用现有指标
        )

        # 决策层 (4H)
        decision_config = self.config.get('decision_layer', {})
        indicators = decision_config.get('indicators', {})
        self.decision_manager = TechnicalIndicatorManager(
            sma_periods=indicators.get('sma_periods', [20, 50]),
            rsi_period=indicators.get('rsi', {}).get('period', 14),
            macd_fast=indicators.get('macd', {}).get('fast', 12),
            macd_slow=indicators.get('macd', {}).get('slow', 26),
            bb_period=indicators.get('bollinger', {}).get('period', 20),
            bb_std=indicators.get('bollinger', {}).get('std', 2.0),
        )

        # 执行层 (5M/15M)
        exec_config = self.config.get('execution_layer', {})
        exec_indicators = exec_config.get('indicators', {})
        self.execution_manager = TechnicalIndicatorManager(
            sma_periods=[5, 20],  # 执行层使用短期 SMA
            ema_periods=[exec_indicators.get('ema', {}).get('period', 10)],
            rsi_period=exec_indicators.get('rsi', {}).get('period', 14),
            support_resistance_lookback=exec_indicators.get('support_resistance', {}).get('lookback', 20),
        )

    def update_trend_bar(self, bar: Bar):
        """更新趋势层 K 线数据"""
        if self.trend_manager:
            self.trend_manager.update(bar)

    def update_decision_bar(self, bar: Bar):
        """更新决策层 K 线数据"""
        if self.decision_manager:
            self.decision_manager.update(bar)

    def update_execution_bar(self, bar: Bar):
        """更新执行层 K 线数据"""
        if self.execution_manager:
            self.execution_manager.update(bar)

    def evaluate_risk_state(self, current_price: float) -> RiskState:
        """
        评估趋势层风险状态 (Risk-On / Risk-Off)

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
            return RiskState.RISK_OFF

        risk_config = self.config.get('trend_layer', {}).get('risk_assessment', {})

        # 获取技术数据
        tech_data = self.trend_manager.get_technical_data(current_price)

        # 规则 1: 价格在 SMA200 上方
        sma_period = risk_config.get('sma_period', 200)
        sma_value = tech_data.get(f'sma_{sma_period}', current_price)
        price_above_sma = current_price > sma_value

        # 规则 2: ADX > 阈值 (表示有趋势)
        # 注意: 需要实现 ADX 指标，暂时使用 RSI 作为替代
        adx_min = risk_config.get('adx_min_for_risk_on', 15)
        # TODO: 实现 ADX 指标
        has_trend = True  # 暂时默认为 True

        # 规则 3: ATR 未异常
        # TODO: 实现 ATR 百分位计算
        atr_normal = True  # 暂时默认为 True

        # 综合判断
        if price_above_sma and has_trend and atr_normal:
            self._risk_state = RiskState.RISK_ON
        else:
            self._risk_state = RiskState.RISK_OFF

        self._risk_state_updated = datetime.utcnow()
        return self._risk_state

    def get_risk_state(self) -> RiskState:
        """获取当前风险状态 (带缓存)"""
        return self._risk_state

    def get_decision_state(self) -> DecisionState:
        """获取当前决策状态"""
        return self._decision_state

    def set_decision_state(self, state: DecisionState, confidence: str = "MEDIUM"):
        """设置决策状态 (由 MultiAgentAnalyzer 调用)"""
        self._decision_state = state
        self._decision_confidence = confidence
        self._decision_updated = datetime.utcnow()

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
            return manager.get_technical_data(current_price)
        return {}

    def is_all_layers_initialized(self) -> bool:
        """检查所有层是否都已初始化"""
        if not self.enabled:
            return True  # 未启用时视为已初始化

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
            }
        }
```

### 3.2 改动: DeepSeekAIStrategy (strategy/deepseek_strategy.py)

#### 3.2.1 新增属性

```python
# 在 __init__ 中添加:

# Multi-Timeframe Manager
self.mtf_enabled = config.multi_timeframe_enabled  # 新增配置项
if self.mtf_enabled:
    from indicators.multi_timeframe_manager import MultiTimeframeManager
    self.mtf_manager = MultiTimeframeManager(config.multi_timeframe_config)

    # 订阅多个时间框架的 bar types
    self.trend_bar_type = BarType.from_str(
        f"{config.instrument_id.split('.')[0]}.BINANCE-1-DAY-LAST-EXTERNAL"
    )
    self.decision_bar_type = BarType.from_str(
        f"{config.instrument_id.split('.')[0]}.BINANCE-4-HOUR-LAST-EXTERNAL"
    )
    self.execution_bar_type = BarType.from_str(
        f"{config.instrument_id.split('.')[0]}.BINANCE-15-MINUTE-LAST-EXTERNAL"
    )
else:
    self.mtf_manager = None
```

#### 3.2.2 修改 on_start()

```python
def on_start(self):
    # ... 现有代码 ...

    if self.mtf_enabled:
        # 订阅多个时间框架
        self.subscribe_bars(self.trend_bar_type)
        self.subscribe_bars(self.decision_bar_type)
        self.subscribe_bars(self.execution_bar_type)
        self.log.info(f"Multi-Timeframe enabled: subscribed to 1D, 4H, 15M bars")

        # 预取各层历史数据
        self._prefetch_multi_timeframe_bars()
    else:
        # 现有单时间框架逻辑
        self.subscribe_bars(self.bar_type)
```

#### 3.2.3 修改 on_bar()

```python
def on_bar(self, bar: Bar):
    # 根据 bar type 路由到对应的管理器
    if self.mtf_enabled and self.mtf_manager:
        bar_type_str = str(bar.bar_type)

        if "1-DAY" in bar_type_str:
            self.mtf_manager.update_trend_bar(bar)
            # 触发趋势层评估
            self._evaluate_trend_layer()

        elif "4-HOUR" in bar_type_str:
            self.mtf_manager.update_decision_bar(bar)
            # 触发决策层分析
            self._schedule_decision_layer_analysis()

        elif "15-MINUTE" in bar_type_str or "5-MINUTE" in bar_type_str:
            self.mtf_manager.update_execution_bar(bar)
            # 更新缓存价格
            with self._state_lock:
                self._cached_current_price = float(bar.close)
    else:
        # 现有单时间框架逻辑
        self.indicator_manager.update(bar)
        with self._state_lock:
            self._cached_current_price = float(bar.close)
```

#### 3.2.4 新增方法

```python
def _evaluate_trend_layer(self):
    """评估趋势层 Risk-On/Risk-Off 状态"""
    if not self.mtf_manager:
        return

    current_price = self._cached_current_price
    risk_state = self.mtf_manager.evaluate_risk_state(current_price)

    self.log.info(f"📊 趋势层评估: {risk_state.value}")

    if risk_state == RiskState.RISK_OFF:
        self.log.info("⚠️ RISK_OFF - 暂停交易，等待市场环境改善")
        # 可选: 发送 Telegram 通知
        if self.telegram_bot:
            self.telegram_bot.send_message_sync(
                f"⚠️ 趋势层信号: RISK_OFF\n"
                f"当前价格: ${current_price:,.2f}\n"
                f"暂停新开仓，等待市场环境改善"
            )


def _schedule_decision_layer_analysis(self):
    """调度决策层分析 (4H 周期)"""
    # 检查是否需要运行分析 (避免重复)
    # 实际分析在 on_timer 中执行
    pass


def on_timer(self, event):
    """定时分析 (改造为多时间框架版本)"""
    if not self.mtf_enabled:
        # 现有单时间框架逻辑
        return self._on_timer_single_timeframe(event)

    return self._on_timer_multi_timeframe(event)


def _on_timer_multi_timeframe(self, event):
    """多时间框架定时分析"""
    self.log.info("=" * 60)
    self.log.info("Running Multi-Timeframe Analysis...")

    # Step 1: 检查趋势层状态
    risk_state = self.mtf_manager.get_risk_state()
    if risk_state == RiskState.RISK_OFF:
        self.log.info("⚠️ RISK_OFF - 跳过交易分析")
        return

    # Step 2: 获取决策层技术数据
    current_price = self._cached_current_price
    decision_tech_data = self.mtf_manager.get_technical_data_for_layer("decision", current_price)

    # Step 3: 运行 MultiAgent 分析 (基于 4H 数据)
    # 在 prompt 中包含趋势层状态
    decision_tech_data['trend_layer_state'] = risk_state.value

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
        self._execute_with_confirmation(multi_agent_result)


def _execute_with_confirmation(self, decision: Dict[str, Any]):
    """执行层入场确认"""
    # 获取执行层技术数据
    current_price = self._cached_current_price
    exec_tech_data = self.mtf_manager.get_technical_data_for_layer("execution", current_price)

    # 检查入场确认条件
    rsi = exec_tech_data.get('rsi', 50)
    exec_config = self.config.multi_timeframe_config.get('execution_layer', {})
    rsi_range = exec_config.get('indicators', {}).get('rsi', {}).get('entry_confirmation_range', [35, 65])

    if rsi_range[0] <= rsi <= rsi_range[1]:
        self.log.info(f"✅ 执行层确认: RSI={rsi:.1f} 在合理范围内")
        self._execute_trade(decision)
    else:
        self.log.info(f"⏳ 执行层等待: RSI={rsi:.1f} 不在范围 {rsi_range}")
        # 保留信号，等待下一个周期确认
```

### 3.3 改动: MultiAgentAnalyzer (agents/multi_agent_analyzer.py)

#### 3.3.1 修改 _format_technical_report()

添加多时间框架上下文：

```python
def _format_technical_report(self, data: Dict[str, Any]) -> str:
    """Format technical data for prompts."""
    if not data:
        return "Technical data not available"

    # 现有格式化逻辑...
    base_report = f"""
Price: ${safe_get('price'):,.2f}
24h Change: {safe_get('price_change'):+.2f}%
...
"""

    # 新增: 多时间框架上下文
    trend_state = data.get('trend_layer_state', 'UNKNOWN')
    if trend_state != 'UNKNOWN':
        base_report = f"""
=== MULTI-TIMEFRAME CONTEXT ===
Trend Layer (1D): {trend_state}
Decision Layer (4H): Current analysis timeframe
Execution Layer: 15M (for entry timing)

{base_report}
"""

    return base_report
```

#### 3.3.2 修改 Bull/Bear Prompts

在辩论 prompt 中包含时间框架上下文：

```python
def _get_bull_argument(self, ...):
    prompt = f"""You are a Bull Analyst advocating for LONG position on {symbol}.

=== TIMEFRAME CONTEXT ===
You are analyzing 4H (4-hour) chart data.
The 1D (daily) trend layer shows: {technical_report.split('Trend Layer (1D):')[1].split('\n')[0] if 'Trend Layer' in technical_report else 'UNKNOWN'}

Your analysis should consider the higher timeframe context.
If the daily trend is RISK_OFF, be more conservative in your bullish arguments.
If the daily trend is RISK_ON, you can be more confident in bullish setups.

=== YOUR TASK ===
Build a strong, evidence-based case for going LONG on the 4H timeframe.
...
"""
```

---

## 4. 诊断工具适配

### 4.1 diagnose_realtime.py 改动

```python
# 添加多时间框架诊断

def diagnose_multi_timeframe(config_manager: ConfigManager):
    """诊断多时间框架配置和状态"""
    print("\n" + "=" * 60)
    print("🕐 多时间框架诊断")
    print("=" * 60)

    mtf_config = config_manager.get('multi_timeframe', default={})
    enabled = mtf_config.get('enabled', False)

    print(f"多时间框架启用状态: {'✅ 已启用' if enabled else '❌ 未启用'}")

    if not enabled:
        print("跳过多时间框架诊断 (未启用)")
        return

    # 检查趋势层配置
    trend_config = mtf_config.get('trend_layer', {})
    print(f"\n趋势层 (1D):")
    print(f"  - 时间框架: {trend_config.get('timeframe', '1d')}")
    print(f"  - SMA 周期: {trend_config.get('risk_assessment', {}).get('sma_period', 200)}")
    print(f"  - ADX 阈值: {trend_config.get('risk_assessment', {}).get('adx_min_for_risk_on', 15)}")

    # 检查决策层配置
    decision_config = mtf_config.get('decision_layer', {})
    print(f"\n决策层 (4H):")
    print(f"  - 时间框架: {decision_config.get('timeframe', '4h')}")
    print(f"  - 辩论轮数: {decision_config.get('debate', {}).get('rounds', 2)}")

    # 检查执行层配置
    exec_config = mtf_config.get('execution_layer', {})
    print(f"\n执行层 (5M/15M):")
    print(f"  - 默认周期: {exec_config.get('default_timeframe', '15m')}")
    print(f"  - 高波动周期: {exec_config.get('high_volatility_timeframe', '5m')}")

    # 获取实时数据验证
    print("\n📊 实时数据验证:")
    # TODO: 调用 Binance API 获取各时间框架数据
```

### 4.2 smart_commit_analyzer.py 新增规则

```json
{
  "id": "mtf_layer_routing",
  "type": "pattern_required",
  "file_pattern": "strategy/deepseek_strategy.py",
  "pattern": "update_trend_bar|update_decision_bar|update_execution_bar",
  "description": "多时间框架必须有正确的 bar 路由逻辑",
  "severity": "critical"
},
{
  "id": "mtf_risk_state_check",
  "type": "pattern_required",
  "file_pattern": "strategy/deepseek_strategy.py",
  "pattern": "RISK_OFF|RISK_ON",
  "description": "多时间框架必须检查趋势层风险状态",
  "severity": "warning"
}
```

---

## 5. 技能和工作流适配

### 5.1 更新 .claude/skills/diagnose/SKILL.md

```markdown
## 多时间框架诊断

### 检查多时间框架状态
```bash
python3 scripts/diagnose_realtime.py --mtf
```

### 预期输出 (多时间框架启用时)
```
🕐 多时间框架诊断
==================================================
多时间框架启用状态: ✅ 已启用

趋势层 (1D):
  - 当前状态: RISK_ON
  - SMA_200: $95,000
  - 价格位置: 在 SMA 上方 ✅

决策层 (4H):
  - 当前状态: ALLOW_LONG
  - 信心级别: HIGH
  - MACD: 看多 ✅
  - RSI: 55 (中性)

执行层 (15M):
  - RSI: 48 (在入场范围内 ✅)
  - 支撑位: $104,500
  - 阻力位: $106,200
```
```

### 5.2 新增 .claude/skills/multi-timeframe/SKILL.md

```markdown
---
name: multi-timeframe
description: |
  Multi-Timeframe Analysis for AItrader. 多时间框架分析。

  Use this skill when:
  - Understanding the three-layer timeframe system (了解三层时间框架)
  - Debugging timeframe conflicts (调试时间框架冲突)
  - Checking Risk-On/Risk-Off status (检查风险状态)
---

# Multi-Timeframe Analysis

## 三层架构

| 层级 | 周期 | 职责 |
|------|------|------|
| 趋势层 | 1D | Risk-On / Risk-Off |
| 决策层 | 4H | Bull/Bear 辩论 |
| 执行层 | 15M | 入场确认 |

## 常用命令

### 检查多时间框架状态
```bash
python3 scripts/diagnose_realtime.py --mtf
```

### 查看各层指标值
```bash
python3 -c "
from utils.config_manager import ConfigManager
from indicators.multi_timeframe_manager import MultiTimeframeManager

config = ConfigManager(env='production').load()
mtf = MultiTimeframeManager(config.get('multi_timeframe', {}))
print(mtf.get_summary())
"
```

## 故障排除

### 问题: 趋势层一直是 RISK_OFF

检查:
1. 1D K 线数据是否正确加载
2. SMA_200 值是否合理
3. 价格是否长期在 SMA 下方

### 问题: 决策层信号不一致

检查:
1. 4H K 线数据更新频率
2. Bull/Bear 辩论 prompt 是否包含趋势上下文
```

---

## 6. 测试用例适配

### 6.1 新增测试文件 tests/test_multi_timeframe.py

```python
"""
Multi-Timeframe Manager Tests
"""
import pytest
from unittest.mock import Mock, patch
from indicators.multi_timeframe_manager import (
    MultiTimeframeManager,
    RiskState,
    DecisionState,
)


class TestMultiTimeframeManager:
    """多时间框架管理器测试"""

    def test_init_disabled(self):
        """测试禁用状态初始化"""
        config = {"enabled": False}
        manager = MultiTimeframeManager(config)
        assert not manager.enabled
        assert manager.trend_manager is None

    def test_init_enabled(self):
        """测试启用状态初始化"""
        config = {
            "enabled": True,
            "trend_layer": {"risk_assessment": {"sma_period": 200}},
            "decision_layer": {"indicators": {"sma_periods": [20, 50]}},
            "execution_layer": {"indicators": {"rsi": {"period": 14}}},
        }
        manager = MultiTimeframeManager(config)
        assert manager.enabled
        assert manager.trend_manager is not None
        assert manager.decision_manager is not None
        assert manager.execution_manager is not None

    def test_risk_state_default(self):
        """测试默认风险状态"""
        config = {"enabled": True, "trend_layer": {}, "decision_layer": {}, "execution_layer": {}}
        manager = MultiTimeframeManager(config)
        assert manager.get_risk_state() == RiskState.RISK_OFF

    def test_decision_state_default(self):
        """测试默认决策状态"""
        config = {"enabled": True, "trend_layer": {}, "decision_layer": {}, "execution_layer": {}}
        manager = MultiTimeframeManager(config)
        assert manager.get_decision_state() == DecisionState.WAIT

    def test_set_decision_state(self):
        """测试设置决策状态"""
        config = {"enabled": True, "trend_layer": {}, "decision_layer": {}, "execution_layer": {}}
        manager = MultiTimeframeManager(config)

        manager.set_decision_state(DecisionState.ALLOW_LONG, "HIGH")
        assert manager.get_decision_state() == DecisionState.ALLOW_LONG
        assert manager._decision_confidence == "HIGH"


class TestRiskEvaluation:
    """风险评估测试"""

    def test_risk_on_above_sma(self):
        """测试价格在 SMA 上方时应为 RISK_ON"""
        # TODO: 需要 mock indicator manager
        pass

    def test_risk_off_below_sma(self):
        """测试价格在 SMA 下方时应为 RISK_OFF"""
        # TODO: 需要 mock indicator manager
        pass
```

### 6.2 更新现有测试

确保现有测试在 `multi_timeframe.enabled: false` 时仍然通过：

```python
# tests/conftest.py

@pytest.fixture
def single_timeframe_config():
    """单时间框架配置 (现有行为)"""
    return {
        "multi_timeframe": {"enabled": False},
        "trading": {"timeframe": "15m"},
        # ... 其他配置
    }

@pytest.fixture
def multi_timeframe_config():
    """多时间框架配置"""
    return {
        "multi_timeframe": {
            "enabled": True,
            "trend_layer": {...},
            "decision_layer": {...},
            "execution_layer": {...},
        },
    }
```

---

## 7. 实施阶段和优先级

### Phase 1: 基础设施 (优先级: 高)

**目标**: 搭建多时间框架基础架构，不影响现有功能

| 任务 | 文件 | 复杂度 | 风险 |
|------|------|--------|------|
| 1.1 添加配置结构 | `configs/base.yaml` | 低 | 低 |
| 1.2 创建 MultiTimeframeManager | `indicators/multi_timeframe_manager.py` | 中 | 低 |
| 1.3 添加 ADX 指标支持 | `indicators/technical_manager.py` | 中 | 低 |
| 1.4 更新 ConfigManager | `utils/config_manager.py` | 低 | 低 |

**验收标准**:
- `multi_timeframe.enabled: false` 时系统行为不变
- 新配置可以正确加载
- MultiTimeframeManager 可以实例化

### Phase 2: 策略集成 (优先级: 高)

**目标**: 将多时间框架集成到主策略

| 任务 | 文件 | 复杂度 | 风险 |
|------|------|--------|------|
| 2.1 添加多 bar 订阅 | `strategy/deepseek_strategy.py` | 中 | 中 |
| 2.2 实现 bar 路由 | `strategy/deepseek_strategy.py` | 中 | 中 |
| 2.3 实现趋势层评估 | `strategy/deepseek_strategy.py` | 中 | 低 |
| 2.4 修改 on_timer 逻辑 | `strategy/deepseek_strategy.py` | 高 | 高 |
| 2.5 实现执行层确认 | `strategy/deepseek_strategy.py` | 中 | 中 |

**验收标准**:
- 能够订阅 1D/4H/15M 三个时间框架
- bar 数据正确路由到对应管理器
- 趋势层 RISK_OFF 时停止交易

### Phase 3: AI 集成 (优先级: 中)

**目标**: 更新 MultiAgentAnalyzer 以支持多时间框架上下文

| 任务 | 文件 | 复杂度 | 风险 |
|------|------|--------|------|
| 3.1 更新 technical report 格式 | `agents/multi_agent_analyzer.py` | 低 | 低 |
| 3.2 修改 Bull/Bear prompts | `agents/multi_agent_analyzer.py` | 中 | 低 |
| 3.3 修改 Judge prompt | `agents/multi_agent_analyzer.py` | 中 | 低 |
| 3.4 测试 AI 输出质量 | 手动测试 | - | - |

**验收标准**:
- AI 能够理解多时间框架上下文
- 辩论结果考虑趋势层状态
- HOLD 比例不显著增加

### Phase 4: 诊断和工具 (优先级: 中)

**目标**: 更新诊断工具和技能文档

| 任务 | 文件 | 复杂度 | 风险 |
|------|------|--------|------|
| 4.1 添加 MTF 诊断 | `scripts/diagnose_realtime.py` | 中 | 低 |
| 4.2 添加回归规则 | `configs/auto_generated_rules.json` | 低 | 低 |
| 4.3 更新技能文档 | `.claude/skills/*/SKILL.md` | 低 | 低 |
| 4.4 更新 CLAUDE.md | `CLAUDE.md` | 低 | 低 |

**验收标准**:
- `diagnose_realtime.py --mtf` 正常工作
- 新代码通过 smart_commit_analyzer.py 检查

### Phase 5: 测试和验证 (优先级: 高)

**目标**: 全面测试确保稳定性

| 任务 | 文件 | 复杂度 | 风险 |
|------|------|--------|------|
| 5.1 添加单元测试 | `tests/test_multi_timeframe.py` | 中 | 低 |
| 5.2 添加集成测试 | `tests/test_integration_mtf.py` | 高 | 低 |
| 5.3 回归测试 | 全部测试文件 | - | - |
| 5.4 生产环境验证 | 服务器部署 | - | 中 |

**验收标准**:
- 所有新测试通过
- 现有测试不受影响
- 生产环境运行稳定

---

## 8. 风险评估和缓解措施

### 8.1 高风险项

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 多 bar 订阅导致内存增加 | 系统稳定性 | 限制历史 bar 数量，监控内存使用 |
| on_timer 逻辑复杂化 | 代码维护 | 充分注释，模块化设计 |
| AI 调用次数增加 | 成本和延迟 | 缓存决策结果，优化 prompt |

### 8.2 中风险项

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 时间框架同步问题 | 信号准确性 | 使用 UTC 时间，添加日志 |
| 配置复杂度增加 | 用户体验 | 提供合理默认值，详细文档 |
| 测试覆盖不足 | 回归问题 | 强制 90% 测试覆盖率 |

### 8.3 回滚计划

如果多时间框架功能导致问题：

1. **立即回滚**: 设置 `multi_timeframe.enabled: false`
2. **代码回滚**: `git revert` 到稳定版本
3. **服务恢复**: 重启服务，验证单时间框架模式正常

---

## 9. 附录

### 9.1 参考资料

- [TradingAgents GitHub](https://github.com/TauricResearch/TradingAgents)
- [NautilusTrader 文档](https://nautilustrader.io/docs/)
- [CLAUDE.md 项目规范](/home/user/AItrader/CLAUDE.md)

### 9.2 配置示例

完整的多时间框架配置示例见 Section 2.1。

### 9.3 代码模板

核心代码模板见 Section 3。
