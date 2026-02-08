#!/usr/bin/env python3
"""
Bracket Order 下单能力检测 v2
测试 3 种路径:
  1. 旧端点 /fapi/v1/order (预期失败)
  2. 新端点 /fapi/v1/algoOrder (预期成功)
  3. NautilusTrader 内部路由 (检查 NT 是否自动用新端点)
"""
import os
import sys
import time
import hmac
import hashlib
import inspect
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
    """Cancel all orders + close position"""
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


def main():
    print("=" * 60)
    print("  Bracket Order Test v2 (3 paths)")
    print("=" * 60)

    qty = "0.002"

    # === Test 1: NT source code analysis ===
    print("\n[1/4] NautilusTrader 1.222.0 源码分析")
    try:
        # Check execution client
        from nautilus_trader.adapters.binance.futures.execution import BinanceFuturesExecutionClient
        src_exec = inspect.getsource(BinanceFuturesExecutionClient)

        # Check HTTP account module
        from nautilus_trader.adapters.binance.futures.http import account as nt_account
        src_account = inspect.getsource(nt_account)

        # Check HTTP module
        from nautilus_trader.adapters.binance.http import client as nt_client
        src_client = inspect.getsource(nt_client)

        # Search for algo-related strings across all sources
        all_src = src_exec + src_account + src_client
        keywords = ["algoOrder", "algo_order", "algo", "/fapi/v1/algo"]
        print("  Execution client:")
        for kw in keywords:
            found = kw in all_src
            print(f"    {'OK' if found else '--'} '{kw}': {'found' if found else 'not found'}")

        # Check what URL is used for STOP orders
        # Look for the submit_stop_market or similar method
        print("\n  Order submission methods:")
        for method_name in dir(BinanceFuturesExecutionClient):
            if "stop" in method_name.lower() or "order" in method_name.lower():
                if not method_name.startswith("_"):
                    continue
                if "submit" in method_name.lower() or "stop" in method_name.lower():
                    print(f"    - {method_name}")

        # Check all HTTP endpoint definitions
        print("\n  HTTP endpoints in account module:")
        for line in src_account.split("\n"):
            stripped = line.strip()
            if "fapi" in stripped and ("order" in stripped.lower() or "algo" in stripped.lower()):
                print(f"    {stripped[:100]}")

        # Check if there's any order type routing logic
        print("\n  Order type routing:")
        if "STOP_MARKET" in src_account:
            print("    OK STOP_MARKET in account module")
        else:
            print("    -- STOP_MARKET not in account module")
        if "TAKE_PROFIT" in src_account:
            print("    OK TAKE_PROFIT in account module")
        else:
            print("    -- TAKE_PROFIT not in account module")

        # Look at the new_order method signature and body
        print("\n  new_order endpoint search:")
        for attr_name in dir(nt_account):
            obj = getattr(nt_account, attr_name, None)
            if obj and hasattr(obj, '__module__'):
                try:
                    obj_src = inspect.getsource(obj)
                    if "new_order" in obj_src.lower() or "place_order" in obj_src.lower():
                        # Find the URL used
                        for line in obj_src.split("\n"):
                            if "url" in line.lower() or "endpoint" in line.lower() or "fapi" in line:
                                print(f"    [{attr_name}] {line.strip()[:120]}")
                except:
                    pass

    except Exception as e:
        print(f"  XX Source analysis error: {e}")
        import traceback
        traceback.print_exc()

    # === Test 2: Price and position ===
    print("\n[2/4] Market state")
    r = requests.get(f"{BASE}/fapi/v1/ticker/price",
                     params={"symbol": "BTCUSDT"}, timeout=5)
    price = float(r.json()["price"])
    print(f"  Price: ${price:,.2f}")

    r = api_get("/fapi/v2/positionRisk", {"symbol": "BTCUSDT"})
    has_pos = any(float(p.get("positionAmt", 0)) != 0 for p in r.json())
    if has_pos:
        print("  HAS POSITION - aborting order test")
        return
    print("  No position")

    sl_price = str(round(price * 0.98, 2))
    tp_price = str(round(price * 1.03, 2))

    # === Test 3: Old endpoint (expected to fail) ===
    print(f"\n[3/4] Old endpoint /fapi/v1/order")

    # Entry first
    r1 = api_post("/fapi/v1/order", {
        "symbol": "BTCUSDT", "side": "BUY",
        "type": "MARKET", "quantity": qty,
    })
    if r1.status_code != 200:
        print(f"  XX Entry failed: {r1.json().get('msg','')}")
        return
    print(f"  OK Entry: orderId={r1.json()['orderId']}")

    # SL via old endpoint
    r2_old = api_post("/fapi/v1/order", {
        "symbol": "BTCUSDT", "side": "SELL",
        "type": "STOP_MARKET", "stopPrice": sl_price,
        "quantity": qty, "reduceOnly": "true",
    })
    if r2_old.status_code == 200:
        print(f"  OK SL (old endpoint): works!")
        old_sl_id = r2_old.json()["orderId"]
        # Cancel it for next test
        api_delete("/fapi/v1/allOpenOrders", {"symbol": "BTCUSDT"})
    else:
        err = r2_old.json()
        print(f"  XX SL (old endpoint): {err.get('code','')} {err.get('msg','')}")
        print(f"     (expected - old endpoint no longer supported)")

    # === Test 4: New algo endpoint ===
    print(f"\n[4/4] New endpoint /fapi/v1/algoOrder")

    # SL via algo endpoint
    r2_new = api_post("/fapi/v1/algoOrder", {
        "symbol": "BTCUSDT", "side": "SELL",
        "type": "STOP_MARKET", "stopPrice": sl_price,
        "quantity": qty, "reduceOnly": "true",
    })
    if r2_new.status_code == 200:
        print(f"  OK SL (algo endpoint): orderId={r2_new.json().get('orderId', r2_new.json())}")
    else:
        err = r2_new.json()
        print(f"  XX SL (algo endpoint): {err.get('code','')} {err.get('msg','')}")
        print(f"     Full response: {r2_new.text[:300]}")

    # TP via algo endpoint
    r3_new = api_post("/fapi/v1/algoOrder", {
        "symbol": "BTCUSDT", "side": "SELL",
        "type": "TAKE_PROFIT_MARKET", "stopPrice": tp_price,
        "quantity": qty, "reduceOnly": "true",
    })
    if r3_new.status_code == 200:
        print(f"  OK TP (algo endpoint): orderId={r3_new.json().get('orderId', r3_new.json())}")
    else:
        err = r3_new.json()
        print(f"  XX TP (algo endpoint): {err.get('code','')} {err.get('msg','')}")
        print(f"     Full response: {r3_new.text[:300]}")

    # Cleanup
    print("\n  --- Cleanup ---")
    cleanup(qty)

    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("  Old /fapi/v1/order:    " + ("OK" if r2_old.status_code == 200 else "BLOCKED (expected)"))
    print("  New /fapi/v1/algoOrder: " + ("OK" if r2_new.status_code == 200 else "FAILED"))
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nXX Fatal: {e}")
        import traceback
        traceback.print_exc()
        print("\nEmergency cleanup...")
        cleanup("0.002")
