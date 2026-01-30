# MTF 方案未实现功能清单

> **版本说明**: 此清单创建于 v3.2.9 时期。当前实现版本为 **v3.6**。
> v3.6 已完成：完整数据覆盖 (period_high/low/change_pct, volume_usdt)、diagnose_realtime.py v11.10。

## 文档信息

| 项目 | 值 |
|------|-----|
| 创建日期 | 2026-01-27 |
| 最后更新 | 2026-01-30 |
| 基于文档 | docs/MULTI_TIMEFRAME_IMPLEMENTATION_PLAN.md v3.6 |
| 当前完成度 | ~85% |
| 版本 | v2.2 (更新至 v3.6 完整数据覆盖) |

---

## 🔴 重要更新 (v2.1)

### v2.1 更新 (完整修改差异)

| 问题 | 等级 | 修复内容 |
|------|------|----------|
| 接口签名冲突 | P0 | 第十一章: 完整代码修改差异 |
| 调用链断裂 | P0 | 11.1: deepseek_strategy.py 完整修改 |
| 格式化方法调用缺失 | P1 | 11.2: multi_agent_analyzer.py 完整修改 |
| MTF 方法签名不兼容 | P1 | 11.3: multi_timeframe_manager.py 完整修改 |
| 数据降级策略不明确 | P1 | 第十二章: 降级规则和过滤器优先级 |
| 配置项缺失 | P2 | 第十三章: DeepSeekStrategyConfig 扩展 |

### v2.0 更新 (架构修复)

| 问题 | 等级 | 修复内容 |
|------|------|----------|
| 异步/同步架构冲突 | P0 | CoinalyzeClient 改为同步 (requests) |
| AI Prompt 整合缺失 | P0 | 新增第八章: AI 整合方案 |
| K线数据格式不匹配 | P1 | OrderFlowProcessor 支持双格式 + BinanceKlineClient |
| MTF 协同关系未定义 | P1 | 新增第九章: MTF 协同设计 |

---

## 🚀 实现路线图 (Quick Reference)

### 实施阶段

| Phase | 任务 | 优先级 | 预计时间 | 文档章节 |
|-------|------|--------|----------|----------|
| **1. 接口扩展** | 修改 `multi_agent_analyzer.analyze()` 签名 | P0 | 0.5 天 | 8.2.1, 11.2.1 |
|  | 添加 `_format_order_flow_report()` 方法 | P0 | 0.5 天 | 8.2.2 |
|  | 添加 `_format_derivatives_report()` 方法 | P0 | 0.5 天 | 8.2.3 |
| **2. 数据获取** | 实现 `BinanceKlineClient` | P2 | 0.5 天 | 3.5 |
|  | 实现 `OrderFlowProcessor` | P2 | 0.5 天 | 3.6 |
|  | 实现 `CoinalyzeClient` | P2 | 1.0 天 | 2.5 |
| **3. 数据整合** | 实现 `AIDataAssembler` | P2 | 1.0 天 | 4.3 |
|  | 修改 `deepseek_strategy.py` 调用链 | P1 | 0.5 天 | 11.1 |
| **4. MTF 激活** | 在 strategy 中启用 MTF | P1 | 0.5 天 | 11.3 |
|  | 配置调整和测试 | P1 | 1.0 天 | 第十三章 |

**总计**: 6-7 个工作日 (包含测试)

### 关键代码索引

| 功能 | 文档章节 | 代码行数 | 状态 |
|------|----------|----------|------|
| 接口签名修复 | 8.2.1, 11.2.1 | ~10 行 | ✅ 代码已提供 |
| _format_order_flow_report() | 8.2.2 | ~50 行 | ✅ 代码已提供 |
| _format_derivatives_report() | 8.2.3 | ~50 行 | ✅ 代码已提供 |
| BinanceKlineClient | 3.5 | ~80 行 | ✅ 代码已提供 |
| OrderFlowProcessor | 3.6 | ~100 行 | ✅ 代码已提供 |
| CoinalyzeClient | 2.5 | ~200 行 | ✅ 代码已提供 |
| AIDataAssembler | 4.3 | ~150 行 | ✅ 代码已提供 |
| 测试模板 | 5.2 | ~300 行 | ✅ 代码已提供 |

**总代码量**: ~940 行 (含测试)

### 实施 Checklist

#### Phase 1: 接口扩展 ✅
- [ ] 修改 `multi_agent_analyzer.py:198` 的 `analyze()` 签名 (添加 order_flow_report, derivatives_report 参数)
- [ ] 添加 `_format_order_flow_report()` 方法 (第 8.2.2 节)
- [ ] 添加 `_format_derivatives_report()` 方法 (第 8.2.3 节)
- [ ] 更新 Bull/Bear Prompt (第 11.2.4-11.2.5 节)
- [ ] 运行单元测试: `pytest tests/test_multi_agent.py -v`

#### Phase 2: 数据获取 ✅
- [ ] 创建 `utils/binance_kline_client.py` (第 3.5 节代码模板)
- [ ] 创建 `utils/order_flow_processor.py` (第 3.6 节代码模板)
- [ ] 创建 `utils/coinalyze_client.py` (第 2.5 节代码模板)
- [ ] 在 `~/.env.aitrader` 添加 `COINALYZE_API_KEY=xxx` (如有 API key)
- [ ] 单元测试: 验证数据获取和降级逻辑

#### Phase 3: 数据整合 ✅
- [ ] 创建 `utils/ai_data_assembler.py` (第 4.3 节代码模板)
- [ ] 修改 `deepseek_strategy.py` __init__ 方法 (第 11.1.2 节)
- [ ] 修改 `deepseek_strategy.py` on_timer() 方法 (第 11.1.3-11.1.4 节)
- [ ] 验证数据流: `python3 scripts/diagnose_realtime.py`

#### Phase 4: MTF 激活 ✅
- [ ] 确认 `configs/base.yaml` 中 `multi_timeframe.enabled: true` (已默认启用)
- [ ] 运行回测验证: `python3 main_backtest.py --days 30`
- [ ] 观察 AI 输出: 确认 "ORDER FLOW ANALYSIS" 和 "DERIVATIVES MARKET DATA" 出现
- [ ] 逐步上线: Week 1 (仅订单流) → Week 2 (+衍生品) → Week 3 (完整 MTF)

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

### 2.5 代码模板 (同步版本 - 兼容 on_timer)

> ⚠️ **v2.0 修复**: 改用 `requests` 同步实现，兼容 NautilusTrader 的同步 `on_timer()` 回调。
> 参考 `utils/sentiment_client.py` 的实现模式。

