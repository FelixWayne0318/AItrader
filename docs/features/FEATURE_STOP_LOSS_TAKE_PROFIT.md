# 自动止损止盈功能 (Auto Stop Loss & Take Profit)

## 📋 功能概述

本功能为 DeepSeek AI 交易策略添加了**自动止损止盈**机制，使用 NautilusTrader 框架原生订单类型实现：

- ✅ **止损单 (Stop Loss)**: 使用 STOP_MARKET 订单
- ✅ **止盈单 (Take Profit)**: 使用 LIMIT 订单
- ✅ **自动触发**: 仓位开启后立即提交
- ✅ **智能计算**: 基于支撑阻力位和信心级别

---

## 🎯 止损止盈规则

### 止损位置 (Stop Loss)

#### BUY 信号 (做多)
```
止损价格 = 最近支撑位 - 0.1% 缓冲
```
- 使用技术指标计算的支撑位
- 在支撑位下方 0.1% 设置止损
- 如果支撑位无效，默认入场价 -2%

#### SELL 信号 (做空)
```
止损价格 = 最近阻力位 + 0.1% 缓冲
```
- 使用技术指标计算的阻力位
- 在阻力位上方 0.1% 设置止损
- 如果阻力位无效，默认入场价 +2%

### 止盈目标 (Take Profit)

根据 AI 信心级别动态调整：

| 信心级别 | 止盈百分比 | 说明 |
|---------|-----------|------|
| **HIGH** | **±3%** | 高信心交易，目标更激进 |
| **MEDIUM** | **±2%** | 中等信心，稳健目标 |
| **LOW** | **±1%** | 低信心交易，保守目标 |

---

## ⚙️ 配置参数

### 配置文件位置
`configs/strategy_config.yaml`

### 新增配置项

```yaml
risk:
  # Stop Loss & Take Profit (自动止损止盈)
  enable_auto_sl_tp: true              # 启用自动止损止盈
  sl_use_support_resistance: true      # 使用支撑阻力位作为止损
  sl_buffer_pct: 0.001                 # 止损缓冲 (0.1%)
  tp_high_confidence_pct: 0.03         # 高信心止盈: 3%
  tp_medium_confidence_pct: 0.02       # 中等信心止盈: 2%
  tp_low_confidence_pct: 0.01          # 低信心止盈: 1%
```

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|-------|------|
| `enable_auto_sl_tp` | bool | true | 是否启用自动止损止盈 |
| `sl_use_support_resistance` | bool | true | 是否使用支撑阻力位计算止损 |
| `sl_buffer_pct` | float | 0.001 | 止损缓冲百分比 (0.1%) |
| `tp_high_confidence_pct` | float | 0.03 | 高信心止盈百分比 (3%) |
| `tp_medium_confidence_pct` | float | 0.02 | 中等信心止盈百分比 (2%) |
| `tp_low_confidence_pct` | float | 0.01 | 低信心止盈百分比 (1%) |

---

## 🔧 实现细节

### 代码结构

#### 1. 配置类更新 (`DeepSeekAIStrategyConfig`)
```python
# Stop Loss & Take Profit
enable_auto_sl_tp: bool = True
sl_use_support_resistance: bool = True
sl_buffer_pct: float = 0.001
tp_high_confidence_pct: float = 0.03
tp_medium_confidence_pct: float = 0.02
tp_low_confidence_pct: float = 0.01
```

#### 2. 核心方法 (`_submit_sl_tp_orders`)
```python
def _submit_sl_tp_orders(
    self,
    entry_side: OrderSide,
    entry_price: float,
    quantity: float,
):
    """
    Submit Stop Loss and Take Profit orders after position is opened.
    """
    # 计算止损价格
    # 计算止盈价格
    # 提交止损单 (STOP_MARKET)
    # 提交止盈单 (LIMIT)
```

#### 3. 触发时机 (`on_position_opened`)
```python
def on_position_opened(self, event):
    """Handle position opened events."""
    # 仓位开启后立即提交止损止盈单
    self._submit_sl_tp_orders(
        entry_side=entry_side,
        entry_price=float(event.avg_px_open),
        quantity=float(event.quantity),
    )
```

