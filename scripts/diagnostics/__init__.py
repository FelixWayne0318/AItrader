"""
Diagnostics Module for AItrader
================================

A modular diagnostic system for real-time trading signal analysis.
Refactored from the monolithic diagnose_realtime.py (v11.16) into
a clean, maintainable architecture.

Module Structure:
- base.py: Core classes, utilities, and shared functionality
- config_checker.py: Configuration validation
- market_data.py: Market data fetching from Binance
- indicator_test.py: Technical indicator testing
- position_check.py: Position and account checking
- ai_decision.py: AI decision analysis (MultiAgent)
- mtf_components.py: Multi-timeframe component testing
- lifecycle_test.py: Post-trade lifecycle and MTF routing tests
- summary.py: Results summary and export

Usage:
    from scripts.diagnostics import DiagnosticRunner
    runner = DiagnosticRunner(env='production')
    runner.run_all()

Version: 2.4.0 - Restored v11.16 missing features
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

__version__ = "2.4.7"  # v2.4.7: Added service health checks (systemd, API latency, trading state, signal history)
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
