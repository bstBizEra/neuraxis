"""The exception path (v0.8.0): expiring, recorded waivers.

ILR-001-DR D-05 rules that the gate needs a waiver path and that the danger is
not the exception but the exception that never ends. These tests are written
against that reading: most of them try to obtain authority a waiver should not
confer, and the positive controls exist so that the deny-assertions cannot all
be satisfied by a gate that simply denies everything.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from neuraxis import (
    Attestation,
    AttestationStore,
    AuthorityRequest,
    Decision,
    GovernanceGate,
    Obligation,
    Waiver,
    WaiverError,
    WaiverPolicy,
    WaiverRegister,
    load_registry,
)
from neuraxis.cli import main
from neuraxis.errors import RegistryError
from neuraxis.resolver import BandResolver

UTC = timezone.utc
NOW = datetime(2026, 9, 16, 9, 0, tzinfo=UTC)
DAY = timedelta(days=1)


# ---- helpers -----------------------------------------------------------


def _store_missing(registry, *absent: str, issued_at: datetime = NOW) -> AttestationStore:
    """Every control attested except the named ones.

    `issued_at` is pinned to the evaluation instant on purpose. A store built
    from the wall clock and evaluated at a fixed `at` produces denials for
    staleness, which would let every assertion below pass without the waiver
    logic being exercised at all.
    """
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


@pytest.fixture
def band_b_request():
    return AuthorityRequest(
        intent="run a governed execution step",
        identity="agent-drafter",
        role="drafter",
        capability="IL-06",
        scope="bst-sa/pipelines",
        verifier="github-ci",
        rollback_tested=True,
    )


# ---- positive controls -------------------------------------------------


def test_missing_control_denies_without_a_waiver(registry, band_b_request):
    """The positive control. Every deny below must be the waiver's doing."""
    gate = GovernanceGate(registry, _store_missing(registry, "GV-05"))
    verdict = gate.evaluate(band_b_request, at=NOW)
    assert verdict.decision is Decision.DENY
    assert verdict.waivers == ()


def test_waiver_licenses_the_band_and_says_so(registry, band_b_request):
    gate = GovernanceGate(
        registry, _store_missing(registry, "GV-05"), _register(registry, _waiver())
    )
    verdict = gate.evaluate(band_b_request, at=NOW)
    assert verdict.decision is Decision.ALLOW
    assert verdict.waivers == ("W-TEST-1",)
    assert "conditionally" in verdict.reasons[0]
    # The word "current" must not survive into a conditional attainment.
    assert "controls current" not in verdict.reasons[0]


def test_full_attestation_needs_no_waiver(registry, band_b_request):
    verdict = GovernanceGate(registry, _store_missing(registry)).evaluate(band_b_request, at=NOW)
    assert verdict.decision is Decision.ALLOW
    assert verdict.waivers == ()


# ---- non-compensable controls ------------------------------------------


@pytest.mark.parametrize("control", ["GV-01", "GV-02", "GV-03", "GV-08"])
def test_integrity_controls_cannot_be_waived_at_all(registry, control):
    """ILR-001-DR D-06. No TTL, no compensating control, no accountable party."""
    with pytest.raises(WaiverError, match="non-compensable"):
        _register(registry, _waiver(control=control, bands=("BAND-A",)))


def test_a_waiver_cannot_stand_in_for_the_kernel_boundary(registry, band_b_request):
    """GV-01 missing is T1 missing, and the exception path does not reach it."""
    store = _store_missing(registry, "GV-01")
    with pytest.raises(WaiverError):
        _register(registry, _waiver(control="GV-01", bands=("BAND-A", "BAND-B")))
    gate = GovernanceGate(registry, store, _register(registry, _waiver()))
    assert gate.evaluate(band_b_request, at=NOW).decision is Decision.DENY


# ---- the self-waiver rule ----------------------------------------------


@pytest.mark.parametrize("field", ["issued_by", "accountable"])
def test_a_waiver_never_licenses_its_own_principal(registry, band_b_request, field):
    waivers = _register(registry, _waiver(**{field: "agent-drafter"}))
    gate = GovernanceGate(registry, _store_missing(registry, "GV-05"), waivers)
    verdict = gate.evaluate(band_b_request, at=NOW)
    assert verdict.decision is Decision.DENY
    assert any("cannot license its own issuer" in r for r in verdict.reasons)


