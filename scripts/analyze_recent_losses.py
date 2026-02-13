#!/usr/bin/env python3
"""
亏损交易深度分析工具 v1.0

分析最近的亏损交易，读取 Binance 交易记录 + 决策快照，
判断亏损原因是设计问题还是市场原因。

数据源:
  1. Binance userTrades API - 成交记录 (价格、数量、方向、时间)
  2. Binance income API - 盈亏记录 (REALIZED_PNL, FUNDING_FEE)
  3. Binance klines API - K线数据 (还原市场走势)
  4. logs/decisions/*.json - AI 决策快照 (如果有)

分析维度:
  A. 交易还原 - 完整的开/加/平仓时间线
  B. AI 决策质量 - 信号、信心、R/R 比率
  C. 市场环境 - 趋势、波动率、RSI 状态
  D. 执行质量 - 滑点、SL/TP 偏移、实际 R/R vs 计划 R/R
  E. 设计问题检测 - 已知 bug 模式匹配

用法:
  python3 scripts/analyze_recent_losses.py              # 分析最近 3 笔亏损
  python3 scripts/analyze_recent_losses.py --trades 5   # 分析最近 5 笔
  python3 scripts/analyze_recent_losses.py --all        # 分析所有交易 (含盈利)
  python3 scripts/analyze_recent_losses.py --json       # JSON 输出
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(project_root))


# ===== Binance API Client (lightweight, no external deps) =====

class BinanceAnalyzer:
    """Lightweight Binance API client for trade analysis."""

    BASE_URL = "https://fapi.binance.com"

    def __init__(self):
        self.api_key = ""
        self.api_secret = ""
        self._time_offset_ms = 0
        self._load_credentials()
        self._sync_server_time()

    def _load_credentials(self):
        """Load API credentials from ~/.env.aitrader or .env file."""
        env_files = [
            os.path.expanduser("~/.env.aitrader"),
            os.path.join(project_root, ".env"),
        ]
        for env_file in env_files:
            if os.path.exists(env_file):
                try:
                    with open(env_file) as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            if "=" in line:
                                key, value = line.split("=", 1)
                                key = key.strip()
                                value = value.strip().strip('"').strip("'")
                                if key == "BINANCE_API_KEY":
                                    self.api_key = value
                                elif key == "BINANCE_API_SECRET":
                                    self.api_secret = value
                except Exception:
                    pass

        if not self.api_key or not self.api_secret:
            print("ERROR: Binance API credentials not found.")
            print("  Check ~/.env.aitrader or .env file")
            sys.exit(1)

    def _sync_server_time(self):
        """Sync with Binance server time."""
        try:
            url = f"{self.BASE_URL}/fapi/v1/time"
            req = urllib.request.Request(url, headers={"User-Agent": "AItrader/1.0"})
            t_before = int(time.time() * 1000)
            resp = urllib.request.urlopen(req, timeout=10)
            t_after = int(time.time() * 1000)
            data = json.loads(resp.read())
            server_time = data.get("serverTime", 0)
            local_time = (t_before + t_after) // 2
            self._time_offset_ms = server_time - local_time
        except Exception as e:
            print(f"WARNING: Failed to sync Binance time: {e}")

    def _make_signed_request(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        """Make authenticated request to Binance."""
        if params is None:
            params = {}

        params["timestamp"] = int(time.time() * 1000) + self._time_offset_ms
        params["recvWindow"] = 5000

        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(
            self.api_secret.encode(), query_string.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature

        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        url = f"{self.BASE_URL}{endpoint}?{query_string}"

        req = urllib.request.Request(url, headers={
            "X-MBX-APIKEY": self.api_key,
            "User-Agent": "AItrader/1.0",
        })
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())

    def _make_public_request(self, endpoint: str, params: Dict) -> Any:
        """Make public (unsigned) request to Binance."""
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        url = f"{self.BASE_URL}{endpoint}?{query_string}"
        req = urllib.request.Request(url, headers={"User-Agent": "AItrader/1.0"})
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())

    def get_trades(self, symbol: str = "BTCUSDT", limit: int = 100) -> List[Dict]:
        """Get recent trades."""
        return self._make_signed_request("/fapi/v1/userTrades", {
            "symbol": symbol, "limit": limit,
        })

    def get_income(self, income_type: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get income history (PnL, funding, commission)."""
        params = {"limit": limit}
        if income_type:
            params["incomeType"] = income_type
        return self._make_signed_request("/fapi/v1/income", params)

    def get_klines(self, symbol: str = "BTCUSDT", interval: str = "15m",
                   start_time: Optional[int] = None, limit: int = 100) -> List:
        """Get kline/candlestick data."""
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time:
            params["startTime"] = start_time
        return self._make_public_request("/fapi/v1/klines", params)

    def get_open_orders(self, symbol: str = "BTCUSDT") -> List[Dict]:
        """Get open orders."""
        return self._make_signed_request("/fapi/v1/openOrders", {"symbol": symbol})


