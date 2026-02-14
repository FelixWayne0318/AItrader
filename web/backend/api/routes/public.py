"""
Public API Routes - No authentication required
"""
import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.database import get_db
from core.config import settings
from models import SocialLink, CopyTradingLink, SiteSettings
from services.performance_service import get_performance_service
from services.trade_evaluation_service import get_trade_evaluation_service

router = APIRouter(prefix="/public", tags=["Public"])

# Upload directory for public file access
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")


@router.get("/performance")
async def get_performance(days: int = 30):
    """
    Get trading performance statistics

    Returns aggregated stats without exposing individual trades
    """
    # Note: performance_service doesn't currently support days parameter
    # It uses fixed 90-day lookback for income history
    service = get_performance_service()
    stats = await service.get_performance_stats()
    return stats


@router.get("/performance/summary")
async def get_performance_summary():
    """Get quick performance summary for homepage"""
    service = get_performance_service()
    stats = await service.get_performance_stats()

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


@router.get("/site-branding")
async def get_site_branding(db: AsyncSession = Depends(get_db)):
    """Get site branding settings (logo, favicon, site name)"""
    branding_keys = ["logo_url", "favicon_url", "site_name", "site_tagline"]
    result = await db.execute(
        select(SiteSettings).where(SiteSettings.key.in_(branding_keys))
    )
    settings = result.scalars().all()

    branding = {s.key: s.value for s in settings}

    return {
        "logo_url": branding.get("logo_url"),
        "favicon_url": branding.get("favicon_url"),
        "site_name": branding.get("site_name", "AlgVex"),
        "site_tagline": branding.get("site_tagline"),
    }


@router.get("/uploads/{filename}")
async def get_public_upload(filename: str):
    """Serve uploaded files publicly (logos, favicons)"""
    # Security: only allow specific prefixes for public access
    allowed_prefixes = ["logo_", "favicon_"]
    if not any(filename.startswith(prefix) for prefix in allowed_prefixes):
        raise HTTPException(status_code=403, detail="Access denied")

    filepath = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(filepath)


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
    aitrader_path = Path(settings.AITRADER_PATH) if settings.AITRADER_PATH else Path(".")
    signal_file_paths = [
        str(aitrader_path / "logs" / "latest_signal.json"),
        str(aitrader_path / "state" / "latest_signal.json"),
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
                        "data_source": "live",  # v3.8: Indicate real data
                    }
            except Exception:
                pass

    # v3.8: Return clear "no data" status instead of fake data
    return {
        "signal": "NO_DATA",
        "confidence": "NONE",
        "reason": "等待交易机器人生成信号 (Waiting for trading bot to generate signal)",
        "symbol": "BTCUSDT",
        "timestamp": datetime.now().isoformat(),
        "data_source": "none",  # Clearly indicate no real data available
    }


@router.get("/signal-history")
async def get_signal_history(limit: int = 10):
    """Get recent AI signal history"""
    import os
    import json
    from datetime import datetime

    aitrader_path = Path(settings.AITRADER_PATH) if settings.AITRADER_PATH else Path(".")
    history_file_paths = [
        str(aitrader_path / "logs" / "signal_history.json"),
        str(aitrader_path / "state" / "signal_history.json"),
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
                        "data_source": "live",  # v3.8: Indicate real data
                    }
            except Exception:
                pass

    # v3.8: Return empty array instead of fake data
    return {
        "signals": [],
        "total": 0,
        "data_source": "none",  # Clearly indicate no real data available
        "message": "等待交易机器人生成信号历史 (Waiting for trading bot to generate signal history)",
    }


@router.get("/ai-analysis")
async def get_ai_analysis():
    """Get detailed AI analysis including Bull/Bear debate"""
    import os
    import json
    from datetime import datetime

    aitrader_path = Path(settings.AITRADER_PATH) if settings.AITRADER_PATH else Path(".")
    analysis_file_paths = [
        str(aitrader_path / "logs" / "latest_analysis.json"),
        str(aitrader_path / "state" / "latest_analysis.json"),
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
                        "data_source": "live",  # v3.8: Indicate real data
                    }
            except Exception:
                pass

    # v3.8: Return clear "no data" status instead of fake analysis
    return {
        "signal": "NO_DATA",
        "confidence": "NONE",
        "confidence_score": 0,
        "bull_analysis": "等待交易机器人生成分析 (Waiting for trading bot to generate analysis)",
        "bear_analysis": "等待交易机器人生成分析 (Waiting for trading bot to generate analysis)",
        "judge_reasoning": "交易机器人尚未运行分析周期 (Trading bot has not run an analysis cycle yet)",
        "entry_price": None,
        "stop_loss": None,
        "take_profit": None,
        "technical_score": 0,
        "sentiment_score": 0,
        "timestamp": datetime.now().isoformat(),
        "data_source": "none",  # Clearly indicate no real data available
    }


# =============================================================================
# Trade Evaluation Endpoints (v5.1)
# Expose trade quality metrics from decision_memory
# =============================================================================


@router.get("/trade-evaluation/summary")
async def get_trade_evaluation_summary(days: int = 30):
    """
    Get aggregate trade evaluation statistics.

    Public endpoint - returns grade distribution, R/R stats, confidence accuracy.
    No sensitive data (prices, conditions) included.

    Parameters
    ----------
    days : int, optional
        Number of days to look back (default: 30, 0 = all time)

    Returns
    -------
    Dict
        {
            "total_evaluated": int,
            "grade_distribution": {"A+": 3, "A": 5, "B": 4, ...},
            "direction_accuracy": float,  // Win rate %
            "avg_winning_rr": float,      // Average R/R for wins
            "avg_execution_quality": float,
            "avg_grade_score": float,     // Quality score 0-5
            "exit_type_distribution": {"TAKE_PROFIT": 10, ...},
            "confidence_accuracy": {
                "HIGH": {"total": 10, "wins": 7, "accuracy": 70.0},
                ...
            },
            "avg_hold_duration_min": int,
            "last_updated": str (ISO timestamp)
        }
    """
    service = get_trade_evaluation_service()
    days_filter = None if days == 0 else days
    return service.get_evaluation_summary(days=days_filter)


@router.get("/trade-evaluation/recent")
async def get_recent_trade_evaluations(limit: int = 20):
    """
    Get recent trade evaluations (public view - sanitized).

    Excludes sensitive fields (entry/exit prices, conditions).
    Suitable for displaying trade quality on public website.

    Parameters
    ----------
    limit : int, optional
        Maximum number of trades to return (default: 20, max: 100)

    Returns
    -------
    List[Dict]
        [
            {
                "grade": "A",
                "planned_rr": 2.0,
                "actual_rr": 1.8,
                "execution_quality": 0.9,
                "exit_type": "TAKE_PROFIT",
                "confidence": "HIGH",
                "hold_duration_min": 1847,
                "direction_correct": true,
                "timestamp": "2026-02-14T02:00:00"
            },
            ...
        ]
    """
    service = get_trade_evaluation_service()
    limit = min(limit, 100)  # Cap at 100 for performance
    return service.get_recent_trades(limit=limit, include_details=False)

