# MTF 方案未实现功能清单

## 文档信息

| 项目 | 值 |
|------|-----|
| 创建日期 | 2026-01-27 |
| 基于文档 | docs/MULTI_TIMEFRAME_IMPLEMENTATION_PLAN.md v3.2.9 |
| 当前完成度 | ~70% |

---

## 一、未实现文件清单

| 文件 | 用途 | 优先级 | 代码量估算 |
|------|------|--------|-----------|
| `utils/coinalyze_client.py` | Coinalyze API 客户端 | P2 | ~200 行 |
| `utils/order_flow_processor.py` | 订单流数据处理 | P2 | ~100 行 |
| `utils/ai_data_assembler.py` | AI 数据组装器 | P2 | ~150 行 |
| `tests/test_multi_timeframe.py` | MTF 单元测试 | P1 | ~300 行 |

---

## 二、Coinalyze 客户端 (utils/coinalyze_client.py)

### 2.1 功能说明

从 Coinalyze API 获取衍生品市场数据，增强 AI 决策信息。

### 2.2 需要获取的数据

| 端点 | 数据 | 用途 |
|------|------|------|
| `/v1/open-interest` | 聚合持仓量 (OI) | 趋势强度判断 |
| `/v1/liquidation-history` | 多空清算数据 | 极端行情信号 |
| `/v1/funding-rate` | 资金费率 | 市场情绪指标 |

### 2.3 API 规格

```
Base URL: https://api.coinalyze.net/v1
认证方式: Header `api_key` 或 Query `?api_key=xxx`
速率限制: 40 次/分钟
Symbol 格式: BTCUSDT_PERP.A (A = Binance)
```

### 2.4 关键实现细节

**时间戳单位不一致 (重要)**:
- 当前端点 (`update` 字段): **毫秒** (13位)
- 历史端点 (`t` 字段): **秒** (10位)
- 历史参数 (`from`/`to`): **秒** (10位)

**OI 单位**:
- API 返回 `value` 是 **BTC 数量**，不是 USD
- 需要乘以当前价格转换为 USD

**Liquidation 响应是嵌套结构**:
```json
[{"symbol": "...", "history": [{"t": ..., "l": ..., "s": ...}]}]
```

### 2.5 代码模板

```python
# utils/coinalyze_client.py

import aiohttp
import time
from typing import Optional
import os


class CoinalyzeClient:
    """
    Coinalyze API 客户端

    获取衍生品数据: OI, 清算, 资金费率
    """

    BASE_URL = "https://api.coinalyze.net/v1"
    DEFAULT_SYMBOL = "BTCUSDT_PERP.A"

    def __init__(self, api_key: str = None, timeout: int = 10):
        self.api_key = api_key or os.getenv("COINALYZE_API_KEY")
        self.timeout = timeout
        self._enabled = bool(self.api_key)

        if not self._enabled:
            print("⚠️ COINALYZE_API_KEY not set, Coinalyze client disabled")

    def _get_headers(self) -> dict:
        return {"api_key": self.api_key} if self.api_key else {}

    async def get_open_interest(self, symbol: str = None) -> Optional[dict]:
        """
        获取当前 Open Interest

        Returns:
            {
                "symbol": "BTCUSDT_PERP.A",
                "value": 102199.59,       # BTC 数量 (非 USD!)
                "update": 1769417410150   # 毫秒时间戳
            }
        """
        if not self._enabled:
            return None

        symbol = symbol or self.DEFAULT_SYMBOL
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/open-interest"
                params = {"symbols": symbol}
                headers = self._get_headers()
                async with session.get(url, params=params, headers=headers,
                                       timeout=self.timeout) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data[0] if data else None
                    elif resp.status == 429:
                        print("⚠️ Coinalyze rate limit reached")
        except Exception as e:
            print(f"⚠️ Coinalyze OI error: {e}")
        return None

    async def get_liquidations(self, symbol: str = None,
                                interval: str = "1hour") -> Optional[dict]:
        """
        获取清算历史

        Args:
            interval: 1hour, 4hour, daily 等

        Returns:
            {
                "symbol": "...",
                "history": [
                    {"t": 1769418000, "l": 123456.78, "s": 98765.43}
                ]
            }

        注意:
        - t 是秒时间戳 (10位)
        - l = long liquidations (USD)
        - s = short liquidations (USD)
        """
        if not self._enabled:
            return None

        symbol = symbol or self.DEFAULT_SYMBOL
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/liquidation-history"
                params = {
                    "symbols": symbol,
                    "interval": interval,
                    "from": int(time.time()) - 3600,  # 秒!
                    "to": int(time.time())
                }
                headers = self._get_headers()
                async with session.get(url, params=params, headers=headers,
                                       timeout=self.timeout) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data[0] if data else None
                    elif resp.status == 429:
                        print("⚠️ Coinalyze rate limit reached")
        except Exception as e:
            print(f"⚠️ Coinalyze liquidation error: {e}")
        return None

    async def get_funding_rate(self, symbol: str = None) -> Optional[dict]:
        """
        获取当前资金费率

        Returns:
            {
                "symbol": "BTCUSDT_PERP.A",
                "value": 0.002847,       # 0.2847%
                "update": 1769420174380  # 毫秒时间戳
            }
        """
        if not self._enabled:
            return None

        symbol = symbol or self.DEFAULT_SYMBOL
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/funding-rate"
                params = {"symbols": symbol}
                headers = self._get_headers()
                async with session.get(url, params=params, headers=headers,
                                       timeout=self.timeout) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data[0] if data else None
                    elif resp.status == 429:
                        print("⚠️ Coinalyze rate limit reached")
        except Exception as e:
            print(f"⚠️ Coinalyze funding error: {e}")
        return None

    def is_enabled(self) -> bool:
        """检查客户端是否启用"""
        return self._enabled
```

