#!/usr/bin/env python3
"""
实盘信号诊断脚本 v3.0.0 (100% Live-Consistent)

基于 TradingAgents v3.27.1 架构的完整诊断工具。
100% 还原实盘 on_timer() → AIDataAssembler → MultiAgentAnalyzer.analyze() 全流程。

v3.0.0 更新 (100% Live Consistency):
- 重写: analyze() 调用传递全部 11 个参数 (与 deepseek_strategy.py 1714-1731 行一致)
- 新增: binance_derivatives_report (Top Traders L/S, Taker Ratio) - 之前缺失
- 新增: orderbook_report (OBI, Slippage) - 之前缺失
- 新增: bars_data (120 bars for S/R Swing Detection) - 之前缺失
- 新增: kline_ohlcv (20 bars OHLCV) 添加到 technical_data - 之前缺失
- 新增: technical_data enrichment (timeframe, price, period_high/low/change_pct) - 与实盘一致
- 新增: BinanceDerivativesClient 集成 - 之前未创建
- 新增: step_timer 计时 - 显示每个步骤耗时
- 新增: invalidation 字段显示 (v3.27 nof1 对齐)
- 重写: architecture_verify 改为实时数据完整性验证 (替代静态文本)
- 更新: 13 类 AI 输入数据验证 (原 11 类)
- 更新: 所有版本引用升级到 v3.27.1

架构 (TradingAgents v3.27.1 - Pure Knowledge Prompts):
- Phase 1: Bull/Bear 辩论 (2 AI calls) - 纯知识描述 prompts
- Phase 2: Judge 决策 (1 AI call) - 量化确认计数
- Phase 3: Risk 评估 (1 AI call) - R/R >= 1.5:1 + invalidation 字段
- 原则: "Autonomy is non-negotiable" - 无 MUST/NEVER/ALWAYS 指令
- INDICATOR_DEFINITIONS: 117 行精简版 (统一 TRENDING/RANGING/failure)

v3.18 订单流程模拟 (7 种场景):
- 场景 1: 新开仓 (无持仓 → 开仓)
- 场景 2: 同向加仓 (SL/TP 数量更新)
- 场景 3: 部分平仓
- 场景 4: 完全平仓
- 场景 5: 反转交易 (两阶段提交)
- 场景 6: Bracket 订单失败
- 场景 7: SL/TP modify 失败回退
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
        description='实盘信号诊断工具 v3.0.0 (100% Live-Consistent, TradingAgents v3.27.1)',
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
    # Phase 0: Service Health
    # =========================================================================
    runner.add_step(ServiceHealthCheck)      # [A] systemd/memory/logs 检查
    runner.add_step(APIHealthCheck)          # [B] API 响应时间检查

    # =========================================================================
    # Phase 0.5: Configuration Validation
    # =========================================================================
    runner.add_step(CriticalConfigChecker)   # 检查关键配置
    runner.add_step(MTFConfigChecker)        # 检查 MTF 配置
    runner.add_step(StrategyConfigLoader)    # 加载策略配置

    # =========================================================================
    # Phase 1: Market Data Collection (mirrors on_timer data fetching)
    # =========================================================================
    runner.add_step(MarketDataFetcher)       # 获取 K 线数据
    runner.add_step(SentimentDataFetcher)    # 获取情绪数据

    # =========================================================================
    # Phase 2: Technical Indicator Initialization
    # =========================================================================
    runner.add_step(IndicatorInitializer)    # 初始化技术指标管理器
    runner.add_step(TechnicalDataFetcher)    # 获取技术指标数据
    runner.add_step(PriceDataBuilder)        # 构建价格数据

    # =========================================================================
    # Phase 3: Position and Account Check
    # =========================================================================
    runner.add_step(PositionChecker)         # 检查 Binance 持仓
    runner.add_step(MemorySystemChecker)     # 记忆系统检查
    runner.add_step(TradingStateCheck)       # [C] 交易暂停状态检查

    # =========================================================================
    # Phase 4: AI Input Data Validation (13 categories, 100% live-consistent)
    # =========================================================================
    runner.add_step(AIInputDataValidator)    # AI 输入数据验证 (13 类: 含 binance_derivatives + kline_ohlcv)

    # =========================================================================
    # Phase 5: AI Decision Process (4 AI calls, identical to live)
    # =========================================================================
    runner.add_step(MultiAgentAnalyzer)      # 运行 AI 分析 (全部 11 个 analyze() 参数)
    runner.add_step(SignalProcessor)         # 信号处理和过滤

    # =========================================================================
    # Phase 5.5: Architecture Verification (live data completeness check)
    # =========================================================================
    runner.add_step(TradingAgentsArchitectureVerifier)  # v3.27.1 架构验证 (实时数据完整性)
    runner.add_step(DiagnosticSummaryBox)    # 诊断总结 box

    # =========================================================================
    # Phase 6: MTF Component Testing (Optional)
    # =========================================================================
    runner.add_step(MTFComponentTester)      # 测试 MTF 组件
    runner.add_step(TelegramChecker)         # Telegram 配置检查
    runner.add_step(ErrorRecoveryChecker)    # 错误恢复机制检查

    # =========================================================================
    # Phase 7: Post-Trade Lifecycle
    # =========================================================================
    runner.add_step(PostTradeLifecycleTest)  # Post-Trade 生命周期测试 (OCO + Trailing)
    runner.add_step(OnBarMTFRoutingTest)     # on_bar MTF 路由逻辑模拟

    # =========================================================================
    # Phase 8: Order Simulation
    # =========================================================================
    runner.add_step(OrderSimulator)          # 模拟订单提交
    runner.add_step(PositionCalculator)      # 仓位计算测试

    # =========================================================================
    # Phase 8.5: v3.18 Order Flow Simulation
    # =========================================================================
    runner.add_step(OrderFlowSimulator)      # v3.18 订单流程完整模拟 (7 种场景)
    runner.add_step(ReversalStateSimulator)  # v3.18 反转状态机详细模拟
    runner.add_step(BracketOrderFlowSimulator)  # Bracket 订单流程详细模拟

    # =========================================================================
    # Phase 9: Summary and Analysis
    # =========================================================================
    runner.add_step(DataFlowSummary)         # 数据流汇总
    runner.add_step(DeepAnalysis)            # 深入分析 (非 summary 模式)
    runner.add_step(SignalHistoryCheck)      # [D] 历史信号追踪

    # Run all diagnostic steps
    success = runner.run_all()

    # Export results if requested
    if export_mode:
        runner.export_results()

    # Return exit code
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
