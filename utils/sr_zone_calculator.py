# utils/sr_zone_calculator.py
"""
Support/Resistance Zone Calculator v2.0

职责:
- 聚合多个数据源的 S/R 候选价位
- 聚类形成 S/R Zone (价差 < cluster_pct 的合并)
- 计算 Zone 强度 (基于 confluence)
- 输出给 AI 和本地硬风控使用
- v2.0: 添加 level (时间框架级别) 和 source_type (来源类型)
- v2.0: 添加详细 AI 报告，包含原始数据供 AI 验证

设计原则:
- 只做预处理，不做交易判断
- 输出结构化数据，让 AI 解读
- 硬风控只在 HIGH strength 时介入
- v2.0: 传递原始数据让 AI 可以验证计算结果

参考:
- QuantStrategy.io: Order Book Depth Analysis
- Analyzing Alpha: Support and Resistance
- TradingAgents: Local preprocessing + AI decision

Author: AItrader Team
Date: 2026-01
Version: 2.0
"""

import logging
from typing import List, Dict, Any, Optional
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
    ORDER_FLOW = "ORDER_FLOW"     # 订单流 (Order Wall) - 最实时
    TECHNICAL = "TECHNICAL"       # 技术指标 (SMA, BB) - 广泛认可
    STRUCTURAL = "STRUCTURAL"     # 结构性 (前高/前低, Pivot) - 历史验证


@dataclass
class SRCandidate:
    """S/R 候选价位"""
    price: float
    source: str          # 来源: BB_Lower, BB_Upper, SMA_50, SMA_200, Order_Wall
    weight: float        # 权重: Order_Wall=2.0, SMA_200=1.5, BB=1.0, SMA_50=0.8
    side: str            # support 或 resistance
    extra: Dict = field(default_factory=dict)  # 额外信息 (如 wall size)
    # v2.0 新增
    level: str = SRLevel.MINOR           # 时间框架级别
    source_type: str = SRSourceType.TECHNICAL  # 来源类型


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