def test_the_same_waiver_licenses_a_different_principal(registry):
    """The other half of the pair: the rule is about who asks, not a dead check."""
    waivers = _register(registry, _waiver(issued_by="agent-drafter"))
    gate = GovernanceGate(registry, _store_missing(registry, "GV-05"), waivers)
    other = AuthorityRequest(
        intent="run a governed execution step",
        identity="agent-cortex",
        role="cortex",
        capability="IL-06",
        scope="bst-sa/pipelines",
        verifier="github-ci",
        rollback_tested=True,
    )
    assert gate.evaluate(other, at=NOW).decision is Decision.ALLOW


@pytest.mark.parametrize("spelling", ["Agent-Drafter", "  agent-drafter  ", "AGENT-DRAFTER"])
def test_principal_matching_survives_case_and_whitespace(registry, band_b_request, spelling):
    waivers = _register(registry, _waiver(issued_by=spelling))
    gate = GovernanceGate(registry, _store_missing(registry, "GV-05"), waivers)
    assert gate.evaluate(band_b_request, at=NOW).decision is Decision.DENY


def test_a_fictitious_performer_does_not_escape_the_self_waiver_rule(registry):
    """`performer` is requester-supplied, so both claimed identities are checked."""
    waivers = _register(registry, _waiver(issued_by="agent-drafter"))
    gate = GovernanceGate(registry, _store_missing(registry, "GV-05"), waivers)
    disguised = AuthorityRequest(
        intent="run a governed execution step",
        identity="agent-cortex",
        role="cortex",
        capability="IL-06",
        scope="bst-sa/pipelines",
        verifier="github-ci",
        rollback_tested=True,
        performer="agent-drafter",
    )
    assert gate.evaluate(disguised, at=NOW).decision is Decision.DENY


# ---- expiry ------------------------------------------------------------


def test_a_waiver_is_expired_at_its_expiry_instant(registry, band_b_request):
    """Half-open [issued, expires). The boundary resolves against the waiver."""
    waiver = _waiver(expires_at=NOW)
    # Attestations two hours old at both instants, so neither answer can come
    # from staleness on either side of the boundary.
    store = _store_missing(registry, "GV-05", issued_at=NOW - timedelta(hours=2))
    gate = GovernanceGate(registry, store, _register(registry, waiver))
    assert gate.evaluate(band_b_request, at=NOW - timedelta(seconds=1)).decision is Decision.ALLOW
    assert gate.evaluate(band_b_request, at=NOW).decision is Decision.DENY


def test_expiry_needs_nothing_to_run(registry, band_b_request):
    """No sweep, no scheduler, no revocation step: lapse is computed on read."""
    waivers = _register(registry, _waiver(expires_at=NOW + DAY))
    inside = GovernanceGate(registry, _store_missing(registry, "GV-05"), waivers)
    assert inside.evaluate(band_b_request, at=NOW).decision is Decision.ALLOW

    # A second store, current at the later instant, so the denial cannot be
    # the other nine controls going stale.
    later = NOW + 2 * DAY
    after = GovernanceGate(
        registry, _store_missing(registry, "GV-05", issued_at=later), waivers
    )
    verdict = after.evaluate(band_b_request, at=later)
    assert verdict.decision is Decision.DENY
    assert any("GV-05: no attestation on file" in r for r in verdict.reasons)


def test_a_future_dated_waiver_is_not_yet_active(registry, band_b_request):
    waivers = _register(registry, _waiver(issued_at=NOW + DAY, expires_at=NOW + 10 * DAY))
    gate = GovernanceGate(registry, _store_missing(registry, "GV-05"), waivers)
    assert gate.evaluate(band_b_request, at=NOW).decision is Decision.DENY


def test_ttl_beyond_the_policy_maximum_is_refused(registry):
    with pytest.raises(WaiverError, match="standing waiver"):
        _register(registry, _waiver(expires_at=NOW + timedelta(days=400)))


def test_expiry_before_issue_is_refused():
    with pytest.raises(WaiverError, match="expires before it begins"):
        Waiver.from_dict(
            {
                **_waiver().to_dict(),
                "issued_at": NOW.isoformat(),
                "expires_at": (NOW - DAY).isoformat(),
            }
        )


# ---- malformed records -------------------------------------------------


@pytest.mark.parametrize(
    "field", ["id", "control", "accountable", "issued_by", "compensating_control", "ratification_ref"]
)
def test_a_blank_accountability_field_is_not_a_lenient_one(field):
    payload = {**_waiver().to_dict(), field: "   "}
    with pytest.raises(WaiverError, match="non-empty"):
        Waiver.from_dict(payload)


def test_an_unscoped_waiver_is_refused():
    with pytest.raises(WaiverError, match="waiver-by-default|bands"):
        Waiver.from_dict({**_waiver().to_dict(), "bands": []})


