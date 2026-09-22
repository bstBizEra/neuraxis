"""GV-05 reversibility — the rollback drill audit (v0.21.0).

The control says a change can be reversed. A drill is the only evidence for
that, and a 30-day window is a long time to keep one honest — long enough that
the drill becomes the thing you run to keep the control open. So most of this
suite is about drills that PASS while proving nothing, not drills that fail.

Every case starts from `_drill()`, which is clean, and changes exactly one
field. A FAIL is therefore attributable to that field rather than to a fixture
that was never going to pass — and `test_a_clean_drill_attests` is the
positive control that keeps the rest of the file from being vacuous.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from neuraxis.model import now_utc
from neuraxis.providers import ProviderOutcome, run_provider
from neuraxis.providers.drill import (
    MAX_DRILL_AGE,
    RESTORED,
    RollbackDrillProvider,
)

NOW = now_utc()


def _drill(**overrides) -> dict:
    """A drill that demonstrates a reversal. Every test breaks one thing."""
    record = {
        "drill_id": "DRILL-001",
        "mutation_class": "kernel-config",
        "performer": "agent-motor",
        "verifier": "github-ci",
        "outcome": RESTORED,
        "mutated": ["config/neuraxis.yaml"],
        "restored": ["config/neuraxis.yaml"],
        "baseline_digest": "sha256:abc123",
        "restored_digest": "sha256:abc123",
        "mutated_at": (NOW - timedelta(hours=2)).isoformat(),
        "rolled_back_at": (NOW - timedelta(hours=1)).isoformat(),
        "verified_at": (NOW - timedelta(minutes=30)).isoformat(),
        "evidence_ref": "ci://run/8814",
    }
    record.update(overrides)
    return record


def _log(tmp_path: Path, *records: dict) -> Path:
    path = tmp_path / "drill-log.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return path


def _run(tmp_path: Path, *records: dict, **config):
    return run_provider(RollbackDrillProvider(drill_log_path=_log(tmp_path, *records), **config))


def _detail(run) -> str:
    return run.result.detail


# ---------------------------------------------------------------------------
# The positive control
# ---------------------------------------------------------------------------


def test_a_clean_drill_attests(tmp_path):
    """Without this, every FAIL below is satisfied by a provider that denies always."""
    run = _run(tmp_path, _drill())
    assert run.attests
    assert run.result.outcome is ProviderOutcome.PASS
    assert run.result.evidence_ref.startswith("file://")
    assert run.result.facts["current"] == 1
    assert run.conformance == ()


# ---------------------------------------------------------------------------
# The two worth building for: drills that pass every skim and measure nothing
# ---------------------------------------------------------------------------


def test_a_drill_that_mutated_nothing_reversed_nothing(tmp_path):
    """The vacuous drill. Independent verifier, correct ordering, success —
    against an empty mutation, so the rollback restored an unchanged system."""
    run = _run(tmp_path, _drill(mutated=[], restored=[]))
    assert not run.attests
    assert "mutated nothing" in _detail(run)


def test_a_restoration_that_was_declared_rather_than_compared(tmp_path):
    """No digests means "restored" is the exit status of a command."""
    run = _run(tmp_path, _drill(baseline_digest="", restored_digest=""))
    assert not run.attests
    assert "declared, not compared" in _detail(run)


@pytest.mark.parametrize("absent", ["baseline_digest", "restored_digest"])
def test_one_missing_digest_is_as_bad_as_both(tmp_path, absent):
    """A comparison with one side missing is not a comparison."""
    run = _run(tmp_path, _drill(**{absent: ""}))
    assert not run.attests
    assert "declared, not compared" in _detail(run)


def test_a_restored_state_that_does_not_match_the_baseline(tmp_path):
    run = _run(tmp_path, _drill(restored_digest="sha256:different"))
    assert not run.attests
    assert "does not match the baseline" in _detail(run)


# ---------------------------------------------------------------------------
# Independence, completeness, ordering
# ---------------------------------------------------------------------------


def test_a_drill_verified_by_its_own_performer(tmp_path):
    run = _run(tmp_path, _drill(verifier="agent-motor"))
    assert not run.attests
    assert "its own performer" in _detail(run)


def test_independence_is_folded_not_merely_compared(tmp_path):
    """`agent-motor` with a zero-width space renders identically.

    ADR-0003: this comparison DENIES on collision, so it uses the aggressive
    fold. Under a strict comparison the invisible codepoint would buy a
    self-verified drill a pass.
    """
    run = _run(tmp_path, _drill(verifier="agent-​motor"))
    assert not run.attests
    assert "its own performer" in _detail(run)


@pytest.mark.parametrize("field", ["performer", "verifier"])
def test_a_missing_principal_is_a_breach(tmp_path, field):
    run = _run(tmp_path, _drill(**{field: "   "}))
    assert not run.attests
    assert f"no {field} recorded" in _detail(run)


def test_a_resource_mutated_and_not_restored(tmp_path):
    run = _run(
        tmp_path,
        _drill(mutated=["a.yaml", "b.yaml"], restored=["a.yaml"]),
    )
    assert not run.attests
    assert "did not restore b.yaml" in _detail(run)


def test_verification_that_does_not_post_date_the_rollback(tmp_path):
    """GV-07 check 4's shape: a stamp rather than an observation."""
    run = _run(tmp_path, _drill(verified_at=(NOW - timedelta(hours=3)).isoformat()))
    assert not run.attests
    assert "verified at or before the rollback" in _detail(run)


