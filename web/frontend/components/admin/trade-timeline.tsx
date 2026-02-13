"use client";

import { motion, AnimatePresence } from "framer-motion";
import { ArrowUpRight, ArrowDownRight, Clock } from "lucide-react";

interface Trade {
  id: string;
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  price: number;
  pnl?: number;
  time: string;
}

interface TradeTimelineProps {
  trades?: Trade[];
}

export function TradeTimeline({ trades }: TradeTimelineProps) {
  const displayTrades = trades?.length ? trades : generateDemoTrades();

  return (
    <div className="space-y-3 max-h-80 overflow-y-auto pr-2">
      <AnimatePresence mode="popLayout">
        {displayTrades.map((trade, index) => (
          <motion.div
            key={trade.id}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
            transition={{ duration: 0.2, delay: index * 0.05 }}
            className="flex items-center gap-3 p-3 rounded-lg bg-muted/30 border border-border/50 hover:border-border transition-colors"
          >
            {/* Side indicator */}
            <div
              className={`p-2 rounded-lg ${
                trade.side === "BUY"
                  ? "bg-green-500/10 text-green-500"
                  : "bg-red-500/10 text-red-500"
              }`}
            >
              {trade.side === "BUY" ? (
                <ArrowUpRight className="h-4 w-4" />
              ) : (
                <ArrowDownRight className="h-4 w-4" />
              )}
            </div>

            {/* Trade info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium">{trade.symbol}</span>
                <span
                  className={`text-xs px-1.5 py-0.5 rounded ${
                    trade.side === "BUY"
                      ? "bg-green-500/10 text-green-500"
                      : "bg-red-500/10 text-red-500"
                  }`}
                >
                  {trade.side}
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>{trade.quantity} @ ${trade.price.toLocaleString()}</span>
              </div>
            </div>

            {/* PnL and time */}
            <div className="text-right">
              {trade.pnl !== undefined && (
                <p
                  className={`font-medium ${
                    trade.pnl >= 0 ? "text-green-500" : "text-red-500"
                  }`}
                >
                  {trade.pnl >= 0 ? "+" : ""}${trade.pnl.toFixed(2)}
                </p>
              )}
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Clock className="h-3 w-3" />
                {formatTime(trade.time)}
              </div>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>

      {!trades && (
        <p className="text-xs text-muted-foreground text-center py-2">
          Demo data - Connect to backend for live trades
        </p>
      )}
    </div>
  );
}

function formatTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(minutes / 60);

  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return date.toLocaleDateString();
}

function generateDemoTrades(): Trade[] {
  const symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
  const trades: Trade[] = [];
  const now = new Date();

  for (let i = 0; i < 5; i++) {
    const symbol = symbols[Math.floor(Math.random() * symbols.length)];
    const side = Math.random() > 0.5 ? "BUY" : "SELL";
    const price = symbol === "BTCUSDT" ? 95000 + Math.random() * 5000 : symbol === "ETHUSDT" ? 3200 + Math.random() * 200 : 180 + Math.random() * 20;
    const quantity = Math.random() * 0.5 + 0.01;
    const pnl = (Math.random() - 0.4) * 100;
    const time = new Date(now.getTime() - i * 3600000 * Math.random() * 5);

    trades.push({
      id: `trade-${i}`,
      symbol,
      side: side as "BUY" | "SELL",
      quantity: Math.round(quantity * 1000) / 1000,
      price: Math.round(price * 100) / 100,
      pnl: Math.round(pnl * 100) / 100,
      time: time.toISOString(),
    });
  }

  return trades;
}