### 2.6 配置要求

**~/.env.aitrader 添加**:
```bash
COINALYZE_API_KEY=your_api_key_here
```

**configs/base.yaml 添加**:
```yaml
order_flow:
  coinalyze:
    enabled: true
    timeout: 10
    symbol: "BTCUSDT_PERP.A"
    rate_limit_per_min: 40
```

---

## 三、订单流处理器 (utils/order_flow_processor.py)

### 3.1 功能说明

处理 Binance K线的完整 12 列数据，计算订单流指标。

### 3.2 K线 12 列

```
[0] open_time        [4] close           [8] trades_count
[1] open             [5] volume          [9] taker_buy_volume ⭐
[2] high             [6] close_time      [10] taker_buy_quote
[3] low              [7] quote_volume    [11] ignore
```

### 3.3 计算的指标

| 指标 | 计算方式 | 含义 |
|------|----------|------|
| `buy_ratio` | taker_buy_volume / volume | >0.5 表示买盘主导 |
| `avg_trade_usdt` | quote_volume / trades_count | 平均成交额 |
| `cvd_trend` | 累积 (buy - sell) 的趋势 | CVD 方向 |

### 3.4 代码模板

```python
# utils/order_flow_processor.py

from typing import List, Dict, Any


class OrderFlowProcessor:
    """
    订单流数据处理器

    从 Binance K线数据计算订单流指标
    """

    def __init__(self):
        self._cvd_history: List[float] = []

    def process_klines(self, klines: List[List]) -> Dict[str, Any]:
        """
        处理 K线数据，计算订单流指标

        Args:
            klines: Binance K线数据 (12 列格式)

        Returns:
            {
                "buy_ratio": 0.55,           # 买盘占比
                "avg_trade_usdt": 1250.5,    # 平均成交额
                "volume_usdt": 125000000,    # 总成交额
                "trades_count": 100000,      # 成交笔数
                "cvd_trend": "RISING",       # CVD 趋势
                "recent_10_bars": [...]      # 最近10根bar的买盘比
            }
        """
        if not klines or len(klines) == 0:
            return self._default_result()

        # 处理最新一根 K线
        latest = klines[-1]

        volume = float(latest[5])
        taker_buy_volume = float(latest[9])
        quote_volume = float(latest[7])
        trades_count = int(latest[8])

        # 计算买盘占比
        buy_ratio = taker_buy_volume / volume if volume > 0 else 0.5

        # 计算平均成交额
        avg_trade_usdt = quote_volume / trades_count if trades_count > 0 else 0

        # 计算 CVD (累积成交量差)
        sell_volume = volume - taker_buy_volume
        cvd_delta = taker_buy_volume - sell_volume
        self._cvd_history.append(cvd_delta)

        # 保留最近 50 个 CVD 值
        if len(self._cvd_history) > 50:
            self._cvd_history = self._cvd_history[-50:]

        # 判断 CVD 趋势
        cvd_trend = self._calculate_cvd_trend()

        # 计算最近 10 根 bar 的买盘比
        recent_10_bars = []
        for bar in klines[-10:]:
            bar_volume = float(bar[5])
            bar_buy = float(bar[9])
            bar_ratio = bar_buy / bar_volume if bar_volume > 0 else 0.5
            recent_10_bars.append(round(bar_ratio, 3))

        return {
            "buy_ratio": round(buy_ratio, 4),
            "avg_trade_usdt": round(avg_trade_usdt, 2),
            "volume_usdt": round(quote_volume, 2),
            "trades_count": trades_count,
            "cvd_trend": cvd_trend,
            "recent_10_bars": recent_10_bars,
        }

    def _calculate_cvd_trend(self) -> str:
        """计算 CVD 趋势"""
        if len(self._cvd_history) < 5:
            return "NEUTRAL"

        recent_5 = self._cvd_history[-5:]
        avg_recent = sum(recent_5) / len(recent_5)

        if len(self._cvd_history) >= 10:
            older_5 = self._cvd_history[-10:-5]
            avg_older = sum(older_5) / len(older_5)

            if avg_recent > avg_older * 1.1:
                return "RISING"
            elif avg_recent < avg_older * 0.9:
                return "FALLING"

        return "NEUTRAL"

    def _default_result(self) -> Dict[str, Any]:
        """返回默认值"""
        return {
            "buy_ratio": 0.5,
            "avg_trade_usdt": 0,
            "volume_usdt": 0,
            "trades_count": 0,
            "cvd_trend": "NEUTRAL",
            "recent_10_bars": [],
        }
```