def test_verification_at_the_same_instant_is_one_automated_step(tmp_path):
    rolled_back = (NOW - timedelta(hours=1)).isoformat()
    run = _run(tmp_path, _drill(rolled_back_at=rolled_back, verified_at=rolled_back))
    assert not run.attests
    assert "verified at or before the rollback" in _detail(run)


def test_a_rollback_that_precedes_its_own_mutation(tmp_path):
    run = _run(tmp_path, _drill(rolled_back_at=(NOW - timedelta(hours=3)).isoformat()))
    assert not run.attests
    assert "incoherent" in _detail(run)


@pytest.mark.parametrize("outcome", ["failed", "partial", "skipped", "", "RESTORED_ISH"])
def test_only_restored_attests(tmp_path, outcome):
    """An unrecognised outcome is not read generously."""
    run = _run(tmp_path, _drill(outcome=outcome))
    assert not run.attests
    assert "is not 'restored'" in _detail(run)


def test_a_failed_drill_denies_rather_than_being_ignored(tmp_path):
    """A rollback that did not work is exactly what GV-05 must deny on."""
    run = _run(tmp_path, _drill(outcome="failed"))
    assert not run.attests


# ---------------------------------------------------------------------------
# The window — the failure that reads greenest
# ---------------------------------------------------------------------------


def _old(**overrides) -> dict:
    age = MAX_DRILL_AGE + timedelta(days=7)
    return _drill(
        mutated_at=(NOW - age - timedelta(hours=2)).isoformat(),
        rolled_back_at=(NOW - age).isoformat(),
        verified_at=(NOW - age + timedelta(hours=1)).isoformat(),
        **overrides,
    )


def test_a_clean_but_stale_drill_does_not_attest(tmp_path):
    """Nothing is wrong with the record. There is simply no evidence for now."""
    run = _run(tmp_path, _old())
    assert not run.attests
    assert "no drill within 30d" in _detail(run)
    assert run.result.facts["breaches"] == 0
    assert run.result.facts["current"] == 0


def test_one_fresh_drill_among_stale_ones_attests(tmp_path):
    run = _run(tmp_path, _old(drill_id="OLD"), _drill(drill_id="NEW"))
    assert run.attests
    assert run.result.facts["current"] == 1
    assert run.result.facts["sampled"] == 2


def test_a_breached_drill_inside_the_window_is_not_recent_evidence(tmp_path):
    """A fresh drill that breaches cannot also satisfy the recency requirement."""
    run = _run(tmp_path, _drill(mutated=[], restored=[]))
    assert not run.attests
    assert run.result.facts["current"] == 0


def test_the_window_may_be_tightened_and_not_widened(tmp_path):
    """A bound that constrains the evidence cannot be set by its supplier."""
    provider = RollbackDrillProvider(
        drill_log_path="x.jsonl", max_age=timedelta(days=3650)
    )
    assert provider.max_age == MAX_DRILL_AGE

    tightened = RollbackDrillProvider(drill_log_path="x.jsonl", max_age=timedelta(days=1))
    assert tightened.max_age == timedelta(days=1)


