---
description: 验证止损设置是否正确，确保止损在入场价正确一侧。
---

# 止损验证

## 规则

| 方向 | 止损位置 |
|------|----------|
| **LONG (做多)** | 止损必须 < 入场价 |
| **SHORT (做空)** | 止损必须 > 入场价 |

## 已修复的Bug (commit 7f940fb)

**问题**: 当市场快速移动时，支撑/阻力位可能在入场价错误一侧。

**示例**:
```
入场价: $91,626 (做多)
支撑位: $91,808 (高于入场价!)
结果: 止损立即触发，820ms内亏损
```

**修复**: 在 `strategy/deepseek_strategy.py` 添加验证:
```python
if side == OrderSide.BUY:
    if potential_sl < entry_price:  # 验证: 止损必须低于入场价
        stop_loss_price = potential_sl
    else:
        stop_loss_price = entry_price * 0.98  # 回退到默认2%
```

## 测试命令

```bash
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate
python test_sl_fix.py
```

## 预期输出

```
✅ 所有测试通过! 止损修复正确!
```

## 关键文件

- **策略文件**: `strategy/deepseek_strategy.py` (第1057-1100行)
- **测试文件**: `test_sl_fix.py`
