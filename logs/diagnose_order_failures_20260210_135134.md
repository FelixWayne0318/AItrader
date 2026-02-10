# Order Failure Diagnostic Report

Generated (UTC): 2026-02-10 13:51:30
Host branch: `codex/check-import-issues-for-diagnosis-results`
Host commit: `dee595ff62d4d1b67bbdcf7cba0ab8c8a4d70cfb`

## Executive Summary
- ✅ **Position mode**: Binance position mode is ONE_WAY.
- ❌ **ReduceOnly rejection in local logs**: Found 241 matching lines in local logs.
- ⚠️ **GTC expiry in local logs**: Found 17 expiry-related lines in local logs.
- ⚠️ **systemd journal scan**: reduce_matches=6, expired_matches=4

## Binance Snapshot
- Symbol: `BTCUSDT`
- Position Mode: `ONE_WAY`
- Open Positions: `1`
- Open Orders: `1`
- Reduce-only Orders: `1`
- Reduce-only STOP Orders: `0`
- Reduce-only LIMIT TP Orders: `1`

## Journal Scan
- Service: `nautilus-trader`
- Lines scanned: `2000`
- Reduce-related matches: `6`
- Expiry-related matches: `4`

## Recommended Next Actions
1. If position mode is `HEDGE`, switch to `ONE_WAY` or upgrade strategy to send explicit `positionSide` on all reduce-only orders.
2. If `-2022` appears near SL/TP fills, enforce stronger two-phase close→recheck→reduce flow and idempotent cancellation.
3. For unexpected GTC expiry, compare expiry timestamps with position-close events and orphan cleanup logs.
