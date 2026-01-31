# BinanceOrderBookClient 实施方案

> 版本: v1.0
> 日期: 2026-01-31
> 状态: 待评估

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

### 1.3 核心指标

| 指标 | 类型 | 说明 |
|------|------|------|
| **OBI** (Order Book Imbalance) | 不平衡 | 买卖压力对比 |
| **加权 OBI** | 不平衡 | 靠近盘口的订单权重更高 ⭐ 新增 |
| **深度分布** | 分布 | 按价格带聚合的挂单量 |
| **异常检测** | 分布 | 超过均值 3x 的大单 |
| **滑点估算** | 流动性 | 执行 N BTC 的预期滑点 |
| **价差** | 流动性 | 买一/卖一价差 |

---

## 2. 架构设计

### 2.1 数据流全景

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         数据流全景图                                     │
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
                               └─────────────────┘
```

### 2.2 组件职责

| 组件 | 文件 | 职责 |
|------|------|------|
| **BinanceOrderBookClient** | `utils/binance_orderbook_client.py` | API 调用、原始数据获取 |
| **OrderBookProcessor** | `utils/orderbook_processor.py` | 指标计算 (OBI, 滑点等) |
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
        pass

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
        pass
```

### 3.2 OrderBookProcessor

```python
# utils/orderbook_processor.py

class OrderBookProcessor:
    """
    订单簿数据处理器

    职责:
    - 计算 OBI (Order Book Imbalance)
    - 计算加权 OBI (靠近盘口权重更高)
    - 计算深度分布 (按价格带聚合)
    - 检测异常大单
    - 估算滑点

    设计原则:
    - 只做预处理，不做判断
    - 输出原始指标，让 AI 解读
    """

    def __init__(
        self,
        price_band_pct: float = 0.5,     # 价格带宽度 (%)
        anomaly_threshold: float = 3.0,   # 异常检测阈值 (倍数)
        slippage_amounts: List[float] = [0.1, 0.5, 1.0],  # BTC
        weighted_obi_decay: float = 0.8,  # 加权 OBI 衰减因子
        logger: logging.Logger = None,
    ):
        pass

    def process(
        self,
        order_book: Dict,
        current_price: float,
    ) -> Dict[str, Any]:
        """
        处理订单簿数据

        Returns
        -------
        {
            # 基础不平衡指标
            "obi": {
                "simple": 0.15,           # 简单 OBI: (bid-ask)/(bid+ask)
                "weighted": 0.12,         # 加权 OBI (靠近盘口权重高)
                "bid_volume_btc": 520.5,  # 买单总量 (BTC)
                "ask_volume_btc": 450.2,  # 卖单总量 (BTC)
                "bid_volume_usd": 45000000,
                "ask_volume_usd": 39000000,
            },

            # 深度分布 (按价格带)
            "depth_distribution": {
                "bands": [
                    {"range": "-1.5% ~ -1.0%", "side": "bid", "volume_usd": 2800000},
                    {"range": "-1.0% ~ -0.5%", "side": "bid", "volume_usd": 3200000},
                    {"range": "-0.5% ~ 0%", "side": "bid", "volume_usd": 5100000},
                    {"range": "0% ~ +0.5%", "side": "ask", "volume_usd": 4800000},
                    {"range": "+0.5% ~ +1.0%", "side": "ask", "volume_usd": 3500000},
                    {"range": "+1.0% ~ +1.5%", "side": "ask", "volume_usd": 2100000},
                ],
                "bid_depth_usd": 11100000,  # 总买单深度
                "ask_depth_usd": 10400000,  # 总卖单深度
            },

            # 异常检测 (大单)
            "anomalies": {
                "bid_anomalies": [
                    {"price": 82000, "volume_btc": 280, "multiplier": 5.6},
                ],
                "ask_anomalies": [
                    {"price": 85000, "volume_btc": 350, "multiplier": 7.0},
                ],
                "has_significant": True,  # 是否有显著异常
            },

            # 流动性指标
            "liquidity": {
                "slippage": {
                    "buy_0.1_btc": 0.02,   # 买入 0.1 BTC 滑点 (%)
                    "buy_0.5_btc": 0.05,   # 买入 0.5 BTC 滑点 (%)
                    "buy_1.0_btc": 0.08,   # 买入 1.0 BTC 滑点 (%)
                    "sell_0.1_btc": 0.02,
                    "sell_0.5_btc": 0.04,
                    "sell_1.0_btc": 0.07,
                },
                "spread_pct": 0.02,       # 买卖价差 (%)
                "spread_usd": 18.5,       # 买卖价差 ($)
                "mid_price": 86250.5,     # 中间价
            },

            # 元数据
            "_metadata": {
                "levels_analyzed": 100,
                "timestamp": 1706745600000,
                "price_used": 86250.0,
            },
        }
        """
        pass

    def _calculate_simple_obi(self, bids: List, asks: List) -> float:
        """计算简单 OBI"""
        pass

    def _calculate_weighted_obi(
        self,
        bids: List,
        asks: List,
        mid_price: float,
    ) -> float:
        """
        计算加权 OBI

        公式: 权重 = decay ^ (距离盘口的档位)
        靠近盘口的订单权重更高，远离盘口的权重递减
        """
        pass

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
    ) -> Dict:
        """检测异常大单 (>3x 平均值)"""
        pass

    def _estimate_slippage(
        self,
        bids: List,
        asks: List,
        amounts: List[float],
    ) -> Dict:
        """估算执行滑点"""
        pass
```

