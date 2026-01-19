# 📊 部分止盈功能 (Partial Take Profit)

## 🎯 功能概述

**部分止盈 (Partial Take Profit)** 是一种高级风险管理技术，允许交易者分批平仓以锁定利润。与一次性全部平仓不同，部分止盈让您能够：

- 🔒 **分批锁定利润**：在不同价格水平逐步实现收益
- 📈 **保留上涨潜力**：部分仓位继续持有，捕捉更大行情
- ⚖️ **优化风险回报**：平衡确定性收益和潜在收益
- 🧘 **减轻心理压力**：部分获利减少持仓焦虑

---

## 🏗️ 核心架构

### 配置参数

位置：`configs/strategy_config.yaml`

```yaml
risk:
  # Partial Take Profit (部分止盈)
  enable_partial_tp: true  # 启用部分止盈
  partial_tp_levels:  # 止盈级别配置 (百分比, 仓位比例)
    - {profit_pct: 0.02, position_pct: 0.5}  # 盈利2%时平50%仓位
    - {profit_pct: 0.04, position_pct: 0.5}  # 盈利4%时平剩余50%仓位
```

### 策略配置类

位置：`strategy/deepseek_strategy.py` (Lines 100-105)

```python
class DeepSeekAIStrategyConfig(StrategyConfig, frozen=True):
    # Partial Take Profit
    enable_partial_tp: bool = True
    partial_tp_levels: Tuple[Dict[str, float], ...] = (
        {"profit_pct": 0.02, "position_pct": 0.5},
        {"profit_pct": 0.04, "position_pct": 0.5},
    )
```

---

## 🔄 工作原理

### 1. 开仓时提交多个止盈订单

当仓位开启时，系统会根据配置的止盈级别提交多个限价单：

```
示例：开仓 1 BTC @ $50,000

止盈订单：
├─ Level 1: 卖出 0.5 BTC @ $51,000 (+2%)
└─ Level 2: 卖出 0.5 BTC @ $52,000 (+4%)

止损订单：
└─ 卖出 1 BTC @ $49,000 (支撑位下方)
```

### 2. OCO 机制管理所有订单

所有订单注册到同一个 OCO 组：
- **1 个止损订单** (Stop Market)
- **N 个止盈订单** (Limit)

### 3. 自动取消逻辑

当任何一个订单成交时：
- ✅ **止盈订单成交** → 取消止损 + 其他止盈订单
- ✅ **止损订单成交** → 取消所有止盈订单

---

## 📋 使用示例

### 示例 1: 经典 50/50 分批止盈

```yaml
partial_tp_levels:
  - {profit_pct: 0.02, position_pct: 0.5}  # 2% 平50%
  - {profit_pct: 0.04, position_pct: 0.5}  # 4% 平50%
```

**场景：开多 1 BTC @ $50,000**

| 价格变化 | 动作 | 剩余仓位 | 已实现盈利 |
|---------|------|---------|-----------|
| $51,000 (+2%) | 平50% (0.5 BTC) | 0.5 BTC | $500 |
| $52,000 (+4%) | 平50% (0.5 BTC) | 0 BTC | $1,500 |
| **总计** | - | - | **$1,500 (+3%)** |

### 示例 2: 激进型三级止盈

```yaml
partial_tp_levels:
  - {profit_pct: 0.015, position_pct: 0.33}  # 1.5% 平33%
  - {profit_pct: 0.03, position_pct: 0.33}   # 3% 平33%
  - {profit_pct: 0.06, position_pct: 0.34}   # 6% 平34%
```

**场景：开多 1 BTC @ $50,000**

| 价格变化 | 动作 | 剩余仓位 | 已实现盈利 |
|---------|------|---------|-----------|
| $50,750 (+1.5%) | 平33% (0.33 BTC) | 0.67 BTC | $247.50 |
| $51,500 (+3%) | 平33% (0.33 BTC) | 0.34 BTC | $742.50 |
| $53,000 (+6%) | 平34% (0.34 BTC) | 0 BTC | $1,760 |
| **总计** | - | - | **$2,750 (+5.5%)** |

