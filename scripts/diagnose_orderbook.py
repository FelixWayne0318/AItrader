#!/usr/bin/env python3
# scripts/diagnose_orderbook.py

"""
订单簿功能诊断脚本

用途:
- 测试 Binance 订单簿 API 连接
- 验证订单簿处理器功能
- 显示完整订单簿数据
- 验证配置加载

运行:
    python3 scripts/diagnose_orderbook.py
    python3 scripts/diagnose_orderbook.py --symbol ETHUSDT
"""

import sys
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.binance_orderbook_client import BinanceOrderBookClient
from utils.orderbook_processor import OrderBookProcessor
from utils.config_manager import ConfigManager


def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def test_orderbook_client(symbol="BTCUSDT", limit=100):
    """
    测试订单簿客户端

    Parameters
    ----------
    symbol : str
        交易对
    limit : int
        深度档位数
    """
    print("\n" + "=" * 70)
    print("📖 测试订单簿客户端")
    print("=" * 70)

    logger = logging.getLogger("test_orderbook_client")
    client = BinanceOrderBookClient(timeout=10, max_retries=2, logger=logger)

    print(f"\n获取 {symbol} 订单簿 (limit={limit})...")

    orderbook = client.get_order_book(symbol=symbol, limit=limit)

    if orderbook:
        print("✅ 订单簿获取成功")
        print(f"\n订单簿信息:")
        print(f"  - 时间戳: {orderbook.get('T', 'N/A')}")
        print(f"  - Bids 数量: {len(orderbook.get('bids', []))}")
        print(f"  - Asks 数量: {len(orderbook.get('asks', []))}")

        # 显示最优买卖价
        if orderbook.get('bids') and orderbook.get('asks'):
            best_bid = float(orderbook['bids'][0][0])
            best_ask = float(orderbook['asks'][0][0])
            spread = best_ask - best_bid
            spread_pct = spread / best_bid * 100

            print(f"\n盘口信息:")
            print(f"  - Best Bid: ${best_bid:,.2f}")
            print(f"  - Best Ask: ${best_ask:,.2f}")
            print(f"  - Spread: ${spread:.2f} ({spread_pct:.4f}%)")

        # 显示前 5 档
        print(f"\n前 5 档买单:")
        for i, (price, qty) in enumerate(orderbook.get('bids', [])[:5]):
            print(f"  {i+1}. ${float(price):,.2f} @ {float(qty):.4f} BTC")

        print(f"\n前 5 档卖单:")
        for i, (price, qty) in enumerate(orderbook.get('asks', [])[:5]):
            print(f"  {i+1}. ${float(price):,.2f} @ {float(qty):.4f} BTC")

        return orderbook
    else:
        print("❌ 订单簿获取失败")
        return None


