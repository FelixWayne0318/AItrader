#!/usr/bin/env python3
"""
Redis OCO Group Monitor for DeepSeek Trading Strategy

Monitors Redis in real-time to show OCO order groups and activity.
"""

import redis
import time
import sys
from datetime import datetime

def main():
    """Monitor Redis OCO groups in real-time."""

    # Connect to Redis
    try:
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        r.ping()
        print("✅ Connected to Redis on 127.0.0.1:6379")
    except Exception as e:
        print(f"❌ Failed to connect to Redis: {e}")
        sys.exit(1)

    print("=" * 70)
    print("🔴 Redis OCO Group Monitor - Press Ctrl+C to stop")
    print("=" * 70)
    print()

    last_key_count = 0

    try:
        while True:
            # Get all OCO groups
            keys = r.keys('nautilus:oco:*')
            key_count = len(keys)

            # Clear screen (optional)
            # print("\033[2J\033[H", end='')

            # Header
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"\r[{timestamp}] OCO Groups: {key_count}", end='')

            # Show details if there are keys
            if keys:
                print()  # New line
                print("-" * 70)

                for key in sorted(keys):
                    # Get all hash fields
                    data = r.hgetall(key)
                    ttl = r.ttl(key)

                    # Display group info
                    group_id = key.split(':')[-1]
                    print(f"\n📦 Group: {group_id}")
                    print(f"   Side: {data.get('side', 'N/A')}")
                    print(f"   Status: {data.get('status', 'N/A')}")
                    print(f"   SL Order: {data.get('sl_order', 'N/A')}")

                    # Parse TP orders (stored as JSON string or multiple fields)
                    tp_orders = data.get('tp_orders', '[]')
                    print(f"   TP Orders: {tp_orders}")

                    print(f"   TTL: {ttl}s ({ttl//3600}h {(ttl%3600)//60}m)")

                print("-" * 70)

            # Alert on new groups
            if key_count > last_key_count:
                print(f"\n🔔 NEW: {key_count - last_key_count} OCO group(s) created!")
            elif key_count < last_key_count:
                print(f"\n🗑️  REMOVED: {last_key_count - key_count} OCO group(s) deleted!")

            last_key_count = key_count

            # Refresh interval
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n\n✅ Monitoring stopped.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
