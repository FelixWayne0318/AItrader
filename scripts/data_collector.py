"""
Data Collection Script for Strategy Evaluation

Implementation Plan Section 5.3:
Collects and persists data required for strategy evaluation according to EVALUATION_FRAMEWORK.md v3.0.1

Data collected:
- S/R predictions and actual results
- Trade records with full context
- AI decision logs (Bull/Bear/Judge)
- Market condition labels

Storage locations:
- data/sr_predictions.json
- data/trades.json
- logs/ai_decisions/
- logs/debates/
- logs/market_conditions/

See: docs/research/IMPLEMENTATION_PLAN.md Section 5.2-5.3
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
import threading

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataCollector:
    """
    Centralized data collection for strategy evaluation.

    Implements Section 5.3 of IMPLEMENTATION_PLAN.md:
    - Automatic persistence of prediction records
    - Trade records with full context
    - AI decision logging
    - Market condition tracking

    Thread-safe implementation using locks.
    """

    def __init__(self, base_dir: str = None):
        """
        Initialize data collector.

        Parameters
        ----------
        base_dir : str
            Base directory for data storage (default: project root)
        """
        if base_dir is None:
            # Find project root (where CLAUDE.md is)
            current = Path(__file__).resolve().parent
            while current != current.parent:
                if (current / "CLAUDE.md").exists():
                    base_dir = str(current)
                    break
                current = current.parent
            else:
                base_dir = str(Path(__file__).resolve().parent.parent)

        self.base_dir = Path(base_dir)

        # Data directories
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"

        # Specific directories
        self.ai_decisions_dir = self.logs_dir / "ai_decisions"
        self.debates_dir = self.logs_dir / "debates"
        self.market_conditions_dir = self.logs_dir / "market_conditions"

        # Data files
        self.sr_predictions_file = self.data_dir / "sr_predictions.json"
        self.trades_file = self.data_dir / "trades.json"

        # Thread safety
        self._lock = threading.Lock()

        # Initialize directories and files
        self._init_storage()

        logger.info(f"DataCollector initialized. Base dir: {self.base_dir}")

    def _init_storage(self):
        """Create necessary directories and files if they don't exist."""
        # Create directories
        for dir_path in [
            self.data_dir,
            self.ai_decisions_dir,
            self.debates_dir,
            self.market_conditions_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Initialize JSON files with empty arrays if they don't exist
        for json_file in [self.sr_predictions_file, self.trades_file]:
            if not json_file.exists():
                self._write_json(json_file, [])

    def _write_json(self, file_path: Path, data: Any):
        """Write data to JSON file with proper formatting."""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    def _read_json(self, file_path: Path) -> Any:
        """Read data from JSON file."""
        if not file_path.exists():
            return []
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _append_to_json(self, file_path: Path, record: Dict):
        """Append a record to a JSON array file."""
        with self._lock:
            data = self._read_json(file_path)
            data.append(record)
            self._write_json(file_path, data)

    # ================================================================
    # S/R Prediction Records (Section 5.2.2)
    # ================================================================

    def save_sr_prediction(
        self,
        sr_zones: List[Dict],
        signal: str,
        confidence: str,
        current_price: float,
        symbol: str = "BTCUSDT",
    ) -> str:
        """
        Save S/R prediction record for later accuracy evaluation.

        Parameters
        ----------
        sr_zones : List[Dict]
            S/R zones from SRZoneCalculator
        signal : str
            Trading signal (BUY/SELL/HOLD)
        confidence : str
            Confidence level (HIGH/MEDIUM/LOW)
        current_price : float
            Current market price at prediction time
        symbol : str
            Trading symbol

        Returns
        -------
        str
            Record ID for later update with actual result
        """
        record_id = f"sr_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{symbol}"

        record = {
            "id": record_id,
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "current_price": current_price,
            "signal": signal,
            "confidence": confidence,
            "sr_zones": sr_zones,
            "actual_result": None,  # To be filled later
            "price_after_1h": None,
            "price_after_4h": None,
            "price_after_24h": None,
            "sr_accuracy": None,  # Calculated after result is known
        }

        self._append_to_json(self.sr_predictions_file, record)
        logger.info(f"Saved S/R prediction: {record_id}")

        return record_id

    def update_sr_prediction_result(
        self,
        record_id: str,
        actual_result: str,
        price_after_1h: float = None,
        price_after_4h: float = None,
        price_after_24h: float = None,
    ):
        """
        Update S/R prediction with actual result.

        Parameters
        ----------
        record_id : str
            ID of the prediction record
        actual_result : str
            Actual outcome (PROFIT/LOSS/HOLD)
        price_after_*h : float
            Prices at different time intervals
        """
        with self._lock:
            data = self._read_json(self.sr_predictions_file)

            for record in data:
                if record.get("id") == record_id:
                    record["actual_result"] = actual_result
                    record["price_after_1h"] = price_after_1h
                    record["price_after_4h"] = price_after_4h
                    record["price_after_24h"] = price_after_24h
                    record["result_timestamp"] = datetime.now().isoformat()

                    # Calculate S/R accuracy
                    record["sr_accuracy"] = self._calculate_sr_accuracy(record)
                    break

            self._write_json(self.sr_predictions_file, data)
            logger.info(f"Updated S/R prediction result: {record_id} -> {actual_result}")

    def _calculate_sr_accuracy(self, record: Dict) -> Optional[bool]:
        """
        Calculate if S/R prediction was accurate.

        Based on EVALUATION_FRAMEWORK.md Section 三:
        - Zone touched + price bounced = True
        - Zone touched + price broke through = False
        """
        if record.get("actual_result") is None:
            return None

        # Simplified accuracy: Did the signal direction match the price movement?
        signal = record.get("signal")
        current_price = record.get("current_price", 0)
        price_after = record.get("price_after_4h") or record.get("price_after_1h")

        if not price_after or not current_price:
            return None

        price_change = (price_after - current_price) / current_price

        if signal == "BUY":
            return price_change > 0.005  # >0.5% gain
        elif signal == "SELL":
            return price_change < -0.005  # >0.5% drop
        else:
            return abs(price_change) < 0.01  # HOLD was correct if <1% move

    # ================================================================
    # Trade Records (Section 5.2.2)
    # ================================================================

    def save_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        signal_data: Dict,
        market_context: Dict = None,
    ) -> str:
        """
        Save trade record with full context.

        Parameters
        ----------
        symbol : str
            Trading symbol
        side : str
            LONG or SHORT
        entry_price : float
            Entry price
        quantity : float
            Position size
        signal_data : Dict
            AI signal data (Bull/Bear/Judge decisions)
        market_context : Dict
            Market conditions at trade time

        Returns
        -------
        str
            Trade ID for later update
        """
        trade_id = f"trade_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{symbol}"

        record = {
            "id": trade_id,
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "quantity": quantity,
            "notional_value": entry_price * quantity,
            "signal_data": signal_data,
            "market_context": market_context or {},
            # To be filled on close
            "exit_price": None,
            "exit_timestamp": None,
            "pnl": None,
            "pnl_percent": None,
            "duration_minutes": None,
            "exit_reason": None,  # TP/SL/MANUAL/SIGNAL
        }

        self._append_to_json(self.trades_file, record)
        logger.info(f"Saved trade: {trade_id} {side} {symbol} @ {entry_price}")

        return trade_id

    def update_trade_exit(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str = "SIGNAL",
    ):
        """
        Update trade record with exit information.

        Parameters
        ----------
        trade_id : str
            Trade ID
        exit_price : float
            Exit price
        exit_reason : str
            Reason for exit (TP/SL/MANUAL/SIGNAL)
        """
        with self._lock:
            data = self._read_json(self.trades_file)

            for record in data:
                if record.get("id") == trade_id:
                    record["exit_price"] = exit_price
                    record["exit_timestamp"] = datetime.now().isoformat()
                    record["exit_reason"] = exit_reason

                    # Calculate PnL
                    entry_price = record.get("entry_price", 0)
                    quantity = record.get("quantity", 0)
                    side = record.get("side", "LONG")

                    if side == "LONG":
                        pnl = (exit_price - entry_price) * quantity
                    else:
                        pnl = (entry_price - exit_price) * quantity

                    record["pnl"] = round(pnl, 4)
                    record["pnl_percent"] = round(pnl / (entry_price * quantity) * 100, 2) if entry_price * quantity > 0 else 0

                    # Calculate duration
                    entry_time = datetime.fromisoformat(record["timestamp"])
                    exit_time = datetime.now()
                    record["duration_minutes"] = int((exit_time - entry_time).total_seconds() / 60)

                    break

            self._write_json(self.trades_file, data)
            logger.info(f"Updated trade exit: {trade_id} @ {exit_price}, PnL: {record.get('pnl')}")

    # ================================================================
    # AI Decision Logs (Section 5.2.2)
    # ================================================================

    def save_ai_decision(
        self,
        signal: str,
        confidence: str,
        bull_argument: str,
        bear_argument: str,
        judge_decision: str,
        risk_evaluation: Dict,
        technical_data: Dict = None,
        sentiment_data: Dict = None,
    ):
        """
        Save AI decision log with full reasoning.

        Parameters
        ----------
        signal : str
            Final trading signal
        confidence : str
            Confidence level
        bull_argument : str
            Bull analyst argument
        bear_argument : str
            Bear analyst argument
        judge_decision : str
            Judge's decision and reasoning
        risk_evaluation : Dict
            Risk manager's evaluation
        technical_data : Dict
            Technical indicators at decision time
        sentiment_data : Dict
            Market sentiment data
        """
        timestamp = datetime.now()
        filename = f"decision_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"

        decision = {
            "timestamp": timestamp.isoformat(),
            "signal": signal,
            "confidence": confidence,
            "bull_argument": bull_argument,
            "bear_argument": bear_argument,
            "judge_decision": judge_decision,
            "risk_evaluation": risk_evaluation,
            "technical_data": technical_data or {},
            "sentiment_data": sentiment_data or {},
        }

        file_path = self.ai_decisions_dir / filename
        self._write_json(file_path, decision)
        logger.debug(f"Saved AI decision: {filename}")

    def save_debate_transcript(
        self,
        rounds: List[Dict],
        final_signal: str,
        symbol: str = "BTCUSDT",
    ):
        """
        Save Bull/Bear debate transcript.

        Parameters
        ----------
        rounds : List[Dict]
            List of debate rounds with Bull/Bear arguments
        final_signal : str
            Final signal after debate
        symbol : str
            Trading symbol
        """
        timestamp = datetime.now()
        filename = f"debate_{timestamp.strftime('%Y%m%d_%H%M%S')}_{symbol}.json"

        transcript = {
            "timestamp": timestamp.isoformat(),
            "symbol": symbol,
            "rounds": rounds,
            "final_signal": final_signal,
            "total_rounds": len(rounds),
        }

        file_path = self.debates_dir / filename
        self._write_json(file_path, transcript)
        logger.debug(f"Saved debate transcript: {filename}")

    # ================================================================
    # Market Condition Labels (Section 5.2.2)
    # ================================================================

    def save_market_condition(
        self,
        condition: str,
        indicators: Dict,
        symbol: str = "BTCUSDT",
    ):
        """
        Save market condition label for regime analysis.

        Parameters
        ----------
        condition : str
            Market condition (BULL/BEAR/SIDEWAYS/VOLATILE)
        indicators : Dict
            Indicators used to determine condition
        symbol : str
            Trading symbol
        """
        timestamp = datetime.now()
        filename = f"condition_{timestamp.strftime('%Y%m%d_%H%M%S')}_{symbol}.json"

        record = {
            "timestamp": timestamp.isoformat(),
            "symbol": symbol,
            "condition": condition,
            "indicators": indicators,
        }

        file_path = self.market_conditions_dir / filename
        self._write_json(file_path, record)
        logger.debug(f"Saved market condition: {condition}")

    # ================================================================
    # Statistics and Reports
    # ================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get collection statistics for monitoring.

        Returns
        -------
        Dict
            Statistics about collected data
        """
        sr_predictions = self._read_json(self.sr_predictions_file)
        trades = self._read_json(self.trades_file)

        # Count files in directories
        ai_decisions_count = len(list(self.ai_decisions_dir.glob("*.json")))
        debates_count = len(list(self.debates_dir.glob("*.json")))
        conditions_count = len(list(self.market_conditions_dir.glob("*.json")))

        # Calculate SR accuracy
        sr_with_results = [r for r in sr_predictions if r.get("sr_accuracy") is not None]
        sr_accurate = len([r for r in sr_with_results if r.get("sr_accuracy") is True])
        sr_accuracy = (sr_accurate / len(sr_with_results) * 100) if sr_with_results else 0

        # Calculate trade stats
        closed_trades = [t for t in trades if t.get("exit_price") is not None]
        winning_trades = len([t for t in closed_trades if t.get("pnl", 0) > 0])
        win_rate = (winning_trades / len(closed_trades) * 100) if closed_trades else 0

        return {
            "sr_predictions": {
                "total": len(sr_predictions),
                "with_results": len(sr_with_results),
                "accuracy": round(sr_accuracy, 1),
            },
            "trades": {
                "total": len(trades),
                "closed": len(closed_trades),
                "open": len(trades) - len(closed_trades),
                "win_rate": round(win_rate, 1),
            },
            "logs": {
                "ai_decisions": ai_decisions_count,
                "debates": debates_count,
                "market_conditions": conditions_count,
            },
            "storage": {
                "base_dir": str(self.base_dir),
                "data_dir": str(self.data_dir),
            },
        }


# Singleton instance
_data_collector = None


def get_data_collector() -> DataCollector:
    """Get singleton DataCollector instance."""
    global _data_collector
    if _data_collector is None:
        _data_collector = DataCollector()
    return _data_collector


# CLI interface for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Data Collector for Strategy Evaluation")
    parser.add_argument("--stats", action="store_true", help="Show collection statistics")
    parser.add_argument("--test", action="store_true", help="Run test data collection")

    args = parser.parse_args()

    collector = get_data_collector()

    if args.stats:
        stats = collector.get_statistics()
        print("\n=== Data Collection Statistics ===")
        print(json.dumps(stats, indent=2))

    if args.test:
        print("\n=== Running Test Data Collection ===")

        # Test S/R prediction
        sr_id = collector.save_sr_prediction(
            sr_zones=[{"price": 100000, "strength": "HIGH", "type": "RESISTANCE"}],
            signal="BUY",
            confidence="HIGH",
            current_price=99500,
            symbol="BTCUSDT",
        )
        print(f"Created S/R prediction: {sr_id}")

        # Test trade
        trade_id = collector.save_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=99500,
            quantity=0.01,
            signal_data={"signal": "BUY", "confidence": "HIGH"},
        )
        print(f"Created trade: {trade_id}")

        # Test AI decision
        collector.save_ai_decision(
            signal="BUY",
            confidence="HIGH",
            bull_argument="Strong support at 99000",
            bear_argument="Resistance at 100000",
            judge_decision="BUY with tight SL",
            risk_evaluation={"sl_price": 99000, "tp_price": 101000},
        )
        print("Saved AI decision")

        # Show stats
        stats = collector.get_statistics()
        print("\nUpdated Statistics:")
        print(json.dumps(stats, indent=2))
