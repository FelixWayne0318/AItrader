"""
Diagnostics Module for AItrader
================================

A modular diagnostic system for real-time trading signal analysis.
Refactored from the monolithic diagnose_realtime.py (v11.16) into
a clean, maintainable architecture.

v5.1 新增模块:
- code_integrity.py: 静态代码完整性检查 (P1.1-P1.10)
- math_verification.py: 数学验证 (M1-M6)

Module Structure:
- base.py: Core classes, utilities, and shared functionality
- code_integrity.py: v5.1 static code analysis (NEW)
- math_verification.py: v5.1 math verification (NEW)
- config_checker.py: Configuration validation
- market_data.py: Market data fetching from Binance
- indicator_test.py: Technical indicator testing
- position_check.py: Position and account checking
- ai_decision.py: AI decision analysis (MultiAgent)
- mtf_components.py: Multi-timeframe component testing
- lifecycle_test.py: Post-trade lifecycle and MTF routing tests
- order_flow_simulation.py: v5.1 order flow simulation (10 scenarios)
- architecture_verify.py: TradingAgents architecture verification
- summary.py: Results summary and export
- service_health.py: Service health and API checks

Usage:
    from scripts.diagnostics import DiagnosticRunner
    runner = DiagnosticRunner(env='production')
    runner.run_all()

"""

from .base import (
    DiagnosticContext,
    DiagnosticStep,
    DiagnosticRunner,
    MockBar,
    TeeOutput,
    ensure_venv,
    fetch_binance_klines,
    create_bar_from_kline,
    safe_float,
    print_wrapped,
    print_section,
    print_box,
)
__all__ = [
    "DiagnosticContext",
    "DiagnosticStep",
    "DiagnosticRunner",
    "MockBar",
    "TeeOutput",
    "ensure_venv",
    "fetch_binance_klines",
    "create_bar_from_kline",
    "safe_float",
    "print_wrapped",
    "print_section",
    "print_box",
]
