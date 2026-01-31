"use client";

import Link from "next/link";
import { useRouter } from "next/router";
import { useState, useEffect, useRef } from "react";
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
  ChevronDown,
  TrendingUp,
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
  const [metricsExpanded, setMetricsExpanded] = useState(false);
  const metricsRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  // Fix hydration mismatch - only render dynamic content after mount
  useEffect(() => {
    setMounted(true);
  }, []);

  // Close metrics dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (metricsRef.current && !metricsRef.current.contains(event.target as Node)) {
        setMetricsExpanded(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Fetch market data - only after mounted to avoid hydration issues
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

  // Fetch site branding (logo, site name)
  const { data: branding } = useSWR(
    mounted ? "/api/public/site-branding" : null,
    fetcher,
    { refreshInterval: 300000 } // Refresh every 5 minutes
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

  // Calculate metrics (safe defaults for SSR)
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
    <header className="fixed top-3 inset-x-0 z-50 px-4">
      {/* Main navbar - background and height on SAME element */}
      <nav className="mx-auto max-w-7xl flex h-14 items-center justify-between px-4 bg-background/80 backdrop-blur-xl border border-border/40 rounded-2xl">
        {/* Logo - Dynamic from branding settings */}
        <Link href="/" className="flex items-center gap-2.5 group">
          {branding?.logo_url ? (
            <img
              src={branding.logo_url}
              alt={branding?.site_name || "AlgVex"}
              className="h-8 w-8 rounded-xl object-contain shadow-md shadow-primary/20 group-hover:shadow-primary/40 transition-shadow"
            />
          ) : (
            <div className="relative h-8 w-8 rounded-xl bg-gradient-to-br from-primary to-primary/70 flex items-center justify-center shadow-md shadow-primary/20 group-hover:shadow-primary/40 transition-shadow">
              <span className="text-primary-foreground font-bold text-sm">A</span>
              <div className="absolute inset-0 rounded-xl bg-white/10 opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
          )}
          <span className="text-lg font-bold bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text">
            {branding?.site_name || "AlgVex"}
          </span>
        </Link>

        {/* Desktop Navigation - Clean pill style */}
        <div className="hidden lg:flex items-center gap-1 bg-muted/30 rounded-xl p-1">
          {navItems.map((item) => {
            const isActive = router.pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
                  isActive
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground hover:bg-background/50"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </div>

        {/* Market Metrics - Condensed with expandable dropdown */}
        {mounted && (
          <div ref={metricsRef} className="hidden lg:flex items-center gap-2 relative">
            {/* Bot Status - Full display with icon */}
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-muted/40 hover:bg-muted/60 transition-colors">
              <Bot className={`h-3.5 w-3.5 ${status?.trading_active ? "text-green-500" : "text-muted-foreground"}`} />
              <span className="text-xs text-muted-foreground">Bot:</span>
              <span className={`text-xs font-medium ${status?.trading_active ? "text-green-500" : "text-muted-foreground"}`}>
                {status?.trading_active ? "Running" : "Offline"}
              </span>
            </div>

            {/* AI Signal - Full display */}
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors ${
              signal === "BUY" || signal === "LONG"
                ? "bg-green-500/10 hover:bg-green-500/20"
                : signal === "SELL" || signal === "SHORT"
                ? "bg-red-500/10 hover:bg-red-500/20"
                : "bg-muted/40 hover:bg-muted/60"
            }`}>
              <Brain className={`h-3.5 w-3.5 ${getSignalColor(signal)}`} />
              <span className="text-xs text-muted-foreground">Signal:</span>
              <span className={`text-xs font-semibold ${getSignalColor(signal)}`}>{signal}</span>
            </div>

            {/* Expandable metrics button */}
            <button
              onClick={() => setMetricsExpanded(!metricsExpanded)}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-muted/40 hover:bg-muted/60 transition-colors text-xs font-medium text-muted-foreground"
            >
              <TrendingUp className="h-3.5 w-3.5" />
              <span className="hidden xl:inline">Markets</span>
              <ChevronDown className={`h-3 w-3 transition-transform ${metricsExpanded ? "rotate-180" : ""}`} />
            </button>

            {/* Dropdown panel for extended metrics */}
            {metricsExpanded && (
              <div className="absolute top-full right-0 mt-2 w-64 bg-background/95 backdrop-blur-xl border border-border/50 rounded-xl shadow-xl p-3 space-y-2 z-50">
                <div className="text-xs text-muted-foreground font-medium mb-2">Market Metrics</div>

                <div className="flex items-center justify-between p-2 rounded-lg bg-muted/30">
                  <div className="flex items-center gap-2">
                    <Users className={`h-4 w-4 ${longPercent > 50 ? "text-green-500" : "text-red-500"}`} />
                    <span className="text-sm">Long/Short</span>
                  </div>
                  <span className={`text-sm font-semibold ${longPercent > 50 ? "text-green-500" : "text-red-500"}`}>
                    {longPercent.toFixed(1)}%
                  </span>
                </div>

                <div className="flex items-center justify-between p-2 rounded-lg bg-muted/30">
                  <div className="flex items-center gap-2">
                    <Percent className={`h-4 w-4 ${fundingRate >= 0 ? "text-green-500" : "text-red-500"}`} />
                    <span className="text-sm">Funding Rate</span>
                  </div>
                  <span className={`text-sm font-semibold ${fundingRate >= 0 ? "text-green-500" : "text-red-500"}`}>
                    {fundingRate >= 0 ? "+" : ""}{fundingRate.toFixed(4)}%
                  </span>
                </div>

                <div className="flex items-center justify-between p-2 rounded-lg bg-muted/30">
                  <div className="flex items-center gap-2">
                    <BarChart3 className="h-4 w-4 text-blue-500" />
                    <span className="text-sm">Open Interest</span>
                  </div>
                  <span className="text-sm font-semibold">{formatOI(oiValue)}</span>
                </div>

                <div className="flex items-center justify-between p-2 rounded-lg bg-muted/30">
                  <div className="flex items-center gap-2">
                    <Activity className="h-4 w-4 text-purple-500" />
                    <span className="text-sm">24h Volume</span>
                  </div>
                  <span className="text-sm font-semibold">{formatVolume(volume24h)}</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Right side - Desktop */}
        <div className="hidden lg:flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleLocale}
            className="h-8 px-2.5 rounded-lg hover:bg-muted/60"
          >
            <Globe className="h-4 w-4" />
            <span className="ml-1.5 text-xs font-medium">{locale.toUpperCase()}</span>
          </Button>
          <Link href="/copy">
            <Button size="sm" className="h-8 rounded-lg px-4 bg-gradient-to-r from-primary to-primary/80 hover:from-primary/90 hover:to-primary/70 shadow-md shadow-primary/20">
              {t("hero.cta")}
            </Button>
          </Link>
        </div>

        {/* Mobile menu button */}
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden h-9 w-9 rounded-lg"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        >
          {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </Button>
      </nav>

      {/* Mobile Navigation Menu - SEPARATE floating element */}
      {mobileMenuOpen && (
        <div className="lg:hidden mt-2 mx-auto max-w-7xl bg-background/95 backdrop-blur-xl border border-border/40 rounded-2xl shadow-lg p-4">
          {/* Navigation Links */}
          <nav className="flex flex-col gap-1 mb-4">
            {navItems.map((item) => {
              const isActive = router.pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-4 py-2.5 rounded-xl transition-all ${
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

          {/* Market Metrics in Mobile Menu */}
          {mounted && (
            <div className="border-t border-border/30 pt-4 mb-4">
              <p className="text-xs text-muted-foreground px-2 mb-3 font-medium">Market Data</p>
              <div className="grid grid-cols-2 gap-2">
                <div className="flex items-center gap-2 p-3 rounded-xl bg-muted/30">
                  <Bot className={`h-4 w-4 ${status?.trading_active ? "text-green-500" : "text-muted-foreground"}`} />
                  <span className={`text-sm font-medium ${status?.trading_active ? "text-green-500" : ""}`}>
                    {status?.trading_active ? "Live" : "Offline"}
                  </span>
                </div>
                <div className={`flex items-center gap-2 p-3 rounded-xl ${
                  signal === "BUY" || signal === "LONG" ? "bg-green-500/10" :
                  signal === "SELL" || signal === "SHORT" ? "bg-red-500/10" : "bg-muted/30"
                }`}>
                  <Brain className={`h-4 w-4 ${getSignalColor(signal)}`} />
                  <span className={`text-sm font-semibold ${getSignalColor(signal)}`}>{signal}</span>
                </div>
                <div className="flex items-center gap-2 p-3 rounded-xl bg-muted/30">
                  <Users className={`h-4 w-4 ${longPercent > 50 ? "text-green-500" : "text-red-500"}`} />
                  <span className="text-sm">{longPercent.toFixed(0)}% Long</span>
                </div>
                <div className="flex items-center gap-2 p-3 rounded-xl bg-muted/30">
                  <Percent className={`h-4 w-4 ${fundingRate >= 0 ? "text-green-500" : "text-red-500"}`} />
                  <span className={`text-sm ${fundingRate >= 0 ? "text-green-500" : "text-red-500"}`}>
                    {fundingRate >= 0 ? "+" : ""}{fundingRate.toFixed(4)}%
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Bottom Actions */}
          <div className="flex items-center justify-between pt-4 border-t border-border/30">
            <Button variant="ghost" size="sm" onClick={toggleLocale} className="rounded-xl">
              <Globe className="h-4 w-4 mr-2" />
              {locale === "en" ? "中文" : "English"}
            </Button>
            <Link href="/copy" onClick={() => setMobileMenuOpen(false)}>
              <Button size="sm" className="rounded-xl bg-gradient-to-r from-primary to-primary/80 shadow-md shadow-primary/20">
                {t("hero.cta")}
              </Button>
            </Link>
          </div>
        </div>
      )}
    </header>
  );
}