# ===== Position Reconstruction =====

def reconstruct_positions(trades: List[Dict]) -> List[Dict]:
    """
    Reconstruct complete positions from individual trade fills.

    Groups consecutive trades into positions (open → add → close).
    A position ends when net quantity returns to 0.
    """
    if not trades:
        return []

    # Sort by time
    trades = sorted(trades, key=lambda t: int(t.get("time", 0)))

    positions = []
    current_pos = None

    for trade in trades:
        side = trade.get("side", "")  # BUY or SELL
        qty = float(trade.get("qty", 0))
        price = float(trade.get("price", 0))
        pnl = float(trade.get("realizedPnl", 0))
        commission = float(trade.get("commission", 0))
        trade_time = int(trade.get("time", 0))
        maker = trade.get("maker", False)

        # Determine if this is an open or close trade
        if current_pos is None:
            # New position
            current_pos = {
                "direction": "LONG" if side == "BUY" else "SHORT",
                "open_time": trade_time,
                "close_time": None,
                "entries": [],
                "exits": [],
                "total_entry_qty": 0.0,
                "total_exit_qty": 0.0,
                "avg_entry_price": 0.0,
                "avg_exit_price": 0.0,
                "realized_pnl": 0.0,
                "total_commission": 0.0,
                "net_pnl": 0.0,
                "trades": [],
            }

        current_pos["trades"].append(trade)
        current_pos["total_commission"] += commission

        is_entry = (
            (current_pos["direction"] == "LONG" and side == "BUY") or
            (current_pos["direction"] == "SHORT" and side == "SELL")
        )

        if is_entry:
            current_pos["entries"].append({
                "time": trade_time, "price": price, "qty": qty,
                "commission": commission, "maker": maker,
            })
            current_pos["total_entry_qty"] += qty
            # Recalculate weighted average entry
            total_cost = sum(e["price"] * e["qty"] for e in current_pos["entries"])
            current_pos["avg_entry_price"] = total_cost / current_pos["total_entry_qty"]
        else:
            current_pos["exits"].append({
                "time": trade_time, "price": price, "qty": qty,
                "pnl": pnl, "commission": commission, "maker": maker,
            })
            current_pos["total_exit_qty"] += qty
            current_pos["realized_pnl"] += pnl

            # Check if position is closed
            remaining = current_pos["total_entry_qty"] - current_pos["total_exit_qty"]
            if remaining < 0.0001:  # Effectively zero
                current_pos["close_time"] = trade_time
                if current_pos["exits"]:
                    total_exit = sum(e["price"] * e["qty"] for e in current_pos["exits"])
                    current_pos["avg_exit_price"] = total_exit / current_pos["total_exit_qty"]
                current_pos["net_pnl"] = current_pos["realized_pnl"] - current_pos["total_commission"]

                positions.append(current_pos)
                current_pos = None

    # Handle still-open position
    if current_pos is not None:
        current_pos["status"] = "OPEN"
        positions.append(current_pos)
    else:
        for p in positions:
            p["status"] = "CLOSED"

    return positions


# ===== Decision Snapshot Matcher =====

def find_decision_snapshots(position: Dict) -> List[Dict]:
    """Find AI decision snapshots matching a position's time range."""
    decisions_dir = project_root / "logs" / "decisions"
    if not decisions_dir.exists():
        return []

    open_time = position.get("open_time", 0)
    close_time = position.get("close_time", 0)

    if not open_time:
        return []

    # Look for decision files 30 minutes before open to close time
    search_start = open_time - 30 * 60 * 1000  # 30 min before
    search_end = close_time + 15 * 60 * 1000 if close_time else open_time + 120 * 60 * 1000

    matched = []
    for f in sorted(decisions_dir.glob("decision_*.json")):
        try:
            # Parse timestamp from filename: decision_20260207_201500.json
            parts = f.stem.replace("decision_", "")
            dt = datetime.strptime(parts, "%Y%m%d_%H%M%S")
            file_ts = int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)

            if search_start <= file_ts <= search_end:
                with open(f) as fh:
                    data = json.load(fh)
                    data["_file"] = str(f.name)
                    data["_timestamp_ms"] = file_ts
                    matched.append(data)
        except Exception:
            continue

    return matched


