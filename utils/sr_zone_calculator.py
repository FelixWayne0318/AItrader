# utils/sr_zone_calculator.py
"""
Support/Resistance Zone Calculator v3.1

职责:
- 聚合多个数据源的 S/R 候选价位
- 聚类形成 S/R Zone (价差 < cluster_pct 的合并)
- 计算 Zone 强度 (基于 confluence + touch count)
- 输出给 AI 和本地硬风控使用
- v2.0: 添加 level (时间框架级别) 和 source_type (来源类型)
- v2.0: 添加详细 AI 报告，包含原始数据供 AI 验证
- v3.0: 添加 Swing Point 检测 (Williams Fractal N-bar pivot)
- v3.0: ATR 自适应聚类阈值
- v3.0: Touch Count 评分 (2-3 touches 最优)
- v3.1: S/R Flip - 被突破的阻力变为支撑，被跌破的支撑变为阻力
- v3.1: Round Number 心理整数关口 (Osler 2000)

设计原则:
- 只做预处理，不做交易判断
- 输出结构化数据，让 AI 解读
- 硬风控只在 HIGH strength 时介入
- v2.0: 传递原始数据让 AI 可以验证计算结果
- v3.0: Swing Points 是学术验证最有效的 S/R 来源 (Chan 2022, MDPI)
- v3.1: S/R Flip 确保价格在任何位置都有上下方 S/R 参考

参考:
- Chan (2022): Machine Learning with Support/Resistance (MDPI)
- Osler (2000): Support for Resistance (FRB NY)
- DeepSupp (2025): HDBSCAN for S/R (arXiv:2507.01971)
- QuantStrategy.io: Order Book Depth Analysis
- Analyzing Alpha: Support and Resistance
- TradingAgents: Local preprocessing + AI decision

Author: AItrader Team
Date: 2026-01
Version: 3.1
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field


# =============================================================================
# v2.0: Level and Source Type Enums
# =============================================================================

class SRLevel:
    """S/R Zone 时间框架级别"""
    MAJOR = "MAJOR"           # 日线/周线级别 (SMA_200, 周线 BB)
    INTERMEDIATE = "INTERMEDIATE"  # 4H 级别 (SMA_50, 4H BB)
    MINOR = "MINOR"           # 15M/1H 级别 (SMA_20, 15M BB, Order Wall)


class SRSourceType:
    """S/R 来源类型"""
    ORDER_FLOW = "ORDER_FLOW"       # 订单流 (Order Wall) - 最实时
    TECHNICAL = "TECHNICAL"         # 技术指标 (SMA, BB) - 广泛认可
    STRUCTURAL = "STRUCTURAL"       # 结构性 (前高/前低, Swing Point) - 历史验证
    PROJECTED = "PROJECTED"         # v4.0: 数学投射 (Pivot Points) - 无历史确认
    PSYCHOLOGICAL = "PSYCHOLOGICAL" # v4.0: 心理关口 (Round Numbers)


@dataclass
class SRCandidate:
    """S/R 候选价位"""
    price: float
    source: str          # 来源: BB_Lower, BB_Upper, SMA_50, SMA_200, Order_Wall, Swing_High, Swing_Low, Round_Number
    weight: float        # 权重: Order_Wall=0.8, SMA_200=1.5, Swing=1.2, BB=1.0, SMA_50=0.8
    side: str            # support 或 resistance
    extra: Dict = field(default_factory=dict)  # 额外信息 (如 wall size, bar_index)
    # v2.0 新增
    level: str = SRLevel.MINOR           # 时间框架级别
    source_type: str = SRSourceType.TECHNICAL  # 来源类型
    # v4.0 新增: 用于同源封顶 — 同 timeframe 的候选权重和不超过 SAME_DATA_WEIGHT_CAP
    timeframe: str = ""  # "1d", "4h", "15m", "daily_pivot", "weekly_pivot", "15m_vp", "realtime", "static"


@dataclass
class SRZone:
    """S/R Zone (聚类后的区域)"""
    price_low: float
    price_high: float
    price_center: float
    side: str            # support 或 resistance
    strength: str        # HIGH, MEDIUM, LOW
    sources: List[str]   # 来源列表
    total_weight: float  # 总权重
    distance_pct: float  # 距离当前价格的百分比
    has_order_wall: bool # 是否包含订单簿大单
    wall_size_btc: float # 大单总量 (BTC)
    # v2.0 新增
    level: str = SRLevel.MINOR           # 时间框架级别 (取最高级别)
    source_type: str = SRSourceType.TECHNICAL  # 主要来源类型
    order_walls: List[Dict] = field(default_factory=list)  # Order Wall 详情
    # v3.0 新增
    touch_count: int = 0                 # 价格触碰次数 (2-3 最优)
    has_swing_point: bool = False        # 是否包含 Swing Point


class SRZoneCalculator:
    """
    S/R Zone 计算器 v3.0

    v3.0 新功能:
    - Swing Point 检测: Williams Fractal (N-bar pivot high/low)
    - ATR 自适应聚类: 用 ATR 替代固定百分比，适应不同波动率
    - Touch Count 评分: 统计价格触碰次数，2-3 次最优 (Osler 2000)

    使用方法:
    ```python
    calculator = SRZoneCalculator()
    result = calculator.calculate(
        current_price=100000,
        bb_data={'upper': 101500, 'lower': 98500, 'middle': 100000},
        sma_data={'sma_50': 99000, 'sma_200': 95000},
        orderbook_anomalies={'bid_anomalies': [...], 'ask_anomalies': [...]},
        bars_data=[{'high': ..., 'low': ..., 'close': ...}, ...],  # v3.0
        atr_value=1500.0,  # v3.0
    )

    # 输出给 AI
    ai_report = result['ai_report']

    # 硬风控检查
    if result['hard_control']['block_long']:
        # 阻止 LONG
    ```
    """

    # 权重配置
    # v2.1: 降低 Order Wall 权重 (从 2.0 → 0.8)
    # v3.0: 新增 Swing Point 权重 1.2 (介于 BB=1.0 和 SMA_200=1.5 之间)
    WEIGHTS = {
        'Order_Wall': 0.8,      # 订单簿大单 (v2.1: 降低权重，仅作为辅助确认)
        'SMA_200': 1.5,         # 长期趋势 (最重要)
        'Swing_High': 1.2,      # v3.0: Swing Point (结构性，学术验证有效)
        'Swing_Low': 1.2,       # v3.0: Swing Point
        'BB_Upper': 1.0,        # 布林带
        'BB_Lower': 1.0,
        'SMA_50': 0.8,          # 中期趋势
        'Pivot': 0.7,           # Pivot Points (可选)
        'Round_Number': 0.6,    # v3.1: 心理整数关口 (Osler 2000: round numbers attract orders)
    }

    # v2.1: Order Wall 过滤阈值
    ORDER_WALL_THRESHOLDS = {
        'min_btc': 50.0,        # 最小 BTC 阈值 (小于此值不算大单)
        'min_distance_pct': 0.5, # 最小距离阈值 (距离当前价 < 0.5% 的不算 S/R)
        'high_strength_btc': 100.0,  # 达到此 BTC 量才能贡献 HIGH strength
    }

    # 强度阈值
    # v2.1: HIGH 需要 total_weight >= 3.0 或 Order Wall >= 100 BTC
    STRENGTH_THRESHOLDS = {
        'HIGH': 3.0,            # 总权重 >= 3.0 或 Order Wall >= high_strength_btc
        'MEDIUM': 1.5,          # 总权重 >= 1.5
        'LOW': 0.0,             # 其他
    }

    def __init__(
        self,
        cluster_pct: float = 0.5,       # 聚类阈值 (价差 < 0.5% 合并)
        zone_expand_pct: float = 0.1,   # Zone 扩展 (上下各 0.1%)
        hard_control_threshold_pct: float = 1.0,  # 硬风控阈值 (距离 < 1%)
        # v3.0: Swing Point 配置
        swing_detection_enabled: bool = True,
        swing_left_bars: int = 5,       # 左侧 N 根 bar
        swing_right_bars: int = 5,      # 右侧 N 根 bar
        swing_weight: float = 1.2,      # Swing Point 权重
        swing_max_age: int = 100,       # 最大回看 bar 数
        # v3.0: ATR 自适应聚类
        use_atr_adaptive: bool = True,
        atr_cluster_multiplier: float = 0.5,  # cluster_threshold = ATR × multiplier
        # v3.0: Touch Count 配置
        touch_count_enabled: bool = True,
        touch_threshold_atr: float = 0.3,  # 触碰判定距离 = ATR × threshold
        optimal_touches: Tuple[int, ...] = (2, 3),  # 最优触碰次数
        decay_after_touches: int = 4,   # 超过此次数开始衰减
        # v4.0: Aggregation rules (from configs/base.yaml: sr_zones.aggregation.*)
        same_data_weight_cap: float = 2.5,   # 同源封顶
        max_zone_weight: float = 6.0,        # Zone 总权重上限
        confluence_bonus_2: float = 0.2,     # 2 种来源类型交汇奖励
        confluence_bonus_3: float = 0.5,     # 3+ 种来源类型交汇奖励
        logger: logging.Logger = None,
    ):
        """
        初始化计算器

        Parameters
        ----------
        cluster_pct : float
            聚类阈值，价差小于此百分比的候选合并为一个 Zone
        zone_expand_pct : float
            Zone 边界扩展百分比
        hard_control_threshold_pct : float
            硬风控触发阈值 (仅对 HIGH strength)
        swing_detection_enabled : bool
            启用 Swing Point 检测 (v3.0)
        swing_left_bars : int
            Swing Point 左侧 bar 数量
        swing_right_bars : int
            Swing Point 右侧 bar 数量
        swing_weight : float
            Swing Point 权重
        swing_max_age : int
            Swing Point 最大回看 bar 数
        use_atr_adaptive : bool
            使用 ATR 自适应聚类阈值 (v3.0)
        atr_cluster_multiplier : float
            ATR 聚类乘数 (cluster_threshold = ATR × multiplier)
        touch_count_enabled : bool
            启用 Touch Count 评分 (v3.0)
        touch_threshold_atr : float
            触碰判定距离 (ATR 的倍数)
        optimal_touches : Tuple[int, ...]
            最优触碰次数 (权重加成)
        decay_after_touches : int
            超过此次数后权重开始衰减
        logger : logging.Logger
            日志记录器
        """
        self.cluster_pct = cluster_pct
        self.zone_expand_pct = zone_expand_pct
        self.hard_control_threshold_pct = hard_control_threshold_pct

        # v3.0: Swing Point
        self.swing_detection_enabled = swing_detection_enabled
        self.swing_left_bars = swing_left_bars
        self.swing_right_bars = swing_right_bars
        self.swing_weight = swing_weight
        self.swing_max_age = swing_max_age
        # Update WEIGHTS with configured swing weight
        self.WEIGHTS = dict(self.WEIGHTS)  # Instance copy
        self.WEIGHTS['Swing_High'] = swing_weight
        self.WEIGHTS['Swing_Low'] = swing_weight

        # v3.0: ATR adaptive clustering
        self.use_atr_adaptive = use_atr_adaptive
        self.atr_cluster_multiplier = atr_cluster_multiplier

        # v3.0: Touch count
        self.touch_count_enabled = touch_count_enabled
        self.touch_threshold_atr = touch_threshold_atr
        self.optimal_touches = optimal_touches
        self.decay_after_touches = decay_after_touches

        # v4.0: Aggregation rules (from configs/base.yaml: sr_zones.aggregation.*)
        self._same_data_weight_cap = same_data_weight_cap
        self._max_zone_weight = max_zone_weight
        self._confluence_bonus_2 = confluence_bonus_2
        self._confluence_bonus_3 = confluence_bonus_3

        self.logger = logger or logging.getLogger(__name__)

    # =========================================================================
    # v3.0: Swing Point Detection (Williams Fractal / N-bar Pivot)
    # =========================================================================

    def _detect_swing_points(
        self,
        bars_data: List[Dict[str, Any]],
        current_price: float,
    ) -> List[SRCandidate]:
        """
        Detect swing highs and swing lows using Williams Fractal method.

        A swing high occurs when a bar's high is the highest of (left_bars + 1 + right_bars) bars.
        A swing low occurs when a bar's low is the lowest of (left_bars + 1 + right_bars) bars.

        Reference: Chan (2022, MDPI) - swing points improved ML S/R profitability by 65%.

        Parameters
        ----------
        bars_data : List[Dict]
            OHLC bar data: [{'high': float, 'low': float, 'close': float}, ...]
            Ordered from oldest to newest.
        current_price : float
            Current market price for support/resistance classification.

        Returns
        -------
        List[SRCandidate]
            Detected swing point candidates.
        """
        candidates = []
        if not bars_data:
            return candidates

        # Limit to max_age bars
        bars = bars_data[-self.swing_max_age:] if len(bars_data) > self.swing_max_age else bars_data
        n = len(bars)
        left = self.swing_left_bars
        right = self.swing_right_bars
        min_bars_needed = left + 1 + right

        if n < min_bars_needed:
            self.logger.debug(
                f"Swing detection: insufficient bars ({n} < {min_bars_needed})"
            )
            return candidates

        for i in range(left, n - right):
            bar = bars[i]
            bar_high = float(bar.get('high', 0))
            bar_low = float(bar.get('low', 0))

            if bar_high <= 0 or bar_low <= 0:
                continue

            # Check swing high: bar[i].high >= all bars in [i-left, i+right]
            is_swing_high = True
            for j in range(i - left, i + right + 1):
                if j == i:
                    continue
                if float(bars[j].get('high', 0)) > bar_high:
                    is_swing_high = False
                    break

            # Check swing low: bar[i].low <= all bars in [i-left, i+right]
            is_swing_low = True
            for j in range(i - left, i + right + 1):
                if j == i:
                    continue
                if float(bars[j].get('low', 0)) < bar_low:
                    is_swing_low = False
                    break

            # Age weighting: more recent swings are more relevant
            bars_ago = n - 1 - i
            age_factor = max(0.5, 1.0 - (bars_ago / self.swing_max_age) * 0.5)

            if is_swing_high:
                # S/R Flip: swing high above price = resistance (standard)
                # swing high below price = support (broken resistance becomes support)
                # Reference: Osler (2000), Chan (2022)
                if bar_high >= current_price:
                    side = 'resistance'
                else:
                    side = 'support'  # S/R flip
                candidates.append(SRCandidate(
                    price=bar_high,
                    source=f"Swing_High",
                    weight=self.WEIGHTS['Swing_High'] * age_factor,
                    side=side,
                    extra={'bar_index': i, 'bars_ago': bars_ago, 'age_factor': age_factor},
                    level=SRLevel.INTERMEDIATE,
                    source_type=SRSourceType.STRUCTURAL,
                    timeframe="15m",  # v4.0 (B3)
                ))

            if is_swing_low:
                # S/R Flip: swing low below price = support (standard)
                # swing low above price = resistance (broken support becomes resistance)
                if bar_low <= current_price:
                    side = 'support'
                else:
                    side = 'resistance'  # S/R flip
                candidates.append(SRCandidate(
                    price=bar_low,
                    source=f"Swing_Low",
                    weight=self.WEIGHTS['Swing_Low'] * age_factor,
                    side=side,
                    extra={'bar_index': i, 'bars_ago': bars_ago, 'age_factor': age_factor},
                    level=SRLevel.INTERMEDIATE,
                    source_type=SRSourceType.STRUCTURAL,
                    timeframe="15m",  # v4.0 (B3)
                ))

        self.logger.debug(
            f"Swing detection: found {len(candidates)} swing points from {n} bars"
        )
        return candidates

    # =========================================================================
    # v3.0: ATR Calculation from Bars
    # =========================================================================

    @staticmethod
    def _calculate_atr_from_bars(
        bars_data: List[Dict[str, Any]],
        period: int = 14,
    ) -> float:
        """
        Calculate ATR (Average True Range) from bar data.

        Used when no external ATR value is provided.

        Parameters
        ----------
        bars_data : List[Dict]
            OHLC bar data.
        period : int
            ATR period (default 14).

        Returns
        -------
        float
            ATR value, or 0.0 if insufficient data.
        """
        if not bars_data or len(bars_data) < 2:
            return 0.0

        true_ranges = []
        for i in range(1, len(bars_data)):
            high = float(bars_data[i].get('high', 0))
            low = float(bars_data[i].get('low', 0))
            prev_close = float(bars_data[i - 1].get('close', 0))

            if high <= 0 or low <= 0 or prev_close <= 0:
                continue

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )
            true_ranges.append(tr)

        if not true_ranges:
            return 0.0

        # Use simple average of last `period` TRs
        recent = true_ranges[-period:] if len(true_ranges) >= period else true_ranges
        return sum(recent) / len(recent)

    # =========================================================================
    # v3.1: Round Number Psychological Levels
    # =========================================================================

    def _generate_round_number_levels(
        self,
        current_price: float,
        count: int = 3,
    ) -> List[SRCandidate]:
        """
        Generate round-number psychological S/R levels near current price.

        Round numbers attract limit orders and act as psychological barriers.
        Reference: Osler (2000) "Support for Resistance" - FRB NY

        Parameters
        ----------
        current_price : float
            Current price.
        count : int
            Number of levels above and below to generate.

        Returns
        -------
        List[SRCandidate]
            Round number candidates (both support and resistance).
        """
        candidates = []
        if current_price <= 0:
            return candidates

        # Determine round-number step based on price magnitude
        if current_price >= 10000:
            step = 1000       # BTC: $71000, $72000, $73000...
        elif current_price >= 1000:
            step = 100        # ETH: $3100, $3200...
        elif current_price >= 100:
            step = 10
        elif current_price >= 10:
            step = 1
        else:
            step = 0.1

        # Find the nearest round number below
        base = int(current_price / step) * step

        for i in range(-count, count + 1):
            level_price = base + i * step
            if level_price <= 0:
                continue
            # Skip levels too close to current price (< 0.1%)
            distance_pct = abs(level_price - current_price) / current_price * 100
            if distance_pct < 0.1:
                continue

            side = 'support' if level_price < current_price else 'resistance'
            candidates.append(SRCandidate(
                price=float(level_price),
                source='Round_Number',
                weight=self.WEIGHTS['Round_Number'],
                side=side,
                level=SRLevel.MINOR,
                source_type=SRSourceType.PSYCHOLOGICAL,  # v4.0 (B3): reclassified
                timeframe="static",  # v4.0 (B3)
            ))

        return candidates

    # =========================================================================
    # v3.0: Touch Count for Zones
    # =========================================================================

    def _count_zone_touches(
        self,
        zone_center: float,
        zone_low: float,
        zone_high: float,
        bars_data: List[Dict[str, Any]],
        atr_value: float,
    ) -> int:
        """
        Count discrete touches of a zone (consecutive bars = 1 touch).

        A "touch" requires price to leave the zone and then re-enter it.
        Consecutive bars overlapping the same zone count as a single touch.
        This matches Osler (2000)'s definition where 2-3 discrete visits
        to a price level indicate optimal S/R strength.

        Parameters
        ----------
        zone_center : float
            Center price of the zone.
        zone_low : float
            Lower boundary of the zone.
        zone_high : float
            Upper boundary of the zone.
        bars_data : List[Dict]
            OHLC bar data.
        atr_value : float
            Current ATR value for touch threshold calculation.

        Returns
        -------
        int
            Number of discrete touches.
        """
        if not bars_data or atr_value <= 0:
            return 0

        touch_distance = atr_value * self.touch_threshold_atr
        expanded_low = zone_low - touch_distance
        expanded_high = zone_high + touch_distance

        touches = 0
        was_in_zone = False

        for bar in bars_data:
            bar_high = float(bar.get('high', 0))
            bar_low = float(bar.get('low', 0))

            if bar_high <= 0 or bar_low <= 0:
                continue

            # Bar overlaps with the expanded zone
            in_zone = (bar_low <= expanded_high and bar_high >= expanded_low)

            if in_zone and not was_in_zone:
                # Price just entered the zone — count as a new touch
                touches += 1

            was_in_zone = in_zone

        return touches

    def _touch_weight_bonus(self, touch_count: int) -> float:
        """
        Calculate weight bonus based on touch count.

        2-3 touches: +0.5 weight bonus (optimal, Osler 2000)
        4+  touches: diminishing bonus (zone may be weakening)
        0-1 touches: no bonus

        Parameters
        ----------
        touch_count : int
            Number of price touches.

        Returns
        -------
        float
            Weight bonus to add to zone's total_weight.
        """
        if touch_count in self.optimal_touches:
            return 0.5
        elif touch_count >= self.decay_after_touches:
            # Diminishing: 0.3 for 4, 0.1 for 5, 0 for 6+
            decay = max(0.0, 0.5 - (touch_count - self.decay_after_touches + 1) * 0.2)
            return decay
        elif touch_count == 1:
            return 0.1
        return 0.0

    # =========================================================================
    # Main Calculation Methods
    # =========================================================================

    def calculate(
        self,
        current_price: float,
        bb_data: Optional[Dict[str, float]] = None,
        sma_data: Optional[Dict[str, float]] = None,
        orderbook_anomalies: Optional[Dict] = None,
        # v3.0: New parameters (backward compatible)
        bars_data: Optional[List[Dict[str, Any]]] = None,
        atr_value: Optional[float] = None,
        # v4.0: MTF bars and additional data sources
        bars_data_4h: Optional[List[Dict[str, Any]]] = None,
        bars_data_1d: Optional[List[Dict[str, Any]]] = None,
        daily_bar: Optional[Dict[str, Any]] = None,
        weekly_bar: Optional[Dict[str, Any]] = None,
        **kwargs,  # v4.0: absorbs old pivot_data from legacy callers
    ) -> Dict[str, Any]:
        """
        计算 S/R Zones

        Parameters
        ----------
        current_price : float
            当前价格
        bb_data : Dict, optional
            布林带数据 {'upper': float, 'lower': float, 'middle': float}
        sma_data : Dict, optional
            SMA 数据 {'sma_50': float, 'sma_200': float}
        orderbook_anomalies : Dict, optional
            订单簿异常数据 {'bid_anomalies': [...], 'ask_anomalies': [...]}
        bars_data : List[Dict], optional
            v3.0: OHLC bar data for swing detection and touch count
        atr_value : float, optional
            v3.0: ATR value for adaptive clustering. If None, calculated from bars_data.
        bars_data_4h : List[Dict], optional
            v4.0: 4H OHLC bars for MTF swing detection
        bars_data_1d : List[Dict], optional
            v4.0: 1D OHLC bars for MTF swing detection
        daily_bar : Dict, optional
            v4.0: Most recent completed daily bar for pivot calculation
        weekly_bar : Dict, optional
            v4.0: Most recent completed weekly bar for pivot calculation

        Returns
        -------
        Dict
            {
                'support_zones': List[SRZone],
                'resistance_zones': List[SRZone],
                'nearest_support': SRZone or None,
                'nearest_resistance': SRZone or None,
                'hard_control': {
                    'block_long': bool,
                    'block_short': bool,
                    'reason': str
                },
                'ai_report': str  # 格式化的 AI 报告
            }
        """
        if current_price <= 0:
            return self._empty_result()

        # v3.0: Calculate ATR if not provided (needed for adaptive clustering + touch count)
        effective_atr = atr_value
        if effective_atr is None and bars_data:
            effective_atr = self._calculate_atr_from_bars(bars_data)
        if effective_atr is None:
            effective_atr = 0.0

        # Step 1: 收集所有候选 (v3.0: Swing Points, v4.0: MTF + Pivots + VP)
        candidates = self._collect_candidates(
            current_price, bb_data, sma_data, orderbook_anomalies,
            bars_data=bars_data,
            bars_data_4h=bars_data_4h,
            bars_data_1d=bars_data_1d,
            daily_bar=daily_bar,
            weekly_bar=weekly_bar,
        )

        if not candidates:
            return self._empty_result()

        # Step 2: 分离 support 和 resistance
        support_candidates = [c for c in candidates if c.side == 'support']
        resistance_candidates = [c for c in candidates if c.side == 'resistance']

        # Step 3: 聚类形成 Zones (v3.0: ATR 自适应)
        support_zones = self._cluster_to_zones(
            support_candidates, current_price, 'support',
            atr_value=effective_atr,
        )
        resistance_zones = self._cluster_to_zones(
            resistance_candidates, current_price, 'resistance',
            atr_value=effective_atr,
        )

        # Step 3.5: v3.0 Touch Count scoring
        if self.touch_count_enabled and bars_data and effective_atr > 0:
            for zone in support_zones + resistance_zones:
                zone.touch_count = self._count_zone_touches(
                    zone.price_center, zone.price_low, zone.price_high,
                    bars_data, effective_atr,
                )
                # Apply touch weight bonus
                bonus = self._touch_weight_bonus(zone.touch_count)
                if bonus > 0:
                    zone.total_weight = round(zone.total_weight + bonus, 2)
                    # Re-evaluate strength after bonus
                    zone.strength = self._evaluate_strength(
                        zone.total_weight, zone.has_order_wall, zone.wall_size_btc
                    )

        # Step 4: 排序 (按距离)
        support_zones.sort(key=lambda z: z.distance_pct)
        resistance_zones.sort(key=lambda z: z.distance_pct)

        # Step 5: 确定最近的 S/R
        nearest_support = support_zones[0] if support_zones else None
        nearest_resistance = resistance_zones[0] if resistance_zones else None

        # Step 6: 硬风控检查
        hard_control = self._check_hard_control(
            current_price, nearest_support, nearest_resistance
        )

        # Step 7: 生成 AI 报告
        ai_report = self._generate_ai_report(
            current_price, support_zones, resistance_zones,
            nearest_support, nearest_resistance
        )

        return {
            'support_zones': support_zones,
            'resistance_zones': resistance_zones,
            'nearest_support': nearest_support,
            'nearest_resistance': nearest_resistance,
            'hard_control': hard_control,
            'ai_report': ai_report,
        }

    def _evaluate_strength(
        self,
        total_weight: float,
        has_order_wall: bool,
        wall_size_btc: float,
        projected_only: bool = False,
    ) -> str:
        """
        Evaluate zone strength from weight and wall size.

        v4.0 (D3): If zone is PROJECTED-only (all candidates are PROJECTED type),
        cap strength at MEDIUM. PROJECTED zones have no historical trade confirmation.
        """
        high_strength_btc = self.ORDER_WALL_THRESHOLDS['high_strength_btc']
        has_significant_wall = has_order_wall and wall_size_btc >= high_strength_btc

        if has_significant_wall or total_weight >= self.STRENGTH_THRESHOLDS['HIGH']:
            strength = 'HIGH'
        elif total_weight >= self.STRENGTH_THRESHOLDS['MEDIUM']:
            strength = 'MEDIUM'
        else:
            strength = 'LOW'

        # v4.0: PROJECTED-only zones capped at MEDIUM
        if projected_only and strength == 'HIGH':
            strength = 'MEDIUM'

        return strength

    def _collect_candidates(
        self,
        current_price: float,
        bb_data: Optional[Dict],
        sma_data: Optional[Dict],
        orderbook_anomalies: Optional[Dict],
        # v3.0: New parameter
        bars_data: Optional[List[Dict[str, Any]]] = None,
        # v4.0: MTF bars and additional data sources
        bars_data_4h: Optional[List[Dict[str, Any]]] = None,
        bars_data_1d: Optional[List[Dict[str, Any]]] = None,
        daily_bar: Optional[Dict[str, Any]] = None,
        weekly_bar: Optional[Dict[str, Any]] = None,
    ) -> List[SRCandidate]:
        """
        收集所有 S/R 候选价位.

        v3.0: Swing Points
        v4.0: MTF swing detection (1D, 4H, 15M), Pivot Points, Volume Profile
              Each source is wrapped in try/except for per-layer error isolation.
              pivot_data parameter removed — Pivot now calculated by sr_pivot_calculator.
        """
        candidates = []

        # ===== 检测层: MTF Swing Points (per-layer error isolation) =====
        # v4.0: Uses sr_swing_detector with Spitsin (2025) volume weighting
        if self.swing_detection_enabled:
            try:
                from utils.sr_swing_detector import detect_swing_points
            except ImportError:
                detect_swing_points = None
                self.logger.warning("sr_swing_detector not available, using legacy swing detection")

            # v4.0: 1D Swing (highest weight, MAJOR level)
            if bars_data_1d:
                try:
                    if detect_swing_points:
                        candidates.extend(detect_swing_points(
                            bars_data_1d, current_price, timeframe="1d",
                            base_weight=2.0, level=SRLevel.MAJOR,
                            left_bars=self.swing_left_bars, right_bars=self.swing_right_bars,
                            max_age=self.swing_max_age, volume_weighting=True,
                        ))
                    else:
                        for c in self._detect_swing_points(bars_data_1d, current_price):
                            c.weight = 2.0 * (c.extra.get('age_factor', 1.0))
                            c.level = SRLevel.MAJOR
                            c.timeframe = "1d"
                            candidates.append(c)
                except Exception as e:
                    self.logger.warning(f"1D Swing detection failed: {e}")

            # v4.0: 4H Swing (intermediate weight)
            if bars_data_4h:
                try:
                    if detect_swing_points:
                        candidates.extend(detect_swing_points(
                            bars_data_4h, current_price, timeframe="4h",
                            base_weight=1.5, level=SRLevel.INTERMEDIATE,
                            left_bars=self.swing_left_bars, right_bars=self.swing_right_bars,
                            max_age=self.swing_max_age, volume_weighting=True,
                        ))
                    else:
                        for c in self._detect_swing_points(bars_data_4h, current_price):
                            c.weight = 1.5 * (c.extra.get('age_factor', 1.0))
                            c.level = SRLevel.INTERMEDIATE
                            c.timeframe = "4h"
                            candidates.append(c)
                except Exception as e:
                    self.logger.warning(f"4H Swing detection failed: {e}")

            # 15M Swing (volume-weighted if available)
            if bars_data:
                try:
                    if detect_swing_points:
                        candidates.extend(detect_swing_points(
                            bars_data, current_price, timeframe="15m",
                            base_weight=0.8, level=SRLevel.MINOR,
                            left_bars=self.swing_left_bars, right_bars=self.swing_right_bars,
                            max_age=self.swing_max_age, volume_weighting=True,
                        ))
                    else:
                        swing_candidates = self._detect_swing_points(bars_data, current_price)
                        candidates.extend(swing_candidates)
                except Exception as e:
                    self.logger.warning(f"15M Swing detection failed: {e}")

        # ===== 投射层: Pivot Points (v4.0, per-layer error isolation) =====
        if daily_bar or weekly_bar:
            try:
                from utils.sr_pivot_calculator import calculate_pivots
                pivot_candidates = calculate_pivots(daily_bar, weekly_bar, current_price)
                candidates.extend(pivot_candidates)
            except Exception as e:
                self.logger.warning(f"Pivot calculation failed: {e}")

        # ===== 确认层: Volume Profile (v4.0, per-layer error isolation) =====
        if bars_data and len(bars_data) >= 10:
            try:
                from utils.sr_volume_profile import calculate_volume_profile
                vp_candidates = calculate_volume_profile(bars_data, current_price)
                candidates.extend(vp_candidates)
            except Exception as e:
                self.logger.warning(f"Volume Profile calculation failed: {e}")

        # ===== 现有来源: BB, SMA, OrderWall, Round# (per-layer error isolation) =====

        # Bollinger Bands (15M = MINOR level)
        try:
            if bb_data:
                bb_upper = bb_data.get('upper')
                bb_lower = bb_data.get('lower')

                if bb_upper and bb_upper > current_price:
                    candidates.append(SRCandidate(
                        price=bb_upper,
                        source='BB_Upper',
                        weight=self.WEIGHTS['BB_Upper'],
                        side='resistance',
                        level=SRLevel.MINOR,
                        source_type=SRSourceType.TECHNICAL,
                        timeframe="15m",  # v4.0 (B3)
                    ))

                if bb_lower and bb_lower < current_price:
                    candidates.append(SRCandidate(
                        price=bb_lower,
                        source='BB_Lower',
                        weight=self.WEIGHTS['BB_Lower'],
                        side='support',
                        level=SRLevel.MINOR,
                        source_type=SRSourceType.TECHNICAL,
                        timeframe="15m",  # v4.0 (B3)
                    ))
        except Exception as e:
            self.logger.warning(f"BB candidates failed: {e}")

        # SMA (SMA_50 = INTERMEDIATE, SMA_200 = MAJOR)
        try:
            if sma_data:
                sma_50 = sma_data.get('sma_50')
                sma_200 = sma_data.get('sma_200')

                if sma_50 and sma_50 > 0:
                    side = 'support' if sma_50 < current_price else 'resistance'
                    candidates.append(SRCandidate(
                        price=sma_50,
                        source='SMA_50',
                        weight=self.WEIGHTS['SMA_50'],
                        side=side,
                        level=SRLevel.INTERMEDIATE,
                        source_type=SRSourceType.TECHNICAL,
                        timeframe="15m",  # v4.0 (B3)
                    ))

                if sma_200 and sma_200 > 0:
                    side = 'support' if sma_200 < current_price else 'resistance'
                    candidates.append(SRCandidate(
                        price=sma_200,
                        source='SMA_200_15M',  # v4.0 (B5): clarify this is 15M SMA_200 (≈50h, not 200 days)
                        weight=self.WEIGHTS['SMA_200'],
                        side=side,
                        level=SRLevel.MAJOR,
                        source_type=SRSourceType.TECHNICAL,
                        timeframe="15m",  # v4.0 (B3)
                    ))
        except Exception as e:
            self.logger.warning(f"SMA candidates failed: {e}")

        # Order Book Walls (MINOR level, ORDER_FLOW type - 最实时)
        # v2.1: 添加严格过滤条件，避免盘口普通订单被误识别为 S/R
        try:
            if orderbook_anomalies:
                min_btc = self.ORDER_WALL_THRESHOLDS['min_btc']
                min_distance_pct = self.ORDER_WALL_THRESHOLDS['min_distance_pct']

                # Bid walls = Support
                for wall in orderbook_anomalies.get('bid_anomalies', []):
                    wall_price = wall.get('price', 0)
                    wall_btc = wall.get('volume_btc', 0)

                    # v2.1: 过滤条件
                    if wall_price <= 0 or wall_price >= current_price:
                        continue

                    # 检查最小 BTC 阈值
                    if wall_btc < min_btc:
                        self.logger.debug(
                            f"Skipping bid wall at ${wall_price:.0f}: {wall_btc:.1f} BTC < {min_btc} BTC threshold"
                        )
                        continue

                    # 检查最小距离阈值
                    distance_pct = (current_price - wall_price) / current_price * 100
                    if distance_pct < min_distance_pct:
                        self.logger.debug(
                            f"Skipping bid wall at ${wall_price:.0f}: {distance_pct:.2f}% < {min_distance_pct}% min distance"
                        )
                        continue

                    candidates.append(SRCandidate(
                        price=wall_price,
                        source=f"Order_Wall_${wall_price:.0f}",
                        weight=self.WEIGHTS['Order_Wall'],
                        side='support',
                        extra={
                            'size_btc': wall_btc,
                            'multiplier': wall.get('multiplier', 1),
                        },
                        level=SRLevel.MINOR,
                        source_type=SRSourceType.ORDER_FLOW,
                        timeframe="realtime",  # v4.0 (B3)
                    ))

                # Ask walls = Resistance
                for wall in orderbook_anomalies.get('ask_anomalies', []):
                    wall_price = wall.get('price', 0)
                    wall_btc = wall.get('volume_btc', 0)

                    # v2.1: 过滤条件
                    if wall_price <= 0 or wall_price <= current_price:
                        continue

                    # 检查最小 BTC 阈值
                    if wall_btc < min_btc:
                        self.logger.debug(
                            f"Skipping ask wall at ${wall_price:.0f}: {wall_btc:.1f} BTC < {min_btc} BTC threshold"
                        )
                        continue

                    # 检查最小距离阈值
                    distance_pct = (wall_price - current_price) / current_price * 100
                    if distance_pct < min_distance_pct:
                        self.logger.debug(
                            f"Skipping ask wall at ${wall_price:.0f}: {distance_pct:.2f}% < {min_distance_pct}% min distance"
                        )
                        continue

                    candidates.append(SRCandidate(
                        price=wall_price,
                        source=f"Order_Wall_${wall_price:.0f}",
                        weight=self.WEIGHTS['Order_Wall'],
                        side='resistance',
                        extra={
                            'size_btc': wall_btc,
                            'multiplier': wall.get('multiplier', 1),
                        },
                        level=SRLevel.MINOR,
                        source_type=SRSourceType.ORDER_FLOW,
                        timeframe="realtime",  # v4.0 (B3)
                    ))
        except Exception as e:
            self.logger.warning(f"OrderWall candidates failed: {e}")

        # v4.0: Old pivot_data block removed — Pivots now calculated by sr_pivot_calculator
        # (called in 投射层 section above with daily_bar + weekly_bar)

        # v3.1: Round Number Psychological Levels
        try:
            round_candidates = self._generate_round_number_levels(current_price)
            candidates.extend(round_candidates)
        except Exception as e:
            self.logger.warning(f"Round number candidates failed: {e}")

        return candidates

    def _cluster_to_zones(
        self,
        candidates: List[SRCandidate],
        current_price: float,
        side: str,
        # v3.0: ATR for adaptive clustering
        atr_value: float = 0.0,
    ) -> List[SRZone]:
        """将候选聚类为 Zones (v3.0: ATR 自适应阈值)"""
        if not candidates:
            return []

        # v3.0: Determine effective cluster threshold
        if self.use_atr_adaptive and atr_value > 0 and current_price > 0:
            # ATR-based threshold: ATR × multiplier, expressed as percentage
            atr_pct = (atr_value / current_price) * 100
            effective_cluster_pct = atr_pct * self.atr_cluster_multiplier
            # Clamp to reasonable range [0.1%, 2.0%]
            effective_cluster_pct = max(0.1, min(2.0, effective_cluster_pct))
            self.logger.debug(
                f"ATR adaptive clustering: ATR=${atr_value:.0f} "
                f"({atr_pct:.2f}%), cluster_pct={effective_cluster_pct:.3f}%"
            )
        else:
            effective_cluster_pct = self.cluster_pct

        # 按价格排序
        candidates.sort(key=lambda c: c.price)

        zones = []
        current_cluster = [candidates[0]]

        for i in range(1, len(candidates)):
            candidate = candidates[i]
            last_price = current_cluster[-1].price

            # 计算价差百分比
            price_diff_pct = abs(candidate.price - last_price) / last_price * 100

            if price_diff_pct <= effective_cluster_pct:
                # 合并到当前 cluster
                current_cluster.append(candidate)
            else:
                # 完成当前 cluster，创建 Zone
                zone = self._create_zone(current_cluster, current_price, side)
                zones.append(zone)
                # 开始新 cluster
                current_cluster = [candidate]

        # 处理最后一个 cluster
        if current_cluster:
            zone = self._create_zone(current_cluster, current_price, side)
            zones.append(zone)

        return zones

    def _create_zone(
        self,
        cluster: List[SRCandidate],
        current_price: float,
        side: str,
    ) -> SRZone:
        """从候选 cluster 创建 Zone (v3.0: 添加 swing_point/touch_count)"""
        prices = [c.price for c in cluster]
        price_center = sum(prices) / len(prices)

        # Zone 边界 (扩展)
        expand = price_center * self.zone_expand_pct / 100
        price_low = min(prices) - expand
        price_high = max(prices) + expand

        # 来源列表
        sources = [c.source for c in cluster]

        # v4.0 (D2): Same-source weight capping + multi-source bonus + total cap
        # Step 1: Group by timeframe, cap each group
        same_data_weight_cap = getattr(self, '_same_data_weight_cap', 2.5)
        weight_by_timeframe = {}
        for c in cluster:
            tf = c.timeframe or "unknown"
            weight_by_timeframe.setdefault(tf, 0.0)
            weight_by_timeframe[tf] = min(
                weight_by_timeframe[tf] + c.weight,
                same_data_weight_cap
            )
        total_weight = sum(weight_by_timeframe.values())

        # Step 2: Multi-source independence bonus (from config)
        unique_source_types = len(set(c.source_type for c in cluster))
        if unique_source_types >= 3:
            total_weight += getattr(self, '_confluence_bonus_3', 0.5)
        elif unique_source_types >= 2:
            total_weight += getattr(self, '_confluence_bonus_2', 0.2)

        # Step 3: Total weight cap
        max_zone_weight = getattr(self, '_max_zone_weight', 6.0)
        total_weight = min(total_weight, max_zone_weight)

        # 是否有 Order Wall
        has_order_wall = any('Order_Wall' in c.source for c in cluster)
        wall_size_btc = sum(
            c.extra.get('size_btc', 0)
            for c in cluster
            if 'Order_Wall' in c.source
        )

        # v2.0: 收集 Order Wall 详情
        order_walls = []
        for c in cluster:
            if 'Order_Wall' in c.source:
                order_walls.append({
                    'price': c.price,
                    'size_btc': c.extra.get('size_btc', 0),
                    'multiplier': c.extra.get('multiplier', 1),
                })

        # v3.0: Check for swing points
        has_swing_point = any('Swing_' in c.source for c in cluster)

        # v4.0 (D3): Evaluate strength with PROJECTED cap
        has_projected_only = all(c.source_type == SRSourceType.PROJECTED for c in cluster)
        strength = self._evaluate_strength(total_weight, has_order_wall, wall_size_btc,
                                           projected_only=has_projected_only)

        # 距离当前价格
        if side == 'support':
            distance_pct = (current_price - price_center) / current_price * 100
        else:
            distance_pct = (price_center - current_price) / current_price * 100

        # v2.0: 确定 Zone 的级别 (取最高级别)
        level_priority = {SRLevel.MAJOR: 3, SRLevel.INTERMEDIATE: 2, SRLevel.MINOR: 1}
        zone_level = SRLevel.MINOR
        for c in cluster:
            if level_priority.get(c.level, 0) > level_priority.get(zone_level, 0):
                zone_level = c.level

        # v2.0: 确定主要来源类型 (ORDER_FLOW > STRUCTURAL > PROJECTED > TECHNICAL > PSYCHOLOGICAL)
        # v3.0: STRUCTURAL priority raised (swing points are strong signals)
        # v4.0 (B4): Added PROJECTED and PSYCHOLOGICAL
        type_priority = {
            SRSourceType.ORDER_FLOW: 4,
            SRSourceType.STRUCTURAL: 3,
            SRSourceType.PROJECTED: 2,
            SRSourceType.TECHNICAL: 1,
            SRSourceType.PSYCHOLOGICAL: 0,
        }
        zone_source_type = SRSourceType.TECHNICAL
        for c in cluster:
            if type_priority.get(c.source_type, 0) > type_priority.get(zone_source_type, 0):
                zone_source_type = c.source_type

        return SRZone(
            price_low=round(price_low, 2),
            price_high=round(price_high, 2),
            price_center=round(price_center, 2),
            side=side,
            strength=strength,
            sources=sources,
            total_weight=round(total_weight, 2),
            distance_pct=round(distance_pct, 2),
            has_order_wall=has_order_wall,
            wall_size_btc=round(wall_size_btc, 2),
            level=zone_level,
            source_type=zone_source_type,
            order_walls=order_walls,
            touch_count=0,  # Filled in calculate() after clustering
            has_swing_point=has_swing_point,
        )

    def _check_hard_control(
        self,
        current_price: float,
        nearest_support: Optional[SRZone],
        nearest_resistance: Optional[SRZone],
    ) -> Dict[str, Any]:
        """
        硬风控检查

        只在 HIGH strength 且距离 < threshold 时阻止
        """
        block_long = False
        block_short = False
        reasons = []

        # 检查阻力位 (阻止 LONG)
        if nearest_resistance and nearest_resistance.strength == 'HIGH':
            if nearest_resistance.distance_pct < self.hard_control_threshold_pct:
                block_long = True
                if nearest_resistance.has_order_wall:
                    reasons.append(
                        f"LONG blocked: Order Wall at ${nearest_resistance.price_center:,.0f} "
                        f"({nearest_resistance.wall_size_btc:.1f} BTC), "
                        f"{nearest_resistance.distance_pct:.1f}% away"
                    )
                else:
                    reasons.append(
                        f"LONG blocked: HIGH strength resistance at ${nearest_resistance.price_center:,.0f} "
                        f"(sources: {', '.join(nearest_resistance.sources)}), "
                        f"{nearest_resistance.distance_pct:.1f}% away"
                    )

        # 检查支撑位 (阻止 SHORT)
        if nearest_support and nearest_support.strength == 'HIGH':
            if nearest_support.distance_pct < self.hard_control_threshold_pct:
                block_short = True
                if nearest_support.has_order_wall:
                    reasons.append(
                        f"SHORT blocked: Order Wall at ${nearest_support.price_center:,.0f} "
                        f"({nearest_support.wall_size_btc:.1f} BTC), "
                        f"{nearest_support.distance_pct:.1f}% away"
                    )
                else:
                    reasons.append(
                        f"SHORT blocked: HIGH strength support at ${nearest_support.price_center:,.0f} "
                        f"(sources: {', '.join(nearest_support.sources)}), "
                        f"{nearest_support.distance_pct:.1f}% away"
                    )

        return {
            'block_long': block_long,
            'block_short': block_short,
            'reason': '; '.join(reasons) if reasons else None,
        }

    def _generate_ai_report(
        self,
        current_price: float,
        support_zones: List[SRZone],
        resistance_zones: List[SRZone],
        nearest_support: Optional[SRZone],
        nearest_resistance: Optional[SRZone],
    ) -> str:
        """生成 AI 报告 (v3.0: 包含 swing/touch 信息)"""
        parts = ["SUPPORT/RESISTANCE ZONES:"]
        parts.append("")

        # 最近阻力
        if nearest_resistance:
            wall_info = f" [Order Wall: {nearest_resistance.wall_size_btc:.1f} BTC]" if nearest_resistance.has_order_wall else ""
            swing_info = " [Swing Point]" if nearest_resistance.has_swing_point else ""
            touch_info = f" [Touches: {nearest_resistance.touch_count}]" if nearest_resistance.touch_count > 0 else ""
            parts.append(f"Nearest RESISTANCE: ${nearest_resistance.price_center:,.0f} "
                        f"({nearest_resistance.distance_pct:.1f}% away) "
                        f"[{nearest_resistance.strength}]{wall_info}{swing_info}{touch_info}")
            parts.append(f"  Zone: ${nearest_resistance.price_low:,.0f} - ${nearest_resistance.price_high:,.0f}")
            parts.append(f"  Sources: {', '.join(nearest_resistance.sources)}")
        else:
            parts.append("Nearest RESISTANCE: None detected")

        parts.append("")

        # 最近支撑
        if nearest_support:
            wall_info = f" [Order Wall: {nearest_support.wall_size_btc:.1f} BTC]" if nearest_support.has_order_wall else ""
            swing_info = " [Swing Point]" if nearest_support.has_swing_point else ""
            touch_info = f" [Touches: {nearest_support.touch_count}]" if nearest_support.touch_count > 0 else ""
            parts.append(f"Nearest SUPPORT: ${nearest_support.price_center:,.0f} "
                        f"({nearest_support.distance_pct:.1f}% away) "
                        f"[{nearest_support.strength}]{wall_info}{swing_info}{touch_info}")
            parts.append(f"  Zone: ${nearest_support.price_low:,.0f} - ${nearest_support.price_high:,.0f}")
            parts.append(f"  Sources: {', '.join(nearest_support.sources)}")
        else:
            parts.append("Nearest SUPPORT: None detected")

        parts.append("")

        # 其他 zones (最多显示 2 个)
        other_resistance = resistance_zones[1:3] if len(resistance_zones) > 1 else []
        other_support = support_zones[1:3] if len(support_zones) > 1 else []

        if other_resistance or other_support:
            parts.append("Other Zones:")
            for zone in other_resistance:
                extras = []
                if zone.has_swing_point:
                    extras.append("Swing")
                if zone.touch_count > 0:
                    extras.append(f"T:{zone.touch_count}")
                extra_str = f" ({', '.join(extras)})" if extras else ""
                parts.append(f"  R: ${zone.price_center:,.0f} ({zone.distance_pct:.1f}% away) [{zone.strength}]{extra_str}")
            for zone in other_support:
                extras = []
                if zone.has_swing_point:
                    extras.append("Swing")
                if zone.touch_count > 0:
                    extras.append(f"T:{zone.touch_count}")
                extra_str = f" ({', '.join(extras)})" if extras else ""
                parts.append(f"  S: ${zone.price_center:,.0f} ({zone.distance_pct:.1f}% away) [{zone.strength}]{extra_str}")

        return "\n".join(parts)

    def _empty_result(self) -> Dict[str, Any]:
        """返回空结果"""
        return {
            'support_zones': [],
            'resistance_zones': [],
            'nearest_support': None,
            'nearest_resistance': None,
            'hard_control': {
                'block_long': False,
                'block_short': False,
                'reason': None,
            },
            'ai_report': "SUPPORT/RESISTANCE ZONES: Data not available",
            'ai_detailed_report': "SUPPORT/RESISTANCE ANALYSIS: Data not available",
            'raw_data': {},
        }

    def generate_ai_detailed_report(
        self,
        current_price: float,
        bb_data: Optional[Dict[str, float]] = None,
        sma_data: Optional[Dict[str, float]] = None,
        orderbook_anomalies: Optional[Dict] = None,
        support_zones: List[SRZone] = None,
        resistance_zones: List[SRZone] = None,
        nearest_support: Optional[SRZone] = None,
        nearest_resistance: Optional[SRZone] = None,
        # v3.0: New parameter
        bars_data: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        生成详细 AI 报告 (v3.0)

        包含:
        1. 原始数据来源 (BB, SMA, Order Wall, Swing Points)
        2. 计算后的 S/R Zones (含 level/strength/source_type/touch_count)
        3. 交易建议 (供 AI 参考)
        """
        lines = []
        lines.append("=" * 70)
        lines.append("            SUPPORT/RESISTANCE ANALYSIS (v3.0)")
        lines.append("=" * 70)
        lines.append("")

        # =================================================================
        # Section 1: RAW DATA SOURCES
        # =================================================================
        lines.append("【RAW DATA SOURCES】")
        lines.append("-" * 40)

        # Technical Indicators
        lines.append("Technical Indicators:")
        if bb_data:
            bb_upper = bb_data.get('upper')
            bb_lower = bb_data.get('lower')
            bb_middle = bb_data.get('middle')
            if bb_upper:
                lines.append(f"  • BB_Upper:  ${bb_upper:,.2f}")
            if bb_middle:
                lines.append(f"  • BB_Middle: ${bb_middle:,.2f}")
            if bb_lower:
                lines.append(f"  • BB_Lower:  ${bb_lower:,.2f}")
        else:
            lines.append("  • Bollinger Bands: Not available")

        if sma_data:
            sma_50 = sma_data.get('sma_50')
            sma_200 = sma_data.get('sma_200')
            if sma_50:
                lines.append(f"  • SMA_50:    ${sma_50:,.2f}")
            if sma_200:
                lines.append(f"  • SMA_200:   ${sma_200:,.2f}")
        else:
            lines.append("  • SMA: Not available")

        lines.append("")

        # v3.0: Swing Points
        swing_count = 0
        if support_zones and resistance_zones:
            for zone in (support_zones or []) + (resistance_zones or []):
                if zone.has_swing_point:
                    swing_count += 1
        lines.append(f"Swing Points (Williams Fractal, L={self.swing_left_bars}/R={self.swing_right_bars}):")
        if bars_data and self.swing_detection_enabled:
            lines.append(f"  • Bars analyzed: {len(bars_data)}")
            lines.append(f"  • Zones with swing points: {swing_count}")
        else:
            lines.append("  • Swing detection: Not available (no bar data)")

        lines.append("")

        # Order Book Walls
        lines.append("Order Book Walls (Real-time):")
        if orderbook_anomalies:
            ask_walls = orderbook_anomalies.get('ask_anomalies', [])
            bid_walls = orderbook_anomalies.get('bid_anomalies', [])

            if ask_walls:
                lines.append("  Ask Walls (Resistance):")
                for wall in ask_walls[:5]:  # 最多显示 5 个
                    price = wall.get('price', 0)
                    size = wall.get('volume_btc', 0)
                    mult = wall.get('multiplier', 1)
                    lines.append(f"    • ${price:,.0f} ({size:.2f} BTC, {mult:.1f}x avg)")
            else:
                lines.append("  Ask Walls: None detected")

            if bid_walls:
                lines.append("  Bid Walls (Support):")
                for wall in bid_walls[:5]:
                    price = wall.get('price', 0)
                    size = wall.get('volume_btc', 0)
                    mult = wall.get('multiplier', 1)
                    lines.append(f"    • ${price:,.0f} ({size:.2f} BTC, {mult:.1f}x avg)")
            else:
                lines.append("  Bid Walls: None detected")
        else:
            lines.append("  Order Book: Not available")

        lines.append("")

        # =================================================================
        # Section 2: CALCULATED S/R ZONES
        # =================================================================
        lines.append("【CALCULATED S/R ZONES】")
        lines.append("-" * 40)

        # Resistance Zones
        if resistance_zones:
            lines.append("RESISTANCE ZONES (sorted by distance):")
            for i, zone in enumerate(resistance_zones[:4], 1):  # 最多 4 个
                marker = ">>>" if zone == nearest_resistance else "   "
                # v4.0 (§3.9): PROJECTED/CONFIRMED annotation
                proj_tag = ""
                if zone.source_type == SRSourceType.PROJECTED:
                    proj_tag = " ⚠️ PROJECTED"
                elif zone.source_type in (SRSourceType.STRUCTURAL, SRSourceType.ORDER_FLOW):
                    proj_tag = " ✅ CONFIRMED"
                lines.append(f"{marker}[R{i}] ${zone.price_center:,.0f} ({zone.distance_pct:.1f}% from current) [{zone.level}|{zone.strength}]{proj_tag}")
                lines.append(f"      Weight: {zone.total_weight} | Sources: {', '.join(zone.sources)}")
                if zone.source_type == SRSourceType.PROJECTED:
                    lines.append(f"      ⚠️ Mathematical projection, NO historical trade confirmation")
                # v3.0: Swing and touch info
                if zone.has_swing_point:
                    lines.append(f"      Swing Point: YES (structurally validated)")
                if zone.touch_count > 0:
                    touch_quality = "optimal" if zone.touch_count in self.optimal_touches else "weakening" if zone.touch_count >= self.decay_after_touches else "developing"
                    lines.append(f"      Touch Count: {zone.touch_count} ({touch_quality})")
                if zone.has_order_wall:
                    lines.append(f"      Order Wall: {zone.wall_size_btc:.2f} BTC total")
                    for wall in zone.order_walls:
                        lines.append(f"        - ${wall['price']:,.0f}: {wall['size_btc']:.2f} BTC")
                lines.append("")
        else:
            lines.append("RESISTANCE ZONES: None detected")
            lines.append("")

        # Support Zones
        if support_zones:
            lines.append("SUPPORT ZONES (sorted by distance):")
            for i, zone in enumerate(support_zones[:4], 1):
                marker = ">>>" if zone == nearest_support else "   "
                # v4.0 (§3.9): PROJECTED/CONFIRMED annotation
                proj_tag = ""
                if zone.source_type == SRSourceType.PROJECTED:
                    proj_tag = " ⚠️ PROJECTED"
                elif zone.source_type in (SRSourceType.STRUCTURAL, SRSourceType.ORDER_FLOW):
                    proj_tag = " ✅ CONFIRMED"
                lines.append(f"{marker}[S{i}] ${zone.price_center:,.0f} ({zone.distance_pct:.1f}% from current) [{zone.level}|{zone.strength}]{proj_tag}")
                lines.append(f"      Weight: {zone.total_weight} | Sources: {', '.join(zone.sources)}")
                if zone.source_type == SRSourceType.PROJECTED:
                    lines.append(f"      ⚠️ Mathematical projection, NO historical trade confirmation")
                # v3.0: Swing and touch info
                if zone.has_swing_point:
                    lines.append(f"      Swing Point: YES (structurally validated)")
                if zone.touch_count > 0:
                    touch_quality = "optimal" if zone.touch_count in self.optimal_touches else "weakening" if zone.touch_count >= self.decay_after_touches else "developing"
                    lines.append(f"      Touch Count: {zone.touch_count} ({touch_quality})")
                if zone.has_order_wall:
                    lines.append(f"      Order Wall: {zone.wall_size_btc:.2f} BTC total")
                    for wall in zone.order_walls:
                        lines.append(f"        - ${wall['price']:,.0f}: {wall['size_btc']:.2f} BTC")
                lines.append("")
        else:
            lines.append("SUPPORT ZONES: None detected")
            lines.append("")

        # =================================================================
        # Section 3: TRADING IMPLICATIONS
        # =================================================================
        lines.append("【TRADING IMPLICATIONS】")
        lines.append("-" * 40)

        # Nearest levels summary
        if nearest_resistance:
            lines.append(f"Nearest Resistance: ${nearest_resistance.price_center:,.0f} "
                        f"({nearest_resistance.distance_pct:.1f}% away)")
            lines.append(f"  → {nearest_resistance.strength} resistance zone - natural LONG take-profit level")
            lines.append(f"  → CAUTION: Entering LONG here risks rejection from this level")
            if nearest_resistance.source_type == SRSourceType.ORDER_FLOW:
                lines.append(f"  → Order flow data: {nearest_resistance.wall_size_btc:.2f} BTC wall (real-time)")
            if nearest_resistance.has_swing_point:
                lines.append(f"  → Swing Point confirmed: structurally validated resistance")
        else:
            lines.append("Nearest Resistance: Not detected (upside open)")

        lines.append("")

        if nearest_support:
            lines.append(f"Nearest Support: ${nearest_support.price_center:,.0f} "
                        f"({nearest_support.distance_pct:.1f}% away)")
            lines.append(f"  → {nearest_support.strength} support zone - IDEAL LONG entry point (bounce expected)")
            lines.append(f"  → CAUTION: Avoid SHORT here - high bounce risk will stop you out")
            if nearest_support.source_type == SRSourceType.ORDER_FLOW:
                lines.append(f"  → Order flow data: {nearest_support.wall_size_btc:.2f} BTC wall (real-time)")
            if nearest_support.has_swing_point:
                lines.append(f"  → Swing Point confirmed: structurally validated support")
        else:
            lines.append("Nearest Support: Not detected (downside open)")

        lines.append("")

        # Risk/reward context
        if nearest_support and nearest_resistance:
            total_range = nearest_resistance.price_center - nearest_support.price_center
            current_to_resistance = nearest_resistance.price_center - current_price
            current_to_support = current_price - nearest_support.price_center
            position_in_range = (current_price - nearest_support.price_center) / total_range * 100 if total_range > 0 else 50

            lines.append("Range Analysis:")
            lines.append(f"  • Price Range: ${nearest_support.price_center:,.0f} - ${nearest_resistance.price_center:,.0f}")
            lines.append(f"  • Current Position: {position_in_range:.0f}% from support to resistance")
            lines.append(f"  • Upside Potential: ${current_to_resistance:,.0f} ({nearest_resistance.distance_pct:.1f}%)")
            lines.append(f"  • Downside Risk: ${current_to_support:,.0f} ({nearest_support.distance_pct:.1f}%)")

            # Risk/reward ratio with guidance
            if current_to_support > 0:
                rr_ratio = current_to_resistance / current_to_support
                rr_status = "✅ FAVORABLE" if rr_ratio >= 1.5 else "⚠️ UNFAVORABLE"
                lines.append(f"  • LONG R/R Ratio: {rr_ratio:.2f}:1 {rr_status}")
                if rr_ratio < 1.5:
                    lines.append(f"    → LONG entry NOT recommended here (R/R < 1.5:1)")
            if current_to_resistance > 0:
                rr_ratio_short = current_to_support / current_to_resistance
                rr_status = "✅ FAVORABLE" if rr_ratio_short >= 1.5 else "⚠️ UNFAVORABLE"
                lines.append(f"  • SHORT R/R Ratio: {rr_ratio_short:.2f}:1 {rr_status}")
                if rr_ratio_short < 1.5:
                    lines.append(f"    → SHORT entry NOT recommended here (R/R < 1.5:1)")

        lines.append("")
        lines.append("=" * 70)
        lines.append("NOTE: ✅ CONFIRMED = STRUCTURAL (Swing Points) or ORDER_FLOW (real-time order book).")
        lines.append("⚠️ PROJECTED = mathematical projection (Pivot Points), NO historical confirmation.")
        lines.append("TECHNICAL = SMA/BB indicators. PSYCHOLOGICAL = round number levels.")
        lines.append("Zones with multiple sources and 2-3 touches are the strongest.")
        lines.append("=" * 70)

        return "\n".join(lines)

    def calculate_with_detailed_report(
        self,
        current_price: float,
        bb_data: Optional[Dict[str, float]] = None,
        sma_data: Optional[Dict[str, float]] = None,
        orderbook_anomalies: Optional[Dict] = None,
        # v3.0: New parameters
        bars_data: Optional[List[Dict[str, Any]]] = None,
        atr_value: Optional[float] = None,
        # v4.0: MTF bars
        bars_data_4h: Optional[List[Dict[str, Any]]] = None,
        bars_data_1d: Optional[List[Dict[str, Any]]] = None,
        daily_bar: Optional[Dict[str, Any]] = None,
        weekly_bar: Optional[Dict[str, Any]] = None,
        **kwargs,  # v4.0: absorbs old pivot_data from legacy callers
    ) -> Dict[str, Any]:
        """
        计算 S/R Zones 并生成详细 AI 报告 (v3.0, v4.0 MTF)

        这是 calculate() 的增强版，额外返回:
        - ai_detailed_report: 详细报告供 AI 验证
        - raw_data: 原始数据供调试
        """
        # 先调用标准计算
        result = self.calculate(
            current_price=current_price,
            bb_data=bb_data,
            sma_data=sma_data,
            orderbook_anomalies=orderbook_anomalies,
            bars_data=bars_data,
            atr_value=atr_value,
            bars_data_4h=bars_data_4h,
            bars_data_1d=bars_data_1d,
            daily_bar=daily_bar,
            weekly_bar=weekly_bar,
        )

        # 生成详细报告
        result['ai_detailed_report'] = self.generate_ai_detailed_report(
            current_price=current_price,
            bb_data=bb_data,
            sma_data=sma_data,
            orderbook_anomalies=orderbook_anomalies,
            support_zones=result['support_zones'],
            resistance_zones=result['resistance_zones'],
            nearest_support=result['nearest_support'],
            nearest_resistance=result['nearest_resistance'],
            bars_data=bars_data,
        )

        # 存储原始数据供调试
        result['raw_data'] = {
            'current_price': current_price,
            'bb_data': bb_data,
            'sma_data': sma_data,
            'orderbook_anomalies': orderbook_anomalies,
            'bars_count': len(bars_data) if bars_data else 0,
            'bars_count_4h': len(bars_data_4h) if bars_data_4h else 0,
            'bars_count_1d': len(bars_data_1d) if bars_data_1d else 0,
            'atr_value': atr_value,
        }

        return result
