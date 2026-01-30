'use client';

import { useEffect, useRef, useState, useCallback } from 'react';

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
  animationSpeed?: number;
  volatility?: number;
  showVolume?: boolean;
  title?: string;
}

function generateInitialCandles(count: number, basePrice: number = 105000): Candle[] {
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

// Pure CSS animated candlestick chart - no framer-motion for better mobile compatibility
export function AnimatedCandlestick({
  height = 300,
  candleCount = 30,
  animationSpeed = 2000,
  volatility = 500,
  showVolume = true,
  title = 'BTC/USDT',
}: AnimatedCandlestickProps) {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [currentPrice, setCurrentPrice] = useState(105000);
  const [priceChange, setPriceChange] = useState(0);
  const [isClient, setIsClient] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Initialize on client only to avoid hydration mismatch
  useEffect(() => {
    setIsClient(true);
    setCandles(generateInitialCandles(candleCount));
  }, [candleCount]);

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
    if (!isClient) return;

    const interval = setInterval(() => {
      setCandles((prev) => {
        if (prev.length === 0) return prev;
        const newCandle = generateNewCandle(prev[prev.length - 1], volatility);
        return [...prev.slice(1), newCandle];
      });
    }, animationSpeed);

    return () => clearInterval(interval);
  }, [animationSpeed, volatility, isClient]);

  // Calculate dimensions
  const headerHeight = 70;
  const bottomPadding = 40;
  const chartAreaHeight = height - headerHeight - bottomPadding;
  const candleChartHeight = showVolume ? chartAreaHeight * 0.75 : chartAreaHeight;
  const volumeChartHeight = showVolume ? chartAreaHeight * 0.20 : 0;

  // Calculate price range
  const prices = candles.length > 0 ? candles.flatMap((c) => [c.high, c.low]) : [105000, 104500];
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const priceRange = maxPrice - minPrice || 1;

  // Calculate volume range
  const volumes = candles.length > 0 ? candles.map((c) => c.volume) : [500];
  const maxVolume = Math.max(...volumes);

  // Convert price to percentage from top
  const priceToPercent = useCallback(
    (price: number) => {
      return ((maxPrice - price) / priceRange) * 100;
    },
    [maxPrice, priceRange]
  );

  // Don't render chart until client-side
  if (!isClient || candles.length === 0) {
    return (
      <div
        ref={containerRef}
        className="relative bg-gradient-to-b from-card/80 to-background rounded-xl border border-border/50 overflow-hidden"
        style={{ height, minHeight: height }}
      >
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="flex items-center gap-2 text-muted-foreground">
            <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
            <span className="text-sm">Loading chart...</span>
          </div>
        </div>
      </div>
    );
  }

  const candleWidth = 100 / candleCount;

  return (
    <div
      ref={containerRef}
      className="relative bg-gradient-to-b from-card/80 to-background rounded-xl border border-border/50 overflow-hidden"
      style={{ height, minHeight: height }}
    >
      {/* CSS for animations */}
      <style jsx>{`
        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translateX(10px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
        @keyframes pulse {
          0%, 100% {
            opacity: 0.5;
            box-shadow: 0 0 4px currentColor;
          }
          50% {
            opacity: 0.8;
            box-shadow: 0 0 8px currentColor;
          }
        }
        @keyframes priceUpdate {
          from {
            opacity: 0;
            transform: translateY(-5px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .candle-enter {
          animation: slideIn 0.3s ease-out forwards;
        }
        .price-animate {
          animation: priceUpdate 0.3s ease-out;
        }
        .glow-pulse {
          animation: pulse 1.5s ease-in-out infinite;
        }
      `}</style>

      {/* Glowing background effect */}
      <div className="absolute inset-0 opacity-30 pointer-events-none">
        <div className="absolute top-1/4 right-1/4 w-40 h-40 bg-primary/30 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 left-1/4 w-32 h-32 bg-accent/20 rounded-full blur-3xl" />
      </div>

      {/* Header */}
      <div
        className="relative p-3 sm:p-4 flex items-center justify-between z-10 bg-gradient-to-b from-card/90 to-transparent"
        style={{ height: headerHeight }}
      >
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
          <p
            key={currentPrice.toFixed(0)}
            className="font-mono text-base sm:text-xl font-bold text-foreground price-animate"
          >
            ${currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
          <p
            className={`text-[10px] sm:text-xs font-medium ${
              priceChange >= 0 ? 'text-green-500' : 'text-red-500'
            }`}
          >
            {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
          </p>
        </div>
      </div>

      {/* Chart container */}
      <div className="relative px-2" style={{ height: chartAreaHeight }}>
        {/* Price axis labels */}
        <div className="absolute right-1 sm:right-2 top-0 flex flex-col justify-between z-10 pointer-events-none" style={{ height: candleChartHeight }}>
          <span className="text-[9px] sm:text-[10px] text-muted-foreground font-mono">
            ${maxPrice.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </span>
          <span className="text-[9px] sm:text-[10px] text-muted-foreground font-mono">
            ${((maxPrice + minPrice) / 2).toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </span>
          <span className="text-[9px] sm:text-[10px] text-muted-foreground font-mono">
            ${minPrice.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </span>
        </div>

        {/* Grid lines */}
        <div className="absolute inset-x-2 top-0" style={{ height: candleChartHeight }}>
          {[0, 25, 50, 75, 100].map((percent) => (
            <div
              key={percent}
              className="absolute w-full border-t border-border/20 border-dashed"
              style={{ top: `${percent}%` }}
            />
          ))}
        </div>

        {/* Candlesticks using divs */}
        <div className="absolute inset-x-2 top-0 flex" style={{ height: candleChartHeight }}>
          {candles.map((candle, index) => {
            const isUp = candle.close >= candle.open;
            const isLatest = index === candles.length - 1;

            const highPercent = priceToPercent(candle.high);
            const lowPercent = priceToPercent(candle.low);
            const bodyTopPercent = priceToPercent(Math.max(candle.open, candle.close));
            const bodyBottomPercent = priceToPercent(Math.min(candle.open, candle.close));
            const bodyHeightPercent = Math.max(bodyBottomPercent - bodyTopPercent, 0.5);

            return (
              <div
                key={candle.id}
                className={`relative ${isLatest ? 'candle-enter' : ''}`}
                style={{ width: `${candleWidth}%`, height: '100%' }}
              >
                {/* Wick */}
                <div
                  className="absolute left-1/2 -translate-x-1/2"
                  style={{
                    top: `${highPercent}%`,
                    height: `${lowPercent - highPercent}%`,
                    width: '1px',
                    backgroundColor: isUp ? '#22c55e' : '#ef4444',
                    transition: 'all 0.3s ease-out',
                  }}
                />
                {/* Body */}
                <div
                  className={`absolute left-1/2 -translate-x-1/2 rounded-sm ${isLatest ? 'glow-pulse' : ''}`}
                  style={{
                    top: `${bodyTopPercent}%`,
                    height: `${bodyHeightPercent}%`,
                    width: '60%',
                    minHeight: '2px',
                    backgroundColor: isUp ? 'rgba(34, 197, 94, 0.3)' : '#ef4444',
                    border: `1px solid ${isUp ? '#22c55e' : '#ef4444'}`,
                    transition: 'all 0.3s ease-out',
                    color: isUp ? '#22c55e' : '#ef4444',
                  }}
                />
              </div>
            );
          })}
        </div>

        {/* Volume bars */}
        {showVolume && (
          <div
            className="absolute inset-x-2 bottom-0 flex items-end"
            style={{ height: volumeChartHeight }}
          >
            {candles.map((candle, index) => {
              const isUp = candle.close >= candle.open;
              const barHeightPercent = (candle.volume / maxVolume) * 100;

              return (
                <div
                  key={candle.id}
                  className="relative"
                  style={{ width: `${candleWidth}%`, height: '100%' }}
                >
                  <div
                    className="absolute bottom-0 left-1/2 -translate-x-1/2 rounded-t-sm"
                    style={{
                      width: '60%',
                      height: `${barHeightPercent}%`,
                      backgroundColor: isUp ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)',
                      transition: 'height 0.3s ease-out',
                    }}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Live indicator */}
      <div className="absolute bottom-2 sm:bottom-3 left-2 sm:left-3 flex items-center gap-1.5 sm:gap-2 z-10">
        <div className="w-1.5 h-1.5 sm:w-2 sm:h-2 rounded-full bg-green-500 animate-pulse" />
        <span className="text-[10px] sm:text-xs text-muted-foreground">Live</span>
      </div>

      {/* Gradient overlay at bottom */}
      <div className="absolute bottom-0 left-0 right-0 h-16 sm:h-20 bg-gradient-to-t from-background/80 to-transparent pointer-events-none" />
    </div>
  );
}

// Hero version with larger size and outer glow
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
