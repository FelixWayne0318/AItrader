#!/usr/bin/env python3
"""
Coinalyze API 诊断脚本

功能:
1. 显示 API 返回的原始数据
2. 分析哪些字段被使用
3. 识别未利用的数据

用法:
    cd /home/linuxuser/nautilus_AItrader
    source venv/bin/activate
    python3 scripts/diagnose_coinalyze.py
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# 加载环境变量
env_file = Path.home() / ".env.aitrader"
if env_file.exists():
    load_dotenv(env_file)
else:
    load_dotenv(project_root / ".env")


def print_header(title: str):
    """打印标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_json(data, indent=2):
    """格式化打印 JSON"""
    print(json.dumps(data, indent=indent, ensure_ascii=False, default=str))


def fetch_raw_api(endpoint: str, params: dict, api_key: str) -> dict:
    """直接调用 Coinalyze API 获取原始响应"""
    url = f"https://api.coinalyze.net/v1{endpoint}"
    headers = {"api_key": api_key} if api_key else {}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "data": response.json() if response.status_code == 200 else response.text,
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    print_header("Coinalyze API 诊断工具")

    api_key = os.getenv("COINALYZE_API_KEY")
    symbol = "BTCUSDT_PERP.A"

    # Dynamic base currency from symbol (e.g. "BTCUSDT_PERP.A" -> "BTC")
    _sym_clean = symbol.split('_')[0] if '_' in symbol else symbol
    base_currency = _sym_clean.replace('USDT', '') if 'USDT' in _sym_clean else _sym_clean.split('-')[0] if '-' in _sym_clean else 'BTC'

    # 检查 API Key
    print("\n📋 配置检查:")
    if api_key:
        print(f"  ✅ COINALYZE_API_KEY: {api_key[:8]}...{api_key[-4:]}")
    else:
        print("  ❌ COINALYZE_API_KEY 未设置!")
        print("  💡 请在 ~/.env.aitrader 中添加: COINALYZE_API_KEY=your_key")
        print("  💡 获取地址: https://coinalyze.net/")
        return

    print(f"  📊 测试交易对: {symbol}")

    # =========================================================================
    # 1. Open Interest API
    # =========================================================================
    print_header("1. Open Interest (持仓量)")

    oi_response = fetch_raw_api(
        "/open-interest",
        {"symbols": symbol},
        api_key
    )

    print("\n🔹 原始 API 响应:")
    print_json(oi_response)

    if oi_response.get("status_code") == 200 and oi_response.get("data"):
        oi_data = oi_response["data"][0] if oi_response["data"] else {}
        print("\n📊 数据字段分析:")
        print(f"  {'字段':<15} {'值':<25} {'是否使用':<10} {'说明'}")
        print("-" * 70)

        fields = [
            ("symbol", oi_data.get("symbol"), "✅ 是", "交易对标识"),
            ("value", oi_data.get("value"), "✅ 是", f"OI 数量 ({base_currency})"),
            ("update", oi_data.get("update"), "❌ 否", "更新时间戳 (ms)"),
        ]
        for name, value, used, desc in fields:
            print(f"  {name:<15} {str(value):<25} {used:<10} {desc}")

        # 检查是否有其他未知字段
        known_fields = {"symbol", "value", "update"}
        unknown = set(oi_data.keys()) - known_fields
        if unknown:
            print(f"\n  ⚠️ 发现未知字段: {unknown}")

    # =========================================================================
    # 2. Funding Rate API
    # =========================================================================
    print_header("2. Funding Rate (资金费率)")

    fr_response = fetch_raw_api(
        "/funding-rate",
        {"symbols": symbol},
        api_key
    )

    print("\n🔹 原始 API 响应:")
    print_json(fr_response)

    if fr_response.get("status_code") == 200 and fr_response.get("data"):
        fr_data = fr_response["data"][0] if fr_response["data"] else {}
        print("\n📊 数据字段分析:")
        print(f"  {'字段':<15} {'值':<25} {'是否使用':<10} {'说明'}")
        print("-" * 70)

        fields = [
            ("symbol", fr_data.get("symbol"), "✅ 是", "交易对标识"),
            ("value", fr_data.get("value"), "✅ 是", "资金费率 (小数)"),
            ("update", fr_data.get("update"), "❌ 否", "更新时间戳 (ms)"),
        ]
        for name, value, used, desc in fields:
            print(f"  {name:<15} {str(value):<25} {used:<10} {desc}")

        # 检查未知字段
        known_fields = {"symbol", "value", "update"}
        unknown = set(fr_data.keys()) - known_fields
        if unknown:
            print(f"\n  ⚠️ 发现未知字段: {unknown}")

    # =========================================================================
    # 3. Liquidation History API
    # =========================================================================
    print_header("3. Liquidation History (爆仓数据)")

    now = int(time.time())
    liq_response = fetch_raw_api(
        "/liquidation-history",
        {
            "symbols": symbol,
            "interval": "1hour",
            "from": now - 3600,  # 过去1小时
            "to": now,
        },
        api_key
    )

    print("\n🔹 原始 API 响应:")
    print_json(liq_response)

    if liq_response.get("status_code") == 200 and liq_response.get("data"):
        liq_data = liq_response["data"][0] if liq_response["data"] else {}
        print("\n📊 数据字段分析:")
        print(f"  {'字段':<15} {'值':<40} {'是否使用':<10} {'说明'}")
        print("-" * 85)

        fields = [
            ("symbol", liq_data.get("symbol"), "✅ 是", "交易对标识"),
            ("history", f"[{len(liq_data.get('history', []))} 条记录]", "✅ 是", "历史数据数组"),
        ]
        for name, value, used, desc in fields:
            print(f"  {name:<15} {str(value):<40} {used:<10} {desc}")

        # 分析 history 数组中的字段
        history = liq_data.get("history", [])
        if history:
            print("\n  📈 history 数组字段:")
            print(f"    {'字段':<10} {'示例值':<25} {'是否使用':<10} {'说明'}")
            print("    " + "-" * 60)

            sample = history[0]
            history_fields = [
                ("t", sample.get("t"), "❌ 否", "时间戳 (秒)"),
                ("l", sample.get("l"), "✅ 是", f"多头爆仓 ({base_currency})"),
                ("s", sample.get("s"), "✅ 是", f"空头爆仓 ({base_currency})"),
            ]
            for name, value, used, desc in history_fields:
                print(f"    {name:<10} {str(value):<25} {used:<10} {desc}")

            # 检查未知字段
            known_fields = {"t", "l", "s"}
            unknown = set(sample.keys()) - known_fields
            if unknown:
                print(f"\n    ⚠️ 发现未知字段: {unknown}")

        # 检查顶层未知字段
        known_fields = {"symbol", "history"}
        unknown = set(liq_data.keys()) - known_fields
        if unknown:
            print(f"\n  ⚠️ 发现未知字段: {unknown}")

    # =========================================================================
    # 4. 其他可用 API 端点 (未使用)
    # =========================================================================
    print_header("4. 其他可用 API 端点 (当前未使用)")

    other_endpoints = [
        ("/open-interest-history", "OI 历史数据", {"symbols": symbol, "interval": "1hour", "from": now-3600, "to": now}),
        ("/funding-rate-history", "资金费率历史", {"symbols": symbol, "interval": "1hour", "from": now-3600, "to": now}),
        ("/long-short-ratio", "多空持仓比", {"symbols": symbol, "interval": "1hour", "from": now-3600, "to": now}),
        ("/long-short-ratio-history", "多空比历史", {"symbols": symbol, "interval": "1hour", "from": now-3600, "to": now}),
    ]

    for endpoint, desc, params in other_endpoints:
        print(f"\n🔸 {desc} ({endpoint})")
        response = fetch_raw_api(endpoint, params, api_key)

        if response.get("status_code") == 200:
            print("  ✅ 可用")
            data = response.get("data", [])
            if data:
                # 只显示第一条数据的结构
                sample = data[0] if isinstance(data, list) else data
                print(f"  📋 数据结构: {list(sample.keys()) if isinstance(sample, dict) else type(sample)}")
                print(f"  📊 示例数据:")
                print_json(sample)
        else:
            print(f"  ❌ 状态码: {response.get('status_code')}")
            if "error" in response:
                print(f"  错误: {response['error']}")

    # =========================================================================
    # 5. 总结
    # =========================================================================
    print_header("5. 数据利用总结")

    print(f"""
┌─────────────────────────────────────────────────────────────────────────┐
│                        当前已使用的数据                                  │
├─────────────────────────────────────────────────────────────────────────┤
│ API 端点              │ 使用的字段           │ 用途                     │
├───────────────────────┼─────────────────────┼─────────────────────────┤
│ /open-interest        │ value               │ 持仓量 ({base_currency} → USD)       │
│ /funding-rate         │ value               │ 资金费率 (%)             │
│ /liquidation-history  │ history[].l, .s     │ 多空爆仓量 ({base_currency} → USD)   │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                        未利用的数据                                      │
├─────────────────────────────────────────────────────────────────────────┤
│ 字段/API              │ 潜在用途                                        │
├───────────────────────┼────────────────────────────────────────────────┤
│ update (时间戳)        │ 数据新鲜度检测，过时数据标记                    │
│ history[].t (时间戳)   │ 爆仓时序分析，趋势判断                          │
│ /open-interest-history │ OI 变化趋势，判断资金流向                       │
│ /funding-rate-history  │ 资金费率趋势，预测挤压风险                      │
│ /long-short-ratio      │ 多空持仓比 (另一个数据源，与 Binance 对比)      │
└─────────────────────────────────────────────────────────────────────────┘

💡 改进建议:

1. 【数据新鲜度】使用 update 字段检测数据是否过时 (>5分钟视为陈旧)

2. 【OI 趋势】获取 OI 历史数据，计算变化率:
   - OI 上升 + 价格上升 = 趋势确认 (做多信号强化)
   - OI 上升 + 价格下跌 = 趋势确认 (做空信号强化)
   - OI 下降 = 趋势减弱 (减少仓位)

3. 【资金费率趋势】获取历史数据，判断:
   - 费率持续走高 → 多头过热，警惕回调
   - 费率持续走低 → 空头堆积，警惕轧空

4. 【爆仓时序】分析 history[].t 时间戳:
   - 爆仓集中在某一时刻 → 大行情信号
   - 爆仓均匀分布 → 正常波动
""")

    print("\n✅ 诊断完成!")
    print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
