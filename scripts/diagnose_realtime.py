#!/usr/bin/env python3
"""
实盘信号诊断脚本 v9.0 (TradingAgents 架构)

关键特性:
1. 调用 main_live.py 中的 get_strategy_config() 获取真实配置
2. 使用与实盘完全相同的组件初始化参数
3. 使用 TradingAgents 层级决策架构，与 deepseek_strategy.py 100% 一致
4. 检查 Binance 真实持仓
5. 模拟完整的 _execute_trade 流程（包括完整的 SL/TP 验证逻辑）
6. 输出实盘环境下会产生的真实结果
7. 检查可能导致不能下单的关键配置 (v9.0 新增)

当前架构 (TradingAgents Judge-based Decision):
- Phase 1: Bull/Bear 辩论 (2 AI calls)
- Phase 2: Judge 决策 (1 AI call with optimized prompt)
- Phase 3: Risk 评估 (1 AI call)
- Judge 决策即最终决策，不需要信号合并
- 参考: TradingAgents (UCLA/MIT) https://github.com/TauricResearch/TradingAgents

历史更新:
v9.0:
- 添加关键配置检查 (load_all, reconciliation, SL/TP 字段名)
- 检测可能导致不能下单的配置问题

v8.0:
- 添加完整的 Bracket Order SL/TP 验证逻辑（与实盘100%一致）
- 添加 --summary 选项用于快速诊断
- 模拟技术分析回退逻辑

v7.0:
- 统一架构命名为 "TradingAgents"，移除"方案A/B"混淆
- 更新注释以反映当前架构状态

v6.0:
- 实现 TradingAgents 层级决策架构
- Judge 决策作为唯一决策者

v5.0:
- 添加 Binance 真实持仓检查
- 添加 _manage_existing_position 逻辑模拟
- 添加仓位为0检查
- 添加 Telegram/交易执行流程说明

使用方法:
    cd /home/linuxuser/nautilus_AItrader
    source venv/bin/activate
    python3 diagnose_realtime.py              # 完整诊断
    python3 diagnose_realtime.py --summary    # 快速诊断（仅显示关键结果）
"""

import argparse
import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional, Tuple

# 解析命令行参数
parser = argparse.ArgumentParser(description='实盘信号诊断工具 v9.0')
parser.add_argument('--summary', action='store_true',
                   help='仅显示关键结果，跳过详细分析')
args = parser.parse_args()

# 全局标志
SUMMARY_MODE = args.summary

# 分析阈值常量 (避免魔法数字)
BB_OVERBOUGHT_THRESHOLD = 80  # 布林带上轨接近阈值
BB_OVERSOLD_THRESHOLD = 20    # 布林带下轨接近阈值
LS_RATIO_EXTREME_BULLISH = 2.0  # 多空比极度看多阈值
LS_RATIO_BULLISH = 1.5          # 多空比偏多阈值
LS_RATIO_EXTREME_BEARISH = 0.5  # 多空比极度看空阈值
LS_RATIO_BEARISH = 0.7          # 多空比偏空阈值

def print_wrapped(text: str, indent: str = "    ", width: int = 80) -> None:
    """打印自动换行的文本"""
    for i in range(0, len(text), width):
        print(f"{indent}{text[i:i+width]}")


def check_critical_config() -> Tuple[list, list]:
    """
    检查可能导致不能下单的关键配置 (v9.0 新增)

    检查项:
    1. main_live.py: load_all=True (instrument 初始化)
    2. main_live.py: reconciliation=True (仓位对账)
    3. deepseek_strategy.py: SL/TP 字段名正确使用

    Returns:
        (issues, warnings): 问题列表和警告列表
    """
    import re

    issues = []  # 严重问题
    warnings = []  # 警告

    project_root = Path(__file__).parent.parent

    # ==========================================================================
    # 检查 1: main_live.py 中的 load_all 配置
    # ==========================================================================
    main_live_path = project_root / "main_live.py"
    if main_live_path.exists():
        with open(main_live_path, 'r', encoding='utf-8') as f:
            main_live_content = f.read()

        # 检查 load_all 设置
        # 匹配 load_all=True 或 load_all=False
        load_all_matches = re.findall(r'load_all\s*=\s*(True|False)', main_live_content)

        if not load_all_matches:
            warnings.append("main_live.py: 未找到 load_all 配置")
        elif 'False' in load_all_matches:
            issues.append(
                "❌ main_live.py: load_all=False\n"
                "   → 可能导致 instrument 初始化不完整，订单无法执行\n"
                "   → 修复: 改为 load_all=True"
            )
        else:
            # 所有都是 True
            pass  # 正常

        # 检查 reconciliation 设置
        reconciliation_matches = re.findall(r'reconciliation\s*=\s*(True|False)', main_live_content)

        if not reconciliation_matches:
            warnings.append("main_live.py: 未找到 reconciliation 配置")
        elif 'False' in reconciliation_matches:
            issues.append(
                "❌ main_live.py: reconciliation=False\n"
                "   → 仓位不同步，可能导致订单管理异常\n"
                "   → 修复: 改为 reconciliation=True"
            )
    else:
        issues.append("❌ main_live.py 文件不存在!")

    # ==========================================================================
    # 检查 2: deepseek_strategy.py 中的 SL/TP 字段名使用
    # ==========================================================================
    strategy_path = project_root / "strategy" / "deepseek_strategy.py"
    if strategy_path.exists():
        with open(strategy_path, 'r', encoding='utf-8') as f:
            strategy_content = f.read()

        # 检查是否使用了错误的字段名 stop_loss_multi / take_profit_multi
        if "stop_loss_multi" in strategy_content:
            issues.append(
                "❌ deepseek_strategy.py: 使用了 'stop_loss_multi' 字段名\n"
                "   → MultiAgent 返回的字段名是 'stop_loss'\n"
                "   → 这会导致 SL 值永远为 None\n"
                "   → 修复: 改为 .get('stop_loss')"
            )

        if "take_profit_multi" in strategy_content:
            issues.append(
                "❌ deepseek_strategy.py: 使用了 'take_profit_multi' 字段名\n"
                "   → MultiAgent 返回的字段名是 'take_profit'\n"
                "   → 这会导致 TP 值永远为 None\n"
                "   → 修复: 改为 .get('take_profit')"
            )

        # 检查是否正确使用了字段名
        correct_sl = re.search(r"\.get\(['\"]stop_loss['\"]\)", strategy_content)
        correct_tp = re.search(r"\.get\(['\"]take_profit['\"]\)", strategy_content)

        if not correct_sl:
            warnings.append("deepseek_strategy.py: 未找到 .get('stop_loss') 调用")
        if not correct_tp:
            warnings.append("deepseek_strategy.py: 未找到 .get('take_profit') 调用")
    else:
        warnings.append("deepseek_strategy.py 文件不存在")

    # ==========================================================================
    # 检查 3: trading_logic.py 中的 SL 距离验证常量
    # ==========================================================================
    trading_logic_path = project_root / "strategy" / "trading_logic.py"
    if trading_logic_path.exists():
        with open(trading_logic_path, 'r', encoding='utf-8') as f:
            trading_logic_content = f.read()

        # 检查 SL 距离阈值 (应该在 trading_logic.py 中定义)
        min_sl_match = re.search(r'MIN_SL_DISTANCE_PCT\s*=\s*([\d.]+)', trading_logic_content)
        if not min_sl_match:
            warnings.append(
                "trading_logic.py: 未找到 MIN_SL_DISTANCE_PCT\n"
                "   → SL 距离验证可能不生效"
            )
        else:
            min_sl_pct = float(min_sl_match.group(1))
            if min_sl_pct < 0.01:  # 小于 1%
                warnings.append(
                    f"trading_logic.py: MIN_SL_DISTANCE_PCT={min_sl_pct}\n"
                    f"   → 建议至少设置为 0.01 (1%)"
                )

    # 检查 multi_agent_analyzer.py 是否正确导入共享常量
    analyzer_path = project_root / "agents" / "multi_agent_analyzer.py"
    if analyzer_path.exists():
        with open(analyzer_path, 'r', encoding='utf-8') as f:
            analyzer_content = f.read()

        # 支持单行和多行导入格式
        has_trading_logic_import = "from strategy.trading_logic import" in analyzer_content
        has_min_sl_constant = "MIN_SL_DISTANCE_PCT" in analyzer_content

        if not (has_trading_logic_import and has_min_sl_constant):
            warnings.append(
                "multi_agent_analyzer.py: 未从 trading_logic 导入 MIN_SL_DISTANCE_PCT\n"
                "   → 可能导致 SL 验证不一致"
            )

    # ==========================================================================
    # 检查 4: patches 是否正确应用
    # ==========================================================================
    patches_init = project_root / "patches" / "__init__.py"
    binance_enums = project_root / "patches" / "binance_enums.py"

    if not binance_enums.exists():
        warnings.append("patches/binance_enums.py 不存在 - 可能缺少枚举兼容性补丁")

    return issues, warnings


