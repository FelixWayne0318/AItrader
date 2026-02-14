"""
Performance Analytics Service
Calculates trading statistics, risk metrics, and performance data

v3.0.1 Update: Uses official libraries for all metrics calculations
- empyrical-reloaded: Sharpe/Sortino/Calmar/MDD/VaR (Python 3.12 compatible)
- scipy: Bootstrap confidence intervals
- statsmodels: Multiple hypothesis testing correction

See: docs/research/EVALUATION_FRAMEWORK.md
"""
import os
import sys
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import hmac
import hashlib
import time
import httpx
import logging

import numpy as np
import pandas as pd

# Official libraries for performance metrics (v3.0.1)
# DO NOT self-implement these calculations - use official libraries!
try:
    import empyrical as ep
    EMPYRICAL_AVAILABLE = True
except ImportError:
    EMPYRICAL_AVAILABLE = False
    logging.warning("empyrical not installed. Run: pip install empyrical-reloaded>=0.5.12")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from dotenv import load_dotenv

# Load environment variables from multiple possible locations
env_paths = [
    os.path.expanduser("~/.env.aitrader"),
    os.path.join(os.path.dirname(__file__), "../../../.env"),
    os.path.join(os.path.dirname(__file__), "../.env"),
    ".env"
]

for env_path in env_paths:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        logger.info(f"Loaded env from: {env_path}")
        break


