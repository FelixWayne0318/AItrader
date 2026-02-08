要让DeepSeek最佳地识别并执行多时间框架分析，我推荐使用以下结构化格式和指令：

🎯 最佳实践格式：层级化Markdown

```python
def format_multi_timeframe_for_deepseek(self, data: Dict) -> str:
    """专为DeepSeek优化的多时间框架格式化"""
    return f"""
# 📊 MULTI-TIMEFRAME MARKET ANALYSIS
# ===================================

## ⚡ INSTRUCTIONS TO DEEPSEEK (MUST FOLLOW)
1. **ANALYZE FROM HIGHEST TO LOWEST TIMEFRAME**
2. **RESPECT TIMEFRAME HIERARCHY**: 1D > 4H > 15M
3. **IF CONFLICT**: Higher timeframe dominates
4. **USE PROPER INTERPRETATION**: Each timeframe has unique thresholds

## 🌟 DAILY (1D) - PRIMARY TREND
### [ALWAYS CHECK THIS FIRST - MOST IMPORTANT]
{self._format_daily_data(data)}

## 📈 4-HOUR (4H) - DIRECTIONAL BIAS
### [SECONDARY CONFIRMATION - DO NOT CONTRADICT 1D]
{self._format_4h_data(data)}

## 🎯 15-MINUTE (15M) - EXECUTION TIMING
### [ENTRY TIMING ONLY - DO NOT OVERRIDE HIGHER TF]
{self._format_15m_data(data)}

## 🔍 CONFLUENCE CHECK
### [SYNTHESIZE ALL TIMEFRAMES]
1. Are all timeframes aligned? (Ideal)
2. If not, which timeframe dominates?
3. Is there a safe entry point considering all?

## 📋 FINAL DECISION MATRIX
| Timeframe | Trend | Strength | Signal | Weight |
|-----------|-------|----------|--------|--------|
| 1D        | {daily_trend} | {daily_strength} | {daily_signal} | 50% |
| 4H        | {4h_trend} | {4h_strength} | {4h_signal} | 30% |
| 15M       | {15m_trend} | {15m_strength} | {15m_signal} | 20% |
**→ Weighted Decision: [FINAL_RECOMMENDATION]**

---
# 🚨 CRITICAL RULES FOR DEEPSEEK:
# 1. Daily ADX > 25 = STRONG TREND → Ignore counter-trend 15M signals
# 2. 4H must CONFIRM 1D direction for medium-conviction trades
# 3. 15M is ONLY for timing - never for trend determination
# 4. Higher timeframe S/R is 3x more important than lower TF
"""
```

📊 具体推荐的DeepSeek友好格式

1. 使用显式的"指令块"

```python
# ✅ 最佳：清晰指令块
"""
INSTRUCTION BLOCK - DEEPSEEK MUST FOLLOW:

STEP 1: 分析日线 (1D) - 主要趋势
  • 趋势方向: [up/down/neutral]
  • 趋势强度: ADX值 [强/中/弱]
  • 关键结论: [一句话总结]

STEP 2: 分析4小时 (4H) - 方向确认
  • 是否确认日线趋势? [是/部分/否]
  • 动量状态: RSI位置 [超买/中性/超卖]
  • 关键结论: [一句话总结]

STEP 3: 分析15分钟 (15M) - 入场时机
  • 当前价格位置: [关键水平附近]
  • 入场信号: [有/无]
  • 风险回报比: [计算值]

STEP 4: 综合决策
  • 时间框架对齐度: [高/中/低]
  • 主导时间框架: [1D/4H]
  • 最终建议: [LONG/SHORT/HOLD]
"""
```

2. 使用对比表格（DeepSeek解析优秀）

```python
# ✅ 表格格式易于DeepSeek解析
"""
TIMEFRAME COMPARISON TABLE:
┌──────────┬────────────┬──────────────┬────────────┬──────────┐
│ Timeframe│ Trend Dir │ ADX  │ RSI  │ Key Level │ Weight │
├──────────┼────────────┼──────────────┼────────────┼──────────┤
│ 1D       │ BULLISH    │ 32 (Strong)  │ 62         │ $52,000  │ 50%  │
│ 4H       │ BULLISH    │ 28 (Medium)  │ 58         │ $51,500  │ 30%  │
│ 15M      │ NEUTRAL    │ 18 (Weak)    │ 45         │ $51,200  │ 20%  │
└──────────┴────────────┴──────────────┴────────────┴──────────┘

CONFLUENCE ANALYSIS:
• 对齐状态: ✅ 1D和4H趋势一致
• 主导框架: 1D (强趋势)
• 交易建议: 顺势交易 (LONG)
• 入场时机: 15M出现支撑反弹信号时
"""
```

