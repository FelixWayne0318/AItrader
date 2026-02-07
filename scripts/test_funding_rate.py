#!/usr/bin/env python3
"""Test funding rate: compare premiumIndex vs fundingRate endpoint"""
import requests, json, time

BASE = "https://fapi.binance.com"

r = requests.get(f"{BASE}/fapi/v1/premiumIndex", params={"symbol": "BTCUSDT"}, timeout=10)
data = r.json()
print("=== /fapi/v1/premiumIndex ===")
print(json.dumps(data, indent=2))

r2 = requests.get(f"{BASE}/fapi/v1/fundingRate", params={"symbol": "BTCUSDT", "limit": 1}, timeout=10)
history = r2.json()
print("\n=== /fapi/v1/fundingRate (last 1) ===")
print(json.dumps(history, indent=2))

mark = float(data["markPrice"])
index = float(data["indexPrice"])
interest = float(data["interestRate"])
last_rate = float(data["lastFundingRate"])
settled_rate = float(history[0]["fundingRate"])

premium = (mark - index) / index
damper = 0.0005
clamped = max(-damper, min(damper, interest - premium))
estimated = premium + clamped

print("\n=== Compare ===")
print(f"premiumIndex.lastFundingRate:  {last_rate*100:.4f}%")
print(f"fundingRate (settled):         {settled_rate*100:.4f}%")
print(f"Same value:                    {abs(last_rate - settled_rate) < 1e-10}")
print(f"")
print(f"Instant premium:               {premium*100:.4f}%")
print(f"Estimated predicted rate:      {estimated*100:.4f}%")
