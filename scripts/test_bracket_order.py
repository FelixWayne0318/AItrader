#!/usr/bin/env python3
"""
Bracket Order (Algo Order API) 下单能力检测
用 0.002 BTC 最小金额测试 STOP_MARKET / TAKE_PROFIT_MARKET 是否被接受
测试后立即清理 (取消挂单 + 平仓)
"""
import os
import sys
import time
import hmac
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.env.aitrader"))

API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")
BASE = "https://fapi.binance.com"


def sign(params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    sig = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    return query + "&signature=" + sig


def api_post(path, params):
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 5000
    url = f"{BASE}{path}?{sign(params)}"
    return requests.post(url, headers={"X-MBX-APIKEY": API_KEY}, timeout=10)


def api_get(path, params=None):
    p = params or {}
    p["timestamp"] = int(time.time() * 1000)
    p["recvWindow"] = 5000
    url = f"{BASE}{path}?{sign(p)}"
    return requests.get(url, headers={"X-MBX-APIKEY": API_KEY}, timeout=10)


def api_delete(path, params):
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 5000
    url = f"{BASE}{path}?{sign(params)}"
    return requests.delete(url, headers={"X-MBX-APIKEY": API_KEY}, timeout=10)


def cleanup(qty):
    """Emergency cleanup: cancel all orders + close position"""
    try:
        api_delete("/fapi/v1/allOpenOrders", {"symbol": "BTCUSDT"})
        time.sleep(0.5)
        api_post("/fapi/v1/order", {
            "symbol": "BTCUSDT", "side": "SELL",
            "type": "MARKET", "quantity": qty, "reduceOnly": "true",
        })
        print("  OK Cleanup done")
    except Exception as e:
        print(f"  XX Cleanup failed: {e}")
        print("  !! MANUAL CLEANUP MAY BE NEEDED")


def main():
    print("=" * 60)
    print("  Bracket Order Test (0.002 BTC)")
    print("=" * 60)

    qty = "0.002"

    # 1. Get price
    print("\n[1/4] Market price")
    r = requests.get(f"{BASE}/fapi/v1/ticker/price",
                     params={"symbol": "BTCUSDT"}, timeout=5)
    price = float(r.json()["price"])
    print(f"  BTCUSDT: ${price:,.2f}")

    # 2. Check position
    print("\n[2/4] Position check")
    r = api_get("/fapi/v2/positionRisk", {"symbol": "BTCUSDT"})
    for p in r.json():
        amt = float(p.get("positionAmt", 0))
        if amt != 0:
            print(f"  HAS POSITION: {amt} BTC - ABORTING")
            sys.exit(0)
    print("  No position - safe to test")

    # 3. Calculate SL/TP
    sl_price = str(round(price * 0.98, 2))
    tp_price = str(round(price * 1.03, 2))
    print(f"\n[3/4] Order params")
    print(f"  Entry: MARKET BUY {qty} BTC")
    print(f"  SL: ${sl_price} (2% below)")
    print(f"  TP: ${tp_price} (3% above)")
    print(f"  Notional: ~${price * float(qty):,.2f}")

    # 4. Execute test
    print(f"\n[4/4] Bracket order test")

    # Entry order
    r1 = api_post("/fapi/v1/order", {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
        "quantity": qty,
    })
    if r1.status_code != 200:
        err = r1.json()
        print(f"  XX Entry FAILED: {err.get('code','')} {err.get('msg','')}")
        sys.exit(1)
    print(f"  OK Entry: orderId={r1.json()['orderId']}")

    # SL (STOP_MARKET) - THE KEY TEST
    r2 = api_post("/fapi/v1/order", {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "STOP_MARKET",
        "stopPrice": sl_price,
        "quantity": qty,
        "reduceOnly": "true",
    })
    if r2.status_code == 200:
        print(f"  OK SL (STOP_MARKET): orderId={r2.json()['orderId']}")
    else:
        err = r2.json()
        print(f"  XX SL FAILED: {err.get('code','')} {err.get('msg','')}")

    # TP (TAKE_PROFIT_MARKET) - THE KEY TEST
    r3 = api_post("/fapi/v1/order", {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "TAKE_PROFIT_MARKET",
        "stopPrice": tp_price,
        "quantity": qty,
        "reduceOnly": "true",
    })
    if r3.status_code == 200:
        print(f"  OK TP (TAKE_PROFIT_MARKET): orderId={r3.json()['orderId']}")
    else:
        err = r3.json()
        print(f"  XX TP FAILED: {err.get('code','')} {err.get('msg','')}")

    # Cleanup
    print("\n  --- Cleanup ---")
    cleanup(qty)

    # Summary
    sl_ok = r2.status_code == 200
    tp_ok = r3.status_code == 200
    print("\n" + "=" * 60)
    if sl_ok and tp_ok:
        print("  RESULT: ALL PASSED - Bracket orders work!")
    elif not sl_ok and not tp_ok:
        print("  RESULT: BOTH FAILED - Algo Order API issue")
    else:
        print(f"  RESULT: SL={'OK' if sl_ok else 'FAIL'}, TP={'OK' if tp_ok else 'FAIL'}")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nXX Fatal error: {e}")
        import traceback
        traceback.print_exc()
        print("\nAttempting cleanup...")
        cleanup("0.002")
