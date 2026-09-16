"""Bounded self-tuning (v0.9.0) — ILR-001-DR D-01.

The ruling splits IL-13 rather than relocating it, on the argument that an
unenforceable prohibition is worse than none because it moves the activity out
of view. That only holds if the replacement line is mechanical, so most of
these tests try to get an adjustment authorised that should not be: with no
bound, with someone else's bound, with a bound that matches everything, with
one signed by the component it constrains.
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
    Limit,
    audit_envelopes,
    load_registry,
)
from neuraxis.cli import main
from neuraxis.envelope import OUT_OF_ENVELOPE
from neuraxis.errors import RegistryError

UTC = timezone.utc
NOW = datetime(2026, 9, 16, 9, 0, tzinfo=UTC)
DAY = timedelta(days=1)


# ---- helpers -----------------------------------------------------------


def _store(registry, *absent: str, issued_at: datetime = NOW) -> AttestationStore:
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


def _envelope(**overrides) -> Envelope:
    fields = {
        "id": "ENV-1",
        "principal": "agent-cortex",
        "capability": "IL-13a",
        "signed_by": "ops-console",
        "manifest_ref": "bst-sa/manifest#v7",
        "targets": ("hippocampus/lessons",),
        "limits": {"retry_budget": [1, 5], "confidence_floor": [0.5, 0.95]},
        "issued_at": NOW - DAY,
        "expires_at": NOW + 29 * DAY,
    }
    fields.update(overrides)
    return Envelope(**fields)


def _register(registry, *envelopes) -> EnvelopeRegister:
    return EnvelopeRegister.for_registry(registry, envelopes=envelopes)


def _tune(**overrides) -> AuthorityRequest:
    fields = {
        "intent": "raise the retry budget for the lesson promoter",
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


def _gate(registry, envelopes=None, store=None) -> GovernanceGate:
    return GovernanceGate(registry, store or _store(registry), None, envelopes)


# ---- the split ---------------------------------------------------------


def test_self_tuning_is_admissible_from_band_c(registry):
    assert registry.capability("IL-13a").band == "BAND-C"
    assert registry.capability("IL-13a").envelope_bounded is True


def test_self_modifying_stays_in_band_g_and_is_not_envelope_bounded(registry):
    assert registry.capability("IL-13b").band == "BAND-G"
    assert registry.capability("IL-13b").envelope_bounded is False


def test_a_declared_bound_authorises_the_adjustment(registry):
    """The positive control. Without it every deny below could be unconditional."""
    verdict = _gate(registry, _register(registry, _envelope())).evaluate(_tune(), at=NOW)
    assert verdict.decision is Decision.ALLOW
    assert any("bounded by envelope ENV-1" in r for r in verdict.reasons)


def test_no_envelope_named_is_il_13b_by_another_name(registry):
    verdict = _gate(registry, _register(registry, _envelope())).evaluate(
        _tune(envelope_ref=None), at=NOW
    )
    assert verdict.decision is Decision.DENY
    assert any("names no envelope" in r for r in verdict.reasons)


def test_an_absent_envelope_file_denies_every_bounded_capability(registry):
    """"Declared in advance" means the default is not permission."""
    assert _gate(registry).evaluate(_tune(), at=NOW).decision is Decision.DENY


def test_an_unknown_envelope_ref_is_not_a_bound(registry):
    verdict = _gate(registry, _register(registry, _envelope())).evaluate(
        _tune(envelope_ref="ENV-NOPE"), at=NOW
    )
    assert verdict.decision is Decision.DENY
    assert any("not on file" in r for r in verdict.reasons)


# ---- the self-signing rule ---------------------------------------------


def test_an_envelope_cannot_be_signed_by_the_principal_it_bounds():
    """D-01's second deny: widening your own bound is IL-13b."""
    with pytest.raises(EnvelopeError, match="signed by the principal it bounds"):
        _envelope(signed_by="agent-cortex")


@pytest.mark.parametrize(
    "disguise", ["Agent-Cortex", "  agent-cortex ", "agent-cortex​", "agent-cörtex"]
)
def test_self_signing_survives_case_whitespace_and_confusables(disguise):
    with pytest.raises(EnvelopeError):
        _envelope(principal="agent-cortex", signed_by=disguise)