---

## 四、AI 数据组装器 (utils/ai_data_assembler.py)

### 4.1 功能说明

并行获取所有外部数据，转换格式，组装成 AI 输入。

### 4.2 数据组装流程

```
┌─────────────────────────────────────────────────────────────┐
│                    并行获取数据                              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐ │
│  │ Coinalyze  │ │ Coinalyze  │ │ Coinalyze  │ │ Binance  │ │
│  │    OI      │ │ Liquidation│ │  Funding   │ │ Sentiment│ │
│  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └────┬─────┘ │
│        │              │              │             │        │
│        └──────────────┴──────────────┴─────────────┘        │
│                           │                                  │
│                           ▼                                  │
│                  ┌─────────────────┐                        │
│                  │   格式转换      │                        │
│                  │ BTC→USD, 时间戳 │                        │
│                  └────────┬────────┘                        │
│                           │                                  │
│                           ▼                                  │
│                  ┌─────────────────┐                        │
│                  │   组装 AI 输入   │                        │
│                  └─────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 代码模板

```python
# utils/ai_data_assembler.py

import asyncio
from typing import Dict, Any, List, Optional


class AIDataAssembler:
    """
    AI 数据组装器

    负责:
    1. 并行获取外部数据
    2. 格式转换 (Coinalyze → 统一格式)
    3. 组装最终数据结构
    """

    def __init__(self, order_flow_processor, coinalyze_client, sentiment_client):
        self.order_flow = order_flow_processor
        self.coinalyze = coinalyze_client
        self.sentiment = sentiment_client

        # OI 变化率计算缓存
        self._last_oi_usd: float = 0.0

    async def assemble(self, klines: List, technical: Dict,
                       position: Dict) -> Dict[str, Any]:
        """
        组装完整的 AI 输入数据

        Args:
            klines: Binance K线数据
            technical: 技术指标数据
            position: 当前持仓信息

        Returns:
            完整的 AI 输入数据字典
        """
        # 并行获取外部数据
        tasks = [
            self.coinalyze.get_open_interest(),
            self.coinalyze.get_liquidations(),
            self.coinalyze.get_funding_rate(),
            self.sentiment.get_long_short_ratio(),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        oi_raw, liq_raw, funding_raw, sentiment = results

        # 处理订单流
        order_flow_data = self.order_flow.process_klines(klines)

        # 获取当前价格
        current_price = float(klines[-1][4]) if klines else 0

        # 格式转换
        derivatives = self._convert_derivatives(
            oi_raw, liq_raw, funding_raw, current_price
        )

        # 组装数据
        return {
            "price": {
                "current": current_price,
                "change_24h_pct": self._calc_change(klines),
            },
            "technical": technical,
            "order_flow": order_flow_data,
            "derivatives": derivatives,
            "sentiment": sentiment if not isinstance(sentiment, Exception) else {},
            "current_position": position,
        }

    def _convert_derivatives(self, oi_raw, liq_raw, funding_raw,
                              current_price: float) -> Dict[str, Any]:
        """
        Coinalyze API → 统一格式转换
        """
        result = {
            "open_interest": None,
            "liquidations_1h": None,
            "funding_rate": None,
        }

        # OI 转换 (BTC → USD)
        if oi_raw and not isinstance(oi_raw, Exception):
            try:
                oi_btc = float(oi_raw.get('value', 0))
                oi_usd = oi_btc * current_price if current_price > 0 else 0

                # 计算变化率
                change_pct = None
                if self._last_oi_usd > 0 and oi_usd > 0:
                    change_pct = round(
                        (oi_usd - self._last_oi_usd) / self._last_oi_usd * 100, 2
                    )
                self._last_oi_usd = oi_usd

                result["open_interest"] = {
                    "total_usd": oi_usd,
                    "change_pct": change_pct,
                }
            except Exception as e:
                print(f"⚠️ OI parse error: {e}")

        # Funding 转换
        if funding_raw and not isinstance(funding_raw, Exception):
            try:
                result["funding_rate"] = {
                    "current": float(funding_raw.get('value', 0)),
                }
            except Exception as e:
                print(f"⚠️ Funding parse error: {e}")

        # Liquidation 转换 (嵌套结构)
        if liq_raw and not isinstance(liq_raw, Exception):
            try:
                history = liq_raw.get('history', [])
                if history:
                    item = history[-1]
                    result["liquidations_1h"] = {
                        "long_usd": float(item.get('l', 0)),
                        "short_usd": float(item.get('s', 0)),
                    }
            except Exception as e:
                print(f"⚠️ Liquidation parse error: {e}")

        return result

    def _calc_change(self, klines: List) -> float:
        """计算 24h 涨跌幅"""
        if len(klines) < 2:
            return 0.0
        old_close = float(klines[0][4])
        new_close = float(klines[-1][4])
        return round((new_close - old_close) / old_close * 100, 2) if old_close > 0 else 0.0
```

---

## 五、单元测试 (tests/test_multi_timeframe.py)

### 5.1 测试范围

| 测试类 | 测试内容 |
|--------|----------|
| `TestMultiTimeframeManager` | 核心管理器初始化、状态管理 |
| `TestBarTypeRouting` | Bar 路由到正确的层 |
| `TestRiskStateTransitions` | 趋势层状态转换 |
| `TestDecisionStateTransitions` | 决策层状态转换 |
| `TestBackwardCompatibility` | 禁用时的向后兼容 |

### 5.2 代码模板

```python
# tests/test_multi_timeframe.py

import pytest
from unittest.mock import Mock, MagicMock
from indicators.multi_timeframe_manager import (
    MultiTimeframeManager,
    RiskState,
    DecisionState,
)


class TestMultiTimeframeManager:
    """MultiTimeframeManager 核心测试"""

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
            "trend_layer": {"sma_period": 200},
            "decision_layer": {"timeframe": "4h"},
            "execution_layer": {"rsi_entry_min": 35, "rsi_entry_max": 65},
        }
        manager = MultiTimeframeManager(config)

        assert manager.enabled
        assert manager._risk_state == RiskState.RISK_OFF  # 默认状态


