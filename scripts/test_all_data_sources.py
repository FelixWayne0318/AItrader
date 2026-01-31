#!/usr/bin/env python3
"""
测试所有数据源整合

验证:
1. BinanceDerivativesClient - 大户数据、Taker 比
2. CoinalyzeClient - 历史数据 API
3. AIDataAssembler - 完整数据组装
4. 格式化报告输出

用法:
    cd /home/linuxuser/nautilus_AItrader
    source venv/bin/activate

    # 仅显示
    python3 scripts/test_all_data_sources.py

    # 导出到 logs/
    python3 scripts/test_all_data_sources.py --export

    # 导出并推送到 GitHub
    python3 scripts/test_all_data_sources.py --export --push
"""

import os
import sys
import json
import argparse
import subprocess
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

# 输出缓冲
output_lines = []


def log(msg: str = ""):
    """同时打印和记录"""
    print(msg)
    output_lines.append(msg)


def print_header(title: str):
    log("\n" + "=" * 70)
    log(f"  {title}")
    log("=" * 70)


def export_data(complete_data: dict, binance_data: dict, coinalyze_data: dict) -> Path:
    """导出原始数据到 logs/ 目录"""
    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 导出完整数据 (JSON)
    json_file = logs_dir / f"data_sources_{timestamp}.json"
    export_data = {
        "timestamp": datetime.now().isoformat(),
        "binance_derivatives": binance_data,
        "coinalyze": coinalyze_data,
        "complete_assembled": complete_data,
    }

    # 自定义 JSON 序列化器处理特殊类型
    def json_serializer(obj):
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return str(obj)

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False, default=json_serializer)

    # 导出文本报告
    txt_file = logs_dir / f"data_sources_{timestamp}.txt"
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    return json_file, txt_file