```python
# utils/coinalyze_client.py

import requests
import time
import logging
from typing import Optional, Dict, Any
import os


class CoinalyzeClient:
    """
    Coinalyze API 客户端 (同步版本)

    获取衍生品数据: OI, 清算, 资金费率

    设计原则:
    - 同步调用，兼容 on_timer() 回调
    - 参考 sentiment_client.py 的错误处理模式
    - 支持指数退避重试
    """

    BASE_URL = "https://api.coinalyze.net/v1"
    DEFAULT_SYMBOL = "BTCUSDT_PERP.A"

    def __init__(
        self,
        api_key: str = None,
        timeout: int = 10,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        logger: logging.Logger = None,
    ):
        """
        初始化 Coinalyze 客户端

        Parameters
        ----------
        api_key : str
            API Key (从 ~/.env.aitrader 的 COINALYZE_API_KEY 读取)
        timeout : int
            请求超时 (秒)
        max_retries : int
            最大重试次数
        retry_delay : float
            重试基础延迟 (秒)，使用指数退避
        logger : Logger
            日志记录器
        """
        self.api_key = api_key or os.getenv("COINALYZE_API_KEY")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = logger or logging.getLogger(__name__)
        self._enabled = bool(self.api_key)

        if not self._enabled:
            self.logger.warning("⚠️ COINALYZE_API_KEY not set, Coinalyze client disabled")

    def _get_headers(self) -> Dict[str, str]:
        """构建请求头"""
        return {"api_key": self.api_key} if self.api_key else {}

    def _request_with_retry(
        self,
        endpoint: str,
        params: Dict[str, Any],
    ) -> Optional[Dict]:
        """
        带重试的 HTTP 请求

        Parameters
        ----------
        endpoint : str
            API 端点 (如 "/open-interest")
        params : Dict
            查询参数

        Returns
        -------
        Optional[Dict]
            API 响应，失败返回 None
        """
        url = f"{self.BASE_URL}{endpoint}"
        headers = self._get_headers()

        for attempt in range(self.max_retries + 1):
            try:
                response = requests.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )

                if response.status_code == 200:
                    data = response.json()
                    return data[0] if data else None

                elif response.status_code == 429:
                    self.logger.warning("⚠️ Coinalyze rate limit reached (429)")
                    # 速率限制时等待更长时间
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay * (2 ** attempt) * 2)
                        continue
                    return None

                else:
                    self.logger.warning(
                        f"⚠️ Coinalyze API error: {response.status_code}"
                    )
                    return None

            except requests.exceptions.Timeout:
                self.logger.warning(
                    f"⚠️ Coinalyze timeout (attempt {attempt + 1}/{self.max_retries + 1})"
                )
            except requests.exceptions.RequestException as e:
                self.logger.warning(
                    f"⚠️ Coinalyze request error (attempt {attempt + 1}): {e}"
                )

            # 指数退避
            if attempt < self.max_retries:
                time.sleep(self.retry_delay * (2 ** attempt))

        return None

    def get_open_interest(self, symbol: str = None) -> Optional[Dict]:
        """
        获取当前 Open Interest

        Returns:
            {
                "symbol": "BTCUSDT_PERP.A",
                "value": 102199.59,       # BTC 数量 (非 USD!)
                "update": 1769417410150   # 毫秒时间戳
            }

        注意: value 是 BTC 数量，需要乘以当前价格转换为 USD
        """
        if not self._enabled:
            return None

        symbol = symbol or self.DEFAULT_SYMBOL
        return self._request_with_retry(
            endpoint="/open-interest",
            params={"symbols": symbol},
        )

    def get_liquidations(
        self,
        symbol: str = None,
        interval: str = "1hour",
    ) -> Optional[Dict]:
        """
        获取清算历史

        Args:
            symbol: 交易对 (默认 BTCUSDT_PERP.A)
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
        return self._request_with_retry(
            endpoint="/liquidation-history",
            params={
                "symbols": symbol,
                "interval": interval,
                "from": int(time.time()) - 3600,  # 秒!
                "to": int(time.time()),
            },
        )

    def get_funding_rate(self, symbol: str = None) -> Optional[Dict]:
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
        return self._request_with_retry(
            endpoint="/funding-rate",
            params={"symbols": symbol},
        )

    def fetch_all(self, symbol: str = None) -> Dict[str, Any]:
        """
        一次性获取所有衍生品数据 (便捷方法)

        Returns:
            {
                "open_interest": {...} or None,
                "liquidations": {...} or None,
                "funding_rate": {...} or None,
                "enabled": bool,
            }
        """
        if not self._enabled:
            return {
                "open_interest": None,
                "liquidations": None,
                "funding_rate": None,
                "enabled": False,
            }

        return {
            "open_interest": self.get_open_interest(symbol),
            "liquidations": self.get_liquidations(symbol),
            "funding_rate": self.get_funding_rate(symbol),
            "enabled": True,
        }

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

> ⚠️ **v2.0 修复**: 支持双格式输入 (Binance 原始 12 列 + 本地 Dict 格式)

### 3.2 数据来源

**核心问题**: 现有 `indicator_manager.get_kline_data()` 返回的 Dict 格式不包含订单流所需字段:
- ❌ 无 `taker_buy_volume` (列[9])
- ❌ 无 `quote_volume` (列[7])
- ❌ 无 `trades_count` (列[8])

**解决方案**: 新增 `BinanceKlineClient` 直接从 Binance API 获取完整 12 列数据。

### 3.3 K线 12 列 (Binance 原始格式)

```
[0] open_time        [4] close           [8] trades_count
[1] open             [5] volume          [9] taker_buy_volume ⭐
[2] high             [6] close_time      [10] taker_buy_quote
[3] low              [7] quote_volume    [11] ignore
```

### 3.4 计算的指标

| 指标 | 计算方式 | 含义 |
|------|----------|------|
| `buy_ratio` | taker_buy_volume / volume | >0.5 表示买盘主导 |
| `avg_trade_usdt` | quote_volume / trades_count | 平均成交额 |
| `cvd_trend` | 累积 (buy - sell) 的趋势 | CVD 方向 |

### 3.5 Binance K线客户端 (新增)

```python
# utils/binance_kline_client.py

import requests
import logging
from typing import List, Optional, Dict, Any


class BinanceKlineClient:
    """
    Binance K线数据客户端

    获取完整 12 列 K线数据，包含订单流所需字段:
    - taker_buy_volume (列[9])
    - quote_volume (列[7])
    - trades_count (列[8])

    注意: 此接口无需 API Key，是公开数据
    """

    # Binance Futures API (永续合约)
    BASE_URL = "https://fapi.binance.com"

    def __init__(
        self,
        timeout: int = 10,
        logger: logging.Logger = None,
    ):
        self.timeout = timeout
        self.logger = logger or logging.getLogger(__name__)

    def get_klines(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        limit: int = 50,
    ) -> Optional[List[List]]:
        """
        获取 K线数据 (完整 12 列)

        Parameters
        ----------
        symbol : str
            交易对 (如 BTCUSDT)
        interval : str
            时间周期 (1m/5m/15m/1h/4h/1d)
        limit : int
            获取数量 (最大 1500)

        Returns
        -------
        List[List]
            Binance 原始 K线数据 (12 列)，失败返回 None

        示例返回:
        [
            [
                1499040000000,      # [0] open_time (ms)
                "0.01634000",       # [1] open
                "0.80000000",       # [2] high
                "0.01575800",       # [3] low
                "0.01577100",       # [4] close
                "148976.11427815",  # [5] volume
                1499644799999,      # [6] close_time (ms)
                "2434.19055334",    # [7] quote_volume ⭐
                308,                # [8] trades_count ⭐
                "1756.87402397",    # [9] taker_buy_volume ⭐
                "28.46694368",      # [10] taker_buy_quote
                "17928899.62484339" # [11] ignore
            ],
            ...
        ]
        """
        try:
            url = f"{self.BASE_URL}/fapi/v1/klines"
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            }

            response = requests.get(url, params=params, timeout=self.timeout)

            if response.status_code == 200:
                return response.json()
            else:
                self.logger.warning(
                    f"⚠️ Binance klines API error: {response.status_code}"
                )
                return None

        except Exception as e:
            self.logger.warning(f"⚠️ Binance klines fetch error: {e}")
            return None

    def get_current_price(self, symbol: str = "BTCUSDT") -> Optional[float]:
        """获取当前价格"""
        klines = self.get_klines(symbol=symbol, interval="1m", limit=1)
        if klines and len(klines) > 0:
            return float(klines[-1][4])  # close price
        return None
```

### 3.6 订单流处理器代码模板 (支持双格式)

```python
# utils/order_flow_processor.py

import logging
from typing import List, Dict, Any, Union


class OrderFlowProcessor:
    """
    订单流数据处理器

    从 Binance K线数据计算订单流指标

    v2.0 更新:
    - 支持 Binance 原始 12 列格式 (List[List])
    - 支持本地 Dict 格式 (List[Dict]) - 降级模式，无订单流数据
    """

    def __init__(self, logger: logging.Logger = None):
        self._cvd_history: List[float] = []
        self.logger = logger or logging.getLogger(__name__)

    def process_klines(
        self,
        klines: Union[List[List], List[Dict]],
    ) -> Dict[str, Any]:
        """
        处理 K线数据，计算订单流指标

        Args:
            klines: K线数据，支持两种格式:
                - List[List]: Binance 原始 12 列格式 (完整订单流数据)
                - List[Dict]: 本地 Dict 格式 (降级模式，无订单流数据)

        Returns:
            {
                "buy_ratio": 0.55,           # 买盘占比
                "avg_trade_usdt": 1250.5,    # 平均成交额
                "volume_usdt": 125000000,    # 总成交额
                "trades_count": 100000,      # 成交笔数
                "cvd_trend": "RISING",       # CVD 趋势
                "recent_10_bars": [...],     # 最近10根bar的买盘比
                "data_source": "binance_raw" | "local_dict",
            }
        """
        if not klines or len(klines) == 0:
            return self._default_result()

        # 检测数据格式
        if isinstance(klines[0], list):
            return self._process_binance_format(klines)
        elif isinstance(klines[0], dict):
            return self._process_dict_format(klines)
        else:
            self.logger.warning(f"⚠️ Unknown kline format: {type(klines[0])}")
            return self._default_result()

    def _process_binance_format(self, klines: List[List]) -> Dict[str, Any]:
        """
        处理 Binance 原始 12 列格式 (完整订单流数据)
        """
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
            "data_source": "binance_raw",
        }

    def _process_dict_format(self, klines: List[Dict]) -> Dict[str, Any]:
        """
        处理本地 Dict 格式 (降级模式)

        注意: Dict 格式不包含 taker_buy_volume，无法计算真实订单流
        返回中性默认值，标记为降级数据源
        """
        self.logger.debug(
            "OrderFlowProcessor: Using Dict format (degraded mode, no order flow data)"
        )

        # 从 Dict 格式提取基础信息
        latest = klines[-1]
        volume = latest.get('volume', 0)

        return {
            "buy_ratio": 0.5,  # 中性值 (无数据)
            "avg_trade_usdt": 0,
            "volume_usdt": volume,  # 只有 volume 可用
            "trades_count": 0,
            "cvd_trend": "NEUTRAL",
            "recent_10_bars": [],
            "data_source": "local_dict",  # 标记为降级模式
            "_warning": "Dict format has no order flow data, using neutral values",
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
            "data_source": "none",
        }

    def reset_cvd_history(self):
        """重置 CVD 历史 (用于测试或重启后)"""
        self._cvd_history = []
