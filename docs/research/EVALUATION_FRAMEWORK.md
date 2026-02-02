# S/R 强度 + 历史数据上下文 评估框架

**日期**: 2026-02-02
**状态**: 评估标准定义 (实施前)
**关联文档**: [SR_STRENGTH_RESEARCH.md](./SR_STRENGTH_RESEARCH.md)

---

## 一、项目概述

### 1.1 待实施功能

| 工程 | 目标 | 预期收益 |
|-----|------|---------|
| **历史数据上下文** | AI 看到 20 值趋势而非孤立单值 | 提升 AI 决策质量 |
| **S/R 强度增强** | 自动识别支撑阻力强度 | 动态调整 SL/TP |

### 1.2 用户确认的需求

| 问题 | 用户确认 |
|-----|---------|
| 哪些数据需要历史上下文？ | ✅ 全部数据类型 |
| 历史数据保留多少个值？ | ✅ 20 个值 |
| 哪些时间框架需要？ | ✅ 全部 (15M, 4H, 1D) |
| 接受 Token 成本增加？ | ✅ 确认接受 |
| 数据持久化方式？ | ✅ 文件持久化 |

---

## 二、技术实现标准

### 2.1 数据质量指标

| 指标 | 目标值 | 测量方法 | 优先级 |
|-----|-------|---------|-------|
| **数据完整性** | ≥95% 无缺失 | 日志检查 `len(history) == 20` | P0 |
| **持久化可靠性** | 重启后数据保留 ≥95% | 重启测试对比 | P0 |
| **数据新鲜度** | 最新数据 < 15分钟 | 时间戳检查 | P1 |

### 2.2 性能指标

| 指标 | 目标值 | 最大容忍 | 测量方法 |
|-----|-------|---------|---------|
| **数据处理延迟** | < 50ms | < 100ms | 性能埋点 |
| **内存增量** | < 30MB | < 50MB | 监控对比 |
| **文件 I/O** | < 10ms/次 | < 20ms/次 | 持久化耗时 |

### 2.3 验收测试用例

```python
# 测试用例 1: 数据完整性
def test_history_completeness():
    """历史数据应包含 20 个值"""
    history = indicator_manager.get_history('rsi', timeframe='15m')
    assert len(history) == 20, f"Expected 20, got {len(history)}"

# 测试用例 2: 持久化可靠性
def test_persistence_after_restart():
    """重启后历史数据应保留"""
    before = load_history_from_file()
    # 模拟重启
    after = load_history_from_file()
    assert before == after, "Data lost after restart"

# 测试用例 3: 性能
def test_processing_latency():
    """数据处理延迟应 < 100ms"""
    start = time.time()
    process_all_indicators()
    elapsed = (time.time() - start) * 1000
    assert elapsed < 100, f"Too slow: {elapsed}ms"
```

---

## 三、S/R 强度准确性标准

### 3.1 准确率目标

| 指标 | Phase 1 目标 | Phase 2 目标 | Phase 3 目标 |
|-----|-------------|-------------|-------------|
| **强阻力识别率** | ≥55% | ≥65% | ≥75% |
| **强支撑识别率** | ≥55% | ≥65% | ≥75% |
| **假信号率** | ≤35% | ≤25% | ≤20% |
| **多框架共振准确率** | ≥60% | ≥70% | ≥80% |

### 3.2 测量定义

