"""
System Service - System control and diagnostics
Separated from ConfigService for security and maintainability
"""
import subprocess
import re
from pathlib import Path
from typing import Dict, Tuple
from datetime import datetime

from core.config import settings


class SystemService:
    """Service for system operations and diagnostics"""

    def __init__(self):
        self.aitrader_path = settings.AITRADER_PATH
        self.service_name = settings.AITRADER_SERVICE_NAME

        # Validate service name to prevent command injection
        if not re.match(r'^[a-z0-9-]+$', self.service_name):
            raise ValueError(
                f"Invalid service name: {self.service_name}. "
                "Service name must contain only lowercase letters, numbers, and hyphens."
            )

    # =========================================================================
    # Service Control
    # =========================================================================
    def get_service_status(self) -> Dict:
        """Get AItrader systemd service status"""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", self.service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            is_active = result.stdout.strip() == "active"

            # Get more details
            result = subprocess.run(
                ["systemctl", "show", self.service_name,
                 "--property=ActiveState,SubState,MainPID,MemoryCurrent,CPUUsageNSec,ExecMainStartTimestamp"],
                capture_output=True,
                text=True,
                timeout=5
            )
            props = {}
            for line in result.stdout.strip().split("\n"):
                if "=" in line:
                    k, v = line.split("=", 1)
                    props[k] = v

            # Parse uptime
            start_time = props.get("ExecMainStartTimestamp", "")
            uptime = ""
            if start_time and is_active:
                try:
                    # Parse format like "Thu 2024-01-30 10:00:00 UTC"
                    parts = start_time.split()
                    if len(parts) >= 3:
                        date_str = f"{parts[1]} {parts[2]}"
                        start_dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                        delta = datetime.now() - start_dt
                        hours, remainder = divmod(int(delta.total_seconds()), 3600)
                        minutes, seconds = divmod(remainder, 60)
                        if hours > 24:
                            days = hours // 24
                            hours = hours % 24
                            uptime = f"{days}d {hours}h {minutes}m"
                        else:
                            uptime = f"{hours}h {minutes}m {seconds}s"
                except Exception:
                    pass

            # Parse memory
            memory = props.get("MemoryCurrent", "0")
            try:
                memory_mb = int(memory) / (1024 * 1024)
                memory_str = f"{memory_mb:.1f} MB"
            except Exception:
                memory_str = "N/A"

            return {
                "running": is_active,
                "state": props.get("ActiveState", "unknown"),
                "sub_state": props.get("SubState", "unknown"),
                "pid": props.get("MainPID", "0"),
                "memory": memory_str,
                "uptime": uptime,
                "start_time": start_time,
            }
        except Exception as e:
            print(f"Error getting service status: {e}")
            return {
                "running": False,
                "state": "error",
                "sub_state": str(e),
                "pid": "0",
                "memory": "N/A",
                "uptime": "",
                "start_time": "",
            }

    def restart_service(self) -> Tuple[bool, str]:
        """Restart AItrader service"""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", self.service_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return True, "Service restarted successfully"
            else:
                return False, result.stderr or "Failed to restart service"
        except subprocess.TimeoutExpired:
            return False, "Restart command timed out"
        except Exception as e:
            return False, str(e)

    def stop_service(self) -> Tuple[bool, str]:
        """Stop AItrader service"""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "stop", self.service_name],
                capture_output=True,
                text=True,
                timeout=15
            )
            if result.returncode == 0:
                return True, "Service stopped successfully"
            else:
                return False, result.stderr or "Failed to stop service"
        except Exception as e:
            return False, str(e)

    def start_service(self) -> Tuple[bool, str]:
        """Start AItrader service"""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "start", self.service_name],
                capture_output=True,
                text=True,
                timeout=15
            )
            if result.returncode == 0:
                return True, "Service started successfully"
            else:
                return False, result.stderr or "Failed to start service"
        except Exception as e:
            return False, str(e)

    # =========================================================================
    # Logs
    # =========================================================================
    def get_recent_logs(self, lines: int = 100) -> str:
        """Get recent service logs from journalctl"""
        try:
            result = subprocess.run(
                ["journalctl", "-u", self.service_name, "-n", str(lines),
                 "--no-pager", "--no-hostname"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout
        except Exception as e:
            return f"Error fetching logs: {e}"

    def get_log_file_content(self, lines: int = 200) -> str:
        """Get recent logs from the log file"""
        log_path = self.aitrader_path / "logs" / "deepseek_strategy.log"
        try:
            if log_path.exists():
                with open(log_path, "r") as f:
                    all_lines = f.readlines()
                    return "".join(all_lines[-lines:])
            return "Log file not found"
        except Exception as e:
            return f"Error reading log file: {e}"

    # =========================================================================
    # System Info
    # =========================================================================
    def get_system_info(self) -> Dict:
        """Get system information"""
        info = {
            "aitrader_path": str(self.aitrader_path),
            "service_name": self.service_name,
            "python_version": "",
            "nautilus_version": "",
            "git_branch": "",
            "git_commit": "",
            "git_commit_date": "",
        }

        try:
            # Python version
            result = subprocess.run(
                [str(self.aitrader_path / "venv" / "bin" / "python"), "--version"],
                capture_output=True, text=True, timeout=5
            )
            info["python_version"] = result.stdout.strip()
        except Exception:
            pass

        try:
            # NautilusTrader version
            result = subprocess.run(
                [str(self.aitrader_path / "venv" / "bin" / "pip"), "show", "nautilus_trader"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.split("\n"):
                if line.startswith("Version:"):
                    info["nautilus_version"] = line.split(":")[1].strip()
                    break
        except Exception:
            pass

        try:
            # Git info
            result = subprocess.run(
                ["git", "-C", str(self.aitrader_path), "branch", "--show-current"],
                capture_output=True, text=True, timeout=5
            )
            info["git_branch"] = result.stdout.strip()

            result = subprocess.run(
                ["git", "-C", str(self.aitrader_path), "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5
            )
            info["git_commit"] = result.stdout.strip()

            result = subprocess.run(
                ["git", "-C", str(self.aitrader_path), "log", "-1", "--format=%ci"],
                capture_output=True, text=True, timeout=5
            )
            info["git_commit_date"] = result.stdout.strip()
        except Exception:
            pass

        return info

    # =========================================================================
    # Diagnostics
    # =========================================================================
    def run_diagnostics(self) -> Dict:
        """Run basic diagnostics and return checks in UI-friendly format"""
        checks = []

        # Import config_service to check config
        from services.config_service import config_service

        # Check config
        config_valid = False
        try:
            config = config_service.get_merged_config()
            if config:
                config_valid = True
                checks.append({
                    "name": "Configuration",
                    "status": "pass",
                    "message": "configs/base.yaml loaded successfully"
                })
            else:
                checks.append({
                    "name": "Configuration",
                    "status": "fail",
                    "message": "Failed to load configuration"
                })
        except Exception as e:
            checks.append({
                "name": "Configuration",
                "status": "fail",
                "message": f"Config error: {e}"
            })

        # Check service
        status = self.get_service_status()
        service_running = status.get("running", False)
        if service_running:
            checks.append({
                "name": "Trading Service",
                "status": "pass",
                "message": f"nautilus-trader is running (PID: {status.get('pid', 'N/A')})"
            })
        else:
            checks.append({
                "name": "Trading Service",
                "status": "fail",
                "message": f"Service is not running (state: {status.get('state', 'unknown')})"
            })

        # Check API keys (from env file)
        env_path = Path.home() / ".env.aitrader"
        binance_configured = False
        telegram_configured = False
        deepseek_configured = False

        if env_path.exists():
            try:
                with open(env_path) as f:
                    content = f.read()
                    if "BINANCE_API_KEY=" in content and "BINANCE_API_SECRET=" in content:
                        # Check if they have actual values (not empty)
                        binance_configured = "BINANCE_API_KEY=\"\"" not in content and "BINANCE_API_KEY=''" not in content
                    if "TELEGRAM_BOT_TOKEN=" in content:
                        telegram_configured = "TELEGRAM_BOT_TOKEN=\"\"" not in content
                    if "DEEPSEEK_API_KEY=" in content:
                        deepseek_configured = "DEEPSEEK_API_KEY=\"\"" not in content

                checks.append({
                    "name": "Environment File",
                    "status": "pass",
                    "message": "~/.env.aitrader found"
                })
            except Exception as e:
                checks.append({
                    "name": "Environment File",
                    "status": "fail",
                    "message": f"Error reading env file: {e}"
                })
        else:
            checks.append({
                "name": "Environment File",
                "status": "fail",
                "message": "~/.env.aitrader not found"
            })

        # Binance API
        if binance_configured:
            checks.append({
                "name": "Binance API",
                "status": "pass",
                "message": "API credentials configured"
            })
        else:
            checks.append({
                "name": "Binance API",
                "status": "fail",
                "message": "BINANCE_API_KEY or BINANCE_API_SECRET not set"
            })

        # DeepSeek API
        if deepseek_configured:
            checks.append({
                "name": "DeepSeek AI",
                "status": "pass",
                "message": "API key configured"
            })
        else:
            checks.append({
                "name": "DeepSeek AI",
                "status": "fail",
                "message": "DEEPSEEK_API_KEY not set"
            })

        # Telegram
        if telegram_configured:
            checks.append({
                "name": "Telegram Bot",
                "status": "pass",
                "message": "Bot token configured"
            })
        else:
            checks.append({
                "name": "Telegram Bot",
                "status": "warn",
                "message": "TELEGRAM_BOT_TOKEN not set (optional)"
            })

        # Check log directory
        log_dir = self.aitrader_path / "logs"
        if log_dir.exists():
            checks.append({
                "name": "Log Directory",
                "status": "pass",
                "message": f"{log_dir} exists"
            })
        else:
            checks.append({
                "name": "Log Directory",
                "status": "warn",
                "message": "logs/ directory not found"
            })

        # Check venv
        venv_python = self.aitrader_path / "venv" / "bin" / "python"
        if venv_python.exists():
            checks.append({
                "name": "Python Virtual Environment",
                "status": "pass",
                "message": "venv/bin/python exists"
            })
        else:
            checks.append({
                "name": "Python Virtual Environment",
                "status": "fail",
                "message": "venv not found - run setup.sh"
            })

        return {"checks": checks}


# Singleton instance
_system_service = None

def get_system_service() -> SystemService:
    global _system_service
    if _system_service is None:
        _system_service = SystemService()
    return _system_service
