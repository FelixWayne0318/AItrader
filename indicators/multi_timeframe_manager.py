"""
Multi-Timeframe Indicator Manager v3.0

管理多个时间框架的技术指标，提供跨周期分析能力。

v3.0 更新:
- 移除对不存在的 ConfigManager 辅助方法的依赖
- 使用 MACD 替代 ADX (ADX 未在 TechnicalIndicatorManager 实现)
- 添加 SMA_200 支持 (需要在 TechnicalIndicatorManager 初始化时指定)

v3.2.8 更新:
- 从文档转为实际可执行文件
- 添加线程安全注释
"""

from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime, timezone
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
            # 初始化为 None 以避免属性访问错误
            self.trend_manager = None
            self.decision_manager = None
            self.execution_manager = None
            self._risk_state = RiskState.RISK_OFF
            self._decision_state = DecisionState.WAIT
            self._decision_confidence = "LOW"
            self._risk_state_updated = None
            self._decision_updated = None
            self._last_trend_price = 0.0
            self._last_decision_price = 0.0
            self._last_execution_price = 0.0
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
        """
        初始化各层技术指标管理器

        v3.2.7 修正: 必须传递所有必需参数，确保指标正确初始化
        v3.2.10 修正: 从配置读取参数，移除硬编码
        TechnicalIndicatorManager 参数参考 indicators/technical_manager.py:29-40
        """
        trend_config = self.config.get('trend_layer', {})
        decision_config = self.config.get('decision_layer', {})
        exec_config = self.config.get('execution_layer', {})

        # 全局默认指标参数 (从 configs/base.yaml indicators 部分读取)
        global_indicators = self.config.get('global_indicators', {})
        default_ema_periods = global_indicators.get('ema_periods', [12, 26])
        default_rsi_period = global_indicators.get('rsi_period', 14)
        default_macd_fast = global_indicators.get('macd_fast', 12)
        default_macd_slow = global_indicators.get('macd_slow', 26)
        default_macd_signal = global_indicators.get('macd_signal', 9)
        default_bb_period = global_indicators.get('bb_period', 20)
        default_bb_std = global_indicators.get('bb_std', 2.0)
        default_volume_ma_period = global_indicators.get('volume_ma_period', 20)
        default_support_resistance_lookback = global_indicators.get('support_resistance_lookback', 20)

        # ========================================
        # 趋势层 (1D) - 需要 SMA_200 用于趋势判断
        # 关键: SMA_200 需要至少 200 根 bar 才能计算
        # ========================================
        sma_period = trend_config.get('sma_period', 200)
        self.trend_manager = TechnicalIndicatorManager(
            sma_periods=[sma_period],      # SMA_200 用于趋势判断
            ema_periods=default_ema_periods,
            rsi_period=default_rsi_period,
            macd_fast=default_macd_fast,
            macd_slow=default_macd_slow,
            macd_signal=default_macd_signal,
            bb_period=default_bb_period,
            bb_std=default_bb_std,
            volume_ma_period=default_volume_ma_period,
            support_resistance_lookback=default_support_resistance_lookback,
        )
        self.logger.debug(f"趋势层管理器初始化: SMA_{sma_period}")

        # ========================================
        # 决策层 (4H) - Bull/Bear 辩论使用的指标
        # 从 decision_layer.indicators 读取配置
        # ========================================
        decision_indicators = decision_config.get('indicators', {})
        self.decision_manager = TechnicalIndicatorManager(
            sma_periods=decision_indicators.get('sma_periods', [20, 50]),
            ema_periods=default_ema_periods,
            rsi_period=decision_indicators.get('rsi_period', default_rsi_period),
            macd_fast=decision_indicators.get('macd_fast', default_macd_fast),
            macd_slow=decision_indicators.get('macd_slow', default_macd_slow),
            macd_signal=default_macd_signal,
            bb_period=decision_indicators.get('bb_period', default_bb_period),
            bb_std=decision_indicators.get('bb_std', default_bb_std),
            volume_ma_period=default_volume_ma_period,
            support_resistance_lookback=default_support_resistance_lookback,
        )
        self.logger.debug("决策层管理器初始化")

        # ========================================
        # 执行层 (5M/15M) - 入场确认指标
        # 从 execution_layer.indicators 读取配置
        # ========================================
        exec_indicators = exec_config.get('indicators', {})
        self.execution_manager = TechnicalIndicatorManager(
            sma_periods=exec_indicators.get('sma_periods', [5, 20]),
            ema_periods=exec_indicators.get('ema_periods', [10, 20]),
            rsi_period=exec_indicators.get('rsi_period', default_rsi_period),
            macd_fast=default_macd_fast,
            macd_slow=default_macd_slow,
            macd_signal=default_macd_signal,
            bb_period=default_bb_period,
            bb_std=default_bb_std,
            volume_ma_period=default_volume_ma_period,
            support_resistance_lookback=exec_indicators.get('support_resistance_lookback', default_support_resistance_lookback),
        )
        self.logger.debug("执行层管理器初始化")

    def is_initialized(self, layer: str = None) -> bool:
        """
        v3.2.7 新增: 检查指标管理器是否已初始化

        Parameters
        ----------
        layer : str, optional
            指定层级 ("trend"/"decision"/"execution")，None 检查全部

        Returns
        -------
        bool
            是否所有指定层级都已初始化 (有足够的 bar 数据)
        """
        if not self.enabled:
            return False

        min_bars = {
            'trend': 200,      # SMA_200 需要 200 根
            'decision': 50,    # SMA_50 需要 50 根
            'execution': 20,   # RSI_14 + EMA_10 需要 ~20 根
        }

        managers = {
            'trend': self.trend_manager,
            'decision': self.decision_manager,
            'execution': self.execution_manager,
        }

        if layer:
            if layer not in managers:
                return False
            mgr = managers[layer]
            if mgr is None:
                return False
            bars_count = len(mgr.recent_bars) if hasattr(mgr, 'recent_bars') else 0
            return bars_count >= min_bars.get(layer, 0)

        # 检查全部
        for name, mgr in managers.items():
            if mgr is None:
                return False
            bars_count = len(mgr.recent_bars) if hasattr(mgr, 'recent_bars') else 0
            if bars_count < min_bars.get(name, 0):
                self.logger.debug(f"{name} 层未初始化: {bars_count}/{min_bars[name]} bars")
                return False

        return True

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
            if self.trend_manager:
                self.trend_manager.update(bar)
            self._last_trend_price = float(bar.close)
            self.logger.debug(f"[1D] 趋势层 bar 更新: close={bar.close}")
            return "trend"

        elif self.decision_bar_type and bar.bar_type == self.decision_bar_type:
            if self.decision_manager:
                self.decision_manager.update(bar)
            self._last_decision_price = float(bar.close)
            self.logger.debug(f"[4H] 决策层 bar 更新: close={bar.close}")
            return "decision"

        elif self.execution_bar_type and bar.bar_type == self.execution_bar_type:
            if self.execution_manager:
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

        self._risk_state_updated = datetime.now(timezone.utc)

        self.logger.info(
            f"[1D] 趋势层评估: {self._risk_state.value} "
            f"(price={current_price:.2f}, SMA_{sma_period}={sma_value:.2f}, MACD={macd_value:.2f})"
        )

        return self._risk_state

    def get_risk_state(self) -> RiskState:
        """获取当前风险状态 (带缓存)"""
        return self._risk_state

    def evaluate_directional_permissions(self, current_price: float) -> Dict[str, Any]:
        """
        评估方向性权限 (替代二元 RISK_ON/OFF 开关)

        符合 TradingAgents 设计意图：
        - 本地提供市场特征 (SMA, MACD)
        - AI 负责决策交易方向
        - 本地仅作为方向性建议，不强制覆盖 AI

        Parameters
        ----------
        current_price : float
            当前价格

        Returns
        -------
        Dict[str, Any]
            {
                "allow_long": bool,      # 是否允许做多
                "allow_short": bool,     # 是否允许做空
                "regime": str,           # 市场状态 (BULL/BEAR/SIDEWAYS)
                "position_multiplier": float,  # 仓位乘数 (0.5-1.5)
                "reason": str            # 判断理由
            }
        """
        if not self.trend_manager or not self.trend_manager.is_initialized():
            self.logger.warning("趋势层未初始化，返回保守权限")
            return {
                "allow_long": False,
                "allow_short": False,
                "regime": "UNKNOWN",
                "position_multiplier": 0.0,
                "reason": "趋势层数据不足"
            }

        trend_config = self.config.get('trend_layer', {})
        tech_data = self.trend_manager.get_technical_data(current_price)

        # 获取技术指标
        sma_period = trend_config.get('sma_period', 200)
        sma_value = tech_data.get(f'sma_{sma_period}', current_price)
        macd_value = tech_data.get('macd', 0)

        price_above_sma = current_price > sma_value
        macd_positive = macd_value > 0

        # 方向性权限判断
        if price_above_sma and macd_positive:
            # 牛市：价格在 SMA 上方，MACD 为正
            permissions = {
                "allow_long": True,
                "allow_short": True,  # 允许短线做空
                "regime": "BULL",
                "position_multiplier": 1.2,  # 牛市增加仓位
                "reason": f"牛市 (价格 {current_price:.2f} > SMA{sma_period} {sma_value:.2f}, MACD {macd_value:.2f} > 0)"
            }
        elif not price_above_sma and not macd_positive:
            # 熊市：价格在 SMA 下方，MACD 为负
            permissions = {
                "allow_long": False,  # 禁止做多
                "allow_short": True,  # ✅ 允许做空（核心修复）
                "regime": "BEAR",
                "position_multiplier": 1.0,  # 熊市做空正常仓位
                "reason": f"熊市 (价格 {current_price:.2f} < SMA{sma_period} {sma_value:.2f}, MACD {macd_value:.2f} < 0)"
            }
        else:
            # 震荡：价格和 MACD 方向不一致
            permissions = {
                "allow_long": True,   # 震荡市允许双向
                "allow_short": True,
                "regime": "SIDEWAYS",
                "position_multiplier": 0.7,  # 震荡市降低仓位
                "reason": f"震荡 (价格与 SMA/MACD 方向不一致)"
            }

        self.logger.info(
            f"[1D] 方向性权限评估: {permissions['regime']} | "
            f"做多={permissions['allow_long']}, 做空={permissions['allow_short']} | "
            f"仓位乘数={permissions['position_multiplier']:.1f}"
        )

        return permissions

    def get_decision_state(self) -> DecisionState:
        """获取当前决策状态"""
        return self._decision_state

    def set_decision_state(self, state: DecisionState, confidence: str = "MEDIUM"):
        """设置决策状态 (由 MultiAgentAnalyzer 调用)"""
        old_state = self._decision_state
        self._decision_state = state
        self._decision_confidence = confidence
        self._decision_updated = datetime.now(timezone.utc)

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
            self.trend_manager is not None and self.trend_manager.is_initialized() and
            self.decision_manager is not None and self.decision_manager.is_initialized() and
            self.execution_manager is not None and self.execution_manager.is_initialized()
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
