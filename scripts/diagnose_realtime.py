#!/usr/bin/env python3
"""
实盘信号诊断脚本 v2.7.0 (v3.18 订单流程模拟)

基于 TradingAgents v3.12 架构的完整诊断工具。

v2.7.0 更新:
- 新增: v3.18 订单流程完整模拟 (7 种场景)
- 新增: 反转两阶段提交验证 (Two-Phase Commit)
- 新增: Bracket 订单失败处理验证 (No unprotected fallback)
- 新增: SL/TP 数量更新验证 (_update_sltp_quantity)
- 新增: 反转状态机详细模拟
- 新增: Bracket 订单流程详细模拟

v2.6.0 更新:
- 新增: S/R Zone Calculator 集成 (聚合 BB, SMA, Order Wall, Pivot)
- 新增: SL/TP 回退计算现在使用 S/R Zone 数据 (与 deepseek_strategy v3.14 一致)
- 新增: TP 基于阻力/支撑位计算，而非固定百分比
- 新增: R/R 比率自动调整确保 >= 1.5:1
- 新增: S/R Zone 数据显示 (级别、强度、来源类型)
- 优化: AI Prompt 改进后的 S/R 入场规则验证

v2.5.1 更新:
- 修复: historical_context count 从 20 增加到 35，确保 MACD 历史计算有足够数据
- 修复: momentum_shift 现在可以正常计算 (不再返回 INSUFFICIENT_DATA)
- 优化: Risk Manager R/R 最低要求从 1:1 提升到 1.5:1

v2.5.0 更新:
- 新增: [10] historical_context 验证 (EVALUATION_FRAMEWORK v3.0.1)
- 新增: 35-bar 趋势数据显示 (price_trend, rsi_trend, macd_trend, volume_trend)
- 新增: trend_direction 和 momentum_shift 分析
- 优化: AI 输入数据验证扩展为 10 类数据 (原 9 类)

v2.4.9 更新:
- 修复: Coinalyze API 测试使用 /open-interest 替代不存在的 /ping 端点
- 修复: HTTP 404 错误 (Coinalyze 没有 /ping 端点)

v2.4.8 更新:
- 修复: dotenv 在 DiagnosticRunner.__init__() 中早期加载
- 修复: APIHealthCheck 现在能正确读取 COINALYZE_API_KEY
- 修复: 消除 "Coinalyze API: 未配置 key" 的误报

v2.4.7 更新:
- 新增: [A] 服务运行状态检查 (systemd, memory, logs)
- 新增: [B] API 健康检查 (响应时间)
- 新增: [C] 交易暂停状态检查
- 新增: [D] 历史信号追踪
- 优化: 完整覆盖实盘运行流程，问题可立即定位

v2.4.6 更新:
- 移除: "触发交易所需条件" 分析 (误导性的硬编码规则显示)
- 原因: 与 TradingAgents v3.x AI 自主决策架构冲突

v2.4.2 更新:
- 修复: AI 输入数据验证 [11/24] 现在先获取数据再打印
- 修复: order_flow, derivatives, order_book 数据在打印前获取
- 优化: MultiAgentAnalyzer 复用已获取的数据，避免重复 API 调用
- 保证: [11/24] 显示的数据与 [12/24] 传给 AI 的数据完全一致

v2.4.1 更新:
- 新增: TradingAgents v3.3 架构验证 (已移除规则, AI接收数据, MTF状态估算)
- 新增: 诊断总结 box (与 v11.14 一致的格式)
- 新增: [分析5] 触发交易所需条件 (BUY/SELL 信号条件检查)
- 修正: account_context 字段名称与生产代码一致

v2.4 更新 (v11.16 功能恢复):
- 新增: AI 输入数据验证 (完整显示传给 AI 的所有数据)
- 新增: AI Prompt 结构验证 (System/User Prompt + INDICATOR_DEFINITIONS + 记忆系统)
- 新增: Bull/Bear 辩论记录显示
- 新增: Post-Trade 生命周期测试 (OCO 清理 + Trailing Stop)
- 新增: on_bar MTF 路由逻辑模拟 (1D/4H/15M bar 分发)
- 增强: 决策结果显示 (Key Reasons, Acknowledged Risks, Debate Summary)

v2.3 更新 (v4.8.1 字段完整性修复):
- Position 字段完整覆盖: 25 个字段与生产代码 _get_current_position_data() 一致
- Account 字段名称修正: max_usdt → max_position_value, remaining_capacity → available_capacity
- 新增字段: capacity_used_pct, max_position_ratio
- 字段名修正: pnl_pct → pnl_percentage (与 AI 格式化器一致)
- Summary 输出增加 v4.5 Tier 1/2 和 v4.7 完整字段显示

v2.2 更新:
- Funding Rate 统一使用 Binance 8h 资金费率 (不再使用 Coinalyze)
- 修复衍生品数据显示，明确标注数据来源

v2.1 更新 (v4.8 适配):
- 杠杆从 Binance API 同步 (不再硬编码)
- ai_controlled 仓位计算方法支持
- 累加模式 (cumulative) 容量检查
- 显示 max_usdt 和剩余可加仓容量

主要功能:
- 检查关键配置 (load_all, reconciliation, SL/TP 字段)
- 验证 MTF 多时间框架配置
- 加载策略配置
- 获取实时市场数据 (K线、情绪)
- 初始化并测试技术指标
- 检查 Binance 真实持仓和杠杆
- AI 输入数据验证 (11 类完整数据, 含 historical_context 和 S/R Zones)
- S/R Zone 计算和显示 (BB, SMA, Order Walls 聚合)
- 运行 AI 决策流程 (Bull/Bear/Judge)
- AI Prompt 结构验证 (记忆系统)
- 测试 MTF 组件 (OrderFlow, Coinalyze, OrderBook)
- Post-Trade 生命周期测试 (OCO + Trailing Stop)
- on_bar MTF 路由逻辑模拟
- 验证 Telegram 配置
- v4.8 仓位计算测试 (ai_controlled + 累加模式)

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
        description='实盘信号诊断工具 v2.7.0 (v3.18 订单流程模拟)',
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
    # Phase 0: Service Health (v2.4.7 新增)
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
    # Phase 1: Market Data Collection
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
    runner.add_step(MemorySystemChecker)     # 记忆系统检查 (v3.12)
    runner.add_step(TradingStateCheck)       # [C] 交易暂停状态检查 (v2.4.7)

    # =========================================================================
    # Phase 4: AI Input Data Validation (v2.4 新增)
    # =========================================================================
    runner.add_step(AIInputDataValidator)    # AI 输入数据验证 (9 类完整数据)

    # =========================================================================
    # Phase 5: AI Decision Process
    # =========================================================================
    runner.add_step(MultiAgentAnalyzer)      # 运行 AI 分析 (含辩论记录+Prompt验证)
    runner.add_step(SignalProcessor)         # 信号处理和过滤

    # =========================================================================
    # Phase 5.5: Architecture Verification (v2.4 新增)
    # =========================================================================
    runner.add_step(TradingAgentsArchitectureVerifier)  # TradingAgents v3.3 架构验证
    runner.add_step(DiagnosticSummaryBox)    # 诊断总结 box

    # =========================================================================
    # Phase 6: MTF Component Testing (Optional)
    # =========================================================================
    runner.add_step(MTFComponentTester)      # 测试 MTF 组件
    runner.add_step(TelegramChecker)         # Telegram 配置检查
    runner.add_step(ErrorRecoveryChecker)    # 错误恢复机制检查

    # =========================================================================
    # Phase 7: Post-Trade Lifecycle (v2.4 新增)
    # =========================================================================
    runner.add_step(PostTradeLifecycleTest)  # Post-Trade 生命周期测试 (OCO + Trailing)
    runner.add_step(OnBarMTFRoutingTest)     # on_bar MTF 路由逻辑模拟

    # =========================================================================
    # Phase 8: Order Simulation
    # =========================================================================
    runner.add_step(OrderSimulator)          # 模拟订单提交
    runner.add_step(PositionCalculator)      # 仓位计算测试

    # =========================================================================
    # Phase 8.5: v3.18 Order Flow Simulation (NEW)
    # =========================================================================
    runner.add_step(OrderFlowSimulator)      # v3.18 订单流程完整模拟 (7 种场景)
    runner.add_step(ReversalStateSimulator)  # v3.18 反转状态机详细模拟
    runner.add_step(BracketOrderFlowSimulator)  # Bracket 订单流程详细模拟

    # =========================================================================
    # Phase 9: Summary and Analysis
    # =========================================================================
    runner.add_step(DataFlowSummary)         # 数据流汇总
    runner.add_step(DeepAnalysis)            # 深入分析 (非 summary 模式)
    runner.add_step(SignalHistoryCheck)      # [D] 历史信号追踪 (v2.4.7)

    # Run all diagnostic steps
    success = runner.run_all()

    # Export results if requested
    if export_mode:
        runner.export_results()

    # Return exit code
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
