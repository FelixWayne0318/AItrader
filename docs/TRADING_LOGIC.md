# AItrader 完整交易逻辑文档

> 版本: 2.0
> 更新日期: 2026-01-27
> 适用代码版本: main 分支

本文档详细描述 AItrader 的完整数据流、信号生成、仓位管理和风险控制逻辑。

---

## 目录

1. [系统架构总览](#1-系统架构总览)
2. [启动流程](#2-启动流程)
3. [数据获取层](#3-数据获取层)
4. [MTF 多时间框架架构](#4-mtf-多时间框架架构)
5. [AI 分析层](#5-ai-分析层)
6. [信号处理流程](#6-信号处理流程)
7. [仓位管理](#7-仓位管理)
8. [止盈止损逻辑](#8-止盈止损逻辑)
9. [完整数据流图](#9-完整数据流图)
10. [关键配置参数](#10-关键配置参数)
11. [文件映射表](#11-文件映射表)

---

## 1. 系统架构总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           AItrader 系统架构                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│  │   数据层     │    │   分析层     │    │   执行层     │              │
│  │              │    │              │    │              │              │
│  │ • K线数据    │───▶│ • MTF过滤    │───▶│ • 仓位计算   │              │
│  │ • 技术指标   │    │ • AI辩论     │    │ • 订单提交   │              │
│  │ • 情绪数据   │    │ • 信号生成   │    │ • 止盈止损   │              │
│  │ • 订单流     │    │              │    │              │              │
│  │ • 衍生品数据 │    │              │    │              │              │
│  └──────────────┘    └──────────────┘    └──────────────┘              │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                        风险管理层                                  │  │
│  │  • 趋势过滤 (RISK_ON/OFF)  • 信心度门槛  • 移动止损  • OCO订单   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 核心特点

| 特性 | 说明 |
|------|------|
| **框架** | NautilusTrader (高性能量化交易框架) |
| **AI引擎** | DeepSeek API (Bull/Bear/Judge 多代理辩论) |
| **时间框架** | MTF 三层架构 (1D趋势 / 4H决策 / 15M执行) |
| **交易对** | BTCUSDT 永续合约 (Binance Futures) |
| **分析周期** | 每 15 分钟执行一次 (on_timer) |

---

## 2. 启动流程

### 2.1 入口文件: main_live.py

```
启动命令: python3 main_live.py --env production

启动流程:
┌─────────────────────────────────────────────────────────────┐
│ 1. 应用补丁                                                  │
│    └─ patches.binance_enums.apply_all_patches()            │
│       修复 Binance POSITION_RISK_CONTROL enum 兼容性         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. 加载环境变量                                              │
│    ├─ 优先级: ~/.env.aitrader > .env > 系统环境变量         │
│    └─ 包含: API Keys (Binance, DeepSeek, Telegram)          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. 加载配置                                                  │
│    ├─ ConfigManager 加载 configs/base.yaml                   │
│    ├─ 合并 configs/{env}.yaml (production/development)      │
│    └─ 构建 DeepSeekAIStrategyConfig 对象                     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. 构建交易节点                                              │
│    ├─ 创建 NautilusTrader TradingNode                       │
│    ├─ 配置 BinanceDataClient (数据)                          │
│    ├─ 配置 BinanceExecClient (执行)                          │
│    └─ 注册 DeepSeekAIStrategy                                │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. 启动                                                      │
│    └─ node.run() 进入事件循环                                │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 策略初始化: DeepSeekAIStrategy.__init__

**文件**: `strategy/deepseek_strategy.py` (Line 190-560)

```python
初始化组件:

1. 技术指标管理器 (TechnicalIndicatorManager)
   ├─ SMA: [5, 20, 50, 200] (200用于MTF趋势层)
   ├─ RSI: 14 周期
   ├─ MACD: (12, 26, 9)
   ├─ Bollinger Bands: (20, 2.0)
   └─ 使用 Cython 指标 (线程安全)

2. MTF 多时间框架管理器 (如启用)
   ├─ 趋势层: 1-DAY K线
   ├─ 决策层: 4-HOUR K线
   └─ 执行层: 15-MINUTE K线

3. AI 分析器
   ├─ DeepSeekAnalyzer (单代理，备用)
   └─ MultiAgentAnalyzer (Bull/Bear/Judge)

4. Telegram 通知
   ├─ TelegramBot (消息发送)
   └─ TelegramCommandHandler (命令处理)

5. 数据客户端
   ├─ SentimentDataFetcher (Binance 多空比)
   ├─ BinanceKlineClient (原始K线数据)
   ├─ OrderFlowProcessor (订单流计算)
   └─ CoinalyzeClient (衍生品数据)
```

---

## 3. 数据获取层

### 3.1 数据源总览

| 数据类型 | 数据源 | 更新频率 | 用途 |
|---------|--------|---------|------|
| K线数据 | Binance Futures API | 实时 (on_bar) | 技术指标计算 |
| 技术指标 | 本地计算 | 每根K线 | AI分析输入 |
| 情绪数据 | Binance 多空比 API | 15分钟 | 市场情绪判断 |
| 订单流 | Binance K线原始数据 | 15分钟 | 买卖力量分析 |
| 衍生品 | Coinalyze API | 15分钟 | OI/资金费率/爆仓 |

### 3.2 技术指标计算

**文件**: `indicators/technical_manager.py`

```python
TechnicalIndicatorManager.get_technical_data(current_price) 返回:

{
    # 移动平均线
    'sma_5': float,      # 5周期SMA
    'sma_20': float,     # 20周期SMA
    'sma_50': float,     # 50周期SMA
    'sma_200': float,    # 200周期SMA (MTF趋势层用)

    # RSI
    'rsi': float,        # 14周期RSI (0-100)

    # MACD
    'macd': float,       # MACD线
    'macd_signal': float,# 信号线
    'macd_histogram': float,

    # 布林带
    'bb_upper': float,   # 上轨
    'bb_middle': float,  # 中轨 (SMA20)
    'bb_lower': float,   # 下轨
    'bb_position': float,# 当前价格在BB中的位置 (0-100%)

    # 支撑/阻力
    'support': float,    # 近期最低点
    'resistance': float, # 近期最高点

    # 趋势判断
    'trend': str,        # 'UPTREND' / 'DOWNTREND' / 'NEUTRAL'
    'trend_strength': str,# 'STRONG' / 'WEAK' / 'NEUTRAL'
}
```

### 3.3 情绪数据

**文件**: `utils/sentiment_client.py`

```python
SentimentDataFetcher.fetch() 返回:

{
    'long_short_ratio': float,  # 多空比 (>1 看多, <1 看空)
    'long_account_pct': float,  # 多头账户占比
    'short_account_pct': float, # 空头账户占比
    'positive_ratio': float,    # 等于 long_account_pct
    'negative_ratio': float,    # 等于 short_account_pct
    'net_sentiment': float,     # positive - negative
    'source': 'binance',
    'timestamp': str,
}

数据源: https://fapi.binance.com/futures/data/globalLongShortAccountRatio
```

### 3.4 订单流数据

**文件**: `utils/order_flow_processor.py`

```python
OrderFlowProcessor.process_klines(klines) 返回:

{
    'buy_ratio': float,      # 买盘占比 (>0.55 多头主导)
    'avg_trade_usdt': float, # 平均成交额 (大单识别)
    'volume_usdt': float,    # 总成交额
    'trades_count': int,     # 成交笔数
    'cvd_trend': str,        # 'RISING' / 'FALLING' / 'NEUTRAL'
    'bars_count': int,       # 分析的K线数量
}

计算方法:
- buy_ratio = avg(taker_buy_volume / total_volume) for last 10 bars
- cvd_trend = 基于累积成交量差值判断
```

### 3.5 衍生品数据

**文件**: `utils/coinalyze_client.py`

```python
CoinalyzeClient.fetch_all() 返回:

{
    'enabled': bool,         # API Key 是否配置
    'open_interest': {
        'value': float,      # BTC 单位
        'change_pct': float, # 24h 变化百分比
        'value_usd': float,  # USD 估值
    },
    'funding_rate': {
        'value': float,      # 资金费率 (0.0001 = 0.01%)
    },
    'liquidations': {
        'long_usd': float,   # 多头爆仓 USD
        'short_usd': float,  # 空头爆仓 USD
    },
}

降级策略: 如果 API Key 缺失或 API 失败，返回中性默认值
```

---

## 4. MTF 多时间框架架构

### 4.1 三层架构设计

基于 [TradingAgents](https://github.com/TauricResearch/TradingAgents) (UCLA/MIT) 框架

```
┌─────────────────────────────────────────────────────────────────────────┐
│  趋势层 (1D) - Risk-On/Risk-Off 宏观判断                                │
├─────────────────────────────────────────────────────────────────────────┤
│  数据: 日线 K线                                                          │
│  指标: SMA_200, MACD                                                     │
│  规则:                                                                   │
│    ├─ 价格 > SMA_200 且 MACD > 0 → RISK_ON (允许交易)                  │
│    └─ 否则 → RISK_OFF (禁止新开仓)                                      │
│  作用: 在熊市中阻止所有新交易，保护资金                                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  决策层 (4H) - Bull/Bear Debate + Judge Decision                        │
├─────────────────────────────────────────────────────────────────────────┤
│  数据: 4小时 K线                                                         │
│  指标: MACD, RSI, SMA_20/50 排列                                        │
│  AI: Bull/Bear 辩论 (2轮) → Judge 决定方向                              │
│  输出:                                                                   │
│    ├─ ALLOW_LONG: 只允许做多信号                                        │
│    ├─ ALLOW_SHORT: 只允许做空信号                                       │
│    └─ WAIT: 方向不明确，等待                                            │
│  作用: 确保交易方向与中期趋势一致                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  执行层 (15M) - Precise Entry Timing                                     │
├─────────────────────────────────────────────────────────────────────────┤
│  数据: 15分钟 K线                                                        │
│  指标: RSI                                                               │
│  规则:                                                                   │
│    └─ RSI 需在 35-65 范围内才允许入场                                   │
│  作用: 避免在超买/超卖极端价位进场                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 MTF 配置

**文件**: `configs/base.yaml` (Line 292-345)

```yaml
multi_timeframe:
  enabled: true

  trend_layer:           # 趋势层 (1D)
    timeframe: "1d"
    sma_period: 200
    require_above_sma: true
    require_macd_positive: true

  decision_layer:        # 决策层 (4H)
    timeframe: "4h"
    debate_rounds: 2
    include_trend_context: true

  execution_layer:       # 执行层 (15M)
    default_timeframe: "15m"
    rsi_entry_min: 35
    rsi_entry_max: 65
```

### 4.3 MTF 过滤规则

**文件**: `strategy/deepseek_strategy.py` (Line 1472-1543)

```python
MTF 信号过滤流程:

原始信号: BUY (HIGH)
    ↓
┌───────────────────────────────────────┐
│ 规则 1: 趋势层检查                     │
│ 如果 RISK_OFF 且 无现仓:              │
│   → 信号改为 HOLD (禁止新开仓)        │
└───────────────────────────────────────┘
    ↓
┌───────────────────────────────────────┐
│ 规则 2: 决策层方向检查                 │
│ BUY 信号需匹配 ALLOW_LONG 状态        │
│ SELL 信号需匹配 ALLOW_SHORT 状态      │
│ 不匹配 → 信号改为 HOLD                │
└───────────────────────────────────────┘
    ↓
┌───────────────────────────────────────┐
│ 规则 3: 执行层 RSI 检查                │
│ RSI 需在 35-65 范围内                 │
│ 超出范围 → 信号改为 HOLD              │
└───────────────────────────────────────┘
    ↓
最终信号: HOLD (被过滤) 或 BUY (通过)
```

---

## 5. AI 分析层

### 5.1 多代理架构 (MultiAgentAnalyzer)

**文件**: `agents/multi_agent_analyzer.py`

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        多代理辩论架构                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────┐        ┌───────────────┐                            │
│  │ Bull Analyst  │◄──────▶│ Bear Analyst  │                            │
│  │ (看多分析师)   │  辩论  │ (看空分析师)   │                            │
│  │ temp=0.3     │  2轮   │ temp=0.3     │                            │
│  └───────┬───────┘        └───────┬───────┘                            │
│          │                        │                                     │
│          └──────────┬─────────────┘                                     │
│                     ↓                                                   │
│          ┌───────────────────┐                                          │
│          │      Judge        │                                          │
│          │ (Portfolio Mgr)   │                                          │
│          │ temp=0.1 (确定性) │                                          │
│          └─────────┬─────────┘                                          │
│                    ↓                                                    │
│          ┌───────────────────┐                                          │
│          │  Risk Evaluator   │                                          │
│          │   (风险评估)       │                                          │
│          └─────────┬─────────┘                                          │
│                    ↓                                                    │
│          ┌───────────────────┐                                          │
│          │   最终信号输出     │                                          │
│          │ BUY/SELL/HOLD    │                                          │
│          │ + 信心度 + SL/TP  │                                          │
│          └───────────────────┘                                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.2 AI 分析输入

```python
MultiAgentAnalyzer.analyze() 输入:

{
    'symbol': 'BTCUSDT',
    'technical_report': {
        # 15M 执行层指标
        'rsi': 45.2,
        'macd': 0.5,
        'trend': 'UPTREND',
        ...
        # 4H 决策层指标 (如启用MTF)
        'decision_layer': {
            'rsi': 55.0,
            'macd': 1.2,
            ...
        }
    },
    'sentiment_report': {
        'long_short_ratio': 1.8,
        'net_sentiment': 0.3,
        ...
    },
    'order_flow_report': {
        'buy_ratio': 0.58,
        'cvd_trend': 'RISING',
        ...
    },
    'derivatives_report': {
        'open_interest': {...},
        'funding_rate': {...},
        'liquidations': {...},
    },
    'current_position': {
        'side': 'LONG' / 'SHORT' / None,
        'size': float,
        'entry_price': float,
        'unrealized_pnl': float,
    },
    'price_data': {
        'price': float,
        'high': float,
        'low': float,
        'volume': float,
    },
}
```

### 5.3 AI 分析输出

```python
MultiAgentAnalyzer.analyze() 返回:

{
    'signal': 'BUY' | 'SELL' | 'HOLD',
    'confidence': 'HIGH' | 'MEDIUM' | 'LOW',
    'reason': str,                    # 详细原因
    'debate_summary': str,            # Bull/Bear 辩论摘要
    'judge_decision': {
        'winning_side': 'Bull' | 'Bear',
        'key_reasons': List[str],
        'confidence_in_decision': float,
    },
    'risk_level': 'HIGH' | 'MEDIUM' | 'LOW',
    'target_tp': float,               # 建议止盈价
    'target_sl': float,               # 建议止损价
}
```

### 5.4 信心度定义

| 信心度 | 权重 | 触发条件 | 仓位乘数 |
|--------|------|---------|---------|
| HIGH | 3 | 多数证据支持，Bull/Bear 一边倒 | 1.5x |
| MEDIUM | 2 | 部分证据支持 | 1.0x |
| LOW | 1 | 少数证据支持，信号较弱 | 0.5x |

---

## 6. 信号处理流程

### 6.1 on_timer 主流程

**文件**: `strategy/deepseek_strategy.py` (Line 1251-1616)

```
on_timer() 每 15 分钟执行一次:

┌─────────────────────────────────────────────────────────────────────────┐
│ Step 1: 心跳通知                                                         │
│ └─ 发送 Telegram 心跳消息 (确认服务器运行)                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 2: 数据收集                                                         │
│ ├─ 技术数据: indicator_manager.get_technical_data()                     │
│ ├─ 4H数据: mtf_manager.get_technical_data_for_layer("decision")        │
│ ├─ 情绪数据: sentiment_fetcher.fetch()                                  │
│ ├─ 订单流: order_flow_processor.process_klines()                       │
│ └─ 衍生品: coinalyze_client.fetch_all()                                │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 3: MTF 风险评估                                                     │
│ └─ mtf_manager.evaluate_risk_state() → RISK_ON / RISK_OFF              │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 4: 多代理 AI 分析                                                   │
│ └─ multi_agent.analyze() → signal_data                                  │
│    ├─ Bull/Bear 辩论 (2轮)                                              │
│    ├─ Judge 决策                                                        │
│    └─ Risk 评估                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 5: MTF 信号过滤                                                     │
│ ├─ RISK_OFF 检查 (禁止新开仓)                                           │
│ ├─ 决策层方向匹配 (ALLOW_LONG/SHORT)                                    │
│ └─ 执行层 RSI 确认 (35-65范围)                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 6: 信号通知                                                         │
│ └─ Telegram 发送信号详情                                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 7: 信号执行                                                         │
│ └─ _execute_trade()                                                     │
│    ├─ 信心度检查                                                        │
│    ├─ 仓位计算                                                          │
│    └─ 订单提交                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 8: 风险管理                                                         │
│ ├─ 孤儿订单清理 (OCO)                                                   │
│ └─ 移动止损更新                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.2 信号执行条件

**文件**: `strategy/deepseek_strategy.py` (Line 1781-1865)

```python
_execute_trade() 执行条件检查:

1. 交易暂停检查
   └─ 如果 /pause 命令激活 → 跳过

2. 信心度检查
   ├─ 获取 min_confidence_to_trade (默认 MEDIUM)
   ├─ 信号信心度 < 最小要求 → 跳过
   └─ 例: LOW 信号不会执行 (如果最小要求是 MEDIUM)

3. HOLD 信号处理
   └─ signal == 'HOLD' → 不执行任何操作

4. 仓位计算
   └─ _calculate_position_size() → 目标仓位 (BTC)

5. 执行分支
   ├─ 有现仓 → _manage_existing_position()
   │  ├─ 同方向 → 调整仓位 (加仓/减仓)
   │  └─ 反方向 → 平仓 + 反向开仓 (如允许)
   └─ 无现仓 → _open_new_position()
```

### 6.3 反向交易保护

```python
反向交易条件:

配置项:
├─ allow_reversals: true          # 是否允许反向
└─ require_high_confidence_for_reversal: false  # 反向是否需要HIGH信心

执行逻辑:
IF 信号方向 ≠ 现仓方向:
    IF allow_reversals == False:
        → 跳过 (保持现仓)

    IF require_high_confidence_for_reversal == True:
        IF confidence ≠ 'HIGH':
            → 跳过 (保持现仓)
        ELSE:
            → 执行反向
    ELSE:
        → 执行反向

建议: 如果频繁换向导致亏损，设置:
  require_high_confidence_for_reversal: true
```

---

## 7. 仓位管理

### 7.1 仓位计算公式

**文件**: `strategy/trading_logic.py` (Line 338-477)

```
仓位计算流程:

基础仓位 (base_usdt_amount)
    │
    │ 默认 $100
    ↓
┌─────────────────────────────────────┐
│ × 信心度乘数                         │
│ ├─ HIGH:   × 1.5 = $150            │
│ ├─ MEDIUM: × 1.0 = $100            │
│ └─ LOW:    × 0.5 = $50             │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ × 趋势强度乘数                       │
│ ├─ 强势趋势: × 1.2                  │
│ └─ 其他:    × 1.0                   │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ × RSI 极端乘数                       │
│ ├─ RSI > 70 或 < 30: × 0.7 (减少)  │
│ └─ 其他:            × 1.0           │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 最大仓位限制                         │
│ └─ 不超过 equity × max_position_ratio│
│    (默认 30%)                        │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Binance 限制验证                     │
│ ├─ 名义价值 >= $100                 │
│ ├─ 数量 >= 0.001 BTC               │
│ └─ +1% 安全边际                     │
└─────────────────────────────────────┘
    ↓
最终仓位: X BTC
```

### 7.2 仓位计算示例

```
场景: BUY 信号, HIGH 信心, 强趋势, RSI=55

计算:
├─ 基础: $100
├─ 信心: × 1.5 = $150
├─ 趋势: × 1.2 = $180
├─ RSI:  × 1.0 = $180 (正常范围)
├─ 价格: $90,000
└─ 数量: $180 / $90,000 = 0.002 BTC

验证:
├─ 名义价值: 0.002 × $90,000 = $180 >= $100 ✓
└─ 数量: 0.002 >= 0.001 ✓

最终: 0.002 BTC
```

### 7.3 配置参数

**文件**: `configs/base.yaml` (Line 52-60)

```yaml
position:
  base_usdt_amount: 100              # 基础仓位 $100
  high_confidence_multiplier: 1.5    # 高信心 1.5倍
  medium_confidence_multiplier: 1.0  # 中等信心 1.0倍
  low_confidence_multiplier: 0.5     # 低信心 0.5倍
  max_position_ratio: 0.30           # 最大占权益 30%
  trend_strength_multiplier: 1.2     # 强趋势 1.2倍
  min_trade_amount: 0.001            # 最小交易量
```

---

## 8. 止盈止损逻辑

### 8.1 止损计算

**文件**: `strategy/trading_logic.py` (Line 200-400)

```
止损优先级:

1. MultiAgent Judge 建议的 SL (最优先)
   └─ 经过 validate_multiagent_sltp() 验证

2. 技术分析 SL (备选)
   ├─ 使用支撑/阻力位 (如启用)
   └─ 使用百分比 (默认 2%)

止损计算逻辑:

BUY (做多) 订单:
┌─────────────────────────────────────────┐
│ IF 支撑位有效:                           │
│   SL = support × (1 - buffer_pct)       │
│       = support × 0.999                 │
│ ELSE:                                   │
│   SL = entry_price × (1 - default_sl%)  │
│       = entry_price × 0.98 (默认2%)     │
│                                         │
│ 验证: SL 必须 < entry_price             │
└─────────────────────────────────────────┘

SELL (做空) 订单:
┌─────────────────────────────────────────┐
│ IF 阻力位有效:                           │
│   SL = resistance × (1 + buffer_pct)    │
│       = resistance × 1.001              │
│ ELSE:                                   │
│   SL = entry_price × (1 + default_sl%)  │
│       = entry_price × 1.02 (默认2%)     │
│                                         │
│ 验证: SL 必须 > entry_price             │
└─────────────────────────────────────────┘
```

### 8.2 止盈计算

```
止盈计算 (按信心度):

BUY (做多) 订单:
┌─────────────────────────────────────────┐
│ HIGH:   TP = entry × 1.03 (3% 目标)    │
│ MEDIUM: TP = entry × 1.02 (2% 目标)    │
│ LOW:    TP = entry × 1.01 (1% 目标)    │
│                                         │
│ 验证: TP 必须 > entry_price             │
└─────────────────────────────────────────┘

SELL (做空) 订单:
┌─────────────────────────────────────────┐
│ HIGH:   TP = entry × 0.97 (3% 目标)    │
│ MEDIUM: TP = entry × 0.98 (2% 目标)    │
│ LOW:    TP = entry × 0.99 (1% 目标)    │
│                                         │
│ 验证: TP 必须 < entry_price             │
└─────────────────────────────────────────┘
```

### 8.3 止损验证规则

```python
validate_multiagent_sltp() 验证规则:

BUY 订单:
├─ SL < entry_price (止损必须在入场价下方)
├─ TP > entry_price (止盈必须在入场价上方)
├─ |SL - entry| / entry >= 1% (最小止损距离)
└─ |TP - entry| / entry >= 0.5% (最小止盈距离)

SELL 订单:
├─ SL > entry_price (止损必须在入场价上方)
├─ TP < entry_price (止盈必须在入场价下方)
├─ |SL - entry| / entry >= 1%
└─ |TP - entry| / entry >= 0.5%

如果验证失败 → 使用技术分析 SL/TP 作为备选
```

### 8.4 移动止损

**配置**: `configs/base.yaml` (Line 157-166)

```yaml
trailing_stop:
  enabled: true
  activation_pct: 0.01        # 盈利 1% 后启动
  distance_pct: 0.005         # 跟踪距离 0.5%
  update_threshold_pct: 0.002 # 更新阈值 0.2%
```

```
移动止损逻辑:

激活条件:
├─ LONG: 当前价格 >= 入场价 × 1.01 (盈利 1%)
└─ SHORT: 当前价格 <= 入场价 × 0.99 (盈利 1%)

激活后:
├─ LONG: SL 跟踪 (最高价 × 0.995)，只上不下
├─ SHORT: SL 跟踪 (最低价 × 1.005)，只下不上
└─ 仅当价格变化 > 0.2% 时才更新订单

示例 (LONG):
├─ 入场: $100,000
├─ 激活: 价格涨到 $101,000 (盈利1%)
├─ 最高: $102,000
├─ 移动止损: $102,000 × 0.995 = $101,490
└─ 如果价格回落到 $101,490 → 触发止损 (锁定 1.49% 利润)
```

### 8.5 配置参数

**文件**: `configs/base.yaml` (Line 129-169)

```yaml
risk:
  min_confidence_to_trade: "MEDIUM"    # 最低交易信心
  allow_reversals: true                # 允许反向交易
  require_high_confidence_for_reversal: false  # 反向需要HIGH

  rsi_extreme_threshold_upper: 70.0    # RSI 超买阈值
  rsi_extreme_threshold_lower: 30.0    # RSI 超卖阈值
  rsi_extreme_multiplier: 0.7          # 极端区域仓位缩减

  stop_loss:
    enabled: true
    use_support_resistance: true       # 使用支撑/阻力
    buffer_pct: 0.001                  # 缓冲 0.1%

  take_profit:
    high_confidence_pct: 0.03          # HIGH: 3%
    medium_confidence_pct: 0.02        # MEDIUM: 2%
    low_confidence_pct: 0.01           # LOW: 1%

  trailing_stop:
    enabled: true
    activation_pct: 0.01               # 激活阈值 1%
    distance_pct: 0.005                # 跟踪距离 0.5%
```

---

## 9. 完整数据流图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              系统启动                                        │
│                                                                             │
│  main_live.py → 加载配置 → 初始化策略 → 启动交易节点                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                           on_bar() - 每根K线触发                             │
│                                                                             │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                       │
│  │  1D K线     │   │  4H K线     │   │  15M K线    │                       │
│  │  (趋势层)   │   │  (决策层)   │   │  (执行层)   │                       │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘                       │
│         │                 │                 │                               │
│         ↓                 ↓                 ↓                               │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                       │
│  │ 更新 SMA200 │   │ 更新 4H 指标│   │ 更新 15M    │                       │
│  │ 更新 MACD   │   │ 评估方向    │   │ 技术指标    │                       │
│  └─────────────┘   └─────────────┘   └─────────────┘                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                        on_timer() - 每15分钟触发                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Step 1: 数据收集                              │   │
│  │                                                                     │   │
│  │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │   │
│  │   │ 技术指标 │  │ 情绪数据 │  │ 订单流   │  │ 衍生品   │          │   │
│  │   │ (15M)   │  │ (多空比) │  │ (买卖比) │  │ (OI/FR)  │          │   │
│  │   └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘          │   │
│  │        └─────────────┴─────────────┴─────────────┘                 │   │
│  │                              │                                      │   │
│  │                              ↓                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                 │                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Step 2: MTF 风险评估                          │   │
│  │                                                                     │   │
│  │   1D 趋势层: 价格 > SMA200 且 MACD > 0 ?                           │   │
│  │   ├─ 是 → RISK_ON (允许交易)                                       │   │
│  │   └─ 否 → RISK_OFF (禁止新开仓)                                    │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                 │                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Step 3: AI 多代理分析                         │   │
│  │                                                                     │   │
│  │   ┌─────────────┐         ┌─────────────┐                          │   │
│  │   │Bull Analyst │◄───────▶│Bear Analyst │                          │   │
│  │   │  (看多)     │  辩论2轮 │  (看空)     │                          │   │
│  │   └──────┬──────┘         └──────┬──────┘                          │   │
│  │          └───────────┬───────────┘                                  │   │
│  │                      ↓                                              │   │
│  │              ┌─────────────┐                                        │   │
│  │              │    Judge    │                                        │   │
│  │              │ (最终决策)  │                                        │   │
│  │              └──────┬──────┘                                        │   │
│  │                     ↓                                               │   │
│  │              ┌─────────────┐                                        │   │
│  │              │Risk Manager │                                        │   │
│  │              │ (风险评估)  │                                        │   │
│  │              └──────┬──────┘                                        │   │
│  │                     ↓                                               │   │
│  │              输出: BUY/SELL/HOLD + 信心度 + SL/TP                   │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                 │                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Step 4: MTF 信号过滤                          │   │
│  │                                                                     │   │
│  │   原始信号: BUY (HIGH)                                              │   │
│  │       │                                                             │   │
│  │       ↓                                                             │   │
│  │   ┌───────────────────────────────────────────────────────┐        │   │
│  │   │ 规则1: RISK_OFF 且无现仓? → 改为 HOLD                 │        │   │
│  │   │ 规则2: 决策层方向不匹配? → 改为 HOLD                  │        │   │
│  │   │ 规则3: RSI 不在 35-65? → 改为 HOLD                    │        │   │
│  │   └───────────────────────────────────────────────────────┘        │   │
│  │       │                                                             │   │
│  │       ↓                                                             │   │
│  │   最终信号: HOLD 或 BUY                                             │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                 │                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Step 5: 信号执行                              │   │
│  │                                                                     │   │
│  │   信心度检查: >= MEDIUM ?                                           │   │
│  │       │                                                             │   │
│  │       ↓                                                             │   │
│  │   仓位计算:                                                          │   │
│  │   $100 × 信心乘数 × 趋势乘数 × RSI乘数 → USDT                       │   │
│  │   USDT ÷ 价格 → BTC 数量                                            │   │
│  │       │                                                             │   │
│  │       ↓                                                             │   │
│  │   ┌─────────────────────────────────────────────────────┐          │   │
│  │   │ 有现仓?                                             │          │   │
│  │   │ ├─ 同方向 → 调整仓位                                │          │   │
│  │   │ └─ 反方向 → 平仓 + 反向开仓 (如允许)               │          │   │
│  │   │                                                     │          │   │
│  │   │ 无现仓?                                             │          │   │
│  │   │ └─ 开新仓 + 设置 SL/TP                             │          │   │
│  │   └─────────────────────────────────────────────────────┘          │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                 │                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Step 6: 风险管理                              │   │
│  │                                                                     │   │
│  │   ├─ 孤儿订单清理 (OCO)                                            │   │
│  │   └─ 移动止损更新 (如启用)                                         │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. 关键配置参数

### 10.1 资金配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `capital.equity` | 1000 | 备用资金值 |
| `capital.leverage` | 5 | 杠杆倍数 |
| `capital.use_real_balance_as_equity` | true | 自动获取真实余额 |

### 10.2 仓位配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `position.base_usdt_amount` | 100 | 基础仓位 USDT |
| `position.high_confidence_multiplier` | 1.5 | HIGH 信心乘数 |
| `position.medium_confidence_multiplier` | 1.0 | MEDIUM 信心乘数 |
| `position.low_confidence_multiplier` | 0.5 | LOW 信心乘数 |
| `position.max_position_ratio` | 0.30 | 最大仓位占权益比 |

### 10.3 风险配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `risk.min_confidence_to_trade` | MEDIUM | 最低交易信心 |
| `risk.allow_reversals` | true | 允许反向交易 |
| `risk.require_high_confidence_for_reversal` | false | 反向需要HIGH信心 |
| `risk.stop_loss.default_pct` | 0.02 | 默认止损 2% |
| `risk.take_profit.high_confidence_pct` | 0.03 | HIGH止盈 3% |
| `risk.take_profit.medium_confidence_pct` | 0.02 | MEDIUM止盈 2% |
| `risk.trailing_stop.enabled` | true | 启用移动止损 |
| `risk.trailing_stop.activation_pct` | 0.01 | 激活阈值 1% |

### 10.4 AI 配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ai.deepseek.model` | deepseek-chat | 模型名称 |
| `ai.deepseek.temperature` | 0.3 | 温度参数 |
| `ai.multi_agent.debate_rounds` | 2 | 辩论轮数 |

### 10.5 定时器配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `timing.timer_interval_sec` | 900 | 分析间隔 (15分钟) |

---

## 11. 文件映射表

| 模块 | 文件 | 关键方法/类 |
|------|------|------------|
| **入口** | `main_live.py` | `get_strategy_config()`, `setup_trading_node()` |
| **策略核心** | `strategy/deepseek_strategy.py` | `DeepSeekAIStrategy`, `on_timer()`, `_execute_trade()` |
| **交易逻辑** | `strategy/trading_logic.py` | `calculate_position_size()`, `validate_multiagent_sltp()` |
| **配置管理** | `utils/config_manager.py` | `ConfigManager` |
| **技术指标** | `indicators/technical_manager.py` | `TechnicalIndicatorManager` |
| **MTF管理** | `indicators/multi_timeframe_manager.py` | `MultiTimeframeManager` |
| **AI分析** | `agents/multi_agent_analyzer.py` | `MultiAgentAnalyzer` |
| **情绪数据** | `utils/sentiment_client.py` | `SentimentDataFetcher` |
| **订单流** | `utils/order_flow_processor.py` | `OrderFlowProcessor` |
| **衍生品** | `utils/coinalyze_client.py` | `CoinalyzeClient` |
| **Telegram** | `utils/telegram_bot.py` | `TelegramBot` |
| **配置文件** | `configs/base.yaml` | 所有配置参数 |

---

## 附录: 常见问题

### Q1: 为什么信号被改为 HOLD?

可能原因:
1. MTF 趋势层为 RISK_OFF (1D 价格 < SMA200)
2. 决策层方向不匹配 (BUY 但决策层是 ALLOW_SHORT)
3. 执行层 RSI 在极端区域 (< 35 或 > 65)
4. 信心度不足 (LOW 但最小要求是 MEDIUM)

### Q2: 如何减少频繁换向?

设置:
```yaml
risk:
  require_high_confidence_for_reversal: true
```

这样只有 HIGH 信心的反向信号才会执行。

### Q3: 如何调整风险?

保守设置:
```yaml
position:
  base_usdt_amount: 50        # 减少基础仓位
  max_position_ratio: 0.10    # 限制最大仓位

risk:
  min_confidence_to_trade: "HIGH"  # 只交易高信心
```

---

*文档结束*