### 3.3 format_for_ai() 输出格式

```
ORDER BOOK DEPTH (Binance /fapi/v1/depth, 100 levels):

IMBALANCE:
  Simple OBI: +0.15 (bid-dominated)
  Weighted OBI: +0.12 (near-book weighted)
  Bid Volume: $45.0M (520.5 BTC)
  Ask Volume: $39.0M (450.2 BTC)

DEPTH DISTRIBUTION (0.5% bands):
  -1.5% ~ -1.0%: Bid $2.8M
  -1.0% ~ -0.5%: Bid $3.2M
  -0.5% ~    0%: Bid $5.1M
     0% ~ +0.5%: Ask $4.8M
  +0.5% ~ +1.0%: Ask $3.5M
  +1.0% ~ +1.5%: Ask $2.1M

ANOMALIES (>3x avg):
  Bid: $82,000 @ 280 BTC (5.6x avg)
  Ask: $85,000 @ 350 BTC (7.0x avg)

LIQUIDITY:
  Spread: 0.02% ($18.5)
  Slippage (Buy): 0.1 BTC=0.02%, 0.5 BTC=0.05%, 1 BTC=0.08%
  Slippage (Sell): 0.1 BTC=0.02%, 0.5 BTC=0.04%, 1 BTC=0.07%
```

---

## 4. 配置设计

### 4.1 base.yaml 新增配置

```yaml
# configs/base.yaml (新增 order_book 段落)

# =============================================================================
# 订单簿深度配置 (Order Book Depth) v1.0
# =============================================================================
order_book:
  enabled: true                        # 启用订单簿数据

  # ---------------------------------------------------------------------------
  # API 配置
  # ---------------------------------------------------------------------------
  api:
    endpoint: "/fapi/v1/depth"
    limit: 100                         # 获取档位数 (5/10/20/50/100/500/1000)
    timeout: 10                        # 请求超时 (秒)
    max_retries: 2                     # 最大重试次数
    retry_delay: 1.0                   # 重试延迟 (秒)

  # ---------------------------------------------------------------------------
  # 处理配置
  # ---------------------------------------------------------------------------
  processing:
    price_band_pct: 0.5                # 价格带宽度 (%)
    anomaly_threshold: 3.0             # 异常检测阈值 (倍数)
    weighted_obi_decay: 0.8            # 加权 OBI 衰减因子
    slippage_amounts:                  # 滑点估算金额 (BTC)
      - 0.1
      - 0.5
      - 1.0

  # ---------------------------------------------------------------------------
  # 缓存配置
  # ---------------------------------------------------------------------------
  cache:
    enabled: true                      # 启用缓存
    ttl_seconds: 5                     # 缓存有效期 (秒)

  # ---------------------------------------------------------------------------
  # 降级配置
  # ---------------------------------------------------------------------------
  fallback:
    enabled: true                      # API 失败时使用默认值
    default_obi: 0.0                   # 默认 OBI (中性)
    default_spread_pct: 0.05           # 默认价差 (%)
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
    'order_book.anomaly_threshold': 'order_book.processing.anomaly_threshold',
}
```

---

## 5. 集成设计

### 5.1 AIDataAssembler 集成

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
        binance_orderbook_client=None,      # ⭐ 新增
        orderbook_processor=None,            # ⭐ 新增
        logger: logging.Logger = None,
    ):
        # ... 现有代码 ...
        self.orderbook_client = binance_orderbook_client
        self.orderbook_processor = orderbook_processor

    def assemble(self, ...):
        # ... 现有代码 ...

        # Step N: 获取订单簿数据 (新增)
        orderbook_data = None
        if self.orderbook_client and self.orderbook_processor:
            try:
                raw_orderbook = self.orderbook_client.get_order_book(symbol=symbol)
                if raw_orderbook:
                    orderbook_data = self.orderbook_processor.process(
                        order_book=raw_orderbook,
                        current_price=current_price,
                    )
            except Exception as e:
                self.logger.warning(f"⚠️ Order book fetch error: {e}")

        return {
            # ... 现有字段 ...
            "order_book": orderbook_data,  # ⭐ 新增
            "_metadata": {
                # ... 现有字段 ...
                "orderbook_enabled": self.orderbook_client is not None,
            },
        }
