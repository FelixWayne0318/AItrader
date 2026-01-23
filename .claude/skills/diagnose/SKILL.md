---
name: diagnose
description: 运行实盘信号诊断，检查 AI 信号生成、技术指标、市场数据是否正常。Use for diagnosing trading signals, checking AI analysis, or debugging why no trades are happening.
argument-hint: "[quick|full|signals]"
allowed-tools: Bash(python3:*), Read, Grep
context: fork
agent: general-purpose
---

# 实盘信号诊断

## 用途

当出现以下情况时使用此技能：
- 没有交易信号产生
- 需要检查 AI 分析是否正常
- 验证技术指标计算
- 调试市场数据获取

## 诊断命令

### 完整诊断 (默认)
```bash
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate
python3 diagnose_realtime.py
```

### 快速诊断 (跳过 AI 调用)
```bash
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate
python3 diagnose.py --quick
```

## 诊断输出解读

### 正常运行标志

```
✅ 配置加载成功
✅ 市场数据获取成功
✅ TechnicalIndicatorManager 初始化成功
✅ 技术数据获取成功
✅ 情绪数据获取成功
✅ DeepSeek 分析成功
✅ MultiAgent 辩论成功
```

### 关键检查点

| 检查项 | 正常值 | 异常处理 |
|--------|--------|----------|
| RSI | 0-100 | 超出范围表示数据错误 |
| MACD | 任意值 | NaN 表示数据不足 |
| DeepSeek Signal | BUY/SELL/HOLD | ERROR 表示 API 失败 |
| MultiAgent Signal | BUY/SELL/HOLD | 与 DeepSeek 对比 |

### 信号分歧处理

```
use_confidence_fusion: True   # 加权信心融合 (推荐)
skip_on_divergence: True      # 分歧时跳过 (后备)
```

**分歧场景**:
- BUY vs SELL → 使用高信心信号 (融合模式)
- BUY vs HOLD → 使用 DeepSeek 信号
- SELL vs HOLD → 使用 DeepSeek 信号

## 常见问题诊断

### 1. 没有交易信号

**可能原因**:
- AI 返回 HOLD (市场不明朗)
- 信心不足 (低于 min_confidence_to_trade)
- BUY vs SELL 分歧且信心相等

**检查命令**:
```bash
# 实时过滤诊断输出
python3 diagnose_realtime.py 2>&1 | grep -E "(Final Signal|Confidence|Divergence)"
```

### 2. DeepSeek API 失败

**可能原因**:
- API Key 无效
- 网络问题
- 配额用尽

**检查**:
```bash
grep "DEEPSEEK_API_KEY" ~/.env.aitrader
```

### 3. 技术指标异常

**可能原因**:
- K线数据不足
- 网络获取失败

**检查**:
```bash
# 实时过滤诊断输出
python3 diagnose_realtime.py 2>&1 | grep -E "(RSI|MACD|SMA)"
```

## 关键文件

| 文件 | 用途 |
|------|------|
| `diagnose_realtime.py` | 完整诊断脚本 |
| `diagnose.py` | 快速诊断脚本 |
| `strategy/deepseek_strategy.py` | 主策略逻辑 |
| `configs/strategy_config.yaml` | 策略配置 |

## 与实盘代码路径一致

诊断脚本调用与 `main_live.py` 完全相同的代码路径：
- 相同的配置加载逻辑
- 相同的技术指标计算
- 相同的 AI 分析调用
- 相同的分歧处理逻辑

诊断结果 = 实盘行为
