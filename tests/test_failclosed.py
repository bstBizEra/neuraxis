"""Fail-closed invariants.

The KBS-001 adversarial review found that most assurance failures are not
wrong policy but broken checks scoring as passes. These tests exist so that a
fault in Neuraxis becomes a DENY rather than an implicit ALLOW.
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
    load_registry,
)
from neuraxis.model import now_utc


@pytest.fixture
def gate(registry, full_store):
    return GovernanceGate(registry, full_store)


def test_unknown_capability_denies(gate, valid_request):
    """An unknown capability is an ungoverned one, so it is refused."""
    verdict = gate.evaluate(AuthorityRequest(**{**valid_request.__dict__, "capability": "IL-99"}))
    assert verdict.decision is Decision.DENY
    assert "ungoverned" in " ".join(verdict.reasons)


def test_internal_fault_denies_rather_than_raising(registry, full_store, valid_request):
    """A gate that crashes open is not a gate."""
    gate = GovernanceGate(registry, full_store)

    class Exploding:
        def first_blocker(self, *_args, **_kwargs):
            raise RuntimeError("resolver exploded")

    gate.resolver = Exploding()  # type: ignore[assignment]
    verdict = gate.evaluate(valid_request)
    assert verdict.decision is Decision.DENY
    assert "denying" in " ".join(verdict.reasons)


def test_every_band_is_blocked_with_no_attestations(registry, empty_store):
    from neuraxis import BandResolver

    resolver = BandResolver(registry, empty_store)
    assert resolver.attained_bands() == ()


def test_partial_attestation_does_not_open_a_band(registry, valid_request):
    """Nine of ten controls is not ten."""
    store = AttestationStore(
        Attestation(control=c, result=True, issued_at=now_utc(), issuer="h", evidence_ref="r")
        for c in list(registry.controls)[:-1]
    )
    from neuraxis import BandResolver

    assert "BAND-G" not in BandResolver(registry, store).attained_bands()


def test_all_decisions_except_allow_block_action(gate, valid_request):
    for decision in Decision:
        assert decision.permits_action is (decision is Decision.ALLOW)


def test_empty_request_fields_are_rejected_at_construction():
    with pytest.raises(ValueError):
        AuthorityRequest(intent="", identity="a", role="r", capability="IL-01", scope="s")
    with pytest.raises(ValueError):
        AuthorityRequest(intent="i", identity="  ", role="r", capability="IL-01", scope="s")


def test_unknown_request_fields_are_rejected_not_ignored():
    """A typo'd field must not silently drop a constraint."""
    with pytest.raises(ValueError, match="unknown request fields"):
        AuthorityRequest.from_dict(
            {
                "intent": "i", "identity": "a", "role": "operator",
                "capability": "IL-01", "scope": "s", "rollbackTested": True,
            }
        )


def test_json_contract_roundtrip_preserves_constraints(registry, full_store):
    request = AuthorityRequest.from_dict(
        {
            "intent": "run pipeline", "identity": "agent-drafter", "role": "drafter",
            "capability": "IL-06", "scope": "bst-sa", "risk": "low",
            "verifier": "github-ci", "rollback_tested": True,
        }
    )
    assert GovernanceGate(registry, full_store).evaluate(request).decision is Decision.ALLOW


def test_expired_attestation_closes_a_previously_attained_band(registry, attest_all, valid_request):
    fresh = attest_all(registry)
    stale = attest_all(registry, age=timedelta(days=31))  # past every window

    assert GovernanceGate(registry, fresh).evaluate(valid_request).decision is Decision.ALLOW
    assert GovernanceGate(registry, stale).evaluate(valid_request).decision is Decision.DENY


def test_failing_attestation_closes_a_band(registry, attest_all, valid_request):
    failing = attest_all(registry, result=False)
    assert GovernanceGate(registry, failing).evaluate(valid_request).decision is Decision.DENY


def test_registry_default_is_the_bundled_kernel_copy():
    """load_registry() with no argument must not fall back to a permissive default."""
    registry = load_registry()
    assert registry.on_missing_attestation == "deny"
    assert registry.enforcement_mode == "l0-mechanical"
