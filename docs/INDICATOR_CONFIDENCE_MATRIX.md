# Indicator Signal Confidence Matrix (方案 A — Prompt 层增强)

> **状态**: 待评估 (Not yet implemented)
> **目标**: 在 Judge prompt 的 `INDICATOR_DEFINITIONS` 后插入结构化权重矩阵，让 AI 在不同 market regime 下对不同信号给予量化的置信度调整
> **影响范围**: 仅修改 `agents/multi_agent_analyzer.py` 中的 prompt 文本，不改变代码逻辑

---

## 一、背景与动机

当前系统在 `INDICATOR_DEFINITIONS` (v3.27) 中用文字描述了指标在不同 regime 下的行为，但：
- AI 可能选择性忽略文字描述（尤其在数据量大时）
- 没有量化的 per-signal、per-regime confidence 参考
- 时序数据（20 bar 序列）、多源同类数据、衍生品时间维度信号完全没有 confidence 指导

## 二、插入位置

```
agents/multi_agent_analyzer.py
  └─ INDICATOR_DEFINITIONS (line ~54)
       └─ 在 "CONFLUENCE FRAMEWORK" 段落 (line ~172) 之后插入
```

仅插入 Judge 和 Risk Manager 的 system prompt。**不插入 Bull/Bear prompt**（辩论者应自由发挥，不受 multiplier 约束）。

## 三、Market Regime 定义（与现有一致）

| Regime | 条件 | 特征 |
|--------|------|------|
| 强趋势 (STRONG_TREND) | ADX > 40 | 趋势层主导，逆势信号需极强确认 |
| 弱趋势 (WEAK_TREND) | 25 < ADX ≤ 40 | 趋势重要但非绝对 |
| 震荡 (RANGING) | ADX < 20, 价格振荡 | 关键水平层权重最高，均值回归有效 |
| 挤压 (SQUEEZE) | ADX < 20 + BB Width 收窄至低点 | 大动作临近，方向未知 |

---

## 四、完整 Prompt 文本

以下是准备插入 prompt 的完整文本块：

