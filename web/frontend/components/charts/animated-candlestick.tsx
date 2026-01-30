'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface Candle {
  id: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  timestamp: number;
}

interface AnimatedCandlestickProps {
  height?: number;
  candleCount?: number;
  animationSpeed?: number; // ms between new candles
  volatility?: number;
  showVolume?: boolean;
  title?: string;
  symbol?: string;
}

function generateInitialCandles(count: number, basePrice: number = 45000): Candle[] {
  const candles: Candle[] = [];
  let price = basePrice;

  for (let i = 0; i < count; i++) {
    const change = (Math.random() - 0.5) * 500;
    const open = price;
    const close = price + change;
    const high = Math.max(open, close) + Math.random() * 150;
    const low = Math.min(open, close) - Math.random() * 150;
    const volume = 100 + Math.random() * 900;

    candles.push({
      id: i,
      open,
      high,
      low,
      close,
      volume,
      timestamp: Date.now() - (count - i) * 60000,
    });

    price = close;
  }

  return candles;
}

function generateNewCandle(lastCandle: Candle, volatility: number): Candle {
  const change = (Math.random() - 0.5) * volatility;
  const open = lastCandle.close;
  const close = open + change;
  const high = Math.max(open, close) + Math.random() * (volatility * 0.3);
  const low = Math.min(open, close) - Math.random() * (volatility * 0.3);
  const volume = 100 + Math.random() * 900;

  return {
    id: lastCandle.id + 1,
    open,
    high,
    low,
    close,
    volume,
    timestamp: Date.now(),
  };
}

