"use client";

import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import useSWR from "swr";
import dynamic from "next/dynamic";
import {
  ArrowRight,
  TrendingUp,
  TrendingDown,
  Shield,
  Zap,
  Bot,
  Activity,
  Target,
  AlertTriangle,
  BarChart3,
  Cpu,
  Globe,
  ChevronRight,
} from "lucide-react";

import { Header } from "@/components/layout/header";
import { Footer } from "@/components/layout/footer";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useTranslation, type Locale } from "@/lib/i18n";
import { TickerTapeWidget, MiniChartWidget } from "@/components/charts/tradingview-widget";

// Dynamic import with SSR disabled to avoid hydration mismatch (random data generation)
const HeroAnimatedCandlestick = dynamic(
  () => import("@/components/charts/animated-candlestick").then(mod => mod.HeroAnimatedCandlestick),
  {
    ssr: false,
    loading: () => (
      <div className="relative w-full max-w-3xl mx-auto px-2 sm:px-0">
        <div className="h-[280px] rounded-xl border border-border/50 bg-card/50 flex items-center justify-center">
          <div className="flex items-center gap-2 text-muted-foreground">
            <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
            <span className="text-sm">Loading chart...</span>
          </div>
        </div>
      </div>
    )
  }
);

const fetcher = (url: string) => fetch(url).then((res) => res.json());

// Format number with sign
const formatPnL = (value: number) => {
  const formatted = Math.abs(value).toFixed(2);
  if (value >= 0) return `+$${formatted}`;
  return `-$${formatted}`;
};

const formatPercent = (value: number) => {
  const formatted = Math.abs(value).toFixed(2);
  if (value >= 0) return `+${formatted}%`;
  return `-${formatted}%`;
};

// Animated number component
function AnimatedValue({
  value,
  isLoading,
  className = "",
}: {
  value: string | number;
  isLoading: boolean;
  className?: string;
}) {
  if (isLoading) {
    return <span className="shimmer inline-block w-20 h-8 rounded" />;
  }
  return <span className={`number-animate ${className}`}>{value}</span>;
}