```
====================================================================
SIGNAL CONFIDENCE MATRIX (v1.0)
====================================================================
When evaluating each confluence layer, apply these confidence
multipliers to weight each signal's reliability in the current regime.

MULTIPLIER SCALE:
  1.3+ = High confidence — signal is especially reliable in this regime
  1.0  = Standard confidence
  0.7  = Low confidence — needs other signals to confirm
  0.5- = Very low — unreliable in this regime, do NOT use as primary basis

====================================================================
SECTION A: SNAPSHOT SIGNALS (per confluence layer)
====================================================================

--- LAYER 1: TREND (1D) ---

| Signal                | STRONG_TREND | WEAK_TREND | RANGING | SQUEEZE | Nature   |
|-----------------------|:---:|:---:|:---:|:---:|----------|
| 1D SMA200 direction   | 1.3 | 1.0 | 0.4 | 0.3 | Lagging  |
| 1D ADX/DI direction   | 1.2 | 1.0 | 0.3 | 0.3 | Lagging  |
| 1D MACD zero-line     | 1.1 | 1.0 | 0.3 | 0.5 | Lagging  |
| 1D RSI level          | 0.9 | 1.0 | 0.7 | 0.6 | Sync     |
| 1D TREND VERDICT      | 1.2 | 1.0 | 0.4 | 0.3 | Computed |

Notes:
- STRONG_TREND: This layer is DOMINANT — all signals reliable
- RANGING: This layer is nearly irrelevant (ADX<20 means trend data is noise)
- SQUEEZE: Historical trend direction has low predictive value (direction about to change)
- TREND VERDICT is pre-computed from SMA200+MACD+DI+RSI — treat as summary, not independent signal

--- LAYER 2: MOMENTUM (4H) ---

| Signal                | STRONG_TREND | WEAK_TREND | RANGING | SQUEEZE | Nature   |
|-----------------------|:---:|:---:|:---:|:---:|----------|
| 4H RSI level          | 0.8 | 1.0 | 1.2 | 0.9 | Sync     |
| 4H RSI divergence*    | 0.5 | 0.8 | 1.3 | 1.1 | Leading  |
| 4H MACD cross         | 1.2 | 1.0 | 0.3 | 0.5 | Lagging  |
| 4H MACD histogram dir | 1.0 | 1.0 | 0.5 | 0.7 | Sync-lag |
| 4H ADX/DI direction   | 1.1 | 1.0 | 0.4 | 0.5 | Lagging  |
| 4H BB position        | 0.6 | 0.9 | 1.2 | 0.8 | Sync     |
| 4H SMA 20/50 cross    | 1.1 | 1.0 | 0.4 | 0.6 | Lagging  |
| CVD single-bar delta  | 0.9 | 1.0 | 1.2 | 1.3 | Leading  |
| CVD trend (cumulative)| 1.1 | 1.0 | 0.8 | 0.7 | Sync-lag |
| CVD divergence*       | 0.7 | 0.9 | 1.3 | 1.2 | Leading  |

Notes:
- *Divergence = inferred from series data (RSI or CVD vs price moving opposite directions)
- RSI in STRONG_TREND: Cardwell range shifts apply (40-80 uptrend, 20-60 downtrend) — traditional 30/70 FAIL
- MACD cross in RANGING: 74-97% false positive rate — nearly useless
- CVD single-bar in SQUEEZE: Pre-breakout fund flow has highest early-warning value
- 4H BB position in RANGING: Mean-reversion at bands works; in STRONG_TREND "walk the band" is normal (NOT reversal)

--- LAYER 3: KEY LEVELS (15M) ---

| Signal                | STRONG_TREND | WEAK_TREND | RANGING | SQUEEZE | Nature   |
|-----------------------|:---:|:---:|:---:|:---:|----------|
| S/R zone test (bounce)| 0.5 | 0.8 | 1.3 | 1.0 | Static   |
| S/R zone breakout     | 1.3 | 1.0 | 0.6 | 1.2 | Event    |
| 15M BB position       | 0.6 | 0.9 | 1.2 | 0.8 | Sync     |
| 15M BB Width level    | 0.7 | 0.8 | 0.9 | 1.4 | Sync     |
| OBI (order book imbal)| 0.6 | 0.8 | 1.1 | 1.2 | Realtime |
| OBI change rate       | 0.7 | 0.9 | 1.2 | 1.3 | Leading  |
| Bid/Ask depth change  | 0.7 | 0.9 | 1.1 | 1.2 | Leading  |
| Pressure gradient     | 0.6 | 0.8 | 1.1 | 1.2 | Leading  |
| Order walls (>3x avg) | 0.5 | 0.7 | 1.0 | 1.1 | Realtime |
| 15M SMA cross (5/20)  | 0.9 | 1.0 | 0.6 | 0.7 | Lagging  |
| 15M Volume ratio      | 0.9 | 1.0 | 1.1 | 1.3 | Sync     |
| Price vs period H/L   | 0.8 | 1.0 | 1.1 | 1.0 | Sync     |

Notes:
- S/R bounce rate: ADX>40 → ~25%, ADX<20 → ~70% (already in INDICATOR_DEFINITIONS)
- S/R breakout in STRONG_TREND: Trend continuation confirmation — high reliability
- OBI change rate > absolute OBI: OBI shifting from -0.3 to +0.1 is more informative than OBI=+0.1 alone
- Order walls in crypto: Spoofing risk always exists — never treat walls as guaranteed S/R
- 15M BB Width in SQUEEZE: Core squeeze detection signal — highest value in this regime
- Volume ratio in SQUEEZE: Volume surge confirms breakout — critical for direction confirmation

--- LAYER 4: DERIVATIVES ---

| Signal                       | STRONG_TREND | WEAK_TREND | RANGING | SQUEEZE | Nature   |
|------------------------------|:---:|:---:|:---:|:---:|----------|
| Funding Rate current value   | 0.7 | 0.9 | 1.0 | 1.0 | Sentiment|
| FR extreme (>±0.05%)        | 0.8 | 1.1 | 1.3 | 1.2 | Leading  |
| FR predicted vs settled diff | 0.9 | 1.0 | 1.1 | 1.2 | Leading  |
| FR settlement history trend  | 0.8 | 1.0 | 1.1 | 1.0 | Sync     |
| FR settlement countdown      | 0.7 | 0.8 | 0.9 | 1.0 | Temporal |
| Premium Index                | 0.8 | 1.0 | 1.1 | 1.2 | Leading  |
| OI↑ + Price↑ (new longs)    | 1.2 | 1.0 | 0.7 | 0.9 | Confirm  |
| OI↑ + Price↓ (new shorts)   | 1.2 | 1.0 | 0.7 | 0.9 | Confirm  |
| OI↓ (unwinding/liquidation) | 0.9 | 1.0 | 1.0 | 0.8 | Event    |
| Liquidation (large event)    | 1.0 | 1.1 | 1.2 | 1.3 | Leading  |
| Taker Buy/Sell Ratio         | 0.9 | 1.0 | 1.1 | 1.2 | Realtime |
| Top Traders L/S position     | 0.7 | 0.9 | 1.2 | 1.1 | Leading  |
| Global L/S extreme (>60%)   | 0.6 | 0.9 | 1.2 | 1.1 | Sentiment|
| Coinalyze L/S Ratio + trend | 0.7 | 0.9 | 1.1 | 1.0 | Sentiment|

Notes:
- FR current in STRONG_TREND: 0.01-0.03% in bull market is NORMAL, not bearish — do not over-interpret
- FR predicted vs settled: Sign reversal (e.g., +0.01% → -0.01%) = significant positioning change
- FR settlement countdown: <30min with extreme predicted rate → expect short-term volatility
- OI 4-quadrant in STRONG_TREND: New positioning confirms trend conviction — high reliability
- OI 4-quadrant in RANGING: May just be hedging activity — lower predictive value
- Top Traders vs Global L/S: Top Traders = institutional positioning (more predictive); Global = retail sentiment
- Taker Ratio: Real-time fund flow direction, similar to CVD but from different source — use for cross-validation
- Liquidation in SQUEEZE: Cascade liquidation can trigger the breakout direction

====================================================================
SECTION B: TIME-SERIES PATTERN SIGNALS
====================================================================
AI receives 20-bar (15M) time-series data. These patterns have different
confidence depending on regime. Detect patterns from series data, then
apply the corresponding multiplier.

--- PRICE SERIES PATTERNS ---

| Pattern               | STRONG_TREND | WEAK_TREND | RANGING | SQUEEZE | Nature  |
|-----------------------|:---:|:---:|:---:|:---:|---------|
| Higher highs/lows     | 1.3 | 1.0 | 0.5 | 0.6 | Confirm |
| Lower highs/lows      | 1.3 | 1.0 | 0.5 | 0.6 | Confirm |
| Range-bound oscillation| 0.4 | 0.7 | 1.3 | 1.0 | Confirm |
| Tightening range      | 0.5 | 0.8 | 1.0 | 1.4 | Leading |
| Volume climax (spike) | 1.0 | 1.1 | 1.2 | 1.4 | Event   |

--- INDICATOR SERIES PATTERNS ---

| Pattern               | STRONG_TREND | WEAK_TREND | RANGING | SQUEEZE | Nature  |
|-----------------------|:---:|:---:|:---:|:---:|---------|
| ADX series rising     | 1.2 | 1.1 | 0.5 | 1.0 | Leading — trend strengthening |
| ADX series falling    | 0.8 | 1.0 | 0.5 | 0.7 | Leading — trend weakening    |
| BB Width narrowing    | 0.6 | 0.8 | 1.0 | 1.5 | Leading — squeeze forming    |
| BB Width expanding    | 1.1 | 1.0 | 0.8 | 1.3 | Confirm — breakout in progress |
| SMA convergence       | 0.7 | 0.9 | 0.8 | 1.2 | Leading — regime change coming |
| SMA divergence        | 1.2 | 1.0 | 0.5 | 0.8 | Confirm — trend established   |
| RSI trend (accel/decel)| 0.9 | 1.0 | 1.1 | 1.0 | Sync   |
| MACD histogram momentum| 1.0 | 1.0 | 0.5 | 0.8 | Sync-lag|
| Volume trend (expanding)| 1.1 | 1.0 | 1.0 | 1.3 | Sync-leading |
| Volume trend (shrinking)| 0.8 | 0.9 | 0.9 | 0.7 | Warning — move losing conviction |

--- K-LINE OHLCV PATTERNS ---

| Pattern               | STRONG_TREND | WEAK_TREND | RANGING | SQUEEZE | Nature  |
|-----------------------|:---:|:---:|:---:|:---:|---------|
| Engulfing candle      | 0.7 | 1.0 | 1.2 | 1.3 | Leading — reversal signal  |
| Doji at S/R           | 0.5 | 0.8 | 1.3 | 1.1 | Leading — indecision at key level |
| Long wicks (rejection)| 0.6 | 0.9 | 1.2 | 1.1 | Leading — price rejection   |
| Consecutive same-dir  | 1.2 | 1.0 | 0.6 | 0.8 | Confirm — trend continuation |

Notes:
- BB Width narrowing is THE defining signal for SQUEEZE — highest multiplier (1.5)
- ADX series direction predicts regime change BEFORE regime threshold crossover
- Volume expansion in SQUEEZE: Breakout validation — if no volume → likely false breakout
- K-line patterns in STRONG_TREND: Reversal patterns (engulfing, doji) often fail against the trend
- K-line patterns in RANGING at S/R: Highest reversal reliability (70%+ when aligned with zone)

====================================================================
SECTION C: MULTI-SOURCE SIGNAL DIFFERENTIATION
====================================================================
The system receives similar data from multiple sources. These are NOT
redundant — each source has different characteristics.

--- LONG/SHORT POSITIONING (3 different sources) ---

| Source                | What it represents     | Predictive edge          | Multiplier boost |
|-----------------------|------------------------|--------------------------|:---:|
| Top Traders Position  | Institutional/whale positioning | Best predictor — smart money | ×1.2 vs base |
| Taker Buy/Sell Ratio  | Real-time aggressive order flow | Real-time direction      | ×1.1 vs base |
| Binance Global L/S    | Retail sentiment (all accounts) | Contrarian at extremes   | ×1.0 (base)  |
| Coinalyze L/S Ratio   | Exchange-specific L/S snapshot  | Cross-validates Binance  | ×0.9 vs base |

RULE: When Top Traders and Global L/S diverge, weight Top Traders higher.
       When all 3+ sources agree at extremes → very high confidence signal.

--- OPEN INTEREST (2 sources) ---

| Source        | Characteristic           | Usage                     |
|---------------|--------------------------|---------------------------|
| Coinalyze OI  | Aggregated multi-exchange | Better for macro trend    |
| Binance OI    | Single exchange, real-time| Better for short-term moves|

RULE: If both sources show same trend → confidence +0.2
      If sources disagree → use Binance for 15M execution, Coinalyze for 4H context

--- FUND FLOW DIRECTION (2 sources) ---

| Source        | Calculation              | Best for                  |
|---------------|--------------------------|---------------------------|
| CVD (K-line)  | Cumulative taker delta   | Trend over multiple bars  |
| Taker Ratio   | Buy vol / Sell vol snapshot | Real-time directional pressure |

RULE: CVD trend + Taker Ratio same direction → cross-validated, confidence +0.2
      If they diverge → situation is transitioning, reduce confidence -0.2

====================================================================
SECTION D: GLOBAL SIGNAL QUALITY MODIFIERS
====================================================================
These are NOT directional signals. They modify the confidence of ALL
other signals globally.

| Condition                         | Modifier | Applies to  |
|-----------------------------------|:---:|-------------|
| 24h Volume < 50% of 7d average   | ×0.7 | All signals — low-volume moves unreliable |
| 24h Volume > 200% of 7d average  | ×1.1 | All signals — high conviction market      |
| Spread > 0.05%                    | ×0.8 | Layer 3 + Risk Manager — execution risk   |
| Slippage (1 BTC) > 0.1%          | ×0.7 | Risk Manager — reduce position size       |
| Multiple data sources unavailable | ×0.8 | Affected layers — incomplete picture      |
| FR settlement < 30 min away      | ×0.8 | Short-term signals — expect volatility    |

RULE: Global modifiers stack multiplicatively with signal multipliers.
      Example: RSI divergence (1.3) in low-volume market (×0.7) = effective 0.91

====================================================================
SECTION E: APPLICATION RULES
====================================================================

RULE 1 — Layer evaluation:
  For each confluence layer, assess each signal's influence as:
    Effective weight = Base signal strength × confidence_multiplier(signal, regime)

RULE 2 — Low-confidence cutoff:
  If a signal's multiplier < 0.5, do NOT use it as primary basis for any layer judgment.

RULE 3 — Conflict resolution:
  If leading signals and lagging signals within the same layer conflict,
  prioritize the one with the HIGHER multiplier in current regime.

RULE 4 — Neutral threshold:
  If only signals with multiplier < 0.7 support a direction in a layer,
  that layer should be judged NEUTRAL.

RULE 5 — SQUEEZE special case:
  In SQUEEZE regime, wait for breakout direction confirmation (volume + price)
  before applying directional multipliers. Pre-breakout: only use non-directional
  signals (BB Width, Volume, OBI change rate).

RULE 6 — Counter-trend in STRONG_TREND:
  Even if a counter-trend signal has high multiplier, it requires at least
  2 independent confirming signals before consideration.

RULE 7 — Multi-source agreement:
  When 3+ independent sources (different data types) agree on direction,
  add +0.2 confidence bonus to that layer's assessment.

RULE 8 — Global quality check:
  Before final decision, check Section D conditions. If any global modifier
  applies, adjust overall confidence accordingly. Multiple modifiers stack.
```

