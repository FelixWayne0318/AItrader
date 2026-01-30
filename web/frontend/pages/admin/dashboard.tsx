"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import Head from "next/head";
import dynamic from "next/dynamic";
import useSWR from "swr";
import {
  Settings,
  Link as LinkIcon,
  Server,
  RefreshCw,
  Power,
  Play,
  LogOut,
  AlertTriangle,
  TrendingUp,
  Activity,
  BarChart3,
  Bell,
  Palette,
  Upload,
  Image,
  Type,
  Globe,
  Mail,
  FileText,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// Dynamic imports for animated components (SSR disabled)
const EquityCurve = dynamic(
  () => import("@/components/admin/equity-curve").then((mod) => mod.EquityCurve),
  { ssr: false, loading: () => <ChartSkeleton /> }
);

const TradeTimeline = dynamic(
  () => import("@/components/admin/trade-timeline").then((mod) => mod.TradeTimeline),
  { ssr: false, loading: () => <ListSkeleton /> }
);

const RiskMetrics = dynamic(
  () => import("@/components/admin/risk-metrics").then((mod) => mod.RiskMetrics),
  { ssr: false, loading: () => <CardSkeleton /> }
);

const AISignalLog = dynamic(
  () => import("@/components/admin/ai-signal-log").then((mod) => mod.AISignalLog),
  { ssr: false, loading: () => <ListSkeleton /> }
);

const PerformanceStats = dynamic(
  () => import("@/components/admin/performance-stats").then((mod) => mod.PerformanceStats),
  { ssr: false, loading: () => <CardSkeleton /> }
);

// Loading skeletons
function ChartSkeleton() {
  return (
    <div className="h-64 bg-muted/30 rounded-lg animate-pulse flex items-center justify-center">
      <BarChart3 className="h-8 w-8 text-muted-foreground/50" />
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((i) => (
        <div key={i} className="h-16 bg-muted/30 rounded-lg animate-pulse" />
      ))}
    </div>
  );
}

function CardSkeleton() {
  return (
    <div className="h-32 bg-muted/30 rounded-lg animate-pulse" />
  );
}

/**
 * Admin Dashboard Page
 *
 * This page uses dynamic imports with ssr: false for all animated components
 * to prevent SSR issues with framer-motion and other browser-only libraries.
 */
