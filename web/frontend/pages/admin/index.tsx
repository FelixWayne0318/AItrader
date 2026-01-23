"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import Head from "next/head";
import useSWR from "swr";
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
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// Admin page - requires authentication
export default function AdminPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [config, setConfig] = useState<any>(null);
  const [socialLinks, setSocialLinks] = useState<any[]>([]);
  const [copyLinks, setCopyLinks] = useState<any[]>([]);
  const [pendingRestart, setPendingRestart] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Check for token on mount
  useEffect(() => {
    const urlToken = router.query.token as string;
    const storedToken = localStorage.getItem("admin_token");

    if (urlToken) {
      localStorage.setItem("admin_token", urlToken);
      setToken(urlToken);
      // Remove token from URL
      router.replace("/admin", undefined, { shallow: true });
    } else if (storedToken) {
      setToken(storedToken);
    }
  }, [router.query.token]);

  // Fetch data when authenticated
  const { data: serviceStatus, mutate: refetchStatus } = useSWR(
    token ? ["/api/admin/service/status", token] : null,
    ([url, t]) =>
      fetch(url, { headers: { Authorization: `Bearer ${t}` } }).then((r) =>
        r.json()
      ),
    { refreshInterval: 5000 }
  );

  useEffect(() => {
    if (token) {
      // Fetch config
      fetch("/api/admin/config", {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then(setConfig)
        .catch(console.error);

      // Fetch social links
      fetch("/api/admin/social-links", {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then(setSocialLinks)
        .catch(console.error);

      // Fetch copy trading links
      fetch("/api/admin/copy-trading", {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then(setCopyLinks)
        .catch(console.error);
    }
  }, [token]);

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

  // Not authenticated - show login
  if (!token) {
    return (
      <>
        <Head>
          <title>Admin Login - Algvex</title>
        </Head>
        <div className="min-h-screen gradient-bg flex items-center justify-center px-4">
          <Card className="w-full max-w-md border-border/50">
            <CardHeader className="text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-primary flex items-center justify-center">
                <span className="text-primary-foreground font-bold text-2xl">A</span>
              </div>
              <CardTitle className="text-2xl">Admin Login</CardTitle>
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

  // Authenticated - show admin panel
  const tabs = [
    { id: "dashboard", label: "Dashboard", icon: Server },
    { id: "strategy", label: "Strategy", icon: Settings },
    { id: "links", label: "Links", icon: LinkIcon },
  ];

  return (
    <>
      <Head>
        <title>Admin Panel - Algvex</title>
      </Head>

      <div className="min-h-screen gradient-bg">
        {/* Header */}
        <header className="border-b border-border/50 bg-background/80 backdrop-blur-lg">
          <div className="container mx-auto px-4">
            <div className="flex h-16 items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
                  <span className="text-primary-foreground font-bold">A</span>
                </div>
                <span className="font-semibold">Algvex Admin</span>
              </div>
              <Button variant="ghost" size="sm" onClick={handleLogout}>
                <LogOut className="h-4 w-4 mr-2" />
                Logout
              </Button>
            </div>
          </div>
        </header>

        {/* Message */}
        {message && (
          <div
            className={`fixed top-20 right-4 p-4 rounded-lg z-50 ${
              message.type === "success"
                ? "bg-[hsl(var(--profit))]/10 text-[hsl(var(--profit))] border border-[hsl(var(--profit))]/30"
                : "bg-[hsl(var(--loss))]/10 text-[hsl(var(--loss))] border border-[hsl(var(--loss))]/30"
            }`}
          >
            {message.text}
          </div>
        )}

        {/* Main */}
        <main className="container mx-auto px-4 py-8">
          {/* Tabs */}
          <div className="flex gap-2 mb-8">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <Button
                  key={tab.id}
                  variant={activeTab === tab.id ? "default" : "outline"}
                  onClick={() => setActiveTab(tab.id)}
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
              {/* Service Status */}
              <Card className="border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Server className="h-5 w-5" />
                    Service Status
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div
                        className={`h-3 w-3 rounded-full ${
                          serviceStatus?.running
                            ? "bg-[hsl(var(--profit))] animate-pulse"
                            : "bg-[hsl(var(--loss))]"
                        }`}
                      />
                      <div>
                        <p className="font-semibold">
                          {serviceStatus?.running ? "Running" : "Stopped"}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          State: {serviceStatus?.state} / {serviceStatus?.sub_state}
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
                        <Button
                          size="sm"
                          onClick={() => handleServiceControl("start")}
                        >
                          <Play className="h-4 w-4 mr-2" />
                          Start
                        </Button>
                      )}
                    </div>
                  </div>

                  {pendingRestart && (
                    <div className="mt-4 p-4 rounded-lg bg-yellow-500/10 border border-yellow-500/30 flex items-center gap-3">
                      <AlertTriangle className="h-5 w-5 text-yellow-500" />
                      <div className="flex-1">
                        <p className="text-yellow-500 font-medium">
                          Configuration changed
                        </p>
                        <p className="text-sm text-muted-foreground">
                          Restart the service to apply changes
                        </p>
                      </div>
                      <Button
                        size="sm"
                        onClick={() => handleServiceControl("restart")}
                      >
                        Restart Now
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
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
                      <label className="text-sm text-muted-foreground">
                        Leverage
                      </label>
                      <input
                        type="number"
                        className="w-full mt-1 px-3 py-2 rounded-lg bg-muted border border-border"
                        defaultValue={config.equity?.leverage || 5}
                        onBlur={(e) =>
                          handleConfigSave("equity.leverage", parseInt(e.target.value))
                        }
                      />
                    </div>
                    <div>
                      <label className="text-sm text-muted-foreground">
                        Base USDT Amount
                      </label>
                      <input
                        type="number"
                        className="w-full mt-1 px-3 py-2 rounded-lg bg-muted border border-border"
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
                        className="w-full mt-1 px-3 py-2 rounded-lg bg-muted border border-border"
                        defaultValue={config.risk?.min_confidence_to_trade || "MEDIUM"}
                        onChange={(e) =>
                          handleConfigSave(
                            "risk.min_confidence_to_trade",
                            e.target.value
                          )
                        }
                      >
                        <option value="LOW">LOW</option>
                        <option value="MEDIUM">MEDIUM</option>
                        <option value="HIGH">HIGH</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-sm text-muted-foreground">
                        Max Position Ratio
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        className="w-full mt-1 px-3 py-2 rounded-lg bg-muted border border-border"
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
                      <span className="w-24 text-sm capitalize">
                        {link.platform}
                      </span>
                      <input
                        type="text"
                        className="flex-1 px-3 py-2 rounded-lg bg-muted border border-border"
                        defaultValue={link.url || ""}
                        placeholder={`https://${link.platform === "twitter" ? "x.com" : "t.me"}/...`}
                        onBlur={(e) =>
                          handleSocialLinkSave(link.platform, e.target.value)
                        }
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
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
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
                        className="w-full px-3 py-2 rounded-lg bg-muted border border-border"
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
        </main>
      </div>
    </>
  );
}
