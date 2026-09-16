"""Regressions from the v0.9.0 adversarial review.

Each test here reproduces something that worked in the first cut of the
envelope path: a `../` that walked straight out of a declared target, a fold
that turned "is this you" into "close enough", four YAML tokens whose deletion
disabled D-01 in silence, and an envelope declaring no numeric bound at all
while reporting in every verdict as a bound.
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
    Envelope,
    EnvelopeError,
    EnvelopePolicy,
    EnvelopeRegister,
    GovernanceGate,
    audit_envelopes,
    load_registry,
)
from neuraxis.cli import main
from neuraxis.envelope import MAX_LIMIT_MAGNITUDE, OUT_OF_ENVELOPE
from neuraxis.errors import RegistryError
from neuraxis.evidence import EvidenceError
from neuraxis.model import normalise_principal, strict_principal

UTC = timezone.utc
NOW = datetime(2026, 9, 16, 9, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def _store(registry, *absent: str, issued_at: datetime = NOW) -> AttestationStore:
    return AttestationStore(
        Attestation(
            control=c, result=True, issued_at=issued_at,
            issuer="h", evidence_ref=f"test://{c}", provenance="provider",
        )
        for c in registry.controls
        if c not in absent
    )


def _envelope(**overrides) -> Envelope:
    fields = {
        "id": "ENV-1",
        "principal": "agent-cortex",
        "capability": "IL-13a",
        "signed_by": "ops-console",
        "manifest_ref": "bst-sa/manifest#v7",
        "targets": ("hippocampus/lessons",),
        "limits": {"retry_budget": [1, 5]},
        "issued_at": NOW - DAY,
        "expires_at": NOW + 29 * DAY,
    }
    fields.update(overrides)
    return Envelope(**fields)


def _tune(**overrides) -> AuthorityRequest:
    fields = {
        "intent": "raise the retry budget",
        "identity": "agent-cortex",
        "role": "cortex",
        "capability": "IL-13a",
        "scope": "hippocampus/lessons/thresholds",
        "verifier": "github-ci",
        "rollback_tested": True,
        "envelope_ref": "ENV-1",
        "adjustments": {"retry_budget": 3},
    }
    fields.update(overrides)
    return AuthorityRequest(**fields)


def _gate(registry, *envelopes) -> GovernanceGate:
    return GovernanceGate(
        registry, _store(registry), None,
        EnvelopeRegister.for_registry(registry, envelopes=envelopes),
    )


# ---- path traversal ----------------------------------------------------


@pytest.mark.parametrize(
    "scope",
    [
        "hippocampus/lessons/../../l0/kernel/policy.yaml",
        "hippocampus/lessons/../../../etc/shadow",
        "hippocampus/lessons/./../../secrets",
        "hippocampus/lessons//../../kernel",
        "hippocampus/lessons/%2e%2e/%2e%2e/kernel",
        "hippocampus/lessons\\..\\..\\kernel",
    ],
)
def test_a_target_prefix_cannot_be_walked_out_of(registry, scope):
    """`a/b/../../c` starts with `a/b/` and is not under it."""
    verdict = _gate(registry, _envelope()).evaluate(_tune(scope=scope), at=NOW)
    assert verdict.decision is Decision.DENY
    assert any(r.startswith(OUT_OF_ENVELOPE) for r in verdict.reasons)


def test_a_target_containing_a_traversal_is_refused_at_load():
    with pytest.raises(EnvelopeError, match="not a comparable path"):
        _envelope(targets=("hippocampus/../l0",))


def test_an_invisible_character_in_the_scope_is_refused(registry):
    verdict = _gate(registry, _envelope()).evaluate(
        _tune(scope="hippocampus/lessons/x​"), at=NOW
    )
    assert verdict.decision is Decision.DENY
    assert any("invisible character" in r for r in verdict.reasons)


# ---- equality authorises, so it must not fold --------------------------


@pytest.mark.parametrize(
    "impostor", ["agent-cörtex", "AGENT-CORTEX", "ａｇｅｎｔ－ｃｏｒｔｅｘ"]
)
def test_a_folded_lookalike_cannot_use_another_principals_envelope(registry, impostor):
    """`normalise_principal` folds these together; `bounds()` must not."""
    verdict = _gate(registry, _envelope(principal="agent-cortex")).evaluate(
        _tune(identity=impostor), at=NOW
    )
    assert verdict.decision is Decision.DENY


def test_the_two_principal_keys_disagree_exactly_where_intended():
    assert normalise_principal("agent-cörtex") == normalise_principal("agent-cortex")
    assert strict_principal("agent-cörtex") != strict_principal("agent-cortex")
    # ...while an invisible character still matches nothing under either.
    assert strict_principal("agent-cortex​") == ""


def test_the_signer_allowlist_does_not_admit_a_folded_lookalike():
    policy = EnvelopePolicy(signers=frozenset({"ops-console"}), max_ttl=timedelta(days=90))
    EnvelopeRegister((_envelope(signed_by="ops-console"),), policy=policy)
    for impostor in ("ops-cönsole", "OPS-CONSOLE", "ｏｐｓ－ｃｏｎｓｏｌｅ"):
        with pytest.raises(EnvelopeError, match="not a declared envelope signer"):
            EnvelopeRegister((_envelope(signed_by=impostor),), policy=policy)


def test_self_signing_still_uses_the_aggressive_fold():
    """The inequality-must-hold side keeps folding, so a lookalike is refused."""
    with pytest.raises(EnvelopeError, match="signed by the principal it bounds"):
        _envelope(principal="agent-cortex", signed_by="agent-cörtex")


# ---- the registry cross-check ------------------------------------------


def _mini(**overrides):
    data = {
        "framework": "test",
        "version": "0.1",
        "governance": {
            "GV-01": {"name": "identity", "attestation": "x/y"},
            "GV-04": {"name": "verification", "attestation": "x/y"},
        },
        "capabilities": {
            "IL-01": {"name": "Thinkable", "band": "BAND-A", "question": "?"},
            "IL-T": {
                "name": "Self-Tuning", "band": "BAND-B", "question": "?",
                "envelope_bounded": True,
            },
        },
        "bands": {
            "BAND-A": {"requires": ["GV-01"], "depends_on": []},
            "BAND-B": {"requires": ["GV-01", "GV-04"], "depends_on": ["BAND-A"]},
        },
        "authority": {
            "role_grants": {"operator": ["BAND-A", "BAND-B"]},
            "envelope_required": ["IL-T"],
            "envelope_signers": ["ops-console"],
        },
        "enforcement": {
            "on_missing_attestation": "deny",
            "attestation_max_age": "24h",
            "envelopes": {"max_ttl": "7d"},
        },
    }
    for key, value in overrides.items():
        data[key] = value
    return data


def _write(tmp_path, data):
    path = tmp_path / "neuraxis.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_dropping_envelope_bounded_no_longer_loads_silently(tmp_path):
    """The one-token deletion that turned IL-13a into unbounded self-tuning."""
    data = _mini()
    del data["capabilities"]["IL-T"]["envelope_bounded"]
    with pytest.raises(RegistryError, match="envelope_required but does not set"):
        load_registry(_write(tmp_path, data))


def test_envelope_required_must_name_a_real_capability(tmp_path):
    data = _mini()
    data["authority"]["envelope_required"] = ["IL-NOPE"]
    with pytest.raises(RegistryError, match="undefined capability"):
        load_registry(_write(tmp_path, data))


def test_the_shipped_registry_names_il_13a_in_both_places(registry):
    assert registry.capability("IL-13a").envelope_bounded is True
    # And the cross-check is live: the shipped file loaded, so the two agree.
    assert main(["--json", "validate"]) == 0


def test_a_malformed_signer_entry_is_a_registry_error(tmp_path):
    data = _mini()
    data["authority"]["envelope_signers"] = [["ops-console"]]
    with pytest.raises(RegistryError, match="not a principal name"):
        load_registry(_write(tmp_path, data))


# ---- a bound that bounds nothing ---------------------------------------


def test_an_envelope_with_no_limits_is_refused():
    with pytest.raises(EnvelopeError, match="declares no parameter"):
        _envelope(limits={})


def test_an_envelope_record_missing_the_limits_key_is_refused():
    payload = _envelope().to_dict()
    del payload["limits"]
    with pytest.raises(EnvelopeError, match="must be a mapping"):
        Envelope.from_dict(payload)


def test_an_unknown_envelope_field_is_refused():
    """A typo'd `limits_` would otherwise load as an envelope with no bounds."""
    with pytest.raises(EnvelopeError, match="unknown envelope field"):
        Envelope.from_dict({**_envelope().to_dict(), "limits_": {"x": [1, 2]}})


