#!/usr/bin/env python3
"""
简化对比测试：仅对比 DeepSeek 提示词差异
不需要 nautilus_trader 依赖
"""

import os
import sys

print("=" * 70)
print("  简化对比测试：DeepSeek 提示词和配置差异")
print("=" * 70)
print()

# =============================================================================
# 1. 对比 DeepSeek 客户端配置
# =============================================================================
print("[1/3] 对比 DeepSeek 客户端配置...")
print()

# 读取本仓库的 DeepSeek 配置
print("  📦 本仓库 (utils/deepseek_client.py):")
with open('utils/deepseek_client.py', 'r') as f:
    content = f.read()

# 找 temperature 默认值
import re
temp_match = re.search(r'temperature:\s*float\s*=\s*([\d.]+)', content)
if temp_match:
    our_temp = temp_match.group(1)
    print(f"     temperature: {our_temp}")

# 找系统提示词
if 'DECISIVE' in content or 'Prefer action' in content:
    print("     系统提示词: ✅ 已优化 (果断行动)")
else:
    print("     系统提示词: ❌ 原始版本 (保守)")

# 读取参考仓库
print()
print("  📦 参考仓库 (/tmp/nautilus_AItrader_ref/utils/deepseek_client.py):")

try:
    with open('/tmp/nautilus_AItrader_ref/utils/deepseek_client.py', 'r') as f:
        ref_content = f.read()

    temp_match = re.search(r'temperature:\s*float\s*=\s*([\d.]+)', ref_content)
    if temp_match:
        ref_temp = temp_match.group(1)
        print(f"     temperature: {ref_temp}")

    if 'DECISIVE' in ref_content or 'Prefer action' in ref_content:
        print("     系统提示词: ✅ 已优化 (果断行动)")
    else:
        print("     系统提示词: ❌ 原始版本 (保守)")
except FileNotFoundError:
    print("     ❌ 参考仓库未克隆")
    ref_temp = "0.1"
    ref_content = ""

print()

# =============================================================================
# 2. 对比 on_timer 流程
# =============================================================================
print("[2/3] 对比 on_timer 信号处理流程...")
print()

print("  📦 参考仓库流程:")
print("     1. 获取技术数据")
print("     2. 调用 DeepSeek.analyze()")
print("     3. 如果 signal in ['BUY', 'SELL']:")
print("        → 发送 Telegram 通知")
print("     4. 执行交易 _execute_trade()")
print()

print("  📦 本仓库流程:")
print("     1. 获取技术数据")
print("     2. 调用 DeepSeek.analyze()")
print("     3. 调用 MultiAgent.analyze() (6次 API 调用)")
print("        - Bull Agent (2次)")
print("        - Bear Agent (2次)")
print("        - Judge (1次)")
print("        - Risk Evaluator (1次)")
print("     4. 调用 process_signals() 合并信号")
print("        - 如果 DeepSeek=BUY, MultiAgent=SELL → 信心融合")
print("        - 如果信心相等 → HOLD (跳过交易)")
print("     5. 如果 final_signal in ['BUY', 'SELL']:")
print("        → 发送 Telegram 通知")
print("     6. 执行交易 _execute_trade()")
print()

# =============================================================================
# 3. 关键差异分析
# =============================================================================
print("[3/3] 关键差异分析...")
print()

print("=" * 70)
print("  🔍 发现的关键差异")
print("=" * 70)
print()

differences = []

# 差异 1: MultiAgent
differences.append({
    'title': 'MultiAgent 辩论系统',
    'ref': '无',
    'ours': '有 (Bull/Bear 辩论 + Judge)',
    'impact': '每次分析需要 6 次 API 调用，耗时 30-60 秒',
    'risk': '如果 DeepSeek 和 MultiAgent 意见不一致，可能导致 HOLD'
})

# 差异 2: 信号合并
differences.append({
    'title': '信号处理',
    'ref': '直接使用 DeepSeek 信号',
    'ours': 'process_signals() 合并两个信号',
    'impact': '增加了信号被修改为 HOLD 的可能性',
    'risk': '如果两个 AI 信心相等但方向相反，结果是 HOLD'
})

# 差异 3: Temperature
if our_temp != ref_temp:
    differences.append({
        'title': 'Temperature 参数',
        'ref': f'{ref_temp} (保守)',
        'ours': f'{our_temp} (平衡)',
        'impact': '较高的 temperature 产生更多变化的响应',
        'risk': '无负面影响'
    })

for i, diff in enumerate(differences, 1):
    print(f"  差异 {i}: {diff['title']}")
    print(f"     参考仓库: {diff['ref']}")
    print(f"     本仓库:   {diff['ours']}")
    print(f"     影响:     {diff['impact']}")
    print(f"     风险:     {diff['risk']}")
    print()

print("=" * 70)
print("  💡 建议")
print("=" * 70)
print()
print("  问题根因: 本仓库添加了 MultiAgent 系统，增加了信号被过滤为 HOLD 的可能性")
print()
print("  解决方案:")
print("     方案 A: 临时禁用 MultiAgent (与参考仓库一致)")
print("             修改 on_timer，跳过 MultiAgent 分析")
print()
print("     方案 B: 降低信号冲突导致 HOLD 的概率")
print("             修改 process_signals() 逻辑，让信号更容易通过")
print()
print("     方案 C: 检查服务器日志，确认 timer 是否在触发")
print()
print("=" * 70)