class PerformanceService:
    """Service for calculating trading performance metrics"""

    def __init__(self):
        self.api_key = os.getenv("BINANCE_API_KEY", "")
        self.api_secret = os.getenv("BINANCE_API_SECRET", "")
        self.base_url = "https://fapi.binance.com"

        # Log credential status (without revealing actual keys)
        if self.api_key:
            logger.info(f"API Key loaded: {self.api_key[:8]}...{self.api_key[-4:]}")
        else:
            logger.warning("BINANCE_API_KEY not found!")
        if self.api_secret:
            logger.info(f"API Secret loaded: {self.api_secret[:4]}...{self.api_secret[-4:]}")
        else:
            logger.warning("BINANCE_API_SECRET not found!")

    async def check_connection(self) -> dict:
        """Diagnostic: Check API connectivity and credentials"""
        result = {
            "api_key_loaded": bool(self.api_key),
            "api_secret_loaded": bool(self.api_secret),
            "api_key_preview": f"{self.api_key[:8]}...{self.api_key[-4:]}" if self.api_key else None,
            "connection_ok": False,
            "account_accessible": False,
            "balance": 0,
            "error": None
        }

        if not self.api_key or not self.api_secret:
            result["error"] = "API credentials not loaded"
            return result

        try:
            # Test connection with account balance
            params = self._sign_request({})
            headers = {"X-MBX-APIKEY": self.api_key}

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/fapi/v2/balance",
                    params=params,
                    headers=headers,
                    timeout=10.0
                )

                result["connection_ok"] = True

                if response.status_code == 200:
                    balances = response.json()
                    result["account_accessible"] = True
                    # Find USDT balance
                    for b in balances:
                        if b.get("asset") == "USDT":
                            result["balance"] = float(b.get("balance", 0))
                            break
                else:
                    result["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Connection check failed: {e}")

        return result

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

    async def _get_initial_equity(self) -> float:
        """
        Get initial equity for returns calculation.
        Uses current USDT balance as a proxy for initial equity.

        Returns:
            float: Initial equity in USDT (default 1000 if unavailable)
        """
        if not self.api_key or not self.api_secret:
            return 1000.0  # Default fallback

        try:
            params = self._sign_request({})
            headers = {"X-MBX-APIKEY": self.api_key}

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/fapi/v2/balance",
                    params=params,
                    headers=headers,
                    timeout=10.0
                )

                if response.status_code == 200:
                    balances = response.json()
                    for b in balances:
                        if b.get("asset") == "USDT":
                            balance = float(b.get("balance", 0))
                            # Use balance as proxy, minimum 1000 to avoid division issues
                            return max(balance, 1000.0)
        except Exception as e:
            logger.error(f"Failed to get equity: {e}")

        return 1000.0  # Default fallback

    async def get_all_traded_symbols(self) -> List[str]:
        """Get all symbols with positions or recent trades"""
        if not self.api_key or not self.api_secret:
            return ["BTCUSDT"]

        symbols = set()
        try:
            # Get current positions
            params = self._sign_request({})
            headers = {"X-MBX-APIKEY": self.api_key}

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/fapi/v2/positionRisk",
                    params=params,
                    headers=headers,
                    timeout=10.0
                )

                if response.status_code == 200:
                    positions = response.json()
                    for pos in positions:
                        if float(pos.get("positionAmt", 0)) != 0:
                            symbols.add(pos.get("symbol"))
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")

        # Always include BTCUSDT as fallback
        if not symbols:
            symbols.add("BTCUSDT")

        return list(symbols)

    async def get_trade_history(self, symbol: Optional[str] = None, limit: int = 100) -> list:
        """Get trade history from Binance Futures (all symbols if none specified)"""
        if not self.api_key or not self.api_secret:
            logger.warning("API credentials missing, cannot fetch trade history")
            return []

        all_trades = []

        # If no symbol specified, get trades for common symbols
        symbols_to_query = [symbol] if symbol else ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]

        try:
            headers = {"X-MBX-APIKEY": self.api_key}

            async with httpx.AsyncClient() as client:
                for sym in symbols_to_query:
                    params = self._sign_request({"symbol": sym, "limit": limit})
                    response = await client.get(
                        f"{self.base_url}/fapi/v1/userTrades",
                        params=params,
                        headers=headers,
                        timeout=10.0
                    )

                    if response.status_code == 200:
                        trades = response.json()
                        logger.info(f"Fetched {len(trades)} trades for {sym}")
                        all_trades.extend(trades)
                    else:
                        logger.warning(f"Failed to get trades for {sym}: {response.status_code}")

            # Sort by time descending
            all_trades.sort(key=lambda x: x.get("time", 0), reverse=True)
            return all_trades[:limit]

        except Exception as e:
            logger.error(f"Error fetching trade history: {e}")
            return []

    async def get_income_history(self, income_type: Optional[str] = None, limit: int = 1000, days: int = 30) -> list:
        """Get income history (PnL, funding fees, etc.) - NO symbol filter to get ALL trades"""
        if not self.api_key or not self.api_secret:
            logger.warning("API credentials missing, cannot fetch income history")
            return []

        try:
            # Calculate start time (30 days ago by default)
            start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

            params = {
                "limit": limit,
                "startTime": start_time
            }
            if income_type:
                params["incomeType"] = income_type

            params = self._sign_request(params)
            headers = {"X-MBX-APIKEY": self.api_key}

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/fapi/v1/income",
                    params=params,
                    headers=headers,
                    timeout=15.0
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Fetched {len(data)} income records (type={income_type}, days={days})")
                    return data
                else:
                    logger.error(f"Income history failed: {response.status_code} - {response.text[:200]}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching income history: {e}")
            return []

    async def get_performance_stats(self) -> dict:
        """Calculate comprehensive performance statistics"""
        trades = await self.get_trade_history(limit=500)

        # Fetch ALL income types first to see what's available
        all_income = await self.get_income_history(income_type=None, limit=1000, days=90)
        logger.info(f"Total income records: {len(all_income)}")

        # Filter to only REALIZED_PNL for calculations
        income = [i for i in all_income if i.get("incomeType") == "REALIZED_PNL"]
        logger.info(f"REALIZED_PNL records: {len(income)}")

        # Log income types breakdown
        income_types = {}
        for i in all_income:
            t = i.get("incomeType", "UNKNOWN")
            income_types[t] = income_types.get(t, 0) + 1
        logger.info(f"Income types breakdown: {income_types}")

        # Calculate basic stats
        total_trades = len(trades)

        if not income:
            logger.warning("No REALIZED_PNL records found!")
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
                # v3.0.1: Core risk-adjusted metrics
                "sharpe_ratio": 0,
                "sortino_ratio": 0,
                "calmar_ratio": 0,
                # v3.0.1: Tail risk metrics
                "var_95": 0,
                "cvar_99": 0,
                "best_trade": 0,
                "worst_trade": 0,
                "avg_trade_duration": "0h",
                "today_pnl": 0,
                "week_pnl": 0,
                "month_pnl": 0,
                "equity_curve": [],
                "initial_equity": 0,
                "_debug": {
                    "api_key_loaded": bool(self.api_key),
                    "total_income_records": len(all_income),
                    "income_types": income_types,
                    "empyrical_available": EMPYRICAL_AVAILABLE,
                    "annualization": 365
                }
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

        # =================================================================
        # v3.0.1: Use empyrical official library for all metrics
        # DO NOT self-implement - official libraries are more accurate!
        # See: docs/research/EVALUATION_FRAMEWORK.md
        # =================================================================

        # Convert PnL to returns series for empyrical
        # Note: empyrical expects returns (percentage), not absolute PnL
        # We need an initial equity estimate to convert PnL to returns
        initial_equity = await self._get_initial_equity()

        # Create returns series from PnL
        returns = pd.Series(pnl_values) / initial_equity

        # Calculate metrics using empyrical (official library)
        if EMPYRICAL_AVAILABLE and len(returns) > 1:
            # Annualization factor: 365 for crypto (24/7 trading)
            # NOT 252 which is for stocks!
            annualization = 365

            try:
                # Core risk-adjusted metrics
                sharpe_ratio = ep.sharpe_ratio(returns, annualization=annualization)
                sortino_ratio = ep.sortino_ratio(returns, annualization=annualization)
                calmar_ratio = ep.calmar_ratio(returns, annualization=annualization)

                # Maximum drawdown (based on equity curve, not PnL)
                max_dd_pct = ep.max_drawdown(returns)  # Returns negative value
                max_dd = abs(max_dd_pct) * initial_equity  # Convert to absolute

                # Tail risk metrics (Basel III/IV standards)
                var_95 = ep.value_at_risk(returns, cutoff=0.05)  # 95% VaR
                # CVaR (Expected Shortfall) - empyrical doesn't have it, calculate manually
                sorted_returns = np.sort(returns)
                cutoff_idx = int(len(sorted_returns) * 0.01)  # 99% CVaR
                cvar_99 = sorted_returns[:max(cutoff_idx, 1)].mean() if cutoff_idx > 0 else sorted_returns[0]

                # Handle NaN values
                sharpe_ratio = 0 if pd.isna(sharpe_ratio) else sharpe_ratio
                sortino_ratio = 0 if pd.isna(sortino_ratio) else sortino_ratio
                calmar_ratio = 0 if pd.isna(calmar_ratio) else calmar_ratio
                var_95 = 0 if pd.isna(var_95) else var_95
                cvar_99 = 0 if pd.isna(cvar_99) else cvar_99

                logger.info(f"Metrics calculated using empyrical (annualization={annualization})")
            except Exception as e:
                logger.error(f"empyrical calculation error: {e}")
                sharpe_ratio = sortino_ratio = calmar_ratio = 0
                max_dd = sum(pnl_values) * 0.1  # Fallback estimate
                var_95 = cvar_99 = 0
        else:
            # Fallback if empyrical not available (legacy calculation)
            logger.warning("empyrical not available, using legacy calculation")
            import statistics
            if len(pnl_values) > 1:
                avg_return = statistics.mean(pnl_values)
                std_return = statistics.stdev(pnl_values)
                # Legacy: 365 for crypto, NOT 252!
                sharpe_ratio = (avg_return / std_return) * (365 ** 0.5) if std_return > 0 else 0
            else:
                sharpe_ratio = 0
            sortino_ratio = 0  # Not available in legacy mode
            calmar_ratio = 0   # Not available in legacy mode
            var_95 = 0         # Not available in legacy mode
            cvar_99 = 0        # Not available in legacy mode

            # Legacy max drawdown calculation
            running_total = 0
            peak = 0
            max_dd = 0
            for pnl in pnl_values:
                running_total += pnl
                if running_total > peak:
                    peak = running_total
                dd = peak - running_total
                if dd > max_dd:
                    max_dd = dd

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

        # Calculate percentages using initial equity
        total_pnl_percent = (total_pnl / initial_equity * 100) if initial_equity > 0 else 0
        max_drawdown_percent = (max_dd / initial_equity * 100) if initial_equity > 0 else 0

        return {
            "total_trades": len(pnl_values),
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_percent": round(total_pnl_percent, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown": round(max_dd, 2),
            "max_drawdown_percent": round(max_drawdown_percent, 2),
            # v3.0.1: Core risk-adjusted metrics (empyrical)
            "sharpe_ratio": round(sharpe_ratio, 2),
            "sortino_ratio": round(sortino_ratio, 2),
            "calmar_ratio": round(calmar_ratio, 2),
            # v3.0.1: Tail risk metrics (Basel III/IV)
            "var_95": round(var_95 * 100, 2),    # As percentage
            "cvar_99": round(cvar_99 * 100, 2),  # As percentage
            "best_trade": round(best_trade, 2),
            "worst_trade": round(worst_trade, 2),
            "avg_trade_duration": "N/A",
            "today_pnl": round(today_pnl, 2),
            "week_pnl": round(week_pnl, 2),
            "month_pnl": round(month_pnl, 2),
            "equity_curve": equity_curve,
            "initial_equity": round(initial_equity, 2),
            "_debug": {
                "api_key_loaded": bool(self.api_key),
                "total_income_records": len(all_income),
                "realized_pnl_count": len(income),
                "income_types": income_types,
                "empyrical_available": EMPYRICAL_AVAILABLE,
                "annualization": 365  # Crypto 24/7 trading
            }
        }

    async def get_recent_trades_formatted(self, limit: int = 20) -> list:
        """Get recent trades formatted for timeline display"""
        income = await self.get_income_history(income_type="REALIZED_PNL", limit=limit, days=90)

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
