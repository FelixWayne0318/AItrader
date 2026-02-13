"""
Indicator Test Module

Tests technical indicator initialization and calculation.
"""

from decimal import Decimal
from typing import Dict, Optional

from .base import (
    DiagnosticContext,
    DiagnosticStep,
    MockBar,
    fetch_binance_klines,
    create_bar_from_kline,
)


class IndicatorInitializer(DiagnosticStep):
    """
    Initialize TechnicalIndicatorManager with production config.

    Uses the same initialization as deepseek_strategy.py __init__.
    """

    name = "初始化 TechnicalIndicatorManager"

    def run(self) -> bool:
        try:
            from indicators.technical_manager import TechnicalIndicatorManager

            cfg = self.ctx.strategy_config

            # Use same parameters as deepseek_strategy.py
            self.ctx.indicator_manager = TechnicalIndicatorManager(
                sma_periods=list(cfg.sma_periods),
                ema_periods=[cfg.macd_fast, cfg.macd_slow],
                rsi_period=cfg.rsi_period,
                macd_fast=cfg.macd_fast,
                macd_slow=cfg.macd_slow,
                macd_signal=9,  # Fixed value
                bb_period=cfg.bb_period,
                bb_std=cfg.bb_std,
                volume_ma_period=20,
                support_resistance_lookback=20,
            )

            if not self.ctx.summary_mode:
                print(f"  sma_periods: {list(cfg.sma_periods)}")
                print(f"  ema_periods: [{cfg.macd_fast}, {cfg.macd_slow}]")
                print(f"  rsi_period: {cfg.rsi_period}")
                print(f"  macd: {cfg.macd_fast}/{cfg.macd_slow}/9")
                print(f"  bb_period: {cfg.bb_period}")
                print("  ✅ TechnicalIndicatorManager 初始化成功")

            # Feed K-line data
            for kline in self.ctx.klines_raw:
                bar = MockBar(
                    float(kline[1]),  # open
                    float(kline[2]),  # high
                    float(kline[3]),  # low
                    float(kline[4]),  # close
                    float(kline[5]),  # volume
                    int(kline[0])     # timestamp
                )
                self.ctx.indicator_manager.update(bar)

            # Check initialization
            if self.ctx.indicator_manager.is_initialized():
                print(f"  ✅ 指标已初始化 ({len(self.ctx.klines_raw)} 根K线)")
            else:
                self.ctx.add_warning("指标未完全初始化，可能数据不足")

            return True

        except Exception as e:
            self.ctx.add_error(f"TechnicalIndicatorManager 失败: {e}")
            import traceback
            traceback.print_exc()
            return False


