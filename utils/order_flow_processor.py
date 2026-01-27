# utils/order_flow_processor.py

import logging
from typing import List, Dict, Any, Union


class OrderFlowProcessor:
    """
    订单流数据处理器

    从 Binance K线数据计算订单流指标

    v2.0 更新:
    - 支持 Binance 原始 12 列格式 (List[List])
    - 支持本地 Dict 格式 (List[Dict]) - 降级模式，无订单流数据
    """

    def __init__(self, logger: logging.Logger = None):
        self._cvd_history: List[float] = []
        self.logger = logger or logging.getLogger(__name__)

    def process_klines(
        self,
        klines: Union[List[List], List[Dict]],
    ) -> Dict[str, Any]:
        """
        处理 K线数据，计算订单流指标

        Args:
            klines: K线数据，支持两种格式:
                - List[List]: Binance 原始 12 列格式 (完整订单流数据)
                - List[Dict]: 本地 Dict 格式 (降级模式，无订单流数据)

        Returns:
            {
                "buy_ratio": 0.55,           # 买盘占比
                "avg_trade_usdt": 1250.5,    # 平均成交额
                "volume_usdt": 125000000,    # 总成交额
                "trades_count": 100000,      # 成交笔数
                "cvd_trend": "RISING",       # CVD 趋势
                "recent_10_bars": [...],     # 最近10根bar的买盘比
                "data_source": "binance_raw" | "local_dict",
            }
        """
        if not klines or len(klines) == 0:
            return self._default_result()

        # 检测数据格式
        if isinstance(klines[0], list):
            return self._process_binance_format(klines)
        elif isinstance(klines[0], dict):
            return self._process_dict_format(klines)
        else:
            self.logger.warning(f"⚠️ Unknown kline format: {type(klines[0])}")
            return self._default_result()

    def _process_binance_format(self, klines: List[List]) -> Dict[str, Any]:
        """
        处理 Binance 原始 12 列格式 (完整订单流数据)

        v2.1 更新:
        - buy_ratio 改用 10 根 K 线平均值 (更稳定，减少噪声)
        - 保留 latest_buy_ratio 供参考
        """
        latest = klines[-1]

        volume = float(latest[5])
        taker_buy_volume = float(latest[9])
        quote_volume = float(latest[7])
        trades_count = int(latest[8])

        # 计算最新 K 线的买盘占比 (保留供参考)
        latest_buy_ratio = taker_buy_volume / volume if volume > 0 else 0.5

        # 计算平均成交额
        avg_trade_usdt = quote_volume / trades_count if trades_count > 0 else 0

        # 计算 CVD (累积成交量差)
        sell_volume = volume - taker_buy_volume
        cvd_delta = taker_buy_volume - sell_volume
        self._cvd_history.append(cvd_delta)

        # 保留最近 50 个 CVD 值
        if len(self._cvd_history) > 50:
            self._cvd_history = self._cvd_history[-50:]

        # 判断 CVD 趋势
        cvd_trend = self._calculate_cvd_trend()

        # 计算最近 10 根 bar 的买盘比
        recent_10_bars = []
        for bar in klines[-10:]:
            bar_volume = float(bar[5])
            bar_buy = float(bar[9])
            bar_ratio = bar_buy / bar_volume if bar_volume > 0 else 0.5
            recent_10_bars.append(round(bar_ratio, 4))

        # v2.1: 使用 10 根 K 线平均值作为主 buy_ratio (更稳定)
        # 之前只用最新一根 K 线，波动太大
        avg_buy_ratio = sum(recent_10_bars) / len(recent_10_bars) if recent_10_bars else 0.5

        return {
            "buy_ratio": round(avg_buy_ratio, 4),  # 使用 10 bar 平均值
            "latest_buy_ratio": round(latest_buy_ratio, 4),  # 保留最新 K 线值供参考
            "avg_trade_usdt": round(avg_trade_usdt, 2),
            "volume_usdt": round(quote_volume, 2),
            "trades_count": trades_count,
            "cvd_trend": cvd_trend,
            "recent_10_bars": recent_10_bars,
            "recent_10_bars_avg": round(avg_buy_ratio, 4),  # 明确标记这是平均值
            "data_source": "binance_raw",
        }

    def _process_dict_format(self, klines: List[Dict]) -> Dict[str, Any]:
        """
        处理本地 Dict 格式 (降级模式)

        注意: Dict 格式不包含 taker_buy_volume，无法计算真实订单流
        返回中性默认值，标记为降级数据源
        """
        self.logger.debug(
            "OrderFlowProcessor: Using Dict format (degraded mode, no order flow data)"
        )

        # 从 Dict 格式提取基础信息
        latest = klines[-1]
        volume = latest.get('volume', 0)

        return {
            "buy_ratio": 0.5,  # 中性值 (无数据)
            "avg_trade_usdt": 0,
            "volume_usdt": volume,  # 只有 volume 可用
            "trades_count": 0,
            "cvd_trend": "NEUTRAL",
            "recent_10_bars": [],
            "data_source": "local_dict",  # 标记为降级模式
            "_warning": "Dict format has no order flow data, using neutral values",
        }

    def _calculate_cvd_trend(self) -> str:
        """计算 CVD 趋势"""
        if len(self._cvd_history) < 5:
            return "NEUTRAL"

        recent_5 = self._cvd_history[-5:]
        avg_recent = sum(recent_5) / len(recent_5)

        if len(self._cvd_history) >= 10:
            older_5 = self._cvd_history[-10:-5]
            avg_older = sum(older_5) / len(older_5)

            if avg_recent > avg_older * 1.1:
                return "RISING"
            elif avg_recent < avg_older * 0.9:
                return "FALLING"

        return "NEUTRAL"

    def _default_result(self) -> Dict[str, Any]:
        """返回默认值"""
        return {
            "buy_ratio": 0.5,
            "avg_trade_usdt": 0,
            "volume_usdt": 0,
            "trades_count": 0,
            "cvd_trend": "NEUTRAL",
            "recent_10_bars": [],
            "data_source": "none",
        }

    def reset_cvd_history(self):
        """重置 CVD 历史 (用于测试或重启后)"""
        self._cvd_history = []
