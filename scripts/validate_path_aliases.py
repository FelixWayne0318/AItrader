#!/usr/bin/env python3
"""
PATH_ALIASES 验证脚本

验证 ConfigManager 的路径别名功能是否正确工作，确保旧路径和新路径都能访问相同的值。

Usage:
    python3 scripts/validate_path_aliases.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.config_manager import ConfigManager


def test_path_alias(config: ConfigManager, old_path: tuple, new_path: tuple, description: str):
    """测试单个路径别名"""
    old_value = config.get(*old_path)
    new_value = config.get(*new_path)

    if old_value == new_value:
        print(f"✅ {description}")
        print(f"   Old: {'.'.join(old_path)} = {old_value}")
        print(f"   New: {'.'.join(new_path)} = {new_value}")
        return True
    else:
        print(f"❌ {description}")
        print(f"   Old: {'.'.join(old_path)} = {old_value}")
        print(f"   New: {'.'.join(new_path)} = {new_value}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("  PATH_ALIASES 验证")
    print("=" * 60)
    print()

    # 加载配置
    try:
        config = ConfigManager(env='production')
        config.load()
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        return 1

    print("配置加载成功\n")

    # 测试路径别名映射
    test_cases = [
        # (旧路径, 新路径, 描述)
        (('strategy', 'instrument_id'), ('trading', 'instrument_id'), '交易对配置'),
        (('strategy', 'bar_type'), ('trading', 'bar_type'), 'K线类型配置'),
        (('strategy', 'equity'), ('capital', 'equity'), '资金配置'),
        (('strategy', 'leverage'), ('capital', 'leverage'), '杠杆配置'),
        (('strategy', 'use_real_balance_as_equity'), ('capital', 'use_real_balance_as_equity'), '真实余额配置'),
        (('strategy', 'position_management', 'base_usdt_amount'), ('position', 'base_usdt_amount'), '基础仓位'),
        (('strategy', 'position_management', 'max_position_ratio'), ('position', 'max_position_ratio'), '最大仓位比例'),
        (('strategy', 'indicators', 'rsi_period'), ('indicators', 'rsi_period'), 'RSI 周期'),
        (('strategy', 'indicators', 'macd_fast'), ('indicators', 'macd_fast'), 'MACD 快线'),
        (('strategy', 'deepseek', 'temperature'), ('ai', 'deepseek', 'temperature'), 'AI 温度参数'),
        (('strategy', 'deepseek', 'model'), ('ai', 'deepseek', 'model'), 'AI 模型'),
        (('strategy', 'risk', 'rsi_extreme_threshold_upper'), ('risk', 'rsi_extreme_threshold_upper'), 'RSI 超买阈值'),
        (('strategy', 'risk', 'rsi_extreme_threshold_lower'), ('risk', 'rsi_extreme_threshold_lower'), 'RSI 超卖阈值'),
        (('strategy', 'telegram', 'enabled'), ('telegram', 'enabled'), 'Telegram 通知'),
        (('strategy', 'timer_interval_sec'), ('timing', 'timer_interval_sec'), '定时器间隔'),
    ]

    passed = 0
    failed = 0

    for old_path, new_path, description in test_cases:
        if test_path_alias(config, old_path, new_path, description):
            passed += 1
        else:
            failed += 1
        print()

    # 特殊测试: skip_on_divergence 和 use_confidence_fusion
    # 这两个参数可能在 ai.signal.* 或 strategy.risk.* 中
    print("特殊路径测试:")
    print()

    skip_on_divergence = config.get('ai', 'signal', 'skip_on_divergence')
    use_confidence_fusion = config.get('ai', 'signal', 'use_confidence_fusion')

    print(f"✅ skip_on_divergence: {skip_on_divergence}")
    print(f"✅ use_confidence_fusion: {use_confidence_fusion}")
    print()

    # 总结
    print("=" * 60)
    print(f"  总计: {passed + failed} 个测试")
    print(f"  通过: {passed}")
    print(f"  失败: {failed}")
    print("=" * 60)

    if failed > 0:
        print("\n❌ 部分路径别名验证失败，请检查 ConfigManager.PATH_ALIASES")
        return 1
    else:
        print("\n✅ 所有路径别名验证通过")
        return 0


if __name__ == "__main__":
    sys.exit(main())