# =============================================================================
# 关键: 使用与 main_live.py 完全相同的初始化流程
# =============================================================================

# 设置项目路径 (与 main_live.py 相同)
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 应用补丁 (与 main_live.py 相同)
from patches.binance_enums import apply_all_patches
apply_all_patches()

# 加载环境变量 (与 main_live.py 相同)
from dotenv import load_dotenv
env_permanent = Path.home() / ".env.aitrader"
env_local = project_root / ".env"

if env_permanent.exists():
    load_dotenv(env_permanent)
elif env_local.exists():
    load_dotenv(env_local)
else:
    load_dotenv()

mode_str = " (快速模式)" if SUMMARY_MODE else ""
print("=" * 70)
print(f"  实盘信号诊断工具 v9.0 (TradingAgents 架构){mode_str}")
print("=" * 70)
print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
print()

# =============================================================================
# 0. 关键配置检查 (v9.0 新增 - 检测可能导致不能下单的配置问题)
# =============================================================================
print("[0/10] 关键配置检查 (检测可能导致不能下单的问题)...")
print("-" * 70)

config_issues, config_warnings = check_critical_config()

if config_issues:
    print()
    print("  🚨 发现严重问题 (可能导致不能下单):")
    print()
    for issue in config_issues:
        for line in issue.split('\n'):
            print(f"  {line}")
        print()

if config_warnings:
    print("  ⚠️ 警告:")
    for warning in config_warnings:
        for line in warning.split('\n'):
            print(f"     {line}")
    print()

if not config_issues and not config_warnings:
    print("  ✅ load_all=True")
    print("  ✅ reconciliation=True")
    print("  ✅ SL/TP 字段名正确")
    print("  ✅ 所有关键配置检查通过")

if config_issues:
    print("  " + "=" * 66)
    print("  ⛔ 发现严重配置问题! 请先修复上述问题再运行实盘交易。")
    print("  " + "=" * 66)
    print()
    response = input("  是否继续诊断? (y/N): ")
    if response.lower() != 'y':
        print("  退出诊断。")
        sys.exit(1)

print()

# =============================================================================
# 1. 从 main_live.py 导入并获取真实配置
# =============================================================================
if not SUMMARY_MODE:
    print("[1/10] 从 main_live.py 加载真实配置...")

try:
    from main_live import get_strategy_config, load_yaml_config

    # 获取与实盘完全相同的配置
    strategy_config = get_strategy_config()
    yaml_config = load_yaml_config()

    if not SUMMARY_MODE:
        print(f"  instrument_id: {strategy_config.instrument_id}")
        print(f"  bar_type: {strategy_config.bar_type}")
        print(f"  equity: ${strategy_config.equity}")
        print(f"  base_usdt_amount: ${strategy_config.base_usdt_amount}")
        print(f"  leverage: {strategy_config.leverage}x")
        print(f"  min_confidence_to_trade: {strategy_config.min_confidence_to_trade}")
        timer_sec = strategy_config.timer_interval_sec
        timer_min = timer_sec / 60
        print(f"  timer_interval_sec: {timer_sec}s ({timer_min:.1f}分钟)")
        print(f"  sma_periods: {strategy_config.sma_periods}")
        print(f"  rsi_period: {strategy_config.rsi_period}")
        print(f"  macd_fast/slow: {strategy_config.macd_fast}/{strategy_config.macd_slow}")
        print(f"  debate_rounds: {strategy_config.debate_rounds}")
        print("  ✅ 配置加载成功 (与实盘完全一致)")
        print()
        print(f"  ⏰ 注意: 实盘每 {timer_min:.0f} 分钟分析一次")
        print(f"     如果刚启动服务，需等待第一个周期触发")
    else:
        timer_sec = strategy_config.timer_interval_sec
        timer_min = timer_sec / 60
except (ImportError, AttributeError, KeyError, ValueError) as e:
    print(f"  ❌ 配置加载失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
except (KeyboardInterrupt, SystemExit):
    print("\n  用户中断")
    raise

print()

# =============================================================================
# 2. 获取市场数据 (与实盘相同的数据源)
# =============================================================================
print("[2/10] 获取市场数据 (Binance Futures)...")

import requests

# 从 bar_type 解析时间周期 (注意: 必须先检查更长的字符串)
bar_type_str = strategy_config.bar_type
# 按照从长到短的顺序检查，避免子字符串匹配错误
if "15-MINUTE" in bar_type_str:
    interval = "15m"
elif "5-MINUTE" in bar_type_str:
    interval = "5m"
elif "1-MINUTE" in bar_type_str:
    interval = "1m"
elif "4-HOUR" in bar_type_str:
    interval = "4h"
elif "1-HOUR" in bar_type_str:
    interval = "1h"
elif "1-DAY" in bar_type_str:
    interval = "1d"
else:
    interval = "15m"

symbol = "BTCUSDT"
limit = 100

try:
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url, timeout=10)
    klines_raw = response.json()

    if isinstance(klines_raw, list) and len(klines_raw) > 0:
        print(f"  交易对: {symbol}")
        print(f"  时间周期: {interval} (从 bar_type 解析)")
        print(f"  K线数量: {len(klines_raw)}")

        latest = klines_raw[-1]
        current_price = float(latest[4])
        print(f"  最新价格: ${current_price:,.2f}")
        print("  ✅ 市场数据获取成功")
    else:
        print(f"  ❌ K线数据异常: {klines_raw}")
        sys.exit(1)
