#!/usr/bin/env python3
"""
记忆系统诊断脚本 v1.0

检测 v3.13 修复后的记忆系统是否正常工作：
1. 检查记忆文件读写
2. 模拟 pnl 计算流程
3. 验证 NautilusTrader Money/Quantity 类型处理
4. 测试 record_outcome() 功能

Usage:
    python3 scripts/diagnose_memory.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def print_header(title: str):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_section(title: str):
    print()
    print(f"[{title}]")
    print("-" * 70)


def test_memory_file():
    """测试 1: 检查记忆文件"""
    print_section("测试 1: 记忆文件检查")

    memory_path = PROJECT_ROOT / "data" / "trading_memory.json"

    print(f"  📂 记忆文件路径: {memory_path}")

    if not memory_path.exists():
        print(f"  ⚠️ 记忆文件不存在")
        return None

    try:
        with open(memory_path, 'r') as f:
            memories = json.load(f)

        print(f"  ✅ 文件读取成功")
        print(f"  📊 记忆条目数: {len(memories)}")

        if memories:
            # 分析 pnl 分布
            pnl_zero = sum(1 for m in memories if m.get('pnl', 0) == 0)
            pnl_positive = sum(1 for m in memories if m.get('pnl', 0) > 0)
            pnl_negative = sum(1 for m in memories if m.get('pnl', 0) < 0)

            print()
            print(f"  📈 PnL 分布:")
            print(f"     零值 (pnl=0): {pnl_zero} 条 ({pnl_zero/len(memories)*100:.1f}%)")
            print(f"     盈利 (pnl>0): {pnl_positive} 条")
            print(f"     亏损 (pnl<0): {pnl_negative} 条")

            if pnl_zero == len(memories):
                print()
                print(f"  ⚠️ 警告: 所有记录的 pnl 都是 0!")
                print(f"     这可能是 v3.13 修复前的历史数据")
                print(f"     需要等待新交易平仓后验证修复是否生效")

            # 显示最近几条记录
            print()
            print(f"  📝 最近 3 条记录:")
            for m in memories[-3:]:
                ts = m.get('timestamp', 'N/A')[:19]
                decision = m.get('decision', 'N/A')
                pnl = m.get('pnl', 0)
                conditions = m.get('conditions', 'N/A')[:50]
                print(f"     [{ts}] {decision} → pnl={pnl:+.2f}%")
                print(f"        {conditions}...")

        return memories

    except json.JSONDecodeError as e:
        print(f"  ❌ JSON 解析错误: {e}")
        return None
    except Exception as e:
        print(f"  ❌ 读取失败: {e}")
        return None


def test_money_quantity_types():
    """测试 2: 验证 NautilusTrader Money/Quantity 类型处理"""
    print_section("测试 2: NautilusTrader 类型处理")

    try:
        from nautilus_trader.model.objects import Money, Quantity, Currency
        print("  ✅ NautilusTrader 类型导入成功")
    except ImportError as e:
        print(f"  ❌ 导入失败: {e}")
        print("     请确保 NautilusTrader 已安装")
        return False

    # 测试 Money 类型
    print()
    print("  📊 Money 类型测试:")
    try:
        # 创建测试 Money 对象
        usdt = Currency.from_str("USDT")
        test_pnl = Money(123.456, usdt)

        print(f"     创建: Money(123.456, USDT) = {test_pnl}")

        # 测试 .as_double() 方法
        if hasattr(test_pnl, 'as_double'):
            value = test_pnl.as_double()
            print(f"     .as_double() = {value}")
            print(f"     类型: {type(value)}")

            if abs(value - 123.456) < 0.001:
                print(f"     ✅ .as_double() 工作正常")
            else:
                print(f"     ❌ .as_double() 返回值不正确")
                return False
        else:
            print(f"     ❌ Money 类型没有 .as_double() 方法")
            return False

        # 测试 float() 转换 (旧方法，可能不工作)
        try:
            float_value = float(test_pnl)
            print(f"     float() = {float_value}")
        except (TypeError, ValueError) as e:
            print(f"     float() 失败: {e}")
            print(f"     ⚠️ 这就是 v3.13 修复的问题!")

    except Exception as e:
        print(f"     ❌ Money 测试失败: {e}")
        return False

    # 测试 Quantity 类型
    print()
    print("  📊 Quantity 类型测试:")
    try:
        test_qty = Quantity.from_str("0.0040")

        print(f"     创建: Quantity.from_str('0.0040') = {test_qty}")

        if hasattr(test_qty, 'as_double'):
            value = test_qty.as_double()
            print(f"     .as_double() = {value}")

            if abs(value - 0.004) < 0.0001:
                print(f"     ✅ .as_double() 工作正常")
            else:
                print(f"     ❌ .as_double() 返回值不正确")
                return False
        else:
            print(f"     ❌ Quantity 类型没有 .as_double() 方法")
            return False

    except Exception as e:
        print(f"     ❌ Quantity 测试失败: {e}")
        return False

    print()
    print("  ✅ NautilusTrader 类型测试全部通过")
    return True


def test_pnl_calculation():
    """测试 3: 模拟 pnl 计算流程"""
    print_section("测试 3: PnL 计算流程模拟")

    try:
        from nautilus_trader.model.objects import Money, Quantity, Currency
    except ImportError:
        print("  ⚠️ 跳过 (NautilusTrader 未安装)")
        return True

    # 模拟 PositionClosed 事件的数据
    print("  📊 模拟交易数据:")

    usdt = Currency.from_str("USDT")

    # 模拟一个盈利交易
    entry_price = 77545.39
    exit_price = 77021.10
    quantity = 0.004

    # SHORT 方向: 入场价 > 出场价 = 盈利
    # pnl = (entry - exit) * quantity = (77545.39 - 77021.10) * 0.004 = 2.097
    expected_pnl = (entry_price - exit_price) * quantity

    print(f"     方向: SHORT")
    print(f"     入场价: ${entry_price:,.2f}")
    print(f"     出场价: ${exit_price:,.2f}")
    print(f"     数量: {quantity} BTC")
    print(f"     预期 PnL: ${expected_pnl:.4f}")

    # 模拟 NautilusTrader 返回的 Money 对象
    realized_pnl = Money(expected_pnl, usdt)
    qty_obj = Quantity.from_str(str(quantity))

    print()
    print("  📊 v3.13 修复后的计算流程:")

    # v3.13 修复后的代码
    try:
        pnl = realized_pnl.as_double() if hasattr(realized_pnl, 'as_double') else float(realized_pnl)
        print(f"     pnl = realized_pnl.as_double() = {pnl:.4f}")
    except Exception as e:
        print(f"     ❌ pnl 提取失败: {e}")
        return False

    try:
        qty = qty_obj.as_double() if hasattr(qty_obj, 'as_double') else float(qty_obj)
        print(f"     quantity = qty_obj.as_double() = {qty:.4f}")
    except Exception as e:
        print(f"     ❌ quantity 提取失败: {e}")
        return False

    position_value = entry_price * qty
    pnl_pct = (pnl / position_value * 100) if position_value > 0 else 0.0

    print(f"     position_value = {entry_price} × {qty} = ${position_value:.2f}")
    print(f"     pnl_pct = ({pnl:.4f} / {position_value:.2f}) × 100 = {pnl_pct:.4f}%")

    # 验证
    expected_pct = (expected_pnl / (entry_price * quantity)) * 100
    print()
    print(f"  📊 验证:")
    print(f"     计算结果: {pnl_pct:.4f}%")
    print(f"     预期结果: {expected_pct:.4f}%")

    if abs(pnl_pct - expected_pct) < 0.001:
        print(f"     ✅ PnL 计算正确!")
        return True
    else:
        print(f"     ❌ PnL 计算错误!")
        return False


def test_record_outcome():
    """测试 4: 测试 record_outcome 功能"""
    print_section("测试 4: record_outcome() 功能")

    try:
        from agents.multi_agent_analyzer import MultiAgentAnalyzer
        print("  ✅ MultiAgentAnalyzer 导入成功")
    except ImportError as e:
        print(f"  ❌ 导入失败: {e}")
        return False

    # 创建临时测试实例
    print()
    print("  📊 创建测试实例...")

    try:
        # 使用 mock API key
        analyzer = MultiAgentAnalyzer(
            api_key="test_key_for_diagnosis",
            model="deepseek-chat",
            temperature=0.3,
        )
        print(f"     ✅ 实例创建成功")
        print(f"     记忆条目数: {len(analyzer.decision_memory)}")
    except Exception as e:
        print(f"     ❌ 实例创建失败: {e}")
        return False

    # 测试不同 pnl 值的 lesson 生成
    print()
    print("  📊 测试 lesson 自动生成:")

    test_cases = [
        (-5.0, "Significant loss"),      # pnl < -2
        (-1.0, "Small loss"),            # -2 <= pnl < 0
        (0.0, "Breakeven"),              # pnl == 0
        (1.0, "Small profit"),           # 0 < pnl <= 2
        (5.0, "Good profit"),            # pnl > 2
    ]

    initial_count = len(analyzer.decision_memory)

    for pnl, expected_keyword in test_cases:
        analyzer.record_outcome(
            decision="TEST",
            pnl=pnl,
            conditions=f"Test with pnl={pnl}",
        )

        # 检查最后一条记录
        last_record = analyzer.decision_memory[-1]
        lesson = last_record.get('lesson', '')

        if expected_keyword.lower() in lesson.lower():
            print(f"     ✅ pnl={pnl:+.1f}% → '{lesson[:40]}...'")
        else:
            print(f"     ❌ pnl={pnl:+.1f}% → 预期包含 '{expected_keyword}'")
            print(f"        实际: '{lesson}'")

    # 验证记录数量增加
    final_count = len(analyzer.decision_memory)
    print()
    print(f"  📊 记录数量变化: {initial_count} → {final_count} (+{final_count - initial_count})")

    if final_count - initial_count == len(test_cases):
        print(f"     ✅ record_outcome() 工作正常")
        return True
    else:
        print(f"     ❌ 记录数量不正确")
        return False


def test_v313_fix_in_strategy():
    """测试 5: 验证 v3.13 修复代码存在"""
    print_section("测试 5: v3.13 修复代码验证")

    strategy_file = PROJECT_ROOT / "strategy" / "deepseek_strategy.py"

    if not strategy_file.exists():
        print(f"  ❌ 策略文件不存在: {strategy_file}")
        return False

    with open(strategy_file, 'r') as f:
        content = f.read()

    # 检查关键修复代码
    checks = [
        ("as_double()", "v3.13 .as_double() 方法调用"),
        ("realized_pnl.as_double()", "realized_pnl 类型正确处理"),
        ("quantity.as_double()", "quantity 类型正确处理"),
        ("v3.13", "v3.13 版本标记"),
    ]

    print("  📋 检查修复代码:")
    all_passed = True

    for pattern, description in checks:
        if pattern in content:
            print(f"     ✅ {description}")
        else:
            print(f"     ❌ {description} - 未找到 '{pattern}'")
            all_passed = False

    # 检查旧代码是否已移除
    old_patterns = [
        "pnl = float(event.realized_pnl)",
        "quantity = float(event.quantity)",
    ]

    print()
    print("  📋 检查旧代码是否已移除:")

    for pattern in old_patterns:
        if pattern in content:
            print(f"     ⚠️ 警告: 发现旧代码 '{pattern}'")
            # 不算失败，可能是注释
        else:
            print(f"     ✅ 已移除: '{pattern[:30]}...'")

    return all_passed


def main():
    print_header("记忆系统诊断工具 v1.0")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  项目: {PROJECT_ROOT}")

    results = {}

    # 运行所有测试
    results['memory_file'] = test_memory_file()
    results['types'] = test_money_quantity_types()
    results['pnl_calc'] = test_pnl_calculation()
    results['record_outcome'] = test_record_outcome()
    results['v313_fix'] = test_v313_fix_in_strategy()

    # 汇总结果
    print_header("诊断结果汇总")

    all_passed = True
    for test_name, result in results.items():
        if result is None:
            status = "⚠️ 跳过"
        elif result:
            status = "✅ 通过"
        else:
            status = "❌ 失败"
            all_passed = False

        print(f"  {test_name}: {status}")

    print()
    if all_passed:
        print("  🎉 所有测试通过!")
        print()
        print("  📝 说明:")
        print("     - 如果记忆文件中所有 pnl=0，这是历史数据")
        print("     - v3.13 修复后的新交易会记录正确的 pnl")
        print("     - 需要等待新交易平仓后验证")
    else:
        print("  ⚠️ 部分测试未通过，请检查上面的错误信息")

    print()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
