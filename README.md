# Public Rate Lock

A GenLayer Intelligent Contract where a borrower locks collateral against two independent public rate sources. Liquidation pays only if both hosts confirm the named rate, in the named units, breached the threshold inside the same UTC window.

## Deployment

- Network: GenLayer StudioNet
- Chain ID: 61999 (0xf22f)
- Contract address: 0x1dC4aCFFDd34C8A93679A44CE61a6AeE2864c9C3
- Explorer: https://explorer-studio.genlayer.com/address/0x1dC4aCFFDd34C8A93679A44CE61a6AeE2864c9C3
- Source file: src/PublicRateLock.py
- Tests: test/direct/test_public_rate_lock.py

## How It Works

1. Borrower calls open_lock with collateral attached, a rate identifier, units, a threshold, a window, and two source URLs.
2. The contract stores the lock, including the rate identity and reserved collateral.
3. After window_end and before grace_after, anyone can call liquidate.
4. Liquidate pays the caller only if both pages return actual boolean confirmation that the named rate, in the named units, breached the threshold inside the window. Otherwise the lock stays open.
5. After grace_after, anyone can call close_expired. The collateral returns to the borrower and the lock closes.

## Methods

- `open_lock(threshold_bps, rate_id, units, window_start, window_end, source_url_a, source_url_b)` payable
  Opens a lock. The borrower attaches native collateral, names the rate and its units, sets a threshold in basis points, a UTC window, and two allowlisted HTTPS URLs on different apex hosts. Returns the lock id.
- `liquidate(lock_id)`
  Callable after `window_end` and before `grace_after`. Pays the caller only if both sources confirm the breach for the stored rate and units. Otherwise the lock stays `OPEN`.
- `close_expired(lock_id)`
  Callable on or after `grace_after` while the lock is still `OPEN`. Returns the collateral to the borrower and closes the lock as `EXPIRED`.
- `can_liquidate(lock_id)`
  View. Returns status, window_end, grace_after, current UTC date, and whether liquidate or close_expired is currently allowed.
- `get_lock(lock_id)`
  View. Returns borrower, liquidator, collateral, threshold_bps, rate_id, units, window dates, source URLs, status, verdict, and funds_disposition.
- `get_lock_count()`
  View. Returns the number of locks created.
- `get_reserved_collateral()`
  View. Returns total collateral still reserved.

## Important Rules

- Sources must be HTTPS, allowlisted, and on different apex hosts. `www` and apex variants of the same domain count as one source.
- Both pages must describe the stored rate identifier and units. Related, date match, breach, rate match, and units match must be actual JSON booleans. The string `"false"` does not count as false.
- One host is never enough to liquidate.
- Liquidation closes at grace_after. A liquidated lock cannot be closed. A closed lock cannot be liquidated.

## Current Test State

The direct tests cover:

- Sources must differ, including apex and www variants of the same host.
- Early liquidation is blocked.
- One source, or a missing rate or units match, does not pay.
- Both sources confirming the named rate and units liquidate once.
- After grace, close_expired returns the collateral.
- close_expired reverts before grace.