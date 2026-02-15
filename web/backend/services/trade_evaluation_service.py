"""
Trade Evaluation Service

Provides access to trade quality metrics from the AI trading system's
decision_memory (agents/multi_agent_analyzer.py).

Data Source: data/trading_memory.json
- Written by: MultiAgentAnalyzer.record_outcome()
- Contains: trade evaluations with grades, R/R, execution quality, etc.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from core.config import settings


class TradeEvaluationService:
    """Service for accessing trade evaluation data from decision_memory"""

    def __init__(self):
        self.memory_file = Path(settings.AITRADER_PATH) / "data" / "trading_memory.json"

    def _load_memory(self) -> List[Dict[str, Any]]:
        """
        Load decision_memory from file.

        Returns
        -------
        List[Dict]
            List of trade memory entries with evaluation data
        """
        if not self.memory_file.exists():
            return []

        try:
            with open(self.memory_file, 'r') as f:
                data = json.load(f)
                # Filter entries that have evaluation data
                return [m for m in data if m.get('evaluation')]
        except Exception:
            return []

    def get_evaluation_summary(self, days: Optional[int] = None) -> Dict[str, Any]:
        """
        Get aggregate trade evaluation statistics.

        Parameters
        ----------
        days : int, optional
            Number of days to look back (None = all trades)

        Returns
        -------
        Dict[str, Any]
            Aggregate statistics:
            - total_evaluated: Number of evaluated trades
            - grade_distribution: Dict of grade counts
            - direction_accuracy: Percentage of profitable trades
            - avg_winning_rr: Average R/R for winning trades
            - avg_execution_quality: Average execution quality (0-2)
            - exit_type_distribution: Dict of exit type counts
            - confidence_accuracy: Dict of confidence level win rates
            - avg_hold_duration_min: Average hold time in minutes
        """
        memories = self._load_memory()

        # Filter by date if specified
        if days is not None:
            cutoff = datetime.now() - timedelta(days=days)
            memories = [
                m for m in memories
                if self._parse_timestamp(m.get('timestamp')) >= cutoff
            ]

        if not memories:
            return self._empty_summary()

        evals = [m['evaluation'] for m in memories]
        total = len(evals)

        # Grade distribution
        grade_counts = {}
        for e in evals:
            g = e.get('grade', '?')
            grade_counts[g] = grade_counts.get(g, 0) + 1

        # Direction accuracy (win rate)
        correct = sum(1 for e in evals if e.get('direction_correct'))
        direction_accuracy = round(correct / total * 100, 1) if total > 0 else 0.0

        # Average R/R for winning trades
        profitable_rrs = [e.get('actual_rr', 0) for e in evals if e.get('direction_correct')]
        avg_winning_rr = round(sum(profitable_rrs) / len(profitable_rrs), 2) if profitable_rrs else 0.0

        # Average execution quality
        exec_quals = [e.get('execution_quality', 0) for e in evals if e.get('execution_quality', 0) > 0]
        avg_exec_quality = round(sum(exec_quals) / len(exec_quals), 2) if exec_quals else 0.0

        # Exit type distribution
        exit_types = {}
        for e in evals:
            et = e.get('exit_type', 'UNKNOWN')
            exit_types[et] = exit_types.get(et, 0) + 1

        # Confidence accuracy (win rate per confidence level)
        confidence_stats = {}
        for e in evals:
            conf = e.get('confidence', 'MEDIUM')
            if conf not in confidence_stats:
                confidence_stats[conf] = {'total': 0, 'wins': 0}
            confidence_stats[conf]['total'] += 1
            if e.get('direction_correct'):
                confidence_stats[conf]['wins'] += 1

        for conf, stats in confidence_stats.items():
            stats['accuracy'] = round(stats['wins'] / stats['total'] * 100, 1) if stats['total'] > 0 else 0.0

        # Average hold duration
        durations = [e.get('hold_duration_min', 0) for e in evals if e.get('hold_duration_min', 0) > 0]
        avg_hold_min = round(sum(durations) / len(durations)) if durations else 0

        # Grade quality score (A+ = 5, A = 4, B = 3, C = 2, D = 1, F = 0)
        grade_scores = {'A+': 5, 'A': 4, 'B': 3, 'C': 2, 'D': 1, 'F': 0}
        total_score = sum(grade_scores.get(e.get('grade', 'F'), 0) for e in evals)
        avg_grade_score = round(total_score / total, 2) if total > 0 else 0.0

        return {
            'total_evaluated': total,
            'grade_distribution': grade_counts,
            'direction_accuracy': direction_accuracy,
            'avg_winning_rr': avg_winning_rr,
            'avg_execution_quality': avg_exec_quality,
            'avg_grade_score': avg_grade_score,
            'exit_type_distribution': exit_types,
            'confidence_accuracy': confidence_stats,
            'avg_hold_duration_min': avg_hold_min,
            'last_updated': datetime.now().isoformat(),
        }

    def get_recent_trades(self, limit: int = 20, include_details: bool = False) -> List[Dict[str, Any]]:
        """
        Get recent trade evaluations.

        Parameters
        ----------
        limit : int
            Maximum number of trades to return
        include_details : bool
            If True, include full evaluation data (admin only)
            If False, exclude sensitive fields (public)

        Returns
        -------
        List[Dict]
            List of trade evaluations, newest first
        """
        memories = self._load_memory()

        # Sort by timestamp (newest first)
        memories.sort(key=lambda m: m.get('timestamp', ''), reverse=True)

        # Limit results
        memories = memories[:limit]

        if include_details:
            # Admin view - return full data
            return [
                {
                    **m['evaluation'],
                    'pnl': m.get('pnl', 0),
                    'conditions': m.get('conditions', ''),
                    'lesson': m.get('lesson', ''),
                    'timestamp': m.get('timestamp', ''),
                }
                for m in memories
            ]
        else:
            # Public view - sanitize sensitive data
            return [
                {
                    'grade': m['evaluation'].get('grade', '?'),
                    'planned_rr': m['evaluation'].get('planned_rr', 0),
                    'actual_rr': m['evaluation'].get('actual_rr', 0),
                    'execution_quality': m['evaluation'].get('execution_quality', 0),
                    'exit_type': m['evaluation'].get('exit_type', 'UNKNOWN'),
                    'confidence': m['evaluation'].get('confidence', 'MEDIUM'),
                    'hold_duration_min': m['evaluation'].get('hold_duration_min', 0),
                    'direction_correct': m['evaluation'].get('direction_correct', False),
                    'timestamp': m.get('timestamp', ''),
                }
                for m in memories
            ]

    def export_data(self, format: str = 'json', days: Optional[int] = None) -> Dict[str, Any]:
        """
        Export trade evaluation data for analysis.

        Parameters
        ----------
        format : str
            'json' or 'csv'
        days : int, optional
            Number of days to export (None = all)

        Returns
        -------
        Dict
            Export data with metadata
        """
        memories = self._load_memory()

        # Filter by date if specified
        if days is not None:
            cutoff = datetime.now() - timedelta(days=days)
            memories = [
                m for m in memories
                if self._parse_timestamp(m.get('timestamp')) >= cutoff
            ]

        if format == 'csv':
            # Convert to CSV-friendly flat structure
            csv_data = []
            for m in memories:
                eval_data = m.get('evaluation', {})
                row = {
                    'timestamp': m.get('timestamp', ''),
                    'decision': m.get('decision', ''),
                    'pnl': m.get('pnl', 0),
                    'grade': eval_data.get('grade', '?'),
                    'direction_correct': eval_data.get('direction_correct', False),
                    'entry_price': eval_data.get('entry_price', 0),
                    'exit_price': eval_data.get('exit_price', 0),
                    'planned_sl': eval_data.get('planned_sl', 0),
                    'planned_tp': eval_data.get('planned_tp', 0),
                    'planned_rr': eval_data.get('planned_rr', 0),
                    'actual_rr': eval_data.get('actual_rr', 0),
                    'execution_quality': eval_data.get('execution_quality', 0),
                    'exit_type': eval_data.get('exit_type', ''),
                    'confidence': eval_data.get('confidence', ''),
                    'position_size_pct': eval_data.get('position_size_pct', 0),
                    'hold_duration_min': eval_data.get('hold_duration_min', 0),
                    'conditions': m.get('conditions', ''),
                    'lesson': m.get('lesson', ''),
                }
                csv_data.append(row)

            return {
                'format': 'csv',
                'data': csv_data,
                'count': len(csv_data),
                'exported_at': datetime.now().isoformat(),
            }
        else:
            # JSON format - return full structure
            return {
                'format': 'json',
                'data': memories,
                'count': len(memories),
                'exported_at': datetime.now().isoformat(),
            }

    def _empty_summary(self) -> Dict[str, Any]:
        """Return empty summary structure when no data available"""
        return {
            'total_evaluated': 0,
            'grade_distribution': {},
            'direction_accuracy': 0.0,
            'avg_winning_rr': 0.0,
            'avg_execution_quality': 0.0,
            'avg_grade_score': 0.0,
            'exit_type_distribution': {},
            'confidence_accuracy': {},
            'avg_hold_duration_min': 0,
            'last_updated': datetime.now().isoformat(),
        }

    def _parse_timestamp(self, ts: Optional[str]) -> datetime:
        """Parse ISO timestamp string to datetime"""
        if not ts:
            return datetime.min
        try:
            # Handle both with and without microseconds
            for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
                try:
                    return datetime.fromisoformat(ts.replace('Z', ''))
                except ValueError:
                    continue
        except Exception:
            pass
        return datetime.min


# Singleton instance
_service_instance = None


def get_trade_evaluation_service() -> TradeEvaluationService:
    """Get singleton instance of TradeEvaluationService"""
    global _service_instance
    if _service_instance is None:
        _service_instance = TradeEvaluationService()
    return _service_instance
