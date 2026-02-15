# Indicator Signal Confidence Matrix (方案 A — Prompt 层增强)

> **状态**: 待评估 → **已评估修正 (v1.1)**
> **目标**: 在 Judge prompt 的 `INDICATOR_DEFINITIONS` 后插入结构化权重矩阵，让 AI 在不同 market regime 下对不同信号给予量化的置信度调整
> **影响范围**: 仅修改 `agents/multi_agent_analyzer.py` 中的 prompt 文本，不改变代码逻辑
> **评审**: 10 维度专家评审，修复 27 处问题 (v1.0 → v1.1)

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

## 三、Market Regime 定义（与现有一致 + v1.1 过渡区）

| Regime | 条件 | 特征 |
|--------|------|------|
| 强趋势 (STRONG_TREND) | ADX > 40 | 趋势层主导，逆势信号需极强确认 |
| 弱趋势 (WEAK_TREND) | 25 < ADX ≤ 40 | 趋势重要但非绝对 |
| 震荡 (RANGING) | ADX < 20, 价格振荡 | 关键水平层权重最高，均值回归有效 |
| 挤压 (SQUEEZE) | ADX < 20 + BB Width 收窄至低点 | 大动作临近，方向未知 |

**v1.1 新增 — 过渡区处理**：
| 过渡区 | ADX 范围 | 处理方式 |
|--------|---------|---------|
| RANGING → WEAK_TREND | 18-22 | 两个 regime 的 multiplier 取平均值 |
| WEAK_TREND → STRONG_TREND | 35-45 | 两个 regime 的 multiplier 取平均值 |

---

## 四、完整 Prompt 文本

以下是准备插入 prompt 的完整文本块：

