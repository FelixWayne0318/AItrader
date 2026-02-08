"""Unit tests for DeepSeek bracket order helpers."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import Mock
import enum
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _ensure_nautilus_stub() -> None:
    """Create minimal nautilus_trader stubs so strategy module can import."""
    try:
        import nautilus_trader  # type: ignore
        return
    except ModuleNotFoundError:
        pass

    base = types.ModuleType("nautilus_trader")
    sys.modules["nautilus_trader"] = base

    config_mod = types.ModuleType("nautilus_trader.config")
    class StrategyConfig:  # noqa: D401 - minimal stub
        """Stub StrategyConfig."""
        def __init_subclass__(cls, **kwargs: Any) -> None:
            return
    config_mod.StrategyConfig = StrategyConfig
    sys.modules["nautilus_trader.config"] = config_mod

    trading_mod = types.ModuleType("nautilus_trader.trading")
    sys.modules["nautilus_trader.trading"] = trading_mod

    trade_strategy_mod = types.ModuleType("nautilus_trader.trading.strategy")
    class Strategy:
        def __init__(self, config: StrategyConfig | None = None) -> None:
            self.config = config
    trade_strategy_mod.Strategy = Strategy
    sys.modules["nautilus_trader.trading.strategy"] = trade_strategy_mod

    model_mod = types.ModuleType("nautilus_trader.model")
    sys.modules["nautilus_trader.model"] = model_mod

    data_mod = types.ModuleType("nautilus_trader.model.data")
    class Bar:
        def __init__(self, open_price, high, low, close, volume):
            self.open = open_price
            self.high = high
            self.low = low
            self.close = close
            self.volume = volume
    class BarType:
        @classmethod
        def from_str(cls, value: str) -> str:
            return value
    data_mod.Bar = Bar
    data_mod.BarType = BarType
    sys.modules["nautilus_trader.model.data"] = data_mod

    enums_mod = types.ModuleType("nautilus_trader.model.enums")
    OrderSide = enum.Enum("OrderSide", "BUY SELL")
    TimeInForce = enum.Enum("TimeInForce", "GTC FOK IOC")
    PositionSide = enum.Enum("PositionSide", "LONG SHORT")
    PriceType = enum.Enum("PriceType", "LAST MARK")
    TriggerType = enum.Enum("TriggerType", "LAST INDEX MARK DEFAULT")
    OrderType = enum.Enum("OrderType", "MARKET LIMIT STOP_MARKET")
    enums_mod.OrderSide = OrderSide
    enums_mod.TimeInForce = TimeInForce
    enums_mod.PositionSide = PositionSide
    enums_mod.PriceType = PriceType
    enums_mod.TriggerType = TriggerType
    enums_mod.OrderType = OrderType
    sys.modules["nautilus_trader.model.enums"] = enums_mod

    identifiers_mod = types.ModuleType("nautilus_trader.model.identifiers")
    class InstrumentId(str):
        @classmethod
        def from_str(cls, value: str) -> "InstrumentId":
            return cls(value)
    identifiers_mod.InstrumentId = InstrumentId
    sys.modules["nautilus_trader.model.identifiers"] = identifiers_mod

    instruments_mod = types.ModuleType("nautilus_trader.model.instruments")
    class Instrument:
        def make_qty(self, quantity: float) -> Decimal:
            return Decimal(str(quantity))
        def make_price(self, price: float) -> Decimal:
            return Decimal(str(price))
    instruments_mod.Instrument = Instrument
    sys.modules["nautilus_trader.model.instruments"] = instruments_mod

    position_mod = types.ModuleType("nautilus_trader.model.position")
    class Position:
        pass
    position_mod.Position = Position
    sys.modules["nautilus_trader.model.position"] = position_mod

    orders_mod = types.ModuleType("nautilus_trader.model.orders")
    class MarketOrder:
        pass
    orders_mod.MarketOrder = MarketOrder
    sys.modules["nautilus_trader.model.orders"] = orders_mod

    indicators_mod = types.ModuleType("nautilus_trader.indicators")

    class _Indicator:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.value = 0.0
            self.initialized = False

        def update_raw(self, value: float) -> None:
            self.value = value
            self.initialized = True

    class SimpleMovingAverage(_Indicator):
        pass

    class ExponentialMovingAverage(_Indicator):
        pass

    class RelativeStrengthIndex(_Indicator):
        pass

    class MovingAverageConvergenceDivergence(_Indicator):
        pass

    class AverageTrueRange(_Indicator):
        pass

    indicators_mod.SimpleMovingAverage = SimpleMovingAverage
    indicators_mod.ExponentialMovingAverage = ExponentialMovingAverage
    indicators_mod.RelativeStrengthIndex = RelativeStrengthIndex
    indicators_mod.MovingAverageConvergenceDivergence = MovingAverageConvergenceDivergence
    indicators_mod.AverageTrueRange = AverageTrueRange
    sys.modules["nautilus_trader.indicators"] = indicators_mod

    openai_mod = types.ModuleType("openai")

    class OpenAI:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=self._create_response)
            )

        def _create_response(self, *args: Any, **kwargs: Any) -> Any:
            content = (
                '{\"signal\":\"HOLD\",\"confidence\":\"LOW\",\"reason\":\"stub\",'
                '\"stop_loss\":0,\"take_profit\":0}'
            )
            message = types.SimpleNamespace(content=content)
            choice = types.SimpleNamespace(message=message)
            return types.SimpleNamespace(choices=[choice])

    openai_mod.OpenAI = OpenAI
    sys.modules["openai"] = openai_mod


_ensure_nautilus_stub()

from nautilus_trader.model.enums import OrderSide, OrderType  # type: ignore
from strategy.deepseek_strategy import DeepSeekAIStrategy


class DummyInstrument:
    def make_qty(self, quantity: float) -> Decimal:
        return Decimal(str(quantity))

    def make_price(self, price: float) -> Decimal:
        return Decimal(str(price))


class DummyOrderList:
    def __init__(self) -> None:
        self.orders = [SimpleNamespace(order_type=OrderType.STOP_MARKET, client_order_id="SL-order")]
        self.id = "order-list-001"


class DummyOrderFactory:
    def __init__(self) -> None:
        self.kwargs: Dict[str, Any] | None = None

    def bracket(self, **kwargs: Any) -> DummyOrderList:
        self.kwargs = kwargs
        return DummyOrderList()


class DummyCache:
    def __init__(self, bars: List[Any]) -> None:
        self._bars = bars

    def bars(self, bar_type: Any) -> List[Any]:
        return self._bars


class DummyLogger:
    def info(self, *args: Any, **kwargs: Any) -> None:
        pass

    def warning(self, *args: Any, **kwargs: Any) -> None:
        pass

    def error(self, *args: Any, **kwargs: Any) -> None:
        pass

    def debug(self, *args: Any, **kwargs: Any) -> None:
        pass


def _make_strategy_stub() -> DeepSeekAIStrategy:
    strategy = DeepSeekAIStrategy.__new__(DeepSeekAIStrategy)
    strategy.position_config = {
        "min_trade_amount": 0.001,
        "adjustment_threshold": 0.0,
    }
    strategy.enable_auto_sl_tp = True
    strategy.sl_use_support_resistance = True
    strategy.sl_buffer_pct = 0.001
    strategy.tp_pct_config = {"HIGH": 0.03, "MEDIUM": 0.02, "LOW": 0.01}
    strategy.latest_signal_data = {"confidence": "HIGH"}
    strategy.latest_technical_data = {"support": 950.0, "resistance": 1050.0}
    strategy.latest_price_data = {"price": 1000.0}
    strategy.indicator_manager = SimpleNamespace(recent_bars=[])
    strategy.cache = DummyCache([])
    strategy.bar_type = "BTC-BARS"
    strategy.order_factory = DummyOrderFactory()
    strategy.submit_order_list = Mock()
    strategy._submit_order = Mock()
    strategy.instrument = DummyInstrument()
    strategy.instrument_id = "BTCUSDT-PERP.BINANCE"
    strategy.enable_trailing_stop = False
    strategy.trailing_stop_state = {}
    strategy.log = DummyLogger()
    # v4.11: Additional attributes needed for _validate_sltp_for_entry
    strategy.binance_account = None
    strategy.telegram_bot = None
    strategy.enable_telegram = False
    strategy._last_signal_status = {}
    return strategy


def test_submit_bracket_order_uses_latest_price_data() -> None:
    """v4.11: Bracket order now uses _validate_sltp_for_entry (unified validation)."""
    strategy = _make_strategy_stub()

    strategy._submit_bracket_order(OrderSide.BUY, 0.01)

    assert strategy.order_factory.kwargs is not None, "Bracket call should occur"
    tp_price = strategy.order_factory.kwargs["tp_price"]
    sl_trigger = strategy.order_factory.kwargs["sl_trigger_price"]

    # SL: Support-based ($950 - 0.1% buffer) = $949.05
    assert sl_trigger == Decimal("949.05")
    # TP: Resistance-based with R/R >= 1.5:1 adjustment (via calculate_technical_sltp)
    assert float(tp_price) > 1050.0, f"TP should be above resistance, got {tp_price}"
    strategy.submit_order_list.assert_called_once()
    strategy._submit_order.assert_not_called()


def test_submit_bracket_order_blocks_when_price_missing() -> None:
    """v3.18 + v4.11: No fallback to unprotected market order when price is missing."""
    strategy = _make_strategy_stub()
    strategy.latest_price_data = {}
    strategy.indicator_manager.recent_bars = []
    strategy.cache = DummyCache([])

    strategy._submit_bracket_order(OrderSide.SELL, 0.02)

    # v3.18: Should NOT submit any order (no unprotected market orders)
    strategy._submit_order.assert_not_called()
    assert strategy.order_factory.kwargs is None


if __name__ == "__main__":
    test_submit_bracket_order_uses_latest_price_data()
    test_submit_bracket_order_blocks_when_price_missing()
    print("✅ bracket order tests passed")