@pytest.mark.parametrize("bound", [1e308, -1e308, MAX_LIMIT_MAGNITUDE * 10])
def test_a_finite_but_absurd_bound_is_the_infinity_bypass(bound):
    with pytest.raises(EnvelopeError, match="maximum magnitude"):
        _envelope(limits={"retry_budget": [0, bound] if bound > 0 else [bound, 0]})


@pytest.mark.parametrize("shape", [range(2), bytearray(b"\x01\x05")])
def test_a_limit_must_be_a_list_or_tuple_not_any_sequence(shape):
    with pytest.raises(EnvelopeError, match="two-element"):
        _envelope(limits={"retry_budget": shape})


def test_an_empty_adjustment_set_is_not_an_adjustment(registry):
    verdict = _gate(registry, _envelope()).evaluate(_tune(adjustments={}), at=NOW)
    assert verdict.decision is Decision.DENY
    assert any("declares no adjustment" in r for r in verdict.reasons)


# ---- the policy is re-checked where it is used -------------------------


def test_a_register_built_outside_the_registry_policy_is_caught_at_the_gate(tmp_path):
    """One `EnvelopeRegister(...)` instead of `for_registry(...)` must not void the bounds."""
    reg = load_registry(_write(tmp_path, _mini()))
    loose = Envelope(
        id="ENV-LOOSE", principal="agent-x", capability="IL-T",
        signed_by="agent-motor",                 # not on the registry's allowlist
        manifest_ref="m#1", targets=("data/tunables",),
        limits={"retry_budget": [1, 5]},
        issued_at=NOW - DAY, expires_at=NOW + 60 * DAY,   # past the 7d ceiling
    )
    with pytest.raises(EnvelopeError):
        EnvelopeRegister.for_registry(reg, envelopes=[loose])

    gate = GovernanceGate(reg, _store(reg), None, EnvelopeRegister((loose,)))
    verdict = gate.evaluate(
        AuthorityRequest(
            intent="tune", identity="agent-x", role="operator", capability="IL-T",
            scope="data/tunables/retry", verifier="ci", envelope_ref="ENV-LOOSE",
            adjustments={"retry_budget": 3},
        ),
        at=NOW,
    )
    assert verdict.decision is Decision.DENY
    assert any("breaches this registry's envelope policy" in r for r in verdict.reasons)


