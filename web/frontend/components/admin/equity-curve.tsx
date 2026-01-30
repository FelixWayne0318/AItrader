"use client";

import { useEffect, useRef } from "react";
import { motion } from "framer-motion";

interface EquityDataPoint {
  time: string;
  value: number;
}

interface EquityCurveProps {
  data?: EquityDataPoint[];
}

export function EquityCurve({ data }: EquityCurveProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Dynamic import lightweight-charts only on client
    import("lightweight-charts").then(({ createChart, ColorType }) => {
      if (!containerRef.current) return;

      // Clear previous chart
      if (chartRef.current) {
        chartRef.current.remove();
      }

      const chart = createChart(containerRef.current, {
        layout: {
          background: { type: ColorType.Solid, color: "transparent" },
          textColor: "hsl(var(--muted-foreground))",
        },
        grid: {
          vertLines: { color: "hsl(var(--border) / 0.3)" },
          horzLines: { color: "hsl(var(--border) / 0.3)" },
        },
        width: containerRef.current.clientWidth,
        height: 240,
        rightPriceScale: {
          borderColor: "hsl(var(--border))",
        },
        timeScale: {
          borderColor: "hsl(var(--border))",
          timeVisible: true,
        },
      });

      chartRef.current = chart;

      const areaSeries = chart.addAreaSeries({
        lineColor: "hsl(var(--primary))",
        topColor: "hsl(var(--primary) / 0.4)",
        bottomColor: "hsl(var(--primary) / 0.05)",
        lineWidth: 2,
      });

      // Use provided data or generate demo data
      const chartData = data?.length
        ? data.map((d) => ({ time: d.time, value: d.value }))
        : generateDemoData();

      areaSeries.setData(chartData as any);
      chart.timeScale().fitContent();

      // Handle resize
      const handleResize = () => {
        if (containerRef.current && chartRef.current) {
          chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
        }
      };

      window.addEventListener("resize", handleResize);
      return () => {
        window.removeEventListener("resize", handleResize);
        if (chartRef.current) {
          chartRef.current.remove();
          chartRef.current = null;
        }
      };
    });
  }, [data]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div ref={containerRef} className="w-full" />
      {!data && (
        <p className="text-xs text-muted-foreground text-center mt-2">
          Demo data - Connect to backend for live data
        </p>
      )}
    </motion.div>
  );
}

function generateDemoData() {
  const data = [];
  let value = 1000;
  const now = new Date();

  for (let i = 30; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);
    const change = (Math.random() - 0.45) * 50;
    value = Math.max(500, value + change);
    data.push({
      time: date.toISOString().split("T")[0],
      value: Math.round(value * 100) / 100,
    });
  }

  return data;
}
