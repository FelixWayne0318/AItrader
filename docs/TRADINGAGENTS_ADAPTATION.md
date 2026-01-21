# TradingAgents 源码借鉴方案

## 概述

经过对 TradingAgents (UCLA+MIT) 源码的深入分析，以下是可以直接借鉴并适配到当前 AItrader 系统的组件。

## 架构对比

### TradingAgents 原始架构 (7 角色)
```
START
  ↓
┌─────────────────────────────────────────┐
│  4 个分析师 (并行运行)                    │
│  ├── Market Analyst (技术分析)           │
│  ├── Social Media Analyst (社交情绪)     │
│  ├── News Analyst (新闻分析)             │
│  └── Fundamentals Analyst (基本面)       │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│  Bull/Bear 辩论 (2-3 轮)                 │
│  ├── Bull Researcher (做多观点)          │
│  └── Bear Researcher (做空观点)          │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│  Research Manager (裁判，决定 BUY/SELL/HOLD) │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│  Trader (制定交易计划)                    │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│  风险辩论 (3 方)                          │
│  ├── Risky Analyst (激进派)              │
│  ├── Safe Analyst (保守派)               │
│  └── Neutral Analyst (中立派)            │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│  Risk Manager (最终决策 + 仓位调整)        │
└─────────────────────────────────────────┘
  ↓
END
```

### 适配后的 AItrader 架构 (简化版)
```
START
  ↓
┌─────────────────────────────────────────┐
│  2 个分析师 (并行)                        │
│  ├── Technical Analyst (技术分析)        │
│  └── Sentiment Analyst (情绪分析)        │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│  Bull/Bear 辩论 (2 轮)                   │
│  ├── Bull Researcher (做多论点)          │
│  └── Bear Researcher (做空论点)          │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│  Research Manager (裁判决策)              │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│  Risk Evaluator (风险评估 + 最终信号)      │
└─────────────────────────────────────────┘
  ↓
NautilusTrader 执行
```

## 可直接借鉴的代码

### 1. Bull Researcher Prompt (做多分析师)

**源文件**: `/home/user/TradingAgents_ref/tradingagents/agents/researchers/bull_researcher.py`

**原始 Prompt** (已针对加密货币适配):
```python
BULL_PROMPT = """You are a Bull Analyst advocating for LONG position on {symbol}.
Your task is to build a strong, evidence-based case emphasizing growth potential,
bullish momentum, and positive market indicators.

Key points to focus on:
- Growth Potential: Highlight upward momentum, breakout patterns, and bullish formations
- Technical Strengths: Emphasize bullish MA alignment, RSI recovering from oversold, MACD crossovers
- Positive Indicators: Use volume surge, support holding, and sentiment data as evidence
- Bear Counterpoints: Critically analyze the bear argument with specific data, showing why long is better

Resources available:
Technical Analysis Report: {technical_report}
Market Sentiment Report: {sentiment_report}
Debate History: {history}
Last Bear Argument: {bear_argument}
Past Reflections (lessons learned): {past_memories}

Deliver a compelling bull argument that refutes the bear's concerns and demonstrates
why going LONG is the optimal decision at this moment."""
```

### 2. Bear Researcher Prompt (做空分析师)

**源文件**: `/home/user/TradingAgents_ref/tradingagents/agents/researchers/bear_researcher.py`

**原始 Prompt** (已针对加密货币适配):
```python
BEAR_PROMPT = """You are a Bear Analyst making the case for SHORT position on {symbol}.
Your goal is to present a well-reasoned argument emphasizing risks, bearish signals,
and potential downside.

Key points to focus on:
- Risks and Challenges: Highlight resistance levels, bearish divergence, overbought conditions
- Technical Weaknesses: Emphasize bearish MA alignment, RSI overbought, MACD bearish crossover
- Negative Indicators: Use volume decline, support breaking, and negative sentiment as evidence
- Bull Counterpoints: Critically analyze the bull argument, exposing over-optimistic assumptions

Resources available:
Technical Analysis Report: {technical_report}
Market Sentiment Report: {sentiment_report}
Debate History: {history}
Last Bull Argument: {bull_argument}
Past Reflections (lessons learned): {past_memories}

Deliver a compelling bear argument that refutes the bull's claims and demonstrates
why going SHORT (or staying flat) is the safer decision."""
```

### 3. Research Manager/Judge Prompt (裁判)

