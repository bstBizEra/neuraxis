"""W9's third clause (v0.12.0) — a verifier may not hold authority over what it verifies.

ILR-001-DR W9: *deny if the verifying principal is the performing principal, is
controlled by it, or shares its envelope.* The first clause shipped in v0.6.0
and was hardened in v0.8.0. The third became checkable when envelopes arrived
in v0.9.0 and is enforced here.

The second — *is controlled by it* — is deliberately absent. It needs a
principal graph that does not exist until T1, and a check that always answers
"no control relation known" is the vacuous probe this package refuses
everywhere else. There is a test below asserting it is absent rather than
stubbed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from neuraxis import (
    Attestation,
    AttestationStore,
    AuthorityRequest,
    Decision,
    Envelope,
    EnvelopeRegister,
    GovernanceGate,
)
from neuraxis.model import normalise_principal, strict_principal

UTC = timezone.utc
NOW = datetime(2026, 9, 16, 9, 0, tzinfo=UTC)
DAY = timedelta(days=1)
SCOPE = "bst-sa/pipelines"


def _store(registry) -> AttestationStore:
    return AttestationStore(
        Attestation(c, True, NOW, "h", f"test://{c}", provenance="provider")
        for c in registry.controls
    )


def _envelope(**overrides) -> Envelope:
    fields = {
        "id": "ENV-V",
        "principal": "agent-motor",
        "capability": "IL-13a",
        "signed_by": "ops-console",
        "manifest_ref": "bst-sa/manifest#v7",
        "targets": (SCOPE,),
        "limits": {"retry_budget": [1, 5]},
        "issued_at": NOW - DAY,
        "expires_at": NOW + 29 * DAY,
    }
    fields.update(overrides)
    return Envelope(**fields)


def _gate(registry, *envelopes) -> GovernanceGate:
    return GovernanceGate(
        registry, _store(registry), None,
        EnvelopeRegister.for_registry(registry, envelopes=envelopes),
    )


def _request(**overrides) -> AuthorityRequest:
    fields = {
        "intent": "ship a governed execution step",
        "identity": "agent-drafter",
        "role": "drafter",
        "capability": "IL-06",          # BAND-B, which requires GV-04
        "scope": SCOPE,
        "verifier": "github-ci",
        "rollback_tested": True,
    }
    fields.update(overrides)
    return AuthorityRequest(**fields)


# ---- positive control --------------------------------------------------


def test_an_uninvolved_verifier_is_accepted(registry):
    """Without this, every deny below could be an unconditional deny."""
    verdict = _gate(registry, _envelope()).evaluate(_request(), at=NOW)
    assert verdict.decision is Decision.ALLOW


def test_no_envelopes_at_all_changes_nothing(registry):
    assert _gate(registry).evaluate(_request(), at=NOW).decision is Decision.ALLOW


# ---- the clause --------------------------------------------------------


def test_a_verifier_holding_authority_over_the_scope_is_refused(registry):
    verdict = _gate(registry, _envelope(principal="agent-motor")).evaluate(
        _request(verifier="agent-motor"), at=NOW
    )
    assert verdict.decision is Decision.DENY
    assert any("ENV-V" in r for r in verdict.reasons)
    assert any("stake" in r for r in verdict.reasons)


def test_authority_over_a_different_target_is_not_a_conflict(registry):
    verdict = _gate(registry, _envelope(targets=("hippocampus/lessons",))).evaluate(
        _request(verifier="agent-motor"), at=NOW
    )
    assert verdict.decision is Decision.ALLOW


def test_authority_under_the_scope_counts(registry):
    """A bound over `a/b` is authority over `a/b/c`."""
    verdict = _gate(registry, _envelope(targets=("bst-sa",))).evaluate(
        _request(verifier="agent-motor"), at=NOW
    )
    assert verdict.decision is Decision.DENY


def test_a_neighbouring_target_is_not_authority(registry):
    """`bst-sa/pipelines-archive` is not `bst-sa/pipelines`."""
    verdict = _gate(registry, _envelope(targets=("bst-sa/pipelines-archive",))).evaluate(
        _request(verifier="agent-motor"), at=NOW
    )
    assert verdict.decision is Decision.ALLOW


def test_the_capability_of_the_envelope_does_not_matter(registry):
    """The question is whether the verifier can write there, not what for."""
    verdict = _gate(registry, _envelope(capability="IL-13a")).evaluate(
        _request(verifier="agent-motor", capability="IL-06"), at=NOW
    )
    assert verdict.decision is Decision.DENY


# ---- expiry ------------------------------------------------------------


def test_an_expired_envelope_is_not_authority(registry):
    verdict = _gate(
        registry, _envelope(issued_at=NOW - 30 * DAY, expires_at=NOW - DAY)
    ).evaluate(_request(verifier="agent-motor"), at=NOW)
    assert verdict.decision is Decision.ALLOW


def test_an_envelope_not_yet_active_is_not_authority(registry):
    verdict = _gate(
        registry, _envelope(issued_at=NOW + DAY, expires_at=NOW + 10 * DAY)
    ).evaluate(_request(verifier="agent-motor"), at=NOW)
    assert verdict.decision is Decision.ALLOW


def test_authority_lapses_with_the_envelope(registry):
    gate = _gate(registry, _envelope(expires_at=NOW + DAY))
    store = AttestationStore(
        Attestation(c, True, NOW + 2 * DAY, "h", f"test://{c}", provenance="provider")
        for c in registry.controls
    )
    later = GovernanceGate(registry, store, None, gate.envelopes)
    assert gate.evaluate(_request(verifier="agent-motor"), at=NOW).decision is Decision.DENY
    assert later.evaluate(
        _request(verifier="agent-motor"), at=NOW + 2 * DAY
    ).decision is Decision.ALLOW


# ---- the fold runs the other way ---------------------------------------


def test_this_clause_folds_to_deny_where_the_authorising_path_folds_to_grant(registry):
    """The asymmetry, asserted directly.

    `bounds()` authorises on a match, so `agent-motor` and `agent-mötor` must
    stay two principals. `may_bind()` denies on a match, so the same two must
    collide. Reusing one for the other is the mistake the v0.9.0 review found.
    """
    env = _envelope(principal="agent-mötor")
    assert env.bounds("agent-motor") is False
    assert env.may_bind("agent-motor") is True
    assert strict_principal("agent-mötor") != strict_principal("agent-motor")
    assert normalise_principal("agent-mötor") == normalise_principal("agent-motor")


@pytest.mark.parametrize(
    "spelling", ["agent-motor", "AGENT-MOTOR", "agent-mötor", "  agent-motor  "]
)
def test_a_lookalike_verifier_does_not_escape_the_clause(registry, spelling):
    verdict = _gate(registry, _envelope(principal="agent-motor")).evaluate(
        _request(verifier=spelling), at=NOW
    )
    assert verdict.decision is Decision.DENY


def test_an_invisible_character_in_the_verifier_does_not_escape_it(registry):
    verdict = _gate(registry, _envelope(principal="agent-motor")).evaluate(
        _request(verifier="agent-motor​"), at=NOW
    )
    assert verdict.decision is Decision.DENY


# ---- an unreadable scope is not an absence of authority ----------------


def test_an_uncomparable_scope_is_treated_as_overlapping(registry):
    """"Nobody can parse this" is not a basis for concluding "no authority"."""
    verdict = _gate(registry, _envelope(targets=("hippocampus/lessons",))).evaluate(
        _request(verifier="agent-motor", scope="bst-sa/../../elsewhere"), at=NOW
    )
    assert verdict.decision is Decision.DENY
    assert any("bst-sa/../../elsewhere" in r for r in verdict.reasons)


def test_an_uncomparable_scope_with_no_bound_verifier_is_not_denied_by_this_clause(registry):
    verdict = _gate(registry, _envelope(principal="someone-else")).evaluate(
        _request(verifier="github-ci", scope="bst-sa/../../elsewhere"), at=NOW
    )
    assert verdict.decision is Decision.ALLOW


# ---- ordering and scope of the check -----------------------------------


def test_being_the_performer_is_still_reported_as_that(registry):
    """Clause 1 keeps its own message; the new clause does not swallow it."""
    verdict = _gate(registry, _envelope(principal="agent-drafter")).evaluate(
        _request(verifier="agent-drafter"), at=NOW
    )
    assert verdict.decision is Decision.DENY
    assert any("V = 0 when performer and verifier" in r for r in verdict.reasons)


def test_the_clause_only_applies_where_gv_04_is_required(registry):
    """BAND-A does not require GV-04, so no verifier question arises there."""
    verdict = _gate(registry, _envelope(targets=("cognition",))).evaluate(
        AuthorityRequest(
            intent="reason about state", identity="agent-drafter", role="drafter",
            capability="IL-01", scope="cognition", verifier="agent-motor",
        ),
        at=NOW,
    )
    assert verdict.decision is Decision.ALLOW


# ---- the clause that is deliberately missing ---------------------------


def test_the_controlled_by_clause_is_absent_rather_than_stubbed(registry):
    """W9's second clause needs a principal graph, which arrives with T1.

    A stub answering "no control relation known" would pass every test and
    check nothing, which is the vacuous probe. Its absence is asserted so that
    adding one has to be a deliberate act with a real graph behind it.
    """
    doc = GovernanceGate._check_verifier_independence.__doc__ or ""
    assert "is controlled by it" in doc
    assert "not** enforced" in doc

    # And the behaviour that proves it is absent rather than half-present:
    # sharing a *signer* is a plausible control relation, and it is not
    # treated as one. Whether it should be is a question for the principal
    # graph T1 brings, not for a guess made here.
    verdict = _gate(
        registry,
        _envelope(id="ENV-P", principal="agent-drafter", targets=("hippocampus/lessons",)),
        _envelope(id="ENV-V2", principal="agent-motor", targets=("elsewhere",)),
    ).evaluate(_request(verifier="agent-motor"), at=NOW)
    assert verdict.decision is Decision.ALLOW


# ---- the lookup, directly ----------------------------------------------


def test_authority_over_returns_the_envelopes_it_matched(registry):
    register = EnvelopeRegister.for_registry(
        registry,
        envelopes=[
            _envelope(id="ENV-A", principal="agent-motor", targets=("bst-sa",)),
            _envelope(id="ENV-B", principal="agent-motor", targets=("elsewhere",)),
            _envelope(id="ENV-C", principal="other", targets=("bst-sa",)),
        ],
    )
    hits = register.authority_over("agent-motor", SCOPE, at=NOW)
    assert [e.id for e in hits] == ["ENV-A"]
    assert register.authority_over("nobody", SCOPE, at=NOW) == ()
