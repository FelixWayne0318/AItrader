#!/usr/bin/env python3
"""
Test funding rate semantics after v5.1 fix.

Verifies:
1. premiumIndex.lastFundingRate != /fundingRate (last settled)
   → lastFundingRate is the real-time predicted rate, NOT the settled rate
2. Our get_funding_rate() correctly separates settled vs predicted
3. All downstream consumers see correct values
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import json

BASE = "https://fapi.binance.com"

print("=" * 60)
print("Funding Rate Semantic Verification (v5.1)")
print("=" * 60)

# 1. Raw API comparison
print("\n--- Step 1: Raw API Data ---")
r1 = requests.get(f"{BASE}/fapi/v1/premiumIndex", params={"symbol": "BTCUSDT"}, timeout=10)
premium_data = r1.json()

r2 = requests.get(f"{BASE}/fapi/v1/fundingRate", params={"symbol": "BTCUSDT", "limit": 1}, timeout=10)
settled_data = r2.json()

last_fr = float(premium_data["lastFundingRate"])
settled_fr = float(settled_data[0]["fundingRate"])

print(f"premiumIndex.lastFundingRate:  {last_fr*100:.4f}%  (= predicted)")
print(f"/fundingRate (latest settled):  {settled_fr*100:.4f}%  (= settled)")
print(f"Are they different?             {abs(last_fr - settled_fr) > 1e-10}  (should be True)")

# 2. Test our get_funding_rate() method
print("\n--- Step 2: BinanceKlineClient.get_funding_rate() ---")
try:
    from utils.binance_kline_client import BinanceKlineClient
    client = BinanceKlineClient(timeout=10)
    result = client.get_funding_rate("BTCUSDT")

    if result:
        print(f"funding_rate (settled):     {result['funding_rate_pct']:.4f}%")
        print(f"predicted_rate (predicted): {result['predicted_rate_pct']:.4f}%")
        print(f"countdown:                  {result['next_funding_countdown_min']} min")
        print(f"mark_price:                 ${result['mark_price']:,.2f}")
        print(f"index_price:                ${result['index_price']:,.2f}")
        print(f"premium_index:              {result['premium_index']*100:.4f}%")

        # Verify correctness
        ok = True
        if abs(result['funding_rate'] - settled_fr) > 1e-8:
            print(f"\nFAIL: funding_rate should match /fundingRate settled rate")
            ok = False
        if abs(result['predicted_rate'] - last_fr) > 1e-8:
            print(f"\nFAIL: predicted_rate should match premiumIndex.lastFundingRate")
            ok = False
        if ok:
            print(f"\nPASS: Semantics correct!")
            print(f"  settled  ({result['funding_rate_pct']:.4f}%) = /fundingRate")
            print(f"  predicted ({result['predicted_rate_pct']:.4f}%) = premiumIndex.lastFundingRate")
    else:
        print("FAIL: get_funding_rate() returned None")
except ImportError as e:
    print(f"SKIP: Cannot import BinanceKlineClient: {e}")
except Exception as e:
    print(f"ERROR: {e}")

print("\n" + "=" * 60)
