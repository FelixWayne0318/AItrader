"""
AI Signal Log Service
Tracks and stores AI analysis signals from Bull/Bear/Judge agents
"""
import os
import json
from datetime import datetime
from typing import Optional
from pathlib import Path


class SignalLogService:
    """Service for managing AI signal logs"""

    def __init__(self):
        self.log_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))) / "logs"
        self.signal_log_file = self.log_dir / "ai_signals.json"
        self._ensure_log_dir()

    def _ensure_log_dir(self):
        """Ensure log directory exists"""
        self.log_dir.mkdir(exist_ok=True)
        if not self.signal_log_file.exists():
            self._write_logs([])

    def _read_logs(self) -> list:
        """Read all signal logs"""
        try:
            if self.signal_log_file.exists():
                with open(self.signal_log_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error reading signal logs: {e}")
        return []

    def _write_logs(self, logs: list):
        """Write signal logs"""
        try:
            with open(self.signal_log_file, "w") as f:
                json.dump(logs, f, indent=2, default=str)
        except Exception as e:
            print(f"Error writing signal logs: {e}")

    def add_signal(
        self,
        symbol: str,
        bull_analysis: dict,
        bear_analysis: dict,
        judge_decision: dict,
        final_signal: str,
        confidence: str,
        market_data: Optional[dict] = None
    ) -> dict:
        """Add a new AI signal analysis log"""
        signal_entry = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S"),
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "bull_analysis": bull_analysis,
            "bear_analysis": bear_analysis,
            "judge_decision": judge_decision,
            "final_signal": final_signal,
            "confidence": confidence,
            "market_data": market_data or {}
        }

        logs = self._read_logs()
        logs.insert(0, signal_entry)  # Add to beginning

        # Keep only last 100 signals
        logs = logs[:100]

        self._write_logs(logs)
        return signal_entry

    def get_signals(self, limit: int = 20) -> list:
        """Get recent AI signals"""
        logs = self._read_logs()
        return logs[:limit]

    def get_signal_by_id(self, signal_id: str) -> Optional[dict]:
        """Get a specific signal by ID"""
        logs = self._read_logs()
        for log in logs:
            if log.get("id") == signal_id:
                return log
        return None

    def get_signal_stats(self) -> dict:
        """Get statistics about AI signals"""
        logs = self._read_logs()

        if not logs:
            return {
                "total_signals": 0,
                "buy_signals": 0,
                "sell_signals": 0,
                "hold_signals": 0,
                "high_confidence": 0,
                "medium_confidence": 0,
                "low_confidence": 0,
                "bull_bear_agreement": 0
            }

        buy_signals = len([l for l in logs if l.get("final_signal") == "BUY"])
        sell_signals = len([l for l in logs if l.get("final_signal") == "SELL"])
        hold_signals = len([l for l in logs if l.get("final_signal") == "HOLD"])

        high_conf = len([l for l in logs if l.get("confidence") == "HIGH"])
        medium_conf = len([l for l in logs if l.get("confidence") == "MEDIUM"])
        low_conf = len([l for l in logs if l.get("confidence") == "LOW"])

        # Calculate bull/bear agreement rate
        agreements = 0
        for log in logs:
            bull = log.get("bull_analysis", {}).get("signal", "")
            bear = log.get("bear_analysis", {}).get("signal", "")
            if bull == bear:
                agreements += 1

        agreement_rate = (agreements / len(logs) * 100) if logs else 0

        return {
            "total_signals": len(logs),
            "buy_signals": buy_signals,
            "sell_signals": sell_signals,
            "hold_signals": hold_signals,
            "high_confidence": high_conf,
            "medium_confidence": medium_conf,
            "low_confidence": low_conf,
            "bull_bear_agreement": round(agreement_rate, 1)
        }

    def clear_logs(self):
        """Clear all signal logs"""
        self._write_logs([])


# Singleton instance
_signal_log_service = None

def get_signal_log_service() -> SignalLogService:
    global _signal_log_service
    if _signal_log_service is None:
        _signal_log_service = SignalLogService()
    return _signal_log_service
