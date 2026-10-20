# Public Rate Lock

A GenLayer Intelligent Contract where a borrower locks collateral against two independent public rate sources, allowing liquidation only if both hosts confirm the rate breached the threshold inside the specified UTC window.

## Deployment

- Network: GenLayer StudioNet
- Chain ID: 61999 (0xf22f)
- Contract address: 0x48f29b8dC0aE569FDb60D746C53ac8A6cc10b3E5
- Explorer: https://explorer-studio.genlayer.com/address/0x48f29b8dC0aE569FDb60D746C53ac8A6cc10b3E5
- Source file: src/PublicRateLock.py
- Tests: test/direct/test_public_rate_lock.py

## How It Works

1. Borrower calls open_lock with collateral attached.
2. Contract stores the threshold, window, two source URLs, and reserved collateral.
3. After window_end and before grace_after, anyone can call liquidate.
4. Liquidate only pays the caller if both pages confirm a breach. Otherwise the lock stays open.
5. After grace_after, anyone can call close_expired. The collateral returns to the borrower and the lock closes.

## Methods

- `open_lock(threshold_bps, window_start, window_end, source_url_a, source_url_b)` payable
  Opens a new rate lock position. The borrower attaches native collateral, specifies a rate threshold in basis points, defines a start and end calendar date (YYYY-MM-DD), and supplies two distinct allowlisted HTTPS URLs. Returns the new lock ID.
- `liquidate(lock_id)`
  Callable by anyone after `window_end` and before `grace_after`. Evaluates both public rate pages. If both sources verify that the rate breached the threshold inside the window, the lock transitions to `LIQUIDATED` and the full collateral is paid to the caller. If either source fails to confirm a breach, the lock remains `OPEN`.
- `close_expired(lock_id)`
  Callable by anyone on or after `grace_after` if the lock is still `OPEN`. Closes the lock with an `EXPIRED` status and returns the collateral to the borrower.
- `can_liquidate(lock_id)`
  View method returning a JSON object with the lock status, `window_end`, `grace_after`, current UTC date, and boolean flags indicating whether `liquidate` or `close_expired` can currently be called.
- `get_lock(lock_id)`
  View method returning a JSON object with all stored fields of the lock: borrower, liquidator, collateral, threshold_bps, window_start, window_end, grace_after, source_url_a, source_url_b, status, verdict, and funds_disposition.
- `get_lock_count()`
  View method returning the total number of locks created as a string.
- `get_reserved_collateral()`
  View method returning the total active collateral currently reserved across open locks as a string.

## Important Rules

- Sources must be HTTPS, allowlisted, and on different hosts. Both URLs must be secure and originate from separate approved domains across major central banks and DeFi protocols.
- One host is never enough to liquidate. Liquidation strictly requires dual confirmation where both independent sources verify a rate breach within the specified window.
- Liquidation is closed at grace_after. Once `grace_after` (calculated as `window_end` plus 1 UTC day) is reached, liquidation can no longer be executed.
- A liquidated lock cannot be closed. A closed lock cannot be liquidated. State transitions to `LIQUIDATED` or `CLOSED` are permanent and prevent repeated payouts or secondary actions.

## Current Test State

The direct test suite in `test/direct/test_public_rate_lock.py` verifies the following behaviors:

- Sources must differ: Rejects lock creation if both source URLs use the same host domain.
- Early liquidation blocked: Verifies that calling `liquidate` before `window_end` reverts and keeps the lock `OPEN`.
- One source does not pay: Verifies that if only one host confirms a breach, no collateral is paid and the lock stays `OPEN`.
- Both sources liquidate once: Verifies that when both sources confirm a breach, collateral is paid to the liquidator, status transitions to `LIQUIDATED`, and duplicate liquidation or closure is rejected.
- Expired close returns collateral: Verifies that after `grace_after`, calling `close_expired` successfully returns the collateral to the borrower and closes the lock.
- Cannot close before grace: Verifies that calling `close_expired` before `grace_after` reverts and preserves the `OPEN` lock.