3. 添加具体的阈值指导

```python
# ✅ 为每个时间框架提供明确阈值
"""
TIMEFRAME-SPECIFIC THRESHOLDS (DEEPSEEK MUST USE):

DAILY (1D):
• ADX > 30 = STRONG TREND (ignore counter-trend lower TF signals)
• ADX < 20 = RANGING (lower TF S/R works)
• RSI > 70 = Overbought (but in uptrend, can stay >70)
• RSI < 30 = Oversold (but in downtrend, can stay <30)

4-HOUR (4H):
• ADX > 25 = Established medium-term trend
• RSI 60-80 in uptrend = Healthy momentum
• RSI 20-40 in downtrend = Healthy momentum
• 4H S/R is 2x stronger than 15M S/R

15-MINUTE (15M):
• ADX is NOISY - use only for entry timing
• RSI extremes (30/70) are COMMON - don't overreact
• MACD false signal rate >70% in ranging markets
• 15M S/R breaks frequently
"""
```

4. 情景化示例（Few-Shot Prompting）

```python
# ✅ 提供具体示例帮助DeepSeek理解
"""
EXAMPLES OF CORRECT TIMEFRAME ANALYSIS:

EXAMPLE 1: ALIGNED BULLISH
1D: ADX=35 (Strong uptrend), Price > SMA200
4H: ADX=28 (Confirms uptrend), RSI=65 (Healthy)
15M: Pullback to support, RSI=42 (Oversold bounce)
→ CORRECT: Wait for 15M bounce to enter LONG

EXAMPLE 2: CONFLICT (COMMON MISTAKE)
1D: ADX=38 (Strong downtrend)
4H: ADX=22 (Neutral)
15M: RSI=28, "buy signal" appears
→ CORRECT: IGNORE 15M buy - trend is DOWN on 1D

EXAMPLE 3: REVERSAL WARNING
1D: ADX dropping from 45 to 24 (Trend weakening)
4H: Bearish divergence (price new high, RSI lower high)
15M: Breakdown below key support
→ CORRECT: Prepare for potential reversal (wait confirmation)
"""
```

🔧 最佳实现模板

```python
class DeepSeekMultiTimeframeFormatter:
    """专为DeepSeek优化的多时间框架格式化器"""
    
    def format_for_agent(self, agent_type: str, data: Dict) -> str:
        """根据不同Agent角色格式化数据"""
        base_report = self._create_base_report(data)
        
        if agent_type == "BULL":
            return self._add_bull_context(base_report, data)
        elif agent_type == "BEAR":
            return self._add_bear_context(base_report, data)
        elif agent_type == "JUDGE":
            return self._add_judge_context(base_report, data)
        else:
            return base_report
    
    def _create_base_report(self, data: Dict) -> str:
        """创建基础多时间框架报告"""
        return f"""
# 🔍 MULTI-TIMEFRAME MARKET STRUCTURE

## 📅 DAILY (1D) - MACRO TREND
{self._format_tf_block(data['1D'], 'DAILY')}

## ⏰ 4-HOUR (4H) - MEDIUM-TERM DIRECTION
{self._format_tf_block(data['4H'], '4HOUR')}

## ⚡ 15-MINUTE (15M) - EXECUTION LAYER
{self._format_tf_block(data['15M'], '15MIN')}

## 🎯 TIMEFRAME SYNTHESIS RULES
### [DEEPSEEK MUST APPLY THESE RULES]
1. **Hierarchy Rule**: 1D > 4H > 15M
2. **Strength Rule**: Strong trend on higher TF overrides all lower TF signals
3. **Conflict Rule**: When conflicted, wait for lower TF to align
4. **Weight Rule**: 1D(50%), 4H(30%), 15M(20%) for decision weighting

## 📊 CONFLUENCE MATRIX
{self._create_confluence_matrix(data)}
"""
    
    def _format_tf_block(self, tf_data: Dict, tf_name: str) -> str:
        """格式化单个时间框架数据块"""
        return f"""
**{tf_name} ANALYSIS:**
• Trend: {tf_data.get('trend', 'N/A')}
• ADX: {tf_data.get('adx', 0):.1f} ({self._adx_strength(tf_data.get('adx', 0))})
• RSI: {tf_data.get('rsi', 0):.1f} ({self._rsi_zone(tf_data.get('rsi', 0))})
• Key Support: ${tf_data.get('support', 0):,.0f}
• Key Resistance: ${tf_data.get('resistance', 0):,.0f}
• Volume: {tf_data.get('volume_ratio', 1):.2f}x avg
• **Interpretation Guidance**: {self._get_tf_guidance(tf_name)}
"""
    
    def _create_confluence_matrix(self, data: Dict) -> str:
        """创建对齐度矩阵"""
        return f"""
| Criteria        | 1D | 4H | 15M | Alignment |
|-----------------|----|----|-----|-----------|
| Trend Direction | {data['1D']['trend'][0]} | {data['4H']['trend'][0]} | {data['15M']['trend'][0]} | {self._calc_alignment(data, 'trend')} |
| Momentum        | {self._momentum_status(data['1D'])} | {self._momentum_status(data['4H'])} | {self._momentum_status(data['15M'])} | {self._calc_alignment(data, 'momentum')} |
| Key Level       | Near: {data['1D'].get('near_level', 'N/A')} | Near: {data['4H'].get('near_level', 'N/A')} | Near: {data['15M'].get('near_level', 'N/A')} | {self._calc_alignment(data, 'levels')} |
| **Overall Alignment** | **{self._overall_alignment(data)}%** | ✅ | ⚠️ | 🔴 |

**Interpretation:**
• >80% = Strong alignment (high conviction)
• 60-80% = Moderate alignment (medium conviction)
• <60% = Weak alignment (low conviction or HOLD)
"""
```