def test_an_envelope_does_not_bound_a_principal_it_does_not_name(registry):
    verdict = _gate(registry, _register(registry, _envelope(principal="agent-motor"))).evaluate(
        _tune(), at=NOW
    )
    assert verdict.decision is Decision.DENY
    assert any("bounds 'agent-motor'" in r for r in verdict.reasons)


def test_a_borrowed_envelope_is_refused_even_when_the_performer_is_named(registry):
    """`performer` is requester-supplied, so it cannot unlock someone else's bound."""
    envelopes = _register(registry, _envelope(principal="agent-motor"))
    borrowed = _tune(identity="agent-cortex", performer="agent-motor")
    verdict = _gate(registry, envelopes).evaluate(borrowed, at=NOW)
    assert verdict.decision is Decision.DENY
    assert any("not self-tuning" in r for r in verdict.reasons)


def test_an_envelope_does_not_license_tuning_on_another_principals_behalf(registry):
    """The mirror: the bound principal acting for someone else is equally out."""
    envelopes = _register(registry, _envelope(principal="agent-cortex"))
    delegated = _tune(identity="agent-cortex", performer="agent-motor")
    assert _gate(registry, envelopes).evaluate(delegated, at=NOW).decision is Decision.DENY


# ---- machine-evaluability ----------------------------------------------


@pytest.mark.parametrize("target", ["*", "**", "/", "**/*", "/*"])
def test_a_target_matching_everything_is_not_a_boundary(target):
    with pytest.raises(EnvelopeError, match="matches everything"):
        _envelope(targets=(target,))


def test_an_envelope_with_no_target_is_refused():
    with pytest.raises(EnvelopeError, match="not machine-evaluable"):
        _envelope(targets=())


def test_a_string_of_targets_is_not_a_list_of_targets():
    """`band in "a b"` is substring matching; the same trap as the waiver path."""
    with pytest.raises(EnvelopeError, match="bare string is not a list"):
        _envelope(targets="hippocampus/lessons other/thing")


def test_a_target_matches_on_a_separator_boundary(registry):
    envelopes = _register(registry, _envelope(targets=("hippocampus/lessons",)))
    gate = _gate(registry, envelopes)
    assert gate.evaluate(_tune(scope="hippocampus/lessons"), at=NOW).decision is Decision.ALLOW
    assert gate.evaluate(
        _tune(scope="hippocampus/lessons/deep/er"), at=NOW
    ).decision is Decision.ALLOW
    verdict = gate.evaluate(_tune(scope="hippocampus/lessons-archive"), at=NOW)
    assert verdict.decision is Decision.DENY
    assert any(r.startswith(OUT_OF_ENVELOPE) for r in verdict.reasons)


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_a_non_finite_limit_is_not_a_limit(bad):
    """`x <= inf` is always true and every NaN comparison is false."""
    with pytest.raises(EnvelopeError, match="finite"):
        _envelope(limits={"retry_budget": [1, bad]})


def test_an_inverted_limit_is_refused():
    with pytest.raises(EnvelopeError, match="exceeds high"):
        _envelope(limits={"retry_budget": [9, 1]})


@pytest.mark.parametrize("shape", ["1:5", [1], [1, 2, 3], {"low": 1}, 5])
def test_a_limit_that_is_not_an_interval_is_prose(shape):
    with pytest.raises(EnvelopeError):
        _envelope(limits={"retry_budget": shape})


def test_a_boolean_limit_bound_is_refused():
    with pytest.raises(EnvelopeError, match="must be a number"):
        _envelope(limits={"retry_budget": [True, 5]})


# ---- staying inside the bound ------------------------------------------


def test_an_adjustment_outside_the_declared_interval_is_denied(registry):
    verdict = _gate(registry, _register(registry, _envelope())).evaluate(
        _tune(adjustments={"retry_budget": 50}), at=NOW
    )
    assert verdict.decision is Decision.DENY
    assert any(r.startswith(OUT_OF_ENVELOPE) and "retry_budget=50" in r for r in verdict.reasons)