except (requests.RequestException, ValueError, KeyError) as e:
    print(f"  ❌ 获取市场数据失败: {e}")
    sys.exit(1)
except (KeyboardInterrupt, SystemExit):
    print("\n  用户中断")
    raise

print()

# =============================================================================
# 3. 使用真实配置初始化 TechnicalIndicatorManager
# =============================================================================
print("[3/10] 初始化 TechnicalIndicatorManager (使用实盘配置)...")

try:
    from indicators.technical_manager import TechnicalIndicatorManager

    # 使用与 deepseek_strategy.py __init__ 完全相同的参数
    indicator_manager = TechnicalIndicatorManager(
        sma_periods=list(strategy_config.sma_periods),  # 从配置读取
        ema_periods=[strategy_config.macd_fast, strategy_config.macd_slow],  # MACD 周期
        rsi_period=strategy_config.rsi_period,
        macd_fast=strategy_config.macd_fast,
        macd_slow=strategy_config.macd_slow,
        macd_signal=9,  # 固定值
        bb_period=strategy_config.bb_period,
        bb_std=strategy_config.bb_std,
        volume_ma_period=20,
        support_resistance_lookback=20,
    )

    print(f"  sma_periods: {list(strategy_config.sma_periods)}")
    print(f"  ema_periods: [{strategy_config.macd_fast}, {strategy_config.macd_slow}]")
    print(f"  rsi_period: {strategy_config.rsi_period}")
    print(f"  macd: {strategy_config.macd_fast}/{strategy_config.macd_slow}/9")
    print(f"  bb_period: {strategy_config.bb_period}")
    print("  ✅ TechnicalIndicatorManager 初始化成功")

    # 喂入 K 线数据
    for kline in klines_raw:
        class MockBar:
            def __init__(self, o, h, l, c, v, ts):
                self.open = Decimal(str(o))
                self.high = Decimal(str(h))
                self.low = Decimal(str(l))
                self.close = Decimal(str(c))
                self.volume = Decimal(str(v))
                self.ts_init = int(ts)

        bar = MockBar(
            float(kline[1]), float(kline[2]), float(kline[3]),
            float(kline[4]), float(kline[5]), int(kline[0])
        )
        indicator_manager.update(bar)

    # 检查是否初始化完成
    if indicator_manager.is_initialized():
        print(f"  ✅ 指标已初始化 ({len(klines_raw)} 根K线)")
    else:
        print(f"  ⚠️ 指标未完全初始化，可能数据不足")

