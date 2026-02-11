# Order Failure Diagnostic Report

Generated (UTC): 2026-02-11 09:37:06
Host branch: `codex/import-diagnosis-results-into-repository`
Host commit: `be41c235080fcc7ccf22d1016b50855331aa8d39`

## Executive Summary
- ✅ **Position mode**: Binance position mode is ONE_WAY.
- ❌ **ReduceOnly rejection in local logs**: Found 425 matching lines in local logs.
- ⚠️ **GTC expiry in local logs**: Found 19 expiry-related lines in local logs.
- ⚠️ **systemd journal scan**: reduce_matches=36, expired_matches=5

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
- Reduce-related matches: `36`
- Expiry-related matches: `5`

## Recommended Next Actions
1. If position mode is `HEDGE`, switch to `ONE_WAY` or upgrade strategy to send explicit `positionSide` on all reduce-only orders.
2. If `-2022` appears near SL/TP fills, enforce stronger two-phase close→recheck→reduce flow and idempotent cancellation.
3. For unexpected GTC expiry, compare expiry timestamps with position-close events and orphan cleanup logs.