---

## 五、与现有系统的兼容性

| 现有 Prompt 段落 | 方案 A 关系 | 冲突 |
|-----------------|-----------|------|
| INDICATOR REFERENCE (v3.27) | 增强 — 将文字描述量化为 multiplier | 无冲突 |
| Judge STEP 1 (Regime 判断) | 依赖 — multiplier 需要先确定 regime | 无冲突 |
| Judge STEP 2 (层级权重) | 互补 — 层级权重 = "哪层重要"，multiplier = "层内哪个信号可信" | 无冲突 |
| Judge Few-shot (4 个示例) | 需增强 — 建议增加 1-2 个展示 multiplier 应用的示例 | 需补充 |
| Risk Manager prompt | 增强 — Risk Manager 可参考 Section D 做仓位调整 | 无冲突 |
| Bull/Bear prompt | 不插入 — 辩论者应自由发挥 | 不影响 |
| base.yaml weights | 不同维度 — yaml = 数据类别级 (0.30/0.25...)，本方案 = 信号级 | 无冲突 |

## 六、覆盖度验证

### AI 实际接收的 49 个数据点 vs 方案 A 覆盖

| 数据来源 | 数据点数 | 方案 A 覆盖 | 覆盖方式 |
|---------|:---:|:---:|---------|
| 15M 技术快照 (Price, SMA, RSI, MACD, ADX, BB, Volume) | 9 | 9 | Section A Layer 2+3 |
| 4H 技术快照 (RSI, MACD, ADX, SMA, BB) | 5 | 5 | Section A Layer 2 |
| 1D 技术快照 (SMA200, MACD, RSI, ADX/DI, TREND VERDICT) | 5 | 5 | Section A Layer 1 |
| Historical 时序 (Price, RSI, MACD, Volume, ADX, DI, BB Width, SMA) | 8 | 8 | Section B |
| K-line OHLCV 形态 | 1 | 1 | Section B K-line patterns |
| Order Flow (Buy Ratio, CVD Trend, Avg Trade Size) | 3 | 3 | Section A Layer 2 + Section C |
| Coinalyze 衍生品 (OI, FR 各维度, Liquidations, L/S) | 8 | 8 | Section A Layer 4 |
| Binance 衍生品 (Top Traders, Taker, OI, 24h Stats) | 4 | 4 | Section A Layer 4 + Section C |
| 订单簿 (OBI, Dynamics, Gradient, Anomalies, Liquidity) | 5 | 5 | Section A Layer 3 + Section D |
| Sentiment (L/S Ratio + History) | 1 | 1 | Section A Layer 4 |
| **合计** | **49** | **49** | **100% 覆盖** |

