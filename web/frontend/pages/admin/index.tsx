"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/router";
import Head from "next/head";
import useSWR from "swr";
import dynamic from "next/dynamic";
import {
  Settings,
  Shield,
  Link as LinkIcon,
  Server,
  RefreshCw,
  Power,
  Play,
  LogOut,
  Save,
  AlertTriangle,
  Activity,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Wallet,
  BarChart3,
  FileText,
  ChevronDown,
  ChevronRight,
  Terminal,
  Cpu,
  HardDrive,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  Zap,
  Globe,
  Database,
  Bot,
  Eye,
  EyeOff,
  Copy,
  Check,
  ExternalLink,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

// Dynamic imports for browser-only components (lightweight-charts requires window)
// Reference: https://nextjs.org/docs/app/building-your-application/optimizing/lazy-loading#skipping-ssr
const EquityCurve = dynamic(
  () => import("@/components/charts/equity-curve").then((mod) => mod.EquityCurve),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-[350px] bg-card/50 rounded-xl border border-border">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 border-primary/30 border-t-primary animate-spin" />
          <span className="text-sm text-muted-foreground">Loading chart...</span>
        </div>
      </div>
    )
  }
);

// Standard imports for components that don't require window
import { TradeTimeline } from "@/components/trading/trade-timeline";
import { RiskMetrics } from "@/components/trading/risk-metrics";
import { AISignalLog } from "@/components/trading/ai-signal-log";
import { NotificationCenter, NotificationBell } from "@/components/notifications/notification-center";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { BotStatus, BotStatusBadge } from "@/components/trading/bot-status";
import { PerformanceStats, StatsCard } from "@/components/trading/stats-cards";

// Fetcher for SWR
const fetcher = (url: string, token: string) =>
  fetch(url, { headers: { Authorization: `Bearer ${token}` } }).then((r) => r.json());

// Format number with commas
const formatNumber = (num: number, decimals = 2) => {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(num);
};

// Format timestamp
const formatTime = (timestamp: number) => {
  return new Date(timestamp).toLocaleString();
};

// Config Section Component
interface ConfigSectionProps {
  title: string;
  description: string;
  fields: any[];
  onSave: (path: string, value: any) => void;
}

