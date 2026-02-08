#!/usr/bin/env python3
"""
Bracket Order 深层诊断 v5
不再测试 API 参数 — 直接分析 NT 内部的订单路由链：
1. _submit_order_list 是否拦截含 STOP_MARKET 的 linked orders?
2. _submit_order 如何 dispatch 不同 order type?
3. 单独提交 SL/TP (非 bracket) 是否可行?
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


def dump_method(cls, method_name, max_lines=80):
    """从类或其父类中找到并打印方法源码"""
    for klass in cls.__mro__:
        if klass.__name__ == "object":
            continue
        try:
            src = inspect.getsource(klass)
            lines = src.split("\n")
            in_method = False
            method_indent = 0
            method_lines = []
            for i, line in enumerate(lines):
                if method_name in line and ("def " in line or "async def " in line):
                    in_method = True
                    method_indent = len(line) - len(line.lstrip())
                    method_lines = [f"  [{klass.__name__}]"]
                    method_lines.append(f"    L{i}: {line.rstrip()}")
                    continue
                if in_method:
                    if line.strip() == "" or line.strip().startswith("#") or line.strip().startswith('"""') or line.strip().startswith("'"):
                        method_lines.append(f"    L{i}: {line.rstrip()}")
                    else:
                        curr_indent = len(line) - len(line.lstrip()) if line.strip() else 999
                        if curr_indent <= method_indent and line.strip():
                            break
                        method_lines.append(f"    L{i}: {line.rstrip()}")
                    if len(method_lines) > max_lines:
                        method_lines.append(f"    ... (truncated at {max_lines} lines)")
                        break
            if method_lines:
                for ml in method_lines:
                    print(ml)
                return True
        except (TypeError, OSError):
            continue
    print(f"  NOT FOUND in any parent class")
    return False