## 七、Token 成本估算

| 段落 | 估算 Tokens |
|------|:---:|
| Section A (4 层快照信号) | ~500 |
| Section B (时序模式) | ~350 |
| Section C (多源区分) | ~200 |
| Section D (全局修正器) | ~100 |
| Section E (应用规则) | ~150 |
| **合计** | **~1,300** |

当前 `INDICATOR_DEFINITIONS` 约 2,000 tokens，增加后约 3,300 tokens。在 DeepSeek 的 64K 上下文窗口中完全可接受（总 prompt 通常 8-12K tokens）。

## 八、实施步骤

1. **代码修改**：在 `multi_agent_analyzer.py` 的 `INDICATOR_DEFINITIONS` 字符串末尾（line ~182 后）插入 Section A-E 的完整文本
2. **Judge prompt 增强**：在现有 4 个 few-shot 示例后增加 1-2 个展示 multiplier 应用的示例
3. **Risk Manager prompt 增强**：在系统 prompt 中引用 Section D 的全局修正器
4. **验证**：运行 `python3 scripts/diagnose_realtime.py --export` 检查 AI 是否在输出中体现 multiplier 的影响
5. **迭代**：根据 ai_calls 日志中 AI 的实际行为，逐步调整 multiplier 数值

## 九、风险与注意事项

1. **AI 遵循度不确定**：DeepSeek 对表格数据的遵循度通常不错，但需要通过 few-shot 强化
2. **Multiplier 数值需迭代**：当前数值基于金融理论和经验估算，非回测验证
3. **Prompt 长度增加**：约增加 1,300 tokens，需监控是否影响 AI 输出质量
4. **不修改 Bull/Bear**：辩论者保持自由发挥，只有 Judge 和 Risk Manager 参考 multiplier
