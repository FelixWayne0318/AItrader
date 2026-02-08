#!/usr/bin/env python3
"""
Bracket Order 下单能力检测 v3
1. 深度分析 NT 1.222.0 如何路由 STOP_MARKET 到 algo endpoint
2. 找到正确的 algotype 参数
3. 用正确参数测试下单
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


def api_delete(path, params):
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 5000
    url = f"{BASE}{path}?{sign(params)}"
    return requests.delete(url, headers={"X-MBX-APIKEY": API_KEY}, timeout=10)


def api_get(path, params=None):
    p = params or {}
    p["timestamp"] = int(time.time() * 1000)
    p["recvWindow"] = 5000
    url = f"{BASE}{path}?{sign(p)}"
    return requests.get(url, headers={"X-MBX-APIKEY": API_KEY}, timeout=10)


def cleanup(qty):
    try:
        api_delete("/fapi/v1/allOpenOrders", {"symbol": "BTCUSDT"})
        # Also try to cancel algo orders
        try:
            api_delete("/fapi/v1/algoOpenOrders", {"symbol": "BTCUSDT"})
        except:
            pass
        time.sleep(0.5)
        api_post("/fapi/v1/order", {
            "symbol": "BTCUSDT", "side": "SELL",
            "type": "MARKET", "quantity": qty, "reduceOnly": "true",
        })
        print("  OK Cleanup done")
    except Exception as e:
        print(f"  XX Cleanup: {e}")


def main():
    print("=" * 60)
    print("  Bracket Order Test v3 - Deep NT Source Analysis")
    print("=" * 60)

    qty = "0.002"

    # === 1. Deep NT source analysis ===
    print("\n[1/3] NT 1.222.0 Algo Order 源码深度分析")

    try:
        # Find the algo order HTTP endpoint class
        import nautilus_trader.adapters.binance.futures.http.account as acct_mod
        src = inspect.getsource(acct_mod)

        # Find all classes in the module
        print("\n  Classes in account module:")
        for name, obj in inspect.getmembers(acct_mod, inspect.isclass):
            if "algo" in name.lower() or "order" in name.lower():
                print(f"    - {name}")

        # Find the algo order class and its parameters
        print("\n  Algo Order class details:")
        for name, obj in inspect.getmembers(acct_mod, inspect.isclass):
            if "algo" in name.lower():
                obj_src = inspect.getsource(obj)
                print(f"\n  === {name} ===")
                # Print first 50 lines
                lines = obj_src.split("\n")
                for i, line in enumerate(lines[:80]):
                    print(f"    {line}")
                if len(lines) > 80:
                    print(f"    ... ({len(lines) - 80} more lines)")

        # Also check the endpoint module for algo
        print("\n  Searching for 'algotype' in NT source:")
        if "algotype" in src:
            for i, line in enumerate(src.split("\n")):
                if "algotype" in line.lower():
                    print(f"    L{i}: {line.strip()[:120]}")
        else:
            print("    'algotype' NOT found in account module")

        # Check endpoint module
        try:
            import nautilus_trader.adapters.binance.http.endpoint as ep_mod
            ep_src = inspect.getsource(ep_mod)
            if "algotype" in ep_src.lower():
                print("    Found 'algotype' in endpoint module")
        except:
            pass

        # Search ALL binance adapter files
        print("\n  Global search for 'algotype':")
        import nautilus_trader.adapters.binance as bn
        bn_path = os.path.dirname(bn.__file__)
        import glob
        for py_file in glob.glob(os.path.join(bn_path, "**/*.py"), recursive=True):
            try:
                with open(py_file) as f:
                    content = f.read()
                if "algotype" in content.lower() or "algo_type" in content.lower():
                    fname = py_file.replace(bn_path, "binance")
                    for i, line in enumerate(content.split("\n")):
                        if "algotype" in line.lower() or "algo_type" in line.lower():
                            print(f"    {fname}:L{i}: {line.strip()[:120]}")
            except:
                pass

        # Search for how _submit_stop_market_order works
        print("\n  _submit_stop_market_order routing:")
        from nautilus_trader.adapters.binance.futures.execution import BinanceFuturesExecutionClient
        exec_src = inspect.getsource(BinanceFuturesExecutionClient)
        in_method = False
        for i, line in enumerate(exec_src.split("\n")):
            if "_submit_stop_market_order" in line and "def " in line:
                in_method = True
            if in_method:
                print(f"    {line}")
                if line.strip() and not line.strip().startswith("#") and not line.strip().startswith("def"):
                    if line.strip().startswith("return") or (line.strip() == "" and i > 0):
                        pass
                # Stop after 40 lines of the method
                if in_method and i > 0:
                    # Detect end of method (next def or class)
                    stripped = line.strip()
                    if stripped.startswith("def ") or stripped.startswith("class "):
                        if "_submit_stop_market_order" not in stripped:
                            break
            if in_method and i > 200:  # safety limit
                break

    except Exception as e:
        print(f"  XX Error: {e}")
        import traceback
        traceback.print_exc()

    # === 2. Get price, open entry ===
    print("\n\n[2/3] Market state + Entry")
    r = requests.get(f"{BASE}/fapi/v1/ticker/price",
                     params={"symbol": "BTCUSDT"}, timeout=5)
    price = float(r.json()["price"])
    print(f"  Price: ${price:,.2f}")

    r = api_get("/fapi/v2/positionRisk", {"symbol": "BTCUSDT"})
    has_pos = any(float(p.get("positionAmt", 0)) != 0 for p in r.json())
    if has_pos:
        print("  HAS POSITION - aborting")
        return
    print("  No position")

    sl_price = str(round(price * 0.98, 2))
    tp_price = str(round(price * 1.03, 2))

    # Entry
    r1 = api_post("/fapi/v1/order", {
        "symbol": "BTCUSDT", "side": "BUY",
        "type": "MARKET", "quantity": qty,
    })
    if r1.status_code != 200:
        print(f"  XX Entry failed: {r1.json().get('msg','')}")
        return
    print(f"  OK Entry: orderId={r1.json()['orderId']}")

    # === 3. Try multiple algotype values ===
    print(f"\n[3/3] Testing /fapi/v1/algoOrder with different algotype values")

    algo_types = ["STOP", "CONDITIONAL", "STOP_MARKET", "stop", "conditional_order"]

    best_result = None
    for algo_type in algo_types:
        r_test = api_post("/fapi/v1/algoOrder", {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "STOP_MARKET",
            "stopPrice": sl_price,
            "quantity": qty,
            "reduceOnly": "true",
            "algotype": algo_type,
        })
        status = "OK" if r_test.status_code == 200 else "XX"
        if r_test.status_code == 200:
            print(f"  OK algotype='{algo_type}': SUCCESS! orderId={r_test.json()}")
            best_result = algo_type
            # Cancel it
            try:
                api_delete("/fapi/v1/algoOpenOrders", {"symbol": "BTCUSDT"})
            except:
                api_delete("/fapi/v1/allOpenOrders", {"symbol": "BTCUSDT"})
            break
        else:
            err = r_test.json()
            print(f"  XX algotype='{algo_type}': {err.get('code','')} {err.get('msg','')[:80]}")

    if not best_result:
        # Try without 'type' field, just algotype
        print("\n  Trying without 'type' field:")
        for algo_type in ["STOP", "STOP_MARKET", "CONDITIONAL"]:
            r_test = api_post("/fapi/v1/algoOrder", {
                "symbol": "BTCUSDT",
                "side": "SELL",
                "stopPrice": sl_price,
                "quantity": qty,
                "reduceOnly": "true",
                "algotype": algo_type,
            })
            if r_test.status_code == 200:
                print(f"  OK algotype='{algo_type}' (no type): SUCCESS!")
                best_result = algo_type
                break
            else:
                err = r_test.json()
                print(f"  XX algotype='{algo_type}' (no type): {err.get('code','')} {err.get('msg','')[:80]}")

    # Cleanup
    print("\n  --- Cleanup ---")
    cleanup(qty)

    print("\n" + "=" * 60)
    if best_result:
        print(f"  RESULT: algotype='{best_result}' WORKS!")
    else:
        print("  RESULT: No working algotype found")
        print("  NT 1.222.0 may use a different API structure internally")
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
