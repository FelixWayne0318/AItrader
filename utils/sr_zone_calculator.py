# utils/sr_zone_calculator.py
"""
Support/Resistance Zone Calculator v1.0

职责:
- 聚合多个数据源的 S/R 候选价位
- 聚类形成 S/R Zone (价差 < cluster_pct 的合并)
- 计算 Zone 强度 (基于 confluence)
- 输出给 AI 和本地硬风控使用

设计原则:
- 只做预处理，不做交易判断
- 输出结构化数据，让 AI 解读
- 硬风控只在 HIGH strength 时介入

参考:
- QuantStrategy.io: Order Book Depth Analysis
- Analyzing Alpha: Support and Resistance
- TradingAgents: Local preprocessing + AI decision

Author: AItrader Team
Date: 2026-01
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class SRCandidate:
    """S/R 候选价位"""
    price: float
    source: str          # 来源: BB_Lower, BB_Upper, SMA_50, SMA_200, Order_Wall
    weight: float        # 权重: Order_Wall=2.0, SMA_200=1.5, BB=1.0, SMA_50=0.8
    side: str            # support 或 resistance
    extra: Dict = field(default_factory=dict)  # 额外信息 (如 wall size)


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
        """收集所有 S/R 候选价位"""
        candidates = []

        # Bollinger Bands
        if bb_data:
            bb_upper = bb_data.get('upper')
            bb_lower = bb_data.get('lower')

            if bb_upper and bb_upper > current_price:
                candidates.append(SRCandidate(
                    price=bb_upper,
                    source='BB_Upper',
                    weight=self.WEIGHTS['BB_Upper'],
                    side='resistance'
                ))

            if bb_lower and bb_lower < current_price:
                candidates.append(SRCandidate(
                    price=bb_lower,
                    source='BB_Lower',
                    weight=self.WEIGHTS['BB_Lower'],
                    side='support'
                ))

        # SMA
        if sma_data:
            sma_50 = sma_data.get('sma_50')
            sma_200 = sma_data.get('sma_200')

            if sma_50 and sma_50 > 0:
                side = 'support' if sma_50 < current_price else 'resistance'
                candidates.append(SRCandidate(
                    price=sma_50,
                    source='SMA_50',
                    weight=self.WEIGHTS['SMA_50'],
                    side=side
                ))

            if sma_200 and sma_200 > 0:
                side = 'support' if sma_200 < current_price else 'resistance'
                candidates.append(SRCandidate(
                    price=sma_200,
                    source='SMA_200',
                    weight=self.WEIGHTS['SMA_200'],
                    side=side
                ))

        # Order Book Walls (最重要)
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
                        }
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
                        }
                    ))

        # Pivot Points (可选)
        if pivot_data:
            for key, price in pivot_data.items():
                if price and price > 0:
                    if 's' in key.lower():  # s1, s2, s3 = support
                        candidates.append(SRCandidate(
                            price=price,
                            source=f"Pivot_{key.upper()}",
                            weight=self.WEIGHTS['Pivot'],
                            side='support'
                        ))
                    elif 'r' in key.lower():  # r1, r2, r3 = resistance
                        candidates.append(SRCandidate(
                            price=price,
                            source=f"Pivot_{key.upper()}",
                            weight=self.WEIGHTS['Pivot'],
                            side='resistance'
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
        """从候选 cluster 创建 Zone"""
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
        }
