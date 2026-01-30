"""
Public API Routes - No authentication required
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.database import get_db
from models import SocialLink, CopyTradingLink, SiteSettings
from services import binance_service

router = APIRouter(prefix="/public", tags=["Public"])


@router.get("/performance")
async def get_performance(days: int = 30):
    """
    Get trading performance statistics

    Returns aggregated stats without exposing individual trades
    """
    if days > 365:
        days = 365
    if days < 1:
        days = 1

    stats = await binance_service.get_performance_stats(days)
    return stats


@router.get("/performance/summary")
async def get_performance_summary():
    """Get quick performance summary for homepage"""
    stats = await binance_service.get_performance_stats(30)

    return {
        "total_return_percent": stats["total_pnl_percent"],
        "win_rate": stats["win_rate"],
        "max_drawdown_percent": stats["max_drawdown_percent"],
        "total_trades": stats["total_trades"],
        "last_updated": stats["last_updated"],
    }


@router.get("/social-links")
async def get_social_links(db: AsyncSession = Depends(get_db)):
    """Get all enabled social media links"""
    result = await db.execute(
        select(SocialLink).where(SocialLink.enabled == True)
    )
    links = result.scalars().all()

    return [
        {
            "platform": link.platform,
            "url": link.url,
        }
        for link in links
    ]


@router.get("/copy-trading")
async def get_copy_trading_links(db: AsyncSession = Depends(get_db)):
    """Get all enabled copy trading links"""
    result = await db.execute(
        select(CopyTradingLink)
        .where(CopyTradingLink.enabled == True)
        .order_by(CopyTradingLink.sort_order)
    )
    links = result.scalars().all()

    return [
        {
            "exchange": link.exchange,
            "name": link.name,
            "url": link.url,
            "icon": link.icon,
        }
        for link in links
    ]


@router.get("/site-settings/{key}")
async def get_site_setting(key: str, db: AsyncSession = Depends(get_db)):
    """Get a specific site setting"""
    result = await db.execute(
        select(SiteSettings).where(SiteSettings.key == key)
    )
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")

    return {"key": setting.key, "value": setting.value}


@router.get("/system-status")
async def get_system_status():
    """Get basic system status (running/stopped)"""
    from services import config_service

    status = config_service.get_service_status()

    return {
        "trading_active": status["running"],
        "status": "Running" if status["running"] else "Stopped",
    }


@router.get("/latest-signal")
async def get_latest_signal():
    """Get the latest AI trading signal"""
    import os
    import json
    from datetime import datetime

    # Try to read from the bot's signal state file
    signal_file_paths = [
        "/home/linuxuser/nautilus_AItrader/logs/latest_signal.json",
        "/home/linuxuser/nautilus_AItrader/state/latest_signal.json",
        os.path.expanduser("~/nautilus_AItrader/logs/latest_signal.json"),
    ]

    for signal_file in signal_file_paths:
        if os.path.exists(signal_file):
            try:
                with open(signal_file, 'r') as f:
                    data = json.load(f)
                    return {
                        "signal": data.get("signal", "HOLD"),
                        "confidence": data.get("confidence", "MEDIUM"),
                        "reason": data.get("reason", ""),
                        "symbol": data.get("symbol", "BTCUSDT"),
                        "timestamp": data.get("timestamp", datetime.now().isoformat()),
                    }
            except Exception:
                pass

    # Default response if no signal file found
    return {
        "signal": "HOLD",
        "confidence": "MEDIUM",
        "reason": "Waiting for next analysis cycle",
        "symbol": "BTCUSDT",
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/signal-history")
async def get_signal_history(limit: int = 10):
    """Get recent AI signal history"""
    import os
    import json
    from datetime import datetime

    history_file_paths = [
        "/home/linuxuser/nautilus_AItrader/logs/signal_history.json",
        "/home/linuxuser/nautilus_AItrader/state/signal_history.json",
        os.path.expanduser("~/nautilus_AItrader/logs/signal_history.json"),
    ]

    for history_file in history_file_paths:
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r') as f:
                    data = json.load(f)
                    signals = data if isinstance(data, list) else data.get("signals", [])
                    return {
                        "signals": signals[:limit],
                        "total": len(signals),
                    }
            except Exception:
                pass

    # Demo data if no history file found
    return {
        "signals": [
            {
                "signal": "HOLD",
                "confidence": "MEDIUM",
                "reason": "Market consolidating, waiting for breakout",
                "timestamp": datetime.now().isoformat(),
                "result": None,
            }
        ],
        "total": 1,
    }


@router.get("/ai-analysis")
async def get_ai_analysis():
    """Get detailed AI analysis including Bull/Bear debate"""
    import os
    import json
    from datetime import datetime

    analysis_file_paths = [
        "/home/linuxuser/nautilus_AItrader/logs/latest_analysis.json",
        "/home/linuxuser/nautilus_AItrader/state/latest_analysis.json",
        os.path.expanduser("~/nautilus_AItrader/logs/latest_analysis.json"),
    ]

    for analysis_file in analysis_file_paths:
        if os.path.exists(analysis_file):
            try:
                with open(analysis_file, 'r') as f:
                    data = json.load(f)
                    return {
                        "signal": data.get("signal", "HOLD"),
                        "confidence": data.get("confidence", "MEDIUM"),
                        "confidence_score": data.get("confidence_score", 50),
                        "bull_analysis": data.get("bull_analysis", ""),
                        "bear_analysis": data.get("bear_analysis", ""),
                        "judge_reasoning": data.get("judge_reasoning", ""),
                        "entry_price": data.get("entry_price"),
                        "stop_loss": data.get("stop_loss"),
                        "take_profit": data.get("take_profit"),
                        "technical_score": data.get("technical_score", 50),
                        "sentiment_score": data.get("sentiment_score", 50),
                        "timestamp": data.get("timestamp", datetime.now().isoformat()),
                    }
            except Exception:
                pass

    # Demo data if no analysis file found
    return {
        "signal": "HOLD",
        "confidence": "MEDIUM",
        "confidence_score": 55,
        "bull_analysis": "RSI showing oversold conditions near key support. Volume increasing on bounces suggests accumulation phase.",
        "bear_analysis": "Price below 200 SMA on daily. Resistance at $105,000 has rejected multiple times. Funding rate positive indicates crowded longs.",
        "judge_reasoning": "Mixed signals warrant caution. Technical indicators suggest potential reversal but macro headwinds persist. Wait for confirmation.",
        "entry_price": None,
        "stop_loss": None,
        "take_profit": None,
        "technical_score": 60,
        "sentiment_score": 45,
        "timestamp": datetime.now().isoformat(),
    }
