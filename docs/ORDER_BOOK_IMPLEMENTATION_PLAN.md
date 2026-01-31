# BinanceOrderBookClient 实施方案

> 版本: v2.0
> 日期: 2026-01-31
> 状态: 已评估，待实施
> 评估得分: 7.49/10 → 修订后预期 9.0/10

---

## 修订记录

| 版本 | 日期 | 修改内容 |
|------|------|----------|
| v1.0 | 2026-01-31 | 初始方案 |
| v2.0 | 2026-01-31 | 基于量化专家评估，添加 Critical 和 Recommended 改进 |

### v2.0 主要改进

| 类型 | 改进项 | 说明 |
|------|--------|------|
| **Critical** | 订单簿变化率指标 | 新增 `dynamics` 段，追踪 OBI/深度变化趋势 |
| **Critical** | 默认值策略优化 | 使用 `"status": "NO_DATA"` 明确标记，避免 AI 误判 |
| **Recommended** | 加权 OBI 可配置化 | 支持自适应衰减，基于波动率调整 |
| **Recommended** | 动态异常阈值 | 基于近期波动率自动调整阈值 |
| **Recommended** | Book Pressure Gradient | 新增近档/远档压力梯度指标 |
| **Recommended** | 滑点不确定性 | 滑点估算加入置信度和范围 |

---

## 1. 概述

### 1.1 目标

为 AI 交易系统增加**订单簿深度数据**，遵循 TradingAgents 哲学：
- **本地只做预处理**：计算 OBI、深度分布、滑点等原始指标
- **AI 做所有决策**：不在本地判断支撑/阻力，让 AI 自行解读

### 1.2 数据利用率目标

| 维度 | 当前 | 新增后 |
|------|------|--------|
| 订单簿深度 | 0% | 100% |
| 整体数据利用率 | 86% | 95%+ |

### 1.3 核心指标 (v2.0 更新)

| 指标 | 类型 | 说明 | 版本 |
|------|------|------|------|
| **OBI** (Order Book Imbalance) | 不平衡 | 买卖压力对比 | v1.0 |
| **加权 OBI** | 不平衡 | 靠近盘口的订单权重更高 | v1.0 |
| **自适应加权 OBI** | 不平衡 | 基于波动率动态调整衰减因子 | ⭐ v2.0 |
| **深度分布** | 分布 | 按价格带聚合的挂单量 | v1.0 |
| **Pressure Gradient** | 分布 | 近档/远档压力梯度 | ⭐ v2.0 |
| **动态异常检测** | 分布 | 基于波动率自适应阈值 | ⭐ v2.0 |
| **滑点估算 (含置信度)** | 流动性 | 执行 N BTC 的预期滑点 + 不确定性 | ⭐ v2.0 |
| **价差** | 流动性 | 买一/卖一价差 | v1.0 |
| **变化率指标** | 动态 | OBI/深度的变化趋势 | ⭐ v2.0 Critical |

---

## 2. 架构设计

### 2.1 数据流全景 (v2.0 更新)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         数据流全景图 v2.0                                │
└─────────────────────────────────────────────────────────────────────────┘

  Binance REST API                    本地处理                     AI 分析
  (/fapi/v1/depth)
        │                                │                            │
        ▼                                ▼                            ▼
┌───────────────┐              ┌─────────────────┐          ┌──────────────┐
│ 原始订单簿     │    HTTP      │ BinanceOrder    │  格式化   │ DeepSeek     │
│ {bids, asks}  │────────────▶ │ BookClient      │────────▶ │ Multi-Agent  │
│ limit=100     │              │                 │          │              │
└───────────────┘              └─────────────────┘          └──────────────┘
                                       │
                                       │ 预处理
                                       ▼
                               ┌─────────────────┐
                               │ OrderBook       │
                               │ Processor       │
                               │ (计算指标)       │
                               │                 │
                               │ ⭐ v2.0 新增:    │
                               │ - 历史缓存      │
                               │ - 变化率计算    │
                               │ - 动态阈值      │
                               └─────────────────┘
                                       │
                                       │ 组装
                                       ▼
                               ┌─────────────────┐
                               │ AIData          │
                               │ Assembler       │
                               │ (数据聚合)       │
                               └─────────────────┘
                                       │
                                       │ format_for_ai()
                                       ▼
                               ┌─────────────────┐
                               │ 格式化文本       │
                               │ (传给 AI)       │
                               │                 │
                               │ ⭐ v2.0 新增:    │
                               │ - 变化率段落    │
                               │ - 数据状态标记  │
                               └─────────────────┘
```

### 2.2 组件职责

| 组件 | 文件 | 职责 |
|------|------|------|
| **BinanceOrderBookClient** | `utils/binance_orderbook_client.py` | API 调用、原始数据获取 |
| **OrderBookProcessor** | `utils/orderbook_processor.py` | 指标计算 (OBI, 滑点等) + ⭐历史缓存 |
| **AIDataAssembler** | `utils/ai_data_assembler.py` | 集成订单簿数据 |
| **ConfigManager** | `configs/base.yaml` | 配置参数 |

### 2.3 与现有组件对比

| 组件 | 数据源 | 处理器 | 对应关系 |
|------|--------|--------|----------|
| K线数据 | BinanceKlineClient | OrderFlowProcessor | 参考模板 |
| 衍生品 | CoinalyzeClient | (内置) | 参考模板 |
| **订单簿** | **BinanceOrderBookClient** | **OrderBookProcessor** | **新增** |

---

## 3. 详细设计

### 3.1 BinanceOrderBookClient

```python
# utils/binance_orderbook_client.py

