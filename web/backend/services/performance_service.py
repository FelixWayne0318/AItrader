"""
Performance Analytics Service
Calculates trading statistics, risk metrics, and performance data
"""
import os
import sys
from datetime import datetime, timedelta
from typing import Optional
import hmac
import hashlib
import time
import httpx

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from dotenv import load_dotenv

# Load environment variables
env_path = os.path.expanduser("~/.env.aitrader")
if os.path.exists(env_path):
    load_dotenv(env_path)


class PerformanceService:
    """Service for calculating trading performance metrics"""

    def __init__(self):
        self.api_key = os.getenv("BINANCE_API_KEY", "")
        self.api_secret = os.getenv("BINANCE_API_SECRET", "")
        self.base_url = "https://fapi.binance.com"

    def _sign_request(self, params: dict) -> dict:
        """Sign request with HMAC SHA256"""
        params["timestamp"] = int(time.time() * 1000)
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    async def get_trade_history(self, symbol: str = "BTCUSDT", limit: int = 100) -> list:
        """Get trade history from Binance Futures"""
        if not self.api_key or not self.api_secret:
            return []

        try:
            params = self._sign_request({"symbol": symbol, "limit": limit})
            headers = {"X-MBX-APIKEY": self.api_key}

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/fapi/v1/userTrades",
                    params=params,
                    headers=headers,
                    timeout=10.0
                )

                if response.status_code == 200:
                    return response.json()
                return []
        except Exception as e:
            print(f"Error fetching trade history: {e}")
            return []

    async def get_income_history(self, income_type: Optional[str] = None, limit: int = 100) -> list:
        """Get income history (PnL, funding fees, etc.)"""
        if not self.api_key or not self.api_secret:
            return []

        try:
            params = {"limit": limit}
            if income_type:
                params["incomeType"] = income_type
            params = self._sign_request(params)
            headers = {"X-MBX-APIKEY": self.api_key}

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/fapi/v1/income",
                    params=params,
                    headers=headers,
                    timeout=10.0
                )

                if response.status_code == 200:
                    return response.json()
                return []
        except Exception as e:
            print(f"Error fetching income history: {e}")
            return []

    async def get_performance_stats(self) -> dict:
        """Calculate comprehensive performance statistics"""
        trades = await self.get_trade_history(limit=500)
        income = await self.get_income_history(income_type="REALIZED_PNL", limit=500)

        # Calculate basic stats
        total_trades = len(trades)

        if not income:
            return {
                "total_trades": total_trades,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "total_pnl_percent": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "profit_factor": 0,
                "max_drawdown": 0,
                "max_drawdown_percent": 0,
                "sharpe_ratio": 0,
                "best_trade": 0,
                "worst_trade": 0,
                "avg_trade_duration": "0h",
                "today_pnl": 0,
                "week_pnl": 0,
                "month_pnl": 0,
                "equity_curve": []
            }

        # Parse PnL values
        pnl_values = [float(i["income"]) for i in income]

        winning_trades = len([p for p in pnl_values if p > 0])
        losing_trades = len([p for p in pnl_values if p < 0])

        total_pnl = sum(pnl_values)
        win_rate = (winning_trades / len(pnl_values) * 100) if pnl_values else 0

        # Calculate averages
        wins = [p for p in pnl_values if p > 0]
        losses = [p for p in pnl_values if p < 0]

        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0

        # Profit factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # Max drawdown calculation
        cumulative = []
        running_total = 0
        peak = 0
        max_dd = 0

        for pnl in pnl_values:
            running_total += pnl
            cumulative.append(running_total)
            if running_total > peak:
                peak = running_total
            dd = peak - running_total
            if dd > max_dd:
                max_dd = dd

        # Sharpe ratio (simplified, assuming risk-free rate = 0)
        import statistics
        if len(pnl_values) > 1:
            avg_return = statistics.mean(pnl_values)
            std_return = statistics.stdev(pnl_values)
            sharpe_ratio = (avg_return / std_return) * (252 ** 0.5) if std_return > 0 else 0
        else:
            sharpe_ratio = 0

        # Best/worst trades
        best_trade = max(pnl_values) if pnl_values else 0
        worst_trade = min(pnl_values) if pnl_values else 0

        # Time-based PnL
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=now.weekday())
        month_start = today_start.replace(day=1)

        today_pnl = 0
        week_pnl = 0
        month_pnl = 0

        for i in income:
            ts = datetime.fromtimestamp(i["time"] / 1000)
            pnl = float(i["income"])

            if ts >= today_start:
                today_pnl += pnl
            if ts >= week_start:
                week_pnl += pnl
            if ts >= month_start:
                month_pnl += pnl

        # Build equity curve data (last 30 days)
        equity_curve = []
        daily_pnl = {}

        for i in income:
            ts = datetime.fromtimestamp(i["time"] / 1000)
            date_str = ts.strftime("%Y-%m-%d")
            pnl = float(i["income"])

            if date_str not in daily_pnl:
                daily_pnl[date_str] = 0
            daily_pnl[date_str] += pnl

        # Sort and build cumulative
        sorted_dates = sorted(daily_pnl.keys())
        cumulative_pnl = 0
        for date_str in sorted_dates[-30:]:  # Last 30 days
            cumulative_pnl += daily_pnl[date_str]
            equity_curve.append({
                "date": date_str,
                "pnl": round(daily_pnl[date_str], 2),
                "cumulative": round(cumulative_pnl, 2)
            })

        return {
            "total_trades": len(pnl_values),
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_percent": 0,  # Would need initial balance to calculate
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown": round(max_dd, 2),
            "max_drawdown_percent": 0,  # Would need peak equity to calculate
            "sharpe_ratio": round(sharpe_ratio, 2),
            "best_trade": round(best_trade, 2),
            "worst_trade": round(worst_trade, 2),
            "avg_trade_duration": "N/A",
            "today_pnl": round(today_pnl, 2),
            "week_pnl": round(week_pnl, 2),
            "month_pnl": round(month_pnl, 2),
            "equity_curve": equity_curve
        }

    async def get_recent_trades_formatted(self, limit: int = 20) -> list:
        """Get recent trades formatted for timeline display"""
        income = await self.get_income_history(income_type="REALIZED_PNL", limit=limit)

        formatted_trades = []
        for i in income:
            ts = datetime.fromtimestamp(i["time"] / 1000)
            pnl = float(i["income"])

            formatted_trades.append({
                "id": i.get("tranId", ""),
                "symbol": i.get("symbol", "BTCUSDT"),
                "time": ts.isoformat(),
                "time_display": ts.strftime("%m/%d %H:%M"),
                "pnl": round(pnl, 2),
                "pnl_percent": 0,  # Would need entry price to calculate
                "side": "LONG" if pnl > 0 else "SHORT",  # Simplified
                "is_profit": pnl > 0
            })

        return formatted_trades


# Singleton instance
_performance_service = None

def get_performance_service() -> PerformanceService:
    global _performance_service
    if _performance_service is None:
        _performance_service = PerformanceService()
    return _performance_service