def test_an_undeclared_parameter_is_denied(registry):
    verdict = _gate(registry, _register(registry, _envelope())).evaluate(
        _tune(adjustments={"kill_switch_delay": 1}), at=NOW
    )
    assert verdict.decision is Decision.DENY
    assert any("is not a parameter ENV-1 declares" in r for r in verdict.reasons)


def test_the_interval_is_closed_at_both_ends(registry):
    gate = _gate(registry, _register(registry, _envelope()))
    for value, expected in ((1, Decision.ALLOW), (5, Decision.ALLOW), (5.0001, Decision.DENY)):
        assert gate.evaluate(_tune(adjustments={"retry_budget": value}), at=NOW).decision is expected


def test_a_boolean_adjustment_is_refused_at_the_request(registry):
    """An envelope bounds magnitudes; `True` would otherwise read as 1."""
    with pytest.raises(ValueError, match="must be a number"):
        _tune(adjustments={"retry_budget": True})


def test_an_empty_adjustment_set_still_needs_the_target_to_be_covered(registry):
    verdict = _gate(registry, _register(registry, _envelope())).evaluate(
        _tune(adjustments={}, scope="motor/queues"), at=NOW
    )
    assert verdict.decision is Decision.DENY


def test_a_denial_names_the_signer_who_could_widen_it(registry):
    """So the resolution is "ask the signer", not "declare a wider envelope"."""
    verdict = _gate(registry, _register(registry, _envelope())).evaluate(
        _tune(adjustments={"retry_budget": 50}), at=NOW
    )
    assert any("signed by ops-console" in r for r in verdict.reasons)


# ---- expiry and scope --------------------------------------------------


def test_an_envelope_is_expired_at_its_expiry_instant(registry):
    envelopes = _register(registry, _envelope(expires_at=NOW))
    store = _store(registry, issued_at=NOW - timedelta(hours=2))
    gate = _gate(registry, envelopes, store)
    assert gate.evaluate(_tune(), at=NOW - timedelta(seconds=1)).decision is Decision.ALLOW
    assert gate.evaluate(_tune(), at=NOW).decision is Decision.DENY


def test_a_future_dated_envelope_is_not_yet_a_bound(registry):
    envelopes = _register(registry, _envelope(issued_at=NOW + DAY, expires_at=NOW + 10 * DAY))
    assert _gate(registry, envelopes).evaluate(_tune(), at=NOW).decision is Decision.DENY


def test_an_envelope_is_not_transferable_between_capabilities(registry):
    envelopes = _register(registry, _envelope(capability="IL-11"))
    verdict = _gate(registry, envelopes).evaluate(_tune(), at=NOW)
    assert verdict.decision is Decision.DENY
    assert any("not transferable" in r for r in verdict.reasons)


def test_ttl_beyond_the_policy_maximum_is_refused(registry):
    with pytest.raises(EnvelopeError, match="standing grant"):
        _register(registry, _envelope(expires_at=NOW + 200 * DAY))


def test_duplicate_envelope_ids_are_refused(registry):
    with pytest.raises(EnvelopeError, match="duplicate envelope id"):
        _register(registry, _envelope(), _envelope(targets=("motor/queues",)))


def test_an_envelope_for_an_undefined_capability_is_refused(registry):
    with pytest.raises(EnvelopeError, match="not a defined capability"):
        _register(registry, _envelope(capability="IL-99"))


def test_expires_before_issued_is_refused():
    with pytest.raises(EnvelopeError, match="no live interval"):
        _envelope(issued_at=NOW, expires_at=NOW - DAY)


def test_a_naive_timestamp_is_refused():
    with pytest.raises(EnvelopeError, match="no timezone"):
        Envelope.from_dict({**_envelope().to_dict(), "expires_at": "2026-12-01T00:00:00"})


def test_an_invisible_character_in_a_target_is_refused():
    with pytest.raises(EnvelopeError, match="invisible or control character"):
        _envelope(targets=("hippocampus/less​ons",))


# ---- signer restriction ------------------------------------------------