def test_a_naive_expiry_is_refused():
    with pytest.raises(WaiverError, match="no timezone"):
        Waiver.from_dict({**_waiver().to_dict(), "expires_at": "2026-12-01T00:00:00"})


def test_duplicate_ids_are_refused(registry):
    with pytest.raises(WaiverError, match="duplicate waiver id"):
        _register(registry, _waiver(), _waiver(control="GV-04"))


def test_unknown_control_and_band_are_refused(registry):
    with pytest.raises(WaiverError, match="not a defined control"):
        _register(registry, _waiver(control="GV-99"))
    with pytest.raises(WaiverError, match="undefined band"):
        _register(registry, _waiver(bands=("BAND-Z",)))


def test_malformed_json_line_raises_rather_than_being_skipped(tmp_path, registry):
    path = tmp_path / "waivers.jsonl"
    path.write_text(json.dumps(_waiver().to_dict()) + "\n{not json}\n", encoding="utf-8")
    with pytest.raises(WaiverError, match="malformed JSON"):
        WaiverRegister.for_registry(registry, path=path)


def test_a_bom_does_not_make_the_file_unreadable(tmp_path, registry):
    """PowerShell writes one by default; it must not fail for the wrong reason."""
    path = tmp_path / "waivers.jsonl"
    path.write_text(json.dumps(_waiver().to_dict()) + "\n", encoding="utf-8-sig")
    assert len(WaiverRegister.for_registry(registry, path=path)) == 1


# ---- scope -------------------------------------------------------------


def test_a_waiver_does_not_leak_into_a_band_it_does_not_name(registry):
    """BAND-D inherits GV-05 by monotonicity; a BAND-B waiver does not follow it."""
    waivers = _register(registry, _waiver(bands=("BAND-B",)))
    gate = GovernanceGate(registry, _store_missing(registry, "GV-05"), waivers)
    band_d = AuthorityRequest(
        intent="assign a step to an actor",
        identity="agent-motor",
        role="motor",
        capability="IL-17",
        scope="bst-sa/orchestration",
        verifier="github-ci",
        rollback_tested=True,
    )
    assert gate.evaluate(band_d, at=NOW).decision is Decision.DENY

    wide = _register(registry, _waiver(bands=("BAND-B", "BAND-D")))
    allowed = GovernanceGate(registry, _store_missing(registry, "GV-05"), wide)
    verdict = allowed.evaluate(band_d, at=NOW)
    assert verdict.decision is Decision.ALLOW
    # One waiver, listed once, though it is consumed at two bands in the closure.
    assert verdict.waivers == ("W-TEST-1",)


def test_a_waiver_does_not_cancel_the_per_request_obligation(registry, band_b_request):
    """Waiving GV-05 at programme level leaves TESTED_ROLLBACK owed per request."""
    waivers = _register(registry, _waiver())
    gate = GovernanceGate(registry, _store_missing(registry, "GV-05"), waivers)
    assert Obligation.TESTED_ROLLBACK in gate.evaluate(band_b_request, at=NOW).obligations

    untested = AuthorityRequest(
        intent="run a governed execution step",
        identity="agent-drafter",
        role="drafter",
        capability="IL-06",
        scope="bst-sa/pipelines",
        verifier="github-ci",
        rollback_tested=False,
    )
    assert gate.evaluate(untested, at=NOW).decision is Decision.DENY


# ---- renewal chains ----------------------------------------------------


def test_one_renewal_is_permitted(registry, band_b_request):
    first = _waiver(id="W-1", expires_at=NOW - timedelta(hours=1))
    second = _waiver(id="W-2", renews="W-1")
    waivers = _register(registry, first, second)
    gate = GovernanceGate(registry, _store_missing(registry, "GV-05"), waivers)
    assert gate.evaluate(band_b_request, at=NOW).decision is Decision.ALLOW


def test_a_second_renewal_is_refused_at_load(registry):
    """D-05's reversal trigger, enforced rather than remembered."""
    chain = (
        _waiver(id="W-1", issued_at=NOW - 30 * DAY, expires_at=NOW - 2 * DAY),
        _waiver(id="W-2", renews="W-1", issued_at=NOW - 2 * DAY, expires_at=NOW - DAY),
        _waiver(id="W-3", renews="W-2"),
    )
    with pytest.raises(WaiverError, match="renewal depth"):
        _register(registry, *chain)


def test_a_renewal_whose_predecessor_is_absent_is_refused(registry):
    """Dropping the predecessor would reset the renewal count to zero."""
    with pytest.raises(WaiverError, match="not in this register"):
        _register(registry, _waiver(id="W-3", renews="W-2"))


