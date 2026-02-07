#!/usr/bin/env python3
"""
实盘信号诊断工具

100% 还原实盘 on_timer() → AIDataAssembler → MultiAgentAnalyzer.analyze() 全流程。

AI 决策流程 (顺序执行，每次分析周期):
  Round 1: Bull Analyst → Bear Analyst  (2 API calls)
  Round 2: Bull Analyst → Bear Analyst  (2 API calls)
  Judge (Portfolio Manager) Decision    (1 API call)
  Risk Manager Evaluation               (1 API call)
  ─────────────────────────────────────
  合计: 6 次 DeepSeek API 顺序调用 (debate_rounds=2 时)

诊断阶段:
  Phase 0: 服务健康检查 + API 响应
  Phase 1: 配置验证
  Phase 2: 市场数据采集 (K线 + 情绪)
  Phase 3: 技术指标计算
  Phase 4: 持仓 + 账户检查
  Phase 5: AI 输入数据验证 (13 类)
  Phase 6: AI 决策 (6 次顺序 API 调用)
  Phase 7: 架构完整性验证
  Phase 8: MTF + Telegram + 错误恢复
  Phase 9: 订单流程模拟 (7 场景)
  Phase 10: 汇总 + 深度分析
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
    AIInputDataValidator,
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
from scripts.diagnostics.lifecycle_test import (
    PostTradeLifecycleTest,
    OnBarMTFRoutingTest,
)
from scripts.diagnostics.architecture_verify import (
    TradingAgentsArchitectureVerifier,
    DiagnosticSummaryBox,
)
from scripts.diagnostics.summary import (
    DataFlowSummary,
    DeepAnalysis,
)
from scripts.diagnostics.service_health import (
    ServiceHealthCheck,
    APIHealthCheck,
    TradingStateCheck,
    SignalHistoryCheck,
)
from scripts.diagnostics.order_flow_simulation import (
    OrderFlowSimulator,
    ReversalStateSimulator,
    BracketOrderFlowSimulator,
)


def main():
    """Main entry point for the diagnostic tool."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='实盘信号诊断工具 (TradingAgents 架构, 6 次顺序 AI 调用)',
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

    # ── Phase 0: Service Health ──
    runner.add_step(ServiceHealthCheck)         # systemd/memory/logs
    runner.add_step(APIHealthCheck)             # API 响应时间

    # ── Phase 1: Configuration ──
    runner.add_step(CriticalConfigChecker)      # 关键配置
    runner.add_step(MTFConfigChecker)           # MTF 配置
    runner.add_step(StrategyConfigLoader)       # 策略配置加载

    # ── Phase 2: Market Data (mirrors on_timer) ──
    runner.add_step(MarketDataFetcher)          # K线数据
    runner.add_step(SentimentDataFetcher)       # 情绪数据

    # ── Phase 3: Technical Indicators ──
    runner.add_step(IndicatorInitializer)       # 指标管理器初始化
    runner.add_step(TechnicalDataFetcher)       # 技术指标数据
    runner.add_step(PriceDataBuilder)           # 价格数据构建

    # ── Phase 4: Position & Account ──
    runner.add_step(PositionChecker)            # Binance 持仓
    runner.add_step(MemorySystemChecker)        # 记忆系统
    runner.add_step(TradingStateCheck)          # 交易暂停状态

    # ── Phase 5: AI Input Validation (13 categories) ──
    runner.add_step(AIInputDataValidator)       # 验证传给 AI 的 13 类数据

    # ── Phase 6: AI Decision (6 sequential DeepSeek calls) ──
    # Bull R1 → Bear R1 → Bull R2 → Bear R2 → Judge → Risk Manager
    runner.add_step(MultiAgentAnalyzer)         # 运行完整 AI 分析
    runner.add_step(SignalProcessor)            # 信号过滤

    # ── Phase 7: Architecture Verification ──
    runner.add_step(TradingAgentsArchitectureVerifier)  # 数据完整性验证
    runner.add_step(DiagnosticSummaryBox)       # 诊断总结

    # ── Phase 8: MTF + Telegram + Error Recovery ──
    runner.add_step(MTFComponentTester)         # MTF 组件
    runner.add_step(TelegramChecker)            # Telegram 配置
    runner.add_step(ErrorRecoveryChecker)       # 错误恢复机制

    # ── Phase 9: Post-Trade Lifecycle ──
    runner.add_step(PostTradeLifecycleTest)     # OCO + Trailing Stop
    runner.add_step(OnBarMTFRoutingTest)        # on_bar MTF 路由

    # ── Phase 10: Order Simulation ──
    runner.add_step(OrderSimulator)             # Bracket 订单模拟
    runner.add_step(PositionCalculator)         # 仓位计算

    # ── Phase 11: Order Flow Simulation (7 scenarios) ──
    runner.add_step(OrderFlowSimulator)         # 完整订单流程 (7 场景)
    runner.add_step(ReversalStateSimulator)     # 反转状态机
    runner.add_step(BracketOrderFlowSimulator)  # Bracket 订单流程

    # ── Phase 12: Summary ──
    runner.add_step(DataFlowSummary)            # 数据流汇总
    runner.add_step(DeepAnalysis)               # 深度分析
    runner.add_step(SignalHistoryCheck)         # 历史信号追踪

    # Run all diagnostic steps
    success = runner.run_all()

    # Export results if requested
    if export_mode:
        runner.export_results()

    # Return exit code
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
