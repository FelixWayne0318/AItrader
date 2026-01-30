"use client";

import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";
import { Menu, X, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MarketIntelligenceBar } from "@/components/trading/market-intelligence-bar";
import type { Locale } from "@/lib/i18n";

interface HeaderProps {
  locale: Locale;
  t: (key: string) => string;
  showIntelligenceBar?: boolean;
}

export function Header({ locale, t, showIntelligenceBar = true }: HeaderProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const router = useRouter();

  const toggleLocale = () => {
    const newLocale = locale === "en" ? "zh" : "en";
    router.push(router.pathname, router.asPath, { locale: newLocale });
  };

  const navItems = [
    { href: "/", label: t("nav.home") },
    { href: "/performance", label: t("nav.performance") },
    { href: "/copy", label: t("nav.copy") },
    { href: "/about", label: t("nav.about") },
  ];

  return (
    <>
      <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-lg">
        <div className="container mx-auto px-4">
          <div className="flex h-16 items-center justify-between">
            {/* Logo */}
            <Link href="/" className="flex items-center space-x-2">
              <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
                <span className="text-primary-foreground font-bold text-lg">A</span>
              </div>
              <span className="text-xl font-bold">Algvex</span>
            </Link>

            {/* Desktop Navigation */}
            <nav className="hidden md:flex items-center space-x-8">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="text-muted-foreground hover:text-foreground transition-colors"
                >
                  {item.label}
                </Link>
              ))}
            </nav>

            {/* Right side */}
            <div className="flex items-center space-x-4">
              {/* Language toggle */}
              <Button
                variant="ghost"
                size="icon"
                onClick={toggleLocale}
                className="hidden md:flex"
              >
                <Globe className="h-5 w-5" />
                <span className="ml-1 text-xs">{locale.toUpperCase()}</span>
              </Button>

              {/* CTA Button */}
              <Link href="/copy" className="hidden md:block">
                <Button size="sm">{t("hero.cta")}</Button>
              </Link>

              {/* Mobile menu button */}
              <Button
                variant="ghost"
                size="icon"
                className="md:hidden"
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              >
                {mobileMenuOpen ? (
                  <X className="h-6 w-6" />
                ) : (
                  <Menu className="h-6 w-6" />
                )}
              </Button>
            </div>
          </div>

          {/* Mobile Navigation */}
          {mobileMenuOpen && (
            <div className="md:hidden py-4 border-t border-border">
              <nav className="flex flex-col space-y-4">
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
                <div className="flex items-center justify-between px-2 pt-4 border-t border-border">
                  <Button variant="ghost" size="sm" onClick={toggleLocale}>
                    <Globe className="h-4 w-4 mr-2" />
                    {locale === "en" ? "中文" : "English"}
                  </Button>
                  <Link href="/copy">
                    <Button size="sm">{t("hero.cta")}</Button>
                  </Link>
                </div>
              </nav>
            </div>
          )}
        </div>
      </header>

      {/* Market Intelligence Bar - shown below header */}
      {showIntelligenceBar && (
        <div className="fixed top-16 left-0 right-0 z-40 border-b border-border/30 bg-background/60 backdrop-blur-sm">
          <MarketIntelligenceBar />
        </div>
      )}
    </>
  );
}
