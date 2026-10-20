# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from genlayer import *


HTTPS = "https://"
MAX_PAGE_CHARS = 12000
MIN_TEXT_CHARS = 3
GRACE_DAYS = 1
ZERO = Address("0x0000000000000000000000000000000000000000")

ALLOWED_HOSTS = (
    "federalreserve.gov",
    "www.federalreserve.gov",
    "bankofengland.co.uk",
    "www.bankofengland.co.uk",
    "ecb.europa.eu",
    "www.ecb.europa.eu",
    "status.aave.com",
    "aave.com",
    "status.compound.finance",
    "compound.finance",
    "status.makerdao.com",
    "makerdao.com",
    "defillama.com",
    "www.defillama.com",
    "coingecko.com",
    "www.coingecko.com",
    "status.lido.fi",
    "lido.fi",
)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _host_allowed(url: str) -> bool:
    host = _host(url)
    if not host:
        return False
    for allowed in ALLOWED_HOSTS:
        base = allowed[4:] if allowed.startswith("www.") else allowed
        if host == allowed or host == base or host.endswith("." + base):
            return True
    return False


def _require_https_url(url: str, label: str) -> str:
    cleaned = url.strip()
    if not cleaned.lower().startswith(HTTPS):
        raise gl.vm.UserError(f"{label} must be an https url")
    if not _host_allowed(cleaned):
        raise gl.vm.UserError(f"{label} host is not on the source allowlist")
    return cleaned


def _require_date(value: str, label: str) -> str:
    cleaned = value.strip()
    try:
        datetime.strptime(cleaned, "%Y-%m-%d")
    except ValueError:
        raise gl.vm.UserError(label + " must be a real calendar date YYYY-MM-DD")
    return cleaned


