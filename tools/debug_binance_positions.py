#!/usr/bin/env python3
"""
Debug script to check what positions Binance API returns.
This helps identify why '币安人生USDT-PERP' appears in position data.
"""

import os
import time
import hmac
import hashlib
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
BASE_URL = "https://fapi.binance.com"


def get_signature(params: dict) -> str:
    """Generate HMAC SHA256 signature."""
    query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
    signature = hmac.new(
        API_SECRET.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature


def get_account_info():
    """Get account information including positions."""
    endpoint = "/fapi/v2/account"
    timestamp = int(time.time() * 1000)

    params = {
        "timestamp": timestamp,
        "recvWindow": 5000,
    }
    params["signature"] = get_signature(params)

    headers = {"X-MBX-APIKEY": API_KEY}

    response = requests.get(
        f"{BASE_URL}{endpoint}",
        params=params,
        headers=headers
    )

    return response.json()


def get_position_risk():
    """Get position risk information."""
    endpoint = "/fapi/v2/positionRisk"
    timestamp = int(time.time() * 1000)

    params = {
        "timestamp": timestamp,
        "recvWindow": 5000,
    }
    params["signature"] = get_signature(params)

    headers = {"X-MBX-APIKEY": API_KEY}

    response = requests.get(
        f"{BASE_URL}{endpoint}",
        params=params,
        headers=headers
    )

    return response.json()


def main():
    print("=" * 70)
    print("Binance Futures Position Debug")
    print("=" * 70)

    # Check position risk endpoint
    print("\n📊 Checking /fapi/v2/positionRisk...")
    positions = get_position_risk()

    if isinstance(positions, list):
        print(f"Total positions returned: {len(positions)}")

        # Find non-ASCII symbols
        non_ascii_symbols = []
        for pos in positions:
            symbol = pos.get('symbol', '')
            # Check if symbol contains non-ASCII characters
            if not symbol.isascii():
                non_ascii_symbols.append(pos)
                print(f"\n⚠️  Non-ASCII Symbol Found:")
                print(f"   Symbol: {symbol}")
                print(f"   Position Amount: {pos.get('positionAmt', 'N/A')}")
                print(f"   Entry Price: {pos.get('entryPrice', 'N/A')}")
                print(f"   Unrealized PnL: {pos.get('unRealizedProfit', 'N/A')}")

        if not non_ascii_symbols:
            print("✅ No non-ASCII symbols found in positions")
        else:
            print(f"\n❌ Found {len(non_ascii_symbols)} non-ASCII symbol(s)")

        # Also show any symbols containing Chinese characters
        print("\n📋 Looking for '币安' in symbol names...")
        for pos in positions:
            symbol = pos.get('symbol', '')
            if '币安' in symbol or '人生' in symbol:
                print(f"   Found: {symbol}")
    else:
        print(f"Error response: {positions}")

    # Check account endpoint
    print("\n" + "=" * 70)
    print("📊 Checking /fapi/v2/account positions...")
    account = get_account_info()

    if 'positions' in account:
        positions = account['positions']
        print(f"Total positions in account: {len(positions)}")

        for pos in positions:
            symbol = pos.get('symbol', '')
            if not symbol.isascii() or '币安' in symbol:
                print(f"\n⚠️  Non-ASCII/Chinese Symbol in account:")
                print(f"   Symbol: {symbol}")
                print(f"   Position Amount: {pos.get('positionAmt', 'N/A')}")
    else:
        print(f"Error or no positions: {account.get('msg', account)}")

    print("\n" + "=" * 70)
    print("Debug complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
