"""
Notification Service
Manages system notifications and Telegram message history
"""
import os
import json
from datetime import datetime
from typing import Optional, Literal
from pathlib import Path


NotificationType = Literal["trade", "signal", "error", "warning", "info", "system"]


class NotificationService:
    """Service for managing notifications"""

    def __init__(self):
        self.log_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))) / "logs"
        self.notification_file = self.log_dir / "notifications.json"
        self._ensure_log_dir()

    def _ensure_log_dir(self):
        """Ensure log directory exists"""
        self.log_dir.mkdir(exist_ok=True)
        if not self.notification_file.exists():
            self._write_notifications([])

    def _read_notifications(self) -> list:
        """Read all notifications"""
        try:
            if self.notification_file.exists():
                with open(self.notification_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error reading notifications: {e}")
        return []

    def _write_notifications(self, notifications: list):
        """Write notifications"""
        try:
            with open(self.notification_file, "w") as f:
                json.dump(notifications, f, indent=2, default=str)
        except Exception as e:
            print(f"Error writing notifications: {e}")

    def add_notification(
        self,
        title: str,
        message: str,
        notification_type: NotificationType = "info",
        data: Optional[dict] = None,
        sent_to_telegram: bool = False
    ) -> dict:
        """Add a new notification"""
        notification = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "timestamp": datetime.now().isoformat(),
            "title": title,
            "message": message,
            "type": notification_type,
            "data": data or {},
            "sent_to_telegram": sent_to_telegram,
            "read": False
        }

        notifications = self._read_notifications()
        notifications.insert(0, notification)

        # Keep only last 200 notifications
        notifications = notifications[:200]

        self._write_notifications(notifications)
        return notification

    def get_notifications(
        self,
        limit: int = 50,
        notification_type: Optional[str] = None,
        unread_only: bool = False
    ) -> list:
        """Get notifications with optional filtering"""
        notifications = self._read_notifications()

        if notification_type:
            notifications = [n for n in notifications if n.get("type") == notification_type]

        if unread_only:
            notifications = [n for n in notifications if not n.get("read", False)]

        return notifications[:limit]

    def mark_as_read(self, notification_id: str) -> bool:
        """Mark a notification as read"""
        notifications = self._read_notifications()

        for n in notifications:
            if n.get("id") == notification_id:
                n["read"] = True
                self._write_notifications(notifications)
                return True

        return False

    def mark_all_as_read(self) -> int:
        """Mark all notifications as read"""
        notifications = self._read_notifications()
        count = 0

        for n in notifications:
            if not n.get("read", False):
                n["read"] = True
                count += 1

        self._write_notifications(notifications)
        return count

    def get_unread_count(self) -> int:
        """Get count of unread notifications"""
        notifications = self._read_notifications()
        return len([n for n in notifications if not n.get("read", False)])

    def delete_notification(self, notification_id: str) -> bool:
        """Delete a notification"""
        notifications = self._read_notifications()
        original_len = len(notifications)

        notifications = [n for n in notifications if n.get("id") != notification_id]

        if len(notifications) < original_len:
            self._write_notifications(notifications)
            return True
        return False

    def clear_all(self):
        """Clear all notifications"""
        self._write_notifications([])


def create_demo_notifications():
    """Create demo notification data"""
    service = NotificationService()

    demo_notifications = [
        {
            "id": "20250130143500000001",
            "timestamp": "2025-01-30T14:35:00",
            "title": "Trade Executed",
            "message": "LONG BTCUSDT @ 104,250.50 | Size: 0.015 BTC | SL: 102,165 | TP: 107,417",
            "type": "trade",
            "data": {
                "symbol": "BTCUSDT",
                "side": "LONG",
                "entry": 104250.50,
                "size": 0.015,
                "sl": 102165,
                "tp": 107417
            },
            "sent_to_telegram": True,
            "read": False
        },
        {
            "id": "20250130143000000001",
            "timestamp": "2025-01-30T14:30:00",
            "title": "AI Signal Generated",
            "message": "BUY signal with MEDIUM confidence. Bull/Bear analysis complete.",
            "type": "signal",
            "data": {
                "signal": "BUY",
                "confidence": "MEDIUM",
                "bull_score": 4,
                "bear_score": 2
            },
            "sent_to_telegram": True,
            "read": False
        },
        {
            "id": "20250130120000000001",
            "timestamp": "2025-01-30T12:00:00",
            "title": "Position Closed",
            "message": "BTCUSDT position closed. PnL: +$125.50 (+1.2%)",
            "type": "trade",
            "data": {
                "symbol": "BTCUSDT",
                "pnl": 125.50,
                "pnl_percent": 1.2
            },
            "sent_to_telegram": True,
            "read": True
        },
        {
            "id": "20250130090000000001",
            "timestamp": "2025-01-30T09:00:00",
            "title": "Bot Started",
            "message": "AItrader bot started successfully. Environment: production",
            "type": "system",
            "data": {
                "environment": "production",
                "version": "1.0.0"
            },
            "sent_to_telegram": True,
            "read": True
        },
        {
            "id": "20250129200000000001",
            "timestamp": "2025-01-29T20:00:00",
            "title": "API Warning",
            "message": "Binance API rate limit approaching. Reducing request frequency.",
            "type": "warning",
            "data": {
                "rate_limit_used": "85%"
            },
            "sent_to_telegram": False,
            "read": True
        },
        {
            "id": "20250129180000000001",
            "timestamp": "2025-01-29T18:00:00",
            "title": "Configuration Updated",
            "message": "Stop loss percentage changed from 2% to 1.5%",
            "type": "info",
            "data": {
                "setting": "sl_buffer_pct",
                "old_value": 0.02,
                "new_value": 0.015
            },
            "sent_to_telegram": False,
            "read": True
        }
    ]

    service._write_notifications(demo_notifications)
    return demo_notifications


# Singleton instance
_notification_service = None

def get_notification_service() -> NotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
