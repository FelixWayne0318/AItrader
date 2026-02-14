"use client";

import { useEffect, useState, useCallback, useRef } from "react";
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
  Target,
  Terminal,
  Wrench,
  ChevronDown,
  ChevronRight,
  Check,
  X,
  Info,
  AlertCircle,
  CheckCircle,
  Monitor,
  Cpu,
  HardDrive,
  GitBranch,
  Clock,
  Save,
} from "lucide-react";

import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useTranslation, type Locale } from "@/lib/i18n";
import { AdminTradeAnalysis } from "@/components/trade-evaluation/AdminTradeAnalysis";

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

// ============================================================================
// Config Field Renderer - renders fields from /api/admin/config/sections
// ============================================================================
interface ConfigField {
  path: string;
  label: string;
  type: string;
  value: any;
  description?: string;
  options?: string[];
  sensitive?: boolean;
}

interface ConfigSection {
  id: string;
  title: string;
  description: string;
  fields: ConfigField[];
}

function ConfigFieldInput({
  field,
  onSave,
}: {
  field: ConfigField;
  onSave: (path: string, value: any) => void;
}) {
  const [localValue, setLocalValue] = useState(field.value);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setLocalValue(field.value);
    setDirty(false);
  }, [field.value]);

  const handleChange = (newValue: any) => {
    setLocalValue(newValue);
    setDirty(true);
  };

  const handleSave = () => {
    if (!dirty) return;
    let val = localValue;
    if (field.type === "number") {
      val = Number(val);
      if (isNaN(val)) return;
    }
    onSave(field.path, val);
    setDirty(false);
  };

  const inputClass =
    "w-full px-3 py-2 rounded-lg bg-muted border border-border focus:border-primary focus:outline-none text-sm transition-colors" +
    (dirty ? " border-yellow-500/50" : "");

  if (field.sensitive) {
    return (
      <div>
        <label className="text-sm text-muted-foreground flex items-center gap-1.5">
          {field.label}
          {field.description && (
            <span title={field.description} className="cursor-help">
              <Info className="h-3 w-3 text-muted-foreground/50" />
            </span>
          )}
        </label>
        <input
          type="password"
          className={inputClass + " mt-1"}
          value="********"
          disabled
        />
        <p className="text-xs text-muted-foreground mt-1">Set via ~/.env.aitrader</p>
      </div>
    );
  }

  if (field.type === "boolean") {
    return (
      <div className="flex items-center justify-between py-1">
        <div>
          <label className="text-sm font-medium">{field.label}</label>
          {field.description && (
            <p className="text-xs text-muted-foreground">{field.description}</p>
          )}
        </div>
        <button
          onClick={() => {
            const newVal = !localValue;
            setLocalValue(newVal);
            onSave(field.path, newVal);
          }}
          className={`relative w-11 h-6 rounded-full transition-colors ${
            localValue ? "bg-primary" : "bg-muted-foreground/30"
          }`}
        >
          <span
            className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-sm ${
              localValue ? "translate-x-5" : ""
            }`}
          />
        </button>
      </div>
    );
  }

  if (field.type === "select" && field.options) {
    return (
      <div>
        <label className="text-sm text-muted-foreground flex items-center gap-1.5">
          {field.label}
          {field.description && (
            <span title={field.description} className="cursor-help">
              <Info className="h-3 w-3 text-muted-foreground/50" />
            </span>
          )}
        </label>
        <select
          className={inputClass + " mt-1"}
          value={localValue ?? ""}
          onChange={(e) => {
            setLocalValue(e.target.value);
            onSave(field.path, e.target.value);
          }}
        >
          {field.options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>
    );
  }

  // number or string
  return (
    <div>
      <label className="text-sm text-muted-foreground flex items-center gap-1.5">
        {field.label}
        {field.description && (
          <span title={field.description} className="cursor-help">
            <Info className="h-3 w-3 text-muted-foreground/50" />
          </span>
        )}
      </label>
      <div className="flex gap-2 mt-1">
        <input
          type={field.type === "number" ? "number" : "text"}
          step={field.type === "number" ? "any" : undefined}
          className={inputClass}
          value={localValue ?? ""}
          onChange={(e) => handleChange(e.target.value)}
          onBlur={handleSave}
          onKeyDown={(e) => e.key === "Enter" && handleSave()}
        />
        {dirty && (
          <Button size="sm" onClick={handleSave} className="px-2 h-[38px]">
            <Save className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  );
}

function ConfigSectionCard({
  section,
  onSave,
  defaultOpen = false,
}: {
  section: ConfigSection;
  onSave: (path: string, value: any) => void;
  defaultOpen?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <Card className="border-border/50">
      <CardHeader
        className="cursor-pointer select-none pb-3"
        onClick={() => setIsOpen(!isOpen)}
      >
        <CardTitle className="flex items-center justify-between text-base">
          <div>
            <span>{section.title}</span>
            <span className="text-xs text-muted-foreground font-normal ml-2">
              ({section.fields.length} fields)
            </span>
          </div>
          {isOpen ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </CardTitle>
        {!isOpen && section.description && (
          <p className="text-xs text-muted-foreground">{section.description}</p>
        )}
      </CardHeader>
      {isOpen && (
        <CardContent className="space-y-4 pt-0">
          {section.description && (
            <p className="text-xs text-muted-foreground pb-2 border-b border-border/30">
              {section.description}
            </p>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {section.fields.map((field) => (
              <ConfigFieldInput key={field.path} field={field} onSave={onSave} />
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  );
}

// ============================================================================
// Logs Viewer Component
// ============================================================================
function LogsViewer({ token }: { token: string }) {
  const [logs, setLogs] = useState("");
  const [loading, setLoading] = useState(false);
  const [lines, setLines] = useState(100);
  const [source, setSource] = useState<"journalctl" | "file">("journalctl");
  const [autoRefresh, setAutoRefresh] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `/api/admin/service/logs?lines=${lines}&source=${source}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const data = await res.json();
      setLogs(data.logs || "No logs available");
    } catch {
      setLogs("Failed to fetch logs");
    }
    setLoading(false);
  }, [token, lines, source]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchLogs, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchLogs]);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <Card className="border-border/50">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between text-lg">
          <div className="flex items-center gap-2">
            <Terminal className="h-5 w-5" />
            Service Logs
          </div>
          <div className="flex items-center gap-2">
            <select
              className="px-2 py-1 rounded bg-muted border border-border text-xs"
              value={source}
              onChange={(e) => setSource(e.target.value as "journalctl" | "file")}
            >
              <option value="journalctl">journalctl</option>
              <option value="file">Log File</option>
            </select>
            <select
              className="px-2 py-1 rounded bg-muted border border-border text-xs"
              value={lines}
              onChange={(e) => setLines(Number(e.target.value))}
            >
              <option value={50}>50 lines</option>
              <option value={100}>100 lines</option>
              <option value={200}>200 lines</option>
              <option value={500}>500 lines</option>
            </select>
            <Button
              variant={autoRefresh ? "default" : "outline"}
              size="sm"
              onClick={() => setAutoRefresh(!autoRefresh)}
              className="h-7 text-xs"
            >
              {autoRefresh ? "Auto" : "Manual"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchLogs}
              disabled={loading}
              className="h-7 text-xs"
            >
              <RefreshCw className={`h-3 w-3 mr-1 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="bg-black/80 rounded-lg p-4 max-h-[600px] overflow-auto font-mono text-xs text-green-400 whitespace-pre-wrap leading-relaxed">
          {logs}
          <div ref={logsEndRef} />
        </div>
      </CardContent>
    </Card>
  );
}

// ============================================================================
// Diagnostics Component
// ============================================================================
function DiagnosticsPanel({ token }: { token: string }) {
  const [diagnostics, setDiagnostics] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const runDiagnostics = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/admin/system/diagnostics", {
        headers: { Authorization: `Bearer ${token}` },
      });
      setDiagnostics(await res.json());
    } catch {
      setDiagnostics({ checks: [{ name: "Connection", status: "fail", message: "Failed to connect to backend" }] });
    }
    setLoading(false);
  };

  useEffect(() => {
    runDiagnostics();
  }, []);

  const statusIcon = (status: string) => {
    if (status === "pass") return <CheckCircle className="h-4 w-4 text-green-500" />;
    if (status === "warn") return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
    return <X className="h-4 w-4 text-red-500" />;
  };

  return (
    <Card className="border-border/50">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between text-lg">
          <div className="flex items-center gap-2">
            <Wrench className="h-5 w-5" />
            System Diagnostics
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={runDiagnostics}
            disabled={loading}
            className="h-7 text-xs"
          >
            <RefreshCw className={`h-3 w-3 mr-1 ${loading ? "animate-spin" : ""}`} />
            Re-run
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!diagnostics ? (
          <div className="text-sm text-muted-foreground">Running diagnostics...</div>
        ) : (
          <div className="space-y-2">
            {diagnostics.checks?.map((check: any, idx: number) => (
              <div
                key={idx}
                className={`flex items-center gap-3 p-3 rounded-lg border ${
                  check.status === "pass"
                    ? "bg-green-500/5 border-green-500/20"
                    : check.status === "warn"
                    ? "bg-yellow-500/5 border-yellow-500/20"
                    : "bg-red-500/5 border-red-500/20"
                }`}
              >
                {statusIcon(check.status)}
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-medium">{check.name}</span>
                  <p className="text-xs text-muted-foreground truncate">{check.message}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ============================================================================
// System Info Component
// ============================================================================
function SystemInfoPanel({ token }: { token: string }) {
  const [info, setInfo] = useState<any>(null);

  useEffect(() => {
    fetch("/api/admin/system/info", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(setInfo)
      .catch(() => {});
  }, [token]);

  if (!info) return <CardSkeleton />;

  const items = [
    { icon: Cpu, label: "Python", value: info.python_version || "N/A" },
    { icon: HardDrive, label: "NautilusTrader", value: info.nautilus_version || "N/A" },
    { icon: GitBranch, label: "Git Branch", value: info.git_branch || "N/A" },
    { icon: Clock, label: "Last Commit", value: info.git_commit ? `${info.git_commit} (${info.git_commit_date?.split(" ")[0] || ""})` : "N/A" },
    { icon: Server, label: "Service", value: info.service_name || "N/A" },
    { icon: Monitor, label: "Path", value: info.aitrader_path || "N/A" },
  ];

  return (
    <Card className="border-border/50">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-lg">
          <Monitor className="h-5 w-5" />
          System Info
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {items.map(({ icon: Icon, label, value }) => (
            <div key={label} className="flex items-center gap-3 p-3 rounded-lg bg-muted/30 border border-border/30">
              <Icon className="h-4 w-4 text-muted-foreground flex-shrink-0" />
              <div className="min-w-0">
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="text-sm font-mono truncate">{value}</p>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ============================================================================
// Main Dashboard
// ============================================================================
export default function AdminDashboard() {
  const router = useRouter();
  const locale = (router.locale || "en") as Locale;
  const { t } = useTranslation(locale);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [config, setConfig] = useState<any>(null);
  const [configSections, setConfigSections] = useState<ConfigSection[]>([]);
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

  // Fetch config sections (structured) and raw config
  useEffect(() => {
    if (token) {
      // Structured sections for Strategy tab
      fetch("/api/admin/config/sections", {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then((data) => setConfigSections(data.sections || []))
        .catch(console.error);

      // Raw config
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

  const showMessage = useCallback((type: "success" | "error", text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 4000);
  }, []);

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
        showMessage("success", data.message);
        setPendingRestart(false);
        refetchStatus();
      } else {
        showMessage("error", data.message || "Failed");
      }
    } catch (e: any) {
      showMessage("error", e.message);
    }
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
        showMessage("success", `Updated ${path}`);
        setPendingRestart(true);
        // Update local sections state
        setConfigSections((prev) =>
          prev.map((section) => ({
            ...section,
            fields: section.fields.map((field) =>
              field.path === path ? { ...field, value } : field
            ),
          }))
        );
      } else {
        showMessage("error", "Failed to update config");
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
    } catch (e: any) {
      showMessage("error", e.message);
    }
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
      showMessage("success", `Updated ${key}`);
    } catch (e: any) {
      showMessage("error", e.message);
    }
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
        showMessage("success", `${type} uploaded successfully`);
      } else {
        showMessage("error", data.detail || "Upload failed");
      }
    } catch (e: any) {
      showMessage("error", e.message);
    } finally {
      setUploading(false);
    }
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
    { id: "system", label: "System", icon: Terminal },
    { id: "trade-quality", label: "Trade Quality", icon: Target },
    { id: "links", label: "Links", icon: LinkIcon },
    { id: "site", label: "Site", icon: Palette },
  ];

  return (
    <>
      <Head>
        <title>Admin Dashboard - {siteSettings.site_name || "AlgVex"}</title>
      </Head>

      <div className="min-h-screen gradient-bg">
        {/* Main Site Header */}
        <Header locale={locale} t={t} />

        {/* Admin Toolbar - positioned below the main navbar */}
        <div className="fixed top-20 inset-x-0 z-40 px-4">
          <div className="max-w-7xl mx-auto">
            <div className="flex items-center justify-between px-4 py-2 bg-background/80 backdrop-blur-xl border border-border/40 rounded-xl">
              <div className="flex items-center gap-3">
                <span className="text-sm font-semibold text-primary">Admin Panel</span>
                {serviceStatus?.running && (
                  <span className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-green-500/10 text-green-500 text-xs">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                    Live
                  </span>
                )}
                {serviceStatus?.uptime && (
                  <span className="text-xs text-muted-foreground hidden sm:inline">
                    Uptime: {serviceStatus.uptime}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Button variant="ghost" size="icon" className="relative h-8 w-8">
                  <Bell className="h-4 w-4" />
                  {pendingRestart && (
                    <span className="absolute top-1 right-1 w-2 h-2 bg-yellow-500 rounded-full" />
                  )}
                </Button>
                <Button variant="ghost" size="sm" onClick={handleLogout} className="h-8">
                  <LogOut className="h-4 w-4 mr-2" />
                  <span className="hidden sm:inline">Logout</span>
                </Button>
              </div>
            </div>
          </div>
        </div>

        {/* Message Toast */}
        {message && (
          <div
            className={`fixed top-32 right-4 p-4 rounded-lg z-50 shadow-lg max-w-sm ${
              message.type === "success"
                ? "bg-green-500/10 text-green-500 border border-green-500/30"
                : "bg-red-500/10 text-red-500 border border-red-500/30"
            }`}
          >
            <div className="flex items-center gap-2">
              {message.type === "success" ? (
                <CheckCircle className="h-4 w-4 flex-shrink-0" />
              ) : (
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
              )}
              <span className="text-sm">{message.text}</span>
            </div>
          </div>
        )}

        {/* Main Content - pt-36 accounts for main navbar (h-14 + top-4) + admin toolbar */}
        <main className="container mx-auto px-4 pt-36 pb-6">
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
                  size="sm"
                >
                  <Icon className="h-4 w-4 mr-2" />
                  {tab.label}
                </Button>
              );
            })}
          </div>

          {/* Pending Restart Banner */}
          {pendingRestart && activeTab !== "dashboard" && (
            <div className="mb-4 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30 flex items-center gap-3">
              <AlertTriangle className="h-4 w-4 text-yellow-500 flex-shrink-0" />
              <span className="text-sm text-yellow-500 flex-1">
                Configuration changed. Restart service to apply.
              </span>
              <Button size="sm" onClick={() => handleServiceControl("restart")} className="h-7 text-xs">
                Restart Now
              </Button>
            </div>
          )}

          {/* ================================================================ */}
          {/* Dashboard Tab */}
          {/* ================================================================ */}
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
                          {serviceStatus?.memory && serviceStatus.memory !== "N/A" && (
                            <span className="ml-2">| {serviceStatus.memory}</span>
                          )}
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
                <Card className="border-border/50">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg">Recent Trades</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <TradeTimeline trades={recentTrades} />
                  </CardContent>
                </Card>

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

          {/* ================================================================ */}
          {/* Strategy Tab - Full Configuration */}
          {/* ================================================================ */}
          {activeTab === "strategy" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold">Strategy Configuration</h2>
                  <p className="text-sm text-muted-foreground">
                    All parameters from configs/base.yaml. Changes require service restart.
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    // Reload sections from server
                    fetch("/api/admin/config/sections", {
                      headers: { Authorization: `Bearer ${token}` },
                    })
                      .then((r) => r.json())
                      .then((data) => {
                        setConfigSections(data.sections || []);
                        showMessage("success", "Configuration reloaded");
                      })
                      .catch(() => showMessage("error", "Failed to reload"));
                  }}
                >
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Reload
                </Button>
              </div>

              {configSections.length === 0 ? (
                <Card className="border-border/50">
                  <CardContent className="py-8 text-center text-sm text-muted-foreground">
                    Loading configuration sections...
                  </CardContent>
                </Card>
              ) : (
                configSections.map((section, idx) => (
                  <ConfigSectionCard
                    key={section.id}
                    section={section}
                    onSave={handleConfigSave}
                    defaultOpen={idx < 3}
                  />
                ))
              )}
            </div>
          )}

          {/* ================================================================ */}
          {/* System Tab - Logs + Diagnostics + System Info */}
          {/* ================================================================ */}
          {activeTab === "system" && (
            <div className="space-y-6">
              {/* Service Control (compact) */}
              <Card className="border-border/50">
                <CardContent className="py-4">
                  <div className="flex flex-wrap items-center gap-3">
                    <div className="flex items-center gap-2 mr-4">
                      <div
                        className={`h-3 w-3 rounded-full ${
                          serviceStatus?.running ? "bg-green-500 animate-pulse" : "bg-red-500"
                        }`}
                      />
                      <span className="text-sm font-medium">
                        {serviceStatus?.running ? "Running" : "Stopped"}
                      </span>
                      {serviceStatus?.uptime && (
                        <span className="text-xs text-muted-foreground">({serviceStatus.uptime})</span>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => handleServiceControl("restart")} className="h-8">
                        <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
                        Restart
                      </Button>
                      {serviceStatus?.running ? (
                        <Button variant="outline" size="sm" onClick={() => handleServiceControl("stop")} className="h-8">
                          <Power className="h-3.5 w-3.5 mr-1.5" />
                          Stop
                        </Button>
                      ) : (
                        <Button size="sm" onClick={() => handleServiceControl("start")} className="h-8">
                          <Play className="h-3.5 w-3.5 mr-1.5" />
                          Start
                        </Button>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* System Info */}
              <SystemInfoPanel token={token} />

              {/* Diagnostics */}
              <DiagnosticsPanel token={token} />

              {/* Logs */}
              <LogsViewer token={token} />
            </div>
          )}

          {/* ================================================================ */}
          {/* Trade Quality Tab */}
          {/* ================================================================ */}
          {activeTab === "trade-quality" && (
            <AdminTradeAnalysis />
          )}

          {/* ================================================================ */}
          {/* Links Tab */}
          {/* ================================================================ */}
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
                          showMessage("success", "Link updated");
                        }}
                      />
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          )}

          {/* ================================================================ */}
          {/* Site Settings Tab */}
          {/* ================================================================ */}
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