class TechnicalDataFetcher(DiagnosticStep):
    """
    Fetch technical indicator data.

    Same as on_timer technical data retrieval.
    """

    name = "获取技术数据 (模拟 on_timer 流程)"

    def run(self) -> bool:
        try:
            technical_data = self.ctx.indicator_manager.get_technical_data(
                self.ctx.current_price
            )

            # Add 'price' key (required by multi_agent_analyzer._format_technical_report)
            technical_data['price'] = self.ctx.current_price
            self.ctx.technical_data = technical_data

            # Display key indicators
            sma_keys = [k for k in technical_data.keys() if k.startswith('sma_')]
            for key in sorted(sma_keys):
                print(f"  {key.upper()}: ${technical_data[key]:,.2f}")

            ema_keys = [k for k in technical_data.keys() if k.startswith('ema_')]
            for key in sorted(ema_keys):
                print(f"  {key.upper()}: ${technical_data[key]:,.2f}")

            print(f"  RSI: {technical_data.get('rsi', 0):.2f}")
            print(f"  MACD: {technical_data.get('macd', 0):.4f}")
            print(f"  MACD Signal: {technical_data.get('macd_signal', 0):.4f}")
            print(f"  MACD Histogram: {technical_data.get('macd_histogram', 0):.4f}")
            print(f"  BB Upper: ${technical_data.get('bb_upper', 0):,.2f}")
            print(f"  BB Lower: ${technical_data.get('bb_lower', 0):,.2f}")

            # Diagnostic-only data (not sent to AI)
            print(f"  [诊断用] Support: ${technical_data.get('support', 0):,.2f}")
            print(f"  [诊断用] Resistance: ${technical_data.get('resistance', 0):,.2f}")
            print(f"  [诊断用] Overall Trend: {technical_data.get('overall_trend', 'N/A')}")
            print("  ✅ 技术数据获取成功")
            print("  📝 v3.8+: AI 接收原始指标 + S/R Zone v2.0 (动态计算)，不接收预计算的 trend 标签")

            # Load MTF data
            self._load_mtf_data()

            return True

        except Exception as e:
            self.ctx.add_error(f"技术数据获取失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _load_mtf_data(self) -> None:
        """Load multi-timeframe data (4H and 1D)."""
        try:
            from indicators.technical_manager import TechnicalIndicatorManager

            # 4H Decision Layer
            klines_4h = fetch_binance_klines(self.ctx.symbol, "4h", 60)
            if klines_4h and len(klines_4h) >= 50:
                indicator_manager_4h = TechnicalIndicatorManager(
                    sma_periods=[20, 50],
                    ema_periods=[12, 26],
                    rsi_period=14,
                    macd_fast=12,
                    macd_slow=26,
                    macd_signal=9,
                    bb_period=20,
                )
                for kline in klines_4h:
                    bar_4h = create_bar_from_kline(kline, "4H")
                    indicator_manager_4h.update(bar_4h)

                decision_layer_data = indicator_manager_4h.get_technical_data(
                    self.ctx.current_price
                )
                self.ctx.technical_data['mtf_decision_layer'] = {
                    'timeframe': '4H',
                    'rsi': decision_layer_data.get('rsi', 50),
                    'macd': decision_layer_data.get('macd', 0),
                    'macd_signal': decision_layer_data.get('macd_signal', 0),
                    'sma_20': decision_layer_data.get('sma_20', 0),
                    'sma_50': decision_layer_data.get('sma_50', 0),
                    'bb_upper': decision_layer_data.get('bb_upper', 0),
                    'bb_middle': decision_layer_data.get('bb_middle', 0),
                    'bb_lower': decision_layer_data.get('bb_lower', 0),
                    'bb_position': decision_layer_data.get('bb_position', 50),
                }
                rsi_4h = self.ctx.technical_data['mtf_decision_layer']['rsi']
                print(f"  ✅ 4H 决策层数据加载: RSI={rsi_4h:.1f}")

                # v4.0: Store raw 4H bars for S/R swing detection + volume profile
                self.ctx.bars_data_4h = [
                    {'high': float(k[2]), 'low': float(k[3]),
                     'close': float(k[4]), 'open': float(k[1]),
                     'volume': float(k[5])}
                    for k in klines_4h
                ]
            else:
                print("  ⚠️ 4H K线数据不足，跳过决策层")

            # 1D Trend Layer
            klines_1d = fetch_binance_klines(self.ctx.symbol, "1d", 220)
            if klines_1d and len(klines_1d) >= 200:
                indicator_manager_1d = TechnicalIndicatorManager(
                    sma_periods=[200],
                    ema_periods=[12, 26],
                    rsi_period=14,
                    macd_fast=12,
                    macd_slow=26,
                    macd_signal=9,
                    bb_period=20,
                )
                for kline in klines_1d:
                    bar_1d = create_bar_from_kline(kline, "1D")
                    indicator_manager_1d.update(bar_1d)

                trend_layer_data = indicator_manager_1d.get_technical_data(
                    self.ctx.current_price
                )
                self.ctx.technical_data['mtf_trend_layer'] = {
                    'timeframe': '1D',
                    'sma_200': trend_layer_data.get('sma_200', 0),
                    'macd': trend_layer_data.get('macd', 0),
                    'macd_signal': trend_layer_data.get('macd_signal', 0),
                    # v3.25: 1D RSI + ADX for macro analysis (match production)
                    'rsi': trend_layer_data.get('rsi', 0),
                    'adx': trend_layer_data.get('adx', 0),
                    'di_plus': trend_layer_data.get('di_plus', 0),
                    'di_minus': trend_layer_data.get('di_minus', 0),
                    'adx_regime': trend_layer_data.get('adx_regime', 'UNKNOWN'),
                }
                mtf_1d = self.ctx.technical_data['mtf_trend_layer']
                sma_200 = mtf_1d['sma_200']
                rsi_1d = mtf_1d['rsi']
                adx_1d = mtf_1d['adx']
                print(f"  ✅ 1D 趋势层数据加载: SMA_200=${sma_200:,.2f}, RSI={rsi_1d:.1f}, ADX={adx_1d:.1f} ({mtf_1d['adx_regime']})")

                # v4.0: Store raw 1D bars for S/R swing detection + pivot calculation
                bars_1d_dicts = [
                    {'high': float(k[2]), 'low': float(k[3]),
                     'close': float(k[4]), 'open': float(k[1]),
                     'volume': float(k[5])}
                    for k in klines_1d
                ]
                self.ctx.bars_data_1d = bars_1d_dicts
                if bars_1d_dicts:
                    self.ctx.daily_bar = bars_1d_dicts[-1]
                    try:
                        from utils.sr_pivot_calculator import aggregate_weekly_bar
                        self.ctx.weekly_bar = aggregate_weekly_bar(bars_1d_dicts)
                    except Exception:
                        pass
            else:
                count = len(klines_1d) if klines_1d else 0
                print(f"  ⚠️ 1D K线数据不足 ({count}/200)，跳过趋势层")

        except Exception as e:
            self.ctx.add_warning(f"MTF 多时间框架数据获取失败: {e}")
