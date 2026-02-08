#!/usr/bin/env python3
"""
Bracket Order 下单能力检测 v4
根据 v3 发现:
  - algoType="CONDITIONAL" 是正确值 (NT L1130 确认)
  - 参数名需要用 triggerPrice 而不是 stopPrice
本版本测试完整的 SL + TP 下单流程
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
        print(f"  Cleanup: {e}")


def main():
    print("=" * 60)
    print("  Bracket Order Test v4 - Correct Algo API Parameters")
    print("=" * 60)

    qty = "0.002"

    # === 1. Dump PostParameters + execution routing ===
    print("\n[1/4] NT PostParameters + Execution Routing\n")

    try:
        import nautilus_trader.adapters.binance.futures.http.account as acct_mod

        # Get PostParameters from BinanceFuturesAlgoOrderHttp
        for name, obj in inspect.getmembers(acct_mod, inspect.isclass):
            if name == "BinanceFuturesAlgoOrderHttp":
                for inner_name, inner_obj in inspect.getmembers(obj, inspect.isclass):
                    if "Post" in inner_name:
                        src = inspect.getsource(inner_obj)
                        print(f"  === {name}.{inner_name} ===")
                        for line in src.split("\n"):
                            print(f"    {line}")
                        print()

        # Find how execution client submits stop market orders
        print("  === Execution Client: _submit_stop_market / _submit_algo ===")
        from nautilus_trader.adapters.binance.futures.execution import BinanceFuturesExecutionClient
        exec_src = inspect.getsource(BinanceFuturesExecutionClient)

        # Search for algo-related methods
        keywords = ["_submit_stop_market", "_submit_algo", "_submit_take_profit", "algo_order", "algoOrder"]
        for kw in keywords:
            if kw.lower() in exec_src.lower():
                print(f"  Found '{kw}' in execution client")

        # Print all method signatures that mention algo or stop
        lines = exec_src.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("async def ") or stripped.startswith("def "):
                if any(k in stripped.lower() for k in ["algo", "stop", "take_profit", "conditional"]):
                    print(f"    L{i}: {stripped[:120]}")

        # Dump the full _submit_stop_market_order or similar
        print("\n  === Full method: _submit_stop_market_order ===")
        in_method = False
        method_indent = 0
        method_lines = []
        for i, line in enumerate(lines):
            if "_submit_stop_market_order" in line and ("def " in line or "async def " in line):
                in_method = True
                method_indent = len(line) - len(line.lstrip())
                method_lines = []
            if in_method:
                method_lines.append(f"    L{i}: {line}")
                # Detect method end (next method at same indent level)
                if len(method_lines) > 2:
                    curr_stripped = line.strip()
                    if curr_stripped and not curr_stripped.startswith("#") and not curr_stripped.startswith('"""'):
                        curr_indent = len(line) - len(line.lstrip())
                        if curr_indent <= method_indent and ("def " in curr_stripped or "class " in curr_stripped):
                            method_lines.pop()  # Remove the next method's line
                            break
                if len(method_lines) > 60:
                    method_lines.append("    ... (truncated at 60 lines)")
                    break
        if method_lines:
            for ml in method_lines:
                print(ml)
        else:
            # Try parent class
            print("    Not found in BinanceFuturesExecutionClient")
            print("    Searching parent classes...")
            for base_cls in BinanceFuturesExecutionClient.__mro__:
                base_name = base_cls.__name__
                if base_name in ("object",):
                    continue
                try:
                    base_src = inspect.getsource(base_cls)
                    if "_submit_stop_market" in base_src:
                        print(f"    Found in: {base_name}")
                        base_lines = base_src.split("\n")
                        in_m = False
                        for j, bl in enumerate(base_lines):
                            if "_submit_stop_market" in bl and ("def " in bl or "async def " in bl):
                                in_m = True
                            if in_m:
                                print(f"      L{j}: {bl}")
                                if len([x for x in range(j) if in_m]) > 60:
                                    break
                                if in_m and j > 0:
                                    bs = bl.strip()
                                    if bs.startswith("def ") or bs.startswith("async def "):
                                        if "_submit_stop_market" not in bs:
                                            break
                except:
                    pass

        # Also find how order list / bracket submits
        print("\n  === Full method: _submit_order_list ===")
        in_method = False
        method_lines = []
        for i, line in enumerate(lines):
            if "_submit_order_list" in line and ("def " in line or "async def " in line):
                in_method = True
                method_indent = len(line) - len(line.lstrip())
                method_lines = []
            if in_method:
                method_lines.append(f"    L{i}: {line}")
                if len(method_lines) > 2:
                    curr_stripped = line.strip()
                    if curr_stripped and not curr_stripped.startswith("#") and not curr_stripped.startswith('"""'):
                        curr_indent = len(line) - len(line.lstrip())
                        if curr_indent <= method_indent and ("def " in curr_stripped or "class " in curr_stripped):
                            method_lines.pop()
                            break
                if len(method_lines) > 80:
                    method_lines.append("    ... (truncated at 80 lines)")
                    break
        if method_lines:
            for ml in method_lines:
                print(ml)
        else:
            print("    Not found - searching parent classes...")
            for base_cls in BinanceFuturesExecutionClient.__mro__:
                try:
                    base_src = inspect.getsource(base_cls)
                    if "_submit_order_list" in base_src:
                        print(f"    Found in: {base_cls.__name__}")
                        break
                except:
                    pass

    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()

    # === 2. Get price ===
    print("\n\n[2/4] Market State")
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

    # === 3. Entry ===
    print(f"\n[3/4] Entry Order")
    r1 = api_post("/fapi/v1/order", {
        "symbol": "BTCUSDT", "side": "BUY",
        "type": "MARKET", "quantity": qty,
    })
    if r1.status_code != 200:
        print(f"  XX Entry failed: {r1.json().get('msg','')}")
        return
    print(f"  OK Entry: orderId={r1.json()['orderId']}")

    # === 4. Test SL + TP via Algo Order API ===
    print(f"\n[4/4] Algo Order API Tests (algoType=CONDITIONAL, triggerPrice)")
    print(f"  SL triggerPrice={sl_price}, TP triggerPrice={tp_price}")

    # --- Test A: SL via STOP_MARKET ---
    print("\n  --- Test A: STOP_MARKET (SL) ---")
    r_sl = api_post("/fapi/v1/algoOrder", {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "STOP_MARKET",
        "algoType": "CONDITIONAL",
        "triggerPrice": sl_price,
        "quantity": qty,
        "reduceOnly": "true",
    })
    if r_sl.status_code == 200:
        sl_data = r_sl.json()
        print(f"  OK SL: algoId={sl_data.get('algoId', '?')}, status={sl_data.get('algoStatus', '?')}")
    else:
        err = r_sl.json()
        print(f"  XX SL: {err.get('code','')} {err.get('msg','')}")
        # Try alternative parameter names
        print("\n  --- Test A2: with stopPrice instead ---")
        r_sl2 = api_post("/fapi/v1/algoOrder", {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "STOP_MARKET",
            "algoType": "CONDITIONAL",
            "stopPrice": sl_price,
            "quantity": qty,
            "reduceOnly": "true",
        })
        if r_sl2.status_code == 200:
            print(f"  OK SL (stopPrice): {r_sl2.json()}")
        else:
            print(f"  XX SL (stopPrice): {r_sl2.json().get('code','')} {r_sl2.json().get('msg','')}")

        print("\n  --- Test A3: with both triggerPrice + stopPrice ---")
        r_sl3 = api_post("/fapi/v1/algoOrder", {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "STOP_MARKET",
            "algoType": "CONDITIONAL",
            "triggerPrice": sl_price,
            "stopPrice": sl_price,
            "quantity": qty,
            "reduceOnly": "true",
        })
        if r_sl3.status_code == 200:
            print(f"  OK SL (both): {r_sl3.json()}")
        else:
            print(f"  XX SL (both): {r_sl3.json().get('code','')} {r_sl3.json().get('msg','')}")

        print("\n  --- Test A4: STOP type (limit-style) ---")
        limit_sl_price = str(round(price * 0.979, 2))
        r_sl4 = api_post("/fapi/v1/algoOrder", {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "STOP",
            "algoType": "CONDITIONAL",
            "triggerPrice": sl_price,
            "price": limit_sl_price,
            "quantity": qty,
            "reduceOnly": "true",
            "timeInForce": "GTC",
        })
        if r_sl4.status_code == 200:
            print(f"  OK SL (STOP): {r_sl4.json()}")
        else:
            print(f"  XX SL (STOP): {r_sl4.json().get('code','')} {r_sl4.json().get('msg','')}")

    # --- Test B: TP via TAKE_PROFIT_MARKET ---
    print("\n  --- Test B: TAKE_PROFIT_MARKET (TP) ---")
    r_tp = api_post("/fapi/v1/algoOrder", {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "TAKE_PROFIT_MARKET",
        "algoType": "CONDITIONAL",
        "triggerPrice": tp_price,
        "quantity": qty,
        "reduceOnly": "true",
    })
    if r_tp.status_code == 200:
        tp_data = r_tp.json()
        print(f"  OK TP: algoId={tp_data.get('algoId', '?')}, status={tp_data.get('algoStatus', '?')}")
    else:
        err = r_tp.json()
        print(f"  XX TP: {err.get('code','')} {err.get('msg','')}")

    # --- Check open algo orders ---
    print("\n  --- Open Algo Orders ---")
    r_open = api_get("/fapi/v1/openAlgoOrders")
    if r_open.status_code == 200:
        orders = r_open.json()
        if isinstance(orders, list):
            print(f"  Total open algo orders: {len(orders)}")
            for o in orders:
                print(f"    algoId={o.get('algoId')}, type={o.get('orderType')}, "
                      f"side={o.get('side')}, trigger={o.get('triggerPrice')}, "
                      f"status={o.get('algoStatus')}")
        else:
            print(f"  Response: {orders}")
    else:
        print(f"  XX: {r_open.json()}")

    # Cleanup
    print("\n  --- Cleanup ---")
    cleanup(qty)

    # Summary
    sl_ok = r_sl.status_code == 200
    tp_ok = r_tp.status_code == 200
    print("\n" + "=" * 60)
    print(f"  RESULT:")
    print(f"    SL (STOP_MARKET):       {'OK' if sl_ok else 'FAILED'}")
    print(f"    TP (TAKE_PROFIT_MARKET): {'OK' if tp_ok else 'FAILED'}")
    if sl_ok and tp_ok:
        print("\n  Bracket Order via Algo API: FULLY WORKING!")
        print("  NT 1.222.0 should handle this correctly internally.")
    elif sl_ok or tp_ok:
        print("\n  PARTIAL: One order type works, need to investigate the other")
    else:
        print("\n  BOTH FAILED: Need to check NT internal routing")
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