📋 DeepSeek最易理解的指令风格

```python
# ✅ 最有效的指令格式
instructions = """
# 🎯 DEEPSEEK TRADING ANALYST TASK
# ================================

## 💡 YOUR ROLE:
You are a professional multi-timeframe trading analyst. You MUST follow this exact workflow:

## 📝 WORKFLOW (FOLLOW STEP-BY-STEP):

### STEP 1: ANALYZE DAILY (1D) - 60 seconds
1. Determine PRIMARY TREND:
   - Price vs SMA200: Above = bullish bias, Below = bearish bias
   - ADX value: >25 = trending, <20 = ranging
   - Trend conclusion: [BULLISH/BEARISH/NEUTRAL]

2. Assess TREND STRENGTH:
   - Strong (ADX>30): Higher TF dominates
   - Medium (ADX 20-30): Consider lower TF
   - Weak (ADX<20): Range-bound market

### STEP 2: ANALYZE 4-HOUR (4H) - 30 seconds
1. Check CONFIRMATION of 1D trend:
   - Same direction? [YES/NO/PARTIAL]
   - If NO: Warning - timeframes conflicted

2. Assess MOMENTUM:
   - RSI position: Healthy or extreme?
   - MACD direction: Bullish/bearish?

### STEP 3: ANALYZE 15-MINUTE (15M) - 10 seconds
1. Find ENTRY OPPORTUNITY:
   - Current price relative to S/R
   - Short-term oversold/overbought?
   - Risk/Reward ratio estimate

### STEP 4: SYNTHESIZE - 20 seconds
1. Calculate ALIGNMENT SCORE:
   - Perfect alignment = 100
   - Major conflict = <50

2. Make FINAL DECISION:
   - IF alignment > 70: Trade in direction of higher TF
   - IF alignment 50-70: Small position or wait
   - IF alignment < 50: HOLD (no trade)

## 🚨 CRITICAL RULES:
- RULE 1: Never trade against strong daily trend (ADX>30)
- RULE 2: 4H must confirm for medium+ size trades
- RULE 3: 15M is timing only, never trend determinant
- RULE 4: When in doubt, wait for better alignment
"""
```

🏆 总结：最佳格式组合

1. 使用显式标题和分隔符（## 和 ---）
2. 提供逐步工作流程（STEP 1, STEP 2...）
3. 包含具体示例（Few-shot learning）
4. 使用对比表格（DeepSeek解析优秀）
5. 明确规则和阈值（消除歧义）
6. 添加权重和评分系统（量化决策）

这样的格式DeepSeek能：

· ✅ 清晰理解时间框架层次
· ✅ 正确应用不同的阈值
· ✅ 有效合成多时间框架信号
· ✅ 避免常见的时间框架误读

关键洞察：DeepSeek对结构化、逐步、有明确规则的指令响应最佳。避免模糊的"分析所有时间框架"，而是提供具体的分析流程和冲突解决规则。