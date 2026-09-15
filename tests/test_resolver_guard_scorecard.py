from __future__ import annotations

from datetime import timedelta

import pytest

from neuraxis import (
    Attestation,
    AttestationStore,
    AuthorityRequest,
    BandResolver,
    CapabilityDenied,
    CapabilityGuard,
    Decision,
    Risk,
    Scorecard,
    measure,
)
from neuraxis.model import now_utc

# ---- resolver ----------------------------------------------------------


def test_all_bands_attained_when_all_controls_hold(registry, full_store):
    resolver = BandResolver(registry, full_store)
    assert set(resolver.attained_bands()) == set(registry.bands)


def test_band_a_attainable_with_only_its_two_controls(registry):
    store = AttestationStore(
        Attestation(control=c, result=True, issued_at=now_utc(), issuer="h", evidence_ref="r")
        for c in ("GV-01", "GV-03")
    )
    resolver = BandResolver(registry, store)
    assert resolver.status("BAND-A").attained is True
    assert resolver.status("BAND-B").attained is False


def test_prerequisite_failure_propagates_upward(registry, attest_all):
    store = attest_all(registry)
    store.record(
        Attestation(control="GV-01", result=False, issued_at=now_utc(), issuer="h", evidence_ref="r")
    )
    resolver = BandResolver(registry, store)
    assert resolver.attained_bands() == ()
    assert resolver.first_blocker("BAND-G").band == "BAND-A"


def test_status_always_explains_itself(registry, empty_store):
    status = BandResolver(registry, empty_store).status("BAND-B")
    assert status.attained is False
    assert status.reasons, "a blocked band must say why"


# ---- guard -------------------------------------------------------------


def test_guard_context_manager_yields_on_allow(registry, full_store, valid_request):
    guard = CapabilityGuard(registry, full_store)
    with guard.require(valid_request) as verdict:
        assert verdict.decision is Decision.ALLOW


def test_guard_raises_on_any_non_allow(registry, empty_store, valid_request):
    guard = CapabilityGuard(registry, empty_store)
    with pytest.raises(CapabilityDenied) as exc:
        with guard.require(valid_request):
            pytest.fail("body must not execute when the gate denies")
    assert exc.value.verdict.decision is Decision.DENY


def test_guard_decorator_blocks_the_function_body(registry, empty_store):
    guard = CapabilityGuard(registry, empty_store)
    calls: list[int] = []

    @guard.capability("IL-06", role="drafter", verifier="ci", rollback_tested=True)
    def run() -> str:
        calls.append(1)
        return "ran"

    with pytest.raises(CapabilityDenied):
        run()
    assert calls == [], "decorated body executed despite a DENY"


def test_guard_decorator_runs_the_body_on_allow(registry, full_store):
    """Positive control for the decorator."""
    guard = CapabilityGuard(registry, full_store)

    @guard.capability("IL-06", role="drafter", identity="agent-drafter",
                      verifier="github-ci", rollback_tested=True)
    def run() -> str:
        return "ran"

    assert run() == "ran"


def test_guard_check_does_not_raise(registry, empty_store, valid_request):
    guard = CapabilityGuard(registry, empty_store)
    assert guard.check(valid_request).decision is Decision.DENY


# ---- scorecard ---------------------------------------------------------


def test_performer_as_verifier_forces_v_to_zero():
    card = measure(
        bands_attained=7, bands_total=7, exam_first_pass_rate=1.0, lesson_yield=1.0,
        retrieval_precision=1.0, tasks_completed=10, tasks_attempted=10,
        independent_verification_coverage=1.0, performer_is_verifier=True,
        controls_passing=10, controls_required=10,
    )
    assert card.V == 0.0
    assert card.effective == 0.0
    assert "V" in card.zeroed_terms


def test_any_zero_term_zeroes_the_product():
    assert Scorecard(C=1, R=1, L=1, A=1, V=1, G=0).effective == 0.0
    assert Scorecard(C=1, R=0, L=1, A=1, V=1, G=1).effective == 0.0


def test_perfect_scorecard_permits_band_g(registry):
    card = Scorecard(C=1, R=1, L=1, A=1, V=1, G=1)
    permitted, reasons = card.gate_band(registry, "BAND-G")
    assert permitted is True
    assert reasons


def test_band_g_blocked_when_verification_is_partial(registry):
    card = Scorecard(C=1, R=1, L=1, A=1, V=0.9, G=1)
    permitted, reasons = card.gate_band(registry, "BAND-G")
    assert permitted is False
    assert any("V = 0.90" in r for r in reasons)


def test_same_scorecard_may_pass_a_lower_band(registry):
    card = Scorecard(C=1, R=0.75, L=1, A=1, V=0.6, G=1)
    assert card.gate_band(registry, "BAND-C")[0] is True
    assert card.gate_band(registry, "BAND-F")[0] is False


def test_governance_integrity_below_one_blocks_every_band(registry):
    card = Scorecard(C=1, R=1, L=1, A=1, V=1, G=0.9)
    for band in registry.bands:
        assert card.gate_band(registry, band)[0] is False


def test_learning_term_is_a_product_of_yield_and_precision():
    card = measure(
        bands_attained=1, bands_total=7, exam_first_pass_rate=0.5, lesson_yield=0.5,
        retrieval_precision=0.4, tasks_completed=1, tasks_attempted=2,
        independent_verification_coverage=0.5, performer_is_verifier=False,
        controls_passing=1, controls_required=2,
    )
    assert card.L == pytest.approx(0.2)


@pytest.mark.parametrize("term", ["C", "R", "L", "A", "V", "G"])
def test_out_of_range_terms_are_rejected(term):
    values = dict(C=0.5, R=0.5, L=0.5, A=0.5, V=0.5, G=0.5)
    values[term] = 1.5
    with pytest.raises(ValueError):
        Scorecard(**values)


def test_impossible_measurements_are_rejected():
    base = dict(
        bands_attained=1, bands_total=7, exam_first_pass_rate=0.5, lesson_yield=0.5,
        retrieval_precision=0.5, tasks_completed=1, tasks_attempted=1,
        independent_verification_coverage=0.5, performer_is_verifier=False,
        controls_passing=1, controls_required=1,
    )
    with pytest.raises(ValueError):
        measure(**{**base, "tasks_completed": 5, "tasks_attempted": 2})
    with pytest.raises(ValueError):
        measure(**{**base, "controls_passing": 5, "controls_required": 2})
    with pytest.raises(ValueError):
        measure(**{**base, "bands_total": 0})
