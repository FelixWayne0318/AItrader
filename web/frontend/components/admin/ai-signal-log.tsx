"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Brain, TrendingUp, TrendingDown, Minus, Clock } from "lucide-react";

interface AISignal {
  id: string;
  time: string;
  signal: "BUY" | "SELL" | "HOLD";
  confidence: "HIGH" | "MEDIUM" | "LOW";
  reason?: string;
  symbol?: string;
}

interface AISignalLogProps {
  signals?: AISignal[];
}

export function AISignalLog({ signals }: AISignalLogProps) {
  const displaySignals = signals?.length ? signals : generateDemoSignals();

  const getSignalConfig = (signal: string) => {
    switch (signal) {
      case "BUY":
        return {
          icon: TrendingUp,
          color: "text-green-500",
          bg: "bg-green-500/10",
          border: "border-green-500/30",
        };
      case "SELL":
        return {
          icon: TrendingDown,
          color: "text-red-500",
          bg: "bg-red-500/10",
          border: "border-red-500/30",
        };
      default:
        return {
          icon: Minus,
          color: "text-yellow-500",
          bg: "bg-yellow-500/10",
          border: "border-yellow-500/30",
        };
    }
  };

  const getConfidenceColor = (confidence: string) => {
    switch (confidence) {
      case "HIGH":
        return "text-green-500 bg-green-500/10";
      case "MEDIUM":
        return "text-yellow-500 bg-yellow-500/10";
      default:
        return "text-muted-foreground bg-muted";
    }
  };

  return (
    <div className="space-y-3 max-h-80 overflow-y-auto pr-2">
      <AnimatePresence mode="popLayout">
        {displaySignals.map((signal, index) => {
          const config = getSignalConfig(signal.signal);
          const Icon = config.icon;

          return (
            <motion.div
              key={signal.id}
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              transition={{ duration: 0.2, delay: index * 0.05 }}
              className={`p-3 rounded-lg ${config.bg} border ${config.border}`}
            >
              <div className="flex items-start gap-3">
                {/* Icon */}
                <div className={`p-2 rounded-lg bg-background/50`}>
                  <Brain className={`h-4 w-4 ${config.color}`} />
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <div className="flex items-center gap-1.5">
                      <Icon className={`h-4 w-4 ${config.color}`} />
                      <span className={`font-medium ${config.color}`}>{signal.signal}</span>
                    </div>
                    {signal.symbol && (
                      <span className="text-xs text-muted-foreground">{signal.symbol}</span>
                    )}
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded ${getConfidenceColor(
                        signal.confidence
                      )}`}
                    >
                      {signal.confidence}
                    </span>
                  </div>
                  {signal.reason && (
                    <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                      {signal.reason}
                    </p>
                  )}
                </div>

                {/* Time */}
                <div className="flex items-center gap-1 text-xs text-muted-foreground whitespace-nowrap">
                  <Clock className="h-3 w-3" />
                  {formatTime(signal.time)}
                </div>
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>

      {!signals && (
        <p className="text-xs text-muted-foreground text-center py-2">
          Demo data - Connect to backend for live signals
        </p>
      )}
    </div>
  );
}

function formatTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function generateDemoSignals(): AISignal[] {
  const signals: ("BUY" | "SELL" | "HOLD")[] = ["BUY", "SELL", "HOLD"];
  const confidences: ("HIGH" | "MEDIUM" | "LOW")[] = ["HIGH", "MEDIUM", "LOW"];
  const reasons = [
    "Strong bullish momentum with RSI divergence",
    "Price approaching key resistance level",
    "Market sentiment neutral, waiting for confirmation",
    "Multiple indicators aligned for entry",
    "Risk/reward ratio favorable at current levels",
  ];

  const result: AISignal[] = [];
  const now = new Date();

  for (let i = 0; i < 5; i++) {
    const time = new Date(now.getTime() - i * 900000); // 15 min intervals
    result.push({
      id: `signal-${i}`,
      time: time.toISOString(),
      signal: signals[Math.floor(Math.random() * signals.length)],
      confidence: confidences[Math.floor(Math.random() * confidences.length)],
      reason: reasons[Math.floor(Math.random() * reasons.length)],
      symbol: "BTCUSDT",
    });
  }

  return result;
}
