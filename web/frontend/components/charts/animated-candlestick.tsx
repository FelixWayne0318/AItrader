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

// DipSway-style animated candlestick chart with real data
export function AnimatedCandlestick({
  height = 320,
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
    { refreshInterval: 10000 }
  );

  useEffect(() => {
    setIsClient(true);
  }, []);

  const candles = klineData?.klines ? parseKlineData(klineData.klines) : [];

  const currentPrice = candles.length > 0 ? candles[candles.length - 1].close : 0;
  const firstPrice = candles.length > 0 ? candles[0].open : 0;
  const priceChange = firstPrice > 0 ? ((currentPrice - firstPrice) / firstPrice) * 100 : 0;

  const headerHeight = 72;
  const bottomPadding = 36;
  const chartAreaHeight = height - headerHeight - bottomPadding;
  const candleChartHeight = showVolume ? chartAreaHeight * 0.78 : chartAreaHeight;
  const volumeChartHeight = showVolume ? chartAreaHeight * 0.18 : 0;

  const prices = candles.length > 0 ? candles.flatMap((c) => [c.high, c.low]) : [0];
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const priceRange = maxPrice - minPrice || 1;

  const volumes = candles.length > 0 ? candles.map((c) => c.volume) : [0];
  const maxVolume = Math.max(...volumes);

  const priceToPercent = useCallback(
    (price: number) => {
      return ((maxPrice - price) / priceRange) * 100;
    },
    [maxPrice, priceRange]
  );

  // Loading state with premium spinner
  if (!isClient || candles.length === 0) {
    return (
      <div
        ref={containerRef}
        className="chart-container glass-strong relative"
        style={{ height, minHeight: height }}
      >
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="flex flex-col items-center gap-3">
            <div className="relative">
              <div className="w-10 h-10 rounded-full border-2 border-primary/30 border-t-primary animate-spin" />
            </div>
            <span className="text-sm text-muted-foreground">
              {error ? 'Failed to load data' : 'Loading market data...'}
            </span>
          </div>
        </div>
      </div>
    );
  }

  const candleWidth = 100 / candles.length;

  return (
    <div
      ref={containerRef}
      className="chart-container relative overflow-hidden rounded-xl border border-border/50"
      style={{ height, minHeight: height }}
    >
      {/* Premium background effects */}
      <div className="absolute inset-0 mesh-gradient opacity-40" />
      <div className="absolute inset-0 grid-pattern opacity-20" />

      {/* Dynamic glow based on price trend */}
      <div
        className="absolute bottom-0 left-1/2 -translate-x-1/2 w-2/3 h-40 rounded-full blur-3xl opacity-15 transition-colors duration-1000"
        style={{ background: priceChange >= 0 ? 'hsl(var(--profit))' : 'hsl(var(--loss))' }}
      />

      {/* Header with glass effect */}
      <div
        className="relative px-4 sm:px-5 py-4 flex items-center justify-between z-10 backdrop-blur-sm bg-card/30"
        style={{ height: headerHeight }}
      >
        <div className="flex items-center gap-3">
          {/* Bitcoin icon with glow */}
          <div className="relative group">
            <div className="absolute inset-0 bg-[#f7931a] rounded-full blur-lg opacity-40 group-hover:opacity-60 transition-opacity" />
            <div className="relative w-10 h-10 rounded-full bg-gradient-to-br from-[#f7931a] to-[#e8850d] flex items-center justify-center shadow-lg border border-[#f7931a]/30">
              <span className="text-white text-sm font-bold">₿</span>
            </div>
          </div>
          <div>
            <h3 className="font-semibold text-foreground text-base tracking-tight">{title}</h3>
            <p className="text-xs text-muted-foreground">Perpetual · {interval}</p>
          </div>
        </div>

        <div className="text-right">
          <p className="font-mono text-xl sm:text-2xl font-bold text-foreground tracking-tight">
            ${currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
          <div className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
            priceChange >= 0
              ? 'bg-[hsl(var(--profit))]/15 text-[hsl(var(--profit))]'
              : 'bg-[hsl(var(--loss))]/15 text-[hsl(var(--loss))]'
          }`}>
            {priceChange >= 0 ? (
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M7 11l5-5m0 0l5 5m-5-5v12" />
              </svg>
            ) : (
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M17 13l-5 5m0 0l-5-5m5 5V6" />
              </svg>
            )}
            {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Chart area */}
      <div className="relative px-3" style={{ height: chartAreaHeight }}>
        {/* Price labels with subtle background */}
        <div
          className="absolute right-2 top-0 flex flex-col justify-between z-10 pointer-events-none"
          style={{ height: candleChartHeight }}
        >
          {[maxPrice, (maxPrice + minPrice) / 2, minPrice].map((price, i) => (
            <span
              key={i}
              className="text-[10px] text-muted-foreground/80 font-mono tabular-nums bg-card/60 backdrop-blur-sm px-1.5 py-0.5 rounded"
            >
              ${price.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </span>
          ))}
        </div>

        {/* Grid lines */}
        <div className="absolute inset-x-3 top-0" style={{ height: candleChartHeight }}>
          {[0, 25, 50, 75, 100].map((percent) => (
            <div
              key={percent}
              className="absolute w-full border-t border-border/20"
              style={{ top: `${percent}%` }}
            />
          ))}
        </div>

        {/* Candlesticks */}
        <div className="absolute inset-x-3 top-0 flex" style={{ height: candleChartHeight }}>
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
                  className="absolute left-1/2 -translate-x-1/2 transition-all duration-150"
                  style={{
                    top: `${highPercent}%`,
                    height: `${lowPercent - highPercent}%`,
                    width: '1px',
                    backgroundColor: isUp ? 'hsl(var(--profit))' : 'hsl(var(--loss))',
                    opacity: isLatest ? 1 : 0.7,
                  }}
                />
                {/* Body */}
                <div
                  className="absolute left-1/2 -translate-x-1/2 rounded-[2px] transition-all duration-150"
                  style={{
                    top: `${bodyTopPercent}%`,
                    height: `${bodyHeightPercent}%`,
                    width: candleCount > 40 ? '50%' : '65%',
                    minHeight: '2px',
                    backgroundColor: isUp ? 'hsl(var(--profit))' : 'hsl(var(--loss))',
                    opacity: isUp ? 0.85 : 1,
                    boxShadow: isLatest
                      ? `0 0 12px ${isUp ? 'hsl(var(--profit) / 0.6)' : 'hsl(var(--loss) / 0.6)'}`
                      : 'none',
                  }}
                />
                {/* Latest candle pulsing border */}
                {isLatest && (
                  <div
                    className="absolute left-1/2 -translate-x-1/2 rounded-[2px] animate-pulse"
                    style={{
                      top: `${bodyTopPercent}%`,
                      height: `${bodyHeightPercent}%`,
                      width: candleCount > 40 ? '50%' : '65%',
                      minHeight: '2px',
                      border: `1px solid ${isUp ? 'hsl(var(--profit))' : 'hsl(var(--loss))'}`,
                      opacity: 0.4,
                    }}
                  />
                )}
              </div>
            );
          })}
        </div>

        {/* Volume bars with gradient */}
        {showVolume && (
          <div
            className="absolute inset-x-3 bottom-0 flex items-end gap-px"
            style={{ height: volumeChartHeight }}
          >
            {candles.map((candle) => {
              const isUp = candle.close >= candle.open;
              const barHeightPercent = maxVolume > 0 ? (candle.volume / maxVolume) * 100 : 0;

              return (
                <div
                  key={candle.id}
                  className="relative flex-1"
                  style={{ height: '100%' }}
                >
                  <div
                    className="absolute bottom-0 left-1/2 -translate-x-1/2 rounded-t-[1px] transition-all duration-150"
                    style={{
                      width: '70%',
                      height: `${Math.max(barHeightPercent, 2)}%`,
                      background: isUp
                        ? 'linear-gradient(to top, hsl(var(--profit) / 0.3), hsl(var(--profit) / 0.1))'
                        : 'linear-gradient(to top, hsl(var(--loss) / 0.3), hsl(var(--loss) / 0.1))',
                    }}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer with live indicator */}
      <div className="absolute bottom-3 left-4 right-4 flex items-center justify-between z-10">
        <div className="flex items-center gap-2">
          <div className="status-dot active" />
          <span className="text-xs text-muted-foreground">Live · Real Data</span>
        </div>
      </div>

      {/* Bottom gradient fade */}
      <div className="absolute bottom-0 left-0 right-0 h-14 bg-gradient-to-t from-[hsl(222_47%_4%)] to-transparent pointer-events-none" />
    </div>
  );
}

// Hero version with premium outer glow
interface HeroAnimatedCandlestickProps {
  symbol?: string;
  interval?: string;
}

export function HeroAnimatedCandlestick({ symbol = 'BTCUSDT', interval = '15m' }: HeroAnimatedCandlestickProps) {
  return (
    <div className="relative w-full max-w-3xl mx-auto px-2 sm:px-0">
      {/* Outer glow layers */}
      <div className="absolute -inset-2 bg-gradient-to-r from-primary/25 via-accent/15 to-primary/25 rounded-2xl blur-2xl opacity-70" />
      <div className="absolute -inset-px bg-gradient-to-r from-primary/40 via-transparent to-accent/40 rounded-xl opacity-40" />

      {/* Chart */}
      <div className="relative">
        <AnimatedCandlestick
          height={320}
          candleCount={30}
          showVolume={true}
          title="BTC/USDT"
          symbol={symbol}
          interval={interval}
        />
      </div>
    </div>
  );
}