```

### 5.2 main_live.py 初始化

```python
# main_live.py (新增初始化)

from utils.binance_orderbook_client import BinanceOrderBookClient
from utils.orderbook_processor import OrderBookProcessor

# ... 现有代码 ...

# 订单簿客户端 (新增)
orderbook_client = None
orderbook_processor = None

if config.get('order_book', 'enabled', default=True):
    orderbook_client = BinanceOrderBookClient(
        timeout=config.get('order_book', 'api', 'timeout', default=10),
        max_retries=config.get('order_book', 'api', 'max_retries', default=2),
        retry_delay=config.get('order_book', 'api', 'retry_delay', default=1.0),
        logger=logger,
    )
    orderbook_processor = OrderBookProcessor(
        price_band_pct=config.get('order_book', 'processing', 'price_band_pct', default=0.5),
        anomaly_threshold=config.get('order_book', 'processing', 'anomaly_threshold', default=3.0),
        slippage_amounts=config.get('order_book', 'processing', 'slippage_amounts', default=[0.1, 0.5, 1.0]),
        weighted_obi_decay=config.get('order_book', 'processing', 'weighted_obi_decay', default=0.8),
        logger=logger,
    )

# 传递给 AIDataAssembler
ai_data_assembler = AIDataAssembler(
    binance_kline_client=kline_client,
    order_flow_processor=order_flow_processor,
    coinalyze_client=coinalyze_client,
    sentiment_client=sentiment_client,
    binance_derivatives_client=derivatives_client,
    binance_orderbook_client=orderbook_client,       # ⭐ 新增
    orderbook_processor=orderbook_processor,          # ⭐ 新增
    logger=logger,
)
```

### 5.3 format_complete_report() 集成

```python
# utils/ai_data_assembler.py (format_complete_report 新增段落)

def format_complete_report(self, data: Dict[str, Any]) -> str:
    # ... 现有代码 ...

    # =========================================================================
    # N. 订单簿深度数据 (新增)
    # =========================================================================
    order_book = data.get("order_book")
    if order_book:
        parts.append("\nORDER BOOK DEPTH (Binance, 100 levels):")

        # OBI
        obi = order_book.get("obi", {})
        parts.append(f"  - Simple OBI: {obi.get('simple', 0):+.3f}")
        parts.append(f"  - Weighted OBI: {obi.get('weighted', 0):+.3f}")
        parts.append(
            f"  - Bid Volume: ${obi.get('bid_volume_usd', 0)/1e6:.1f}M "
            f"({obi.get('bid_volume_btc', 0):.1f} BTC)"
        )
        parts.append(
            f"  - Ask Volume: ${obi.get('ask_volume_usd', 0)/1e6:.1f}M "
            f"({obi.get('ask_volume_btc', 0):.1f} BTC)"
        )

        # 深度分布
        depth = order_book.get("depth_distribution", {})
        bands = depth.get("bands", [])
        if bands:
            parts.append("  - Depth by Price Band:")
            for band in bands:
                parts.append(
                    f"    {band['range']}: {band['side'].capitalize()} "
                    f"${band['volume_usd']/1e6:.1f}M"
                )

        # 异常
        anomalies = order_book.get("anomalies", {})
        if anomalies.get("has_significant"):
            parts.append("  - Anomalies (>3x avg):")
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

        # 流动性
        liquidity = order_book.get("liquidity", {})
        parts.append(f"  - Spread: {liquidity.get('spread_pct', 0):.3f}%")
        slippage = liquidity.get("slippage", {})
        if slippage:
            parts.append(
                f"  - Slippage (Buy 1 BTC): {slippage.get('buy_1.0_btc', 0):.3f}%"
            )

    # ... 现有代码 ...
```

---

## 6. 降级策略

### 6.1 降级场景

| 场景 | 触发条件 | 降级行为 |
|------|----------|----------|
| API 超时 | 请求超过 timeout | 重试 → 使用缓存 → 使用默认值 |
| API 错误 (4xx/5xx) | HTTP 状态码非 200 | 重试 → 使用缓存 → 使用默认值 |
| 数据解析失败 | JSON 解析错误 | 使用默认值 |
| 限流 (429) | 请求过于频繁 | 等待 2x 延迟后重试 |

### 6.2 默认值

```python
DEFAULT_ORDERBOOK_DATA = {
    "obi": {
        "simple": 0.0,      # 中性
        "weighted": 0.0,
        "bid_volume_btc": 0,
        "ask_volume_btc": 0,
        "bid_volume_usd": 0,
        "ask_volume_usd": 0,
    },
    "depth_distribution": {
        "bands": [],
        "bid_depth_usd": 0,
        "ask_depth_usd": 0,
    },
    "anomalies": {
        "bid_anomalies": [],
        "ask_anomalies": [],
        "has_significant": False,
    },
    "liquidity": {
        "slippage": {},
        "spread_pct": 0.05,  # 假设 0.05% 默认价差
        "spread_usd": 0,
        "mid_price": 0,
    },
    "_metadata": {
        "source": "fallback",
        "reason": "api_error",
    },
}
```

---

## 7. 测试计划

### 7.1 单元测试

| 测试文件 | 测试内容 |
|----------|----------|
| `tests/test_orderbook_client.py` | API 调用、重试、降级 |
| `tests/test_orderbook_processor.py` | OBI 计算、深度分布、滑点估算 |

### 7.2 测试用例

```python
# tests/test_orderbook_processor.py

