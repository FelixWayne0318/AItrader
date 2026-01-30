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
  const [containerWidth, setContainerWidth] = useState(0);

  // Get container width for responsive rendering
  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setContainerWidth(containerRef.current.clientWidth);
      }
    };
    updateWidth();
    window.addEventListener('resize', updateWidth);
    return () => window.removeEventListener('resize', updateWidth);
  }, []);

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
  const chartHeight = showVolume ? height * 0.65 : height - 80;
  const volumeHeight = showVolume ? height * 0.15 : 0;
  const headerHeight = 70;
  const bottomPadding = 40;

  // Calculate price range
  const prices = candles.flatMap((c) => [c.high, c.low]);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const priceRange = maxPrice - minPrice || 1;

  // Calculate volume range
  const volumes = candles.map((c) => c.volume);
  const maxVolume = Math.max(...volumes);

  // Responsive candle count
  const effectiveCandleCount = containerWidth < 400 ? Math.min(candleCount, 20) : candleCount;
  const displayCandles = candles.slice(-effectiveCandleCount);

  // SVG dimensions
  const svgWidth = 100;
  const svgHeight = chartHeight + volumeHeight;

  const candleWidth = (svgWidth - 4) / effectiveCandleCount;
  const candleGap = candleWidth * 0.15;
  const candleBodyWidth = candleWidth - candleGap;

  // Convert price to Y coordinate
  const priceToY = useCallback(
    (price: number) => {
      const padding = 5;
      return (
        padding +
        ((maxPrice - price) / priceRange) * (chartHeight - 2 * padding)
      );
    },
    [maxPrice, priceRange, chartHeight]
  );

  // Convert volume to height
  const volumeToHeight = useCallback(
    (volume: number) => {
      return (volume / maxVolume) * (volumeHeight - 5);
    },
    [maxVolume, volumeHeight]
  );

  return (
    <div
      ref={containerRef}
      className="relative bg-gradient-to-b from-card/80 to-background rounded-xl border border-border/50 overflow-hidden"
      style={{ height, minHeight: height }}
    >
      {/* Glowing background effect */}
      <div className="absolute inset-0 opacity-30 pointer-events-none">
        <div className="absolute top-1/4 right-1/4 w-40 h-40 bg-primary/30 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 left-1/4 w-32 h-32 bg-accent/20 rounded-full blur-3xl" />
      </div>

      {/* Header */}
      <div className="relative p-3 sm:p-4 flex items-center justify-between z-10 bg-gradient-to-b from-card/90 to-transparent" style={{ height: headerHeight }}>
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-gradient-to-br from-[#f7931a] to-[#f39c12] flex items-center justify-center flex-shrink-0">
            <span className="text-white text-xs font-bold">₿</span>
          </div>
          <div>
            <h3 className="font-semibold text-foreground text-sm sm:text-base">{title}</h3>
            <p className="text-[10px] sm:text-xs text-muted-foreground">Perpetual</p>
          </div>
        </div>
        <div className="text-right">
          <motion.p
            key={currentPrice.toFixed(2)}
            initial={{ y: -10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            className="font-mono text-base sm:text-xl font-bold text-foreground"
          >
            ${currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </motion.p>
          <p
            className={`text-[10px] sm:text-xs font-medium ${
              priceChange >= 0 ? 'text-[hsl(var(--profit))]' : 'text-[hsl(var(--loss))]'
            }`}
          >
            {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
          </p>
        </div>
      </div>

      {/* Chart container */}
      <div className="relative" style={{ height: height - headerHeight - bottomPadding }}>
        {/* Price axis labels - positioned absolutely on the right */}
        <div
          className="absolute right-1 sm:right-2 top-0 bottom-0 flex flex-col justify-between py-2 z-10 pointer-events-none"
          style={{ width: 'auto' }}
        >
          <div className="text-[9px] sm:text-[10px] text-muted-foreground font-mono text-right whitespace-nowrap">
            ${maxPrice.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
          <div className="text-[9px] sm:text-[10px] text-muted-foreground font-mono text-right whitespace-nowrap">
            ${((maxPrice + minPrice) / 2).toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
          <div className="text-[9px] sm:text-[10px] text-muted-foreground font-mono text-right whitespace-nowrap">
            ${minPrice.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
        </div>

        {/* Candlestick chart SVG */}
        <svg
          className="absolute inset-0 w-full h-full"
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          preserveAspectRatio="xMidYMid meet"
        >
          {/* Grid lines */}
          <defs>
            <pattern id="candleGrid" width="10" height="10" patternUnits="userSpaceOnUse">
              <path
                d="M 10 0 L 0 0 0 10"
                fill="none"
                stroke="currentColor"
                strokeWidth="0.1"
                className="text-border"
                opacity="0.2"
              />
            </pattern>
            {/* Glow filter for the latest candle */}
            <filter id="candleGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="0.8" result="coloredBlur" />
              <feMerge>
                <feMergeNode in="coloredBlur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          <rect width={svgWidth} height={svgHeight} fill="url(#candleGrid)" />

          {/* Horizontal grid lines */}
          {[0.25, 0.5, 0.75].map((ratio) => (
            <line
              key={ratio}
              x1="0"
              y1={chartHeight * ratio}
              x2={svgWidth}
              y2={chartHeight * ratio}
              stroke="currentColor"
              strokeWidth="0.1"
              className="text-border"
              opacity="0.3"
              strokeDasharray="2 2"
            />
          ))}

          {/* Candles */}
          <AnimatePresence mode="popLayout">
            {displayCandles.map((candle, index) => {
              const x = 2 + index * candleWidth + candleGap / 2;
              const isUp = candle.close >= candle.open;
              const isLatest = index === displayCandles.length - 1;

              const bodyTop = priceToY(Math.max(candle.open, candle.close));
              const bodyBottom = priceToY(Math.min(candle.open, candle.close));
              const bodyHeight = Math.max(bodyBottom - bodyTop, 0.8);

              const wickTop = priceToY(candle.high);
              const wickBottom = priceToY(candle.low);

              return (
                <motion.g
                  key={candle.id}
                  initial={{ opacity: 0, x: candleWidth }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -candleWidth }}
                  transition={{ duration: 0.3 }}
                  filter={isLatest ? 'url(#candleGlow)' : undefined}
                >
                  {/* Wick */}
                  <motion.line
                    x1={x + candleBodyWidth / 2}
                    y1={wickTop}
                    x2={x + candleBodyWidth / 2}
                    y2={wickBottom}
                    stroke={isUp ? '#22c55e' : '#ef4444'}
                    strokeWidth="0.3"
                    initial={isLatest ? { y1: bodyTop, y2: bodyBottom } : undefined}
                    animate={{ y1: wickTop, y2: wickBottom }}
                    transition={{ duration: 0.5 }}
                  />
                  {/* Body */}
                  <motion.rect
                    x={x}
                    width={candleBodyWidth}
                    fill={isUp ? '#22c55e' : '#ef4444'}
                    fillOpacity={isUp ? 0.2 : 1}
                    stroke={isUp ? '#22c55e' : '#ef4444'}
                    strokeWidth="0.2"
                    rx="0.3"
                    initial={isLatest ? { y: bodyTop, height: 0.8 } : { y: bodyTop, height: bodyHeight }}
                    animate={{ y: bodyTop, height: bodyHeight }}
                    transition={{ duration: 0.5, ease: 'easeOut' }}
                  />
                  {/* Glow effect for latest candle */}
                  {isLatest && (
                    <motion.rect
                      x={x - 0.5}
                      y={bodyTop - 0.5}
                      width={candleBodyWidth + 1}
                      height={bodyHeight + 1}
                      fill="none"
                      stroke={isUp ? '#22c55e' : '#ef4444'}
                      strokeWidth="0.4"
                      rx="0.5"
                      opacity={0.5}
                      animate={{
                        opacity: [0.3, 0.6, 0.3],
                        strokeWidth: [0.4, 0.6, 0.4],
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
                {displayCandles.map((candle, index) => {
                  const x = 2 + index * candleWidth + candleGap / 2;
                  const isUp = candle.close >= candle.open;
                  const barHeight = volumeToHeight(candle.volume);

                  return (
                    <motion.rect
                      key={candle.id}
                      x={x}
                      y={volumeHeight - barHeight}
                      width={candleBodyWidth}
                      height={barHeight}
                      fill={isUp ? '#22c55e' : '#ef4444'}
                      opacity={0.3}
                      rx="0.3"
                      initial={{ height: 0, y: volumeHeight }}
                      animate={{ height: barHeight, y: volumeHeight - barHeight }}
                      exit={{ height: 0, y: volumeHeight }}
                      transition={{ duration: 0.3 }}
                    />
                  );
                })}
              </AnimatePresence>
            </g>
          )}
        </svg>
      </div>

      {/* Live indicator */}
      <div className="absolute bottom-2 sm:bottom-3 left-2 sm:left-3 flex items-center gap-1.5 sm:gap-2 z-10">
        <motion.div
          className="w-1.5 h-1.5 sm:w-2 sm:h-2 rounded-full bg-[#22c55e]"
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
        <span className="text-[10px] sm:text-xs text-muted-foreground">Live</span>
      </div>

      {/* Gradient overlay at bottom */}
      <div className="absolute bottom-0 left-0 right-0 h-16 sm:h-20 bg-gradient-to-t from-background/80 to-transparent pointer-events-none" />
    </div>
  );
}

// Hero version with larger size and more effects
export function HeroAnimatedCandlestick() {
  return (
    <div className="relative w-full max-w-3xl mx-auto px-2 sm:px-0">
      {/* Outer glow */}
      <div className="absolute -inset-2 sm:-inset-4 bg-gradient-to-r from-primary/20 via-accent/20 to-primary/20 rounded-2xl blur-xl opacity-50" />

      <AnimatedCandlestick
        height={280}
        candleCount={25}
        animationSpeed={1800}
        volatility={500}
        showVolume={true}
        title="BTC/USDT"
      />
    </div>
  );
}
