---
name: diagnose
description: |
  Run diagnostics for the AItrader trading system. 运行 AItrader 交易系统诊断。

  Use this skill when:
  - No trading signals are being generated (没有交易信号)
  - Need to check if AI analysis is working (检查 AI 分析是否正常)
  - Verifying technical indicator calculations (验证技术指标计算)
  - Debugging market data fetching issues (调试市场数据获取)
  - Troubleshooting why no trades are happening (排查为什么没有交易)
  - Running system health checks (运行系统健康检查)

  Keywords: diagnose, debug, signals, indicators, AI, analysis, troubleshoot, 诊断, 调试, 信号
---

# Trading System Diagnostics

## Purpose

Use this skill when:
- No trading signals are being generated
- Need to verify AI analysis is working
- Validating technical indicator calculations
- Debugging market data issues

## Diagnostic Commands

### Full Diagnostic (Default)
```bash
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate
python3 diagnose.py
```

### Quick Diagnostic (Skip AI calls)
```bash
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate
python3 diagnose.py --quick
```

### With Update and Restart
```bash
python3 diagnose.py --update --restart
```

## Expected Output

### Normal Operation Signs (方案B)
```
✅ Configuration loaded successfully
✅ Market data fetched successfully
✅ TechnicalIndicatorManager initialized
✅ Technical data retrieved
✅ Sentiment data retrieved
✅ MultiAgent 层级决策成功
   🐂 Bull Agent 分析中...
   🐻 Bear Agent 分析中...
   ⚖️ Judge Agent 判断中...
   🛡️ Risk Manager 评估中...
🎯 Judge 最终决策: BUY/SELL/HOLD
```

### Key Checkpoints

| Check | Normal Value | Abnormal Handling |
|-------|--------------|-------------------|
| RSI | 0-100 | Out of range = data error |
| MACD | Any value | NaN = insufficient data |
| Judge Signal | BUY/SELL/HOLD | ERROR = API failure |
| Winning Side | BULL/BEAR/TIE | 显示辩论胜方 |

## 信号决策流程 (方案B - 层级决策架构)

**v6.0 更新**: 采用 TradingAgents 层级决策架构，Judge 决策即最终决策

```
决策流程:
Phase 1: Bull/Bear Debate (辩论)
  └→ 🐂 Bull Agent: 寻找做多理由
  └→ 🐻 Bear Agent: 寻找做空理由

Phase 2: Judge (Portfolio Manager) Decision
  └→ ⚖️ 评估辩论结果，做出最终决策

Phase 3: Risk Evaluation
  └→ 🛡️ 确定仓位大小和止损止盈
```

**注意**: 以下配置已标记为 LEGACY，不再生效:
```yaml
skip_on_divergence: true      # [LEGACY] 方案B不使用
use_confidence_fusion: true   # [LEGACY] 方案B不使用
```

## Common Issues

### 1. No Trading Signals

**Possible Causes** (方案B):
- Judge returns HOLD (Bull/Bear辩论无明显胜者)
- Confidence below min_confidence_to_trade
- Risk Manager 认为风险过高

**Check Command**:
```bash
python3 diagnose_realtime.py 2>&1 | grep -E "(Judge|Final Signal|Confidence|Winning Side)"
```

### 2. DeepSeek API Failure

**Check**:
```bash
grep "DEEPSEEK_API_KEY" ~/.env.aitrader
```

### 3. Abnormal Technical Indicators

**Check**:
```bash
python3 diagnose.py 2>&1 | grep -E "(RSI|MACD|SMA)"
```

## Key Files

| File | Purpose |
|------|---------|
| `diagnose.py` | Main diagnostic script |
| `strategy/deepseek_strategy.py` | Main strategy logic |
| `configs/strategy_config.yaml` | Strategy configuration |