def test_a_tightened_window_rejects_a_drill_the_default_would_accept(tmp_path):
    week_old = _drill(
        mutated_at=(NOW - timedelta(days=8)).isoformat(),
        rolled_back_at=(NOW - timedelta(days=7)).isoformat(),
        verified_at=(NOW - timedelta(days=7) + timedelta(hours=1)).isoformat(),
    )
    assert _run(tmp_path, week_old).attests
    assert not _run(tmp_path, week_old, max_age=timedelta(days=1)).attests


# ---------------------------------------------------------------------------
# Fail closed
# ---------------------------------------------------------------------------


def test_a_missing_log_is_not_live(tmp_path):
    run = run_provider(RollbackDrillProvider(drill_log_path=tmp_path / "absent.jsonl"))
    assert not run.attests
    assert "positive control" in _detail(run)


def test_an_empty_log_is_no_drill_rather_than_no_failures(tmp_path):
    path = tmp_path / "drill-log.jsonl"
    path.write_text("", encoding="utf-8")
    run = run_provider(RollbackDrillProvider(drill_log_path=path))
    assert not run.attests
    assert "positive control" in _detail(run)


def test_a_malformed_line_fails_rather_than_being_skipped(tmp_path):
    path = tmp_path / "drill-log.jsonl"
    path.write_text(json.dumps(_drill()) + "\n{not json\n", encoding="utf-8")
    run = run_provider(RollbackDrillProvider(drill_log_path=path))
    assert not run.attests


def test_a_bom_written_log_still_reads(tmp_path):
    """PowerShell writes one by default; an encoding detail must not read as a breach."""
    path = tmp_path / "drill-log.jsonl"
    path.write_bytes(("﻿" + json.dumps(_drill())).encode("utf-8"))
    assert run_provider(RollbackDrillProvider(drill_log_path=path)).attests


@pytest.mark.parametrize("field", ["mutated_at", "rolled_back_at", "verified_at"])
def test_a_naive_timestamp_is_a_breach_not_a_convenience(tmp_path, field):
    run = _run(tmp_path, _drill(**{field: "2026-09-01T10:00:00"}))
    assert not run.attests
    assert "no timezone offset" in _detail(run)


@pytest.mark.parametrize("field", ["mutated", "restored"])
def test_a_resource_string_is_refused_rather_than_iterated(tmp_path, field):
    """`"mutated": "config.yaml"` would otherwise become 12 mutated characters."""
    run = _run(tmp_path, _drill(**{field: "config.yaml"}))
    assert not run.attests
    assert f"`{field}` is not a list" in _detail(run)


def test_a_non_string_resource_is_refused(tmp_path):
    run = _run(tmp_path, _drill(mutated=["a.yaml", 7]))
    assert not run.attests
    assert "not a list" in _detail(run)


def test_one_breach_fails_the_whole_sample(tmp_path):
    """Reversibility holds or does not; it is not a ratio to optimise."""
    run = _run(tmp_path, _drill(drill_id="GOOD"), _drill(drill_id="BAD", mutated=[], restored=[]))
    assert not run.attests
    assert run.result.facts["breaches"] == 1
    assert run.result.facts["sampled"] == 2


# ---------------------------------------------------------------------------
# The harness rules
# ---------------------------------------------------------------------------


def test_the_vacuity_probe_fails_as_the_harness_requires(tmp_path):
    probe = RollbackDrillProvider(drill_log_path=_log(tmp_path, _drill())).vacuity_probe()
    assert probe.outcome is ProviderOutcome.FAIL
    assert "mutated nothing" in probe.detail


def test_the_vacuity_probe_is_not_the_easiest_possible_breach(tmp_path):
    """It must fail on vacuity, not on a field any trivial check would catch.

    A probe recording `outcome: failed` would be caught by a provider that
    reads only that field, and such a provider would satisfy the harness while
    checking almost nothing.
    """
    provider = RollbackDrillProvider(drill_log_path=_log(tmp_path, _drill()))
    probe = provider.vacuity_probe()
    assert "is not 'restored'" not in probe.detail
    assert "no verifier" not in probe.detail
    assert "its own performer" not in probe.detail


def test_a_pass_always_cites_its_evidence(tmp_path):
    run = _run(tmp_path, _drill())
    assert run.attests and run.result.evidence_ref


def test_the_provider_is_wired_and_claims_gv_05():
    from neuraxis.providers.registry import providers_for

    wired = {p.control: p for p in providers_for()}
    assert wired["GV-05"].name == "nx/rollback-drill"
    assert not type(wired["GV-05"]).__name__.startswith("Unwired")