def test_a_renewal_may_not_change_control(registry):
    first = _waiver(id="W-1", control="GV-04", issued_at=NOW - 10 * DAY, expires_at=NOW - DAY)
    second = _waiver(id="W-2", control="GV-05", renews="W-1")
    with pytest.raises(WaiverError, match="changes control|not GV-05|which waives"):
        _register(registry, first, second)


def test_a_waiver_cannot_renew_itself(registry):
    with pytest.raises(WaiverError, match="renews itself"):
        Waiver.from_dict({**_waiver(id="W-1").to_dict(), "renews": "W-1"})


def test_an_active_renewal_arms_the_reversal_trigger(registry):
    waivers = _register(
        registry,
        _waiver(id="W-1", issued_at=NOW - 10 * DAY, expires_at=NOW - DAY),
        _waiver(id="W-2", renews="W-1"),
    )
    armed = waivers.triggers(NOW)
    assert any("renewal of W-1" in line for line in armed)


# ---- the active cap ----------------------------------------------------


def test_exceeding_the_active_cap_voids_every_waiver(registry, band_b_request):
    """Over the cap the matrix is mis-calibrated, so the exception path shuts."""
    two = _register(
        registry,
        _waiver(id="W-1", control="GV-05"),
        _waiver(id="W-2", control="GV-04", bands=("BAND-B",)),
    )
    gate_ok = GovernanceGate(registry, _store_missing(registry, "GV-05"), two)
    assert gate_ok.evaluate(band_b_request, at=NOW).decision is Decision.ALLOW

    three = _register(
        registry,
        _waiver(id="W-1", control="GV-05"),
        _waiver(id="W-2", control="GV-04", bands=("BAND-B",)),
        _waiver(id="W-3", control="GV-06", bands=("BAND-D",)),
    )
    gate_over = GovernanceGate(registry, _store_missing(registry, "GV-05"), three)
    verdict = gate_over.evaluate(band_b_request, at=NOW)
    assert verdict.decision is Decision.DENY
    assert any("D-05" in line for line in three.triggers(NOW))


def test_the_cap_counts_active_waivers_not_recorded_ones(registry, band_b_request):
    """Expired records accumulate in an append-only file; they must not count."""
    waivers = _register(
        registry,
        _waiver(id="W-OLD-1", control="GV-04", issued_at=NOW - 40 * DAY, expires_at=NOW - 5 * DAY),
        _waiver(
            id="W-OLD-2", control="GV-06", bands=("BAND-D",),
            issued_at=NOW - 40 * DAY, expires_at=NOW - 4 * DAY,
        ),
        _waiver(
            id="W-OLD-3", control="GV-07", bands=("BAND-G",),
            issued_at=NOW - 40 * DAY, expires_at=NOW - 3 * DAY,
        ),
        _waiver(id="W-NOW", control="GV-05"),
    )
    gate = GovernanceGate(registry, _store_missing(registry, "GV-05"), waivers)
    assert gate.evaluate(band_b_request, at=NOW).decision is Decision.ALLOW
    assert waivers.triggers(NOW) == ()


# ---- reporting ---------------------------------------------------------


def test_status_reports_conditional_rather_than_attained(registry):
    resolver = BandResolver(
        registry, _store_missing(registry, "GV-05"), _register(registry, _waiver())
    )
    status = resolver.status("BAND-B", at=NOW)
    assert status.attained is True
    assert status.conditional is True
    assert status.waived_controls == ("GV-05",)
    assert status.to_dict()["conditional"] is True


def test_an_unconditional_band_is_not_marked_conditional(registry):
    status = BandResolver(registry, _store_missing(registry)).status("BAND-B", at=NOW)
    assert status.attained is True
    assert status.conditional is False


def test_a_prerequisite_waiver_is_named_in_the_dependent_band(registry):
    resolver = BandResolver(
        registry,
        _store_missing(registry, "GV-05"),
        _register(registry, _waiver(bands=("BAND-B", "BAND-D"))),
    )
    reasons = resolver.status("BAND-D", at=NOW).reasons
    assert any("prerequisite attained under waiver" in r for r in reasons)


# ---- the monotonicity invariant ----------------------------------------


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


def test_a_band_may_not_require_fewer_controls_than_its_prerequisite(tmp_path):
    path = tmp_path / "neuraxis.yaml"
    path.write_text(
        yaml.safe_dump(_two_band_registry(["GV-01", "GV-04"], ["GV-01"])), encoding="utf-8"
    )
    with pytest.raises(RegistryError, match="monotonic staircase"):
        load_registry(path)