export default function AdminDashboard() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [config, setConfig] = useState<any>(null);
  const [socialLinks, setSocialLinks] = useState<any[]>([]);
  const [copyLinks, setCopyLinks] = useState<any[]>([]);
  const [siteSettings, setSiteSettings] = useState<Record<string, string>>({});
  const [pendingRestart, setPendingRestart] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Authentication check
  useEffect(() => {
    const storedToken = localStorage.getItem("admin_token");
    if (!storedToken) {
      router.replace("/admin");
      return;
    }

    // Verify token
    fetch("/api/auth/me", {
      headers: { Authorization: `Bearer ${storedToken}` },
    })
      .then((res) => {
        if (res.ok) {
          setToken(storedToken);
        } else {
          localStorage.removeItem("admin_token");
          router.replace("/admin");
        }
      })
      .catch(() => {
        router.replace("/admin");
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [router]);

  // Fetch service status
  const { data: serviceStatus, mutate: refetchStatus } = useSWR(
    token ? ["/api/admin/service/status", token] : null,
    ([url, t]) =>
      fetch(url, { headers: { Authorization: `Bearer ${t}` } }).then((r) => r.json()),
    { refreshInterval: 5000 }
  );

  // Fetch performance data
  const { data: performanceData } = useSWR(
    token ? ["/api/admin/performance", token] : null,
    ([url, t]) =>
      fetch(url, { headers: { Authorization: `Bearer ${t}` } }).then((r) => r.json()),
    { refreshInterval: 30000 }
  );

  // Fetch recent trades
  const { data: recentTrades } = useSWR(
    token ? ["/api/admin/trades/recent", token] : null,
    ([url, t]) =>
      fetch(url, { headers: { Authorization: `Bearer ${t}` } }).then((r) => r.json()),
    { refreshInterval: 10000 }
  );

  // Fetch AI signals
  const { data: aiSignals } = useSWR(
    token ? ["/api/admin/signals/recent", token] : null,
    ([url, t]) =>
      fetch(url, { headers: { Authorization: `Bearer ${t}` } }).then((r) => r.json()),
    { refreshInterval: 15000 }
  );

  // Fetch config and links
  useEffect(() => {
    if (token) {
      fetch("/api/admin/config", {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then(setConfig)
        .catch(console.error);

      fetch("/api/admin/social-links", {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then(setSocialLinks)
        .catch(console.error);

      fetch("/api/admin/copy-trading", {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then(setCopyLinks)
        .catch(console.error);

      fetch("/api/admin/settings", {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then(setSiteSettings)
        .catch(console.error);
    }
  }, [token]);

  const handleLogout = () => {
    localStorage.removeItem("admin_token");
    router.replace("/admin");
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
        setMessage({ type: "success", text: data.message });
        setPendingRestart(false);
        refetchStatus();
      } else {
        setMessage({ type: "error", text: data.message || "Failed" });
      }
    } catch (e: any) {
      setMessage({ type: "error", text: e.message });
    }

    setTimeout(() => setMessage(null), 5000);
  };

  const handleConfigSave = async (path: string, value: any) => {
    if (!token) return;

    try {
      const res = await fetch("/api/admin/config", {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ path, value }),
      });
      const data = await res.json();

      if (data.success) {
        setMessage({ type: "success", text: `Updated ${path}` });
        setPendingRestart(true);
      } else {
        setMessage({ type: "error", text: "Failed to update config" });
      }
    } catch (e: any) {
      setMessage({ type: "error", text: e.message });
    }

    setTimeout(() => setMessage(null), 5000);
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
      setMessage({ type: "success", text: `Updated ${platform} link` });
    } catch (e: any) {
      setMessage({ type: "error", text: e.message });
    }

    setTimeout(() => setMessage(null), 5000);
  };

  const handleSiteSettingSave = async (key: string, value: string) => {
    if (!token) return;

    try {
      await fetch(`/api/admin/settings/${key}?value=${encodeURIComponent(value)}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      setSiteSettings((prev) => ({ ...prev, [key]: value }));
      setMessage({ type: "success", text: `Updated ${key}` });
    } catch (e: any) {
      setMessage({ type: "error", text: e.message });
    }

    setTimeout(() => setMessage(null), 5000);
  };

  const handleFileUpload = async (type: "logo" | "favicon", file: File) => {
    if (!token) return;

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`/api/admin/upload/${type}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      const data = await res.json();
      if (data.success) {
        setSiteSettings((prev) => ({
          ...prev,
          [`${type}_url`]: data.url,
        }));
        setMessage({ type: "success", text: `${type} uploaded successfully` });
      } else {
        setMessage({ type: "error", text: data.detail || "Upload failed" });
      }
    } catch (e: any) {
      setMessage({ type: "error", text: e.message });
    } finally {
      setUploading(false);
    }

    setTimeout(() => setMessage(null), 5000);
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="min-h-screen gradient-bg flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 mx-auto mb-4 rounded-xl bg-primary flex items-center justify-center animate-pulse">
            <span className="text-primary-foreground font-bold text-xl">A</span>
          </div>
          <p className="text-muted-foreground">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  // Not authenticated
  if (!token) {
    return null;
  }

  const tabs = [
    { id: "dashboard", label: "Dashboard", icon: Activity },
    { id: "strategy", label: "Strategy", icon: Settings },
    { id: "links", label: "Links", icon: LinkIcon },
    { id: "site", label: "Site Settings", icon: Palette },
  ];

  return (
    <>
      <Head>
        <title>Admin Dashboard - AlgVex</title>
      </Head>

      <div className="min-h-screen gradient-bg">
        {/* Header */}
        <header className="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-lg">
          <div className="container mx-auto px-4">
            <div className="flex h-16 items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
                  <span className="text-primary-foreground font-bold">A</span>
                </div>
                <span className="font-semibold">AlgVex Admin</span>
                {serviceStatus?.running && (
                  <span className="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded-full bg-green-500/10 text-green-500 text-xs">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                    Live
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Button variant="ghost" size="icon" className="relative">
                  <Bell className="h-5 w-5" />
                  {pendingRestart && (
                    <span className="absolute top-1 right-1 w-2 h-2 bg-yellow-500 rounded-full" />
                  )}
                </Button>
                <Button variant="ghost" size="sm" onClick={handleLogout}>
                  <LogOut className="h-4 w-4 mr-2" />
                  <span className="hidden sm:inline">Logout</span>
                </Button>
              </div>
            </div>
          </div>
        </header>

        {/* Message Toast */}
        {message && (
          <div
            className={`fixed top-20 right-4 p-4 rounded-lg z-50 shadow-lg ${
              message.type === "success"
                ? "bg-green-500/10 text-green-500 border border-green-500/30"
                : "bg-red-500/10 text-red-500 border border-red-500/30"
            }`}
          >
            {message.text}
          </div>
        )}

        {/* Main Content */}
        <main className="container mx-auto px-4 py-6">
          {/* Tabs */}
          <div className="flex gap-2 mb-6 overflow-x-auto pb-2">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <Button
                  key={tab.id}
                  variant={activeTab === tab.id ? "default" : "outline"}
                  onClick={() => setActiveTab(tab.id)}
                  className="whitespace-nowrap"
                >
                  <Icon className="h-4 w-4 mr-2" />
                  {tab.label}
                </Button>
              );
            })}
          </div>

          {/* Dashboard Tab */}
          {activeTab === "dashboard" && (
            <div className="space-y-6">
              {/* Service Status Card */}
              <Card className="border-border/50">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <Server className="h-5 w-5" />
                    Trading Service
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                    <div className="flex items-center gap-4">
                      <div
                        className={`h-4 w-4 rounded-full ${
                          serviceStatus?.running
                            ? "bg-green-500 animate-pulse shadow-lg shadow-green-500/50"
                            : "bg-red-500"
                        }`}
                      />
                      <div>
                        <p className="font-semibold text-lg">
                          {serviceStatus?.running ? "Running" : "Stopped"}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {serviceStatus?.state} / {serviceStatus?.sub_state}
                        </p>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleServiceControl("restart")}
                      >
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Restart
                      </Button>
                      {serviceStatus?.running ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleServiceControl("stop")}
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

                  {pendingRestart && (
                    <div className="mt-4 p-4 rounded-lg bg-yellow-500/10 border border-yellow-500/30 flex flex-col sm:flex-row items-start sm:items-center gap-3">
                      <AlertTriangle className="h-5 w-5 text-yellow-500 flex-shrink-0" />
                      <div className="flex-1">
                        <p className="text-yellow-500 font-medium">Configuration changed</p>
                        <p className="text-sm text-muted-foreground">
                          Restart the service to apply changes
                        </p>
                      </div>
                      <Button size="sm" onClick={() => handleServiceControl("restart")}>
                        Restart Now
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Performance Stats */}
              <PerformanceStats data={performanceData} />

              {/* Charts Row */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Equity Curve */}
                <Card className="border-border/50">
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-lg">
                      <TrendingUp className="h-5 w-5" />
                      Equity Curve
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <EquityCurve data={performanceData?.equity_history} />
                  </CardContent>
                </Card>

                {/* Risk Metrics */}
                <Card className="border-border/50">
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-lg">
                      <Activity className="h-5 w-5" />
                      Risk Metrics
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <RiskMetrics data={performanceData?.risk_metrics} />
                  </CardContent>
                </Card>
              </div>

              {/* Activity Row */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Recent Trades */}
                <Card className="border-border/50">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg">Recent Trades</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <TradeTimeline trades={recentTrades} />
                  </CardContent>
                </Card>

                {/* AI Signals */}
                <Card className="border-border/50">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg">AI Signal Log</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <AISignalLog signals={aiSignals} />
                  </CardContent>
                </Card>
              </div>
            </div>
          )}

          {/* Strategy Tab */}
          {activeTab === "strategy" && config && (
            <div className="space-y-6">
              {/* Equity Settings */}
              <Card className="border-border/50">
                <CardHeader>
                  <CardTitle>Equity & Leverage</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="text-sm text-muted-foreground">Leverage</label>
                      <input
                        type="number"
                        className="w-full mt-1 px-3 py-2 rounded-lg bg-muted border border-border focus:border-primary focus:outline-none"
                        defaultValue={config.equity?.leverage || 5}
                        onBlur={(e) =>
                          handleConfigSave("equity.leverage", parseInt(e.target.value))
                        }
                      />
                    </div>
                    <div>
                      <label className="text-sm text-muted-foreground">Base USDT Amount</label>
                      <input
                        type="number"
                        className="w-full mt-1 px-3 py-2 rounded-lg bg-muted border border-border focus:border-primary focus:outline-none"
                        defaultValue={config.position_management?.base_usdt_amount || 100}
                        onBlur={(e) =>
                          handleConfigSave(
                            "position_management.base_usdt_amount",
                            parseFloat(e.target.value)
                          )
                        }
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Risk Settings */}
              <Card className="border-border/50">
                <CardHeader>
                  <CardTitle>Risk Management</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="text-sm text-muted-foreground">
                        Min Confidence to Trade
                      </label>
                      <select
                        className="w-full mt-1 px-3 py-2 rounded-lg bg-muted border border-border focus:border-primary focus:outline-none"
                        defaultValue={config.risk?.min_confidence_to_trade || "MEDIUM"}
                        onChange={(e) =>
                          handleConfigSave("risk.min_confidence_to_trade", e.target.value)
                        }
                      >
                        <option value="LOW">LOW</option>
                        <option value="MEDIUM">MEDIUM</option>
                        <option value="HIGH">HIGH</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-sm text-muted-foreground">Max Position Ratio</label>
                      <input
                        type="number"
                        step="0.01"
                        className="w-full mt-1 px-3 py-2 rounded-lg bg-muted border border-border focus:border-primary focus:outline-none"
                        defaultValue={config.position_management?.max_position_ratio || 0.3}
                        onBlur={(e) =>
                          handleConfigSave(
                            "position_management.max_position_ratio",
                            parseFloat(e.target.value)
                          )
                        }
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Links Tab */}
          {activeTab === "links" && (
            <div className="space-y-6">
              {/* Social Links */}
              <Card className="border-border/50">
                <CardHeader>
                  <CardTitle>Social Links</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {socialLinks.map((link) => (
                    <div key={link.platform} className="flex items-center gap-4">
                      <span className="w-24 text-sm capitalize">{link.platform}</span>
                      <input
                        type="text"
                        className="flex-1 px-3 py-2 rounded-lg bg-muted border border-border focus:border-primary focus:outline-none"
                        defaultValue={link.url || ""}
                        placeholder={`https://${link.platform === "twitter" ? "x.com" : "t.me"}/...`}
                        onBlur={(e) => handleSocialLinkSave(link.platform, e.target.value)}
                      />
                    </div>
                  ))}
                </CardContent>
              </Card>

              {/* Copy Trading Links */}
              <Card className="border-border/50">
                <CardHeader>
                  <CardTitle>Copy Trading Links</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {copyLinks.map((link) => (
                    <div
                      key={link.id}
                      className="p-4 rounded-lg bg-muted/30 border border-border/50"
                    >
                      <div className="flex items-center justify-between mb-3">
                        <span className="font-semibold">{link.name}</span>
                        <label className="flex items-center gap-2 text-sm cursor-pointer">
                          <input
                            type="checkbox"
                            className="rounded"
                            defaultChecked={link.enabled}
                            onChange={async (e) => {
                              await fetch(`/api/admin/copy-trading/${link.id}`, {
                                method: "PUT",
                                headers: {
                                  Authorization: `Bearer ${token}`,
                                  "Content-Type": "application/json",
                                },
                                body: JSON.stringify({ enabled: e.target.checked }),
                              });
                            }}
                          />
                          Enabled
                        </label>
                      </div>
                      <input
                        type="text"
                        className="w-full px-3 py-2 rounded-lg bg-muted border border-border focus:border-primary focus:outline-none"
                        defaultValue={link.url || ""}
                        placeholder="Copy trading URL"
                        onBlur={async (e) => {
                          await fetch(`/api/admin/copy-trading/${link.id}`, {
                            method: "PUT",
                            headers: {
                              Authorization: `Bearer ${token}`,
                              "Content-Type": "application/json",
                            },
                            body: JSON.stringify({ url: e.target.value }),
                          });
                          setMessage({ type: "success", text: "Link updated" });
                          setTimeout(() => setMessage(null), 3000);
                        }}
                      />
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          )}

          {/* Site Settings Tab */}
          {activeTab === "site" && (
            <div className="space-y-6">
              {/* Logo & Branding */}
              <Card className="border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Image className="h-5 w-5" />
                    Logo & Branding
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* Logo Upload */}
                  <div>
                    <label className="text-sm text-muted-foreground mb-2 block">Site Logo</label>
                    <div className="flex items-start gap-4">
                      <div className="w-24 h-24 rounded-lg border-2 border-dashed border-border flex items-center justify-center bg-muted/30 overflow-hidden">
                        {siteSettings.logo_url ? (
                          <img
                            src={siteSettings.logo_url}
                            alt="Logo"
                            className="w-full h-full object-contain"
                          />
                        ) : (
                          <Image className="h-8 w-8 text-muted-foreground" />
                        )}
                      </div>
                      <div className="flex-1">
                        <input
                          type="file"
                          accept="image/*"
                          className="hidden"
                          id="logo-upload"
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file) handleFileUpload("logo", file);
                          }}
                        />
                        <label htmlFor="logo-upload">
                          <Button
                            variant="outline"
                            size="sm"
                            className="cursor-pointer"
                            disabled={uploading}
                            asChild
                          >
                            <span>
                              <Upload className="h-4 w-4 mr-2" />
                              {uploading ? "Uploading..." : "Upload Logo"}
                            </span>
                          </Button>
                        </label>
                        <p className="text-xs text-muted-foreground mt-2">
                          Recommended: 200x200px, PNG or SVG
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Favicon Upload */}
                  <div>
                    <label className="text-sm text-muted-foreground mb-2 block">Favicon</label>
                    <div className="flex items-start gap-4">
                      <div className="w-16 h-16 rounded-lg border-2 border-dashed border-border flex items-center justify-center bg-muted/30 overflow-hidden">
                        {siteSettings.favicon_url ? (
                          <img
                            src={siteSettings.favicon_url}
                            alt="Favicon"
                            className="w-full h-full object-contain"
                          />
                        ) : (
                          <Globe className="h-6 w-6 text-muted-foreground" />
                        )}
                      </div>
                      <div className="flex-1">
                        <input
                          type="file"
                          accept="image/*,.ico"
                          className="hidden"
                          id="favicon-upload"
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file) handleFileUpload("favicon", file);
                          }}
                        />
                        <label htmlFor="favicon-upload">
                          <Button
                            variant="outline"
                            size="sm"
                            className="cursor-pointer"
                            disabled={uploading}
                            asChild
                          >
                            <span>
                              <Upload className="h-4 w-4 mr-2" />
                              {uploading ? "Uploading..." : "Upload Favicon"}
                            </span>
                          </Button>
                        </label>
                        <p className="text-xs text-muted-foreground mt-2">
                          Recommended: 32x32px or 64x64px, ICO or PNG
                        </p>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Site Information */}
              <Card className="border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Type className="h-5 w-5" />
                    Site Information
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="text-sm text-muted-foreground">Site Name</label>
                      <input
                        type="text"
                        className="w-full mt-1 px-3 py-2 rounded-lg bg-muted border border-border focus:border-primary focus:outline-none"
                        defaultValue={siteSettings.site_name || "AlgVex"}
                        onBlur={(e) => handleSiteSettingSave("site_name", e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="text-sm text-muted-foreground">Tagline</label>
                      <input
                        type="text"
                        className="w-full mt-1 px-3 py-2 rounded-lg bg-muted border border-border focus:border-primary focus:outline-none"
                        defaultValue={siteSettings.tagline || "AI-Powered Crypto Trading"}
                        onBlur={(e) => handleSiteSettingSave("tagline", e.target.value)}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-sm text-muted-foreground">Site Description (SEO)</label>
                    <textarea
                      className="w-full mt-1 px-3 py-2 rounded-lg bg-muted border border-border focus:border-primary focus:outline-none resize-none"
                      rows={3}
                      defaultValue={
                        siteSettings.site_description ||
                        "Advanced algorithmic trading powered by DeepSeek AI and multi-agent decision system"
                      }
                      onBlur={(e) => handleSiteSettingSave("site_description", e.target.value)}
                    />
                  </div>
                </CardContent>
              </Card>

              {/* Contact Information */}
              <Card className="border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Mail className="h-5 w-5" />
                    Contact Information
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="text-sm text-muted-foreground">Contact Email</label>
                      <input
                        type="email"
                        className="w-full mt-1 px-3 py-2 rounded-lg bg-muted border border-border focus:border-primary focus:outline-none"
                        defaultValue={siteSettings.contact_email || ""}
                        placeholder="contact@algvex.com"
                        onBlur={(e) => handleSiteSettingSave("contact_email", e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="text-sm text-muted-foreground">Support Email</label>
                      <input
                        type="email"
                        className="w-full mt-1 px-3 py-2 rounded-lg bg-muted border border-border focus:border-primary focus:outline-none"
                        defaultValue={siteSettings.support_email || ""}
                        placeholder="support@algvex.com"
                        onBlur={(e) => handleSiteSettingSave("support_email", e.target.value)}
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Legal */}
              <Card className="border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <FileText className="h-5 w-5" />
                    Legal & Disclaimers
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <label className="text-sm text-muted-foreground">Risk Disclaimer</label>
                    <textarea
                      className="w-full mt-1 px-3 py-2 rounded-lg bg-muted border border-border focus:border-primary focus:outline-none resize-none"
                      rows={4}
                      defaultValue={
                        siteSettings.risk_disclaimer ||
                        "Trading cryptocurrencies involves significant risk. Past performance does not guarantee future results. Trade responsibly."
                      }
                      onBlur={(e) => handleSiteSettingSave("risk_disclaimer", e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="text-sm text-muted-foreground">Copyright Text</label>
                    <input
                      type="text"
                      className="w-full mt-1 px-3 py-2 rounded-lg bg-muted border border-border focus:border-primary focus:outline-none"
                      defaultValue={siteSettings.copyright_text || "© 2025 AlgVex. All rights reserved."}
                      onBlur={(e) => handleSiteSettingSave("copyright_text", e.target.value)}
                    />
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </main>
      </div>
    </>
  );
}
