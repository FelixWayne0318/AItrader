#!/usr/bin/env python3
"""
Coinalyze API 验证脚本
用于验证 API 响应格式，确认与方案设计是否一致

使用方法:
    python3 scripts/test_coinalyze_api.py

或指定 API Key:
    COINALYZE_API_KEY=xxx python3 scripts/test_coinalyze_api.py
"""

import os
import sys
import json
import time

try:
    import requests
except ImportError:
    print("请先安装 requests: pip install requests")
    sys.exit(1)


# API 配置
API_KEY = os.getenv('COINALYZE_API_KEY', '8be2c53d-480f-4347-b7cf-d9f2b06576fa')
BASE_URL = 'https://api.coinalyze.net/v1'
SYMBOL = 'BTCUSDT_PERP.A'  # Binance BTCUSDT 永续合约


def make_request(endpoint: str, params: dict = None) -> dict:
    """发送 API 请求"""
    headers = {'api_key': API_KEY}
    url = f'{BASE_URL}/{endpoint}'

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        return {
            'status_code': resp.status_code,
            'data': resp.json() if resp.status_code == 200 else resp.text,
            'headers': dict(resp.headers)
        }
    except Exception as e:
        return {'error': str(e)}


def test_exchanges():
    """测试交易所列表端点"""
    print("=" * 60)
    print("1. 测试 /exchanges 端点")
    print("=" * 60)

    result = make_request('exchanges')

    if 'error' in result:
        print(f"❌ 错误: {result['error']}")
        return

    print(f"HTTP Status: {result['status_code']}")

    if result['status_code'] == 200:
        data = result['data']
        print(f"✅ 成功! 共 {len(data)} 个交易所")
        print("\n交易所代码示例:")
        for ex in data[:5]:
            print(f"  - {ex}")

        # 查找 Binance
        binance = [e for e in data if 'binance' in str(e).lower() or e.get('code') == 'A']
        if binance:
            print(f"\n🔍 Binance 交易所: {binance[0]}")
    else:
        print(f"❌ 失败: {result['data']}")


def test_open_interest():
    """测试 Open Interest 端点"""
    print("\n" + "=" * 60)
    print("2. 测试 /open-interest 端点")
    print("=" * 60)

    result = make_request('open-interest', {'symbols': SYMBOL})

    if 'error' in result:
        print(f"❌ 错误: {result['error']}")
        return

    print(f"HTTP Status: {result['status_code']}")
    print(f"Symbol: {SYMBOL}")

    if result['status_code'] == 200:
        data = result['data']
        print(f"✅ 成功!")
        print("\n完整响应:")
        print(json.dumps(data, indent=2))

        if data:
            item = data[0] if isinstance(data, list) else data
            print("\n📊 字段分析:")
            for key, value in item.items():
                print(f"  {key}: {value} ({type(value).__name__})")
    else:
        print(f"❌ 失败: {result['data']}")


def test_funding_rate():
    """测试 Funding Rate 端点"""
    print("\n" + "=" * 60)
    print("3. 测试 /funding-rate 端点")
    print("=" * 60)

    result = make_request('funding-rate', {'symbols': SYMBOL})

    if 'error' in result:
        print(f"❌ 错误: {result['error']}")
        return

    print(f"HTTP Status: {result['status_code']}")
    print(f"Symbol: {SYMBOL}")

    if result['status_code'] == 200:
        data = result['data']
        print(f"✅ 成功!")
        print("\n完整响应:")
        print(json.dumps(data, indent=2))

        if data:
            item = data[0] if isinstance(data, list) else data
            print("\n📊 字段分析:")
            for key, value in item.items():
                print(f"  {key}: {value} ({type(value).__name__})")
    else:
        print(f"❌ 失败: {result['data']}")


def test_liquidation_history():
    """测试 Liquidation History 端点"""
    print("\n" + "=" * 60)
    print("4. 测试 /liquidation-history 端点")
    print("=" * 60)

    # 最近 1 小时
    end_time = int(time.time() * 1000)
    start_time = end_time - 3600000

    result = make_request('liquidation-history', {
        'symbols': SYMBOL,
        'interval': '1hour',  # ⚠️ 必须是 "1hour" 不是 "1h"
        'from': start_time,
        'to': end_time
    })

    if 'error' in result:
        print(f"❌ 错误: {result['error']}")
        return

    print(f"HTTP Status: {result['status_code']}")
    print(f"Symbol: {SYMBOL}")
    print(f"Time Range: {start_time} - {end_time}")

    if result['status_code'] == 200:
        data = result['data']
        print(f"✅ 成功!")
        print("\n完整响应:")
        print(json.dumps(data, indent=2))

        if data:
            item = data[-1] if isinstance(data, list) else data
            print("\n📊 最新一条字段分析:")
            for key, value in item.items():
                print(f"  {key}: {value} ({type(value).__name__})")
    else:
        print(f"❌ 失败: {result['data']}")


def test_oi_history():
    """测试 OI History 端点 (用于计算变化率)"""
    print("\n" + "=" * 60)
    print("5. 测试 /open-interest-history 端点")
    print("=" * 60)

    # 最近 24 小时
    end_time = int(time.time() * 1000)
    start_time = end_time - 86400000  # 24h

    result = make_request('open-interest-history', {
        'symbols': SYMBOL,
        'interval': '1h',
        'from': start_time,
        'to': end_time
    })

    if 'error' in result:
        print(f"❌ 错误: {result['error']}")
        return

    print(f"HTTP Status: {result['status_code']}")

    if result['status_code'] == 200:
        data = result['data']
        print(f"✅ 成功! 共 {len(data) if isinstance(data, list) else 1} 条记录")

        if data and isinstance(data, list) and len(data) > 0:
            print("\n最新一条:")
            print(json.dumps(data[-1], indent=2))

            print("\n最旧一条 (24h前):")
            print(json.dumps(data[0], indent=2))

            # 计算变化率
            if len(data) >= 2:
                old_oi = data[0].get('o', data[0].get('openInterestUsd', 0))
                new_oi = data[-1].get('o', data[-1].get('openInterestUsd', 0))
                if old_oi > 0:
                    change_pct = (new_oi - old_oi) / old_oi * 100
                    print(f"\n📈 24h OI 变化: {change_pct:.2f}%")
    else:
        print(f"❌ 失败: {result['data']}")


def main():
    print("=" * 60)
    print("🔍 Coinalyze API 验证脚本")
    print("=" * 60)
    print(f"API Key: {API_KEY[:8]}...{API_KEY[-4:]}")
    print(f"Base URL: {BASE_URL}")
    print(f"Symbol: {SYMBOL}")
    print()

    test_exchanges()
    test_open_interest()
    test_funding_rate()
    test_liquidation_history()
    test_oi_history()

    print("\n" + "=" * 60)
    print("📋 格式对照表 (方案 vs 实际)")
    print("=" * 60)
    print("""
方案期望格式                    | 实际 API 字段 (待确认)
-------------------------------|------------------------
open_interest.total_usd        | openInterestUsd 或 o
open_interest.change_24h_pct   | (需从 history 计算)
funding_rate.current           | fundingRate 或 r
funding_rate.predicted         | predictedFundingRate
liquidations_1h.long_usd       | l 或 longLiquidationUsd
liquidations_1h.short_usd      | s 或 shortLiquidationUsd
""")


if __name__ == '__main__':
    main()
