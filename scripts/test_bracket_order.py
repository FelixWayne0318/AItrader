#!/usr/bin/env python3
"""
实盘订单流测试 v6 — 完整生命周期
1. 开空 0.002 BTC
2. SL (+1%) via algoOrder + TP (-1%) via regular order
3. 等10秒
4. 修改 SL/TP 为 2%
5. 再等10秒后平仓清理
"""
import os, time, hmac, hashlib, math, requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.env.aitrader"))

API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")
BASE = "https://fapi.binance.com"
QTY = "0.002"
TICK = 0.10  # BTCUSDT tick size


def sign(params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    sig = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    return query + "&signature=" + sig


def api(method, path, params):
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 5000
    url = f"{BASE}{path}?{sign(params)}"
    headers = {"X-MBX-APIKEY": API_KEY}
    if method == "POST":
        return requests.post(url, headers=headers, timeout=10)
    elif method == "DELETE":
        return requests.delete(url, headers=headers, timeout=10)
    else:
        return requests.get(url, headers=headers, timeout=10)


def tick_round(price):
    """Round to BTCUSDT tick size (0.10)"""
    return round(math.floor(price / TICK) * TICK, 1)


def tick_ceil(price):
    """Ceil to BTCUSDT tick size (0.10)"""
    return round(math.ceil(price / TICK) * TICK, 1)


def show(label, r):
    if r.status_code == 200:
        d = r.json()
        oid = d.get("orderId") or d.get("algoId") or "OK"
        print(f"  OK {label}: id={oid}")
        return d
    else:
        d = r.json()
        print(f"  XX {label}: {d.get('code')} {d.get('msg','')[:80]}")
        return None


def main():
    print("=" * 60)
    print("  Live Order Flow Test v6")
    print("  SHORT 0.002 BTC → SL/TP 1% → modify 2% → cleanup")
    print("=" * 60)

    # Check no existing position
    r = api("GET", "/fapi/v2/positionRisk", {"symbol": "BTCUSDT"})
    if any(float(p.get("positionAmt", 0)) != 0 for p in r.json()):
        print("\n  XX Has existing position - aborting")
        return

    # Get price
    r = requests.get(f"{BASE}/fapi/v1/ticker/price", params={"symbol": "BTCUSDT"}, timeout=5)
    price = float(r.json()["price"])
    print(f"\n  Price: ${price:,.2f}")

    # ============================================================
    # STEP 1: Entry (SHORT = SELL)
    # ============================================================
    print(f"\n[Step 1] MARKET SELL {QTY} BTC (开空)")
    r = api("POST", "/fapi/v1/order", {
        "symbol": "BTCUSDT", "side": "SELL",
        "type": "MARKET", "quantity": QTY,
    })
    entry = show("Entry", r)
    if not entry:
        return
    time.sleep(1)

    # Get actual fill price
    r = api("GET", "/fapi/v2/positionRisk", {"symbol": "BTCUSDT"})
    pos = [p for p in r.json() if float(p.get("positionAmt", 0)) != 0]
    if pos:
        fill_price = float(pos[0]["entryPrice"])
        print(f"  Fill price: ${fill_price:,.2f}")
    else:
        fill_price = price
        print(f"  Using market price: ${fill_price:,.2f}")

    # ============================================================
    # STEP 2: SL (+1%) + TP (-1%)
    # ============================================================
    sl1 = tick_ceil(fill_price * 1.01)  # SL above for short
    tp1 = tick_round(fill_price * 0.99)  # TP below for short

    print(f"\n[Step 2] Set SL/TP at 1%")
    print(f"  SL: ${sl1:,.1f} (+1%, STOP_MARKET via algoOrder)")
    print(f"  TP: ${tp1:,.1f} (-1%, LIMIT via regular order)")

    # SL via Algo Order API
    r_sl = api("POST", "/fapi/v1/algoOrder", {
        "symbol": "BTCUSDT", "side": "BUY",
        "type": "STOP_MARKET",
        "algoType": "CONDITIONAL",
        "triggerPrice": str(sl1),
        "quantity": QTY,
        "reduceOnly": "true",
    })
    sl1_data = show("SL (algoOrder)", r_sl)

    # TP via regular order
    r_tp = api("POST", "/fapi/v1/order", {
        "symbol": "BTCUSDT", "side": "BUY",
        "type": "LIMIT", "price": str(tp1),
        "quantity": QTY, "reduceOnly": "true",
        "timeInForce": "GTC",
    })
    tp1_data = show("TP (LIMIT)", r_tp)

    # Show current orders
    print(f"\n  --- Current orders ---")
    r_reg = api("GET", "/fapi/v1/openOrders", {"symbol": "BTCUSDT"})
    r_algo = api("GET", "/fapi/v1/openAlgoOrders", {})
    if r_reg.status_code == 200:
        for o in r_reg.json():
            print(f"    Regular: {o['type']} {o['side']} price={o.get('price','?')} stop={o.get('stopPrice','?')}")
    if r_algo.status_code == 200:
        orders = r_algo.json()
        if isinstance(orders, list):
            for o in orders:
                print(f"    Algo: {o['orderType']} {o['side']} trigger={o.get('triggerPrice','?')}")

    # ============================================================
    # STEP 3: Wait 10 seconds
    # ============================================================
    print(f"\n[Step 3] Waiting 10 seconds...")
    time.sleep(10)

    # Verify position still exists
    r = api("GET", "/fapi/v2/positionRisk", {"symbol": "BTCUSDT"})
    pos = [p for p in r.json() if float(p.get("positionAmt", 0)) != 0]
    if not pos:
        print("  XX Position gone (SL/TP triggered?) - aborting")
        return
    print(f"  Position still open: {pos[0]['positionAmt']} BTC, PnL: {pos[0].get('unRealizedProfit','?')}")

    # ============================================================
    # STEP 4: Modify SL/TP to 2%
    # ============================================================
    sl2 = tick_ceil(fill_price * 1.02)
    tp2 = tick_round(fill_price * 0.98)

    print(f"\n[Step 4] Modify SL/TP to 2%")
    print(f"  New SL: ${sl1:,.1f} → ${sl2:,.1f}")
    print(f"  New TP: ${tp1:,.1f} → ${tp2:,.1f}")

    # Cancel old SL (algo order)
    if sl1_data and sl1_data.get("algoId"):
        r_cancel_sl = api("DELETE", "/fapi/v1/algoOrder", {
            "algoId": sl1_data["algoId"],
        })
        show("Cancel old SL", r_cancel_sl)

    # Cancel old TP (regular order)
    if tp1_data and tp1_data.get("orderId"):
        r_cancel_tp = api("DELETE", "/fapi/v1/order", {
            "symbol": "BTCUSDT",
            "orderId": tp1_data["orderId"],
        })
        show("Cancel old TP", r_cancel_tp)

    time.sleep(0.5)

    # New SL at 2%
    r_sl2 = api("POST", "/fapi/v1/algoOrder", {
        "symbol": "BTCUSDT", "side": "BUY",
        "type": "STOP_MARKET",
        "algoType": "CONDITIONAL",
        "triggerPrice": str(sl2),
        "quantity": QTY,
        "reduceOnly": "true",
    })
    show("New SL 2% (algoOrder)", r_sl2)

    # New TP at 2%
    r_tp2 = api("POST", "/fapi/v1/order", {
        "symbol": "BTCUSDT", "side": "BUY",
        "type": "LIMIT", "price": str(tp2),
        "quantity": QTY, "reduceOnly": "true",
        "timeInForce": "GTC",
    })
    show("New TP 2% (LIMIT)", r_tp2)

    # Show updated orders
    print(f"\n  --- Updated orders ---")
    r_reg = api("GET", "/fapi/v1/openOrders", {"symbol": "BTCUSDT"})
    r_algo = api("GET", "/fapi/v1/openAlgoOrders", {})
    if r_reg.status_code == 200:
        for o in r_reg.json():
            print(f"    Regular: {o['type']} {o['side']} price={o.get('price','?')} stop={o.get('stopPrice','?')}")
    if r_algo.status_code == 200:
        orders = r_algo.json()
        if isinstance(orders, list):
            for o in orders:
                print(f"    Algo: {o['orderType']} {o['side']} trigger={o.get('triggerPrice','?')}")

    # ============================================================
    # STEP 5: Wait then cleanup
    # ============================================================
    print(f"\n[Step 5] Waiting 10 seconds then cleanup...")
    time.sleep(10)

    # Cancel all orders
    api("DELETE", "/fapi/v1/allOpenOrders", {"symbol": "BTCUSDT"})
    try:
        api("DELETE", "/fapi/v1/algoOpenOrders", {"symbol": "BTCUSDT"})
    except:
        pass
    time.sleep(0.5)

    # Close position
    r_close = api("POST", "/fapi/v1/order", {
        "symbol": "BTCUSDT", "side": "BUY",
        "type": "MARKET", "quantity": QTY, "reduceOnly": "true",
    })
    show("Close position", r_close)

    # ============================================================
    # SUMMARY
    # ============================================================
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    s1 = "OK" if sl1_data else "FAIL"
    t1 = "OK" if tp1_data else "FAIL"
    s2 = "OK" if r_sl2.status_code == 200 else "FAIL"
    t2 = "OK" if r_tp2.status_code == 200 else "FAIL"
    print(f"  Entry (MARKET SELL):     OK")
    print(f"  SL 1% (algoOrder):       {s1}")
    print(f"  TP 1% (LIMIT):           {t1}")
    print(f"  Modify SL → 2%:         {s2}")
    print(f"  Modify TP → 2%:         {t2}")
    if all(x == "OK" for x in [s1, t1, s2, t2]):
        print(f"\n  ALL PASSED - v4.13 order flow works!")
    else:
        print(f"\n  SOME FAILED - check output above")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nXX Fatal: {e}")
        import traceback
        traceback.print_exc()
        print("\nEmergency cleanup...")
        api("DELETE", "/fapi/v1/allOpenOrders", {"symbol": "BTCUSDT"})
        try:
            api("DELETE", "/fapi/v1/algoOpenOrders", {"symbol": "BTCUSDT"})
        except:
            pass
        time.sleep(0.5)
        api("POST", "/fapi/v1/order", {
            "symbol": "BTCUSDT", "side": "BUY",
            "type": "MARKET", "quantity": QTY, "reduceOnly": "true",
        })
        print("  Cleanup done")