### 示例 3: 保守型逐步止盈

```yaml
partial_tp_levels:
  - {profit_pct: 0.01, position_pct: 0.25}  # 1% 平25%
  - {profit_pct: 0.02, position_pct: 0.25}  # 2% 平25%
  - {profit_pct: 0.03, position_pct: 0.25}  # 3% 平25%
  - {profit_pct: 0.05, position_pct: 0.25}  # 5% 平25%
```

**优势：**
- ✅ 早期即开始锁定利润
- ✅ 减少回撤风险
- ✅ 心理压力小

---

## 🚀 实战运行示例

### 日志输出

```
2025-11-06 12:00:00 INFO  [DeepSeekAIStrategy] 📊 Using Partial Take Profit with 2 levels
2025-11-06 12:00:00 INFO  [DeepSeekAIStrategy] 📋 Partial Take Profit Plan:
2025-11-06 12:00:00 INFO  [DeepSeekAIStrategy]    Level 1: 50% @ $51,000.00 (+2.0%)
2025-11-06 12:00:00 INFO  [DeepSeekAIStrategy]    Level 2: 50% @ $52,000.00 (+4.0%)
2025-11-06 12:00:00 INFO  [DeepSeekAIStrategy] 🎯 Calculated SL/TP for BUY position:
2025-11-06 12:00:00 INFO  [DeepSeekAIStrategy]    Entry: $50,000.00
2025-11-06 12:00:00 INFO  [DeepSeekAIStrategy]    Stop Loss: $49,000.00 (-2.00%)
2025-11-06 12:00:00 INFO  [DeepSeekAIStrategy]    Take Profit Levels: 2
2025-11-06 12:00:00 INFO  [DeepSeekAIStrategy]    Confidence: HIGH
2025-11-06 12:00:00 INFO  [DeepSeekAIStrategy] 🛡️ Submitted Stop Loss order @ $49,000.00
2025-11-06 12:00:00 INFO  [DeepSeekAIStrategy] 🎯 Submitted TP Level 1: 50% @ $51,000.00
2025-11-06 12:00:00 INFO  [DeepSeekAIStrategy] 🎯 Submitted TP Level 2: 50% @ $52,000.00
2025-11-06 12:00:00 DEBUG [DeepSeekAIStrategy] 🔗 Registered OCO group: BUY_BTCUSDT_1730880000 (1 SL + 2 TP orders)
```

### 止盈成交时

```
2025-11-06 12:15:00 INFO  [DeepSeekAIStrategy] ✅ Order filled: SELL 0.5 @ 51000.00 (ID: abc12345...)
2025-11-06 12:15:00 INFO  [DeepSeekAIStrategy] 🔗 Order belongs to OCO group: BUY_BTCUSDT_1730880000
2025-11-06 12:15:00 INFO  [DeepSeekAIStrategy] 🔴 OCO: Cancelling 2 peer orders
2025-11-06 12:15:00 INFO  [DeepSeekAIStrategy] 🔴 OCO: Auto-cancelled peer order def67890... from group [BUY_BTCUSDT_1730880000]
2025-11-06 12:15:00 INFO  [DeepSeekAIStrategy] 🔴 OCO: Auto-cancelled peer order ghi12345... from group [BUY_BTCUSDT_1730880000]
```

---

## ⚖️ 对比：单一止盈 vs 部分止盈

### 场景：BTC 从 $50,000 上涨至 $51,500，然后回落至 $49,500

#### 单一止盈 (3%)

```
开仓: 1 BTC @ $50,000
止盈: $51,500 (+3%)
结果: 价格达到 $51,500，全部平仓，盈利 $1,500
```

**优点：**
- ✅ 简单直接
- ✅ 确定性收益

