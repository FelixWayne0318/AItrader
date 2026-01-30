'use client';

import useSWR from 'swr';
import { Bot, TrendingUp, TrendingDown, Activity, Percent, DollarSign, Users } from 'lucide-react';

const fetcher = (url: string) => fetch(url).then((res) => res.json());

interface MetricItemProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  subValue?: string;
  type?: 'positive' | 'negative' | 'neutral' | 'warning';
  isLoading?: boolean;
}

function MetricItem({ icon, label, value, subValue, type = 'neutral', isLoading = false }: MetricItemProps) {
  const colorClass = {
    positive: 'text-[hsl(var(--profit))]',
    negative: 'text-[hsl(var(--loss))]',
    warning: 'text-yellow-500',
    neutral: 'text-foreground',
  }[type];

  const bgClass = {
    positive: 'bg-[hsl(var(--profit))]/10',
    negative: 'bg-[hsl(var(--loss))]/10',
    warning: 'bg-yellow-500/10',
    neutral: 'bg-primary/10',
  }[type];

  return (
    <div className="flex items-center gap-2 sm:gap-3 px-3 sm:px-4 py-2 rounded-lg hover:bg-muted/30 transition-colors">
      <div className={`p-1.5 rounded-md ${bgClass}`}>
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-[10px] sm:text-xs text-muted-foreground whitespace-nowrap">{label}</p>
        {isLoading ? (
          <div className="w-12 h-4 bg-muted rounded animate-pulse" />
        ) : (
          <div className="flex items-baseline gap-1.5">
            <p className={`text-xs sm:text-sm font-semibold ${colorClass} whitespace-nowrap`}>{value}</p>
            {subValue && (
              <span className="text-[10px] text-muted-foreground hidden sm:inline">{subValue}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function MarketIntelligenceBar() {
  // Fetch bot status
  const { data: status, error: statusError } = useSWR('/api/public/system-status', fetcher, {
    refreshInterval: 30000,
  });

  // Fetch BTC ticker
  const { data: ticker, error: tickerError } = useSWR('/api/trading/ticker/BTCUSDT', fetcher, {
    refreshInterval: 10000,
  });

  // Fetch long/short ratio (market sentiment)
  const { data: sentiment } = useSWR('/api/trading/long-short-ratio/BTCUSDT', fetcher, {
    refreshInterval: 60000,
  });

  // Fetch mark price (includes funding rate)
  const { data: markPrice } = useSWR('/api/trading/mark-price/BTCUSDT', fetcher, {
    refreshInterval: 30000,
  });

  // Fetch latest AI signal stats
  const { data: performance } = useSWR('/api/public/performance?days=7', fetcher, {
    refreshInterval: 60000,
  });

  const isLoading = !status && !statusError;
  const btcPrice = ticker?.price ? parseFloat(ticker.price) : 0;
  const priceChange = ticker?.price_change_percent ? parseFloat(ticker.price_change_percent) : 0;

  // Long/Short ratio - values > 1 means more longs
  const longShortRatio = sentiment?.longShortRatio ? parseFloat(sentiment.longShortRatio) : 1;
  const longPercent = longShortRatio > 0 ? (longShortRatio / (longShortRatio + 1)) * 100 : 50;

  // Funding rate (typically shown as percentage)
  const fundingRate = markPrice?.lastFundingRate ? parseFloat(markPrice.lastFundingRate) * 100 : 0;

  // Win rate from performance
  const winRate = performance?.win_rate || 0;

  return (
    <div className="w-full overflow-x-auto scrollbar-hide">
      <div className="flex items-center justify-center gap-1 sm:gap-2 min-w-max px-4 py-1">
        {/* Bot Status */}
        <MetricItem
          icon={
            <Bot className={`h-3 w-3 sm:h-4 sm:w-4 ${status?.trading_active ? 'text-[hsl(var(--profit))]' : 'text-muted-foreground'}`} />
          }
          label="Bot Status"
          value={status?.trading_active ? 'Active' : 'Offline'}
          type={status?.trading_active ? 'positive' : 'neutral'}
          isLoading={isLoading}
        />

        {/* Divider */}
        <div className="w-px h-8 bg-border/50 mx-1 hidden sm:block" />

        {/* BTC Price */}
        <MetricItem
          icon={
            <DollarSign className={`h-3 w-3 sm:h-4 sm:w-4 ${priceChange >= 0 ? 'text-[hsl(var(--profit))]' : 'text-[hsl(var(--loss))]'}`} />
          }
          label="BTC Price"
          value={btcPrice > 0 ? `$${btcPrice.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '--'}
          subValue={priceChange !== 0 ? `${priceChange >= 0 ? '+' : ''}${priceChange.toFixed(2)}%` : undefined}
          type={priceChange >= 0 ? 'positive' : 'negative'}
          isLoading={!ticker && !tickerError}
        />

        {/* Divider */}
        <div className="w-px h-8 bg-border/50 mx-1 hidden sm:block" />

        {/* Long/Short Ratio */}
        <MetricItem
          icon={
            <Users className={`h-3 w-3 sm:h-4 sm:w-4 ${longPercent > 50 ? 'text-[hsl(var(--profit))]' : 'text-[hsl(var(--loss))]'}`} />
          }
          label="Long/Short"
          value={`${longPercent.toFixed(0)}% L`}
          subValue={longShortRatio > 0 ? `(${longShortRatio.toFixed(2)})` : undefined}
          type={longPercent > 55 ? 'positive' : longPercent < 45 ? 'negative' : 'neutral'}
        />

        {/* Divider */}
        <div className="w-px h-8 bg-border/50 mx-1 hidden sm:block" />

        {/* Funding Rate */}
        <MetricItem
          icon={
            <Percent className={`h-3 w-3 sm:h-4 sm:w-4 ${fundingRate >= 0 ? 'text-[hsl(var(--profit))]' : 'text-[hsl(var(--loss))]'}`} />
          }
          label="Funding"
          value={`${fundingRate >= 0 ? '+' : ''}${fundingRate.toFixed(4)}%`}
          subValue={fundingRate > 0.01 ? 'Longs pay' : fundingRate < -0.01 ? 'Shorts pay' : undefined}
          type={Math.abs(fundingRate) > 0.05 ? 'warning' : fundingRate >= 0 ? 'positive' : 'negative'}
        />

        {/* Divider */}
        <div className="w-px h-8 bg-border/50 mx-1 hidden sm:block" />

        {/* Win Rate */}
        <MetricItem
          icon={
            <Activity className={`h-3 w-3 sm:h-4 sm:w-4 ${winRate >= 50 ? 'text-[hsl(var(--profit))]' : 'text-[hsl(var(--loss))]'}`} />
          }
          label="Win Rate"
          value={winRate > 0 ? `${winRate.toFixed(0)}%` : '--'}
          subValue="7 days"
          type={winRate >= 55 ? 'positive' : winRate >= 45 ? 'neutral' : 'negative'}
          isLoading={!performance}
        />

        {/* Divider */}
        <div className="w-px h-8 bg-border/50 mx-1 hidden sm:block" />

        {/* 24h Volume or Last Signal */}
        <MetricItem
          icon={
            priceChange >= 0 ? (
              <TrendingUp className="h-3 w-3 sm:h-4 sm:w-4 text-[hsl(var(--profit))]" />
            ) : (
              <TrendingDown className="h-3 w-3 sm:h-4 sm:w-4 text-[hsl(var(--loss))]" />
            )
          }
          label="24h Trend"
          value={priceChange >= 0 ? 'Bullish' : 'Bearish'}
          type={priceChange >= 0 ? 'positive' : 'negative'}
        />
      </div>
    </div>
  );
}
