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

### Normal Operation Signs
```
✅ Configuration loaded successfully
✅ Market data fetched successfully
✅ TechnicalIndicatorManager initialized
✅ Technical data retrieved
✅ Sentiment data retrieved
✅ DeepSeek analysis successful
✅ MultiAgent debate successful
```

### Key Checkpoints

| Check | Normal Value | Abnormal Handling |
|-------|--------------|-------------------|
| RSI | 0-100 | Out of range = data error |
| MACD | Any value | NaN = insufficient data |
| DeepSeek Signal | BUY/SELL/HOLD | ERROR = API failure |
| MultiAgent Signal | BUY/SELL/HOLD | Compare with DeepSeek |

## Signal Divergence Handling

```yaml
use_confidence_fusion: true   # Weighted confidence fusion (recommended)
skip_on_divergence: true      # Skip on divergence (fallback)
```

**Divergence Scenarios**:
- BUY vs SELL → Use higher confidence signal (fusion mode)
- BUY vs HOLD → Use DeepSeek signal
- SELL vs HOLD → Use DeepSeek signal

## Common Issues

### 1. No Trading Signals

**Possible Causes**:
- AI returns HOLD (unclear market)
- Confidence below min_confidence_to_trade
- BUY vs SELL divergence with equal confidence

**Check Command**:
```bash
python3 diagnose.py 2>&1 | grep -E "(Final Signal|Confidence|Divergence)"
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
