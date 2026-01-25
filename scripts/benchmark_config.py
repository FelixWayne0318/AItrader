#!/usr/bin/env python3
"""
配置加载性能基线测试

测试 ConfigManager 的加载性能，确保符合 < 200ms 的性能目标。

Usage:
    python3 scripts/benchmark_config.py
    python3 scripts/benchmark_config.py --iterations 100
"""

import sys
import time
import argparse
from pathlib import Path
import statistics

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.config_manager import ConfigManager


def benchmark_single_load(env: str = 'production') -> float:
    """
    单次配置加载性能测试

    Returns
    -------
    float
        加载耗时 (秒)
    """
    start = time.perf_counter()
    config = ConfigManager(env=env)
    config.load()
    end = time.perf_counter()
    return end - start


def benchmark_cached_access(config: ConfigManager, iterations: int = 1000) -> float:
    """
    缓存访问性能测试

    Returns
    -------
    float
        平均访问耗时 (微秒)
    """
    start = time.perf_counter()
    for _ in range(iterations):
        _ = config.get('capital', 'equity')
        _ = config.get('ai', 'deepseek', 'temperature')
        _ = config.get('risk', 'rsi_extreme_threshold_upper')
    end = time.perf_counter()

    total_time = end - start
    avg_time_per_access = (total_time / (iterations * 3)) * 1_000_000  # 转换为微秒
    return avg_time_per_access


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='ConfigManager 性能基线测试')
    parser.add_argument('--iterations', type=int, default=10,
                        help='配置加载测试次数 (默认 10)')
    args = parser.parse_args()

    print("=" * 60)
    print("  ConfigManager 性能基线测试")
    print("=" * 60)
    print()

    # 测试 1: 首次加载性能
    print("测试 1: 首次配置加载性能")
    print("-" * 60)

    load_times = []
    for i in range(args.iterations):
        elapsed = benchmark_single_load('production')
        load_times.append(elapsed * 1000)  # 转换为毫秒
        print(f"  第 {i+1:2d} 次: {elapsed*1000:.2f} ms")

    avg_load_time = statistics.mean(load_times)
    median_load_time = statistics.median(load_times)
    min_load_time = min(load_times)
    max_load_time = max(load_times)

    print()
    print(f"  平均耗时: {avg_load_time:.2f} ms")
    print(f"  中位数:   {median_load_time:.2f} ms")
    print(f"  最小值:   {min_load_time:.2f} ms")
    print(f"  最大值:   {max_load_time:.2f} ms")
    print()

    # 性能目标检查
    if avg_load_time < 200:
        print(f"✅ 性能达标: {avg_load_time:.2f} ms < 200 ms (目标)")
    else:
        print(f"❌ 性能不达标: {avg_load_time:.2f} ms >= 200 ms (目标)")
    print()

    # 测试 2: 缓存访问性能
    print("测试 2: 配置访问性能 (缓存命中)")
    print("-" * 60)

    config = ConfigManager(env='production')
    config.load()

    avg_access_time = benchmark_cached_access(config, iterations=1000)
    print(f"  平均访问耗时: {avg_access_time:.2f} μs")
    print()

    if avg_access_time < 1.0:
        print(f"✅ 缓存性能优秀: {avg_access_time:.2f} μs < 1 μs")
    else:
        print(f"⚠️  缓存性能一般: {avg_access_time:.2f} μs (建议优化)")
    print()

    # 测试 3: 不同环境加载对比
    print("测试 3: 不同环境配置加载对比")
    print("-" * 60)

    environments = ['production', 'development', 'backtest']
    env_times = {}

    for env in environments:
        elapsed = benchmark_single_load(env)
        env_times[env] = elapsed * 1000
        print(f"  {env:12s}: {elapsed*1000:.2f} ms")

    print()

    # 测试 4: 路径别名性能影响
    print("测试 4: 路径别名性能影响")
    print("-" * 60)

    # 测试新路径访问
    start = time.perf_counter()
    for _ in range(1000):
        _ = config.get('capital', 'equity')
    new_path_time = (time.perf_counter() - start) / 1000 * 1_000_000

    # 测试旧路径访问 (通过别名)
    start = time.perf_counter()
    for _ in range(1000):
        _ = config.get('strategy', 'equity')
    old_path_time = (time.perf_counter() - start) / 1000 * 1_000_000

    print(f"  新路径访问: {new_path_time:.2f} μs")
    print(f"  旧路径访问: {old_path_time:.2f} μs (通过别名)")
    print(f"  性能差异:   {old_path_time - new_path_time:.2f} μs")
    print()

    if old_path_time - new_path_time < 0.5:
        print("✅ 路径别名性能影响可忽略")
    else:
        print("⚠️  路径别名有一定性能开销 (建议迁移到新路径)")
    print()

    # 总结
    print("=" * 60)
    print("  性能测试总结")
    print("=" * 60)
    print()
    print(f"  配置加载平均耗时: {avg_load_time:.2f} ms")
    print(f"  性能目标 (< 200ms): {'✅ 达标' if avg_load_time < 200 else '❌ 不达标'}")
    print(f"  配置访问平均耗时: {avg_access_time:.2f} μs")
    print(f"  缓存命中性能:      {'✅ 优秀' if avg_access_time < 1.0 else '⚠️  一般'}")
    print()

    # 建议
    if avg_load_time >= 200:
        print("建议:")
        print("  - 检查 YAML 文件大小")
        print("  - 减少验证规则数量")
        print("  - 考虑实现配置缓存")
        print()

    return 0 if avg_load_time < 200 else 1


if __name__ == "__main__":
    sys.exit(main())
