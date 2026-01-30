"use client";

import { useRouter } from "next/router";
import Head from "next/head";
import { Bot, Shield, Zap, LineChart, Brain, Server } from "lucide-react";

import { Header } from "@/components/layout/header";
import { Footer } from "@/components/layout/footer";
import { Card, CardContent } from "@/components/ui/card";
import { useTranslation, type Locale } from "@/lib/i18n";

const features = [
  {
    icon: Brain,
    titleKey: "about.strategy",
    descKey: "about.strategyDesc",
  },
  {
    icon: Shield,
    titleKey: "about.risk",
    descKey: "about.riskDesc",
  },
  {
    icon: Zap,
    titleKey: "about.tech",
    descKey: "about.techDesc",
  },
];

const techStack = [
  {
    name: "NautilusTrader",
    description: "High-performance algorithmic trading platform",
    version: "1.221.0",
  },
  {
    name: "DeepSeek AI",
    description: "Advanced language model for market analysis",
    version: "deepseek-chat",
  },
  {
    name: "Multi-Agent System",
    description: "Bull/Bear debate mechanism for decision making",
    version: "TradingAgents",
  },
  {
    name: "Binance Futures",
    description: "Primary exchange for BTC/USDT perpetual",
    version: "API v3",
  },
];

export default function AboutPage() {
  const router = useRouter();
  const locale = (router.locale || "en") as Locale;
  const { t } = useTranslation(locale);

  return (
    <>
      <Head>
        <title>About - Algvex</title>
        <meta
          name="description"
          content="Learn about Algvex AI-powered trading system"
        />
      </Head>

      <div className="min-h-screen gradient-bg">
        <Header locale={locale} t={t} />

        {/* pt-20 accounts for single-row unified header (56px) */}
        <main className="pt-20 pb-16 px-4">
          <div className="container mx-auto max-w-4xl">
            {/* Page Header */}
            <div className="text-center mb-16">
              <h1 className="text-4xl font-bold mb-4">{t("about.title")}</h1>
              <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
                An AI-powered algorithmic trading system built for consistent,
                data-driven decision making in cryptocurrency markets.
              </p>
            </div>

            {/* Core Features */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-16">
              {features.map((feature) => {
                const Icon = feature.icon;
                return (
                  <Card
                    key={feature.titleKey}
                    className="border-border/50 text-center"
                  >
                    <CardContent className="p-8">
                      <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-primary/10 flex items-center justify-center">
                        <Icon className="h-8 w-8 text-primary" />
                      </div>
                      <h3 className="text-xl font-semibold mb-3">
                        {t(feature.titleKey)}
                      </h3>
                      <p className="text-muted-foreground">
                        {t(feature.descKey)}
                      </p>
                    </CardContent>
                  </Card>
                );
              })}
            </div>

            {/* How It Works */}
            <Card className="border-border/50 mb-16">
              <CardContent className="p-8">
                <h2 className="text-2xl font-bold mb-6 text-center">
                  How It Works
                </h2>
                <div className="space-y-6">
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center flex-shrink-0 font-semibold">
                      1
                    </div>
                    <div>
                      <h4 className="font-semibold mb-1">Market Data Collection</h4>
                      <p className="text-muted-foreground">
                        Real-time price data, technical indicators (RSI, MACD,
                        Bollinger Bands), and Binance long/short ratio are collected
                        every 15 minutes.
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center flex-shrink-0 font-semibold">
                      2
                    </div>
                    <div>
                      <h4 className="font-semibold mb-1">AI Analysis</h4>
                      <p className="text-muted-foreground">
                        DeepSeek AI analyzes the data. A multi-agent system with
                        Bull and Bear analysts debate the market direction, while a
                        Judge makes the final decision.
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center flex-shrink-0 font-semibold">
                      3
                    </div>
                    <div>
                      <h4 className="font-semibold mb-1">Signal Generation</h4>
                      <p className="text-muted-foreground">
                        Trading signals (BUY/SELL/HOLD) are generated with confidence
                        levels (HIGH/MEDIUM/LOW). Position sizing is adjusted based
                        on confidence.
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center flex-shrink-0 font-semibold">
                      4
                    </div>
                    <div>
                      <h4 className="font-semibold mb-1">Risk Management</h4>
                      <p className="text-muted-foreground">
                        Automatic stop-loss, take-profit, and trailing stop orders
                        protect capital. Maximum position size is capped at 30% of
                        equity.
                      </p>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Tech Stack */}
            <Card className="border-border/50">
              <CardContent className="p-8">
                <h2 className="text-2xl font-bold mb-6 text-center">
                  Technology Stack
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {techStack.map((tech) => (
                    <div
                      key={tech.name}
                      className="p-4 rounded-lg bg-muted/30 border border-border/50"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="font-semibold">{tech.name}</h4>
                        <span className="text-xs text-primary bg-primary/10 px-2 py-1 rounded">
                          {tech.version}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {tech.description}
                      </p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </main>

        <Footer t={t} />
      </div>
    </>
  );
}
