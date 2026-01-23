"use client";

import { useRouter } from "next/router";
import Head from "next/head";
import Link from "next/link";
import useSWR from "swr";
import { ArrowRight, TrendingUp, Shield, Zap, Bot } from "lucide-react";

import { Header } from "@/components/layout/header";
import { Footer } from "@/components/layout/footer";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { StatsCard } from "@/components/stats-card";
import { PnLChart } from "@/components/charts/pnl-chart";
import { useTranslation, type Locale } from "@/lib/i18n";
import { fetchPerformance, fetchSystemStatus } from "@/lib/api";
import { formatPercent } from "@/lib/utils";

const fetcher = (url: string) => fetch(url).then((res) => res.json());

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

  const isLoading = !performance && !perfError;

  return (
    <>
      <Head>
        <title>Algvex - AI-Powered Crypto Trading</title>
        <meta
          name="description"
          content="Advanced algorithmic trading powered by DeepSeek AI and multi-agent decision system"
        />
      </Head>

      <div className="min-h-screen gradient-bg">
        <Header locale={locale} t={t} />

        {/* Hero Section */}
        <section className="pt-32 pb-20 px-4">
          <div className="container mx-auto text-center">
            {/* Status Badge */}
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-primary/30 bg-primary/10 mb-8">
              <span
                className={`h-2 w-2 rounded-full ${
                  status?.trading_active
                    ? "bg-[hsl(var(--profit))] animate-pulse"
                    : "bg-muted-foreground"
                }`}
              />
              <span className="text-sm">
                {status?.trading_active ? t("stats.running") : t("stats.stopped")}
              </span>
            </div>

            {/* Main Title */}
            <h1 className="text-5xl md:text-7xl font-bold mb-6">
              <span className="text-primary">{t("hero.title")}</span>
              <br />
              {t("hero.title2")}
            </h1>

            <p className="text-xl text-muted-foreground max-w-2xl mx-auto mb-10">
              {t("hero.subtitle")}
            </p>

            {/* CTA Buttons */}
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link href="/copy">
                <Button size="lg" className="glow-primary">
                  {t("hero.cta")}
                  <ArrowRight className="ml-2 h-5 w-5" />
                </Button>
              </Link>
              <Link href="/performance">
                <Button size="lg" variant="outline">
                  {t("hero.stats")}
                </Button>
              </Link>
            </div>
          </div>
        </section>

        {/* Stats Section */}
        <section className="py-16 px-4">
          <div className="container mx-auto">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <StatsCard
                title={t("stats.totalReturn")}
                value={
                  isLoading
                    ? "..."
                    : formatPercent(performance?.total_pnl_percent || 0)
                }
                type={
                  (performance?.total_pnl_percent || 0) >= 0 ? "profit" : "loss"
                }
                icon="trending"
              />
              <StatsCard
                title={t("stats.winRate")}
                value={isLoading ? "..." : `${performance?.win_rate || 0}%`}
                type="neutral"
                icon="target"
              />
              <StatsCard
                title={t("stats.maxDrawdown")}
                value={
                  isLoading
                    ? "..."
                    : `-${performance?.max_drawdown_percent || 0}%`
                }
                type="loss"
                icon="alert"
              />
              <StatsCard
                title={t("stats.totalTrades")}
                value={isLoading ? "..." : performance?.total_trades || 0}
                type="neutral"
                icon="activity"
              />
            </div>
          </div>
        </section>

        {/* Chart Section */}
        <section className="py-16 px-4">
          <div className="container mx-auto">
            <Card className="border-border/50">
              <CardContent className="p-6">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h2 className="text-2xl font-bold">{t("perf.pnlCurve")}</h2>
                    <p className="text-muted-foreground">{t("perf.days30")}</p>
                  </div>
                </div>
                {performance?.pnl_curve ? (
                  <PnLChart data={performance.pnl_curve} />
                ) : (
                  <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                    {isLoading ? t("common.loading") : t("common.error")}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </section>

        {/* Features Section */}
        <section className="py-16 px-4">
          <div className="container mx-auto">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold mb-4">{t("about.title")}</h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              <Card className="border-border/50 text-center">
                <CardContent className="p-8">
                  <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-primary/10 flex items-center justify-center">
                    <Bot className="h-8 w-8 text-primary" />
                  </div>
                  <h3 className="text-xl font-semibold mb-3">
                    {t("about.strategy")}
                  </h3>
                  <p className="text-muted-foreground">
                    {t("about.strategyDesc")}
                  </p>
                </CardContent>
              </Card>

              <Card className="border-border/50 text-center">
                <CardContent className="p-8">
                  <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-primary/10 flex items-center justify-center">
                    <Shield className="h-8 w-8 text-primary" />
                  </div>
                  <h3 className="text-xl font-semibold mb-3">
                    {t("about.risk")}
                  </h3>
                  <p className="text-muted-foreground">{t("about.riskDesc")}</p>
                </CardContent>
              </Card>

              <Card className="border-border/50 text-center">
                <CardContent className="p-8">
                  <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-primary/10 flex items-center justify-center">
                    <Zap className="h-8 w-8 text-primary" />
                  </div>
                  <h3 className="text-xl font-semibold mb-3">
                    {t("about.tech")}
                  </h3>
                  <p className="text-muted-foreground">{t("about.techDesc")}</p>
                </CardContent>
              </Card>
            </div>
          </div>
        </section>

        <Footer t={t} />
      </div>
    </>
  );
}
