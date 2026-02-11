# Order Failure Diagnostic Report

Generated (UTC): 2026-02-11 11:36:07
Host branch: `codex/import-diagnosis-results-into-repository-4z639y`
Host commit: `35da86545b4eb938170fed9cbad0323e8d812c2a`

## Executive Summary
- ✅ **Position mode**: Binance position mode is ONE_WAY.
- ❌ **ReduceOnly rejection in local logs**: Found 224 rejection lines in local logs (strict reject patterns).
- ⚠️ **GTC expiry in local logs**: Found 2 expiry-related lines in local logs.
- ⚠️ **systemd journal scan**: reduce_matches=57, expired_matches=2

## Binance Snapshot
- Symbol: `BTCUSDT`
- Position Mode: `ONE_WAY`
- Open Positions: `0`
- Open Orders: `0`
- Reduce-only Orders: `0`
- Reduce-only STOP Orders: `0`
- Reduce-only LIMIT TP Orders: `0`

- Reduce-only mentions (non-rejection): `0`
- Timestamped matched lines in window: `198` / `425`

## Journal Scan
- Service: `nautilus-trader`
- Lines scanned: `2000`
- Reduce-related matches: `57`
- Expiry-related matches: `2`

## Likely Root Causes
- Likely root cause: reduce-only orders submitted after position already closed / stale close flow race.
- Likely root cause: orphan GTC protective orders not canceled fast enough after fill/close events.

## Recommended Next Actions
1. If position mode is `HEDGE`, switch to `ONE_WAY` or upgrade strategy to send explicit `positionSide` on all reduce-only orders.
2. If `-2022` appears near SL/TP fills, enforce stronger two-phase close→recheck→reduce flow and idempotent cancellation.
3. For unexpected GTC expiry, compare expiry timestamps with position-close events and orphan cleanup logs.
