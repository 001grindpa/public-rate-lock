CONTRACT = "src/PublicRateLock.py"
SOURCE_A = "https://www.federalreserve.gov/"
SOURCE_B = "https://www.ecb.europa.eu/"


def _set_today(day: str) -> None:
    import src.PublicRateLock as mod

    mod._today_utc = lambda: day


def _open(contract, vm, borrower, window_end="2026-12-31", threshold=500):
    vm.sender = borrower
    return contract.open_lock(
        threshold,
        "2026-10-01",
        window_end,
        SOURCE_A,
        SOURCE_B,
        value=10**18,
    )


def test_sources_must_differ(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("sources must come from two different hosts"):
        contract.open_lock(
            500,
            "2026-10-01",
            "2026-12-31",
            SOURCE_A,
            "https://www.federalreserve.gov/releases/",
            value=10**18,
        )


def test_rejects_impossible_date(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("window_end must be a real calendar date"):
        contract.open_lock(
            500,
            "2026-10-01",
            "2026-02-31",
            SOURCE_A,
            SOURCE_B,
            value=10**18,
        )


def test_window_end_before_start(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("window_end must be on or after window_start"):
        contract.open_lock(
            500,
            "2026-12-31",
            "2026-10-01",
            SOURCE_A,
            SOURCE_B,
            value=10**18,
        )


def test_early_liquidate_blocked(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    lock_id = _open(contract, direct_vm, direct_alice)
    with direct_vm.expect_revert("liquidation cannot run before window_end"):
        contract.liquidate(lock_id)
    assert "OPEN" in contract.get_lock(lock_id)


def test_one_source_is_not_enough(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    lock_id = _open(contract, direct_vm, direct_alice, window_end="2026-10-20")

    def only_one(_lock):
        return {"verdict": "UNKNOWN"}

    contract._adjudicate = only_one
    _set_today("2026-10-20")
    status = contract.liquidate(lock_id)
    after = contract.get_lock(lock_id)
    assert "OPEN" in after
    assert "UNKNOWN" in after
    assert "LIQUIDATED" not in str(status)
    assert contract.get_reserved_collateral() == str(10**18)


def test_both_sources_liquidate_once(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    lock_id = _open(contract, direct_vm, direct_alice, window_end="2026-10-20")

    def breach(_lock):
        return {"verdict": "BREACH"}

    contract._adjudicate = breach
    _set_today("2026-10-20")
    direct_vm.sender = direct_bob
    contract.liquidate(lock_id)
    after = contract.get_lock(lock_id)
    assert "LIQUIDATED" in after
    assert "BREACH" in after
    assert "PAID_TO_LIQUIDATOR" in after
    assert contract.get_reserved_collateral() == "0"
    with direct_vm.expect_revert("lock is not open"):
        contract.liquidate(lock_id)
    with direct_vm.expect_revert("only an open lock can be closed as expired"):
        contract.close_expired(lock_id)


def test_close_expired_returns_collateral_once(
    direct_vm, direct_deploy, direct_alice
):
    contract = direct_deploy(CONTRACT)
    lock_id = _open(contract, direct_vm, direct_alice, window_end="2020-01-01")
    raw = contract.get_lock(lock_id)
    assert "2020-01-02" in raw
    with direct_vm.expect_revert("liquidation is closed"):
        contract.liquidate(lock_id)
    contract.close_expired(lock_id)
    after = contract.get_lock(lock_id)
    assert "CLOSED" in after
    assert "EXPIRED" in after
    assert "RETURNED_TO_BORROWER" in after
    assert contract.get_reserved_collateral() == "0"
    with direct_vm.expect_revert("only an open lock can be closed as expired"):
        contract.close_expired(lock_id)


def test_cannot_close_before_grace(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    lock_id = _open(contract, direct_vm, direct_alice, window_end="2026-10-20")
    _set_today("2026-10-20")
    with direct_vm.expect_revert("close_expired cannot run before grace_after"):
        contract.close_expired(lock_id)
    assert "OPEN" in contract.get_lock(lock_id)


def test_liquidate_then_close_on_same_lock(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT)
    lock_id = _open(contract, direct_vm, direct_alice, window_end="2026-10-20")

    def breach(_lock):
        return {"verdict": "BREACH"}

    contract._adjudicate = breach
    _set_today("2026-10-20")
    direct_vm.sender = direct_bob
    contract.liquidate(lock_id)
    assert "LIQUIDATED" in contract.get_lock(lock_id)
    with direct_vm.expect_revert("only an open lock can be closed as expired"):
        contract.close_expired(lock_id)
    assert contract.get_reserved_collateral() == "0"