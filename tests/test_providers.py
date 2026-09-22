"""Provider harness conformance (v0.3).

The harness exists because the KBS-001 review found three of five assurance
probes passing unconditionally. These tests assert that each way a provider can
be broken produces a FAIL rather than a green attestation.
"""

from __future__ import annotations

import json

import pytest

from neuraxis.errors import NeuraxisError
from neuraxis.providers import (
    Provider,
    ProviderOutcome,
    ProviderResult,
    UnwiredProvider,
    get_provider,
    providers_for,
    register,
    run_provider,
)
from neuraxis.providers.builtin import VerifierIndependenceProvider
from neuraxis.providers.registry import PROVIDERS, UnknownProviderError


class _Base(Provider):
    control = "GV-04"
    name = "test/base"

    def positive_control(self) -> bool:
        return True

    def vacuity_probe(self) -> ProviderResult:
        return ProviderResult.failed("probe correctly fails")

    def check(self) -> ProviderResult:
        return ProviderResult.passed("test://evidence", "all good")


# ---- positive control for the harness itself ---------------------------


def test_conformant_provider_passes():
    """POSITIVE CONTROL. Without this, every FAIL assertion below is vacuous."""
    run = run_provider(_Base())
    assert run.attests is True
    assert run.result.outcome is ProviderOutcome.PASS
    assert run.conformance == ()


def test_passing_run_converts_to_a_recordable_attestation():
    attestation = run_provider(_Base()).to_attestation()
    assert attestation.control == "GV-04"
    assert attestation.result is True
    assert attestation.evidence_ref == "test://evidence"


# ---- rule 1: fail closed -----------------------------------------------


def test_check_that_raises_becomes_fail():
    class Exploding(_Base):
        def check(self) -> ProviderResult:
            raise RuntimeError("source unreachable")

    run = run_provider(Exploding())
    assert run.attests is False
    assert "check-raised" in run.conformance


def test_positive_control_that_raises_becomes_fail():
    class Exploding(_Base):
        def positive_control(self) -> bool:
            raise RuntimeError("cannot reach source")

    run = run_provider(Exploding())
    assert run.attests is False
    assert "positive-control-raised" in run.conformance


def test_vacuity_probe_that_raises_becomes_fail():
    class Exploding(_Base):
        def vacuity_probe(self) -> ProviderResult:
            raise RuntimeError("probe broken")

    run = run_provider(Exploding())
    assert run.attests is False
    assert "vacuity-probe-raised" in run.conformance


def test_wrong_return_type_becomes_fail():
    class Sloppy(_Base):
        def check(self):  # type: ignore[override]
            return True

    run = run_provider(Sloppy())
    assert run.attests is False
    assert "bad-return-type" in run.conformance


# ---- rule 2: positive control -------------------------------------------


def test_dead_check_cannot_pass():
    """A denial from a check that is not live proves nothing."""

    class Dead(_Base):
        def positive_control(self) -> bool:
            return False

    run = run_provider(Dead())
    assert run.attests is False
    assert "positive-control-failed" in run.conformance
    assert "not live" in run.result.detail


# ---- rule 3: vacuity ----------------------------------------------------


def test_provider_whose_vacuity_probe_passes_is_rejected():
    """A check returning the same result for a must-fail condition is not a check."""

    class Vacuous(_Base):
        def vacuity_probe(self) -> ProviderResult:
            return ProviderResult.passed("test://anything", "passes everything")

    run = run_provider(Vacuous())
    assert run.attests is False
    assert "vacuous" in run.conformance
    assert "discriminates nothing" in run.result.detail


# ---- rule 4: evidence ---------------------------------------------------


def test_pass_without_evidence_reference_is_rejected():
    class Unreferenced(_Base):
        def check(self) -> ProviderResult:
            return ProviderResult(ProviderOutcome.PASS, "   ", "trust me")

    run = run_provider(Unreferenced())
    assert run.attests is False
    assert "no-evidence" in run.conformance


def test_failure_without_evidence_is_allowed():
    """Only a PASS needs a reference; a FAIL may have nothing to cite."""

    class Failing(_Base):
        def check(self) -> ProviderResult:
            return ProviderResult.failed("control does not hold")

    run = run_provider(Failing())
    assert run.attests is False
    assert run.conformance == ()


# ---- unwired ------------------------------------------------------------


def test_unwired_provider_reports_as_unwired_not_as_a_violation():
    run = run_provider(UnwiredProvider("GV-01", "kbs/probe", "KBS-001 T1"))
    assert run.attests is False
    assert run.result.outcome is ProviderOutcome.UNWIRED
    assert run.conformance == ("unwired",)
    assert "KBS-001 T1" in run.result.detail


def test_unwired_attestation_records_false_and_says_why():
    attestation = run_provider(UnwiredProvider("GV-01", "kbs/probe", "T1")).to_attestation()
    assert attestation.result is False
    assert attestation.evidence_ref.startswith("unwired:")