def test_a_monotonic_registry_loads(tmp_path):
    path = tmp_path / "neuraxis.yaml"
    path.write_text(
        yaml.safe_dump(_two_band_registry(["GV-01"], ["GV-01", "GV-04"])), encoding="utf-8"
    )
    assert load_registry(path).band("BAND-B").requires == ("GV-01", "GV-04")


def test_the_shipped_registry_declares_the_four_non_compensable_controls(registry):
    assert registry.waiver_policy.non_compensable == frozenset({"GV-01", "GV-02", "GV-03", "GV-08"})
    assert registry.waiver_policy.max_active == 2
    assert registry.waiver_policy.max_renewals == 1
    assert registry.waiver_policy.max_ttl == timedelta(days=90)


def test_waiver_policy_rejects_a_boolean_bound(tmp_path):
    data = _two_band_registry(["GV-01"], ["GV-01", "GV-04"])
    data["enforcement"]["waivers"] = {"max_active": True}
    path = tmp_path / "neuraxis.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(RegistryError, match="non-negative integer"):
        load_registry(path)


def test_waiver_policy_rejects_an_undefined_non_compensable_control(tmp_path):
    data = _two_band_registry(["GV-01"], ["GV-01", "GV-04"])
    data["enforcement"]["waivers"] = {"non_compensable": ["GV-99"]}
    path = tmp_path / "neuraxis.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(RegistryError, match="undefined control"):
        load_registry(path)


# ---- CLI ---------------------------------------------------------------


def _waivers_path(tmp_path):
    return str(tmp_path / "waivers.jsonl")


def test_cli_waive_then_waivers_roundtrip(tmp_path, capsys):
    path = _waivers_path(tmp_path)
    code = main([
        "--waivers", path, "waive",
        "--id", "W-D06", "--control", "GV-07", "--band", "BAND-G",
        "--accountable", "OP-Vily", "--issued-by", "ops-console",
        "--compensating", "break-glass merge logged to the evidence sink",
        "--ratification-ref", "KBS-001/7.7", "--ttl", "30d",
    ])
    assert code == 0
    assert "W-D06" in capsys.readouterr().out

    assert main(["--waivers", path, "waivers"]) == 0
    out = capsys.readouterr().out
    assert "ACTIVE" in out and "GV-07" in out and "OP-Vily" in out


def test_cli_waive_refuses_a_non_compensable_control(tmp_path, capsys):
    code = main([
        "--waivers", _waivers_path(tmp_path), "waive",
        "--id", "W-BAD", "--control", "GV-03", "--band", "BAND-A",
        "--accountable", "OP-Vily", "--issued-by", "ops-console",
        "--compensating", "nothing, which is the point",
        "--ratification-ref", "none", "--ttl", "30d",
    ])
    assert code == 2
    assert "non-compensable" in capsys.readouterr().err


def test_cli_waive_refuses_a_ttl_beyond_the_maximum(tmp_path, capsys):
    code = main([
        "--waivers", _waivers_path(tmp_path), "waive",
        "--id", "W-LONG", "--control", "GV-07", "--band", "BAND-G",
        "--accountable", "OP-Vily", "--issued-by", "ops-console",
        "--compensating", "x", "--ratification-ref", "y", "--ttl", "365d",
    ])
    assert code == 2
    assert "standing waiver" in capsys.readouterr().err


def test_cli_waivers_exits_nonzero_when_a_trigger_is_armed(tmp_path, capsys):
    path = tmp_path / "waivers.jsonl"
    records = [
        _waiver(id="W-1", control="GV-05"),
        _waiver(id="W-2", control="GV-04", bands=("BAND-B",)),
        _waiver(id="W-3", control="GV-06", bands=("BAND-D",)),
    ]
    path.write_text(
        "".join(json.dumps(w.to_dict(), sort_keys=True) + "\n" for w in records), encoding="utf-8"
    )
    assert main(["--waivers", str(path), "waivers"]) == 10
    assert "TRIGGER ARMED" in capsys.readouterr().out


def test_cli_waivers_is_clean_with_no_file(tmp_path, capsys):
    assert main(["--waivers", str(tmp_path / "absent.jsonl"), "waivers"]) == 0
    assert "gate is unconditional" in capsys.readouterr().out


def test_cli_waive_refuses_a_duplicate_id(tmp_path, capsys):
    path = _waivers_path(tmp_path)
    args = [
        "--waivers", path, "waive",
        "--id", "W-DUP", "--control", "GV-07", "--band", "BAND-G",
        "--accountable", "OP-Vily", "--issued-by", "ops-console",
        "--compensating", "x", "--ratification-ref", "y", "--ttl", "10d",
    ]
    assert main(args) == 0
    capsys.readouterr()
    assert main(args) == 2
    assert "already exists" in capsys.readouterr().err