def push_to_github(files: list):
    """推送文件到 GitHub"""
    try:
        # 添加文件
        for f in files:
            subprocess.run(["git", "add", str(f)], cwd=project_root, check=True)

        # 提交
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_msg = f"data: Export data sources snapshot {timestamp}"
        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=project_root,
            check=True,
        )

        # 推送
        result = subprocess.run(
            ["git", "push"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            log("✅ 已推送到 GitHub")
        else:
            log(f"⚠️ 推送失败: {result.stderr}")

    except subprocess.CalledProcessError as e:
        log(f"❌ Git 操作失败: {e}")


def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="测试所有数据源整合")
    parser.add_argument("--export", action="store_true", help="导出数据到 logs/ 目录")
    parser.add_argument("--push", action="store_true", help="推送到 GitHub (需要 --export)")
    args = parser.parse_args()

    print_header("数据源整合测试")
    log(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # =========================================================================
    # 1. 测试 BinanceDerivativesClient
    # =========================================================================
    print_header("1. BinanceDerivativesClient 测试")

    from utils.binance_derivatives_client import BinanceDerivativesClient

    binance_deriv = BinanceDerivativesClient()

    log("\n获取所有 Binance 衍生品数据...")
    binance_data = binance_deriv.fetch_all(symbol="BTCUSDT", period="15m", history_limit=10)

    # 显示结果
    for key, value in binance_data.items():
        if key == "_metadata":
            continue
        if isinstance(value, dict):
            latest = value.get("latest")
            trend = value.get("trend", "N/A")
            if latest:
                log(f"\n  ✅ {key}:")
                log(f"     Latest: {latest}")
                log(f"     Trend: {trend}")
            else:
                log(f"\n  ⚠️ {key}: {value}")
        else:
            log(f"\n  ✅ {key}: {value}")

    # 测试格式化输出
    log("\n📄 格式化输出:")
    log(binance_deriv.format_for_ai(binance_data))

    # =========================================================================
    # 2. 测试 CoinalyzeClient (扩展的历史数据)
    # =========================================================================
    print_header("2. CoinalyzeClient 历史数据测试")

    from utils.coinalyze_client import CoinalyzeClient

    coinalyze = CoinalyzeClient()
    coinalyze_data = {}

    if coinalyze.is_enabled():
        log("\n获取所有 Coinalyze 数据 (含历史)...")
        coinalyze_data = coinalyze.fetch_all_with_history(history_hours=4)

        # 显示趋势
        trends = coinalyze_data.get("trends", {})
        log("\n  📊 趋势分析:")
        log(f"     OI 趋势: {trends.get('oi_trend', 'N/A')}")
        log(f"     资金费率趋势: {trends.get('funding_trend', 'N/A')}")
        log(f"     多空比趋势: {trends.get('long_short_trend', 'N/A')}")

        # 显示历史数据条数
        oi_hist = coinalyze_data.get("open_interest_history", {})
        if oi_hist and oi_hist.get("history"):
            log(f"\n  ✅ OI 历史: {len(oi_hist['history'])} 条记录")

        fr_hist = coinalyze_data.get("funding_rate_history", {})
        if fr_hist and fr_hist.get("history"):
            log(f"  ✅ 资金费率历史: {len(fr_hist['history'])} 条记录")

        ls_hist = coinalyze_data.get("long_short_ratio_history", {})
        if ls_hist and ls_hist.get("history"):
            log(f"  ✅ 多空比历史: {len(ls_hist['history'])} 条记录")
            # 显示最新的多空比
            latest = ls_hist["history"][-1]
            log(f"     最新: ratio={latest.get('r')}, long={latest.get('l')}%, short={latest.get('s')}%")

        # 测试格式化输出
        log("\n📄 格式化输出:")
        log(coinalyze.format_for_ai(coinalyze_data, current_price=100000))
    else:
        log("  ❌ COINALYZE_API_KEY 未设置")

    # =========================================================================
    # 3. 测试 AIDataAssembler 完整数据组装
    # =========================================================================
    print_header("3. AIDataAssembler 完整数据组装测试")

    from utils.binance_kline_client import BinanceKlineClient
    from utils.order_flow_processor import OrderFlowProcessor
    from utils.sentiment_client import SentimentDataFetcher
    from utils.ai_data_assembler import AIDataAssembler

    # 初始化所有客户端
    kline_client = BinanceKlineClient()
    order_flow = OrderFlowProcessor()
    sentiment = SentimentDataFetcher()

    # 创建 AIDataAssembler (包含新的 binance_derivatives)
    assembler = AIDataAssembler(
        binance_kline_client=kline_client,
        order_flow_processor=order_flow,
        coinalyze_client=coinalyze,
        sentiment_client=sentiment,
        binance_derivatives_client=binance_deriv,  # v3.0 新增
    )

    # 准备技术指标数据 (模拟)
    technical_data = {
        "price": 100000,
        "sma_20": 99500,
        "sma_50": 98000,
        "rsi": 55,
        "macd": {"macd": 100, "signal": 80, "histogram": 20},
    }

    log("\n组装完整数据...")
    complete_data = assembler.assemble(
        technical_data=technical_data,
        symbol="BTCUSDT",
        interval="15m",
    )

    # 显示数据源状态
    metadata = complete_data.get("_metadata", {})
    log("\n  📊 数据源状态:")
    log(f"     K线来源: {metadata.get('kline_source', 'unknown')}")
    log(f"     Coinalyze: {'✅ 启用' if metadata.get('coinalyze_enabled') else '❌ 禁用'}")
    log(f"     Binance 衍生品: {'✅ 启用' if metadata.get('binance_derivatives_enabled') else '❌ 禁用'}")

    # 显示趋势数据
    derivatives = complete_data.get("derivatives", {})
    trends = derivatives.get("trends", {})
    if trends:
        log("\n  📈 趋势数据:")
        for key, value in trends.items():
            log(f"     {key}: {value}")

    # 显示 Binance 衍生品数据
    binance_deriv_data = complete_data.get("binance_derivatives")
    if binance_deriv_data:
        log("\n  🏦 Binance 衍生品数据:")
        top_pos = binance_deriv_data.get("top_long_short_position", {}).get("latest")
        if top_pos:
            log(f"     大户持仓比: {top_pos.get('longShortRatio')}")
        taker = binance_deriv_data.get("taker_long_short", {}).get("latest")
        if taker:
            log(f"     Taker 买卖比: {taker.get('buySellRatio')}")

    # 测试完整报告格式化
    log("\n📄 完整市场数据报告:")
    log(assembler.format_complete_report(complete_data))

    # =========================================================================
    # 4. 数据利用率统计
    # =========================================================================
    print_header("4. 数据利用率统计")

    stats = """
┌─────────────────────────────────────────────────────────────────────────────┐
│                          v3.0 数据利用率                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  📊 Binance K线 12 列:                    8/12 = 66% → 保持                  │
│                                                                              │
│  📊 Binance 衍生品 API:                   1/6 → 6/6 = 100% ✅ 新增           │
│     + 大户多空账户比 (topLongShortAccountRatio)                              │
│     + 大户多空持仓比 (topLongShortPositionRatio) ⭐                          │
│     + Taker 买卖比 (takerlongshortRatio) ⭐                                  │
│     + OI 历史 (openInterestHist)                                            │
│     + 资金费率历史 (fundingRate)                                            │
│     + 24h 行情统计 (ticker/24hr)                                            │
│                                                                              │
│  📊 Coinalyze API:                        3/7 → 6/7 = 86% ✅ 新增            │
│     + OI 历史 (/open-interest-history) ⭐                                    │
│     + 资金费率历史 (/funding-rate-history) ⭐                                │
│     + 多空比历史 (/long-short-ratio-history) ⭐                              │
│                                                                              │
│  📊 总体利用率:   35-40% → 80%+ ✅                                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
"""
    log(stats)

    log("\n" + "=" * 70)
    log("  ✅ 所有数据源测试完成!")
    log("=" * 70)

    # =========================================================================
    # 5. 导出和推送
    # =========================================================================
    if args.export:
        print_header("5. 导出数据")
        json_file, txt_file = export_data(complete_data, binance_data, coinalyze_data)
        log(f"\n  ✅ JSON 数据: {json_file}")
        log(f"  ✅ 文本报告: {txt_file}")

        if args.push:
            log("\n推送到 GitHub...")
            push_to_github([json_file, txt_file])


if __name__ == "__main__":
    main()
