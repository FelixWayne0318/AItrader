---
name: stop-loss-check
description: 验证止损设置是否正确，确保止损在入场价正确一侧。Use when validating stop loss, checking SL placement, or before live trading to ensure SL is on correct side of entry price.
allowed-tools: Read, Grep, Bash(python3:*)
---

# 止损验证

## 核心规则

| 方向 | 止损位置 | 验证条件 |
|------|----------|----------|
| **LONG (做多)** | 止损必须 < 入场价 | `stop_loss_price < entry_price - PRICE_EPSILON` |
| **SHORT (做空)** | 止损必须 > 入场价 | `stop_loss_price > entry_price + PRICE_EPSILON` |

> 注意：使用 `PRICE_EPSILON = entry_price * 1e-8` 进行浮点数比较，避免精度问题。

## 已修复的Bug

**Commit**: `7f940fb`
**问题**: 当市场快速移动时，支撑/阻力位可能在入场价错误一侧，导致止损立即触发。

**示例**:
```
入场价: $91,626 (做多)
支撑位: $91,808 (高于入场价!)
原逻辑: 止损 = $91,808 × 0.999 = $91,808.10
结果: 止损立即触发，820ms内亏损 -$0.18
```

**修复后**:
```python
# strategy/deepseek_strategy.py 第1502-1543行
PRICE_EPSILON = max(entry_price * 1e-8, 1e-8)  # 相对容差

if side == OrderSide.BUY:
    default_sl = entry_price * 0.98  # 默认2%止损
    if self.sl_use_support_resistance and support > 0:
        potential_sl = support * (1 - self.sl_buffer_pct)
        # 验证: 止损必须低于入场价 (带epsilon容差)
        if potential_sl < entry_price - PRICE_EPSILON:
            stop_loss_price = potential_sl
        else:
            stop_loss_price = default_sl  # 回退到默认2%
            self.log.warning(f"⚠️ Support above entry, using default SL")
```

## 测试命令

在服务器上运行测试：

```bash
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate
python test_sl_fix.py
```

## 预期输出

```
============================================================
  止损修复验证测试
============================================================
测试 1: Bug场景: 支撑位高于入场价 ✅ 通过
测试 2: 正常场景: 支撑位低于入场价 ✅ 通过
...
🎉 所有测试通过! 止损修复正确!
```

## 关键文件

| 文件 | 用途 | 关键行号 |
|------|------|----------|
| `strategy/deepseek_strategy.py` | 主策略 | 1502-1602 |
| `test_sl_fix.py` | 测试脚本 | - |

## 验证步骤

1. 读取 `strategy/deepseek_strategy.py` 第1502-1602行
2. 确认存在止损验证逻辑 (含 `PRICE_EPSILON` 容差)
3. 运行 `python test_sl_fix.py` 测试
4. 所有测试通过 = 修复正确