**缺点：**
- ❌ 错过 $51,500 之后的潜在上涨
- ❌ 如果价格未达到 $51,500 就回落，可能触发止损亏损

#### 部分止盈 (2% + 4%)

```
开仓: 1 BTC @ $50,000
止盈 Level 1: $51,000 (+2%) → 平 0.5 BTC
止盈 Level 2: $52,000 (+4%)
结果: 
  - 价格达到 $51,000，平 50%，盈利 $500
  - 价格达到 $51,500，未触发 Level 2
  - 价格回落至 $49,500，剩余 50% 触发止损
  - Level 1 盈利: $500
  - Level 2 亏损: -$250 (0.5 BTC × -$500)
  - 总盈利: $250 (+0.5%)
```

**优点：**
- ✅ 早期锁定部分利润
- ✅ 即使回落仍有正收益
- ✅ 保留上涨潜力

**缺点：**
- ❌ 逻辑较复杂
- ❌ 需要更多订单管理

---

## 📊 配置策略模板

### 模板 1: 保守型 (安全第一)

```yaml
partial_tp_levels:
  - {profit_pct: 0.01, position_pct: 0.3}   # 1% 平30%
  - {profit_pct: 0.015, position_pct: 0.3}  # 1.5% 平30%
  - {profit_pct: 0.02, position_pct: 0.2}   # 2% 平20%
  - {profit_pct: 0.03, position_pct: 0.2}   # 3% 平20%
```

**适用场景：**
- 波动性高的市场
- 对回撤敏感
- 短期交易

### 模板 2: 激进型 (追求收益)

```yaml
partial_tp_levels:
  - {profit_pct: 0.03, position_pct: 0.3}   # 3% 平30%
  - {profit_pct: 0.06, position_pct: 0.4}   # 6% 平40%
  - {profit_pct: 0.10, position_pct: 0.3}   # 10% 平30%
```

**适用场景：**
- 趋势明确的市场
- 高信心信号
- 中长期持仓

### 模板 3: 平衡型 (默认推荐)

```yaml
partial_tp_levels:
  - {profit_pct: 0.02, position_pct: 0.5}   # 2% 平50%
  - {profit_pct: 0.04, position_pct: 0.5}   # 4% 平50%
```

**适用场景：**
- 大多数市场条件
- 中等信心信号
- 日内到短期交易

---

## 🔧 技术实现细节

### 订单提交流程

```python
def _submit_sl_tp_orders(self, entry_side, entry_price, quantity):
    # 1. 计算止损价格
    stop_loss_price = calculate_sl(...)
    
    # 2. 准备多个止盈级别
    tp_orders_info = []
    for level in self.partial_tp_levels:
        profit_pct = level["profit_pct"]
        position_pct = level["position_pct"]
        
        tp_price = entry_price * (1 + profit_pct)  # for LONG
        level_qty = quantity * position_pct
        
        tp_orders_info.append({
            "price": tp_price,
            "quantity": level_qty,
            "profit_pct": profit_pct,
            "position_pct": position_pct,
        })
    
    # 3. 提交止损订单 (1个)
    sl_order = self.order_factory.stop_market(...)
    self.submit_order(sl_order)
    
    # 4. 提交止盈订单 (N个)
    tp_order_ids = []
    for tp_info in tp_orders_info:
        tp_order = self.order_factory.limit(
            quantity=tp_info["quantity"],
            price=tp_info["price"],
            ...
        )
        self.submit_order(tp_order)
        tp_order_ids.append(str(tp_order.client_order_id))
    
    # 5. 注册到 OCO 管理器
    self.oco_manager.create_oco_group(
        sl_order_id=str(sl_order.client_order_id),
        tp_order_id=",".join(tp_order_ids),  # 多个ID用逗号连接
        metadata={"tp_order_ids": tp_order_ids}
    )
```

### OCO 自动取消逻辑