# ---- the real provider --------------------------------------------------


def _log(tmp_path, records):
    path = tmp_path / "task-log.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return path


def test_verifier_independence_passes_on_a_clean_log(tmp_path):
    path = _log(tmp_path, [
        {"task_id": "t1", "performer": "agent-drafter", "verifier": "github-ci"},
        {"task_id": "t2", "performer": "agent-motor", "verifier": "github-ci"},
    ])
    run = run_provider(VerifierIndependenceProvider(log_path=path))
    assert run.attests is True
    assert run.result.facts["sampled"] == 2


def test_verifier_independence_fails_on_a_self_verified_task(tmp_path):
    path = _log(tmp_path, [
        {"task_id": "t1", "performer": "agent-drafter", "verifier": "github-ci"},
        {"task_id": "t2", "performer": "agent-cortex", "verifier": "agent-cortex"},
    ])
    run = run_provider(VerifierIndependenceProvider(log_path=path))
    assert run.attests is False
    assert "verifier equals performer" in run.result.detail


def test_verifier_independence_fails_when_verifier_is_absent(tmp_path):
    path = _log(tmp_path, [{"task_id": "t1", "performer": "agent-drafter"}])
    run = run_provider(VerifierIndependenceProvider(log_path=path))
    assert run.attests is False
    assert "no verifier recorded" in run.result.detail


def test_missing_log_fails_the_positive_control(tmp_path):
    """No log means the check is not live, which is a FAIL, not a PASS."""
    run = run_provider(VerifierIndependenceProvider(log_path=tmp_path / "absent.jsonl"))
    assert run.attests is False
    assert "positive-control-failed" in run.conformance


def test_empty_log_fails_rather_than_passing_trivially(tmp_path):
    """Zero breaches out of zero tasks is not evidence of independence."""
    path = _log(tmp_path, [])
    run = run_provider(VerifierIndependenceProvider(log_path=path))
    assert run.attests is False


def test_malformed_log_fails(tmp_path):
    path = tmp_path / "task-log.jsonl"
    path.write_text("{not json\n", encoding="utf-8")
    run = run_provider(VerifierIndependenceProvider(log_path=path))
    assert run.attests is False


def test_its_own_vacuity_probe_fails_as_required(tmp_path):
    """The provider's must-fail probe must actually fail."""
    provider = VerifierIndependenceProvider(log_path=tmp_path / "x.jsonl")
    assert provider.vacuity_probe().outcome is ProviderOutcome.FAIL


# ---- registry -----------------------------------------------------------


def test_every_control_has_a_declared_provider(registry):
    covered = {p.control for p in providers_for()}
    assert covered == set(registry.controls), "an undeclared control is an invisible gap"


def test_wired_providers_are_exactly_the_ones_with_a_real_source():
    """Asserts the set, not a count — a count says nothing about which moved."""
    wired = sorted(p.name for p in providers_for() if not isinstance(p, UnwiredProvider))
    assert wired == [
        "badf/gate-log",
        "l0/lease-audit",
        "l0/scope-budget",
        "nx/rollback-drill",
        "nx/verifier-independence",
    ]


def test_every_unwired_provider_names_a_blocker():
    for provider in providers_for():
        if isinstance(provider, UnwiredProvider):
            assert provider.blocked_on, f"{provider.name} is unwired with no blocker named"


def test_get_provider_by_name():
    assert get_provider("nx/verifier-independence").control == "GV-04"


def test_unknown_provider_name_raises():
    with pytest.raises(UnknownProviderError):
        get_provider("nx/does-not-exist")


class _ForUnwired(_Base):
    """A real provider for a control that ships as an UNWIRED stub."""

    control = "GV-01"
    name = "test/real-kernel-probe"


def test_registering_over_a_wired_builtin_is_refused():
    """Extras run after builtins, so a shadow's attestation would win."""
    with pytest.raises(NeuraxisError, match="wired builtin"):
        register("test/shadow-gv04", lambda **_: _Base())
    assert "test/shadow-gv04" not in PROVIDERS


def test_registering_a_builtin_name_is_refused():
    with pytest.raises(NeuraxisError, match="is a builtin"):
        register("nx/verifier-independence", lambda **_: _Base())


def test_registering_over_an_unwired_stub_replaces_it():
    """The supported extension path: wire a control this package cannot."""
    register("test/real-kernel-probe", lambda **_: _ForUnwired())
    try:
        covering = [p for p in providers_for("GV-01")]
        assert [p.name for p in covering] == ["test/real-kernel-probe"]
        assert not isinstance(covering[0], UnwiredProvider)
    finally:
        PROVIDERS.pop("test/real-kernel-probe", None)


def test_registering_a_duplicate_name_is_refused():
    name = "test/duplicate-guard"
    register(name, lambda **_: _ForUnwired())
    try:
        with pytest.raises(NeuraxisError, match="already registered"):
            register(name, lambda **_: _ForUnwired())
    finally:
        PROVIDERS.pop(name, None)
