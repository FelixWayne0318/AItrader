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
