# scripts/diagnose_realtime.py 专家评估报告

**评估日期**: 2026-02-01
**脚本版本**: v11.15
**评估人**: Claude (AI 代码审计专家)
**评估方法**: 静态代码分析 + 架构一致性检查 + 误导性内容审查

---

## 📊 总体评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **功能完整性** | 9.5/10 | 覆盖完整交易流程，14 步骤全面诊断 |
| **代码质量** | 9.0/10 | 结构清晰，注释详尽，可维护性高 |
| **架构一致性** | 8.5/10 | 与 main_live.py 高度一致，部分遗留引用待清理 |
| **文档准确性** | 7.5/10 | 存在误导性描述，引用已删除功能 |
| **可用性** | 9.8/10 | 命令行参数丰富，输出格式友好 |

**综合评分**: **8.9/10** (优秀)

---

## ✅ 优点

### 1. 功能覆盖全面

**14 步骤诊断流程**:
1. 配置加载验证 (ConfigManager, main_live.py)
2. Binance API 连接测试
3. Telegram 连接测试
4. 技术指标计算测试
5. 订单流数据测试 (BinanceKlineClient)
6. 衍生品数据测试 (Coinalyze + Binance Derivatives)
7. 情绪数据测试
8. 订单簿深度测试 (v3.7)
9. AIDataAssembler 测试
10. MultiAgentAnalyzer 测试 (Bull/Bear/Judge/Risk)
11. 仓位计算测试
12. SL/TP 计算测试
13. 订单提交模拟
14. 完整信号生成

### 2. 代码质量高

- **模块化设计**: 每个测试步骤独立封装，可单独运行
- **错误处理**: 完善的异常捕获和降级逻辑
- **日志输出**: 清晰的进度提示和结果显示
- **参数化配置**: `--summary`/`--export`/`--push` 等灵活选项

### 3. 架构同步

- **配置共享**: 使用 `get_strategy_config()` 从 `main_live.py` 获取真实配置
- **组件初始化**: 与实盘代码完全一致的参数传递
- **数据流一致**: 与 TradingAgents v3.4 架构匹配

### 4. 实用工具

```bash
# 快速诊断
python3 scripts/diagnose_realtime.py --summary

# 完整诊断 + 导出
python3 scripts/diagnose_realtime.py --export

# 诊断 + 推送到 GitHub
python3 scripts/diagnose_realtime.py --export --push
```

---

## ⚠️ 问题清单

### 问题 1: 引用已删除的 MTF DecisionState (Critical)

**位置**: Line 63, 137, 250, 792, 873-875, 1919-1926, 3240

**问题描述**:
多处引用 `DecisionState` 枚举和 `ALLOW_LONG/ALLOW_SHORT/WAIT` 状态，但这些在 MTF v3.3 重构中已被删除。

**原因**:
MTF v3.3 重构移除了本地决策逻辑，改为完全由 AI 控制。但诊断脚本中的描述和模拟逻辑未同步更新。

**影响**:
- ✅ 不影响功能 (实际代码未调用 `get_decision_state()`)
- ❌ 误导性描述 (用户以为仍有本地决策)
- ❌ 模拟逻辑过时 (Line 1917-1926 的 MTF 状态估算使用旧逻辑)

**修复方案**:
```python
# 删除或更新以下内容:

# Line 63, 137, 250: 更新版本说明
- 添加 MTF 状态估算 (基于当前数据估算趋势方向, ALLOW_LONG/SHORT)
+ 添加 MTF 数据展示 (三层时间框架原始数据，无本地决策)

# Line 792-793: 修改导入成功消息
print("  ✅ MultiTimeframeManager 导入成功")
- print(f"     v3.3: DecisionState 已移除 (决策逻辑由 AI 控制)")
+ print(f"     v3.3: 三层数据收集 (1D/4H/15M)，决策逻辑由 AI 控制")

# Line 873-875: 已正确标注移除，保留

# Line 1917-1926: 删除旧的 MTF 状态估算逻辑
# 此段代码试图模拟 ALLOW_LONG/SHORT/WAIT，但 MTF v3.3 已无此概念

# Line 3240: 更新流程说明
- print(f"       - 计算 ALLOW_LONG/ALLOW_SHORT/WAIT 状态")
+ print(f"       - 收集决策层技术指标 (AI 自主分析)")
```

---

### 问题 2: support/resistance 遗留引用 (Medium)

**位置**: Line 58, 77, 131, 150, 1091, 1249, 1881, 2007-2020, 2028-2041, 3465-3517

**问题描述**:
脚本中多处提到 `support/resistance` 数据，并在调用 `calculate_technical_sltp()` 时传递这些参数。