@pytest.mark.parametrize("bad", [90, "90d", None, timedelta(0), timedelta(days=-5)])
def test_envelope_policy_refuses_a_ttl_that_is_not_a_positive_timedelta(bad):
    with pytest.raises(EnvelopeError):
        EnvelopePolicy(max_ttl=bad)


# ---- the audit ---------------------------------------------------------


def _row(ref: str, at: str) -> dict:
    return {
        "record": "evidence", "decision": "DENY", "envelope_ref": ref, "at": at,
        "reasons": [f"{OUT_OF_ENVELOPE}: scope outside targets"],
    }


def test_a_naive_timestamp_is_counted_not_dropped():
    """Dropping the offset was one edit away from a clean report."""
    rows = [_row("ENV-1", "2026-09-15T09:00:00") for _ in range(2)]
    audit = audit_envelopes(rows, at=NOW)
    assert audit.denials == {"ENV-1": 2}
    assert not audit.clean


def test_a_malformed_sink_line_becomes_a_fault_not_an_exception():
    def raising():
        yield _row("ENV-1", (NOW - DAY).isoformat())
        raise EvidenceError("sink.jsonl:2: malformed evidence record")

    audit = audit_envelopes(raising(), at=NOW)
    assert audit.faults and not audit.clean
    assert "could not be read" in audit.faults[0]


def test_the_threshold_travels_with_the_result():
    audit = audit_envelopes(
        [_row("ENV-1", (NOW - DAY).isoformat()) for _ in range(2)], threshold=7, at=NOW
    )
    assert audit.to_dict()["threshold"] == 7
    assert audit.clean and audit.denials == {"ENV-1": 2}


def test_an_expired_envelope_being_hammered_is_visible_to_the_trigger(registry):
    """Not a boundary breach in the narrow sense, but the split being leaned on."""
    envelopes = EnvelopeRegister.for_registry(
        registry, envelopes=[_envelope(issued_at=NOW - 10 * DAY, expires_at=NOW - DAY)]
    )
    gate = GovernanceGate(registry, _store(registry), None, envelopes)
    verdict = gate.evaluate(_tune(), at=NOW)
    assert verdict.decision is Decision.DENY
    assert any(r.startswith(OUT_OF_ENVELOPE) for r in verdict.reasons)


def test_cli_envelopes_audit_reports_a_sink_fault(tmp_path, capsys):
    sink = tmp_path / "evidence.jsonl"
    sink.write_text(json.dumps(_row("ENV-1", NOW.isoformat())) + "\n{\n", encoding="utf-8")
    code = main([
        "--envelopes", str(tmp_path / "e.jsonl"), "--evidence-sink", str(sink),
        "envelopes", "--audit",
    ])
    assert code == 10
    assert "AUDIT FAULT" in capsys.readouterr().out


# ---- a blank performer -------------------------------------------------


def test_a_blank_performer_is_refused_rather_than_silently_emptied():
    """`"   "` is truthy, so it emptied the recorded performer and switched off
    the obligation audit's self-discharge check."""
    with pytest.raises(ValueError, match="performer is blank"):
        _tune(performer="   ")
