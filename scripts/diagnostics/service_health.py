# scripts/diagnostics/service_health.py
"""
服务健康检查模块 v2.4.7

新增诊断项:
- [A] 服务运行状态检查 (systemd, memory, logs)
- [B] API 健康检查 (响应时间, 错误率)
- [C] 交易暂停状态检查
- [D] 历史信号追踪
"""

import os
import time
import subprocess
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from .base import DiagnosticStep


class ServiceHealthCheck(DiagnosticStep):
    """
    [新增 A] 服务运行状态检查

    检查项:
    - systemd 服务状态
    - 进程内存使用
    - 最近日志错误计数
    - 上次重启时间
    """

    name = "服务运行状态检查"
    step_number = "0"  # 放在最前面

    def run(self) -> bool:
        print()
        print("  📊 Systemd 服务状态:")

        # Check if running on server (has systemctl)
        try:
            # Get service status
            result = subprocess.run(
                ["systemctl", "is-active", "nautilus-trader"],
                capture_output=True,
                text=True,
                timeout=5
            )
            status = result.stdout.strip()

            if status == "active":
                print("     ✅ nautilus-trader: 运行中")

                # Get uptime
                result = subprocess.run(
                    ["systemctl", "show", "nautilus-trader", "--property=ActiveEnterTimestamp"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                timestamp_line = result.stdout.strip()
                if "=" in timestamp_line:
                    timestamp_str = timestamp_line.split("=")[1]
                    print(f"     启动时间: {timestamp_str}")

            elif status == "inactive":
                print("     ⚠️ nautilus-trader: 未运行")
            else:
                print(f"     ❓ nautilus-trader: {status}")

        except FileNotFoundError:
            print("     ℹ️ systemctl 不可用 (可能在开发环境)")
        except subprocess.TimeoutExpired:
            print("     ⚠️ systemctl 超时")
        except Exception as e:
            print(f"     ⚠️ 检查失败: {e}")

        # Check recent log errors
        print()
        print("  📋 最近日志错误统计:")
        try:
            # Count errors in last 10 minutes
            result = subprocess.run(
                ["journalctl", "-u", "nautilus-trader", "--since", "10 min ago", "--no-pager"],
                capture_output=True,
                text=True,
                timeout=10
            )
            log_content = result.stdout

            error_count = log_content.lower().count("error")
            warning_count = log_content.lower().count("warning")
            panic_count = log_content.lower().count("panic")

            if panic_count > 0:
                print(f"     🔴 PANIC: {panic_count} (严重!)")
            if error_count > 0:
                print(f"     🔴 ERROR: {error_count}")
            else:
                print(f"     ✅ ERROR: 0")
            if warning_count > 0:
                print(f"     🟡 WARNING: {warning_count}")
            else:
                print(f"     ✅ WARNING: 0")

        except FileNotFoundError:
            print("     ℹ️ journalctl 不可用")
        except subprocess.TimeoutExpired:
            print("     ⚠️ journalctl 超时")
        except Exception as e:
            print(f"     ⚠️ 日志检查失败: {e}")

        # Check memory usage (if possible)
        print()
        print("  💾 进程资源使用:")
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=5
            )
            for line in result.stdout.split('\n'):
                if 'main_live.py' in line or 'nautilus' in line.lower():
                    parts = line.split()
                    if len(parts) >= 6:
                        cpu = parts[2]
                        mem = parts[3]
                        print(f"     CPU: {cpu}%, MEM: {mem}%")
                        break
            else:
                print("     ℹ️ 未找到运行中的进程")
        except Exception as e:
            print(f"     ⚠️ 资源检查失败: {e}")

        return True


class APIHealthCheck(DiagnosticStep):
    """
    [新增 B] API 健康检查

    检查项:
    - Binance API 响应时间
    - DeepSeek API 响应时间
    - Coinalyze API 响应时间
    """

    name = "API 健康检查 (响应时间)"
    step_number = "0.5"

    def run(self) -> bool:
        import requests

        print()
        print("  🌐 API 响应时间测试:")

        apis = [
            ("Binance Futures", "https://fapi.binance.com/fapi/v1/ping", 2),
            ("Binance Spot", "https://api.binance.com/api/v3/ping", 2),
        ]

        for name, url, timeout in apis:
            try:
                start = time.time()
                resp = requests.get(url, timeout=timeout)
                elapsed = (time.time() - start) * 1000

                if resp.status_code == 200:
                    status = "✅" if elapsed < 500 else "🟡" if elapsed < 1000 else "🔴"
                    print(f"     {status} {name}: {elapsed:.0f}ms")
                else:
                    print(f"     🔴 {name}: HTTP {resp.status_code}")
            except requests.Timeout:
                print(f"     🔴 {name}: 超时 (>{timeout}s)")
            except Exception as e:
                print(f"     🔴 {name}: {str(e)[:50]}")

        # Test DeepSeek API (just connectivity, not actual call)
        try:
            start = time.time()
            resp = requests.get(
                "https://api.deepseek.com",
                timeout=3,
                headers={"User-Agent": "AItrader-diagnostic"}
            )
            elapsed = (time.time() - start) * 1000
            # Any response means network is reachable
            print(f"     ✅ DeepSeek API: {elapsed:.0f}ms (连通性)")
        except requests.Timeout:
            print(f"     🔴 DeepSeek API: 超时")
        except Exception as e:
            print(f"     🟡 DeepSeek API: {str(e)[:40]}")

        # Test Coinalyze (if API key exists)
        coinalyze_key = os.getenv('COINALYZE_API_KEY')
        if coinalyze_key:
            try:
                start = time.time()
                resp = requests.get(
                    "https://api.coinalyze.net/v1/ping",
                    timeout=3,
                    headers={"api_key": coinalyze_key}
                )
                elapsed = (time.time() - start) * 1000
                if resp.status_code == 200:
                    print(f"     ✅ Coinalyze API: {elapsed:.0f}ms")
                else:
                    print(f"     🟡 Coinalyze API: HTTP {resp.status_code}")
            except Exception as e:
                print(f"     🟡 Coinalyze API: {str(e)[:40]}")
        else:
            print(f"     ℹ️ Coinalyze API: 未配置 key")

        return True


class TradingStateCheck(DiagnosticStep):
    """
    [新增 C] 交易暂停状态检查

    检查项:
    - is_trading_paused 状态
    - _timer_lock 状态 (如果可检测)
    """

    name = "交易状态检查"
    step_number = "9.5"  # 在持仓检查后

    def run(self) -> bool:
        print()
        print("  🔒 交易控制状态:")

        # Check if there's a pause file or state file
        pause_file = "/home/linuxuser/nautilus_AItrader/data/trading_paused"
        state_file = "/home/linuxuser/nautilus_AItrader/data/trading_state.json"

        if os.path.exists(pause_file):
            print("     ⏸️ 交易已暂停 (pause file exists)")
            try:
                with open(pause_file, 'r') as f:
                    reason = f.read().strip()
                    if reason:
                        print(f"     暂停原因: {reason}")
            except:
                pass
        else:
            print("     ✅ 交易未暂停 (无 pause file)")

        # Check state file if exists
        if os.path.exists(state_file):
            try:
                import json
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    paused = state.get('is_trading_paused', False)
                    if paused:
                        print(f"     ⏸️ state file 显示: 已暂停")
                        print(f"     暂停原因: {state.get('pause_reason', 'N/A')}")
                    else:
                        print(f"     ✅ state file 显示: 正常交易")
            except Exception as e:
                print(f"     ⚠️ state file 读取失败: {e}")

        # Check min_confidence setting
        min_conf = getattr(self.ctx.strategy_config, 'min_confidence_to_trade', 'MEDIUM')
        print(f"     最低信心要求: {min_conf}")

        return True


class SignalHistoryCheck(DiagnosticStep):
    """
    [新增 D] 历史信号追踪

    检查项:
    - 最近信号记录
    - 信号执行结果
    """

    name = "历史信号追踪"
    step_number = "15.5"  # 在诊断总结后

    def run(self) -> bool:
        print()
        print("  📜 最近信号记录:")

        # Check signal history file
        signal_history_file = "/home/linuxuser/nautilus_AItrader/data/signal_history.json"

        if os.path.exists(signal_history_file):
            try:
                import json
                with open(signal_history_file, 'r') as f:
                    history = json.load(f)

                if isinstance(history, list) and len(history) > 0:
                    recent = history[-5:]  # Last 5 signals
                    print(f"     总记录: {len(history)} 条")
                    print()
                    for i, sig in enumerate(reversed(recent), 1):
                        ts = sig.get('timestamp', 'N/A')
                        signal = sig.get('signal', 'N/A')
                        conf = sig.get('confidence', 'N/A')
                        executed = sig.get('executed', 'N/A')
                        reason = sig.get('reason', '')

                        status = "✅" if executed else "❌"
                        print(f"     [{i}] {ts[:19] if len(ts) > 19 else ts}")
                        print(f"         Signal: {signal} ({conf}) {status}")
                        if reason and not executed:
                            print(f"         原因: {reason[:50]}")
                else:
                    print("     ℹ️ 无信号记录")
            except Exception as e:
                print(f"     ⚠️ 读取失败: {e}")
        else:
            print("     ℹ️ 信号历史文件不存在")
            print("     → 这是正常的，实盘运行后会自动创建")

        # Also check position snapshots
        snapshots_dir = "/home/linuxuser/nautilus_AItrader/data/position_snapshots"
        if os.path.exists(snapshots_dir):
            try:
                files = sorted(os.listdir(snapshots_dir))[-5:]
                if files:
                    print()
                    print("  📊 最近持仓快照:")
                    for f in files:
                        print(f"     - {f}")
            except Exception as e:
                print(f"     ⚠️ 快照目录读取失败: {e}")

        return True
