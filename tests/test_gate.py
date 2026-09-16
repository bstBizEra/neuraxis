"""Gate behaviour.

Every deny-assertion here is paired with the `valid_request` positive control
in `test_allows_when_everything_holds`. Without that pairing, a gate that
denied unconditionally would pass this entire file.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from neuraxis import (
    Attestation,
    AttestationStore,
    AuthorityRequest,
    Decision,
    GovernanceGate,
    Obligation,
    Risk,
)
from neuraxis.model import now_utc


@pytest.fixture
def gate(registry, full_store):
    return GovernanceGate(registry, full_store)


# ---- positive control --------------------------------------------------


def test_allows_when_everything_holds(gate, valid_request):
    """POSITIVE CONTROL. If this fails, every other test in this file is vacuous."""
    verdict = gate.evaluate(valid_request)
    assert verdict.decision is Decision.ALLOW
    assert verdict.permits_action is True
    assert verdict.band == "BAND-B"
    assert verdict.missing_controls == ()


def test_allow_carries_the_obligations_of_its_band(gate, valid_request):
    verdict = gate.evaluate(valid_request)
    assert Obligation.EMIT_EVIDENCE in verdict.obligations
    assert Obligation.INDEPENDENT_VERIFICATION in verdict.obligations
    assert Obligation.TESTED_ROLLBACK in verdict.obligations


# ---- authority ---------------------------------------------------------


def test_denies_when_no_attestations_exist(registry, empty_store, valid_request):
    gate = GovernanceGate(registry, empty_store)
    verdict = gate.evaluate(valid_request)
    assert verdict.decision is Decision.DENY
    assert "GV-01" in verdict.missing_controls


def test_denies_when_one_required_control_expires(registry, valid_request):
    """One stale control out of ten closes the band.

    GV-01 is chosen because it carries a 24h window; the staleness must be
    measured against the control's own window, not a global one. The store is
    built stale rather than back-dated after the fact, since newest-wins would
    correctly discard an older record pushed over a fresh one.
    """
    stale = registry.max_age_for("GV-01") + timedelta(hours=6)
    store = AttestationStore(
        Attestation(
            control=control,
            result=True,
            issued_at=now_utc() - (stale if control == "GV-01" else timedelta(0)),
            issuer="harness",
            evidence_ref="test://stale" if control == "GV-01" else "test://fresh",
        )
        for control in registry.controls
    )
    verdict = GovernanceGate(registry, store).evaluate(valid_request)
    assert verdict.decision is Decision.DENY
    assert "GV-01" in verdict.missing_controls


def test_back_dated_record_cannot_close_an_open_band(registry, attest_all, valid_request):
    """Newest-wins: pushing an older record must not change current state."""
    store = attest_all(registry)
    store.record(
        Attestation(
            control="GV-04", result=False,
            issued_at=now_utc() - timedelta(hours=1),
            issuer="harness", evidence_ref="test://back-dated",
        )
    )
    assert GovernanceGate(registry, store).evaluate(valid_request).decision is Decision.ALLOW


def test_denial_reports_the_root_blocker_not_the_requested_band(registry, empty_store):
    """BAND-G is never the real problem; BAND-A is."""
    gate = GovernanceGate(registry, empty_store)
    verdict = gate.evaluate(
        AuthorityRequest(
            intent="evolve", identity="op", role="operator", capability="IL-33",
            scope="system", verifier="council", rollback_tested=True,
            ratification_ref="BADF-1",
        )
    )
    assert verdict.decision is Decision.DENY
    assert "BAND-A" in verdict.reasons[0]


# ---- role --------------------------------------------------------------


def test_delegates_when_another_role_holds_the_band(gate):
    verdict = gate.evaluate(
        AuthorityRequest(
            intent="orchestrate the workstream", identity="agent-drafter", role="drafter",
            capability="IL-17", scope="g1", verifier="ci", rollback_tested=True,
        )
    )
    assert verdict.decision is Decision.DELEGATE
    assert any("motor" in r or "operator" in r for r in verdict.reasons)


def test_unknown_role_delegates_rather_than_allowing(gate, valid_request):
    verdict = gate.evaluate(
        AuthorityRequest(**{**valid_request.__dict__, "role": "intruder"})
    )
    assert verdict.decision is not Decision.ALLOW


# ---- verifier independence (NX-INV-2) ----------------------------------


def test_denies_when_performer_verifies_itself(gate, valid_request):
    verdict = gate.evaluate(
        AuthorityRequest(
            **{**valid_request.__dict__, "verifier": "agent-drafter", "performer": "agent-drafter"}
        )
    )
    assert verdict.decision is Decision.DENY
    assert any("V = 0" in r for r in verdict.reasons)


def test_denies_when_no_verifier_is_named(gate, valid_request):
    verdict = gate.evaluate(AuthorityRequest(**{**valid_request.__dict__, "verifier": None}))
    assert verdict.decision is Decision.DENY
    assert any("no verifier named" in r for r in verdict.reasons)


# ---- reversibility (NX-INV-3) ------------------------------------------


def test_denies_when_rollback_is_untested(gate, valid_request):
    verdict = gate.evaluate(
        AuthorityRequest(**{**valid_request.__dict__, "rollback_tested": False})
    )
    assert verdict.decision is Decision.DENY
    assert any("untested rollback counts as none" in r for r in verdict.reasons)


# ---- ratification ------------------------------------------------------


def test_non_delegable_capability_waits_for_authority(gate):
    verdict = gate.evaluate(
        AuthorityRequest(
            intent="reorganise the agent topology", identity="op", role="operator",
            capability="IL-31", scope="system", verifier="council", rollback_tested=True,
        )
    )
    assert verdict.decision is Decision.WAIT_FOR_AUTHORITY
    assert any("non-delegable floor" in r for r in verdict.reasons)


def test_ratified_non_delegable_capability_is_allowed(gate):
    """Positive control for the ratification path."""
    verdict = gate.evaluate(
        AuthorityRequest(
            intent="reorganise the agent topology", identity="op", role="operator",
            capability="IL-31", scope="system", verifier="council", rollback_tested=True,
            ratification_ref="BADF-GATE-2026-09-15",
        )
    )
    assert verdict.decision is Decision.ALLOW


def test_band_g_requires_ratification_even_for_non_floor_capabilities(gate):
    verdict = gate.evaluate(
        AuthorityRequest(
            intent="improve the prompt template", identity="op", role="operator",
            capability="IL-13b", scope="skillshub", verifier="ci", rollback_tested=True,
        )
    )
    assert verdict.decision is Decision.WAIT_FOR_AUTHORITY
    assert any("GV-07" in r for r in verdict.reasons)


# ---- risk --------------------------------------------------------------


def test_critical_risk_escalates_even_when_attained(gate, valid_request):
    verdict = gate.evaluate(
        AuthorityRequest(**{**valid_request.__dict__, "risk": Risk.CRITICAL})
    )
    assert verdict.decision is Decision.ESCALATE


def test_high_risk_below_threshold_still_allows(gate, valid_request):
    verdict = gate.evaluate(AuthorityRequest(**{**valid_request.__dict__, "risk": Risk.HIGH}))
    assert verdict.decision is Decision.ALLOW


# ---- serialisation -----------------------------------------------------


def test_verdict_serialises_to_the_json_contract(gate, valid_request):
    import json

    payload = json.loads(gate.evaluate(valid_request).to_json())
    assert payload["decision"] == "ALLOW"
    assert payload["capability"] == "IL-06"
    assert isinstance(payload["obligations"], list)
    assert isinstance(payload["reasons"], list)