class SRZoneCalculator:
    """
    S/R Zone 计算器

    使用方法:
    ```python
    calculator = SRZoneCalculator()
    result = calculator.calculate(
        current_price=100000,
        bb_data={'upper': 101500, 'lower': 98500, 'middle': 100000},
        sma_data={'sma_50': 99000, 'sma_200': 95000},
        orderbook_anomalies={'bid_anomalies': [...], 'ask_anomalies': [...]}
    )

    # 输出给 AI
    ai_report = result['ai_report']

    # 硬风控检查
    if result['hard_control']['block_long']:
        # 阻止 LONG
    ```
    """

    # 权重配置
    WEIGHTS = {
        'Order_Wall': 2.0,      # 订单簿大单 (最重要)
        'SMA_200': 1.5,         # 长期趋势
        'BB_Upper': 1.0,        # 布林带
        'BB_Lower': 1.0,
        'SMA_50': 0.8,          # 中期趋势
        'Pivot': 0.7,           # Pivot Points (可选)
    }

    # 强度阈值
    STRENGTH_THRESHOLDS = {
        'HIGH': 3.0,            # 总权重 >= 3.0 或有 Order Wall
        'MEDIUM': 1.5,          # 总权重 >= 1.5
        'LOW': 0.0,             # 其他
    }

    def __init__(
        self,
        cluster_pct: float = 0.5,       # 聚类阈值 (价差 < 0.5% 合并)
        zone_expand_pct: float = 0.1,   # Zone 扩展 (上下各 0.1%)
        hard_control_threshold_pct: float = 1.0,  # 硬风控阈值 (距离 < 1%)
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
        logger : logging.Logger
            日志记录器
        """
        self.cluster_pct = cluster_pct
        self.zone_expand_pct = zone_expand_pct
        self.hard_control_threshold_pct = hard_control_threshold_pct
        self.logger = logger or logging.getLogger(__name__)

    def calculate(
        self,
        current_price: float,
        bb_data: Optional[Dict[str, float]] = None,
        sma_data: Optional[Dict[str, float]] = None,
        orderbook_anomalies: Optional[Dict] = None,
        pivot_data: Optional[Dict[str, float]] = None,
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
        pivot_data : Dict, optional
            Pivot Points {'r1': float, 's1': float, ...}

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

        # Step 1: 收集所有候选
        candidates = self._collect_candidates(
            current_price, bb_data, sma_data, orderbook_anomalies, pivot_data
        )

        if not candidates:
            return self._empty_result()

        # Step 2: 分离 support 和 resistance
        support_candidates = [c for c in candidates if c.side == 'support']
        resistance_candidates = [c for c in candidates if c.side == 'resistance']

        # Step 3: 聚类形成 Zones
        support_zones = self._cluster_to_zones(support_candidates, current_price, 'support')
        resistance_zones = self._cluster_to_zones(resistance_candidates, current_price, 'resistance')

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

    def _collect_candidates(
        self,
        current_price: float,
        bb_data: Optional[Dict],
        sma_data: Optional[Dict],
        orderbook_anomalies: Optional[Dict],
        pivot_data: Optional[Dict],
    ) -> List[SRCandidate]:
        """收集所有 S/R 候选价位 (v2.0: 添加 level 和 source_type)"""
        candidates = []

        # Bollinger Bands (15M = MINOR level)
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
                ))

            if bb_lower and bb_lower < current_price:
                candidates.append(SRCandidate(
                    price=bb_lower,
                    source='BB_Lower',
                    weight=self.WEIGHTS['BB_Lower'],
                    side='support',
                    level=SRLevel.MINOR,
                    source_type=SRSourceType.TECHNICAL,
                ))

        # SMA (SMA_50 = INTERMEDIATE, SMA_200 = MAJOR)
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
                ))

            if sma_200 and sma_200 > 0:
                side = 'support' if sma_200 < current_price else 'resistance'
                candidates.append(SRCandidate(
                    price=sma_200,
                    source='SMA_200',
                    weight=self.WEIGHTS['SMA_200'],
                    side=side,
                    level=SRLevel.MAJOR,
                    source_type=SRSourceType.TECHNICAL,
                ))

        # Order Book Walls (MINOR level, ORDER_FLOW type - 最实时)
        if orderbook_anomalies:
            # Bid walls = Support
            for wall in orderbook_anomalies.get('bid_anomalies', []):
                if wall.get('price', 0) < current_price:
                    candidates.append(SRCandidate(
                        price=wall['price'],
                        source=f"Order_Wall_${wall['price']:.0f}",
                        weight=self.WEIGHTS['Order_Wall'],
                        side='support',
                        extra={
                            'size_btc': wall.get('volume_btc', 0),
                            'multiplier': wall.get('multiplier', 1),
                        },
                        level=SRLevel.MINOR,
                        source_type=SRSourceType.ORDER_FLOW,
                    ))

            # Ask walls = Resistance
            for wall in orderbook_anomalies.get('ask_anomalies', []):
                if wall.get('price', 0) > current_price:
                    candidates.append(SRCandidate(
                        price=wall['price'],
                        source=f"Order_Wall_${wall['price']:.0f}",
                        weight=self.WEIGHTS['Order_Wall'],
                        side='resistance',
                        extra={
                            'size_btc': wall.get('volume_btc', 0),
                            'multiplier': wall.get('multiplier', 1),
                        },
                        level=SRLevel.MINOR,
                        source_type=SRSourceType.ORDER_FLOW,
                    ))

        # Pivot Points (STRUCTURAL type)
        if pivot_data:
            for key, price in pivot_data.items():
                if price and price > 0:
                    if 's' in key.lower():  # s1, s2, s3 = support
                        candidates.append(SRCandidate(
                            price=price,
                            source=f"Pivot_{key.upper()}",
                            weight=self.WEIGHTS['Pivot'],
                            side='support',
                            level=SRLevel.INTERMEDIATE,
                            source_type=SRSourceType.STRUCTURAL,
                        ))
                    elif 'r' in key.lower():  # r1, r2, r3 = resistance
                        candidates.append(SRCandidate(
                            price=price,
                            source=f"Pivot_{key.upper()}",
                            weight=self.WEIGHTS['Pivot'],
                            side='resistance',
                            level=SRLevel.INTERMEDIATE,
                            source_type=SRSourceType.STRUCTURAL,
                        ))

        return candidates

    def _cluster_to_zones(
        self,
        candidates: List[SRCandidate],
        current_price: float,
        side: str,
    ) -> List[SRZone]:
        """将候选聚类为 Zones"""
        if not candidates:
            return []

        # 按价格排序
        candidates.sort(key=lambda c: c.price)

        zones = []
        current_cluster = [candidates[0]]

        for i in range(1, len(candidates)):
            candidate = candidates[i]
            last_price = current_cluster[-1].price

            # 计算价差百分比
            price_diff_pct = abs(candidate.price - last_price) / last_price * 100

            if price_diff_pct <= self.cluster_pct:
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
        """从候选 cluster 创建 Zone (v2.0: 添加 level/source_type/order_walls)"""
        prices = [c.price for c in cluster]
        price_center = sum(prices) / len(prices)

        # Zone 边界 (扩展)
        expand = price_center * self.zone_expand_pct / 100
        price_low = min(prices) - expand
        price_high = max(prices) + expand

        # 来源列表
        sources = [c.source for c in cluster]

        # 总权重
        total_weight = sum(c.weight for c in cluster)

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

        # 计算强度
        if has_order_wall or total_weight >= self.STRENGTH_THRESHOLDS['HIGH']:
            strength = 'HIGH'
        elif total_weight >= self.STRENGTH_THRESHOLDS['MEDIUM']:
            strength = 'MEDIUM'
        else:
            strength = 'LOW'

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

        # v2.0: 确定主要来源类型 (ORDER_FLOW > TECHNICAL > STRUCTURAL)
        type_priority = {
            SRSourceType.ORDER_FLOW: 3,
            SRSourceType.TECHNICAL: 2,
            SRSourceType.STRUCTURAL: 1,
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
        """生成 AI 报告"""
        parts = ["SUPPORT/RESISTANCE ZONES:"]
        parts.append("")

        # 最近阻力
        if nearest_resistance:
            wall_info = f" [Order Wall: {nearest_resistance.wall_size_btc:.1f} BTC]" if nearest_resistance.has_order_wall else ""
            parts.append(f"Nearest RESISTANCE: ${nearest_resistance.price_center:,.0f} "
                        f"({nearest_resistance.distance_pct:.1f}% away) "
                        f"[{nearest_resistance.strength}]{wall_info}")
            parts.append(f"  Zone: ${nearest_resistance.price_low:,.0f} - ${nearest_resistance.price_high:,.0f}")
            parts.append(f"  Sources: {', '.join(nearest_resistance.sources)}")
        else:
            parts.append("Nearest RESISTANCE: None detected")

        parts.append("")

        # 最近支撑
        if nearest_support:
            wall_info = f" [Order Wall: {nearest_support.wall_size_btc:.1f} BTC]" if nearest_support.has_order_wall else ""
            parts.append(f"Nearest SUPPORT: ${nearest_support.price_center:,.0f} "
                        f"({nearest_support.distance_pct:.1f}% away) "
                        f"[{nearest_support.strength}]{wall_info}")
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
                parts.append(f"  R: ${zone.price_center:,.0f} ({zone.distance_pct:.1f}% away) [{zone.strength}]")
            for zone in other_support:
                parts.append(f"  S: ${zone.price_center:,.0f} ({zone.distance_pct:.1f}% away) [{zone.strength}]")

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
    ) -> str:
        """
        生成详细 AI 报告 (v2.0)

        包含:
        1. 原始数据来源 (BB, SMA, Order Wall)
        2. 计算后的 S/R Zones (含 level/strength/source_type)
        3. 交易建议 (供 AI 参考)

        Parameters
        ----------
        current_price : float
            当前价格
        bb_data : Dict, optional
            布林带原始数据
        sma_data : Dict, optional
            SMA 原始数据
        orderbook_anomalies : Dict, optional
            订单簿大单数据
        support_zones : List[SRZone]
            计算后的支撑区
        resistance_zones : List[SRZone]
            计算后的阻力区
        nearest_support : SRZone, optional
            最近支撑
        nearest_resistance : SRZone, optional
            最近阻力

        Returns
        -------
        str
            格式化的详细报告
        """
        lines = []
        lines.append("=" * 70)
        lines.append("            SUPPORT/RESISTANCE ANALYSIS (v2.0)")
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
                lines.append(f"{marker}[R{i}] ${zone.price_center:,.0f} ({zone.distance_pct:.1f}% from current)")
                lines.append(f"      Level: {zone.level} | Strength: {zone.strength} (weight: {zone.total_weight})")
                lines.append(f"      Sources: {', '.join(zone.sources)}")
                lines.append(f"      Type: {zone.source_type}")
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
                lines.append(f"{marker}[S{i}] ${zone.price_center:,.0f} ({zone.distance_pct:.1f}% from current)")
                lines.append(f"      Level: {zone.level} | Strength: {zone.strength} (weight: {zone.total_weight})")
                lines.append(f"      Sources: {', '.join(zone.sources)}")
                lines.append(f"      Type: {zone.source_type}")
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
            lines.append(f"  → LONG entries face {nearest_resistance.strength} resistance here")
            if nearest_resistance.source_type == SRSourceType.ORDER_FLOW:
                lines.append(f"  → Order flow data: {nearest_resistance.wall_size_btc:.2f} BTC wall (real-time)")
            lines.append(f"  → Consider this level for LONG take-profit")
        else:
            lines.append("Nearest Resistance: Not detected (upside open)")

        lines.append("")

        if nearest_support:
            lines.append(f"Nearest Support: ${nearest_support.price_center:,.0f} "
                        f"({nearest_support.distance_pct:.1f}% away)")
            lines.append(f"  → SHORT entries face {nearest_support.strength} support here")
            if nearest_support.source_type == SRSourceType.ORDER_FLOW:
                lines.append(f"  → Order flow data: {nearest_support.wall_size_btc:.2f} BTC wall (real-time)")
            lines.append(f"  → Consider this level for SHORT take-profit")
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

            # Risk/reward ratio
            if current_to_support > 0:
                rr_ratio = current_to_resistance / current_to_support
                lines.append(f"  • LONG R/R Ratio: {rr_ratio:.2f}")
            if current_to_resistance > 0:
                rr_ratio_short = current_to_support / current_to_resistance
                lines.append(f"  • SHORT R/R Ratio: {rr_ratio_short:.2f}")

        lines.append("")
        lines.append("=" * 70)
        lines.append("NOTE: ORDER_FLOW data reflects real-time order book. TECHNICAL data")
        lines.append("reflects calculated indicators. Use both for comprehensive analysis.")
        lines.append("=" * 70)

        return "\n".join(lines)

    def calculate_with_detailed_report(
        self,
        current_price: float,
        bb_data: Optional[Dict[str, float]] = None,
        sma_data: Optional[Dict[str, float]] = None,
        orderbook_anomalies: Optional[Dict] = None,
        pivot_data: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        计算 S/R Zones 并生成详细 AI 报告 (v2.0)

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
            pivot_data=pivot_data,
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
        )

        # 存储原始数据供调试
        result['raw_data'] = {
            'current_price': current_price,
            'bb_data': bb_data,
            'sma_data': sma_data,
            'orderbook_anomalies': orderbook_anomalies,
            'pivot_data': pivot_data,
        }

        return result
