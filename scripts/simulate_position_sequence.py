#!/usr/bin/env python3
"""
v4.8 仓位序列模拟

模拟实际交易中的首仓和历次加仓仓位大小
"""

def simulate_trading_sequence():
    """模拟交易序列"""

    print("=" * 70)
    print("v4.8 仓位序列模拟 (累加模式)")
    print("=" * 70)

    # 配置参数
    config = {
        'equity': 1000,           # $1000 资金
        'leverage': 10,           # 10x 杠杆 (从币安同步)
        'max_position_ratio': 0.30,  # 30% 最大仓位比例
        'confidence_mapping': {
            'HIGH': 80,
            'MEDIUM': 50,
            'LOW': 30
        }
    }

    btc_price = 100000  # BTC 价格

    # 计算关键参数
    max_usdt = config['equity'] * config['max_position_ratio'] * config['leverage']

    print(f"\n📊 配置参数:")
    print(f"   资金 (equity): ${config['equity']}")
    print(f"   杠杆 (leverage): {config['leverage']}x")
    print(f"   最大仓位比例: {config['max_position_ratio']*100:.0f}%")
    print(f"   BTC 价格: ${btc_price:,}")
    print(f"\n   🎯 max_usdt = ${config['equity']} × {config['max_position_ratio']*100:.0f}% × {config['leverage']}x = ${max_usdt:,.0f}")

    print("\n" + "=" * 70)
    print("模拟场景 1: 连续 MEDIUM 信心加仓")
    print("=" * 70)

    current_position_usdt = 0
    current_position_btc = 0
    trade_count = 0

    # 模拟 5 次交易
    for i in range(5):
        confidence = 'MEDIUM'
        size_pct = config['confidence_mapping'][confidence]

        # 本次计算的仓位
        calculated_usdt = max_usdt * (size_pct / 100)
        calculated_btc = calculated_usdt / btc_price

        # 累加模式：目标 = 当前 + 计算量
        target_usdt = current_position_usdt + calculated_usdt
        target_btc = current_position_btc + calculated_btc

        # 检查是否超过上限
        if target_usdt > max_usdt:
            # 只加到上限
            actual_add_usdt = max_usdt - current_position_usdt
            actual_add_btc = actual_add_usdt / btc_price

            if actual_add_usdt <= 0:
                print(f"\n❌ 第 {i+1} 次: 已达上限，无法加仓")
                print(f"   当前持仓: ${current_position_usdt:,.0f} ({current_position_btc:.6f} BTC)")
                print(f"   max_usdt: ${max_usdt:,.0f}")
                continue

            print(f"\n⚠️ 第 {i+1} 次: 加仓受限 (达到上限)")
            print(f"   计算量: ${calculated_usdt:,.0f} → 实际: ${actual_add_usdt:,.0f}")
        else:
            actual_add_usdt = calculated_usdt
            actual_add_btc = calculated_btc

            trade_count += 1
            action = "首仓" if i == 0 else f"第 {i} 次加仓"
            print(f"\n✅ {action} ({confidence} 信心 {size_pct}%)")
            print(f"   本次: ${actual_add_usdt:,.0f} ({actual_add_btc:.6f} BTC)")

        # 更新持仓
        current_position_usdt += actual_add_usdt
        current_position_btc += actual_add_btc

        print(f"   累计持仓: ${current_position_usdt:,.0f} ({current_position_btc:.6f} BTC)")
        print(f"   占 max_usdt: {current_position_usdt/max_usdt*100:.1f}%")

    print("\n" + "=" * 70)
    print("模拟场景 2: 不同信心级别的加仓")
    print("=" * 70)

    current_position_usdt = 0
    current_position_btc = 0

    # 场景：LOW → MEDIUM → HIGH
    signals = [
        ('LOW', '首仓'),
        ('MEDIUM', '第 1 次加仓'),
        ('HIGH', '第 2 次加仓'),
        ('HIGH', '第 3 次加仓'),
    ]

    for confidence, action in signals:
        size_pct = config['confidence_mapping'][confidence]
        calculated_usdt = max_usdt * (size_pct / 100)
        calculated_btc = calculated_usdt / btc_price

        target_usdt = current_position_usdt + calculated_usdt

        if target_usdt > max_usdt:
            actual_add_usdt = max(0, max_usdt - current_position_usdt)
            actual_add_btc = actual_add_usdt / btc_price

            if actual_add_usdt <= 0:
                print(f"\n❌ {action}: 已达上限，无法加仓")
                continue

            print(f"\n⚠️ {action} ({confidence} {size_pct}%) - 受限")
            print(f"   计算量: ${calculated_usdt:,.0f} → 实际: ${actual_add_usdt:,.0f}")
        else:
            actual_add_usdt = calculated_usdt
            actual_add_btc = calculated_btc
            print(f"\n✅ {action} ({confidence} 信心 {size_pct}%)")
            print(f"   本次: ${actual_add_usdt:,.0f} ({actual_add_btc:.6f} BTC)")

        current_position_usdt += actual_add_usdt
        current_position_btc += actual_add_btc

        print(f"   累计持仓: ${current_position_usdt:,.0f} ({current_position_btc:.6f} BTC)")
        print(f"   占 max_usdt: {current_position_usdt/max_usdt*100:.1f}%")

    print("\n" + "=" * 70)
    print("📋 仓位大小总结")
    print("=" * 70)
    print(f"\n配置: $1000 资金, 10x 杠杆, 30% 最大比例")
    print(f"max_usdt = $3000")
    print(f"\n单次仓位计算:")
    print(f"  HIGH (80%):   $3000 × 80% = $2,400 (0.024 BTC)")
    print(f"  MEDIUM (50%): $3000 × 50% = $1,500 (0.015 BTC)")
    print(f"  LOW (30%):    $3000 × 30% = $900   (0.009 BTC)")
    print(f"\n累加模式规则:")
    print(f"  - 每次信号计算新的加仓量")
    print(f"  - 累计持仓不超过 max_usdt ($3000)")
    print(f"  - 达到上限后停止加仓")


if __name__ == '__main__':
    simulate_trading_sequence()