function ConfigSection({ title, description, fields, onSave }: ConfigSectionProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [localValues, setLocalValues] = useState<Record<string, any>>({});
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const initial: Record<string, any> = {};
    fields.forEach((f) => {
      initial[f.path] = f.value;
    });
    setLocalValues(initial);
  }, [fields]);

  const handleChange = (path: string, value: any, type: string) => {
    let parsedValue = value;
    if (type === "number") parsedValue = parseFloat(value) || 0;
    else if (type === "boolean") parsedValue = value === "true" || value === true;
    setLocalValues((prev) => ({ ...prev, [path]: parsedValue }));
  };

  const handleSave = (path: string) => {
    onSave(path, localValues[path]);
  };

  return (
    <div className="border border-border/50 rounded-xl overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-6 py-4 flex items-center justify-between bg-card hover:bg-muted/30 transition-colors"
      >
        <div className="text-left">
          <h3 className="font-semibold text-foreground">{title}</h3>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
        {isOpen ? (
          <ChevronDown className="h-5 w-5 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-5 w-5 text-muted-foreground" />
        )}
      </button>

      {isOpen && (
        <div className="px-6 py-4 border-t border-border/50 bg-background/50 space-y-4">
          {fields.map((field) => (
            <div key={field.path} className="grid grid-cols-1 md:grid-cols-3 gap-4 items-start">
              <div>
                <label className="text-sm font-medium text-foreground">{field.label}</label>
                {field.description && (
                  <p className="text-xs text-muted-foreground mt-0.5">{field.description}</p>
                )}
              </div>
              <div className="md:col-span-2 flex gap-2">
                {field.type === "select" ? (
                  <select
                    className="flex-1 px-3 py-2 rounded-lg bg-muted border border-border text-foreground"
                    value={localValues[field.path] ?? field.value}
                    onChange={(e) => handleChange(field.path, e.target.value, field.type)}
                  >
                    {field.options?.map((opt: string) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                ) : field.type === "boolean" ? (
                  <select
                    className="flex-1 px-3 py-2 rounded-lg bg-muted border border-border text-foreground"
                    value={String(localValues[field.path] ?? field.value)}
                    onChange={(e) => handleChange(field.path, e.target.value, field.type)}
                  >
                    <option value="true">Enabled</option>
                    <option value="false">Disabled</option>
                  </select>
                ) : field.sensitive ? (
                  <div className="flex-1 flex gap-2">
                    <input
                      type={showSecrets[field.path] ? "text" : "password"}
                      className="flex-1 px-3 py-2 rounded-lg bg-muted border border-border text-foreground font-mono text-sm"
                      value={localValues[field.path] ?? ""}
                      onChange={(e) => handleChange(field.path, e.target.value, field.type)}
                      placeholder="••••••••"
                    />
                    <button
                      type="button"
                      onClick={() =>
                        setShowSecrets((prev) => ({ ...prev, [field.path]: !prev[field.path] }))
                      }
                      className="px-3 py-2 rounded-lg bg-muted border border-border hover:bg-muted/80"
                    >
                      {showSecrets[field.path] ? (
                        <EyeOff className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                ) : (
                  <input
                    type={field.type === "number" ? "number" : "text"}
                    step={field.type === "number" ? "any" : undefined}
                    className="flex-1 px-3 py-2 rounded-lg bg-muted border border-border text-foreground"
                    value={localValues[field.path] ?? ""}
                    onChange={(e) => handleChange(field.path, e.target.value, field.type)}
                  />
                )}
                <Button size="sm" onClick={() => handleSave(field.path)}>
                  <Save className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Position Row Component
function PositionRow({ position }: { position: any }) {
  const isLong = position.positionSide === "LONG" || parseFloat(position.positionAmt) > 0;
  const pnl = parseFloat(position.unRealizedProfit || 0);
  const pnlPercent = parseFloat(position.percentage || 0);

  return (
    <tr className="border-b border-border/30 hover:bg-muted/20">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="font-medium">{position.symbol}</span>
          <span
            className={`px-2 py-0.5 text-xs rounded-full ${
              isLong ? "bg-[hsl(var(--profit))]/20 text-[hsl(var(--profit))]" : "bg-[hsl(var(--loss))]/20 text-[hsl(var(--loss))]"
            }`}
          >
            {isLong ? "LONG" : "SHORT"}
          </span>
        </div>
      </td>
      <td className="px-4 py-3 text-right font-mono">
        {formatNumber(Math.abs(parseFloat(position.positionAmt)), 4)}
      </td>
      <td className="px-4 py-3 text-right font-mono">
        ${formatNumber(parseFloat(position.entryPrice))}
      </td>
      <td className="px-4 py-3 text-right font-mono">
        ${formatNumber(parseFloat(position.markPrice))}
      </td>
      <td className="px-4 py-3 text-right">
        <span className={pnl >= 0 ? "text-[hsl(var(--profit))]" : "text-[hsl(var(--loss))]"}>
          {pnl >= 0 ? "+" : ""}${formatNumber(pnl)}
        </span>
      </td>
      <td className="px-4 py-3 text-right">
        <span
          className={`px-2 py-1 rounded-lg text-xs font-medium ${
            pnl >= 0
              ? "bg-[hsl(var(--profit))]/20 text-[hsl(var(--profit))]"
              : "bg-[hsl(var(--loss))]/20 text-[hsl(var(--loss))]"
          }`}
        >
          {pnl >= 0 ? "+" : ""}
          {formatNumber(pnlPercent)}%
        </span>
      </td>
      <td className="px-4 py-3 text-right font-mono text-muted-foreground">
        {position.leverage}x
      </td>
    </tr>
  );
}

// Order Row Component
function OrderRow({ order }: { order: any }) {
  const isBuy = order.side === "BUY";

  return (
    <tr className="border-b border-border/30 hover:bg-muted/20">
      <td className="px-4 py-3 font-medium">{order.symbol}</td>
      <td className="px-4 py-3">
        <span
          className={`px-2 py-0.5 text-xs rounded-full ${
            isBuy ? "bg-[hsl(var(--profit))]/20 text-[hsl(var(--profit))]" : "bg-[hsl(var(--loss))]/20 text-[hsl(var(--loss))]"
          }`}
        >
          {order.side}
        </span>
      </td>
      <td className="px-4 py-3 text-muted-foreground">{order.type}</td>
      <td className="px-4 py-3 text-right font-mono">{formatNumber(parseFloat(order.origQty), 4)}</td>
      <td className="px-4 py-3 text-right font-mono">
        ${formatNumber(parseFloat(order.price || order.stopPrice || 0))}
      </td>
      <td className="px-4 py-3">
        <span className="px-2 py-0.5 text-xs rounded-full bg-primary/20 text-primary">
          {order.status}
        </span>
      </td>
      <td className="px-4 py-3 text-right text-muted-foreground text-sm">
        {formatTime(order.time)}
      </td>
    </tr>
  );
}

// Admin page - requires authentication
export default function AdminPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [pendingRestart, setPendingRestart] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error" | "warning"; text: string } | null>(null);
  const [logLines, setLogLines] = useState(100);
  const [logSource, setLogSource] = useState<"journalctl" | "file">("journalctl");
  const [copiedText, setCopiedText] = useState<string | null>(null);

  // Check for token on mount
  useEffect(() => {
    const urlToken = router.query.token as string;
    const storedToken = localStorage.getItem("admin_token");

    if (urlToken) {
      localStorage.setItem("admin_token", urlToken);
      setToken(urlToken);
      router.replace("/admin", undefined, { shallow: true });
    } else if (storedToken) {
      setToken(storedToken);
    }
  }, [router.query.token]);

  // Data fetching with SWR
  const { data: serviceStatus, mutate: refetchStatus } = useSWR(
    token ? ["/api/admin/service/status", token] : null,
    ([url, t]) => fetcher(url, t),
    { refreshInterval: 5000 }
  );

  const { data: accountData, mutate: refetchAccount } = useSWR(
    token ? ["/api/trading/account", token] : null,
    ([url, t]) => fetcher(url, t),
    { refreshInterval: 30000 }
  );

  const { data: positionsData, mutate: refetchPositions } = useSWR(
    token ? ["/api/trading/positions", token] : null,
    ([url, t]) => fetcher(url, t),
    { refreshInterval: 10000 }
  );

  const { data: openOrders, mutate: refetchOrders } = useSWR(
    token ? ["/api/trading/orders/open", token] : null,
    ([url, t]) => fetcher(url, t),
    { refreshInterval: 10000 }
  );

  const { data: configSections } = useSWR(
    token ? ["/api/admin/config/sections", token] : null,
    ([url, t]) => fetcher(url, t)
  );

  const { data: systemInfo } = useSWR(
    token ? ["/api/admin/system/info", token] : null,
    ([url, t]) => fetcher(url, t)
  );

  const { data: logsData, mutate: refetchLogs } = useSWR(
    token && activeTab === "logs" ? [`/api/admin/logs?lines=${logLines}&source=${logSource}`, token] : null,
    ([url, t]) => fetcher(url, t),
    { refreshInterval: 5000 }
  );

  const { data: diagnosticsData, mutate: refetchDiagnostics } = useSWR(
    token && activeTab === "system" ? ["/api/admin/system/diagnostics", token] : null,
    ([url, t]) => fetcher(url, t)
  );

  const { data: socialLinks, mutate: refetchSocialLinks } = useSWR(
    token ? ["/api/admin/social-links", token] : null,
    ([url, t]) => fetcher(url, t)
  );

  const { data: copyLinks, mutate: refetchCopyLinks } = useSWR(
    token ? ["/api/admin/copy-trading", token] : null,
    ([url, t]) => fetcher(url, t)
  );

  const { data: btcTicker } = useSWR(
    "/api/trading/ticker/BTCUSDT",
    (url) => fetch(url).then((r) => r.json()),
    { refreshInterval: 5000 }
  );

  const showMessage = useCallback((type: "success" | "error" | "warning", text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  }, []);

  const handleLogin = () => {
    window.location.href = "/api/auth/login";
  };

  const handleLogout = () => {
    localStorage.removeItem("admin_token");
    setToken(null);
  };

  const handleServiceControl = async (action: "restart" | "stop" | "start") => {
    if (!token) return;

    const confirmed = window.confirm(
      `Are you sure you want to ${action} the trading service?`
    );
    if (!confirmed) return;

    try {
      const res = await fetch("/api/admin/service/control", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ action, confirm: true }),
      });
      const data = await res.json();

      if (data.success) {
        showMessage("success", data.message);
        setPendingRestart(false);
        refetchStatus();
      } else {
        showMessage("error", data.message || "Operation failed");
      }
    } catch (e: any) {
      showMessage("error", e.message);
    }
  };

  const handleConfigSave = async (path: string, value: any) => {
    if (!token) return;

    try {
      const res = await fetch("/api/admin/config/value", {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ path, value }),
      });
      const data = await res.json();

      if (data.success) {
        showMessage("success", `Updated: ${path}`);
        setPendingRestart(true);
      } else {
        showMessage("error", data.message || "Failed to update config");
      }
    } catch (e: any) {
      showMessage("error", e.message);
    }
  };

  const handleSocialLinkSave = async (platform: string, url: string) => {
    if (!token) return;

    try {
      await fetch(`/api/admin/social-links/${platform}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ platform, url, enabled: !!url }),
      });
      showMessage("success", `Updated ${platform} link`);
      refetchSocialLinks();
    } catch (e: any) {
      showMessage("error", e.message);
    }
  };

  const handleCopyLinkSave = async (id: number, data: any) => {
    if (!token) return;

    try {
      await fetch(`/api/admin/copy-trading/${id}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
      });
      showMessage("success", "Link updated");
      refetchCopyLinks();
    } catch (e: any) {
      showMessage("error", e.message);
    }
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopiedText(label);
    setTimeout(() => setCopiedText(null), 2000);
  };

  // Not authenticated - show login
  if (!token) {
    return (
      <>
        <Head>
          <title>Admin Login - Algvex</title>
        </Head>
        <div className="min-h-screen gradient-bg flex items-center justify-center px-4">
          <Card className="w-full max-w-md border-border/50 glass">
            <CardHeader className="text-center">
              <div className="w-20 h-20 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-primary to-accent flex items-center justify-center glow-primary">
                <span className="text-primary-foreground font-bold text-3xl">A</span>
              </div>
              <CardTitle className="text-2xl">Admin Panel</CardTitle>
              <CardDescription>Sign in to manage your trading system</CardDescription>
            </CardHeader>
            <CardContent>
              <Button onClick={handleLogin} className="w-full" size="lg">
                <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24">
                  <path
                    fill="currentColor"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  />
                  <path
                    fill="currentColor"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  />
                  <path
                    fill="currentColor"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                  />
                  <path
                    fill="currentColor"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                  />
                </svg>
                Sign in with Google
              </Button>
            </CardContent>
          </Card>
        </div>
      </>
    );
  }

  // Calculate account metrics
  const totalBalance = accountData?.totalWalletBalance ? parseFloat(accountData.totalWalletBalance) : 0;
  const availableBalance = accountData?.availableBalance ? parseFloat(accountData.availableBalance) : 0;
  const totalPnL = accountData?.totalUnrealizedProfit ? parseFloat(accountData.totalUnrealizedProfit) : 0;
  const marginUsed = accountData?.totalInitialMargin ? parseFloat(accountData.totalInitialMargin) : 0;

  // Filter active positions
  const activePositions = positionsData?.filter(
    (p: any) => parseFloat(p.positionAmt) !== 0
  ) || [];

  // Performance data fetching
  const { data: performanceData, mutate: refetchPerformance } = useSWR(
    token ? ["/api/performance/stats", token] : null,
    ([url, t]) => fetcher(url, t),
    { refreshInterval: 60000 }
  );

  const { data: recentTrades } = useSWR(
    token ? ["/api/performance/trades?limit=20", token] : null,
    ([url, t]) => fetcher(url, t),
    { refreshInterval: 30000 }
  );

  const { data: aiSignals, mutate: refetchSignals } = useSWR(
    token ? ["/api/performance/signals?limit=10", token] : null,
    ([url, t]) => fetcher(url, t),
    { refreshInterval: 60000 }
  );

  const { data: notifications, mutate: refetchNotifications } = useSWR(
    token ? ["/api/performance/notifications?limit=50", token] : null,
    ([url, t]) => fetcher(url, t),
    { refreshInterval: 30000 }
  );

  const { data: notificationCount } = useSWR(
    token ? ["/api/performance/notifications/unread-count", token] : null,
    ([url, t]) => fetcher(url, t),
    { refreshInterval: 10000 }
  );

  const handleMarkNotificationRead = async (id: string) => {
    if (!token) return;
    try {
      await fetch(`/api/performance/notifications/${id}/read`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      refetchNotifications();
    } catch (e) {
      console.error(e);
    }
  };

  const handleMarkAllNotificationsRead = async () => {
    if (!token) return;
    try {
      await fetch("/api/performance/notifications/read-all", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      refetchNotifications();
    } catch (e) {
      console.error(e);
    }
  };

  // Tabs configuration
  const tabs = [
    { id: "dashboard", label: "Dashboard", icon: Activity },
    { id: "performance", label: "Performance", icon: BarChart3 },
    { id: "signals", label: "AI Signals", icon: Bot },
    { id: "trading", label: "Trading", icon: TrendingUp },
    { id: "config", label: "Configuration", icon: Settings },
    { id: "logs", label: "Logs", icon: Terminal },
    { id: "system", label: "System", icon: Cpu },
    { id: "links", label: "Links", icon: LinkIcon },
  ];

  return (
    <>
      <Head>
        <title>Admin Panel - Algvex</title>
      </Head>

      <div className="min-h-screen gradient-bg">
        {/* Header */}
        <header className="sticky top-0 z-40 border-b border-border/50 bg-background/80 backdrop-blur-lg">
          <div className="container mx-auto px-4">
            <div className="flex h-16 items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center">
                  <span className="text-primary-foreground font-bold text-lg">A</span>
                </div>
                <div>
                  <span className="font-semibold">Algvex Admin</span>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        serviceStatus?.running ? "bg-[hsl(var(--profit))] animate-pulse" : "bg-[hsl(var(--loss))]"
                      }`}
                    />
                    {serviceStatus?.running ? "Service Running" : "Service Stopped"}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-4">
                {btcTicker && (
                  <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-muted/50">
                    <span className="text-sm text-muted-foreground">BTC</span>
                    <span className="font-mono font-semibold">
                      ${formatNumber(parseFloat(btcTicker.lastPrice))}
                    </span>
                    <span
                      className={`text-xs ${
                        parseFloat(btcTicker.priceChangePercent) >= 0
                          ? "text-[hsl(var(--profit))]"
                          : "text-[hsl(var(--loss))]"
                      }`}
                    >
                      {parseFloat(btcTicker.priceChangePercent) >= 0 ? "+" : ""}
                      {formatNumber(parseFloat(btcTicker.priceChangePercent))}%
                    </span>
                  </div>
                )}
                <ThemeToggle />
                <NotificationBell
                  unreadCount={notificationCount?.data?.count || 0}
                  onClick={() => setActiveTab("notifications")}
                />
                <Button variant="ghost" size="sm" onClick={handleLogout}>
                  <LogOut className="h-4 w-4 mr-2" />
                  Logout
                </Button>
              </div>
            </div>
          </div>
        </header>

        {/* Message Toast */}
        {message && (
          <div
            className={`fixed top-20 right-4 p-4 rounded-xl z-50 animate-slide-in flex items-center gap-3 ${
              message.type === "success"
                ? "bg-[hsl(var(--profit))]/10 text-[hsl(var(--profit))] border border-[hsl(var(--profit))]/30"
                : message.type === "warning"
                ? "bg-yellow-500/10 text-yellow-500 border border-yellow-500/30"
                : "bg-[hsl(var(--loss))]/10 text-[hsl(var(--loss))] border border-[hsl(var(--loss))]/30"
            }`}
          >
            {message.type === "success" ? (
              <CheckCircle className="h-5 w-5" />
            ) : message.type === "warning" ? (
              <AlertTriangle className="h-5 w-5" />
            ) : (
              <XCircle className="h-5 w-5" />
            )}
            {message.text}
          </div>
        )}

        {/* Pending Restart Banner */}
        {pendingRestart && (
          <div className="bg-yellow-500/10 border-b border-yellow-500/30">
            <div className="container mx-auto px-4 py-3 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <AlertTriangle className="h-5 w-5 text-yellow-500" />
                <span className="text-yellow-500">
                  Configuration changed. Restart the service to apply.
                </span>
              </div>
              <Button size="sm" onClick={() => handleServiceControl("restart")}>
                <RefreshCw className="h-4 w-4 mr-2" />
                Restart Now
              </Button>
            </div>
          </div>
        )}

        {/* Main Content */}
        <main className="container mx-auto px-4 py-6">
          {/* Tab Navigation */}
          <div className="flex flex-wrap gap-2 mb-6">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <Button
                  key={tab.id}
                  variant={activeTab === tab.id ? "default" : "outline"}
                  size="sm"
                  onClick={() => setActiveTab(tab.id)}
                  className={activeTab === tab.id ? "" : "border-border/50"}
                >
                  <Icon className="h-4 w-4 mr-2" />
                  {tab.label}
                </Button>
              );
            })}
          </div>

          {/* Dashboard Tab */}
          {activeTab === "dashboard" && (
            <div className="space-y-6 animate-fade-in">
              {/* Service Status Card */}
              <Card className="border-border/50 glass">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2">
                      <Server className="h-5 w-5 text-primary" />
                      Service Status
                    </CardTitle>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleServiceControl("restart")}
                        className="border-border/50"
                      >
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Restart
                      </Button>
                      {serviceStatus?.running ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleServiceControl("stop")}
                          className="border-[hsl(var(--loss))]/50 text-[hsl(var(--loss))] hover:bg-[hsl(var(--loss))]/10"
                        >
                          <Power className="h-4 w-4 mr-2" />
                          Stop
                        </Button>
                      ) : (
                        <Button size="sm" onClick={() => handleServiceControl("start")}>
                          <Play className="h-4 w-4 mr-2" />
                          Start
                        </Button>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-4 rounded-xl bg-muted/30">
                      <p className="text-sm text-muted-foreground">Status</p>
                      <div className="flex items-center gap-2 mt-1">
                        <span
                          className={`h-2.5 w-2.5 rounded-full ${
                            serviceStatus?.running ? "bg-[hsl(var(--profit))]" : "bg-[hsl(var(--loss))]"
                          }`}
                        />
                        <span className="font-semibold">
                          {serviceStatus?.running ? "Running" : "Stopped"}
                        </span>
                      </div>
                    </div>
                    <div className="p-4 rounded-xl bg-muted/30">
                      <p className="text-sm text-muted-foreground">State</p>
                      <p className="font-semibold mt-1">{serviceStatus?.state || "Unknown"}</p>
                    </div>
                    <div className="p-4 rounded-xl bg-muted/30">
                      <p className="text-sm text-muted-foreground">Uptime</p>
                      <p className="font-semibold mt-1">{serviceStatus?.uptime || "N/A"}</p>
                    </div>
                    <div className="p-4 rounded-xl bg-muted/30">
                      <p className="text-sm text-muted-foreground">Memory</p>
                      <p className="font-semibold mt-1">{serviceStatus?.memory || "N/A"}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Account Overview */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <Card className="border-border/50 stat-card">
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-muted-foreground">Total Balance</p>
                        <p className="text-2xl font-bold mt-1">
                          ${formatNumber(totalBalance)}
                        </p>
                      </div>
                      <div className="h-12 w-12 rounded-xl bg-primary/20 flex items-center justify-center">
                        <Wallet className="h-6 w-6 text-primary" />
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card className="border-border/50 stat-card">
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-muted-foreground">Available</p>
                        <p className="text-2xl font-bold mt-1">
                          ${formatNumber(availableBalance)}
                        </p>
                      </div>
                      <div className="h-12 w-12 rounded-xl bg-accent/20 flex items-center justify-center">
                        <DollarSign className="h-6 w-6 text-accent" />
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card className="border-border/50 stat-card">
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-muted-foreground">Unrealized PnL</p>
                        <p
                          className={`text-2xl font-bold mt-1 ${
                            totalPnL >= 0 ? "text-[hsl(var(--profit))]" : "text-[hsl(var(--loss))]"
                          }`}
                        >
                          {totalPnL >= 0 ? "+" : ""}${formatNumber(totalPnL)}
                        </p>
                      </div>
                      <div
                        className={`h-12 w-12 rounded-xl flex items-center justify-center ${
                          totalPnL >= 0 ? "bg-[hsl(var(--profit))]/20" : "bg-[hsl(var(--loss))]/20"
                        }`}
                      >
                        {totalPnL >= 0 ? (
                          <TrendingUp className="h-6 w-6 text-[hsl(var(--profit))]" />
                        ) : (
                          <TrendingDown className="h-6 w-6 text-[hsl(var(--loss))]" />
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card className="border-border/50 stat-card">
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-muted-foreground">Margin Used</p>
                        <p className="text-2xl font-bold mt-1">
                          ${formatNumber(marginUsed)}
                        </p>
                      </div>
                      <div className="h-12 w-12 rounded-xl bg-yellow-500/20 flex items-center justify-center">
                        <Shield className="h-6 w-6 text-yellow-500" />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Active Positions */}
              <Card className="border-border/50">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2">
                      <BarChart3 className="h-5 w-5 text-primary" />
                      Active Positions ({activePositions.length})
                    </CardTitle>
                    <Button variant="ghost" size="sm" onClick={() => refetchPositions()}>
                      <RefreshCw className="h-4 w-4" />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {activePositions.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead>
                          <tr className="border-b border-border/50">
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                              Symbol
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">
                              Size
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">
                              Entry
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">
                              Mark
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">
                              PnL
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">
                              ROE
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">
                              Leverage
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {activePositions.map((position: any, idx: number) => (
                            <PositionRow key={idx} position={position} />
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">
                      <BarChart3 className="h-12 w-12 mx-auto mb-4 opacity-50" />
                      <p>No active positions</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}

          {/* Performance Tab */}
          {activeTab === "performance" && (
            <div className="space-y-6 animate-fade-in">
              {/* Performance Stats Cards */}
              {performanceData?.data && (
                <PerformanceStats
                  stats={performanceData.data}
                  loading={!performanceData}
                />
              )}

              {/* Equity Curve and Risk Metrics */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Equity Curve */}
                <Card className="border-border/50 lg:col-span-2">
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <CardTitle className="flex items-center gap-2">
                        <TrendingUp className="h-5 w-5 text-primary" />
                        Equity Curve
                      </CardTitle>
                      <Button variant="ghost" size="sm" onClick={() => refetchPerformance()}>
                        <RefreshCw className="h-4 w-4" />
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <EquityCurve
                      data={performanceData?.data?.equity_curve || []}
                      height={350}
                    />
                  </CardContent>
                </Card>

                {/* Bot Status */}
                <div className="space-y-4">
                  <BotStatus
                    status={serviceStatus?.running ? "running" : "stopped"}
                    timerIntervalSec={900}
                  />

                  {/* Quick Stats */}
                  <Card className="border-border/50">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Risk Metrics</CardTitle>
                    </CardHeader>
                    <CardContent>
                      {performanceData?.data && (
                        <div className="space-y-3">
                          <div className="flex justify-between">
                            <span className="text-sm text-muted-foreground">Profit Factor</span>
                            <span className={`font-semibold ${performanceData.data.profit_factor >= 1.5 ? 'text-[hsl(var(--profit))]' : 'text-[hsl(var(--warning))]'}`}>
                              {performanceData.data.profit_factor?.toFixed(2)}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-sm text-muted-foreground">Sharpe Ratio</span>
                            <span className={`font-semibold ${performanceData.data.sharpe_ratio >= 1 ? 'text-[hsl(var(--profit))]' : 'text-muted-foreground'}`}>
                              {performanceData.data.sharpe_ratio?.toFixed(2)}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-sm text-muted-foreground">Max Drawdown</span>
                            <span className="font-semibold text-[hsl(var(--loss))]">
                              ${performanceData.data.max_drawdown?.toFixed(2)}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-sm text-muted-foreground">Best Trade</span>
                            <span className="font-semibold text-[hsl(var(--profit))]">
                              +${performanceData.data.best_trade?.toFixed(2)}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-sm text-muted-foreground">Worst Trade</span>
                            <span className="font-semibold text-[hsl(var(--loss))]">
                              ${performanceData.data.worst_trade?.toFixed(2)}
                            </span>
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </div>
              </div>

              {/* Trade History Timeline */}
              <Card className="border-border/50">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2">
                    <Clock className="h-5 w-5 text-primary" />
                    Recent Trades
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <TradeTimeline trades={recentTrades?.data || []} maxItems={10} />
                </CardContent>
              </Card>
            </div>
          )}

          {/* AI Signals Tab */}
          {activeTab === "signals" && (
            <div className="space-y-6 animate-fade-in">
              <Card className="border-border/50">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="flex items-center gap-2">
                        <Bot className="h-5 w-5 text-primary" />
                        AI Analysis History
                      </CardTitle>
                      <CardDescription>
                        Bull vs Bear debate analysis with Judge decisions
                      </CardDescription>
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => refetchSignals()}>
                      <RefreshCw className="h-4 w-4" />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <AISignalLog signals={aiSignals?.data || []} maxItems={10} />
                </CardContent>
              </Card>
            </div>
          )}

          {/* Notifications Tab */}
          {activeTab === "notifications" && (
            <div className="space-y-6 animate-fade-in">
              <Card className="border-border/50">
                <CardContent className="p-6">
                  <NotificationCenter
                    notifications={notifications?.data || []}
                    unreadCount={notificationCount?.data?.count || 0}
                    onMarkAsRead={handleMarkNotificationRead}
                    onMarkAllAsRead={handleMarkAllNotificationsRead}
                  />
                </CardContent>
              </Card>
            </div>
          )}

          {/* Trading Tab */}
          {activeTab === "trading" && (
            <div className="space-y-6 animate-fade-in">
              {/* Open Orders */}
              <Card className="border-border/50">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2">
                      <FileText className="h-5 w-5 text-primary" />
                      Open Orders ({openOrders?.length || 0})
                    </CardTitle>
                    <Button variant="ghost" size="sm" onClick={() => refetchOrders()}>
                      <RefreshCw className="h-4 w-4" />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {openOrders && openOrders.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead>
                          <tr className="border-b border-border/50">
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                              Symbol
                            </th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                              Side
                            </th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                              Type
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">
                              Quantity
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">
                              Price
                            </th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                              Status
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">
                              Time
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {openOrders.map((order: any, idx: number) => (
                            <OrderRow key={idx} order={order} />
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">
                      <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                      <p>No open orders</p>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Positions */}
              <Card className="border-border/50">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5 text-primary" />
                    All Positions
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {activePositions.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead>
                          <tr className="border-b border-border/50">
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                              Symbol
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">
                              Size
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">
                              Entry
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">
                              Mark
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">
                              PnL
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">
                              ROE
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">
                              Leverage
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {activePositions.map((position: any, idx: number) => (
                            <PositionRow key={idx} position={position} />
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">
                      <BarChart3 className="h-12 w-12 mx-auto mb-4 opacity-50" />
                      <p>No active positions</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}

          {/* Configuration Tab */}
          {activeTab === "config" && (
            <div className="space-y-4 animate-fade-in">
              <Card className="border-border/50 mb-6">
                <CardContent className="p-4">
                  <div className="flex items-center gap-3">
                    <AlertCircle className="h-5 w-5 text-primary" />
                    <p className="text-sm text-muted-foreground">
                      Changes to configuration will require a service restart to take effect.
                      Configuration is saved to <code className="text-primary">configs/base.yaml</code>.
                    </p>
                  </div>
                </CardContent>
              </Card>

              {configSections?.sections?.map((section: any) => (
                <ConfigSection
                  key={section.id}
                  title={section.title}
                  description={section.description}
                  fields={section.fields}
                  onSave={handleConfigSave}
                />
              ))}
            </div>
          )}

          {/* Logs Tab */}
          {activeTab === "logs" && (
            <div className="space-y-4 animate-fade-in">
              <Card className="border-border/50">
                <CardHeader className="pb-3">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <CardTitle className="flex items-center gap-2">
                      <Terminal className="h-5 w-5 text-primary" />
                      System Logs
                    </CardTitle>
                    <div className="flex items-center gap-3">
                      <select
                        className="px-3 py-2 rounded-lg bg-muted border border-border text-sm"
                        value={logSource}
                        onChange={(e) => setLogSource(e.target.value as "journalctl" | "file")}
                      >
                        <option value="journalctl">journalctl</option>
                        <option value="file">Log File</option>
                      </select>
                      <select
                        className="px-3 py-2 rounded-lg bg-muted border border-border text-sm"
                        value={logLines}
                        onChange={(e) => setLogLines(parseInt(e.target.value))}
                      >
                        <option value="50">50 lines</option>
                        <option value="100">100 lines</option>
                        <option value="200">200 lines</option>
                        <option value="500">500 lines</option>
                      </select>
                      <Button variant="outline" size="sm" onClick={() => refetchLogs()}>
                        <RefreshCw className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="log-viewer bg-[hsl(222,47%,4%)] rounded-xl p-4 font-mono text-xs overflow-auto max-h-[600px]">
                    {logsData?.logs ? (
                      logsData.logs.split("\n").map((line: string, idx: number) => (
                        <div key={idx} className="log-line py-0.5 hover:bg-muted/20">
                          <span
                            className={
                              line.includes("ERROR")
                                ? "text-[hsl(var(--loss))]"
                                : line.includes("WARNING")
                                ? "text-yellow-500"
                                : line.includes("INFO")
                                ? "text-primary"
                                : "text-muted-foreground"
                            }
                          >
                            {line}
                          </span>
                        </div>
                      ))
                    ) : (
                      <p className="text-muted-foreground">Loading logs...</p>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* System Tab */}
          {activeTab === "system" && (
            <div className="space-y-6 animate-fade-in">
              {/* System Info */}
              <Card className="border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Cpu className="h-5 w-5 text-primary" />
                    System Information
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <div className="p-4 rounded-xl bg-muted/30">
                      <p className="text-sm text-muted-foreground">Python Version</p>
                      <p className="font-mono mt-1">{systemInfo?.python_version || "N/A"}</p>
                    </div>
                    <div className="p-4 rounded-xl bg-muted/30">
                      <p className="text-sm text-muted-foreground">NautilusTrader</p>
                      <p className="font-mono mt-1">{systemInfo?.nautilus_version || "N/A"}</p>
                    </div>
                    <div className="p-4 rounded-xl bg-muted/30">
                      <p className="text-sm text-muted-foreground">Git Commit</p>
                      <div className="flex items-center gap-2 mt-1">
                        <p className="font-mono truncate">{systemInfo?.git_commit?.slice(0, 8) || "N/A"}</p>
                        {systemInfo?.git_commit && (
                          <button
                            onClick={() => copyToClipboard(systemInfo.git_commit, "commit")}
                            className="text-muted-foreground hover:text-foreground"
                          >
                            {copiedText === "commit" ? (
                              <Check className="h-4 w-4 text-[hsl(var(--profit))]" />
                            ) : (
                              <Copy className="h-4 w-4" />
                            )}
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="p-4 rounded-xl bg-muted/30">
                      <p className="text-sm text-muted-foreground">Git Branch</p>
                      <p className="font-mono mt-1">{systemInfo?.git_branch || "N/A"}</p>
                    </div>
                    <div className="p-4 rounded-xl bg-muted/30">
                      <p className="text-sm text-muted-foreground">Platform</p>
                      <p className="font-mono mt-1">{systemInfo?.platform || "N/A"}</p>
                    </div>
                    <div className="p-4 rounded-xl bg-muted/30">
                      <p className="text-sm text-muted-foreground">Config Environment</p>
                      <p className="font-mono mt-1">{systemInfo?.config_env || "N/A"}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Diagnostics */}
              <Card className="border-border/50">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2">
                      <Activity className="h-5 w-5 text-primary" />
                      System Diagnostics
                    </CardTitle>
                    <Button variant="outline" size="sm" onClick={() => refetchDiagnostics()}>
                      <RefreshCw className="h-4 w-4 mr-2" />
                      Run Diagnostics
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {diagnosticsData?.checks ? (
                    <div className="space-y-3">
                      {diagnosticsData.checks.map((check: any, idx: number) => (
                        <div
                          key={idx}
                          className={`p-4 rounded-xl flex items-center justify-between ${
                            check.status === "pass"
                              ? "bg-[hsl(var(--profit))]/10 border border-[hsl(var(--profit))]/20"
                              : check.status === "warn"
                              ? "bg-yellow-500/10 border border-yellow-500/20"
                              : "bg-[hsl(var(--loss))]/10 border border-[hsl(var(--loss))]/20"
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            {check.status === "pass" ? (
                              <CheckCircle className="h-5 w-5 text-[hsl(var(--profit))]" />
                            ) : check.status === "warn" ? (
                              <AlertTriangle className="h-5 w-5 text-yellow-500" />
                            ) : (
                              <XCircle className="h-5 w-5 text-[hsl(var(--loss))]" />
                            )}
                            <div>
                              <p className="font-medium">{check.name}</p>
                              <p className="text-sm text-muted-foreground">{check.message}</p>
                            </div>
                          </div>
                          <span
                            className={`px-3 py-1 rounded-full text-xs font-medium ${
                              check.status === "pass"
                                ? "bg-[hsl(var(--profit))]/20 text-[hsl(var(--profit))]"
                                : check.status === "warn"
                                ? "bg-yellow-500/20 text-yellow-500"
                                : "bg-[hsl(var(--loss))]/20 text-[hsl(var(--loss))]"
                            }`}
                          >
                            {check.status.toUpperCase()}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">
                      <Activity className="h-12 w-12 mx-auto mb-4 opacity-50" />
                      <p>Click "Run Diagnostics" to check system health</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}

          {/* Links Tab */}
          {activeTab === "links" && (
            <div className="space-y-6 animate-fade-in">
              {/* Social Links */}
              <Card className="border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Globe className="h-5 w-5 text-primary" />
                    Social Links
                  </CardTitle>
                  <CardDescription>
                    Configure your social media links displayed on the website
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {socialLinks?.map((link: any) => (
                    <div key={link.platform} className="flex items-center gap-4">
                      <span className="w-24 text-sm font-medium capitalize">{link.platform}</span>
                      <input
                        type="text"
                        className="flex-1 px-4 py-2.5 rounded-lg bg-muted border border-border text-foreground"
                        defaultValue={link.url || ""}
                        placeholder={`https://${link.platform === "twitter" ? "x.com" : "t.me"}/...`}
                        onBlur={(e) => handleSocialLinkSave(link.platform, e.target.value)}
                      />
                      <a
                        href={link.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`p-2.5 rounded-lg border border-border ${
                          link.url ? "hover:bg-muted" : "opacity-50 pointer-events-none"
                        }`}
                      >
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    </div>
                  ))}
                </CardContent>
              </Card>

              {/* Copy Trading Links */}
              <Card className="border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Bot className="h-5 w-5 text-primary" />
                    Copy Trading Links
                  </CardTitle>
                  <CardDescription>
                    Manage copy trading platform links for your followers
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {copyLinks?.map((link: any) => (
                    <div
                      key={link.id}
                      className="p-5 rounded-xl bg-muted/30 border border-border/50 space-y-4"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className="h-10 w-10 rounded-lg bg-primary/20 flex items-center justify-center">
                            <Zap className="h-5 w-5 text-primary" />
                          </div>
                          <div>
                            <p className="font-semibold">{link.name}</p>
                            <p className="text-sm text-muted-foreground">{link.platform}</p>
                          </div>
                        </div>
                        <label className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            className="w-4 h-4 rounded border-border"
                            defaultChecked={link.enabled}
                            onChange={(e) =>
                              handleCopyLinkSave(link.id, { enabled: e.target.checked })
                            }
                          />
                          <span className="text-sm">Enabled</span>
                        </label>
                      </div>
                      <input
                        type="text"
                        className="w-full px-4 py-2.5 rounded-lg bg-muted border border-border text-foreground"
                        defaultValue={link.url || ""}
                        placeholder="Copy trading URL"
                        onBlur={(e) => handleCopyLinkSave(link.id, { url: e.target.value })}
                      />
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          )}
        </main>

        {/* Footer */}
        <footer className="border-t border-border/50 mt-12">
          <div className="container mx-auto px-4 py-6">
            <div className="flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-muted-foreground">
              <p>Algvex Admin Panel v3.6</p>
              <div className="flex items-center gap-4">
                <a
                  href="https://github.com/FelixWayne0318/AItrader"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-foreground transition-colors"
                >
                  GitHub
                </a>
                <a href="/" className="hover:text-foreground transition-colors">
                  Back to Website
                </a>
              </div>
            </div>
          </div>
        </footer>
      </div>
    </>
  );
}