# ===== Market Context Analysis =====

def analyze_market_context(client: BinanceAnalyzer, position: Dict) -> Dict:
    """Fetch and analyze market conditions around a trade."""
    open_time = position.get("open_time", 0)
    if not open_time:
        return {}

    # Fetch klines: 2 hours before open time
    start_time = open_time - 2 * 60 * 60 * 1000
    try:
        klines = client.get_klines(
            symbol="BTCUSDT", interval="15m",
            start_time=start_time, limit=30,
        )
    except Exception as e:
        return {"error": str(e)}

    if not klines:
        return {"error": "No kline data"}

    # Calculate indicators from klines
    closes = [float(k[4]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    volumes = [float(k[5]) for k in klines]

    # Simple RSI (14-period)
    rsi = _calculate_rsi(closes, 14)

    # Volatility (std of returns)
    if len(closes) > 1:
        returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
        volatility = (sum(r**2 for r in returns) / len(returns)) ** 0.5 * 100
    else:
        volatility = 0

    # Trend (SMA20 vs price)
    sma20 = sum(closes[-20:]) / min(len(closes), 20) if closes else 0
    current_price = closes[-1] if closes else 0
    trend = "BULLISH" if current_price > sma20 else "BEARISH"

    # Price range
    period_high = max(highs[-8:]) if highs else 0  # Last 2 hours
    period_low = min(lows[-8:]) if lows else 0
    range_pct = (period_high - period_low) / period_low * 100 if period_low else 0

    # Volume analysis
    avg_volume = sum(volumes) / len(volumes) if volumes else 0
    recent_volume = volumes[-1] if volumes else 0
    volume_ratio = recent_volume / avg_volume if avg_volume else 0

    return {
        "rsi_at_entry": rsi,
        "volatility_pct": round(volatility, 4),
        "trend": trend,
        "sma20": round(sma20, 2),
        "current_price": current_price,
        "period_high": period_high,
        "period_low": period_low,
        "range_pct": round(range_pct, 2),
        "volume_ratio": round(volume_ratio, 2),
        "kline_count": len(klines),
    }


def _calculate_rsi(closes: List[float], period: int = 14) -> float:
    """Calculate RSI from close prices."""
    if len(closes) < period + 1:
        return 50.0  # Default neutral

    gains = []
    losses = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        gains.append(max(0, change))
        losses.append(max(0, -change))

    if len(gains) < period:
        return 50.0

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


# ===== Loss Diagnosis Engine =====

KNOWN_DESIGN_ISSUES = [
    {
        "id": "D1",
        "name": "R/R degradation on MARKET fill",
        "description": "SL/TP calculated at bar close price, MARKET fill at different price degrades R/R",
        "check": lambda pos, ctx: _check_rr_degradation(pos),
        "severity": "HIGH",
        "status": "FIXED in v4.9 (post-fill R/R validation)",
    },
    {
        "id": "D2",
        "name": "OCO broken after _update_sltp_quantity",
        "description": "When adding to position, modify_order fails → cancel+recreate breaks OCO linkage",
        "check": lambda pos, ctx: len(pos.get("entries", [])) > 1,
        "severity": "HIGH",
        "status": "KNOWN - OCO orphan risk after scaling",
    },
    {
        "id": "D3",
        "name": "Trailing stop moved SL (not SL hit)",
        "description": "Trailing stop activated and moved SL above original, then position closed by AI or trailing SL",
        "check": lambda pos, ctx: _check_trailing_stop_close(pos),
        "severity": "INFO",
        "status": "BY DESIGN - trailing stop working as intended",
    },
    {
        "id": "D4",
        "name": "Cumulative sizing near max capacity",
        "description": "Cumulative mode added to position until near max_usdt limit",
        "check": lambda pos, ctx: _check_over_sizing(pos),
        "severity": "MEDIUM",
        "status": "BY DESIGN - but increases risk when AI adds at worse price",
    },
    {
        "id": "D5",
        "name": "RSI overbought/oversold entry",
        "description": "Entered when RSI > 65 (LONG) or RSI < 35 (SHORT)",
        "check": lambda pos, ctx: _check_rsi_extreme_entry(pos, ctx),
        "severity": "MEDIUM",
        "status": "MARKET CAUSE - AI should have detected this",
    },
    {
        "id": "D6",
        "name": "AI closed before SL hit",
        "description": "Position closed at market price (not SL) by subsequent AI CLOSE/SHORT signal",
        "check": lambda pos, ctx: _check_ai_close_before_sl(pos),
        "severity": "INFO",
        "status": "BY DESIGN - AI override of SL is expected behavior",
    },
    {
        "id": "D7",
        "name": "High volatility whipsaw",
        "description": "Market volatility >0.5% per bar caused whipsaw",
        "check": lambda pos, ctx: ctx.get("volatility_pct", 0) > 0.5,
        "severity": "INFO",
        "status": "MARKET CAUSE - volatile environment",
    },
]


def _check_rr_degradation(pos: Dict) -> bool:
    """Check if entry price was significantly different from expected."""
    entries = pos.get("entries", [])
    if not entries:
        return False
    # If first entry and exits show tight loss, R/R likely degraded
    avg_entry = pos.get("avg_entry_price", 0)
    avg_exit = pos.get("avg_exit_price", 0)
    if not avg_entry or not avg_exit:
        return False
    loss_pct = abs(avg_exit - avg_entry) / avg_entry * 100
    return loss_pct < 1.0  # Lost less than 1% = SL probably wasn't hit


def _check_trailing_stop_close(pos: Dict) -> bool:
    """Check if close price suggests trailing stop activation."""
    direction = pos.get("direction", "")
    avg_entry = pos.get("avg_entry_price", 0)
    avg_exit = pos.get("avg_exit_price", 0)
    if not avg_entry or not avg_exit:
        return False

    if direction == "LONG":
        loss_pct = (avg_exit - avg_entry) / avg_entry
        # Trailing stop close: loss is small (< 1%) and exit is near entry
        return -0.015 < loss_pct < 0.005
    elif direction == "SHORT":
        loss_pct = (avg_entry - avg_exit) / avg_entry
        return -0.015 < loss_pct < 0.005
    return False


def _check_over_sizing(pos: Dict) -> bool:
    """Check if position was added to (multiple entries)."""
    return len(pos.get("entries", [])) > 1


def _check_rsi_extreme_entry(pos: Dict, ctx: Dict) -> bool:
    """Check if RSI was extreme at entry time."""
    rsi = ctx.get("rsi_at_entry", 50)
    direction = pos.get("direction", "")
    if direction == "LONG" and rsi > 65:
        return True
    if direction == "SHORT" and rsi < 35:
        return True
    return False


def _check_ai_close_before_sl(pos: Dict) -> bool:
    """Check if position was likely closed by AI (not SL)."""
    # If exit price is significantly above SL level (for LONG), it was not SL
    # We can only infer this from the loss percentage
    direction = pos.get("direction", "")
    avg_entry = pos.get("avg_entry_price", 0)
    avg_exit = pos.get("avg_exit_price", 0)
    if not avg_entry or not avg_exit:
        return False

    if direction == "LONG":
        loss_pct = (avg_exit - avg_entry) / avg_entry
        # Typical SL is ~2.5% below entry. If loss < 1.5%, probably not SL
        return -0.015 < loss_pct < 0
    elif direction == "SHORT":
        loss_pct = (avg_entry - avg_exit) / avg_entry
        return -0.015 < loss_pct < 0
    return False


def diagnose_position(pos: Dict, market_ctx: Dict, decisions: List[Dict]) -> Dict:
    """Run full diagnosis on a single position."""
    diagnosis = {
        "triggered_issues": [],
        "root_cause": "UNKNOWN",
        "category": "UNKNOWN",  # DESIGN / MARKET / AI_DECISION / EXECUTION
        "details": "",
        "recommendations": [],
    }

    # Run all checks
    for issue in KNOWN_DESIGN_ISSUES:
        try:
            if issue["check"](pos, market_ctx):
                diagnosis["triggered_issues"].append({
                    "id": issue["id"],
                    "name": issue["name"],
                    "description": issue["description"],
                    "severity": issue["severity"],
                    "status": issue["status"],
                })
        except Exception:
            pass

    # Determine root cause category
    triggered_ids = [i["id"] for i in diagnosis["triggered_issues"]]

    if "D1" in triggered_ids:
        diagnosis["category"] = "DESIGN"
        diagnosis["root_cause"] = "R/R degradation due to stale entry price estimation"
        diagnosis["details"] = (
            "SL/TP was calculated using bar close price, but MARKET order filled at a "
            "significantly different price, degrading the actual R/R below the 1.5:1 minimum."
        )
        diagnosis["recommendations"].append("Upgrade to v4.9+ (post-fill R/R validation + real-time price)")

    if "D2" in triggered_ids:
        if diagnosis["category"] == "UNKNOWN":
            diagnosis["category"] = "DESIGN"
        diagnosis["root_cause"] = "Position scaling broke OCO linkage"
        diagnosis["details"] += (
            "\nPosition was scaled (multiple entries). After adding, SL/TP orders may have "
            "lost their OCO linkage, meaning if one triggered, the other wouldn't auto-cancel."
        )
        diagnosis["recommendations"].append("Monitor logs for 'modify_order failed' warnings during scaling")

    if "D5" in triggered_ids:
        if diagnosis["category"] == "UNKNOWN":
            diagnosis["category"] = "AI_DECISION"
        rsi = market_ctx.get("rsi_at_entry", 50)
        diagnosis["root_cause"] = f"AI entered at extreme RSI ({rsi})"
        diagnosis["details"] += f"\nRSI was {rsi} at entry, suggesting {pos['direction']} was counter-momentum."
        diagnosis["recommendations"].append("Review AI Risk Manager prompt for RSI filtering")

    if "D6" in triggered_ids and "D3" in triggered_ids:
        if diagnosis["category"] == "UNKNOWN":
            diagnosis["category"] = "AI_DECISION"
        diagnosis["root_cause"] = "AI closed position before SL triggered (possibly trailing stop)"
        diagnosis["details"] += (
            "\nPosition was closed at a price much higher than the original SL. "
            "This could be: (a) AI sent CLOSE/SHORT signal at next cycle, or "
            "(b) Trailing stop activated and moved SL up."
        )

    if "D7" in triggered_ids:
        if diagnosis["category"] == "UNKNOWN":
            diagnosis["category"] = "MARKET"
        vol = market_ctx.get("volatility_pct", 0)
        diagnosis["root_cause"] = f"High volatility whipsaw ({vol:.2f}% per bar)"
        diagnosis["details"] += f"\nMarket was highly volatile. This increases risk of stop-outs."
        diagnosis["recommendations"].append("Consider wider SL in volatile conditions")

    if diagnosis["category"] == "UNKNOWN":
        # Default: analyze based on loss size
        avg_entry = pos.get("avg_entry_price", 0)
        avg_exit = pos.get("avg_exit_price", 0)
        if avg_entry and avg_exit:
            if pos["direction"] == "LONG":
                loss_pct = (avg_exit - avg_entry) / avg_entry * 100
            else:
                loss_pct = (avg_entry - avg_exit) / avg_entry * 100

            if loss_pct < -2.0:
                diagnosis["category"] = "MARKET"
                diagnosis["root_cause"] = f"Full SL hit ({loss_pct:.2f}%)"
                diagnosis["details"] = "Price moved against position and hit stop loss. This is normal risk."
            else:
                diagnosis["category"] = "AI_DECISION"
                diagnosis["root_cause"] = f"Small loss ({loss_pct:.2f}%), likely AI signal change"
                diagnosis["details"] = "Position closed with a small loss, suggesting AI changed its signal."

    # Add decision snapshot analysis
    if decisions:
        for d in decisions:
            ai_out = d.get("ai_outputs", {})
            signal = ai_out.get("signal", "?")
            confidence = ai_out.get("confidence", "?")
            reason = ai_out.get("reason", "")
            sl = ai_out.get("stop_loss")
            tp = ai_out.get("take_profit")
            file_name = d.get("_file", "?")

            diagnosis.setdefault("decision_snapshots", []).append({
                "file": file_name,
                "signal": signal,
                "confidence": confidence,
                "stop_loss": sl,
                "take_profit": tp,
                "reason": reason[:200] if reason else "",
            })

    return diagnosis


# ===== Display Functions =====

def format_timestamp(ms: int) -> str:
    """Format millisecond timestamp to readable string (UTC+8)."""
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone(timedelta(hours=8)))
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def print_position_report(pos: Dict, idx: int, market_ctx: Dict, diagnosis: Dict):
    """Print detailed report for a single position."""
    direction = pos.get("direction", "?")
    status = pos.get("status", "?")
    net_pnl = pos.get("net_pnl", 0)
    realized_pnl = pos.get("realized_pnl", 0)
    commission = pos.get("total_commission", 0)

    # Header
    pnl_emoji = "+" if net_pnl >= 0 else ""
    result = "WIN" if net_pnl >= 0 else "LOSS"
    print(f"\n{'='*72}")
    print(f"  Trade #{idx}  |  {direction}  |  {result}  |  {pnl_emoji}${net_pnl:.2f} USDT")
    print(f"{'='*72}")

    # Timeline
    print(f"\n  --- Timeline ---")
    entries = pos.get("entries", [])
    exits = pos.get("exits", [])

    for i, entry in enumerate(entries):
        label = "OPEN" if i == 0 else f"ADD #{i}"
        print(f"  [{format_timestamp(entry['time'])}] {label}: "
              f"{entry['qty']:.4f} BTC @ ${entry['price']:,.2f}")

    for i, exit_ in enumerate(exits):
        label = "CLOSE" if i == len(exits) - 1 else f"PARTIAL #{i}"
        pnl_str = f"PnL: ${exit_['pnl']:+.2f}" if exit_.get('pnl') else ""
        print(f"  [{format_timestamp(exit_['time'])}] {label}: "
              f"{exit_['qty']:.4f} BTC @ ${exit_['price']:,.2f}  {pnl_str}")

    # Duration
    open_time = pos.get("open_time", 0)
    close_time = pos.get("close_time", 0)
    if open_time and close_time:
        duration_min = (close_time - open_time) / 60000
        if duration_min >= 60:
            print(f"  Duration: {duration_min/60:.1f} hours")
        else:
            print(f"  Duration: {duration_min:.0f} minutes")

    # Price Analysis
    print(f"\n  --- Price Analysis ---")
    avg_entry = pos.get("avg_entry_price", 0)
    avg_exit = pos.get("avg_exit_price", 0)
    if avg_entry and avg_exit:
        if direction == "LONG":
            pnl_pct = (avg_exit - avg_entry) / avg_entry * 100
        else:
            pnl_pct = (avg_entry - avg_exit) / avg_entry * 100
        print(f"  Avg Entry:  ${avg_entry:,.2f}")
        print(f"  Avg Exit:   ${avg_exit:,.2f}")
        print(f"  P&L:        {pnl_pct:+.2f}%  (${realized_pnl:+.2f} - ${commission:.2f} fee = ${net_pnl:+.2f})")

    # Total position size
    total_qty = pos.get("total_entry_qty", 0)
    notional = total_qty * avg_entry if avg_entry else 0
    print(f"  Total Size: {total_qty:.4f} BTC (${notional:,.0f} notional)")

    # Market Context
    if market_ctx and not market_ctx.get("error"):
        print(f"\n  --- Market Context (at entry) ---")
        print(f"  RSI (14):     {market_ctx.get('rsi_at_entry', '?')}")
        print(f"  Trend:        {market_ctx.get('trend', '?')} (SMA20: ${market_ctx.get('sma20', 0):,.2f})")
        print(f"  Volatility:   {market_ctx.get('volatility_pct', 0):.3f}% per bar")
        print(f"  2H Range:     ${market_ctx.get('period_low', 0):,.2f} - ${market_ctx.get('period_high', 0):,.2f} "
              f"({market_ctx.get('range_pct', 0):.2f}%)")
        print(f"  Volume Ratio: {market_ctx.get('volume_ratio', 0):.2f}x avg")

    # Decision Snapshots
    snapshots = diagnosis.get("decision_snapshots", [])
    if snapshots:
        print(f"\n  --- AI Decision Snapshots ({len(snapshots)} found) ---")
        for snap in snapshots:
            print(f"  [{snap['file']}]")
            print(f"    Signal: {snap['signal']} ({snap['confidence']})")
            if snap.get("stop_loss") and snap.get("take_profit"):
                print(f"    SL: ${snap['stop_loss']:,.2f}  TP: ${snap['take_profit']:,.2f}")
            if snap.get("reason"):
                print(f"    Reason: {snap['reason'][:120]}...")

    # Diagnosis
    print(f"\n  --- Diagnosis ---")
    category_emoji = {
        "DESIGN": "BUG",
        "MARKET": "MARKET",
        "AI_DECISION": "AI",
        "EXECUTION": "EXEC",
        "UNKNOWN": "???",
    }
    cat = diagnosis.get("category", "UNKNOWN")
    print(f"  Category:   [{category_emoji.get(cat, '???')}] {cat}")
    print(f"  Root Cause: {diagnosis.get('root_cause', 'Unknown')}")

    if diagnosis.get("details"):
        for line in diagnosis["details"].strip().split("\n"):
            print(f"  {line}")

    # Triggered issues
    issues = diagnosis.get("triggered_issues", [])
    if issues:
        print(f"\n  Triggered Pattern Matches:")
        for issue in issues:
            severity_mark = {"HIGH": "!!", "MEDIUM": "! ", "INFO": "  "}.get(issue["severity"], "  ")
            print(f"    [{severity_mark}] {issue['id']}: {issue['name']}")
            print(f"         Status: {issue['status']}")

    # Recommendations
    recs = diagnosis.get("recommendations", [])
    if recs:
        print(f"\n  Recommendations:")
        for rec in recs:
            print(f"    -> {rec}")


def print_summary(positions: List[Dict], diagnoses: List[Dict]):
    """Print aggregate summary."""
    losses = [p for p in positions if p.get("net_pnl", 0) < 0]
    wins = [p for p in positions if p.get("net_pnl", 0) >= 0]

    total_loss = sum(p.get("net_pnl", 0) for p in losses)
    total_win = sum(p.get("net_pnl", 0) for p in wins)
    total_pnl = total_loss + total_win

    print(f"\n{'='*72}")
    print(f"  SUMMARY")
    print(f"{'='*72}")
    print(f"  Total Positions:  {len(positions)} ({len(wins)} wins, {len(losses)} losses)")
    print(f"  Win Rate:         {len(wins)/len(positions)*100:.0f}%" if positions else "  Win Rate:  N/A")
    print(f"  Total P&L:        ${total_pnl:+.2f} USDT")
    print(f"  Total Wins:       ${total_win:+.2f} USDT")
    print(f"  Total Losses:     ${total_loss:+.2f} USDT")

    # Categorize losses
    if diagnoses:
        categories = {}
        for d in diagnoses:
            cat = d.get("category", "UNKNOWN")
            categories[cat] = categories.get(cat, 0) + 1

        print(f"\n  Loss Categories:")
        category_labels = {
            "DESIGN": "Design/Bug Issues",
            "MARKET": "Market Conditions",
            "AI_DECISION": "AI Decision Quality",
            "EXECUTION": "Execution Issues",
            "UNKNOWN": "Unknown",
        }
        for cat, count in sorted(categories.items()):
            label = category_labels.get(cat, cat)
            pct = count / len(diagnoses) * 100
            bar = "#" * int(pct / 5)
            print(f"    {label:25s}: {count} ({pct:.0f}%) {bar}")

    # Aggregate recommendations
    all_recs = set()
    for d in diagnoses:
        for r in d.get("recommendations", []):
            all_recs.add(r)

    if all_recs:
        print(f"\n  Key Recommendations:")
        for rec in sorted(all_recs):
            print(f"    -> {rec}")

    print(f"\n{'='*72}")


# ===== Funding Fee Analysis =====

def analyze_funding_fees(client: BinanceAnalyzer, positions: List[Dict]) -> Dict:
    """Analyze funding fees impact on positions."""
    try:
        funding = client.get_income(income_type="FUNDING_FEE", limit=50)
    except Exception:
        return {"error": "Failed to fetch funding fees"}

    total_funding = sum(float(f.get("income", 0)) for f in funding)

    # Match funding fees to positions
    for pos in positions:
        pos_funding = 0
        open_time = pos.get("open_time", 0)
        close_time = pos.get("close_time", open_time + 24 * 3600 * 1000)
        for f in funding:
            f_time = int(f.get("time", 0))
            if open_time <= f_time <= close_time:
                pos_funding += float(f.get("income", 0))
        pos["funding_fees"] = pos_funding

    return {
        "total_funding": total_funding,
        "count": len(funding),
    }


# ===== Main =====

def main():
    parser = argparse.ArgumentParser(description="Analyze recent losing trades")
    parser.add_argument("--trades", type=int, default=3,
                        help="Number of losing trades to analyze (default: 3)")
    parser.add_argument("--all", action="store_true",
                        help="Analyze all trades (including wins)")
    parser.add_argument("--json", action="store_true",
                        help="Output in JSON format")
    parser.add_argument("--limit", type=int, default=200,
                        help="Max trade records to fetch from Binance (default: 200)")
    args = parser.parse_args()

    print(f"{'='*72}")
    print(f"  AItrader Loss Analysis Tool v1.0")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*72}")

    # Initialize Binance client
    print("\n[1/5] Connecting to Binance API...")
    client = BinanceAnalyzer()
    print("  OK - Connected")

    # Fetch trades
    print(f"\n[2/5] Fetching recent trades (limit={args.limit})...")
    try:
        raw_trades = client.get_trades(symbol="BTCUSDT", limit=args.limit)
        print(f"  OK - {len(raw_trades)} trade fills fetched")
    except Exception as e:
        print(f"  FAIL - {e}")
        sys.exit(1)

    if not raw_trades:
        print("\n  No trades found. The account may not have recent BTCUSDT trades.")
        sys.exit(0)

    # Reconstruct positions
    print(f"\n[3/5] Reconstructing positions from fills...")
    positions = reconstruct_positions(raw_trades)
    closed = [p for p in positions if p.get("status") == "CLOSED"]
    open_pos = [p for p in positions if p.get("status") == "OPEN"]
    print(f"  OK - {len(closed)} closed positions, {len(open_pos)} open")

    if not closed and not open_pos:
        print("\n  No positions reconstructed. Raw trades may not form complete positions.")
        sys.exit(0)

    # Filter to losses (unless --all)
    if args.all:
        target_positions = closed
        print(f"\n  Analyzing ALL {len(target_positions)} closed positions")
    else:
        losses = [p for p in closed if p.get("net_pnl", 0) < 0]
        target_positions = losses[-args.trades:] if len(losses) > args.trades else losses
        print(f"\n  Found {len(losses)} losing positions, analyzing last {len(target_positions)}")

    if not target_positions:
        print("\n  No matching positions to analyze.")
        if closed:
            wins = [p for p in closed if p.get("net_pnl", 0) >= 0]
            print(f"  ({len(wins)} winning positions found)")
        sys.exit(0)

    # Fetch funding fees
    print(f"\n[4/5] Fetching funding fees...")
    try:
        funding_info = analyze_funding_fees(client, target_positions)
        print(f"  OK - Total funding: ${funding_info.get('total_funding', 0):+.2f}")
    except Exception as e:
        print(f"  WARN - {e}")

    # Analyze each position
    print(f"\n[5/5] Running deep analysis on {len(target_positions)} positions...")
    all_diagnoses = []

    for i, pos in enumerate(target_positions):
        # Get market context
        market_ctx = analyze_market_context(client, pos)

        # Find decision snapshots
        decisions = find_decision_snapshots(pos)

        # Run diagnosis
        diagnosis = diagnose_position(pos, market_ctx, decisions)
        all_diagnoses.append(diagnosis)

        if args.json:
            # Build JSON output
            pos["market_context"] = market_ctx
            pos["diagnosis"] = diagnosis
        else:
            print_position_report(pos, i + 1, market_ctx, diagnosis)

    # Summary
    if args.json:
        output = {
            "analysis_time": datetime.now().isoformat(),
            "total_positions": len(positions),
            "analyzed": len(target_positions),
            "positions": target_positions,
            "funding": funding_info if 'funding_info' in dir() else {},
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print_summary(target_positions, all_diagnoses)

        # Final verdict
        design_count = sum(1 for d in all_diagnoses if d.get("category") == "DESIGN")
        market_count = sum(1 for d in all_diagnoses if d.get("category") == "MARKET")
        ai_count = sum(1 for d in all_diagnoses if d.get("category") == "AI_DECISION")

        print(f"\n  VERDICT:")
        if design_count > 0:
            print(f"    {design_count} loss(es) likely caused by DESIGN issues")
            print(f"    -> Code fixes recommended (see recommendations above)")
        if ai_count > 0:
            print(f"    {ai_count} loss(es) likely caused by AI DECISION quality")
            print(f"    -> Review AI prompts and signal logic")
        if market_count > 0:
            print(f"    {market_count} loss(es) likely caused by MARKET conditions")
            print(f"    -> Normal trading risk, no code changes needed")
        if not design_count and not ai_count and not market_count:
            print(f"    Unable to determine root cause. Check server logs for more details.")

        print()


if __name__ == "__main__":
    main()
