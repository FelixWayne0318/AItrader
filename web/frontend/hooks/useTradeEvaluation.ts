import useSWR from 'swr';

interface GradeDistribution {
  "A+": number;
  A: number;
  B: number;
  C: number;
  D: number;
  F: number;
}

interface ExitTypeDistribution {
  TAKE_PROFIT: number;
  STOP_LOSS: number;
  MANUAL: number;
  REVERSAL: number;
}

interface ConfidenceStats {
  total: number;
  wins: number;
  accuracy: number;
}

interface ConfidenceAccuracy {
  HIGH: ConfidenceStats;
  MEDIUM: ConfidenceStats;
  LOW: ConfidenceStats;
}

export interface TradeEvaluationSummary {
  total_evaluated: number;
  grade_distribution: GradeDistribution;
  direction_accuracy: number;
  avg_winning_rr: number;
  avg_execution_quality: number;
  avg_grade_score: number;
  exit_type_distribution: ExitTypeDistribution;
  confidence_accuracy: ConfidenceAccuracy;
  avg_hold_duration_min: number;
  last_updated: string;
}

export interface TradeEvaluation {
  grade: string;
  planned_rr: number;
  actual_rr: number;
  execution_quality: number;
  exit_type: string;
  confidence: string;
  hold_duration_min: number;
  direction_correct: boolean;
  timestamp: string;
  // Admin only fields
  entry_price?: number;
  exit_price?: number;
  planned_sl?: number;
  planned_tp?: number;
  pnl?: number;
  position_size_pct?: number;
  conditions?: string;
  lesson?: string;
  decision?: string;
}

/**
 * Hook to fetch trade evaluation summary statistics
 * @param days Number of days to look back (0 = all time, default 30)
 */
export function useTradeEvaluationSummary(days: number = 30) {
  const { data, error, mutate } = useSWR<TradeEvaluationSummary>(
    `/api/public/trade-evaluation/summary?days=${days}`,
    { refreshInterval: 60000 }
  );

  return {
    summary: data,
    isLoading: !error && !data,
    isError: error,
    mutate,
  };
}

/**
 * Hook to fetch recent trade evaluations (public, sanitized data)
 * @param limit Number of trades to fetch (default 20, max 100)
 */
export function useRecentTrades(limit: number = 20) {
  const { data, error, mutate } = useSWR<TradeEvaluation[]>(
    `/api/public/trade-evaluation/recent?limit=${limit}`,
    { refreshInterval: 60000 }
  );

  return {
    trades: data || [],
    isLoading: !error && !data,
    isError: error,
    mutate,
  };
}

/**
 * Hook to fetch full trade evaluations (admin only, includes prices)
 * @param limit Number of trades to fetch (default 50, max 500)
 */
export function useFullTrades(limit: number = 50) {
  const { data, error, mutate } = useSWR<TradeEvaluation[]>(
    `/api/admin/trade-evaluation/full?limit=${limit}`,
    { refreshInterval: 60000 }
  );

  return {
    trades: data || [],
    isLoading: !error && !data,
    isError: error,
    mutate,
  };
}

/**
 * Hook to fetch admin summary (includes all data)
 * @param days Number of days to look back (0 = all time)
 */
export function useAdminSummary(days: number = 0) {
  const { data, error, mutate } = useSWR<TradeEvaluationSummary>(
    `/api/admin/trade-evaluation/summary-admin?days=${days}`,
    { refreshInterval: 60000 }
  );

  return {
    summary: data,
    isLoading: !error && !data,
    isError: error,
    mutate,
  };
}
