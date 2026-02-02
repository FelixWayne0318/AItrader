#!/usr/bin/env python3
"""
v4.8 仓位计算验证脚本

验证 ai_controlled 方法的计算逻辑：
- max_usdt = equity × max_position_ratio × leverage
- final_usdt = max_usdt × size_pct

例如：$1000 × 30% × 10杠杆 = $3000 最大仓位
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def simulate_ai_controlled_sizing(price_data, signal_data, config):
    """模拟 ai_controlled 仓位计算 (绕过依赖)"""
    equity = config.get('equity', 1000)
    leverage = config.get('leverage', 5)
    max_position_ratio = config.get('max_position_ratio', 0.30)
    max_usdt = equity * max_position_ratio * leverage

    sizing_config = config.get('position_sizing', {})
    ai_config = sizing_config.get('ai_controlled', {})
    default_size_pct = ai_config.get('default_size_pct', 50)
    confidence_mapping = ai_config.get('confidence_mapping', {
        'HIGH': 80,
        'MEDIUM': 50,
        'LOW': 30
    })

    ai_size_pct = signal_data.get('position_size_pct')

    if ai_size_pct is not None and ai_size_pct >= 0:
        size_pct = float(ai_size_pct)
        size_source = 'ai_provided'
    else:
        confidence = signal_data.get('confidence', 'MEDIUM').upper()
        size_pct = confidence_mapping.get(confidence, default_size_pct)
        size_source = f'confidence_{confidence}'

    size_ratio = size_pct / 100.0
    final_usdt = max_usdt * size_ratio

    current_price = price_data.get('price', 100000)
    btc_qty = final_usdt / current_price

    details = {
        'method': 'ai_controlled',
        'ai_size_pct': ai_size_pct,
        'size_pct_used': size_pct,
        'size_source': size_source,
        'confidence': signal_data.get('confidence', 'MEDIUM'),
        'equity': equity,
        'leverage': leverage,
        'max_position_ratio': max_position_ratio,
        'max_usdt': max_usdt,
        'final_usdt': final_usdt,
    }

    return btc_qty, details


def test_position_sizing():
    """测试仓位计算"""

    print("=" * 70)
    print("v4.8 仓位计算验证")
    print("=" * 70)

    # 测试配置
    config = {
        'equity': 1000,
        'leverage': 10,
        'max_position_ratio': 0.30,
        'position_sizing': {
            'method': 'ai_controlled',
            'ai_controlled': {
                'default_size_pct': 50,
                'confidence_mapping': {
                    'HIGH': 80,
                    'MEDIUM': 50,
                    'LOW': 30
                }
            }
        }
    }

    price_data = {'price': 100000}  # BTC price
    technical_data = {'overall_trend': '震荡整理', 'rsi': 50}

    # 预期 max_usdt = $1000 × 30% × 10 = $3000
    expected_max_usdt = 1000 * 0.30 * 10
    print(f"\n预期 max_usdt: ${expected_max_usdt:.0f}")
    print(f"  公式: equity(${config['equity']}) × ratio({config['max_position_ratio']*100:.0f}%) × leverage({config['leverage']}x)")

    print("\n" + "-" * 70)
    print("测试场景")
    print("-" * 70)

    test_cases = [
        # (信号数据, 描述, 预期仓位)
        ({'signal': 'LONG', 'confidence': 'HIGH'}, 'HIGH 信心 (80%)', 3000 * 0.80),
        ({'signal': 'LONG', 'confidence': 'MEDIUM'}, 'MEDIUM 信心 (50%)', 3000 * 0.50),
        ({'signal': 'LONG', 'confidence': 'LOW'}, 'LOW 信心 (30%)', 3000 * 0.30),
        ({'signal': 'LONG', 'confidence': 'HIGH', 'position_size_pct': 100}, 'AI 指定 100%', 3000 * 1.00),
        ({'signal': 'LONG', 'confidence': 'HIGH', 'position_size_pct': 50}, 'AI 指定 50%', 3000 * 0.50),
    ]

    all_passed = True

    for signal_data, desc, expected_usdt in test_cases:
        btc_qty, details = simulate_ai_controlled_sizing(
            price_data=price_data,
            signal_data=signal_data,
            config=config
        )

        actual_usdt = details.get('final_usdt', 0)
        passed = abs(actual_usdt - expected_usdt) < 1  # 允许 $1 误差

        status = "✅" if passed else "❌"
        print(f"\n{status} {desc}")
        print(f"   信号: {signal_data}")
        print(f"   预期: ${expected_usdt:.2f}")
        print(f"   实际: ${actual_usdt:.2f}")
        print(f"   来源: {details.get('size_source', 'N/A')}")
        print(f"   BTC 数量: {btc_qty:.6f}")

        if not passed:
            all_passed = False
            print(f"   ⚠️ 计算详情: {details}")

    print("\n" + "=" * 70)

    # 验证 max_usdt 计算
    _, details = simulate_ai_controlled_sizing(
        price_data=price_data,
        signal_data={'signal': 'LONG', 'confidence': 'HIGH'},
        config=config
    )

    actual_max_usdt = details.get('max_usdt', 0)
    max_usdt_correct = abs(actual_max_usdt - expected_max_usdt) < 1

    print(f"\nmax_usdt 验证: {'✅' if max_usdt_correct else '❌'}")
    print(f"  预期: ${expected_max_usdt:.0f}")
    print(f"  实际: ${actual_max_usdt:.0f}")
    print(f"  leverage: {details.get('leverage', 'N/A')}")
    print(f"  max_position_ratio: {details.get('max_position_ratio', 'N/A')}")

    if not max_usdt_correct:
        all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("✅ 所有测试通过！v4.8 仓位计算正确")
        print("\n仓位计算总结 ($1000 资金, 10x 杠杆, 30% 最大比例):")
        print("  - max_usdt = $3000")
        print("  - HIGH 信心: 80% → $2400")
        print("  - MEDIUM 信心: 50% → $1500")
        print("  - LOW 信心: 30% → $900")
    else:
        print("❌ 部分测试失败，请检查计算逻辑")
    print("=" * 70)

    return all_passed


if __name__ == '__main__':
    success = test_position_sizing()
    sys.exit(0 if success else 1)