export function AnimatedCandlestick({
  height = 300,
  candleCount = 30,
  animationSpeed = 2000,
  volatility = 500,
  showVolume = true,
  title = 'BTC/USDT',
  symbol,
}: AnimatedCandlestickProps) {
  const [candles, setCandles] = useState<Candle[]>(() =>
    generateInitialCandles(candleCount)
  );
  const [currentPrice, setCurrentPrice] = useState(0);
  const [priceChange, setPriceChange] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  // Update current price display
  useEffect(() => {
    if (candles.length > 0) {
      const lastCandle = candles[candles.length - 1];
      const firstCandle = candles[0];
      setCurrentPrice(lastCandle.close);
      setPriceChange(((lastCandle.close - firstCandle.open) / firstCandle.open) * 100);
    }
  }, [candles]);

  // Generate new candles periodically
  useEffect(() => {
    const interval = setInterval(() => {
      setCandles((prev) => {
        const newCandle = generateNewCandle(prev[prev.length - 1], volatility);
        return [...prev.slice(1), newCandle];
      });
    }, animationSpeed);

    return () => clearInterval(interval);
  }, [animationSpeed, volatility]);

  // Calculate chart dimensions
  const chartHeight = showVolume ? height * 0.7 : height - 20;
  const volumeHeight = showVolume ? height * 0.2 : 0;
  const padding = 10;

  // Calculate price range
  const prices = candles.flatMap((c) => [c.high, c.low]);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const priceRange = maxPrice - minPrice || 1;

  // Calculate volume range
  const volumes = candles.map((c) => c.volume);
  const maxVolume = Math.max(...volumes);

  // Convert price to Y coordinate
  const priceToY = useCallback(
    (price: number) => {
      return (
        padding +
        ((maxPrice - price) / priceRange) * (chartHeight - 2 * padding)
      );
    },
    [maxPrice, priceRange, chartHeight, padding]
  );

  // Convert volume to height
  const volumeToHeight = useCallback(
    (volume: number) => {
      return (volume / maxVolume) * (volumeHeight - 10);
    },
    [maxVolume, volumeHeight]
  );

  const candleWidth = (100 - 2) / candleCount; // percentage width
  const candleGap = candleWidth * 0.2;
  const candleBodyWidth = candleWidth - candleGap;

  return (
    <div
      ref={containerRef}
      className="relative bg-gradient-to-b from-card/80 to-background rounded-xl border border-border/50 overflow-hidden"
      style={{ height }}
    >
      {/* Glowing background effect */}
      <div className="absolute inset-0 opacity-30">
        <div className="absolute top-1/4 right-1/4 w-40 h-40 bg-primary/30 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 left-1/4 w-32 h-32 bg-accent/20 rounded-full blur-3xl" />
      </div>

      {/* Header */}
      <div className="absolute top-0 left-0 right-0 p-4 flex items-center justify-between z-10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#f7931a] to-[#f39c12] flex items-center justify-center">
            <span className="text-white text-xs font-bold">₿</span>
          </div>
          <div>
            <h3 className="font-semibold text-foreground">{title}</h3>
            <p className="text-xs text-muted-foreground">Perpetual</p>
          </div>
        </div>
        <div className="text-right">
          <motion.p
            key={currentPrice.toFixed(2)}
            initial={{ y: -10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            className="font-mono text-xl font-bold text-foreground"
          >
            ${currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </motion.p>
          <p
            className={`text-xs font-medium ${
              priceChange >= 0 ? 'text-[hsl(var(--profit))]' : 'text-[hsl(var(--loss))]'
            }`}
          >
            {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
          </p>
        </div>
      </div>

      {/* Price axis labels */}
      <div className="absolute right-2 top-16 bottom-20 flex flex-col justify-between text-[10px] text-muted-foreground font-mono z-10">
        <span>${maxPrice.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
        <span>${((maxPrice + minPrice) / 2).toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
        <span>${minPrice.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
      </div>

      {/* Candlestick chart */}
      <svg
        className="absolute inset-0"
        style={{ top: 60 }}
        viewBox={`0 0 100 ${height - 60}`}
        preserveAspectRatio="none"
      >
        {/* Grid lines */}
        <defs>
          <pattern id="grid" width="10" height="10" patternUnits="userSpaceOnUse">
            <path
              d="M 10 0 L 0 0 0 10"
              fill="none"
              stroke="hsl(var(--border))"
              strokeWidth="0.1"
              opacity="0.3"
            />
          </pattern>
          {/* Glow filter for the latest candle */}
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="1" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <rect width="100" height={height - 60} fill="url(#grid)" />

        {/* Candles */}
        <AnimatePresence mode="popLayout">
          {candles.map((candle, index) => {
            const x = 1 + index * candleWidth + candleGap / 2;
            const isUp = candle.close >= candle.open;
            const color = isUp ? 'hsl(var(--profit))' : 'hsl(var(--loss))';
            const isLatest = index === candles.length - 1;

            const bodyTop = priceToY(Math.max(candle.open, candle.close));
            const bodyBottom = priceToY(Math.min(candle.open, candle.close));
            const bodyHeight = Math.max(bodyBottom - bodyTop, 0.5);

            const wickTop = priceToY(candle.high);
            const wickBottom = priceToY(candle.low);

            return (
              <motion.g
                key={candle.id}
                initial={{ opacity: 0, x: candleWidth }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -candleWidth }}
                transition={{ duration: 0.3 }}
                filter={isLatest ? 'url(#glow)' : undefined}
              >
                {/* Wick */}
                <motion.line
                  x1={x + candleBodyWidth / 2}
                  y1={wickTop}
                  x2={x + candleBodyWidth / 2}
                  y2={wickBottom}
                  stroke={color}
                  strokeWidth="0.15"
                  initial={isLatest ? { y1: bodyTop, y2: bodyBottom } : undefined}
                  animate={{ y1: wickTop, y2: wickBottom }}
                  transition={{ duration: 0.5 }}
                />
                {/* Body */}
                <motion.rect
                  x={x}
                  width={candleBodyWidth}
                  fill={isUp ? 'transparent' : color}
                  stroke={color}
                  strokeWidth="0.15"
                  rx="0.2"
                  initial={isLatest ? { y: bodyTop, height: 0.5 } : { y: bodyTop, height: bodyHeight }}
                  animate={{ y: bodyTop, height: bodyHeight }}
                  transition={{ duration: 0.5, ease: 'easeOut' }}
                />
                {/* Glow effect for latest candle */}
                {isLatest && (
                  <motion.rect
                    x={x - 0.3}
                    y={bodyTop - 0.3}
                    width={candleBodyWidth + 0.6}
                    height={bodyHeight + 0.6}
                    fill="none"
                    stroke={color}
                    strokeWidth="0.3"
                    rx="0.3"
                    opacity={0.5}
                    animate={{
                      opacity: [0.3, 0.6, 0.3],
                      strokeWidth: [0.3, 0.5, 0.3],
                    }}
                    transition={{
                      duration: 1.5,
                      repeat: Infinity,
                      ease: 'easeInOut',
                    }}
                  />
                )}
              </motion.g>
            );
          })}
        </AnimatePresence>

        {/* Volume bars */}
        {showVolume && (
          <g transform={`translate(0, ${chartHeight + 5})`}>
            <AnimatePresence mode="popLayout">
              {candles.map((candle, index) => {
                const x = 1 + index * candleWidth + candleGap / 2;
                const isUp = candle.close >= candle.open;
                const color = isUp ? 'hsl(var(--profit))' : 'hsl(var(--loss))';
                const barHeight = volumeToHeight(candle.volume);

                return (
                  <motion.rect
                    key={candle.id}
                    x={x}
                    y={volumeHeight - barHeight - 5}
                    width={candleBodyWidth}
                    height={barHeight}
                    fill={color}
                    opacity={0.4}
                    rx="0.2"
                    initial={{ height: 0, y: volumeHeight - 5 }}
                    animate={{ height: barHeight, y: volumeHeight - barHeight - 5 }}
                    exit={{ height: 0, y: volumeHeight - 5 }}
                    transition={{ duration: 0.3 }}
                  />
                );
              })}
            </AnimatePresence>
          </g>
        )}
      </svg>

      {/* Live indicator */}
      <div className="absolute bottom-3 left-3 flex items-center gap-2">
        <motion.div
          className="w-2 h-2 rounded-full bg-[hsl(var(--profit))]"
          animate={{
            scale: [1, 1.3, 1],
            opacity: [1, 0.7, 1],
          }}
          transition={{
            duration: 1.5,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        />
        <span className="text-xs text-muted-foreground">Live</span>
      </div>

      {/* Gradient overlay at bottom */}
      <div className="absolute bottom-0 left-0 right-0 h-20 bg-gradient-to-t from-background/80 to-transparent pointer-events-none" />
    </div>
  );
}

// Hero version with larger size and more effects
export function HeroAnimatedCandlestick() {
  return (
    <div className="relative w-full max-w-3xl mx-auto">
      {/* Outer glow */}
      <div className="absolute -inset-4 bg-gradient-to-r from-primary/20 via-accent/20 to-primary/20 rounded-2xl blur-xl opacity-50" />

      <AnimatedCandlestick
        height={350}
        candleCount={40}
        animationSpeed={1500}
        volatility={600}
        showVolume={true}
        title="BTC/USDT"
      />
    </div>
  );
}