```

---

## 四、AI 数据组装器 (utils/ai_data_assembler.py)

### 4.1 功能说明

顺序获取所有外部数据，转换格式，组装成 AI 输入。

> ⚠️ **v2.0 修复**: 改为同步版本，兼容 on_timer() 回调

### 4.2 数据组装流程

```
┌─────────────────────────────────────────────────────────────┐
│                    顺序获取数据 (同步)                        │
│  ┌────────────┐                                             │
│  │ Binance    │──► 获取完整 K线 (12列)                       │
│  │ Klines     │                                             │
│  └─────┬──────┘                                             │
│        │                                                     │
│        ▼                                                     │
│  ┌────────────┐                                             │
│  │ OrderFlow  │──► 计算 buy_ratio, cvd_trend                │
│  │ Processor  │                                             │
│  └─────┬──────┘                                             │
│        │                                                     │
│        ▼                                                     │
│  ┌────────────┐                                             │
│  │ Coinalyze  │──► OI, Funding, Liquidations                │
│  │ Client     │    (fetch_all 一次性获取)                    │
│  └─────┬──────┘                                             │
│        │                                                     │
│        ▼                                                     │
│  ┌────────────┐                                             │
│  │ Sentiment  │──► Long/Short Ratio                         │
│  │ Fetcher    │                                             │
│  └─────┬──────┘                                             │
│        │                                                     │
│        ▼                                                     │
│  ┌─────────────────┐                                        │
│  │   格式转换      │                                        │
│  │ BTC→USD, 时间戳 │                                        │
│  └────────┬────────┘                                        │
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────┐                                        │
│  │   组装 AI 输入   │                                        │
│  └─────────────────┘                                        │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 代码模板 (同步版本)

```python
# utils/ai_data_assembler.py

import logging
from typing import Dict, Any, List, Optional, Union


class AIDataAssembler:
    """
    AI 数据组装器 (同步版本)

    负责:
    1. 顺序获取外部数据 (Binance K线、Coinalyze、Sentiment)
    2. 格式转换 (Coinalyze → 统一格式, BTC → USD)
    3. 组装最终数据结构

    v2.0 更新:
    - 改为同步实现，兼容 on_timer() 回调
    - 支持双格式 K线输入
    - 添加数据新鲜度检查
    """

    def __init__(
        self,
        binance_kline_client,
        order_flow_processor,
        coinalyze_client,
        sentiment_client,
        logger: logging.Logger = None,
    ):
        """
        初始化数据组装器

        Parameters
        ----------
        binance_kline_client : BinanceKlineClient
            Binance K线客户端 (获取完整 12 列数据)
        order_flow_processor : OrderFlowProcessor
            订单流处理器
        coinalyze_client : CoinalyzeClient
            Coinalyze 衍生品客户端
        sentiment_client : SentimentDataFetcher
            情绪数据客户端
        """
        self.binance_klines = binance_kline_client
        self.order_flow = order_flow_processor
        self.coinalyze = coinalyze_client
        self.sentiment = sentiment_client
        self.logger = logger or logging.getLogger(__name__)

        # OI 变化率计算缓存
        self._last_oi_usd: float = 0.0

    def assemble(
        self,
        technical_data: Dict[str, Any],
        position_data: Optional[Dict[str, Any]] = None,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
    ) -> Dict[str, Any]:
        """
        组装完整的 AI 输入数据 (同步方法)

        Parameters
        ----------
        technical_data : Dict
            技术指标数据 (来自 indicator_manager.get_technical_data())
        position_data : Dict, optional
            当前持仓信息
        symbol : str
            交易对
        interval : str
            K线周期

        Returns
        -------
        Dict
            完整的 AI 输入数据字典
        """
        # Step 1: 获取 Binance 完整 K线 (12 列)
        raw_klines = self.binance_klines.get_klines(
            symbol=symbol,
            interval=interval,
            limit=50,
        )

        # Step 2: 处理订单流数据
        if raw_klines:
            order_flow_data = self.order_flow.process_klines(raw_klines)
            current_price = float(raw_klines[-1][4])
        else:
            self.logger.warning("⚠️ Failed to get Binance klines, using degraded mode")
            order_flow_data = self.order_flow._default_result()
            current_price = technical_data.get('price', 0)

        # Step 3: 获取 Coinalyze 衍生品数据
        coinalyze_data = self.coinalyze.fetch_all()

        # Step 4: 转换衍生品数据格式
        derivatives = self._convert_derivatives(
            oi_raw=coinalyze_data.get('open_interest'),
            liq_raw=coinalyze_data.get('liquidations'),
            funding_raw=coinalyze_data.get('funding_rate'),
            current_price=current_price,
        )

        # Step 5: 获取情绪数据
        sentiment_data = self.sentiment.fetch()
        if sentiment_data is None:
            sentiment_data = self._default_sentiment()

        # Step 6: 组装最终数据
        return {
            "price": {
                "current": current_price,
                "change_pct": self._calc_change(raw_klines) if raw_klines else 0,
            },
            "technical": technical_data,
            "order_flow": order_flow_data,
            "derivatives": derivatives,
            "sentiment": sentiment_data,
            "current_position": position_data or {},
            "_metadata": {
                "kline_source": "binance_raw" if raw_klines else "none",
                "coinalyze_enabled": self.coinalyze.is_enabled(),
            },
        }

    def _convert_derivatives(
        self,
        oi_raw: Optional[Dict],
        liq_raw: Optional[Dict],
        funding_raw: Optional[Dict],
        current_price: float,
    ) -> Dict[str, Any]:
        """
        Coinalyze API → 统一格式转换
        """
        result = {
            "open_interest": None,
            "liquidations_1h": None,
            "funding_rate": None,
        }

        # OI 转换 (BTC → USD)
        if oi_raw:
            try:
                oi_btc = float(oi_raw.get('value', 0))
                oi_usd = oi_btc * current_price if current_price > 0 else 0

                # 计算变化率 (首次为 None)
                change_pct = None
                if self._last_oi_usd > 0 and oi_usd > 0:
                    change_pct = round(
                        (oi_usd - self._last_oi_usd) / self._last_oi_usd * 100, 2
                    )
                self._last_oi_usd = oi_usd

                result["open_interest"] = {
                    "total_usd": round(oi_usd, 0),
                    "total_btc": round(oi_btc, 2),
                    "change_pct": change_pct,
                }
            except Exception as e:
                self.logger.warning(f"⚠️ OI parse error: {e}")

        # Funding 转换
        if funding_raw:
            try:
                funding_value = float(funding_raw.get('value', 0))
                result["funding_rate"] = {
                    "current": funding_value,
                    "current_pct": round(funding_value * 100, 4),  # 转为百分比
                    "interpretation": self._interpret_funding(funding_value),
                }
            except Exception as e:
                self.logger.warning(f"⚠️ Funding parse error: {e}")

        # Liquidation 转换 (嵌套结构)
        if liq_raw:
            try:
                history = liq_raw.get('history', [])
                if history:
                    item = history[-1]
                    long_liq = float(item.get('l', 0))
                    short_liq = float(item.get('s', 0))
                    total = long_liq + short_liq

                    result["liquidations_1h"] = {
                        "long_usd": round(long_liq, 0),
                        "short_usd": round(short_liq, 0),
                        "total_usd": round(total, 0),
                        "long_ratio": round(long_liq / total, 2) if total > 0 else 0.5,
                    }
            except Exception as e:
                self.logger.warning(f"⚠️ Liquidation parse error: {e}")

        return result

    def _interpret_funding(self, funding_rate: float) -> str:
        """解读资金费率"""
        if funding_rate > 0.001:  # > 0.1%
            return "VERY_BULLISH"
        elif funding_rate > 0.0005:  # > 0.05%
            return "BULLISH"
        elif funding_rate < -0.001:  # < -0.1%
            return "VERY_BEARISH"
        elif funding_rate < -0.0005:  # < -0.05%
            return "BEARISH"
        else:
            return "NEUTRAL"

    def _calc_change(self, klines: List) -> float:
        """计算涨跌幅 (基于 K线数据)"""
        if not klines or len(klines) < 2:
            return 0.0
        old_close = float(klines[0][4])
        new_close = float(klines[-1][4])
        return round((new_close - old_close) / old_close * 100, 2) if old_close > 0 else 0.0

    def _default_sentiment(self) -> Dict[str, Any]:
        """默认情绪数据 (中性)"""
        return {
            'positive_ratio': 0.5,
            'negative_ratio': 0.5,
            'net_sentiment': 0.0,
            'long_short_ratio': 1.0,
            'source': 'default_neutral',
        }
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

---

## 八、AI Prompt 整合方案 (P0 修复)

> ⚠️ **v2.0 新增**: 此章节解决"新数据不会被 AI 看到"的关键问题

### 8.1 问题分析

**现状**: `multi_agent_analyzer.py` 的 `analyze()` 方法仅接收 `technical_report` 和 `sentiment_report`

**影响**: 即使数据组装成功，订单流和衍生品数据也不会传递给 AI

### 8.2 修改方案

#### 8.2.1 扩展 `analyze()` 方法接口

```python
# agents/multi_agent_analyzer.py

