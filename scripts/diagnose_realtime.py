#!/usr/bin/env python3
"""
实盘信号诊断脚本 v2.0 (模块化重构版)

基于 TradingAgents v3.12 架构的完整诊断工具。

主要改进:
- 模块化架构，代码从 4234 行重构为独立模块
- DiagnosticContext 数据类替代全局变量
- DiagnosticStep 抽象基类统一步骤定义
- 更好的错误处理和步骤跟踪
- 安全的 API 密钥显示 (mask_sensitive)

功能:
- 检查关键配置 (load_all, reconciliation, SL/TP 字段)
- 验证 MTF 多时间框架配置
- 加载策略配置
- 获取实时市场数据 (K线、情绪)
- 初始化并测试技术指标
- 检查 Binance 真实持仓
- 运行 AI 决策流程 (Bull/Bear/Judge)
- 测试 MTF 组件 (OrderFlow, Coinalyze, OrderBook)
- 验证 Telegram 配置
- 模拟订单提交流程

使用方法:
    cd /home/linuxuser/nautilus_AItrader
    python3 scripts/diagnose_realtime.py              # 完整诊断
    python3 scripts/diagnose_realtime.py --summary    # 快速诊断
    python3 scripts/diagnose_realtime.py --export     # 导出到文件
    python3 scripts/diagnose_realtime.py --push       # 导出并推送到 GitHub

架构 (TradingAgents v3.12):
- Phase 1: Bull/Bear 辩论 (2 AI calls)
- Phase 2: Judge 决策 (1 AI call)
- Phase 3: Risk 评估 (1 AI call)
- 本地风控: S/R Zone v2.0 Block
"""

import argparse
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(project_root))

# Import venv helper first (before other imports)
from scripts.diagnostics.base import ensure_venv

# Ensure running in venv
ensure_venv()

# Now import the diagnostic framework
from scripts.diagnostics import DiagnosticRunner

# Import all diagnostic steps
from scripts.diagnostics.config_checker import (
    CriticalConfigChecker,
    MTFConfigChecker,
    StrategyConfigLoader,
)
from scripts.diagnostics.market_data import (
    MarketDataFetcher,
    SentimentDataFetcher,
    PriceDataBuilder,
)
from scripts.diagnostics.indicator_test import (
    IndicatorInitializer,
    TechnicalDataFetcher,
)
from scripts.diagnostics.position_check import (
    PositionChecker,
    MemorySystemChecker,
)
from scripts.diagnostics.ai_decision import (
    MultiAgentAnalyzer,
    SignalProcessor,
    OrderSimulator,
    PositionCalculator,
)
from scripts.diagnostics.mtf_components import (
    MTFComponentTester,
    TelegramChecker,
    ErrorRecoveryChecker,
)
from scripts.diagnostics.summary import (
    DataFlowSummary,
    DeepAnalysis,
)


def main():
    """Main entry point for the diagnostic tool."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='实盘信号诊断工具 v2.0 (模块化重构版)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/diagnose_realtime.py              # Full diagnosis
  python3 scripts/diagnose_realtime.py --summary    # Quick summary only
  python3 scripts/diagnose_realtime.py --export     # Export to logs/
  python3 scripts/diagnose_realtime.py --push       # Export and push to GitHub
        """
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='仅显示关键结果，跳过详细分析'
    )
    parser.add_argument(
        '--export',
        action='store_true',
        help='导出诊断结果到文件 (logs/diagnosis_YYYYMMDD_HHMMSS.txt)'
    )
    parser.add_argument(
        '--push',
        action='store_true',
        help='导出并推送到 GitHub'
    )
    parser.add_argument(
        '--env',
        default='production',
        choices=['production', 'development', 'backtest'],
        help='运行环境 (default: production)'
    )
    args = parser.parse_args()

    # --push implies --export
    export_mode = args.export or args.push

    # Create diagnostic runner
    runner = DiagnosticRunner(
        env=args.env,
        summary_mode=args.summary,
        export_mode=export_mode,
        push_to_github=args.push
    )

    # Add diagnostic steps in order
    # =========================================================================
    # Phase 0: Configuration Validation
    # =========================================================================
    runner.add_step(CriticalConfigChecker)   # [1/14] 检查关键配置
    runner.add_step(MTFConfigChecker)        # [2/14] 检查 MTF 配置
    runner.add_step(StrategyConfigLoader)    # [3/14] 加载策略配置

    # =========================================================================
    # Phase 1: Market Data Collection
    # =========================================================================
    runner.add_step(MarketDataFetcher)       # [4/14] 获取 K 线数据
    runner.add_step(SentimentDataFetcher)    # [5/14] 获取情绪数据

    # =========================================================================
    # Phase 2: Technical Indicator Initialization
    # =========================================================================
    runner.add_step(IndicatorInitializer)    # [6/14] 初始化技术指标管理器
    runner.add_step(TechnicalDataFetcher)    # [7/14] 获取技术指标数据
    runner.add_step(PriceDataBuilder)        # [8/14] 构建价格数据

    # =========================================================================
    # Phase 3: Position and Account Check
    # =========================================================================
    runner.add_step(PositionChecker)         # [9/14] 检查 Binance 持仓
    runner.add_step(MemorySystemChecker)     # [9.5/14] 记忆系统检查 (v3.12)

    # =========================================================================
    # Phase 4: AI Decision Process
    # =========================================================================
    runner.add_step(MultiAgentAnalyzer)      # [10/14] 运行 AI 分析
    runner.add_step(SignalProcessor)         # [11/14] 信号处理和过滤

    # =========================================================================
    # Phase 5: MTF Component Testing (Optional)
    # =========================================================================
    runner.add_step(MTFComponentTester)      # [12/14] 测试 MTF 组件
    runner.add_step(TelegramChecker)         # [12.5/14] Telegram 配置检查
    runner.add_step(ErrorRecoveryChecker)    # [12.6/14] 错误恢复机制检查

    # =========================================================================
    # Phase 6: Order Simulation
    # =========================================================================
    runner.add_step(OrderSimulator)          # [13/14] 模拟订单提交
    runner.add_step(PositionCalculator)      # [13.5/14] 仓位计算测试

    # =========================================================================
    # Phase 7: Summary and Analysis
    # =========================================================================
    runner.add_step(DataFlowSummary)         # [14/14] 数据流汇总
    runner.add_step(DeepAnalysis)            # [14.5/14] 深入分析 (非 summary 模式)

    # Run all diagnostic steps
    success = runner.run_all()

    # Export results if requested
    if export_mode:
        runner.export_results()

    # Return exit code
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
