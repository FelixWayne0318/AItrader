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

  const getSignalColor = (type: "positive" | "negative" | "neutral") => {
    if (type === "positive") return "text-green-500";
    if (type === "negative") return "text-red-500";
    return "text-foreground";
  };

  return (
    <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-lg">
      <div className="container mx-auto px-4">
        <div className="flex h-14 items-center justify-between">
          {/* Logo - Always visible */}
          <Link href="/" className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-lg bg-primary flex items-center justify-center">
              <span className="text-primary-foreground font-bold text-sm">A</span>
            </div>
            <span className="text-lg font-bold">Algvex</span>
          </Link>

          {/* Desktop Navigation - Only on lg+ screens */}
          <nav className="hidden lg:flex items-center gap-6">
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

          {/* Market Metrics - Only on lg+ screens */}
          <div className="hidden lg:flex items-center gap-2">
            {/* Bot Status */}
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted/30">
              <Bot className={`h-3.5 w-3.5 ${status?.trading_active ? "text-green-500" : "text-muted-foreground"}`} />
              <span className={`text-xs font-medium ${status?.trading_active ? "text-green-500" : ""}`}>
                {status?.trading_active ? "Active" : "Offline"}
              </span>
            </div>

            {/* Long/Short */}
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted/30">
              <Users className={`h-3.5 w-3.5 ${longPercent > 50 ? "text-green-500" : "text-red-500"}`} />
              <span className="text-xs font-medium">{longPercent.toFixed(0)}% L</span>
            </div>

            {/* Funding Rate */}
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted/30">
              <Percent className={`h-3.5 w-3.5 ${fundingRate >= 0 ? "text-green-500" : "text-red-500"}`} />
              <span className={`text-xs font-medium ${fundingRate >= 0 ? "text-green-500" : "text-red-500"}`}>
                {fundingRate >= 0 ? "+" : ""}{fundingRate.toFixed(4)}%
              </span>
            </div>

            {/* Open Interest - Only on xl+ */}
            <div className="hidden xl:flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted/30">
              <BarChart3 className="h-3.5 w-3.5 text-blue-500" />
              <span className="text-xs font-medium">OI {formatOI(oiValue)}</span>
            </div>

            {/* 24h Volume - Only on xl+ */}
            <div className="hidden xl:flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted/30">
              <Activity className="h-3.5 w-3.5 text-purple-500" />
              <span className="text-xs font-medium">{formatVolume(volume24h)}</span>
            </div>

            {/* AI Signal */}
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted/30">
              <Brain className={`h-3.5 w-3.5 ${getSignalColor(getSignalType(signal))}`} />
              <span className={`text-xs font-medium ${getSignalColor(getSignalType(signal))}`}>{signal}</span>
            </div>
          </div>

          {/* Right side - Desktop */}
          <div className="hidden lg:flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={toggleLocale} className="h-8 px-2">
              <Globe className="h-4 w-4" />
              <span className="ml-1 text-xs">{locale.toUpperCase()}</span>
            </Button>
            <Link href="/copy">
              <Button size="sm" className="h-8">{t("hero.cta")}</Button>
            </Link>
          </div>

          {/* Mobile menu button - Only on mobile */}
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden h-9 w-9"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </Button>
        </div>

        {/* Mobile Navigation Menu */}
        {mobileMenuOpen && (
          <div className="lg:hidden py-4 border-t border-border">
            {/* Navigation Links */}
            <nav className="flex flex-col gap-1 mb-4">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="px-3 py-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  {item.label}
                </Link>
              ))}
            </nav>

            {/* Market Metrics in Mobile Menu */}
            <div className="border-t border-border pt-4 mb-4">
              <p className="text-xs text-muted-foreground px-3 mb-2">Market Data</p>
              <div className="grid grid-cols-2 gap-2 px-3">
                <div className="flex items-center gap-2 p-2 rounded-md bg-muted/30">
                  <Bot className={`h-4 w-4 ${status?.trading_active ? "text-green-500" : "text-muted-foreground"}`} />
                  <span className="text-sm">{status?.trading_active ? "Active" : "Offline"}</span>
                </div>
                <div className="flex items-center gap-2 p-2 rounded-md bg-muted/30">
                  <Users className="h-4 w-4" />
                  <span className="text-sm">{longPercent.toFixed(0)}% Long</span>
                </div>
                <div className="flex items-center gap-2 p-2 rounded-md bg-muted/30">
                  <Percent className="h-4 w-4" />
                  <span className="text-sm">{fundingRate >= 0 ? "+" : ""}{fundingRate.toFixed(4)}%</span>
                </div>
                <div className="flex items-center gap-2 p-2 rounded-md bg-muted/30">
                  <Brain className={`h-4 w-4 ${getSignalColor(getSignalType(signal))}`} />
                  <span className={`text-sm ${getSignalColor(getSignalType(signal))}`}>{signal}</span>
                </div>
              </div>
            </div>

            {/* Bottom Actions */}
            <div className="flex items-center justify-between px-3 pt-4 border-t border-border">
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