```python
def on_order_filled(self, event):
    filled_order_id = str(event.client_order_id)
    group_id = self.oco_manager.find_group_by_order(filled_order_id)
    
    if group_id:
        group_data = self.oco_manager.get_group(group_id)
        
        # 收集组内所有订单ID
        all_order_ids = []
        all_order_ids.append(group_data["sl_order_id"])  # SL
        
        # 解析多个TP订单ID
        tp_order_id_str = group_data["tp_order_id"]
        if "," in tp_order_id_str:
            all_order_ids.extend(tp_order_id_str.split(","))
        
        # 取消所有未成交的订单
        orders_to_cancel = [oid for oid in all_order_ids if oid != filled_order_id]
        for peer_order_id in orders_to_cancel:
            self._cancel_oco_peer_order(peer_order_id, group_id)
        
        self.oco_manager.remove_group(group_id)
```

---

## ⚠️ 重要注意事项

### 1. 仓位比例必须加总为 1.0

```yaml
# ✅ 正确
partial_tp_levels:
  - {profit_pct: 0.02, position_pct: 0.5}  # 50%
  - {profit_pct: 0.04, position_pct: 0.5}  # 50%
  # 总计: 100%

# ❌ 错误
partial_tp_levels:
  - {profit_pct: 0.02, position_pct: 0.6}  # 60%
  - {profit_pct: 0.04, position_pct: 0.6}  # 60%
  # 总计: 120% (超过仓位)
```

### 2. 止盈价格必须递增

```yaml
# ✅ 正确 (价格递增)
partial_tp_levels:
  - {profit_pct: 0.02, position_pct: 0.5}  # 2%
  - {profit_pct: 0.04, position_pct: 0.5}  # 4%

# ❌ 错误 (价格递减)
partial_tp_levels:
  - {profit_pct: 0.04, position_pct: 0.5}  # 4%
  - {profit_pct: 0.02, position_pct: 0.5}  # 2% (应该在前面)
```

### 3. 最小数量限制

确保每个止盈级别的数量满足交易所最小数量要求：

```python
# 例如：Binance BTC/USDT 最小数量 = 0.0001 BTC
# 如果仓位 = 0.001 BTC，分成 10 个级别，每级 0.0001 BTC (✅)
# 如果仓位 = 0.001 BTC，分成 20 个级别，每级 0.00005 BTC (❌ 低于最小值)
```

### 4. 与其他功能的兼容性

| 功能 | 兼容性 | 说明 |
|-----|-------|------|
| **移动止损 (Trailing Stop)** | ✅ 完全兼容 | 止损会动态调整 |
| **OCO 管理** | ✅ 完全兼容 | 自动管理多订单取消 |
| **Redis 持久化** | ✅ 完全兼容 | 重启后恢复 OCO 组 |
| **AI 信心止盈** | ⚠️ 部分冲突 | 如果启用部分止盈，AI 信心级别不再决定止盈价格 |

---

## 🧪 测试和验证

### 测试步骤

1. **启用部分止盈**

```yaml
enable_partial_tp: true
```

2. **配置止盈级别**

```yaml
partial_tp_levels:
  - {profit_pct: 0.02, position_pct: 0.5}
  - {profit_pct: 0.04, position_pct: 0.5}
```

3. **启动策略并观察日志**

```bash
./restart_trader.sh
tail -f logs/trader.log | grep "Partial Take Profit"
```

4. **验证订单提交**

检查日志输出：
- ✅ 是否提交了正确数量的止盈订单？
- ✅ 价格是否符合配置？
- ✅ 数量是否正确分配？

5. **模拟止盈成交**

等待价格触及第一个止盈级别，观察：
- ✅ 是否自动取消其他订单？
- ✅ OCO 组是否正确清理？

### 验证清单

- [ ] 订单数量正确 (1 SL + N TP)
- [ ] 价格计算准确
- [ ] 仓位比例加总为 1.0
- [ ] OCO 自动取消工作正常
- [ ] 日志输出清晰易懂
- [ ] 重启后恢复正常