def test_a_restricted_signer_set_refuses_an_unlisted_signer(registry):
    policy = EnvelopePolicy(signers=frozenset({"ops-console"}), max_ttl=timedelta(days=90))
    EnvelopeRegister((_envelope(),), policy=policy)  # the listed signer is fine
    with pytest.raises(EnvelopeError, match="not a declared envelope signer"):
        EnvelopeRegister((_envelope(signed_by="agent-motor"),), policy=policy)


def test_the_shipped_registry_leaves_signers_unrestricted_and_says_so(registry, capsys):
    assert registry.envelope_policy.signers_restricted is False
    assert main(["--json", "validate"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert any("envelope_signers is empty" in w for w in payload["warnings"])


def test_envelope_bounded_must_be_written_as_a_boolean(tmp_path):
    data = {
        "framework": "test",
        "version": "0.1",
        "governance": {"GV-01": {"name": "identity", "attestation": "x/y"}},
        "capabilities": {
            "IL-01": {
                "name": "Thinkable", "band": "BAND-A", "question": "?",
                "envelope_bounded": "no",
            }
        },
        "bands": {"BAND-A": {"requires": ["GV-01"], "depends_on": []}},
        "authority": {"role_grants": {"operator": ["BAND-A"]}},
        "enforcement": {"on_missing_attestation": "deny", "attestation_max_age": "24h"},
    }
    path = tmp_path / "neuraxis.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(RegistryError, match="must be a YAML boolean"):
        load_registry(path)


def test_a_registry_cannot_declare_a_perpetual_envelope(tmp_path, registry):
    assert registry.envelope_policy.max_ttl == timedelta(days=90)


# ---- the D-01 reversal trigger -----------------------------------------


def _denial_row(ref: str, at: datetime, marked: bool = True) -> dict:
    return {
        "record": "evidence",
        "decision": "DENY",
        "envelope_ref": ref,
        "at": at.isoformat(),
        "reasons": [f"{OUT_OF_ENVELOPE}: scope outside targets"] if marked else ["denied"],
    }


def test_two_out_of_envelope_denials_arm_the_trigger():
    rows = [_denial_row("ENV-1", NOW - DAY), _denial_row("ENV-1", NOW - 2 * DAY)]
    audit = audit_envelopes(rows, at=NOW)
    assert audit.denials == {"ENV-1": 2}
    assert not audit.clean
    assert any("ENV-1 has 2 out-of-envelope denials" in line for line in audit.armed)


def test_one_denial_does_not_arm_the_trigger():
    audit = audit_envelopes([_denial_row("ENV-1", NOW - DAY)], at=NOW)
    assert audit.clean


def test_denials_outside_the_window_do_not_count():
    rows = [_denial_row("ENV-1", NOW - 200 * DAY), _denial_row("ENV-1", NOW - DAY)]
    assert audit_envelopes(rows, at=NOW).denials == {"ENV-1": 1}


def test_allows_and_unmarked_denials_do_not_count():
    rows = [
        {**_denial_row("ENV-1", NOW - DAY), "decision": "ALLOW"},
        _denial_row("ENV-1", NOW - DAY, marked=False),
    ]
    assert audit_envelopes(rows, at=NOW).denials == {}


def test_an_unparseable_timestamp_is_counted_rather_than_dropped():
    """Dropping it would make the trigger easier to avoid than to satisfy."""
    rows = [
        {**_denial_row("ENV-1", NOW - DAY), "at": "not-a-date"},
        {**_denial_row("ENV-1", NOW - DAY), "at": "also-not"},
    ]
    assert audit_envelopes(rows, at=NOW).denials == {"ENV-1": 2}


# ---- CLI ---------------------------------------------------------------


def _declare(path, capsys, **overrides):
    args = {
        "--id": "ENV-CLI", "--principal": "agent-cortex", "--capability": "IL-13a",
        "--signed-by": "ops-console", "--manifest-ref": "bst-sa/manifest#v7",
        "--target": "hippocampus/lessons", "--limit": "retry_budget=1:5", "--ttl": "30d",
    }
    args.update(overrides)
    argv = ["--envelopes", str(path), "declare"]
    for k, v in args.items():
        argv += [k, v]
    return main(argv)


def test_cli_declare_then_envelopes_roundtrip(tmp_path, capsys):
    path = tmp_path / "envelopes.jsonl"
    assert _declare(path, capsys) == 0
    capsys.readouterr()
    assert main(["--envelopes", str(path), "envelopes"]) == 0
    out = capsys.readouterr().out
    assert "ENV-CLI" in out and "ACTIVE" in out and "hippocampus/lessons" in out


def test_cli_declare_refuses_a_capability_the_gate_does_not_check(tmp_path, capsys):
    assert _declare(tmp_path / "e.jsonl", capsys, **{"--capability": "IL-11"}) == 2
    assert "not envelope-bounded" in capsys.readouterr().err


def test_cli_declare_refuses_a_self_signed_envelope(tmp_path, capsys):
    assert _declare(tmp_path / "e.jsonl", capsys, **{"--signed-by": "agent-cortex"}) == 2
    assert "signed by the principal it bounds" in capsys.readouterr().err


def test_cli_declare_refuses_a_vacuous_target(tmp_path, capsys):
    assert _declare(tmp_path / "e.jsonl", capsys, **{"--target": "*"}) == 2
    assert "matches everything" in capsys.readouterr().err


def test_cli_envelopes_warns_when_the_signer_set_is_unrestricted(tmp_path, capsys):
    assert main(["--envelopes", str(tmp_path / "absent.jsonl"), "envelopes"]) == 0
    out = capsys.readouterr().out
    assert "WARNING" in out and "envelope_signers is empty" in out
    assert "No envelopes on file" in out


def test_cli_envelopes_audit_exits_nonzero_when_the_trigger_is_armed(tmp_path, capsys):
    sink = tmp_path / "evidence.jsonl"
    sink.write_text(
        "".join(
            json.dumps(_denial_row("ENV-1", NOW - DAY)) + "\n" for _ in range(2)
        ),
        encoding="utf-8",
    )
    code = main([
        "--envelopes", str(tmp_path / "e.jsonl"), "--evidence-sink", str(sink),
        "envelopes", "--audit",
    ])
    assert code == 10
    assert "TRIGGER ARMED" in capsys.readouterr().out


def test_cli_gate_carries_the_envelope_into_the_evidence_record(tmp_path, capsys):
    envelopes = tmp_path / "envelopes.jsonl"
    assert _declare(envelopes, capsys) == 0
    capsys.readouterr()

    attestations = tmp_path / "attestations.jsonl"
    for control in ("GV-01", "GV-02", "GV-03", "GV-04", "GV-05", "GV-09"):
        main([
            "--attestations", str(attestations), "attest",
            "--control", control, "--result", "pass",
            "--issuer", "test", "--evidence-ref", f"test://{control}",
        ])
    capsys.readouterr()

    sink = tmp_path / "evidence.jsonl"
    code = main([
        "--attestations", str(attestations), "--envelopes", str(envelopes),
        "--evidence-sink", str(sink), "gate",
        "--capability", "IL-13a", "--identity", "agent-cortex", "--role", "cortex",
        "--intent", "raise the retry budget", "--scope", "hippocampus/lessons/thresholds",
        "--verifier", "github-ci", "--rollback-tested",
        "--envelope-ref", "ENV-CLI", "--adjust", "retry_budget=3",
    ])
    assert code == 0, capsys.readouterr()
    rows = [json.loads(line) for line in sink.read_text(encoding="utf-8").splitlines() if line]
    record = next(r for r in rows if r["record"] == "evidence")
    assert record["envelope_ref"] == "ENV-CLI"
    assert record["adjustments"] == {"retry_budget": 3.0}


def test_cli_gate_refuses_an_adjustment_that_is_not_a_number(tmp_path, capsys):
    code = main([
        "--envelopes", str(tmp_path / "e.jsonl"), "gate",
        "--capability", "IL-13a", "--identity", "a", "--role", "cortex",
        "--intent", "i", "--scope", "s", "--adjust", "retry_budget=lots",
    ])
    assert code == 2
    assert "not a number" in capsys.readouterr().err
