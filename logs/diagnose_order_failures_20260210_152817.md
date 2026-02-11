# Order Failure Diagnostic Report

Generated (UTC): 2026-02-10 15:28:17
Host branch: `work`
Host commit: `2b558fc857e3b85bb7cdfb45f904b9d648b9efff`

## Executive Summary
- ⚠️ **Position mode**: Unable to confirm Binance position mode.
- ✅ **ReduceOnly rejection in local logs**: No reduce-only rejection found in scanned local logs.
- ✅ **GTC expiry in local logs**: No unexpected expiry found in scanned local logs.
- ✅ **systemd journal scan**: reduce_matches=0, expired_matches=0

## Binance Snapshot
- Symbol: `BTCUSDT`
- Position Mode: `UNKNOWN`
- Open Positions: `0`
- Open Orders: `0`
- Reduce-only Orders: `0`
- Reduce-only STOP Orders: `0`
- Reduce-only LIMIT TP Orders: `0`

## Journal Scan
- Service: `nautilus-trader`
- Lines scanned: `1`
- Reduce-related matches: `0`
- Expiry-related matches: `0`

## Recommended Next Actions
1. If position mode is `HEDGE`, switch to `ONE_WAY` or upgrade strategy to send explicit `positionSide` on all reduce-only orders.
2. If `-2022` appears near SL/TP fills, enforce stronger two-phase close→recheck→reduce flow and idempotent cancellation.
3. For unexpected GTC expiry, compare expiry timestamps with position-close events and orphan cleanup logs.