except (ImportError, AttributeError, TypeError, ValueError) as e:
    print(f"  ❌ TechnicalIndicatorManager 失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
except (KeyboardInterrupt, SystemExit):
    print("\n  用户中断")
    raise

print()

# =============================================================================
# 3.5. 检查 Binance 真实持仓 (与实盘一致)
# =============================================================================
print("[3.5/10] 检查 Binance 真实持仓...")
print("-" * 70)

current_position = None  # 默认无持仓

try:
    from utils.binance_account import BinanceAccountFetcher

    account_fetcher = BinanceAccountFetcher()
    positions = account_fetcher.get_positions(symbol="BTCUSDT")

    if positions:
        pos = positions[0]  # 取第一个 BTCUSDT 持仓
        pos_amt = float(pos.get('positionAmt', 0))
        entry_price = float(pos.get('entryPrice', 0))
        unrealized_pnl = float(pos.get('unRealizedProfit', 0))

        if pos_amt != 0:
            side = 'long' if pos_amt > 0 else 'short'
            current_position = {
                'side': side,
                'quantity': abs(pos_amt),
                'avg_px': entry_price,
                'unrealized_pnl': unrealized_pnl,
            }
            print(f"  ⚠️ 检测到现有持仓!")
            print(f"     方向: {side.upper()}")
            print(f"     数量: {abs(pos_amt):.4f} BTC")
            print(f"     入场价: ${entry_price:,.2f}")
            print(f"     未实现盈亏: ${unrealized_pnl:,.2f}")

            # 计算盈亏百分比
            if entry_price > 0:
                pnl_pct = (unrealized_pnl / (entry_price * abs(pos_amt))) * 100
                print(f"     盈亏比例: {pnl_pct:+.2f}%")
        else:
            print("  ✅ 无持仓")
    else:
        print("  ✅ 无持仓")

except (ImportError, AttributeError, KeyError, ValueError, requests.RequestException) as e:
    print(f"  ⚠️ 持仓检查失败: {e}")
    print("  → 继续假设无持仓")
except (KeyboardInterrupt, SystemExit):
    print("\n  用户中断")
    raise

print()

# =============================================================================
# 4. 获取技术数据 (与 on_timer 相同)
# =============================================================================
print("[4/10] 获取技术数据 (模拟 on_timer 流程)...")

try:
    technical_data = indicator_manager.get_technical_data(current_price)

    # 显示关键指标
    sma_keys = [k for k in technical_data.keys() if k.startswith('sma_')]
    for key in sorted(sma_keys):
        print(f"  {key.upper()}: ${technical_data[key]:,.2f}")

    ema_keys = [k for k in technical_data.keys() if k.startswith('ema_')]
    for key in sorted(ema_keys):
        print(f"  {key.upper()}: ${technical_data[key]:,.2f}")

    print(f"  RSI: {technical_data.get('rsi', 0):.2f}")
    print(f"  MACD: {technical_data.get('macd', 0):.4f}")
    print(f"  MACD Signal: {technical_data.get('macd_signal', 0):.4f}")
    print(f"  MACD Histogram: {technical_data.get('macd_histogram', 0):.4f}")
    print(f"  BB Upper: ${technical_data.get('bb_upper', 0):,.2f}")
    print(f"  BB Lower: ${technical_data.get('bb_lower', 0):,.2f}")
    print(f"  Support: ${technical_data.get('support', 0):,.2f}")
    print(f"  Resistance: ${technical_data.get('resistance', 0):,.2f}")
    print(f"  Overall Trend: {technical_data.get('overall_trend', 'N/A')}")
    print("  ✅ 技术数据获取成功")

except (AttributeError, KeyError, TypeError, ValueError) as e:
    print(f"  ❌ 技术数据获取失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
except (KeyboardInterrupt, SystemExit):
    print("\n  用户中断")
    raise

print()

# =============================================================================
# 5. 初始化并获取情绪数据 (使用实盘配置)
# =============================================================================
print("[5/10] 获取情绪数据 (使用实盘配置)...")

try:
    from utils.sentiment_client import SentimentDataFetcher

    # 使用与 deepseek_strategy.py on_start 相同的参数
    sentiment_fetcher = SentimentDataFetcher(
        lookback_hours=strategy_config.sentiment_lookback_hours,
        timeframe=strategy_config.sentiment_timeframe,
    )

    print(f"  lookback_hours: {strategy_config.sentiment_lookback_hours}")
    print(f"  timeframe: {strategy_config.sentiment_timeframe}")

    sentiment_data = sentiment_fetcher.fetch()

    if sentiment_data:
        print(f"  Long/Short Ratio: {sentiment_data.get('long_short_ratio', 0):.4f}")
        print(f"  Long Account %: {sentiment_data.get('long_account_pct', 0):.2f}%")
        print(f"  Short Account %: {sentiment_data.get('short_account_pct', 0):.2f}%")
        print(f"  Source: {sentiment_data.get('source', 'N/A')}")
        print("  ✅ 情绪数据获取成功")
    else:
        # 与 on_timer 相同的 fallback 逻辑
        sentiment_data = {
            'long_short_ratio': 1.0,
            'long_account_pct': 50.0,
            'short_account_pct': 50.0,
            'source': 'default_neutral',
            'timestamp': None,
        }
        print("  ⚠️ 使用中性默认值 (与 on_timer fallback 相同)")

except (ImportError, AttributeError, requests.RequestException, ValueError) as e:
    print(f"  ❌ 情绪数据获取失败: {e}")
    sentiment_data = {
        'long_short_ratio': 1.0,
        'long_account_pct': 50.0,
        'short_account_pct': 50.0,
        'source': 'fallback',
    }
except (KeyboardInterrupt, SystemExit):
    print("\n  用户中断")
    raise

print()

# =============================================================================
# 6. 构建价格数据 (与 on_timer 相同结构)
# =============================================================================
print("[6/10] 构建价格数据...")

kline_data = indicator_manager.get_kline_data(count=10)

# 计算价格变化
bars = indicator_manager.recent_bars
if len(bars) >= 2:
    price_change = ((float(bars[-1].close) - float(bars[-2].close)) / float(bars[-2].close)) * 100
else:
    price_change = 0.0

price_data = {
    'price': current_price,
    'timestamp': datetime.now().isoformat(),
    'high': float(klines_raw[-1][2]),
    'low': float(klines_raw[-1][3]),
    'volume': float(klines_raw[-1][5]),
    'price_change': price_change,
    'kline_data': kline_data,
}

print(f"  Current Price: ${price_data['price']:,.2f}")
print(f"  High: ${price_data['high']:,.2f}")
print(f"  Low: ${price_data['low']:,.2f}")
print(f"  Price Change: {price_data['price_change']:.2f}%")
print(f"  K-line Count: {len(price_data['kline_data'])}")
print("  ✅ 价格数据构建成功")

print()

# =============================================================================
# 7. MultiAgent 层级决策 (TradingAgents 架构 - 使用实盘配置)
# =============================================================================
print("[7/10] MultiAgent 层级决策 (TradingAgents 架构)...")
print("-" * 70)
print("  📋 决策流程:")
print("     Phase 1: Bull/Bear Debate (辩论)")
print("     Phase 2: Judge (Portfolio Manager) Decision")
print("     Phase 3: Risk Evaluation")
print()

try:
    from agents.multi_agent_analyzer import MultiAgentAnalyzer

    # 使用与 deepseek_strategy.py 完全相同的初始化参数
    multi_agent = MultiAgentAnalyzer(
        api_key=strategy_config.deepseek_api_key,
        model=strategy_config.deepseek_model,
        temperature=strategy_config.deepseek_temperature,
        debate_rounds=strategy_config.debate_rounds,
    )

    print(f"  Model: {strategy_config.deepseek_model}")
    print(f"  Temperature: {strategy_config.deepseek_temperature}")
    print(f"  Debate Rounds: {strategy_config.debate_rounds}")
    print()
    print("  🐂 Bull Agent 分析中...")
    print("  🐻 Bear Agent 分析中...")
    print("  ⚖️ Judge Agent 判断中...")
    print("  🛡️ Risk Manager 评估中...")

    # 调用分析 (与 on_timer 相同，使用真实持仓)
    # TradingAgents: Judge 决策即最终决策，不需要与 DeepSeek 合并
    signal_data = multi_agent.analyze(
        symbol="BTCUSDT",
        technical_report=technical_data,
        sentiment_report=sentiment_data,
        current_position=current_position,  # 使用真实持仓
        price_data=price_data,
    )

    print()
    print("  🎯 Judge 最终决策:")
    print(f"     Signal: {signal_data.get('signal', 'N/A')}")
    print(f"     Confidence: {signal_data.get('confidence', 'N/A')}")
    print(f"     Risk Level: {signal_data.get('risk_level', 'N/A')}")
    print(f"     Stop Loss: {signal_data.get('stop_loss', 'N/A')}")
    print(f"     Take Profit: {signal_data.get('take_profit', 'N/A')}")

    # 显示 Judge 详细决策
    judge_decision = signal_data.get('judge_decision', {})
    if judge_decision:
        winning_side = judge_decision.get('winning_side', 'N/A')
        key_reasons = judge_decision.get('key_reasons', [])
        print(f"     Winning Side: {winning_side}")
        if key_reasons:
            print(f"     Key Reasons: {', '.join(key_reasons[:3])}")

    if signal_data.get('debate_summary'):
        summary = signal_data['debate_summary']
        print(f"     Debate Summary: {summary[:150]}..." if len(summary) > 150 else f"     Debate Summary: {summary}")

    reason = signal_data.get('reason', 'N/A')
    print(f"     Reason: {reason[:150]}..." if len(reason) > 150 else f"     Reason: {reason}")
    print("  ✅ MultiAgent 层级决策成功")

except (ImportError, AttributeError, requests.RequestException, ValueError, KeyError) as e:
    print(f"  ❌ MultiAgent 层级决策失败: {e}")
    import traceback
    traceback.print_exc()
    signal_data = {
        'signal': 'ERROR',
        'confidence': 'LOW',
        'reason': str(e),
        'stop_loss': None,
        'take_profit': None,
    }
except (KeyboardInterrupt, SystemExit):
    print("\n  用户中断")
    raise

print()

# =============================================================================
# 8. 交易决策 (TradingAgents - Judge 决策即最终决策)
# =============================================================================
print("[8/10] 交易决策 (TradingAgents - Judge 决策即最终决策)...")
print("-" * 70)

# 导入共享模块 (与实盘使用完全相同的函数)
from strategy.trading_logic import (
    check_confidence_threshold,
    calculate_position_size,
    validate_multiagent_sltp,
    calculate_technical_sltp,
    CONFIDENCE_LEVELS,
)

# TradingAgents: Judge 决策即最终决策，不需要信号合并
final_signal = signal_data.get('signal', 'HOLD')
confidence = signal_data.get('confidence', 'LOW')

print(f"  🎯 Final Signal: {final_signal}")
print(f"  📊 Confidence: {confidence}")
print()

# =============================================================================
# SL/TP 验证逻辑 (与 deepseek_strategy.py:1272-1388 完全一致)
# =============================================================================
final_sl = None
final_tp = None
sltp_source = "N/A"

if final_signal in ['BUY', 'SELL']:
    print("  📊 SL/TP 验证 (模拟 _submit_bracket_order 逻辑):")
    print("-" * 70)

    # 获取 entry price
    entry_price = price_data.get('price', current_price)

    # 检查 MultiAgent SL/TP (来自 Judge 的决策)
    multi_sl = signal_data.get('stop_loss')
    multi_tp = signal_data.get('take_profit')

    if multi_sl and multi_tp:
        print(f"     MultiAgent 返回: SL=${multi_sl:,.2f}, TP=${multi_tp:,.2f}")

        # 验证 MultiAgent SL/TP
        is_valid, validated_sl, validated_tp, reason = validate_multiagent_sltp(
            side=final_signal,
            multi_sl=multi_sl,
            multi_tp=multi_tp,
            entry_price=entry_price
        )

        if is_valid:
            print(f"     ✅ MultiAgent SL/TP 验证通过: {reason}")
            final_sl = validated_sl
            final_tp = validated_tp
            sltp_source = "MultiAgent (Judge)"
        else:
            print(f"     ❌ MultiAgent SL/TP 验证失败: {reason}")
            print(f"     → 回退到技术分析计算")

            # 回退到技术分析
            support = technical_data.get('support', 0.0)
            resistance = technical_data.get('resistance', 0.0)
            use_sr = getattr(strategy_config, 'sl_use_support_resistance', True)
            sl_buffer = getattr(strategy_config, 'sl_buffer_pct', 0.001)

            final_sl, final_tp, calc_method = calculate_technical_sltp(
                side=final_signal,
                entry_price=entry_price,
                support=support,
                resistance=resistance,
                confidence=confidence,
                use_support_resistance=use_sr,
                sl_buffer_pct=sl_buffer
            )
            sltp_source = f"Technical Analysis ({calc_method})"
            print(f"     📍 技术分析计算: SL=${final_sl:,.2f}, TP=${final_tp:,.2f}")
            print(f"     方法: {calc_method}")
    else:
        print("     ⚠️ MultiAgent 未返回 SL/TP，使用技术分析")

        # 直接使用技术分析
        support = technical_data.get('support', 0.0)
        resistance = technical_data.get('resistance', 0.0)
        use_sr = getattr(strategy_config, 'sl_use_support_resistance', True)
        sl_buffer = getattr(strategy_config, 'sl_buffer_pct', 0.001)

        final_sl, final_tp, calc_method = calculate_technical_sltp(
            side=final_signal,
            entry_price=entry_price,
            support=support,
            resistance=resistance,
            confidence=confidence,
            use_support_resistance=use_sr,
            sl_buffer_pct=sl_buffer
        )
        sltp_source = f"Technical Analysis ({calc_method})"
        print(f"     📍 技术分析计算: SL=${final_sl:,.2f}, TP=${final_tp:,.2f}")
        print(f"     方法: {calc_method}")

    # 显示最终 SL/TP
    print()
    print(f"  🎯 最终 SL/TP (实盘会使用的值):")
    if final_sl and final_tp:
        sl_pct = ((final_sl / entry_price) - 1) * 100
        tp_pct = ((final_tp / entry_price) - 1) * 100
        print(f"     Entry: ~${entry_price:,.2f}")
        print(f"     Stop Loss: ${final_sl:,.2f} ({sl_pct:+.2f}%)")
        print(f"     Take Profit: ${final_tp:,.2f} ({tp_pct:+.2f}%)")
        print(f"     来源: {sltp_source}")
    else:
        print(f"     ❌ 无法计算 SL/TP")

print()

# 模拟 _execute_trade 的检查逻辑 (使用共享模块)
print("  模拟 _execute_trade 检查:")

# 0. 检查 is_trading_paused (诊断无法检测，需查看服务状态)
print("  ⚠️ is_trading_paused: 无法检测 (需查看服务日志)")

# 1. 检查 min_confidence (使用共享函数)
passes_threshold, threshold_msg = check_confidence_threshold(
    confidence, strategy_config.min_confidence_to_trade
)
print(f"  {threshold_msg}")

if not passes_threshold:
    print("     → Trade would be SKIPPED")
    would_trade = False
else:
    would_trade = True

# 2. 检查是否 HOLD
if final_signal == 'HOLD':
    print("  ℹ️ Signal is HOLD → No action")
    would_trade = False
elif final_signal in ['BUY', 'SELL']:
    print(f"  ✅ Signal is {final_signal} → Actionable")
else:
    print(f"  ❌ Signal is {final_signal} → Error state")
    would_trade = False

# 3. 计算仓位大小 (使用共享模块 calculate_position_size - 100% 一致)
if would_trade and final_signal in ['BUY', 'SELL']:
    print()
    print("  模拟仓位计算 (调用共享 calculate_position_size):")

    # 构建与 strategy 相同的配置字典
    position_config = {
        'base_usdt': strategy_config.base_usdt_amount,
        'equity': strategy_config.equity,
        'high_confidence_multiplier': strategy_config.high_confidence_multiplier,
        'medium_confidence_multiplier': strategy_config.medium_confidence_multiplier,
        'low_confidence_multiplier': strategy_config.low_confidence_multiplier,
        'trend_strength_multiplier': strategy_config.trend_strength_multiplier,
        'rsi_extreme_multiplier': strategy_config.rsi_extreme_multiplier,
        'rsi_extreme_upper': strategy_config.rsi_extreme_threshold_upper,
        'rsi_extreme_lower': strategy_config.rsi_extreme_threshold_lower,
        'max_position_ratio': strategy_config.max_position_ratio,
        'min_trade_amount': getattr(strategy_config, 'min_trade_amount', 0.001),
    }

    # 使用共享模块计算仓位 (与 strategy._calculate_position_size 完全相同)
    btc_quantity, calc_details = calculate_position_size(
        signal_data=signal_data,  # TradingAgents: 使用 Judge 的决策数据
        price_data=price_data,
        technical_data=technical_data,
        config=position_config,
        logger=None,  # 静默模式，我们手动打印
    )

    # 显示计算详情
    print(f"     Base: ${calc_details['base_usdt']}")
    print(f"     × Confidence Mult: {calc_details['conf_mult']}")
    print(f"     × Trend Mult: {calc_details['trend_mult']} (trend={calc_details['trend']})")
    print(f"     × RSI Mult: {calc_details['rsi_mult']} (RSI={calc_details['rsi']:.1f})")
    print(f"     = ${calc_details['suggested_usdt']:.2f}")
    print(f"     Max allowed: ${calc_details['max_usdt']:.2f}")
    print(f"     Final: ${calc_details['final_usdt']:.2f}")
    print(f"     BTC Quantity: {btc_quantity:.4f} BTC")
    print(f"     Notional: ${calc_details['notional']:.2f}")
    if calc_details.get('adjusted'):
        print(f"     ⚠️ Quantity adjusted to meet minimum notional")

    # 3.5 检查仓位为0 (与 _execute_trade 一致)
    if btc_quantity == 0:
        print()
        print("  ❌ 仓位计算结果为 0!")
        print("     → 实盘会输出: 'Calculated position size is 0, skipping trade'")
        print("     → 🔴 NO TRADE")
        would_trade = False

    # 4. 检查现有持仓 (与 _manage_existing_position 逻辑一致)
    print()
    print("  模拟持仓管理检查:")
    target_side = 'long' if final_signal == 'BUY' else 'short'

    if current_position:
        current_side = current_position['side']
        current_qty = current_position['quantity']
        adjustment_threshold = getattr(strategy_config, 'position_adjustment_threshold', 0.001)

        print(f"     当前持仓: {current_side.upper()} {current_qty:.4f} BTC")
        print(f"     目标方向: {target_side.upper()} {btc_quantity:.4f} BTC")
        print(f"     调整阈值: {adjustment_threshold} BTC")

        if target_side == current_side:
            # 同方向持仓
            size_diff = btc_quantity - current_qty
            print(f"     仓位差异: {size_diff:+.4f} BTC")

            if abs(size_diff) < adjustment_threshold:
                print(f"     ⚠️ 仓位差异 ({abs(size_diff):.4f}) < 阈值 ({adjustment_threshold})")
                print(f"     → 实盘会输出: 'Position size appropriate, no adjustment needed'")
                print(f"     → 🔴 NO NEW TRADE - 这就是信号发出但无交易的原因!")
                would_trade = False
            elif size_diff > 0:
                print(f"     → 将增加仓位 {abs(size_diff):.4f} BTC")
            else:
                print(f"     → 将减少仓位 {abs(size_diff):.4f} BTC")
        else:
            # 反向持仓 - 反转
            allow_reversals = getattr(strategy_config, 'allow_reversals', True)
            require_high_conf = getattr(strategy_config, 'require_high_confidence_for_reversal', False)

            if allow_reversals:
                if require_high_conf and confidence != 'HIGH':
                    print(f"     ⚠️ 反转需要 HIGH 信心，当前为 {confidence}")
                    print(f"     → 实盘会保持现有 {current_side.upper()} 持仓")
                    would_trade = False
                else:
                    print(f"     → 将反转持仓: {current_side.upper()} → {target_side.upper()}")
            else:
                print(f"     ⚠️ 反转已禁用")
                print(f"     → 实盘会保持现有 {current_side.upper()} 持仓")
                would_trade = False
    else:
        print(f"     无现有持仓 → 将开新 {target_side.upper()} 仓位 {btc_quantity:.4f} BTC")

print()

# =============================================================================
# 最终诊断总结
# =============================================================================
print("=" * 70)
print("  诊断总结 (TradingAgents - Judge 层级决策)")
print("=" * 70)
print()

# TradingAgents: Judge 决策即最终决策，无需共识检查
print(f"  📊 Final Signal: {final_signal}")
print(f"  📊 Confidence: {confidence}")
judge_decision = signal_data.get('judge_decision', {})
winning_side = judge_decision.get('winning_side', 'N/A')
print(f"  📊 Winning Side: {winning_side}")
print(f"  📊 Risk Level: {signal_data.get('risk_level', 'N/A')}")
print()

# 显示持仓信息
if current_position:
    print(f"  📊 Current Position: {current_position['side'].upper()} {current_position['quantity']:.4f} BTC")
else:
    print(f"  📊 Current Position: None")
print()

if would_trade and final_signal in ['BUY', 'SELL']:
    print(f"  🟢 WOULD EXECUTE: {final_signal} {btc_quantity:.4f} BTC @ ${current_price:,.2f}")
    print(f"     Notional: ${btc_quantity * current_price:.2f}")
    # 显示最终的 SL/TP (经过验证或技术分析计算)
    if final_sl:
        print(f"     Stop Loss: ${final_sl:,.2f}")
    if final_tp:
        print(f"     Take Profit: ${final_tp:,.2f}")
    if sltp_source and sltp_source != "N/A":
        print(f"     SL/TP 来源: {sltp_source}")
elif final_signal == 'HOLD':
    print("  🟡 NO TRADE: Judge recommends HOLD")
    reason = signal_data.get('reason', 'N/A')
    print(f"     Reason: {reason[:100]}..." if len(reason) > 100 else f"     Reason: {reason}")
elif not would_trade and final_signal in ['BUY', 'SELL']:
    # 信号是 BUY/SELL 但因为持仓原因不会执行
    print(f"  🔴 NO TRADE: Signal={final_signal}, but blocked by position management")
    if current_position:
        target_side = 'long' if final_signal == 'BUY' else 'short'
        if current_position['side'] == target_side:
            print(f"     → 已有同方向持仓 ({current_position['side'].upper()} {current_position['quantity']:.4f} BTC)")
            print(f"     → 仓位差异低于调整阈值，无需操作")
        else:
            print(f"     → 反转被阻止 (当前: {current_position['side'].upper()}, 信号: {target_side.upper()})")
else:
    print(f"  🔴 NO TRADE: Signal={final_signal}, Confidence={confidence}")
    if not passes_threshold:
        print(f"     → Confidence below minimum ({strategy_config.min_confidence_to_trade})")

print()

# Telegram 和交易执行流程说明
print("-" * 70)
print("  📱 实盘执行流程:")
print("-" * 70)
print()

if final_signal in ['BUY', 'SELL']:
    print(f"  Step 1: AI 分析完成 → Signal = {final_signal}")
    print(f"  Step 2: 📱 发送 Telegram 信号通知")
    print(f"          → 此时你会收到交易信号消息")
    print(f"  Step 3: 调用 _execute_trade()")

    if not passes_threshold:
        print(f"          → ❌ 信心 {confidence} < 最低要求 {strategy_config.min_confidence_to_trade}")
        print(f"          → 🔴 交易被跳过，但 Telegram 信号已发送!")
    elif would_trade:
        print(f"          → ✅ 所有检查通过")
        print(f"          → 📊 提交订单到 Binance")
    else:
        print(f"          → ❌ 被持仓管理阻止")
        print(f"          → 🔴 交易被跳过，但 Telegram 信号已发送!")
else:
    print(f"  Step 1: AI 分析完成 → Signal = {final_signal}")
    print(f"  Step 2: ❌ 非 BUY/SELL 信号，不发送 Telegram")
    print(f"  Step 3: _execute_trade 直接返回")

print()
print("  💡 关键点: Telegram 通知在 _execute_trade 之前发送!")
print("     如果收到信号但无交易，检查服务日志查看 _execute_trade 输出")
print()
print("=" * 70)
print("  诊断完成 - 使用共享模块，与实盘逻辑 100% 一致")
print("=" * 70)

# =============================================================================
# 深入分析: 为什么没有交易信号?
# =============================================================================
if not SUMMARY_MODE:
    print()
    print("=" * 70)
    print("  📋 深入分析: 信号产生条件")
    print("=" * 70)
    print()

    # 1. 技术指标详细分析
    print("[分析1] 技术指标阈值检查")
    print("-" * 50)

rsi = technical_data.get('rsi', 50)
rsi_upper = getattr(strategy_config, 'rsi_extreme_threshold_upper', 70)
rsi_lower = getattr(strategy_config, 'rsi_extreme_threshold_lower', 30)

print(f"  RSI: {rsi:.2f}")
print(f"    配置阈值: 超卖<{rsi_lower}, 超买>{rsi_upper}")
if rsi > rsi_upper:
    print(f"    → 🔴 超买区 (>{rsi_upper}) - 可能触发 SELL")
elif rsi < rsi_lower:
    print(f"    → 🟢 超卖区 (<{rsi_lower}) - 可能触发 BUY")
else:
    print(f"    → ⚪ 中性区间 ({rsi_lower}-{rsi_upper}) - 无明确方向")
    print(f"    → 距离超买: {rsi_upper - rsi:.2f} 点")
    print(f"    → 距离超卖: {rsi - rsi_lower:.2f} 点")

macd = technical_data.get('macd', 0)
macd_signal = technical_data.get('macd_signal', 0)
macd_hist = technical_data.get('macd_histogram', 0)
print()
print(f"  MACD: {macd:.4f}")
print(f"  MACD Signal: {macd_signal:.4f}")
print(f"  MACD Histogram: {macd_hist:.4f}")
if macd > macd_signal:
    print("    → 🟢 MACD 在信号线上方 - 看涨")
else:
    print("    → 🔴 MACD 在信号线下方 - 看跌")

if macd_hist > 0:
    print(f"    → 🟢 柱状图为正 (+{macd_hist:.4f}) - 上涨动能")
else:
    print(f"    → 🔴 柱状图为负 ({macd_hist:.4f}) - 下跌动能")

# SMA 分析
print()
sma_5 = technical_data.get('sma_5', 0)
sma_20 = technical_data.get('sma_20', 0)
sma_50 = technical_data.get('sma_50', 0)
print(f"  SMA_5: ${sma_5:,.2f}")
print(f"  SMA_20: ${sma_20:,.2f}")
print(f"  SMA_50: ${sma_50:,.2f}")
print(f"  当前价格: ${current_price:,.2f}")

if current_price > sma_5 > sma_20 > sma_50:
    print("    → 🟢 完美多头排列 (价格 > SMA5 > SMA20 > SMA50)")
elif current_price < sma_5 < sma_20 < sma_50:
    print("    → 🔴 完美空头排列 (价格 < SMA5 < SMA20 < SMA50)")
else:
    print("    → ⚪ 无明确趋势排列")
    if current_price > sma_20:
        print(f"       价格在 SMA20 上方 (+{((current_price/sma_20)-1)*100:.2f}%)")
    else:
        print(f"       价格在 SMA20 下方 ({((current_price/sma_20)-1)*100:.2f}%)")

# 布林带分析
print()
bb_upper = technical_data.get('bb_upper', 0)
bb_lower = technical_data.get('bb_lower', 0)
bb_width = bb_upper - bb_lower if bb_upper and bb_lower else 0
bb_position = ((current_price - bb_lower) / bb_width * 100) if bb_width > 0 else 50

print(f"  BB Upper: ${bb_upper:,.2f}")
print(f"  BB Lower: ${bb_lower:,.2f}")
print(f"  BB Width: ${bb_width:,.2f} ({bb_width/current_price*100:.2f}%)")
print(f"  价格在带内位置: {bb_position:.1f}%")

if bb_position > BB_OVERBOUGHT_THRESHOLD:
    print(f"    → 🔴 接近上轨 (>{BB_OVERBOUGHT_THRESHOLD}%, 可能超买)")
elif bb_position < BB_OVERSOLD_THRESHOLD:
    print(f"    → 🟢 接近下轨 (<{BB_OVERSOLD_THRESHOLD}%, 可能超卖)")
else:
    print("    → ⚪ 带内中间区域")

# 2. 趋势分析
print()
print("[分析2] 趋势强度分析")
print("-" * 50)

trend = technical_data.get('overall_trend', 'N/A')
print(f"  整体趋势判断: {trend}")

# 计算近期价格变化
if len(bars) >= 10:
    price_10_bars_ago = float(bars[-10].close)
    price_change_10 = ((current_price - price_10_bars_ago) / price_10_bars_ago) * 100
    print(f"  近10根K线变化: {price_change_10:+.2f}%")
else:
    print(f"  近10根K线变化: N/A (K线数量不足: {len(bars)})")

if len(bars) >= 20:
    price_20_bars_ago = float(bars[-20].close)
    price_change_20 = ((current_price - price_20_bars_ago) / price_20_bars_ago) * 100
    print(f"  近20根K线变化: {price_change_20:+.2f}%")
else:
    print(f"  近20根K线变化: N/A (K线数量不足: {len(bars)})")

# 3. 情绪分析
print()
print("[分析3] 市场情绪分析")
print("-" * 50)

ls_ratio = sentiment_data.get('long_short_ratio', 1.0)
print(f"  多空比: {ls_ratio:.4f}")

if ls_ratio > LS_RATIO_EXTREME_BULLISH:
    print(f"    → 🔴 极度看多 (>{LS_RATIO_EXTREME_BULLISH}, 逆向指标: 可能下跌)")
elif ls_ratio > LS_RATIO_BULLISH:
    print(f"    → 🟡 偏多 (>{LS_RATIO_BULLISH}, 市场乐观)")
elif ls_ratio < LS_RATIO_EXTREME_BEARISH:
    print(f"    → 🔴 极度看空 (<{LS_RATIO_EXTREME_BEARISH}, 逆向指标: 可能上涨)")
elif ls_ratio < LS_RATIO_BEARISH:
    print(f"    → 🟡 偏空 (<{LS_RATIO_BEARISH}, 市场悲观)")
else:
    print("    → ⚪ 多空平衡")

# 4. 为什么 AI 返回该信号 (TradingAgents: Judge 决策分析)
print()
print("[分析4] Judge 决策原因分析 (TradingAgents)")
print("-" * 50)

print(f"  ⚖️ Judge 最终决策: {signal_data.get('signal', 'N/A')}")
print()

# 显示 Judge 详细决策
judge_decision = signal_data.get('judge_decision', {})
if judge_decision:
    print(f"  Winning Side: {judge_decision.get('winning_side', 'N/A')}")
    key_reasons = judge_decision.get('key_reasons', [])
    if key_reasons:
        print(f"  Key Reasons:")
        for reason in key_reasons[:3]:
            print(f"    • {reason}")
    risks = judge_decision.get('acknowledged_risks', [])
    if risks:
        print(f"  Acknowledged Risks:")
        for risk in risks[:2]:
            print(f"    • {risk}")

print()
print(f"  📋 Judge 完整理由:")
judge_reason = signal_data.get('reason', 'N/A')
print_wrapped(judge_reason)

print()
print(f"  🗣️ 辩论摘要:")
debate_summary = signal_data.get('debate_summary', 'N/A')
print_wrapped(str(debate_summary))

# 5. 触发交易的条件 (基于更新后的提示词)
print()
print("[分析5] 触发交易所需条件 (最新提示词)")
print("-" * 50)

print("  要触发 BUY 信号 (ANY 2 of these is sufficient):")
print(f"    • 价格在 SMA5/SMA20 上方 (当前: {'✅' if current_price > sma_5 and current_price > sma_20 else '❌'})")
print(f"    • RSI < 60 且不超买 (当前: {rsi:.2f}, {'✅' if rsi < 60 else '❌'})")
print(f"    • MACD 金叉或柱状图为正 (当前: {'✅' if macd > macd_signal or macd_hist > 0 else '❌'})")
print(f"    • 价格接近支撑或 BB 下轨 (当前位置: {bb_position:.1f}%)")
print()
print("  要触发 SELL 信号 (ANY 2 of these is sufficient):")
print(f"    • 价格在 SMA5/SMA20 下方 (当前: {'✅' if current_price < sma_5 and current_price < sma_20 else '❌'})")
print(f"    • RSI > 40 且显示弱势 (当前: {rsi:.2f}, {'✅' if rsi > 40 else '❌'})")
print(f"    • MACD 死叉或柱状图为负 (当前: {'✅' if macd < macd_signal or macd_hist < 0 else '❌'})")
print(f"    • 价格接近阻力或 BB 上轨 (当前位置: {bb_position:.1f}%)")
print()
print("  📌 提示词更新后，HOLD 仅在信号真正冲突时使用")
print(f"     当前 min_confidence_to_trade: {strategy_config.min_confidence_to_trade}")

# 6. 建议
print()
print("[分析6] 诊断建议")
print("-" * 50)

if final_signal == 'HOLD':
    print("  📌 当前市场状态分析:")

    # 综合评分
    bullish_score = 0
    bearish_score = 0

    # RSI
    if rsi < 40:
        bullish_score += 1
    elif rsi > 60:
        bearish_score += 1

    # MACD
    if macd > macd_signal:
        bullish_score += 1
    else:
        bearish_score += 1

    # Price vs SMA20
    if current_price > sma_20:
        bullish_score += 1
    else:
        bearish_score += 1

    # BB position
    if bb_position < 30:
        bullish_score += 1
    elif bb_position > 70:
        bearish_score += 1

    # Long/Short ratio (逆向)
    if ls_ratio > LS_RATIO_EXTREME_BULLISH:
        bearish_score += 1
    elif ls_ratio < LS_RATIO_BEARISH:
        bullish_score += 1

    print(f"    多头信号得分: {bullish_score}/5")
    print(f"    空头信号得分: {bearish_score}/5")

    if bullish_score > bearish_score + 1:
        print("    → 偏多头，但信号不够强烈")
    elif bearish_score > bullish_score + 1:
        print("    → 偏空头，但信号不够强烈")
    else:
        print("    → 多空信号混杂，无明确方向")

    print()
    print("  💡 HOLD 的常见原因:")
    print("    1. 技术指标处于中性区间 (RSI 30-70)")
    print("    2. 趋势不明确 (震荡整理)")
    print("    3. 多头和空头信号相互矛盾")
    print("    4. 市场波动率低，缺乏明确方向")
    print()
    print("  ⏳ 等待以下情况之一发生:")
    print("    • RSI 突破 30 或 70")
    print("    • MACD 形成明确金叉/死叉")
    print("    • 价格突破关键支撑/阻力位")
    print(f"      支撑: ${technical_data.get('support', 0):,.2f}")
    print(f"      阻力: ${technical_data.get('resistance', 0):,.2f}")

    print()
    print("=" * 70)
    print("  深入分析完成")
    print("=" * 70)
else:
    # Summary mode: add actionable suggestions
    print()
    print("=" * 70)
    print("  🔧 下一步建议")
    print("=" * 70)
    print()

    if final_signal == 'HOLD':
        print("  📌 当前信号: HOLD")
        print(f"  原因: {signal_data.get('reason', 'N/A')[:100]}")
        print()
        print("  💡 等待条件:")
        print("    • RSI 突破超买/超卖区间 (< 30 或 > 70)")
        print("    • MACD 形成明确金叉/死叉")
        print("    • 价格突破关键支撑/阻力位")
        rsi = technical_data.get('rsi', 50)
        if rsi > 50:
            print(f"    • 当前 RSI={rsi:.1f}, 距离超买还需 {70-rsi:.1f} 点")
        else:
            print(f"    • 当前 RSI={rsi:.1f}, 距离超卖还需 {rsi-30:.1f} 点")
        print()
        print("  ⏰ 实盘每 {:.0f} 分钟重新分析一次".format(timer_min))

    elif not would_trade and current_position:
        print(f"  📌 有信号 ({final_signal}) 但未执行")
        target_side = 'long' if final_signal == 'BUY' else 'short'
        if current_position['side'] == target_side:
            print(f"  原因: 已有同向持仓，仓位差异低于调整阈值")
            print()
            print("  💡 建议:")
            print("    • 这是正常行为，避免频繁微调仓位")
            print("    • 等待更大的仓位变化需求或反转信号")
        else:
            print(f"  原因: 反转被阻止")
            print()
            print("  💡 检查:")
            print("    • 配置: allow_reversals 是否启用?")
            print("    • 配置: require_high_confidence_for_reversal?")
            print(f"    • 当前信心: {confidence}")

    elif btc_quantity == 0:
        print(f"  📌 有信号 ({final_signal}) 但仓位为 0")
        print("  原因: 计算的仓位大小低于最小交易量")
        print()
        print("  💡 建议:")
        print("    • 增加账户余额")
        print("    • 或调整配置: base_usdt_amount")

    elif not passes_threshold:
        print(f"  📌 有信号 ({final_signal}) 但信心不足")
        print(f"  原因: {confidence} < {strategy_config.min_confidence_to_trade}")
        print()
        print("  💡 建议:")
        print("    • 等待更强的市场信号")
        print("    • 或降低配置: min_confidence_to_trade")

    elif would_trade:
        print(f"  📌 将执行交易: {final_signal} {btc_quantity:.4f} BTC")
        if final_sl and final_tp:
            sl_pct = ((final_sl / entry_price) - 1) * 100
            tp_pct = ((final_tp / entry_price) - 1) * 100
            print(f"  SL: ${final_sl:,.2f} ({sl_pct:+.2f}%)")
            print(f"  TP: ${final_tp:,.2f} ({tp_pct:+.2f}%)")
        print()
        print("  💡 实盘状态:")
        print("    • 检查服务是否运行: systemctl status nautilus-trader")
        print("    • 查看日志: journalctl -u nautilus-trader -f --no-hostname")

    print()
    print("  📖 详细分析: 运行 python3 diagnose_realtime.py (不加 --summary)")
    print()