```python
def is_sr_prediction_correct(
    sr_zone: SRZone,
    price_history: List[float],
    atr: float
) -> bool:
    """
    S/R 预测成功的定义:

    条件 1: 价格触及 S/R Zone
      - 触及定义: |price - zone.price_center| < ATR * 0.3

    条件 2: 在 3 根 K 线内反弹
      - 反弹定义: 价格变化 ≥ 0.5%

    条件 3: 未在 6 根 K 线内突破
      - 突破定义: 收盘价穿越 zone.price_center ± ATR * 0.5

    Returns:
        True if all conditions met (成功预测)
        False otherwise (失败预测)
    """
    # 条件 1: 触及
    touch_threshold = atr * 0.3
    touched = any(
        abs(price - sr_zone.price_center) < touch_threshold
        for price in price_history[:3]
    )
    if not touched:
        return None  # 未触及，不计入统计

    # 条件 2: 反弹
    touch_price = price_history[0]
    max_bounce = max(
        abs(price - touch_price) / touch_price
        for price in price_history[1:4]
    )
    bounced = max_bounce >= 0.005  # 0.5%

    # 条件 3: 未突破
    break_threshold = atr * 0.5
    broke_through = any(
        abs(close - sr_zone.price_center) > break_threshold
        for close in price_history[1:7]  # 6 根 K 线
    )

    return bounced and not broke_through


def calculate_sr_accuracy(predictions: List[Dict]) -> Dict:
    """
    计算 S/R 准确率

    Returns:
        {
            'total_predictions': int,
            'touched': int,
            'correct': int,
            'accuracy': float,  # correct / touched
            'false_positive_rate': float  # 假信号率
        }
    """
    touched = [p for p in predictions if p['result'] is not None]
    correct = [p for p in touched if p['result'] == True]

    return {
        'total_predictions': len(predictions),
        'touched': len(touched),
        'correct': len(correct),
        'accuracy': len(correct) / len(touched) if touched else 0,
        'false_positive_rate': 1 - (len(correct) / len(touched)) if touched else 0
    }
```

### 3.3 强度分级标准

| 强度等级 | 条件 | 预期准确率 |
|---------|------|-----------|
| **STRONG** | Order Wall + 多框架共振 + Volume 确认 | ≥75% |
| **MEDIUM** | 2+ 指标共振 | 60-75% |
| **WEAK** | 单一指标 | 50-60% |

---

## 四、交易绩效标准 (核心)

### 4.1 A/B 测试设计

```
┌─────────────────────────────────────────────────────────────┐
│  对照组 (A): 当前系统                                        │
│  ├─ 固定 SL: 2%                                             │
│  ├─ 固定 TP: 根据 confidence (1%/2%/3%)                     │
│  ├─ 无历史数据上下文                                         │
│  └─ 无 S/R 强度调整                                         │
└─────────────────────────────────────────────────────────────┘
                          vs
┌─────────────────────────────────────────────────────────────┐
│  实验组 (B): 新系统                                          │
│  ├─ 动态 SL: 基于支撑强度调整                                │
│  ├─ 动态 TP: 基于阻力强度调整                                │
│  ├─ 20 值历史数据上下文                                      │
│  └─ AI 可见趋势变化                                          │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 核心绩效指标

| 指标 | 定义 | 目标改进 | 最低接受 |
|-----|------|---------|---------|
| **胜率 (Win Rate)** | 盈利交易 / 总交易 | +5% | 不低于基准 |
| **盈亏比 (R:R)** | 平均盈利 / 平均亏损 | +15% | +5% |
| **最大回撤 (MDD)** | 最大峰谷跌幅 | -10% | 不高于基准 |
| **Sharpe Ratio** | (收益-无风险) / 波动率 | +0.2 | 不低于基准 |
| **Profit Factor** | 总盈利 / 总亏损 | +10% | +5% |
| **平均持仓时间** | 开仓到平仓时间 | 记录变化 | 无硬性要求 |

### 4.3 计算公式

```python
def calculate_trading_metrics(trades: List[Trade]) -> Dict:
    """
    计算交易绩效指标
    """
    if not trades:
        return {}

    # 基础统计
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]

    # 胜率
    win_rate = len(wins) / len(trades) if trades else 0

    # 盈亏比
    avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t.pnl for t in losses) / len(losses)) if losses else 1
    risk_reward = avg_win / avg_loss if avg_loss > 0 else 0

    # Profit Factor
    total_profit = sum(t.pnl for t in wins)
    total_loss = abs(sum(t.pnl for t in losses))
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

    # 最大回撤
    cumulative = []
    running_total = 0
    for t in trades:
        running_total += t.pnl
        cumulative.append(running_total)

    peak = cumulative[0]
    max_drawdown = 0
    for value in cumulative:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak if peak > 0 else 0
        max_drawdown = max(max_drawdown, drawdown)

    # Sharpe Ratio (简化版，假设无风险利率=0)
    returns = [t.pnl_pct for t in trades]
    avg_return = sum(returns) / len(returns)
    std_return = (sum((r - avg_return)**2 for r in returns) / len(returns)) ** 0.5
    sharpe = avg_return / std_return if std_return > 0 else 0

    return {
        'total_trades': len(trades),
        'win_rate': win_rate,
        'risk_reward': risk_reward,
        'profit_factor': profit_factor,
        'max_drawdown': max_drawdown,
        'sharpe_ratio': sharpe,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
    }
