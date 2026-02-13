"""
Trading API Routes - Real-time trading data from Binance
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional

from services.trading_service import trading_service
from api.deps import get_current_admin

router = APIRouter(prefix="/trading", tags=["Trading"])


# ============================================================================
# Public Market Data (No Auth Required)
# ============================================================================
@router.get("/ticker/{symbol}")
async def get_ticker(symbol: str = "BTCUSDT"):
    """Get 24hr ticker for a symbol"""
    data = await trading_service.get_ticker(symbol)
    return data or {"error": "Failed to fetch ticker"}


@router.get("/mark-price/{symbol}")
async def get_mark_price(symbol: str = "BTCUSDT"):
    """Get mark price and funding rate"""
    data = await trading_service.get_mark_price(symbol)
    return data or {"error": "Failed to fetch mark price"}


@router.get("/klines/{symbol}")
async def get_klines(
    symbol: str = "BTCUSDT",
    interval: str = Query("15m", description="Kline interval (1m, 5m, 15m, 1h, 4h, 1d)"),
    limit: int = Query(100, ge=1, le=1500)
):
    """Get kline/candlestick data"""
    data = await trading_service.get_klines(symbol, interval, limit)
    return {"symbol": symbol, "interval": interval, "klines": data}


@router.get("/orderbook/{symbol}")
async def get_order_book(
    symbol: str = "BTCUSDT",
    limit: int = Query(20, ge=5, le=100)
):
    """Get order book depth"""
    data = await trading_service.get_order_book(symbol, limit)
    return data or {"error": "Failed to fetch order book"}


@router.get("/long-short-ratio/{symbol}")
async def get_long_short_ratio(
    symbol: str = "BTCUSDT",
    period: str = Query("15m", description="Period (5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d)"),
    limit: int = Query(10, ge=1, le=100)
):
    """Get long/short account ratio"""
    data = await trading_service.get_long_short_ratio(symbol, period, limit)
    return {"symbol": symbol, "period": period, "data": data}


@router.get("/open-interest/{symbol}")
async def get_open_interest(symbol: str = "BTCUSDT"):
    """Get open interest and 24h change"""
    data = await trading_service.get_open_interest(symbol)
    return data or {"error": "Failed to fetch open interest"}


# ============================================================================
# Protected Account Data (Auth Required)
# ============================================================================
@router.get("/account")
async def get_account(admin=Depends(get_current_admin)):
    """Get account information with balances"""
    data = await trading_service.get_account_info()
    if data:
        return data
    return {"error": "Failed to fetch account info", "detail": "Check API credentials"}


@router.get("/positions")
async def get_positions(
    symbol: Optional[str] = None,
    admin=Depends(get_current_admin)
):
    """Get all open positions"""
    data = await trading_service.get_positions(symbol)
    return {"positions": data, "count": len(data)}


@router.get("/orders/open")
async def get_open_orders(
    symbol: Optional[str] = None,
    admin=Depends(get_current_admin)
):
    """Get all open orders"""
    data = await trading_service.get_open_orders(symbol)
    return {"orders": data, "count": len(data)}


@router.get("/orders/history")
async def get_order_history(
    symbol: str = "BTCUSDT",
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(100, ge=1, le=500),
    admin=Depends(get_current_admin)
):
    """Get order history"""
    data = await trading_service.get_order_history(symbol, days, limit)
    return {"orders": data, "count": len(data)}


@router.get("/trades")
async def get_trade_history(
    symbol: str = "BTCUSDT",
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(100, ge=1, le=500),
    admin=Depends(get_current_admin)
):
    """Get trade/fill history"""
    data = await trading_service.get_trade_history(symbol, days, limit)
    return {"trades": data, "count": len(data)}


@router.get("/income")
async def get_income_history(
    income_type: Optional[str] = Query(None, description="REALIZED_PNL, FUNDING_FEE, COMMISSION, TRANSFER"),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(500, ge=1, le=1000),
    admin=Depends(get_current_admin)
):
    """Get income history (PnL, funding, commissions)"""
    data = await trading_service.get_income_history(income_type, days, limit)
    return {"income": data, "count": len(data)}


@router.get("/performance")
async def get_performance(
    days: int = Query(30, ge=1, le=365),
    admin=Depends(get_current_admin)
):
    """Get comprehensive performance statistics"""
    data = await trading_service.get_performance_stats(days)
    return data


# ============================================================================
# Dashboard Summary (Auth Required)
# ============================================================================
@router.get("/dashboard")
async def get_dashboard_data(admin=Depends(get_current_admin)):
    """Get all dashboard data in one request"""
    import asyncio

    # Fetch all data concurrently
    account_task = trading_service.get_account_info()
    positions_task = trading_service.get_positions()
    orders_task = trading_service.get_open_orders()
    ticker_task = trading_service.get_ticker("BTCUSDT")
    mark_task = trading_service.get_mark_price("BTCUSDT")
    performance_task = trading_service.get_performance_stats(30)

    results = await asyncio.gather(
        account_task,
        positions_task,
        orders_task,
        ticker_task,
        mark_task,
        performance_task,
        return_exceptions=True
    )

    return {
        "account": results[0] if not isinstance(results[0], Exception) else None,
        "positions": results[1] if not isinstance(results[1], Exception) else [],
        "open_orders": results[2] if not isinstance(results[2], Exception) else [],
        "ticker": results[3] if not isinstance(results[3], Exception) else None,
        "mark_price": results[4] if not isinstance(results[4], Exception) else None,
        "performance": results[5] if not isinstance(results[5], Exception) else None,
    }
