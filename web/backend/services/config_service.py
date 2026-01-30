"""
Configuration Service - Integrated with AItrader ConfigManager
Manages strategy configuration and system control
"""
import yaml
import subprocess
import re
import os
import sys
from pathlib import Path
from typing import Optional, Any, Dict, Tuple, List
from datetime import datetime

from core.config import settings

# Add AItrader root to path for importing ConfigManager
AITRADER_ROOT = settings.AITRADER_PATH
if str(AITRADER_ROOT) not in sys.path:
    sys.path.insert(0, str(AITRADER_ROOT))


class ConfigService:
    """Service for managing AItrader configuration and system control"""

    def __init__(self):
        self.aitrader_path = settings.AITRADER_PATH
        self.service_name = settings.AITRADER_SERVICE_NAME
        self.configs_path = self.aitrader_path / "configs"
        self.base_config_path = self.configs_path / "base.yaml"

        # Validate service name to prevent command injection
        if not re.match(r'^[a-z0-9-]+$', self.service_name):
            raise ValueError(
                f"Invalid service name: {self.service_name}. "
                "Service name must contain only lowercase letters, numbers, and hyphens."
            )

    # =========================================================================
    # Configuration Reading
    # =========================================================================
    def read_base_config(self) -> Dict:
        """Read base.yaml configuration"""
        try:
            if self.base_config_path.exists():
                with open(self.base_config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error reading base config: {e}")
        return {}

    def read_env_config(self, env: str = "production") -> Dict:
        """Read environment-specific config overlay"""
        env_path = self.configs_path / f"{env}.yaml"
        try:
            if env_path.exists():
                with open(env_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error reading {env} config: {e}")
        return {}

    def get_merged_config(self, env: str = "production") -> Dict:
        """Get merged configuration (base + environment overlay)"""
        base = self.read_base_config()
        overlay = self.read_env_config(env)
        return self._deep_merge(base, overlay)

    def _deep_merge(self, base: Dict, overlay: Dict) -> Dict:
        """Deep merge two dictionaries"""
        result = base.copy()
        for key, value in overlay.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def read_strategy_config(self) -> Dict:
        """Read strategy configuration - alias for get_merged_config"""
        return self.get_merged_config()

    # =========================================================================
    # Configuration Writing
    # =========================================================================
    def write_base_config(self, config: Dict) -> bool:
        """Write to base.yaml configuration"""
        try:
            # Backup current config
            if self.base_config_path.exists():
                backup_path = self.base_config_path.with_suffix(".yaml.bak")
                with open(self.base_config_path, "r") as f:
                    backup_content = f.read()
                with open(backup_path, "w") as f:
                    f.write(backup_content)

            # Write new config
            with open(self.base_config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            return True
        except Exception as e:
            print(f"Error writing config: {e}")
            return False

    def write_strategy_config(self, config: Dict) -> bool:
        """Write strategy configuration - alias for write_base_config"""
        return self.write_base_config(config)

    def update_config_value(self, path: str, value: Any) -> bool:
        """
        Update a specific value in the base configuration

        path: dot-separated path like "capital.leverage" or "risk.min_confidence_to_trade"
        """
        config = self.read_base_config()
        if not config:
            return False

        # Navigate to the parent and set the value
        keys = path.split(".")
        current = config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        # Type conversion based on existing value type
        old_value = current.get(keys[-1])
        if old_value is not None:
            if isinstance(old_value, bool):
                if isinstance(value, str):
                    value = value.lower() in ('true', '1', 'yes')
            elif isinstance(old_value, int) and not isinstance(old_value, bool):
                value = int(value)
            elif isinstance(old_value, float):
                value = float(value)

        current[keys[-1]] = value
        return self.write_base_config(config)

    def get_config_value(self, path: str, default: Any = None) -> Any:
        """Get a specific value from configuration"""
        config = self.get_merged_config()
        keys = path.split(".")
        current = config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    # =========================================================================
    # Configuration Sections (for UI)
    # =========================================================================
    def get_config_sections(self) -> Dict[str, Dict]:
        """Get configuration organized by sections for admin UI"""
        config = self.get_merged_config()

        sections = {
            "trading": {
                "title": "Trading Configuration",
                "description": "Core trading parameters",
                "fields": self._extract_section(config, "trading"),
            },
            "capital": {
                "title": "Capital & Leverage",
                "description": "Account funding and leverage settings",
                "fields": self._extract_section(config, "capital"),
            },
            "position": {
                "title": "Position Management",
                "description": "Position sizing and limits",
                "fields": self._extract_section(config, "position"),
            },
            "risk": {
                "title": "Risk Management",
                "description": "Stop loss, take profit, and risk controls",
                "fields": self._extract_section(config, "risk"),
            },
            "ai": {
                "title": "AI Configuration",
                "description": "DeepSeek and multi-agent settings",
                "fields": self._extract_section(config, "ai"),
            },
            "indicators": {
                "title": "Technical Indicators",
                "description": "Indicator periods and parameters",
                "fields": self._extract_section(config, "indicators"),
            },
            "telegram": {
                "title": "Telegram Notifications",
                "description": "Notification settings",
                "fields": self._extract_section(config, "telegram"),
            },
            "timing": {
                "title": "Timing",
                "description": "Timer and interval settings",
                "fields": self._extract_section(config, "timing"),
            },
            "logging": {
                "title": "Logging",
                "description": "Log levels and outputs",
                "fields": self._extract_section(config, "logging"),
            },
            "multi_timeframe": {
                "title": "Multi-Timeframe (MTF)",
                "description": "Three-layer MTF framework settings",
                "fields": self._extract_section(config, "multi_timeframe"),
            },
            "order_flow": {
                "title": "Order Flow",
                "description": "Order flow and derivatives data",
                "fields": self._extract_section(config, "order_flow"),
            },
        }

        return sections

    def _extract_section(self, config: Dict, section: str) -> Dict:
        """Extract a section from config with metadata"""
        return config.get(section, {})

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
        """Run basic diagnostics"""
        results = {
            "config_valid": False,
            "service_running": False,
            "binance_configured": False,
            "telegram_configured": False,
            "deepseek_configured": False,
            "errors": [],
        }

        # Check config
        try:
            config = self.get_merged_config()
            if config:
                results["config_valid"] = True
        except Exception as e:
            results["errors"].append(f"Config error: {e}")

        # Check service
        status = self.get_service_status()
        results["service_running"] = status.get("running", False)

        # Check API keys (from env file)
        env_path = Path.home() / ".env.aitrader"
        if env_path.exists():
            try:
                with open(env_path) as f:
                    content = f.read()
                    if "BINANCE_API_KEY=" in content and "BINANCE_API_SECRET=" in content:
                        results["binance_configured"] = True
                    if "TELEGRAM_BOT_TOKEN=" in content:
                        results["telegram_configured"] = True
                    if "DEEPSEEK_API_KEY=" in content:
                        results["deepseek_configured"] = True
            except Exception as e:
                results["errors"].append(f"Env file error: {e}")

        return results


# Singleton instance
config_service = ConfigService()
