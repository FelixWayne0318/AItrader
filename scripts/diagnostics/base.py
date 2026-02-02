"""
Base module for the diagnostics system.

Contains core classes, utilities, and shared functionality used
across all diagnostic steps.
"""

import io
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


# =============================================================================
# Virtual Environment Helper
# =============================================================================

def ensure_venv() -> bool:
    """
    Ensure running in virtual environment, auto-switch if not.

    Returns:
        True if already in venv, False if switched
    """
    project_dir = Path(__file__).parent.parent.parent.absolute()
    venv_python = project_dir / "venv" / "bin" / "python"

    in_venv = (
        hasattr(sys, 'real_prefix') or
        (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    )

    if not in_venv and venv_python.exists():
        print(f"\033[93m[!]\033[0m Detected non-venv environment, auto-switching...")
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)

    return in_venv


# =============================================================================
# Output Utilities
# =============================================================================

class TeeOutput:
    """Simultaneously output to terminal and buffer for export."""

    def __init__(self, stream, buffer: io.StringIO):
        self.stream = stream
        self.buffer = buffer

    def write(self, data: str) -> None:
        self.stream.write(data)
        self.buffer.write(data)

    def flush(self) -> None:
        self.stream.flush()


def print_wrapped(text: str, indent: str = "    ", width: int = 80) -> None:
    """Print auto-wrapped text with indentation."""
    for i in range(0, len(text), width):
        print(f"{indent}{text[i:i+width]}")


def print_section(title: str, char: str = "-", width: int = 70) -> None:
    """Print a section header."""
    print(char * width)
    print(f"  {title}")
    print(char * width)


def print_box(title: str, width: int = 70) -> None:
    """Print a box header for data sections."""
    border = "━" * (width - 2)
    print(f"  ┏{border}┓")
    # Center the title
    padding = (width - 4 - len(title)) // 2
    print(f"  ┃{' ' * padding}{title}{' ' * (width - 4 - padding - len(title))}┃")
    print(f"  ┗{border}┛")


# =============================================================================
# Data Type Helpers
# =============================================================================

def safe_float(value: Any) -> Optional[float]:
    """
    Safely convert value to float, handling strings and None.

    AI may return strings or numbers, this handles both.
    """
    if value is None:
        return None
    try:
        if isinstance(value, str):
            # Remove currency symbols and commas
            value = value.replace('$', '').replace(',', '').strip()
        return float(value)
    except (ValueError, TypeError):
        return None


def mask_sensitive(value: str, visible_chars: int = 4) -> str:
    """
    Mask sensitive string (API keys, tokens) for safe display.

    Args:
        value: The sensitive string
        visible_chars: Number of characters to show at start

    Returns:
        Masked string like "sk-a****" or "******* (len=32)"
    """
    if not value:
        return "(not set)"
    if len(value) <= visible_chars * 2:
        return "*" * len(value)
    return f"{value[:visible_chars]}{'*' * 8} (len={len(value)})"


# =============================================================================
# Mock Objects for Testing
# =============================================================================

class MockBar:
    """
    Mock bar object for indicator updates.

    Mimics the structure of NautilusTrader Bar objects.
    Used for feeding historical data to indicators.
    """

    def __init__(self, o: float, h: float, l: float, c: float, v: float, ts: int):
        self.open = Decimal(str(o))
        self.high = Decimal(str(h))
        self.low = Decimal(str(l))
        self.close = Decimal(str(c))
        self.volume = Decimal(str(v))
        self.ts_init = int(ts)

    def __repr__(self) -> str:
        return f"MockBar(o={self.open}, h={self.high}, l={self.low}, c={self.close})"


# =============================================================================
# Binance API Helpers
# =============================================================================

def fetch_binance_klines(
    symbol: str,
    interval: str,
    limit: int,
    timeout: int = 15
) -> List[List]:
    """
    Fetch klines from Binance Futures API.

    Args:
        symbol: Trading pair (e.g., "BTCUSDT")
        interval: K-line interval (e.g., "15m", "4h", "1d")
        limit: Number of klines to fetch
        timeout: Request timeout in seconds

    Returns:
        List of kline data or empty list on failure
    """
    try:
        url = f"https://fapi.binance.com/fapi/v1/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        response = requests.get(url, params=params, timeout=timeout)
        if response.status_code == 200:
            return response.json()
        return []
    except (requests.RequestException, ValueError):
        return []


def create_bar_from_kline(kline: List, bar_type: str = "") -> MockBar:
    """
    Create a MockBar from Binance kline data.

    Args:
        kline: Binance kline array [timestamp, open, high, low, close, volume, ...]
        bar_type: Bar type string (for logging only)

    Returns:
        MockBar object
    """
    return MockBar(
        float(kline[1]),  # open
        float(kline[2]),  # high
        float(kline[3]),  # low
        float(kline[4]),  # close
        float(kline[5]),  # volume
        int(kline[0])     # timestamp
    )