def test_orderbook_processor(orderbook, current_price, volatility=0.02):
    """
    测试订单簿处理器

    Parameters
    ----------
    orderbook : dict
        原始订单簿数据
    current_price : float
        当前价格
    volatility : float
        波动率
    """
    print("\n" + "=" * 70)
    print("⚙️  测试订单簿处理器")
    print("=" * 70)

    logger = logging.getLogger("test_orderbook_processor")

    # 从配置加载参数
    try:
        config = ConfigManager(env='development')
        config.load()

        processor_config = config.get('order_book', 'processing', default={})
        weighted_obi_config = processor_config.get('weighted_obi', {})
        anomaly_config = processor_config.get('anomaly_detection', {})
        slippage_amounts = processor_config.get('slippage_amounts', [0.1, 0.5, 1.0])

        print(f"\n配置加载成功:")
        print(f"  - Weighted OBI: {weighted_obi_config}")
        print(f"  - Anomaly Detection: {anomaly_config}")
        print(f"  - Slippage Amounts: {slippage_amounts}")

    except Exception as e:
        print(f"⚠️ 配置加载失败: {e}，使用默认配置")
        weighted_obi_config = {}
        anomaly_config = {}
        slippage_amounts = [0.1, 0.5, 1.0]

    # Ensure all required keys are present (avoid KeyError)
    complete_weighted_obi_config = {
        "base_decay": weighted_obi_config.get('base_decay', 0.8),
        "adaptive": weighted_obi_config.get('adaptive', True),
        "volatility_factor": weighted_obi_config.get('volatility_factor', 0.1),
        "min_decay": weighted_obi_config.get('min_decay', 0.5),
        "max_decay": weighted_obi_config.get('max_decay', 0.95),
    }

    processor = OrderBookProcessor(
        price_band_pct=0.5,
        base_anomaly_threshold=anomaly_config.get('base_threshold', 3.0),
        slippage_amounts=slippage_amounts,
        weighted_obi_config=complete_weighted_obi_config,
        history_size=10,
        logger=logger,
    )

    print(f"\n处理订单簿 (current_price=${current_price:,.2f}, volatility={volatility:.4f})...")

    result = processor.process(
        order_book=orderbook,
        current_price=current_price,
        volatility=volatility,
    )

    if result and result.get("_status", {}).get("code") == "OK":
        print("✅ 订单簿处理成功")

        # 显示 OBI
        obi = result.get("obi", {})
        print(f"\nOBI 指标:")
        print(f"  - Simple OBI: {obi.get('simple', 0):+.4f}")
        print(f"  - Weighted OBI: {obi.get('weighted', 0):+.4f}")
        print(f"  - Adaptive Weighted OBI: {obi.get('adaptive_weighted', 0):+.4f}")
        print(f"  - Decay Used: {obi.get('decay_used', 0):.2f}")
        print(f"  - Bid Volume: ${obi.get('bid_volume_usd', 0):,.0f} ({obi.get('bid_volume_btc', 0):.2f} BTC)")
        print(f"  - Ask Volume: ${obi.get('ask_volume_usd', 0):,.0f} ({obi.get('ask_volume_btc', 0):.2f} BTC)")

        # 显示 Pressure Gradient
        gradient = result.get("pressure_gradient", {})
        if gradient:
            print(f"\nPressure Gradient:")
            print(f"  - Bid: {gradient.get('bid_near_5', 0):.0%} near-5, "
                  f"{gradient.get('bid_near_10', 0):.0%} near-10 "
                  f"[{gradient.get('bid_concentration', 'N/A')}]")
            print(f"  - Ask: {gradient.get('ask_near_5', 0):.0%} near-5, "
                  f"{gradient.get('ask_near_10', 0):.0%} near-10 "
                  f"[{gradient.get('ask_concentration', 'N/A')}]")

        # 显示流动性
        liquidity = result.get("liquidity", {})
        if liquidity:
            print(f"\n流动性:")
            print(f"  - Spread: {liquidity.get('spread_pct', 0):.4f}%")

            slippage = liquidity.get("slippage", {})
            for key, value in slippage.items():
                if "buy_1.0_btc" in key and value.get("estimated") is not None:
                    print(f"  - Slippage (Buy 1 BTC): {value['estimated']:.4f}% "
                          f"[conf={value['confidence']:.0%}, "
                          f"range={value['range'][0]:.4f}%-{value['range'][1]:.4f}%]")

        # 显示异常
        anomalies = result.get("anomalies", {})
        if anomalies and anomalies.get("has_significant"):
            print(f"\n异常检测:")
            print(f"  - Threshold: {anomalies.get('threshold_used', 0):.1f}x "
                  f"({anomalies.get('threshold_reason', 'N/A')})")

            bid_anomalies = anomalies.get("bid_anomalies", [])
            if bid_anomalies:
                print(f"  - Bid Anomalies: {len(bid_anomalies)}")
                for a in bid_anomalies[:3]:
                    print(f"    @ ${a['price']:,.0f}: {a['volume_btc']:.0f} BTC ({a['multiplier']:.1f}x)")

            ask_anomalies = anomalies.get("ask_anomalies", [])
            if ask_anomalies:
                print(f"  - Ask Anomalies: {len(ask_anomalies)}")
                for a in ask_anomalies[:3]:
                    print(f"    @ ${a['price']:,.0f}: {a['volume_btc']:.0f} BTC ({a['multiplier']:.1f}x)")

        # 显示 Dynamics (第二次运行时会有数据)
        dynamics = result.get("dynamics", {})
        if dynamics and dynamics.get("samples_count", 0) > 0:
            print(f"\nDynamics (vs previous):")
            print(f"  - OBI Change: {dynamics.get('obi_change', 0):+.4f} "
                  f"({dynamics.get('obi_change_pct', 0):+.1f}%)")
            print(f"  - Trend: {dynamics.get('trend', 'N/A')}")

        return result
    else:
        print(f"❌ 订单簿处理失败")
        status = result.get("_status", {})
        print(f"  Status: {status.get('code', 'UNKNOWN')}")
        print(f"  Message: {status.get('message', 'N/A')}")
        return None


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="订单簿功能诊断")
    parser.add_argument("--symbol", default="BTCUSDT", help="交易对 (默认: BTCUSDT)")
    parser.add_argument("--limit", type=int, default=100, help="深度档位数 (默认: 100)")
    parser.add_argument("--volatility", type=float, default=0.02, help="波动率 (默认: 0.02)")

    args = parser.parse_args()

    setup_logging()

    print("\n" + "=" * 70)
    print("🔍 订单簿功能诊断脚本")
    print("=" * 70)
    print(f"\n参数:")
    print(f"  - Symbol: {args.symbol}")
    print(f"  - Limit: {args.limit}")
    print(f"  - Volatility: {args.volatility}")

    # Step 1: 测试客户端
    orderbook = test_orderbook_client(symbol=args.symbol, limit=args.limit)

    if not orderbook:
        print("\n❌ 订单簿客户端测试失败，退出")
        sys.exit(1)

    # Step 2: 测试处理器
    best_bid = float(orderbook['bids'][0][0])
    best_ask = float(orderbook['asks'][0][0])
    current_price = (best_bid + best_ask) / 2

    result = test_orderbook_processor(
        orderbook=orderbook,
        current_price=current_price,
        volatility=args.volatility,
    )

    if not result:
        print("\n❌ 订单簿处理器测试失败，退出")
        sys.exit(1)

    # Step 3: 第二次运行 (测试 Dynamics)
    print("\n" + "=" * 70)
    print("🔄 第二次运行 (测试 Dynamics 功能)")
    print("=" * 70)

    orderbook2 = test_orderbook_client(symbol=args.symbol, limit=args.limit)
    if orderbook2:
        # 使用相同的 processor 实例 (保留历史)
        logger = logging.getLogger("test_orderbook_processor")
        processor_config = ConfigManager(env='development').get('order_book', 'processing', default={})
        weighted_obi_raw = processor_config.get('weighted_obi', {})
        # Ensure all required keys are present (avoid KeyError)
        weighted_obi_complete = {
            "base_decay": weighted_obi_raw.get('base_decay', 0.8),
            "adaptive": weighted_obi_raw.get('adaptive', True),
            "volatility_factor": weighted_obi_raw.get('volatility_factor', 0.1),
            "min_decay": weighted_obi_raw.get('min_decay', 0.5),
            "max_decay": weighted_obi_raw.get('max_decay', 0.95),
        }
        processor = OrderBookProcessor(
            price_band_pct=0.5,
            base_anomaly_threshold=3.0,
            weighted_obi_config=weighted_obi_complete,
            logger=logger,
        )

        # 第一次处理 (建立历史)
        processor.process(orderbook, current_price, args.volatility)

        # 第二次处理 (显示 Dynamics)
        result2 = processor.process(orderbook2, current_price, args.volatility)

        dynamics = result2.get("dynamics", {})
        if dynamics and dynamics.get("samples_count", 0) > 0:
            print("\n✅ Dynamics 数据可用:")
            print(f"  - Samples Count: {dynamics.get('samples_count', 0)}")
            print(f"  - Trend: {dynamics.get('trend', 'N/A')}")

    print("\n" + "=" * 70)
    print("✅ 所有测试完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