```
====================================================================
SIGNAL CONFIDENCE MATRIX (v1.1)
====================================================================
When evaluating each confluence layer, apply these confidence
multipliers to weight each signal's reliability in the current regime.

MULTIPLIER SCALE:
  HIGH (1.2+) = Signal is especially reliable in this regime
  STD  (1.0)  = Standard confidence
  LOW  (0.7)  = Needs other signals to confirm before trusting
  SKIP (≤0.4) = Unreliable in this regime — ignore as primary basis

REGIME TRANSITION: When ADX is near a boundary (18-22 or 35-45),
blend the multipliers of adjacent regimes (take the average).

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

Notes:
- STRONG_TREND: This layer is DOMINANT — all signals reliable.
- RANGING: This layer is nearly irrelevant (ADX<20 = trend data is noise).
- SQUEEZE: Historical trend direction has low predictive value (about to change).
- ⚠️ 1D TREND VERDICT (STRONG_BULLISH etc.) is pre-computed from these 4 signals.
  It is a SUMMARY — do NOT count it as a 5th independent signal.
  Use it for quick reference, then verify with the individual signals above.

--- LAYER 2: MOMENTUM (4H) ---

| Signal                | STRONG_TREND | WEAK_TREND | RANGING | SQUEEZE | Nature   |
|-----------------------|:---:|:---:|:---:|:---:|----------|
| 4H RSI level          | 0.8 | 1.0 | 1.2 | 0.9 | Sync     |
| 4H RSI divergence*    | 0.6 | 0.8 | 1.3 | 1.1 | Leading  |
| 4H MACD cross         | 1.2 | 1.0 | 0.3 | 0.5 | Lagging  |
| 4H MACD histogram dir | 1.0 | 1.0 | 0.5 | 0.7 | Sync-lag |
| 4H ADX/DI direction   | 1.1 | 1.0 | 0.4 | 0.5 | Lagging  |
| 4H BB position        | 0.6 | 0.9 | 1.2 | 0.8 | Sync     |
| 4H SMA 20/50 cross    | 1.1 | 1.0 | 0.4 | 0.6 | Lagging  |
| CVD single-bar delta  | 0.9 | 1.0 | 1.2 | 1.3 | Leading  |
| CVD trend (cumulative)| 1.1 | 1.0 | 0.8 | 0.7 | Sync-lag |
| CVD divergence*       | 0.7 | 0.9 | 1.3 | 1.2 | Leading  |
| Buy Ratio (taker %)   | 0.8 | 1.0 | 1.1 | 1.2 | Realtime |
| Avg Trade Size change | 0.7 | 0.9 | 1.0 | 1.2 | Leading  |

Notes:
- *Divergence = inferred from series data (RSI or CVD vs price moving opposite directions).
- RSI in STRONG_TREND: Cardwell range shifts apply (40-80 uptrend, 20-60 downtrend)
  — traditional 30/70 FAIL. RSI divergence at 0.6 because it still signals deceleration risk.
- MACD cross in RANGING: 74-97% false positive rate — nearly useless.
- CVD single-bar in SQUEEZE: Pre-breakout fund flow has highest early-warning value.
- 4H BB position in RANGING: Mean-reversion at bands works; in STRONG_TREND "walk the band"
  is normal (NOT reversal).
- Buy Ratio: Taker buy percentage from Order Flow data. >55% = buy pressure, <45% = sell pressure.
- Avg Trade Size: Sudden increase = institutional activity (leading signal for direction).

--- LAYER 3: KEY LEVELS (15M) ---

| Signal                | STRONG_TREND | WEAK_TREND | RANGING | SQUEEZE | Nature   |
|-----------------------|:---:|:---:|:---:|:---:|----------|
| S/R zone test (bounce)| 0.5 | 0.8 | 1.3 | 1.0 | Static   |
| S/R zone breakout     | 1.3 | 1.0 | 0.6 | 1.2 | Event    |
| 15M BB position       | 0.6 | 0.9 | 1.2 | 0.8 | Sync     |
| 15M BB Width level    | 0.7 | 0.8 | 0.9 | 1.3 | Sync     |
| OBI (order book imbal)| 0.6 | 0.8 | 1.1 | 1.2 | Realtime |
| OBI change rate       | 0.7 | 0.9 | 1.2 | 1.3 | Leading  |
| Bid/Ask depth change  | 0.7 | 0.9 | 1.1 | 1.2 | Leading  |
| Pressure gradient     | 0.6 | 0.8 | 1.1 | 1.2 | Leading  |
| Order walls (>3x avg) | 0.4 | 0.6 | 0.9 | 1.0 | Realtime |
| 15M SMA cross (5/20)  | 0.9 | 1.0 | 0.6 | 0.7 | Lagging  |
| 15M Volume ratio      | 0.9 | 1.0 | 1.1 | 1.3 | Sync     |
| Price vs period H/L   | 0.8 | 1.0 | 1.1 | 1.0 | Sync     |
| Spread (liquidity)    | 0.9 | 1.0 | 1.0 | 1.1 | Quality  |
| Slippage (execution)  | 0.9 | 1.0 | 1.0 | 1.1 | Quality  |

Notes:
- S/R bounce rate: ADX>40 → ~25%, ADX<20 → ~70% (already in INDICATOR_DEFINITIONS).
- S/R breakout in STRONG_TREND: Trend continuation confirmation — high reliability.
- OBI change rate > absolute OBI: OBI shifting from -0.3 to +0.1 is more informative
  than OBI=+0.1 alone.
- Order walls in crypto: Spoofing probability is HIGH (>70% of large walls are pulled
  before touch in trending markets). SKIP in STRONG_TREND, treat cautiously elsewhere.
- Spread & Slippage: Not directional signals — they indicate execution quality.
  High spread (>0.05%) or high slippage (>0.1% for 1 BTC) → reduce ALL Layer 3 signals
  by one confidence tier AND reduce position size.

--- LAYER 4: DERIVATIVES ---
⚠️ This layer has the most signals. To prevent Layer 4 from dominating
decisions purely by signal count, group related signals and evaluate
the GROUP as one input (not each signal separately):
  Group A: Funding Rate (current + extreme + predicted + history + countdown) → 1 input
  Group B: Open Interest (OI 4-quadrant + OI trend) → 1 input
  Group C: Positioning (Top Traders + Global L/S + Coinalyze L/S) → 1 input
  Group D: Real-time flow (Taker Ratio + Liquidations) → 1 input

| Signal                       | STRONG_TREND | WEAK_TREND | RANGING | SQUEEZE | Nature   |
|------------------------------|:---:|:---:|:---:|:---:|----------|
| — GROUP A: FUNDING RATE —    |     |     |     |     |          |
| FR current value             | 0.8 | 0.9 | 1.0 | 1.0 | Sentiment|
| FR extreme (>±0.05%)        | 0.8 | 1.1 | 1.3 | 1.2 | Leading  |
| FR predicted vs settled diff | 0.9 | 1.0 | 1.1 | 1.2 | Leading  |
| FR settlement history trend  | 0.8 | 1.0 | 1.1 | 1.0 | Sync     |
| FR settlement countdown      | 0.7 | 0.8 | 0.9 | 1.0 | Temporal |
| — GROUP B: OPEN INTEREST —   |     |     |     |     |          |
| Premium Index                | 0.8 | 1.0 | 1.1 | 1.2 | Leading  |
| OI↑ + Price↑ (new longs)    | 1.2 | 1.0 | 0.8 | 0.9 | Confirm  |
| OI↑ + Price↓ (new shorts)   | 1.2 | 1.0 | 0.8 | 0.9 | Confirm  |
| OI↓ (unwinding/liquidation) | 0.9 | 1.0 | 1.0 | 0.8 | Event    |
| — GROUP C: POSITIONING —     |     |     |     |     |          |
| Top Traders L/S position     | 1.0 | 1.0 | 1.2 | 1.1 | Leading  |
| Global L/S extreme (>60%)   | 0.6 | 0.9 | 1.2 | 1.1 | Sentiment|
| Coinalyze L/S Ratio + trend | 0.7 | 0.9 | 1.1 | 1.0 | Sentiment|
| — GROUP D: REAL-TIME FLOW —  |     |     |     |     |          |
| Taker Buy/Sell Ratio         | 0.9 | 1.0 | 1.1 | 1.2 | Realtime |
| Liquidation (large event)    | 1.0 | 1.1 | 1.2 | 1.3 | Leading  |
| 24h Volume level             | 0.8 | 1.0 | 1.0 | 1.1 | Context  |
| 24h Price Change %           | 0.7 | 0.9 | 0.9 | 1.0 | Context  |

Notes:
- ⚠️ GROUP RULE: Pick the strongest signal within each group to represent it.
  Do NOT stack all FR signals into one massive FR-driven conclusion.
- FR current in STRONG_TREND: 0.01-0.03% in bull market is NORMAL — don't over-interpret.
- FR predicted vs settled: Sign reversal (+0.01% → -0.01%) = significant positioning change.
- FR settlement countdown: <30min + extreme predicted rate → expect short-term volatility.
- OI 4-quadrant in STRONG_TREND: New positioning confirms trend — high reliability.
- OI 4-quadrant in RANGING: May be hedging activity — lower but still moderate value (0.8).
- Top Traders in STRONG_TREND: Smart money aligning WITH trend = confirmation signal (1.0).
  Top Traders AGAINST trend in STRONG_TREND = early warning but needs 2+ confirmations.
- Taker Ratio: Real-time fund flow, cross-validate with CVD (Section C).
- Liquidation in SQUEEZE: Cascade liquidation can trigger breakout direction.
- 24h Volume & Price Change: Context signals — low volume reduces all signal reliability.

====================================================================
SECTION B: TIME-SERIES PATTERN SIGNALS
====================================================================
AI receives 20-bar (15M) time-series data for price, RSI, MACD,
MACD Signal, volume, ADX, DI+, DI-, BB Width, and SMA.
Detect patterns from these series, then apply multipliers.

--- PRICE SERIES PATTERNS ---

| Pattern               | STRONG_TREND | WEAK_TREND | RANGING | SQUEEZE | Nature  |
|-----------------------|:---:|:---:|:---:|:---:|---------|
| Higher highs/lows     | 1.3 | 1.0 | 0.5 | 0.6 | Confirm |
| Lower highs/lows      | 1.3 | 1.0 | 0.5 | 0.6 | Confirm |
| Range-bound oscillation| 0.4 | 0.7 | 1.3 | 1.0 | Confirm |
| Tightening range      | 0.5 | 0.8 | 1.0 | 1.3 | Leading |
| Volume climax (spike) | 1.0 | 1.1 | 1.2 | 1.3 | Event   |

--- INDICATOR SERIES PATTERNS ---

| Pattern                | STRONG_TREND | WEAK_TREND | RANGING | SQUEEZE | Nature  |
|------------------------|:---:|:---:|:---:|:---:|---------|
| ADX series rising      | 1.2 | 1.1 | 1.3 | 1.2 | Leading — trend forming/strengthening |
| ADX series falling     | 0.8 | 1.0 | 0.7 | 0.7 | Leading — trend weakening             |
| BB Width narrowing     | 0.6 | 0.8 | 1.0 | 1.3 | Leading — squeeze forming             |
| BB Width expanding     | 1.1 | 1.0 | 0.8 | 1.3 | Confirm — breakout in progress        |
| SMA convergence (5→20) | 0.7 | 0.9 | 1.1 | 1.2 | Leading — regime change coming        |
| SMA divergence (spread)| 1.2 | 1.0 | 0.5 | 0.8 | Confirm — trend established           |
| RSI trend (accel/decel)| 0.9 | 1.0 | 1.1 | 1.0 | Sync                                  |
| MACD histogram momentum| 1.0 | 1.0 | 0.5 | 0.8 | Sync-lag                              |
| Volume trend (expanding)| 1.1 | 1.0 | 1.0 | 1.3 | Sync-leading                          |
| Volume trend (shrinking)| 0.8 | 0.9 | 0.9 | 0.7 | Warning — move losing conviction      |

--- K-LINE OHLCV PATTERNS ---
(Detected from the OHLCV table provided to AI)

| Pattern               | STRONG_TREND | WEAK_TREND | RANGING | SQUEEZE | Nature  |
|-----------------------|:---:|:---:|:---:|:---:|---------|
| Engulfing candle      | 0.7 | 1.0 | 1.2 | 1.3 | Leading — reversal signal  |
| Doji at S/R           | 0.5 | 0.8 | 1.3 | 1.1 | Leading — indecision       |
| Long wicks (rejection)| 0.6 | 0.9 | 1.2 | 1.1 | Leading — price rejection  |
| Consecutive same-dir  | 1.2 | 1.0 | 0.6 | 0.8 | Confirm — continuation     |

Notes:
- ⚠️ ADX rising in RANGING (1.3) = CRITICAL leading signal. ADX climbing from 12→18 means
  regime is about to shift from RANGING to TRENDING. This is one of the most valuable
  signals in the entire matrix — it predicts the NEXT regime.
- BB Width narrowing in SQUEEZE at 1.3 (not 1.5): BB Width narrowing DEFINES the squeeze,
  so giving it the highest multiplier creates circular logic. Use 1.3 for the narrowing
  PROCESS, but the squeeze regime itself is already identified by STEP 1.
- SMA convergence in RANGING (1.1): Converging SMAs in a range = breakout forming, valuable.
- Volume expansion in SQUEEZE: Breakout validation — if no volume → likely false breakout.
- K-line patterns: In STRONG_TREND, reversal patterns (engulfing, doji) often fail.
  In RANGING at S/R: Highest reversal reliability (70%+ when aligned with zone).

====================================================================
SECTION C: MULTI-SOURCE SIGNAL DIFFERENTIATION
====================================================================
The system receives similar data from multiple sources. These are NOT
redundant — each source has different predictive characteristics.

--- LONG/SHORT POSITIONING (3 sources) ---

| Source                | Represents                 | Edge                         | Relative weight |
|-----------------------|----------------------------|------------------------------|:---:|
| Top Traders Position  | Institutional/whale positions | Best predictor (smart money)| Highest         |
| Taker Buy/Sell Ratio  | Real-time aggressive flow  | Real-time direction          | High            |
| Binance Global L/S    | Retail sentiment (all accounts)| Contrarian at extremes    | Base            |
| Coinalyze L/S Ratio   | Exchange-specific snapshot  | Cross-validates Binance      | Below base      |

RULE: When Top Traders and Global L/S diverge → weight Top Traders.
      When all 3+ sources agree at extremes → very HIGH confidence.
      Top Traders AGAINST the trend in STRONG_TREND → early reversal warning.

--- OPEN INTEREST (2 sources) ---

| Source        | Characteristic           | Best for                  |
|---------------|--------------------------|---------------------------|
| Coinalyze OI  | Aggregated multi-exchange | Macro trend (4H context)  |
| Binance OI    | Single exchange, real-time| Short-term moves (15M)    |

RULE: Same trend from both → add one confidence tier to OI assessment.
      If they disagree → use Binance for execution, Coinalyze for context.

--- FUND FLOW DIRECTION (2 sources) ---

| Source        | Calculation              | Best for                  |
|---------------|--------------------------|---------------------------|
| CVD (K-line)  | Cumulative taker delta   | Trend over multiple bars  |
| Taker Ratio   | Buy vol / Sell vol snapshot | Real-time pressure      |

RULE: CVD + Taker same direction → cross-validated, add one confidence tier.
      If they diverge → market is transitioning, reduce confidence one tier.

====================================================================
SECTION D: GLOBAL SIGNAL QUALITY MODIFIERS
====================================================================
These are NOT directional signals. They modify the RELIABILITY of all
other signals. Apply BEFORE making final decision.

Instead of exact multipliers (which are hard to compute mentally),
use a TIER SYSTEM: each condition shifts all signal confidence DOWN
by one tier (e.g., HIGH→STD, STD→LOW, LOW→SKIP).

| Condition                                    | Effect          | Applies to         |
|----------------------------------------------|:---:|---------------------|
| Volume Ratio < 0.5x (from 15M data)         | DOWN one tier   | ALL signals         |
| Volume Ratio > 2.0x                          | UP one tier     | ALL signals         |
| Spread > 0.05% OR Slippage > 0.1%           | DOWN one tier   | Layer 3 + position sizing |
| 2+ data sources unavailable (Coinalyze etc.) | DOWN one tier   | Affected layers     |
| FR settlement < 30 min away                  | DOWN one tier   | Short-term (15M) signals |
| Weekend/holiday (low global participation)   | DOWN one tier   | ALL signals (crypto liquidity ~40-60% of weekday) |

Notes:
- Tier shifts stack: 2 conditions = DOWN two tiers.
  Example: RSI divergence (HIGH=1.2) + low-volume (DOWN) + weekend (DOWN) = LOW (0.7 effective).
- Volume Ratio comes from the 15M technical data ("Volume Ratio: X.XXx average").
  Use this instead of comparing 24h volume to 7d average (which is not in the data).
- Weekend detection: If data shows consistently low volume across multiple bars
  and reduced orderbook depth, treat as weekend/low-liquidity environment.

====================================================================
SECTION E: APPLICATION RULES
====================================================================

RULE 1 — Layer evaluation:
  For each confluence layer, assess each signal's influence weighted by
  its confidence tier in the current regime:
    HIGH (1.2+) = Primary evidence for layer judgment
    STD  (1.0)  = Supporting evidence
    LOW  (0.7)  = Note but don't base judgment on it alone
    SKIP (≤0.4) = Ignore for this regime

RULE 2 — TREND VERDICT is not a 5th signal:
  The pre-computed 1D TREND VERDICT (STRONG_BULLISH etc.) is a summary
  of the 4 Layer 1 signals. Use it for quick reference only.
  Do NOT count it as an additional independent signal when scoring Layer 1.

RULE 3 — Conflict resolution:
  If leading signals and lagging signals within the same layer conflict,
  prioritize the one with the HIGHER confidence tier in current regime.

RULE 4 — Neutral threshold:
  If only SKIP or LOW signals support a direction in a layer,
  that layer should be judged NEUTRAL.

RULE 5 — SQUEEZE special case:
  In SQUEEZE, wait for breakout confirmation (volume + price + direction)
  before applying directional multipliers. Pre-breakout: focus on
  non-directional signals (BB Width, Volume, OBI change rate, ADX rising).

RULE 6 — Counter-trend in STRONG_TREND:
  Even HIGH-confidence counter-trend signals require at least
  2 independent confirming signals before consideration.

RULE 7 — Multi-source agreement:
  When 3+ independent sources (different data types) agree on direction,
  upgrade that layer's confidence by one tier.

RULE 8 — Layer 4 grouping (anti-stacking):
  Layer 4 signals MUST be evaluated in 4 groups (A/B/C/D as defined above).
  Each group contributes ONE input to the layer judgment, not 14 separate inputs.
  This prevents derivatives data from overwhelming other layers.

RULE 9 — Global quality check:
  Before final decision, check Section D conditions.
  Apply tier shifts to overall confidence. Tier shifts stack.
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
| 1D 技术快照 (SMA200, MACD, RSI, ADX/DI + TREND VERDICT) | 5 | 5 | Section A Layer 1 (VERDICT as note) |
| Historical 时序 (Price, RSI, MACD, Volume, ADX, DI, BB Width, SMA) | 8 | 8 | Section B |
| K-line OHLCV 形态 | 1 | 1 | Section B K-line patterns |
| Order Flow (Buy Ratio, CVD Trend, Avg Trade Size) | 3 | 3 | Section A Layer 2 (Buy Ratio + Avg Trade Size 显式列出) |
| Coinalyze 衍生品 (OI, FR 各维度, Liquidations, L/S) | 8 | 8 | Section A Layer 4 Group A+B |
| Binance 衍生品 (Top Traders, Taker, OI, 24h Stats) | 4 | 4 | Section A Layer 4 Group C+D |
| 订单簿 (OBI, Dynamics, Gradient, Anomalies, Liquidity) | 5 | 5 | Section A Layer 3 (Spread/Slippage 显式列出) |
| Sentiment (L/S Ratio + History) | 1 | 1 | Section A Layer 4 Group C |
| **合计** | **49** | **49** | **100% 覆盖** |

## 七、Token 成本估算

| 段落 | 估算 Tokens |
|------|:---:|
| Section A (4 层快照信号 + grouping) | ~600 |
| Section B (时序模式) | ~350 |
| Section C (多源区分) | ~200 |
| Section D (全局修正器 — 档位制) | ~120 |
| Section E (应用规则 — 9 条) | ~180 |
| **合计** | **~1,450** |

当前 Judge prompt = 11,681 tokens，增加后约 13,100 tokens。在 DeepSeek 的 64K 上下文窗口中完全可接受。

## 八、实施步骤

1. **代码修改**：在 `multi_agent_analyzer.py` 的 `INDICATOR_DEFINITIONS` 字符串末尾（line ~182 后）插入 Section A-E 的完整文本
2. **Judge prompt 增强**：在现有 4 个 few-shot 示例后增加 1-2 个展示 multiplier 应用的示例
3. **Risk Manager prompt 增强**：在系统 prompt 中引用 Section D 的全局修正器（档位制）
4. **验证**：运行 `python3 scripts/diagnose_realtime.py --export` 检查 AI 是否在输出中体现 multiplier 的影响
5. **迭代**：根据 ai_calls 日志中 AI 的实际行为，逐步调整 multiplier 数值

## 九、风险与注意事项

1. **AI 遵循度不确定**：DeepSeek 对表格数据的遵循度通常不错，但需要通过 few-shot 强化
2. **Multiplier 数值需迭代**：当前数值基于金融理论和经验估算，非回测验证
3. **Prompt 长度增加**：约增加 1,450 tokens，需监控是否影响 AI 输出质量
4. **不修改 Bull/Bear**：辩论者保持自由发挥，只有 Judge 和 Risk Manager 参考 multiplier
5. **周末检测为启发式**：AI 无直接日期数据，通过 volume+depth 间接推断

## 十、v1.0 → v1.1 变更日志

### 评审发现的 27 处问题 (全部已修复)

**金融有效性修正 (6 处)**：
| # | 信号 | v1.0 | v1.1 | 理由 |
|---|------|:---:|:---:|------|
| F1 | Top Traders L/S @ STRONG_TREND | 0.7 | **1.0** | 大户顺势=确认，非低信心 |
| F2 | RSI 背离 @ STRONG_TREND | 0.5 | **0.6** | 0.5 被 RULE 截断；仍指示减速风险 |
| F3 | FR 当前值 @ STRONG_TREND | 0.7 | **0.8** | FR 顺趋势=中性确认 |
| F4 | OI 4-象限 @ RANGING | 0.7 | **0.8** | Range 边缘建仓有意义 |
| F5 | BB Width narrowing @ SQUEEZE | 1.5 | **1.3** | 消除循环逻辑 |
| F6 | Order walls @ STRONG_TREND | 0.5 | **0.4** | Spoofing >70%，应 SKIP |

**内部一致性修正 (3 处)**：
| # | 问题 | 修正 |
|---|------|------|
| C1 | ADX rising @ RANGING = 0.5 | → **1.3** (regime 转换领先信号) |
| C2 | SMA 收敛 @ RANGING = 0.8 | → **1.1** (breakout 形成信号) |
| C3 | TREND VERDICT double-counting | → 移出表格，改为 Note 说明 + RULE 2 |

**数据对齐修正 (3 处)**：
| # | 问题 | 修正 |
|---|------|------|
| A1 | Buy Ratio 未显式列入 | → Layer 2 新增行 |
| A2 | Avg Trade Size 未显式列入 | → Layer 2 新增行 |
| A3 | "24h Vol < 50% of 7d avg" 数据不可用 | → 改为 "Volume Ratio < 0.5x" (15M 数据) |

**Regime 边界修正 (1 处)**：新增过渡区规则 (ADX 18-22, 35-45 取平均)

**信号重复计数修正 (3 处)**：
| # | 问题 | 修正 |
|---|------|------|
| R1 | TREND VERDICT + 4 个个体信号 | → RULE 2 禁止 double-count |
| R2 | Layer 4 有 14 信号 vs Layer 1 的 5 个 | → GROUP A/B/C/D 分组，4 个输入 |
| R3 | 4 个 FR 信号同时触发 | → Group A 规则：取组内最强信号 |

**LLM 可执行性修正 (3 处)**：
| # | 问题 | 修正 |
|---|------|------|
| E1 | Multiplier 乘法堆叠 | → 档位制 (HIGH/STD/LOW/SKIP + tier shift) |
| E2 | "24h Vol < 50% of 7d avg" | → "Volume Ratio < 0.5x" |
| E3 | Section D 全部改为 tier shift | → "DOWN one tier" 代替 "×0.7" |

**风险敞口修正 (2 处)**：
| # | 问题 | 修正 |
|---|------|------|
| H1 | BB Width 1.5 循环逻辑 | → 1.3 + 注释说明 |
| H2 | RANGING Layer 3 双重放大 | → Layer 3 notes 中已有 S/R bounce rate 说明 |

**加密特异性修正 (3 处)**：
| # | 缺失项 | 修正 |
|---|--------|------|
| K1 | 周末流动性 | → Section D 新增条件 |
| K2 | Spoofing 概率 | → Order walls note 量化 ">70%" |
| K3 | Spread/Slippage | → Layer 3 新增 2 行 + note |