```

### 4.4 样本量要求

| 要求 | 最小值 | 推荐值 | 原因 |
|-----|-------|-------|------|
| **交易次数** | ≥50 次/组 | ≥100 次/组 | 统计显著性 |
| **时间跨度** | ≥14 天 | ≥30 天 | 覆盖不同市场状态 |
| **牛市天数** | ≥5 天 | ≥10 天 | 避免偏差 |
| **熊市天数** | ≥5 天 | ≥10 天 | 避免偏差 |
| **震荡天数** | ≥5 天 | ≥10 天 | 避免偏差 |

### 4.5 统计显著性检验

```python
from scipy import stats

def is_improvement_significant(
    control_results: List[float],
    experiment_results: List[float],
    alpha: float = 0.05
) -> Dict:
    """
    检验实验组是否显著优于对照组

    使用 Welch's t-test (不假设等方差)
    """
    t_stat, p_value = stats.ttest_ind(
        experiment_results,
        control_results,
        equal_var=False
    )

    # 单尾检验 (实验组 > 对照组)
    p_value_one_tail = p_value / 2 if t_stat > 0 else 1 - p_value / 2

    return {
        't_statistic': t_stat,
        'p_value': p_value_one_tail,
        'is_significant': p_value_one_tail < alpha,
        'confidence_level': 1 - alpha,
        'conclusion': '实验组显著优于对照组' if p_value_one_tail < alpha else '无显著差异'
    }
```

---

## 五、AI 决策质量标准

### 5.1 信号质量指标

| 指标 | 目标 | 测量方法 |
|-----|------|---------|
| **HOLD 信号比例** | 减少 20% | 对比新旧系统 |
| **信号一致性** | ≥70% | 相同数据重复测试 |
| **HIGH confidence 胜率** | ≥60% | 高信心信号的实际胜率 |
| **信号变化频率** | 合理范围 | 避免过度交易或过度保守 |

### 5.2 历史上下文利用率

```python
def analyze_ai_reasoning(reasoning_text: str) -> Dict:
    """
    分析 AI 是否实际使用了历史数据上下文

    检查关键词:
    - 趋势类: 趋势, trend, rising, falling, increasing, decreasing
    - 历史类: 连续, consecutive, previous, 之前, 历史
    - 变化类: 变化, change, shift, 转变
    - 比较类: 相比, compared, versus, vs
    """
    text_lower = reasoning_text.lower()

    trend_keywords = ['趋势', 'trend', 'rising', 'falling', 'increasing',
                      'decreasing', 'upward', 'downward', '上升', '下降']
    history_keywords = ['连续', 'consecutive', 'previous', '之前', '历史',
                        'earlier', 'past', '前']
    change_keywords = ['变化', 'change', 'shift', '转变', 'moved', 'shifted']
    compare_keywords = ['相比', 'compared', 'versus', 'vs', '对比', 'than']

    uses_trend = any(kw in text_lower for kw in trend_keywords)
    uses_history = any(kw in text_lower for kw in history_keywords)
    uses_change = any(kw in text_lower for kw in change_keywords)
    uses_compare = any(kw in text_lower for kw in compare_keywords)

    utilization_score = sum([uses_trend, uses_history, uses_change, uses_compare])

    return {
        'uses_trend': uses_trend,
        'uses_history': uses_history,
        'uses_change': uses_change,
        'uses_compare': uses_compare,
        'utilization_score': utilization_score,  # 0-4
        'utilizes_context': utilization_score >= 1
    }

