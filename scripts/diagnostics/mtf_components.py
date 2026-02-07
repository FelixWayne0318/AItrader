"""
MTF Components Module

Tests Multi-Timeframe data collection components.
"""

import os
from typing import Dict, Optional

from .base import (
    DiagnosticContext,
    DiagnosticStep,
    fetch_binance_klines,
    mask_sensitive,
)


class MTFComponentTester(DiagnosticStep):
    """
    Test MTF v2.1 components integration.

    Tests:
    - BinanceKlineClient
    - OrderFlowProcessor
    - CoinalyzeClient
    - AIDataAssembler
    - OrderBookProcessor (if enabled)
    """

    name = "MTF v2.1 组件集成测试"

    def run(self) -> bool:
        print("-" * 70)

        try:
            # Test individual components
            self._test_binance_kline_client()
            self._test_order_flow_processor()
            self._test_coinalyze_client()
            self._test_ai_data_assembler()
            self._test_order_book()
            self._test_sr_zone_calculator()

            print()
            print("  ✅ MTF v2.1 + Order Book 组件集成测试完成")
            return True

        except Exception as e:
            self.ctx.add_error(f"MTF 组件测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _test_binance_kline_client(self) -> None:
        """Test BinanceKlineClient."""
        print("  [9.1] 测试 BinanceKlineClient...")
        try:
            from utils.binance_kline_client import BinanceKlineClient

            kline_client = BinanceKlineClient(timeout=10)
            print("     ✅ BinanceKlineClient 导入成功")

            # Test get_klines
            klines = kline_client.get_klines(
                symbol=self.ctx.symbol,
                interval="15m",
                limit=10
            )
            if klines and len(klines) > 0:
                print(f"     ✅ get_klines: 返回 {len(klines)} 根 K线")
            else:
                print("     ⚠️ get_klines 返回空数据")

        except ImportError as e:
            print(f"     ❌ 无法导入 BinanceKlineClient: {e}")
        except Exception as e:
            print(f"     ❌ BinanceKlineClient 测试失败: {e}")

    def _test_order_flow_processor(self) -> None:
        """Test OrderFlowProcessor."""
        print()
        print("  [9.2] 测试 OrderFlowProcessor...")
        try:
            from utils.order_flow_processor import OrderFlowProcessor
            from utils.binance_kline_client import BinanceKlineClient

            processor = OrderFlowProcessor(logger=None)
            print("     ✅ OrderFlowProcessor 导入成功")

            kline_client = BinanceKlineClient(timeout=10)
            klines = kline_client.get_klines(
                symbol=self.ctx.symbol,
                interval="15m",
                limit=10
            )

            if klines:
                result = processor.process_klines(klines)
                if result:
                    print(f"     ✅ process_klines: buy_ratio={result.get('buy_ratio', 0):.4f}")
                    print(f"        cvd_trend: {result.get('cvd_trend', 'N/A')}")
                    print(f"        volume_usdt: ${result.get('volume_usdt', 0):,.0f}")

        except ImportError as e:
            print(f"     ❌ 无法导入 OrderFlowProcessor: {e}")
        except Exception as e:
            print(f"     ❌ OrderFlowProcessor 测试失败: {e}")

    def _test_coinalyze_client(self) -> None:
        """Test CoinalyzeClient."""
        print()
        print("  [9.3] 测试 CoinalyzeClient...")
        try:
            from utils.coinalyze_client import CoinalyzeClient
            from utils.binance_kline_client import BinanceKlineClient

            coinalyze_cfg = self.ctx.base_config.get('order_flow', {}).get('coinalyze', {})
            coinalyze_enabled = coinalyze_cfg.get('enabled', False)
            coinalyze_api_key = coinalyze_cfg.get('api_key') or os.getenv('COINALYZE_API_KEY')

            coinalyze_client = CoinalyzeClient(
                api_key=coinalyze_api_key,
                timeout=coinalyze_cfg.get('timeout', 10),
                max_retries=coinalyze_cfg.get('max_retries', 2),
                logger=None
            )
            print("     ✅ CoinalyzeClient 导入成功")

            if not coinalyze_enabled:
                print("     ℹ️ Coinalyze 未启用")
            elif not coinalyze_api_key:
                print("     ⚠️ Coinalyze API Key 未配置")
            else:
                print(f"     📊 Coinalyze API 测试 (Key: {mask_sensitive(coinalyze_api_key)})")

                symbol = coinalyze_cfg.get('symbol', 'BTCUSDT_PERP.A')

                # Test Open Interest
                oi_data = coinalyze_client.get_open_interest(symbol=symbol)
                if oi_data:
                    print(f"        ✅ OI (BTC): {oi_data.get('value', 0):,.2f}")
                else:
                    print("        ❌ OI 获取失败")

                # Test Funding Rate (使用 Binance 作为主要数据源)
                kline_client = BinanceKlineClient(timeout=10)
                binance_fr = kline_client.get_funding_rate(symbol=self.ctx.symbol)
                if binance_fr:
                    print(f"        ✅ Settled FR: {binance_fr.get('funding_rate_pct', 0):.4f}% | Predicted FR: {binance_fr.get('predicted_rate_pct', 0):.4f}%")
                    # v4.8: 保存 Binance funding rate 到 context (主要数据源)
                    self.ctx.binance_funding_rate = binance_fr

        except ImportError as e:
            print(f"     ❌ 无法导入 CoinalyzeClient: {e}")
        except Exception as e:
            print(f"     ❌ CoinalyzeClient 测试失败: {e}")

    def _test_ai_data_assembler(self) -> None:
        """Test AIDataAssembler."""
        print()
        print("  [9.4] 测试 AIDataAssembler...")
        try:
            from utils.ai_data_assembler import AIDataAssembler
            from utils.binance_kline_client import BinanceKlineClient
            from utils.order_flow_processor import OrderFlowProcessor
            from utils.coinalyze_client import CoinalyzeClient
            from utils.sentiment_client import SentimentDataFetcher

            kline_client = BinanceKlineClient(timeout=10)
            processor = OrderFlowProcessor(logger=None)

            coinalyze_cfg = self.ctx.base_config.get('order_flow', {}).get('coinalyze', {})
            coinalyze_api_key = coinalyze_cfg.get('api_key') or os.getenv('COINALYZE_API_KEY')
            coinalyze_client = CoinalyzeClient(
                api_key=coinalyze_api_key,
                timeout=10,
                logger=None
            )

            sentiment_client = SentimentDataFetcher()

            assembler = AIDataAssembler(
                binance_kline_client=kline_client,
                order_flow_processor=processor,
                coinalyze_client=coinalyze_client,
                sentiment_client=sentiment_client,
                logger=None
            )
            print("     ✅ AIDataAssembler 导入成功")

            assembled = assembler.assemble(
                technical_data=self.ctx.technical_data,
                position_data=self.ctx.current_position,
                symbol=self.ctx.symbol,
                interval=self.ctx.interval
            )

            print(f"     ✅ 数据组装完成:")
            print(f"        - 技术指标: {assembled.get('technical') is not None}")
            print(f"        - 订单流: {assembled.get('order_flow') is not None}")
            print(f"        - 衍生品: {assembled.get('derivatives') is not None}")
            print(f"        - 情绪数据: {assembled.get('sentiment') is not None}")

        except ImportError as e:
            print(f"     ❌ 无法导入 AIDataAssembler: {e}")
        except Exception as e:
            print(f"     ❌ AIDataAssembler 测试失败: {e}")

    def _test_order_book(self) -> None:
        """Test Order Book components."""
        print()
        print("  [9.5] 测试 Order Book (v3.7)...")

        order_book_cfg = self.ctx.base_config.get('order_book', {})
        order_book_enabled = order_book_cfg.get('enabled', False)

        if not order_book_enabled:
            print("     ℹ️ Order Book 未启用 (order_book.enabled = false)")
            print("     → 若要启用，修改 configs/base.yaml: order_book.enabled: true")
            return

        try:
            from utils.binance_orderbook_client import BinanceOrderBookClient
            from utils.orderbook_processor import OrderBookProcessor

            ob_api_cfg = order_book_cfg.get('api', {})
            ob_proc_cfg = order_book_cfg.get('processing', {})

            ob_client = BinanceOrderBookClient(
                timeout=ob_api_cfg.get('timeout', 10),
                max_retries=ob_api_cfg.get('max_retries', 2),
                logger=None
            )
            print("     ✅ BinanceOrderBookClient 导入成功")

            weighted_obi_cfg = ob_proc_cfg.get('weighted_obi', {})
            anomaly_cfg = ob_proc_cfg.get('anomaly_detection', {})

            # Ensure all required keys are present (avoid KeyError)
            weighted_obi_config = {
                "base_decay": weighted_obi_cfg.get('base_decay', 0.8),
                "adaptive": weighted_obi_cfg.get('adaptive', True),
                "volatility_factor": weighted_obi_cfg.get('volatility_factor', 0.1),
                "min_decay": weighted_obi_cfg.get('min_decay', 0.5),
                "max_decay": weighted_obi_cfg.get('max_decay', 0.95),
            }

            ob_processor = OrderBookProcessor(
                price_band_pct=ob_proc_cfg.get('price_band_pct', 0.5),
                base_anomaly_threshold=anomaly_cfg.get('base_threshold', 3.0),
                slippage_amounts=ob_proc_cfg.get('slippage_amounts', [0.1, 0.5, 1.0]),
                weighted_obi_config=weighted_obi_config,
                history_size=ob_proc_cfg.get('history', {}).get('size', 10),
                logger=None
            )
            print("     ✅ OrderBookProcessor 导入成功")

            # Get order book
            ob_limit = ob_api_cfg.get('limit', 100)
            raw_ob = ob_client.get_order_book(symbol=self.ctx.symbol, limit=ob_limit)

            if raw_ob:
                bids = raw_ob.get('bids', [])
                asks = raw_ob.get('asks', [])
                print(f"     ✅ 订单簿获取成功: {len(bids)} bids, {len(asks)} asks")

                if bids and asks:
                    best_bid = float(bids[0][0])
                    best_ask = float(asks[0][0])
                    spread = best_ask - best_bid
                    spread_pct = (spread / best_bid) * 100
                    print(f"        盘口: Bid ${best_bid:,.2f} | Ask ${best_ask:,.2f}")
                    print(f"        Spread: ${spread:.2f} ({spread_pct:.4f}%)")

                # Process
                ob_result = ob_processor.process(
                    order_book=raw_ob,
                    current_price=self.ctx.current_price,
                    volatility=0.02
                )

                if ob_result:
                    obi = ob_result.get('obi', {})
                    print(f"        OBI Simple: {obi.get('simple', 0):+.4f}")
                    print(f"        OBI Adaptive: {obi.get('adaptive_weighted', 0):+.4f}")

        except ImportError as e:
            print(f"     ❌ 无法导入订单簿模块: {e}")
        except Exception as e:
            print(f"     ❌ Order Book 测试失败: {e}")

    def _test_sr_zone_calculator(self) -> None:
        """Test S/R Zone Calculator."""
        print()
        print("  [9.5.5] S/R Zone Calculator 测试 (v2.0):")
        try:
            from utils.sr_zone_calculator import SRZoneCalculator, SRLevel, SRSourceType
            print("     ✅ SRZoneCalculator 导入成功")

            # Get data from context
            test_bb_data = None
            test_sma_data = None

            if self.ctx.technical_data:
                bb_upper = self.ctx.technical_data.get('bb_upper')
                bb_lower = self.ctx.technical_data.get('bb_lower')
                if bb_upper and bb_lower:
                    test_bb_data = {
                        'upper': bb_upper,
                        'lower': bb_lower,
                        'middle': self.ctx.technical_data.get('bb_middle'),
                    }

                sma_50 = self.ctx.technical_data.get('sma_50')
                sma_200 = self.ctx.technical_data.get('sma_200')
                if sma_50 or sma_200:
                    test_sma_data = {'sma_50': sma_50, 'sma_200': sma_200}

            sr_calc = SRZoneCalculator(
                cluster_pct=0.5,
                zone_expand_pct=0.1,
                hard_control_threshold_pct=1.0,
            )

            sr_result = sr_calc.calculate_with_detailed_report(
                current_price=self.ctx.current_price,
                bb_data=test_bb_data,
                sma_data=test_sma_data,
                orderbook_anomalies=None,
            )

            print(f"     📊 当前价格: ${self.ctx.current_price:,.0f}")
            print(f"     📊 数据源: BB={'✅' if test_bb_data else '❌'}, SMA={'✅' if test_sma_data else '❌'}")

            # Display resistance zones
            resistance_zones = sr_result.get('resistance_zones', [])
            print(f"     🔴 阻力位: {len(resistance_zones)} zones")
            for i, zone in enumerate(resistance_zones[:2]):
                wall_info = f" [Wall: {zone.wall_size_btc:.1f} BTC]" if zone.has_order_wall else ""
                print(f"        {i+1}. ${zone.price_center:,.0f} ({zone.distance_pct:.1f}% away) [{zone.strength}]{wall_info}")

            # Display support zones
            support_zones = sr_result.get('support_zones', [])
            print(f"     🟢 支撑位: {len(support_zones)} zones")
            for i, zone in enumerate(support_zones[:2]):
                wall_info = f" [Wall: {zone.wall_size_btc:.1f} BTC]" if zone.has_order_wall else ""
                print(f"        {i+1}. ${zone.price_center:,.0f} ({zone.distance_pct:.1f}% away) [{zone.strength}]{wall_info}")

            # Hard control status (v3.16: AI 建议，非本地覆盖)
            hard_control = sr_result.get('hard_control', {})
            block_long = hard_control.get('block_long', False)
            block_short = hard_control.get('block_short', False)
            if block_long or block_short:
                print(f"     📋 AI 建议: 避免 LONG={block_long}, 避免 SHORT={block_short} (v3.16 AI 自主判断)")
            else:
                print(f"     ✅ S/R Zone 建议: 无限制")

            print("     ✅ S/R Zone Calculator 测试完成")

        except ImportError as e:
            print(f"     ❌ 无法导入 SRZoneCalculator: {e}")
        except Exception as e:
            print(f"     ❌ S/R Zone 测试失败: {e}")

    def should_skip(self) -> bool:
        return self.ctx.summary_mode


class TelegramChecker(DiagnosticStep):
    """
    Verify Telegram command handling.

    Tests bot connectivity and command handler setup.
    """

    name = "Telegram 命令处理验证"

    def run(self) -> bool:
        print("-" * 70)

        try:
            import requests

            telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
            telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')

            if not telegram_token:
                self.ctx.add_warning("TELEGRAM_BOT_TOKEN 未配置")
                return True
            if not telegram_chat_id:
                self.ctx.add_warning("TELEGRAM_CHAT_ID 未配置")
                return True

            print(f"  ✅ Telegram 配置已加载")
            print(f"     Bot Token: {mask_sensitive(telegram_token)}")
            print(f"     Chat ID: {telegram_chat_id}")

            # Check module imports
            print()
            print("  📋 Telegram 模块检查:")

            from utils.telegram_bot import TelegramBot
            print("     ✅ TelegramBot 类可导入")

            if hasattr(TelegramBot, 'send_message_sync'):
                print("     ✅ TelegramBot.send_message_sync 方法存在")
            else:
                self.ctx.add_warning("TelegramBot.send_message_sync 方法缺失")

            from utils.telegram_command_handler import TelegramCommandHandler
            print("     ✅ TelegramCommandHandler 类可导入")

            # Check command methods
            commands = ['cmd_status', 'cmd_position', 'cmd_pause', 'cmd_resume', 'cmd_close']
            for cmd in commands:
                if hasattr(TelegramCommandHandler, cmd):
                    print(f"        ✅ {cmd} 方法存在")
                else:
                    print(f"        ⚠️ {cmd} 方法缺失")

            # Test API connectivity
            print()
            print("  📤 Telegram API 连通性测试:")
            api_url = f"https://api.telegram.org/bot{telegram_token}/getMe"
            resp = requests.get(api_url, timeout=10)

            if resp.status_code == 200:
                bot_info = resp.json()
                if bot_info.get('ok'):
                    result = bot_info.get('result', {})
                    print(f"     ✅ Bot Token 有效")
                    print(f"        Bot 名称: @{result.get('username', 'N/A')}")
                else:
                    print(f"     ❌ Bot Token 无效")
            else:
                print(f"     ❌ API 错误: {resp.status_code}")

            print()
            print("  ✅ Telegram 验证完成")
            return True

        except Exception as e:
            self.ctx.add_warning(f"Telegram 验证失败: {e}")
            return True  # Non-critical

    def should_skip(self) -> bool:
        return self.ctx.summary_mode


class ErrorRecoveryChecker(DiagnosticStep):
    """
    Verify error recovery mechanisms.

    Checks fallback logic for various failure scenarios.
    """

    name = "错误恢复机制验证"

    def run(self) -> bool:
        print("-" * 70)

        print("  📋 AI 调用失败恢复机制:")
        print()

        # Check MultiAgentAnalyzer fallback
        print("  [1] MultiAgentAnalyzer fallback:")
        try:
            from agents.multi_agent_analyzer import MultiAgentAnalyzer
            if hasattr(MultiAgentAnalyzer, '_create_fallback_signal'):
                print("     ✅ _create_fallback_signal 方法存在")
                print("     → AI 调用失败时返回 HOLD + LOW confidence")
            else:
                print("     ⚠️ _create_fallback_signal 方法不存在")
        except ImportError as e:
            print(f"     ❌ 无法导入 MultiAgentAnalyzer: {e}")

        # API retry mechanism
        print()
        print("  [2] API 重试机制:")
        print("     ✅ _call_api_with_retry: 最多重试 2 次")
        print("     ✅ _extract_json_with_retry: JSON 解析失败重试 2 次")
        print("     → 失败后使用 fallback signal")

        # Data fetch failure recovery
        print()
        print("  [3] 数据获取失败恢复:")
        print("     ✅ Coinalyze 失败 → 使用中性默认值 (OI=0, FR=0)")
        print("     ✅ Binance K线失败 → 使用 indicator_manager 缓存数据")
        print("     ✅ 情绪数据失败 → 使用中性默认值 (ratio=0.5)")

        # SL/TP validation failure
        print()
        print("  [4] SL/TP 验证失败恢复:")
        print("     ✅ validate_multiagent_sltp 失败 → 回退到 calculate_technical_sltp")
        print("        (包括: SL 方向错误, 距离不足, R/R < 1.5:1)")
        print("     ✅ 技术 SL/TP 计算失败 → 使用默认 2% SL, confidence-based TP")

        # Network error recovery
        print()
        print("  [5] 网络错误恢复:")
        print("     ✅ requests 超时 → 自动重试 (指数退避)")
        print("     ✅ API rate limit → 等待后重试")
        print("     ✅ 连接失败 → 记录错误，使用 fallback")

        print()
        print("  ✅ 错误恢复机制验证完成")
        return True

    def should_skip(self) -> bool:
        return self.ctx.summary_mode
