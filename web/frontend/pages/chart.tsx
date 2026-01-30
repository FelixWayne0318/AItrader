"use client";

import { useState } from "react";
import Head from "next/head";
import Link from "next/link";
import useSWR from "swr";
import {
  TradingViewWidget,
  TechnicalAnalysisWidget,
} from "@/components/charts/tradingview-widget";
import { MarketIntelligenceBar } from "@/components/trading/market-intelligence-bar";
import {
  ArrowLeft,
  TrendingUp,
  TrendingDown,
  BarChart3,
  Activity,
  Clock,
  DollarSign,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

const formatNumber = (num: number, decimals = 2) => {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(num);
};

export default function ChartPage() {
  const [interval, setInterval] = useState("15");
  const [symbol, setSymbol] = useState("BINANCE:BTCUSDT.P");

  // Fetch real-time data
  const { data: ticker } = useSWR("/api/trading/ticker/BTCUSDT", fetcher, {
    refreshInterval: 5000,
  });

  const { data: markPrice } = useSWR("/api/trading/mark-price/BTCUSDT", fetcher, {
    refreshInterval: 5000,
  });

  const { data: longShortRatio } = useSWR(
    "/api/trading/long-short-ratio/BTCUSDT",
    fetcher,
    { refreshInterval: 60000 }
  );

  const intervals = [
    { value: "1", label: "1m" },
    { value: "5", label: "5m" },
    { value: "15", label: "15m" },
    { value: "60", label: "1H" },
    { value: "240", label: "4H" },
    { value: "D", label: "1D" },
    { value: "W", label: "1W" },
  ];

  const symbols = [
    { value: "BINANCE:BTCUSDT.P", label: "BTC/USDT" },
    { value: "BINANCE:ETHUSDT.P", label: "ETH/USDT" },
    { value: "BINANCE:SOLUSDT.P", label: "SOL/USDT" },
    { value: "BINANCE:BNBUSDT.P", label: "BNB/USDT" },
    { value: "BINANCE:XRPUSDT.P", label: "XRP/USDT" },
    { value: "BINANCE:ADAUSDT.P", label: "ADA/USDT" },
  ];

  const priceChange = ticker ? parseFloat(ticker.priceChangePercent) : 0;
  const isPositive = priceChange >= 0;

  return (
    <>
      <Head>
        <title>Live Chart - Algvex</title>
        <meta name="description" content="Real-time cryptocurrency charts with technical analysis" />
      </Head>

      <div className="min-h-screen gradient-bg">
        {/* Market Intelligence Bar - consistent with other pages */}
        <div className="border-b border-border/30 bg-background/60 backdrop-blur-sm">
          <MarketIntelligenceBar />
        </div>

        {/* Header */}
        <header className="border-b border-border/50 bg-background/80 backdrop-blur-lg">
          <div className="container mx-auto px-4">
            <div className="flex h-16 items-center justify-between">
              <div className="flex items-center gap-4">
                <Link href="/">
                  <Button variant="ghost" size="sm">
                    <ArrowLeft className="h-4 w-4 mr-2" />
                    Back
                  </Button>
                </Link>
                <div className="h-6 w-px bg-border" />
                <div className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-primary to-accent flex items-center justify-center">
                    <BarChart3 className="h-4 w-4 text-primary-foreground" />
                  </div>
                  <span className="font-semibold">Live Chart</span>
                </div>
              </div>

              {/* Symbol selector */}
              <div className="flex items-center gap-3">
                <select
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  className="px-3 py-2 rounded-lg bg-muted border border-border text-sm"
                >
                  {symbols.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </header>

        <main className="container mx-auto px-4 py-6">
          {/* Price Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-6">
            <Card className="border-border/50 stat-card">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-1">
                  <DollarSign className="h-4 w-4 text-primary" />
                  <span className="text-xs text-muted-foreground">Price</span>
                </div>
                <p className="text-xl font-bold font-mono">
                  ${ticker ? formatNumber(parseFloat(ticker.lastPrice)) : "---"}
                </p>
              </CardContent>
            </Card>

            <Card className="border-border/50 stat-card">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-1">
                  {isPositive ? (
                    <TrendingUp className="h-4 w-4 text-[hsl(var(--profit))]" />
                  ) : (
                    <TrendingDown className="h-4 w-4 text-[hsl(var(--loss))]" />
                  )}
                  <span className="text-xs text-muted-foreground">24h Change</span>
                </div>
                <p
                  className={`text-xl font-bold font-mono ${
                    isPositive ? "text-[hsl(var(--profit))]" : "text-[hsl(var(--loss))]"
                  }`}
                >
                  {isPositive ? "+" : ""}
                  {ticker ? formatNumber(priceChange) : "---"}%
                </p>
              </CardContent>
            </Card>

            <Card className="border-border/50 stat-card">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-1">
                  <Activity className="h-4 w-4 text-accent" />
                  <span className="text-xs text-muted-foreground">24h High</span>
                </div>
                <p className="text-xl font-bold font-mono">
                  ${ticker ? formatNumber(parseFloat(ticker.highPrice)) : "---"}
                </p>
              </CardContent>
            </Card>

            <Card className="border-border/50 stat-card">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-1">
                  <Activity className="h-4 w-4 text-muted-foreground" />
                  <span className="text-xs text-muted-foreground">24h Low</span>
                </div>
                <p className="text-xl font-bold font-mono">
                  ${ticker ? formatNumber(parseFloat(ticker.lowPrice)) : "---"}
                </p>
              </CardContent>
            </Card>

            <Card className="border-border/50 stat-card">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-1">
                  <BarChart3 className="h-4 w-4 text-primary" />
                  <span className="text-xs text-muted-foreground">Volume (24h)</span>
                </div>
                <p className="text-xl font-bold font-mono">
                  {ticker
                    ? `$${formatNumber(parseFloat(ticker.quoteVolume) / 1000000, 1)}M`
                    : "---"}
                </p>
              </CardContent>
            </Card>

            <Card className="border-border/50 stat-card">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-1">
                  <Clock className="h-4 w-4 text-yellow-500" />
                  <span className="text-xs text-muted-foreground">Long/Short</span>
                </div>
                <p className="text-xl font-bold font-mono">
                  {longShortRatio?.length > 0
                    ? formatNumber(parseFloat(longShortRatio[0].longShortRatio), 2)
                    : "---"}
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Interval Selector */}
          <div className="flex gap-2 mb-4">
            {intervals.map((i) => (
              <Button
                key={i.value}
                variant={interval === i.value ? "default" : "outline"}
                size="sm"
                onClick={() => setInterval(i.value)}
                className={interval !== i.value ? "border-border/50" : ""}
              >
                {i.label}
              </Button>
            ))}
          </div>

          {/* Main Chart */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <div className="lg:col-span-3">
              <Card className="border-border/50 overflow-hidden">
                <CardContent className="p-0">
                  <div style={{ height: 600 }}>
                    <TradingViewWidget
                      symbol={symbol}
                      interval={interval}
                      theme="dark"
                      height={600}
                      autosize={false}
                      showToolbar={true}
                      showDetails={true}
                    />
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Technical Analysis Sidebar */}
            <div className="space-y-6">
              <Card className="border-border/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Activity className="h-4 w-4 text-primary" />
                    Technical Analysis
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  <TechnicalAnalysisWidget
                    symbol={symbol}
                    interval={`${interval}${interval === "D" || interval === "W" ? "" : "m"}`}
                    colorTheme="dark"
                    height={350}
                  />
                </CardContent>
              </Card>

              {/* Mark Price Info */}
              <Card className="border-border/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Mark Price Info</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Mark Price</span>
                    <span className="font-mono">
                      ${markPrice ? formatNumber(parseFloat(markPrice.markPrice)) : "---"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Index Price</span>
                    <span className="font-mono">
                      ${markPrice ? formatNumber(parseFloat(markPrice.indexPrice)) : "---"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Funding Rate</span>
                    <span
                      className={`font-mono ${
                        markPrice && parseFloat(markPrice.lastFundingRate) > 0
                          ? "text-[hsl(var(--profit))]"
                          : "text-[hsl(var(--loss))]"
                      }`}
                    >
                      {markPrice
                        ? `${(parseFloat(markPrice.lastFundingRate) * 100).toFixed(4)}%`
                        : "---"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Next Funding</span>
                    <span className="font-mono text-sm">
                      {markPrice
                        ? new Date(markPrice.nextFundingTime).toLocaleTimeString()
                        : "---"}
                    </span>
                  </div>
                </CardContent>
              </Card>

              {/* Long/Short Ratio */}
              {longShortRatio?.length > 0 && (
                <Card className="border-border/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Long/Short Ratio</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {longShortRatio.slice(0, 5).map((item: any, idx: number) => {
                        const ratio = parseFloat(item.longShortRatio);
                        const longPercent = (ratio / (ratio + 1)) * 100;
                        return (
                          <div key={idx}>
                            <div className="flex justify-between text-xs mb-1">
                              <span className="text-muted-foreground">
                                {new Date(item.timestamp).toLocaleTimeString()}
                              </span>
                              <span className="font-mono">{formatNumber(ratio, 2)}</span>
                            </div>
                            <div className="h-2 rounded-full bg-[hsl(var(--loss))]/30 overflow-hidden">
                              <div
                                className="h-full bg-[hsl(var(--profit))]"
                                style={{ width: `${longPercent}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </main>

        {/* Footer */}
        <footer className="border-t border-border/50 mt-12">
          <div className="container mx-auto px-4 py-6">
            <div className="flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-muted-foreground">
              <p>Real-time data from Binance Futures</p>
              <div className="flex items-center gap-4">
                <Link href="/" className="hover:text-foreground transition-colors">
                  Home
                </Link>
                <Link href="/admin" className="hover:text-foreground transition-colors">
                  Admin
                </Link>
              </div>
            </div>
          </div>
        </footer>
      </div>
    </>
  );
}
