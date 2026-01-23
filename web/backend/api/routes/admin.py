"""
Admin API Routes - Authentication required
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, Any

from core.database import get_db
from models import SocialLink, CopyTradingLink, SiteSettings
from services import config_service
from api.deps import get_current_admin

router = APIRouter(prefix="/admin", tags=["Admin"])


# ============ Schemas ============

class SocialLinkUpdate(BaseModel):
    platform: str
    url: Optional[str] = None
    enabled: bool = True


class CopyTradingLinkCreate(BaseModel):
    exchange: str
    name: str
    url: Optional[str] = None
    trader_id: Optional[str] = None
    enabled: bool = True
    icon: Optional[str] = None
    sort_order: int = 0


class CopyTradingLinkUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    trader_id: Optional[str] = None
    enabled: Optional[bool] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None


class ConfigUpdate(BaseModel):
    path: str
    value: Any


class ServiceAction(BaseModel):
    action: str  # restart, stop, start
    confirm: bool = False


# ============ Strategy Configuration ============

@router.get("/config")
async def get_strategy_config(admin=Depends(get_current_admin)):
    """Get full strategy configuration"""
    config = config_service.read_strategy_config()
    return config


@router.put("/config")
async def update_strategy_config(update: ConfigUpdate, admin=Depends(get_current_admin)):
    """Update a specific configuration value"""
    success = config_service.update_config_value(update.path, update.value)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update configuration")
    return {"success": True, "message": f"Updated {update.path}"}


@router.put("/config/full")
async def update_full_config(config: dict, admin=Depends(get_current_admin)):
    """Update full strategy configuration"""
    success = config_service.write_strategy_config(config)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update configuration")
    return {"success": True, "message": "Configuration updated"}


# ============ Service Control ============

@router.get("/service/status")
async def get_service_status(admin=Depends(get_current_admin)):
    """Get detailed service status"""
    return config_service.get_service_status()


@router.post("/service/control")
async def control_service(action: ServiceAction, admin=Depends(get_current_admin)):
    """Control the trading service (restart/stop/start)"""
    if not action.confirm:
        raise HTTPException(
            status_code=400,
            detail="Please confirm the action by setting confirm=true"
        )

    if action.action == "restart":
        success, message = config_service.restart_service()
    elif action.action == "stop":
        success, message = config_service.stop_service()
    elif action.action == "start":
        success, message = config_service.start_service()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")

    if not success:
        raise HTTPException(status_code=500, detail=message)

    return {"success": True, "message": message}


@router.get("/service/logs")
async def get_service_logs(lines: int = 100, admin=Depends(get_current_admin)):
    """Get recent service logs"""
    if lines > 1000:
        lines = 1000
    logs = config_service.get_recent_logs(lines)
    return {"logs": logs}


# ============ Social Links ============

@router.get("/social-links")
async def list_social_links(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin)
):
    """List all social links (including disabled)"""
    result = await db.execute(select(SocialLink))
    links = result.scalars().all()
    return [
        {
            "id": link.id,
            "platform": link.platform,
            "url": link.url,
            "enabled": link.enabled,
        }
        for link in links
    ]


@router.put("/social-links/{platform}")
async def update_social_link(
    platform: str,
    data: SocialLinkUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin)
):
    """Update or create a social link"""
    result = await db.execute(
        select(SocialLink).where(SocialLink.platform == platform)
    )
    link = result.scalar_one_or_none()

    if link:
        link.url = data.url
        link.enabled = data.enabled
    else:
        link = SocialLink(
            platform=platform,
            url=data.url,
            enabled=data.enabled
        )
        db.add(link)

    await db.commit()
    return {"success": True, "platform": platform}


# ============ Copy Trading Links ============

@router.get("/copy-trading")
async def list_copy_trading_links(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin)
):
    """List all copy trading links"""
    result = await db.execute(
        select(CopyTradingLink).order_by(CopyTradingLink.sort_order)
    )
    links = result.scalars().all()
    return [
        {
            "id": link.id,
            "exchange": link.exchange,
            "name": link.name,
            "url": link.url,
            "trader_id": link.trader_id,
            "enabled": link.enabled,
            "icon": link.icon,
            "sort_order": link.sort_order,
        }
        for link in links
    ]


@router.post("/copy-trading")
async def create_copy_trading_link(
    data: CopyTradingLinkCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin)
):
    """Create a new copy trading link"""
    link = CopyTradingLink(
        exchange=data.exchange,
        name=data.name,
        url=data.url,
        trader_id=data.trader_id,
        enabled=data.enabled,
        icon=data.icon,
        sort_order=data.sort_order,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return {"success": True, "id": link.id}


@router.put("/copy-trading/{link_id}")
async def update_copy_trading_link(
    link_id: int,
    data: CopyTradingLinkUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin)
):
    """Update a copy trading link"""
    result = await db.execute(
        select(CopyTradingLink).where(CopyTradingLink.id == link_id)
    )
    link = result.scalar_one_or_none()

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    if data.name is not None:
        link.name = data.name
    if data.url is not None:
        link.url = data.url
    if data.trader_id is not None:
        link.trader_id = data.trader_id
    if data.enabled is not None:
        link.enabled = data.enabled
    if data.icon is not None:
        link.icon = data.icon
    if data.sort_order is not None:
        link.sort_order = data.sort_order

    await db.commit()
    return {"success": True, "id": link_id}


@router.delete("/copy-trading/{link_id}")
async def delete_copy_trading_link(
    link_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin)
):
    """Delete a copy trading link"""
    result = await db.execute(
        select(CopyTradingLink).where(CopyTradingLink.id == link_id)
    )
    link = result.scalar_one_or_none()

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    await db.delete(link)
    await db.commit()
    return {"success": True}


# ============ Site Settings ============

@router.get("/settings")
async def list_site_settings(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin)
):
    """List all site settings"""
    result = await db.execute(select(SiteSettings))
    settings = result.scalars().all()
    return {s.key: s.value for s in settings}


@router.put("/settings/{key}")
async def update_site_setting(
    key: str,
    value: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin)
):
    """Update a site setting"""
    result = await db.execute(
        select(SiteSettings).where(SiteSettings.key == key)
    )
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = value
    else:
        setting = SiteSettings(key=key, value=value)
        db.add(setting)

    await db.commit()
    return {"success": True, "key": key}
