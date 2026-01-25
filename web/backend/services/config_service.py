"""
Configuration Service - Read/Write AItrader configuration
"""
import yaml
import subprocess
import re
from pathlib import Path
from typing import Optional, Any

from core.config import settings


class ConfigService:
    """Service for managing AItrader configuration"""

    def __init__(self):
        self.config_path = settings.aitrader_config_path
        self.service_name = settings.AITRADER_SERVICE_NAME

        # Validate service name to prevent command injection
        if not re.match(r'^[a-z0-9-]+$', self.service_name):
            raise ValueError(
                f"Invalid service name: {self.service_name}. "
                "Service name must contain only lowercase letters, numbers, and hyphens."
            )

    def read_strategy_config(self) -> dict:
        """Read strategy configuration from YAML file"""
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error reading config: {e}")
        return {}

    def write_strategy_config(self, config: dict) -> bool:
        """Write strategy configuration to YAML file"""
        try:
            # Backup current config
            if self.config_path.exists():
                backup_path = self.config_path.with_suffix(".yaml.bak")
                with open(self.config_path, "r") as f:
                    backup_content = f.read()
                with open(backup_path, "w") as f:
                    f.write(backup_content)

            # Write new config
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            return True
        except Exception as e:
            print(f"Error writing config: {e}")
            return False

    def update_config_value(self, path: str, value: Any) -> bool:
        """
        Update a specific value in the configuration

        path: dot-separated path like "equity.leverage" or "risk.min_confidence_to_trade"
        """
        config = self.read_strategy_config()
        if not config:
            return False

        # Navigate to the parent and set the value
        keys = path.split(".")
        current = config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value
        return self.write_strategy_config(config)

    def get_config_value(self, path: str, default: Any = None) -> Any:
        """Get a specific value from configuration"""
        config = self.read_strategy_config()
        keys = path.split(".")
        current = config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    def get_service_status(self) -> dict:
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
                ["systemctl", "show", self.service_name, "--property=ActiveState,SubState,MainPID"],
                capture_output=True,
                text=True,
                timeout=5
            )
            props = {}
            for line in result.stdout.strip().split("\n"):
                if "=" in line:
                    k, v = line.split("=", 1)
                    props[k] = v

            return {
                "running": is_active,
                "state": props.get("ActiveState", "unknown"),
                "sub_state": props.get("SubState", "unknown"),
                "pid": props.get("MainPID", "0"),
            }
        except Exception as e:
            print(f"Error getting service status: {e}")
            return {
                "running": False,
                "state": "error",
                "sub_state": str(e),
                "pid": "0",
            }

    def restart_service(self) -> tuple[bool, str]:
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

    def stop_service(self) -> tuple[bool, str]:
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

    def start_service(self) -> tuple[bool, str]:
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

    def get_recent_logs(self, lines: int = 100) -> str:
        """Get recent service logs"""
        try:
            result = subprocess.run(
                ["journalctl", "-u", self.service_name, "-n", str(lines), "--no-pager", "--no-hostname"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout
        except Exception as e:
            return f"Error fetching logs: {e}"


# Singleton instance
config_service = ConfigService()
