"""
Database Models for Settings and Configuration
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func

from core.database import Base


class SocialLink(Base):
    """Social media links configuration"""
    __tablename__ = "social_links"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(50), unique=True, nullable=False)  # telegram, twitter, discord
    url = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CopyTradingLink(Base):
    """Copy trading links for different exchanges"""
    __tablename__ = "copy_trading_links"

    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String(50), nullable=False)  # binance, bybit, okx, bitget
    name = Column(String(100), nullable=False)  # Display name
    url = Column(Text, nullable=True)
    trader_id = Column(String(100), nullable=True)  # Trader/Lead ID
    enabled = Column(Boolean, default=True)
    icon = Column(String(50), nullable=True)  # Icon identifier
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class SiteSettings(Base):
    """General site settings"""
    __tablename__ = "site_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PerformanceCache(Base):
    """Cached performance data from Binance"""
    __tablename__ = "performance_cache"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String(10), unique=True, nullable=False)  # YYYY-MM-DD
    daily_pnl = Column(String(50), nullable=True)  # Store as string to preserve precision
    cumulative_pnl = Column(String(50), nullable=True)
    win_rate = Column(String(20), nullable=True)
    total_trades = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