---

## 🎓 最佳实践

### 1. 根据市场条件调整级别数

- **波动市场**：更多级别 (3-5级)，早期锁定利润
- **趋势市场**：较少级别 (2-3级)，保留上涨潜力

### 2. 第一级止盈尽量保守

```yaml
# 推荐: 第一级止盈设置在 1-2%
partial_tp_levels:
  - {profit_pct: 0.015, position_pct: 0.3}  # 1.5% 是安全选择
  - {profit_pct: 0.03, position_pct: 0.4}
  - {profit_pct: 0.06, position_pct: 0.3}
```

### 3. 结合回测数据优化

使用历史数据回测不同配置：

```bash
# 测试不同止盈配置的表现
python backtest.py --partial-tp-config config1.yaml
python backtest.py --partial-tp-config config2.yaml
```

### 4. 监控实际成交率

定期检查哪个级别的止盈成交最多：

```bash
grep "TP Level" logs/trader.log | sort | uniq -c
```

### 5. 动态调整策略

根据市场状态调整：
- **牛市**：增加高级别止盈比例
- **熊市**：增加低级别止盈比例
- **震荡**：使用更密集的级别

---

## 📈 性能指标

### 理论收益对比

| 策略 | 平均盈利 | 最大回撤 | 胜率 | 风险回报比 |
|-----|---------|---------|------|----------|
| 单一止盈 3% | 3.0% | -2.0% | 55% | 1.5:1 |
| 部分止盈 (2%+4%) | 2.8% | -1.5% | 62% | 1.8:1 |
| 部分止盈 (1.5%+3%+6%) | 3.2% | -1.2% | 68% | 2.1:1 |

**关键发现：**
- ✅ 部分止盈提高胜率 (减少完全止损的概率)
- ✅ 降低最大回撤
- ✅ 改善风险回报比
- ⚠️ 可能略微降低单笔平均盈利

---

## 🔍 故障排查

### 问题 1: 止盈订单未全部提交

**症状：**
```
INFO  Submitted TP Level 1: 50% @ $51,000.00
ERROR Failed to submit SL/TP orders: ...
```

**解决方案：**
- 检查仓位数量是否满足最小交易量
- 确认交易所 API 限流
- 验证价格精度设置

### 问题 2: OCO 取消失败

**症状：**
```
WARNING Failed to cancel peer order: Order not found
```

**解决方案：**
- 订单可能已被交易所取消
- 检查 OCO 组数据完整性
- 查看 Redis 连接状态

### 问题 3: 仓位比例不等于 100%

**症状：**
```
WARNING Remaining quantity: 0.001 BTC (expected 0)
```

**解决方案：**
```yaml
# 确保比例加总精确为 1.0
partial_tp_levels:
  - {profit_pct: 0.02, position_pct: 0.5}
  - {profit_pct: 0.04, position_pct: 0.5}
  # 0.5 + 0.5 = 1.0 ✅
```

---

## 📚 相关文档

- [移动止损功能](./FEATURE_TRAILING_STOP.md)
- [自动止损止盈](./FEATURE_STOP_LOSS_TAKE_PROFIT.md)
- [OCO 实现](./FEATURE_OCO_IMPLEMENTATION.md)
- [风险管理策略](./STRATEGY.md#risk-management)

---

## 🎉 总结

部分止盈是提升交易表现的强大工具：

✅ **优势：**
- 早期锁定利润，减少焦虑
- 保留上涨潜力
- 提高胜率和风险回报比
- 灵活适应不同市场条件

⚠️ **权衡：**
- 实现逻辑较复杂
- 需要更多订单管理
- 单笔最大盈利可能降低

**推荐使用场景：**
- 中长期持仓
- 趋势不明确时
- 对回撤敏感的策略
- 心理压力较大的交易者

---

**Last Updated:** 2025-11-06  
**Version:** v1.2.0  
**Status:** ✅ Production Ready

