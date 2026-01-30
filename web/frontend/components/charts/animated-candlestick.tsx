'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import useSWR from 'swr';

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
  showVolume?: boolean;
  title?: string;
  symbol?: string;
  interval?: string;
}

const fetcher = (url: string) => fetch(url).then((res) => res.json());

// Parse Binance kline data to Candle format
function parseKlineData(klines: any[]): Candle[] {
  if (!klines || !Array.isArray(klines)) return [];

  return klines.map((k, index) => ({
    id: index,
    open: parseFloat(k.open || k[1]),
    high: parseFloat(k.high || k[2]),
    low: parseFloat(k.low || k[3]),
    close: parseFloat(k.close || k[4]),
    volume: parseFloat(k.volume || k[5]),
    timestamp: k.open_time || k[0],
  }));
}

// Pure CSS animated candlestick chart with real data
export function AnimatedCandlestick({
  height = 300,
  candleCount = 30,
  showVolume = true,
  title = 'BTC/USDT',
  symbol = 'BTCUSDT',
  interval = '15m',
}: AnimatedCandlestickProps) {
  const [isClient, setIsClient] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Fetch real kline data from API
  const { data: klineData, error } = useSWR(
    isClient ? `/api/trading/klines/${symbol}?interval=${interval}&limit=${candleCount}` : null,
    fetcher,
    { refreshInterval: 10000 } // Refresh every 10 seconds
  );

  // Initialize client-side rendering
  useEffect(() => {
    setIsClient(true);
  }, []);

  // Parse kline data
  const candles = klineData?.klines ? parseKlineData(klineData.klines) : [];

  // Calculate current price and change
  const currentPrice = candles.length > 0 ? candles[candles.length - 1].close : 0;
  const firstPrice = candles.length > 0 ? candles[0].open : 0;
  const priceChange = firstPrice > 0 ? ((currentPrice - firstPrice) / firstPrice) * 100 : 0;

  // Calculate dimensions
  const headerHeight = 70;
  const bottomPadding = 40;
  const chartAreaHeight = height - headerHeight - bottomPadding;
  const candleChartHeight = showVolume ? chartAreaHeight * 0.75 : chartAreaHeight;
  const volumeChartHeight = showVolume ? chartAreaHeight * 0.20 : 0;

  // Calculate price range
  const prices = candles.length > 0 ? candles.flatMap((c) => [c.high, c.low]) : [0];
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const priceRange = maxPrice - minPrice || 1;

  // Calculate volume range
  const volumes = candles.length > 0 ? candles.map((c) => c.volume) : [0];
  const maxVolume = Math.max(...volumes);

  // Convert price to percentage from top
  const priceToPercent = useCallback(
    (price: number) => {
      return ((maxPrice - price) / priceRange) * 100;
    },
    [maxPrice, priceRange]
  );

  // Loading state
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
            <span className="text-sm">{error ? 'Failed to load data' : 'Loading real-time data...'}</span>
          </div>
        </div>
      </div>
    );
  }

  const candleWidth = 100 / candles.length;

  return (
    <div
      ref={containerRef}
      className="relative bg-gradient-to-b from-card/80 to-background rounded-xl border border-border/50 overflow-hidden"
      style={{ height, minHeight: height }}
    >
      {/* CSS for animations */}
      <style jsx>{`
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
            <p className="text-[10px] sm:text-xs text-muted-foreground">Perpetual · {interval}</p>
          </div>
        </div>
        <div className="text-right">
          <p className="font-mono text-base sm:text-xl font-bold text-foreground">
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
                className="relative"
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
              const barHeightPercent = maxVolume > 0 ? (candle.volume / maxVolume) * 100 : 0;

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
        <span className="text-[10px] sm:text-xs text-muted-foreground">Live · Real Data</span>
      </div>

      {/* Gradient overlay at bottom */}
      <div className="absolute bottom-0 left-0 right-0 h-16 sm:h-20 bg-gradient-to-t from-background/80 to-transparent pointer-events-none" />
    </div>
  );
}

// Hero version with larger size and outer glow
interface HeroAnimatedCandlestickProps {
  symbol?: string;
  interval?: string;
}

export function HeroAnimatedCandlestick({ symbol = 'BTCUSDT', interval = '15m' }: HeroAnimatedCandlestickProps) {
  return (
    <div className="relative w-full max-w-3xl mx-auto px-2 sm:px-0">
      {/* Outer glow */}
      <div className="absolute -inset-2 sm:-inset-4 bg-gradient-to-r from-primary/20 via-accent/20 to-primary/20 rounded-2xl blur-xl opacity-50" />

      <AnimatedCandlestick
        height={280}
        candleCount={30}
        showVolume={true}
        title="BTC/USDT"
        symbol={symbol}
        interval={interval}
      />
    </div>
  );
}