**澄清**:
- ✅ **TradingAgents v3.3 确实移除了传给 AI 的 support/resistance**
  （AI 改用 SMA/BB 作为动态支撑阻力）
- ✅ **但 `calculate_technical_sltp()` 仍需要 support/resistance 参数**
  （用于技术回退计算，非 AI 输入）

**当前状态**: **正确**，但缺少说明导致误解

**优化方案**:
```python
# Line 1249: 添加澄清说明
print("  📝 v3.3: AI 只接收原始数值 (SMA/RSI/MACD/BB)，不接收 support/resistance/trend 标签")
+ print("     注: support/resistance 仍用于技术回退计算 (非 AI 输入)")

# Line 1881: 修改说明
print("     ❌ support/resistance - AI 用 SMA_50/BB 作动态支撑阻力")
+ print("       (但仍保留用于技术回退计算)")
```

---

### 问题 3: Funding Rate 数据源标注 (Fixed in v3.8)

**位置**: Line 65, 139, 2488-2521, 3661-3674

**状态**: ✅ **已在本次修复中解决**

**修改内容**:
- 配置改为 `always_use_binance: true`
- 输出标注为 "币安 8 小时资金费率"
- 添加结算周期说明 (00:00/08:00/16:00 UTC)

---

### 问题 4: 版本号管理混乱 (Minor)

**位置**: 文件头部 (Line 3-150)

**问题描述**:
版本更新日志堆积，导致文件头部过长（150 行）。

**影响**: 可维护性降低

**建议**:
```python
# 保留最近 3-5 个版本的更新日志
# 旧版本日志移至 docs/DIAGNOSE_REALTIME_CHANGELOG.md

# 当前文件头部应保持在 50 行以内:
"""
实盘信号诊断脚本 v11.15

当前架构 (TradingAgents v3.4):
- System Prompt: 角色定义 + INDICATOR_DEFINITIONS
- User Prompt: 原始数据 + 任务指令
- Phase 1: Bull/Bear 辩论 (2 AI calls)
- Phase 2: Judge 决策 (1 AI call)
- Phase 3: Risk 评估 (1 AI call)
- 执行层风控: S/R Zone Block

最近更新:
v11.15: 添加记忆系统和提示词验证 (v3.12)
v11.14: 修复误导性输出问题 (HOLD 仓位计算等)
v11.13: 添加 S/R Zone 测试 (v3.8)

完整更新日志: docs/DIAGNOSE_REALTIME_CHANGELOG.md
"""
```

---

### 问题 5: 硬编码常量 (Minor)

**位置**: Line 1917-1926, 等

**问题描述**:
MTF 状态估算逻辑中使用硬编码的 RSI 阈值 (70/30)，与配置文件不一致。

**修复方案**:
如果保留 MTF 估算功能，应从 `strategy_config` 读取阈值。
**建议**: 删除此功能（因为 MTF v3.3 已无本地决策）。

---

## 🔧 修复优先级

| 优先级 | 问题 | 影响 | 修复难度 |
|--------|------|------|----------|
| **P0** | DecisionState 引用 | 误导用户 | 低 (删除/修改描述) |
| **P1** | support/resistance 说明 | 理解混淆 | 低 (添加注释) |
| **P2** | 版本号管理 | 可维护性 | 中 (重构文件头部) |
| **P3** | 硬编码常量 | 配置一致性 | 低 (删除或配置化) |

---

## 📝 修复检查清单

- [ ] 删除所有 `DecisionState`/`ALLOW_LONG`/`ALLOW_SHORT`/`WAIT` 引用
- [ ] 删除 Line 1917-1926 的旧 MTF 状态估算逻辑
- [ ] 添加 support/resistance 用途说明 (技术回退 vs AI 输入)
- [ ] 清理版本更新日志 (移至独立文件)
- [ ] 验证所有输出描述与当前架构一致

---

## 🎯 推荐操作

### 立即修复
1. **删除 DecisionState 引用** (避免误导)
2. **添加 Funding Rate 周期标注** (已完成)

### 中期优化
3. **重构版本日志** (提高可维护性)
4. **添加架构一致性检查** (自动化验证)

### 长期改进
5. **自动化测试** (pytest 集成)
6. **性能优化** (并行 API 调用)

---

## 📚 参考

- MTF v3.3 重构: commit `ed27cb5`
- TradingAgents 架构: https://github.com/TauricResearch/TradingAgents
- 配置管理: docs/CONFIG_MANAGEMENT_PROPOSAL.md
- 资金费率修复: v3.8 (本次修复)

---

**评估完成时间**: 2026-02-01
**下次评估建议**: 每次架构重构后 (MTF v3.x, TradingAgents v3.x 等)
