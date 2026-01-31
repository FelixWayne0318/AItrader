"use client";

import Link from "next/link";
import { useRouter } from "next/router";
import { useState, useEffect } from "react";
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
  const [mounted, setMounted] = useState(false);
  const router = useRouter();

  // Fix hydration mismatch
  useEffect(() => {
    setMounted(true);
  }, []);

  // Fetch market data - only after mounted
  const { data: status } = useSWR(
    mounted ? "/api/public/system-status" : null,
    fetcher,
    { refreshInterval: 30000 }
  );

  const { data: sentiment } = useSWR(
    mounted ? "/api/trading/long-short-ratio/BTCUSDT" : null,
    fetcher,
    { refreshInterval: 60000 }
  );

  const { data: markPrice } = useSWR(
    mounted ? "/api/trading/mark-price/BTCUSDT" : null,
    fetcher,
    { refreshInterval: 30000 }
  );

  const { data: openInterest } = useSWR(
    mounted ? "/api/trading/open-interest/BTCUSDT" : null,
    fetcher,
    { refreshInterval: 60000 }
  );

  const { data: ticker } = useSWR(
    mounted ? "/api/trading/ticker/BTCUSDT" : null,
    fetcher,
    { refreshInterval: 10000 }
  );

  const { data: latestSignal } = useSWR(
    mounted ? "/api/public/latest-signal" : null,
    fetcher,
    { refreshInterval: 30000 }
  );

  const { data: branding } = useSWR(
    mounted ? "/api/public/site-branding" : null,
    fetcher,
    { refreshInterval: 300000 }
  );

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
  const getSignalColor = (s: string) => {
    if (s === "BUY" || s === "LONG") return "text-green-500";
    if (s === "SELL" || s === "SHORT") return "text-red-500";
    return "text-foreground";
  };

  return (
    <header className="fixed top-4 inset-x-0 z-50 px-4">
      {/* Floating rounded navbar - NOT full-width black background */}
      <nav className="max-w-7xl mx-auto flex h-14 items-center justify-between px-6 bg-background/80 backdrop-blur-xl border border-border/40 rounded-2xl">
          {/* Logo - Always visible */}
          <Link href="/" className="flex items-center gap-2">
            {branding?.logo_url ? (
              <img
                src={branding.logo_url}
                alt={branding?.site_name || "AlgVex"}
                className="h-7 w-7 rounded-lg object-contain"
              />
            ) : (
              <div className="h-7 w-7 rounded-lg bg-primary flex items-center justify-center">
                <span className="text-primary-foreground font-bold text-sm">A</span>
              </div>
            )}
            <span className="text-lg font-bold">{branding?.site_name || "AlgVex"}</span>
          </Link>

          {/* Desktop Navigation - Hidden on mobile, flex on lg+ */}
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

          {/* Market Metrics - Hidden on mobile, flex on lg+ */}
          {mounted && (
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
                <Brain className={`h-3.5 w-3.5 ${getSignalColor(signal)}`} />
                <span className={`text-xs font-medium ${getSignalColor(signal)}`}>{signal}</span>
              </div>
            </div>
          )}

          {/* Right side - Hidden on mobile, flex on lg+ */}
          <div className="hidden lg:flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={toggleLocale} className="h-8 px-2">
              <Globe className="h-4 w-4" />
              <span className="ml-1 text-xs">{locale.toUpperCase()}</span>
            </Button>
            <Link href="/copy">
              <Button size="sm" className="h-8">{t("hero.cta")}</Button>
            </Link>
          </div>

          {/* Mobile menu button - Visible on mobile, hidden on lg+ */}
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden h-9 w-9"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </Button>
      </nav>

      {/* Mobile Navigation Menu - Separate floating element */}
      {mobileMenuOpen && (
        <div className="lg:hidden mt-2 max-w-7xl mx-auto bg-background/95 backdrop-blur-xl border border-border/40 rounded-2xl p-4">
            {/* Navigation Links */}
            <nav className="flex flex-col gap-1 mb-4">
              {navItems.map((item) => {
                const isActive = router.pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`px-4 py-2.5 rounded-lg transition-all ${
                      isActive
                        ? "bg-primary/10 text-primary font-medium"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                    }`}
                    onClick={() => setMobileMenuOpen(false)}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>

            {/* Market Metrics Grid */}
            {mounted && (
              <div className="border-t border-border pt-4 mb-4">
                <p className="text-xs text-muted-foreground px-2 mb-3 font-medium">Market Data</p>
                <div className="grid grid-cols-2 gap-2">
                  <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/30">
                    <Bot className={`h-4 w-4 ${status?.trading_active ? "text-green-500" : "text-muted-foreground"}`} />
                    <span className={`text-sm font-medium ${status?.trading_active ? "text-green-500" : ""}`}>
                      {status?.trading_active ? "Live" : "Offline"}
                    </span>
                  </div>
                  <div className={`flex items-center gap-2 p-3 rounded-lg ${
                    signal === "BUY" || signal === "LONG" ? "bg-green-500/10" :
                    signal === "SELL" || signal === "SHORT" ? "bg-red-500/10" : "bg-muted/30"
                  }`}>
                    <Brain className={`h-4 w-4 ${getSignalColor(signal)}`} />
                    <span className={`text-sm font-semibold ${getSignalColor(signal)}`}>{signal}</span>
                  </div>
                  <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/30">
                    <Users className={`h-4 w-4 ${longPercent > 50 ? "text-green-500" : "text-red-500"}`} />
                    <span className="text-sm">{longPercent.toFixed(0)}% Long</span>
                  </div>
                  <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/30">
                    <Percent className={`h-4 w-4 ${fundingRate >= 0 ? "text-green-500" : "text-red-500"}`} />
                    <span className={`text-sm ${fundingRate >= 0 ? "text-green-500" : "text-red-500"}`}>
                      {fundingRate >= 0 ? "+" : ""}{fundingRate.toFixed(4)}%
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Bottom Actions */}
            <div className="flex items-center justify-between pt-4 border-t border-border">
              <Button variant="ghost" size="sm" onClick={toggleLocale} className="rounded-lg">
                <Globe className="h-4 w-4 mr-2" />
                {locale === "en" ? "中文" : "English"}
              </Button>
              <Link href="/copy" onClick={() => setMobileMenuOpen(false)}>
                <Button size="sm" className="rounded-lg">
                  {t("hero.cta")}
                </Button>
              </Link>
          </div>
        </div>
      )}
    </header>
  );
}