// Stats card component
function StatsCard({
  title,
  value,
  subtitle,
  icon: Icon,
  type = "neutral",
  isLoading = false,
}: {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: any;
  type?: "profit" | "loss" | "neutral";
  isLoading?: boolean;
}) {
  const colorClass =
    type === "profit"
      ? "text-[hsl(var(--profit))]"
      : type === "loss"
      ? "text-[hsl(var(--loss))]"
      : "text-foreground";

  const bgClass =
    type === "profit"
      ? "bg-[hsl(var(--profit))]/10"
      : type === "loss"
      ? "bg-[hsl(var(--loss))]/10"
      : "bg-primary/10";

  return (
    <Card className="stat-card border-border/50">
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">{title}</p>
            <div className="flex items-baseline gap-2">
              <AnimatedValue
                value={value}
                isLoading={isLoading}
                className={`text-3xl font-bold ${colorClass}`}
              />
            </div>
            {subtitle && (
              <p className="text-xs text-muted-foreground">{subtitle}</p>
            )}
          </div>
          <div className={`p-3 rounded-xl ${bgClass}`}>
            <Icon
              className={`h-6 w-6 ${
                type === "profit"
                  ? "text-[hsl(var(--profit))]"
                  : type === "loss"
                  ? "text-[hsl(var(--loss))]"
                  : "text-primary"
              }`}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// Mini PnL Chart
function MiniPnLChart({ data }: { data: Array<{ cumulative_pnl: number }> }) {
  if (!data || data.length < 2) return null;

  const values = data.map((d) => d.cumulative_pnl);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const width = 100;
  const height = 40;
  const padding = 2;

  const points = values
    .map((v, i) => {
      const x = padding + (i / (values.length - 1)) * (width - 2 * padding);
      const y =
        height - padding - ((v - min) / range) * (height - 2 * padding);
      return `${x},${y}`;
    })
    .join(" ");

  const isPositive = values[values.length - 1] >= values[0];

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-10">
      <defs>
        <linearGradient id="lineGradient" x1="0" y1="0" x2="0" y2="1">
          <stop
            offset="0%"
            stopColor={
              isPositive ? "hsl(var(--profit))" : "hsl(var(--loss))"
            }
            stopOpacity="0.3"
          />
          <stop
            offset="100%"
            stopColor={
              isPositive ? "hsl(var(--profit))" : "hsl(var(--loss))"
            }
            stopOpacity="0"
          />
        </linearGradient>
      </defs>
      <polygon
        points={`${padding},${height - padding} ${points} ${
          width - padding
        },${height - padding}`}
        fill="url(#lineGradient)"
      />
      <polyline
        points={points}
        fill="none"
        stroke={isPositive ? "hsl(var(--profit))" : "hsl(var(--loss))"}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// Feature card
function FeatureCard({
  icon: Icon,
  title,
  description,
}: {
  icon: any;
  title: string;
  description: string;
}) {
  return (
    <Card className="feature-card border-border/50 group hover:border-primary/30 transition-all duration-300">
      <CardContent className="p-8">
        <div className="icon-wrapper w-14 h-14 mb-6 rounded-2xl bg-gradient-to-br from-primary/20 to-accent/10 flex items-center justify-center">
          <Icon className="h-7 w-7 text-primary" />
        </div>
        <h3 className="text-xl font-semibold mb-3 group-hover:text-primary transition-colors">
          {title}
        </h3>
        <p className="text-muted-foreground leading-relaxed">{description}</p>
      </CardContent>
    </Card>
  );
}

export default function HomePage() {
  const router = useRouter();
  const locale = (router.locale || "en") as Locale;
  const { t } = useTranslation(locale);

  // Fetch performance data
  const { data: performance, error: perfError } = useSWR(
    "/api/public/performance?days=30",
    fetcher,
    { refreshInterval: 60000 }
  );

  // Fetch system status
  const { data: status } = useSWR("/api/public/system-status", fetcher, {
    refreshInterval: 30000,
  });

  // Fetch ticker for BTC price
  const { data: ticker } = useSWR("/api/trading/ticker/BTCUSDT", fetcher, {
    refreshInterval: 10000,
  });

  const isLoading = !performance && !perfError;
  const pnlType =
    (performance?.total_pnl || 0) >= 0 ? "profit" : ("loss" as const);

  return (
    <>
      <Head>
        <title>Algvex - AI-Powered Crypto Trading</title>
        <meta
          name="description"
          content="Advanced algorithmic trading powered by DeepSeek AI and multi-agent decision system"
        />
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <div className="min-h-screen gradient-bg noise-overlay">
        <Header locale={locale} t={t} />

        {/* Ticker Tape - positioned below fixed header */}
        <div className="pt-16 border-b border-border/50 bg-background/50">
          <TickerTapeWidget />
        </div>

        {/* Hero Section */}
        <section className="relative pt-16 pb-24 px-4 overflow-hidden">
          {/* Background effects */}
          <div className="absolute inset-0 grid-pattern opacity-30" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-primary/5 rounded-full blur-3xl" />

          <div className="container mx-auto relative z-10">
            <div className="max-w-4xl mx-auto text-center">
              {/* Status Badge */}
              <div className="inline-flex items-center gap-2.5 px-5 py-2.5 rounded-full glass mb-10">
                <span
                  className={`status-dot ${
                    status?.trading_active ? "active" : "inactive"
                  }`}
                />
                <span className="text-sm font-medium">
                  {status?.trading_active
                    ? "Bot Active & Trading"
                    : "Bot Offline"}
                </span>
                {ticker?.price && (
                  <>
                    <span className="text-muted-foreground">|</span>
                    <span className="text-sm">
                      BTC{" "}
                      <span className="font-mono font-semibold">
                        ${Number(ticker.price).toLocaleString()}
                      </span>
                    </span>
                    <span
                      className={`text-xs ${
                        ticker.price_change_percent >= 0
                          ? "text-[hsl(var(--profit))]"
                          : "text-[hsl(var(--loss))]"
                      }`}
                    >
                      {formatPercent(ticker.price_change_percent)}
                    </span>
                  </>
                )}
              </div>

              {/* Main Title */}
              <h1 className="text-5xl md:text-7xl font-bold mb-6 leading-tight">
                <span className="text-primary text-glow">AI-Powered</span>
                <br />
                <span className="bg-gradient-to-r from-foreground to-muted-foreground bg-clip-text text-transparent">
                  Crypto Trading
                </span>
              </h1>

              <p className="text-xl text-muted-foreground max-w-2xl mx-auto mb-12 leading-relaxed">
                Advanced algorithmic trading powered by{" "}
                <span className="text-foreground font-medium">DeepSeek AI</span>{" "}
                and{" "}
                <span className="text-foreground font-medium">
                  multi-agent decision system
                </span>
                . Automated 24/7 trading with intelligent risk management.
              </p>

              {/* CTA Buttons */}
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16">
                <Link href="/copy">
                  <Button size="lg" className="glow-primary text-lg px-8 h-14">
                    Start Copy Trading
                    <ArrowRight className="ml-2 h-5 w-5" />
                  </Button>
                </Link>
                <Link href="/chart">
                  <Button
                    size="lg"
                    variant="outline"
                    className="text-lg px-8 h-14"
                  >
                    <BarChart3 className="mr-2 h-5 w-5" />
                    Live Chart
                  </Button>
                </Link>
              </div>

              {/* Animated Candlestick Chart */}
              <HeroAnimatedCandlestick
                basePrice={ticker?.price ? Number(ticker.price) : undefined}
                priceChangePercent={ticker?.price_change_percent}
              />
            </div>
          </div>
        </section>

        {/* Live Stats Section */}
        <section className="py-16 px-4 relative">
          <div className="container mx-auto">
            <div className="flex items-center justify-between mb-8">
              <div>
                <h2 className="text-2xl font-bold">Live Performance</h2>
                <p className="text-muted-foreground">Last 30 days</p>
              </div>
              <Link
                href="/performance"
                className="flex items-center gap-1 text-sm text-primary hover:underline"
              >
                View Details <ChevronRight className="h-4 w-4" />
              </Link>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 stagger-children">
              <StatsCard
                title="Total Return"
                value={
                  isLoading
                    ? "..."
                    : formatPnL(performance?.total_pnl || 0)
                }
                subtitle={
                  performance?.total_pnl_percent
                    ? formatPercent(performance.total_pnl_percent)
                    : undefined
                }
                icon={pnlType === "profit" ? TrendingUp : TrendingDown}
                type={pnlType}
                isLoading={isLoading}
              />
              <StatsCard
                title="Win Rate"
                value={isLoading ? "..." : `${performance?.win_rate || 0}%`}
                subtitle={`${performance?.winning_trades || 0}W / ${
                  performance?.losing_trades || 0
                }L`}
                icon={Target}
                type="neutral"
                isLoading={isLoading}
              />
              <StatsCard
                title="Max Drawdown"
                value={
                  isLoading
                    ? "..."
                    : `-${performance?.max_drawdown_percent || 0}%`
                }
                subtitle="Peak to trough"
                icon={AlertTriangle}
                type="loss"
                isLoading={isLoading}
              />
              <StatsCard
                title="Total Trades"
                value={isLoading ? "..." : performance?.total_trades || 0}
                subtitle="Executed orders"
                icon={Activity}
                type="neutral"
                isLoading={isLoading}
              />
            </div>

            {/* Mini Chart */}
            {performance?.pnl_curve && performance.pnl_curve.length > 0 && (
              <Card className="mt-8 border-border/50">
                <CardContent className="p-6">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="font-semibold">Cumulative PnL</h3>
                      <p className="text-sm text-muted-foreground">
                        30-day equity curve
                      </p>
                    </div>
                    <div className="text-right">
                      <p
                        className={`text-2xl font-bold ${
                          (performance?.total_pnl || 0) >= 0
                            ? "text-[hsl(var(--profit))]"
                            : "text-[hsl(var(--loss))]"
                        }`}
                      >
                        {formatPnL(performance?.total_pnl || 0)}
                      </p>
                    </div>
                  </div>
                  <div className="h-32">
                    <MiniPnLChart data={performance.pnl_curve} />
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </section>

        {/* Features Section */}
        <section className="py-20 px-4">
          <div className="container mx-auto">
            <div className="text-center mb-16">
              <h2 className="text-3xl md:text-4xl font-bold mb-4">
                Why Choose Algvex?
              </h2>
              <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
                Powered by cutting-edge AI technology and institutional-grade
                risk management
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
              <FeatureCard
                icon={Bot}
                title="Multi-Agent AI"
                description="Bull, Bear, and Judge agents debate market conditions using DeepSeek AI for balanced, unbiased decisions."
              />
              <FeatureCard
                icon={Shield}
                title="Risk Management"
                description="Dynamic position sizing, support/resistance-based stop losses, and trailing stops protect your capital."
              />
              <FeatureCard
                icon={BarChart3}
                title="Multi-Timeframe Analysis"
                description="Three-layer framework (1D trend, 4H decision, 15M execution) ensures precise entry timing."
              />
              <FeatureCard
                icon={Zap}
                title="24/7 Automation"
                description="Never miss an opportunity. The bot monitors markets and executes trades around the clock."
              />
              <FeatureCard
                icon={Cpu}
                title="Order Flow Analysis"
                description="Real-time buy/sell ratio, CVD, and volume analysis to detect institutional activity."
              />
              <FeatureCard
                icon={Globe}
                title="Derivatives Data"
                description="Open interest, funding rates, and liquidation data provide market sentiment insights."
              />
            </div>
          </div>
        </section>

        {/* CTA Section */}
        <section className="py-20 px-4">
          <div className="container mx-auto">
            <Card className="border-border/50 overflow-hidden relative">
              <div className="absolute inset-0 mesh-gradient opacity-50" />
              <CardContent className="p-12 md:p-16 relative z-10 text-center">
                <h2 className="text-3xl md:text-4xl font-bold mb-4">
                  Ready to Start?
                </h2>
                <p className="text-muted-foreground text-lg mb-8 max-w-xl mx-auto">
                  Connect your exchange account and let our AI handle the
                  trading while you focus on what matters.
                </p>
                <Link href="/copy">
                  <Button size="lg" className="glow-primary text-lg px-10 h-14">
                    Get Started
                    <ArrowRight className="ml-2 h-5 w-5" />
                  </Button>
                </Link>
              </CardContent>
            </Card>
          </div>
        </section>

        <Footer t={t} />
      </div>
    </>
  );
}