# 目标: ≥60% 的 AI 决策 utilizes_context == True
```

### 5.3 决策质量分级

| 质量等级 | 条件 | 预期比例 |
|---------|------|---------|
| **优秀** | 使用 3+ 类上下文关键词 | ≥20% |
| **良好** | 使用 1-2 类上下文关键词 | ≥40% |
| **一般** | 未明确使用上下文 | ≤40% |

---

## 六、风险控制标准

### 6.1 异常场景处理

| 风险场景 | 检测条件 | 预期行为 | 验收标准 |
|---------|---------|---------|---------|
| **极端波动** | 5分钟波动 >3% | 回退到保守 SL/TP (固定 2%) | 100% 触发 |
| **S/R 数据缺失** | nearest_support=None | 使用默认值，不崩溃 | 100% 正常运行 |
| **历史数据不足** | len(history) < 10 | 标记数据质量低，告知 AI | 100% 正确标记 |
| **API 超时** | 数据获取 >5秒 | 使用缓存数据 | 100% 降级成功 |
| **连续亏损** | 3 次连续止损 | 降低仓位或发出警告 | 可配置触发 |

### 6.2 回退机制测试

```python
def test_fallback_mechanisms():
    """测试各种异常场景的回退机制"""

    # 场景 1: S/R 数据缺失
    result = calculate_sl_tp(sr_zone=None, confidence='MEDIUM')
    assert result['sl_pct'] == 0.02, "Should fallback to default 2%"

    # 场景 2: 历史数据不足
    history = [1, 2, 3]  # 只有 3 个值
    quality = assess_data_quality(history, required=20)
    assert quality['is_sufficient'] == False
    assert quality['warning'] == 'Insufficient history data'

    # 场景 3: 极端波动
    volatility = calculate_5min_volatility()
    if volatility > 0.03:  # 3%
        config = get_risk_config()
        assert config['use_conservative_sl_tp'] == True
```

### 6.3 安全边界

| 参数 | 硬限制 | 原因 |
|-----|-------|------|
| **最大止损** | ≤5% | 防止单笔巨亏 |
| **最小止损** | ≥0.5% | 避免被噪音止损 |
| **最大止盈** | ≤10% | 避免贪婪 |
| **最小止盈** | ≥0.5% | 覆盖手续费 |

---

## 七、评估时间线

```
┌─────────────────────────────────────────────────────────────┐
│  Week 1-2: 技术实现 + 单元测试                               │
│  ├─ 目标: 完成代码实现                                       │
│  ├─ 评估: 技术实现标准 (Section 二)                         │
│  ├─ 产出: 功能完成，所有测试通过                             │
│  └─ 里程碑: 代码合并到 main 分支                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Week 3-4: 数据收集 (模拟/纸交易)                            │
│  ├─ 目标: 收集 S/R 预测数据                                 │
│  ├─ 评估: S/R 准确性标准 (Section 三)                       │
│  ├─ 产出: 初步准确率报告                                     │
│  └─ 决策点: 准确率 ≥55% 继续，否则优化                      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Week 5-8: A/B 测试 (小资金实盘)                             │
│  ├─ 目标: 对比新旧系统绩效                                   │
│  ├─ 评估: 交易绩效标准 (Section 四)                         │
│  ├─ 样本: ≥50 次交易/组                                     │
│  ├─ 产出: 绩效对比报告                                       │
│  └─ 决策点: 达到最低接受标准继续                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Week 9-12: 扩展测试 + 优化                                  │
│  ├─ 目标: 增加样本量，优化参数                               │
│  ├─ 评估: 所有标准                                          │
│  ├─ 样本: ≥100 次交易/组                                    │
│  ├─ 产出: 完整评估报告                                       │
│  └─ 决策点: 全面上线 / 继续优化 / 回滚                      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Week 13+: 全面上线或回滚                                    │
│  ├─ 条件: 达到所有最低接受标准                               │
│  ├─ 监控: 持续跟踪绩效指标                                   │
│  └─ 迭代: 根据数据持续优化                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 八、评估报告模板