def _add_days(day: str, days: int) -> str:
    return (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@gl.evm.contract_interface
class _Wallet:
    class View:
        pass

    class Write:
        pass


def _pay(to: Address, amount: u256) -> None:
    if amount == 0:
        return
    if to == ZERO:
        raise gl.vm.UserError("cannot pay the zero address")
    _Wallet(to).emit_transfer(value=amount)


@allow_storage
@dataclass
class RateLock:
    borrower: Address
    liquidator: Address
    collateral: u256
    threshold_bps: u256
    window_start: str
    window_end: str
    grace_after: str
    source_url_a: str
    source_url_b: str
    status: str
    verdict: str
    funds_disposition: str


class PublicRateLock(gl.Contract):
    locks: TreeMap[str, RateLock]
    next_id: u256
    reserved_collateral: u256

    def __init__(self):
        self.next_id = u256(1)
        self.reserved_collateral = u256(0)

    def _id(self) -> str:
        return str(int(self.next_id))

    def _get(self, lock_id: str) -> RateLock:
        if lock_id not in self.locks:
            raise gl.vm.UserError("lock not found")
        return self.locks[lock_id]

    def _extract_breach(self, url: str, threshold_bps: u256, window_start: str, window_end: str) -> dict:
        failed = {"related": False, "date_match": False, "breached": False}
        try:
            raw = gl.nondet.web.render(url, mode="text")
            page_text = raw if isinstance(raw, str) else str(raw)
            page_text = page_text[:MAX_PAGE_CHARS]
        except Exception:
            return failed

        prompt = f"""
Read one public rate or status page and decide if the rate breached the threshold inside the window.

Threshold (basis points): {int(threshold_bps)}
Window start (YYYY-MM-DD): {window_start}
Window end (YYYY-MM-DD): {window_end}
Source URL: {url}

Page text:
{page_text}

Return JSON only:
{{
  "related": true or false,
  "date_match": true or false,
  "breached": true or false
}}
Rules:
- related is true only if the page shows a rate or index that can be compared to the threshold.
- date_match is true only if the breach (or the rate reading) falls inside the window.
- breached is true only if the page shows the rate at or above the threshold inside that window.
"""
        try:
            parsed = gl.nondet.exec_prompt(prompt, response_format="json")
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
        except Exception:
            return failed

        return {
            "related": bool(parsed.get("related", False)),
            "date_match": bool(parsed.get("date_match", False)),
            "breached": bool(parsed.get("breached", False)),
        }

    def _decision(self, lock: RateLock) -> dict:
        try:
            page_a = self._extract_breach(
                lock.source_url_a, lock.threshold_bps, lock.window_start, lock.window_end
            )
            page_b = self._extract_breach(
                lock.source_url_b, lock.threshold_bps, lock.window_start, lock.window_end
            )
        except Exception:
            return {"verdict": "UNKNOWN"}

        if (
            not page_a["related"]
            or not page_b["related"]
            or not page_a["date_match"]
            or not page_b["date_match"]
            or not page_a["breached"]
            or not page_b["breached"]
        ):
            return {"verdict": "UNKNOWN"}
        return {"verdict": "BREACH"}

    def _adjudicate(self, lock: RateLock) -> dict:
        def leader_fn() -> str:
            return json.dumps(self._decision(lock), sort_keys=True, separators=(",", ":"))

        def validator_fn(leader_result) -> bool:
            payload = leader_result
            if hasattr(leader_result, "calldata"):
                payload = leader_result.calldata
            if isinstance(payload, (bytes, bytearray)):
                payload = payload.decode("utf-8", errors="replace")
            if not isinstance(payload, str):
                payload = str(payload)
            try:
                leader = json.loads(payload)
            except Exception:
                return False
            own = self._decision(lock)
            return own.get("verdict") == str(leader.get("verdict", "")).upper()

        try:
            raw = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        except Exception:
            return {"verdict": "UNKNOWN"}
        try:
            if isinstance(raw, str):
                return json.loads(raw)
            if hasattr(raw, "calldata"):
                data = raw.calldata
                return json.loads(data if isinstance(data, str) else str(data))
            return json.loads(str(raw))
        except Exception:
            return {"verdict": "UNKNOWN"}

    @gl.public.write.payable
    def open_lock(
        self,
        threshold_bps: u256,
        window_start: str,
        window_end: str,
        source_url_a: str,
        source_url_b: str,
    ) -> str:
        if threshold_bps == 0:
            raise gl.vm.UserError("threshold must be greater than zero")
        window_start = _require_date(window_start, "window_start")
        window_end = _require_date(window_end, "window_end")
        if window_end < window_start:
            raise gl.vm.UserError("window_end must be on or after window_start")
        url_a = _require_https_url(source_url_a, "source_url_a")
        url_b = _require_https_url(source_url_b, "source_url_b")
        if _host(url_a) == _host(url_b):
            raise gl.vm.UserError("sources must come from two different hosts")
        collateral = gl.message.value
        if collateral == 0:
            raise gl.vm.UserError("collateral must be greater than zero")

        lock_id = self._id()
        self.locks[lock_id] = RateLock(
            borrower=gl.message.sender_address,
            liquidator=ZERO,
            collateral=collateral,
            threshold_bps=threshold_bps,
            window_start=window_start,
            window_end=window_end,
            grace_after=_add_days(window_end, GRACE_DAYS),
            source_url_a=url_a,
            source_url_b=url_b,
            status="OPEN",
            verdict="",
            funds_disposition="RESERVED",
        )
        self.next_id = self.next_id + u256(1)
        self.reserved_collateral = self.reserved_collateral + collateral
        return lock_id

    @gl.public.write
    def liquidate(self, lock_id: str) -> str:
        lock = self._get(lock_id)
        if lock.status != "OPEN":
            raise gl.vm.UserError("lock is not open")
        today = _today_utc()
        if today < lock.window_end:
            raise gl.vm.UserError("liquidation cannot run before window_end " + lock.window_end)
        if today >= lock.grace_after:
            raise gl.vm.UserError("liquidation is closed; use close_expired after grace")

        result = self._adjudicate(lock)
        verdict = str(result.get("verdict", "UNKNOWN")).upper()

        if verdict == "BREACH":
            lock.status = "LIQUIDATED"
            lock.verdict = "BREACH"
            lock.funds_disposition = "PAID_TO_LIQUIDATOR"
            lock.liquidator = gl.message.sender_address
            self.reserved_collateral = self.reserved_collateral - lock.collateral
            self.locks[lock_id] = lock
            _pay(gl.message.sender_address, lock.collateral)
        else:
            lock.verdict = verdict if verdict in ("UNKNOWN", "DISAGREE") else "UNKNOWN"
            self.locks[lock_id] = lock
        return self.locks[lock_id].status

    @gl.public.write
    def close_expired(self, lock_id: str) -> None:
        lock = self._get(lock_id)
        if lock.status != "OPEN":
            raise gl.vm.UserError("only an open lock can be closed as expired")
        today = _today_utc()
        if today < lock.grace_after:
            raise gl.vm.UserError("close_expired cannot run before grace_after " + lock.grace_after)
        # Recovery: second host never confirmed, collateral returns to borrower
        collateral = lock.collateral
        borrower = lock.borrower
        lock.status = "CLOSED"
        lock.verdict = "EXPIRED"
        lock.funds_disposition = "RETURNED_TO_BORROWER"
        self.reserved_collateral = self.reserved_collateral - collateral
        self.locks[lock_id] = lock
        _pay(borrower, collateral)

    @gl.public.view
    def can_liquidate(self, lock_id: str) -> str:
        lock = self._get(lock_id)
        today = _today_utc()
        open_lock = lock.status == "OPEN"
        return json.dumps(
            {
                "status": lock.status,
                "window_end": lock.window_end,
                "grace_after": lock.grace_after,
                "now_utc": today,
                "liquidate_allowed": open_lock and today >= lock.window_end and today < lock.grace_after,
                "close_expired_allowed": open_lock and today >= lock.grace_after,
            },
            sort_keys=True,
        )

    @gl.public.view
    def get_lock(self, lock_id: str) -> str:
        lock = self._get(lock_id)
        return json.dumps(
            {
                "borrower": lock.borrower.as_hex,
                "liquidator": lock.liquidator.as_hex,
                "collateral": str(int(lock.collateral)),
                "threshold_bps": str(int(lock.threshold_bps)),
                "window_start": lock.window_start,
                "window_end": lock.window_end,
                "grace_after": lock.grace_after,
                "source_url_a": lock.source_url_a,
                "source_url_b": lock.source_url_b,
                "status": lock.status,
                "verdict": lock.verdict,
                "funds_disposition": lock.funds_disposition,
            },
            sort_keys=True,
        )

    @gl.public.view
    def get_lock_count(self) -> str:
        return str(int(self.next_id) - 1)

    @gl.public.view
    def get_reserved_collateral(self) -> str:
        return str(int(self.reserved_collateral))