**源文件**: `/home/user/TradingAgents_ref/tradingagents/agents/managers/research_manager.py`

```python
JUDGE_PROMPT = """As the portfolio manager and debate facilitator, your role is to
critically evaluate this debate and make a DEFINITIVE decision.

CRITICAL RULES:
1. You MUST choose a side - Bull (LONG) or Bear (SHORT/FLAT)
2. HOLD is only valid when BOTH sides have equally compelling arguments
3. Do NOT default to HOLD just because both have valid points
4. Commit to a stance grounded in the debate's STRONGEST arguments

Your recommendation must include:
1. Your Decision: LONG, SHORT, or HOLD (with clear justification)
2. Rationale: Why the winning side's arguments are more compelling
3. Key Evidence: The 2-3 most convincing points that led to your decision
4. Risk Acknowledgment: What could go wrong with this decision

Past Mistakes to Avoid:
{past_memories}

Debate Transcript:
{debate_history}

Make your decision now. Be decisive, not neutral."""
```

### 4. Risk Evaluator Prompt (风险评估)

**源文件**: `/home/user/TradingAgents_ref/tradingagents/agents/risk_mgmt/conservative_debator.py`

```python
RISK_PROMPT = """As the Risk Evaluator, assess the proposed trade:

Proposed Action: {proposed_action}
Current Position: {current_position}
Technical Report: {technical_report}
Sentiment Report: {sentiment_report}

Evaluate:
1. Risk Level: LOW / MEDIUM / HIGH
2. Position Size Recommendation:
   - HIGH confidence + LOW risk → Full size (100%)
   - MEDIUM confidence or MEDIUM risk → Half size (50%)
   - LOW confidence or HIGH risk → Quarter size (25%) or SKIP
3. Stop Loss Placement: Based on support/resistance
4. Take Profit Target: Based on risk/reward ratio

Return your final recommendation in JSON:
{{
    "action": "LONG|SHORT|HOLD",
    "confidence": "HIGH|MEDIUM|LOW",
    "risk_level": "LOW|MEDIUM|HIGH",
    "position_size_pct": 25|50|100,
    "stop_loss": <price>,
    "take_profit": <price>,
    "reason": "..."
}}"""
```

## 实现代码

### 新增文件: `agents/multi_agent_analyzer.py`

