"""GV-07 ratification provider (v0.5.1).

The control is *automation may propose, never merge*. Each breach class gets
its own test, and each is paired with the clean-log positive control — without
that pairing a provider that failed everything would pass this whole file.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from neuraxis.providers import ProviderOutcome, providers_for, run_provider
from neuraxis.providers.builtin import GateLogRatificationProvider

UTC = timezone.utc
T0 = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)


def _rec(**over):
    base = {
        "change_id": "SECB-PF-412",
        "change_class": "kernel",
        "proposer": "agent-drafter",
        "ratifier": "ounkhamvilay",
        "ratifier_kind": "human",
        "proposed_at": T0.isoformat(),
        "ratified_at": (T0 + timedelta(hours=1)).isoformat(),
        "merged_at": (T0 + timedelta(hours=1, minutes=2)).isoformat(),
        "gate": "BADF-07",
        "evidence_ref": "github://bstBizEra/secb_pf/pull/412",
    }
    base.update(over)
    return base


def _log(tmp_path, records, name="gate-log.jsonl", bom=False):
    path = tmp_path / name
    text = "\n".join(json.dumps(r) for r in records)
    path.write_bytes((("﻿" if bom else "") + text).encode("utf-8"))
    return path


def _run(tmp_path, records, **kw):
    return run_provider(GateLogRatificationProvider(gate_log_path=_log(tmp_path, records, **kw)))


# ---- positive control --------------------------------------------------


def test_clean_gate_log_passes(tmp_path):
    """POSITIVE CONTROL. Every breach assertion below is vacuous without it."""
    run = _run(tmp_path, [_rec(), _rec(change_id="SECB-PF-413", proposer="agent-cortex")])
    assert run.attests is True
    assert run.result.facts["sampled"] == 2
    assert run.result.facts["breaches"] == 0


def test_optional_fields_may_be_absent(tmp_path):
    """Only the fields the checks turn on are required."""
    run = _run(tmp_path, [
        {
            "change_id": "X-1", "proposer": "agent-drafter", "ratifier": "vily",
            "ratifier_kind": "human",
            "ratified_at": T0.isoformat(),
            "merged_at": (T0 + timedelta(minutes=5)).isoformat(),
        }
    ])
    assert run.attests is True


# ---- breach classes ----------------------------------------------------


def test_merge_with_no_ratifier(tmp_path):
    run = _run(tmp_path, [_rec(ratifier=None)])
    assert run.attests is False
    assert "merged with no ratifier" in run.result.detail


def test_self_ratification(tmp_path):
    run = _run(tmp_path, [_rec(ratifier="agent-drafter")])
    assert run.attests is False
    assert "self-ratified by agent-drafter" in run.result.detail


def test_automation_ratifier_is_refused(tmp_path):
    """A bot ratifier satisfies the record and defeats the control."""
    run = _run(tmp_path, [_rec(ratifier="ci-bot", ratifier_kind="automation")])
    assert run.attests is False
    assert "not human" in run.result.detail


def test_unspecified_ratifier_kind_is_refused(tmp_path):
    """Absent is not human. Fail closed on the field the control turns on."""
    run = _run(tmp_path, [_rec(ratifier_kind=None)])
    assert run.attests is False
    assert "not human" in run.result.detail


def test_ratified_after_merge(tmp_path):
    """The check worth building for: a gate that has become a rubber stamp."""
    run = _run(tmp_path, [
        _rec(
            merged_at=(T0 + timedelta(hours=1)).isoformat(),
            ratified_at=(T0 + timedelta(hours=3)).isoformat(),
        )
    ])
    assert run.attests is False
    assert "ratified after merge" in run.result.detail


def test_ratified_before_proposed(tmp_path):
    run = _run(tmp_path, [
        _rec(
            proposed_at=(T0 + timedelta(hours=5)).isoformat(),
            ratified_at=(T0 + timedelta(hours=1)).isoformat(),
            merged_at=(T0 + timedelta(hours=6)).isoformat(),
        )
    ])
    assert run.attests is False
    assert "ratified before it was proposed" in run.result.detail


def test_missing_proposer(tmp_path):
    run = _run(tmp_path, [_rec(proposer=None)])
    assert run.attests is False
    assert "no proposer recorded" in run.result.detail


@pytest.mark.parametrize("field", ["ratified_at", "merged_at"])
def test_naive_timestamp_is_a_breach(tmp_path, field):
    """Ordering across mixed or absent offsets is not decidable."""
    run = _run(tmp_path, [_rec(**{field: "2026-09-14T09:00:00"})])
    assert run.attests is False
    assert "no timezone offset" in run.result.detail


@pytest.mark.parametrize("field", ["ratified_at", "merged_at"])
def test_missing_required_timestamp_is_a_breach(tmp_path, field):
    run = _run(tmp_path, [_rec(**{field: None})])
    assert run.attests is False
    assert field in run.result.detail


def test_unparseable_timestamp_is_a_breach(tmp_path):
    run = _run(tmp_path, [_rec(ratified_at="last Tuesday")])
    assert run.attests is False
    assert "not ISO-8601" in run.result.detail


def test_one_breach_fails_the_whole_sample(tmp_path):
    """Ratification holds or does not — it is not a ratio to optimise."""
    run = _run(tmp_path, [_rec(), _rec(change_id="bad", ratifier="agent-drafter"), _rec()])
    assert run.attests is False
    assert run.result.facts["breaches"] == 1
    assert run.result.facts["sampled"] == 3


# ---- conformance -------------------------------------------------------


def test_absent_log_fails_the_positive_control(tmp_path):
    """No log means the check is not live, which is a FAIL, not a PASS."""
    run = run_provider(GateLogRatificationProvider(gate_log_path=tmp_path / "absent.jsonl"))
    assert run.attests is False
    assert "positive-control-failed" in run.conformance


def test_empty_log_is_no_evidence_not_zero_breaches(tmp_path):
    run = _run(tmp_path, [])
    assert run.attests is False


def test_malformed_log_fails(tmp_path):
    path = tmp_path / "gate-log.jsonl"
    path.write_text("{not json\n", encoding="utf-8")
    run = run_provider(GateLogRatificationProvider(gate_log_path=path))
    assert run.attests is False


def test_bom_does_not_break_the_check(tmp_path):
    """PowerShell writes a BOM by default; it must not read as 'not live'."""
    run = _run(tmp_path, [_rec()], bom=True)
    assert run.attests is True


def test_bom_does_not_mask_a_real_breach(tmp_path):
    run = _run(tmp_path, [_rec(ratifier="agent-drafter")], bom=True)
    assert run.attests is False
    assert "self-ratified" in run.result.detail


def test_its_own_vacuity_probe_fails_as_required(tmp_path):
    provider = GateLogRatificationProvider(gate_log_path=tmp_path / "x.jsonl")
    assert provider.vacuity_probe().outcome is ProviderOutcome.FAIL


def test_a_passing_run_cites_the_log_it_read(tmp_path):
    path = _log(tmp_path, [_rec()])
    run = run_provider(GateLogRatificationProvider(gate_log_path=path))
    assert run.attests is True
    assert str(path) in run.result.evidence_ref


# ---- registry ----------------------------------------------------------


def test_gv_07_is_wired_and_reachable():
    gv07 = [p for p in providers_for("GV-07")]
    assert [p.name for p in gv07] == ["badf/gate-log"]
    assert not hasattr(gv07[0], "blocked_on"), "GV-07 should no longer be declared unwired"