class TestRiskStateTransitions:
    """趋势层状态转换测试"""

    def test_risk_on_conditions(self):
        """测试 RISK_ON 条件"""
        # Price > SMA_200 且 MACD > 0 → RISK_ON
        config = {"enabled": True}
        manager = MultiTimeframeManager(config)

        # Mock 技术数据
        tech_data = {
            "sma_200": 95000,
            "macd": 150,
        }
        current_price = 100000  # > SMA_200

        manager.evaluate_risk_state(current_price, tech_data)
        assert manager.get_risk_state() == RiskState.RISK_ON

    def test_risk_off_price_below_sma(self):
        """测试价格低于 SMA → RISK_OFF"""
        config = {"enabled": True}
        manager = MultiTimeframeManager(config)

        tech_data = {
            "sma_200": 100000,
            "macd": 150,
        }
        current_price = 95000  # < SMA_200

        manager.evaluate_risk_state(current_price, tech_data)
        assert manager.get_risk_state() == RiskState.RISK_OFF


class TestDecisionStateTransitions:
    """决策层状态转换测试"""

    def test_allow_long(self):
        """测试 ALLOW_LONG 设置"""
        config = {"enabled": True}
        manager = MultiTimeframeManager(config)

        manager.set_decision_state(DecisionState.ALLOW_LONG, "HIGH")

        assert manager.get_decision_state() == DecisionState.ALLOW_LONG
        assert manager.get_decision_confidence() == "HIGH"

    def test_allow_short(self):
        """测试 ALLOW_SHORT 设置"""
        config = {"enabled": True}
        manager = MultiTimeframeManager(config)

        manager.set_decision_state(DecisionState.ALLOW_SHORT, "MEDIUM")

        assert manager.get_decision_state() == DecisionState.ALLOW_SHORT


