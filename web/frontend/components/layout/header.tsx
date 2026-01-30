"use client";

import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";
import useSWR from "swr";
import {
  Menu,
  X,
  Globe,
  Bot,
  Users,
  Percent,
  BarChart3,
  Activity,
  Brain,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Locale } from "@/lib/i18n";

const fetcher = (url: string) => fetch(url).then((res) => res.json());

interface HeaderProps {
  locale: Locale;
  t: (key: string) => string;
}

function MetricChip({
  icon,
  value,
  type = "neutral",
}: {
  icon: React.ReactNode;
  value: string;
  type?: "positive" | "negative" | "neutral";
}) {
  const colorClass = {
    positive: "text-[hsl(var(--profit))]",
    negative: "text-[hsl(var(--loss))]",
    neutral: "text-foreground",
  }[type];

  return (
    <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted/30 hover:bg-muted/50 transition-colors">
      {icon}
      <span className={`text-xs font-medium ${colorClass}`}>{value}</span>
    </div>
  );
}

export function Header({ locale, t }: HeaderProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const router = useRouter();

  // Fetch market data
  const { data: status } = useSWR("/api/public/system-status", fetcher, {
    refreshInterval: 30000,
  });

  const { data: sentiment } = useSWR("/api/trading/long-short-ratio/BTCUSDT", fetcher, {
    refreshInterval: 60000,
  });

  const { data: markPrice } = useSWR("/api/trading/mark-price/BTCUSDT", fetcher, {
    refreshInterval: 30000,
  });

  const { data: openInterest } = useSWR("/api/trading/open-interest/BTCUSDT", fetcher, {
    refreshInterval: 60000,
  });

  const { data: ticker } = useSWR("/api/trading/ticker/BTCUSDT", fetcher, {
    refreshInterval: 10000,
  });

  const { data: latestSignal } = useSWR("/api/public/latest-signal", fetcher, {
    refreshInterval: 30000,
  });

  const toggleLocale = () => {
    const newLocale = locale === "en" ? "zh" : "en";
    router.push(router.pathname, router.asPath, { locale: newLocale });
  };

  const navItems = [
    { href: "/", label: t("nav.home") },
    { href: "/chart", label: "Chart" },
    { href: "/performance", label: t("nav.performance") },
    { href: "/copy", label: t("nav.copy") },
  ];

  // Calculate metrics
  const longShortRatio = sentiment?.data?.[0]?.long_short_ratio || sentiment?.longShortRatio || 1;
  const longPercent = longShortRatio > 0 ? (longShortRatio / (longShortRatio + 1)) * 100 : 50;

  const fundingRate = markPrice?.funding_rate
    ? markPrice.funding_rate * 100
    : markPrice?.lastFundingRate
    ? parseFloat(markPrice.lastFundingRate) * 100
    : 0;

  const oiValue = openInterest?.value || 0;
  const formatOI = (value: number) => {
    if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
    if (value >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
    return "--";
  };

  const volume24h = ticker?.quote_volume_24h || 0;
  const formatVolume = (value: number) => {
    if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
    if (value >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
    return "--";
  };

  const signal = latestSignal?.signal || "HOLD";
  const getSignalType = (s: string): "positive" | "negative" | "neutral" => {
    if (s === "BUY" || s === "LONG") return "positive";
    if (s === "SELL" || s === "SHORT") return "negative";
    return "neutral";
  };

  return (
    <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-lg">
      <div className="container mx-auto px-4">
        <div className="flex h-14 items-center justify-between gap-4">
          {/* Logo */}
          <Link href="/" className="flex items-center space-x-2 flex-shrink-0">
            <div className="h-7 w-7 rounded-lg bg-primary flex items-center justify-center">
              <span className="text-primary-foreground font-bold text-sm">A</span>
            </div>
            <span className="text-lg font-bold hidden sm:inline">Algvex</span>
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden lg:flex items-center space-x-6">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                {item.label}
              </Link>
            ))}
          </nav>

          {/* Market Metrics - Desktop */}
          <div className="hidden md:flex items-center gap-2 flex-1 justify-center">
            {/* Bot Status */}
            <MetricChip
              icon={
                <Bot
                  className={`h-3.5 w-3.5 ${
                    status?.trading_active ? "text-[hsl(var(--profit))]" : "text-muted-foreground"
                  }`}
                />
              }
              value={status?.trading_active ? "Active" : "Offline"}
              type={status?.trading_active ? "positive" : "neutral"}
            />

            {/* Long/Short */}
            <MetricChip
              icon={
                <Users
                  className={`h-3.5 w-3.5 ${
                    longPercent > 50 ? "text-[hsl(var(--profit))]" : "text-[hsl(var(--loss))]"
                  }`}
                />
              }
              value={`${longPercent.toFixed(0)}% L`}
              type={longPercent > 55 ? "positive" : longPercent < 45 ? "negative" : "neutral"}
            />

            {/* Funding Rate */}
            <MetricChip
              icon={
                <Percent
                  className={`h-3.5 w-3.5 ${
                    fundingRate >= 0 ? "text-[hsl(var(--profit))]" : "text-[hsl(var(--loss))]"
                  }`}
                />
              }
              value={`${fundingRate >= 0 ? "+" : ""}${fundingRate.toFixed(4)}%`}
              type={fundingRate >= 0 ? "positive" : "negative"}
            />

            {/* Open Interest - Hidden on smaller screens */}
            <div className="hidden xl:block">
              <MetricChip
                icon={<BarChart3 className="h-3.5 w-3.5 text-blue-500" />}
                value={`OI ${formatOI(oiValue)}`}
                type="neutral"
              />
            </div>

            {/* 24h Volume - Hidden on smaller screens */}
            <div className="hidden xl:block">
              <MetricChip
                icon={<Activity className="h-3.5 w-3.5 text-purple-500" />}
                value={formatVolume(volume24h)}
                type="neutral"
              />
            </div>

            {/* AI Signal */}
            <MetricChip
              icon={
                <Brain
                  className={`h-3.5 w-3.5 ${
                    getSignalType(signal) === "positive"
                      ? "text-[hsl(var(--profit))]"
                      : getSignalType(signal) === "negative"
                      ? "text-[hsl(var(--loss))]"
                      : "text-foreground"
                  }`}
                />
              }
              value={signal}
              type={getSignalType(signal)}
            />
          </div>

          {/* Right side */}
          <div className="flex items-center space-x-3 flex-shrink-0">
            {/* Language toggle */}
            <Button
              variant="ghost"
              size="sm"
              onClick={toggleLocale}
              className="hidden md:flex h-8 px-2"
            >
              <Globe className="h-4 w-4" />
              <span className="ml-1 text-xs">{locale.toUpperCase()}</span>
            </Button>

            {/* CTA Button */}
            <Link href="/copy" className="hidden md:block">
              <Button size="sm" className="h-8">{t("hero.cta")}</Button>
            </Link>

            {/* Mobile menu button */}
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden h-8 w-8"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              {mobileMenuOpen ? (
                <X className="h-5 w-5" />
              ) : (
                <Menu className="h-5 w-5" />
              )}
            </Button>
          </div>
        </div>

        {/* Mobile Navigation */}
        {mobileMenuOpen && (
          <div className="lg:hidden py-4 border-t border-border">
            <nav className="flex flex-col space-y-3">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="text-muted-foreground hover:text-foreground transition-colors px-2 py-1"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  {item.label}
                </Link>
              ))}
            </nav>

            {/* Mobile Metrics */}
            <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t border-border">
              <MetricChip
                icon={
                  <Bot
                    className={`h-3.5 w-3.5 ${
                      status?.trading_active ? "text-[hsl(var(--profit))]" : "text-muted-foreground"
                    }`}
                  />
                }
                value={status?.trading_active ? "Active" : "Offline"}
                type={status?.trading_active ? "positive" : "neutral"}
              />
              <MetricChip
                icon={<Users className="h-3.5 w-3.5" />}
                value={`${longPercent.toFixed(0)}% L`}
                type={longPercent > 55 ? "positive" : longPercent < 45 ? "negative" : "neutral"}
              />
              <MetricChip
                icon={<Percent className="h-3.5 w-3.5" />}
                value={`${fundingRate >= 0 ? "+" : ""}${fundingRate.toFixed(4)}%`}
                type={fundingRate >= 0 ? "positive" : "negative"}
              />
              <MetricChip
                icon={<Brain className="h-3.5 w-3.5" />}
                value={signal}
                type={getSignalType(signal)}
              />
            </div>

            <div className="flex items-center justify-between px-2 pt-4 mt-4 border-t border-border">
              <Button variant="ghost" size="sm" onClick={toggleLocale}>
                <Globe className="h-4 w-4 mr-2" />
                {locale === "en" ? "中文" : "English"}
              </Button>
              <Link href="/copy" onClick={() => setMobileMenuOpen(false)}>
                <Button size="sm">{t("hero.cta")}</Button>
              </Link>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
