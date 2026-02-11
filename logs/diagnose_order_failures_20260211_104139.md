# Order Failure Diagnostic Report

Generated (UTC): 2026-02-11 10:41:34
Host branch: `codex/import-diagnosis-results-into-repository-cnxuxy`
Host commit: `178a65ffe6b693e4092c2323f9556e5752e5a2b9`

## Executive Summary
- ✅ **Position mode**: Binance position mode is ONE_WAY.
- ❌ **ReduceOnly rejection in local logs**: Found 431 matching lines in local logs.
- ⚠️ **GTC expiry in local logs**: Found 19 expiry-related lines in local logs.
- ⚠️ **systemd journal scan**: reduce_matches=45, expired_matches=3

## Binance Snapshot
- Symbol: `BTCUSDT`
- Position Mode: `ONE_WAY`
- Open Positions: `0`
- Open Orders: `0`
- Reduce-only Orders: `0`
- Reduce-only STOP Orders: `0`
- Reduce-only LIMIT TP Orders: `0`

## Journal Scan
- Service: `nautilus-trader`
- Lines scanned: `2000`
- Reduce-related matches: `45`
- Expiry-related matches: `3`

## Recommended Next Actions
1. If position mode is `HEDGE`, switch to `ONE_WAY` or upgrade strategy to send explicit `positionSide` on all reduce-only orders.
2. If `-2022` appears near SL/TP fills, enforce stronger two-phase close→recheck→reduce flow and idempotent cancellation.
3. For unexpected GTC expiry, compare expiry timestamps with position-close events and orphan cleanup logs.
