"""Regressions from the v0.8.0 adversarial review.

Every test here reproduces a finding that was live in the first cut of the
waiver path. They are kept in their own module rather than folded into
`test_waiver.py` because each one is a specific thing that worked: an
invisible codepoint that let a principal license itself, four lines of YAML
whose absence made the integrity controls waivable, a star of renewals that
measured depth one, and a series of unlinked waivers that covered five years
without ever arming a trigger.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import yaml

from neuraxis import (
    Attestation,
    AttestationStore,
    AuthorityRequest,
    Decision,
    GovernanceGate,
    Waiver,
    WaiverError,
    WaiverRegister,
    load_registry,
)
from neuraxis.errors import RegistryError
from neuraxis.resolver import BandResolver
from neuraxis.waiver import NON_COMPENSABLE_FLOOR

UTC = timezone.utc
NOW = datetime(2026, 9, 16, 9, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def _store_missing(registry, *absent: str, issued_at: datetime = NOW) -> AttestationStore:
    return AttestationStore(
        Attestation(
            control=control,
            result=True,
            issued_at=issued_at,
            issuer="test-harness",
            evidence_ref=f"test://{control}",
            provenance="provider",
        )
        for control in registry.controls
        if control not in absent
    )


def _waiver(**overrides) -> Waiver:
    fields = {
        "id": "W-TEST-1",
        "control": "GV-05",
        "bands": ("BAND-B",),
        "accountable": "OP-Vily",
        "issued_by": "ops-console",
        "compensating_control": "manual rollback rehearsed before each merge",
        "ratification_ref": "ILR-001-DR/D-05",
        "issued_at": NOW - DAY,
        "expires_at": NOW + 29 * DAY,
        "renews": None,
    }
    fields.update(overrides)
    return Waiver(**fields)


def _register(registry, *waivers) -> WaiverRegister:
    return WaiverRegister.for_registry(registry, waivers=waivers)


def _request(**overrides) -> AuthorityRequest:
    fields = {
        "intent": "run a governed execution step",
        "identity": "agent-drafter",
        "role": "drafter",
        "capability": "IL-06",
        "scope": "bst-sa/pipelines",
        "verifier": "github-ci",
        "rollback_tested": True,
    }
    fields.update(overrides)
    return AuthorityRequest(**fields)


def _two_band_registry(lower, upper):
    return {
        "framework": "test",
        "version": "0.1",
        "governance": {
            "GV-01": {"name": "identity", "attestation": "x/y"},
            "GV-04": {"name": "verification", "attestation": "x/y"},
        },
        "capabilities": {
            "IL-01": {"name": "Thinkable", "band": "BAND-A", "question": "?"},
            "IL-06": {"name": "Actionable", "band": "BAND-B", "question": "?"},
        },
        "bands": {
            "BAND-A": {"requires": lower, "depends_on": []},
            "BAND-B": {"requires": upper, "depends_on": ["BAND-A"]},
        },
        "authority": {"role_grants": {"operator": ["BAND-A", "BAND-B"]}},
        "enforcement": {"on_missing_attestation": "deny", "attestation_max_age": "24h"},
    }


def _write(tmp_path, data):
    path = tmp_path / "neuraxis.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


# ---- regressions from the v0.8.0 adversarial review --------------------
#
# Every test below reproduces a finding that was live in the first cut of
# this module. They are kept as regressions rather than folded into the
# sections above, because each one is a specific thing that worked.


@pytest.mark.parametrize(
    "invisible",
    ["agent-drafter​", "​agent-drafter", "agent-drafter﻿", "agent­drafter"],
)
def test_an_invisible_codepoint_cannot_disguise_a_principal(invisible):
    """A name that renders as one principal and compares as another."""
    with pytest.raises(WaiverError, match="invisible or control character"):
        Waiver.from_dict({**_waiver().to_dict(), "issued_by": invisible})


def test_invisible_characters_in_a_claimed_identity_still_match(registry):
    """The record is clean; the *request* carries the disguise."""
    waivers = _register(registry, _waiver(issued_by="agent-drafter"))
    gate = GovernanceGate(registry, _store_missing(registry, "GV-05"), waivers)
    disguised = AuthorityRequest(
        intent="run a governed execution step",
        identity="agent-drafter​",
        role="drafter",
        capability="IL-06",
        scope="bst-sa/pipelines",
        verifier="github-ci",
        rollback_tested=True,
    )
    assert gate.evaluate(disguised, at=NOW).decision is Decision.DENY


def test_a_dotted_capital_i_does_not_separate_two_principals(registry):
    """casefold() alone maps 'İ' to 'i' plus a combining dot, which is not 'i'."""
    waivers = _register(registry, _waiver(issued_by="OP-Vily"))
    gate = GovernanceGate(registry, _store_missing(registry, "GV-05"), waivers)
    request = AuthorityRequest(
        intent="run a governed execution step",
        identity="OP-VİLY",
        role="drafter",
        capability="IL-06",
        scope="bst-sa/pipelines",
        verifier="github-ci",
        rollback_tested=True,
    )
    assert gate.evaluate(request, at=NOW).decision is Decision.DENY


def test_verifier_independence_survives_an_invisible_codepoint(registry):
    """NX-INV-2 itself, with every control attested and no waiver in play."""
    gate = GovernanceGate(registry, _store_missing(registry))
    self_verified = AuthorityRequest(
        intent="run a governed execution step",
        identity="agent-drafter",
        role="drafter",
        capability="IL-06",
        scope="bst-sa/pipelines",
        verifier="agent-drafter​",
        rollback_tested=True,
    )
    verdict = gate.evaluate(self_verified, at=NOW)
    assert verdict.decision is Decision.DENY
    assert any("NX-INV-2" in r for r in verdict.reasons)


# ---- the non-compensable floor is in code, not in YAML -----------------


def test_a_registry_with_no_waiver_block_still_carries_the_floor(tmp_path):
    path = _write(tmp_path, _two_band_registry(["GV-01"], ["GV-01", "GV-04"]))
    assert load_registry(path).waiver_policy.non_compensable >= NON_COMPENSABLE_FLOOR


def test_a_registry_cannot_empty_the_non_compensable_set(tmp_path, registry):
    data = _two_band_registry(["GV-01"], ["GV-01", "GV-04"])
    data["enforcement"]["waivers"] = {
        "non_compensable": [],
        "max_ttl": "3650d",
        "max_active": 999,
        "max_renewals": 999,
    }
    path = _write(tmp_path, data)
    policy = load_registry(path).waiver_policy
    assert policy.non_compensable >= NON_COMPENSABLE_FLOOR
    assert policy.max_ttl == timedelta(days=90)
    assert policy.max_active == 2
    assert policy.max_renewals == 1


def test_a_registry_may_tighten_but_not_loosen(tmp_path):
    data = _two_band_registry(["GV-01"], ["GV-01", "GV-04"])
    data["enforcement"]["waivers"] = {
        "non_compensable": ["GV-04"], "max_ttl": "7d", "max_active": 1, "max_renewals": 0
    }
    path = _write(tmp_path, data)
    policy = load_registry(path).waiver_policy
    assert "GV-04" in policy.non_compensable and policy.non_compensable >= NON_COMPENSABLE_FLOOR
    assert policy.max_ttl == timedelta(days=7)
    assert policy.max_active == 1


def test_a_register_built_without_a_registry_still_carries_the_floor():
    """The policy travels with the register; a bare one must not be permissive."""
    with pytest.raises(WaiverError, match="non-compensable"):
        WaiverRegister((_waiver(control="GV-01", bands=("BAND-A",)),))


# ---- renewal counting --------------------------------------------------


def test_a_star_of_renewals_pointing_at_one_root_is_refused(registry):
    """Every node measures depth 1, so the depth cap alone never fires."""
    root = _waiver(id="W-1", issued_at=NOW - 60 * DAY, expires_at=NOW - 30 * DAY)
    star = [_waiver(id=f"W-{i}", renews="W-1") for i in range(2, 6)]
    with pytest.raises(WaiverError, match="renewed by more than one record"):
        _register(registry, root, *star)


def test_tiled_waivers_on_one_scope_are_refused(registry):
    """Each record inside 90d, never two active, no renews link: 5 years of cover."""
    tiles = [
        _waiver(
            id=f"W-{i}",
            issued_at=NOW + i * 90 * DAY,
            expires_at=NOW + (i + 1) * 90 * DAY,
        )
        for i in range(4)
    ]
    with pytest.raises(WaiverError, match="does not renew"):
        _register(registry, *tiles)


def test_a_successor_on_the_same_scope_must_declare_renews(registry):
    first = _waiver(id="W-1", issued_at=NOW - 60 * DAY, expires_at=NOW - 30 * DAY)
    second = _waiver(id="W-2")
    with pytest.raises(WaiverError, match="already waived by W-1"):
        _register(registry, first, second)
    # ...and with the link it is accepted, now under the renewal counter.
    assert len(_register(registry, first, _waiver(id="W-2", renews="W-1"))) == 2


# ---- direct construction -----------------------------------------------


def test_a_string_of_bands_is_not_a_list_of_bands():
    """`band in "BAND-B BAND-D"` is substring matching, and covers 'AND-B'."""
    with pytest.raises(WaiverError, match="bare string is not a list"):
        _waiver(bands="BAND-B BAND-D")


@pytest.mark.parametrize("field", ["accountable", "issued_by", "compensating_control"])
def test_direct_construction_validates_the_same_fields_as_parsing(field):
    with pytest.raises(WaiverError, match="non-empty"):
        _waiver(**{field: ""})


def test_an_anonymous_waiver_cannot_be_built():
    """Blank principals would make `principals` empty and block nothing."""
    with pytest.raises(WaiverError):
        Waiver(
            id="W-X", control="GV-05", bands=("BAND-B",), accountable="",
            issued_by="", compensating_control="", ratification_ref="",
            issued_at=NOW - DAY, expires_at=NOW + DAY,
        )


def test_a_non_string_band_entry_is_refused():
    with pytest.raises(WaiverError, match="not a band id"):
        Waiver.from_dict({**_waiver().to_dict(), "bands": [True, 1.5]})


# ---- reporting integrity ----------------------------------------------


def test_a_void_waiver_set_says_so_rather_than_reading_as_unattested(registry):
    three = _register(
        registry,
        _waiver(id="W-1", control="GV-05"),
        _waiver(id="W-2", control="GV-04", bands=("BAND-B",)),
        _waiver(id="W-3", control="GV-06", bands=("BAND-D",)),
    )
    gate = GovernanceGate(registry, _store_missing(registry, "GV-05"), three)
    verdict = gate.evaluate(_request(), at=NOW)
    assert verdict.decision is Decision.DENY
    assert any("all waivers are void" in r for r in verdict.reasons)


def test_status_carries_the_waiver_ids_it_actually_used(registry):
    resolver = BandResolver(
        registry, _store_missing(registry, "GV-05"), _register(registry, _waiver())
    )
    status = resolver.status("BAND-B", at=NOW)
    assert status.waiver_ids == ("W-TEST-1",)
    assert status.to_dict()["waiver_ids"] == ["W-TEST-1"]


def test_authority_returns_the_blocker_and_the_waivers_from_one_traversal(registry):
    resolver = BandResolver(
        registry,
        _store_missing(registry, "GV-05"),
        _register(registry, _waiver(bands=("BAND-B", "BAND-D"))),
    )
    blocker, waivers = resolver.authority("BAND-D", at=NOW)
    assert blocker is None
    assert waivers == ("W-TEST-1",)


def test_a_blocked_closure_rests_on_no_waiver(registry):
    resolver = BandResolver(registry, _store_missing(registry, "GV-01"), _register(registry))
    blocker, waivers = resolver.authority("BAND-D", at=NOW)
    assert blocker is not None
    assert waivers == ()


# ---- the registry staircase -------------------------------------------


def test_a_second_root_band_is_refused(tmp_path):
    """The fast lane: a band depending on nothing inherits no control."""
    data = _two_band_registry(["GV-01"], ["GV-01", "GV-04"])
    data["bands"]["BAND-H"] = {"requires": ["GV-04"], "depends_on": []}
    data["capabilities"]["IL-32"] = {"name": "Self-Evolving", "band": "BAND-H", "question": "?"}
    path = _write(tmp_path, data)
    with pytest.raises(RegistryError, match="declare no prerequisite"):
        load_registry(path)


def test_a_non_delegable_capability_cannot_be_rehomed_to_a_cheaper_band(tmp_path):
    data = _two_band_registry(["GV-01"], ["GV-01", "GV-04"])
    data["capabilities"]["IL-32"] = {"name": "Self-Evolving", "band": "BAND-A", "question": "?"}
    data["authority"]["non_delegable"] = ["IL-32"]
    path = _write(tmp_path, data)
    with pytest.raises(RegistryError, match="non-delegable but sits in"):
        load_registry(path)


def test_the_shipped_registry_satisfies_the_non_delegable_floor(registry):
    for cid in registry.non_delegable:
        band = registry.band(registry.capability(cid).band)
        assert set(band.requires) == set(registry.controls), cid


# ---- traversal cost ----------------------------------------------------


def test_band_status_is_computed_once_per_evaluation(registry):
    """The gate is synchronous and blocking; an exponential traversal is a bypass.

    Without memoisation the shipped seven-band registry costs 66 status
    computations per evaluation, and the cost is exponential in depth.
    """
    calls: list[str] = []

    class Counting(BandResolver):
        def _status(self, band_id, at, claimed, cache):
            if band_id not in cache:
                calls.append(band_id)
            return super()._status(band_id, at, claimed, cache)

    gate = GovernanceGate(registry, _store_missing(registry))
    gate.resolver = Counting(registry, _store_missing(registry))
    gate.evaluate(_request(), at=NOW)
    assert calls == sorted(set(calls), key=calls.index)
    assert len(calls) <= len(registry.bands)
