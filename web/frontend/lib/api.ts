const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export interface PerformanceStats {
  total_pnl: number;
  total_pnl_percent: number;
  win_rate: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  max_drawdown: number;
  max_drawdown_percent: number;
  pnl_curve: Array<{
    date: string;
    daily_pnl: number;
    cumulative_pnl: number;
  }>;
  period_days: number;
  last_updated: string;
}

export interface SocialLink {
  platform: string;
  url: string;
}

export interface CopyTradingLink {
  exchange: string;
  name: string;
  url: string;
  icon: string;
}

export interface SystemStatus {
  trading_active: boolean;
  status: string;
}

export async function fetchPerformance(days: number = 30): Promise<PerformanceStats> {
  const res = await fetch(`${API_BASE}/api/public/performance?days=${days}`);
  if (!res.ok) throw new Error("Failed to fetch performance");
  return res.json();
}

export async function fetchPerformanceSummary(): Promise<{
  total_return_percent: number;
  win_rate: number;
  max_drawdown_percent: number;
  total_trades: number;
  last_updated: string;
}> {
  const res = await fetch(`${API_BASE}/api/public/performance/summary`);
  if (!res.ok) throw new Error("Failed to fetch summary");
  return res.json();
}

export async function fetchSocialLinks(): Promise<SocialLink[]> {
  const res = await fetch(`${API_BASE}/api/public/social-links`);
  if (!res.ok) throw new Error("Failed to fetch social links");
  return res.json();
}

export async function fetchCopyTradingLinks(): Promise<CopyTradingLink[]> {
  const res = await fetch(`${API_BASE}/api/public/copy-trading`);
  if (!res.ok) throw new Error("Failed to fetch copy trading links");
  return res.json();
}

export async function fetchSystemStatus(): Promise<SystemStatus> {
  const res = await fetch(`${API_BASE}/api/public/system-status`);
  if (!res.ok) throw new Error("Failed to fetch system status");
  return res.json();
}

// Admin API functions
export async function fetchAdminConfig(token: string): Promise<Record<string, any>> {
  const res = await fetch(`${API_BASE}/api/admin/config`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to fetch config");
  return res.json();
}

export async function updateAdminConfig(
  token: string,
  path: string,
  value: any
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/admin/config`, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ path, value }),
  });
  if (!res.ok) throw new Error("Failed to update config");
}

export async function controlService(
  token: string,
  action: "restart" | "stop" | "start"
): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/api/admin/service/control`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ action, confirm: true }),
  });
  return res.json();
}