def analyze(
    self,
    symbol: str,
    technical_report: Dict[str, Any],
    sentiment_report: Optional[Dict[str, Any]] = None,
    current_position: Optional[Dict[str, Any]] = None,
    price_data: Optional[Dict[str, Any]] = None,
    # ========== v2.0 新增参数 ==========
    order_flow_report: Optional[Dict[str, Any]] = None,
    derivatives_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
```

#### 8.2.2 新增 `_format_order_flow_report()` 方法

```python
def _format_order_flow_report(self, data: Optional[Dict[str, Any]]) -> str:
    """格式化订单流数据供 AI 使用"""
    if not data or data.get('data_source') == 'none':
        return "ORDER FLOW: Data not available"

    buy_ratio = data.get('buy_ratio', 0.5)
    cvd_trend = data.get('cvd_trend', 'NEUTRAL')
    avg_trade = data.get('avg_trade_usdt', 0)
    trades_count = data.get('trades_count', 0)
    recent_bars = data.get('recent_10_bars', [])

    # 解读买卖比
    if buy_ratio > 0.55:
        buy_interpretation = "BULLISH (buyers dominating)"
    elif buy_ratio < 0.45:
        buy_interpretation = "BEARISH (sellers dominating)"
    else:
        buy_interpretation = "NEUTRAL (balanced)"

    # 格式化最近 10 根 bar
    recent_str = ", ".join([f"{r:.1%}" for r in recent_bars[-5:]]) if recent_bars else "N/A"

    return f"""
ORDER FLOW ANALYSIS (Binance Taker Data):
- Buy Ratio: {buy_ratio:.1%} ({buy_interpretation})
- CVD Trend: {cvd_trend} ({'Accumulation' if cvd_trend == 'RISING' else 'Distribution' if cvd_trend == 'FALLING' else 'Sideways'})
- Avg Trade Size: ${avg_trade:,.0f} USDT
- Trade Count: {trades_count:,}
- Recent 5 Bars Buy Ratio: [{recent_str}]

INTERPRETATION:
- Buy Ratio > 55%: Strong buying pressure, confirms bullish momentum
- Buy Ratio < 45%: Strong selling pressure, confirms bearish momentum
- CVD RISING: Smart money accumulating, potential breakout
- CVD FALLING: Distribution phase, potential breakdown
"""
```

#### 8.2.3 新增 `_format_derivatives_report()` 方法

```python
def _format_derivatives_report(self, data: Optional[Dict[str, Any]]) -> str:
    """格式化衍生品数据供 AI 使用"""
    if not data:
        return "DERIVATIVES: Data not available"

    parts = ["DERIVATIVES MARKET DATA:"]

    # Open Interest
    oi = data.get('open_interest')
    if oi:
        oi_usd = oi.get('total_usd', 0)
        oi_change = oi.get('change_pct')
        change_str = f" ({oi_change:+.1f}%)" if oi_change is not None else ""
        parts.append(f"- Open Interest: ${oi_usd/1e9:.2f}B{change_str}")

        # OI 解读
        if oi_change is not None:
            if oi_change > 5:
                parts.append("  → OI Rising: New positions entering, trend strengthening")
            elif oi_change < -5:
                parts.append("  → OI Falling: Positions closing, trend weakening")

    # Funding Rate
    funding = data.get('funding_rate')
    if funding:
        rate = funding.get('current', 0)
        rate_pct = funding.get('current_pct', 0)
        interp = funding.get('interpretation', 'NEUTRAL')
        parts.append(f"- Funding Rate: {rate_pct:.4f}% ({interp})")

        # Funding 解读
        if rate > 0.001:
            parts.append("  → HIGH Funding: Market overheated, potential long squeeze")
        elif rate < -0.001:
            parts.append("  → NEGATIVE Funding: Shorts paying longs, potential short squeeze")

    # Liquidations
    liq = data.get('liquidations_1h')
    if liq:
        long_liq = liq.get('long_usd', 0)
        short_liq = liq.get('short_usd', 0)
        total = liq.get('total_usd', 0)
        long_ratio = liq.get('long_ratio', 0.5)

        parts.append(f"- Liquidations (1h): ${total/1e6:.1f}M total")
        parts.append(f"  → Long Liq: ${long_liq/1e6:.1f}M ({long_ratio:.0%})")
        parts.append(f"  → Short Liq: ${short_liq/1e6:.1f}M ({1-long_ratio:.0%})")

        # 清算解读
        if total > 50_000_000:  # > $50M
            parts.append("  → ⚠️ HIGH liquidations: Extreme volatility, be cautious")

    return "\n".join(parts)
```

#### 8.2.4 修改 Bull/Bear 辩论 Prompt

在 `_get_bull_argument()` 和 `_get_bear_argument()` 方法中添加新数据:

```python
def _get_bull_argument(
    self,
    symbol: str,
    technical_report: str,
    sentiment_report: str,
    order_flow_report: str,      # 新增
    derivatives_report: str,      # 新增
    history: str,
    bear_argument: str,
) -> str:
    """生成 Bull 分析师论点"""
    prompt = f"""You are a Bull Analyst advocating for LONG position on {symbol}.
Your task is to build a strong, evidence-based case for going LONG.

Key points to focus on:
- BULLISH Technical Signals: Price above SMAs, RSI recovering from oversold, MACD bullish crossover
- Order Flow Confirmation: Buy ratio > 50%, CVD rising
- Derivatives Support: OI rising with price, neutral/negative funding
- Growth Momentum: Breakout patterns, increasing volume, support holding
- Counter Bear Arguments: Use specific numbers to refute bearish concerns

Resources Available:

TECHNICAL ANALYSIS:
{technical_report}

{order_flow_report}

{derivatives_report}

{sentiment_report}

Previous Debate:
{history if history else "This is the opening argument."}

Last Bear Argument:
{bear_argument if bear_argument else "No bear argument yet - make your opening case."}

INSTRUCTIONS:
1. Present 2-3 compelling reasons for LONG
2. Use specific numbers from ALL data sources (technical, order flow, derivatives)
3. If bear made arguments, directly counter them with data
4. Be persuasive but factual

Deliver your argument now (2-3 paragraphs):"""

    return self._call_api_with_retry([
        {"role": "system", "content": "You are a professional Bull Analyst. Use order flow and derivatives data to strengthen your arguments."},
        {"role": "user", "content": prompt}
    ])
```

#### 8.2.5 修改 Judge 决策 Prompt

在 `_get_judge_decision()` 中扩展确认点计数:

```python
=== STEP 1: COUNT TECHNICAL CONFIRMATIONS (MANDATORY) ===

BULLISH Confirmations (count in Bull's arguments):
1. Price above SMA20 OR Price above SMA50
2. RSI < 60 (not overbought, has room to rise)
3. MACD > Signal (bullish crossover) OR MACD histogram > 0
4. Price near support level OR Price near BB lower band
5. Increasing volume OR bullish volume pattern mentioned
6. [NEW] Buy Ratio > 55% (order flow bullish)           # 新增
7. [NEW] CVD Trend = RISING (accumulation)              # 新增
8. [NEW] OI Rising + Price Rising (trend confirmation)  # 新增
9. [NEW] Funding Rate < 0.05% (not overheated)          # 新增

BEARISH Confirmations (count in Bear's arguments):
1. Price below SMA20 OR Price below SMA50
2. RSI > 40 (showing weakness or overbought)
3. MACD < Signal (bearish crossover) OR MACD histogram < 0
4. Price near resistance level OR Price near BB upper band
5. Decreasing volume OR bearish volume pattern mentioned
6. [NEW] Buy Ratio < 45% (order flow bearish)           # 新增
7. [NEW] CVD Trend = FALLING (distribution)             # 新增
8. [NEW] OI Falling (trend weakening)                   # 新增
9. [NEW] Funding Rate > 0.1% (overheated, squeeze risk) # 新增
```

### 8.3 完整修改差异

需要修改的文件:

| 文件 | 修改内容 |
|------|----------|
| `agents/multi_agent_analyzer.py` | 扩展 `analyze()` 接口，新增两个格式化方法 |
| `strategy/deepseek_strategy.py` | 在 `on_timer()` 中调用 `AIDataAssembler` 并传递新数据 |

### 8.4 调用示例

```python
# strategy/deepseek_strategy.py on_timer() 中

# 初始化组装器 (在 __init__ 中)
self.data_assembler = AIDataAssembler(
    binance_kline_client=BinanceKlineClient(),
    order_flow_processor=OrderFlowProcessor(),
    coinalyze_client=CoinalyzeClient(),
    sentiment_client=self.sentiment_fetcher,
)

# 在 on_timer() 中使用
ai_data = self.data_assembler.assemble(
    technical_data=technical_data,
    position_data=current_position,
)

# 调用 MultiAgent 分析
signal_data = self.multi_agent.analyze(
    symbol=self.symbol,
    technical_report=ai_data['technical'],
    sentiment_report=ai_data['sentiment'],
    current_position=ai_data['current_position'],
    price_data={'price': ai_data['price']['current']},
    # ========== 新增参数 ==========
    order_flow_report=ai_data['order_flow'],
    derivatives_report=ai_data['derivatives'],
)
```

---

## 九、MTF 协同设计 (P1 修复)

> ⚠️ **v2.0 新增**: 定义新数据源与现有 MTF 三层架构的协同关系

### 9.1 现有 MTF 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│  趋势层 (1D)                                                │
│  ├─ 指标: SMA_200, MACD                                     │
│  ├─ 输出: RiskState (RISK_ON / RISK_OFF)                   │
│  └─ 作用: 决定是否允许开仓                                  │
├─────────────────────────────────────────────────────────────┤
│  决策层 (4H)                                                │
│  ├─ 指标: RSI, MACD, SMA_20/50, BB                         │
│  ├─ 输出: DecisionState (ALLOW_LONG / ALLOW_SHORT / WAIT)  │
│  └─ 作用: AI 辩论决定方向                                   │
├─────────────────────────────────────────────────────────────┤
│  执行层 (15M)                                               │
│  ├─ 指标: RSI, EMA, Support/Resistance                     │
│  ├─ 输出: 入场时机确认                                      │
│  └─ 作用: 精确入场点                                        │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 新数据源归属定义

| 数据源 | 归属层 | 理由 | 使用方式 |
|--------|--------|------|----------|
| **buy_ratio** | 执行层 (15M) | 短期买卖力量，用于入场确认 | RSI + buy_ratio 共振 |
| **cvd_trend** | 决策层 (4H) | 中期资金流向，影响方向判断 | 辩论额外证据 |
| **open_interest** | 趋势层 (1D) | 长期持仓变化，趋势强度 | RISK_ON 额外条件 |
| **funding_rate** | 决策层 (4H) | 市场情绪周期 (8h 结算) | 过热预警 |
| **liquidations** | 执行层 (15M) | 短期极端行情 | 入场风险过滤 |

### 9.3 协同规则设计

#### 9.3.1 趋势层增强 (RISK_ON 条件)

```python
# multi_timeframe_manager.py evaluate_risk_state() 扩展

def evaluate_risk_state(
    self,
    current_price: float,
    oi_data: Optional[Dict] = None,  # 新增
) -> RiskState:
    """
    评估趋势层风险状态

    原有条件:
    1. 价格 > SMA_200
    2. MACD > 0

    新增条件 (可选):
    3. OI 变化率 > -10% (持仓未大幅下降)
    """
    # 原有逻辑...

    # 新增 OI 条件 (可选增强)
    if oi_data and self.config.get('trend_layer', {}).get('use_oi_filter', False):
        oi_change = oi_data.get('change_pct')
        if oi_change is not None and oi_change < -10:
            self.logger.info(f"[1D] OI 大幅下降 ({oi_change:.1f}%), 趋势减弱")
            # 可选: 降低 RISK_ON 置信度，但不直接改为 RISK_OFF
```

#### 9.3.2 决策层增强 (4H 辩论数据)

```python
# 在 multi_agent_analyzer.py 的辩论中使用

# CVD Trend 作为额外论据
if cvd_trend == "RISING":
    bull_extra = "CVD is RISING, indicating accumulation by smart money"
elif cvd_trend == "FALLING":
    bear_extra = "CVD is FALLING, indicating distribution phase"

# Funding Rate 作为风险信号
if funding_rate > 0.001:
    judge_warning = "⚠️ Funding > 0.1%, market overheated, long squeeze risk"
```

#### 9.3.3 执行层增强 (入场确认)

```python
# multi_timeframe_manager.py check_execution_confirmation() 扩展

def check_execution_confirmation(
    self,
    current_price: float,
    direction: str,  # "LONG" or "SHORT"
    order_flow_data: Optional[Dict] = None,  # 新增
    liquidations_data: Optional[Dict] = None,  # 新增
) -> Dict[str, Any]:
    """
    检查执行层入场确认条件

    原有条件:
    - RSI 在 [35, 65] 范围内

    新增条件:
    - buy_ratio 确认 (LONG 需 > 0.50, SHORT 需 < 0.50)
    - 无极端清算 (1h 清算 < $50M)
    """
    result = {
        'confirmed': True,
        'checks': [],
    }

    # 原有 RSI 检查
    rsi = tech_data.get('rsi', 50)
    rsi_ok = 35 <= rsi <= 65
    result['checks'].append({
        'name': 'RSI Range',
        'passed': rsi_ok,
        'value': rsi,
    })

    # 新增: 订单流确认
    if order_flow_data and order_flow_data.get('data_source') != 'none':
        buy_ratio = order_flow_data.get('buy_ratio', 0.5)

        if direction == "LONG":
            flow_ok = buy_ratio >= 0.50
        else:  # SHORT
            flow_ok = buy_ratio <= 0.50

        result['checks'].append({
            'name': 'Order Flow',
            'passed': flow_ok,
            'value': buy_ratio,
            'required': '>= 0.50' if direction == "LONG" else '<= 0.50',
        })

        if not flow_ok:
            result['confirmed'] = False

    # 新增: 清算风险检查
    if liquidations_data:
        total_liq = liquidations_data.get('total_usd', 0)
        liq_ok = total_liq < 50_000_000  # < $50M

        result['checks'].append({
            'name': 'Liquidation Risk',
            'passed': liq_ok,
            'value': total_liq,
            'threshold': 50_000_000,
        })

        if not liq_ok:
            result['confirmed'] = False
            result['warning'] = f"⚠️ High liquidations (${total_liq/1e6:.1f}M), entry risky"

    return result
```

### 9.4 数据源协同矩阵

```
                    ┌─────────────────────────────────────────────────┐
                    │              数据协同矩阵                        │
                    ├─────────┬──────────┬──────────┬─────────────────┤
                    │ 技术指标 │ 订单流   │ 衍生品   │ 情绪            │
┌───────────────────┼─────────┼──────────┼──────────┼─────────────────┤
│ 技术指标          │    -    │ RSI +    │ SMA_200 +│ 情绪极值       │
│                   │         │ buy_ratio│ OI 趋势  │ 过滤           │
├───────────────────┼─────────┼──────────┼──────────┼─────────────────┤
│ 订单流            │         │    -     │ CVD + OI │ buy_ratio +    │
│                   │         │          │ 背离检测 │ 多空比         │
├───────────────────┼─────────┼──────────┼──────────┼─────────────────┤
│ 衍生品            │         │          │    -     │ Funding +      │
│                   │         │          │          │ 情绪           │
├───────────────────┼─────────┼──────────┼──────────┼─────────────────┤
│ 情绪              │         │          │          │       -        │
└───────────────────┴─────────┴──────────┴──────────┴─────────────────┘
```

### 9.5 配置示例

```yaml
# configs/base.yaml 新增配置

multi_timeframe:
  enabled: true

  # 趋势层 OI 增强
  trend_layer:
    use_oi_filter: true           # 启用 OI 过滤
    oi_decline_threshold: -10     # OI 下降超过 10% 发出警告

  # 决策层数据源
  decision_layer:
    use_cvd_in_debate: true       # 在辩论中使用 CVD
    use_funding_warning: true     # Funding 过热预警

  # 执行层确认
  execution_layer:
    use_order_flow_confirm: true  # 订单流入场确认
    use_liquidation_filter: true  # 清算风险过滤
    liquidation_threshold: 50000000  # $50M

# 数据权重 (供 AI 参考)
order_flow:
  prompt:
    weights:
      technical: 0.30
      order_flow: 0.25
      derivatives: 0.25
      sentiment: 0.20
```

---

## 十、实施检查清单

### 10.1 文件创建清单

| 文件 | 状态 | 依赖 |
|------|------|------|
| `utils/binance_kline_client.py` | 待创建 | 无 |
| `utils/coinalyze_client.py` | 待创建 | 无 |
| `utils/order_flow_processor.py` | 待创建 | 无 |
| `utils/ai_data_assembler.py` | 待创建 | 上述三个文件 |
| `tests/test_order_flow.py` | 待创建 | order_flow_processor |
| `tests/test_coinalyze.py` | 待创建 | coinalyze_client |

### 10.2 文件修改清单

| 文件 | 修改内容 | 详细说明 |
|------|----------|----------|
| `strategy/deepseek_strategy.py` | 初始化新客户端 + on_timer 获取数据 | 见 11.1 节 |
| `agents/multi_agent_analyzer.py` | 扩展 analyze() + 新增格式化方法 | 见 11.2 节 |
| `indicators/multi_timeframe_manager.py` | 扩展方法签名 + 新增参数 | 见 11.3 节 |
| `configs/base.yaml` | 新增 order_flow 和 MTF 协同配置 | 见 12.5 节 |
| `~/.env.aitrader` | 添加 COINALYZE_API_KEY | 仅敏感信息 |

### 10.3 测试验证

```bash
# 1. 单元测试
pytest tests/test_order_flow.py -v
pytest tests/test_coinalyze.py -v

# 2. 集成测试
python3 main_live.py --env development --dry-run

# 3. 验证数据流
python3 scripts/diagnose_realtime.py
```

---

## 十一、完整代码修改差异 (v2.1 新增)

> ⚠️ **v2.1 新增**: 解决接口签名冲突和调用链断裂问题

### 11.1 deepseek_strategy.py 修改

#### 11.1.1 导入新模块 (文件顶部)

```python
# strategy/deepseek_strategy.py 顶部导入区域新增

# Order Flow and Derivatives clients (v2.1)
from utils.binance_kline_client import BinanceKlineClient
from utils.order_flow_processor import OrderFlowProcessor
from utils.coinalyze_client import CoinalyzeClient
```

#### 11.1.2 __init__ 中初始化新客户端

在 `__init__` 方法中，`self.sentiment_fetcher` 初始化后添加：

```python
# strategy/deepseek_strategy.py __init__ 方法中
# 在 self.sentiment_fetcher 初始化后添加 (约 line 512 后)

# ========== Order Flow & Derivatives (v2.1) ==========
# 从配置读取参数
order_flow_enabled = config.order_flow_enabled if hasattr(config, 'order_flow_enabled') else True

if order_flow_enabled:
    # Binance K线客户端 (获取完整 12 列数据)
    self.binance_kline_client = BinanceKlineClient(
        timeout=config.order_flow_binance_timeout if hasattr(config, 'order_flow_binance_timeout') else 10,
        logger=self.log,
    )

    # 订单流处理器
    self.order_flow_processor = OrderFlowProcessor(logger=self.log)

    # Coinalyze 客户端 (衍生品数据)
    coinalyze_enabled = config.order_flow_coinalyze_enabled if hasattr(config, 'order_flow_coinalyze_enabled') else True
    if coinalyze_enabled:
        self.coinalyze_client = CoinalyzeClient(
            api_key=None,  # 从环境变量读取
            timeout=config.order_flow_coinalyze_timeout if hasattr(config, 'order_flow_coinalyze_timeout') else 10,
            max_retries=config.order_flow_coinalyze_max_retries if hasattr(config, 'order_flow_coinalyze_max_retries') else 2,
            retry_delay=config.order_flow_coinalyze_retry_delay if hasattr(config, 'order_flow_coinalyze_retry_delay') else 1.0,
            logger=self.log,
        )
    else:
        self.coinalyze_client = None
        self.log.info("Coinalyze client disabled by config")

    self.log.info("✅ Order Flow & Derivatives clients initialized")
else:
    self.binance_kline_client = None
    self.order_flow_processor = None
    self.coinalyze_client = None
    self.log.info("Order Flow disabled by config")
```

#### 11.1.3 on_timer() 中获取新数据

在 `on_timer()` 方法中，`sentiment_data` 获取后、调用 `analyze()` 前添加：

```python
# strategy/deepseek_strategy.py on_timer() 方法中
# 在 sentiment_data 处理后 (约 line 1287 后)，调用 analyze() 前添加

# ========== 获取订单流数据 (v2.1) ==========
order_flow_data = None
if self.binance_kline_client and self.order_flow_processor:
    try:
        # 获取 Binance 完整 K线 (12 列，包含订单流字段)
        raw_klines = self.binance_kline_client.get_klines(
            symbol="BTCUSDT",
            interval="15m",
            limit=50,
        )
        if raw_klines:
            order_flow_data = self.order_flow_processor.process_klines(raw_klines)
            self.log.info(
                f"📊 Order Flow: buy_ratio={order_flow_data.get('buy_ratio', 0):.1%}, "
                f"cvd_trend={order_flow_data.get('cvd_trend', 'N/A')}"
            )
        else:
            self.log.warning("⚠️ Failed to get Binance klines for order flow")
    except Exception as e:
        self.log.warning(f"⚠️ Order flow processing failed: {e}")

# ========== 获取衍生品数据 (v2.1) ==========
derivatives_data = None
if self.coinalyze_client and self.coinalyze_client.is_enabled():
    try:
        derivatives_data = self.coinalyze_client.fetch_all()
        if derivatives_data.get('enabled'):
            oi = derivatives_data.get('open_interest')
            funding = derivatives_data.get('funding_rate')
            self.log.info(
                f"📊 Derivatives: OI={oi.get('value', 0):.2f} BTC, "
                f"Funding={funding.get('value', 0)*100:.4f}%" if oi and funding else "Derivatives: partial data"
            )
        else:
            self.log.debug("Coinalyze client disabled, no derivatives data")
    except Exception as e:
        self.log.warning(f"⚠️ Derivatives fetch failed: {e}")
```

#### 11.1.4 修改 analyze() 调用

修改 `analyze()` 调用，传入新参数：

```python
# strategy/deepseek_strategy.py on_timer() 方法中
# 替换原有的 self.multi_agent.analyze() 调用 (约 line 1362-1368)

signal_data = self.multi_agent.analyze(
    symbol="BTCUSDT",
    technical_report=ai_technical_data,
    sentiment_report=sentiment_data,
    current_position=current_position,
    price_data=price_data,
    # ========== v2.1 新增参数 ==========
    order_flow_report=order_flow_data,
    derivatives_report=derivatives_data,
)
```

### 11.2 multi_agent_analyzer.py 修改

#### 11.2.1 扩展 analyze() 方法签名

```python
# agents/multi_agent_analyzer.py
# 修改 analyze() 方法签名 (约 line 198-205)

def analyze(
    self,
    symbol: str,
    technical_report: Dict[str, Any],
    sentiment_report: Optional[Dict[str, Any]] = None,
    current_position: Optional[Dict[str, Any]] = None,
    price_data: Optional[Dict[str, Any]] = None,
    # ========== v2.1 新增参数 ==========
    order_flow_report: Optional[Dict[str, Any]] = None,
    derivatives_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
```

#### 11.2.2 在 analyze() 方法内部格式化新数据

在 `analyze()` 方法中，`tech_summary` 和 `sent_summary` 格式化后添加：

```python
# agents/multi_agent_analyzer.py analyze() 方法中
# 在 tech_summary = ... 和 sent_summary = ... 后添加 (约 line 251-252 后)

# Format order flow and derivatives for prompts (v2.1)
order_flow_summary = self._format_order_flow_report(order_flow_report)
derivatives_summary = self._format_derivatives_report(derivatives_report)
```

#### 11.2.3 修改 Bull/Bear 方法调用

修改辩论循环中的调用：

```python
# agents/multi_agent_analyzer.py analyze() 方法中
# 修改 _get_bull_argument 调用 (约 line 267-273)

# Bull's turn
bull_argument = self._get_bull_argument(
    symbol=symbol,
    technical_report=tech_summary,
    sentiment_report=sent_summary,
    order_flow_report=order_flow_summary,      # v2.1 新增
    derivatives_report=derivatives_summary,     # v2.1 新增
    history=debate_history,
    bear_argument=bear_argument,
)

# 同样修改 _get_bear_argument 调用 (约 line 277-283)

# Bear's turn
bear_argument = self._get_bear_argument(
    symbol=symbol,
    technical_report=tech_summary,
    sentiment_report=sent_summary,
    order_flow_report=order_flow_summary,      # v2.1 新增
    derivatives_report=derivatives_summary,     # v2.1 新增
    history=debate_history,
    bull_argument=bull_argument,
)
```

#### 11.2.4 修改 _get_bull_argument() 方法

```python
# agents/multi_agent_analyzer.py
# 替换整个 _get_bull_argument 方法 (约 line 320-365)

def _get_bull_argument(
    self,
    symbol: str,
    technical_report: str,
    sentiment_report: str,
    order_flow_report: str,      # v2.1 新增
    derivatives_report: str,     # v2.1 新增
    history: str,
    bear_argument: str,
) -> str:
    """
    Generate bull analyst's argument.

    Borrowed from: TradingAgents/agents/researchers/bull_researcher.py
    v2.1: Added order flow and derivatives data
    """
    prompt = f"""You are a Bull Analyst advocating for LONG position on {symbol}.
Your task is to build a strong, evidence-based case for going LONG.

Key points to focus on:
- BULLISH Technical Signals: Price above SMAs, RSI recovering from oversold, MACD bullish crossover
- Order Flow Confirmation: Buy ratio > 50%, CVD rising (accumulation)
- Derivatives Support: OI rising with price, neutral/negative funding (not overheated)
- Growth Momentum: Breakout patterns, increasing volume, support holding
- Counter Bear Arguments: Use specific numbers to refute bearish concerns

Resources Available:

TECHNICAL ANALYSIS:
{technical_report}

{order_flow_report}

{derivatives_report}

{sentiment_report}

Previous Debate:
{history if history else "This is the opening argument."}

Last Bear Argument:
{bear_argument if bear_argument else "No bear argument yet - make your opening case."}

INSTRUCTIONS:
1. Present 2-3 compelling reasons for LONG
2. Use specific numbers from ALL data sources (technical, order flow, derivatives)
3. If bear made arguments, directly counter them with data
4. Be persuasive but factual

Deliver your argument now (2-3 paragraphs):"""

    return self._call_api_with_retry([
        {"role": "system", "content": "You are a professional Bull Analyst. Use order flow and derivatives data to strengthen your arguments."},
        {"role": "user", "content": prompt}
    ])
```

#### 11.2.5 修改 _get_bear_argument() 方法

```python
# agents/multi_agent_analyzer.py
# 替换整个 _get_bear_argument 方法 (约 line 367-412)

def _get_bear_argument(
    self,
    symbol: str,
    technical_report: str,
    sentiment_report: str,
    order_flow_report: str,      # v2.1 新增
    derivatives_report: str,     # v2.1 新增
    history: str,
    bull_argument: str,
) -> str:
    """
    Generate bear analyst's argument.

    Borrowed from: TradingAgents/agents/researchers/bear_researcher.py
    v2.1: Added order flow and derivatives data
    """
    prompt = f"""You are a Bear Analyst making the case AGAINST going LONG on {symbol}.
Your goal is to present well-reasoned arguments for SHORT or staying FLAT.

Key points to focus on:
- BEARISH Technical Signals: Price below SMAs, overbought RSI, MACD bearish divergence
- Order Flow Warning: Buy ratio < 50%, CVD falling (distribution)
- Derivatives Risk: High funding rate (squeeze risk), OI falling (trend weakening)
- Downside Risks: Resistance levels, decreasing volume, support breaking
- Counter Bull Arguments: Expose over-optimistic assumptions with specific data

Resources Available:

TECHNICAL ANALYSIS:
{technical_report}

{order_flow_report}

{derivatives_report}

{sentiment_report}

Previous Debate:
{history}

Last Bull Argument:
{bull_argument}

INSTRUCTIONS:
1. Present 2-3 compelling reasons AGAINST long / FOR short
2. Use specific numbers from ALL data sources (technical, order flow, derivatives)
3. Directly counter the bull's arguments with data
4. Highlight risks the bull is ignoring

Deliver your argument now (2-3 paragraphs):"""

    return self._call_api_with_retry([
        {"role": "system", "content": "You are a professional Bear Analyst. Use order flow and derivatives data to highlight risks."},
        {"role": "user", "content": prompt}
    ])
```

#### 11.2.6 新增格式化方法

在类末尾添加两个新方法（在 `get_last_debate()` 方法后）：

```python
# agents/multi_agent_analyzer.py
# 在类末尾添加 (约 line 886 后)

def _format_order_flow_report(self, data: Optional[Dict[str, Any]]) -> str:
    """
    Format order flow data for AI prompts.

    v2.1: New method for order flow integration
    """
    if not data or data.get('data_source') == 'none':
        return "ORDER FLOW: Data not available (using neutral assumptions)"

    buy_ratio = data.get('buy_ratio', 0.5)
    cvd_trend = data.get('cvd_trend', 'NEUTRAL')
    avg_trade = data.get('avg_trade_usdt', 0)
    trades_count = data.get('trades_count', 0)
    recent_bars = data.get('recent_10_bars', [])

    # Interpret buy/sell ratio
    if buy_ratio > 0.55:
        buy_interpretation = "BULLISH (buyers dominating)"
    elif buy_ratio < 0.45:
        buy_interpretation = "BEARISH (sellers dominating)"
    else:
        buy_interpretation = "NEUTRAL (balanced)"

    # Format recent bars
    recent_str = ", ".join([f"{r:.1%}" for r in recent_bars[-5:]]) if recent_bars else "N/A"

    return f"""
ORDER FLOW ANALYSIS (Binance Taker Data):
- Buy Ratio: {buy_ratio:.1%} ({buy_interpretation})
- CVD Trend: {cvd_trend} ({'Accumulation' if cvd_trend == 'RISING' else 'Distribution' if cvd_trend == 'FALLING' else 'Sideways'})
- Avg Trade Size: ${avg_trade:,.0f} USDT
- Trade Count: {trades_count:,}
- Recent 5 Bars Buy Ratio: [{recent_str}]

INTERPRETATION:
- Buy Ratio > 55%: Strong buying pressure, confirms bullish momentum
- Buy Ratio < 45%: Strong selling pressure, confirms bearish momentum
- CVD RISING: Smart money accumulating, potential breakout
- CVD FALLING: Distribution phase, potential breakdown
"""

def _format_derivatives_report(self, data: Optional[Dict[str, Any]]) -> str:
    """
    Format derivatives data for AI prompts.

    v2.1: New method for derivatives integration
    """
    if not data or not data.get('enabled', True):
        return "DERIVATIVES: Data not available (Coinalyze API disabled or unavailable)"

    parts = ["DERIVATIVES MARKET DATA:"]

    # Open Interest
    oi = data.get('open_interest')
    if oi:
        oi_btc = oi.get('value', 0)
        parts.append(f"- Open Interest: {oi_btc:,.2f} BTC")
        parts.append("  → OI Rising + Price Rising: Trend strengthening (bullish confirmation)")
        parts.append("  → OI Falling: Positions closing, trend may be weakening")
    else:
        parts.append("- Open Interest: N/A")

    # Funding Rate
    funding = data.get('funding_rate')
    if funding:
        rate = funding.get('value', 0)
        rate_pct = rate * 100

        if rate > 0.001:
            interp = "VERY_BULLISH (longs paying shorts, potential squeeze risk)"
        elif rate > 0.0005:
            interp = "BULLISH"
        elif rate < -0.001:
            interp = "VERY_BEARISH (shorts paying longs, potential short squeeze)"
        elif rate < -0.0005:
            interp = "BEARISH"
        else:
            interp = "NEUTRAL"

        parts.append(f"- Funding Rate: {rate_pct:.4f}% ({interp})")

        if rate > 0.001:
            parts.append("  → ⚠️ HIGH Funding: Market overheated, long squeeze risk")
        elif rate < -0.001:
            parts.append("  → NEGATIVE Funding: Shorts paying longs, potential short squeeze")
    else:
        parts.append("- Funding Rate: N/A")

    # Liquidations
    liq = data.get('liquidations')
    if liq:
        history = liq.get('history', [])
        if history:
            item = history[-1]
            long_liq = float(item.get('l', 0))
            short_liq = float(item.get('s', 0))
            total = long_liq + short_liq

            parts.append(f"- Liquidations (1h): ${total/1e6:.1f}M total")
            parts.append(f"  → Long Liq: ${long_liq/1e6:.1f}M, Short Liq: ${short_liq/1e6:.1f}M")

            if total > 50_000_000:
                parts.append("  → ⚠️ HIGH liquidations: Extreme volatility, be cautious")
    else:
        parts.append("- Liquidations: N/A")

    return "\n".join(parts)
```

### 11.3 multi_timeframe_manager.py 修改

#### 11.3.1 扩展 evaluate_risk_state() 方法

```python
# indicators/multi_timeframe_manager.py
# 修改 evaluate_risk_state 方法签名和实现 (约 line 293-347)

def evaluate_risk_state(
    self,
    current_price: float,
    oi_data: Optional[Dict[str, Any]] = None,  # v2.1 新增
) -> RiskState:
    """
    评估趋势层风险状态 (Risk-On / Risk-Off)

    使用 MACD 替代 ADX (ADX 未在 TechnicalIndicatorManager 实现)
    v2.1: 新增 OI 数据作为可选增强条件

    Parameters
    ----------
    current_price : float
        当前价格
    oi_data : Dict, optional
        Open Interest 数据 (来自 Coinalyze)
        格式: {"value": float, "change_pct": float}

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

    # ========== v2.1 新增: OI 增强条件 (可选) ==========
    oi_warning = None
    use_oi_filter = trend_config.get('use_oi_filter', False)

    if use_oi_filter and oi_data:
        oi_change = oi_data.get('change_pct')
        oi_decline_threshold = trend_config.get('oi_decline_threshold', -10)

        if oi_change is not None and oi_change < oi_decline_threshold:
            oi_warning = f"OI 大幅下降 ({oi_change:.1f}%), 趋势减弱"
            self.logger.warning(f"[1D] ⚠️ {oi_warning}")
            # 注意: OI 下降只是警告，不直接改变 RISK_ON/OFF 状态
            # 这是为了避免过度过滤

    if conditions_met:
        self._risk_state = RiskState.RISK_ON
    else:
        self._risk_state = RiskState.RISK_OFF

    self._risk_state_updated = datetime.now(timezone.utc)

    log_msg = (
        f"[1D] 趋势层评估: {self._risk_state.value} "
        f"(price={current_price:.2f}, SMA_{sma_period}={sma_value:.2f}, MACD={macd_value:.2f})"
    )
    if oi_warning:
        log_msg += f" | ⚠️ {oi_warning}"
    self.logger.info(log_msg)

    return self._risk_state
```

#### 11.3.2 扩展 check_execution_confirmation() 方法

```python
# indicators/multi_timeframe_manager.py
# 修改 check_execution_confirmation 方法 (约 line 402-436)

def check_execution_confirmation(
    self,
    current_price: float,
    direction: str = None,                           # v2.1 新增
    order_flow_data: Optional[Dict[str, Any]] = None,  # v2.1 新增
    liquidations_data: Optional[Dict[str, Any]] = None,  # v2.1 新增
) -> Dict[str, Any]:
    """
    检查执行层入场确认条件

    v2.1: 新增订单流和清算数据作为可选增强条件

    Parameters
    ----------
    current_price : float
        当前价格
    direction : str, optional
        交易方向 ("LONG" 或 "SHORT")，用于订单流确认
    order_flow_data : Dict, optional
        订单流数据 (来自 OrderFlowProcessor)
    liquidations_data : Dict, optional
        清算数据 (来自 Coinalyze)

    Returns
    -------
    Dict
        {
            'confirmed': bool,
            'rsi': float,
            'rsi_in_range': bool,
            'order_flow_ok': bool,      # v2.1 新增
            'liquidation_ok': bool,     # v2.1 新增
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

    # ========== 原有: RSI 范围检查 ==========
    rsi = tech_data.get('rsi', 50)
    rsi_min = exec_config.get('rsi_entry_min', 35)
    rsi_max = exec_config.get('rsi_entry_max', 65)
    rsi_in_range = rsi_min <= rsi <= rsi_max

    result = {
        'confirmed': rsi_in_range,
        'rsi': rsi,
        'rsi_in_range': rsi_in_range,
        'rsi_range': [rsi_min, rsi_max],
        'reason': f'RSI={rsi:.1f} {"在" if rsi_in_range else "不在"}范围[{rsi_min}, {rsi_max}]内',
        'order_flow_ok': True,      # 默认通过
        'liquidation_ok': True,     # 默认通过
    }

    # ========== v2.1 新增: 订单流确认 ==========
    use_order_flow_confirm = exec_config.get('use_order_flow_confirm', False)

    if use_order_flow_confirm and order_flow_data and direction:
        if order_flow_data.get('data_source') not in ['none', 'local_dict']:
            buy_ratio = order_flow_data.get('buy_ratio', 0.5)

            if direction == "LONG":
                flow_ok = buy_ratio >= 0.50
            elif direction == "SHORT":
                flow_ok = buy_ratio <= 0.50
            else:
                flow_ok = True  # 未知方向，跳过检查

            result['order_flow_ok'] = flow_ok
            result['buy_ratio'] = buy_ratio

            if not flow_ok:
                result['confirmed'] = False
                result['reason'] += f" | 订单流不确认 (buy_ratio={buy_ratio:.1%})"

    # ========== v2.1 新增: 清算风险过滤 ==========
    use_liquidation_filter = exec_config.get('use_liquidation_filter', False)
    liquidation_threshold = exec_config.get('liquidation_threshold', 50_000_000)  # $50M

    if use_liquidation_filter and liquidations_data:
        history = liquidations_data.get('history', [])
        if history:
            item = history[-1]
            long_liq = float(item.get('l', 0))
            short_liq = float(item.get('s', 0))
            total_liq = long_liq + short_liq

            liq_ok = total_liq < liquidation_threshold
            result['liquidation_ok'] = liq_ok
            result['total_liquidation'] = total_liq

            if not liq_ok:
                result['confirmed'] = False
                result['reason'] += f" | ⚠️ 高清算风险 (${total_liq/1e6:.1f}M)"

    return result
```

---

## 十二、数据降级策略 (v2.1 新增)

> ⚠️ **v2.1 新增**: 定义数据不可用时的处理规则

### 12.1 降级场景定义

| 场景 | 原因 | 影响数据 |
|------|------|----------|
| **Coinalyze 禁用** | 无 API Key | OI, Funding, Liquidations |
| **Coinalyze 超时** | 网络问题 | OI, Funding, Liquidations |
| **Binance K线失败** | 网络问题 | buy_ratio, cvd_trend |
| **部分数据缺失** | API 返回不完整 | 单个指标 |

### 12.2 降级处理规则

```python
# 在 _format_order_flow_report 和 _format_derivatives_report 中已处理
# 数据不可用时返回明确的提示文本

# ORDER FLOW 降级
if not data or data.get('data_source') == 'none':
    return "ORDER FLOW: Data not available (using neutral assumptions)"

# DERIVATIVES 降级
if not data or not data.get('enabled', True):
    return "DERIVATIVES: Data not available (Coinalyze API disabled or unavailable)"
```

### 12.3 Judge 确认点降级规则

在 `_get_judge_decision()` 的 Prompt 中添加降级说明：

```python
# agents/multi_agent_analyzer.py _get_judge_decision() 方法中
# 在确认点计数规则后添加

=== DATA AVAILABILITY RULES ===

IF "ORDER FLOW: Data not available" appears in the debate:
    → Skip confirmations 6-7 (Order Flow related)
    → Count from remaining confirmations only
    → DO NOT penalize either side for missing data

IF "DERIVATIVES: Data not available" appears in the debate:
    → Skip confirmations 8-9 (Derivatives related)
    → Count from remaining confirmations only
    → DO NOT penalize either side for missing data

IF BOTH are unavailable:
    → Use original 5-point confirmation system only
    → This is normal operation, not an error
```

### 12.4 过滤器优先级定义

```
MTF 过滤器执行顺序 (从高到低):

┌─────────────────────────────────────────────────────────────┐
│ Priority 1: RISK_OFF 过滤 (最高优先级)                       │
│ ├─ 条件: 价格 < SMA_200 或 MACD < 0                         │
│ ├─ 动作: 禁止新开仓 (BUY/SELL → HOLD)                       │
│ └─ OI 警告: 仅记录日志，不过滤                              │
├─────────────────────────────────────────────────────────────┤
│ Priority 2: 决策层方向匹配                                   │
│ ├─ 条件: 信号与 DecisionState 冲突                          │
│ ├─ 动作: BUY + ALLOW_SHORT → HOLD                          │
│ │         SELL + ALLOW_LONG → HOLD                          │
│ │         WAIT → HOLD                                       │
│ └─ 注意: 只在 RISK_ON 时检查                                │
├─────────────────────────────────────────────────────────────┤
│ Priority 3: RSI 入场确认                                     │
│ ├─ 条件: RSI 不在 [35, 65] 范围                             │
│ ├─ 动作: 交易信号 → HOLD                                    │
│ └─ 注意: 只在有交易信号时检查                               │
├─────────────────────────────────────────────────────────────┤
│ Priority 4: 订单流确认 (可选，默认关闭)                      │
│ ├─ 条件: LONG + buy_ratio < 50% 或 SHORT + buy_ratio > 50% │
│ ├─ 动作: 交易信号 → HOLD                                    │
│ └─ 配置: execution_layer.use_order_flow_confirm = true      │
├─────────────────────────────────────────────────────────────┤
│ Priority 5: 清算风险过滤 (可选，默认关闭)                    │
│ ├─ 条件: 1小时清算 > $50M                                   │
│ ├─ 动作: 交易信号 → HOLD                                    │
│ └─ 配置: execution_layer.use_liquidation_filter = true      │
└─────────────────────────────────────────────────────────────┘

注意:
- Priority 4-5 默认关闭，需要在配置中启用
- 任一过滤器触发即停止检查后续过滤器
- 每个过滤器都会记录日志
```

### 12.5 配置示例 (完整版)

```yaml
# configs/base.yaml 完整配置

# ========== Order Flow 配置 ==========
order_flow:
  enabled: true

  binance_klines:
    timeout: 10
    limit: 50

  coinalyze:
    enabled: true
    timeout: 10
    max_retries: 2
    retry_delay: 1.0
    symbol: "BTCUSDT_PERP.A"

# ========== MTF 协同配置 ==========
multi_timeframe:
  enabled: true

  # 趋势层 (1D)
  trend_layer:
    sma_period: 200
    require_above_sma: true
    require_macd_positive: true
    use_oi_filter: false          # OI 过滤 (默认关闭，仅警告)
    oi_decline_threshold: -10     # OI 下降超过 10% 发出警告

  # 决策层 (4H)
  decision_layer:
    timeframe: "4h"
    use_cvd_in_debate: true       # 在辩论中使用 CVD
    use_funding_warning: true     # Funding 过热预警

  # 执行层 (15M)
  execution_layer:
    rsi_entry_min: 35
    rsi_entry_max: 65
    use_order_flow_confirm: false  # 订单流确认 (默认关闭)
    use_liquidation_filter: false  # 清算风险过滤 (默认关闭)
    liquidation_threshold: 50000000  # $50M
```

---

## 十三、DeepSeekStrategyConfig 扩展 (v2.1 新增)

需要在 `strategy/deepseek_strategy.py` 的 `DeepSeekStrategyConfig` dataclass 中添加：

```python
# strategy/deepseek_strategy.py DeepSeekStrategyConfig dataclass 中添加

# ========== Order Flow 配置 (v2.1) ==========
order_flow_enabled: bool = True
order_flow_binance_timeout: int = 10
order_flow_coinalyze_enabled: bool = True
order_flow_coinalyze_timeout: int = 10
order_flow_coinalyze_max_retries: int = 2
order_flow_coinalyze_retry_delay: float = 1.0
```

并在 `main_live.py` 中从 ConfigManager 加载这些参数。
