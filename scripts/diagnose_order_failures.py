#!/usr/bin/env python3
"""
Order failure diagnostic tool for Binance -2022 ReduceOnly and unexpected GTC expiries.

Design goals:
1) Reproducible and server-friendly (single script, no extra dependencies)
2) Production-grade observability export (JSON + Markdown)
3) Optional git push flow for importing diagnostic results back to repository

Example:
  source venv/bin/activate
  python3 scripts/diagnose_order_failures.py --export --push --hours 24
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.binance_account import BinanceAccountFetcher


@dataclass
class CheckResult:
    name: str
    status: str
    details: str


def run_cmd(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 25) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def sanitize_git_remote(url: str) -> str:
    """Remove credentials from git remote URLs to avoid exporting secrets."""
    if not url:
        return url

    # https://<token>@github.com/org/repo.git or https://user:token@host/path
    redacted = re.sub(r"(https?://)([^/@]+@)", r"\1***@", url)

    # ssh://user:token@host/path
    redacted = re.sub(r"(ssh://)([^/@]+@)", r"\1***@", redacted)
    return redacted


def discover_git_info() -> Dict[str, str]:
    branch = "UNKNOWN"
    commit = "UNKNOWN"
    remote = "UNKNOWN"

    rc, out, _ = run_cmd(["git", "branch", "--show-current"], cwd=PROJECT_ROOT)
    if rc == 0 and out:
        branch = out

    rc, out, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT)
    if rc == 0 and out:
        commit = out

    rc, out, _ = run_cmd(["git", "remote", "get-url", "origin"], cwd=PROJECT_ROOT)
    if rc == 0 and out:
        remote = sanitize_git_remote(out)

    return {
        "branch": branch,
        "commit": commit,
        "origin": remote,
    }


def parse_log_file(path: Path, cutoff_utc: datetime) -> Dict[str, Any]:
    stats = {
        "file": str(path),
        "matched_lines": 0,
        "reduce_only_rejects": 0,
        "expired_events": 0,
        "samples": [],
    }

    if not path.exists():
        return stats

    # Broad matching to support multilingual logs / varied formatter output
    re_reject = re.compile(r"order\s+rejected|reduceonly|reduce-only|-2022", re.IGNORECASE)
    re_expired = re.compile(r"order\s+expired|gtc\s+order\s+expired", re.IGNORECASE)

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line_lc = line.lower()
        if not (re_reject.search(line_lc) or re_expired.search(line_lc)):
            continue

        stats["matched_lines"] += 1
        if re_reject.search(line_lc):
            stats["reduce_only_rejects"] += 1
        if re_expired.search(line_lc):
            stats["expired_events"] += 1

        if len(stats["samples"]) < 12:
            stats["samples"].append(line[:500])

    return stats


def collect_local_logs(hours: int) -> Dict[str, Any]:
    logs_dir = PROJECT_ROOT / "logs"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    candidates: List[Path] = []
    if logs_dir.exists():
        for p in logs_dir.glob("*.log*"):
            if p.is_file():
                candidates.append(p)

    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    candidates = candidates[:10]

    items = [parse_log_file(p, cutoff) for p in candidates]

    return {
        "directory": str(logs_dir),
        "scanned_files": len(candidates),
        "files": items,
        "total_reduce_only_rejects": sum(i["reduce_only_rejects"] for i in items),
        "total_expired_events": sum(i["expired_events"] for i in items),
    }


def collect_journal(service: str, hours: int) -> Dict[str, Any]:
    since = f"{hours} hours ago"
    cmd = ["journalctl", "-u", service, "--since", since, "--no-pager", "-n", "2000"]
    rc, out, err = run_cmd(cmd, timeout=45)
    if rc != 0:
        return {
            "available": False,
            "error": err or "journalctl command failed",
            "service": service,
        }

    lines = out.splitlines()
    re_reduce = re.compile(r"-2022|reduceonly|reduce-only|order rejected", re.IGNORECASE)
    re_expired = re.compile(r"order expired|gtc order expired", re.IGNORECASE)

    reduce_lines = [ln[:500] for ln in lines if re_reduce.search(ln)]
    expired_lines = [ln[:500] for ln in lines if re_expired.search(ln)]

    return {
        "available": True,
        "service": service,
        "lines_scanned": len(lines),
        "reduce_matches": len(reduce_lines),
        "expired_matches": len(expired_lines),
        "reduce_samples": reduce_lines[:15],
        "expired_samples": expired_lines[:15],
    }


def collect_binance_snapshot(symbol: str) -> Dict[str, Any]:
    fetcher = BinanceAccountFetcher()

    mode = fetcher.get_position_mode()
    positions = fetcher.get_positions(symbol=symbol)
    open_orders = fetcher.get_open_orders(symbol=symbol)

    reduce_only_orders = [o for o in open_orders if bool(o.get("reduceOnly", False))]
    stop_orders = [o for o in reduce_only_orders if str(o.get("type", "")).upper() in {"STOP", "STOP_MARKET"}]
    tp_limit_orders = [o for o in reduce_only_orders if str(o.get("type", "")).upper() == "LIMIT"]

    return {
        "symbol": symbol,
        "position_mode": mode,
        "positions_count": len(positions),
        "positions": positions,
        "open_orders_count": len(open_orders),
        "reduce_only_orders_count": len(reduce_only_orders),
        "reduce_only_stop_orders_count": len(stop_orders),
        "reduce_only_tp_limit_orders_count": len(tp_limit_orders),
        "open_orders_sample": open_orders[:20],
    }


def evaluate(data: Dict[str, Any]) -> List[CheckResult]:
    results: List[CheckResult] = []

    snapshot = data["binance_snapshot"]
    mode = snapshot.get("position_mode", "UNKNOWN")
    if mode == "ONE_WAY":
        results.append(CheckResult("Position mode", "PASS", "Binance position mode is ONE_WAY."))
    elif mode == "HEDGE":
        results.append(CheckResult("Position mode", "FAIL", "Binance position mode is HEDGE; reduce-only rejection risk is high without explicit positionSide."))
    else:
        results.append(CheckResult("Position mode", "WARN", "Unable to confirm Binance position mode."))

    local = data["local_logs"]
    reject_count = int(local.get("total_reduce_only_rejects", 0))
    if reject_count == 0:
        results.append(CheckResult("ReduceOnly rejection in local logs", "PASS", "No reduce-only rejection found in scanned local logs."))
    else:
        results.append(CheckResult("ReduceOnly rejection in local logs", "FAIL", f"Found {reject_count} matching lines in local logs."))

    expired_count = int(local.get("total_expired_events", 0))
    if expired_count == 0:
        results.append(CheckResult("GTC expiry in local logs", "PASS", "No unexpected expiry found in scanned local logs."))
    else:
        results.append(CheckResult("GTC expiry in local logs", "WARN", f"Found {expired_count} expiry-related lines in local logs."))

    j = data["journal"]
    if not j.get("available", False):
        results.append(CheckResult("systemd journal scan", "WARN", f"journalctl unavailable: {j.get('error', 'unknown error')}"))
    else:
        results.append(CheckResult(
            "systemd journal scan",
            "PASS" if int(j.get("reduce_matches", 0)) == 0 and int(j.get("expired_matches", 0)) == 0 else "WARN",
            f"reduce_matches={j.get('reduce_matches', 0)}, expired_matches={j.get('expired_matches', 0)}"
        ))

    return results


def format_markdown(report: Dict[str, Any], checks: List[CheckResult]) -> str:
    lines: List[str] = []
    lines.append("# Order Failure Diagnostic Report")
    lines.append("")
    lines.append(f"Generated (UTC): {report['meta']['generated_at_utc']}")
    lines.append(f"Host branch: `{report['git']['branch']}`")
    lines.append(f"Host commit: `{report['git']['commit']}`")
    lines.append("")

    lines.append("## Executive Summary")
    for c in checks:
        icon = "✅" if c.status == "PASS" else "⚠️" if c.status == "WARN" else "❌"
        lines.append(f"- {icon} **{c.name}**: {c.details}")
    lines.append("")

    lines.append("## Binance Snapshot")
    b = report["binance_snapshot"]
    lines.append(f"- Symbol: `{b.get('symbol')}`")
    lines.append(f"- Position Mode: `{b.get('position_mode')}`")
    lines.append(f"- Open Positions: `{b.get('positions_count')}`")
    lines.append(f"- Open Orders: `{b.get('open_orders_count')}`")
    lines.append(f"- Reduce-only Orders: `{b.get('reduce_only_orders_count')}`")
    lines.append(f"- Reduce-only STOP Orders: `{b.get('reduce_only_stop_orders_count')}`")
    lines.append(f"- Reduce-only LIMIT TP Orders: `{b.get('reduce_only_tp_limit_orders_count')}`")
    lines.append("")

    lines.append("## Journal Scan")
    j = report["journal"]
    if not j.get("available", False):
        lines.append(f"- journalctl unavailable: `{j.get('error', 'unknown')}`")
    else:
        lines.append(f"- Service: `{j.get('service')}`")
        lines.append(f"- Lines scanned: `{j.get('lines_scanned')}`")
        lines.append(f"- Reduce-related matches: `{j.get('reduce_matches')}`")
        lines.append(f"- Expiry-related matches: `{j.get('expired_matches')}`")
    lines.append("")

    lines.append("## Recommended Next Actions")
    lines.append("1. If position mode is `HEDGE`, switch to `ONE_WAY` or upgrade strategy to send explicit `positionSide` on all reduce-only orders.")
    lines.append("2. If `-2022` appears near SL/TP fills, enforce stronger two-phase close→recheck→reduce flow and idempotent cancellation.")
    lines.append("3. For unexpected GTC expiry, compare expiry timestamps with position-close events and orphan cleanup logs.")
    lines.append("")

    return "\n".join(lines)


def push_outputs(paths: List[Path], message: str) -> Dict[str, Any]:
    results: Dict[str, Any] = {"pushed": False, "error": ""}

    rc, remotes, err = run_cmd(["git", "remote"], cwd=PROJECT_ROOT)
    if rc != 0:
        results["error"] = f"git remote check failed: {err}"
        return results

    remote_names = [r.strip() for r in remotes.splitlines() if r.strip()]
    if "origin" not in remote_names:
        if remote_names:
            results["error"] = (
                "git remote 'origin' is missing. "
                f"Available remotes: {', '.join(remote_names)}"
            )
        else:
            results["error"] = "no git remotes configured; cannot push diagnostic report"
        return results

    for p in paths:
        rc, _, err = run_cmd(["git", "add", "-f", str(p)], cwd=PROJECT_ROOT)
        if rc != 0:
            results["error"] = f"git add failed for {p}: {err}"
            return results

    rc, out, err = run_cmd(["git", "commit", "-m", message], cwd=PROJECT_ROOT)
    if rc != 0:
        combined = f"{out}\n{err}".lower()
        if "nothing to commit" not in combined:
            results["error"] = f"git commit failed: {err or out}"
            return results

    rc, branch, err = run_cmd(["git", "branch", "--show-current"], cwd=PROJECT_ROOT)
    if rc != 0:
        results["error"] = f"failed to detect branch: {err}"
        return results

    rc, _, err = run_cmd(["git", "push", "-u", "origin", branch], cwd=PROJECT_ROOT, timeout=60)
    if rc != 0:
        results["error"] = f"git push failed: {err}"
        return results

    results["pushed"] = True
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Comprehensive diagnostics for Binance -2022 ReduceOnly rejects and GTC expiries"
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="Binance symbol, default BTCUSDT")
    parser.add_argument("--service", default="nautilus-trader", help="systemd service name")
    parser.add_argument("--hours", type=int, default=24, help="lookback hours for logs/journal")
    parser.add_argument("--export", action="store_true", help="export json+md report to logs/")
    parser.add_argument("--push", action="store_true", help="commit and push exported report files")
    args = parser.parse_args()

    # --push implies --export
    export_mode = args.export or args.push

    # env loading compatible with current repo practice
    load_env_file(Path.home() / ".env.aitrader")
    load_env_file(PROJECT_ROOT / ".env")

    report: Dict[str, Any] = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "tool": "scripts/diagnose_order_failures.py",
            "hours": args.hours,
        },
        "git": discover_git_info(),
        "binance_snapshot": collect_binance_snapshot(args.symbol),
        "local_logs": collect_local_logs(args.hours),
        "journal": collect_journal(args.service, args.hours),
    }

    checks = evaluate(report)
    report["checks"] = [c.__dict__ for c in checks]

    print("=" * 72)
    print("Order Failure Diagnostics")
    print("=" * 72)
    for c in checks:
        icon = "✅" if c.status == "PASS" else "⚠️" if c.status == "WARN" else "❌"
        print(f"{icon} {c.name}: {c.details}")

    exported_paths: List[Path] = []
    if export_mode:
        out_dir = PROJECT_ROOT / "logs"
        out_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        json_path = out_dir / f"diagnose_order_failures_{ts}.json"
        md_path = out_dir / f"diagnose_order_failures_{ts}.md"

        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(format_markdown(report, checks), encoding="utf-8")
        exported_paths = [json_path, md_path]

        print(f"\nExported JSON: {json_path}")
        print(f"Exported MD:   {md_path}")

    if args.push:
        if not exported_paths:
            print("❌ --push requires exported files")
            return 2
        commit_msg = "chore: add order failure diagnostic report"
        push_result = push_outputs(exported_paths, commit_msg)
        if push_result.get("pushed"):
            print("✅ Diagnostic report committed and pushed to remote branch.")
        else:
            print(f"❌ Push failed: {push_result.get('error', 'unknown error')}")
            return 2

    # Return non-zero only on severe findings
    failed = [c for c in checks if c.status == "FAIL"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