class TestBackwardCompatibility:
    """向后兼容性测试"""

    def test_disabled_mode(self):
        """测试禁用时系统行为不变"""
        config = {"enabled": False}
        manager = MultiTimeframeManager(config)

        assert not manager.enabled

        # route_bar 应返回 "disabled"
        mock_bar = Mock()
        result = manager.route_bar(mock_bar)
        assert result == "disabled"
```

---

## 六、集成步骤

### 6.1 实现顺序

```
Step 1: 创建 utils/coinalyze_client.py
        └─ 配置 COINALYZE_API_KEY
        └─ 测试 API 连接

Step 2: 创建 utils/order_flow_processor.py
        └─ 单元测试

Step 3: 创建 utils/ai_data_assembler.py
        └─ 集成 coinalyze + order_flow

Step 4: 修改 agents/multi_agent_analyzer.py
        └─ 接收并使用新数据字段

Step 5: 修改 strategy/deepseek_strategy.py
        └─ 在 on_timer 中调用数据组装器

Step 6: 创建 tests/test_multi_timeframe.py
        └─ 完整测试覆盖
```

### 6.2 配置更新

**~/.env.aitrader**:
```bash
COINALYZE_API_KEY=your_key_here
```

**configs/base.yaml**:
```yaml
order_flow:
  enabled: true
  coinalyze:
    enabled: true
    timeout: 10
    symbol: "BTCUSDT_PERP.A"
```

---

## 七、预期效果

### 7.1 AI 输入数据对比

**当前 (无订单流)**:
```json
{
  "technical": {"rsi": 55, "macd": 100},
  "sentiment": {"long_short_ratio": 1.2}
}
```

**完整实现后**:
```json
{
  "technical": {"rsi": 55, "macd": 100},
  "sentiment": {"long_short_ratio": 1.2},
  "order_flow": {
    "buy_ratio": 0.58,
    "cvd_trend": "RISING",
    "avg_trade_usdt": 1500
  },
  "derivatives": {
    "open_interest": {"total_usd": 18500000000, "change_pct": 3.5},
    "funding_rate": {"current": 0.0008},
    "liquidations_1h": {"long_usd": 2500000, "short_usd": 1800000}
  }
}
```

### 7.2 决策质量提升

| 数据类型 | 提供的信息 | 决策价值 |
|----------|-----------|----------|
| `buy_ratio` | 买盘主导程度 | 确认趋势强度 |
| `cvd_trend` | 资金流向 | 判断真假突破 |
| `open_interest` | 持仓量变化 | 趋势持续性 |
| `funding_rate` | 市场情绪 | 过热/过冷信号 |
| `liquidations` | 清算数据 | 极端行情预警 |
