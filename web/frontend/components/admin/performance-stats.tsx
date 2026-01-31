"use client";

import { motion } from "framer-motion";
import { DollarSign, TrendingUp, BarChart3, Percent } from "lucide-react";

interface PerformanceData {
  total_equity?: number;
  total_pnl?: number;
  total_pnl_percent?: number;
  total_trades?: number;
  winning_trades?: number;
  losing_trades?: number;
  avg_profit?: number;
  avg_loss?: number;
}

interface PerformanceStatsProps {
  data?: PerformanceData;
}

export function PerformanceStats({ data }: PerformanceStatsProps) {
  const stats = data || generateDemoData();

  const items = [
    {
      label: "Total Equity",
      value: `$${(stats.total_equity || 0).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`,
      icon: DollarSign,
      color: "text-primary",
      bgColor: "bg-primary/10",
    },
    {
      label: "Total P&L",
      value: `${(stats.total_pnl || 0) >= 0 ? "+" : ""}$${(stats.total_pnl || 0).toLocaleString(
        undefined,
        { minimumFractionDigits: 2, maximumFractionDigits: 2 }
      )}`,
      subValue: `${(stats.total_pnl_percent || 0) >= 0 ? "+" : ""}${(
        stats.total_pnl_percent || 0
      ).toFixed(2)}%`,
      icon: TrendingUp,
      color: (stats.total_pnl || 0) >= 0 ? "text-green-500" : "text-red-500",
      bgColor: (stats.total_pnl || 0) >= 0 ? "bg-green-500/10" : "bg-red-500/10",
    },
    {
      label: "Total Trades",
      value: (stats.total_trades || 0).toString(),
      subValue: `${stats.winning_trades || 0}W / ${stats.losing_trades || 0}L`,
      icon: BarChart3,
      color: "text-blue-500",
      bgColor: "bg-blue-500/10",
    },
    {
      label: "Win Rate",
      value: `${(
        ((stats.winning_trades || 0) / Math.max(stats.total_trades || 1, 1)) *
        100
      ).toFixed(1)}%`,
      subValue: `Avg: +$${(stats.avg_profit || 0).toFixed(2)} / -$${Math.abs(
        stats.avg_loss || 0
      ).toFixed(2)}`,
      icon: Percent,
      color:
        (stats.winning_trades || 0) / Math.max(stats.total_trades || 1, 1) > 0.5
          ? "text-green-500"
          : "text-yellow-500",
      bgColor:
        (stats.winning_trades || 0) / Math.max(stats.total_trades || 1, 1) > 0.5
          ? "bg-green-500/10"
          : "bg-yellow-500/10",
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {items.map((item, index) => {
        const Icon = item.icon;
        return (
          <motion.div
            key={item.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: index * 0.1 }}
            className="p-4 rounded-xl bg-card border border-border/50 hover:border-border transition-colors"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className={`p-2 rounded-lg ${item.bgColor}`}>
                <Icon className={`h-5 w-5 ${item.color}`} />
              </div>
              <span className="text-sm text-muted-foreground">{item.label}</span>
            </div>
            <p className={`text-2xl font-bold ${item.color}`}>{item.value}</p>
            {item.subValue && (
              <p className="text-xs text-muted-foreground mt-1">{item.subValue}</p>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}

function generateDemoData(): PerformanceData {
  const totalTrades = Math.floor(50 + Math.random() * 100);
  const winRate = 0.45 + Math.random() * 0.2;
  const winningTrades = Math.floor(totalTrades * winRate);
  const losingTrades = totalTrades - winningTrades;
  const avgProfit = 50 + Math.random() * 100;
  const avgLoss = 30 + Math.random() * 50;
  const totalPnl = winningTrades * avgProfit - losingTrades * avgLoss;
  const baseEquity = 10000;

  return {
    total_equity: baseEquity + totalPnl,
    total_pnl: totalPnl,
    total_pnl_percent: (totalPnl / baseEquity) * 100,
    total_trades: totalTrades,
    winning_trades: winningTrades,
    losing_trades: losingTrades,
    avg_profit: avgProfit,
    avg_loss: avgLoss,
  };
}