```python
"""
Multi-Agent Trading Analyzer
Borrowed from TradingAgents (UCLA+MIT) and adapted for crypto trading.
"""

import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from openai import OpenAI


class MultiAgentAnalyzer:
    """
    Multi-agent trading analysis system with Bull/Bear debate mechanism.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        temperature: float = 0.3,
        base_url: str = "https://api.deepseek.com",
        debate_rounds: int = 2,
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.temperature = temperature
        self.debate_rounds = debate_rounds

        # Memory for learning from past decisions
        self.decision_memory: List[Dict] = []

    def analyze(
        self,
        symbol: str,
        technical_report: Dict[str, Any],
        sentiment_report: Optional[Dict[str, Any]] = None,
        current_position: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run multi-agent analysis with Bull/Bear debate.

        Returns:
            Dict with final trading decision
        """
        # Phase 1: Generate analysis reports
        tech_summary = self._format_technical_report(technical_report)
        sent_summary = self._format_sentiment_report(sentiment_report)

        # Phase 2: Bull/Bear Debate
        debate_history = ""
        bull_argument = ""
        bear_argument = ""

        for round_num in range(self.debate_rounds):
            # Bull's turn
            bull_argument = self._get_bull_argument(
                symbol=symbol,
                technical_report=tech_summary,
                sentiment_report=sent_summary,
                history=debate_history,
                bear_argument=bear_argument,
            )
            debate_history += f"\n\n[Round {round_num + 1}] BULL: {bull_argument}"

            # Bear's turn
            bear_argument = self._get_bear_argument(
                symbol=symbol,
                technical_report=tech_summary,
                sentiment_report=sent_summary,
                history=debate_history,
                bull_argument=bull_argument,
            )
            debate_history += f"\n\n[Round {round_num + 1}] BEAR: {bear_argument}"

        # Phase 3: Judge decides
        judge_decision = self._get_judge_decision(
            debate_history=debate_history,
            past_memories=self._get_past_memories(),
        )

        # Phase 4: Risk evaluation
        final_decision = self._evaluate_risk(
            proposed_action=judge_decision,
            technical_report=tech_summary,
            sentiment_report=sent_summary,
            current_position=current_position,
        )

        return final_decision

    def _get_bull_argument(
        self,
        symbol: str,
        technical_report: str,
        sentiment_report: str,
        history: str,
        bear_argument: str,
    ) -> str:
        """Generate bull analyst's argument."""

        prompt = f"""You are a Bull Analyst advocating for LONG position on {symbol}.
Build a strong, evidence-based case for going LONG.

Focus on:
- Bullish technical signals (MA alignment, RSI oversold recovery, MACD crossover)
- Positive momentum and breakout patterns
- Counter the bear's arguments with specific data

Technical Analysis: {technical_report}
Sentiment Data: {sentiment_report}
Debate History: {history}
Last Bear Argument: {bear_argument if bear_argument else "None yet"}

Deliver a compelling 2-3 paragraph argument for LONG. Be specific with numbers."""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
        )
        return response.choices[0].message.content

    def _get_bear_argument(
        self,
        symbol: str,
        technical_report: str,
        sentiment_report: str,
        history: str,
        bull_argument: str,
    ) -> str:
        """Generate bear analyst's argument."""

        prompt = f"""You are a Bear Analyst making the case AGAINST going LONG on {symbol}.
Present a well-reasoned argument for staying SHORT or FLAT.

Focus on:
- Bearish technical signals (resistance, overbought RSI, bearish divergence)
- Downside risks and potential support breaks
- Counter the bull's optimistic assumptions

Technical Analysis: {technical_report}
Sentiment Data: {sentiment_report}
Debate History: {history}
Last Bull Argument: {bull_argument}

Deliver a compelling 2-3 paragraph argument against LONG. Be specific with numbers."""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
        )
        return response.choices[0].message.content

    def _get_judge_decision(
        self,
        debate_history: str,
        past_memories: str,
    ) -> Dict[str, Any]:
        """Judge evaluates the debate and makes decision."""

        prompt = f"""You are the Portfolio Manager judging this Bull vs Bear debate.

CRITICAL RULES:
1. You MUST choose a side - LONG, SHORT, or HOLD
2. HOLD is ONLY valid when arguments are equally compelling
3. Do NOT default to HOLD - make a decisive choice
4. Base decision on the STRONGEST arguments presented

Past Mistakes to Avoid:
{past_memories if past_memories else "No past data"}

Full Debate:
{debate_history}

Provide your decision in JSON format:
{{
    "decision": "LONG|SHORT|HOLD",
    "winning_side": "BULL|BEAR|TIE",
    "confidence": "HIGH|MEDIUM|LOW",
    "key_reasons": ["reason1", "reason2"],
    "acknowledged_risks": ["risk1", "risk2"]
}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # Lower temp for decision
        )

        result = response.choices[0].message.content
        try:
            # Extract JSON
            start = result.find('{')
            end = result.rfind('}') + 1
            if start != -1 and end > start:
                return json.loads(result[start:end])
        except:
            pass

        return {"decision": "HOLD", "confidence": "LOW", "key_reasons": ["Parse error"]}

    def _evaluate_risk(
        self,
        proposed_action: Dict[str, Any],
        technical_report: str,
        sentiment_report: str,
        current_position: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Final risk evaluation and position sizing."""

        action = proposed_action.get("decision", "HOLD")
        confidence = proposed_action.get("confidence", "LOW")

        prompt = f"""As Risk Manager, evaluate this proposed trade:

Proposed: {action} with {confidence} confidence
Reasons: {proposed_action.get('key_reasons', [])}
Risks: {proposed_action.get('acknowledged_risks', [])}

Technical Data: {technical_report}
Sentiment: {sentiment_report}
Current Position: {current_position if current_position else "None"}

Provide final recommendation in JSON:
{{
    "signal": "BUY|SELL|HOLD",
    "confidence": "HIGH|MEDIUM|LOW",
    "risk_level": "LOW|MEDIUM|HIGH",
    "position_size_pct": 25|50|100,
    "stop_loss_pct": 0.01-0.03,
    "take_profit_pct": 0.02-0.05,
    "reason": "Final decision rationale",
    "debate_summary": "Brief summary of bull/bear debate"
}}

Map: LONG→BUY, SHORT→SELL, HOLD→HOLD"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )

        result = response.choices[0].message.content
        try:
            start = result.find('{')
            end = result.rfind('}') + 1
            if start != -1 and end > start:
                decision = json.loads(result[start:end])
                decision["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                decision["debate_rounds"] = self.debate_rounds
                return decision
        except:
            pass

        return {
            "signal": "HOLD",
            "confidence": "LOW",
            "reason": "Risk evaluation parse error",
            "is_fallback": True,
        }

    def _format_technical_report(self, data: Dict[str, Any]) -> str:
        """Format technical data for prompts."""
        return f"""
Price: ${data.get('price', 0):,.2f}
Trend: {data.get('overall_trend', 'N/A')}
RSI: {data.get('rsi', 0):.1f}
MACD: {data.get('macd', 0):.4f} (Signal: {data.get('macd_signal', 0):.4f})
Support: ${data.get('support', 0):,.2f}
Resistance: ${data.get('resistance', 0):,.2f}
Volume Ratio: {data.get('volume_ratio', 1):.2f}x
"""

    def _format_sentiment_report(self, data: Optional[Dict[str, Any]]) -> str:
        """Format sentiment data for prompts."""
        if not data:
            return "Sentiment data unavailable"
        return f"""
Bullish Ratio: {data.get('positive_ratio', 0):.1%}
Bearish Ratio: {data.get('negative_ratio', 0):.1%}
Net Sentiment: {data.get('net_sentiment', 0):+.3f}
"""

    def _get_past_memories(self) -> str:
        """Get past decision memories for learning."""
        if not self.decision_memory:
            return ""

        memories = []
        for mem in self.decision_memory[-5:]:  # Last 5 decisions
            outcome = "Profit" if mem.get('pnl', 0) > 0 else "Loss"
            memories.append(
                f"- {mem.get('decision')}: {outcome} ({mem.get('pnl', 0):+.2f}%) - Lesson: {mem.get('lesson', 'N/A')}"
            )
        return "\n".join(memories)

    def record_outcome(self, decision: str, pnl: float, lesson: str):
        """Record trade outcome for learning."""
        self.decision_memory.append({
            "decision": decision,
            "pnl": pnl,
            "lesson": lesson,
            "timestamp": datetime.now().isoformat(),
        })
        # Keep only last 20 memories
        if len(self.decision_memory) > 20:
            self.decision_memory.pop(0)
```