class BinanceOrderBookClient:
    """
    Binance 订单簿客户端

    功能:
    - 获取订单簿深度数据 (/fapi/v1/depth)
    - 支持重试和降级
    - 遵循现有客户端模式

    注意: 此接口无需 API Key，是公开数据
    """

    BASE_URL = "https://fapi.binance.com"

    def __init__(
        self,
        timeout: int = 10,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        logger: logging.Logger = None,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = logger or logging.getLogger(__name__)

    def get_order_book(
        self,
        symbol: str = "BTCUSDT",
        limit: int = 100,  # 5, 10, 20, 50, 100, 500, 1000
    ) -> Optional[Dict]:
        """
        获取订单簿深度

        Returns
        -------
        {
            "lastUpdateId": 160,
            "E": 1499404346076,        # 消息时间
            "T": 1499404346076,        # 撮合引擎时间
            "bids": [
                ["4.00000000", "431.00000000"],  # [价格, 数量]
                ...
            ],
            "asks": [
                ["4.00000200", "12.00000000"],
                ...
            ]
        }
        """
        # 实现带重试的 HTTP 请求
        pass
```

### 3.2 OrderBookProcessor (v2.0 重大更新)

```python
# utils/orderbook_processor.py

class OrderBookProcessor:
    """
    订单簿数据处理器 v2.0

    职责:
    - 计算 OBI (Order Book Imbalance)
    - 计算加权 OBI (靠近盘口权重更高)
    - ⭐ v2.0: 自适应加权 OBI (基于波动率)
    - 计算深度分布 (按价格带聚合)
    - ⭐ v2.0: Book Pressure Gradient
    - ⭐ v2.0: 动态异常检测阈值
    - 估算滑点
    - ⭐ v2.0: 滑点置信度和范围
    - ⭐ v2.0: 变化率计算 (Critical)

    设计原则:
    - 只做预处理，不做判断
    - 输出原始指标，让 AI 解读
    - ⭐ v2.0: 明确标记数据状态
    """

    def __init__(
        self,
        price_band_pct: float = 0.5,
        base_anomaly_threshold: float = 3.0,      # 基础阈值
        slippage_amounts: List[float] = [0.1, 0.5, 1.0],
        # ⭐ v2.0: 加权 OBI 可配置化
        weighted_obi_config: Dict = None,
        # ⭐ v2.0: 历史缓存大小
        history_size: int = 10,
        logger: logging.Logger = None,
    ):
        self.price_band_pct = price_band_pct
        self.base_anomaly_threshold = base_anomaly_threshold
        self.slippage_amounts = slippage_amounts
        self.logger = logger or logging.getLogger(__name__)

        # ⭐ v2.0: 加权 OBI 配置
        self.weighted_obi_config = weighted_obi_config or {
            "base_decay": 0.8,
            "adaptive": True,
            "volatility_factor": 0.1,
            "min_decay": 0.5,
            "max_decay": 0.95,
        }

        # ⭐ v2.0: 历史数据缓存 (用于计算变化率)
        self._history: List[Dict] = []
        self._history_size = history_size

    def process(
        self,
        order_book: Dict,
        current_price: float,
        volatility: float = None,  # ⭐ v2.0: 可选，用于自适应调整
    ) -> Dict[str, Any]:
        """
        处理订单簿数据

        Returns
        -------
        {
            # =========================================================
            # 基础不平衡指标
            # =========================================================
            "obi": {
                "simple": 0.15,
                "weighted": 0.12,
                "adaptive_weighted": 0.13,        # ⭐ v2.0
                "decay_used": 0.75,               # ⭐ v2.0: 实际使用的衰减因子
                "bid_volume_btc": 520.5,
                "ask_volume_btc": 450.2,
                "bid_volume_usd": 45000000,
                "ask_volume_usd": 39000000,
            },

            # =========================================================
            # ⭐ v2.0 Critical: 变化率指标
            # =========================================================
            "dynamics": {
                "obi_change": 0.05,               # OBI 相比上次的变化
                "obi_change_pct": 33.3,           # OBI 变化百分比
                "bid_depth_change_pct": -2.3,     # 买盘深度变化 (%)
                "ask_depth_change_pct": +1.8,     # 卖盘深度变化 (%)
                "spread_change_pct": -5.0,        # 价差变化 (%)
                "samples_count": 5,               # 历史样本数
                "trend": "BID_WEAKENING",         # 趋势描述 (仅描述，不判断)
            },

            # =========================================================
            # ⭐ v2.0: Pressure Gradient
            # =========================================================
            "pressure_gradient": {
                "bid_near_5": 0.35,               # 前5档占总买单的比例
                "bid_near_10": 0.55,              # 前10档占比
                "bid_near_20": 0.72,              # 前20档占比
                "ask_near_5": 0.28,
                "ask_near_10": 0.48,
                "ask_near_20": 0.68,
                "bid_concentration": "HIGH",      # 买单集中度 (描述)
                "ask_concentration": "MEDIUM",    # 卖单集中度 (描述)
            },

            # =========================================================
            # 深度分布 (按价格带)
            # =========================================================
            "depth_distribution": {
                "bands": [
                    {"range": "-1.5% ~ -1.0%", "side": "bid", "volume_usd": 2800000},
                    {"range": "-1.0% ~ -0.5%", "side": "bid", "volume_usd": 3200000},
                    {"range": "-0.5% ~ 0%", "side": "bid", "volume_usd": 5100000},
                    {"range": "0% ~ +0.5%", "side": "ask", "volume_usd": 4800000},
                    {"range": "+0.5% ~ +1.0%", "side": "ask", "volume_usd": 3500000},
                    {"range": "+1.0% ~ +1.5%", "side": "ask", "volume_usd": 2100000},
                ],
                "bid_depth_usd": 11100000,
                "ask_depth_usd": 10400000,
            },

            # =========================================================
            # ⭐ v2.0: 动态异常检测
            # =========================================================
            "anomalies": {
                "threshold_used": 2.8,            # 实际使用的阈值 (动态)
                "threshold_reason": "high_volatility",  # 阈值调整原因
                "bid_anomalies": [
                    {"price": 82000, "volume_btc": 280, "multiplier": 5.6},
                ],
                "ask_anomalies": [
                    {"price": 85000, "volume_btc": 350, "multiplier": 7.0},
                ],
                "has_significant": True,
            },

            # =========================================================
            # ⭐ v2.0: 滑点估算 (含不确定性)
            # =========================================================
            "liquidity": {
                "slippage": {
                    "buy_0.1_btc": {
                        "estimated": 0.02,
                        "confidence": 0.9,        # 置信度
                        "range": [0.01, 0.03],    # 可能范围
                    },
                    "buy_0.5_btc": {
                        "estimated": 0.05,
                        "confidence": 0.8,
                        "range": [0.03, 0.08],
                    },
                    "buy_1.0_btc": {
                        "estimated": 0.08,
                        "confidence": 0.7,
                        "range": [0.05, 0.12],
                    },
                    "sell_0.1_btc": {...},
                    "sell_0.5_btc": {...},
                    "sell_1.0_btc": {...},
                },
                "spread_pct": 0.02,
                "spread_usd": 18.5,
                "mid_price": 86250.5,
            },

            # =========================================================
            # ⭐ v2.0 Critical: 数据状态标记
            # =========================================================
            "_status": {
                "code": "OK",                     # OK / PARTIAL / NO_DATA
                "message": "Full data available",
                "timestamp": 1706745600000,
                "levels_analyzed": 100,
                "price_used": 86250.0,
                "history_samples": 5,
            },
        }
        """
        pass

    # =========================================================================
    # ⭐ v2.0 新增方法
    # =========================================================================

    def _calculate_adaptive_decay(self, volatility: float) -> float:
        """
        计算自适应衰减因子

        高波动时: 降低衰减 (更关注盘口)
        低波动时: 提高衰减 (更多考虑远档)

        Formula:
            decay = base_decay - volatility * volatility_factor
            decay = clamp(decay, min_decay, max_decay)
        """
        config = self.weighted_obi_config
        if not config.get("adaptive") or volatility is None:
            return config["base_decay"]

        decay = config["base_decay"] - volatility * config["volatility_factor"]
        return max(config["min_decay"], min(config["max_decay"], decay))

    def _calculate_dynamics(self, current_data: Dict) -> Dict:
        """
        计算变化率指标 (Critical v2.0)

        比较当前数据与历史数据，计算:
        - OBI 变化
        - 深度变化
        - 价差变化
        """
        if len(self._history) == 0:
            return {
                "obi_change": None,
                "obi_change_pct": None,
                "bid_depth_change_pct": None,
                "ask_depth_change_pct": None,
                "spread_change_pct": None,
                "samples_count": 0,
                "trend": "INSUFFICIENT_DATA",
            }

        prev = self._history[-1]
        curr_obi = current_data["obi"]["simple"]
        prev_obi = prev["obi"]["simple"]

        obi_change = curr_obi - prev_obi
        obi_change_pct = (obi_change / abs(prev_obi) * 100) if prev_obi != 0 else None

        curr_bid = current_data["depth_distribution"]["bid_depth_usd"]
        prev_bid = prev["depth_distribution"]["bid_depth_usd"]
        bid_change = ((curr_bid - prev_bid) / prev_bid * 100) if prev_bid > 0 else None

        curr_ask = current_data["depth_distribution"]["ask_depth_usd"]
        prev_ask = prev["depth_distribution"]["ask_depth_usd"]
        ask_change = ((curr_ask - prev_ask) / prev_ask * 100) if prev_ask > 0 else None

        curr_spread = current_data["liquidity"]["spread_pct"]
        prev_spread = prev["liquidity"]["spread_pct"]
        spread_change = ((curr_spread - prev_spread) / prev_spread * 100) if prev_spread > 0 else None

        # 趋势描述 (不做判断，只描述现象)
        trend = self._describe_trend(obi_change, bid_change, ask_change)

        return {
            "obi_change": round(obi_change, 4) if obi_change else None,
            "obi_change_pct": round(obi_change_pct, 2) if obi_change_pct else None,
            "bid_depth_change_pct": round(bid_change, 2) if bid_change else None,
            "ask_depth_change_pct": round(ask_change, 2) if ask_change else None,
            "spread_change_pct": round(spread_change, 2) if spread_change else None,
            "samples_count": len(self._history),
            "trend": trend,
        }

    def _describe_trend(
        self,
        obi_change: float,
        bid_change: float,
        ask_change: float,
    ) -> str:
        """
        描述趋势 (仅描述，不做判断)

        返回值是客观描述，不是交易建议
        """
        if obi_change is None:
            return "INSUFFICIENT_DATA"

        if obi_change > 0.05:
            return "BID_STRENGTHENING"      # 买盘相对增强
        elif obi_change < -0.05:
            return "ASK_STRENGTHENING"      # 卖盘相对增强
        elif bid_change and bid_change < -5:
            return "BID_THINNING"           # 买盘稀薄化
        elif ask_change and ask_change < -5:
            return "ASK_THINNING"           # 卖盘稀薄化
        else:
            return "STABLE"                 # 相对稳定

    def _calculate_pressure_gradient(
        self,
        bids: List,
        asks: List,
    ) -> Dict:
        """
        计算 Pressure Gradient (v2.0)

        衡量订单集中在盘口附近还是分散在远档
        """
        def calc_concentration(orders: List, levels: List[int]) -> Dict:
            total = sum(float(o[1]) for o in orders)
            if total == 0:
                return {f"near_{l}": 0.0 for l in levels}

            result = {}
            for level in levels:
                near_vol = sum(float(orders[i][1]) for i in range(min(level, len(orders))))
                result[f"near_{level}"] = round(near_vol / total, 4)
            return result

        bid_conc = calc_concentration(bids, [5, 10, 20])
        ask_conc = calc_concentration(asks, [5, 10, 20])

        # 描述集中度 (不做判断)
        def describe_concentration(near_5: float) -> str:
            if near_5 > 0.4:
                return "HIGH"           # 订单集中在盘口
            elif near_5 > 0.25:
                return "MEDIUM"
            else:
                return "LOW"            # 订单分散

        return {
            "bid_near_5": bid_conc["near_5"],
            "bid_near_10": bid_conc["near_10"],
            "bid_near_20": bid_conc["near_20"],
            "ask_near_5": ask_conc["near_5"],
            "ask_near_10": ask_conc["near_10"],
            "ask_near_20": ask_conc["near_20"],
            "bid_concentration": describe_concentration(bid_conc["near_5"]),
            "ask_concentration": describe_concentration(ask_conc["near_5"]),
        }

    def _calculate_dynamic_threshold(
        self,
        volumes: List[float],
        volatility: float = None,
    ) -> Tuple[float, str]:
        """
        计算动态异常阈值 (v2.0)

        基于近期订单量波动自动调整阈值
        """
        if len(volumes) < 5:
            return self.base_anomaly_threshold, "insufficient_data"

        import statistics
        std = statistics.stdev(volumes)
        mean = statistics.mean(volumes)

        if mean == 0:
            return self.base_anomaly_threshold, "zero_mean"

        cv = std / mean  # 变异系数

        # 高变异 → 提高阈值 (减少误报)
        # 低变异 → 降低阈值 (提高敏感度)
        if cv > 1.0:
            threshold = min(5.0, self.base_anomaly_threshold * 1.5)
            reason = "high_volatility"
        elif cv < 0.3:
            threshold = max(2.0, self.base_anomaly_threshold * 0.7)
            reason = "low_volatility"
        else:
            threshold = self.base_anomaly_threshold
            reason = "normal"

        return round(threshold, 2), reason

    def _estimate_slippage_with_confidence(
        self,
        orders: List,
        amount: float,
        side: str,
    ) -> Dict:
        """
        估算滑点 (含置信度) v2.0

        考虑:
        - 可见流动性
        - 隐藏流动性不确定性 (冰山订单)
        """
        cumulative = 0.0
        weighted_price = 0.0

        for price_str, qty_str in orders:
            price = float(price_str)
            qty = float(qty_str)

            if cumulative + qty >= amount:
                remaining = amount - cumulative
                weighted_price += price * remaining
                cumulative = amount
                break
            else:
                weighted_price += price * qty
                cumulative += qty

        if cumulative < amount:
            # 深度不足
            return {
                "estimated": None,
                "confidence": 0.0,
                "range": [None, None],
                "reason": "insufficient_depth",
            }

        avg_price = weighted_price / amount
        best_price = float(orders[0][0])

        if side == "buy":
            slippage = (avg_price - best_price) / best_price * 100
        else:
            slippage = (best_price - avg_price) / best_price * 100

        # 置信度: 基于深度充裕程度
        depth_ratio = cumulative / amount
        confidence = min(0.95, 0.5 + depth_ratio * 0.3)

        # 范围: 考虑隐藏流动性的不确定性
        # 假设实际滑点可能在 0.5x ~ 1.5x 估算值
        range_low = max(0, slippage * 0.5)
        range_high = slippage * 1.5

        return {
            "estimated": round(slippage, 4),
            "confidence": round(confidence, 2),
            "range": [round(range_low, 4), round(range_high, 4)],
        }

    def _update_history(self, data: Dict):
        """更新历史缓存"""
        # 只缓存必要字段
        cached = {
            "obi": {"simple": data["obi"]["simple"]},
            "depth_distribution": {
                "bid_depth_usd": data["depth_distribution"]["bid_depth_usd"],
                "ask_depth_usd": data["depth_distribution"]["ask_depth_usd"],
            },
            "liquidity": {"spread_pct": data["liquidity"]["spread_pct"]},
            "timestamp": data["_status"]["timestamp"],
        }
        self._history.append(cached)
        if len(self._history) > self._history_size:
            self._history = self._history[-self._history_size:]

    # =========================================================================
    # 原有方法 (保留)
    # =========================================================================

    def _calculate_simple_obi(self, bids: List, asks: List) -> float:
        """计算简单 OBI"""
        bid_vol = sum(float(b[1]) for b in bids)
        ask_vol = sum(float(a[1]) for a in asks)
        total = bid_vol + ask_vol
        if total == 0:
            return 0.0
        return (bid_vol - ask_vol) / total

    def _calculate_weighted_obi(
        self,
        bids: List,
        asks: List,
        decay: float,
    ) -> float:
        """
        计算加权 OBI

        公式: 权重 = decay ^ (距离盘口的档位)
        靠近盘口的订单权重更高，远离盘口的权重递减
        """
        weighted_bid = sum(
            float(bid[1]) * (decay ** i)
            for i, bid in enumerate(bids)
        )
        weighted_ask = sum(
            float(ask[1]) * (decay ** i)
            for i, ask in enumerate(asks)
        )
        total = weighted_bid + weighted_ask
        if total == 0:
            return 0.0
        return (weighted_bid - weighted_ask) / total

    def _calculate_depth_distribution(
        self,
        bids: List,
        asks: List,
        current_price: float,
    ) -> Dict:
        """按价格带聚合深度"""
        pass

    def _detect_anomalies(
        self,
        bids: List,
        asks: List,
        threshold: float,
    ) -> Dict:
        """检测异常大单"""
        pass
```

### 3.3 format_for_ai() 输出格式 (v2.0 更新)

```
ORDER BOOK DEPTH (Binance /fapi/v1/depth, 100 levels):
Status: OK (5 history samples)

IMBALANCE:
  Simple OBI: +0.15
  Weighted OBI: +0.12 (decay=0.75, adaptive)
  Bid Volume: $45.0M (520.5 BTC)
  Ask Volume: $39.0M (450.2 BTC)

⭐ DYNAMICS (vs previous snapshot):
  OBI Change: +0.05 (+33.3%)
  Bid Depth Change: -2.3%
  Ask Depth Change: +1.8%
  Spread Change: -5.0%
  Trend: BID_STRENGTHENING

⭐ PRESSURE GRADIENT:
  Bid: 35% near-5, 55% near-10, 72% near-20 [HIGH concentration]
  Ask: 28% near-5, 48% near-10, 68% near-20 [MEDIUM concentration]

DEPTH DISTRIBUTION (0.5% bands):
  -1.5% ~ -1.0%: Bid $2.8M
  -1.0% ~ -0.5%: Bid $3.2M
  -0.5% ~    0%: Bid $5.1M
     0% ~ +0.5%: Ask $4.8M
  +0.5% ~ +1.0%: Ask $3.5M
  +1.0% ~ +1.5%: Ask $2.1M

ANOMALIES (threshold=2.8x, high_volatility):
  Bid: $82,000 @ 280 BTC (5.6x)
  Ask: $85,000 @ 350 BTC (7.0x)

LIQUIDITY:
  Spread: 0.02% ($18.5)
  Slippage (Buy 1 BTC): 0.08% [confidence=0.7, range=0.05%-0.12%]
  Slippage (Sell 1 BTC): 0.07% [confidence=0.7, range=0.04%-0.11%]
```

### 3.4 NO_DATA 状态输出格式 (v2.0 Critical)

```
ORDER BOOK DEPTH (Binance /fapi/v1/depth):
Status: NO_DATA
Reason: API timeout after 3 retries

[All metrics unavailable - AI should not assume neutral market]
```

---

## 4. 配置设计 (v2.0 更新)

### 4.1 base.yaml 新增配置

```yaml
# configs/base.yaml (新增 order_book 段落)

# =============================================================================
# 订单簿深度配置 (Order Book Depth) v2.0
# =============================================================================
order_book:
  enabled: true

  # ---------------------------------------------------------------------------
  # API 配置
  # ---------------------------------------------------------------------------
  api:
    endpoint: "/fapi/v1/depth"
    limit: 100
    timeout: 10
    max_retries: 2
    retry_delay: 1.0

  # ---------------------------------------------------------------------------
  # 处理配置 (v2.0 更新)
  # ---------------------------------------------------------------------------
  processing:
    price_band_pct: 0.5

    # ⭐ v2.0: 加权 OBI 可配置化
    weighted_obi:
      base_decay: 0.8
      adaptive: true                   # 启用自适应衰减
      volatility_factor: 0.1           # 波动率影响因子
      min_decay: 0.5                   # 最小衰减 (高波动时)
      max_decay: 0.95                  # 最大衰减 (低波动时)

    # ⭐ v2.0: 动态异常阈值
    anomaly_detection:
      base_threshold: 3.0              # 基础阈值
      dynamic: true                    # 启用动态调整
      min_threshold: 2.0               # 最小阈值
      max_threshold: 5.0               # 最大阈值

    # 滑点估算
    slippage_amounts:
      - 0.1
      - 0.5
      - 1.0

    # ⭐ v2.0: 历史缓存 (用于变化率计算)
    history:
      size: 10                         # 缓存最近 N 次快照
      min_samples_for_trend: 3         # 计算趋势需要的最小样本数

  # ---------------------------------------------------------------------------
  # 缓存配置
  # ---------------------------------------------------------------------------
  cache:
    enabled: true
    ttl_seconds: 5

  # ---------------------------------------------------------------------------
  # ⭐ v2.0: 降级配置 (优化)
  # ---------------------------------------------------------------------------
  fallback:
    enabled: true
    # 注意: 不再使用 default_obi = 0.0
    # 而是返回明确的 NO_DATA 状态
    return_no_data_status: true        # 返回 NO_DATA 而非中性值
    default_spread_pct: 0.05           # 仅在格式化时使用
```

### 4.2 配置路径别名

```python
# utils/config_manager.py (PATH_ALIASES 新增)

PATH_ALIASES = {
    # ... 现有别名 ...

    # 订单簿配置
    'order_book.enabled': 'order_book.enabled',
    'order_book.limit': 'order_book.api.limit',
    'order_book.timeout': 'order_book.api.timeout',
    'order_book.price_band_pct': 'order_book.processing.price_band_pct',
    'order_book.base_anomaly_threshold': 'order_book.processing.anomaly_detection.base_threshold',
    'order_book.weighted_obi_adaptive': 'order_book.processing.weighted_obi.adaptive',
    'order_book.history_size': 'order_book.processing.history.size',
}
```

---

## 5. 集成设计

### 5.1 AIDataAssembler 集成 (v2.0 更新)

```python
# utils/ai_data_assembler.py (修改)

class AIDataAssembler:
    def __init__(
        self,
        binance_kline_client,
        order_flow_processor,
        coinalyze_client,
        sentiment_client,
        binance_derivatives_client=None,
        binance_orderbook_client=None,
        orderbook_processor=None,
        logger: logging.Logger = None,
    ):
        # ... 现有代码 ...
        self.orderbook_client = binance_orderbook_client
        self.orderbook_processor = orderbook_processor

    def assemble(self, ...):
        # ... 现有代码 ...

        # Step N: 获取订单簿数据
        orderbook_data = None
        if self.orderbook_client and self.orderbook_processor:
            try:
                raw_orderbook = self.orderbook_client.get_order_book(symbol=symbol)
                if raw_orderbook:
                    # ⭐ v2.0: 传入波动率用于自适应调整
                    volatility = self._get_recent_volatility(technical_data)
                    orderbook_data = self.orderbook_processor.process(
                        order_book=raw_orderbook,
                        current_price=current_price,
                        volatility=volatility,
                    )
            except Exception as e:
                self.logger.warning(f"⚠️ Order book fetch error: {e}")
                # ⭐ v2.0: 返回 NO_DATA 状态而非 None
                orderbook_data = self._no_data_orderbook(reason=str(e))

        return {
            # ... 现有字段 ...
            "order_book": orderbook_data,
            "_metadata": {
                # ... 现有字段 ...
                "orderbook_enabled": self.orderbook_client is not None,
                "orderbook_status": orderbook_data.get("_status", {}).get("code") if orderbook_data else "DISABLED",
            },
        }

    def _no_data_orderbook(self, reason: str) -> Dict:
        """
        ⭐ v2.0 Critical: 返回明确的 NO_DATA 状态

        避免 AI 将缺失数据误解为中性市场
        """
        return {
            "obi": None,
            "dynamics": None,
            "pressure_gradient": None,
            "depth_distribution": None,
            "anomalies": None,
            "liquidity": None,
            "_status": {
                "code": "NO_DATA",
                "message": f"Order book data unavailable: {reason}",
                "timestamp": int(time.time() * 1000),
            },
        }

    def _get_recent_volatility(self, technical_data: Dict) -> float:
        """获取近期波动率 (用于自适应参数)"""
        # 可以从 ATR 或价格变化计算
        atr = technical_data.get("atr", 0)
        price = technical_data.get("price", 1)
        if price > 0:
            return atr / price  # 相对波动率
        return 0.02  # 默认 2%
```

### 5.2 format_complete_report() 集成 (v2.0 更新)

```python
def format_complete_report(self, data: Dict[str, Any]) -> str:
    # ... 现有代码 ...

    # =========================================================================
    # N. 订单簿深度数据 (v2.0 更新)
    # =========================================================================
    order_book = data.get("order_book")
    if order_book:
        status = order_book.get("_status", {})
        status_code = status.get("code", "UNKNOWN")

        parts.append(f"\nORDER BOOK DEPTH (Binance, 100 levels):")
        parts.append(f"  Status: {status_code}")

        # ⭐ v2.0: 处理 NO_DATA 状态
        if status_code == "NO_DATA":
            parts.append(f"  Reason: {status.get('message', 'Unknown')}")
            parts.append("  [All metrics unavailable - do not assume neutral market]")
        else:
            # OBI
            obi = order_book.get("obi", {})
            if obi:
                parts.append(f"  Simple OBI: {obi.get('simple', 0):+.3f}")
                decay = obi.get('decay_used', 0.8)
                parts.append(f"  Weighted OBI: {obi.get('adaptive_weighted', 0):+.3f} (decay={decay})")
                parts.append(
                    f"  Bid Volume: ${obi.get('bid_volume_usd', 0)/1e6:.1f}M "
                    f"({obi.get('bid_volume_btc', 0):.1f} BTC)"
                )
                parts.append(
                    f"  Ask Volume: ${obi.get('ask_volume_usd', 0)/1e6:.1f}M "
                    f"({obi.get('ask_volume_btc', 0):.1f} BTC)"
                )

            # ⭐ v2.0: Dynamics
            dynamics = order_book.get("dynamics", {})
            if dynamics and dynamics.get("samples_count", 0) > 0:
                parts.append("  DYNAMICS (vs previous):")
                if dynamics.get("obi_change") is not None:
                    parts.append(
                        f"    OBI Change: {dynamics['obi_change']:+.4f} "
                        f"({dynamics.get('obi_change_pct', 0):+.1f}%)"
                    )
                if dynamics.get("bid_depth_change_pct") is not None:
                    parts.append(f"    Bid Depth: {dynamics['bid_depth_change_pct']:+.1f}%")
                if dynamics.get("ask_depth_change_pct") is not None:
                    parts.append(f"    Ask Depth: {dynamics['ask_depth_change_pct']:+.1f}%")
                parts.append(f"    Trend: {dynamics.get('trend', 'N/A')}")

            # ⭐ v2.0: Pressure Gradient
            gradient = order_book.get("pressure_gradient", {})
            if gradient:
                parts.append("  PRESSURE GRADIENT:")
                parts.append(
                    f"    Bid: {gradient.get('bid_near_5', 0):.0%} near-5, "
                    f"{gradient.get('bid_near_10', 0):.0%} near-10 "
                    f"[{gradient.get('bid_concentration', 'N/A')}]"
                )
                parts.append(
                    f"    Ask: {gradient.get('ask_near_5', 0):.0%} near-5, "
                    f"{gradient.get('ask_near_10', 0):.0%} near-10 "
                    f"[{gradient.get('ask_concentration', 'N/A')}]"
                )

            # 异常
            anomalies = order_book.get("anomalies", {})
            if anomalies and anomalies.get("has_significant"):
                threshold = anomalies.get("threshold_used", 3.0)
                reason = anomalies.get("threshold_reason", "normal")
                parts.append(f"  ANOMALIES (threshold={threshold}x, {reason}):")
                for a in anomalies.get("bid_anomalies", []):
                    parts.append(
                        f"    Bid @ ${a['price']:,.0f}: {a['volume_btc']:.0f} BTC "
                        f"({a['multiplier']:.1f}x)"
                    )
                for a in anomalies.get("ask_anomalies", []):
                    parts.append(
                        f"    Ask @ ${a['price']:,.0f}: {a['volume_btc']:.0f} BTC "
                        f"({a['multiplier']:.1f}x)"
                    )

            # ⭐ v2.0: 滑点 (含置信度)
            liquidity = order_book.get("liquidity", {})
            if liquidity:
                parts.append(f"  Spread: {liquidity.get('spread_pct', 0):.3f}%")
                slippage = liquidity.get("slippage", {})
                if slippage.get("buy_1.0_btc"):
                    s = slippage["buy_1.0_btc"]
                    parts.append(
                        f"  Slippage (Buy 1 BTC): {s['estimated']:.3f}% "
                        f"[conf={s['confidence']:.0%}, range={s['range'][0]:.3f}%-{s['range'][1]:.3f}%]"
                    )

    # ... 现有代码 ...
```

---

## 6. 降级策略 (v2.0 更新)

### 6.1 降级场景

| 场景 | 触发条件 | 降级行为 |
|------|----------|----------|
| API 超时 | 请求超过 timeout | 重试 → 返回 NO_DATA 状态 |
| API 错误 (4xx/5xx) | HTTP 状态码非 200 | 重试 → 返回 NO_DATA 状态 |
| 数据解析失败 | JSON 解析错误 | 返回 NO_DATA 状态 |
| 限流 (429) | 请求过于频繁 | 等待 2x 延迟后重试 |

### 6.2 NO_DATA 状态结构 (v2.0 Critical)

```python
# ⭐ v2.0: 不再使用中性默认值，而是明确标记 NO_DATA

NO_DATA_ORDERBOOK = {
    "obi": None,                      # 不是 0.0!
    "dynamics": None,
    "pressure_gradient": None,
    "depth_distribution": None,
    "anomalies": None,
    "liquidity": None,
    "_status": {
        "code": "NO_DATA",            # 明确状态码
        "message": "API timeout",     # 原因
        "timestamp": 1706745600000,
    },
}
```

**为什么不使用中性默认值？**

| 方式 | 问题 |
|------|------|
| `obi = 0.0` | AI 可能误解为 "市场买卖平衡" |
| `obi = None` + `status = NO_DATA` | AI 明确知道 "数据不可用"，可以忽略此数据源 |

---

## 7. 测试计划 (v2.0 更新)

### 7.1 单元测试

| 测试文件 | 测试内容 |
|----------|----------|
| `tests/test_orderbook_client.py` | API 调用、重试、降级 |
| `tests/test_orderbook_processor.py` | 指标计算 (含 v2.0 新指标) |

### 7.2 测试用例 (v2.0 新增)

```python
# tests/test_orderbook_processor.py

class TestOrderBookProcessor:
    # 原有测试...

    # ⭐ v2.0 新增测试
    def test_adaptive_decay_high_volatility(self):
        """高波动时衰减因子降低"""
        processor = OrderBookProcessor()
        decay = processor._calculate_adaptive_decay(volatility=0.05)
        assert decay < 0.8  # 低于基础值

    def test_adaptive_decay_low_volatility(self):
        """低波动时衰减因子提高"""
        processor = OrderBookProcessor()
        decay = processor._calculate_adaptive_decay(volatility=0.01)
        assert decay > 0.8  # 高于基础值

    def test_dynamics_calculation(self):
        """变化率计算正确"""
        processor = OrderBookProcessor()
        # 模拟历史数据
        processor._history = [{"obi": {"simple": 0.10}, ...}]
        current = {"obi": {"simple": 0.15}, ...}
        dynamics = processor._calculate_dynamics(current)
        assert dynamics["obi_change"] == 0.05
        assert dynamics["trend"] == "BID_STRENGTHENING"

    def test_dynamics_insufficient_data(self):
        """历史数据不足时返回 INSUFFICIENT_DATA"""
        processor = OrderBookProcessor()
        processor._history = []
        dynamics = processor._calculate_dynamics({})
        assert dynamics["trend"] == "INSUFFICIENT_DATA"

    def test_pressure_gradient_high_concentration(self):
        """高集中度正确识别"""
        pass

    def test_dynamic_threshold_high_volatility(self):
        """高波动时阈值提高"""
        pass

    def test_slippage_with_confidence(self):
        """滑点估算包含置信度"""
        pass

    def test_no_data_status_on_error(self):
        """错误时返回 NO_DATA 状态而非中性值"""
        pass
```

---

## 8. 文件清单 (v2.0 更新)

### 8.1 新增文件

| 文件 | 说明 | 预估行数 |
|------|------|----------|
| `utils/binance_orderbook_client.py` | 订单簿 API 客户端 | ~120 行 |
| `utils/orderbook_processor.py` | 订单簿数据处理器 (v2.0) | ~400 行 ⬆️ |
| `tests/test_orderbook_client.py` | 客户端单元测试 | ~100 行 |
| `tests/test_orderbook_processor.py` | 处理器单元测试 (v2.0) | ~300 行 ⬆️ |

### 8.2 修改文件

| 文件 | 修改内容 | 预估改动 |
|------|----------|----------|
| `configs/base.yaml` | 添加 order_book 配置段 (v2.0) | +60 行 ⬆️ |
| `utils/config_manager.py` | 添加配置路径别名 | +15 行 |
| `utils/ai_data_assembler.py` | 集成订单簿数据 (v2.0) | +80 行 ⬆️ |
| `main_live.py` | 初始化订单簿客户端 | +35 行 |
| `scripts/diagnose_realtime.py` | 添加订单簿诊断 | +50 行 ⬆️ |
| `CLAUDE.md` | 更新配置文档 | +30 行 |

### 8.3 总计

- **新增代码**: ~920 行 (v1.0: 670 行)
- **修改代码**: ~270 行 (v1.0: 180 行)
- **总计**: ~1190 行 (v1.0: 850 行)

---

## 9. 实施步骤

### Phase 1: 核心实现 (Day 1)

1. [ ] 创建 `binance_orderbook_client.py`
2. [ ] 创建 `orderbook_processor.py` (含 v2.0 新功能)
3. [ ] 添加配置到 `base.yaml`

### Phase 2: 集成 (Day 1-2)

4. [ ] 修改 `ai_data_assembler.py`
5. [ ] 修改 `main_live.py`
6. [ ] 更新 `format_complete_report()`

### Phase 3: 测试 (Day 2)

7. [ ] 编写单元测试 (含 v2.0 新测试)
8. [ ] 编写集成测试
9. [ ] 运行 `diagnose_realtime.py` 验证

### Phase 4: 文档 (Day 2-3)

10. [ ] 更新 `CLAUDE.md`
11. [ ] 更新 `DATA_SOURCES_MATRIX.md`
12. [ ] 运行 `smart_commit_analyzer.py`

---

## 10. 风险评估

### 10.1 技术风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| API 限流 | 中 | 低 | 缓存 + 降级 |
| 延迟增加 | 低 | 低 | 异步获取 (未来优化) |
| 数据不一致 | 低 | 低 | 时间戳验证 |
| 历史缓存内存 | 低 | 低 | 限制缓存大小 (10 samples) |

### 10.2 兼容性风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 破坏现有流程 | 低 | 高 | 可选启用 (enabled: false) |
| 配置冲突 | 低 | 低 | PATH_ALIASES 兼容 |

---

## 11. 成功标准

| 标准 | 验证方式 |
|------|----------|
| OBI 计算正确 | 单元测试 + 手动验证 |
| 加权 OBI 符合预期 | 单元测试 |
| ⭐ 自适应衰减工作正常 | 单元测试 |
| ⭐ 变化率指标正确 | 单元测试 |
| ⭐ Pressure Gradient 正确 | 单元测试 |
| ⭐ 动态阈值工作正常 | 单元测试 |
| 滑点估算准确 | 与实际执行对比 |
| ⭐ NO_DATA 状态正确返回 | 模拟 API 失败 |
| AI 收到完整数据 | `diagnose_realtime.py` |
| 无性能回归 | 15分钟周期内完成 |

---

## 12. 参考资料

- [Binance Futures API - Order Book](https://binance-docs.github.io/apidocs/futures/en/#order-book)
- [python-binance Documentation](https://python-binance.readthedocs.io/)
- [Order Book Imbalance Analysis](https://questdb.com/blog/order-book-imbalance-analysis/)
- [TradingAgents Framework](https://github.com/TauricResearch/TradingAgents)

---

## 附录 A: API 响应示例

```json
{
    "lastUpdateId": 1027024,
    "E": 1589436922972,
    "T": 1589436922959,
    "bids": [
        ["9000.00", "10.5"],
        ["8999.50", "5.2"],
        ["8999.00", "8.8"]
    ],
    "asks": [
        ["9000.50", "8.3"],
        ["9001.00", "6.1"],
        ["9001.50", "12.4"]
    ]
}
```

## 附录 B: 加权 OBI 算法 (v2.0 自适应版本)

```python
def weighted_obi(bids, asks, decay=0.8, volatility=None, config=None):
    """
    加权 OBI 算法 v2.0

    v1.0: 固定衰减因子
    v2.0: 自适应衰减因子

    权重 = decay ^ level
    - Level 0 (盘口): 权重 = 1.0
    - Level 1: 权重 = decay
    - Level 2: 权重 = decay^2
    - ...

    自适应调整:
    - 高波动: 降低 decay (更关注盘口)
    - 低波动: 提高 decay (更多考虑远档)
    """
    # v2.0: 自适应衰减
    if config and config.get("adaptive") and volatility is not None:
        decay = config["base_decay"] - volatility * config["volatility_factor"]
        decay = max(config["min_decay"], min(config["max_decay"], decay))

    weighted_bid = sum(
        float(bid[1]) * (decay ** i)
        for i, bid in enumerate(bids)
    )
    weighted_ask = sum(
        float(ask[1]) * (decay ** i)
        for i, ask in enumerate(asks)
    )

    total = weighted_bid + weighted_ask
    if total == 0:
        return 0.0, decay

    return (weighted_bid - weighted_ask) / total, decay
```

## 附录 C: v2.0 新增指标说明

### C.1 Dynamics (变化率指标)

| 字段 | 类型 | 说明 |
|------|------|------|
| `obi_change` | float | OBI 绝对变化 |
| `obi_change_pct` | float | OBI 变化百分比 |
| `bid_depth_change_pct` | float | 买盘深度变化 % |
| `ask_depth_change_pct` | float | 卖盘深度变化 % |
| `spread_change_pct` | float | 价差变化 % |
| `samples_count` | int | 历史样本数 |
| `trend` | str | 趋势描述 (见下表) |

**Trend 值说明**:

| 值 | 含义 | 触发条件 |
|---|------|---------|
| `BID_STRENGTHENING` | 买盘相对增强 | OBI 变化 > +0.05 |
| `ASK_STRENGTHENING` | 卖盘相对增强 | OBI 变化 < -0.05 |
| `BID_THINNING` | 买盘稀薄化 | 买盘深度变化 < -5% |
| `ASK_THINNING` | 卖盘稀薄化 | 卖盘深度变化 < -5% |
| `STABLE` | 相对稳定 | 其他情况 |
| `INSUFFICIENT_DATA` | 数据不足 | 历史样本 < 1 |

### C.2 Pressure Gradient

| 字段 | 类型 | 说明 |
|------|------|------|
| `bid_near_5` | float | 前5档买单占比 |
| `bid_near_10` | float | 前10档买单占比 |
| `bid_near_20` | float | 前20档买单占比 |
| `ask_near_5` | float | 前5档卖单占比 |
| `ask_near_10` | float | 前10档卖单占比 |
| `ask_near_20` | float | 前20档卖单占比 |
| `bid_concentration` | str | 买单集中度 (HIGH/MEDIUM/LOW) |
| `ask_concentration` | str | 卖单集中度 (HIGH/MEDIUM/LOW) |

**Concentration 判断标准**:
- HIGH: near_5 > 40%
- MEDIUM: 25% < near_5 <= 40%
- LOW: near_5 <= 25%