def parse_bar_interval(bar_type_str: str) -> str:
    """
    Parse NautilusTrader bar type string to Binance interval.

    Args:
        bar_type_str: Like "BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-EXTERNAL"

    Returns:
        Binance interval like "15m", "4h", "1d"
    """
    # Check from longest to shortest to avoid substring matches
    # e.g., "15-MINUTE" should not match "5-MINUTE"
    if "15-MINUTE" in bar_type_str:
        return "15m"
    elif "5-MINUTE" in bar_type_str:
        return "5m"
    elif "1-MINUTE" in bar_type_str:
        return "1m"
    elif "4-HOUR" in bar_type_str:
        return "4h"
    elif "1-HOUR" in bar_type_str:
        return "1h"
    elif "1-DAY" in bar_type_str:
        return "1d"
    else:
        return "15m"  # Default


def extract_symbol(instrument_id: str) -> str:
    """
    Extract trading symbol from instrument ID.

    Args:
        instrument_id: Like "BTCUSDT-PERP.BINANCE"

    Returns:
        Symbol like "BTCUSDT"
    """
    return instrument_id.split('-')[0]


# =============================================================================
# Diagnostic Context (Shared State)
# =============================================================================

@dataclass
class DiagnosticContext:
    """
    Shared context for all diagnostic steps.

    Holds all data collected during the diagnostic process,
    eliminating the need for global variables.
    """

    # Configuration
    env: str = "production"
    summary_mode: bool = False
    export_mode: bool = False
    push_to_github: bool = False

    # Project paths
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent)

    # Strategy configuration (loaded from main_live.py)
    strategy_config: Any = None
    base_config: Dict = field(default_factory=dict)

    # Thresholds (loaded from config, not hardcoded)
    bb_overbought_threshold: float = 80.0
    bb_oversold_threshold: float = 20.0
    ls_ratio_extreme_bullish: float = 1.5
    ls_ratio_bullish: float = 1.2
    ls_ratio_extreme_bearish: float = 0.67
    ls_ratio_bearish: float = 0.83

    # Market data
    symbol: str = "BTCUSDT"
    interval: str = "15m"
    klines_raw: List = field(default_factory=list)
    current_price: float = 0.0
    snapshot_timestamp: str = ""

    # Indicator data
    indicator_manager: Any = None
    technical_data: Dict = field(default_factory=dict)

    # Position data
    current_position: Optional[Dict] = None
    account_balance: Dict = field(default_factory=dict)

    # Sentiment data
    sentiment_data: Dict = field(default_factory=dict)

    # Price data
    price_data: Dict = field(default_factory=dict)

    # MTF data
    order_flow_report: Optional[Dict] = None
    derivatives_report: Optional[Dict] = None
    orderbook_report: Optional[Dict] = None

    # AI decision data
    multi_agent: Any = None
    signal_data: Dict = field(default_factory=dict)
    final_signal: str = "HOLD"

    # Output buffer for export
    output_buffer: io.StringIO = field(default_factory=io.StringIO)
    original_stdout: Any = None

    # Step tracking
    current_step: int = 0
    total_steps: int = 19  # 17 main steps + 2 summary steps
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)
        print(f"  ❌ {message}")

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)
        print(f"  ⚠️ {message}")

    def print_step(self, title: str) -> None:
        """Print step header with progress."""
        self.current_step += 1
        print(f"[{self.current_step}/{self.total_steps}] {title}")

    def load_thresholds_from_config(self) -> None:
        """Load threshold values from base_config, with defaults."""
        indicators = self.base_config.get('indicators', {})

        self.bb_overbought_threshold = indicators.get('bb_overbought_threshold', 80.0)
        self.bb_oversold_threshold = indicators.get('bb_oversold_threshold', 20.0)
        self.ls_ratio_extreme_bullish = indicators.get('ls_ratio_extreme_bullish', 1.5)
        self.ls_ratio_bullish = indicators.get('ls_ratio_bullish', 1.2)
        self.ls_ratio_extreme_bearish = indicators.get('ls_ratio_extreme_bearish', 0.67)
        self.ls_ratio_bearish = indicators.get('ls_ratio_bearish', 0.83)


# =============================================================================
# Diagnostic Step Base Class
# =============================================================================

class DiagnosticStep(ABC):
    """
    Abstract base class for diagnostic steps.

    Each diagnostic step should inherit from this class and
    implement the run() method.
    """

    name: str = "Unnamed Step"
    description: str = ""

    def __init__(self, ctx: DiagnosticContext):
        self.ctx = ctx

    @abstractmethod
    def run(self) -> bool:
        """
        Execute the diagnostic step.

        Returns:
            True if step completed successfully, False otherwise
        """
        pass

    def should_skip(self) -> bool:
        """
        Check if this step should be skipped.

        Override in subclasses for conditional execution.
        """
        return False

    def print_header(self) -> None:
        """Print step header."""
        self.ctx.print_step(self.name)
        if self.description:
            print(f"  {self.description}")


