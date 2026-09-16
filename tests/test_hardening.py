"""Regressions from the v1.0 adversarial review.

Every test here corresponds to a confirmed exploit against v0.5.2. They are
kept together because the class of defect is the same in each case: a check
that reported a pass on evidence, or a request, that should not have produced
one — and in several cases the docstring above the code asserted the property
the code did not have.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from neuraxis import (
    Attestation,
    AttestationStore,
    AuthorityRequest,
    Decision,
    GovernanceGate,
    load_registry,
)
from neuraxis.errors import RegistryError
from neuraxis.providers import run_provider
from neuraxis.providers.builtin import GateLogRatificationProvider
from neuraxis.providers.lease import LeaseContainmentProvider

UTC = timezone.utc
NOW = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)


# ---- S3: the only attestation attack that survives an append-only sink ----


def test_an_appended_pass_cannot_overtake_a_fail_at_the_same_instant():
    """No edit, no clock advance — just an append. Ties must go to the denial."""
    store = AttestationStore([
        Attestation("GV-04", False, NOW, "p", "e1"),
        Attestation("GV-04", True, NOW, "p", "e2"),
    ])
    assert store.get("GV-04").result is False
    assert store.holds("GV-04", timedelta(days=7), at=NOW) is False


def test_a_genuinely_newer_pass_still_supersedes_a_fail():
    """Positive control: the tie-break must not freeze the store on any FAIL."""
    store = AttestationStore([
        Attestation("GV-04", False, NOW, "p", "e1"),
        Attestation("GV-04", True, NOW + timedelta(seconds=1), "p", "e2"),
    ])
    assert store.get("GV-04").result is True


# ---- S10: the loader and a line-based auditor must see the same records ----


@pytest.mark.parametrize("sep", ["\v", "\f", "\x1c", "\x85", " "])
def test_exotic_separators_do_not_split_records(tmp_path, sep):
    """splitlines() breaks on these; wc, diff and a per-line hasher do not."""
    path = tmp_path / "attestations.jsonl"
    payload = {
        "control": "GV-01", "result": True, "issued_at": NOW.isoformat(),
        "issuer": "op", "evidence_ref": f"a{sep}b",
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    store = AttestationStore.from_file(path)
    assert len(store) == 1


# ---- S4: gate obligations satisfied by whitespace or a fictitious performer ----


@pytest.fixture
def gate():
    registry = load_registry()
    store = AttestationStore(
        Attestation(c, True, datetime.now(UTC), "h", "r", provenance="provider")
        for c in registry.controls
    )
    return GovernanceGate(registry, store)


BASE = dict(intent="i", identity="agent-x", role="drafter", capability="IL-06", scope="s")


def test_naming_a_fictitious_performer_does_not_buy_self_verification(gate):
    verdict = gate.evaluate(
        AuthorityRequest(**BASE, performer="ghost", verifier="agent-x", rollback_tested=True)
    )
    assert verdict.decision is Decision.DENY
    assert "identities this request claims" in " ".join(verdict.reasons)


@pytest.mark.parametrize("verifier", ["agent-x ", " agent-x", "Agent-X", "AGENT-X"])
def test_verifier_comparison_is_stripped_and_case_folded(gate, verifier):
    verdict = gate.evaluate(AuthorityRequest(**BASE, verifier=verifier, rollback_tested=True))
    assert verdict.decision is Decision.DENY


@pytest.mark.parametrize("verifier", [" ", "", "\t"])
def test_a_blank_verifier_is_no_verifier(gate, verifier):
    verdict = gate.evaluate(AuthorityRequest(**BASE, verifier=verifier, rollback_tested=True))
    assert verdict.decision is Decision.DENY
    assert "no verifier named" in " ".join(verdict.reasons)


def test_a_distinct_verifier_still_allows(gate):
    """Positive control for the independence check."""
    verdict = gate.evaluate(AuthorityRequest(**BASE, verifier="github-ci", rollback_tested=True))
    assert verdict.decision is Decision.ALLOW


@pytest.mark.parametrize("value", ["false", "no", "0", 1, 0.1, [], {}])
def test_rollback_tested_must_be_a_real_boolean(value):
    """`"false"` is a non-empty string; truthiness let the word satisfy NX-INV-3."""
    with pytest.raises(ValueError, match="must be a JSON boolean"):
        AuthorityRequest.from_dict({**BASE, "verifier": "v", "rollback_tested": value})


def test_a_real_boolean_still_parses():
    request = AuthorityRequest.from_dict({**BASE, "verifier": "v", "rollback_tested": True})
    assert request.rollback_tested is True


def test_a_whitespace_ratification_reference_is_not_a_reference(gate):
    verdict = gate.evaluate(
        AuthorityRequest(
            intent="i", identity="op", role="operator", capability="IL-31", scope="s",
            verifier="council", rollback_tested=True, ratification_ref="   ",
        )
    )
    assert verdict.decision is Decision.WAIT_FOR_AUTHORITY


# ---- S1: a band that requires nothing licenses everything ----


def test_a_band_requiring_no_controls_is_rejected(tmp_path):
    data = {
        "framework": "t", "version": "1",
        "governance": {"GV-01": {"name": "identity", "attestation": "x"}},
        "capabilities": {"IL-32": {"name": "Self-Evolving", "band": "BAND-G", "question": "?"}},
        "bands": {"BAND-G": {"requires": [], "depends_on": []}},
        "authority": {"role_grants": {"drafter": ["BAND-G"]}},
        "enforcement": {"on_missing_attestation": "deny"},
    }
    path = tmp_path / "evil.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(RegistryError, match="requires no controls"):
        load_registry(path)


# ---- S5: the GV-06 vacuous-pass family ----


def _lease(**over):
    base = {
        "record": "lease", "lease_id": "L", "principal": "a", "issued_by": "g",
        "issued_at": NOW.isoformat(), "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        "scope": ["s"], "ceilings": {"tokens": 100}, "consumed": {"tokens": 10},
    }
    base.update(over)
    return base


def _gv06(tmp_path, record, raw=None):
    path = tmp_path / "lease-log.jsonl"
    path.write_text(raw if raw is not None else json.dumps(record), encoding="utf-8")
    return run_provider(LeaseContainmentProvider(lease_log_path=path))


def test_containment_still_passes_a_clean_lease(tmp_path):
    """Positive control."""
    assert _gv06(tmp_path, _lease()).attests is True


def test_omitted_consumption_is_not_zero_consumption(tmp_path):
    record = {k: v for k, v in _lease().items() if k != "consumed"}
    run = _gv06(tmp_path, record)
    assert run.attests is False
    assert "not an object" in run.result.detail


@pytest.mark.parametrize("consumed", [{}, [], 0, "", None])
def test_empty_or_wrong_typed_consumption_is_a_breach(tmp_path, consumed):
    run = _gv06(tmp_path, _lease(consumed=consumed))
    assert run.attests is False


def test_a_declared_ceiling_with_no_reported_usage_is_a_breach(tmp_path):
    """Under-reporting was undetectable: the loop iterated consumption."""
    run = _gv06(tmp_path, _lease(ceilings={"tokens": 100, "wall_seconds": 900}))
    assert run.attests is False
    assert "no consumption reported" in run.result.detail


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "1e999"])
def test_non_finite_numbers_are_a_breach(tmp_path, literal):
    """NaN loses every comparison silently; json.loads accepts the bare literal."""
    # 7, not 10: `"tokens": 10` is a substring of the ceiling `"tokens": 100`,
    # so replacing it would corrupt the ceiling and the record would not parse.
    raw = json.dumps(_lease(consumed={"tokens": 7})).replace('"tokens": 7', f'"tokens": {literal}')
    run = _gv06(tmp_path, None, raw=raw)
    assert run.attests is False
    assert "not finite" in run.result.detail or "over ceiling" in run.result.detail


# ---- S6: ratification made simultaneous with the merge ----


def _gate_log(tmp_path, **over):
    base = {
        "change_id": "C-1", "proposer": "agent-drafter", "ratifier": "vily",
        "ratifier_kind": "human",
        "ratified_at": (NOW + timedelta(hours=1)).isoformat(),
        "merged_at": (NOW + timedelta(hours=1, minutes=2)).isoformat(),
    }
    base.update(over)
    path = tmp_path / "gate-log.jsonl"
    path.write_text(json.dumps(base), encoding="utf-8")
    return run_provider(GateLogRatificationProvider(gate_log_path=path))


def test_ratification_at_the_merge_instant_is_a_breach(tmp_path):
    """A stamp emitted by the same automated step as the merge."""
    at = (NOW + timedelta(hours=1)).isoformat()
    run = _gate_log(tmp_path, ratified_at=at, merged_at=at)
    assert run.attests is False
    assert "at or after merge" in run.result.detail


def test_ratification_before_the_merge_still_passes(tmp_path):
    """Positive control."""
    assert _gate_log(tmp_path).attests is True


@pytest.mark.parametrize("value", ["", 0, None])
def test_a_present_but_empty_proposed_at_is_a_breach(tmp_path, value):
    """Absent is fine; present-and-empty was a free pass while garbage was not."""
    run = _gate_log(tmp_path, proposed_at=value)
    assert run.attests is False
    assert "present but empty" in run.result.detail


def test_an_absent_proposed_at_is_still_permitted(tmp_path):
    """The field is optional; only a present-but-falsy one is a breach."""
    assert _gate_log(tmp_path).attests is True