### 订单类型

#### 止损单 (Stop Loss Order)
```python
sl_order = self.order_factory.stop_market(
    instrument_id=self.instrument_id,
    order_side=exit_side,              # 平仓方向
    quantity=self.instrument.make_qty(quantity),
    trigger_price=self.instrument.make_price(stop_loss_price),
    trigger_type=TriggerType.LAST_TRADE,
    reduce_only=True,                  # 仅平仓
)
```

#### 止盈单 (Take Profit Order)
```python
tp_order = self.order_factory.limit(
    instrument_id=self.instrument_id,
    order_side=exit_side,              # 平仓方向
    quantity=self.instrument.make_qty(quantity),
    price=self.instrument.make_price(take_profit_price),
    time_in_force=TimeInForce.GTC,
    reduce_only=True,                  # 仅平仓
)
```

---

## 📊 示例场景

### 场景 1: HIGH 信心 BUY 信号

```
AI 信号:
- Signal: BUY
- Confidence: HIGH
- Entry Price: $70,000

技术指标:
- Support: $69,500
- Resistance: $71,200

计算结果:
✅ Entry Price: $70,000
🛡️ Stop Loss: $69,430.50  (Support $69,500 - 0.1% = $69,430.50)
   风险: -0.81%
🎯 Take Profit: $72,100  (Entry $70,000 + 3% = $72,100)
   收益: +3.00%

Risk/Reward Ratio: 3.7:1
```

### 场景 2: MEDIUM 信心 SELL 信号

```
AI 信号:
- Signal: SELL
- Confidence: MEDIUM
- Entry Price: $70,000

技术指标:
- Support: $68,800
- Resistance: $70,500

计算结果:
✅ Entry Price: $70,000
🛡️ Stop Loss: $70,570.50  (Resistance $70,500 + 0.1% = $70,570.50)
   风险: +0.81%
🎯 Take Profit: $68,600  (Entry $70,000 - 2% = $68,600)
   收益: -2.00%

Risk/Reward Ratio: 2.5:1
```

---

## 🧪 测试建议

### 1. 禁用功能测试
```yaml
risk:
  enable_auto_sl_tp: false  # 禁用
```
验证：仓位开启后不应该有止损止盈单提交

### 2. 启用功能测试
```yaml
risk:
  enable_auto_sl_tp: true   # 启用
```
验证：
- ✅ 仓位开启后自动提交 2 个订单（1 止损 + 1 止盈）
- ✅ 止损单为 STOP_MARKET 类型
- ✅ 止盈单为 LIMIT 类型
- ✅ 两个订单都设置 reduce_only=True

### 3. 支撑阻力位测试
```yaml
risk:
  sl_use_support_resistance: true   # 使用支撑阻力位
```
验证：
- ✅ BUY: 止损价格应在支撑位下方
- ✅ SELL: 止损价格应在阻力位上方

### 4. 固定百分比测试
```yaml
risk:
  sl_use_support_resistance: false  # 不使用支撑阻力位
```
验证：
- ✅ BUY: 止损价格 = 入场价 * 0.98 (-2%)
- ✅ SELL: 止损价格 = 入场价 * 1.02 (+2%)

### 5. 信心级别测试

测试不同信心级别的止盈目标：

**HIGH 信心**
```
Expected TP: Entry ± 3%
```

**MEDIUM 信心**
```
Expected TP: Entry ± 2%
```

**LOW 信心**
```
Expected TP: Entry ± 1%
```

---

## 📝 日志输出示例

### 开仓时
```
🟢 Position opened: LONG 0.001 @ $70000.00

🎯 Calculated SL/TP for BUY position:
   Entry: $70,000.00
   Stop Loss: $69,430.50 (-0.81%)
   Take Profit: $72,100.00 (+3.00%)
   Confidence: HIGH (TP: 3.0%)

📍 Using support level for SL: $69,500.00 → $69,430.50
🛡️ Submitted Stop Loss order @ $69,430.50
🎯 Submitted Take Profit order @ $72,100.00
```

### 止损触发
```
✅ Order filled: SELL 0.001 @ $69,430.50
🔴 Position closed: LONG
   P&L: -569.50 USDT
```

