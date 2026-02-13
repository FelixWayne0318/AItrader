"""
Binance API Service - Fetch trading performance data
"""
import hmac
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional
import httpx

from core.config import settings, load_aitrader_env


class BinanceService:
    """Service for fetching trading data from Binance Futures API"""

    BASE_URL = "https://fapi.binance.com"

    def __init__(self):
        load_aitrader_env()
        self.api_key = settings.BINANCE_API_KEY
        self.api_secret = settings.BINANCE_API_SECRET

    def _sign(self, params: dict) -> dict:
        """Sign request with HMAC SHA256"""
        if not self.api_secret:
            raise ValueError("Binance API secret not configured")

        params["timestamp"] = int(time.time() * 1000)
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        signature = hmac.new(
            self.api_secret.encode(),
            query_string.encode(),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _headers(self) -> dict:
        """Get request headers"""
        return {"X-MBX-APIKEY": self.api_key or ""}

    async def get_account_info(self) -> Optional[dict]:
        """Get futures account information"""
        try:
            params = self._sign({})
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.BASE_URL}/fapi/v2/account",
                    params=params,
                    headers=self._headers(),
                    timeout=10.0
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            print(f"Error fetching account info: {e}")
        return None

    async def get_income_history(
        self,
        income_type: str = "REALIZED_PNL",
        days: int = 30,
        limit: int = 1000
    ) -> list:
        """
        Get income history (realized PnL, funding fees, etc.)

        income_type options:
        - REALIZED_PNL: Trading profit/loss
        - FUNDING_FEE: Funding fees
        - COMMISSION: Trading fees
        - TRANSFER: Transfers
        """
        try:
            start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
            params = self._sign({
                "incomeType": income_type,
                "startTime": start_time,
                "limit": limit,
            })

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.BASE_URL}/fapi/v1/income",
                    params=params,
                    headers=self._headers(),
                    timeout=30.0
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            print(f"Error fetching income history: {e}")
        return []

    async def get_trade_history(self, symbol: str = "BTCUSDT", days: int = 30) -> list:
        """Get trade history for a symbol"""
        try:
            start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
            params = self._sign({
                "symbol": symbol,
                "startTime": start_time,
                "limit": 1000,
            })

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.BASE_URL}/fapi/v1/userTrades",
                    params=params,
                    headers=self._headers(),
                    timeout=30.0
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            print(f"Error fetching trade history: {e}")
        return []

    async def get_performance_stats(self, days: int = 30) -> dict:
        """
        Calculate performance statistics from trading history

        Returns aggregated stats without exposing individual trades
        """
        # Get realized PnL
        pnl_history = await self.get_income_history("REALIZED_PNL", days)

        if not pnl_history:
            return self._empty_stats()

        # Process data
        daily_pnl = {}
        total_pnl = 0.0
        winning_trades = 0
        losing_trades = 0

        for record in pnl_history:
            pnl = float(record.get("income", 0))
            timestamp = int(record.get("time", 0))
            date_str = datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")

            # Aggregate daily PnL
            if date_str not in daily_pnl:
                daily_pnl[date_str] = 0.0
            daily_pnl[date_str] += pnl
            total_pnl += pnl

            # Count wins/losses
            if pnl > 0:
                winning_trades += 1
            elif pnl < 0:
                losing_trades += 1

        # Separate wins and losses for avg calculations
        win_amounts = []
        loss_amounts = []

        for record in pnl_history:
            pnl = float(record.get("income", 0))
            if pnl > 0:
                win_amounts.append(pnl)
            elif pnl < 0:
                loss_amounts.append(abs(pnl))

        # Calculate metrics
        total_trades = winning_trades + losing_trades
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        avg_profit = sum(win_amounts) / len(win_amounts) if win_amounts else 0
        avg_loss = sum(loss_amounts) / len(loss_amounts) if loss_amounts else 0
        total_wins = sum(win_amounts)
        total_losses = sum(loss_amounts)
        profit_factor = (total_wins / total_losses) if total_losses > 0 else 0
        risk_reward = (avg_profit / avg_loss) if avg_loss > 0 else 0

        # Calculate cumulative PnL curve
        sorted_dates = sorted(daily_pnl.keys())
        cumulative = 0.0
        pnl_curve = []
        for date in sorted_dates:
            cumulative += daily_pnl[date]
            pnl_curve.append({
                "date": date,
                "daily_pnl": round(daily_pnl[date], 2),
                "cumulative_pnl": round(cumulative, 2)
            })

        # Calculate max drawdown
        peak = 0.0
        max_drawdown = 0.0
        for point in pnl_curve:
            cum = point["cumulative_pnl"]
            if cum > peak:
                peak = cum
            drawdown = peak - cum
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # Calculate Sharpe ratio (annualized, crypto = 365 days)
        daily_returns = [p["daily_pnl"] for p in pnl_curve]
        sharpe_ratio = 0.0
        if len(daily_returns) > 1:
            import statistics
            mean_return = statistics.mean(daily_returns)
            std_return = statistics.stdev(daily_returns)
            if std_return > 0:
                sharpe_ratio = (mean_return / std_return) * (365 ** 0.5)

        # Get account info for balance
        account = await self.get_account_info()
        balance = 0.0
        if account:
            balance = float(account.get("totalWalletBalance", 0))

        return {
            "total_pnl": round(total_pnl, 2),
            "total_pnl_percent": round((total_pnl / balance * 100) if balance > 0 else 0, 2),
            "total_equity": round(balance, 2),
            "win_rate": round(win_rate, 1),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "avg_profit": round(avg_profit, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "risk_reward": round(risk_reward, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_percent": round((max_drawdown / balance * 100) if balance > 0 else 0, 2),
            "pnl_curve": pnl_curve,
            "period_days": days,
            "last_updated": datetime.now().isoformat(),
        }

    def _empty_stats(self) -> dict:
        """Return empty stats structure"""
        return {
            "total_pnl": 0,
            "total_pnl_percent": 0,
            "total_equity": 0,
            "win_rate": 0,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "avg_profit": 0,
            "avg_loss": 0,
            "profit_factor": 0,
            "risk_reward": 0,
            "sharpe_ratio": 0,
            "max_drawdown": 0,
            "max_drawdown_percent": 0,
            "pnl_curve": [],
            "period_days": 0,
            "last_updated": datetime.now().isoformat(),
        }


# Singleton instance
binance_service = BinanceService()