# =============================================================================
# Diagnostic Runner
# =============================================================================

class DiagnosticRunner:
    """
    Main runner for the diagnostic system.

    Orchestrates all diagnostic steps in the correct order.
    """

    def __init__(
        self,
        env: str = "production",
        summary_mode: bool = False,
        export_mode: bool = False,
        push_to_github: bool = False
    ):
        self.ctx = DiagnosticContext(
            env=env,
            summary_mode=summary_mode,
            export_mode=export_mode,
            push_to_github=push_to_github
        )
        self.steps: List[DiagnosticStep] = []

    def add_step(self, step_class: type) -> None:
        """Add a diagnostic step."""
        self.steps.append(step_class(self.ctx))

    def setup_output_capture(self) -> None:
        """Setup output capture for export mode."""
        if self.ctx.export_mode:
            self.ctx.original_stdout = sys.stdout
            sys.stdout = TeeOutput(sys.stdout, self.ctx.output_buffer)

    def restore_output(self) -> None:
        """Restore original stdout."""
        if self.ctx.export_mode and self.ctx.original_stdout:
            sys.stdout = self.ctx.original_stdout

    def run_all(self) -> bool:
        """
        Run all diagnostic steps.

        Returns:
            True if all steps passed, False if any failed
        """
        try:
            self.setup_output_capture()

            print("=" * 70)
            print("  实盘信号诊断工具 v2.0 (模块化重构版)")
            print("  基于 TradingAgents v3.12 架构")
            print("=" * 70)
            print()

            success = True
            for step in self.steps:
                if step.should_skip():
                    print(f"  ⏭️ Skipped: {step.name}")
                    continue

                try:
                    step.print_header()
                    if not step.run():
                        success = False
                        self.ctx.add_error(f"Step failed: {step.name}")
                    print()
                except KeyboardInterrupt:
                    print("\n  用户中断")
                    raise
                except Exception as e:
                    success = False
                    self.ctx.add_error(f"Step {step.name} raised exception: {e}")
                    import traceback
                    traceback.print_exc()

            self._print_final_summary()
            return success

        finally:
            self.restore_output()

    def _print_final_summary(self) -> None:
        """Print final diagnostic summary."""
        print("=" * 70)
        print("  诊断完成")
        print("=" * 70)

        if self.ctx.errors:
            print(f"\n  ❌ 错误数: {len(self.ctx.errors)}")
            for error in self.ctx.errors[:5]:
                print(f"     • {error}")

        if self.ctx.warnings:
            print(f"\n  ⚠️ 警告数: {len(self.ctx.warnings)}")
            for warning in self.ctx.warnings[:5]:
                print(f"     • {warning}")

        if not self.ctx.errors and not self.ctx.warnings:
            print("\n  ✅ 所有检查通过")

    def export_results(self) -> Optional[Path]:
        """
        Export diagnostic results to file.

        Returns:
            Path to exported file, or None if not in export mode
        """
        if not self.ctx.export_mode:
            return None

        self.restore_output()

        logs_dir = self.ctx.project_root / "logs"
        logs_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"diagnosis_{timestamp}.txt"
        filepath = logs_dir / filename

        output_content = self.ctx.output_buffer.getvalue()
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(output_content)

        print()
        print("=" * 70)
        print("  📤 诊断结果导出")
        print("=" * 70)
        print(f"  ✅ 已保存到: {filepath}")
        print(f"  📊 文件大小: {len(output_content):,} 字符")

        if self.ctx.push_to_github:
            self._push_to_github(filepath, filename)

        return filepath

    def _push_to_github(self, filepath: Path, filename: str) -> None:
        """Push export file to GitHub."""
        import subprocess

        commit_msg = f"chore: Add diagnosis report {filename}"
        try:
            os.chdir(self.ctx.project_root)

            subprocess.run(['git', 'add', '-f', str(filepath)], check=True, capture_output=True)
            subprocess.run(['git', 'commit', '-m', commit_msg], check=True, capture_output=True)

            result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True, text=True, check=True
            )
            branch = result.stdout.strip()

            subprocess.run(['git', 'push', '-u', 'origin', branch], check=True, capture_output=True)

            print(f"  ✅ 已推送到 GitHub (分支: {branch})")
            print(f"  📎 文件路径: logs/{filename}")

        except subprocess.CalledProcessError as e:
            print(f"  ⚠️ Git 推送失败: {e}")
            print(f"     请手动提交: git add -f {filepath} && git commit -m '{commit_msg}' && git push")