### 止盈触发
```
✅ Order filled: SELL 0.001 @ $72,100.00
🔴 Position closed: LONG
   P&L: +2,100.00 USDT
```

---

## ⚠️ 注意事项

### 1. 订单互斥
- 止损单和止盈单会同时提交
- 当其中一个成交时，需要手动取消另一个
- **未来改进**: 实现 OCO (One-Cancels-the-Other) 逻辑

### 2. 仓位调整
- 如果仓位数量调整，需要同步更新止损止盈单
- **当前版本**: 不支持自动调整

### 3. 支撑阻力位计算
- 基于最近 20 根 K 线的高低点
- 如果数据不足，回退到固定百分比

### 4. 滑点影响
- 止损单使用 STOP_MARKET，可能有滑点
- 止盈单使用 LIMIT，不会有滑点但可能不成交

---

## 🚀 使用步骤

### 1. 确认配置
```bash
cat configs/strategy_config.yaml | grep -A 6 "Stop Loss"
```

### 2. 启动策略
```bash
bash restart_trader.sh
```

### 3. 监控日志
```bash
tail -f logs/trader.log | grep -E "🛡️|🎯|Stop Loss|Take Profit"
```

### 4. 验证订单
登录 Binance 查看当前持仓和挂单：
- 应该看到仓位
- 应该看到 1 个 STOP_MARKET 订单（止损）
- 应该看到 1 个 LIMIT 订单（止盈）

---

## 📈 风险回报比优化

### 推荐配置

**激进策略**
```yaml
tp_high_confidence_pct: 0.05      # 5%
tp_medium_confidence_pct: 0.03    # 3%
tp_low_confidence_pct: 0.02       # 2%
sl_buffer_pct: 0.0005             # 0.05% (更紧止损)
```

**保守策略**
```yaml
tp_high_confidence_pct: 0.02      # 2%
tp_medium_confidence_pct: 0.015   # 1.5%
tp_low_confidence_pct: 0.01       # 1%
sl_buffer_pct: 0.002              # 0.2% (更宽止损)
```

**平衡策略** (当前默认)
```yaml
tp_high_confidence_pct: 0.03      # 3%
tp_medium_confidence_pct: 0.02    # 2%
tp_low_confidence_pct: 0.01       # 1%
sl_buffer_pct: 0.001              # 0.1%
```

---

## 🔄 Git 分支信息

**当前分支**: `feature/stop-PnL`

**提交信息建议**:
```bash
git add .
git commit -m "feat: Add automatic stop loss and take profit functionality

Features:
- Auto SL/TP using NautilusTrader native orders
- Stop Loss based on support/resistance levels
- Take Profit based on AI confidence levels
- Configurable thresholds and buffers

Technical Details:
- STOP_MARKET orders for stop loss
- LIMIT orders for take profit
- Triggers on position_opened event
- Support/resistance from technical indicators

Configuration:
- enable_auto_sl_tp: true/false
- sl_use_support_resistance: true/false
- tp_high/medium/low_confidence_pct

Risk Management:
- BUY: SL below support, TP at +1/2/3%
- SELL: SL above resistance, TP at -1/2/3%
- Buffer: 0.1% beyond S/R levels"
```

---

## 📚 相关文档

- [STRATEGY.md](STRATEGY.md) - 策略整体说明
- [GIT_WORKFLOW.md](GIT_WORKFLOW.md) - Git 工作流程
- [ARCHITECTURE_ANALYSIS.md](ARCHITECTURE_ANALYSIS.md) - 架构分析

---

## ✅ 完成清单

- [x] 配置文件添加参数
- [x] 策略类添加配置
- [x] 实现 `_submit_sl_tp_orders()` 方法
- [x] 修改 `on_position_opened()` 触发
- [x] 添加 TriggerType 导入
- [x] 创建功能文档
- [ ] 实盘测试验证
- [ ] 性能监控和优化
- [ ] OCO 订单逻辑（未来改进）

---

**版本**: v1.1.0-feature  
**日期**: 2025-11-06  
**作者**: DeepSeek AI Trading Team  
**分支**: feature/stop-PnL