class TestOrderBookProcessor:
    def test_simple_obi_balanced(self):
        """买卖平衡时 OBI = 0"""
        pass

    def test_simple_obi_bid_dominated(self):
        """买盘主导时 OBI > 0"""
        pass

    def test_weighted_obi_near_book_weighted(self):
        """靠近盘口的订单权重更高"""
        pass

    def test_depth_distribution_correct_bands(self):
        """深度分布按价格带正确聚合"""
        pass

    def test_anomaly_detection_threshold(self):
        """异常检测阈值正确"""
        pass

    def test_slippage_estimation_accuracy(self):
        """滑点估算准确"""
        pass

    def test_fallback_on_empty_data(self):
        """空数据时正确降级"""
        pass
```

### 7.3 集成测试

```python
# tests/test_integration_orderbook.py

class TestOrderBookIntegration:
    def test_ai_data_assembler_includes_orderbook(self):
        """AIDataAssembler 正确集成订单簿数据"""
        pass

    def test_format_complete_report_includes_orderbook(self):
        """格式化报告包含订单簿段落"""
        pass

    def test_config_loading(self):
        """配置正确加载"""
        pass
```

---

## 8. 文件清单

### 8.1 新增文件

| 文件 | 说明 | 预估行数 |
|------|------|----------|
| `utils/binance_orderbook_client.py` | 订单簿 API 客户端 | ~120 行 |
| `utils/orderbook_processor.py` | 订单簿数据处理器 | ~250 行 |
| `tests/test_orderbook_client.py` | 客户端单元测试 | ~100 行 |
| `tests/test_orderbook_processor.py` | 处理器单元测试 | ~200 行 |

### 8.2 修改文件

| 文件 | 修改内容 | 预估改动 |
|------|----------|----------|
| `configs/base.yaml` | 添加 order_book 配置段 | +40 行 |
| `utils/config_manager.py` | 添加配置路径别名 | +10 行 |
| `utils/ai_data_assembler.py` | 集成订单簿数据 | +50 行 |
| `main_live.py` | 初始化订单簿客户端 | +30 行 |
| `scripts/diagnose_realtime.py` | 添加订单簿诊断 | +30 行 |
| `CLAUDE.md` | 更新配置文档 | +20 行 |

### 8.3 总计

- **新增代码**: ~670 行
- **修改代码**: ~180 行
- **总计**: ~850 行

---

## 9. 实施步骤

### Phase 1: 核心实现 (Day 1)

1. ✅ 创建 `binance_orderbook_client.py`
2. ✅ 创建 `orderbook_processor.py`
3. ✅ 添加配置到 `base.yaml`

### Phase 2: 集成 (Day 1-2)

4. ✅ 修改 `ai_data_assembler.py`
5. ✅ 修改 `main_live.py`
6. ✅ 更新 `format_complete_report()`

### Phase 3: 测试 (Day 2)

7. ✅ 编写单元测试
8. ✅ 编写集成测试
9. ✅ 运行 `diagnose_realtime.py` 验证

### Phase 4: 文档 (Day 2-3)

10. ✅ 更新 `CLAUDE.md`
11. ✅ 更新 `DATA_SOURCES_MATRIX.md`
12. ✅ 运行 `smart_commit_analyzer.py`

---

## 10. 风险评估

### 10.1 技术风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| API 限流 | 中 | 低 | 缓存 + 降级 |
| 延迟增加 | 低 | 低 | 异步获取 (未来优化) |
| 数据不一致 | 低 | 低 | 时间戳验证 |

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
| 滑点估算准确 | 与实际执行对比 |
| 降级正确触发 | 模拟 API 失败 |
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

## 附录 B: 加权 OBI 算法

```python
def weighted_obi(bids, asks, decay=0.8):
    """
    加权 OBI 算法

    权重 = decay ^ level
    - Level 0 (盘口): 权重 = 1.0
    - Level 1: 权重 = 0.8
    - Level 2: 权重 = 0.64
    - Level 3: 权重 = 0.512
    - ...

    这样靠近盘口的订单对 OBI 影响更大
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
```