```markdown
# S/R 强度 + 历史数据上下文 评估报告

## 基本信息
- **测试周期**: YYYY-MM-DD 至 YYYY-MM-DD
- **测试阶段**: Phase X (Week Y-Z)
- **测试环境**: 模拟/小资金实盘/全资金实盘

## 一、技术实现评估

| 指标 | 目标 | 实际 | 状态 |
|-----|------|------|------|
| 数据完整性 | ≥95% | __% | ✅/❌ |
| 持久化可靠性 | ≥95% | __% | ✅/❌ |
| 处理延迟 | <100ms | __ms | ✅/❌ |
| 内存增量 | <50MB | __MB | ✅/❌ |

**技术评估结论**: 通过 / 需改进

## 二、S/R 准确性评估

| 指标 | 目标 | 实际 | 状态 |
|-----|------|------|------|
| 强阻力识别率 | ≥__% | __% | ✅/❌ |
| 强支撑识别率 | ≥__% | __% | ✅/❌ |
| 假信号率 | ≤__% | __% | ✅/❌ |
| 多框架共振准确率 | ≥__% | __% | ✅/❌ |

**样本量**: __ 次 S/R 预测
**准确性评估结论**: 通过 / 需改进

## 三、交易绩效评估

### 3.1 基准数据 (对照组 A)
- 交易次数: __
- 胜率: __%
- 盈亏比: __
- 最大回撤: __%
- Sharpe Ratio: __
- Profit Factor: __

### 3.2 实验数据 (实验组 B)
- 交易次数: __
- 胜率: __% (vs 基准: __%）
- 盈亏比: __ (vs 基准: __%)
- 最大回撤: __% (vs 基准: __%)
- Sharpe Ratio: __ (vs 基准: __)
- Profit Factor: __ (vs 基准: __%)

### 3.3 统计显著性
- t-statistic: __
- p-value: __
- 结论: 显著优于 / 无显著差异 / 显著劣于

**绩效评估结论**: 通过 / 需改进

## 四、AI 决策质量评估

| 指标 | 目标 | 实际 | 状态 |
|-----|------|------|------|
| HOLD 信号比例变化 | -20% | __% | ✅/❌ |
| 信号一致性 | ≥70% | __% | ✅/❌ |
| HIGH confidence 胜率 | ≥60% | __% | ✅/❌ |
| 历史上下文利用率 | ≥60% | __% | ✅/❌ |

**AI 质量评估结论**: 通过 / 需改进

## 五、风险控制评估

| 场景 | 测试次数 | 正确处理 | 成功率 |
|-----|---------|---------|-------|
| 极端波动回退 | __ | __ | __% |
| S/R 数据缺失 | __ | __ | __% |
| 历史数据不足 | __ | __ | __% |
| 连续亏损处理 | __ | __ | __% |

**风险控制评估结论**: 通过 / 需改进

## 六、总体结论

### 6.1 各维度评估汇总

| 维度 | 状态 | 备注 |
|-----|------|------|
| 技术实现 | ✅/❌ | |
| S/R 准确性 | ✅/❌ | |
| 交易绩效 | ✅/❌ | |
| AI 决策质量 | ✅/❌ | |
| 风险控制 | ✅/❌ | |

### 6.2 决策建议

- [ ] **全面上线**: 所有指标达标，建议全面启用
- [ ] **继续优化**: 部分指标达标，建议优化后重新测试
- [ ] **回滚**: 多项指标未达标，建议回滚到原系统

### 6.3 后续行动

1. __________________
2. __________________
3. __________________

## 附录

### A. 详细交易记录
(附表或链接)

### B. S/R 预测详细数据
(附表或链接)

### C. AI 决策样本分析
(附表或链接)

---
报告生成时间: YYYY-MM-DD HH:MM:SS
报告人: __________
```

---

## 九、指标速查表

| 维度 | 核心指标 | 最低接受 | 目标值 |
|-----|---------|---------|-------|
| **技术** | 数据完整性 | ≥95% | 100% |
| **技术** | 处理延迟 | <100ms | <50ms |
| **准确性** | S/R 识别率 | ≥55% | ≥75% |
| **准确性** | 假信号率 | ≤35% | ≤20% |
| **绩效** | 胜率变化 | ≥0% | +5% |
| **绩效** | 盈亏比变化 | +5% | +15% |
| **绩效** | 最大回撤 | 不高于基准 | -10% |
| **AI** | 上下文利用率 | ≥50% | ≥70% |
| **风险** | 异常处理成功率 | 100% | 100% |
| **样本** | 最小交易次数 | ≥50次/组 | ≥100次/组 |
| **样本** | 最小测试天数 | ≥14天 | ≥30天 |

---

## 十、参考资料

- S/R 强度研究报告: [SR_STRENGTH_RESEARCH.md](./SR_STRENGTH_RESEARCH.md)
- Cont et al. (2014). The Price Impact of Order Book Events
- 12-Factor App Configuration: https://12factor.net/config
- A/B Testing Calculator: https://www.evanmiller.org/ab-testing/

---

**文档版本**: v1.0
**创建日期**: 2026-02-02
**最后更新**: 2026-02-02