def main():
    print("=" * 70)
    print("  Bracket Order Deep Diagnosis v5 - NT Internal Routing")
    print("=" * 70)

    qty = "0.002"

    # ================================================================
    # PART 1: NT 内部订单路由链分析
    # ================================================================
    print("\n" + "=" * 70)
    print("  PART 1: NT Internal Order Routing Chain")
    print("=" * 70)

    try:
        from nautilus_trader.adapters.binance.futures.execution import BinanceFuturesExecutionClient

        # 1a. _submit_order_list - 这是 bracket 的入口
        print("\n[1a] _submit_order_list (bracket 入口):")
        dump_method(BinanceFuturesExecutionClient, "_submit_order_list")

        # 1b. _submit_order - 单个订单 dispatch
        print("\n[1b] _submit_order (单订单 dispatch):")
        dump_method(BinanceFuturesExecutionClient, "_submit_order", max_lines=100)

        # 1c. _submit_stop_market_order - SL 路由
        print("\n[1c] _submit_stop_market_order (SL 路由到 algo?):")
        dump_method(BinanceFuturesExecutionClient, "_submit_stop_market_order")

        # 1d. _submit_take_profit_market_order - TP 路由
        print("\n[1d] _submit_take_profit_market_order (TP 路由到 algo?):")
        dump_method(BinanceFuturesExecutionClient, "_submit_take_profit_market_order")

        # 1e. _submit_limit_order - bracket 的 TP 是 LIMIT
        print("\n[1e] _submit_limit_order (bracket TP 通常是 LIMIT):")
        dump_method(BinanceFuturesExecutionClient, "_submit_limit_order")

        # 1f. new_algo_order - 实际调用 algo endpoint
        print("\n[1f] new_algo_order (实际调用 /fapi/v1/algoOrder):")
        dump_method(BinanceFuturesExecutionClient, "new_algo_order")

        # 1g. 搜索 "UNSUPPORTED_OCO" 或 "deny" 关键字
        print("\n[1g] Search for order denial / OCO rejection logic:")
        for klass in BinanceFuturesExecutionClient.__mro__:
            if klass.__name__ == "object":
                continue
            try:
                src = inspect.getsource(klass)
                for i, line in enumerate(src.split("\n")):
                    low = line.lower()
                    if any(k in low for k in ["unsupported", "deny", "reject", "_deny_order"]):
                        if "def " in line or "deny" in low or "unsupported" in low:
                            print(f"    [{klass.__name__} L{i}]: {line.strip()[:120]}")
            except (TypeError, OSError):
                continue

        # 1h. 检查 linked_order_ids 处理
        print("\n[1h] Search for linked_order_ids handling:")
        for klass in BinanceFuturesExecutionClient.__mro__:
            if klass.__name__ == "object":
                continue
            try:
                src = inspect.getsource(klass)
                for i, line in enumerate(src.split("\n")):
                    if "linked_order" in line.lower():
                        print(f"    [{klass.__name__} L{i}]: {line.strip()[:120]}")
            except (TypeError, OSError):
                continue

    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()

    # ================================================================
    # PART 2: 验证 Algo API (正确参数)
    # ================================================================
    print("\n\n" + "=" * 70)
    print("  PART 2: Direct Algo API Test (algoType=CONDITIONAL + triggerPrice)")
    print("=" * 70)

    r = requests.get(f"{BASE}/fapi/v1/ticker/price",
                     params={"symbol": "BTCUSDT"}, timeout=5)
    price = float(r.json()["price"])
    print(f"\n  Price: ${price:,.2f}")

    r = api_get("/fapi/v2/positionRisk", {"symbol": "BTCUSDT"})
    has_pos = any(float(p.get("positionAmt", 0)) != 0 for p in r.json())
    if has_pos:
        print("  HAS POSITION - aborting Part 2")
        return
    print("  No position")

    sl_price = str(round(price * 0.98, 2))
    tp_price = str(round(price * 1.03, 2))

    # Entry
    print(f"\n  [Entry] MARKET BUY {qty} BTC")
    r1 = api_post("/fapi/v1/order", {
        "symbol": "BTCUSDT", "side": "BUY",
        "type": "MARKET", "quantity": qty,
    })
    if r1.status_code != 200:
        print(f"  XX Entry failed: {r1.json().get('msg','')}")
        return
    print(f"  OK Entry: orderId={r1.json()['orderId']}")

    # SL via Algo
    print(f"\n  [SL] STOP_MARKET via algoOrder (triggerPrice={sl_price})")
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
        print(f"  OK SL: {r_sl.json()}")
    else:
        print(f"  XX SL: {r_sl.json()}")

    # TP via Algo
    print(f"\n  [TP] TAKE_PROFIT_MARKET via algoOrder (triggerPrice={tp_price})")
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
        print(f"  OK TP: {r_tp.json()}")
    else:
        print(f"  XX TP: {r_tp.json()}")

    # TP via regular LIMIT (this is what bracket() actually creates)
    print(f"\n  [TP-alt] LIMIT via regular /fapi/v1/order")
    r_tp2 = api_post("/fapi/v1/order", {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "LIMIT",
        "price": tp_price,
        "quantity": qty,
        "reduceOnly": "true",
        "timeInForce": "GTC",
    })
    if r_tp2.status_code == 200:
        print(f"  OK TP-LIMIT: orderId={r_tp2.json()['orderId']}")
    else:
        print(f"  XX TP-LIMIT: {r_tp2.json()}")

    # Check all open orders
    print(f"\n  [Check] Open orders:")
    r_regular = api_get("/fapi/v1/openOrders", {"symbol": "BTCUSDT"})
    r_algo = api_get("/fapi/v1/openAlgoOrders")
    if r_regular.status_code == 200:
        reg_orders = r_regular.json()
        print(f"    Regular orders: {len(reg_orders)}")
        for o in reg_orders:
            print(f"      {o.get('type')} {o.get('side')} qty={o.get('origQty')} price={o.get('price')} stop={o.get('stopPrice')}")
    if r_algo.status_code == 200:
        algo_orders = r_algo.json()
        if isinstance(algo_orders, list):
            print(f"    Algo orders: {len(algo_orders)}")
            for o in algo_orders:
                print(f"      {o.get('orderType')} {o.get('side')} qty={o.get('quantity')} trigger={o.get('triggerPrice')}")

    # Cleanup
    print(f"\n  --- Cleanup ---")
    cleanup(qty)

    # ================================================================
    # SUMMARY
    # ================================================================
    sl_ok = r_sl.status_code == 200
    tp_ok = r_tp.status_code == 200
    tp2_ok = r_tp2.status_code == 200

    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Algo SL  (STOP_MARKET):        {'OK' if sl_ok else 'FAILED'}")
    print(f"  Algo TP  (TAKE_PROFIT_MARKET): {'OK' if tp_ok else 'FAILED'}")
    print(f"  Regular TP (LIMIT):            {'OK' if tp2_ok else 'FAILED'}")
    print()
    if sl_ok:
        print("  Algo API WORKS with correct params!")
        print("  If NT bracket orders still fail, the issue is in NT's")
        print("  _submit_order_list() not routing to algo endpoint.")
        print()
        print("  FIX: Stop using bracket orders. Submit individually:")
        print("    1. MARKET entry → on_order_filled()")
        print("    2. → STOP_MARKET SL (will route to algo)")
        print("    3. → LIMIT TP (regular endpoint)")
        print("    4. Manual OCO: cancel peer when one fills")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nXX Fatal: {e}")
        import traceback
        traceback.print_exc()
        print("\nEmergency cleanup...")
        cleanup("0.002")