## 集成到现有策略

### 修改 `strategy/deepseek_strategy.py`

在 `DeepSeekAIStrategy.__init__` 中添加:

```python
from agents.multi_agent_analyzer import MultiAgentAnalyzer

# In __init__:
self.multi_agent_analyzer = MultiAgentAnalyzer(
    api_key=config.deepseek_api_key,
    model=config.deepseek_model,
    temperature=0.3,
    debate_rounds=2,
)
```

在信号生成时使用:

```python
def _get_ai_signal(self, price_data, technical_data, sentiment_data, position):
    # Use multi-agent analysis
    signal = self.multi_agent_analyzer.analyze(
        symbol="BTCUSDT",
        technical_report=technical_data,
        sentiment_report=sentiment_data,
        current_position=position,
    )
    return signal
```

## API 成本估算

| 组件 | 调用次数/信号 | Token 数 (约) | 成本 (DeepSeek) |
|------|--------------|---------------|-----------------|
| Bull Analyst | 2 | ~800 | ~$0.0008 |
| Bear Analyst | 2 | ~800 | ~$0.0008 |
| Judge | 1 | ~1000 | ~$0.001 |
| Risk Evaluator | 1 | ~600 | ~$0.0006 |
| **总计/信号** | 6 | ~4000 | **~$0.004** |

15分钟一次信号 → 每天 96 次 → 每天约 $0.38 → 每月约 $11.5

## 优势对比

| 特性 | 原单一 Agent | 多 Agent 辩论 |
|------|-------------|--------------|
| 决策过程 | 黑盒，单一视角 | 透明，多角度辩论 |
| 抗偏差 | 容易陷入单一判断 | Bull/Bear 相互制衡 |
| 可解释性 | 仅一段理由 | 完整辩论记录 |
| 学习能力 | 无历史学习 | 记忆过去错误 |
| 风险控制 | 固定规则 | 动态风险评估 |

## 下一步

1. 创建 `agents/` 目录
2. 实现 `MultiAgentAnalyzer` 类
3. 集成到现有策略
4. 本地测试辩论输出
5. 部署到服务器

---
*基于 TradingAgents (UCLA+MIT) 开源项目适配*
*参考仓库: https://github.com/TaurusQ/tradingagents*
